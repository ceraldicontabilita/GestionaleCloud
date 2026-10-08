import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { Card } from "./shared/Card";
import { RefreshCw, Check, X, ShieldCheck, ShieldAlert, Clock, AlertTriangle, Thermometer, Package, ClipboardList, UserCheck, UserX, Zap, GitMerge, Users, CheckCircle2, ChevronDown, ChevronRight, FileText, Search, Ban } from "lucide-react";

export function DuplicatiMergePanel() {
  const [loading, setLoading] = useState(false);
  const [gruppi, setGruppi] = useState([]);
  const [totale, setTotale] = useState(0);
  const [espanso, setEspanso] = useState(false);
  const [selKeep, setSelKeep] = useState({}); // { piva: nome_master }
  const [merging, setMerging] = useState(null);
  const [confermaOpen, setConfermaOpen] = useState(null);

  const carica = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/fornitori/duplicati-per-piva`);
      setGruppi(res.data.gruppi || []);
      setTotale(res.data.totale_gruppi || 0);
      // Pre-seleziona di default il primo (quello con più fatture)
      const preSel = {};
      (res.data.gruppi || []).forEach(g => {
        preSel[g.piva] = g.varianti[0]?.nome || "";
      });
      setSelKeep(preSel);
    } catch (e) {
      toast.error("Errore caricamento duplicati");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (espanso) carica(); }, [espanso]);

  const eseguiMerge = async (gruppo) => {
    const keep = selKeep[gruppo.piva];
    if (!keep) return toast.error("Seleziona quale nome mantenere");
    const merge_nomi = gruppo.varianti.map(v => v.nome).filter(n => n !== keep);
    if (merge_nomi.length === 0) return toast.error("Nessun fornitore da unire");

    setMerging(gruppo.piva);
    try {
      const res = await axios.post(`${API}/fornitori/merge`, {
        keep_nome: keep,
        merge_nomi,
      });
      const d = res.data;
      toast.success(
        `✓ Uniti in "${d.master}": ${d.fatture_trasferite_totali} fatture trasferite, ${d.fornitori_eliminati} record eliminati`,
        { duration: 5000 }
      );
      setConfermaOpen(null);
      // Ricarica la lista
      await carica();
    } catch (e) {
      toast.error(apiError(e, "Errore durante merge"));
    } finally {
      setMerging(null);
    }
  };

  return (
    <Card className="p-4 mb-4">
      <button
        onClick={() => setEspanso(v => !v)}
        className="w-full flex items-center justify-between"
        data-testid="duplicati-toggle-btn"
      >
        <div className="flex items-center gap-2">
          <GitMerge size={18} className="text-[#7a5f3d]" />
          <h3 className="font-semibold text-gray-800">
            Deduplica Fornitori
            {totale > 0 && (
              <span className="ml-2 text-xs bg-[#f3e8d4] text-[#6f583a] px-2 py-0.5 rounded-full font-bold">
                {totale} {totale === 1 ? "gruppo" : "gruppi"} duplicati
              </span>
            )}
          </h3>
        </div>
        {espanso ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {espanso && (
        <div className="mt-4 space-y-3">
          <p className="text-xs text-gray-500 bg-gray-50 p-3 rounded-lg">
            <Users size={12} className="inline mr-1" />
            Fornitori con <strong>stessa P.IVA</strong> ma nomi diversi (probabilmente sono lo stesso soggetto legale).
            Scegli il nome da mantenere e clicca <em>Unisci</em> per trasferire tutte le fatture.
          </p>

          {loading ? (
            <div className="text-center py-6 text-gray-400">
              <RefreshCw size={20} className="animate-spin mx-auto mb-2" />
              Caricamento...
            </div>
          ) : gruppi.length === 0 ? (
            <div className="text-center py-6 text-green-600">
              <CheckCircle2 size={32} className="mx-auto mb-2" />
              <p className="font-semibold">Nessun duplicato trovato</p>
              <p className="text-xs text-gray-500 mt-1">Tutti i fornitori hanno P.IVA univoca.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {gruppi.map(g => (
                <div
                  key={g.piva}
                  className="border border-[#e6d3ab] bg-[#faf5ec]/30 rounded-lg p-3"
                  data-testid={`gruppo-dup-${g.piva}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-mono text-[#6f583a] bg-[#f3e8d4] px-2 py-0.5 rounded">
                      P.IVA {g.piva}
                    </div>
                    <span className="text-[11px] text-gray-500">{g.count} varianti</span>
                  </div>

                  <div className="space-y-1.5">
                    {g.varianti.map((v, i) => {
                      const isKeep = selKeep[g.piva] === v.nome;
                      return (
                        <label
                          key={i}
                          className={`flex items-center justify-between p-2 rounded cursor-pointer transition-colors ${
                            isKeep ? "bg-green-50 border border-green-300" : "bg-white border border-gray-200 hover:border-[#d4b87f]"
                          }`}
                          data-testid={`variante-${g.piva}-${i}`}
                        >
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <input
                              type="radio"
                              name={`keep-${g.piva}`}
                              checked={isKeep}
                              onChange={() => setSelKeep(s => ({ ...s, [g.piva]: v.nome }))}
                              className="flex-shrink-0"
                            />
                            <span className="text-sm font-medium text-gray-800 truncate">{v.nome}</span>
                            {isKeep && (
                              <span className="text-[10px] bg-green-500 text-white px-1.5 py-0.5 rounded-full font-bold flex-shrink-0">
                                MANTIENI
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                            <span className="text-xs text-gray-600 font-mono">
                              {v.num_fatture_reali} fatt
                            </span>
                            {v.escluso && <Ban size={12} className="text-red-500" title="Escluso" />}
                          </div>
                        </label>
                      );
                    })}
                  </div>

                  <div className="flex justify-end mt-2">
                    {confermaOpen === g.piva ? (
                      <div className="flex items-center gap-2 bg-amber-50 border border-amber-300 rounded p-2 w-full">
                        <AlertTriangle size={14} className="text-amber-600 flex-shrink-0" />
                        <span className="text-xs text-amber-800 flex-1">
                          Confermi? Tutte le fatture degli altri nomi verranno trasferite a <strong>{selKeep[g.piva]}</strong>.
                        </span>
                        <button
                          onClick={() => setConfermaOpen(null)}
                          disabled={merging === g.piva}
                          className="text-xs px-2 py-1 text-gray-600 hover:text-gray-800"
                          data-testid={`annulla-${g.piva}`}
                        >
                          Annulla
                        </button>
                        <button
                          onClick={() => eseguiMerge(g)}
                          disabled={merging === g.piva}
                          className="text-xs px-3 py-1 bg-red-600 text-white rounded font-bold hover:bg-red-700 disabled:opacity-50"
                          data-testid={`conferma-merge-${g.piva}`}
                        >
                          {merging === g.piva ? "Unisco..." : "✓ Conferma"}
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfermaOpen(g.piva)}
                        disabled={merging !== null}
                        className="text-xs px-3 py-1.5 bg-[#7a5f3d] text-white rounded font-semibold hover:bg-[#6f583a] disabled:opacity-50 flex items-center gap-1.5"
                        data-testid={`merge-btn-${g.piva}`}
                      >
                        <GitMerge size={12} />
                        Unisci in "{selKeep[g.piva] || '...'}"
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
