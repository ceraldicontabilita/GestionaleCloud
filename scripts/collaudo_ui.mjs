/**
 * COLLAUDO UI (18/07/2026) — apre OGNI pagina del gestionale con un browser
 * vero e registra: errori JavaScript, chiamate API fallite (>=400), pagine
 * bianche. NON clicca mai bottoni che mutano dati (gira contro l'API di
 * produzione): il collaudo fotografa, non tocca.
 *
 * Uso (dalla sandbox di sviluppo):
 *   1. avvia il server locale che serve frontend/dist e proxa /api al prod
 *   2. AUTH_TOKEN=... BASE_URL=http://localhost:8777 node scripts/collaudo_ui.mjs
 *
 * Output: report JSON su stdout + screenshot dei problemi in OUT_DIR.
 */
import { createRequire } from 'module';
import { readFileSync, mkdirSync } from 'fs';

const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('playwright-core');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8777';
const AUTH_TOKEN = process.env.AUTH_TOKEN || '';
const OUT_DIR = process.env.OUT_DIR || '/tmp/collaudo-ui';
const EXECUTABLE = process.env.CHROMIUM_PATH || undefined;
const VERBALE_TEST_ID = (process.env.VERBALE_TEST_ID || '').trim();

// Fonte unica: lo stesso catalogo numerato usato da test, smoke ed E2E.
// Leggere solo main.jsx produceva appena le route hub e saltava le schermate
// interne (il numero reale viene letto dal catalogo, non dalle circa 30
// registrazioni React principali).
function rotte() {
  const catalog = JSON.parse(
    readFileSync(new URL('../page_catalog.json', import.meta.url), 'utf8')
  );
  return catalog.pages
    .map(page => {
      if (!page.path.includes(':')) return page.path;
      if (page.id === 15 && VERBALE_TEST_ID) {
        return `/verbali-noleggio/${encodeURIComponent(VERBALE_TEST_ID)}`;
      }
      return null;
    })
    .filter(Boolean);
}

// Rumore noto da ignorare (non sono difetti del gestionale)
const IGNORA = [
  /favicon/i,
  /ResizeObserver loop/i,
  /WebSocket/i, // il proxy locale non inoltra ws:// — non è un difetto del gestionale
];

const main = async () => {
  mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({
    ...(EXECUTABLE ? { executablePath: EXECUTABLE } : {}),
    args: ['--no-sandbox'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(token => {
    window.localStorage.setItem('auth_token', token);
  }, AUTH_TOKEN);

  const report = [];
  for (const rotta of rotte()) {
    const pagina = await ctx.newPage();
    const problemi = [];
    pagina.on('pageerror', err => problemi.push({ tipo: 'js_error', dettaglio: String(err).slice(0, 200) }));
    pagina.on('console', msg => {
      if (msg.type() === 'error' && !IGNORA.some(r => r.test(msg.text()))) {
        problemi.push({ tipo: 'console_error', dettaglio: msg.text().slice(0, 200) });
      }
    });
    pagina.on('response', res => {
      const url = res.url();
      if (url.includes('/api/') && res.status() >= 400) {
        problemi.push({ tipo: 'api_fallita', dettaglio: `${res.status()} ${res.request().method()} ${new URL(url).pathname}` });
      }
    });

    let esito = 'ok';
    try {
      await pagina.goto(`${BASE_URL}${rotta}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await pagina.waitForTimeout(3500); // lascia finire le chiamate iniziali
      const testo = (await pagina.textContent('body').catch(() => '')) || '';
      if (testo.trim().length < 40) problemi.push({ tipo: 'pagina_vuota', dettaglio: `solo ${testo.trim().length} caratteri` });
      if (/pagina non trovata/i.test(testo)) problemi.push({ tipo: 'not_found', dettaglio: 'rotta finita su PaginaNonTrovata' });
    } catch (e) {
      problemi.push({ tipo: 'navigazione_fallita', dettaglio: String(e).slice(0, 200) });
    }

    // dedup problemi identici
    const visti = new Set();
    const unici = problemi.filter(p => {
      const k = `${p.tipo}|${p.dettaglio}`;
      if (visti.has(k)) return false;
      visti.add(k);
      return true;
    });
    if (unici.length) {
      esito = 'problemi';
      await pagina.screenshot({ path: `${OUT_DIR}/${rotta.replace(/\//g, '_') || 'home'}.png`, fullPage: false }).catch(() => {});
    }
    report.push({ rotta, esito, problemi: unici });
    process.stderr.write(`${esito === 'ok' ? '✓' : '✗'} ${rotta} (${unici.length})\n`);
    await pagina.close();
  }

  await browser.close();
  const conProblemi = report.filter(r => r.esito !== 'ok');
  console.log(JSON.stringify({
    base_url: BASE_URL,
    rotte_totali: report.length,
    rotte_ok: report.length - conProblemi.length,
    rotte_con_problemi: conProblemi.length,
    dettaglio: conProblemi,
  }, null, 1));
};

main().catch(e => { console.error(e); process.exit(1); });
