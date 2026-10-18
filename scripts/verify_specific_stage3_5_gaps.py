"""Verification script for the 6 specific Stage 3-5 checks requested in Gap 4.

1. Fresh dependency installation in isolation.
2. Actual HTTP tests for private mode disabled and enabled with missing artifacts.
3. Patient-export rejection through HTTP endpoint using clearly labeled fixture.
4. Five actual synthetic export downloads.
5. Historical inspector cutoff across polling.
6. All four dropout durations.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from glucotwin.stage6.api import create_app, Manager
from glucotwin.stage6.sources import synthetic, Reading
from glucotwin.stage6.engine import Session

EXPORT_DIR = ROOT / 'reports/capability_recovery/export_verification'


def test_1_fresh_dependency_installation():
    print("\n--- Check 1: Fresh Dependency Installation in Isolation ---")
    with tempfile.TemporaryDirectory(prefix="glucotwin_fresh_install_") as temp_dir:
        venv_dir = Path(temp_dir) / "test_venv"
        print(f"Creating isolated virtual environment at {venv_dir}...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        pip_exe = venv_dir / "Scripts" / "pip.exe"
        cache_dir = r"c:\users\manish\appdata\local\pip\cache"

        print("Installing requirements-stage6.txt from local wheel cache...")
        cmd = [str(pip_exe), "install", "--cache-dir", cache_dir, "-r", str(ROOT / "requirements-stage6.txt")]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("Pip install stdout:", res.stdout)
            print("Pip install stderr:", res.stderr)
            raise AssertionError(f"Fresh dependency installation failed with code {res.returncode}")

        print("Running pip check in isolated venv...")
        check_proc = subprocess.run([str(pip_exe), "check"], capture_output=True, text=True)
        print("Pip check output:", check_proc.stdout.strip())
        if check_proc.returncode != 0:
            raise AssertionError(f"Pip check failed: {check_proc.stderr}")

        print("Verifying core module imports in isolated venv...")
        python_exe = venv_dir / "Scripts" / "python.exe"
        import_proc = subprocess.run([
            str(python_exe), "-c",
            "import fastapi, uvicorn, pydantic, pandas, numpy, sklearn; print('All core dependencies imported cleanly!')"
        ], capture_output=True, text=True)
        print(import_proc.stdout.strip())
        if import_proc.returncode != 0:
            raise AssertionError(f"Import check failed: {import_proc.stderr}")

    return {"status": "PASSED", "message": "Isolated virtual environment successfully built and verified with pip check."}


def test_2_http_private_mode():
    print("\n--- Check 2: Actual HTTP Tests for Private Mode (Disabled & Enabled with Missing Artifacts) ---")
    results = {}
    with tempfile.TemporaryDirectory() as td:
        runtime = Path(td) / "runtime"
        empty_root = Path(td) / "empty_root"
        empty_root.mkdir()

        # Part A: local_enabled=False
        app_disabled = create_app(root=empty_root, runtime=runtime, local_enabled=False, run_clock=False)
        with TestClient(app_disabled) as client:
            resp = client.post("/api/replay/sessions", json={"source_id": "local-unavailable"})
            print("Mode disabled HTTP status:", resp.status_code)
            print("Mode disabled detail:", resp.json())
            assert resp.status_code == 409
            assert "LOCAL_MODE_DISABLED" in resp.json()["detail"]
            results["disabled"] = resp.json()["detail"]

        # Part B: local_enabled=True with missing Stage 5 artifacts
        app_enabled_missing = create_app(root=empty_root, runtime=runtime, local_enabled=True, run_clock=False)
        with TestClient(app_enabled_missing) as client:
            resp = client.post("/api/replay/sessions", json={"source_id": "local-unavailable"})
            print("Mode enabled missing artifacts HTTP status:", resp.status_code)
            print("Mode enabled missing artifacts detail:", resp.json())
            assert resp.status_code == 409
            assert "LOCAL_ARTIFACTS_UNAVAILABLE" in resp.json()["detail"]
            results["enabled_missing"] = resp.json()["detail"]

    return {"status": "PASSED", "details": results}


def test_3_patient_export_rejection():
    print("\n--- Check 3: Patient Export Rejection Through HTTP Endpoint (Fixture) ---")
    with tempfile.TemporaryDirectory() as td:
        runtime = Path(td) / "runtime"
        app = create_app(root=ROOT, runtime=runtime, local_enabled=False, run_clock=False)
        with TestClient(app) as client:
            # Create a regular synthetic session first
            s_resp = client.post("/api/replay/sessions", json={"source_id": "synthetic-dawn", "start": "full"}).json()
            session_id = s_resp["session_id"]
            generation = s_resp["generation"]

            # Mutate the in-memory session to represent a labeled fixture local session
            manager = app.state.manager
            with manager.lock:
                sess = manager.get(session_id)
                sess.source = replace(sess.source, mode="local")

            # Verify that export is rejected with HTTP 403 PATIENT_EXPORT_DISABLED for all kinds
            rejections = {}
            for kind in ["configuration", "readings", "forecasts", "scores", "summary"]:
                exp_resp = client.post(f"/api/replay/sessions/{session_id}/export", json={
                    "generation": generation,
                    "kind": kind
                })
                print(f"Export kind '{kind}' response: {exp_resp.status_code} - {exp_resp.text.strip()}")
                assert exp_resp.status_code == 403
                assert "PATIENT_EXPORT_DISABLED" in exp_resp.json()["detail"]
                rejections[kind] = exp_resp.status_code

    return {"status": "PASSED", "rejections": rejections}


def test_4_five_synthetic_export_downloads():
    print("\n--- Check 4: Five Actual Synthetic Export Downloads & Interval Bounds Audit ---")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        runtime = Path(td) / "runtime"
        app = create_app(root=ROOT, runtime=runtime, local_enabled=False, run_clock=False)
        with TestClient(app) as client:
            s_resp = client.post("/api/replay/sessions", json={"source_id": "synthetic-dawn", "start": "warm"}).json()
            session_id = s_resp["session_id"]
            generation = s_resp["generation"]

            # Step 10 times to accumulate forecasts and scores
            for i in range(10):
                client.post(f"/api/replay/sessions/{session_id}/control", json={
                    "generation": generation,
                    "request_id": f"step_{i}",
                    "action": "step"
                })

            exports_info = {}
            for kind in ["configuration", "readings", "forecasts", "scores", "summary"]:
                resp = client.post(f"/api/replay/sessions/{session_id}/export", json={
                    "generation": generation,
                    "kind": kind
                })
                assert resp.status_code == 200
                content = resp.content
                ext = "json" if resp.headers.get("content-type") == "application/json" else "csv"
                out_path = EXPORT_DIR / f"glucotwin-synthetic-{kind}.{ext}"
                out_path.write_bytes(content)
                print(f"Exported {kind}: {len(content)} bytes -> {out_path.name}")

                if kind == "summary":
                    data = json.loads(content.decode("utf-8"))
                    assert data["summary"]["interval_available"] == 0
                    assert data["summary"]["empirical_coverage"] is None
                    assert data["summary"]["scheduled"] > 0
                    assert data["summary"]["issued"] > 0
                    exports_info["summary"] = {
                        "interval_available": data["summary"]["interval_available"],
                        "empirical_coverage": data["summary"]["empirical_coverage"],
                        "scheduled": data["summary"]["scheduled"],
                        "issued": data["summary"]["issued"]
                    }
                elif kind == "forecasts":
                    lines = content.decode("utf-8").splitlines()
                    header = lines[0].split(",")
                    assert "interval_reason" in header
                    assert "SYNTHETIC_INTERVALS_UNCALIBRATED" in content.decode("utf-8")
                    # Confirm lower and upper interval bound columns are NOT present
                    assert "interval_lower" not in header and "lower" not in header
                    exports_info["forecasts"] = {
                        "rows": len(lines) - 1,
                        "interval_reason_verified": True
                    }
                elif kind == "configuration":
                    data = json.loads(content.decode("utf-8"))
                    assert "configuration" in data
                    assert data["predictor"] == "persistence"
                    exports_info["configuration"] = {"generator_version": data["generator_version"]}
                else:
                    exports_info[kind] = {"bytes": len(content)}

    return {"status": "PASSED", "exports": exports_info}


def test_5_historical_inspector_cutoff_polling():
    print("\n--- Check 5: Historical Inspector Cutoff Across Polling ---")
    with tempfile.TemporaryDirectory() as td:
        runtime = Path(td) / "runtime"
        app = create_app(root=ROOT, runtime=runtime, local_enabled=False, run_clock=False)
        with TestClient(app) as client:
            s_resp = client.post("/api/replay/sessions", json={"source_id": "synthetic-dawn", "start": "full"}).json()
            session_id = s_resp["session_id"]
            generation = s_resp["generation"]

            # Advance to minute 60
            manager = app.state.manager
            sess = manager.get(session_id)
            sess.advance_to(60)

            # Query exploration cutoff at minute 60
            exp60 = client.get(f"/api/replay/sessions/{session_id}/explore?end_minute=60&window=60").json()
            initial_history_len = len(exp60["history"])
            initial_forecasts_len = len(exp60["forecasts"])
            print(f"At cutoff 60: {initial_history_len} readings, {initial_forecasts_len} forecasts.")

            # Now advance replay clock from 60 to 120 (simulating live polling while inspector remains pinned to 60)
            for m in range(65, 125, 5):
                sess.advance_to(m)
                polled = client.get(f"/api/replay/sessions/{session_id}/explore?end_minute=60&window=60").json()

                # History and forecasts must remain strictly pinned to <= 60
                assert len(polled["history"]) == initial_history_len
                assert len(polled["forecasts"]) == initial_forecasts_len
                for r in polled["history"]:
                    t = r["measurement_time"]
                    # measurement time should not exceed epoch + 60 minutes
                    assert "2026-01-01T09:00:00Z" >= t
                for f in polled["forecasts"]:
                    assert "2026-01-01T09:00:00Z" >= f["origin_time"]
                    if f["score"] is not None:
                        assert f["score"]["matured_time"] <= "2026-01-01T09:00:00Z"

            print(f"Verified: Inspector cutoff strictly isolated while session advanced to minute {sess.minute}.")

    return {"status": "PASSED", "pinned_cutoff_minute": 60, "session_advanced_to": 120}


def test_6_all_four_dropout_durations():
    print("\n--- Check 6: All Four Dropout Durations (15, 30, 60, 120 min) ---")
    durations = [15, 30, 60, 120]
    results = {}
    for dur in durations:
        scenario = f"dropout{dur}"
        s = Session(synthetic(scenario))
        gap_start, gap_end = 180, 180 + dur
        expected_rec_min = gap_end + 60

        # During outage
        s.advance_to(180 + dur // 2)
        r_mid = s.snapshot()["recovery"]
        assert r_mid["is_suppressed"] is True
        assert r_mid["consecutive_valid_cells"] == 0
        assert r_mid["conditional_recovery_minute"] is None

        # Just after outage ends (first valid reading)
        s.advance_to(gap_end)
        r_end = s.snapshot()["recovery"]
        assert r_end["is_suppressed"] is True
        assert r_end["consecutive_valid_cells"] == 1
        assert r_end["conditional_recovery_minute"] == expected_rec_min

        # Just before recovery (55 minutes after resumption)
        s.advance_to(gap_end + 55)
        r_pre = s.snapshot()["recovery"]
        assert r_pre["is_suppressed"] is True
        f_pre = next(f for f in s.forecasts if f.origin == gap_end + 55)
        assert f_pre.value is None
        assert f_pre.reason == "INCOMPLETE_HISTORY"

        # At exact recovery minute
        s.advance_to(expected_rec_min)
        r_rec = s.snapshot()["recovery"]
        assert r_rec["is_suppressed"] is False
        assert r_rec["consecutive_valid_cells"] == 61
        f_rec = next(f for f in s.forecasts if f.origin == expected_rec_min)
        assert f_rec.value is not None
        assert f_rec.reason == "OK"

        print(f"Duration {dur}m: Gap [{gap_start}..{gap_end}] -> Rebuilding [{gap_end}..{expected_rec_min}) -> Recovered at minute {expected_rec_min} (reason: OK)")
        results[dur] = {
            "gap": [gap_start, gap_end],
            "first_resumption": gap_end,
            "suppressed_before": gap_end + 55,
            "recovery_minute": expected_rec_min,
            "forecast_value": f_rec.value,
            "forecast_reason": f_rec.reason
        }

    return {"status": "PASSED", "durations": results}


def main():
    print("=" * 70)
    print("EXECUTING STAGE 3-5 SPECIFIC VERIFICATION GAPS")
    print("=" * 70)

    summary = {}
    summary["check_1_fresh_dependency_installation"] = test_1_fresh_dependency_installation()
    summary["check_2_http_private_mode"] = test_2_http_private_mode()
    summary["check_3_patient_export_rejection"] = test_3_patient_export_rejection()
    summary["check_4_five_synthetic_export_downloads"] = test_4_five_synthetic_export_downloads()
    summary["check_5_historical_inspector_cutoff_polling"] = test_5_historical_inspector_cutoff_polling()
    summary["check_6_all_four_dropout_durations"] = test_6_all_four_dropout_durations()

    report_path = ROOT / "reports/capability_recovery/SPECIFIC_GAPS_VERIFICATION_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2))
    print(f"\nAll 6 checks completed successfully! Report written to {report_path}")


if __name__ == "__main__":
    main()
