// Il periodo dell'Area Commercialista: mese, trimestre, anno o intervallo libero.
// Ogni scelta diventa sempre `dal`/`al` ISO (aaaa-mm-gg): e' quello che parlano i
// servizi del pacchetto. L'interfaccia scrive e legge gg/mm/aaaa.

export const MESI = [
  '', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
];

export const MODI_PERIODO = [
  { id: 'mese', label: 'Mese' },
  { id: 'trimestre', label: 'Trimestre' },
  { id: 'anno', label: 'Anno' },
  { id: 'personalizzato', label: 'Personalizzato' },
];

export const TRIMESTRI = [
  { id: 1, label: 'I trimestre (gen - mar)' },
  { id: 2, label: 'II trimestre (apr - giu)' },
  { id: 3, label: 'III trimestre (lug - set)' },
  { id: 4, label: 'IV trimestre (ott - dic)' },
];

const MAX_GIORNI = 400;
const pad = n => String(n).padStart(2, '0');
const ultimoGiorno = (anno, mese) => new Date(anno, mese, 0).getDate();

/** `30/09/2026` -> `2026-09-30`; null se non e' una data vera. */
export function isoDaIT(testo) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(testo || '').trim());
  if (!m) return null;
  const [g, me, a] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const d = new Date(a, me - 1, g);
  if (d.getFullYear() !== a || d.getMonth() !== me - 1 || d.getDate() !== g) return null;
  return `${a}-${pad(me)}-${pad(g)}`;
}

/** `2026-09-30` -> `30/09/2026`. */
export function itDaISO(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '';
}

/** Mentre si scrive: inserisce da solo le barre (`3009` -> `30/09/`). */
export function mascheraDataIT(testo) {
  const cifre = String(testo || '').replace(/\D/g, '').slice(0, 8);
  if (cifre.length <= 2) return cifre;
  if (cifre.length <= 4) return `${cifre.slice(0, 2)}/${cifre.slice(2)}`;
  return `${cifre.slice(0, 2)}/${cifre.slice(2, 4)}/${cifre.slice(4)}`;
}

const senzaErrore = (dal, al, etichetta, extra = {}) => ({
  valido: true, errore: null, dal, al, etichetta, ...extra,
});

/**
 * Il periodo scelto. `stato`: { modo, anno, mese (1-12), trimestre (1-4), dalIT, alIT }.
 * Restituisce { valido, errore, dal, al, etichetta, anno, meseRotta } dove `meseRotta`
 * e' il mese per le rotte `/{anno}/{mese}` (0 = non e' un mese singolo).
 */
export function calcolaPeriodo(stato) {
  const { modo = 'mese', anno, mese = 1, trimestre = 1, dalIT = '', alIT = '' } = stato || {};
  if (modo === 'mese') {
    return senzaErrore(`${anno}-${pad(mese)}-01`, `${anno}-${pad(mese)}-${pad(ultimoGiorno(anno, mese))}`,
      `${MESI[mese]} ${anno}`, { anno, meseRotta: mese });
  }
  if (modo === 'trimestre') {
    const primo = (trimestre - 1) * 3 + 1;
    const ultimo = primo + 2;
    return senzaErrore(`${anno}-${pad(primo)}-01`, `${anno}-${pad(ultimo)}-${pad(ultimoGiorno(anno, ultimo))}`,
      `${trimestre}° trimestre ${anno}`, { anno, meseRotta: 0 });
  }
  if (modo === 'anno') {
    return senzaErrore(`${anno}-01-01`, `${anno}-12-31`, `Intero anno ${anno}`, { anno, meseRotta: 0 });
  }
  const dal = isoDaIT(dalIT);
  const al = isoDaIT(alIT);
  const nullo = errore => ({ valido: false, errore, dal: null, al: null, etichetta: '', anno, meseRotta: 0 });
  if (!dal || !al) return nullo('Scrivi le due date come gg/mm/aaaa');
  if (dal > al) return nullo('La data di inizio e\' dopo quella di fine');
  const giorni = (new Date(al) - new Date(dal)) / 86400000;
  if (giorni > MAX_GIORNI) return nullo(`Periodo troppo lungo (massimo ${MAX_GIORNI} giorni)`);
  return senzaErrore(dal, al, `dal ${itDaISO(dal)} al ${itDaISO(al)}`, { anno: Number(dal.slice(0, 4)), meseRotta: 0 });
}

/** `?dal=..&al=..` (+ eventuali parametri extra) per ogni chiamata del pacchetto. */
export function queryPeriodo(periodo, extra = {}) {
  const parametri = new URLSearchParams({ dal: periodo.dal, al: periodo.al });
  Object.entries(extra).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') parametri.set(k, v);
  });
  return `?${parametri.toString()}`;
}

/** Il periodo di un mese dell'anno dato, come stato del selettore. */
export const statoMese = (anno, mese) => ({ modo: 'mese', anno, mese, trimestre: 1, dalIT: '', alIT: '' });
