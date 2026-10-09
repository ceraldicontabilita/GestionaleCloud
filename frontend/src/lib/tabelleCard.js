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
const ETICHETTA_LUNGA = 22;

function righeIntestazione(tabella) {
  const righe = tabella.tHead ? [...tabella.tHead.rows] : [];
  if (righe.length) return righe.length <= 3 ? righe : null;
  const prima = tabella.rows[0];
  if (prima && [...prima.cells].every(c => c.tagName === 'TH')) return [prima];
  return null;
}

/**
 * Etichetta di ogni colonna, anche con intestazione a più livelli (rowspan/colspan):
 * vale la cella più in basso che copre la colonna (la «foglia»), quella del gruppo
 * («Registratore contro terminali») resta solo dove sotto non c'è altro.
 */
function etichetteColonne(righe) {
  const occupata = [];
  const foglia = [];
  righe.forEach((riga, r) => {
    let c = 0;
    for (const cella of riga.cells) {
      while (occupata[r] && occupata[r][c]) c += 1;
      const rs = cella.rowSpan || 1;
      const cs = cella.colSpan || 1;
      const testo = (cella.textContent || '').replace(/\s+/g, ' ').trim();
      for (let dr = 0; dr < rs; dr += 1) {
        occupata[r + dr] = occupata[r + dr] || [];
        for (let dc = 0; dc < cs; dc += 1) occupata[r + dr][c + dc] = true;
      }
      for (let dc = 0; dc < cs; dc += 1) {
        if (testo || foglia[c + dc] === undefined) foglia[c + dc] = testo;
      }
      c += cs;
    }
  });
  return foglia.map(x => x || '');
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
  for (const riga of tabella.rows) {
    if (intestazioni.has(riga)) continue;
    let colonna = 0;
    for (const cella of riga.cells) {
      const etichetta = cella.colSpan > 1 ? '' : etichette[colonna] || '';
      if (etichetta) {
        if (cella.dataset.label !== etichetta) cella.dataset.label = etichetta;
        // Etichetta lunga: il CSS la mette sopra al valore.
        if (etichetta.length > ETICHETTA_LUNGA) cella.dataset.lungo = '';
        else delete cella.dataset.lungo;
      } else if (cella.dataset.label !== undefined) {
        delete cella.dataset.label;
        delete cella.dataset.lungo;
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
