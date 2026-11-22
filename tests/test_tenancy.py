"""Password onboarding, trusted membership and cross-institution integration."""
import time
import pytest
from test_onboarding import client, smtp, token, PASSWORD


def login(client, email):
    csrf=client.get('/api/auth/session').json()['data']['csrf_token']
    response=client.post('/api/auth/login',json={'username':email,'password':PASSWORD},headers={'X-CSRF-Token':csrf})
    assert response.status_code==200,response.text
    client.headers['X-CSRF-Token']=response.json()['data']['csrf_token']
    return response.json()['data']['user']


def register(client,smtp,kind,email):
    response=client.post('/api/onboarding/register',json={'name':'Test Administrator','email':email,'password':PASSWORD})
    assert response.status_code==201,response.text
    account=login(client,email)
    assert account['role']=='unassigned'
    response=client.post('/api/onboarding/workspace',json={'institution_type':kind,'institution_name':kind+' Test'})
    assert response.status_code==201,response.text
    client.headers['X-CSRF-Token']=response.json()['data']['csrf_token']
    return response.json()['data']['user']


def logout(client):
    assert client.post('/api/auth/logout').status_code==200
    client.headers['X-CSRF-Token']=client.get('/api/auth/session').json()['data']['csrf_token']


@pytest.mark.parametrize('kind',['SCHOOL','COLLEGE'])
def test_workspaces_jobs_invitations_and_isolation(client,smtp,kind):
    first=register(client,smtp,kind,'first@institution.example')
    assert first['institution_type']==kind
    assert client.post('/api/product/seed').status_code==200
    catalog=client.get('/api/product/catalog').json()['data']
    faculty=catalog['faculty'][0]['id']; batch=catalog['batches'][0]['id']
    result=client.post('/api/product/jobs',json={'solver':'csp','time_limit_seconds':15})
    assert result.status_code in (200,202),result.text
    job=result.json()['data']['id']
    for _ in range(150):
        state=client.get('/api/product/jobs/'+job).json()['data']
        if state['state'] not in ('queued','running'): break
        time.sleep(.2)
    assert state['state']=='success',state
    saved=client.post('/api/product/jobs/'+job+'/save')
    assert saved.status_code==200,saved.text
    version=saved.json()['data']['id']
    revision=saved.json()['data']['revision']
    assert client.post('/api/product/versions/'+version+'/publish',json={'revision':revision}).status_code==200
    invitation=client.post('/api/auth/invitations',json={'email':'teacher@institution.example','role':'teacher','faculty_id':faculty})
    assert invitation.status_code==201,invitation.text
    link=token(smtp)
    invitation_id=invitation.json()['data']['id']
    logout(client)
    second=register(client,smtp,kind,'second@institution.example')
    assert first['institution_id']!=second['institution_id']
    assert client.get('/api/product/catalog').json()['data']['faculty']==[]
    assert client.get('/api/product/versions').json()['data']==[]
    for path in ('jobs/'+job,'versions/'+version,'versions/'+version+'/reports','versions/'+version+'/export/csv','versions/'+version+'/export/pdf'):
        assert client.get('/api/product/'+path).status_code==404,path
    assert client.delete('/api/auth/invitations/'+invitation_id).status_code==404
    assert client.put('/api/auth/users/'+first['id'],json={'role':'viewer','scopes':[],'active':False}).status_code==404
    assert client.post('/api/product/seed').status_code==200 # Identical IDs are valid in another institution.
    logout(client)
    accepted=client.post('/api/onboarding/accept-invitation',json={'token':link,'password':PASSWORD})
    assert accepted.status_code==200,accepted.text
    assert client.post('/api/onboarding/accept-invitation',json={'token':link,'password':PASSWORD}).status_code==400
    teacher=login(client,'teacher@institution.example')
    assert teacher['institution_id']==first['institution_id'] and teacher['role']=='teacher'
    assert client.get('/api/product/catalog').status_code==403
    assert client.post('/api/product/jobs',json={}).status_code==403
    assert client.get('/api/auth/users').status_code==403
    detail=client.get('/api/product/versions/'+version)
    assert detail.status_code==200,detail.text
    assert all(row['faculty']==faculty for row in detail.json()['data']['lectures'])
    assert client.get('/api/product/versions/'+version+'/reports').status_code==200
    assert client.get('/api/product/versions/'+version+'/export/pdf').status_code==200

    logout(client)
    login(client,'first@institution.example')
    student_invite=client.post('/api/auth/invitations',json={'email':'student@institution.example','role':'student','batch_ids':[batch]})
    assert student_invite.status_code==201,student_invite.text
    student_token=token(smtp)
    logout(client)
    assert client.post('/api/onboarding/accept-invitation',json={'token':student_token,'password':PASSWORD}).status_code==200
    student=login(client,'student@institution.example')
    assert student['institution_id']==first['institution_id']
    detail=client.get('/api/product/versions/'+version).json()['data']
    assert detail['lectures'] and all(row['batch']==batch for row in detail['lectures'])
    assert client.get('/api/product/versions/'+version+'/export/csv').status_code==200
    assert client.post('/api/auth/invitations',json={'email':'evil@institution.example','role':'planner'}).status_code==403


def test_invitation_rotation_expiration_and_role_injection(client,smtp,monkeypatch):
    from sqlalchemy import update
    from campusflow.product.catalog import transaction
    from campusflow.auth.tables import invitations
    register(client,smtp,'COLLEGE','admin@invitations.example')
    assert client.post('/api/auth/invitations',json={'email':'new@invitations.example','role':'administrator'}).status_code==422
    assert client.post('/api/auth/invitations',json={'email':'new@invitations.example','institution_id':'other'}).status_code==422
    response=client.post('/api/auth/invitations',json={'email':'new@invitations.example','role':'planner'})
    identifier=response.json()['data']['id'];old=token(smtp)
    assert client.post('/api/auth/invitations/'+identifier+'/resend').status_code==200
    fresh=token(smtp)
    assert old!=fresh
    logout(client)
    assert client.post('/api/onboarding/accept-invitation',json={'token':old,'password':PASSWORD}).status_code==400
    with transaction() as conn:
        conn.execute(update(invitations).where(invitations.c.id==identifier).values(expires_at=0))
    assert client.post('/api/onboarding/accept-invitation',json={'token':fresh,'password':PASSWORD}).status_code==400
    login(client,'admin@invitations.example')
    assert client.post('/api/auth/invitations/'+identifier+'/resend').status_code==200
    revoked=token(smtp)
    assert client.delete('/api/auth/invitations/'+identifier).status_code==200
    logout(client)
    assert client.post('/api/onboarding/accept-invitation',json={'token':revoked,'password':PASSWORD}).status_code==400


def test_platform_role_is_local_only_and_cannot_read_academics(client,smtp):
    from campusflow.product.catalog import transaction
    from campusflow.auth.service import create_user
    from campusflow.tenancy import LEGACY
    with transaction() as conn:
        operator=create_user(conn,'operator',PASSWORD,'platform_super_admin',[],must_change=False,tenant=LEGACY)
    login(client,'operator')
    assert client.get('/api/platform/institutions').status_code==200
    assert client.get('/api/product/catalog').status_code==403
    logout(client)
    register(client,smtp,'SCHOOL','school@operator.example')
    assert client.get('/api/platform/institutions').status_code==403
    assert client.post('/api/auth/users',json={'username':'evil','password':PASSWORD,'role':'platform_super_admin'}).status_code==422


def test_scoped_sql_aliases_nested_queries_and_composite_references(client,smtp):
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from campusflow.product import database as db
    from campusflow.product.catalog import transaction
    from campusflow.tenancy import institution,LEGACY
    first=register(client,smtp,'COLLEGE','boundary@institution.example')
    assert client.post('/api/product/seed').status_code==200
    with institution(LEGACY), db.connection() as conn:
        alias=db.faculty.alias('private_faculty')
        assert conn.execute(select(alias)).all()==[]
        with pytest.raises(TypeError,match='Nested'):
            conn.execute(select(select(db.faculty.c.id).limit(1).scalar_subquery()))
    with db.database().begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(db.assignments.insert().values(institution_id=LEGACY,faculty_id='F101',subject_id='CS201'))
    assert client.post('/api/product/records/rooms',json={'id':'injected','name':'Injected','capacity':30,'kind':'theory','institution_id':LEGACY}).status_code==422


def test_existing_account_invitation_requires_matching_authenticated_user(client,smtp):
    register(client,smtp,'SCHOOL','owner@link.example')
    invite=client.post('/api/auth/invitations',json={'email':'member@link.example','role':'planner'})
    assert invite.status_code==201
    link=token(smtp)
    logout(client)
    assert client.post('/api/onboarding/register',json={'name':'Member','email':'member@link.example','password':PASSWORD}).status_code==201
    assert client.post('/api/onboarding/accept-invitation',json={'token':link,'password':PASSWORD}).status_code==403
    user=login(client,'member@link.example');assert user['role']=='unassigned'
    assert client.post('/api/onboarding/accept-invitation',json={'token':link,'password':PASSWORD}).status_code==200
    client.headers['X-CSRF-Token']=client.get('/api/auth/session').json()['data']['csrf_token']
    assert client.get('/api/auth/session').json()['data']['user'] is None
    assert login(client,'member@link.example')['role']=='planner'
