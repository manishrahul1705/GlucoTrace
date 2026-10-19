import { useEffect, useRef, useState } from 'react';
import type { Forecast, Snapshot, ScenarioConfiguration, LibraryItem } from './types';
import { reasonDetail } from './reasons';
import { ExclusiveAction, LatestRequest, displayNameProblem } from './actions';

export async function labApi<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch('/api/replay' + path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(30000)
  });
  const data = await r.json();
  if (!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Request unavailable');
  return data;
}

const fmt = (n: number | null | undefined) => (n == null ? 'Unavailable' : n.toFixed(2));

export function ForecastInspector({
  forecast,
  cutoff,
  onClose
}: {
  forecast: Forecast;
  cutoff: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
    };
  }, []);

  const f = forecast;

  return (
    <dialog
      ref={dialog}
      className="inspector"
      aria-labelledby="inspector-title"
      onCancel={e => {
        e.preventDefault();
        onClose();
      }}
      onClick={e => {
        if (e.target === dialog.current) {
          onClose();
        }
      }}
    >
      <div className="inspector-header">
        <div>
          <div className="eyebrow">IMMUTABLE ISSUE · {f.phase.toUpperCase()}</div>
          <h2 id="inspector-title">Forecast inspector</h2>
        </div>
        <button onClick={onClose} aria-label="Close inspector">
          Close ×
        </button>
      </div>

      <p className="inspection-cutoff">
        As-of cutoff: {cutoff}. This view stays fixed; close and reopen to refresh.
      </p>

      <dl className="inspector-data">
        <dt>Predictor</dt>
        <dd>{f.variant}</dd>

        <dt>Origin</dt>
        <dd>{f.origin_time}</dd>

        <dt>Exact t+30 target</dt>
        <dd>{f.target_time}</dd>

        <dt>Point forecast</dt>
        <dd>{f.value == null ? reasonDetail(f.point_reason) : `${fmt(f.value)} mg/dL`}</dd>

        {f.endpoint_flags?.map(flag=><div key={flag.threshold_mg_dl}><dt>Endpoint &gt;{flag.threshold_mg_dl} mg/dL (+30 minutes)</dt><dd>{flag.flag_status}; target {flag.target_status}; {flag.confusion??'outcome unavailable'}</dd></div>)}

        <dt>Required history</dt>
        <dd>
          {f.history_start} → {f.history_end}
          <br />
          {f.history_count} accepted / 61 required minute cells, spanning 60 elapsed minutes
        </dd>

        <dt>Artifact identity at issue</dt>
        <dd>{f.artifact_identity}</dd>

        <dt>Scoring status</dt>
        <dd>
          {!f.score
            ? 'Pending target'
            : f.score.reason === 'OK'
            ? 'Scored'
            : reasonDetail(f.score.reason)}
        </dd>

        {f.score && (
          <>
            <dt>Revealed target</dt>
            <dd>{fmt(f.score.observed)} mg/dL</dd>

            <dt>Signed error (prediction − target)</dt>
            <dd>{fmt(f.score.signed_error)} mg/dL</dd>

            <dt>Absolute error</dt>
            <dd>
              {fmt(f.score.signed_error == null ? null : Math.abs(f.score.signed_error))} mg/dL
            </dd>
          </>
        )}
      </dl>

      <h3>Nominal intervals at issue</h3>
      {f.intervals.map(i => (
        <p key={i.alpha} className="interval-spec">
          <b>{i.alpha === '0.10' ? '90%' : '95%'}:</b>{' '}
          {i.lower == null || i.upper == null
            ? reasonDetail(i.reason)
            : `${fmt(i.lower)} – ${fmt(i.upper)} mg/dL`}
        </p>
      ))}

      <p className="setup-note">
        Targets appear only after maturity at the inspected cutoff. Historical inspection can retain
        a pending view. Intervals are nominal, not guaranteed outcome probabilities. Later
        calibration never revises this issue.
      </p>
    </dialog>
  );
}

function LibraryRow({
  item,
  current,
  onRename,
  onRecreate,
  onSummary
}: {
  item: LibraryItem;
  current: boolean;
  onRename: (id: string, name: string) => void;
  onRecreate: (id: string) => void;
  onSummary: (item: LibraryItem) => void;
}) {
  return (
    <article className="library-row" data-session-id={item.id} data-current={current}>
      <div className="library-item-heading">
        <span>
          {current ? 'Current replay / ' : ''}
          {item.mode === 'synthetic' ? 'Demo session' : 'Private research'}
        </span>
        <span className={`library-state ${item.status}`}>{item.status}</span>
      </div>

      <form
        onSubmit={e => {
          e.preventDefault();
          const input = e.currentTarget.elements.namedItem('name') as HTMLInputElement;
          const problem = displayNameProblem(input.value);
          input.setCustomValidity(problem ?? '');
          if (problem) {
            input.reportValidity();
            return;
          }
          onRename(item.id, input.value);
        }}
      >
        <label>
          Session display name
          <input
            name="name"
            aria-label={`Rename ${item.name}`}
            defaultValue={item.name}
            key={item.name}
            maxLength={80}
            required
            onInput={e => e.currentTarget.setCustomValidity('')}
          />
        </label>
        <button>Save name</button>
      </form>

      <p>
        {item.configuration?.name ?? 'Legacy configuration unavailable'} · seed{' '}
        {item.configuration?.seed ?? 'not retained'}
        <br />
        <time dateTime={item.created_at ?? undefined} title={item.created_at ?? undefined}>
          {item.created_at
            ? new Date(item.created_at).toLocaleString('en-GB', {
                day: '2-digit',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
                timeZone: 'UTC'
              }) + ' UTC'
            : 'Creation time not retained'}
        </time>
      </p>

      <div className="library-actions">
        <button onClick={() => onSummary(item)} disabled={!item.summary}>
          Read-only summary
        </button>
        <button disabled={!item.recreatable} onClick={() => onRecreate(item.id)}>
          Recreate scenario
        </button>
      </div>
    </article>
  );
}

export function FeaturePanels({
  snapshot,
  busy,
  onRecreate
}: {
  snapshot: Snapshot | null;
  busy: boolean;
  onRecreate: (id: string) => void;
}) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [working, setWorking] = useState(false);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [notice, setNotice] = useState('');
  const [actionLabel, setActionLabel] = useState('');

  const action = useRef(new ExclusiveAction());
  const requests = useRef(new LatestRequest());
  const identity = useRef('');
  identity.current = snapshot ? `${snapshot.session_id}:${snapshot.generation}` : 'empty';

  const refresh = async () => {
    const version = requests.current.begin();
    setLoadingLibrary(true);
    try {
      const data = await labApi<{ sessions: LibraryItem[] }>('/library?limit=20');
      if (
        !Array.isArray(data.sessions) ||
        data.sessions.some(i => typeof i.id !== 'string' || typeof i.name !== 'string')
      )
        throw Error('Invalid session library response');
      if (requests.current.accepts(version)) {
        setItems(data.sessions);
        setError('');
      }
    } catch (e) {
      if (requests.current.accepts(version)) setError((e as Error).message);
    } finally {
      if (requests.current.accepts(version)) setLoadingLibrary(false);
    }
  };

  const run = async (label: string, task: () => Promise<string>) => {
    await action.current.run(async () => {
      const owner = identity.current;
      setWorking(true);
      setActionLabel(label);
      setNotice('');
      setError('');
      try {
        const message = await task();
        if (owner === identity.current) setNotice(message);
      } catch (e) {
        if (owner === identity.current) setError((e as Error).message);
      } finally {
        setWorking(false);
        setActionLabel('');
      }
    });
  };

  useEffect(() => {
    setSelected(null);
    setNotice('');
    setError('');
    void refresh();
  }, [snapshot?.session_id, snapshot?.generation]);

  const rename = (id: string, name: string) =>
    run('Saving session name…', async () => {
      await labApi(`/library/${id}/rename`, { name });
      await refresh();
      return 'Session name saved.';
    });

  const showSummary = (item: LibraryItem) =>
    run('Loading retained summary…', async () => {
      const owner = identity.current;
      const result = await labApi<LibraryItem>(`/library/${item.id}`);
      if (owner !== identity.current) return '';
      setSelected(result);
      return 'Retained summary loaded. This view is read-only.';
    });

  const download = (kind: string) =>
    run('Preparing demo export…', async () => {
      if (!snapshot) return '';
      const r = await fetch(`/api/replay/sessions/${snapshot.session_id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          generation: snapshot.generation,
          kind,
          cutoff_minute: Math.floor(snapshot.elapsed_minutes)
        }),
        signal: AbortSignal.timeout(30000)
      });
      if (!r.ok) {
        const data = await r.json();
        throw Error(data.detail ?? 'Export unavailable');
      }
      const blob = await r.blob();
      if (blob.size > 2_000_000) throw Error('Export exceeded the supported size.');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `glucotrace-demo-${kind}.${
        ['configuration', 'summary'].includes(kind) ? 'json' : 'csv'
      }`;
      a.click();
      URL.revokeObjectURL(url);
      return `Demo ${kind} export prepared · cutoff ${snapshot.virtual_time}`;
    });

  const filteredItems = search.trim()
    ? items.filter(
        i =>
          i.name.toLowerCase().includes(search.toLowerCase()) ||
          i.configuration?.name.toLowerCase().includes(search.toLowerCase()) ||
          i.mode.toLowerCase().includes(search.toLowerCase())
      )
    : items;

  return (
    <div className="feature-panels">
      {/* Export & Summary Panel */}
      <section className="panel export-panel" id="session-summary">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">CURRENT / END-OF-SESSION</div>
            <h2>Summary & reproduction</h2>
          </div>
        </div>
        <div className="panel-body">
          <p>
            {snapshot
              ? `${snapshot.status === 'ended' ? 'Session ended' : 'Current replay'} · cutoff ${
                  snapshot.virtual_time
                }`
              : 'Create a session to begin.'}
          </p>
          <p>
            Downloads freeze the replay cutoff at the time of the request. Summary JSON retains
            per-variant counts and errors; unavailable values remain null.
          </p>
          <p>
            {snapshot?.mode === 'synthetic'
              ? 'Demo results, not patient accuracy. Intervals and coverage remain unavailable.'
              : 'Patient-backed downloads are disabled. No patient values, models or calibration artifacts can be exported here.'}
          </p>
          <div className="export-actions">
            {['configuration', 'readings', 'forecasts', 'scores', 'summary'].map(kind => (
              <button
                key={kind}
                disabled={!snapshot || snapshot.mode !== 'synthetic' || busy || working}
                onClick={() => void download(kind)}
              >
                Export demo {kind}
              </button>
            ))}
          </div>
          <p className="setup-note">
            Configuration JSON recreates a new runtime. CSVs and summary include synthetic
            provenance, seed, generator/export version, units, predictor and virtual cutoff. Pending
            targets remain blank.
          </p>
        </div>
      </section>

      {/* Session Library Panel */}
      <section className="panel library-panel" id="session-library" aria-busy={working || loadingLibrary}>
        <div className="panel-heading">
          <div>
            <div className="eyebrow">LOCAL DATABASE · RECENT REPLAYS</div>
            <h2>Session library</h2>
          </div>
          <button disabled={working || busy || loadingLibrary} onClick={() => void refresh()}>
            Refresh library
          </button>
        </div>
        <div className="panel-body">
          <p>
            Recreate a retained demo configuration as a new session. Restart expires runtimes;
            summaries and immutable evidence remain local.
          </p>
          {items.length > 3 && (
            <div style={{ margin: '8px 0 10px' }}>
              <input
                type="search"
                placeholder="Filter sessions by name or scenario…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ fontSize: '11px', minHeight: '32px' }}
                aria-label="Filter sessions"
              />
            </div>
          )}
          <p className="action-status" role="status" aria-live="polite">
            {working ? actionLabel : loadingLibrary ? 'Loading session library…' : notice}
          </p>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {!items.length && !loadingLibrary && (
            <p className="library-empty">
              No retained sessions yet. Create a replay to save its configuration here.
            </p>
          )}
          <fieldset disabled={working || busy || loadingLibrary} className="library-list">
            {filteredItems.map(item => (
              <LibraryRow
                key={item.id}
                item={item}
                current={item.id === snapshot?.session_id}
                onRename={(id, name) => void rename(id, name)}
                onRecreate={onRecreate}
                onSummary={i => void showSummary(i)}
              />
            ))}
          </fieldset>
          {selected && (
            <section className="retained-summary" aria-label="Retained session summary">
              <h3>{selected.name} · read-only</h3>
              <p>
                {selected.status} · evidence cutoff {selected.summary?.virtual_cutoff}
              </p>
              {selected.summary?.summaries.map(s => (
                <p key={s.variant}>
                  {s.variant}: {s.issued} issued / {s.scheduled} scheduled; {s.scored} scored,{' '}
                  {s.pending} pending, {s.missing_targets} missing targets. MAE {fmt(s.mae)}, mean
                  signed error {fmt(s.mean_signed_error)} mg/dL.
                </p>
              ))}
              <button onClick={() => setSelected(null)}>Close summary</button>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}

export function ScenarioDetails({ configuration }: { configuration: ScenarioConfiguration | null }) {
  return configuration ? (
    <details className="scenario-config">
      <summary>Active scenario configuration</summary>
      <dl>
        {Object.entries(configuration).map(([key, value]) => (
          <div key={key}>
            <dt>{key.replaceAll('_', ' ')}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>
      <p>
        Authored engineering scenario. This configuration is separate from revealed readings; no
        future realized values are previewed.
      </p>
    </details>
  ) : null;
}
