import { Snowflake, Thermometer } from "lucide-react";
import { Modal } from "./uiLotti";

// Modale "Recall Ingrediente — Tracciabilità Produzione" (Reg. CE 178/2002):
// filtri, elenco lotti coinvolti, export .txt del report e registrazione
// formale del richiamo. Estratto 1:1 da LottiList.jsx (refactor 25/07/2026).
export default function ModalRecallIngrediente({
  ingrediente, risultati, loading, filtri, setFiltri,
  onClose, onApplicaFiltri, onApriLotto,
  onRegistraRichiamo, registrandoRichiamo,
}) {
  const scaricaReport = () => {
    const righe = risultati.lotti.map(l =>
      `${l.numero_lotto}\t${l.prodotto}\t${l.data_produzione}\t${l.data_scadenza || ""}\t${l.quantita || ""} ${l.unita_misura || ""}\t${l.frigo_numero || ""}\t${l.fornitore || ""}`
    ).join("\n");
    const filtriTesto = Object.entries(filtri).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(", ") || "nessuno";
    const contenuto = `REPORT RECALL — Reg. CE 178/2002\nData: ${new Date().toLocaleString("it-IT")}\n\nIngrediente: ${ingrediente}\nFiltri: ${filtriTesto}\nLotti: ${risultati.totale_lotti}\n\nN° LOTTO\tPRODOTTO\tDATA PROD.\tSCADENZA\tQUANTITÀ\tFRIGO\tFORNITORE\n${righe}`;
    const blob = new Blob([contenuto], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `recall_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 500);
  };

  return (
    <Modal isOpen={!!ingrediente} onClose={onClose}
      title="Recall Ingrediente — Tracciabilità Produzione">
      <div className="space-y-4">
        <div className="p-3 bg-red-50 border-2 border-red-300 rounded-xl">
          <p className="text-xs font-bold text-red-600 uppercase tracking-wide mb-1">
            ⚠ Ingrediente sotto controllo (Reg. CE 178/2002)
          </p>
          <p className="text-sm font-medium text-red-800 break-words">{ingrediente}</p>
        </div>

        <div className="bg-gray-50 rounded-xl p-3 space-y-3 border border-gray-200">
          <p className="text-xs font-bold text-gray-600 uppercase tracking-wide">Filtri Ricerca</p>
          <div className="grid grid-cols-2 gap-2">
            {[
              { key: "data_da", label: "Data Da", type: "date" },
              { key: "data_a", label: "Data A", type: "date" },
              { key: "fornitore", label: "Fornitore", type: "text", placeholder: "es. F.lli Fiorentino..." },
              { key: "frigo", label: "N° Frigo", type: "text", placeholder: "es. Frigo 1..." }
            ].map(({ key, label, type, placeholder }) => (
              <div key={key}>
                <label className="text-xs text-gray-500 mb-1 block">{label}</label>
                <input type={type} value={filtri[key]}
                  onChange={(e) => setFiltri(f => ({ ...f, [key]: e.target.value }))}
                  placeholder={placeholder}
                  className="w-full px-2 py-1.5 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-red-300" />
              </div>
            ))}
          </div>
          <button onClick={onApplicaFiltri} disabled={loading}
            className="w-full py-2 bg-gray-800 hover:bg-gray-900 text-white rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5">
            {loading ? "Ricerca..." : "Applica Filtri"}
          </button>
        </div>

        {loading && (
          <div className="text-center py-6 text-gray-500">
            <p className="text-sm">Ricerca lotti in corso...</p>
          </div>
        )}

        {risultati && !loading && (
          <>
            <div className={`p-3 rounded-xl text-center font-bold text-lg border-2 ${
              risultati.totale_lotti > 0 ? "bg-orange-50 border-orange-400 text-orange-800" : "bg-green-50 border-green-300 text-green-700"
            }`}>
              {risultati.totale_lotti > 0
                ? `⚠ ${risultati.totale_lotti} lotti di produzione coinvolti`
                : "✓ Nessun lotto trovato con questo ingrediente"}
            </div>

            {risultati.lotti.length > 0 && (
              <div className="space-y-2 max-h-[45vh] overflow-y-auto">
                {risultati.lotti.map((lotto) => (
                  <div key={lotto.id}
                    className="p-3 bg-white border border-gray-200 rounded-lg hover:border-[#b8d0c2] hover:bg-[#f2f6f3] transition-colors cursor-pointer"
                    title="Clicca per aprire il dettaglio del lotto"
                    onClick={() => onApriLotto(lotto)}>
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="font-bold text-gray-800 capitalize">{lotto.prodotto}</span>
                      <span className="font-mono text-xs text-[#5b7a6b] bg-[#f2f6f3] px-2 py-0.5 rounded">{lotto.numero_lotto}</span>
                      {lotto.frigo_numero && (
                        <span className={`text-xs px-1.5 py-0.5 rounded flex items-center gap-0.5 ${/congelat|freezer|surgelat/i.test(lotto.frigo_numero) ? "bg-[#e8efe9] text-[#3f5a4e]" : "bg-orange-100 text-orange-700"}`}>
                          {/congelat|freezer|surgelat/i.test(lotto.frigo_numero) ? <Snowflake size={10} /> : <Thermometer size={10} />} {lotto.frigo_numero}
                        </span>
                      )}
                    </div>
                    <div className="flex gap-3 text-xs text-gray-500 flex-wrap">
                      <span>Prod: <strong>{lotto.data_produzione}</strong></span>
                      <span>Scad: <strong>{lotto.data_scadenza || "N/D"}</strong></span>
                      {lotto.fornitore && <span className="text-gray-400 italic">{lotto.fornitore}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {risultati.lotti.length > 0 && (
              <button onClick={scaricaReport}
                className="w-full py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-colors">
                ⬇ Scarica Report Recall (.txt)
              </button>
            )}

            {risultati.lotti.length > 0 && (
              <button onClick={onRegistraRichiamo} disabled={registrandoRichiamo}
                title="Registra formalmente che il richiamo è stato avviato su questi lotti (diverso da una semplice ricerca): resta in cronologia su ogni lotto"
                className="w-full py-2.5 bg-white border-2 border-red-600 hover:bg-red-50 text-red-700 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-60">
                {registrandoRichiamo ? "Registro..." : "✓ Registra come richiamo eseguito"}
              </button>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
