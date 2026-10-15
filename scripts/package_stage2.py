"""Review ZIP allowlist; local observations/origins/features/labels never packaged."""
from pathlib import Path
import hashlib,json,zipfile
REPORTS=['eligibility_summary.csv','exclusions.csv','event_definition_comparison.csv','personalization_coverage.csv','episode_contribution.csv','split_manifest.json','freeze_manifest.json','verification.json','execution_record.md','input_verification.json','stage1_preservation_manifest.json','environment.json','preparation_summary.json','reproducibility.json']
SCRIPTS=['prepare_stage2.py','verify_stage2.py','package_stage2.py','build_stage2_docs.py']
def review_files(root):
 files=[]
 for folder,pattern in [('docs/stage2','*'),('src/glucotwin','*.py'),('tests','test_stage2*.py')]:
  files.extend(p for p in (root/folder).rglob(pattern) if p.is_file() and '__pycache__' not in p.parts)
 files.extend(root/'reports/stage2'/n for n in REPORTS if (root/'reports/stage2'/n).is_file());files.extend(root/'scripts'/n for n in SCRIPTS if (root/'scripts'/n).is_file());files.extend(root/n for n in ['configs/stage2_protocol.json','requirements-stage2.txt','README-stage2.md','tests/stage2_fixture.py','.gitignore'] if (root/n).is_file())
 if any('data' in p.relative_to(root).parts or p.suffix in ['.pkl','.parquet','.npz'] for p in files):raise ValueError('Unexpected participant data in review allowlist')
 return sorted(set(files))
def main():
 r=Path(__file__).resolve().parents[1];out=r.parent/'GlucoTwin_Stage2_Review.zip';files=review_files(r);manifest={'raw_data_included':False,'participant_feature_tables_included':False,'participant_origin_or_observation_tables_included':False,'local_only_files_are_referenced_by_hash':True,'files':[{'path':str(p.relative_to(r)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in files]}
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for p in files:z.write(p,'GlucoTwin/'+str(p.relative_to(r)))
  z.writestr('GlucoTwin/reports/stage2/review_package_manifest.json',json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 with zipfile.ZipFile(out) as z:assert z.testzip() is None
 print(f'{out.name}: {len(files)+1} files, {out.stat().st_size} bytes; no raw/prepared participant tables')
if __name__=='__main__':main()
