"""Performance evaluation, metric aggregation, baseline models, and paired participant bootstrap.

Preserves full float64 precision throughout all calculations; rounding is applied strictly at export/display boundaries.
"""
from typing import Dict, List, Any
import numpy as np
import pandas as pd


VALID_GLUCOSE_RANGE = (40.0, 400.0)


def compute_persistence_predictions(df_sensor: pd.DataFrame) -> np.ndarray:
    """Evaluate 30-minute persistence baseline: g_hat(t+30) = g(t) = glucose_lag_0m."""
    return df_sensor['glucose_lag_0m'].to_numpy(dtype=float)


def compute_trend_predictions(df_sensor: pd.DataFrame) -> np.ndarray:
    """Evaluate 30-minute linear trend baseline: g_hat(t+30) = g(t) + 30 * glucose_slope_15m."""
    lag_0 = df_sensor['glucose_lag_0m'].to_numpy(dtype=float)
    slope_15 = df_sensor['glucose_slope_15m'].to_numpy(dtype=float)
    return lag_0 + 30.0 * slope_15


def compute_point_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    """Calculate MAE, RMSE, mean signed error, and boundary counts in full precision."""
    residuals = y_pred - y_true
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    mse = float(np.mean(residuals))
    non_finite = int(np.sum(~np.isfinite(y_pred)))
    out_of_range = int(np.sum((y_pred < VALID_GLUCOSE_RANGE[0]) | (y_pred > VALID_GLUCOSE_RANGE[1])))

    return {
        'mae': mae,
        'rmse': rmse,
        'mean_signed_error': mse,
        'non_finite_count': non_finite,
        'out_of_range_count': out_of_range
    }


def compute_per_participant_metrics(
    pred_df: pd.DataFrame,
    methods: List[str],
    participants: List[int]
) -> pd.DataFrame:
    """Calculate evaluation metrics for each participant and method."""
    records = []
    for pid in participants:
        sub = pred_df[pred_df['participant_id'] == pid]
        y_true = sub['target_mg_dl'].to_numpy(dtype=float)
        n_p = len(sub)

        for m in methods:
            y_hat = sub[m].to_numpy(dtype=float)
            m_stats = compute_point_metrics(y_true, y_hat)
            records.append({
                'participant_id': pid,
                'method': m,
                'origin_count': n_p,
                'mae_mg_dl': m_stats['mae'],
                'rmse_mg_dl': m_stats['rmse'],
                'mean_signed_error_mg_dl': m_stats['mean_signed_error'],
                'non_finite_count': m_stats['non_finite_count'],
                'out_of_range_count': m_stats['out_of_range_count']
            })

    return pd.DataFrame(records)


def compute_aggregate_metrics(
    per_person_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    methods: List[str]
) -> pd.DataFrame:
    """Calculate primary equal-person averages and secondary window-weighted metrics."""
    agg_records = []
    base_mae = per_person_df[per_person_df['method'] == 'persistence']['mae_mg_dl'].mean()
    base_trend_mae = per_person_df[per_person_df['method'] == 'trend']['mae_mg_dl'].mean()

    for m in methods:
        m_df = per_person_df[per_person_df['method'] == m]
        eq_mae = float(m_df['mae_mg_dl'].mean())
        eq_rmse = float(m_df['rmse_mg_dl'].mean())
        eq_mse = float(m_df['mean_signed_error_mg_dl'].mean())

        # Window-weighted across all paired origins
        all_res = pred_df[m].to_numpy(dtype=float) - pred_df['target_mg_dl'].to_numpy(dtype=float)
        ww_mae = float(np.mean(np.abs(all_res)))
        ww_rmse = float(np.sqrt(np.mean(all_res ** 2)))
        ww_mse = float(np.mean(all_res))

        # Skill scores relative to baselines
        skill_pers = float((base_mae - eq_mae) / base_mae * 100.0)
        skill_trend = float((base_trend_mae - eq_mae) / base_trend_mae * 100.0)

        tot_nan = int(m_df['non_finite_count'].sum())
        tot_oor = int(m_df['out_of_range_count'].sum())

        agg_records.append({
            'method': m,
            'primary_equal_person_mae_mg_dl': eq_mae,
            'secondary_equal_person_rmse_mg_dl': eq_rmse,
            'equal_person_mean_signed_error_mg_dl': eq_mse,
            'window_weighted_mae_mg_dl': ww_mae,
            'window_weighted_rmse_mg_dl': ww_rmse,
            'window_weighted_mean_signed_error_mg_dl': ww_mse,
            'persistence_relative_skill_pct': skill_pers,
            'trend_relative_skill_pct': skill_trend,
            'total_non_finite_predictions': tot_nan,
            'total_out_of_range_predictions': tot_oor
        })

    return pd.DataFrame(agg_records)


def compute_paired_participant_bootstrap(
    per_person_df: pd.DataFrame,
    family: str,
    seed: int,
    n_resamples: int
) -> Dict[str, Any]:
    """Run paired participant bootstrap for baseline fusion comparison in full float64 precision.

    Sign convention: delta = combined - sensor.
    Negative delta indicates improvement (lower error for combined).
    """
    sensor_m = f"{family}_sensor_only"
    comb_m = f"{family}_sensor_plus_baseline"

    s_p = per_person_df[per_person_df['method'] == sensor_m].sort_values('participant_id')
    c_p = per_person_df[per_person_df['method'] == comb_m].sort_values('participant_id')

    mae_s = s_p['mae_mg_dl'].to_numpy(dtype=float)
    mae_c = c_p['mae_mg_dl'].to_numpy(dtype=float)
    delta_mae = mae_c - mae_s

    rmse_s = s_p['rmse_mg_dl'].to_numpy(dtype=float)
    rmse_c = c_p['rmse_mg_dl'].to_numpy(dtype=float)
    delta_rmse = rmse_c - rmse_s

    n_participants = len(mae_s)
    rng = np.random.default_rng(seed)

    boot_mae_deltas = []
    boot_rmse_deltas = []

    for _ in range(n_resamples):
        b_idx = rng.choice(n_participants, size=n_participants, replace=True)
        boot_mae_deltas.append(float(np.mean(delta_mae[b_idx])))
        boot_rmse_deltas.append(float(np.mean(delta_rmse[b_idx])))

    mae_ci_lower = float(np.percentile(boot_mae_deltas, 2.5))
    mae_ci_upper = float(np.percentile(boot_mae_deltas, 97.5))
    rmse_ci_lower = float(np.percentile(boot_rmse_deltas, 2.5))
    rmse_ci_upper = float(np.percentile(boot_rmse_deltas, 97.5))

    return {
        'family': family,
        'resamples': n_resamples,
        'seed': seed,
        'delta_mae_per_participant': [float(x) for x in delta_mae],
        'delta_rmse_per_participant': [float(x) for x in delta_rmse],
        'mean_delta_mae': float(np.mean(delta_mae)),
        'mae_95_ci': [mae_ci_lower, mae_ci_upper],
        'mean_delta_rmse': float(np.mean(delta_rmse)),
        'rmse_95_ci': [rmse_ci_lower, rmse_ci_upper],
        'mean_sensor_mae': float(np.mean(mae_s)),
        'mean_combined_mae': float(np.mean(mae_c)),
        'mean_sensor_rmse': float(np.mean(rmse_s)),
        'mean_combined_rmse': float(np.mean(rmse_c)),
        'participants_improved_mae': int(np.sum(delta_mae < 0)),
        'participants_worsened_mae': int(np.sum(delta_mae > 0)),
        'participants_tied_mae': int(np.sum(delta_mae == 0)),
        'participants_improved_rmse': int(np.sum(delta_rmse < 0)),
        'participants_worsened_rmse': int(np.sum(delta_rmse > 0)),
        'participants_tied_rmse': int(np.sum(delta_rmse == 0)),
    }
