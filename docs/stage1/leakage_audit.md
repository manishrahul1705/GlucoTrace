# Temporal leakage and causal-input decision
**Verdict B — CONDITIONAL GO — RESTRICTED SCOPE.** The permitted technical scope is a retrospective benchmark of the released processed signal. A live-equivalent causal forecast benchmark is not established.

VERIFIED SOURCE (S3, Data Records): released CGM is linearly interpolated between neighboring native readings; nominal cadences are Libre 15 minutes and Dexcom 5 minutes. MEASURED: the audited CSV schemas contain no original-observation marker, interpolation anchor ID, ingestion timestamp or availability timestamp. The authors' inspected notebook does not implement the raw-to-release interpolation pipeline.

INFERENCE — confirmed mechanism: an interpolated value between anchors depends mathematically on its later anchor. Exposing it at its displayed event time can reveal information that was not yet measured. This is not proof that every release row is interpolated, nor that every proposed experiment necessarily leaks. Selecting every fifth row, timestamp divisibility and slope changes cannot certify native observations: flat segments, phase offsets, rounded values and missing intervals create ambiguity. No native observations were reconstructed.

INFERENCE — potential mechanisms: activity smoothing may use future samples if centered; portion-adjusted macros can reveal post-meal information; assay collection time does not establish result availability. These risks are distinct from the confirmed interpolation operation. No centered-filter claim is made.

**Formal rule:** `available_at <= prediction_issue_time` for every feature version. `temporal_availability.csv` records each field's event time, availability, processing direction, confidence and inclusion decision. Unknown availability is not replaced with event time.

RECOMMENDATION — proposed causal preprocessing specification:
1. Obtain original exports and preprocessing code; retain original timestamp, device, provenance and availability fields. Preserve a separate released-value table.
2. Only use observations whose acquisition and reporting delay are known or explicitly assumed. Resample with backward-looking aggregation/as-of joins. Preserve missingness; never backward-fill or interpolate features using future endpoints.
3. A proposed 6-minute Dexcom / 16-minute Libre stale-feature rule is only an ASSUMPTION under strict maximum 5/15-minute anchor separation, plus one-minute processing latency. It is not approved here because gap bridging and uploads are undocumented. Do not use it as proof that the actual release is causal.
4. Include Age/BMI and screening A1c/fasting glucose only under a recorded baseline-result-known-before-evaluation assumption or verified result times. One baseline row is not a longitudinal EHR. Do not derive a baseline from the full CGM trace.
5. Exclude meals, HR, activity, microbiome and later fingersticks from the initial causal feature contract until timing is resolved. Keep meal-null separate from confirmed no-meal. No arbitrary fixed meal delay is deemed verified.
6. Store prediction issue time, event time, available_at, source observation IDs, age/staleness, masks and model version. Refuse inputs newer than issue time. Targets may be future, but must not alter feature construction.
7. For the restricted released-signal task, label every input/target and replay screen as retrospective, interpolated-release research. Its accuracy cannot establish performance on native future sensor readings or clinician benefit.

BLOCKED: causal origin counts and observed-native target counts. Null causal counts in outputs mean unestablished, not zero available retrospective data. Release quality and causal availability are separate questions.
