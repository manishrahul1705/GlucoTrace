"""Copy a trusted private bundle and context without modifying either bundle.

Destination must be a fresh private directory outside the checkout. Choose a
durable, non-shared location; the tool cannot detect cloud backup policies.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from glucotwin.experiment.common import digest, load, stamp, write, separate
from glucotwin.experiment.verify import check_hashes, verify


def inventory(root):
    entries = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            raise ValueError('Linked path refused: ' + str(p))
        if p.is_file():
            entries[p.relative_to(root).as_posix()] = dict(size=p.stat().st_size, sha256=digest(p))
        elif p.is_dir():
            entries[p.relative_to(root).as_posix() + '/'] = dict(directory=True)
    return entries


def preserve(source, destination, trusted, contexts=()):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    separate(destination, source, Path(__file__).resolve().parents[1])
    check_hashes(source, trusted)
    run = load(source / 'run-manifest.json')
    if run['artifact_manifest_sha256'] != trusted or run['fits_completed'] != 14:
        raise ValueError('Trusted execution record disagreement')
    before = inventory(source)
    destination.mkdir(parents=True, exist_ok=False)
    record = dict(started_at=stamp(), source=str(source), destination=str(destination),
                  artifact_manifest_sha256=trusted, status='COPYING', inventory=before)
    try:
        shutil.copytree(source, destination / 'bundle')
        if inventory(source) != before or inventory(destination / 'bundle') != before:
            raise ValueError('Copied relative paths, sizes or SHA256 differ')
        context_records = []
        for i, raw in enumerate(contexts):
            src = Path(raw).resolve()
            dst = destination / 'context' / f'{i:02d}-{src.name}'
            dst.parent.mkdir(exist_ok=True)
            if src.is_dir():
                expected = inventory(src)
                shutil.copytree(src, dst)
                if inventory(src) != expected or inventory(dst) != expected:
                    raise ValueError('Context copy mismatch')
            else:
                expected = dict(size=src.stat().st_size, sha256=digest(src))
                shutil.copy2(src, dst)
                if dst.stat().st_size != expected['size'] or digest(dst) != expected['sha256'] or digest(src) != expected['sha256']:
                    raise ValueError('Context file mismatch')
            context_records.append(dict(source=str(src), copied=str(dst), inventory=expected))
        record['context'] = context_records
        result = verify(destination / 'bundle', trusted)
        write(destination / 'durable-bundle-verification.json', result)
        if inventory(destination / 'bundle') != before or inventory(source) != before:
            raise ValueError('Bundle changed during independent verification')
        record['status'] = 'PASS'
    except Exception as exc:
        record['status'], record['error'] = 'FAIL', repr(exc)
        raise
    finally:
        record['finished_at'] = stamp()
        write(destination / 'migration.json', record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--context', type=Path, action='append', default=[])
    a = p.parse_args()
    result = preserve(a.source, a.destination, a.manifest_sha256, a.context)
    print('Durable copy and independent verification:', result['status'])


if __name__ == '__main__':
    main()
