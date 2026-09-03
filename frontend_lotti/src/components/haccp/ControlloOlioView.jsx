import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import { Flame, Plus, CheckCircle, AlertTriangle, RefreshCw, Trash2, Info } from "lucide-react";
import { SceltaMotivo, MOTIVI } from "./shared/SceltaMotivo";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// Scala colore olio visuale (1=ottimo → 5=scartare)
const COLORI_OLIO = [
  { v: 1, label: "Chiaro / Ottimo",    cls: "bg-yellow-200 text-yellow-800" },
  { v: 2, label: "Giallo dorato",      cls: "bg-yellow-400 text-yellow-900" },
  { v: 3, label: "Ambrato",            cls: "bg-amber-500 text-white" },
  { v: 4, label: "Marrone / Attenzione", cls: "bg-orange-600 text-white" },
  { v: 5, label: "Scuro / Sostituire", cls: "bg-red-700 text-white" },
];
const FRIGGITRICI_DEFAULT = ["Friggitrice 1", "Friggitrice 2", "Friggitrice 3"];

export default function ControlloOlioView() {
  const [registrazioni, setReg] = useState([]);
  const [stats, setStats]       = useState(null);
  const [loading, setLoading]   = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving]     = useState(false);
  const [form, setForm] = useState({
    friggitrice: "Friggitrice 1",
    colore: 1,
    odore_ok: true,
    polarita: "",
    temperatura: "",
    olio_sostituito: false,
    azione_correttiva: "",
    operatore: "",
    note: "",
  });

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [rOggi, rStats] = await Promise.all([
        axios.get(`${API}/controllo-olio/oggi`),
        axios.get(`${API}/controllo-olio/statistiche?giorni=30`),
      ]);
      setReg(rOggi.data || []);
      setStats(rStats.data || null);
    } catch { toast.error("Errore caricamento dati olio"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`${API}/controllo-olio/registra`, {
        ...form,
        polarita: form.polarita !== "" ? parseFloat(form.polarita) : null,
        temperatura: form.temperatura !== "" ? parseFloat(form.temperatura) : null,
      });
      toast.success("Controllo olio registrato");
      setShowForm(false);
      setForm({ friggitrice: "Friggitrice 1", colore: 1, odore_ok: true, polarita: "", temperatura: "", olio_sostituito: false, azione_correttiva: "", operatore: "", note: "" });
      carica();
    } catch (e) {
      toast.error("Errore salvataggio");
    }
    setSaving(false);
  };

  const elimina = async (id) => {
    if (!await conferma("Eliminare questo controllo?")) return;
    try {
      await axios.delete(`${API}/controllo-olio/${id}`);
      toast.success("Eliminato");
      carica();
    } catch (e) {
      toast.error("Errore durante l'eliminazione");
    }
  };

  return (
    <div className="space-y-4 p-4 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center">
            <Flame size={20} className="text-orange-600" />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-700">Soglia: T° &lt; 175°C — Polarità &lt; 25%</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={carica} className="p-2 rounded-xl border border-gray-200 hover:bg-gray-50">
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            onClick={() => setShowForm(v => !v)}
            data-testid="nuovo-controllo-olio-btn"
            className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded-xl text-sm font-medium hover:bg-orange-600 transition-colors"
          >
            <Plus size={15} /> Nuovo Controllo
          </button>
        </div>
      </div>

      {/* KPI */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white border border-gray-100 rounded-xl p-3 text-center shadow-sm">
            <p className="text-2xl font-bold text-gray-900">{stats.totale_controlli}</p>
            <p className="text-xs text-gray-500">Controlli 30gg</p>
          </div>
          <div className={`border rounded-xl p-3 text-center shadow-sm ${stats.percentuale_conformita >= 90 ? "bg-green-50 border-green-200" : "bg-amber-50 border-amber-200"}`}>
            <p className={`text-2xl font-bold ${stats.percentuale_conformita >= 90 ? "text-green-700" : "text-amber-700"}`}>{stats.percentuale_conformita}%</p>
            <p className="text-xs text-gray-500">Conformità</p>
          </div>
          <div className="bg-[#f2f6f3] border border-[#cfdfd5] rounded-xl p-3 text-center shadow-sm">
            <p className="text-2xl font-bold text-[#5b7a6b]">{stats.sostituzioni_olio}</p>
            <p className="text-xs text-gray-500">Sostituzioni</p>
          </div>
        </div>
      )}

      {/* Banner info soglie */}
      <div className="flex items-start gap-2 bg-orange-50 border border-orange-200 rounded-xl p-3 text-xs text-orange-800">
        <Info size={14} className="flex-shrink-0 mt-0.5" />
        <span>
          <strong>Limiti legali olio frittura:</strong> Temperatura massima <strong>175°C</strong> (limite assoluto 180°C).
          Test polarità (se disponibile): max <strong>25%</strong>. Colore &gt; 3 o odore alterato → sostituire olio.
        </span>
      </div>

      {/* Form nuovo controllo */}
      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white border border-orange-200 rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="font-semibold text-gray-800 text-sm">Registra Controllo Olio</h3>

          <div className="grid grid-cols-2 gap-3">
            {/* Friggitrice */}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Friggitrice *</label>
              <select value={form.friggitrice} onChange={e => setForm(f => ({...f, friggitrice: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
                {FRIGGITRICI_DEFAULT.map(f => <option key={f}>{f}</option>)}
              </select>
            </div>
            {/* Temperatura */}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Temperatura (°C)</label>
              <input type="number" step="0.1" value={form.temperatura}
                onChange={e => setForm(f => ({...f, temperatura: e.target.value}))}
                placeholder="es. 165"
                className={`w-full px-3 py-2 border rounded-lg text-sm ${form.temperatura && parseFloat(form.temperatura) >= 175 ? "border-red-400 bg-red-50" : "border-gray-200"}`} />
              {form.temperatura && parseFloat(form.temperatura) >= 175 && (
                <p className="text-xs text-red-600 mt-0.5">Fuori norma! Max 175°C</p>
              )}
            </div>
          </div>

          {/* Colore olio */}
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-2">Colore Olio *</label>
            <div className="flex gap-2 flex-wrap">
              {COLORI_OLIO.map(c => (
                <button key={c.v} type="button"
                  onClick={() => setForm(f => ({...f, colore: c.v}))}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border-2 transition-all ${form.colore === c.v ? `${c.cls} border-gray-600 scale-105` : "bg-gray-100 text-gray-600 border-transparent hover:border-gray-300"}`}>
                  {c.v} — {c.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Odore */}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Odore Olio *</label>
              <div className="flex gap-2">
                <button type="button" onClick={() => setForm(f => ({...f, odore_ok: true}))}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium border-2 transition-colors ${form.odore_ok ? "bg-green-500 text-white border-green-500" : "bg-white text-gray-600 border-gray-200 hover:border-green-300"}`}>
                  Normale
                </button>
                <button type="button" onClick={() => setForm(f => ({...f, odore_ok: false}))}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium border-2 transition-colors ${!form.odore_ok ? "bg-red-500 text-white border-red-500" : "bg-white text-gray-600 border-gray-200 hover:border-red-300"}`}>
                  Alterato
                </button>
              </div>
            </div>
            {/* Test polarità */}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Test Polarità (%)</label>
              <input type="number" step="0.1" min="0" max="100" value={form.polarita}
                onChange={e => setForm(f => ({...f, polarita: e.target.value}))}
                placeholder="opzionale — max 25%"
                className={`w-full px-3 py-2 border rounded-lg text-sm ${form.polarita && parseFloat(form.polarita) >= 25 ? "border-red-400 bg-red-50" : "border-gray-200"}`} />
              {form.polarita && parseFloat(form.polarita) >= 25 && (
                <p className="text-xs text-red-600 mt-0.5">Fuori norma! Sostituire olio</p>
              )}
            </div>
          </div>

          {/* Olio sostituito */}
          <div className="flex items-center gap-3">
            <input type="checkbox" id="olio_sost" checked={form.olio_sostituito}
              onChange={e => setForm(f => ({...f, olio_sostituito: e.target.checked}))}
              className="w-4 h-4 text-orange-500 rounded" />
            <label htmlFor="olio_sost" className="text-sm text-gray-700 font-medium">Olio sostituito in questa occasione</label>
          </div>

          {/* Azione correttiva — mostra solo se parametri fuori norma */}
          {(form.colore >= 4 || !form.odore_ok || (form.polarita && parseFloat(form.polarita) >= 25) || (form.temperatura && parseFloat(form.temperatura) >= 175)) && (
            <div>
              <label className="text-xs font-medium text-red-600 block mb-1">Azione Correttiva *</label>
              <SceltaMotivo tono="danger" opzioni={MOTIVI.olio_fuori_norma}
                value={form.azione_correttiva}
                onChange={(v) => setForm(f => ({...f, azione_correttiva: v}))} />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Operatore</label>
              <input value={form.operatore} onChange={e => setForm(f => ({...f, operatore: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Nome operatore" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Note</label>
              <input value={form.note} onChange={e => setForm(f => ({...f, note: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Note aggiuntive" />
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={() => setShowForm(false)}
              className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50">Annulla</button>
            <button type="submit" disabled={saving}
              data-testid="salva-controllo-olio-btn"
              className="flex-1 py-2.5 bg-orange-500 text-white rounded-xl text-sm font-semibold hover:bg-orange-600 disabled:opacity-50">
              {saving ? "Salvataggio..." : "Registra Controllo"}
            </button>
          </div>
        </form>
      )}

      {/* Lista controlli oggi */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-700">
          Controlli di oggi {registrazioni.length > 0 && <span className="text-gray-400 font-normal">({registrazioni.length})</span>}
        </h3>
        {loading ? (
          <div className="text-center py-8 text-gray-400"><RefreshCw className="animate-spin mx-auto mb-2" size={18} /> Caricamento...</div>
        ) : registrazioni.length === 0 ? (
          <div className="text-center py-10 bg-gray-50 rounded-2xl border border-dashed border-gray-200">
            <Flame size={28} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-400">Nessun controllo olio registrato oggi</p>
          </div>
        ) : (
          registrazioni.map(reg => {
            const isOk = reg.esito === "CONFORME";
            const coloreOlio = COLORI_OLIO.find(c => c.v === reg.colore) || COLORI_OLIO[0];
            return (
              <div key={reg.id} data-testid={`controllo-olio-${reg.id}`}
                className={`flex items-start gap-3 p-4 rounded-xl border ${isOk ? "bg-white border-gray-100" : "bg-red-50 border-red-200"}`}>
                <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${isOk ? "bg-green-100" : "bg-red-100"}`}>
                  {isOk ? <CheckCircle size={16} className="text-green-600" /> : <AlertTriangle size={16} className="text-red-600" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-gray-900">{reg.friggitrice}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${isOk ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {reg.esito}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${coloreOlio.cls}`}>
                      Colore {reg.colore} — {coloreOlio.label}
                    </span>
                    {reg.olio_sostituito && <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#e8efe9] text-[#5b7a6b] font-medium">Olio Sostituito</span>}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                    <span>{reg.ora}</span>
                    {reg.temperatura != null && <span>T° {reg.temperatura}°C</span>}
                    {reg.polarita != null && <span>Polarità {reg.polarita}%</span>}
                    {reg.odore_ok === false && <span className="text-red-500">Odore alterato</span>}
                    {reg.operatore && <span>Op: {reg.operatore}</span>}
                  </div>
                  {!isOk && reg.azione_correttiva && (
                    <p className="text-xs text-red-700 mt-1 bg-red-100 px-2 py-1 rounded-lg">
                      <strong>Azione:</strong> {reg.azione_correttiva}
                    </p>
                  )}
                </div>
                <button onClick={() => elimina(reg.id)} className="text-gray-300 hover:text-red-400 p-1 flex-shrink-0">
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
