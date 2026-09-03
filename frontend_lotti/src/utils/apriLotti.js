// Apre la pagina Tracciabilità con la ricerca già compilata su un lotto.
//
// Perché esiste (fix 25/07/2026): i tre punti che facevano questo salto
// scrivevano la chiave in sessionStorage e cambiavano l'hash. Ma se si era
// GIÀ sulla pagina Lotti l'hash non cambiava, l'effetto in App.js non si
// rieseguiva e il bottone sembrava rotto ("clicco Apri recall e non succede
// nulla" — segnalato dal titolare). Ora si emette anche un evento, così la
// ricerca si applica comunque.
export const EVENTO_RICERCA_LOTTI = "lotti-cerca";

export function apriLottiConRicerca(testo) {
  const q = String(testo || "").trim();
  try { sessionStorage.setItem("lotti_search", q); } catch { /* no-op */ }
  if (window.location.hash !== "#lotti") window.location.hash = "lotti";
  try {
    window.dispatchEvent(new CustomEvent(EVENTO_RICERCA_LOTTI, { detail: q }));
  } catch { /* no-op */ }
}
