/**
 * Audit automatico di layout — gira in CI a ogni push (workflow
 * audit-layout.yml) e in locale con: node scripts/audit-layout.cjs
 * (richiede `vite preview --port 4173` attivo e Playwright installato).
 *
 * Per ogni pagina, su telefono (390px) e monitor (1280px), verifica:
 *   1. NESSUN overflow orizzontale (elementi che escono dalle card o
 *      dallo schermo — es. bottoni fuori card, span di griglia sbagliati);
 *   2. NESSUN titolo h1-h4 invisibile (navy su fondo navy: il CSS globale
 *      colora gli heading di navy e sui widget scuri sparivano);
 *   3. La ROUTE risponde davvero: niente redirect silenzioso altrove e
 *      niente pagina 404 (se una voce di menù punta a una route sparita,
 *      il push deve diventare rosso, non "tornare alla Dashboard").
 *
 * Le API sono finte (auth ok + risposte vuote): si testa il LAYOUT, non i
 * dati. Esce con codice 1 se trova regressioni → il push fallisce in CI.
 */
let chromium;
try {
  ({ chromium } = require('playwright-core'));
} catch {
  // ambiente locale/sandbox: playwright globale
  ({ chromium } = require('/opt/node22/lib/node_modules/playwright/node_modules/playwright-core'));
}

const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:4173';
const EXE = process.env.PLAYWRIGHT_CHROMIUM || undefined;

const PAGINE = [
  '/', '/fornitori', '/prima-nota', '/riconciliazione',
  '/riconciliazione/f24', '/riconciliazione/paypal',
  '/riconciliazione/coerenza-pos', '/riconciliazione/assegni',
  '/fatture', '/fatture/corrispettivi', '/documenti', '/documenti/import',
  '/admin', '/noleggio', '/learning-machine', '/scadenze', '/mappa-gestionale',
];

const VIEWPORTS = [
  { nome: 'mobile', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
  { nome: 'desktop', viewport: { width: 1280, height: 800 } },
];

async function auditPagina(page, path) {
  try {
    await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 30000 });
  } catch {
    // networkidle può non arrivare con polling: si procede comunque
  }
  await page.waitForTimeout(1500);
  return page.evaluate(pathRichiesto => {
    const doc = document.documentElement;
    const overflow = doc.scrollWidth - doc.clientWidth;
    const pathname = window.location.pathname;
    const redirectata = pathname !== pathRichiesto;
    const nonTrovata = !!document.querySelector('[data-testid="pagina-non-trovata"]');
    const colpevoli = overflow > 1
      ? [...document.querySelectorAll('*')]
          .filter(el => el.getBoundingClientRect().right > doc.clientWidth + 1)
          .slice(0, 5)
          .map(el => (el.dataset.testid || el.className || el.tagName).toString().slice(0, 60))
      : [];

    const bgDi = el => {
      let n = el;
      while (n && n !== document.body) {
        const bg = getComputedStyle(n).backgroundColor;
        if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg;
        n = n.parentElement;
      }
      return 'white';
    };
    const invisibili = [...document.querySelectorAll('h1,h2,h3,h4')]
      .filter(h => h.offsetParent !== null && h.textContent.trim())
      .filter(h => getComputedStyle(h).color === 'rgb(15, 39, 68)'
                   && bgDi(h).includes('15, 39, 68'))
      .map(h => h.textContent.trim().slice(0, 50));

    return { overflow, colpevoli, invisibili, redirectata, pathname, nonTrovata };
  }, path);
}

(async () => {
  const browser = await chromium.launch(EXE ? { executablePath: EXE } : {});
  let errori = 0;

  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext(vp.nome === 'mobile'
      ? { viewport: vp.viewport, isMobile: true, hasTouch: true }
      : { viewport: vp.viewport });
    await ctx.addInitScript(() => {
      try {
        localStorage.setItem('auth_token', 'fake');
        localStorage.setItem('ceraldi_anno_globale', '2026');
      } catch {}
    });
    const page = await ctx.newPage();
    await page.route('**/api/**', route =>
      route.request().url().includes('/api/auth/verify')
        ? route.fulfill({ status: 200, contentType: 'application/json',
            body: JSON.stringify({ user: { id: 'a', email: 'a@a', name: 'A', role: 'admin' } }) })
        : route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    );

    for (const p of PAGINE) {
      const r = await auditPagina(page, p);
      const ok =
        r.overflow <= 1 && r.invisibili.length === 0 && !r.redirectata && !r.nonTrovata;
      const riga = `[${vp.nome}] ${p.padEnd(32)} overflowX:${String(r.overflow).padStart(3)}px  titoli invisibili:${r.invisibili.length}`;
      if (ok) {
        console.log('OK  ' + riga);
      } else {
        errori += 1;
        console.error('FAIL ' + riga);
        if (r.colpevoli.length) console.error('     sborda:', JSON.stringify(r.colpevoli));
        if (r.invisibili.length) console.error('     invisibili:', JSON.stringify(r.invisibili));
        if (r.redirectata) console.error(`     route redirectata a: ${r.pathname}`);
        if (r.nonTrovata) console.error('     la route mostra la pagina 404');
      }
    }
    await ctx.close();
  }

  await browser.close();
  if (errori > 0) {
    console.error(`\nAUDIT LAYOUT FALLITO: ${errori} pagina/e con regressioni.`);
    process.exit(1);
  }
  console.log('\nAUDIT LAYOUT OK: nessun overflow, nessun titolo invisibile.');
})();
