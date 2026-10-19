import React from 'react';
import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {Availability,IssuedForecast} from './availability';
import type {Snapshot,Forecast,VariantAvailability} from './types';

const variant=(name:string,point:string,levels=['OK','INSUFFICIENT_CALIBRATION']):VariantAvailability=>({
 variant:name,capability_reason:'OK',current_reason:point,next_issue_reason:'AWAITING_NEXT_ISSUE',
 latest_forecast_id:name,latest_origin_time:'2026-01-01T10:00:00Z',latest_point_reason:point,
 intervals:levels.map((r,n)=>({alpha:n===0?'0.10':'0.05',calibration_reason:r,current_reason:point==='OK'?r:point,latest_reason:r}))
});
const snapshot=(availability:VariantAvailability[])=>({mode:'local',artifacts_frozen:true,availability} as Snapshot);
describe('availability displays',()=>{
 it('renders each variant independently regardless of order',()=>{
  const a=variant('sensor_only_unadapted','OK'),b=variant('sensor_only_offset24h','INSUFFICIENT_OFFSET_DATA');
  for(const list of [[a,b],[b,a]]){
   const html=renderToStaticMarkup(<Availability snapshot={snapshot(list)}/>);
   expect(html).toContain('Sensor-only unadapted');expect(html).toContain('Sensor-only with 24h offset');
   expect(html).toContain('Available at issue');expect(html).toContain('Too few eligible pairs to fit the fixed offset');
  }
 });
 it('does not equate frozen calibration with available bounds',()=>{
  const html=renderToStaticMarkup(<Availability snapshot={snapshot([variant('sensor_only_unadapted','OK')])}/>);
  expect(html).toContain('completed / frozen');expect(html).toContain('90% calibration: Available');
  expect(html).toContain('95% calibration: Too few eligible calibration pairs');
 });
 it('shows awaiting assessment between issues and retains prior issue availability',()=>{
  const v={...variant('persistence','OK'),current_reason:'AWAITING_NEXT_ISSUE'};
  const html=renderToStaticMarkup(<Availability snapshot={snapshot([v])}/>);
  expect(html).toContain('Current cutoff: Not yet assessed');expect(html).toContain('Available at issue');
 });
 it('shows ended scheduling separately from the last valid issue',()=>{
  const v={...variant('persistence','OK'),current_reason:'SESSION_ENDED',next_issue_reason:'SESSION_ENDED'};
  const html=renderToStaticMarkup(<Availability snapshot={snapshot([v])}/>);
  expect(html).toContain('Session ended; no future issue');expect(html).toContain('Available at issue');
 });
 it('preserves unsupported synthetic intervals at every level',()=>{
  const s={...snapshot([variant('persistence','OK',['SYNTHETIC_INTERVALS_UNCALIBRATED','SYNTHETIC_INTERVALS_UNCALIBRATED'])]),mode:'synthetic'} as Snapshot;
  const html=renderToStaticMarkup(<Availability snapshot={s}/>);
  expect(html).toContain('not applicable');expect(html).toContain('No interval calibration exists in demo mode');
 });
 it('latest issue support never borrows current recovery counts',()=>{
  const f={variant:'persistence',origin_time:'2026-01-01T11:30:00Z',target_time:'2026-01-01T12:00:00Z',history_count:1,value:null,point_reason:'INCOMPLETE_HISTORY'} as Forecast;
  const html=renderToStaticMarkup(<IssuedForecast forecast={f}/>);
  expect(html).toContain('Support at issue: 1/61');expect(html).toContain(f.origin_time);
  expect(html).toContain('Suppressed');
 });
});
