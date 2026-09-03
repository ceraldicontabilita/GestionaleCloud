/**
 * RegistroAllergeniView — Registro Allergeni (Reg. UE 1169/2011, Allegato II)
 * Matrice stampabile: ricette × 14 allergeni + QR code + mappatura manuale rapida
 */
import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import {
  AlertTriangle, Printer, Search, RefreshCw, X,
  QrCode, Zap, ChevronDown, ChevronRight
} from "lucide-react";

import { API } from "../../utils/constants";

const ALLERGENI_14 = [
  { id: "Glutine",            abbr: "GLU", color: "bg-yellow-100 text-yellow-800" },
  { id: "Crostacei",          abbr: "CRO", color: "bg-orange-100 text-orange-800" },
  { id: "Uova",               abbr: "UOV", color: "bg-yellow-100 text-yellow-800" },
  { id: "Pesce",              abbr: "PES", color: "bg-[#e8efe9] text-[#3f5a4e]" },
  { id: "Arachidi",           abbr: "ARA", color: "bg-amber-100 text-amber-800" },
  { id: "Soia",               abbr: "SOI", color: "bg-green-100 text-green-800" },
  { id: "Latte",              abbr: "LAT", color: "bg-[#e8efe9] text-[#3f5a4e]" },
  { id: "Frutta a guscio",    abbr: "GUS", color: "bg-amber-100 text-amber-800" },
  { id: "Sedano",             abbr: "SED", color: "bg-green-100 text-green-800" },
  { id: "Senape",             abbr: "SEN", color: "bg-yellow-100 text-yellow-800" },
  { id: "Sesamo",             abbr: "SES", color: "bg-amber-100 text-amber-800" },
  { id: "Anidride solforosa", abbr: "SO2", color: "bg-gray-100 text-gray-700" },
  { id: "Lupini",             abbr: "LUP", color: "bg-[#f3e8d4] text-[#5c4830]" },
  { id: "Molluschi",          abbr: "MOL", color: "bg-[#e8efe9] text-[#3f5a4e]" },
];


// ── QR Modal ────────────────────────────────────────────────────────────────
const QRModal = ({ ricetta, onClose }) => {
  if (!ricetta) return null;
  const alls = ricetta.allergeni || [];
  const testo = alls.length > 0
    ? `ALLERGENI: ${alls.join(", ")}`
    : "Nessun allergene dichiarato — verificare con il personale";
  const url = `${window.location.origin}${process.env.PUBLIC_URL || ""}/#qr-allergeni?r=${encodeURIComponent(ricetta.nome)}&a=${encodeURIComponent(alls.join(","))}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl p-6 max-w-xs w-full text-center">
        <button onClick={onClose} className="absolute top-3 right-3 text-gray-400 hover:text-gray-600">
          <X size={18} />
        </button>
        <p className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-1">QR Allergeni</p>
        <h3 className="text-base font-bold text-gray-800 mb-3 leading-tight">{ricetta.nome}</h3>

        <div className="flex justify-center mb-3">
          <QRCodeSVG
            value={testo}
            size={160}
            level="M"
            includeMargin
            fgColor="#1f2937"
          />
        </div>

        {alls.length > 0 ? (
          <div className="flex flex-wrap gap-1 justify-center mb-3">
            {alls.map(a => (
              <span key={a} className="text-[10px] bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-medium">
                {a}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-amber-600 mb-3">Nessun allergene dichiarato</p>
        )}

        <p className="text-[10px] text-gray-400 italic mb-4">
          Reg. UE 1169/2011 — Allegato II
        </p>

        <button
          onClick={() => window.print()}
          className="w-full py-2 bg-gray-800 text-white rounded-xl text-sm font-semibold hover:bg-gray-700 transition-colors flex items-center justify-center gap-2"
        >
          <Printer size={14} /> Stampa QR
        </button>
      </div>
    </div>
  );
};


// ── Pannello completamento allergeni ────────────────────────────────────────
const PannelloMancanti = ({ ricette, onAggiornato, onAutoRilevaAll, autoLoadingAll }) => {
  const [aperto, setAperto]     = useState(true);
  const [editor, setEditor]     = useState(null);   // ricetta in modifica
  const [selezione, setSel]     = useState({});      // ricetta_id -> Set di allergeni
  const [saving, setSaving]     = useState(false);
  const [autoLoading, setAutoL] = useState(null);   // id ricetta in auto-detect

  const ricetteSenza = ricette.filter(r => !r.allergeni || r.allergeni.length === 0);
  if (ricetteSenza.length === 0) return null;

  const toggleAllergen = (rid, all) => {
    setSel(prev => {
      const cur = new Set(prev[rid] || []);
      cur.has(all) ? cur.delete(all) : cur.add(all);
      return { ...prev, [rid]: cur };
    });
  };

  const salva = async (ricetta) => {
    setSaving(true);
    try {
      const alls = Array.from(selezione[ricetta.id] || []);
      await axios.post(`${API}/food-cost/aggiorna-allergeni-ricetta`, {
        ricetta_id: ricetta.id,
        allergeni: alls,
        nutrizionale: {}
      });
      onAggiornato();
      setEditor(null);
    } catch { toast.error("Errore salvataggio"); }
    finally { setSaving(false); }
  };

  const autoRileva = async (ricetta) => {
    setAutoL(ricetta.id);
    try {
      const res = await axios.post(`${API}/food-cost/auto-rileva-allergeni-ricetta/${ricetta.id}`);
      const trovati = res.data?.allergeni_suggeriti || [];
      setSel(prev => ({ ...prev, [ricetta.id]: new Set(trovati) }));
      if (trovati.length > 0) setEditor(ricetta.id);
    } catch { }
    finally { setAutoL(null); }
  };

  return (
    <div className="mb-4 rounded-xl border border-amber-200 overflow-hidden no-print">
      <div className="w-full flex items-center gap-2 px-4 py-3 bg-amber-50 hover:bg-amber-100 transition-colors">
        <button
          onClick={() => setAperto(v => !v)}
          className="flex items-center gap-2 flex-1"
          data-testid="toggle-allergeni-mancanti"
        >
          <AlertTriangle size={16} className="text-amber-600 flex-shrink-0" />
          <span className="font-semibold text-amber-800 text-sm flex-1 text-left">
            {ricetteSenza.length} ricett{ricetteSenza.length === 1 ? "a" : "e"} senza allergeni dichiarati — da completare
          </span>
          <span className="text-[10px] text-amber-600">Reg. UE 1169/2011</span>
        </button>
        <button
          onClick={e => { e.stopPropagation(); onAutoRilevaAll && onAutoRilevaAll(); }}
          disabled={autoLoadingAll}
          data-testid="auto-rileva-tutte-btn"
          className="flex items-center gap-1 px-3 py-1 bg-[#5b7a6b] text-white rounded-lg text-[10px] font-bold hover:bg-[#4d6a5c] transition-colors disabled:opacity-50 mr-2"
        >
          {autoLoadingAll ? <RefreshCw size={10} className="animate-spin" /> : <Zap size={10} />}
          Auto-rileva Tutte
        </button>
        <button onClick={() => setAperto(v => !v)} className="p-1">
          {aperto ? <ChevronDown size={15} className="text-amber-500" /> : <ChevronRight size={15} className="text-amber-500" />}
        </button>
      </div>

      {aperto && (
        <div className="divide-y bg-white">
          {ricetteSenza.map(r => (
            <div key={r.id} className="px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="flex-1 text-sm font-medium text-gray-800 truncate">{r.nome}</span>
                {r.categoria && <span className="text-[10px] text-gray-400">({r.categoria})</span>}
                <button
                  onClick={() => autoRileva(r)}
                  disabled={autoLoading === r.id}
                  className="flex items-center gap-1 px-2.5 py-1 bg-[#f2f6f3] text-[#5b7a6b] rounded-lg text-[10px] font-semibold hover:bg-[#dce8e0] transition-colors disabled:opacity-50"
                  data-testid={`auto-rileva-${r.id}`}
                >
                  {autoLoading === r.id ? <RefreshCw size={10} className="animate-spin" /> : <Zap size={10} />}
                  Auto-rileva
                </button>
                <button
                  onClick={() => { setEditor(editor === r.id ? null : r.id); if (!selezione[r.id]) setSel(p => ({...p, [r.id]: new Set(r.allergeni||[])})); }}
                  className="flex items-center gap-1 px-2.5 py-1 bg-gray-100 text-gray-700 rounded-lg text-[10px] font-semibold hover:bg-gray-200"
                >
                  Modifica
                </button>
              </div>

              {/* Editor allergeni inline */}
              {editor === r.id && (
                <div className="mt-2 p-3 bg-gray-50 rounded-xl">
                  <p className="text-[10px] text-gray-500 mb-2 font-medium">Seleziona allergeni presenti:</p>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {ALLERGENI_14.map(a => {
                      const sel = (selezione[r.id] || new Set()).has(a.id);
                      return (
                        <button
                          key={a.id}
                          onClick={() => toggleAllergen(r.id, a.id)}
                          className={`px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-all ${
                            sel
                              ? "bg-red-500 text-white border-red-500"
                              : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                          }`}
                        >
                          {a.abbr}
                        </button>
                      );
                    })}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setEditor(null)}
                      className="px-3 py-1.5 text-xs text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100"
                    >
                      Annulla
                    </button>
                    <button
                      onClick={() => salva(r)}
                      disabled={saving}
                      className="px-4 py-1.5 text-xs bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 disabled:opacity-50"
                      data-testid={`salva-allergeni-${r.id}`}
                    >
                      {saving ? "Salvataggio..." : "Salva"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};


// ── Componente principale ────────────────────────────────────────────────────
export default function RegistroAllergeniView() {
  const [dati, setDati]                 = useState(null);
  const [loading, setLoading]           = useState(true);
  const [autoLoading, setAutoLoading]   = useState(false);
  const [search, setSearch]             = useState("");
  const [filtroCategoria, setFiltroC]   = useState("tutti");
  const [filtroSolo, setFiltroSolo]     = useState("tutti"); // "tutti"|"senza"|"con"
  const [qrRicetta, setQrRicetta]       = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/food-cost/registro-allergeni`);
      setDati(res.data);
    } catch { }
    setLoading(false);
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const autoRilevaToAll = async () => {
    setAutoLoading(true);
    try {
      const res = await axios.post(`${API}/food-cost/auto-rileva-allergeni-tutte`, {});
      const d = res.data;
      const trovate = d.aggiornate || 0;
      const conAll  = d.con_allergeni || 0;
      const senza   = d.senza_allergeni_trovati || 0;
      if (trovate > 0 && conAll > 0) {
        toast.success(`${trovate} ricette analizzate — ${conAll} con allergeni rilevati, ${senza} senza allergeni`);
      } else if (trovate > 0) {
        toast.info(`${trovate} ricette elaborate — nessun allergene rilevato automaticamente. Completa manualmente le rimanenti.`);
      } else {
        toast.info("Nessuna ricetta da aggiornare");
      }
      await carica();
    } catch { toast.error("Errore auto-rilevazione"); }
    setAutoLoading(false);
  };

  useEffect(() => { carica(); }, [carica]);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <RefreshCw className="animate-spin text-gray-400" size={28} />
    </div>
  );

  const tutteRicette = dati?.ricette || [];
  const categorie = [...new Set(tutteRicette.map(r => r.categoria).filter(Boolean))].sort();

  const ricette = tutteRicette.filter(r => {
    const matchSearch = !search || r.nome.toLowerCase().includes(search.toLowerCase());
    const matchCat    = filtroCategoria === "tutti" || r.categoria === filtroCategoria;
    const matchSolo   = filtroSolo === "tutti"
      || (filtroSolo === "senza" && (!r.allergeni || r.allergeni.length === 0))
      || (filtroSolo === "con"   && r.allergeni?.length > 0);
    return matchSearch && matchCat && matchSolo;
  });

  const conteggioA = {};
  ALLERGENI_14.forEach(a => {
    conteggioA[a.id] = tutteRicette.filter(r => (r.allergeni || []).includes(a.id)).length;
  });

  const senzaAllergeni = tutteRicette.filter(r => !r.allergeni || r.allergeni.length === 0);

  return (
    <div className="p-4 max-w-full">
      {/* QR Modal */}
      {qrRicetta && <QRModal ricetta={qrRicetta} onClose={() => setQrRicetta(null)} />}

      {/* Azioni (titolo nell'intestazione uniforme di pagina) */}
      <div className="flex items-center justify-end mb-4 no-print">
        <div className="flex gap-2">
          <button
            onClick={carica}
            className="flex items-center gap-2 border border-gray-200 text-gray-600 px-3 py-2 rounded-xl text-sm hover:bg-gray-50 transition-colors"
            data-testid="refresh-allergeni"
          >
            <RefreshCw size={14} /> Aggiorna
          </button>
          <button
            onClick={() => window.print()}
            data-testid="stampa-registro-allergeni"
            className="flex items-center gap-2 bg-gray-800 text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-gray-700 transition-colors"
          >
            <Printer size={14} /> Stampa
          </button>
        </div>
      </div>

      {/* Pannello ricette senza allergeni */}
      <PannelloMancanti ricette={tutteRicette} onAggiornato={carica} onAutoRilevaAll={autoRilevaToAll} autoLoadingAll={autoLoading} />

      {/* Riepilogo allergeni */}
      <div className="grid grid-cols-7 gap-1.5 mb-4 no-print">
        {ALLERGENI_14.map(a => (
          <div key={a.id} className={`rounded-lg p-2 text-center ${a.color}`}>
            <div className="text-xs font-bold">{a.abbr}</div>
            <div className="text-[10px] truncate hidden sm:block">{a.id}</div>
            <div className="text-xs font-semibold">{conteggioA[a.id]}</div>
          </div>
        ))}
      </div>

      {/* Filtri */}
      <div className="flex gap-2 mb-4 no-print flex-wrap">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search size={14} className="absolute left-2.5 top-2.5 text-gray-400" />
          <input
            className="w-full pl-8 pr-3 py-2 text-sm border rounded-xl focus:ring-2 focus:ring-[#5b7a6b] outline-none"
            placeholder="Cerca ricetta..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            data-testid="search-allergeni"
          />
        </div>
        <select
          className="border rounded-xl px-3 py-2 text-sm outline-none"
          value={filtroCategoria}
          onChange={e => setFiltroC(e.target.value)}
        >
          <option value="tutti">Tutte le categorie</option>
          {categorie.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          className="border rounded-xl px-3 py-2 text-sm outline-none"
          value={filtroSolo}
          onChange={e => setFiltroSolo(e.target.value)}
        >
          <option value="tutti">Tutte le ricette</option>
          <option value="senza">Solo senza allergeni ({senzaAllergeni.length})</option>
          <option value="con">Solo con allergeni ({tutteRicette.length - senzaAllergeni.length})</option>
        </select>
      </div>

      {/* Avviso normativo */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-4 text-xs text-amber-800 no-print">
        <strong>Obbligo OSA:</strong> Reg. UE 1169/2011 + D.Lgs. 109/92 — Sanzioni da <strong>750€ a 4.500€</strong> (D.Lgs. 190/2006).
        Clicca <QrCode size={10} className="inline" /> su ogni ricetta per generare il QR code da esporre.
      </div>

      {/* Tabella matrice */}
      <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
        <table className="text-xs w-full border-collapse print-table">
          <thead>
            <tr className="bg-gray-800 text-white">
              <th className="text-left py-2.5 px-3 font-semibold sticky left-0 bg-gray-800 min-w-[200px]">
                Ricetta / Piatto
              </th>
              {ALLERGENI_14.map(a => (
                <th key={a.id} className="py-2 px-1 text-center min-w-[34px]" title={a.id}>
                  <div className="font-bold">{a.abbr}</div>
                </th>
              ))}
              <th className="py-2 px-1 text-center min-w-[40px]">N.</th>
              <th className="py-2 px-1 text-center min-w-[36px] no-print">QR</th>
            </tr>
            <tr className="bg-gray-100 text-gray-600 border-b text-[9px]">
              <td className="py-1 px-3 italic sticky left-0 bg-gray-100">
                GLU=Glutine · CRO=Crostacei · UOV=Uova · PES=Pesce · ARA=Arachidi · SOI=Soia · LAT=Latte · GUS=Frutta guscio
              </td>
              <td colSpan={15} className="py-1 px-2 italic">
                SED=Sedano · SEN=Senape · SES=Sesamo · SO2=Solfiti · LUP=Lupini · MOL=Molluschi
              </td>
            </tr>
          </thead>
          <tbody>
            {ricette.length === 0 ? (
              <tr>
                <td colSpan={17} className="text-center py-8 text-gray-400">
                  Nessuna ricetta trovata
                </td>
              </tr>
            ) : ricette.map((r, i) => {
              const alls  = r.allergeni || [];
              const nAlls = alls.length;
              return (
                <tr
                  key={r.id}
                  className={`border-b hover:bg-gray-50 transition-colors ${
                    i % 2 === 0 ? "bg-white" : "bg-gray-50/50"
                  } ${nAlls === 0 ? "bg-orange-50/40" : ""}`}
                >
                  <td className="py-2 px-3 sticky left-0 bg-inherit font-medium text-gray-800">
                    {r.nome}
                    {r.categoria && <span className="ml-1 text-[10px] text-gray-400">({r.categoria})</span>}
                    {nAlls === 0 && <span className="ml-1 text-[10px] text-orange-500 font-medium">⚠</span>}
                  </td>
                  {ALLERGENI_14.map(a => {
                    const presente = alls.includes(a.id);
                    return (
                      <td key={a.id} className="py-2 px-1 text-center">
                        {presente ? (
                          <span className="inline-flex items-center justify-center w-5 h-5 bg-red-500 rounded text-white font-bold text-[10px]">
                            ✓
                          </span>
                        ) : (
                          <span className="text-gray-200 text-[10px]">—</span>
                        )}
                      </td>
                    );
                  })}
                  <td className="py-2 px-1 text-center">
                    <span className={`inline-block px-1.5 py-0.5 rounded-full font-bold text-[10px] ${
                      nAlls === 0 ? "bg-orange-100 text-orange-600" :
                      nAlls >= 4  ? "bg-red-100 text-red-700" :
                      "bg-green-100 text-green-700"
                    }`}>
                      {nAlls}
                    </span>
                  </td>
                  <td className="py-2 px-1 text-center no-print">
                    <button
                      onClick={() => setQrRicetta(r)}
                      className="p-1 text-gray-400 hover:text-[#5b7a6b] hover:bg-[#f2f6f3] rounded transition-colors"
                      title="Genera QR Code allergeni"
                      data-testid={`qr-${r.id}`}
                    >
                      <QrCode size={14} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer stampa */}
      <div className="mt-4 text-[10px] text-gray-400 print-only hidden">
        <p><strong>Stabilimento:</strong> Ceraldi Group · Aggiornato: {new Date().toLocaleDateString("it-IT")}</p>
        <p>Reg. UE 1169/2011, Allegato II. Conservare presso l&apos;esercizio.</p>
      </div>

      <style>{`
        @media print {
          .no-print { display: none !important; }
          .print-only { display: block !important; }
          body { font-size: 9px; }
          .print-table th, .print-table td { padding: 2px 3px !important; }
        }
      `}</style>
    </div>
  );
}
