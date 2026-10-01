import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { AlertTriangle, CheckCircle2, Hotel, Link2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { API, formatDate } from "../../utils/constants";

const STATI = ["ricevuto", "confermato", "in_preparazione", "pronto", "consegnato", "annullato"];
const label = (s) => String(s || "").replaceAll("_", " ");
const euro = (n) => Number(n || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });

function Riga({ ordine, riga, onAggiornato, onNavigate }) {
  const [lotto, setLotto] = useState("");
  const associa = async () => {
    if (!lotto.trim()) return toast.warning("Scrivi il numero o ID del lotto reale");
    try {
      await axios.post(`${API}/ordini-hotel/${ordine.id}/lotti`, { chiave: riga.chiave, lotto_id: lotto.trim() });
      setLotto(""); toast.success("Lotto associato all'ordine"); onAggiornato();
    } catch (e) { toast.error(e.response?.data?.detail || "Lotto non associato"); }
  };
  const apriRicetta = () => {
    try { sessionStorage.setItem("apri_ricetta_id", riga.ricetta_id); } catch { /* no-op */ }
    onNavigate("ricette");
  };
  return (
    <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><b>{riga.quantita}× {riga.nome}</b><div className="text-xs text-stone-500">{euro(riga.prezzo_unitario)} cad. · {euro(riga.totale)}</div></div>
        <span className={`rounded-full px-2 py-1 text-[11px] font-bold ${riga.lotti_associati?.length ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"}`}>
          {riga.lotti_associati?.length ? "Lotto associato" : label(riga.tracciabilita_stato)}
        </span>
      </div>
      {!!riga.allergeni?.length && <p className="mt-2 text-xs text-red-700"><b>Allergeni:</b> {riga.allergeni.join(", ")}</p>}
      {!!riga.fatture_origine?.length && <p className="mt-1 text-xs text-stone-500">Prova acquisto: {riga.fatture_origine.map((f) => `fattura ${f.numero_fattura || f.fattura_id || "registrata"}`).join(", ")}</p>}
      {!!riga.lotti_associati?.length && <p className="mt-1 text-xs text-emerald-700">Lotti: {riga.lotti_associati.map((l) => l.numero_lotto || l.id).join(", ")}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {riga.ricetta_id && <button className="rounded-lg bg-[#5b7a6b] px-3 py-2 text-xs font-bold text-white" onClick={apriRicetta}>Apri ricetta / Produci</button>}
        <input className="min-w-[190px] flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm" value={lotto} onChange={(e) => setLotto(e.target.value)} placeholder="Numero o ID lotto reale" />
        <button className="flex items-center gap-1 rounded-lg border border-[#5b7a6b] px-3 py-2 text-xs font-bold text-[#3f5a4e]" onClick={associa}><Link2 size={14}/> Associa lotto</button>
      </div>
    </div>
  );
}

export default function OrdiniHotelView({ onNavigate }) {
  const [ordini, setOrdini] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState("aperti");
  const carica = useCallback(async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/ordini-hotel`); setOrdini(r.data?.ordini || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Ordini hotel non disponibili"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { carica(); }, [carica]);
  const visibili = useMemo(() => ordini.filter((o) => filtro === "tutti" || !["consegnato", "annullato"].includes(o.stato)), [ordini, filtro]);
  const daIncassare = ordini.filter((o) => o.pagamento !== "incassato" && o.stato !== "annullato").reduce((a, o) => a + Number(o.totale || 0), 0);
  const aggiorna = async (id, body) => {
    try { await axios.patch(`${API}/ordini-hotel/${id}`, body); toast.success("Ordine aggiornato"); carica(); }
    catch (e) { toast.error(e.response?.data?.detail || "Aggiornamento non riuscito"); }
  };
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-3 sm:p-5">
      <div className="rounded-2xl bg-gradient-to-br from-[#5b7a6b] to-[#34493f] p-5 text-white shadow-lg">
        <div className="flex items-start justify-between gap-3"><div><h1 className="flex items-center gap-2 text-2xl font-black"><Hotel/> Ordini prodotti dagli hotel</h1><p className="mt-1 text-sm text-white/80">Produzione, allergeni, importi da incassare e lotti reali nello stesso flusso.</p></div><button className="rounded-xl bg-white/15 p-2" onClick={carica} aria-label="Aggiorna"><RefreshCw size={20}/></button></div>
        <div className="mt-4 flex flex-wrap gap-3"><span className="rounded-xl bg-white/15 px-3 py-2 font-bold">{ordini.filter((o) => !["consegnato", "annullato"].includes(o.stato)).length} da lavorare</span><span className="rounded-xl bg-white/15 px-3 py-2 font-bold">{euro(daIncassare)} da incassare</span></div>
      </div>
      <div className="flex gap-2"><button className={`rounded-full px-4 py-2 text-sm font-bold ${filtro === "aperti" ? "bg-[#5b7a6b] text-white" : "bg-white text-stone-600"}`} onClick={() => setFiltro("aperti")}>Da lavorare</button><button className={`rounded-full px-4 py-2 text-sm font-bold ${filtro === "tutti" ? "bg-[#5b7a6b] text-white" : "bg-white text-stone-600"}`} onClick={() => setFiltro("tutti")}>Tutti</button></div>
      {loading ? <p className="text-stone-500">Caricamento…</p> : visibili.length === 0 ? <div className="rounded-2xl bg-white p-6 text-center text-stone-500">Nessun ordine in questa lista.</div> : visibili.map((o) => (
        <article key={o.id} className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-black text-stone-900">{o.struttura_nome} · {o.id}</h2><p className="text-sm text-stone-500">Consegna {formatDate(o.data_consegna)} · creato {formatDate(o.creato_il, true)}</p></div><div className="text-right"><div className="text-xl font-black text-[#5b7a6b]">{euro(o.totale)}</div><span className={`text-xs font-bold ${o.pagamento === "incassato" ? "text-emerald-700" : "text-amber-700"}`}>{o.pagamento === "incassato" ? "Incassato" : "Da incassare"}</span></div></div>
          {o.nota && <div className="mt-3 flex gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle size={17}/>{o.nota}</div>}
          <div className="mt-3 space-y-2">{(o.righe || []).map((r) => <Riga key={r.chiave} ordine={o} riga={r} onAggiornato={carica} onNavigate={onNavigate}/>)}</div>
          <div className="mt-4 flex flex-wrap items-center gap-2"><select className="rounded-lg border border-stone-300 px-3 py-2 text-sm" value={o.stato} onChange={(e) => aggiorna(o.id, { stato: e.target.value })}>{STATI.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select><button className={`flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-bold ${o.pagamento === "incassato" ? "border border-emerald-600 text-emerald-700" : "bg-emerald-600 text-white"}`} onClick={() => aggiorna(o.id, { pagamento: o.pagamento === "incassato" ? "da_incassare" : "incassato" })}><CheckCircle2 size={16}/> {o.pagamento === "incassato" ? "Incassato" : "Segna incassato"}</button></div>
        </article>
      ))}
    </div>
  );
}
