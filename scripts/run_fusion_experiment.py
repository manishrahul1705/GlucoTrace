"""Freeze, execute or independently verify a separate private combined experiment."""
import argparse
import os
import sys
from pathlib import Path
for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[name]='1'
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from glucotwin.experiment.fusion import freeze,execute,verify
from glucotwin.experiment.common import write

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['freeze','execute','verify'])
    p.add_argument('--bundle',type=Path)
    p.add_argument('--trusted',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--freeze',type=Path)
    a=p.parse_args()
    if a.mode=='freeze':print('FREEZE_SHA256',freeze(a.bundle,a.trusted,a.output))
    elif a.mode=='execute':print(execute(a.freeze,a.trusted,a.output))
    else:
        result=verify(a.bundle,a.trusted)
        if a.output.exists():raise ValueError('Verification evidence already exists')
        write(a.output,result);print(result)
if __name__=='__main__':main()
