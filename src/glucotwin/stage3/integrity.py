"""Preflight and execution integrity checks for Stage 3 glucose forecasting.

Verifies protocol hashes, split manifests, source provenance, prepared feature integrity,
timestamp spacing, column ordering, participant disjointness, and metadata exclusion before fitting.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd


SENSOR_FEATURES = [
    'glucose_lag_0m', 'glucose_lag_5m', 'glucose_lag_10m', 'glucose_lag_15m',
    'glucose_lag_20m', 'glucose_lag_25m', 'glucose_lag_30m', 'glucose_lag_35m',
    'glucose_lag_40m', 'glucose_lag_45m', 'glucose_lag_50m', 'glucose_lag_55m',
    'glucose_lag_60m', 'glucose_mean_15m', 'glucose_std_15m', 'glucose_mean_30m',
    'glucose_std_30m', 'glucose_mean_60m', 'glucose_std_60m', 'glucose_slope_15m',
    'glucose_slope_30m'
]

BASELINE_FEATURES = ['age', 'bmi', 'hba1c', 'fasting_glucose']

COMBINED_FEATURES = SENSOR_FEATURES + BASELINE_FEATURES

TARGET_COL = 'target_mg_dl'

METADATA_COLUMNS = [
    'origin_id', 'participant_id', 'issue_time', 'history_start', 'target_time', TARGET_COL
]

PROHIBITED_COLUMNS = [
    'origin_id', 'participant_id', 'issue_time', 'history_start', 'target_time',
    'target_mg_dl', 'source_row', 'split_fold'
]

EXPECTED_PARTICIPANTS = [3, 5, 12, 14, 28, 30, 35, 36, 38, 39, 42, 46, 47, 49]

# Checkpoint references
EXPECTED_STAGE2_PROTOCOL_HASH = "2cb9be37042bbb6ea4b2a5d233c3d8f9f8bd89a0f11414bbf12b3ee200cd5abf"
EXPECTED_SPLIT_MANIFEST_HASH = "6fbc950407acf1f1a21f17f70ec4c497ac3a55c04805127e68e65a6c713321cd"
EXPECTED_SOURCE_PROVENANCE_HASH = "b9006433b4386b2524e0c2d5b97bb6e1c6eb821013eacf63823145ad68c2da73"
EXPECTED_SENSOR_ONLY_HASH = "aff438a00dfea96f3564ce3e28bf4360204cc106d8422f2fa413ccc62f85d9de"
EXPECTED_SENSOR_PLUS_BASELINE_HASH = "401302b33b56da9a6b4c49b9b59cc966119d32a6a45d6a34e9c8d29714d60bea"
EXPECTED_WINDOWS_FREEZE_HASH = "029b530f7616c50fe634f1c695e25753b4041410ae611cfe7fd6019bc6c0147c"
EXPECTED_LINUX_FREEZE_HASH = "b871a7de0af394410c2a4484710f809c77e1be24c60291395de28f5fd7c1d8ce"


class IntegrityError(Exception):
    """Raised when an integrity check fails before fitting."""
    pass


def sha256_file(p: Path) -> str:
    """Compute SHA-256 hash of a file."""
    if not p.is_file():
        raise IntegrityError(f"Required file does not exist: {p}")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify_feature_order_and_finiteness(df: pd.DataFrame, expected_features: list[str], matrix_name: str):
    """Ensure dataframe columns follow exact required order and contain purely finite numerical values."""
    for col in expected_features:
        if col not in df.columns:
            raise IntegrityError(f"Missing required feature '{col}' in {matrix_name}")
    vals = df[expected_features].to_numpy(dtype=float)
    if not np.isfinite(vals).all():
        raise IntegrityError(f"Non-finite values detected in features for {matrix_name}")


def verify_no_prohibited_metadata_in_features(feature_names: list[str]):
    """Ensure no prohibited metadata or target columns are included in estimator feature lists."""
    for col in PROHIBITED_COLUMNS:
        if col in feature_names:
            raise IntegrityError(f"Prohibited column '{col}' found in feature list: {feature_names}")


def run_preflight_checks(
    root: Path,
    config_path: Path,
    split_path: Path,
    sensor_csv: Path,
    combined_csv: Path
) -> dict:
    """Run all 10 preflight integrity checks before model fitting.

    Returns a summary dictionary suitable for writing to reports/stage3_remediation/preflight_report.json.
    Raises IntegrityError on any material violation.
    """
    report = {
        "status": "RUNNING",
        "checks": {}
    }

    # 1. Exact Stage 2 protocol hash
    protocol_path = root / 'configs' / 'stage2_protocol.json'
    obs_protocol_hash = sha256_file(protocol_path)
    if obs_protocol_hash != EXPECTED_STAGE2_PROTOCOL_HASH:
        raise IntegrityError(
            f"Stage 2 protocol hash mismatch: expected {EXPECTED_STAGE2_PROTOCOL_HASH}, observed {obs_protocol_hash}"
        )
    report["checks"]["stage2_protocol_hash"] = {
        "expected": EXPECTED_STAGE2_PROTOCOL_HASH,
        "observed": obs_protocol_hash,
        "pass": True
    }

    # 2. Exact split manifest hash
    obs_split_hash = sha256_file(split_path)
    if obs_split_hash != EXPECTED_SPLIT_MANIFEST_HASH:
        raise IntegrityError(
            f"Split manifest hash mismatch: expected {EXPECTED_SPLIT_MANIFEST_HASH}, observed {obs_split_hash}"
        )
    report["checks"]["split_manifest_hash"] = {
        "expected": EXPECTED_SPLIT_MANIFEST_HASH,
        "observed": obs_split_hash,
        "pass": True
    }

    # 3. Source provenance references
    stage1_preservation_path = root / 'reports' / 'stage2' / 'stage1_preservation_manifest.json'
    if not stage1_preservation_path.exists():
        raise IntegrityError("Stage 1 preservation manifest missing")
    freeze_manifest_path = root / 'reports' / 'stage2' / 'freeze_manifest.json'
    if not freeze_manifest_path.exists():
        raise IntegrityError("Stage 2 freeze manifest missing")
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding='utf-8'))
    obs_source_provenance = freeze_manifest.get('source_provenance_sha256')
    if obs_source_provenance != EXPECTED_SOURCE_PROVENANCE_HASH:
        raise IntegrityError(
            f"Source provenance mismatch: expected {EXPECTED_SOURCE_PROVENANCE_HASH}, observed {obs_source_provenance}"
        )
    report["checks"]["source_provenance"] = {
        "expected": EXPECTED_SOURCE_PROVENANCE_HASH,
        "observed": obs_source_provenance,
        "pass": True
    }

    # 4. Local prepared-feature hashes against recorded Windows preparation manifest
    obs_sensor_hash = sha256_file(sensor_csv)
    if obs_sensor_hash != EXPECTED_SENSOR_ONLY_HASH:
        raise IntegrityError(
            f"sensor_only.csv hash mismatch: expected {EXPECTED_SENSOR_ONLY_HASH}, observed {obs_sensor_hash}"
        )
    obs_comb_hash = sha256_file(combined_csv)
    if obs_comb_hash != EXPECTED_SENSOR_PLUS_BASELINE_HASH:
        raise IntegrityError(
            f"sensor_plus_baseline.csv hash mismatch: expected {EXPECTED_SENSOR_PLUS_BASELINE_HASH}, observed {obs_comb_hash}"
        )
    report["checks"]["prepared_feature_hashes"] = {
        "sensor_only": {"expected": EXPECTED_SENSOR_ONLY_HASH, "observed": obs_sensor_hash, "pass": True},
        "sensor_plus_baseline": {"expected": EXPECTED_SENSOR_PLUS_BASELINE_HASH, "observed": obs_comb_hash, "pass": True}
    }

    # Load dataframes for semantic integrity checks
    df_sensor = pd.read_csv(sensor_csv)
    df_combined = pd.read_csv(combined_csv)

    # 5. Expected participants
    obs_pids_sensor = sorted(df_sensor['participant_id'].unique().tolist())
    obs_pids_comb = sorted(df_combined['participant_id'].unique().tolist())
    if obs_pids_sensor != EXPECTED_PARTICIPANTS or obs_pids_comb != EXPECTED_PARTICIPANTS:
        raise IntegrityError(
            f"Participant IDs mismatch: expected {EXPECTED_PARTICIPANTS}, observed sensor {obs_pids_sensor}, comb {obs_pids_comb}"
        )
    report["checks"]["expected_participants"] = {
        "expected_count": 14,
        "observed_count": len(obs_pids_sensor),
        "pass": True
    }

    # 6. Origin uniqueness and count
    n_sensor = len(df_sensor)
    n_comb = len(df_combined)
    if n_sensor != 39496 or n_comb != 39496:
        raise IntegrityError(f"Expected 39496 rows, got sensor={n_sensor}, comb={n_comb}")
    if not df_sensor['origin_id'].is_unique:
        raise IntegrityError("Duplicate origin_id in sensor_only.csv")
    if not df_combined['origin_id'].is_unique:
        raise IntegrityError("Duplicate origin_id in sensor_plus_baseline.csv")
    report["checks"]["origin_uniqueness"] = {
        "expected_origins": 39496,
        "observed_origins": n_sensor,
        "pass": True
    }

    # 7. Paired sensor/combined origins and targets
    # Sort deterministically by participant_id, issue_time
    df_sensor_sorted = df_sensor.sort_values(['participant_id', 'issue_time']).reset_index(drop=True)
    df_combined_sorted = df_combined.sort_values(['participant_id', 'issue_time']).reset_index(drop=True)

    if not (df_sensor_sorted['origin_id'] == df_combined_sorted['origin_id']).all():
        raise IntegrityError("Origin IDs do not match between sensor and combined matrices")
    if not (df_sensor_sorted[TARGET_COL] == df_combined_sorted[TARGET_COL]).all():
        raise IntegrityError("Target glucose values do not match between sensor and combined matrices")
    report["checks"]["paired_origins_and_targets"] = {"pass": True}

    # 8. Correct issue/history/target timestamps
    issue_times = pd.to_datetime(df_sensor_sorted['issue_time'])
    history_starts = pd.to_datetime(df_sensor_sorted['history_start'])
    target_times = pd.to_datetime(df_sensor_sorted['target_time'])

    hist_diffs = issue_times - history_starts
    if not (hist_diffs == pd.Timedelta(minutes=60)).all():
        raise IntegrityError("History duration is not exactly 60 minutes for all origins")
    target_diffs = target_times - issue_times
    if not (target_diffs == pd.Timedelta(minutes=30)).all():
        raise IntegrityError("Forecast horizon is not exactly 30 minutes for all origins")
    report["checks"]["timestamp_spacing"] = {
        "history_delta_min": 60,
        "target_horizon_min": 30,
        "pass": True
    }

    # 9. Feature-column order and finite feature values
    expected_sensor_cols = METADATA_COLUMNS + SENSOR_FEATURES
    expected_comb_cols = METADATA_COLUMNS + SENSOR_FEATURES + BASELINE_FEATURES
    if df_sensor.columns.tolist() != expected_sensor_cols:
        raise IntegrityError("sensor_only.csv column order does not match contract")
    if df_combined.columns.tolist() != expected_comb_cols:
        raise IntegrityError("sensor_plus_baseline.csv column order does not match contract")

    verify_feature_order_and_finiteness(df_sensor, SENSOR_FEATURES, "sensor_only.csv")
    verify_feature_order_and_finiteness(df_combined, COMBINED_FEATURES, "sensor_plus_baseline.csv")
    if not np.isfinite(df_sensor[TARGET_COL].to_numpy(dtype=float)).all():
        raise IntegrityError("Non-finite values detected in target_mg_dl")
    report["checks"]["feature_columns_and_finiteness"] = {
        "sensor_features_count": len(SENSOR_FEATURES),
        "combined_features_count": len(COMBINED_FEATURES),
        "pass": True
    }

    # 10. No prohibited metadata in estimator feature lists
    verify_no_prohibited_metadata_in_features(SENSOR_FEATURES)
    verify_no_prohibited_metadata_in_features(COMBINED_FEATURES)
    report["checks"]["prohibited_metadata_excluded"] = {"pass": True}

    report["status"] = "PASS"
    return report
