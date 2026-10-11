/** Unico adattamento tabelle per ERP, HR, Lotti, Menu e B&B.
 * Su telefono ogni riga mantiene celle, controlli e intestazioni complete.
 * Il DOM dei dati non viene clonato: click, input e aggiornamenti React restano attivi.
 * CSS limitato allo schermo mobile, senza modificare desktop o stampa.
 */
export const BREAKPOINT_CARD = 768;
const ETICHETTA_LUNGA = 22;

function righeIntestazione(tabella) {
  const righe = tabella.tHead ? [...tabella.tHead.rows] : [];
  if (righe.length) return righe;
  const prima = tabella.rows[0];
  if (prima && [...prima.cells].every(c => c.tagName === 'TH')) return [prima];
  return null;
}

/**
 * Etichetta di ogni colonna, anche con intestazione a più livelli (rowspan/colspan):
 * conserva il percorso gruppo/colonna (13ª · Busta, 14ª · Busta).
 */
function etichetteColonne(righe) {
  const occupata = [];
  const percorsi = [];
  righe.forEach((riga, r) => {
    let c = 0;
    for (const cella of riga.cells) {
      while (occupata[r] && occupata[r][c]) c += 1;
      const rs = cella.rowSpan || 1;
      const cs = cella.colSpan || 1;
      const testo = (cella.textContent || cella.getAttribute('aria-label') || cella.title || '').replace(/\s+/g, ' ').trim();
      for (let dr = 0; dr < rs; dr += 1) {
        occupata[r + dr] = occupata[r + dr] || [];
        for (let dc = 0; dc < cs; dc += 1) occupata[r + dr][c + dc] = true;
      }
      for (let dc = 0; dc < cs; dc += 1) {
        const percorso = percorsi[c + dc] ||= [];
        if (testo && percorso.at(-1) !== testo) percorso.push(testo);
      }
      c += cs;
    }
  });
  // Conserva anche il gruppo: "Busta" sotto 13ª e 14ª non sono lo stesso campo.
  return percorsi.map(x => x.join(' · '));
}

/**
 * Tabella senza intestazione (elenco «voce | valore», riepiloghi): non ha etichette da
 * copiare, ma resta una pila di righe invece di una tabella larga. Vale solo con poche
 * colonne (al massimo 3): oltre, senza intestazione non si sa cosa significhi ogni cella.
 */
const COLONNE_MAX_SENZA_TESTA = 3;
function senzaIntestazioneImpilabile(tabella) {
  const righe = [...tabella.rows];
  if (!righe.length) return false;
  return righe.every(r => r.cells.length > 0 && r.cells.length <= COLONNE_MAX_SENZA_TESTA);
}

export function etichettaTabella(tabella) {
  if (!tabella || tabella.dataset.card === 'no') return;
  const testa = righeIntestazione(tabella);
  delete tabella.dataset.chiaveValore;
  if (!testa) {
    if (senzaIntestazioneImpilabile(tabella)) {
      tabella.dataset.card = 'si';
      tabella.dataset.chiaveValore = '';
    }
    return;
  }
  const etichette = etichetteColonne(testa);
  if (!etichette.length) return;
  const intestazioni = new Set(testa);
  testa.forEach(riga => { riga.dataset.cardHeader = ''; });
  const occupate = [];
  for (const riga of tabella.rows) {
    if (intestazioni.has(riga)) continue;
    const contesto = occupate.filter(x => x?.righe > 0).map(x => x.testo).filter(Boolean);
    if (contesto.length) riga.dataset.cardContext = [...new Set(contesto)].join(' · ');
    else delete riga.dataset.cardContext;
    let colonna = 0;
    for (const cella of riga.cells) {
      while (occupate[colonna]?.righe > 0) colonna += 1;
      const etichetta = cella.colSpan > 1 ? '' : etichette[colonna] || '';
      if (etichetta) {
        if (cella.dataset.label !== etichetta) cella.dataset.label = etichetta;
        if (etichetta.length > ETICHETTA_LUNGA) cella.dataset.lungo = '';
        else delete cella.dataset.lungo;
      } else {
        delete cella.dataset.label;
        delete cella.dataset.lungo;
      }
      if (cella.rowSpan > 1) {
        for (let i = 0; i < cella.colSpan; i++) {
          occupate[colonna + i] = { righe: cella.rowSpan, testo: (cella.textContent || '').trim() };
        }
      }
      colonna += cella.colSpan || 1;
    }
    occupate.forEach(x => { if (x) x.righe -= 1; });
  }
  tabella.dataset.card = 'si';
}

function tabelleDi(nodo) {
  if (nodo?.nodeType === 3) nodo = nodo.parentElement;
  if (!(nodo instanceof Element)) return [];
  const trovate = [...nodo.querySelectorAll('table')];
  const sopra = nodo.closest('table');
  if (sopra) trovate.push(sopra);
  return trovate;
}

export function avviaTabelleCard(radice = document.body) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {};
  inserisciStile();
  const mq = window.matchMedia(`(max-width: ${BREAKPOINT_CARD}px)`);
  let osservatore = null;
  let coda = new Set();
  let programmato = false;

  const svuota = () => {
    programmato = false;
    const tabelle = coda;
    coda = new Set();
    tabelle.forEach(etichettaTabella);
  };
  const pianifica = () => {
    if (programmato) return;
    programmato = true;
    window.requestAnimationFrame(svuota);
  };
  const ascolta = records => {
    for (const r of records) {
      r.addedNodes.forEach(n => tabelleDi(n).forEach(t => coda.add(t)));
      if (r.type === 'childList' || r.type === 'characterData') tabelleDi(r.target).forEach(t => coda.add(t));
    }
    if (coda.size) pianifica();
  };
  const accendi = () => {
    radice.querySelectorAll('table').forEach(t => coda.add(t));
    pianifica();
    osservatore = new MutationObserver(ascolta);
    osservatore.observe(radice, { childList: true, subtree: true, characterData: true });
  };
  const spegni = () => {
    if (osservatore) osservatore.disconnect();
    osservatore = null;
  };
  const cambia = () => (mq.matches ? (osservatore ? null : accendi()) : spegni());

  cambia();
  mq.addEventListener ? mq.addEventListener('change', cambia) : mq.addListener(cambia);
  return () => {
    spegni();
    mq.removeEventListener ? mq.removeEventListener('change', cambia) : mq.removeListener(cambia);
  };
}

const ID_STILE = 'tabelle-card-stile';
const STILE = `
@media screen and (max-width: 768px) {
  table[data-card="si"] {
    display: block !important; width: 100% !important; max-width: 100% !important;
    min-width: 0 !important; border: 0 !important; background: transparent !important;
    white-space: normal !important; overflow: visible !important;
  }
  table[data-card="si"] > thead, table[data-card="si"] > colgroup,
  table[data-card="si"] [data-card-header] { display: none !important; }
  table[data-card="si"] > tbody, table[data-card="si"] > tfoot {
    display: block !important; width: 100% !important; min-width: 0 !important;
  }
  table[data-card="si"] > :is(tbody,tfoot) > tr,
  table[data-card="si"] > tr {
    display: block !important; width: 100% !important; min-width: 0 !important;
    box-sizing: border-box; height: auto !important; margin: 0 0 12px; padding: 8px 12px;
    background: var(--tabelle-card-bg, var(--c-card, #fffefb));
    border: 1px solid var(--c-border, var(--line, #e6e0d4)) !important; border-radius: 12px;
  }
  table[data-card="si"] tr[data-card-context]::before {
    content: attr(data-card-context); display: block; font-weight: 700; padding-block: 8px;
    overflow-wrap: anywhere;
  }
  table[data-card="si"] > :is(tbody,tfoot) > tr > :is(td,th),
  table[data-card="si"] > tr > :is(td,th) {
    display: block !important; position: static !important; width: 100% !important;
    min-width: 0 !important; max-width: 100% !important; height: auto !important;
    box-sizing: border-box; padding: 8px 0 !important; text-align: left !important;
    white-space: normal !important; overflow-wrap: anywhere; word-break: normal;
    border: 0 !important; border-bottom: 1px solid var(--c-border, var(--line, #e6e0d4)) !important;
    box-shadow: none !important; background: transparent !important;
  }
  table[data-card="si"] tr > :is(td,th):last-child { border-bottom: 0 !important; }
  table[data-card="si"] tr > :is(td,th)[data-label]::before {
    content: attr(data-label); display: block !important; position: static !important;
    width: auto !important; max-width: 100% !important; margin-bottom: 4px;
    font-weight: 600; font-size: 12px; line-height: 1.4; text-align: left;
    color: var(--c-text-muted, var(--mute, #6b7669)); white-space: normal;
  }
  table[data-card="si"] tr > :is(td,th):not([data-label])::before { display: none !important; }
  table[data-card="si"] :is(td,th) > * {
    min-width: 0 !important; max-width: 100% !important; box-sizing: border-box;
    white-space: normal !important; overflow-wrap: anywhere;
  }
  table[data-card="si"] :is(td,th) :is(.truncate,[class*="line-clamp-"]) {
    overflow: visible !important; text-overflow: clip !important; white-space: normal !important;
    -webkit-line-clamp: unset !important;
  }
  table[data-card="si"] :is(td,th) [style*="display: flex"] { flex-wrap: wrap; }
  table[data-card="si"] :is(button,a,select,input:not([type="checkbox"]):not([type="radio"]),summary) {
    min-height: 44px !important; max-width: 100%; white-space: normal; overflow-wrap: anywhere;
  }
  table[data-card="si"] :is(button,a,summary) { min-width: 44px !important; }
  table[data-card="si"] a { display: inline-flex; align-items: center; }
  table[data-card="si"] :is(select,textarea,input:not([type="checkbox"]):not([type="radio"])) {
    width: 100%; min-width: 0 !important; box-sizing: border-box;
  }
}
`;
function inserisciStile() {
  if (document.getElementById(ID_STILE)) return;
  const el = document.createElement('style');
  el.id = ID_STILE; el.textContent = STILE; document.head.appendChild(el);
}
