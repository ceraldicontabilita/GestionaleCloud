import axios from "axios";
import { API } from "./constants";
import { toast } from "sonner";
import { apriDocumentoAutenticato } from "../auth";
import { MODI, getModoStampa, stampaEtichettaLotto, base64Di } from "./stampaEpson";

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
export function bytesToBase64(bytes) {
  return base64Di(new Uint8Array(bytes));
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
  if (categoria === "etichette" && getModoStampa() === MODI.RAWBT && /\/stampa\/lotto\//.test(url)) {
    await stampaRawbt(url);
    return { accodato: false, rawbt: true };
  }
  // Diretta dal dispositivo (Epson ePOS): solo per l'etichetta di un lotto.
  const lotto = categoria === "etichette" && getModoStampa() === MODI.EPSON
    ? /\/stampa\/lotto\/([^/?]+)\/?(?:\?|$)/.exec(url || "")
    : null;
  if (lotto) {
    try {
      await stampaEtichettaLotto(decodeURIComponent(lotto[1]), reparto);
      toast.success("Etichetta stampata");
      return { accodato: false, diretta: true };
    } catch (e) {
      // Mai perdere l'etichetta: motivo in chiaro e il documento resta apribile.
      toast.error(e.message, {
        duration: 20000,
        action: { label: "Apri PDF", onClick: () => apriDocumentoAutenticato(url) },
      });
      return { accodato: false, diretta: false, errore: e.message };
    }
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
