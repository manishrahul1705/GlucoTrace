# Local synthetic replay: setup and verification

The synthetic app runs without patient data, learned weights, calibration files or local audit reports. It uses authored seeded scenarios and persistence. Historical experiment aggregates and old local browser reports are separate evidence; local `reports/stage6`, `reports/feature_update`, `reports/completion` and audit screenshots are not guaranteed to exist in a source checkout. No current verification claim depends on those paths.

## Select the Python environment

Use Python 3.12. The existing `venv/Scripts/python.exe` passed verification with Python 3.12.10; the existing `.venv` in the audit environment was Python 3.11.9 and lacked NumPy. Environment directory names do not establish compatibility. Check the interpreter you intend to use:

```powershell
# Existing checkout: select an environment, then verify it.
$python = '.\venv\Scripts\python.exe'
& $python --version
& $python -c "import fastapi, uvicorn, numpy, pandas, sklearn; print('imports OK')"
& $python -m pip check
```

For a fresh checkout, create a new environment with `py -3.12 -m venv .venv`, select `$python = '.\.venv\Scripts\python.exe'`, and install `& $python -m pip install -r requirements-stage6.txt`. On POSIX use `python3.12 -m venv .venv` and `.venv/bin/python`. Do not overwrite an existing environment or upgrade dependencies just to run verification. Node v24.21.0 and npm 11.19.0 were used; dependencies and lockfile remain unchanged.

## Start

Install frontend dependencies from the lockfile with `npm.cmd ci --prefix frontend` (POSIX: `npm ci --prefix frontend`). Windows PowerShell may block `npm.ps1`; `npm.cmd` avoids changing execution policy.

```powershell
& $python scripts/start_stage6.py
# Explicit workaround only if the default Vite config loader hits sandbox access errors:
& $python scripts/start_stage6.py --config-loader runner
```

Default UI: http://127.0.0.1:15173/; API: http://127.0.0.1:18060/api/health. Use `--api-port` and `--web-port` for distinct free loopback ports. The launcher discovers Node on PATH; `GLUCOTWIN_NODE` may explicitly name another executable. It uses its current Python interpreter for the backend. Ctrl+C stops only owned children; occupied ports do not trigger termination of another service.

Synthetic-only is the default. `--local` enables private source discovery only when a trusted matching bundle is already available: minute observations, Ridge/scaler weights, Stage 5 calibration/partition/reproduction/hash files, split mapping and protocol freeze. See `src/glucotwin/stage6/sources.py:Registry._check/load` for exact filenames. Actual patient replay remains blocked in this checkout by absent artifacts. Do not deserialize untrusted joblib/pickle files, download data or generate substitutes merely to make this check pass. Patient exports remain forbidden.

## Current verification commands

Run Python from the repository root and frontend commands from `frontend/`:

```powershell
$env:PYTHONPATH = 'src'
& $python -m unittest discover -s tests -p 'test_*.py' -v
Set-Location frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
# Only when the documented default config loader fails with ancestor access denied:
npm.cmd exec -- vitest run --configLoader runner
npm.cmd exec -- vite build --configLoader runner
Set-Location ..
git diff --check
```

The Phase 3 candidate run recorded 144 backend tests and 30 frontend tests. Report default and alternate command results separately; no package scripts were changed to conceal sandbox access errors. A passing `pip check` alone does not establish that all required dependencies are installed. The fresh dependency installation recipe has been corrected for portability, but a fresh network installation was not part of this audit; existing environments/lockfile were used.

## Source and evidence package modes

`configs/source_package.json` is the explicit versioned input contract. Every `required_source_files` entry must exist. It includes the pending Phase 2/3 implementation/test files as intended source inputs rather than relying on a permanent list of untracked files in the verifier. Newly added source files must be added to this manifest. Git metadata is not needed to verify an exported source tree.

```powershell
# Use a new external path; existing reports are refused.
& $python scripts/verify_portable_package.py --mode source --output "$env:TEMP/glucotwin-source-integrity.json"
& $python scripts/verify_portable_package.py --mode source --root PATH_TO_CANDIDATE --output "$env:TEMP/glucotwin-candidate-integrity.json"
# Opt in only when the declared historical/local evidence is present:
& $python scripts/verify_portable_package.py --mode evidence --output "$env:TEMP/glucotwin-evidence-integrity.json"
```

Source mode selects no reports or private inputs. Evidence mode additionally requires every `required_evidence_files` entry (including the four historical local capability reports); missing required evidence is an integrity failure. Only explicitly named `optional_evidence_files` may be absent, and their absence is recorded; currently that list is empty. Neither mode verifies the claims inside historical evidence, dependencies, browser behavior, patient readiness or research reproduction. Both modes prehash/copy/check every selected path, size and SHA256, report actual copied counts and reject unsafe paths, duplicates and changed bytes. Output is written only after success, without overwriting previous evidence. Copies use isolated temporary destinations.

The Phase 3 audit verified an explicit **candidate snapshot**, not a committed clean clone. Its exact files, exclusions and hashes were recorded in local audit evidence, which is not required for source operation. The same source manifest supports source-checkout/export verification after committing the reviewed source changes. A local source checkpoint does not establish fresh dependency installation or patient replay.

## Current browser smoke check

Use a dedicated synthetic application instance, with a fresh database for verification, and a new external output directory:

```powershell
node scripts/verify_responsive_browser.mjs --url http://127.0.0.1:15173/ --output "$env:TEMP/glucotwin-responsive-new"
```

The script requires existing Playwright Chromium (`npm.cmd exec --prefix frontend -- playwright install chromium` installs it if needed outside this audit). It checks 360/390/720/1024/1440px at normal CSS zoom and the confirmed720px case separately at CSS zoom2, header/transport bounds, keyboard step, playback speed, start/pause/reset, console errors and failed API requests. CSS zoom is an approximation, separate from native browser UI zoom; native zoom is NOT RUN by this script. It creates a synthetic session on the specified service and never starts/stops that service. Do not target an existing private/user session during an audit.

Older `verify_stage6_browser.mjs` and `verify_capability_recovery_browser.mjs` runners are historical checks with historical selectors and repository output locations, not the current acceptance command. The previously documented `verify_feature_update_browser.mjs` is absent and must not be invoked. Existing local audit reports are optional historical evidence for source setup, not committed browser proof.

## Replay controls

Create a session after selecting source, clean/input-loss scenario and start mode.
Start/resume uses the selected 1x/60x/300x speed; pause freezes virtual time. Step
processes every intermediate minute until the next five-minute issue. Snapshot
polling never advances the clock. Reset creates a new generation and reprocesses
the configured full/warm start; old-generation responses are rejected. Keyboard
Tab/Enter operates native controls; controls have visible focus states.

Warm synthetic sessions process minutes 0-120 before opening. Warm local sessions
process the entire early history through the same engine, opening at the first
inherited issue whose history starts at/after hour48. A warm start is explicitly
labelled. Full chronology remains available. Local early processing may take time;
the UI shows Preparing and explains chronological processing; it does not substitute precomputed predictions.

The chart displays revealed readings only, gaps for missing cells and separate
forecast endpoints at origin+30. No smooth future trajectory is invented. An
optional whisker represents the selected nominal interval. Cards and the ledger
retain origin and target identities. Past forecasts are never reissued as fresh
output. Targets appear only after maturity. Nominal coverage, empirical coverage,
point error, issuance and scoring have separate fields/denominators.

## Scientific and permissions boundary

Persistent mode disclosures distinguish processed replay from independent
synthetic demonstration. Original source timestamps retain unknown timezone and
elapsed gaps; they are mapped onto a declared artificial UTC epoch. Measurement
and assumed arrival times are separate fields, with zero delay explicitly assumed.
This is not a live sensor connection. Chronological access tests cannot undo
upstream interpolation or certify actual availability.

The frozen Stage 5 design remains authoritative: 61 minute cells spanning 60
elapsed minutes, exact t+30 target, separate 24h median-offset and 24h interval
calibration phases, support-based purging, exact order statistics and inclusive
coverage. Models/offsets/quantiles remain fixed during evaluation. Both local
sensor-only variants are explicit comparisons; no preferred model is selected.

Stage 5 nominal 90% and 95% coverage was not fully achieved. The new 24h adaptation
worsened >180 mg/dL MAE by 0.558784 mg/dL and increased underprediction; the original
48h Stage 4 deterioration of 0.570931 mg/dL is preserved. Below70 observations are
sparse (19 origins in 2 participants). The cohort has already been examined;
evaluation remains exploratory. No clinical alarms, dosing, treatment, live-sensor
validation or guaranteed coverage claims are supported.

Licensing and submission questions remain unresolved in the existing permissions
tracker. Do not publish local data, weights, calibration, mappings, SQLite files,
patient-backed screenshots or detailed logs. Candidate code/aggregate records are
technically reviewable pending applicable permissions, not cleared for publication.
The historical audit performed no external messages or deployment; a local source checkpoint does not establish publication permissions.
