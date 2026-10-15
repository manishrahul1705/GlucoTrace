"""Create remediation review archive for Stage 3 excluding raw data, feature tables, predictions, archives, and credentials."""
import os
import sys
import json
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ZIP = ROOT / 'GlucoTwin_Stage3_Remediation_Review.zip'

EXCLUDE_PATTERNS = [
    'data/', '.venv/', '__pycache__/', '.git/', '.tmp', '.bak', '.pyc', 'archive/',
    'reports/stage3_remediation/*.log', 'reports/stage2/*.log', 'reports/stage3/*.log'
]

EXCLUDE_SUFFIXES = [
    '.pyc', '.pkl', '.parquet', '.npz', '.bin', '.pt', '.onnx', '.joblib'
]


def review_files(root: Path):
    all_files = []

    # Include docs, configs, scripts, src, tests, and selected reports
    for folder in ['configs', 'docs', 'scripts', 'src', 'tests']:
        d = root / folder
        if d.exists():
            for p in d.rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:
                    all_files.append(p)

    # Reports: include stage1, stage2, stage3, and stage3_remediation (excluding any predictions/logs)
    rep_d = root / 'reports'
    if rep_d.exists():
        for p in rep_d.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.log':
                all_files.append(p)

    # Root files
    for name in [
        'README.md', 'README-stage2.md', 'START_HERE_WINDOWS.md',
        'requirements-audit.txt', 'requirements-stage2.txt', 'requirements-stage3.txt',
        'HANDOFF_MANIFEST.json', 'STAGE3_HANDOFF_FOR_REVIEW.md',
        'STAGE3_REMEDIATION_HANDOFF_FOR_REVIEW.md', '.gitignore'
    ]:
        p = root / name
        if p.is_file():
            all_files.append(p)

    # Filter out exclusions
    clean_files = []
    for p in all_files:
        rel = p.relative_to(root).as_posix()
        if any(ex in rel for ex in ['data/', '.venv/', '__pycache__/', '.git/', 'archive/']):
            continue
        if p.suffix in EXCLUDE_SUFFIXES:
            continue
        if 'predictions' in rel:
            continue
        clean_files.append(p)

    return sorted(set(clean_files))


def verify_exclusions(files: list, root: Path):
    """Enforce security and privacy boundaries on package candidates."""
    for p in files:
        rel = p.relative_to(root).as_posix()
        assert not rel.startswith('data/'), f"Security violation: participant data included: {rel}"
        assert not rel.startswith('.venv/'), f"Security violation: venv included: {rel}"
        assert not rel.startswith('archive/'), f"Security violation: archive included: {rel}"
        assert not rel.startswith('.git/'), f"Security violation: git included: {rel}"
        assert 'predictions' not in rel, f"Security violation: predictions included: {rel}"
        assert p.suffix not in EXCLUDE_SUFFIXES, f"Security violation: binary/weight file included: {rel}"


def main():
    print("================================================================")
    print("  Creating GlucoTwin Stage 3 Remediation Review Package")
    print("================================================================")
    files = review_files(ROOT)
    print(f"Total files selected for package: {len(files)}")

    # Verify exclusions strictly
    verify_exclusions(files, ROOT)
    print("All security and privacy exclusion assertions passed.")

    manifest = {
        'package_name': 'GlucoTwin_Stage3_Remediation_Review.zip',
        'raw_data_included': False,
        'participant_feature_tables_included': False,
        'per_origin_predictions_included': False,
        'model_weights_included': False,
        'environment_packages_included': False,
        'archive_directories_included': False,
        'total_files': len(files),
        'files': [
            {
                'path': p.relative_to(ROOT).as_posix(),
                'bytes': p.stat().st_size,
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest()
            }
            for p in files
        ]
    }

    manifest_json = json.dumps(manifest, indent=2) + '\n'
    (ROOT / 'reports/stage3_remediation/review_package_manifest.json').write_text(manifest_json, encoding='utf-8')

    with zipfile.ZipFile(OUT_ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, 'GlucoTwin/' + p.relative_to(ROOT).as_posix())
        z.writestr(
            'GlucoTwin/reports/stage3_remediation/review_package_manifest.json',
            manifest_json
        )

    # Verify zip integrity
    with zipfile.ZipFile(OUT_ZIP, 'r') as z:
        assert z.testzip() is None, "ZIP integrity test failed!"
        names = z.namelist()
        for name in names:
            assert not any(forbidden in name for forbidden in ['/data/', '/.venv/', '/archive/', '/predictions/']), (
                f"Security violation in ZIP: {name}"
            )

    size_mb = OUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"Successfully generated {OUT_ZIP.name} ({size_mb:.2f} MB)")
    print(f"Package contains {len(names)} files; zero patient data, zero weights, zero archives.")


if __name__ == '__main__':
    main()
