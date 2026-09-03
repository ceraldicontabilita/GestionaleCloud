/**
 * VenditaBancoView — Tablet serale per registrare l'invenduto
 * Design: card con foto + pulsantoni touch, pensato per uso su tablet
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { format, subDays, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import { API, fotoSrc } from "../../utils/constants";

const GRADIENT_HEADER = "linear-gradient(135deg, #f97316 0%, #ea580c 100%)";

// ── Placeholder foto prodotto ─────────────────────────────────────────────────
function FotoProdotto({ url, nome, size = 80 }) {
  const [errore, setErrore] = useState(false);
  if (url && !errore) {
    return (
      <img
        src={fotoSrc(url)}
        alt={nome}
        onError={() => setErrore(true)}
        style={{
          width: size, height: size, objectFit: "cover",
          borderRadius: 12, flexShrink: 0,
          background: "#f1f5f9"
        }}
      />
    );
  }
  // Fallback: iniziale del nome
  const iniziale = (nome || "?")[0].toUpperCase();
  const hue = (nome || "").split("").reduce((h, c) => h + c.charCodeAt(0), 0) % 360;
  return (
    <div style={{
      width: size, height: size, borderRadius: 12, flexShrink: 0,
      background: `hsl(${hue},55%,88%)`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.42, fontWeight: 900, color: `hsl(${hue},50%,35%)`
    }}>
      {iniziale}
    </div>
  );
}

// ── Card singolo prodotto ─────────────────────────────────────────────────────
function CardProdotto({ item, onSalva, onRiapri }) {
  const totale = item.pezzi_prodotti || 0;  // difesa da null/undefined
  const [invenduto, setInvenduto] = useState(
    item.pezzi_invenduto != null ? item.pezzi_invenduto : totale
  );
  const [loading, setLoading] = useState(false);
  const salvato = item.stato === "chiuso";

  const pezziVenduti = Math.max(0, totale - invenduto);
  const pct = totale > 0 ? Math.round((pezziVenduti / totale) * 100) : 0;

  const dec = () => setInvenduto(v => Math.max(0, v - 1));
  const inc = () => setInvenduto(v => Math.min(totale, v + 1));

  const handleSalva = async () => {
    setLoading(true);
    try {
      await onSalva(item.id, invenduto);
    } finally {
      setLoading(false);
    }
  };

  const handleRiapri = async () => {
    setLoading(true);
    try {
      await onRiapri(item.id);
      setInvenduto(0);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      background: "#fff",
      border: `2px solid ${salvato ? "#86efac" : "#fed7aa"}`,
      borderRadius: 18,
      overflow: "hidden",
      boxShadow: "0 2px 12px rgba(0,0,0,0.07)",
      display: "flex",
      flexDirection: "column"
    }}>
      {/* Header: foto + nome + pezzi prodotti */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", borderBottom: "1px solid #f1f5f9" }}>
        <FotoProdotto url={item.foto_url} nome={item.prodotto_nome} size={64} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: 0, fontWeight: 800, fontSize: 15, textTransform: "capitalize", color: "#1e293b",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {item.prodotto_nome}
          </p>
          <p style={{ margin: "2px 0 0", fontSize: 12, color: "#64748b" }}>
            Mandato al banco: <strong>{item.pezzi_prodotti} pz</strong>
          </p>
          {item.creato_at && (
            <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>
              {(() => {
                try {
                  const d = parseISO(item.creato_at);
                  return format(d, "dd/MM/yyyy - HH:mm", { locale: it });
                } catch { return item.creato_at; }
              })()}
            </p>
          )}
          {item.invenduto_at && (
            <p style={{ margin: "1px 0 0", fontSize: 11, color: "var(--success)" }}>
              Chiuso: {(() => {
                try {
                  const d = parseISO(item.invenduto_at);
                  return format(d, "HH:mm", { locale: it });
                } catch { return ""; }
              })()}
            </p>
          )}
        </div>
        {salvato && (
          <span style={{ background: "var(--success)", color: "#fff", borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
            ✓ OK
          </span>
        )}
      </div>

      {/* Corpo: controllo invenduto */}
      <div style={{ padding: "12px 14px", flex: 1 }}>
        <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1 }}>
          Invenduto (pz rimasti)
        </p>

        {/* Controlli grandi touch */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <button onClick={dec} disabled={loading}
            style={{
              width: 52, height: 52, borderRadius: 12, border: "2px solid #e2e8f0",
              background: "#f8fafc", fontWeight: 900, fontSize: 26, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#374151", flexShrink: 0
            }}>−</button>

          <div style={{ flex: 1, textAlign: "center" }}>
            <input
              type="number"
              min="0"
              max={totale}
              value={invenduto}
              onChange={(e) => setInvenduto(Math.min(totale, Math.max(0, parseInt(e.target.value) || 0)))}
              style={{
                width: "100%", padding: "10px 0", fontSize: 30, fontWeight: 900,
                border: "2px solid #cbd5e1", borderRadius: 12, textAlign: "center",
                color: "#1e293b", outline: "none", background: "#fff"
              }}
            />
            <p style={{ margin: "3px 0 0", fontSize: 12, color: "#64748b" }}>
              = <strong style={{ color: "var(--success)" }}>{pezziVenduti} venduti</strong>
            </p>
          </div>

          <button onClick={inc} disabled={loading}
            style={{
              width: 52, height: 52, borderRadius: 12, border: "2px solid #e2e8f0",
              background: "#f8fafc", fontWeight: 900, fontSize: 26, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#374151", flexShrink: 0
            }}>+</button>
        </div>

        {/* Preset veloci: 0, 1, 2, 3, 5, 10... */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 10 }}>
          {[0, 1, 2, 3, 5, 10, 15, 20].filter(v => v <= totale).map(v => (
            <button key={v} onClick={() => setInvenduto(v)}
              style={{
                padding: "4px 11px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer",
                border: `2px solid ${invenduto === v ? "#f97316" : "#e2e8f0"}`,
                background: invenduto === v ? "#fff7ed" : "#f8fafc",
                color: invenduto === v ? "#ea580c" : "#64748b"
              }}>
              {v}
            </button>
          ))}
          {/* Preset "tutti invenduti" */}
          <button onClick={() => setInvenduto(totale)}
            style={{
              padding: "4px 11px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
              border: `2px solid ${invenduto === totale ? "var(--danger)" : "#e2e8f0"}`,
              background: invenduto === totale ? "#fef2f2" : "#f8fafc",
              color: invenduto === totale ? "var(--danger-dark)" : "#94a3b8"
            }}>
            Tutti ({totale})
          </button>
        </div>

        {/* Barra % venduto */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#64748b", marginBottom: 3 }}>
            <span>{pct}% venduto</span>
            <span style={{ color: pct >= 80 ? "var(--success)" : pct >= 50 ? "var(--warning-dark)" : "var(--danger)", fontWeight: 700 }}>
              {pct >= 80 ? "Ottimo" : pct >= 50 ? "Buono" : "Basso"}
            </span>
          </div>
          <div style={{ background: "#e2e8f0", borderRadius: 8, height: 8, overflow: "hidden" }}>
            <div style={{
              width: `${pct}%`, height: "100%", borderRadius: 8,
              background: pct >= 80 ? "var(--success)" : pct >= 50 ? "var(--warning)" : "var(--danger)",
              transition: "width 0.4s ease"
            }} />
          </div>
        </div>

        {/* Pulsanti azione */}
        {!salvato ? (
          <button onClick={handleSalva} disabled={loading}
            style={{
              width: "100%", padding: "13px 0", borderRadius: 12, border: "none",
              background: loading ? "#94a3b8" : GRADIENT_HEADER,
              color: "#fff", fontWeight: 800, fontSize: 15, cursor: loading ? "not-allowed" : "pointer",
              letterSpacing: 0.3
            }}>
            {loading ? "Salvataggio..." : `✓ Salva — ${invenduto} invenduti, ${pezziVenduti} venduti`}
          </button>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={handleSalva} disabled={loading}
              style={{
                flex: 2, padding: "11px 0", borderRadius: 12, border: "none",
                background: loading ? "#94a3b8" : "var(--success)",
                color: "#fff", fontWeight: 800, fontSize: 14, cursor: loading ? "not-allowed" : "pointer"
              }}>
              {loading ? "..." : `✓ Aggiorna`}
            </button>
            <button onClick={handleRiapri} disabled={loading}
              style={{
                flex: 1, padding: "11px 0", borderRadius: 12,
                border: "2px solid #e2e8f0", background: "#f8fafc",
                fontWeight: 600, fontSize: 13, cursor: "pointer", color: "#94a3b8"
              }}>
              Modifica
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sezione Sprechi ───────────────────────────────────────────────────────────
function SprechiView({ onBack }) {
  const [raggruppamento, setRaggruppamento] = useState("giorno");
  const [dataDa, setDataDa] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().split("T")[0];
  });
  const [dataA, setDataA] = useState(() => new Date().toISOString().split("T")[0]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [espanso, setEspanso] = useState(null); // indice periodo espanso

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/vendita-banco/report-sprechi`, {
        params: { raggruppamento, data_da: dataDa, data_a: dataA }
      });
      setReport(res.data);
    } catch { toast.error("Errore caricamento sprechi"); }
    finally { setLoading(false); }
  }, [raggruppamento, dataDa, dataA]);

  useEffect(() => { carica(); }, [carica]);

  const kpi = report?.kpi || {};
  const periodi = report?.periodi || [];

  const labelPeriodo = (p) => {
    if (raggruppamento === "anno") return p;
    if (raggruppamento === "mese") {
      const [y, m] = p.split("-");
      const mesi = ["","Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"];
      return `${mesi[parseInt(m)]} ${y}`;
    }
    try {
      const [y, m, d] = p.split("-");
      return `${d}/${m}/${y}`;
    } catch { return p; }
  };

  const colorePerc = (pct) => pct < 10 ? "var(--success)" : pct < 25 ? "var(--warning)" : "var(--danger)";

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc" }}>
      {/* Header */}
      <div style={{ background: "linear-gradient(135deg, #5b7a6b, #3f5a4e)", padding: "16px 18px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <button onClick={onBack} style={{
            background: "rgba(255,255,255,0.2)", border: "none", color: "#fff",
            borderRadius: 10, padding: "8px 14px", fontWeight: 700, cursor: "pointer"
          }}>← Banco</button>
          <div>
            <h1 style={{ color: "#fff", margin: 0, fontSize: 20, fontWeight: 800 }}>Sprechi & Invenduto</h1>
            <p style={{ color: "rgba(255,255,255,0.75)", margin: "2px 0 0", fontSize: 12 }}>
              Analisi pezzi buttati e costo materie prime
            </p>
          </div>
        </div>

        {/* Filtri */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {/* Raggruppamento */}
          {[{id:"giorno",l:"Giornaliero"},{id:"mese",l:"Mensile"},{id:"anno",l:"Annuale"}].map(r => (
            <button key={r.id} onClick={() => setRaggruppamento(r.id)} style={{
              padding: "6px 12px", borderRadius: 8, fontWeight: 700, fontSize: 12, cursor: "pointer",
              border: `2px solid rgba(255,255,255,${raggruppamento === r.id ? 0.9 : 0.3})`,
              background: raggruppamento === r.id ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.1)",
              color: raggruppamento === r.id ? "#5b7a6b" : "#fff"
            }}>{r.l}</button>
          ))}
          {/* Date */}
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="date" value={dataDa} onChange={e => setDataDa(e.target.value)}
              style={{ padding: "5px 8px", borderRadius: 8, border: "none", fontSize: 12, fontWeight: 600 }} />
            <span style={{ color: "rgba(255,255,255,0.7)", fontSize: 12 }}>→</span>
            <input type="date" value={dataA} onChange={e => setDataA(e.target.value)}
              style={{ padding: "5px 8px", borderRadius: 8, border: "none", fontSize: 12, fontWeight: 600 }} />
          </div>
        </div>
      </div>

      <div style={{ padding: 16 }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: 60, color: "#94a3b8" }}>Caricamento...</div>
        ) : (
          <>
            {/* KPI */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 10, marginBottom: 16 }}>
              <div style={{ background: "#fff", borderRadius: 14, padding: "14px 16px", border: "1px solid #e2e8f0" }}>
                <p style={{ margin: 0, fontSize: 26, fontWeight: 900, color: "#5b7a6b" }}>
                  {kpi.totale_pezzi_invenduti || 0}
                </p>
                <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>Pezzi buttati</p>
              </div>
              <div style={{ background: "#fff", borderRadius: 14, padding: "14px 16px", border: "1px solid #e2e8f0" }}>
                <p style={{ margin: 0, fontSize: 26, fontWeight: 900, color: "var(--danger)" }}>
                  €{(kpi.costo_totale_sprecato || 0).toFixed(2)}
                </p>
                <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>Costo mat. prime sprecate</p>
              </div>
              <div style={{ background: "#fff", borderRadius: 14, padding: "14px 16px", border: "1px solid #e2e8f0" }}>
                <p style={{ margin: 0, fontSize: 26, fontWeight: 900, color: colorePerc(kpi.pct_media_spreco || 0) }}>
                  {kpi.pct_media_spreco || 0}%
                </p>
                <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>% media spreco</p>
              </div>
              <div style={{ background: "#fff", borderRadius: 14, padding: "14px 16px", border: "1px solid #e2e8f0" }}>
                <p style={{ margin: 0, fontSize: 26, fontWeight: 900, color: "var(--info)" }}>
                  {kpi.totale_prodotto || 0}
                </p>
                <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>Pezzi prodotti (periodo)</p>
              </div>
            </div>

            {/* Lista periodi */}
            {periodi.length === 0 ? (
              <div style={{ textAlign: "center", padding: 40, background: "#fff", borderRadius: 14, border: "1px solid #e2e8f0" }}>
                <p style={{ fontSize: 32, margin: "0 0 8px" }}>🎉</p>
                <p style={{ fontWeight: 700, color: "var(--success)" }}>Nessun invenduto nel periodo</p>
                <p style={{ fontSize: 13, color: "#94a3b8" }}>Hai venduto tutto!</p>
              </div>
            ) : periodi.map((p, idx) => (
              <div key={p.periodo} style={{ background: "#fff", borderRadius: 14, border: "1px solid #e2e8f0", marginBottom: 10, overflow: "hidden" }}>
                {/* Riga periodo */}
                <div
                  onClick={() => setEspanso(espanso === idx ? null : idx)}
                  style={{
                    padding: "12px 16px", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    background: espanso === idx ? "#f2f6f3" : "#fff"
                  }}
                >
                  <div>
                    <p style={{ margin: 0, fontWeight: 800, fontSize: 14, color: "#1e293b" }}>
                      {labelPeriodo(p.periodo)}
                    </p>
                    <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>
                      {p.totale_invenduto} pz invenduti su {p.totale_prodotto} prodotti
                    </p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <p style={{ margin: 0, fontWeight: 800, fontSize: 16, color: "var(--danger)" }}>
                      €{p.costo_sprecato.toFixed(2)}
                    </p>
                    <p style={{ margin: "2px 0 0", fontSize: 11, fontWeight: 700, color: colorePerc(p.pct_sprecato) }}>
                      {p.pct_sprecato}% sprecato
                    </p>
                  </div>
                  <span style={{ marginLeft: 10, color: "#94a3b8", fontSize: 16 }}>
                    {espanso === idx ? "▲" : "▼"}
                  </span>
                </div>

                {/* Barra % */}
                <div style={{ height: 4, background: "#f1f5f9" }}>
                  <div style={{
                    height: "100%", width: `${Math.min(p.pct_sprecato, 100)}%`,
                    background: colorePerc(p.pct_sprecato), transition: "width 0.4s"
                  }} />
                </div>

                {/* Dettaglio prodotti (espanso) */}
                {espanso === idx && (
                  <div style={{ padding: "8px 16px 12px" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 50px 50px 70px", gap: 6,
                      padding: "6px 0", borderBottom: "1px solid #f1f5f9", marginBottom: 4 }}>
                      {["Prodotto","Inv.","Prod.","€ Spreco"].map(h => (
                        <span key={h} style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>{h}</span>
                      ))}
                    </div>
                    {p.prodotti.map(prod => (
                      <div key={prod.nome} style={{ display: "grid", gridTemplateColumns: "1fr 50px 50px 70px",
                        gap: 6, padding: "7px 0", borderBottom: "1px solid #f8fafc", alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, textTransform: "capitalize",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {prod.nome}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--danger)" }}>{prod.pezzi_invenduto}</span>
                        <span style={{ fontSize: 12, color: "#64748b" }}>{prod.pezzi_prodotto}</span>
                        <div>
                          <span style={{ fontSize: 13, fontWeight: 700, color: prod.costo_sprecato > 0 ? "#5b7a6b" : "#94a3b8" }}>
                            {prod.costo_sprecato > 0 ? `€${prod.costo_sprecato.toFixed(2)}` : "—"}
                          </span>
                          {prod.costo_pz > 0 && (
                            <p style={{ margin: 0, fontSize: 9, color: "#94a3b8" }}>€{prod.costo_pz.toFixed(3)}/pz</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ── Statistiche ───────────────────────────────────────────────────────────────
function StatisticheVendite({ onBack }) {
  const [stats, setStats]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [periodo, setPeriodo] = useState(30);
  const [reparto, setReparto] = useState("");
  const [vistaStats, setVistaStats] = useState("prodotto"); // "prodotto" | "giorno"
  const [statsGiorno, setStatsGiorno] = useState([]);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const data_da = format(subDays(new Date(), periodo), "yyyy-MM-dd");
      const data_a  = format(new Date(), "yyyy-MM-dd");
      const params = { data_da, data_a, ...(reparto ? { reparto } : {}) };
      const [resProd, resGiorno] = await Promise.all([
        axios.get(`${API}/vendita-banco/statistiche`, { params }),
        axios.get(`${API}/vendita-banco/statistiche-giorno`, { params })
      ]);
      setStats(resProd.data || []);
      setStatsGiorno(resGiorno.data || []);
    } catch { toast.error("Errore statistiche"); }
    finally { setLoading(false); }
  }, [periodo, reparto]);

  useEffect(() => { carica(); }, [carica]);

  const totVend  = stats.reduce((s, r) => s + r.totale_venduti, 0);
  const totProd  = stats.reduce((s, r) => s + r.totale_prodotti, 0);
  const totInv   = stats.reduce((s, r) => s + r.totale_invenduto, 0);
  const pctGlob  = totProd > 0 ? Math.round((totVend / totProd) * 100) : 0;

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc" }}>
      <div style={{ background: GRADIENT_HEADER, padding: "16px 20px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <button onClick={onBack} style={{
            background: "rgba(255,255,255,0.2)", border: "none", color: "#fff",
            borderRadius: 10, padding: "8px 14px", fontWeight: 700, cursor: "pointer"
          }}>← Banco</button>
          <h1 style={{ color: "#fff", margin: 0, fontSize: 20, fontWeight: 800 }}>Statistiche Vendita</h1>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[7, 30, 90, 365].map(g => (
            <button key={g} onClick={() => setPeriodo(g)} style={{
              padding: "6px 12px", borderRadius: 8,
              border: `2px solid rgba(255,255,255,${periodo === g ? 0.9 : 0.4})`,
              background: periodo === g ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.15)",
              color: periodo === g ? "#ea580c" : "#fff",
              fontWeight: 700, fontSize: 12, cursor: "pointer"
            }}>
              {g === 365 ? "1 anno" : `${g}gg`}
            </button>
          ))}
          <select value={reparto} onChange={e => setReparto(e.target.value)} style={{
            padding: "6px 10px", borderRadius: 8, border: "none", fontSize: 12,
            fontWeight: 600, background: "rgba(255,255,255,0.9)"
          }}>
            <option value="">Tutti</option>
            <option value="rosticceria">Rosticceria</option>
            <option value="pasticceria">Pasticceria</option>
          </select>
        </div>
      </div>

      <div style={{ padding: 16 }}>
        {/* KPI globali */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 16 }}>
          {[
            { label: "Prodotti", val: totProd.toLocaleString("it-IT"), color: "var(--info)" },
            { label: "Venduti",  val: totVend.toLocaleString("it-IT"), color: "var(--success)" },
            { label: "Invenduto",val: totInv.toLocaleString("it-IT"),  color: "var(--danger)" },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ background: "#fff", borderRadius: 14, padding: 12, textAlign: "center", border: "1px solid #e2e8f0" }}>
              <p style={{ margin: 0, fontWeight: 800, fontSize: 22, color }}>{val}</p>
              <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>{label}</p>
            </div>
          ))}
        </div>

        {/* % globale */}
        <div style={{ background: "#fff", borderRadius: 14, padding: 14, marginBottom: 16, border: "1px solid #e2e8f0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>Indice venduto</span>
            <span style={{ fontWeight: 800, fontSize: 18, color: pctGlob >= 80 ? "var(--success)" : pctGlob >= 50 ? "var(--warning-dark)" : "var(--danger)" }}>
              {pctGlob}%
            </span>
          </div>
          <div style={{ background: "#e2e8f0", borderRadius: 8, height: 10, overflow: "hidden" }}>
            <div style={{
              width: `${pctGlob}%`, height: "100%", borderRadius: 8,
              background: pctGlob >= 80 ? "var(--success)" : pctGlob >= 50 ? "var(--warning)" : "var(--danger)"
            }} />
          </div>
        </div>

        {/* Toggle vista */}
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {[
            { id: "prodotto", label: "Per Prodotto" },
            { id: "giorno",   label: "Per Giorno" }
          ].map(v => (
            <button key={v.id} onClick={() => setVistaStats(v.id)} style={{
              padding: "7px 16px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: "pointer",
              border: `2px solid ${vistaStats === v.id ? "#f97316" : "#e2e8f0"}`,
              background: vistaStats === v.id ? "#fff7ed" : "#fff",
              color: vistaStats === v.id ? "#ea580c" : "#64748b"
            }}>{v.label}</button>
          ))}
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: 40, color: "#94a3b8" }}>Caricamento...</div>
        ) : vistaStats === "prodotto" ? (
          /* ── TABELLA PER PRODOTTO ── */
          <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #e2e8f0", overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", background: "#f8fafc", borderBottom: "1px solid #e2e8f0",
              display: "grid", gridTemplateColumns: "1fr 55px 55px 55px 50px", gap: 8 }}>
              {["Prodotto","Prod.","Vend.","Inv.","%"].map(h => (
                <span key={h} style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>{h}</span>
              ))}
            </div>
            {stats.length === 0 ? (
              <p style={{ textAlign: "center", padding: 30, color: "#94a3b8" }}>Nessun dato</p>
            ) : stats.map((r, i) => (
              <div key={r.prodotto} style={{
                padding: "10px 14px",
                borderBottom: i < stats.length - 1 ? "1px solid #f1f5f9" : "none",
                display: "grid", gridTemplateColumns: "1fr 55px 55px 55px 50px", gap: 8, alignItems: "center"
              }}>
                <span style={{ fontSize: 13, fontWeight: 600, textTransform: "capitalize", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.prodotto}</span>
                <span style={{ fontSize: 13, color: "var(--info)", fontWeight: 600 }}>{r.totale_prodotti}</span>
                <span style={{ fontSize: 13, color: "var(--success)", fontWeight: 600 }}>{r.totale_venduti}</span>
                <span style={{ fontSize: 13, color: "var(--danger)", fontWeight: 600 }}>{r.totale_invenduto}</span>
                <span style={{ fontSize: 12, fontWeight: 800,
                  color: r.pct_venduto >= 80 ? "var(--success)" : r.pct_venduto >= 50 ? "var(--warning-dark)" : "var(--danger)"
                }}>{r.pct_venduto}%</span>
              </div>
            ))}
          </div>
        ) : (
          /* ── TABELLA PER GIORNO ── */
          <div>
            {statsGiorno.length === 0 ? (
              <p style={{ textAlign: "center", padding: 30, color: "#94a3b8" }}>Nessun dato</p>
            ) : statsGiorno.map((giorno) => (
              <div key={giorno.data} style={{ background: "#fff", borderRadius: 14, border: "1px solid #e2e8f0", overflow: "hidden", marginBottom: 12 }}>
                {/* Header giorno */}
                <div style={{
                  padding: "10px 14px", background: "#fff7ed", borderBottom: "2px solid #fed7aa",
                  display: "flex", justifyContent: "space-between", alignItems: "center"
                }}>
                  <span style={{ fontWeight: 800, fontSize: 14, color: "#c2410c" }}>
                    {(() => {
                      try { return format(parseISO(giorno.data), "EEEE d MMMM yyyy", { locale: it }); }
                      catch { return giorno.data; }
                    })()}
                  </span>
                  <div style={{ display: "flex", gap: 10, fontSize: 12 }}>
                    <span style={{ color: "var(--info)", fontWeight: 700 }}>P: {giorno.totale_prodotti}</span>
                    <span style={{ color: "var(--success)", fontWeight: 700 }}>V: {giorno.totale_venduti}</span>
                    <span style={{ color: "var(--danger)", fontWeight: 700 }}>I: {giorno.totale_invenduto}</span>
                  </div>
                </div>
                {/* Righe prodotti del giorno */}
                {giorno.prodotti.map((p, i) => (
                  <div key={p.prodotto} style={{
                    padding: "9px 14px",
                    borderBottom: i < giorno.prodotti.length - 1 ? "1px solid #f1f5f9" : "none",
                    display: "grid", gridTemplateColumns: "1fr 55px 55px 55px 50px", gap: 8, alignItems: "center"
                  }}>
                    <span style={{ fontSize: 13, fontWeight: 600, textTransform: "capitalize", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.prodotto}</span>
                    <span style={{ fontSize: 13, color: "var(--info)", fontWeight: 600 }}>{p.pezzi_prodotti}</span>
                    <span style={{ fontSize: 13, color: "var(--success)", fontWeight: 600 }}>{p.pezzi_venduti ?? "-"}</span>
                    <span style={{ fontSize: 13, color: "var(--danger)", fontWeight: 600 }}>{p.pezzi_invenduto ?? "-"}</span>
                    <span style={{ fontSize: 12, fontWeight: 800,
                      color: p.pct >= 80 ? "var(--success)" : p.pct >= 50 ? "var(--warning-dark)" : "var(--danger)"
                    }}>{p.pct != null ? `${p.pct}%` : "-"}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Componente principale ─────────────────────────────────────────────────────
export const VenditaBancoView = ({ onBack }) => {
  const [vista, setVista]           = useState("banco");  // "banco"|"tutti"|"dettaglio"|"statistiche"|"sprechi"
  const [venditeOggi, setVenditeOggi] = useState([]);
  const [tuttiProdotti, setTuttiProdotti] = useState([]);
  const [prodottoSel, setProdottoSel]   = useState(null); // record per dettaglio
  const [loading, setLoading]       = useState(true);
  const [archivioAperto, setArchivioAperto] = useState(false);

  const caricaOggi = useCallback(async () => {
    setLoading(true);
    try {
      // Carica TUTTI i prodotti al banco oggi senza filtro reparto
      const [resOggi, resRicette] = await Promise.all([
        axios.get(`${API}/vendita-banco/oggi`),
        axios.get(`${API}/ricette`)
      ]);
      setVenditeOggi(resOggi.data || []);
      setTuttiProdotti(resRicette.data || []);
    } catch { toast.error("Errore caricamento"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { caricaOggi(); }, [caricaOggi]);

  const handleSalva = async (id, invenduto) => {
    // Ottimistico: rimuovi subito dalla lista "da fare" senza aspettare il server
    setVenditeOggi(prev => prev.map(v =>
      v.id === id ? { ...v, stato: "chiuso", pezzi_invenduto: invenduto, pezzi_venduti: Math.max(0, (v.pezzi_prodotti || 0) - invenduto) } : v
    ));
    toast.success("Salvato!");
    try {
      await axios.put(`${API}/vendita-banco/${id}/invenduto`, { vendita_id: id, pezzi_invenduto: invenduto });
      caricaOggi(); // aggiorna in background
    } catch {
      toast.error("Errore salvataggio");
      caricaOggi(); // rollback
    }
  };

  const handleRiapri = async (id) => {
    await axios.put(`${API}/vendita-banco/${id}/riapri`);
    toast.success("Record riaperto per modifica");
    await caricaOggi();
  };

  // Naviga a dettaglio: usa record vendita se esiste, altrimenti crea record vuoto da ricetta
  const apriDettaglio = (prodotto) => {
    const nomeN = (prodotto.nome || prodotto.prodotto_nome || "").toLowerCase().trim();
    const vendita = venditeOggi.find(v => (v.prodotto_nome || "").toLowerCase().trim() === nomeN);
    setProdottoSel(vendita || {
      prodotto_nome: prodotto.nome,
      foto_url: prodotto.foto_url,
      pezzi_prodotti: 0,
      stato: "non_prodotto",
      non_prodotto: true
    });
    setVista("dettaglio");
  };

  if (vista === "statistiche") return <StatisticheVendite onBack={() => setVista("banco")} />;
  if (vista === "sprechi") return <SprechiView onBack={() => setVista("banco")} />;

  // ── Vista Dettaglio ──────────────────────────────────────────────────────────
  if (vista === "dettaglio" && prodottoSel) {
    const isNonProdotto = prodottoSel.non_prodotto || prodottoSel.pezzi_prodotti === 0;
    return (
      <div style={{ minHeight: "100vh", background: "#f8fafc" }}>
        {/* Header */}
        <div style={{ background: GRADIENT_HEADER, padding: "14px 18px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button onClick={() => setVista("tutti")} style={{
              background: "rgba(255,255,255,0.2)", border: "none", color: "#fff",
              borderRadius: 10, padding: "8px 14px", fontWeight: 700, cursor: "pointer", fontSize: 14
            }}>←</button>
            <h1 style={{ color: "#fff", margin: 0, fontSize: 18, fontWeight: 800, textTransform: "capitalize", flex: 1, minWidth: 0 }}>
              {prodottoSel.prodotto_nome}
            </h1>
          </div>
        </div>

        <div style={{ padding: 16 }}>
          {/* Foto */}
          <div style={{ borderRadius: 16, overflow: "hidden", height: 180, background: "#e2e8f0", marginBottom: 16 }}>
            {prodottoSel.foto_url ? (
              <img src={fotoSrc(prodottoSel.foto_url)} alt={prodottoSel.prodotto_nome}
                style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            ) : (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 60, color: "#94a3b8" }}>🍽</div>
            )}
          </div>

          {isNonProdotto ? (
            <div style={{ background: "#fff", borderRadius: 14, padding: 20, textAlign: "center",
              border: "2px dashed #e2e8f0" }}>
              <p style={{ fontSize: 32, margin: "0 0 8px" }}>📦</p>
              <p style={{ fontWeight: 700, fontSize: 16, color: "#475569", margin: 0 }}>Non prodotto oggi</p>
              <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 4 }}>
                Nessuna produzione registrata per questo prodotto oggi.
              </p>
            </div>
          ) : (
            <CardProdotto item={prodottoSel} onSalva={handleSalva} onRiapri={handleRiapri} />
          )}
        </div>
      </div>
    );
  }

  // ── Vista Tutti i Prodotti ────────────────────────────────────────────────────
  if (vista === "tutti") {
    const oggi = format(new Date(), "yyyy-MM-dd");
    return (
      <div style={{ minHeight: "100vh", background: "#f8fafc" }}>
        <div style={{ background: GRADIENT_HEADER, padding: "14px 18px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <button onClick={() => setVista("banco")} style={{
              background: "rgba(255,255,255,0.2)", border: "none", color: "#fff",
              borderRadius: 10, padding: "8px 14px", fontWeight: 700, cursor: "pointer", fontSize: 14
            }}>←</button>
            <h1 style={{ color: "#fff", margin: 0, fontSize: 18, fontWeight: 800, flex: 1, minWidth: 0 }}>
              Tutti i Prodotti
            </h1>
          </div>
          <p style={{ color: "rgba(255,255,255,0.8)", margin: "4px 0 0", fontSize: 12 }}>
            {format(new Date(), "EEEE d MMMM yyyy", { locale: it })} · {tuttiProdotti.length} prodotti
          </p>
        </div>

        <div style={{ padding: 12 }}>
          {/* Legenda */}
          <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            {[
              { colore: "var(--success)", label: "Chiuso" },
              { colore: "var(--warning)", label: "Al banco" },
              { colore: "#e2e8f0", label: "Non prodotto" }
            ].map(({ colore, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#64748b" }}>
                <div style={{ width: 10, height: 10, borderRadius: "50%", background: colore }} />
                {label}
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(150px,1fr))", gap: 10 }}>
            {tuttiProdotti.map(prod => {
              const nomeN = (prod.nome || "").toLowerCase().trim();
              const vendita = venditeOggi.find(v => (v.prodotto_nome || "").toLowerCase().trim() === nomeN);
              const stato = vendita ? vendita.stato : "non_prodotto";
              const bordo = stato === "chiuso" ? "#86efac" : stato === "aperto" ? "var(--warning-soft)" : "#e2e8f0";
              const badge = stato === "chiuso" ? { bg: "var(--success)", label: "✓" }
                          : stato === "aperto" ? { bg: "var(--warning)", label: "⏳" }
                          : { bg: "#cbd5e1", label: "—" };
              return (
                <div key={prod.id} onClick={() => apriDettaglio(prod)}
                  style={{ background: "#fff", borderRadius: 14, border: `2px solid ${bordo}`,
                    overflow: "hidden", cursor: "pointer", boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
                    transition: "transform 0.1s", userSelect: "none" }}
                  onTouchStart={e => e.currentTarget.style.transform="scale(0.97)"}
                  onTouchEnd={e => e.currentTarget.style.transform="scale(1)"}
                >
                  {/* Foto */}
                  <div style={{ height: 90, background: "#f1f5f9", position: "relative", overflow: "hidden" }}>
                    {prod.foto_url ? (
                      <img src={fotoSrc(prod.foto_url)} alt={prod.nome}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        onError={e => { e.target.style.display="none"; }} />
                    ) : (
                      <div style={{ height: "100%", display: "flex", alignItems: "center",
                        justifyContent: "center", fontSize: 30, color: "#cbd5e1" }}>🍽</div>
                    )}
                    <div style={{ position: "absolute", top: 6, right: 6, background: badge.bg,
                      color: "#fff", borderRadius: 20, padding: "2px 7px", fontSize: 10, fontWeight: 700 }}>
                      {badge.label}
                    </div>
                  </div>
                  {/* Nome + quantità */}
                  <div style={{ padding: "7px 9px" }}>
                    <p style={{ margin: 0, fontSize: 11, fontWeight: 700, textTransform: "capitalize",
                      color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {prod.nome}
                    </p>
                    {vendita && (
                      <p style={{ margin: "2px 0 0", fontSize: 10, color: "#64748b" }}>
                        {vendita.pezzi_prodotti}pz · {vendita.pezzi_invenduto ?? "?"}inv.
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  const aperte = venditeOggi.filter(v => v.stato === "aperto");
  const chiuse = venditeOggi.filter(v => v.stato === "chiuso");
  const totVend = chiuse.reduce((s, v) => s + (v.pezzi_venduti || 0), 0);
  const totInv  = chiuse.reduce((s, v) => s + (v.pezzi_invenduto || 0), 0);

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div style={{ background: GRADIENT_HEADER, padding: "14px 18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {onBack && (
              <button onClick={onBack} style={{
                background: "rgba(255,255,255,0.2)", border: "none", color: "#fff",
                borderRadius: 10, padding: "8px 12px", fontWeight: 700, cursor: "pointer", fontSize: 16
              }}>←</button>
            )}
            <div>
              <h1 style={{ color: "#fff", margin: 0, fontSize: 20, fontWeight: 800 }}>Registro Invenduto</h1>
              <p style={{ color: "rgba(255,255,255,0.85)", margin: "2px 0 0", fontSize: 13 }}>
                {format(new Date(), "EEEE d MMMM yyyy", { locale: it })}
              </p>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, flexDirection: "column", alignItems: "flex-end" }}>
            <button onClick={() => setVista("statistiche")} style={{
              background: "rgba(255,255,255,0.2)", border: "2px solid rgba(255,255,255,0.4)",
              color: "#fff", borderRadius: 10, padding: "7px 12px",
              fontWeight: 700, cursor: "pointer", fontSize: 12
            }}>Statistiche</button>
            <button onClick={() => setVista("sprechi")} style={{
              background: "rgba(211,95,78,0.4)", border: "2px solid rgba(230,150,138,0.6)",
              color: "#fff", borderRadius: 10, padding: "7px 12px",
              fontWeight: 700, cursor: "pointer", fontSize: 12
            }}>Sprechi</button>
            <button onClick={() => setVista("tutti")} style={{
              background: "rgba(255,255,255,0.15)", border: "2px solid rgba(255,255,255,0.3)",
              color: "#fff", borderRadius: 10, padding: "6px 12px",
              fontWeight: 700, cursor: "pointer", fontSize: 12
            }}>Tutti i prodotti</button>
          </div>
        </div>

        {/* Sommario */}
        <div style={{ display: "flex", gap: 8 }}>
          {[
            { val: chiuse.length,  label: "Registrati", bg: "rgba(74,222,128,0.3)",  color: "#fff" },
            { val: totVend,        label: "Pz venduti", bg: "rgba(255,255,255,0.2)",  color: "#fff" },
            { val: totInv,         label: "Pz inv.",    bg: "rgba(252,165,165,0.3)", color: "#fff" },
          ].map(({ val, label, bg, color }) => (
            <div key={label} style={{ background: bg, borderRadius: 10, padding: "6px 12px", textAlign: "center" }}>
              <p style={{ margin: 0, fontWeight: 900, fontSize: 18, color }}>{val}</p>
              <p style={{ margin: 0, fontSize: 10, color, opacity: 0.85 }}>{label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Contenuto */}
      <div style={{ flex: 1, padding: 14, overflowY: "auto" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: 60, color: "#94a3b8", fontSize: 16 }}>Caricamento...</div>
        ) : venditeOggi.length === 0 ? (
          <div style={{ textAlign: "center", padding: 60 }}>
            <div style={{ fontSize: 56, marginBottom: 14 }}>🛒</div>
            <p style={{ fontSize: 18, fontWeight: 700, color: "#475569" }}>Nessun articolo al banco oggi</p>
            <p style={{ fontSize: 14, color: "#94a3b8", marginTop: 6 }}>
              Gli articoli appariranno qui quando vengono<br />
              inviati al banco dal tablet di produzione
            </p>
          </div>
        ) : (
          <>
            {/* Da registrare — visibili solo gli aperti */}
            {aperte.length > 0 ? (
              <div style={{ marginBottom: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                  <div style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--warning)" }} />
                  <p style={{ margin: 0, fontWeight: 800, fontSize: 13, color: "var(--warning-dark)", textTransform: "uppercase", letterSpacing: 1 }}>
                    Da registrare ({aperte.length})
                  </p>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
                  {aperte.map(item => (
                    <CardProdotto key={item.id} item={item} onSalva={handleSalva} onRiapri={handleRiapri} />
                  ))}
                </div>
              </div>
            ) : (
              /* Tutto registrato */
              <div style={{ textAlign: "center", padding: "40px 20px" }}>
                <div style={{ fontSize: 64, marginBottom: 12 }}>✅</div>
                <p style={{ fontSize: 20, fontWeight: 800, color: "var(--success)", margin: 0 }}>Tutto registrato!</p>
                <p style={{ fontSize: 14, color: "#64748b", marginTop: 6 }}>
                  {chiuse.length} referenze chiuse — {totVend} pz venduti, {totInv} pz invenduti
                </p>
              </div>
            )}

            {/* Archivio collassabile — prodotti già registrati */}
            {chiuse.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <button
                  onClick={() => setArchivioAperto(v => !v)}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                    background: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 12,
                    padding: "10px 16px", cursor: "pointer", fontWeight: 700, fontSize: 13,
                    color: "#475569"
                  }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--success)" }} />
                    Archivio di oggi — {chiuse.length} registrati ({totVend} venduti · {totInv} invenduti)
                  </span>
                  <span style={{ fontSize: 18, lineHeight: 1 }}>{archivioAperto ? "▲" : "▼"}</span>
                </button>

                {archivioAperto && (
                  <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
                    {chiuse.map(item => (
                      <CardProdotto key={item.id} item={item} onSalva={handleSalva} onRiapri={handleRiapri} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default VenditaBancoView;
