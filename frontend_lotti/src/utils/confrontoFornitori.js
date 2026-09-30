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

/** Unità in cui si ordina da quel fornitore: quella del listino («12 PZ»)
 *  o quella della fattura (i codici C5, B4, PZ... cambiano da un fornitore all'altro). */
export function unitaOrdine(riga) {
  if (riga?.origine === "listino") return (riga.unita_vendita || riga.unita_fattura || "pz").toLowerCase();
  return riga?.per_cartone ? "cartone" : /^KG/i.test(riga?.unita_fattura || "") ? "kg" : "pz";
}

/** Riga di carrello: si ordina nell'unità in cui il fornitore vende. */
export function rigaCarrello(articolo, riga) {
  return {
    id: `conf_${articolo.chiave}_${riga.fornitore_id || riga.fornitore}`,
    nome: articolo.nome_standard || articolo.nome,
    unita_misura: unitaOrdine(riga),
    fornitore: riga.fornitore,
    prezzo: Number(riga.prezzo_fattura),
    prezzo_fonte: riga.origine === "listino" ? "listino_fornitore" : "fattura_xml",
    prezzo_iva_esclusa: true,
    codici: riga.codice_articolo ? [riga.codice_articolo] : [],
    quantita: 1,
  };
}

/** Chi vende a meno l'articolo scelto (backend: GET /confronto-fornitori/migliore).
 *  Torna il consiglio o null: senza confronto si ordina da dove lo si è scelto. */
export async function chiediMigliore(axios, API, { descrizione, fornitore, codice, prodottoMasterId }) {
  try {
    const { data } = await axios.get(`${API}/confronto-fornitori/migliore`, {
      params: {
        descrizione: descrizione || "", fornitore: fornitore || "", codice: codice || "",
        prodotto_master_id: prodottoMasterId || "",
      },
      timeout: 10000,
    });
    return data?.trovato ? data : null;
  } catch {
    return null;
  }
}

/** La riga di carrello spostata sul fornitore più conveniente. */
export function versoIlMigliore(item, esito) {
  const c = esito?.consiglio;
  if (!c?.cambia || !c.migliore) return { item, cambiato: false };
  const m = c.migliore;
  return {
    cambiato: true,
    da: c.attuale?.fornitore || item.fornitore,
    risparmio: c.risparmio_pezzo,
    item: {
      ...item,
      nome: esito.articolo?.nome_standard || item.nome,
      fornitore: m.fornitore,
      prezzo: Number(m.prezzo_fattura) || item.prezzo,
      prezzo_fonte: m.origine === "listino" ? "listino_fornitore" : "fattura_xml",
      prezzo_iva_esclusa: true,
      unita_misura: unitaOrdine(m),
      codici: m.codice_articolo ? [m.codice_articolo] : (item.codici || []),
      fornitore_scelto_da: "miglior_prezzo",
      fornitore_proposto: item.fornitore,
    },
  };
}

/** Testo del toast: dove parte l'ordine e perché. */
export function messaggioMigliore(nome, spostato) {
  const m = spostato.item;
  const prezzo = spostato.risparmio && Number(spostato.risparmio) > 0 ? ` — ${euroPezzo(spostato.risparmio)} in meno al pezzo` : "";
  return `${String(nome).slice(0, 40)}: si ordina da ${m.fornitore}, il più conveniente${prezzo} (invece di ${spostato.da})`;
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
