// Le righe del PDF dei carnet assegni. Il beneficiario non e' una colonna: e' solo il
// ripiego del fornitore. Cio' che non e' collegato resta scritto «Da collegare», mai «-»:
// nessun collegamento si fa da qui (identita' e importo al centesimo sono del motore assegni).
import { formatDateIT } from './utils';

export const DA_COLLEGARE = 'Da collegare';

const pieno = valore => String(valore ?? '').trim();

/** Fornitore, numero e data fattura di un assegno, gia' arricchito dalla lista assegni. */
export function datiRigaAssegno(a) {
  const dettaglio = Array.isArray(a?.fatture_dettaglio) ? a.fatture_dettaglio : [];
  const dateDettaglio = [...new Set(dettaglio.map(d => d.data_fattura).filter(Boolean).map(formatDateIT))];
  const dataFattura = a?.data_fattura ? formatDateIT(a.data_fattura) : dateDettaglio.join(', ');
  return {
    fornitore: pieno(a?.fornitore_fattura || a?.fornitore_ragione_sociale || a?.beneficiario) || DA_COLLEGARE,
    numeroFattura: pieno(a?.numero_fattura || a?.fattura_numero) || DA_COLLEGARE,
    dataFattura: dataFattura || DA_COLLEGARE,
  };
}

export const senzaFattura = a => datiRigaAssegno(a).numeroFattura === DA_COLLEGARE;

export const contaSenzaFattura = assegni => (assegni || []).filter(senzaFattura).length;

/** La riga di avviso della card e del PDF, o stringa vuota se tutti sono collegati. */
export function avvisoSenzaFattura(assegni) {
  const n = contaSenzaFattura(assegni);
  return n ? `${n} assegn${n === 1 ? 'o' : 'i'} senza fattura collegata` : '';
}
