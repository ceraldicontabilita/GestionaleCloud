import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { BookOpen, ExternalLink, RefreshCw, Search, ShoppingCart } from "lucide-react";
import { toast } from "sonner";
import { API } from "../../utils/constants";

export default function IrcaSpuntiView() {
  const [sezione, setSezione] = useState("ricette");
  const [ricette, setRicette] = useState([]);
  const [totaleRicette, setTotaleRicette] = useState(0);
  const [cataloghi, setCataloghi] = useState([]);
  const [selezionate, setSelezionate] = useState({});
  const [query, setQuery] = useState("");
  const [distinta, setDistinta] = useState(null);
  const [descrizione, setDescrizione] = useState("");
  const [peso, setPeso] = useState(100);
  const [pezzi, setPezzi] = useState(10);
  const [progetto, setProgetto] = useState(null);
  const [progettando, setProgettando] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [r, c] = await Promise.all([
        axios.get(`${API}/irca/ricette?limit=200`),
        axios.get(`${API}/irca/cataloghi`),
      ]);
      setRicette(r.data?.ricette || []);
      setTotaleRicette(r.data?.totale || 0);
      setCataloghi(c.data?.cataloghi || []);
    } catch { toast.error("Impossibile caricare l'archivio IRCA"); }
    setLoading(false);
  }, []);
  useEffect(() => { carica(); }, [carica]);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const r = await axios.get(`${API}/irca/ricette?limit=500&q=${encodeURIComponent(query.trim())}`);
        setRicette(r.data?.ricette || []);
        setTotaleRicette(r.data?.totale || 0);
      } catch { toast.error("Ricerca ricette IRCA non riuscita"); }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const caricaAltre = async () => {
    try {
      const r = await axios.get(`${API}/irca/ricette?limit=200&skip=${ricette.length}`);
      setRicette(current => [...current, ...(r.data?.ricette || [])]);
      setTotaleRicette(r.data?.totale || totaleRicette);
    } catch { toast.error("Caricamento di altre ricette non riuscito"); }
  };

  const payload = () => ({
    ricette: Object.entries(selezionate).map(([slug, moltiplicatore]) => ({ slug, moltiplicatore })),
  });

  const genera = async () => {
    if (!Object.keys(selezionate).length) return toast.error("Seleziona almeno una ricetta");
    try {
      const r = await axios.post(`${API}/irca/distinta`, payload());
      setDistinta(r.data);
      toast.success("Distinta ingredienti generata");
    } catch { toast.error("Errore nella generazione della distinta"); }
  };

  const aggiungiOrdine = async () => {
    try {
      const r = await axios.post(`${API}/irca/distinta/aggiungi-carrello`, payload());
      window.dispatchEvent(new Event("ordini_smart_cart_update"));
      toast.success(`${r.data.aggiunti} prodotti aggiunti alla bozza ordini; ${r.data.da_verificare} da verificare`);
    } catch { toast.error("Impossibile creare la bozza ordine"); }
  };

  const sincronizza = async () => {
    setSyncing(true);
    try {
      const r = await axios.post(`${API}/irca/sincronizza`);
      toast.success(r.data.message || r.data.messaggio);
    } catch { toast.error("Avvio sincronizzazione IRCA non riuscito"); }
    setSyncing(false);
  };

  const progetta = async () => {
    if (descrizione.trim().length < 20) return toast.error("Descrivi meglio il risultato desiderato");
    setProgettando(true);
    try {
      const r = await axios.post(`${API}/irca/progetta-dolce`, {
        descrizione, peso_pezzo_g: Number(peso), pezzi: Number(pezzi), genera_immagine: true,
      }, { timeout: 240000 });
      setProgetto(r.data);
      toast.success("Bozza tecnica e quantità generate");
    } catch (e) { toast.error(e.response?.data?.detail || "Progettazione non riuscita"); }
    setProgettando(false);
  };

  if (loading) return <div className="p-10 text-center text-gray-500">Caricamento archivio IRCA…</div>;
  return <div className="space-y-5">
    <div className="bg-white border border-gray-100 rounded-xl p-4 flex flex-wrap items-center gap-3">
      <div className="mr-auto">
        <h2 className="font-bold text-xl text-gray-800">Spunti IRCA</h2>
        <p className="text-sm text-gray-500">Ricette, cataloghi e distinta per preparare la bozza d'ordine</p>
      </div>
      <button onClick={sincronizza} disabled={syncing} className="g-btn g-btn-secondary flex items-center gap-2">
        <RefreshCw size={15} className={syncing ? "animate-spin" : ""} /> Aggiorna archivio
      </button>
    </div>

    <div className="g-tabs">
      <button className={`g-tab${sezione === "ricette" ? " active" : ""}`} onClick={() => setSezione("ricette")}>Ricette ({totaleRicette})</button>
      <button className={`g-tab${sezione === "cataloghi" ? " active" : ""}`} onClick={() => setSezione("cataloghi")}>Cataloghi e ricettari ({cataloghi.length})</button>
      <button className={`g-tab${sezione === "crea" ? " active" : ""}`} onClick={() => setSezione("crea")}>Crea il tuo dolce</button>
    </div>

    {sezione === "crea" ? <div className="space-y-5">
      <section className="bg-white border rounded-xl p-5 space-y-4">
        <div><h3 className="font-bold text-lg">Descrivi il risultato che vuoi ottenere</h3>
          <p className="text-sm text-gray-500">Indica struttura, ripieno, copertura, gusto e consistenza. La proposta cita ricette e prodotti IRCA usati come fonte.</p></div>
        <textarea rows={5} value={descrizione} onChange={e => setDescrizione(e.target.value)}
          placeholder="Esempio: dolce morbido con cuore di crema al cioccolato, consistenza pan di Spagna, glassa al cioccolato e riso soffiato…"
          className="w-full border rounded-xl p-3 text-sm" />
        <div className="flex flex-wrap gap-4 items-end">
          <label className="text-sm">Peso finito per pezzo (g)<input type="number" min="1" value={peso} onChange={e => setPeso(e.target.value)} className="block border rounded-lg px-3 py-2 mt-1 w-44" /></label>
          <label className="text-sm">Numero pezzi<input type="number" min="1" value={pezzi} onChange={e => setPezzi(e.target.value)} className="block border rounded-lg px-3 py-2 mt-1 w-44" /></label>
          <button onClick={progetta} disabled={progettando} className="g-btn g-btn-primary">{progettando ? "Studio cataloghi e formula…" : "Genera concept e quantità"}</button>
        </div>
      </section>
      {progetto && <section className="bg-white border rounded-xl overflow-hidden">
        <div className="grid lg:grid-cols-[360px_1fr]">
          <div className="bg-gray-100 min-h-72">{progetto.immagine_url && <img src={progetto.immagine_url} alt={progetto.titolo} className="w-full h-full object-cover" />}</div>
          <div className="p-5 space-y-3"><div><h3 className="font-bold text-xl">{progetto.titolo}</h3><p className="text-gray-600">{progetto.descrizione_concept}</p></div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
              <div className="bg-gray-50 rounded p-2"><b>{progetto.richiesta.pezzi}</b><br />pezzi</div>
              <div className="bg-gray-50 rounded p-2"><b>{progetto.richiesta.peso_pezzo_g} g</b><br />per pezzo</div>
              <div className="bg-gray-50 rounded p-2"><b>{progetto.peso_finito_totale_g} g</b><br />peso finito</div>
              <div className="bg-gray-50 rounded p-2"><b>{progetto.massa_lorda_stimata_g} g</b><br />massa lorda stimata</div>
            </div>
            <p className="text-xs text-amber-700">Bozza tecnica da validare con una prova di laboratorio. Resa stimata: {progetto.resa_percentuale}%. Immagine: {progetto.immagine_stato.replaceAll("_", " ")}.</p>
          </div>
        </div>
        <div className="p-5 space-y-5">
          {progetto.componenti?.map((c, ci) => <div key={`${c.nome}-${ci}`}><h4 className="font-bold capitalize">{c.nome}</h4><p className="text-sm text-gray-600 mb-2">{c.descrizione}</p>
            <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b text-left"><th className="py-2">Ingrediente/prodotto</th><th>Per kg lordo</th><th>Totale</th><th>Funzione</th><th>Fonte</th></tr></thead>
              <tbody>{c.ingredienti?.map((i, ii) => <tr key={ii} className="border-b last:border-0"><td className="py-2 font-medium">{i.prodotto_irca?.nome || i.nome}</td><td>{i.quantita_per_kg_lordo_g} g</td><td className="font-semibold">{i.quantita_totale_g} g</td><td>{i.funzione}</td><td>{i.prodotto_irca?.link_prodotto ? <a className="text-blue-700" href={i.prodotto_irca.link_prodotto} target="_blank" rel="noreferrer">IRCA</a> : i.evidenza || "Ingrediente comune"}</td></tr>)}</tbody>
            </table></div></div>)}
          {!!progetto.emulsionanti_e_stabilizzanti?.length && <div><h4 className="font-bold">Emulsionanti e stabilizzanti proposti</h4><ul className="list-disc pl-5 text-sm">{progetto.emulsionanti_e_stabilizzanti.map((e, i) => <li key={i}>{e.product_slug}: {e.motivo} {e.dose_da_validare && <b>— dose da validare</b>}</li>)}</ul></div>}
          <div className="grid md:grid-cols-2 gap-5"><div><h4 className="font-bold">Procedimento proposto</h4><ol className="list-decimal pl-5 text-sm space-y-1">{progetto.procedimento?.map((p, i) => <li key={i}>{p}</li>)}</ol></div>
            <div><h4 className="font-bold">Controlli e rischi</h4><ul className="list-disc pl-5 text-sm space-y-1">{progetto.controlli_e_rischi?.map((p, i) => <li key={i}>{p}</li>)}</ul></div></div>
          {!!progetto.ricette_riferimento?.length && <div><h4 className="font-bold">Ricette IRCA di riferimento</h4><div className="flex flex-wrap gap-2 mt-2">{progetto.ricette_riferimento.map(r => <a key={r.slug} href={r.fonte.url} target="_blank" rel="noreferrer" className="border rounded-lg px-3 py-2 text-sm text-blue-700">{r.fonte.nome} · {r.motivo}</a>)}</div></div>}
        </div>
      </section>}
    </div> : sezione === "cataloghi" ? <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
      {cataloghi.map(c => <article key={c.id} className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        <img src={c.immagine_url || c.copertina_flipsnack_url} alt="" className="w-full aspect-[4/5] object-cover bg-gray-100" />
        <div className="p-3 space-y-2">
          <span className="text-[11px] uppercase font-bold text-[#5b7a6b]">{c.tipo}</span>
          <h3 className="font-semibold text-sm leading-snug">{c.titolo}</h3>
          {c.premium && <span className="inline-block text-xs px-2 py-1 rounded bg-amber-100 text-amber-800">Premium · accesso richiesto</span>}
          {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="text-sm text-blue-700 flex items-center gap-1">Apri pubblicazione <ExternalLink size={13} /></a>}
        </div>
      </article>)}
    </div> : <>
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[240px]">
          <Search size={15} className="absolute left-3 top-3 text-gray-400" />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Cerca ricetta o categoria…" className="w-full border rounded-lg py-2 pl-9 pr-3" />
        </div>
        <button onClick={genera} className="g-btn g-btn-primary flex items-center gap-2"><BookOpen size={15} /> Genera distinta ({Object.keys(selezionate).length})</button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {ricette.map(r => {
          const scelta = Object.prototype.hasOwnProperty.call(selezionate, r.slug);
          return <article key={r.slug} className={`bg-white border rounded-xl overflow-hidden ${scelta ? "border-[#5b7a6b] ring-1 ring-[#5b7a6b]" : "border-gray-100"}`}>
            <div className="flex gap-3 p-3">
              <img src={r.immagine_url} alt="" className="w-24 h-24 object-cover rounded-lg bg-gray-100" />
              <div className="min-w-0 flex-1">
                <label className="flex gap-2 items-start cursor-pointer">
                  <input type="checkbox" checked={scelta} onChange={e => setSelezionate(s => {
                    const next = { ...s }; if (e.target.checked) next[r.slug] = 1; else delete next[r.slug]; return next;
                  })} className="mt-1" />
                  <span className="font-semibold leading-snug">{r.nome}</span>
                </label>
                <p className="text-xs text-gray-500 mt-1">{r.categoria} · {r.livello}</p>
                {scelta && <label className="text-xs flex items-center gap-2 mt-2">Moltiplicatore
                  <input type="number" min="0.1" step="0.1" value={selezionate[r.slug]} onChange={e => setSelezionate(s => ({ ...s, [r.slug]: Number(e.target.value) || 1 }))} className="w-20 border rounded px-2 py-1" />
                </label>}
                <a href={r.url} target="_blank" rel="noreferrer" className="text-xs text-blue-700 mt-2 inline-flex items-center gap-1">Ricetta ufficiale <ExternalLink size={12} /></a>
              </div>
            </div>
          </article>;
        })}
      </div>
      {!query.trim() && ricette.length < totaleRicette && <div className="text-center">
        <button onClick={caricaAltre} className="g-btn g-btn-secondary">Mostra altre ricette ({ricette.length} di {totaleRicette})</button>
      </div>}
    </>}

    {distinta && <section className="bg-white border rounded-xl p-4 space-y-3">
      <div className="flex flex-wrap justify-between gap-3 items-center">
        <div><h3 className="font-bold text-lg">Distinta prodotti e ingredienti</h3>
          <p className="text-sm text-gray-500">{distinta.totali.pronti} associati a MePA · {distinta.totali.da_verificare} da verificare</p></div>
        <button onClick={aggiungiOrdine} className="g-btn g-btn-primary flex items-center gap-2"><ShoppingCart size={15} /> Crea bozza ordine</button>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="text-left border-b"><th className="py-2">Ingrediente / prodotto</th><th>Quantità</th><th>Codice IRCA</th><th>Da chi</th><th>Stato</th></tr></thead>
        <tbody>{distinta.righe.map((r, i) => <tr key={`${r.ingrediente}-${i}`} className="border-b last:border-0">
          <td className="py-2"><div className="font-medium">{r.ingrediente}</div><div className="text-xs text-gray-500 max-w-xl">{r.descrizione}</div></td>
          <td>{r.quantita_min == null ? r.dosi_originali.join(" + ") : `${r.quantita_min}${r.quantita_max !== r.quantita_min ? `–${r.quantita_max}` : ""}${r.unita}`}</td>
          <td>{r.codici_irca?.join(", ") || "—"}</td>
          <td>{r.fornitore ? `${r.fornitore.nome}${r.fornitore.codice ? ` · ${r.fornitore.codice}` : ""}` : "Da scegliere"}</td>
          <td><span className={`text-xs px-2 py-1 rounded ${r.stato === "pronto" ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}`}>{r.stato}</span></td>
        </tr>)}</tbody>
      </table></div>
      <p className="text-xs text-amber-700">La bozza inserisce una confezione per prodotto: il numero di confezioni resta da confermare perché dipende dal formato di vendita.</p>
    </section>}
  </div>;
}
