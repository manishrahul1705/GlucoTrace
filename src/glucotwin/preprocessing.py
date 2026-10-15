"""Lossless minute indexing and exact target eligibility; no value filling."""
import hashlib
import numpy as np
import pandas as pd
from .contracts import ContractError

def prepare_observations(raw,pid,source_file,provenance_reference,bounds=(40,400)):
 if not {'Timestamp','Dexcom GL'}.issubset(raw):raise ContractError('Missing exact Dexcom/Timestamp columns')
 tm=pd.to_datetime(raw.Timestamp,errors='coerce')
 if tm.isna().any():raise ContractError('Timestamp parse failure')
 if tm.duplicated().any():raise ContractError('Duplicate timestamp input rejected')
 if not tm.is_monotonic_increasing:raise ContractError('Non-monotonic timestamp input rejected')
 if not len(tm):raise ContractError('Empty observation input')
 if not ((tm-tm.iloc[0]).dt.total_seconds()%60).eq(0).all():raise ContractError('Off-minute-grid timestamp rejected')
 if tm.dt.tz is not None:raise ContractError('Unexpected timezone; do not silently convert shifted event times')
 y=pd.to_numeric(raw['Dexcom GL'],errors='coerce').to_numpy(dtype=float)
 d=pd.DataFrame({'participant_id':pid,'sensor':'Dexcom GL','glucose_mg_dl':y,'source_file':source_file,'source_row':np.arange(1,len(raw)+1),'provenance_reference':provenance_reference},index=pd.DatetimeIndex(tm,name='event_time'))
 grid=pd.date_range(tm.iloc[0],tm.iloc[-1],freq='min',name='event_time');d=d.reindex(grid)
 d['row_present']=d.source_row.notna();d['participant_id']=pid;d['sensor']='Dexcom GL';d['source_file']=source_file;d['provenance_reference']=provenance_reference
 d['valid']=np.isfinite(d.glucose_mg_dl)&d.glucose_mg_dl.between(*bounds);d['processing_status']='released_potentially_interpolated';d['actual_available_at']=pd.NaT;d['availability_verified']=False;d['native_observation_status']='unknown'
 return d

def origin_id(pid,t):return hashlib.sha256(f'stage2-v1|{pid}|Dexcom GL|{pd.Timestamp(t).isoformat()}|60|30'.encode()).hexdigest()[:24]

def construct_origins(d,baseline,history=60,horizon=30):
 n=len(d);idx=d.index;v=d.valid;full=v.astype(int).rolling(history+1,min_periods=history+1).sum().eq(history+1);target=v.shift(-horizon,fill_value=False)
 enough_past=np.arange(n)>=history;enough_future=np.arange(n)+horizon<n
 masks={'history_outside_recording':~enough_past,'history_missing_or_invalid':enough_past&~full.to_numpy(),'target_outside_recording':~enough_future,'target_missing_or_invalid':enough_future&~target.to_numpy(),'baseline_missing_or_invalid':np.full(n,not baseline.baseline_valid)}
 reasons=np.full(n,'',dtype=object)
 for reason,mask in masks.items():reasons[mask]=np.where(reasons[mask]=='',reason,reasons[mask]+';'+reason)
 pid=baseline.participant_id
 o=pd.DataFrame({'origin_id':[origin_id(pid,t) for t in idx],'participant_id':pid,'issue_time':idx,'history_start':idx-pd.Timedelta(minutes=history),'target_time':idx+pd.Timedelta(minutes=horizon),'source_file':d.source_file.iloc[0],'provenance_reference':d.provenance_reference.iloc[0],'eligible':reasons=='','exclusion_reason':reasons,'experiment_task':'retrospective_released_signal_regression','causal_certification':False,'is_primary_grid':np.arange(n)%5==0},index=idx)
 # Exact elapsed-time lookup on the preserved minute index; never nearest match.
 o['target_mg_dl']=d.glucose_mg_dl.shift(-horizon);return o,masks
