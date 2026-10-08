/**
 * Avvia un polling soltanto mentre la pagina e' visibile e impedisce che due
 * richieste dello stesso giro si sovrappongano. Al ritorno sulla scheda esegue
 * subito un aggiornamento.
 */
export function avviaPollingVisibile(callback, intervalloMs) {
  let timer = null;
  let inCorso = false;

  const esegui = async () => {
    if (document.hidden || inCorso) return;
    inCorso = true;
    try { await callback(); } finally { inCorso = false; }
  };
  const ferma = () => {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
  };
  const avvia = () => {
    if (timer === null && !document.hidden) timer = window.setInterval(esegui, intervalloMs);
  };
  const visibilita = () => {
    if (document.hidden) ferma();
    else { esegui(); avvia(); }
  };

  document.addEventListener("visibilitychange", visibilita);
  avvia();
  return () => {
    ferma();
    document.removeEventListener("visibilitychange", visibilita);
  };
}
