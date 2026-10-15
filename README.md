# GlucoTwin

> **Restrospective 30-Minute Continuous Glucose Forecasting Research Benchmark**

GlucoTwin investigates 30-minute ahead continuous glucose monitoring (CGM) forecasting in adults with Type 2 Diabetes using trailing sensor dynamics and baseline clinical screening characteristics (Age, BMI, HbA1c, Fasting Glucose).

This repository contains the independently authored open-source research codebase, data preparation pipelines, feature extraction modules, cross-validation protocols, and synthetic test suites.

---

## 1. Project Purpose & Scope

The core scientific inquiry of GlucoTwin is evaluating whether concatenating static patient screening variables to short-term dynamic sensor features improves 30-minute forward glucose extrapolation in unseen individuals, or whether short-term sensor dynamics dominate the forecast horizon.

- **Current Stage**: Stage 6 local research app implemented and verified with Playwright Chromium. Historical experiments remain frozen.
- **Current Scope**: Retrospective research on released, processed continuous glucose monitoring data from the PhysioNet CGMacros v1.0.0 cohort.
- **Evaluation Design**: 14 Leave-One-Participant-Out (LOPO) outer test folds with nested 3-fold grouped inner cross-validation for hyperparameter selection across 39,496 paired 5-minute issue origins.

---

## Local research dashboard

Start the synthetic-only dashboard (after the setup in [Stage 6 instructions](docs/stage6/README.md)):

```powershell
.\.venv\Scripts\python.exe scripts/start_stage6.py
```

Open http://127.0.0.1:15173/. Add `--local` only for private processed-data replay.
Chromium verification passes at 1440px, 768px and 390px; six synthetic screenshots and actual results are in `reports/stage6/`. This is retrospective/synthetic research,
not a live sensor connection or clinical tool. No deployment is included.

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
- Python 3.12 (recommended) or compatible Python 3.10+
- Git

### 1. Clone the Repository
```powershell
git clone https://github.com/manishrahul1705/GlucoTwin.git
cd GlucoTwin
```

### 2. Create and Activate Virtual Environment
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-stage6.txt
```

### 3. Run Synthetic Verification Tests (No Data Required)
The unit suite uses synthetic fixtures and repository integrity checks. It does not require downloading external datasets. Install the Stage 6 dependencies above for the API tests:
```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```
The current full Python suite has **100 tests**; the Stage 6 frontend has **7 separate tests**. See the Stage 6 execution record for actual results and limitations; Chromium browser verification now passes.

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

## 5. Summary of Findings

*Detailed experimental analysis and roadmaps are documented in [PROJECT_STATUS.md](PROJECT_STATUS.md).*

1. **Short-Term Dynamics Outperform Baselines**:
   - Ridge regression on 21 sensor features achieved a primary equal-person MAE of **13.50 mg/dL**, outperforming simple persistence (15.15 mg/dL) by **+10.93% skill**.
   - Trailing linear extrapolation failed severely (**20.41 mg/dL MAE**, -34.71% skill vs persistence) due to noise amplification.
2. **Static Demographic Fusion Does Not Assist**:
   - Concatenating static baseline screening variables (Age, BMI, HbA1c, Fasting Glucose) to the sensor trajectory yielded a statistically negligible difference for Ridge (\(\Delta = +0.056\) mg/dL, 95% bootstrap CI `[-0.33, +0.39]`).
   - For Histogram Gradient Boosting, static fusion degraded performance by \(\Delta = +0.374\) mg/dL (9 of 14 participants worsened).
   - Short-term glucose dynamics (\(t-60\) to \(t\)) contain virtually all predictive signal for 30-minute forecasting; static screening values collected weeks or months earlier provide no actionable forward signal.

---

## 6. Strict Scientific, Medical & Regulatory Boundaries

These boundaries reflect technical constraints, not claims of regulatory clearance:

- **Retrospective Processed Signal Only**: The released PhysioNet CGMacros signals contain upstream sensor-level filtering, interpolation, and artifact correction. **Causal live equivalence is NOT ESTABLISHED**.
- **Sampling vs Packet Arrivals**: The computational 5-minute grid does not reconstruct native Bluetooth packet receipt times, transmitter clock drift, or transmission dropouts.
- **No Clinical Clearance or Device Exemption**: GlucoTwin is not an approved medical device, diagnostic tool, or clinical decision support system. It has not received FDA clearance, CE marking, CDSCO approval, or prospective clinical trial validation. Labeling software as "research only" does not confer legal exemption for clinical use.
- **No Treatment, Dosing, or Alert Guidance**: Under no circumstances should predictions be used for insulin titration, oral agent adjustments, carbohydrate intake, or acute clinical alerts.
- **No Population Generalization to Indian Cohorts**: Glycemic variability, pathophysiology, and dietary compositions in Indian or South Asian populations have not been validated.
- **Public Competition Permissions Unresolved**: Reconciling the PhysioNet ODC-BY / CC BY-NC-SA terms with the Figshare CC BY cross-deposit remains pending with maintainers. Raw data, participant feature tables, per-origin predictions, and model weights are strictly retained in ignored local storage.

---

## 7. Licensing & Attribution

- **Project Software**: Independently authored source code, test suites, and configurations are licensed under the [MIT License](LICENSE).
- **Data Licensing**: The code license does not relicense or grant rights to the underlying CGMacros dataset. The dataset remains subject to its governing PhysioNet licenses (ODC-BY 1.0 and CC BY-NC-SA 4.0).
- **Citation**:
  - Gutierrez-Osuna, Kerr, Mortazavi & Das, *Continuous Glucose Monitoring and Macronutrient Composition (CGMacros)*, PhysioNet v1.0.0 (2025), DOI: [10.13026/3z8q-x658](https://doi.org/10.13026/3z8q-x658).
  - Das et al., "CGMacros: A multimodal dataset of continuous glucose monitoring and dietary macronutrients in type 2 diabetes," *Scientific Data* 12:1557 (2025), DOI: [10.1038/s41597-025-05851-7](https://doi.org/10.1038/s41597-025-05851-7).
