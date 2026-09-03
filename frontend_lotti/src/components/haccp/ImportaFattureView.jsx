/**
 * ImportaFattureView + ImportDropdown
 * Estratto da App.js
 */
import { useState, useEffect, useRef } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import {
  FileUp, Upload, RefreshCw, CheckCircle, FileText,
  FolderUp, ChevronDown, Trash2
} from "lucide-react";
import Button from "../ui/Button";
import { API, withToken } from "../../utils/constants";
import { useConferma } from "./shared/useConferma";

// ── Componenti UI locali ───────────────────────────────────────────────────────
const Card = ({ children, className = "" }) => (
  <div className={`bg-white rounded-xl shadow-sm border border-gray-100 ${className}`}>{children}</div>
);

const SyncGestionaleCard = ({ onImported }) => {
  const [stato, setStato] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const carica = async () => {
    try {
      const r = await axios.get(`${API}/gestionale-fatture/stato`);
      setStato(r.data || {});
    } catch { setStato({ configurato: false, errore: true }); }
  };
  useEffect(() => { carica(); }, []);

  const syncOra = async () => {
    setSyncing(true);
    try {
      const anno = new Date().getFullYear();
      const r = await axios.post(`${API}/gestionale-fatture/sync?anno=${anno}&limit=1000&anteprima=false`, null, { timeout: 180000 });
      const d = r.data || {};
      if (!d.configurato) toast.error(d.motivo || "Collegamento non configurato");
      else if (d.conflitti?.length || d.errori?.length) {
        toast.error(`Sync completata con ${d.conflitti?.length || 0} conflitti e ${d.errori?.length || 0} errori`);
      } else {
        toast.success(`GestionaleCloud: ${d.importate || 0} nuove, ${d.collegate_esistenti || 0} gia presenti, ${d.gia_ricevute || 0} gia ricevute`);
      }
      await carica();
      if ((d.importate || 0) > 0 && onImported) onImported();
    } catch (e) { toast.error(apiError(e, "Sincronizzazione GestionaleCloud non riuscita")); }
    finally { setSyncing(false); }
  };

  const ok = stato?.configurato;
  return (
    <Card className="p-4 border-[#cfdfd5] bg-[#f7faf8]">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={`w-2.5 h-2.5 rounded-full ${ok ? "bg-green-500" : "bg-amber-500"}`} />
          <div>
            <p className="text-sm font-bold text-gray-800">Fatture da GestionaleCloud</p>
            <p className="text-xs text-gray-500">
              {!stato ? "Controllo collegamento…" : ok
                ? `Collegato · ${stato.ricevute_registrate || 0} fatture registrate · database separati e protetti dai duplicati`
                : "Collegamento non ancora configurato sul server"}
            </p>
            <p className="text-[11px] text-[#5b7a6b] mt-1 font-semibold">
              Importa le fatture in GestionaleCloud: Lotti le riceve automaticamente ogni 15 minuti.
            </p>
          </div>
        </div>
        <Button onClick={syncOra} disabled={syncing || !ok} variant="secondary">
          <RefreshCw className={syncing ? "animate-spin" : ""} size={16} /> Sincronizza ora
        </Button>
      </div>
    </Card>
  );
};

// ── ImportaFatture ─────────────────────────────────────────────────────────────
export const ImportaFatture = ({ onImportComplete, imp, startImport }) => {
  const { conferma, dialogConferma } = useConferma();
  const [files, setFiles]       = useState([]);
  const [uploading, setUploading] = useState(false);
  const [risultato, setRisultato] = useState(null);
  const [fatture, setFatture]   = useState([]);
  // Selettore ANNO in cima (richiesta Enzo 20/07/2026): leggere i dati per anno.
  // Default: anno corrente. "" = tutti gli anni.
  const [anno, setAnno]         = useState(new Date().getFullYear());
  const [anni, setAnni]         = useState([]);
  // Pre-scan fornitori nuovi (PIANO #1): classificare prima di importare
  const [prescanLoading, setPrescanLoading] = useState(false);
  const [prescanOpen, setPrescanOpen] = useState(false);
  const [prescan, setPrescan] = useState([]);        // [{fornitore, piva, stato, tipo_fornitura}]
  const [classif, setClassif] = useState({});        // nome → "completo"|"solo_magazzino"|"escluso"
  const [pendingFiles, setPendingFiles] = useState([]);

  const fetchFatture = async (a = anno) => {
    try {
      // anno selezionato → tutte le fatture di quell'anno; "" → tutto lo storico
      const q = a ? `?anno=${a}` : `?mesi=0`;
      const res = await axios.get(`${API}/fatture${q}`);
      setFatture(res.data || []);
    } catch (e) {
      console.error("Errore fatture:", e);
      setFatture([]);
    }
  };

  // Anni disponibili per il selettore (una volta sola)
  useEffect(() => {
    axios.get(`${API}/fatture/anni`)
      .then(r => setAnni(Array.isArray(r.data) ? r.data : []))
      .catch(() => setAnni([]));
  }, []);
  // Ricarica la lista quando cambia l'anno (copre anche il primo caricamento)
  useEffect(() => {
    fetchFatture();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anno]);

  const handleFileChange = (e) => {
    if (e.target.files) setFiles(Array.from(e.target.files));
  };

  const procediImport = (lista) => {
    startImport(lista, () => {
      const fi = document.getElementById("xml-upload");
      if (fi) fi.value = "";
      fetchFatture();
      if (onImportComplete) onImportComplete();
    });
    setFiles([]);
    toast.success("Importazione avviata — la barra in basso mostra l'avanzamento, anche se cambi pagina");
  };

  const handleUpload = async () => {
    if (files.length === 0) { toast.error("Seleziona almeno un file XML o ZIP"); return; }
    // Pre-scan: i fornitori nuovi vanno classificati PRIMA dell'import, così non
    // entrano grezzi in catalogo/lotti/giacenze. Se la prescan fallisce, non blocca.
    setPrescanLoading(true);
    try {
      const fd = new FormData();
      files.forEach(f => fd.append("files", f));
      const res = await axios.post(`${API}/fatture/prescan-fornitori`, fd, { timeout: 120000 });
      const nuovi = res.data?.da_classificare || [];
      if (nuovi.length > 0) {
        setPendingFiles(files);
        setClassif({});
        setPrescan(nuovi);
        setPrescanOpen(true);
        setPrescanLoading(false);
        return; // l'import parte dal modal dopo la classificazione
      }
    } catch (e) {
      console.warn("prescan fornitori non riuscita, importo comunque", e);
    }
    setPrescanLoading(false);
    procediImport(files);
  };

  // Chiave univoca per riga: il NOME può essere vuoto o duplicato (fatture senza
  // fornitore), quindi includo P.IVA + indice per non far collidere le selezioni.
  const cardId = (p, idx) => `${p.piva || ""}|${p.fornitore || ""}|${idx}`;

  const confermaClassificazioni = async () => {
    // NIENTE blocco: salvo la classificazione SOLO per i fornitori scelti; quelli
    // lasciati senza scelta restano "in attesa" e l'import procede comunque. Prima
    // un solo fornitore non classificato bloccava tutto e impediva di salvare.
    const scelte = prescan
      .map((p, idx) => [p.fornitore, classif[cardId(p, idx)]])
      .filter(([nome, tipo]) => nome && tipo);
    try {
      for (const [nome, tipo] of scelte) {
        await axios.post(`${API}/fornitori/tipo-fornitura?nome=${encodeURIComponent(nome)}&tipo=${tipo}`);
      }
    } catch (e) { toast.error("Errore salvataggio classificazione: " + apiError(e)); return; }
    const inAttesa = prescan.length - scelte.length;
    const lista = pendingFiles;
    setPrescanOpen(false); setPrescan([]); setPendingFiles([]); setClassif({});
    toast.success(
      inAttesa > 0
        ? `${scelte.length} fornitori classificati · ${inAttesa} restano "in attesa"`
        : `${scelte.length} fornitori classificati`
    );
    procediImport(lista);
  };

  const importaSenzaClassificare = () => {
    const lista = pendingFiles;
    setPrescanOpen(false); setPrescan([]); setPendingFiles([]); setClassif({});
    procediImport(lista);
  };

  const handleAggiorna = async () => {
    setUploading(true);
    setRisultato(null);
    try {
      const res = await axios.post(`${API}/aggiorna-materie-da-fatture`);
      toast.success(res.data.message);
      setRisultato({ aggiornamenti: res.data.aggiornamenti, dettagli: res.data.dettagli });
      if (onImportComplete) onImportComplete();
    } catch { toast.error("Errore nell'aggiornamento"); }
    finally { setUploading(false); }
  };

  const handlePuliziaDati = async () => {
    if (!(await conferma("Eliminare le righe spazzatura?", { dettaglio: "Da Materie Prime, Dizionario e Lotti." }))) return;
    setUploading(true);
    try {
      const res = await axios.post(`${API}/pulizia-dati-spazzatura`);
      toast.success(`Pulizia completata: ${res.data.totale} righe eliminate`);
      fetchFatture();
      if (onImportComplete) onImportComplete();
    } catch (e) {
      toast.error("Errore pulizia: " + apiError(e));
    } finally { setUploading(false); }
  };

  const handleDeleteFattura = async (id) => {
    if (!(await conferma("Eliminare questa fattura?"))) return;
    try {
      await axios.delete(`${API}/fatture/${id}`);
      toast.success("Eliminata!");
      fetchFatture();
    } catch { toast.error("Errore"); }
  };

  return (
    <div className="space-y-6">
      {dialogConferma}
      {prescanOpen && (
        <div className="fixed inset-0 z-[120] bg-black/50 flex items-end md:items-center justify-center p-3"
          onClick={() => setPrescanOpen(false)}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[92vh] flex flex-col overflow-hidden"
            onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-800">Fornitori nuovi da classificare</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                {prescan.length} fornitori non ancora classificati in queste fatture. Scegli come trattarli prima di importare.
              </p>
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                <span className="text-[11px] font-semibold text-slate-400 self-center mr-1">Imposta tutti:</span>
                {[["completo", "Completo"], ["solo_magazzino", "Solo magazzino"], ["escluso", "Escludi"]].map(([k, lab]) => (
                  <button key={k}
                    onClick={() => setClassif(Object.fromEntries(prescan.map((p, idx) => [cardId(p, idx), k])))}
                    className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-bold text-slate-600 hover:bg-slate-50">
                    {lab}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
              {prescan.map((p, idx) => {
                const fidKey = cardId(p, idx);
                const sel = classif[fidKey] || "";
                const opt = [
                  { k: "completo", lab: "Completo", sub: "magazzino + lotti + ricette",
                    on: "border-emerald-400 bg-emerald-50 ring-2 ring-emerald-200" },
                  { k: "solo_magazzino", lab: "Solo magazzino", sub: "ordini/magazzino, no lotti/ricette",
                    on: "border-amber-400 bg-amber-50 ring-2 ring-amber-200" },
                  { k: "escluso", lab: "Escludi", sub: "non-merce / da ignorare",
                    on: "border-rose-400 bg-rose-50 ring-2 ring-rose-200" },
                ];
                return (
                  <div key={fidKey} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-800 capitalize truncate">{(p.fornitore || "(senza nome)").toLowerCase()}</span>
                      <span className="text-[10px] text-slate-400 whitespace-nowrap">{p.piva || "no P.IVA"}</span>
                    </div>
                    <div className="grid grid-cols-3 gap-1.5 mt-2">
                      {opt.map(o => (
                        <button key={o.k}
                          onClick={() => setClassif(c => ({ ...c, [fidKey]: o.k }))}
                          className={`rounded-lg px-2 py-2 text-left border transition-all ${
                            sel === o.k ? o.on : "border-slate-200 hover:bg-slate-50"}`}>
                          <div className="text-[12px] font-bold text-slate-700">{o.lab}</div>
                          <div className="text-[10px] text-slate-400 leading-tight">{o.sub}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="px-5 py-3 border-t border-slate-100 flex flex-col gap-2">
              <Button onClick={confermaClassificazioni}>
                <CheckCircle size={18} /> Salva e importa
              </Button>
              <button onClick={importaSenzaClassificare}
                className="text-xs text-slate-500 hover:text-slate-700 py-1">
                Importa senza classificare (restano "in attesa")
              </button>
            </div>
          </div>
        </div>
      )}
      <SyncGestionaleCard onImported={() => { fetchFatture(); if (onImportComplete) onImportComplete(); }} />
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FileUp className="text-[#5b7a6b]" size={24} /> Importazione manuale di emergenza
        </h3>
        <p className="text-sm text-gray-500 mb-4">
          Normalmente importa soltanto da GestionaleCloud. Usa questa sezione solo se una fattura non e presente nel gestionale: XML, ZIP o file .p7m vengono comunque riconosciuti e i doppioni identici sono ignorati.
        </p>
        <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-[#b8d0c2] transition-colors">
          <input type="file" accept=".xml,.zip,.p7m" multiple onChange={handleFileChange} className="hidden" id="xml-upload" />
          <label htmlFor="xml-upload" className="cursor-pointer">
            <Upload className="mx-auto mb-3 text-gray-400" size={40} />
            <p className="text-gray-600 font-medium">Clicca per selezionare file XML o ZIP</p>
            <p className="text-sm text-gray-400">oppure trascina qui i file</p>
          </label>
        </div>
        {files.length > 0 && (
          <div className="mt-4">
            <p className="text-sm font-medium text-gray-700 mb-2">{files.length} file selezionati:</p>
            <div className="flex flex-wrap gap-2">
              {files.map((f, i) => (
                <span key={i} className="px-3 py-1 bg-[#e8efe9] text-[#5b7a6b] rounded-full text-sm">{f.name}</span>
              ))}
            </div>
          </div>
        )}
        <div className="flex gap-3 mt-4 flex-wrap">
          <Button onClick={handleUpload} disabled={(imp && imp.running) || prescanLoading || files.length === 0}>
            {((imp && imp.running) || prescanLoading) ? <RefreshCw className="animate-spin" size={18} /> : <Upload size={18} />}
            {prescanLoading ? "Controllo fornitori…" : ((imp && imp.running) ? "Importazione in corso…" : "Importa Fatture")}
          </Button>
          <Button onClick={handleAggiorna} variant="secondary" disabled={uploading || (imp && imp.running)}>
            <RefreshCw size={18} /> Aggiorna Materie (ultimi 10 giorni)
          </Button>
          <Button onClick={handlePuliziaDati} variant="outline" disabled={uploading || (imp && imp.running)}
            className="border-red-200 text-red-600 hover:bg-red-50">
            <Trash2 size={18} /> Pulizia Dati Spazzatura
          </Button>
        </div>
      </Card>

      {risultato !== null && (
        <Card className="p-6 bg-green-50 border-green-200">
          <h4 className="font-semibold text-green-800 mb-3 flex items-center gap-2">
            <CheckCircle size={20} /> Risultato Importazione
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {[
              { val: risultato.fatture_processate || 0,                              label: "Fatture processate",  col: "text-green-600"  },
              { val: risultato.prodotti_trovati || 0,                                label: "Prodotti trovati",    col: "text-[#5b7a6b]"   },
              { val: risultato.materie_aggiornate || risultato.aggiornamenti || 0,   label: "Materie aggiornate",  col: "text-[#7a5f3d]" },
              { val: risultato.errori?.length || 0,                                  label: "Errori",              col: "text-orange-600" },
            ].map(({ val, label, col }) => (
              <div key={label} className="text-center p-3 bg-white rounded-lg">
                <p className={`text-2xl font-bold ${col}`}>{val}</p>
                <p className="text-xs text-gray-500">{label}</p>
              </div>
            ))}
          </div>
          {risultato.dettagli?.length > 0 && (
            <div className="mb-3">
              <p className="text-sm font-medium text-green-700 mb-2">Dettagli aggiornamenti:</p>
              <div className="max-h-40 overflow-y-auto space-y-1">
                {risultato.dettagli.map((d, i) => (
                  <div key={i} className="text-xs bg-white p-2 rounded">
                    <span className="font-medium">{d.ingrediente}</span>
                    <span className="text-gray-500"> → {d.nuovo_fornitore} ({d.nuova_fattura})</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {risultato.errori?.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-red-700 mb-2">Errori:</p>
              {risultato.errori.map((err, i) => <p key={i} className="text-xs text-red-600">{err}</p>)}
            </div>
          )}
        </Card>
      )}

      <Card>
        <div className="p-4 border-b flex items-center justify-between gap-3 flex-wrap">
          <h4 className="font-semibold flex items-center gap-2">
            <FileText size={20} /> Fatture Importate ({Array.isArray(fatture) ? fatture.length : 0})
          </h4>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <span className="font-medium">Anno</span>
            <select
              value={anno}
              onChange={(e) => setAnno(e.target.value ? Number(e.target.value) : "")}
              className="rounded-lg border border-[#cfdfd5] bg-[#f2f6f3] text-[#3f5a4e] font-semibold px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#b8d0c2]"
              data-testid="fatture-anno-select"
            >
              {Array.from(new Set([...(anni || []), anno].filter(Boolean)))
                .sort((a, b) => b - a)
                .map((y) => <option key={y} value={y}>{y}</option>)}
              <option value="">Tutti gli anni</option>
            </select>
          </label>
        </div>
        <div className="divide-y max-h-96 overflow-y-auto">
          {!Array.isArray(fatture) || fatture.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <FolderUp size={48} className="mx-auto mb-3 opacity-30" />
              <p>Nessuna fattura importata</p>
            </div>
          ) : (
            fatture.map((f, idx) => (
              <div key={f.id || idx} className="p-4 hover:bg-gray-50 flex items-center justify-between">
                <div>
                  <p className="font-medium">{f.fornitore || "N/A"}</p>
                  <p className="text-sm text-gray-500">
                    Fatt. {f.numero_fattura || "N/A"} — {f.data_fattura || "N/A"} — {f.num_prodotti ?? (Array.isArray(f.prodotti) ? f.prodotti.length : 0)} prodotti
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => { const id = f.id || f.numero_fattura; if (id) window.open(withToken(`${API}/fatture/${id}/visualizza`), "_blank"); }}
                    className="px-2.5 py-1.5 text-[#5b7a6b] bg-[#f2f6f3] hover:bg-[#dce8e0] rounded-lg text-xs flex items-center gap-1.5 border border-[#cfdfd5]"
                    data-testid={`visualizza-fattura-${f.id}`}
                  >
                    <FileText size={13} /> {(f.has_xml ?? f.xml_raw) ? "Assosoftware" : "Visualizza"}
                  </button>
                  <button onClick={() => handleDeleteFattura(f.id)} className="p-2 text-red-500 hover:bg-red-50 rounded-lg">
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
};

// ── ImportDropdown ─────────────────────────────────────────────────────────────
export const ImportDropdown = ({ activeTab, onTabChange }) => {
  const [open, setOpen]       = useState(false);
  const [dropPos, setDropPos] = useState({ top: 0, left: 0 });
  const btnRef  = useRef(null);
  const menuRef = useRef(null);
  const isActive = activeTab === "fatture";

  useEffect(() => {
    const handler = (e) => {
      if (btnRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleToggle = () => {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setDropPos({ top: rect.bottom + 4, left: rect.left });
    }
    setOpen(v => !v);
  };

  return (
    <>
      <button ref={btnRef} onClick={handleToggle}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all whitespace-nowrap text-xs ${
          isActive ? "bg-[#5b7a6b] text-white shadow-md" : "bg-white text-gray-600 hover:bg-gray-100 border"
        }`}
        data-testid="import-dropdown-btn"
      >
        <FileUp size={14} />
        Importa
        <ChevronDown size={12} className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div ref={menuRef}
          style={{ position: "fixed", top: dropPos.top, left: dropPos.left, zIndex: 9999 }}
          className="w-44 bg-white border border-gray-200 rounded-xl shadow-xl overflow-hidden"
        >
          {[
            { id: "fatture",    icon: <FileUp size={14} className="text-[#5b7a6b]" />, label: "Fatture XML",  testid: "nav-fatture-xml",   hoverCls: "hover:bg-[#f2f6f3]", activeCls: "bg-[#f2f6f3] text-[#5b7a6b]" },
          ].map((item, i) => (
            <div key={item.id}>
              {i > 0 && <div className="border-t border-gray-100" />}
              <button
                onClick={() => { onTabChange(item.id); setOpen(false); }}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-xs font-medium transition-colors ${item.hoverCls} ${activeTab === item.id ? item.activeCls : "text-gray-700"}`}
                data-testid={item.testid}
              >
                {item.icon} {item.label}
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
};

export default ImportaFatture;
