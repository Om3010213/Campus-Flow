"""Direct password signup followed by explicit, isolated institution onboarding."""
import os
import time
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, delete
from campusflow.product.catalog import ProductError, transaction, save_settings
from campusflow.tenancy import institution
from . import service
from .mail import normalize_email
from .tables import users, profiles, memberships, sessions
from .onboarding_tables import institutions

router=APIRouter(prefix="/api/onboarding",tags=["Institution onboarding"])
PUBLIC_PATHS={"/api/onboarding/status","/api/onboarding/register","/api/onboarding/accept-invitation"}

class EmailInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    email:str=Field(min_length=3,max_length=254)
    @field_validator("email")
    @classmethod
    def email_address(cls,value): return normalize_email(value)

class RegistrationInput(EmailInput):
    name:str=Field(min_length=1,max_length=120)
    password:str=Field(min_length=12,max_length=128)
    @field_validator("name")
    @classmethod
    def name_valid(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 for c in value): raise ValueError("Enter a valid name")
        return value

class WorkspaceInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    institution_name:str=Field(min_length=1,max_length=200)
    institution_type:Literal["SCHOOL","COLLEGE"]
    @field_validator("institution_name")
    @classmethod
    def clean_name(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 for c in value): raise ValueError("Enter a valid institution name")
        return value

class VerifyInput(BaseModel):
    # Compatibility name for invitation acceptance, not email verification.
    model_config=ConfigDict(extra="forbid")
    token:str=Field(min_length=43,max_length=43,pattern=r"^[A-Za-z0-9_-]+$")
    password:str=Field(min_length=12,max_length=128)

def limit(request,key,action):
    service.reserve_attempt(request.app.state.security,key,request.client.host if request.client else "unknown",action)

def enabled(): return os.getenv("CAMPUSFLOW_ONBOARDING_ENABLED","1")=="1"

@router.get("/status")
def status():
    return {"data":{"registration_enabled":enabled(),"workspace_activation_enabled":True,
        "email_verification_required":False,"reason":"ready" if enabled() else "feature_disabled",
        "message":"Create an account with your name, email and password." if enabled() else "Registration is disabled."}}

@router.post("/register",status_code=201)
def register(body:RegistrationInput,request:Request):
    if not enabled(): raise ProductError("Registration is disabled",503)
    if request.state.user: raise ProductError("Sign out before creating another account",409)
    limit(request,body.email,"signup")
    hashed=service.hasher.hash(body.password)
    with transaction() as conn:
        if conn.execute(select(users.c.id).where(users.c.username==body.email)).first():
            raise ProductError("Registration could not be completed. Try signing in or contact your administrator.",409)
        identifier=uuid4().hex
        conn.execute(users.insert().values(id=identifier,username=body.email,password_hash=hashed,
            role="viewer",scopes=[],active=1,must_change_password=0))
        conn.execute(profiles.insert().values(user_id=identifier,name=body.name))
    return {"status":"registered","message":"Account created. Sign in with your email and password."}

@router.post("/workspace",status_code=201)
def create_workspace(body:WorkspaceInput,request:Request,response:Response):
    from .routes import reply
    user=request.state.user
    limit(request,user["id"],"workspace-create")
    with transaction() as conn:
        if conn.execute(select(memberships.c.user_id).where(memberships.c.user_id==user["id"])).first():
            raise ProductError("This account already belongs to an institution",409)
        if not conn.execute(select(profiles.c.user_id).where(profiles.c.user_id==user["id"])).first():
            raise ProductError("Account onboarding is unavailable",403)
        tenant=uuid4().hex
        conn.execute(institutions.insert().values(institution_id=tenant,institution_name=body.institution_name,
            institution_type=body.institution_type,created_at=time.time(),status="ACTIVE"))
        conn.execute(memberships.insert().values(user_id=user["id"],institution_id=tenant,role="administrator",
            scopes=[],active=1,batch_ids=[]))
        with institution(tenant):
            save_settings(conn,{"working_days":["Monday","Tuesday","Wednesday","Thursday","Friday"],
                "start":"09:00","end":"16:00","slot_minutes":40 if body.institution_type=="SCHOOL" else 60,
                "breaks":[{"start":"10:20","end":"10:40"},{"start":"12:00","end":"12:40"}] if body.institution_type=="SCHOOL" else [{"start":"12:00","end":"13:00"}]})
        service.revoke_user(conn,user["id"])
        token=service.issue(conn,request.app.state.security,user["id"])
        current=service.member_user(conn,dict(conn.execute(select(users).where(users.c.id==user["id"])).mappings().one()))
    return reply(response,request.app.state.security,token,current)
