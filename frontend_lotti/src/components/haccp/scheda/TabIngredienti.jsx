/**
 * TabIngredienti.jsx — Tab Ingredienti di SchedaProdottoView
 */
import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Search, X, Edit, Plus, Minus, Trash2, Package, RefreshCw, GripVertical
} from "lucide-react";
import { API } from "../../../utils/constants";
import { formatCosto, InlinePrezzoDizionario } from "./utils";
import OpenFoodFactsLookup from "@/components/shared/OpenFoodFactsLookup";

const TabIngredienti = ({ ricetta, onUpdated }) => {
  const [dettaglio, setDettaglio] = useState(null);
  const [ingredientiDB, setIngredientiDB] = useState([]);
  const [tracciabilita, setTracciabilita] = useState({});
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [nuovoIng, setNuovoIng] = useState({ nome: "", quantita: "", unita: "g" });
  const [suggerimenti, setSuggerimenti] = useState([]);
  const [prodottoSel, setProdottoSel] = useState(null);
  const [filtroAcquaviva, setFiltroAcquaviva] = useState(false);
  const [semilavorati, setSemilavorati] = useState([]);
  const [editIdx, setEditIdx] = useState(null);
  const [editIng, setEditIng] = useState({ quantita: "", unita: "g" });
  const dropBlockRef = useRef(false);
  const [dragIdx, setDragIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [offOpen, setOffOpen] = useState(false);

  const carica = useCallback(async () => {
    if (!ricetta?.id) return;
    setLoading(true);
    try {
      const [rCosto, rRicetta] = await Promise.all([
        axios.get(`${API}/food-cost/calcola/${ricetta.id}`),
        axios.get(`${API}/ricette/${ricetta.id}`)
      ]);
      setDettaglio(rCosto.data);
      setIngredientiDB(rRicetta.data?.ingredienti_dettaglio || []);
    } catch { toast.error("Errore caricamento ingredienti"); }
    finally { setLoading(false); }
  }, [ricetta?.id]);

  useEffect(() => { carica(); }, [carica]);

  // Provenienza FIFO derivata al volo (single source: lotto FIFO-attivo, non il
  // riferimento congelato all'import). Caricata a parte per non bloccare la lista.
  useEffect(() => {
    if (!ricetta?.id) { setTracciabilita({}); return; }
    let vivo = true;
    axios.get(`${API}/ricette/${ricetta.id}/tracciabilita-fifo`)
      .then(r => {
        if (!vivo) return;
        const mappa = {};
        for (const t of (r.data?.ingredienti || [])) {
          const k = (t.ingrediente || "").toLowerCase().trim();
          if (k) mappa[k] = t;
        }
        setTracciabilita(mappa);
      })
      .catch(() => { if (vivo) setTracciabilita({}); });
    return () => { vivo = false; };
  }, [ricetta?.id]);

  useEffect(() => {
    if (dropBlockRef.current) { dropBlockRef.current = false; return; }
    const timer = setTimeout(() => {
      if (filtroAcquaviva) {
        if (nuovoIng.nome.length === 0) {
          setSuggerimenti(semilavorati.slice(0, 20));
        } else {
          const q = nuovoIng.nome.toLowerCase();
          setSuggerimenti(semilavorati.filter(p => {
            const nome = (p.nome_display || p.nome_normalizzato || "").toLowerCase();
            return nome.includes(q) || q.split(" ").every(w => w.length < 2 || nome.includes(w));
          }));
        }
      } else if (nuovoIng.nome.length >= 2) {
        const q = encodeURIComponent(nuovoIng.nome);
        Promise.all([
          axios.get(`${API}/food-cost/dizionario/search?q=${q}`).then(r => r.data || []).catch(() => []),
          axios.get(`${API}/ingredienti/smart-search?q=${q}`).then(r => r.data?.risultati || []).catch(() => []),
        ]).then(([diz, xml]) => {
          const visti = new Set();
          const out = [];
          // 1) Dizionario (nomi canonici, ideali per FIFO/genealogia)
          for (const p of diz) {
            const chiave = (p.nome_display || p.nome_normalizzato || "").toLowerCase().trim();
            if (!chiave || visti.has(chiave)) continue;
            visti.add(chiave);
            out.push({ ...p, _fonte: "diz" });
          }
          // 2) Righe delle fatture XML non già coperte dal dizionario
          for (const r of xml) {
            const desc = (r.descrizione || "").trim();
            const chiave = desc.toLowerCase().slice(0, 28);
            if (!desc || visti.has(chiave)) continue;
            visti.add(chiave);
            const unitaKg = (r.unita_misura || "").toUpperCase().startsWith("KG");
            out.push({
              _fonte: "xml",
              id: null,
              nome_display: desc,
              nome_normalizzato: desc,
              fornitore: r.fornitore,
              data_fattura: r.data_fattura,
              fattura_ref: r.numero_fattura,
              prezzo_kg: unitaKg ? r.prezzo_unitario : null,
              prezzo_riga: r.prezzo_pezzo || r.prezzo_unitario,
              unita_misura_xml: r.unita_misura,
            });
          }
          setSuggerimenti(out.slice(0, 24));
        }).catch(() => setSuggerimenti([]));
      } else {
        setSuggerimenti([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  // dropBlockRef.current è una ref (mutabile senza re-render); axios/API sono module-level
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nuovoIng.nome, filtroAcquaviva, semilavorati]);

  useEffect(() => {
    if (!filtroAcquaviva) return;
    axios.get(`${API}/food-cost/semilavorati-acquaviva`)
      .then(r => { setSemilavorati(r.data || []); setSuggerimenti(r.data?.slice(0, 20) || []); })
      .catch(() => {});
  }, [filtroAcquaviva]);

  const calcolaCosto = (quantita, unita, prezzoKg, costoPezzo) => {
    const qty = parseFloat(quantita);
    if (isNaN(qty) || qty <= 0) return null;
    if (unita === "pz" && costoPezzo > 0) return qty * costoPezzo;
    if (!prezzoKg) return null;
    let kg = qty;
    if (unita === "g" || unita === "ml") kg /= 1000;
    return kg * prezzoKg;
  };

  const aggiungiIngrediente = async () => {
    const nomeFinale = (prodottoSel?.nome_display || prodottoSel?.nome_normalizzato || nuovoIng.nome || "").trim();
    if (!nomeFinale) { toast.error("Seleziona un ingrediente"); return; }
    if (!nuovoIng.quantita || parseFloat(nuovoIng.quantita) <= 0) { toast.error("Inserisci una quantità valida"); return; }
    const cp = prodottoSel?.costo_per_pezzo || null;
    const costo = prodottoSel ? calcolaCosto(nuovoIng.quantita, nuovoIng.unita, prodottoSel.prezzo_kg, cp) : null;
    const ingrediente = {
      nome: nomeFinale,
      quantita: parseFloat(nuovoIng.quantita),
      unita_misura: nuovoIng.unita,
      prodotto_dizionario_id: prodottoSel?.id || null,
      prezzo_kg: prodottoSel?.prezzo_kg || null,
      costo_per_pezzo: cp,
      is_acquaviva: prodottoSel?.is_acquaviva || false,
      costo_calcolato: costo != null ? parseFloat(costo) : null,
      fornitore: prodottoSel?.fornitore || null,
      fattura_ref: prodottoSel?.fattura_ref || null
    };
    try {
      await axios.post(`${API}/food-cost/aggiorna-ingredienti-ricetta`, {
        ricetta_id: ricetta.id,
        ingredienti_dettaglio: [...ingredientiDB, ingrediente]
      });
      toast.success("Ingrediente aggiunto");
      setNuovoIng({ nome: "", quantita: "", unita: "g" });
      setSuggerimenti([]);
      setProdottoSel(null);
      setShowForm(false);
      setFiltroAcquaviva(false);
      carica();
      onUpdated && onUpdated();
    } catch { toast.error("Errore salvataggio"); }
  };

  const rimuoviIngrediente = async (idx) => {
    try {
      const rRicetta = await axios.get(`${API}/ricette/${ricetta.id}`);
      const ingrCorrenti = rRicetta.data?.ingredienti_dettaglio || [];
      await axios.post(`${API}/food-cost/aggiorna-ingredienti-ricetta`, {
        ricetta_id: ricetta.id,
        ingredienti_dettaglio: ingrCorrenti.filter((_, i) => i !== idx)
      });
      toast.success("Ingrediente rimosso");
      carica();
      onUpdated && onUpdated();
    } catch { toast.error("Errore"); }
  };

  const handleDragStart = (idx) => setDragIdx(idx);
  const handleDragOver = (e, idx) => { e.preventDefault(); setDragOverIdx(idx); };
  const handleDrop = async (e, targetIdx) => {
    e.preventDefault();
    if (dragIdx === null || dragIdx === targetIdx) { setDragIdx(null); setDragOverIdx(null); return; }
    const savedDragIdx = dragIdx;
    setDragIdx(null);
    setDragOverIdx(null);
    try {
      const rRicetta = await axios.get(`${API}/ricette/${ricetta.id}`);
      const lista = [...(rRicetta.data?.ingredienti_dettaglio || [])];
      const [spostato] = lista.splice(savedDragIdx, 1);
      lista.splice(targetIdx, 0, spostato);
      await axios.post(`${API}/food-cost/aggiorna-ingredienti-ricetta`, {
        ricetta_id: ricetta.id,
        ingredienti_dettaglio: lista
      });
      carica();
    } catch { toast.error("Errore riordinamento"); }
  };
  const handleDragEnd = () => { setDragIdx(null); setDragOverIdx(null); };

  const salvaModificaIngrediente = async (idx) => {
    try {
      const rRicetta = await axios.get(`${API}/ricette/${ricetta.id}`);
      const ingrCorrenti = rRicetta.data?.ingredienti_dettaglio || [];
      if (ingrCorrenti.length === 0) { toast.error("Impossibile salvare: ingredienti non caricati"); return; }
      const nuovi = ingrCorrenti.map((ing, i) => {
        if (i !== idx) return ing;
        return { ...ing, quantita: parseFloat(editIng.quantita) || ing.quantita, unita_misura: editIng.unita };
      });
      await axios.post(`${API}/food-cost/aggiorna-ingredienti-ricetta`, {
        ricetta_id: ricetta.id,
        ingredienti_dettaglio: nuovi
      });
      toast.success("Ingrediente aggiornato");
      setEditIdx(null);
      carica();
      onUpdated && onUpdated();
    } catch (e) {
      const det = e?.response?.data?.detail;
      const msg = Array.isArray(det) ? det.map(d => d.msg).join(", ") : (typeof det === "string" ? det : e?.message || "Errore sconosciuto");
      toast.error("Errore salvataggio: " + msg);
    }
  };

  if (loading) return <div className="flex items-center justify-center py-16 text-gray-400"><RefreshCw className="animate-spin mr-2" size={18} /> Caricamento...</div>;

  const ingredienti = dettaglio?.ingredienti || [];
  const costoTot = dettaglio?.costo_totale || 0;
  const porzioni = dettaglio?.porzioni || ricetta?.porzioni || 1;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        {ingredienti.map((ing, idx) => (
          <div
            key={ing.id || ing.ingrediente_id || ing.nome || ing.ingrediente}
            draggable
            onDragStart={() => handleDragStart(idx)}
            onDragOver={(e) => handleDragOver(e, idx)}
            onDrop={(e) => handleDrop(e, idx)}
            onDragEnd={handleDragEnd}
            className={`rounded-xl border transition-all ${
              dragOverIdx === idx && dragIdx !== idx
                ? "border-[#5b7a6b] bg-[#f2f6f3] scale-[1.01]"
                : dragIdx === idx
                ? "opacity-40"
                : ing.is_acquaviva ? "bg-[#f2f6f3] border-[#cfdfd5]" : "bg-gray-50 border-gray-100"
            }`}
          >
            {editIdx === idx ? (
              <div className="p-3 space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-base font-semibold text-gray-800 capitalize flex-1 truncate">{ing.nome}</span>
                  <button onClick={() => setEditIdx(null)} className="text-gray-400 hover:text-red-500 p-1.5 rounded-lg hover:bg-gray-100"><X size={18} /></button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-semibold text-gray-500">Quantità</label>
                    <div className="mt-1 flex items-stretch gap-1">
                      <button type="button" title="Diminuisci"
                        onClick={() => { const s = (editIng.unita === "kg" || editIng.unita === "lt") ? 0.1 : editIng.unita === "pz" ? 1 : 10; setEditIng({ ...editIng, quantita: String(Math.round(Math.max(0, (parseFloat(editIng.quantita) || 0) - s) * 100) / 100) }); }}
                        className="flex w-11 items-center justify-center rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200"><Minus size={18} /></button>
                      <input type="number" value={editIng.quantita} onChange={e => setEditIng({ ...editIng, quantita: e.target.value })}
                        className="w-full px-2 py-2.5 border border-gray-200 rounded-lg text-base text-center font-semibold" min="0" step="0.1" />
                      <button type="button" title="Aumenta"
                        onClick={() => { const s = (editIng.unita === "kg" || editIng.unita === "lt") ? 0.1 : editIng.unita === "pz" ? 1 : 10; setEditIng({ ...editIng, quantita: String(Math.round(((parseFloat(editIng.quantita) || 0) + s) * 100) / 100) }); }}
                        className="flex w-11 items-center justify-center rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200"><Plus size={18} /></button>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-500">Unità</label>
                    <select value={editIng.unita} onChange={e => setEditIng({ ...editIng, unita: e.target.value })}
                      className="w-full mt-1 px-3 py-2.5 border border-gray-200 rounded-lg text-base bg-white">
                      <option value="g">g</option><option value="kg">kg</option>
                      <option value="ml">ml</option><option value="lt">lt</option><option value="pz">pz</option>
                    </select>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setEditIdx(null)} className="flex-1 py-2.5 bg-gray-100 text-gray-600 rounded-lg text-sm font-semibold hover:bg-gray-200">Annulla</button>
                  <button onClick={() => salvaModificaIngrediente(idx)} className="flex-1 py-2.5 bg-[#5b7a6b] text-white rounded-lg text-sm font-bold hover:bg-[#4d6a5c]">Salva</button>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-2 p-2.5">
                <div className="flex-shrink-0 cursor-grab active:cursor-grabbing text-gray-300 hover:text-gray-500 mt-0.5 pt-0.5" title="Trascina per riordinare">
                  <GripVertical size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div onClick={() => { setEditIdx(idx); setEditIng({ quantita: String(ing.quantita || ""), unita: ing.unita_misura || ing.unita || "g" }); }}
                    className="cursor-pointer" title="Tocca per modificare la quantità">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-gray-800 capitalize truncate">{ing.nome}</span>
                      {ing.is_acquaviva && <span className="text-[10px] bg-[#e8efe9] text-[#5b7a6b] px-1.5 rounded-full">Acquaviva</span>}
                    </div>
                    <p className="text-sm text-gray-500">
                      {ing.quantita} {ing.unita_misura || ing.unita || "g"}
                      {ing.prezzo_kg > 0 && <span className="ml-2 text-gray-400">@€{Number(ing.prezzo_kg).toFixed(2)}/kg</span>}
                      {ing.costo_calcolato != null && <span className="ml-2 text-green-600 font-semibold">→ €{formatCosto(ing.costo_calcolato)}</span>}
                    </p>
                  </div>
                  {(() => {
                    const prov = tracciabilita[(ing.nome || "").toLowerCase().trim()];
                    if (!prov) return null;
                    const comp = prov.composizione || [];
                    const all = prov.allergeni || [];
                    const azo = prov.avviso_coloranti_azoici || [];
                    return (
                      <>
                        {prov.trovato && (
                          <p className="text-[11px] text-gray-400 mt-0.5 truncate" title={`${prov.fornitore || ""}${prov.prodotto ? " · " + prov.prodotto : ""}`}>
                            🧾 da: <span className="text-gray-500 font-medium">{prov.fornitore || "—"}</span>
                            {prov.data_fattura ? ` · ${prov.data_fattura}` : ""}
                            {prov.data_scadenza ? ` · scad ${prov.data_scadenza}` : ""}
                          </p>
                        )}
                        {comp.length > 0 && (
                          <p className="text-[10px] text-gray-400 mt-0.5 leading-snug">↳ {comp.join(", ")}</p>
                        )}
                        {all.length > 0 && (
                          <p className="text-[10px] text-amber-600 mt-0.5 leading-snug">allergeni: {all.join(", ")}</p>
                        )}
                        {azo.length > 0 && (
                          <p className="text-[10px] text-amber-700 mt-0.5 leading-snug">⚠ coloranti azoici ({azo.join(", ")}): possono influire su attività/attenzione dei bambini</p>
                        )}
                      </>
                    );
                  })()}
                  {(ing.costo_calcolato == null && !(ing.prezzo_kg > 0)) && !ing.is_acquaviva && (
                    <InlinePrezzoDizionario ing={ing} ricettaId={ricetta?.id} onSaved={carica} />
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button onClick={() => { setEditIdx(idx); setEditIng({ quantita: String(ing.quantita || ""), unita: ing.unita_misura || ing.unita || "g" }); }}
                    className="text-gray-400 hover:text-[#5b7a6b] hover:bg-[#f2f6f3] p-2 rounded-lg" title="Modifica quantità">
                    <Edit size={18} />
                  </button>
                  <button onClick={() => rimuoviIngrediente(idx)} className="text-gray-400 hover:text-red-600 hover:bg-red-50 p-2 rounded-lg" title="Elimina ingrediente">
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
        {ingredienti.length === 0 && (
          <div className="text-center py-8 text-gray-400">
            <Package size={32} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">Nessun ingrediente</p>
          </div>
        )}
      </div>

      {showForm ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-green-800">Aggiungi Ingrediente</p>
            <label className="flex items-center gap-2 cursor-pointer">
              <span className="text-xs text-gray-500">Acquaviva</span>
              <button type="button"
                onClick={() => { setFiltroAcquaviva(!filtroAcquaviva); setNuovoIng({ nome: "", quantita: "", unita: filtroAcquaviva ? "g" : "pz" }); setProdottoSel(null); setSuggerimenti([]); }}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${filtroAcquaviva ? "bg-[#5b7a6b]" : "bg-gray-300"}`}>
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform shadow ${filtroAcquaviva ? "translate-x-4" : "translate-x-1"}`} />
              </button>
            </label>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
            <input type="text" value={nuovoIng.nome}
              onChange={e => setNuovoIng({ ...nuovoIng, nome: e.target.value })}
              onBlur={() => setTimeout(() => setSuggerimenti([]), 150)}
              placeholder={filtroAcquaviva ? "Cerca prodotto Acquaviva..." : "Cerca nel dizionario e nelle fatture XML..."}
              className="w-full pl-9 pr-28 py-2 border border-gray-200 rounded-xl text-sm focus:ring-2 focus:ring-green-400 focus:outline-none" />
            <button type="button" onClick={() => setOffOpen(true)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-bold px-2 py-1 rounded-lg bg-[#e8efe9] text-[#3f5a4e] hover:bg-[#dce8e0]"
              title="Cerca su Open Food Facts (suggerimento)">Open Food Facts</button>
            {offOpen && (
              <OpenFoodFactsLookup
                queryIniziale={nuovoIng.nome}
                onPick={(nome) => setNuovoIng((v) => ({ ...v, nome }))}
                onClose={() => setOffOpen(false)}
              />
            )}
            {suggerimenti.length > 0 && (
              <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-xl shadow-xl max-h-80 overflow-y-auto">
                {suggerimenti.map((p, i) => {
                  const prezzoTxt = p._fonte === "xml"
                    ? (p.prezzo_kg ? `€${Number(p.prezzo_kg).toFixed(2)}/kg` : `€${Number(p.prezzo_riga || 0).toFixed(4)}/${(p.unita_misura_xml || "u").toLowerCase()}`)
                    : (p.costo_per_pezzo > 0 ? `€${p.costo_per_pezzo.toFixed(4)}/pz` : `€${(p.prezzo_kg || 0).toFixed(2)}/kg`);
                  return (
                  <div key={p.id || i} onMouseDown={e => {
                    e.preventDefault();
                    const nome = p.nome_display || p.nome_normalizzato;
                    dropBlockRef.current = true;
                    setNuovoIng({ nome, quantita: nuovoIng.quantita, unita: p.is_acquaviva ? "pz" : nuovoIng.unita });
                    setProdottoSel(p);
                    setSuggerimenti([]);
                  }} className="flex items-start gap-2 px-3 py-3 cursor-pointer hover:bg-green-50 border-b border-gray-100 last:border-0">
                    {p.immagine_url && <img src={p.immagine_url} alt="" className="w-10 h-10 object-contain rounded shrink-0" />}
                    <div className="min-w-0 flex-1">
                      <div className="text-[15px] font-semibold text-gray-800 capitalize leading-snug break-words">
                        {p._fonte === "xml" && <span className="text-[9px] font-bold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded mr-1 align-middle normal-case">FATTURA</span>}
                        {p.nome_display || p.nome_normalizzato}
                      </div>
                      {p.fornitore && <div className="text-[12px] text-gray-500 mt-0.5 break-words">🏭 {p.fornitore}</div>}
                      {p._fonte === "xml" && (p.fattura_ref || p.data_fattura) && (
                        <div className="text-[12px] text-gray-500 break-words">🧾 {p.fattura_ref ? `Fattura n. ${p.fattura_ref}` : "Fattura"}{p.data_fattura ? ` · ${p.data_fattura}` : ""}</div>
                      )}
                      <div className="mt-1 flex flex-wrap items-center gap-x-2">
                        <span className="text-[13px] font-bold text-green-600">{prezzoTxt}</span>
                        {p.quantita_disponibile_kg > 0 && <span className="text-[12px] text-gray-400">· {p.quantita_disponibile_kg.toFixed(1)} kg disponibili</span>}
                      </div>
                    </div>
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          {prodottoSel && (
            <div className="px-3 py-2.5 bg-green-100 rounded-xl text-green-900 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-semibold capitalize break-words">✓ {prodottoSel.nome_display || prodottoSel.nome_normalizzato}</div>
                {prodottoSel.fornitore && <div className="text-[12px] text-green-700 break-words">🏭 {prodottoSel.fornitore}</div>}
                {prodottoSel._fonte === "xml" && (prodottoSel.fattura_ref || prodottoSel.data_fattura) && (
                  <div className="text-[12px] text-green-700 break-words">🧾 {prodottoSel.fattura_ref ? `Fattura n. ${prodottoSel.fattura_ref}` : "Fattura"}{prodottoSel.data_fattura ? ` · ${prodottoSel.data_fattura}` : ""}</div>
                )}
              </div>
              <button onClick={() => setProdottoSel(null)} className="text-green-700 hover:text-red-500 shrink-0"><X size={16} /></button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-500">Quantità *</label>
              <input type="number" value={nuovoIng.quantita}
                onChange={e => setNuovoIng({ ...nuovoIng, quantita: e.target.value })}
                min="0" step="0.1" placeholder="es. 500"
                className="w-full mt-1 px-3 py-2 border border-gray-200 rounded-xl text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-500">Unità</label>
              <select value={nuovoIng.unita} onChange={e => setNuovoIng({ ...nuovoIng, unita: e.target.value })}
                className="w-full mt-1 px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white">
                <option value="g">grammi (g)</option>
                <option value="kg">kg</option>
                <option value="ml">ml</option>
                <option value="lt">lt</option>
                <option value="pz">pezzi (pz)</option>
              </select>
            </div>
          </div>

          {prodottoSel && nuovoIng.quantita && (() => {
            const cp = prodottoSel.costo_per_pezzo || null;
            const val = calcolaCosto(nuovoIng.quantita, nuovoIng.unita, prodottoSel.prezzo_kg, cp);
            if (val == null) return null;
            return <div className="bg-[#f2f6f3] border border-[#cfdfd5] rounded-xl px-3 py-2 text-xs text-[#3f5a4e]">
              Costo stimato: <strong>€{formatCosto(val)}</strong>
            </div>;
          })()}

          <div className="flex gap-2">
            <button onClick={() => { setShowForm(false); setFiltroAcquaviva(false); setNuovoIng({ nome: "", quantita: "", unita: "g" }); setSuggerimenti([]); setProdottoSel(null); }}
              className="flex-1 py-2 bg-gray-100 text-gray-700 rounded-xl text-sm hover:bg-gray-200">Annulla</button>
            <button onClick={aggiungiIngrediente}
              disabled={(!nuovoIng.nome.trim() && !prodottoSel) || !nuovoIng.quantita}
              className="flex-1 py-2 bg-green-600 text-white rounded-xl text-sm font-semibold hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed">Aggiungi</button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button onClick={() => { setFiltroAcquaviva(false); setShowForm(true); }}
            className="flex-1 py-2.5 border-2 border-dashed border-gray-200 text-gray-500 rounded-xl text-sm hover:border-green-400 hover:text-green-600 transition-colors flex items-center justify-center gap-2">
            <Plus size={16} /> Ingrediente normale
          </button>
          <button onClick={() => { setFiltroAcquaviva(true); setNuovoIng({ nome: "", quantita: "", unita: "pz" }); setShowForm(true); }}
            className="flex-1 py-2.5 border-2 border-dashed border-[#cfdfd5] text-[#5b7a6b] rounded-xl text-sm hover:border-[#b8d0c2] hover:text-[#5b7a6b] transition-colors flex items-center justify-center gap-2">
            <Plus size={16} /> Acquaviva
          </button>
        </div>
      )}
    </div>
  );
};

export default TabIngredienti;
