import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { AlertCircle, Plus, Check, Clock, X, ChevronDown, ChevronUp, RefreshCw, Refrigerator, Snowflake, Printer, ArrowLeftRight } from "lucide-react";
import Button from "../ui/Button";
import { API, withToken } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { getOperatoreNome } from "../../auth";

// Mappa attrezzature suggerite per categoria
const ATTREZZATURE_PER_CATEGORIA = {
  "Frigorifero": [
    "Frigo 1","Frigo 2","Frigo 3","Frigo 4","Frigo 5",
    "Cella Frigo A","Cella Frigo B","Frigorifero Vetrina","Frigorifero Banco"
  ],
  "Congelatore": [
    "Congelatore 1","Congelatore 2","Surgelatore 1","Surgelatore 2",
    "Cella Surgelati","Freezer Banco"
  ],
  "Abbattitore": [
    "Abbattitore 1","Abbattitore 2","Abbattitore Pasticceria","Abbattitore Rosticceria"
  ],
  "Forno": [
    "Forno 1","Forno 2","Forno Pasticceria","Forno Rosticceria","Forno Statico","Forno Ventilato"
  ],
  "Piano cottura": [
    "Piano Cottura 1","Piano Cottura 2","Fornello Gas 1","Fornello Gas 2","Induzione 1"
  ],
  "Friggitrice": [
    "Friggitrice 1","Friggitrice 2","Friggitrice Grande","Friggitrice Piccola"
  ],
  "Impastatrice": [
    "Impastatrice 1","Impastatrice 2","Planetaria 1","Planetaria 2","Sfogliatrice"
  ],
  "Affettatrice": [
    "Affettatrice 1","Affettatrice 2","Affettatrice Prosciutto"
  ],
  "Lavastoviglie": [
    "Lavastoviglie 1","Lavastoviglie 2","Lavastoviglie Industriale"
  ],
  "Tavolo di lavoro": [
    "Tavolo Inox 1","Tavolo Inox 2","Tavolo Marmo","Tavolo Preparazione","Banco Pasticceria"
  ],
  "Vetrina refrigerata": [
    "Vetrina Banco 1","Vetrina Banco 2","Vetrina Esposizione","Vetrina Dolci"
  ],
  "Scaffalatura": [
    "Scaffale Dispensa","Scaffale Magazzino","Scaffale Frigo","Scaffale Secco"
  ],
  "Altro": []
};

const TIPI_ANOMALIA = [
  "Temperatura fuori range",
  "Contaminazione",
  "Attrezzatura in disuso",
  "Malfunzionamento",
  "Guasto",
  "Manutenzione programmata",
  "Pulizia straordinaria",
  "Sostituzione",
  "Altro"
];

const CATEGORIE = [
  "Frigorifero",
  "Congelatore",
  "Tavolo di lavoro",
  "Forno",
  "Piano cottura",
  "Lavastoviglie",
  "Affettatrice",
  "Impastatrice",
  "Friggitrice",
  "Abbattitore",
  "Vetrina refrigerata",
  "Scaffalatura",
  "Altro"
];

const PRIORITA_COLORS = {
  "Alta": "bg-red-100 text-red-800 border-red-200",
  "Media": "bg-yellow-100 text-yellow-800 border-yellow-200",
  "Bassa": "bg-green-100 text-green-800 border-green-200"
};

const STATO_COLORS = {
  "Aperta": "bg-red-50 border-red-300",
  "In corso": "bg-yellow-50 border-yellow-300",
  "Risolta": "bg-green-50 border-green-300",
  "Chiusa": "bg-gray-50 border-gray-300"
};

const ESITI_VERIFICA = [
  "Funzionamento ripristinato e verificato",
  "Parametri rientrati nei limiti HACCP",
  "Attrezzatura esclusa dal servizio in sicurezza",
  "Prodotti coinvolti messi in sicurezza",
  "Pulizia e sanificazione verificate",
  "Intervento tecnico completato con esito conforme",
];

const suggerimentiAzione = (anomalia) => {
  const testo = `${anomalia.tipo || ""} ${anomalia.categoria || ""}`.toLowerCase();
  if (testo.includes("temperatura") || testo.includes("frigor") || testo.includes("congel")) {
    return [
      "Prodotti spostati in un'apparecchiatura conforme",
      "Temperatura regolata e ricontrollata dopo la stabilizzazione",
      "Attrezzatura messa fuori servizio e tecnico contattato",
      "Prodotti non conformi segregati e identificati",
    ];
  }
  if (testo.includes("pulizia") || testo.includes("contamin")) {
    return [
      "Pulizia e sanificazione straordinaria eseguita",
      "Prodotti potenzialmente contaminati segregati",
      "Superficie ricontrollata prima della ripresa dell'attività",
    ];
  }
  if (testo.includes("manutenzione")) {
    return [
      "Manutenzione eseguita come da programma",
      "Componenti usurati sostituiti e funzionamento verificato",
      "Controllo tecnico completato senza ulteriori anomalie",
    ];
  }
  return [
    "Attrezzatura messa fuori servizio e tecnico contattato",
    "Componente riparato o sostituito",
    "Regolazione effettuata e funzionamento verificato",
    "Area resa sicura e attività ripresa dopo il controllo",
  ];
};

function RisoluzioneInline({ anomalia, onCancel, onSaved }) {
  const [azione, setAzione] = useState(anomalia.azione_correttiva || "");
  const [esito, setEsito] = useState(anomalia.esito_verifica || "");
  const [note, setNote] = useState(anomalia.note || "");
  const [saving, setSaving] = useState(false);
  const operatore = getOperatoreNome();

  const salva = async (stato) => {
    if (!azione.trim()) {
      toast.error("Descrivi l'intervento eseguito");
      return;
    }
    if (stato === "Risolta" && !esito.trim()) {
      toast.error("Indica come hai verificato la risoluzione");
      return;
    }
    setSaving(true);
    try {
      await axios.put(`${API}/anomalie/${anomalia.id}`, {
        stato,
        azione_correttiva: azione.trim(),
        esito_verifica: esito.trim(),
        operatore_risoluzione: operatore,
        operatore_presa_in_carico: operatore,
        note: note.trim(),
      });
      toast.success(stato === "Risolta" ? "Anomalia risolta e registrata" : "Intervento salvato in corso");
      onSaved();
    } catch (err) {
      toast.error(apiError(err, "Impossibile salvare l'intervento"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-3 rounded-xl border-2 border-emerald-200 bg-white p-4 space-y-4">
      <div>
        <p className="font-bold text-sm text-gray-900">Metti a posto l'anomalia</p>
        <p className="text-xs text-gray-500 mt-1">
          Operatore registrato: <b>{operatore || "identità del PIN attivo"}</b>
        </p>
      </div>

      <div>
        <label className="block text-xs font-bold text-gray-700 mb-2">Azioni rapide</label>
        <div className="flex flex-wrap gap-2">
          {suggerimentiAzione(anomalia).map((testo) => (
            <button key={testo} type="button" onClick={() => setAzione(testo)}
              className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-100">
              {testo}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs font-bold text-gray-700 mb-1">Intervento eseguito *</label>
        <textarea value={azione} onChange={(e) => setAzione(e.target.value)} rows={3}
          placeholder="Descrivi cosa è stato fatto, eventuali ricambi e messa in sicurezza"
          className="w-full rounded-lg border border-gray-300 p-3 text-sm focus:border-emerald-500 focus:outline-none" />
      </div>

      <div>
        <label className="block text-xs font-bold text-gray-700 mb-1">Verifica finale *</label>
        <select value={esito} onChange={(e) => setEsito(e.target.value)}
          className="w-full rounded-lg border border-gray-300 bg-white p-3 text-sm focus:border-emerald-500 focus:outline-none">
          <option value="">Seleziona l'esito del controllo</option>
          {ESITI_VERIFICA.map((voce) => <option key={voce} value={voce}>{voce}</option>)}
        </select>
      </div>

      <div>
        <label className="block text-xs font-bold text-gray-700 mb-1">Note o riferimento tecnico</label>
        <input value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Es. tecnico, rapporto intervento, ricambio utilizzato"
          className="w-full rounded-lg border border-gray-300 p-3 text-sm focus:border-emerald-500 focus:outline-none" />
      </div>

      <div className="flex flex-wrap gap-2 border-t pt-3">
        <button type="button" disabled={saving} onClick={() => salva("In corso")}
          className="rounded-lg bg-amber-100 px-4 py-2 text-sm font-bold text-amber-800 hover:bg-amber-200 disabled:opacity-50">
          <Clock size={15} className="inline mr-1" /> Salva in corso
        </button>
        <button type="button" disabled={saving} onClick={() => salva("Risolta")}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-50">
          <Check size={15} className="inline mr-1" /> {saving ? "Salvataggio…" : "Conferma risolta"}
        </button>
        <button type="button" disabled={saving} onClick={onCancel}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100">
          Annulla
        </button>
      </div>
    </div>
  );
}

// ── Modale spostamento massivo lotti (Tranche 2 — Intelligenza operativa
// frigoriferi): quando un'attrezzatura va in anomalia, ricalcola IN TEMPO
// REALE i lotti presenti (non lo snapshot salvato alla segnalazione, che
// potrebbe essere superato) e li sposta tutti in blocco, tracciando ogni
// spostamento nel registro movimenti collegato all'anomalia.
function SpostaMassivoModal({ anomalia, onClose, onFatto }) {
  const [lotti, setLotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selezionati, setSelezionati] = useState({});
  const [tipo, setTipo] = useState("frigo");
  const [numero, setNumero] = useState("");
  const [reparto, setReparto] = useState("pasticceria");
  const [motivo, setMotivo] = useState("");
  const [azioneCorrettiva, setAzioneCorrettiva] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/anomalie/${anomalia.id}/lotti-attuali`).then((r) => {
      const l = r.data?.lotti || [];
      setLotti(l);
      const sel = {};
      l.forEach((x) => { sel[x.id] = true; });
      setSelezionati(sel);
    }).catch((e) => toast.error(apiError(e, "Impossibile caricare i lotti attuali"))).finally(() => setLoading(false));
  }, [anomalia.id]);

  const idsSelezionati = Object.entries(selezionati).filter(([, v]) => v).map(([k]) => k);

  const conferma = async () => {
    if (idsSelezionati.length === 0) { toast.error("Seleziona almeno un lotto"); return; }
    if (!numero.trim()) { toast.error("Indica la posizione di destinazione"); return; }
    if (!azioneCorrettiva.trim()) { toast.error("Indica l'azione correttiva HACCP"); return; }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/anomalie/${anomalia.id}/sposta-lotti-massivo`, {
        lotti_ids: idsSelezionati, tipo, numero, reparto, motivo,
        azione_correttiva_haccp: azioneCorrettiva, operatore_nome: getOperatoreNome(),
      });
      toast.success(`${res.data.spostati} lotti spostati`);
      onFatto();
    } catch (e) {
      toast.error(apiError(e, "Spostamento non riuscito"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="p-4 bg-red-600 text-white flex items-center justify-between sticky top-0">
          <h3 className="font-black flex items-center gap-2"><ArrowLeftRight size={18}/> Sposta tutti i lotti</h3>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-gray-600">Da: <b>{anomalia.attrezzatura}</b></p>

          {loading && <p className="text-sm text-gray-400">Carico i lotti presenti...</p>}
          {!loading && lotti.length === 0 && (
            <p className="text-sm text-gray-400">Nessun lotto attivo trovato in questa attrezzatura al momento.</p>
          )}
          {!loading && lotti.length > 0 && (
            <div className="space-y-1 max-h-40 overflow-y-auto border border-gray-200 rounded-lg p-2">
              {lotti.map((l) => (
                <label key={l.id} className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={!!selezionati[l.id]}
                    onChange={(e) => setSelezionati((s) => ({ ...s, [l.id]: e.target.checked }))} />
                  <span className="font-medium">{l.prodotto}</span>
                  <span className="text-gray-400 font-mono">{l.numero_lotto}</span>
                  <span className="ml-auto">{l.quantita} {l.unita_misura || ""}</span>
                </label>
              ))}
            </div>
          )}

          <label className="block text-sm">
            Nuova posizione — tipo
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}
              className="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
              <option value="frigo">Frigorifero</option>
              <option value="congelatore">Congelatore</option>
              <option value="abbattitore">Abbattitore</option>
              <option value="banco">Banco</option>
              <option value="magazzino">Magazzino</option>
            </select>
          </label>
          <label className="block text-sm">
            Apparecchio / dettaglio destinazione
            <input value={numero} onChange={(e) => setNumero(e.target.value)}
              placeholder="es. Frigorifero N°5" className="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          </label>
          <label className="block text-sm">
            Reparto
            <select value={reparto} onChange={(e) => setReparto(e.target.value)}
              className="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
              <option value="pasticceria">Pasticceria</option>
              <option value="rosticceria">Rosticceria</option>
              <option value="bar">Bar</option>
            </select>
          </label>
          <label className="block text-sm">
            Motivo (facoltativo)
            <input value={motivo} onChange={(e) => setMotivo(e.target.value)}
              placeholder="es. guasto in corso" className="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          </label>
          <label className="block text-sm">
            Azione correttiva HACCP (obbligatoria)
            <textarea value={azioneCorrettiva} onChange={(e) => setAzioneCorrettiva(e.target.value)} rows={3}
              placeholder="es. prodotti trasferiti entro 10 minuti, temperatura verificata"
              className="w-full mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none" />
          </label>

          <div className="flex gap-2 pt-2">
            <Button variant="secondary" onClick={onClose} className="flex-1">Annulla</Button>
            <Button variant="danger" onClick={conferma} disabled={saving || loading} className="flex-1">
              {saving ? "Sposto..." : `Sposta ${idsSelezionati.length || ""}`}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

const AnomalieView = () => {
  const [anomalie, setAnomalie] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [filtroStato, setFiltroStato] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [risoluzioneId, setRisoluzioneId] = useState(null);
  const [spostaMassivoAnomalia, setSpostaMassivoAnomalia] = useState(null);
  
  // Form state
  const [nuovaAnomalia, setNuovaAnomalia] = useState({
    attrezzatura: "",
    categoria: "Frigorifero",
    tipo: "Attrezzatura in disuso",
    descrizione: "",
    operatore_segnalazione: "",
    priorita: "Media",
    note: ""
  });

  const fetchAnomalie = useCallback(async () => {
    setLoading(true);
    try {
      let url = `${API}/anomalie/lista`;
      const params = new URLSearchParams();
      if (filtroStato) params.append("stato", filtroStato);
      if (filtroCategoria) params.append("categoria", filtroCategoria);
      if (params.toString()) url += `?${params.toString()}`;
      
      const res = await axios.get(url);
      setAnomalie(res.data);
    } catch (err) {
      toast.error("Errore caricamento anomalie");
    }
    setLoading(false);
  }, [filtroStato, filtroCategoria]);

  useEffect(() => { fetchAnomalie(); }, [fetchAnomalie]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!nuovaAnomalia.attrezzatura || !nuovaAnomalia.descrizione) {
      toast.error("Compila tutti i campi obbligatori");
      return;
    }
    
    try {
      await axios.post(`${API}/anomalie/registra`, nuovaAnomalia);
      toast.success("Anomalia registrata!");
      setShowForm(false);
      setNuovaAnomalia({
        attrezzatura: "",
        categoria: "Frigorifero",
        tipo: "Attrezzatura in disuso",
        descrizione: "",
        operatore_segnalazione: "",
        priorita: "Media",
        note: ""
      });
      fetchAnomalie();
    } catch (err) {
      toast.error("Errore registrazione anomalia");
    }
  };

  const aggiornaStato = async (id, nuovoStato) => {
    try {
      await axios.put(`${API}/anomalie/${id}`, {
        stato: nuovoStato,
        operatore_presa_in_carico: getOperatoreNome(),
      });
      toast.success(`Stato aggiornato a ${nuovoStato}`);
      fetchAnomalie();
    } catch (err) {
      toast.error("Errore aggiornamento");
    }
  };

  // Genera nome attrezzatura basato su categoria
  const generaNomeAttrezzatura = (categoria) => {
    if (categoria === "Frigorifero") {
      return `Frigorifero N°${Math.floor(Math.random() * 12) + 1}`;
    } else if (categoria === "Congelatore") {
      return `Congelatore N°${Math.floor(Math.random() * 12) + 1}`;
    }
    return "";
  };

  const handleCategoriaChange = (cat) => {
    // Resetta attrezzatura quando cambia categoria
    setNuovaAnomalia({
      ...nuovaAnomalia,
      categoria: cat,
      attrezzatura: ""
    });
  };

  // Statistiche
  const aperte = anomalie.filter(a => a.stato === "Aperta" || a.stato === "In corso").length;
  const risolte = anomalie.filter(a => a.stato === "Risolta" || a.stato === "Chiusa").length;

  if (loading) return <div className="text-center py-10"><RefreshCw className="animate-spin mx-auto" /></div>;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm font-semibold text-gray-600">Gestione attrezzature in disuso e non conformità</p>
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="secondary" 
            onClick={() => window.open(withToken(`${API}/anomalie/report-pdf/${new Date().getFullYear()}`), '_blank')}
            data-testid="stampa-report-anomalie-btn"
          >
            <Printer size={16}/> Report PDF
          </Button>
          <Button onClick={() => setShowForm(!showForm)} data-testid="nuova-anomalia-btn">
            <Plus size={16}/> Nuova Anomalia
          </Button>
        </div>
      </div>

      {/* Statistiche */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white border rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-gray-800">{anomalie.length}</div>
          <div className="text-xs text-gray-500">Totale</div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-red-600">{aperte}</div>
          <div className="text-xs text-red-700">Aperte</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-green-600">{risolte}</div>
          <div className="text-xs text-green-700">Risolte</div>
        </div>
      </div>

      {/* Form nuova anomalia */}
      {showForm && (
        <div className="bg-white border rounded-lg p-4">
          <h3 className="font-semibold mb-3">Registra Nuova Anomalia</h3>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Categoria *</label>
                <select
                  value={nuovaAnomalia.categoria}
                  onChange={(e) => handleCategoriaChange(e.target.value)}
                  className="w-full border rounded px-3 py-2 text-sm"
                >
                  {CATEGORIE.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Attrezzatura *</label>
                <input
                  type="text"
                  value={nuovaAnomalia.attrezzatura}
                  onChange={(e) => setNuovaAnomalia({...nuovaAnomalia, attrezzatura: e.target.value})}
                  className="w-full border rounded px-3 py-2 text-sm"
                  placeholder="Nome attrezzatura"
                  list={`attrezzature-${nuovaAnomalia.categoria.replace(/\s/g,'-')}`}
                />
                {/* Datalist contestuale per categoria */}
                <datalist id={`attrezzature-${nuovaAnomalia.categoria.replace(/\s/g,'-')}`}>
                  {(ATTREZZATURE_PER_CATEGORIA[nuovaAnomalia.categoria] || []).map(a => (
                    <option key={a} value={a} />
                  ))}
                </datalist>
                {/* Chips rapide per la categoria selezionata */}
                {(ATTREZZATURE_PER_CATEGORIA[nuovaAnomalia.categoria] || []).length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {(ATTREZZATURE_PER_CATEGORIA[nuovaAnomalia.categoria] || []).slice(0, 6).map(a => (
                      <button
                        key={a}
                        type="button"
                        onClick={() => setNuovaAnomalia({...nuovaAnomalia, attrezzatura: a})}
                        className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                          nuovaAnomalia.attrezzatura === a
                            ? "bg-[#5b7a6b] text-white border-[#5b7a6b]"
                            : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-[#f2f6f3] hover:border-[#b8d0c2]"
                        }`}
                      >
                        {a}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Tipo Anomalia</label>
                <select
                  value={nuovaAnomalia.tipo}
                  onChange={(e) => setNuovaAnomalia({...nuovaAnomalia, tipo: e.target.value})}
                  className="w-full border rounded px-3 py-2 text-sm"
                >
                  {TIPI_ANOMALIA.map(tipo => (
                    <option key={tipo} value={tipo}>{tipo}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Priorità</label>
                <select
                  value={nuovaAnomalia.priorita}
                  onChange={(e) => setNuovaAnomalia({...nuovaAnomalia, priorita: e.target.value})}
                  className="w-full border rounded px-3 py-2 text-sm"
                >
                  <option value="Alta">Alta</option>
                  <option value="Media">Media</option>
                  <option value="Bassa">Bassa</option>
                </select>
              </div>
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-1">Descrizione *</label>
              <textarea
                value={nuovaAnomalia.descrizione}
                onChange={(e) => setNuovaAnomalia({...nuovaAnomalia, descrizione: e.target.value})}
                className="w-full border rounded px-3 py-2 text-sm"
                rows={2}
                placeholder="Descrivi il problema..."
              />
            </div>
            
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Operatore</label>
                <select
                  value={nuovaAnomalia.operatore_segnalazione}
                  onChange={(e) => setNuovaAnomalia({...nuovaAnomalia, operatore_segnalazione: e.target.value})}
                  className="w-full border rounded px-3 py-2 text-sm"
                >
                  <option value="">Seleziona...</option>
                  <option value="Pocci Salvatore">Pocci Salvatore</option>
                  <option value="Vincenzo Ceraldi">Vincenzo Ceraldi</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Note</label>
                <input
                  type="text"
                  value={nuovaAnomalia.note}
                  onChange={(e) => setNuovaAnomalia({...nuovaAnomalia, note: e.target.value})}
                  className="w-full border rounded px-3 py-2 text-sm"
                  placeholder="Note aggiuntive..."
                />
              </div>
            </div>
            
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>
                Annulla
              </Button>
              <Button type="submit">
                Registra Anomalia
              </Button>
            </div>
          </form>
        </div>
      )}

      {/* Filtri */}
      <div className="flex gap-3 items-center">
        <select
          value={filtroStato}
          onChange={(e) => setFiltroStato(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm"
        >
          <option value="">Tutti gli stati</option>
          <option value="Aperta">Aperte</option>
          <option value="In corso">In corso</option>
          <option value="Risolta">Risolte</option>
          <option value="Chiusa">Chiuse</option>
        </select>
        <select
          value={filtroCategoria}
          onChange={(e) => setFiltroCategoria(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm"
        >
          <option value="">Tutte le categorie</option>
          {CATEGORIE.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
        <Button variant="secondary" size="sm" onClick={fetchAnomalie}>
          <RefreshCw size={14}/> Aggiorna
        </Button>
      </div>

      {/* Lista anomalie */}
      <div className="space-y-2">
        {anomalie.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <AlertCircle size={48} className="mx-auto mb-2 opacity-30" />
            <p>Nessuna anomalia registrata</p>
          </div>
        ) : (
          anomalie.map(anomalia => (
            <div 
              key={anomalia.id} 
              className={`bg-white border-2 rounded-lg overflow-hidden ${STATO_COLORS[anomalia.stato] || 'border-gray-200'}`}
            >
              <div 
                className="p-3 cursor-pointer flex items-center justify-between"
                onClick={() => setExpandedId(expandedId === anomalia.id ? null : anomalia.id)}
              >
                <div className="flex items-center gap-3">
                  {anomalia.categoria === "Frigorifero" ? (
                    <Refrigerator className="text-orange-500" size={20}/>
                  ) : anomalia.categoria === "Congelatore" ? (
                    <Snowflake className="text-[#5b7a6b]" size={20}/>
                  ) : (
                    <AlertCircle className="text-gray-500" size={20}/>
                  )}
                  <div>
                    <p className="font-semibold text-sm">{anomalia.attrezzatura}</p>
                    <p className="text-xs text-gray-500">{anomalia.tipo} • {anomalia.data_segnalazione}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${PRIORITA_COLORS[anomalia.priorita]}`}>
                    {anomalia.priorita}
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    anomalia.stato === "Aperta" ? "bg-red-100 text-red-700" :
                    anomalia.stato === "In corso" ? "bg-yellow-100 text-yellow-700" :
                    anomalia.stato === "Risolta" ? "bg-green-100 text-green-700" :
                    "bg-gray-100 text-gray-700"
                  }`}>
                    {anomalia.stato}
                  </span>
                  {expandedId === anomalia.id ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
                </div>
              </div>
              
              {expandedId === anomalia.id && (
                <div className="px-3 pb-3 border-t bg-gray-50">
                  <div className="grid grid-cols-2 gap-3 py-3 text-sm">
                    <div>
                      <p className="text-gray-500 text-xs">Descrizione</p>
                      <p>{anomalia.descrizione}</p>
                    </div>
                    <div>
                      <p className="text-gray-500 text-xs">Segnalato da</p>
                      <p>{anomalia.operatore_segnalazione || "-"}</p>
                    </div>
                    {anomalia.azione_correttiva && (
                      <div>
                        <p className="text-gray-500 text-xs">Azione Correttiva</p>
                        <p>{anomalia.azione_correttiva}</p>
                      </div>
                    )}
                    {anomalia.data_risoluzione && (
                      <div>
                        <p className="text-gray-500 text-xs">Data Risoluzione</p>
                        <p>{anomalia.data_risoluzione}</p>
                      </div>
                    )}
                    {anomalia.esito_verifica && (
                      <div>
                        <p className="text-gray-500 text-xs">Verifica finale</p>
                        <p>{anomalia.esito_verifica}</p>
                      </div>
                    )}
                    {anomalia.operatore_risoluzione && (
                      <div>
                        <p className="text-gray-500 text-xs">Risolto da</p>
                        <p>{anomalia.operatore_risoluzione}</p>
                      </div>
                    )}
                  </div>

                  {/* Lotti coinvolti — mostrati solo per anomalie temperatura frigo */}
                  {(anomalia.lotti_coinvolti || []).length > 0 && (
                    <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                      <p className="text-xs font-bold text-red-700 mb-2 flex items-center gap-1">
                        ⚠ {anomalia.lotti_a_rischio} lotti presenti nel frigo al momento dell'anomalia
                      </p>
                      {anomalia.nota_tracciabilita && (
                        <p className="text-xs text-red-600 mb-2">{anomalia.nota_tracciabilita}</p>
                      )}
                      <div className="space-y-1">
                        {anomalia.lotti_coinvolti.map((l, i) => (
                          <div key={i} className="flex justify-between text-xs bg-white rounded px-2 py-1 border border-red-100">
                            <span className="font-medium text-red-800">{l.prodotto}</span>
                            <span className="text-red-500 font-mono">{l.numero_lotto}</span>
                            <span className="text-red-600">Scade: {l.data_scadenza}</span>
                          </div>
                        ))}
                      </div>
                      {(anomalia.stato === "Aperta" || anomalia.stato === "In corso") && (
                        <button onClick={() => setSpostaMassivoAnomalia(anomalia)}
                          className="mt-2 flex items-center gap-1 px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700">
                          <ArrowLeftRight size={12} /> Sposta tutti i lotti
                        </button>
                      )}
                    </div>
                  )}
                  
                  {/* Azioni */}
                  {(anomalia.stato === "Aperta" || anomalia.stato === "In corso") && (
                    <div className="flex gap-2 pt-2 border-t">
                      {anomalia.stato === "Aperta" && (
                        <button
                          onClick={() => aggiornaStato(anomalia.id, "In corso")}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200"
                        >
                          <Clock size={12}/> Prendi in carico
                        </button>
                      )}
                      <button
                        onClick={() => setRisoluzioneId(
                          risoluzioneId === anomalia.id ? null : anomalia.id
                        )}
                        className="flex items-center gap-1 px-3 py-2 text-xs font-bold bg-green-100 text-green-700 rounded hover:bg-green-200"
                      >
                        <Check size={12}/> Registra intervento e risolvi
                      </button>
                    </div>
                  )}
                  {risoluzioneId === anomalia.id && (
                    <RisoluzioneInline
                      anomalia={anomalia}
                      onCancel={() => setRisoluzioneId(null)}
                      onSaved={() => {
                        setRisoluzioneId(null);
                        fetchAnomalie();
                      }}
                    />
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {spostaMassivoAnomalia && (
        <SpostaMassivoModal anomalia={spostaMassivoAnomalia}
          onClose={() => setSpostaMassivoAnomalia(null)}
          onFatto={() => { setSpostaMassivoAnomalia(null); fetchAnomalie(); }} />
      )}
    </div>
  );
};

export default AnomalieView;
