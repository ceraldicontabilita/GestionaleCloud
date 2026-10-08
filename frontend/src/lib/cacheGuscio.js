import api, { getAuthToken } from '../api';

// Copia nel browser dei dati letti: un solo meccanismo per il guscio e per
// le pagine.
//
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

// Pagine (26/09/2026): Prima Nota, Dashboard, IVA e riepiloghi mostrano
// subito l'ultima copia vista in questa sessione, con «aggiornato alle», e la
// sostituiscono appena arriva la risposta fresca. Stessa memoria e stesso
// legame col token del guscio; oltre ~2 MB non si salva (la pagina funziona
// lo stesso, solo senza copia).
const LIMITE_COPIA_PAGINA = 2000000;

export function scriviCopiaPagina(url, dati) {
  try {
    const testo = JSON.stringify({ tok: improntaToken(), at: Date.now(), dati });
    if (testo.length <= LIMITE_COPIA_PAGINA) sessionStorage.setItem(PREFISSO + url, testo);
  } catch (e) {
    // sessionStorage pieno o bloccato: niente copia, la pagina aspetta i dati
  }
}

/**
 * GET con copia: chiama subito ``onCopia(dati, at)`` se c'e' una copia valida
 * per questo token, poi fa la richiesta vera, salva la risposta e la
 * restituisce (gli errori passano al chiamante come prima).
 */
export async function getConCopia(url, config, onCopia) {
  const voce = leggiCacheGuscio(url);
  if (voce && onCopia) onCopia(voce.dati, voce.at);
  const risposta = config === undefined ? await api.get(url) : await api.get(url, config);
  scriviCopiaPagina(url, risposta.data);
  return risposta;
}

/** «aggiornato alle 14:32» dall'ora di una copia o di un'istantanea del server. */
export function aggiornatoAlle(quando) {
  if (!quando) return '';
  const data = new Date(quando);
  if (Number.isNaN(data.getTime())) return '';
  const ora = data.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  const oggi = new Date().toDateString() === data.toDateString();
  return oggi ? `aggiornato alle ${ora}` : `aggiornato il ${data.toLocaleDateString('it-IT')} alle ${ora}`;
}
