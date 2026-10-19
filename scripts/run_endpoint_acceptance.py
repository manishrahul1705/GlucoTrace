"""Private endpoint HTTP acceptance; immutable bundles and isolated loopback services."""
import argparse,os,sys,subprocess,shutil,traceback,math
from pathlib import Path
sys.dont_write_bytecode=True
for n in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[n]='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
import pandas as pd
import numpy as np
from run_patient_replay_acceptance import free_port,wait_ready
from glucotwin.experiment.common import load,write,stamp,digest,source_files,hashes,separate
from glucotwin.experiment.acceptance import Records,HTTPAcceptance,source_mapping,minute

def check_flags(f,cutoff):
 assert len(f['endpoint_flags'])==2
 for x,threshold in zip(f['endpoint_flags'],(180,250)):
  assert x['threshold_mg_dl']==threshold and x['comparison']=='>' and x['horizon_minutes']==30
  flag=None if f['point_reason']!='OK' or f['value'] is None else f['value']>threshold
  assert x['flag'] is flag
  score=f['score']
  if score is None or score['matured_time']>cutoff:
   assert x['target_status']=='PENDING' and x['label'] is None and x['confusion'] is None
  elif score['observed'] is None:
   assert x['target_status']=='MISSING' and x['label'] is None and x['confusion'] is None
  else:
   actual=score['observed']>threshold
   assert x['target_status']=='MATURED' and x['label'] is actual
   wanted=None if flag is None else 'TP' if flag and actual else 'FP' if flag else 'FN' if actual else 'TN'
   assert x['confusion']==wanted

class EndpointAcceptance(HTTPAcceptance):
 def step(self,s):
  result=super().step(s)
  for forecast in result['forecasts']:check_flags(forecast,result['virtual_time'])
  return result

def participant(r,pid,source):
 s=None;result=dict(participant_id=pid,status='RUNNING',case='endpoint_exact_maturity')
 try:
  s=r.call('POST','/replay/sessions',json=dict(source_id=source,start='warm',scenario='clean'))
  expected=r.records.expected(pid,'clean');models=set(r.records.protocol['models'])
  # Warm starts precede supported evaluation origins: derive a finite target case from records.
  minimum=s['elapsed_minutes'];rows=expected.reset_index()
  valid=rows[(rows.minute>=minimum)&rows.point_reason.eq('OK')&np.isfinite(rows.target)]
  selected=int(valid.minute.min());target=selected+30;ids=None;baseline=None;pending_checks=0
  while s['elapsed_minutes']<=target:
   now=int(s['elapsed_minutes'])
   for f in s['forecasts']:check_flags(f,s['virtual_time'])
   if now==selected:
    chosen=[f for f in s['forecasts'] if minute(f['origin_time'],s['session_epoch'])==selected]
    assert {f['variant'] for f in chosen}==models
    for f in chosen:r.records.check_forecast(f,s['session_epoch'],expected);assert f['score'] is None
    ids={f['id'] for f in chosen};baseline=r.projection(s,selected)
   if ids and selected<now<target:
    assert all(f['score'] is None for f in s['forecasts'] if f['id'] in ids);pending_checks+=1
   if now==target:
    chosen=[f for f in s['forecasts'] if f['id'] in ids];assert len(chosen)==4
    for f in chosen:assert f['score'] and f['score']['matured_time']==f['target_time'];check_flags(f,s['virtual_time'])
    assert r.projection(s,selected)==baseline
    break
   s=r.step(s)
  assert pending_checks==5
  for kind in ('configuration','readings','forecasts','scores','summary'):
   response=r.client.post(f"/replay/sessions/{s['session_id']}/export",json=dict(generation=s['generation'],kind=kind))
   assert response.status_code==403 and response.json()['detail']=='PATIENT_EXPORT_DISABLED'
  response=r.client.post(f"/replay/sessions/{s['session_id']}/export",json=dict(generation=s['generation'],kind='endpoint_flags'));assert response.status_code==422
  response=r.client.post(f"/replay/library/{s['session_id']}/recreate",json={});assert response.status_code==409
  result.update(status='PASS',variants=sorted(models),selected_origin=selected,exact_maturity=target,pending_checks=pending_checks,historical_isolation=True,exports_rejected=5)
 except Exception:result.update(status='FAIL',error=traceback.format_exc())
 finally:
  if s:r.call('DELETE',f"/replay/sessions/{s['session_id']}")
 return result

def synthetic_checks(r):
 cases=[];catalog=r.call('GET','/replay/scenarios')['scenarios'];assert len(catalog)==9
 for case in catalog:
  sessions=[]
  try:
   config=dict(source_id='synthetic-dawn',scenario=case['id'],start='warm',seed=1705,duration_minutes=360)
   a=r.call('POST','/replay/sessions',json=config);sessions.append(a)
   b=r.call('POST','/replay/sessions',json=config);sessions.append(b)
   assert [(f['origin_time'],f['value'],f['endpoint_flags']) for f in a['forecasts']]==[(f['origin_time'],f['value'],f['endpoint_flags']) for f in b['forecasts']]
   for f in a['forecasts']:check_flags(f,a['virtual_time']);assert f['model_family']=='persistence'
   r.call('POST',f"/replay/library/{a['session_id']}/rename",json=dict(name='=2+2'))
   for kind in ('configuration','readings','forecasts','scores','summary'):
    response=r.client.post(f"/replay/sessions/{a['session_id']}/export",json=dict(generation=a['generation'],kind=kind));assert response.status_code==200
    if kind in ('readings','forecasts','scores'):assert "'=2+2" in response.text
   c=r.call('POST',f"/replay/library/{a['session_id']}/recreate",json={});sessions.append(c);assert c['configuration']==a['configuration']
   # Terminal accounting: no issue beyond data end; a further step cannot add an issue.
   while a['status']!='ended':a=r.step(a)
   count=a['forecast_count'];last=a['elapsed_minutes'];a=r.step(a);assert a['forecast_count']==count and a['elapsed_minutes']==last
   cases.append(dict(scenario=case['id'],status='PASS',deterministic=True,exports=5,terminal=True,library_recreate=True))
  except Exception:cases.append(dict(scenario=case['id'],status='FAIL',error=traceback.format_exc()))
  finally:
   for s in sessions:r.call('DELETE',f"/replay/sessions/{s['session_id']}")
 return cases

def supported_states(r,mapping):
 cases=[]
 pid=next(iter(mapping));source=mapping[pid];s=None
 try:
  s=r.call('POST','/replay/sessions',json=dict(source_id=source,start='full',scenario='clean'));s=r.step(s)
  assert s['forecasts'] and any(f['point_reason']!='OK' for f in s['forecasts'])
  for f in s['forecasts']:check_flags(f,s['virtual_time'])
  cases.append(dict(case='natural initial incomplete-history/offset unavailable',participant_id=pid,status='PASS'))
 finally:
  if s:r.call('DELETE',f"/replay/sessions/{s['session_id']}")
 # Actual missing target, selected only by frozen missingness, never by classification success.
 found=False
 for pid,source in mapping.items():
  _,anchor=r.records.participant(pid);warm=math.ceil((anchor+2880+60)/5)*5
  stream=pd.read_csv(r.records.project/f'data/processed/stage2/observations/p{pid:03d}.csv')
  rows=r.records.expected(pid,'clean').reset_index();missing=rows[(rows.minute>=warm)&(rows.minute+30<len(stream))&rows.point_reason.eq('OK')&~np.isfinite(rows.target)]
  if missing.empty:continue
  s=r.call('POST','/replay/sessions',json=dict(source_id=source,start='warm',scenario='clean'))
  try:
   selected=int(missing.minute.min());found=True
   while s['elapsed_minutes']<selected+30:s=r.step(s)
   chosen=[f for f in s['forecasts'] if minute(f['origin_time'],s['session_epoch'])==selected]
   assert len(chosen)==4
   for f in chosen:check_flags(f,s['virtual_time']);assert all(x['target_status']=='MISSING' and x['confusion'] is None for x in f['endpoint_flags'])
   cases.append(dict(case='actual missing exact target',participant_id=pid,selected_origin=selected,status='PASS'));break
  finally:r.call('DELETE',f"/replay/sessions/{s['session_id']}")
 if not found:cases.append(dict(case='actual missing exact target',status='UNAVAILABLE',reason='No future warm-replay missing target supported by frozen records; independently tested fixture'))
 return cases

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('bundle','fusion-bundle','output'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('manifest-sha256','fusion-trusted'):p.add_argument('--'+name,required=True)
 p.add_argument('--service-startup-timeout',type=int,default=1800,help='Wall-clock allowance for mandatory independent verification, not a performance SLO');p.add_argument('--browser',action='store_true');p.add_argument('--browser-only',action='store_true',help='Run genuine browser checks only; report HTTP as NOT_RUN_BROWSER_ONLY');a=p.parse_args();assert 600<=a.service_startup_timeout<=3600;out=a.output.resolve();separate(out,a.bundle.resolve(),a.fusion_bundle.resolve(),ROOT);out.mkdir(parents=True)
 revision=hashes(ROOT,source_files());write(out/'implementation.json',dict(recorded_at_utc=stamp(),source_sha256=revision,sensor_manifest=a.manifest_sha256,fusion_manifest=a.fusion_trusted,fits=0))
 result=dict(started_at=stamp(),status='RUNNING',http=[],synthetic=[],input_loss=[],supported_states=[],browser=None,fits=0,http_scope='NOT_RUN_BROWSER_ONLY' if a.browser_only else 'ALL_FROZEN_PARTICIPANTS');services=[];logs=[]
 try:
  port,webport=free_port(),free_port();api=f'http://127.0.0.1:{port}'
  log=(out/'server.log').open('w');logs.append(log)
  server=subprocess.Popen([sys.executable,'-B',str(ROOT/'scripts/serve_new_experiment.py'),'--bundle',str(a.bundle),'--manifest-sha256',a.manifest_sha256,'--fusion-bundle',str(a.fusion_bundle),'--fusion-manifest-sha256',a.fusion_trusted,'--runtime',str(out/'runtime'),'--port',str(port)],stdout=log,stderr=subprocess.STDOUT);services.append(server);wait_ready(api+'/api/health',server,seconds=a.service_startup_timeout)
  records=Records(a.bundle);fusion=pd.read_csv(a.fusion_bundle/'evaluation.csv',dtype={'alpha':str},float_precision='round_trip');records.evaluation=pd.concat([records.evaluation,fusion],ignore_index=True);records.protocol['models']+=['baseline_sensor_unadapted','baseline_sensor_offset24h']
  mapping=source_mapping(records,out/'runtime');r=EndpointAcceptance(api,records,out)
  discovered=r.call('GET','/replay/sources')['sources'];assert {s['id'] for s in discovered if s['mode']=='local' and s['available']}==set(mapping.values())
  for pid,source in ([] if a.browser_only else mapping.items()):
   case=participant(r,pid,source);result['http'].append(case);write(out/'acceptance.json',result);print('Endpoint HTTP',pid,case['status'],flush=True)
  pid=records.pids[0];result['input_loss']=[]
  for duration in ([] if a.browser_only else (15,30,60,120)):
   case=r.loss(pid,mapping[pid],duration);result['input_loss'].append(case);write(out/'acceptance.json',result);print('Endpoint strict loss',duration,case['status'],flush=True)
  if not a.browser_only:result['supported_states']=supported_states(r,mapping);result['synthetic']=synthetic_checks(r)
  r.client.close()
  write(out/'browser-input.json',dict(sources=[dict(participant_id=p,source_id=s) for p,s in mapping.items()],durations=[15,30,60,120]))
  if a.browser or a.browser_only:
   log=(out/'frontend.log').open('w');logs.append(log);env=dict(os.environ,GLUCOTWIN_API_PORT=str(port),GLUCOTWIN_WEB_PORT=str(webport))
   web=subprocess.Popen([shutil.which('node'),str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--configLoader','runner'],cwd=ROOT/'frontend',env=env,stdout=log,stderr=subprocess.STDOUT);services.append(web);wait_ready(f'http://127.0.0.1:{webport}',web,60)
   browser=subprocess.run([shutil.which('node'),str(ROOT/'scripts/verify_endpoint_browser.mjs'),'--url',f'http://127.0.0.1:{webport}','--input',str(out/'browser-input.json'),'--output',str(out)])
   result['browser']=load(out/'endpoint-browser.json');assert browser.returncode==0
  assert all(x['status']=='PASS' for x in result['http']+result['synthetic']+result['input_loss']);assert all(x['status'] in ('PASS','UNAVAILABLE') for x in result['supported_states']);assert hashes(ROOT,revision)==revision
  result['status']='PASS'
 except Exception:result.update(status='FAIL',error=traceback.format_exc())
 finally:
  for s in reversed(services):
   s.terminate()
   try:s.wait(timeout=10)
   except subprocess.TimeoutExpired:s.kill();s.wait()
  for log in logs:log.close()
  result['finished_at']=stamp();write(out/'acceptance.json',result)
 print('Endpoint acceptance',result['status']);return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
