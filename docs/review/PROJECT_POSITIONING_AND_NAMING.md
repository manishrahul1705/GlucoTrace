# GlucoTwin — Project Positioning, Naming & Attribution Reconciliation

**Document Version:** 1.1.0 (Corrected)  
**Audit Date:** 2026-10-18  
**Auditor:** Research-Integrity Reviewer & Submission-Evidence Engineer  
**Target Event:** Happiest Health — CRP Digital Twin Challenge 2026  
**Repository:** `https://github.com/manishrahul1705/GlucoTwin` (`HEAD: 5007db3`)  

---

## 1. Context & Purpose

This document analyzes existing public uses of the name "GlucoTwin" and establishes an authoritative positioning and attribution strategy for GlucoTwin in the context of the **Happiest Health CRP Digital Twin Challenge 2026**.

**Search Limitations:** The prior art review documented herein reflects a preliminary search of public web domains, IEEE Xplore, and public GitHub repositories conducted on 2026-10-18. It is **not** an exhaustive legal trademark search, comprehensive patent audit, or corporate registry clearance. Formal trademark availability and legal clearance remain **unassessed**.

---

## 2. Identified Prior Art & Name Collisions

A preliminary query identified the following external uses of the "GlucoTwin" name:

### 2.1 Commercial Web Domain (`glucotwin.com`)
- **Observed Scope:** Public website advertising an AI-driven metabolic health platform with continuous glucose monitoring integration, Health Connect synchronization, and lifestyle guidance.
- **Corporate & Trademark Status:** The exact corporate incorporation details, registration dates, trademark registrations, and operating status were not independently verified from primary registry filings. They remain unresolved.
- **Distinction from this repository:** Our repository is an open-source, non-commercial research benchmark focused on retrospective statistical and machine learning evaluation of processed clinical sensor signals. There is zero shared infrastructure, code, ownership, or affiliation.

### 2.2 Academic Publication: Sayed et al. (EHB 2023)
- **Primary Source:** Sayed, S., et al., "GlucoTwin: A Digital Twin for Gestational Diabetes Mellitus," *2023 International Conference on E-Health and Bioengineering (EHB)*, Grigore T. Popa University of Medicine and Pharmacy, Iasi, Romania, 2023.
- **Scope:** Conceptual framework and mobile telemonitoring architecture specifically targeting gestational diabetes mellitus (GDM) during pregnancy.
- **Distinction from this repository:** Sayed et al. conceptualized a digital twin for gestational diabetes. This repository investigates retrospective 30-minute ahead glucose forecasting in non-pregnant adults with Type 2 Diabetes from the PhysioNet CGMacros cohort. There is no author overlap or collaborative connection.

### 2.3 Public GitHub Codebases
- **`bauber/glucotwin` (Victor Bautista):** A public personal Android glucose logger written in Kotlin with a FastAPI backend.
- **`Namrata-Gangwar/Gluco-twin`:** A personal machine learning exploratory repository.
- **Distinction from this repository:** These repositories do not implement the 14-fold Leave-One-Participant-Out cross-validation protocol, within-patient 24h/48h residual adaptation, conformal prediction intervals, or deterministic virtual replay engine present in this codebase.

---

## 3. Positioning & Disambiguation Policy

To avoid confusion while preserving repository commit history and existing links, the following policies are established:

### 3.1 Retain Repository Name (`GlucoTwin`)
The GitHub repository name remains `GlucoTwin` at `https://github.com/manishrahul1705/GlucoTwin`. Changing the repository slug would break existing Git commit parentage, remote configurations, published citations, and reviewer bookmarks.

### 3.2 Mandate Standardized Subtitle
All project documentation, user interface headers, academic summaries, presentation slides, and submission entries must display the descriptive subtitle:

> **GlucoTwin — Patient-Adaptive Glucose Forecasting and Replay Research Prototype**

This subtitle explicitly qualifies the scope:
1. **Patient-Adaptive:** Refers strictly to the 24h/48h within-patient scalar median residual offset evaluated in Stages 4 and 5.
2. **Glucose Forecasting:** Identifies the single-point statistical regression task ($t+30$ minutes).
3. **Replay:** Clarifies that the interactive UI operates on retrospective chronological replay and synthetic generation, not live hardware telemetry.
4. **Research Prototype:** Emphasizes non-commercial research status and the complete absence of clinical clearance.

### 3.3 Author & Challenge Attribution
All public submission materials must include clear authorship and competition details:
- **Authors:** Manish Rahul and Project Collaborators.
- **Submission:** Prepared for the *Happiest Health CRP Digital Twin Challenge 2026* (Hosted on Unstop).
- **Date / Version:** October 2026 / Version 1.1.0.

### 3.4 Explicit Non-Affiliation & Trademark Notice
The following notice is placed in the project `README.md` and submission materials:

> **Attribution & Non-Affiliation Notice:**  
> *GlucoTwin is an independent open-source research prototype developed by Manish Rahul and collaborators for the Happiest Health CRP Digital Twin Challenge 2026. This project is not affiliated with, sponsored by, or endorsed by glucotwin.com, commercial metabolic health platforms, or unrelated academic research publications sharing the name. Legal trademark availability has not been assessed.*

---

## 4. Digital Twin Architectural Classification

To prevent inflated claims, GlucoTwin's architecture is classified against common digital twin definitions:

| Dimension | What GlucoTwin IS | What GlucoTwin IS NOT |
|-----------|-------------------|-----------------------|
| **Modeling Paradigm** | **Data-Driven Statistical Regressor:** Learns linear and gradient boosted relationships from 21 trailing sensor features and historical calibration residuals. | **Not a Mechanistic / Physiological Simulator:** Does not model insulin pharmacokinetics, gastrointestinal carbohydrate absorption, or physiological differential equations (e.g. UVA/Padova). |
| **Adaptation Mechanism** | **Scalar Residual Offset:** Calculates a fixed participant-specific median residual offset over an initial 24–48 hour calibration period to adjust later point predictions. | **Not an Online Model Updater:** Does not update internal regressor weights or optimize neural parameters on streaming data. |
| **Prediction Endpoint** | **Single-Point Horizon ($t+30$):** Predicts continuous glucose concentration (mg/dL) at a single elapsed time 30 minutes ahead of origin. | **Not a Multi-Step Trajectory or Hazard Classifier:** Does not output a multi-step trajectory, does not compute event probabilities, and does not evaluate adverse event risk over windows. |
| **Uncertainty Quantification** | **Conformal Empirical Intervals:** Computes empirical quantile bounds from calibration residuals at specified significance levels ($\alpha=0.05, 0.10$). | **Not a Bayesian Posterior / Confidence Guarantee:** Evaluated empirical coverage does not guarantee distribution-free coverage under non-exchangeable time-series shifts. |
| **Operational Interface** | **Virtual Chronological Replay:** Deterministic minute-by-minute virtual clock advancing synthetic or retrospective sensor data in loopback. | **Not a Live Hardware Daemon or Clinical Alert Tool:** Does not connect to Bluetooth CGM sensors and contains **no threshold warning or emergency alert implementation**. |

---
*Positioning and naming audit updated on 2026-10-18.*
