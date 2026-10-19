"""Private NEW experiment CLI; defaults to hash-only preflight."""
import sys
import os
from pathlib import Path
for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
    os.environ[name]='1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from glucotwin.experiment.generate import main

if __name__ == '__main__':
    raise SystemExit(main())
