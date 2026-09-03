import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import { Thermometer, Plus, CheckCircle, AlertTriangle, RefreshCw, Trash2, Info } from "lucide-react";
import { SceltaMotivo, MOTIVI } from "./shared/SceltaMotivo";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const TIPI_COTTURA = [
  { v: "forno",     label: "Forno" },
  { v: "pentola",   label: "Pentola / Bollitura" },
  { v: "vapore",    label: "Cottura al Vapore" },
  { v: "griglia",   label: "Griglia / Piastra" },
  { v: "friggitrice", label: "Friggitrice" },
  { v: "microonde", label: "Microonde" },
  { v: "altro",     label: "Altro" },
];

export default function TemperatureCotturaView() {
  const [registrazioni, setReg] = useState([]);
  const [ricette, setRicette]   = useState([]);
  const [stats, setStats]       = useState(null);
  const [loading, setLoading]   = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving]     = useState(false);
  const [form, setForm] = useState({
    prodotto: "",
    ricetta_id: "",
    tipo_cottura: "forno",
    temperatura_cuore: "",
    abbattimento_immediato: false,
    azione_correttiva: "",
    operatore: "",
    note: "",
  });

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [rOggi, rStats, rRic] = await Promise.all([
        axios.get(`${API}/temperature-cottura/oggi`),
        axios.get(`${API}/temperature-cottura/statistiche?giorni=30`),
        axios.get(`${API}/ricette`),
      ]);
      setReg(rOggi.data || []);
      setStats(rStats.data || null);
      setRicette(rRic.data || []);
    } catch { toast.error("Errore caricamento"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const soglia = form.abbattimento_immediato ? 70 : 75;
  const tempVal = form.temperatura_cuore !== "" ? parseFloat(form.temperatura_cuore) : null;
  const tempFuoriNorma = tempVal !== null && tempVal < soglia;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.prodotto.trim()) { toast.error("Inserisci il nome del prodotto"); return; }
    if (form.temperatura_cuore === "") { toast.error("Inserisci la temperatura al cuore"); return; }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/temperature-cottura/registra`, {
        ...form,
        temperatura_cuore: parseFloat(form.temperatura_cuore),
      });
      toast.success(res.data.conforme ? "Temperatura conforme registrata" : "Temperatura NON conforme — verifica azione correttiva");
      setShowForm(false);
      setForm({ prodotto: "", ricetta_id: "", tipo_cottura: "forno", temperatura_cuore: "", abbattimento_immediato: false, azione_correttiva: "", operatore: "", note: "" });
      carica();
    } catch { toast.error("Errore salvataggio"); }
    setSaving(false);
  };

  const elimina = async (id) => {
    if (!await conferma("Eliminare?")) return;
    await axios.delete(`${API}/temperature-cottura/${id}`);
    carica();
  };

  return (
    <div className="space-y-4 p-4 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-red-100 rounded-xl flex items-center justify-center">
            <Thermometer size={20} className="text-red-600" />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-700">Temperatura al cuore ≥ +75°C (≥ +70°C con abbattimento)</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={carica} className="p-2 rounded-xl border border-gray-200 hover:bg-gray-50">
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            onClick={() => setShowForm(v => !v)}
            data-testid="nuova-temp-cottura-btn"
            className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-xl text-sm font-medium hover:bg-red-600 transition-colors"
          >
            <Plus size={15} /> Nuova Misurazione
          </button>
        </div>
      </div>

      {/* KPI */}
      {stats && (
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white border border-gray-100 rounded-xl p-3 text-center shadow-sm">
            <p className="text-2xl font-bold text-gray-900">{stats.totale_registrazioni}</p>
            <p className="text-xs text-gray-500">Misurazioni 30gg</p>
          </div>
          <div className={`border rounded-xl p-3 text-center shadow-sm ${stats.percentuale_conformita >= 95 ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`}>
            <p className={`text-2xl font-bold ${stats.percentuale_conformita >= 95 ? "text-green-700" : "text-red-700"}`}>{stats.percentuale_conformita}%</p>
            <p className="text-xs text-gray-500">Conformità</p>
          </div>
        </div>
      )}

      {/* Banner info */}
      <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-800">
        <Info size={14} className="flex-shrink-0 mt-0.5" />
        <span>
          <strong>Norma HACCP:</strong> La temperatura interna (al cuore) del prodotto deve raggiungere almeno <strong>+75°C</strong> per garantire la sicurezza microbiologica.
          Con abbattimento immediato: ≥ <strong>+70°C</strong> al cuore.
        </span>
      </div>

      {/* Form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white border border-red-200 rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="font-semibold text-gray-800 text-sm">Nuova Misurazione Temperatura Cottura</h3>

          <div className="grid grid-cols-2 gap-3">
            {/* Prodotto */}
            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-600 block mb-1">Prodotto / Ricetta *</label>
              <div className="flex gap-2">
                <input value={form.prodotto} onChange={e => setForm(f => ({...f, prodotto: e.target.value}))}
                  className="min-w-0 flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm"
                  placeholder="Nome prodotto o preparazione" />
                <select value={form.ricetta_id}
                  onChange={e => {
                    const ric = ricette.find(r => r.id === e.target.value);
                    setForm(f => ({...f, ricetta_id: e.target.value, prodotto: ric ? ric.nome : f.prodotto}));
                  }}
                  className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white min-w-[160px]">
                  <option value="">Da ricettario...</option>
                  {ricette.map(r => <option key={r.id} value={r.id}>{r.nome}</option>)}
                </select>
              </div>
            </div>

            {/* Tipo cottura */}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Tipo Cottura *</label>
              <select value={form.tipo_cottura} onChange={e => setForm(f => ({...f, tipo_cottura: e.target.value}))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
                {TIPI_COTTURA.map(t => <option key={t.v} value={t.v}>{t.label}</option>)}
              </select>
            </div>

            {/* Temperatura al cuore */}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">
                Temperatura al Cuore (°C) * <span className="text-gray-400">min {soglia}°C</span>
              </label>
              <input type="number" step="0.1" min="-10" max="300"
                value={form.temperatura_cuore}
                onChange={e => setForm(f => ({...f, temperatura_cuore: e.target.value}))}
                className={`w-full px-3 py-2 border rounded-lg text-sm font-bold ${
                  tempFuoriNorma ? "border-red-400 bg-red-50 text-red-700" :
                  tempVal !== null && tempVal >= soglia ? "border-green-400 bg-green-50 text-green-700" :
                  "border-gray-200"
                }`}
                placeholder={`min ${soglia}°C`} />
              {tempFuoriNorma && <p className="text-xs text-red-600 mt-0.5">Sotto soglia! Prolungare la cottura</p>}
              {tempVal !== null && tempVal >= soglia && <p className="text-xs text-green-600 mt-0.5">Temperatura conforme</p>}
            </div>
          </div>

          {/* Abbattimento */}
          <div className="flex items-center gap-3 p-3 bg-[#f2f6f3] rounded-xl border border-[#cfdfd5]">
            <input type="checkbox" id="abbatt" checked={form.abbattimento_immediato}
              onChange={e => setForm(f => ({...f, abbattimento_immediato: e.target.checked}))}
              className="w-4 h-4 text-[#5b7a6b] rounded" />
            <label htmlFor="abbatt" className="text-sm text-[#3f5a4e]">
              Abbattimento immediato dopo cottura (soglia ridotta a +70°C)
            </label>
          </div>

          {/* Azione correttiva — solo se fuori norma */}
          {tempFuoriNorma && (
            <div>
              <label className="text-xs font-medium text-red-600 block mb-1">Azione Correttiva *</label>
              <SceltaMotivo tono="danger" opzioni={MOTIVI.cottura_sotto_soglia}
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
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={() => setShowForm(false)}
              className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50">Annulla</button>
            <button type="submit" disabled={saving}
              data-testid="salva-temp-cottura-btn"
              className="flex-1 py-2.5 bg-red-500 text-white rounded-xl text-sm font-semibold hover:bg-red-600 disabled:opacity-50">
              {saving ? "Salvataggio..." : "Registra Temperatura"}
            </button>
          </div>
        </form>
      )}

      {/* Lista */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-700">
          Registrazioni di oggi {registrazioni.length > 0 && <span className="text-gray-400 font-normal">({registrazioni.length})</span>}
        </h3>
        {loading ? (
          <div className="text-center py-8 text-gray-400"><RefreshCw className="animate-spin mx-auto mb-2" size={18} /> Caricamento...</div>
        ) : registrazioni.length === 0 ? (
          <div className="text-center py-10 bg-gray-50 rounded-2xl border border-dashed border-gray-200">
            <Thermometer size={28} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-400">Nessuna misurazione cottura oggi</p>
          </div>
        ) : (
          registrazioni.map(reg => {
            const tipoCottura = TIPI_COTTURA.find(t => t.v === reg.tipo_cottura)?.label || reg.tipo_cottura;
            return (
              <div key={reg.id} data-testid={`temp-cottura-${reg.id}`}
                className={`flex items-start gap-3 p-4 rounded-xl border ${reg.conforme ? "bg-white border-gray-100" : "bg-red-50 border-red-200"}`}>
                <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${reg.conforme ? "bg-green-100" : "bg-red-100"}`}>
                  {reg.conforme ? <CheckCircle size={16} className="text-green-600" /> : <AlertTriangle size={16} className="text-red-600" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-gray-900 capitalize">{reg.prodotto}</span>
                    <span className={`text-lg font-bold ${reg.conforme ? "text-green-700" : "text-red-700"}`}>
                      {reg.temperatura_cuore}°C
                    </span>
                    <span className="text-xs text-gray-400">{tipoCottura}</span>
                    {reg.abbattimento_immediato && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#e8efe9] text-[#5b7a6b]">+Abbattimento</span>
                    )}
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${reg.conforme ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {reg.conforme ? "CONFORME" : "NON CONFORME"}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                    <span>{reg.ora}</span>
                    {reg.operatore && <span>Op: {reg.operatore}</span>}
                    <span className="text-gray-400">Soglia: {reg.soglia_applicata}°C</span>
                  </div>
                  {!reg.conforme && reg.azione_correttiva && (
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
