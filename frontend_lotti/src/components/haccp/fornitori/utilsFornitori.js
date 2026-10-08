// Costanti e helper condivisi della sezione Fornitori
// (estratti da FornitoriList.jsx — refactor 25/07/2026, nessun cambio di logica)

// Stato iniziale della scheda contatti/condizioni (tutti i campi editabili)
export const CONTATTO_VUOTO = {
  email: "", cellulare: "", email_verificata: false,
  rivendita_colazione: false, rivendita_senza_glutine: false,
  pec: "", sito_web: "", referente: "", telefono_fisso: "",
  giorni_consegna: "", giorni_chiusura: "", ordine_minimo: "", condizioni_pagamento: "", metodo_pagamento: "", certificazioni: "",
  giorni_consegna_settimana: [], lead_time_giorni: 1, ora_limite_ordine: "",
  procedura_ordini_attiva: true, chiusure_programmate: [],
};

export const forniSlug = (nome) => (nome || "").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9\-]/g, "").slice(0, 60);

export const getFornitoreFromHash = (fornitori) => {
  const slug = window.location.hash.replace("#", "").split("/")[1] || "";
  if (!slug) return null;
  return fornitori.find(f => forniSlug(f.nome) === slug)?.nome || null;
};

export const setHashFornitore = (nome) => {
  window.location.hash = nome ? `fornitori/${forniSlug(nome)}` : "fornitori";
};
