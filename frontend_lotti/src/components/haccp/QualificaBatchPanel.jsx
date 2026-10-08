import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { Card } from "./shared/Card";
import { RefreshCw, Check, X, ShieldCheck, ShieldAlert, Clock, AlertTriangle, Thermometer, Package, ClipboardList, UserCheck, UserX, Zap, GitMerge, Users, CheckCircle2, ChevronDown, ChevronRight, FileText, Search } from "lucide-react";

export const QualificaBatchPanel = () => {
  const [aperto, setAperto]       = useState(false);
  const [lista, setLista]         = useState([]);
  const [loading, setLoading]     = useState(false);
  const [saving, setSaving]       = useState(false);
  const [selezionati, setSelezionati] = useState(new Set());

  const carica = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/fornitori/qualifica/in-attesa`);
      setLista(res.data || []);
    } catch { toast.error("Errore caricamento fornitori in attesa"); }
    finally { setLoading(false); }
  };

  useEffect(() => { if (aperto && lista.length === 0) carica(); }, [aperto]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSel = (piva) =>
    setSelezionati(prev => {
      const n = new Set(prev);
      n.has(piva) ? n.delete(piva) : n.add(piva);
      return n;
    });

  const selezionaTutti = () =>
    setSelezionati(new Set(lista.map(f => f.piva).filter(Boolean)));

  const approva = async (includi) => {
    const pive = Array.from(selezionati);
    if (pive.length === 0) { toast.warning("Seleziona almeno un fornitore"); return; }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/fornitori/qualifica/approva-batch`, { pive, includi });
      toast.success(`${res.data.aggiornati} fornitore/i ${includi ? "qualificati" : "esclusi"}`);
      setLista(prev => prev.filter(f => !selezionati.has(f.piva)));
      setSelezionati(new Set());
    } catch { toast.error("Errore durante l'approvazione"); }
    finally { setSaving(false); }
  };

  const autoQualificaTutti = async () => {
    setSaving(true);
    try {
      const res = await axios.post(`${API}/fornitori/qualifica/auto-qualifica-tutti`);
      toast.success(`Auto-qualifica completata: ${res.data.aggiornati} fornitori qualificati automaticamente`);
      setLista([]);
      setSelezionati(new Set());
    } catch { toast.error("Errore auto-qualifica"); }
    finally { setSaving(false); }
  };

  const count = lista.length;

  return (
    <Card>
      <button
        onClick={() => setAperto(v => !v)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 rounded-xl transition-colors"
        data-testid="toggle-qualifica-batch"
      >
        <div className="flex items-center gap-3">
          <ClipboardList size={20} className={count > 0 ? "text-amber-500" : "text-green-500"} />
          <div className="text-left">
            <div className="flex items-center gap-2">
              <p className="font-semibold text-gray-800">Registro Qualifica Fornitori HACCP</p>
              {count > 0 && (
                <span className="bg-amber-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full">
                  {count} in attesa
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              Reg. CE 178/2002 art. 18 · Approvazione rapida dei fornitori
            </p>
          </div>
        </div>
        {aperto ? <ChevronDown size={18} className="text-gray-400" /> : <ChevronRight size={18} className="text-gray-400" />}
      </button>

      {aperto && (
        <div className="border-t">
          {/* Banner normativa */}
          <div className="px-4 py-2 bg-amber-50 border-b border-amber-100 text-xs text-amber-800 flex gap-2">
            <AlertTriangle size={13} className="flex-shrink-0 mt-0.5 text-amber-600" />
            <span>
              <strong>Reg. CE 178/2002 — Art. 18:</strong> Ogni fornitore deve essere formalmente qualificato.
              Usa <strong>Auto-qualifica</strong> per qualificare automaticamente tutti i fornitori con fatture attive.
            </span>
          </div>

          {/* Pulsante Auto-qualifica prominente */}
          {lista.length > 0 && (
            <div className="px-4 py-3 bg-green-50 border-b border-green-100 flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-green-800">{lista.length} fornitori in attesa di qualifica</p>
                <p className="text-xs text-green-600 mt-0.5">I fornitori con fatture attive vengono qualificati automaticamente. Solo i fornitori esclusi manualmente rimangono esclusi.</p>
              </div>
              <button
                onClick={autoQualificaTutti}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-bold hover:bg-green-700 disabled:opacity-40 whitespace-nowrap"
                data-testid="btn-auto-qualifica-tutti"
              >
                <Zap size={15} /> {saving ? "In corso..." : "Auto-qualifica Automatica"}
              </button>
            </div>
          )}

          {/* Barra azioni manuali */}
          {lista.length > 0 && (
            <div className="px-4 py-2.5 border-b bg-gray-50 flex items-center gap-2 flex-wrap">
              <button onClick={selezionaTutti} className="text-xs text-[#5b7a6b] underline">
                Seleziona tutti ({lista.length})
              </button>
              <div className="flex-1" />
              <span className="text-xs text-gray-500">{selezionati.size} selezionati</span>
              <button
                onClick={() => approva(false)}
                disabled={saving || selezionati.size === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 border border-red-200 text-red-600 rounded-lg text-xs font-medium hover:bg-red-50 disabled:opacity-40"
                data-testid="btn-escludi-batch"
              >
                <UserX size={13} /> Escludi
              </button>
              <button
                onClick={() => approva(true)}
                disabled={saving || selezionati.size === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-semibold hover:bg-green-700 disabled:opacity-40"
                data-testid="btn-qualifica-batch"
              >
                <UserCheck size={13} /> {saving ? "Salvataggio..." : "Qualifica"}
              </button>
              <button
                onClick={async () => { setSelezionati(new Set(lista.map(f=>f.piva).filter(Boolean))); await approva(true); }}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[#5b7a6b] text-white rounded-lg text-xs font-semibold hover:bg-[#4d6a5c] disabled:opacity-40"
                data-testid="btn-qualifica-tutti"
              >
                <Zap size={13} /> Qualifica Tutti
              </button>
            </div>
          )}

          {/* Lista fornitori */}
          {loading ? (
            <div className="p-8 text-center text-gray-400">
              <RefreshCw size={22} className="animate-spin mx-auto mb-2" />
              Caricamento...
            </div>
          ) : lista.length === 0 ? (
            <div className="p-8 text-center">
              <CheckCircle2 size={36} className="mx-auto mb-2 text-green-400" />
              <p className="text-sm font-medium text-green-700">Tutti i fornitori sono qualificati</p>
              <p className="text-xs text-gray-400 mt-1">Nessuna azione richiesta</p>
            </div>
          ) : (
            <div className="divide-y max-h-[480px] overflow-y-auto">
              {lista.map(f => (
                <label
                  key={f.piva || f.nome_fornitore}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 cursor-pointer"
                  data-testid={`qualifica-row-${f.piva}`}
                >
                  <input
                    type="checkbox"
                    checked={selezionati.has(f.piva)}
                    onChange={() => toggleSel(f.piva)}
                    className="w-4 h-4 rounded border-gray-300 accent-green-600"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-800 truncate">{f.nome_fornitore}</p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-[10px] text-gray-400 font-mono">{f.piva}</span>
                      <span className="text-[10px] text-gray-300">·</span>
                      <span className="text-[10px] text-gray-500">{f.num_fatture || 0} fatture</span>
                      {f.ultima_consegna && (
                        <>
                          <span className="text-[10px] text-gray-300">·</span>
                          <span className="text-[10px] text-gray-500">Ultima: {f.ultima_consegna}</span>
                        </>
                      )}
                    </div>
                    {f.prodotti_campione?.length > 0 && (
                      <p className="text-[10px] text-gray-400 mt-0.5 truncate">
                        {f.prodotti_campione.slice(0, 3).join(" · ")}
                      </p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    {f.totale_acquistato > 0 && (
                      <p className="text-xs font-semibold text-gray-700">€{f.totale_acquistato?.toFixed(0)}</p>
                    )}
                    <span className="text-[9px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full font-medium">
                      In attesa
                    </span>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
};
