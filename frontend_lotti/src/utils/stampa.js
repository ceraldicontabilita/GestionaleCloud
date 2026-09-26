import axios from "axios";
import { API } from "./constants";
import { apriDocumentoAutenticato } from "../auth";

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
 * @param {string} o.url        URL del documento, SENZA token: il JWT non va mai
 *                              in un URL. L'agente di stampa si autentica da se'
 *                              con l'header Authorization del proprio operatore.
 * @param {string} [o.formato]  "pdf" | "html" (default pdf)
 * @param {string} [o.titolo]
 * @param {string} [o.reparto]
 * @returns {Promise<{accodato:boolean}>}
 */
export async function stampaDoc({ categoria, url, formato = "pdf", titolo = "", reparto = "" }) {
  if (isStampaAuto()) {
    await axios.post(`${API}/stampanti/coda`, { categoria, url, formato, titolo, reparto });
    return { accodato: true };
  }
  // Modalità classica: la scheda si apre subito, dentro il gesto del clic
  // (niente blocco popup), e il documento arriva con l'header Authorization.
  apriDocumentoAutenticato(url);
  return { accodato: false };
}
