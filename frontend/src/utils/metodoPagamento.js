/**
 * «Metodo di pagamento non configurato», lato schermo.
 *
 * Gemello di `app/constants/metodi_pagamento.py`: la lista deve restare
 * uguale, e un test lo verifica. `misto` NON è fra questi: è un metodo vero
 * (il fornitore si paga in parte in cassa e in parte in banca). Il filtro
 * «Senza metodo pagamento» dell'archivio lo contava fra i mancanti e
 * mostrava 326 fatture invece di 53.
 */

/** I valori che significano «metodo non configurato» (minuscolo, senza spazi ai bordi). */
export const METODI_NON_CONFIGURATI = ['', 'sospesa', 'da_configurare', 'none', 'null'];

/** `true` se il metodo vale «non configurato»; tollera null, undefined, spazi e maiuscole. */
export function metodoNonConfigurato(valore) {
  if (valore === null || valore === undefined) return true;
  return METODI_NON_CONFIGURATI.includes(String(valore).trim().toLowerCase());
}
