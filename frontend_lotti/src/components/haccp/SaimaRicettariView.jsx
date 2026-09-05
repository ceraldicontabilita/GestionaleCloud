import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { FileText, Download, ExternalLink, RefreshCw, BookOpen, Trash2 } from "lucide-react";
import { API, withToken } from "../../utils/constants";

const SEZIONI_COLORI = {
  "Ricorrenze":          "bg-[#f2f6f3] border-[#cfdfd5]",
  "Applicazioni Prodotto":"bg-green-50 border-green-200",
  "Ricette":             "bg-[#eef4ef] border-[#cfdfd5]",
  "Aggiornato":          "bg-[#faf5ec] border-[#e6d3ab]",
};

// ── Viewer PDF: apre direttamente in nuova scheda via proxy backend ──
const PdfViewer = ({ ricett, onClose }) => {
  const proxyUrl = `${process.env.REACT_APP_LOTTI_BACKEND_URL}/api/saima/ricettari/pdf-proxy?url=${encodeURIComponent(ricett.url_pdf)}`;

  // Apri subito in nuova scheda
  useEffect(() => {
    window.open(withToken(proxyUrl), "_blank");
  }, [proxyUrl]);

  return (
    <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-lg">
      <div className="flex items-center justify-between p-4 border-b border-gray-100 bg-gray-50">
        <span className="font-semibold text-sm text-gray-700 flex items-center gap-2">
          <FileText size={14} className="text-[#5b7a6b]" />
          {ricett.nome}
        </span>
        <button onClick={onClose} className="text-sm px-3 py-1.5 bg-gray-200 text-gray-600 hover:bg-gray-300 rounded-lg">✕ Chiudi</button>
      </div>
      <div className="p-8 text-center">
        <p className="text-gray-600 mb-4">Il PDF si è aperto in una nuova scheda.</p>
        <div className="flex items-center justify-center gap-3">
          <a href={proxyUrl} target="_blank" rel="noopener noreferrer"
            className="px-4 py-2 bg-[#5b7a6b] text-white rounded-lg text-sm font-medium hover:bg-[#4d6a5c] flex items-center gap-2">
            <ExternalLink size={14} /> Apri di nuovo
          </a>
          <a href={proxyUrl} download={`${ricett.nome}.pdf`}
            className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 flex items-center gap-2">
            <Download size={14} /> Scarica PDF
          </a>
        </div>
      </div>
    </div>
  );
};

export const SaimaRicettariView = () => {
  const [ricettari, setRicettari] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pdfAperto, setPdfAperto] = useState(null);
  const [importando, setImportando] = useState(false);
  const [importEsito, setImportEsito] = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/saima/ricettari`);
      setRicettari(res.data || []);
    } catch {
      setRicettari([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const handleAggiorna = async () => {
    try {
      await axios.post(`${API}/saima/ricettari/aggiorna`);
      setTimeout(carica, 3000);
    } catch { }
  };

  const handleImportaRicette = async () => {
    setImportando(true);
    try {
      const response = await axios.post(`${API}/saima/ricettari/importa-ricette`);
      setImportEsito(response.data);
    } finally {
      setImportando(false);
    }
  };

  // Raggruppa per sezione. MEPA avrà un proprio ricettario separato.
  const gruppi = ricettari.reduce((acc, r) => {
    const sez = r.sezione || "Ricorrenze";
    if (!acc[sez]) acc[sez] = [];
    acc[sez].push(r);
    return acc;
  }, {});

  // Ordine delle sole sezioni SAIMA.
  const ordineSezioni = ["Ricorrenze", "Applicazioni Prodotto", "Ricette", "Aggiornato"]
    .concat(Object.keys(gruppi).filter(s => !["Ricorrenze","Applicazioni Prodotto","Ricette","Aggiornato"].includes(s)));

  if (loading) return (
    <div className="flex items-center justify-center py-16 text-gray-400">
      <RefreshCw className="animate-spin mr-2" size={18} /> Caricamento ricettari...
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-[#5b7a6b] text-white rounded-2xl p-4 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <BookOpen size={20} /> Ricettari SAIMA
          </h2>
          <p className="text-sm opacity-80 mt-0.5">
            {ricettari.length} ricettari ufficiali — le ricette estratte entrano nel ricettario Ceraldi
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleImportaRicette} disabled={importando}
            className="text-sm px-3 py-1.5 bg-white text-[#4d6a5c] hover:bg-[#f2f6f3] rounded-lg flex items-center gap-1.5 transition-colors disabled:opacity-60">
            <BookOpen size={13} /> {importando ? "Inserimento…" : "Inserisci nel ricettario"}
          </button>
          <button onClick={handleAggiorna}
            className="text-sm px-3 py-1.5 bg-white/20 hover:bg-white/30 rounded-lg flex items-center gap-1.5 transition-colors">
            <RefreshCw size={13} /> Aggiorna SAIMA
          </button>
        </div>
      </div>

      {importEsito && <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">Ricettario aggiornato: {importEsito.inserite} nuove ricette, {importEsito.gia_presenti} già presenti. Totale disponibile {importEsito.totale_bundle}.</div>}

      {/* Viewer PDF inline */}
      {pdfAperto && (
        <PdfViewer ricett={pdfAperto} onClose={() => setPdfAperto(null)} />
      )}

      {/* Griglia ricettari per sezione */}
      {ordineSezioni.filter(s => gruppi[s]).map(sezione => (
        <div key={sezione}>
          <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            {sezione}
            <span className="text-gray-300 font-normal">({gruppi[sezione].length})</span>
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
            {gruppi[sezione].map(ricett => (
              <div
                key={ricett.id}
                className={`relative group rounded-xl border-2 ${SEZIONI_COLORI[ricett.sezione] || "bg-gray-50 border-gray-200"} p-4 hover:shadow-md transition-all ${pdfAperto?.id === ricett.id ? "ring-2 ring-[#5b7a6b]" : ""}`}
              >
                <div className="flex items-center justify-center mb-3 h-16">
                  <FileText size={44} className="text-stone-400 opacity-60 group-hover:opacity-90 transition-opacity" />
                </div>
                <p className="text-xs font-bold text-gray-700 text-center leading-tight mb-2 line-clamp-2">
                  {ricett.nome}
                </p>
                {ricett.ricette_importabili > 0 && <p className="mb-2 text-center text-[10px] font-black text-[#5b7a6b]">{ricett.ricette_importabili} ricette estratte</p>}
                <div className="flex gap-1.5 justify-center mt-auto">
                  <button
                    onClick={() => setPdfAperto(pdfAperto?.id === ricett.id ? null : ricett)}
                    className="text-[10px] flex-1 py-1 bg-[#5b7a6b] text-white rounded-lg font-medium hover:bg-[#4d6a5c] flex items-center justify-center gap-0.5"
                    data-testid={`btn-visualizza-pdf-${ricett.id}`}
                  >
                    <FileText size={9} /> Visualizza
                  </button>
                  <a
                    href={withToken(`${process.env.REACT_APP_LOTTI_BACKEND_URL}/api/saima/ricettari/pdf-proxy?url=${encodeURIComponent(ricett.url_pdf)}`)}
                    download={`${ricett.nome}.pdf`}
                    onClick={e => e.stopPropagation()}
                    className="text-[10px] px-2 py-1 bg-white border border-[#b8d0c2] text-[#5b7a6b] rounded-lg font-medium hover:bg-[#f2f6f3] flex items-center"
                    title="Scarica PDF"
                  >
                    <Download size={9} />
                  </a>
                  {ricett.aggiunto_manualmente && (
                    <button onClick={async e => {
                      e.stopPropagation();
                      await axios.delete(`${API}/saima/ricettari/${ricett.id}`);
                      carica();
                    }} className="text-[10px] px-1.5 py-1 bg-red-50 border border-red-200 text-red-500 rounded-lg hover:bg-red-100" title="Elimina">
                      <Trash2 size={9} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {ricettari.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <BookOpen size={48} className="mx-auto mb-4 opacity-30" />
          <p>Nessun ricettario disponibile. Clicca "Aggiorna" per scaricare i ricettari.</p>
        </div>
      )}
    </div>
  );
};

export default SaimaRicettariView;
