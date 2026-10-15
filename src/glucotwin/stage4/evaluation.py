"""Stage 4 Evaluation Module: Metrics, cohort aggregation, and shared paired bootstrap.

Preserves full float64 precision throughout all calculations; rounding is applied strictly at export/display boundaries.
Uses a single pre-generated shared draw-index matrix across all paired comparisons.
"""
from typing import Dict, List, Any, Tuple, Sequence
import hashlib
import numpy as np
import pandas as pd


VALID_GLUCOSE_RANGE = (40.0, 400.0)


def compute_point_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> Dict[str, Any]:
    """Calculate MAE, RMSE, mean signed error, and boundary violation counts.

    Sign convention for mean signed error:
        mean_signed_error = mean(y_pred - y_true)
        Positive means predictions systematically overestimate the truth.

    Parameters
    ----------
    y_true : sequence of float
        Ground truth targets.
    y_pred : sequence of float
        Predictions.

    Returns
    -------
    dict
        'mae': float
        'rmse': float
        'mean_signed_error': float
        'non_finite_count': int
        'out_of_range_count': int
    """
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_pred, dtype=np.float64)

    if len(yt) != len(yp):
        raise ValueError(f"Length mismatch: len(y_true)={len(yt)} != len(y_pred)={len(yp)}")
    if len(yt) == 0:
        raise ValueError("Cannot compute metrics on empty arrays")

    residuals = yp - yt
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    mse = float(np.mean(residuals))
    non_finite = int(np.sum(~np.isfinite(yp)))
    out_of_range = int(np.sum((yp < VALID_GLUCOSE_RANGE[0]) | (yp > VALID_GLUCOSE_RANGE[1])))

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
    """Calculate point evaluation metrics for each participant and method.

    Parameters
    ----------
    pred_df : pd.DataFrame
        DataFrame containing 'participant_id', 'target_mg_dl', and columns for each method.
    methods : list of str
        List of prediction column names.
    participants : list of int
        List of participant IDs in sorted order.

    Returns
    -------
    pd.DataFrame
        Per-participant metrics dataframe.
    """
    records = []
    for pid in participants:
        sub = pred_df[pred_df['participant_id'] == pid]
        if len(sub) == 0:
            continue
        y_true = sub['target_mg_dl'].to_numpy(dtype=np.float64)
        n_p = len(sub)

        for m in methods:
            if m not in sub.columns:
                raise ValueError(f"Method column '{m}' not found in predictions dataframe")
            y_hat = sub[m].to_numpy(dtype=np.float64)
            stats = compute_point_metrics(y_true, y_hat)
            records.append({
                'participant_id': pid,
                'method': m,
                'n_origins': n_p,
                'mae_mg_dl': stats['mae'],
                'rmse_mg_dl': stats['rmse'],
                'mean_signed_error_mg_dl': stats['mean_signed_error'],
                'non_finite_count': stats['non_finite_count'],
                'out_of_range_count': stats['out_of_range_count']
            })

    return pd.DataFrame(records)


def compute_cohort_aggregates(
    per_person_df: pd.DataFrame,
    methods: List[str]
) -> pd.DataFrame:
    """Compute primary equally-weighted and secondary window-weighted cohort aggregates.

    Parameters
    ----------
    per_person_df : pd.DataFrame
        Per-participant metrics table.
    methods : list of str
        List of methods to aggregate.

    Returns
    -------
    pd.DataFrame
        Aggregate metrics table.
    """
    agg_records = []
    for m in methods:
        sub = per_person_df[per_person_df['method'] == m]
        if len(sub) == 0:
            continue

        n_p = len(sub)
        n_origins_total = int(sub['n_origins'].sum())
        weights = sub['n_origins'].to_numpy(dtype=np.float64) / n_origins_total

        eq_mae = float(np.mean(sub['mae_mg_dl']))
        eq_rmse = float(np.mean(sub['rmse_mg_dl']))
        eq_mse = float(np.mean(sub['mean_signed_error_mg_dl']))

        ww_mae = float(np.sum(sub['mae_mg_dl'].to_numpy(dtype=np.float64) * weights))
        # Window-weighted RMSE is sqrt of weighted mean squared error
        mse_per_person = sub['rmse_mg_dl'].to_numpy(dtype=np.float64) ** 2
        ww_rmse = float(np.sqrt(np.sum(mse_per_person * weights)))
        ww_mse = float(np.sum(sub['mean_signed_error_mg_dl'].to_numpy(dtype=np.float64) * weights))

        tot_nan = int(sub['non_finite_count'].sum())
        tot_oor = int(sub['out_of_range_count'].sum())

        agg_records.append({
            'method': m,
            'n_participants': n_p,
            'total_origins': n_origins_total,
            'primary_equal_person_mae_mg_dl': eq_mae,
            'secondary_equal_person_rmse_mg_dl': eq_rmse,
            'equal_person_mean_signed_error_mg_dl': eq_mse,
            'window_weighted_mae_mg_dl': ww_mae,
            'window_weighted_rmse_mg_dl': ww_rmse,
            'window_weighted_mean_signed_error_mg_dl': ww_mse,
            'total_non_finite_predictions': tot_nan,
            'total_out_of_range_predictions': tot_oor
        })

    return pd.DataFrame(agg_records)


def generate_shared_bootstrap_draws(
    n_participants: int,
    n_resamples: int = 2000,
    seed: int = 20261015
) -> Tuple[np.ndarray, str]:
    """Generate and hash a shared 2D draw-index matrix for all paired comparisons.

    Parameters
    ----------
    n_participants : int
        Number of participants (e.g., 14).
    n_resamples : int, default=2000
        Number of bootstrap replications.
    seed : int, default=20261015
        Seed for NumPy default_rng.

    Returns
    -------
    draw_indices : np.ndarray
        Array of shape (n_resamples, n_participants) containing integer participant indices.
    draw_sha256 : str
        SHA-256 hash of the draw index bytes.
    """
    rng = np.random.default_rng(seed)
    draw_indices = rng.choice(n_participants, size=(n_resamples, n_participants), replace=True)
    draw_bytes = np.ascontiguousarray(draw_indices).tobytes()
    draw_sha256 = hashlib.sha256(draw_bytes).hexdigest()
    return draw_indices, draw_sha256


def paired_participant_bootstrap(
    per_person_df: pd.DataFrame,
    method_a: str,
    method_b: str,
    comparison_name: str,
    draw_indices: np.ndarray,
    alpha: float = 0.05,
    quantile_method: str = 'linear'
) -> Dict[str, Any]:
    """Evaluate paired participant bootstrap comparison using pre-generated shared draws.

    Sign convention:
        delta = method_a - method_b
        E.g. adapted - unadapted: negative delta indicates improvement (lower error for adapted).

    Parameters
    ----------
    per_person_df : pd.DataFrame
        Per-participant metrics dataframe.
    method_a : str
        Target method (e.g., 'ridge_sensor_only_adapted').
    method_b : str
        Baseline/reference method (e.g., 'ridge_sensor_only_unadapted').
    comparison_name : str
        Descriptive label for this comparison.
    draw_indices : np.ndarray
        Shared draw-index matrix of shape (n_resamples, n_participants).
    alpha : float, default=0.05
        Significance level for two-sided (1 - alpha) CI.
    quantile_method : str, default='linear'
        Quantile interpolation method for np.quantile.

    Returns
    -------
    dict
        Summary dictionary containing deltas, CIs, participant counts, and model statistics.
    """
    sub_a = per_person_df[per_person_df['method'] == method_a].sort_values('participant_id')
    sub_b = per_person_df[per_person_df['method'] == method_b].sort_values('participant_id')

    pids_a = sub_a['participant_id'].to_list()
    pids_b = sub_b['participant_id'].to_list()
    if pids_a != pids_b:
        raise ValueError(f"Participant mismatch between {method_a} and {method_b}: {pids_a} != {pids_b}")

    mae_a = sub_a['mae_mg_dl'].to_numpy(dtype=np.float64)
    mae_b = sub_b['mae_mg_dl'].to_numpy(dtype=np.float64)
    delta_mae = mae_a - mae_b

    rmse_a = sub_a['rmse_mg_dl'].to_numpy(dtype=np.float64)
    rmse_b = sub_b['rmse_mg_dl'].to_numpy(dtype=np.float64)
    delta_rmse = rmse_a - rmse_b

    n_participants = len(mae_a)
    n_resamples = draw_indices.shape[0]

    if draw_indices.shape[1] != n_participants:
        raise ValueError(
            f"draw_indices column dimension {draw_indices.shape[1]} != n_participants {n_participants}"
        )

    # Vectorized bootstrap means across shared draws
    boot_mae_deltas = np.mean(delta_mae[draw_indices], axis=1)
    boot_rmse_deltas = np.mean(delta_rmse[draw_indices], axis=1)

    mae_ci_lower = float(np.quantile(boot_mae_deltas, alpha / 2.0, method=quantile_method))
    mae_ci_upper = float(np.quantile(boot_mae_deltas, 1.0 - alpha / 2.0, method=quantile_method))

    rmse_ci_lower = float(np.quantile(boot_rmse_deltas, alpha / 2.0, method=quantile_method))
    rmse_ci_upper = float(np.quantile(boot_rmse_deltas, 1.0 - alpha / 2.0, method=quantile_method))

    return {
        'comparison_name': comparison_name,
        'method_a': method_a,
        'method_b': method_b,
        'n_participants': n_participants,
        'n_resamples': n_resamples,
        'quantile_method': quantile_method,
        'alpha': alpha,
        'mean_method_a_mae': float(np.mean(mae_a)),
        'mean_method_b_mae': float(np.mean(mae_b)),
        'mean_delta_mae': float(np.mean(delta_mae)),
        'mae_95_ci': [mae_ci_lower, mae_ci_upper],
        'mean_method_a_rmse': float(np.mean(rmse_a)),
        'mean_method_b_rmse': float(np.mean(rmse_b)),
        'mean_delta_rmse': float(np.mean(delta_rmse)),
        'rmse_95_ci': [rmse_ci_lower, rmse_ci_upper],
        'participants_improved_mae': int(np.sum(delta_mae < 0)),
        'participants_worsened_mae': int(np.sum(delta_mae > 0)),
        'participants_tied_mae': int(np.sum(delta_mae == 0)),
        'participants_improved_rmse': int(np.sum(delta_rmse < 0)),
        'participants_worsened_rmse': int(np.sum(delta_rmse > 0)),
        'participants_tied_rmse': int(np.sum(delta_rmse == 0)),
        'delta_mae_per_participant': [float(x) for x in delta_mae],
        'delta_rmse_per_participant': [float(x) for x in delta_rmse],
    }
