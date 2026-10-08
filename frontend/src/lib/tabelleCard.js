/**
 * Tabelle → card impilate quando NON CI STANNO (regola «mai scroll orizzontale»).
 *
 * Un meccanismo solo per tutte le pagine dell'ERP, misurato sullo spazio reale:
 * ogni <table> con intestazione semplice riceve in `data-label` di ogni <td>
 * l'etichetta della colonna (copiata dalle <th>) e `data-card="si"`; poi si
 * misura quanto e' larga al minimo (ogni parola a capo, `width: min-content`)
 * e la si confronta con lo spazio del contenitore. Se non ci sta, o ci sta
 * solo spezzando le parole, prende `data-stretta` e index.css la disegna come
 * pila di card, una per riga. Si rimisura a ogni ridimensionamento della
 * finestra e a ogni tabella nuova. Decisione del titolare (07/10/2026): non
 * una versione per telefono e una per tablet, una pagina sola che si adatta.
 *
 * Sotto `BREAKPOINT_CARD` (telefono) e' sempre card, senza misurare. Una
 * tabella che non deve cambiare (matrici, calendari) porta `data-card="no"`;
 * una con intestazione a piu' livelli o con colspan nell'intestazione resta
 * com'e' (scroll di riserva).
 */
export const BREAKPOINT_CARD = 768;
// Una tabella «ci sta» solo con un po' d'aria oltre il minimo: al minimo ogni
// colonna e' larga quanto la sua parola piu' lunga e le descrizioni vanno a
// capo a ogni parola (iPad, 07/10/2026).
export const FATTORE_LEGGIBILITA = 1.15;
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

/** Etichette nei td e `data-card="si"`: la tabella e' pronta a diventare card. */
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

/**
 * La tabella ci sta nel suo spazio? `disponibile` e' la larghezza del
 * contenitore, `minima` quella della tabella con ogni parola a capo. Sotto il
 * telefono e' sempre card; senza misura (0) non si decide e resta tabella.
 */
export function ciSta({ disponibile, minima, finestra }) {
  if (finestra && finestra <= BREAKPOINT_CARD) return false;
  if (!disponibile || !minima) return true;
  return disponibile >= minima * FATTORE_LEGGIBILITA;
}

/** Larghezza minima reale della tabella (ogni parola a capo), misurata come tabella. */
function misuraMinima(tabella) {
  const eraStretta = tabella.dataset.stretta !== undefined;
  const larghezza = tabella.style.width;
  if (eraStretta) delete tabella.dataset.stretta;
  tabella.style.width = 'min-content';
  const minima = tabella.offsetWidth;
  tabella.style.width = larghezza;
  if (eraStretta) tabella.dataset.stretta = '';
  return minima;
}

/** Decide tabella o card per una tabella gia' etichettata (`data-card="si"`). */
export function adattaTabella(tabella, finestra = window.innerWidth) {
  if (!tabella || tabella.dataset.card !== 'si') return;
  if (finestra <= BREAKPOINT_CARD) {
    tabella.dataset.stretta = '';
    return;
  }
  const contenitore = tabella.parentElement;
  const disponibile = contenitore ? contenitore.clientWidth : 0;
  const minima = disponibile ? misuraMinima(tabella) : 0;
  if (ciSta({ disponibile, minima, finestra })) delete tabella.dataset.stretta;
  else tabella.dataset.stretta = '';
}

function tabelleDi(nodo) {
  if (nodo?.nodeType === Node.TEXT_NODE) nodo = nodo.parentElement;
  if (!(nodo instanceof Element)) return [];
  const trovate = [...nodo.querySelectorAll('table')];
  const sopra = nodo.closest('table');
  if (sopra) trovate.push(sopra);
  return trovate;
}

export function avviaTabelleCard(radice = document.body) {
  if (typeof window === 'undefined' || typeof MutationObserver === 'undefined') return () => {};
  let coda = new Set();
  let programmato = false;
  let attesaRidimensione = null;
  let fermato = false;
  const contenitori = new Map();
  const osservaDimensioni = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(entries => {
    for (const { target } of entries) {
      const larghezza = target.clientWidth;
      if (contenitori.get(target) === larghezza) continue;
      contenitori.set(target, larghezza);
      target.querySelectorAll('table[data-card="si"]').forEach(t => coda.add(t));
    }
    if (coda.size) pianifica();
  });

  const svuota = () => {
    programmato = false;
    if (fermato) return;
    const tabelle = coda;
    coda = new Set();
    tabelle.forEach(etichettaTabella);
    // Prima tutte le etichette, poi tutte le misure: una misura per tabella,
    // senza rimbalzare fra scrittura e lettura del layout.
    tabelle.forEach(t => {
      adattaTabella(t);
      const contenitore = t.parentElement;
      if (osservaDimensioni && t.dataset.card === 'si' && contenitore && !contenitori.has(contenitore)) {
        contenitori.set(contenitore, contenitore.clientWidth);
        osservaDimensioni.observe(contenitore);
      }
    });
  };
  const pianifica = () => {
    if (programmato || fermato) return;
    programmato = true;
    window.requestAnimationFrame(svuota);
  };
  const ascolta = records => {
    for (const r of records) {
      r.addedNodes.forEach(n => tabelleDi(n).forEach(t => coda.add(t)));
      tabelleDi(r.target).forEach(t => coda.add(t));
    }
    for (const contenitore of contenitori.keys()) {
      if (!contenitore.isConnected) {
        osservaDimensioni?.unobserve(contenitore);
        contenitori.delete(contenitore);
      }
    }
    if (coda.size) pianifica();
  };
  const ridimensiona = () => {
    if (attesaRidimensione) clearTimeout(attesaRidimensione);
    attesaRidimensione = setTimeout(() => {
      attesaRidimensione = null;
      radice.querySelectorAll('table[data-card="si"]').forEach(t => coda.add(t));
      if (coda.size) pianifica();
    }, 120);
  };

  radice.querySelectorAll('table').forEach(t => coda.add(t));
  pianifica();
  const osservatore = new MutationObserver(ascolta);
  osservatore.observe(radice, { childList: true, characterData: true, subtree: true });
  window.addEventListener('resize', ridimensiona);
  return () => {
    fermato = true;
    osservatore.disconnect();
    osservaDimensioni?.disconnect();
    contenitori.clear();
    coda.clear();
    window.removeEventListener('resize', ridimensiona);
    if (attesaRidimensione) clearTimeout(attesaRidimensione);
  };
}
