import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { SceltaMotivo, MOTIVI } from "./shared/SceltaMotivo";
import { useConferma } from "./shared/useConferma";
import {
  Truck, Plus, CheckCircle, AlertTriangle, RefreshCw,
  Trash2, X, FileText, ChevronDown, ChevronUp, Package, Flag, ShieldAlert
} from "lucide-react";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

const TIPI_PRODOTTO = [
  { v: "refrigerato", label: "Refrigerato",    range: "0 → +4°C",   color: "blue" },
  { v: "congelato",   label: "Congelato",       range: "-25 → -15°C", color: "cyan" },
  { v: "surgelato",   label: "Surgelato",       range: "-25 → -18°C", color: "indigo" },
  { v: "fresco",      label: "Fresco",          range: "0 → +8°C",   color: "green" },
  { v: "ambient",     label: "Ambiente / Secco", range: "N/A",        color: "amber" },
];

const formVuoto = {
  fornitore_id: "", fornitore_nome: "", prodotto: "",
  tipo_prodotto: "refrigerato", temperatura_ricezione: "",
  lotto_fornitore: "", data_scadenza_lotto: "",
  quantita: "", unita: "cf",
  imballaggio_integro: true, etichetta_conforme: true,
  azione_correttiva: "", accettato: true, operatore: "", note: "",
};

export default function RicezioneMerceView() {
  const { conferma, dialogConferma } = useConferma();
  const [ricezioni,    setRicezioni]    = useState([]);
  const [diFatture,    setDiFatture]    = useState([]);
  const [stats,        setStats]        = useState(null);
  const [loading,      setLoading]      = useState(true);
  const [loadingFatt,  setLoadingFatt]  = useState(false);
  const [showForm,     setShowForm]     = useState(false);
  const [saving,       setSaving]       = useState(false);
  const [form,         setForm]         = useState(formVuoto);
  const [vistaTab,     setVistaTab]     = useState("ricezione"); // ricezione | reclami
  const [reclami,      setReclami]      = useState([]);
  const [loadingReclami, setLoadingReclami] = useState(false);
  const [espanso,      setEspanso]      = useState({});   // apri/chiudi riga da fattura
  const [tempForm,     setTempForm]     = useState({});   // temperatura per ogni riga da fattura
  const [anomalie,     setAnomalie]     = useState({});   // anomalie per riga
  const [confermati,   setConfermati]   = useState({});   // lotti già confermati
  const [giorni,       setGiorni]       = useState(30);

  const caricaTutto = useCallback(async () => {
    setLoading(true);
    setLoadingFatt(true);
    try {
      const [rOggi, rStats, rFatture] = await Promise.allSettled([
        axios.get(`${API}/ricezione-merce/oggi`),
        axios.get(`${API}/ricezione-merce/statistiche/riepilogo?giorni=30`),
        axios.get(`${API}/ricezione-merce/da-fatture/ultimi-arrivi?giorni=${giorni}`),
      ]);
      if (rOggi.status === "fulfilled")    setRicezioni(rOggi.value.data || []);
      if (rStats.status === "fulfilled")   setStats(rStats.value.data || null);
      if (rFatture.status === "fulfilled") setDiFatture(rFatture.value.data || []);
    } catch { toast.error("Errore caricamento ricezioni"); }
    finally { setLoading(false); setLoadingFatt(false); }
  }, [giorni]);

  // Mantieni alias per compatibilità con i chiamanti interni
  const carica = caricaTutto;
  const caricaDaFatture = caricaTutto;

  useEffect(() => { caricaTutto(); }, [caricaTutto]);

  // Calcola conformità temperatura
  // Accetta la virgola italiana ("1,5"): l'input è testo, qui si normalizza.
  const numTemp = (temp) => parseFloat(String(temp).replace(",", "."));
  const calcConformita = (temp, tipo) => {
    if (temp === "" || temp === null || temp === undefined || tipo === "ambient") return true;
    const soglie = { refrigerato: [0,4], congelato: [-25,-15], surgelato: [-25,-18], fresco: [0,8] };
    const [min, max] = soglie[tipo] || [0,4];
    return numTemp(temp) >= min && numTemp(temp) <= max;
  };

  // Form manuale
  const tempVal = form.temperatura_ricezione !== "" ? parseFloat(form.temperatura_ricezione) : null;
  const isTempConform = calcConformita(tempVal, form.tipo_prodotto);
  const isConform = isTempConform && form.imballaggio_integro && form.etichetta_conforme;
  const tipoProdSelected = TIPI_PRODOTTO.find(t => t.v === form.tipo_prodotto) || TIPI_PRODOTTO[0];

  const handleSubmitManuale = async (e) => {
    e.preventDefault();
    if (!form.fornitore_nome.trim()) { toast.error("Inserisci il fornitore"); return; }
    if (!form.prodotto.trim()) { toast.error("Inserisci il prodotto"); return; }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/ricezione-merce/registra`, {
        ...form, temperatura_ricezione: tempVal, accettato: form.accettato && isConform,
      });
      toast.success(res.data.conforme ? "Ricezione conforme registrata" : "Ricezione NON CONFORME registrata");
      setShowForm(false);
      setForm(formVuoto);
      carica();
    } catch { toast.error("Errore salvataggio"); }
    setSaving(false);
  };

  // Conferma da fattura
  const confermaDaFattura = async (lotto) => {
    const temp = tempForm[lotto.lotto_id] ?? "";
    const anomalia = anomalie[lotto.lotto_id] ?? {};
    const imb_ok = anomalia.imballaggio !== true ? true : false;  // se spuntato = non integro
    const eth_ok = anomalia.etichetta !== true ? true : false;
    const tipo = lotto.tipo_prodotto_suggerito || "refrigerato";
    const tempConform = calcConformita(temp, tipo);
    const conforme = tempConform && !anomalia.imballaggio && !anomalia.etichetta && !anomalia.nonConforme;

    if (!conforme && !anomalia.azione) {
      toast.error("Inserire l'azione correttiva per la non conformità");
      return;
    }

    setSaving(true);
    try {
      const res = await axios.post(`${API}/ricezione-merce/registra`, {
        fornitore_nome: lotto.fornitore,
        prodotto: lotto.prodotto_nome,
        tipo_prodotto: tipo,
        temperatura_ricezione: temp !== "" ? numTemp(temp) : null,
        lotto_fornitore: lotto.lotto_id,
        data_scadenza_lotto: lotto.data_scadenza ? lotto.data_scadenza.split("/").reverse().join("-") : "",
        quantita: lotto.quantita_disponibile || "",
        unita: lotto.unita_misura || "cf",
        imballaggio_integro: !anomalia.imballaggio,
        etichetta_conforme: !anomalia.etichetta,
        azione_correttiva: anomalia.azione || "",
        accettato: anomalia.respinta ? false : true,
        note: `Da fattura ${lotto.fattura_ref} del ${lotto.data_fattura}`,
        operatore: anomalia.operatore || "",
      });

      // Feedback ordine aggiornato
      const statoOrdine = res.data?.ordine_stato;
      if (statoOrdine === "ricevuto") {
        toast.success("✅ Ricezione registrata — Ordine fornitore CHIUSO completamente");
      } else if (statoOrdine === "ricevuto_parziale") {
        toast.success("⚠ Ricezione registrata — Ordine fornitore: PARZIALMENTE ricevuto");
      } else {
        toast.success(conforme ? "Ricezione conforme registrata" : "Anomalia registrata");
      }

      setConfermati(c => ({...c, [lotto.lotto_id]: true}));
      setEspanso(e => ({...e, [lotto.lotto_id]: false}));
      carica();
    } catch { toast.error("Errore salvataggio"); }
    setSaving(false);
  };

  const caricaReclami = useCallback(async () => {
    setLoadingReclami(true);
    try {
      const res = await axios.get(`${API}/reclami-fornitori`);
      setReclami(res.data?.reclami || []);
    } catch { /* silenzioso */ }
    finally { setLoadingReclami(false); }
  }, []);

  useEffect(() => {
    caricaReclami();  // anche al mount: il badge "aperti" era sempre 0
  }, [vistaTab, caricaReclami]);

  const elimina = async (id) => {
    if (!(await conferma("Eliminare questa ricezione?"))) return;
    await axios.delete(`${API}/ricezione-merce/${id}`);
    carica();
  };

  const nonConfermati = diFatture.filter(l => !l.gia_ricevuto_oggi && !confermati[l.lotto_id]);
  const giaNotizia = diFatture.filter(l => l.gia_ricevuto_oggi || confermati[l.lotto_id]);

  return (
    <div className="space-y-5 p-4 max-w-4xl mx-auto">
      {dialogConferma}

      {/* Header — flex-wrap: su smartphone i tab e "Ricezione Manuale" andavano
          fuori dallo schermo a destra (audit visivo 24/07/2026) */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 shrink-0 bg-[#e8efe9] rounded-xl flex items-center justify-center">
            <Truck size={20} className="text-[#5b7a6b]" />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-700">Controllo conformità forniture — lettura automatica da fatture XML</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          {/* Tab switcher */}
          <div className="flex border border-gray-200 rounded-xl overflow-hidden">
            <button onClick={() => setVistaTab("ricezione")}
              className={`px-3 py-1.5 text-xs font-semibold flex items-center gap-1.5 ${vistaTab === "ricezione" ? "bg-[#5b7a6b] text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}>
              <Truck size={13} /> Ricezioni
            </button>
            <button onClick={() => setVistaTab("reclami")}
              className={`px-3 py-1.5 text-xs font-semibold flex items-center gap-1.5 ${vistaTab === "reclami" ? "bg-red-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}>
              <ShieldAlert size={13} />
              Reclami
              {reclami.filter(r => r.stato === "aperto").length > 0 && (
                <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 ml-0.5 text-[10px]">
                  {reclami.filter(r => r.stato === "aperto").length}
                </span>
              )}
            </button>
          </div>
          <button onClick={() => { carica(); caricaDaFatture(); }}
            className="p-2 rounded-xl border border-gray-200 hover:bg-gray-50" title="Aggiorna">
            <RefreshCw size={15} className={loading || loadingFatt ? "animate-spin" : ""} />
          </button>
          <button onClick={() => setShowForm(v => !v)} data-testid="nuova-ricezione-btn"
            className="flex items-center gap-2 px-4 py-2 bg-[#5b7a6b] text-white rounded-xl text-sm font-medium hover:bg-[#4d6a5c]">
            <Plus size={15} /> Ricezione Manuale
          </button>
        </div>
      </div>

      {vistaTab === "ricezione" && (<>
      {/* KPI */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white border border-gray-100 rounded-xl p-3 text-center shadow-sm">
            <p className="text-2xl font-bold text-gray-900">{stats.totale_ricezioni}</p>
            <p className="text-xs text-gray-500">Ricezioni 30gg</p>
          </div>
          <div className={`border rounded-xl p-3 text-center shadow-sm ${stats.percentuale_conformita >= 95 ? "bg-green-50 border-green-200" : "bg-amber-50 border-amber-200"}`}>
            <p className={`text-2xl font-bold ${stats.percentuale_conformita >= 95 ? "text-green-700" : "text-amber-700"}`}>{stats.percentuale_conformita}%</p>
            <p className="text-xs text-gray-500">Conformità</p>
          </div>
          <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-center shadow-sm">
            <p className="text-2xl font-bold text-red-700">{stats.merci_respinte}</p>
            <p className="text-xs text-gray-500">Merci Respinte</p>
          </div>
        </div>
      )}

      {/* ── PRODOTTI DA FATTURE XML ── */}
      <div className="bg-white border border-[#dce8e0] rounded-2xl shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 p-4 bg-[#f2f6f3] border-b border-[#dce8e0]">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <FileText size={18} className="text-[#5b7a6b] shrink-0" />
            <h3 className="font-semibold text-[#3f5a4e] text-sm">Prodotti arrivati da fatture XML</h3>
            {nonConfermati.length > 0 && (
              <span className="bg-amber-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                {nonConfermati.length} da verificare
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <select value={giorni} onChange={e => setGiorni(parseInt(e.target.value))}
              className="text-xs px-2 py-1 border border-[#cfdfd5] rounded-lg bg-white">
              <option value={7}>Ultimi 7gg</option>
              <option value={14}>Ultimi 14gg</option>
              <option value={30}>Ultimi 30gg</option>
              <option value={60}>Ultimi 60gg</option>
            </select>
          </div>
        </div>

        {loadingFatt ? (
          <div className="p-8 text-center text-gray-400"><RefreshCw className="animate-spin mx-auto mb-2" size={18} /><p className="text-sm">Caricamento da fatture...</p></div>
        ) : nonConfermati.length === 0 && giaNotizia.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            <Package size={28} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">Nessun prodotto trovato nelle fatture recenti</p>
          </div>
        ) : (
          <div className="divide-y">
            {nonConfermati.map((lotto, idx) => {
              const aperto = espanso[lotto.lotto_id];
              const temp = tempForm[lotto.lotto_id] ?? "";
              const anomalia = anomalie[lotto.lotto_id] ?? {};
              const tipo = lotto.tipo_prodotto_suggerito || "refrigerato";
              const tipoInfo = TIPI_PRODOTTO.find(t => t.v === tipo) || TIPI_PRODOTTO[0];
              const tempConform = calcConformita(temp, tipo);
              const haNonConf = anomalia.imballaggio || anomalia.etichetta || anomalia.nonConforme || (temp !== "" && !tempConform);

              return (
                <div key={`${lotto.lotto_id}-${idx}`} className={`${haNonConf ? "bg-red-50" : "bg-white"}`}>
                  {/* Riga sommario: Conforme registra al volo, Non conforme apre il pannello */}
                  <div className="flex flex-wrap items-center gap-2 p-3 hover:bg-gray-50">
                    <div className="flex flex-1 min-w-0 items-center gap-3 cursor-pointer"
                      onClick={() => setEspanso(e => ({...e, [lotto.lotto_id]: !e[lotto.lotto_id]}))}>
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${haNonConf ? "bg-red-100" : "bg-gray-100"}`}>
                        {haNonConf ? <AlertTriangle size={15} className="text-red-600" /> : <Truck size={15} className="text-gray-500" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">{lotto.prodotto_nome}</p>
                        <p className="text-xs text-gray-500 truncate">
                          {lotto.fornitore} · Lotto {lotto.lotto_id} · Scad: {lotto.data_scadenza || "N/D"} · {tipoInfo.label} · Fatt. {lotto.fattura_ref}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button type="button" disabled={saving}
                        onClick={(e) => { e.stopPropagation(); confermaDaFattura(lotto); }}
                        data-testid={`conforme-rapido-${lotto.lotto_id}`}
                        className="flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-green-700 disabled:opacity-50">
                        <CheckCircle size={13} /> Conforme
                      </button>
                      <button type="button" disabled={saving}
                        onClick={(e) => {
                          e.stopPropagation();
                          setAnomalie(a => ({...a, [lotto.lotto_id]: {...(a[lotto.lotto_id]||{}), nonConforme: true}}));
                          setEspanso(es => ({...es, [lotto.lotto_id]: true}));
                        }}
                        data-testid={`non-conforme-${lotto.lotto_id}`}
                        className="flex items-center gap-1 rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700 hover:bg-red-100 disabled:opacity-50">
                        <AlertTriangle size={13} /> Non conforme
                      </button>
                      <button type="button" className="p-1"
                        onClick={() => setEspanso(e => ({...e, [lotto.lotto_id]: !e[lotto.lotto_id]}))}>
                        {aperto ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
                      </button>
                    </div>
                  </div>

                  {/* Pannello conferma */}
                  {aperto && (
                    <div className="px-4 pb-4 pt-2 bg-gray-50 border-t border-gray-100">
                      <div className="grid grid-cols-2 gap-3 mb-3">
                        {/* Temperatura */}
                        {tipo !== "ambient" && (
                          <div>
                            <label className="text-xs font-medium text-gray-600 block mb-1">
                              Temperatura °C <span className="text-gray-400">({tipoInfo.range})</span>
                            </label>
                            <input type="text" inputMode="decimal" value={temp}
                              onChange={e => setTempForm(t => ({...t, [lotto.lotto_id]: e.target.value}))}
                              className={`w-full px-3 py-2 border rounded-lg text-sm font-bold ${
                                temp !== "" && !tempConform ? "border-red-400 bg-red-50 text-red-700" :
                                temp !== "" && tempConform ? "border-green-400 bg-green-50 text-green-700" :
                                "border-gray-200 bg-white"
                              }`} placeholder="Misura col termometro" />
                            {temp !== "" && !tempConform && (
                              <p className="text-xs text-red-600 mt-0.5">Fuori range! ({tipoInfo.range})</p>
                            )}
                          </div>
                        )}

                        {/* Operatore */}
                        <div>
                          <label className="text-xs font-medium text-gray-600 block mb-1">Operatore</label>
                          <input value={anomalia.operatore || ""}
                            onChange={e => setAnomalie(a => ({...a, [lotto.lotto_id]: {...(a[lotto.lotto_id]||{}), operatore: e.target.value}}))}
                            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
                            placeholder="Nome operatore" />
                        </div>
                      </div>

                      {/* Checklist anomalie */}
                      <div className="space-y-2 mb-3 p-3 bg-white rounded-xl border border-gray-200">
                        <p className="text-xs font-semibold text-gray-600">Segnala anomalie (lascia vuoto = tutto conforme)</p>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input type="checkbox" checked={!!anomalia.imballaggio}
                            onChange={e => setAnomalie(a => ({...a, [lotto.lotto_id]: {...(a[lotto.lotto_id]||{}), imballaggio: e.target.checked}}))}
                            className="w-4 h-4 accent-red-500" />
                          <span className={`text-sm ${anomalia.imballaggio ? "text-red-600 font-medium" : "text-gray-600"}`}>
                            Imballaggio NON integro (rotture, gonfiamenti, perdite)
                          </span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input type="checkbox" checked={!!anomalia.etichetta}
                            onChange={e => setAnomalie(a => ({...a, [lotto.lotto_id]: {...(a[lotto.lotto_id]||{}), etichetta: e.target.checked}}))}
                            className="w-4 h-4 accent-red-500" />
                          <span className={`text-sm ${anomalia.etichetta ? "text-red-600 font-medium" : "text-gray-600"}`}>
                            Etichettatura NON conforme (data illeggibile, dati mancanti)
                          </span>
                        </label>
                      </div>

                      {/* Azione correttiva (se non conforme) — tendina coi motivi
                          pronti: il pasticcere ha le mani sporche, mai tastiera
                          (regola Enzo 04/07/2026); "Altro" solo come eccezione */}
                      {haNonConf && (
                        <div className="mb-3 space-y-2 p-3 bg-red-50 rounded-xl border border-red-200">
                          <p className="text-xs font-semibold text-red-700">Azione correttiva obbligatoria</p>
                          <SceltaMotivo tono="danger" opzioni={MOTIVI.ricezione_non_conforme}
                            value={anomalia.azione || ""}
                            onChange={(v) => setAnomalie(a => ({...a, [lotto.lotto_id]: {...(a[lotto.lotto_id]||{}), azione: v}}))} />
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={!!anomalia.respinta}
                              onChange={e => setAnomalie(a => ({...a, [lotto.lotto_id]: {...(a[lotto.lotto_id]||{}), respinta: e.target.checked}}))}
                              className="w-4 h-4 accent-red-600" />
                            <span className="text-sm text-red-700 font-medium">Merce RESPINTA al fornitore</span>
                          </label>
                        </div>
                      )}

                      <div className="flex gap-2">
                        <button type="button" onClick={() => {
                            setEspanso(e => ({...e, [lotto.lotto_id]: false}));
                            setAnomalie(a => ({...a, [lotto.lotto_id]: {...(a[lotto.lotto_id]||{}), nonConforme: false}}));
                          }}
                          className="px-4 py-2 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-white">
                          Annulla
                        </button>
                        <button type="button" disabled={saving} onClick={() => confermaDaFattura(lotto)}
                          data-testid={`conferma-ricezione-${lotto.lotto_id}`}
                          className={`flex-1 py-2 rounded-xl text-sm font-semibold text-white disabled:opacity-50 ${haNonConf ? "bg-red-500 hover:bg-red-600" : "bg-green-600 hover:bg-green-700"}`}>
                          {saving ? "Salvataggio..." : haNonConf ? "Registra Anomalia" : "Conferma Ricezione Conforme"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {/* Già confermati oggi */}
            {giaNotizia.map(lotto => (
              <div key={lotto.lotto_id} className="flex items-center gap-3 p-3 bg-green-50 opacity-70">
                <CheckCircle size={16} className="text-green-600 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-700 truncate">{lotto.prodotto_nome}</p>
                  <p className="text-xs text-gray-400">{lotto.fornitore} · Lotto {lotto.lotto_id}</p>
                </div>
                <span className="text-xs text-green-700 font-medium bg-green-100 px-2 py-0.5 rounded">Già verificato oggi</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── FORM MANUALE ── */}
      {showForm && (
        <form onSubmit={handleSubmitManuale} className="bg-white border border-[#cfdfd5] rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-800 text-sm">Ricezione Manuale</h3>
            <button type="button" onClick={() => setShowForm(false)}><X size={16} className="text-gray-400 hover:text-gray-600" /></button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-600 block mb-1">Fornitore *</label>
              <input value={form.fornitore_nome} onChange={e => setForm(f => ({...f, fornitore_nome: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                placeholder="Nome fornitore" />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-600 block mb-1">Prodotto / Merce *</label>
              <input value={form.prodotto} onChange={e => setForm(f => ({...f, prodotto: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                placeholder="Es. Farina 00, Mozzarella..." />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-600 block mb-2">Tipo Prodotto</label>
              <div className="flex gap-2 flex-wrap">
                {TIPI_PRODOTTO.map(t => (
                  <button key={t.v} type="button" onClick={() => setForm(f => ({...f, tipo_prodotto: t.v}))}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border-2 transition-all ${form.tipo_prodotto === t.v ? "border-[#5b7a6b] bg-[#f2f6f3] text-[#5b7a6b]" : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"}`}>
                    {t.label} <span className="text-gray-400 font-normal">({t.range})</span>
                  </button>
                ))}
              </div>
            </div>
            {form.tipo_prodotto !== "ambient" && (
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">
                  Temperatura °C <span className="text-gray-400">({tipoProdSelected.range})</span>
                </label>
                <input type="number" step="0.1" value={form.temperatura_ricezione}
                  onChange={e => setForm(f => ({...f, temperatura_ricezione: e.target.value}))}
                  className={`w-full px-3 py-2 border rounded-lg text-sm font-bold ${
                    tempVal !== null && !isTempConform ? "border-red-400 bg-red-50 text-red-700" :
                    tempVal !== null && isTempConform ? "border-green-400 bg-green-50 text-green-700" :
                    "border-gray-200"
                  }`} placeholder="Misura col termometro" />
                {tempVal !== null && !isTempConform && (
                  <p className="text-xs text-red-600 mt-0.5">Fuori range!</p>
                )}
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Lotto Fornitore</label>
              <input value={form.lotto_fornitore} onChange={e => setForm(f => ({...f, lotto_fornitore: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="N° lotto" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Data Scadenza</label>
              <input type="date" value={form.data_scadenza_lotto} onChange={e => setForm(f => ({...f, data_scadenza_lotto: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Operatore</label>
              <input value={form.operatore} onChange={e => setForm(f => ({...f, operatore: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Nome" />
            </div>
          </div>
          <div className="space-y-2 p-3 bg-gray-50 rounded-xl border border-gray-200">
            <p className="text-xs font-semibold text-gray-600 mb-2">Checklist conformità</p>
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" checked={form.imballaggio_integro} onChange={e => setForm(f => ({...f, imballaggio_integro: e.target.checked}))} className="w-4 h-4" />
              <span className={`text-sm ${form.imballaggio_integro ? "text-gray-700" : "text-red-600 font-medium"}`}>Imballaggio integro</span>
              {!form.imballaggio_integro && <AlertTriangle size={14} className="text-red-500" />}
            </label>
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" checked={form.etichetta_conforme} onChange={e => setForm(f => ({...f, etichetta_conforme: e.target.checked}))} className="w-4 h-4" />
              <span className={`text-sm ${form.etichetta_conforme ? "text-gray-700" : "text-red-600 font-medium"}`}>Etichettatura conforme</span>
              {!form.etichetta_conforme && <AlertTriangle size={14} className="text-red-500" />}
            </label>
          </div>
          {!isConform && (
            <div className="space-y-3 p-3 bg-red-50 rounded-xl border border-red-200">
              <p className="text-xs font-semibold text-red-700">Merce NON CONFORME — Azione obbligatoria</p>
              <SceltaMotivo tono="danger" opzioni={MOTIVI.ricezione_non_conforme}
                value={form.azione_correttiva}
                onChange={(v) => setForm(f => ({...f, azione_correttiva: v}))} />
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={form.accettato} onChange={e => setForm(f => ({...f, accettato: e.target.checked}))} className="w-4 h-4" />
                <span className="text-sm text-red-700">Accettata con riserva (non respingere)</span>
              </label>
            </div>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={() => setShowForm(false)}
              className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50">Annulla</button>
            <button type="submit" disabled={saving} data-testid="salva-ricezione-btn"
              className={`flex-1 py-2.5 rounded-xl text-sm font-semibold disabled:opacity-50 text-white ${isConform ? "bg-[#5b7a6b] hover:bg-[#4d6a5c]" : "bg-red-500 hover:bg-red-600"}`}>
              {saving ? "Salvataggio..." : isConform ? "Registra Conforme" : "Registra Non Conforme"}
            </button>
          </div>
        </form>
      )}

      {/* ── RICEZIONI DI OGGI ── */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          Ricezioni registrate oggi
          {ricezioni.length > 0 && <span className="text-gray-400 font-normal">({ricezioni.length})</span>}
        </h3>
        {loading ? (
          <div className="text-center py-8 text-gray-400"><RefreshCw className="animate-spin mx-auto mb-2" size={18} /></div>
        ) : ricezioni.length === 0 ? (
          <div className="text-center py-8 bg-gray-50 rounded-2xl border border-dashed border-gray-200">
            <Truck size={24} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-400">Nessuna ricezione registrata oggi</p>
          </div>
        ) : (
          ricezioni.map(rec => {
            const tipoLabel = TIPI_PRODOTTO.find(t => t.v === rec.tipo_prodotto)?.label || rec.tipo_prodotto;
            return (
              <div key={rec.id} data-testid={`ricezione-${rec.id}`}
                className={`flex items-start gap-3 p-4 rounded-xl border ${rec.conforme ? "bg-white border-gray-100" : "bg-red-50 border-red-200"}`}>
                <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${rec.conforme ? "bg-green-100" : "bg-red-100"}`}>
                  {rec.conforme ? <CheckCircle size={16} className="text-green-600" /> : <AlertTriangle size={16} className="text-red-600" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-gray-900">{rec.prodotto}</span>
                    <span className="text-xs text-gray-500">— {rec.fornitore_nome}</span>
                    <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">{tipoLabel}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${rec.conforme ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {rec.conforme ? "CONFORME" : "NON CONFORME"}
                    </span>
                    {!rec.accettato && <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-700 text-white font-bold">RESPINTA</span>}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 flex-wrap">
                    <span>{rec.ora}</span>
                    {rec.temperatura_ricezione != null && (
                      <span>T° {rec.temperatura_ricezione}°C {!rec.temperatura_conforme && <span className="text-red-500">(fuori range)</span>}</span>
                    )}
                    {rec.lotto_fornitore && <span>Lotto: {rec.lotto_fornitore}</span>}
                    {rec.data_scadenza_lotto && <span>Scad: {rec.data_scadenza_lotto}</span>}
                    {rec.operatore && <span>Op: {rec.operatore}</span>}
                  </div>
                  {!rec.imballaggio_integro && <p className="text-xs text-red-600 mt-0.5">Imballaggio non integro</p>}
                  {!rec.etichetta_conforme && <p className="text-xs text-red-600 mt-0.5">Etichettatura non conforme</p>}
                  {!rec.conforme && rec.azione_correttiva && (
                    <p className="text-xs text-red-700 mt-1 bg-red-100 px-2 py-1 rounded-lg">
                      <strong>Azione:</strong> {rec.azione_correttiva}
                    </p>
                  )}
                </div>
                <button onClick={() => elimina(rec.id)} className="text-gray-300 hover:text-red-400 p-1 flex-shrink-0">
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })
        )}
      </div>

      </>)}

      {/* ── VISTA RECLAMI ── */}
      {vistaTab === "reclami" && (
        <div className="space-y-3">
          {loadingReclami ? (
            <div className="text-center py-8 text-gray-400">Caricamento reclami...</div>
          ) : reclami.length === 0 ? (
            <div className="text-center py-10">
              <ShieldAlert size={40} className="mx-auto text-green-300 mb-3" />
              <p className="text-gray-500 font-medium">Nessun reclamo aperto</p>
              <p className="text-xs text-gray-400 mt-1">Ottimo! Tutti i fornitori stanno rispettando gli standard.</p>
            </div>
          ) : (
            <>
              <div className="flex gap-3 text-xs mb-2">
                <span className="px-2 py-1 bg-red-50 text-red-700 rounded font-semibold">
                  🔴 {reclami.filter(r=>r.stato==="aperto").length} aperti
                </span>
                <span className="px-2 py-1 bg-yellow-50 text-yellow-700 rounded font-semibold">
                  🟡 {reclami.filter(r=>r.stato==="in_gestione").length} in gestione
                </span>
                <span className="px-2 py-1 bg-green-50 text-green-700 rounded font-semibold">
                  🟢 {reclami.filter(r=>r.stato==="risolto").length} risolti
                </span>
              </div>
              {reclami.map(r => (
                <div key={r.id} className="bg-white border border-gray-100 rounded-xl p-3 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                          r.gravita === "critica" ? "bg-red-100 text-red-700" :
                          r.gravita === "alta" ? "bg-orange-100 text-orange-700" :
                          r.gravita === "media" ? "bg-yellow-100 text-yellow-700" :
                          "bg-gray-100 text-gray-600"
                        }`}>{r.gravita?.toUpperCase()}</span>
                        <span className={`text-xs px-2 py-0.5 rounded border ${
                          r.stato === "aperto" ? "border-red-200 text-red-600" :
                          r.stato === "in_gestione" ? "border-yellow-200 text-yellow-600" :
                          "border-green-200 text-green-600"
                        }`}>{r.stato?.replace("_"," ")}</span>
                        <span className="text-xs text-gray-400 font-mono">{r.creato_il?.slice(0,10)}</span>
                      </div>
                      <p className="text-sm font-semibold text-gray-800">{r.fornitore_nome}</p>
                      <p className="text-xs text-gray-500">{r.prodotto} — {r.tipo?.replace(/_/g," ")}</p>
                      <p className="text-xs text-gray-600 mt-1">{r.descrizione}</p>
                      {r.azione_richiesta && (
                        <p className="text-xs text-[#5b7a6b] mt-1">📋 {r.azione_richiesta}</p>
                      )}
                    </div>
                    {r.stato === "aperto" && (
                      <button
                        onClick={async () => {
                          await axios.patch(`${API}/reclami-fornitori/${r.id}/stato?stato=in_gestione`);
                          caricaReclami();
                        }}
                        className="text-xs bg-yellow-50 text-yellow-700 border border-yellow-200 px-2 py-1 rounded whitespace-nowrap hover:bg-yellow-100"
                      >
                        Prendi in carico
                      </button>
                    )}
                    {r.stato === "in_gestione" && (
                      <button
                        onClick={async () => {
                          await axios.patch(`${API}/reclami-fornitori/${r.id}/stato?stato=risolto`);
                          caricaReclami();
                          toast.success("Reclamo segnato come risolto");
                        }}
                        className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-1 rounded whitespace-nowrap hover:bg-green-100"
                      >
                        Segna risolto
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
