import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Building2,
  AlertTriangle,
  Ban,
  FileText,
  Check,
  Search,
  RefreshCw,
} from "lucide-react";
import { API } from "../../utils/constants";
import { Card } from "./shared/Card";
import { QualificaBatchPanel } from "./QualificaBatchPanel";
import { SchedeRicevimentoPanel } from "./SchedeRicevimentoPanel";
import { DuplicatiMergePanel } from "./DuplicatiMergePanel";
import RegistroQualificaPanel from "./fornitori/RegistroQualificaPanel";
import SchedaAnagraficaModal from "./fornitori/SchedaAnagraficaModal";
import { CONTATTO_VUOTO, getFornitoreFromHash, setHashFornitore } from "./fornitori/utilsFornitori";

// Pagina Fornitori — orchestratore (refactor 25/07/2026): lo stato e le
// chiamate restano qui, la presentazione pesante è nei moduli ./fornitori/
// (SchedaAnagraficaModal, TrackerColliOmaggio, RegistroQualificaPanel,
// NoteRicevimento) senza cambi di comportamento.
const FornitoriList = ({ fornitori, onRefresh }) => {
  const [search, setSearch] = useState("");
  const [filtroStato, setFiltroStato] = useState("tutti");
  const [selectedFornitore, setSelectedFornitoreState] = useState(null);
  const [anagrafica, setAnagrafica] = useState(null);
  const [loadingAnagrafica, setLoadingAnagrafica] = useState(false);
  const [annoFiltro, setAnnoFiltro] = useState(new Date().getFullYear());
  const [anniDisponibili, setAnniDisponibili] = useState([new Date().getFullYear()]);
  // Stato locale per override immediato (esclusioni/inclusioni in tempo reale)
  const [localOverrides, setLocalOverrides] = useState({});
  // Contatti fornitore (scheda estesa: contatti + condizioni commerciali)
  const [contattoEdit, setContattoEdit] = useState({ ...CONTATTO_VUOTO });
  const [salvandoContatto, setSalvandoContatto] = useState(false);
  // Pannello "qualità dati per le ricette"
  const [qualitaRicette, setQualitaRicette] = useState(null);
  // Registro ricette prodotte coi prodotti del fornitore (tracciabilità inversa)
  const [registroRicette, setRegistroRicette] = useState(null);

  const setSelectedFornitore = (nome) => {
    setSelectedFornitoreState(nome);
    setHashFornitore(nome);
  };

  // Ripristina fornitore da URL al mount
  useEffect(() => {
    const nome = getFornitoreFromHash(fornitori);
    if (nome) loadAnagrafica(nome);
  }, []); // eslint-disable-line

  // Tasto indietro browser
  useEffect(() => {
    const onHash = () => {
      const nome = getFornitoreFromHash(fornitori);
      setSelectedFornitoreState(nome || null);
      if (!nome) setAnagrafica(null);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [fornitori]);

  // Gli override locali vengono applicati ai fornitori
  const fornitoriEffettivi = fornitori.map(f => {
    const ovr = localOverrides[f.nome];
    if (ovr) return { ...f, ...ovr };
    return f;
  });

  const fornitoriAttivi = fornitoriEffettivi.filter(f => !f.escluso && !f.in_attesa).length;
  const fornitoriEsclusi = fornitoriEffettivi.filter(f => f.escluso).length;
  const fornitoriInAttesa = fornitoriEffettivi.filter(f => f.in_attesa).length;

  const filteredFornitori = fornitoriEffettivi.filter(f => {
    const matchSearch = f.nome?.toLowerCase().includes(search.toLowerCase());
    if (!matchSearch) return false;
    if (filtroStato === "attivo") return !f.escluso && !f.in_attesa;
    if (filtroStato === "escluso") return f.escluso;
    if (filtroStato === "in_attesa") return f.in_attesa;
    // "tutti" → esclusi nascosti per default (visibili solo nel tab Esclusi)
    return !f.escluso;
  });

  const loadAnagrafica = async (nome, anno) => {
    setSelectedFornitoreState(nome);
    setHashFornitore(nome);
    setLoadingAnagrafica(true);
    setContattoEdit({ ...CONTATTO_VUOTO });
    setQualitaRicette(null);
    try {
      const resAll = await axios.get(`${API}/fornitori/${encodeURIComponent(nome)}/anagrafica?anno=tutti`);
      const tutteAnni = (resAll.data?.anni_disponibili || []).sort((a, b) => b - a);
      let annoUsato = anno;
      if (!annoUsato) {
        annoUsato = tutteAnni.length > 0 ? tutteAnni[0] : new Date().getFullYear();
      }
      setAnniDisponibili(tutteAnni.length > 0 ? tutteAnni : [new Date().getFullYear()]);
      setAnnoFiltro(annoUsato);
      const res = await axios.get(`${API}/fornitori/${encodeURIComponent(nome)}/anagrafica?anno=${annoUsato}`);
      setAnagrafica(res.data);
      // Carica contatti dall'anagrafica
      try {
        const resC = await axios.get(`${API}/fornitori-anagrafica/${encodeURIComponent(nome)}`);
        const d = resC.data || {};
        setContattoEdit({
          email: d.email || "", cellulare: d.cellulare || "",
          email_verificata: !!d.email_verificata,
          rivendita_colazione: !!d.rivendita_colazione, rivendita_senza_glutine: !!d.rivendita_senza_glutine,
          pec: d.pec || "", sito_web: d.sito_web || "", referente: d.referente || "",
          telefono_fisso: d.telefono_fisso || "", giorni_consegna: d.giorni_consegna || "", giorni_chiusura: d.giorni_chiusura || "",
          ordine_minimo: d.ordine_minimo || "", condizioni_pagamento: d.condizioni_pagamento || "",
          metodo_pagamento: d.metodo_pagamento || "",
          certificazioni: d.certificazioni || "",
          giorni_consegna_settimana: d.giorni_consegna_settimana || [],
          lead_time_giorni: d.lead_time_giorni ?? 1,
          ora_limite_ordine: d.ora_limite_ordine || "",
          procedura_ordini_attiva: d.procedura_ordini_attiva !== false,
          chiusure_programmate: d.chiusure_programmate || [],
        });
      } catch (_) {}
      // Pannello qualità dati per le ricette (non bloccante)
      axios.get(`${API}/fornitori/${encodeURIComponent(nome)}/qualita-ricette`)
        .then(r => setQualitaRicette(r.data))
        .catch(() => setQualitaRicette(null));
      // Registro ricette fatte coi prodotti di questo fornitore (processo
      // inverso della tracciabilità — richiesta Enzo 23/07/2026)
      setRegistroRicette(null);
      axios.get(`${API}/fornitori/${encodeURIComponent(nome)}/ricette-prodotte`)
        .then(r => setRegistroRicette(r.data))
        .catch(() => setRegistroRicette(null));
    } catch (e) {
      toast.error("Errore caricamento anagrafica");
    } finally {
      setLoadingAnagrafica(false);
    }
  };

  const cambiaAnno = (nuovoAnno) => {
    setAnnoFiltro(nuovoAnno);
    if (selectedFornitore) {
      setLoadingAnagrafica(true);
      axios.get(`${API}/fornitori/${encodeURIComponent(selectedFornitore)}/anagrafica?anno=${nuovoAnno}`)
        .then(r => setAnagrafica(r.data))
        .catch(() => toast.error("Errore"))
        .finally(() => setLoadingAnagrafica(false));
    }
  };

  const approvaFornitore = async (nome, includi, piva = "") => {
    try {
      // Aggiornamento ottimistico immediato
      setLocalOverrides(prev => ({
        ...prev,
        [nome]: { escluso: !includi, in_attesa: false }
      }));
      // La P.IVA rende la decisione robusta alle varianti di nome tra fatture
      await axios.post(`${API}/fornitori/approva?nome=${encodeURIComponent(nome)}&includi=${includi}&piva=${encodeURIComponent(piva || "")}`);
      toast.success(includi ? `${nome} incluso tra i fornitori attivi` : `${nome} escluso`);
      onRefresh();
    } catch (e) {
      // Rollback override
      setLocalOverrides(prev => { const n = { ...prev }; delete n[nome]; return n; });
      toast.error("Errore approvazione fornitore");
    }
  };

  // Tri-stato fornitura: completo (magazzino+lotti+ricette) | solo_magazzino | escluso
  const setTipoFornitura = async (nome, tipo) => {
    try {
      setLocalOverrides(prev => ({
        ...prev,
        [nome]: { ...(prev[nome] || {}), tipo_fornitura: tipo, escluso: tipo === "escluso", in_attesa: false },
      }));
      await axios.post(`${API}/fornitori/tipo-fornitura?nome=${encodeURIComponent(nome)}&tipo=${tipo}`);
      toast.success(`${nome}: ${tipo === "completo" ? "magazzino + lotti" : tipo === "solo_magazzino" ? "solo magazzino" : "escluso"}`);
      onRefresh();
    } catch (e) {
      setLocalOverrides(prev => { const n = { ...prev }; delete n[nome]; return n; });
      toast.error("Errore aggiornamento tipo fornitore");
    }
  };

  const salvaScheda = async () => {
    setSalvandoContatto(true);
    try {
      await axios.put(`${API}/fornitori-anagrafica/${encodeURIComponent(selectedFornitore)}`, {
        ...contattoEdit,
        nome: selectedFornitore,
        email_verificata: !!contattoEdit.email_verificata,
        rivendita_colazione: !!contattoEdit.rivendita_colazione,
        rivendita_senza_glutine: !!contattoEdit.rivendita_senza_glutine,
      });
      toast.success(contattoEdit.email_verificata ? "Scheda salvata — email bloccata come verificata" : "Scheda fornitore salvata");
    } catch { toast.error("Errore salvataggio"); }
    finally { setSalvandoContatto(false); }
  };

  return (
    <div className="space-y-4">
      {/* Notifica fornitori in attesa */}
      {fornitoriInAttesa > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="text-amber-600 flex-shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <p className="font-semibold text-amber-800">{fornitoriInAttesa} nuovo/i fornitore/i richiede approvazione</p>
            <p className="text-sm text-amber-700 mt-1">Nuove fatture importate da fornitori mai visti prima.</p>
          </div>
          <div className="flex gap-2 flex-shrink-0">
            <button onClick={async () => {
              try {
                const res = await axios.post(`${API}/fornitori/auto-classifica-horeca`);
                toast.success(`Auto-classificati: ${res.data.inclusi_horeca} HORECA inclusi, ${res.data.esclusi_non_horeca} non-alimentari esclusi`);
                onRefresh();
              } catch { toast.error("Errore auto-classificazione"); }
            }}
              className="px-3 py-1.5 bg-[#5b7a6b] text-white rounded-lg text-xs font-medium hover:bg-[#4d6a5c]">
              Auto-classifica
            </button>
            <button onClick={() => setFiltroStato("in_attesa")}
              className="px-3 py-1.5 bg-amber-500 text-white rounded-lg text-xs font-medium hover:bg-amber-600">
              Vedi
            </button>
          </div>
        </div>
      )}

      <Card>
        <div className="p-4 border-b flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Building2 className="text-[#5b7a6b]" size={24} />
              Gestione Fornitori
            </h3>
            <p className="text-sm text-gray-500 mt-1">
              Gestisci i fornitori: includi, escludi e visualizza la scheda anagrafica
            </p>
          </div>
          <button onClick={onRefresh} className="p-2 text-gray-500 hover:bg-gray-100 rounded-lg">
            <RefreshCw size={18} />
          </button>
        </div>

        {/* Stats */}
        <div className="p-4 bg-gray-50 border-b grid grid-cols-4 gap-4">
          {[
            { label: "Totale", value: fornitori.length, color: "text-[#5b7a6b]", stato: "tutti", tooltip: "Tutti i fornitori registrati" },
            { label: "Attivi", value: fornitoriAttivi, color: "text-green-600", stato: "attivo", tooltip: "Fornitori con fatture attive e qualificati" },
            { label: "In Attesa", value: fornitoriInAttesa, color: "text-amber-600", stato: "in_attesa", tooltip: "In attesa di qualifica — nessuna fattura ricevuta ancora" },
            { label: "Esclusi", value: fornitoriEsclusi, color: "text-red-600", stato: "escluso", tooltip: "Fornitori esclusi manualmente. Le loro fatture vengono saltate durante l'import PEC." },
          ].map(s => (
            <button key={s.stato} onClick={() => setFiltroStato(s.stato === filtroStato ? "tutti" : s.stato)}
              title={s.tooltip}
              className={`text-center p-2 rounded-lg transition-all ${filtroStato === s.stato ? "ring-2 ring-[#5b7a6b] bg-white" : ""}`}>
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-gray-500">{s.label}</p>
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="p-4 border-b">
          <div className="relative">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Cerca fornitore..." data-testid="search-fornitore"
              className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-[#5b7a6b]" />
          </div>
        </div>

        {/* Lista */}
        <div className="divide-y max-h-[500px] overflow-y-auto">
          {filteredFornitori.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <Building2 size={48} className="mx-auto mb-3 opacity-30" />
              <p>Nessun fornitore trovato</p>
              <p className="text-xs mt-1">Importa fatture XML per vedere i fornitori</p>
            </div>
          ) : (
            filteredFornitori.map((f, idx) => (
              <div key={f.nome || idx}
                className={`p-3 transition-colors ${
                  f.in_attesa ? "bg-amber-50" : f.escluso ? "bg-red-50" : "hover:bg-gray-50"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${
                    f.in_attesa ? "bg-amber-100 text-amber-600" :
                    f.escluso ? "bg-red-100 text-red-600" : "bg-[#e8efe9] text-[#5b7a6b]"
                  }`}>
                    {f.in_attesa ? <AlertTriangle size={18} /> : f.escluso ? <Ban size={18} /> : <Building2 size={18} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`font-semibold text-[15px] leading-snug break-words ${f.escluso ? "text-red-700 line-through" : f.in_attesa ? "text-amber-800" : "text-gray-900"}`}>
                      {f.nome}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {f.num_fatture || 0} fatture
                      {f.piva && ` • P.IVA: ${f.piva}`}
                      {f.ultima_fattura && ` • ultima: ${f.ultima_fattura}`}
                    </p>
                  </div>
                </div>

                <div className="flex gap-1.5 flex-wrap justify-end mt-2">
                  <button onClick={() => loadAnagrafica(f.nome)}
                    className="p-1.5 text-[#5b7a6b] hover:bg-[#f2f6f3] rounded" title="Scheda anagrafica">
                    <FileText size={15} />
                  </button>

                  {f.in_attesa && (
                    <>
                      <button onClick={() => approvaFornitore(f.nome, true, f.piva)}
                        className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200 font-medium">
                        <Check size={13} className="inline mr-0.5" />Includi
                      </button>
                      <button onClick={() => approvaFornitore(f.nome, false, f.piva)}
                        className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 font-medium">
                        <Ban size={13} className="inline mr-0.5" />Escludi
                      </button>
                    </>
                  )}

                  {!f.in_attesa && (() => {
                    const tipo = f.tipo_fornitura || (f.escluso ? "escluso" : "completo");
                    const opts = [
                      { v: "completo", l: "Mag. + Lotti", d: "Ingrediente: stock, tracciabilità lotti e ricette" },
                      { v: "solo_magazzino", l: "Solo mag.", d: "Stock/ordini, ma niente lotti né ricette" },
                      { v: "escluso", l: "Escluso", d: "Le sue fatture non vengono importate" },
                    ];
                    const cls = (v, on) => on
                      ? (v === "escluso" ? "bg-red-600 text-white border-red-600" : v === "solo_magazzino" ? "bg-amber-500 text-white border-amber-500" : "bg-green-600 text-white border-green-600")
                      : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50";
                    return opts.map(o => (
                      <button key={o.v} onClick={() => setTipoFornitura(f.nome, o.v)} title={o.d}
                        data-testid={`tipo-${o.v}-${f.nome}`}
                        className={`rounded-md px-2 py-1 text-xs font-bold border transition ${cls(o.v, tipo === o.v)}`}>
                        {o.l}
                      </button>
                    ));
                  })()}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      {/* ── Registro Qualifica Fornitori HACCP ──────────────────────────── */}
      <RegistroQualificaPanel fornitori={fornitori} />

      {/* Modale Anagrafica */}
      <SchedaAnagraficaModal
        selectedFornitore={selectedFornitore}
        anagrafica={anagrafica}
        loadingAnagrafica={loadingAnagrafica}
        anniDisponibili={anniDisponibili}
        annoFiltro={annoFiltro}
        onCambiaAnno={cambiaAnno}
        onClose={() => { setSelectedFornitore(null); setAnagrafica(null); }}
        contattoEdit={contattoEdit}
        setContattoEdit={setContattoEdit}
        salvandoContatto={salvandoContatto}
        onSalvaScheda={salvaScheda}
        qualitaRicette={qualitaRicette}
        registroRicette={registroRicette}
        fornitoriEffettivi={fornitoriEffettivi}
        onSetTipoFornitura={setTipoFornitura}
      />

      {/* ── Qualifica Fornitori Batch ───────────────────────────────────── */}
      <QualificaBatchPanel />

      {/* ── Deduplica Fornitori (stessa P.IVA, nomi diversi) ─────────────── */}
      <DuplicatiMergePanel />

      {/* ── Registro Ricevimento Merci Temperature ─────────────────────── */}
      <SchedeRicevimentoPanel />

      {/* Info Box */}
      <Card className="p-4 bg-amber-50 border-amber-200">
        <div className="flex items-start gap-3">
          <AlertTriangle className="text-amber-600 flex-shrink-0" size={20} />
          <div>
            <p className="font-medium text-amber-800">Come funziona esclusione</p>
            <ul className="text-sm text-amber-700 mt-2 list-disc list-inside">
              <li>I fornitori esclusi non vengono inclusi nel mapping materie prime e nel Food Cost</li>
              <li>Le fatture rimangono nel database ma vengono ignorate nell'analisi</li>
              <li>I nuovi fornitori appaiono "In Attesa" finché non approvi o escludi</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default FornitoriList;
