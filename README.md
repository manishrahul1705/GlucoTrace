# GlucoTwin

> **GlucoTwin — Patient-Adaptive Glucose Forecasting and Replay Research Prototype**

GlucoTwin investigates retrospective 30-minute ahead continuous glucose monitoring (CGM) forecasting and within-patient calibration in adults with Type 2 Diabetes using trailing sensor dynamics and baseline clinical screening characteristics (Age, BMI, HbA1c, Fasting Glucose).

This repository contains the independently authored open-source research codebase, data preparation pipelines, feature extraction modules, cross-validation protocols, interactive virtual replay engine, Scenario Lab, and synthetic test suites.

**Competition Review Documentation:**
- [Requirements & Evidence Matrix](docs/review/REQUIREMENTS_EVIDENCE_MATRIX.md)
- [Project Positioning & Naming Reconciliation](docs/review/PROJECT_POSITIONING_AND_NAMING.md)
- [Submission Gaps, Clarifications & Deliverables Blueprint](docs/review/SUBMISSION_GAPS_AND_CLARIFICATIONS.md)
- [Stages 1 & 2 Execution Record](docs/review/STAGES_1_2_EXECUTION_RECORD.md)

---

## 1. Project Purpose & Scope

The core scientific inquiry of GlucoTwin is evaluating whether concatenating static patient screening variables to short-term dynamic sensor features improves 30-minute forward glucose extrapolation in unseen individuals, or whether short-term sensor dynamics dominate the forecast horizon.

- **Current Stage**: Stage 6 local research app implemented and verified with Playwright Chromium. Historical experiments remain frozen.
- **Current Scope**: Retrospective research on released, processed continuous glucose monitoring data from the PhysioNet CGMacros v1.0.0 cohort.
- **Evaluation Design**: 14 Leave-One-Participant-Out (LOPO) outer test folds with nested 3-fold grouped inner cross-validation for hyperparameter selection across 39,496 paired 5-minute issue origins.

---

## Local research dashboard

Select and verify a Python 3.12 environment first (an existing `.venv` may lack dependencies). Start the synthetic-only dashboard (after the setup in [Stage 6 instructions](docs/stage6/README.md)):

```powershell
.\.venv\Scripts\python.exe scripts/start_stage6.py
```

Open http://127.0.0.1:15173/. Add `--local` only for private processed-data replay (requires the complete trusted, matching observations/model/calibration bundle; data files alone are insufficient). See the [Stage 6 instructions and startup guide](docs/stage6/README.md). This is retrospective/synthetic research,
not a live sensor connection or clinical tool. No deployment is included.

## Scenario Lab and session tools

The replay workspace supports authored seeded scenarios, a local session library, forecast inspection, revealed-history exploration, and five synthetic-only export formats. See [feature setup/API/export contracts](docs/stage6/SCENARIO_LAB.md). Original research results remain preserved.

## 2. Implemented Components

The project is structured modularly under `src/glucotwin/`:

- **Data Contracts & Preprocessing** (`src/glucotwin/contracts.py`, `preprocessing.py`):
  Enforces monotonic timestamps, physical glucose bounds ([40, 400] mg/dL), 60-minute history availability, and causal boundary isolation.
- **Feature Engineering** (`src/glucotwin/features.py`, `labels.py`):
  Extracts 21 trailing sensor features (13 discrete lags at 5-minute intervals from \(t-60\) to \(t\), 6 rolling window statistics, and 2 trailing linear slopes) and 4 baseline features (Age, BMI, HbA1c, Fasting Glucose).
- **Partitioning & Protocol** (`src/glucotwin/splits.py`, `configs/stage2_protocol.json`, `configs/stage3_run.json`):
  Enforces strict participant disjointness across 14 outer folds and grouped inner folds.
- **Execution & Invariant Enforcement** (`src/glucotwin/stage3/integrity.py`):
  Preflight validation verifying 10 protocol, feature table, and split invariants before model training.
- **Model Training & Prediction** (`src/glucotwin/stage3/training.py`, `selection.py`):
  Supports Ridge regression and Histogram Gradient Boosting with training-only feature standardization and deterministic candidate tie-breaking.
- **Metric Computation & Bootstrap** (`src/glucotwin/stage3/metrics.py`):
  Full IEEE 754 float64 precision calculation of participant-equal and window-weighted MAE, RMSE, signed error, and 2,000-draw paired participant bootstrap confidence intervals.
- **Independent Verifier** (`scripts/verify_stage3.py`):
  Validates all 728 distinct fit ledger identities, origin-to-target joins, candidate optimality, and end-to-end refit reproduction.

---

## 3. Quickstart & Installation (Windows / PowerShell)

### Prerequisites
- Python 3.12 (verified interpreter: 3.12.10); Node 24.21.0 / npm 11.19.0 for the dashboard
- Git

### 1. Clone the Repository
```powershell
git clone https://github.com/manishrahul1705/GlucoTwin.git
cd GlucoTwin
```

### 2. Create and Activate Virtual Environment
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-stage6.txt
```

### 3. Run Synthetic Verification Tests (No Data Required)
The unit suite uses synthetic fixtures and repository integrity checks. It does not require downloading external datasets. Install the Stage 6 dependencies above for the API tests:
```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```
At the Phase 3 candidate revision, verification ran **144 Python tests** and **30 frontend tests** (six Vitest files). These are recorded results at this revision, not fixed future test counts. Tests use synthetic fixtures; they do not establish patient execution or clinical validity. See [current commands, environment selection, package modes and the restricted-loader workaround](docs/stage6/README.md). Historical verifier scripts are separate from the complete unit suite.

---

## 4. Dataset Reproduction & Benchmark Execution

To reproduce the retrospective benchmark on real clinical data:

### Step 1: Review License Terms
Read `docs/stage1/licensing_and_permissions.md` and `docs/stage2/licensing_status.md`. Ensure your intended research use complies with the PhysioNet Open Data Commons Attribution License (ODC-BY 1.0) and CC BY-NC-SA 4.0.

### Step 2: Download the PhysioNet Dataset
Download the 48 raw table files and publisher dictionaries directly from PhysioNet via HTTPS byte-range extraction:
```powershell
.\.venv\Scripts\python.exe scripts/download_data.py
```
*Note: This downloads source data locally into `data/raw/` (ignored by git).*

### Step 3: Run Stage 2 Data Preparation
Generate standardized observation grids, paired 5-minute origins, and feature tables:
```powershell
.\.venv\Scripts\python.exe scripts/prepare_stage2.py
.\.venv\Scripts\python.exe scripts/verify_stage2.py --rerun
```

### Step 4: Execute the Stage 3 Benchmark
Run the frozen benchmark across all 14 LOPO folds (728 fits):
```powershell
.\.venv\Scripts\python.exe scripts/run_stage3.py --restart
```

### Step 5: Independently Verify Results
Verify fit ledger integrity, origin joins, candidate selection optimality, and refit reproduction:
```powershell
.\.venv\Scripts\python.exe scripts/verify_stage3.py
```

---

## 5. Historical benchmark findings

*These historical benchmark results are preserved. Later new-experiment sensor/fusion and exact-endpoint research are described in [current Stage 6 instructions](docs/stage6/README.md) and [fusion/endpoint scope](docs/stage6/FUSION_AND_ENDPOINTS.md). They do not demonstrate a fusion improvement. Detailed historical analysis remains in [PROJECT_STATUS.md](PROJECT_STATUS.md).*

1. **Short-Term Dynamics Outperform Baselines**:
   - Ridge regression on 21 sensor features achieved a primary equal-person MAE of **13.50 mg/dL**, outperforming simple persistence (15.15 mg/dL) by **+10.93% skill**.
   - Trailing linear extrapolation failed severely (**20.41 mg/dL MAE**, -34.71% skill vs persistence) due to noise amplification.
2. **No Demonstrated Static-Fusion Benefit in This Cohort**:
   - Concatenating static baseline screening variables (Age, BMI, HbA1c, Fasting Glucose) to the sensor trajectory yielded a statistically negligible difference for Ridge (\(\Delta = +0.056\) mg/dL, 95% bootstrap CI `[-0.33, +0.39]`).
   - For Histogram Gradient Boosting, static fusion degraded performance by \(\Delta = +0.374\) mg/dL (9 of 14 participants worsened).
   - In this cohort and candidate set, static screening features did not demonstrate additional benefit over trailing sensor dynamics. This does not establish lack of benefit in other cohorts or settings.

---

## 6. Strict Scientific, Medical & Regulatory Boundaries

These boundaries reflect technical constraints, not claims of regulatory clearance:

- **Retrospective Processed Signal Only**: The released PhysioNet CGMacros signals contain upstream sensor-level filtering, interpolation, and artifact correction. **Causal live equivalence is NOT ESTABLISHED**.
- **Sampling vs Packet Arrivals**: The computational 5-minute grid does not reconstruct native Bluetooth packet receipt times, transmitter clock drift, or transmission dropouts.
- **No Clinical Clearance or Device Exemption**: GlucoTwin is not an approved medical device, diagnostic tool, or clinical decision support system. It has not received FDA clearance, CE marking, CDSCO approval, or prospective clinical trial validation. Labeling software as "research only" does not confer legal exemption for clinical use.
- **Regulatory Compliance Not Assessed**: Technical exclusion of raw data via `.gitignore` and running offline synthetic demonstrations do not constitute compliance with the Digital Personal Data Protection Act (DPDP Act 2023) or HIPAA. Formal statutory and regulatory compliance has not been assessed.
- **Single-Point Endpoint & No Alert Mechanisms**: Predictions are restricted to a single continuous scalar value at origin + 30 minutes ($t+30$). The software contains no multi-step future trajectory, no threshold-crossing detection, no adverse event probability calculation, and no clinical warning or alert mechanisms.
- **No Treatment, Dosing, or Alert Guidance**: Under no circumstances should predictions be used for insulin titration, oral agent adjustments, carbohydrate intake, or acute clinical alerts.
- **No Population Generalization to Indian Cohorts**: Glycemic variability, pathophysiology, and dietary compositions in Indian or South Asian populations have not been validated.
- **Public Competition Permissions Unresolved**: Reconciling the PhysioNet ODC-BY / CC BY-NC-SA terms with the Figshare CC BY cross-deposit remains pending with maintainers. Raw data, participant feature tables, per-origin predictions, and model weights are strictly retained in ignored local storage. Competition eligibility and redistribution rights are not cleared.

---

## 7. Licensing & Attribution

- **Project Software**: Independently authored source code, test suites, and configurations are licensed under the [MIT License](LICENSE).
- **Data Licensing**: The code license does not relicense or grant rights to the underlying CGMacros dataset. The dataset remains subject to its governing PhysioNet licenses (ODC-BY 1.0 and CC BY-NC-SA 4.0).
- **Citation**:
  - Gutierrez-Osuna, Kerr, Mortazavi & Das, *Continuous Glucose Monitoring and Macronutrient Composition (CGMacros)*, PhysioNet v1.0.0 (2025), DOI: [10.13026/3z8q-x658](https://doi.org/10.13026/3z8q-x658).
  - Das et al., "CGMacros: A multimodal dataset of continuous glucose monitoring and dietary macronutrients in type 2 diabetes," *Scientific Data* 12:1557 (2025), DOI: [10.1038/s41597-025-05851-7](https://doi.org/10.1038/s41597-025-05851-7).

---

## 8. Hackathon Submission & Team Attribution

- **Target Competition**: Happiest Health — CRP Digital Twin Challenge 2026 (Hosted on Unstop)
- **Challenge Track**: Chronic Disease Management Proof of Concept (Type 2 Diabetes)
- **Team Name**: `[Your Team Name]`
- **Institution / College**: `[Your College / University Name]`
- **Team Members & Roles**:
  - `[Member 1 Name]` — Machine Learning & Research Architecture
  - `[Member 2 Name]` — Frontend Engineering & Data Visualization
  - `[Collaborator 3 Name]` — Clinical Data Pipelines & Verification
- **Submission Repository**: https://github.com/manishrahul1705/GlucoTwin
- **Video Walkthrough ($\ge$ 20 min)**: `[Link to unlisted YouTube / Google Drive demonstration]`
- **Architecture & Presentation Decks**: See `docs/review/SUBMISSION_GAPS_AND_CLARIFICATIONS.md` for preparation blueprints.

### Non-Affiliation & Trademark Notice
*GlucoTwin is an independent academic and open-source research prototype developed by Manish Rahul and collaborators for the Happiest Health CRP Digital Twin Challenge 2026. This project is not affiliated with, sponsored by, or endorsed by glucotwin.com, commercial metabolic health platforms, or unrelated academic research publications sharing the name.*
