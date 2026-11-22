"""Operator-only institution directory; no academic data access or public provisioning."""
from fastapi import APIRouter, Request
from sqlalchemy import select, update
from pydantic import BaseModel, ConfigDict
from typing import Literal
from campusflow.product.catalog import transaction, ProductError
from .onboarding_tables import institutions
from .tables import memberships, sessions
router=APIRouter(prefix='/api/platform',tags=['Platform operations'])
class StatusInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    status: Literal['ACTIVE','SUSPENDED']
def operator(request):
    if request.state.user['role']!='platform_super_admin':
        raise ProductError('Platform operator access required',403)
@router.get('/institutions')
def directory(request:Request):
    operator(request)
    with transaction() as conn:
        return {'data':[dict(row) for row in conn.execute(select(institutions)).mappings()]}
@router.put('/institutions/{identifier}/status')
def status(identifier:str,body:StatusInput,request:Request):
    operator(request)
    if identifier==request.state.user['institution_id']:
        raise ProductError('The operator workspace cannot suspend itself',409)
    with transaction() as conn:
        result=conn.execute(update(institutions).where(institutions.c.institution_id==identifier).values(status=body.status))
        if not result.rowcount: raise ProductError('Institution not found',404)
        conn.execute(sessions.delete().where(sessions.c.user_id.in_(select(memberships.c.user_id).where(memberships.c.institution_id==identifier))))
    return {'data':{'institution_id':identifier,'status':body.status}}
