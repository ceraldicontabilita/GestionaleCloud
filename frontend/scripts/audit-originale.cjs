/**
 * E2E dell'apertura dell'originale (DRV-04) — gira in CI (job «browser») e in locale con:
 *   yarn build:erp && npx vite preview --port 4173 &
 *   node scripts/audit-originale.cjs
 * (Playwright installato; `PLAYWRIGHT_CHROMIUM` per un Chrome gia' presente).
 *
 * Le API sono finte (stesso pattern di audit-viste-fiscali.cjs): nessuna
 * dipendenza dalla rete, nessun dato aziendale. Si prova che da ogni pagina
 * il documento si apra DAVVERO dall'endpoint unico `/api/originale`:
 *
 *   1. F24 (modello) e 2. QUIETANZA: da `/fiscale/f24/:id`.
 *   3. FATTURA: da `/fatture`, «Vedi» e poi «Scarica» l'XML originale.
 *   4. CEDOLINO: da `/personale/cedolini/:id`.
 *   5. VERBALE: da `/verbali-noleggio/:numero`, secondo PDF (`?indice=1`).
 *   6. RICEVUTA PAGOPA: da `/riconciliazione/pagopa`.
 *   7. PROTOCOLLO: da `/protocollo/AAAA/NNNNNN`, con SHA-256 noto; senza
 *      SHA-256 il bottone non c'e' e la pagina dice «Originale non disponibile».
 *   8. ORIGINALE MANCANTE: il server risponde 404 col suo `code` e il
 *      visualizzatore lo dice con le parole del server e il riferimento,
 *      mai una pagina vuota.
 *
 * Nessuna pagina deve piu' chiamare gli indirizzi vecchi (`/api/f24-public/pdf`,
 * `/api/cedolini/:id/pdf`, `/api/download`...). Su telefono (390px) e desktop
 * (1280px): mai overflow orizzontale.
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
const XML_FINTO = Buffer.from('<?xml version="1.0"?><FatturaElettronica/>');
const json = (route, corpo, status = 200) => route.fulfill({
  status, contentType: 'application/json', body: JSON.stringify(corpo),
});
const pdf = route => route.fulfill({ status: 200, contentType: 'application/pdf', body: PDF_FINTO });

const VECCHI_INDIRIZZI = [
  /^\/api\/f24-public\/pdf\//, /^\/api\/cedolini\/[^/]+\/pdf/, /^\/api\/download/,
  /^\/api\/pagopa\/ricevute\/[^/]+\/pdf/, /^\/api\/verbali-noleggio\/pdf\//, /^\/api\/documenti\/documento\/.*\/download/,
  /^\/api\/fatture-ricevute\/fattura\/[^/]+\/(xml-originale|pdf\/)/, /^\/api\/fiscal\/documents\/.*\/content/,
];

const RIGA_F24 = n => ({
  id: `Q9:${n}`, document_id: 'Q9', ordinal: n, payment_year: '2026', payment_date: '2026-04-16', section: 'ERARIO',
  tax_code: '6003', description: 'IVA mensile', reference_period: '03/2026', debit_amount: 1200, credit_amount: 0,
  protocol: '26041535212746370', filename: 'q9.pdf', evidence_state: 'QUIETANZA_DOCUMENTALE_NON_PROVA_BANCARIA',
  pdf_url: '/api/originale/quietanza/Q9',
});
const BUSTA = {
  id: 'c1', dipendente: 'ROSSI MARIO', periodo: 'Giugno 2025', tipo: 'mensile', canale: 'drive', netto: 1500,
  netto_fonte: 'cella', lordo: 2000, totale_trattenute: 500, pagato: false, sostituito: false, filename: 'rossi.pdf',
  versione: { variante: null, stampa_di_controllo: false, rettificato: false, n_versioni_totali: null, versioni_scartate: [], storico_netto: [], da_decidere: false },
  versioni_gruppo: [], decisione: null, pdf_disponibile: true, pdf_url: '/api/originale/cedolino/c1',
};
const PROTOCOLLO = (extra = {}) => ({
  numero: '2023/000123', data_protocollo: '2023-05-04', data_documento: null, tipo_documento: 'TARI', direzione: 'ENTRATA',
  controparte: 'Comune di Napoli', pratica: null, importo: 210.5, nome_file: 'tari.pdf', canale: 'drive',
  ambito: 'personale_familiare', accounting_excluded: true, stato: 'attivo', oggetto: 'Avviso TARI 2023',
  sha256: 'a'.repeat(64), drive_file_id: 'DRIVE-PP1',
  collegati: { sola_lettura: true, escluso_dalla_contabilita: true, documenti: [] }, ...extra,
});
const FATTURA = {
  id: 'F1', invoice_number: '12', supplier_name: 'FORNITORE TEST SRL', supplier_vat: '01234567890', total_amount: 122,
  invoice_date: '2026-03-01', status: 'imported', stato_pagamento: 'non_pagata', metodo_pagamento: 'bonifico',
};
const RICEVUTA = {
  id: 'R1', iuv: '01234567890123456', importo: 50.1, data_pagamento: '2026-04-02', beneficiario: 'Comune di Napoli',
  stato: 'da_associare', filename: 'ricevuta.pdf',
};

async function nuovaPagina(browser, opzioni, richieste, mancanti = false) {
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
    const percorso = decodeURIComponent(url.pathname);
    richieste.push(`${percorso}${url.search}`);
    if (percorso === '/api/auth/verify') {
      return json(route, { user: { id: 'a', email: 'a@a', name: 'A', role: 'admin', mfa_enabled: true }, mfa_verified: true });
    }
    // l'endpoint unico degli originali
    if (percorso.startsWith('/api/originale')) {
      if (mancanti) {
        return json(route, {
          code: 'ORIGINALE_NON_DISPONIBILE', message: 'Originale non disponibile', details: { provato: ['pdf_data'] },
          correlation_id: 'rif123456789', detail: 'Originale non disponibile',
        }, 404);
      }
      return percorso.startsWith('/api/originale/fattura/')
        ? route.fulfill({ status: 200, contentType: 'application/xml', body: XML_FINTO })
        : pdf(route);
    }
    if (percorso === '/api/fiscal/f24-rows') return json(route, { items: [RIGA_F24(1), RIGA_F24(2)] });
    if (percorso === '/api/f24/quietanze/Q9' || percorso === '/api/f24/quietanze/M1') return json(route, { canale: 'posta' });
    if (percorso === '/api/f24-riconciliazione/quietanze-banca') return json(route, { riscontrati: [] });
    if (percorso === '/api/cedolini/c1') return json(route, BUSTA);
    if (percorso === '/api/protocollo-personale/2023/123') return json(route, PROTOCOLLO());
    if (percorso === '/api/protocollo-personale/2023/124') return json(route, PROTOCOLLO({ numero: '2023/000124', sha256: null }));
    if (percorso === '/api/fatture-ricevute/archivio') return json(route, { fatture: [FATTURA] });
    if (percorso === '/api/fatture-ricevute/fattura/F1/allegati') {
      return json(route, { allegati: [{ indice: 0, nome: 'cortesia.pdf', formato: 'PDF', descrizione: 'PDF del fornitore' }] });
    }
    if (percorso === '/api/fatture-ricevute/fattura/F1/documenti-pagamento') return json(route, { documenti: [] });
    if (percorso === '/api/fatture-ricevute/fattura/F1/view-assoinvoice') {
      return route.fulfill({ status: 200, contentType: 'text/html', body: '<html><body>Fattura 12</body></html>' });
    }
    if (percorso.startsWith('/api/verbali-noleggio/dettaglio/')) {
      return json(route, {
        numero_verbale: 'V-1', targa: 'AB123CD', importo: 51.64,
        pdf_disponibili: [{ indice: 0, filename: 'verbale.pdf' }, { indice: 1, filename: 'quietanza.pdf', tipo: 'quietanza' }],
      });
    }
    if (percorso === '/api/pagopa/ricevute') return json(route, [RICEVUTA]);
    if (percorso === '/api/pagopa/nature') return json(route, { nature: [] });
    if (percorso === '/api/pagopa/stats') return json(route, { totale_ricevute: 1, associate: 0, da_associare: 1 });
    return json(route, {});
  });
  return { ctx, page, errori };
}

const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const attendi = (page, testid, timeout = 10000) => page.locator(`[data-testid="${testid}"]`).first().waitFor({ state: 'visible', timeout });
async function vai(page, percorso) {
  await page.goto(BASE + percorso, { waitUntil: 'domcontentloaded', timeout: 30000 });
}

async function caso(browser, vp, nome, corpo, mancanti = false) {
  const richieste = [];
  const { ctx, page, errori } = await nuovaPagina(browser, vp.opzioni, richieste, mancanti);
  const esiti = [];
  const verifica = (ok, nota) => esiti.push({ ok: Boolean(ok), nota: `[${vp.nome}] ${nome}: ${nota}` });
  try {
    await corpo({ page, richieste, verifica });
    const vecchie = richieste.filter(r => VECCHI_INDIRIZZI.some(re => re.test(r.split('?')[0])));
    verifica(vecchie.length === 0, `nessun indirizzo di apertura vecchio chiamato${vecchie.length ? ` (${vecchie[0]})` : ''}`);
    verifica((await overflow(page)) <= 1, 'nessun overflow orizzontale');
    verifica(errori.length === 0, `nessun errore JavaScript${errori.length ? ` (${errori[0]})` : ''}`);
  } catch (e) {
    verifica(false, `eccezione: ${String(e.message).split('\n')[0]}`);
  }
  await ctx.close();
  return esiti;
}

const chiediOriginale = (richieste, prefisso) => richieste.some(r => r.startsWith(prefisso));

const CASI = [
  ['1-2 F24 e quietanza da /fiscale/f24/:id', async ({ page, richieste, verifica }) => {
    await vai(page, '/fiscale/f24/Q9');
    await attendi(page, 'vista-f24');
    await page.locator('[data-testid="f24-apri-originale"]:visible').first().click();
    await attendi(page, 'document-viewer-overlay');
    await page.waitForTimeout(800);
    verifica(chiediOriginale(richieste, '/api/originale/quietanza/Q9'), 'la quietanza si apre da /api/originale/quietanza/Q9');
    verifica(await page.locator('[data-testid="document-viewer-download"]').count() === 1, 'il visualizzatore ha «Scarica»');
    await page.keyboard.press('Escape');
  }],

  ['3 fattura da /fatture', async ({ page, richieste, verifica }) => {
    await vai(page, '/fatture');
    const vedi = page.getByRole('button', { name: 'Vedi' }).locator('visible=true').first();
    await vedi.waitFor({ state: 'visible', timeout: 15000 });
    await vedi.click();
    await attendi(page, 'modal-fattura-overlay');
    await page.waitForTimeout(500);
    await page.locator('[data-testid="modal-fattura-download"]').first().click();
    await page.waitForTimeout(800);
    verifica(chiediOriginale(richieste, '/api/originale/fattura/F1'), 'l\'XML originale si scarica da /api/originale/fattura/F1');
    await page.locator('[data-testid="modal-fattura-allegato-0"]').first().click();
    await page.waitForTimeout(800);
    verifica(chiediOriginale(richieste, '/api/originale/allegato_fattura/F1'), 'l\'allegato PDF si apre da /api/originale/allegato_fattura/F1');
  }],

  ['4 busta paga da /personale/cedolini/:id', async ({ page, richieste, verifica }) => {
    await vai(page, '/personale/cedolini/c1');
    await attendi(page, 'cedolino-scheda');
    await page.locator('[data-testid="cedolino-apri-originale"]:visible').first().click();
    await attendi(page, 'document-viewer-overlay');
    await page.waitForTimeout(800);
    verifica(chiediOriginale(richieste, '/api/originale/cedolino/c1'), 'il PDF della busta si apre da /api/originale/cedolino/c1');
  }],

  ['5 verbale da /verbali-noleggio/:numero', async ({ page, richieste, verifica }) => {
    await vai(page, '/verbali-noleggio/V-1');
    await attendi(page, 'open-verbale-pdf-0');
    await page.locator('[data-testid="open-verbale-pdf-0"]').first().click();
    await attendi(page, 'document-viewer-overlay');
    await page.waitForTimeout(800);
    verifica(chiediOriginale(richieste, '/api/originale/verbale/V-1'), 'il PDF si apre da /api/originale/verbale/V-1');
  }],

  ['6 ricevuta PagoPA da /riconciliazione/pagopa', async ({ page, richieste, verifica }) => {
    await vai(page, '/riconciliazione/pagopa');
    const vedi = page.locator('[data-testid="view-ricevuta-0"]:visible').first();
    await vedi.waitFor({ state: 'visible', timeout: 15000 });
    await vedi.click();
    await attendi(page, 'document-viewer-overlay');
    await page.waitForTimeout(800);
    verifica(chiediOriginale(richieste, '/api/originale/ricevuta_pagopa/R1'), 'la ricevuta si apre da /api/originale/ricevuta_pagopa/R1');
  }],

  ['7 protocollo da /protocollo/AAAA/NNNNNN', async ({ page, richieste, verifica }) => {
    await vai(page, '/protocollo/2023/000123');
    await attendi(page, 'protocollo-scheda');
    await page.locator('[data-testid="protocollo-apri-originale"]:visible').first().click();
    await attendi(page, 'document-viewer-overlay');
    await page.waitForTimeout(800);
    verifica(chiediOriginale(richieste, '/api/originale/protocollo/2023/000123'), 'il file si apre da /api/originale/protocollo/2023/000123');
    await page.keyboard.press('Escape');
    await vai(page, '/protocollo/2023/000124');
    await attendi(page, 'protocollo-scheda');
    verifica(await page.locator('[data-testid="protocollo-apri-originale"]').count() === 0, 'senza SHA-256 registrato non c\'e\' un bottone che non puo\' aprire');
    verifica((await page.locator('[data-testid="protocollo-apri-originale-assente"]').innerText()).includes('Originale non disponibile'), 'la pagina dice «Originale non disponibile»');
  }],
];

const CASO_MANCANTE = ['8 originale mancante: errore leggibile', async ({ page, richieste, verifica }) => {
  await vai(page, '/personale/cedolini/c1');
  await attendi(page, 'cedolino-scheda');
  await page.locator('[data-testid="cedolino-apri-originale"]:visible').first().click();
  await attendi(page, 'document-viewer-overlay');
  const messaggio = page.getByText(/Originale non disponibile \(rif\. rif123456789\)/);
  await messaggio.first().waitFor({ state: 'visible', timeout: 8000 });
  verifica(true, 'il visualizzatore dice «Originale non disponibile» col riferimento del server');
  verifica(chiediOriginale(richieste, '/api/originale/cedolino/c1'), 'la richiesta e andata all\'endpoint unico');
}];

(async () => {
  const browser = await chromium.launch(EXE ? { executablePath: EXE, args: ['--no-sandbox'] } : { args: ['--no-sandbox'] });
  let errori = 0;
  for (const vp of VIEWPORTS) {
    const prove = [...CASI.map(c => [...c, false]), [...CASO_MANCANTE, true]];
    for (const [nome, corpo, mancanti] of prove) {
      for (const e of await caso(browser, vp, nome, corpo, mancanti)) {
        if (e.ok) console.log(`OK   ${e.nota}`);
        else { errori += 1; console.error(`FAIL ${e.nota}`); }
      }
    }
  }
  await browser.close();
  if (errori) {
    console.error(`\nE2E ORIGINALE FALLITO: ${errori} controllo/i falliti.`);
    process.exit(1);
  }
  console.log('\nE2E ORIGINALE OK.');
})();
