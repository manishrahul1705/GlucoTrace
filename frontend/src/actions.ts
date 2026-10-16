/** Synchronous guard for controls whose React disabled state has not rendered yet. */
export class ExclusiveAction {
  private locked=false;
  async run(action:()=>Promise<void>):Promise<boolean>{
    if(this.locked)return false;
    this.locked=true;
    try{await action();return true}finally{this.locked=false}
  }
}
/** Ignore stale success and failure responses from overlapping library refreshes. */
export class LatestRequest {
  private version=0;
  begin(){return ++this.version}
  accepts(version:number){return version===this.version}
}
export function displayNameProblem(name:string):string|null{
  if(!name.trim())return 'Enter a session name containing a visible character.';
  if(name.length>80)return 'Use 80 characters or fewer.';
  if(/[\x00-\x1f\x7f]/.test(name))return 'Use printable characters without line breaks.';
  return null;
}
