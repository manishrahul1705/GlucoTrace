# Private fusion and endpoint research stages

Stage A retains the 14 existing held-out participants, origin IDs and outer folds.
It fits exactly 14 additional sensor-plus-baseline Ridge models using the separate
combined selections in the pinned selected-candidates table, without another
selection search. Each pair is reused for Stage 4 (48-hour offset) and Stage 5
(24-hour offset plus 24-hour calibration); original gates, support purges,
quantile ranks, two nominal levels and loss scenarios are unchanged.

The input order is the existing 21 trailing sensor features followed by age,
BMI, HbA1c and fasting glucose. Source columns are Age, BMI, A1c PDL (Lab), and
Fasting GLU - PDL (Lab), joined using subject. Units are years, kg/m^2, percent,
and mg/dL. These are baseline study attributes, not longitudinal EHR. Screening
availability before evaluation is an unresolved assumption; actual result times
are unknown. HbA1c operational percent follows the existing paper-based resolution
despite the dictionary conflict. There is no conversion or missing-value imputation.

`run_fusion_experiment.py freeze` records source/input hashes, actual UTC time,
runtime, feature ordering and all combined selections before evaluation. Execution
requires that exact freeze digest and a fresh output directory outside Git.
`verify` checks pinned bytes before model loading, training-only moments, the
25-dimensional normal equations, held-out predictions, scalar medians/ranks,
chronological partitions and scheduled scenario predictions/bounds/reasons.
Results are new private research evidence, not original-result reproduction.

The optional fusion bundle has its own manifest and models. Serve it with
`serve_new_experiment.py --fusion-bundle ... --fusion-manifest-sha256 ...` in
addition to the original pinned sensor bundle. Baseline/scaler/schema/mapping
failures make only the combined family unavailable. Sensor-only remains the
default; no held-out outcome selects a winning model. Each family has independent
offset/calibration states, and issued forecasts keep immutable family identifiers.
Baseline provenance and paired MAE differences are displayed, including harms.

Paired comparisons use matched scheduled/eligible origins, participant-level MAE,
RMSE, signed error and high-glucose behavior, along with interval coverage/width
and availability denominators. The participant bootstrap is exploratory with 14
participants, not an independence assumption about overlapping origins.

Stage B is separately frozen after its implementation and before endpoint
evaluation. Its predeclared primary model is sensor-only unadapted, regardless of
Stage A outcomes. It uses no new fits. It concerns strictly greater than 180 and
250 mg/dL at the exact +30-minute endpoint on the inherited five-minute grid.
Already-high origins remain included; every origin is an endpoint decision with
no refractory/merging rule. This is not an episode/onset predictor. Lead time and
false alarms/day are not reported. No calibrated adverse-event probabilities,
treatment, dosing, safe/unsafe advice or clinical validation are claimed.

Private data, fitted models, prediction tables, authorization and screenshots must
remain outside source/evidence packages. Competition use remains pending. Stage A
and Stage B require separate reviewed local commits after their acceptance passes.
