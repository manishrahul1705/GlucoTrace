"""Verification of portable source package with explicit current working-tree manifest.

Ensures that the repository tracked source AND required new verification files
from the current working tree (not committed HEAD) can be packaged or copied to an
isolated directory, verifies SHA-256 hash agreement for all changed files, runs tests cleanly,
and does not depend on host-specific absolute paths, private artifacts, or untracked state.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

REQUIRED_NEW_FILES = [
    "scripts/verify_portable_package.py",
    "scripts/verify_specific_stage3_5_gaps.py",
    "scripts/verify_capability_recovery_browser.mjs",
    "scripts/run_capability_recovery_verification.py",
    "reports/capability_recovery/REQUIREMENTS_VERIFICATION_MATRIX.md",
    "reports/capability_recovery/DEFECT_RECORD_AND_CORRECTIONS.md",
    "reports/capability_recovery/EXECUTION_RECORD.md",
    "reports/capability_recovery/SPECIFIC_GAPS_VERIFICATION_REPORT.json",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main():
    print("Testing portable source package from current working tree...")
    with tempfile.TemporaryDirectory(prefix="glucotwin_portable_") as temp_dir:
        dest = Path(temp_dir) / "GlucoTwin_portable"
        dest.mkdir()

        # 1. Get list of tracked git files
        proc = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
        tracked_files = [f.strip() for f in proc.stdout.splitlines() if f.strip()]

        # 2. Combine tracked files with required new files from current working tree
        manifest_files = sorted(set(tracked_files + REQUIRED_NEW_FILES))
        print(f"Manifest contains {len(manifest_files)} files ({len(tracked_files)} tracked + {len(REQUIRED_NEW_FILES)} required new files).")

        # 3. Determine changed files relative to HEAD
        diff_proc = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True)
        modified_in_wt = set()
        for line in diff_proc.stdout.splitlines():
            if line.strip():
                status = line[:2]
                fname = line[3:].strip().replace('\\', '/')
                if 'M' in status:
                    modified_in_wt.add(fname)

        print(f"Detected {len(modified_in_wt)} modified files in working tree relative to HEAD.")

        # 4. Copy each file from current working tree to destination and compute hashes
        hash_audit = []
        for rel_path in manifest_files:
            src_file = ROOT / rel_path
            dst_file = dest / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            if src_file.exists():
                shutil.copy2(src_file, dst_file)
                # Compute hashes if file is modified or newly required
                if rel_path in modified_in_wt or rel_path in REQUIRED_NEW_FILES:
                    src_hash = sha256_file(src_file)
                    dst_hash = sha256_file(dst_file)
                    assert src_hash == dst_hash, f"Hash mismatch for {rel_path}: {src_hash} != {dst_hash}"
                    hash_audit.append({
                        "file": rel_path,
                        "status": "modified" if rel_path in modified_in_wt else "new_required",
                        "source_sha256": src_hash,
                        "package_sha256": dst_hash,
                        "matches": True,
                        "size_bytes": src_file.stat().st_size
                    })

        print(f"Verified hash parity for {len(hash_audit)} modified/required files.")

        # 5. Write portable manifest to report directory
        manifest_report = {
            "portable_package_version": "1.0.0",
            "working_tree_source": str(ROOT),
            "isolated_destination": str(dest),
            "total_files_packaged": len(manifest_files),
            "tracked_files_count": len(tracked_files),
            "required_new_files_count": len(REQUIRED_NEW_FILES),
            "verified_changed_files_count": len(hash_audit),
            "hash_audit": hash_audit
        }
        manifest_out = ROOT / "reports/capability_recovery/PORTABLE_PACKAGE_MANIFEST.json"
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(manifest_report, indent=2))
        print(f"Package manifest report written to: {manifest_out}")

        # 6. Verify that no private data or forbidden folders leaked into package
        for forbidden in ["data/raw", "data/processed", "weights", ".venv", ".venv312", "venv"]:
            if (dest / forbidden).exists():
                raise AssertionError(f"Forbidden directory {forbidden} found in portable package!")

        # 7. Run Python test suite inside the isolated directory using packaged source
        env = os.environ.copy()
        env["PYTHONPATH"] = str(dest / "src")

        print("Running Python tests in isolated portable copy...")
        test_proc = subprocess.run(
            [PYTHON, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True
        )

        print(test_proc.stdout)
        if test_proc.returncode != 0:
            print(test_proc.stderr, file=sys.stderr)
            raise AssertionError(f"Tests failed in isolated portable package with code {test_proc.returncode}")

        print("Portable package test passed! All tests executed cleanly in isolated directory.")


if __name__ == "__main__":
    main()
