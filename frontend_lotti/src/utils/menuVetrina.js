// Logica della vetrina «In menu» (19/09/2026).
//
// Il titolare: «il menu Lotti deve essere un contenitore visivo dei prodotti
// da vendere». Qui sta SOLO il ragionamento (nessun React, nessun axios), così
// è testabile: quali ricette sono nel Menu, dove finiscono, con che prezzo e
// quali sono da sistemare.
//
// Le regole ricalcano una per una quelle del ponte backend
// (`app/lotti/servizi/menu_bridge.py`: `prezzo_per_menu` e `_destinazione_menu`).
// Se una delle due cambia, cambiano entrambe: il frontend deve mostrare
// esattamente ciò che il Menu pubblicherà, non una seconda interpretazione.

// Destinazione canonica usata dal ponte Menu: una sola categoria e una
// sottocategoria derivata dal reparto operativo.
export const CATEGORIA_PREDEFINITA = "Produzione Ceraldi";
export const SOTTOCATEGORIA_PER_REPARTO = {
  pasticceria: "Pasticceria",
  rosticceria: "Rosticceria",
  bar: "Bar",
};
export const SOTTOCATEGORIA_ALTRO = "Altro";

// Ogni problema ha un testo: il colore da solo non è mai l'informazione.
export const PROBLEMI = {
  prezzo_banco: {
    etichetta: "Prezzo al banco nel Menu",
    aiuto: "Il prezzo al tavolo non è mai stato deciso: i clienti vedono quello al banco.",
    gravita: "avviso",
  },
  senza_prezzo: {
    etichetta: "Nessun prezzo",
    aiuto: "Né al tavolo né al banco: nel Menu la ricetta esce senza prezzo.",
    gravita: "pericolo",
  },
  senza_descrizione: {
    etichetta: "Senza descrizione",
    aiuto: "Manca la riga breve che il cliente legge sotto il nome.",
    gravita: "avviso",
  },
  senza_foto: {
    etichetta: "Senza foto",
    aiuto: "Nel Menu il prodotto compare senza immagine.",
    gravita: "avviso",
  },
};

export const ORDINE_PROBLEMI = [
  "senza_prezzo", "prezzo_banco", "senza_descrizione", "senza_foto",
];

const intero = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : null;
};

const numero = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number.parseFloat(String(v).replace(",", "."));
  return Number.isFinite(n) && n > 0 ? n : null;
};

const testo = (v) => (typeof v === "string" ? v.trim() : "");

/** Indice delle categorie Menu per lookup immediato (id → voce). */
export function indicizzaCategorie(payload) {
  const categorie = Array.isArray(payload?.categorie) ? payload.categorie : [];
  const perId = new Map();
  const sottoPerId = new Map();
  categorie.forEach((c) => {
    const id = intero(c?.id);
    if (id === null) return;
    perId.set(id, c);
    (Array.isArray(c?.sottocategorie) ? c.sottocategorie : []).forEach((s) => {
      const sid = intero(s?.id);
      if (sid === null) return;
      sottoPerId.set(sid, { ...s, category_id: intero(s?.category_id) });
    });
  });
  return { categorie, perId, sottoPerId, caricato: categorie.length > 0 };
}

export const nomeCategoria = (voce) =>
  testo(voce?.name_it) || testo(voce?.name) || (voce?.id != null ? `Categoria ${voce.id}` : "");

/** Sottocategoria canonica della ricetta: il suo reparto operativo. */
export const sottocategoriaPerReparto = (reparto) =>
  SOTTOCATEGORIA_PER_REPARTO[String(reparto || "").trim().toLowerCase()] || SOTTOCATEGORIA_ALTRO;

/**
 * Prezzo che il Menu espone e da dove viene — gemello di
 * `menu_bridge.prezzo_per_menu`.
 * @returns {{prezzo: number|null, origine: "tavolo"|"banco"|"assente"}}
 */
export function prezzoPerMenu(ricetta) {
  const tavolo = numero(ricetta?.prezzo_tavolo);
  if (tavolo !== null) return { prezzo: tavolo, origine: "tavolo" };
  const banco = numero(ricetta?.prezzo_vendita);
  if (banco !== null) return { prezzo: banco, origine: "banco" };
  return { prezzo: null, origine: "assente" };
}

/**
 * Dove finisce la ricetta nel Menu — gemello di `menu_bridge._destinazione_menu`.
 * @returns {{origine: "automatica",
 *            categoria: string, sottocategoria: string}}
 */
export function destinazioneMenu(ricetta) {
  return {
    categoria: CATEGORIA_PREDEFINITA,
    sottocategoria: sottocategoriaPerReparto(ricetta?.reparto),
    origine: "automatica",
  };
}

/** Le ricette che il titolare ha spuntato per il Menu pubblico. */
export const ricetteInMenu = (ricette) =>
  (Array.isArray(ricette) ? ricette : []).filter((r) => r?.menu_pubblico === true);

export const fotoRicetta = (r) => testo(r?.foto_url) || testo(r?.foto) || testo(r?.immagine);

export const allergeniRicetta = (r) =>
  (Array.isArray(r?.allergeni) ? r.allergeni : [])
    .map((a) => (typeof a === "string" ? a.trim() : testo(a?.nome)))
    .filter(Boolean);

/** Cosa c'è da sistemare su questa ricetta, in ordine di gravità. */
export function problemiRicettaMenu(ricetta) {
  const problemi = [];
  const { origine } = prezzoPerMenu(ricetta);
  if (origine === "assente") problemi.push("senza_prezzo");
  else if (origine === "banco") problemi.push("prezzo_banco");
  if (!testo(ricetta?.descrizione)) problemi.push("senza_descrizione");
  if (!fotoRicetta(ricetta)) problemi.push("senza_foto");
  return ORDINE_PROBLEMI.filter((codice) => problemi.includes(codice));
}

/** Quante ricette hanno ciascun problema (per i filtri a chip in cima). */
export function riepilogoProblemi(ricette, indice) {
  const conteggio = {};
  ORDINE_PROBLEMI.forEach((c) => { conteggio[c] = 0; });
  let daSistemare = 0;
  (Array.isArray(ricette) ? ricette : []).forEach((r) => {
    const p = problemiRicettaMenu(r, indice);
    if (p.length) daSistemare += 1;
    p.forEach((c) => { conteggio[c] += 1; });
  });
  return { conteggio, daSistemare, totale: (ricette || []).length };
}

/** Ordina per «prima quello che va sistemato», poi per nome. */
export function ordinaPerUrgenza(ricette, indice) {
  const peso = (r) => {
    const p = problemiRicettaMenu(r, indice);
    if (!p.length) return 99;
    return ORDINE_PROBLEMI.indexOf(p[0]);
  };
  return [...(Array.isArray(ricette) ? ricette : [])].sort((a, b) => {
    const d = peso(a) - peso(b);
    if (d !== 0) return d;
    return String(a?.nome || "").localeCompare(String(b?.nome || ""), "it");
  });
}
