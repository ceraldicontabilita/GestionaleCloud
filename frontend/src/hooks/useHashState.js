/**
 * useHashState — Deep Linking via window.location.hash
 * =====================================================
 * Sincronizza ogni cambio di stato UI (tab, filtri, selezione) con l'URL hash.
 *
 * Formato hash: #key1=val1&key2=val2  (URLSearchParams-compatible)
 *
 * Comportamento:
 * - Al mount: legge l'hash corrente e lo unisce ai defaults
 * - Ad ogni cambio di stato: aggiorna l'hash senza ricaricare la pagina
 * - hashchange (browser back/forward): sincronizza lo stato
 * - Navigazione React Router verso altra route: pulisce l'hash → defaults usati
 *
 * Utilizzo:
 *   const [hs, setHs, setHsMany] = useHashState({ tab: 'email', search: '' });
 *   const activeTab = hs.tab;
 *   setHs('tab', 'system');                         // → #tab=system
 *   setHsMany({ mese: '3', stato: 'pagata' });      // → #mese=3&stato=pagata
 *
 * Le chiavi con valore vuoto (''), null o undefined vengono omesse dall'hash.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

// ─── helpers ──────────────────────────────────────────────────────────────────

function parseHash() {
  const raw = window.location.hash.slice(1);
  if (!raw) return {};
  try {
    return Object.fromEntries(new URLSearchParams(raw));
  } catch {
    return {};
  }
}

function writeHash(state) {
  const params = new URLSearchParams();
  Object.entries(state).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      params.set(k, String(v));
    }
  });
  const str = params.toString();
  const newHash = str ? `#${str}` : window.location.pathname + window.location.search;
  // replaceState evita di intasare la history ad ogni keystroke
  const url = window.location.pathname + window.location.search + (str ? `#${str}` : '');
  window.history.replaceState(null, '', url);
}

// ─── hook ─────────────────────────────────────────────────────────────────────

/**
 * @param {Record<string, string>} defaults  Stato iniziale / reset values
 * @returns {[state, setKey, setMany, reset]}
 */
export function useHashState(defaults = {}) {
  const defaultsRef = useRef(defaults);

  const [state, setState] = useState(() => {
    const fromHash = parseHash();
    return { ...defaults, ...fromHash };
  });

  // Scrivi nell'hash ad ogni cambio di stato
  useEffect(() => {
    writeHash(state);
  }, [state]);

  // Gestisci browser back/forward (hashchange)
  useEffect(() => {
    function onHashChange() {
      const fromHash = parseHash();
      setState(() => {
        const defs = defaultsRef.current;
        const next = { ...defs };
        // Applica i valori dall'hash; chiavi assenti → reset al default
        Object.keys(defs).forEach(k => {
          if (fromHash[k] !== undefined) next[k] = fromHash[k];
        });
        // Includi anche chiavi extra non nei defaults
        Object.keys(fromHash).forEach(k => {
          if (!(k in defs)) next[k] = fromHash[k];
        });
        return next;
      });
    }
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Imposta una singola chiave
  const setKey = useCallback((key, value) => {
    setState(prev => ({ ...prev, [key]: value ?? '' }));
  }, []);

  // Imposta più chiavi contemporaneamente
  const setMany = useCallback(updates => {
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  // Ripristina tutti i defaults
  const reset = useCallback(() => {
    setState({ ...defaultsRef.current });
  }, []);

  return [state, setKey, setMany, reset];
}

export default useHashState;
