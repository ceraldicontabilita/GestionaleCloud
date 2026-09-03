// Titoli e intestazioni di pagina — UNICA fonte per document.title,
// PageHeader e breadcrumb. Estratto da navigation.js/App.js (fase 2
// ristrutturazione 24/07/2026): qui SOLO metadati, niente routing.
import { PRIMARY_TABS, SECONDARY_TABS, HACCP_TABS } from "./navigation";

export const PAGE_NAMES = (() => {
  const names = {};
  [...PRIMARY_TABS, ...SECONDARY_TABS, ...HACCP_TABS].forEach((tab) => { names[tab.id] = tab.label; });
  Object.assign(names, {
    backup: "Backup", fatture: "Import fatture", ricettario: "Produzione",
    food_cost: "Produzione", listino: "Listino", magazzino_prodotti: "Giacenze",
    sconti_merce: "Sconti merce", stampanti: "Stampanti",
  });
  return names;
})();

const SAGE = "linear-gradient(135deg,#7d9b8b,#5b7a6b)";
export const PAGE_META = {
  fornitori: { sub: "Anagrafica e contatti dei fornitori", colore: SAGE, icona: "🚚" },
  lotti: { sub: "Tracciabilità lotti, scadenze e recall", colore: "linear-gradient(135deg,#c9a877,#8a6f47)", icona: "🏷️" },
  cosa_usare_oggi: { sub: "Lotti ordinati per scadenza e valore", colore: "linear-gradient(135deg,#e08e3e,#c4894a)", icona: "⏰" },
  dashboard_economica: { sub: "Valore lotti, spreco, margini e fornitori", colore: SAGE, icona: "💶" },
  produzione_consigliata: { sub: "Suggerimenti basati su storico, invenduto e festività", colore: "linear-gradient(135deg,#c9a877,#8a6f47)", icona: "👨‍🍳" },
  mappa_tracciabilita: { sub: "Percorso del prodotto dalla fattura allo smaltimento", colore: SAGE, icona: "🗺️" },
  storico_produzioni: { sub: "Produzioni registrate", colore: SAGE, icona: "📦" },
  fatture: { sub: "Fatture XML e prodotti acquistati", colore: SAGE, icona: "🧾" },
  materie: { sub: "Materie prime e giacenze", colore: SAGE, icona: "🌾" },
  prodotti: { sub: "Listini, cataloghi fornitori, prezzi banco e magazzino", colore: SAGE, icona: "📚" },
  magazzino_prodotti: { sub: "Giacenze di magazzino", colore: SAGE, icona: "📦" },
  movimenti_magazzino: { sub: "Prelievi, movimenti e rifornimenti", colore: SAGE, icona: "🔁" },
  sconti_merce: { sub: "Sconti e valorizzazioni merce", colore: SAGE, icona: "🏷️" },
  corrispettivi: { sub: "Corrispettivi giornalieri", colore: SAGE, icona: "💶" },
  disinfestazione: { sub: "Registro disinfestazione", colore: "linear-gradient(135deg,#f87171,#dc2626)", icona: "🐛" },
  sanificazione: { sub: "Registro sanificazione", colore: SAGE, icona: "✨" },
  temp_negative: { sub: "Temperature congelatori", colore: SAGE, icona: "❄️" },
  temp_positive: { sub: "Temperature frigoriferi", colore: "linear-gradient(135deg,#fb923c,#ea580c)", icona: "🌡️" },
  anomalie: { sub: "Anomalie e azioni correttive", colore: "linear-gradient(135deg,#fbbf24,#d97706)", icona: "⚠️" },
  controllo_olio: { sub: "Controllo olio di frittura", colore: "linear-gradient(135deg,#fb923c,#ea580c)", icona: "🔥" },
  temp_cottura: { sub: "Temperature di cottura", colore: "linear-gradient(135deg,#f87171,#dc2626)", icona: "🌡️" },
  ricezione_merce: { sub: "Controllo merce in ingresso", colore: "linear-gradient(135deg,#8a6f47,#6f583a)", icona: "📥" },
  allergeni: { sub: "Registro allergeni dei prodotti", colore: "linear-gradient(135deg,#fbbf24,#b45309)", icona: "⚠️" },
  schede_tecniche: { sub: "Schede tecniche e composizioni", colore: SAGE, icona: "📄" },
  registro_haccp: { sub: "Registro unico HACCP", colore: SAGE, icona: "✅" },
  manuale: { sub: "Manuale di autocontrollo HACCP", colore: SAGE, icona: "📗" },
  personale: { sub: "Dati azienda e personale", colore: SAGE, icona: "👤" },
  gelati: { sub: "Gestione gelati e semilavorati", colore: SAGE, icona: "🍨" },
  cataloghi_esterni: { sub: "Cataloghi e fonti dei fornitori", colore: SAGE, icona: "🌐" },
  collaudi: { sub: "Verifiche manuali successive alle modifiche", colore: SAGE, icona: "🧪" },
  attrezzature: { sub: "Nomi degli apparecchi, aggiunta, rimozione e guasti", colore: SAGE, icona: "🧊" },
};

// Pagine che disegnano da sole la propria intestazione (PageHeader NON mostrato)
export const TAB_HEADER_PROPRIO = new Set([
  "dashboard", "ricette", "backoffice", "food_cost", "ricettario",
  "configura", "guida", "stampanti", "backup",
]);
