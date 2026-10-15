"""Capture authoritative public sources without contacting anyone."""
from pathlib import Path
import urllib.request,datetime,json,hashlib,concurrent.futures
R=Path(__file__).resolve().parents[1];S=R/'sources';S.mkdir(exist_ok=True)
URLS={'physionet':'https://physionet.org/content/cgmacros/1.0.0/','license':'https://physionet.org/content/cgmacros/view-license/1.0.0/','paper':'https://www.nature.com/articles/s41597-025-05851-7','repo_tree':'https://api.github.com/repos/PSI-TAMU/CGMacros/git/trees/3d0c9b71647fe870b993e16f998e03a5ffc6381c?recursive=1','notebook':'https://raw.githubusercontent.com/PSI-TAMU/CGMacros/3d0c9b71647fe870b993e16f998e03a5ffc6381c/parse_data.ipynb','figshare':'https://api.figshare.com/v2/articles/29733005','challenge':'https://unstop.com/hackathons/crp-digital-twin-challenge-2026-happiest-health-1757873/amp'}
def f(kv):
 k,u=kv;x={'source':k,'url':u,'accessed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(u,timeout=45) as r:b=r.read();x['http_status']=r.status
  (S/(k+'.txt')).write_bytes(b);x.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),local_path='sources/'+k+'.txt')
 except Exception as e:x.update(status='BLOCKED',error=type(e).__name__+': '+str(e))
 return x
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as e:results=list(e.map(f,URLS.items()))
 (R/'reports/stage1/source_capture_manifest.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
