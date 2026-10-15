# Local research replay

Stage 6 implements a FastAPI backend, deterministic minute-event engine and a
React/TypeScript dashboard. Local Chromium browser verification now passes at
1440px, 768px and 390px. Playwright checked controls, delayed scoring, all input-loss
durations, disclosure persistence, clipping/overflow and console/API failures.
Two observed defects were fixed: the scrolling disclosure and a session-transition
poll/delete race. Actual evidence and six independent synthetic screenshots are in
`reports/stage6/browser_verification.json` and `reports/stage6/synthetic-screenshots/`.
The earlier computer-use browser blocker was resolved using locally installed
Playwright Chromium. This does not establish clinical/live validity or permissions.

## Start on Windows / PowerShell

From the repository root, install dependencies once:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-stage6.txt
npm.cmd ci --prefix frontend
```

Use `npm.cmd`, since the machine's PowerShell policy may block `npm.ps1`. No machine
execution-policy change is needed. Launch the independent synthetic-only app:

```powershell
.\.venv\Scripts\python.exe scripts/start_stage6.py
```

Open **http://127.0.0.1:15173/**. API health: **http://127.0.0.1:18060/api/health**.
Ctrl+C stops only the backend and frontend children owned by this launcher.
Occupied ports produce an explicit error; unrelated services are not stopped.
These ports were chosen because 8000 and 5173 were already occupied during testing.
The loopback app is not deployed or published.

To enable private local processed-data sources, stop the earlier launcher first:

```powershell
.\.venv\Scripts\python.exe scripts/start_stage6.py --local
```

The launcher sets `GLUCOTWIN_LOCAL_REPLAY=1` only for its children. Without `--local`
it explicitly sets `0` and works without any CGMacros files, patient models,
private calibration data or dataset reports. Synthetic uses a hand-authored seeded
generator and persistence; its intervals are unavailable. It never loads patient
weights or interval quantiles. Synthetic scenario identifiers are not participants.

For separate terminals, the equivalent commands are:

```powershell
# Terminal 1: omit this assignment for synthetic-only mode (the default)
$env:GLUCOTWIN_LOCAL_REPLAY='1'
.\.venv\Scripts\python.exe scripts/serve_stage6.py
# Terminal 2
Set-Location frontend
npm.cmd run dev
```

The backend CORS allowlist is limited to `http://127.0.0.1:15173` and
`http://localhost:15173`. `GLUCOTWIN_FRONTEND_ORIGINS` may restrict that list,
not enable arbitrary remote origins. No production authentication is implemented.

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
the UI shows Working and does not substitute precomputed predictions.

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
No messages, deployment, staging, commit or push were performed.

## Repeat the browser verification

With the local app running, install Chromium once and run the synthetic-only UI check:

```powershell
Set-Location frontend
npm.cmd ci
npx.cmd playwright install chromium
Set-Location ..
node scripts/verify_stage6_browser.mjs
```

This launches actual headless Chromium and operates the app via its visible controls.
It saves a structured report and six synthetic screenshots; pending patient data
are never used. Before/after source hashes bind the report to the tested UI.
The source/model and scientific limitations remain unchanged. No deployment occurs.
