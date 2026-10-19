/** Current synthetic-only responsive smoke check. Does not start/stop user services.
 * node scripts/verify_responsive_browser.mjs --url http://127.0.0.1:PORT --output TEMP_DIR
 * CSS zoom is measured separately; native browser zoom is not automated.
 */
import {createRequire} from 'node:module';
import {parseArgs} from 'node:util';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {values}=parseArgs({options:{url:{type:'string'},output:{type:'string'}}});
if(!values.url||!values.output)throw Error('Required: --url LOOPBACK_URL --output NEW_EXTERNAL_DIRECTORY');
const url=new URL(values.url);
if(!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw Error('Use a dedicated loopback application instance.');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=path.resolve(values.output);
if(out===root||out.startsWith(root+path.sep))throw Error('Output must be outside source.');
await fs.mkdir(out); // Refuse existing evidence directories.
const require=createRequire(path.join(root,'frontend/package.json'));
const {chromium,expect}=require('@playwright/test');
const results=[],errors=[],failed=[];let browser;
try{
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
  page.on('requestfailed',r=>failed.push(r.url()+': '+r.failure()?.errorText));
  page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)failed.push(r.url()+': '+r.status())});
  await page.goto(url.href,{waitUntil:'networkidle'});
  await page.getByRole('combobox',{name:'Source',exact:true}).selectOption('synthetic-dawn');
  await page.getByRole('button',{name:/^Create (demo |new )?session$/}).click();
  await expect(page.locator('.recovery-panel')).toContainText('61 of 61');
  // Five normal viewports plus the separately reproduced CSS zoom condition.
  // Native browser UI zoom is deliberately not represented by either method.
  for(const {zoom,width} of [...[360,390,720,1024,1440].map(width=>({zoom:1,width})),{zoom:2,width:720}]){
    await page.setViewportSize({width,height:1100});
    await page.evaluate(z=>{document.documentElement.style.zoom=String(z)},zoom);
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const metrics=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
      offenders:[...document.querySelectorAll('.topbar,.topbar-actions,.transport,.transport-actions,.speed,.replay-clock')].map(e=>({class:e.className,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))}));
    results.push({width,cssZoom:zoom,...metrics});
    await page.screenshot({path:path.join(out,`synthetic-${width}-css${zoom}.png`)});
    assert.ok(metrics.scroll<=metrics.client+1,`Horizontal overflow at ${width}px CSS zoom${zoom}: ${JSON.stringify(metrics)}`);
    for(const e of metrics.offenders)assert.ok(e.left>=-1&&e.right<=width+1,`Clipped control group: ${e.class}`);
    const step=page.getByRole('button',{name:'Step 5 min',exact:true});
    await step.focus();await expect(step).toBeFocused();await page.keyboard.press('Enter');await expect(step).toBeEnabled();
    const speed=page.getByRole('button',{name:'Playback speed 300x'});
    await speed.click();await expect(speed).toHaveAttribute('aria-pressed','true');
    await page.getByRole('button',{name:'Start / resume',exact:true}).click();
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    await page.getByRole('button',{name:'Reset replay',exact:true}).click();
    await expect(page.locator('.recovery-panel')).toContainText('Continuous run: 121');
    results.at(-1).controls='PASS: keyboard step, speed300, start, pause, reset';
  }
  assert.equal(errors.length,0);assert.equal(failed.length,0);
}catch(e){results.push({failure:String(e)});process.exitCode=1}
finally{
  await fs.writeFile(path.join(out,'responsive-results.json'),JSON.stringify({nativeZoom:'NOT RUN; CSS zoom is separate',results,errors,failed},null,2));
  if(browser)await browser.close();
}
