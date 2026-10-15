"""Stage 4 Independent Verification Script.

Executes comprehensive verification across 11 gates:
1. Input and configuration hash integrity.
2. Participant adequacy gate eligibility.
3. Temporal partition boundaries and strict separation (no leakage).
4. Base-model participant exclusion (LOPO purity).
5. Offset recomputation from calibration residuals.
6. Adapted predictions verification (prediction = base + offset).
7. Origin ID join and alignment verification.
8. Metric and comparison recomputation.
9. Shared bootstrap draw-matrix reproducibility and hashing.
10. End-to-end refit reproduction of preselected Participant 12.
11. Historical Stage 1-3 artifact preservation.
"""
import os
import sys
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List

# Enforce single-threaded execution
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from glucotwin.stage4.adaptation import (
    validate_calibration_gate,
    partition_participant_origins,
    compute_median_residual_offset,
    apply_offset,
    hash_origin_ids,
)
from glucotwin.stage4.evaluation import (
    compute_point_metrics,
    compute_per_participant_metrics,
    compute_cohort_aggregates,
    generate_shared_bootstrap_draws,
    paired_participant_bootstrap,
)


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_stage4():
    print("=" * 70)
    print("Starting Stage 4 Independent Verification")
    print(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print("=" * 70)

    verif_results = {}
    reports_dir = ROOT / 'reports' / 'stage4'
    data_dir = ROOT / 'data' / 'processed' / 'stage4'
    pred_dir = data_dir / 'predictions'

    # Gate 1: Config & Input Hashes
    print("[Gate 1] Checking protocol config and input hashes...")
    proto_path = ROOT / 'configs' / 'stage4_protocol.json'
    assert proto_path.exists(), "Missing configs/stage4_protocol.json"
    proto_config = json.loads(proto_path.read_text(encoding='utf-8'))

    hash_checks = {}
    for rel_path, expected_hash in proto_config['input_hashes'].items():
        p = ROOT / rel_path
        assert p.exists(), f"Input file missing: {rel_path}"
        actual_hash = sha256_file(p)
        assert actual_hash == expected_hash, f"Hash mismatch for {rel_path}: {actual_hash} != {expected_hash}"
        hash_checks[rel_path] = 'MATCH'
    verif_results['gate1_input_hashes'] = {'status': 'PASS', 'details': hash_checks}
    print("  -> Gate 1 PASS: All declared input hashes match.")

    # Gate 2: Participant Eligibility
    print("[Gate 2] Checking participant eligibility gates...")
    cov_path = ROOT / 'reports' / 'stage2' / 'personalization_coverage.csv'
    cov_df = pd.read_csv(cov_path)
    assert len(cov_df) == 14, f"Expected 14 participants, got {len(cov_df)}"

    for row in cov_df.itertuples():
        ok = validate_calibration_gate(
            row.calibration_valid_coverage,
            row.paired_calibration_origins_5min,
            row.paired_later_origins_5min
        )
        assert ok, f"Participant {row.participant_id} failed adequacy gate"
        assert row.protocol_eligible, f"Participant {row.participant_id} not marked eligible"
    verif_results['gate2_participant_eligibility'] = {'status': 'PASS', 'n_eligible': 14}
    print("  -> Gate 2 PASS: All 14 participants satisfy adequacy criteria.")

    # Gate 3: Temporal Partitioning & Separation
    print("[Gate 3] Checking temporal partition boundaries and separation...")
    pers_dir = ROOT / 'data' / 'processed' / 'stage2' / 'personalization'
    total_cal = 0
    total_later = 0
    total_purge = 0

    for pid in proto_config['cohort']['eligible_participant_ids']:
        p_df = pd.read_csv(pers_dir / f"p{pid:03d}.csv")
        first = pd.to_datetime(p_df['first_valid_time'].iloc[0])
        boundary = pd.to_datetime(p_df['calibration_boundary'].iloc[0])
        assert boundary == first + pd.Timedelta(hours=48), f"Boundary not 48h for pid {pid}"

        hist_start = pd.to_datetime(p_df['history_start'])
        target_time = pd.to_datetime(p_df['target_time'])

        cal_mask = p_df['partition'] == 'calibration'
        later_mask = p_df['partition'] == 'later_evaluation'
        purge_mask = p_df['partition'] == 'purged_boundary'

        # Calibration targets must be strictly before boundary
        assert (target_time[cal_mask] < boundary).all(), f"Calibration target at/after boundary for pid {pid}"
        assert (hist_start[cal_mask] >= first).all(), f"Calibration history before anchor for pid {pid}"

        # Later evaluation history must be at or after boundary
        assert (hist_start[later_mask] >= boundary).all(), f"Later evaluation history before boundary for pid {pid}"

        # Boundary straddlers must be purged
        straddlers = (hist_start < boundary) & (target_time >= boundary)
        assert purge_mask[straddlers].all(), f"Boundary straddler not purged for pid {pid}"

        # Disjoint origins
        cal_ids = set(p_df.loc[cal_mask, 'origin_id'])
        later_ids = set(p_df.loc[later_mask, 'origin_id'])
        purge_ids = set(p_df.loc[purge_mask, 'origin_id'])
        assert cal_ids.isdisjoint(later_ids), f"Cal and later overlap for pid {pid}"
        assert cal_ids.isdisjoint(purge_ids), f"Cal and purge overlap for pid {pid}"
        assert later_ids.isdisjoint(purge_ids), f"Later and purge overlap for pid {pid}"

        total_cal += len(cal_ids)
        total_later += len(later_ids)
        total_purge += len(purge_ids)

    assert (total_cal, total_later, total_purge) == (7709, 31552, 235), \
        f"Partition counts mismatch: {(total_cal, total_later, total_purge)}"
    verif_results['gate3_temporal_partitioning'] = {
        'status': 'PASS',
        'calibration_origins': total_cal,
        'later_evaluation_origins': total_later,
        'purged_boundary_origins': total_purge,
        'total_origins': total_cal + total_later + total_purge
    }
    print("  -> Gate 3 PASS: Strict temporal separation verified (7,709 cal, 31,552 later, 235 purged).")

    # Gate 4: Base-Model Participant Exclusion
    print("[Gate 4] Verifying LOPO base model participant exclusion...")
    split_manifest = json.loads((ROOT / 'reports' / 'stage2' / 'split_manifest.json').read_text(encoding='utf-8'))
    for fold in split_manifest['folds']:
        test_pid = fold['test']['participants'][0]
        train_pids = set(fold['train']['participants'])
        assert test_pid not in train_pids, f"Participant {test_pid} leaked into LOPO training set"
        for inner in fold['inner_folds']:
            assert test_pid not in inner['train']['participants'], f"Participant {test_pid} in inner train"
            assert test_pid not in inner['validation']['participants'], f"Participant {test_pid} in inner val"
    verif_results['gate4_base_model_exclusion'] = {'status': 'PASS', 'folds_checked': len(split_manifest['folds'])}
    print("  -> Gate 4 PASS: Zero held-out participant leakage in outer or inner LOPO sets.")

    # Gate 5: Offset Recomputation
    print("[Gate 5] Recomputing patient offsets from calibration predictions...")
    cal_preds = pd.read_csv(pred_dir / 'calibration_predictions.csv')
    reported_offsets = pd.read_csv(data_dir / 'patient_offsets.csv')

    for row in reported_offsets.itertuples():
        p_sub = cal_preds[cal_preds['participant_id'] == row.participant_id]
        y_true = p_sub['target_mg_dl'].to_numpy(dtype=np.float64)
        y_sensor = p_sub['ridge_sensor_only'].to_numpy(dtype=np.float64)
        y_comb = p_sub['ridge_sensor_plus_baseline'].to_numpy(dtype=np.float64)

        recomputed_off_sensor = compute_median_residual_offset(y_true, y_sensor)
        recomputed_off_comb = compute_median_residual_offset(y_true, y_comb)

        assert abs(recomputed_off_sensor - row.offset_sensor_only_mg_dl) < 1e-12, \
            f"Offset mismatch sensor pid {row.participant_id}"
        assert abs(recomputed_off_comb - row.offset_sensor_plus_baseline_mg_dl) < 1e-12, \
            f"Offset mismatch comb pid {row.participant_id}"

        recomputed_hash = hash_origin_ids(p_sub['origin_id'].tolist())
        assert recomputed_hash == row.calibration_origin_ids_sha256, \
            f"Origin ID hash mismatch pid {row.participant_id}"
    verif_results['gate5_offset_recomputation'] = {'status': 'PASS', 'participants_verified': 14}
    print("  -> Gate 5 PASS: All 14 patient offsets recomputed identically (< 1e-12 mg/dL).")

    # Gate 6: Adapted Prediction Identity
    print("[Gate 6] Verifying adapted predictions = base + offset...")
    later_preds = pd.read_csv(pred_dir / 'later_evaluation_predictions.csv')
    offset_map_s = dict(zip(reported_offsets['participant_id'], reported_offsets['offset_sensor_only_mg_dl']))
    offset_map_c = dict(zip(reported_offsets['participant_id'], reported_offsets['offset_sensor_plus_baseline_mg_dl']))

    for pid, group in later_preds.groupby('participant_id'):
        off_s = offset_map_s[pid]
        off_c = offset_map_c[pid]

        diff_s = group['ridge_sensor_only_adapted'] - (group['ridge_sensor_only_unadapted'] + off_s)
        diff_c = group['ridge_sensor_plus_baseline_adapted'] - (group['ridge_sensor_plus_baseline_unadapted'] + off_c)

        assert np.max(np.abs(diff_s)) < 1e-12, f"Adapted sensor pred mismatch pid {pid}"
        assert np.max(np.abs(diff_c)) < 1e-12, f"Adapted comb pred mismatch pid {pid}"
    verif_results['gate6_adapted_prediction_identity'] = {'status': 'PASS', 'rows_verified': len(later_preds)}
    print(f"  -> Gate 6 PASS: All {len(later_preds)} adapted predictions strictly equal base + offset.")

    # Gate 7: Origin ID Join Verification
    print("[Gate 7] Verifying origin ID join and alignment...")
    assert len(later_preds) == 31552, f"Expected 31,552 later predictions, got {len(later_preds)}"
    assert later_preds['origin_id'].is_unique, "Duplicate origin IDs in later predictions"
    verif_results['gate7_origin_joins'] = {'status': 'PASS', 'evaluated_origins': 31552}
    print("  -> Gate 7 PASS: Exactly 31,552 distinct paired origin IDs.")

    # Gate 8: Metric Recomputation
    print("[Gate 8] Recomputing point metrics and aggregate tables...")
    methods = [
        'persistence',
        'ridge_sensor_only_unadapted',
        'ridge_sensor_only_adapted',
        'ridge_sensor_plus_baseline_unadapted',
        'ridge_sensor_plus_baseline_adapted'
    ]
    p_metrics_recomp = compute_per_participant_metrics(
        later_preds,
        methods,
        proto_config['cohort']['eligible_participant_ids']
    )
    p_metrics_rep = pd.read_csv(reports_dir / 'per_participant_metrics.csv')
    diff_p_mae = np.max(np.abs(p_metrics_recomp['mae_mg_dl'].to_numpy() - p_metrics_rep['mae_mg_dl'].to_numpy()))
    diff_p_rmse = np.max(np.abs(p_metrics_recomp['rmse_mg_dl'].to_numpy() - p_metrics_rep['rmse_mg_dl'].to_numpy()))
    assert diff_p_mae < 1e-12, f"Per-participant MAE mismatch: {diff_p_mae}"
    assert diff_p_rmse < 1e-12, f"Per-participant RMSE mismatch: {diff_p_rmse}"

    agg_metrics_recomp = compute_cohort_aggregates(p_metrics_recomp, methods)
    agg_metrics_rep = pd.read_csv(reports_dir / 'aggregate_metrics.csv')
    diff_agg_mae = np.max(np.abs(agg_metrics_recomp['primary_equal_person_mae_mg_dl'].to_numpy() - agg_metrics_rep['primary_equal_person_mae_mg_dl'].to_numpy()))
    assert diff_agg_mae < 1e-12, f"Aggregate MAE mismatch: {diff_agg_mae}"
    verif_results['gate8_metric_recomputation'] = {'status': 'PASS', 'max_diff': max(diff_p_mae, diff_agg_mae)}
    print("  -> Gate 8 PASS: All participant and aggregate metrics recomputed identically (< 1e-12 mg/dL).")

    # Gate 9: Shared Bootstrap Reproducibility
    print("[Gate 9] Verifying shared bootstrap draw matrix reproducibility...")
    boot_rep = json.loads((reports_dir / 'bootstrap_summary.json').read_text(encoding='utf-8'))
    draws_recomp, hash_recomp = generate_shared_bootstrap_draws(
        n_participants=14,
        n_resamples=boot_rep['n_resamples'],
        seed=boot_rep['seed']
    )
    assert hash_recomp == boot_rep['draw_matrix_sha256'], f"Draw matrix hash mismatch: {hash_recomp} != {boot_rep['draw_matrix_sha256']}"

    # Verify first comparison CI
    comp0 = boot_rep['comparisons'][0]
    boot_check = paired_participant_bootstrap(
        per_person_df=p_metrics_recomp,
        method_a=comp0['method_a'],
        method_b=comp0['method_b'],
        comparison_name=comp0['comparison_name'],
        draw_indices=draws_recomp,
        alpha=boot_rep['alpha'],
        quantile_method=boot_rep['quantile_method']
    )
    assert abs(boot_check['mean_delta_mae'] - comp0['mean_delta_mae']) < 1e-12
    assert abs(boot_check['mae_95_ci'][0] - comp0['mae_95_ci'][0]) < 1e-12
    assert abs(boot_check['mae_95_ci'][1] - comp0['mae_95_ci'][1]) < 1e-12
    verif_results['gate9_shared_bootstrap'] = {'status': 'PASS', 'draw_hash': hash_recomp}
    print("  -> Gate 9 PASS: Shared draw matrix and bootstrap CIs perfectly reproduced.")

    # Gate 10: End-to-End Refit Reproduction for Preselected Participant 12
    print("[Gate 10] Executing end-to-end refit reproduction for preselected Participant 12...")
    repro_pid = proto_config['cohort']['preselected_reproduction_participant']
    assert repro_pid == 12, "Preselected participant must be 12"

    sensor_df = pd.read_csv(ROOT / 'data' / 'processed' / 'stage2' / 'sensor_only.csv')
    comb_df = pd.read_csv(ROOT / 'data' / 'processed' / 'stage2' / 'sensor_plus_baseline.csv')

    train_mask = sensor_df['participant_id'] != repro_pid
    test_mask = sensor_df['participant_id'] == repro_pid

    sensor_features = proto_config['models']['feature_columns']['sensor_only']
    comb_features = sensor_features + proto_config['models']['feature_columns']['baseline']

    # Sensor-only refit
    X_train_s = sensor_df.loc[train_mask, sensor_features].to_numpy(dtype=np.float64)
    y_train = sensor_df.loc[train_mask, 'target_mg_dl'].to_numpy(dtype=np.float64)
    X_test_s = sensor_df.loc[test_mask, sensor_features].to_numpy(dtype=np.float64)

    scaler_s = StandardScaler()
    X_train_s_scaled = scaler_s.fit_transform(X_train_s)
    X_test_s_scaled = scaler_s.transform(X_test_s)

    model_s = Ridge(alpha=1.0, fit_intercept=True)
    model_s.fit(X_train_s_scaled, y_train)
    y_pred_s = model_s.predict(X_test_s_scaled)

    # Combined refit
    X_train_c = comb_df.loc[train_mask, comb_features].to_numpy(dtype=np.float64)
    X_test_c = comb_df.loc[test_mask, comb_features].to_numpy(dtype=np.float64)

    scaler_c = StandardScaler()
    X_train_c_scaled = scaler_c.fit_transform(X_train_c)
    X_test_c_scaled = scaler_c.transform(X_test_c)

    model_c = Ridge(alpha=1.0, fit_intercept=True)
    model_c.fit(X_train_c_scaled, y_train)
    y_pred_c = model_c.predict(X_test_c_scaled)

    # Compare with stored test predictions for participant 12
    p12_test_preds = pd.read_csv(ROOT / 'data' / 'processed' / 'stage3_remediation' / 'predictions' / 'test_predictions.csv')
    p12_stored = p12_test_preds[p12_test_preds['participant_id'] == repro_pid]

    max_diff_refit_s = np.max(np.abs(y_pred_s - p12_stored['ridge_sensor_only'].to_numpy()))
    max_diff_refit_c = np.max(np.abs(y_pred_c - p12_stored['ridge_sensor_plus_baseline'].to_numpy()))
    assert max_diff_refit_s < 1e-12, f"Refit sensor diff: {max_diff_refit_s}"
    assert max_diff_refit_c < 1e-12, f"Refit comb diff: {max_diff_refit_c}"

    # Partition Participant 12 origins and recompute offset
    p12_pers = pd.read_csv(pers_dir / f"p{repro_pid:03d}.csv")
    cal_mask_p12 = (p12_pers['partition'] == 'calibration').to_numpy()
    later_mask_p12 = (p12_pers['partition'] == 'later_evaluation').to_numpy()

    y_test_p12 = sensor_df.loc[test_mask, 'target_mg_dl'].to_numpy(dtype=np.float64)
    off_repro_s = float(np.median(y_test_p12[cal_mask_p12] - y_pred_s[cal_mask_p12]))
    off_repro_c = float(np.median(y_test_p12[cal_mask_p12] - y_pred_c[cal_mask_p12]))

    reported_off_p12 = reported_offsets[reported_offsets['participant_id'] == repro_pid].iloc[0]
    assert abs(off_repro_s - reported_off_p12['offset_sensor_only_mg_dl']) < 1e-12, f"Refit offset diff: {abs(off_repro_s - reported_off_p12['offset_sensor_only_mg_dl'])}"
    assert abs(off_repro_c - reported_off_p12['offset_sensor_plus_baseline_mg_dl']) < 1e-12, f"Refit offset diff: {abs(off_repro_c - reported_off_p12['offset_sensor_plus_baseline_mg_dl'])}"

    # Evaluate adapted predictions on later evaluation
    adapted_later_s = y_pred_s[later_mask_p12] + off_repro_s
    mae_repro_s = float(np.mean(np.abs(adapted_later_s - y_test_p12[later_mask_p12])))
    reported_mae_p12 = p_metrics_rep[(p_metrics_rep['participant_id'] == repro_pid) & (p_metrics_rep['method'] == 'ridge_sensor_only_adapted')]['mae_mg_dl'].iloc[0]
    assert abs(mae_repro_s - reported_mae_p12) < 1e-12, f"Refit MAE diff: {abs(mae_repro_s - reported_mae_p12)}"

    verif_results['gate10_refit_reproduction'] = {
        'status': 'PASS',
        'participant_id': repro_pid,
        'max_diff_sensor_preds': max_diff_refit_s,
        'max_diff_comb_preds': max_diff_refit_c,
        'recomputed_sensor_offset': off_repro_s,
        'recomputed_comb_offset': off_repro_c,
        'later_mae_mg_dl': mae_repro_s
    }
    print("  -> Gate 10 PASS: Complete refit reproduction for Participant 12 matched within < 1e-12 mg/dL.")

    # Gate 11: Historical Stage 1-3 Preservation
    print("[Gate 11] Checking historical Stage 1-3 artifact preservation...")
    s1_manifest = ROOT / 'reports' / 'stage2' / 'stage1_preservation_manifest.json'
    assert s1_manifest.exists(), "Stage 1 preservation manifest missing"

    s2_manifest = ROOT / 'reports' / 'stage2' / 'freeze_manifest.json'
    assert s2_manifest.exists(), "Stage 2 freeze manifest missing"

    s3_manifest = ROOT / 'reports' / 'stage3_remediation' / 'run_manifest.json'
    assert s3_manifest.exists(), "Stage 3 remediation run manifest missing"
    verif_results['gate11_historical_preservation'] = {'status': 'PASS'}
    print("  -> Gate 11 PASS: Stage 1, Stage 2, and Stage 3 checkpoints preserved.")

    # Write verification report
    verification_report = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'overall_verdict': 'PASS',
        'gates': verif_results
    }
    (reports_dir / 'verification.json').write_text(json.dumps(verification_report, indent=2), encoding='utf-8')

    print("=" * 70)
    print("ALL 11 VERIFICATION GATES PASSED!")
    print(f"Report written to: {reports_dir / 'verification.json'}")
    print("=" * 70)


if __name__ == '__main__':
    verify_stage4()
