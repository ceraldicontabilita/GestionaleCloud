// useInvioSingolo — protezione standard dai DOPPI INVII (fase 2, 24/07/2026).
// Avvolge un'azione asincrona: mentre gira, le chiamate successive vengono
// ignorate e `inCorso` è true (da usare per disabilitare il bottone e
// mostrare l'indicatore di caricamento). Errori → toast comprensibile.
//
//   const { esegui, inCorso } = useInvioSingolo();
//   <button disabled={inCorso}
//           onClick={() => esegui(async () => { await axios.post(...); },
//                               { ok: "Salvato ✅" })}>
//     {inCorso ? "Salvo…" : "Salva"}
//   </button>
import { useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { apiError } from "../utils/apiError";

export function useInvioSingolo() {
  const occupato = useRef(false);
  const [inCorso, setInCorso] = useState(false);

  const esegui = useCallback(async (azione, opzioni = {}) => {
    if (occupato.current) return;          // doppio tocco: ignorato
    occupato.current = true;
    setInCorso(true);
    try {
      const esito = await azione();
      if (opzioni.ok) toast.success(opzioni.ok);
      return esito;
    } catch (e) {
      toast.error(opzioni.err ? `${opzioni.err}: ${apiError(e)}` : apiError(e));
      return undefined;
    } finally {
      occupato.current = false;
      setInCorso(false);
    }
  }, []);

  return { esegui, inCorso };
}
