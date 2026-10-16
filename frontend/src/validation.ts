export function validateSnapshot(value:unknown):void{
 if(!value||typeof value!=='object')throw Error('Invalid replay response');
 const s=value as Record<string,unknown>;
 if(typeof s.session_id!=='string'||typeof s.generation!=='string'||!Number.isFinite(s.sequence)||!Number.isFinite(s.elapsed_minutes)||!Array.isArray(s.history)||!Array.isArray(s.forecasts)||!Array.isArray(s.summaries))throw Error('Invalid replay response');
 for(const r of s.history as Record<string,unknown>[])if(typeof r.measurement_time!=='string'||(r.value!==null&&!Number.isFinite(r.value)))throw Error('Invalid reading response');
 for(const f of s.forecasts as Record<string,unknown>[])if(typeof f.id!=='string'||typeof f.origin_time!=='string'||typeof f.target_time!=='string'||!Array.isArray(f.intervals)||(f.value!==null&&!Number.isFinite(f.value)))throw Error('Invalid forecast response');
}
