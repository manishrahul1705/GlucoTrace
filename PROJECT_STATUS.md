# GlucoTwin — Project Status & Roadmap

## 1. Project Purpose & Scope

GlucoTwin investigates retrospective 30-minute continuous glucose forecasting in adults with Type 2 Diabetes using trailing sensor observations and static baseline clinical screening characteristics.

- **Current Stage**: Stage 3 (Retrospective Benchmark) — **reported complete**.
- **Current Scope**: Restricted retrospective research on published, processed sensor signals.
- **Commit SHA**: `HEAD` (recorded on publication commit).
- **Causal Live Equivalence**: **NOT ESTABLISHED**.
- **Public Competition Permissions**: **UNRESOLVED**.
- **Medical / Clinical Clearance**: **NONE**. Not a medical device; no treatment, dosing, or autonomous alerting capabilities.

---

## 2. Nine-Stage Project Roadmap

| Stage | Name | Status | Key Evidence / Gate Deliverable |
| :---: | :--- | :---: | :--- |
| **1** | **Dataset research/audit** | **reported complete** | Audited PhysioNet CGMacros 1.0.0 (48 CSV tables). Verified source provenance SHA-256 (`b9006433...`). Documented upstream interpolation and timestamp spacing. Evidence: `reports/stage1/provenance_manifest.json`. |
| **2** | **Data and evaluation preparation** | **reported complete** | Established technical contracts, 14 outer LOPO / 3-fold grouped-inner partitions, and data extraction pipelines. Checkpoint frozen (`029b530f...`). Evidence: `reports/stage2/freeze_manifest.json`, `reports/stage2/split_manifest.json`. |
| **3** | **Retrospective benchmark** | **reported complete** | Executed all 728 planned fits across 14 LOPO folds (39,496 paired 5-minute origins). 46 unit tests passing. Verified that baseline fusion provides no generalization advantage over sensor-only dynamics. Evidence: `reports/stage3_remediation/preflight_report.json`, `reports/stage3_remediation/verification.json`, `reports/stage3_remediation/aggregate_metrics.csv`, `reports/stage3_remediation/run_comparison.json`. |
| **4** | **Fusion interpretation and separate patient adaptation** | **PLANNED (NEXT)** | Investigate dynamic within-patient calibration using frozen first-48-hour calibration windows (`personalization_coverage.csv`) to test whether patient-specific residual offsets improve later forecasts. |
| **5** | **Uncertainty and failure handling** | **PLANNED** | Implement non-parametric split conformal prediction intervals (90%/95% marginal coverage) and analyze out-of-distribution / sensor-gap failure modes. |
| **6** | **Research backend/dashboard** | **PLANNED** | Develop local research interface for interactive retrospective forecast inspection and offline scenario replay. |
| **7** | **External feedback and permission clarification** | **PLANNED** | Clarify dual-licensing discrepancy with data maintainers (ODC-BY / CC BY-NC-SA vs Figshare CC BY) before competition submission or public model weight distribution. |
| **8** | **Final verification/submission materials** | **PLANNED** | Independent multi-platform audit, reproduction scripts, and submission package compilation. |
| **9** | **Submission** | **PLANNED** | Final entry packaging and formal review submission. |

---

## 3. Current Test & Verification Status

- **Unit Test Suite**: **46 tests passing** (100% pass rate in fresh Python 3.12 environment).
  - 33 Stage 2 synthetic tests covering data contracts, feature extraction, event labeling, LOPO partitioning, and review allowlists.
  - 13 Stage 3 synthetic tests covering preflight invariant enforcement, training-only scaling, data isolation, unequal fold weighting, candidate tie-breaking, metric formulas, and cross-platform path handling.
- **Offline Synthetic Execution**: All 46 tests run purely in memory using synthetic fixtures and do not require raw or processed participant data.
- **Independent Verification Status**: `scripts/verify_stage3.py` verified **PASS**:
  1. All 728 distinct fit combinations (672 inner selection fits + 56 outer refits) validated by composite key `(stage, outer_fold, held_out_pid, inner_fold, family, variant, candidate_id)`.
  2. Outer test completeness: 39,496 origins joined by `origin_id` with 0-tolerance float target matching.
  3. Candidate selection optimality: minimal equal-person validation MAE under deterministic tie-breaking.
  4. Metric reconciliation: zero discrepancy between reported metrics and raw prediction calculations.
  5. End-to-end refit reproduction of preselected fold `holdout_012`: reproduced predictions match stored predictions to within machine precision (`max_abs_diff = 5.68e-14`).

---

## 4. Key Scientific Findings (Stage 3 Benchmark)

The Stage 3 benchmark evaluated Ridge regression and Histogram Gradient Boosting across two feature variants:
- **Sensor-Only**: 21 trailing sensor features (13 lags across 60 minutes, 6 rolling statistics, 2 trailing linear slopes).
- **Sensor + Baseline**: 25 features (21 sensor features + Age, BMI, HbA1c, Fasting Glucose).

### Measured Outcomes
1. **Dynamic Sensor Trajectory Outperforms Baselines**:
   - Ridge sensor-only achieved a primary equal-person MAE of **13.50 mg/dL** across 14 unseen LOPO participants, representing a **+10.93% skill improvement** over simple persistence (15.15 mg/dL).
   - Trailing linear extrapolation failed severely (**20.41 mg/dL MAE**, -34.71% skill vs persistence) due to sensor noise amplification.
2. **Static Demographic Fusion Provides No Generalization Advantage**:
   - For Ridge regression, adding static baseline screening features yielded a negligible paired difference of **\(\Delta = +0.056\) mg/dL** (95% bootstrap CI: `[-0.33, +0.39]` mg/dL, spanning zero).
   - For Histogram Gradient Boosting, adding baseline variables worsened performance by **\(\Delta = +0.374\) mg/dL** (9 out of 14 participants experienced higher error).
   - **Conclusion**: Trailing sensor dynamics (\(t-60\) to \(t\)) dominate 30-minute forward extrapolation in unseen participants. Static baseline screening values collected weeks or months earlier provide no actionable predictive signal for short-term forecasts.

---

## 5. Known Scientific, Medical & Regulatory Boundaries

1. **Retrospective Processed Signal Only**: The dataset evaluates released CGMacros Dexcom G6 data containing upstream interpolation, sensor-level filtering, and artifact corrections. Causal live equivalence is **NOT ESTABLISHED**.
2. **Synthetic Grid vs Native Sensor Packets**: The 5-minute sampling grid is an analytical construct and does not reconstruct native Bluetooth packet timing, transmitter clock drift, or transmission dropouts.
3. **No Clinical Efficacy or Device Exemption**: GlucoTwin has not received FDA clearance, CE marking, CDSCO approval, or prospective clinical trial validation. It is not an approved medical device, and labeling it as "research only" does not confer legal exemption for clinical deployment.
4. **Strictly No Treatment or Dosing Guidance**: Predictions must never be used to guide insulin titration, medication administration, carbohydrate consumption, or acute clinical management.
5. **No Validation on Indian Cohorts**: Pathophysiology, diet, and glycemic variability in Indian or South Asian populations have not been evaluated.

---

## 6. Licensing & Permission Questions

- **Source Dataset**: Gutierrez-Osuna et al., CGMacros PhysioNet v1.0.0 (DOI: 10.13026/3z8q-x658), licensed under ODC-BY 1.0 and CC BY-NC-SA 4.0.
- **Cross-Deposit Discrepancy**: A Figshare cross-deposit lists CC BY 4.0. Reconciling this discrepancy with the maintainers is required before public distribution of derived artifacts, per-origin predictions, or competition entries.
- **Local Data Boundary**: All raw CSV files, participant observations, feature tables, per-origin predictions, and model weights are strictly excluded from version control and public distribution.

---

## 7. Next Actions & Stage 4 Transition

1. **Next Planned Stage**: Stage 4: Fusion interpretation and separate patient adaptation.
2. **Action Item**: Implement the frozen first-48-hour within-patient adaptation protocol (`personalization_coverage.csv`) to test whether patient-specific dynamic calibration outperforms static demographic fusion.
3. **Action Item**: Implement split conformal prediction bounds for non-parametric uncertainty estimation.
