/**
 * prodotti/VistaTabellaPrezzi.jsx — Vista tabella per editing massivo prezzi
 */
import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { DollarSign } from "lucide-react";

import { API } from "../../../utils/constants";

const VistaTabellaPrezzi = ({ prodotti, onAggiornato }) => {
  const [prezzi, setPrezzi] = useState({});
  const [saving, setSaving] = useState({});
  const [filtroSenzaPrezzo, setFiltroSP] = useState(false);

  const lista = filtroSenzaPrezzo ? prodotti.filter(p => !((p.prezzo_vendita || 0) > 0)) : prodotti;

  const calcMargine = (costo, prezzo) => {
    if (!prezzo || prezzo <= 0 || !costo || costo <= 0) return null;
    return (((prezzo - costo) / prezzo) * 100).toFixed(1);
  };

  const salva = async (prodotto) => {
    const val = parseFloat(String(prezzi[prodotto.id] || "").replace(",", "."));
    if (isNaN(val) || val <= 0) { toast.error("Prezzo non valido"); return; }
    setSaving(s => ({ ...s, [prodotto.id]: true }));
    try {
      await axios.put(`${API}/prodotti-vendita/${prodotto.id}/prezzo?prezzo_vendita=${val}`);
      toast.success(`${prodotto.nome}: €${val.toFixed(2)}`);
      setPrezzi(p => { const n = { ...p }; delete n[prodotto.id]; return n; });
      onAggiornato && onAggiornato();
    } catch { toast.error("Errore salvataggio"); }
    setSaving(s => ({ ...s, [prodotto.id]: false }));
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
      <div className="px-4 py-3 border-b bg-green-50 flex items-center gap-3 flex-wrap">
        <DollarSign size={16} className="text-green-600" />
        <span className="font-semibold text-green-800 text-sm">Gestione Prezzi di Vendita</span>
        <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer ml-auto">
          <input type="checkbox" checked={filtroSenzaPrezzo} onChange={e => setFiltroSP(e.target.checked)} className="accent-green-600" />
          Solo senza prezzo ({prodotti.filter(p => !((p.prezzo_vendita || 0) > 0)).length})
        </label>
      </div>
      <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 border-b text-xs text-gray-500 font-semibold">
            <tr>
              <th className="text-left px-4 py-2">Prodotto / Categoria</th>
              <th className="text-right px-3 py-2">Costo</th>
              <th className="text-right px-3 py-2 min-w-[130px]">Prezzo attuale</th>
              <th className="text-right px-3 py-2">Margine</th>
              <th className="text-center px-3 py-2 min-w-[180px]">Nuovo prezzo</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {lista.map(p => {
              const costoN = parseFloat(p.costo_produzione || 0);
              const prezzoN = parseFloat(p.prezzo_vendita || 0);
              const nuovoPrezzoN = parseFloat(String(prezzi[p.id] || "").replace(",", ".")) || null;
              const margineAtt = calcMargine(costoN, prezzoN);
              const margineNew = nuovoPrezzoN ? calcMargine(costoN, nuovoPrezzoN) : null;
              const isSaving = saving[p.id];
              const haInput = prezzi[p.id] !== undefined;
              return (
                <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5">
                    <p className="font-medium text-gray-800 truncate max-w-[220px]">{p.nome}</p>
                    {p.categoria && <p className="text-[10px] text-gray-400">{p.categoria}</p>}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <span className="text-gray-600 font-mono text-xs">
                      {costoN > 0 ? `€${costoN.toFixed(3)}` : <span className="text-gray-300">—</span>}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {prezzoN > 0 ? <span className="font-semibold text-gray-800 font-mono">€{prezzoN.toFixed(2)}</span> : <span className="text-xs text-amber-500 font-medium">da impostare</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {margineAtt !== null ? (
                      <span className={`font-semibold text-xs ${parseFloat(margineAtt) >= 60 ? "text-green-600" : parseFloat(margineAtt) >= 40 ? "text-amber-600" : "text-red-500"}`}>
                        {margineNew ? `→ ${margineNew}%` : `${margineAtt}%`}
                      </span>
                    ) : margineNew ? <span className="text-green-600 text-xs font-semibold">{margineNew}%</span> : <span className="text-gray-200 text-xs">—</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1.5 justify-center">
                      <span className="text-gray-400 text-xs">€</span>
                      <input type="number" min="0" step="0.05"
                        placeholder={prezzoN > 0 ? prezzoN.toFixed(2) : "0.00"}
                        value={prezzi[p.id] ?? ""}
                        onChange={e => setPrezzi(prev => ({ ...prev, [p.id]: e.target.value }))}
                        onKeyDown={e => e.key === "Enter" && salva(p)}
                        className="w-20 border border-gray-200 rounded-lg px-2 py-1 text-sm text-right focus:ring-2 focus:ring-green-300 outline-none"
                        data-testid={`input-prezzo-${p.id}`} />
                      <button onClick={() => salva(p)} disabled={!haInput || isSaving}
                        className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all ${haInput && !isSaving ? "bg-green-600 text-white hover:bg-green-700" : "bg-gray-100 text-gray-300 cursor-not-allowed"}`}
                        data-testid={`salva-prezzo-${p.id}`}>
                        {isSaving ? "..." : "Salva"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2 bg-gray-50 border-t text-[10px] text-gray-500">
        Digita il prezzo e premi <strong>Invio</strong> o <strong>Salva</strong>. Il margine viene calcolato automaticamente.
        Costo = food cost dalle ricette. Margine = (prezzo - costo) / prezzo × 100.
      </div>
    </div>
  );
};

export default VistaTabellaPrezzi;
