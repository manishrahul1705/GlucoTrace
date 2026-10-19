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
    p.add_argument('--fusion-bundle',type=Path)
    p.add_argument('--fusion-manifest-sha256')
    args=p.parse_args()
    if not 1024<=args.port<=65535:p.error('Unprivileged port required')
    print('Verifying pinned sensor bundle before serving',flush=True)
    verify(args.bundle,args.manifest_sha256)
    print('Pinned sensor bundle verification PASS',flush=True)
    if args.fusion_bundle:
        from glucotwin.experiment.fusion import verify as verify_fusion
        from glucotwin.experiment.common import load
        if not args.fusion_manifest_sha256:p.error('Fusion requires trusted manifest digest')
        print('Verifying pinned fusion bundle before serving',flush=True)
        result=verify_fusion(args.fusion_bundle,args.fusion_manifest_sha256)
        if load(args.fusion_bundle/'freeze.json')['parent_manifest_sha256']!=args.manifest_sha256:p.error('Fusion parent mismatch')
        print('Pinned fusion bundle verification PASS',flush=True)
    runtime=args.runtime.resolve();separate(runtime,args.bundle.resolve(),Path(__file__).resolve().parents[1])
    runtime.mkdir(parents=True)
    from glucotwin.stage6.api import create_app
    import uvicorn
    uvicorn.run(create_app(root=args.bundle.resolve()/'project',runtime=runtime,local_enabled=True,fusion_root=args.fusion_bundle),
                host='127.0.0.1',port=args.port,access_log=False)


if __name__=='__main__':main()
