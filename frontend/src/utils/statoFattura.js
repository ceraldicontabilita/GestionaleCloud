/**
 * L'unico posto, lato schermo, che sa se una fattura è pagata.
 *
 * Il 20/09/2026 ogni pagina se lo chiedeva a modo suo — `f.pagato`,
 * `f.status === 'paid'`, `f.stato_pagamento === 'pagata'` — e **nessuna**
 * guardava `f.stato`, che è il campo dove stanno le 639 fatture pagate
 * (311.838,20 €). Su quelle `f.pagato` è `undefined`, quindi l'interfaccia le
 * mostrava **non pagate**: è il motivo per cui in Prima Nota vedevi giorni
 * senza niente e fatture che sembravano aperte.
 *
 * Com'è davvero l'archivio, misurato su 2.555 fatture:
 *
 *     stato             786   pagata 639 · da_pagare 142 · parziale 5
 *     stato_pagamento   832   da_verificare 641 · da_pagare 142 · pagata 46 · pagato 3
 *     pagato             46   sempre true
 *     paid               46   sempre true
 *     payment_status     29   sempre "paid"
 *     status === 'paid'   0   ramo morto: `status` è lo stato del documento
 *
 * Gemello di `app/services/stato_pagamento_fattura.py`: le due liste di parole
 * devono restare uguali, e un test lo verifica.
 */

/** Ogni modo in cui l'archivio scrive «pagata». */
export const PAROLE_PAGATA = [
  'pagata', 'pagato', 'paid', 'saldata', 'saldato',
  'quietanzata', 'quietanzato', 'chiusa', 'chiuso', 'closed',
];
/** Una stornata non è né pagata né da pagare. */
export const PAROLE_ANNULLATA = [
  'annullata', 'annullato', 'stornata', 'stornato',
  'cancelled', 'canceled', 'deleted', 'eliminata', 'eliminato',
];
export const PAROLE_PARZIALE = ['parziale', 'partial', 'parzialmente_pagata'];
export const PAROLE_DA_PAGARE = ['da_pagare', 'non_pagata', 'non_pagato', 'unpaid', 'aperta'];

/** I campi che portano lo stato di *pagamento*. `status` no: è del documento. */
const CAMPI_STATO = ['stato_pagamento', 'stato', 'payment_status'];
const CAMPI_BOOLEANI = ['pagato', 'paid'];

const parole = (f) => CAMPI_STATO
  .map((c) => f?.[c])
  .filter((v) => v !== null && v !== undefined && v !== '')
  .map((v) => String(v).trim().toLowerCase());

const unBooleanoDiceSi = (f) =>
  CAMPI_BOOLEANI.some((c) => f?.[c] === true || String(f?.[c]).toLowerCase() === 'true');

/** Vera se un qualunque campo dichiara il pagamento: basta uno. */
export function ePagata(fattura) {
  if (eAnnullata(fattura)) return false;
  return unBooleanoDiceSi(fattura) || parole(fattura).some((p) => PAROLE_PAGATA.includes(p));
}

export function eAnnullata(fattura) {
  return parole(fattura).some((p) => PAROLE_ANNULLATA.includes(p));
}

export function eParziale(fattura) {
  return !ePagata(fattura) && parole(fattura).some((p) => PAROLE_PARZIALE.includes(p));
}

/**
 * Uno solo fra: pagata, parziale, da_pagare, annullata, da_verificare.
 * Quando nessun campo dice niente la risposta è `da_verificare`, non
 * `da_pagare`: le fatture fornitore non hanno scadenza, decide il titolare.
 */
export function statoPagamento(fattura) {
  if (eAnnullata(fattura)) return 'annullata';
  if (ePagata(fattura)) return 'pagata';
  const p = parole(fattura);
  if (p.some((x) => PAROLE_PARZIALE.includes(x))) return 'parziale';
  if (p.some((x) => PAROLE_DA_PAGARE.includes(x))) return 'da_pagare';
  return 'da_verificare';
}

/** Etichetta e colore per il badge, cosi' ogni pagina mostra la stessa cosa. */
export const ASPETTO_STATO = {
  pagata:        { testo: 'Pagata',        variante: 'success' },
  parziale:      { testo: 'Parziale',      variante: 'warning' },
  da_pagare:     { testo: 'Da pagare',     variante: 'danger'  },
  annullata:     { testo: 'Annullata',     variante: 'default' },
  da_verificare: { testo: 'Da verificare', variante: 'default' },
};
