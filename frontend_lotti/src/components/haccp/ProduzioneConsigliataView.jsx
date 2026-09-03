import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  ChefHat, TrendingUp, TrendingDown, Check, X, Pencil, Calendar, Sparkles, RefreshCw,
} from "lucide-react";
import Button from "../ui/Button";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { getOperatoreNome } from "../../auth";

function oggiISO(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

const STATO_BADGE = {
  accettato:  "bg-emerald-100 text-emerald-700",
  modificato: "bg-amber-100 text-amber-700",
  ignorato:   "bg-stone-100 text-stone-500",
};

function SuggerimentoCard({ s, onDecidi }) {
  const [modificando, setModificando] = useState(false);
  const [quantita, setQuantita] = useState(s.quantita_consigliata);
  const decisione = s.decisione;

  return (
    <div className="bg-white rounded-2xl border-2 border-stone-200 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-black text-stone-900 truncate">{s.prodotto}</h3>
          {s.stagionale && <span className="text-[10px] font-bold bg-[#e8efe9] text-[#3f5a4e] px-2 py-0.5 rounded-full">Stagionale</span>}
        </div>
        {decisione && (
          <span className={`text-[11px] font-bold px-2 py-1 rounded-full whitespace-nowrap ${STATO_BADGE[decisione.stato] || ""}`}>
            {decisione.stato === "ignorato" ? "Ignorato" : `${decisione.stato === "accettato" ? "Accettato" : "Modificato"}: ${decisione.quantita_decisa} pz`}
          </span>
        )}
      </div>

      <div className="text-3xl font-black text-[#5b7a6b] mt-2">{s.quantita_consigliata} pz</div>
      <p className="text-xs text-stone-500 mt-1">{s.motivazione}</p>
      <div className="flex gap-4 mt-2 text-xs text-stone-400">
        <span>Media produzione: {s.media_produzione} pz</span>
        {s.media_invenduto !== null && <span>Media invenduto: {s.media_invenduto} pz{s.pct_invenduto_storico !== null ? ` (${s.pct_invenduto_storico}%)` : ""}</span>}
      </div>

      {modificando ? (
        <div className="flex items-center gap-2 mt-3">
          <input type="number" min="0" value={quantita} onChange={(e) => setQuantita(Number(e.target.value))}
            className="w-24 px-2 py-1.5 border border-stone-200 rounded-lg text-sm" />
          <Button size="sm" onClick={() => { onDecidi(s, "modificato", quantita); setModificando(false); }}>Conferma</Button>
          <Button size="sm" variant="secondary" onClick={() => setModificando(false)}>Annulla</Button>
        </div>
      ) : (
        <div className="flex gap-2 mt-3">
          <Button size="sm" onClick={() => onDecidi(s, "accettato", s.quantita_consigliata)}><Check size={15}/> Accetta</Button>
          <Button size="sm" variant="secondary" onClick={() => { setQuantita(s.quantita_consigliata); setModificando(true); }}><Pencil size={15}/> Modifica</Button>
          <Button size="sm" variant="secondary" onClick={() => onDecidi(s, "ignorato", null)}><X size={15}/> Ignora</Button>
        </div>
      )}
    </div>
  );
}

function ListaCompatta({ titolo, icon: Icon, righe, campo }) {
  if (!righe?.length) return null;
  return (
    <div className="bg-white rounded-2xl border border-stone-200 p-4">
      <h3 className="text-sm font-black text-stone-900 mb-2 flex items-center gap-2">
        <Icon size={16} className="text-[#5b7a6b]" /> {titolo}
      </h3>
      <div className="space-y-1">
        {righe.map((r, i) => (
          <div key={i} className="flex justify-between text-xs">
            <span className="text-stone-700">{r.prodotto}</span>
            <span className="font-bold text-stone-900">{campo === "spreco" ? `${r.pct_invenduto_storico}%` : `${r.media_produzione} pz`}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ProduzioneConsigliataView() {
  const [data, setData] = useState(oggiISO(1)); // default: domani
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(true);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/produzione-consigliata`, { params: { data } });
      setDati(r.data);
    } catch (e) {
      toast.error(apiError(e, "Impossibile caricare i suggerimenti"));
    } finally {
      setLoading(false);
    }
  }, [data]);

  useEffect(() => { carica(); }, [carica]);

  const decidi = async (s, stato, quantitaDecisa) => {
    try {
      await axios.post(`${API}/produzione-consigliata/decisione`, {
        data, prodotto: s.prodotto, quantita_consigliata: s.quantita_consigliata,
        quantita_decisa: quantitaDecisa, stato, operatore_nome: getOperatoreNome(),
      });
      toast.success(stato === "ignorato" ? "Suggerimento ignorato" : `${stato === "accettato" ? "Accettato" : "Modificato"}: ${quantitaDecisa} pz`);
      carica();
    } catch (e) {
      toast.error(apiError(e, "Operazione non riuscita"));
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-black text-stone-900">Produzione consigliata</h1>
          <p className="text-sm text-stone-500">Cosa produrre, in base a storico, invenduto, festività e incassi</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-stone-200 overflow-hidden">
            <button onClick={() => setData(oggiISO(0))} className={`px-3 py-1.5 text-sm font-semibold ${data === oggiISO(0) ? "bg-[#5b7a6b] text-white" : "bg-white text-stone-600"}`}>Oggi</button>
            <button onClick={() => setData(oggiISO(1))} className={`px-3 py-1.5 text-sm font-semibold ${data === oggiISO(1) ? "bg-[#5b7a6b] text-white" : "bg-white text-stone-600"}`}>Domani</button>
          </div>
          <label className="flex items-center gap-1.5 text-sm text-stone-600">
            <Calendar size={16} />
            <input type="date" value={data} onChange={(e) => setData(e.target.value)}
              className="border border-stone-200 rounded-lg px-2 py-1.5 text-sm" />
          </label>
          <Button variant="secondary" size="sm" onClick={carica}><RefreshCw size={16}/> Aggiorna</Button>
        </div>
      </div>

      {loading && <p className="text-center text-stone-500 py-8">Carico...</p>}

      {!loading && dati && (
        <>
          <div className="text-sm text-stone-500 flex items-center gap-2 flex-wrap">
            <span className="capitalize font-semibold text-stone-700">{dati.giorno_settimana}</span>
            {dati.festivo_o_ponte && (
              <span className="bg-amber-100 text-amber-700 text-xs font-bold px-2 py-1 rounded-full">🎉 {dati.festivo_o_ponte}</span>
            )}
            {dati.trend_incassi && Math.abs(dati.trend_incassi.fattore_pct) >= 3 && (
              <span className={`text-xs font-bold px-2 py-1 rounded-full flex items-center gap-1 ${dati.trend_incassi.variazione_incassi_pct > 0 ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                {dati.trend_incassi.variazione_incassi_pct > 0 ? <TrendingUp size={12}/> : <TrendingDown size={12}/>}
                Incassi {dati.trend_incassi.variazione_incassi_pct > 0 ? "+" : ""}{dati.trend_incassi.variazione_incassi_pct}% (2 settimane)
              </span>
            )}
          </div>

          {dati.suggerimenti.length === 0 && (
            <p className="text-center text-stone-400 py-8">Nessun suggerimento: servono almeno 2 produzioni storiche nello stesso giorno della settimana.</p>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {dati.suggerimenti.map((s) => (
              <SuggerimentoCard key={s.prodotto} s={s} onDecidi={decidi} />
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ListaCompatta titolo="Prodotti più richiesti" icon={Sparkles} righe={dati.prodotti_piu_richiesti} campo="richiesti" />
            <ListaCompatta titolo="Prodotti più sprecati" icon={ChefHat} righe={dati.prodotti_piu_sprecati} campo="spreco" />
          </div>
        </>
      )}
    </div>
  );
}
