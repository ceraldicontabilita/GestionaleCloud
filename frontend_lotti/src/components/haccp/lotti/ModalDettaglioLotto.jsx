import { Printer, FileText } from "lucide-react";
import { withToken } from "../../../utils/constants";
import { ALLERGENI_EU_LIST, allergeniDaTesto } from "../../../utils/allergeni";
import { Modal, Button } from "./uiLotti";

// Modale "Dettaglio Lotto" — estratto 1:1 da LottiList.jsx (refactor
// 25/07/2026): dati del lotto, allergeni Reg. UE 1169/2011, ingredienti
// cliccabili per il recall, tracciabilità fornitori, etichetta e stampe.
// Componente di sola presentazione: riceve il lotto e i callback.
export default function ModalDettaglioLotto({ lotto, onClose, onPrint, onRecallIngrediente }) {
  return (
    <Modal isOpen={!!lotto} onClose={onClose} title="Dettaglio Lotto">
      {lotto && (() => {
        const allergeniTesto = lotto.allergeni_testo || "";
        const ingredienti = lotto.ingredienti_dettaglio || [];
        const allergeniPresenti = allergeniDaTesto(allergeniTesto + " " + ingredienti.join(" "));
        const ingredientiOrdinati = [...ingredienti].sort((a, b) => {
          const aH = a.toLowerCase().includes("contiene") || a.toLowerCase().includes("allergeni");
          const bH = b.toLowerCase().includes("contiene") || b.toLowerCase().includes("allergeni");
          if (aH && !bH) return -1;
          if (!aH && bH) return 1;
          return a.localeCompare(b);
        });

        return (
          <div className="space-y-4 max-h-[80vh] overflow-y-auto">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-gray-50 rounded-xl">
                <p className="text-xs text-gray-500 mb-0.5">Prodotto</p>
                <p className="font-bold text-gray-800">{lotto.prodotto}</p>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl">
                <p className="text-xs text-gray-500 mb-0.5">Numero Lotto</p>
                <p className="font-bold text-[#5b7a6b] font-mono text-sm">{lotto.numero_lotto}</p>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl">
                <p className="text-xs text-gray-500 mb-0.5">Data Produzione</p>
                <p className="font-semibold">{lotto.data_produzione}</p>
              </div>
              <div className="p-3 bg-amber-50 rounded-xl border border-amber-200">
                <p className="text-xs text-amber-600 mb-0.5">Data Scadenza</p>
                <p className="font-bold text-amber-800">{lotto.data_scadenza}</p>
              </div>
              {lotto.frigo_numero && (
                <div className="col-span-2 p-3 bg-[#f2f6f3] rounded-xl border border-[#cfdfd5] flex items-center gap-2">
                  <span className="text-[#5b7a6b] text-lg">🧊</span>
                  <div>
                    <p className="text-xs text-[#5b7a6b]">Frigorifero di Stoccaggio</p>
                    <p className="font-bold text-[#3f5a4e]">{lotto.frigo_numero}</p>
                  </div>
                </div>
              )}
            </div>

            <div className="flex gap-2 flex-wrap">
              {lotto.consumato && (
                <span className="px-3 py-1.5 bg-gray-200 text-gray-600 border border-gray-300 rounded-full text-xs font-bold uppercase tracking-wide">
                  Esaurito — consumato il {lotto.data_consumo ? new Date(lotto.data_consumo).toLocaleDateString("it-IT") : "N/D"}
                </span>
              )}
              {lotto.surgelato && (
                <span className="px-3 py-1.5 bg-[#e8efe9] text-[#5b7a6b] border border-[#cfdfd5] rounded-full text-xs font-semibold">
                  ❄️ SURGELATO — Fornitore: {lotto.fornitore_surgelato || "N/D"}
                </span>
              )}
              {lotto.vegano && (
                <span className="px-3 py-1.5 bg-green-100 text-green-700 border border-green-200 rounded-full text-xs font-semibold">
                  🌿 CERTIFICATO VEGANO
                </span>
              )}
              {allergeniPresenti.length === 0 && (
                <span className="px-3 py-1.5 bg-gray-100 text-gray-600 border border-gray-200 rounded-full text-xs font-semibold">
                  ✓ Non contiene allergeni dichiarati
                </span>
              )}
            </div>

            {allergeniPresenti.length > 0 && (
              <div className="p-4 bg-red-50 border-2 border-red-400 rounded-xl">
                <p className="text-sm font-bold text-red-700 mb-3">⚠️ ALLERGENI (Reg. UE 1169/2011) — CONTIENE:</p>
                <div className="flex flex-wrap gap-2">
                  {allergeniPresenti.sort().map((a) => (
                    <span key={a} className="px-3 py-1.5 bg-red-600 text-white rounded-lg text-xs font-bold uppercase tracking-wide">{a}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="p-3 bg-white border border-gray-200 rounded-xl">
              <p className="text-xs font-bold text-gray-600 uppercase tracking-wide mb-2">14 Allergeni Europei (Reg. 1169/2011)</p>
              <div className="grid grid-cols-2 gap-1">
                {[...ALLERGENI_EU_LIST].sort().map((a) => {
                  const presente = allergeniPresenti.includes(a);
                  return (
                    <div key={a} className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs ${presente ? "bg-red-50 text-red-700 font-bold" : "text-gray-400"}`}>
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${presente ? "bg-red-500" : "bg-gray-200"}`} />
                      {a}
                      {presente && <span className="ml-auto text-red-500">✓</span>}
                    </div>
                  );
                })}
              </div>
            </div>

            <div>
              <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
                Ingredienti con Tracciabilità
                <span className="text-xs text-gray-400 font-normal">(allergeni evidenziati)</span>
                <span className="text-xs text-[#5b7a6b] font-normal ml-auto">Clicca per Recall</span>
              </p>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {ingredientiOrdinati.map((ing) => {
                  const hasAllergeni = ing.toLowerCase().includes("contiene") && !ing.toLowerCase().includes("non contiene");
                  return (
                    <button key={ing} onClick={() => onRecallIngrediente(ing)}
                      className={`w-full text-left p-2.5 rounded-lg text-sm border transition-all hover:shadow-md hover:scale-[1.01] cursor-pointer group ${
                        hasAllergeni ? "bg-amber-50 border-amber-200 hover:bg-amber-100 hover:border-amber-400"
                          : "bg-gray-50 border-gray-100 hover:bg-[#f2f6f3] hover:border-[#b8d0c2]"
                      }`}
                      title="Clicca per vedere tutti i lotti realizzati con questo ingrediente">
                      <div className="flex items-start justify-between gap-2">
                        <span>
                          {hasAllergeni && <span className="text-amber-600 font-bold mr-1">⚠</span>}
                          {ing}
                        </span>
                        <span className="shrink-0 text-gray-300 group-hover:text-[#5b7a6b] transition-colors mt-0.5">🔍</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Sezione Tracciabilità Fornitori (controllo a ritroso) */}
            {lotto.lotti_fornitori?.lotti_scalati?.length > 0 && (
              <div>
                <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
                  Tracciabilità Fornitori
                  <span className="text-xs text-gray-400 font-normal">(Reg. CE 178/2002)</span>
                </p>
                <div className="space-y-2 max-h-56 overflow-y-auto">
                  {lotto.lotti_fornitori.lotti_scalati.map((ls, i) => {
                    const isFattura = (ls.lotto_id_fornitore || "").startsWith("FAT-");
                    return (
                      <div key={i} className={`p-2.5 border rounded-lg ${isFattura ? "bg-amber-50 border-amber-200" : "bg-green-50 border-green-200"}`}>
                        <div className="flex items-start justify-between gap-2 mb-1">
                          {isFattura ? (
                            <span className="font-mono text-xs font-bold text-amber-800 bg-amber-100 px-1.5 py-0.5 rounded">
                              FAT: {ls.lotto_id_fornitore?.replace("FAT-", "") || "N/D"}
                            </span>
                          ) : (
                            <span className="font-mono text-xs font-bold text-green-800 bg-green-100 px-1.5 py-0.5 rounded">
                              LOT: {ls.lotto_id_fornitore || "N/D"}
                            </span>
                          )}
                          {ls.data_scadenza && (
                            <span className="text-xs font-bold text-red-700 bg-red-50 px-1.5 py-0.5 rounded border border-red-200">
                              Scad: {ls.data_scadenza}
                            </span>
                          )}
                          {isFattura && ls.data_fattura && (
                            <span className="text-xs text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                              Fattura: {ls.data_fattura}
                            </span>
                          )}
                        </div>
                        <p className="text-xs font-semibold text-gray-700">{ls.fornitore || "—"}</p>
                        <p className="text-xs text-gray-500">{ls.prodotto || ls.ingrediente}</p>
                        <div className="flex gap-3 mt-1 text-xs text-gray-400 flex-wrap">
                          <span>Ing.: <strong className="text-gray-600">{ls.ingrediente}</strong></span>
                          <span>Usato: <strong>{ls.quantita_consumata} {ls.unita}</strong></span>
                          <span>Rimasto: <strong>{ls.quantita_rimasta} {ls.unita}</strong></span>
                        </div>
                        {!isFattura && ls.data_produzione && (
                          <p className="text-xs text-gray-400 mt-0.5">Prod. fornitore: {ls.data_produzione}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
                {lotto.lotti_fornitori.ingredienti_non_trovati?.length > 0 && (
                  <p className="text-xs text-gray-400 italic mt-1.5">
                    Non tracciati: {lotto.lotti_fornitori.ingredienti_non_trovati.join(", ")}
                  </p>
                )}
              </div>
            )}

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Etichetta</p>
              <div className="p-3 bg-[#f2f6f3] border border-[#cfdfd5] rounded-lg text-[#3f5a4e] font-medium text-sm">
                {lotto.etichetta || `${lotto.prodotto} - prodotto il ${lotto.data_produzione}`}
                {allergeniPresenti.length > 0 && (
                  <div className="mt-2 text-red-700 font-bold text-xs border-t border-[#cfdfd5] pt-2">
                    CONTIENE: {allergeniPresenti.join(", ").toUpperCase()}
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <Button onClick={() => onPrint(lotto)} className="flex-1">
                <Printer size={18} /> Stampa Etichetta
              </Button>
              <Button onClick={() => onPrint(lotto, true)} variant="secondary" className="flex-1">
                <Printer size={16} /> + Nutrizionali
              </Button>
            </div>
            <div className="pt-1">
              <Button
                onClick={() => window.open(withToken(`${process.env.REACT_APP_LOTTI_BACKEND_URL}/api/etichette/lotto/${lotto.id}`), "_blank")}
                variant="secondary"
                className="w-full"
              >
                <FileText size={16} /> Etichetta tracciabilità ASL (lotti fornitori)
              </Button>
            </div>
          </div>
        );
      })()}
    </Modal>
  );
}
