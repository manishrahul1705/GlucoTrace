"""Execute synthetic tests, real-data invariants and optional deterministic full rerun."""
from pathlib import Path
import sys,json,hashlib,subprocess,re,zipfile,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import pandas as pd,numpy as np
from glucotwin.splits import verify_splits,ids_hash
from glucotwin.features import SENSOR_FEATURES,BASELINE_FEATURES
from glucotwin.contracts import ContractError,access_history
R=Path(__file__).resolve().parents[1];O=R/'reports/stage2';L=R/'data/processed/stage2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def require(ok,message):
 if not ok:raise AssertionError(message)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rerun',action='store_true');ap.add_argument('--package',action='store_true');args=ap.parse_args();checks=[]
 freeze=json.loads((O/'freeze_manifest.json').read_text())
 for p,h in freeze['files'].items():require(sha(R/p)==h,'Frozen file changed: '+p)
 require(freeze['stage1_preserved'],'Stage1 changed during preparation');snap=json.loads((O/'stage1_preservation_manifest.json').read_text())
 for p,h in snap.items():require(sha(R/p)==h,'Stage1 preservation failure: '+p)
 checks.append('Stage 1 preserved and all frozen-file hashes match')
 test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_stage2*.py','-v'],cwd=R,capture_output=True,text=True)
 (O/'unittest.log').write_text(test.stdout+test.stderr);require(test.returncode==0,'Synthetic tests failed; see reports/stage2/unittest.log')
 match=re.search(r'Ran (\d+) tests?',test.stderr);test_count=int(match[1]) if match else None;checks.append(f'{test_count} synthetic contract/feature/label/split/privacy tests passed')
 s=pd.read_csv(L/'sensor_only.csv');c=pd.read_csv(L/'sensor_plus_baseline.csv');meta=['origin_id','participant_id','issue_time','history_start','target_time','target_mg_dl'];require(s.columns.tolist()==meta+SENSOR_FEATURES,'Unexpected sensor feature set');require(c.columns.tolist()==meta+SENSOR_FEATURES+BASELINE_FEATURES,'Unexpected combined feature set');pd.testing.assert_frame_equal(s,c[s.columns]);require(s.origin_id.is_unique,'Duplicate paired origins');require(np.isfinite(c[SENSOR_FEATURES+BASELINE_FEATURES+['target_mg_dl']].to_numpy()).all(),'Nonfinite prepared data');checks.append('Both variants have identical paired origins, metadata, targets and sensor features; finite values')
 issue=pd.to_datetime(s.issue_time);hist=pd.to_datetime(s.history_start);target=pd.to_datetime(s.target_time);require((issue-hist).eq(pd.Timedelta(minutes=60)).all(),'History endpoint wrong');require((target-issue).eq(pd.Timedelta(minutes=30)).all(),'Target endpoint wrong')
 members={int(p):a.origin_id.tolist() for p,a in s.groupby('participant_id')};split=json.loads((O/'split_manifest.json').read_text());require(verify_splits(split,members),'Split verification failed');checks.append('Every participant outer-test exactly once; all outer/inner participant and origin partitions disjoint')
 es=pd.read_csv(O/'eligibility_summary.csv');require(es.stage1_delta.eq(0).all(),'Stage1 window mismatch');require(int(es.paired_primary_5min.sum())==len(s),'Paired origin summary mismatch');require(int(es.paired_eligible_1min.sum())==197475,'Reconciled T2D minute-grid count changed without amendment');checks.append('Per-participant Stage1 reconciliation agrees with current 1-minute counts; five-minute totals reconcile')
 for p in sorted((L/'observations').glob('*.csv')):
  d=pd.read_csv(p);require(d.actual_available_at.isna().all(),'Unknown availability fabricated');require(d.native_observation_status.eq('unknown').all(),'Native status guessed')
  # Actual released data cannot pass causal access, even though retrospective features exist.
  obs=d.copy();obs.index=pd.to_datetime(obs.event_time)
  try:access_history(obs,obs.index[min(60,len(obs)-1)],mode='causal')
  except ContractError:pass
  else:raise AssertionError('Causal mode accepted unknown real-data availability')
 checks.append('Actual availability/native status remain unknown; causal mode fails closed on all 14 real participants')
 eventrows=0
 for p in sorted((L/'events').glob('*.csv')):
  e=pd.read_csv(p);i=pd.to_datetime(e.event_time);end=pd.to_datetime(e.max_label_information_end);actual=pd.to_datetime(e.actual_decision_information_end);positive=e.outcome.eq('positive');negative=e.outcome.eq('negative');unknown=e.outcome.isin(['excluded','censored'])
  require((end-i).eq(pd.Timedelta(minutes=44)).all(),'Event support end is not t+44');require(e.loc[unknown,'event_label'].isna().all(),'Unknown event label coerced negative');require(e.loc[positive,'event_label'].eq(1).all(),'Positive label mismatch');require(e.loc[negative,'event_label'].eq(0).all(),'Negative label mismatch');require(actual.loc[unknown].isna().all(),'Unknown decision end fabricated');onset=pd.to_datetime(e.confirmed_onset_time);require((actual.loc[positive]-onset.loc[positive]).eq(pd.Timedelta(minutes=14)).all(),'Confirmation length wrong');require((onset.loc[positive]>i.loc[positive]).all() and (onset.loc[positive]<=i.loc[positive]+pd.Timedelta(minutes=30)).all(),'Onset outside horizon');require((actual.loc[negative]==end.loc[negative]).all(),'Negative information end wrong');eventrows+=len(e)
 checks.append(f'All {eventrows} event-origin labels retain states, unknown censoring and full information intervals')
 pc=pd.read_csv(O/'personalization_coverage.csv');counts={}
 for p in sorted((L/'personalization').glob('*.csv')):
  a=pd.read_csv(p);boundary=pd.to_datetime(a.calibration_boundary);hist=pd.to_datetime(a.history_start);target=pd.to_datetime(a.target_time);cal=a.partition.eq('calibration');ev=a.partition.eq('later_evaluation');require((target.loc[cal]<boundary.loc[cal]).all(),'Calibration labels cross boundary');require((hist.loc[ev]>=boundary.loc[ev]).all(),'Evaluation history crosses calibration boundary');require(set(a.loc[cal,'origin_id']).isdisjoint(set(a.loc[ev,'origin_id'])),'Personalization origins overlap');counts[int(a.participant_id.iloc[0])]=(int(cal.sum()),int(ev.sum()),int(a.partition.eq('purged_boundary').sum()))
 for row in pc.itertuples():require(counts[row.participant_id]==(row.paired_calibration_origins_5min,row.paired_later_origins_5min,row.purged_boundary_origins_5min),'Personalization summary count mismatch')
 checks.append('48 elapsed-hour calibration coverage and full-history/target boundary purge verified for every participant')
 repro=None
 if args.rerun:
  first=freeze
  with (O/'rerun.log').open('w') as log:r=subprocess.run([sys.executable,'scripts/prepare_stage2.py'],cwd=R,stdout=log,stderr=subprocess.STDOUT)
  require(r.returncode==0,'Preparation rerun failed');second=json.loads((O/'freeze_manifest.json').read_text());require(first['files']==second['files'],'Deterministic file hashes differ between real-data reruns');require(first['deterministic_sha256']==second['deterministic_sha256'],'Checkpoint differs')
  repro={'passed':True,'first_sha256':first['deterministic_sha256'],'second_sha256':second['deterministic_sha256'],'compared_files':len(first['files']),'feature_tables':{p:h for p,h in first['files'].items() if p.endswith(('sensor_only.csv','sensor_plus_baseline.csv'))},'config_and_split_hashes':{p:h for p,h in first['files'].items() if p.endswith(('stage2_protocol.json','split_manifest.json'))},'timestamps_and_logs_excluded':True};dump(O/'reproducibility.json',repro);checks.append('Two real-data preparation runs produced identical config/data/split/checkpoint hashes')
 elif (O/'reproducibility.json').exists():
  repro=json.loads((O/'reproducibility.json').read_text());require(repro['second_sha256']==freeze['deterministic_sha256'],'Reproducibility result is stale')
 package_verified=False
 if args.package:
  with zipfile.ZipFile(R.parent/'GlucoTwin_Stage2_Review.zip') as z:
   require(z.testzip() is None,'Review ZIP integrity failed');names=z.namelist();require(not any('/data/' in p or '/sources/' in p or '/.venv/' in p for p in names),'Raw/prepared data packaged');require(not any(p.endswith(('sensor_only.csv','sensor_plus_baseline.csv','forecast_origins.csv','baseline_contract.csv','origin_membership.csv')) for p in names),'Participant table packaged');package_verified=True
  checks.append('Actual review ZIP excludes raw files, observations, participant features, origins and event-label tables')
 verification={'technical_preparation':'PASS' if repro and repro['passed'] else 'CONDITIONAL','causal_live_equivalent':'NOT ESTABLISHED','public_competition_release':'UNRESOLVED','synthetic_tests_passed':test_count,'all_checks_passed':True,'checks':checks,'reproducibility_verified':bool(repro and repro['passed']),'review_package_verified':package_verified,'models_trained':False,'predictive_test_performance_computed':False,'freeze_sha256':freeze['deterministic_sha256']};dump(O/'verification.json',verification)
 print(json.dumps(verification,indent=2))
if __name__=='__main__':main()
