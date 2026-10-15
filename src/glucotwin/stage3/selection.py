"""Inner cross-validation scoring, candidate selection, and deterministic tie-breaking.

Preserves full float64 precision throughout validation scoring and equal-person averaging.
"""
from typing import List, Dict, Tuple, Any
import numpy as np
import pandas as pd

from glucotwin.stage3.training import fit_estimator, predict_estimator, get_participant_indices


def compute_equal_person_val_mae(
    val_preds: np.ndarray,
    val_targets: np.ndarray,
    val_pids: np.ndarray,
    unique_val_pids: List[int]
) -> Dict[int, float]:
    """Compute unrounded MAE for each validation participant in full float64 precision."""
    person_maes = {}
    for pid in unique_val_pids:
        mask = val_pids == pid
        if not np.any(mask):
            continue
        p_res = np.abs(val_preds[mask] - val_targets[mask])
        person_maes[pid] = float(np.mean(p_res))
    return person_maes


def select_candidate(candidate_evaluations: List[Tuple[int, float, dict]]) -> Tuple[int, float, dict]:
    """Select candidate with minimal equal-person validation MAE.

    candidate_evaluations is a list of tuples: (candidate_id, equal_person_val_mae, candidate_dict).
    Ties in equal_person_val_mae are broken by earliest candidate_id.
    """
    if not candidate_evaluations:
        raise ValueError("Cannot select candidate from empty evaluation list")

    # Sort primarily by score ascending, secondarily by candidate_id ascending
    sorted_cands = sorted(candidate_evaluations, key=lambda item: (item[1], item[0]))
    return sorted_cands[0]


def evaluate_inner_candidate(
    family: str,
    candidate: dict,
    inner_folds: list,
    df_src: pd.DataFrame,
    features: List[str],
    target_col: str,
    outer_train_pids: List[int],
    outer_fold_name: str,
    held_out_pid: int,
    variant: str,
    fit_counter_start: int
) -> Tuple[float, List[dict], int]:
    """Evaluate a candidate hyperparameter configuration across all inner folds.

    Returns:
        (mean_equal_person_mae, fit_ledger_records, next_fit_counter)
    """
    val_person_maes: Dict[int, float] = {}
    ledger_records = []
    fit_counter = fit_counter_start

    cand_id = candidate['candidate_id']

    for inner_f in inner_folds:
        fold_num = inner_f['fold']
        in_train_pids = inner_f['train']['participants']
        in_val_pids = inner_f['validation']['participants']

        in_train_idx = get_participant_indices(df_src, in_train_pids)
        in_val_idx = get_participant_indices(df_src, in_val_pids)

        X_in_train = df_src.loc[in_train_idx, features].to_numpy(dtype=float)
        y_in_train = df_src.loc[in_train_idx, target_col].to_numpy(dtype=float)
        X_in_val = df_src.loc[in_val_idx, features].to_numpy(dtype=float)
        y_in_val = df_src.loc[in_val_idx, target_col].to_numpy(dtype=float)
        val_pids_arr = df_src.loc[in_val_idx, 'participant_id'].to_numpy()

        import time
        t_fit_start = time.time()
        est, scaler = fit_estimator(family, candidate, X_in_train, y_in_train)
        t_fit_dur = time.time() - t_fit_start

        preds_val = predict_estimator(est, scaler, X_in_val)

        fit_counter += 1
        ledger_records.append({
            'fit_index': fit_counter,
            'stage': 'inner_selection',
            'outer_fold': outer_fold_name,
            'held_out_pid': held_out_pid,
            'inner_fold': fold_num,
            'family': family,
            'variant': variant,
            'candidate_id': cand_id,
            'n_train_rows': len(in_train_idx),
            'n_val_test_rows': len(in_val_idx),
            'duration_sec': round(t_fit_dur, 4)
        })

        f_maes = compute_equal_person_val_mae(preds_val, y_in_val, val_pids_arr, in_val_pids)
        val_person_maes.update(f_maes)

    # Verify every outer-training participant was evaluated in validation
    assert len(val_person_maes) == len(outer_train_pids), (
        f"Expected {len(outer_train_pids)} validation participants, got {len(val_person_maes)}"
    )

    # Equal-person mean across all outer-training participants (full float64 precision)
    mean_val_mae = float(np.mean(list(val_person_maes.values())))
    return mean_val_mae, ledger_records, fit_counter
