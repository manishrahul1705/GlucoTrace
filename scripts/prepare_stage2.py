"""Execute deterministic Stage 2 preparation only. No predictions/model training."""
from pathlib import Path
import sys,json,hashlib,platform,importlib.metadata,dataclasses,os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import pandas as pd
import numpy as np
from glucotwin.contracts import baseline_contract,require_join,BASE_UNITS,ContractError
from glucotwin.preprocessing import prepare_observations,construct_origins
from glucotwin.features import paired_features,SENSOR_FEATURES,BASELINE_FEATURES
from glucotwin.labels import event_labels,future_any_crossing
from glucotwin.splits import make_splits,verify_splits,ids_hash
R=Path(__file__).resolve().parents[1];OUT=R/'reports/stage2';LOCAL=R/'data/processed/stage2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic_bytes(p,b):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.preparing');tmp.write_bytes(b);os.replace(tmp,p)
 if hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(b).digest():raise IOError('Artifact write integrity failure: '+str(p))
def dump(p,obj):atomic_bytes(p,(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n').encode())
def csv(p,df,index=False):
 text=df.to_csv(index=index,float_format='%.17g',date_format='%Y-%m-%dT%H:%M:%S',lineterminator='\n')
 atomic_bytes(p,text.encode())
def main():
 OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(parents=True,exist_ok=True);config=json.loads((R/'configs/stage2_protocol.json').read_text());provpath=R/config['dataset']['provenance_manifest']
 if sha(provpath)!=config['dataset']['provenance_sha256']:raise ContractError('Stage 1 provenance manifest changed')
 prov=json.loads(provpath.read_text());checks=[]
 for x in prov['extracted']+prov['downloads']:
  p=R/x['path'];actual=sha(p)
  if actual!=x['sha256']:raise ContractError('Input SHA mismatch: '+x['path'])
  checks.append({'path':x['path'],'sha256':actual,'passed':True})
 dump(OUT/'input_verification.json',{'version':prov['version'],'source':'PhysioNet only','provenance_sha256':sha(provpath),'checks':checks,'full_archive_sha_verified':prov['archive_sha256_verified']})
 # Snapshot immutable Stage 1 outputs before proceeding, without rewriting them.
 stage1={str(p.relative_to(R)):sha(p) for folder in ['docs/stage1','reports/stage1'] for p in sorted((R/folder).rglob('*')) if p.is_file()}
 dump(OUT/'stage1_preservation_manifest.json',stage1)
 bio_entry=next(x for x in prov['extracted'] if x['archive_member'].endswith('/bio.csv'));bio=pd.read_csv(R/bio_entry['path']);bases=baseline_contract(bio,config,bio_entry['path'],bio_entry['sha256'])
 entries=[x for x in prov['extracted'] if Path(x['path']).name.startswith('CGMacros-')];pid_entries={int(Path(x['path']).stem.split('-')[-1]):x for x in entries};require_join(list(pid_entries),bases)
 cohort_ids=sorted(p for p,b in bases.items() if b.cohort_group=='T2D' and p in pid_entries)
 if cohort_ids!=config['population']['expected_t2d_ids']:raise ContractError('Cohort differs from checkpoint; document amendment before final freeze')
 baseline_rows=[]
 for p in cohort_ids:
  b=dataclasses.asdict(bases[p]);b['units']=json.dumps(b['units'],sort_keys=True);baseline_rows.append(b)
 csv(LOCAL/'baseline_contract.csv',pd.DataFrame(baseline_rows))
 summary=[];exclusions=[];events=[];eps_summary=[];pers=[];sensor_tables=[];combined_tables=[];allorigins=[];members={};stage1w=pd.read_csv(R/'docs/stage1/usable_windows.csv');stage1e=pd.read_csv(R/'docs/stage1/event_feasibility.csv');origsets=[]
 for pid in cohort_ids:
  entry=pid_entries[pid];raw=pd.read_csv(R/entry['path']);d=prepare_observations(raw,pid,entry['path'],entry['sha256'],config['valid_glucose_mg_dl']);b=bases[pid]
  csv(LOCAL/f'observations/p{pid:03d}.csv',d,index=True)
  origins,masks=construct_origins(d,b);allorigins.append(origins.reset_index(drop=True));sf,cf=paired_features(d,origins,b);sensor_tables.append(sf);combined_tables.append(cf)
  members[pid]=sf.origin_id.tolist();origsets.append({'participant_id':pid,'origin_ids_sha256':ids_hash(members[pid]),'n_origins':len(sf)})
  # Sensor-only hypothetical coverage keeps baseline invalidity separate from paired coverage.
  sensor_eligible=np.ones(len(origins),dtype=bool)
  for reason,mask in masks.items():
   if reason!='baseline_missing_or_invalid':sensor_eligible&=~mask
  ref=stage1w[(stage1w.participant==pid)&(stage1w.sensor=='Dexcom GL')&(stage1w.history_minutes==60)&(stage1w.horizon_minutes==30)&(stage1w.max_missing_run_minutes==0)]
  previous=int(ref.eligible_origins.iloc[0]);one=int(origins.eligible.sum());sensorone=int(sensor_eligible.sum());primary=int((origins.eligible&origins.is_primary_grid).sum())
  if sensorone!=previous:raise ContractError(f'Stage1 discrepancy for {pid}: current {sensorone}, prior {previous}; explain before freeze')
  summary.append({'participant_id':pid,'cohort_group':'T2D','raw_rows':len(raw),'minute_grid_positions':len(d),'baseline_valid':b.baseline_valid,'sensor_eligible_1min':sensorone,'paired_eligible_1min':one,'stage1_eligible_1min':previous,'stage1_delta':sensorone-previous,'candidate_primary_5min':int(origins.is_primary_grid.sum()),'paired_primary_5min':primary,'sensor_eligible_primary_5min':int((sensor_eligible&origins.is_primary_grid.to_numpy()).sum()),'baseline_only_attrition_1min':sensorone-one,'baseline_only_attrition_5min':int((sensor_eligible&origins.is_primary_grid.to_numpy()).sum())-primary,'selected_for_lopo':primary>0,'causal_certification':False})
  for spacing,gridmask in [(1,np.ones(len(d),dtype=bool)),(5,origins.is_primary_grid.to_numpy())]:
   for reason,mask in masks.items():exclusions.append({'participant_id':pid,'issue_spacing_minutes':spacing,'reason':reason,'nonexclusive_count':int((gridmask&mask).sum()),'exclusive_first_reason_count':int((gridmask&origins.exclusion_reason.str.split(';').str[0].eq(reason).to_numpy()).sum())})
  # First 48 elapsed hours, never compressed to usable time.
  first=d.index[d.valid][0];boundary=first+pd.Timedelta(hours=48);calgrid=pd.date_range(first,boundary-pd.Timedelta(minutes=1),freq='min');calvalid=int(d.valid.reindex(calgrid,fill_value=False).sum());calmask=origins.eligible&origins.is_primary_grid&origins.history_start.ge(first)&origins.target_time.lt(boundary);evalmask=origins.eligible&origins.is_primary_grid&origins.history_start.ge(boundary);purge=origins.eligible&origins.is_primary_grid&~calmask&~evalmask
  pc={'participant_id':pid,'calibration_valid_minutes':calvalid,'calibration_expected_minutes':2880,'calibration_valid_coverage':calvalid/2880,'paired_calibration_origins_5min':int(calmask.sum()),'paired_later_origins_5min':int(evalmask.sum()),'purged_boundary_origins_5min':int(purge.sum()),'calibration_adequate':bool(calvalid/2880>=.8 and calmask.sum()>=100),'later_adequate':bool(evalmask.sum()>=100),'causal_certification':False}
  pc['protocol_eligible']=pc['calibration_adequate'] and pc['later_adequate'];pers.append(pc)
  personal=origins.loc[origins.eligible&origins.is_primary_grid,['origin_id','participant_id','issue_time','history_start','target_time']].copy();personal['first_valid_time']=first;personal['calibration_boundary']=boundary;personal['partition']=np.where(calmask.loc[personal.index],'calibration',np.where(evalmask.loc[personal.index],'later_evaluation','purged_boundary'));personal['event_max_information_end']=personal.issue_time+pd.Timedelta(minutes=44);personal['event_calibration_interval_safe']=personal.history_start.ge(first)&personal.event_max_information_end.lt(boundary);csv(LOCAL/f'personalization/p{pid:03d}.csv',personal.reset_index(drop=True))
  for threshold in config['event']['thresholds_mg_dl']:
   labels,episodes=event_labels(d,threshold);labels.insert(0,'origin_id',origins.origin_id);labels.insert(1,'participant_id',pid);csv(LOCAL/f'events/p{pid:03d}_gt{threshold}.csv',labels,index=True);csv(LOCAL/f'episodes/p{pid:03d}_gt{threshold}.csv',episodes)
   anycross=future_any_crossing(d,threshold);s1=stage1e[(stage1e.participant==pid)&(stage1e.sensor=='Dexcom GL')&(stage1e.threshold_mg_dl==threshold)&(stage1e.horizon_minutes==30)].iloc[0]
   if int(anycross.sum())!=int(s1.new_crossing_positive_origins):raise ContractError('Stage1 any-crossing reconciliation failed')
   if len(episodes)!=int(s1.independent_episodes_30min_recovery):raise ContractError('Stage1 episode reconciliation failed')
   eps_summary.append({'participant_id':pid,'threshold_mg_dl':threshold,'qualifying_episodes':len(episodes),'stage1_operational_episodes':int(s1.independent_episodes_30min_recovery),'delta':len(episodes)-int(s1.independent_episodes_30min_recovery)})
   for spacing,gridmask in [(1,np.ones(len(d),dtype=bool)),(5,origins.is_primary_grid.to_numpy())]:
    l=labels.loc[gridmask];at=l.origin_state.eq('eligible_at_risk');pairmask=origins.eligible.to_numpy()[gridmask]
    events.append({'participant_id':pid,'threshold_mg_dl':threshold,'issue_spacing_minutes':spacing,'candidate_origins':len(l),'stage1_any_crossing_positives':int(anycross.loc[gridmask].sum()),'sustained_at_risk_positive_origins':int(l.outcome.eq('positive').sum()),'stage1_any_crossing_on_at_risk_origins':int((anycross.loc[gridmask]&at).sum()),'sustained_positive_also_stage1_any_crossing':int((anycross.loc[gridmask]&l.outcome.eq('positive')).sum()),'known_sustained_positive_without_complete_stage1_30min_future':int((~anycross.loc[gridmask]&l.outcome.eq('positive')).sum()),'at_risk_negative_origins':int(l.outcome.eq('negative').sum()),'already_high_excluded_origins':int(l.origin_state.eq('currently_above').sum()),'incomplete_recovery_excluded_origins':int(l.origin_state.eq('below_insufficient_recovery').sum()),'invalid_current_excluded_origins':int(l.origin_state.eq('invalid_current').sum()),'at_risk_origins':int(at.sum()),'censored_at_risk_origins':int(l.outcome.eq('censored').sum()),'paired_regression_positive_origins':int((l.outcome.eq('positive').to_numpy()&pairmask).sum()),'paired_regression_censored_origins':int((l.outcome.eq('censored').to_numpy()&pairmask).sum()),'full_label_max_offset_minutes':44,'labels':'retrospective potentially interpolated release'})
  print(f'Prepared participant {pid}: paired 1min={one}, primary 5min={primary}',flush=True)
 sensor=pd.concat(sensor_tables,ignore_index=True);combined=pd.concat(combined_tables,ignore_index=True);oo=pd.concat(allorigins,ignore_index=True)
 if not sensor.origin_id.equals(combined.origin_id):raise ContractError('Unpaired feature variants')
 csv(LOCAL/'sensor_only.csv',sensor);csv(LOCAL/'sensor_plus_baseline.csv',combined);csv(LOCAL/'forecast_origins.csv',oo);csv(LOCAL/'origin_membership.csv',sensor[['origin_id','participant_id']])
 dump(LOCAL/'participant_origin_sets.json',origsets)
 eligible_members={p:ids for p,ids in members.items() if ids};split=make_splits(eligible_members);verify_splits(split,eligible_members);dump(OUT/'split_manifest.json',split)
 for name,rows in [('eligibility_summary.csv',summary),('exclusions.csv',exclusions),('event_definition_comparison.csv',events),('personalization_coverage.csv',pers),('episode_contribution.csv',eps_summary)]:csv(OUT/name,pd.DataFrame(rows))
 features=[]
 for i,name in enumerate(SENSOR_FEATURES):
  units='mg/dL/min' if 'slope' in name else 'mg/dL';features.append({'name':name,'order':i,'variant':'both','units':units,'endpoints':'lag exact or trailing inclusive [t-W,t]','std_ddof':0 if '_std_' in name else None,'availability':'retrospective event-time constraint only; upstream unknown','learned_transform':'none'})
 for i,name in enumerate(BASELINE_FEATURES,len(SENSOR_FEATURES)):features.append({'name':name,'order':i,'variant':'sensor_plus_baseline','units':BASE_UNITS[name],'endpoints':'screening baseline, not full-trace derived','std_ddof':None,'availability':'ASSUMPTION: baseline results known before evaluation; actual timestamp unknown','learned_transform':'none'})
 csv(R/'docs/stage2/feature_specification.csv',pd.DataFrame(features))
 versions={'python':platform.python_version(),'numpy':importlib.metadata.version('numpy'),'pandas':importlib.metadata.version('pandas')};dump(OUT/'environment.json',versions);(R/'requirements-stage2.txt').write_text(f"numpy=={versions['numpy']}\npandas=={versions['pandas']}\n")
 summary_all={'eligible_participants':sorted(eligible_members),'paired_origins_1min':int(sum(x['paired_eligible_1min'] for x in summary)),'paired_primary_origins_5min':len(sensor),'n_sensor_features':len(SENSOR_FEATURES),'n_combined_features':len(SENSOR_FEATURES)+len(BASELINE_FEATURES),'all_input_hashes_match':True,'models_trained':False,'predictions_calculated':False,'causal_certification':False,'task':config['task'],'baseline_unit_status':'operational percent per original paper; dictionary conflict retained','public_competition_release':'UNRESOLVED'}
 dump(OUT/'preparation_summary.json',summary_all)
 tracked=[R/'configs/stage2_protocol.json',R/'requirements-stage2.txt']+sorted((R/'src/glucotwin').glob('*.py'))+[Path(__file__),R/'scripts/verify_stage2.py',R/'scripts/package_stage2.py',R/'tests/stage2_fixture.py']+sorted((R/'tests').glob('test_stage2*.py'))+sorted(LOCAL.rglob('*.csv'))+sorted(LOCAL.rglob('*.json'))+[OUT/x for x in ['split_manifest.json','input_verification.json','eligibility_summary.csv','exclusions.csv','event_definition_comparison.csv','personalization_coverage.csv','episode_contribution.csv','preparation_summary.json']]+[R/'docs/stage2/feature_specification.csv']
 hashes={str(p.relative_to(R)):sha(p) for p in tracked if p.exists()}
 deterministic=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 dump(OUT/'freeze_manifest.json',{'protocol_version':config['protocol_version'],'checkpoint_type':config['freeze_type'],'deterministic_sha256':deterministic,'files':hashes,'excludes':'timestamps, logs, environment-specific paths, verification run outputs, narrative reports','source_provenance_sha256':sha(provpath),'stage1_preserved':all(sha(R/p)==h for p,h in stage1.items()),'causal_status':'NOT ESTABLISHED','public_competition_release':'UNRESOLVED','model_trained':False})
 print(json.dumps(summary_all,indent=2));print('Deterministic checkpoint:',deterministic)
if __name__=='__main__':main()
