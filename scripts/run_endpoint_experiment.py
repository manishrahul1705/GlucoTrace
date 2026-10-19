"""Private endpoint protocol freeze, zero-fit evaluation and independent verification."""
import os,sys,argparse
from pathlib import Path
for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[name]='1'
sys.dont_write_bytecode=True;sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from glucotwin.experiment import endpoints
from glucotwin.experiment.common import write

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','execute','verify']);p.add_argument('--bundle',type=Path);p.add_argument('--trusted',required=True);p.add_argument('--fusion-bundle',type=Path);p.add_argument('--fusion-trusted');p.add_argument('--freeze',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.mode=='freeze':print('ENDPOINT_FREEZE_SHA256',endpoints.freeze(a.bundle,a.trusted,a.fusion_bundle,a.fusion_trusted,a.output))
 elif a.mode=='execute':print('ENDPOINT_MANIFEST_SHA256',endpoints.execute(a.freeze,a.trusted,a.output))
 else:
  result=endpoints.verify(a.bundle,a.trusted)
  if a.output.exists():raise ValueError('Existing verification evidence refused')
  write(a.output,result);print(result)
if __name__=='__main__':main()
