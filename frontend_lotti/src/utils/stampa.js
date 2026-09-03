import axios from "axios";
import { API, withToken } from "./constants";

// Modalità "stampa automatica": i documenti vengono accodati all'agente locale
// che li manda alla stampante giusta per categoria. Se spenta, si apre la
// finestra di stampa del browser (comportamento classico).
export function isStampaAuto() {
  try { return localStorage.getItem("stampa_auto") === "1"; } catch { return false; }
}
export function setStampaAuto(on) {
  try { localStorage.setItem("stampa_auto", on ? "1" : "0"); } catch { /* no-op */ }
}

/**
 * Stampa un documento del backend.
 * @param {object} o
 * @param {string} o.categoria  etichette | ricette | manuale | scontrini | report
 * @param {string} o.url        URL del documento (senza token: lo aggiunge qui)
 * @param {string} [o.formato]  "pdf" | "html" (default pdf)
 * @param {string} [o.titolo]
 * @param {string} [o.reparto]
 * @returns {Promise<{accodato:boolean}>}
 */
export async function stampaDoc({ categoria, url, formato = "pdf", titolo = "", reparto = "" }) {
  const full = withToken(url);
  if (isStampaAuto()) {
    await axios.post(`${API}/stampanti/coda`, { categoria, url: full, formato, titolo, reparto });
    return { accodato: true };
  }
  // Modalità classica: apertura sincrona (resta nel gesto del clic → no popup-block).
  window.open(full, "_blank");
  return { accodato: false };
}
