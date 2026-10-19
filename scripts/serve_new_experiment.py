"""Verify a trusted NEW bundle before serving private loopback replay. No fitting."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from glucotwin.experiment.verify import verify
from glucotwin.experiment.common import separate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--port',type=int,default=18060)
    args=p.parse_args()
    if not 1024<=args.port<=65535:p.error('Unprivileged port required')
    verify(args.bundle,args.manifest_sha256)
    runtime=args.runtime.resolve();separate(runtime,args.bundle.resolve(),Path(__file__).resolve().parents[1])
    runtime.mkdir(parents=True)
    from glucotwin.stage6.api import create_app
    import uvicorn
    uvicorn.run(create_app(root=args.bundle.resolve()/'project',runtime=runtime,local_enabled=True),
                host='127.0.0.1',port=args.port,access_log=False)


if __name__=='__main__':main()
