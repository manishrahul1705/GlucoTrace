"""Loopback backend; no deployment, credentials or remote patient-data access."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
if __name__=='__main__':
    import uvicorn
    from glucotwin.stage6.api import create_app
    uvicorn.run(create_app(),host='127.0.0.1',port=18060,log_level='warning',access_log=False)
