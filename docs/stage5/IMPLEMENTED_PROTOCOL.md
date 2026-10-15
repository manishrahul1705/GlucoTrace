# Stage 5 implemented protocol

The frozen machine-readable authority is `configs/stage5_protocol.json`.
`reports/stage5/protocol_freeze.json` records its byte SHA-256 before evaluation.
The earlier proposal remains historical design evidence. This implementation is
exploratory retrospective research, with no default model selection or tuning.

Excluded from model fitting and interval calibration; outcomes from this cohort have previously been examined, so this analysis remains exploratory.

The glucose stream is released Dexcom GL, in mg/dL. Stage 2 requires every minute
in inclusive [t-60,t], including 61 cells. Thirteen five-minute lags, inclusive
rolling means/standard deviations (ddof=0), and trailing OLS slopes reproduce the
21 frozen sensor features. The issue grid is every fifth minute anchored at the
first parsed recording timestamp. Targets are exact released values at t+30;
regression does not require every intervening future minute. Naive shifted event
timestamps are preserved. Actual availability and original observations remain
unknown. Neither chronological access nor its tests undo upstream interpolation.

## Partition and model provenance

The existing first-valid Dexcom anchor determines elapsed-hour boundaries.
Offset origins require history_start>=anchor and target_time<anchor+24h.
Interval calibration requires history_start>=anchor+24h and target_time<anchor+48h.
Evaluation requires history_start>=anchor+48h. All other origins are purged.
Equality of a target to an upper phase boundary is excluded from that phase.
Equality of history_start to a lower boundary is allowed. Purges are defined by
these support predicates, not the proposal's ambiguous displayed gap intervals.
This is a regression task; event-label t+44 support is inapplicable.

The new 24-hour offset is distinct from Stage 4's preserved 48-hour experiment.
The same frozen sensor-only Ridge is compared with and without a median
(target minus base prediction) offset. No mean replacement, rolling update, model
switching, or new search is permitted. Existing weights were unavailable; only
14 previously selected Ridge outer refits are reconstructed, training solely on
the original other-participant folds. All original held-out predictions must
reproduce within 1e-8 mg/dL before evaluation. Stage 3's full 728 fits are not rerun.

Minimum 100 offset origins, 100 interval-calibration origins and 100 later eligible
origins retain existing proposal rules. These are engineering gates, not evidence
of statistical adequacy. Per-phase minute coverage is reported locally. Stage 4's
80% gate over 48 hours is not silently reinterpreted as a new gate in each 24 hours.

## Exact intervals and metrics

For each participant, variant and alpha (0.10, 0.05), use separate calibration
scores abs(target-prediction), with the first-phase offset already fixed.
Compute k=ceil((n+1)*(1-alpha)) with exact rational arithmetic for decimal alpha;
use sorted_scores[k-1] only if n>=100 and k<=n. Otherwise interval calibration is
unavailable. A single invalid/non-finite/negative score invalidates its entire
calibration set and records the count; it is never silently discarded. Frozen
calibration objects cannot be updated during evaluation. No interpolated percentile,
maximum-score fallback, or physiological clipping is used.

Intervals [prediction-q,prediction+q] include both endpoints for measured empirical
coverage. Check that each 95% interval contains its 90% counterpart on the same
origin. Nominal coverage is a requested level, not guaranteed coverage;
exchangeability is not established for overlapping dependent observations.
Winkler/interval scores are explicitly deferred, rather than added after evaluation.

MAE, RMSE, signed error (prediction minus target), empirical coverage and mean
width are first calculated per contributing participant, then averaged. Undefined
metrics for absent participants remain undefined and are excluded with explicit
denominators; they are never imputed as zero. Pooled metrics use all scored windows
(pooled RMSE is square root of pooled squared error). Report participant minima and
maxima for coverage and mean width, with detailed participant metrics local only.
Widths/coverage use the interval-scoreable set; point errors use the point-scoreable
set. Both sets' counts are explicit, allowing unavailable intervals with valid points.

Clean eligibility denotes the original full-history/exact-target eligibility.
Scheduled counts include every inherited post-boundary grid issue through recording
end, even missing-history or outside-recording-target issues. Target availability
does not gate forecast issuance. Slice denominators are scheduled origins with known
targets in <70, inclusive 70-180 or >180; missing targets are excluded from slices
but retained in the overall schedule and reason counts. Empty slices have zero
counts and undefined errors. Representation of all participants is not robustness.

## Reusable reasons

| Reason | Exact interpretation |
|---|---|
| INVALID_UNIT | Operational input unit is not mg/dL; reject stream. |
| NON_FINITE_READING | Present current input cell has non-finite/non-numeric glucose. |
| CONFLICTING_DUPLICATE | Duplicate timestamp has conflicting glucose values; reject stream. |
| DUPLICATE_TIMESTAMP | Even identical duplicate timestamps are rejected, per Stage 2. |
| INVALID_TIMESTAMP | Empty/invalid, nonmonotonic, timezone-shifted or off-minute index; reject stream, or off-grid requested issue. |
| INVALID_SENSOR | Stream contains anything other than Dexcom GL; no substitution. |
| SOURCE_INVALID_READING | Current reading violates inherited inclusive 40-400 source-validity rule. No new bounds invented. |
| MISSING_CURRENT_READING | No valid current exact-minute cell; always suppress point forecast. |
| STALE_READING | Most recent revealed valid cell is older than 10 elapsed minutes, the existing proposal engineering threshold. Additional missing-current reason; never emits a stale forecast. |
| INSUFFICIENT_HISTORY | Required history begins before supplied recording begins. |
| INCOMPLETE_HISTORY | Current cell valid, but one or more required minute cells in [t-60,t] absent/invalid. |
| INSUFFICIENT_OFFSET_DATA | Fewer than 100 eligible first-phase origins; adapted point unavailable, unadapted comparison can remain available. |
| INSUFFICIENT_CALIBRATION | n<100 or exact rank k>n; point can remain valid. |
| INVALID_CALIBRATION_SCORES | Calibration set includes invalid scores; entire set unavailable with invalid count recorded. |
| INVALID_MODEL_OUTPUT | Model/offset input or point output is non-finite. |
| INVALID_INTERVAL_ORDER | Invalid/non-finite/negative half-width, overflowed bounds, or lower>upper. |
| TARGET_MISSING | Evaluator's exact t+30 reference is absent/invalid/outside recording; no nearest substitution. Point state is unaffected. |

Reasons may be combined for missing-current conditions; stream-wide invalidity
raises a structured `StreamError`. No backward filling, two-sided interpolation,
centered smoothing or glucose forward filling occurs. Forward filling of a
last-valid *timestamp* is only metadata for staleness detection. Restoration
requires all 61 minute cells valid at a scheduled issue. Existing outputs and
calibration objects are not updated when new rows become visible.

## Synthetic input-loss experiment

One separate scenario per 15/30/60/120-minute gap, per participant. Start at the
first inherited grid timestamp >=anchor+72h, independent of outcomes. Gaps are
half-open [start,start+duration) on the unchanged minute grid. Detailed schedules
stay local. Remove input glucose/validity before calling the trailing feature
builder, while evaluator retains the original reference target stream (mode A:
input/transport loss). Calibration-period dropout and mode B observation/target
loss are deferred. Clean offsets/quantiles stay fixed in all scenarios.

Report issuance and scoring separately over the whole schedule, then compare clean
and dropout errors/coverage on the explicit intersection of accepted, interval-valid,
target-available origins. Those matched forecasts should coincide: no data are
imputed or altered outside missing input history. This is a synthetic availability
stress test of processed signals, not reconstruction of actual hardware failure.

## Verification and limitations

The verifier recomputes timestamp partitions, offsets, Decimal ranks, targets,
availability gates, participant/pooled/slice metrics and matched-origin metrics
directly from local evidence. It shares the Stage 2 trailing builder for prediction
reconstruction and production Stage 5 replay for future-access checks. It is not
wholly independent. Prefix tests establish application access isolation only.

Stage 4's high-glucose deterioration remains material: >180 mg/dL slice MAE rose
0.570931 mg/dL and underprediction increased. Stage 5 evaluates its new 24-hour
model afresh, without choosing a default from the results. Severe sparsity of
observations below 70 mg/dL, dependent windows, unknown upstream filter/interpolation
support, lack of independent/prospective validation and unresolved permissions
remain limitations. No clinical, dosing or live-validation claims are supported.

Detailed data, predictions, bounds, models, offsets, quantiles, participant metrics,
gap schedules, input inventories and handoff remain ignored. Aggregate candidate
reports are technically reviewable pending applicable permissions, not cleared
for publication. Existing licensing findings remain unchanged; no messages sent.
