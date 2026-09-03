/**
 * CorrispettiviView.jsx
 * Sezione dedicata Corrispettivi: andamento incassi giornaliero + confronto con
 * lo stesso periodo dell'anno precedente. Stessa logica delle fatture: legge la
 * collection corrispettivi di Lotti (il backend rileva il campo importo reale).
 */
import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const eur = (v) => (v == null ? "—" : `€ ${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

function DeltaBadge({ pct }) {
  if (pct == null) return <span style={{ fontSize: 12, color: "#94a3b8" }}>n/d anno prec.</span>;
  const up = pct >= 0;
  return (
    <span style={{ fontSize: 12, fontWeight: 800, color: up ? "#00B884" : "#F44336" }}>
      {up ? "▲" : "▼"} {Math.abs(pct)}% <span style={{ color: "#94a3b8", fontWeight: 600 }}>vs anno prec.</span>
    </span>
  );
}

function CardKpi({ titolo, dato }) {
  return (
    <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #ece7f6", padding: "16px 18px" }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#64748B", textTransform: "uppercase", letterSpacing: 0.5 }}>{titolo}</div>
      <div style={{ fontSize: 26, fontWeight: 900, color: "#2a3329", margin: "4px 0 6px" }}>{eur(dato?.valore)}</div>
      <DeltaBadge pct={dato?.delta_pct} />
      <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>anno prec.: {eur(dato?.anno_precedente)}</div>
    </div>
  );
}

export default function CorrispettiviView() {
  const [riepilogo, setRiepilogo] = useState(null);
  const [andamento, setAndamento] = useState(null);
  const [correlazione, setCorrelazione] = useState(null);
  const [festivita, setFestivita] = useState(null);
  const [previsione, setPrevisione] = useState(null);
  const [gran, setGran] = useState("giorno");
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState("");
  const [importMsg, setImportMsg] = useState("");
  const [importing, setImporting] = useState(false);

  const carica = useCallback(async () => {
    setLoading(true); setErrore("");
    // AUDIT 25/07/2026: prima era Promise.all — bastava che UNO dei cinque
    // riquadri non avesse dati (es. la previsione, che vuole abbastanza
    // storico) e la pagina restava completamente vuota, con un solo messaggio
    // rosso. Ora ogni riquadro va per conto suo: si vede quello che c'è.
    const [r, a, co, fe, pr] = await Promise.allSettled([
      axios.get(`${API}/corrispettivi/riepilogo`),
      axios.get(`${API}/corrispettivi/andamento`, { params: { granularita: gran } }),
      axios.get(`${API}/corrispettivi/correlazione-ordini`),
      axios.get(`${API}/corrispettivi/festivita-imminenti`, { params: { giorni: 21 } }),
      axios.get(`${API}/corrispettivi/previsione`),
    ]);
    const dato = (x) => (x.status === "fulfilled" ? x.value.data : null);
    setRiepilogo(dato(r));
    setAndamento(dato(a));
    setCorrelazione(dato(co));
    setFestivita(dato(fe));
    setPrevisione(dato(pr));
    // Il messaggio compare SOLO se non è arrivato proprio niente.
    if ([r, a, co, fe, pr].every((x) => x.status === "rejected")) {
      const motivo = r.reason?.response?.data?.detail;
      setErrore(motivo || "Nessun corrispettivo ancora importato: carica i file XML qui sopra.");
    }
    setLoading(false);
  }, [gran]);

  useEffect(() => { carica(); }, [carica]);

  const importaXml = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setImporting(true); setImportMsg("");
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const r = await axios.post(`${API}/corrispettivi/importa-xml`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setImportMsg(`Importati ${r.data.importati}/${r.data.totale_file} corrispettivi`);
      await carica();
    } catch (err) {
      setImportMsg(err?.response?.data?.detail || "Errore import XML");
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  };

  const maxInc = andamento?.serie?.reduce((m, p) => Math.max(m, p.incasso), 0) || 1;

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: "8px 4px 40px" }}>
      <h2 style={{ fontSize: 22, fontWeight: 900, color: "#2a3329", margin: "4px 0 2px" }}>Corrispettivi</h2>
      <p style={{ fontSize: 13, color: "#64748B", margin: "0 0 12px" }}>
        Andamento incassi giornaliero, con confronto sullo stesso periodo dell'anno precedente.
      </p>

      {/* Import XML corrispettivi telematici (COR10) */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18, flexWrap: "wrap" }}>
        <label style={{
          display: "inline-flex", alignItems: "center", gap: 8, cursor: "pointer",
          background: "#5b7a6b", color: "#fff", fontWeight: 800, fontSize: 13,
          padding: "9px 16px", borderRadius: 10, opacity: importing ? 0.6 : 1,
        }}>
          {importing ? "Importo…" : "Importa XML corrispettivi"}
          <input type="file" accept=".xml" multiple onChange={importaXml} disabled={importing} style={{ display: "none" }} />
        </label>
        {importMsg && <span style={{ fontSize: 13, color: "#00B884", fontWeight: 700 }}>{importMsg}</span>}
      </div>

      {loading ? (
        <div style={{ textAlign: "center", color: "#94a3b8", padding: 40 }}>Caricamento…</div>
      ) : errore ? (
        <div style={{ background: "#fff5f5", border: "1px solid #fed7d7", borderRadius: 12, padding: 16, color: "#c53030", fontSize: 14 }}>
          {errore}
        </div>
      ) : (
        <>
          {/* KPI */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12, marginBottom: 22 }}>
            <CardKpi titolo="Oggi" dato={riepilogo?.oggi} />
            <CardKpi titolo="Settimana" dato={riepilogo?.settimana} />
            <CardKpi titolo="Mese" dato={riepilogo?.mese} />
            <CardKpi titolo="Anno" dato={riepilogo?.anno} />
          </div>

          {/* Correlazione incassi ↔ ordini */}
          {correlazione && (
            <div style={{
              background: "#fff", borderRadius: 16, padding: "16px 18px", marginBottom: 22,
              border: `1px solid ${correlazione.giustificato === false ? "#fecaca" : correlazione.giustificato === true ? "#bbf7d0" : "#ece7f6"}`,
            }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#2a3329", marginBottom: 10 }}>
                Ordini giustificati dall'incasso?
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10, marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 11, color: "#64748B", fontWeight: 700, textTransform: "uppercase" }}>Incasso periodo</div>
                  <div style={{ fontSize: 19, fontWeight: 900, color: "#00B884" }}>{eur(correlazione.periodo?.incasso)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: "#64748B", fontWeight: 700, textTransform: "uppercase" }}>Spesa ordini</div>
                  <div style={{ fontSize: 19, fontWeight: 900, color: "#5b7a6b" }}>{eur(correlazione.periodo?.spesa_ordini)}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>{correlazione.periodo?.n_ordini || 0} ordini</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: "#64748B", fontWeight: 700, textTransform: "uppercase" }}>Incidenza</div>
                  <div style={{ fontSize: 19, fontWeight: 900, color: "#2a3329" }}>
                    {correlazione.periodo?.incidenza_pct != null ? `${correlazione.periodo.incidenza_pct}%` : "—"}
                  </div>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>
                    periodo prec.: {correlazione.periodo_precedente?.incidenza_pct != null ? `${correlazione.periodo_precedente.incidenza_pct}%` : "n/d"}
                  </div>
                </div>
              </div>
              <div style={{
                fontSize: 14, fontWeight: 700, padding: "10px 12px", borderRadius: 10,
                background: correlazione.giustificato === false ? "#fff5f5" : correlazione.giustificato === true ? "#f0fdf4" : "#f8fafc",
                color: correlazione.giustificato === false ? "#c53030" : correlazione.giustificato === true ? "#15803d" : "#64748B",
              }}>
                {correlazione.giustificato === false ? "⚠️ " : correlazione.giustificato === true ? "✓ " : "ℹ️ "}
                {correlazione.messaggio}
              </div>
            </div>
          )}

          {/* Festività in arrivo (anticipa ordini) */}
          {festivita?.festivita?.length > 0 && (
            <div style={{ background: "#fff", borderRadius: 16, padding: "16px 18px", marginBottom: 22, border: "1px solid #fde68a" }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#2a3329", marginBottom: 10 }}>
                🗓️ Festività in arrivo — anticipa gli ordini
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {festivita.festivita.map((f) => (
                  <div key={f.data} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "10px 12px", background: "#fffbeb", borderRadius: 10 }}>
                    <div style={{ textAlign: "center", minWidth: 54 }}>
                      <div style={{ fontSize: 20, fontWeight: 900, color: "#b45309" }}>{f.giorni_mancanti}gg</div>
                      <div style={{ fontSize: 10, color: "#92400e" }}>{f.giorno_settimana}</div>
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 800, color: "#2a3329" }}>
                        {f.nome} — {f.data.split("-").reverse().join("/")}
                        {f.ponte && <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 700, color: "#b45309", background: "#fef3c7", borderRadius: 5, padding: "2px 6px" }}>PONTE ({f.ponte.tipo})</span>}
                      </div>
                      <div style={{ fontSize: 12, color: "#78716c", marginTop: 2 }}>{f.suggerimento}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Previsione (apprendimento storico) */}
          {previsione && previsione.crescita_media_annua_pct != null && (
            <div style={{ background: "#fff", borderRadius: 16, padding: "16px 18px", marginBottom: 22, border: "1px solid #ece7f6" }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#2a3329", marginBottom: 4 }}>
                📈 Previsione mese {String(previsione.mese).padStart(2, "0")}/{previsione.anno_target}
              </div>
              <div style={{ display: "flex", gap: 18, flexWrap: "wrap", margin: "8px 0" }}>
                <div>
                  <div style={{ fontSize: 11, color: "#64748B", fontWeight: 700, textTransform: "uppercase" }}>Crescita media/anno</div>
                  <div style={{ fontSize: 19, fontWeight: 900, color: previsione.crescita_media_annua_pct >= 0 ? "#00B884" : "#F44336" }}>
                    {previsione.crescita_media_annua_pct >= 0 ? "+" : ""}{previsione.crescita_media_annua_pct}%
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: "#64748B", fontWeight: 700, textTransform: "uppercase" }}>Incasso atteso</div>
                  <div style={{ fontSize: 19, fontWeight: 900, color: "#5b7a6b" }}>{eur(previsione.incasso_atteso)}</div>
                </div>
              </div>
              <div style={{ fontSize: 13, color: "#475569", background: "#f8fafc", borderRadius: 10, padding: "10px 12px" }}>
                {previsione.suggerimento}
              </div>
            </div>
          )}

          {/* Andamento */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
            <div style={{ fontSize: 16, fontWeight: 800, color: "#2a3329" }}>
              Andamento ({andamento?.da} → {andamento?.a})
              {andamento?.delta_pct != null && (
                <span style={{ marginLeft: 10, fontSize: 13 }}><DeltaBadge pct={andamento.delta_pct} /></span>
              )}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              {["giorno", "settimana", "mese"].map((g) => (
                <button key={g} onClick={() => setGran(g)} style={{
                  padding: "6px 14px", borderRadius: 20, fontSize: 13, fontWeight: 700, cursor: "pointer",
                  border: gran === g ? "none" : "1px solid #ddd6ec",
                  background: gran === g ? "#5b7a6b" : "#fff", color: gran === g ? "#fff" : "#5b7a6b",
                }}>{g}</button>
              ))}
            </div>
          </div>

          <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #ece7f6", padding: 16 }}>
            {(!andamento?.serie || andamento.serie.length === 0) ? (
              <div style={{ textAlign: "center", color: "#94a3b8", padding: 24 }}>Nessun dato nel periodo</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {andamento.serie.map((p) => (
                  <div key={p.periodo} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 92, fontSize: 12, color: "#64748B", flexShrink: 0 }}>{p.periodo}</div>
                    <div style={{ flex: 1, background: "#f1edfb", borderRadius: 6, height: 18, overflow: "hidden" }}>
                      <div style={{ width: `${Math.max(2, (p.incasso / maxInc) * 100)}%`, height: "100%", background: "#5b7a6b" }} />
                    </div>
                    <div style={{ width: 96, textAlign: "right", fontSize: 13, fontWeight: 800, color: "#2a3329", flexShrink: 0 }}>{eur(p.incasso)}</div>
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid #f0ecf9", display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span style={{ color: "#64748B" }}>Totale periodo</span>
              <strong style={{ color: "#2a3329" }}>{eur(andamento?.totale)}</strong>
            </div>
            {andamento?.anno_precedente && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#94a3b8", marginTop: 4 }}>
                <span>Stesso periodo anno prec.</span>
                <span>{eur(andamento.anno_precedente.totale)}</span>
              </div>
            )}
          </div>

          {andamento?.campo_importo && (
            <p style={{ fontSize: 11, color: "#cbd5e1", marginTop: 10 }}>
              Importo letto dal campo "{andamento.campo_importo}" della collection corrispettivi.
            </p>
          )}
        </>
      )}
    </div>
  );
}
