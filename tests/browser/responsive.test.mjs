import assert from 'node:assert/strict';
import test from 'node:test';
import { chromium } from 'playwright';

const baseUrl = process.env.COURTIQ_BROWSER_BASE_URL || 'http://127.0.0.1:8000/';
const routes = [
  'entry', 'train/overview', 'train/analyze', 'train/plan', 'train/learn',
  'train/puzzles', 'train/profile', 'predict/overview', 'predict/match',
  'predict/players', 'predict/compare', 'predict/tournaments',
  'predict/simulation', 'predict/model-lab', 'privacy', 'terms'
];
const viewports = [
  [320, 568], [360, 800], [375, 812], [390, 844], [412, 915],
  [768, 1024], [1440, 900]
];

function contrastRatio(first, second) {
  const luminance = hex => {
    const channels = hex.match(/[a-f\d]{2}/gi).map(value => Number.parseInt(value, 16) / 255);
    const adjusted = channels.map(value => value <= .03928 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
    return .2126 * adjusted[0] + .7152 * adjusted[1] + .0722 * adjusted[2];
  };
  const a = luminance(first);
  const b = luminance(second);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}

test('shared CourtIQ tokens meet WCAG AA contrast targets', () => {
  assert.ok(contrastRatio('#f6f8f1', '#07120e') >= 4.5, 'primary text on surface');
  assert.ok(contrastRatio('#c4cec6', '#07120e') >= 4.5, 'secondary text on surface');
  assert.ok(contrastRatio('#8f9b93', '#050907') >= 4.5, 'muted text on app background');
  assert.ok(contrastRatio('#07120e', '#d7ff31') >= 4.5, 'accent foreground on lime');
});

function renderedLayoutAudit() {
  const viewportWidth = window.innerWidth;
  const visible = [...document.querySelectorAll('body *')].filter(element => {
    if (element.closest('.side:not(.drawer-open)')) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && Number(style.opacity) > 0.01 && rect.width > 0 && rect.height > 0;
  });
  const outsideViewport = visible.flatMap(element => {
    const rect = element.getBoundingClientRect();
    if (rect.left >= -1 && rect.right <= viewportWidth + 1) return [];
    return [{
      tag: element.tagName.toLowerCase(),
      id: element.id,
      className: String(element.className || '').slice(0, 100),
      left: Math.round(rect.left),
      right: Math.round(rect.right)
    }];
  });
  const darkTextOnDark = visible.flatMap(element => {
    if (!element.textContent?.trim() || element.children.length) return [];
    const style = getComputedStyle(element);
    const match = style.color.match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/);
    if (!match) return [];
    const rgb = match.slice(1, 4).map(Number);
    const brightness = (.2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]) / 255;
    if (brightness > .32) return [];
    let node = element;
    let brightSurface = false;
    for (let depth = 0; node && depth < 6; depth += 1, node = node.parentElement) {
      const nodeStyle = getComputedStyle(node);
      const paint = `${nodeStyle.backgroundColor} ${nodeStyle.backgroundImage}`;
      if (/rgb\((215, 255, 49|216, 255, 69|205, 252, 57|247, 250, 239|246, 248, 241|245, 241, 232|255, 255, 255)\)/.test(paint)) brightSurface = true;
    }
    if (brightSurface) return [];
    return [{
      tag: element.tagName.toLowerCase(),
      className: String(element.className || '').slice(0, 100),
      text: element.textContent.trim().slice(0, 100),
      color: style.color
    }];
  });
  return {
    scrollWidth: document.documentElement.scrollWidth,
    viewportWidth,
    outsideViewport,
    darkTextOnDark
  };
}

test('all routes fit every supported viewport with readable dark surfaces', { timeout: 120_000 }, async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const failures = [];
    for (const [width, height] of viewports) {
      await page.setViewportSize({ width, height });
      for (const route of routes) {
        await page.goto(`${baseUrl}#${route}`, { waitUntil: 'networkidle' });
        const audit = await page.evaluate(renderedLayoutAudit);
        if (audit.scrollWidth > width) failures.push(`${route} at ${width}x${height} scrolls to ${audit.scrollWidth}px`);
        if (audit.outsideViewport.length) failures.push(`${route} at ${width}x${height} off-screen: ${JSON.stringify(audit.outsideViewport)}`);
        if (audit.darkTextOnDark.length) failures.push(`${route} at ${width}x${height} dark text: ${JSON.stringify(audit.darkTextOnDark)}`);
      }
    }
    assert.deepEqual(failures, []);
  } finally {
    await browser.close();
  }
});

test('mobile navigation and focus states remain usable', { timeout: 30_000 }, async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 320, height: 568 } });
    await page.goto(`${baseUrl}#entry`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Open navigation' }).click();
    await page.getByRole('button', { name: 'Train overview' }).click();
    await page.waitForURL(/#train\/overview$/);
    assert.equal(await page.locator('#app-sidebar').evaluate(node => node.classList.contains('drawer-open')), false);
    await page.reload({ waitUntil: 'networkidle' });
    await page.keyboard.press('Tab');
    const outline = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
    assert.notEqual(outline, 'none');
  } finally {
    await browser.close();
  }
});
