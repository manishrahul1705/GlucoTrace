"""Direct recomputation verifier; shared feature/access components are disclosed.

Independent rank arithmetic, partitions, metrics and availability oracle. Shares
Stage 2 feature builder and Stage 5 replay for prefix-access checks only.
No model fitting and no historical artifact writes.
"""
import os
for name in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:
    os.environ[name]='1'
import hashlib
import json
from pathlib import Path
import sys
from decimal import Decimal, ROUND_CEILING
import numpy as np
import pandas as pd
import joblib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from glucotwin.features import build_sensor_features, SENSOR_FEATURES
from glucotwin.stage5.core import forecast_stream


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_close(a,b):
    np.testing.assert_allclose(a,b,rtol=0,atol=1e-8,equal_nan=True)


def direct_metrics(d):
    p=d[(d.point_reason=='OK') & np.isfinite(d.target)]
    q=d[(d.interval_reason=='OK') & (d.point_reason=='OK') & np.isfinite(d.target)]
    e=p.prediction.to_numpy()-p.target.to_numpy()
    return dict(mae=float(np.abs(e).mean()) if len(e) else np.nan,
                rmse=float(np.sqrt(np.mean(e*e))) if len(e) else np.nan,
                mean_signed_error=float(e.mean()) if len(e) else np.nan,
                empirical_coverage=float(((q.lower<=q.target)&(q.target<=q.upper)).mean()) if len(q) else np.nan,
                mean_width=float((q.upper-q.lower).mean()) if len(q) else np.nan)


def check_summary(d,stored,n_participants):
    people=[direct_metrics(g) for _,g in d.groupby('participant_id')]
    for row in stored.itertuples():
        if row.weighting=='pooled_window':
            expected=direct_metrics(d)
        else:
            expected={key:float(np.mean([p[key] for p in people if np.isfinite(p[key])]))
                      if any(np.isfinite(p[key]) for p in people) else np.nan for key in direct_metrics(d)}
        for key,value in expected.items(): assert_close(getattr(row,key),value)
        issued=d.point_reason.eq('OK') & np.isfinite(d.prediction)
        intervals=issued & d.interval_reason.eq('OK')
        score=issued & np.isfinite(d.target)
        iscore=intervals & np.isfinite(d.target)
        for key,value in dict(n_scheduled=len(d),n_eligible=int(d.clean_eligible.sum()),n_issued=int(issued.sum()),
                              n_interval_available=int(intervals.sum()),n_target_available=int(np.isfinite(d.target).sum()),
                              n_point_scored=int(score.sum()),n_interval_scored=int(iscore.sum()),
                              contributing_point_participants=d.loc[score].participant_id.nunique(),
                              contributing_interval_participants=d.loc[iscore].participant_id.nunique()).items():
            assert getattr(row,key)==value,(key,getattr(row,key),value)
        assert row.n_expected_participants==n_participants
        assert row.absent_point_participants==n_participants-d.loc[score].participant_id.nunique()
        assert row.absent_interval_participants==n_participants-d.loc[iscore].participant_id.nunique()
        for metric in ['empirical_coverage','mean_width']:
            values=[p[metric] for p in people if np.isfinite(p[metric])]
            assert_close(getattr(row,'participant_'+metric+'_min'),min(values) if values else np.nan)
            assert_close(getattr(row,'participant_'+metric+'_max'),max(values) if values else np.nan)


def verify():
    local,out=ROOT/'data/processed/stage5',ROOT/'reports/stage5'
    manifest=json.loads((out/'run_manifest.json').read_text())
    config=json.loads((ROOT/'configs/stage5_protocol.json').read_text())
    assert sha(ROOT/'configs/stage5_protocol.json')==manifest['protocol_sha256']
    assert manifest['protocol_sha256']==json.loads((local/'protocol_freeze.json').read_text())['protocol_sha256']
    for name,value in manifest['code_sha256'].items(): assert sha(ROOT/name)==value
    inputs=json.loads((local/'input_hashes.json').read_text())
    for name,value in inputs.items(): assert sha(ROOT/name)==value
    assert hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()==manifest['input_bundle_sha256']
    for name,value in json.loads((local/'stage4_preservation.json').read_text()).items(): assert sha(ROOT/name)==value
    for name,value in manifest['output_sha256'].items(): assert sha(out/name)==value
    assert sha(local/'calibration_artifacts.json')==manifest['local_calibration_artifacts_sha256']
    rows=pd.read_csv(local/'evaluation.csv',dtype={'alpha':str},parse_dates=['issue_time','target_time'])
    parts=pd.read_csv(local/'partition_predictions.csv',parse_dates=['issue_time','history_start','target_time'])
    adequacy=pd.read_csv(local/'partition_adequacy.csv',parse_dates=['anchor'])
    artifacts=json.loads((local/'calibration_artifacts.json').read_text())
    gaps=pd.read_csv(local/'gap_schedule.csv',parse_dates=['start','end'])
    split=json.loads((ROOT/'reports/stage2/split_manifest.json').read_text())
    pids=split['eligible_participants']
    for fold in split['folds']:
        held=fold['test']['participants']
        assert len(held)==1 and set(held).isdisjoint(fold['train']['participants'])
        assert set(fold['train']['participants'])==set(pids)-set(held)
        for inner in fold['inner_folds']:
            assert set(held).isdisjoint(inner['train']['participants']+inner['validation']['participants'])
    previous=pd.read_csv(ROOT/'data/processed/stage3_remediation/predictions/test_predictions.csv').set_index('origin_id')
    max_error=0.; suppressed=0; resumed=0; future_checks=0
    for pid in pids:
        stream=pd.read_csv(ROOT/f'data/processed/stage2/observations/p{pid:03d}.csv',parse_dates=['event_time']).set_index('event_time')
        a=adequacy[adequacy.participant_id==pid].iloc[0]
        anchor=a.anchor
        assert anchor==stream.index[stream.valid][0]
        p=parts[parts.participant_id==pid]
        assert (p.history_start==p.issue_time-pd.Timedelta(minutes=60)).all()
        assert (p.target_time==p.issue_time+pd.Timedelta(minutes=30)).all()
        independent=[]
        for hs,target in zip(p.history_start,p.target_time):
            if hs>=anchor and target<anchor+pd.Timedelta(hours=24): label='offset'
            elif hs>=anchor+pd.Timedelta(hours=24) and target<anchor+pd.Timedelta(hours=48): label='calibration'
            elif hs>=anchor+pd.Timedelta(hours=48): label='evaluation'
            else: label='purged'
            independent.append(label)
        assert p.partition.tolist()==independent
        for label,column in [('offset','n_offset'),('calibration','n_calibration'),('evaluation','n_evaluation'),('purged','n_purged')]:
            assert int(p.partition.eq(label).sum())==getattr(a,column)
        phase1=p[p.partition=='offset']; phase2=p[p.partition=='calibration']
        assert set(phase1.origin_id).isdisjoint(phase2.origin_id)
        delta=float(np.median(phase1.target_mg_dl-phase1.base_prediction))
        assert_close(p.base_prediction,previous.loc[p.origin_id,'ridge_sensor_only'])
        est,scaler=joblib.load(local/f'model_{pid:03d}.joblib')
        predict=lambda x: est.predict(scaler.transform(x))
        model_before=joblib.hash((est,scaler))
        for art in [x for x in artifacts if x['participant_id']==pid]:
            b=delta if art['variant'].endswith('offset24h') else 0
            assert_close(art['offset'],b)
            scores=np.sort(np.abs(phase2.target_mg_dl.to_numpy()-phase2.base_prediction.to_numpy()-b))
            # Separate Decimal ceiling implementation (production uses Fraction).
            k=int(((Decimal(len(scores))+1)*(1-Decimal(art['alpha']))).to_integral_value(rounding=ROUND_CEILING))
            assert art['k']==k and art['n']==len(scores) and art['invalid_count']==0
            assert len(scores)>=100 and k<=len(scores) and art['reason']=='OK'
            assert_close(art['q'],scores[k-1])
        grid=stream.index[::5]
        schedule=grid[grid-pd.Timedelta(minutes=60)>=anchor+pd.Timedelta(hours=48)]
        pg=rows[rows.participant_id==pid]
        for scenario,g in pg.groupby('scenario'):
            d=stream.copy()
            gap=None
            if scenario!='clean':
                duration=int(scenario.removeprefix('input_loss_').removesuffix('m'))
                gap=gaps[(gaps.participant_id==pid)&(gaps.duration_minutes==duration)].iloc[0]
                expected_start=grid[grid>=anchor+pd.Timedelta(hours=72)][0]
                assert gap.start==expected_start and gap.end==expected_start+pd.Timedelta(minutes=duration)
                mask=(d.index>=gap.start)&(d.index<gap.end)
                assert int(mask.sum())==gap.removed_minutes
                d.loc[mask,'valid']=False;d.loc[mask,'glucose_mg_dl']=np.nan
            valid=d.valid & np.isfinite(d.glucose_mg_dl) & d.glucose_mg_dl.between(40,400)
            complete=valid.astype(int).rolling(61,min_periods=61).sum().eq(61).reindex(schedule).to_numpy()
            features=build_sensor_features(d)
            base=np.full(len(schedule),np.nan)
            base[complete]=predict(features.reindex(schedule[complete])[SENSOR_FEATURES].to_numpy())
            reference=stream.reindex(schedule+pd.Timedelta(minutes=30))
            target=np.where(reference.valid.eq(True)&np.isfinite(reference.glucose_mg_dl)&reference.glucose_mg_dl.between(40,400),reference.glucose_mg_dl,np.nan)
            for (variant,alpha),r in g.groupby(['variant','alpha']):
                assert pd.DatetimeIndex(r.issue_time).equals(schedule)
                assert (r.target_time==r.issue_time+pd.Timedelta(minutes=30)).all()
                assert np.array_equal(r.point_reason.eq('OK').to_numpy(),complete)
                offset=delta if variant.endswith('offset24h') else 0
                assert_close(r.prediction,base+offset)
                assert_close(r.target,target)
                assert np.array_equal(r.target_reason.eq('OK'),np.isfinite(target))
                art=next(x for x in artifacts if x['participant_id']==pid and x['variant']==variant and x['alpha']==alpha)
                assert np.array_equal(r.interval_reason.eq('OK'),complete)
                assert_close(r.lower,r.prediction-art['q']);assert_close(r.upper,r.prediction+art['q'])
                err=np.nanmax(np.abs(r.prediction.to_numpy()-base-offset))
                max_error=max(max_error,float(err))
                if gap is not None:
                    affected=(r.issue_time>=gap.start)&(r.issue_time<gap.end+pd.Timedelta(minutes=60))
                    assert not r.loc[affected].point_reason.eq('OK').any()
                    suppressed+=int(affected.sum())
            if gap is not None:
                recovery=schedule[schedule>=gap.end+pd.Timedelta(minutes=60)][0]
                expected=bool(valid.loc[recovery-pd.Timedelta(minutes=60):recovery].all())
                assert bool(complete[schedule.get_loc(recovery)])==expected
                resumed+=int(expected)
        # Exercise production application path with all unrevealed rows changed.
        issue=schedule[0]
        early=forecast_stream(stream,[issue],predict)
        changed=stream.copy();changed.loc[changed.index>issue,'glucose_mg_dl']=-999;changed.loc[changed.index>issue,'valid']=False
        pd.testing.assert_frame_equal(early,forecast_stream(changed,[issue],predict))
        assert joblib.hash((est,scaler))==model_before
        future_checks+=1
    # Nested intervals compared on exactly the same participant/issue/scenario/variant.
    wide=rows.pivot(index=['participant_id','issue_time','scenario','variant'],columns='alpha',values=['lower','upper'])
    finite=wide['lower']['0.10'].notna() & wide['lower']['0.05'].notna()
    assert (wide['lower']['0.05'][finite]<=wide['lower']['0.10'][finite]).all()
    assert (wide['upper']['0.05'][finite]>=wide['upper']['0.10'][finite]).all()
    stored=pd.read_csv(out/'aggregate_metrics.csv',dtype={'alpha':str})
    partition_summary=json.loads((out/'partition_summary.json').read_text())
    assert partition_summary['origin_counts']==parts.partition.value_counts().to_dict()
    assert partition_summary['n_participants']==len(pids)
    assert partition_summary['n_offset_adequate']==int((adequacy.n_offset>=100).sum())
    assert partition_summary['n_calibration_adequate']==int((adequacy.n_calibration>=100).sum())
    assert partition_summary['n_later_adequate']==int((adequacy.n_evaluation>=100).sum())
    assert partition_summary['n_scheduled_clean']==int(((rows.scenario=='clean') &
           (rows.variant=='sensor_only_unadapted') & (rows.alpha=='0.10')).sum())
    reason_table=rows.groupby(['scenario','variant','alpha','point_reason','interval_reason','target_reason']).size().rename('count').reset_index()
    pd.testing.assert_frame_equal(reason_table,pd.read_csv(out/'availability_reasons.csv',dtype={'alpha':str}))
    for (scenario,variant,alpha,slice_name),r in stored.groupby(['scenario','variant','alpha','slice']):
        d=rows[(rows.scenario==scenario)&(rows.variant==variant)&(rows.alpha==alpha)]
        if slice_name=='below70': d=d[d.target<70]
        elif slice_name=='70to180': d=d[d.target.between(70,180)]
        elif slice_name=='above180': d=d[d.target>180]
        check_summary(d,r,len(pids))
    dropout=pd.read_csv(out/'dropout_summary.csv',dtype={'alpha':str})
    pd.testing.assert_frame_equal(dropout.reset_index(drop=True),stored[(stored.scenario!='clean')&(stored['slice']=='all')].reset_index(drop=True))
    matched=pd.read_csv(out/'dropout_matched_metrics.csv',dtype={'alpha':str})
    for (scenario,variant,alpha),r in matched.groupby(['scenario','variant','alpha']):
        clean=rows[(rows.scenario=='clean')&(rows.variant==variant)&(rows.alpha==alpha)]
        gap=rows[(rows.scenario==scenario)&(rows.variant==variant)&(rows.alpha==alpha)]
        keys=['participant_id','issue_time']
        good=gap[(gap.point_reason=='OK')&(gap.interval_reason=='OK')&np.isfinite(gap.target)][keys]
        clean=clean.merge(good,on=keys,validate='one_to_one')
        gap=gap.merge(good,on=keys,validate='one_to_one')
        assert_close(clean.prediction,gap.prediction)
        assert_close(clean.lower,gap.lower);assert_close(clean.upper,gap.upper)
        check_summary(clean,r[r.matched_source=='clean'],len(pids))
        check_summary(gap,r[r.matched_source=='gap'],len(pids))
    # Candidate reports contain no participant IDs/rows or private absolute paths.
    for path in out.glob('*'):
        if path.suffix not in ['.json','.csv','.md']:continue
        text=path.read_text(encoding='utf-8')
        assert 'C:\\Users\\' not in text and 'C:/Users/' not in text
        if path.suffix=='.csv':
            columns=pd.read_csv(path,nrows=0).columns
            assert not set(columns)&{'participant_id','origin_id','issue_time','target_time','offset','q','source_file'}
    # Read-only historical Stage 4 reproduction; never regenerate its reports.
    historical_cal=pd.read_csv(ROOT/'data/processed/stage4/predictions/calibration_predictions.csv')
    historical_later=pd.read_csv(ROOT/'data/processed/stage4/predictions/later_evaluation_predictions.csv')
    historical_agg=pd.read_csv(ROOT/'reports/stage4/aggregate_metrics.csv').set_index('method')
    historical_offsets=pd.read_csv(ROOT/'data/processed/stage4/patient_offsets.csv').set_index('participant_id')
    for variant in ['sensor_only','sensor_plus_baseline']:
        person_metrics=[]
        for pid,g in historical_later.groupby('participant_id'):
            c=historical_cal[historical_cal.participant_id==pid]
            b=float(np.median(c.target_mg_dl-c['ridge_'+variant]))
            assert_close(b,historical_offsets.loc[pid,'offset_'+variant+'_mg_dl'])
            assert_close(g['ridge_'+variant+'_adapted'],g['ridge_'+variant+'_unadapted']+b)
            for state in ['unadapted','adapted']:
                name='ridge_'+variant+'_'+state
                error=g[name]-g.target_mg_dl
                person_metrics.append(dict(method=name,mae=float(error.abs().mean()),
                                           rmse=float(np.sqrt((error**2).mean())),signed=float(error.mean())))
        for name,g in pd.DataFrame(person_metrics).groupby('method'):
            assert_close(g.mae.mean(),historical_agg.loc[name,'primary_equal_person_mae_mg_dl'])
            assert_close(g.rmse.mean(),historical_agg.loc[name,'secondary_equal_person_rmse_mg_dl'])
            assert_close(g.signed.mean(),historical_agg.loc[name,'equal_person_mean_signed_error_mg_dl'])
    report=dict(status='PASS',scope='Executed Stage 5 checks only; scientific/permissions limitations remain',
                n_participants=len(pids),n_stored_rows=len(rows),n_aggregate_rows=len(stored),
                max_recomputed_prediction_difference=max_error, future_access_checks=future_checks,
                gap_scenario_recovery_checks=resumed, suppressed_rows_across_variants_levels=suppressed,
                stage4_files_unchanged=True, input_and_protocol_hashes_pass=True,
                historical_stage4_offset_and_point_metrics_reproduced=True,
                shared_components=['Stage 2 trailing feature builder for replay prediction reproduction',
                                   'Stage 5 forecast_stream for application future-access checks'],
                independent_calculations=['Decimal ranks and scores','timestamp partitions','median offsets',
                                         'availability oracle','direct metrics, slice summaries and matched summaries','exact target joins'],
                limitations=config['limitations'])
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['limitations','shared_components','independent_calculations']},indent=2))


if __name__=='__main__':
    verify()
