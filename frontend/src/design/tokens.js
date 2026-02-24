/**
 * CERALDI ERP — DESIGN TOKENS (unica fonte di verità)
 * 
 * Importare SEMPRE da questo file, non da ceraldiDesignSystem.ts o pageLayoutStyle.js
 * 
 * COLORI: blu scuro #1535a8 come accent principale
 * FONT: Plus Jakarta Sans (UI) + JetBrains Mono (numeri)
 */

// ─── PALETTE ──────────────────────────────────────────────
export const COLOR = {
  // Brand / Accent
  brand:         '#1535a8',
  brandLight:    '#2050e8',
  brandDark:     '#0f2785',
  brandBg:       '#eef3ff',
  brandBorder:   '#cfe2ff',
  brandMid:      '#4a7cf5',

  // Stato
  success:       '#15803d',
  successBg:     '#dcfce7',
  successBorder: '#86efac',
  warning:       '#92400e',
  warningBg:     '#fef3c7',
  warningBorder: '#fcd34d',
  danger:        '#991b1b',
  dangerBg:      '#fee2e2',
  dangerBorder:  '#fca5a5',
  info:          '#1535a8',
  infoBg:        '#eef3ff',

  // Neutrals
  ink:           '#09152a',
  ink2:          '#2d4466',
  ink3:          '#6080a0',
  ink4:          '#98b0c8',
  border:        '#dce8f4',
  bg:            '#f2f6fd',
  surface:       '#ffffff',

  // Nav
  navBg:         '#d9e8f8',
  navBorder:     '#b5cff0',
};

// ─── SPACING ──────────────────────────────────────────────
export const SPACE = {
  xs:  4,
  sm:  8,
  md:  12,
  lg:  16,
  xl:  20,
  xxl: 24,
  xxxl: 32,
};

// ─── RADIUS ───────────────────────────────────────────────
export const RADIUS = {
  sm: 6,
  md: 10,
  lg: 14,
  full: 9999,
};

// ─── SHADOWS ──────────────────────────────────────────────
export const SHADOW = {
  sm:  '0 1px 4px rgba(8,24,80,.07)',
  md:  '0 5px 20px rgba(8,24,80,.11)',
  lg:  '0 12px 44px rgba(8,24,80,.16)',
};

// ─── TYPOGRAPHY ───────────────────────────────────────────
export const FONT = {
  ui:   "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  mono: "'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace",

  xs:   10,
  sm:   11,
  base: 12,
  md:   13,
  lg:   14,
  xl:   16,
  xxl:  18,
  xxxl: 22,
};

// ─── COMPONENT STYLES (oggetti pronti da usare inline) ────
export const STYLES = {
  // Pagina base
  page: {
    fontFamily: FONT.ui,
    padding: `${SPACE.xl}px ${SPACE.xxl}px ${SPACE.xxxl * 2}px`,
    maxWidth: 1440,
    margin: '0 auto',
    color: COLOR.ink,
    background: COLOR.bg,
    minHeight: '100%',
  },

  // Card standard
  card: {
    background: COLOR.surface,
    border: `1.5px solid ${COLOR.border}`,
    borderRadius: RADIUS.lg,
    overflow: 'hidden',
    boxShadow: SHADOW.sm,
  },

  // Card header
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: `${SPACE.md}px ${SPACE.lg + 2}px`,
    borderBottom: `1px solid ${COLOR.border}`,
  },

  // Table
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontFamily: FONT.ui,
    fontSize: FONT.md,
  },
  th: {
    padding: '0 14px 10px',
    textAlign: 'left',
    fontSize: FONT.xs,
    fontWeight: 800,
    textTransform: 'uppercase',
    letterSpacing: '0.7px',
    color: COLOR.ink4,
  },
  td: {
    padding: '10px 14px',
    borderTop: `1px solid ${COLOR.border}`,
    verticalAlign: 'middle',
    fontSize: FONT.md,
  },

  // Pill / Badge
  pill: (variant = 'blue') => {
    const variants = {
      green:   { background: COLOR.successBg,  color: COLOR.success },
      amber:   { background: COLOR.warningBg,  color: COLOR.warning },
      red:     { background: COLOR.dangerBg,   color: COLOR.danger  },
      blue:    { background: COLOR.brandBg,    color: COLOR.brand   },
      neutral: { background: '#f1f5f9',         color: COLOR.ink3   },
    };
    return {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '3px 9px',
      borderRadius: RADIUS.full,
      fontSize: FONT.sm,
      fontWeight: 700,
      ...(variants[variant] || variants.blue),
    };
  },

  // Buttons
  btnPrimary: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 16px',
    borderRadius: RADIUS.md,
    fontFamily: 'inherit',
    fontSize: FONT.md,
    fontWeight: 700,
    cursor: 'pointer',
    border: 'none',
    background: COLOR.brand,
    color: COLOR.surface,
    transition: 'all .15s',
  },
  btnSecondary: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 16px',
    borderRadius: RADIUS.md,
    fontFamily: 'inherit',
    fontSize: FONT.md,
    fontWeight: 700,
    cursor: 'pointer',
    border: `1.5px solid ${COLOR.brandBorder}`,
    background: COLOR.surface,
    color: COLOR.brand,
    transition: 'all .15s',
  },

  // Page header
  pageHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    marginBottom: 20,
  },
  pageTitle: {
    fontSize: FONT.xxxl,
    fontWeight: 800,
    letterSpacing: '-0.6px',
    color: COLOR.ink,
    lineHeight: 1.2,
  },
  pageSubtitle: {
    fontSize: FONT.base,
    color: COLOR.ink3,
    marginTop: 3,
  },

  // Mono number
  mono: {
    fontFamily: FONT.mono,
    fontSize: FONT.base,
  },

  // KPI card
  kpiCard: {
    background: COLOR.surface,
    border: `1.5px solid ${COLOR.border}`,
    borderRadius: RADIUS.lg,
    padding: '18px 20px',
    transition: 'all .18s',
  },
};

// ─── RE-EXPORT per compatibilità legacy ──────────────────
// Permettono a ceraldiDesignSystem.ts e pageLayoutStyle.js di
// essere aggiornati gradualmente senza rompere le importazioni esistenti
export const COLORS = {
  primary:      COLOR.brand,
  primaryLight: COLOR.brandLight,
  success:      COLOR.success,
  warning:      '#d97706',
  danger:       COLOR.danger,
  info:         COLOR.brand,
  gray:         COLOR.ink3,
  grayLight:    COLOR.border,
  grayBg:       COLOR.bg,
  white:        COLOR.surface,
};

// PAGE_WRAPPER / PAGE_CONTAINER per PageLayout.jsx
export const PAGE_WRAPPER = {
  minHeight: '100%',
  background: COLOR.bg,
  fontFamily: FONT.ui,
};

export const PAGE_CONTAINER = {
  background: COLOR.surface,
  borderRadius: RADIUS.lg,
  boxShadow: SHADOW.md,
  overflow: 'hidden',
};

export const PAGE_HEADER = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '16px 20px',
  borderBottom: `1px solid ${COLOR.border}`,
  background: COLOR.surface,
  flexWrap: 'wrap',
  gap: 12,
};

export const PAGE_CONTENT = {
  padding: 20,
  flex: 1,
};

export const PAGE_TITLE = {
  fontSize: FONT.xxxl,
  fontWeight: 800,
  letterSpacing: '-0.6px',
  color: COLOR.ink,
};

export const PAGE_SUBTITLE = {
  fontSize: FONT.base,
  color: COLOR.ink3,
  marginTop: 3,
};

export const HEADER_ACTIONS = {
  display: 'flex',
  gap: 8,
  alignItems: 'center',
};

export const TABS_CONTAINER = {
  display: 'flex',
  gap: 4,
  padding: '0 20px',
  borderBottom: `1px solid ${COLOR.border}`,
  background: COLOR.bg,
};

export const TAB_STYLE = (active = false) => ({
  padding: '8px 14px',
  fontSize: FONT.md,
  fontWeight: active ? 700 : 500,
  color: active ? COLOR.brand : COLOR.ink3,
  cursor: 'pointer',
  borderBottom: active ? `2px solid ${COLOR.brand}` : '2px solid transparent',
  background: 'none',
  border: 'none',
  borderBottom: active ? `2px solid ${COLOR.brand}` : '2px solid transparent',
  fontFamily: 'inherit',
});
