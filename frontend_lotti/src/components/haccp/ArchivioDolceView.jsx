import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { BookOpen, ChefHat, ExternalLink, Search, X } from "lucide-react";
import { API } from "../../utils/constants";

const pulisciTipo = (value) => String(value || "Ricetta").replace(/^[^A-Za-zÀ-ÿ]+\s*/, "");

function testoIngredienti(value) {
  return String(value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
}

function Dettaglio({ item, allItems, onClose, onApriOperativa, onOpen }) {
  const collegate = item.kind === "recipe"
    ? allItems.filter(x => x.kind === "component" && x.parentRecipe === item.name && x.source === item.source)
    : [];
  return (
    <div className="fixed inset-0 z-[150] flex items-end justify-center bg-black/55 p-2 md:items-center md:p-6" onClick={onClose}>
      <article className="max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-t-[28px] bg-[#fffdf8] shadow-2xl md:rounded-[28px]" onClick={e => e.stopPropagation()}>
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[#ded4c7] bg-[#fffdf8]/95 px-5 py-4 backdrop-blur md:px-8">
          <div>
            <p className="m-0 text-xs font-black uppercase tracking-[.16em] text-[#5b7a6b]">{item.source || "Fonte non indicata"}</p>
            <h2 className="m-0 mt-1 font-serif text-2xl font-bold text-stone-900 md:text-4xl">{item.name}</h2>
            <p className="m-0 mt-1 text-sm font-semibold text-stone-500">{pulisciTipo(item.type)} · {item.kind === "component" ? "Preparazione base" : `Ricetta n. ${item.number}`}</p>
          </div>
          <button onClick={onClose} className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-stone-200 bg-white text-stone-600"><X size={18} /></button>
        </header>
        <div className="grid gap-7 p-5 md:grid-cols-[.9fr_1.1fr] md:p-8">
          <section>
            <h3 className="mb-3 font-serif text-xl font-bold text-stone-900">Ingredienti</h3>
            {testoIngredienti(item.ingredients).length ? (
              <ul className="m-0 space-y-2 rounded-2xl border border-[#e7ddd0] bg-white p-4 text-sm text-stone-700">
                {testoIngredienti(item.ingredients).map((riga, i) => <li key={i} className="border-b border-stone-100 pb-2 last:border-0 last:pb-0">{riga}</li>)}
              </ul>
            ) : <p className="rounded-2xl bg-stone-100 p-4 text-sm text-stone-500">Ingredienti non indicati nella fonte.</p>}
            {collegate.length > 0 && <div className="mt-5"><h3 className="mb-2 font-serif text-lg font-bold">Preparazioni collegate</h3><div className="flex flex-wrap gap-2">{collegate.map(c => <button key={c.id} onClick={() => onOpen(c)} className="rounded-full border border-[#b9cec1] bg-[#edf4ef] px-3 py-2 text-xs font-black text-[#3f5a4e]">{c.name}</button>)}</div></div>}
          </section>
          <section className="space-y-6">
            <div><h3 className="mb-3 font-serif text-xl font-bold text-stone-900">Modo di preparazione</h3><p className="m-0 whitespace-pre-line rounded-2xl border border-[#e7ddd0] bg-white p-5 text-[15px] leading-7 text-stone-700">{item.procedure || "Procedimento non indicato nella fonte."}</p></div>
            {item.notes && <div><h3 className="mb-2 font-serif text-lg font-bold">Note</h3><p className="m-0 whitespace-pre-line rounded-2xl bg-[#f2eee6] p-4 text-sm leading-6 text-stone-700">{item.notes}</p></div>}
            <div className="rounded-2xl border border-dashed border-[#b9a994] p-4 text-xs leading-5 text-stone-500">
              <strong className="text-stone-700">Provenienza:</strong> {item.provenance?.sheet || "—"}, riga {item.provenance?.row || "—"}<br />
              {item.provenance?.sourceSheet && <>Foglio fonte: {item.provenance.sourceSheet}, riga {item.provenance.sourceRow || "—"}<br /></>}
              Archivio: Ricettario_Completo_v6.xlsx
            </div>
            {item.ricetta_operativa && <button onClick={() => onApriOperativa(item.ricetta_operativa.id)} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#5b7a6b] px-5 py-3 font-black text-white shadow-sm"><ChefHat size={18} /> Apri la ricetta Ceraldi operativa <ExternalLink size={15} /></button>}
          </section>
        </div>
      </article>
    </div>
  );
}

export default function ArchivioDolceView({ onClose, onApriOperativa }) {
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");
  const [fonte, setFonte] = useState("tutte");
  const [tipo, setTipo] = useState("recipe");
  const [selected, setSelected] = useState(null);

  useEffect(() => { axios.get(`${API}/ricette-archivio`).then(r => setData(r.data)).catch(() => setData({ error: true, recipes: [], components: [] })); }, []);
  const items = useMemo(() => [...(data?.recipes || []), ...(data?.components || [])], [data]);
  const fonti = useMemo(() => [...new Set(items.map(x => x.source).filter(Boolean))].sort((a, b) => a.localeCompare(b, "it")), [items]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter(x => (tipo === "all" || x.kind === tipo) && (fonte === "tutte" || x.source === fonte) && (!q || [x.name, x.ingredients, x.procedure, x.notes, x.components].join(" ").toLowerCase().includes(q)));
  }, [items, query, fonte, tipo]);

  if (!data) return <div className="py-16 text-center font-bold text-stone-400">Carico l'archivio professionale…</div>;
  return <div>
    <div className="mb-5 rounded-[26px] border border-[#cfded4] bg-gradient-to-br from-[#e8efe9] to-[#faf7ef] p-5 md:p-7">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between"><div><p className="m-0 text-xs font-black uppercase tracking-[.18em] text-[#5b7a6b]">Archivio professionale verificato</p><h2 className="m-0 mt-1 font-serif text-3xl font-bold text-stone-900">Modi di preparazione e ricette tecniche</h2><p className="m-0 mt-2 max-w-3xl text-sm font-semibold text-stone-600">{data.meta?.recipeCount || 0} ricette e {data.meta?.componentCount || 0} preparazioni base. Le ricette Ceraldi restano distinte: {data.collegate || 0} collegamenti trovati senza duplicare dati.</p></div><button onClick={onClose} className="rounded-xl border border-stone-300 bg-white px-4 py-2 text-sm font-black text-stone-700">Torna alle ricette operative</button></div>
    </div>
    <div className="mb-5 grid gap-3 md:grid-cols-[1fr_auto_auto]">
      <label className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" size={17} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Cerca nome, ingrediente o procedimento…" className="w-full rounded-xl border border-stone-200 bg-white py-3 pl-10 pr-3 text-sm font-semibold outline-none focus:ring-2 focus:ring-[#cfded4]" /></label>
      <select value={fonte} onChange={e => setFonte(e.target.value)} className="rounded-xl border border-stone-200 bg-white px-3 py-3 text-sm font-bold"><option value="tutte">Tutte le fonti</option>{fonti.map(f => <option key={f}>{f}</option>)}</select>
      <div className="flex rounded-xl border border-stone-200 bg-white p-1">{[["recipe", "Ricette"], ["component", "Basi"], ["all", "Tutto"]].map(([v, l]) => <button key={v} onClick={() => setTipo(v)} className={`rounded-lg px-3 py-2 text-xs font-black ${tipo === v ? "bg-[#5b7a6b] text-white" : "text-stone-600"}`}>{l}</button>)}</div>
    </div>
    <p className="mb-3 text-xs font-black uppercase tracking-wider text-stone-500">{filtered.length} risultati</p>
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{filtered.map(item => <button key={`${item.kind}-${item.id}`} onClick={() => setSelected(item)} className="group min-h-44 rounded-2xl border border-[#e2d8ca] bg-[#fffdf8] p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-[#9cb7a7] hover:shadow-md"><div className="flex items-start justify-between gap-3"><span className="text-[10px] font-black uppercase tracking-widest text-[#5b7a6b]">{item.source}</span>{item.ricetta_operativa && <span className="rounded-full bg-[#e2f2e8] px-2 py-1 text-[10px] font-black text-[#347052]">Ceraldi</span>}</div><h3 className="my-3 font-serif text-xl font-bold leading-tight text-stone-900">{item.name}</h3><p className="m-0 line-clamp-3 text-xs leading-5 text-stone-500">{item.procedure || item.ingredients || "Informazioni non indicate."}</p><div className="mt-4 flex items-center gap-2 text-xs font-black text-[#5b7a6b]"><BookOpen size={15} /> Apri scheda</div></button>)}</div>
    {selected && <Dettaglio item={selected} allItems={items} onClose={() => setSelected(null)} onOpen={setSelected} onApriOperativa={onApriOperativa} />}
  </div>;
}
