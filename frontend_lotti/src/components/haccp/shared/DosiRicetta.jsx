import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";

// Unico calcolo di dose usato dalla scheda #ricette e dalle card di reparto.
// Il server scala gli ingredienti; qui non si salva la ricetta ufficiale.
export default function DosiRicetta({ ricetta }) {
  const [moltiplicatore, setMoltiplicatore] = useState("1");
  const [calcolata, setCalcolata] = useState(null);
  const [errore, setErrore] = useState("");
  const dettaglio = Array.isArray(ricetta?.ingredienti_dettaglio) ? ricetta.ingredienti_dettaglio : [];
  const soliNomi = Array.isArray(ricetta?.ingredienti) ? ricetta.ingredienti : [];

  useEffect(() => {
    setMoltiplicatore("1");
    setCalcolata(null);
    setErrore("");
  }, [ricetta?.id]);

  useEffect(() => {
    if (!ricetta?.id || dettaglio.length === 0) return;
    const valore = Number(moltiplicatore);
    if (!Number.isFinite(valore) || valore <= 0 || valore > 1000) {
      setCalcolata(null);
      setErrore("Inserisci un moltiplicatore maggiore di zero e al massimo 1000.");
      return;
    }
    let attivo = true;
    const timer = setTimeout(() => {
      axios.post(`${API}/food-cost/ricetta/${ricetta.id}/dose-produzione`, { moltiplicatore: valore })
        .then(({ data }) => { if (attivo) { setCalcolata(data); setErrore(""); } })
        .catch((e) => { if (attivo) { setCalcolata(null); setErrore(apiError(e, "Dose non calcolabile")); } });
    }, 200);
    return () => { attivo = false; clearTimeout(timer); };
  }, [ricetta?.id, dettaglio.length, moltiplicatore]);

  const cambia = (valore) => { setCalcolata(null); setMoltiplicatore(String(valore)); };
  const ingredienti = calcolata?.ingredienti || dettaglio;
  const righe = ingredienti.length ? ingredienti.map((i) => ({
    nome: i?.nome || "Ingrediente",
    dose: [i?.quantita, i?.unita_misura || i?.unita].filter((v) => v !== null && v !== undefined && v !== "").join(" "),
  })) : soliNomi.map((i) => ({ nome: typeof i === "string" ? i : i?.nome || "Ingrediente", dose: "" }));

  return <div>
    {dettaglio.length > 0 && <div style={{ background: "#fff", border: "1px solid #e6e0d4", borderRadius: 12, padding: 12, marginBottom: 12 }}>
      <label htmlFor={`moltiplicatore-${ricetta.id}`} style={{ fontWeight: 800 }}>Moltiplicatore della dose</label>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
        <button onClick={() => cambia(Math.max(0.1, (Number(moltiplicatore) || 1) - 0.5))} aria-label="Riduci dose" style={{ minWidth: 44, minHeight: 44 }}>−</button>
        <input id={`moltiplicatore-${ricetta.id}`} type="number" min="0.1" max="1000" step="0.1" value={moltiplicatore} onChange={(e) => cambia(e.target.value)}
          style={{ width: 100, minHeight: 44, textAlign: "center", fontSize: 18, fontWeight: 800 }} />
        <button onClick={() => cambia((Number(moltiplicatore) || 0) + 0.5)} aria-label="Aumenta dose" style={{ minWidth: 44, minHeight: 44 }}>+</button>
      </div>
      {calcolata && <small>Ingrediente base: {calcolata.base} · dose ×{calcolata.fattore} · circa {calcolata.porzioni_stimate} pezzi</small>}
      {errore && <p role="alert" style={{ color: "#8f3829", margin: "8px 0 0" }}>{errore}</p>}
    </div>}
    {righe.length === 0 ? <p>Questa ricetta non ha ancora ingredienti.</p> : righe.map((r, i) =>
      <div key={`${r.nome}-${i}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "10px 12px", borderBottom: "1px solid #eee7dd", background: "#fff" }}>
        <span>{r.nome}</span><strong style={{ whiteSpace: "nowrap" }}>{r.dose || "—"}</strong>
      </div>
    )}
  </div>;
}
