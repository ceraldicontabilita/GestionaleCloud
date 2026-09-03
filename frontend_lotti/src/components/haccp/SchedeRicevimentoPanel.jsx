import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { Card } from "./shared/Card";
import { RefreshCw, Check, X, ShieldCheck, ShieldAlert, Clock, AlertTriangle, Thermometer, Package, ClipboardList, UserCheck, UserX, Zap, GitMerge, Users, CheckCircle2, ChevronDown, ChevronRight, FileText, Search } from "lucide-react";
import NoteRicevimento from "./fornitori/NoteRicevimento";

// FIX 25/07/2026: BADGE_TIPO e NoteRicevimento erano rimasti in
// FornitoriList.jsx (non esportati) dopo l'estrazione di questo pannello →
// ReferenceError "BADGE_TIPO is not defined" all'apertura del registro.
const BADGE_TIPO = {
  surgelato:   { label: "Surgelato",    bg: "bg-[#e8efe9]",   text: "text-[#3f5a4e]",   icon: "❄️" },
  refrigerato: { label: "Refrigerato",  bg: "bg-[#e8efe9]",   text: "text-[#5b7a6b]",   icon: "🧊" },
  ambiente:    { label: "Ambiente",     bg: "bg-gray-100",   text: "text-gray-600",   icon: "📦" },
};

export const SchedeRicevimentoPanel = () => {
  const [schede, setSchede]       = useState([]);
  const [loading, setLoading]     = useState(false);
  const [aperta, setAperta]       = useState(false);
  const [espansa, setEspansa]     = useState(null); // id_fattura espanso
  const [raggruppa, setRaggruppa] = useState(true); // raggruppa per fornitore

  const carica = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/fornitori/schede-ricevimento?limit=100`);
      setSchede(res.data || []);
    } catch {
      toast.error("Errore caricamento schede ricevimento");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (aperta && schede.length === 0) carica();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aperta]);

  // Raggruppa schede per fornitore (mostra ultima consegna + conteggio)
  const schedeVista = raggruppa
    ? Object.values(
        schede.reduce((acc, s) => {
          const k = s.fornitore;
          if (!acc[k] || s.data_consegna > acc[k].data_consegna) {
            acc[k] = { ...s, num_consegne: (acc[k]?.num_consegne || 0) + 1 };
          } else {
            acc[k].num_consegne = (acc[k].num_consegne || 1) + 1;
          }
          return acc;
        }, {})
      ).sort((a, b) => b.data_consegna?.localeCompare(a.data_consegna))
    : schede;

  const surgelati   = schede.filter(s => s.tipo_conservazione === "surgelato");
  const refrigerati = schede.filter(s => s.tipo_conservazione === "refrigerato");
  const ambiente    = schede.filter(s => s.tipo_conservazione === "ambiente");

  const renderBadgeTemp = (scheda) => {
    const tipo = BADGE_TIPO[scheda.tipo_conservazione] || BADGE_TIPO.ambiente;
    if (scheda.temperatura_rilevata === null) {
      return (
        <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${tipo.bg} ${tipo.text}`}>
          {tipo.icon} N/A
        </span>
      );
    }
    return (
      <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${tipo.bg} ${tipo.text}`}>
        {tipo.icon} {scheda.temperatura_rilevata > 0 ? "+" : ""}{scheda.temperatura_rilevata}°C
      </span>
    );
  };

  return (
    <Card>
      <button
        onClick={() => setAperta(v => !v)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 rounded-xl transition-colors"
        data-testid="toggle-schede-ricevimento"
      >
        <div className="flex items-center gap-3">
          <Thermometer size={20} className="text-[#5b7a6b]" />
          <div className="text-left">
            <p className="font-semibold text-gray-800">Registro Ricevimento Merci — Temperature</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Reg. CE 852/2004 · Temperature pre-compilate nei range di legge · {schede.length > 0 ? `${schede.length} consegne` : "Clicca per caricare"}
            </p>
          </div>
        </div>
        {aperta ? <ChevronDown size={18} className="text-gray-400" /> : <ChevronRight size={18} className="text-gray-400" />}
      </button>

      {aperta && (
        <div className="border-t">
          {/* Banner normativa + toggle raggruppa */}
          <div className="px-4 py-2.5 bg-[#f2f6f3] border-b border-[#dce8e0] flex items-center gap-2 text-xs text-[#3f5a4e]">
            <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5 text-[#5b7a6b]" />
            <span className="flex-1">
              <strong>Conforme Reg. CE 852/2004:</strong> Temperature registrate automaticamente. I fornitori esclusi sono esclusi da questa lista.
            </span>
            <button
              onClick={() => setRaggruppa(v => !v)}
              className={`ml-auto flex-shrink-0 px-2.5 py-1 rounded-full text-[10px] font-bold border transition-all ${raggruppa ? 'bg-[#5b7a6b] text-white border-[#5b7a6b]' : 'bg-white text-[#5b7a6b] border-[#b8d0c2]'}`}
              data-testid="toggle-raggruppa-fornitori"
              title={raggruppa ? "Mostra tutte le consegne" : "Raggruppa per fornitore"}
            >
              {raggruppa ? "Per fornitore" : "Tutte le consegne"}
            </button>
          </div>

          {/* Riepilogo per tipo */}
          {schede.length > 0 && (
            <div className="grid grid-cols-3 border-b text-center text-xs py-2.5 bg-gray-50">
              <div>
                <div className="font-bold text-[#4f6d5f] text-lg">{surgelati.length}</div>
                <div className="text-gray-500">❄️ Surgelati</div>
                <div className="text-[10px] text-[#3f5a4e] font-medium">≤ -18°C</div>
              </div>
              <div>
                <div className="font-bold text-[#5b7a6b] text-lg">{refrigerati.length}</div>
                <div className="text-gray-500">🧊 Refrigerati</div>
                <div className="text-[10px] text-[#5b7a6b] font-medium">0 – 4°C</div>
              </div>
              <div>
                <div className="font-bold text-gray-500 text-lg">{ambiente.length}</div>
                <div className="text-gray-500">📦 Ambiente</div>
                <div className="text-[10px] text-gray-400 font-medium">N/A</div>
              </div>
            </div>
          )}

          {/* Lista schede */}
          {loading ? (
            <div className="p-8 text-center text-gray-400">
              <RefreshCw size={24} className="animate-spin mx-auto mb-2" />
              Caricamento schede...
            </div>
          ) : schede.length === 0 ? (
            <div className="p-8 text-center text-gray-400">
              <Package size={36} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Nessuna scheda ricevimento</p>
              <p className="text-xs mt-1">Importa fatture per generare le schede</p>
            </div>
          ) : (
            <div className="divide-y max-h-[520px] overflow-y-auto">
              {schedeVista.map(s => {
                const rowKey = s.id_fattura || s.fornitore;
                const isEspansa = espansa === rowKey;
                const tipo = BADGE_TIPO[s.tipo_conservazione] || BADGE_TIPO.ambiente;
                return (
                  <div key={rowKey} className="hover:bg-gray-50 transition-colors">
                    <button
                      onClick={() => setEspansa(isEspansa ? null : rowKey)}
                      className="w-full text-left px-4 py-2.5 flex items-center gap-3"
                      data-testid={`scheda-ricevimento-${rowKey}`}
                    >
                      <span className="text-base flex-shrink-0">{tipo.icon}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-semibold text-gray-800 truncate">{s.fornitore}</span>
                          <span className="text-[10px] text-gray-400 font-mono">{s.numero_documento}</span>
                          {raggruppa && s.num_consegne > 1 && (
                            <span className="text-[10px] bg-[#e8efe9] text-[#5b7a6b] font-bold px-1.5 py-0.5 rounded-full">
                              {s.num_consegne} consegne
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] text-gray-500">{s.data_consegna}</span>
                          <span className="text-[10px] text-gray-400">·</span>
                          <span className="text-[10px] text-gray-500">{s.num_prodotti} prodotti</span>
                        </div>
                      </div>
                      {/* Badge temperatura */}
                      <div className="flex-shrink-0 flex flex-col items-end gap-1">
                        {renderBadgeTemp(s)}
                        <span className="text-[9px] text-green-600 font-bold flex items-center gap-0.5">
                          <Check size={9} /> Conforme
                        </span>
                      </div>
                      {isEspansa
                        ? <ChevronDown size={14} className="text-gray-400 flex-shrink-0" />
                        : <ChevronRight size={14} className="text-gray-400 flex-shrink-0" />
                      }
                    </button>

                    {/* Dettaglio espanso */}
                    {isEspansa && (
                      <div className="px-4 pb-3 border-t border-gray-100 bg-gray-50">
                        {/* Info temperatura */}
                        <div className={`mt-2 mb-2 rounded-lg px-3 py-2 ${tipo.bg} border border-opacity-50`}>
                          <div className="flex items-start gap-2">
                            <Thermometer size={14} className={`flex-shrink-0 mt-0.5 ${tipo.text}`} />
                            <div>
                              <p className={`text-[11px] font-bold ${tipo.text}`}>
                                Temperatura rilevata al ricevimento:{" "}
                                {s.temperatura_rilevata !== null
                                  ? `${s.temperatura_rilevata > 0 ? "+" : ""}${s.temperatura_rilevata}°C`
                                  : "Non applicabile"}
                              </p>
                              {s.temperatura_min !== null && (
                                <p className="text-[10px] text-gray-600 mt-0.5">
                                  Range: {s.temperatura_min}°C / {s.temperatura_max}°C
                                </p>
                              )}
                              <p className="text-[10px] text-gray-500 mt-0.5 italic">{s.note_temperatura}</p>
                            </div>
                          </div>
                        </div>

                        {/* Prodotti + Lotti */}
                        {s.prodotti?.length > 0 && (
                          <div className="mt-1">
                            <p className="text-[10px] text-gray-500 font-medium mb-1 uppercase tracking-wide">
                              Prodotti consegnati — trascrizione lotti
                            </p>
                            <div className="space-y-1 max-h-48 overflow-y-auto">
                              {s.prodotti.map((p, i) => (
                                <div key={i} className="flex items-center justify-between text-[10px] py-1.5 px-2 rounded-lg bg-white border border-gray-100">
                                  <div className="flex-1 min-w-0 mr-2">
                                    <span className="text-gray-700 font-medium truncate block">{p.descrizione}</span>
                                    <span className="text-gray-400">{p.quantita} {p.unita_misura}</span>
                                    {p.lotto && (
                                      <span className="ml-2 text-[#5b7a6b] font-mono text-[9px] bg-[#f2f6f3] px-1 rounded">
                                        Lotto: {p.lotto}
                                      </span>
                                    )}
                                    {p.scadenza && (
                                      <span className="ml-1 text-amber-600 text-[9px]">Scad: {p.scadenza}</span>
                                    )}
                                  </div>
                                  {p.totale > 0 && (
                                    <span className="text-gray-600 font-semibold flex-shrink-0">€{p.totale.toFixed(2)}</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Note operatore */}
                        <NoteRicevimento idFattura={s.id_fattura} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </Card>
  );
};
