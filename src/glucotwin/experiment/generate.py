"""NEW experiment generation. Historical command-line gates are never rewritten."""
from dataclasses import asdict
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import uuid
import numpy as np
import pandas as pd
import joblib
from .common import (ROOT, META, digest, load, write, stamp, separate, source_files,
                     hashes, selections, runtime, preflight, relative)
from .audit import audit_stream
from glucotwin.preprocessing import prepare_observations
from glucotwin.features import SENSOR_FEATURES
from glucotwin.stage3.training import fit_estimator, predict_estimator
from glucotwin.stage4.adaptation import partition_participant_origins, validate_calibration_gate
from glucotwin.stage5.core import (partition_origins, fit_offset, calibrate, forecast_stream,
                                  exact_targets, inject_gap, gap_start)
from glucotwin.stage5.metrics import summarize


def csv(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format='%.17g', date_format='%Y-%m-%dT%H:%M:%S', lineterminator='\n')


def audit_project(project):
    prov = load(project/META[0])
    split, _ = selections(project)
    windows, events = [], []
    for entry in prov['extracted']:
        name = Path(entry['path']).stem
        if not name.startswith('CGMacros-'):
            continue
        pid = int(name.split('-')[-1])
        if pid not in split['eligible_participants']:
            continue
        d = prepare_observations(pd.read_csv(project/entry['path']), pid, entry['path'], entry['sha256'])
        w, e = audit_stream(d, pid)
        windows.extend(w); events.extend(e)
    if sorted(r['participant'] for r in windows) != sorted(split['eligible_participants']):
        raise ValueError('Audit cohort missing or duplicated')
    csv(project/'docs/stage1/usable_windows.csv', pd.DataFrame(windows))
    csv(project/'docs/stage1/event_feasibility.csv', pd.DataFrame(events))
    write(project/'reports/new_experiment/audit-provenance.json',
          dict(scope='NEW derived audit, not historical Stage1 tables', expected_totals_inserted=False,
               hashes=hashes(project, ['docs/stage1/usable_windows.csv', 'docs/stage1/event_feasibility.csv'])))


def generate_models(project, frozen_split, manifest, synthetic=False):
    """Called only by explicit execution, or labelled synthetic test projects."""
    if synthetic and not manifest.get('synthetic_fixture'):
        raise ValueError('Synthetic computations must be labelled')
    split, selected = selections(project)
    if split != frozen_split:
        raise ValueError('Prepared split differs from frozen participant/origin mapping')
    feature_path = project/'data/processed/stage2/sensor_only.csv'
    features = pd.read_csv(feature_path, float_precision='round_trip')
    if sorted(features.participant_id.unique()) != sorted(split['eligible_participants']):
        raise ValueError('Prepared cohort mismatch')
    if features.origin_id.duplicated().any() or not np.isfinite(features[SENSOR_FEATURES+['target_mg_dl']]).all().all():
        raise ValueError('Invalid feature/reference rows')
    local = project/'data/processed/stage5'
    local.mkdir(parents=True, exist_ok=False)
    s4local = project/'data/processed/new_stage4'
    s4local.mkdir(parents=True, exist_ok=False)
    s5 = load(project/'configs/stage5_protocol.json')
    write(project/'reports/stage5/protocol_freeze.json', dict(protocol_sha256=digest(project/'configs/stage5_protocol.json'),
          frozen_at_utc=manifest['amendment_frozen_at'], new_execution=True,
          implementation_amendment_sha256=manifest['amendment_sha256']))
    partitions, adequacy, artifacts, reproduction, evaluations, stage4rows, stage4info = [], [], [], [], [], [], []
    stage4metrics = []
    for fold in split['folds']:
        pid = fold['test']['participants'][0]
        train = features[features.participant_id.isin(fold['train']['participants'])]
        test = features[features.participant_id.eq(pid)].copy()
        if len(train) != fold['train']['n_origins'] or len(test) != fold['test']['n_origins'] or test.empty:
            raise ValueError('Frozen origin counts differ')
        spec = json.loads(next(r for r in selected if r['outer_fold'] == fold['outer_fold'])['selected_candidate_spec'])
        model, scaler = fit_estimator('ridge', spec, train[SENSOR_FEATURES].to_numpy(), train.target_mg_dl.to_numpy())
        manifest['fits_completed'] += 1
        joblib.dump((model, scaler), local/f'model_{pid:03d}.joblib')
        predictor = lambda x: predict_estimator(model, scaler, x)
        test['base_prediction'] = predictor(test[SENSOR_FEATURES].to_numpy())
        reproduction.append(dict(participant_id=pid, train_participants=fold['train']['participants'], candidate=spec,
                                 n_predictions=len(test), fit_count=1, reference_kind='NEW',
                                 training_origin_sha256=digest_ids(train.origin_id), feature_order=SENSOR_FEATURES))
        stream = pd.read_csv(project/f'data/processed/stage2/observations/p{pid:03d}.csv', parse_dates=['event_time'],
                             float_precision='round_trip').set_index('event_time')
        anchor = stream.index[stream.valid][0]
        part = partition_origins(test, anchor)
        partitions.append(part)
        offset_rows = part[part.partition.eq('offset')]
        cal = part[part.partition.eq('calibration')]
        later = part[part.partition.eq('evaluation')]
        offset, reason = fit_offset(offset_rows.target_mg_dl, offset_rows.base_prediction)
        if len(later) < 100:
            raise ValueError('Stage5 insufficient later evaluation; no participant silently dropped')
        adequacy.append(dict(participant_id=pid, anchor=anchor.isoformat(), n_offset=len(offset_rows),
                             n_calibration=len(cal), n_evaluation=len(later), n_purged=int(part.partition.eq('purged').sum()),
                             offset_reason=reason, calibration_adequate=len(cal)>=100))
        p4 = partition_participant_origins(test, anchor)
        cal4 = p4[p4.partition.eq('calibration')]
        later4 = p4[p4.partition.eq('later_evaluation')]
        coverage = float(stream.valid.reindex(pd.date_range(anchor, periods=2880, freq='min'), fill_value=False).mean())
        ready4 = validate_calibration_gate(coverage, len(cal4), len(later4))
        off4, _ = fit_offset(cal4.target_mg_dl, cal4.base_prediction)
        if not ready4:
            off4 = None
        p4['adapted_prediction'] = p4.base_prediction+off4 if off4 is not None else np.nan
        stage4rows.append(p4)
        stage4info.append(dict(participant_id=pid, offset=off4, coverage=coverage, n_calibration=len(cal4),
                               n_later=len(later4), ready=ready4))
        stage4metrics.append(dict(participant_id=pid,n_later=len(later4),ready=ready4,
            unadapted_mae=float(np.abs(later4.target_mg_dl-later4.base_prediction).mean()),
            adapted_mae=float(np.abs(later4.target_mg_dl-later4.base_prediction-off4).mean()) if off4 is not None else np.nan))
        scheduled = stream.index[::5]
        scheduled = scheduled[scheduled-pd.Timedelta(minutes=60) >= anchor+pd.Timedelta(hours=48)]
        target = exact_targets(stream, scheduled)
        clean = forecast_stream(stream, scheduled, predictor)
        scenarios = {'clean': clean}
        start = gap_start(stream, anchor)
        for duration in (15, 30, 60, 120):
            if start+pd.Timedelta(minutes=duration+60) > stream.index[-1]:
                raise ValueError('Stream too short for frozen gap scenarios')
            scenarios[f'input_loss_{duration}m'] = forecast_stream(inject_gap(stream, start, duration), scheduled, predictor)
        for variant in ('sensor_only_unadapted', 'sensor_only_offset24h'):
            off = 0 if variant.endswith('unadapted') else offset
            for alpha in ('0.10', '0.05'):
                calibration = calibrate(np.abs(cal.target_mg_dl.to_numpy()-(cal.base_prediction.to_numpy()+(off or 0))), alpha)
                if off is None:
                    calibration = type(calibration)(len(cal), calibration.k, None, 'INSUFFICIENT_OFFSET_DATA')
                artifacts.append(dict(participant_id=pid, variant=variant, alpha=alpha, offset=off,
                                      offset_reason=reason, **asdict(calibration)))
                for scenario, points in scenarios.items():
                    rows = points.copy()
                    if off is None:
                        rows.loc[rows.point_reason.eq('OK'), 'point_reason'] = 'INSUFFICIENT_OFFSET_DATA'
                        rows['prediction'] = np.nan
                    else:
                        rows['prediction'] += off
                    rows['lower'] = rows.prediction-calibration.q if calibration.q is not None else np.nan
                    rows['upper'] = rows.prediction+calibration.q if calibration.q is not None else np.nan
                    rows['interval_reason'] = np.where(rows.point_reason.eq('OK'), calibration.reason, rows.point_reason)
                    rows['target'] = target
                    rows['target_time'] = rows.issue_time+pd.Timedelta(minutes=30)
                    rows['target_reason'] = np.where(np.isfinite(target), 'OK', 'TARGET_MISSING')
                    rows['scored_at'] = rows.target_time.where(rows.point_reason.eq('OK') & np.isfinite(target))
                    rows['clean_eligible'] = clean.point_reason.eq('OK').to_numpy() & np.isfinite(target)
                    rows['participant_id'], rows['variant'], rows['alpha'], rows['scenario'] = pid, variant, alpha, scenario
                    evaluations.append(rows)
        # Persist a durable fit counter after each fold; Stage4/5 never call fit.
        write(project.parent/'run-manifest.json', manifest)
    csv(local/'partition_predictions.csv', pd.concat(partitions, ignore_index=True))
    csv(local/'partition_adequacy.csv', pd.DataFrame(adequacy))
    write(local/'calibration_artifacts.json', artifacts)
    write(local/'model_reproduction.json', reproduction)
    csv(s4local/'references.csv', pd.concat(stage4rows, ignore_index=True))
    write(s4local/'offsets.json', stage4info)
    csv(project/'reports/new_experiment/stage4_per_participant.csv',pd.DataFrame(stage4metrics))
    evaluation = pd.concat(evaluations, ignore_index=True)
    csv(local/'evaluation.csv', evaluation)
    summaries = []
    for (scenario, variant, alpha), group in evaluation.groupby(['scenario', 'variant', 'alpha']):
        summary, _ = summarize(group, 14)
        summary['scenario'], summary['variant'], summary['alpha'] = scenario, variant, alpha
        summaries.append(summary)
    csv(project/'reports/new_experiment/aggregate_metrics.csv', pd.concat(summaries, ignore_index=True))
    # Compatible existing replay loader schema, explicitly NEW provenance.
    names = ['reports/stage2/split_manifest.json', 'configs/stage5_protocol.json'] + [
        f'data/processed/stage2/observations/p{p:03d}.csv' for p in split['eligible_participants']]
    write(local/'input_hashes.json', hashes(project, names))
    if manifest['fits_completed'] != 14:
        raise ValueError('Expected exactly fourteen fits')


def digest_ids(values):
    import hashlib
    return hashlib.sha256('\n'.join(map(str, values)).encode()).hexdigest()


def freeze(acquisition, output, code=ROOT):
    acquisition, output = Path(acquisition).resolve(), Path(output).resolve()
    separate(output, acquisition, code)
    plan = preflight(acquisition, code)
    output.mkdir(parents=True)
    try:
        names = source_files(code)
        source_hashes = hashes(code, names)
        for name in names:
            dest = relative(output/'source', name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(relative(code, name), dest)
        if hashes(output/'source', names) != source_hashes:
            raise ValueError('Source copy changed')
        amendment = dict(schema=1, kind='NEW_EXPERIMENT_IMPLEMENTATION_AMENDMENT', frozen_at_utc=stamp(),
                         original_design_unchanged=True, plan=plan, source_sha256=source_hashes,
                         source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip(),
                         dirty_state=subprocess.check_output(['git','status','--porcelain'],cwd=code,text=True).splitlines(),
                         expected_fits=14, stages='audit; unchanged Stage2 preparation; selected references once; Stage4; Stage5; independent verification',
                         scope='private noncommercial research; competition pending; no redistribution',
                         fixture_policy='Synthetic test bundles cannot pass production verifier or replay launcher')
        write(output/'amendment.json', amendment)
    except Exception as exc:
        write(output/'failure.json', dict(error=str(exc), at=stamp()))
        raise
    return digest(output/'amendment.json')


def execute(acquisition, amendment_path, expected_digest, output, authorization, *, _synthetic_fixture=False):
    acquisition, amendment_path, output = Path(acquisition).resolve(), Path(amendment_path).resolve(), Path(output).resolve()
    if digest(amendment_path) != expected_digest:
        raise ValueError('Amendment digest mismatch')
    amendment = load(amendment_path)
    if amendment['kind'] != 'NEW_EXPERIMENT_IMPLEMENTATION_AMENDMENT':
        raise ValueError('Wrong amendment kind')
    source = amendment_path.parent/'source'
    if hashes(source, amendment['source_sha256']) != amendment['source_sha256'] or hashes(ROOT, amendment['source_sha256']) != amendment['source_sha256']:
        raise ValueError('Implementation changed; freeze a new amendment')
    plan = preflight(acquisition, source)
    if plan != amendment['plan']:
        raise ValueError('Inputs/runtime changed since implementation freeze')
    if not (authorization.get('permits_processing_and_training') is True and authorization.get('private_noncommercial_only') is True and
            all(isinstance(authorization.get(k), str) and authorization[k].strip() for k in ('basis','reviewed_by','reviewed_at'))):
        raise ValueError('Explicit private noncommercial training authorization required')
    separate(output, acquisition, ROOT, amendment_path.parent)
    output.mkdir(parents=True)
    manifest = dict(run_id=uuid.uuid4().hex, state='PREPARING', kind='NEW_EXPERIMENT', synthetic_fixture=_synthetic_fixture,
                    started_at=stamp(), fits_completed=0, patient_replay_verified=False,
                    amendment_sha256=expected_digest, amendment_frozen_at=amendment['frozen_at_utc'],
                    authorization=authorization, runtime=runtime(), commands=[])
    try:
        project = output/'project'
        shutil.copytree(source, project)
        shutil.copy2(amendment_path, output/'amendment.json')
        meta_root = acquisition/'experiment-v1/input-project'
        for name in META:
            dest = relative(project, name); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(meta_root/name, dest)
        for name in plan['input_hashes']:
            dest = relative(project, name); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(acquisition/'inputs'/name, dest)
        if hashes(project, plan['input_hashes']) != plan['input_hashes']:
            raise ValueError('Input snapshot copy mismatch')
        if hashes(project, plan['metadata_hashes']) != plan['metadata_hashes']:
            raise ValueError('Metadata snapshot copy mismatch')
        if hashes(project, amendment['source_sha256']) != amendment['source_sha256']:
            raise ValueError('Source snapshot copy mismatch')
        original_split = load(project/META[1])
        dest = project/'reports/new_experiment/frozen_split.json'
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project/META[1], dest)
        write(output/'run-manifest.json', manifest)
        audit_project(project)
        command = [sys.executable, str(project/'scripts/prepare_stage2.py')]
        manifest['commands'].append(command)
        with (output/'stage2.log').open('w',encoding='utf-8') as log:
            subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT, check=True)
        manifest['state'] = 'GENERATING'
        generate_models(project, original_split, manifest, synthetic=_synthetic_fixture)
        manifest['state'] = 'GENERATED_NOT_VERIFIED'
        # These hashes must be recorded BEFORE any verifier deserializes models.
        files = {p.relative_to(project).as_posix(): digest(p) for p in project.rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
        write(output/'artifact-manifest.json', dict(kind='NEW_EXPERIMENT', synthetic_fixture=_synthetic_fixture,
              files=files, amendment_sha256=expected_digest, fits=manifest['fits_completed']))
        manifest['artifact_manifest_sha256'] = digest(output/'artifact-manifest.json')
        write(output/'run-manifest.json', manifest)
        command = [sys.executable, str(project/'scripts/verify_new_experiment.py'), '--bundle', str(output),
                   '--manifest-sha256', manifest['artifact_manifest_sha256']]
        manifest['commands'].append(command)
        with (output/'verification.log').open('w',encoding='utf-8') as log:
            subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT, check=True)
        result = load(output/'bundle-verification.json')
        if result.get('status')!='PASS' or result.get('artifact_manifest_sha256')!=manifest['artifact_manifest_sha256']:
            raise ValueError('Independent verifier did not confirm pinned bundle')
        manifest['state'] = 'SYNTHETIC_FIXTURE_VERIFIED' if _synthetic_fixture else 'BUNDLE_VERIFIED_REPLAY_NOT_RUN'
    except Exception as exc:
        manifest['state'], manifest['error'] = 'FAILED', type(exc).__name__+': '+str(exc)
        raise
    finally:
        manifest['finished_at'] = stamp()
        write(output/'run-manifest.json', manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquisition-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--freeze-amendment', action='store_true')
    mode.add_argument('--execute', action='store_true')
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--amendment', type=Path)
    parser.add_argument('--amendment-sha256')
    parser.add_argument('--authorization', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if not all([args.output_root,args.amendment,args.amendment_sha256,args.authorization]):
                raise ValueError('Execution requires new output root, pinned amendment and authorization')
            result = execute(args.acquisition_root,args.amendment,args.amendment_sha256,args.output_root,load(args.authorization))
            print(result['state'])
        elif args.freeze_amendment:
            if not args.output_root:
                raise ValueError('Freeze requires a new external --output-root')
            print('Amendment SHA256:', freeze(args.acquisition_root,args.output_root))
        else:
            result = preflight(args.acquisition_root)
            print(json.dumps(dict(ready=True, expected_fits=14, selection_searches=0, inputs=len(result['input_hashes']),
                                  runtime=result['runtime'], patient_execution=False),indent=2))
        return 0
    except Exception as exc:
        print(f'NEW experiment blocked: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
