// I riepiloghi salvati prima della distinzione cedolini/presenze restano
// leggibili dopo un aggiornamento, senza ricaricare i PDF già elaborati.
export function normalizzaEsitoImportPaghe(esito) {
  if (!esito) return esito;
  const presenze = (esito.da_controllare || []).filter(v => !v.errore &&
    /^foglio presenze(?: \(\d+ pagin[ae]\), nessuna busta|, nessuna pagina retributiva)$/i.test(v.motivo || ''));
  if (!presenze.length) return esito;
  const saltati = [...(esito.saltati_presenze || [])];
  for (const voce of presenze) {
    if (!saltati.some(v => v.file === voce.file)) saltati.push(voce);
  }
  const errori = (esito.errori || []).filter(e => !presenze.some(v => v.file &&
    e === `${v.file}: nessuna busta acquisita. Controlla il documento e le segnalazioni.`));
  const da_controllare = (esito.da_controllare || []).filter(v => !presenze.includes(v));
  const soloPresenze = !esito.totale_associati && !esito.duplicati?.length && !errori.length && !da_controllare.length;
  return { ...esito, da_controllare, errori, saltati_presenze: saltati,
    ...(soloPresenze ? { esito: 'solo_presenze', success: true, partial: false } : {}) };
}
