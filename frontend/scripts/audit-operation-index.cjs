/**
 * E2E non distruttivo dell'Indice operazioni bancarie.
 *
 * Le API sono intercettate con fixture: il test attraversa autenticazione,
 * pagina, scelta categoria, scelta cedolino e conferma, senza contattare o
 * modificare il database reale.
 */
let chromium;
try {
  ({ chromium } = require('playwright-core'));
} catch {
  ({ chromium } = require('/opt/node22/lib/node_modules/playwright/node_modules/playwright-core'));
}

const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:4173';
const EXE = process.env.PLAYWRIGHT_CHROMIUM || undefined;

const categories = [
  { id: 'fornitore', label: 'Fornitore (senza fattura)', target_type: 'supplier', requires_target: true, help: 'Scegli il fornitore.' },
  { id: 'fattura', label: 'Fornitore / fattura', target_type: 'invoice', requires_target: true, help: 'Scegli la fattura.' },
  { id: 'cedolino', label: 'Cedolino / dipendente', target_type: 'payslip', requires_target: true, help: 'Scegli il cedolino.' },
  { id: 'f24', label: 'F24', target_type: 'f24_model', requires_target: true, help: 'Scegli il modello.' },
  { id: 'noleggio', label: 'Noleggio / veicolo', target_type: 'rental_vehicle', requires_target: true, help: 'Scegli targa e veicolo.' },
  { id: 'verbale', label: 'Verbale', target_type: 'fine', requires_target: true, help: 'Scegli il verbale.' },
  { id: 'altro', label: 'Altro', target_type: null, requires_target: false, help: 'Aggiungi una nota.' },
];

const indexPayload = {
  year: 2026,
  total_rows: 1,
  loaded_rows: 1,
  categories,
  automation: 'disabled_for_manual_index',
  rows: [{
    id: 'movement-e2e',
    date: '2026-08-03',
    type: 'uscita',
    amount_cents: 150000,
    description: 'VOSTRA DISPOSIZIONE CERALDI VALERIO STIPENDIO LUGLIO 2026',
    index_status: 'da_classificare',
    decision: null,
  }],
};

async function auditViewport(browser, viewport) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript(() => {
    localStorage.setItem('auth_token', 'fixture-token');
    localStorage.setItem('annoGlobale', '2026');
  });
  const page = await context.newPage();
  let savedPayload = null;
  const browserErrors = [];
  page.on('pageerror', error => browserErrors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });

  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = request.url();
    if (url.includes('/api/auth/verify')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ user: { id: 'e2e', name: 'Operatore', role: 'admin' } }) });
    }
    if (url.includes('/api/config-import/anno')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ anno: 2026 }) });
    }
    if (url.includes('/indice-operazioni/movement-e2e/candidati')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        matching: 'manual_only',
        candidates: [{ id: 'payslip-e2e', label: 'Valerio Ceraldi - 2026-07', date: '2026-07-31', amount_cents: 150000 }],
      }) });
    }
    if (url.includes('/indice-operazioni/movement-e2e') && request.method() === 'PUT') {
      savedPayload = request.postDataJSON();
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ saved: true, source_unchanged: true, payment_status_changed: false }) });
    }
    if (url.includes('/api/prima-nota/indice-operazioni')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(indexPayload) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });

  await page.goto(`${BASE}/riconciliazione/movimenti-banca`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  try {
    await page.getByRole('heading', { name: 'Indice operazioni bancarie' }).waitFor({ timeout: 20000 });
  } catch (error) {
    const body = await page.locator('body').innerText().catch(() => 'body non leggibile');
    throw new Error(`Pagina non raggiunta (${page.url()}): ${body.slice(0, 1200)} | errori=${browserErrors.join(' || ') || 'nessuno'} | ${error}`);
  }
  await page.getByRole('button', { name: 'Classifica' }).click();
  await page.getByRole('button', { name: /Cedolino \/ dipendente/ }).click();
  await page.getByText('Valerio Ceraldi - 2026-07').click();
  await page.getByRole('button', { name: /Conferma scelta/ }).click();
  await page.waitForTimeout(300);

  if (!savedPayload || savedPayload.category !== 'cedolino' || savedPayload.target_id !== 'payslip-e2e') {
    throw new Error(`Payload manuale errato su ${viewport.width}px: ${JSON.stringify(savedPayload)}`);
  }
  if (await page.getByText('Collegare alla riga esistente').count()) {
    throw new Error('La vecchia proposta automatica e ancora visibile');
  }
  const overflow = await page.locator('[data-testid="manual-operation-index"]').evaluate(node => node.scrollWidth > node.clientWidth + 2);
  if (overflow) throw new Error(`Overflow orizzontale indice su ${viewport.width}px`);
  await context.close();
  return `${viewport.width}x${viewport.height}: OK`;
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: EXE });
  try {
    const results = [];
    for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }]) {
      results.push(await auditViewport(browser, viewport));
    }
    console.log(`INDICE OPERAZIONI E2E OK\n${results.join('\n')}`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
