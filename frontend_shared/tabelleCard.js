/**
 * Tabelle → card impilate su telefono, per HR, Lotti e Menu (l'ERP ha la sua versione
 * con le stesse regole: `frontend/src/lib/tabelleCard.js`). Regola del titolare:
 * mai scroll orizzontale su smartphone, e un meccanismo solo, non una pagina alla volta.
 *
 * Su schermo stretto ogni <table> con una sola riga d'intestazione diventa una pila di
 * card, una per riga, con l'etichetta della colonna a fianco del valore (`data-label`,
 * copiata dalle <th>). `data-card="no"` tiene una tabella com'è (matrici, calendari);
 * un'intestazione a più livelli (colspan/rowspan) resta com'è. Una tabella già
 * scritta a card (`dc-table--cards`, HR) non si tocca.
 */
const LARGHEZZA_MAX = 768;
const ID_STILE = "tabelle-card-stile";

const STILE = `
@media screen and (max-width: ${LARGHEZZA_MAX}px) {
  table[data-card="si"] { display: block !important; width: 100% !important; min-width: 0 !important; border: 0 !important; }
  table[data-card="si"] thead { display: none !important; }
  table[data-card="si"] tbody, table[data-card="si"] tfoot { display: block !important; width: 100% !important; }
  table[data-card="si"] tr {
    display: block !important; width: 100% !important; box-sizing: border-box;
    background: #fffefb; border: 1px solid #e6e0d4 !important; border-radius: 12px;
    margin: 0 0 10px; padding: 8px 14px;
  }
  table[data-card="si"] td {
    display: flex !important; justify-content: space-between; align-items: center; gap: 12px;
    width: 100% !important; box-sizing: border-box; padding: 6px 0 !important;
    border: 0 !important; border-bottom: 1px solid #f0ece2 !important;
    text-align: right !important; white-space: normal !important; overflow-wrap: anywhere;
    font-size: 0.9rem;
  }
  table[data-card="si"] td:last-child { border-bottom: 0 !important; }
  table[data-card="si"] td::before {
    content: attr(data-label); flex-shrink: 0; max-width: 45%; text-align: left;
    font-weight: 600; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.04em; color: #6b7669;
  }
  table[data-card="si"] td:not([data-label]) { text-align: left !important; }
  table[data-card="si"] td:not([data-label])::before { display: none; }
  table[data-card="si"] td:empty { display: none !important; }
  table[data-card="si"] td button, table[data-card="si"] td a { min-height: 36px; }
}
`;

function inserisciStile() {
  if (document.getElementById(ID_STILE)) return;
  const el = document.createElement("style");
  el.id = ID_STILE;
  el.textContent = STILE;
  document.head.appendChild(el);
}

export function applicaCard(radice = document) {
  const piccolo = window.matchMedia(`(max-width: ${LARGHEZZA_MAX}px)`).matches;
  radice.querySelectorAll("table").forEach((tabella) => {
    if (tabella.dataset.card === "no" || tabella.classList.contains("dc-table--cards")) return;
    if (!piccolo) {
      if (tabella.dataset.card === "si") delete tabella.dataset.card;
      return;
    }
    const righeTesta = tabella.querySelectorAll("thead tr");
    if (righeTesta.length !== 1 || righeTesta[0].querySelector("[colspan],[rowspan]")) return;
    const etichette = Array.from(righeTesta[0].children).map((th) => (th.textContent || "").trim());
    const etichetta = (cella, i) => {
      if (!etichette[i]) return;
      if (cella.getAttribute("data-label") !== etichette[i]) cella.setAttribute("data-label", etichette[i]);
    };
    tabella.querySelectorAll("tbody tr").forEach((riga) => {
      if (Array.from(riga.children).some((c) => c.hasAttribute("colspan"))) return;
      Array.from(riga.children).forEach(etichetta);
    });
    // Righe dei totali: l'etichetta segue la colonna coperta, anche con colspan.
    tabella.querySelectorAll("tfoot tr").forEach((riga) => {
      let colonna = 0;
      Array.from(riga.children).forEach((cella) => {
        etichetta(cella, colonna);
        colonna += Number(cella.getAttribute("colspan")) || 1;
      });
    });
    tabella.dataset.card = "si";
  });
}

export function avviaTabelleCard() {
  inserisciStile();
  let pianificato = false;
  const rinvia = () => {
    if (pianificato) return;
    pianificato = true;
    requestAnimationFrame(() => { pianificato = false; applicaCard(); });
  };
  new MutationObserver(rinvia).observe(document.body, { childList: true, subtree: true, characterData: true });
  window.addEventListener("resize", rinvia);
  rinvia();
}
