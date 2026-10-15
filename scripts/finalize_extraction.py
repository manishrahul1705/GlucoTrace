"""Verify range-extracted CSV members against publisher ZIP central directory."""
from pathlib import Path
import json,zlib,hashlib,datetime
R=Path(__file__).resolve().parents[1];O=R/'reports/stage1';raw=R/'data/raw';inventory=json.loads((O/'archive_inventory.json').read_text());members=[]
for i in inventory:
 if i['name'].lower().endswith(('.csv','.ipynb','.txt','.md')) and '__MACOSX' not in i['name']:
  p=raw/'tables'/i['name'];b=p.read_bytes();assert len(b)==i['bytes'] and zlib.crc32(b)==i['crc32']
  members.append(dict(path=str(p.relative_to(R)),archive_member=i['name'],bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),crc32_verified=True,transformation='Lossless selective HTTP range extraction; no images extracted'))
expected={l.split()[1]:l.split()[0] for l in (raw/'SHA256SUMS.txt').read_text().splitlines()};downloads=[]
for name in ['DataDictionary_Bio.csv','DataDictionary_CGMacros-00X.csv','DataDictionary_Gut_Health_Test.csv','DataDictionary_Microbes.csv','SHA256SUMS.txt']:
 p=raw/name;b=p.read_bytes();sha=hashlib.sha256(b).hexdigest()
 if name in expected:assert sha==expected[name]
 downloads.append(dict(path=str(p.relative_to(R)),url='https://physionet.org/files/cgmacros/1.0.0/'+name,bytes=len(b),sha256=sha))
(O/'provenance_manifest.json').write_text(json.dumps(dict(version='1.0.0',accessed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),archive_url='https://physionet.org/files/cgmacros/1.0.0/CGMacros_dateshifted365.zip',archive_size_bytes=657187340,archive_sha256_published=expected['CGMacros_dateshifted365.zip'],archive_sha256_verified=False,verification_note='Selected members CRC32/size checked; local SHA256 recorded. Full archive hash not verified. Dictionaries match publisher SHA256. Partial full-download attempt is not an audit input.',extracted=members,downloads=downloads),indent=2));print('Verified',len(members),'CSV members')
