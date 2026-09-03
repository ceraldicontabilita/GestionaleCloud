import { useState, useEffect, useCallback } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import {
  Bug, ChevronLeft, ChevronRight, RefreshCw, Check, AlertTriangle,
  Printer, Plus, X, Save, Edit, User, Wrench
} from "lucide-react";
import { API, MESI_IT, withToken } from "../../utils/constants";
import { giorniNelMese } from "../../utils/dateUtils";

// ──────────────────────────────────────────────────────────────
// Modal registra intervento mensile
// ──────────────────────────────────────────────────────────────
const ModalIntervento = ({ anno, mese, interventoEsistente, onClose, onSalvato }) => {
  const oggi = new Date();
  const [giorno, setGiorno] = useState(
    interventoEsistente?.giorno || (mese === oggi.getMonth() + 1 && anno === oggi.getFullYear() ? oggi.getDate() : 15)
  );
  const [esito, setEsito] = useState(interventoEsistente?.esito || "OK - Nessuna infestazione rilevata");
  const [note,  setNote]  = useState(interventoEsistente?.note  || "Derattizzazione e disinfestazione eseguite come da contratto");
  const [responsabile, setResponsabile] = useState(interventoEsistente?.responsabile_interno || "");
  const [tecnico,      setTecnico]      = useState(interventoEsistente?.tecnico_esterno      || "ANTHIRAT CONTROL");
  const [ditta,        setDitta]        = useState(interventoEsistente?.ditta_esterna         || "ANTHIRAT CONTROL SRL");
  const [saving, setSaving] = useState(false);

  const salva = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/disinfestazione/registra-intervento/${anno}/${mese}`, null, {
        params: { giorno, esito, note, responsabile_interno: responsabile, tecnico_esterno: tecnico, ditta_esterna: ditta }
      });
      toast.success("Intervento salvato");
      onSalvato();
      onClose();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
    setSaving(false);
  };

  const numGiorni = giorniNelMese(mese, anno);

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="font-bold text-gray-800">Registra Intervento — {MESI_IT[mese - 1]} {anno}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">Giorno del mese</label>
            <input
              type="number" min={1} max={numGiorni} value={giorno}
              onChange={e => setGiorno(parseInt(e.target.value) || 1)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-orange-400 focus:outline-none"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">Esito</label>
            <select value={esito} onChange={e => setEsito(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-orange-400 focus:outline-none">
              <option value="OK - Nessuna infestazione rilevata">OK — Nessuna infestazione rilevata</option>
              <option value="OK - Presenza minima, gestita">OK — Presenza minima, gestita</option>
              <option value="Richiede intervento straordinario">Richiede intervento straordinario</option>
              <option value="Presenza infestanti — trattamento effettuato">Presenza infestanti — trattamento effettuato</option>
            </select>
          </div>
          {/* Responsabile interno e tecnico esterno */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-gray-600 block mb-1">Responsabile interno</label>
              <input value={responsabile} onChange={e => setResponsabile(e.target.value)}
                placeholder="Es. Mario Rossi"
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-orange-400 focus:outline-none" />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 block mb-1">Tecnico esterno</label>
              <input value={tecnico} onChange={e => setTecnico(e.target.value)}
                placeholder="Nome tecnico"
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-orange-400 focus:outline-none" />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 block mb-1">Ditta esterna</label>
            <input value={ditta} onChange={e => setDitta(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-orange-400 focus:outline-none" />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">Note</label>
            <textarea value={note} onChange={e => setNote(e.target.value)} rows={3}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:ring-2 focus:ring-orange-400 focus:outline-none"
              placeholder="Note sull'intervento..." />
          </div>
        </div>
        <div className="px-5 py-3 border-t bg-gray-50 flex gap-2">
          <button onClick={onClose}
            className="flex-1 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-100">Annulla</button>
          <button onClick={salva} disabled={saving}
            className="flex-1 py-2 bg-orange-600 text-white text-sm font-semibold rounded-lg hover:bg-orange-700 disabled:opacity-50 flex items-center justify-center gap-2">
            {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
            Salva Intervento
          </button>
        </div>
      </div>
    </div>
  );
};

// ──────────────────────────────────────────────────────────────
// Card apparecchio cliccabile
// ──────────────────────────────────────────────────────────────
const CardApparecchio = ({ nome, numero, tipo, dati, onClick }) => {
  const isOk = dati?.esito === "OK";
  const isProblema = dati?.controllato && !isOk;
  const nonControllato = !dati?.controllato;

  return (
    <div
      onClick={onClick}
      title={dati?.note || (nonControllato ? "Clicca per registrare" : dati?.esito)}
      className={`flex flex-col items-center p-2.5 rounded-xl border-2 min-w-[62px] cursor-pointer transition-all hover:scale-105 active:scale-95 select-none ${
        isOk
          ? "bg-green-50 border-green-300 hover:border-green-500"
          : isProblema
            ? "bg-red-50 border-red-300 hover:border-red-500"
            : "bg-gray-50 border-gray-200 hover:border-orange-400 hover:bg-orange-50"
      }`}
    >
      <span className="text-[10px] text-gray-500 font-medium">{tipo}</span>
      <span className="font-bold text-lg leading-none my-0.5">{numero}</span>
      {dati?.controllato ? (
        <div className={`w-6 h-6 rounded-full flex items-center justify-center ${
          isOk ? "bg-green-500 text-white" : "bg-red-500 text-white"
        }`}>
          {isOk ? <Check size={13} /> : <AlertTriangle size={13} />}
        </div>
      ) : (
        <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center">
          <Plus size={11} className="text-gray-400" />
        </div>
      )}
    </div>
  );
};

// ──────────────────────────────────────────────────────────────
// Modal modifica apparecchio
// ──────────────────────────────────────────────────────────────
const ModalApparecchio = ({ anno, mese, apparecchio, datiAttuali, onClose, onSalvato }) => {
  const [esito, setEsito] = useState(datiAttuali?.esito || "OK");
  const [note, setNote] = useState(datiAttuali?.note || "");
  const [saving, setSaving] = useState(false);

  const salva = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/disinfestazione/registra-monitoraggio/${anno}/${mese}`, null, {
        params: { apparecchio, esito, note }
      });
      toast.success(`${apparecchio} aggiornato`);
      onSalvato();
      onClose();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="font-bold text-gray-800 text-sm">{apparecchio}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-2">Esito Controllo</label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { val: "OK", label: "OK — Nessun problema", color: "green" },
                { val: "Richiede intervento", label: "Richiede intervento", color: "red" }
              ].map(opt => (
                <button key={opt.val} type="button" onClick={() => setEsito(opt.val)}
                  className={`py-3 px-3 rounded-xl border-2 text-sm font-semibold transition-all ${
                    esito === opt.val
                      ? opt.color === "green"
                        ? "bg-green-500 border-green-500 text-white"
                        : "bg-red-500 border-red-500 text-white"
                      : "border-gray-200 text-gray-500 hover:border-gray-300"
                  }`}>
                  {opt.color === "green" ? <Check size={14} className="mx-auto mb-1" /> : <AlertTriangle size={14} className="mx-auto mb-1" />}
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">Note (opzionale)</label>
            <input type="text" value={note} onChange={e => setNote(e.target.value)}
              placeholder="es. Tracce rilevate in angolo sinistro"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-orange-400 focus:outline-none" />
          </div>
        </div>
        <div className="px-5 py-3 border-t bg-gray-50 flex gap-2">
          <button onClick={onClose}
            className="flex-1 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-100">Annulla</button>
          <button onClick={salva} disabled={saving}
            className="flex-1 py-2 bg-orange-600 text-white text-sm font-semibold rounded-lg hover:bg-orange-700 disabled:opacity-50 flex items-center justify-center gap-2">
            {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
            Salva
          </button>
        </div>
      </div>
    </div>
  );
};

// ──────────────────────────────────────────────────────────────
// Componente principale
// ──────────────────────────────────────────────────────────────
const DisinfestazioneView = () => {
  const [mese, setMese] = useState(new Date().getMonth() + 1);
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [scheda, setScheda] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modalIntervento, setModalIntervento] = useState(false);
  const [modalApparecchio, setModalApparecchio] = useState(null); // {nome, dati}

  const fetchScheda = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/disinfestazione/scheda-annuale/${anno}`);
      setScheda(res.data);
    } catch {
      toast.error("Errore caricamento scheda disinfestazione");
    }
    setLoading(false);
  }, [anno]);

  useEffect(() => { fetchScheda(); }, [fetchScheda]);

  const cambiaMese = (delta) => {
    let nm = mese + delta;
    let na = anno;
    if (nm < 1) { nm = 12; na--; }
    if (nm > 12) { nm = 1; na++; }
    setMese(nm);
    setAnno(na);
  };

  const getMonitoraggioMese = (apparecchio) => {
    if (!scheda) return null;
    return scheda.monitoraggio_apparecchi?.[apparecchio]?.[String(mese)] || null;
  };

  const getInterventoMese = () => scheda?.interventi_mensili?.[String(mese)] || null;

  if (loading) return <div className="flex items-center justify-center py-16"><RefreshCw className="animate-spin text-orange-500" size={32} /></div>;

  const monitoraggio = scheda?.monitoraggio_apparecchi || {};
  const intervento = getInterventoMese();

  const frigoriferi = Object.keys(monitoraggio)
    .filter(n => n.includes("Frigorifero"))
    .sort((a, b) => parseInt(a.match(/\d+/)?.[0] || 0) - parseInt(b.match(/\d+/)?.[0] || 0));

  const congelatori = Object.keys(monitoraggio)
    .filter(n => n.includes("Congelatore"))
    .sort((a, b) => parseInt(a.match(/\d+/)?.[0] || 0) - parseInt(b.match(/\d+/)?.[0] || 0));

  // Contatori
  const totControllati = frigoriferi.concat(congelatori).filter(n => getMonitoraggioMese(n)?.controllato).length;
  const totOk = frigoriferi.concat(congelatori).filter(n => getMonitoraggioMese(n)?.esito === "OK").length;
  const totApparecchi = frigoriferi.length + congelatori.length;

  return (
    <div className="space-y-4">
      {/* Modals */}
      {modalIntervento && (
        <ModalIntervento
          anno={anno} mese={mese}
          interventoEsistente={intervento}
          onClose={() => setModalIntervento(false)}
          onSalvato={fetchScheda}
        />
      )}
      {modalApparecchio && (
        <ModalApparecchio
          anno={anno} mese={mese}
          apparecchio={modalApparecchio.nome}
          datiAttuali={modalApparecchio.dati}
          onClose={() => setModalApparecchio(null)}
          onSalvato={fetchScheda}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm font-semibold text-gray-600">Monitoraggio Pest Control</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => cambiaMese(-1)} className="p-2 hover:bg-gray-100 rounded-lg"><ChevronLeft size={20} /></button>
          <span className="font-semibold min-w-[150px] text-center">{MESI_IT[mese - 1]} {anno}</span>
          <button onClick={() => cambiaMese(1)} className="p-2 hover:bg-gray-100 rounded-lg"><ChevronRight size={20} /></button>
          <button
            onClick={() => window.open(withToken(`${API}/disinfestazione/export-pdf/${anno}`), '_blank')}
            className="flex items-center gap-1.5 px-3 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium">
            <Printer size={15} /> PDF
          </button>
          <button onClick={fetchScheda} className="p-2 hover:bg-gray-100 rounded-lg" title="Aggiorna">
            <RefreshCw size={18} className="text-gray-500" />
          </button>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-orange-700">{totControllati}/{totApparecchi}</p>
          <p className="text-xs text-orange-600 mt-0.5">Apparecchi controllati</p>
        </div>
        <div className={`border rounded-xl p-3 text-center ${totOk === totControllati && totControllati > 0 ? "bg-green-50 border-green-200" : "bg-amber-50 border-amber-200"}`}>
          <p className={`text-2xl font-bold ${totOk === totControllati && totControllati > 0 ? "text-green-700" : "text-amber-700"}`}>{totOk}</p>
          <p className={`text-xs mt-0.5 ${totOk === totControllati && totControllati > 0 ? "text-green-600" : "text-amber-600"}`}>Senza problemi</p>
        </div>
        <div className={`border rounded-xl p-3 text-center ${intervento ? "bg-green-50 border-green-200" : "bg-gray-50 border-gray-200"}`}>
          <p className={`text-2xl font-bold ${intervento ? "text-green-700" : "text-gray-400"}`}>
            {intervento ? `Gg ${intervento.giorno}` : "—"}
          </p>
          <p className={`text-xs mt-0.5 ${intervento ? "text-green-600" : "text-gray-400"}`}>Intervento mese</p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-3 text-center">
          <p className="text-sm font-semibold text-gray-700 truncate">{scheda?.ditta?.ragione_sociale || "ANTHIRAT CONTROL"}</p>
          <p className="text-xs text-gray-400 mt-0.5">Ditta incaricata</p>
        </div>
      </div>

      {/* Intervento mensile */}
      <div className={`rounded-xl border-2 p-4 ${intervento ? "bg-green-50 border-green-300" : "bg-amber-50 border-amber-300"}`}>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <p className="font-semibold text-gray-800 flex items-center gap-2">
              <Bug size={16} className="text-red-600" />
              Intervento {MESI_IT[mese - 1]} {anno}
            </p>
            {intervento ? (
              <p className="text-sm text-green-700 mt-1">
                <strong>Giorno {intervento.giorno}</strong> — {intervento.esito?.split(' - ')[0]}
                {intervento.responsabile_interno && (
                  <span className="ml-2 inline-flex items-center gap-1 text-[#5b7a6b] text-xs">
                    <User size={12} /> {intervento.responsabile_interno}
                  </span>
                )}
                {intervento.tecnico_esterno && (
                  <span className="ml-2 inline-flex items-center gap-1 text-[#5b7a6b] text-xs">
                    <Wrench size={12} /> {intervento.tecnico_esterno}
                  </span>
                )}
                {intervento.note && <span className="ml-2 text-gray-500 text-xs">{intervento.note}</span>}
              </p>
            ) : (
              <p className="text-sm text-amber-600 mt-1">Nessun intervento registrato per questo mese</p>
            )}
          </div>
          <button
            onClick={() => setModalIntervento(true)}
            className="flex items-center gap-1.5 px-4 py-2 bg-orange-600 text-white text-sm font-semibold rounded-lg hover:bg-orange-700">
            {intervento ? <><Edit size={14} /> Modifica</> : <><Plus size={14} /> Registra Intervento</>}
          </button>
        </div>
      </div>

      {/* Frigoriferi */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="bg-[#f2f6f3] px-4 py-2.5 flex items-center justify-between">
          <h4 className="font-semibold text-[#3f5a4e] text-sm">
            Frigoriferi — {MESI_IT[mese - 1]} {anno}
          </h4>
          <span className="text-xs text-[#5b7a6b]">
            {frigoriferi.filter(n => getMonitoraggioMese(n)?.controllato).length}/{frigoriferi.length} controllati
          </span>
        </div>
        <p className="text-xs text-gray-400 px-4 pt-2">Clicca su un frigorifero per registrare il controllo</p>
        <div className="p-3 flex gap-2 flex-wrap">
          {frigoriferi.map((nome, idx) => (
            <CardApparecchio
              key={nome}
              nome={nome}
              numero={idx + 1}
              tipo="Frigo"
              dati={getMonitoraggioMese(nome)}
              onClick={() => setModalApparecchio({ nome, dati: getMonitoraggioMese(nome) })}
            />
          ))}
        </div>
      </div>

      {/* Congelatori */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="bg-[#f2f6f3] px-4 py-2.5 flex items-center justify-between">
          <h4 className="font-semibold text-[#34483f] text-sm">
            Congelatori — {MESI_IT[mese - 1]} {anno}
          </h4>
          <span className="text-xs text-[#4f6d5f]">
            {congelatori.filter(n => getMonitoraggioMese(n)?.controllato).length}/{congelatori.length} controllati
          </span>
        </div>
        <p className="text-xs text-gray-400 px-4 pt-2">Clicca su un congelatore per registrare il controllo</p>
        <div className="p-3 flex gap-2 flex-wrap">
          {congelatori.map((nome, idx) => (
            <CardApparecchio
              key={nome}
              nome={nome}
              numero={idx + 1}
              tipo="Cong"
              dati={getMonitoraggioMese(nome)}
              onClick={() => setModalApparecchio({ nome, dati: getMonitoraggioMese(nome) })}
            />
          ))}
        </div>
      </div>

      {/* Riepilogo Annuale */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="bg-gray-100 px-4 py-2.5 flex items-center justify-between">
          <h4 className="font-semibold text-gray-700 text-sm">Riepilogo Interventi Anno {anno}</h4>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-gray-50">
              <tr>
                {MESI_IT.map((m, i) => (
                  <th key={i} className={`px-2 py-2 text-center font-medium text-gray-600 cursor-pointer hover:bg-orange-50 transition-colors ${mese === i + 1 && anno === anno ? "bg-orange-100 text-orange-700" : ""}`}
                    onClick={() => setMese(i + 1)}>
                    {m.slice(0, 3)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {MESI_IT.map((_, idx) => {
                  const meseNum = idx + 1;
                  const int = scheda?.interventi_mensili?.[String(meseNum)];
                  const isCurrentMese = meseNum === mese;
                  return (
                    <td key={idx}
                      className={`px-2 py-2 text-center border-t cursor-pointer transition-colors ${isCurrentMese ? "bg-orange-50" : "hover:bg-gray-50"}`}
                      onClick={() => { setMese(meseNum); }}>
                      {int ? (
                        <div className="flex flex-col items-center">
                          <span className="font-bold text-gray-700">{int.giorno}</span>
                          <div className={`w-4 h-4 rounded-full flex items-center justify-center mt-0.5 ${
                            int.esito?.includes("OK") ? "bg-green-100 text-green-600" : "bg-yellow-100 text-yellow-600"
                          }`}>
                            <Check size={10} />
                          </div>
                        </div>
                      ) : (
                        <span className="text-gray-300 text-base">·</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Legenda */}
      <div className="flex items-center gap-4 text-xs text-gray-500 bg-gray-50 p-3 rounded-xl flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center text-white"><Check size={11} /></span>
          OK — nessuna infestazione
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white"><AlertTriangle size={11} /></span>
          Richiede intervento
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-5 h-5 bg-gray-200 rounded-full flex items-center justify-center"><Plus size={11} className="text-gray-400" /></span>
          Non controllato — clicca per registrare
        </span>
      </div>
    </div>
  );
};

export default DisinfestazioneView;
