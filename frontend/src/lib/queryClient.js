/**
 * React Query Configuration
 * Gestisce caching, refetching e sincronizzazione dati
 */
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Cache dati per 5 minuti
      staleTime: 5 * 60 * 1000,
      // Mantieni cache per 30 minuti
      gcTime: 30 * 60 * 1000,
      // Retry 2 volte in caso di errore
      retry: 2,
      // Refetch automatico quando la finestra torna in focus (staleTime: 5min previene abusi)
      refetchOnWindowFocus: true,
      // Refetch in background quando i dati sono stale
      refetchOnMount: true,
    },
    mutations: {
      // Retry 1 volta per le mutazioni
      retry: 1,
    },
  },
});

// Query keys per organizzare le cache
export const queryKeys = {
  // Prima Nota Salari
  primaNota: {
    all: ['prima-nota'],
    salari: (filters) => ['prima-nota', 'salari', filters],
    dipendenti: () => ['prima-nota', 'dipendenti'],
  },
  // Libro Unico
  libroUnico: {
    all: ['libro-unico'],
    salaries: (monthYear) => ['libro-unico', 'salaries', monthYear],
  },
  // Libretti Sanitari
  libretti: {
    all: ['libretti'],
    list: () => ['libretti', 'list'],
  },
  // Contratti
  contratti: {
    all: ['contratti'],
    list: () => ['contratti', 'list'],
    scadenze: () => ['contratti', 'scadenze'],
  },
  // Dipendenti
  dipendenti: {
    all: ['dipendenti'],
    list: (filters) => ['dipendenti', 'list', filters],
    detail: (id) => ['dipendenti', 'detail', id],
  },
};
