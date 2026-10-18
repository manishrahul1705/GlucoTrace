/**
 * Verification of Stage 3 (Mode Capability Clarity) & Stage 4 (History Recovery Explanation)
 * in real headless Chromium browser across viewports (1440, 768, 390, 360px).
 */
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const {chromium, expect} = require('@playwright/test');
const out = path.join(root, 'reports/capability_recovery');
await fs.mkdir(out, {recursive: true});

const errors = [];
const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1});
const page = await context.newPage();

page.on('pageerror', e => errors.push(String(e)));
page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

const checks = [];

try {
  await page.goto('http://127.0.0.1:15173/', {waitUntil: 'networkidle'});

  // 1. Create a warm-start clean session
  const waitPost = page.waitForResponse(r => r.url().includes('/api/replay/sessions') && r.request().method() === 'POST');
  await page.getByRole('button', {name: /^Create (new )?session$/}).click();
  const res = await waitPost;
  assert.equal(res.status(), 200);
  const snap = await res.json();
  assert.equal(snap.mode, 'synthetic');

  // 2. Verify Recovery Panel elements (Stage 4)
  const recPanel = page.locator('.recovery-panel');
  await expect(recPanel).toBeVisible();
  await expect(recPanel).toContainText('HISTORY SUPPORT & RECOVERY STATUS');
  await expect(recPanel).toContainText('61 consecutive minute cells spanning 60 elapsed minutes');
  await expect(recPanel).toContainText('Current Valid Support');
  await expect(recPanel).toContainText('Next Issue Eligibility');
  await expect(recPanel).toContainText('Suppression Status & Reason');
  await expect(recPanel).toContainText('Conditional Recovery Estimate');
  await expect(recPanel).toContainText('Calculated strictly from revealed history and 5-min issue grid without future-schedule knowledge');
  checks.push('Stage 4: History support & recovery panel renders all required fields and disclaimer');

  // 3. Verify Mode Capability Card in Prediction Panel (Stage 3)
  const capCard = page.locator('.capability-card');
  await expect(capCard).toBeVisible();
  await expect(capCard).toContainText('INDEPENDENT SYNTHETIC');
  await expect(capCard).toContainText('Horizon: +30 min');
  await expect(capCard).toContainText('Active Session:');
  await expect(capCard).toContainText('Scripted day / independent synthetic');
  await expect(capCard).toContainText('Predictor');
  await expect(capCard).toContainText('Scripted Persistence baseline');
  await expect(capCard).toContainText('Variants');
  await expect(capCard).toContainText('persistence (sensor-only baseline)');
  await expect(capCard).toContainText('Point Availability');
  await expect(capCard).toContainText('Evaluation Status');
  await expect(capCard).toContainText('Interval Calibration');
  await expect(capCard).toContainText('Unavailable in synthetic mode (no synthetic interval calibration)');
  await expect(capCard).toContainText('Evidence Boundary:');
  checks.push('Stage 3: Mode capability card consolidates predictor, variants, horizon, availability, calibration and boundary');

  // 4. Verify nominal interval shows Unavailable indicator in synthetic mode
  const nominal = page.locator('.nominal');
  await expect(nominal).toContainText('(Unavailable in Synthetic)');
  checks.push('Stage 3: Nominal interval selector indicates unavailable status in synthetic mode');

  // 5. Test Decoupling: Change dropdown selection without creating new session
  await page.getByRole('combobox', {name: 'Source', exact: true}).selectOption({index: 1}); // select local source
  await page.waitForTimeout(300);

  // Capability card must still reflect active session as Synthetic, while showing dropdown configuration as pending
  await expect(capCard.locator('.source-alignment-row.mismatch')).toBeVisible();
  await expect(capCard.locator('.source-alignment-row.mismatch')).toContainText('Configured in Dropdown:');
  await expect(capCard.locator('.source-alignment-row.mismatch')).toContainText('Pending (applies to next session)');
  await expect(capCard.locator('.capability-mode-badge')).toContainText('INDEPENDENT SYNTHETIC');
  checks.push('Stage 3: Active session snapshot remains authoritative when dropdown selection changes');

  // 6. Test Dropout Scenario: Create dropout30 session and verify recovery progression
  await page.getByRole('combobox', {name: 'Source', exact: true}).selectOption('synthetic-dawn');
  await page.getByRole('combobox', {name: 'Input scenario', exact: true}).selectOption('dropout30');
  const waitDrop = page.waitForResponse(r => r.url().includes('/api/replay/sessions') && r.request().method() === 'POST');
  await page.getByRole('button', {name: /^Create (new )?session$/}).click();
  const dropSnap = await (await waitDrop).json();
  assert.equal(dropSnap.gap.label, '30-minute simulated input dropout');
  checks.push('Stage 4: Gap label authoritatively reported as "simulated input dropout"');

  // Advance to minute 185 (inside dropout)
  while (dropSnap.elapsed_minutes < 180) {
    const waitStep = page.waitForResponse(r => r.url().endsWith('/control'));
    await page.getByRole('button', {name: 'Step 5 min'}).click();
    const s = await (await waitStep).json();
    dropSnap.elapsed_minutes = s.elapsed_minutes;
  }
  await expect(recPanel).toContainText('Forecasts Suppressed');
  await expect(recPanel).toContainText('Simulated input dropout active: current reading is missing');
  await expect(recPanel).toContainText('Awaiting continuous valid input arrival');
  checks.push('Stage 4: Active simulated input dropout shows suppression reason and awaiting input arrival');

  // Advance past dropout to minute 210
  while (dropSnap.elapsed_minutes < 210) {
    const waitStep = page.waitForResponse(r => r.url().endsWith('/control'));
    await page.getByRole('button', {name: 'Step 5 min'}).click();
    const s = await (await waitStep).json();
    dropSnap.elapsed_minutes = s.elapsed_minutes;
  }
  await expect(recPanel).toContainText('Earliest eligible issue if readings continue without interruption: Minute 270');
  checks.push('Stage 4: Post-dropout recovery correctly projects earliest eligible issue at Minute 270');

  // 7. Verify layout at 1440, 768, 390, 360px
  for (const width of [1440, 768, 390, 360]) {
    await page.setViewportSize({width, height: (width <= 400 ? 844 : 1000)});
    await page.waitForTimeout(200);
    const overflow = await page.evaluate(() => {
      const el = document.documentElement;
      return {
        clientWidth: el.clientWidth,
        scrollWidth: el.scrollWidth,
        overflowing: el.scrollWidth > el.clientWidth + 1
      };
    });
    assert.equal(overflow.overflowing, false, `Horizontal overflow at ${width}px: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`);
    await page.screenshot({path: path.join(out, `viewport-${width}.png`), fullPage: false});
  }
  checks.push('Stage 5: Clean responsive layout verified at 1440px, 768px, 390px, and 360px without horizontal overflow');

  assert.deepEqual(errors, [], 'No browser console errors');

  const report = {
    status: 'PASS',
    checks,
    viewports: [1440, 768, 390, 360],
    screenshots: [
      'reports/capability_recovery/viewport-1440.png',
      'reports/capability_recovery/viewport-768.png',
      'reports/capability_recovery/viewport-390.png',
      'reports/capability_recovery/viewport-360.png'
    ],
    timestamp: new Date().toISOString()
  };
  await fs.writeFile(path.join(out, 'browser_capability_recovery_verification.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));

} catch (err) {
  console.error('Verification failed:', err);
  process.exitCode = 1;
} finally {
  await browser.close();
}
