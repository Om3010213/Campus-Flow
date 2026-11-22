"""Direct signup, unprivileged accounts and explicit institution ownership."""
import re
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from campusflow.api.main import app
from campusflow.auth import service
from campusflow.auth.tables import users,memberships,profiles
from campusflow.auth.onboarding_tables import registrations
from campusflow.product import database as db
PASSWORD='A private onboarding passphrase!'
BODY={'name':'Asha Rao','email':'asha@north.example','password':PASSWORD}
@pytest.fixture
def smtp():
    # Compatibility fixture name: captures API-returned invitation links, no mail server.
    return SimpleNamespace(messages=[])
@pytest.fixture
def client(tmp_path,monkeypatch,smtp):
    monkeypatch.setenv('CAMPUSFLOW_DATABASE_URL','sqlite:///'+(tmp_path/'onboarding.db').as_posix())
    monkeypatch.setenv('CAMPUSFLOW_ENV','development')
    monkeypatch.setenv('CAMPUSFLOW_ONBOARDING_ENABLED','1')
    monkeypatch.delenv('CAMPUSFLOW_EMAIL_PROVIDER',raising=False)
    def capture(response):
        response.read()
        if response.headers.get('content-type','').startswith('application/json'):
            value=response.json().get('data')
            if isinstance(value,dict) and value.get('acceptance_path'): smtp.messages.append(value['acceptance_path'])
    with TestClient(app) as client:
        client.event_hooks['response'].append(capture)
        client.headers['X-CSRF-Token']=client.get('/api/auth/session').json()['data']['csrf_token']
        yield client

def token(smtp): return re.search(r'#token=([A-Za-z0-9_-]{43})',smtp.messages[-1]).group(1)

def signin(client):
    result=client.post('/api/auth/login',json={'username':BODY['email'],'password':PASSWORD})
    assert result.status_code==200,result.text
    client.headers['X-CSRF-Token']=result.json()['data']['csrf_token']
    return result.json()['data']['user']

def test_direct_signup_without_mail_has_no_admin_privileges(client):
    assert client.get('/api/onboarding/status').json()['data']['email_verification_required'] is False
    assert client.post('/api/onboarding/register',json=BODY).status_code==201
    with db.database().connect() as conn:
        row=conn.execute(select(users)).mappings().one()
        assert row['password_hash'].startswith('$argon2id$') and service.verify(row['password_hash'],PASSWORD)
        assert conn.execute(select(func.count()).select_from(memberships)).scalar_one()==0
        assert conn.execute(select(profiles.c.name)).scalar_one()==BODY['name']
    user=signin(client)
    assert user['role']=='unassigned' and user['institution_id'] is None
    for path in ('/api/auth/users','/api/product/catalog','/api/product/versions','/api/platform/institutions'):
        assert client.get(path).status_code==403
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/product/catalog').status_code==401

@pytest.mark.parametrize('kind',['SCHOOL','COLLEGE'])
def test_explicit_workspace_creation_isolated_and_one_time(client,kind):
    client.post('/api/onboarding/register',json=BODY);signin(client)
    body={'institution_name':'My '+kind,'institution_type':kind}
    result=client.post('/api/onboarding/workspace',json=body)
    assert result.status_code==201,result.text
    data=result.json()['data'];client.headers['X-CSRF-Token']=data['csrf_token']
    assert data['user']['role']=='administrator' and data['user']['institution_type']==kind
    assert client.get('/api/product/catalog').json()['data']['faculty']==[]
    assert client.post('/api/onboarding/workspace',json=body).status_code==409

@pytest.mark.parametrize('extra',[{'role':'administrator'},{'institution_id':'existing'},{'institution_name':'Existing'},{'verified_at':1}])
def test_signup_cannot_choose_privileges(client,extra):
    assert client.post('/api/onboarding/register',json={**BODY,**extra}).status_code==422

def test_duplicate_does_not_change_password(client):
    assert client.post('/api/onboarding/register',json=BODY).status_code==201
    assert client.post('/api/onboarding/register',json={**BODY,'password':'Attacker passphrase long!'}).status_code==409
    signin(client)

def test_signup_csrf_throttling_and_gate(client,monkeypatch):
    assert client.post('/api/onboarding/register',json=BODY,headers={'X-CSRF-Token':''}).status_code==403
    for i in range(5): assert client.post('/api/onboarding/register',json=BODY).status_code==(201 if i==0 else 409)
    assert client.post('/api/onboarding/register',json=BODY).status_code==429
    monkeypatch.setenv('CAMPUSFLOW_ONBOARDING_ENABLED','0')
    assert client.post('/api/onboarding/register',json=BODY).status_code==503

def test_retired_verification_cannot_activate_account(client):
    assert client.post('/api/onboarding/verify',json={'token':'x'*43,'password':PASSWORD}).status_code==401
    assert client.post('/api/onboarding/resend',json=BODY).status_code==401

@pytest.mark.parametrize('email',['bad','a@b','a\r\nBcc:evil@else.example','a..b@college.example'])
def test_email_validation(client,email):
    assert client.post('/api/onboarding/register',json={**BODY,'email':email}).status_code==422

def test_institution_migration_preserves_legacy_registration(tmp_path):
    from sqlalchemy import create_engine, text
    from campusflow.product.migrations import _upgrade_legacy as upgrade
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy-registration.db').as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)"))
        for version in (1, 2, 3):
            conn.execute(text("INSERT INTO schema_versions VALUES (:version)"), {"version": version})
        conn.execute(text("CREATE TABLE college_registrations (id VARCHAR PRIMARY KEY, email VARCHAR UNIQUE NOT NULL, name VARCHAR NOT NULL, college_name VARCHAR NOT NULL, password_hash VARCHAR NOT NULL, created_at FLOAT NOT NULL, verified_at FLOAT)"))
        conn.execute(text("INSERT INTO college_registrations VALUES ('old-id', 'old@college.example', 'Legacy Admin', 'Legacy College', 'preserved-hash', 100, NULL)"))
    upgrade(engine)
    upgrade(engine)
    with engine.connect() as conn:
        row = conn.execute(select(registrations)).mappings().one()
        assert row["id"] == "old-id" and row["password_hash"] == "preserved-hash"
        assert row["college_name"] == row["institution_name"] == "Legacy College"
        assert row["institution_type"] == "COLLEGE"
    engine.dispose()




def test_workspace_cannot_join_existing_institution(client):
    client.post('/api/onboarding/register',json=BODY);signin(client)
    assert client.post('/api/onboarding/workspace',json={'institution_name':'Other','institution_type':'SCHOOL','institution_id':'existing'}).status_code==422


def test_inactive_membership_never_becomes_unassigned(client):
    from sqlalchemy import update
    from campusflow.product.catalog import transaction
    client.post('/api/onboarding/register',json=BODY);signin(client)
    r=client.post('/api/onboarding/workspace',json={'institution_name':'School','institution_type':'SCHOOL'})
    user=r.json()['data']['user']
    with transaction() as conn: conn.execute(update(memberships).where(memberships.c.user_id==user['id']).values(active=0))
    assert client.get('/api/auth/session').json()['data']['user'] is None
    assert client.post('/api/auth/login',json={'username':BODY['email'],'password':PASSWORD},headers={'X-CSRF-Token':client.get('/api/auth/session').json()['data']['csrf_token']}).status_code==401
