# Scenario Lab, sessions and synthetic exports

The feature update reuses the Stage 6 minute clock, history-only predictor, immutable
ledger, delayed evaluator, polling gate, disclosures and seven-step Help. New features
are integrated into the existing replay workspace rather than a second application.

## Start

Tested Windows Python 3.12.3, Node 24.21.0/npm 11.11.1:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-stage6.txt
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
.\.venv\Scripts\python.exe scripts/start_stage6.py
```

Open http://127.0.0.1:15173/ (API 18060). Default synthetic-only mode needs no private
artifacts or unpublished research reports. `--local` explicitly enables matching
private processed sources. Optional distinct `--api-port`/`--web-port` remain supported.
No dependency additions were needed. Loopback/CORS restrictions remain unchanged.

## Authoring and reproduction

Choose Scripted day, Steady baseline, Scripted rise & recovery, Activity variation,
Noisy observations or input loss of 15/30/60/120 minutes. Seeds are strict integers
0–2147483647. Duration is360–1440minutes in five-minute increments. Backend validation
is authoritative. Original scripted scenarios retain `scripted-v1`; the four new
profiles use `scenario-lab-v1`. They are hand-authored and seeded, never fitted to
patient trajectories. Persistence is the only synthetic predictor; synthetic intervals
and coverage remain unavailable. These are not validated physiological or treatment
simulators. No medication/dose controls exist.

Active configuration includes name/description, scenario, seed, generator version,
duration, input-loss duration, predictor, provenance and units. No realized future
glucose or future event schedule is returned in normal snapshots. The older `gap`
snapshot field is now null; input-loss duration is transparent configuration, while
the schedule remains internal to source generation and outside predictor requests.
The explanatory Help describes the authored loss rule, without showing future values.

Reset uses exactly the existing source/configuration with a new generation. The
library's Recreate scenario creates a NEW session ID and generation with that
configuration; it never resumes old clock/runtime state. Select full or warm start
before creation/recreation. Exported configuration JSON reproduces the same generator
via the create request below; only the scenario/seed/duration fields are input settings.

## Library and migration

The library lists 12 recent sessions in the UI (API default 20/max 50), with harmless
name, mode/scenario, seed, creation time and status. Names are1–80 printable characters;
they are parameterized SQL values, never filesystem paths. Renaming preserves IDs,
generation, configuration and immutable events. Summary viewing is read-only.

SQLite migration version 1 adds nullable display_name/created_at/configuration/summary
columns to the existing sessions table. For an existing old schema, a SQLite backup
is created before ALTER operations, alongside the database with a unique suffix if
needed; the connection closes explicitly. Events and old metadata remain unchanged.
Restart expires all runtimes; old rows remain listed as expired. Legacy rows lacking
configuration/summary are honestly unavailable for those features, not reconstructed
from guesses. A new session is never silently created under an expired generation.
The backup, SQLite evidence and source keys must remain ignored/private.

## Inspector and revealed-history exploration

Click a chart endpoint or ledger origin, or press Enter/Space on a focused endpoint.
The native modal dialog traps interaction, supports Escape/close and restores focus.
It shows model, origin/exact target, point/reason, nominal intervals/reasons, required
history span, accepted cell count recorded at issue, phase and opaque artifact identity.
No patient calibration scalars/quantiles/files are exposed. Observed target and errors
only appear after maturity at the inspected cutoff. Earlier issues retain their original
unavailable intervals even after calibration completes.

History windows 60/180/360 minutes and an inspection cutoff select only revealed data.
Follow replay / Return to current time restore the live virtual clock. Historical
projections mask scores maturing after that historical cutoff. Missing spans stay gaps;
each point is one separate origin+30 endpoint, never a smooth future trajectory.
Exploration requests share the transition polling gate and are drained before replacement.
New session/generation keys reset the chart view; obsolete responses cannot replace it.

## Summary denominators

Each variant is summarized separately. Private mode uses support-safe evaluation-phase
issues only, excluding offset/calibration/purged issues. Synthetic mode uses all scheduled
scenario origins, including those suppressed while history builds. Do not add the two
private variant counts together as if they were different origins.

- Scheduled: issue origins in that phase; issued: non-null points.
- Available intervals: issued events with at least one available nominal band.
- Pending: issued points with no matured score; missing targets: issued points with
  an exact matured target missing. Suppressed points are not pending issued forecasts.
- Scored: valid issued points with exact observed target at maturity.
- Forecast availability=issued/scheduled; scoring availability=scored/issued.
  Both are null when denominator is zero; pending points stay in the issued denominator.
- MAE and mean signed error (prediction minus target) use scored points only; an empty
  set is null. Nominal levels and measured coverage remain distinct, with per-level
  scored-interval denominators. Synthetic interval coverage stays unavailable.

## API contracts

All requests forbid extra fields. Main additions:

| Method/path | Contract |
|---|---|
| GET `/api/replay/scenarios` | Bounded authored catalog; no realized values |
| POST `/api/replay/sessions` | Existing source_id/start plus scenario, strict seed, duration_minutes; private settings remain fixed |
| GET `/api/replay/library?limit=20` |1–50 recent metadata/retained-summary rows; opaque IDs |
| GET `/api/replay/library/{id}` | Read-only metadata/aggregate summary or404 |
| POST `/api/replay/library/{id}/rename` | `{name}`; no identity/science change |
| POST `/api/replay/library/{id}/recreate` | `{start:"full" or "warm"}`; synthetic retained configuration only |
| GET `/api/replay/sessions/{id}/explore?end_minute=60&window=180` | End must be revealed; window 60/180/360; <=361 readings and 100 forecast records |
| POST `/api/replay/sessions/{id}/export` | `{generation,kind,cutoff_minute?}`; synthetic-only; kinds below |

Snapshot forecasts add history_start/end/count and artifact_identity, recorded at issue.
Summaries add mean_signed_error, forecast_availability and scoring_availability.
Snapshot configuration is synthetic configuration or null for private/legacy sources.
Unknown session404; expired runtime410; stale generation409; invalid settings422;
patient export403; oversized export413. Existing request-id idempotency and concurrent
control locking remain. Frontend-consumed replay/list projections are validated rather
than replaced with hard-coded success metrics.

## Export schema `glucotwin-synthetic-export-v1`

POST kinds: `configuration` JSON, `readings` CSV, `forecasts` CSV, `scores` CSV,
`summary` JSON. Every payload/CSV record carries export_schema_version,
synthetic_provenance, generator_version, seed, virtual_cutoff, units and predictor.
Empty score CSVs retain a metadata-only row. A cutoff is an integer minute already
processed; default is the current processed minute under the same manager lock.
No target joins or reference-map access occur during export. Pending observed targets
are blank/null; scores include only matured outcomes. Historical cutoff exports are
deterministic as the fixed authored stream advances. Summary exports do not include
wall-clock generation times, which would break that determinism.

CSV uses standard quoting. User-controlled formula-leading text (including leading
whitespace before =,+,-,@) gets an apostrophe prefix; numeric errors stay numeric.
Filenames are fixed ASCII names, never derived from the display name. Export body is
bounded at 2 MB; scenario length is bounded at 1440 minutes. Patient-backed export is
unconditionally blocked, including configuration and aggregate download routes.
No patient data/model/quantile publication is added.

## Verification and limits

Current evidence is in `reports/feature_update/`, separate from earlier reports.
Source-only checks use synthetic fixtures; the combined verifier additionally requires
private frozen Stage5 artifacts. No fitting/search is needed. Dataset permissions,
external feedback, official competition requirements, original arrivals/upstream support,
independent/prospective validation and dependent-data exchangeability remain unresolved.
Both frozen private references, high-glucose deterioration and undercoverage remain
research context, never claims about synthetic accuracy. No deployment or external action.
