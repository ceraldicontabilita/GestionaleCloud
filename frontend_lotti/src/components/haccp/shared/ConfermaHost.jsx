import { useEffect, useState, useCallback } from "react";
import { AlertTriangle } from "lucide-react";
import { _registraConfermaHandler } from "../../../utils/conferma";

// Host UNICO del modale di conferma: montato una volta sola in App.js.
// Registra la funzione conferma() e la risolve quando l'utente sceglie.
export default function ConfermaHost() {
  const [stato, setStato] = useState(null); // { opts, resolve }

  const handler = useCallback((opts) => {
    return new Promise((resolve) => setStato({ opts, resolve }));
  }, []);

  useEffect(() => { _registraConfermaHandler(handler); }, [handler]);

  if (!stato) return null;
  const { opts, resolve } = stato;
  const chiudi = (val) => { resolve(val); setStato(null); };
  // Modal con input testo (chiediTesto): OK → stringa, Annulla → null
  const confermaInput = () => {
    const el = document.getElementById("conferma-host-input");
    chiudi(el ? el.value : "");
  };

  return (
    // z-index SOPRA ogni modale dell'app (FormRicetta usa 2000, i tablet
    // 3000-4000): 23/07/2026 la conferma "Eliminare ricetta?" finiva NASCOSTA.
    <div
      className="fixed inset-0 z-[9500] flex items-center justify-center p-4"
      onClick={() => chiudi(false)}
    >
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          {opts.pericolo && (
            <div className="flex-shrink-0 mt-0.5" style={{ color: "#d35f4e" }}>
              <AlertTriangle size={22} />
            </div>
          )}
          <div className="min-w-0">
            <h3 className="text-base font-extrabold text-gray-900">{opts.titolo}</h3>
            <p className="text-sm text-gray-600 mt-1 whitespace-pre-line">{opts.messaggio}</p>
          </div>
        </div>
        {opts.input && (
          <input
            id="conferma-host-input"
            defaultValue={opts.valore || ""}
            placeholder={opts.placeholder || ""}
            autoFocus
            onKeyDown={(e) => { if (e.key === "Enter") confermaInput(); }}
            className="mt-3 w-full rounded-lg border-2 border-gray-200 px-3 py-2 text-sm outline-none focus:border-[#5b7a6b]"
          />
        )}
        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={() => chiudi(opts.input ? null : false)}
            className="px-4 py-2 rounded-lg text-sm font-bold text-gray-600 hover:bg-gray-100"
          >
            {opts.annulla}
          </button>
          <button
            onClick={() => (opts.input ? confermaInput() : chiudi(true))}
            autoFocus={!opts.input}
            className="px-4 py-2 rounded-lg text-sm font-bold text-white"
            style={{ background: opts.pericolo ? "#d35f4e" : "#5b7a6b" }}
          >
            {opts.ok}
          </button>
        </div>
      </div>
    </div>
  );
}
