/**
 * tablet/PannelloReparti.jsx — Modal gestione assegnazione reparti alle ricette
 */
import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../../utils/constants";

function PannelloReparti({ onClose }) {
  const [ricette, setRicette] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchAdmin, setSearchAdmin] = useState("");

  const loadRicette = async () => {
    const res = await axios.get(`${API}/ricette?limit=200`);
    setRicette(res.data);
  };

  useEffect(() => { loadRicette(); }, []);

  const handleAutoAssegna = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/ricette/auto-assegna-reparti`);
      toast.success(`Auto-categorizzazione: ${res.data.pasticceria} pasticceria, ${res.data.rosticceria} rosticceria`);
      await loadRicette();
    } catch { toast.error("Errore auto-categorizzazione"); }
    setLoading(false);
  };

  const handleCambiaReparto = async (id, nuovoReparto) => {
    try {
      await axios.put(`${API}/ricette/${id}/reparto?reparto=${nuovoReparto}`);
      setRicette(prev => prev.map(r => r.id === id ? { ...r, reparto: nuovoReparto } : r));
    } catch { toast.error("Errore aggiornamento reparto"); }
  };

  const filtrate = ricette.filter(r => !searchAdmin || r.nome?.toLowerCase().includes(searchAdmin.toLowerCase()));
  const colorePill = { pasticceria: "var(--warning-soft)", rosticceria: "var(--success-soft)", bar: "#efe7db", altro: "#f0ebe0" };
  const testoPill = { pasticceria: "var(--warning-text)", rosticceria: "var(--success-dark)", bar: "#7c4a02", altro: "#5c564a" };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 2000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: "#fff", borderRadius: 20, width: "100%", maxWidth: 600, maxHeight: "90vh", overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "20px 24px 16px", borderBottom: "1px solid #f0ebe0", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#2a3329" }}>Gestione Reparti</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={handleAutoAssegna} disabled={loading} style={{
              padding: "8px 16px", borderRadius: 10, border: "none", background: "#a8854f",
              color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer"
            }}>
              {loading ? "..." : "Auto-assegna"}
            </button>
            <button onClick={onClose} style={{
              padding: "8px 14px", borderRadius: 10, border: "1px solid #e6e0d4",
              background: "#faf7f0", cursor: "pointer", fontSize: 14, color: "#7a7266"
            }}>✕</button>
          </div>
        </div>
        <div style={{ padding: "12px 24px", borderBottom: "1px solid #f0ebe0" }}>
          <input type="text" value={searchAdmin} onChange={(e) => setSearchAdmin(e.target.value)}
            placeholder="Cerca ricetta..."
            style={{ width: "100%", padding: "8px 14px", borderRadius: 10, border: "1px solid #e6e0d4", fontSize: 14, boxSizing: "border-box" }} />
        </div>
        <div style={{ overflowY: "auto", flex: 1, padding: "8px 24px 20px" }}>
          {filtrate.map(r => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid #faf7f0" }}>
              <span style={{ fontSize: 14, fontWeight: 500, textTransform: "capitalize", color: "#2a3329", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.nome}</span>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                {["pasticceria", "rosticceria", "bar", "altro"].map(rp => (
                  <button key={rp} onClick={() => handleCambiaReparto(r.id, rp)} style={{
                    padding: "4px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: "pointer",
                    border: "2px solid",
                    borderColor: r.reparto === rp ? testoPill[rp] : "transparent",
                    background: r.reparto === rp ? colorePill[rp] : "#faf7f0",
                    color: r.reparto === rp ? testoPill[rp] : "#a39a87",
                    transition: "all 0.15s"
                  }}>
                    {rp === "pasticceria" ? "Past." : rp === "rosticceria" ? "Rost." : rp === "bar" ? "Bar" : "Altro"}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default PannelloReparti;
