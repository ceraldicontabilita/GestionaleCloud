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
