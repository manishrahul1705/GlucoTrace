"""GlucoTwin Stage 3 glucose forecasting module."""

from glucotwin.stage3.integrity import (
    SENSOR_FEATURES,
    BASELINE_FEATURES,
    COMBINED_FEATURES,
    TARGET_COL,
    METADATA_COLUMNS,
    PROHIBITED_COLUMNS,
    EXPECTED_PARTICIPANTS,
    IntegrityError,
    sha256_file,
    run_preflight_checks,
)
from glucotwin.stage3.training import (
    get_feature_columns,
    build_estimator,
    fit_estimator,
    predict_estimator,
    get_participant_indices,
)
from glucotwin.stage3.selection import (
    compute_equal_person_val_mae,
    select_candidate,
    evaluate_inner_candidate,
)
from glucotwin.stage3.metrics import (
    compute_persistence_predictions,
    compute_trend_predictions,
    compute_point_metrics,
    compute_per_participant_metrics,
    compute_aggregate_metrics,
    compute_paired_participant_bootstrap,
)

__all__ = [
    'SENSOR_FEATURES',
    'BASELINE_FEATURES',
    'COMBINED_FEATURES',
    'TARGET_COL',
    'METADATA_COLUMNS',
    'PROHIBITED_COLUMNS',
    'EXPECTED_PARTICIPANTS',
    'IntegrityError',
    'sha256_file',
    'run_preflight_checks',
    'get_feature_columns',
    'build_estimator',
    'fit_estimator',
    'predict_estimator',
    'get_participant_indices',
    'compute_equal_person_val_mae',
    'select_candidate',
    'evaluate_inner_candidate',
    'compute_persistence_predictions',
    'compute_trend_predictions',
    'compute_point_metrics',
    'compute_per_participant_metrics',
    'compute_aggregate_metrics',
    'compute_paired_participant_bootstrap',
]
