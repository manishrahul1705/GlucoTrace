# Targeted retrospective bundle regeneration

`scripts/regenerate_replay.py` orchestrates the existing frozen scripts. It does
not download data, reselect models, call the 728-fit Stage 3 benchmark, or turn
new predictions into their own historical reference. Its default is preflight.
The resulting bundle is a **new execution**, never the original restored bundle.

```powershell
# No copy of patient data, freeze, model load or fit. Exit 2 means blocked inputs.
.\venv\Scripts\python.exe scripts/regenerate_replay.py --dry-run `
  --input-root C:\path\to\authorized-input-project `
  --output-root "$env:TEMP/glucotwin-new-preflight"
```

Use a new external output directory. Existing output directories are refused.
Preflight writes only `preflight.json` when an output directory is specified;
otherwise it prints the plan. Full missing/incompatible paths are listed there.
Patient-level input records are never printed. A ready preflight establishes
technical input consistency, not permission to execute.

Execution requires an explicit reviewed intended-use/provenance attestation:

```json
{
  "permits_processing_and_training": true,
  "intended_use": "Describe the actual scope, including competition/commercial use",
  "basis": "Identify the applicable grant or reviewed permission document",
  "reviewed_by": "Responsible reviewer",
  "reviewed_at": "Actual review timestamp"
}
```

This is an attestation and audit trail, not automated legal clearance. The
project's currently documented noncommercial grant does not establish the
intended commercial authorization. Do not use a synthetic test attestation for
patient execution. Competition participation alone does not determine whether
a use is commercial or prohibited. Assess the actual purpose, requested rights
and applicable terms; obtain additional permission where that scope requires it,
or explicitly restrict this execution to an authorized noncommercial scope. Public accessibility alone is not a grant
for every intended use. No dataset acquisition is implemented by this runner.

Only after those issues and all preflight prerequisites are resolved:

```powershell
# NOT executed during runner development; performs patient training when ready.
.\venv\Scripts\python.exe scripts/regenerate_replay.py --execute `
  --input-root C:\path\to\authorized-input-project `
  --output-root C:\private\new-versioned-regeneration `
  --authorization C:\private\reviewed-permission.json
```

The output root must be separate from both source and inputs. All outputs are
under its `project/` directory; original inputs and historical reports are never
overwritten. The current Python interpreter runs the copied scripts. Run identity,
source commit/dirty state (when Git is available), runtime versions, input/source
hashes, commands, logs and generated-file hashes are recorded externally. New
execution metadata and the new protocol freeze are written before evaluation;
no original timestamp is fabricated. On failure the isolated directory is kept
with a failed manifest, and cannot silently be reused.

## Exact dependency chain

The runner reuses Stage 2 only when both frozen feature tables, the original
split and coverage report, and all selected observation/personalization files
are present and match the historical Stage 2 byte hashes. Raw data and Stage 1
comparison tables remain visible in the upstream trace but are not consumed
again when already-verified Stage 2 intermediates can be reused.

Otherwise it requires:

- `configs/stage2_protocol.json`, the original Stage 1 provenance JSON at its
  configured path, and every extracted/downloaded file named there with matching
  recorded hashes. The runner never fetches them.
- **Both** `docs/stage1/usable_windows.csv` and
  `docs/stage1/event_feasibility.csv`, with their historical hashes from
  `reports/stage2/stage1_preservation_manifest.json`. The original preparation
  script retains its window-count, crossing-count and episode-count checks.
  Missing tables must be restored, not invented; missing historical generators
  are not an excuse to skip their validation.
- The original `reports/stage2/freeze_manifest.json` expected observation,
  personalization, feature, split and coverage hashes. Newly generated Stage 2
  outputs must match these original expectations before training starts.

The following references remain mandatory regardless of Stage 2 reuse:

- Frozen Stage 2–5 configurations, original split and all Stage 4 input-hash
  anchors, including `docs/stage2/personalization_protocol.md`.
- `reports/stage3_remediation/selected_candidates.csv`: exactly one sensor-only
  Ridge candidate per each of the 14 original outer folds. All outer/inner
  training exclusions are validated. Other model selections are not refitted.
- `data/processed/stage3_remediation/predictions/test_predictions.csv`, matching
  its original Stage 4 hash. Fitting a new model does not recreate a missing
  independent historical reference or satisfy this gate by itself.
- Stage 4 `data/processed/stage4/predictions/{later_evaluation_predictions.csv,
  calibration_predictions.csv}`, `data/processed/stage4/patient_offsets.csv`, and
  `reports/stage4/aggregate_metrics.csv`. The latter additional files are required
  by the existing full Stage 5 verifier, not merely by the generator.

The only executable steps are optional `prepare_stage2.py`, then `run_stage5.py`
and `verify_stage5.py`. These scripts retain their existing checks. Stage 5 uses
14 frozen selected sensor-only Ridge refits, 24-hour offset fitting, the next
24 hours for calibration, original purges, count gates and nominal levels.
It does not substitute Stage 4's 48-hour adaptation design.

The original hard-coded paths are isolated by copying the source snapshot and
required inputs to the fresh output `project/`; existing scripts derive their
root from their copied location. No research-script root or protocol rewrite is
necessary. Source/input copy hashes are checked; newly generated model files are
pinned before the existing verifier reads those freshly generated files. No
pre-existing pickle/joblib input is required or deserialized by the runner.

A successful verifier yields `BUNDLE_VERIFIED_REPLAY_NOT_RUN`, **not** verified
patient replay. Subsequent real HTTP and Chromium checks must use
`create_app(root=<output>/project, runtime=<new external runtime>, local_enabled=True)`
and must preserve patient-export restrictions. Missing original Stage 5 results
still prevent a claim of complete original-experiment reproduction, even when
the new bundle is internally consistent and agrees with older Stage 3/4 evidence.

Synthetic orchestration tests inject an executor that writes explicitly labelled
placeholder files and never fits/deserializes a model. They prove ordering and
failure behavior only; they are not patient execution, scientific validation,
clinical validation or permission evidence.
