# GlucoTwin — Submission Gaps, Scope Clarifications & Action Plan

**Document Version:** 1.1.0 (Corrected)  
**Audit Date:** 2026-10-18  
**Auditor:** Research-Integrity Reviewer & Submission-Evidence Engineer  
**Target Event:** Happiest Health — CRP Digital Twin Challenge 2026  
**Repository:** `https://github.com/manishrahul1705/GlucoTwin` (`HEAD: 5007db3`)  

---

## 1. Purpose & Scope

This document provides a rigorous, transparent analysis of the operational and technical gaps identified during our research-integrity audit for the **Happiest Health CRP Digital Twin Challenge 2026**.

Specifically, this document:
1. Reconciles the two core scientific scope divergences (Multimodal Fusion and Adverse Event Prediction Horizon) against actual code and experimental evidence.
2. Formulates unsent clarification inquiries for competition organizers and dataset maintainers.
3. Details the deliverable gaps (video demo, presentation deck, architecture diagram) and provides production blueprints for each.
4. Identifies the unassessed regulatory compliance and unresolved dataset-licensing boundaries.

---

## 2. Technical Reconciliation of Scope Divergences

### 2.1 Gap 1: Multimodal Fusion (Static EHR vs Trailing Sensor Dynamics)

#### Official Challenge Prompt
> *"The solution must integrate static electronic health record (EHR) data (such as demographics, laboratory biomarkers, and medical history) with dynamic time-series data from wearable health sensors to create an accurate patient digital twin."*

#### Repository Implementation
GlucoTwin implemented multimodal feature extraction in `src/glucotwin/features.py`:
- **Dynamic continuous features (21 total):** 13 discrete lags at 5-minute intervals ($t-60$ to $t$), 6 rolling window statistics (mean, std, min, max, IQR, median), and 2 trailing linear slopes (15m and 60m).
- **Static clinical screening features (4 total):** Age, Body Mass Index (BMI), Glycated Hemoglobin (HbA1c), and Fasting Blood Glucose.

#### Experimental Findings (Strictly Bounded to Evaluated Setup)
Across 14 adult T2D participants from the PhysioNet CGMacros cohort evaluated in Leave-One-Participant-Out (LOPO) cross-validation:
- **Ridge Regression (Stage 3, 39,496 origins):** Sensor-only MAE = **13.503 mg/dL** vs Combined MAE = **13.559 mg/dL** ($\Delta = +0.056$ mg/dL; 95% bootstrap CI `[-0.33, +0.39]`).
- **Histogram Gradient Boosting (Stage 3, 39,496 origins):** Sensor-only MAE = **13.969 mg/dL** vs Combined MAE = **14.343 mg/dL** ($\Delta = +0.374$ mg/dL; 9 of 14 participants degraded).
- **Within-Patient Adaptation (Stage 4, 31,552 later-period origins):** Adapted sensor-only MAE = **12.687 mg/dL** vs Adapted combined MAE = **12.769 mg/dL** ($\Delta = +0.082$ mg/dL; 9 of 14 participants degraded).

#### Scope Divergence & Status
These findings are strictly bounded to the evaluated 14 participants, the 4 baseline screening variables, the tested model architectures, and the 30-minute prediction horizon. They do not demonstrate universal lack of fusion benefit across other cohorts, clinical variables, or longer horizons.

Because the challenge requirement asks for a solution that combines static EHR and dynamic wearable data, our empirical finding that static fusion did not improve accuracy in this setup—and our resulting decision to freeze a sensor-only model in Stage 5/6—represents an **unresolved scope divergence**. A negative experimental finding does not automatically satisfy the challenge requirement. This divergence must be explicitly reviewed with the competition organizers.

---

### 2.2 Gap 2: Adverse Event Output vs Single-Point Continuous Forecasting

#### Official Challenge Prompt
> *"The algorithmic model should predict an adverse event (e.g. glucose spike 2 hours ahead) or physiological trajectory."*

#### Current Repository Implementation
- **Prediction Endpoint:** A continuous scalar glucose prediction at a single future horizon ($t+30$ minutes: `origin + 30m`), implemented in `src/glucotwin/stage3/training.py` and `src/glucotwin/stage6/prediction.py`.
- **Uncertainty Quantification:** Empirical conformal prediction intervals calibrated at 95% and 90% confidence ($\alpha=0.05, 0.10$), evaluated in `src/glucotwin/stage5/core.py`.
- **Slice Performance:** Evaluated retrospectively on ground-truth subsets: $>180$ mg/dL (MAE 22.2 mg/dL) and $<70$ mg/dL (sparse: 19 points in 2 participants).

#### Code & Test Reality
Inspection of the entire codebase and test suites confirms:
1. **Single-Point Endpoint, Not a Trajectory:** The model predicts a single scalar glucose value at $t+30$ minutes. It does not output a continuous trajectory of multiple future timepoints.
2. **No Adverse-Event Classifier:** The model does not output the probability of an excursion or adverse event occurring over a window.
3. **No Threshold Warnings or Alerts:** There is **no alert system, threshold-crossing logic, or notification engine** in the code or tests. Claims of "triggering warnings" or "actionable lead time" are unsupported and removed.
4. **No 2-Hour Horizon:** No model was trained or evaluated for a 120-minute horizon. The 30-minute target was defined in the historical protocol (`docs/stage2/target_definitions.md`).

#### Scope Divergence & Status
GlucoTwin's single-point continuous $t+30$ prediction is mathematically distinct from an evaluated adverse-event predictor or a 2-hour spike classifier. Whether continuous $30$-minute regression satisfies the competition criteria is **unresolved** and requires formal confirmation from organizers.

---

## 3. Unsent Draft Communications

The following communications are drafted for the user to review. No messages have been sent.

### Draft 1: Inquiry to Hackathon Organizers (Unstop / Happiest Health)

```text
Subject: Technical Scope Inquiry: CRP Digital Twin Challenge 2026 [Team Inquiry]

Dear Happiest Health CRP Digital Twin Challenge Organizing Committee,

We are preparing our submission for the CRP Digital Twin Challenge 2026 focusing on Type 2 Diabetes. We would appreciate clarification on two technical evaluation points:

1. Static EHR + Dynamic Wearable Fusion:
Our research evaluated multimodal fusion (combining Age, BMI, HbA1c, Fasting Glucose with 21 trailing CGM sensor features) against sensor-only dynamic models across 14 patient folds (39,496 origins) using Leave-One-Participant-Out cross-validation. In our specific experimental setup, static fusion yielded no demonstrated accuracy benefit for Ridge (+0.056 mg/dL MAE) and degraded gradient boosting (+0.374 mg/dL MAE), leading us to freeze a sensor-only model for primary deployment. 
Does the evaluation panel accept submissions where multimodal fusion was implemented and evaluated as an experimental negative result, with the primary deployed model using sensor-only dynamics?

2. Prediction Formulation & Horizon:
The prompt mentions "predicting an adverse event (e.g. glucose spike 2 hours ahead) or physiological trajectory". Our model outputs a continuous scalar glucose forecast at a single 30-minute forward horizon (t+30) with calibrated conformal uncertainty intervals, rather than a 2-hour binary excursion classifier or multi-point trajectory. Does a single-point continuous 30-minute regression forecast satisfy the adverse-event/trajectory criterion?

Thank you for your guidance.

Warm regards,
GlucoTwin Team
```

### Draft 2: Inquiry to CGMacros Dataset Maintainers (PhysioNet)

```text
Subject: Licensing Clarification for Academic Hackathon Entry: CGMacros v1.0.0

Dear Authors and Maintainers of CGMacros,

We are writing to request clarification regarding the terms governing derivative benchmark models based on the CGMacros dataset (PhysioNet v1.0.0, DOI: 10.13026/3z8q-x658).

The primary PhysioNet release specifies ODC-BY 1.0 and CC BY-NC-SA 4.0, while the Figshare cross-deposit indicates CC BY 4.0. We are participating in a student/academic hackathon (Happiest Health CRP Digital Twin Challenge 2026) where public GitHub repository submission is required.

To maintain strict compliance:
1. We do not distribute raw patient data, individual CGM traces, or patient-level feature tables in our public repository.
2. Our interactive dashboard operates by default on authored synthetic scenarios without requiring any PhysioNet data files.

Could you confirm whether publishing open-source reproduction code and trained benchmark regression weights derived from the cohort for non-commercial competition evaluation complies with the CC BY-NC-SA 4.0 terms?

Thank you for your time and guidance.

Sincerely,
GlucoTwin Research Contributors
```

---

## 4. Deliverables Gap Audit & Production Blueprints

### 4.1 Deliverable 1: Video Demonstration ($\ge$ 20 Minutes)
- **Current Status:** **MISSING**. No $\ge$ 20-minute video walkthrough exists in the repository.
- **Requirement:** Minimum 20-minute video explaining problem statement, model architecture, UI, and live code walk.
- **Production Blueprint (Corrected 20-Minute Outline):**

| Timestamp | Section | Content to Cover |
|-----------|---------|------------------|
| **00:00 – 03:30** | **Problem Statement & T2D Research Context** | Present Type 2 Diabetes glycemic variability challenges. Introduce GlucoTwin as a patient-adaptive research prototype. Disclose non-commercial status, lack of clinical clearance, and disambiguate from `glucotwin.com`. |
| **03:30 – 07:00** | **The Fusion Experiment & Bounded Results** | Introduce the PhysioNet CGMacros cohort (14 T2D participants). Detail the static vs dynamic feature sets. Present the empirical finding showing static variables did not improve 30m forecasts in this setup, explaining why the primary model is sensor-only. |
| **07:00 – 11:00** | **Modeling Formulation & Uncertainty Quantification** | Detail the 21 dynamic lag features, Ridge regression with training-only scaling, and the 24h within-patient median residual offset. Explain empirical conformal intervals ($\alpha=0.05, 0.10$). Explicitly state that predictions are single-point $t+30$ scalar values without threshold alerts. |
| **11:00 – 16:00** | **Interactive Dashboard & Scenario Lab** | Demonstrate the React dashboard on `http://127.0.0.1:15173/`. Walk through the deterministic virtual clock, authored scenarios (Postprandial Excursion, Overnight Euglycemia, Sensor Dropout), delayed ground-truth scoring, and synthetic CSV/JSON exports. |
| **16:00 – 19:00** | **Codebase Walkthrough & Quality Engineering** | Walk through `src/glucotwin/contracts.py`, `features.py`, `stage5/core.py`, and `stage6/api.py`. Present the static test inventory (117 Python contract tests, 22 frontend tests) and describe the virtual clock mechanics. |
| **19:00 – 20:30** | **Boundaries, Privacy & Conclusion** | Disclose data boundaries (zero patient data in git), state that DPDP/HIPAA compliance is unassessed, outline the submission status, and summarize conclusions. |

---

### 4.2 Deliverable 2: Architecture Diagram (PDF / PPT)
- **Current Status:** **MISSING**. Standalone PDF/PPT export does not exist in the repository.
- **Source:** Markdown and Mermaid diagrams in `docs/stage6/ARCHITECTURE.md`.
- **Action Required:** Team must render and export the architecture diagram into a clean, standalone PDF/PPT slide.

---

### 4.3 Deliverable 3: Presentation Slide Deck (PDF / PPT)
- **Current Status:** **MISSING**. Formatted presentation file does not exist.
- **Slide Deck Blueprint (10 Slides):**
  1. *Title & Attribution:* GlucoTwin — Patient-Adaptive Glucose Forecasting and Replay Research Prototype. Team and challenge details.
  2. *Clinical Context:* Type 2 Diabetes glycemic management and research motivation.
  3. *Cohort & Methodology:* PhysioNet CGMacros v1.0.0 (14 T2D participants), Leave-One-Participant-Out protocol (39,496 origins).
  4. *The Multimodal Fusion Experiment:* Controlled comparison of sensor-only vs combined models; documented negative result at 30 minutes.
  5. *Patient Adaptation Mechanics:* Within-patient 24h median residual offset; bias reduction and high-glucose error trade-off.
  6. *Uncertainty Quantification:* Conformal prediction interval formulation and empirical coverage metrics.
  7. *System Architecture:* FastAPI backend, deterministic virtual clock, React dashboard, SQLite session ledger.
  8. *Scenario Lab & Replay Engine:* Authored synthetic scenarios, dropout stress-testing, delayed evaluation scoring.
  9. *Engineering & Privacy Boundaries:* Static test inventory, zero-patient-data Git policy, unassessed regulatory status.
  10. *Project Boundaries & Roadmap:* Research-only limitations, prospective trial requirements, South Asian cohort needs.

---

### 4.4 Deliverable 4: Submission Archive Naming
- **Requirement:** Archive formatted as `Team Name_College Name.zip`.
- **Current Status:** **PENDING USER INPUT**. Awaiting team and college names to build the submission archive.

---
*Submission gap analysis updated on 2026-10-18.*
