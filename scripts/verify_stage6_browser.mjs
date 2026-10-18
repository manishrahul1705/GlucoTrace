/** Actual Chromium UI verification; only independent synthetic scenarios. */
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(root,'frontend/package.json'));
const {chromium,expect}=require('@playwright/test');
const out=path.join(root,'reports/stage6');
const screenshots=path.join(out,'synthetic-screenshots');
await fs.mkdir(screenshots,{recursive:true});
const errors=[],failures=[],badApis=[],checks=[],layouts=[],images=[];
const testedFiles=['frontend/src/main.tsx','frontend/src/state.ts','frontend/src/state.test.ts','frontend/src/style.css','frontend/src/types.ts','frontend/package.json','frontend/package-lock.json','scripts/verify_stage6_browser.mjs'];
const sourceHashes=Object.fromEntries(await Promise.all(testedFiles.map(async name=>[name,createHash('sha256').update(await fs.readFile(path.join(root,name))).digest('hex')])));
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const page=await context.newPage();
let latest=null;
page.on('pageerror',e=>errors.push(String(e)));
page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text())});
page.on('requestfailed',r=>failures.push({url:r.url().replace(/\/sessions\/[\w-]+/,'/sessions/[session]'),error:r.failure()?.errorText}));
page.on('response',async r=>{
 if(r.url().includes('/api/')&&r.status()>=400)badApis.push({path:new URL(r.url()).pathname.replace(/\/sessions\/[\w-]+/,'/sessions/[session]'),status:r.status()});
 if(r.url().includes('/api/replay/sessions')&&r.ok()&&r.request().method()!=='DELETE'){
  try{const body=await r.json();if(body.generation)latest=body}catch{}
 }
});
const disclosure=page.locator('.disclosure');
async function assertDisclosure(){await expect(disclosure).toContainText('Synthetic scenario demonstration. No real patient readings.');await expect(page.locator('.mode-badge')).toContainText('INDEPENDENT SYNTHETIC')}
async function create(scenario='clean',start='warm'){
 await page.getByRole('combobox',{name:'Input scenario',exact:true}).selectOption(scenario);
 await page.getByRole('combobox',{name:'Session start',exact:true}).selectOption(start);
 const wait=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/replay/sessions'&&r.request().method()==='POST');
 await page.getByRole('button',{name:/^Create (new )?session$/}).click();
 const response=await wait;assert.equal(response.status(),200);const s=await response.json();
 await expect(page.locator('.phase-line')).toContainText(`${Math.floor(s.elapsed_minutes)} /`);
 await expect(page.getByRole('button',{name:'Step 5 min',exact:true})).toBeEnabled();
 await assertDisclosure();return s;
}
async function control(action,button){
 const wait=page.waitForResponse(r=>r.url().endsWith('/control')&&r.request().method()==='POST'&&r.request().postDataJSON()?.action===action);
 await button.click();const r=await wait;assert.equal(r.status(),200);const s=await r.json();
 await expect(page.locator('.phase-line')).toContainText(`${Math.floor(s.elapsed_minutes)} /`);
 await expect(page.getByRole('button',{name:'Reset replay'})).toBeEnabled();return s;
}
const step=()=>control('step',page.getByRole('button',{name:'Step 5 min',exact:true}));
async function reset(){
 const wait=page.waitForResponse(r=>r.url().endsWith('/reset')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Reset replay'}).click();const r=await wait;assert.equal(r.status(),200);const s=await r.json();
 await expect(page.locator('.phase-line')).toContainText(`${Math.floor(s.elapsed_minutes)} /`);return s;
}
function assertReveal(s){
 const now=Date.parse(s.virtual_time);
 for(const reading of s.history)assert.ok(Date.parse(reading.measurement_time)<=now);
 for(const f of s.forecasts){
  assert.equal(Date.parse(f.target_time)-Date.parse(f.origin_time),30*60000);
  if(Date.parse(f.target_time)>now)assert.equal(f.score,null,'Pending score leaked a target');
  if(f.score)assert.ok(Date.parse(f.score.matured_time)<=now);
 }
 assert.equal(s.mode,'synthetic');
}
async function screenshot(name,fullPage=true){
 await assertDisclosure();assert.equal(latest.mode,'synthetic');
 await page.screenshot({path:path.join(screenshots,name),fullPage});images.push('reports/stage6/synthetic-screenshots/'+name);
}
async function layout(width){
 await page.setViewportSize({width,height:(width===390||width===360)?844:1000});
 await page.evaluate(()=>document.fonts.ready);await page.locator('h1').scrollIntoViewIfNeeded();
 const measurements=await page.evaluate(()=>{
  const overflowing=[...document.querySelectorAll('h1,h2,.stat,.panel,.disclosure,.transport,button,td,th,.prediction-title,.interval-line,.stat-number')].filter(e=>{
   const r=e.getBoundingClientRect();return r.width&& (r.left< -1||r.right>innerWidth+1);
  }).map(e=>({element:e.tagName,class:e.className,text:e.textContent.slice(0,80)}));
  const clipped=[...document.querySelectorAll('button,h1,h2,.stat-number,.prediction-title,.interval-line,td,th')].filter(e=>e.clientWidth&&e.scrollWidth>e.clientWidth+2).map(e=>({element:e.tagName,class:e.className,text:e.textContent.slice(0,80)}));
  return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,overflowing,clipped};
 });
 layouts.push(measurements);
 assert.ok(measurements.documentWidth<=width+1,`Horizontal overflow at ${width}: ${JSON.stringify(measurements)}`);
 assert.deepEqual(measurements.overflowing,[],`Off-screen content at ${width}`);
 assert.deepEqual(measurements.clipped,[],`Clipped content at ${width}`);
 await screenshot(`synthetic-${width}.png`);
 await page.locator('#ledger').scrollIntoViewIfNeeded();await expect(disclosure).toBeInViewport();
 if(width===390||width===360)await screenshot(`synthetic-${width}-ledger.png`,false);
}
let status='FAIL',failure=null;
try{
 await page.goto('http://127.0.0.1:15173/',{waitUntil:'networkidle'});
 await expect(page.getByRole('button',{name:'Create session',exact:true})).toBeEnabled();
 let s=await create();assert.equal(s.elapsed_minutes,120);assertReveal(s);
 checks.push('Synthetic warm start, disclosure, exact targets, unavailable intervals and no future values');
 assert.ok(s.forecasts.some(f=>f.score?.reason==='OK'));
 assert.ok(s.forecasts.some(f=>f.score===null));
 await expect(page.locator('.prediction-panel')).toContainText('Interval unavailable');
 const original=s.elapsed_minutes;s=await step();assert.equal(s.elapsed_minutes,original+5);
 await control('speed',page.getByRole('button',{name:'Playback speed 300x'}));
 s=await control('start',page.getByRole('button',{name:'Start / resume',exact:true}));
 await expect.poll(()=>latest?.elapsed_minutes,{timeout:6000}).toBeGreaterThan(s.elapsed_minutes);
 s=await control('pause',page.getByRole('button',{name:'Pause',exact:true}));
 const paused=s.elapsed_minutes;
 await page.waitForResponse(r=>r.url().includes('/snapshot'));
 await page.waitForResponse(r=>r.url().includes('/snapshot'));
 assert.equal(latest.elapsed_minutes,paused);await assertDisclosure();
 const generation=s.generation;s=await reset();assert.notEqual(s.generation,generation);assert.equal(s.elapsed_minutes,120);
 checks.push('Start, 300x playback, pause stability across polls, five-minute step and reset generation');
 for(const width of [1440,768,390,360])await layout(width);
 await page.locator('#ledger').scrollIntoViewIfNeeded();await expect(disclosure).toBeInViewport();
 checks.push('Persistent disclosure while scrolling the ledger');
 await page.setViewportSize({width:1440,height:1000});
 s=await create('clean','full');assert.equal(s.elapsed_minutes,0);
 await expect(page.locator('.prediction-panel')).toContainText('insufficient history');
 while(s.elapsed_minutes<60)s=await step();
 const forecast=s.forecasts.at(-1);assert.equal(forecast.score,null);
 while(s.elapsed_minutes<85)s=await step();
 assert.equal(s.forecasts.find(f=>f.id===forecast.id).score,null);
 s=await step();assert.equal(s.elapsed_minutes,90);
 assert.equal(s.forecasts.find(f=>f.id===forecast.id).score.reason,'OK');
 await expect(page.locator('#ledger')).toContainText('Matured');
 checks.push('Full chronology, insufficient history, target hidden until exactly +30 minutes, matured score in ledger');
 for(const duration of [15,30,60,120]){
  s=await create('dropout'+duration);
  while(s.elapsed_minutes<180)s=await step();
  assert.equal(s.forecasts.at(-1).value,null);
  await expect(page.locator('.prediction-panel')).toContainText('missing current reading');
  if(duration===15)await screenshot('synthetic-dropout-suppressed.png');
  while(s.elapsed_minutes<180+duration+55){s=await step();assert.equal(s.forecasts.at(-1).value,null)}
  await expect(page.locator('.prediction-panel')).toContainText('incomplete history');
  s=await step();assert.equal(s.elapsed_minutes,180+duration+60);assert.equal(s.forecasts.at(-1).point_reason,'OK');
  assertReveal(s);await assertDisclosure();
  if(duration===15)await screenshot('synthetic-dropout-recovered.png');
  checks.push(`${duration}-minute input loss: suppression, incomplete-history interval, first complete-history recovery at minute ${s.elapsed_minutes}`);
 }
 await page.locator('.signal-panel').scrollIntoViewIfNeeded();
 const segmentCount=latest.history.reduce((state,r)=>({count:state.count+(r.value!==null&&!state.inSegment?1:0),inSegment:r.value!==null}),{count:0,inSegment:false}).count;
 await expect(page.locator('.chart svg path')).toHaveCount(segmentCount);
 assert.deepEqual(errors,[],'Browser console/page errors');
 assert.deepEqual(badApis,[],'Failed API responses');
 assert.deepEqual(failures,[],'Failed browser requests');
 status='PASS';
}catch(e){failure=String(e.message??e).replaceAll(root,'[workspace]');process.exitCode=1;await page.screenshot({path:path.join(root,'data/runtime/stage6/browser_completion/failure.png'),fullPage:true}).catch(()=>{});
}finally{
 for(const [name,hash] of Object.entries(sourceHashes)){if(createHash('sha256').update(await fs.readFile(path.join(root,name))).digest('hex')!==hash){status='FAIL';failure='Tested source changed during browser verification';process.exitCode=1}}
 const report={status,tested_source_sha256:sourceHashes,browser:await browser.version(),headless:true,mode:'independent synthetic only',checks,layouts,screenshots:images,consoleErrors:errors,failedRequests:failures,failedApiResponses:badApis,failure};
 await fs.writeFile(path.join(out,'browser_verification.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report,null,2));
 if(latest?.session_id)await context.request.delete(`http://127.0.0.1:15173/api/replay/sessions/${latest.session_id}`).catch(()=>{});
 await browser.close();
}
