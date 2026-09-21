/**
 * Collaudo isolato: CRUD via HTTP reale e rilettura nel browser.
 * Rifiuta host non locali e server privi dell'identificativo E2E.
 * Le schermate contengono soltanto le fixture del server di collaudo.
 */
const assert = require('node:assert/strict');
const { createHmac } = require('node:crypto');
const { mkdirSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { chromium } = require('playwright-core');

const BASE = (process.env.E2E_BASE_URL || 'http://127.0.0.1:8788').replace(/\/+$/, '');
const EXE = process.env.PLAYWRIGHT_CHROMIUM
  || (process.platform === 'win32'
    ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    : undefined);
const OUT = resolve(process.env.E2E_SCREENSHOTS_DIR || '/tmp/prima-nota-e2e');
const TEST_SECRET = 'e2e-isolato-solo-test-non-produzione';

function assertLocalTarget(base) {
  const url = new URL(base);
  assert(['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname),
    'Collaudo distruttivo vietato su host non locali');
  assert.equal(url.protocol, 'http:', 'Il server E2E deve usare HTTP locale');
  assert(!url.username && !url.password, 'Credenziali nella URL non ammesse');
}

function base64url(value) {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function tokenPerRuolo(role) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url({ alg: 'HS256', typ: 'JWT' });
  const payload = base64url({
    sub: `${role}@example.invalid`, email: `${role}@example.invalid`,
    name: `E2E ${role}`, role, iat: now, exp: now + 900,
  });
  const signature = createHmac('sha256', TEST_SECRET)
    .update(`${header}.${payload}`).digest('base64url');
  return `${header}.${payload}.${signature}`;
}

function assertAmount(actual, expected, label) {
  assert(Number.isFinite(Number(actual)), `${label}: importo non numerico`);
  assert(Math.abs(Number(actual) - expected) < 0.01,
    `${label}: trovato ${actual}, atteso ${expected}`);
}

async function run() {
  assertLocalTarget(BASE);
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch(EXE ? { executablePath: EXE } : {});
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    // Prima di QUALSIASI mutazione: anche un proxy locale verso produzione
    // deve essere respinto. Nessun token o dato aziendale viene utilizzato.
    const health = await context.request.get(`${BASE}/api/health`, { maxRedirects: 0 });
    assert(health.ok(), `Server E2E non disponibile: HTTP ${health.status()}`);
    assert.equal((await health.json()).environment, 'e2e-isolato',
      'Mutazioni vietate: il server non dichiara ambiente e2e-isolato');

    const login = await context.request.post(`${BASE}/api/auth/login`, {
      data: { email: 'e2e@example.invalid', password: 'e2e-password-solo-test' },
      maxRedirects: 0,
    });
    assert(login.ok(), `Login E2E fallito: HTTP ${login.status()}`);
    const adminToken = (await login.json()).access_token;
    assert(adminToken, 'Login E2E senza token');
    const headers = { Authorization: `Bearer ${adminToken}` };
    const call = async (method, path, data, expectedStatus = 200) => {
      const response = await context.request[method](`${BASE}${path}`, {
        headers, data, maxRedirects: 0,
      });
      assert.equal(response.status(), expectedStatus,
        `${method.toUpperCase()} ${path}: HTTP ${response.status()} ${await response.text()}`);
      return response.json();
    };
    const cassa = () => call('get', '/api/prima-nota/cassa?anno=2026&limit=200');
    const banca = () => call('get', '/api/prima-nota/banca?anno=2026&limit=200');
    const scadenze = async () => (await call('get',
      '/api/scadenze/tutte?anno=2026&tipo=CUSTOM&include_passate=true&limit=50')).scadenze || [];

    await context.addInitScript(({ token }) => {
      localStorage.setItem('auth_token', token);
      localStorage.setItem('ceraldi_anno_globale', '2026');
    }, { token: adminToken });
    const page = await context.newPage();
    await page.routeWebSocket('**', socket => socket.close());
    const screenshots = [];
    const capture = async name => {
      await page.screenshot({ path: resolve(OUT, name), fullPage: true });
      screenshots.push(name);
    };
    try {
      await page.goto(`${BASE}/scadenze`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.locator('select')
        .filter({ has: page.locator('option[value="CUSTOM"]') }).selectOption('CUSTOM');
      const riga = page.getByTestId('scadenze-table').locator('tbody tr')
        .filter({ hasText: 'COLLAUDO E2E - cancellami' }).first();
      await riga.getByTitle('Elimina').click();
      await page.getByTestId('confirm-dialog-cancel').click();
      assert((await scadenze()).some(s => s.id === 'e2e-scadenza-da-eliminare'),
        'Annulla ha cancellato la scadenza');
      await riga.getByTitle('Elimina').click();
      const eliminazione = page.waitForResponse(r => r.request().method() === 'DELETE'
        && r.url().endsWith('/api/scadenze/e2e-scadenza-da-eliminare'));
      await page.getByTestId('confirm-dialog-confirm').click();
      assert.equal((await eliminazione).status(), 200);
      await page.getByText('COLLAUDO E2E - cancellami').waitFor({ state: 'detached' });
      assert(!(await scadenze()).some(s => s.id === 'e2e-scadenza-da-eliminare'),
        'La scadenza confermata risulta ancora presente');

      const creato = await call('post', '/api/prima-nota/cassa', {
        data: '2026-09-21', tipo: 'entrata', importo: 100,
        descrizione: 'COLLAUDO E2E CASSA CRUD', categoria: 'Altro',
      });
      assert(creato.id, 'Creazione Cassa senza id');
      await call('put', `/api/prima-nota/cassa/${creato.id}`, {
        importo: 125, descrizione: 'COLLAUDO E2E CASSA CRUD MODIFICATO',
      });
      const cassaCrud = (await cassa()).movimenti.find(m => m.id === creato.id);
      assert(cassaCrud, 'Movimento Cassa non persistito');
      assertAmount(cassaCrud.importo, 125, 'Importo Cassa modificato');
      assert.equal(cassaCrud.descrizione, 'COLLAUDO E2E CASSA CRUD MODIFICATO');
      await page.goto(`${BASE}/prima-nota`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.getByText('COLLAUDO E2E CASSA CRUD MODIFICATO', { exact: false })
        .first().waitFor({ timeout: 10000 });
      await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
      await page.getByText('COLLAUDO E2E CASSA CRUD MODIFICATO', { exact: false })
        .first().waitFor({ timeout: 10000 });
      await capture('cassa-dopo-ricarica.png');
      await call('delete', `/api/prima-nota/cassa/${creato.id}?force=true`);
      assert(!(await cassa()).movimenti.some(m => m.id === creato.id),
        'Movimento Cassa archiviato ancora visibile');

      await call('post', '/api/prima-nota/provvisori/conferma', {
        fattura_id: 'e2e-fattura-cassa', metodo: 'cassa',
      });
      const pagamentoCassa = (await cassa()).movimenti.find(m => m.fattura_id === 'e2e-fattura-cassa');
      assert(pagamentoCassa, 'Conferma Cassa senza movimento');
      assertAmount(pagamentoCassa.importo, 90, 'Pagamento Cassa');
      await call('post', '/api/prima-nota/provvisori/conferma', {
        fattura_id: 'e2e-fattura-banca-attesa', metodo: 'banca',
      }, 409);
      await call('post', '/api/prima-nota/provvisori/attendi-banca', {
        fattura_id: 'e2e-fattura-banca-attesa',
      });
      assert(!(await banca()).movimenti.some(m => m.fattura_id === 'e2e-fattura-banca-attesa'),
        'Attendi banca ha creato una falsa scrittura bancaria');
      await call('post', '/api/prima-nota/provvisori/conferma', {
        fattura_id: 'e2e-fattura-banca-prova', metodo: 'banca',
        movimento_banca_id: 'e2e-ec-banca-prova',
      });
      const pagamentoBanca = (await banca()).movimenti.find(m => m.fattura_id === 'e2e-fattura-banca-prova');
      assert(pagamentoBanca, 'Pagamento Banca con prova assente');
      assertAmount(pagamentoBanca.importo, 160, 'Pagamento Banca');
      assert.equal(pagamentoBanca.riconciliato, true);
      await call('post', '/api/prima-nota/provvisori/conferma-divisione', {
        fattura_id: 'e2e-fattura-mista', importo_cassa: 40, importo_banca: 60, performed_by: 'e2e',
      });
      const cassaPayload = await cassa();
      const bancaPayload = await banca();
      const quotaCassa = cassaPayload.movimenti.find(m => m.fattura_id === 'e2e-fattura-mista');
      assert(quotaCassa, 'Quota Cassa mista assente');
      assertAmount(quotaCassa.importo, 40, 'Quota Cassa mista');
      assert(!bancaPayload.movimenti.some(m => m.fattura_id === 'e2e-fattura-mista'),
        'Pagamento misto: quota Banca inventata senza estratto conto');
      const provPayload = await call('get', '/api/prima-nota/provvisori?anno=2026');
      const attesa = (provPayload.in_attesa_banca || []).find(p => p.fattura_id === 'e2e-fattura-banca-attesa');
      const residuo = (provPayload.in_attesa_banca || []).find(p => p.fattura_id === 'e2e-fattura-mista');
      assert(attesa && attesa.suggerimento === 'banca', 'Fattura in attesa scomparsa dai Provvisori');
      assert(residuo, 'Residuo misto assente dai Provvisori');
      assertAmount(residuo.importo_residuo, 60, 'Residuo Banca misto');
      assertAmount(cassaPayload.saldo, -130, 'Saldo Cassa delle fixture isolate');
      assertAmount(bancaPayload.saldo, -160, 'Saldo Banca delle fixture isolate');

      const conteggiProvvisoriAttesi = await call(
        'get', '/api/prima-nota/provvisori/conteggi?anno=2026',
      );
      await page.goto(`${BASE}/prima-nota#sezione=banca`, {
        waitUntil: 'networkidle', timeout: 30000,
      });
      await page.getByText(
        `Da decidere (${conteggiProvvisoriAttesi.totale_da_decidere})`,
        { exact: false },
      ).first().waitFor({ timeout: 10000 });
      await page.getByText(
        `Attesa banca (${conteggiProvvisoriAttesi.totale_in_attesa_banca})`,
        { exact: false },
      ).first().waitFor({ timeout: 10000 });

      for (const [sezione, testo] of [
        ['banca', 'E2E-BANCA-PROVA-001'],
        ['provvisori', 'E2E-BANCA-ATTESA-001'],
      ]) {
        await page.goto(`${BASE}/prima-nota#sezione=${sezione}`, {
          waitUntil: 'networkidle', timeout: 30000,
        });
        await page.getByText(testo, { exact: false }).first().waitFor({ timeout: 10000 });
        await capture(`${sezione}-desktop.png`);
        await page.setViewportSize({ width: 390, height: 844 });
        await capture(`${sezione}-mobile.png`);
        await page.setViewportSize({ width: 1280, height: 900 });
      }

      const reset = await context.request.delete(`${BASE}/api/learning-machine/reset-learning`, {
        headers: { Authorization: `Bearer ${tokenPerRuolo('operatore')}` }, maxRedirects: 0,
      });
      assert.equal(reset.status(), 403, 'Reset non-admin non bloccato');
      const regole = (await call('get', '/api/learning-machine/regole-apprese')).regole || [];
      assert(regole.some(r => r.id === 'e2e-regola-protetta'), 'Reset respinto ma dati modificati');
      writeFileSync(resolve(OUT, 'esito.json'), JSON.stringify({
        ambiente: 'e2e-isolato', dati: 'fixture sintetiche, nessun dato aziendale',
        metodo: 'CRUD HTTP reale e rilettura browser desktop/mobile',
        esito: 'superato', saldo_cassa: -130, saldo_banca: -160,
        residuo_misto: 60, screenshots,
      }, null, 2));
      console.log('E2E DISTRUTTIVO OK: scadenze e permessi; Prima Nota Cassa/Banca/Provvisori, prova bancaria, pagamento misto e schermate verificati.');
    } catch (error) {
      await capture('errore.png').catch(() => {});
      throw error;
    }
  } finally {
    await browser.close();
  }
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
