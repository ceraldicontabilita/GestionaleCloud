import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import { apiError } from "../../utils/apiError";
import { API } from "../../utils/constants";
import { isAdmin } from "../../auth";
import { BookMarked, RefreshCw, Search, Check, X, DatabaseZap, Layers } from "lucide-react";

const SAGE = "#5b7a6b";
const inputCls =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 focus:border-[#5b7a6b] focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]/20";

// Elenco compatto delle categorie merceologiche usate dal sistema di normalizzazione,
// per il menu a tendina della conferma rapida.
const CATEGORIE = [
  "Farine e Cereali", "Dolcificanti", "Latticini e Grassi", "Uova",
  "Frutta e Verdura", "Frutta Secca", "Formaggi", "Semilavorati Pasticceria",
  "Aromi", "Bagne e Aromi", "Lieviti e Addensanti", "Cioccolato e Cacao",
  "Condimenti", "Decorazioni", "Varie Alimentari",
];

// Ultimo acquisto COME IN FATTURA: prezzo, quantità (litro/boccione/cartone) e
// unità — così Enzo riconosce il prodotto senza ricerche (richiesta 04/07/2026).
// Le righe storiche senza i campi nuovi mostrano il €/kg finché non arriva
// la prossima fattura che le tocca.
function UltimoAcquisto({ p }) {
  const prz = Number(p.ultimo_prezzo_riga) || 0;
  const qta = Number(p.ultima_quantita_riga) || 0;
  const um = (p.ultima_unita_riga || "").toUpperCase();
  if (prz > 0 || qta > 0) {
    return (
      <div className="text-xs font-semibold text-[#5b7a6b]">
        {prz > 0 ? `€ ${prz.toFixed(2)}` : "prezzo n/d"}
        {qta > 0 ? ` · ${qta} ${um || "pz"}` : ""}
      </div>
    );
  }
  const kg = Number(p.prezzo_kg) || 0;
  return kg > 0 ? <div className="text-xs font-semibold text-[#5b7a6b]">€ {kg.toFixed(2)}/kg</div> : null;
}

function RigaProdotto({ p, onSalva, onEscludi, vistaEsclusi = false }) {
  // La PROPOSTA automatica arriva già pre-compilata nel campo: Enzo conferma
  // con un tocco o corregge ("van." → Vaniglia) — regola mani-sporche.
  const [nome, setNome] = useState(p.ingrediente_canonico || p.nome_canonico || p.proposta_canonico || "");
  const [categoria, setCategoria] = useState("Varie Alimentari");
  const [salvando, setSalvando] = useState(false);
  const associato = !!(p.ingrediente_canonico || p.nome_canonico);
  const eProposta = !associato && !!p.proposta_canonico && nome === p.proposta_canonico;

  const conferma = async () => {
    if (!nome.trim()) return;
    setSalvando(true);
    try {
      await onSalva(p, nome.trim(), categoria);
    } finally {
      setSalvando(false);
    }
  };

  // Vista "Escluse": la riga mostra solo il motivo e il bottone Ripristina.
  if (vistaEsclusi) {
    return (
      <tr className="border-b border-stone-100 bg-stone-50/60">
        <td className="p-2.5 align-top">
          <div className="font-semibold text-stone-500">{p.nome_originale || p.nome_normalizzato}</div>
          <div className="text-xs text-stone-400">{p.fornitore || "—"}</div>
          <UltimoAcquisto p={p} />
        </td>
        <td className="p-2.5 align-top text-center text-xs text-stone-400">
          {p.conteggio_acquisti || 1}×
          <div>{(p.ultima_fattura_data || "").slice(0, 10) || "—"}</div>
        </td>
        <td className="p-2.5 align-top text-xs text-stone-500" colSpan={2}>
          Esclusa dal battesimo
          {p.escluso_motivo ? ` · ${String(p.escluso_motivo).replace("famiglia:", "famiglia ")}` : ""}
        </td>
        <td className="p-2.5 align-top text-right">
          <button
            onClick={() => onEscludi(p, false)}
            className="inline-flex items-center gap-1 rounded-lg border border-[#5b7a6b] px-3 py-2 text-xs font-bold text-[#5b7a6b] hover:bg-[#eef3ef]"
          >
            <RefreshCw size={13} /> Ripristina
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr className={`border-b border-stone-100 ${associato ? "" : "bg-amber-50/40"}`}>
      <td className="p-2.5 align-top">
        <div className="font-semibold text-stone-800">{p.nome_originale || p.nome_normalizzato}</div>
        <div className="text-xs text-stone-500">{p.fornitore || "—"}</div>
        <UltimoAcquisto p={p} />
      </td>
      <td className="p-2.5 align-top text-center text-xs text-stone-500">
        {p.conteggio_acquisti || 1}×
        <div>{(p.ultima_fattura_data || "").slice(0, 10) || "—"}</div>
      </td>
      <td className="p-2.5 align-top">
        <input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="nome ingrediente…"
          list="canonici-diz"
          className={inputCls}
        />
        {eProposta && (
          <div className="mt-1 text-[11px] font-bold text-[#5b7a6b]">
            proposta del sistema — confermala o correggila
          </div>
        )}
      </td>
      <td className="p-2.5 align-top">
        <select value={categoria} onChange={(e) => setCategoria(e.target.value)} className={inputCls}>
          {CATEGORIE.map((c) => <option key={c}>{c}</option>)}
        </select>
      </td>
      <td className="p-2.5 align-top text-right">
        <div className="flex flex-col items-end gap-1.5">
          <button
            onClick={conferma}
            disabled={salvando || !nome.trim()}
            className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-bold text-white disabled:opacity-40 ${
              eProposta ? "bg-green-600 hover:bg-green-700" : "bg-[#5b7a6b] hover:bg-[#4a6657]"
            }`}
          >
            <Check size={14} /> {associato ? "Aggiorna" : eProposta ? "Conferma proposta" : "Conferma"}
          </button>
          {/* Non c'entra con le ricette (segnaletica, bevande...)? Fuori dalla
              coda con un tocco. Reversibile dalla vista «Escluse». */}
          <button
            onClick={() => onEscludi(p, true)}
            title="Escludi dal battesimo: non è un ingrediente delle ricette. La ritrovi nella vista «Escluse»."
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-bold text-stone-400 hover:bg-stone-100 hover:text-[#d35f4e]"
          >
            <X size={12} /> Escludi
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function DizionarioIngredientiView() {
  const [prodotti, setProdotti] = useState([]);
  const [totale, setTotale] = useState(0);
  const [loading, setLoading] = useState(true);
  // vista: "da_associare" | "tutte" | "escluse"
  const [vista, setVista] = useState("da_associare");
  // default ON: le righe che contano per il matching ricette sono quelle dei
  // fornitori Magazzino+Lotti (richiesta Enzo 04/07/2026)
  const [soloCompleti, setSoloCompleti] = useState(true);
  const [canonici, setCanonici] = useState([]);
  const [q, setQ] = useState("");
  const [skip, setSkip] = useState(0);
  const LIMIT = 100;

  const carica = useCallback(async (nuovoSkip = 0) => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/food-cost/dizionario`, {
        params: {
          search: q.trim() || undefined,
          senza_canonico: vista === "da_associare",
          solo_completi: soloCompleti,
          solo_esclusi: vista === "escluse",
          skip: nuovoSkip,
          limit: LIMIT,
        },
      });
      setProdotti(data.prodotti || []);
      setTotale(data.totale || 0);
      setSkip(nuovoSkip);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setLoading(false);
    }
  }, [q, vista, soloCompleti]);

  useEffect(() => { carica(0); }, [carica]);

  // nomi canonici esistenti per l'autocomplete (una volta sola)
  useEffect(() => {
    axios.get(`${API}/food-cost/dizionario/canonici`)
      .then(r => setCanonici(Array.isArray(r.data) ? r.data : []))
      .catch(() => { /* non bloccante */ });
  }, []);

  const salvaRiga = async (p, nomeCanc, categoria) => {
    try {
      await axios.post(`${API}/normalizzazione/correggi-mapping`, {
        descrizione_key: p.nome_normalizzato,
        nome_canc: nomeCanc,
        categoria,
      });
      toast.success(`"${p.nome_originale}" → ${nomeCanc}`);
      // La riga associata esce dal filtro "da associare": la tolgo subito dalla lista.
      setProdotti((prev) => prev.filter((x) => x.id !== p.id));
      setTotale((t) => Math.max(0, t - 1));
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  // Escludi/ripristina UNA riga (richiesta Enzo 23/07/2026): fuori dalla coda
  // da battezzare con un tocco, reversibile dalla vista «Escluse».
  const escludiRiga = async (p, escluso) => {
    try {
      await axios.post(`${API}/food-cost/dizionario/escludi`, { id: p.id, escluso });
      toast.success(escluso
        ? `"${p.nome_originale || p.nome_normalizzato}" esclusa — la ritrovi in «Escluse»`
        : `"${p.nome_originale || p.nome_normalizzato}" ripristinata`);
      setProdotti((prev) => prev.filter((x) => x.id !== p.id));
      setTotale((t) => Math.max(0, t - 1));
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  // Escludi un'intera FAMIGLIA (bevande / alcolici / vini): prima l'anteprima
  // con conteggio ed esempi, poi la conferma — mai un'esclusione al buio.
  const [famigliaBusy, setFamigliaBusy] = useState(false);
  const escludiFamiglia = async (famiglia, etichetta) => {
    if (!famiglia) return;
    setFamigliaBusy(true);
    try {
      const ant = await axios.post(`${API}/food-cost/dizionario/escludi-famiglia`, { famiglia, anteprima: true });
      const { quante = 0, esempi = [] } = ant.data || {};
      if (!quante) { toast(`Nessuna riga di tipo "${etichetta}" da escludere.`); return; }
      const ok = await conferma(
        `Escludere ${quante} righe (${etichetta}) dal battesimo?\n\nEsempi:\n${esempi.map(e => "• " + e).join("\n")}\n\nReversibile dalla vista «Escluse».`,
        { titolo: `Escludi ${etichetta}`, ok: `Escludi ${quante} righe` }
      );
      if (!ok) return;
      const r = await axios.post(`${API}/food-cost/dizionario/escludi-famiglia`, { famiglia });
      toast.success(`${r.data?.escluse || 0} righe (${etichetta}) escluse dal battesimo`);
      carica(0);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setFamigliaBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookMarked className="text-[#5b7a6b]" size={26} />
          <h2 className="text-xl font-bold text-stone-800">Dizionario ingredienti ↔ fatture</h2>
        </div>
        <button
          onClick={() => carica(0)}
          className="rounded-lg p-2 text-stone-500 hover:bg-stone-100 hover:text-[#5b7a6b]"
          title="Ricarica"
        >
          <RefreshCw size={18} />
        </button>
      </div>
      <p className="mb-4 text-sm text-stone-500">
        Ogni riga XML trovata nelle fatture dei fornitori Magazzino+Lotti, con prezzo,
        quantità e unità come in fattura. Il sistema PROPONE il nome canonico: tu lo
        confermi con un tocco o lo correggi ("van." → Vaniglia). Le righe nuove arrivano
        da sole a ogni fattura e il Supervisore ti ricorda quante ne restano da battezzare:
        battezzarle tutte = collegamento esatto con le ricette.
      </p>
      <datalist id="canonici-diz">
        {canonici.map((c) => <option key={c} value={c} />)}
      </datalist>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" size={16} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && carica(0)}
            placeholder="Cerca per nome prodotto…"
            className={`${inputCls} pl-9`}
          />
        </div>
        <div className="flex overflow-hidden rounded-xl border border-stone-200">
          {[["da_associare", "Da associare"], ["tutte", "Tutte"], ["escluse", "Escluse"]].map(([id, lab]) => (
            <button
              key={id}
              onClick={() => setVista(id)}
              className={`px-4 py-2 text-sm font-bold ${vista === id ? "bg-[#5b7a6b] text-white" : "bg-white text-stone-500 hover:bg-stone-50"}`}
            >
              {lab}
            </button>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-stone-600">
          <input type="checkbox" checked={soloCompleti} onChange={(e) => setSoloCompleti(e.target.checked)}
            className="h-4 w-4 accent-[#5b7a6b]" />
          Solo Magazzino+Lotti
        </label>
        {/* Escludi in blocco per famiglia (bevande/alcolici/vini): tendina +
            anteprima + conferma. Non sono ingredienti delle ricette. */}
        <select
          value=""
          disabled={famigliaBusy}
          onChange={(e) => {
            const v = e.target.value;
            e.target.value = "";
            if (v === "bevande") escludiFamiglia("bevande", "bevande: acqua, bibite, succhi…");
            if (v === "alcolici") escludiFamiglia("alcolici", "alcolici e liquori");
            if (v === "vini") escludiFamiglia("vini", "vini e spumanti");
          }}
          className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-xs font-bold text-stone-600 focus:outline-none"
          title="Escludi dal battesimo un'intera famiglia di prodotti (con anteprima e conferma)"
        >
          <option value="">🚫 Escludi per categoria…</option>
          <option value="bevande">Bevande (acqua, bibite, succhi)</option>
          <option value="alcolici">Alcolici e liquori</option>
          <option value="vini">Vini e spumanti</option>
        </select>
        {isAdmin() && (
          <button
            onClick={async () => {
              try {
                const r = await axios.post(`${API}/food-cost/backfill-dati-riga-dizionario`);
                const d = r.data || {};
                toast.success(`Dati storici: ${d.aggiornati || 0} righe aggiornate su ${d.righe_scoperte ?? "?"} scoperte${d.senza_fattura_trovata ? ` (${d.senza_fattura_trovata} senza fattura in archivio)` : ""}`);
                carica(skip);
              } catch (e) { toast.error("Errore: " + apiError(e)); }
            }}
            title="Riempie prezzo/quantità/unità sulle righe storiche leggendo l'ultima fattura che le cita (una tantum, innocuo se ripetuto)"
            className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-bold text-stone-600 hover:bg-stone-50"
          >
            <DatabaseZap size={14} /> Completa dati storici
          </button>
        )}
        {isAdmin() && (
          <button
            onClick={async () => {
              try {
                // 1) anteprima (sola lettura): quanti doppioni ci sono
                const p = await axios.get(`${API}/food-cost/dizionario/duplicati`);
                const g = p.data?.gruppi_doppioni || 0;
                if (!g) { toast.success("Nessun doppione da unire nel Dizionario."); return; }
                if (!await conferma(`Trovati ${g} prodotti in doppio (${p.data.righe_da_unire} righe da unire). Unirli nel record migliore ed eliminare i doppioni? I collegamenti delle ricette vengono spostati sul record tenuto.`)) return;
                // 2) applica (solo dopo conferma)
                const r = await axios.post(`${API}/food-cost/dizionario/dedup`);
                const d = r.data || {};
                toast.success(`Doppioni uniti: ${d.gruppi_uniti || 0} prodotti, ${d.righe_eliminate || 0} righe eliminate, ${d.ricette_ripuntate || 0} ricette aggiornate.`);
                carica(skip);
              } catch (e) { toast.error("Errore: " + apiError(e)); }
            }}
            title="Unisce i prodotti presenti in doppio nel Dizionario (stessa materia prima con due nomi): mostra prima quanti sono, poi chiede conferma"
            className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-bold text-stone-600 hover:bg-stone-50"
          >
            <Layers size={14} /> Unisci doppioni
          </button>
        )}
      </div>

      {loading ? (
        <div className="py-10 text-center text-stone-500">Caricamento…</div>
      ) : prodotti.length === 0 ? (
        <div className="rounded-xl border border-stone-200 bg-[#eef3ef] py-10 text-center text-stone-500">
          {vista === "da_associare" ? "Nessuna riga da associare: tutto collegato."
            : vista === "escluse" ? "Nessuna riga esclusa." : "Nessun risultato."}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-stone-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#eef3ef] text-left text-xs font-bold uppercase tracking-wide text-[#5b7a6b]">
                  <th className="p-2.5">Riga fattura</th>
                  <th className="p-2.5 text-center">Vista</th>
                  <th className="p-2.5">Ingrediente</th>
                  <th className="p-2.5">Categoria</th>
                  <th className="p-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {prodotti.map((p) => (
                  <RigaProdotto key={p.id || p.nome_normalizzato} p={p} onSalva={salvaRiga}
                    onEscludi={escludiRiga} vistaEsclusi={vista === "escluse"} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-stone-500">
            <span>{totale} righe totali · {skip + 1}–{Math.min(skip + LIMIT, totale)}</span>
            <div className="flex gap-2">
              <button
                onClick={() => carica(Math.max(0, skip - LIMIT))}
                disabled={skip === 0}
                className="rounded-lg border border-stone-200 px-3 py-1.5 font-bold text-stone-600 hover:bg-stone-50 disabled:opacity-30"
              >
                ← Precedenti
              </button>
              <button
                onClick={() => carica(skip + LIMIT)}
                disabled={skip + LIMIT >= totale}
                className="rounded-lg border border-stone-200 px-3 py-1.5 font-bold text-stone-600 hover:bg-stone-50 disabled:opacity-30"
              >
                Successive →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
