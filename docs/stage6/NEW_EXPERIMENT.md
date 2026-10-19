# Private NEW experiment route

This route is a new, locally frozen retrospective experiment. It does not restore
original results, certify native sensor timing, authorize competition use, or
perform clinical validation. No patient fitting/evaluation was executed during
implementation. Source and all historical commands/gates are preserved.

`run_new_experiment.py` defaults to read-only preflight. It requires the verified
acquisition layout, original design/input freezes, all54 hash-matching inputs,
archive hash, original metadata and unchanged scientific contracts. No downloader
is included. Use separate new external directories for amendment and execution.

```powershell
$repo = (Get-Location).Path
$private = 'D:/GlucoTwin-private' # Choose your own durable, private, non-shared directory.
$acq = "$private/verified-acquisition" # Existing verified acquisition layout, not a download destination.
$python = "$repo/venv/Scripts/python.exe"
& $python "$repo/scripts/run_new_experiment.py" --dry-run --acquisition-root $acq
# Choose NEW external paths; do not reuse an earlier amendment/output root.
$amend = "$private/implementation-v1"
$bundle = "$private/execution-v1"
& $python "$repo/scripts/run_new_experiment.py" --freeze-amendment --acquisition-root $acq --output-root $amend
$amendHash = (Get-FileHash "$amend/amendment.json" -Algorithm SHA256).Hash.ToLowerInvariant()
```

The amendment records current source bytes (including dirty state), runtime,
verified inputs, frozen selections and original design digest before evaluation.
It neither modifies nor backdates experiment-v1. Any implementation/runtime/input
change requires a new amendment. Synthetic fixture bundles are rejected by the
production verifier and server; tests invoke an explicitly labelled Python-only
fixture path. There is no CLI switch to make patient data a fixture.

Only when patient execution is separately authorized, supply a private JSON
attestation with `permits_processing_and_training: true`,
`private_noncommercial_only: true`, and truthful nonempty `basis`, `reviewed_by`,
`reviewed_at`. Do not reuse the acquisition-only scope record as training consent.

```powershell
# NOT run during implementation. This performs14 patient model fits.
& $python "$repo/scripts/run_new_experiment.py" --execute --acquisition-root $acq `
  --amendment "$amend/amendment.json" --amendment-sha256 $amendHash `
  --authorization "$private/reviewed-training-authorization.json" --output-root $bundle
```

Actual sequence: independently specified Stage1 audits derive window/crossing/
episode counts; unchanged `prepare_stage2.py` reconciles them; prepared cohort,
origin membership and grouped splits must equal the frozen split; exactly14
selected Ridge models/scalers fit on outer-training participants only. Those
pairs generate NEW held-out references and are reused for both Stage4 (48h) and
Stage5 (24h offset +24h calibration). No inner search, additional refit or historical
reference substitution occurs. Support purges, minima, alpha ranks, exact targets,
missingness and input-loss scenarios remain explicit. New hashes are labelled new.

Pre-verifier artifact hashes are written to `artifact-manifest.json`; the run
manifest records its digest BEFORE model loading by the verifier. Preserve that
digest as a trusted local execution record. A self-computed digest alone does not
authenticate an unknown bundle. Commands, failures and fit progress remain in the
external execution directory. Failed directories cannot be reused.

```powershell
$manifestHash = (Get-Content "$bundle/run-manifest.json" | ConvertFrom-Json).artifact_manifest_sha256
& $python "$repo/scripts/verify_new_experiment.py" --bundle $bundle --manifest-sha256 $manifestHash
# Separate future private replay; does not train. New runtime directory required.
& $python "$repo/scripts/serve_new_experiment.py" --bundle $bundle --manifest-sha256 $manifestHash `
  --runtime "$private/runtime-v1" --port 18060
# In another terminal:
& $python "$repo/scripts/check_new_replay.py" --url http://127.0.0.1:18060
$env:GLUCOTWIN_API_PORT='18060'; $env:GLUCOTWIN_WEB_PORT='15173'
Set-Location "$repo/frontend"
npm.cmd exec -- vite --host 127.0.0.1 --configLoader runner
```

Browser replay is a separate manual acceptance at http://127.0.0.1:15173: select a
local processed source, create a warm session, inspect both variants/levels,
start/pause/step and historical cutoff. Do not export patient outputs. The HTTP
command checks local source creation/snapshot only; it does not assert full
chronological replay or UI correctness. No frontend changes are needed. Existing
responsive browser automation is synthetic-only, not patient acceptance.

## Durable preservation and automated private acceptance

Preserve an existing verified execution without another fit. Retain its trusted
artifact-manifest digest from the execution record; calculating a digest from an
unknown bundle does not establish trust. Keep the original copy. The preservation
tool refuses an existing destination, rejects linked paths, compares every relative
file/directory path, file size and SHA256 before and after verification, and writes
migration metadata and a fresh verifier result alongside the copied `bundle`.
It does not rewrite the copied run manifest or earlier verification evidence.

```powershell
$trusted = 'REPLACE_WITH_PREVIOUSLY_RECORDED_ARTIFACT_MANIFEST_SHA256'
$preserved = "$private/preserved-checkpoint-v1" # Must not exist.
& $python "$repo/scripts/preserve_new_experiment.py" --source $bundle `
  --destination $preserved --manifest-sha256 $trusted `
  --context "$acq/experiment-v1/protocol.json" `
  --context "$acq/experiment-v1/protocol-freeze.json" `
  --context "$acq/experiment-v1/verified-input-freeze.json" `
  --context "$acq/verification-final.json" --context "$acq/records" `
  --context $amend --context "$private/reviewed-training-authorization.json"
& $python -B "$repo/scripts/run_patient_replay_acceptance.py" `
  --bundle "$preserved/bundle" --manifest-sha256 $trusted `
  --output "$preserved/acceptance-v1" --browser
```

Also preserve the applicable research-use review and acquisition scope record as
context, rather than inferring training permission from acquisition alone. Choose
a durable private destination outside Git, temporary/cache directories, cloud-sync
roots and public folders. The preservation tool cannot discover backup/sharing
policies. Detailed logs, patient source mappings, database and screenshots stay
in the private output directory and must not enter source/evidence packages.

The acceptance runner starts a dedicated loopback server, which independently
verifies the pinned bundle before serving it, and an isolated runtime/database.
It runs full chronological HTTP checks for every frozen participant: both
variants, offset/calibration boundaries, per-level readiness, selected point and
bound agreement with frozen evaluation rows, exact delayed target maturity,
historical cutoff isolation and rejection of all five patient export types.
Unavailable states are recorded as observed. Expected availability comes from
the frozen artifacts, never an assumption that each point/interval is available.

All four protocol-supported simulated input-loss durations are exercised over
HTTP on one representative participant. These are simulated losses applied to
processed patient replay, not genuine transport-loss observations. Predictions
and bounds are checked against the existing frozen scenario rows. Calibration-
period loss and target loss remain unsupported/deferred; no production API is
added. Recovery can remain unavailable if original data also lacks support.

Chromium selects and creates every local source and renders both variant readiness
panels and interval controls. Deep phase-transition, historical-slider and one
input-loss/recovery case are representative, not exhaustive browser coverage.
Per-participant/per-case JSON and screenshots record their actual scope. Failures
are retained in the fresh output and the runner exits nonzero; reruns require a
new output directory. The runner never fits a model or recomputes calibration.
`--browser-only` runs a fresh browser rerun with `http_scope` explicitly marked
`NOT_RUN_BROWSER_ONLY`; it cannot replace or clear an earlier HTTP/loss failure.

Earlier strict loss checks exposed a replay metadata defect: injected absent
readings were reconstructed as present non-finite readings, appending
`NON_FINITE_READING` to `MISSING_CURRENT_READING`. Earlier failed evidence remains
immutable. Replay revision `row-presence-v1` carries `Reading.row_present` from
local ingestion (including original row-presence flags and simulated loss), through
history/duplicate identity and normalization, into the prediction frame. A present
non-finite reading still reports `NON_FINITE_READING`. No reason string is rewritten;
the existing Stage 5 core computes reasons using the preserved metadata.

The acceptance runner writes a separate `replay-implementation.json` before
starting replay, containing source hashes and links to the existing artifact
manifest and generation amendment. Its digest is recorded in the acceptance
report; source hashes are checked again after acceptance. This revision does not
replace or modify the generation amendment or bundle. Regression tests cover absent,
present non-finite and present finite inputs, exact reasons/bounds, local ingestion,
history gaps, availability, duplicate identity and recovery. No model refit or new
calibration artifact is needed for this replay-only correction.

Updating source, documentation or the package manifest does not amend an existing
bundle. Future patient generation with changed source requires a new versioned
implementation amendment; existing frozen bundles remain independently verifiable.

The independent verifier checks byte completeness before deserialization,
raw/prepared observations, scalar feature math, training-only moments, closed-form
Ridge solution (no fit), held-out predictions, chronological purges, scalar median
offsets and integer/rational quantile ranks, missingness, exact-target maturity and
interval arithmetic. Bundle PASS remains `BUNDLE_VERIFIED_REPLAY_NOT_RUN`.
