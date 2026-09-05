import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Pencil, Plus, Printer, RefreshCw, Save, Search, ShoppingCart, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import ModalRevisioneDizionario from "./shared/ModalRevisioneDizionario";
import { API } from "../../utils/constants";

const repartoLabel = (r) => ({ pasticceria: "Pasticceria", rosticceria: "Rosticceria", altro: "Altro", tutti: "Tutte" }[r] || "Altro");
const reparti = ["tutti", "pasticceria", "rosticceria", "altro"];

const categorie = [
  { id: "tutte", label: "Tutte", icon: "📋" },
  { id: "panini", label: "Panini", icon: "🥪" },
  { id: "torte", label: "Torte", icon: "🎂" },
  { id: "lievitati", label: "Lievitati", icon: "🥐" },
  { id: "pasticceria", label: "Pasticceria", icon: "🍰" },
  { id: "rosticceria", label: "Rosticceria", icon: "🍕" },
];

function getCategoria(r) {
  const nome = String(r?.nome || "").toLowerCase();
  const cat = String(r?.categoria || "").toLowerCase();
  const reparto = String(r?.reparto || "").toLowerCase();
  if (cat.includes("panin") || nome.includes("panino") || nome.includes("panuozzo")) return "panini";
  if (cat.includes("tort") || nome.includes("torta") || nome.includes("crostata")) return "torte";
  if (cat.includes("lievit") || nome.includes("cornetto") || nome.includes("brioche") || nome.includes("babà") || nome.includes("baba")) return "lievitati";
  if (reparto === "pasticceria") return "pasticceria";
  if (reparto === "rosticceria") return "rosticceria";
  return "altro";
}

function iconFor(r) {
  const c = getCategoria(r);
  if (c === "panini") return "🥪";
  if (c === "torte") return "🎂";
  if (c === "lievitati") return "🥐";
  if (c === "rosticceria") return "🍕";
  if (c === "pasticceria") return "🍰";
  return "📋";
}

function photoUrl(r) {
  const url = r?.foto_url || r?.immagine_url || r?.image_url || "";
  if (!url) return "";
  if (url.startsWith("http")) return url;
  if (url.startsWith("/images") || url.startsWith("/saima")) return url;
  // Qualunque altro path relativo (/api/foto/<id>, /uploads/...) vive sul backend
  if (url.startsWith("/")) return `${process.env.REACT_APP_LOTTI_BACKEND_URL || ""}${url}`;
  return "";
}

function money(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n.toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function MainCard({ icon, title, text, tone = "violet", onClick, badge }) {
  const tones = {
    violet: "bg-[#f2f6f3] border-[#cfdfd5] text-[#3f5a4e]",
    amber: "bg-amber-50 border-amber-200 text-amber-900",
    green: "bg-emerald-50 border-emerald-200 text-emerald-900",
    blue: "bg-amber-50 border-amber-200 text-amber-900",
    red: "bg-red-50 border-red-200 text-red-900",
  };
  return (
    <button onClick={onClick} className={`rounded-[28px] border p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md active:scale-[.99] ${tones[tone]}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="grid h-14 w-14 place-items-center rounded-3xl border border-white/70 bg-white/75 text-3xl shadow-sm">{icon}</div>
        {badge !== undefined && badge !== null && badge !== "" ? <span className="rounded-full bg-white/80 px-3 py-1 text-xs font-black shadow-sm">{badge}</span> : null}
      </div>
      <h3 className="mt-4 text-lg font-black text-stone-900">{title}</h3>
      <p className="mt-1 text-sm font-semibold leading-snug text-stone-500">{text}</p>
    </button>
  );
}

function CategoryStrip({ active, setActive, counts }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {categorie.map(c => {
        const selected = active === c.id;
        return (
          <button key={c.id} onClick={() => setActive(c.id)} className={`rounded-3xl border p-4 text-left shadow-sm transition active:scale-[.99] ${selected ? "border-[#b8d0c2] bg-[#e8efe9]" : "border-stone-200 bg-white hover:border-stone-300"}`}>
            <div className="flex items-start justify-between gap-2">
              <span className="text-3xl">{c.icon}</span>
              <span className="rounded-full bg-white/80 px-2 py-0.5 text-xs font-black text-stone-600">{counts[c.id] || 0}</span>
            </div>
            <div className="mt-3 text-sm font-black text-stone-900">{c.label}</div>
          </button>
        );
      })}
    </div>
  );
}

function RecipeCard({ r, onOpen, onClone, onScheda, onCompila, onVerifica }) {
  const ing = r.ingredienti_dettaglio?.length || r.ingredienti?.length || 0;
  const allergeni = r.allergeni?.length || r.allergeni_auto?.length || 0;
  const reparto = r.reparto || "altro";
  const costo = money(r.costo_porzione || r.costo_unitario || r.food_cost || r.costo_totale);
  const img = photoUrl(r);
  return (
    <div className="overflow-hidden rounded-[26px] border border-stone-200 bg-white shadow-sm transition hover:shadow-md">
      <div className="relative h-28 bg-gradient-to-br from-[#f2f6f3] to-stone-100">
        {img ? <img src={img} alt={r.nome} className="h-full w-full object-cover" /> : <div className="grid h-full w-full place-items-center text-5xl">{iconFor(r)}</div>}
        <span className="absolute left-3 top-3 rounded-full bg-white/90 px-3 py-1 text-xs font-black text-stone-700 shadow-sm">{repartoLabel(reparto)}</span>
        {costo ? <span className="absolute right-3 top-3 rounded-full bg-emerald-600 px-3 py-1 text-xs font-black text-white shadow-sm">{costo}</span> : null}
      </div>
      <div className="p-4">
        <h4 className="m-0 truncate text-base font-black text-stone-900">{r.nome}</h4>
        <p className="m-0 mt-1 text-xs font-bold uppercase tracking-wide text-stone-400">{ing} ingredienti · {allergeni} allergeni</p>
        {r.fonte_archivio?.toLowerCase().includes("saima") && <p className="m-0 mt-1 text-[10px] font-black uppercase tracking-wide text-[#5b7a6b]">Ricettario SAIMA · pagina {r.pagina_fonte || "—"}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => onVerifica(r)} className="flex items-center gap-1 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-black text-white"><CheckCircle2 size={12} /> Posso produrla?</button>
          <button onClick={() => onOpen(r, "allergeni")} className="rounded-full bg-amber-100 px-3 py-1.5 text-xs font-black text-amber-800">Allergeni</button>
          <button onClick={() => onOpen(r, "ingredienti")} className="rounded-full bg-amber-100 px-3 py-1.5 text-xs font-black text-amber-800">Ingredienti</button>
          <button onClick={() => onClone(r)} className="rounded-full bg-[#e8efe9] px-3 py-1.5 text-xs font-black text-[#3f5a4e]">Clona</button>
          <button onClick={() => onCompila(r)} className="flex items-center gap-1 rounded-full bg-stone-100 px-3 py-1.5 text-xs font-black text-stone-700"><Pencil size={12} /> Compila</button>
          <button onClick={() => onScheda(r)} className="rounded-full bg-emerald-100 px-3 py-1.5 text-xs font-black text-emerald-800">Stampa scheda</button>
        </div>
      </div>
    </div>
  );
}

export function VerificaDisponibilitaModal({ ricetta, onClose, onRicetteUpdate }) {
  const resaSalvata = Number(ricetta.porzioni || ricetta.pezzi_ricetta_base || 0);
  const [pezzi, setPezzi] = useState(resaSalvata > 0 ? resaSalvata : "");
  const [esito, setEsito] = useState(null);
  const [loading, setLoading] = useState(false);
  const [aggiungendo, setAggiungendo] = useState(false);

  const verifica = async () => {
    const n = Number(pezzi);
    if (!Number.isFinite(n) || n <= 0) {
      toast.error("Indica quanti pezzi vuoi ottenere");
      return;
    }
    setLoading(true);
    try {
      if (resaSalvata <= 0) {
        await axios.post(`${API}/food-cost/salva-porzioni-ricetta`, null, { params: { ricetta_id: ricetta.id, porzioni_base: Math.round(n) } });
        toast.success(`Resa base salvata: ${Math.round(n)} pezzi`);
        onRicetteUpdate?.();
      }
      const response = await axios.post(`${API}/saima/ricettari/ricette/${encodeURIComponent(ricetta.id)}/verifica-disponibilita`, { pezzi: n });
      setEsito(response.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Verifica non disponibile");
    } finally {
      setLoading(false);
    }
  };

  const aggiungiMancanti = async () => {
    setAggiungendo(true);
    try {
      const response = await axios.post(`${API}/saima/ricettari/ricette/${encodeURIComponent(ricetta.id)}/aggiungi-mancanti-carrello`, { pezzi: Number(pezzi) });
      toast.success(response.data.aggiunti ? `${response.data.aggiunti} ingredienti aggiunti al carrello` : "Gli ingredienti erano già nel carrello");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Non riesco ad aggiornare il carrello");
    } finally {
      setAggiungendo(false);
    }
  };

  const statusStyle = {
    disponibile: "border-emerald-200 bg-emerald-50",
    sostituibile: "border-amber-200 bg-amber-50",
    da_acquistare: "border-rose-200 bg-rose-50",
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-stone-900/60 p-2 sm:items-center sm:p-4" onClick={onClose}>
      <div className="max-h-[94vh] w-full max-w-3xl overflow-y-auto rounded-t-[28px] bg-[#fffdf8] shadow-2xl sm:rounded-[28px]" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-stone-200 bg-[#fffdf8]/95 p-5 backdrop-blur">
          <div><p className="m-0 text-xs font-black uppercase tracking-wider text-[#5b7a6b]">Verifica fatture e magazzino</p><h3 className="m-0 mt-1 text-2xl font-black text-stone-900">{ricetta.nome}</h3></div>
          <button onClick={onClose} className="grid h-10 w-10 place-items-center rounded-full bg-stone-100"><X size={18} /></button>
        </div>
        <div className="space-y-4 p-5">
          <div className="rounded-2xl border border-[#cfdfd5] bg-white p-4">
            <label className="block text-sm font-black text-stone-800">Quanti pezzi vuoi produrre?</label>
            <p className="mb-3 mt-1 text-xs font-semibold text-stone-500">{resaSalvata > 0 ? `La ricetta base produce ${resaSalvata} pezzi; le dosi saranno scalate.` : "Prima volta: questo numero verrà salvato come resa dell'impasto base."}</p>
            <div className="flex gap-2"><input inputMode="numeric" type="number" min="1" step="1" value={pezzi} onChange={e => setPezzi(e.target.value)} className="min-h-12 flex-1 rounded-2xl border border-stone-200 px-4 text-xl font-black outline-none focus:ring-2 focus:ring-[#b8d0c2]" placeholder="es. 40" /><button onClick={verifica} disabled={loading} className="min-h-12 rounded-2xl bg-[#5b7a6b] px-5 font-black text-white disabled:opacity-50">{loading ? "Controllo…" : "Controlla"}</button></div>
          </div>

          {esito && <>
            <div className={`rounded-2xl border p-4 ${esito.realizzabile_subito ? "border-emerald-300 bg-emerald-50" : esito.realizzabile_con_sostituzioni ? "border-amber-300 bg-amber-50" : "border-rose-300 bg-rose-50"}`}>
              <h4 className="m-0 text-lg font-black">{esito.realizzabile_subito ? "Realizzabile subito" : esito.realizzabile_con_sostituzioni ? "Realizzabile confermando le alternative" : "Mancano alcuni ingredienti"}</h4>
              <p className="m-0 mt-1 text-sm font-semibold text-stone-600">Disponibili {esito.totali.disponibili} · alternative {esito.totali.sostituibili} · da acquistare {esito.totali.da_acquistare}</p>
            </div>
            <div className="space-y-2">
              {esito.righe.map((row, idx) => <div key={`${row.ingrediente}-${idx}`} className={`rounded-2xl border p-4 ${statusStyle[row.stato]}`}>
                <div className="flex items-start justify-between gap-3"><div><strong className="block text-sm text-stone-900">{row.ingrediente}</strong><span className="text-xs font-semibold text-stone-500">Richiesta: {row.richiesta.valore || "q.b."} {row.richiesta.unita}</span></div><span className="rounded-full bg-white/80 px-2 py-1 text-[10px] font-black uppercase">{row.stato === "disponibile" ? "Disponibile" : row.stato === "sostituibile" ? "Alternativa" : "Da acquistare"}</span></div>
                {row.prodotto && <p className="mb-0 mt-2 text-xs font-bold text-emerald-800">Abbiamo: {row.prodotto.nome}{row.prodotto.fornitore ? ` · ${row.prodotto.fornitore}` : ""}</p>}
                {row.motivo && <p className="mb-0 mt-1 text-xs font-bold text-rose-700">{row.motivo}{row.mancante ? ` Da acquistare: ${row.mancante.valore} ${row.mancante.unita}.` : ""}</p>}
                {row.alternative?.length > 0 && <div className="mt-3 rounded-xl bg-white/75 p-3"><p className="m-0 mb-2 text-xs font-black text-amber-900">Possibili sostituti da confermare:</p>{row.alternative.map(alt => <p key={alt.id || alt.nome} className="m-0 border-b border-amber-100 py-1 text-xs font-semibold last:border-0">{alt.nome} · disponibile {alt.quantita_disponibile} {alt.unita}<span className="block font-normal text-stone-500">{alt.motivo}</span></p>)}</div>}
              </div>)}
            </div>
            {esito.totali.da_acquistare > 0 && <button onClick={aggiungiMancanti} disabled={aggiungendo} className="flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-rose-600 px-4 font-black text-white disabled:opacity-50"><ShoppingCart size={17} /> {aggiungendo ? "Aggiungo…" : "Aggiungi solo i mancanti al carrello"}</button>}
            <p className="rounded-2xl bg-stone-100 p-3 text-xs font-semibold text-stone-500"><AlertTriangle className="mr-1 inline" size={14} /> Le alternative non modificano la ricetta e non vengono usate automaticamente: il pasticciere deve confermare compatibilità, gusto e resa.</p>
          </>}
        </div>
      </div>
    </div>
  );
}

function SchedaModal({ ricetta, onClose }) {
  const [html, setHtml] = useState("");
  const [stato, setStato] = useState("loading"); // loading | ok | errore
  const iframeRef = useRef(null);

  useEffect(() => {
    let vivo = true;
    setStato("loading");
    axios.get(`${API}/ricette/${ricetta.id}/pdf-scheda`, { responseType: "text" })
      .then((res) => {
        if (!vivo) return;
        setHtml(typeof res.data === "string" ? res.data : "");
        setStato("ok");
      })
      .catch(() => {
        if (!vivo) return;
        setStato("errore");
        toast.error("Scheda non disponibile");
      });
    return () => { vivo = false; };
  }, [ricetta.id]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const stampa = () => {
    const w = iframeRef.current?.contentWindow;
    if (!w) return;
    w.focus();
    w.print();
  };

  return (
    <div onClick={onClose} className="fixed inset-0 z-[60] flex items-center justify-center bg-stone-900/60 p-2 sm:p-4">
      <div onClick={(e) => e.stopPropagation()} className="flex h-full max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-stone-200 px-4 py-3">
          <h3 className="m-0 truncate text-base font-black text-stone-900">{ricetta.nome}</h3>
          <div className="flex shrink-0 items-center gap-2">
            <button onClick={stampa} disabled={stato !== "ok"} className="flex items-center gap-1.5 rounded-full bg-emerald-600 px-4 py-2 text-xs font-black text-white shadow-sm disabled:opacity-40"><Printer size={15} /> Stampa</button>
            <button onClick={onClose} aria-label="Chiudi" className="grid h-9 w-9 place-items-center rounded-full bg-stone-100 text-stone-600 hover:bg-stone-200"><X size={18} /></button>
          </div>
        </div>
        <div className="relative flex-1 bg-stone-50">
          {stato === "loading" && <div className="grid h-full place-items-center text-stone-400"><span className="flex items-center gap-2 text-sm font-bold"><RefreshCw className="animate-spin" size={16} /> Carico la scheda...</span></div>}
          {stato === "errore" && <div className="grid h-full place-items-center px-6 text-center text-sm font-bold text-stone-500">Scheda non disponibile. Riprova.</div>}
          {stato === "ok" && <iframe ref={iframeRef} title={`Scheda ${ricetta.nome}`} srcDoc={html} className="h-full w-full border-0 bg-white" />}
        </div>
      </div>
    </div>
  );
}

function _passi(arr) {
  if (!Array.isArray(arr)) return [];
  return arr.map((p) => typeof p === "string" ? { titolo: "", testo: p } : { titolo: p?.titolo || "", testo: p?.testo || p?.descrizione || "" });
}
function _stringhe(arr) {
  return Array.isArray(arr) ? arr.map((c) => String(c ?? "")) : [];
}
function _coppie(arr, ka, kb, kaAlt, kbAlt) {
  if (!Array.isArray(arr)) return [];
  return arr.map((it) => typeof it === "string" ? { [ka]: it, [kb]: "" } : { [ka]: it?.[ka] ?? it?.[kaAlt] ?? "", [kb]: it?.[kb] ?? it?.[kbAlt] ?? "" });
}

function Campo({ label, children }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-black uppercase tracking-wide text-stone-500">{label}</label>
      {children}
    </div>
  );
}

export function SchedaEditorModal({ ricetta, onClose, onSaved, onAnteprima }) {
  const [occhiello, setOcchiello] = useState(ricetta.occhiello || "");
  const [procedimento, setProcedimento] = useState(() => _passi(ricetta.procedimento));
  const [critico, setCritico] = useState(ricetta.dettaglio_critico || "");
  const [consigli, setConsigli] = useState(() => _stringhe(ricetta.consigli));
  const [errore, setErrore] = useState(ricetta.errore_da_evitare || "");
  const [kcal, setKcal] = useState(ricetta?.nutrizione?.kcal ?? "");
  const [impiattamento, setImpiattamento] = useState(() => _coppie(ricetta.impiattamento, "elemento", "nota", "nome", "descrizione"));
  const [varianti, setVarianti] = useState(() => _coppie(ricetta.varianti, "nome", "descrizione", "nome", "desc"));
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const inputCls = "w-full rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm font-semibold outline-none focus:ring-2 focus:ring-[#dce8e0]";
  const addBtn = "flex items-center gap-1.5 rounded-full bg-[#e8efe9] px-3 py-1.5 text-xs font-black text-[#3f5a4e]";
  const delBtn = "grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-rose-50 text-rose-600";

  const salva = async (apriAnteprima = false) => {
    setSalvando(true);
    try {
      const payload = {
        occhiello: occhiello.trim(),
        procedimento: procedimento.map((p) => ({ titolo: (p.titolo || "").trim(), testo: (p.testo || "").trim() })).filter((p) => p.titolo || p.testo),
        dettaglio_critico: critico.trim(),
        consigli: consigli.map((c) => c.trim()).filter(Boolean),
        errore_da_evitare: errore.trim(),
        nutrizione: kcal !== "" && Number.isFinite(Number(kcal)) ? { kcal: Number(kcal) } : {},
        impiattamento: impiattamento.map((i) => ({ elemento: (i.elemento || "").trim(), nota: (i.nota || "").trim() })).filter((i) => i.elemento || i.nota),
        varianti: varianti.map((v) => ({ nome: (v.nome || "").trim(), descrizione: (v.descrizione || "").trim() })).filter((v) => v.nome || v.descrizione),
      };
      await axios.put(`${API}/ricette/${ricetta.id}/scheda`, payload);
      toast.success("Scheda salvata");
      onSaved && onSaved();
      if (apriAnteprima && onAnteprima) onAnteprima(ricetta);
      else onClose();
    } catch {
      toast.error("Salvataggio non riuscito");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div onClick={onClose} className="fixed inset-0 z-[60] flex items-center justify-center bg-stone-900/60 p-2 sm:p-4">
      <div onClick={(e) => e.stopPropagation()} className="flex h-full max-h-[94vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-stone-200 px-4 py-3">
          <div className="min-w-0"><h3 className="m-0 truncate text-base font-black text-stone-900">Compila scheda</h3><p className="m-0 truncate text-xs font-bold text-stone-400">{ricetta.nome}</p></div>
          <button onClick={onClose} aria-label="Chiudi" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-stone-100 text-stone-600 hover:bg-stone-200"><X size={18} /></button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
          <Campo label="Occhiello (sottotitolo)">
            <input value={occhiello} onChange={(e) => setOcchiello(e.target.value)} placeholder="es. Il classico napoletano, a modo nostro" className={inputCls} />
          </Campo>

          <Campo label="Procedimento (passi)">
            <div className="space-y-2">
              {procedimento.map((p, i) => (
                <div key={i} className="rounded-xl border border-stone-200 bg-stone-50 p-2">
                  <div className="flex items-center gap-2">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#e8efe9] text-xs font-black text-[#3f5a4e]">{i + 1}</span>
                    <input value={p.titolo} onChange={(e) => setProcedimento(procedimento.map((x, j) => j === i ? { ...x, titolo: e.target.value } : x))} placeholder="Titolo passo" className={inputCls} />
                    <button onClick={() => setProcedimento(procedimento.filter((_, j) => j !== i))} className={delBtn}><Trash2 size={15} /></button>
                  </div>
                  <textarea value={p.testo} onChange={(e) => setProcedimento(procedimento.map((x, j) => j === i ? { ...x, testo: e.target.value } : x))} placeholder="Descrizione del passo" rows={2} className={`mt-2 ${inputCls}`} />
                </div>
              ))}
              <button onClick={() => setProcedimento([...procedimento, { titolo: "", testo: "" }])} className={addBtn}><Plus size={14} /> Aggiungi passo</button>
            </div>
          </Campo>

          <Campo label="Dettaglio critico (il punto da non sbagliare)">
            <textarea value={critico} onChange={(e) => setCritico(e.target.value)} rows={2} placeholder="es. La crema non deve bollire dopo i tuorli" className={inputCls} />
          </Campo>

          <Campo label="Consigli">
            <div className="space-y-2">
              {consigli.map((c, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input value={c} onChange={(e) => setConsigli(consigli.map((x, j) => j === i ? e.target.value : x))} placeholder="Un consiglio" className={inputCls} />
                  <button onClick={() => setConsigli(consigli.filter((_, j) => j !== i))} className={delBtn}><Trash2 size={15} /></button>
                </div>
              ))}
              <button onClick={() => setConsigli([...consigli, ""])} className={addBtn}><Plus size={14} /> Aggiungi consiglio</button>
            </div>
          </Campo>

          <Campo label="Errore da evitare">
            <textarea value={errore} onChange={(e) => setErrore(e.target.value)} rows={2} placeholder="es. Non versare lo zucchero tutto insieme" className={inputCls} />
          </Campo>

          <Campo label="Calorie (kcal / porzione)">
            <input type="number" inputMode="numeric" value={kcal} onChange={(e) => setKcal(e.target.value)} placeholder="es. 220" className={inputCls} />
          </Campo>

          <Campo label="Impiattamento">
            <div className="space-y-2">
              {impiattamento.map((it, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input value={it.elemento} onChange={(e) => setImpiattamento(impiattamento.map((x, j) => j === i ? { ...x, elemento: e.target.value } : x))} placeholder="Elemento" className={`${inputCls} max-w-[42%]`} />
                  <input value={it.nota} onChange={(e) => setImpiattamento(impiattamento.map((x, j) => j === i ? { ...x, nota: e.target.value } : x))} placeholder="Nota" className={inputCls} />
                  <button onClick={() => setImpiattamento(impiattamento.filter((_, j) => j !== i))} className={delBtn}><Trash2 size={15} /></button>
                </div>
              ))}
              <button onClick={() => setImpiattamento([...impiattamento, { elemento: "", nota: "" }])} className={addBtn}><Plus size={14} /> Aggiungi voce</button>
            </div>
          </Campo>

          <Campo label="Varianti">
            <div className="space-y-2">
              {varianti.map((v, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input value={v.nome} onChange={(e) => setVarianti(varianti.map((x, j) => j === i ? { ...x, nome: e.target.value } : x))} placeholder="Nome" className={`${inputCls} max-w-[42%]`} />
                  <input value={v.descrizione} onChange={(e) => setVarianti(varianti.map((x, j) => j === i ? { ...x, descrizione: e.target.value } : x))} placeholder="Descrizione" className={inputCls} />
                  <button onClick={() => setVarianti(varianti.filter((_, j) => j !== i))} className={delBtn}><Trash2 size={15} /></button>
                </div>
              ))}
              <button onClick={() => setVarianti([...varianti, { nome: "", descrizione: "" }])} className={addBtn}><Plus size={14} /> Aggiungi variante</button>
            </div>
          </Campo>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-stone-200 px-4 py-3">
          <button onClick={onClose} className="rounded-full bg-stone-100 px-4 py-2 text-sm font-black text-stone-600">Annulla</button>
          <button onClick={() => salva(true)} disabled={salvando} className="flex items-center gap-1.5 rounded-full bg-emerald-100 px-4 py-2 text-sm font-black text-emerald-800 disabled:opacity-50"><Printer size={15} /> Salva e vedi</button>
          <button onClick={() => salva(false)} disabled={salvando} className="flex items-center gap-1.5 rounded-full bg-[#5b7a6b] px-5 py-2 text-sm font-black text-white shadow-sm disabled:opacity-50"><Save size={16} /> {salvando ? "Salvo..." : "Salva"}</button>
        </div>
      </div>
    </div>
  );
}

export default function RicetteDashboardView({ ricette = [], loadingRicette = false, searchRicette, setSearchRicette, onRicetteUpdate, onOpenRicetta, onCloneRicetta, onNuovaRicetta }) {
  const [filtro, setFiltro] = useState("tutti");
  const [categoria, setCategoria] = useState("tutte");
  const [revisione, setRevisione] = useState(false);
  const [scheda, setScheda] = useState(null);
  const [verificaRicetta, setVerificaRicetta] = useState(null);
  const [editor, setEditor] = useState(null);
  const q = (searchRicette || "").toLowerCase().trim();
  const filtrate = useMemo(() => ricette
    .filter(r => filtro === "tutti" || (r.reparto || "altro") === filtro)
    .filter(r => categoria === "tutte" || getCategoria(r) === categoria)
    .filter(r => !q || (r.nome || "").toLowerCase().includes(q))
    .sort((a, b) => (a.nome || "").localeCompare(b.nome || "", "it", { sensitivity: "base" })), [ricette, filtro, categoria, q]);

  const stats = useMemo(() => ({
    totale: ricette.length,
    pasticceria: ricette.filter(r => r.reparto === "pasticceria").length,
    rosticceria: ricette.filter(r => r.reparto === "rosticceria").length,
    allergeni: ricette.filter(r => (r.allergeni?.length || r.allergeni_auto?.length || 0) > 0).length,
  }), [ricette]);

  const counts = useMemo(() => {
    const base = { tutte: ricette.length, panini: 0, torte: 0, lievitati: 0, pasticceria: 0, rosticceria: 0 };
    ricette.forEach(r => { const c = getCategoria(r); if (base[c] !== undefined) base[c] += 1; });
    return base;
  }, [ricette]);

  const panini = counts.panini;

  return (
    <div className="space-y-5 rounded-[32px] bg-gradient-to-br from-[#f2f6f3] via-stone-50 to-white p-3 sm:p-4">
      <div className="rounded-[30px] border border-[#cfdfd5] bg-white/90 p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3"><div className="grid h-16 w-16 place-items-center rounded-3xl border border-[#cfdfd5] bg-[#e8efe9] text-4xl shadow-sm">📋</div><div><h1 className="m-0 text-3xl font-black tracking-tight text-stone-900">Motore Ricette</h1><p className="m-0 mt-1 text-sm font-semibold text-stone-500">Crea, clona e gestisci le ricette. La produzione si fa dalle card Pasticceria e Rosticceria.</p></div></div>
          <button onClick={onRicetteUpdate} className="flex items-center justify-center gap-2 rounded-2xl border border-stone-200 bg-white px-4 py-3 text-sm font-black text-stone-700 shadow-sm hover:bg-stone-50"><RefreshCw size={16} /> Aggiorna</button>
        </div>
      </div>

      <button onClick={() => setRevisione(true)} className="w-fit rounded-full border border-[#cfdfd5] bg-[#f2f6f3] px-4 py-2 text-sm font-black text-[#3f5a4e]">📖 Dizionario nomi</button>

      {revisione && <ModalRevisioneDizionario onClose={() => setRevisione(false)} />}
      {scheda && <SchedaModal ricetta={scheda} onClose={() => setScheda(null)} />}
      {verificaRicetta && <VerificaDisponibilitaModal ricetta={verificaRicetta} onClose={() => setVerificaRicetta(null)} onRicetteUpdate={onRicetteUpdate} />}
      {editor && <SchedaEditorModal ricetta={editor} onClose={() => setEditor(null)} onSaved={onRicetteUpdate} onAnteprima={(r) => { setEditor(null); setScheda(r); }} />}

      <CategoryStrip active={categoria} setActive={setCategoria} counts={counts} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-3xl border border-stone-200 bg-white p-4 shadow-sm"><div className="text-2xl font-black">{stats.totale}</div><div className="text-xs font-bold uppercase text-stone-400">Ricette</div></div>
        <div className="rounded-3xl border border-amber-200 bg-amber-50 p-4 shadow-sm"><div className="text-2xl font-black">{stats.pasticceria}</div><div className="text-xs font-bold uppercase text-amber-700">Pasticceria</div></div>
        <div className="rounded-3xl border border-amber-200 bg-amber-50 p-4 shadow-sm"><div className="text-2xl font-black">{stats.rosticceria}</div><div className="text-xs font-bold uppercase text-amber-700">Rosticceria</div></div>
        <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm"><div className="text-2xl font-black">{panini}</div><div className="text-xs font-bold uppercase text-emerald-700">Panini</div></div>
      </div>

      <div id="lista-ricette" className="rounded-[30px] border border-stone-200 bg-white/95 p-4 shadow-sm">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div><h2 className="m-0 text-xl font-black text-stone-900">Ricette operative</h2><p className="m-0 text-sm font-semibold text-stone-500">Tocca una ricetta per produrla o modificarla.</p></div><button onClick={onNuovaRicetta} className="rounded-2xl bg-[#5b7a6b] px-4 py-3 text-sm font-black text-white shadow-sm"><Plus size={16} className="inline" /> Nuova ricetta</button></div>
        <div className="mb-4 flex flex-col gap-2 sm:flex-row"><div className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" size={16} /><input value={searchRicette || ""} onChange={e => setSearchRicette(e.target.value)} placeholder="Cerca ricetta..." className="w-full rounded-2xl border border-stone-200 bg-white py-3 pl-10 pr-3 text-sm font-semibold outline-none focus:ring-2 focus:ring-[#dce8e0]" /></div><div className="flex flex-wrap gap-2">{reparti.map(r => <button key={r} onClick={() => setFiltro(r)} className={`rounded-2xl border px-3 py-2 text-xs font-black ${filtro === r ? "border-[#b8d0c2] bg-[#e8efe9] text-[#3f5a4e]" : "border-stone-200 bg-white text-stone-600"}`}>{repartoLabel(r)}</button>)}</div></div>
        {loadingRicette ? <div className="py-12 text-center text-stone-400"><RefreshCw className="mx-auto mb-2 animate-spin" />Caricamento ricette...</div> : filtrate.length === 0 ? <div className="py-12 text-center text-stone-400">Nessuna ricetta trovata.</div> : <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{filtrate.map(r => <RecipeCard key={r.id || r.nome} r={r} onOpen={onOpenRicetta} onClone={onCloneRicetta} onScheda={setScheda} onCompila={setEditor} onVerifica={setVerificaRicetta} />)}</div>}
      </div>
    </div>
  );
}
