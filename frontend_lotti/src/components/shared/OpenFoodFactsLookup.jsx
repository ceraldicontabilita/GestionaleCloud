import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Search, X } from "lucide-react";
import { API } from "@/utils/constants";

/**
 * Lookup Open Food Facts. Suggerisce nome/ingredienti/allergeni da confermare.
 * Props: queryIniziale, onPick(nome), onClose
 */
export default function OpenFoodFactsLookup({ queryIniziale = "", onPick, onClose }) {
  const [q, setQ] = useState(queryIniziale);
  const [loading, setLoading] = useState(false);
  const [risultati, setRisultati] = useState([]);
  const [fatto, setFatto] = useState(false);

  const cerca = async () => {
    const term = q.trim();
    if (term.length < 2) { toast.error("Scrivi almeno 2 lettere"); return; }
    setLoading(true);
    try {
      const r = await axios.get(`${API}/ingredienti/openfoodfacts`, { params: { q: term }, timeout: 15000 });
      setRisultati(r.data?.risultati || []);
      setFatto(true);
    } catch {
      toast.error("Open Food Facts non raggiungibile, riprova");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", display: "grid", placeItems: "center", zIndex: 1000, padding: 16 }}>
      <div style={{ width: "min(560px, 96vw)", maxHeight: "86vh", overflow: "auto", background: "#fff", borderRadius: 16, padding: 18 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <h3 style={{ margin: 0, fontWeight: 800, color: "#3f5a4e" }}>Cerca su Open Food Facts</h3>
          <button onClick={onClose} style={{ border: "none", background: "transparent", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <p style={{ margin: "0 0 12px", fontSize: 12, color: "#9a917f" }}>
          Dati inseriti dalla community: usali come suggerimento e <b>conferma sempre</b> ingredienti e allergeni in etichetta.
        </p>
        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") cerca(); }}
            placeholder="es. nutella, farina manitoba, latte intero…"
            style={{ flex: 1, padding: "10px 12px", border: "1px solid #e6e0d4", borderRadius: 10, fontSize: 14 }}
          />
          <button onClick={cerca} disabled={loading}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "10px 14px", background: "#5b7a6b", color: "#fff", border: "none", borderRadius: 10, fontWeight: 700, cursor: "pointer" }}>
            <Search size={16} /> {loading ? "…" : "Cerca"}
          </button>
        </div>

        {fatto && risultati.length === 0 && !loading && (
          <div style={{ textAlign: "center", color: "#9a917f", padding: 20 }}>Nessun risultato.</div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {risultati.map((r, i) => (
            <div key={i} style={{ border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
              <div style={{ fontWeight: 700, color: "#2a3329" }}>{r.nome}</div>
              {r.marca ? <div style={{ fontSize: 12, color: "#9a917f" }}>{r.marca}</div> : null}
              {r.allergeni && r.allergeni.length ? (
                <div style={{ fontSize: 12, color: "#b45309", marginTop: 4 }}>Allergeni (da confermare): {r.allergeni.join(", ")}</div>
              ) : null}
              {r.ingredienti ? (
                <div style={{ fontSize: 12, color: "#555", marginTop: 4, maxHeight: 60, overflow: "auto" }}>{r.ingredienti}</div>
              ) : null}
              <button
                onClick={() => { onPick && onPick(r.nome); onClose && onClose(); }}
                style={{ marginTop: 8, padding: "6px 12px", background: "#5b7a6b", color: "#fff", border: "none", borderRadius: 8, fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
                Usa questo nome
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
