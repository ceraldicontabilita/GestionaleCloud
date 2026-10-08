import api, { messaggioErrore } from '../api';

// Un solo modo di scaricare il file originale (PDF, XML) da un endpoint
// autenticato: prima c'erano sei copie dello stesso codice, e la maggior parte
// dei visualizzatori non aveva il pulsante «Scarica». Il nome del file arriva
// dall'intestazione del server quando c'e', altrimenti dal suggerimento.
export const nomeDaIntestazione = intestazione => {
  const testo = String(intestazione || '');
  const utf8 = testo.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      return utf8[1].trim();
    }
  }
  const semplice = testo.match(/filename="?([^";]+)"?/i);
  return semplice ? semplice[1].trim() : '';
};

export function salvaBlob(blob, nomeFile) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', nomeFile || 'documento');
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => window.URL.revokeObjectURL(url), 10000);
}

const ESTENSIONI = {
  'application/pdf': '.pdf',
  'application/xml': '.xml',
  'text/xml': '.xml',
  'text/html': '.html',
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
  'application/zip': '.zip',
};

// Un nome senza estensione la prende dal tipo del file: un documento HTML
// non deve arrivare come «.pdf».
export function conEstensione(nome, tipo) {
  if (/\.[a-z0-9]{2,5}$/i.test(nome || '')) return nome;
  const base = String(tipo || '').split(';')[0].trim().toLowerCase();
  return `${nome || 'documento'}${ESTENSIONI[base] || ''}`;
}

// Con `responseType: 'blob'` anche l'errore del server arriva come blob: si
// rilegge il JSON (`code`, `message`, `correlation_id`) per dire all'utente
// perche' l'originale non c'e', non «Request failed with status code 404».
export async function messaggioErroreOriginale(errore, predefinito = 'Originale non disponibile') {
  const dati = errore?.response?.data;
  if (dati instanceof Blob && /json/i.test(dati.type || '')) {
    try {
      const json = JSON.parse(await dati.text());
      return messaggioErrore({ ...errore, response: { ...errore.response, data: json } }, predefinito);
    } catch {
      /* il corpo non era JSON: vale il messaggio generico */
    }
  }
  return messaggioErrore(errore, predefinito);
}

export async function scaricaOriginale(url, nomeSuggerito = 'documento', mimeType) {
  const risposta = await api.get(url, { responseType: 'blob' });
  const tipo = risposta.headers?.['content-type'] || mimeType || 'application/octet-stream';
  const blob = risposta.data instanceof Blob ? risposta.data : new Blob([risposta.data], { type: tipo });
  const nome = nomeDaIntestazione(risposta.headers?.['content-disposition'])
    || conEstensione(nomeSuggerito, tipo);
  salvaBlob(blob, nome);
  return nome;
}

export default scaricaOriginale;
