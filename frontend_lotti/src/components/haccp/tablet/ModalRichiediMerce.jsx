import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { apiError } from "../../../utils/apiError";
import { API } from "../../../utils/constants";

/**
 * ModalRichiediMerce — un UNICO modo, da qualsiasi reparto, per chiedere merce
 * al magazzino. La richiesta finisce sulla "lavagna" del magazzino (stesso
 * endpoint del bar). Niente più uscire e rientrare come "Magazzino".
 *
 * Flusso minimo: cerca → tocca il prodotto → −/+ quantità → Invia.
 */
export default function ModalRichiediMerce({ operatoreNome = "", onClose }) {
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sel, setSel] = useState(null);
  const [qta, setQta] = useState(1);
  const [unita, setUnita] = useState("collo");
  const [inviando, setInviando] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/magazzino/prodotti-unificati`, { timeout: 15000 });
        const list = Array.isArray(r.data) ? r.data : (r.data?.prodotti || r.data?.items || []);
        setProdotti(list);
      } catch (e) { toast.error(apiError(e, "Errore caricamento prodotti")); }
      finally { setLoading(false); }
    })();
  }, []);

  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];
    return prodotti.filter(p => (p.nome || "").toLowerCase().includes(q)).slice(0, 20);
  }, [search, prodotti]);

  const invia = async () => {
    if (!sel) { toast.error("Scegli un prodotto"); return; }
    setInviando(true);
    try {
      await axios.post(`${API}/magazzino-bar/richieste`, {
        prodotto_id: sel.id, quantita: Number(qta) || 1,
        unita_movimento: unita, operatore_nome: operatoreNome,
      });
      toast.success(`Richiesta inviata: ${qta} ${unita === "collo" ? "cartoni" : "pezzi"} di ${sel.nome}`);
      onClose && onClose();
    } catch (e) { toast.error(apiError(e, "Errore invio richiesta")); }
    finally { setInviando(false); }
  };

  return (
    // Popup CENTRATO (richiesta Enzo 23/07/2026: prima era un foglio
    // attaccato al fondo, appariva troppo in basso e tagliato)
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 3000, background: "rgba(0,0,0,.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "#1c2620", color: "#fff", width: "100%", maxWidth: 560, borderRadius: 22, padding: "18px 18px 24px", maxHeight: "88vh", overflowY: "auto", boxShadow: "0 20px 60px rgba(0,0,0,.5)" }}>
        {/* Intestazione */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ fontWeight: 900, fontSize: 20 }}>📦 Richiedi merce al magazzino</div>
          <button onClick={onClose} style={{ border: "none", background: "transparent", color: "#a39a87", fontSize: 26, fontWeight: 900, lineHeight: 1, cursor: "pointer" }}>×</button>
        </div>

        {!sel ? (
          <>
            <input autoFocus value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Cerca il prodotto… (es. farina, prosecco)"
              style={{ width: "100%", boxSizing: "border-box", padding: "15px 16px", borderRadius: 14, border: "1px solid #3d463c", background: "#2a3329", color: "#fff", fontSize: 17 }} />
            {loading && <div style={{ padding: 16, color: "#a39a87" }}>Carico i prodotti…</div>}
            {!loading && search && matches.length === 0 && (
              <div style={{ padding: 16, color: "#a39a87" }}>Nessun prodotto trovato per “{search}”.</div>
            )}
            {matches.map(p => (
              <button key={p.id} onClick={() => setSel(p)}
                style={{ display: "block", width: "100%", textAlign: "left", marginTop: 10, padding: "14px 16px", borderRadius: 14, border: "1px solid #3d463c", background: "#2a3329", color: "#fff", fontWeight: 800, fontSize: 16, cursor: "pointer" }}>
                {p.nome} {p.stock != null && <span style={{ color: "#7a7266", fontWeight: 700 }}>· in casa {p.stock}</span>}
              </button>
            ))}
          </>
        ) : (
          <>
            {/* Prodotto scelto */}
            <div style={{ fontWeight: 900, fontSize: 19, marginBottom: 16 }}>{sel.nome}</div>
            {/* Quantità grande */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 18, marginBottom: 18 }}>
              <button onClick={() => setQta(q => Math.max(1, (Number(q) || 1) - 1))} style={{ width: 64, height: 64, borderRadius: 18, border: "none", background: "#3d463c", color: "#fff", fontSize: 30, fontWeight: 900, cursor: "pointer" }}>−</button>
              <div style={{ minWidth: 70, textAlign: "center", fontSize: 40, fontWeight: 900 }}>{qta}</div>
              <button onClick={() => setQta(q => (Number(q) || 1) + 1)} style={{ width: 64, height: 64, borderRadius: 18, border: "none", background: "#3d463c", color: "#fff", fontSize: 30, fontWeight: 900, cursor: "pointer" }}>+</button>
            </div>
            {/* Unità */}
            <button onClick={() => setUnita(u => u === "collo" ? "pezzo" : "collo")}
              style={{ width: "100%", border: "1px solid #5c564a", background: "transparent", color: "#cfc6b4", borderRadius: 14, padding: "14px", fontWeight: 900, fontSize: 16, marginBottom: 14, cursor: "pointer" }}>
              {unita === "collo" ? "📦 Cartoni  (tocca per pezzi)" : "🔢 Pezzi  (tocca per cartoni)"}
            </button>
            {/* Azioni */}
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => { setSel(null); setQta(1); }} style={{ flex: "0 0 auto", border: "none", background: "#3d463c", color: "#fff", borderRadius: 14, padding: "16px 18px", fontWeight: 900, fontSize: 16, cursor: "pointer" }}>← Cambia</button>
              <button onClick={invia} disabled={inviando} style={{ flex: 1, border: "none", background: "#16a34a", color: "#fff", borderRadius: 14, padding: "16px", fontWeight: 900, fontSize: 18, cursor: inviando ? "wait" : "pointer" }}>
                {inviando ? "Invio…" : "📨 Invia richiesta"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
