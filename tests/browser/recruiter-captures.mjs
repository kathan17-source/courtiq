import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from 'playwright';

// Capture the actual local API/app. No route mocks, injected markup, or private uploads.
const base = process.env.COURTIQ_BROWSER_BASE_URL || 'http://127.0.0.1:8000/';
const dir = 'artifacts/recruiter-captures';
await fs.mkdir(dir, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${base}#predict/match`, { waitUntil: 'networkidle' });
  const predictionResponse = page.waitForResponse(r => r.url().endsWith('/api/predict') && r.request().method() === 'POST');
  await page.locator('#predict').click();
  const response = await predictionResponse;
  assert.equal(response.status(), 200);
  const prediction = await response.json();
  assert.equal(prediction.diagnostics.evaluation_status, 'unverified');
  await page.locator('.forecast-result').waitFor();
  assert.match(await page.locator('#prediction-result').innerText(), /unverified/);
  await page.screenshot({ path: `${dir}/predict.png`, fullPage: true });

  await page.goto(`${base}#train/analyze`, { waitUntil: 'networkidle' });
  assert.match(await page.locator('#page').innerText(), /No video selected/);
  await page.screenshot({ path: `${dir}/analyze.png`, fullPage: true });

  await page.goto(`${base}#predict/simulation`, { waitUntil: 'networkidle' });
  const simulationResponse = page.waitForResponse(r => r.url().endsWith('/api/simulate/tournament') && r.request().method() === 'POST');
  await page.locator('#run-sim').click();
  assert.equal((await simulationResponse).status(), 200);
  await page.locator('.champion-list i').first().waitFor();
  assert.match(await page.locator('#page').innerText(), /MODEL-SIMULATED CHAMPION PROBABILITY/);
  await page.screenshot({ path: `${dir}/simulation.png`, fullPage: true });

  await page.goto(`${base}#predict/model-lab`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('.model-terminal')?.textContent.includes('Evaluation unverified'));
  const lab = await page.locator('.model-terminal').innerText();
  assert.ok(lab.includes('Unavailable'));
  for (const retired of ['65.50%', '0.7132', '0.6185', '0.2154', '0.0271']) assert.ok(!lab.includes(retired));
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}
