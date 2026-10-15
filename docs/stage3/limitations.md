# GlucoTwin Stage 3 — Scientific, Medical, and Licensing Limitations

## 1. Causal and Data Signal Limitations

1. **Retrospective Processed Signal Only**: The experiment evaluates the published CGMacros PhysioNet 1.0.0 dataset. The released CGM streams contain upstream interpolation, sensor-level filtering, and artifact corrections applied prior to release. Causal live equivalence is **NOT ESTABLISHED**.
2. **Upstream Two-Sided Leakage**: Because the released grid contains potential forward-backward interpolation applied by upstream providers, trailing history windows may mathematically encode information originating from future points across missing gaps. Our pure trailing feature extractor cannot purge pre-existing upstream bidirectional filter support.
3. **Synthetic Grid Sampling vs Native Sensor Packets**: Primary evaluation operates on a 5-minute sampling grid aligned to the first parsed timestamp. This computational sampling grid does not reconstruct raw Dexcom Bluetooth packet receipt times, transmitter clock drift, or native sample arrivals.
4. **Baseline Measurement Availability Assumption**: The baseline variables (Age, BMI, HbA1c, Fasting Glucose) are assumed to have been available prior to CGM recording. However, the exact chronological reporting timestamps of these screening lab draws are not recorded in the source files.

---

## 2. Statistical and Methodological Boundaries

1. **Cohort Size (\(n=14\))**: Evaluation is restricted to the 14 eligible Type 2 Diabetes participants from CGMacros. While 39,496 paired 5-minute origin windows were evaluated, contiguous windows from the same individual are highly correlated time series. The effective degrees of freedom are governed by \(n=14\) individuals, not 39,496 observations.
2. **Exploratory Bootstrap Intervals**: The paired participant bootstrap (2,000 resamples) appropriately treats the individual participant as the unit of resampling. However, given \(n=14\), these confidence intervals are exploratory, wide, and cannot establish population-level clinical equivalence or superiority.
3. **No Direct "Personalization" Established**: Concatenating four static screening variables into a global linear or tree model constitutes static demographic fusion, not dynamic patient personalization. In fact, empirical results demonstrate that static fusion provided no statistically reliable benefit.
4. **No Calibration or Adaptive Tuning**: These experiments evaluate global models on unseen patients under strict LOPO. No patient-specific recalibration, residual adaptation, or prediction intervals were trained.

---

## 3. Strict Medical and Clinical Boundaries

1. **No Clinical Clearance or Efficacy**: GlucoTwin is a retrospective research study, not a medical device, diagnostic tool, or clinical decision support system. It has not received FDA clearance, CE mark, CDSCO approval, or prospective clinical trial validation.
2. **No Treatment or Medication Recommendations**: Under no circumstances should predictions from this model be used to guide insulin titration, oral hypoglycemic medication dosing, meal timing, or acute clinical management.
3. **No Autonomous Alerts or Adverse Event Prevention**: Regression error (e.g. MAE 13.5 mg/dL) does not measure or guarantee clinical alert reliability, sensitivity to severe hypoglycemia (<54 mg/dL), or prevention of diabetic ketoacidosis / hyperosmolar hyperglycemic states.
4. **Population Specificity**: The model has not been validated on an Indian or South Asian cohort. Diabetes pathophysiology, glycemic variability, and dietary macronutrient compositions in other populations differ substantially from the study cohort.
5. **No Medical Device Exemption**: Stating "research use only" does not confer exemption from medical device regulations if software is deployed in clinical workflows.

---

## 4. Licensing and Distribution Status

1. **Public Competition Use**: **UNRESOLVED**. A discrepancy exists between the PhysioNet ODC-BY / NC-SA licensing constraints and the Figshare release terms. Distribution of derived artifacts, per-origin predictions, or competition entries requires formal relicensing authorization.
2. **Commercial Reuse**: Not cleared under the audited non-commercial PhysioNet grant.
3. **Data Protection Boundary**: Raw participant files, individual feature matrices, per-origin predictions, and model weight binaries must remain in local ignored storage (`data/`) and must NOT be committed to public version control or packaged in public review archives.
