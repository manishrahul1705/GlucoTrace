"""Independent NEW bundle checks. No generator, fitting, or historical CLI calls.

Model deserialization occurs only AFTER the caller-pinned manifest, complete file
coverage, source amendment and model-byte hashes have been checked.
"""
from pathlib import Path
from fractions import Fraction
import argparse
import hashlib
import json
import math
import numpy as np
import pandas as pd
import joblib
from .common import digest, load, write, relative, stamp

FEATURES = [f'glucose_lag_{m}m' for m in range(0,61,5)] + [
    f'glucose_{s}_{m}m' for m in (15,30,60) for s in ('mean','std')] + [f'glucose_slope_{m}m' for m in (15,30)]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, message, atol=1e-8):
    require(np.allclose(np.asarray(actual,float), np.asarray(expected,float), rtol=0,atol=atol,equal_nan=True), message)


def feature(history):
    """Scalar history arithmetic, independent of pandas rolling/core builders."""
    g = np.asarray(history,float)
    require(len(g)==61 and np.isfinite(g).all(), 'Feature support')
    values = [g[-1-m] for m in range(0,61,5)]
    for minutes in (15,30,60):
        w = g[-minutes-1:]
        mean = sum(w)/len(w)
        values.extend([mean, math.sqrt(sum((float(x)-mean)**2 for x in w)/len(w))])
    for minutes in (15,30):
        w = g[-minutes-1:]; x = np.arange(len(w),dtype=float); x -= sum(x)/len(x)
        values.append(float(sum(x*w)/sum(x*x)))
    return np.array(values)


def phase(issue, anchor, stage):
    h, t = issue-pd.Timedelta(minutes=60), issue+pd.Timedelta(minutes=30)
    b, c = anchor+pd.Timedelta(hours=24), anchor+pd.Timedelta(hours=48)
    if stage == 4:
        return 'calibration' if h>=anchor and t<c else 'later_evaluation' if h>=c else 'purged_boundary'
    return 'offset' if h>=anchor and t<b else 'calibration' if h>=b and t<c else 'evaluation' if h>=c else 'purged'


def median(values):
    v = sorted(map(float,values)); n = len(v)
    require(n>0 and all(math.isfinite(x) for x in v), 'Invalid median input')
    return v[n//2] if n%2 else (v[n//2-1]+v[n//2])/2


def quantile(scores, alpha, minimum=100):
    v = list(map(float,scores)); n=len(v)
    a=Fraction(str(alpha)); require(0<a<1, 'Invalid alpha')
    numerator=(n+1)*(a.denominator-a.numerator)
    k=(numerator+a.denominator-1)//a.denominator
    if any(not math.isfinite(x) or x<0 for x in v):
        return n,k,None,'INVALID_CALIBRATION_SCORES'
    if n<minimum or k>n:
        return n,k,None,'INSUFFICIENT_CALIBRATION'
    return n,k,sorted(v)[k-1],'OK'


def check_model(model,scaler,x,y,alpha):
    require(model.__class__.__name__=='Ridge' and scaler.__class__.__name__=='StandardScaler','Model types')
    require(model.alpha==alpha and model.fit_intercept and model.n_features_in_==21,'Frozen candidate')
    mu=x.mean(axis=0);var=((x-mu)**2).mean(axis=0)
    close(scaler.mean_,mu,'Training-only scaler mean')
    close(scaler.var_,var,'Training-only scaler variance')
    require(scaler.n_samples_seen_==len(x),'Scaler training sample count')
    # Match sklearn's documented near-constant handling using its error bound,
    # expressed independently rather than importing its private implementation.
    eps=np.finfo(float).eps
    constant=var <= len(x)*eps*var+(len(x)*mu*eps)**2
    scale=np.where(constant,1,np.sqrt(var));close(scaler.scale_,scale,'Scaler scale')
    z=(x-mu)/scale;zc=z-z.mean(axis=0);yc=y-y.mean()
    coef=np.linalg.solve(zc.T@zc+float(alpha)*np.eye(21),zc.T@yc)
    close(model.coef_,coef,'Selected Ridge normal-equation agreement',1e-5)
    close(model.intercept_,y.mean()-z.mean(axis=0)@coef,'Ridge intercept',1e-6)
    return lambda xx: ((np.asarray(xx)-mu)/scale)@model.coef_+model.intercept_


def counts(g, valid):
    """Convolution interval counts, independent of generator's slice loops."""
    g=np.asarray(g,float);valid=np.asarray(valid,bool);n=len(g)
    full=np.convolve(valid.astype(int),np.ones(61,dtype=int),'valid') if n>=61 else np.array([])
    windows=int(sum(full[t-60]==61 and valid[t+30] for t in range(60,n-30)))
    events={}
    for threshold in (180,250):
        low=valid&(g<=threshold);high=valid&(g>threshold)
        cross=0;episodes=0
        if n>=31:
            good=np.convolve(valid.astype(int),np.ones(31,dtype=int),'valid')==31
            future=np.convolve(high.astype(int),np.ones(30,dtype=int),'valid')[1:]
            cross=int((good&low[:n-30]&(future>0)).sum())
        if n>=45:
            recovery=np.convolve(low.astype(int),np.ones(30,dtype=int),'valid')
            confirmation=np.convolve(high.astype(int),np.ones(15,dtype=int),'valid')
            episodes=int(sum(recovery[s-30]==30 and confirmation[s]==15 for s in range(30,n-14)))
        events[threshold]=(cross,episodes)
    return windows,events


def check_hashes(bundle, expected_digest, allow_synthetic=False):
    manifest_path=bundle/'artifact-manifest.json'
    require(digest(manifest_path)==expected_digest,'Caller-pinned manifest mismatch')
    manifest=load(manifest_path)
    require(manifest['kind']=='NEW_EXPERIMENT','Wrong bundle type')
    require(allow_synthetic or not manifest['synthetic_fixture'],'Synthetic fixture is not a patient bundle')
    require(manifest['fits']==14,'Fit count mismatch')
    project=bundle/'project'
    actual={p.relative_to(project).as_posix() for p in project.rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    require(actual==set(manifest['files']),'Artifact manifest coverage mismatch')
    for name,h in manifest['files'].items():
        require(digest(relative(project,name))==h,'Artifact hash mismatch: '+name)
    amendment=load(bundle/'amendment.json')
    require(digest(bundle/'amendment.json')==manifest['amendment_sha256'],'Amendment mismatch')
    # Stage2 intentionally writes these two source-document/environment outputs.
    generated={'requirements-stage2.txt','docs/stage2/feature_specification.csv'}
    for name,h in amendment['source_sha256'].items():
        if name not in generated:
            require(digest(relative(project,name))==h,'Frozen implementation changed: '+name)
    plan=amendment['plan']
    for name,h in plan['input_hashes'].items():
        require(digest(relative(project,name))==h,'Frozen acquired input mismatch')
    for name,h in plan['metadata_hashes'].items():
        if name!='reports/stage2/split_manifest.json':
            require(digest(relative(project,name))==h,'Frozen selection/provenance mismatch')
    require(digest(project/'reports/new_experiment/frozen_split.json')==plan['metadata_hashes']['reports/stage2/split_manifest.json'],
            'Frozen split provenance mismatch')
    require(load(project/'reports/stage2/split_manifest.json')==load(project/'reports/new_experiment/frozen_split.json'),
            'Prepared split mismatch')
    return project,manifest,amendment


def verify(bundle, expected_digest, allow_synthetic=False):
    bundle=Path(bundle).resolve()
    project,manifest,amendment=check_hashes(bundle,expected_digest,allow_synthetic)
    features=pd.read_csv(project/'data/processed/stage2/sensor_only.csv',float_precision='round_trip')
    require(features.origin_id.is_unique,'Duplicate reference origins')
    split=load(project/'reports/new_experiment/frozen_split.json')
    pids=split['eligible_participants']
    require(len(pids)==14 and len(set(pids))==14 and len(split['folds'])==14,'Fourteen folds required')
    require(set(features.participant_id)==set(pids),'Cohort mismatch')
    local=project/'data/processed/stage5'
    require({p.name for p in local.glob('model_*.joblib')}=={f'model_{p:03d}.joblib' for p in pids},'Model set mismatch')
    replay_inputs=load(local/'input_hashes.json')
    replay_names=['reports/stage2/split_manifest.json','configs/stage5_protocol.json']+[
        f'data/processed/stage2/observations/p{p:03d}.csv' for p in pids]
    require(set(replay_inputs)==set(replay_names),'Replay input manifest coverage')
    for name in replay_names:require(digest(relative(project,name))==replay_inputs[name],'Replay input hash')
    protocol_freeze=load(project/'reports/stage5/protocol_freeze.json')
    require(protocol_freeze['protocol_sha256']==digest(project/'configs/stage5_protocol.json')
            and protocol_freeze['implementation_amendment_sha256']==manifest['amendment_sha256'],'Replay protocol freeze')
    refs=pd.read_csv(local/'partition_predictions.csv',float_precision='round_trip')
    s4=pd.read_csv(project/'data/processed/new_stage4/references.csv',float_precision='round_trip')
    evaluations=pd.read_csv(local/'evaluation.csv',dtype={'alpha':str},float_precision='round_trip')
    cal=load(local/'calibration_artifacts.json')
    info4=load(project/'data/processed/new_stage4/offsets.json')
    reproduce=load(local/'model_reproduction.json')
    adequacy=pd.read_csv(local/'partition_adequacy.csv')
    auditw=pd.read_csv(project/'docs/stage1/usable_windows.csv')
    audite=pd.read_csv(project/'docs/stage1/event_feasibility.csv')
    metrics4=pd.read_csv(project/'reports/new_experiment/stage4_per_participant.csv',float_precision='round_trip')
    require(len(cal)==56 and len(reproduce)==14 and len(info4)==14 and len(adequacy)==14,'Metadata coverage')
    require(set(refs.origin_id)==set(features.origin_id) and refs.origin_id.is_unique,'Reference coverage')
    require(set(s4.origin_id)==set(features.origin_id) and s4.origin_id.is_unique,'Stage4 coverage')
    selected=amendment['plan']['selected']
    require(len(selected)==14,'Frozen selections')
    metrics=[]
    for fold in split['folds']:
        pid=fold['test']['participants'][0];train_ids=fold['train']['participants']
        require(set(train_ids)==set(pids)-{pid} and len(train_ids)==13,'Outer exclusion')
        require(len(fold['inner_folds'])==3,'Inner fold count')
        for inner in fold['inner_folds']:
            a=set(inner['train']['participants']);b=set(inner['validation']['participants'])
            require(not a&b and a|b==set(train_ids) and pid not in a|b,'Inner exclusion')
        chosen=[r for r in selected if r['outer_fold']==fold['outer_fold'] and int(r['held_out_pid'])==pid]
        require(len(chosen)==1,'Selected fold mismatch')
        alpha=json.loads(chosen[0]['selected_candidate_spec'])['alpha']
        train=features[features.participant_id.isin(train_ids)]
        test=features[features.participant_id==pid]
        require(len(train)==fold['train']['n_origins'] and len(test)==fold['test']['n_origins'],'Origin membership count')
        model,scaler=joblib.load(local/f'model_{pid:03d}.joblib')
        x=train[FEATURES].to_numpy();y=train.target_mg_dl.to_numpy()
        prediction=check_model(model,scaler,x,y,alpha)
        record=[r for r in reproduce if r['participant_id']==pid]
        require(len(record)==1 and record[0]['fit_count']==1 and record[0]['train_participants']==train_ids
                and record[0]['feature_order']==FEATURES,'Training provenance')
        train_hash=hashlib.sha256('\n'.join(map(str,train.origin_id)).encode()).hexdigest()
        require(record[0]['training_origin_sha256']==train_hash,'Training membership hash')
        rows=refs[refs.participant_id==pid].set_index('origin_id').loc[test.origin_id].reset_index()
        close(rows.base_prediction,prediction(test[FEATURES]),'Held-out predictions')
        close(rows[FEATURES],test[FEATURES],'Reference feature copy')
        close(rows.target_mg_dl,test.target_mg_dl,'Reference exact targets')
        for column in ('issue_time','history_start','target_time'):
            require(list(pd.to_datetime(rows[column]))==list(pd.to_datetime(test[column])),'Reference support copy')
        stream=pd.read_csv(project/f'data/processed/stage2/observations/p{pid:03d}.csv',parse_dates=['event_time'],float_precision='round_trip').set_index('event_time')
        require(stream.index.tz is None and stream.index.equals(pd.date_range(stream.index[0],periods=len(stream),freq='min')),'Elapsed minute grid')
        g=stream.glucose_mg_dl.to_numpy(float)
        valid=stream.valid.to_numpy(bool)
        require(np.array_equal(valid,np.isfinite(g)&(g>=40)&(g<=400)),'Glucose validity')
        # Compare prepared observations to original verified raw bytes, with no fill.
        prov=load(project/'reports/stage1/provenance_manifest.json')
        entry=next(e for e in prov['extracted'] if Path(e['path']).name==f'CGMacros-{pid:03d}.csv')
        raw=pd.read_csv(project/entry['path']);tm=pd.DatetimeIndex(pd.to_datetime(raw.Timestamp))
        require(not tm.has_duplicates and tm.is_monotonic_increasing,'Raw timestamps')
        rawseries=pd.Series(pd.to_numeric(raw['Dexcom GL'],errors='coerce').to_numpy(),index=tm).reindex(stream.index)
        close(g,rawseries,'Observation/raw agreement')
        anchor=stream.index[np.flatnonzero(valid)[0]]
        win,events=counts(g,valid)
        w=auditw[auditw.participant==pid]
        require(len(w)==1 and int(w.eligible_origins.iloc[0])==win,'New window reconciliation')
        for threshold,(cross,episodes) in events.items():
            e=audite[(audite.participant==pid)&(audite.threshold_mg_dl==threshold)]
            require(len(e)==1 and int(e.new_crossing_positive_origins.iloc[0])==cross
                    and int(e.independent_episodes_30min_recovery.iloc[0])==episodes,'New event reconciliation')
        expected_positions=[t for t in range(60,len(g)-30) if t%5==0 and valid[t-60:t+1].all() and valid[t+30]]
        require(list(pd.to_datetime(test.issue_time))==list(stream.index[expected_positions]),'Eligibility/grid membership')
        for row,t in zip(test.itertuples(),expected_positions):
            close([getattr(row,n) for n in FEATURES],feature(g[t-60:t+1]),'Independent trailing features')
            close(row.target_mg_dl,g[t+30],'Exact target')
            require(pd.Timestamp(row.history_start)==stream.index[t]-pd.Timedelta(minutes=60)
                    and pd.Timestamp(row.target_time)==stream.index[t+30],'Origin support')
        expected_phase=[phase(pd.Timestamp(i),anchor,5) for i in rows.issue_time]
        require(list(rows.partition)==expected_phase,'Stage5 chronological purges')
        offrows=rows[rows.partition=='offset'];calrows=rows[rows.partition=='calibration'];later=rows[rows.partition=='evaluation']
        off=median(offrows.target_mg_dl-offrows.base_prediction) if len(offrows)>=100 else None
        a=adequacy[adequacy.participant_id==pid].iloc[0]
        require(pd.Timestamp(a.anchor)==anchor and a.n_offset==len(offrows) and a.n_calibration==len(calrows)
                and a.n_evaluation==len(later) and a.n_purged==expected_phase.count('purged'),'Adequacy counts')
        four=s4[s4.participant_id==pid].set_index('origin_id').loc[test.origin_id].reset_index()
        require(list(four.partition)==[phase(pd.Timestamp(i),anchor,4) for i in four.issue_time],'Stage4 chronological purges')
        close(four.base_prediction,rows.base_prediction,'Stage4 model reuse')
        close(four.target_mg_dl,test.target_mg_dl,'Stage4 exact targets')
        for column in ('issue_time','history_start','target_time'):
            require(list(pd.to_datetime(four[column]))==list(pd.to_datetime(test[column])),'Stage4 support copy')
        cal4=four[four.partition=='calibration'];later4=four[four.partition=='later_evaluation']
        coverage=sum(bool(valid[i]) for i in range(len(g)) if anchor<=stream.index[i]<anchor+pd.Timedelta(hours=48))/2880
        ready4=coverage>=.8 and len(cal4)>=100 and len(later4)>=100
        offset4=median(cal4.target_mg_dl-cal4.base_prediction) if ready4 else None
        info=next(i for i in info4 if i['participant_id']==pid)
        require(info['ready']==ready4,'Stage4 adequacy');close(info['coverage'],coverage,'Stage4 coverage')
        close(info['offset'] if info['offset'] is not None else np.nan,offset4 if offset4 is not None else np.nan,'Stage4 offset')
        close(four.adapted_prediction,four.base_prediction+offset4 if offset4 is not None else np.full(len(four),np.nan),'Stage4 adaptation')
        m4=metrics4[metrics4.participant_id==pid]
        require(len(m4)==1 and m4.n_later.iloc[0]==len(later4),'Stage4 metric denominator')
        close(m4.unadapted_mae.iloc[0],sum(abs(later4.target_mg_dl-later4.base_prediction))/len(later4),'Stage4 MAE')
        close(m4.adapted_mae.iloc[0],sum(abs(later4.target_mg_dl-later4.base_prediction-offset4))/len(later4)
              if offset4 is not None else np.nan,'Stage4 adapted MAE')
        for variant in ('sensor_only_unadapted','sensor_only_offset24h'):
            offset=0 if variant.endswith('unadapted') else off
            for alpha in ('0.10','0.05'):
                artifacts=[c for c in cal if c['participant_id']==pid and c['variant']==variant and c['alpha']==alpha]
                require(len(artifacts)==1,'Calibration key coverage');c=artifacts[0]
                n,k,q,reason=quantile(abs(calrows.target_mg_dl-(calrows.base_prediction+(offset or 0))),alpha)
                if offset is None:q,reason=None,'INSUFFICIENT_OFFSET_DATA'
                require((c['n'],c['k'],c['reason'],c['offset'])==(n,k,reason,offset),'Calibration rank/reason/offset')
                close(c['q'] if c['q'] is not None else np.nan,q if q is not None else np.nan,'Calibration quantile')
                groups=evaluations[(evaluations.participant_id==pid)&(evaluations.variant==variant)&(evaluations.alpha==alpha)]
                require(set(groups.scenario)=={'clean','input_loss_15m','input_loss_30m','input_loss_60m','input_loss_120m'},'Scenario coverage')
                scheduled=[t for t in range(0,len(g),5) if stream.index[t]-pd.Timedelta(minutes=60)>=anchor+pd.Timedelta(hours=48)]
                start=next(t for t in range(0,len(g),5) if stream.index[t]>=anchor+pd.Timedelta(hours=72))
                prediction_cache={t:float(prediction(feature(g[t-60:t+1]))) for t in scheduled
                                  if valid[t-60:t+1].all()}
                for scenario,group in groups.groupby('scenario'):
                    require(list(pd.to_datetime(group.issue_time))==list(stream.index[scheduled]),'Schedule coverage/order')
                    duration=0 if scenario=='clean' else int(scenario.split('_')[-1][:-1])
                    changed_valid=valid.copy()
                    if duration:changed_valid[start:start+duration]=False
                    last_valid=np.maximum.accumulate(np.where(changed_valid,np.arange(len(g)),-1))
                    for row,t in zip(group.itertuples(),scheduled):
                        history_valid=valid[t-60:t+1].copy()
                        if duration:
                            positions=np.arange(t-60,t+1);history_valid &= ~((positions>=start)&(positions<start+duration))
                        current=valid[t] and not(duration and start<=t<start+duration)
                        history_ok=history_valid.all()
                        ok=current and history_ok and offset is not None
                        if not current:
                            codes=['MISSING_CURRENT_READING']
                            injected=bool(duration and start<=t<start+duration)
                            present=bool(stream.row_present.iloc[t]) if pd.notna(stream.row_present.iloc[t]) else False
                            if not injected and present and not math.isfinite(g[t]):codes.append('NON_FINITE_READING')
                            if not injected and math.isfinite(g[t]) and not 40<=g[t]<=400:codes.append('SOURCE_INVALID_READING')
                            if last_valid[t]>=0 and t-last_valid[t]>10:codes.append('STALE_READING')
                            point_reason=';'.join(codes)
                        elif not history_ok:point_reason='INCOMPLETE_HISTORY'
                        elif offset is None:point_reason='INSUFFICIENT_OFFSET_DATA'
                        else:point_reason='OK'
                        require(row.point_reason==point_reason,'Missingness point gate/reason')
                        yp=prediction_cache[t]+offset if ok else np.nan
                        yt=g[t+30] if t+30<len(g) and valid[t+30] else np.nan
                        close(row.prediction,yp,'Scheduled prediction/model reuse');close(row.target,yt,'Exact target scoring')
                        require(pd.Timestamp(row.target_time)==stream.index[t]+pd.Timedelta(minutes=30),'Scoring horizon')
                        scored=pd.notna(row.scored_at)
                        require(scored==(ok and math.isfinite(yt)),'Delayed score availability')
                        if scored:require(pd.Timestamp(row.scored_at)==pd.Timestamp(row.target_time),'Delayed scoring maturity')
                        require(row.target_reason==('OK' if math.isfinite(yt) else 'TARGET_MISSING'),'Missing target reason')
                        require(bool(row.clean_eligible)==bool(valid[t-60:t+1].all() and math.isfinite(yt)),
                                'Clean eligibility denominator')
                        close(row.lower,yp-q if ok and q is not None else np.nan,'Interval lower')
                        close(row.upper,yp+q if ok and q is not None else np.nan,'Interval upper')
                        require(row.interval_reason==(reason if ok else row.point_reason),'Interval readiness')
        metrics.append(pid)
    require(set(metrics)==set(pids),'Participant verification coverage')
    result=dict(status='PASS',kind='NEW_EXPERIMENT',synthetic_fixture=manifest['synthetic_fixture'],
                verified_at=stamp(),model_fits=14,selection_searches=0,patient_replay_verified=False,
                artifact_manifest_sha256=expected_digest,scope='NEW internal bundle verification, not original reproduction or clinical validation')
    # Ensure verification itself did not mutate a pinned artifact.
    for name,h in manifest['files'].items():require(digest(relative(project,name))==h,'Artifact changed during verification')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True,help='Trusted digest printed/recorded by the generating execution')
    args=parser.parse_args(argv)
    try:
        result=verify(args.bundle,args.manifest_sha256)
        write(args.bundle/'bundle-verification.json',result)
        print('BUNDLE_VERIFIED_REPLAY_NOT_RUN')
        return 0
    except Exception as exc:
        print('Bundle verification failed: '+str(exc))
        return 1
