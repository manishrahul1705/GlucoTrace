"""Retrospective research event labels, never clinical alerts."""
import numpy as np
import pandas as pd

def forward_all(mask,count):
 return mask.astype(int).iloc[::-1].rolling(count,min_periods=count).sum().iloc[::-1].eq(count)
def future_any_crossing(d,threshold,horizon=30):
 v=d.valid;g=d.glucose_mg_dl.where(v)
 full=forward_all(v,horizon+1);future=g.shift(-1).iloc[::-1].rolling(horizon,min_periods=horizon).max().iloc[::-1]
 return v&g.le(threshold)&full&future.gt(threshold)
def event_labels(d,threshold,horizon=30,recovery=30,duration=15):
 idx=d.index;g=d.glucose_mg_dl;v=d.valid;below=v&g.le(threshold);above=v&g.gt(threshold)
 recovered=below.astype(int).rolling(recovery,min_periods=recovery).sum().eq(recovery)
 onset=recovered.shift(1,fill_value=False)&forward_all(above,duration)
 onset_idx=np.flatnonzero(onset.to_numpy());positions=np.arange(len(d));k=np.searchsorted(onset_idx,positions+1);next_onset=np.full(len(d),-1,dtype=int);has=k<len(onset_idx);next_onset[has]=onset_idx[k[has]]
 hit=(next_onset>positions)&(next_onset<=positions+horizon)
 maxend=idx+pd.Timedelta(minutes=horizon+duration-1)
 future_complete=forward_all(v.shift(-1,fill_value=False),horizon+duration-1)
 state=np.where(~v,'invalid_current',np.where(above,'currently_above',np.where(~recovered,'below_insufficient_recovery','eligible_at_risk')))
 at=state=='eligible_at_risk';outcome=np.where(~at,'excluded',np.where(hit,'positive',np.where(future_complete,'negative','censored')))
 label=pd.array([None]*len(d),dtype='Int64');label[outcome=='positive']=1;label[outcome=='negative']=0
 ends=pd.Series(maxend,index=idx);positive=outcome=='positive';ends.loc[positive]=idx[next_onset[positive]]+pd.Timedelta(minutes=duration-1)
 # earliest onset is stored only for a positive at-risk origin; excluded states have no outcome.
 times=pd.Series(pd.NaT,index=idx,dtype='datetime64[ns]');times.loc[positive]=idx[next_onset[positive]]
 rows=pd.DataFrame({'threshold_mg_dl':threshold,'origin_state':state,'outcome':outcome,'event_label':label,'confirmed_onset_time':times,'label_information_start':idx-pd.Timedelta(minutes=recovery-1),'actual_decision_information_end':ends,'max_label_information_end':maxend,'causal_certification':False},index=idx)
 rows.loc[(~at)|(outcome=='censored'),'actual_decision_information_end']=pd.NaT
 eps=pd.DataFrame({'onset_time':idx[onset.to_numpy()],'recovery_start':idx[onset.to_numpy()]-pd.Timedelta(minutes=recovery),'confirmation_end':idx[onset.to_numpy()]+pd.Timedelta(minutes=duration-1),'threshold_mg_dl':threshold})
 return rows,eps
