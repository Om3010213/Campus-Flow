"""Institution-bound, single-use invitations. No role or tenant from acceptance input."""
import secrets
import time
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select, update
from campusflow.product.catalog import transaction, ProductError
from campusflow.tenancy import institution_id
from . import service
from .tables import invitations, users, memberships
from .routes import AccessInput, validate_links
from .onboarding import EmailInput, VerifyInput, limit

router = APIRouter(tags=["Institution invitations"])


class InviteInput(EmailInput, AccessInput):
    role: Literal["planner", "teacher", "student", "viewer"] = "viewer"
    scopes: list[str] = Field(default_factory=lambda:["College"])


def digest(request, token):
    return service.digest(request.app.state.security, "institution-invitation:"+token)


def send(conn, request, row):
    token=secrets.token_urlsafe(32)
    conn.execute(update(invitations).where(invitations.c.id==row["id"]).values(
        digest=digest(request,token), expires_at=time.time()+72*3600))
    return "/accept-invitation#token="+token


@router.get("/api/auth/invitations")
def list_invitations():
    with transaction() as conn:
        rows=conn.execute(select(invitations).where(invitations.c.institution_id==institution_id())).mappings()
        return {"data":[{k:v for k,v in r.items() if k!="digest"} for r in rows]}


@router.post("/api/auth/invitations",status_code=201)
def invite(body:InviteInput,request:Request):
    limit(request,body.email,"invite-send")
    with transaction() as conn:
        validate_links(conn,body)
        if conn.execute(select(users.c.id).join(memberships,users.c.id==memberships.c.user_id).where(users.c.username==body.email)).first():
            raise ProductError("This address already has an account; automatic membership transfer is not allowed.",409)
        conn.execute(update(invitations).where(invitations.c.institution_id==institution_id(), invitations.c.email==body.email,
            invitations.c.used_at.is_(None)).values(revoked_at=time.time()))
        identifier=uuid4().hex
        conn.execute(invitations.insert().values(id=identifier,institution_id=institution_id(),email=body.email,
            role=body.role,scopes=body.scopes,faculty_id=body.faculty_id,batch_ids=body.batch_ids,
            digest=secrets.token_hex(32),expires_at=time.time(),inviter_id=request.state.user["id"]))
        path=send(conn,request,{"id":identifier,"email":body.email})
    return {"data":{"id":identifier,"acceptance_path":path},"message":"Invitation created. Share the private link securely with the intended recipient."}


@router.post("/api/auth/invitations/{identifier}/resend")
def resend(identifier:str,request:Request):
    limit(request,identifier,"invite-send")
    with transaction() as conn:
        row=conn.execute(select(invitations).where(invitations.c.id==identifier,
            invitations.c.institution_id==institution_id(),invitations.c.used_at.is_(None),invitations.c.revoked_at.is_(None))).mappings().first()
        if not row: raise ProductError("Active invitation not found",404)
        path=send(conn,request,row)
    return {"data":{"acceptance_path":path},"message":"New invitation link created; previous link revoked."}


@router.delete("/api/auth/invitations/{identifier}")
def revoke(identifier:str):
    with transaction() as conn:
        changed=conn.execute(update(invitations).where(invitations.c.id==identifier,
            invitations.c.institution_id==institution_id()).values(revoked_at=time.time()))
        if not changed.rowcount: raise ProductError("Invitation not found",404)
    return {"data":None}


@router.post("/api/onboarding/accept-invitation")
def accept(body:VerifyInput,request:Request):
    value=digest(request,body.token)
    limit(request,value,"invite-accept")
    with transaction() as conn:
        row=conn.execute(select(invitations).where(invitations.c.digest==value,invitations.c.used_at.is_(None),
            invitations.c.revoked_at.is_(None),invitations.c.expires_at>time.time())).mappings().first()
        if not row: raise ProductError("Invitation is invalid, expired or already used",400)
        from .onboarding_tables import institutions
        if not conn.execute(select(institutions.c.institution_id).where(institutions.c.institution_id==row["institution_id"], institutions.c.status=="ACTIVE")).first():
            raise ProductError("Institution is not active",403)
        from campusflow.tenancy import institution
        with institution(row["institution_id"]):
            validate_links(conn,InviteInput(email=row["email"],role=row["role"],scopes=row["scopes"],faculty_id=row["faculty_id"],batch_ids=row["batch_ids"]))
            existing=conn.execute(select(users).where(users.c.username==row["email"])).mappings().first()
            if existing:
                actor=request.state.user
                if not actor or actor["id"]!=existing["id"] or not service.verify(existing["password_hash"],body.password):
                    raise ProductError("Sign in to the invited account before accepting this invitation",403)
                if conn.execute(select(memberships.c.user_id).where(memberships.c.user_id==existing["id"])).first():
                    raise ProductError("Account already belongs to an institution",409)
                conn.execute(memberships.insert().values(user_id=existing["id"],institution_id=row["institution_id"],
                    role=row["role"],scopes=row["scopes"],active=1,faculty_id=row["faculty_id"],batch_ids=row["batch_ids"]))
                service.revoke_user(conn,existing["id"])
            else:
                service.create_user(conn,row["email"],body.password,row["role"],row["scopes"],must_change=False,
                    tenant=row["institution_id"],faculty_id=row["faculty_id"],batch_ids=row["batch_ids"])
        conn.execute(update(invitations).where(invitations.c.id==row["id"]).values(used_at=time.time()))
    return {"status":"invitation_accepted","message":"Invitation accepted. Sign in with your email and password."}
