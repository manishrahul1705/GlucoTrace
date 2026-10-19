/** Current GlucoTrace demo checks against an owned, synthetic-only loopback app.
 * Never starts services, records video, or opens a private patient source.
 */
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,all)=>i%2?a:[...a,[v.slice(2),all[i+1]]],[]));
if(!args.url||!args.output)throw Error('Required: --url LOOPBACK_URL --output NEW_EXTERNAL_DIRECTORY');
const url=new URL(args.url),root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),out=path.resolve(args.output);
assert.equal(url.protocol,'http:');assert(['127.0.0.1','localhost'].includes(url.hostname));
assert(out!==root&&!out.startsWith(root+path.sep));fs.mkdirSync(out);
const require=createRequire(path.join(root,'frontend/package.json')),{chromium,expect}=require('@playwright/test');
const report={kind:'GLUCOTRACE_DEMO_BROWSER',started_at:new Date().toISOString(),scenarios:[],checks:[],errors:[],failed_requests:[],private_sources_opened:0,video_recorded:false};
const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:1100},acceptDownloads:true});
let session,sequence=0;
page.on('pageerror',e=>report.errors.push(String(e)));
page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text())});
page.on('requestfailed',r=>report.failed_requests.push(r.url()+': '+r.failure()?.errorText));
page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)report.failed_requests.push(r.url()+': '+r.status())});
const check=caseName=>report.checks.push({case:caseName,status:'PASS'});
async function api(method,route,data){const r=await page.request.fetch(new URL('/api/replay'+route,url).href,{method,data});assert.equal(r.status(),200,await r.text());return r.json()}
async function step(){session=await api('POST',`/sessions/${session.session_id}/control`,{generation:session.generation,request_id:'demo-'+(++sequence),action:'step'});return session}
async function advance(t){while(session.elapsed_minutes<t)await step();await expect(page.getByLabel('Inspection cutoff',{exact:true})).toHaveAttribute('max',String(t));}
async function create(scenario='clean',start='warm'){
 await page.goto(url.href+'#replay',{waitUntil:'networkidle'});
 await page.getByLabel('Source',{exact:true}).selectOption('synthetic-dawn');await page.getByLabel('Input scenario',{exact:true}).selectOption(scenario);await page.getByLabel('Session start',{exact:true}).selectOption(start);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/replay/sessions')&&r.request().method()==='POST');await page.getByRole('button',{name:'Create demo session',exact:true}).click();const r=await response;assert.equal(r.status(),200);session=await r.json();return session;
}
try{
 await page.goto(url.href,{waitUntil:'networkidle'});await expect(page).toHaveTitle('GlucoTrace | Research replay');await expect(page.locator('h1')).toHaveText('GlucoTrace');await expect(page.locator('.heading')).toContainText('Patient-Adaptive Glucose Forecasting Research Platform');await expect(page.locator('.disclosure')).toHaveText('Demo data — simulated readings');
 assert(!/glucotwin/i.test(await page.locator('body').innerText()));check('current title, branding, subtitle and persistent simulated-data disclosure');
 const sources=await api('GET','/sources');assert(!sources.sources.some(s=>s.mode==='local'&&s.available),'Use a dedicated synthetic-only service for this runner');
 await page.getByText('Source information',{exact:true}).click();await expect(page.locator('.source-information')).toContainText('does not use patient-trained Ridge');await page.getByRole('button',{name:'Help · How to use',exact:true}).click();await expect(page.getByLabel('How to use GlucoTrace')).toBeVisible();await page.getByRole('button',{name:'Close help',exact:true}).click();check('source provenance and branded help');
 const order=['clean','steady','meal','activity','noisy','dropout15','dropout30','dropout60','dropout120'];const catalog=await api('GET','/scenarios');assert.deepEqual(new Set(catalog.scenarios.map(x=>x.id)),new Set(order));
 for(const [index,id] of order.entries()){
  await page.goto(url.href+'#scenario-lab');await expect(page.locator('.scenario-card')).toHaveCount(9);
  const response=page.waitForResponse(r=>r.url().endsWith('/api/replay/sessions')&&r.request().method()==='POST');await page.locator('.scenario-card').nth(index).getByRole('button').click();const r=await response;assert.equal(r.status(),200);session=await r.json();assert.equal(session.configuration.scenario,id,'Clicked scenario must be the configuration actually launched');assert.equal(session.mode,'synthetic');assert.equal(session.elapsed_minutes,120);assert.equal(session.configuration.seed,1705);assert.equal(session.configuration.duration_minutes,720);
  assert.equal(session.recovery.is_suppressed,false);assert(session.forecasts.some(f=>f.history_count===61&&f.value!==null));assert(session.forecasts.every(f=>f.model_family==='persistence'&&f.intervals.every(i=>i.lower===null&&i.upper===null)));report.scenarios.push({id,status:'PASS',start_minute:session.elapsed_minutes});
 }
 check('all nine scenario cards create the requested warm demo with sufficient history and unavailable intervals');
 await create();const stepButton=page.getByRole('button',{name:'Step 5 min',exact:true});await page.keyboard.press('Tab');await stepButton.focus();assert(await stepButton.evaluate(e=>e.matches(':focus-visible')&&getComputedStyle(e).outlineStyle!=='none'));await page.keyboard.press('Enter');await expect(stepButton).toBeEnabled();
 await page.getByRole('button',{name:'Playback speed 300x'}).click();await page.getByRole('button',{name:'Start / resume',exact:true}).click();await page.getByRole('button',{name:'Pause',exact:true}).click();await page.getByRole('button',{name:'Reset replay',exact:true}).click();await expect(page.locator('.recovery-panel')).toContainText('Continuous run: 121');check('keyboard focus, step, speed, start, pause and reset');
 session=await api('GET',`/sessions/${session.session_id}/snapshot`);const origin=session.forecasts.at(-1);assert.equal(origin.score,null);const cutoff=session.elapsed_minutes;
 const earlier=await api('GET',`/sessions/${session.session_id}/explore?end_minute=${cutoff}&window=180`);
 await page.getByRole('button',{name:/^Inspect forecast /}).first().click();const dialog=page.getByRole('dialog',{name:'Forecast inspector'});await expect(dialog).toContainText('target PENDING');await expect(dialog).toContainText('No interval calibration exists in demo mode');
 await advance(cutoff+25);assert(session.forecasts.find(f=>f.id===origin.id).score===null);await advance(cutoff+30);const matured=session.forecasts.find(f=>f.id===origin.id);assert.equal(matured.score.matured_time,matured.target_time);assert(matured.endpoint_flags.every(x=>x.target_status==='MATURED'));await expect(dialog).toContainText('target PENDING');await page.getByRole('button',{name:'Close inspector',exact:true}).click();assert.deepEqual(await api('GET',`/sessions/${session.session_id}/explore?end_minute=${cutoff}&window=180`),earlier);
 const slider=page.getByLabel('Inspection cutoff',{exact:true});await slider.focus();await slider.press('End');for(let i=0;i<30;i++)await slider.press('ArrowLeft');await expect(slider).toHaveValue(String(cutoff));await expect(page.getByRole('button',{name:'Return to current time',exact:true})).toBeVisible();await page.getByRole('button',{name:'Return to current time',exact:true}).click();check('endpoint pending through +25, exact +30 maturity and immutable historical cutoff/inspector');
 await create('clean','full');await step();assert(session.forecasts.some(f=>f.value===null&&f.endpoint_flags.every(x=>x.flag===null)));check('full chronology retains unavailable-history forecasts rather than fabricating points');
 for(const duration of [15,30,60,120]){
  await create('dropout'+duration);await advance(180);assert(session.recovery.is_suppressed);assert.equal(session.forecasts.at(-1).point_reason,'MISSING_CURRENT_READING');assert(session.forecasts.at(-1).endpoint_flags.every(x=>x.flag_status==='FORECAST_UNAVAILABLE'));
  await advance(180+duration+60);assert(!session.recovery.is_suppressed);assert.equal(session.forecasts.at(-1).point_reason,'OK');report.checks.push({case:`demo ${duration}m loss and 61-cell recovery`,status:'PASS',recovery_minute:session.elapsed_minutes});
 }
 await create();await page.goto(url.href+'#session-library');const row=page.locator('.library-row[data-current="true"]');await row.getByRole('textbox').fill('=2+2');await row.getByRole('button',{name:'Save name',exact:true}).click();await expect(page.locator('.library-panel .action-status')).toContainText('Session name saved.');await expect(row.getByRole('textbox')).toHaveValue('=2+2');await row.getByRole('button',{name:'Read-only summary',exact:true}).click();await expect(page.getByRole('region',{name:'Retained session summary'})).toBeVisible();await page.getByRole('button',{name:'Close summary',exact:true}).click();
 await page.goto(url.href+'#session-summary');
 for(const kind of ['configuration','readings','forecasts','scores','summary']){
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Export demo '+kind,exact:true}).click();const download=await pending;assert(download.suggestedFilename().startsWith('glucotrace-demo-'));const target=path.join(out,download.suggestedFilename());await download.saveAs(target);const text=fs.readFileSync(target,'utf8');assert(/synthetic/i.test(text),'Simulation provenance remains in the actual export');if(['readings','forecasts','scores'].includes(kind))assert(text.includes("'=2+2"),'Formula-like display names must be escaped');
 }
 await page.goto(url.href+'#session-library');const recreated=page.waitForResponse(r=>r.url().endsWith('/recreate')&&r.request().method()==='POST');await row.getByRole('button',{name:'Recreate scenario',exact:true}).click();const fresh=await (await recreated).json();assert.notEqual(fresh.session_id,session.session_id);assert.deepEqual(fresh.configuration,session.configuration);check('retention, rename, summary, new-session recreation and all five genuine exports with provenance/formula protection');
 await page.goto(url.href+'#replay');
 for(const width of [360,768,1440]){
  await page.setViewportSize({width,height:1100});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'No page overflow at '+width);await expect(page.locator('.topbar')).toContainText('GlucoTrace');await expect(page.locator('.disclosure')).toHaveText('Demo data — simulated readings');await page.screenshot({path:path.join(out,`demo-${width}.png`),fullPage:true});
 }
 assert(!/GlucoTwin|\uFFFD|\u00c3\u00a2|\u00e2\u20ac/.test(await page.locator('body').innerText()));assert.deepEqual(report.errors,[]);assert.deepEqual(report.failed_requests,[]);check('360/768/1440 layout, current branding, Unicode and clean console/API requests');report.status='PASS';
}catch(e){report.status='FAIL';report.failure=String(e.stack||e);await page.screenshot({path:path.join(out,'first-failure.png'),fullPage:true});process.exitCode=1}
finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(out,'demo-browser.json'),JSON.stringify(report,null,2));await browser.close()}
console.log('Demo browser',report.status,`${report.scenarios.length}/9 scenarios`);
