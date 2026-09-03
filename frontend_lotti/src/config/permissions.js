// Permessi di NAVIGAZIONE — unica fonte per "chi può aprire cosa" nel
// frontend. ATTENZIONE: questo è solo UX (nascondere/bloccare pagine);
// la sicurezza vera sta nel backend (auth_dependency + require_admin).
// Estratto da navigation.js (fase 2 ristrutturazione 24/07/2026).

// Sezioni riservate all'amministratore: impostazioni/PIN/personale,
// controllo dati, backoffice, configurazione, backup, stampanti, cataloghi,
// collaudi. I dipendenti girano liberi su tutte le altre pagine.
export const ADMIN_TABS = [
  "personale", "controllo_dati", "backoffice", "configura", "backup",
  "stampanti", "cataloghi_esterni", "collaudi",
  // Rinominare un frigorifero riscrive il nome su tutti i controlli già
  // registrati: è una modifica ai registri, non una preferenza (25/07/2026).
  "attrezzature",
];

export function tabRiservataAdmin(tabId) {
  return ADMIN_TABS.includes(tabId);
}

// admin: booleano (tipicamente isAdmin() da auth.js — passato dal chiamante
// per mantenere questo modulo puro e testabile senza localStorage)
export function puoAprireTab(tabId, admin) {
  return !tabRiservataAdmin(tabId) || !!admin;
}
