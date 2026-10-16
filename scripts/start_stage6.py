"""One-command local launcher. Ctrl+C stops only the two children it owns."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--local',action='store_true',help='Enable approved local processed-data sources (private)')
    parser.add_argument('--api-port',type=int,default=18060)
    parser.add_argument('--web-port',type=int,default=15173)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    vite=root/'frontend/node_modules/vite/bin/vite.js'
    node=shutil.which('node')
    if not vite.exists() or not node:raise SystemExit('Install frontend dependencies with npm.cmd ci --prefix frontend first.')
    if any(not 1024<=p<=65535 for p in (args.api_port,args.web_port)) or args.api_port==args.web_port:
        parser.error('Use two distinct unprivileged ports between 1024 and 65535.')
    for port in (args.api_port,args.web_port):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))==0:raise SystemExit(f'Loopback port {port} is in use. Stop your earlier GlucoTwin session first; no process was terminated.')
    env=os.environ.copy();env['GLUCOTWIN_LOCAL_REPLAY']='1' if args.local else '0'
    env['GLUCOTWIN_API_PORT']=str(args.api_port);env['GLUCOTWIN_WEB_PORT']=str(args.web_port)
    children=[]
    try:
        children.append(subprocess.Popen([sys.executable,str(root/'scripts/serve_stage6.py')],cwd=root,env=env))
        children.append(subprocess.Popen([node,str(vite),'--host','127.0.0.1'],cwd=root/'frontend',env=env))
        print(f'GlucoTwin: http://127.0.0.1:{args.web_port}/ | API: http://127.0.0.1:{args.api_port}/api/health',flush=True)
        print('Mode: '+('local processed replay + independent synthetic' if args.local else 'independent synthetic only')+'; Ctrl+C to stop.',flush=True)
        while all(p.poll() is None for p in children):time.sleep(.3)
    except KeyboardInterrupt:pass
    finally:
        for child in children:
            if child.poll() is None:child.terminate()
        for child in children:
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':main()
