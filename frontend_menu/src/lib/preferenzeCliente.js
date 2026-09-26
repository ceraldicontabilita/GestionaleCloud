// Preferenze del cliente del menu pubblico, salvate solo nel suo browser.
//
// Il localStorage puo' mancare o lanciare (navigazione privata, dati del sito
// bloccati): ogni lettura e scrittura sta in try/catch e la pagina funziona
// comunque, con l'italiano e il banner dei cookie come punto di partenza.

export const LINGUE = ['it', 'en'];
export const LINGUA_PREDEFINITA = 'it';

const CHIAVE_LINGUA = 'menu_lingua';
const CHIAVE_CONSENSO = 'menu_consenso_cookie';
// Chiave storica: conservava solo il «si'» (`'true'`), il «no» non lasciava
// traccia e il banner ricompariva a ogni visita.
const CHIAVE_CONSENSO_STORICA = 'cookieAccepted';

export const CONSENSO_ACCETTATO = 'accettato';
export const CONSENSO_RIFIUTATO = 'rifiutato';

function leggi(chiave) {
  try {
    return window.localStorage.getItem(chiave);
  } catch {
    return null;
  }
}

function scrivi(chiave, valore) {
  try {
    window.localStorage.setItem(chiave, valore);
    return true;
  } catch {
    return false;
  }
}

export function leggiLingua() {
  const salvata = leggi(CHIAVE_LINGUA);
  return LINGUE.includes(salvata) ? salvata : LINGUA_PREDEFINITA;
}

export function salvaLingua(lingua) {
  if (!LINGUE.includes(lingua)) return false;
  return scrivi(CHIAVE_LINGUA, lingua);
}

/**
 * La scelta sui cookie: `{ scelta: 'accettato' | 'rifiutato', data }` oppure
 * `null` se il cliente non ha ancora risposto. `data` e' ISO-8601; per la
 * vecchia chiave (solo «accettato», senza data) resta `null`.
 */
export function leggiConsenso() {
  const grezzo = leggi(CHIAVE_CONSENSO);
  if (grezzo) {
    try {
      const valore = JSON.parse(grezzo);
      if (valore && [CONSENSO_ACCETTATO, CONSENSO_RIFIUTATO].includes(valore.scelta)) {
        return { scelta: valore.scelta, data: typeof valore.data === 'string' ? valore.data : null };
      }
    } catch {
      // valore illeggibile: si richiede la scelta
    }
  }
  if (leggi(CHIAVE_CONSENSO_STORICA) === 'true') {
    return { scelta: CONSENSO_ACCETTATO, data: null };
  }
  return null;
}

export function salvaConsenso(scelta, adesso = new Date()) {
  if (![CONSENSO_ACCETTATO, CONSENSO_RIFIUTATO].includes(scelta)) {
    throw new Error(`Scelta sui cookie sconosciuta: ${scelta}`);
  }
  const record = { scelta, data: adesso.toISOString() };
  scrivi(CHIAVE_CONSENSO, JSON.stringify(record));
  return record;
}
