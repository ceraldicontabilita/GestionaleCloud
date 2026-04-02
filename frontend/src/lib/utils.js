import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/* ================================
   CERALDI ERP – DESIGN SYSTEM
   INLINE STYLE ONLY (NO TAILWIND)
   ================================ */

/* ---------- COLORI ---------- */
export const COLORS = {
  primary: '#1e3a5f',
  primaryLight: '#2d5a87',
  success: '#4caf50',
  warning: '#ff9800',
  danger: '#ef4444',
  info: '#2196f3',
  purple: '#9c27b0',
  gray: '#6b7280',
  grayLight: '#e5e7eb',
  grayBg: '#f9fafb',
  white: '#ffffff'
};

/* ---------- SPAZIATURE ---------- */
export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24
};

/* ---------- STILI BASE ---------- */
export const STYLES = {
  page: {
    padding: SPACING.xl,
    maxWidth: 1400,
    margin: '0 auto'
  },

  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.lg,
    padding: `${SPACING.lg}px ${SPACING.xl}px`,
    background: `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.primaryLight} 100%)`,
    borderRadius: 12,
    color: COLORS.white,
    flexWrap: 'wrap',
    gap: 12
  },

  card: {
    background: COLORS.white,
    borderRadius: 12,
    padding: SPACING.xl,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    border: `1px solid ${COLORS.grayLight}`
  },

  input: {
    padding: '10px 12px',
    borderRadius: 8,
    border: `2px solid ${COLORS.grayLight}`,
    fontSize: 14,
    width: '100%',
    boxSizing: 'border-box'
  },

  select: {
    padding: '10px 12px',
    borderRadius: 8,
    border: `2px solid ${COLORS.grayLight}`,
    fontSize: 14,
    background: COLORS.white,
    boxSizing: 'border-box'
  },

  table: {
    width: '100%',
    borderCollapse: 'collapse'
  },

  th: {
    padding: '12px 16px',
    textAlign: 'left',
    fontWeight: 600,
    background: COLORS.grayBg,
    borderBottom: `2px solid ${COLORS.grayLight}`
  },

  td: {
    padding: '12px 16px',
    borderBottom: '1px solid #f3f4f6'
  },

  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
    gap: SPACING.lg
  },

  flexRow: {
    display: 'flex',
    gap: SPACING.sm,
    alignItems: 'center',
    flexWrap: 'wrap'
  }
};

/* ---------- BOTTONI ---------- */
export function button(type = 'primary', disabled = false) {
  const base = {
    padding: '10px 20px',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8
  };
  
  if (type === 'primary') {
    return { ...base, background: COLORS.success, color: COLORS.white };
  }
  if (type === 'secondary') {
    return { ...base, background: COLORS.grayLight, color: '#374151' };
  }
  if (type === 'danger') {
    return { ...base, background: COLORS.danger, color: COLORS.white };
  }
  if (type === 'info') {
    return { ...base, background: COLORS.info, color: COLORS.white };
  }
  if (type === 'warning') {
    return { ...base, background: COLORS.warning, color: COLORS.white };
  }
  return base;
}

/* ---------- BADGE ---------- */
export function badge(type) {
  const base = {
    padding: '4px 10px',
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 600,
    display: 'inline-block'
  };
  
  if (type === 'success') return { ...base, background: '#dcfce7', color: '#16a34a' };
  if (type === 'warning') return { ...base, background: '#fef3c7', color: '#d97706' };
  if (type === 'danger') return { ...base, background: '#fee2e2', color: '#dc2626' };
  if (type === 'info') return { ...base, background: '#e0f2fe', color: '#0284c7' };
  return base;
}

/* ================================
   FORMATTAZIONE ITALIANA
   ================================ */

/**
 * Converte una data ISO (YYYY-MM-DD) in formato italiano (gg/mm/aaaa)
 */
export function formatDateIT(dateStr) {
  if (!dateStr) return "-";
  try {
    // Se contiene T, prendi solo la parte data
    const datePart = dateStr.includes("T") ? dateStr.split("T")[0] : dateStr;
    const parts = datePart.split("-");
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

/**
 * Converte una data italiana (gg/mm/aaaa) in formato ISO (YYYY-MM-DD)
 */
export function parseDateIT(dateStr) {
  if (!dateStr) return null;
  try {
    const parts = dateStr.split("/");
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

/**
 * Formatta un importo in euro con formato italiano
 * Usa il punto come separatore delle migliaia e la virgola per i decimali
 * Es: 5830.62 -> € 5.830,62
 */
export function formatEuro(amount) {
  if (amount === null || amount === undefined) return "€ 0,00";
  return `€ ${new Intl.NumberFormat('it-IT', { 
    minimumFractionDigits: 2, 
    maximumFractionDigits: 2,
    useGrouping: true
  }).format(parseFloat(amount))}`;
}

/**
 * Formatta data e ora in italiano
 */
export function formatDateTimeIT(dateStr) {
  if (!dateStr) return "-";
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return dateStr;
  }
}

/**
 * Formatta data in formato breve (gg/mm)
 */
export function formatDateShort(dateStr) {
  if (!dateStr) return "-";
  try {
    const datePart = dateStr.includes("T") ? dateStr.split("T")[0] : dateStr;
    const parts = datePart.split("-");
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}`;
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

/**
 * Formatta euro senza simbolo (solo numero)
 */
export function formatEuroShort(amount) {
  if (amount === null || amount === undefined) return "0,00";
  return new Intl.NumberFormat('it-IT', { 
    minimumFractionDigits: 2, 
    maximumFractionDigits: 2,
    useGrouping: true
  }).format(parseFloat(amount));
}

/**
 * Formatta euro come stringa semplice
 */
export function formatEuroStr(amount) {
  if (amount === null || amount === undefined) return "€ 0,00";
  return formatEuro(amount);
}

/* ================================
   COSTANTI MESI
   ================================ */

export const MESI_SHORT = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

export const MESI_FULL = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];

export const MESI = [
  { key: '01', value: 1, label: 'Gennaio', short: 'Gen' },
  { key: '02', value: 2, label: 'Febbraio', short: 'Feb' },
  { key: '03', value: 3, label: 'Marzo', short: 'Mar' },
  { key: '04', value: 4, label: 'Aprile', short: 'Apr' },
  { key: '05', value: 5, label: 'Maggio', short: 'Mag' },
  { key: '06', value: 6, label: 'Giugno', short: 'Giu' },
  { key: '07', value: 7, label: 'Luglio', short: 'Lug' },
  { key: '08', value: 8, label: 'Agosto', short: 'Ago' },
  { key: '09', value: 9, label: 'Settembre', short: 'Set' },
  { key: '10', value: 10, label: 'Ottobre', short: 'Ott' },
  { key: '11', value: 11, label: 'Novembre', short: 'Nov' },
  { key: '12', value: 12, label: 'Dicembre', short: 'Dic' }
];

/* ================================
   DESIGN SYSTEM / THEME
   ================================ */

export const THEME = {
  primary: '#1e3a5f',
  primaryLight: '#2d5a87',
  primaryDark: '#152a47',
  success: '#16a34a',
  successLight: '#dcfce7',
  warning: '#f59e0b',
  warningLight: '#fef3c7',
  error: '#dc2626',
  errorLight: '#fee2e2',
  info: '#2563eb',
  infoLight: '#dbeafe',
  gray: {
    50: '#f9fafb',
    100: '#f3f4f6',
    200: '#e5e7eb',
    300: '#d1d5db',
    400: '#9ca3af',
    500: '#6b7280',
    600: '#4b5563',
    700: '#374151',
    800: '#1f2937',
    900: '#111827'
  }
};

export const SHADOWS = {
  sm: '0 1px 2px rgba(0,0,0,0.05)',
  md: '0 2px 8px rgba(0,0,0,0.08)',
  lg: '0 4px 12px rgba(0,0,0,0.12)',
  xl: '0 8px 24px rgba(0,0,0,0.16)'
};

export const BORDER_RADIUS = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  full: 9999
};

