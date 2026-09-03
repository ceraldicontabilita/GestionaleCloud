/**
 * LottiList — Gestione lotti di produzione
 * Estratto da App.js per ridurre dimensioni del file principale.
 */
import { useState, useEffect } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { format, addDays } from "date-fns";
import { toast } from "sonner";
import { chiediTesto } from "../../utils/conferma";
import {
  Search, FileText, Printer, Trash2, Layers, Calendar,
  AlertTriangle, PackageX, CheckCircle2, History
} from "lucide-react";
import { API, withToken } from "../../utils/constants";
import { SchedaLottoModal, AzioneModal } from "./shared/SchedaLottoModal";
import { getOperatoreNome } from "../../auth";
// Refactor 25/07/2026: primitivi UI, costanti allergeni e i modali pesanti
// stanno in file dedicati — qui resta l'orchestrazione (stato + chiamate).
import { Badge } from "./lotti/uiLotti";
import { ModalReportHACCP, ModalRegistroASL } from "./lotti/ModaliLotto";
import ModalDettaglioLotto from "./lotti/ModalDettaglioLotto";
import ModalRecallIngrediente from "./lotti/ModalRecallIngrediente";

// 25/07/2026 — tolta la finestra "Genera Nuovo Lotto": il lotto si crea SOLO
// producendo una ricetta (così scarica gli ingredienti e nasce con la sua
// provenienza). Qui era un doppione senza tracciabilità e per giunta
// irraggiungibile, perché il bottone che la apriva non esiste più.
const LottiList = ({
  items, onDelete,
  search, setSearch,
  filtroDataDa, setFiltroDataDa,
  filtroDataA, setFiltroDataA,
  filtroSoloScaduti, setFiltroSoloScaduti,
}) => {
  // Confirm elimina (sostituisce window.confirm)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [selectedLotto, setSelectedLotto] = useState(null);
  const [mostraArchivio, setMostraArchivio] = useState(false);
  const [smaltimentoId, setSmaltimentoId] = useState(null);
  const [smaltendo, setSmaltendo] = useState(false);
  // Cronologia completa / gemello digitale (Tranche 3) — riusa lo stesso
  // modale di CosaUsareOggiView, raggiungibile anche da qui.
  const [schedaLottoId, setSchedaLottoId] = useState(null);
  const [azioneLotto, setAzioneLotto] = useState(null); // { tipo, lotto }
  const [smaltiBatchConfirm, setSmaltiBatchConfirm] = useState(false);
  const [smaltiBatchLoading, setSmaltiBatchLoading] = useState(false);
  const [showRegistroModal, setShowRegistroModal] = useState(false);
  const [dataInizioRegistro, setDataInizioRegistro] = useState(format(addDays(new Date(), -30), "yyyy-MM-dd"));
  const [dataFineRegistro, setDataFineRegistro] = useState(format(new Date(), "yyyy-MM-dd"));
  const [showReportHACCPModal, setShowReportHACCPModal] = useState(false);
  // Attrezzature dinamiche da HACCP
  const [attrezzature, setAttrezzature] = useState({ frigoriferi: [], congelatori: [] });
  useEffect(() => {
    axios.get(`${API}/attrezzature/`).then(r => setAttrezzature(r.data || { frigoriferi: [], congelatori: [] })).catch(() => {});
  }, []);
  const [reportAnno, setReportAnno] = useState(new Date().getFullYear());
  const [reportMese, setReportMese] = useState(new Date().getMonth() + 1);

  // Stato Recall
  const [recallIngrediente, setRecallIngrediente] = useState(null);
  const [recallRisultati, setRecallRisultati] = useState(null);
  const [recallLoading, setRecallLoading] = useState(false);
  const [uniRisultati, setUniRisultati] = useState(null);
  const [uniLoading, setUniLoading] = useState(false);
  const [recallFiltri, setRecallFiltri] = useState({ data_da: "", data_a: "", fornitore: "", frigo: "" });
  const [registrandoRichiamo, setRegistrandoRichiamo] = useState(false);

  const registraRichiamoEseguito = async () => {
    if (!recallRisultati?.lotti?.length) return;
    const motivo = await chiediTesto("Motivo del richiamo (es. allerta fornitore, contaminazione):", { titolo: "Richiamo lotti", pericolo: true, ok: "Registra richiamo" });
    if (motivo === null) return;
    setRegistrandoRichiamo(true);
    try {
      await axios.post(`${API}/lotti/recall/esegui`, {
        ingrediente: recallIngrediente,
        filtri: recallFiltri,
        lotti_ids: recallRisultati.lotti.map((l) => l.id),
      }, { params: { motivo, operatore_nome: getOperatoreNome() } });
      toast.success(`Richiamo registrato su ${recallRisultati.lotti.length} lotti`);
    } catch (e) {
      toast.error("Errore registrazione richiamo: " + apiError(e));
    } finally {
      setRegistrandoRichiamo(false);
    }
  };

  const handleRecallIngrediente = async (testoIngrediente) => {
    setRecallIngrediente(testoIngrediente);
    setRecallRisultati(null);
    setRecallFiltri({ data_da: "", data_a: "", fornitore: "", frigo: "" });
    setRecallLoading(true);
    try {
      const res = await axios.get(`${API}/lotti/recall/cerca`, { params: { ingrediente: testoIngrediente, limit: 200, mesi: 2 } });
      setRecallRisultati(res.data);
    } catch (e) {
      toast.error("Errore ricerca recall: " + apiError(e));
    } finally {
      setRecallLoading(false);
    }
  };

  const handleRecallConFiltri = async () => {
    if (!recallIngrediente) return;
    setRecallLoading(true);
    try {
      const params = { ingrediente: recallIngrediente, limit: 200 };
      if (recallFiltri.data_da) params.data_da = recallFiltri.data_da;
      if (recallFiltri.data_a) params.data_a = recallFiltri.data_a;
      if (recallFiltri.fornitore) params.fornitore = recallFiltri.fornitore;
      if (recallFiltri.frigo) params.frigo = recallFiltri.frigo;
      const res = await axios.get(`${API}/lotti/recall/cerca`, { params });
      setRecallRisultati(res.data);
    } catch (e) {
      toast.error("Errore filtro recall: " + apiError(e));
    } finally {
      setRecallLoading(false);
    }
  };

  const handleStampaRegistroASL = () => {
    const url = `${API}/registro-lotti-asl?data_inizio=${dataInizioRegistro}&data_fine=${dataFineRegistro}`;
    window.open(withToken(url), "_blank");
    setShowRegistroModal(false);
  };

  const handleRegistroTracciabilitaCompleto = async () => {
    try {
      const res = await axios.get(`${API}/vendita-banco/registro-tracciabilita`, {
        params: { data_da: dataInizioRegistro, data_a: dataFineRegistro, limit: 1000 }
      });
      const json = JSON.stringify(res.data, null, 2);
      const blob = new Blob([json], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `tracciabilita_completa_${dataInizioRegistro}_${dataFineRegistro}.json`;
      a.click();
      toast.success("Registro tracciabilità completo scaricato");
      setShowRegistroModal(false);
    } catch { toast.error("Errore export tracciabilità"); }
  };

  const handlePrint = (lotto, conNutrizionali = false) => {
    const id = lotto.numero_lotto || lotto.id;
    const url = `${API}/stampa/lotto/${encodeURIComponent(id)}${conNutrizionali ? "?mostra_nutrizionali=true" : ""}`;
    const win = window.open(withToken(url), "_blank", "width=600,height=900");
    if (!win) toast.error("Popup bloccato dal browser. Consenti i popup per questo sito.");
  };

  const ricalcolaTracciabilita = async () => {
    try {
      const res = await axios.post(`${API}/lotti/ricalcola-tracciabilita?solo_mancanti=true`);
      const { aggiornati = 0, processati = 0 } = res.data || {};
      if (processati === 0) {
        toast.info("Nessun lotto da ricalcolare");
      } else if (aggiornati === 0) {
        toast.info(`${processati} lotti elaborati, ma nessuna provenienza collegabile (materie prime non più in giacenza o ricetta non trovata)`);
      } else {
        toast.success(`Provenienza ricalcolata: ${aggiornati}/${processati} lotti collegati`);
      }
      if (onDelete) onDelete("__refresh__"); // trigger refresh
    } catch {
      toast.error("Errore ricalcolo provenienza");
    }
  };

  // ── Smaltimento lotti scaduti ────────────────────────────────────────────────
  const smaltiLotto = async (lottoId) => {
    setSmaltendo(true);
    try {
      await axios.patch(`${API}/lotti/${lottoId}/smalti?motivo=smaltito_scaduto`);
      toast.success("Lotto smaltito e registrato");
      setSmaltimentoId(null);
      if (onDelete) onDelete("__refresh__"); // Ricarica lista
    } catch {
      toast.error("Errore durante lo smaltimento");
    }
    setSmaltendo(false);
  };

  const smaltiBatchScaduti = async () => {
    setSmaltiBatchLoading(true);
    try {
      const scaduti = items.filter(i => {
        if (i.stato === "smaltito") return false;
        const d = parseScadenza(i.data_scadenza);
        return d && d < new Date();
      });
      if (scaduti.length === 0) { toast.info("Nessun lotto scaduto trovato"); setSmaltiBatchConfirm(false); setSmaltiBatchLoading(false); return; }
      const ids = scaduti.map(s => s.id).filter(Boolean);
      const res = await axios.post(`${API}/lotti/smalti-batch?motivo=smaltito_scaduto`, { ids });
      toast.success(`Smaltiti ${res.data.smaltiti} lotti scaduti`);
      setSmaltiBatchConfirm(false);
      if (onDelete) onDelete("__refresh__"); // Ricarica lista
    } catch {
      toast.error("Errore smaltimento batch");
    }
    setSmaltiBatchLoading(false);
  };

  // Parser data_scadenza (supporta dd/mm/yyyy e yyyy-mm-dd)
  const parseScadenza = (ds) => {
    if (!ds) return null;
    try {
      if (ds.includes("/")) {
        const [dd, mm, yyyy] = ds.split("/");
        return new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd));
      }
      return new Date(ds);
    } catch { return null; }
  };

  const lottiFiltrati_scaduti = items.filter(i => {
    if (i.stato === "smaltito") return false;
    const d = parseScadenza(i.data_scadenza);
    return d && d < new Date();
  });

  return (
    <>
      <div className="space-y-4">
        {/* Header Lotti */}
        <div className="rounded-2xl text-white p-4 sm:p-5" style={{ background: "linear-gradient(135deg,#5b7a6b,#3f5a4e)" }}>
          <div className="flex items-start justify-end gap-3 flex-wrap">
            <div className="flex gap-2 flex-wrap">
              <button onClick={() => setShowReportHACCPModal(true)} className="px-3 py-2 rounded-lg text-sm font-bold inline-flex items-center gap-2" style={{ background: "rgba(255,255,255,.15)", color: "#fff" }}><FileText size={16} /> Report HACCP PDF</button>
              <button onClick={() => setShowRegistroModal(true)} className="px-3 py-2 rounded-lg text-sm font-bold inline-flex items-center gap-2" style={{ background: "rgba(255,255,255,.15)", color: "#fff" }}><FileText size={16} /> Registro ASL</button>
            </div>
          </div>
          <div className="relative mt-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={18} style={{ color: "#cdd9d0" }} />
            <input type="text" placeholder="Cerca lotto, prodotto, fornitore, data..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="search-lotti-input" className="w-full pl-10 pr-4 py-2.5 rounded-lg text-sm text-slate-800 outline-none" />
          </div>
        </div>

        {/* Ricerca ASL estesa: UNA sola barra (quella sopra). Questo bottone usa
            lo STESSO testo digitato e cerca anche per fornitore/data/lotto
            fornitore (server), utile per un richiamo. Prima erano due barre. */}
        <div className="px-1">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={async () => {
                const q = (search || "").trim();
                if (!q) { toast("Scrivi prima cosa cercare nella barra qui sopra"); return; }
                setUniLoading(true);
                try {
                  const r = await axios.get(`${API}/lotti/cerca-universale`, { params: { q, limit: 100 } });
                  setUniRisultati(r.data);
                } catch { toast.error("Errore ricerca"); }
                finally { setUniLoading(false); }
              }}
              className="text-xs font-bold inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
              style={{ background: "#eef3ef", color: "#3f5a4e", border: "1px solid #d4e0d6" }}
            >
              <Search size={14} /> {uniLoading ? "Cerco…" : "Cerca ovunque (anche fornitore, data)"}
            </button>
            {uniRisultati && (
              <button onClick={() => setUniRisultati(null)} className="text-xs text-gray-500 underline">Pulisci risultati</button>
            )}
          </div>
          {uniRisultati && (
            <div className="mt-3">
              <p className="text-xs font-semibold mb-2" style={{ color: "#3f5a4e" }}>
                {uniRisultati.totale} lott{uniRisultati.totale === 1 ? "o" : "i"} per "{uniRisultati.query}"
              </p>
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {uniRisultati.risultati.map((l) => (
                  <div
                    key={l.id}
                    onClick={() => { const full = items.find(x => x.id === l.id); if (full) setSelectedLotto(full); }}
                    className="p-2.5 rounded-lg cursor-pointer"
                    style={{ background: "#fffefb", border: "1px solid #e6e0d4" }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold" style={{ color: "#3f5a4e" }}>{l.numero_lotto}</span>
                      <span className="text-xs" style={{ color: "#6b7669" }}>{l.data_produzione}</span>
                    </div>
                    <p className="text-sm font-semibold mt-1" style={{ color: "#2a3329" }}>{l.prodotto}</p>
                    {l.match_in?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {l.match_in.map((m, i) => (
                          <span key={i} className="text-xs px-1.5 py-0.5 rounded" style={{ background: "#e8efe9", color: "#3f5a4e" }}>
                            {m}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {uniRisultati.totale === 0 && (
                  <p className="text-sm text-center py-4" style={{ color: "#9aa593" }}>Nessun lotto trovato</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Filtri data */}
        <div className="flex items-center gap-3 flex-wrap p-3 bg-white rounded-xl border border-gray-100 shadow-sm">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide shrink-0">Filtra per data produzione:</span>
          <div className="flex items-center gap-2 flex-1 flex-wrap">
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500 whitespace-nowrap">Dal</label>
              <input type="date" value={filtroDataDa || ""} onChange={(e) => setFiltroDataDa && setFiltroDataDa(e.target.value)}
                className="px-2 py-1.5 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-[#5b7a6b]" />
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500 whitespace-nowrap">Al</label>
              <input type="date" value={filtroDataA || ""} onChange={(e) => setFiltroDataA && setFiltroDataA(e.target.value)}
                className="px-2 py-1.5 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-[#5b7a6b]" />
            </div>
            {(filtroDataDa || filtroDataA) && (
              <button onClick={() => { setFiltroDataDa && setFiltroDataDa(""); setFiltroDataA && setFiltroDataA(""); }}
                className="text-xs text-red-500 hover:text-red-700 px-2 py-1 rounded-lg hover:bg-red-50 transition-colors">
                Cancella filtri
              </button>
            )}
          </div>
        </div>

        {/* ── Banner: filtro solo scaduti attivo ────────────────────────────── */}
        {filtroSoloScaduti && (
          <div className="bg-red-100 border border-red-300 rounded-xl px-4 py-2.5 flex items-center gap-3">
            <AlertTriangle size={16} className="text-red-600 flex-shrink-0" />
            <p className="text-sm font-semibold text-red-800 flex-1">
              Stai vedendo solo i lotti scaduti
            </p>
            <button
              onClick={() => setFiltroSoloScaduti && setFiltroSoloScaduti(false)}
              data-testid="btn-rimuovi-filtro-scaduti"
              className="flex-shrink-0 px-3 py-1 bg-red-600 text-white rounded-lg text-xs font-semibold hover:bg-red-700 flex items-center gap-1"
            >
              <CheckCircle2 size={12} /> Mostra tutti
            </button>
          </div>
        )}

        {/* Banner Lotti Scaduti — smaltimento batch */}
        {lottiFiltrati_scaduti.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex items-center gap-3 flex-wrap">
            <AlertTriangle size={18} className="text-red-600 flex-shrink-0" />
            <div className="flex-1 min-w-[180px]">
              <p className="text-sm font-semibold text-red-800">
                {lottiFiltrati_scaduti.length} lott{lottiFiltrati_scaduti.length === 1 ? "o scaduto" : "i scaduti"} da smaltire
              </p>
              <p className="text-xs text-red-600">
                Reg. CE 852/2004 — smaltire formalmente e documentare. Il badge rimane attivo finché non vengono smaltiti.
              </p>
            </div>
            <button
              data-testid="btn-smalti-batch-scaduti"
              onClick={() => setSmaltiBatchConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-xl text-sm font-semibold hover:bg-red-700 transition-all flex-shrink-0"
            >
              <PackageX size={14} /> Smalti Tutti
            </button>
          </div>
        )}

        {/* Banner ricalcola provenienza materie prime */}
        {items.filter(l => !l.lotti_fornitori?.lotti_scalati?.length).length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2 flex items-center gap-3 flex-wrap">
            <AlertTriangle size={16} className="text-amber-600 flex-shrink-0" />
            <p className="text-xs text-amber-800 flex-1 min-w-[180px]">
              {items.filter(l => !l.lotti_fornitori?.lotti_scalati?.length).length} lott{items.filter(l => !l.lotti_fornitori?.lotti_scalati?.length).length === 1 ? "o" : "i"} senza provenienza materie prime collegata (lotti fornitore non agganciati in etichetta)
            </p>
            <button onClick={ricalcolaTracciabilita}
              data-testid="btn-ricalcola-tracciabilita"
              className="flex-shrink-0 px-3 py-1.5 bg-amber-500 text-white rounded-lg text-xs font-semibold hover:bg-amber-600">
              Ricalcola
            </button>
          </div>
        )}

        {/* Conferma smaltimento batch */}
        {smaltiBatchConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/50" onClick={() => setSmaltiBatchConfirm(false)} />
            <div className="relative bg-white rounded-2xl shadow-2xl p-6 max-w-sm w-full text-center">
              <PackageX size={40} className="mx-auto mb-3 text-red-500" />
              <h3 className="text-lg font-bold text-gray-800 mb-1">Smalti {lottiFiltrati_scaduti.length} lotti scaduti?</h3>
              <p className="text-sm text-gray-500 mb-2">Questa operazione documenterà formalmente lo smaltimento di tutti i lotti con data scadenza superata.</p>
              <p className="text-xs text-[#5b7a6b] bg-[#f2f6f3] rounded-lg p-2 mb-5">
                Reg. CE 852/2004 · Data smaltimento e motivo verranno registrati nel sistema
              </p>
              <div className="flex gap-3">
                <button onClick={() => setSmaltiBatchConfirm(false)}
                  className="flex-1 px-4 py-2 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50">
                  Annulla
                </button>
                <button
                  onClick={smaltiBatchScaduti}
                  disabled={smaltiBatchLoading}
                  data-testid="btn-conferma-smalti-batch"
                  className="flex-1 px-4 py-2 bg-red-600 text-white rounded-xl text-sm font-semibold hover:bg-red-700 disabled:opacity-50"
                >
                  {smaltiBatchLoading ? "Smaltimento..." : "Conferma Smaltimento"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Conferma smaltimento singolo */}
        {smaltimentoId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/50" onClick={() => setSmaltimentoId(null)} />
            <div className="relative bg-white rounded-2xl shadow-2xl p-6 max-w-xs w-full text-center">
              <PackageX size={36} className="mx-auto mb-3 text-red-500" />
              <h3 className="text-lg font-bold text-gray-800 mb-1">Smalti lotto?</h3>
              <p className="text-sm text-gray-500 mb-5">Verrà registrato come smaltito con data odierna.</p>
              <div className="flex gap-3">
                <button onClick={() => setSmaltimentoId(null)}
                  className="flex-1 px-4 py-2 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50">
                  Annulla
                </button>
                <button
                  onClick={() => smaltiLotto(smaltimentoId)}
                  disabled={smaltendo}
                  className="flex-1 px-4 py-2 bg-red-600 text-white rounded-xl text-sm font-semibold hover:bg-red-700 disabled:opacity-50"
                >
                  {smaltendo ? "..." : "Smalti"}
                </button>
              </div>
            </div>
          </div>
        )}

        <ModalReportHACCP
          isOpen={showReportHACCPModal}
          onClose={() => setShowReportHACCPModal(false)}
          anno={reportAnno} setAnno={setReportAnno}
          mese={reportMese} setMese={setReportMese}
        />

        <ModalRegistroASL
          isOpen={showRegistroModal}
          onClose={() => setShowRegistroModal(false)}
          dataInizio={dataInizioRegistro} setDataInizio={setDataInizioRegistro}
          dataFine={dataFineRegistro} setDataFine={setDataFineRegistro}
          onStampaRegistro={handleStampaRegistroASL}
          onTracciabilitaCompleta={handleRegistroTracciabilitaCompleto}
        />

        <ModalDettaglioLotto
          lotto={selectedLotto}
          onClose={() => setSelectedLotto(null)}
          onPrint={handlePrint}
          onRecallIngrediente={handleRecallIngrediente}
        />

        <ModalRecallIngrediente
          ingrediente={recallIngrediente}
          risultati={recallRisultati}
          loading={recallLoading}
          filtri={recallFiltri}
          setFiltri={setRecallFiltri}
          onClose={() => { setRecallIngrediente(null); setRecallRisultati(null); }}
          onApplicaFiltri={handleRecallConFiltri}
          onApriLotto={(lotto) => { setRecallIngrediente(null); setRecallRisultati(null); setSelectedLotto(lotto); }}
          onRegistraRichiamo={registraRichiamoEseguito}
          registrandoRichiamo={registrandoRichiamo}
        />

        {/* Modal conferma eliminazione */}
        {confirmDeleteId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/50" onClick={() => setConfirmDeleteId(null)} />
            <div className="relative bg-white rounded-2xl shadow-2xl p-6 max-w-xs w-full mx-4 text-center">
              <Trash2 size={36} className="mx-auto mb-3 text-red-500" />
              <h3 className="text-lg font-bold text-gray-800 mb-1">Eliminare il lotto?</h3>
              <p className="text-sm text-gray-500 mb-5">Questa azione non può essere annullata.</p>
              <div className="flex gap-3">
                <button onClick={() => setConfirmDeleteId(null)}
                  className="flex-1 px-4 py-2 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50">
                  Annulla
                </button>
                <button onClick={() => { onDelete(confirmDeleteId); setConfirmDeleteId(null); }}
                  className="flex-1 px-4 py-2 bg-red-600 text-white rounded-xl text-sm font-semibold hover:bg-red-700">
                  Elimina
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Toggle archivio (lotti scaduti da oltre 30 giorni) */}
        {(() => {
          const archiviatiN = items.filter(i => { const d = parseScadenza(i.data_scadenza); return d && (Date.now() - d.getTime()) > 30 * 86400000; }).length;
          if (!archiviatiN && !mostraArchivio) return null;
          return (
            <div className="flex items-center justify-between gap-2 px-1">
              <span className="text-xs text-gray-400">
                {mostraArchivio ? "Archivio — scaduti da oltre 30 giorni" : `${archiviatiN} in archivio (scaduti da oltre 30gg)`}
              </span>
              <button onClick={() => setMostraArchivio(v => !v)} className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50">
                {mostraArchivio ? "← Lotti attivi" : "🗄 Archivio"}
              </button>
            </div>
          );
        })()}

        {/* Lista lotti — ogni lotto in una card */}
        <div className="space-y-3">
            {(() => {
              // Applica filtro "solo scaduti" se attivo
              const isArchiviato = (i) => {
                const d = parseScadenza(i.data_scadenza);
                return d && (Date.now() - d.getTime()) > 30 * 86400000;
              };
              const q = (search || "").trim().toLowerCase();
              // Lotti recenti: in vista attiva mostra solo quelli prodotti negli ultimi 30 giorni.
              const recente = (i) => {
                const d = parseScadenza(i.data_produzione);
                if (!d) return true; // senza data: non nascondere
                return (Date.now() - d.getTime()) <= 30 * 86400000;
              };
              let lottiDaRenderare = items
                .filter(i => mostraArchivio ? isArchiviato(i) : !isArchiviato(i))
                .filter(i => mostraArchivio || q ? true : recente(i))
                .filter(i => !q || (i.prodotto || "").toLowerCase().includes(q) || (i.numero_lotto || "").toLowerCase().includes(q));
              if (filtroSoloScaduti) {
                lottiDaRenderare = lottiDaRenderare.filter(i => {
                  if (i.stato === "smaltito") return false;
                  const d = parseScadenza(i.data_scadenza);
                  return d && d < new Date();
                });
              }
              // Logica umana: i lotti che scadono PRIMA in cima (prima l'ordine
              // era casuale, com'era arrivato dall'API). Chi non ha scadenza va in fondo.
              lottiDaRenderare = [...lottiDaRenderare].sort((a, b) => {
                const da = parseScadenza(a.data_scadenza), dbb = parseScadenza(b.data_scadenza);
                if (!da && !dbb) return 0;
                if (!da) return 1;
                if (!dbb) return -1;
                return da - dbb;
              });

              if (lottiDaRenderare.length === 0) {
                return (
                  <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-8 text-center text-gray-500">
                    <Layers size={48} className="mx-auto mb-3 opacity-30" />
                    <p>{mostraArchivio ? "Archivio vuoto" : filtroSoloScaduti ? "Nessun lotto scaduto trovato" : q ? "Nessun lotto per la ricerca" : "Nessun lotto trovato"}</p>
                  </div>
                );
              }

              return lottiDaRenderare.map((item) => {
                const scadenza = item.data_scadenza || "";
                const scadenzaDate = scadenza ? (() => {
                  try {
                    if (scadenza.includes("/")) {
                      const [d, m, y] = scadenza.split("/");
                      return new Date(`${y}-${m}-${d}`);
                    }
                    return new Date(scadenza);
                  } catch { return null; }
                })() : null;
                const oggi = new Date();
                const giorniScadenza = scadenzaDate ? Math.ceil((scadenzaDate - oggi) / 86400000) : null;
                const scadutaOggi = giorniScadenza !== null && giorniScadenza <= 0;
                const inScadenza = giorniScadenza !== null && giorniScadenza > 0 && giorniScadenza <= 5;
                // Un lotto bloccato da richiamo era indistinguibile dagli altri
                // nella lista (audit visivo 24/07/2026): bordo e badge dedicati.
                const bloccatoRichiamo = item.stato === "bloccato_richiamo";
                const bordo = bloccatoRichiamo ? "border-red-400"
                  : item.consumato ? "border-gray-200"
                  : scadutaOggi ? "border-red-300"
                  : inScadenza ? "border-amber-300"
                  : "border-emerald-200";

                return (
                  <div key={item.id} className={`bg-white rounded-xl border ${bordo} shadow-sm p-4 hover:shadow-md transition-shadow ${item.consumato ? "opacity-60" : ""}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="cursor-pointer flex-1 min-w-0" onClick={() => setSelectedLotto(item)}>
                        <div className="flex items-center gap-3 flex-wrap">
                          <p className={`font-medium ${item.consumato ? "text-gray-400 line-through" : "text-gray-900"}`}>{item.prodotto}</p>
                          <Badge>Lotto #{item.numero_lotto}</Badge>
                          {item.consumato && (
                            <span className="text-[10px] font-bold bg-gray-200 text-gray-500 px-2 py-0.5 rounded-full uppercase tracking-wide">
                              Esaurito {item.data_consumo ? new Date(item.data_consumo).toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" }) : ""}
                            </span>
                          )}
                          {bloccatoRichiamo && <span className="text-[10px] font-bold bg-red-600 text-white px-2 py-0.5 rounded-full uppercase tracking-wide">Bloccato — richiamo</span>}
                          {scadutaOggi && <span className="text-[10px] font-bold bg-red-100 text-red-700 px-2 py-0.5 rounded-full">SCADUTO</span>}
                          {inScadenza && <span className="text-[10px] font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">Scade tra {giorniScadenza}gg</span>}
                        </div>
                        <div className="flex items-center gap-x-4 gap-y-1 mt-1 text-sm text-gray-500 flex-wrap">
                          <span className="flex items-center gap-1"><Calendar size={14} /> Prod: {item.data_produzione}</span>
                          <span className={`flex items-center gap-1 ${scadutaOggi ? "text-red-600 font-semibold" : inScadenza ? "text-amber-600 font-medium" : ""}`}>
                            <Calendar size={14} /> Scad: {scadenza || <span className="text-gray-300">—</span>}
                          </span>
                        </div>
                        {(() => {
                          const fns = [...new Set(((item.lotti_fornitori?.lotti_scalati) || []).map(x => x.fornitore).filter(Boolean))];
                          if (!fns.length) return null;
                          return (
                            <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                              {fns.slice(0, 3).map((f, idx) => (
                                <span key={idx} className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-full">
                                  🏭 {f}
                                </span>
                              ))}
                              {fns.length > 3 && <span className="text-[11px] text-gray-400">+{fns.length - 3}</span>}
                            </div>
                          );
                        })()}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button onClick={() => setSchedaLottoId(item.id)} className="p-2 text-[#5b7a6b] hover:bg-[#f2f6f3] rounded-lg" title="Cronologia completa / gemello digitale">
                          <History size={18} />
                        </button>
                        <button onClick={() => handlePrint(item)} className="p-2 text-[#5b7a6b] hover:bg-[#f2f6f3] rounded-lg" title="Stampa">
                          <Printer size={18} />
                        </button>
                        {scadutaOggi && item.stato !== "smaltito" && !item.consumato && (
                          <button
                            onClick={() => setSmaltimentoId(item.id)}
                            className="p-2 text-red-500 hover:bg-red-50 rounded-lg"
                            title="Smalti lotto scaduto"
                            data-testid={`btn-smalti-lotto-${item.id}`}
                          >
                            <PackageX size={18} />
                          </button>
                        )}
                        {!item.consumato && (
                          <button onClick={() => setConfirmDeleteId(item.id)} className="p-2 text-red-400 hover:bg-red-50 rounded-lg" title="Elimina" data-testid={`btn-elimina-lotto-${item.id}`}>
                            <Trash2 size={18} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              });
            })()}
        </div>
      </div>

      {schedaLottoId && (
        <SchedaLottoModal lottoId={schedaLottoId} onClose={() => setSchedaLottoId(null)}
          onCambiato={(tipo, lotto) => setAzioneLotto({ tipo, lotto })} />
      )}
      {azioneLotto && (
        <AzioneModal lotto={azioneLotto.lotto} azione={azioneLotto.tipo} attrezzature={attrezzature}
          onClose={() => setAzioneLotto(null)}
          onFatto={() => { setAzioneLotto(null); setSchedaLottoId(null); }} />
      )}
    </>
  );
};

export default LottiList;
