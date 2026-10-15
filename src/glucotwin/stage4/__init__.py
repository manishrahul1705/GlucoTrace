"""Stage 4: Retrospective within-patient adaptation module."""
from .adaptation import (
    validate_calibration_gate,
    partition_participant_origins,
    compute_median_residual_offset,
    apply_offset,
    OffsetProvenance,
)
from .evaluation import (
    VALID_GLUCOSE_RANGE,
    compute_point_metrics,
    generate_shared_bootstrap_draws,
    paired_participant_bootstrap,
    compute_cohort_aggregates,
)

__all__ = [
    'validate_calibration_gate',
    'partition_participant_origins',
    'compute_median_residual_offset',
    'apply_offset',
    'OffsetProvenance',
    'VALID_GLUCOSE_RANGE',
    'compute_point_metrics',
    'generate_shared_bootstrap_draws',
    'paired_participant_bootstrap',
    'compute_cohort_aggregates',
]
