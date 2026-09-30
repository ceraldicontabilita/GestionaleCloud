import api from '../api';

/**
 * Contratto della vista `/protocollo/:id` (MINI-08) con l'API di MINI-07
 * (`GET /api/protocollo-personale/{anno}/{progressivo}`, solo admin).
 *
 * Il numero di protocollo e' `AAAA/NNNNNN`. La pagina legge UNA scheda e
 * mostra solo i campi qui sotto; quelli che il server non manda sono «Dato
 * non disponibile». Il protocollo personale e familiare non entra mai nei
 * conti dell'azienda (`accounting_excluded`): il ponte verso la contabilita'
 * (`collegati`) e' solo informativo e porta la rotta della sezione esistente.
 */
export const STATO_PROTOCOLLO = {
  DISPONIBILE: 'disponibile',
  NON_DISPONIBILE: 'non_disponibile',
  NON_TROVATO: 'non_trovato',
  ERRORE: 'errore',
};

/** Campi della scheda (nome nella risposta -> etichetta in pagina). */
export const CAMPI_SCHEDA_PROTOCOLLO = {
  numero: 'Numero di protocollo',
  data_protocollo: 'Data di protocollo',
  data_documento: 'Data del documento',
  tipo_documento: 'Tipo di documento',
  direzione: 'Entrata o uscita',
  controparte: 'Mittente o destinatario',
  pratica: 'Pratica',
  importo: 'Importo',
  nome_file: 'File',
  canale: 'Canale',
};

export const AMBITI = {
  personale_familiare: 'Personale e familiare, fuori dai conti',
  aziendale: 'Aziendale',
  da_verificare: 'Da verificare',
};

/** «2023/000123» -> { anno: 2023, progressivo: 123 }, altrimenti `null`. */
export function numeroProtocollo(id) {
  const m = /^(\d{4})\/(\d{1,9})$/.exec(String(id ?? '').trim());
  return m ? { anno: Number(m[1]), progressivo: Number(m[2]) } : null;
}

/**
 * Legge la scheda. Non inventa mai una risposta: un numero che non ha la
 * forma giusta e' «non trovato» senza chiamare la rete; un 404 del server
 * senza il codice `NON_TROVATO` (l'API non e' montata) e' «non disponibile».
 * @returns {Promise<{stato: string, dati?: object, messaggio?: string}>}
 */
export async function leggiProtocollo(id) {
  const numero = numeroProtocollo(id);
  if (!numero) return { stato: STATO_PROTOCOLLO.NON_TROVATO };
  try {
    const r = await api.get(`/api/protocollo-personale/${numero.anno}/${numero.progressivo}`);
    return { stato: STATO_PROTOCOLLO.DISPONIBILE, dati: r.data || {} };
  } catch (e) {
    const status = e?.response?.status;
    const codice = e?.response?.data?.detail?.code;
    if (status === 404 && codice === 'NON_TROVATO') return { stato: STATO_PROTOCOLLO.NON_TROVATO };
    if (status === 404 || status === 405) return { stato: STATO_PROTOCOLLO.NON_DISPONIBILE };
    const dettaglio = e?.response?.data?.detail;
    return {
      stato: STATO_PROTOCOLLO.ERRORE,
      messaggio: (typeof dettaglio === 'string' ? dettaglio : dettaglio?.message) || e?.message || 'Lettura non riuscita',
    };
  }
}
