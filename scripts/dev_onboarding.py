"""Start the local password-authentication API; no SMTP service required."""
import argparse
import os
from pathlib import Path
import uvicorn

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--database',type=Path,default=Path('data/development-v5.db'))
    args=parser.parse_args()
    if os.getenv('CAMPUSFLOW_ENV','development')!='development':
        parser.error('This local launcher requires development mode')
    if not 1<=args.port<=65535: parser.error('Invalid port')
    path=args.database.resolve();path.parent.mkdir(parents=True,exist_ok=True)
    os.environ['CAMPUSFLOW_DATABASE_URL']='sqlite:///'+path.as_posix()
    os.environ.setdefault('CAMPUSFLOW_ONBOARDING_ENABLED','1')
    print('Local development database: '+str(path),flush=True)
    uvicorn.run('campusflow.api.main:app',host='127.0.0.1',port=args.port)

if __name__=='__main__': main()
