import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Check, ExternalLink, PencilLine, Ban } from "lucide-react";
import { apiError } from "../../utils/apiError";
import { API } from "../../utils/constants";

// Proposte della ricerca web: per ogni riga di fattura il sistema ha già
// cercato cos'è («OLVA THERMO CREMA» → margarina) e quali ingredienti di
// ricetta serve. Una persona conferma con un tocco, cambia il nome o dice
// «non è un ingrediente». Una riga confermata ha la precedenza nel FIFO.

const CONFIDENZA = {
  alta: { testo: "sicura", cls: "bg-[#e7f1ec] text-[#3d8168]" },
  media: { testo: "da guardare", cls: "bg-[#f6ecdf] text-[#c4894a]" },
  bassa: { testo: "incerta", cls: "bg-[#fbe9e6] text-[#d35f4e]" },
};

function Proposta({ v, onConferma }) {
  const [modifica, setModifica] = useState(false);
  const [nome, setNome] = useState(v.nome_canc || "");
  const [ingredienti, setIngredienti] = useState(v.ingredienti_ricetta || []);
  const [salvando, setSalvando] = useState(false);
  const conf = CONFIDENZA[v.confidenza] || CONFIDENZA.media;

  const invia = async (alimentare) => {
    setSalvando(true);
    try {
      await onConferma(v, { nome_canc: nome.trim(), ingredienti_ricetta: ingredienti, alimentare });
    } finally {
      setSalvando(false);
    }
  };

  return (
    <li className="rounded-xl border border-[#e6e0d4] bg-[#fffefb] p-3" data-testid="proposta-articolo">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-[#2a3329]">{v.descrizione_originale || v.descrizione_key}</div>
          <div className="text-xs text-stone-500">{v.fornitore || "—"}</div>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${conf.cls}`}>{conf.testo}</span>
      </div>
      {v.cosa_e && <p className="mt-2 text-sm text-stone-600">{v.cosa_e}</p>}
      {v.fonte_url && (
        <a href={v.fonte_url} target="_blank" rel="noreferrer"
          className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-[#5b7a6b] underline">
          <ExternalLink size={12} aria-hidden="true" /> fonte della ricerca
        </a>
      )}

      {v.alimentare === false ? (
        <div className="mt-2 text-sm font-semibold text-stone-500">Proposta: non è un ingrediente</div>
      ) : (
        <div className="mt-2">
          <div className="text-xs font-bold uppercase tracking-wide text-stone-500">Lo chiamiamo</div>
          {modifica ? (
            <input value={nome} onChange={(e) => setNome(e.target.value)} list="canonici-proposte"
              aria-label="Nome dell'articolo"
              className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm focus:border-[#5b7a6b] focus:outline-none" />
          ) : (
            <div className="text-base font-extrabold tracking-tight text-[#3f5a4e]">{nome}</div>
          )}
          {ingredienti.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Ingredienti di ricetta serviti">
              {ingredienti.map((i) => (
                <button key={i} type="button"
                  onClick={() => setIngredienti((xs) => xs.filter((x) => x !== i))}
                  title="Tocca per togliere"
                  className="min-h-[36px] rounded-full border border-[#5b7a6b] bg-[#eef3ef] px-3 text-xs font-bold text-[#3f5a4e]">
                  {i} ×
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" disabled={salvando || (v.alimentare !== false && !nome.trim())}
          onClick={() => invia(v.alimentare !== false)}
          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#5b7a6b] px-4 text-sm font-bold text-white disabled:opacity-40">
          <Check size={16} aria-hidden="true" /> Conferma
        </button>
        {v.alimentare !== false && (
          <button type="button" onClick={() => setModifica((m) => !m)}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-[#5b7a6b] px-4 text-sm font-bold text-[#5b7a6b]">
            <PencilLine size={16} aria-hidden="true" /> Cambia nome
          </button>
        )}
        {v.alimentare !== false && (
          <button type="button" disabled={salvando} onClick={() => invia(false)}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-stone-300 px-4 text-sm font-bold text-stone-500">
            <Ban size={16} aria-hidden="true" /> Non è un ingrediente
          </button>
        )}
      </div>
    </li>
  );
}

export default function ProposteArticoliPanel({ canonici = [] }) {
  const [voci, setVoci] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState("");

  const carica = useCallback(async () => {
    setLoading(true);
    setErrore("");
    try {
      const { data } = await axios.get(`${API}/normalizzazione/proposte-web`, { params: { stato: "da_confermare" } });
      setVoci(data.voci || []);
    } catch (e) {
      setErrore(apiError(e));
      setVoci([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const conferma = async (v, scelta) => {
    try {
      const { data } = await axios.post(`${API}/normalizzazione/conferma-articolo`, {
        descrizione: v.descrizione_key, ...scelta,
      });
      toast.success(scelta.alimentare
        ? `${v.descrizione_originale || v.descrizione_key} → ${scelta.nome_canc} (${data.lotti_aggiornati} lotti)`
        : "Segnato come non ingrediente");
      setVoci((xs) => xs.filter((x) => x.descrizione_key !== v.descrizione_key));
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  if (loading) return <div className="py-10 text-center text-stone-500">Caricamento…</div>;
  if (errore) {
    return (
      <div role="alert" className="rounded-xl border border-[#d35f4e] bg-[#fbe9e6] p-4 text-sm text-[#d35f4e]">
        Proposte non disponibili: {errore}
        <button type="button" onClick={carica} className="ml-3 font-bold underline">Riprova</button>
      </div>
    );
  }
  if (voci.length === 0) {
    return (
      <div className="rounded-xl border border-stone-200 bg-[#eef3ef] py-10 text-center text-stone-500">
        Nessuna proposta da confermare.
      </div>
    );
  }
  return (
    <div>
      <p className="mb-3 text-sm text-stone-600">
        {voci.length} righe di fattura con una proposta dalla ricerca web. Finché non confermi, il
        magazzino le aggancia solo per nome e lo scarico resta da ricontrollare.
      </p>
      <datalist id="canonici-proposte">
        {canonici.map((c) => <option key={c} value={c} />)}
      </datalist>
      <ul className="grid gap-3 md:grid-cols-2">
        {voci.map((v) => (
          <Proposta key={v.descrizione_key} v={v} onConferma={conferma} />
        ))}
      </ul>
    </div>
  );
}
