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

// Modalità "tablet Android": l'etichetta lotto si scarica in ESC/POS e si passa
// all'app RawBT (LAN, Bluetooth o USB), che la manda all'Epson. Un browser non
// può aprire socket TCP, quindi l'app Android fa da ponte.
export function isStampaRawbt() {
  try { return localStorage.getItem("stampa_rawbt") === "1"; } catch { return false; }
}
export function setStampaRawbt(on) {
  try { localStorage.setItem("stampa_rawbt", on ? "1" : "0"); } catch { /* no-op */ }
}

export function bytesToBase64(bytes) {
  let bin = "";
  const u8 = new Uint8Array(bytes);
  for (let i = 0; i < u8.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

export function urlRawbt(bytes) {
  return `intent:base64,${bytesToBase64(bytes)}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;`;
}

/** Scarica l'ESC/POS di un'etichetta lotto e lo consegna a RawBT. */
export async function stampaRawbt(url) {
  const base = url.split("?")[0].replace(/\/$/, "");
  const esc = base.endsWith("/escpos") ? base : `${base}/escpos`;
  const { data } = await axios.get(esc, { responseType: "arraybuffer" });
  window.location.href = urlRawbt(data);
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
  if (isStampaRawbt() && /\/stampa\/lotto\//.test(url)) {
    await stampaRawbt(url);
    return { accodato: false, rawbt: true };
  }
  if (isStampaAuto()) {
    await axios.post(`${API}/stampanti/coda`, { categoria, url, formato, titolo, reparto });
    return { accodato: true };
  }
  // Modalità classica: la scheda si apre subito, dentro il gesto del clic
  // (niente blocco popup), e il documento arriva con l'header Authorization.
  apriDocumentoAutenticato(url);
  return { accodato: false };
}
