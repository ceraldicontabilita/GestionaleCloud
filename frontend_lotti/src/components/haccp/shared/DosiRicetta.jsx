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
  const [tentativo, setTentativo] = useState(0);
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
      axios.post(`${API}/food-cost/ricetta/${ricetta.id}/dose-produzione`, { moltiplicatore: valore, normalizza_1kg: true })
        .then(({ data }) => { if (attivo) { setCalcolata(data); setErrore(""); } })
        .catch((e) => { if (attivo) { setCalcolata(null); setErrore(apiError(e, "Dose non calcolabile")); } });
    }, 200);
    return () => { attivo = false; clearTimeout(timer); };
  }, [ricetta?.id, dettaglio.length, moltiplicatore, tentativo]);

  const cambia = (valore) => { setCalcolata(null); setMoltiplicatore(String(valore)); };
  const ingredienti = calcolata?.ingredienti || dettaglio;
  const righe = ingredienti.length ? ingredienti.map((i) => ({
    nome: i?.nome || "Ingrediente",
    dose: [i?.quantita, i?.unita_misura || i?.unita].filter((v) => v !== null && v !== undefined && v !== "").join(" "),
  })) : soliNomi.map((i) => ({ nome: typeof i === "string" ? i : i?.nome || "Ingrediente", dose: "" }));

  return <div>
    {dettaglio.length > 0 && <div style={{ background: "#fff", border: "1px solid #e6e0d4", borderRadius: 12, padding: 12, marginBottom: 12 }}>
      <label htmlFor={`moltiplicatore-${ricetta.id}`} style={{ fontWeight: 800 }}>Dose per 1 kg dell’ingrediente principale</label>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
        <button onClick={() => cambia(Math.max(0.1, (Number(moltiplicatore) || 1) - 0.5))} aria-label="Riduci dose" style={{ minWidth: 44, minHeight: 44 }}>−</button>
        <input id={`moltiplicatore-${ricetta.id}`} type="number" min="0.1" max="1000" step="0.1" value={moltiplicatore} onChange={(e) => cambia(e.target.value)}
          style={{ width: 100, minHeight: 44, textAlign: "center", fontSize: 18, fontWeight: 800 }} />
        <button onClick={() => cambia((Number(moltiplicatore) || 0) + 0.5)} aria-label="Aumenta dose" style={{ minWidth: 44, minHeight: 44 }}>+</button>
      </div>
      {calcolata && <div style={{ marginTop: 8, fontSize: 13 }}>
        <div>Ingrediente principale: {calcolata.base} · {moltiplicatore} kg</div>
        {calcolata.peso_totale_g > 0 && <div>Impasto {calcolata.peso_impasto_g} g{calcolata.peso_pieghe_g > 0 ? ` + pieghe ${calcolata.peso_pieghe_g} g` : ""} = {calcolata.peso_totale_g} g</div>}
        {calcolata.porzioni_stimate != null
          ? <strong>{calcolata.porzioni_stimate} pezzi interi da {calcolata.peso_pezzo_g} g</strong>
          : <div>Resa in pezzi da completare: indica peso del pezzo e dosi mancanti nella ricetta.</div>}
        {calcolata.ingredienti_senza_massa?.length > 0 && <div>Dosi o pesi mancanti: {calcolata.ingredienti_senza_massa.join(", ")}</div>}
      </div>}
      {errore && <div role="alert" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", margin: "8px 0 0" }}>
        <span style={{ color: "#8f3829", flex: 1, minWidth: 0 }}>{errore}</span>
        <button type="button" onClick={() => setTentativo((n) => n + 1)}
          style={{ minHeight: 44, padding: "0 14px", borderRadius: 10, border: "1px solid #cfdfd5", background: "#f2f6f3", color: "#3f5a4e", fontWeight: 800, cursor: "pointer" }}>
          Riprova
        </button>
      </div>}
    </div>}
    {righe.length === 0 ? <p>Questa ricetta non ha ancora ingredienti.</p> : righe.map((r, i) =>
      <div key={`${r.nome}-${i}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "10px 12px", borderBottom: "1px solid #eee7dd", background: "#fff" }}>
        <span>{r.nome}</span><strong style={{ whiteSpace: "nowrap" }}>{r.dose || "—"}</strong>
      </div>
    )}
  </div>;
}
