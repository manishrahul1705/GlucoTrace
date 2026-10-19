# Dataset Licensing & Competition Permissions Tracker

**Dataset**: CGMacros (PhysioNet v1.0.0, DOI: 10.13026/3z8q-x658)  
**Authors**: Gutierrez-Osuna, Kerr, Mortazavi, Das  
**Published Paper**: Das et al., Scientific Data 12:1557 (2025), DOI: 10.1038/s41597-025-05851-7  
**Status**: RESTRICTED LOCAL RESEARCH ONLY — PUBLIC COMPETITION USE UNRESOLVED  

---

## 1. Conflicting License Labels

| Repository / Location | Declared License | Terms & Restrictions |
|---|---|---|
| **PhysioNet Deposit** | ODC-BY 1.0 & CC BY-NC-SA 4.0 | Non-commercial use only; share-alike required for adaptations. |
| **Figshare Cross-Deposit** | CC BY 4.0 | Attribution only; commercial reuse permitted. |

Because the primary PhysioNet release specifies **CC BY-NC-SA 4.0** (Non-Commercial, Share-Alike), GlucoTwin operates strictly under non-commercial research boundaries until this discrepancy is formally reconciled.

---

## 2. Unsent Clarification Questions for Dataset Maintainers

*(Draft questions for maintainer inquiry; NO MESSAGES SENT)*

1. **License Harmonization**: "The PhysioNet repository for CGMacros lists ODC-BY 1.0 and CC BY-NC-SA 4.0, while the Figshare record cites CC BY 4.0. Could you clarify which license governs derivative predictive models and aggregated research benchmarks?"
2. **Competition Use**: "Does entry into an open-source technical competition involving monetary prizes or public leaderboard evaluations constitute commercial use under the CC BY-NC-SA 4.0 terms?"
3. **Model Artifact Distribution**: "Are trained model weight binaries (e.g. scikit-learn Ridge estimators fitted on CGMacros sensor matrices) permitted to be hosted publicly on GitHub without violating the data use agreement?"

---

## 3. Unsent Questions for Competition Organizers

*(Draft questions for organizers; NO MESSAGES SENT)*

1. **Third-Party Data Verification**: "Given that GlucoTwin benchmarks retrospective performance on an external open-access cohort (CGMacros) under non-commercial academic research terms, does the competition platform permit submissions where raw training data remains local and only reproduction scripts and aggregated metrics are published?"
2. **Intellectual Property & Licensing**: "If a prize or award requires granting commercial rights or Apache-2.0 / MIT licensing to contest organizers, how should non-commercial source datasets (CC BY-NC-SA) be accommodated?"

---

Additional scope questions (unsent):

- Does evaluated baseline-plus-sensor fusion with no demonstrated improvement satisfy the requested fusion scope when sensor-only remains the default?
- Does an exact +30-minute endpoint decision satisfy the requested adverse-event/trajectory scope? It is not an episode/onset or two-hour predictor.

## 4. Current Compliance Boundary

- **Local Data Boundary**: All raw CSV files, prepared feature matrices, per-origin predictions, individual patient offsets, and trained model binaries remain strictly in local `.gitignore` storage.
- **Repository Contents**: Only source code, synthetic unit test fixtures, experiment configurations, cryptographic manifests, and safe cohort-level aggregate reports are tracked.
- **Status Verdict**: UNRESOLVED. No external contact made. No commercial or live clinical claims made.
