import React from 'react';
import type {Snapshot,Forecast} from './types';
import {variantLabel} from './availability';

export function EndpointFlags({snapshot}:{snapshot:Snapshot|null}){
 if(!snapshot)return null;
 const latest=new Map<string,Forecast>();for(const f of snapshot.forecasts)latest.set(f.variant,f);
 return <section className="panel" aria-label="Exact +30-minute endpoint research flags">
  <h3>Exact +30-minute endpoint research flags</h3>
  <p>Current replay cutoff: {snapshot.virtual_time}. Research only: strictly greater than 180 or 250 mg/dL at the exact target time. These are endpoint flags, not episode/onset predictions or event probabilities. Already-high origins remain included; repeated flags are separate endpoint decisions.</p>
  {snapshot.mode==='synthetic'&&<p>Synthetic persistence-derived flags; these are not patient performance.</p>}
  {[...latest.values()].map(f=><article key={f.variant} data-event-variant={f.variant}><strong>{variantLabel(f.variant)}</strong><p>Origin {f.origin_time}; exact target {f.target_time}; model family {f.model_family??f.variant}.</p>
   {f.endpoint_flags?.map(flag=><p key={flag.threshold_mg_dl}>Endpoint &gt;{flag.threshold_mg_dl} mg/dL: {flag.flag_status}; target {flag.target_status}; {flag.label==null?'outcome unavailable':`observed endpoint ${flag.label?'above':'not above'} threshold`}{flag.confusion?` · ${flag.confusion}`:''}.</p>)}
  </article>)}
  <p>Suppressed forecasts are unavailable, pending targets are not false positives, and missing targets are unscorable. No treatment or dosing guidance.</p>
 </section>;
}
