# GlucoTwin — Project Status & Roadmap

## 1. Project Purpose & Scope

GlucoTwin investigates retrospective 30-minute continuous glucose forecasting in adults with Type 2 Diabetes using trailing sensor observations and static baseline clinical screening characteristics.

- **Current Stage**: Stage 4 (Retrospective Within-Patient Adaptation) — **reported complete**.
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
| **3** | **Retrospective benchmark** | **reported complete** | Executed all 728 planned fits across 14 LOPO folds (39,496 paired 5-minute origins). 46 unit tests passing. Verified that baseline demographic fusion provides no generalization advantage over sensor-only dynamics. Resolved bootstrap RNG state discrepancy. Evidence: `reports/stage3_remediation/preflight_report.json`, `reports/stage3_remediation/verification.json`, `reports/stage4/stage3_bootstrap_reconciliation.md`. |
| **4** | **Patient adaptation** | **reported complete** | Evaluated fixed patient-specific median residual correction from first 48 elapsed hours across 31,552 later-period origins. All 14 participants met adequacy gates. Ridge sensor-only improved by -0.4703 mg/dL MAE (95% CI [-0.9165, -0.1054], 11 improved, 3 worsened). Evidence: `configs/stage4_protocol.json`, `reports/stage4/verification.json`, `reports/stage4/aggregate_metrics.csv`, `reports/stage4/adaptation_comparison.csv`, `reports/stage4/bootstrap_summary.json`. |
| **5** | **Uncertainty and failure handling** | **PLANNED (NEXT)** | Implement non-parametric split conformal prediction intervals (90%/95% marginal coverage) and analyze out-of-distribution / sensor-gap failure modes. |
| **6** | **Research backend/dashboard** | **PLANNED** | Develop local research interface for interactive retrospective forecast inspection and offline scenario replay. |
| **7** | **External feedback and permission clarification** | **PLANNED** | Clarify dual-licensing discrepancy with data maintainers (ODC-BY / CC BY-NC-SA vs Figshare CC BY) before competition submission or public model weight distribution. |
| **8** | **Final verification/submission materials** | **PLANNED** | Independent multi-platform audit, reproduction scripts, and submission package compilation. |
| **9** | **Submission** | **PLANNED** | Final entry packaging and formal review submission. |

---

## 3. Current Test & Verification Status

- **Unit Test Suite**: **62 tests passing** (100% pass rate in Python 3.12 environment).
  - 33 Stage 2 synthetic tests covering data contracts, feature extraction, event labeling, LOPO partitioning, and review allowlists.
  - 13 Stage 3 synthetic tests covering preflight invariant enforcement, training-only scaling, data isolation, unequal fold weighting, candidate tie-breaking, metric formulas, and cross-platform path handling.
  - 16 Stage 4 synthetic tests covering median residual sign, manual offset calculation, held-out participant exclusion, later-label change immunity, boundary purging, gap non-compression, adequacy gates, shared bootstrap draw hashing, and preflight tamper detection.
- **Offline Synthetic Execution**: All 62 tests run purely in memory using synthetic fixtures and do not require raw or processed participant data.
- **Stage 4 Independent Verification Status**: `scripts/verify_stage4.py` verified **PASS** across all 11 gates:
  1. Config & input hashes: exact match across all declared input matrices and split manifests.
  2. Participant adequacy: all 14 participants meet coverage (>=80%) and origin count (>=100 cal, >=100 later) thresholds.
  3. Temporal partitioning: strict temporal separation verified (7,709 calibration, 31,552 later evaluation, 235 boundary-purged).
  4. Base model purity: zero held-out participant leakage in outer or inner LOPO fits.
  5. Offset recomputation: recomputed from calibration predictions with zero difference (< 1e-12 mg/dL).
  6. Adapted prediction identity: all 31,552 adapted predictions strictly equal base + offset (< 1e-12 mg/dL).
  7. Origin ID join: exactly 31,552 distinct, non-duplicate paired origin IDs.
  8. Metric recomputation: all participant and aggregate metrics match raw calculations (< 1e-12 mg/dL).
  9. Shared bootstrap reproducibility: deterministic draw matrix (hash `af81ab35...`) and CIs reproduced bit-for-bit.
  10. End-to-end refit reproduction: preselected Participant 12 refitted from scratch matches stored predictions (< 5.68e-14 mg/dL difference).
  11. Historical preservation: Stage 1, Stage 2, and Stage 3 checkpoints preserved intact.

---

## 4. Key Scientific Findings

### Stage 3: Retrospective Benchmark Summary
- Ridge sensor-only achieved equal-person MAE of **13.50 mg/dL** across 14 LOPO folds (+10.93% skill vs persistence 15.15 mg/dL).
- Demographic baseline fusion provided no benefit (\(\Delta = +0.056\) mg/dL for Ridge, \(\Delta = +0.374\) mg/dL worse for HistGB).
- Resolved bootstrap discrepancy: proven that differences between original and remediation intervals stemmed from RNG sequential consumption vs per-call seeding.

### Stage 4: Retrospective Within-Patient Adaptation Outcomes (31,552 Later Origins)
Evaluated across 5 paired methods on identical 31,552 later-period origins:
1. **Persistence Reference**:
   - Equal-person MAE: **14.8903 mg/dL** | RMSE: **22.5087 mg/dL**
2. **Ridge Sensor-Only (Unadapted)**:
   - Equal-person MAE: **13.1573 mg/dL** | RMSE: **19.4103 mg/dL**
3. **Ridge Sensor-Only (Adapted via 48h Median Residual Offset)**:
   - Equal-person MAE: **12.6871 mg/dL** | RMSE: **19.1466 mg/dL**
   - **Adaptation Delta MAE**: **-0.4703 mg/dL** (95% bootstrap CI: `[-0.9165, -0.1054]` mg/dL)
   - **Participants Improved**: **11 improved, 3 worsened, 0 tied** (out of 14)
   - **Skill vs Persistence**: **-2.2033 mg/dL** MAE (95% CI: `[-2.5333, -1.8860]`, 14 improved)
4. **Ridge Sensor + Baseline (Unadapted)**:
   - Equal-person MAE: **13.2608 mg/dL** | RMSE: **19.2812 mg/dL**
5. **Ridge Sensor + Baseline (Adapted via 48h Median Residual Offset)**:
   - Equal-person MAE: **12.7692 mg/dL** | RMSE: **19.0876 mg/dL**
   - **Adaptation Delta MAE**: **-0.4916 mg/dL** (95% bootstrap CI: `[-0.8672, -0.1112]` mg/dL)
   - **Participants Improved**: **11 improved, 3 worsened, 0 tied** (out of 14)

### Core Scientific Conclusions
- **Within-patient adaptation provides a modest, statistically non-zero retrospective benefit**: A simple scalar median residual offset computed over the first 48 elapsed hours reduced 30-minute forecasting MAE by approximately **0.47 mg/dL** on later observations, with 11 of 14 participants benefiting.
- **Baseline fusion remains ineffective**: Even after adaptation, Ridge sensor-only (12.6871 mg/dL) outperforms Ridge sensor + baseline (12.7692 mg/dL). Static demographic screening characteristics continue to offer no predictive advantage over sensor dynamics.
- **Boundary & Generalization Caveats**: Stage 4 is an exploratory retrospective finding on previously examined participants. It does not establish real-time causal personalization or generalization to unseen patient cohorts.

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
- **Local Data Boundary**: All raw CSV files, participant observations, feature tables, per-origin predictions, patient offsets, and model weights are strictly excluded from version control and public distribution.

---

## 7. Next Actions & Stage 5 Transition

1. **Next Planned Stage**: Stage 5: Uncertainty and failure handling.
2. **Action Item**: Implement non-parametric split conformal prediction intervals on the later evaluation period to provide valid 90% and 95% marginal coverage bounds.
3. **Action Item**: Analyze prediction behavior during sensor dropout episodes, post-gap sensor reconnections, and high rate-of-change events.
