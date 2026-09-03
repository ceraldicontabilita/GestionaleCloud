import { printHtml } from './printHtml';
/**
 * posPrint.js — Template stampa ottimizzato per QIAN QTP-BTWF-01
 * Stampante termica POS 80mm (area stampa 72mm) · 203 DPI · ESC/POS
 * Usa solo bianco/nero: NO sfondi colorati, NO gradienti.
 */

const POS_CSS = `
  @page {
    size: 80mm auto;
    margin: 0;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 8pt;
    font-weight: 700;
    line-height: 1.25;
    width: 72mm;
    padding: 1.5mm 2mm 4mm 2mm;
    color: #000;
    background: #fff;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  /* ── Struttura ── */
  .azienda {
    text-align: center;
    font-size: 6pt;
    font-weight: 500;
    color: #666;
    margin-bottom: 0.5mm;
  }
  .titolo-sezione {
    text-align: center;
    font-size: 10pt;
    font-weight: 900;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 0.5mm;
  }
  .prodotto-nome {
    text-align: center;
    font-size: 9pt;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    word-break: break-word;
    margin-bottom: 0.5mm;
  }
  .lotto-box {
    border: 2px solid #000;
    text-align: center;
    padding: 1mm 1.5mm;
    font-size: 8pt;
    font-weight: 900;
    font-family: 'Courier New', monospace;
    letter-spacing: 0.5px;
    margin: 1mm 0;
    word-break: break-all;
  }
  .qty-box {
    text-align: center;
    font-size: 9pt;
    font-weight: 900;
    margin-bottom: 0.5mm;
    color: #000;
  }

  /* ── Righe info ── */
  .row {
    display: flex;
    justify-content: space-between;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 0.5mm 0;
    border-bottom: 1px solid #aaa;
    color: #000;
    gap: 3mm;
  }
  .row .label { font-weight: 900; white-space: nowrap; }
  .row .val   { font-weight: 900; text-align: right; color: #000; }
  .row.scad .val { text-decoration: underline; }
  .row.frigo .val { border: 1px solid #000; padding: 0.2mm 0.8mm; font-size: 7pt; }

  /* ── Separatori ── */
  .sep-solid { border-top: 2px solid #000; margin: 1mm 0; }
  .sep-dash  { border-top: 1px dashed #000; margin: 1mm 0; }

  /* ── Ingredienti ── */
  .ing-title { font-size: 7pt; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.8mm; }
  .ing {
    font-size: 6.5pt;
    font-weight: 700;
    padding: 0.4mm 0;
    border-bottom: 1px dotted #666;
    word-break: break-word;
    color: #000;
  }
  .ing.allergene { font-weight: 900; }
  .ing.allergene::before { content: "! "; font-weight: 900; }

  /* ── Allergeni ── */
  .allergeni-box {
    border: 2px solid #000;
    padding: 1.5mm;
    margin-top: 1mm;
    background: #fff;
  }
  .allergeni-title {
    font-size: 7pt;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    text-align: center;
    border-bottom: 1px solid #000;
    padding-bottom: 1mm;
    margin-bottom: 1mm;
    color: #000;
  }
  .allergeni-list {
    font-size: 7.5pt;
    font-weight: 900;
    word-break: break-word;
    text-align: center;
    color: #000;
    line-height: 1.4;
  }
  .no-allergeni {
    font-size: 7pt;
    font-weight: 700;
    text-align: center;
    margin-top: 1mm;
    color: #000;
  }

  /* ── Tracciabilità Fornitori ── */
  .trac-title {
    font-size: 7pt;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.8mm;
    margin-top: 1mm;
  }
  .trac-row {
    font-size: 6pt;
    font-weight: 700;
    padding: 0.8mm 0;
    border-bottom: 1px dotted #888;
    line-height: 1.3;
  }
  .trac-row .trac-lotto {
    font-family: 'Courier New', monospace;
    font-weight: 900;
    font-size: 6.5pt;
  }
  .trac-row .trac-fornitore {
    font-weight: 700;
    color: #333;
  }
  .trac-row .trac-scad {
    font-weight: 900;
    text-decoration: underline;
  }
  .trac-non-trovati {
    font-size: 5.5pt;
    color: #888;
    font-style: italic;
    margin-top: 0.5mm;
  }

  /* ── Footer ── */
  .footer {
    margin-top: 1.5mm;
    border-top: 1px solid #000;
    padding-top: 1mm;
    font-size: 6pt;
    font-weight: 600;
    text-align: center;
    line-height: 1.4;
  }

  /* ── Footer ── */
  .footer {
    border: 1.5px solid #000;
    padding: 1.5mm;
    margin-top: 1.5mm;
    font-size: 7.5pt;
    font-weight: 900;
    text-align: center;
    word-break: break-word;
    line-height: 1.4;
  }
`;

/**
 * Genera HTML completo per stampa POS 80mm del lotto.
 * @param {object} lotto
 * @param {string[]} allergeniPresenti  — array di allergeni rilevati
 * @param {string[]} ingredientiOrdinati — ingredienti con allergeni prima
 * @returns {string} HTML completo
 */
export function buildPosHtml(lotto, allergeniPresenti = [], ingredientiOrdinati = []) {
  const dataOra = new Date().toLocaleString("it-IT", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit"
  });

  const righeIngredienti = ingredientiOrdinati.length > 0
    ? ingredientiOrdinati.map(ing => {
        const isA = ing.toLowerCase().includes("contiene") && !ing.toLowerCase().includes("non contiene");
        return `<div class="ing${isA ? " allergene" : ""}">• ${ing}</div>`;
      }).join("")
    : '<div class="ing">Dati non disponibili</div>';

  const sezioneAllergeni = allergeniPresenti.length > 0
    ? `<div class="allergeni-box">
        <div class="allergeni-title">!!! ALLERGENI (Reg. UE 1169/2011) !!!</div>
        <div class="allergeni-list">${allergeniPresenti.join(" · ")}</div>
       </div>`
    : `<div class="no-allergeni">✓ Non contiene allergeni dichiarati</div>`;

  // Sezione tracciabilità fornitori (lotti_fornitori.lotti_scalati)
  const lottiScalati = lotto.lotti_fornitori?.lotti_scalati || [];
  const ingredientiNonTrovati = lotto.lotti_fornitori?.ingredienti_non_trovati || [];
  const fonteDizionario = lotto.lotti_fornitori?.fonte === "dizionario_prodotti";

  // Costruisce righe tracciabilità — con lotti_scalati OPPURE da ingredienti_dettaglio
  let sezioneTracciabilita = "";

  if (lottiScalati.length > 0) {
    // Caso normale: scalati da lotti fornitori
    const righeScalati = lottiScalati.map(ls => {
      const isFattura = (ls.lotto_id_fornitore || "").startsWith("FAT-");
      const isDiz = ls.da_dizionario === true;
      const numFattura = isFattura ? ls.lotto_id_fornitore.replace("FAT-", "") : ls.lotto_id_fornitore;
      return `
      <div class="trac-row">
        ${isDiz
          ? `<span class="trac-lotto" style="background:#f2f6f3;color:#3f5a4e;">MAG: ${numFattura || "N/D"}</span>`
          : isFattura
            ? `<span class="trac-lotto" style="background:var(--warning-soft);color:var(--warning-text);">FAT: ${numFattura || "N/D"}</span>`
            : `<span class="trac-lotto">LOT: ${numFattura || "N/D"}</span>`
        }
        ${ls.data_scadenza ? `<span class="trac-scad"> | Scad: ${ls.data_scadenza}</span>` : ""}
        ${isFattura && ls.data_fattura ? `<span style="font-size:6pt;color:var(--warning-text);"> | Data Fattura: ${ls.data_fattura}</span>` : ""}
        <br/><span class="trac-fornitore">${ls.fornitore || "—"}</span>
        <br/><span>${ls.prodotto || ls.ingrediente || "—"}</span>
        <br/><span style="font-size:5.5pt;font-weight:bold;">
          ${ls.quantita_consumata != null ? `Qtà usata: ${ls.quantita_consumata} ${ls.unita || ""} · ` : ""}
          Rimasto in magazzino: ${ls.quantita_rimasta !== undefined ? ls.quantita_rimasta : "—"} ${ls.unita || ""}
          ${ls.esaurito ? " · ⚠ ESAURITO" : ""}
        </span>
      </div>`;
    }).join("");

    sezioneTracciabilita = `<div class="sep-dash"></div>
       <div class="trac-title">Tracciabilità Fornitori (Controllo a Ritroso · Reg. CE 178/2002)</div>
       ${righeScalati}
       ${ingredientiNonTrovati.length > 0
         ? `<div class="trac-non-trovati">Non tracciati: ${ingredientiNonTrovati.join(", ")}</div>`
         : fonteDizionario ? "" : ""
       }`;

  } else if ((lotto.ingredienti_dettaglio || []).length > 0) {
    // Fallback: mostra ingredienti_dettaglio con nota "rimanenza non disponibile"
    const righeIng = (lotto.ingredienti_dettaglio || []).map(ing => {
      const nomeIng = typeof ing === "string" ? ing : (ing.nome || "?");
      return `
      <div class="trac-row">
        <span class="trac-lotto" style="background:#f3f4f6;color:#374151;">ING</span>
        <br/><span>${nomeIng}</span>
        <br/><span style="font-size:5.5pt;color:#6b7280;">Rimanenza magazzino: verificare manualmente</span>
      </div>`;
    }).join("");

    sezioneTracciabilita = `<div class="sep-dash"></div>
       <div class="trac-title">Ingredienti (Tracciabilità in elaborazione — Reg. CE 178/2002)</div>
       ${righeIng}`;
  }

  return `<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8"/>
  <title>Lotto ${lotto.numero_lotto || ""}</title>
  <style>${POS_CSS}</style>
</head>
<body>
  <div class="azienda">Ceraldi Group S.R.L.</div>

  <div class="titolo-sezione">LOTTO</div>
  <div class="prodotto-nome">${lotto.prodotto || lotto.prodotto_nome || ""}</div>
  <div class="lotto-box">${lotto.numero_lotto || "N/D"}</div>

  ${(lotto.pezzi || lotto.quantita)
    ? `<div class="qty-box">QTA: ${lotto.pezzi || lotto.quantita} ${lotto.unita || lotto.unita_misura || "pz"}</div>`
    : ""}

  <div class="sep-solid"></div>
  <div class="row"><span class="label">PRODOTTO:</span><span class="val">${lotto.data_produzione || "—"}</span></div>
  <div class="row scad"><span class="label">SCADENZA:</span><span class="val">${lotto.data_scadenza || "—"}</span></div>
  ${lotto.scadenza_abbattuto
    ? `<div class="row"><span class="label">SCAD -18°C:</span><span class="val">${lotto.scadenza_abbattuto}</span></div>`
    : ""}
  ${lotto.frigo_numero
    ? `<div class="row frigo"><span class="label">FRIGO:</span><span class="val">${lotto.frigo_numero}</span></div>`
    : ""}

  ${ingredientiOrdinati.length > 0
    ? `<div class="sep-dash"></div>
       <div class="ing-title">INGREDIENTI + TRACCIABILITA:</div>
       ${righeIngredienti}`
    : ""}

  ${sezioneTracciabilita}

  ${sezioneAllergeni}

  <div class="etichetta-finale">
    ${(lotto.prodotto || lotto.prodotto_nome || "").toUpperCase()} · ${lotto.data_produzione || ""}
    ${allergeniPresenti.length > 0
      ? `<br/>CONTIENE: ${allergeniPresenti.join(", ")}`
      : ""}
  </div>

  <div class="footer">
    Stampato: ${dataOra}<br/>
    Reg. CE 178/2002 — Ceraldi Group S.R.L.
  </div>
</body>
</html>`;
}

/**
 * Apre finestra di stampa POS.
 * @param {object} lotto
 * @param {string[]} allergeniPresenti
 * @param {string[]} ingredientiOrdinati
 */
export function stampaPOS(lotto, allergeniPresenti = [], ingredientiOrdinati = []) {
  const html = buildPosHtml(lotto, allergeniPresenti, ingredientiOrdinati);
  printHtml(html, { size: "width=320,height=600" });
}
