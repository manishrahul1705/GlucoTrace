"""Separate frozen combined Ridge experiment. Never modifies the sensor bundle."""
from dataclasses import asdict
from pathlib import Path
import csv
import json
import joblib
import numpy as np
import pandas as pd
from .common import ROOT, digest, load, write, stamp, hashes, source_files, separate, runtime
from .verify import check_hashes, close, require, median, quantile
from .generate import csv as save_csv
from glucotwin.features import SENSOR_FEATURES, BASELINE_FEATURES
from glucotwin.contracts import BASE_UNITS, BASE_COLUMNS
from glucotwin.stage3.training import fit_estimator, predict_estimator
from glucotwin.stage4.adaptation import partition_participant_origins, validate_calibration_gate
from glucotwin.stage5.core import partition_origins, fit_offset, calibrate, forecast_stream, inject_gap, gap_start, exact_targets
from glucotwin.stage5.metrics import summarize, slice_masks

FEATURES = SENSOR_FEATURES + BASELINE_FEATURES
VARIANTS = ('baseline_sensor_unadapted', 'baseline_sensor_offset24h')


def baseline_record(project, pid):
    frame = pd.read_csv(project/'data/processed/stage2/baseline_contract.csv')
    row = frame[frame.participant_id.eq(pid)]
    require(len(row)==1, 'BASELINE_PARTICIPANT_MISMATCH')
    row = row.iloc[0]
    return dict(schema=1, participant_id=pid, features=BASELINE_FEATURES, units=json.loads(row.units),
                values=[float(row[n]) for n in BASELINE_FEATURES], valid=bool(row.baseline_valid),
                source_file=row.source_file, source_row=int(row.source_row), provenance=row.provenance_reference,
                availability_assumption=row.baseline_availability_status)


def validate_baseline(record, pid):
    require(isinstance(record,dict), 'BASELINE_UNAVAILABLE')
    require(record.get('schema')==1 and record.get('features')==BASELINE_FEATURES, 'BASELINE_SCHEMA_INVALID')
    require(record.get('participant_id')==pid, 'BASELINE_PARTICIPANT_MISMATCH')
    require(record.get('units')==BASE_UNITS, 'BASELINE_UNITS_INVALID')
    values=np.asarray(record.get('values'),float)
    require(record.get('valid') is True and values.shape==(4,) and np.isfinite(values).all(), 'BASELINE_NONFINITE_OR_INVALID')
    return values


def freeze(bundle, trusted, output):
    bundle,output=Path(bundle).resolve(),Path(output).resolve()
    separate(output,bundle,ROOT)
    project,_,_=check_hashes(bundle,trusted)
    split=load(project/'reports/stage2/split_manifest.json')
    rows=list(csv.DictReader((project/'reports/stage3_remediation/selected_candidates.csv').open()))
    selected=[r for r in rows if r['family']=='ridge' and r['variant']=='sensor_plus_baseline']
    require(len(selected)==len(split['folds'])==14,'Combined selection coverage')
    for fold in split['folds']:
        chosen=[r for r in selected if r['outer_fold']==fold['outer_fold'] and int(r['held_out_pid'])==fold['test']['participants'][0]]
        require(len(chosen)==1,'Combined fold selection mismatch')
    output.mkdir(parents=True)
    record=dict(kind='FUSION_EXPERIMENT_FREEZE',frozen_at_utc=stamp(),parent_bundle=str(bundle),
                parent_manifest_sha256=trusted,source_sha256=hashes(ROOT,source_files()),runtime=runtime(),
                protocol=load(ROOT/'configs/fusion_protocol.json'),feature_order=FEATURES,selected=selected,expected_fits=14,
                inputs=hashes(project,['data/processed/stage2/sensor_plus_baseline.csv','data/processed/stage2/sensor_only.csv',
                    'data/processed/stage2/baseline_contract.csv','reports/stage2/split_manifest.json',
                    'reports/stage3_remediation/selected_candidates.csv']))
    write(output/'freeze.json',record)
    return digest(output/'freeze.json')


def execute(freeze_path, expected, output):
    freeze_path,output=Path(freeze_path).resolve(),Path(output).resolve();f=load(freeze_path)
    require(digest(freeze_path)==expected,'Fusion freeze digest')
    require(hashes(ROOT,f['source_sha256'])==f['source_sha256'] and runtime()==f['runtime'],'Frozen source/runtime changed')
    bundle=Path(f['parent_bundle']);project,_,_=check_hashes(bundle,f['parent_manifest_sha256'])
    require(hashes(project,f['inputs'])==f['inputs'],'Frozen inputs changed')
    separate(output,bundle,freeze_path.parent,ROOT);output.mkdir(parents=True)
    run=dict(kind='FUSION_NEW_EXPERIMENT',started_at=stamp(),fits=0,state='RUNNING',freeze_sha256=expected)
    write(output/'freeze.json',f)
    try:
        frame=pd.read_csv(project/'data/processed/stage2/sensor_plus_baseline.csv',float_precision='round_trip')
        sensor=pd.read_csv(project/'data/processed/stage2/sensor_only.csv',float_precision='round_trip')
        require(frame.origin_id.equals(sensor.origin_id),'Paired origin identity')
        close(frame[SENSOR_FEATURES],sensor[SENSOR_FEATURES],'Paired features');close(frame.target_mg_dl,sensor.target_mg_dl,'Paired targets')
        require(list(frame.columns[-25:])==FEATURES and np.isfinite(frame[FEATURES]).all().all(),'Combined feature order/values')
        split=load(project/'reports/stage2/split_manifest.json');allparts=[];evals=[];artifacts=[];s4=[]
        for fold in split['folds']:
            pid=fold['test']['participants'][0];train=frame[frame.participant_id.isin(fold['train']['participants'])]
            require(pid not in set(train.participant_id),'Outer exclusion')
            chosen=next(r for r in f['selected'] if r['outer_fold']==fold['outer_fold']);spec=json.loads(chosen['selected_candidate_spec'])
            model,scaler=fit_estimator('ridge',spec,train[FEATURES].to_numpy(),train.target_mg_dl.to_numpy())
            run['fits']+=1;write(output/'run.json',run);joblib.dump((model,scaler),output/f'model_{pid:03d}.joblib')
            baseline=baseline_record(project,pid);values=validate_baseline(baseline,pid)
            raw=pd.read_csv(project/'data/raw/tables/CGMacros/bio.csv');source=raw.iloc[baseline['source_row']-1]
            require(int(source.subject)==pid,'Baseline source participant');close(values,[source[BASE_COLUMNS[n]] for n in BASELINE_FEATURES],'Baseline source values')
            write(output/f'baseline_{pid:03d}.json',baseline)
            pred=lambda x:predict_estimator(model,scaler,np.column_stack((x,np.tile(values,(len(x),1)))))
            test=frame[frame.participant_id.eq(pid)].copy();test['base_prediction']=pred(test[SENSOR_FEATURES].to_numpy())
            stream=pd.read_csv(project/f'data/processed/stage2/observations/p{pid:03d}.csv',parse_dates=['event_time'],float_precision='round_trip').set_index('event_time')
            anchor=stream.index[stream.valid][0];part=partition_origins(test,anchor);allparts.append(part)
            offset_rows=part[part.partition.eq('offset')];cal=part[part.partition.eq('calibration')]
            offset,reason=fit_offset(offset_rows.target_mg_dl,offset_rows.base_prediction)
            four=partition_participant_origins(test,anchor);c4=four[four.partition.eq('calibration')];later=four[four.partition.eq('later_evaluation')]
            coverage=float(stream.valid.reindex(pd.date_range(anchor,periods=2880,freq='min'),fill_value=False).mean())
            ready=validate_calibration_gate(coverage,len(c4),len(later));off4,_=fit_offset(c4.target_mg_dl,c4.base_prediction)
            if not ready:off4=None
            for variant,delta in [('unadapted',0),('adapted48h',off4)]:
                errors=later.base_prediction+delta-later.target_mg_dl if delta is not None else pd.Series(dtype=float)
                high=errors[later.target_mg_dl>180] if len(errors) else errors
                s4.append(dict(participant_id=pid,variant=variant,ready=ready,n_calibration=len(c4),n_evaluation=len(later),coverage=coverage,offset=delta,
                    mae=errors.abs().mean(),rmse=np.sqrt((errors**2).mean()),mean_signed_error=errors.mean(),above180_mae=high.abs().mean(),above180_signed_error=high.mean()))
            scheduled=stream.index[::5];scheduled=scheduled[scheduled-pd.Timedelta(minutes=60)>=anchor+pd.Timedelta(hours=48)]
            start=gap_start(stream,anchor);targets=exact_targets(stream,scheduled)
            points={'clean':forecast_stream(stream,scheduled,pred)}
            for duration in (15,30,60,120):points[f'input_loss_{duration}m']=forecast_stream(inject_gap(stream,start,duration),scheduled,pred)
            for variant in VARIANTS:
                delta=0 if variant.endswith('unadapted') else offset
                for alpha in ('0.10','0.05'):
                    c=calibrate(abs(cal.target_mg_dl-(cal.base_prediction+(delta or 0))),alpha)
                    if delta is None:c=type(c)(len(cal),c.k,None,'INSUFFICIENT_OFFSET_DATA')
                    artifacts.append(dict(participant_id=pid,variant=variant,alpha=alpha,offset=delta,**asdict(c)))
                    for scenario,point in points.items():
                        rows=point.copy();rows['prediction']=rows.prediction+delta if delta is not None else np.nan
                        if delta is None:rows.loc[rows.point_reason.eq('OK'),'point_reason']='INSUFFICIENT_OFFSET_DATA'
                        rows['lower']=rows.prediction-c.q if c.q is not None else np.nan;rows['upper']=rows.prediction+c.q if c.q is not None else np.nan
                        rows['interval_reason']=np.where(rows.point_reason.eq('OK'),c.reason,rows.point_reason)
                        rows['target']=targets;rows['participant_id']=pid;rows['variant']=variant;rows['alpha']=alpha;rows['scenario']=scenario
                        rows['clean_eligible']=points['clean'].point_reason.eq('OK').to_numpy()&np.isfinite(targets);evals.append(rows)
        save_csv(output/'partitions.csv',pd.concat(allparts,ignore_index=True));save_csv(output/'stage4.csv',pd.DataFrame(s4))
        write(output/'calibration.json',artifacts);evaluation=pd.concat(evals,ignore_index=True);save_csv(output/'evaluation.csv',evaluation)
        summaries=[];people=[]
        for (scenario,variant,alpha),rows in evaluation.groupby(['scenario','variant','alpha']):
            for name,mask in slice_masks(rows).items():
                summary,per=summarize(rows.loc[mask],14)
                for d in (summary,per):d['scenario']=scenario;d['variant']=variant;d['alpha']=alpha;d['slice']=name
                summaries.append(summary);people.append(per)
        save_csv(output/'aggregate.csv',pd.concat(summaries));save_csv(output/'per_participant.csv',pd.concat(people))
        compare(output,project,evaluation)
        require(run['fits']==14,'Fit count')
        write(output/'manifest.json',dict(kind='FUSION_ARTIFACTS',freeze_sha256=expected,files={p.name:digest(p) for p in output.iterdir() if p.is_file() and p.name not in ('run.json','manifest.json')}))
        run['artifact_manifest_sha256']=digest(output/'manifest.json');run['state']='GENERATED_NOT_VERIFIED'
    except Exception as exc:run['state']='FAIL';run['error']=repr(exc);raise
    finally:run['finished_at']=stamp();write(output/'run.json',run)
    return run


def compare(output,project,evaluation):
    sensor=pd.read_csv(project/'data/processed/stage5/evaluation.csv',dtype={'alpha':str},float_precision='round_trip')
    paired=[]
    for variant in VARIANTS:
        old='sensor_only_'+variant.removeprefix('baseline_sensor_')
        for pid,rows in evaluation[(evaluation.scenario=='clean')&(evaluation.variant==variant)&(evaluation.alpha=='0.05')].groupby('participant_id'):
            base=sensor[(sensor.participant_id==pid)&(sensor.scenario=='clean')&(sensor.variant==old)&(sensor.alpha=='0.05')]
            require(list(pd.to_datetime(base.issue_time))==list(pd.to_datetime(rows.issue_time)),'Paired scheduled origins')
            for name,mask in slice_masks(rows).items():
                eligible=mask.to_numpy()&rows.point_reason.eq('OK').to_numpy()&np.isfinite(rows.target.to_numpy())&base.point_reason.eq('OK').to_numpy()
                a=rows.loc[eligible];b=base.loc[eligible];ae=a.prediction-a.target;be=b.prediction-b.target
                paired.append(dict(participant_id=pid,variant=variant,slice=name,n=len(a),combined_mae=ae.abs().mean(),sensor_mae=be.abs().mean(),
                    mae_difference=ae.abs().mean()-be.abs().mean(),combined_signed_error=ae.mean(),sensor_signed_error=be.mean(),
                    combined_underprediction=float((ae<0).mean()) if len(a) else np.nan,sensor_underprediction=float((be<0).mean()) if len(b) else np.nan))
    frame=pd.DataFrame(paired);save_csv(output/'paired.csv',frame)
    from glucotwin.stage4.evaluation import generate_shared_bootstrap_draws
    draws,_=generate_shared_bootstrap_draws(14,10000,1705)
    results=[]
    for variant,rows in frame[frame.slice.eq('all')].groupby('variant'):
        delta=rows.mae_difference.to_numpy();means=delta[np.asarray(draws)].mean(1)
        results.append(dict(variant=variant,participants=len(rows),mae_difference=float(delta.mean()),
                            participant_bootstrap_95=list(map(float,np.quantile(means,[.025,.975])))))
    write(output/'paired_summary.json',results)


def verify(output,trusted):
    """Independent scaler/normal equation, partition, median and rank arithmetic. No fit."""
    output=Path(output);require(digest(output/'manifest.json')==trusted,'Fusion caller-pinned manifest')
    manifest=load(output/'manifest.json');require(manifest['kind']=='FUSION_ARTIFACTS','Fusion artifact kind')
    for name,h in manifest['files'].items():
        require(Path(name).name==name and digest(output/name)==h,'Fusion artifact bytes')
    f=load(output/'freeze.json');require(digest(output/'freeze.json')==manifest['freeze_sha256'],'Fusion freeze')
    project,_,_=check_hashes(Path(f['parent_bundle']),f['parent_manifest_sha256'])
    require(hashes(project,f['inputs'])==f['inputs'],'Fusion parent input hashes')
    frame=pd.read_csv(project/'data/processed/stage2/sensor_plus_baseline.csv',float_precision='round_trip')
    refs=pd.read_csv(output/'partitions.csv',float_precision='round_trip');cal=load(output/'calibration.json')
    evaluation=pd.read_csv(output/'evaluation.csv',dtype={'alpha':str},float_precision='round_trip')
    stage4=pd.read_csv(output/'stage4.csv',float_precision='round_trip')
    require(f['feature_order']==FEATURES and list(frame.columns[-25:])==FEATURES,'Fusion feature order')
    require(refs.origin_id.equals(frame.origin_id) or set(refs.origin_id)==set(frame.origin_id),'Fusion reference coverage')
    require(refs.origin_id.is_unique and len(cal)==56,'Fusion reference/calibration cardinality')
    for fold in load(project/'reports/stage2/split_manifest.json')['folds']:
        pid=fold['test']['participants'][0];train=frame[frame.participant_id.isin(fold['train']['participants'])];test=frame[frame.participant_id.eq(pid)]
        require(pid not in set(train.participant_id),'Fusion outer exclusion')
        model,scaler=joblib.load(output/f'model_{pid:03d}.joblib');x=train[FEATURES].to_numpy();y=train.target_mg_dl.to_numpy()
        require(model.__class__.__name__=='Ridge' and scaler.__class__.__name__=='StandardScaler' and model.fit_intercept,'Fusion estimator types')
        close(scaler.mean_,x.mean(0),'Fusion training mean');close(scaler.var_,x.var(0),'Fusion training variance');require(scaler.n_samples_seen_==len(x),'Fusion scaler sample count')
        eps=np.finfo(float).eps;var=x.var(0);constant=var<=len(x)*eps*var+(len(x)*x.mean(0)*eps)**2
        close(scaler.scale_,np.where(constant,1,np.sqrt(var)),'Fusion scaler scale')
        require(model.n_features_in_==scaler.n_features_in_==25,'Fusion dimensions')
        chosen=next(r for r in f['selected'] if r['outer_fold']==fold['outer_fold']);alpha=json.loads(chosen['selected_candidate_spec'])['alpha'];require(model.alpha==alpha,'Combined selected alpha')
        z=(x-scaler.mean_)/scaler.scale_;zc=z-z.mean(0);coef=np.linalg.solve(zc.T@zc+alpha*np.eye(25),zc.T@(y-y.mean()))
        close(model.coef_,coef,'Fusion normal equation',1e-5);close(model.intercept_,y.mean()-z.mean(0)@coef,'Fusion intercept',1e-6)
        b=validate_baseline(load(output/f'baseline_{pid:03d}.json'),pid);close(test[BASELINE_FEATURES],np.tile(b,(len(test),1)),'Fusion baseline mapping')
        raw=pd.read_csv(project/'data/raw/tables/CGMacros/bio.csv');source=raw[raw.subject.eq(pid)]
        require(len(source)==1,'Fusion baseline source key');close(b,[source.iloc[0][BASE_COLUMNS[n]] for n in BASELINE_FEATURES],'Fusion raw baseline agreement')
        rows=refs[refs.participant_id.eq(pid)].set_index('origin_id').loc[test.origin_id]
        predictions=((test[FEATURES].to_numpy()-scaler.mean_)/scaler.scale_)@model.coef_+model.intercept_
        close(rows.base_prediction,predictions,'Fusion held-out predictions')
        from .verify import phase
        anchor=pd.Timestamp(pd.read_csv(project/'data/processed/stage5/partition_adequacy.csv').set_index('participant_id').loc[pid,'anchor'])
        require(list(rows.partition)==[phase(pd.Timestamp(i),anchor,5) for i in rows.issue_time],'Fusion purges')
        for record in stage4[stage4.participant_id.eq(pid)].itertuples():
            parts=[phase(pd.Timestamp(i),anchor,4) for i in rows.issue_time];c4=rows[np.array(parts)=='calibration'];later=rows[np.array(parts)=='later_evaluation']
            delta=0 if record.variant=='unadapted' else median(c4.target_mg_dl-c4.base_prediction) if record.ready else None
            close(record.offset,delta if delta is not None else np.nan,'Fusion Stage4 offset')
            if delta is not None:close(record.mae,abs(later.base_prediction+delta-later.target_mg_dl).mean(),'Fusion Stage4 MAE')
        off=rows[rows.partition.eq('offset')];cr=rows[rows.partition.eq('calibration')];offset=median(off.target_mg_dl-off.base_prediction) if len(off)>=100 else None
        stream=pd.read_csv(project/f'data/processed/stage2/observations/p{pid:03d}.csv',parse_dates=['event_time'],float_precision='round_trip').set_index('event_time')
        from .verify import feature
        g=stream.glucose_mg_dl.to_numpy();valid=stream.valid.to_numpy();start=int(np.ceil(((anchor-stream.index[0]).total_seconds()/60+4320)/5)*5)
        schedule=[t for t in range(0,len(g),5) if stream.index[t]-pd.Timedelta(minutes=60)>=anchor+pd.Timedelta(hours=48)]
        cache={t:float(((np.r_[feature(g[t-60:t+1]),b]-scaler.mean_)/scaler.scale_)@model.coef_+model.intercept_) for t in schedule if valid[t-60:t+1].all()}
        for a in [a for a in cal if a['participant_id']==pid]:
            delta=0 if a['variant'].endswith('unadapted') else offset
            n,k,q,reason=quantile(abs(cr.target_mg_dl-cr.base_prediction-(delta or 0)),a['alpha'])
            if delta is None:q=None;reason='INSUFFICIENT_OFFSET_DATA'
            require((a['n'],a['k'],a['reason'],a['offset'])==(n,k,reason,delta),'Fusion offset/rank');close(a['q'] if a['q'] is not None else np.nan,q if q is not None else np.nan,'Fusion quantile')
            groups=evaluation[evaluation.participant_id.eq(pid)&evaluation.variant.eq(a['variant'])&evaluation.alpha.eq(a['alpha'])]
            require(set(groups.scenario)==set(f['protocol']['scenarios']),'Fusion scenario coverage')
            for scenario,group in groups.groupby('scenario'):
                duration=0 if scenario=='clean' else int(scenario.split('_')[-1][:-1]);changed=valid.copy()
                if duration:changed[start:start+duration]=False
                require(list(pd.to_datetime(group.issue_time))==list(stream.index[schedule]),'Fusion schedule')
                last=-1;last_valid=np.full(len(g),-1)
                for t,ok in enumerate(changed):
                    if ok:last=t
                    last_valid[t]=last
                for row,t in zip(group.itertuples(),schedule):
                    ok=bool(changed[t-60:t+1].all()) and delta is not None
                    yp=cache[t]+delta if ok else np.nan;yt=g[t+30] if t+30<len(g) and valid[t+30] else np.nan
                    close(row.prediction,yp,'Fusion scheduled prediction');close(row.target,yt,'Fusion exact target')
                    close(row.lower,yp-q if ok and q is not None else np.nan,'Fusion lower bound');close(row.upper,yp+q if ok and q is not None else np.nan,'Fusion upper bound')
                    if not changed[t]:
                        codes=['MISSING_CURRENT_READING'];injected=bool(duration and start<=t<start+duration)
                        if not injected and bool(stream.row_present.iloc[t]) and not np.isfinite(g[t]):codes.append('NON_FINITE_READING')
                        if not injected and np.isfinite(g[t]) and not 40<=g[t]<=400:codes.append('SOURCE_INVALID_READING')
                        if last_valid[t]>=0 and t-last_valid[t]>10:codes.append('STALE_READING')
                        point_reason=';'.join(codes)
                    else:point_reason='INCOMPLETE_HISTORY' if not changed[t-60:t+1].all() else 'INSUFFICIENT_OFFSET_DATA' if delta is None else 'OK'
                    require(row.point_reason==point_reason,'Fusion missingness reason');require(row.interval_reason==(reason if ok else point_reason),'Fusion interval readiness')
    return dict(status='PASS',verified_at=stamp(),fits=14,participants=14,artifact_manifest_sha256=trusted)
