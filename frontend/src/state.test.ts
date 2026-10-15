import {describe,it,expect} from 'vitest';
import {acceptsSnapshot,responseIsCurrent,PollingGate} from './state';
const current={session_id:'a',generation:'new',sequence:30};
describe('replay response isolation',()=>{
 it('rejects stale generations even with higher sequence',()=>expect(acceptsSnapshot(current,{...current,generation:'old',sequence:500})).toBe(false));
 it('rejects responses for another session',()=>expect(acceptsSnapshot(current,{...current,session_id:'b'})).toBe(false));
 it('rejects out-of-order sequences',()=>expect(acceptsSnapshot(current,{...current,sequence:29})).toBe(false));
 it('accepts paused repeats and monotonic updates',()=>{expect(acceptsSnapshot(current,current)).toBe(true);expect(acceptsSnapshot(current,{...current,sequence:31})).toBe(true)});
 it('invalidates in-flight polling when reset/create starts',()=>{expect(responseIsCurrent(2,3)).toBe(false);expect(responseIsCurrent(3,3)).toBe(true)});
});
describe('session transition polling',()=>{
 it('pauses immediately and drains all in-flight polls before replacement',async()=>{
   const gate=new PollingGate();let finish!:()=>void;let fail!:(e:Error)=>void;
   gate.track(new Promise<void>(resolve=>{finish=resolve}));
   gate.track(new Promise<void>((_,reject)=>{fail=reject}));
   let drained=false;const pending=gate.suspend().then(()=>{drained=true});
   expect(gate.paused).toBe(true);expect(drained).toBe(false);
   finish();await Promise.resolve();expect(drained).toBe(false);
   fail(new Error('handled old-session request'));await pending;
   expect(drained).toBe(true);expect(gate.paused).toBe(true);
 });
 it('resumes and can safely drain the next reset generation',async()=>{
   const gate=new PollingGate();await gate.suspend();gate.resume();expect(gate.paused).toBe(false);
   let finish!:()=>void;gate.track(new Promise<void>(resolve=>{finish=resolve}));
   const reset=gate.suspend();expect(gate.paused).toBe(true);finish();await reset;
   gate.resume();expect(gate.paused).toBe(false);
 });
});
