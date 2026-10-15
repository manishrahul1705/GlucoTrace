"""Timestamp-based access gates, frozen calibration, and input-loss replay.

No interpolation, target substitution, physiological output clipping, or fitting.
The trailing builder is shared with Stage 2; upstream processing remains unknown.
"""
from dataclasses import dataclass
from fractions import Fraction
from math import ceil
import numpy as np
import pandas as pd
from glucotwin.features import build_sensor_features, SENSOR_FEATURES


class StreamError(ValueError):
    pass


@dataclass(frozen=True)
class Calibration:
    n: int
    k: int
    q: float | None
    reason: str
    invalid_count: int = 0


def calibrate(scores, alpha, minimum=100):
    """Use exact decimal/rational rank; invalidate the entire set on bad scores."""
    a = Fraction(str(alpha))
    if not 0 < a < 1 or minimum < 1:
        raise ValueError('Invalid alpha or minimum')
    s = np.asarray(scores, dtype=float)
    if s.ndim != 1:
        raise ValueError('One-dimensional scores required')
    n = len(s)
    k = ceil((n + 1) * (1 - a))
    bad = int((~np.isfinite(s) | (s < 0)).sum())
    if bad:
        return Calibration(n, k, None, 'INVALID_CALIBRATION_SCORES', bad)
    if n < minimum or k > n:
        return Calibration(n, k, None, 'INSUFFICIENT_CALIBRATION')
    return Calibration(n, k, float(np.sort(s)[k - 1]), 'OK')


def fit_offset(target, prediction, minimum=100):
    yt, yp = np.asarray(target, dtype=float), np.asarray(prediction, dtype=float)
    if yt.shape != yp.shape or yt.ndim != 1:
        raise ValueError('Aligned one-dimensional offset inputs required')
    if len(yt) < minimum:
        return None, 'INSUFFICIENT_OFFSET_DATA'
    if not np.isfinite(yt).all() or not np.isfinite(yp).all():
        return None, 'INVALID_MODEL_OUTPUT'
    return float(np.median(yt - yp)), 'OK'


def partition_origins(origins, anchor):
    """Half-open partitions using full regression support; no row-count split."""
    out = origins.copy()
    issue = pd.to_datetime(out.issue_time)
    hs, target = pd.to_datetime(out.history_start), pd.to_datetime(out.target_time)
    if not (hs == issue-pd.Timedelta(minutes=60)).all() or not (target == issue+pd.Timedelta(minutes=30)).all():
        raise ValueError('Full 60-minute history and exact t+30 target support required')
    a = pd.Timestamp(anchor)
    b, c = a+pd.Timedelta(hours=24), a+pd.Timedelta(hours=48)
    out['partition'] = np.select([(hs >= a) & (target < b), (hs >= b) & (target < c), hs >= c],
                                  ['offset', 'calibration', 'evaluation'], default='purged')
    return out


def validate_stream(stream, unit='mg/dL'):
    if unit != 'mg/dL':
        raise StreamError('INVALID_UNIT')
    if not isinstance(stream.index, pd.DatetimeIndex) or stream.empty or stream.index.hasnans:
        raise StreamError('INVALID_TIMESTAMP')
    if stream.index.has_duplicates:
        conflict = stream.groupby(level=0).glucose_mg_dl.nunique(dropna=False).gt(1).any()
        raise StreamError('CONFLICTING_DUPLICATE' if conflict else 'DUPLICATE_TIMESTAMP')
    if not stream.index.is_monotonic_increasing or stream.index.tz is not None:
        raise StreamError('INVALID_TIMESTAMP')
    if ((stream.index-stream.index[0]).total_seconds() % 60 != 0).any():
        raise StreamError('INVALID_TIMESTAMP')
    if 'sensor' in stream and not stream.sensor.eq('Dexcom GL').all():
        raise StreamError('INVALID_SENSOR')


def forecast_stream(stream, issues, predictor, unit='mg/dL', stale_minutes=10):
    """Return point state per scheduled issue; predictor receives trailing features only.

    Slice to last requested issue before constructing features. Rolling operations
    are trailing. Targets are deliberately absent from this function's interface.
    """
    issues = pd.DatetimeIndex(issues)
    if len(issues) == 0:
        return pd.DataFrame(columns=['issue_time', 'prediction', 'point_reason'])
    revealed = stream.loc[stream.index <= issues.max()].copy()
    validate_stream(revealed, unit)
    minute_grid = pd.date_range(revealed.index[0], max(issues.max(), revealed.index[-1]), freq='min')
    d = revealed.reindex(minute_grid)
    glucose = pd.to_numeric(d.glucose_mg_dl, errors='coerce')
    valid = d.valid.eq(True) & np.isfinite(glucose) & glucose.between(40, 400)
    d['valid'] = valid
    d['glucose_mg_dl'] = glucose
    complete = valid.astype(int).rolling(61, min_periods=61).sum().eq(61)
    features = build_sensor_features(d)
    last_valid = pd.Series(d.index.where(valid), index=d.index).ffill()
    reasons = []
    for issue in issues:
        if issue not in d.index:
            reasons.append('INVALID_TIMESTAMP')
            continue
        if not valid.loc[issue]:
            codes = ['MISSING_CURRENT_READING']
            present = d.loc[issue].get('row_present', False)
            if pd.notna(present) and bool(present) and not np.isfinite(glucose.loc[issue]):
                codes.append('NON_FINITE_READING')
            if np.isfinite(glucose.loc[issue]) and not 40 <= glucose.loc[issue] <= 400:
                codes.append('SOURCE_INVALID_READING')
            if pd.notna(last_valid.loc[issue]) and issue-last_valid.loc[issue] > pd.Timedelta(minutes=stale_minutes):
                codes.append('STALE_READING')
            reasons.append(';'.join(codes))
        elif issue-pd.Timedelta(minutes=60) < d.index[0]:
            reasons.append('INSUFFICIENT_HISTORY')
        elif not complete.loc[issue]:
            reasons.append('INCOMPLETE_HISTORY')
        else:
            reasons.append('OK')
    result = pd.DataFrame(dict(issue_time=issues, prediction=np.nan, point_reason=reasons))
    ok = result.point_reason.eq('OK')
    if ok.any():
        matrix = features.reindex(issues[ok])[SENSOR_FEATURES].to_numpy(dtype=float)
        predictions = np.asarray(predictor(matrix), dtype=float)
        if predictions.shape != (int(ok.sum()),):
            raise ValueError('Predictor must return one output per issue')
        result.loc[ok, 'prediction'] = predictions
        bad_rows = result.index[ok][~np.isfinite(predictions)]
        result.loc[bad_rows, 'prediction'] = np.nan
        result.loc[bad_rows, 'point_reason'] = 'INVALID_MODEL_OUTPUT'
    return result


def interval_bounds(prediction, calibration):
    if not np.isfinite(prediction):
        return np.nan, np.nan, 'INVALID_MODEL_OUTPUT'
    if calibration.reason != 'OK':
        return np.nan, np.nan, calibration.reason
    q = calibration.q
    if q is None or not np.isfinite(q) or q < 0:
        return np.nan, np.nan, 'INVALID_INTERVAL_ORDER'
    lower, upper = prediction-q, prediction+q
    if not np.isfinite([lower, upper]).all() or lower > upper:
        return np.nan, np.nan, 'INVALID_INTERVAL_ORDER'
    return lower, upper, 'OK'


def exact_targets(reference, issues):
    """Evaluator lookup only; no nearest target and no target-dependent forecast gate."""
    times = pd.DatetimeIndex(issues)+pd.Timedelta(minutes=30)
    d = reference.reindex(times)
    values = pd.to_numeric(d.glucose_mg_dl, errors='coerce').to_numpy(dtype=float)
    valid = d.valid.eq(True).to_numpy(dtype=bool) & np.isfinite(values) & (values >= 40) & (values <= 400)
    return np.where(valid, values, np.nan)


def gap_start(stream, anchor):
    candidates = stream.index[::5]
    candidates = candidates[candidates >= pd.Timestamp(anchor)+pd.Timedelta(hours=72)]
    if len(candidates) == 0:
        raise ValueError('No scheduled gap placement')
    return candidates[0]


def inject_gap(stream, start, minutes):
    """Input loss before features; reference target stream must remain a separate copy."""
    if minutes not in (15, 30, 60, 120):
        raise ValueError('Unfrozen duration')
    out = stream.copy(deep=True)
    mask = (out.index >= start) & (out.index < start+pd.Timedelta(minutes=minutes))
    out.loc[mask, 'glucose_mg_dl'] = np.nan
    out.loc[mask, 'valid'] = False
    out.loc[mask, 'row_present'] = False
    return out
