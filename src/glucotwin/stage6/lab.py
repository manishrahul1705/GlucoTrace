"""Read-only projections and cutoff-safe synthetic exports."""
import csv,io,json
from .prediction import timestamp

def forecast_view(session,f,cutoff):
    score=session.scores.get(f.id)
    if score and score.matured>cutoff:score=None
    return dict(id=f.id,seq=f.seq,variant=f.variant,phase=f.phase,origin_time=timestamp(f.origin),target_time=timestamp(f.target),
                value=f.value,point_reason=f.reason,history_start=timestamp(f.origin-60),history_end=timestamp(f.origin),history_count=f.history_count,
                artifact_identity=f.artifact_identity,intervals=[dict(alpha=a,lower=l,upper=u,reason=r) for a,l,u,r in f.intervals],
                score=None if not score else dict(observed=score.observed,signed_error=score.signed_error,reason=score.reason,matured_time=timestamp(score.matured),coverage=dict(score.coverage)))

def exploration(session,end,window):
    if not 0<=end<=session.minute or window not in [60,180,360]:raise ValueError('INVALID_REVEALED_RANGE')
    history=[]
    for minute in range(max(0,end-window),end+1):
        r=session.history.by_time.get(minute)
        history.append(dict(id=r.id if r else f'missing-{minute}',measurement_time=timestamp(minute),assumed_arrival_time=timestamp(minute),value=r.value if r and r.valid else None))
    forecasts=[forecast_view(session,f,end) for f in session.forecasts if max(0,end-window-30)<=f.origin<=end][-100:]
    return dict(virtual_time=timestamp(end),history=history,forecasts=forecasts)

def csv_safe(value):
    if isinstance(value,str) and value and (value[:1] in '=+-@\t\r\n' or (value.lstrip() and value.lstrip()[:1] in '=+-@')):
        return "'"+value
    return value

def export_session(session,kind,cutoff,display_name):
    if session.source.mode!='synthetic':raise PermissionError('PATIENT_EXPORT_DISABLED')
    if not 0<=cutoff<=session.minute:raise ValueError('INVALID_EXPORT_CUTOFF')
    config=session.source.configuration
    if config is None:raise ValueError('LEGACY_CONFIGURATION_UNAVAILABLE')
    metadata=dict(export_schema_version='glucotwin-synthetic-export-v1',synthetic_provenance=config['provenance'],
                  generator_version=config['generator_version'],seed=config['seed'],virtual_cutoff=timestamp(cutoff),units='mg/dL',predictor='persistence')
    if kind=='configuration':return json.dumps(dict(**metadata,configuration=config),indent=2), 'application/json'
    fs=[f for f in session.forecasts if f.origin<=cutoff]
    scores=[session.scores[f.id] for f in fs if f.id in session.scores and session.scores[f.id].matured<=cutoff]
    scored=[s for s in scores if s.reason=='OK'];issued=sum(f.value is not None for f in fs)
    if kind=='summary':
        summary=dict(scheduled=len(fs),issued=issued,interval_available=0,pending=sum(f.value is not None and (f.id not in session.scores or session.scores[f.id].matured>cutoff) for f in fs),
                     scored=len(scored),missing_targets=sum(s.reason=='TARGET_MISSING' and next(f for f in fs if f.id==s.forecast_id).value is not None for s in scores),
                     forecast_availability=issued/len(fs) if fs else None,scoring_availability=len(scored)/issued if issued else None,
                     mae=sum(abs(s.signed_error) for s in scored)/len(scored) if scored else None,
                     mean_signed_error=sum(s.signed_error for s in scored)/len(scored) if scored else None,empirical_coverage=None)
        return json.dumps(dict(**metadata,summary=summary),indent=2,allow_nan=False),'application/json'
    if kind=='readings':rows=[dict(measurement_time=timestamp(m),value=r.value if r.valid else None) for m,r in sorted(session.history.by_time.items()) if m<=cutoff]
    elif kind=='forecasts':
        rows=[]
        for f in fs:
            score=session.scores.get(f.id);score=score if score and score.matured<=cutoff else None
            rows.append(dict(forecast_id=f.id,origin_time=timestamp(f.origin),target_time=timestamp(f.target),variant=f.variant,point_forecast=f.value,point_reason=f.reason,interval_reason='SYNTHETIC_INTERVALS_UNCALIBRATED',observed_target=score.observed if score else None,score_status=score.reason if score else 'PENDING'))
    elif kind=='scores':rows=[dict(forecast_id=s.forecast_id,matured_time=timestamp(s.matured),observed_target=s.observed,signed_error=s.signed_error,reason=s.reason) for s in scores]
    else:raise ValueError('INVALID_EXPORT_KIND')
    # A metadata record is present even for an empty scored set.
    combined=[dict(**metadata,session_name=display_name,**row) for row in rows] or [dict(**metadata,session_name=display_name)]
    fields=list(dict.fromkeys(k for row in combined for k in row));output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=fields)
    writer.writeheader();writer.writerows({k:csv_safe(v) for k,v in row.items()} for row in combined)
    return output.getvalue(),'text/csv'

def library_item(store,row,active):
    id,generation,raw,expired,name,created,config,summary=row
    meta=json.loads(raw);configuration=json.loads(config) if config else None
    return dict(id=id,generation=generation,name=name or 'Legacy replay',created_at=created,status='expired' if expired or id not in active else active[id].status,
                mode=meta['mode'],configuration=configuration,recreatable=meta['mode']=='synthetic' and configuration is not None,
                summary=json.loads(summary) if summary else None)

LIBRARY_COLUMNS='id,generation,metadata,expired,display_name,created_at,configuration,summary'
