# GlucoTwin — Project Status & Roadmap

## 1. Project Purpose & Scope

GlucoTwin investigates retrospective 30-minute continuous glucose forecasting in adults with Type 2 Diabetes using trailing sensor observations and static baseline clinical screening characteristics.

- **Current Stage**: Stage 6 local research replay - **implemented and verified, including Chromium browser checks**.
- **Current Scope**: Restricted retrospective research on published, processed sensor signals.
- **Commit SHA**: `c2aa0201fa2a5e48315eac2492a5db205e8641dd` (actual completion-pass starting HEAD on `main`; subsequent work remains unstaged).
- **Causal Live Equivalence**: **NOT ESTABLISHED**.
- **Public Competition Permissions**: **UNRESOLVED**.
- **Medical / Clinical Clearance**: **NONE**. Not a medical device; no treatment, dosing, or autonomous alerting capabilities.

---

## 2. Nine-Stage Project Roadmap

| Stage | Name | Status | Key Evidence / Gate Deliverable |
| :---: | :--- | :---: | :--- |
| **1** | **Dataset research/audit** | **reported complete** | Audited PhysioNet CGMacros 1.0.0 (48 CSV tables). Verified source provenance SHA-256 (`b9006433...`). Documented upstream interpolation and timestamp spacing. Evidence: `reports/stage1/provenance_manifest.json`. |
| **2** | **Data and evaluation preparation** | **reported complete** | Established technical contracts, 14 outer LOPO / 3-fold grouped-inner partitions, and data extraction pipelines. Checkpoint frozen (`029b530f...`). Evidence: `reports/stage2/freeze_manifest.json`, `reports/stage2/split_manifest.json`. |
| **3** | **Retrospective benchmark** | **reported complete** | Executed all 728 planned fits across 14 LOPO folds (39,496 paired 5-minute origins). 46 unit tests passing. Observed no demonstrated benefit from static baseline demographic fusion over sensor-only dynamics in this cohort. Resolved bootstrap discrepancy. Evidence: `reports/stage3_remediation/preflight_report.json`, `reports/stage3_remediation/verification.json`, `reports/stage4/stage3_bootstrap_reconciliation.md`. |
| **4** | **Patient adaptation** | **reported complete** | Evaluated fixed patient-specific median residual correction from first 48 elapsed hours across 31,552 later-period origins. All 14 participants met adequacy gates. Ridge sensor-only improved by -0.4703 mg/dL MAE (95% CI [-0.9165, -0.1054], 11 improved, 3 worsened). Evidence: `configs/stage4_protocol.json`, `reports/stage4/verification.json`, `reports/stage4/aggregate_metrics.csv`, `reports/stage4/adaptation_comparison.csv`, `reports/stage4_remediation/adaptation_comparison_extended.csv`, `reports/stage4_remediation/glycemic_slices_summary.csv`. |
| **5** | **Uncertainty and failure handling** | **EXECUTED / VERIFIED (exploratory)** | Frozen 24h offset / 24h interval calibration; both sensor-only references, exact ranks and input-loss stress tests executed. Evidence: `configs/stage5_protocol.json`, `reports/stage5/verification.json`, `reports/stage5/execution_record.md`. No guaranteed coverage or default selection. |
| **6** | **Research backend/dashboard** | **IMPLEMENTED / VERIFIED** | FastAPI, deterministic replay, React dashboard, 114 Python tests and 13 frontend tests pass. Playwright Chromium controls/dropouts/scoring pass; prior Stage 6 browser evidence is preserved. Completion redesign, help, accounting, failure recovery and expanded checks are recorded separately in `reports/completion/`. |
| **7** | **External feedback and permission clarification** | **PARTIAL ? UNSENT DRAFTS** | Clarify dual-licensing discrepancy with data maintainers (ODC-BY / CC BY-NC-SA vs Figshare CC BY) before competition submission or public model weight distribution. Tracker: `docs/licensing_and_permissions_tracker.md`. |
| **8** | **Final verification/submission materials** | **LOCAL VERIFICATION / PACKAGING; SUBMISSION GATES OPEN** | Local showcase/startup/demo/submission checklist drafted; Windows source-copy installation and checks recorded in `reports/completion/`. Official competition requirements, independent multi-platform review and permission gate remain open. |
| **9** | **Submission** | **PLANNED** | Final entry packaging and formal review submission. |

---

## 3. Current Test & Verification Status

- Full Python suite: **114 tests passed** (33 Stage 2, 13 Stage 3, 21 Stage 4, 13 Stage 5, 20 Stage 6, 4 completion regressions, 10 feature-update tests). Frontend: **13 tests passed**; TypeScript and production build pass. Chromium browser verification passes at 1440/768/390/360px; current evidence is in `reports/completion/`.
- Stage 5 focused suite: **13 passed**. Synthetic fixtures plus existing repository integrity checks; no claim that test counts establish scientific validity.
- Stage 5 verifier: **PASS**, recomputing 705,720 stored scenario/variant/level rows, timestamp partitions, offsets, exact ranks, target joins, availability, nested intervals and aggregate/matched metrics.
- All 14 frozen selected Ridge outer refits reproduced original held-out predictions within 5.69e-14 mg/dL. No inner search or full Stage 3 rerun.
- Historical Stage 4 offsets and point metrics reproduced read-only; original outputs unchanged.
- Verifier shares the Stage 2 feature builder and production replay for access-isolation checks; it is not wholly independent. Details: `reports/stage5/verification.json`.

---

## 4. Key Scientific Findings & Bounded Interpretation

### Stage 3: Retrospective Benchmark Summary
- Ridge sensor-only achieved equal-person MAE of **13.50 mg/dL** across 14 LOPO folds (+10.93% skill vs persistence 15.15 mg/dL).
- **Static Baseline Fusion**: Showed no demonstrated benefit in this cohort (\(\Delta = +0.056\) mg/dL for Ridge). For HistGB, the point estimate favored sensor-only (\(\Delta = +0.374\) mg/dL), but both original `[-0.0034, +0.7820]` and remediation `[-0.0244, +0.7831]` bootstrap intervals span zero, indicating statistical uncertainty includes no difference.
- Resolved bootstrap discrepancy: proven that differences between original and remediation intervals stemmed from sequential RNG consumption across models vs per-call generator initialization.

### Stage 4: Retrospective Within-Patient Adaptation Outcomes (31,552 Later Origins)
Evaluated across 5 paired methods on identical 31,552 later-period origins:
1. **Persistence Reference**:
   - Equal-person MAE: **14.8903 mg/dL** | RMSE: **22.5087 mg/dL**
2. **Ridge Sensor-Only (Unadapted)**:
   - Equal-person MAE: **13.1573 mg/dL** | RMSE: **19.4103 mg/dL** | Mean signed error: **-0.0462 mg/dL**
3. **Ridge Sensor-Only (Adapted via 48h Median Residual Offset)**:
   - Equal-person MAE: **12.6871 mg/dL** | RMSE: **19.1466 mg/dL** | Mean signed error: **-1.2654 mg/dL**
   - **Adaptation Delta MAE**: **-0.4703 mg/dL** (95% bootstrap CI: `[-0.9165, -0.1054]` mg/dL, 11 improved, 3 worsened)
   - **Skill vs Persistence**: **-2.2033 mg/dL** MAE (95% CI: `[-2.5333, -1.8860]`, 14 improved)
4. **Ridge Sensor + Baseline (Unadapted)**:
   - Equal-person MAE: **13.2608 mg/dL** | RMSE: **19.2812 mg/dL**
5. **Ridge Sensor + Baseline (Adapted via 48h Median Residual Offset)**:
   - Equal-person MAE: **12.7692 mg/dL** | RMSE: **19.0876 mg/dL**
   - **Adaptation Delta MAE**: **-0.4916 mg/dL** (95% bootstrap CI: `[-0.8672, -0.1112]` mg/dL, 11 improved, 3 worsened)

### Post-Hoc Comparison: Adapted Combined vs Adapted Sensor-Only
- **Exploratory Paired Difference**: \(\Delta = \text{adapted\_combined} - \text{adapted\_sensor} = \mathbf{+0.0821}\) mg/dL (95% bootstrap CI: `[-0.0586, +0.2904]`, 9 improved, 5 worsened).
- **Interpretation**: Even after patient-specific adaptation, static baseline demographic features provide no statistically reliable advantage over pure sensor dynamics in this cohort.

### Mechanistic Analysis of Signed Error Shift
- Unadapted mean signed error was near-zero (-0.0462 mg/dL) purely due to cross-participant cancellation: individual participant biases ranged from \(-6.90\) to \(+6.17\) mg/dL.
- Applying a scalar median offset reduced individual bias magnitude for 11 of 14 participants.
- Calibration residuals are defined as target minus base prediction; evaluation signed error is prediction minus target. Recomputed equal-person calibration residual mean is +0.205796 mg/dL and mean of participant medians (fixed offsets) is -1.219171 mg/dL. Thus -0.046241 + (-1.219171) = -1.265413 mg/dL later mean signed error. Median optimality applies to calibration absolute loss, not guaranteed later-period loss. Meal/postprandial mechanisms remain hypotheses without meal-aligned evidence.

### Descriptive Retrospective Glycemic Slices (Later Period, N = 31,552)
- **Euglycemia (70–180 mg/dL)**: 21,497 origins (68.1% of data, all 14 participants). Unadapted MAE: 10.34 mg/dL \(\to\) Adapted MAE: **10.04 mg/dL** (\(\Delta = -0.30\) mg/dL).
- **Hyperglycemia (>180 mg/dL)**: 10,036 origins (31.8% of data, all 14 participants). Unadapted MAE: 21.66 mg/dL \(\to\) Adapted MAE: 22.23 mg/dL (\(\Delta = +0.57\) mg/dL).
- **Hypoglycemia (<70 mg/dL)**: **Extremely Sparse** — only 19 origins across 2 participants (0.06% of data; 12 of 14 participants had zero hypoglycemic observations). No valid performance claims can be established for this range.

---

## 5. Known Scientific, Medical & Regulatory Boundaries

1. **Retrospective Processed Signal Only**: The dataset evaluates released CGMacros Dexcom G6 data containing upstream interpolation, sensor-level filtering, and artifact corrections. Causal live equivalence is **NOT ESTABLISHED**.
2. **Exploratory Cohort Finding**: The 48-hour calibration window was evaluated on the same 14 participants previously examined in Stage 3. It is not an independent confirmation cohort.
3. **No Clinical Validation or Clearance**: GlucoTwin has not been evaluated in prospective clinical trials, has received no regulatory clearance (FDA, CE, CDSCO), and is strictly not a medical device.
4. **Strictly No Treatment Guidance**: Predictions must never be used to guide insulin titration, medication administration, carbohydrate consumption, or acute clinical management.
5. **No Indian Cohort Validation**: Pathophysiology, diet, and glycemic variability in Indian or South Asian populations have not been evaluated.

---

## 6. Licensing & Permission Questions

- **Source Dataset**: Gutierrez-Osuna et al., CGMacros PhysioNet v1.0.0 (DOI: 10.13026/3z8q-x658), licensed under ODC-BY 1.0 and CC BY-NC-SA 4.0.
- **Cross-Deposit Discrepancy**: A Figshare cross-deposit lists CC BY 4.0. Reconciling this discrepancy with the maintainers is required before public distribution of derived artifacts, per-origin predictions, or competition entries. Tracker maintained in `docs/licensing_and_permissions_tracker.md`.
- **Local Data Boundary**: All raw CSV files, participant observations, feature tables, per-origin predictions, patient offsets, and model weights are strictly excluded from version control and public distribution.

---

## 7. Next Actions after Stage 5

1. Manually review Stage 5 source, tests and candidate aggregates pending applicable permissions; no staging, commit or push was performed.
2. Resolve the existing licensing/permissions discrepancy and upstream-processing evidence gaps.
3. Manually review the completed Stage 6 browser evidence and synthetic screenshots; do not infer publication or clinical clearance. No new dataset or real sensor integration was added.

## Historical final Stage 4 correction (2026-10-15; Stage 5 status superseded below)

**High-glucose trade-off:** adaptation increases >180 mg/dL participant-averaged
slice MAE by **0.570931 mg/dL** and increases underprediction (mean signed error
-9.878717 to -11.097888 mg/dL). No default selection based solely on overall MAE,
no target-dependent switching, and no correction tuning against these outcomes.
Both adapted and unadapted sensor-only references remain in the proposed Stage 5 design.

Participant slice-origin fractions times their own slice MAEs reconstruct every
participant's overall MAE; averaging these reconstructs 13.157343 unadapted and
12.687070 adapted (delta -0.470274 mg/dL). Cohort origin proportions times separately
participant-averaged slice errors instead give 13.944538 and 13.921516: they mix
weights and contributor sets and do not reconstruct equal-person MAE. See
`reports/stage4_remediation/final_correction_aggregate.json`; participant details
remain under ignored `data/processed/stage4/final_correction/`.

Severe sparsity of observations below 70 mg/dL remains (19 origins, 2 participants).
Lack of demonstrated fusion benefit remains bounded to this cohort.

Excluded from model fitting and interval calibration; outcomes from this cohort have previously been examined, so this analysis remains exploratory.

The proposed 24-hour offset is a different model from Stage 4's 48-hour offset and
requires fresh evaluation. Stage 5 remains proposed and unexecuted. Licensing,
upstream signal processing, independent cohort validation, and dependent-observation
exchangeability remain unresolved. See the corrected handoff and execution record
for commands and their actual results.

## Stage 5 executed results (2026-10-15)

Frozen design and implementation: `configs/stage5_protocol.json` and
`docs/stage5/IMPLEMENTED_PROTOCOL.md`; historical proposal is preserved.
New 24h adaptation remains separate from the original 48h Stage 4 experiment.
No default selection, target-dependent switching or evaluation-based tuning.

| Variant | alpha | MAE | RMSE | Mean signed error | Empirical coverage | Mean width |
|---|---|---|---|---|---|---|
| sensor_only_offset24h | 0.050000 | 12.780945 | 19.156085 | -0.892881 | 0.941726 | 82.367752 |
| sensor_only_offset24h | 0.100000 | 12.780945 | 19.156085 | -0.892881 | 0.889133 | 58.442915 |
| sensor_only_unadapted | 0.050000 | 13.157343 | 19.410279 | -0.046241 | 0.939586 | 82.225878 |
| sensor_only_unadapted | 0.100000 | 13.157343 | 19.410279 | -0.046241 | 0.887960 | 58.899669 |

Coverage values are measured empirical fractions at the listed alpha, not guarantees.
Equal-participant clean metrics use the same 31,552 scoreable origins and 14 people.
Scheduled count is 35,286; 31,655 points/intervals issued, 31,552 scored. Input-loss
15/30/60/120-minute scenarios issued 31,445/31,403/31,319/31,151 forecasts, scoring
31,342/31,300/31,216/31,048. Matched accepted-origin predictions and bounds coincide
with clean replay; differences over whole scenarios reflect exclusions.

**High-glucose trade-off:** the new 24h model increases >180 slice MAE from
21.657423 to 22.216207 (+0.558784 mg/dL) and increases underprediction (mean signed
error -9.878717 to -10.725356). The original Stage 4 48h deterioration of +0.570931
mg/dL is preserved separately. Severe sparsity below70 persists: 19 origins,
2 participants. Neither all-participant slice coverage nor test counts establish robustness.

Excluded from model fitting and interval calibration; outcomes from this cohort have previously been examined, so this analysis remains exploratory.

Application future-access tests do not undo upstream interpolation. Actual arrival
and original observation information remain unresolved; exchangeability is not
established. No prospective/live, clinical, dosing or guaranteed-coverage claims.
Permissions remain unresolved. Calibration-period dropout, observation-loss mode B,
and interval scores are deferred. Detailed evidence remains ignored locally;
candidate reports are for technical review pending permissions.

## Stage 6 local research application (2026-10-15)

FastAPI backend and React/TypeScript dashboard run on loopback ports 18060 and
15173. One-command startup: `.\.venv\Scripts\python.exe scripts/start_stage6.py`.
Default independent synthetic-only mode needs no CGMacros artifacts. Persistence
is explicit, synthetic intervals unavailable, and synthetic outcomes are never
labelled T2D validation. `--local` enables approved private processed-data streams
with the matching frozen sensor-only Ridge model, median 24h offset and quantiles.

The deterministic virtual clock processes minute arrivals, phase transitions,
forecast issuance and target maturity in order, including all intermediate minutes
under accelerated playback. Prediction requests contain arrived history only;
evaluator references remain separate. Required history is 61 minute cells spanning
60 elapsed minutes. Exact targets are origin+30 elapsed minutes. Warm start traverses
the same chronological engine. SQLite metadata/events remain ignored locally;
server restart expires sessions explicitly. No live sensor or production hosting.

Original Stage 6 evidence recorded 20 focused backend tests, 100 Python tests and 7 frontend guard tests. The completion pass now has 24 focused replay tests, 104 Python tests and 10 frontend tests;
TypeScript, build and network API integration pass. All 14 local streams agree
with Stage 5 on 700 checked forecasts over the first 120 evaluation minutes per
source (max difference 8.57e-11 mg/dL), including early-phase reconstruction and
calibration checks. This is agreement testing, not a new cohort performance study.

**Original Stage 6 browser completion (historical checkpoint):** locally installed Playwright Chromium resolved the earlier
computer-use tooling blocker. Controls, all four dropout durations, exact delayed
scoring, persistent synthetic disclosure, 1440/768/390px layout and clipping/overflow
checks pass. Final run: zero console/page errors, failed requests or failed API
responses. Six synthetic screenshots captured and inspected. The browser pass found
and fixed a scrolling-disclosure defect and a poll/delete race on session replacement;
two regression tests bring the frontend count to 7. See
`reports/stage6/browser_verification.json` and `STAGE6_HANDOFF_FOR_REVIEW.md` (local).

Scientific results remain frozen. Nominal Stage 5 coverage was not fully achieved;
adaptation worsened >180 errors and underprediction; below70 observations are
sparse. Upstream interpolation/actual arrivals remain unresolved, this previously
examined cohort remains exploratory, and there are no clinical or guaranteed
coverage claims. Permissions remain unresolved; no messages or publication.

## Completion pass

Implemented a readable dashboard, seven-step keyboard Help, historical endpoint details, explicit availability/scoring denominators and expired/network recovery. See `docs/showcase/README.md`, `reports/completion/` and the ignored `GLUCOTWIN_COMPLETION_HANDOFF_FOR_REVIEW.md`. Earlier reports remain historical evidence. Stage 7 permissions/external feedback and Stage 9 submission remain planned; no contact, publishing or deployment occurred.

## Scenario Lab feature update (2026-10-16)

Implemented nine independent authored scenario choices with bounded seeds/duration and generator provenance; a migrated SQLite library with renaming, read-only summaries and honest new-session recreation; accessible forecast inspection; revealed-only chart ranges/follow mode; explicit summary denominators and five synthetic-only exports. Patient exports remain blocked. See `docs/stage6/SCENARIO_LAB.md` and separate `reports/feature_update/` evidence. Original Stage 4/5/completion reports and uncommitted showcase work remain preserved. Permissions, external feedback and official competition/submission gates remain unresolved; Stages 7 and 9 are not complete.

## Release-readiness review (2026-10-16)

Separate release evidence is under `reports/release_readiness/`; adaptable materials and official-requirement review are under `docs/release/`. The Stage 1 source register identifies Happiest Health Digital Twin Challenge 2026; the official Unstop AMP page was retrieved again. Its static/dynamic fusion and adverse-event requirements require organizer scope confirmation. Public-repository submission, a minimum20-minute video and PDF/PPT materials remain gates; local synthetic packaging is not submission readiness. Stage7 remains partial: permissions and external feedback are unanswered, with UNSENT drafts only. Stage8 covers local verification/material preparation and exact-archive synthetic reproducibility only to the extent recorded. Stage9 remains pending actual user submission. No publication, deployment or external messages. Research artifacts and prior reports remain preserved.

Release execution outcome: 116 full Python tests, 13 frontend tests, TypeScript/build, npm audit (0 vulnerabilities), 10 API groups, 18 main Chromium groups and four modal widths pass. Limited historical agreement: 700 forecasts across14 sources, max8.57e-11mg/dL;197 frozen/historical files and33 private inputs preserve byte hashes. Exact synthetic archive contains45 selected files plus its generated manifest; fresh installation runs36 source-only Python tests,13 frontend tests,build and18 browser groups, with missing private artifacts explicitly409. A14.56-second silent engineering video and visually checked1-page architecture/7-page presentation PDF drafts exist; the required20-minute explanatory video, team review, organizer scope confirmation, permissions and independent feedback remain open. See the local release handoff for exact commands and evidence limits.

## Functional and UI audit (2026-10-16)

Scoped to the existing replay application. Historical-inspector polling and incompatible source/scenario switching were corrected; library coordination/name validation/feedback, chart follow behavior and visual hierarchy were improved. Evidence is separate in `reports/functional_ui/`; previous reports, frozen research and permissions status remain preserved. No models, quantiles, partitions, treatment/live-sensor features, submission work or external messages were added. Final counts and limitations are recorded in the local functional/UI handoff.

Functional/UI final scope: 65 feature/action rows, 117 full Python tests, 22 frontend tests, 18 main Chromium groups at1440/768/390/360px, plus explicit control/error/stress/private checks. The isolated44-file copy passes37 source-only Python tests,22 frontend tests/build and18 browser groups; a separate no-runtime/no-report startup also passes. Limited frozen agreement remains700 forecasts/14 sources, not a full-cohort reanalysis. The normal synthetic app is available on15173/18060. No permission, clinical or production-validation claim is added.
