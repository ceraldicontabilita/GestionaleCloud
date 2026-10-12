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
  const [salvataggi, setSalvataggi] = useState(new Set());
  const carica = useCallback(async () => {
    const id = ++richiesta.current;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/cataloghi/preferiti/${encodeURIComponent(fonte)}`);
      if (id === richiesta.current) { setProdotti(r.data.prodotti || []); setErrore(""); }
    } catch {
      if (id === richiesta.current) setErrore("Non riesco a leggere acquisti e preferiti. Riprova.");
    } finally { if (id === richiesta.current) setLoading(false); }
  }, [fonte]);
  useEffect(() => { carica(); return () => { richiesta.current++; }; }, [carica]);
  useEffect(() => {
    const aggiornaDaSync = event => {
      if (event.detail?.fonte !== fonte || !Array.isArray(event.detail?.prodotti)) return;
      richiesta.current++;
      setProdotti(event.detail.prodotti);
      setErrore("");
      setLoading(false);
    };
    window.addEventListener("cataloghi-preferiti-sincronizzati", aggiornaDaSync);
    return () => window.removeEventListener("cataloghi-preferiti-sincronizzati", aggiornaDaSync);
  }, [fonte]);
  const chiave = useCallback(p => String(p?.codice_articolo || p?.codice || p?.id || "").trim().toLowerCase(), []);
  const isPreferito = useCallback(p => {
    const k = chiave(p?.raw || p);
    return prodotti.some(x => x.preferito_manuale && chiave(x) === k);
  }, [chiave, prodotti]);
  const toggle = useCallback(async p => {
    const originale = p?.raw || p;
    const k = chiave(originale);
    if (!k || salvataggi.has(k)) return;
    const preferito = !isPreferito(originale);
    setSalvataggi(prev => new Set(prev).add(k));
    try {
      await axios.put(`${API}/cataloghi/preferiti/${encodeURIComponent(fonte)}`, { prodotto: originale, preferito });
      await carica();
      return preferito;
    } finally {
      setSalvataggi(prev => { const next = new Set(prev); next.delete(k); return next; });
    }
  }, [carica, chiave, fonte, isPreferito, salvataggi]);
  const isSalvando = useCallback(p => salvataggi.has(chiave(p?.raw || p)), [chiave, salvataggi]);
  return { prodotti, loading, errore, carica, isPreferito, isSalvando, toggle };
}
