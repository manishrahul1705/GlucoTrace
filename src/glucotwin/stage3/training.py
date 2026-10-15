"""Model construction, training, feature extraction, and prediction functions for Stage 3.

Enforces training-only scaling (no leakage into validation or outer test sets) and strict estimator configurations.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from typing import Tuple, Optional, List
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor

from glucotwin.stage3.integrity import SENSOR_FEATURES, COMBINED_FEATURES


def get_feature_columns(variant: str) -> List[str]:
    """Return immutable feature list for the given experimental variant."""
    if variant == 'sensor_only':
        return list(SENSOR_FEATURES)
    elif variant == 'sensor_plus_baseline':
        return list(COMBINED_FEATURES)
    else:
        raise ValueError(f"Unknown variant: {variant}")


def build_estimator(family: str, candidate: dict):
    """Instantiate a regressor for the specified family and candidate parameters."""
    if family == 'ridge':
        return Ridge(alpha=candidate['alpha'], fit_intercept=True)
    elif family == 'hist_gradient_boosting':
        return HistGradientBoostingRegressor(
            learning_rate=candidate['learning_rate'],
            max_iter=candidate['max_iter'],
            max_leaf_nodes=candidate['max_leaf_nodes'],
            min_samples_leaf=candidate['min_samples_leaf'],
            l2_regularization=candidate['l2_regularization'],
            early_stopping=candidate['early_stopping'],
            random_state=candidate['random_state']
        )
    else:
        raise ValueError(f"Unknown estimator family: {family}")


def fit_estimator(
    family: str,
    candidate: dict,
    X_train: np.ndarray,
    y_train: np.ndarray
) -> Tuple[object, Optional[StandardScaler]]:
    """Fit an estimator strictly on training data, applying StandardScaler only for Ridge.

    Returns the fitted estimator and fitted scaler (or None if no scaling).
    """
    scaler = None
    if family == 'ridge':
        scaler = StandardScaler()
        X_train_proc = scaler.fit_transform(X_train)
    else:
        X_train_proc = X_train

    est = build_estimator(family, candidate)
    est.fit(X_train_proc, y_train)
    return est, scaler


def predict_estimator(
    est: object,
    scaler: Optional[StandardScaler],
    X: np.ndarray
) -> np.ndarray:
    """Generate predictions from a fitted estimator, using training-fitted scaler if present.

    Does not clip predictions to allow accurate tracking of out-of-range rates.
    """
    if scaler is not None:
        X_proc = scaler.transform(X)
    else:
        X_proc = X
    return est.predict(X_proc)


def get_participant_indices(df: pd.DataFrame, participant_ids: List[int]) -> np.ndarray:
    """Return row indices corresponding to the specified participant IDs."""
    mask = df['participant_id'].isin(participant_ids)
    return np.where(mask)[0]
