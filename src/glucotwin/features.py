"""Shared trailing feature builder. No learned transforms or predictive model fitting."""
import numpy as np
import pandas as pd
from .contracts import access_history,ContractError
SENSOR_FEATURES=[f'glucose_lag_{m}m' for m in range(0,61,5)]+[f'glucose_{stat}_{m}m' for m in (15,30,60) for stat in ('mean','std')]+[f'glucose_slope_{m}m' for m in (15,30)]
BASELINE_FEATURES=['age','bmi','hba1c','fasting_glucose']
def slope_weights(minutes):
 x=np.arange(-minutes,1,dtype=float);x-=x.mean();return x/(x@x)
def build_sensor_features(observations):
 g=observations.glucose_mg_dl.where(observations.valid);f={}
 for m in range(0,61,5):f[f'glucose_lag_{m}m']=g.shift(m)
 for m in (15,30,60):
  r=g.rolling(m+1,min_periods=m+1);f[f'glucose_mean_{m}m']=r.mean();f[f'glucose_std_{m}m']=r.std(ddof=0)
 for m in (15,30):
  weights=slope_weights(m)
  f[f'glucose_slope_{m}m']=g.rolling(m+1,min_periods=m+1).apply(lambda a,w=weights:float(a@w),raw=True)
 return pd.DataFrame(f,index=g.index)[SENSOR_FEATURES]
def features_at(observations,issue_time,mode='retrospective'):
 h=access_history(observations,issue_time,60,mode)
 expected=pd.date_range(pd.Timestamp(issue_time)-pd.Timedelta(minutes=60),pd.Timestamp(issue_time),freq='min')
 if not h.index.equals(expected) or not h.valid.all():raise ContractError('Complete valid exact-minute history required')
 return build_sensor_features(h).iloc[-1]
def paired_features(observations,origins,baseline):
 eligible=origins.eligible&origins.is_primary_grid;f=build_sensor_features(observations).loc[eligible].copy()
 if not np.isfinite(f.to_numpy()).all():raise ContractError('Nonfinite prepared features')
 meta=origins.loc[eligible,['origin_id','participant_id','issue_time','history_start','target_time','target_mg_dl']].reset_index(drop=True)
 sensor=pd.concat([meta,f.reset_index(drop=True)],axis=1);combined=sensor.copy()
 for c in BASELINE_FEATURES:combined[c]=getattr(baseline,c)
 if not baseline.baseline_valid and len(combined):raise ContractError('Invalid baseline must exclude both variants')
 return sensor,combined

def persistence_formula(history):return float(np.asarray(history)[-1])
def trend_formula(history,horizon=30):
 a=np.asarray(history,dtype=float)
 if len(a)<16 or not np.isfinite(a[-16:]).all():raise ContractError('Trend requires 16 finite one-minute samples')
 return float(a[-1]+horizon*(a[-16:]@slope_weights(15)))
