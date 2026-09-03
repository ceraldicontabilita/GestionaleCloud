import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import { apiError } from "../../utils/apiError";
import { API } from "../../utils/constants";
import { isStampaAuto, setStampaAuto } from "../../utils/stampa";
import { Printer, Save, Trash2, Plus, RefreshCw, Network } from "lucide-react";

const REPARTI = [
  { v: "banco", l: "Banco" },
  { v: "magazzino", l: "Magazzino" },
  { v: "rosticceria", l: "Rosticceria" },
  { v: "pasticceria", l: "Pasticceria" },
  { v: "", l: "— nessuno —" },
];

// Tipi di documento che ciascuna stampante gestisce in automatico.
const CATEGORIE_DOC = [
  { v: "etichette", l: "Etichette lotti" },
  { v: "ricette", l: "Schede ricette" },
  { v: "manuale", l: "Manuale / report HACCP" },
  { v: "scontrini", l: "Scontrini / banco" },
  { v: "report", l: "Report giacenze" },
];

export default function StampantiConfigView() {
  const [stampanti, setStampanti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState(null);
  const [autoOn, setAutoOn] = useState(isStampaAuto());

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/stampanti`);
      setStampanti(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error("Errore caricamento: " + apiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  const aggiorna = (id, campo, valore) => {
    setStampanti((prev) => prev.map((s) => (s.id === id ? { ...s, [campo]: valore } : s)));
  };

  const salva = async (s) => {
    setSalvando(s.id);
    try {
      await axios.put(`${API}/stampanti/${s.id}`, {
        nome: s.nome,
        reparto: s.reparto || "",
        indirizzo_rete: (s.indirizzo_rete || "").trim(),
        porta: parseInt(s.porta, 10) || 9100,
        cosa_stampa: s.cosa_stampa || "",
        categorie: s.categorie || [],
        stampante_windows: (s.stampante_windows || "").trim(),
        attiva: s.attiva !== false,
      });
      toast.success("Stampante salvata");
    } catch (e) {
      toast.error("Errore salvataggio: " + apiError(e));
    } finally {
      setSalvando(null);
    }
  };

  const aggiungi = async () => {
    try {
      const { data } = await axios.post(`${API}/stampanti`, {
        nome: "Nuova stampante",
        reparto: "",
        indirizzo_rete: "",
        porta: 9100,
        cosa_stampa: "",
        attiva: true,
      });
      setStampanti((prev) => [...prev, data]);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  const elimina = async (id) => {
    if (!await conferma("Eliminare questa stampante?")) return;
    try {
      await axios.delete(`${API}/stampanti/${id}`);
      setStampanti((prev) => prev.filter((s) => s.id !== id));
      toast.success("Stampante eliminata");
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <Printer className="text-[#5b7a6b]" size={26} />
          <h2 className="text-xl font-bold text-gray-800">Configurazione stampanti</h2>
        </div>
        <button
          onClick={carica}
          className="p-2 text-gray-500 hover:text-[#5b7a6b] rounded-lg hover:bg-gray-100"
          title="Ricarica"
        >
          <RefreshCw size={18} />
        </button>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Indirizzo di rete (IP) e porta della stampante associata a ciascun reparto. La porta
        standard delle stampanti di rete è 9100.
      </p>

      {/* Interruttore stampa automatica (richiede l'agente locale avviato sul PC) */}
      <div className="flex items-center justify-between bg-[#f2f6f3] border border-[#cfdfd5] rounded-xl px-4 py-3 mb-5">
        <div>
          <div className="text-sm font-bold text-[#3f5a4e]">Stampa automatica (agente locale)</div>
          <div className="text-xs text-[#5b7a6b]">
            Se attiva, i documenti vanno alla stampante giusta per categoria senza finestra.
            Richiede il print-agent avviato sul PC del negozio.
          </div>
        </div>
        <button
          type="button"
          onClick={() => { setStampaAuto(!autoOn); setAutoOn(!autoOn); }}
          className={`relative w-12 h-7 rounded-full transition ${autoOn ? "bg-[#4d6a5c]" : "bg-gray-300"}`}
        >
          <span className={`absolute top-1 left-1 w-5 h-5 bg-white rounded-full transition ${autoOn ? "translate-x-5" : ""}`} />
        </button>
      </div>

      {loading ? (
        <div className="text-gray-500 py-10 text-center">Caricamento…</div>
      ) : (
        <div className="space-y-4">
          {stampanti.map((s) => (
            <div key={s.id} className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
              <div className="flex items-start gap-3 mb-3">
                <input
                  value={s.nome || ""}
                  onChange={(e) => aggiorna(s.id, "nome", e.target.value)}
                  className="flex-1 text-lg font-semibold text-gray-800 border-b border-transparent hover:border-gray-300 focus:border-[#5b7a6b] outline-none px-1 py-1"
                  placeholder="Nome stampante"
                />
                <label className="flex items-center gap-2 text-sm text-gray-600 mt-2">
                  <input
                    type="checkbox"
                    checked={s.attiva !== false}
                    onChange={(e) => aggiorna(s.id, "attiva", e.target.checked)}
                  />
                  Attiva
                </label>
                <button
                  onClick={() => elimina(s.id)}
                  className="p-2 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 mt-1"
                  title="Elimina"
                >
                  <Trash2 size={18} />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Reparto</label>
                  <select
                    value={s.reparto || ""}
                    onChange={(e) => aggiorna(s.id, "reparto", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-[#5b7a6b] outline-none"
                  >
                    {REPARTI.map((r) => (
                      <option key={r.v} value={r.v}>
                        {r.l}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Cosa stampa</label>
                  <input
                    value={s.cosa_stampa || ""}
                    onChange={(e) => aggiorna(s.id, "cosa_stampa", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-[#5b7a6b] outline-none"
                    placeholder="es. etichette lotti rosticceria"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1 flex items-center gap-1">
                    <Network size={13} /> Indirizzo di rete (IP)
                  </label>
                  <input
                    value={s.indirizzo_rete || ""}
                    onChange={(e) => aggiorna(s.id, "indirizzo_rete", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:border-[#5b7a6b] outline-none"
                    placeholder="192.168.1.50"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Porta</label>
                  <input
                    type="number"
                    value={s.porta ?? 9100}
                    onChange={(e) => aggiorna(s.id, "porta", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:border-[#5b7a6b] outline-none"
                    placeholder="9100"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-xs font-medium text-gray-500 mb-1 flex items-center gap-1">
                    <Printer size={13} /> Nome stampante in Windows (per la stampa automatica)
                  </label>
                  <input
                    value={s.stampante_windows || ""}
                    onChange={(e) => aggiorna(s.id, "stampante_windows", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-[#5b7a6b] outline-none"
                    placeholder='Esatto come in Windows, es. "EPSON ET-5170 Series"'
                  />
                </div>
              </div>

              <div className="mt-3">
                <label className="block text-xs font-medium text-gray-500 mb-1">
                  Tipi di documento gestiti da questa stampante
                </label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIE_DOC.map((c) => {
                    const sel = (s.categorie || []).includes(c.v);
                    return (
                      <button
                        key={c.v}
                        type="button"
                        onClick={() => {
                          const cur = s.categorie || [];
                          const next = sel ? cur.filter((x) => x !== c.v) : [...cur, c.v];
                          aggiorna(s.id, "categorie", next);
                        }}
                        className={`px-3 py-1.5 rounded-full text-xs font-semibold border ${
                          sel
                            ? "bg-[#4d6a5c] text-white border-[#5b7a6b]"
                            : "bg-white text-gray-600 border-gray-300 hover:border-[#b8d0c2]"
                        }`}
                      >
                        {c.l}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex justify-end mt-3">
                <button
                  onClick={() => salva(s)}
                  disabled={salvando === s.id}
                  className="flex items-center gap-2 bg-[#4d6a5c] hover:bg-[#3f5a4e] text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
                >
                  <Save size={16} />
                  {salvando === s.id ? "Salvataggio…" : "Salva"}
                </button>
              </div>
            </div>
          ))}

          <button
            onClick={aggiungi}
            className="flex items-center gap-2 text-[#5b7a6b] hover:text-[#3f5a4e] font-medium px-2 py-2"
          >
            <Plus size={18} /> Aggiungi stampante
          </button>
        </div>
      )}
    </div>
  );
}
