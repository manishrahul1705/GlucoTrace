"""Reproduce frozen Ridge refits, then run the frozen Stage 5 experiment."""
import os
for name in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:
    os.environ[name] = '1'
import hashlib
import json
from pathlib import Path
import sys
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from glucotwin.features import SENSOR_FEATURES, build_sensor_features
from glucotwin.stage3.training import fit_estimator, predict_estimator
from glucotwin.stage5.core import (calibrate, fit_offset, partition_origins, forecast_stream,
                                    exact_targets, interval_bounds, gap_start, inject_gap)
from glucotwin.stage5.metrics import summarize, slice_masks


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def load_stream(pid):
    d = pd.read_csv(ROOT/f'data/processed/stage2/observations/p{pid:03d}.csv', parse_dates=['event_time'])
    return d.set_index('event_time')


def add_intervals(points, variant, offset, calibration, alpha, scenario, pid, clean_eligible, targets):
    d = points.copy()
    if variant == 'sensor_only_offset24h':
        if offset is None:
            mask = d.point_reason.eq('OK')
            d.loc[mask, 'point_reason'] = 'INSUFFICIENT_OFFSET_DATA'
            d.loc[mask, 'prediction'] = np.nan
        else:
            d['prediction'] += offset
    bounds = [interval_bounds(p, calibration) if reason == 'OK' else (np.nan,np.nan,reason)
              for p, reason in zip(d.prediction, d.point_reason)]
    d[['lower','upper','interval_reason']] = pd.DataFrame(bounds, index=d.index)
    d['participant_id'], d['variant'], d['alpha'], d['scenario'] = pid, variant, alpha, scenario
    d['target_time'] = d.issue_time+pd.Timedelta(minutes=30)
    d['target'] = targets
    d['target_reason'] = np.where(np.isfinite(targets), 'OK', 'TARGET_MISSING')
    d['clean_eligible'] = clean_eligible
    return d


def run():
    out, local = ROOT/'reports/stage5', ROOT/'data/processed/stage5'
    out.mkdir(exist_ok=True)
    local.mkdir(exist_ok=True)
    proto_path = ROOT/'configs/stage5_protocol.json'
    protocol = json.loads(proto_path.read_text())
    if not (local/'starting_state.json').exists():
        initial = {str(p.relative_to(ROOT).as_posix()):sha(p)
                   for folder in ['src','tests','scripts','configs','docs','reports']
                   for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts
                   and p.suffix not in ['.pyc','.log']}
        for name in ['.gitignore','PROJECT_STATUS.md','STAGE4_REMEDIATION_HANDOFF_FOR_REVIEW.md']:
            if (ROOT/name).exists(): initial[name]=sha(ROOT/name)
        write_json(local/'starting_state.json',dict(
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),initial_file_hashes=initial))
    if not (local/'protocol_freeze.json').exists():
        write_json(local/'protocol_freeze.json',dict(protocol_sha256=sha(proto_path),
            recorded_before_stage5_evaluation=True,frozen_at_utc=datetime.now(timezone.utc).isoformat()))
    freeze = json.loads((local/'protocol_freeze.json').read_text())
    assert sha(proto_path) == freeze['protocol_sha256'], 'Protocol changed since freeze'
    # Persist the hash before loading predictions or computing any Stage 5 metrics.
    write_json(out/'protocol_freeze.json', freeze)
    print('Frozen Stage 5 protocol SHA-256:', freeze['protocol_sha256'], flush=True)
    inputs = ['configs/stage2_protocol.json','configs/stage3_run.json','configs/stage4_protocol.json',
              'reports/stage2/split_manifest.json','reports/stage3_remediation/selected_candidates.csv',
              'data/processed/stage2/sensor_only.csv',
              'data/processed/stage3_remediation/predictions/test_predictions.csv']
    inputs += [str(p.relative_to(ROOT).as_posix()) for p in (ROOT/'data/processed/stage2/observations').glob('*.csv')]
    inputs += [str(p.relative_to(ROOT).as_posix()) for p in (ROOT/'data/processed/stage2/personalization').glob('*.csv')]
    input_hashes = {name: sha(ROOT/name) for name in sorted(inputs)}
    write_json(local/'input_hashes.json', input_hashes)
    old = {str(p.relative_to(ROOT).as_posix()):sha(p) for folder in ['reports/stage4','data/processed/stage4']
           for p in (ROOT/folder).rglob('*') if p.is_file()}
    write_json(local/'stage4_preservation.json', old)
    s4 = json.loads((ROOT/'configs/stage4_protocol.json').read_text())
    for name, expected in s4['input_hashes'].items():
        content = (ROOT/name).read_bytes().replace(b'\r\n',b'\n')
        assert hashlib.sha256(content).hexdigest() == expected, f'Historical input changed: {name}'
    features = pd.read_csv(ROOT/'data/processed/stage2/sensor_only.csv')
    previous = pd.read_csv(ROOT/'data/processed/stage3_remediation/predictions/test_predictions.csv').set_index('origin_id')
    candidates = pd.read_csv(ROOT/'reports/stage3_remediation/selected_candidates.csv')
    split = json.loads((ROOT/'reports/stage2/split_manifest.json').read_text())
    pids = split['eligible_participants']
    assert sorted(features.participant_id.unique()) == pids
    partitions, adequacy, artifacts, gaps, reproduction = [], [], [], [], []
    evaluations = []
    for fold in split['folds']:
        pid = fold['test']['participants'][0]
        train_ids = fold['train']['participants']
        assert set(train_ids).isdisjoint([pid]) and set(train_ids) == set(pids)-{pid}
        for inner in fold['inner_folds']:
            assert pid not in inner['train']['participants']+inner['validation']['participants']
        train = features[features.participant_id.isin(train_ids)]
        test = features[features.participant_id.eq(pid)].copy()
        assert len(train) == fold['train']['n_origins'] and len(test) == fold['test']['n_origins']
        selected = candidates[(candidates.outer_fold == fold['outer_fold']) & (candidates.family == 'ridge') & (candidates.variant == 'sensor_only')]
        assert len(selected) == 1 and int(selected.held_out_pid.iloc[0]) == pid
        candidate = json.loads(selected.selected_candidate_spec.iloc[0])
        estimator, scaler = fit_estimator('ridge', candidate, train[SENSOR_FEATURES].to_numpy(), train.target_mg_dl.to_numpy())
        frozen_model_hash = joblib.hash((estimator,scaler))
        predictor = lambda x: predict_estimator(estimator, scaler, x)
        predicted = predictor(test[SENSOR_FEATURES].to_numpy())
        expected = previous.loc[test.origin_id, 'ridge_sensor_only'].to_numpy()
        np.testing.assert_allclose(predicted, expected, atol=1e-8, rtol=0)
        joblib.dump((estimator, scaler), local/f'model_{pid:03d}.joblib')
        reproduction.append(dict(participant_id=pid, max_prediction_discrepancy=float(np.max(np.abs(predicted-expected))),
                                 n_predictions=len(test), train_participants=train_ids, candidate=candidate))
        stream = load_stream(pid)
        personalization = pd.read_csv(ROOT/f'data/processed/stage2/personalization/p{pid:03d}.csv')
        anchors = pd.to_datetime(personalization.first_valid_time).unique()
        assert len(anchors) == 1
        anchor = pd.Timestamp(anchors[0])
        assert stream.index[stream.valid][0] == anchor
        # Full released-stream reconstruction matches the original prepared features.
        rebuilt = build_sensor_features(stream).reindex(pd.to_datetime(test.issue_time)).to_numpy()
        np.testing.assert_allclose(rebuilt, test[SENSOR_FEATURES].to_numpy(), atol=1e-8, rtol=0)
        grid = stream.index[::5]
        assert pd.DatetimeIndex(pd.to_datetime(test.issue_time)).isin(grid).all()
        np.testing.assert_allclose(exact_targets(stream, pd.to_datetime(test.issue_time)),test.target_mg_dl,rtol=0,atol=1e-10)
        test['base_prediction'] = predicted
        partitioned = partition_origins(test, anchor)
        partitions.append(partitioned)
        offset_rows = partitioned[partitioned.partition.eq('offset')]
        cal_rows = partitioned[partitioned.partition.eq('calibration')]
        later_rows = partitioned[partitioned.partition.eq('evaluation')]
        assert set(offset_rows.origin_id).isdisjoint(cal_rows.origin_id)
        original_later = pd.read_csv(ROOT/'data/processed/stage4/predictions/later_evaluation_predictions.csv')
        assert set(later_rows.origin_id) == set(original_later[original_later.participant_id.eq(pid)].origin_id)
        offset, offset_reason = fit_offset(offset_rows.target_mg_dl,offset_rows.base_prediction,protocol['adequacy']['min_offset_origins'])
        assert len(later_rows) >= protocol['adequacy']['min_later_eligible_origins']
        phases = {}
        for name, start in [('offset',anchor),('calibration',anchor+pd.Timedelta(hours=24))]:
            minute_index = pd.date_range(start, periods=1440, freq='min')
            phases[name+'_valid_minute_fraction'] = float(stream.valid.reindex(minute_index,fill_value=False).mean())
        adequacy.append(dict(participant_id=pid, anchor=anchor.isoformat(), n_offset=len(offset_rows),
                             n_calibration=len(cal_rows), n_evaluation=len(later_rows),
                             n_purged=int(partitioned.partition.eq('purged').sum()),
                             offset_reason=offset_reason, calibration_adequate=len(cal_rows)>=100, **phases))
        scheduled = grid[grid-pd.Timedelta(minutes=60) >= anchor+pd.Timedelta(hours=48)]
        clean_points = forecast_stream(stream, scheduled, predictor)
        targets = exact_targets(stream,scheduled)
        clean_eligible = clean_points.point_reason.eq('OK').to_numpy() & np.isfinite(targets)
        assert int(clean_eligible.sum()) == len(later_rows)
        start = gap_start(stream,anchor)
        scenarios = {'clean': clean_points}
        for duration in protocol['dropout']['durations_minutes']:
            assert start+pd.Timedelta(minutes=duration+60) <= stream.index[-1]
            changed = inject_gap(stream,start,duration)
            scenarios[f'input_loss_{duration}m'] = forecast_stream(changed,scheduled,predictor)
            gaps.append(dict(participant_id=pid,duration_minutes=duration,start=start.isoformat(),
                             end=(start+pd.Timedelta(minutes=duration)).isoformat(),
                             removed_minutes=int(((stream.index>=start)&(stream.index<start+pd.Timedelta(minutes=duration))).sum())))
        for variant in protocol['models']:
            cal_pred = cal_rows.base_prediction.to_numpy()+(offset if variant.endswith('offset24h') and offset is not None else 0)
            for alpha in protocol['interval']['alphas']:
                calibration = calibrate(np.abs(cal_rows.target_mg_dl.to_numpy()-cal_pred),alpha,
                                        protocol['adequacy']['min_interval_calibration_origins'])
                if variant.endswith('offset24h') and offset is None:
                    calibration = type(calibration)(len(cal_rows),calibration.k,None,'INSUFFICIENT_OFFSET_DATA')
                artifacts.append(dict(participant_id=pid,variant=variant,alpha=alpha,offset=offset if variant.endswith('offset24h') else 0,
                                      offset_reason=offset_reason, **asdict(calibration)))
                for scenario,points in scenarios.items():
                    evaluations.append(add_intervals(points,variant,offset,calibration,alpha,scenario,pid,clean_eligible,targets))
        assert joblib.hash((estimator,scaler)) == frozen_model_hash, 'Population model changed during replay'
        print(f'Frozen fold reproduced; participant processed ({len(adequacy)}/{len(pids)})',flush=True)
    partition_df = pd.concat(partitions,ignore_index=True)
    partition_df.to_csv(local/'partition_predictions.csv',index=False)
    pd.DataFrame(adequacy).to_csv(local/'partition_adequacy.csv',index=False)
    pd.DataFrame(gaps).to_csv(local/'gap_schedule.csv',index=False)
    write_json(local/'model_reproduction.json',reproduction)
    write_json(local/'calibration_artifacts.json',artifacts)
    frozen_artifact_hash = sha(local/'calibration_artifacts.json')
    rows = pd.concat(evaluations,ignore_index=True)
    rows.to_csv(local/'evaluation.csv',index=False)
    summaries, per_people, matched = [], [], []
    for (scenario,variant,alpha), group in rows.groupby(['scenario','variant','alpha']):
        for slice_name,mask in slice_masks(group).items():
            aggregate, per = summarize(group.loc[mask],len(pids))
            for frame in [aggregate,per]:
                frame['scenario'],frame['variant'],frame['alpha'],frame['slice'] = scenario,variant,alpha,slice_name
            summaries.append(aggregate)
            per_people.append(per)
        if scenario != 'clean':
            clean = rows[(rows.scenario=='clean') & (rows.variant==variant) & (rows.alpha==alpha)]
            join = group.merge(clean,on=['participant_id','issue_time'],suffixes=('_gap','_clean'),validate='one_to_one')
            accept = (join.point_reason_gap.eq('OK') & join.point_reason_clean.eq('OK') &
                      join.interval_reason_gap.eq('OK') & join.interval_reason_clean.eq('OK') & np.isfinite(join.target_gap))
            join = join.loc[accept]
            for label in ['gap','clean']:
                selected = join[[c for c in join if c.endswith('_'+label)]].copy()
                selected.columns = selected.columns.str.removesuffix('_'+label)
                selected['participant_id'] = join.participant_id
                aggregate,_ = summarize(selected,len(pids))
                aggregate['scenario'],aggregate['variant'],aggregate['alpha'] = scenario,variant,alpha
                aggregate['matched_source'] = label
                matched.append(aggregate)
    all_summary = pd.concat(summaries,ignore_index=True)
    all_summary.to_csv(out/'aggregate_metrics.csv',index=False)
    all_summary[(all_summary.scenario!='clean') & (all_summary['slice']=='all')].to_csv(out/'dropout_summary.csv',index=False)
    pd.concat(matched,ignore_index=True).to_csv(out/'dropout_matched_metrics.csv',index=False)
    pd.concat(per_people,ignore_index=True).to_csv(local/'participant_metrics.csv',index=False)
    reasons = rows.groupby(['scenario','variant','alpha','point_reason','interval_reason','target_reason']).size().rename('count').reset_index()
    reasons.to_csv(out/'availability_reasons.csv',index=False)
    counts = partition_df.partition.value_counts().to_dict()
    write_json(out/'partition_summary.json',dict(n_participants=len(pids), origin_counts=counts,
        n_offset_adequate=sum(a['offset_reason']=='OK' for a in adequacy),
        n_calibration_adequate=sum(a['calibration_adequate'] for a in adequacy),
        n_later_adequate=len(adequacy), n_scheduled_clean=int((rows.scenario.eq('clean') & rows.variant.eq(protocol['models'][0]) & rows.alpha.eq('0.10')).sum())))
    assert sha(local/'calibration_artifacts.json') == frozen_artifact_hash
    assert sha(proto_path) == freeze['protocol_sha256']
    assert all(sha(ROOT/name)==value for name,value in input_hashes.items())
    assert all(sha(ROOT/name)==value for name,value in old.items())
    code_paths = [*sorted((ROOT/'src/glucotwin/stage5').glob('*.py')),ROOT/'scripts/run_stage5.py',ROOT/'scripts/verify_stage5.py',
                  ROOT/'src/glucotwin/features.py',ROOT/'src/glucotwin/stage3/training.py',ROOT/'tests/test_stage5.py']
    code_hashes = {str(p.relative_to(ROOT).as_posix()):sha(p) for p in code_paths if p.exists()}
    write_json(out/'run_manifest.json',dict(protocol='stage5-v1',protocol_sha256=freeze['protocol_sha256'],
        frozen_before_evaluation=True,head=json.loads((local/'starting_state.json').read_text())['head'],
        timestamp_utc=datetime.now(timezone.utc).isoformat(), n_participants=len(pids),
        model_refits=14,selection_searches=0, code_sha256=code_hashes,
        input_bundle_sha256=hashlib.sha256(json.dumps(input_hashes,sort_keys=True).encode()).hexdigest(),
        local_calibration_artifacts_sha256=frozen_artifact_hash,
        model_reproduction_max_abs_difference=max(r['max_prediction_discrepancy'] for r in reproduction),
        stage4_files_unchanged=True, output_sha256={p.name:sha(p) for p in sorted(out.glob('*.csv'))},
        environment=dict(python=sys.version.split()[0],numpy=np.__version__,pandas=pd.__version__),
        limitations=protocol['limitations'],permissions='Candidate aggregates for technical review only; publication permissions unresolved'))
    print('Stage 5 evaluation complete; verifier required.',flush=True)


if __name__ == '__main__':
    run()
