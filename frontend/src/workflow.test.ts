import {describe,it,expect} from 'vitest';
import {scenarioForSource,inspectionAtCutoff,explorationAtCutoff} from './workflow';
import type {Forecast} from './types';
const f={id:'f',origin_time:'2026-01-01T09:00:00Z',target_time:'2026-01-01T09:30:00Z',value:114,score:{matured_time:'2026-01-01T09:30:00Z',observed:160,signed_error:-46,reason:'OK',coverage:{}}} as Forecast;
describe('workflow boundaries',()=>{
 it('normalizes every synthetic-only scenario when selecting a private source',()=>{for(const name of ['steady','meal','activity','noisy'])expect(scenarioForSource('local-opaque',name)).toBe('clean')});
 it('preserves supported dropout selections and all synthetic selections',()=>{for(const name of ['clean','dropout15','dropout30','dropout60','dropout120'])expect(scenarioForSource('local-opaque',name)).toBe(name);expect(scenarioForSource('synthetic-dawn','meal')).toBe('meal')});
 it('projects historical inspection without promoting a later score or mutating its input',()=>{const view=inspectionAtCutoff(f,'2026-01-01T09:00:00Z');expect(view.forecast.score).toBeNull();expect(view.forecast.value).toBe(114);expect(f.score?.observed).toBe(160);expect(view.cutoff).toBe('2026-01-01T09:00:00Z')});
 it('reveals a score exactly at inclusive maturity and preserves absent scores',()=>{expect(inspectionAtCutoff(f,f.target_time).forecast.score?.observed).toBe(160);expect(inspectionAtCutoff({...f,score:null},f.target_time).forecast.score).toBeNull()});
 it('filters a later cached chart response while an earlier cutoff loads, retaining issued future endpoints',()=>{
  const view={virtual_time:'2026-01-01T10:00:00Z',history:[{id:'past',measurement_time:'2026-01-01T09:00:00Z',assumed_arrival_time:'2026-01-01T09:00:00Z',value:114},{id:'future',measurement_time:'2026-01-01T09:30:00Z',assumed_arrival_time:'2026-01-01T09:30:00Z',value:160}],forecasts:[f,{...f,id:'future-issue',origin_time:'2026-01-01T09:05:00Z'}]};
  const result=explorationAtCutoff(view,'2026-01-01T09:00:00Z',60);
  expect(result.history.map(r=>r.id)).toEqual(['past']);expect(result.forecasts.map(f=>f.id)).toEqual(['f']);expect(result.forecasts[0].score).toBeNull();expect(result.forecasts[0].target_time).toBe(f.target_time);expect(view.forecasts[0].score?.observed).toBe(160);
 });
});
