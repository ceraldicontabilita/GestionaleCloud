/**
 * E2E delle viste 1.6 (MINI-08) — gira in CI (job «browser») e in locale con:
 *   yarn build:erp && npx vite preview --port 4173 &
 *   node scripts/audit-viste-fiscali.cjs
 * (Playwright installato; `PLAYWRIGHT_CHROMIUM` per un Chrome gia' presente).
 *
 * Le API sono finte (stesso pattern di audit-layout.cjs e audit-viewer.cjs):
 * nessuna dipendenza dalla rete, nessun dato aziendale. Si prova che le
 * quattro viste esistano come indirizzi stabili, che il browser le apra da un
 * link diretto e che i collegamenti funzionino davvero:
 *
 *   1. TRIBUTO -> QUIETANZA: da `/fiscale/tributi/6003` l'importo versato apre
 *      la quietanza (il PDF viene davvero richiesto a `/api/f24-public/pdf/…`
 *      e appare nel visualizzatore) e «Scheda dell'F24» porta a `/fiscale/f24/:id`
 *      con le righe tributo.
 *   2. FILTRO ANNO GLOBALE: l'anno del selettore in alto arriva alla richiesta
 *      dati, «Tutti gli anni» la toglie e resta nell'indirizzo.
 *   3. BUSTA PAGA: `/personale/cedolini/:id` mostra netto, canale, versioni e
 *      apre il PDF; con il netto assente scrive «Dato non disponibile».
 *   4. PROTOCOLLO E VECCHI INDIRIZZI: `/protocollo/AAAA/NNNNNN` legge l'API
 *      del protocollo personale (MINI-07) e dice che il documento e fuori dai
 *      conti; e `/f24/:id`, `/tributi/:codice`, `/cedolini/:id` rimandano al
 *      canonico.
 *
 * Su telefono (390px) e desktop (1280px): mai overflow orizzontale.
 */
let chromium;
try {
  ({ chromium } = require('playwright-core'));
} catch {
  ({ chromium } = require('/opt/node22/lib/node_modules/playwright/node_modules/playwright-core'));
}

const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:4173';
const EXE = process.env.PLAYWRIGHT_CHROMIUM || undefined;

const VIEWPORTS = [
  { nome: '390x844', opzioni: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  { nome: '1280x800', opzioni: { viewport: { width: 1280, height: 800 } } },
];

const PDF_FINTO = Buffer.from('%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF');
const json = (route, corpo, status = 200) => route.fulfill({
  status, contentType: 'application/json', body: JSON.stringify(corpo),
});

const VOCE_6003 = {
  chiave: 'erario|6003|2026|3', codice: '6003', descrizione: 'IVA mensile marzo', anno: 2026, mese: 3, periodo: '03/2026',
  inviato_cents: 0, quietanza_cents: 120000, ravvedimento_cents: 0, credito_cents: 0, residuo_cents: 0,
  stato: 'PAGATO', stato_label: 'Pagato (quietanza)', ultimo_pagamento: '2026-04-16',
  documenti: [{ tipo: 'quietanza', data: '2026-04-16', protocollo: 'P1', importo_cents: 120000, pdf_url: '/api/f24-public/pdf/Q9' }],
};

const RIGA_F24 = n => ({
  id: `Q9:${n}`, document_id: 'Q9', ordinal: n, payment_year: '2026', payment_date: '2026-04-16', section: 'ERARIO',
  tax_code: '6003', description: 'IVA mensile', reference_period: '03/2026', debit_amount: 1200, credit_amount: 0,
  protocol: '26041535212746370', filename: 'q9.pdf', evidence_state: 'QUIETANZA_DOCUMENTALE_NON_PROVA_BANCARIA', pdf_url: null,
});

const BUSTA = {
  id: 'c1', dipendente: 'ROSSI MARIO', periodo: 'Giugno 2025', tipo: 'mensile', canale: 'drive', netto: 1500,
  netto_fonte: 'cella', lordo: 2000, totale_trattenute: 500, pagato: false, sostituito: false, filename: 'rossi.pdf',
  versione: { variante: 2, stampa_di_controllo: false, rettificato: true, n_versioni_totali: 2, versioni_scartate: [], storico_netto: [], da_decidere: false },
  versioni_gruppo: [
    { id: 'c0', netto: 1400, stampa_di_controllo: true, variante: null, filename: 'bozza.pdf', corrente: false },
    { id: 'c1', netto: 1500, stampa_di_controllo: false, variante: 2, filename: 'rossi.pdf', corrente: true },
  ],
  decisione: { esito: 'vincitore', motivo: 'la busta definitiva batte la stampa di controllo', vincitore: 'c1' },
  pdf_disponibile: true, pdf_url: '/api/cedolini/c1/pdf',
};
const PROTOCOLLO = {
  numero: '2023/000123', data_protocollo: '2023-05-04', data_documento: null, tipo_documento: 'TARI', direzione: 'ENTRATA',
  controparte: 'Comune di Napoli', pratica: null, importo: 210.5, nome_file: 'tari.pdf', canale: 'drive',
  ambito: 'personale_familiare', accounting_excluded: true, stato: 'attivo', oggetto: 'Avviso TARI 2023',
  collegati: { sola_lettura: true, escluso_dalla_contabilita: true, documenti: [] },
};
const BUSTA_SENZA_NETTO = {
  ...BUSTA, id: 'c2', netto: null, lordo: null, totale_trattenute: null, netto_fonte: 'non_letto_da_lul', canale: null,
  pdf_disponibile: false, pdf_url: null, versioni_gruppo: [], decisione: null,
  versione: { variante: null, stampa_di_controllo: false, rettificato: false, n_versioni_totali: null, versioni_scartate: [], storico_netto: [], da_decidere: false },
};

async function nuovaPagina(browser, opzioni, richieste) {
  const ctx = await browser.newContext(opzioni);
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem('auth_token', 'fake');
      localStorage.setItem('annoGlobale', '2026');
    } catch { /* storage non disponibile */ }
  });
  const page = await ctx.newPage();
  const errori = [];
  page.on('pageerror', e => errori.push(`pageerror: ${e.message}`));
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    const percorso = url.pathname;
    richieste.push(`${percorso}${url.search}`);
    if (percorso === '/api/auth/verify') {
      return json(route, { user: { id: 'a', email: 'a@a', name: 'A', role: 'admin', mfa_enabled: true }, mfa_verified: true });
    }
    if (percorso === '/api/f24/tributi') return json(route, { voci: [VOCE_6003] });
    if (percorso === '/api/fiscale/incroci') {
      return json(route, { confronti_iva_mensile: [], irap_riscontro: [], iva_annuale_riscontro: [] });
    }
    if (percorso === '/api/fiscal/f24-rows') return json(route, { items: [RIGA_F24(1), RIGA_F24(2)] });
    if (percorso === '/api/f24/quietanze/Q9') return json(route, { canale: 'posta' });
    if (percorso === '/api/f24-riconciliazione/quietanze-banca') return json(route, { riscontrati: [] });
    if (percorso === '/api/f24-public/pdf/Q9' || percorso === '/api/cedolini/c1/pdf') {
      return route.fulfill({ status: 200, contentType: 'application/pdf', body: PDF_FINTO });
    }
    if (percorso === '/api/protocollo-personale/2023/123') return json(route, PROTOCOLLO);
    if (percorso === '/api/cedolini/c1') return json(route, BUSTA);
    if (percorso === '/api/cedolini/c2') return json(route, BUSTA_SENZA_NETTO);
    return json(route, {});
  });
  return { ctx, page, errori };
}

const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

async function vai(page, percorso) {
  await page.goto(BASE + percorso, { waitUntil: 'domcontentloaded', timeout: 30000 });
}

async function caso(browser, vp, nome, corpo) {
  const richieste = [];
  const { ctx, page, errori } = await nuovaPagina(browser, vp.opzioni, richieste);
  const esiti = [];
  const verifica = (ok, nota) => esiti.push({ ok: Boolean(ok), nota: `[${vp.nome}] ${nome}: ${nota}` });
  try {
    await corpo({ page, richieste, verifica });
    verifica((await overflow(page)) <= 1, 'nessun overflow orizzontale');
    verifica(errori.length === 0, `nessun errore JavaScript${errori.length ? ` (${errori[0]})` : ''}`);
  } catch (e) {
    verifica(false, `eccezione: ${String(e.message).split('\n')[0]}`);
  }
  await ctx.close();
  return esiti;
}

const attendi = (page, testid, timeout = 10000) => page.locator(`[data-testid="${testid}"]`).first().waitFor({ state: 'visible', timeout });

const CASI = [
  ['1 tributo -> quietanza -> scheda F24', async ({ page, richieste, verifica }) => {
    await vai(page, '/fiscale/tributi/6003');
    await attendi(page, 'vista-tributo');
    const importo = page.locator('[data-testid="apri-quietanza-erario|6003|2026|3"]:visible').first();
    await importo.waitFor({ state: 'visible', timeout: 10000 });
    verifica((await importo.innerText()).includes('1.200,00'), 'l\'importo versato e in euro con cifre italiane');
    await importo.click();
    await attendi(page, 'document-viewer-overlay');
    verifica(true, 'il visualizzatore della quietanza si apre');
    await page.waitForTimeout(800);
    verifica(richieste.some(r => r.startsWith('/api/f24-public/pdf/Q9')), 'il PDF della quietanza e stato richiesto davvero');
    await page.keyboard.press('Escape');
    await page.locator('[data-testid="scheda-f24-erario|6003|2026|3"]:visible').first().click();
    await attendi(page, 'vista-f24');
    verifica(new URL(page.url()).pathname === '/fiscale/f24/Q9', 'la scheda F24 ha l\'indirizzo stabile');
    await attendi(page, 'f24-righe');
    verifica((await page.locator('[data-testid="vista-f24"]').innerText()).includes('6003'), 'la scheda mostra le righe tributo');
    await page.waitForFunction(() => document.querySelector('[data-testid="f24-canale"]')?.textContent.includes('Posta'), null, { timeout: 8000 });
    verifica(true, 'il canale d\'arrivo e in pagina');
    const legenda = page.locator('[data-testid="legenda-f24"]');
    verifica(await legenda.count() === 1, 'la legenda delle regole e in pagina');
  }],

  ['2 filtro anno globale', async ({ page, richieste, verifica }) => {
    await vai(page, '/fiscale/tributi/6003');
    await attendi(page, 'filtro-anno-vista');
    await page.waitForTimeout(600);
    verifica(richieste.some(r => r.startsWith('/api/f24/tributi') && r.includes('anno=2026')), 'l\'anno globale 2026 arriva alla richiesta');
    const prima = richieste.length;
    await page.getByRole('button', { name: 'Tutti gli anni' }).click();
    await page.waitForFunction(() => location.search.includes('anno=tutti'), null, { timeout: 5000 });
    await page.waitForTimeout(600);
    const dopo = richieste.slice(prima).filter(r => r.startsWith('/api/f24/tributi'));
    verifica(dopo.length > 0 && dopo.every(r => !r.includes('anno=')), '«Tutti gli anni» toglie il limite dalla richiesta');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await attendi(page, 'filtro-anno-vista');
    const premuto = await page.getByRole('button', { name: 'Tutti gli anni' }).getAttribute('aria-pressed');
    verifica(premuto === 'true', 'la scelta resta nell\'indirizzo dopo il ricaricamento');
  }],

  ['3 busta paga', async ({ page, richieste, verifica }) => {
    await vai(page, '/personale/cedolini/c1');
    await attendi(page, 'cedolino-scheda');
    const testo = await page.locator('[data-testid="vista-cedolino"]').innerText();
    verifica(testo.includes('1.500,00') && testo.includes('Drive') && testo.includes('Variante 2'), 'netto in euro, canale e variante');
    verifica((await page.locator('[data-testid="cedolino-versione"]').count()) === 2, 'le due versioni della busta sono affiancate');
    await page.locator('[data-testid="cedolino-apri-originale"]:visible').first().click();
    await attendi(page, 'document-viewer-overlay');
    await page.waitForTimeout(800);
    verifica(richieste.some(r => r.startsWith('/api/cedolini/c1/pdf')), 'il PDF della busta e stato richiesto davvero');
    await page.keyboard.press('Escape');
    await vai(page, '/personale/cedolini/c2');
    await attendi(page, 'cedolino-scheda');
    const senza = await page.locator('[data-testid="cedolino-scheda"]').innerText();
    verifica(senza.includes('Dato non disponibile') && !/0,00/.test(senza), 'netto assente: «Dato non disponibile», mai zero');
  }],

  ['4 protocollo e vecchi indirizzi', async ({ page, richieste, verifica }) => {
    await vai(page, '/protocollo/2023/000123');
    await attendi(page, 'protocollo-scheda');
    const scheda = await page.locator('[data-testid="vista-protocollo"]').innerText();
    verifica(scheda.includes('2023/000123') && scheda.includes('04/05/2023') && scheda.includes('210,50'), 'la scheda del protocollo ha numero, data gg/mm/aaaa e importo in euro');
    verifica(scheda.includes('Dato non disponibile'), 'un campo assente e «Dato non disponibile»');
    verifica(richieste.some(r => r === '/api/protocollo-personale/2023/123'), 'la scheda legge l\'API del protocollo personale');
    verifica(scheda.includes('fuori dai conti'), 'la pagina dice che il documento personale e fuori dai conti');
    await vai(page, '/protocollo/COLLAUDO');
    await attendi(page, 'protocollo-non-trovato');
    verifica(true, 'un numero senza la forma AAAA/NNNNNN e «non trovato», non una pagina vuota');
    await vai(page, '/f24/Q9');
    await page.waitForFunction(() => location.pathname === '/fiscale/f24/Q9', null, { timeout: 8000 });
    verifica(true, '/f24/:id rimanda a /fiscale/f24/:id');
    await vai(page, '/tributi/6003?anno=tutti');
    await page.waitForFunction(() => location.pathname === '/fiscale/tributi/6003' && location.search === '?anno=tutti', null, { timeout: 8000 });
    verifica(true, '/tributi/:codice rimanda al canonico tenendo il filtro');
    await vai(page, '/cedolini/c1');
    await page.waitForFunction(() => location.pathname === '/personale/cedolini/c1', null, { timeout: 8000 });
    verifica(true, '/cedolini/:id rimanda a /personale/cedolini/:id');
  }],
];

(async () => {
  const browser = await chromium.launch(EXE ? { executablePath: EXE, args: ['--no-sandbox'] } : { args: ['--no-sandbox'] });
  let errori = 0;
  for (const vp of VIEWPORTS) {
    for (const [nome, corpo] of CASI) {
      for (const e of await caso(browser, vp, nome, corpo)) {
        if (e.ok) console.log(`OK   ${e.nota}`);
        else { errori += 1; console.error(`FAIL ${e.nota}`); }
      }
    }
  }
  await browser.close();
  if (errori) {
    console.error(`\nE2E VISTE FISCALI FALLITO: ${errori} controllo/i falliti.`);
    process.exit(1);
  }
  console.log('\nE2E VISTE FISCALI OK.');
})();
