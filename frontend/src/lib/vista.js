import { formatDateIT, formatEuro } from './utils';

/**
 * Regole di lettura comuni alle viste `/fiscale/f24/:id`, `/fiscale/tributi/:codice`,
 * `/personale/cedolini/:id` e `/protocollo/:id` (MINI-08).
 *
 * - Un valore che manca e' «Dato non disponibile», mai zero: un importo `0`
 *   arriva dal server solo quando lo zero e' vero.
 * - Date sempre gg/mm/aaaa, importi in euro.
 * - Un solo modo di aprire un originale (`urlOriginale` e `ApriOriginale`,
 *   DRV-04): le pagine non compongono indirizzi di download da sole.
 */
export const NON_DISPONIBILE = 'Dato non disponibile';

const vuoto = v => v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v));

export const testoOppure = v => (vuoto(v) ? NON_DISPONIBILE : String(v));

export const dataOppure = v => (vuoto(v) ? NON_DISPONIBILE : formatDateIT(v));

/** Importo in euro (numero). `null`/assente = «Dato non disponibile». */
export const euroOppure = v => {
  if (vuoto(v)) return NON_DISPONIBILE;
  const n = Number(v);
  return Number.isFinite(n) ? formatEuro(n) : NON_DISPONIBILE;
};

/** Importo in centesimi (interi, come li da' `/api/f24/tributi`). */
export const euroCentesimiOppure = v => (vuoto(v) ? NON_DISPONIBILE : euroOppure(Number(v) / 100));

/**
 * Colonne dove il server manda 0 per «nessun importo» (inviato dal commercialista,
 * ravvedimento, credito, versato): lo zero si scrive «—», non «€ 0,00», che
 * sembrerebbe un versamento a zero. Un valore assente resta «Dato non disponibile».
 */
export const euroCentesimiOTrattino = v => (vuoto(v) ? NON_DISPONIBILE : Number(v) === 0 ? '—' : euroCentesimiOppure(v));

/** Il codice tributo e' sempre testo: mai convertito a numero. */
export const codiceTributo = v => String(v ?? '').trim();

export const ID_F24_DA_URL = /^\/api\/(?:originale\/(?:f24|quietanza)|f24-public\/pdf)\/([^/?#]+)/;

/** L'id di un modello o di una quietanza F24 dal suo indirizzo PDF, o `null`. */
export const idF24DaUrl = url => {
  const m = ID_F24_DA_URL.exec(String(url || ''));
  return m ? decodeURIComponent(m[1]) : null;
};

const segmenti = id => String(id).split('/').map(encodeURIComponent).join('/');

/**
 * L'indirizzo dell'originale (DRV-04): un endpoint solo, `/api/originale`.
 * - `tipo` + `id` (f24, quietanza, cedolino, fattura, documento, verbale,
 *   protocollo...; `indice` per il secondo PDF di un verbale o l'allegato di
 *   una fattura);
 * - `driveId` o `sha256` per un originale della cartella unica;
 * - `url` gia' pronto (quello che il server scrive in `pdf_url`).
 * Senza chiave `null` = non apribile. Il tipo lo valida il server.
 */
export function urlOriginale({ tipo, id, indice, driveId, sha256, url } = {}) {
  if (url) return url;
  if (!vuoto(driveId)) return `/api/originale?drive_id=${encodeURIComponent(String(driveId))}`;
  if (!vuoto(sha256)) return `/api/originale?sha256=${encodeURIComponent(String(sha256))}`;
  if (vuoto(id) || vuoto(tipo)) return null;
  const base = `/api/originale/${encodeURIComponent(String(tipo))}/${segmenti(id)}`;
  return indice ? `${base}?indice=${Number(indice)}` : base;
}

export const percorsoF24 = id => `/fiscale/f24/${encodeURIComponent(String(id))}`;
export const percorsoTributo = codice => `/fiscale/tributi/${encodeURIComponent(codiceTributo(codice))}`;
export const percorsoCedolino = id => `/personale/cedolini/${encodeURIComponent(String(id))}`;
/** `AAAA/NNNNNN` diventa `/protocollo/AAAA/NNNNNN`; un id di altra forma resta un solo segmento. */
export const percorsoProtocollo = id => {
  const m = /^(\d{4})\/(\d{1,9})$/.exec(String(id));
  return m ? `/protocollo/${m[1]}/${m[2]}` : `/protocollo/${encodeURIComponent(String(id))}`;
};

/**
 * Il filtro anno delle viste: `?anno=tutti` toglie il limite, `?anno=2024`
 * lo fissa, senza parametro vale l'anno globale (selettore in alto).
 */
export function annoDelFiltro(annoGlobale, parametro) {
  if (parametro === 'tutti') return null;
  const n = Number.parseInt(parametro, 10);
  return Number.isFinite(n) ? n : annoGlobale;
}
