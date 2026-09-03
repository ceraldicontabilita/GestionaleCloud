import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, Eye, MoreVertical, ArrowLeftRight, Snowflake, Store, RotateCcw, Trash2, BellRing } from "lucide-react";
import { getOperatoreNome } from "../../auth";
import Button from "../ui/Button";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { SEMAFORO, euro, posizioneLabel, AzioneModal, SchedaLottoModal } from "./shared/SchedaLottoModal";

// ── Card lotto ────────────────────────────────────────────────────────────────
function LottoCard({ lotto, onDettaglio, onAzione, onUsaOggi }) {
  const [menuAperto, setMenuAperto] = useState(false);
  const sem = SEMAFORO[lotto.stato_scadenza?.colore] || SEMAFORO.grigio;

  return (
    <div className={`bg-white rounded-2xl border-2 ${sem.bordo} p-4 relative`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${sem.puntino} shrink-0`} />
            <h3 className="font-black text-stone-900 truncate">{lotto.prodotto}</h3>
          </div>
          <p className="text-xs text-stone-500 mt-0.5">Lotto {lotto.numero_lotto}</p>
        </div>
        <span className={`text-[11px] font-bold px-2 py-1 rounded-full whitespace-nowrap ${sem.badge}`}>
          {lotto.stato_scadenza?.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3 text-xs text-stone-600">
        <div>Quantità: <b>{lotto.quantita ?? "—"} {lotto.unita_misura || ""}</b></div>
        <div>Valore: <b>{euro(lotto.valore_economico)}</b></div>
        <div className="col-span-2">Posizione: <b>{posizioneLabel(lotto)}</b></div>
      </div>

      <div className="flex items-center gap-2 mt-3">
        {/* "Usa oggi" — mancava (audit onesto 04/07/2026): manda il lotto
            nei task del giorno dei tablet, così il reparto lo vede subito */}
        <Button size="sm" onClick={() => onUsaOggi(lotto)} className="flex-1">
          <BellRing size={16}/> Usa oggi
        </Button>
        <Button size="sm" variant="secondary" onClick={() => onDettaglio(lotto.id)}><Eye size={16}/> Dettaglio</Button>
        <div className="relative">
          <button onClick={() => setMenuAperto((v) => !v)} className="p-2 rounded-lg border border-stone-200 hover:bg-stone-50">
            <MoreVertical size={18} />
          </button>
          {menuAperto && (
            <div className="absolute right-0 bottom-full mb-1 bg-white border border-stone-200 rounded-xl shadow-lg overflow-hidden z-10 w-44">
              {[
                { k: "sposta", label: "Sposta frigo", icon: ArrowLeftRight },
                { k: "congela", label: "Congela", icon: Snowflake },
                { k: "banco", label: "Manda al banco", icon: Store },
                { k: "recupera", label: "Recupera", icon: RotateCcw },
                { k: "smalti", label: "Smaltisci", icon: Trash2 },
              ].map(({ k, label, icon: Icon }) => (
                <button key={k} onClick={() => { setMenuAperto(false); onAzione(k, lotto); }}
                  className="w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-stone-50">
                  <Icon size={15} /> {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Vista principale ──────────────────────────────────────────────────────────
export default function CosaUsareOggiView() {
  const [lotti, setLotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [attrezzature, setAttrezzature] = useState({ frigoriferi: [], congelatori: [] });
  const [schedaLottoId, setSchedaLottoId] = useState(null);
  const [azione, setAzione] = useState(null); // { tipo, lotto }

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/lotti/cosa-usare-oggi`);
      setLotti(r.data?.lotti || []);
    } catch (e) {
      toast.error(apiError(e, "Impossibile caricare i lotti"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    carica();
    axios.get(`${API}/attrezzature/`).then((r) => setAttrezzature(r.data || { frigoriferi: [], congelatori: [] })).catch(() => {});
  }, [carica]);

  const dopoAzione = () => {
    setAzione(null);
    setSchedaLottoId(null);
    carica();
  };

  // "Usa oggi": crea il task del giorno per i tablet di reparto — il lotto
  // compare in «📋 Cosa fare oggi» e chi lo usa lo spunta col proprio nome.
  const usaOggi = async (lotto) => {
    try {
      await axios.post(`${API}/task-dipendenti`, {
        titolo: `🕐 Usa prima: ${lotto.prodotto}`,
        descrizione: `Lotto ${lotto.numero_lotto} — scade il ${lotto.data_scadenza || "?"}. Segnalato da ${getOperatoreNome() || "ufficio"} da "Cosa usare oggi".`,
        reparto: "tutti",
        tipo: "scadenza",
        priorita: "urgente",
      });
      toast.success(`"${lotto.prodotto}" mandato nei task di oggi dei tablet`);
    } catch (e) {
      toast.error(apiError(e, "Non sono riuscito a creare il task"));
    }
  };

  return (
    <div className="max-w-5xl mx-auto p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-black text-stone-900">Cosa usare oggi</h1>
          <p className="text-sm text-stone-500">Lotti attivi ordinati per urgenza scadenza e valore economico</p>
        </div>
        <Button variant="secondary" size="sm" onClick={carica}><RefreshCw size={16}/> Aggiorna</Button>
      </div>

      {loading && <p className="text-center text-stone-500 py-8">Carico...</p>}
      {!loading && lotti.length === 0 && (
        <p className="text-center text-stone-500 py-8">Nessun lotto attivo al momento.</p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {lotti.map((l) => (
          <LottoCard key={l.id} lotto={l}
            onDettaglio={setSchedaLottoId}
            onUsaOggi={usaOggi}
            onAzione={(tipo, lotto) => setAzione({ tipo, lotto })} />
        ))}
      </div>

      {schedaLottoId && (
        <SchedaLottoModal lottoId={schedaLottoId} onClose={() => setSchedaLottoId(null)}
          onCambiato={(tipo, lotto) => setAzione({ tipo, lotto })} />
      )}
      {azione && (
        <AzioneModal lotto={azione.lotto} azione={azione.tipo} attrezzature={attrezzature}
          onClose={() => setAzione(null)} onFatto={dopoAzione} />
      )}
    </div>
  );
}
