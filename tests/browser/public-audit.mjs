import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const baseUrl = process.env.PUBLIC_BASE_URL || 'https://courtiq-77cz.onrender.com/';
const outputDir = path.resolve('artifacts/public-audit/after');
const routes = [
  'entry', 'train/overview', 'train/analyze', 'train/plan', 'train/learn',
  'train/puzzles', 'train/profile', 'predict/overview', 'predict/match',
  'predict/players', 'predict/compare', 'predict/tournaments',
  'predict/simulation', 'predict/model-lab', 'privacy', 'terms'
];
const viewports = [[320, 568], [360, 800], [375, 812], [390, 844], [412, 915], [768, 1024], [1440, 900]];

function pageAudit() {
  const width = window.innerWidth;
  const visible = [...document.querySelectorAll('body *')].filter(element => {
    if (element.closest('.side:not(.drawer-open)')) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && Number(style.opacity) > 0.01 && rect.width > 0 && rect.height > 0;
  });
  const outsideViewport = visible.flatMap(element => {
    const rect = element.getBoundingClientRect();
    if (rect.left >= -1 && rect.right <= width + 1) return [];
    return [{ tag: element.tagName.toLowerCase(), id: element.id,
      className: String(element.className || '').slice(0, 100),
      left: Math.round(rect.left), right: Math.round(rect.right) }];
  });
  const darkTextOnDark = visible.flatMap(element => {
    if (!element.textContent?.trim() || element.children.length) return [];
    const style = getComputedStyle(element);
    const match = style.color.match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/);
    if (!match) return [];
    const [red, green, blue] = match.slice(1, 4).map(Number);
    if ((.2126 * red + .7152 * green + .0722 * blue) / 255 > .32) return [];
    let node = element;
    for (let depth = 0; node && depth < 6; depth += 1, node = node.parentElement) {
      const nodeStyle = getComputedStyle(node);
      const paint = `${nodeStyle.backgroundColor} ${nodeStyle.backgroundImage}`;
      if (/rgba?\((215, 255, 49|216, 255, 69|205, 252, 57|247, 250, 239|246, 248, 241|245, 241, 232|255, 255, 255)/.test(paint)) return [];
    }
    return [{ tag: element.tagName.toLowerCase(), className: String(element.className || '').slice(0, 100),
      text: element.textContent.trim().slice(0, 100), color: style.color }];
  });
  return { width, scrollWidth: document.documentElement.scrollWidth, outsideViewport, darkTextOnDark };
}

await fs.mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const releasePage = await browser.newPage();
let released = false;
for (let attempt = 0; attempt < 40; attempt += 1) {
  await releasePage.goto(`${baseUrl}?audit=${Date.now()}#predict/model-lab`, { waitUntil: 'networkidle' });
  released = await releasePage.evaluate(() => getComputedStyle(document.querySelector('#page')).overflow === 'visible'
    && getComputedStyle(document.querySelector('.calibration-card')).maxWidth === '100%'
    && [...document.querySelectorAll('link[rel="stylesheet"]')].some(link => link.href.endsWith('responsive-fixes.css?v=4')));
  if (released) break;
  await releasePage.waitForTimeout(15_000);
}
await releasePage.close();
assert.equal(released, true, 'Render did not activate the responsive release within 10 minutes');

const results = [];
const failures = [];
for (const [width, height] of viewports) {
  const page = await browser.newPage({ viewport: { width, height } });
  const consoleErrors = [];
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', error => consoleErrors.push(error.message));
  for (const route of routes) {
    await page.goto(`${baseUrl}?audit=${Date.now()}#${route}`, { waitUntil: 'networkidle' });
    const audit = await page.evaluate(pageAudit);
    const name = `${route.replaceAll('/', '--')}__${width}x${height}.png`;
    await page.screenshot({ path: path.join(outputDir, name), fullPage: true });
    const record = { route, viewport: `${width}x${height}`, screenshot: name, ...audit };
    results.push(record);
    if (audit.scrollWidth > width) failures.push(`${route} ${width}x${height}: scrollWidth ${audit.scrollWidth}`);
    if (audit.outsideViewport.length) failures.push(`${route} ${width}x${height}: off-screen ${JSON.stringify(audit.outsideViewport)}`);
    if (audit.darkTextOnDark.length) failures.push(`${route} ${width}x${height}: dark text ${JSON.stringify(audit.darkTextOnDark)}`);
  }
  if (consoleErrors.length) failures.push(`${width}x${height}: console errors ${JSON.stringify([...new Set(consoleErrors)])}`);
  await page.close();
}

const interactionPage = await browser.newPage({ viewport: { width: 320, height: 568 } });
await interactionPage.goto(`${baseUrl}#entry`, { waitUntil: 'networkidle' });
await interactionPage.getByRole('button', { name: 'Open navigation' }).click();
assert.equal(await interactionPage.locator('.side.drawer-open').count(), 1);
await interactionPage.getByRole('button', { name: 'Overview' }).first().click();
assert.match(interactionPage.url(), /#train\/overview$/);
await interactionPage.goto(`${baseUrl}#predict/match`, { waitUntil: 'networkidle' });
const predictButton = interactionPage.locator('#predict');
if (await predictButton.isEnabled()) {
  await predictButton.click();
  await interactionPage.waitForTimeout(2_000);
  assert.ok(await interactionPage.locator('.result.forecast-result').count() <= 1, 'Match Predictor rendered duplicate results');
}
await interactionPage.goto(`${baseUrl}#train/plan`, { waitUntil: 'networkidle' });
await interactionPage.getByRole('button', { name: /Generate Plan|Regenerate/ }).first().click();
assert.equal((await interactionPage.evaluate(pageAudit)).outsideViewport.length, 0);
await interactionPage.goto(`${baseUrl}#train/puzzles`, { waitUntil: 'networkidle' });
const firstOption = interactionPage.locator('.puzzle-options button').first();
if (await firstOption.count()) await firstOption.click();
assert.equal((await interactionPage.evaluate(pageAudit)).darkTextOnDark.length, 0);
await interactionPage.goto(`${baseUrl}#entry`, { waitUntil: 'networkidle' });
await interactionPage.getByRole('button', { name: 'Coaching help' }).click();
assert.equal((await interactionPage.evaluate(pageAudit)).outsideViewport.length, 0);
await interactionPage.close();

await fs.writeFile(path.resolve('artifacts/public-audit/audit.json'), JSON.stringify({ baseUrl, routes, viewports, results, failures }, null, 2));
await browser.close();
assert.deepEqual(failures, []);
console.log(`Public audit passed: ${results.length} route/viewport screenshots, zero measured overflow or dark-on-dark text failures.`);
