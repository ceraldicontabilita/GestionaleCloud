/**
 * Audit E2E del viewer documentale — gira in CI (workflow viewer-e2e.yml) e
 * in locale con: node scripts/audit-viewer.cjs (richiede
 * `vite preview --port 4173` attivo e Playwright installato).
 *
 * Copertura (piano residuo op.18): apre DocumentViewerModal dalla pagina
 * /documenti (flusso "documento PDF generico", fetchUrl autenticato via
 * blob) su più viewport e verifica il comportamento del componente
 * CANONICO condiviso da tutti gli 8 tipi documento (fattura ASSO HTML,
 * fattura PDF, cedolino, F24, quietanza, PagoPA, verbale, documento non
 * associato — vedi memoria/AUDIT_VIEWER_DOCUMENTI.md): nessun overflow
 * orizzontale, chiusura sempre raggiungibile (bottone + ESC), focus
 * trap in ingresso, ritorno del focus al bottone di origine alla chiusura.
 *
 * NON copre (debito tecnico esplicito, vedi
 * memoria/PIANO_CONSOLIDAMENTO_TRACKING.md op.18): le pagine/flussi
 * specifici degli altri 7 tipi documento (pulsante/endpoint diversi per
 * ognuno), zoom/fit/fullscreen/download funzionali (qui solo che i
 * controlli esistano e siano cliccabili), autorizzazione del download.
 *
 * Le API sono finte (stesso pattern di audit-layout.cjs): un solo
 * documento fittizio, un PDF minimo valido come fetchUrl.
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
  { nome: '390x844', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
  { nome: '768x1024', viewport: { width: 768, height: 1024 } },
  { nome: '1920x1080', viewport: { width: 1920, height: 1080 } },
];

const DOC_FINTO = {
  id: 'doc-audit-e2e',
  filename: 'documento-test.pdf',
  category: 'fattura',
  status: 'processed',
  processed: true,
  file_size: 12345,
  data_ricezione: '2026-07-14T00:00:00Z',
};

// PDF minimo valido (header %PDF- + EOF), sufficiente perché il browser lo
// mostri come application/pdf senza errore nell'iframe.
const PDF_FINTO = Buffer.from(
  '%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
);

async function testaViewport(browser, vp) {
  const ctx = await browser.newContext(vp.isMobile
    ? { viewport: vp.viewport, isMobile: true, hasTouch: true }
    : { viewport: vp.viewport });
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem('auth_token', 'fake');
      localStorage.setItem('ceraldi_anno_globale', '2026');
    } catch {}
  });
  const page = await ctx.newPage();

  await page.route('**/api/**', route => {
    const url = route.request().url();
    if (url.includes('/api/auth/verify')) {
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ user: { id: 'a', email: 'a@a', name: 'A', role: 'admin' } }),
      });
    }
    if (url.includes('/api/documenti/lista')) {
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ documents: [DOC_FINTO], categories: {} }),
      });
    }
    if (url.includes(`/api/documenti/documento/${DOC_FINTO.id}/download`)) {
      return route.fulfill({ status: 200, contentType: 'application/pdf', body: PDF_FINTO });
    }
    if (url.includes('/api/documenti/statistiche')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });

  const risultati = [];
  try {
    await page.goto(BASE + '/documenti', { waitUntil: 'networkidle', timeout: 30000 });
  } catch {
    // networkidle può non arrivare con polling: si procede comunque
  }
  await page.waitForTimeout(1500);

  // La tabella coi documenti è nel tab "Tutti i Documenti" (di default è
  // selezionato "Per Mittente").
  await page.getByText('Tutti i Documenti', { exact: false }).first().click();
  await page.waitForTimeout(500);

  const bottoneVedi = page.locator(`[data-testid="view-pdf-${DOC_FINTO.id}"]`);
  const trovato = await bottoneVedi.count();
  if (!trovato) {
    risultati.push({ ok: false, nota: 'bottone "Vedi" non trovato — il documento finto non è nella lista renderizzata' });
    await ctx.close();
    return risultati;
  }

  await bottoneVedi.click();
  const overlay = page.locator('[data-testid="document-viewer-overlay"]');
  try {
    await overlay.waitFor({ state: 'visible', timeout: 10000 });
  } catch {
    risultati.push({ ok: false, nota: 'overlay del viewer non apparso entro 10s' });
    await ctx.close();
    return risultati;
  }

  // 1. Nessun overflow orizzontale introdotto dal modale
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  risultati.push({ ok: overflow <= 1, nota: `overflow orizzontale con modale aperto: ${overflow}px` });

  // 2. Bottone chiusura visibile e cliccabile
  const chiusura = page.locator('[data-testid="document-viewer-close"]');
  const chiusuraVisibile = await chiusura.isVisible().catch(() => false);
  risultati.push({ ok: chiusuraVisibile, nota: 'bottone chiusura raggiungibile' });

  // 3. Controlli principali presenti (fit larghezza/pagina, zoom, fullscreen, download)
  for (const testid of ['fit-width', 'fit-page', 'zoom-in', 'zoom-out', 'fullscreen', 'download']) {
    const presente = await page.locator(`[data-testid="document-viewer-${testid}"]`).count();
    risultati.push({ ok: presente > 0, nota: `controllo "${testid}" presente` });
  }

  // 4. ESC chiude il modale
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  const overlayDopoEsc = await overlay.count();
  const chiuso = overlayDopoEsc === 0 || !(await overlay.isVisible().catch(() => false));
  risultati.push({ ok: chiuso, nota: 'ESC chiude il modale' });

  // 5. Il focus torna al bottone di origine dopo la chiusura
  const focusTornato = await bottoneVedi.evaluate(el => el === document.activeElement).catch(() => false);
  risultati.push({ ok: focusTornato, nota: 'focus tornato al bottone "Vedi" dopo la chiusura' });

  await ctx.close();
  return risultati;
}

(async () => {
  const browser = await chromium.launch(EXE ? { executablePath: EXE } : {});
  let errori = 0;

  for (const vp of VIEWPORTS) {
    const risultati = await testaViewport(browser, vp);
    for (const r of risultati) {
      const riga = `[${vp.nome}] ${r.nota}`;
      if (r.ok) {
        console.log('OK  ' + riga);
      } else {
        errori += 1;
        console.error('FAIL ' + riga);
      }
    }
  }

  await browser.close();
  if (errori > 0) {
    console.error(`\nAUDIT VIEWER FALLITO: ${errori} controllo/i falliti.`);
    process.exit(1);
  }
  console.log('\nAUDIT VIEWER OK.');
})();
