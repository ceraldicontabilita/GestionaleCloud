import type { CSSProperties } from 'react';

/* ================================
   CERALDI ERP – DESIGN SYSTEM
   TYPE SCRIPT TIPIZZATO
   INLINE STYLE ONLY
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
} as const;

export type ColorKey = keyof typeof COLORS;

/* ---------- SPAZIATURE ---------- */
export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24
} as const;

/* ---------- TESTI ---------- */
export const TEXT: Record<string, CSSProperties> = {
  titleXL: { fontSize: 22, fontWeight: 'bold' },
  title: { fontSize: 18, fontWeight: 600 },
  body: { fontSize: 14 },
  small: { fontSize: 12, color: COLORS.gray }
};

/* ---------- STILI BASE ---------- */
export const STYLES: Record<string, CSSProperties | ((...args: any[]) => CSSProperties)> = {
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
    background: COLORS.primary,
    borderRadius: 12,
    color: COLORS.white
  },

  card: {
    background: COLORS.white,
    borderRadius: 12,
    padding: SPACING.xl,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    border: `1px solid ${COLORS.grayLight}`
  },

  input: (error: boolean = false): CSSProperties => ({
    padding: '10px 12px',
    borderRadius: 8,
    border: error
      ? `2px solid ${COLORS.danger}`
      : `2px solid ${COLORS.grayLight}`,
    fontSize: 14,
    width: '100%',
    boxSizing: 'border-box'
  }),

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
  }
};

/* ---------- BOTTONI ---------- */
export type ButtonType = 'primary' | 'secondary' | 'danger';

export function button(
  type: ButtonType = 'primary',
  disabled: boolean = false
): CSSProperties {
  return {
    padding: '10px 20px',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    ...(type === 'primary' && {
      background: COLORS.success,
      color: COLORS.white
    }),
    ...(type === 'secondary' && {
      background: COLORS.grayLight,
      color: '#374151'
    }),
    ...(type === 'danger' && {
      background: COLORS.danger,
      color: COLORS.white
    })
  };
}

/* ---------- BADGE ---------- */
export type BadgeType = 'success' | 'warning' | 'danger' | 'info';

export function badge(type: BadgeType): CSSProperties {
  return {
    padding: '4px 10px',
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 600,
    ...(type === 'success' && { background: '#dcfce7', color: '#16a34a' }),
    ...(type === 'warning' && { background: '#fef3c7', color: '#d97706' }),
    ...(type === 'danger' && { background: '#fee2e2', color: '#dc2626' }),
    ...(type === 'info' && { background: '#e0f2fe', color: '#0284c7' })
  };
}

/* ---------- LAYOUT ---------- */
export const grid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
  gap: SPACING.lg
};

export const flexRow: CSSProperties = {
  display: 'flex',
  gap: SPACING.sm,
  alignItems: 'center',
  flexWrap: 'wrap'
};

/* ================================
   FORMATTAZIONE ITALIANA
   ================================ */

export function formatDateIT(date?: Date | string | null): string {
  if (!date) return '';
  return new Date(date).toLocaleDateString('it-IT');
}

export function formatDateTimeIT(date?: Date | string | null): string {
  if (!date) return '';
  return new Date(date).toLocaleString('it-IT');
}

export function formatEuro(value?: number | null): string {
  if (value == null || isNaN(value)) return '€ 0,00';
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: 'EUR'
  }).format(value);
}

export function formatEuroNumber(value?: number | null): string {
  if (value == null || isNaN(value)) return '0,00';
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

export function formatEuroSigned(value?: number | null): string {
  const n = Number(value ?? 0);
  const abs = formatEuro(Math.abs(n));
  return n < 0 ? `− ${abs}` : abs;
}

export function formatPercent(value?: number | null): string {
  if (value == null || isNaN(value)) return '0%';
  return `${value.toLocaleString('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}%`;
}
