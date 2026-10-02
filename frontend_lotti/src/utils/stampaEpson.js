// Stampa diretta dal dispositivo su Epson TM-T20III di rete (ePOS-Print XML).
//
// Il tablet parla da solo con la stampante, senza server ne' PC: Render non
// raggiunge la LAN del negozio. L'IP viene sempre dalla configurazione
// (Impostazioni > Stampanti), mai scritto qui. Lotti e' in https, quindi anche
// la chiamata alla stampante lo e' (porta 443, certificato autofirmato da
// accettare una volta aprendo https://<ip> in Chrome).
import axios from "axios";
import { API } from "./constants";

export const LARGHEZZA_PUNTI = 576; // 80 mm a 203 dpi
const NS = "http://www.epson-pos.com/schemas/2011/03/epos-print";

// ── Modalita' di stampa, per dispositivo ────────────────────────────────────
export const MODI = { FINESTRA: "finestra", AGENTE: "agente", EPSON: "epson" };

export function getModoStampa() {
  try {
    const m = localStorage.getItem("stampa_modo");
    if (Object.values(MODI).includes(m)) return m;
    // Compatibilita': prima esisteva solo l'interruttore dell'agente PC.
    return localStorage.getItem("stampa_auto") === "1" ? MODI.AGENTE : MODI.FINESTRA;
  } catch { return MODI.FINESTRA; }
}
export function setModoStampa(modo) {
  try {
    localStorage.setItem("stampa_modo", modo);
    // Tiene allineato il vecchio flag che legge ancora stampaDoc/agente.
    localStorage.setItem("stampa_auto", modo === MODI.AGENTE ? "1" : "0");
  } catch { /* no-op */ }
}

// ── Raster 1 bit + XML ePOS-Print (funzioni pure, testabili) ────────────────
/** ImageData RGBA → byte 1 bit per pixel, riga per riga, bit 7 = primo pixel, 1 = nero. */
export function rasterizza(data, width, height, soglia = 160) {
  const perRiga = Math.ceil(width / 8);
  const out = new Uint8Array(perRiga * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const a = data[i + 3];
      const lum = a === 0 ? 255 : (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
      if (lum < soglia) out[y * perRiga + (x >> 3)] |= 0x80 >> (x & 7);
    }
  }
  return out;
}

export function base64Di(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

export function costruisciXml({ bytes, width, height, testo = "" }) {
  const img = bytes
    ? `<image width="${width}" height="${height}" color="color_1" mode="mono">${base64Di(bytes)}</image>`
    : "";
  const riga = testo ? `<text>${testo.replace(/[<>&]/g, "")}&#10;</text>` : "";
  return (
    `<?xml version="1.0" encoding="utf-8"?>` +
    `<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>` +
    `<epos-print xmlns="${NS}">${riga}${img}<feed line="2"/><cut type="feed"/></epos-print>` +
    `</s:Body></s:Envelope>`
  );
}

// ── Errori in italiano ──────────────────────────────────────────────────────
export class ErroreStampaDiretta extends Error {}

export function spiegaErrore(e, host = "") {
  const dove = host ? `https://${host}` : "la stampante";
  if (e instanceof ErroreStampaDiretta) return e.message;
  if (e && e.name === "AbortError") {
    return `La stampante non risponde (${host || "IP non raggiungibile"}). Controlla che sia accesa, collegata alla rete e che l'indirizzo IP sia giusto.`;
  }
  return (
    `Il tablet non riesce a parlare con la stampante. Possibili cause: ` +
    `1) il certificato non è stato accettato (apri ${dove} in Chrome e scegli «Avanzate → Procedi»); ` +
    `2) Chrome ha negato l'accesso alla rete locale (tocca il lucchetto accanto all'indirizzo → Impostazioni sito → «Dispositivi in rete locale» → Consenti); ` +
    `3) stampante spenta o IP errato; ` +
    `4) ePOS-Print non attivo nella configurazione web della stampante.`
  );
}

/** Invia un lavoro XML alla stampante. Lancia ErroreStampaDiretta/errori di rete. */
export async function inviaXml(host, xml, { timeoutMs = 12000 } = {}) {
  if (!host) throw new ErroreStampaDiretta("Nessun indirizzo IP configurato per questa stampante: impostalo in Impostazioni → Stampanti.");
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`https://${host}/cgi-bin/epos/service.cgi?devid=local_printer&timeout=10000`, {
      method: "POST",
      headers: { "Content-Type": "text/xml; charset=utf-8", SOAPAction: '""' },
      body: xml,
      signal: ctrl.signal,
      // Chrome «accesso alla rete locale»: dichiara che la meta' e' in LAN.
      targetAddressSpace: "local",
    });
  } finally {
    clearTimeout(t);
  }
  if (!res.ok) throw new ErroreStampaDiretta(`La stampante ha risposto con errore ${res.status}. Verifica che ePOS-Print sia attivo nella sua configurazione web.`);
  const corpo = await res.text();
  if (/success="true"/i.test(corpo)) return true;
  const code = (corpo.match(/code="([^"]*)"/i) || [])[1] || "";
  const noti = {
    EPTR_COVER_OPEN: "Il coperchio della stampante è aperto.",
    EPTR_REC_EMPTY: "La carta è finita.",
    EPTR_AUTOMATICAL: "Il tagliacarte si è bloccato.",
    EPTR_COVER_OPEN_ALT: "Il coperchio della stampante è aperto.",
    SchemaError: "La stampante non ha accettato il comando (ePOS-Print non configurato correttamente).",
    PRINTER_IS_BUSY: "La stampante è occupata: riprova tra qualche secondo.",
  };
  throw new ErroreStampaDiretta(noti[code] || `La stampante ha rifiutato il lavoro${code ? ` (${code})` : ""}.`);
}

// ── Disegno dell'etichetta su canvas ────────────────────────────────────────
function righeA(ctx, testo, maxW) {
  const parole = String(testo || "").split(/\s+/).filter(Boolean);
  const righe = [];
  let cur = "";
  for (const p of parole) {
    const prova = cur ? `${cur} ${p}` : p;
    if (cur && ctx.measureText(prova).width > maxW) { righe.push(cur); cur = p; } else cur = prova;
  }
  if (cur) righe.push(cur);
  return righe;
}

/**
 * Disegna l'etichetta lotto (stesso contenuto dell'etichetta HTML attuale).
 * `d` e' la risposta di GET /stampa/lotto/{id}/dati.
 */
export function disegnaEtichetta(d, canvas = document.createElement("canvas")) {
  const W = LARGHEZZA_PUNTI, M = 14, maxW = W - 2 * M;
  const FONT = '"Plus Jakarta Sans", system-ui, Arial, sans-serif';
  // Prima passata per misurare l'altezza, seconda per disegnare.
  const passata = (ctx, disegna) => {
    let y = 12;
    const testo = (t, px, { bold = true, align = "center", gap = 6 } = {}) => {
      ctx.font = `${bold ? "800" : "500"} ${px}px ${FONT}`;
      ctx.textAlign = align;
      const x = align === "center" ? W / 2 : M;
      for (const r of righeA(ctx, t, maxW)) {
        y += px;
        if (disegna) ctx.fillText(r, x, y);
        y += 4;
      }
      y += gap;
    };
    const coppia = (a, b, px, bold = true) => {
      y += px;
      if (disegna) {
        ctx.font = `500 ${px}px ${FONT}`; ctx.textAlign = "left"; ctx.fillText(a, M, y);
        ctx.font = `${bold ? "800" : "500"} ${px}px ${FONT}`; ctx.textAlign = "right"; ctx.fillText(b, W - M, y);
      }
      y += 10;
    };
    const linea = (tratteggio) => {
      y += 4;
      if (disegna) {
        ctx.save(); ctx.lineWidth = 2; ctx.setLineDash(tratteggio ? [8, 6] : []);
        ctx.beginPath(); ctx.moveTo(M, y); ctx.lineTo(W - M, y); ctx.stroke(); ctx.restore();
      }
      y += 10;
    };

    testo(d.azienda || "", 26);
    if (d.indirizzo) testo(d.indirizzo, 16, { bold: false });
    testo((d.prodotto || "").toUpperCase(), 38, { gap: 8 });
    testo("LOTTO DI PRODUZIONE", 16, { bold: false, gap: 4 });
    // riquadro del numero di lotto
    ctx.font = `800 32px ${FONT}`;
    const numero = d.numero_lotto || "N/D";
    const w = Math.min(maxW, ctx.measureText(numero).width + 28);
    if (disegna) {
      ctx.save(); ctx.lineWidth = 3; ctx.strokeRect((W - w) / 2, y, w, 48); ctx.restore();
      ctx.textAlign = "center"; ctx.fillText(numero, W / 2, y + 36);
    }
    y += 48 + 10;
    if (d.quantita) testo(`QTA: ${d.quantita} ${d.unita || "pz"}`, 22, { gap: 4 });
    linea(false);
    coppia("PRODUZIONE:", d.data_produzione || "—", 22);
    coppia("SCADENZA:", d.data_scadenza || "—", 28);
    if (d.scadenza_abbattuto) coppia("SCAD -18°C:", d.scadenza_abbattuto, 22);
    if (d.frigo) coppia("FRIGO:", String(d.frigo), 22);
    if (d.operatore) coppia("OPERATORE:", d.operatore, 22);
    if ((d.ingredienti || []).length) {
      linea(true);
      testo("Ingredienti", 18, { align: "left", gap: 2 });
      for (const i of d.ingredienti) testo(`• ${i}`, 16, { bold: false, align: "left", gap: 0 });
    }
    // riquadro allergeni
    y += 10;
    const testoAll = (d.allergeni || []).length ? (d.allergeni || []).join(" · ") : "";
    const inizio = y;
    y += 8;
    if ((d.allergeni || []).length) {
      testo("!!! ALLERGENI (Reg. UE 1169/2011) !!!", 17);
      testo(testoAll, 22, { gap: 2 });
    } else {
      testo("✓ Non contiene allergeni dichiarati", 18, { gap: 2 });
    }
    y += 4;
    if (disegna) { ctx.save(); ctx.lineWidth = 3; ctx.strokeRect(M, inizio, maxW, y - inizio); ctx.restore(); }
    y += 12;
    testo("Reg. CE 178/2002", 14, { bold: false, gap: 2 });
    const quando = d.stampato ? new Date(d.stampato) : new Date();
    testo(`Stampato: ${quando.toLocaleString("it-IT", { timeZone: "Europe/Rome" })}`, 14, { bold: false, gap: 8 });
    return y + 8;
  };

  canvas.width = W;
  const misura = canvas.getContext("2d");
  const H = Math.ceil(passata(misura, false));
  canvas.width = W; canvas.height = H; // azzera il contesto
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = "#000"; ctx.strokeStyle = "#000"; ctx.textBaseline = "alphabetic";
  passata(ctx, true);
  return canvas;
}

// ── API per l'app ───────────────────────────────────────────────────────────
/** Stampante attiva per reparto + categoria, dalla configurazione esistente. */
export async function stampantePer(categoria, reparto = "") {
  const { data } = await axios.get(`${API}/stampanti/per-categoria`, { params: { categoria, reparto } });
  return data && data.stampante ? data.stampante : null;
}

async function stampaCanvas(host, canvas) {
  const ctx = canvas.getContext("2d");
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const bytes = rasterizza(data, canvas.width, canvas.height);
  await inviaXml(host, costruisciXml({ bytes, width: canvas.width, height: canvas.height }));
}

/** Stampa l'etichetta di un lotto. Lancia con un messaggio gia' in italiano. */
export async function stampaEtichettaLotto(lottoId, reparto = "") {
  const { data } = await axios.get(`${API}/stampa/lotto/${encodeURIComponent(lottoId)}/dati`);
  const st = await stampantePer("etichette", reparto || data.reparto || "");
  if (!st || !st.indirizzo_rete) {
    throw new ErroreStampaDiretta("Nessuna stampante attiva con indirizzo IP per le etichette di questo reparto: configurala in Impostazioni → Stampanti.");
  }
  const host = st.indirizzo_rete.trim();
  try {
    await stampaCanvas(host, disegnaEtichetta(data));
  } catch (e) {
    throw new ErroreStampaDiretta(spiegaErrore(e, host));
  }
}

/** «Prova stampa»: una riga di test e il taglio. */
export async function provaStampa(host) {
  host = (host || "").trim();
  try {
    await inviaXml(host, costruisciXml({ testo: `Prova stampa Ceraldi - ${new Date().toLocaleString("it-IT", { timeZone: "Europe/Rome" })}` }));
  } catch (e) {
    throw new ErroreStampaDiretta(spiegaErrore(e, host));
  }
}
