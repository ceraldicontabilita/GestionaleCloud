/**
 * HOOKS CONDIVISI - Frontend React
 * ================================
 *
 * Custom hooks per gestione centralizzata dei dati.
 * Forniscono caching, error handling e refresh automatico.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api';

// ==================== UTILITY HOOKS ====================

/**
 * Hook per rilevare se siamo su mobile
 */
export function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(window.innerWidth < breakpoint);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < breakpoint);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [breakpoint]);

  return isMobile;
}

/**
 * Hook per debounce di valori
 */
export function useDebounce(value, delay = 300) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// ==================== DATA HOOKS ====================

/**
 * Hook generico per fetch dati con caching
 */
export function useFetch(url, options = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const cache = useRef({});

  const {
    enabled = true,
    refetchInterval = null,
    cacheTime = 60000, // 1 minuto
  } = options;

  const fetchData = useCallback(async () => {
    if (!enabled || !url) return;

    // Check cache
    const cached = cache.current[url];
    if (cached && Date.now() - cached.timestamp < cacheTime) {
      setData(cached.data);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const res = await api.get(url);
      const result = res.data;

      // Update cache
      cache.current[url] = { data: result, timestamp: Date.now() };

      setData(result);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [url, enabled, cacheTime]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh disabled - manual refresh only
  // useEffect(() => {
  //   if (!refetchInterval) return;
  //   const interval = setInterval(fetchData, refetchInterval);
  //   return () => clearInterval(interval);
  // }, [fetchData, refetchInterval]);

  return { data, loading, error, refetch: fetchData };
}

// ==================== FATTURE HOOK ====================

/**
 * Hook per gestione fatture
 */
export function useFatture(filters = {}) {
  const [fatture, setFatture] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({ total: 0, paid: 0, unpaid: 0 });

  const loadFatture = useCallback(async () => {
    try {
      setLoading(true);

      const params = new URLSearchParams();
      // Forza anno corrente se non specificato per performance
      const currentYear = new Date().getFullYear();
      params.append('anno', filters.year || currentYear);
      if (filters.status) params.append('status', filters.status);
      if (filters.supplier) params.append('supplier_vat', filters.supplier);
      params.append('limit', filters.limit || '100');

      const res = await api.get(`/api/invoices?${params}`);
      const items = res.data.items || res.data || [];

      setFatture(items);

      // Calcola stats
      const paid = items.filter(f => f.pagato === true || f.payment_status === 'paid').length;
      setStats({
        total: items.length,
        paid,
        unpaid: items.length - paid,
        totalAmount: items.reduce((sum, f) => sum + (f.total_amount || f.importo_totale || 0), 0),
      });

      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [filters.year, filters.status, filters.supplier, filters.limit]);

  useEffect(() => {
    loadFatture();
  }, [loadFatture]);

  // Delete con validazione
  const deleteFattura = useCallback(
    async (id, force = false) => {
      try {
        const res = await api.delete(`/api/fatture/${id}?force=${force}`);

        if (res.data.require_force) {
          return {
            success: false,
            requireConfirm: true,
            warnings: res.data.warnings,
          };
        }

        // Refresh list
        await loadFatture();
        return { success: true };
      } catch (e) {
        const detail = e.response?.data?.detail;
        return {
          success: false,
          error: detail?.message || detail || e.message,
          errors: detail?.errors || [],
        };
      }
    },
    [loadFatture]
  );

  // Pay fattura
  const payFattura = useCallback(
    async (id, paymentData) => {
      try {
        const res = await api.put(`/api/fatture/${id}/paga`, paymentData);
        await loadFatture();
        return { success: true, data: res.data };
      } catch (e) {
        return { success: false, error: e.response?.data?.detail || e.message };
      }
    },
    [loadFatture]
  );

  return {
    fatture,
    loading,
    error,
    stats,
    refetch: loadFatture,
    deleteFattura,
    payFattura,
  };
}

// ==================== CORRISPETTIVI HOOK ====================

/**
 * Hook per gestione corrispettivi
 */
export function useCorrispettivi(filters = {}) {
  const [corrispettivi, setCorrispettivi] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadCorrispettivi = useCallback(async () => {
    try {
      setLoading(true);

      const params = new URLSearchParams();
      if (filters.year) params.append('anno', filters.year);
      if (filters.month) params.append('mese', filters.month);
      params.append('limit', filters.limit || '500');

      const res = await api.get(`/api/corrispettivi?${params}`);
      setCorrispettivi(res.data || []);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [filters.year, filters.month, filters.limit]);

  useEffect(() => {
    loadCorrispettivi();
  }, [loadCorrispettivi]);

  // Delete con validazione
  const deleteCorrispettivo = useCallback(
    async (id, force = false) => {
      try {
        const res = await api.delete(`/api/corrispettivi/${id}?force=${force}`);

        if (res.data.require_force) {
          return { success: false, requireConfirm: true, warnings: res.data.warnings };
        }

        await loadCorrispettivi();
        return { success: true };
      } catch (e) {
        const detail = e.response?.data?.detail;
        return { success: false, error: detail?.message || detail || e.message };
      }
    },
    [loadCorrispettivi]
  );

  // Calcola totali
  const totals = {
    count: corrispettivi.length,
    totale: corrispettivi.reduce((sum, c) => sum + (c.totale || 0), 0),
    contanti: corrispettivi.reduce((sum, c) => sum + (c.pagato_contanti || 0), 0),
    pos: corrispettivi.reduce((sum, c) => sum + (c.pagato_pos || 0), 0),
  };

  return {
    corrispettivi,
    loading,
    error,
    totals,
    refetch: loadCorrispettivi,
    deleteCorrispettivo,
  };
}

// ==================== PRIMA NOTA HOOK ====================

/**
 * Hook per gestione Prima Nota
 */
export function usePrimaNota(tipo = 'cassa', filters = {}) {
  const [movimenti, setMovimenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saldi, setSaldi] = useState({ entrate: 0, uscite: 0, saldo: 0 });

  const loadMovimenti = useCallback(async () => {
    try {
      setLoading(true);

      const params = new URLSearchParams();
      if (filters.year) params.append('anno', filters.year);
      if (filters.month) params.append('mese', filters.month);
      params.append('limit', filters.limit || '10000');

      const endpoint = tipo === 'cassa' ? '/api/prima-nota/cassa' : '/api/prima-nota/banca';
      const res = await api.get(`${endpoint}?${params}`);

      const data = res.data;
      setMovimenti(data.movimenti || data || []);

      if (data.totale_entrate !== undefined) {
        setSaldi({
          entrate: data.totale_entrate || 0,
          uscite: data.totale_uscite || 0,
          saldo: data.saldo || 0,
        });
      }

      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [tipo, filters.year, filters.month, filters.limit]);

  useEffect(() => {
    loadMovimenti();
  }, [loadMovimenti]);

  // Delete movimento
  const deleteMovimento = useCallback(
    async (id, force = false) => {
      try {
        const endpoint =
          tipo === 'cassa' ? `/api/prima-nota/cassa/${id}` : `/api/prima-nota/banca/${id}`;
        const res = await api.delete(`${endpoint}?force=${force}`);

        if (res.data.require_force) {
          return { success: false, requireConfirm: true, warnings: res.data.warnings };
        }

        await loadMovimenti();
        return { success: true };
      } catch (e) {
        const detail = e.response?.data?.detail;
        return { success: false, error: detail?.message || detail || e.message };
      }
    },
    [tipo, loadMovimenti]
  );

  // Add movimento
  const addMovimento = useCallback(
    async movimento => {
      try {
        const endpoint = tipo === 'cassa' ? '/api/prima-nota/cassa' : '/api/prima-nota/banca';
        await api.post(endpoint, movimento);
        await loadMovimenti();
        return { success: true };
      } catch (e) {
        return { success: false, error: e.response?.data?.detail || e.message };
      }
    },
    [tipo, loadMovimenti]
  );

  return {
    movimenti,
    loading,
    error,
    saldi,
    refetch: loadMovimenti,
    deleteMovimento,
    addMovimento,
  };
}

// ==================== FORNITORI HOOK ====================

/**
 * Hook per gestione fornitori
 */
export function useFornitori(filters = {}) {
  const [fornitori, setFornitori] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadFornitori = useCallback(async () => {
    try {
      setLoading(true);

      const params = new URLSearchParams();
      if (filters.search) params.append('search', filters.search);
      params.append('limit', filters.limit || '500');

      const res = await api.get(`/api/suppliers?${params}`);
      setFornitori(res.data || []);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [filters.search, filters.limit]);

  useEffect(() => {
    loadFornitori();
  }, [loadFornitori]);

  return { fornitori, loading, error, refetch: loadFornitori };
}

// ==================== ASSEGNI HOOK ====================

/**
 * Hook per gestione assegni
 */
export function useAssegni(_filters = {}) {
  const [assegni, setAssegni] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadAssegni = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/api/assegni');
      setAssegni(res.data || []);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAssegni();
  }, [loadAssegni]);

  // Delete assegno
  const deleteAssegno = useCallback(
    async (id, force = false) => {
      try {
        const res = await api.delete(`/api/assegni/${id}?force=${force}`);

        if (res.data.require_force) {
          return { success: false, requireConfirm: true, warnings: res.data.warnings };
        }

        await loadAssegni();
        return { success: true };
      } catch (e) {
        const detail = e.response?.data?.detail;
        return { success: false, error: detail?.message || detail || e.message };
      }
    },
    [loadAssegni]
  );

  // Raggruppa per carnet
  const carnets = assegni.reduce((acc, a) => {
    const prefix = a.numero?.split('-')[0] || 'Senza Carnet';
    if (!acc[prefix]) acc[prefix] = [];
    acc[prefix].push(a);
    return acc;
  }, {});

  return {
    assegni,
    carnets: Object.entries(carnets).map(([id, items]) => ({ id, assegni: items })),
    loading,
    error,
    refetch: loadAssegni,
    deleteAssegno,
  };
}

// ==================== TOAST/MESSAGE HOOK ====================

/**
 * Hook per gestione messaggi/toast
 */
export function useMessage(timeout = 3000) {
  const [message, setMessage] = useState(null);

  const show = useCallback(
    (text, type = 'success') => {
      setMessage({ text, type });
      setTimeout(() => setMessage(null), timeout);
    },
    [timeout]
  );

  const showSuccess = useCallback(text => show(text, 'success'), [show]);
  const showError = useCallback(text => show(text, 'error'), [show]);
  const showWarning = useCallback(text => show(text, 'warning'), [show]);

  const clear = useCallback(() => setMessage(null), []);

  return { message, show, showSuccess, showError, showWarning, clear };
}

// ==================== CONFIRM DIALOG HOOK ====================

/**
 * Hook per dialog di conferma
 */
export function useConfirm() {
  const [dialog, setDialog] = useState(null);

  const confirm = useCallback(options => {
    return new Promise(resolve => {
      setDialog({
        ...options,
        onConfirm: () => {
          setDialog(null);
          resolve(true);
        },
        onCancel: () => {
          setDialog(null);
          resolve(false);
        },
      });
    });
  }, []);

  const close = useCallback(() => setDialog(null), []);

  return { dialog, confirm, close };
}
