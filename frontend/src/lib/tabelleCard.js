/**
 * Tabelle → card impilate su telefono (regola «mai scroll orizzontale»).
 *
 * Un meccanismo solo per tutte le pagine dell'ERP: su schermo stretto ogni
 * <table> con intestazione semplice diventa una pila di card, una per riga,
 * con l'etichetta della colonna sopra al valore. L'etichetta la copia da qui
 * dalle <th> in `data-label` di ogni <td>; il layout lo fa index.css
 * (`table[data-card="si"]`). Una tabella che non deve cambiare (matrici,
 * calendari) porta `data-card="no"`; una con intestazione a più livelli o con
 * colspan nell'intestazione resta com'è (scroll di riserva).
 */
export const BREAKPOINT_CARD = 768;

function celleIntestazione(tabella) {
  const righe = tabella.tHead ? [...tabella.tHead.rows] : [];
  if (righe.length === 1) return [...righe[0].cells];
  if (righe.length === 0) {
    const prima = tabella.rows[0];
    if (prima && [...prima.cells].every(c => c.tagName === 'TH')) return [...prima.cells];
  }
  return null;
}

export function etichettaTabella(tabella) {
  if (!tabella || tabella.dataset.card === 'no') return;
  const testa = celleIntestazione(tabella);
  if (!testa || testa.some(c => c.colSpan > 1)) return;
  const etichette = testa.map(c => (c.textContent || '').replace(/\s+/g, ' ').trim());
  for (const riga of tabella.rows) {
    if (riga.parentElement === tabella.tHead || riga === tabella.rows[0] && !tabella.tHead) continue;
    let colonna = 0;
    for (const cella of riga.cells) {
      const etichetta = cella.colSpan > 1 ? '' : etichette[colonna] || '';
      if (etichetta) {
        if (cella.dataset.label !== etichetta) cella.dataset.label = etichetta;
      } else if (cella.dataset.label !== undefined) {
        delete cella.dataset.label;
      }
      colonna += cella.colSpan || 1;
    }
  }
  tabella.dataset.card = 'si';
}

function tabelleDi(nodo) {
  if (!(nodo instanceof Element)) return [];
  const trovate = [...nodo.querySelectorAll('table')];
  const sopra = nodo.closest('table');
  if (sopra) trovate.push(sopra);
  return trovate;
}

export function avviaTabelleCard(radice = document.body) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {};
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
      if (r.type === 'childList') tabelleDi(r.target).forEach(t => coda.add(t));
    }
    if (coda.size) pianifica();
  };
  const accendi = () => {
    document.querySelectorAll('table').forEach(t => coda.add(t));
    pianifica();
    osservatore = new MutationObserver(ascolta);
    osservatore.observe(radice, { childList: true, subtree: true });
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
