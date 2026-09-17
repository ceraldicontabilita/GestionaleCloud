import React, { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { CheckCircle2, Download, Plus, RefreshCw } from "lucide-react";
import { filtraPaghe } from "./pagheView.js";

const API = "/hr/api/dipendenti-cloud";
const FILTER_KEY = "hr-paghe-filtri";
function leggiFiltri() {
  try {
    const value = JSON.parse(sessionStorage.getItem(FILTER_KEY) || "{}");
    return {
      anno: Number.isInteger(value.anno) && value.anno >= 1900 && value.anno <= 2200 ? value.anno : null,
      mese: Number.isInteger(value.mese) && value.mese >= 0 && value.mese <= 12 ? value.mese : 0,
      stato: ["", "pagato", "parziale", "da_pagare", "bonifico_senza_busta"].includes(value.stato) ? value.stato : "",
    };
  } catch { return {}; }
}

export default function PagheBonificiPage({ notify: toast, Badge }) {
  const mesi = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
  const annoCorr = new Date().getFullYear();
  const [anno, setAnno] = useState(() => leggiFiltri().anno || annoCorr);
  const [mese, setMese] = useState(() => leggiFiltri().mese || 0);
  const [filtroStato, setFiltroStato] = useState(() => leggiFiltri().stato || "");
  const [archivio, setArchivio] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errore, setErrore] = useState("");
  const [aperta, setAperta] = useState(null);
  const [busy, setBusy] = useState(null);
  const [exportBusy, setExportBusy] = useState(false);
  const richiesta = useRef(null);
  const data = useMemo(() => filtraPaghe(archivio || [], anno, mese, filtroStato),
    [archivio, anno, mese, filtroStato]);

  const eur = (n) => (Number(n) || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const keyOf = (r) => `${r.dipendente_id}_${r.anno}_${r.mese}`;

  const load = useCallback(async () => {
    richiesta.current?.abort();
    const controller = new AbortController();
    richiesta.current = controller;
    setLoading(true);
    setErrore("");
    try {
      // Un'unica lettura del registro persistente, senza import o sincronizzazioni.
      // Anno, mese e stato filtrano la stessa risposta già caricata in memoria.
      const r = await axios.get(`${API}/paghe/associazioni-bonifici`, { signal: controller.signal });
      if (!Array.isArray(r.data?.righe)) throw new Error("Risposta paghe non valida");
      if (!controller.signal.aborted) setArchivio(r.data.righe);
    } catch (e) {
      if (!controller.signal.aborted) setErrore("Impossibile aggiornare i cedolini. I dati già caricati restano consultabili.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    load();
    return () => richiesta.current?.abort();
  }, [load]);
  useEffect(() => {
    try { sessionStorage.setItem(FILTER_KEY, JSON.stringify({ anno, mese, stato: filtroStato })); } catch {}
    setAperta(null);
  }, [anno, mese, filtroStato]);

  const conferma = async (r, val) => {
    setBusy(keyOf(r));
    try {
      await axios.post(`${API}/paghe/conferma-associazione`, {
        dipendente_id: r.dipendente_id, anno: r.anno, mese: r.mese, riconciliato: val,
      });
      await load();
    } catch (e) { toast(e?.response?.data?.detail || "Errore conferma", "err"); }
    finally { setBusy(null); }
  };

  const esportaExcel = async () => {
    setExportBusy(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.set("anno", anno);
      if (mese) params.set("mese", mese);
      if (filtroStato) params.set("stato", filtroStato);
      const r = await axios.get(`${API}/paghe/associazioni-bonifici/export-excel?${params.toString()}`, { responseType: "blob" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(r.data);
      a.download = `cedolini_bonifici${anno ? `_${anno}` : ""}${mese ? `_${String(mese).padStart(2, '0')}` : ""}.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    } catch (e) { toast("Errore generazione Excel", "err"); }
    finally { setExportBusy(false); }
  };

  const t = data.totali || {};
  const STATI = {
    pagato: { label: "✓ Pagato", variant: "success" },
    parziale: { label: "Parziale", variant: "warning" },
    da_pagare: { label: "Da pagare", variant: "danger" },
    bonifico_senza_busta: { label: "Bonifico senza busta", variant: "info" },
  };
  const QUALITA = {
    esatto: { txt: "Match esatto", col: "#234d3d", bg: "#e2efe8", bd: "#c2ddd0" },
    per_importo: { txt: "Match per importo", col: "#234d3d", bg: "#e2efe8", bd: "#c2ddd0" },
    aggregato: { txt: "Più bonifici", col: "#56442d", bg: "#f3ead9", bd: "#e7d6b9" },
    da_verificare: { txt: "Da verificare", col: "#7a3b32", bg: "#f6e4e1", bd: "#e8c5bf" },
  };
  const FONTI = { banca: "Estratto/CSV banca", prima_nota: "Prima nota", manuale: "Inserito a mano" };

  const cardWrap = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 18 };
  const card = { background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 12, padding: "12px 14px" };
  const lbl = { fontSize: 11, color: "#7a8576", textTransform: "uppercase", letterSpacing: 0.4, fontWeight: 700 };
  const val = { fontSize: 20, fontWeight: 800, color: "#2a3329", marginTop: 4 };
  const sel = { border: "1px solid #e6e0d4", borderRadius: 8, padding: "7px 10px", fontSize: 14, background: "#fffefb", color: "#2a3329", width: "auto", flex: "1 1 160px", minHeight: 44 };
  const th = { textAlign: "left", padding: "10px 12px", fontSize: 11, color: "#7a8576", textTransform: "uppercase", letterSpacing: 0.4, fontWeight: 700, borderBottom: "2px solid #e6e0d4", whiteSpace: "nowrap" };
  const td = { padding: "10px 12px", fontSize: 14, color: "#2a3329", borderBottom: "1px solid #efe9dd", verticalAlign: "top" };

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, color: "#2a3329" }}>Cedolini &amp; Bonifici</h2>
          <p className="dc-muted" style={{ marginTop: 4 }}>
            Per ogni busta vedi se il <b>bonifico è stato effettuato</b> e a quale cedolino è associato.
            Consulta il registro già acquisito: cambiare periodo filtra i dati senza reimportarli.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <a href="/documenti/import" className="dc-btn">
            <Plus size={16} /> Carica documenti
          </a>
          <button className="dc-btn" disabled={exportBusy} onClick={esportaExcel}>
            <Download size={16} /> {exportBusy ? "Esporto…" : "Esporta Excel"}
          </button>
        </div>
      </div>

      {/* Filtri */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 16 }}>
        <select aria-label="Anno cedolini" style={sel} value={anno} onChange={e => setAnno(Number(e.target.value))}>
          {[...new Set([annoCorr, anno, ...(archivio || []).map(r => Number(r.anno)).filter(Boolean)])].sort((a, b) => b - a).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select aria-label="Mese cedolini" style={sel} value={mese} onChange={e => setMese(Number(e.target.value))}>
          <option value={0}>Tutto l'anno</option>
          {mesi.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
        </select>
        <select aria-label="Stato cedolini" style={sel} value={filtroStato} onChange={e => setFiltroStato(e.target.value)}>
          <option value="">Tutti gli stati</option>
          <option value="pagato">Pagati</option>
          <option value="parziale">Parziali</option>
          <option value="da_pagare">Da pagare</option>
          <option value="bonifico_senza_busta">Bonifico senza busta</option>
        </select>
        <button className="dc-btn" onClick={load} disabled={loading} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <RefreshCw size={15} /> Aggiorna
        </button>
      </div>

      {errore && <p role="alert" style={{ color: "#b04a3a" }}>{errore}</p>}
      {loading && <p role="status">{archivio ? "Aggiornamento archivio…" : "Caricamento archivio cedolini…"}</p>}
      {/* Riepilogo */}
      {archivio && <div style={cardWrap}>
        <div style={card}><div style={lbl}>Totale buste</div><div style={val}>€ {eur(t.buste)}</div></div>
        <div style={card}><div style={lbl}>Bonifici</div><div style={{ ...val, color: "#3d8168" }}>€ {eur(t.bonifici)}</div></div>
        <div style={card}><div style={lbl}>Saldo da pagare</div><div style={{ ...val, color: (t.saldo > 0.5 ? "#b04a3a" : "#3d8168") }}>€ {eur(t.saldo)}</div></div>
        <div style={card}><div style={lbl}>Pagati</div><div style={{ ...val, color: "#3d8168" }}>{t.pagati || 0}</div></div>
        <div style={card}><div style={lbl}>Da pagare</div><div style={{ ...val, color: "#b04a3a" }}>{t.da_pagare || 0}</div></div>
        <div style={card}><div style={lbl}>Da verificare</div><div style={{ ...val, color: "#7a3b32" }}>{t.da_verificare || 0}</div></div>
      </div>}

      {/* Tabella */}
      <div style={{ background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>Dipendente</th>
                <th style={th}>Periodo</th>
                <th style={{ ...th, textAlign: "right" }}>Busta</th>
                <th style={{ ...th, textAlign: "right" }}>Bonifico</th>
                <th style={{ ...th, textAlign: "right" }}>Saldo</th>
                <th style={th}>Stato</th>
                <th style={th}>Associazione</th>
                <th style={th}>Cedolino</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {loading && !archivio && <tr><td style={td} colSpan={9}>Caricamento…</td></tr>}
              {!loading && !errore && data.righe.length === 0 && <tr><td style={td} colSpan={9}>Nessuna busta per il periodo selezionato.</td></tr>}
              {data.righe.map(r => {
                const k = keyOf(r);
                const exp = aperta === k;
                const stInfo = STATI[r.stato] || { label: r.stato, variant: "default" };
                const qInfo = r.qualita ? QUALITA[r.qualita] : null;
                const periodoLbl = (r.mese >= 1 && r.mese <= 12) ? `${mesi[r.mese - 1]} ${r.anno}` : `${r.mese}/${r.anno}`;
                return (
                  <Fragment key={k}>
                    <tr style={{ background: exp ? "#f7f4ec" : "transparent" }}>
                      <td style={{ ...td, fontWeight: 600 }}>{r.dipendente}</td>
                      <td style={td}>{periodoLbl}</td>
                      <td style={{ ...td, textAlign: "right" }}>{r.busta > 0 ? `€ ${eur(r.busta)}` : "—"}</td>
                      <td style={{ ...td, textAlign: "right", color: r.bonifico > 0 ? "#3d8168" : "#9aa295", fontWeight: 600 }}>
                        {r.bonifico > 0 ? `€ ${eur(r.bonifico)}` : "—"}
                        {r.fonte && <div style={{ fontSize: 10, color: "#9aa295", fontWeight: 400 }}>{FONTI[r.fonte] || r.fonte}</div>}
                      </td>
                      <td style={{ ...td, textAlign: "right", color: r.saldo > 0.5 ? "#b04a3a" : "#3d8168" }}>
                        {Math.abs(r.saldo) > 0.5 ? `€ ${eur(r.saldo)}` : "✓"}
                      </td>
                      <td style={td}><Badge variant={stInfo.variant}>{stInfo.label}</Badge></td>
                      <td style={td}>
                        {r.riconciliato
                          ? <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "#234d3d", fontWeight: 700, fontSize: 12 }}><CheckCircle2 size={14} /> Confermata</span>
                          : qInfo
                            ? <span style={{ background: qInfo.bg, color: qInfo.col, border: `1px solid ${qInfo.bd}`, borderRadius: 6, padding: "2px 7px", fontSize: 11, fontWeight: 700 }}>{qInfo.txt}</span>
                            : <span style={{ color: "#9aa295", fontSize: 12 }}>—</span>}
                      </td>
                      <td style={td}>
                        {r.cedolino_pdf
                          ? <span style={{ color: "#234d3d", fontSize: 12, fontWeight: 600 }}>PDF ✓</span>
                          : <span style={{ color: "#9aa295", fontSize: 12 }}>no PDF</span>}
                      </td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}>
                        {(r.n_bonifici > 0) && (
                          <button className="dc-btn" onClick={() => setAperta(exp ? null : k)} style={{ fontSize: 12, padding: "4px 8px" }}>
                            {exp ? "Nascondi" : `Dettagli (${r.n_bonifici})`}
                          </button>
                        )}
                        {(r.bonifico > 0 || r.stato === "bonifico_senza_busta") && (
                          r.riconciliato
                            ? <button className="dc-btn" disabled={busy === k} onClick={() => conferma(r, false)} style={{ fontSize: 12, padding: "4px 8px", marginLeft: 6 }}>Annulla</button>
                            : <button className="dc-btn" disabled={busy === k} onClick={() => conferma(r, true)} style={{ fontSize: 12, padding: "4px 8px", marginLeft: 6 }}>Conferma</button>
                        )}
                      </td>
                    </tr>
                    {exp && r.bonifici.length > 0 && (
                      <tr>
                        <td style={{ ...td, background: "#f7f4ec" }} colSpan={9}>
                          <div style={{ fontSize: 11, color: "#7a8576", fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Bonifici realmente pagati</div>
                          <table style={{ width: "100%", borderCollapse: "collapse" }}>
                            <thead>
                              <tr>
                                <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Data</th>
                                <th style={{ ...th, borderBottom: "1px solid #e6e0d4", textAlign: "right" }}>Importo</th>
                                <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Causale</th>
                                <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Beneficiario</th>
                                <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Riferimento</th>
                                <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>PDF</th>
                              </tr>
                            </thead>
                            <tbody>
                              {r.bonifici.map((b, i) => (
                                <tr key={i}>
                                  <td style={{ ...td, borderBottom: "none" }}>{b.data || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", textAlign: "right", color: "#3d8168", fontWeight: 600 }}>€ {eur(b.importo)}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 13 }}>{b.causale || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 13 }}>{b.beneficiario || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 12, color: "#7a8576" }}>{b.riferimento || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 12 }}>
                                    {b.pdf_key
                                      ? <a href={`${API}/paghe/pagamento-esito/${b.pdf_key}/pdf`} target="_blank" rel="noreferrer" style={{ color: "#3d8168", fontWeight: 600 }}>📄 Apri PDF</a>
                                      : <span style={{ color: "#9aa295" }}>no PDF</span>}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <p className="dc-muted" style={{ fontSize: 12, marginTop: 10 }}>
        <b>Un dato suggerisce, una prova conferma.</b> La corrispondenza di importo non prova il pagamento: verifica la fonte e il movimento bancario prima di confermare un collegamento.
      </p>
    </div>
  );
}
