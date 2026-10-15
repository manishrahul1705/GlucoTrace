# GlucoTwin Stage 3 — Next Stage Recommendations

## 1. Summary of Stage 3 Empirical Evidence

The Stage 3 experiments yielded two clear, evidence-backed findings:
1. **Dynamic sensor features outperform simple persistence**: Ridge regression on 21 trailing sensor features achieved a primary equal-person MAE of **13.50 mg/dL** (10.9% improvement over persistence at 15.15 mg/dL).
2. **Static baseline demographic/screening fusion does not help**: Concatenating Age, BMI, HbA1c, and Fasting Glucose yielded a negligible \(\Delta\) of **+0.056 mg/dL** for Ridge (95% CI: [-0.33, +0.39] mg/dL), and degraded HistGradientBoosting MAE by **+0.374 mg/dL** (9 out of 14 participants worsened).

---

## 2. Recommended Next Stage: Stage 4 (Patient-Specific Adaptation & Conformal Uncertainty)

Based on these measured outcomes, we recommend advancing to **Stage 4: Within-Patient Adaptation and Conformal Uncertainty Bounds**, with the following strict scope:

### A. Evaluate Frozen First-48-Hour Adaptation (Stage 2 Personalization Protocol)
- Use the predeclared, frozen 48-elapsed-hour calibration protocol verified in Stage 2 (`personalization_coverage.csv`).
- For each participant, use an outer base model trained strictly without that participant.
- Fit a single median residual offset using only the participant's permitted calibration labels \([t_0, t_0 + 48\text{h})\).
- Evaluate on the untouched later interval with full temporal purge.
- **Scientific Question**: Does dynamic patient-specific calibration reduce error where static baseline fusion failed?

### B. Conformal Prediction Intervals (Quantifying Horizon Uncertainty)
- Rather than point forecasts alone, construct non-parametric split conformal prediction intervals guaranteeing marginal coverage (e.g., 90% and 95% target intervals).
- Evaluate interval sharpness (width in mg/dL) and conditional coverage across glycemic ranges (hypoglycemic, euglycemic, hyperglycemic).

### C. Explicit Scope Exclusions for Stage 4
- **DO NOT** add meal, activity, or heart-rate inputs without verifying causal availability.
- **DO NOT** attempt live Bluetooth sensor streaming or mobile app deployment until causal live equivalence is validated.
- **DO NOT** perform clinical alert generation or insulin dosing decision support.
- **DO NOT** distribute per-origin predictions or weights publicly while licensing status remains UNRESOLVED.

---

## 3. Decision Gate Matrix for Stage 4

| Track | Current Gate Status | Stage 4 Requirement |
| :--- | :---: | :--- |
| **Retrospective Engineering** | **PASS** | Implement frozen 48-hour median offset adapter and conformal uncertainty calibration |
| **Causal Live Equivalence** | **NOT ESTABLISHED** | Retain research-only processed signal scope; fail closed on live deployment claims |
| **Public Distribution / Prize Release** | **UNRESOLVED** | Obtain formal PhysioNet / Figshare licensing clarification before distributing competition package |
