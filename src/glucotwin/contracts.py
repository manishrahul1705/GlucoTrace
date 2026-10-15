"""Strict contracts. Operational units are explicit; missing actual times stay missing."""
from dataclasses import dataclass,asdict
import json
import numpy as np
import pandas as pd
BASE_COLUMNS={'age':'Age','bmi':'BMI','hba1c':'A1c PDL (Lab)','fasting_glucose':'Fasting GLU - PDL (Lab)'}
BASE_UNITS={'age':'years','bmi':'kg/m^2','hba1c':'percent','fasting_glucose':'mg/dL'}
class ContractError(ValueError):pass
@dataclass(frozen=True)
class ParticipantBaseline:
 participant_id:int
 cohort_group:str
 age:float
 bmi:float
 hba1c:float
 fasting_glucose:float
 units:dict
 source_file:str
 source_row:int
 provenance_reference:str
 baseline_availability_status:str
 actual_available_at:object=None
 baseline_valid:bool=True
 exclusion_reason:str=''
@dataclass(frozen=True)
class ReleasedGlucoseObservation:
 participant_id:int
 sensor:str
 event_time:object
 glucose_mg_dl:float
 valid:bool
 source_file:str
 source_row:object
 provenance_reference:str
 processing_status:str='released_potentially_interpolated'
 actual_available_at:object=None
 native_observation_status:str='unknown'
@dataclass(frozen=True)
class ForecastOrigin:
 origin_id:str
 participant_id:int
 issue_time:object
 history_start:object
 target_time:object
 source_file:str
 provenance_reference:str
 eligible:bool
 exclusion_reason:str
 experiment_task:str='retrospective_released_signal_regression'
 causal_certification:bool=False

def baseline_contract(raw,config,source_file,provenance_reference):
 spec=config['baseline']
 if spec['columns']!=BASE_COLUMNS or spec['units']!=BASE_UNITS:raise ContractError('Selected columns/operational units differ from frozen contract')
 if not {'subject',*BASE_COLUMNS.values()}.issubset(raw):raise ContractError('Missing exact baseline source column')
 ids=pd.to_numeric(raw['subject'],errors='coerce')
 if ids.isna().any() or not np.isfinite(ids).all() or (ids%1!=0).any() or ids.duplicated().any():raise ContractError('Missing/noninteger/duplicate participant baseline key')
 result={}
 for rownum,(_,row) in enumerate(raw.iterrows(),1):
  values={k:pd.to_numeric(row[c],errors='coerce') for k,c in BASE_COLUMNS.items()};reasons=[]
  for k,v in values.items():
   lo,hi=spec['accepted_ranges'][k]
   if not np.isfinite(v):reasons.append(k+'_nonfinite')
   elif not lo<=v<=hi:reasons.append(k+'_outside_documented_range')
  h=values['hba1c'];group='unknown' if not np.isfinite(h) else 'healthy' if h<5.7 else 'prediabetes' if h<=6.4 else 'T2D'
  pid=int(row.subject);result[pid]=ParticipantBaseline(pid,group,**values,units=BASE_UNITS.copy(),source_file=source_file,source_row=rownum,provenance_reference=provenance_reference,baseline_availability_status=spec['availability_status'],baseline_valid=not reasons,exclusion_reason=';'.join(reasons))
 return result

def require_join(participant_ids,baselines):
 if len(participant_ids)!=len(set(participant_ids)):raise ContractError('Duplicate time-series participant key')
 missing=set(participant_ids)-set(baselines)
 if missing:raise ContractError(f'Missing baseline participant keys: {sorted(missing)}')

def access_history(observations,issue_time,history_minutes=60,mode='retrospective'):
 if mode not in ['retrospective','causal']:raise ContractError('Unknown access mode')
 issue=pd.Timestamp(issue_time);start=issue-pd.Timedelta(minutes=history_minutes)
 out=observations.loc[(observations.index>=start)&(observations.index<=issue)].copy()
 if mode=='causal':
  if 'actual_available_at' not in out:raise ContractError('Causal access: actual availability unknown')
  at=pd.to_datetime(out.actual_available_at,errors='coerce')
  if at.isna().any() or (at>issue).any():raise ContractError('Causal access: unknown or later availability')
  if 'availability_verified' not in out or not out.availability_verified.eq(True).all():raise ContractError('Causal access: availability not verified')
 return out
