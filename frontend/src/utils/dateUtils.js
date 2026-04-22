/**
 * UTILITY FORMATTAZIONE ITALIANA
 *
 * REGOLA FONDAMENTALE:
 * - Date: formato GG/MM/AAAA (es. 25/01/2026)
 * - Valuta: formato € 0.000,00 (punto per migliaia, virgola per decimali)
 *
 * Usare SEMPRE queste funzioni in tutta l'applicazione!
 */

/**
 * Formatta una data nel formato italiano DD/MM/YYYY
 * @param {string|Date} dataStr - Data in qualsiasi formato
 * @returns {string} Data formattata GG/MM/AAAA
 */
export const formattaDataItaliana = dataStr => {
  if (!dataStr) return '';

  // Se è una stringa vuota o null
  if (typeof dataStr === 'string' && dataStr.trim() === '') return '';

  // Se contiene T, è formato ISO - estrai solo la data
  if (typeof dataStr === 'string' && dataStr.includes('T')) {
    dataStr = dataStr.split('T')[0];
  }

  // Formato YYYY-MM-DD (ISO)
  if (typeof dataStr === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dataStr)) {
    const [anno, mese, giorno] = dataStr.split('-');
    return `${giorno}/${mese}/${anno}`;
  }

  // Già in formato italiano DD/MM/YYYY
  if (typeof dataStr === 'string' && /^\d{2}\/\d{2}\/\d{4}$/.test(dataStr)) {
    return dataStr;
  }

  // Formato americano MM/DD/YYYY o MM/DD/YY - converti a italiano
  if (typeof dataStr === 'string' && /^\d{2}\/\d{2}\/\d{2,4}$/.test(dataStr)) {
    const parts = dataStr.split('/');
    // Se il primo numero è > 12, è già DD/MM
    if (parseInt(parts[0]) > 12) {
      return dataStr;
    }
    // Altrimenti assumiamo MM/DD/YY(YY) e convertiamo
    let anno = parts[2];
    if (anno.length === 2) {
      anno = parseInt(anno) > 50 ? '19' + anno : '20' + anno;
    }
    return `${parts[1]}/${parts[0]}/${anno}`;
  }

  // Prova parsing Date object
  try {
    const dt = dataStr instanceof Date ? dataStr : new Date(dataStr);
    if (!isNaN(dt.getTime())) {
      const giorno = String(dt.getDate()).padStart(2, '0');
      const mese = String(dt.getMonth() + 1).padStart(2, '0');
      const anno = dt.getFullYear();
      return `${giorno}/${mese}/${anno}`;
    }
  } catch (e) {
    /* ignora errori di parsing */
  }

  return dataStr;
};

/**
 * Formatta un importo nel formato italiano € 0.000,00
 * @param {number|string} importo - Importo da formattare
 * @param {boolean} conSymbolo - Se true, aggiunge € davanti (default: true)
 * @returns {string} Importo formattato
 */
export const formattaValutaItaliana = (importo, conSymbolo = true) => {
  if (importo === null || importo === undefined || importo === '')
    return conSymbolo ? '€ 0,00' : '0,00';

  const numero = typeof importo === 'string' ? parseFloat(importo.replace(',', '.')) : importo;

  if (isNaN(numero)) return conSymbolo ? '€ 0,00' : '0,00';

  // Formatta con separatore migliaia (.) e decimali (,)
  const formattato = numero.toLocaleString('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return conSymbolo ? `€ ${formattato}` : formattato;
};

/**
 * Alias breve per formattaValutaItaliana
 */
export const formatCurrency = formattaValutaItaliana;

/**
 * Alias breve per formattaDataItaliana
 */
export const formatDate = formattaDataItaliana;

/**
 * Calcola i giorni in un mese
 * @param {number} mese - Numero del mese (1-12)
 * @param {number} anno - Anno
 * @returns {number} Numero di giorni
 */
export const giorniNelMese = (mese, anno) => new Date(anno, mese, 0).getDate();

/**
 * Formatta un periodo (data inizio - data fine)
 * @param {string} dataInizio
 * @param {string} dataFine
 * @returns {string} Periodo formattato
 */
export const formattaPeriodo = (dataInizio, dataFine) => {
  const inizio = formattaDataItaliana(dataInizio);
  const fine = formattaDataItaliana(dataFine);
  if (!inizio && !fine) return '';
  if (!fine) return `dal ${inizio}`;
  if (!inizio) return `al ${fine}`;
  return `dal ${inizio} al ${fine}`;
};
