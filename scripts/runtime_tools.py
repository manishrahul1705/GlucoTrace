"""Runtime discovery shared by local launchers; no account-specific defaults."""
import os
from pathlib import Path
import shutil


def find_node():
    requested=os.environ.get('GLUCOTWIN_NODE','node')
    node=shutil.which(requested)
    if node is None:
        raise SystemExit('Node.js unavailable: add node to PATH or set GLUCOTWIN_NODE to its executable.')
    return node


def venv_python(directory):
    """Use the new environment's interpreter for python -m pip on each OS."""
    return Path(directory)/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
