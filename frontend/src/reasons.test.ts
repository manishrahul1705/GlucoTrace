import {describe,it,expect} from 'vitest';
import {reasonDetail} from './reasons';
import {PollingGate} from './state';
describe('availability explanations',()=>{
 it('keeps technical codes alongside actionable descriptions',()=>{
  expect(reasonDetail('MISSING_CURRENT_READING;STALE_READING')).toContain('no fresh point');
  expect(reasonDetail('MISSING_CURRENT_READING;STALE_READING')).toContain('[MISSING_CURRENT_READING;STALE_READING]');
  expect(reasonDetail('SYNTHETIC_INTERVALS_UNCALIBRATED')).toContain('point forecast can still');
 });
 it('preserves unknown reason codes rather than inventing availability',()=>expect(reasonDetail('NEW_REASON')).toBe('new reason [NEW_REASON]'));
 it('exposes outstanding polls until their settlement',async()=>{
  const gate=new PollingGate();let finish!:()=>void;
  gate.track(new Promise<void>(resolve=>{finish=resolve}));expect(gate.inFlight).toBe(true);
  finish();await gate.suspend();expect(gate.inFlight).toBe(false);
 });
});
