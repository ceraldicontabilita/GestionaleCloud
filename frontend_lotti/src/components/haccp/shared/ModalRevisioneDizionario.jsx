import { useState, useEffect, useCallback } from "react";
import { apiError } from "../../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { X, Check, Edit2, BookOpen, RefreshCw } from "lucide-react";
import { API } from "../../../utils/constants";

const NAVY = "#3f5a4e";
const SAGE = "#5b7a6b";
const CREAM = "#faf7f0";
const LINE = "#e6e0d4";

const CATEGORIE = [
  "Farine e Cereali", "Latticini e Grassi", "Uova", "Frutta Secca",
  "Frutta e Verdura", "Dolcificanti", "Aromi", "Condimenti",
  "Conserve e Condimenti", "Cioccolato e Cacao", "Lieviti e Addensanti",
  "Alcolici e Liquori", "Bevande", "Carne e Salumi", "Pesce",
  "Varie Alimentari", "Non Alimentare",
];

/**
 * Modal per revisionare e correggere a mano le associazioni
 * nome commerciale → nome usuale del dizionario.
 */
export default function ModalRevisioneDizionario({ onClose }) {
  const [tab, setTab] = useState("revisione");
  const [daRevisionare, setDaRevisionare] = useState([]);
  const [nomiUsuali, setNomiUsuali] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ nome_canc: "", categoria: "" });

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [rev, usuali] = await Promise.all([
        axios.get(`${API}/normalizzazione/da-revisionare?limit=100`),
        axios.get(`${API}/normalizzazione/nomi-usuali`),
      ]);
      setDaRevisionare(rev.data?.mapping || []);
      setNomiUsuali(usuali.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const salvaCorrezione = async (descKey) => {
    if (!form.nome_canc.trim()) { toast.error("Inserisci il nome usuale"); return; }
    try {
      const r = await axios.post(`${API}/normalizzazione/correggi-mapping`, {
        descrizione_key: descKey,
        nome_canc: form.nome_canc.trim(),
        categoria: form.categoria,
      });
      toast.success(`Corretto · ${r.data.prodotti_aggiornati || 0} prodotti aggiornati`);
      setEditing(null);
      setForm({ nome_canc: "", categoria: "" });
      carica();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,0.5)", backdropFilter: "blur(3px)", zIndex: 320, display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}
      onClick={onClose}
    >
      <div
        style={{ background: "#fffefb", borderRadius: 18, width: "100%", maxWidth: 560, height: "100%", maxHeight: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${LINE}`, display: "flex", alignItems: "center", gap: 10 }}>
          <BookOpen size={18} color={SAGE} />
          <span style={{ fontWeight: 600, fontSize: 17, flex: 1, color: NAVY, fontFamily: "'Fraunces', Georgia, serif" }}>
            Dizionario nomi prodotti
          </span>
          <button onClick={carica} style={{ background: "none", border: "none", cursor: "pointer", color: "#9aa593" }}>
            <RefreshCw size={16} />
          </button>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#9aa593" }}>
            <X size={22} />
          </button>
        </div>

        <div style={{ display: "flex", borderBottom: `1px solid ${LINE}` }}>
          {[
            { id: "revisione", l: `Da rivedere (${daRevisionare.length})` },
            { id: "usuali", l: `Nomi usuali (${nomiUsuali.length})` },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                flex: 1, padding: "12px", border: "none", cursor: "pointer",
                background: tab === t.id ? CREAM : "transparent",
                color: tab === t.id ? NAVY : "#6b7669",
                fontWeight: tab === t.id ? 700 : 500, fontSize: 13, fontFamily: "inherit",
                borderBottom: tab === t.id ? `2px solid ${SAGE}` : "2px solid transparent",
              }}
            >
              {t.l}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 16, background: CREAM }}>
          {loading && <div style={{ textAlign: "center", color: "#9aa593", paddingTop: 40 }}>Caricamento...</div>}

          {!loading && tab === "revisione" && (
            <>
              {daRevisionare.length === 0 && (
                <div style={{ textAlign: "center", color: "#9aa593", padding: "40px 16px" }}>
                  <Check size={40} style={{ opacity: 0.3, marginBottom: 10 }} />
                  <p style={{ fontSize: 14 }}>Nessun nome da rivedere. Dizionario in ordine.</p>
                </div>
              )}
              {daRevisionare.map((m, i) => {
                const key = m.descrizione_key;
                const isEdit = editing === key;
                return (
                  <div key={i} style={{ background: "#fffefb", border: `1px solid ${LINE}`, borderRadius: 12, padding: 14, marginBottom: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: NAVY, marginBottom: 4 }}>
                      {m.descrizione_originale || m.descrizione_key}
                    </div>
                    <div style={{ fontSize: 12, color: "#6b7669", marginBottom: 10 }}>
                      Attuale: <b>{m.nome_canc || "—"}</b>
                      {m.categoria && <span> · {m.categoria}</span>}
                      {m.fonte && <span style={{ marginLeft: 6, fontSize: 10, background: "#e8efe9", color: SAGE, padding: "1px 6px", borderRadius: 4 }}>{m.fonte}</span>}
                    </div>

                    {isEdit ? (
                      <div style={{ display: "grid", gap: 8 }}>
                        <input
                          value={form.nome_canc}
                          onChange={(e) => setForm((f) => ({ ...f, nome_canc: e.target.value }))}
                          placeholder="Nome usuale corretto (es. Margarina)"
                          style={{ padding: "9px 11px", border: `1px solid ${LINE}`, borderRadius: 8, fontSize: 13, fontFamily: "inherit", outline: "none" }}
                          autoFocus
                        />
                        <select
                          value={form.categoria}
                          onChange={(e) => setForm((f) => ({ ...f, categoria: e.target.value }))}
                          style={{ padding: "9px 11px", border: `1px solid ${LINE}`, borderRadius: 8, fontSize: 13, fontFamily: "inherit", background: "#fff" }}
                        >
                          <option value="">— categoria —</option>
                          {CATEGORIE.map((c) => <option key={c}>{c}</option>)}
                        </select>
                        <div style={{ display: "flex", gap: 8 }}>
                          <button onClick={() => { setEditing(null); setForm({ nome_canc: "", categoria: "" }); }} style={{ flex: 1, padding: "9px", border: `1px solid ${LINE}`, borderRadius: 8, background: "#fff", color: "#6b7669", fontWeight: 600, fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Annulla</button>
                          <button onClick={() => salvaCorrezione(key)} style={{ flex: 2, padding: "9px", border: "none", borderRadius: 8, background: SAGE, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>
                            <Check size={14} style={{ display: "inline", marginRight: 4 }} /> Salva
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => { setEditing(key); setForm({ nome_canc: m.nome_canc || "", categoria: m.categoria || "" }); }}
                        style={{ padding: "7px 14px", border: `1px solid ${SAGE}`, borderRadius: 8, background: "#fff", color: SAGE, fontWeight: 600, fontSize: 12, cursor: "pointer", fontFamily: "inherit", display: "flex", alignItems: "center", gap: 5 }}
                      >
                        <Edit2 size={13} /> Correggi
                      </button>
                    )}
                  </div>
                );
              })}
            </>
          )}

          {!loading && tab === "usuali" && (
            <>
              {nomiUsuali.sort((a, b) => (b.prodotti_mappati || 0) - (a.prodotti_mappati || 0)).map((u, i) => (
                <div key={i} style={{ background: "#fffefb", border: `1px solid ${LINE}`, borderRadius: 10, padding: "10px 14px", marginBottom: 6, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: NAVY }}>{u.nome_usuale}</div>
                    {u.categoria && <div style={{ fontSize: 11, color: "#9aa593" }}>{u.categoria}</div>}
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: SAGE, background: "#e8efe9", padding: "3px 10px", borderRadius: 20, whiteSpace: "nowrap" }}>
                    {u.prodotti_mappati} prod.
                  </span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
