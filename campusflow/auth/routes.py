import time
from typing import Literal
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update, delete, func

from campusflow.product.catalog import ProductError, transaction
from campusflow.product.database import database
from . import service
from .tables import users, sessions, memberships
from campusflow.tenancy import institution_id
from campusflow.product import database as db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AccessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["administrator", "planner", "viewer", "teacher", "student"] = "viewer"
    scopes: list[str] = Field(default_factory=list, max_length=100)
    active: bool = True
    faculty_id: str | None = None
    batch_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("scopes")
    @classmethod
    def valid_scopes(cls, values):
        if any(not v.strip() or len(v) > 200 or v.strip() == "*" for v in values):
            raise ValueError("Scopes must be explicit names of 1–200 characters; wildcards are not allowed")
        return sorted(set(v.strip() for v in values))


class UserCreate(Credentials, AccessInput):
    password: str = Field(min_length=12, max_length=128)


def reply(response, config, token, user):
    response.set_cookie(config.cookie, token, max_age=config.session_seconds if user else 1800,
                        secure=config.production, httponly=True, samesite="strict", path="/")
    return {"status": "success", "data": {"user": service.public_user(user) if user else None,
                                            "csrf_token": service.csrf(config, token)}}


@router.get("/session")
def current(request: Request, response: Response):
    config = request.app.state.security
    token = request.state.token
    if not request.state.session:
        with transaction() as conn:
            conn.execute(delete(sessions).where(sessions.c.expires_at <= time.time()))
            token = service.issue(conn, config)
    return reply(response, config, token, request.state.user)


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    config = request.app.state.security
    user = service.authenticate(config, body.username, body.password, request.client.host if request.client else "unknown")
    with transaction() as conn:
        latest = conn.execute(select(users).where(users.c.id == user["id"])).mappings().one()
        if not latest["active"] or latest["password_hash"] != user["password_hash"]:
            raise ProductError("Invalid username or password.", 401)
        conn.execute(delete(sessions).where(sessions.c.digest == service.digest(config, request.state.token)))
        if service.hasher.check_needs_rehash(user["password_hash"]):
            conn.execute(update(users).where(users.c.id == user["id"]).values(password_hash=service.hasher.hash(body.password)))
        token = service.issue(conn, config, user["id"])
        latest_user = service.member_user(conn, dict(latest))
        if not latest_user:
            raise ProductError("Account access changed. Sign in again.",401)
    return reply(response, config, token, latest_user)


@router.post("/logout")
def logout(request: Request, response: Response):
    config = request.app.state.security
    with transaction() as conn:
        conn.execute(delete(sessions).where(sessions.c.digest == service.digest(config, request.state.token)))
    response.delete_cookie(config.cookie, path="/", secure=config.production, httponly=True, samesite="strict")
    return {"status": "success", "data": None}


@router.post("/password")
def change_password(body: PasswordChange, request: Request, response: Response):
    user, config = request.state.user, request.app.state.security
    service.reserve_attempt(config, user["username"], request.client.host if request.client else "unknown", "password")
    if not service.verify(user["password_hash"], body.current_password):
        raise ProductError("Current password is incorrect.", 400)
    if body.new_password == body.current_password:
        raise ProductError("Choose a different password.")
    hashed = service.hasher.hash(body.new_password)
    with transaction() as conn:
        changed = conn.execute(update(users).where(users.c.id == user["id"], users.c.password_hash == user["password_hash"])
                               .values(password_hash=hashed, must_change_password=0))
        if not changed.rowcount:
            raise ProductError("Account changed. Sign in again.", 401)
        service.revoke_user(conn, user["id"])
        token = service.issue(conn, config, user["id"])
    user["must_change_password"] = 0
    return reply(response, config, token, user)


def validate_links(conn, body):
    if body.role == "teacher" and not body.faculty_id:
        raise ProductError("Teacher accounts require an assigned faculty record")
    if body.role == "student" and not body.batch_ids:
        raise ProductError("Student accounts require assigned batches/sections")
    if body.faculty_id and not conn.execute(select(db.faculty.c.id).where(db.faculty.c.id == body.faculty_id)).first():
        raise ProductError("Faculty record not found in this institution")
    for batch in body.batch_ids:
        if not conn.execute(select(db.batches.c.id).where(db.batches.c.id == batch)).first():
            raise ProductError("Batch/section not found in this institution")


@router.get("/users")
def list_users():
    with database().connect() as conn:
        rows = conn.execute(select(users).join(memberships, users.c.id == memberships.c.user_id)
            .where(memberships.c.institution_id == institution_id(), memberships.c.role != "platform_super_admin").order_by(users.c.username)).mappings()
        result=[]
        for row in rows:
            member=conn.execute(select(memberships).where(memberships.c.user_id==row["id"])).mappings().one()
            result.append(service.public_user({**dict(row), **dict(member)}))
        return {"status":"success","data":result}


@router.post("/users", status_code=201)
def add_user(body: UserCreate):
    with transaction() as conn:
        validate_links(conn, body)
        user = service.create_user(conn, body.username, body.password, body.role, body.scopes,
            faculty_id=body.faculty_id, batch_ids=body.batch_ids)
        if not body.active:
            conn.execute(update(users).where(users.c.id == user["id"]).values(active=0))
            conn.execute(update(memberships).where(memberships.c.user_id == user["id"]).values(active=0))
            user["active"] = 0
    return {"status":"success","data":service.public_user(user)}


@router.put("/users/{identifier}")
def update_access(identifier: str, body: AccessInput):
    with transaction() as conn:
        member = conn.execute(select(memberships).where(memberships.c.user_id==identifier,
            memberships.c.institution_id==institution_id())).mappings().first()
        if not member:
            raise ProductError("User not found",404)
        if member["role"] == "platform_super_admin":
            raise ProductError("Platform accounts require local operator management",403)
        validate_links(conn,body)
        count=conn.execute(select(func.count()).select_from(memberships).where(
            memberships.c.institution_id==institution_id(),memberships.c.role=="administrator",memberships.c.active==1)).scalar()
        if member["role"]=="administrator" and member["active"] and count==1 and (body.role!="administrator" or not body.active):
            raise ProductError("The last active administrator cannot be disabled or demoted.",409)
        conn.execute(update(memberships).where(memberships.c.user_id==identifier).values(**body.model_dump()))
        conn.execute(update(users).where(users.c.id==identifier).values(active=int(body.active)))
        service.revoke_user(conn,identifier)
        row=dict(conn.execute(select(users).where(users.c.id==identifier)).mappings().one())
        return {"status":"success","data":service.public_user({**row,**body.model_dump(),"institution_id":institution_id()})}
