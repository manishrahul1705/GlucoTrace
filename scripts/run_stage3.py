"""Stage 3 execution runner: fits 728 estimators across 14 LOPO folds with strict preflight integrity.

Outputs to remediation directories with atomic writes, full float64 precision, and restart-only semantics.
"""
import os
import sys
import json
import time
import shutil
import argparse
import platform
import importlib.metadata
from pathlib import Path

# Thread limits to prevent CPU oversubscription and deadlock
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from glucotwin.stage3.integrity import (
    SENSOR_FEATURES,
    BASELINE_FEATURES,
    COMBINED_FEATURES,
    TARGET_COL,
    EXPECTED_PARTICIPANTS,
    run_preflight_checks,
    sha256_file
)
from glucotwin.stage3.training import (
    get_feature_columns,
    fit_estimator,
    predict_estimator,
    get_participant_indices
)
from glucotwin.stage3.selection import (
    compute_equal_person_val_mae,
    select_candidate,
    evaluate_inner_candidate
)
from glucotwin.stage3.metrics import (
    compute_persistence_predictions,
    compute_trend_predictions,
    compute_per_participant_metrics,
    compute_aggregate_metrics,
    compute_paired_participant_bootstrap
)


def atomic_write_text(p: Path, text: str):
    """Write text atomically via temporary file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, p)


def atomic_write_csv(p: Path, df: pd.DataFrame, index: bool = False):
    """Write DataFrame to CSV atomically via temporary file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    df.to_csv(tmp, index=index, lineterminator='\n')
    os.replace(tmp, p)


def main():
    parser = argparse.ArgumentParser(description="GlucoTwin Stage 3 Benchmark Runner (Restart-Only)")
    parser.add_argument('--output-dir', type=str, default='reports/stage3_remediation',
                        help="Output directory for reports and figures")
    parser.add_argument('--data-dir', type=str, default='data/processed/stage3_remediation',
                        help="Output directory for local predictions")
    parser.add_argument('--config', type=str, default='configs/stage3_run.json',
                        help="Path to Stage 3 configuration")
    parser.add_argument('--split-manifest', type=str, default='reports/stage2/split_manifest.json',
                        help="Path to split manifest")
    parser.add_argument('--restart', action='store_true',
                        help="Restart run from scratch, clearing any existing output directory")
    parser.add_argument('--force', action='store_true',
                        help="Force overwrite of existing output directory")
    args = parser.parse_args()

    start_time = time.time()
    start_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time))

    out_dir = ROOT / args.output_dir
    data_dir = ROOT / args.data_dir
    pred_dir = data_dir / 'predictions'
    fig_dir = out_dir / 'figures'
    cfg_path = ROOT / args.config
    split_path = ROOT / args.split_manifest
    sensor_csv = ROOT / 'data/processed/stage2/sensor_only.csv'
    comb_csv = ROOT / 'data/processed/stage2/sensor_plus_baseline.csv'

    print("================================================================")
    print("  GlucoTwin Stage 3 Retrospective Benchmark Runner (Remediation)")
    print("================================================================")
    print(f"Output directory : {out_dir.as_posix()}")
    print(f"Prediction dir   : {pred_dir.as_posix()}")
    print(f"Execution policy : Restart-only (non-resumable atomic execution)")

    # Enforce restart-only execution policy
    if out_dir.exists():
        existing_files = list(out_dir.glob('*'))
        if existing_files:
            if not (args.restart or args.force):
                print(f"ERROR: Output directory {out_dir} already exists and contains files.")
                print("GlucoTwin Stage 3 uses a strict restart-only execution policy.")
                print("Pass --restart or --force to clean the directory and start fresh.")
                sys.exit(1)
            else:
                print(f"Restart flag provided: clearing existing contents of {out_dir}...")
                for item in out_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

    out_dir.mkdir(parents=True, exist_ok=True)
    pred_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 1. Enforce preflight integrity before any model fit
    print("\n[1/5] Executing preflight integrity checks...")
    preflight_report = run_preflight_checks(
        root=ROOT,
        config_path=cfg_path,
        split_path=split_path,
        sensor_csv=sensor_csv,
        combined_csv=comb_csv
    )
    preflight_report['timestamp'] = start_iso
    preflight_report['execution_policy'] = "restart_only"
    atomic_write_text(out_dir / 'preflight_report.json', json.dumps(preflight_report, indent=2) + '\n')
    print("Preflight check passed: all protocol hashes, feature tables, and metadata verified.")

    # Record environment metadata
    env_info = {
        "os": platform.platform(),
        "python": sys.version,
        "python_version": platform.python_version(),
        "numpy": importlib.metadata.version('numpy'),
        "pandas": importlib.metadata.version('pandas'),
        "scikit-learn": importlib.metadata.version('scikit-learn'),
        "scipy": importlib.metadata.version('scipy'),
        "matplotlib": importlib.metadata.version('matplotlib'),
        "joblib": importlib.metadata.version('joblib'),
        "threadpoolctl": importlib.metadata.version('threadpoolctl'),
        "timestamp_start": start_iso,
        "execution_policy": "restart_only",
        "precision": "float64_full_precision_throughout"
    }
    atomic_write_text(out_dir / 'environment.json', json.dumps(env_info, indent=2) + '\n')

    # Load configuration and split manifest
    config = json.loads(cfg_path.read_text(encoding='utf-8'))
    split_manifest = json.loads(split_path.read_text(encoding='utf-8'))

    # Load prepared feature matrices
    print("\n[2/5] Loading prepared feature matrices...")
    df_sensor = pd.read_csv(sensor_csv).sort_values(['participant_id', 'issue_time']).reset_index(drop=True)
    df_combined = pd.read_csv(comb_csv).sort_values(['participant_id', 'issue_time']).reset_index(drop=True)

    n_origins = len(df_sensor)
    pids = sorted(df_sensor['participant_id'].unique().tolist())
    print(f"Paired 5-minute origins: {n_origins} across {len(pids)} participants.")

    # Prediction containers
    predictions = {
        'origin_id': df_sensor['origin_id'].to_numpy(),
        'participant_id': df_sensor['participant_id'].to_numpy(),
        'issue_time': df_sensor['issue_time'].to_numpy(),
        'target_mg_dl': df_sensor[TARGET_COL].to_numpy(dtype=float),
        'persistence': compute_persistence_predictions(df_sensor),
        'trend': compute_trend_predictions(df_sensor),
        'ridge_sensor_only': np.full(n_origins, np.nan, dtype=float),
        'ridge_sensor_plus_baseline': np.full(n_origins, np.nan, dtype=float),
        'hist_gradient_boosting_sensor_only': np.full(n_origins, np.nan, dtype=float),
        'hist_gradient_boosting_sensor_plus_baseline': np.full(n_origins, np.nan, dtype=float),
    }

    fit_ledger = []
    inner_scores_records = []
    selected_candidates_records = []
    fit_counter = 0

    families = ['ridge', 'hist_gradient_boosting']
    variants = ['sensor_only', 'sensor_plus_baseline']
    outer_folds = split_manifest['folds']

    print(f"\n[3/5] Executing {len(outer_folds)} LOPO outer folds (728 planned fits)...")

    for outer_idx, outer_fold in enumerate(outer_folds):
        outer_fold_name = outer_fold['outer_fold']
        test_pids = outer_fold['test']['participants']
        assert len(test_pids) == 1
        held_out_pid = test_pids[0]
        outer_train_pids = outer_fold['train']['participants']
        assert held_out_pid not in outer_train_pids

        test_indices = get_participant_indices(df_sensor, [held_out_pid])
        train_indices = get_participant_indices(df_sensor, outer_train_pids)
        inner_folds = outer_fold['inner_folds']

        print(f"  Fold [{outer_idx+1:02d}/14] {outer_fold_name} (held-out participant {held_out_pid})")

        for family in families:
            cand_list = config['execution_parameters']['methods'][family]['candidates']
            for variant in variants:
                features = get_feature_columns(variant)
                df_src = df_sensor if variant == 'sensor_only' else df_combined

                candidate_evals = []

                # Inner cross-validation selection
                for cand in cand_list:
                    cand_id = cand['candidate_id']
                    mean_val_mae, inner_ledger, fit_counter = evaluate_inner_candidate(
                        family=family,
                        candidate=cand,
                        inner_folds=inner_folds,
                        df_src=df_src,
                        features=features,
                        target_col=TARGET_COL,
                        outer_train_pids=outer_train_pids,
                        outer_fold_name=outer_fold_name,
                        held_out_pid=held_out_pid,
                        variant=variant,
                        fit_counter_start=fit_counter
                    )
                    fit_ledger.extend(inner_ledger)
                    candidate_evals.append((cand_id, mean_val_mae, cand))

                    inner_scores_records.append({
                        'outer_fold': outer_fold_name,
                        'held_out_pid': held_out_pid,
                        'family': family,
                        'variant': variant,
                        'candidate_id': cand_id,
                        'equal_person_val_mae': mean_val_mae,
                        'candidate_spec': json.dumps(cand, sort_keys=True)
                    })

                # Candidate selection: minimal validation MAE, tie-broken by earliest candidate_id
                selected_cand_id, best_val_score, selected_cand = select_candidate(candidate_evals)

                selected_candidates_records.append({
                    'outer_fold': outer_fold_name,
                    'held_out_pid': held_out_pid,
                    'family': family,
                    'variant': variant,
                    'selected_candidate_id': selected_cand_id,
                    'validation_mae': best_val_score,
                    'selected_candidate_spec': json.dumps(selected_cand, sort_keys=True)
                })

                # Outer Refit on outer-training set
                X_train = df_src.loc[train_indices, features].to_numpy(dtype=float)
                y_train = df_src.loc[train_indices, TARGET_COL].to_numpy(dtype=float)
                X_test = df_src.loc[test_indices, features].to_numpy(dtype=float)

                t_refit_start = time.time()
                final_est, final_scaler = fit_estimator(family, selected_cand, X_train, y_train)
                t_refit_dur = time.time() - t_refit_start

                preds_test = predict_estimator(final_est, final_scaler, X_test)

                fit_counter += 1
                fit_ledger.append({
                    'fit_index': fit_counter,
                    'stage': 'outer_refit',
                    'outer_fold': outer_fold_name,
                    'held_out_pid': held_out_pid,
                    'inner_fold': -1,
                    'family': family,
                    'variant': variant,
                    'candidate_id': selected_cand_id,
                    'n_train_rows': len(train_indices),
                    'n_val_test_rows': len(test_indices),
                    'duration_sec': round(t_refit_dur, 4)
                })

                method_col = f"{family}_{variant}"
                predictions[method_col][test_indices] = preds_test

    print(f"\nAll fits executed successfully: total {fit_counter} fits (672 inner + 56 outer refits).")
    assert fit_counter == 728, f"Expected 728 fits, observed {fit_counter}"

    # Build predictions dataframe
    pred_df = pd.DataFrame(predictions)
    for col in [
        'persistence', 'trend', 'ridge_sensor_only', 'ridge_sensor_plus_baseline',
        'hist_gradient_boosting_sensor_only', 'hist_gradient_boosting_sensor_plus_baseline'
    ]:
        assert not pred_df[col].isna().any(), f"NaN detected in {col} predictions"

    # Save local predictions
    atomic_write_csv(pred_dir / 'test_predictions.csv', pred_df)

    # Save fit ledger and candidate logs
    atomic_write_csv(out_dir / 'fit_ledger.csv', pd.DataFrame(fit_ledger))
    atomic_write_csv(out_dir / 'inner_selection_scores.csv', pd.DataFrame(inner_scores_records))
    atomic_write_csv(out_dir / 'selected_candidates.csv', pd.DataFrame(selected_candidates_records))

    # Evaluate metrics in full float64 precision
    print("\n[4/5] Computing metrics in full float64 precision...")
    methods = [
        'persistence', 'trend',
        'ridge_sensor_only', 'ridge_sensor_plus_baseline',
        'hist_gradient_boosting_sensor_only', 'hist_gradient_boosting_sensor_plus_baseline'
    ]

    per_person_df = compute_per_participant_metrics(pred_df, methods, pids)
    atomic_write_csv(out_dir / 'per_participant_metrics.csv', per_person_df)

    agg_df = compute_aggregate_metrics(per_person_df, pred_df, methods)
    atomic_write_csv(out_dir / 'aggregate_metrics.csv', agg_df)

    print("\n=== Aggregate Performance Summary (Remediation) ===")
    display_cols = ['method', 'primary_equal_person_mae_mg_dl', 'secondary_equal_person_rmse_mg_dl',
                    'persistence_relative_skill_pct', 'total_out_of_range_predictions']
    print(agg_df[display_cols].to_string(index=False))

    # Fusion comparison and paired participant bootstrap
    print("\nComputing paired participant bootstrap...")
    boot_seed = config['execution_parameters']['uncertainty_estimation']['seed']
    boot_resamples = config['execution_parameters']['uncertainty_estimation']['resamples']

    fusion_records = []
    bootstrap_results = {}

    for fam in families:
        boot_res = compute_paired_participant_bootstrap(
            per_person_df=per_person_df,
            family=fam,
            seed=boot_seed,
            n_resamples=boot_resamples
        )
        bootstrap_results[fam] = boot_res

        fusion_records.append({
            'family': fam,
            'metric': 'MAE',
            'mean_sensor_mg_dl': boot_res['mean_sensor_mae'],
            'mean_combined_mg_dl': boot_res['mean_combined_mae'],
            'mean_paired_difference_mg_dl': boot_res['mean_delta_mae'],
            'ci_95_lower_mg_dl': boot_res['mae_95_ci'][0],
            'ci_95_upper_mg_dl': boot_res['mae_95_ci'][1],
            'participants_improved': boot_res['participants_improved_mae'],
            'participants_worsened': boot_res['participants_worsened_mae'],
            'participants_tied': boot_res['participants_tied_mae'],
            'sign_convention': 'combined_minus_sensor (negative = improvement)'
        })

        fusion_records.append({
            'family': fam,
            'metric': 'RMSE',
            'mean_sensor_mg_dl': boot_res['mean_sensor_rmse'],
            'mean_combined_mg_dl': boot_res['mean_combined_rmse'],
            'mean_paired_difference_mg_dl': boot_res['mean_delta_rmse'],
            'ci_95_lower_mg_dl': boot_res['rmse_95_ci'][0],
            'ci_95_upper_mg_dl': boot_res['rmse_95_ci'][1],
            'participants_improved': boot_res['participants_improved_rmse'],
            'participants_worsened': boot_res['participants_worsened_rmse'],
            'participants_tied': boot_res['participants_tied_rmse'],
            'sign_convention': 'combined_minus_sensor (negative = improvement)'
        })

    fusion_df = pd.DataFrame(fusion_records)
    atomic_write_csv(out_dir / 'fusion_comparison.csv', fusion_df)
    atomic_write_text(out_dir / 'bootstrap_summary.json', json.dumps(bootstrap_results, indent=2) + '\n')

    print("\n=== Fusion Comparison ===")
    print(fusion_df[['family', 'metric', 'mean_paired_difference_mg_dl', 'ci_95_lower_mg_dl', 'ci_95_upper_mg_dl', 'participants_improved', 'participants_worsened']].to_string(index=False))

    # Generate figures
    print("\n[5/5] Generating figures...")
    # 1. Per-participant MAE by method
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(pids))
    width = 0.14
    for idx, m in enumerate(methods):
        sub_p = per_person_df[per_person_df['method'] == m].sort_values('participant_id')
        ax.bar(x + idx * width, sub_p['mae_mg_dl'], width, label=m)
    ax.set_xlabel('Participant ID')
    ax.set_ylabel('MAE (mg/dL)')
    ax.set_title('Per-Participant 30-min Forecast MAE by Method (LOPO Outer Test - Remediation)')
    ax.set_xticks(x + width * 2.5)
    ax.set_xticklabels([f"p{p:03d}" for p in pids])
    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(fig_dir / 'per_participant_mae.png', dpi=200)
    plt.close()

    # 2. Paired fusion differences
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for idx, fam in enumerate(families):
        s_m = f"{fam}_sensor_only"
        c_m = f"{fam}_sensor_plus_baseline"
        s_vals = per_person_df[per_person_df['method'] == s_m].sort_values('participant_id')['mae_mg_dl'].values
        c_vals = per_person_df[per_person_df['method'] == c_m].sort_values('participant_id')['mae_mg_dl'].values
        diffs = c_vals - s_vals
        axes[idx].bar([f"p{p:03d}" for p in pids], diffs, color=['green' if d < 0 else 'red' for d in diffs])
        axes[idx].axhline(0, color='black', linestyle='--', linewidth=0.8)
        axes[idx].axhline(np.mean(diffs), color='blue', linestyle=':', label=f"Mean diff: {np.mean(diffs):+.2f} mg/dL")
        axes[idx].set_xlabel('Participant ID')
        axes[idx].set_ylabel('Combined - Sensor MAE (mg/dL)')
        axes[idx].set_title(f"{fam.replace('_', ' ').title()}: Baseline Fusion Delta (Negative = Improvement)")
        axes[idx].legend()
    plt.tight_layout()
    plt.savefig(fig_dir / 'paired_fusion_differences.png', dpi=200)
    plt.close()

    # 3. Aggregate metrics bar chart
    fig, ax = plt.subplots(figsize=(10, 5))
    x_agg = np.arange(len(methods))
    ax.bar(x_agg - 0.2, agg_df['primary_equal_person_mae_mg_dl'], 0.4, label='Equal-Person MAE (mg/dL)', color='steelblue')
    ax.bar(x_agg + 0.2, agg_df['secondary_equal_person_rmse_mg_dl'], 0.4, label='Equal-Person RMSE (mg/dL)', color='coral')
    ax.set_xticks(x_agg)
    ax.set_xticklabels(methods, rotation=25, ha='right')
    ax.set_ylabel('Error (mg/dL)')
    ax.set_title('Aggregate Outer-Test Forecasting Performance (n=14 Participants - Remediation)')
    ax.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / 'aggregate_metrics.png', dpi=200)
    plt.close()

    # 4. Representative forecast traces
    rep_pid = 12
    rep_sub = pred_df[pred_df['participant_id'] == rep_pid].iloc[100:300]
    fig, ax = plt.subplots(figsize=(14, 6))
    time_points = np.arange(len(rep_sub)) * 5
    ax.plot(time_points, rep_sub['target_mg_dl'], 'k-', label='Observed Target (t+30m)', linewidth=2.0)
    ax.plot(time_points, rep_sub['persistence'], 'g--', label='Persistence g(t)', alpha=0.7)
    ax.plot(time_points, rep_sub['trend'], 'm:', label='Trailing Linear Trend', alpha=0.7)
    ax.plot(time_points, rep_sub['ridge_sensor_only'], 'b-', label='Ridge (Sensor Only)', alpha=0.8)
    ax.plot(time_points, rep_sub['hist_gradient_boosting_sensor_only'], 'r-', label='HistGB (Sensor Only)', alpha=0.8)
    ax.set_xlabel('Elapsed Time (minutes)')
    ax.set_ylabel('Glucose (mg/dL)')
    ax.set_title(f'Representative Continuous Forecast Traces: Participant p{rep_pid:03d} (200 Sequential 5-min Origins)')
    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(fig_dir / 'representative_forecast_traces.png', dpi=200)
    plt.close()

    total_duration = time.time() - start_time
    print(f"\nExecution finished in {total_duration:.2f} seconds.")

    # Write execution record
    exec_record = f"""# Stage 3 Remediation Execution Record

## Execution Environment
- Operating System: {platform.platform()}
- Python: {platform.python_version()}
- scikit-learn: {importlib.metadata.version('scikit-learn')}
- numpy: {importlib.metadata.version('numpy')}
- pandas: {importlib.metadata.version('pandas')}
- scipy: {importlib.metadata.version('scipy')}
- matplotlib: {importlib.metadata.version('matplotlib')}
- Duration: {total_duration:.2f} seconds
- Total learned-estimator fits: {fit_counter} (672 inner selection + 56 outer refits)
- Execution Policy: Restart-only (non-resumable)
- Precision Policy: float64 full precision throughout selection and metrics

## Preflight Verification Status
- Verified Stage 2 Checkpoint: `029b530f7616c50fe634f1c695e25753b4041410ae611cfe7fd6019bc6c0147c`
- Verified Original Linux Checkpoint: `b871a7de0af394410c2a4484710f809c77e1be24c60291395de28f5fd7c1d8ce`
- Stage 2 Protocol SHA256: `{sha256_file(ROOT / 'configs/stage2_protocol.json')}`
- Split Manifest SHA256: `{sha256_file(ROOT / 'reports/stage2/split_manifest.json')}`
- Source Provenance SHA256: `b9006433b4386b2524e0c2d5b97bb6e1c6eb821013eacf63823145ad68c2da73`

## Budget Accounting
- Outer Folds: 14 planned / 14 executed
- Inner Folds: 3 per outer fold (42 fold evaluations)
- Candidate Grid: 4 per family/variant (16 candidate configurations per outer fold)
- Inner Fits: 672 planned / 672 executed
- Outer Refits: 56 planned / 56 executed
- Total Fits: 728 planned / 728 executed
- Missing or Failed Fits: 0
"""
    atomic_write_text(out_dir / 'execution_record.md', exec_record)

    # Write run manifest
    run_manifest = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'total_duration_sec': round(total_duration, 2),
        'execution_policy': 'restart_only',
        'fits_planned': 728,
        'fits_completed': fit_counter,
        'outer_folds': 14,
        'participants': pids,
        'total_paired_origins': n_origins,
        'methods_evaluated': methods,
        'precision_retained': 'float64_full',
        'files_generated': [
            (out_dir / 'preflight_report.json').relative_to(ROOT).as_posix(),
            (out_dir / 'fit_ledger.csv').relative_to(ROOT).as_posix(),
            (out_dir / 'inner_selection_scores.csv').relative_to(ROOT).as_posix(),
            (out_dir / 'selected_candidates.csv').relative_to(ROOT).as_posix(),
            (out_dir / 'per_participant_metrics.csv').relative_to(ROOT).as_posix(),
            (out_dir / 'aggregate_metrics.csv').relative_to(ROOT).as_posix(),
            (out_dir / 'fusion_comparison.csv').relative_to(ROOT).as_posix(),
            (out_dir / 'bootstrap_summary.json').relative_to(ROOT).as_posix(),
            (out_dir / 'execution_record.md').relative_to(ROOT).as_posix(),
            (out_dir / 'environment.json').relative_to(ROOT).as_posix(),
            (fig_dir / 'per_participant_mae.png').relative_to(ROOT).as_posix(),
            (fig_dir / 'paired_fusion_differences.png').relative_to(ROOT).as_posix(),
            (fig_dir / 'aggregate_metrics.png').relative_to(ROOT).as_posix(),
            (fig_dir / 'representative_forecast_traces.png').relative_to(ROOT).as_posix(),
            (pred_dir / 'test_predictions.csv').relative_to(ROOT).as_posix(),
        ]
    }
    atomic_write_text(out_dir / 'run_manifest.json', json.dumps(run_manifest, indent=2) + '\n')
    print("Stage 3 remediation run finished successfully!")


if __name__ == '__main__':
    main()
