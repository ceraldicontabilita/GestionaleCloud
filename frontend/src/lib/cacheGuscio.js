import { getAuthToken } from '../api';

// Dati del guscio dell'app (sessione, campana alert, avviso commercialista):
// una lettura all'apertura, poi un giro ogni 120 s. Il valore si tiene anche
// in sessionStorage, così un caricamento intero della pagina entro i 120 s
// lo riusa invece di richiederlo. La voce vale solo per il token con cui è
// stata letta: dopo logout, nuovo login o rinnovo del token si rilegge.
export const INTERVALLO_GUSCIO_MS = 120000;

const PREFISSO = 'guscio:';

function improntaToken() {
  const token = getAuthToken();
  return token ? token.slice(-24) : '';
}

export function leggiCacheGuscio(chiave) {
  try {
    const voce = JSON.parse(sessionStorage.getItem(PREFISSO + chiave));
    if (voce && voce.tok && voce.tok === improntaToken()) return voce;
  } catch (e) {
    // sessionStorage assente o voce illeggibile: si rilegge dal backend
  }
  return null;
}

export function scriviCacheGuscio(chiave, dati) {
  try {
    sessionStorage.setItem(
      PREFISSO + chiave,
      JSON.stringify({ tok: improntaToken(), at: Date.now(), dati })
    );
  } catch (e) {
    // sessionStorage pieno o bloccato: resta la copia in memoria
  }
}

/** Millisecondi prima del prossimo giro: 0 se la copia manca o è scaduta. */
export function attesaProssimoGiro(chiave) {
  const voce = leggiCacheGuscio(chiave);
  if (!voce) return 0;
  return Math.max(0, INTERVALLO_GUSCIO_MS - (Date.now() - voce.at));
}
