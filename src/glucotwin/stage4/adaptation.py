"""Stage 4 Adaptation Logic: Temporal partitioning, gate validation, and offset calculation.

Implements the frozen retrospective within-patient adaptation protocol:
- Anchor = first valid Dexcom timestamp.
- Boundary = anchor + 48 elapsed hours.
- Missing periods remain elapsed time; never compressed.
- Calibration origins: history_start >= anchor and target_time < boundary.
- Later evaluation origins: history_start >= boundary.
- Purged origins: straddling the boundary.
- Calibration residual: observed_target - base_prediction.
- Offset: median(calibration_residuals).
- Adapted prediction: base_prediction + offset.
"""
from typing import Dict, Any, Union, Sequence
from dataclasses import dataclass, asdict
import hashlib
import numpy as np
import pandas as pd


def validate_calibration_gate(
    coverage_ratio: float,
    n_cal_origins: int,
    n_later_origins: int,
    min_coverage: float = 0.80,
    min_cal: int = 100,
    min_later: int = 100
) -> bool:
    """Validate whether participant meets predeclared Stage 4 adequacy gates.

    Predeclared gates:
    - >=80% valid calibration coverage across 2,880 minute cells
    - >=100 paired five-minute calibration origins
    - >=100 paired five-minute later evaluation origins
    """
    if coverage_ratio < min_coverage:
        return False
    if n_cal_origins < min_cal:
        return False
    if n_later_origins < min_later:
        return False
    return True


def partition_participant_origins(
    df_origins: pd.DataFrame,
    first_valid_time: Union[str, pd.Timestamp],
    duration_hours: int = 48
) -> pd.DataFrame:
    """Partition participant origins into calibration, later_evaluation, or purged_boundary.

    Parameters
    ----------
    df_origins : pd.DataFrame
        DataFrame containing at least:
        ['origin_id', 'participant_id', 'issue_time', 'history_start', 'target_time']
    first_valid_time : str or pd.Timestamp
        First valid Dexcom timestamp for the participant.
    duration_hours : int, default=48
        Elapsed duration for the calibration window.

    Returns
    -------
    pd.DataFrame
        Copy of df_origins with added columns:
        ['first_valid_time', 'calibration_boundary', 'partition']
        where partition is one of 'calibration', 'later_evaluation', 'purged_boundary'.
    """
    required_cols = {'origin_id', 'participant_id', 'issue_time', 'history_start', 'target_time'}
    missing = required_cols - set(df_origins.columns)
    if missing:
        raise ValueError(f"Missing required columns in df_origins: {sorted(missing)}")

    out = df_origins.copy()
    first = pd.to_datetime(first_valid_time)
    boundary = first + pd.Timedelta(hours=duration_hours)

    hist_start = pd.to_datetime(out['history_start'])
    target_time = pd.to_datetime(out['target_time'])

    calmask = (hist_start >= first) & (target_time < boundary)
    evalmask = hist_start >= boundary
    purgemask = ~calmask & ~evalmask

    partitions = np.empty(len(out), dtype=object)
    partitions[calmask] = 'calibration'
    partitions[evalmask] = 'later_evaluation'
    partitions[purgemask] = 'purged_boundary'

    out['first_valid_time'] = first.isoformat()
    out['calibration_boundary'] = boundary.isoformat()
    out['partition'] = partitions

    return out


def compute_median_residual_offset(
    y_true: Sequence[float],
    y_pred: Sequence[float]
) -> float:
    """Compute patient-specific median residual offset from calibration observations.

    Formula:
        residual = observed_target - base_prediction
        offset = median(calibration_residuals)

    Sign convention:
        If model underestimates target (y_true > y_pred), residual > 0, offset > 0.
        Adding offset to future base predictions will shift them upward.

    Parameters
    ----------
    y_true : sequence of float
        Observed ground-truth targets on calibration origins.
    y_pred : sequence of float
        Base-model predictions on calibration origins.

    Returns
    -------
    float
        Median residual offset in full float64 precision.
    """
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_pred, dtype=np.float64)

    if len(yt) != len(yp):
        raise ValueError(f"Length mismatch: len(y_true)={len(yt)} != len(y_pred)={len(yp)}")
    if len(yt) == 0:
        raise ValueError("Cannot compute offset from empty calibration set")

    if not (np.all(np.isfinite(yt)) and np.all(np.isfinite(yp))):
        raise ValueError("Non-finite values encountered in y_true or y_pred")

    residuals = yt - yp
    return float(np.median(residuals))


def apply_offset(
    y_pred: Sequence[float],
    offset: float
) -> np.ndarray:
    """Apply patient-specific median residual offset to base predictions.

    Formula:
        adapted_prediction = base_prediction + offset

    No clipping, capping, or rounding is applied.

    Parameters
    ----------
    y_pred : sequence of float
        Base predictions on later evaluation origins.
    offset : float
        Patient-specific median residual offset.

    Returns
    -------
    np.ndarray
        Adapted predictions in float64 precision.
    """
    yp = np.asarray(y_pred, dtype=np.float64)
    off = float(offset)

    if not np.isfinite(off):
        raise ValueError(f"Non-finite offset provided: {off}")
    if not np.all(np.isfinite(yp)):
        raise ValueError("Non-finite values encountered in y_pred")

    return yp + off


@dataclass
class OffsetProvenance:
    """Provenance metadata for a patient-specific adaptation offset."""
    participant_id: int
    variant: str
    n_calibration_origins: int
    calibration_origin_ids_sha256: str
    latest_calibration_target_time: str
    calibration_boundary: str
    offset_mg_dl: float
    base_model_provenance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def hash_origin_ids(origin_ids: Sequence[str]) -> str:
    """Compute deterministic SHA-256 hash of sorted origin IDs."""
    sorted_ids = sorted(str(oid) for oid in origin_ids)
    payload = '\n'.join(sorted_ids) + '\n'
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
