import React, { useState, useEffect } from "react";
import { apiError } from "../../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../../utils/constants";

export function ModalAlpha({ onClose, modo = "ordine" }) {
  const isBanco = modo === "banco";
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [prodottoOrdine, setProdottoOrdine] = useState(null);
  const [cartoniOrdine, setCartoniOrdine] = useState(1);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`${API}/acquaviva/prodotti/senza-glutine`);
        setProdotti(res.data || []);
      } catch { toast.error("Errore caricamento prodotti Alpha"); }
      setLoading(false);
    };
    load();
  }, []);

  const filtrati = prodotti
    .filter(p => !search || p.nome.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));

  const aggiungiAOrdine = async () => {
    if (!prodottoOrdine || cartoniOrdine < 1) return;
    setSaving(true);
    try {
      await axios.post(`${API}/ordini-fornitori`, {
        source: "catalogo_alpha",
        reparto: "pasticceria",
        operatore: "Catalogo tablet",
        note_operatore: "Aggiunto dal catalogo",
        prodotti: [{
          prodotto_id: String(prodottoOrdine.id || prodottoOrdine.codice || prodottoOrdine.nome),
          nome: prodottoOrdine.nome,
          fornitore: "Alfa Service Srl",
          quantita: cartoniOrdine,
          unita: "CT",
          prezzo_ultimo: Number(prodottoOrdine.prezzo_acquisto_confezione || 0),
          note: ""
        }],
        ricette_da_produrre: []
      });
      toast.success(`${cartoniOrdine} CT di ${prodottoOrdine.nome} nella bozza ordine: la confermi da Ordini`);
      setProdottoOrdine(null);
      setCartoniOrdine(1);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
    setSaving(false);
  };

  const mandaAlBanco = async () => {
    if (!prodottoOrdine || cartoniOrdine < 1) return;
    setSaving(true);
    try {
      await axios.post(`${API}/vendita-banco/registra`, {
        prodotto_id: String(prodottoOrdine.id || prodottoOrdine.codice || prodottoOrdine.nome),
        prodotto_nome: prodottoOrdine.nome,
        reparto: "pasticceria",
        pezzi_prodotti: cartoniOrdine,
        foto_url: prodottoOrdine.foto_url || null,
        consumo_immediato: true,
      });
      toast.success(`${cartoniOrdine}\u00d7 ${prodottoOrdine.nome} inviato al banco`);
      setProdottoOrdine(null);
      setCartoniOrdine(1);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
    setSaving(false);
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      background: "rgba(0,0,0,0.7)", display: "flex", flexDirection: "column"
    }}>
      <div style={{
        background: "linear-gradient(135deg, var(--success-text), var(--success-dark))",
        padding: "16px 20px",
        display: "flex", alignItems: "center", justifyContent: "space-between"
      }}>
        <div>
          <h2 style={{ color: "#fff", margin: 0, fontSize: 20, fontWeight: 800 }}>{isBanco ? "Senza Glutine" : "Progetto Alpha"}</h2>
          <p style={{ color: "rgba(255,255,255,0.75)", margin: 0, fontSize: 12 }}>
            {filtrati.length} prodotti senza glutine
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span style={{ background: "rgba(255,255,255,0.2)", borderRadius: 20, padding: "4px 10px", color: "#fff", fontSize: 11, fontWeight: 700 }}>
            SENZA GLUTINE
          </span>
          <button onClick={() => { setProdottoOrdine(null); setCartoniOrdine(1); setSaving(false); onClose(); }}
            style={{
              background: "rgba(255,255,255,0.2)", border: "2px solid rgba(255,255,255,0.4)",
              color: "#fff", borderRadius: 10, padding: "8px 14px", fontWeight: 700, cursor: "pointer"
            }}>✕ Chiudi</button>
        </div>
      </div>

      <div style={{ background: "#fff", padding: "12px 16px", borderBottom: "1px solid #e5e7eb" }}>
        <input type="text" placeholder="Cerca prodotto senza glutine..."
          value={search} onChange={e => setSearch(e.target.value)}
          style={{
            width: "100%", padding: "10px 16px", borderRadius: 10,
            border: "2px solid #d1d5db", fontSize: 16, outline: "none", boxSizing: "border-box"
          }} />
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 16, background: "#f0fdf4" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: 40, color: "#9ca3af" }}>Caricamento...</div>
        ) : filtrati.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "#9ca3af" }}>
            <p style={{ fontSize: 32 }}>🌿</p>
            <p>Nessun prodotto trovato</p>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12 }}>
            {filtrati.map(prod => (
              <div key={prod.id}
                onClick={() => { setProdottoOrdine(prod); setCartoniOrdine(1); }}
                style={{
                  background: "#fff", borderRadius: 14, overflow: "hidden",
                  border: "2px solid var(--success-soft)", cursor: "pointer",
                  boxShadow: "0 2px 8px rgba(5,150,105,0.1)",
                  transition: "transform 0.12s, box-shadow 0.12s"
                }}
                onMouseDown={e => { e.currentTarget.style.transform = "scale(0.96)"; }}
                onMouseUp={e => { e.currentTarget.style.transform = "scale(1)"; }}
                onTouchStart={e => { e.currentTarget.style.transform = "scale(0.96)"; }}
                onTouchEnd={e => { e.currentTarget.style.transform = "scale(1)"; }}
              >
                <div style={{
                  background: "linear-gradient(135deg, var(--success-soft), var(--success-soft))",
                  height: 70, display: "flex", alignItems: "center",
                  justifyContent: "center", fontSize: 28
                }}>🌿</div>
                <div style={{ padding: "8px 10px 10px" }}>
                  <p style={{
                    margin: 0, fontSize: 12, fontWeight: 700, color: "#064e3b",
                    textTransform: "capitalize", lineHeight: 1.25,
                    display: "-webkit-box", WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical", overflow: "hidden"
                  }}>{prod.nome}</p>
                  <div style={{ marginTop: 4, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                    {prod.prezzo_singolo > 0 && (
                      <span style={{ fontSize: 11, color: "var(--success-dark)", fontWeight: 700 }}>
                        €{prod.prezzo_singolo.toFixed(2)}/pz
                      </span>
                    )}
                    {prod.pz_confezione > 0 && (
                      <span style={{ fontSize: 10, color: "#6b7280" }}>{prod.pz_confezione} pz/conf</span>
                    )}
                  </div>
                  {prod.allergeni?.length > 0 && (
                    <p style={{ margin: "3px 0 0", fontSize: 9, color: "var(--warning-dark)", fontWeight: 600 }}>
                      ⚠ {prod.allergeni.slice(0,2).join(", ")}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {prodottoOrdine && (
        <div style={{
          position: "absolute", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "flex-end", justifyContent: "center"
        }} onClick={e => { if (e.target === e.currentTarget) { setProdottoOrdine(null); setCartoniOrdine(1); } }}>
          <div style={{
            background: "#fff", borderRadius: "20px 20px 0 0", padding: "24px 20px",
            width: "100%", maxWidth: 460
          }}>
            <div style={{ marginBottom: 16 }}>
              <p style={{ margin: 0, fontWeight: 800, fontSize: 18, color: "#064e3b", textTransform: "capitalize" }}>
                🌿 {prodottoOrdine.nome}
              </p>
              <div style={{ marginTop: 4, display: "flex", gap: 10, flexWrap: "wrap" }}>
                {prodottoOrdine.prezzo_singolo > 0 && (
                  <span style={{ fontSize: 13, color: "var(--success-dark)", fontWeight: 700 }}>
                    €{prodottoOrdine.prezzo_singolo.toFixed(2)}/pz
                  </span>
                )}
                {prodottoOrdine.pz_confezione > 0 && (
                  <span style={{ fontSize: 12, color: "#6b7280" }}>{prodottoOrdine.pz_confezione} pz/conf</span>
                )}
              </div>
              {prodottoOrdine.allergeni?.length > 0 && (
                <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--warning-dark)" }}>
                  ⚠ Allergeni: {prodottoOrdine.allergeni.join(", ")}
                </p>
              )}
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>
                {isBanco ? "Pezzi da mandare al banco:" : "Cartoni da ordinare:"}
              </label>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <button onClick={() => setCartoniOrdine(Math.max(1, cartoniOrdine - 1))}
                  style={{ width: 44, height: 44, borderRadius: 12, border: "2px solid #e5e7eb", background: "#f9fafb", fontSize: 22, cursor: "pointer" }}>−</button>
                <input type="number" min={1} value={cartoniOrdine}
                  onChange={e => setCartoniOrdine(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{ flex: 1, textAlign: "center", fontSize: 28, fontWeight: 800, border: "2px solid #d1d5db", borderRadius: 12, padding: "6px 0", outline: "none" }} />
                <button onClick={() => setCartoniOrdine(cartoniOrdine + 1)}
                  style={{ width: 44, height: 44, borderRadius: 12, border: "2px solid #e5e7eb", background: "#f9fafb", fontSize: 22, cursor: "pointer" }}>+</button>
              </div>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => { setProdottoOrdine(null); setCartoniOrdine(1); }}
                style={{
                  flex: 1, padding: "14px", borderRadius: 12, border: "2px solid #e5e7eb",
                  background: "#f9fafb", fontSize: 14, fontWeight: 600, cursor: "pointer", color: "#6b7280"
                }}>Annulla</button>
              <button onClick={isBanco ? mandaAlBanco : aggiungiAOrdine} disabled={saving}
                style={{
                  flex: 2, padding: "14px", borderRadius: 12, border: "none",
                  background: saving ? "#9ca3af" : "linear-gradient(135deg, var(--success-text), var(--success-dark))",
                  color: "#fff", fontSize: 14, fontWeight: 800, cursor: saving ? "default" : "pointer"
                }}>
                {saving
                  ? (isBanco ? "Invio..." : "Aggiungo...")
                  : (isBanco ? `\u2615 Manda ${cartoniOrdine} pz al banco` : `\u{1F6D2} Aggiungi ${cartoniOrdine} CT alla bozza ordine`)}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ModalAlpha;
