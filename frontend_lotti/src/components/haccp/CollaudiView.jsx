/**
 * CollaudiView — "Collaudi da fare" (richiesta Enzo 03/07/2026: i test manuali
 * post-deploy vivono in una pagina, non dettati in chat).
 * Ogni intervento di sviluppo registra qui i suoi test (POST /collaudi);
 * Enzo li esegue sul telefono/tablet e li spunta: Fatto ✓ o Fallito ✗
 * (i falliti sono i bug da rimandare a Claude).
 */
import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { getOperatoreNome } from "../../auth";
import { ClipboardCheck, Check, X, RotateCcw, Trash2 } from "lucide-react";

const STATO_UI = {
  da_fare: { label: "Da fare", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  fatto:   { label: "✓ Fatto", cls: "bg-green-50 text-green-700 border-green-200" },
  fallito: { label: "✗ Fallito", cls: "bg-red-50 text-red-700 border-red-200" },
};

export default function CollaudiView() {
  const [collaudi, setCollaudi] = useState([]);
  const [loading, setLoading] = useState(true);
  const [soloDaFare, setSoloDaFare] = useState(true);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/collaudi`);
      setCollaudi(data.collaudi || []);
    } catch { toast.error("Errore caricamento collaudi"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { carica(); }, [carica]);

  const setStato = async (c, stato) => {
    try {
      await axios.post(`${API}/collaudi/${c.id}/stato?stato=${stato}&operatore=${encodeURIComponent(getOperatoreNome() || "")}`);
      toast.success(stato === "fatto" ? `"${c.titolo}" collaudato ✓` : stato === "fallito" ? `"${c.titolo}" segnato come fallito — da sistemare` : "Rimesso tra i da fare");
      carica();
    } catch { toast.error("Errore salvataggio"); }
  };

  const elimina = async (c) => {
    if (!await conferma(`Eliminare il collaudo "${c.titolo}"?`)) return;
    try { await axios.delete(`${API}/collaudi/${c.id}`); carica(); }
    catch { toast.error("Errore eliminazione"); }
  };

  const visibili = collaudi.filter(c => !soloDaFare || c.stato === "da_fare");
  const daFare = collaudi.filter(c => c.stato === "da_fare").length;
  const falliti = collaudi.filter(c => c.stato === "fallito").length;
  const gruppi = {};
  visibili.forEach(c => { const g = c.gruppo || "Altro"; (gruppi[g] = gruppi[g] || []).push(c); });

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-1">
        <ClipboardCheck size={22} className="text-[#5b7a6b]" />
        <h1 className="text-xl font-bold text-gray-800">Collaudi da fare</h1>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Ogni modifica all'app lascia qui i suoi test: eseguili dal telefono/tablet e spuntali.
        I <b>falliti</b> sono i bug da segnalare in chat.
      </p>

      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span className="text-xs font-bold bg-amber-100 text-amber-700 px-3 py-1.5 rounded-full">{daFare} da fare</span>
        {falliti > 0 && <span className="text-xs font-bold bg-red-100 text-red-700 px-3 py-1.5 rounded-full">{falliti} falliti</span>}
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer ml-auto">
          <input type="checkbox" checked={soloDaFare} onChange={e => setSoloDaFare(e.target.checked)} className="accent-[#5b7a6b]" />
          Solo da fare
        </label>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Caricamento…</div>
      ) : visibili.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <Check size={32} className="mx-auto mb-2 text-green-500" />
          <p className="text-sm font-semibold text-gray-600">Nessun collaudo in sospeso</p>
        </div>
      ) : Object.entries(gruppi).map(([g, items]) => (
        <div key={g} className="mb-5">
          <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{g}</h2>
          <div className="space-y-3">
            {items.map(c => {
              const st = STATO_UI[c.stato] || STATO_UI.da_fare;
              return (
                <div key={c.id} className="bg-white rounded-xl border border-gray-100 p-4">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <p className="font-semibold text-gray-800 text-sm">{c.titolo}</p>
                    <span className={`text-[10px] font-bold px-2 py-1 rounded-full border whitespace-nowrap ${st.cls}`}>{st.label}</span>
                  </div>
                  <ol className="list-decimal list-inside space-y-1 mb-3">
                    {(c.passi || []).map((p, i) => (
                      <li key={i} className="text-sm text-gray-600 leading-snug">{p}</li>
                    ))}
                  </ol>
                  {c.eseguito_il && (
                    <p className="text-[11px] text-gray-400 mb-2">
                      {c.stato === "fatto" ? "Collaudato" : "Segnato"} il {new Date(c.eseguito_il).toLocaleString("it-IT")} {c.eseguito_da ? `da ${c.eseguito_da}` : ""}
                    </p>
                  )}
                  <div className="flex items-center gap-2">
                    {c.stato === "da_fare" ? (<>
                      <button onClick={() => setStato(c, "fatto")}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-bold hover:bg-green-700">
                        <Check size={13} /> Funziona
                      </button>
                      <button onClick={() => setStato(c, "fallito")}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-[#d35f4e] text-white rounded-lg text-xs font-bold hover:brightness-90">
                        <X size={13} /> Non funziona
                      </button>
                    </>) : (
                      <button onClick={() => setStato(c, "da_fare")}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs font-bold hover:bg-gray-200">
                        <RotateCcw size={13} /> Rimetti tra i da fare
                      </button>
                    )}
                    <button onClick={() => elimina(c)} className="ml-auto p-1.5 text-gray-300 hover:text-red-500">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
