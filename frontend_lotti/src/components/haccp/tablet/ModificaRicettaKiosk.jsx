import { useState } from "react";
import axios from "axios";
import { Calculator, Plus, Save, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";

const REPARTI = [
  ["pasticceria", "Pasticceria"],
  ["rosticceria", "Rosticceria"],
  ["bar", "Bar"],
];
const UNITA = ["g", "kg", "ml", "l", "pz", "q.b."];

function testoProcedimento(ricetta) {
  return ricetta?.procedimento_testo || ricetta?.procedimento || ricetta?.preparazione || ricetta?.metodo_preparazione || "";
}

export function creaBozzaRicetta(ricetta = {}) {
  const dettaglio = Array.isArray(ricetta.ingredienti_dettaglio) ? ricetta.ingredienti_dettaglio : [];
  const soloNomi = Array.isArray(ricetta.ingredienti) ? ricetta.ingredienti : [];
  const ingredienti = dettaglio.length
    ? dettaglio.map((i) => ({
        nome: i?.nome || "",
        quantita: i?.quantita ?? "",
        unita: i?.unita_misura || i?.unita || "g",
      }))
    : soloNomi.map((i) => ({
        nome: typeof i === "string" ? i : (i?.nome || ""),
        quantita: typeof i === "object" ? (i?.quantita ?? "") : "",
        unita: typeof i === "object" ? (i?.unita_misura || i?.unita || "g") : "g",
      }));
  return {
    nome: ricetta.nome || "",
    reparto: ricetta.reparto || "pasticceria",
    porzioni: ricetta.porzioni ?? 1,
    metodo_conservazione: ricetta.metodo_conservazione || "",
    ingredienti,
    allergeni: (Array.isArray(ricetta.allergeni) ? ricetta.allergeni : []).filter(Boolean).join(", "),
    procedimento: testoProcedimento(ricetta),
    note: typeof ricetta.note === "string" ? ricetta.note : "",
  };
}

function numero(v) {
  if (v === "" || v === null || v === undefined) return 0;
  const n = Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

export function payloadRicettaDaBozza(bozza, originale = {}, allergeniConfermati = false) {
  const ingredienti = (bozza.ingredienti || [])
    .filter((i) => String(i?.nome || "").trim())
    .map((i) => ({
      nome: String(i.nome).trim(),
      quantita: numero(i.quantita),
      unita_misura: i.unita || "g",
    }));
  return {
    nome: String(bozza.nome || "").trim(),
    reparto: bozza.reparto || "pasticceria",
    porzioni: Math.max(1, Math.round(numero(bozza.porzioni) || 1)),
    metodo_conservazione: String(bozza.metodo_conservazione || "").trim(),
    ingredienti: ingredienti.map((i) => i.nome),
    ingredienti_dettaglio: ingredienti,
    allergeni: String(bozza.allergeni || "")
      .split(/[,;\n]/)
      .map((a) => a.trim())
      .filter(Boolean),
    allergeni_confermati: allergeniConfermati,
    procedimento_testo: String(bozza.procedimento || "").trim(),
    note: String(bozza.note || "").trim(),
    componenti: Array.isArray(originale.componenti) ? originale.componenti : [],
    foto_url: originale.foto_url || "",
    prezzo_vendita: numero(originale.prezzo_vendita),
    ricetta_base_id: originale.ricetta_base_id || null,
    ricetta_base_nome: originale.ricetta_base_nome || null,
    ingrediente_variante: originale.ingrediente_variante || null,
    fornitore_rivendita: originale.fornitore_rivendita || "",
    origine_ingredienti: "manuale",
  };
}

export default function ModificaRicettaKiosk({ ricetta, onAnnulla, onSalvata }) {
  const [bozza, setBozza] = useState(() => creaBozzaRicetta(ricetta));
  const [salvando, setSalvando] = useState(false);
  const [rilevando, setRilevando] = useState(false);
  const [allergeniConfermati, setAllergeniConfermati] = useState(false);

  const aggiornaIngrediente = (indice, campo, valore) => {
    setBozza((corrente) => ({
      ...corrente,
      ingredienti: corrente.ingredienti.map((i, n) => n === indice ? { ...i, [campo]: valore } : i),
    }));
  };

  const eliminaIngrediente = (indice) => {
    setBozza((corrente) => ({
      ...corrente,
      ingredienti: corrente.ingredienti.filter((_, n) => n !== indice),
    }));
  };

  const salva = async () => {
    if (!bozza.nome.trim()) {
      toast.error("Inserisci il nome della ricetta");
      return;
    }
    setSalvando(true);
    try {
      const risposta = await axios.put(
        `${API}/ricette/${ricetta.id}`,
        payloadRicettaDaBozza(bozza, ricetta, allergeniConfermati),
      );
      toast.success("Ricetta aggiornata");
      onSalvata(risposta.data);
    } catch (errore) {
      toast.error(apiError(errore, "Non è stato possibile salvare la ricetta"));
    } finally {
      setSalvando(false);
    }
  };

  const rilevaAllergeni = async () => {
    setRilevando(true);
    try {
      const ingredienti = bozza.ingredienti
        .map((ingrediente) => ({ nome: String(ingrediente?.nome || "").trim() }))
        .filter((ingrediente) => ingrediente.nome);
      const risposta = await axios.post(
        `${API}/food-cost/auto-rileva-allergeni-ricetta/${ricetta.id}`,
        { ingredienti_dettaglio: ingredienti },
      );
      const suggeriti = risposta.data?.allergeni_suggeriti || [];
      setBozza((corrente) => ({ ...corrente, allergeni: suggeriti.join(", ") }));
      setAllergeniConfermati(false);
      toast.success(suggeriti.length ? `Rilevati ${suggeriti.length} allergeni` : "Nessun allergene rilevato");
    } catch (errore) {
      toast.error(apiError(errore, "Rilevamento allergeni non riuscito"));
    } finally {
      setRilevando(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Campo titolo="Nome ricetta">
        <input value={bozza.nome} onChange={(e) => setBozza({ ...bozza, nome: e.target.value })} style={inputStyle} />
      </Campo>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(135px,1fr))", gap: 10 }}>
        <Campo titolo="Resa (pezzi)">
          <input type="number" inputMode="numeric" min="1" value={bozza.porzioni}
            onChange={(e) => setBozza({ ...bozza, porzioni: e.target.value })} style={inputStyle} />
        </Campo>
        <Campo titolo="Reparto">
          <select value={bozza.reparto} onChange={(e) => setBozza({ ...bozza, reparto: e.target.value })} style={inputStyle}>
            {REPARTI.map(([valore, etichetta]) => <option key={valore} value={valore}>{etichetta}</option>)}
          </select>
        </Campo>
        <Campo titolo="Conservazione">
          <input value={bozza.metodo_conservazione}
            onChange={(e) => setBozza({ ...bozza, metodo_conservazione: e.target.value })}
            placeholder="Es. frigo, freezer" style={inputStyle} />
        </Campo>
      </div>

      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
          <h3 style={titoloStyle}>Ingredienti</h3>
          <button type="button" onClick={() => setBozza((b) => ({ ...b, ingredienti: [...b.ingredienti, { nome: "", quantita: "", unita: "g" }] }))} style={secondaryButton}>
            <Plus size={15} /> Aggiungi
          </button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {bozza.ingredienti.map((ingrediente, indice) => (
            <div key={indice} style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
              <input aria-label={`Ingrediente ${indice + 1}`} value={ingrediente.nome}
                onChange={(e) => aggiornaIngrediente(indice, "nome", e.target.value)} placeholder="Ingrediente"
                style={{ ...inputStyle, flex: "1 1 170px" }} />
              <input aria-label={`Quantità ${ingrediente.nome || indice + 1}`} inputMode="decimal" value={ingrediente.quantita}
                onChange={(e) => aggiornaIngrediente(indice, "quantita", e.target.value)} placeholder="Q.tà"
                style={{ ...inputStyle, flex: "0 1 90px" }} />
              <select aria-label={`Unità ${ingrediente.nome || indice + 1}`} value={ingrediente.unita}
                onChange={(e) => aggiornaIngrediente(indice, "unita", e.target.value)} style={{ ...inputStyle, padding: "10px 5px", flex: "0 0 72px" }}>
                {UNITA.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
              <button type="button" onClick={() => eliminaIngrediente(indice)} aria-label={`Elimina ${ingrediente.nome || "ingrediente"}`}
                style={{ minWidth: 40, minHeight: 42, border: "1px solid #fecaca", borderRadius: 10, background: "#fff1f2", color: "#b91c1c", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      </div>

      <Campo titolo="Allergeni" aiuto="Si aggiornano automaticamente dagli ingredienti al salvataggio">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
          <input value={bozza.allergeni} onChange={(e) => {
              setBozza({ ...bozza, allergeni: e.target.value });
              setAllergeniConfermati(true);
            }}
            placeholder="Glutine, Latte, Uova…" style={{ ...inputStyle, flex: "1 1 220px" }} />
          <button type="button" onClick={rilevaAllergeni} disabled={rilevando} style={secondaryButton}>
            <Calculator size={15} /> {rilevando ? "Analisi…" : "Rileva dagli ingredienti"}
          </button>
        </div>
      </Campo>
      <Campo titolo="Modo di preparazione">
        <textarea value={bozza.procedimento} onChange={(e) => setBozza({ ...bozza, procedimento: e.target.value })}
          rows={6} placeholder="Descrivi i passaggi della lavorazione" style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }} />
      </Campo>
      <Campo titolo="Note di lavorazione">
        <textarea value={bozza.note} onChange={(e) => setBozza({ ...bozza, note: e.target.value })}
          rows={3} style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }} />
      </Campo>

      <div style={{ position: "sticky", bottom: 0, display: "flex", gap: 8, padding: "10px 0 2px", background: "#faf7f0" }}>
        <button type="button" onClick={onAnnulla} disabled={salvando} style={{ ...secondaryButton, flex: 1, justifyContent: "center", minHeight: 46 }}>
          <X size={17} /> Annulla
        </button>
        <button type="button" onClick={salva} disabled={salvando} style={{ ...primaryButton, flex: 2 }}>
          <Save size={18} /> {salvando ? "Salvataggio…" : "Salva modifiche"}
        </button>
      </div>
    </div>
  );
}

function Campo({ titolo, aiuto, children }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 5, color: "#2a3329", fontSize: 12, fontWeight: 800 }}>
      <span>{titolo}{aiuto ? <small style={{ marginLeft: 6, color: "#6b7669", fontWeight: 500 }}>{aiuto}</small> : null}</span>
      {children}
    </label>
  );
}

const inputStyle = {
  width: "100%", boxSizing: "border-box", minHeight: 42, border: "1px solid #d8d2c6",
  borderRadius: 10, background: "#fffefb", color: "#2a3329", padding: "10px 11px",
  fontFamily: "inherit", fontSize: 14, outlineColor: "#6f9180",
};
const titoloStyle = { margin: 0, fontSize: 15, fontWeight: 900, color: "#2a3329" };
const secondaryButton = {
  minHeight: 38, border: "1px solid #cfdfd5", borderRadius: 10, background: "#f2f6f3",
  color: "#3f5a4e", padding: "7px 11px", cursor: "pointer", display: "inline-flex",
  alignItems: "center", gap: 5, fontFamily: "inherit", fontSize: 12, fontWeight: 800,
};
const primaryButton = {
  minHeight: 46, border: "none", borderRadius: 11, background: "#4f6d5f", color: "#fff",
  padding: "10px 16px", cursor: "pointer", display: "inline-flex", alignItems: "center",
  justifyContent: "center", gap: 7, fontFamily: "inherit", fontSize: 13, fontWeight: 900,
};
