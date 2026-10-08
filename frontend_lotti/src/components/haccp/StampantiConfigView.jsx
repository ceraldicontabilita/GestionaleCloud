import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import { apiError } from "../../utils/apiError";
import { API } from "../../utils/constants";
import { stampaRawbt } from "../../utils/stampa";
import { MODI, getModoStampa, setModoStampa, provaStampa } from "../../utils/stampaEpson";
import { Printer, Save, Trash2, Plus, RefreshCw, Network, FlaskConical } from "lucide-react";

const MODALITA = [
  { v: MODI.FINESTRA, l: "Finestra di stampa", d: "Si apre il documento e stampi dal browser." },
  { v: MODI.AGENTE, l: "Agente PC", d: "I documenti vanno in coda e il print-agent sul PC del negozio li stampa." },
  { v: MODI.EPSON, l: "Diretta Epson ePOS", d: "Il tablet stampa da solo sulla Epson di rete, senza PC né finestra." },
  { v: MODI.RAWBT, l: "Tablet Android · RawBT", d: "Richiede RawBT installata e la stampante scelta nell'app (LAN, Bluetooth o USB)." },
];

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
  const [modo, setModo] = useState(getModoStampa());
  const [provando, setProvando] = useState(null);

  const provaRawbt = async () => {
    try {
      const { data } = await axios.get(`${API}/lotti`, { params: { limit: 1 } });
      const l = (Array.isArray(data) ? data : data?.lotti || [])[0];
      if (!l) return toast.error("Nessun lotto per la prova");
      await stampaRawbt(`${API}/stampa/lotto/${encodeURIComponent(l.numero_lotto || l.id)}`);
    } catch (e) {
      toast.error("Prova di stampa fallita: " + apiError(e));
    }
  };

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

  const prova = async (s) => {
    setProvando(s.id);
    try {
      await provaStampa(s.indirizzo_rete);
      toast.success("Prova inviata: controlla che sia uscita la riga e il taglio");
    } catch (e) {
      toast.error(e.message, { duration: 20000 });
    } finally {
      setProvando(null);
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

      {/* Modalità di stampa di QUESTO dispositivo (salvata nel browser) */}
      <div className="bg-[#f2f6f3] border border-[#cfdfd5] rounded-xl px-4 py-3 mb-5">
        <div className="text-sm font-bold text-[#3f5a4e] mb-1">Come stampa questo dispositivo</div>
        <div className="text-xs text-[#5b7a6b] mb-3">La scelta vale solo per questo tablet o PC.</div>
        <div role="radiogroup" aria-label="Modalità di stampa" className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {MODALITA.map((m) => (
            <button
              key={m.v}
              type="button"
              role="radio"
              aria-checked={modo === m.v}
              onClick={() => { setModoStampa(m.v); setModo(m.v); }}
              className={`text-left rounded-lg border px-3 py-3 min-h-[44px] ${
                modo === m.v ? "bg-[#4d6a5c] text-white border-[#3f5a4e]" : "bg-white text-[#2a3329] border-[#e6e0d4]"
              }`}
            >
              <div className="text-sm font-bold">{m.l}</div>
              <div className={`text-xs ${modo === m.v ? "text-white/90" : "text-[#5b7a6b]"}`}>{m.d}</div>
            </button>
          ))}
        </div>
      </div>

      {modo === MODI.RAWBT && <button type="button" onClick={provaRawbt}
        className="mb-4 px-3 min-h-[44px] rounded-lg bg-[#5b7a6b] text-white text-sm font-bold">
        Stampa etichetta di prova · RawBT
      </button>}

      {modo === MODI.EPSON && (
        <div className="bg-[#fffefb] border border-[#e6e0d4] rounded-xl px-4 py-3 mb-5 text-sm text-[#2a3329]">
          <div className="font-bold text-[#3f5a4e] mb-1">Prima volta su questo tablet (una tantum)</div>
          <ol className="list-decimal pl-5 space-y-1">
            <li>Qui sotto inserisci l'IP della stampante (es. quello della Epson TM-T20III) e salva.</li>
            <li>Apri in Chrome <span className="font-mono">https://&lt;IP della stampante&gt;</span>, scegli «Avanzate → Procedi» e accetta il certificato.</li>
            <li>Nella pagina web della stampante controlla che <b>ePOS-Print</b> sia attivo (impostazioni ePOS-Print / Web Config).</li>
            <li>Se Chrome chiede l'accesso alla rete locale, tocca <b>Consenti</b>. Se l'hai negato: lucchetto accanto all'indirizzo → Impostazioni sito → «Dispositivi in rete locale» → Consenti.</li>
            <li>Premi <b>Prova stampa</b>: deve uscire una riga e il taglio.</li>
          </ol>
          <div className="text-xs text-[#8a6f47] mt-2">Se la stampa diretta non riesce, l'app spiega il motivo e offre «Apri PDF»: l'etichetta non si perde.</div>
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 py-10 text-center">Caricamento…</div>
      ) : (
        <div className="space-y-4">
          {stampanti.map((s) => (
            <section key={s.id} aria-label={`Stampante ${s.nome || "senza nome"}`} className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
              <div className="flex items-start gap-3 mb-3">
                <input
                  aria-label={`Nome della stampante ${s.nome || ""}`.trim()}
                  value={s.nome || ""}
                  onChange={(e) => aggiorna(s.id, "nome", e.target.value)}
                  className="flex-1 min-w-0 text-lg font-semibold text-gray-800 border-b border-transparent hover:border-gray-300 focus:border-[#5b7a6b] outline-none px-1 py-1"
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
                  aria-label={`Elimina la stampante ${s.nome || "senza nome"}`}
                >
                  <Trash2 size={18} />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label htmlFor={`st-reparto-${s.id}`} className="block text-xs font-medium text-gray-500 mb-1">Reparto</label>
                  <select
                    id={`st-reparto-${s.id}`}
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
                  <label htmlFor={`st-cosa_stampa-${s.id}`} className="block text-xs font-medium text-gray-500 mb-1">Cosa stampa</label>
                  <input
                    id={`st-cosa_stampa-${s.id}`}
                    value={s.cosa_stampa || ""}
                    onChange={(e) => aggiorna(s.id, "cosa_stampa", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-[#5b7a6b] outline-none"
                    placeholder="es. etichette lotti rosticceria"
                  />
                </div>
                <div>
                  <label htmlFor={`st-indirizzo_rete-${s.id}`} className="block text-xs font-medium text-gray-500 mb-1 flex items-center gap-1">
                    <Network size={13} aria-hidden="true" /> Indirizzo di rete (IP)
                  </label>
                  <input
                    id={`st-indirizzo_rete-${s.id}`}
                    value={s.indirizzo_rete || ""}
                    onChange={(e) => aggiorna(s.id, "indirizzo_rete", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:border-[#5b7a6b] outline-none"
                    placeholder="192.168.1.50"
                  />
                </div>
                <div>
                  <label htmlFor={`st-porta-${s.id}`} className="block text-xs font-medium text-gray-500 mb-1">Porta</label>
                  <input
                    id={`st-porta-${s.id}`}
                    type="number"
                    value={s.porta ?? 9100}
                    onChange={(e) => aggiorna(s.id, "porta", e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:border-[#5b7a6b] outline-none"
                    placeholder="9100"
                  />
                </div>
                <div className="md:col-span-2">
                  <label htmlFor={`st-stampante_windows-${s.id}`} className="block text-xs font-medium text-gray-500 mb-1 flex items-center gap-1">
                    <Printer size={13} aria-hidden="true" /> Nome stampante in Windows (per la stampa automatica)
                  </label>
                  <input
                    id={`st-stampante_windows-${s.id}`}
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

              <div className="flex justify-end gap-2 mt-3">
                <button
                  type="button"
                  onClick={() => prova(s)}
                  disabled={provando === s.id || !(s.indirizzo_rete || "").trim()}
                  className="flex items-center gap-2 border border-[#4d6a5c] text-[#3f5a4e] px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 min-h-[44px]"
                  title="Stampa una riga di prova e taglia (modalità diretta Epson)"
                >
                  <FlaskConical size={16} />
                  {provando === s.id ? "Invio…" : "Prova stampa"}
                </button>
                <button
                  onClick={() => salva(s)}
                  disabled={salvando === s.id}
                  className="flex items-center gap-2 bg-[#4d6a5c] hover:bg-[#3f5a4e] text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
                >
                  <Save size={16} />
                  {salvando === s.id ? "Salvataggio…" : "Salva"}
                </button>
              </div>
            </section>
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
