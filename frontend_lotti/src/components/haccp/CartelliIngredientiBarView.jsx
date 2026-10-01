import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { CheckSquare, Printer, Search, Square, Upload } from "lucide-react";
import { toast } from "sonner";
import { fotoSrc } from "../../utils/constants";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function stampaProdotti(prodotti) {
  if (!prodotti.length) return;
  const cards = prodotti.map((p) => `
    <article class="card">
      ${p.foto_url ? `<img src="${escapeHtml(fotoSrc(p.foto_url))}" alt="">` : '<div class="no-photo">Foto non disponibile</div>'}
      <div class="body">
        <div class="code">Codice ${escapeHtml(p.codice || "—")}</div>
        <h1>${escapeHtml(p.nome)}</h1>
        <h2>Ingredienti</h2><p>${escapeHtml(p.ingredienti)}</p>
        <h2>Allergeni</h2><p class="allergeni">${escapeHtml((p.allergeni || []).join(" · ") || "Nessun allergene rilevato nella lista fornita")}</p>
      </div>
    </article>`).join("");
  const win = window.open("", "_blank");
  if (!win) { toast.error("Consenti le finestre popup per stampare i cartelli"); return; }
  win.opener = null;
  win.document.write(`<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Cartelli ingredienti bar</title><style>
    @page{size:A4;margin:10mm}*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;color:#20251f}
    .card{page-break-inside:avoid;border:2px solid #5b7a6b;border-radius:12px;overflow:hidden;margin:0 0 10mm;display:grid;grid-template-columns:42mm 1fr;min-height:58mm}
    img,.no-photo{width:42mm;height:100%;min-height:58mm;object-fit:cover;background:#eef2ef;display:flex;align-items:center;justify-content:center;text-align:center;color:#66736b;font-size:10pt;padding:4mm}
    .body{padding:6mm}.code{font-size:9pt;color:#657168}h1{font-size:17pt;margin:1mm 0 4mm}h2{font-size:10pt;text-transform:uppercase;color:#5b7a6b;margin:3mm 0 1mm}p{font-size:9.5pt;line-height:1.35;margin:0}.allergeni{font-weight:700;color:#8b3a2b}
  </style></head><body>${cards}<script>window.onload=()=>window.print()<\/script></body></html>`);
  win.document.close();
}

export default function CartelliIngredientiBarView() {
  const [prodotti, setProdotti] = useState([]);
  const [selezionati, setSelezionati] = useState(new Set());
  const [search, setSearch] = useState("");
  const [soloUsati, setSoloUsati] = useState(false);
  const [loading, setLoading] = useState(true);
  const [importando, setImportando] = useState(false);
  const fileRef = useRef(null);

  const caricaProdotti = useCallback(() => axios.get(`${API}/acquaviva/cartelli-bar`)
    .then((r) => setProdotti(r.data?.prodotti || [])), []);

  useEffect(() => {
    setLoading(true);
    caricaProdotti()
      .catch(() => toast.error("Errore nel caricamento degli ingredienti"))
      .finally(() => setLoading(false));
  }, [caricaProdotti]);

  const importaPdf = async (file) => {
    if (!file) return;
    setImportando(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await axios.post(`${API}/acquaviva/import-ingredienti-pdf`, form);
      await caricaProdotti();
      const mancanti = (r.data.non_trovati || []).length;
      const ambigui = (r.data.ambigui || []).length;
      toast.success(`${r.data.prodotti_aggiornati} prodotti aggiornati, ${r.data.ricette_aggiornate} ricette collegate${mancanti || ambigui ? `; ${mancanti} non trovati, ${ambigui} ambigui` : ""}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Importazione lista ingredienti non riuscita");
    } finally {
      setImportando(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const visibili = useMemo(() => prodotti.filter((p) => {
    if (soloUsati && !p.in_ricette) return false;
    const q = search.trim().toLocaleLowerCase("it");
    return !q || `${p.nome} ${p.codice} ${p.ingredienti}`.toLocaleLowerCase("it").includes(q);
  }), [prodotti, search, soloUsati]);
  const selezionatiProdotti = prodotti.filter((p) => selezionati.has(p.id));
  const tuttiVisibili = visibili.length > 0 && visibili.every((p) => selezionati.has(p.id));

  const toggle = (id) => setSelezionati((prima) => {
    const dopo = new Set(prima);
    dopo.has(id) ? dopo.delete(id) : dopo.add(id);
    return dopo;
  });
  const toggleTutti = () => setSelezionati((prima) => {
    const dopo = new Set(prima);
    if (tuttiVisibili) visibili.forEach((p) => dopo.delete(p.id));
    else visibili.forEach((p) => dopo.add(p.id));
    return dopo;
  });

  return <section className="space-y-4">
    <div className="rounded-2xl border border-[#cfdfd5] bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Cartelli ingredienti per il bar</h2>
          <p className="mt-1 text-sm text-gray-500">Foto, ingredienti e allergeni dalla lista ufficiale Acquaviva/Vandemoortele.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => importaPdf(e.target.files?.[0])}/>
          <button onClick={() => fileRef.current?.click()} disabled={importando}
            className="flex items-center gap-2 rounded-xl border border-[#cfdfd5] px-4 py-2 text-sm font-semibold text-[#5b7a6b] disabled:opacity-50">
            <Upload size={16}/> {importando ? "Aggiornamento…" : "Aggiorna lista PDF"}
          </button>
          <button onClick={() => stampaProdotti(selezionatiProdotti)} disabled={!selezionatiProdotti.length}
            className="flex items-center gap-2 rounded-xl bg-[#5b7a6b] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
            <Printer size={16}/> Stampa selezionati ({selezionatiProdotti.length})
          </button>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="relative min-w-[260px] flex-1"><Search size={16} className="absolute left-3 top-3 text-gray-400"/>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca prodotto, codice o ingrediente"
            className="w-full rounded-xl border border-gray-200 py-2.5 pl-9 pr-3 text-sm"/>
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700"><input type="checkbox" checked={soloUsati} onChange={(e) => setSoloUsati(e.target.checked)}/> Solo prodotti usati nel ricettario</label>
        <button onClick={toggleTutti} className="flex items-center gap-2 rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700">
          {tuttiVisibili ? <CheckSquare size={16}/> : <Square size={16}/>} {tuttiVisibili ? "Deseleziona visibili" : "Seleziona visibili"}
        </button>
      </div>
    </div>

    {loading ? <div className="py-12 text-center text-gray-500">Caricamento…</div> :
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {visibili.map((p) => <article key={p.id} className={`overflow-hidden rounded-2xl border bg-white shadow-sm ${selezionati.has(p.id) ? "border-[#5b7a6b] ring-2 ring-[#cfdfd5]" : "border-gray-200"}`}>
          <button type="button" onClick={() => toggle(p.id)} className="block w-full text-left" aria-pressed={selezionati.has(p.id)}>
            <div className="relative h-44 bg-gray-100">
              {p.foto_url ? <img src={fotoSrc(p.foto_url)} alt={p.nome} className="h-full w-full object-cover"/> : <div className="flex h-full items-center justify-center text-sm text-gray-400">Foto non disponibile</div>}
              <span className="absolute right-3 top-3 rounded-lg bg-white p-1.5 shadow">{selezionati.has(p.id) ? <CheckSquare size={20} className="text-[#5b7a6b]"/> : <Square size={20} className="text-gray-500"/>}</span>
            </div>
            <div className="p-4"><div className="text-xs text-gray-500">Codice {p.codice || "—"}{p.in_ricette ? " · Nel ricettario" : ""}</div><h3 className="mt-1 font-bold text-gray-800">{p.nome}</h3>
              <p className="mt-3 line-clamp-5 text-xs leading-5 text-gray-600">{p.ingredienti}</p>
              <div className="mt-3 flex flex-wrap gap-1">{(p.allergeni || []).map((a) => <span key={a} className="rounded-full bg-red-50 px-2 py-1 text-[11px] font-semibold text-red-700">{a}</span>)}</div>
            </div>
          </button>
          <div className="border-t border-gray-100 p-3"><button onClick={() => stampaProdotti([p])} className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#cfdfd5] py-2 text-sm font-medium text-[#5b7a6b]"><Printer size={15}/> Stampa questo cartello</button></div>
        </article>)}
      </div>}
    {!loading && !visibili.length && <div className="rounded-2xl border border-dashed border-gray-300 bg-white py-12 text-center text-gray-500">Nessun prodotto con ingredienti disponibile per questo filtro.</div>}
  </section>;
}
