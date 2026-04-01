import { useState, useEffect } from "react";
import api from "../api";
import PageLayout from "../components/PageLayout";
import { COLORS, STYLES, SPACING, button, badge } from "../lib/utils";

export default function RicettarioAdmin() {
  const [ricette, setRicette] = useState([]);
  const [riepilogo, setRiepilogo] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sezione, setSezione] = useState("lista"); // lista | costi
  const [dettaglio, setDettaglio] = useState(null);
  const [loadingCosto, setLoadingCosto] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [r1, r2, r3] = await Promise.all([
        api.get("/api/cucina/ricette"),
        api.get("/api/cucina/food-cost/ricette-riepilogo"),
        api.get("/api/cucina/ricette/stats"),
      ]);
      setRicette(r1.data);
      setRiepilogo(r2.data);
      setStats(r3.data);
    } catch (e) {
      setErr("Errore caricamento dati");
    } finally {
      setLoading(false);
    }
  }

  async function calcolaDettaglio(id) {
    setLoadingCosto(true);
    try {
      const r = await api.get(`/api/cucina/food-cost/calcola/${id}`);
      setDettaglio(r.data);
    } catch (e) {
      setErr("Errore calcolo food cost");
    } finally {
      setLoadingCosto(false);
    }
  }

  async function approvaRicetta(id) {
    await api.patch(`/api/cucina/ricette/${id}/approva`);
    setRicette(prev => prev.map(r => r.id === id ? { ...r, approvata: true } : r));
  }

  const ricetteFiltrate = ricette.filter(r =>
    !search || r.nome?.toLowerCase().includes(search.toLowerCase())
  );

  const riepilogoMap = Object.fromEntries(riepilogo.map(r => [r.id, r]));

  return (
    <PageLayout>
      <div style={STYLES.page}>
        {/* Header */}
        <div style={STYLES.header} data-testid="ricettario-header">
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Ricettario</h1>
            <div style={{ fontSize: 13, opacity: 0.8, marginTop: 4 }}>
              {stats.totale || 0} ricette · {stats.da_approvare || 0} da approvare · {stats.nuove_settimana || 0} nuove questa settimana
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              style={button(sezione === "lista" ? "primary" : "outline")}
              onClick={() => setSezione("lista")}
              data-testid="tab-lista"
            >Lista</button>
            <button
              style={button(sezione === "costi" ? "primary" : "outline")}
              onClick={() => setSezione("costi")}
              data-testid="tab-costi"
            >Costi</button>
            <a
              href="/api/cucina/ricette/export/pdf"
              target="_blank"
              rel="noopener noreferrer"
              style={{ ...button("success"), textDecoration: "none" }}
              data-testid="btn-export-pdf"
            >Stampa PDF</a>
          </div>
        </div>

        {err && <div style={{ ...STYLES.card, background: "#fee2e2", color: COLORS.danger, marginBottom: 12 }}>{err}</div>}

        {/* Search */}
        <div style={{ marginBottom: 16 }}>
          <input
            style={{ ...STYLES.input, maxWidth: 360 }}
            placeholder="Cerca ricetta..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            data-testid="search-ricetta"
          />
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: 60, color: COLORS.gray }}>Caricamento...</div>
        ) : sezione === "lista" ? (
          /* ── SEZIONE LISTA ── */
          <div style={STYLES.card}>
            <table style={STYLES.table}>
              <thead>
                <tr>
                  <th style={STYLES.th}>Nome Ricetta</th>
                  <th style={{ ...STYLES.th, textAlign: "center" }}>Ingredienti</th>
                  <th style={{ ...STYLES.th, textAlign: "right" }}>Costo/pz</th>
                  <th style={{ ...STYLES.th, textAlign: "center" }}>Stato</th>
                  <th style={{ ...STYLES.th, textAlign: "center" }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {ricetteFiltrate.map(r => {
                  const costi = riepilogoMap[r.id];
                  return (
                    <tr key={r.id} data-testid={`riga-ricetta-${r.id}`}>
                      <td style={STYLES.td}>
                        <strong>{r.nome}</strong>
                        {r.reparto && (
                          <span style={{ marginLeft: 8, fontSize: 11, padding: "2px 8px", borderRadius: 10, background: r.reparto === "pasticceria" ? "#fef3c7" : "#dbeafe", color: r.reparto === "pasticceria" ? "#92400e" : "#1e40af" }}>
                            {r.reparto}
                          </span>
                        )}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "center" }}>
                        {costi ? `${costi.ingredienti_con_prezzo}/${costi.ingredienti_totali}` : (r.ingredienti_dettaglio?.length || r.ingredienti?.length || 0)}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "right" }}>
                        {costi?.costo_porzione > 0 ? `€ ${costi.costo_porzione.toFixed(3)}` : "—"}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "center" }}>
                        {r.approvata
                          ? <span style={{ ...badge("success"), fontSize: 11 }}>Approvata</span>
                          : <span style={{ ...badge("warning"), fontSize: 11 }}>Da approvare</span>}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "center" }}>
                        <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
                          <button
                            style={{ ...button("outline"), padding: "4px 10px", fontSize: 12 }}
                            onClick={() => calcolaDettaglio(r.id)}
                            data-testid={`btn-calcola-${r.id}`}
                          >Calcola</button>
                          {!r.approvata && (
                            <button
                              style={{ ...button("success"), padding: "4px 10px", fontSize: 12 }}
                              onClick={() => approvaRicetta(r.id)}
                              data-testid={`btn-approva-${r.id}`}
                            >Approva</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {ricetteFiltrate.length === 0 && (
              <div style={{ textAlign: "center", padding: 40, color: COLORS.gray }}>
                Nessuna ricetta trovata
              </div>
            )}
          </div>
        ) : (
          /* ── SEZIONE COSTI ── */
          <div style={STYLES.card}>
            <table style={STYLES.table}>
              <thead>
                <tr>
                  <th style={STYLES.th}>Ricetta</th>
                  <th style={{ ...STYLES.th, textAlign: "center" }}>Copertura</th>
                  <th style={{ ...STYLES.th, textAlign: "right" }}>Costo Tot.</th>
                  <th style={{ ...STYLES.th, textAlign: "right" }}>Costo/pz</th>
                </tr>
              </thead>
              <tbody>
                {riepilogo.filter(r => !search || r.nome?.toLowerCase().includes(search.toLowerCase())).map(r => (
                  <tr key={r.id} data-testid={`riga-costo-${r.id}`}>
                    <td style={STYLES.td}><strong>{r.nome}</strong></td>
                    <td style={{ ...STYLES.td, textAlign: "center" }}>
                      <span style={{ color: r.ingredienti_con_prezzo === r.ingredienti_totali ? COLORS.success : COLORS.warning }}>
                        {r.completezza}
                      </span>
                    </td>
                    <td style={{ ...STYLES.td, textAlign: "right" }}>
                      {r.costo_totale > 0 ? `€ ${r.costo_totale.toFixed(2)}` : "—"}
                    </td>
                    <td style={{ ...STYLES.td, textAlign: "right", fontWeight: 600 }}>
                      {r.costo_porzione > 0 ? `€ ${r.costo_porzione.toFixed(3)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Modal Dettaglio Food Cost */}
        {dettaglio && (
          <div
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
            onClick={() => setDettaglio(null)}
          >
            <div
              style={{ background: COLORS.white, borderRadius: 12, padding: SPACING.xl, maxWidth: 640, width: "90%", maxHeight: "85vh", overflowY: "auto" }}
              onClick={e => e.stopPropagation()}
            >
              {loadingCosto ? (
                <div style={{ textAlign: "center", padding: 40 }}>Calcolo in corso...</div>
              ) : (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <h2 style={{ margin: 0, color: COLORS.primary }}>{dettaglio.nome}</h2>
                    <button style={button("outline")} onClick={() => setDettaglio(null)}>✕</button>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                    {[
                      { label: "Costo Totale", value: `€ ${dettaglio.costo_totale?.toFixed(2)}` },
                      { label: "Porzioni", value: dettaglio.porzioni },
                      { label: "Costo/Porzione", value: `€ ${dettaglio.costo_porzione?.toFixed(3)}` },
                      { label: "Copertura", value: dettaglio.completezza },
                    ].map(({ label, value }) => (
                      <div key={label} style={{ ...STYLES.card, padding: 12, background: COLORS.grayBg }}>
                        <div style={{ fontSize: 11, color: COLORS.gray }}>{label}</div>
                        <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.primary }}>{value}</div>
                      </div>
                    ))}
                  </div>
                  <table style={STYLES.table}>
                    <thead>
                      <tr>
                        <th style={STYLES.th}>Ingrediente</th>
                        <th style={{ ...STYLES.th, textAlign: "center" }}>Qtà</th>
                        <th style={{ ...STYLES.th, textAlign: "right" }}>€/kg</th>
                        <th style={{ ...STYLES.th, textAlign: "right" }}>Costo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dettaglio.ingredienti?.map((ing, i) => (
                        <tr key={i} style={{ background: ing.costo == null ? "#fff7ed" : "white" }}>
                          <td style={STYLES.td}>{ing.nome}{ing.costo == null && <span style={{ color: COLORS.warning, fontSize: 11, marginLeft: 6 }}>⚠ mancante</span>}</td>
                          <td style={{ ...STYLES.td, textAlign: "center" }}>{ing.quantita} {ing.unita}</td>
                          <td style={{ ...STYLES.td, textAlign: "right" }}>{ing.prezzo_kg ? `€ ${ing.prezzo_kg.toFixed(2)}` : "—"}</td>
                          <td style={{ ...STYLES.td, textAlign: "right", fontWeight: 600 }}>{ing.costo != null ? `€ ${ing.costo.toFixed(3)}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
