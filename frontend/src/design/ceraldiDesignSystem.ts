/**
 * CERALDI ERP – DESIGN SYSTEM (wrapper di compatibilità)
 * 
 * ⚠️  Non aggiungere nuovi colori qui.
 * ⚠️  Per nuove pagine, importare direttamente da './tokens.js'
 * 
 * Questo file rimane per retrocompatibilità con le pagine esistenti.
 * I valori sono stati allineati con tokens.js (primary = #1535a8).
 */

import type { CSSProperties } from 'react';

// Re-importa dai token unificati per allineamento
// (non importiamo direttamente per evitare problemi TS con .js)
export const COLORS = {
  primary:      '#1535a8',   // ✅ allineato con tokens.js
  primaryLight: '#2050e8',   // ✅ allineato
  success:      '#15803d',   // ✅ allineato (era #4caf50 — CORRETTO)
  warning:      '#d97706',   // ✅ allineato (era #ff9800 — CORRETTO)
  danger:       '#991b1b',
  info:         '#1535a8',
  purple:       '#7c3aed',
  gray:         '#6080a0',
  grayLight:    '#dce8f4',
  grayBg:       '#f2f6fd',
  white:        '#ffffff'
} as const;

export type ColorKey = keyof typeof COLORS;

export const SPACING = {
  xs:  4,
  sm:  8,
  md:  12,
  lg:  16,
  xl:  20,
  xxl: 24,
  xxxl: 32,
} as const;

export const TEXT: Record<string, CSSProperties> = {
  titleXL: { fontSize: 22, fontWeight: 800, letterSpacing: '-0.6px', color: '#09152a' },
  title:   { fontSize: 18, fontWeight: 700 },
  body:    { fontSize: 13 },
  small:   { fontSize: 11, color: COLORS.gray }
};

export const STYLES: Record<string, CSSProperties | ((...args: any[]) => CSSProperties)> = {
  page: {
    padding: SPACING.xl,
    maxWidth: 1440,
    margin: '0 auto',
    color: '#09152a',
    background: '#f2f6fd',
  },

  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.lg,
    padding: `${SPACING.lg}px ${SPACING.xl}px`,
    background: `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.primaryLight} 100%)`,
    borderRadius: 14,
    color: COLORS.white
  },

  card: {
    background: COLORS.white,
    borderRadius: 14,
    padding: SPACING.xl,
    boxShadow: '0 1px 4px rgba(8,24,80,.07)',
    border: `1.5px solid #dce8f4`
  },

  input: (error: boolean = false): CSSProperties => ({
    padding: '9px 12px',
    borderRadius: 8,
    border: error ? `2px solid ${COLORS.danger}` : `1.5px solid #dce8f4`,
    fontSize: 13,
    width: '100%',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
  }),

  select: {
    padding: '9px 12px',
    borderRadius: 8,
    border: `1.5px solid #dce8f4`,
    fontSize: 13,
    background: COLORS.white,
    boxSizing: 'border-box',
    fontFamily: 'inherit',
  },

  table: { width: '100%', borderCollapse: 'collapse' },

  th: {
    padding: '0 14px 10px',
    textAlign: 'left',
    fontWeight: 800,
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.7px',
    color: '#98b0c8',
    background: 'transparent',
    borderBottom: `1.5px solid #dce8f4`,
  },

  td: { padding: '10px 14px', borderBottom: '1px solid #dce8f4', fontSize: 13 }
};

export type ButtonType = 'primary' | 'secondary' | 'danger';

export function button(type: ButtonType = 'primary', disabled: boolean = false): CSSProperties {
  const base: CSSProperties = {
    padding: '8px 16px',
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 700,
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    fontFamily: 'inherit',
    transition: 'all .15s',
  };
  if (type === 'primary')   return { ...base, background: COLORS.primary, color: COLORS.white };
  if (type === 'secondary') return { ...base, background: '#eef3ff', color: COLORS.primary, border: '1.5px solid #cfe2ff' };
  if (type === 'danger')    return { ...base, background: COLORS.dangerBg || '#fee2e2', color: COLORS.danger };
  return base;
}
