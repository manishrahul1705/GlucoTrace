/** Private Chromium smoke for every frozen source, representative deep UI cases. */
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require=createRequire(path.join(root,'frontend/package.json'));
const {chromium,expect}=require('@playwright/test');
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,all)=>i%2?a:[...a,[v.slice(2),all[i+1]]],[]));
const url=new URL(args.url);
assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');
const input=JSON.parse(fs.readFileSync(args.input,'utf8'));
const output=path.resolve(args.output);
const report={kind:'PRIVATE_ENDPOINT_CHROMIUM_ACCEPTANCE',sources:[],deep:[],failures:[],started_at:new Date().toISOString()};
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(String(e)));
let sequence=0;
const save=()=>fs.writeFileSync(path.join(output,'endpoint-browser.json'),JSON.stringify(report,null,2)+'\n');
async function api(method,route,data){const r=await page.request.fetch(new URL('/api'+route,url).href,{method,data,timeout:120000});assert.equal(r.status(),200,await r.text());return r.json();}
async function create(source,start,scenario='clean'){
 await page.goto(url.href,{waitUntil:'networkidle'});
 await page.getByLabel('Source',{exact:true}).selectOption(source);
 await page.getByLabel('Session start',{exact:true}).selectOption(start);
 await page.getByLabel('Input scenario',{exact:true}).selectOption(scenario);
 const started=performance.now();
 // A warm four-variant replay reconstructs 48 hours before returning. Match the
 // existing HTTP client request budget; this is not a scientific tolerance/SLO.
 const response=page.waitForResponse(r=>r.url().endsWith('/api/replay/sessions')&&r.request().method()==='POST',{timeout:120000});
 await page.getByRole('button',{name:/^Create (new )?session$/}).click();
 const r=await response;assert.equal(r.status(),200);const s=await r.json();assert.equal(s.mode,'local');assert.equal(s.source_id,source);
 s.acceptance_creation_ms=performance.now()-started;
 await expect(page.locator('.capability-card')).toContainText('RETROSPECTIVE REPLAY');
 return s;
}

function flags(s){
 for(const f of s.forecasts){assert.equal(f.endpoint_flags.length,2);for(const flag of f.endpoint_flags){
  const wanted=f.point_reason==='OK'&&f.value!==null?f.value>flag.threshold_mg_dl:null;assert.equal(flag.flag,wanted);
  if(!f.score){assert.equal(flag.target_status,'PENDING');assert.equal(flag.label,null);assert.equal(flag.confusion,null);}
  else if(f.score.observed===null){assert.equal(flag.target_status,'MISSING');assert.equal(flag.confusion,null);}
  else {const label=f.score.observed>flag.threshold_mg_dl;assert.equal(flag.label,label);assert.equal(flag.confusion,wanted===null?null:wanted&&label?'TP':wanted?'FP':label?'FN':'TN');}
 }}
}

async function readiness(s){
 flags(s);
 const area=page.getByRole('region',{name:'Exact +30-minute endpoint research flags',exact:true});await expect(area).toBeVisible();await expect(area).toContainText('not episode/onset');
 for(const a of s.availability){await expect(area.locator(`[data-event-variant="${a.variant}"]`)).toBeVisible();}
 for(const variant of s.availability){
  const section=page.locator(`.variant-availability section[data-variant="${variant.variant}"]`);
  await expect(section).toBeVisible();await expect(section).toContainText('90% calibration:');await expect(section).toContainText('95% calibration:');
  if(variant.current_reason==='OK')await expect(section).toContainText('Point issued at this cutoff');
  assert.equal(variant.intervals.length,2);
 }
}
async function step(s){const next=await api('POST',`/replay/sessions/${s.session_id}/control`,{generation:s.generation,request_id:'browser-'+(++sequence),action:'step'});flags(next);return next;}
async function advance(s,target){while(s.elapsed_minutes<target)s=await step(s);return s;}
async function sync(s){await expect(page.getByLabel('Inspection cutoff',{exact:true})).toHaveAttribute('max',String(Math.floor(s.elapsed_minutes)));}
async function close(s){if(s)await api('DELETE',`/replay/sessions/${s.session_id}`);}
try{
 for(const source of input.sources){
  const record={...source,status:'RUNNING'};report.sources.push(record);save();let s;
  try{
   s=await create(source.source_id,'warm');assert.equal(s.phase,'evaluation');assert(s.artifacts_frozen);assert.equal(s.artifact_reason,'OK');await readiness(s);
   for(const level of ['90%','95%']){const button=page.getByRole('button',{name:level,exact:true});await button.click();await expect(button).toHaveAttribute('aria-pressed','true');}
   await page.screenshot({path:path.join(output,`browser-p${source.participant_id}-warm.png`),fullPage:true});
   record.status='PASS';record.readiness=s.availability;record.creation_ms=s.acceptance_creation_ms;
  }catch(e){record.status='FAIL';record.error=String(e.stack||e);report.failures.push(record.error);}
  finally{await close(s);save();}
 }
 const representative=input.sources[0];let s;
 try{
  s=await create(representative.source_id,'full');assert.equal(s.phase,'offset');
  await expect(page.locator('.variant-availability')).toContainText('not yet frozen');
  while(s.phase==='offset')s=await step(s);
  assert.equal(s.phase,'calibration');await readiness(s);await page.screenshot({path:path.join(output,'deep-calibration.png'),fullPage:true});
  while(s.phase==='calibration')s=await step(s);
  assert.equal(s.phase,'evaluation');assert(s.artifacts_frozen);
  await expect(page.locator('.variant-availability')).toContainText('completed / frozen');
  report.deep.push({participant_id:representative.participant_id,case:'full offset/calibration/evaluation transitions',status:'PASS'});save();
  s=await advance(s,s.elapsed_minutes+100);await sync(s);await readiness(s);
  const issued=s.forecasts.filter(f=>f.origin_time===s.virtual_time);assert.equal(issued.length,4);const ids=new Set(issued.map(f=>f.id));assert(issued.every(f=>f.endpoint_flags.every(x=>x.target_status==='PENDING')));
  await page.getByRole('button',{name:/^Inspect forecast /}).first().click();const dialog=page.getByRole('dialog',{name:'Forecast inspector',exact:true});await expect(dialog).toContainText('target PENDING');await expect(dialog).toContainText('Endpoint >180');
  const issuedAt=s.elapsed_minutes;s=await advance(s,issuedAt+25);assert(s.forecasts.filter(f=>ids.has(f.id)).every(f=>f.endpoint_flags.every(x=>x.target_status==='PENDING')));
  s=await advance(s,issuedAt+30);const mature=s.forecasts.filter(f=>ids.has(f.id));assert.equal(mature.length,4);assert(mature.every(f=>f.score&&f.score.matured_time===f.target_time));flags(s);await sync(s);await expect(dialog).toContainText('target PENDING');await page.getByRole('button',{name:'Close inspector',exact:true}).click();
  report.deep.push({case:'four immutable endpoint flags pending through +25 and mature at exact +30',status:'PASS'});
  const cutoff=s.elapsed_minutes-30;
  const range=page.getByLabel('Inspection cutoff',{exact:true});
  await range.focus();await range.press('End');
  const historical=page.waitForResponse(r=>r.url().includes('/explore?')&&r.url().includes(`end_minute=${cutoff}&`));
  for(let n=0;n<30;n++)await range.press('ArrowLeft');
  await expect(range).toHaveValue(String(cutoff));
  const r=await historical;assert.equal(r.status(),200);const view=await r.json();
  assert(view.history.every(x=>x.measurement_time<=view.virtual_time));
  assert(view.forecasts.every(f=>f.origin_time<=view.virtual_time&&(!f.score||f.score.matured_time<=view.virtual_time)));flags(view);
  await expect(page.getByRole('button',{name:'Return to current time'})).toBeVisible();
  await page.screenshot({path:path.join(output,'deep-historical-cutoff.png'),fullPage:true});
  await page.getByRole('button',{name:'Return to current time'}).click();
  report.deep.push({participant_id:representative.participant_id,case:'historical slider hides future readings and later scores',status:'PASS'});save();
 }finally{await close(s);}
 // One representative supported loss duration; HTTP covers every protocol duration.
 try{
  const duration=input.durations[0];s=await create(representative.source_id,'warm',`dropout${duration}`);
  const epoch=Date.parse(s.session_epoch),begin=(Date.parse(s.gap.start_time)-epoch)/60000,end=(Date.parse(s.gap.end_time)-epoch)/60000;
  s=await advance(s,begin);await sync(s);assert(s.recovery.is_suppressed);
  for(const variant of s.availability){
   assert.equal(variant.latest_point_reason,'MISSING_CURRENT_READING');
   for(const level of variant.intervals)assert.equal(level.latest_reason,'MISSING_CURRENT_READING');
   const section=page.locator(`.variant-availability section[data-variant="${variant.variant}"]`);
   await expect(section).toContainText('missing current reading:');
   await expect(section).not.toContainText('A reading is not finite');
  }
  await expect(page.locator('.recovery-panel')).toContainText(s.recovery.suppression_message);
  await page.screenshot({path:path.join(output,'deep-simulated-input-loss.png'),fullPage:true});
  s=await advance(s,end+s.recovery.required_minutes);await sync(s);
  assert.equal(s.recovery.is_suppressed,false);
  for(const variant of s.availability)assert.equal(variant.latest_point_reason,'OK');
  await expect(page.locator('.recovery-panel')).toContainText(s.recovery.suppression_message);
  await readiness(s);await page.screenshot({path:path.join(output,'deep-input-loss-recovery.png'),fullPage:true});
  report.deep.push({participant_id:representative.participant_id,case:`simulated processed-replay input loss ${duration}m and recovery`,status:'PASS',recovery:s.recovery});
 }finally{}
 for(const width of [360,768,1440]){
  await page.setViewportSize({width,height:1000});await expect(page.locator('.topbar')).toBeVisible();await expect(page.getByRole('region',{name:'Playback controls',exact:true})).toBeVisible();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),`horizontal overflow ${width}`);
  await page.screenshot({path:path.join(output,`endpoint-responsive-${width}.png`),fullPage:true});
 }
 await close(s);
 report.deep.push({case:'responsive header and transport at 360/768/1440px',status:'PASS'});
 assert.deepEqual(errors,[]);
}catch(e){report.failures.push(String(e.stack||e));}
finally{report.page_errors=errors;report.status=report.failures.length?'FAIL':'PASS';report.finished_at=new Date().toISOString();save();await browser.close();}
console.log(`Chromium sources ${report.sources.filter(s=>s.status==='PASS').length}/${input.sources.length}; representative deep cases ${report.deep.length}; ${report.status}`);
if(report.status!=='PASS')process.exitCode=1;
