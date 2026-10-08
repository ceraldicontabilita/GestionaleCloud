import { useState, useCallback } from "react";

/**
 * Conferma UNICA e on-brand per tutta l'app (prima ogni pagina usava il popup
 * grezzo del browser, tranne Lotti con un modale suo → aspetto incoerente).
 *
 * Uso:
 *   const { conferma, dialogConferma } = useConferma();
 *   // nel JSX: {dialogConferma}
 *   // nell'handler (async): if (!(await conferma("Eliminare la fattura?"))) return;
 *
 * Se ci si dimenttica di rendere {dialogConferma}, la conferma semplicemente non
 * appare e l'azione NON parte: fallimento nella direzione sicura (mai cancella
 * senza chiedere).
 */
export function useConferma() {
  const [stato, setStato] = useState(null); // { messaggio, dettaglio, tonoDanger, resolve }

  const conferma = useCallback(
    (messaggio, opts = {}) =>
      new Promise((resolve) =>
        setStato({
          messaggio,
          dettaglio: opts.dettaglio || "",
          tonoDanger: opts.tonoDanger !== false, // default: azione distruttiva
          resolve,
        })
      ),
    []
  );

  const chiudi = (val) => {
    if (stato) stato.resolve(val);
    setStato(null);
  };

  const dialogConferma = stato ? (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={() => chiudi(false)} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm p-5">
        <p className="text-base font-bold text-gray-800">{stato.messaggio}</p>
        {stato.dettaglio && <p className="text-sm text-gray-500 mt-1">{stato.dettaglio}</p>}
        <div className="flex gap-2 justify-end mt-4">
          <button
            onClick={() => chiudi(false)}
            className="px-4 py-2 rounded-lg border border-gray-200 text-gray-600 font-semibold hover:bg-gray-50"
          >
            Annulla
          </button>
          <button
            onClick={() => chiudi(true)}
            className="px-4 py-2 rounded-lg font-bold text-white"
            style={{ background: stato.tonoDanger ? "#d35f4e" : "#5b7a6b" }}
          >
            Conferma
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return { conferma, dialogConferma };
}
