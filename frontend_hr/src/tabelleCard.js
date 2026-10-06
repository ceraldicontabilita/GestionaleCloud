/**
 * Su telefono ogni tabella `dc-table` a una sola riga d'intestazione diventa una
 * card per riga (classe `dc-table--cards`, regole in App.css): niente scroll
 * orizzontale. L'etichetta di ogni cella viene dall'intestazione della colonna.
 * `data-card="no"` tiene una tabella com'è; un'intestazione a più livelli
 * (colspan/rowspan) non si tocca. Un solo meccanismo, come nell'ERP.
 */
const LARGHEZZA_MAX = 768;

export function applicaCard(radice = document) {
  const piccolo = window.matchMedia(`(max-width: ${LARGHEZZA_MAX}px)`).matches;
  radice.querySelectorAll('table.dc-table').forEach((tabella) => {
    if (tabella.classList.contains('dc-table--cards') && tabella.dataset.cardAuto !== 'si') return;
    if (tabella.dataset.card === 'no') return;
    if (!piccolo) {
      if (tabella.dataset.cardAuto === 'si') {
        tabella.classList.remove('dc-table--cards');
        delete tabella.dataset.cardAuto;
      }
      return;
    }
    const righeTesta = tabella.querySelectorAll('thead tr');
    if (righeTesta.length !== 1 || righeTesta[0].querySelector('[colspan],[rowspan]')) return;
    const etichette = Array.from(righeTesta[0].children).map((th) => (th.textContent || '').trim());
    tabella.querySelectorAll('tbody tr').forEach((riga) => {
      if (Array.from(riga.children).some((c) => c.hasAttribute('colspan'))) return;
      Array.from(riga.children).forEach((cella, i) => {
        if (!cella.hasAttribute('data-label') && etichette[i]) cella.setAttribute('data-label', etichette[i]);
      });
    });
    tabella.classList.add('dc-table--cards');
    tabella.dataset.cardAuto = 'si';
  });
}

export function avviaTabelleCard() {
  let pianificato = false;
  const rinvia = () => {
    if (pianificato) return;
    pianificato = true;
    requestAnimationFrame(() => { pianificato = false; applicaCard(); });
  };
  new MutationObserver(rinvia).observe(document.body, { childList: true, subtree: true });
  window.addEventListener('resize', rinvia);
  rinvia();
}
