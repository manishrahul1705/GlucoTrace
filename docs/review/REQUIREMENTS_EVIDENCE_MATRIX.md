# GlucoTwin — Official Hackathon Requirements & Evidence Reconciliation Matrix

**Document Version:** 1.1.0 (Corrected)  
**Audit Date:** 2026-10-18  
**Auditor:** Research-Integrity Reviewer & Submission-Evidence Engineer  
**Target Event:** Happiest Health — CRP Digital Twin Challenge 2026  
**Official Challenge URL:** `https://unstop.com/hackathons/crp-digital-twin-challenge-2026-happiest-health-1757873/amp`  
**Repository:** `https://github.com/manishrahul1705/GlucoTwin` (`HEAD: 5007db3`)  

---

## 1. Executive Summary & Review Scope

The **CRP Digital Twin Challenge 2026**, hosted by **Happiest Health** on Unstop, invites participants to build a Digital Twin Proof of Concept (PoC) targeting chronic diseases (specifically Type 2 Diabetes).

This matrix reconciles the official requirements against verified code, configs, and documented experiments in the GlucoTwin repository. Status definitions are strictly bounded:
- **SATISFIED**: Implemented and verified in the repository.
- **UNRESOLVED / SCOPE DIVERGENCE**: Diverges from challenge wording or requires formal organizer confirmation; negative experimental findings or single-point formulation do not automatically satisfy the requirement.
- **REGULATORY COMPLIANCE NOT ASSESSED**: Technical data-handling boundaries exist, but formal legal or statutory compliance (DPDP Act, HIPAA) has not been evaluated by legal counsel.
- **MISSING**: Submission deliverables required by the competition that do not exist in the repository.
- **PENDING USER INPUT**: Administrative details (team name, institution) awaiting maintainer entry.

---

## 2. Master Requirement-to-Evidence Matrix

| # | Official Challenge Requirement | Status | Concrete Repository Evidence | Scientific & Implementation Details | Next Action Required |
|---|--------------------------------|--------|------------------------------|-------------------------------------|----------------------|
| **1** | **Chronic Condition Domain (Type 2 Diabetes)** | **SATISFIED** | `docs/stage1/source_register.csv`<br>`docs/stage2/data_contract.md`<br>`configs/stage2_protocol.json` | Evaluates the de-identified PhysioNet CGMacros v1.0.0 cohort: 14 adult individuals diagnosed with Type 2 Diabetes undergoing 10–14 days of Dexcom G6 CGM monitoring. | None. Domain alignment verified. |
| **2** | **Static EHR + Dynamic Sensor Fusion** | **UNRESOLVED / SCOPE DIVERGENCE** | `src/glucotwin/features.py`<br>`src/glucotwin/stage3/training.py`<br>`reports/stage3_remediation/fusion_comparison.csv`<br>`reports/stage4/adaptation_comparison.csv` | Multimodal feature extractors implemented in `features.py` (21 sensor features + 4 baseline static features: Age, BMI, HbA1c, Fasting Glucose). In our specific experiments on this cohort, static fusion showed no demonstrated benefit for Ridge ($\Delta = +0.056$ mg/dL; 95% bootstrap CI `[-0.33, +0.39]`), degraded HistGB ($+0.374$ mg/dL), and degraded Stage 4 adapted MAE ($+0.082$ mg/dL). Primary Stage 5/6 model was frozen on sensor-only dynamics. A negative fusion result does NOT automatically satisfy the challenge requirement. | Organizer confirmation required on whether an empirical negative result and sensor-only primary model are acceptable. |
| **3** | **Algorithmic Adverse Event / Trajectory Model** | **UNRESOLVED / SCOPE DIVERGENCE** | `src/glucotwin/stage3/training.py`<br>`src/glucotwin/stage5/core.py`<br>`configs/stage5_protocol.json`<br>`docs/stage5/IMPLEMENTED_PROTOCOL.md` | Model outputs a continuous scalar glucose prediction at a single future point ($t+30$ minutes) with conformal uncertainty bounds ($\alpha=0.05, 0.10$). Slices evaluated retrospectively for $>180$ mg/dL (MAE 22.2 mg/dL) and $<70$ mg/dL (sparse: 19 points in 2 participants). The model does NOT output a multi-step trajectory, does NOT predict 2 hours ahead, does NOT compute event probabilities, does NOT detect threshold crossings, and implements NO threshold warning or alert mechanics. | Organizer confirmation required on whether single-point $t+30$ continuous regression satisfies the adverse-event requirement. |
| **4** | **Clinician Interaction Dashboard** | **SATISFIED** | `frontend/src/`<br>`src/glucotwin/stage6/api.py`<br>`src/glucotwin/stage6/engine.py`<br>`src/glucotwin/stage6/scenarios.py`<br>`docs/stage6/ARCHITECTURE.md` | React 18 / TypeScript frontend paired with FastAPI backend on loopback (`http://127.0.0.1:15173/`, `http://127.0.0.1:18060/`). Verified in prior audits across 1440px, 768px, 390px, and 360px viewports. Features Scenario Lab (9 authored scenarios), chronological replay, delayed scoring, session library, inspection modal, and 5 synthetic exports. | None. Local dashboard implemented and operational. |
| **5** | **Sandbox Rules & DPDP / HIPAA Compliance** | **REGULATORY COMPLIANCE NOT ASSESSED** | `.gitignore`<br>`src/glucotwin/stage6/scenarios.py`<br>`docs/stage1/leakage_audit.md` | Evaluates de-identified PhysioNet CGMacros data. Raw CSVs, participant feature tables, per-origin predictions, and model weights are excluded via `.gitignore`. Default application runs on authored synthetic scenarios. Technical data exclusion and de-identification DO NOT establish DPDP Act (2023) or HIPAA compliance. Formal regulatory compliance has NOT been assessed. | Disclose in submission that legal/statutory compliance is unassessed. |
| **6** | **Open-Source Repository & Permissive License** | **SATISFIED** (Pending manual push) | `LICENSE`<br>`https://github.com/manishrahul1705/GlucoTwin` | Codebase licensed under standard MIT License (`LICENSE`). All source code, configs, test suites, and documentation prepared for public repository review. | User to perform manual `git push`. |
| **7** | **Comprehensive Documentation & Attribution** | **SATISFIED** | `README.md`<br>`PROJECT_STATUS.md`<br>`docs/stage6/ARCHITECTURE.md` | Standardized subtitle applied (*"GlucoTwin — Patient-Adaptive Glucose Forecasting and Replay Research Prototype"*). Architecture summary, static test inventory, quickstart guide, team template, and clinical disclaimers documented. | Fill in team member names and institution in README template. |
| **8** | **Video Demonstration ($\ge$ 20 min)** | **MISSING** | `docs/review/SUBMISSION_GAPS_AND_CLARIFICATIONS.md` | Challenge mandates a narrated video of minimum 20 minutes. No 20-minute video currently exists in the repository. | Team must record, edit, and host a $\ge$ 20-minute video walkthrough prior to submission deadline. |
| **9** | **Architecture Diagram (PDF / PPT)** | **MISSING** | `docs/stage6/ARCHITECTURE.md` | Architectural text and Mermaid diagrams exist in markdown, but no standalone single-page PDF or PPT export exists in the repository. | Export architecture diagrams to a standalone PDF/PPT document. |
| **10** | **Presentation Slide Deck (PDF / PPT)** | **MISSING** | `docs/review/SUBMISSION_GAPS_AND_CLARIFICATIONS.md` | 10-slide presentation structure drafted, but finalized PDF/PPT slide deck has not been compiled. | Team must compile a 10–12 slide presentation deck in PDF/PPT format. |
| **11** | **Submission Folder Naming Format** | **PENDING USER INPUT** | N/A | Specified format: `Team Name_College Name.zip`. Awaiting official team and institution details. | Provide team and institution names to build archive structure. |
| **12** | **Dataset Licensing Clearance** | **UNRESOLVED / NOT CLEARED** | `docs/licensing_and_permissions_tracker.md`<br>`docs/stage1/licensing_and_permissions.md` | Official PhysioNet CGMacros v1.0.0 release is dual-licensed under ODC-BY 1.0 and CC BY-NC-SA 4.0; Figshare cross-deposit lists CC BY 4.0. Commercial/competition prize eligibility under CC BY-NC-SA 4.0 is unconfirmed. Redistribution permissions and legal clearance are NOT asserted. | Maintain unsent draft inquiry to maintainers; present codebase with synthetic mode. |

---

## 3. Analysis of Core Scope Divergences

### 3.1 Static EHR + Dynamic Sensor Fusion
- **Challenge Requirement:** Solution must combine static EHR data with dynamic wearable sensor data.
- **Repository Implementation:** Implemented in `src/glucotwin/features.py`: extracts 21 trailing sensor features (lags, rolling stats, slopes) and 4 baseline screening features (Age, BMI, HbA1c, Fasting Glucose).
- **Experimental Findings (Limited to Evaluated Setup):**
  - In Stage 3 (14 LOPO folds, 39,496 origins), adding static baseline variables to sensor dynamics yielded Ridge equal-person MAE of 13.559 mg/dL vs 13.503 mg/dL for sensor-only ($\Delta = +0.056$ mg/dL; 95% bootstrap CI `[-0.33, +0.39]`), which was statistically indistinguishable from zero.
  - For Histogram Gradient Boosting, static fusion degraded MAE by $+0.374$ mg/dL (14.343 vs 13.969 mg/dL; 9 of 14 participants worsened).
  - In Stage 4 (31,552 later-period origins), combining static features with 48h residual adaptation yielded 12.769 mg/dL vs 12.687 mg/dL for sensor-only adapted ($\Delta = +0.082$ mg/dL; 9 of 14 participants worsened).
- **Status & Boundaries:** These negative findings are strictly limited to the evaluated 14-participant CGMacros cohort, the tested model classes (Ridge, HistGB), the 4 static screening variables, and the 30-minute horizon. They do not prove universal sensor dominance. Because the challenge specifically requests static + dynamic fusion, presenting an empirical negative result and deploying a sensor-only model represents a divergence that requires organizer review.

### 3.2 Adverse Event Prediction vs Single-Point Continuous Forecasting
- **Challenge Requirement:** Algorithmic model predicting an adverse event (e.g. glucose spike 2 hours ahead) or physiological trajectory.
- **Repository Implementation:** Model outputs a single continuous prediction at $t+30$ minutes with empirical conformal uncertainty bands (`src/glucotwin/stage5/core.py`).
- **Code & Test Reality:**
  - **Single Point, Not Trajectory:** The model predicts a single scalar value at origin + 30 minutes, not a multi-step future curve.
  - **No Event Probability:** The model does not output the probability of an excursion event occurring over a window.
  - **No Threshold Warnings or Alerts:** There is no alert engine, notification pipeline, or threshold-crossing detector implemented in the codebase or test suite.
  - **No 2-Hour Horizon:** No model was trained or evaluated for a 120-minute horizon.
- **Status & Boundaries:** Continuous single-point regression at $t+30$ minutes is not an evaluated adverse-event predictor. Whether this formulation satisfies the competition criteria is unresolved and must be clarified with organizers.

---
*Matrix updated and verified against repository commit `5007db3` on 2026-10-18.*
