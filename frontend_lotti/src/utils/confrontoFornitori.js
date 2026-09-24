/**
 * Miglior fornitore: formattazione e carrello per la vista Ordini → Confronto.
 * Gli importi arrivano dal backend come stringhe Decimal ("0.4525").
 */

export const CART_LS_KEY = "ordini_smart_carrello";

export function euro(valore, decimali = 2) {
  const n = Number(valore);
  if (valore === null || valore === undefined || valore === "" || Number.isNaN(n)) return "—";
  return "€ " + n.toLocaleString("it-IT", { minimumFractionDigits: decimali, maximumFractionDigits: decimali });
}

/** Prezzo per pezzo: sotto l'euro servono tre decimali per vedere la differenza. */
export function euroPezzo(valore) {
  const n = Number(valore);
  return euro(valore, !Number.isNaN(n) && Math.abs(n) < 1 ? 3 : 2);
}

/** "2026-08-26" → "26/08/2026" */
export function dataIt(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : String(iso || "");
}

/** Quanto costa in più di chi costa meno, per pezzo (stringa già formattata o ""). */
export function differenza(riga, migliore) {
  if (!riga || !migliore || riga === migliore) return "";
  const d = Number(riga.prezzo_pezzo) - Number(migliore.prezzo_pezzo);
  if (!(d > 0)) return "";
  return `+${euroPezzo(d)} al pezzo`;
}

/** Riga di carrello: si ordina nell'unità in cui il fornitore fattura. */
export function rigaCarrello(articolo, riga) {
  return {
    id: `conf_${articolo.chiave}_${riga.fornitore_id || riga.fornitore}`,
    nome: articolo.nome,
    // i codici di fattura (C5, B4, PZ...) cambiano da un fornitore all'altro
    unita_misura: riga.per_cartone ? "cartone" : /^KG/i.test(riga.unita_fattura || "") ? "kg" : "pz",
    fornitore: riga.fornitore,
    prezzo: Number(riga.prezzo_fattura),
    quantita: 1,
  };
}

export function aggiungiAlCarrello(item, storage = window.localStorage) {
  let items = [];
  try { items = JSON.parse(storage.getItem(CART_LS_KEY) || "[]"); } catch { items = []; }
  const idx = items.findIndex((x) => x.id === item.id);
  if (idx >= 0) items[idx].quantita = (Number(items[idx].quantita) || 0) + (Number(item.quantita) || 1);
  else items.push(item);
  try { storage.setItem(CART_LS_KEY, JSON.stringify(items)); } catch { /* memoria piena: resta in pagina */ }
  try { window.dispatchEvent(new Event("ordini_smart_cart_update")); } catch { /* ambiente senza window */ }
  return items;
}
