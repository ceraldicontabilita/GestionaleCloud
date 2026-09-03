import { printHtml } from '../../utils/printHtml';
import { useState } from "react";
import { BookOpen, Download, Printer, Share2, Mail, MessageCircle, FileText } from "lucide-react";
import Button from "../ui/Button";
import { API, withToken } from "../../utils/constants";

const ManualeHACCPView = () => {
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [showShareModal, setShowShareModal] = useState(false);
  const [showViewer, setShowViewer] = useState(false);
  const [manualeHtml, setManualeHtml] = useState("");
  const [loadingManuale, setLoadingManuale] = useState(false);
  const [dataDa, setDataDa] = useState("");
  const [dataA, setDataA] = useState("");
  const [sezioniSelezionate, setSezioniSelezionate] = useState({
    temperature_positive: true,
    temperature_negative: true,
    sanificazione: true,
    disinfestazione: true,
    anomalie: true,
    fornitori_qualificati: true,
    ricevimento_merci: true,
    allergeni: true,
    principi_haccp: true,
    personale: true,
  });

  const anni = [2022, 2023, 2024, 2025, 2026];

  const sezioniStr = Object.entries(sezioniSelezionate)
    .filter(([, v]) => v).map(([k]) => k).join(",");

  const urlManuale = `${API}/manuale-haccp/genera-manuale?anno=${anno}` +
    (dataDa ? `&data_da=${dataDa}` : "") +
    (dataA ? `&data_a=${dataA}` : "") +
    (sezioniStr ? `&sezioni=${sezioniStr}` : "");

  const apriViewer = async () => {
    setLoadingManuale(true);
    setShowViewer(true);
    try {
      // withToken: con AUTH_ENFORCE attivo su Render una fetch senza token
      // riceve 401 e il viewer mostrava il JSON "Autenticazione richiesta"
      // al posto del manuale (l'interceptor axios non copre fetch()).
      const res = await fetch(withToken(urlManuale), { headers: { Accept: "text/html" } });
      if (!res.ok) throw new Error(`Il server ha risposto ${res.status}`);
      const html = await res.text();
      setManualeHtml(html);
    } catch (e) {
      setManualeHtml(`<div style="padding:40px;color:red;font-size:16px;">Errore: ${e.message}</div>`);
    } finally {
      setLoadingManuale(false);
    }
  };

  const stampaDaViewer = () => {
    printHtml(manualeHtml || '');
  };

  const scaricaHtml = () => {
    const blob = new Blob([manualeHtml || ''], { type: "text/html;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `manuale_haccp_${anno}.html`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); document.body.removeChild(a); }, 1000);
  };

  const handleCondividiWhatsApp = () => {
    const messaggio = encodeURIComponent(`Manuale HACCP Ceraldi Group S.R.L. - Anno ${anno}`);
    const url = encodeURIComponent(urlManuale);
    window.open(`https://wa.me/?text=${messaggio}%20${url}`, '_blank');
  };
  
  const handleCondividiEmail = () => {
    const subject = encodeURIComponent(`Manuale HACCP - Anno ${anno}`);
    const body = encodeURIComponent(`Consulta il Manuale HACCP al seguente link:\n\n${urlManuale}`);
    window.location.href = `mailto:?subject=${subject}&body=${body}`;
  };

  // ─── Viewer a schermo intero ─────────────────────────────────────────────
  if (showViewer) {
    return (
      <div style={{ position: "fixed", inset: 0, zIndex: 99999, display: "flex", flexDirection: "column", background: "#fff" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", background: "var(--success)", color: "#fff", flexShrink: 0, gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>
            Manuale di Autocontrollo HACCP — Anno {anno}
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={stampaDaViewer}
              disabled={loadingManuale}
              data-testid="btn-stampa-manuale"
              style={{ padding: "6px 14px", borderRadius: 7, border: "2px solid rgba(255,255,255,0.5)", background: "rgba(255,255,255,0.2)", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
              <Printer size={14} /> Stampa / Salva PDF
            </button>
            <button
              onClick={scaricaHtml}
              disabled={loadingManuale}
              style={{ padding: "6px 14px", borderRadius: 7, border: "2px solid rgba(255,255,255,0.5)", background: "rgba(255,255,255,0.15)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
              <Download size={14} /> Scarica HTML
            </button>
            <button
              onClick={() => { setShowViewer(false); setManualeHtml(""); }}
              style={{ padding: "6px 14px", borderRadius: 7, border: "2px solid rgba(255,255,255,0.5)", background: "rgba(255,255,255,0.15)", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
              ✕ Chiudi
            </button>
          </div>
        </div>
        {loadingManuale ? (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16, color: "#64748b" }}>
            <div style={{ fontSize: 40 }}>⏳</div>
            <p style={{ fontSize: 16, fontWeight: 600 }}>Generazione manuale in corso...</p>
          </div>
        ) : (
          <iframe
            srcDoc={manualeHtml}
            style={{ flex: 1, width: "100%", border: "none" }}
            title="Manuale HACCP"
            sandbox="allow-same-origin allow-scripts"
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <BookOpen className="text-green-600" /> Manuale HACCP
          </h2>
          <p className="text-sm text-gray-500">Manuale di Autocontrollo conforme al Reg. CE 852/2004</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={anno}
            onChange={(e) => setAnno(parseInt(e.target.value))}
            className="border rounded-lg px-3 py-2 text-sm"
          >
            {anni.map(a => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Card Principale */}
      <div className="bg-gradient-to-br from-green-50 to-emerald-100 border-2 border-green-200 rounded-2xl p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="p-4 bg-white rounded-xl shadow-sm">
            <FileText size={48} className="text-green-600" />
          </div>
          <div>
            <h3 className="text-2xl font-bold text-gray-800">Ceraldi Group S.R.L.</h3>
            <p className="text-gray-600">Piazza Carità 14, 80134 Napoli (NA)</p>
            <p className="text-sm text-green-700 font-medium mt-1">Anno di riferimento: {anno}</p>
          </div>
        </div>

        {/* Contenuti del Manuale */}
        <div className="bg-white rounded-xl p-4 mb-6">
          <h4 className="font-semibold text-gray-800 mb-3">📑 Contenuti del Manuale (21 Sezioni)</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Dati Azienda
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> 7 Principi HACCP
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Diagrammi di Flusso
            </div>
            <div className="flex items-center gap-1 p-2 bg-[#f2f6f3] rounded border border-[#cfdfd5]">
              <span className="text-[#5b7a6b]">🌳</span> Albero Decisioni CCP
            </div>
            <div className="flex items-center gap-1 p-2 bg-red-50 rounded border border-red-200">
              <span className="text-red-600">⚠</span> Analisi Pericoli
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Identificazione CCP
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Non Conformità
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Controllo Infestanti
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Approvv. Idrico
            </div>
            <div className="flex items-center gap-1 p-2 bg-orange-50 rounded border border-orange-200">
              <span className="text-orange-600">🚨</span> Procedure Emergenza
            </div>
            <div className="flex items-center gap-1 p-2 bg-[#faf5ec] rounded border border-[#e6d3ab]">
              <span className="text-[#7a5f3d]">🏗️</span> Planimetria Locale
            </div>
            <div className="flex items-center gap-1 p-2 bg-amber-50 rounded border border-amber-200">
              <span className="text-amber-600">⚠</span> Gestione Allergeni
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Rintracciabilità
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Igiene Personale
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Pulizia/Sanificazione
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Detergenti
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Gestione Rifiuti
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Formazione
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Manutenzione
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Operatori
            </div>
            <div className="flex items-center gap-1 p-2 bg-gray-50 rounded">
              <span className="text-green-600">✓</span> Allegati
            </div>
          </div>
        </div>

        {/* Selezione Periodo e Sezioni */}
        <div className="bg-white rounded-xl p-4 mb-4 border border-gray-200">
          <p className="text-sm font-semibold text-gray-700 mb-3">Filtri per la stampa (opzionali)</p>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="text-xs font-semibold text-gray-500">Data da</label>
              <input type="date" value={dataDa} onChange={e => setDataDa(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm mt-1 focus:ring-2 focus:ring-green-400" />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-500">Data a</label>
              <input type="date" value={dataA} onChange={e => setDataA(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm mt-1 focus:ring-2 focus:ring-green-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-500">Sezioni da includere</p>
              <div className="flex gap-2">
                <button onClick={() => setSezioniSelezionate(Object.fromEntries(Object.keys(sezioniSelezionate).map(k => [k, true])))}
                  className="text-xs text-[#5b7a6b] hover:underline">Tutte</button>
                <button onClick={() => setSezioniSelezionate(Object.fromEntries(Object.keys(sezioniSelezionate).map(k => [k, false])))}
                  className="text-xs text-gray-400 hover:underline">Nessuna</button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(sezioniSelezionate).map(([k, v]) => (
                <label key={k} className="flex items-center gap-2 text-xs cursor-pointer select-none">
                  <input type="checkbox" checked={v}
                    onChange={e => setSezioniSelezionate(prev => ({ ...prev, [k]: e.target.checked }))}
                    className="rounded" />
                  <span className="text-gray-700">{k.replace(/_/g, ' ')}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Azioni */}
        <div className="flex flex-wrap gap-3">
          <Button onClick={apriViewer} variant="success" className="flex-1 md:flex-none" data-testid="btn-apri-manuale">
            <Printer size={18} /> Visualizza e Stampa
          </Button>
          <Button onClick={() => setShowShareModal(true)} variant="secondary" className="flex-1 md:flex-none">
            <Share2 size={18} /> Condividi
          </Button>
        </div>
      </div>

      {/* Modal Condivisione */}
      {showShareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowShareModal(false)} />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Share2 className="text-green-600" /> Condividi Manuale HACCP
            </h3>
            
            <div className="space-y-3">
              <button
                onClick={handleCondividiWhatsApp}
                className="w-full flex items-center gap-3 p-4 bg-green-50 hover:bg-green-100 border border-green-200 rounded-xl transition-colors"
              >
                <div className="p-2 bg-green-500 rounded-full">
                  <MessageCircle size={20} className="text-white" />
                </div>
                <div className="text-left">
                  <p className="font-semibold text-gray-800">Condividi su WhatsApp</p>
                  <p className="text-sm text-gray-500">Invia il link via messaggio</p>
                </div>
              </button>
              
              <button
                onClick={handleCondividiEmail}
                className="w-full flex items-center gap-3 p-4 bg-[#f2f6f3] hover:bg-[#dce8e0] border border-[#cfdfd5] rounded-xl transition-colors"
              >
                <div className="p-2 bg-[#5b7a6b] rounded-full">
                  <Mail size={20} className="text-white" />
                </div>
                <div className="text-left">
                  <p className="font-semibold text-gray-800">Invia via Email</p>
                  <p className="text-sm text-gray-500">Apre il client email</p>
                </div>
              </button>
              
              <div className="p-3 bg-gray-100 rounded-lg">
                <p className="text-xs text-gray-500 mb-1">Link diretto:</p>
                <p className="text-sm font-mono text-gray-700 break-all">{urlManuale}</p>
              </div>
            </div>
            
            <button
              onClick={() => setShowShareModal(false)}
              className="mt-4 w-full py-2 text-gray-600 hover:text-gray-800"
            >
              Chiudi
            </button>
          </div>
        </div>
      )}

      {/* Info Normativa */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <h4 className="font-semibold text-amber-800 mb-2">📋 Riferimenti Normativi</h4>
        <ul className="text-sm text-amber-700 space-y-1">
          <li>• <strong>Reg. CE 852/2004</strong> - Igiene dei prodotti alimentari</li>
          <li>• <strong>Reg. CE 178/2002</strong> - Principi generali sicurezza alimentare</li>
          <li>• <strong>D.Lgs. 193/2007</strong> - Attuazione direttive CE sicurezza alimentare</li>
          <li>• <strong>Codex Alimentarius</strong> - Linee guida HACCP</li>
        </ul>
      </div>
    </div>
  );
};

export default ManualeHACCPView;
