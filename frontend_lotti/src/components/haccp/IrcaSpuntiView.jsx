import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { BookOpen, CheckCircle2, ChefHat, CircleAlert, ExternalLink, PackageCheck, RefreshCw, Search, ShoppingCart, Star, X } from "lucide-react";
import { toast } from "sonner";
import { API } from "../../utils/constants";

const ordinaPreferite = (items) => [...items].sort((a, b) =>
  Number(Boolean(b.preferito)) - Number(Boolean(a.preferito))
    || String(a.nome || "").localeCompare(String(b.nome || ""), "it")
);

const linguaCatalogo = (catalogo) => catalogo.lingua
  || (/vegan-pastry/i.test(`${catalogo.url || ""} ${catalogo.titolo_originale || ""}`) ? "en" : "it");

const titoloCatalogo = (catalogo) => catalogo.titolo_originale
  || (/vegan-pastry/i.test(catalogo.url || "") ? "Vegan pastry catalog" : catalogo.titolo);

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
  const [syncStatus, setSyncStatus] = useState(null);
  const [dettaglio, setDettaglio] = useState(null);
  const [dettaglioDistinta, setDettaglioDistinta] = useState(null);
  const [dettaglioLoading, setDettaglioLoading] = useState(false);
  const [preferitoBusy, setPreferitoBusy] = useState("");
  const [preparando, setPreparando] = useState(false);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [r, c, s] = await Promise.all([
        axios.get(`${API}/irca/ricette?limit=200`),
        axios.get(`${API}/irca/cataloghi`),
        axios.get(`${API}/irca/stato`),
      ]);
      setRicette(ordinaPreferite(r.data?.ricette || []));
      setTotaleRicette(r.data?.totale || 0);
      setCataloghi(c.data?.cataloghi || []);
      setSyncStatus(s.data || null);
    } catch { toast.error("Impossibile caricare l'archivio IRCA"); }
    setLoading(false);
  }, []);
  useEffect(() => { carica(); }, [carica]);

  useEffect(() => {
    if (syncStatus?.stato !== "in_corso") return undefined;
    const timer = setInterval(async () => {
      try {
        const r = await axios.get(`${API}/irca/stato`);
        setSyncStatus(r.data || null);
        if (r.data?.stato === "completato") {
          setSyncing(false);
          clearInterval(timer);
          await carica();
          toast.success("Archivio Ricette IRCA aggiornato");
        }
      } catch { /* il prossimo controllo riprova */ }
    }, 4000);
    return () => clearInterval(timer);
  }, [syncStatus?.stato, carica]);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const termine = query.trim();
        const limit = termine ? 500 : 200;
        const r = await axios.get(`${API}/irca/ricette?limit=${limit}&q=${encodeURIComponent(termine)}`);
        setRicette(ordinaPreferite(r.data?.ricette || []));
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
      toast.success(`${r.data.aggiunti} prodotti mancanti aggiunti; ${r.data.gia_acquistati} già acquistati esclusi; ${r.data.da_verificare} da associare`);
    } catch { toast.error("Impossibile creare la bozza ordine"); }
  };

  const impostaPreferita = async (ricetta, preferito) => {
    setPreferitoBusy(ricetta.slug);
    try {
      await axios.put(`${API}/irca/ricette/${encodeURIComponent(ricetta.slug)}/preferito`, { preferito });
      setRicette(current => ordinaPreferite(current.map(r => r.slug === ricetta.slug ? { ...r, preferito } : r)));
      setDettaglio(current => current?.slug === ricetta.slug ? { ...current, preferito } : current);
      toast.success(preferito ? "Ricetta aggiunta ai preferiti" : "Ricetta rimossa dai preferiti");
    } catch { toast.error("Preferito non salvato"); }
    setPreferitoBusy("");
  };

  const preparaProduzione = async (ricetta) => {
    setPreparando(true);
    const selezione = { ricette: [{ slug: ricetta.slug, moltiplicatore: selezionate[ricetta.slug] || 1 }] };
    try {
      const [d, c] = await Promise.all([
        axios.post(`${API}/irca/distinta`, selezione),
        axios.post(`${API}/irca/distinta/aggiungi-carrello`, selezione),
      ]);
      setDistinta(d.data);
      setSelezionate(s => ({ ...s, [ricetta.slug]: s[ricetta.slug] || 1 }));
      window.dispatchEvent(new Event("ordini_smart_cart_update"));
      toast.success(c.data.aggiunti
        ? `${c.data.aggiunti} prodotti mancanti aggiunti agli ordini; ${c.data.gia_acquistati} già acquistati esclusi${c.data.da_verificare_aggiunti ? `; ${c.data.da_verificare_aggiunti} da associare prima dell'invio` : ""}`
        : `Nessun acquisto aggiunto: ${c.data.gia_acquistati} prodotti risultano già acquistati${c.data.da_verificare ? `, ${c.data.da_verificare} da associare` : ""}`);
    } catch (e) { toast.error(e.response?.data?.detail || "Preparazione ordine non riuscita"); }
    setPreparando(false);
  };

  const sincronizza = async () => {
    setSyncing(true);
    try {
      const r = await axios.post(`${API}/irca/sincronizza`);
      setSyncStatus(s => ({ ...(s || {}), stato: "in_corso", fase: "avvio" }));
      toast.success(r.data.message || r.data.messaggio);
    } catch { toast.error("Avvio sincronizzazione IRCA non riuscito"); }
    setSyncing(false);
  };

  const apriRicetta = async (ricetta) => {
    setDettaglioLoading(true);
    setDettaglio({ ...ricetta, caricamento: true });
    setDettaglioDistinta(null);
    try {
      const [r, d] = await Promise.all([
        axios.get(`${API}/irca/ricette/${encodeURIComponent(ricetta.slug)}`),
        axios.post(`${API}/irca/distinta`, { ricette: [{ slug: ricetta.slug, moltiplicatore: 1 }] }),
      ]);
      setDettaglio(r.data);
      setDettaglioDistinta(d.data);
    } catch (e) {
      setDettaglio(null);
      toast.error(e.response?.data?.detail || "Dettaglio ricetta non disponibile");
    }
    setDettaglioLoading(false);
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
    <div className="overflow-hidden rounded-2xl border border-[#d8e3dc] bg-gradient-to-br from-[#f7f1e5] via-white to-[#eaf3ee] p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#3f5a4e] text-white shadow-sm"><ChefHat size={25}/></div>
        <div className="mr-auto">
          <p className="m-0 text-[11px] font-black uppercase tracking-[0.18em] text-[#8a6135]">Quaderno professionale</p>
          <h2 className="m-0 mt-0.5 text-2xl font-black text-[#263a31]">Ricettario IRCA</h2>
          <p className="m-0 mt-1 text-sm text-gray-600">Ricettari e ricette ufficiali archiviati nel gestionale, con prodotti MEPA e ordine dei soli mancanti.</p>
        </div>
        <div className="rounded-xl border border-white/80 bg-white/80 px-4 py-2 text-center shadow-sm">
          <strong className="block text-xl text-[#3f5a4e]">{totaleRicette}</strong><span className="text-[11px] font-bold uppercase tracking-wide text-gray-500">ricette archiviate</span>
        </div>
        <button onClick={sincronizza} disabled={syncing || syncStatus?.stato === "in_corso"} className="g-btn g-btn-secondary flex items-center gap-2">
          <RefreshCw size={15} className={(syncing || syncStatus?.stato === "in_corso") ? "animate-spin" : ""} /> {(syncing || syncStatus?.stato === "in_corso") ? "Aggiornamento…" : "Aggiorna tutte"}
        </button>
      </div>
      {syncStatus?.stato === "in_corso" && <div className="mt-4 rounded-xl bg-white/80 px-4 py-3 text-xs font-semibold text-[#3f5a4e]">Importazione in corso: {syncStatus.fase || "avvio"}{syncStatus.totale_fase ? ` · ${syncStatus.avanzamento || 0} di ${syncStatus.totale_fase}` : ""}. Le ricette già salvate restano consultabili.</div>}
    </div>

    <div className="g-tabs">
      <button className={`g-tab${sezione === "cataloghi" ? " active" : ""}`} onClick={() => setSezione("cataloghi")}>Ricettari e cataloghi ({cataloghi.length})</button>
      <button className={`g-tab${sezione === "ricette" ? " active" : ""}`} onClick={() => setSezione("ricette")}>Singole ricette ({totaleRicette})</button>
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
              <tbody>{c.ingredienti?.map((i, ii) => <tr key={ii} className="border-b last:border-0"><td className="py-2"><div className="font-medium">{i.prodotto_irca?.nome || i.nome}</div>{!!i.prodotto_irca?.codici_irca?.length && <div className="text-xs text-gray-500">Codici IRCA: {i.prodotto_irca.codici_irca.join(", ")}</div>}{(i.prodotto_irca?.descrizione_breve || i.prodotto_irca?.descrizione) && <div className="text-xs text-gray-500 max-w-lg">{i.prodotto_irca.descrizione_breve || i.prodotto_irca.descrizione}</div>}</td><td>{i.quantita_per_kg_lordo_g} g</td><td className="font-semibold">{i.quantita_totale_g} g</td><td>{i.funzione}</td><td>{i.prodotto_irca?.link_prodotto ? <a className="text-blue-700" href={i.prodotto_irca.link_prodotto} target="_blank" rel="noreferrer">IRCA</a> : i.evidenza || "Ingrediente comune"}</td></tr>)}</tbody>
            </table></div></div>)}
          {!!progetto.emulsionanti_e_stabilizzanti?.length && <div><h4 className="font-bold">Emulsionanti e stabilizzanti proposti</h4><ul className="list-disc pl-5 text-sm">{progetto.emulsionanti_e_stabilizzanti.map((e, i) => <li key={i}>{e.product_slug}: {e.motivo} {e.dose_da_validare && <b>— dose da validare</b>}</li>)}</ul></div>}
          <div className="grid md:grid-cols-2 gap-5"><div><h4 className="font-bold">Procedimento proposto</h4><ol className="list-decimal pl-5 text-sm space-y-1">{progetto.procedimento?.map((p, i) => <li key={i}>{p}</li>)}</ol></div>
            <div><h4 className="font-bold">Controlli e rischi</h4><ul className="list-disc pl-5 text-sm space-y-1">{progetto.controlli_e_rischi?.map((p, i) => <li key={i}>{p}</li>)}</ul></div></div>
          {!!progetto.ricette_riferimento?.length && <div><h4 className="font-bold">Ricette IRCA di riferimento</h4><div className="flex flex-wrap gap-2 mt-2">{progetto.ricette_riferimento.map(r => <a key={r.slug} href={r.fonte.url} target="_blank" rel="noreferrer" className="border rounded-lg px-3 py-2 text-sm text-blue-700">{r.fonte.nome} · {r.motivo}</a>)}</div></div>}
        </div>
      </section>}
    </div> : sezione === "cataloghi" ? <div className="space-y-4">
      <div className="rounded-2xl border border-[#e6ddce] bg-[#fffaf0] p-4"><h3 className="m-0 font-black text-[#4a3826]">Biblioteca dei ricettari</h3><p className="m-0 mt-1 text-sm text-[#725b42]">I cataloghi sono documenti di consultazione. Per scegliere cosa produrre usa “Singole ricette”: la scheda si apre nel gestionale e controlla i prodotti MEPA mancanti senza aprire il catalogo esterno.</p><button type="button" onClick={() => setSezione("ricette")} className="mt-3 rounded-xl bg-[#3f5a4e] px-4 py-2 text-sm font-black text-white">Vai alle ricette da produrre</button></div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      {cataloghi.map(c => <article key={c.id} className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm">
        <img src={c.immagine_url || c.copertina_flipsnack_url} alt="" className="w-full aspect-[4/5] object-cover bg-gray-100" />
        <div className="p-3 space-y-2">
          <span className="text-[11px] uppercase font-bold text-[#5b7a6b]">{c.tipo}</span>
          <h3 className="font-semibold text-sm leading-snug">{titoloCatalogo(c)}</h3>
          <span className="inline-block rounded bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-700">Lingua: {linguaCatalogo(c) === "en" ? "Inglese" : "Italiano"}</span>
          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700"><CheckCircle2 size={12}/> Salvato nel gestionale</span>
          {c.premium && <span className="inline-block text-xs px-2 py-1 rounded bg-amber-100 text-amber-800">Premium · accesso richiesto</span>}
          {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="text-sm font-bold text-[#3f5a4e] flex items-center gap-1">Consulta catalogo originale{linguaCatalogo(c) === "en" ? " (inglese)" : ""} <ExternalLink size={13} /></a>}
        </div>
      </article>)}
      </div>
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
          return <article key={r.slug} className={`group overflow-hidden rounded-2xl border bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${scelta ? "border-[#5b7a6b] ring-1 ring-[#5b7a6b]" : "border-[#e8e2d8]"}`}>
            <div className="relative h-44 overflow-hidden bg-[#f3efe7]">
              <button type="button" aria-label={`Apri ricetta ${r.nome}`} onClick={() => apriRicetta(r)} className="h-full w-full p-0 text-left">
                {r.immagine_url ? <img src={r.immagine_url} alt={r.nome} className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]" /> : <span className="flex h-full items-center justify-center text-[#8ca193]"><ChefHat size={42}/></span>}
              </button>
              <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-[#3f5a4e] shadow-sm">{r.categoria || "Ricetta IRCA"}</span>
              <button type="button" aria-label={r.preferito ? `Rimuovi ${r.nome} dai preferiti` : `Aggiungi ${r.nome} ai preferiti`}
                disabled={preferitoBusy === r.slug} onClick={() => impostaPreferita(r, !r.preferito)}
                className={`absolute right-3 top-3 rounded-full p-2 shadow-sm ${r.preferito ? "bg-amber-400 text-white" : "bg-white/90 text-gray-500"}`}>
                <Star size={17} fill={r.preferito ? "currentColor" : "none"}/>
              </button>
            </div>
            <div className="p-4">
              <div className="min-w-0">
                <label className="flex gap-2 items-start cursor-pointer">
                  <input type="checkbox" checked={scelta} onChange={e => setSelezionate(s => {
                    const next = { ...s }; if (e.target.checked) next[r.slug] = 1; else delete next[r.slug]; return next;
                  })} className="mt-1" />
                  <span className="font-black leading-snug text-[#263a31]">{r.nome}</span>
                </label>
                <p className="text-xs text-gray-500 mt-1">{r.livello || "Livello non indicato"} · {(r.ingredienti || []).length} ingredienti</p>
                {scelta && <label className="text-xs flex items-center gap-2 mt-2">Moltiplicatore
                  <input type="number" min="0.1" step="0.1" value={selezionate[r.slug]} onChange={e => setSelezionate(s => ({ ...s, [r.slug]: Number(e.target.value) || 1 }))} className="w-20 border rounded px-2 py-1" />
                </label>}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" onClick={() => apriRicetta(r)} className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-[#3f5a4e] px-3 py-2 text-xs font-black text-white"><BookOpen size={14}/> Apri nel gestionale</button>
                  <a href={r.url} target="_blank" rel="noreferrer" aria-label={`Apri ${r.nome} sul sito IRCA`} className="flex items-center justify-center rounded-xl border border-gray-200 px-3 text-gray-500 hover:bg-gray-50"><ExternalLink size={14} /></a>
                </div>
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
          <p className="text-sm text-gray-500">{distinta.totali.gia_acquistati} già acquistati · {distinta.totali.da_acquistare} da acquistare · {distinta.totali.da_verificare} da associare</p></div>
        <button onClick={aggiungiOrdine} disabled={!distinta.totali.da_acquistare} className="g-btn g-btn-primary flex items-center gap-2"><ShoppingCart size={15} /> Aggiungi solo i mancanti ({distinta.totali.da_acquistare})</button>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="text-left border-b"><th className="py-2">Ingrediente / prodotto</th><th>Quantità</th><th>Codice IRCA</th><th>Da chi</th><th>Stato</th></tr></thead>
        <tbody>{distinta.righe.map((r, i) => <tr key={`${r.ingrediente}-${i}`} className="border-b last:border-0">
          <td className="py-2"><div className="font-medium">{r.ingrediente}</div><div className="text-xs text-gray-500 max-w-xl">{r.descrizione}</div></td>
          <td>{r.quantita_min == null ? r.dosi_originali.join(" + ") : `${r.quantita_min}${r.quantita_max !== r.quantita_min ? `–${r.quantita_max}` : ""}${r.unita}`}</td>
          <td>{r.codici_irca?.join(", ") || "—"}</td>
          <td>{r.fornitore ? `${r.fornitore.nome}${r.fornitore.codice ? ` · ${r.fornitore.codice}` : ""}` : "Da scegliere"}</td>
          <td><StatoAcquisto stato={r.stato}/></td>
        </tr>)}</tbody>
      </table></div>
      <p className="text-xs text-amber-700">I prodotti già acquistati non vengono duplicati. Per i mancanti viene inserita una confezione: il numero definitivo resta da confermare quando il formato MEPA non consente una conversione certa.</p>
    </section>}
    {dettaglio && (
      <DettaglioRicetta ricetta={dettaglio} distinta={dettaglioDistinta} loading={dettaglioLoading}
        onPreferito={(preferito) => impostaPreferita(dettaglio, preferito)} preferitoBusy={preferitoBusy === dettaglio.slug}
        onPrepara={() => preparaProduzione(dettaglio)} preparando={preparando}
        onClose={() => { setDettaglio(null); setDettaglioDistinta(null); }}/>
    )}
  </div>;
}

function StatoAcquisto({ stato }) {
  if (stato === "gia_acquistato") return <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-1 text-xs font-bold text-emerald-800"><PackageCheck size={13}/> Già acquistato</span>;
  if (stato === "da_acquistare") return <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 text-xs font-bold text-amber-900"><ShoppingCart size={13}/> Da acquistare</span>;
  return <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-1 text-xs font-bold text-rose-800"><CircleAlert size={13}/> Da associare</span>;
}

function TestoPreparazione({ testo }) {
  const [procedimento, avvertenze] = String(testo || "").split(/\bAVVERTENZE\s*:/i, 2);
  return <>
    {procedimento.trim() && <p className="m-0 whitespace-pre-line text-sm leading-7 text-gray-700">{procedimento.trim()}</p>}
    {avvertenze?.trim() && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><strong className="block text-sm text-amber-900">Avvertenze</strong><p className="m-0 mt-2 whitespace-pre-line text-sm leading-7 text-amber-950">{avvertenze.trim()}</p></div>}
  </>;
}

function DettaglioRicetta({ ricetta, distinta, loading, onPreferito, preferitoBusy, onPrepara, preparando, onClose }) {
  const associazioni = new Map((distinta?.righe || []).map(r => [r.prodotto_irca_slug || r.ingrediente, r]));
  return <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/60 p-3 sm:p-6" onClick={onClose}>
    <article role="dialog" aria-modal="true" aria-label={`Ricetta ${ricetta.nome}`} className="max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-3xl bg-[#fbfaf6] shadow-2xl" onClick={e => e.stopPropagation()}>
      <header className="relative overflow-hidden rounded-t-3xl bg-[#263a31] text-white">
        {ricetta.immagine_url && <img src={ricetta.immagine_url} alt="" className="absolute inset-0 h-full w-full object-cover opacity-25"/>}
        <div className="relative flex min-h-52 items-end p-6 sm:p-8">
          <div className="mr-auto max-w-3xl"><p className="m-0 text-xs font-black uppercase tracking-[0.18em] text-[#f0ca92]">{ricetta.categoria || "Ricetta ufficiale IRCA"}</p><h3 className="m-0 mt-2 text-3xl font-black leading-tight">{ricetta.nome}</h3><p className="m-0 mt-2 text-sm text-white/80">{ricetta.livello || "Livello non indicato"}</p></div>
          <button type="button" onClick={onClose} aria-label="Chiudi ricetta" className="absolute right-4 top-4 rounded-full bg-black/25 p-2 text-white hover:bg-black/40"><X size={20}/></button>
        </div>
      </header>
      {loading ? <div className="p-12 text-center text-gray-500">Caricamento ingredienti e collegamenti MEPA…</div> : <><nav className="flex flex-wrap gap-2 border-b border-[#e6e0d5] bg-white px-5 py-3 sm:px-8" aria-label="Sezioni della ricetta">{(ricetta.fasi || []).map((fase, index) => <a key={index} href={`#irca-fase-${index}`} className="rounded-full bg-[#eef5f1] px-3 py-1.5 text-xs font-black text-[#3f5a4e]">{index + 1}. {fase.nome || `Fase ${index + 1}`}</a>)}</nav><div className="grid gap-6 p-5 sm:p-8 lg:grid-cols-[1fr_330px]">
        <div className="space-y-6">
          {(ricetta.fasi || []).map((fase, index) => { const finale = /composizione\s+finale|finitura/i.test(fase.nome || ""); return <section id={`irca-fase-${index}`} key={`${fase.nome}-${index}`} className={`scroll-mt-4 rounded-2xl border p-5 ${finale ? "border-amber-300 bg-amber-50/40" : "border-[#e6e0d5] bg-white"}`}>
            <div className="mb-4 flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#eaf3ee] text-sm font-black text-[#3f5a4e]">{index + 1}</span><h4 className="m-0 text-lg font-black text-[#263a31]">{fase.nome || `Fase ${index + 1}`}</h4></div>
            {!!fase.ingredienti?.length && <div className="mb-4 divide-y divide-gray-100 rounded-xl border border-gray-100">{fase.ingredienti.map((ingrediente, i) => {
              const slug = ingrediente.prodotto_irca_url?.split("/").filter(Boolean).pop() || ingrediente.nome;
              const link = associazioni.get(slug);
              return <div key={`${ingrediente.nome}-${i}`} className="flex flex-wrap items-center gap-2 px-3 py-2.5 text-sm"><strong className="mr-auto text-gray-800">{ingrediente.nome}</strong><span className="font-mono text-gray-600">{ingrediente.dose || "—"}</span>{ingrediente.prodotto_irca_url && link && <StatoAcquisto stato={link.stato}/>}</div>;
            })}</div>}
            {fase.preparazione && <TestoPreparazione testo={fase.preparazione}/>}</section>; })}
          {!ricetta.fasi?.length && <section className="rounded-2xl border border-[#e6e0d5] bg-white p-5"><h4 className="mt-0 text-lg font-black">Ingredienti</h4>{(ricetta.ingredienti || []).map((i, n) => <div key={n} className="flex justify-between border-b py-2 text-sm"><span>{i.nome}</span><strong>{i.dose}</strong></div>)}</section>}
        </div>
        <aside className="space-y-4">
          <section className="rounded-2xl border border-[#d6e5dc] bg-[#eef5f1] p-4"><h4 className="m-0 flex items-center gap-2 font-black text-[#263a31]"><PackageCheck size={18}/> Prodotti richiesti e stato ordine</h4><div className="mt-3 space-y-3">{(distinta?.righe || []).filter(r => r.prodotto_irca_slug).map((r, i) => <div key={`${r.ingrediente}-${i}`} className="rounded-xl bg-white p-3 shadow-sm"><strong className="block text-sm text-gray-800">{r.ingrediente}</strong><span className="mt-0.5 block text-xs text-gray-500">{r.fornitore ? `${r.fornitore.prodotto_nome || "Prodotto MEPA"}${r.fornitore.codice ? ` · ${r.fornitore.codice}` : ""}` : r.motivo}</span><span className="mt-2 inline-block"><StatoAcquisto stato={r.stato}/></span></div>)}{!distinta?.righe?.some(r => r.prodotto_irca_slug) && <p className="m-0 text-sm text-gray-600">Nessun prodotto IRCA associabile automaticamente.</p>}</div></section>
          <button type="button" onClick={() => onPreferito(!ricetta.preferito)} disabled={preferitoBusy}
            className={`flex w-full items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-black ${ricetta.preferito ? "border-amber-300 bg-amber-50 text-amber-800" : "border-[#d8d2c7] bg-white text-[#3f5a4e]"}`}>
            <Star size={17} fill={ricetta.preferito ? "currentColor" : "none"}/> {ricetta.preferito ? "Preferita · in alto nel ricettario" : "Aggiungi ai preferiti"}
          </button>
          <button type="button" onClick={onPrepara} disabled={preparando || loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-amber-600 px-4 py-3 text-sm font-black text-white disabled:opacity-50">
            <ShoppingCart size={17}/> {preparando ? "Controllo prodotti…" : "Produci questa ricetta · aggiungi solo mancanti"}
          </button>
          <a href={ricetta.url} target="_blank" rel="noreferrer" className="flex w-full items-center justify-center gap-2 rounded-xl border border-[#d8d2c7] bg-white px-4 py-3 text-sm font-bold text-[#3f5a4e]"><ExternalLink size={16}/> Vedi fonte ufficiale IRCA</a>
          <p className="rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-900">Il gestionale esclude i prodotti già acquistati. I mancanti vengono aggiunti all’ordine; se il collegamento IRCA–MEPA non è univoco, entrano come “Da associare” senza inventare fornitore, codice o prezzo.</p>
        </aside>
      </div></>}
    </article>
  </div>;
}
