import {describe,it,expect} from 'vitest';
import {ExclusiveAction,LatestRequest,displayNameProblem} from './actions';
describe('library action coordination',()=>{
 it('rejects a second action before any disabled render and runs again after completion',async()=>{
  const gate=new ExclusiveAction();let finish!:()=>void;let calls=0;
  const first=gate.run(async()=>{calls++;await new Promise<void>(r=>{finish=r})});
  expect(await gate.run(async()=>{calls++})).toBe(false);expect(calls).toBe(1);
  finish();expect(await first).toBe(true);expect(await gate.run(async()=>{calls++})).toBe(true);expect(calls).toBe(2);
 });
 it('releases the guard on failure so recovery remains possible',async()=>{
  const gate=new ExclusiveAction();await expect(gate.run(async()=>{throw Error('offline')})).rejects.toThrow('offline');
  expect(await gate.run(async()=>{})).toBe(true);
 });
 it('accepts only the latest refresh including when earlier requests fail late',()=>{
  const requests=new LatestRequest();const old=requests.begin(),current=requests.begin();
  expect(requests.accepts(old)).toBe(false);expect(requests.accepts(current)).toBe(true);
 });
 it('rejects visually blank, overlong and control-character names while preserving CSV-sensitive printable input',()=>{
  for(const name of ['', '   ', '\t', 'x'.repeat(81), 'a\nb'])expect(displayNameProblem(name)).not.toBeNull();
  for(const name of ['A replay', '=Formula, "quoted"', '  +name', 'x'.repeat(80)])expect(displayNameProblem(name)).toBeNull();
 });
});
