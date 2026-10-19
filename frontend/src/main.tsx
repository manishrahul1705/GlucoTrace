import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ArrowRight,
  ChevronRight,
  Clock3,
  Database,
  Download,
  FlaskConical,
  Layers3,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  Signal,
  SkipForward,
  TriangleAlert
} from 'lucide-react';
import type { Snapshot, Source, Forecast } from './types';
import { acceptsSnapshot, responseIsCurrent, PollingGate } from './state';
import './style.css';
import './functional-ui.css';
import { Help } from './help';
import { FeaturePanels, ForecastInspector, ScenarioDetails, labApi } from './lab';
import { validateSnapshot } from './validation';
import { scenarioForSource, inspectionAtCutoff, explorationAtCutoff, type Inspection } from './workflow';
import { reasonDetail, reasonText } from './reasons';
import { Availability, IssuedForecast } from './availability';

const time = (value: string) =>
  new Date(value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' });

const number = (v: number | null | undefined, dp = 1) => (v == null ? '—' : v.toFixed(dp));

const label = (v: string) => ({persistence:'Persistence',sensor_only_unadapted:'Sensor-only ? unadapted',sensor_only_offset24h:'Sensor-only ? 24h offset',baseline_sensor_unadapted:'Baseline + sensor ? unadapted',baseline_sensor_offset24h:'Baseline + sensor ? 24h offset'}[v] ?? v);

const reason = reasonDetail;

async function api<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch('/api' + path, {
    method: method ?? (body ? 'POST' : 'GET'),
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(
      path === '/replay/sessions' || path.endsWith('/recreate') || path.endsWith('/reset') ? 120000 : 30000
    )
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : Array.isArray(data.detail)
        ? data.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.at(-1)}: ${d.msg}`).join('; ')
        : 'Request could not be completed.'
    );
  if (data.session_id) validateSnapshot(data);
  return data as T;
}

const SCENARIO_CATALOG_DATA = [
  {
    id: 'clean',
    name: 'Scripted Day',
    category: 'Daily Profile',
    desc: 'Authored daily profile with physiological rises, meals, and glycemic variation.',
    version: 'scripted-v1',
    loss: 0,
    badge: 'Baseline'
  },
  {
    id: 'steady',
    name: 'Steady Baseline',
    category: 'Constant',
    desc: 'Constant authored glucose level (~110 mg/dL) with low observation noise (±0.35 mg/dL).',
    version: 'scenario-lab-v1',
    loss: 0,
    badge: 'Steady'
  },
  {
    id: 'meal',
    name: 'Scripted Rise & Recovery',
    category: 'Postprandial',
    desc: 'Isolated meal-related glycemic excursion peaking at ~165 mg/dL with exponential return.',
    version: 'scenario-lab-v1',
    loss: 0,
    badge: 'Glycemic Event'
  },
  {
    id: 'activity',
    name: 'Activity Variation',
    category: 'Exertion',
    desc: 'Acute exertion-induced downward excursion (-18 mg/dL) at minute 180, followed by steady recovery.',
    version: 'scenario-lab-v1',
    loss: 0,
    badge: 'Exertion'
  },
  {
    id: 'noisy',
    name: 'Noisy Observations',
    category: 'Measurement Noise',
    desc: 'High-frequency Gaussian measurement noise (σ=4.0 mg/dL) testing model lag resistance.',
    version: 'scenario-lab-v1',
    loss: 0,
    badge: 'Noisy'
  },
  {
    id: 'dropout15',
    name: '15-Min Input Loss',
    category: 'Simulated Input Dropout',
    desc: '15-minute simulated input dropout at minute 180. Suppresses forecasts; requires 61 valid cells to recover.',
    version: 'scripted-v1',
    loss: 15,
    badge: 'Loss 15m'
  },
  {
    id: 'dropout30',
    name: '30-Min Input Loss',
    category: 'Simulated Input Dropout',
    desc: '30-minute simulated input dropout at minute 180. Evaluates prompt suppression and exact recovery boundary.',
    version: 'scripted-v1',
    loss: 30,
    badge: 'Loss 30m'
  },
  {
    id: 'dropout60',
    name: '60-Min Input Loss',
    category: 'Simulated Input Dropout',
    desc: '1-hour simulated input dropout at minute 180. Evaluator reference targets retained for retrospective scoring.',
    version: 'scripted-v1',
    loss: 60,
    badge: 'Loss 60m'
  },
  {
    id: 'dropout120',
    name: '120-Min Input Loss',
    category: 'Simulated Input Dropout',
    desc: 'Extended 2-hour simulated input dropout at minute 180. Demonstrates full history rebuilding before restoration.',
    version: 'scripted-v1',
    loss: 120,
    badge: 'Loss 120m'
  }
];

function Chart({
  snapshot: live,
  alpha,
  onInspect,
  gate
}: {
  snapshot: Snapshot | null;
  alpha: string;
  onInspect: (f: Forecast, cutoff: string) => void;
  gate: PollingGate;
}) {
  const [window, setWindow] = useState(180);
  const [endMinute, setEndMinute] = useState<number | null>(null);
  const [view, setView] = useState<Pick<Snapshot, 'history' | 'forecasts' | 'virtual_time'> | null>(null);
  const [rangeError, setRangeError] = useState('');

  useEffect(() => {
    setEndMinute(null);
    setView(null);
  }, [live?.session_id, live?.generation]);

  useEffect(() => {
    let valid = true;
    if (!live || gate.paused) return;
    gate.track(
      labApi<Pick<Snapshot, 'history' | 'forecasts' | 'virtual_time'>>(
        `/sessions/${live.session_id}/explore?end_minute=${endMinute ?? Math.floor(live.elapsed_minutes)}&window=${window}`
      )
        .then(data => {
          if (!Array.isArray(data.history) || !Array.isArray(data.forecasts))
            throw Error('Invalid exploration response');
          if (valid) {
            setView(data);
            setRangeError('');
          }
        })
        .catch(e => {
          if (valid) setRangeError(e.message);
        })
    );
    return () => {
      valid = false;
    };
  }, [live?.session_id, live?.generation, live?.sequence, window, endMinute]);

  const cutoff = live
    ? new Date(Date.parse(live.session_epoch) + (endMinute ?? Math.floor(live.elapsed_minutes)) * 60000).toISOString()
    : '';

  const snapshot = live ? { ...live, ...explorationAtCutoff(view ?? live, cutoff, window) } : null;

  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);

  useEffect(() => {
    const obs = new ResizeObserver(e => setWidth(e[0].contentRect.width));
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  const w = Math.max(width, 260);
  const h = 270;
  const left = 40;
  const right = 20;
  const top = 22;
  const bottom = 34;

  const now = snapshot ? new Date(snapshot.virtual_time).getTime() : 0;
  const start = now - window * 60000;
  const end = now + 35 * 60000;

  const x = (t: number) => left + ((t - start) / (end - start)) * (w - left - right);

  const values = (snapshot?.history ?? []).flatMap(r => (r.value == null ? [] : [r.value]));
  for (const f of snapshot?.forecasts ?? []) {
    if (f.value != null) values.push(f.value);
    for (const i of f.intervals)
      if (i.alpha === alpha && i.lower != null && i.upper != null) values.push(i.lower, i.upper);
  }

  const lo = Math.floor(Math.min(60, ...values) / 20) * 20;
  const hi = Math.ceil(Math.max(240, ...values) / 20) * 20;
  const y = (v: number) => h - bottom - ((v - lo) / (hi - lo)) * (h - top - bottom);

  const paths: string[] = [];
  let path = '';
  for (const r of snapshot?.history ?? []) {
    if (r.value == null) {
      if (path) paths.push(path);
      path = '';
      continue;
    }
    path += `${path ? 'L' : 'M'}${x(new Date(r.measurement_time).getTime())},${y(r.value)} `;
  }
  if (path) paths.push(path);

  const endpoints = (snapshot?.forecasts ?? []).filter(f => new Date(f.target_time).getTime() >= start);

  return (
    <>
      <div className="chart-controls">
        <label>
          History range
          <select aria-label="History range" value={window} onChange={e => setWindow(Number(e.target.value))}>
            {[60, 180, 360].map(n => (
              <option key={n} value={n}>
                {n} minutes
              </option>
            ))}
          </select>
        </label>

        <label style={{ flexGrow: 1, minWidth: '130px' }}>
          Inspection cutoff
          <input
            aria-label="Inspection cutoff"
            type="range"
            min={0}
            max={Math.floor(live?.elapsed_minutes ?? 0)}
            value={endMinute ?? Math.floor(live?.elapsed_minutes ?? 0)}
            disabled={!live}
            onChange={e => setEndMinute(Number(e.target.value))}
          />
        </label>

        <button
          disabled={!live}
          aria-pressed={endMinute === null}
          onClick={() => setEndMinute(current => (current === null ? Math.floor(live?.elapsed_minutes ?? 0) : null))}
        >
          Follow replay
        </button>

        {endMinute !== null && (
          <button disabled={!live} onClick={() => setEndMinute(null)}>
            Return to current time
          </button>
        )}

        <span>{endMinute === null ? 'Following replay' : `Historical inspection · minute ${endMinute}`}</span>
      </div>

      {rangeError && (
        <p role="alert" className="error" style={{ margin: '8px 16px' }}>
          {rangeError}
        </p>
      )}

      <div ref={ref} className="chart">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          role="group"
          aria-label="Revealed glucose history with separate forecast endpoints, no future ground truth"
        >
          {/* Future prediction interval region background */}
          <rect
            x={x(now)}
            y={top}
            width={Math.max(0, w - right - x(now))}
            height={h - top - bottom}
            fill="#FAF6ED"
            opacity="0.85"
          />

          {/* Grid lines and values */}
          {Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4).map(v => (
            <g key={v}>
              <line x1={left} x2={w - right} y1={y(v)} y2={y(v)} stroke="#E5EDF2" strokeWidth="1" />
              <text x={left - 8} y={y(v) + 4} textAnchor="end">
                {v.toFixed(0)}
              </text>
            </g>
          ))}

          <text x={left} y={14} fontWeight="600">
            mg/dL
          </text>
          <text x={w - right} y={14} textAnchor="end" fontWeight="600">
            t + 30
          </text>

          {/* Revealed reading segments */}
          {paths.map((d, i) => (
            <path key={i} d={d} fill="none" stroke="#117F87" strokeWidth="2.6" strokeLinejoin="round" />
          ))}

          {/* Current virtual time reference line */}
          <line
            x1={x(now)}
            x2={x(now)}
            y1={top}
            y2={h - bottom}
            stroke="#8496A6"
            strokeWidth="1.2"
            strokeDasharray="4 4"
          />

          {/* Forecast endpoints */}
          {endpoints.map(f => {
            if (f.value == null) return null;
            const isOffset = f.variant.endsWith('_offset24h');
            const fx = x(new Date(f.target_time).getTime());
            const fy = y(f.value);
            const interval = f.intervals.find(a => a.alpha === alpha);
            const color = isOffset ? '#7852A9' : '#C08032';

            return (
              <g
                key={f.id}
                tabIndex={0}
                role="button"
                onClick={() => onInspect(f, snapshot!.virtual_time)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onInspect(f, snapshot!.virtual_time);
                  }
                }}
                aria-label={`${label(f.variant)}; origin ${time(f.origin_time)}; target ${time(f.target_time)}; ${number(
                  f.value
                )} mg/dL; ${f.score ? reasonText(f.score.reason) : 'Pending target'}`}
                stroke={color}
                fill={color}
              >
                <title>{`${label(f.variant)} · origin ${time(f.origin_time)} → target ${time(
                  f.target_time
                )} · ${number(f.value)} mg/dL · ${f.score ? reasonText(f.score.reason) : 'Pending target'}`}</title>
                {interval?.lower != null && interval.upper != null && (
                  <>
                    <line x1={fx} x2={fx} y1={y(interval.lower)} y2={y(interval.upper)} strokeWidth="2" />
                    <line x1={fx - 4} x2={fx + 4} y1={y(interval.lower)} y2={y(interval.lower)} strokeWidth="1.5" />
                    <line x1={fx - 4} x2={fx + 4} y1={y(interval.upper)} y2={y(interval.upper)} strokeWidth="1.5" />
                  </>
                )}
                <circle cx={fx} cy={fy} r="4.5" />
              </g>
            );
          })}

          {/* Time ticks */}
          {(w < 500 ? [-window, -window / 2, 0, 30] : [-window, (-window * 2) / 3, -window / 3, 0, 30]).map(m => (
            <text key={m} x={x(now + m * 60000)} y={h - 8} textAnchor="middle">
              {snapshot ? time(new Date(now + m * 60000).toISOString()) : '—'}
            </text>
          ))}
        </svg>
      </div>
    </>
  );
}

function App() {
  const [section, setSection] = useState(location.hash || '#replay');

  useEffect(() => {
    const changed = () => setSection(location.hash || '#replay');
    addEventListener('hashchange', changed);
    return () => removeEventListener('hashchange', changed);
  }, []);

  const [operation, setOperation] = useState('');
  const [busySeconds, setBusySeconds] = useState(0);
  const [sources, setSources] = useState<Source[]>([]);
  const [source, setSource] = useState('synthetic-dawn');
  const [scenario, setScenario] = useState('clean');
  const [start, setStart] = useState('warm');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [alpha, setAlpha] = useState('0.10');
  const [seed, setSeed] = useState(1705);
  const [duration, setDuration] = useState(720);
  const [catalog, setCatalog] = useState<{ id: string; name: string; description: string }[]>([]);
  const [inspected, setInspected] = useState<Inspection | null>(null);

  const inspectorReturn = useRef<HTMLElement | null>(null);

  const openInspector = (f: Forecast, cutoff = active.current?.virtual_time ?? f.origin_time) => {
    inspectorReturn.current = document.activeElement as HTMLElement;
    setInspected(inspectionAtCutoff(f, cutoff));
  };

  const closeInspector = () => {
    setInspected(null);
    requestAnimationFrame(() => {
      if (inspectorReturn.current?.isConnected) inspectorReturn.current.focus();
    });
  };

  const active = useRef<Snapshot | null>(null);
  const epoch = useRef(0);
  const polling = useRef(new PollingGate());
  const transition = useRef(false);
  const [expired, setExpired] = useState(false);
  const [loadingSources, setLoadingSources] = useState(true);
  const discovery = useRef(false);

  useEffect(() => {
    if (!busy) {
      setBusySeconds(0);
      return;
    }
    const since = performance.now();
    const timer = setInterval(() => setBusySeconds(Math.floor((performance.now() - since) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [busy]);

  const loadSources = () => {
    if (discovery.current) return;
    discovery.current = true;
    setLoadingSources(true);
    setError('');
    setPollError('');
    void Promise.all([api<{ sources: Source[] }>('/replay/sources'), labApi<{ scenarios: typeof catalog }>('/scenarios')])
      .then(([x, c]) => {
        if (!Array.isArray(x.sources) || !Array.isArray(c.scenarios)) throw Error('Invalid source/scenario response');
        setSources(x.sources);
        setCatalog(c.scenarios);
      })
      .catch(() => setError('Backend unavailable. Start the local server, then retry source discovery.'))
      .finally(() => {
        discovery.current = false;
        setLoadingSources(false);
      });
  };

  const fail = (e: unknown, fromPoll = false) => {
    const message = (e as Error).message;
    if (/SESSION_EXPIRED|SESSION_NOT_FOUND/.test(message)) {
      setExpired(true);
      polling.current.paused = true;
      setError('This replay has expired or the server restarted. Create a new session; earlier events remain retained locally.');
    } else {
      const text = message === 'Failed to fetch' ? 'Cannot reach the local backend. Check the server, then retry.' : message;
      if (fromPoll) setPollError(text);
      else setError(text);
    }
  };

  const update = (next: Snapshot, replace = false) => {
    if (replace || acceptsSnapshot(active.current, next)) {
      active.current = next;
      setSnapshot(next);
      if (replace) setInspected(null);
    }
  };

  useEffect(() => {
    loadSources();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      const current = active.current;
      if (!current || polling.current.paused || polling.current.inFlight) return;
      const version = epoch.current;
      polling.current.track(
        api<Snapshot>(`/replay/sessions/${current.session_id}/snapshot`)
          .then(x => {
            if (responseIsCurrent(version, epoch.current)) {
              update(x);
              setPollError('');
            }
          })
          .catch(e => {
            if (responseIsCurrent(version, epoch.current)) fail(e, true);
          })
      );
    }, 600);
    return () => clearInterval(timer);
  }, []);

  const create = async (recreateId?: string) => {
    if (transition.current) return;
    transition.current = true;
    const version = ++epoch.current;
    setBusy(true);
    setOperation('Preparing session');
    setError('');
    setPollError('');
    try {
      await polling.current.suspend();
      const old = active.current;
      const next = recreateId
        ? await api<Snapshot>(`/replay/library/${recreateId}/recreate`, { start })
        : await api<Snapshot>('/replay/sessions', {
            source_id: source,
            scenario,
            start,
            seed: source === 'synthetic-dawn' ? seed : 1705,
            duration_minutes: source === 'synthetic-dawn' ? duration : 720
          });
      if (next.configuration) {
        setSource('synthetic-dawn');
        setScenario(next.configuration.scenario);
        setSeed(next.configuration.seed);
        setDuration(next.configuration.duration_minutes);
      }
      if (responseIsCurrent(version, epoch.current)) {
        update(next, true);
        setExpired(false);
        polling.current.resume();
        if (old && !expired) void api(`/replay/sessions/${old.session_id}`, undefined, 'DELETE').catch(() => {});
      }
    } catch (e) {
      fail(e);
    } finally {
      if (responseIsCurrent(version, epoch.current)) {
        if (!expired) polling.current.resume();
        transition.current = false;
        setBusy(false);
        setOperation('');
      }
    }
  };

  const control = async (action: string, speed?: number) => {
    const current = active.current;
    if (!current || transition.current || expired) return;
    transition.current = true;
    setBusy(true);
    setOperation('Updating replay');
    setError('');
    setPollError('');
    const version = epoch.current;
    try {
      const next = await api<Snapshot>(`/replay/sessions/${current.session_id}/control`, {
        generation: current.generation,
        request_id: crypto.randomUUID(),
        action,
        speed
      });
      if (responseIsCurrent(version, epoch.current)) update(next);
    } catch (e) {
      fail(e);
    } finally {
      transition.current = false;
      setBusy(false);
      setOperation('');
    }
  };

  const reset = async () => {
    const current = active.current;
    if (!current || transition.current || expired) return;
    transition.current = true;
    const version = ++epoch.current;
    setBusy(true);
    setOperation('Resetting replay');
    setError('');
    setPollError('');
    try {
      await polling.current.suspend();
      const next = await api<Snapshot>(`/replay/sessions/${current.session_id}/reset`, {
        generation: current.generation,
        request_id: crypto.randomUUID()
      });
      if (responseIsCurrent(version, epoch.current)) update(next, true);
    } catch (e) {
      fail(e);
    } finally {
      if (!expired) polling.current.resume();
      transition.current = false;
      setBusy(false);
      setOperation('');
    }
  };

  const mode = snapshot?.mode ?? sources.find(s => s.id === source)?.mode ?? 'synthetic';
  const latest = new Map<string, Forecast>();
  for (const f of snapshot?.forecasts ?? []) latest.set(f.variant, f);
  const summaries = snapshot?.summaries ?? [];
  const last = snapshot?.latest_reading;
  const selected = sources.find(s => s.id === source);

  // Active view destination helper
  const isScenarioLabView = section === '#scenario-lab';
  const isSessionLibraryView = section === '#session-library';
  const isResultsExportsView = section === '#results-exports' || section === '#session-summary';

  return (
    <div className="workspace">
      {/* Primary Left Navigation */}
      <aside className="sidebar">
        <a className="brand" href="#replay" aria-label="GlucoTwin replay workspace">
          <span className="brand-mark">
            <Activity size={18} />
          </span>
          GlucoTwin<span className="brand-dot">.</span>
        </a>

        <div className="sidebar-label">PRIMARY WORKSPACES</div>

        <a
          className={`nav-item ${section === '#replay' || (!isScenarioLabView && !isSessionLibraryView && !isResultsExportsView && section !== '#ledger' && section !== '#method') ? 'active' : ''}`}
          aria-current={section === '#replay' || (!isScenarioLabView && !isSessionLibraryView && !isResultsExportsView && section !== '#ledger' && section !== '#method') ? 'location' : undefined}
          href="#replay"
        >
          <Activity size={16} /> Replay Workspace <ChevronRight size={14} />
        </a>

        <a
          className={`nav-item ${isScenarioLabView ? 'active' : ''}`}
          aria-current={isScenarioLabView ? 'location' : undefined}
          href="#scenario-lab"
        >
          <FlaskConical size={16} /> Scenario Lab <ChevronRight size={14} />
        </a>

        <a
          className={`nav-item ${isSessionLibraryView ? 'active' : ''}`}
          aria-current={isSessionLibraryView ? 'location' : undefined}
          href="#session-library"
        >
          <Database size={16} /> Session Library <ChevronRight size={14} />
        </a>

        <a
          className={`nav-item ${isResultsExportsView ? 'active' : ''}`}
          aria-current={isResultsExportsView ? 'location' : undefined}
          href="#results-exports"
        >
          <Download size={16} /> Results & Exports <ChevronRight size={14} />
        </a>

        <div className="sidebar-label" style={{ marginTop: '16px' }}>
          VERIFICATION
        </div>

        <a
          className={`nav-item ${section === '#ledger' ? 'active' : ''}`}
          aria-current={section === '#ledger' ? 'location' : undefined}
          href="#ledger"
        >
          <Clock3 size={16} /> Forecast Ledger
        </a>

        <a
          className={`nav-item ${section === '#method' ? 'active' : ''}`}
          aria-current={section === '#method' ? 'location' : undefined}
          href="#method"
        >
          <ShieldCheck size={16} /> Method & Limits
        </a>

        <div className="sidebar-bottom">
          <span className="live-dot" /> LOCAL ENVIRONMENT
          <p>
            Retrospective research.
            <br />
            No clinical decisions.
          </p>
          <span className="version">GLUCOTWIN · STAGE 06</span>
        </div>
      </aside>

      {/* Main Content Area */}
      <main>
        {/* Top Header Bar */}
        <header className="topbar">
          <div className="topbar-breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <b>
              {isScenarioLabView
                ? 'Scenario Lab'
                : isSessionLibraryView
                ? 'Session Library'
                : isResultsExportsView
                ? 'Results & Exports'
                : 'Replay Workspace'}
            </b>
          </div>

          <div className="topbar-actions">
            <Help />
            <span className="local-tag">
              <span className="live-dot" /> Local session
            </span>
          </div>
        </header>

        {/* Section Heading */}
        <section className="heading">
          <div>
            <div className="eyebrow">
              {isScenarioLabView
                ? 'RESEARCH SYNTHETICS / SCENARIO LAB'
                : isSessionLibraryView
                ? 'LOCAL REPLAY STORAGE / SESSION LIBRARY'
                : isResultsExportsView
                ? 'RESULTS EVALUATION / SYNTHETIC EXPORTS'
                : 'LOCAL RESEARCH / REPLAY WORKSPACE'}
            </div>
            <h1>
              {isScenarioLabView
                ? 'Synthetic Scenario Lab'
                : isSessionLibraryView
                ? 'Session Library'
                : isResultsExportsView
                ? 'Research Results & Exports'
                : 'Explore the signal.'}
            </h1>
            <p>
              {isScenarioLabView
                ? 'Reproduce, inspect, and launch 9 versioned synthetic scenarios.'
                : isSessionLibraryView
                ? 'Manage local replays, review retained historical summaries, or recreate configurations.'
                : isResultsExportsView
                ? 'Verify per-variant error statistics and download permitted synthetic datasets.'
                : 'Revealed history. Fixed forecasts. Transparent outcomes.'}
            </p>
          </div>

          <span className={`mode-badge ${mode}`}>
            <FlaskConical size={14} />
            {mode === 'synthetic' ? 'INDEPENDENT SYNTHETIC' : 'PROCESSED-DATA REPLAY'}
          </span>
        </section>

        {/* Persistent Disclosure Banner */}
        <div className="disclosure">
          <ShieldCheck size={16} />
          <p>
            {snapshot?.disclosure ??
              selected?.disclosure ??
              'Synthetic scenario demonstration. No real patient readings. Not a validated physiological simulator.'}
          </p>
        </div>

        {/* Navigation Tabs Bar */}
        <nav className="feature-nav" aria-label="Research destinations">
          <a
            href="#replay"
            className={!isScenarioLabView && !isSessionLibraryView && !isResultsExportsView && section !== '#ledger' && section !== '#method' ? 'active' : ''}
            aria-current={!isScenarioLabView && !isSessionLibraryView && !isResultsExportsView && section !== '#ledger' && section !== '#method' ? 'location' : undefined}
          >
            Replay Workspace
          </a>
          <a href="#scenario-lab" className={isScenarioLabView ? 'active' : ''} aria-current={isScenarioLabView ? 'location' : undefined}>
            Scenario Lab
          </a>
          <a href="#session-library" className={isSessionLibraryView ? 'active' : ''} aria-current={isSessionLibraryView ? 'location' : undefined}>
            Session Library
          </a>
          <a href="#session-summary" className={isResultsExportsView ? 'active' : ''} aria-current={isResultsExportsView ? 'location' : undefined}>
            Results & Exports
          </a>
          <a href="#ledger" className={section === '#ledger' ? 'active' : ''} aria-current={section === '#ledger' ? 'location' : undefined}>
            Forecast Ledger
          </a>
        </nav>

        {/* DEDICATED DESTINATION: SCENARIO LAB (When #scenario-lab active) */}
        {isScenarioLabView && (
          <div className="scenario-lab-workspace">
            <section className="configuration-card" aria-labelledby="scenario-lab">
              <div className="configuration-heading">
                <div>
                  <div className="eyebrow">CONFIGURED RUNTIME</div>
                  <h2 id="scenario-lab" className="section-title">
                    Scenario Setup & Parameters
                  </h2>
                </div>
                <span className="configuration-hint">
                  {source === 'synthetic-dawn' ? 'Seeded inputs / fixed forecasts' : 'Processed inputs / fixed references'}
                </span>
              </div>

              <section className="setup" aria-label="Replay configuration" aria-busy={busy}>
                <label>
                  Source
                  <select
                    disabled={busy}
                    aria-label="Source"
                    value={source}
                    onChange={e => {
                      setSource(e.target.value);
                      setScenario(current => scenarioForSource(e.target.value, current));
                    }}
                  >
                    {sources.map(s => (
                      <option key={s.id} value={s.id} disabled={!s.available}>
                        {s.label}
                        {s.available ? '' : ` · ${reason(s.reason ?? 'unavailable')}`}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Input scenario
                  <select disabled={busy} aria-label="Input scenario" value={scenario} onChange={e => setScenario(e.target.value)}>
                    {(catalog.length
                      ? catalog.filter(c => source === 'synthetic-dawn' || ['clean', 'dropout15', 'dropout30', 'dropout60', 'dropout120'].includes(c.id))
                      : [{ id: 'clean', name: 'Scripted day', description: '' }]
                    ).map(c => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Session start
                  <select disabled={busy} aria-label="Session start" value={start} onChange={e => setStart(e.target.value)}>
                    <option value="warm">Warm start · earlier events processed</option>
                    <option value="full">Full chronological session</option>
                  </select>
                </label>

                <button className="primary create" onClick={() => void create()} disabled={busy || !selected?.available}>
                  {busy ? 'Preparing…' : snapshot ? 'Create new session' : 'Create session'}
                  <ArrowRight size={15} />
                </button>
              </section>

              <div className="scenario-settings">
                <label>
                  Reproducible seed
                  <input
                    aria-label="Reproducible seed"
                    type="number"
                    min={0}
                    max={2147483647}
                    step={1}
                    value={seed}
                    disabled={busy || source !== 'synthetic-dawn'}
                    onChange={e => setSeed(Number(e.target.value))}
                  />
                </label>

                <label>
                  Duration (minutes)
                  <input
                    aria-label="Duration minutes"
                    type="number"
                    min={360}
                    max={1440}
                    step={5}
                    value={duration}
                    disabled={busy || source !== 'synthetic-dawn'}
                    onChange={e => setDuration(Number(e.target.value))}
                  />
                </label>

                <p>
                  {source !== 'synthetic-dawn' ? (
                    'Private replay uses both frozen sensor-only Ridge variants. Seed and duration settings are fixed.'
                  ) : (
                    <>
                      {catalog.find(c => c.id === scenario)?.description} Independent authored scenarios; not validated physiology.
                      Predictor: persistence. Generator:{' '}
                      {['steady', 'meal', 'activity', 'noisy'].includes(scenario) ? 'scenario-lab-v1' : 'scripted-v1'}.
                    </>
                  )}
                </p>
              </div>

              <ScenarioDetails configuration={snapshot?.configuration ?? null} />

              <p className="setup-note" role="status">
                {loadingSources
                  ? 'Discovering available sources…'
                  : busy
                  ? `${operation} / ${busySeconds}s elapsed. Controls are temporarily locked; no future targets are exposed.`
                  : start === 'warm'
                  ? 'Warm start processes earlier arrivals, forecasts and scores chronologically (synthetic: 120 min; local: through calibration and history rebuilding).'
                  : 'Full chronology begins at minute zero. Forecasts require 61 valid minute cells spanning 60 minutes.'}
              </p>
            </section>

            {/* 9 Reproducible Scenarios Grid */}
            <div className="eyebrow" style={{ marginTop: '24px' }}>
              CATALOG OF 9 REPRODUCIBLE SCENARIOS
            </div>
            <div className="scenario-catalog-grid">
              {SCENARIO_CATALOG_DATA.map(item => {
                const isCurrent = scenario === item.id;
                return (
                  <div
                    key={item.id}
                    className={`scenario-card ${isCurrent ? 'active' : ''}`}
                    onClick={() => setScenario(item.id)}
                    tabIndex={0}
                    role="button"
                    onKeyDown={e => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setScenario(item.id);
                      }
                    }}
                  >
                    <div className="scenario-card-header">
                      <h3 className="scenario-card-title">{item.name}</h3>
                      <span className={`scenario-badge ${item.loss > 0 ? 'loss' : ''}`}>{item.badge}</span>
                    </div>

                    <p className="scenario-card-desc">{item.desc}</p>

                    <div className="scenario-card-meta">
                      <span>
                        Gen: <b>{item.version}</b>
                      </span>
                      <span>
                        Loss: <b>{item.loss > 0 ? `${item.loss} min` : 'None'}</b>
                      </span>
                      <span>
                        Seed: <b>{seed}</b>
                      </span>
                      <span>
                        Target: <b>+30 min</b>
                      </span>
                    </div>

                    <button
                      className="primary"
                      style={{ marginTop: '8px', width: '100%' }}
                      onClick={e => {
                        e.stopPropagation();
                        setScenario(item.id);
                        void create();
                      }}
                      disabled={busy}
                    >
                      {isCurrent ? 'Run Selected Scenario' : 'Select & Launch'}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* SETUP FORM FOR REPLAY WORKSPACE (Always available so user can adjust or scripts can select) */}
        {!isScenarioLabView && (
          <section className="configuration-card" aria-labelledby="scenario-lab">
            <div className="configuration-heading">
              <div>
                <div className="eyebrow">ACTIVE REPLAY CONFIGURATION</div>
                <h2 id="scenario-lab" className="section-title">
                  Scenario Setup
                </h2>
              </div>
              <span className="configuration-hint">
                {source === 'synthetic-dawn' ? 'Seeded inputs / fixed forecasts' : 'Processed inputs / fixed references'}
              </span>
            </div>

            <section className="setup" aria-label="Replay configuration" aria-busy={busy}>
              <label>
                Source
                <select
                  disabled={busy}
                  aria-label="Source"
                  value={source}
                  onChange={e => {
                    setSource(e.target.value);
                    setScenario(current => scenarioForSource(e.target.value, current));
                  }}
                >
                  {sources.map(s => (
                    <option key={s.id} value={s.id} disabled={!s.available}>
                      {s.label}
                      {s.available ? '' : ` · ${reason(s.reason ?? 'unavailable')}`}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Input scenario
                <select disabled={busy} aria-label="Input scenario" value={scenario} onChange={e => setScenario(e.target.value)}>
                  {(catalog.length
                    ? catalog.filter(c => source === 'synthetic-dawn' || ['clean', 'dropout15', 'dropout30', 'dropout60', 'dropout120'].includes(c.id))
                    : [{ id: 'clean', name: 'Scripted day', description: '' }]
                  ).map(c => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Session start
                <select disabled={busy} aria-label="Session start" value={start} onChange={e => setStart(e.target.value)}>
                  <option value="warm">Warm start · earlier events processed</option>
                  <option value="full">Full chronological session</option>
                </select>
              </label>

              <button className="primary create" onClick={() => void create()} disabled={busy || !selected?.available}>
                {busy ? 'Preparing…' : snapshot ? 'Create new session' : 'Create session'}
                <ArrowRight size={15} />
              </button>
            </section>

            <div className="scenario-settings">
              <label>
                Reproducible seed
                <input
                  aria-label="Reproducible seed"
                  type="number"
                  min={0}
                  max={2147483647}
                  step={1}
                  value={seed}
                  disabled={busy || source !== 'synthetic-dawn'}
                  onChange={e => setSeed(Number(e.target.value))}
                />
              </label>

              <label>
                Duration (minutes)
                <input
                  aria-label="Duration minutes"
                  type="number"
                  min={360}
                  max={1440}
                  step={5}
                  value={duration}
                  disabled={busy || source !== 'synthetic-dawn'}
                  onChange={e => setDuration(Number(e.target.value))}
                />
              </label>

              <p>
                {source !== 'synthetic-dawn' ? (
                  'Private replay uses both frozen sensor-only Ridge variants. Seed and duration settings are fixed.'
                ) : (
                  <>
                    {catalog.find(c => c.id === scenario)?.description} Independent authored scenarios; not validated physiology.
                    Predictor: persistence. Generator:{' '}
                    {['steady', 'meal', 'activity', 'noisy'].includes(scenario) ? 'scenario-lab-v1' : 'scripted-v1'}.
                  </>
                )}
              </p>
            </div>

            <ScenarioDetails configuration={snapshot?.configuration ?? null} />

            <p className="setup-note" role="status">
              {loadingSources
                ? 'Discovering available sources…'
                : busy
                ? `${operation} / ${busySeconds}s elapsed. Controls are temporarily locked; no future targets are exposed.`
                : start === 'warm'
                ? 'Warm start processes earlier arrivals, forecasts and scores chronologically (synthetic: 120 min; local: through calibration and history rebuilding).'
                : 'Full chronology begins at minute zero. Forecasts require 61 valid minute cells spanning 60 minutes.'}
            </p>
          </section>
        )}

        {/* Global Error Banner */}
        {(error || pollError) && (
          <div className="error" role="alert">
            <b>{expired ? 'Session expired' : 'Request unavailable'}</b>
            <p>{error || pollError}</p>
            {expired ? (
              <button onClick={() => void create()} disabled={busy}>
                Create a new replay
              </button>
            ) : (
              <button onClick={loadSources} disabled={loadingSources}>
                Retry connection
              </button>
            )}
          </div>
        )}

        {/* REPLAY WORKSPACE PRIMARY CONTROLS & CENTERPIECE CHART */}
        {(!isScenarioLabView && !isSessionLibraryView && !isResultsExportsView) && (
          <>
            {/* Replay Controls Toolbar */}
            <section className="transport" aria-label="Playback controls">
              <div className="transport-actions">
                <button
                  className="play"
                  disabled={!snapshot || busy || expired || snapshot.status === 'ended'}
                  onClick={() => void control(snapshot?.status === 'running' ? 'pause' : 'start')}
                >
                  {snapshot?.status === 'running' ? <Pause size={16} /> : <Play size={16} />}
                  {snapshot?.status === 'running' ? 'Pause' : 'Start / resume'}
                </button>

                <button
                  disabled={!snapshot || busy || expired || snapshot.status === 'running' || snapshot.status === 'ended'}
                  onClick={() => void control('step')}
                >
                  <SkipForward size={16} />
                  Step 5 min
                </button>

                <button aria-label="Reset replay" disabled={!snapshot || busy || expired} onClick={() => void reset()}>
                  <RotateCcw size={15} />
                  <span>Reset</span>
                </button>
              </div>

              <div className="speed" aria-label="Playback speed">
                {[1, 60, 300].map(n => (
                  <button
                    key={n}
                    aria-label={`Playback speed ${n}x`}
                    aria-pressed={snapshot?.speed === n}
                    disabled={!snapshot || busy || expired}
                    className={snapshot?.speed === n ? 'selected' : ''}
                    onClick={() => void control('speed', n)}
                  >
                    {n}×
                  </button>
                ))}
              </div>

              <div className="replay-clock">
                <span className={snapshot?.status === 'running' ? 'running-dot' : 'paused-dot'} />
                <span>
                  {snapshot?.status ?? 'No session'}
                  <b>{snapshot ? time(snapshot.virtual_time) : '—'}</b>
                </span>
              </div>
            </section>

            {/* Timeline & Phase Bar */}
            <div className="phase-line">
              <span>
                <span className="tiny-label">PHASE</span> {snapshot?.phase ?? 'Ready to replay'}
                {snapshot?.mode === 'local'
                  ? ` / matured pairs: offset ${snapshot.phase_counts.offset}, calibration ${snapshot.phase_counts.calibration}`
                  : ''}
                {snapshot?.warm_start ? ' · warm start processed chronologically' : ''}
              </span>
              <span>
                {snapshot ? `${Math.floor(snapshot.elapsed_minutes)} / ${snapshot.end_minutes} elapsed min` : 'Choose a source to begin'}
              </span>
            </div>

            <progress
              className="replay-progress"
              aria-label="Replay timeline progress"
              value={snapshot?.elapsed_minutes ?? 0}
              max={snapshot?.end_minutes ?? 721}
            />

            {/* History Support & Recovery Explanation */}
            <section className="panel recovery-panel" aria-label="History support and recovery tracking">
              <div className="recovery-header">
                <div className="recovery-title-group">
                  <div className="recovery-eyebrow">HISTORY SUPPORT &amp; RECOVERY STATUS</div>
                  <div className="recovery-summary-line">
                    <span className="recovery-label">Required Support:</span>
                    <strong>61 consecutive minute cells spanning 60 elapsed minutes</strong>
                    <span className="recovery-sep">·</span>
                    <span className="recovery-label">Current trailing-window support:</span>
                    <strong>
                      {snapshot?.recovery
                        ? `${snapshot.recovery.available_valid_cells} of 61 valid cells in trailing window; continuous support spans ${snapshot.recovery.support_span_minutes} of 60 elapsed min`
                        : 'Awaiting session creation'}
                    </strong>
                  </div>
                </div>
                <div className="recovery-badge-group">
                  <span className={`recovery-badge ${snapshot?.recovery?.is_suppressed ? 'suppressed' : 'active'}`}>
                    {!snapshot ? 'Awaiting session creation' : snapshot.recovery?.is_suppressed ? 'History incomplete' : 'History requirement satisfied'}
                  </span>
                </div>
              </div>

              {snapshot?.recovery && <p>Continuous run: {snapshot.recovery.consecutive_valid_cells} valid processed minute cells spanning {snapshot.recovery.consecutive_valid_minutes} elapsed minutes.</p>}
              <div className="recovery-details-grid">
                <div className="recovery-detail-item">
                  <span className="recovery-detail-label">Next scheduled issue / history support</span>
                  <span className="recovery-detail-val">
                    {snapshot?.recovery?.next_issue_minute != null
                      ? `Minute ${snapshot.recovery.next_issue_minute} (${time(snapshot.recovery.next_issue_time!)}) · ${snapshot.recovery.next_issue_eligible ? 'History support conditionally sufficient; predictor not yet assessed' : 'History rebuilding; forecast not promised'}`
                      : snapshot ? 'No future issue scheduled in this session.' : 'Awaiting session creation'}
                  </span>
                </div>

                <div className="recovery-detail-item">
                  <span className="recovery-detail-label">Suppression Status &amp; Reason</span>
                  <span className="recovery-detail-val">
                    {snapshot?.recovery?.suppression_message ?? (snapshot ? 'History requirement satisfied.' : 'Awaiting session creation.')}
                  </span>
                </div>

                <div className="recovery-detail-item recovery-detail-estimate">
                  <span className="recovery-detail-label">Conditional Recovery Estimate</span>
                  <span className="recovery-detail-val recovery-estimate-highlight">
                    {snapshot?.recovery?.conditional_recovery_label ?? '—'}
                  </span>
                  <p className="recovery-boundary-disclaimer">
                    Calculated strictly from revealed history and 5-min issue grid without future-schedule knowledge. Any missing reading resets consecutive support and immediately voids this estimate.
                  </p>
                </div>
              </div>
            </section>

            {/* 4 Key Metric Cards */}
            <section className="stat-grid">
              <article className="stat">
                <div className="stat-label">
                  <Signal size={14} />
                  Latest accepted reading
                </div>
                <div className="stat-number">
                  {number(last?.value)} <small>mg/dL</small>
                </div>
                <p>
                  {last
                    ? `Measured ${time(last.measurement_time)} · age ${number(last.age_minutes, 1)} min`
                    : 'Waiting for an accepted reading'}
                </p>
              </article>

              <article className="stat">
                <div className="stat-label">
                  <ArrowRight size={14} />
                  Latest scheduled forecast
                </div>
                {latest.size ? [...latest.values()].map(f => <IssuedForecast key={f.variant} forecast={f} />)
                  : <p>No scheduled forecast has been issued yet.</p>}
              </article>

              <article className="stat">
                <div className="stat-label">
                  <Clock3 size={14} />
                  Scored-origin accuracy
                </div>
                {summaries.length ? summaries.map(s => <div key={s.variant}>
                  <div className="stat-number">{number(s.mae)} <small>MAE · mg/dL</small></div>
                  <p>{label(s.variant)} / {s.scored} scored / {s.matured} matured forecasts</p>
                </div>) : <p>Scores appear only after target maturity</p>}
              </article>

              <article className="stat">
                <div className="stat-label">
                  <Database size={14} />
                  Forecast availability
                </div>
                {summaries.length ? summaries.map(s => <div key={s.variant}>
                  <div className="stat-number">{s.scheduled ? number(s.issued / s.scheduled * 100, 1) : '—'}<small>%</small></div>
                  <p>{label(s.variant)}: {s.issued} issued / {s.scheduled} scheduled</p>
                </div>) : <p>Independent of scoring availability</p>}
              </article>
            </section>

            {/* VISUAL CENTERPIECE: MAIN GLUCOSE CHART & PREDICTION PANEL */}
            <div className="content-grid">
              <section className="panel signal-panel">
                <div className="panel-heading">
                  <div>
                    <div className="eyebrow">REVEALED HISTORY</div>
                    <h2>The signal & the endpoint</h2>
                  </div>
                  <span className="unit-tag">1 min readings</span>
                </div>

                <Chart
                  key={snapshot ? `${snapshot.session_id}:${snapshot.generation}` : 'empty'}
                  snapshot={snapshot}
                  alpha={alpha}
                  onInspect={openInspector}
                  gate={polling.current}
                />

                <div className="chart-key">
                  <span>
                    <i className="swatch green" />
                    Revealed readings
                  </span>
                  {snapshot?.mode === 'local' ? (
                    <>
                      <span>
                        <i className="swatch amber" />
                        Unadapted endpoint
                      </span>
                      <span>
                        <i className="swatch purple" />
                        24h offset endpoint
                      </span>
                    </>
                  ) : (
                    <span>
                      <i className="swatch amber" />
                      Forecast endpoint
                    </span>
                  )}
                  <span className="chart-note">Separate historical endpoints · focus/hover for details</span>
                </div>

                <div className="chart-foot">
                  <Clock3 size={13} />
                  <span>
                    Artificial UTC session clock. {snapshot?.mode === 'local' ? 'Source timezone unknown.' : 'Synthetic minute grid.'}{' '}
                    Zero assumed arrival delay.
                  </span>
                </div>
              </section>

              {/* Research Comparison & Forecast Panel */}
              <section className="panel prediction-panel">
                <div className="panel-heading">
                  <div>
                    <div className="eyebrow">RESEARCH COMPARISON</div>
                    <h2>Latest forecast issue</h2>
                  </div>
                </div>

                {/* Mode-Specific Capability Consolidation */}
                <div className="capability-card" aria-label="Mode capability and active source profile">
                  <div className="capability-top-bar">
                    <span className="capability-mode-badge">
                      {snapshot ? (snapshot.mode === 'synthetic' ? 'INDEPENDENT SYNTHETIC' : 'RETROSPECTIVE REPLAY') : 'NO SESSION'}
                    </span>
                    <span className="capability-horizon-badge">Horizon: +30 min</span>
                  </div>

                  <div className="capability-source-alignment">
                    <div className="source-alignment-row">
                      <span className="cap-meta-label">Active Session:</span>
                      <span className="cap-meta-val">
                        {snapshot
                          ? (sources.find(s => s.id === snapshot.source_id)?.label ?? (snapshot.mode === 'synthetic' ? 'Scripted day / independent synthetic' : 'Local processed stream'))
                          : 'No active session'}
                      </span>
                    </div>
                    {snapshot && source !== snapshot.source_id && (
                      <div className="source-alignment-row mismatch">
                        <span className="cap-meta-label">Configured in Dropdown:</span>
                        <span className="cap-meta-val">
                          {sources.find(s => s.id === source)?.label ?? source}
                          <span className="pending-badge">Pending (applies to next session)</span>
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="capability-grid">
                    <div className="cap-item">
                      <span className="cap-label">Predictor</span>
                      <span className="cap-val">
                        {snapshot?.mode === 'local'
                          ? 'Ridge Regression baseline'
                          : 'Scripted Persistence baseline (zero-order hold)'}
                      </span>
                    </div>
                    <div className="cap-item">
                      <span className="cap-label">Variants</span>
                      <span className="cap-val">
                        {snapshot?.mode === 'local'
                          ? snapshot.availability?.map(v=>label(v.variant)).join(', ') ?? 'Sensor-only'
                          : 'persistence (sensor-only baseline)'}
                      </span>
                    </div>
                    <div className="cap-item full-width">
                      <span className="cap-label">Point availability and interval readiness by variant</span>
                      <Availability snapshot={snapshot} />
                    </div>
                    <div className="cap-item full-width">
                      <span className="cap-label">Evaluation Status</span>
                      <span className="cap-val">
                        {snapshot?.mode === 'local'
                          ? 'Retrospective benchmark evaluation (delayed ground-truth scoring at +30m target maturity)'
                          : 'Synthetic demonstration (scripted reference comparison; no patient data)'}
                      </span>
                    </div>
                  </div>

                  <div className="evidence-boundary-note">
                    <strong>Evidence Boundary: </strong>
                    <span>
                      {snapshot?.mode === 'local'
                        ? 'Retrospective replay on processed dataset. Arrival times are assumed under artificial UTC clock; values reflect upstream interpolation. Research prototype only — no live sensor connection, treatment advice, or event probability predictions.'
                        : 'Synthetic benchmark simulation. Model uses scripted persistence without patient-trained weights; interval calibration is not performed and interval bounds remain unavailable. Not a physiological simulator.'}
                    </span>
                  </div>
                </div>

                <div className="nominal">
                  <div className="nominal-label-wrap">
                    <span>Nominal interval</span>
                    {snapshot?.mode === 'synthetic' && (
                      <span className="nominal-unavailable-hint">(Unavailable in Synthetic)</span>
                    )}
                  </div>
                  <div>
                    {['0.10', '0.05'].map(a => (
                      <button
                        key={a}
                        className={alpha === a ? 'chosen' : ''}
                        aria-pressed={alpha === a}
                        onClick={() => setAlpha(a)}
                      >
                        {a === '0.10' ? '90%' : '95%'}
                      </button>
                    ))}
                  </div>
                </div>

                {latest.size ? (
                  [...latest.values()].map(f => {
                    const interval = f.intervals.find(i => i.alpha === alpha);
                    return (
                      <div className="prediction" key={f.variant}>
                        <div className="prediction-title">
                          {label(f.variant)}
                          <span className={f.value === null ? 'unavailable' : 'available'}>
                            {f.value === null ? 'Unavailable' : 'Issued'}
                          </span>
                        </div>

                        <div className="prediction-value">
                          {number(f.value)}
                          <small>mg/dL</small>
                        </div>

                        <p>
                          {f.value === null ? reason(f.point_reason) : `Origin ${time(f.origin_time)} → target ${time(f.target_time)}`}
                        </p>

                        <div className="interval-line">
                          {interval?.lower != null
                            ? `${number(interval.lower)} – ${number(interval.upper)} mg/dL`
                            : 'Interval unavailable'}
                          <small>
                            {interval?.reason === 'OK'
                              ? 'Nominal band, not an individual probability'
                              : reason(interval?.reason ?? f.point_reason)}
                          </small>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="empty">
                    <FlaskConical size={26} />
                    <p>Create a session to inspect its predictor and availability.</p>
                  </div>
                )}

                <p className="prediction-note">
                  {mode === 'synthetic'
                    ? 'Persistence uses the latest accepted value. No patient-trained weights or patient interval quantiles are loaded.'
                    : 'Each model/variant is shown independently. Sensor-only remains the default; no target-dependent switching.'}
                </p>
              </section>
            </div>
          </>
        )}

        {/* AVAILABILITY ACCOUNTING TABLE (Shown on Replay Workspace or Results destination) */}
        {(!isScenarioLabView && !isSessionLibraryView) && (
          <section className="panel accounting" aria-label="Availability accounting">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">SEPARATE DENOMINATORS</div>
                <h2>Availability & scoring</h2>
              </div>
            </div>

            {snapshot?.summaries.map(s => (
              <div className="account-row" key={s.variant}>
                <h3>{label(s.variant)}</h3>
                <dl>
                  {[
                    ['Scheduled origins', s.scheduled],
                    ['Issued points', s.issued],
                    ['Available intervals', s.interval_available],
                    ['Scored points', s.scored],
                    ['Pending issued points', s.pending],
                    ['Missing exact targets', s.missing_targets]
                  ].map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
                <p>
                  Mean signed error {number(s.mean_signed_error)} mg/dL. Scoring availability{' '}
                  {s.scoring_availability == null ? 'unavailable' : number(s.scoring_availability * 100) + '%'} (scored / issued).
                  MAE uses {s.scored} scored points. Interval availability counts issues with any available nominal band.{' '}
                  {s.coverage_denominators[alpha] > 0 && s.empirical_coverage[alpha] != null ? (
                    <>
                      Empirical {alpha === '0.10' ? '90%' : '95%'} coverage:{' '}
                      {number(s.empirical_coverage[alpha]! * 100)}% / {s.coverage_denominators[alpha]} scored intervals.{' '}
                    </>
                  ) : (
                    <>
                      {snapshot.mode === 'synthetic'
                        ? 'Intervals unavailable in synthetic mode (no synthetic interval calibration). '
                        : 'Intervals not yet evaluated for empirical coverage. '}
                    </>
                  )}
                  {snapshot.mode === 'local' ? 'Evaluation phase only.' : 'Synthetic scenario only; not patient accuracy.'}
                </p>
              </div>
            )) ?? <p className="setup-note">No session yet. Counts appear after session preparation.</p>}
          </section>
        )}

        {/* DEDICATED FEATURE PANELS (Session Library & Exports) */}
        {(!isScenarioLabView) && (
          <FeaturePanels snapshot={snapshot} busy={busy} onRecreate={id => void create(id)} />
        )}

        {/* FORECAST LEDGER & RESEARCH LIMITATIONS */}
        {(!isScenarioLabView && !isSessionLibraryView) && (
          <div className="lower-grid">
            <section className="panel ledger" id="ledger">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">IMMUTABLE FORECAST EVENTS</div>
                  <h2>Forecast ledger</h2>
                </div>
                <span className="count-badge">{snapshot?.forecast_count ?? 0} events</span>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Origin → target</th>
                      <th>Predictor</th>
                      <th>Forecast</th>
                      <th>Observed</th>
                      <th>Scoring state</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot?.forecasts
                      .slice(-12)
                      .reverse()
                      .map(f => (
                        <tr key={f.id}>
                          <td>
                            <button
                              className="inspect-link"
                              onClick={() => openInspector(f)}
                              aria-label={`Inspect forecast ${time(f.origin_time)} ${f.variant}`}
                            >
                              {time(f.origin_time)}
                            </button>{' '}
                            <span>→</span> {time(f.target_time)}
                          </td>
                          <td>{label(f.variant)}</td>
                          <td>{number(f.value)}</td>
                          <td>{number(f.score?.observed)}</td>
                          <td>
                            <span className={f.score?.reason === 'OK' ? 'state matured' : 'state'}>
                              {f.score
                                ? f.score.reason === 'OK'
                                  ? 'Matured'
                                  : f.value === null
                                  ? 'No point issued'
                                  : 'Target unavailable'
                                : f.value === null
                                ? 'No point; target pending'
                                : 'Pending target'}
                            </span>
                            {f.score && f.score.reason !== 'OK' && (
                              <details className="reason-details">
                                <summary>Reason</summary>
                                {reason(f.score.reason)}
                              </details>
                            )}
                          </td>
                        </tr>
                      )) ?? null}
                  </tbody>
                </table>
                {!snapshot && <div className="ledger-empty">Your replay ledger will appear here.</div>}
              </div>

              <div className="ledger-foot">
                Only matured targets are revealed. Latest 12 records shown from a bounded snapshot.
              </div>
            </section>

            {/* Research Context & Limitations Section */}
            <section className="panel limitations" id="method">
              <details open>
                <summary>Research context & limitations</summary>
                <div className="panel-heading">
                  <div>
                    <div className="eyebrow">READ THE CONTEXT</div>
                    <h2>Research, with limits.</h2>
                  </div>
                  <TriangleAlert size={18} />
                </div>
                <p>Processed-cohort outcomes have already been examined. Evaluation remains exploratory.</p>
                <ul>
                  <li>Nominal 90% / 95% coverage was not fully achieved in Stage 5.</li>
                  <li>Adaptation worsened errors and underprediction above 180 mg/dL.</li>
                  <li>Observations below 70 mg/dL are sparse.</li>
                  <li>Upstream interpolation and actual availability remain unresolved.</li>
                </ul>
                <div className="not-clinical">No clinical alarms, dosing or treatment recommendations.</div>
                {snapshot?.gap && (
                  <div className="gap-note">
                    <b>Synthetic input-loss schedule</b>
                    {time(snapshot.gap.start_time)}–{time(snapshot.gap.end_time)} · half-open input gap. Evaluator retains
                    reference targets.
                  </div>
                )}
              </details>
            </section>
          </div>
        )}

        {/* Accessible Forecast Inspector Modal Dialog */}
        {inspected && (
          <ForecastInspector forecast={inspected.forecast} cutoff={inspected.cutoff} onClose={closeInspector} />
        )}

        {/* Master Footer */}
        <footer>
          <span>GlucoTwin / Local research workspace</span>
          <span>No live sensor connection · No coverage guarantees</span>
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
