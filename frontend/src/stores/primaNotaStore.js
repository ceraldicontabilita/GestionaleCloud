/**
 * Store Zustand per Prima Nota Salari
 * Gestione centralizzata dello stato con performance ottimizzate
 */
import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import api from '../api';

export const usePrimaNotaStore = create(
  devtools(
    (set, get) => ({
      // State
      salariMovimenti: [],
      dipendentiLista: [],
      loading: false,
      importing: false,
      importResult: null,
      anniEsclusi: [],
      filtroDipendente: '',
      selectedMonth: '',
      selectedYear: null,

      // Computed values cache
      _totalsCache: null,
      _filteredDataCache: null,

      // Actions
      setFiltroDipendente: value => set({ filtroDipendente: value, _totalsCache: null }),
      setSelectedMonth: value => set({ selectedMonth: value, _totalsCache: null }),
      setSelectedYear: value => set({ selectedYear: value, _totalsCache: null }),

      toggleAnnoEscluso: anno =>
        set(state => {
          const nuoviAnni = state.anniEsclusi.includes(anno)
            ? state.anniEsclusi.filter(a => a !== anno)
            : [...state.anniEsclusi, anno];
          return { anniEsclusi: nuoviAnni, _totalsCache: null };
        }),

      resetAnniEsclusi: () => set({ anniEsclusi: [], _totalsCache: null }),

      // Fetch data
      fetchSalari: async () => {
        const { selectedYear, selectedMonth, filtroDipendente } = get();
        set({ loading: true });

        try {
          const params = [];
          if (selectedYear) params.push(`anno=${selectedYear}`);
          if (selectedMonth) params.push(`mese=${selectedMonth}`);
          if (filtroDipendente) params.push(`dipendente=${encodeURIComponent(filtroDipendente)}`);

          const url = `/api/prima-nota-salari/salari?${params.join('&')}`;
          const res = await api.get(url);
          // API returns direct array
          set({ salariMovimenti: res.data || [], loading: false, _totalsCache: null });
        } catch (error) {
          console.error('Error fetching salari:', error);
          set({ salariMovimenti: [], loading: false });
        }
      },

      fetchDipendentiLista: async () => {
        try {
          const res = await api.get('/api/prima-nota-salari/dipendenti-lista');
          set({ dipendentiLista: res.data || [] });
        } catch (error) {
          console.error('Error fetching dipendenti lista:', error);
        }
      },

      // Import actions
      importPaghe: async file => {
        set({ importing: true, importResult: null });
        try {
          const formData = new FormData();
          formData.append('file', file);
          const res = await api.post('/api/prima-nota-salari/import-paghe', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
          set({ importResult: res.data, importing: false });
          get().fetchSalari();
          get().fetchDipendentiLista();
          return res.data;
        } catch (error) {
          const result = { error: true, message: error.response?.data?.detail || error.message };
          set({ importResult: result, importing: false });
          return result;
        }
      },

      importBonifici: async file => {
        set({ importing: true, importResult: null });
        try {
          const formData = new FormData();
          formData.append('file', file);
          const res = await api.post('/api/prima-nota-salari/import-bonifici', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
          set({ importResult: res.data, importing: false });
          get().fetchSalari();
          return res.data;
        } catch (error) {
          const result = { error: true, message: error.response?.data?.detail || error.message };
          set({ importResult: result, importing: false });
          return result;
        }
      },

      clearImportResult: () => set({ importResult: null }),

      // Ricalcola progressivi
      ricalcolaProgressivi: async () => {
        const { anniEsclusi, filtroDipendente } = get();
        try {
          const params = new URLSearchParams();
          params.append('force_reset', 'true');
          if (anniEsclusi.length > 0) {
            params.append('anni_esclusi', anniEsclusi.join(','));
          }
          if (filtroDipendente) {
            params.append('dipendente', filtroDipendente);
          }
          await api.post(`/api/prima-nota-salari/ricalcola-progressivi?${params.toString()}`);
          await get().fetchSalari();
        } catch (error) {
          console.error('Errore ricalcolo:', error);
        }
      },

      // Delete record
      deleteRecord: async recordId => {
        try {
          await api.delete(`/api/prima-nota-salari/salari/${recordId}`);
          await get().fetchSalari();
          return true;
        } catch (error) {
          console.error('Error deleting record:', error);
          return false;
        }
      },

      // Update record
      updateRecord: async (recordId, data) => {
        try {
          await api.put(`/api/prima-nota-salari/salari/${recordId}`, data);
          await get().fetchSalari();
          return true;
        } catch (error) {
          console.error('Error updating record:', error);
          return false;
        }
      },

      // Reset all data
      resetAllData: async () => {
        try {
          await api.delete('/api/prima-nota-salari/salari/reset');
          await get().fetchSalari();
          await get().fetchDipendentiLista();
          return true;
        } catch (error) {
          console.error('Error resetting data:', error);
          return false;
        }
      },

      // Selectors (computed values with caching)
      getFilteredData: () => {
        const { salariMovimenti, anniEsclusi } = get();
        return salariMovimenti.filter(m => !anniEsclusi.includes(m.anno));
      },

      getTotals: () => {
        const state = get();
        if (state._totalsCache) return state._totalsCache;

        const filtered = state.getFilteredData();
        const totals = {
          records: filtered.length,
          totalRecords: state.salariMovimenti.length,
          totaleBuste: filtered.reduce((sum, m) => sum + (m.importo_busta || 0), 0),
          totaleBonifici: filtered.reduce((sum, m) => sum + (m.importo_bonifico || 0), 0),
          differenza: filtered.reduce(
            (sum, m) => sum + (m.importo_bonifico || 0) - (m.importo_busta || 0),
            0
          ),
        };

        // Cache the result
        set({ _totalsCache: totals });
        return totals;
      },
    }),
    { name: 'prima-nota-store' }
  )
);

// Selector hooks for optimized re-renders
export const useSalariMovimenti = () => usePrimaNotaStore(state => state.salariMovimenti);
export const useAnniEsclusi = () => usePrimaNotaStore(state => state.anniEsclusi);
export const useLoading = () => usePrimaNotaStore(state => state.loading);
export const useImporting = () => usePrimaNotaStore(state => state.importing);
