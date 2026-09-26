// Le quattro applicazioni condividono lo stesso origin ma usano token diversi.
// Il logout del Gestionale deve quindi eliminare ogni credenziale derivata:
// altrimenti HR, Lotti o Menu restano aperti fino alla scadenza del loro JWT.
const CHIAVI_LOCALI_SESSIONE = Object.freeze([
  "auth_token",
  "admin_token",
  "pt_token",
  "pt_role",
  "pt_name",
  "lotti_token",
  "lotti_gate_until",
  "lotti_operatore_nome",
  "lotti_ruolo",
  "tablet_operatore",
]);

const CHIAVI_SESSIONE_TAB = Object.freeze([
  "tablet_operatore",
  "lotti_pagina_richiesta",
]);

export function pulisciSessioneGruppoBrowser() {
  for (const chiave of CHIAVI_LOCALI_SESSIONE) {
    try { localStorage.removeItem(chiave); } catch { /* storage non disponibile */ }
  }
  for (const chiave of CHIAVI_SESSIONE_TAB) {
    try { sessionStorage.removeItem(chiave); } catch { /* storage non disponibile */ }
  }
}

// «Esci» dell'amministratore da qualunque app del gruppo: con la sessione
// unica togliere solo il token locale non fa uscire nessuno (la pagina
// d'ingresso lo ricrea dal cookie del Gestionale). Il logout del Gestionale
// revoca la sessione sul server, e con lei i token di HR, Lotti e Menu.
export async function esciDalGruppo(destinazione = "/login") {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  } catch {
    // La pulizia locale resta necessaria anche se il backend non risponde.
  }
  pulisciSessioneGruppoBrowser();
  window.location.assign(destinazione);
}
