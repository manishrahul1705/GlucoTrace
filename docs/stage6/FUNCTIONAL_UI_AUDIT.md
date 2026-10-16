# Replay workspace: startup and interaction guide

This remains a local synthetic/retrospective research application. Existing
permissions and research limitations are unchanged. No submission materials,
videos or external correspondence are part of this audit.

## Start the current application

From the repository root, after installing the documented dependencies:

```powershell
.\.venv\Scripts\python.exe scripts/start_stage6.py
```

Open http://127.0.0.1:15173/ (API18060). Default synthetic mode requires no patient
files. An already running Python server must be restarted to load backend changes;
restart expires runtimes and retains local evidence. Recreate a retained synthetic
configuration as a new session rather than attempting to resume an expired one.
Use `--api-port 18061 --web-port 15174` for free alternative ports. Do not stop an
unrelated listener. `--local` explicitly enables matching private artifacts;
missing artifacts are unavailable rather than substituted with synthetic values.

## Configure and inspect

Choose a source, scenario, seed and duration. When changing to a private source,
an unsupported synthetic-only scenario becomes clean input; supported dropout
choices remain. Both fixed sensor-only private variants remain available, with
no preferred model or outcome-dependent switching.

Warm start processes earlier events chronologically. Preparation reports real
elapsed wall time; it does not estimate completion or advance the virtual clock.
Start/pause, five-minute step, three speeds and reset retain their original
semantics. Reset creates a new generation.

Follow replay is now a real toggle. Turning it off holds the current inspection
minute; moving the cutoff also enters historical inspection. Return to current
time appears only in historical mode. Changing the history range never reveals
unobserved future readings. Missing spans remain missing, and forecast endpoints
do not form an invented trajectory.

Click an endpoint or ledger origin, or press Enter/Space on a focused endpoint.
The inspector holds the displayed as-of cutoff, including score availability.
Live polls cannot turn a historical pending target into a revealed target.
Close and reopen to inspect a later cutoff. Escape closes and restores focus.

## Library and exports

The current replay is marked in the library. Names require a visible printable
character and at most80 characters; quoted/formula-leading text remains literal
and is escaped in CSV exports. Save/load/export feedback describes actual actions.
Overlapping library actions are prevented, and late refresh/summary responses
cannot overwrite a newer context. Summaries are read-only and remain per variant.

Five synthetic exports freeze the request cutoff and include provenance/version,
seed, units and unavailable values. Pending targets stay blank. An “export prepared”
message means the browser download was initiated, not that a file was saved to a
particular disk location. Patient exports remain backend-rejected. Help remains
keyboard-operable and never starts playback.

The ledger renders the latest12 rows, the library requests12 retained sessions,
and chart exploration remains bounded. Counts use explicit denominators; absent
scores and unavailable intervals remain unavailable. No clinical/live validation,
validated physiological simulation or guaranteed coverage is claimed.

Audit evidence is separate under `reports/functional_ui/`; the detailed local
handoff is `GLUCOTWIN_FUNCTIONAL_UI_AUDIT_HANDOFF.md`.
