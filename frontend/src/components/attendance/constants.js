/**
 * Costanti per il modulo Attendance
 */

// Stati presenza con colori
export const STATI_PRESENZA = {
  presente: { label: 'P', color: '#22c55e', bg: '#dcfce7', name: 'Presente' },
  assente: { label: 'A', color: '#ef4444', bg: '#fee2e2', name: 'Assente' },
  ferie: { label: 'F', color: '#f59e0b', bg: '#fef3c7', name: 'Ferie' },
  permesso: { label: 'PE', color: '#8b5cf6', bg: '#ede9fe', name: 'Permesso' },
  malattia: { label: 'M', color: '#3b82f6', bg: '#dbeafe', name: 'Malattia' },
  rol: { label: 'R', color: '#06b6d4', bg: '#cffafe', name: 'ROL' },
  chiuso: { label: 'CH', color: '#64748b', bg: '#e2e8f0', name: 'Chiuso' },
  riposo_settimanale: { label: 'RS', color: '#6b7280', bg: '#f3f4f6', name: 'Riposo Sett.' },
  trasferta: { label: 'T', color: '#6366f1', bg: '#e0e7ff', name: 'Trasferta' },
  cessato: { label: 'X', color: '#991b1b', bg: '#fef2f2', name: 'Cessato' },
  riposo: { label: '-', color: '#9ca3af', bg: '#f3f4f6', name: 'Riposo' },
  festivita_lavorata: { label: 'FL', color: '#059669', bg: '#d1fae5', name: 'Festività Lavorata' },
  festivita_non_lavorata: {
    label: 'FNL',
    color: '#0891b2',
    bg: '#cffafe',
    name: 'Festività Non Lavorata',
  },
};

// Giorni settimana abbreviati
export const GIORNI_SETTIMANA = ['D', 'L', 'M', 'M', 'G', 'V', 'S'];

// Nomi dei mesi
export const MESI = [
  'Gennaio',
  'Febbraio',
  'Marzo',
  'Aprile',
  'Maggio',
  'Giugno',
  'Luglio',
  'Agosto',
  'Settembre',
  'Ottobre',
  'Novembre',
  'Dicembre',
];

// Mansioni predefinite
export const MANSIONI_DEFAULT = [
  { id: 'cameriere', nome: 'Camerieri', color: '#3b82f6' },
  { id: 'cucina', nome: 'Cucina', color: '#22c55e' },
  { id: 'bar', nome: 'Bar', color: '#f59e0b' },
  { id: 'cassa', nome: 'Cassa', color: '#8b5cf6' },
  { id: 'pulizie', nome: 'Pulizie', color: '#64748b' },
];
