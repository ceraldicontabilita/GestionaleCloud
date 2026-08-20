/**
 * Collaudo di apertura delle 62 schermate operative contro l'ERP isolato.
 *
 * Usa router backend reali e MongoDB in memoria (vedi
 * scripts/e2e_distruttivo_server.py). Non legge e non modifica dati aziendali.
 * Il catalogo pagina -> componente e la stessa fonte usata dallo smoke runtime.
 */
const { createHmac } = require('crypto');
const { readFileSync } = require('fs');
const { resolve } = require('path');
const { chromium } = require('playwright-core');

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:8788';
const EXE = process.env.PLAYWRIGHT_CHROMIUM
  || (process.platform === 'win32'
    ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    : undefined);
const ROOT = resolve(__dirname, '..', '..');
const catalog = JSON.parse(readFileSync(resolve(ROOT, 'page_catalog.json'), 'utf8'));
const TEST_SECRET = 'e2e-isolato-solo-test-non-produzione';

const IGNORE_CONSOLE = [
  /favicon/i,
  /ResizeObserver loop/i,
  /WebSocket/i,
  /Download the React DevTools/i,
];

function base64url(value) {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function adminToken() {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url({ alg: 'HS256', typ: 'JWT' });
  const payload = base64url({
    sub: 'e2e@example.invalid',
    email: 'e2e@example.invalid',
    name: 'E2E admin',
    role: 'admin',
    iat: now,
    exp: now + 1800,
  });
  const signature = createHmac('sha256', TEST_SECRET)
    .update(`${header}.${payload}`)
    .digest('base64url');
  return `${header}.${payload}.${signature}`;
}

function uniqueProblems(problems) {
  const seen = new Set();
  return problems.filter(problem => {
    const key = `${problem.type}|${problem.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

(async () => {
  if (catalog.pages.length !== 64) {
    throw new Error(`Catalogo incompleto: attese 64 pagine, trovate ${catalog.pages.length}`);
  }

  const browser = await chromium.launch(EXE ? { executablePath: EXE } : {});
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const token = adminToken();
  await context.addInitScript(({ authToken }) => {
    localStorage.setItem('auth_token', authToken);
    localStorage.setItem('ceraldi_anno_globale', '2026');
  }, { authToken: token });

  const results = [];
  for (const definition of catalog.pages) {
    const path = definition.e2e_path || definition.path;
    const page = await context.newPage();
    const problems = [];
    const allowedStatuses = new Set(definition.allowed_api_statuses || []);

    await page.routeWebSocket('**', socket => socket.close());
    page.on('pageerror', error => {
      problems.push({ type: 'javascript', detail: String(error).slice(0, 240) });
    });
    page.on('console', message => {
      const detail = message.text();
      // Le pagine di dettaglio possono dichiarare un 404 di fixture come
      // stato vuoto atteso. Chromium emette anche un generico console error
      // per la stessa risposta: non va contato due volte come difetto pagina.
      if (allowedStatuses.has(404) && /Failed to load resource.*404/i.test(detail)) return;
      if (message.type() === 'error' && !IGNORE_CONSOLE.some(pattern => pattern.test(detail))) {
        problems.push({ type: 'console', detail: detail.slice(0, 240) });
      }
    });
    page.on('response', response => {
      if (!response.url().includes('/api/') || response.status() < 400) return;
      if (allowedStatuses.has(response.status())) return;
      const url = new URL(response.url());
      problems.push({
        type: 'api',
        detail: `${response.status()} ${response.request().method()} ${url.pathname}`,
      });
    });

    try {
      await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(1200);
      const bodyText = ((await page.textContent('body').catch(() => '')) || '').trim();
      if (bodyText.length < 30) {
        problems.push({ type: 'empty', detail: `Body con soli ${bodyText.length} caratteri` });
      }
      if (await page.getByTestId('pagina-non-trovata').count()) {
        problems.push({ type: 'route', detail: 'La route ha aperto PaginaNonTrovata' });
      }
      if (await page.getByTestId('error-boundary').count()) {
        problems.push({ type: 'react', detail: 'ErrorBoundary visibile' });
      }
      if (path === '/fatture') {
        await page.getByRole('columnheader', { name: 'Documento' }).waitFor({ timeout: 10000 });
        await page.getByRole('columnheader', { name: 'Azione' }).waitFor({ timeout: 10000 });
        const rows = page.locator('tbody tr');
        if (await rows.count() !== 3) {
          problems.push({ type: 'fixture', detail: `Attese 3 fatture E2E, trovate ${await rows.count()}` });
        }

        const positions = await rows.evaluateAll(elements => elements.map(row => {
          const view = [...row.querySelectorAll('button')].find(button => button.textContent.trim() === 'Vedi');
          const link = [...row.querySelectorAll('button')].find(button => button.textContent.trim() === 'Abbina');
          const viewRect = view?.getBoundingClientRect();
          const linkRect = link?.getBoundingClientRect();
          return {
            type: row.textContent.includes('TD04') ? 'credit_note' : 'invoice',
            viewX: viewRect?.x,
            viewY: viewRect?.y,
            linkX: linkRect?.x,
            linkY: linkRect?.y,
          };
        }));
        const invoices = positions.filter(position => position.type === 'invoice');
        const credit = positions.find(position => position.type === 'credit_note');
        const sameColumn = (values) => values.length > 0
          && Math.max(...values) - Math.min(...values) <= 1;
        if (positions.some(position => !Number.isFinite(position.viewX))) {
          problems.push({ type: 'layout', detail: 'Una fattura non espone il pulsante Vedi' });
        }
        if (invoices.some(position => !Number.isFinite(position.linkX))) {
          problems.push({ type: 'layout', detail: 'Una fattura pagabile non espone il pulsante Abbina' });
        }
        if (!sameColumn(positions.map(position => position.viewX).filter(Number.isFinite))) {
          problems.push({ type: 'layout', detail: 'I pulsanti Vedi non sono allineati nella stessa colonna' });
        }
        if (!sameColumn(invoices.map(position => position.linkX).filter(Number.isFinite))) {
          problems.push({ type: 'layout', detail: 'I pulsanti Abbina non sono allineati nella stessa colonna' });
        }
        if (invoices.some(position => Math.abs(position.viewY - position.linkY) > 1)) {
          problems.push({ type: 'layout', detail: 'Vedi e Abbina non sono centrati sulla stessa riga' });
        }
        if (!credit || Number.isFinite(credit.linkX)) {
          problems.push({ type: 'accounting', detail: 'La nota di credito espone ancora Abbina assegno' });
        }
      }
    } catch (error) {
      problems.push({ type: 'navigation', detail: String(error).slice(0, 240) });
    }

    const unique = uniqueProblems(problems);
    results.push({
      id: definition.id,
      label: definition.label,
      path,
      ok: unique.length === 0,
      problems: unique,
    });
    process.stderr.write(`${unique.length ? 'FAIL' : 'OK  '} ${String(definition.id).padStart(2, '0')} ${path} (${unique.length})\n`);
    await page.close();
  }

  await browser.close();
  const failed = results.filter(result => !result.ok);
  console.log(JSON.stringify({
    catalog_pages: results.length,
    passed: results.length - failed.length,
    failed: failed.length,
    failures: failed,
  }, null, 2));
  if (failed.length) process.exit(1);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
