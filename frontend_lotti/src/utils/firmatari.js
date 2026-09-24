/**
 * Chi ha firmato davvero le rilevazioni del mese (PIN o sessione verificata).
 *
 * Le schede temperature stampavano sempre «Operatori: Pocci Salvatore,
 * Vincenzo Ceraldi», due nomi scritti nel codice, qualunque cosa ci fosse nel
 * registro. Ora il nome c'e' solo se e' nella firma di una rilevazione.
 */
export function firmatariDelMese(schede, mese) {
  const nomi = new Set();
  Object.values(schede || {}).forEach((scheda) => {
    const giorni = scheda?.temperature?.[String(mese)] || {};
    Object.values(giorni).forEach((rec) => {
      if (rec && typeof rec === "object" && rec.firma_verificata && rec.operatore) nomi.add(rec.operatore);
    });
  });
  return [...nomi].sort();
}

export function testoFirmatari(schede, mese) {
  const nomi = firmatariDelMese(schede, mese);
  return nomi.length ? nomi.join(", ") : "nessuna firma verificata nel mese";
}
