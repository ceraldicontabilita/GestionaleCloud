// FattureList — estratto da FornitoriList.jsx (fase 2 refactoring 24/07/2026)
// Nessun cambio di comportamento: lista fatture del fornitore con filtro anno
// e visualizzatore fattura.
import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
// FIX 25/07/2026: le icone erano rimaste senza import dopo l'estrazione da
// FornitoriList.jsx → ReferenceError "FileText is not defined" appena la
// scheda anagrafica mostrava lo storico fatture.
import { FileText, Eye, Printer, X } from "lucide-react";
import { apiError } from "../../../utils/apiError";
import { API, withToken } from "../../../utils/constants";

const FattureList = ({ fatture }) => {
  const [filtroAnno, setFiltroAnno] = useState("tutti");
  const [doc, setDoc] = useState(null); // { numero, loading } | { numero, html } | { numero, error }

  // Estrai l'anno da date in formato italiano (dd/mm/yyyy) o ISO (yyyy-mm-dd)
  const estraiAnno = (data = "") => {
    if (!data) return null;
    if (data.includes("/")) {
      const parts = data.split("/");
      return parts.length === 3 ? parts[2] : null;
    }
    if (data.includes("-")) {
      return data.substring(0, 4);
    }
    return null;
  };

  // Estrai anni unici dalle fatture
  const anni = [...new Set(
    fatture.map(f => estraiAnno(f.data)).filter(Boolean)
  )].sort((a, b) => b - a);

  const filtrate = filtroAnno === "tutti"
    ? fatture
    : fatture.filter(f => estraiAnno(f.data) === filtroAnno);

  // Visualizzatore fattura stile PDF, IN-APP: fetch HTML via axios (il token JWT
  // viaggia con l'interceptor) e lo mostro in un iframe. Niente window.open su
  // /api: la tab nuova non eredita il token e prende 401 (AUTH_ENFORCE attivo).
  const apriFattura = async (f) => {
    const id = f.id || f.numero;
    if (!id) return;
    setDoc({ numero: f.numero, loading: true });
    try {
      const res = await axios.get(`${API}/fatture/${encodeURIComponent(id)}/visualizza`, { responseType: "text" });
      setDoc({ numero: f.numero, html: res.data });
    } catch (e) {
      setDoc({ numero: f.numero, error: apiError(e, "Impossibile aprire la fattura") });
    }
  };

  const stampaFattura = () => {
    const ifr = document.getElementById("fattura-iframe");
    if (ifr && ifr.contentWindow) ifr.contentWindow.print();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
          <FileText size={14} className="text-[#5b7a6b]" />
          Fatture
          <span className="text-xs text-gray-400 font-normal">({filtrate.length} di {fatture.length})</span>
        </p>
        {/* Filtro anni */}
        <div className="flex gap-1">
          <button onClick={() => setFiltroAnno("tutti")}
            className={`px-2 py-0.5 rounded text-xs font-bold ${filtroAnno === "tutti" ? "bg-[#e8efe9] text-[#5b7a6b]" : "text-gray-400 hover:text-gray-600"}`}>
            Tutte
          </button>
          {anni.map(a => (
            <button key={a} onClick={() => setFiltroAnno(a)}
              className={`px-2 py-0.5 rounded text-xs font-bold ${filtroAnno === a ? "bg-[#e8efe9] text-[#5b7a6b]" : "text-gray-400 hover:text-gray-600"}`}>
              {a}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
        {filtrate.length === 0 ? (
          <p className="text-xs text-gray-400 text-center py-4">Nessuna fattura per questo anno</p>
        ) : filtrate.map((f, i) => (
          <button
            key={i}
            onClick={() => apriFattura(f)}
            className="w-full flex justify-between items-center text-xs text-gray-600 py-1.5 px-2 border-b border-gray-100 hover:bg-[#f2f6f3] hover:text-[#5b7a6b] transition-colors rounded group cursor-pointer"
            data-testid={`fattura-row-${f.numero}`}
          >
            <span className="font-mono font-medium truncate max-w-[100px]">{f.numero?.substring(0, 20)}</span>
            <span className="text-gray-500 font-medium min-w-[70px] text-right">{f.data}</span>
            <span className="text-gray-400 min-w-[50px] text-right">{f.num_prodotti}prd</span>
            <div className="flex items-center gap-1 ml-1">
              {f.has_xml
                ? <span className="text-[10px] bg-green-100 text-green-700 px-1 py-0.5 rounded-full">XML</span>
                : <span className="text-[10px] bg-gray-100 text-gray-400 px-1 py-0.5 rounded-full" title="Fattura da database (senza XML originale)">Imp.</span>}
              <Eye size={12} className="text-stone-400 opacity-0 group-hover:opacity-100" />
            </div>
          </button>
        ))}
      </div>

      {/* Visualizzatore fattura stile PDF */}
      {doc && (
        <div className="fixed inset-0 z-[120] bg-black/60 flex items-center justify-center p-3"
          onClick={() => setDoc(null)}>
          <div className="bg-white rounded-2xl w-full max-w-3xl h-[90vh] flex flex-col overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
              <p className="text-sm font-semibold text-gray-800 flex items-center gap-2 truncate">
                <FileText size={16} className="text-[#5b7a6b]" />
                Fattura {doc.numero}
              </p>
              <div className="flex items-center gap-2 flex-shrink-0">
                {doc.html && (
                  <button onClick={stampaFattura}
                    className="px-3 py-1.5 bg-[#5b7a6b] text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 hover:bg-[#4d6a5c]">
                    <Printer size={14} /> Stampa / PDF
                  </button>
                )}
                <button onClick={() => setDoc(null)} className="p-1.5 text-gray-400 hover:bg-gray-200 rounded-lg">
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="flex-1 bg-gray-100 overflow-hidden">
              {doc.loading && (
                <div className="h-full flex items-center justify-center text-gray-400 text-sm">Caricamento fattura…</div>
              )}
              {doc.error && (
                <div className="h-full flex items-center justify-center text-red-500 text-sm px-6 text-center">{doc.error}</div>
              )}
              {doc.html && (
                <iframe id="fattura-iframe" title="Fattura" srcDoc={doc.html}
                  className="w-full h-full bg-white" sandbox="allow-same-origin allow-modals allow-popups" />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Pannello Qualifica Fornitori Batch ─────────────────────────────────────




// ── Note Operatore per scheda ricevimento ────────────────────────────────────

export default FattureList;
