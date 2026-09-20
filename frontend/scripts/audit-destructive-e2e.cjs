/**
 * Collaudo distruttivo in browser contro scripts/e2e_distruttivo_server.py.
 * Il server usa router reali + Drive/Sheets in memoria: nessuna richiesta puo'
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


  // ── FASE 0A: Prima Nota operativa ──────────────────────────────────────
  // CRUD Cassa reale attraverso gli endpoint montati.
  const headers = { Authorization: `Bearer ${adminToken}` };
  const creaCassa = await context.request.post(`${BASE}/api/prima-nota/cassa`, {
    headers,
    data: {
      data: '2026-09-21',
      tipo: 'entrata',
      importo: 100,
      descrizione: 'COLLAUDO E2E CASSA CRUD',
      categoria: 'Altro',
    },
  });
  if (!creaCassa.ok()) throw new Error(`Creazione Cassa fallita: HTTP ${creaCassa.status()}`);
  const cassaId = (await creaCassa.json()).id;
  if (!cassaId) throw new Error('Creazione Cassa senza id');

  const modificaCassa = await context.request.put(`${BASE}/api/prima-nota/cassa/${cassaId}`, {
    headers,
    data: { importo: 125, descrizione: 'COLLAUDO E2E CASSA CRUD MODIFICATO' },
  });
  if (!modificaCassa.ok()) throw new Error(`Modifica Cassa fallita: HTTP ${modificaCassa.status()}`);

  let cassa = await context.request.get(`${BASE}/api/prima-nota/cassa?anno=2026&limit=200`, { headers });
  if (!cassa.ok()) throw new Error(`Lettura Cassa fallita: HTTP ${cassa.status()}`);
  let cassaPayload = await cassa.json();
  const cassaCrud = (cassaPayload.movimenti || []).find(m => m.id === cassaId);
  if (!cassaCrud || Number(cassaCrud.importo) !== 125
      || cassaCrud.descrizione !== 'COLLAUDO E2E CASSA CRUD MODIFICATO') {
    throw new Error('CRUD Cassa non persistito correttamente');
  }

  // Verifica UI + reload: il dato deve sopravvivere alla navigazione, non solo
  // alla risposta del POST.
  await page.goto(`${BASE}/prima-nota`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.getByText('COLLAUDO E2E CASSA CRUD MODIFICATO', { exact: false }).first()
    .waitFor({ timeout: 10000 });
  await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
  await page.getByText('COLLAUDO E2E CASSA CRUD MODIFICATO', { exact: false }).first()
    .waitFor({ timeout: 10000 });

  const eliminaCassa = await context.request.delete(
    `${BASE}/api/prima-nota/cassa/${cassaId}?force=true`,
    { headers },
  );
  if (!eliminaCassa.ok()) throw new Error(`Eliminazione Cassa fallita: HTTP ${eliminaCassa.status()}`);
  cassa = await context.request.get(`${BASE}/api/prima-nota/cassa?anno=2026&limit=200`, { headers });
  cassaPayload = await cassa.json();
  if ((cassaPayload.movimenti || []).some(m => m.id === cassaId)) {
    throw new Error('Movimento Cassa archiviato ancora visibile nell’elenco operativo');
  }

  // Provvisori -> Cassa: una conferma esplicita genera la scrittura reale.
  const confermaCassa = await context.request.post(
    `${BASE}/api/prima-nota/provvisori/conferma`,
    { headers, data: { fattura_id: 'e2e-fattura-cassa', metodo: 'cassa' } },
  );
  if (!confermaCassa.ok()) {
    throw new Error(`Provvisorio -> Cassa fallito: HTTP ${confermaCassa.status()} ${await confermaCassa.text()}`);
  }
  cassa = await context.request.get(`${BASE}/api/prima-nota/cassa?anno=2026&limit=200`, { headers });
  cassaPayload = await cassa.json();
  const pagamentoCassa = (cassaPayload.movimenti || []).find(m => m.fattura_id === 'e2e-fattura-cassa');
  if (!pagamentoCassa || Number(pagamentoCassa.importo) !== 90) {
    throw new Error('Conferma Cassa non ha creato la scrittura da 90 EUR');
  }

  // Banca: una fattura NON può essere dichiarata pagata senza prova EC.
  const bancaSenzaProva = await context.request.post(
    `${BASE}/api/prima-nota/provvisori/conferma`,
    { headers, data: { fattura_id: 'e2e-fattura-banca-attesa', metodo: 'banca' } },
  );
  if (bancaSenzaProva.status() !== 409) {
    throw new Error(`Pagamento Banca senza prova non bloccato: HTTP ${bancaSenzaProva.status()}`);
  }

  const attendiBanca = await context.request.post(
    `${BASE}/api/prima-nota/provvisori/attendi-banca`,
    { headers, data: { fattura_id: 'e2e-fattura-banca-attesa' } },
  );
  if (!attendiBanca.ok()) {
    throw new Error(`Attendi banca fallito: HTTP ${attendiBanca.status()} ${await attendiBanca.text()}`);
  }

  let banca = await context.request.get(`${BASE}/api/prima-nota/banca?anno=2026&limit=200`, { headers });
  if (!banca.ok()) throw new Error(`Lettura Banca fallita: HTTP ${banca.status()}`);
  let bancaPayload = await banca.json();
  if ((bancaPayload.movimenti || []).some(m => m.fattura_id === 'e2e-fattura-banca-attesa')) {
    throw new Error('Attendi banca ha creato una falsa scrittura bancaria');
  }

  // Banca con prova: la stessa conferma è ammessa quando esiste il movimento EC.
  const bancaConProva = await context.request.post(
    `${BASE}/api/prima-nota/provvisori/conferma`,
    {
      headers,
      data: {
        fattura_id: 'e2e-fattura-banca-prova',
        metodo: 'banca',
        movimento_banca_id: 'e2e-ec-banca-prova',
      },
    },
  );
  if (!bancaConProva.ok()) {
    throw new Error(`Banca con prova EC fallita: HTTP ${bancaConProva.status()} ${await bancaConProva.text()}`);
  }
  banca = await context.request.get(`${BASE}/api/prima-nota/banca?anno=2026&limit=200`, { headers });
  bancaPayload = await banca.json();
  const pagamentoBanca = (bancaPayload.movimenti || []).find(m => m.fattura_id === 'e2e-fattura-banca-prova');
  if (!pagamentoBanca || Number(pagamentoBanca.importo) !== 160 || pagamentoBanca.riconciliato !== true) {
    throw new Error('Pagamento Banca con prova EC non risulta reale e riconciliato');
  }

  // Misto: solo la quota Cassa diventa denaro reale; il residuo Banca resta aperto.
  const divisione = await context.request.post(
    `${BASE}/api/prima-nota/provvisori/conferma-divisione`,
    {
      headers,
      data: {
        fattura_id: 'e2e-fattura-mista',
        importo_cassa: 40,
        importo_banca: 60,
        performed_by: 'e2e',
      },
    },
  );
  if (!divisione.ok()) {
    throw new Error(`Divisione mista fallita: HTTP ${divisione.status()} ${await divisione.text()}`);
  }
  cassa = await context.request.get(`${BASE}/api/prima-nota/cassa?anno=2026&limit=200`, { headers });
  cassaPayload = await cassa.json();
  const quotaCassa = (cassaPayload.movimenti || []).find(m => m.fattura_id === 'e2e-fattura-mista');
  if (!quotaCassa || Number(quotaCassa.importo) !== 40) {
    throw new Error('Quota Cassa del pagamento misto non registrata');
  }
  banca = await context.request.get(`${BASE}/api/prima-nota/banca?anno=2026&limit=200`, { headers });
  bancaPayload = await banca.json();
  if ((bancaPayload.movimenti || []).some(m => m.fattura_id === 'e2e-fattura-mista')) {
    throw new Error('Pagamento misto ha inventato una quota Banca senza estratto conto');
  }

  const provvisori = await context.request.get(
    `${BASE}/api/prima-nota/provvisori?anno=2026`,
    { headers },
  );
  if (!provvisori.ok()) throw new Error(`Lettura Provvisori fallita: HTTP ${provvisori.status()}`);
  const provPayload = await provvisori.json();
  const attesa = (provPayload.provvisori || []).find(p => p.fattura_id === 'e2e-fattura-banca-attesa');
  const residuoMisto = (provPayload.provvisori || []).find(p => p.fattura_id === 'e2e-fattura-mista');
  if (!attesa || attesa.suggerimento !== 'banca') {
    throw new Error('Fattura in attesa banca non è rimasta nei Provvisori');
  }
  if (!residuoMisto || Math.abs(Number(residuoMisto.importo_residuo) - 60) > 0.01) {
    throw new Error('Residuo Banca del pagamento misto non è rimasto aperto a 60 EUR');
  }

  // Quadratura finale isolata: CRUD manuale è stato eliminato, quindi Cassa
  // contiene solo 90 EUR della fattura Cassa + 40 EUR della quota mista.
  if (Math.abs(Number(cassaPayload.saldo) - 130) > 0.01) {
    throw new Error(`Saldo Cassa E2E inatteso: ${cassaPayload.saldo}, atteso 130`);
  }
  if (Math.abs(Number(bancaPayload.saldo) - (-160)) > 0.01) {
    throw new Error(`Saldo Banca E2E inatteso: ${bancaPayload.saldo}, atteso -160`);
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
  console.log('E2E DISTRUTTIVO OK: scadenze e permessi verificati; Prima Nota Cassa/Banca/Provvisori CRUD, prova bancaria e pagamento misto verificati.');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
