"""Runner for Stage 3 & 4 capability and recovery browser verification."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from runtime_tools import find_node

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
VITE = ROOT / 'frontend/node_modules/vite/bin/vite.js'
API_PORT = 18060
WEB_PORT = 15173


def wait_port(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                return True
        time.sleep(0.2)
    return False


def main():
    NODE = find_node()
    print(f"Checking ports {API_PORT} and {WEB_PORT}...")
    for port in (API_PORT, WEB_PORT):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                print(f"Error: port {port} already in use", file=sys.stderr)
                sys.exit(1)

    env = os.environ.copy()
    env['GLUCOTWIN_LOCAL_REPLAY'] = '0'
    env['GLUCOTWIN_API_PORT'] = str(API_PORT)
    env['GLUCOTWIN_WEB_PORT'] = str(WEB_PORT)
    env['PYTHONPATH'] = str(ROOT / 'src')

    children = []
    try:
        print("Starting FastAPI backend...")
        backend = subprocess.Popen([PYTHON, str(ROOT / 'scripts/serve_stage6.py')], cwd=ROOT, env=env)
        children.append(backend)

        print("Starting Vite frontend...")
        frontend = subprocess.Popen([NODE, str(VITE), '--host', '127.0.0.1', '--port', str(WEB_PORT)], cwd=ROOT / 'frontend', env=env)
        children.append(frontend)

        print("Waiting for backend on port 18060...")
        if not wait_port(API_PORT, timeout=20):
            raise RuntimeError("Backend did not become ready on port 18060")

        print("Waiting for frontend on port 15173...")
        if not wait_port(WEB_PORT, timeout=20):
            raise RuntimeError("Frontend did not become ready on port 15173")

        print("Running verify_capability_recovery_browser.mjs...")
        test_proc = subprocess.run([NODE, str(ROOT / 'scripts/verify_capability_recovery_browser.mjs')], cwd=ROOT, env=env)
        if test_proc.returncode != 0:
            print(f"verify_capability_recovery_browser.mjs failed with code {test_proc.returncode}", file=sys.stderr)
            sys.exit(test_proc.returncode)
        print("Capability and recovery browser verification completed successfully!")

    finally:
        print("Stopping background services...")
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        print("Cleanup done.")


if __name__ == '__main__':
    main()

