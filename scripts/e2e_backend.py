"""Disposable browser-test backend with no SMTP or external email dependency."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import uvicorn
if __name__=='__main__':
    with TemporaryDirectory(prefix='campusflow-e2e-') as directory:
        os.environ['CAMPUSFLOW_DATABASE_URL']='sqlite:///'+(Path(directory)/'test.db').as_posix()
        os.environ['CAMPUSFLOW_ENV']='development'
        os.environ['CAMPUSFLOW_ONBOARDING_ENABLED']='1'
        from campusflow.product.database import migrate
        from campusflow.product.catalog import transaction
        from campusflow.auth.service import create_user
        migrate()
        with transaction() as conn:
            create_user(conn,'browser-admin','Browser test password 123!','administrator',must_change=False)
        uvicorn.run('campusflow.api.main:app',host='127.0.0.1',port=8001,log_level='warning')
