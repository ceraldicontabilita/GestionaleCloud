import { useState, useEffect } from "react";
import api from "../api";
import PageLayout from "../components/PageLayout";
import { COLORS, STYLES, SPACING, button, badge } from "../lib/utils";

const FORM_VUOTO = {
  nome: "", categoria: "", descrizione: "", fonte: "interno",
  fornitore: "", prezzo_vendita: "", costo_produzione: "",
  iva: 10, pezzi_cartone: "", pezzi_per_ricetta: "",
  peso_pezzo_g: "", attivo: true, visibile_tablet: true,
  allergeni: [], ingredienti: "", stagionale: false,
};

export default function ProdottiVendita() {
  const [prodotti, setProdotti] = useState([]);
  const [categorie, setCategorie] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(FORM_VUOTO);
  const [editId, setEditId] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        api.get("/api/cucina/prodotti-vendita/lista?solo_attivi=false&limit=200"),
        api.get("/api/cucina/prodotti-vendita/categorie"),
      ]);
      setProdotti(r1.data);
      setCategorie(r2.data);
    } catch (e) { setErr("Errore caricamento"); }
    finally { setLoading(false); }
  }

  function apriNuovo() {
    setForm(FORM_VUOTO);
    setEditId(null);
    setModalOpen(true);
  }

  function apriModifica(p) {
    setForm({
      nome: p.nome || "", categoria: p.categoria || "",
      descrizione: p.descrizione || "", fonte: p.fonte || "interno",
      fornitore: p.fornitore || "",
      prezzo_vendita: p.prezzo_vendita || "",
      costo_produzione: p.costo_produzione || "",
      iva: p.iva || 10, pezzi_cartone: p.pezzi_cartone || "",
      pezzi_per_ricetta: p.pezzi_per_ricetta || "",
      peso_pezzo_g: p.peso_pezzo_g || "",
      attivo: p.attivo !== false, visibile_tablet: p.visibile_tablet !== false,
      allergeni: p.allergeni || [], ingredienti: p.ingredienti || "",
      stagionale: p.stagionale || false,
    });
    setEditId(p.id);
    setModalOpen(true);
  }

  async function salva() {
    if (!form.nome.trim()) { setErr("Il nome è obbligatorio"); return; }
    setSalvando(true);
    try {
      const payload = {
        ...form,
        prezzo_vendita: parseFloat(form.prezzo_vendita) || 0,
        costo_produzione: parseFloat(form.costo_produzione) || 0,
        iva: parseFloat(form.iva) || 10,
        pezzi_cartone: parseInt(form.pezzi_cartone) || null,
        pezzi_per_ricetta: parseInt(form.pezzi_per_ricetta) || null,
        peso_pezzo_g: parseFloat(form.peso_pezzo_g) || null,
      };
      if (editId) {
        await api.put(`/api/cucina/prodotti-vendita/${editId}`, payload);
      } else {
        await api.post("/api/cucina/prodotti-vendita/", payload);
      }
      setMsg(editId ? "Prodotto aggiornato!" : "Prodotto creato!");
      setModalOpen(false);
      loadAll();
      setTimeout(() => setMsg(""), 3000);
    } catch (e) { setErr("Errore salvataggio"); }
    finally { setSalvando(false); }
  }

  async function eliminaProdotto(id) {
    if (!window.confirm("Eliminare questo prodotto?")) return;
    try {
      await api.delete(`/api/cucina/prodotti-vendita/${id}`);
      setMsg("Prodotto eliminato");
      setProdotti(prev => prev.filter(p => p.id !== id));
      setTimeout(() => setMsg(""), 3000);
    } catch (e) { setErr("Errore eliminazione"); }
  }

  const prodottiFiltrati = prodotti.filter(p => {
    const matchS = !search || p.nome?.toLowerCase().includes(search.toLowerCase());
    const matchC = !filtroCategoria || p.categoria === filtroCategoria;
    return matchS && matchC;
  });

  const attivi = prodotti.filter(p => p.attivo !== false).length;

  return (
    <PageLayout>
      <div style={STYLES.page}>
        {/* Header */}
        <div style={STYLES.header} data-testid="prodotti-vendita-header">
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Prodotti Vendita</h1>
            <div style={{ fontSize: 13, opacity: 0.8, marginTop: 4 }}>
              {prodotti.length} prodotti · {attivi} attivi
            </div>
          </div>
          <button style={button("success")} onClick={apriNuovo} data-testid="btn-nuovo-prodotto">
            + Nuovo Prodotto
          </button>
        </div>

        {err && <div style={{ background: "#fee2e2", color: COLORS.danger, padding: 12, borderRadius: 8, marginBottom: 12, fontSize: 13 }}>{err}</div>}
        {msg && <div style={{ background: "#dcfce7", color: "#166534", padding: 12, borderRadius: 8, marginBottom: 12, fontSize: 13 }}>{msg}</div>}

        {/* Filtri */}
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <input
            style={{ ...STYLES.input, maxWidth: 280 }}
            placeholder="Cerca prodotto..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            data-testid="search-prodotti"
          />
          <select
            style={{ ...STYLES.select, maxWidth: 200 }}
            value={filtroCategoria}
            onChange={e => setFiltroCategoria(e.target.value)}
            data-testid="filtro-categoria"
          >
            <option value="">Tutte le categorie</option>
            {categorie.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: 60, color: COLORS.gray }}>Caricamento...</div>
        ) : (
          <div style={STYLES.card}>
            <table style={STYLES.table}>
              <thead>
                <tr>
                  <th style={STYLES.th}>Nome</th>
                  <th style={STYLES.th}>Categoria</th>
                  <th style={STYLES.th}>Fonte</th>
                  <th style={{ ...STYLES.th, textAlign: "right" }}>Costo</th>
                  <th style={{ ...STYLES.th, textAlign: "right" }}>Prezzo</th>
                  <th style={{ ...STYLES.th, textAlign: "right" }}>Margine</th>
                  <th style={{ ...STYLES.th, textAlign: "center" }}>Stato</th>
                  <th style={{ ...STYLES.th, textAlign: "center" }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {prodottiFiltrati.map(p => {
                  const margine = p.margine_percentuale || 0;
                  const margineColor = margine >= 40 ? COLORS.success : margine >= 20 ? COLORS.warning : COLORS.danger;
                  return (
                    <tr key={p.id} data-testid={`riga-pv-${p.id}`}>
                      <td style={STYLES.td}><strong>{p.nome}</strong></td>
                      <td style={STYLES.td}>{p.categoria || "—"}</td>
                      <td style={STYLES.td}>{p.fonte || "—"}</td>
                      <td style={{ ...STYLES.td, textAlign: "right" }}>
                        {p.costo_produzione > 0 ? `€ ${Number(p.costo_produzione).toFixed(3)}` : "—"}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "right", fontWeight: 600 }}>
                        {p.prezzo_vendita > 0 ? `€ ${Number(p.prezzo_vendita).toFixed(2)}` : "—"}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "right", fontWeight: 700, color: margineColor }}>
                        {margine > 0 ? `${margine.toFixed(1)}%` : "—"}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "center" }}>
                        {p.attivo !== false
                          ? <span style={{ ...badge("success"), fontSize: 11 }}>Attivo</span>
                          : <span style={{ ...badge("error"), fontSize: 11 }}>Inattivo</span>}
                      </td>
                      <td style={{ ...STYLES.td, textAlign: "center" }}>
                        <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
                          <button
                            style={{ ...button("outline"), padding: "4px 10px", fontSize: 12 }}
                            onClick={() => apriModifica(p)}
                            data-testid={`btn-modifica-${p.id}`}
                          >Modifica</button>
                          <button
                            style={{ ...button("danger"), padding: "4px 10px", fontSize: 12 }}
                            onClick={() => eliminaProdotto(p.id)}
                            data-testid={`btn-elimina-${p.id}`}
                          >Elimina</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {prodottiFiltrati.length === 0 && (
              <div style={{ textAlign: "center", padding: 40, color: COLORS.gray }}>Nessun prodotto trovato</div>
            )}
          </div>
        )}

        {/* Modal Nuovo/Modifica */}
        {modalOpen && (
          <div
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
            onClick={() => setModalOpen(false)}
          >
            <div
              style={{ background: COLORS.white, borderRadius: 12, padding: SPACING.xl, maxWidth: 560, width: "95%", maxHeight: "90vh", overflowY: "auto" }}
              onClick={e => e.stopPropagation()}
              data-testid="modal-prodotto"
            >
              <h2 style={{ margin: "0 0 16px", color: COLORS.primary }}>
                {editId ? "Modifica Prodotto" : "Nuovo Prodotto"}
              </h2>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {[
                  { key: "nome", label: "Nome *", type: "text", full: true },
                  { key: "categoria", label: "Categoria", type: "text" },
                  { key: "fonte", label: "Fonte", type: "select", opts: ["interno", "fornitore", "acquaviva"] },
                  { key: "fornitore", label: "Fornitore", type: "text" },
                  { key: "prezzo_vendita", label: "Prezzo Vendita (€)", type: "number" },
                  { key: "costo_produzione", label: "Costo Produzione (€)", type: "number" },
                  { key: "iva", label: "IVA (%)", type: "number" },
                  { key: "peso_pezzo_g", label: "Peso pezzo (g)", type: "number" },
                  { key: "pezzi_cartone", label: "Pezzi/cartone", type: "number" },
                  { key: "pezzi_per_ricetta", label: "Pezzi/ricetta", type: "number" },
                ].map(({ key, label, type, opts, full }) => (
                  <div key={key} style={{ gridColumn: full ? "1 / -1" : "auto" }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: COLORS.gray, display: "block", marginBottom: 4 }}>{label}</label>
                    {type === "select" ? (
                      <select
                        style={STYLES.select}
                        value={form[key]}
                        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                      >
                        {opts.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input
                        style={STYLES.input}
                        type={type}
                        value={form[key]}
                        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                        data-testid={`input-${key}`}
                      />
                    )}
                  </div>
                ))}
                <div style={{ gridColumn: "1 / -1" }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: COLORS.gray, display: "block", marginBottom: 4 }}>Ingredienti</label>
                  <textarea
                    style={{ ...STYLES.input, height: 64, resize: "vertical" }}
                    value={form.ingredienti}
                    onChange={e => setForm(f => ({ ...f, ingredienti: e.target.value }))}
                  />
                </div>
                <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                  <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, cursor: "pointer" }}>
                    <input type="checkbox" checked={form.attivo} onChange={e => setForm(f => ({ ...f, attivo: e.target.checked }))} />
                    Attivo
                  </label>
                  <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, cursor: "pointer" }}>
                    <input type="checkbox" checked={form.visibile_tablet} onChange={e => setForm(f => ({ ...f, visibile_tablet: e.target.checked }))} />
                    Visibile Tablet
                  </label>
                </div>
              </div>
              {err && <div style={{ background: "#fee2e2", color: COLORS.danger, padding: 10, borderRadius: 6, marginTop: 12, fontSize: 13 }}>{err}</div>}
              <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 16 }}>
                <button style={button("outline")} onClick={() => setModalOpen(false)}>Annulla</button>
                <button
                  style={button("primary")}
                  onClick={salva}
                  disabled={salvando}
                  data-testid="btn-salva-prodotto"
                >{salvando ? "Salvataggio..." : "Salva"}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
