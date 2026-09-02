/**
 * W1-04 spike — drive the browser harness with Playwright.
 *
 * - runs every probe in src/main.ts and dumps `window.__spike` to out/browser-facts.json
 * - saves the two required PNGs into ../../docs/spikes/img/
 *
 * Prereq: `npm run dev` on http://localhost:5178 (or pass SPIKE_URL).
 * Run:    node scripts/screenshots.mjs
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, '..', 'out');
const IMG = resolve(HERE, '..', '..', '..', 'docs', 'spikes', 'img');
const URL_BASE = process.env.SPIKE_URL ?? 'http://localhost:5178';

mkdirSync(OUT, { recursive: true });
mkdirSync(IMG, { recursive: true });

const browser = await chromium.launch({
  args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--js-flags=--expose-gc'],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 2 });

const consoleLines = [];
page.on('console', (m) => consoleLines.push(`${m.type()}: ${m.text()}`.slice(0, 400)));
page.on('pageerror', (e) => consoleLines.push(`pageerror: ${String(e).slice(0, 400)}`));

await page.goto(`${URL_BASE}/?auto=1`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__spike?.ready === true, null, { timeout: 240000 });

const spike = await page.evaluate(() => window.__spike);
writeFileSync(resolve(OUT, 'browser-facts.json'), JSON.stringify({ ...spike, console: consoleLines }, null, 2));
writeFileSync(
  resolve(OUT, 'roundtrip-browser.dxf'),
  await page.evaluate(() => window.__roundTripDxf ?? '')
);

// --- screenshot 1: Korean fixture with the SHIPPED default font chain.
// TEXT/ATTRIB use STYLE `HANGUL` (big font whgtxt.shx) and render; MTEXT uses
// STYLE `Standard` and falls back to hztxt/simsun/simplex, which have no Hangul.
await page.evaluate(async () => {
  const { FontManager } = await import('/node_modules/@mlightcad/mtext-renderer/dist/index.js');
  FontManager.instance.setDefaultFonts('modern');
  FontManager.instance.setFontMapping({});
});
await page.evaluate(() => window.__spikeOpen('dxf'));
await page.waitForTimeout(5000);
await page.screenshot({ path: resolve(IMG, 'fixture-korean-default-fonts.png') });

// --- screenshot 2: same fixture after the Korean fallback chain is configured
await page.evaluate(() => window.__spikeKoreanFallback());
await page.waitForTimeout(5000);
await page.screenshot({ path: resolve(IMG, 'fixture-korean-mtext.png') });

// --- screenshot 3: the sample DWG from the mlightcad cad-data repository
await page.evaluate(() => window.__spikeOpen('dwg'));
await page.waitForTimeout(9000);
await page.screenshot({ path: resolve(IMG, 'sample-dwg-canteen.png') });

console.log(`facts: ${spike.facts.length}`);
for (const f of spike.facts) console.log(`  ${f.verdict.padEnd(12)} ${f.id}`);
console.log(`png: ${IMG}`);
await browser.close();
