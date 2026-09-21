import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { apiError } from "../../../utils/apiError";
import { API } from "../../../utils/constants";
import { norm } from "../../../utils/textNormalize";

export function prodottiRichiedibili(prodotti, destinazione) {
  if (destinazione === "lavagna") return prodotti.filter(p => p.source === "bar");
  const perNome = new Map();
  prodotti.forEach(prodotto => {
    const chiave = norm(prodotto.nome || "");
    if (chiave && (!perNome.has(chiave) || prodotto.source === "bar")) perNome.set(chiave, prodotto);
  });
  return [...perNome.values()];
}

/** Una richiesta con destinazione esplicita, accessibile da ogni reparto. */
export default function ModalRichiediMerce({ operatoreNome = "", reparto = "", onClose }) {
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sel, setSel] = useState(null);
  const [qta, setQta] = useState(1);
  const [unita, setUnita] = useState("collo");
  const [inviando, setInviando] = useState(false);
  const [destinazione, setDestinazione] = useState("lavagna");

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
    const q = norm(search.trim());
    if (!q) return [];
    const richiedibili = prodottiRichiedibili(prodotti, destinazione);
    return richiedibili.filter(p => norm(p.nome || "").includes(q)).slice(0, 20);
  }, [search, prodotti, destinazione]);

  const invia = async () => {
    if (!sel) { toast.error("Scegli un prodotto"); return; }
    setInviando(true);
    try {
      if (destinazione === "lavagna") {
        await axios.post(`${API}/magazzino-bar/richieste`, {
          prodotto_id: sel.id, quantita: Number(qta) || 1,
          unita_movimento: unita, operatore_nome: operatoreNome,
        });
        toast.success(`${sel.nome}: richiesta sulla lavagna del magazzino`);
      } else {
        await axios.post(`${API}/ordini-fornitori/carrello-sospesi/richieste`, {
          prodotto_id: sel.id, nome: sel.nome, quantita: Number(qta) || 1,
          unita: sel.unita || "pz", fornitore: sel.fornitore || "",
          richiesto_da: operatoreNome, reparto,
        });
        toast.success(`${sel.nome}: richiesta inviata al carrello ordini del titolare`);
      }
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
          <div style={{ fontWeight: 900, fontSize: 20 }}>📦 Richiedi merce</div>
          <button onClick={onClose} style={{ border: "none", background: "transparent", color: "#a39a87", fontSize: 26, fontWeight: 900, lineHeight: 1, cursor: "pointer" }}>×</button>
        </div>

        <div role="group" aria-label="Destinazione richiesta" style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:14}}>
          {[["lavagna","Lavagna magazzino","Consegna dalla scorta"],["carrello","Carrello ordini","Il titolare valuta l'acquisto"]].map(([valore,titolo,descrizione]) => (
            <button key={valore} type="button" aria-pressed={destinazione===valore}
              onClick={() => { setDestinazione(valore); setSel(null); setQta(1); }}
              style={{border:`2px solid ${destinazione===valore?"#86efac":"#3d463c"}`,borderRadius:12,background:destinazione===valore?"#314739":"#2a3329",color:"#fff",padding:"10px 8px",textAlign:"left",cursor:"pointer",fontFamily:"inherit"}}>
              <strong style={{display:"block",fontSize:13}}>{titolo}</strong>
              <small style={{display:"block",color:"#cfc6b4",marginTop:3}}>{descrizione}</small>
            </button>
          ))}
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
            {destinazione === "lavagna" && <button onClick={() => setUnita(u => u === "collo" ? "pezzo" : "collo")}
              style={{ width: "100%", border: "1px solid #5c564a", background: "transparent", color: "#cfc6b4", borderRadius: 14, padding: "14px", fontWeight: 900, fontSize: 16, marginBottom: 14, cursor: "pointer" }}>
              {unita === "collo" ? "📦 Cartoni  (tocca per pezzi)" : "🔢 Pezzi  (tocca per cartoni)"}
            </button>}
            {destinazione === "carrello" && <div style={{color:"#cfc6b4",textAlign:"center",fontSize:14,marginBottom:14}}>Quantità in {sel.unita || "pezzi"}. Il titolare potrà modificarla nel carrello.</div>}
            {/* Azioni */}
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => { setSel(null); setQta(1); }} style={{ flex: "0 0 auto", border: "none", background: "#3d463c", color: "#fff", borderRadius: 14, padding: "16px 18px", fontWeight: 900, fontSize: 16, cursor: "pointer" }}>← Cambia</button>
              <button onClick={invia} disabled={inviando} style={{ flex: 1, border: "none", background: "#16a34a", color: "#fff", borderRadius: 14, padding: "16px", fontWeight: 900, fontSize: 18, cursor: inviando ? "wait" : "pointer" }}>
                {inviando ? "Invio…" : destinazione === "lavagna" ? "📨 Invia alla lavagna" : "🛒 Invia al carrello ordini"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
