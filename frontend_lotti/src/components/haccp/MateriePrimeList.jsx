/**
 * MateriePrimeList — mostra TUTTI i prodotti dalle fatture reali, raggruppati per fornitore.
 * Molto più completo della vecchia versione che mostrava solo i 33 prodotti matchati.
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import { norm } from "../../utils/textNormalize";
import { Search, Package, ChevronDown, ChevronRight, RefreshCw, FileText } from "lucide-react";
import { API } from "../../utils/constants";
import SchedaFonteModal from "./SchedaFonteModal";

// ── Fuzzy matching (esportato per IngredienteAutocomplete) ────────────────────
export const fuzzyMatch = (text, query) => {
  if (!text || !query) return { match: false, score: 0 };
  const tl = norm(text);
  const ql = norm(query);
  if (tl.includes(ql)) return { match: true, score: tl.startsWith(ql) ? 100 : 85 };
  const words = tl.split(/\s+/);
  for (const w of words) {
    if (w.startsWith(ql)) return { match: true, score: 90 };
  }
  return { match: false, score: 0 };
};

// ── IngredienteAutocomplete — usato nel form ingredienti ricette ──────────────
export const IngredienteAutocomplete = ({ value, onChange, onSelect, materiePrime, placeholder }) => {
  const [open, setOpen] = useState(false);
  const suggestions = useMemo(() => {
    if (value.length < 2) return [];
    return materiePrime
      .map(m => ({ ...m, ...fuzzyMatch(m.materia_prima || m.descrizione || "", value) }))
      .filter(m => m.match)
      .sort((a, b) => b.score - a.score)
      .slice(0, 10);
  }, [value, materiePrime]);

  return (
    <div className="relative flex-1">
      <input type="text" value={value}
        onChange={e => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        onKeyDown={e => { if (e.key === "Enter" && suggestions.length > 0) { e.preventDefault(); onSelect(suggestions[0].materia_prima || suggestions[0].descrizione); onChange(""); setOpen(false); } }}
        placeholder={placeholder}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#5b7a6b] focus:outline-none" />
      {open && suggestions.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {suggestions.map((item, i) => (
            <div key={i} onClick={() => { onSelect(item.materia_prima || item.descrizione); onChange(""); setOpen(false); }}
              className={`px-3 py-2 cursor-pointer hover:bg-[#f2f6f3] flex justify-between items-center ${i === 0 ? "bg-[#f2f6f3] border-l-4 border-[#5b7a6b]" : ""}`}>
              <span className="text-sm font-medium text-gray-900">{item.materia_prima || item.descrizione}</span>
              {item.azienda && <span className="text-xs text-gray-400 ml-2 truncate max-w-[120px]">{item.azienda}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── Card singolo fornitore ────────────────────────────────────────────────────
const CardFornitore = ({ gruppo, search }) => {
  const [aperto, setAperto] = useState(false);
  const [schedaProd, setSchedaProd] = useState(null);

  const prodottiFiltrati = useMemo(() => {
    if (!search) return gruppo.prodotti;
    const s = search.toLowerCase();
    return gruppo.prodotti.filter(p => p.descrizione.toLowerCase().includes(s));
  }, [gruppo.prodotti, search]);

  // Se stiamo cercando, apri sempre
  const isAperto = aperto || !!search;

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden mb-2">
      <button
        onClick={() => setAperto(!aperto)}
        className="w-full bg-gray-50 px-3 py-2 flex items-center justify-between hover:bg-gray-100 transition-colors">
        <div className="flex items-center gap-2">
          {isAperto ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
          <span className="font-semibold text-gray-800 text-sm">{gruppo.fornitore}</span>
        </div>
        <span className="text-xs bg-[#e8efe9] text-[#5b7a6b] font-bold px-2 py-0.5 rounded-full">
          {prodottiFiltrati.length}{search && prodottiFiltrati.length !== gruppo.totale_prodotti ? ` / ${gruppo.totale_prodotti}` : ""}
        </span>
      </button>

      {isAperto && (
        <div className="divide-y divide-gray-50">
          {prodottiFiltrati.length === 0 ? (
            <p className="px-3 py-2 text-xs text-gray-400 italic">Nessun prodotto corrisponde alla ricerca</p>
          ) : (
            prodottiFiltrati.map((prod, i) => (
              <div key={i} className="px-3 py-1.5 flex items-center justify-between gap-2 hover:bg-gray-50">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-900 truncate">{prod.descrizione}</p>
                  <p className="text-xs text-gray-400">
                    {prod.numero_fattura && <span>{prod.numero_fattura} • </span>}
                    {prod.data_fattura}
                    {prod.quantita && <span className="ml-2 text-gray-500">{prod.quantita} {prod.unita_misura}</span>}
                    {prod.prezzo > 0 && <span className="ml-2 font-medium text-green-700">€{Number(prod.prezzo).toFixed(2)}</span>}
                  </p>
                </div>
                <button onClick={() => setSchedaProd(prod)} title="Scheda / fonte: sito produttore, foto etichetta, allergeni"
                  className="shrink-0 text-[#5b7a6b] hover:text-[#3f5a4e] p-1">
                  <FileText size={15} />
                </button>
              </div>
            ))
          )}
        </div>
      )}
      {schedaProd && <SchedaFonteModal prodotto={schedaProd} onClose={() => setSchedaProd(null)} />}
    </div>
  );
};

// ── Componente principale ─────────────────────────────────────────────────────
const MateriePrimeList = () => {
  const [gruppi, setGruppi] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [mesi, setMesi] = useState(12); // default ultimi 12 mesi

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/materie-prime/da-fatture`, {
        params: { mesi }
      });
      setGruppi(res.data);
    } catch (e) {
      console.error("Errore materie prime:", e);
    }
    setLoading(false);
  }, [mesi]);

  useEffect(() => { fetch(); }, [fetch]);

  const totProdotti = gruppi.reduce((s, g) => s + g.totale_prodotti, 0);

  // Gruppi filtrati per ricerca
  const gruppiFiltrati = useMemo(() => {
    if (!search) return gruppi;
    const s = search.toLowerCase();
    return gruppi
      .map(g => ({
        ...g,
        prodotti: g.prodotti.filter(p => p.descrizione.toLowerCase().includes(s))
      }))
      .filter(g => g.prodotti.length > 0 || g.fornitore.toLowerCase().includes(s));
  }, [gruppi, search]);

  return (
    <div className="flex flex-col h-[calc(100vh-200px)]">
      {/* Header */}
      <div className="sticky top-0 bg-gray-50 z-10 pb-3 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 relative min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
            <input type="text" placeholder="Cerca prodotto o fornitore..."
              value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#5b7a6b] bg-white focus:outline-none" />
          </div>
          <select value={mesi} onChange={e => setMesi(Number(e.target.value))}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none">
            <option value={1}>Ultimo mese</option>
            <option value={3}>Ultimi 3 mesi</option>
            <option value={6}>Ultimi 6 mesi</option>
            <option value={12}>Ultimo anno</option>
            <option value={999}>Tutti</option>
          </select>
          <button onClick={fetch} disabled={loading}
            className="p-2 hover:bg-gray-100 rounded-lg text-gray-500 disabled:opacity-50">
            <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="bg-[#f2f6f3] text-[#5b7a6b] px-2 py-0.5 rounded font-medium">
            {loading ? "..." : `${totProdotti} prodotti • ${gruppi.length} fornitori`}
          </span>
          {search && (
            <span className="text-orange-600">
              Filtro: {gruppiFiltrati.reduce((s, g) => s + g.prodotti.length, 0)} risultati
            </span>
          )}
        </div>
      </div>

      {/* Lista */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="animate-spin text-[#5b7a6b] mr-2" size={24} />
            <span className="text-gray-500">Caricamento prodotti dalle fatture...</span>
          </div>
        ) : gruppiFiltrati.length === 0 ? (
          <div className="bg-white rounded-lg border p-8 text-center text-gray-500">
            <Package size={40} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">Nessun prodotto trovato</p>
            {search && (
              <button onClick={() => setSearch("")} className="mt-2 text-[#5b7a6b] text-sm underline">
                Cancella ricerca
              </button>
            )}
          </div>
        ) : (
          gruppiFiltrati.map(g => (
            <CardFornitore key={g.fornitore} gruppo={g} search={search} />
          ))
        )}
      </div>
    </div>
  );
};

export default MateriePrimeList;
