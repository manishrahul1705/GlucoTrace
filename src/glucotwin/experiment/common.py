"""Non-executable manifests and input provenance for the NEW experiment route."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import platform
import subprocess
import importlib.metadata
import os

ROOT = Path(__file__).resolve().parents[3]
META = ['reports/stage1/provenance_manifest.json', 'reports/stage2/split_manifest.json',
        'reports/stage3_remediation/selected_candidates.csv']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda: stream.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def relative(root, name):
    p = Path(name.replace('\\', '/'))
    if p.is_absolute() or ':' in str(p) or '..' in p.parts:
        raise ValueError('Unsafe manifest path')
    result = (root/p).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Manifest path escapes root')
    return result


def separate(output, *roots):
    if any(output == r or output.is_relative_to(r) or r.is_relative_to(output) for r in roots):
        raise ValueError('Output must be separate from source, acquisition and amendment roots')
    if output.exists():
        raise ValueError('Existing output root refused')


def source_files(root=ROOT):
    return load(root/'configs/source_package.json')['required_source_files']


def hashes(root, names):
    return {name: digest(relative(root, name)) for name in names}


def selections(project):
    # Reuse the existing metadata-only fold gate, not a scientific CLI.
    import importlib.util
    spec = importlib.util.spec_from_file_location('frozen_regeneration', project/'scripts/regenerate_replay.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    split = load(project/META[1])
    with (project/META[2]).open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    module.validate_folds(split, rows)
    return split, [r for r in rows if r['family'] == 'ridge' and r['variant'] == 'sensor_only']


def runtime():
    return dict(python=platform.python_version(), threading={n:os.getenv(n) for n in
                ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')},
                **{n: importlib.metadata.version(n) for n in ('numpy', 'pandas', 'scikit-learn', 'scipy', 'joblib')})


def preflight(acquisition, code=ROOT):
    """Hash-only private preflight. No patient table is parsed or estimator fitted."""
    acquisition, code = Path(acquisition).resolve(), Path(code).resolve()
    verification = load(acquisition/'verification-final.json')
    design = acquisition/'experiment-v1'
    freeze = load(design/'protocol-freeze.json')
    verified = load(design/'verified-input-freeze.json')
    if digest(design/'protocol.json') != freeze['protocol_sha256'] or verified['protocol_sha256'] != freeze['protocol_sha256']:
        raise ValueError('Original design freeze mismatch')
    if digest(acquisition/'verification-final.json') != verified['verification_sha256']:
        raise ValueError('Acquisition verification record changed')
    if verification['status'] != 'VERIFIED' or len(verification['checks']) != 54 or verification['mismatches']:
        raise ValueError('Incomplete acquisition verification')
    provenance = load(design/'input-project'/META[0])
    expected = {e['path']: e['sha256'] for e in provenance['extracted']+provenance['downloads']}
    if expected != verified['input_sha256'] or len(expected) != 54:
        raise ValueError('Input manifest disagreement')
    if any(not e['match'] or expected.get(e['path']) != e['sha256'] for e in verification['checks']):
        raise ValueError('Input verification disagreement')
    actual = hashes(acquisition/'inputs', expected)
    if actual != expected:
        raise ValueError('Input bytes changed')
    archive = acquisition/'download/CGMacros_dateshifted365.s3.zip'
    if digest(archive) != verified['archive_sha256'] or archive.stat().st_size != provenance['archive_size_bytes']:
        raise ValueError('Archive changed')
    project = design/'input-project'
    split, selected = selections(project)
    original = load(design/'protocol.json')
    # All original scientific source/config contracts remain frozen. Manifest can
    # add the new entrypoints; the new implementation is frozen separately.
    for name, expected_hash in original['frozen_source_sha256'].items():
        if name.startswith(('src/', 'configs/stage', 'scripts/prepare_stage2.py')):
            if digest(relative(code, name)) != expected_hash:
                raise ValueError('Original scientific source changed: '+name)
    for name in META:
        if digest(project/name) != original['historical_metadata_sha256'][name]:
            raise ValueError('Frozen metadata changed: '+name)
    return dict(acquisition=str(acquisition), original_protocol_sha256=freeze['protocol_sha256'],
                input_hashes=actual, metadata_hashes=hashes(project, META),
                expected_fits=14, model_reselection=False, selected=selected,
                participants=split['eligible_participants'], runtime=runtime(),
                original_records={str(p.relative_to(acquisition).as_posix()): digest(p) for p in
                    [design/'protocol.json', design/'protocol-freeze.json', design/'verified-input-freeze.json',
                     acquisition/'verification-final.json']})
