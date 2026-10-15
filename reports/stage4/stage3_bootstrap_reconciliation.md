# Stage 3 Paired Participant Bootstrap Reconciliation

## 1. Executive Summary & Root Cause

During Stage 3 remediation, the reported 95% bootstrap confidence interval for Histogram Gradient Boosting (HistGB) paired MAE delta (\(\Delta = \text{Combined} - \text{Sensor}\)) shifted from:
- **Original Stage 3 Run**: `[-0.0034, +0.7820] mg/dL`
- **Remediation Stage 3 Run**: `[-0.0244, +0.7831] mg/dL`

By contrast, the Ridge regression bootstrap interval was identical between both runs:
- **Original Stage 3 Run**: `[-0.3327, +0.3881] mg/dL`
- **Remediation Stage 3 Run**: `[-0.3327, +0.3882] mg/dL`

### Root Cause
The root cause was **RNG sequential state advancement across model families** in the original monolithic runner vs **per-function re-seeding** in the modularized remediation library:

1. **Original Runner (`archive/stage3_original/scripts/run_stage3.py`, lines 409–447)**:
   A single `rng = np.random.default_rng(20261015)` was instantiated before the `for fam in ['ridge', 'hist_gradient_boosting']` loop.
   - Iteration 1 (`ridge`): Consumed draws **1 through 2,000** from the generator.
   - Iteration 2 (`hist_gradient_boosting`): Consumed the **next 2,000 draws (draws 2,001 through 4,000)** from the advancing generator.

2. **Remediation Function (`src/glucotwin/stage3/metrics.py`, line 144)**:
   `compute_paired_participant_bootstrap` was extracted as a self-contained pure function taking `(per_person_df, family, seed, n_resamples)`. Inside the function, `rng = np.random.default_rng(seed)` was called on each invocation.
   - `ridge` execution: Consumed draws **1 through 2,000** from seed 20261015.
   - `hist_gradient_boosting` execution: Consumed draws **1 through 2,000** from seed 20261015.

Because Ridge was the first evaluated family in both implementations, its bootstrap draw indices were identical, yielding identical confidence intervals. HistGB was evaluated on draws 2,001–4,000 in the original run and draws 1–2,000 in the remediation run.

---

## 2. Quantitative Decomposition of Effects

To establish that no other hidden implementation differences exist, both implementations were reproduced and evaluated under controlled ablation conditions:

| Condition | Description | HistGB MAE 95% CI (mg/dL) | Lower Bound Delta | Upper Bound Delta |
| :--- | :--- | :---: | :---: | :---: |
| **A. Original Run** | Rounded inputs (4 decimals), Draws 2,001–4,000 | `[-0.0034, +0.7820]` | *Reference* | *Reference* |
| **B. Precision Ablation** | Unrounded float64 inputs, Draws 2,001–4,000 | `[-0.0034, +0.7820]` | `+0.000014` | `+0.000016` |
| **C. Draw-Order Ablation** | Rounded inputs (4 decimals), Draws 1–2,000 | `[-0.0244, +0.7831]` | `-0.020991` | `+0.001118` |
| **D. Remediation Run** | Unrounded float64 inputs, Draws 1–2,000 | `[-0.0244, +0.7831]` | `-0.020970` | `+0.001130` |

### Quantification Summary
1. **Precision-Only Effect**: Retaining full IEEE 754 `float64` precision (avoiding intermediate 4-decimal truncation of per-participant MAEs) accounts for only **\(\sim 0.000015\) mg/dL** of variation.
2. **RNG / Draw-Index Effect**: Advancing the RNG state from draws 1–2,000 to draws 2,001–4,000 accounts for **\(0.0210\) mg/dL** on the 2.5th percentile and **\(0.0011\) mg/dL** on the 97.5th percentile.
3. **Other Factors**:
   - Participant ordering: Identical (`[3, 5, 12, 14, 28, 30, 35, 36, 38, 39, 42, 46, 47, 49]`).
   - Resamples: Identical (2,000 draws).
   - Quantile method: Identical (`numpy.percentile` with default linear interpolation).
   - Point estimates: Identical (\(\text{mean paired } \Delta = +0.3744\) mg/dL).

---

## 3. Scientific Impact & Substantive Conclusion

Neither interval is selected for aesthetic favorability. Both intervals support the exact same scientific finding:
- **Original Interval**: `[-0.0034, +0.7820] mg/dL`
- **Remediation Interval**: `[-0.0244, +0.7831] mg/dL`

In both cases:
1. The mean paired difference is positive (**\(+0.3744\) mg/dL**, indicating baseline fusion worsened error).
2. Exactly **9 out of 14 participants** suffered worse forecasting performance when baseline features were added.
3. The 95% confidence interval cleanly spans zero or leans positive, ruling out any statistically reliable benefit from baseline fusion for HistGB.

---

## 4. Documented Amendment for Stage 4 Protocol

To permanently eliminate RNG sequential-coupling across models:
1. **Explicit Draw-Index Matrix**: In Stage 4 (`src/glucotwin/stage4/evaluation.py`), generate a single 2D array of draw indices `draw_indices = rng.choice(n_participants, size=(n_resamples, n_participants), replace=True)` once from seed `20261015`.
2. **Paired Matrix Reuse**: The exact same draw-index matrix is reused across all method evaluations (Persistence, Ridge unadapted, Ridge adapted, etc.), ensuring true paired bootstrap comparisons across all models.
3. **Matrix Provenance**: The SHA-256 hash of the draw-index matrix is recorded in `bootstrap_summary.json` for independent verification.
