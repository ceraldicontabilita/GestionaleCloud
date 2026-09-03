/**
 * prodotti/SenzaPesoPanel.jsx — Pannello prodotti senza peso (dizionario)
 */
import { useState, useEffect } from "react";
import { apiError } from "../../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { CheckCircle, Trash2, X } from "lucide-react";

import { API } from "../../../utils/constants";

function SenzaPesoPanel({ open, onClose, onProductDeleted }) {
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fix, setFix] = useState({});
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    axios.get(`${API}/normalizzazione/prodotti-senza-peso?limit=150`)
      .then(r => setProdotti(r.data.prodotti || []))
      .catch(() => toast.error("Errore caricamento prodotti senza peso"))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  const correggi = async (nomeNorm, peso, unita) => {
    try {
      await axios.post(`${API}/normalizzazione/correggi-peso?nome_normalizzato=${encodeURIComponent(nomeNorm)}&peso_kg=${peso}&unita=${unita}`);
      toast.success(`Aggiornato: ${nomeNorm}`);
      setProdotti(ps => ps.filter(p => p.nome_normalizzato !== nomeNorm));
    } catch { toast.error("Errore aggiornamento"); }
  };

  const eliminaDizionario = async (prodDiz) => {
    setDeletingId(prodDiz.nome_normalizzato);
    try {
      const res = await axios.get(`${API}/food-cost/dizionario/search?q=${encodeURIComponent(prodDiz.nome_normalizzato.substring(0, 8))}&escludi_fornitori=false`);
      const match = res.data.find(p => p.nome_normalizzato === prodDiz.nome_normalizzato);
      if (match?.id) await axios.delete(`${API}/food-cost/dizionario/${match.id}`);
      toast.success(`Eliminato: ${prodDiz.nome_originale || prodDiz.nome_normalizzato}`);
      setProdotti(ps => ps.filter(p => p.nome_normalizzato !== prodDiz.nome_normalizzato));
      if (onProductDeleted) onProductDeleted();
    } catch (e) {
      toast.error("Errore eliminazione: " + apiError(e));
    }
    setDeletingId(null);
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="bg-amber-600 text-white px-6 py-4 flex items-center justify-between rounded-t-2xl">
          <div>
            <h2 className="font-semibold">Prodotti Senza Peso</h2>
            <p className="text-amber-200 text-xs">{prodotti.length} prodotti con prezzo/kg approssimativo · Correggi il peso o elimina dal dizionario</p>
          </div>
          <button onClick={onClose}><X size={20} /></button>
        </div>
        <div className="overflow-y-auto flex-1 p-4">
          {loading && <p className="text-center text-gray-400 py-10">Caricamento...</p>}
          {!loading && prodotti.length === 0 && (
            <div className="text-center py-10">
              <CheckCircle size={40} className="mx-auto text-green-500 mb-2" />
              <p className="text-gray-600 font-medium">Tutti i prodotti hanno il peso configurato!</p>
            </div>
          )}
          <div className="space-y-2">
            {prodotti.map(p => {
              const fixVal = fix[p.nome_normalizzato] || { peso: "", unita: "kg" };
              const isDeleting = deletingId === p.nome_normalizzato;
              return (
                <div key={p.nome_normalizzato} className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{p.nome_originale || p.nome_normalizzato}</p>
                    <p className="text-xs text-gray-500">{p.fornitore} · Prezzo attuale: €{(p.prezzo_kg||0).toFixed(4)}/kg</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <input type="number" step="0.001" placeholder="Peso"
                      className="w-20 border border-amber-300 rounded-lg px-2 py-1 text-sm text-center"
                      value={fixVal.peso}
                      onChange={e => setFix(f => ({ ...f, [p.nome_normalizzato]: { ...fixVal, peso: e.target.value } }))} />
                    <select className="border border-amber-300 rounded-lg px-2 py-1 text-sm"
                      value={fixVal.unita}
                      onChange={e => setFix(f => ({ ...f, [p.nome_normalizzato]: { ...fixVal, unita: e.target.value } }))}>
                      <option value="kg">kg</option>
                      <option value="lt">lt</option>
                      <option value="pz">pz</option>
                    </select>
                    <button onClick={() => fixVal.peso && correggi(p.nome_normalizzato, parseFloat(fixVal.peso), fixVal.unita)}
                      disabled={!fixVal.peso}
                      className="px-3 py-1 bg-amber-600 text-white rounded-lg text-xs disabled:opacity-40 hover:bg-amber-700">Salva</button>
                    <button onClick={() => eliminaDizionario(p)} disabled={isDeleting}
                      className="px-2 py-1 bg-red-100 text-red-600 rounded-lg text-xs hover:bg-red-200 disabled:opacity-40" title="Elimina dal dizionario prezzi">
                      {isDeleting ? "..." : <Trash2 size={13} />}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default SenzaPesoPanel;
