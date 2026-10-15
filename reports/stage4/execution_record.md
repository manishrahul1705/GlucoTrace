# Stage 4 Execution Record

- **Protocol Version**: `stage4-v1`
- **Execution Date**: `2026-10-15 14:47:45 UTC`
- **Elapsed Time**: `0.91 seconds`
- **Platform**: `Windows-11-10.0.26300-SP0`
- **Python**: `3.12.3 (tags/v3.12.3:f6650f9, Apr  9 2024, 14:05:25) [MSC v.1938 64 bit (AMD64)]`
- **Preselected Reproduction Fold**: `holdout_012` (Participant `12`)

## Cohort & Origin Counts
- **Total Eligible Participants**: 14
- **Paired Calibration Origins (48h)**: 7709
- **Paired Later Evaluation Origins**: 31552
- **Purged Boundary-Straddling Origins**: 235
- **Total Processed Origins**: 39496

## Aggregate Later-Period Evaluation (N = 31552)
| Method | Equal-Person MAE (mg/dL) | Equal-Person RMSE (mg/dL) | Window-Weighted MAE (mg/dL) | Window-Weighted RMSE (mg/dL) |
|---|---|---|---|---|
| persistence | 14.8903 | 22.5087 | 14.8881 | 22.7009 |
| ridge_sensor_only_unadapted | 13.1573 | 19.4103 | 13.1564 | 19.5795 |
| ridge_sensor_only_adapted | 12.6871 | 19.1466 | 12.6846 | 19.3233 |
| ridge_sensor_plus_baseline_unadapted | 13.2608 | 19.2812 | 13.2576 | 19.4451 |
| ridge_sensor_plus_baseline_adapted | 12.7692 | 19.0876 | 12.7669 | 19.2860 |

## Adaptation Comparison Deltas (delta = adapted - unadapted; negative = improvement)
| Comparison | Mean Delta MAE (95% CI) | Improved / Worsened / Tied (MAE) |
|---|---|---|
| Ridge Sensor-Only: Adapted vs Unadapted | -0.4703 [-0.9165, -0.1054] | 11 / 3 / 0 |
| Ridge Combined: Adapted vs Unadapted | -0.4916 [-0.8672, -0.1112] | 11 / 3 / 0 |
| Ridge Sensor-Only Unadapted vs Persistence | -1.7330 [-2.2781, -1.1399] | 13 / 1 / 0 |
| Ridge Sensor-Only Adapted vs Persistence | -2.2033 [-2.5333, -1.8860] | 14 / 0 / 0 |
| Ridge Combined Unadapted vs Persistence | -1.6295 [-2.0430, -1.2603] | 14 / 0 / 0 |
| Ridge Combined Adapted vs Persistence | -2.1212 [-2.4481, -1.7891] | 14 / 0 / 0 |

- **Shared Bootstrap Draw Matrix SHA-256**: `af81ab357e83b64b24ddefa2fc2f3e87c2485e02cf43fcab0603816a1b2cadc9`
