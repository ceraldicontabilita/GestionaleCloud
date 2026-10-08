/**
 * BulkPrezziView — Wizard rapido per assegnare prezzi di vendita in massa
 * Mostra i prodotti senza prezzo, permettendo di impostare velocemente il prezzo
 * con bottoni preset margine o inserimento manuale.
 */
import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Tag, Save, X, CheckCircle } from "lucide-react";
import { toast } from "sonner";
import { API } from "../../utils/constants";

const IVA_DEFAULT = 10;

function calcolaPrezzoDaMargine(costo, margine) {
  if (!costo || costo <= 0) return 0;
  return Math.round((costo / (1 - margine / 100)) * 100) / 100;
}

// ─── Riga singolo prodotto ──────────────────────────────────────────────────
function RigaProdotto({ prodotto, onSave, salvando }) {
  const costo = parseFloat(prodotto.costo_produzione) || 0;
  const [prezzo, setPrezzo] = useState(prodotto.prezzo_vendita > 0 ? prodotto.prezzo_vendita : "");
  const [iva, setIva] = useState(prodotto.iva || IVA_DEFAULT);
  const [saved, setSaved] = useState(false);

  const margineCalc = prezzo && costo > 0
    ? Math.round(((parseFloat(prezzo) - costo) / parseFloat(prezzo)) * 1000) / 10
    : null;

  const margineColor = margineCalc === null ? ""
    : margineCalc >= 30 ? "text-green-600"
    : margineCalc >= 20 ? "text-yellow-600"
    : "text-red-500";

  const handleSave = async () => {
    if (!prezzo || parseFloat(prezzo) <= 0) {
      toast.error("Inserisci un prezzo valido");
      return;
    }
    await onSave(prodotto.id, { prezzo_vendita: parseFloat(prezzo), iva: parseFloat(iva) });
    setSaved(true);
  };

  const applicaMargine = (pct) => {
    if (costo <= 0) { toast.error("Costo non disponibile"); return; }
    setPrezzo(calcolaPrezzoDaMargine(costo, pct));
  };

  return (
    <div className={`bg-white rounded-xl border px-4 py-3 flex items-center gap-3 transition-all ${saved ? "border-green-300 bg-green-50" : "border-gray-100 hover:border-[#b8d0c2]"}`}>
      {/* Nome + categoria */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-800 truncate">{prodotto.nome}</p>
        <p className="text-xs text-gray-400 truncate">
          {prodotto.categoria || "Senza categoria"}
          {costo > 0 ? ` · Costo: €${costo.toFixed(4)}` : " · Costo non disponibile"}
        </p>
      </div>

      {/* Preset margine rapido */}
      <div className="hidden md:flex items-center gap-1 flex-shrink-0">
        {[25, 30, 35, 40].map(pct => (
          <button
            key={pct}
            onClick={() => applicaMargine(pct)}
            disabled={costo <= 0}
            className="px-2 py-1 bg-gray-50 border border-gray-200 rounded text-xs hover:border-[#b8d0c2] hover:bg-[#f2f6f3] transition-all disabled:opacity-30"
            title={`Margine ${pct}%`}
          >
            {pct}%
          </button>
        ))}
      </div>

      {/* IVA select */}
      <select
        value={iva}
        onChange={e => setIva(e.target.value)}
        className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs w-20 flex-shrink-0"
      >
        <option value={4}>IVA 4%</option>
        <option value={10}>IVA 10%</option>
        <option value={22}>IVA 22%</option>
        <option value={0}>Esente</option>
      </select>

      {/* Input prezzo */}
      <div className="relative flex-shrink-0 w-28">
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-sm">€</span>
        <input
          type="number"
          step="0.01"
          min="0"
          placeholder="0,00"
          value={prezzo}
          onChange={e => setPrezzo(e.target.value)}
          className="w-full pl-6 pr-2 py-1.5 border border-gray-200 rounded-lg text-sm text-right focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
          onKeyDown={e => e.key === "Enter" && handleSave()}
        />
      </div>

      {/* Margine badge */}
      <div className="w-14 text-center flex-shrink-0">
        {margineCalc !== null ? (
          <span className={`text-xs font-bold ${margineColor}`}>{margineCalc.toFixed(0)}%</span>
        ) : (
          <span className="text-xs text-gray-300">—</span>
        )}
      </div>

      {/* Salva */}
      <button
        onClick={handleSave}
        disabled={salvando || saved}
        data-testid={`btn-salva-prezzo-${prodotto.id}`}
        className={`flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
          saved
            ? "bg-green-100 text-green-700 border border-green-300"
            : "bg-[#5b7a6b] text-white hover:bg-[#4d6a5c]"
        } disabled:opacity-50`}
      >
        {saved ? <CheckCircle size={14} /> : <Save size={14} />}
      </button>
    </div>
  );
}

// ─── Vista principale ────────────────────────────────────────────────────────
export default function BulkPrezziView({ onClose }) {
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [filtroFonte, setFiltroFonte] = useState("tutti");
  const [search, setSearch] = useState("");
  const [salvatiCount, setSalvatiCount] = useState(0);


  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/prodotti-vendita/?solo_attivi=false`);
      setProdotti(r.data || []);  // tutti, non solo senza prezzo
    } catch { toast.error("Errore caricamento"); }
    setLoading(false);
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const handleSave = async (id, payload) => {
    setSalvando(true);
    try {
      // Calcola margine_percentuale
      const cp = prodotti.find(p => p.id === id)?.costo_produzione || 0;
      const pv = payload.prezzo_vendita;
      const margine_euro = Math.round((pv - cp) * 100) / 100;
      const margine_percentuale = pv > 0 ? Math.round(((pv - cp) / pv) * 1000) / 10 : 0;
      const prezzo_ivato = Math.round(pv * (1 + (payload.iva || 10) / 100) * 100) / 100;

      await axios.put(`${API}/prodotti-vendita/${id}`, {
        ...prodotti.find(p => p.id === id),
        ...payload,
        margine_euro,
        margine_percentuale,
        prezzo_ivato
      });
      // Aggiorna stato locale immediatamente (prodotto sale in cima)
      setProdotti(prev => prev.map(p => p.id === id ? { ...p, ...payload } : p));
      setSalvatiCount(c => c + 1);
    } catch { toast.error("Errore salvataggio"); }
    setSalvando(false);
  };

  const prodottiFiltrati = prodotti
    .filter(p => {
      if (filtroFonte !== "tutti" && p.fonte !== filtroFonte) return false;
      if (search && !p.nome?.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    })
    .sort((a, b) => {
      const aHasPrice = (a.prezzo_vendita || 0) > 0;
      const bHasPrice = (b.prezzo_vendita || 0) > 0;
      if (aHasPrice && !bHasPrice) return -1;
      if (!aHasPrice && bHasPrice) return 1;
      return (a.nome || "").localeCompare(b.nome || "", "it");
    });

  const [prezzoFisso, setPrezzoFisso] = useState("");

  const applicaMargineGlobale = (pct) => {
    const conCosto = prodottiFiltrati.filter(p => (parseFloat(p.costo_produzione) || 0) > 0);
    if (conCosto.length === 0) { toast.error("Nessun prodotto con costo disponibile nel filtro corrente"); return; }
    toast.info(`Applico ${pct}% a ${conCosto.length} prodotti con costo...`);
    conCosto.forEach(async p => {
      const costo = parseFloat(p.costo_produzione) || 0;
      const prezzo = calcolaPrezzoDaMargine(costo, pct);
      await handleSave(p.id, { prezzo_vendita: prezzo, iva: p.iva || 10 });
    });
  };

  const applicaPrezzoFissoGlobale = () => {
    const pv = parseFloat(prezzoFisso);
    if (!pv || pv <= 0) { toast.error("Inserisci un prezzo fisso valido"); return; }
    toast.info(`Applico €${pv.toFixed(2)} a ${prodottiFiltrati.length} prodotti...`);
    prodottiFiltrati.forEach(async p => {
      await handleSave(p.id, { prezzo_vendita: pv, iva: p.iva || 10 });
    });
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div
        className="bg-gray-50 rounded-t-2xl sm:rounded-2xl shadow-2xl w-full max-w-4xl max-h-[95vh] sm:max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-[#4d6a5c] text-white px-6 py-4 rounded-t-2xl flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="font-bold text-lg flex items-center gap-2">
              <Tag size={20} /> Imposta Prezzi di Vendita
            </h2>
            <p className="text-white/70 text-sm">
              {loading ? "Caricamento..." : (() => {
                const conPrezzo = prodotti.filter(p => (p.prezzo_vendita || 0) > 0).length;
                const senza = prodotti.length - conPrezzo;
                return `${prodotti.length} prodotti · ${senza} senza prezzo · ${salvatiCount} aggiornati`;
              })()}
            </p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white transition-colors">
            <X size={22} />
          </button>
        </div>

        {/* Toolbar */}
        <div className="px-4 py-3 bg-white border-b border-gray-100 flex flex-wrap gap-3 items-center flex-shrink-0">
          {/* Ricerca */}
          <input
            data-testid="search-bulk-prezzi"
            type="text"
            placeholder="Cerca prodotto..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm flex-1 min-w-[160px] focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
          />
          {/* Filtro fonte */}
          <select
            value={filtroFonte}
            onChange={e => setFiltroFonte(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="tutti">Tutti</option>
            <option value="interno">Nostri</option>
            <option value="acquaviva">Acquaviva</option>
            <option value="esterno">Esterni</option>
          </select>
          {/* Applica margine globale (solo prodotti con costo) */}
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-xs text-gray-500 flex-shrink-0">Margine (con costo):</span>
            {[25, 30, 35, 40].map(pct => (
              <button
                key={pct}
                onClick={() => applicaMargineGlobale(pct)}
                data-testid={`btn-margine-globale-${pct}`}
                className="px-3 py-1.5 bg-[#f2f6f3] border border-[#cfdfd5] text-[#5b7a6b] rounded-lg text-xs hover:bg-[#dce8e0] transition-all font-medium"
              >
                {pct}%
              </button>
            ))}
          </div>
          {/* Prezzo fisso a tutti */}
          <div className="flex items-center gap-1 border-l pl-3">
            <span className="text-xs text-gray-500 flex-shrink-0">Prezzo fisso:</span>
            <div className="relative w-24">
              <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">€</span>
              <input
                type="number" step="0.05" min="0" placeholder="0.00"
                value={prezzoFisso}
                onChange={e => setPrezzoFisso(e.target.value)}
                className="w-full pl-5 pr-1 py-1.5 border border-gray-200 rounded-lg text-xs text-right focus:outline-none focus:ring-2 focus:ring-orange-400"
              />
            </div>
            <button
              onClick={applicaPrezzoFissoGlobale}
              className="px-3 py-1.5 bg-orange-50 border border-orange-200 text-orange-700 rounded-lg text-xs hover:bg-orange-100 transition-all font-medium"
            >
              Applica
            </button>
          </div>
          <p className="text-xs text-gray-400 ml-auto">{prodottiFiltrati.length} prodotti</p>
        </div>

        {/* Lista prodotti */}
        <div className="overflow-y-auto flex-1 p-4 space-y-2">
          {loading ? (
            <div className="text-center py-20 text-gray-400">Caricamento...</div>
          ) : prodottiFiltrati.length === 0 ? (
            <div className="text-center py-20">
              <CheckCircle size={40} className="mx-auto text-green-400 mb-3" />
              <p className="text-gray-600 font-semibold">Nessun prodotto trovato.</p>
              <button onClick={onClose} className="mt-4 px-6 py-2 bg-[#5b7a6b] text-white rounded-lg text-sm">
                Chiudi
              </button>
            </div>
          ) : (() => {
            const conPrezzo = prodottiFiltrati.filter(p => (p.prezzo_vendita || 0) > 0);
            const senzaPrezzo = prodottiFiltrati.filter(p => !p.prezzo_vendita || p.prezzo_vendita <= 0);
            return (
              <>
                {senzaPrezzo.map(p => (
                  <RigaProdotto key={p.id} prodotto={p} onSave={handleSave} salvando={salvando} />
                ))}
                {conPrezzo.length > 0 && (
                  <>
                    <div className="flex items-center gap-3 py-2">
                      <div className="flex-1 border-t border-gray-200" />
                      <span className="text-xs text-gray-400 font-medium flex-shrink-0">
                        {conPrezzo.length} prodotti con prezzo
                      </span>
                      <div className="flex-1 border-t border-gray-200" />
                    </div>
                    {conPrezzo.map(p => (
                      <RigaProdotto key={p.id} prodotto={p} onSave={handleSave} salvando={salvando} />
                    ))}
                  </>
                )}
              </>
            );
          })()}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-200 bg-white rounded-b-2xl flex items-center justify-between flex-shrink-0">
          <p className="text-sm text-gray-500">
            {salvatiCount > 0 && (
              <span className="text-green-600 font-semibold">{salvatiCount} prezzi salvati</span>
            )}
          </p>
          <button
            onClick={onClose}
            className="px-5 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-all"
          >
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
}
