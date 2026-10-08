import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import api from '../api';
import {
  INTERVALLO_GUSCIO_MS,
  attesaProssimoGiro,
  leggiCacheGuscio,
  scriviCacheGuscio,
} from '../lib/cacheGuscio';

const GuscioContext = createContext(null);

/**
 * Un dato del guscio: letto una volta all'apertura (o ripreso dalla copia di
 * sessione se ha meno di 120 s), poi riletto ogni 120 s. Gli errori sono
 * silenziosi come prima: resta l'ultimo valore buono.
 */
function useDatoGuscio(url) {
  const [dati, setDati] = useState(() => leggiCacheGuscio(url)?.dati ?? null);

  const ricarica = useCallback(async () => {
    try {
      const res = await api.get(url);
      scriviCacheGuscio(url, res.data);
      setDati(res.data);
    } catch (e) {
      // Silenzioso: il prossimo giro riprova
    }
  }, [url]);

  useEffect(() => {
    let timer;
    let chiuso = false;
    const giro = async () => {
      await ricarica();
      if (!chiuso) timer = setTimeout(giro, INTERVALLO_GUSCIO_MS);
    };
    timer = setTimeout(giro, attesaProssimoGiro(url));
    return () => {
      chiuso = true;
      clearTimeout(timer);
    };
  }, [url, ricarica]);

  return [dati, ricarica];
}

export function GuscioProvider({ children }) {
  const [alertsSummary] = useDatoGuscio('/api/alerts/summary');
  const [alertCommercialista, ricaricaAlertCommercialista] = useDatoGuscio(
    '/api/commercialista/alert-status'
  );

  const value = useMemo(
    () => ({ alertsSummary, alertCommercialista, ricaricaAlertCommercialista }),
    [alertsSummary, alertCommercialista, ricaricaAlertCommercialista]
  );

  return <GuscioContext.Provider value={value}>{children}</GuscioContext.Provider>;
}

export function useGuscio() {
  const ctx = useContext(GuscioContext);
  if (!ctx) throw new Error('useGuscio must be used within GuscioProvider');
  return ctx;
}
