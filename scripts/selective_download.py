"""HTTP-range ZIP access: download CSV/code/text members only, not food images."""
import urllib.request,io,zipfile,struct,zlib,hashlib,json,pathlib,datetime,concurrent.futures,time
ROOT=pathlib.Path(__file__).resolve().parents[1];BASE='https://physionet.org/files/cgmacros/1.0.0/';URL=BASE+'CGMacros_dateshifted365.zip';SIZE=657187340
OUT=ROOT/'data/raw';OUT.mkdir(parents=True,exist_ok=True)
def get(url,start=None,end=None):
 for attempt in range(3):
  try:
   req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'} if start is not None else {})
   with urllib.request.urlopen(req,timeout=60) as r:
    b=r.read()
    if start is not None:
     assert r.status==206 and r.headers['Content-Range'].startswith(f'bytes {start}-'),str(r.headers)
    return b
  except Exception:
   if attempt==2:raise
class Remote(io.RawIOBase):
 def __init__(self):self.pos=0;self.tail=get(URL,SIZE-655360,SIZE-1)
 def seekable(self):return True
 def seek(self,p,w=0):self.pos=p if w==0 else self.pos+p if w==1 else SIZE+p;return self.pos
 def tell(self):return self.pos
 def read(self,n=-1):
  n=SIZE-self.pos if n<0 else n
  p=self.pos;self.pos+=n
  return self.tail[p-(SIZE-len(self.tail)):p-(SIZE-len(self.tail))+n] if p>=SIZE-len(self.tail) else get(URL,p,p+n-1)
def main():
 z=zipfile.ZipFile(Remote());infos=z.infolist();(ROOT/'reports/stage1/archive_inventory.json').write_text(json.dumps([{'name':i.filename,'compressed_bytes':i.compress_size,'bytes':i.file_size,'crc32':i.CRC} for i in infos],indent=2))
 selected=[i for i in infos if i.filename.lower().endswith(('.csv','.ipynb','.txt','.md')) and '__MACOSX' not in i.filename]
 def fetch(i):
  rel=pathlib.PurePosixPath(i.filename);assert not rel.is_absolute() and '..' not in rel.parts
  p=OUT/'tables'/rel
  if p.exists():
   raw=p.read_bytes()
   if len(raw)==i.file_size and zlib.crc32(raw)==i.CRC:
    return {'path':str(p.relative_to(ROOT)),'archive_member':i.filename,'bytes':len(raw),'compressed_bytes':i.compress_size,'sha256':hashlib.sha256(raw).hexdigest(),'crc32_verified':True,'url':URL,'transformation':'Lossless range extraction; existing member reverified; images not extracted'}
  b=get(URL,i.header_offset,min(SIZE-1,i.header_offset+30+len(i.filename.encode())+65535+i.compress_size-1))
  h=struct.unpack('<4s5H3I2H',b[:30]);off=30+h[-2]+h[-1];c=b[off:off+i.compress_size]
  raw=zlib.decompress(c,-15) if i.compress_type==8 else c
  assert len(raw)==i.file_size and zlib.crc32(raw)==i.CRC,i.filename
  p=OUT/'tables'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  return {'path':str(p.relative_to(ROOT)),'archive_member':i.filename,'bytes':len(raw),'compressed_bytes':i.compress_size,'sha256':hashlib.sha256(raw).hexdigest(),'crc32_verified':True,'url':URL,'transformation':'Lossless range extraction; images not downloaded'}
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: members=list(ex.map(fetch,selected))
 downloads=[]
 for name in ['DataDictionary_Bio.csv','DataDictionary_CGMacros-00X.csv','DataDictionary_Gut_Health_Test.csv','DataDictionary_Microbes.csv','SHA256SUMS.txt','LICENSE.txt']:
  p=OUT/name;b=p.read_bytes() if p.exists() else get(BASE+name) if name=='LICENSE.txt' else get(BASE+name,0,999999);p.write_bytes(b);downloads.append({'path':str(p.relative_to(ROOT)),'url':BASE+name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
 expected={l.split()[1]:l.split()[0] for l in (OUT/'SHA256SUMS.txt').read_text().splitlines()}
 for x in downloads:
  name=pathlib.Path(x['path']).name
  if name in expected:assert x['sha256']==expected[name]
 provpath=ROOT/'reports/stage1/provenance_manifest.json'
 if not provpath.exists():
  result={'version':'1.0.0','accessed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive_url':URL,'archive_size_bytes':SIZE,'archive_sha256_published':expected['CGMacros_dateshifted365.zip'],'archive_sha256_verified':False,'verification_note':'Full archive not downloaded; selected members CRC32 verified and locally SHA256 hashed. Dictionary hashes match publisher.','extracted':members,'downloads':downloads}
  provpath.write_text(json.dumps(result,indent=2))
 print('Complete',len(members),'selected members',sum(x['bytes'] for x in members),'uncompressed bytes')
if __name__=='__main__':main()
