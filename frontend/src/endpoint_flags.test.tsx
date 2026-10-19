import React from 'react';
import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {EndpointFlags} from './endpoint_flags';
import type {Snapshot} from './types';

describe('exact endpoint research flags',()=>{
 it('separates flags, pending targets and synthetic provenance',()=>{
  const snapshot={mode:'synthetic',virtual_time:'2026-01-01T10:00:00Z',forecasts:[{variant:'persistence',model_family:'persistence',origin_time:'2026-01-01T10:00:00Z',target_time:'2026-01-01T10:30:00Z',endpoint_flags:[{threshold_mg_dl:180,flag:true,flag_status:'FLAG',target_status:'PENDING',label:null,confusion:null}]}]} as unknown as Snapshot;
  const html=renderToStaticMarkup(<EndpointFlags snapshot={snapshot}/>);
  expect(html).toContain('Demo persistence-derived');expect(html).toContain('target PENDING');expect(html).toContain('not episode/onset');expect(html).not.toContain(' · FP');
 });
 it('keeps unavailable separate from a negative endpoint flag',()=>{
  const snapshot={mode:'local',virtual_time:'cutoff',forecasts:[{variant:'baseline_sensor_unadapted',origin_time:'origin',target_time:'target',endpoint_flags:[{threshold_mg_dl:250,flag:null,flag_status:'FORECAST_UNAVAILABLE',target_status:'MISSING',label:null,confusion:null}]}]} as unknown as Snapshot;
  const html=renderToStaticMarkup(<EndpointFlags snapshot={snapshot}/>);expect(html).toContain('FORECAST_UNAVAILABLE');expect(html).toContain('target MISSING');expect(html).toContain('Baseline + sensor');
 });
});
