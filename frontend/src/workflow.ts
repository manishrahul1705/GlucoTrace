import type {Forecast,Snapshot} from './types';
const privateScenarios=new Set(['clean','dropout15','dropout30','dropout60','dropout120']);
export function scenarioForSource(source:string,scenario:string){return source==='synthetic-dawn'||privateScenarios.has(scenario)?scenario:'clean'}
export type Inspection={forecast:Forecast;cutoff:string};
/** Hold an as-of projection. Live polls must not promote its historical score. */
export function inspectionAtCutoff(forecast:Forecast,cutoff:string):Inspection{
 const score=forecast.score&&Date.parse(forecast.score.matured_time)<=Date.parse(cutoff)?forecast.score:null;
 const endpoint_flags=forecast.endpoint_flags?.map(flag=>score?flag:{...flag,target_status:'PENDING' as const,label:null,confusion:null,status:flag.flag===null?'FORECAST_UNAVAILABLE':'TARGET_PENDING'});
 return {cutoff,forecast:{...forecast,score,endpoint_flags}};
}
/** Keep a cached exploration safe while an earlier range request is in flight. */
export function explorationAtCutoff(view:Pick<Snapshot,'history'|'forecasts'|'virtual_time'>,cutoff:string,minutes:number){
 const end=Date.parse(cutoff),start=end-minutes*60000;
 return {virtual_time:cutoff,
  history:view.history.filter(r=>Date.parse(r.measurement_time)<=end&&Date.parse(r.measurement_time)>=start),
  forecasts:view.forecasts.filter(f=>Date.parse(f.origin_time)<=end&&Date.parse(f.target_time)>=start).map(f=>inspectionAtCutoff(f,cutoff).forecast)};
}
