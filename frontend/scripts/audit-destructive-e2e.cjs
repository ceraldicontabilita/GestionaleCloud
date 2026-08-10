/**
 * Collaudo distruttivo in browser contro scripts/e2e_distruttivo_server.py.
 * Il server usa router reali + MongoDB in memoria: nessuna richiesta puo'
 * raggiungere Atlas o la produzione.
 */
const { createHmac } = require('crypto');
const { chromium } = require('playwright-core');

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:8788';
const EXE = process.env.PLAYWRIGHT_CHROMIUM
  || (process.platform === 'win32'
    ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    : undefined);
const TEST_SECRET = 'e2e-isolato-solo-test-non-produzione';

function base64url(value) {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function tokenPerRuolo(role) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url({ alg: 'HS256', typ: 'JWT' });
  const payload = base64url({
    sub: `${role}@example.invalid`,
    email: `${role}@example.invalid`,
    name: `E2E ${role}`,
    role,
    iat: now,
    exp: now + 900,
  });
  const signature = createHmac('sha256', TEST_SECRET)
    .update(`${header}.${payload}`)
    .digest('base64url');
  return `${header}.${payload}.${signature}`;
}

async function getScadenze(request, token) {
  const response = await request.get(
    `${BASE}/api/scadenze/tutte?anno=2026&tipo=CUSTOM&include_passate=true&limit=50`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok()) throw new Error(`GET scadenze fallita: HTTP ${response.status()}`);
  return (await response.json()).scadenze || [];
}

(async () => {
  const browser = await chromium.launch(EXE ? { executablePath: EXE } : {});
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });

  const login = await context.request.post(`${BASE}/api/auth/login`, {
    data: { email: 'e2e@example.invalid', password: 'e2e-password-solo-test' },
  });
  if (!login.ok()) throw new Error(`Login E2E fallito: HTTP ${login.status()}`);
  const adminToken = (await login.json()).access_token;

  await context.addInitScript(({ token }) => {
    localStorage.setItem('auth_token', token);
    localStorage.setItem('ceraldi_anno_globale', '2026');
  }, { token: adminToken });

  const page = await context.newPage();
  // Il collaudo non riguarda le notifiche realtime. Intercettare qui il WS
  // evita che il token di test compaia nell'access log del server.
  await page.routeWebSocket('**', socket => socket.close());
  await page.goto(`${BASE}/scadenze`, { waitUntil: 'networkidle', timeout: 30000 });
  // La pagina limita la risposta a 50 elementi. Con tutte le fatture e le
  // scadenze fiscali il record isolato puo' essere correttamente salvato ma
  // restare fuori dalla prima pagina: il filtro CUSTOM rende deterministico
  // il collaudo senza modificare il contratto di produzione.
  await page
    .locator('select')
    .filter({ has: page.locator('option[value="CUSTOM"]') })
    .selectOption('CUSTOM');
  // Limita la ricerca alla tabella Scadenze: il precedente selettore generico
  // poteva scegliere il div interno della descrizione, che non contiene il
  // pulsante. La riga e il relativo comando restano così legati allo stesso
  // record di prova senza dipendere dalla struttura di contenitori della pagina.
  const riga = page
    .getByTestId('scadenze-table')
    .locator('tbody tr')
    .filter({ hasText: 'COLLAUDO E2E - cancellami' })
    .first();
  await riga.getByTitle('Elimina').click();
  await page.getByTestId('confirm-dialog-cancel').click();

  let scadenze = await getScadenze(context.request, adminToken);
  if (!scadenze.some(s => s.id === 'e2e-scadenza-da-eliminare')) {
    throw new Error('Annulla ha cancellato il record: regressione del dialog di conferma');
  }

  await riga.getByTitle('Elimina').click();
  const eliminazione = page.waitForResponse(
    r => r.request().method() === 'DELETE'
      && r.url().endsWith('/api/scadenze/e2e-scadenza-da-eliminare'),
  );
  await page.getByTestId('confirm-dialog-confirm').click();
  const rispostaEliminazione = await eliminazione;
  if (rispostaEliminazione.status() !== 200) {
    throw new Error(`Eliminazione scadenza fallita: HTTP ${rispostaEliminazione.status()}`);
  }
  await page.getByText('COLLAUDO E2E - cancellami').waitFor({ state: 'detached' });

  scadenze = await getScadenze(context.request, adminToken);
  if (scadenze.some(s => s.id === 'e2e-scadenza-da-eliminare')) {
    throw new Error('Il record risulta ancora nel database dopo la conferma');
  }

  const operatoreToken = tokenPerRuolo('operatore');
  const tentativoNonAdmin = await context.request.delete(
    `${BASE}/api/learning-machine/reset-learning`,
    { headers: { Authorization: `Bearer ${operatoreToken}` } },
  );
  if (tentativoNonAdmin.status() !== 403) {
    throw new Error(`Reset non-admin non bloccato: HTTP ${tentativoNonAdmin.status()}`);
  }

  const regoleDopoTentativo = await context.request.get(
    `${BASE}/api/learning-machine/regole-apprese`,
    { headers: { Authorization: `Bearer ${adminToken}` } },
  );
  const regole = (await regoleDopoTentativo.json()).regole || [];
  if (!regole.some(r => r.id === 'e2e-regola-protetta')) {
    throw new Error('Il reset non-admin e stato bloccato con 403 ma ha modificato i dati');
  }

  await browser.close();
  console.log('E2E DISTRUTTIVO OK: annullamento preserva il record; conferma lo elimina; reset non-admin bloccato con 403 e dati invariati.');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
