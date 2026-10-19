import React from 'react';
import type {Forecast, Snapshot} from './types';
import {reasonText} from './reasons';

export const variantLabel = (variant:string) => ({
  persistence:'Persistence',sensor_only_unadapted:'Sensor-only unadapted',
  sensor_only_offset24h:'Sensor-only with 24h offset'
}[variant] ?? variant.replaceAll('_',' '));

// Every value here belongs to the immutable issue, never current recovery state.
export function IssuedForecast({forecast:f}:{forecast:Forecast}) {
  return <div className="issued-forecast" data-variant={f.variant}>
    <strong>{variantLabel(f.variant)}</strong>
    <p>Issue {f.origin_time} · target {f.target_time} (+30 min)</p>
    <p>{f.value == null ? `Suppressed · ${reasonText(f.point_reason)}` : `${f.value.toFixed(1)} mg/dL (at issue)`}</p>
    <p>Support at issue: {f.history_count}/61 accepted minute cells</p>
  </div>;
}

export function Availability({snapshot:s}:{snapshot:Snapshot|null}) {
  if(!s)return <p>Awaiting session creation.</p>;
  if(!s.availability)return <p>Availability details unavailable; restart the backend to load the current contract.</p>;
  return <div className="variant-availability">
    <p>Calibration period: {s.mode==='synthetic' ? 'not applicable to synthetic persistence' : s.artifacts_frozen ? 'completed / frozen; readiness listed per level below' : 'not yet frozen'}</p>
    {s.availability.map(v=><section key={v.variant} aria-label={`${variantLabel(v.variant)} availability`} data-variant={v.variant}>
      <strong>{variantLabel(v.variant)}</strong>
      <p>Source capability: {v.capability_reason==='OK' ? 'Supported in this session' : reasonText(v.capability_reason)}</p>
      <p>Current cutoff: {v.current_reason==='OK' ? 'Point issued at this cutoff' : reasonText(v.current_reason)}</p>
      <p>Latest scheduled point{v.latest_origin_time ? ` at ${v.latest_origin_time}` : ''}: {v.latest_point_reason==='OK' ? 'Available at issue' : reasonText(v.latest_point_reason)}</p>
      <p>Next scheduled issue: {reasonText(v.next_issue_reason)}</p>
      {v.intervals.map(i=><p key={i.alpha}>
        {i.alpha==='0.10'?'90%':'95%'} calibration: {reasonText(i.calibration_reason)}.
        {' '}Current bounds: {reasonText(i.current_reason)}.
        {' '}Bounds at latest issue: {reasonText(i.latest_reason)}
      </p>)}
    </section>)}
  </div>;
}
