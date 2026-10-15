"""Stage 4 Execution Runner: Retrospective within-patient median residual adaptation.

Executes the frozen protocol:
1. Preflight integrity checks on all Stage 2 & 3 inputs and configurations.
2. Temporal partitioning verification (7,709 calibration, 31,552 later evaluation, 235 purged).
3. Estimation of patient-specific median residual offsets on calibration origins.
4. Application of fixed scalar offset to base LOPO predictions on later evaluation origins.
5. Evaluation of all 5 methods on identical 31,552 later evaluation origins.
6. Shared paired participant bootstrap (2,000 resamples, seed 20261015).
7. Atomic writes to reports/stage4/ and data/processed/stage4/.
"""
import os
import sys
import json
import time
import hashlib
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List

# Enforce single-threaded execution to prevent CPU oversubscription
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np
import pandas as pd

from glucotwin.stage4.adaptation import (
    validate_calibration_gate,
    partition_participant_origins,
    compute_median_residual_offset,
    apply_offset,
    OffsetProvenance,
    hash_origin_ids,
)
from glucotwin.stage4.evaluation import (
    compute_per_participant_metrics,
    compute_cohort_aggregates,
    generate_shared_bootstrap_draws,
    paired_participant_bootstrap,
)


def sha256_file(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(p: Path, text: str):
    """Write text atomically via temporary file replacement."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(p)


def atomic_write_csv(p: Path, df: pd.DataFrame, index: bool = False):
    """Write dataframe atomically via temporary file replacement in full precision."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    df.to_csv(tmp, index=index, lineterminator='\n')
    os.replace(tmp, p)


def atomic_write_json(p: Path, obj: Any, indent: int = 2):
    """Write JSON atomically via temporary file replacement."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=indent)
    tmp.replace(p)


def run_stage4():
    start_time = time.time()
    print("=" * 70)
    print("Starting Stage 4: Retrospective Within-Patient Adaptation")
    print(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time))}")
    print("=" * 70)

    # Output paths
    reports_dir = ROOT / 'reports' / 'stage4'
    data_dir = ROOT / 'data' / 'processed' / 'stage4'
    pred_dir = data_dir / 'predictions'
    reports_dir.mkdir(parents=True, exist_ok=True)
    pred_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load protocol configuration and run preflight checks
    proto_path = ROOT / 'configs' / 'stage4_protocol.json'
    if not proto_path.exists():
        raise FileNotFoundError(f"Missing Stage 4 protocol config: {proto_path}")

    config = json.loads(proto_path.read_text(encoding='utf-8'))
    print("Verifying input hashes declared in configs/stage4_protocol.json...")

    preflight_records = []
    preflight_ok = True

    for rel_path, expected_hash in config['input_hashes'].items():
        full_path = ROOT / rel_path
        if not full_path.exists():
            preflight_records.append({
                'path': rel_path,
                'status': 'MISSING',
                'expected_sha256': expected_hash,
                'actual_sha256': None
            })
            preflight_ok = False
            print(f"  [FAIL] Missing file: {rel_path}")
            continue

        actual_hash = sha256_file(full_path)
        if actual_hash != expected_hash:
            preflight_records.append({
                'path': rel_path,
                'status': 'HASH_MISMATCH',
                'expected_sha256': expected_hash,
                'actual_sha256': actual_hash
            })
            preflight_ok = False
            print(f"  [FAIL] Hash mismatch: {rel_path}")
        else:
            preflight_records.append({
                'path': rel_path,
                'status': 'PASS',
                'expected_sha256': expected_hash,
                'actual_sha256': actual_hash
            })
            print(f"  [PASS] {rel_path}")

    preflight_report = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'overall_status': 'PASS' if preflight_ok else 'FAIL',
        'checks': preflight_records
    }
    atomic_write_json(reports_dir / 'preflight_report.json', preflight_report)

    if not preflight_ok:
        raise RuntimeError("Stage 4 preflight verification failed! See reports/stage4/preflight_report.json")

    # 2. Verify eligibility from personalization coverage
    cov_path = ROOT / 'reports' / 'stage2' / 'personalization_coverage.csv'
    cov_df = pd.read_csv(cov_path)
    print(f"Loaded personalization coverage for {len(cov_df)} participants.")

    elig_records = []
    for row in cov_df.itertuples():
        is_gate_ok = validate_calibration_gate(
            row.calibration_valid_coverage,
            row.paired_calibration_origins_5min,
            row.paired_later_origins_5min
        )
        elig_records.append({
            'participant_id': row.participant_id,
            'calibration_valid_minutes': row.calibration_valid_minutes,
            'calibration_expected_minutes': row.calibration_expected_minutes,
            'calibration_valid_coverage': row.calibration_valid_coverage,
            'paired_calibration_origins_5min': row.paired_calibration_origins_5min,
            'paired_later_origins_5min': row.paired_later_origins_5min,
            'purged_boundary_origins_5min': row.purged_boundary_origins_5min,
            'calibration_adequate': row.calibration_adequate,
            'later_adequate': row.later_adequate,
            'protocol_eligible': is_gate_ok and bool(row.protocol_eligible)
        })

    elig_df = pd.DataFrame(elig_records)
    atomic_write_csv(reports_dir / 'eligibility_summary.csv', elig_df)

    eligible_pids = sorted(elig_df[elig_df['protocol_eligible']]['participant_id'].tolist())
    expected_pids = config['cohort']['eligible_participant_ids']
    if eligible_pids != expected_pids:
        raise ValueError(f"Eligible participants mismatch: {eligible_pids} != {expected_pids}")
    print(f"All {len(eligible_pids)} participants met adequacy gates.")

    # 3. Load Stage 3 outer LOPO predictions
    stage3_pred_path = ROOT / 'data' / 'processed' / 'stage3_remediation' / 'predictions' / 'test_predictions.csv'
    preds_all = pd.read_csv(stage3_pred_path)
    print(f"Loaded {len(preds_all)} Stage 3 LOPO predictions.")

    # Load participant partition assignments
    pers_dir = ROOT / 'data' / 'processed' / 'stage2' / 'personalization'
    partition_dfs = []
    for pid in eligible_pids:
        p_file = pers_dir / f"p{pid:03d}.csv"
        if not p_file.exists():
            raise FileNotFoundError(f"Missing personalization file: {p_file}")
        p_df = pd.read_csv(p_file)
        partition_dfs.append(p_df[['origin_id', 'participant_id', 'first_valid_time', 'calibration_boundary', 'partition']])

    partition_df = pd.concat(partition_dfs, ignore_index=True)
    merged = pd.merge(preds_all, partition_df, on=['origin_id', 'participant_id'], how='inner')
    if len(merged) != len(preds_all):
        raise ValueError(f"Partition join count mismatch: {len(merged)} != {len(preds_all)}")

    cal_count = int((merged['partition'] == 'calibration').sum())
    eval_count = int((merged['partition'] == 'later_evaluation').sum())
    purge_count = int((merged['partition'] == 'purged_boundary').sum())

    print(f"Temporal Partitions: {cal_count} calibration, {eval_count} later evaluation, {purge_count} purged boundary.")
    if (cal_count, eval_count, purge_count) != (7709, 31552, 235):
        raise ValueError(f"Partition counts unexpected: ({cal_count}, {eval_count}, {purge_count}) != (7709, 31552, 235)")

    # 4. Compute patient-specific calibration offsets
    cal_subset = merged[merged['partition'] == 'calibration'].copy()
    offsets_records = []
    provenance_records = []

    # Load selected candidates for base model provenance
    cands_df = pd.read_csv(ROOT / 'reports' / 'stage3_remediation' / 'selected_candidates.csv')

    for pid in eligible_pids:
        p_cal = cal_subset[cal_subset['participant_id'] == pid]
        cal_true = p_cal['target_mg_dl'].to_numpy(dtype=np.float64)
        cal_pred_sensor = p_cal['ridge_sensor_only'].to_numpy(dtype=np.float64)
        cal_pred_comb = p_cal['ridge_sensor_plus_baseline'].to_numpy(dtype=np.float64)

        offset_sensor = compute_median_residual_offset(cal_true, cal_pred_sensor)
        offset_comb = compute_median_residual_offset(cal_true, cal_pred_comb)

        cal_origin_ids = p_cal['origin_id'].tolist()
        cal_hash = hash_origin_ids(cal_origin_ids)
        latest_cal_target = p_cal['issue_time'].max()  # issue time + 30m is target
        boundary = p_cal['calibration_boundary'].iloc[0]

        # Model provenance
        fold_name = f"holdout_{pid:03d}"
        cands_fold = cands_df[(cands_df['outer_fold'] == fold_name) & (cands_df['family'] == 'ridge')]
        spec_sensor = json.loads(cands_fold[cands_fold['variant'] == 'sensor_only']['selected_candidate_spec'].iloc[0])
        spec_comb = json.loads(cands_fold[cands_fold['variant'] == 'sensor_plus_baseline']['selected_candidate_spec'].iloc[0])
        sensor_alpha = float(spec_sensor.get('alpha', 1.0))
        comb_alpha = float(spec_comb.get('alpha', 1.0))

        offsets_records.append({
            'participant_id': pid,
            'n_calibration_origins': len(p_cal),
            'offset_sensor_only_mg_dl': offset_sensor,
            'offset_sensor_plus_baseline_mg_dl': offset_comb,
            'calibration_origin_ids_sha256': cal_hash,
            'calibration_boundary': boundary
        })

        prov_sensor = OffsetProvenance(
            participant_id=pid,
            variant='sensor_only',
            n_calibration_origins=len(p_cal),
            calibration_origin_ids_sha256=cal_hash,
            latest_calibration_target_time=latest_cal_target,
            calibration_boundary=boundary,
            offset_mg_dl=offset_sensor,
            base_model_provenance={'outer_fold': fold_name, 'model': 'Ridge', 'alpha': sensor_alpha}
        )
        prov_comb = OffsetProvenance(
            participant_id=pid,
            variant='sensor_plus_baseline',
            n_calibration_origins=len(p_cal),
            calibration_origin_ids_sha256=cal_hash,
            latest_calibration_target_time=latest_cal_target,
            calibration_boundary=boundary,
            offset_mg_dl=offset_comb,
            base_model_provenance={'outer_fold': fold_name, 'model': 'Ridge', 'alpha': comb_alpha}
        )
        provenance_records.extend([prov_sensor.to_dict(), prov_comb.to_dict()])

    offsets_df = pd.DataFrame(offsets_records)
    atomic_write_csv(data_dir / 'patient_offsets.csv', offsets_df)
    atomic_write_json(data_dir / 'offset_provenance.json', provenance_records)

    # Save calibration predictions
    atomic_write_csv(pred_dir / 'calibration_predictions.csv', cal_subset)
    print(f"Computed patient-specific offsets for all {len(eligible_pids)} participants.")

    # 5. Apply offsets to later evaluation origins
    later_subset = merged[merged['partition'] == 'later_evaluation'].copy()
    offset_map_sensor = dict(zip(offsets_df['participant_id'], offsets_df['offset_sensor_only_mg_dl']))
    offset_map_comb = dict(zip(offsets_df['participant_id'], offsets_df['offset_sensor_plus_baseline_mg_dl']))

    adapted_sensor_preds = []
    adapted_comb_preds = []

    for row in later_subset.itertuples():
        pid = row.participant_id
        off_s = offset_map_sensor[pid]
        off_c = offset_map_comb[pid]

        adapted_sensor_preds.append(row.ridge_sensor_only + off_s)
        adapted_comb_preds.append(row.ridge_sensor_plus_baseline + off_c)

    later_subset['persistence'] = later_subset['persistence']
    later_subset['ridge_sensor_only_unadapted'] = later_subset['ridge_sensor_only']
    later_subset['ridge_sensor_only_adapted'] = adapted_sensor_preds
    later_subset['ridge_sensor_plus_baseline_unadapted'] = later_subset['ridge_sensor_plus_baseline']
    later_subset['ridge_sensor_plus_baseline_adapted'] = adapted_comb_preds

    eval_columns = [
        'origin_id',
        'participant_id',
        'issue_time',
        'target_mg_dl',
        'persistence',
        'ridge_sensor_only_unadapted',
        'ridge_sensor_only_adapted',
        'ridge_sensor_plus_baseline_unadapted',
        'ridge_sensor_plus_baseline_adapted'
    ]
    eval_predictions_df = later_subset[eval_columns].copy()
    atomic_write_csv(pred_dir / 'later_evaluation_predictions.csv', eval_predictions_df)
    print(f"Saved {len(eval_predictions_df)} later evaluation predictions across 5 methods.")

    # 6. Evaluate point metrics on later evaluation origins
    methods = [
        'persistence',
        'ridge_sensor_only_unadapted',
        'ridge_sensor_only_adapted',
        'ridge_sensor_plus_baseline_unadapted',
        'ridge_sensor_plus_baseline_adapted'
    ]

    per_person_df = compute_per_participant_metrics(eval_predictions_df, methods, eligible_pids)
    atomic_write_csv(reports_dir / 'per_participant_metrics.csv', per_person_df)

    cohort_aggregates_df = compute_cohort_aggregates(per_person_df, methods)
    atomic_write_csv(reports_dir / 'aggregate_metrics.csv', cohort_aggregates_df)

    # 7. Adaptation Comparisons and Bootstrap
    comparisons = [
        ('Ridge Sensor-Only: Adapted vs Unadapted', 'ridge_sensor_only_adapted', 'ridge_sensor_only_unadapted'),
        ('Ridge Combined: Adapted vs Unadapted', 'ridge_sensor_plus_baseline_adapted', 'ridge_sensor_plus_baseline_unadapted'),
        ('Ridge Sensor-Only Unadapted vs Persistence', 'ridge_sensor_only_unadapted', 'persistence'),
        ('Ridge Sensor-Only Adapted vs Persistence', 'ridge_sensor_only_adapted', 'persistence'),
        ('Ridge Combined Unadapted vs Persistence', 'ridge_sensor_plus_baseline_unadapted', 'persistence'),
        ('Ridge Combined Adapted vs Persistence', 'ridge_sensor_plus_baseline_adapted', 'persistence'),
    ]

    # Shared draw-index matrix
    boot_config = config['evaluation']['bootstrap']
    n_resamples = boot_config['n_resamples']
    seed = boot_config['seed']
    draw_indices, draw_hash = generate_shared_bootstrap_draws(
        n_participants=len(eligible_pids),
        n_resamples=n_resamples,
        seed=seed
    )
    # Save draw matrix
    np.save(data_dir / 'bootstrap_draw_indices.npy', draw_indices)

    bootstrap_results = {
        'seed': seed,
        'n_resamples': n_resamples,
        'draw_matrix_shape': list(draw_indices.shape),
        'draw_matrix_sha256': draw_hash,
        'participant_order': eligible_pids,
        'quantile_method': boot_config['quantile_method'],
        'alpha': boot_config['alpha'],
        'comparisons': []
    }

    comp_records = []

    for name, method_a, method_b in comparisons:
        boot_res = paired_participant_bootstrap(
            per_person_df=per_person_df,
            method_a=method_a,
            method_b=method_b,
            comparison_name=name,
            draw_indices=draw_indices,
            alpha=boot_config['alpha'],
            quantile_method=boot_config['quantile_method']
        )
        bootstrap_results['comparisons'].append(boot_res)

        # Retrieve window-weighted metrics for delta
        agg_a = cohort_aggregates_df[cohort_aggregates_df['method'] == method_a].iloc[0]
        agg_b = cohort_aggregates_df[cohort_aggregates_df['method'] == method_b].iloc[0]

        comp_records.append({
            'comparison_name': name,
            'method_a': method_a,
            'method_b': method_b,
            'delta_equal_mae_mg_dl': boot_res['mean_delta_mae'],
            'mae_95_ci_lower': boot_res['mae_95_ci'][0],
            'mae_95_ci_upper': boot_res['mae_95_ci'][1],
            'delta_equal_rmse_mg_dl': boot_res['mean_delta_rmse'],
            'rmse_95_ci_lower': boot_res['rmse_95_ci'][0],
            'rmse_95_ci_upper': boot_res['rmse_95_ci'][1],
            'delta_window_mae_mg_dl': agg_a['window_weighted_mae_mg_dl'] - agg_b['window_weighted_mae_mg_dl'],
            'delta_window_rmse_mg_dl': agg_a['window_weighted_rmse_mg_dl'] - agg_b['window_weighted_rmse_mg_dl'],
            'participants_improved_mae': boot_res['participants_improved_mae'],
            'participants_worsened_mae': boot_res['participants_worsened_mae'],
            'participants_tied_mae': boot_res['participants_tied_mae'],
            'participants_improved_rmse': boot_res['participants_improved_rmse'],
            'participants_worsened_rmse': boot_res['participants_worsened_rmse'],
            'participants_tied_rmse': boot_res['participants_tied_rmse'],
        })

    comp_df = pd.DataFrame(comp_records)
    atomic_write_csv(reports_dir / 'adaptation_comparison.csv', comp_df)
    atomic_write_json(reports_dir / 'bootstrap_summary.json', bootstrap_results)

    # 8. Execution Record and Run Manifest
    elapsed = time.time() - start_time
    run_manifest = {
        'protocol': config['protocol'],
        'execution_timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'elapsed_seconds': elapsed,
        'environment': {
            'platform': platform.platform(),
            'python_version': sys.version,
            'numpy_version': np.__version__,
            'pandas_version': pd.__version__,
        },
        'cohort_participants': eligible_pids,
        'total_evaluated_origins': eval_count,
        'shared_bootstrap_draw_sha256': draw_hash,
        'generated_files': {
            'configs/stage4_protocol.json': sha256_file(proto_path),
            'reports/stage4/preflight_report.json': sha256_file(reports_dir / 'preflight_report.json'),
            'reports/stage4/eligibility_summary.csv': sha256_file(reports_dir / 'eligibility_summary.csv'),
            'reports/stage4/per_participant_metrics.csv': sha256_file(reports_dir / 'per_participant_metrics.csv'),
            'reports/stage4/aggregate_metrics.csv': sha256_file(reports_dir / 'aggregate_metrics.csv'),
            'reports/stage4/adaptation_comparison.csv': sha256_file(reports_dir / 'adaptation_comparison.csv'),
            'reports/stage4/bootstrap_summary.json': sha256_file(reports_dir / 'bootstrap_summary.json'),
        }
    }
    atomic_write_json(reports_dir / 'run_manifest.json', run_manifest)

    # Markdown execution record
    exec_record_text = f"""# Stage 4 Execution Record

- **Protocol Version**: `{config['protocol']}`
- **Execution Date**: `{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}`
- **Elapsed Time**: `{elapsed:.2f} seconds`
- **Platform**: `{platform.platform()}`
- **Python**: `{sys.version}`
- **Preselected Reproduction Fold**: `{config['cohort']['preselected_reproduction_fold']}` (Participant `{config['cohort']['preselected_reproduction_participant']}`)

## Cohort & Origin Counts
- **Total Eligible Participants**: {len(eligible_pids)}
- **Paired Calibration Origins (48h)**: {cal_count}
- **Paired Later Evaluation Origins**: {eval_count}
- **Purged Boundary-Straddling Origins**: {purge_count}
- **Total Processed Origins**: {cal_count + eval_count + purge_count}

## Aggregate Later-Period Evaluation (N = {eval_count})
| Method | Equal-Person MAE (mg/dL) | Equal-Person RMSE (mg/dL) | Window-Weighted MAE (mg/dL) | Window-Weighted RMSE (mg/dL) |
|---|---|---|---|---|
"""
    for row in cohort_aggregates_df.itertuples():
        exec_record_text += f"| {row.method} | {row.primary_equal_person_mae_mg_dl:.4f} | {row.secondary_equal_person_rmse_mg_dl:.4f} | {row.window_weighted_mae_mg_dl:.4f} | {row.window_weighted_rmse_mg_dl:.4f} |\n"

    exec_record_text += "\n## Adaptation Comparison Deltas (delta = adapted - unadapted; negative = improvement)\n"
    exec_record_text += "| Comparison | Mean Delta MAE (95% CI) | Improved / Worsened / Tied (MAE) |\n|---|---|---|\n"
    for row in comp_df.itertuples():
        exec_record_text += f"| {row.comparison_name} | {row.delta_equal_mae_mg_dl:+.4f} [{row.mae_95_ci_lower:+.4f}, {row.mae_95_ci_upper:+.4f}] | {row.participants_improved_mae} / {row.participants_worsened_mae} / {row.participants_tied_mae} |\n"

    exec_record_text += f"\n- **Shared Bootstrap Draw Matrix SHA-256**: `{draw_hash}`\n"
    atomic_write_text(reports_dir / 'execution_record.md', exec_record_text)

    print("=" * 70)
    print("Stage 4 Run Completed Successfully!")
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"Results written to: {reports_dir}")
    print("=" * 70)


if __name__ == '__main__':
    run_stage4()
