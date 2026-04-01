import { useState, useEffect } from "react";
import api from "../api";
import PageLayout from "../components/PageLayout";
import { COLORS, STYLES, SPACING, button } from "../lib/utils";

export default function FoodCostAdmin() {
  const [sezione, setSezione] = useState("riepilogo"); // riepilogo | dizionario | dettaglio
  const [riepilogo, setRiepilogo] = useState([]);
  const [dizionario, setDizionario] = useState([]);
  const [dettaglio, setDettaglio] = useState(null);
  const [ricettaSelezionata, setRicettaSelezionata] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchRic, setSearchRic] = useState("");
  const [searchDiz, setSearchDiz] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { loadRiepilogo(); }, []);

  async function loadRiepilogo() {
    setLoading(true);
    try {
      const r = await api.get("/api/cucina/food-cost/ricette-riepilogo");
      setRiepilogo(r.data);
    } catch (e) { setErr("Errore caricamento"); }
    finally { setLoading(false); }
  }

  async function loadDizionario(q = "") {
    try {
      const r = await api.get(`/api/cucina/food-cost/dizionario${q ? `?search=${q}` : ""}`);
      setDizionario(r.data);
    } catch (e) { setErr("Errore dizionario"); }
  }

  async function calcolaDettaglio(id, nome) {
    setDettaglio(null);
    setRicettaSelezionata(nome);
    setSezione("dettaglio");
    try {
      const r = await api.get(`/api/cucina/food-cost/calcola/${id}`);
      setDettaglio(r.data);
    } catch (e) { setErr("Errore calcolo"); }
  }

  function handleSezione(s) {
    setSezione(s);
    if (s === "dizionario" && dizionario.length === 0) loadDizionario();
  }

  const riepilogoFiltrato = riepilogo.filter(r =>
    !searchRic || r.nome?.toLowerCase().includes(searchRic.toLowerCase())
  );

  const dicionarioFiltrato = dizionario.filter(p =>
    !searchDiz || (p.nome_normalizzato || "").toLowerCase().includes(searchDiz.toLowerCase())
  );

  return (
    <PageLayout>
      <div style={STYLES.page}>
        {/* Header */}
        <div style={STYLES.header} data-testid="foodcost-header">
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Food Cost</h1>
            <div style={{ fontSize: 13, opacity: 0.8, marginTop: 4 }}>
              Analisi costi ingredienti e redditività ricette
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {["riepilogo", "dizionario"].map(s => (
              <button
                key={s}
                style={button(sezione === s ? "primary" : "outline")}
                onClick={() => handleSezione(s)}
                data-testid={`tab-${s}`}
              >{s === "riepilogo" ? "Riepilogo Ricette" : "Dizionario Prezzi"}</button>
            ))}
          </div>
        </div>

        {err && <div style={{ ...STYLES.card, background: "#fee2e2", color: COLORS.danger, marginBottom: 12 }}>{err}</div>}

        {/* ── RIEPILOGO ── */}
        {sezione === "riepilogo" && (
          <>
            <div style={{ marginBottom: 14 }}>
              <input
                style={{ ...STYLES.input, maxWidth: 340 }}
                placeholder="Cerca ricetta..."
                value={searchRic}
                onChange={e => setSearchRic(e.target.value)}
                data-testid="search-riepilogo"
              />
            </div>
            {loading ? (
              <div style={{ textAlign: "center", padding: 60, color: COLORS.gray }}>Caricamento...</div>
            ) : (
              <div style={STYLES.card}>
                <table style={STYLES.table}>
                  <thead>
                    <tr>
                      <th style={STYLES.th}>Ricetta</th>
                      <th style={{ ...STYLES.th, textAlign: "center" }}>Copertura</th>
                      <th style={{ ...STYLES.th, textAlign: "right" }}>Costo Tot.</th>
                      <th style={{ ...STYLES.th, textAlign: "right" }}>Costo/pz</th>
                      <th style={{ ...STYLES.th, textAlign: "center" }}>Dettaglio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {riepilogoFiltrato.map(r => {
                      const pct = r.ingredienti_totali > 0
                        ? Math.round(r.ingredienti_con_prezzo / r.ingredienti_totali * 100) : 0;
                      return (
                        <tr key={r.id} data-testid={`riga-fc-${r.id}`}>
                          <td style={STYLES.td}><strong>{r.nome}</strong></td>
                          <td style={{ ...STYLES.td, textAlign: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "center" }}>
                              <div style={{ width: 60, height: 6, background: COLORS.grayLight, borderRadius: 3, overflow: "hidden" }}>
                                <div style={{ width: `${pct}%`, height: "100%", background: pct === 100 ? COLORS.success : pct > 60 ? COLORS.warning : COLORS.danger }} />
                              </div>
                              <span style={{ fontSize: 11 }}>{r.completezza}</span>
                            </div>
                          </td>
                          <td style={{ ...STYLES.td, textAlign: "right" }}>
                            {r.costo_totale > 0 ? `€ ${r.costo_totale.toFixed(2)}` : "—"}
                          </td>
                          <td style={{ ...STYLES.td, textAlign: "right", fontWeight: 700, color: COLORS.primary }}>
                            {r.costo_porzione > 0 ? `€ ${r.costo_porzione.toFixed(3)}` : "—"}
                          </td>
                          <td style={{ ...STYLES.td, textAlign: "center" }}>
                            <button
                              style={{ ...button("outline"), padding: "4px 10px", fontSize: 12 }}
                              onClick={() => calcolaDettaglio(r.id, r.nome)}
                              data-testid={`btn-dettaglio-${r.id}`}
                            >Analizza</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* ── DIZIONARIO ── */}
        {sezione === "dizionario" && (
          <>
            <div style={{ marginBottom: 14 }}>
              <input
                style={{ ...STYLES.input, maxWidth: 340 }}
                placeholder="Cerca prodotto..."
                value={searchDiz}
                onChange={e => {
                  setSearchDiz(e.target.value);
                  loadDizionario(e.target.value);
                }}
                data-testid="search-dizionario"
              />
            </div>
            <div style={STYLES.card}>
              <table style={STYLES.table}>
                <thead>
                  <tr>
                    <th style={STYLES.th}>Prodotto</th>
                    <th style={STYLES.th}>Fornitore</th>
                    <th style={{ ...STYLES.th, textAlign: "right" }}>€/kg</th>
                    <th style={{ ...STYLES.th, textAlign: "right" }}>€/pz</th>
                    <th style={STYLES.th}>Categoria</th>
                  </tr>
                </thead>
                <tbody>
                  {dicionarioFiltrato.map((p, i) => (
                    <tr key={i}>
                      <td style={STYLES.td}>{p.nome_canonico || p.nome_normalizzato}</td>
                      <td style={STYLES.td}>{p.fornitore || "—"}</td>
                      <td style={{ ...STYLES.td, textAlign: "right" }}>
                        {p.prezzo_kg ? `€ ${Number(p.prezzo_kg).toFixed(2)}` : "—"}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "right" }}>
                        {p.costo_per_pezzo ? `€ ${Number(p.costo_per_pezzo).toFixed(3)}` : "—"}
                      </td>
                      <td style={STYLES.td}>{p.categoria || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {dicionarioFiltrato.length === 0 && (
                <div style={{ textAlign: "center", padding: 40, color: COLORS.gray }}>Nessun prodotto trovato</div>
              )}
            </div>
          </>
        )}

        {/* ── DETTAGLIO ── */}
        {sezione === "dettaglio" && (
          <div style={STYLES.card}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <button style={button("outline")} onClick={() => setSezione("riepilogo")}>← Indietro</button>
              <h2 style={{ margin: 0, color: COLORS.primary }}>{ricettaSelezionata}</h2>
            </div>
            {!dettaglio ? (
              <div style={{ textAlign: "center", padding: 60, color: COLORS.gray }}>Calcolo in corso...</div>
            ) : (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 20 }}>
                  {[
                    { label: "Costo Totale", value: `€ ${dettaglio.costo_totale?.toFixed(2)}` },
                    { label: "Porzioni", value: dettaglio.porzioni },
                    { label: "Costo/Porzione", value: `€ ${dettaglio.costo_porzione?.toFixed(3)}` },
                    { label: "Copertura", value: dettaglio.completezza },
                  ].map(({ label, value }) => (
                    <div key={label} style={{ ...STYLES.card, padding: 14, background: COLORS.grayBg }}>
                      <div style={{ fontSize: 11, color: COLORS.gray, marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.primary }}>{value}</div>
                    </div>
                  ))}
                </div>
                {dettaglio.ingredienti_mancanti?.length > 0 && (
                  <div style={{ background: "#fff7ed", border: `1px solid #fed7aa`, borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 13 }}>
                    <strong style={{ color: COLORS.warning }}>Ingredienti senza prezzo:</strong>{" "}
                    {dettaglio.ingredienti_mancanti.join(", ")}
                  </div>
                )}
                <table style={STYLES.table}>
                  <thead>
                    <tr>
                      <th style={STYLES.th}>Ingrediente</th>
                      <th style={{ ...STYLES.th, textAlign: "center" }}>Quantità</th>
                      <th style={{ ...STYLES.th, textAlign: "center" }}>U.M.</th>
                      <th style={{ ...STYLES.th, textAlign: "right" }}>€/kg</th>
                      <th style={{ ...STYLES.th, textAlign: "right", color: COLORS.primary }}>Costo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dettaglio.ingredienti?.map((ing, i) => (
                      <tr key={i} style={{ background: ing.costo == null ? "#fff7ed" : "white" }}>
                        <td style={STYLES.td}>
                          {ing.nome}
                          {ing.costo == null && (
                            <span style={{ marginLeft: 6, fontSize: 11, color: COLORS.warning }}>⚠ non trovato</span>
                          )}
                        </td>
                        <td style={{ ...STYLES.td, textAlign: "center" }}>{ing.quantita}</td>
                        <td style={{ ...STYLES.td, textAlign: "center" }}>{ing.unita}</td>
                        <td style={{ ...STYLES.td, textAlign: "right" }}>
                          {ing.prezzo_kg ? `€ ${ing.prezzo_kg.toFixed(2)}` : "—"}
                        </td>
                        <td style={{ ...STYLES.td, textAlign: "right", fontWeight: 600, color: ing.costo != null ? COLORS.primary : COLORS.gray }}>
                          {ing.costo != null ? `€ ${ing.costo.toFixed(3)}` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
