/**
 * scheda/utils.js — Utilità condivise tra i tab di SchedaProdottoView
 */
import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { TrendingUp, TrendingDown, Edit, X } from "lucide-react";
import { API } from "../../../utils/constants";

// ─── Hook attrezzature ────────────────────────────────────────────────────────
export const useAttrezzature = () => {
  const [attrezzature, setAttrezzature] = useState({ frigoriferi: [], congelatori: [], tutti: [] });
  useEffect(() => {
    axios.get(`${API}/attrezzature/`)
      .then(r => setAttrezzature(r.data || { frigoriferi: [], congelatori: [], tutti: [] }))
      .catch(() => {});
  }, []);
  return attrezzature;
};

// ─── Formatter ────────────────────────────────────────────────────────────────
export const formatCosto = (val) => {
  if (val == null) return "0.00";
  const n = parseFloat(val);
  if (isNaN(n) || n === 0) return "0.00";
  if (n < 0.005) return n.toFixed(4);
  if (n < 0.10) return n.toFixed(3);
  return n.toFixed(2);
};

export const formatPeso = (grammi) => {
  if (grammi >= 1000) return `${(grammi / 1000).toFixed(2)} kg`;
  return `${grammi.toFixed(0)} g`;
};

// ─── Badge Margine ────────────────────────────────────────────────────────────
export const BadgeMargine = ({ pct }) => {
  if (!pct || pct <= 0) return <span className="text-xs text-gray-300">—</span>;
  const color = pct >= 50 ? "text-green-700 bg-green-50 border-green-200"
    : pct >= 30 ? "text-amber-700 bg-amber-50 border-amber-200"
    : "text-red-700 bg-red-50 border-red-200";
  const Icon = pct >= 30 ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-full border ${color}`}>
      <Icon size={10} /> {pct.toFixed(1)}%
    </span>
  );
};

// ─── Inline Prezzo Dizionario ─────────────────────────────────────────────────
export const InlinePrezzoDizionario = ({ ing, ricettaId, onSaved }) => {
  const [editing, setEditing] = useState(false);
  const [prezzoKg, setPrezzoKg] = useState("");
  const [fornitore, setFornitore] = useState("");

  const salva = async () => {
    const n = parseFloat(prezzoKg);
    if (isNaN(n) || n <= 0) { setEditing(false); return; }
    try {
      await axios.post(`${API}/food-cost/dizionario/manuale`, {
        nome: ing.nome,
        prezzo_kg: n,
        fornitore: fornitore || "Manuale"
      });
      toast.success(`Prezzo €${n.toFixed(2)}/kg salvato per "${ing.nome}"`);
      setEditing(false);
      onSaved && onSaved();
    } catch { toast.error("Errore salvataggio prezzo"); setEditing(false); }
  };

  if (editing) return (
    <div className="flex items-center gap-1 mt-1">
      <input type="number" step="0.01" min="0.01" value={prezzoKg}
        onChange={e => setPrezzoKg(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter") salva(); if (e.key === "Escape") setEditing(false); }}
        autoFocus placeholder="€/kg"
        className="w-20 text-right px-2 py-0.5 border-2 border-amber-400 rounded text-xs focus:outline-none font-mono" />
      <input type="text" value={fornitore} onChange={e => setFornitore(e.target.value)}
        placeholder="Fornitore"
        className="w-24 px-2 py-0.5 border border-gray-300 rounded text-xs focus:outline-none" />
      <button onClick={salva} className="px-2 py-0.5 bg-amber-500 text-white rounded text-xs font-bold">OK</button>
      <button onClick={() => setEditing(false)} className="text-gray-400 hover:text-red-400"><X size={12} /></button>
    </div>
  );

  return (
    <button
      onClick={() => setEditing(true)}
      className="text-[10px] text-amber-600 hover:text-amber-800 hover:underline flex items-center gap-0.5 mt-0.5"
      title="Clicca per impostare il prezzo manualmente">
      <Edit size={9} /> imposta prezzo manuale
    </button>
  );
};

// ─── Inline Prezzo Edit ───────────────────────────────────────────────────────
export const InlinePrezzoEdit = ({ id, prezzo, onSaved }) => {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState("");
  const salva = async () => {
    const n = parseFloat(val);
    if (isNaN(n) || n < 0) { setEditing(false); return; }
    try {
      await axios.put(`${API}/ricette/${id}/prezzo-vendita`, null, { params: { prezzo: n } });
      toast.success(`Prezzo €${n.toFixed(2)} salvato`);
      setEditing(false);
      onSaved && onSaved();
    } catch { toast.error("Errore salvataggio"); setEditing(false); }
  };
  if (editing) return (
    <div className="flex items-center gap-1">
      <span className="text-xs text-gray-400">€</span>
      <input type="number" step="0.01" min="0" value={val}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter") salva(); if (e.key === "Escape") setEditing(false); }}
        onBlur={salva} autoFocus placeholder="0.00"
        className="w-24 text-right px-2 py-1 border-2 border-[#5b7a6b] rounded-lg text-sm focus:outline-none font-mono" />
    </div>
  );
  return (
    <button onClick={() => { setEditing(true); setVal(prezzo > 0 ? String(prezzo) : ""); }}
      className={`text-sm font-mono transition-colors ${prezzo > 0 ? "text-[#5b7a6b] hover:text-[#3f5a4e] font-semibold" : "text-gray-300 hover:text-[#5b7a6b] text-xs"}`}
      title="Clicca per modificare il prezzo">
      {prezzo > 0 ? `€${prezzo.toFixed(2)}` : "+ imposta prezzo"}
    </button>
  );
};
