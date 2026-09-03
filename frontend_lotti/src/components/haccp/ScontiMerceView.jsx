import { useState, useEffect, useMemo } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import {
  Gift, Plus, Trash2, Edit, RefreshCw, Save, X, Calendar
} from "lucide-react";
import { API } from "../../utils/constants";

const Card = ({ children, className = "" }) => (
  <div className={`bg-white rounded-xl shadow-sm border border-gray-100 ${className}`}>
    {children}
  </div>
);

const MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];

const annoCorrente = new Date().getFullYear();
const meseCorrente = new Date().getMonth() + 1;

const formVuoto = {
  data: new Date().toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" }),
  fornitore: "",
  prodotto: "",
  cartoni: "",
  pezzi_per_cartone: "",
  pezzi_totali: "",
  valore_unitario: "",
  valore_totale: "",
  fattura_riferimento: "",
  note: ""
};

export const ScontiMerceView = () => {
  const [sconti, setSconti] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(formVuoto);
  const [filtroAnno, setFiltroAnno] = useState(annoCorrente);
  const [filtroMese, setFiltroMese] = useState(0);
  const [nascondiNonValorizzati, setNascondiNonValorizzati] = useState(true);
  const [riepilogoMensile, setRiepilogoMensile] = useState(null);
  const [riepilogoFornitori, setRiepilogoFornitori] = useState([]);
  const [vistaAttiva, setVistaAttiva] = useState("lista");
  const [fornitori, setFornitori] = useState([]);
  const [prodottiForn, setProdottiForn] = useState([]); // prodotti del fornitore selezionato

  const fetchSconti = async () => {
    setLoading(true);
    try {
      const params = { anno: filtroAnno };
      if (filtroMese > 0) params.mese = filtroMese;
      const res = await axios.get(`${API}/sconti-merce/`, { params });
      setSconti(res.data || []);
    } catch (e) {
      toast.error("Errore caricamento sconti");
    } finally {
      setLoading(false);
    }
  };

  const fetchRiepilogo = async () => {
    try {
      const [mensile, fornit] = await Promise.all([
        axios.get(`${API}/sconti-merce/riepilogo/mensile`, { params: { anno: filtroAnno } }),
        axios.get(`${API}/sconti-merce/riepilogo/fornitori`, { params: { anno: filtroAnno, ...(filtroMese > 0 ? { mese: filtroMese } : {}) } })
      ]);
      setRiepilogoMensile(mensile.data);
      setRiepilogoFornitori(fornit.data || []);
    } catch (e) {
      console.error(e);
    }
  };

  const importaDaFatture = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/sconti-merce/importa-da-fatture`);
      toast.success(`Importati ${res.data.importati} sconti da ${res.data.fatture_analizzate} fatture (${res.data.saltati_gia_presenti} già presenti)`);
      fetchSconti();
      fetchRiepilogo();
    } catch (e) {
      toast.error("Errore importazione da fatture");
    } finally {
      setLoading(false);
    }
  };

  const fetchFornitori = async () => {
    try {
      const res = await axios.get(`${API}/fornitori`);
      // Solo fornitori attivi (non esclusi)
      const attivi = (res.data || []).filter(f => !f.escluso);
      setFornitori(attivi.map(f => f.nome).filter(Boolean).sort());
    } catch (e) { }
  };

  // Carica prodotti dalle fatture del fornitore selezionato
  const fetchProdottiFornitore = async (nomeFornitore) => {
    if (!nomeFornitore) { setProdottiForn([]); return; }
    try {
      const res = await axios.get(`${API}/sconti-merce/prodotti-fornitore`, {
        params: { fornitore: nomeFornitore }
      });
      setProdottiForn(res.data || []);
    } catch { setProdottiForn([]); }
  };

  useEffect(() => {
    fetchSconti();
    fetchRiepilogo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroAnno, filtroMese]);

  useEffect(() => { fetchFornitori(); }, []);

  // Quando cambia il fornitore nel form → carica i suoi prodotti
  useEffect(() => {
    if (form.fornitore) fetchProdottiFornitore(form.fornitore);
    else setProdottiForn([]);
  }, [form.fornitore]);

  // Calcolo anteprima automatica nel form
  // Accetta la virgola italiana: gli input sono testo, qui si normalizza.
  const num = (v) => parseFloat(String(v ?? "").replace(",", ".")) || 0;
  const anteprima = useMemo(() => {
    const cartoni = num(form.cartoni);
    const ppc = num(form.pezzi_per_cartone);
    const pezziTot = num(form.pezzi_totali) || (cartoni * ppc);
    const valUnit = num(form.valore_unitario);
    const valTot = num(form.valore_totale) || (valUnit * (cartoni || pezziTot));
    return { pezziTot, valTot };
  }, [form]);

  const handleSave = async () => {
    if (!form.fornitore || !form.prodotto) {
      toast.error("Fornitore e prodotto sono obbligatori");
      return;
    }
    try {
      const payload = {
        ...form,
        cartoni: num(form.cartoni),
        pezzi_per_cartone: num(form.pezzi_per_cartone),
        pezzi_totali: num(form.pezzi_totali) || anteprima.pezziTot,
        valore_unitario: num(form.valore_unitario),
        valore_totale: num(form.valore_totale) || anteprima.valTot,
      };
      if (editingId) {
        await axios.put(`${API}/sconti-merce/${editingId}`, payload);
        toast.success("Sconto aggiornato");
      } else {
        await axios.post(`${API}/sconti-merce/`, payload);
        toast.success("Sconto registrato");
      }
      setShowModal(false);
      setEditingId(null);
      setForm(formVuoto);
      fetchSconti();
      fetchRiepilogo();
    } catch (e) {
      toast.error("Errore salvataggio");
    }
  };

  const handleEdit = (s) => {
    setEditingId(s.id);
    setForm({
      data: s.data || "",
      fornitore: s.fornitore || "",
      prodotto: s.prodotto || "",
      cartoni: s.cartoni || "",
      pezzi_per_cartone: s.pezzi_per_cartone || "",
      pezzi_totali: s.pezzi_totali || "",
      valore_unitario: s.valore_unitario || "",
      valore_totale: s.valore_totale || "",
      fattura_riferimento: s.fattura_riferimento || "",
      note: s.note || ""
    });
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    if (!await conferma("Eliminare questo sconto?")) return;
    try {
      await axios.delete(`${API}/sconti-merce/${id}`);
      toast.success("Eliminato");
      fetchSconti();
      fetchRiepilogo();
    } catch (e) {
      toast.error("Errore eliminazione");
    }
  };

  // Totali lista corrente
  const scontiFiltrati = useMemo(() => {
    if (!nascondiNonValorizzati) return sconti;
    return sconti.filter(s => {
      const prodotto = (s.prodotto || "").toLowerCase();
      const isRigaInutile = prodotto.includes("documento di trasporto") ||
        prodotto.includes("riga ausiliaria") ||
        prodotto.includes("scheda di vendita") ||
        (prodotto.includes("omaggio") && (s.valore_totale || 0) === 0) ||
        ((s.cartoni || 0) === 0 && (s.valore_totale || 0) === 0);
      return !isRigaInutile;
    });
  }, [sconti, nascondiNonValorizzati]);

  const totali = useMemo(() => ({
    valore: scontiFiltrati.reduce((s, x) => s + (x.valore_totale || 0), 0),
    cartoni: scontiFiltrati.reduce((s, x) => s + (x.cartoni || 0), 0),
    pezzi: scontiFiltrati.reduce((s, x) => s + (x.pezzi_totali || 0), 0),
  }), [scontiFiltrati]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-3">
            <Gift className="text-emerald-600" size={28} />
            Sconti Merce
          </h2>
          <p className="text-gray-500 mt-1">Prodotti ricevuti come sconto — riepilogo mensile e annuale</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={importaDaFatture}
            disabled={loading}
            className="px-3 py-2 bg-[#5b7a6b] text-white rounded-lg flex items-center gap-2 hover:bg-[#4d6a5c] text-sm"
            data-testid="importa-da-fatture-btn"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Importa da Fatture
          </button>
          <button
            onClick={async () => {
              try {
                const res = await axios.post(`${API}/sconti-merce/valorizza-da-fatture`);
                toast.success(`Valorizzati ${res.data.aggiornati} sconti, ${res.data.non_trovati_in_fattura} non trovati`);
                fetchSconti();
              } catch { toast.error("Errore valorizzazione"); }
            }}
            disabled={loading}
            className="px-3 py-2 bg-amber-500 text-white rounded-lg flex items-center gap-2 hover:bg-amber-600 text-sm"
            data-testid="valorizza-sconti-btn"
          >
            <RefreshCw size={15} /> Valorizza da Fatture
          </button>
          <button
            onClick={() => { setEditingId(null); setForm(formVuoto); setShowModal(true); }}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg flex items-center gap-2 hover:bg-emerald-700 text-sm"
            data-testid="nuovo-sconto-btn"
          >
            <Plus size={16} /> Registra Sconto
          </button>
        </div>
      </div>

      {/* Filtri */}
      <Card className="p-4">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex items-center gap-2">
            <Calendar size={16} className="text-gray-500" />
            <label className="text-sm text-gray-600">Anno:</label>
            <select
              value={filtroAnno}
              onChange={e => setFiltroAnno(parseInt(e.target.value))}
              className="px-3 py-1.5 border rounded-lg text-sm"
            >
              {[annoCorrente - 1, annoCorrente, annoCorrente + 1].map(a => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600">Mese:</label>
            <select
              value={filtroMese}
              onChange={e => setFiltroMese(parseInt(e.target.value))}
              className="px-3 py-1.5 border rounded-lg text-sm"
            >
              <option value={0}>Tutti i mesi</option>
              {MESI.slice(1).map((m, i) => (
                <option key={i + 1} value={i + 1}>{m}</option>
              ))}
            </select>
          </div>

          {/* Filtro non valorizzati */}
          <label className="flex items-center gap-2 cursor-pointer ml-2">
            <input
              type="checkbox"
              checked={nascondiNonValorizzati}
              onChange={e => setNascondiNonValorizzati(e.target.checked)}
              className="w-4 h-4 accent-emerald-600"
            />
            <span className="text-sm text-gray-600">Nascondi righe inutili</span>
          </label>

          {/* Switch vista */}
          <div className="ml-auto flex gap-1">
            {["lista", "mensile", "fornitori"].map(v => (
              <button
                key={v}
                onClick={() => setVistaAttiva(v)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  vistaAttiva === v ? "bg-emerald-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                {v === "lista" ? "Lista" : v === "mensile" ? "Mensile" : "Per Fornitore"}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-emerald-600">{scontiFiltrati.length}</p>
          <p className="text-sm text-gray-600">Registrazioni</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-[#5b7a6b]">{totali.cartoni.toFixed(0)}</p>
          <p className="text-sm text-gray-600">Cartoni Totali</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-[#7a5f3d]">{totali.pezzi.toFixed(0)}</p>
          <p className="text-sm text-gray-600">Pezzi Totali</p>
        </Card>
        <Card className="p-4 text-center border-2 border-emerald-200 bg-emerald-50">
          <p className="text-3xl font-bold text-emerald-700">€{totali.valore.toFixed(2)}</p>
          <p className="text-sm text-emerald-600 font-medium">Valore Totale</p>
        </Card>
      </div>

      {/* Vista Lista */}
      {vistaAttiva === "lista" && (
        <Card className="overflow-hidden">
          <div className="p-4 border-b flex justify-between items-center">
            <h3 className="font-semibold text-gray-800">
              {filtroMese > 0 ? `${MESI[filtroMese]} ${filtroAnno}` : `Anno ${filtroAnno}`} — {scontiFiltrati.length} righe
            </h3>
            <button onClick={() => { fetchSconti(); fetchRiepilogo(); }} disabled={loading} className="p-2 text-gray-500 hover:text-gray-700">
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left p-3 font-medium">Data</th>
                  <th className="text-left p-3 font-medium">Fornitore</th>
                  <th className="text-left p-3 font-medium">Prodotto</th>
                  <th className="text-center p-3 font-medium">Cartoni</th>
                  <th className="text-center p-3 font-medium">Pezzi/Cart.</th>
                  <th className="text-center p-3 font-medium">Pezzi Tot.</th>
                  <th className="text-right p-3 font-medium">Valore/U.</th>
                  <th className="text-right p-3 font-medium text-emerald-700">Valore Tot.</th>
                  <th className="text-left p-3 font-medium">Fattura Rif.</th>
                  <th className="text-center p-3 font-medium">Azioni</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {scontiFiltrati.map(s => {
                  const daFattura = s.fattura_riferimento && s.fattura_riferimento !== "";
                  const haValore = s.valore_totale > 0;
                  return (
                  <tr key={s.id} className={`hover:bg-gray-50 ${daFattura && !haValore ? "bg-amber-50/40" : ""}`}>
                    <td className="p-3 text-gray-600 whitespace-nowrap">{s.data}</td>
                    <td className="p-3 font-medium text-gray-800 text-xs">{s.fornitore}</td>
                    <td className="p-3 text-gray-700 text-xs">{s.prodotto}</td>
                    <td className="p-3 text-center">{s.cartoni > 0 ? s.cartoni : "-"}</td>
                    <td className="p-3 text-center text-gray-500">{s.pezzi_per_cartone > 0 ? s.pezzi_per_cartone : "-"}</td>
                    <td className="p-3 text-center font-medium">{s.pezzi_totali > 0 ? s.pezzi_totali : "-"}</td>
                    <td className="p-3 text-right text-gray-500">{s.valore_unitario > 0 ? `€${s.valore_unitario.toFixed(2)}` : "-"}</td>
                    <td className="p-3 text-right font-bold">
                      {haValore
                        ? <span className="text-emerald-600">€{s.valore_totale.toFixed(2)}</span>
                        : daFattura
                          ? <span className="text-amber-500 text-xs font-medium">da valorizzare</span>
                          : <span className="text-gray-300">-</span>
                      }
                    </td>
                    <td className="p-3 text-xs">
                      {daFattura
                        ? <span className="inline-flex items-center gap-1 bg-[#f2f6f3] text-[#5b7a6b] border border-[#cfdfd5] px-2 py-0.5 rounded-full font-mono text-[10px]">
                            Fatt. {s.fattura_riferimento}
                          </span>
                        : <span className="text-gray-400">-</span>
                      }
                    </td>
                    <td className="p-3 text-center">
                      <div className="flex justify-center gap-1">
                        <button onClick={() => handleEdit(s)} className="p-1.5 text-[#5b7a6b] hover:bg-[#f2f6f3] rounded">
                          <Edit size={14} />
                        </button>
                        <button onClick={() => handleDelete(s.id)} className="p-1.5 text-red-600 hover:bg-red-50 rounded">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
              {sconti.length > 0 && (
                <tfoot className="bg-emerald-50">
                  <tr>
                    <td colSpan={3} className="p-3 font-bold text-right text-gray-700">TOTALI</td>
                    <td className="p-3 text-center font-bold">{totali.cartoni.toFixed(0)}</td>
                    <td className="p-3"></td>
                    <td className="p-3 text-center font-bold">{totali.pezzi.toFixed(0)}</td>
                    <td className="p-3"></td>
                    <td className="p-3 text-right font-bold text-emerald-700 text-base">€{totali.valore.toFixed(2)}</td>
                    <td colSpan={2}></td>
                  </tr>
                </tfoot>
              )}
            </table>
            {sconti.length === 0 && (
              <p className="text-center text-gray-400 py-12">Nessuno sconto registrato per questo periodo</p>
            )}
          </div>
        </Card>
      )}

      {/* Vista Riepilogo Mensile */}
      {vistaAttiva === "mensile" && riepilogoMensile && (
        <Card className="overflow-hidden">
          <div className="p-4 border-b flex justify-between items-center">
            <h3 className="font-semibold text-gray-800">Riepilogo Mensile — Anno {filtroAnno}</h3>
            <span className="text-sm font-bold text-emerald-600">
              Totale anno: €{riepilogoMensile.totale_anno.toFixed(2)}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left p-3 font-medium">Mese</th>
                  <th className="text-center p-3 font-medium">Registrazioni</th>
                  <th className="text-center p-3 font-medium">Cartoni</th>
                  <th className="text-center p-3 font-medium">Pezzi</th>
                  <th className="text-center p-3 font-medium">Fornitori</th>
                  <th className="text-right p-3 font-medium text-emerald-700">Valore €</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {riepilogoMensile.mesi.map(m => (
                  <tr
                    key={m.mese}
                    onClick={() => { setFiltroMese(m.mese); setVistaAttiva("lista"); }}
                    className={`cursor-pointer transition-colors ${
                      m.num_righe === 0 ? "text-gray-300" :
                      m.mese === meseCorrente ? "bg-emerald-50 hover:bg-emerald-100 font-medium" :
                      "hover:bg-gray-50"
                    }`}
                  >
                    <td className="p-3">
                      {m.nome_mese}
                      {m.mese === meseCorrente && <span className="ml-2 text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">corrente</span>}
                    </td>
                    <td className="p-3 text-center">{m.num_righe || "-"}</td>
                    <td className="p-3 text-center">{m.cartoni_totali > 0 ? m.cartoni_totali.toFixed(0) : "-"}</td>
                    <td className="p-3 text-center">{m.pezzi_totali > 0 ? m.pezzi_totali.toFixed(0) : "-"}</td>
                    <td className="p-3 text-center">{m.num_fornitori || "-"}</td>
                    <td className={`p-3 text-right font-bold ${m.valore_totale > 0 ? "text-emerald-600" : "text-gray-300"}`}>
                      {m.valore_totale > 0 ? `€${m.valore_totale.toFixed(2)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-emerald-100">
                <tr>
                  <td colSpan={5} className="p-3 font-bold text-right text-gray-700">TOTALE ANNO {filtroAnno}</td>
                  <td className="p-3 text-right font-bold text-emerald-700 text-base">
                    €{riepilogoMensile.totale_anno.toFixed(2)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      )}

      {/* Vista Per Fornitore */}
      {vistaAttiva === "fornitori" && (
        <Card className="overflow-hidden">
          <div className="p-4 border-b">
            <h3 className="font-semibold text-gray-800">
              Riepilogo per Fornitore — {filtroMese > 0 ? `${MESI[filtroMese]} ` : ""}{filtroAnno}
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left p-3 font-medium">Fornitore</th>
                  <th className="text-center p-3 font-medium">Righe</th>
                  <th className="text-center p-3 font-medium">Prodotti Diversi</th>
                  <th className="text-center p-3 font-medium">Cartoni Tot.</th>
                  <th className="text-center p-3 font-medium">Pezzi Tot.</th>
                  <th className="text-right p-3 font-medium text-emerald-700">Valore Tot.</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {riepilogoFornitori.map((f, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="p-3 font-medium text-gray-800">{f.fornitore}</td>
                    <td className="p-3 text-center">{f.num_righe}</td>
                    <td className="p-3 text-center">{f.num_prodotti}</td>
                    <td className="p-3 text-center">{f.cartoni_totali > 0 ? f.cartoni_totali.toFixed(0) : "-"}</td>
                    <td className="p-3 text-center">{f.pezzi_totali > 0 ? f.pezzi_totali.toFixed(0) : "-"}</td>
                    <td className="p-3 text-right font-bold text-emerald-600">
                      {f.valore_totale > 0 ? `€${f.valore_totale.toFixed(2)}` : "-"}
                    </td>
                  </tr>
                ))}
                {riepilogoFornitori.length === 0 && (
                  <tr><td colSpan={6} className="p-8 text-center text-gray-400">Nessun dato</td></tr>
                )}
              </tbody>
              {riepilogoFornitori.length > 0 && (
                <tfoot className="bg-emerald-50">
                  <tr>
                    <td colSpan={5} className="p-3 font-bold text-right">TOTALE</td>
                    <td className="p-3 text-right font-bold text-emerald-700 text-base">
                      €{riepilogoFornitori.reduce((s, f) => s + f.valore_totale, 0).toFixed(2)}
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </Card>
      )}

      {/* Modal Form */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-5 border-b flex justify-between items-center sticky top-0 bg-white">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Gift size={20} className="text-emerald-600" />
                {editingId ? "Modifica Sconto" : "Registra Sconto Merce"}
              </h3>
              <button onClick={() => setShowModal(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Data + Fornitore */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-700">Data *</label>
                  <input
                    type="text"
                    placeholder="gg/mm/aaaa"
                    value={form.data}
                    onChange={e => setForm({ ...form, data: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">Fornitore *</label>
                  <input
                    type="text"
                    list="fornitori-list"
                    value={form.fornitore}
                    onChange={e => setForm({ ...form, fornitore: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                    placeholder="es. VANDEMOORTELE"
                  />
                  <datalist id="fornitori-list">
                    {fornitori.map(f => <option key={f} value={f} />)}
                  </datalist>
                </div>
              </div>

              {/* Prodotto */}
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Prodotto *
                  {prodottiForn.length > 0 && (
                    <span className="ml-2 text-xs text-green-600 font-normal">
                      ({prodottiForn.length} trovati per questo fornitore)
                    </span>
                  )}
                  {form.fornitore && prodottiForn.length === 0 && (
                    <span className="ml-2 text-xs text-gray-400 font-normal">(nessuna fattura trovata)</span>
                  )}
                </label>
                <input
                  type="text"
                  list="prodotti-forn-list"
                  value={form.prodotto}
                  onChange={e => setForm({ ...form, prodotto: e.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                  placeholder={form.fornitore ? "Inizia a digitare il nome..." : "Prima seleziona il fornitore"}
                  disabled={!form.fornitore}
                />
                <datalist id="prodotti-forn-list">
                  {prodottiForn.map((p, i) => <option key={i} value={p} />)}
                </datalist>
                {prodottiForn.length === 0 && form.fornitore && (
                  <p className="text-xs text-amber-600 mt-1">
                    Nessun prodotto trovato nelle fatture. Puoi digitare manualmente.
                  </p>
                )}
              </div>

              {/* Cartoni + Pezzi/Cartone */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-sm font-medium text-gray-700">Cartoni / Colli</label>
                  <input
                    type="text" inputMode="decimal"
                    min="0"
                    step="1"
                    value={form.cartoni}
                    onChange={e => setForm({ ...form, cartoni: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">Pz / Cartone</label>
                  <input
                    type="text" inputMode="decimal"
                    min="0"
                    step="1"
                    value={form.pezzi_per_cartone}
                    onChange={e => setForm({ ...form, pezzi_per_cartone: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">Pezzi Totali</label>
                  <input
                    type="text" inputMode="decimal"
                    min="0"
                    value={form.pezzi_totali || (anteprima.pezziTot > 0 ? anteprima.pezziTot : "")}
                    onChange={e => setForm({ ...form, pezzi_totali: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm bg-gray-50"
                    placeholder={anteprima.pezziTot > 0 ? `${anteprima.pezziTot}` : "auto"}
                  />
                </div>
              </div>

              {/* Valori */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-700">Valore Unitario (€)</label>
                  <input
                    type="text" inputMode="decimal"
                    min="0"
                    step="0.01"
                    value={form.valore_unitario}
                    onChange={e => setForm({ ...form, valore_unitario: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                    placeholder="€ per cartone/pezzo"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">Valore Totale (€)</label>
                  <input
                    type="text" inputMode="decimal"
                    min="0"
                    step="0.01"
                    value={form.valore_totale || (anteprima.valTot > 0 ? anteprima.valTot : "")}
                    onChange={e => setForm({ ...form, valore_totale: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm bg-gray-50"
                    placeholder={anteprima.valTot > 0 ? `€${anteprima.valTot.toFixed(2)}` : "auto"}
                  />
                </div>
              </div>

              {/* Anteprima calcolo */}
              {(anteprima.pezziTot > 0 || anteprima.valTot > 0) && (
                <div className="p-3 bg-emerald-50 border border-emerald-100 rounded-lg flex justify-between text-sm">
                  <span className="text-emerald-700">
                    Pezzi calcolati: <strong>{anteprima.pezziTot}</strong>
                  </span>
                  <span className="text-emerald-700 font-bold">
                    Valore: €{anteprima.valTot.toFixed(2)}
                  </span>
                </div>
              )}

              {/* Fattura riferimento + Note */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-700">Fattura Rif.</label>
                  <input
                    type="text"
                    value={form.fattura_riferimento}
                    onChange={e => setForm({ ...form, fattura_riferimento: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                    placeholder="N. fattura collegata"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">Note</label>
                  <input
                    type="text"
                    value={form.note}
                    onChange={e => setForm({ ...form, note: e.target.value })}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                    placeholder="Descrizione aggiuntiva"
                  />
                </div>
              </div>
            </div>

            <div className="p-5 border-t flex justify-end gap-3 sticky bottom-0 bg-white">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg">
                Annulla
              </button>
              <button
                onClick={handleSave}
                className="px-5 py-2 bg-emerald-600 text-white rounded-lg flex items-center gap-2 hover:bg-emerald-700"
                data-testid="salva-sconto-btn"
              >
                <Save size={16} /> Salva
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ScontiMerceView;
