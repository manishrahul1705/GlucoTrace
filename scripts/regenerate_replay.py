"""Isolated, selected-only regeneration. Default: read-only preflight, no training.

No downloader, model reselection, or Stage3 benchmark invocation. Frozen Stage3
and Stage4 reference files remain prerequisites, never self-generated evidence.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

CODE_ROOT = Path(__file__).resolve().parents[1]
METADATA = ['configs/stage2_protocol.json', 'configs/stage3_run.json',
            'configs/stage4_protocol.json', 'configs/stage5_protocol.json',
            'reports/stage2/split_manifest.json', 'reports/stage2/freeze_manifest.json',
            'reports/stage2/stage1_preservation_manifest.json']
REFERENCES = ['reports/stage3_remediation/selected_candidates.csv',
              'data/processed/stage3_remediation/predictions/test_predictions.csv',
              'data/processed/stage4/predictions/later_evaluation_predictions.csv',
              'data/processed/stage4/predictions/calibration_predictions.csv',
              'data/processed/stage4/patient_offsets.csv',
              'reports/stage4/aggregate_metrics.csv']
COMPARISONS = ['docs/stage1/usable_windows.csv', 'docs/stage1/event_feasibility.csv']


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe(root, relative):
    relative = relative.replace('\\', '/')
    if ':' in relative or relative.startswith('/') or any(p in ('', '.', '..') for p in relative.split('/')):
        raise ValueError('Unsafe prerequisite path')
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Prerequisite escapes input root')
    return path


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def validate_folds(split, selections):
    """Metadata-only exclusions; never examine later targets for selection."""
    pids = split['eligible_participants']
    folds = split['folds']
    if len(pids) != 14 or len(set(pids)) != 14 or len(folds) != 14:
        raise ValueError('Expected fourteen frozen outer folds')
    selected = [r for r in selections if r['family'] == 'ridge' and r['variant'] == 'sensor_only']
    if len(selected) != 14:
        raise ValueError('Expected exactly fourteen frozen sensor-only Ridge selections')
    held_out = []
    for fold in folds:
        test, train = set(fold['test']['participants']), set(fold['train']['participants'])
        if len(test) != 1 or train != set(pids) - test:
            raise ValueError('Outer held-out training exclusion failed')
        held_out.extend(test)
        if len(fold['inner_folds']) != 3:
            raise ValueError('Expected three frozen inner folds')
        for inner in fold['inner_folds']:
            a, b = set(inner['train']['participants']), set(inner['validation']['participants'])
            if a & b or (a | b) != train or test & (a | b):
                raise ValueError('Inner fold exclusion failed')
        matches = [r for r in selected if r['outer_fold'] == fold['outer_fold']]
        if len(matches) != 1 or int(matches[0]['held_out_pid']) not in test:
            raise ValueError('Frozen selection does not match held-out fold')
        spec = json.loads(matches[0]['selected_candidate_spec'])
        if type(spec.get('alpha')) not in (int, float) or not math.isfinite(spec['alpha']) or spec['alpha'] <= 0:
            raise ValueError('Invalid frozen Ridge candidate')
    if sorted(held_out) != sorted(pids):
        raise ValueError('Outer held-out coverage failed')
    return 14


def preflight(input_root, code_root=None):
    root, code = Path(input_root).resolve(), Path(code_root or CODE_ROOT).resolve()
    result = dict(input_root=str(root), code_root=str(code), ready=False, issues=[],
                  files={}, upstream_trace={}, expected_stage2={}, steps=[], selected_refits=0)

    def check(relative, expected=None, normalized=False, required=True):
        path = safe(root, relative)
        present = path.is_file()
        actual = sha(path) if present else None
        observed = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() if present and normalized else actual
        reason = 'MISSING' if not present else 'INCOMPATIBLE' if expected is not None and observed != expected else 'VERIFIED'
        record = dict(status=reason, sha256=actual, expected_sha256=expected,
                      basis='LF normalized' if normalized else 'exact bytes')
        if required:
            result['files'][relative] = record
            if reason != 'VERIFIED':
                result['issues'].append(f'{reason}: {relative}')
        else:
            result['upstream_trace'][relative] = record
        return reason == 'VERIFIED'

    try:
        for rel in METADATA:
            check(rel)
        if result['issues']:
            return result
        load = lambda rel: json.loads(safe(root, rel).read_text(encoding='utf-8-sig'))
        s2, s3, s4 = (load(p) for p in METADATA[:3])
        split, freeze, stage1 = (load(p) for p in METADATA[4:])
        for rel in METADATA[:4]:
            check(rel, sha(safe(code, rel)))  # no silent protocol/config amendments
        expected = {p.replace('\\', '/'): h for p, h in freeze['files'].items()}
        provenance = s2['dataset']['provenance_manifest']
        check(provenance, s2['dataset']['provenance_sha256'])
        if not safe(root, provenance).is_file():
            return result
        prov = load(provenance)
        pids = split['eligible_participants']
        prepared = ['data/processed/stage2/sensor_only.csv', 'data/processed/stage2/sensor_plus_baseline.csv',
                    'reports/stage2/personalization_coverage.csv', 'reports/stage2/split_manifest.json']
        prepared += [f'data/processed/stage2/{family}/p{pid:03d}.csv'
                     for family in ['observations', 'personalization'] for pid in pids]
        reuse = all(safe(root, rel).is_file() for rel in prepared)
        result['stage2_mode'] = 'reuse' if reuse else 'prepare'
        stage1_hashes = {p.replace('\\', '/'): h for p, h in stage1.items()}
        for rel in COMPARISONS:
            check(rel, stage1_hashes.get(rel), required=not reuse)
            if not reuse and rel not in stage1_hashes:
                result['issues'].append(f'Missing historical Stage1 comparison digest: {rel}')
        for entry in prov['extracted'] + prov['downloads']:
            check(entry['path'], entry['sha256'], required=not reuse)
        for rel in prepared:
            if rel not in expected:
                result['issues'].append(f'Missing historical Stage2 digest: {rel}')
            result['expected_stage2'][rel] = expected.get(rel)
            if reuse:
                check(rel, expected.get(rel))
        for rel in REFERENCES:
            check(rel)
        for rel, digest in s4['input_hashes'].items():
            # Stage5 uses this exact normalized historical gate. Stage2-generated
            # inputs are checked after preparation if not available yet.
            if not reuse and rel in prepared:
                continue
            check(rel, digest, normalized=True)
        checkpoint = s3['checkpoint_references']
        check('reports/stage2/split_manifest.json', checkpoint['split_manifest_sha256'])
        check('configs/stage2_protocol.json', checkpoint['stage2_protocol_sha256'])
        if safe(root, REFERENCES[0]).is_file():
            with safe(root, REFERENCES[0]).open(newline='', encoding='utf-8') as stream:
                result['selected_refits'] = validate_folds(split, list(csv.DictReader(stream)))
        result['steps'] = ([] if reuse else ['scripts/prepare_stage2.py']) + ['scripts/run_stage5.py', 'scripts/verify_stage5.py']
        result['ready'] = not result['issues']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['issues'].append(f'Invalid prerequisite metadata: {type(exc).__name__}: {exc}')
    return result


def _run(command, cwd, log):
    with log.open('w', encoding='utf-8') as stream:
        subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)


def execute(plan, output_root, authorization, executor=None):
    """Execute unchanged frozen scripts only after fresh preflight and attestation.

    executor injection exists for synthetic orchestration tests, never a CLI
    patient/fixture mode. No original model object is loaded by this runner.
    """
    if not plan['ready']:
        raise ValueError('Preflight is blocked; no training started')
    if not (authorization.get('permits_processing_and_training') is True and
            all(isinstance(authorization.get(k), str) and authorization[k].strip()
                for k in ['intended_use', 'basis', 'reviewed_by', 'reviewed_at'])):
        raise ValueError('Explicit intended-use permission/provenance attestation is required')
    source, code, output = Path(plan['input_root']), Path(plan['code_root']), Path(output_root).resolve()
    if any(output == p or output.is_relative_to(p) or p.is_relative_to(output) for p in [source, code]):
        raise ValueError('Output root must be separate from input and source roots')
    output.mkdir(parents=True, exist_ok=False)
    work = output / 'project'
    manifest = dict(run_id=uuid.uuid4().hex, state='PREPARING', new_execution=True,
                    started_at=datetime.now(timezone.utc).isoformat(), commands=[], authorization=authorization,
                    selected_refits=14, model_reselection=False, source_root=str(code), patient_replay_verified=False)
    run = executor or _run
    try:
        selected = json.loads((code / 'configs/source_package.json').read_text())['required_source_files']
        source_hashes = {rel: sha(safe(code, rel)) for rel in selected}
        for rel in selected:
            dest = safe(work, rel); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe(code, rel), dest)
            if sha(dest) != source_hashes[rel]:
                raise ValueError('Source snapshot changed during copy')
        manifest['source_sha256'] = source_hashes
        for rel, entry in plan['files'].items():
            path = safe(source, rel)
            if sha(path) != entry['sha256']:
                raise ValueError(f'Input changed since preflight: {rel}')
            dest = safe(work, rel); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            if sha(dest) != entry['sha256']:
                raise ValueError(f'Input copy mismatch: {rel}')
        manifest['input_sha256'] = {r: e['sha256'] for r, e in plan['files'].items()}
        identity = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=code, capture_output=True, text=True)
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=code, capture_output=True, text=True)
        manifest.update(source_commit=identity.stdout.strip() if identity.returncode == 0 else None,
                        source_dirty_state=status.stdout.splitlines() if status.returncode == 0 else None)
        import importlib.metadata
        manifest['runtime'] = dict(python=sys.version, **{p: importlib.metadata.version(p)
            for p in ['numpy', 'pandas', 'scikit-learn', 'scipy', 'joblib']})
        write(output / 'run-manifest.json', manifest)
        for script in plan['steps']:
            if script == 'scripts/run_stage5.py':
                # Preserve original Stage2 byte checks even when it was just
                # regenerated; do not replace its expected hashes with new ones.
                for rel, digest in plan['expected_stage2'].items():
                    if not digest or sha(safe(work, rel)) != digest:
                        raise ValueError(f'Stage2 historical hash mismatch: {rel}')
                for rel, digest in json.loads((work / 'configs/stage4_protocol.json').read_text())['input_hashes'].items():
                    if hashlib.sha256(safe(work, rel).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != digest:
                        raise ValueError(f'Historical Stage4 input mismatch: {rel}')
                local = work / 'data/processed/stage5'
                # Authentic NEW execution identity/freeze, never a fabricated
                # original timestamp. Existing run_stage5 reads these records.
                write(local / 'starting_state.json', dict(head=manifest['source_commit'],
                    status=manifest['source_dirty_state'], initial_file_hashes=source_hashes,
                    regeneration_run_id=manifest['run_id'], new_execution=True))
                write(local / 'protocol_freeze.json', dict(protocol_sha256=sha(work / 'configs/stage5_protocol.json'),
                    recorded_before_stage5_evaluation=True, frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                    regeneration_run_id=manifest['run_id'], new_execution=True))
            if script == 'scripts/verify_stage5.py':
                # Only freshly generated local outputs, pinned before the
                # existing verifier deserializes the generated model objects.
                local = work / 'data/processed/stage5'
                models = list(local.glob('model_*.joblib'))
                if len(models) != 14:
                    raise ValueError('Expected fourteen newly generated model files')
                manifest['generated_sha256'] = {str(p.relative_to(work).as_posix()): sha(p)
                    for p in local.rglob('*') if p.is_file()}
                write(output / 'run-manifest.json', manifest)
            command = [sys.executable, str(work / script)]
            manifest['commands'].append(command)
            run(command, work, output / (Path(script).stem + '.log'))
        verification = json.loads((work / 'reports/stage5/verification.json').read_text())
        if verification.get('status') != 'PASS':
            raise ValueError('Existing Stage5 verification did not pass')
        for rel, digest in manifest['generated_sha256'].items():
            if sha(safe(work, rel)) != digest:
                raise ValueError('Generated artifact changed during verification')
        manifest['state'] = 'BUNDLE_VERIFIED_REPLAY_NOT_RUN'
        manifest['patient_replay_verified'] = False
        manifest['output_sha256'] = {str(p.relative_to(work).as_posix()): sha(p)
            for folder in ['data/processed/stage5', 'reports/stage5']
            for p in (work / folder).rglob('*') if p.is_file()}
    except Exception:
        manifest['state'] = 'FAILED'
        raise
    finally:
        write(output / 'run-manifest.json', manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, default=CODE_ROOT)
    parser.add_argument('--output-root', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Default; no copy, freeze, model load or fitting')
    mode.add_argument('--execute', action='store_true')
    parser.add_argument('--authorization', type=Path, help='Reviewed intended-use/provenance attestation JSON; never inferred from public availability')
    args = parser.parse_args(argv)
    try:
        plan = preflight(args.input_root)
        if not args.execute:
            if args.output_root:
                output = args.output_root.resolve()
                if any(output == p or output.is_relative_to(p) or p.is_relative_to(output)
                       for p in [args.input_root.resolve(), CODE_ROOT]):
                    raise ValueError('Preflight output must be separate from input/source roots')
                output.mkdir(parents=True, exist_ok=False)
                write(output / 'preflight.json', plan)
            print(json.dumps(dict(ready=plan['ready'], selected_refits=plan['selected_refits'],
                                  stage2_mode=plan.get('stage2_mode'), steps=plan['steps'], issues=plan['issues']), indent=2))
            return 0 if plan['ready'] else 2
        if not args.output_root or not args.authorization:
            raise ValueError('--execute requires a new --output-root and --authorization')
        # Re-evaluate metadata immediately before accepting execution.
        execute(plan, args.output_root, json.loads(args.authorization.read_text(encoding='utf-8')))
        print('Bundle verifier passed; actual replay remains a separate check.')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Regeneration failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
