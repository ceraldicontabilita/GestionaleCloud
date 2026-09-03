/**
 * GestioneProdottiView — Sezione centralizzata di gestione prodotti del magazzino.
 * Per ogni prodotto: flag Visualizza/Non visualizza in magazzino, categoria (menu a tendina),
 * nome normalizzato da usare. Gli override hanno priorità sul filtro automatico alimenti.
 */
import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { Search, Eye, EyeOff, Save, RotateCcw } from "lucide-react";

const WRAP = { padding: "16px", maxWidth: 900, margin: "0 auto", fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" };
const INPUT = { width: "100%", padding: "9px 12px", borderRadius: 10, border: "1px solid var(--border, #ece4d6)", fontSize: 14, background: "#fff", outline: "none" };

export default function GestioneProdottiView() {
  const [prodotti, setProdotti] = useState([]);
  const [categorie, setCategorie] = useState([]);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState("tutti"); // tutti | visibili | nascosti
  const [mostra, setMostra] = useState(120); // rendering incrementale: 1192 card insieme uccidono il telefono
  const dirtyRef = useRef({});

  useEffect(() => { const t = setTimeout(() => setDebounced(search), 250); return () => clearTimeout(t); }, [search]);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/magazzino/gestione-prodotti`, { params: debounced ? { search: debounced } : {} });
      setProdotti(r.data.prodotti || []);
      setCategorie(r.data.categorie || []);
    } catch { toast.error("Errore caricamento prodotti"); }
    finally { setLoading(false); }
  }, [debounced]);
  useEffect(() => { carica(); }, [carica]);

  const patchLocale = (key, patch) => {
    setProdotti((prev) => prev.map((p) => (p.key === key ? { ...p, ...patch } : p)));
    dirtyRef.current[key] = { ...(dirtyRef.current[key] || {}), ...patch };
  };

  const salva = async (p) => {
    const d = dirtyRef.current[p.key] || {};
    try {
      await axios.post(`${API}/magazzino/override-prodotto`, {
        key: p.key,
        nome_originale: p.nome_originale,
        visualizza: p.visualizza,
        categoria: p.categoria,
        nome_norm: (d.nome_norm !== undefined ? d.nome_norm : p.nome_norm) || "",
      });
      delete dirtyRef.current[p.key];
      toast.success("Salvato", { duration: 1200 });
      setProdotti((prev) => prev.map((x) => (x.key === p.key ? { ...x, override_manuale: true, nome_visualizzato: (x.nome_norm || x.nome_originale) } : x)));
    } catch { toast.error("Errore salvataggio"); }
  };

  const azzera = async (p) => {
    try {
      await axios.post(`${API}/magazzino/reset-override`, { key: p.key });
      delete dirtyRef.current[p.key];
      toast.success("Ripristinato automatico", { duration: 1200 });
      carica();
    } catch { toast.error("Errore"); }
  };

  const visti = prodotti.filter((p) =>
    filtro === "tutti" ? true : filtro === "visibili" ? p.visualizza : !p.visualizza
  );
  const nVis = prodotti.filter((p) => p.visualizza).length;

  return (
    <div style={WRAP}>
      <h2 style={{ fontSize: 22, fontWeight: 800, margin: "0 0 4px", color: "var(--ink,#0f172a)" }}>Gestione prodotti magazzino</h2>
      <p style={{ color: "var(--muted,#64748b)", fontSize: 13, margin: "0 0 14px" }}>
        Decidi cosa appare in magazzino, la categoria e il nome da usare.{" "}
        {loading ? "Carico l'elenco…" : `${nVis} visibili su ${prodotti.length}.`}
      </p>

      <div style={{ position: "relative", marginBottom: 10 }}>
        <Search size={17} style={{ position: "absolute", left: 12, top: 11, color: "#9aa3b2" }} />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca prodotto o fornitore…" style={{ ...INPUT, paddingLeft: 36 }} />
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {[["tutti", "Tutti"], ["visibili", "In magazzino"], ["nascosti", "Nascosti"]].map(([id, lb]) => (
          <button key={id} onClick={() => setFiltro(id)}
            style={{ padding: "7px 14px", borderRadius: 999, border: filtro === id ? "none" : "1px solid var(--border,#ece4d6)", background: filtro === id ? "var(--viola,#8a6f47)" : "#fff", color: filtro === id ? "#fff" : "var(--muted,#64748b)", fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>
            {lb}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: "center", color: "#64748b", padding: 40 }}>Carico…</div>
      ) : visti.length === 0 ? (
        <div style={{ textAlign: "center", color: "#64748b", padding: 40 }}>Nessun prodotto.</div>
      ) : (
        visti.slice(0, mostra).map((p) => {
          const dirty = !!dirtyRef.current[p.key];
          return (
            <div key={p.key} style={{ background: "#fff", border: "1px solid var(--border,#ece4d6)", borderRadius: 14, padding: 12, marginBottom: 10, opacity: p.visualizza ? 1 : 0.62 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 11, color: "#9aa3b2", textTransform: "uppercase", fontWeight: 700, marginBottom: 3 }}>
                    {p.source === "bar" ? "BAR" : "FATTURA"}{p.fornitore ? " · " + p.fornitore : ""}
                  </div>
                  <div style={{ fontSize: 13.5, fontWeight: 700, color: "#1f2937", lineHeight: 1.3, wordBreak: "break-word" }}>{p.nome_originale}</div>
                </div>
                <button onClick={() => patchLocale(p.key, { visualizza: !p.visualizza })}
                  title={p.visualizza ? "In magazzino" : "Nascosto"}
                  style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 6, padding: "8px 12px", borderRadius: 10, border: "none", cursor: "pointer", fontWeight: 800, fontSize: 12.5, background: p.visualizza ? "#E7F8F2" : "#FDECEA", color: p.visualizza ? "#067a57" : "#c0392b" }}>
                  {p.visualizza ? <Eye size={15} /> : <EyeOff size={15} />}
                  {p.visualizza ? "In magazzino" : "Nascosto"}
                </button>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                <div style={{ flex: "1 1 180px" }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: "#64748b" }}>Categoria</label>
                  <select value={p.categoria || "Altro"} onChange={(e) => patchLocale(p.key, { categoria: e.target.value })} style={{ ...INPUT, marginTop: 3 }}>
                    {categorie.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div style={{ flex: "1 1 220px" }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: "#64748b" }}>Nome da usare (normalizzazione)</label>
                  <input defaultValue={p.nome_norm || ""} placeholder={p.nome_originale}
                    onChange={(e) => patchLocale(p.key, { nome_norm: e.target.value })} style={{ ...INPUT, marginTop: 3 }} />
                </div>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 10, justifyContent: "flex-end" }}>
                {p.override_manuale && (
                  <button onClick={() => azzera(p)} style={{ display: "flex", alignItems: "center", gap: 5, padding: "8px 12px", borderRadius: 10, border: "1px solid var(--border,#ece4d6)", background: "#fff", color: "#64748b", fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>
                    <RotateCcw size={14} /> Auto
                  </button>
                )}
                <button onClick={() => salva(p)} disabled={!dirty}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, border: "none", background: dirty ? "var(--viola,#8a6f47)" : "#ece4d6", color: dirty ? "#fff" : "#9aa3b2", fontWeight: 800, fontSize: 12.5, cursor: dirty ? "pointer" : "default" }}>
                  <Save size={14} /> Salva
                </button>
              </div>
            </div>
          );
        })
      )}
      {!loading && visti.length > mostra && (
        <button onClick={() => setMostra((m) => m + 200)}
          style={{ width: "100%", padding: "12px", borderRadius: 12, border: "1px solid var(--border,#ece4d6)", background: "#fff", fontWeight: 800, color: "var(--muted,#64748b)", cursor: "pointer" }}>
          Mostra altri ({visti.length - mostra} rimasti)
        </button>
      )}
    </div>
  );
}
