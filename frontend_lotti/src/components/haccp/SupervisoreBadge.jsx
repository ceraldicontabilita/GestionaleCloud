/**
 * SupervisoreBadge — Pannello supervisore operativo HACCP
 * Si carica ad ogni apertura dell'app e mostra tutti i controlli pendenti.
 * Cliccando su un alert si naviga direttamente alla sezione da completare.
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  AlertTriangle, CheckCircle, AlertCircle,
  X, ChevronRight, RefreshCw, ShieldCheck
} from "lucide-react";

import { API } from "../../utils/constants";

const COLORI_PRIORITA = {
  critica: { bg: "bg-red-50",     border: "border-red-400",   text: "text-red-700",   badge: "bg-red-500",     icon: AlertTriangle },
  alta:    { bg: "bg-orange-50",  border: "border-orange-300", text: "text-orange-700", badge: "bg-orange-500",  icon: AlertCircle },
  media:   { bg: "bg-amber-50",   border: "border-amber-300",  text: "text-amber-700",  badge: "bg-amber-400",   icon: AlertCircle },
  bassa:   { bg: "bg-[#f2f6f3]",    border: "border-[#cfdfd5]",   text: "text-[#5b7a6b]",   badge: "bg-[#6f9180]",    icon: AlertCircle },
};

const SEMAFORO = {
  rosso:     { color: "bg-red-500",     label: "Azioni critiche richieste" },
  arancione: { color: "bg-orange-400",  label: "Azioni da completare" },
  verde:     { color: "bg-green-500",   label: "Tutto in regola" },
};

export function SupervisoreBadge({ onNavigate }) {
  const [dati, setDati]           = useState(null);
  const [aperto, setAperto]       = useState(false);
  const [loading, setLoading]     = useState(false);
  const [errore, setErrore]       = useState(false);

  const carica = useCallback(async (tentativi = 5) => {
    setLoading(true);
    setErrore(false);
    // Verifica e auto-popola le temperature di oggi (silenzioso, in background)
    axios.get(`${API}/haccp-auto/verifica-oggi`).catch(() => {});
    // Carica lo stato del supervisore, con ritentativi (il server free può essere in avvio)
    for (let i = 0; i < tentativi; i++) {
      try {
        const res = await axios.get(`${API}/supervisor/stato`, { timeout: 70000 });
        setDati(res.data);
        setErrore(false);
        setLoading(false);
        return;
      } catch (e) {
        if (i < tentativi - 1) await new Promise(r => setTimeout(r, 6000));
      }
    }
    setErrore(true);
    setLoading(false);
  }, []);

  // Carica all'avvio e ogni 5 minuti
  useEffect(() => {
    carica();
    const timer = setInterval(carica, 5 * 60 * 1000);
    return () => clearInterval(timer);
  }, [carica]);

  // Aggiornamento automatico quando un lotto viene eliminato/smaltito
  useEffect(() => {
    const onLottiChanged = () => carica();
    window.addEventListener("haccp:lotti-changed", onLottiChanged);
    return () => window.removeEventListener("haccp:lotti-changed", onLottiChanged);
  }, [carica]);

  const vaiA = (route, alertId) => {
    if (route && onNavigate) onNavigate(route, alertId);
    setAperto(false);
  };

  const [espanso, setEspanso] = useState(null); // alert.id con elenco aperto
  const vaiAVoce = (alert, item) => {
    // deep-link: la pagina di destinazione apre direttamente la scheda giusta.
    // "apri_ricetta_id" è la chiave che la pagina Ricette (BackofficeView/TabRicette)
    // legge davvero per aprire il form di modifica di UNA ricetta specifica.
    if (alert.route === "ricette" && item.id) {
      sessionStorage.setItem("apri_ricetta_id", item.id);
    }
    vaiA(alert.route, alert.id);
  };

  const semaforo = dati ? SEMAFORO[dati.semaforo] : null;

  return (
    <div className="relative">
      {/* ── Pulsante semaforo nella navbar ─────────────────────────────── */}
      <button
        onClick={() => setAperto(v => !v)}
        data-testid="supervisor-badge"
        className={`g-sup-btn${dati ? ' ' + dati.semaforo : ''}`}
      >
        {loading ? (
          <RefreshCw size={14} style={{ color:'rgba(255,255,255,.7)' }} className="animate-spin" />
        ) : dati?.semaforo === "verde" ? (
          <ShieldCheck size={14} style={{ color:'var(--success-accent)' }} />
        ) : (
          <AlertTriangle size={14} style={{ color: dati?.semaforo === "rosso" ? '#FF8A80' : '#FFCC80' }} />
        )}
        <span style={{ fontSize:13, fontWeight:700, color:'rgba(255,255,255,.9)', lineHeight:1 }}>
          {!dati ? "…" :
           dati.semaforo === "verde" ? "OK" :
           `${dati.totale_alert} alert`}
        </span>
        {dati && dati.critici > 0 && (
          <span style={{ position:'absolute', top:-5, right:-5, minWidth:18, height:18, padding:'0 4px', background:'var(--danger)', color:'#fff', fontSize:10, fontWeight:800, borderRadius:99, display:'flex', alignItems:'center', justifyContent:'center' }}>
            {dati.critici}
          </span>
        )}
      </button>

      {/* ── Pannello dettaglio ────────────────────────────────────────────── */}
      {aperto && (
        <>
          {/* Overlay mobile */}
          <div
            className="fixed inset-0 z-[998] bg-black/20 md:hidden"
            onClick={() => setAperto(false)}
          />
          <div className="fixed right-2 top-16 z-[999] w-[360px] max-w-[calc(100vw-16px)] bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden">
            {!dati ? (
              <div className="p-6 text-center">
                {loading ? (
                  <div className="flex flex-col items-center gap-2 py-6">
                    <RefreshCw size={30} className="animate-spin text-gray-400" />
                    <p className="text-sm text-gray-500">Caricamento controlli…</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3 py-6">
                    <AlertTriangle size={30} className="text-amber-500" />
                    <p className="text-sm text-gray-600">Non riesco a caricare i controlli adesso. Il server potrebbe essersi appena riavviato.</p>
                    <button onClick={() => carica()} className="px-4 py-2 bg-[#5b7a6b] text-white rounded-lg text-sm font-semibold flex items-center gap-2"><RefreshCw size={14}/> Riprova</button>
                  </div>
                )}
              </div>
            ) : (<>
            {/* Header */}
            <div className={`flex items-center justify-between px-4 py-3 ${
              dati.semaforo === "rosso" ? "bg-red-600" :
              dati.semaforo === "arancione" ? "bg-orange-500" : "bg-green-600"
            }`}>
              <div className="flex items-center gap-2 text-white">
                <ShieldCheck size={18} />
                <span className="font-bold text-sm">Supervisore HACCP</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-white/80 text-xs">{semaforo?.label}</span>
                <button onClick={() => setAperto(false)} className="text-white/80 hover:text-white">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Contatori */}
            <div className="grid grid-cols-4 border-b text-center text-xs py-2">
              <div>
                <div className="font-bold text-red-600 text-base">{dati.critici}</div>
                <div className="text-gray-500">Critici</div>
              </div>
              <div>
                <div className="font-bold text-orange-500 text-base">{dati.alti}</div>
                <div className="text-gray-500">Alti</div>
              </div>
              <div>
                <div className="font-bold text-amber-500 text-base">{dati.medi}</div>
                <div className="text-gray-500">Medi</div>
              </div>
              <div>
                <div className="font-bold text-[#5b7a6b] text-base">{dati.bassi}</div>
                <div className="text-gray-500">Bassi</div>
              </div>
            </div>

            {/* Lista alert */}
            <div className="max-h-[460px] overflow-y-auto divide-y">
              {dati.totale_alert === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-center px-4">
                  <CheckCircle size={36} className="text-green-500" />
                  <p className="font-semibold text-gray-700">Tutto in regola!</p>
                  <p className="text-xs text-gray-400">Temperature, lotti, allergeni, fornitori e pipeline sono tutti aggiornati.</p>
                </div>
              ) : dati.alerts.map(alert => {
                const C = COLORI_PRIORITA[alert.priorita] || COLORI_PRIORITA.media;
                const Icon = C.icon;
                const haElenco = Array.isArray(alert.items) && alert.items.length > 0;
                return (
                  <div key={alert.id}>
                  <div className={`w-full flex items-start gap-1 ${C.bg}`}>
                  <button
                    onClick={() => haElenco ? setEspanso(e => e === alert.id ? null : alert.id) : vaiA(alert.route, alert.id)}
                    data-testid={`supervisor-alert-${alert.id}`}
                    className="flex-1 min-w-0 text-left p-3 flex items-start gap-3 hover:brightness-95 transition-all"
                  >
                    <span className={`flex-shrink-0 mt-0.5 w-5 h-5 rounded-full ${C.badge} flex items-center justify-center`}>
                      <Icon size={11} className="text-white" />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className={`text-xs font-bold ${C.text} flex items-center gap-1`}>
                        {alert.titolo}
                        {alert.contatore > 0 && (
                          <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${C.badge} text-white`}>
                            {alert.contatore}
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-gray-500 mt-0.5 line-clamp-2">{alert.descrizione}</div>
                    </div>
                    {alert.route && <ChevronRight size={14} className={`flex-shrink-0 text-gray-400 mt-1 transition-transform ${espanso === alert.id ? "rotate-90" : ""}`} />}
                  </button>
                  {/* ✕ = silenzia per oggi; riappare da solo se il problema cambia/cresce.
                      Gli alert CRITICI (obblighi di legge) non hanno la ✕: si tolgono
                      solo risolvendo il problema (decisione Enzo 04/07/2026). */}
                  {alert.priorita !== "critica" ? (
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          await axios.post(`${API}/supervisor/alerts/${alert.id}/silenzia?contatore=${alert.contatore || 0}&priorita=${alert.priorita || ""}`);
                          carica();
                        } catch { /* non bloccante */ }
                      }}
                      title="Nascondi per oggi (riappare se il problema cambia)"
                      className="flex-shrink-0 p-3 text-gray-400 hover:text-gray-700"
                    >
                      <X size={14} />
                    </button>
                  ) : (
                    <span
                      title="Alert di legge: non si può nascondere, sparisce risolvendo il problema"
                      className="flex-shrink-0 p-3 text-red-300 cursor-not-allowed select-none text-[10px] font-bold"
                    >
                      !
                    </span>
                  )}
                  </div>
                  {haElenco && espanso === alert.id && (
                    <div className="bg-white border-t border-gray-100 max-h-56 overflow-y-auto">
                      {alert.items.map(item => (
                        <button key={item.id} onClick={() => vaiAVoce(alert, item)}
                          className="w-full text-left px-4 py-2.5 flex items-center justify-between gap-2 text-xs font-semibold text-gray-700 hover:bg-amber-50 border-b border-gray-50">
                          <span className="truncate capitalize">{item.nome}</span>
                          <ChevronRight size={12} className="flex-shrink-0 text-amber-500" />
                        </button>
                      ))}
                    </div>
                  )}
                  </div>
                );
              })}
            </div>

            {/* Footer */}
            <div className="border-t px-4 py-2.5 flex items-center justify-between bg-gray-50">
              <span className="text-[11px] text-gray-400">
                Aggiornato: {dati.data_controllo ? new Date(dati.data_controllo).toLocaleTimeString("it-IT", {hour:"2-digit",minute:"2-digit"}) : "—"}
              </span>
              <button
                onClick={carica}
                className="text-[11px] text-[#5b7a6b] hover:underline flex items-center gap-1"
              >
                <RefreshCw size={11} /> Ricontrolla
              </button>
            </div>
            </>)}
          </div>
        </>
      )}
    </div>
  );
}
