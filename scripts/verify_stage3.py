"""Stage 3 independent verifier: verifies fit ledger identities, origin joins, candidate optimality,
metric reconciliation, and end-to-end refit reproduction for preselected fold holdout_012.
"""
import os
import sys
import json
import hashlib
import argparse
from pathlib import Path

# Thread limits to prevent contention
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np
import pandas as pd

from glucotwin.stage3.integrity import (
    SENSOR_FEATURES,
    BASELINE_FEATURES,
    COMBINED_FEATURES,
    TARGET_COL,
    EXPECTED_PARTICIPANTS,
    sha256_file
)
from glucotwin.stage3.training import (
    get_feature_columns,
    fit_estimator,
    predict_estimator,
    get_participant_indices
)
from glucotwin.stage3.selection import select_candidate
from glucotwin.stage3.metrics import (
    compute_per_participant_metrics,
    compute_aggregate_metrics,
    compute_paired_participant_bootstrap
)

PRESELECTED_REPRO_FOLD = "holdout_012"
PRESELECTED_REPRO_PID = 12


def require(condition: bool, msg: str):
    if not condition:
        raise AssertionError(msg)


def main():
    parser = argparse.ArgumentParser(description="GlucoTwin Stage 3 Verification")
    parser.add_argument('--reports-dir', type=str, default='reports/stage3_remediation',
                        help="Path to Stage 3 reports directory")
    parser.add_argument('--predictions-dir', type=str, default='data/processed/stage3_remediation/predictions',
                        help="Path to Stage 3 predictions directory")
    args = parser.parse_args()

    reports_dir = ROOT / args.reports_dir
    pred_dir = ROOT / args.predictions_dir
    config_path = ROOT / 'configs/stage3_run.json'
    split_path = ROOT / 'reports/stage2/split_manifest.json'
    sensor_csv = ROOT / 'data/processed/stage2/sensor_only.csv'
    comb_csv = ROOT / 'data/processed/stage2/sensor_plus_baseline.csv'

    print("================================================================")
    print("  GlucoTwin Stage 3 Independent Verification (Remediation)")
    print("================================================================")
    print(f"Reports directory     : {reports_dir.as_posix()}")
    print(f"Predictions directory : {pred_dir.as_posix()}")

    checks = []

    # 1. Config, split manifest, and preflight report presence
    require(config_path.exists(), "configs/stage3_run.json missing")
    config = json.loads(config_path.read_text(encoding='utf-8'))
    require(split_path.exists(), "reports/stage2/split_manifest.json missing")
    split_manifest = json.loads(split_path.read_text(encoding='utf-8'))

    preflight_report_path = reports_dir / 'preflight_report.json'
    require(preflight_report_path.exists(), "preflight_report.json missing")
    preflight_data = json.loads(preflight_report_path.read_text(encoding='utf-8'))
    require(preflight_data.get('status') == 'PASS', "Preflight status is not PASS")
    checks.append("Stage 3 run config, Stage 2 split manifest, and preflight report present and verified PASS")

    # 2. Comprehensive Fit Ledger Verification (all 728 distinct fit identities)
    fit_ledger_path = reports_dir / 'fit_ledger.csv'
    require(fit_ledger_path.exists(), "fit_ledger.csv missing")
    df_ledger = pd.read_csv(fit_ledger_path)
    require(len(df_ledger) == 728, f"Expected 728 fits in ledger, got {len(df_ledger)}")

    inner_fits = df_ledger[df_ledger['stage'] == 'inner_selection']
    outer_fits = df_ledger[df_ledger['stage'] == 'outer_refit']
    require(len(inner_fits) == 672, f"Expected 672 inner selection fits, got {len(inner_fits)}")
    require(len(outer_fits) == 56, f"Expected 56 outer refits, got {len(outer_fits)}")

    # Distinct composite key verification: (stage, outer_fold, held_out_pid, inner_fold, family, variant, candidate_id)
    key_cols = ['stage', 'outer_fold', 'held_out_pid', 'inner_fold', 'family', 'variant', 'candidate_id']
    distinct_keys = df_ledger[key_cols].drop_duplicates()
    require(len(distinct_keys) == 728, f"Duplicate fit keys found: {len(distinct_keys)} unique vs 728 expected")

    # Verify no missing fit combinations
    families = ['ridge', 'hist_gradient_boosting']
    variants = ['sensor_only', 'sensor_plus_baseline']
    outer_folds = split_manifest['folds']
    outer_fold_names = [f['outer_fold'] for f in outer_folds]

    for of in outer_folds:
        of_name = of['outer_fold']
        h_pid = of['test']['participants'][0]
        # Check outer refits: 4 fits per outer fold (2 families x 2 variants)
        of_outer = outer_fits[(outer_fits['outer_fold'] == of_name) & (outer_fits['held_out_pid'] == h_pid)]
        require(len(of_outer) == 4, f"Outer refits missing for {of_name}: expected 4, got {len(of_outer)}")

        # Check inner fits: 48 fits per outer fold (3 inner folds x 2 families x 2 variants x 4 candidates)
        of_inner = inner_fits[(inner_fits['outer_fold'] == of_name) & (inner_fits['held_out_pid'] == h_pid)]
        require(len(of_inner) == 48, f"Inner fits missing for {of_name}: expected 48, got {len(of_inner)}")

    checks.append("All 728 distinct fit identities validated (672 inner selection + 56 outer refits; 0 duplicates, 0 missing)")

    # 3. Outer test completeness and origin joins
    pred_path = pred_dir / 'test_predictions.csv'
    require(pred_path.exists(), "test_predictions.csv missing")
    df_pred = pd.read_csv(pred_path)
    require(len(df_pred) == 39496, f"Expected 39496 predictions, got {len(df_pred)}")
    require(df_pred['origin_id'].is_unique, "Duplicate origin_id in predictions")

    unique_pids = sorted(df_pred['participant_id'].unique().tolist())
    require(unique_pids == EXPECTED_PARTICIPANTS, f"Participants mismatch: {unique_pids} vs {EXPECTED_PARTICIPANTS}")

    df_sensor = pd.read_csv(sensor_csv).sort_values(['participant_id', 'issue_time']).reset_index(drop=True)
    df_comb = pd.read_csv(comb_csv).sort_values(['participant_id', 'issue_time']).reset_index(drop=True)

    # Join predictions to sensor_only by origin_id
    require(len(df_sensor) == 39496, f"Expected 39496 sensor rows, got {len(df_sensor)}")
    np.testing.assert_array_equal(df_pred['origin_id'].to_numpy(), df_sensor['origin_id'].to_numpy())
    np.testing.assert_array_equal(df_pred['participant_id'].to_numpy(), df_sensor['participant_id'].to_numpy())

    # Target values float identity (0 tolerance)
    target_pred = df_pred['target_mg_dl'].to_numpy(dtype=float)
    target_sensor = df_sensor[TARGET_COL].to_numpy(dtype=float)
    target_comb = df_comb[TARGET_COL].to_numpy(dtype=float)
    require(np.array_equal(target_pred, target_sensor), "Target values in predictions do not match sensor_only.csv")
    require(np.array_equal(target_pred, target_comb), "Target values in predictions do not match sensor_plus_baseline.csv")
    checks.append("Outer test completeness verified: exactly 39496 origins joined by ID; target glucose matches with 0 tolerance")

    # 4. Candidate selection optimality
    scores_path = reports_dir / 'inner_selection_scores.csv'
    selected_path = reports_dir / 'selected_candidates.csv'
    require(scores_path.exists(), "inner_selection_scores.csv missing")
    require(selected_path.exists(), "selected_candidates.csv missing")

    df_scores = pd.read_csv(scores_path)
    df_selected = pd.read_csv(selected_path)
    require(len(df_selected) == 56, f"Expected 56 selected candidates (14 folds x 4), got {len(df_selected)}")

    for _, row in df_selected.iterrows():
        o_fold = row['outer_fold']
        fam = row['family']
        var = row['variant']
        sel_cand = row['selected_candidate_id']
        val_score = row['validation_mae']

        sub_scores = df_scores[
            (df_scores['outer_fold'] == o_fold) &
            (df_scores['family'] == fam) &
            (df_scores['variant'] == var)
        ]
        require(len(sub_scores) == 4, f"Expected 4 candidate scores for {o_fold} {fam} {var}, got {len(sub_scores)}")

        # Verify optimality and tie-break
        cand_tuples = [
            (int(r['candidate_id']), float(r['equal_person_val_mae']), {})
            for _, r in sub_scores.iterrows()
        ]
        best_id, best_mae, _ = select_candidate(cand_tuples)
        require(best_id == sel_cand, f"Suboptimal selection in {o_fold} {fam} {var}: selected {sel_cand} but optimal is {best_id}")
        np.testing.assert_almost_equal(best_mae, val_score, decimal=6)

    checks.append("Candidate selection optimality verified for all 56 outer refits (minimal equal-person validation MAE with deterministic tie-break)")

    # 5. Metric reconciliation directly from stored predictions
    methods = [
        'persistence', 'trend',
        'ridge_sensor_only', 'ridge_sensor_plus_baseline',
        'hist_gradient_boosting_sensor_only', 'hist_gradient_boosting_sensor_plus_baseline'
    ]

    recomputed_per_person = compute_per_participant_metrics(df_pred, methods, EXPECTED_PARTICIPANTS)
    reported_per_person = pd.read_csv(reports_dir / 'per_participant_metrics.csv')
    require(len(recomputed_per_person) == len(reported_per_person), "Per-participant metrics row count mismatch")

    for col in ['mae_mg_dl', 'rmse_mg_dl', 'mean_signed_error_mg_dl']:
        np.testing.assert_allclose(
            recomputed_per_person[col].to_numpy(dtype=float),
            reported_per_person[col].to_numpy(dtype=float),
            rtol=1e-5, atol=1e-5,
            err_msg=f"Discrepancy in per-participant {col}"
        )

    recomputed_agg = compute_aggregate_metrics(recomputed_per_person, df_pred, methods)
    reported_agg = pd.read_csv(reports_dir / 'aggregate_metrics.csv')

    for col in [
        'primary_equal_person_mae_mg_dl', 'secondary_equal_person_rmse_mg_dl',
        'equal_person_mean_signed_error_mg_dl', 'window_weighted_mae_mg_dl',
        'window_weighted_rmse_mg_dl', 'window_weighted_mean_signed_error_mg_dl',
        'persistence_relative_skill_pct', 'trend_relative_skill_pct'
    ]:
        np.testing.assert_allclose(
            recomputed_agg[col].to_numpy(dtype=float),
            reported_agg[col].to_numpy(dtype=float),
            rtol=1e-5, atol=1e-5,
            err_msg=f"Discrepancy in aggregate {col}"
        )
    checks.append("All per-participant and aggregate metrics reconciled with zero unexplained discrepancy")

    # 6. End-to-end refit reproduction for preselected fold holdout_012
    print(f"\nReproducing preselected fold {PRESELECTED_REPRO_FOLD} (Participant {PRESELECTED_REPRO_PID})...")
    f_fold = next(f for f in outer_folds if f['outer_fold'] == PRESELECTED_REPRO_FOLD)
    f_train_pids = f_fold['train']['participants']
    f_test_pids = f_fold['test']['participants']
    require(f_test_pids == [PRESELECTED_REPRO_PID], "Holdout participant mismatch")

    f_train_idx = get_participant_indices(df_sensor, f_train_pids)
    f_test_idx = get_participant_indices(df_sensor, f_test_pids)

    repro_diffs = {}
    for fam in families:
        for var in variants:
            m_col = f"{fam}_{var}"
            feat_cols = get_feature_columns(var)
            df_src = df_sensor if var == 'sensor_only' else df_comb

            # Get selected candidate spec
            sel_row = df_selected[
                (df_selected['outer_fold'] == PRESELECTED_REPRO_FOLD) &
                (df_selected['family'] == fam) &
                (df_selected['variant'] == var)
            ].iloc[0]
            cand_spec = json.loads(sel_row['selected_candidate_spec'])

            X_tr = df_src.loc[f_train_idx, feat_cols].to_numpy(dtype=float)
            y_tr = df_src.loc[f_train_idx, TARGET_COL].to_numpy(dtype=float)
            X_te = df_src.loc[f_test_idx, feat_cols].to_numpy(dtype=float)

            re_est, re_scaler = fit_estimator(fam, cand_spec, X_tr, y_tr)
            re_preds = predict_estimator(re_est, re_scaler, X_te)

            stored_preds = df_pred.loc[f_test_idx, m_col].to_numpy(dtype=float)
            max_abs_diff = float(np.max(np.abs(re_preds - stored_preds)))
            repro_diffs[m_col] = max_abs_diff

            # Ridge is deterministic with 0 tolerance; HistGB with fixed random_state is identical
            require(max_abs_diff < 1e-6, f"Reproduction mismatch in {m_col}: max abs diff {max_abs_diff}")

    checks.append(f"Preselected fold {PRESELECTED_REPRO_FOLD} reproduced end-to-end (max abs diff < 1e-6 across all 4 models: {repro_diffs})")

    # Write verification.json
    verification_summary = {
        "status": "PASS",
        "verified_directory": reports_dir.as_posix(),
        "total_fits_verified": 728,
        "inner_fits_count": 672,
        "outer_refits_count": 56,
        "participants_count": 14,
        "total_predictions_count": 39496,
        "reproduced_fold": PRESELECTED_REPRO_FOLD,
        "reproduced_fold_differences": repro_diffs,
        "checks": checks,
        "all_checks_passed": True
    }

    verif_out_path = reports_dir / 'verification.json'
    verif_out_path.write_text(json.dumps(verification_summary, indent=2) + '\n', encoding='utf-8')
    print(f"\nVerification successfully PASSED! Wrote {verif_out_path.as_posix()}")
    for idx, c in enumerate(checks, 1):
        print(f"  [{idx}] {c}")


if __name__ == '__main__':
    main()
