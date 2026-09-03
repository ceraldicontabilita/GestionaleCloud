/**
 * TabAllergeni.jsx — Tab Allergeni & Nutrizionale di SchedaProdottoView
 */
import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { AlertTriangle, Scale, X, Check, Save, RefreshCw, Calculator } from "lucide-react";
import { API } from "../../../utils/constants";

const ALLERGENI_14 = [
  { id: "Glutine",              icon: "🌾", note: "Grano, segale, orzo, avena, farro, kamut" },
  { id: "Crostacei",            icon: "🦐", note: "Gamberi, granchi, aragoste, scampi" },
  { id: "Uova",                 icon: "🥚", note: "e prodotti a base di uova" },
  { id: "Pesce",                icon: "🐟", note: "e prodotti a base di pesce" },
  { id: "Arachidi",             icon: "🥜", note: "e prodotti a base di arachidi" },
  { id: "Soia",                 icon: "🫘", note: "e prodotti a base di soia" },
  { id: "Latte",                icon: "🥛", note: "e prodotti lattiero-caseari (incluso lattosio)" },
  { id: "Frutta a guscio",      icon: "🌰", note: "Mandorle, nocciole, noci, anacardi, pistacchi, noci pecan, noci del Brasile, macadamia" },
  { id: "Sedano",               icon: "🥬", note: "e prodotti a base di sedano" },
  { id: "Senape",               icon: "🌿", note: "e prodotti a base di senape" },
  { id: "Sesamo",               icon: "🌱", note: "e prodotti a base di semi di sesamo" },
  { id: "Anidride solforosa",   icon: "💨", note: "e solfiti (conc. > 10 mg/kg o 10 mg/L)" },
  { id: "Lupini",               icon: "🌼", note: "e prodotti a base di lupini" },
  { id: "Molluschi",            icon: "🦑", note: "Cozze, ostriche, vongole, calamari, polpi" },
];

const NUTRI_FIELDS = [
  { k: "kcal",        label: "Valore energetico", um: "kcal" },
  { k: "grassi",      label: "Grassi totali",     um: "g" },
  { k: "saturi",      label: "di cui saturi",     um: "g" },
  { k: "carboidrati", label: "Carboidrati",       um: "g" },
  { k: "zuccheri",    label: "di cui zuccheri",   um: "g" },
  { k: "proteine",    label: "Proteine",          um: "g" },
  { k: "sale",        label: "Sale",              um: "g" },
];

const NUTRI_EMPTY = { kcal: "", grassi: "", saturi: "", carboidrati: "", zuccheri: "", proteine: "", sale: "" };

const TabAllergeni = ({ ricetta, onUpdated }) => {
  const [allergeni, setAllergeni] = useState([]);
  const [nutri, setNutri] = useState(NUTRI_EMPTY);
  const [salvando, setSalvando] = useState(false);
  const [rilevando, setRilevando] = useState(false);
  const [rilevaAll, setRilevaAll] = useState(false);

  useEffect(() => {
    if (!ricetta) return;
    const savedAll = ricetta.allergeni || [];
    const savedNutri = ricetta.nutrizionale || NUTRI_EMPTY;
    setAllergeni(savedAll);
    setNutri(savedNutri);

    const hasIng = (ricetta.ingredienti_dettaglio?.length > 0 || ricetta.ingredienti?.length > 0);
    const hasNutri = NUTRI_FIELDS.some(f => Number(savedNutri[f.k] || 0) > 0);
    const needAll = (!savedAll || savedAll.length === 0) && hasIng;
    const needNutri = !hasNutri && hasIng;
    if (!needAll && !needNutri) return;

    // Calcolo automatico (allergeni + valori nutrizionali) con un solo salvataggio
    (async () => {
      let nuoviAll = savedAll;
      let nuoviNutri = savedNutri;
      if (needAll) {
        try {
          const r = await axios.post(`${API}/food-cost/auto-rileva-allergeni-ricetta/${ricetta.id}`);
          const sugg = r.data.allergeni_suggeriti || [];
          if (sugg.length > 0) { nuoviAll = sugg; setAllergeni(sugg); }
        } catch { /* ignore */ }
      }
      if (needNutri) {
        try {
          const r = await axios.get(`${API}/ricette/${ricetta.id}/nutrizionali`, { timeout: 30000 });
          const p = r.data?.per_100g;
          if (p && r.data?.ingredienti_coperti) {
            nuoviNutri = {
              kcal: p.kcal ?? "", grassi: p.grassi ?? "", saturi: p.saturi ?? "",
              carboidrati: p.carboidrati ?? "", zuccheri: p.zuccheri ?? "",
              proteine: p.proteine ?? "", sale: p.sale ?? "",
            };
            setNutri(nuoviNutri);
          }
        } catch { /* ignore */ }
      }
      if (nuoviAll !== savedAll || nuoviNutri !== savedNutri) {
        axios.post(`${API}/food-cost/aggiorna-allergeni-ricetta`, {
          ricetta_id: ricetta.id,
          allergeni: nuoviAll,
          nutrizionale: nuoviNutri,
        }).catch(() => {});
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ricetta?.id]);

  const toggleAllergene = (id) => {
    setAllergeni(prev => prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]);
  };

  const rilevaDaIngredienti = async () => {
    setRilevando(true);
    try {
      const res = await axios.post(`${API}/food-cost/auto-rileva-allergeni-ricetta/${ricetta.id}`);
      const suggeriti = res.data.allergeni_suggeriti || [];
      if (suggeriti.length === 0) {
        toast.info("Nessun allergene rilevato automaticamente dagli ingredienti");
      } else {
        setAllergeni(suggeriti);
        toast.success(`Rilevati ${suggeriti.length} allergeni dagli ingredienti`);
      }
    } catch { toast.error("Errore nel rilevamento"); }
    finally { setRilevando(false); }
  };

  const salva = async () => {
    setSalvando(true);
    try {
      await axios.post(`${API}/food-cost/aggiorna-allergeni-ricetta`, {
        ricetta_id: ricetta.id,
        allergeni,
        nutrizionale: nutri
      });
      toast.success("Allergeni e dati nutrizionali salvati");
      onUpdated && onUpdated();
    } catch { toast.error("Errore nel salvataggio"); }
    finally { setSalvando(false); }
  };

  if (!ricetta) return null;

  return (
    <div className="space-y-6 pb-6">
      <div className="rounded-xl p-3 flex gap-2 text-xs" style={{ background: "#f7ecdc", border: "1px solid #ecd6b8", color: "#7d5526" }}>
        <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
        <span><strong>Reg. UE 1169/2011 – Allegato II:</strong> La dichiarazione degli allergeni è obbligatoria per tutti gli operatori della ristorazione (OSA). Gli allergeni vengono rilevati <strong>automaticamente</strong> dagli ingredienti; puoi correggerli a mano qui sotto.</span>
      </div>

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={rilevaDaIngredienti}
          disabled={rilevando}
          data-testid="auto-rileva-allergeni-btn"
          className="flex items-center gap-2 text-white rounded-xl px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          style={{ background: "#5b7a6b" }}
        >
          {rilevando ? <RefreshCw size={14} className="animate-spin" /> : <Calculator size={14} />}
          Ri-rileva da ingredienti
        </button>
        <button
          onClick={() => setAllergeni([])}
          className="flex items-center gap-2 border rounded-xl px-3 py-2 text-sm transition-colors"
          style={{ borderColor: "#e6e0d4", color: "#6b7669" }}
        >
          <X size={14} /> Reset
        </button>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5" style={{ color: "#2a3329" }}>
          <AlertTriangle size={14} style={{ color: "#c77b56" }} /> 14 Allergeni Obbligatori (Reg. UE 1169/2011)
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {ALLERGENI_14.map(a => {
            const attivo = allergeni.includes(a.id);
            return (
              <button
                key={a.id}
                onClick={() => toggleAllergene(a.id)}
                data-testid={`allergen-${a.id}`}
                className={`text-left rounded-xl border p-2.5 transition-all ${attivo ? "bg-red-50 border-red-400 ring-1 ring-red-300" : "bg-gray-50 border-gray-200 hover:border-gray-300"}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-base">{a.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className={`text-xs font-semibold ${attivo ? "text-red-700" : "text-gray-700"}`}>{a.id}</div>
                    <div className="text-[10px] text-gray-400 truncate">{a.note}</div>
                  </div>
                  {attivo && <Check size={12} className="text-red-500 flex-shrink-0" />}
                </div>
              </button>
            );
          })}
        </div>
        {allergeni.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {allergeni.map(a => (
              <span key={a} className="inline-flex items-center gap-1 bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full font-medium">
                {ALLERGENI_14.find(x => x.id === a)?.icon} {a}
              </span>
            ))}
          </div>
        )}
        {allergeni.length === 0 && (
          <p className="mt-2 text-xs text-gray-400 italic">Nessun allergene selezionato — assicurati che sia corretto</p>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1 flex items-center gap-1.5">
          <Scale size={14} className="text-[#5b7a6b]" /> Dichiarazione Nutrizionale (per 100g – obbligatoria dal 2016)
        </h3>
        <p className="text-[11px] text-gray-400 mb-3">Calcolata automaticamente dagli ingredienti (stima USDA). Puoi correggerla a mano.</p>
        <div className="grid grid-cols-2 gap-2">
          {NUTRI_FIELDS.map(f => (
            <div key={f.k} className="flex flex-col gap-1">
              <label className="text-[11px] font-medium text-gray-600">
                {f.label} <span className="text-gray-400">({f.um}/100g)</span>
                <span className="text-red-400 ml-1">*</span>
              </label>
              <input
                type="number" step="0.1" min="0"
                value={nutri[f.k] || ""}
                onChange={e => setNutri(p => ({ ...p, [f.k]: e.target.value }))}
                className="border rounded-lg px-2 py-1.5 text-sm text-right focus:ring-2 focus:ring-[#5b7a6b] outline-none"
                placeholder="0.0"
              />
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={salva}
        disabled={salvando}
        data-testid="salva-allergeni-btn"
        className="w-full bg-red-600 hover:bg-red-700 text-white rounded-xl py-2.5 text-sm font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
      >
        {salvando ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
        Salva Allergeni & Dati Nutrizionali
      </button>
    </div>
  );
};

export default TabAllergeni;
