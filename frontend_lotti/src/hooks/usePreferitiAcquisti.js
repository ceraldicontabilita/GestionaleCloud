import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "../utils/constants";

export function useStatoCatalogo(fonte, campo, iniziale) {
  const chiave = `catalogo:${fonte}:${campo}`;
  const leggi = () => {
    try { return JSON.parse(sessionStorage.getItem(chiave)) ?? iniziale; } catch { return iniziale; }
  };
  const [stato, setStato] = useState(() => ({ chiave, valore: leggi() }));
  const valore = stato.chiave === chiave ? stato.valore : leggi();
  const aggiorna = useCallback(value => {
    setStato({ chiave, valore: value });
    try { sessionStorage.setItem(chiave, JSON.stringify(value)); } catch { /* memoria browser piena */ }
  }, [chiave]);
  return [valore, aggiorna];
}

export default function usePreferitiAcquisti(fonte) {
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState("");
  const richiesta = useRef(0);
  const carica = useCallback(async () => {
    const id = ++richiesta.current;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/cataloghi/preferiti/${encodeURIComponent(fonte)}`);
      if (id === richiesta.current) { setProdotti(r.data.prodotti || []); setErrore(""); }
    } catch {
      if (id === richiesta.current) setErrore("Non riesco a leggere i preferiti dalle fatture. Riprova.");
    } finally { if (id === richiesta.current) setLoading(false); }
  }, [fonte]);
  useEffect(() => { carica(); return () => { richiesta.current++; }; }, [carica]);
  return { prodotti, loading, errore, carica };
}
