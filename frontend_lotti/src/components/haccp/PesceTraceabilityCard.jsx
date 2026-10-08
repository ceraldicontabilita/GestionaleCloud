import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../utils/constants";

const inputCls =
  "w-full rounded-xl border border-[#cfdfd5] bg-white px-3 py-2.5 text-sm text-stone-900 focus:border-[#5b7a6b] focus:outline-none focus:ring-2 focus:ring-[#e8efe9]";
const labelCls = "mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500";
const fmtData = (d) => { if (!d) return "—"; const [a, m, g] = String(d).slice(0, 10).split("-"); return g ? `${g}/${m}/${a}` : d; };

const RIC_VUOTO = { prodotto: "", denominazione: "", metodo: "pescato", zona_fao: "", fornitore: "", lotto_fornitore: "", quantita_kg: "", temperatura_arrivo: "", stato_imballo: "integro", data_scadenza: "", operatore: "" };
const ABB_VUOTO = { prodotto: "", fornitore: "", lotto_fornitore: "", quantita_kg: "", operatore: "" };

export default function PesceTraceabilityCard() {
  const [sezione, setSezione] = useState("ricevimento"); // ricevimento | abbattimento | richiamo
  const [ric, setRic] = useState(RIC_VUOTO);
  const [allerg, setAllerg] = useState({ pesce: true, crostacei: false, molluschi: false });
  const [abb, setAbb] = useState(ABB_VUOTO);
  const [lotti, setLotti] = useState([]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [qRecall, setQRecall] = useState("");
  const [recall, setRecall] = useState(null);

  const carica = useCallback(async () => {
    try { const r = await axios.get(`${API}/lotti/pesce?limit=12`); setLotti(r.data?.lotti || []); }
    catch { setLotti([]); }
  }, []);
  useEffect(() => { carica(); }, [carica]);

  const salvaRicevimento = async () => {
    if (!ric.prodotto.trim()) { setMsg({ ok: false, t: "Scrivi il prodotto" }); return; }
    setSaving(true); setMsg(null);
    try {
      const r = await axios.post(`${API}/lotti/ricevimento-pesce`, {
        ...ric, quantita_kg: Number(ric.quantita_kg) || 0,
        allergeni: Object.keys(allerg).filter((k) => allerg[k]),
      });
      setMsg({ ok: true, t: `Ricevimento registrato: lotto ${r.data?.lotto?.numero_lotto}${ric.stato_imballo !== "integro" ? " — ANOMALIA imballo segnalata" : ""}.` });
      setRic(RIC_VUOTO); carica();
    } catch (e) { setMsg({ ok: false, t: e?.response?.data?.detail || "Errore" }); }
    finally { setSaving(false); }
  };

  const salvaAbbattimento = async () => {
    if (!abb.prodotto.trim()) { setMsg({ ok: false, t: "Scrivi il prodotto" }); return; }
    setSaving(true); setMsg(null);
    try {
      const r = await axios.post(`${API}/lotti/abbattimento-pesce`, { ...abb, quantita_kg: Number(abb.quantita_kg) || 0 });
      setMsg({ ok: true, t: `Abbattimento avviato: lotto ${r.data?.lotto?.numero_lotto} (≥24h a -20°C).` });
      setAbb(ABB_VUOTO); carica();
    } catch (e) { setMsg({ ok: false, t: e?.response?.data?.detail || "Errore" }); }
    finally { setSaving(false); }
  };

  const concludi = async (id) => {
    try {
      const r = await axios.put(`${API}/lotti/abbattimento-pesce/${id}/concludi`);
      setMsg({ ok: true, t: `Abbattimento concluso (${r.data?.abbattimento?.ore_effettive ?? "?"}h) — esito: ${r.data?.abbattimento?.esito}.` });
      carica();
    } catch (e) { setMsg({ ok: false, t: e?.response?.data?.detail || "Errore" }); }
  };

  const cercaRecall = async () => {
    const q = qRecall.trim(); if (q.length < 2) return;
    try { const r = await axios.get(`${API}/lotti/cerca-universale`, { params: { q, limit: 10 } }); setRecall(r.data); }
    catch { setRecall({ totale: 0, risultati: [] }); }
  };

  const Tab = ({ id, label }) => (
    <button onClick={() => { setSezione(id); setMsg(null); }}
      className={`rounded-full px-3 py-1.5 text-xs font-black ${sezione === id ? "bg-[#5b7a6b] text-white" : "bg-white text-[#3f5a4e] border border-[#cfdfd5]"}`}>{label}</button>
  );

  return (
    <section id="pesce-tracciabilita" className="rounded-[32px] border border-[#cfdfd5] bg-gradient-to-br from-[#f2f6f3] via-white to-[#faf7f0] p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="grid h-14 w-14 place-items-center rounded-3xl border border-[#cfdfd5] bg-white/85 text-3xl shadow-sm">🐟</div>
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-2xl font-black text-stone-900">Registro Pesce</h2>
          <p className="m-0 mt-0.5 text-sm font-semibold text-stone-500">Ricevimento (Reg. 1379/2013) · Abbattimento (Reg. 853/2004) · Allergeni · Richiamo — tutto nel sistema lotti unico.</p>
        </div>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <Tab id="ricevimento" label="📥 Ricevimento" />
        <Tab id="abbattimento" label="❄️ Abbattimento" />
        <Tab id="richiamo" label="🔎 Richiamo" />
      </div>

      {msg && (
        <div className={`mb-4 rounded-xl border-l-4 p-3 text-sm font-semibold ${msg.ok ? "border-emerald-500 bg-emerald-50 text-emerald-800" : "border-amber-500 bg-amber-50 text-amber-800"}`}>{msg.t}</div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-3xl border border-[#e2ece6] bg-white p-4 shadow-sm">
          {sezione === "ricevimento" && (
            <>
              <h3 className="m-0 text-base font-black text-stone-900">Registra ricevimento</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className={labelCls}>Prodotto</label>
                  <input className={inputCls} value={ric.prodotto} onChange={(e) => setRic({ ...ric, prodotto: e.target.value })} placeholder="es. Salmone fresco" />
                </div>
                <div>
                  <label className={labelCls}>Denominazione (etichetta)</label>
                  <input className={inputCls} value={ric.denominazione} onChange={(e) => setRic({ ...ric, denominazione: e.target.value })} placeholder="es. Salmo salar" />
                </div>
                <div>
                  <label className={labelCls}>Metodo</label>
                  <select className={inputCls} value={ric.metodo} onChange={(e) => setRic({ ...ric, metodo: e.target.value })}>
                    <option value="pescato">Pescato</option>
                    <option value="allevato">Allevato</option>
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Zona FAO</label>
                  <input className={inputCls} value={ric.zona_fao} onChange={(e) => setRic({ ...ric, zona_fao: e.target.value })} placeholder="es. FAO 27" />
                </div>
                <div>
                  <label className={labelCls}>Fornitore</label>
                  <input className={inputCls} value={ric.fornitore} onChange={(e) => setRic({ ...ric, fornitore: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>Lotto fornitore</label>
                  <input className={inputCls} value={ric.lotto_fornitore} onChange={(e) => setRic({ ...ric, lotto_fornitore: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>Quantità (kg)</label>
                  <input className={inputCls} type="number" min="0" value={ric.quantita_kg} onChange={(e) => setRic({ ...ric, quantita_kg: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>Temperatura arrivo (°C)</label>
                  <input className={inputCls} value={ric.temperatura_arrivo} onChange={(e) => setRic({ ...ric, temperatura_arrivo: e.target.value })} placeholder="es. 2" />
                </div>
                <div>
                  <label className={labelCls}>Stato imballo</label>
                  <select className={inputCls} value={ric.stato_imballo} onChange={(e) => setRic({ ...ric, stato_imballo: e.target.value })}>
                    <option value="integro">Integro</option>
                    <option value="danneggiato">Danneggiato</option>
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Scadenza (dal fornitore)</label>
                  <input className={inputCls} type="date" value={ric.data_scadenza} onChange={(e) => setRic({ ...ric, data_scadenza: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>Operatore</label>
                  <input className={inputCls} value={ric.operatore} onChange={(e) => setRic({ ...ric, operatore: e.target.value })} />
                </div>
                <div className="sm:col-span-2">
                  <label className={labelCls}>Allergeni presenti</label>
                  <div className="flex flex-wrap gap-3">
                    {["pesce", "crostacei", "molluschi"].map((a) => (
                      <label key={a} className="flex items-center gap-2 text-sm font-bold text-stone-700">
                        <input type="checkbox" checked={allerg[a]} onChange={(e) => setAllerg({ ...allerg, [a]: e.target.checked })} className="h-5 w-5" />
                        {a.charAt(0).toUpperCase() + a.slice(1)}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <button onClick={salvaRicevimento} disabled={saving}
                className="mt-4 rounded-xl bg-[#5b7a6b] px-4 py-2.5 text-sm font-black text-white hover:bg-[#3f5a4e] disabled:opacity-50">
                {saving ? "Salvo…" : "📥 Registra ricevimento"}
              </button>
            </>
          )}
          {sezione === "abbattimento" && (
            <>
              <h3 className="m-0 text-base font-black text-stone-900">Avvia abbattimento (consumo crudo)</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className={labelCls}>Prodotto</label>
                  <input className={inputCls} value={abb.prodotto} onChange={(e) => setAbb({ ...abb, prodotto: e.target.value })} placeholder="es. Alici per marinatura" />
                </div>
                <div>
                  <label className={labelCls}>Fornitore</label>
                  <input className={inputCls} value={abb.fornitore} onChange={(e) => setAbb({ ...abb, fornitore: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>Lotto fornitore</label>
                  <input className={inputCls} value={abb.lotto_fornitore} onChange={(e) => setAbb({ ...abb, lotto_fornitore: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>Quantità (kg)</label>
                  <input className={inputCls} type="number" min="0" value={abb.quantita_kg} onChange={(e) => setAbb({ ...abb, quantita_kg: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>Operatore</label>
                  <input className={inputCls} value={abb.operatore} onChange={(e) => setAbb({ ...abb, operatore: e.target.value })} />
                </div>
              </div>
              <button onClick={salvaAbbattimento} disabled={saving}
                className="mt-4 rounded-xl bg-[#5b7a6b] px-4 py-2.5 text-sm font-black text-white hover:bg-[#3f5a4e] disabled:opacity-50">
                {saving ? "Salvo…" : "❄️ Avvia abbattimento (-20°C, ≥24h)"}
              </button>
            </>
          )}
          {sezione === "richiamo" && (
            <>
              <h3 className="m-0 text-base font-black text-stone-900">Richiamo / verifica lotto</h3>
              <p className="mt-1 text-sm font-semibold text-stone-500">Cerca per lotto fornitore, prodotto o fornitore: trovi tutti i lotti collegati (pesce, produzioni, gelati).</p>
              <div className="mt-3 flex gap-2">
                <input className={inputCls} value={qRecall} onChange={(e) => setQRecall(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && cercaRecall()} placeholder="es. SAL-999, salmone, ITTICA…" />
                <button onClick={cercaRecall} className="rounded-xl bg-[#5b7a6b] px-4 text-sm font-black text-white">Cerca</button>
              </div>
              {recall && (
                <div className="mt-3 space-y-2">
                  <div className="text-xs font-black text-stone-500">{recall.totale} lotti trovati</div>
                  {(recall.risultati || []).map((l) => (
                    <div key={l.id || l.numero_lotto} className="rounded-2xl bg-amber-50 p-3">
                      <div className="text-sm font-black text-amber-900">{l.prodotto} · {l.numero_lotto}</div>
                      <div className="text-xs font-semibold text-amber-800">match: {(l.match_in || []).join(", ") || "—"} · scad. {fmtData(l.data_scadenza)}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div className="rounded-3xl border border-amber-100 bg-white p-4 shadow-sm">
          <h3 className="m-0 text-base font-black text-stone-900">Registro: ultimi movimenti</h3>
          {lotti.length === 0 ? (
            <p className="mt-3 text-sm font-semibold text-stone-400">Nessun lotto pesce registrato.</p>
          ) : (
            <div className="mt-3 space-y-2">
              {lotti.map((l) => {
                const ab = l.abbattimento || null;
                const inCorso = ab && !ab.fine;
                return (
                  <div key={l.id} className="rounded-2xl bg-amber-50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0 text-sm font-black text-amber-900">{l.prodotto}</div>
                      <div className="flex items-center gap-1.5">
                        <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-black text-[#3f5a4e]">{l.numero_lotto}</span>
                        {l.tipo === "pesce_ricevimento" && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-black text-emerald-800">ricevuto</span>}
                        {inCorso && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-black text-amber-800">in abbattimento</span>}
                        {ab && ab.fine && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-black text-emerald-800">abbattuto ✓</span>}
                        {l.anomalia && <span className="rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-black text-red-700">anomalia</span>}
                      </div>
                    </div>
                    <div className="mt-1 text-xs font-semibold text-amber-800">
                      {l.fornitore ? `${l.fornitore} · ` : ""}{l.lotto_fornitore ? `lotto forn. ${l.lotto_fornitore} · ` : ""}
                      {l.temperatura_arrivo ? `arrivo ${l.temperatura_arrivo}°C · ` : ""}
                      {fmtData(l.data_produzione)} · scad. {fmtData(l.data_scadenza)}
                      {(l.allergeni || []).length ? ` · allergeni: ${l.allergeni.join(", ")}` : ""}
                    </div>
                    {inCorso && (
                      <button onClick={() => concludi(l.id)}
                        className="mt-2 rounded-lg bg-[#5b7a6b] px-3 py-1.5 text-xs font-black text-white hover:bg-[#3f5a4e]">
                        ✓ Concludi abbattimento (dopo 24h)
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
