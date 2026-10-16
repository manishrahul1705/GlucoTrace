# Stage 6 architecture and replay contract

Configuration: `configs/stage6_replay.json`; scientific rules are unchanged in
`configs/stage5_protocol.json`. Stage 2/3/4/5 production modules and historical
reports are preserved. New code lives under `src/glucotwin/stage6/`.

| Component | Responsibility / access |
|---|---|
| Registry and source loader | Server-approved opaque IDs; local files or independent generator; never client file paths or remote patient data. |
| Revealed History | Accepts arrived records, rejects conflicting timestamps, provides only prior/current history. |
| Predictor | `PredictRequest(origin,history,variant,offset,quantiles)`; no source, reference table, event schedule or scoring results. |
| Immutable forecast ledger | Frozen dataclass values; origin/target identity and interval state never change after issue. |
| Evaluator | Holds reference targets separately; scores only at exact target maturity; no future targets in pending responses. |
| Manager / clock | One lifespan task, monotonic wall time, per-session virtual seconds, locked controls and session state. |
| SQLite Store | Appends immutable forecast and score events, records session metadata, retains old generations privately. |
| React client | Polls bounded snapshots, rejects stale generation/session/sequence responses; no clock advancement on reads. |

Prediction uses Stage 5 `forecast_stream` and `interval_bounds`, and the Stage 2
trailing builder. Requests contain only arrived history (including a preceding
last-valid cell for staleness metadata when needed); there is no backfilling of
glucose. A request with any future cell is rejected. The source loader validates
local model identity against stored Stage 5 features/predictions **only as an
artifact verification step**; those values never generate replay forecasts or enter
prediction requests. Replayed predictions are computed from revealed inputs.

This is an in-process capability boundary enforced by component interfaces and
tests, not OS/process sandboxing. Full sources exist in server memory, and trusted
server code could access them. Application future-mutation tests do not establish
causal validity of the release's upstream interpolation.

## Clock, timestamps and ordering

Every intermediate minute executes even when accelerated/stepped. At each minute:

1. Accept reading arrivals and resolve duplicates.
2. Freeze artifacts if this minute equals a phase boundary.
3. Issue on the original five-minute grid, using arrived history only.
4. Mature and score existing forecasts whose exact target equals this minute.

Upper phase support uses strict target_time<boundary. Consequently all eligible
earlier-phase labels mature **before** its freeze; labels equal to the boundary
are purged. Calibration never borrows offset pairs or later outcomes. At least
100 eligible pairs are required, retaining Stage 5 engineering gates; a non-finite
model output in an otherwise eligible early pair is recorded and invalidates
the affected fitting/calibration set rather than being silently omitted.

Source elapsed minutes map to artificial UTC epoch `2026-01-01T08:00:00+00:00`.
Unknown-timezone source datetimes are not relabelled true UTC. Source anchor is
the original first-valid Dexcom minute, while the issue grid remains anchored at
first parsed timestamp. Measurement_time and assumed_arrival_time are distinct,
equal by default under the zero-delay assumption. Configurable delays are deferred.
Targets use +30 elapsed minutes, not six records. Elapsed gaps are preserved.

Step requires pause; reset starts a fresh generation, clears active history,
forecasts, scores and fitting state, then performs the configured warmup if selected.
Old generations remain historical SQLite evidence and cannot be returned by stale
control requests. Polling is suspended and in-flight requests are drained before replacing/resetting a session, so deletion cannot race an old snapshot request. Request IDs make repeated controls idempotent; reuse with a
different payload is rejected. Session controls serialize under a lock; only one
background clock task is created per app lifespan. Snapshots are pure reads.

## Duplicates, failures and synthetic gaps

Identical ID/payload is idempotent. Equivalent observations at the same timestamp
collapse deterministically. Conflicting values invalidate the timestamp and any
subsequent required history containing it; no last-write-wins. Already issued
forecasts remain unchanged. Invalid units/non-finite/source-invalid readings cannot
become accepted glucose readings. Numeric absence serializes as JSON null.

Stage 5 reason codes cover current missingness/staleness, insufficient/incomplete
history, invalid units/model output/interval order, insufficient offset/calibration,
invalid calibration scores and missing exact target. Additional loader reasons:
`LOCAL_MODE_DISABLED`, `LOCAL_ARTIFACTS_UNAVAILABLE`, `SOURCE_UNAVAILABLE`,
`UNKNOWN_SCENARIO`, `INCOMPATIBLE_ARTIFACTS`. Missing/incompatible local artifacts
never trigger a synthetic substitute. API errors omit private paths and traces.

Independent synthetic uses a fixed seeded baseline, hand-scripted positive meal
and negative activity pulses plus AR/observation noise. It is not trained on
CGMacros, a validated physiological simulator or T2D validation. Its persistence
prediction has no calibrated interval; no patient quantiles or weights are loaded.

Separate clean and 15/30/60/120-minute input-loss scenarios remove input cells
before features. Half-open gaps start at synthetic minute180, or the inherited
local grid at/after anchor+72h. Evaluator references remain intact: transport/input
loss, not observation loss. Resume requires all 61 cells spanning 60 elapsed
minutes restored. No imputation, smoothing, stream substitution or silent clipping.

## API and persistence

FastAPI endpoints: health, approved sources, create, control, snapshot, reset and
delete, under `/api/replay/`. Pydantic forbids extra input fields; explicit nested
response models define forecasts, intervals, matured scores and summaries.

Snapshot defaults to 30 forecast records, max100; history max181 minute cells.
Use `after_seq` and `limit` for ascending event pages. Default snapshots show the
latest bounded records. Summary denominators distinguish scheduled, issued,
interval-available, matured and scored. Completion adds pending **issued** points,
issued points whose matured exact target is missing, and per-alpha coverage
denominators. Pending and missing-target counts exclude suppressed point issues.
MAE uses scored points; empirical coverage uses scored points with that interval
available, with an explicit denominator for each alpha. Synthetic coverage is null. Forecasts targeting beyond recording end remain
pending/unscored when the clock ends, never fabricated missing outcomes in advance.

SQLite under ignored `data/runtime/stage6/` persists metadata and immutable events.
Restart recovery is **not** implemented: prior IDs return HTTP410, with an explicit
create-new-session message. Delete expires a session and retains its historical
events. The development API has no production authentication and stays loopback.
No Internet hosting or publication is performed.

## Verification limits

Production tests exercise engine/API isolation, determinism, phase freezing,
dropout recovery, concurrency, reset, timestamps, missing artifacts, persistence
and bounded outputs. Frontend tests exercise stale session/generation/sequence and
request-epoch guards. The network verifier exercises real HTTP controls and delayed
scoring. The real-data agreement verifier reconstructs all early phases and compares
the first 120 evaluation minutes per source against Stage 5, not a new performance
study. It shares production code and is not wholly independent.

Actual Playwright Chromium verification now passes at 1440px, 768px and 390px,
including controls, delayed scoring, all four dropout durations and disclosure
persistence while scrolled. The disclosure is sticky; session transitions drain
polling before reset/replacement. Final console/page errors, failed requests and
failed API responses are zero. Six synthetic screenshots were visually inspected.
The original computer-use-only blocker is historical; locally installed Chromium
resolved it. The browser report records exact scope and tested-source hashes.
This is Chromium viewport verification, not physical-device or clinical validation.

## Completion evidence

Current UI/browser/source-copy checks are separate in `reports/completion/`; original Stage 6 evidence above is preserved as historical context. Help is inline and keyboard-accessible. One outstanding poll and synchronous transition/discovery guards bound browser requests. Expired sessions stop polling and expose create-new recovery. Malformed private inventories are unavailable. Current SVG endpoints represent every issued point in the bounded displayed page; interval whiskers remain absent for issues created before interval availability. Exact data/scientific contracts are unchanged.
