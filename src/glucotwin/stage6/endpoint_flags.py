"""Exact +30-minute endpoint research flags, never episode/onset probabilities."""
import math
import numpy as np

THRESHOLDS=(180,250)

def issued_flags(value,reason):
    available=reason=='OK' and value is not None and math.isfinite(value)
    return tuple((threshold,bool(value>threshold) if available else None) for threshold in THRESHOLDS)

def views(forecast,score,cutoff):
    if score is not None and score.matured>cutoff:score=None
    result=[]
    for threshold,flag in forecast.endpoint_flags:
        target_state='PENDING' if score is None else 'MISSING' if score.observed is None or not math.isfinite(score.observed) else 'MATURED'
        label=None if target_state!='MATURED' else bool(score.observed>threshold)
        confusion=None if flag is None or label is None else 'TP' if flag and label else 'FP' if flag else 'FN' if label else 'TN'
        result.append(dict(kind='exact_endpoint_threshold',threshold_mg_dl=threshold,comparison='>',horizon_minutes=30,
                           flag=flag,flag_status='FORECAST_UNAVAILABLE' if flag is None else 'FLAG' if flag else 'NO_FLAG',
                           target_status=target_state,label=label,confusion=confusion,
                           status='FORECAST_UNAVAILABLE' if flag is None else 'TARGET_PENDING' if target_state=='PENDING' else 'TARGET_MISSING' if target_state=='MISSING' else 'SCORED'))
    return result

def ratio(n,d):return float(n/d) if d else None

def metrics(predictions,targets,reasons,threshold):
    pred=np.asarray(predictions,float);target=np.asarray(targets,float)
    issued=(np.asarray(reasons)=='OK')&np.isfinite(pred);observed=np.isfinite(target);scorable=issued&observed
    positive=pred>threshold;actual=target>threshold
    tp=int((scorable&positive&actual).sum());fp=int((scorable&positive&~actual).sum())
    tn=int((scorable&~positive&~actual).sum());fn=int((scorable&~positive&actual).sum())
    return dict(TP=tp,FP=fp,TN=tn,FN=fn,scheduled=len(pred),issued=int(issued.sum()),suppressed=int((~issued).sum()),
                scorable=int(scorable.sum()),missing_target=int((~observed).sum()),issued_missing_target=int((issued&~observed).sum()),
                observed_positive_targets=int((observed&actual).sum()),scorable_positive_targets=tp+fn,
                precision=ratio(tp,tp+fp),recall=ratio(tp,tp+fn),specificity=ratio(tn,tn+fp))
