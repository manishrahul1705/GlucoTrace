# GlucoTrace: 30-minute recording checklist

Patient-Adaptive Glucose Forecasting Research Platform

This is a 30-minute presentation, not a 30-minute input dataset. Record only demo
mode. Keep the persistent "Demo data — simulated readings" disclosure visible.
Do not select private patient replay while competition-use clarification is pending.
No video is recorded or submitted by these preparation steps.

## Preparation and launch

Use the current checkout or a NEW source snapshot containing the GlucoTrace changes.
The preserved `release-rehearsal-20261019-v1/candidate` is an older GlucoTwin copy;
checkout edits do not update it. Leave that snapshot and all frozen bundles intact.
For recording, prefer a fresh source snapshot and its initially empty local runtime;
do not reuse a library containing private patient sessions. Install frontend packages
with `npm.cmd ci --prefix frontend` and select a compatible Python environment as
in [setup](README.md). From the updated source root:

```powershell
$python = '.\venv\Scripts\python.exe' # Or your verified Python 3.12 interpreter.
& $python scripts/start_stage6.py --api-port 18170 --web-port 15283 --config-loader runner
```

Open http://127.0.0.1:15283/. The launcher serves the source tree containing its own
script, not whichever copy was edited elsewhere. The explicit alternate loader is
for restricted environments. Use fresh distinct ports if occupied; do not stop other
services. Synthetic-only backend operation is the default; do not pass `--local`.
A fresh snapshot can use an absolute path to an existing verified Python interpreter.
The exact verified snapshot command is recorded in the private branding checkpoint.

Confirm the browser title, header and home heading say GlucoTrace, with the subtitle
above. Choose Demo data, seed **1705**, duration **720 minutes**, and **Warm start**.
Warm start processes minutes0–120 chronologically. It provides more than the61
accepted minute cells spanning60 minutes needed for a point forecast; no history
requirement is shortened. All nine existing scenarios remain available. The demo
predictor is persistence, not patient-trained Ridge; adaptation, calibrated interval
bounds and empirical interval coverage are unavailable. Source information and Help
retain simulation provenance; exports/API records still explicitly say synthetic.

## Recording sequence (30 minutes of narration)

| Recording time | Actions and points to explain |
| --- | --- |
| 0–3 min | Show GlucoTrace/subtitle and persistent source disclosure. Open Source information and Help. Explain simulated data, persistence and the exact+30-minute endpoint. |
| 3–8 min | Open Demo scenarios. Select Scripted day or Steady baseline, warm start, seed1705,720minutes. Demonstrate Start, Pause, Step5min,1x/60x/300x and Reset. Explain virtual replay speed differs from recording time. |
| 8–14 min | Show61/61 history support, immutable origin and target, pending endpoint flags and unavailable intervals. Inspect a forecast. Briefly create a full chronological session to show unavailable history, then return to warm start. No Ridge adaptation or interval calibration is demonstrated. |
| 14–20 min | Create the15-minute input-loss demo, same seed/duration/warm start. Pause and step to minute180. Show suppression; inputs return at195. Rebuild history through minute255 (61cells spanning60minutes), then verify recovery. Reference targets remain available to the evaluator. Other supported losses are30/60/120minutes. |
| 20–24 min | Reset or create a clean warm demo. Inspect a fresh issue while its target is pending. Advance six5-minute steps to exact+30 maturity. Revisit the earlier cutoff: later readings, scores and endpoint outcomes remain hidden. Missing targets are unscorable, not negative outcomes. |
| 24–27 min | Show automatic local session retention. Rename a demo, save, inspect its retained summary and recreate it as a new session. Download configuration, readings, forecasts, scores and summary; explain fixed cutoffs, explicit simulation metadata and blank pending/unavailable values. CSV formula-like names are escaped. |
| 27–30 min | Recap exact endpoints versus onset/episode prediction, unavailable intervals, simulation versus processed retrospective research, no clinical/dosing claims and pending competition-use clarification. Finish on the demo disclosure and research boundaries. |

At minute180, affected forecasts are suppressed. Recovery may be delayed when a
source itself lacks support; inspect the actual readiness panel rather than promise
a universal recovery time. The authored15-minute demo with seed1705 supplies support
at255. Use Step while paused for exact boundaries;300x is useful for travel only.
Keep the browser at100% zoom, preferably1440px wide. Layout at360/768/1440 is checked;
the previously known360px/CSS200% overflow limitation is not fixed here. Native zoom
and an actual30-minute recording are not claimed by the automated checks.

## Naming and provenance boundaries

Current product surfaces use GlucoTrace. Internal `glucotwin` modules, repository
name/URLs, environment variables, scenario IDs, API routes, database schemas,
simulation reason codes and historical export metadata remain compatible. Old
GlucoTwin references in historical reports, frozen manifests, old technical records
and non-rendered CSS provenance comments are intentional, not current branding.
Historical research findings are not renamed or represented as new demo evidence.
Do not distribute private artifacts, screenshots or logs. Demo-only recording does
not establish permission to submit or publish a video.
