import type {Snapshot} from './types';
export function acceptsSnapshot(current:Pick<Snapshot,'session_id'|'generation'|'sequence'>|null,incoming:Pick<Snapshot,'session_id'|'generation'|'sequence'>):boolean {
  return !current || (current.session_id===incoming.session_id && current.generation===incoming.generation && incoming.sequence>=current.sequence);
}
export function responseIsCurrent(requestEpoch:number,activeEpoch:number){return requestEpoch===activeEpoch;}

/** Drain requests before replacing/resetting a session; never delete beneath a poll. */
export class PollingGate {
  paused=false;
  private requests=new Set<Promise<unknown>>();
  track(request:Promise<unknown>){
    this.requests.add(request);
    void request.then(()=>this.requests.delete(request),()=>this.requests.delete(request));
  }
  async suspend(){
    this.paused=true;
    await Promise.allSettled([...this.requests]);
  }
  resume(){this.paused=false;}
}
