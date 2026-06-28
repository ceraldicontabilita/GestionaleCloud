import React from 'react';
import { clsx } from 'clsx';

/* ================================================================
   CERALDI ERP — DESIGN SYSTEM UNIFICATO
   Inline styles only · No Tailwind · No CSS-in-JS runtime
   Palette: Navy + Oro sobrio (contabile / professionale)
   ================================================================ */

export function cn(...inputs) {
  return clsx(inputs);
}

/* ---------- PALETTE CHIAVE ---------- */
export const COLORS = {
  /* Primari — salvia / verde bosco */
  primary: '#5b7a6b',
  primaryLight: '#6f9180',
  primaryDark: '#3f5a4e',
  primarySoft: '#e7eee9',
  /* Accent ocra (sostituisce l'oro) */
  accent: '#c4894a',
  accentLight: '#d49a5e',
  accentSoft: '#f3e9d8',
  /* Stato — caldi e desaturati, nessun freddo */
  success: '#3d8168',
  successLight: '#e2ede8',
  warning: '#c4894a',
  warningLight: '#f3e9d8',
  danger: '#d35f4e',
  dangerLight: '#f6e2dd',
  info: '#8a6f47',        // sabbia, ex blu
  infoLight: '#ece3d4',
  /* Neutri crema/sabbia */
  bg: '#faf7f0',
  bgAlt: '#f4efe4',
  card: '#fffefb',
  border: '#e6e0d4',
  borderDark: '#d8cfbd',
  text: '#2c2418',
  textMuted: '#7a6f5d',
  textSubtle: '#a89a82',
  /* Scala sabbia (sostituisce i grigi slate) */
  gray: {
    50: '#faf7f0',
    100: '#f4efe4',
    200: '#e6e0d4',
    300: '#d8cfbd',
    400: '#b3a486',
    500: '#8a7a5c',
    600: '#6e5f44',
    700: '#524833',
    800: '#3d3526',
    900: '#2c2418',
  },
  /* Legacy aliases */
  white: '#fffefb',
  grayLight: '#e6e0d4',
  grayBg: '#f4efe4',
  purple: '#8a6f47',   // ex viola → sabbia (niente freddi)
};

/* Theme alias: usato in diverse pagine legacy */
export const THEME = {
  primary: COLORS.primary,
  primaryLight: COLORS.primaryLight,
  primaryDark: COLORS.primaryDark,
  success: COLORS.success,
  successLight: COLORS.successLight,
  warning: COLORS.warning,
  warningLight: COLORS.warningLight,
  error: COLORS.danger,
  errorLight: COLORS.dangerLight,
  info: COLORS.info,
  infoLight: COLORS.infoLight,
  gray: COLORS.gray,
};

/* ---------- SPAZIATURE ---------- */
export const SPACING = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };

/* ---------- OMBRE ---------- */
export const SHADOWS = {
  sm: '0 1px 6px rgba(63,90,78,0.06)',
  md: '0 2px 10px rgba(63,90,78,0.08)',
  lg: '0 6px 16px rgba(91,122,107,0.14)',
  xl: '0 12px 32px rgba(63,90,78,0.16)',
};

/* ---------- RADIUS ---------- */
export const BORDER_RADIUS = { sm: 8, md: 12, lg: 16, xl: 20, full: 9999 };

/* ---------- TIPOGRAFIA ---------- */
export const FONT = {
  family: "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  serif: "'Fraunces', Georgia, 'Times New Roman', serif",   // titoli e valori stat
  mono: "'JetBrains Mono', 'SF Mono', Menlo, Monaco, Consolas, monospace",
};

/* ================================================================
   STILI BASE
   ================================================================ */
export const STYLES = {
  /* Pagina: full-frame, no max-width */
  page: {
    width: '100%',
    maxWidth: '100%',
    padding: 0,
    margin: 0,
    boxSizing: 'border-box',
    background: 'transparent',
    color: COLORS.text,
  },

  /* Wrapper interno quando serve un minimo di padding laterale */
  pageInner: {
    width: '100%',
    maxWidth: '100%',
    padding: `${SPACING.lg}px ${SPACING.xxl}px`,
    boxSizing: 'border-box',
  },

  /* Header pagina — stile sobrio, senza gradiente aggressivo */
  pageHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: `${SPACING.lg}px ${SPACING.xl}px`,
    background: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderLeft: `4px solid ${COLORS.primary}`,
    borderRadius: BORDER_RADIUS.md,
    color: COLORS.text,
    flexWrap: 'wrap',
    gap: SPACING.md,
    marginBottom: SPACING.lg,
    boxShadow: SHADOWS.sm,
  },

  pageTitle: {
    margin: 0,
    fontSize: 20,
    fontWeight: 700,
    color: COLORS.primary,
    letterSpacing: '-0.2px',
    display: 'flex',
    alignItems: 'center',
    gap: SPACING.sm,
  },

  pageSubtitle: {
    margin: 0,
    fontSize: 13,
    color: COLORS.textMuted,
    fontWeight: 500,
  },

  /* Header legacy — gradiente morbido (retrocompat) */
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.lg,
    padding: `${SPACING.lg}px ${SPACING.xl}px`,
    background: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderLeft: `4px solid ${COLORS.primary}`,
    borderRadius: BORDER_RADIUS.md,
    color: COLORS.text,
    flexWrap: 'wrap',
    gap: 12,
    boxShadow: SHADOWS.sm,
  },

  /* Card base */
  card: {
    background: COLORS.card,
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.xl,
    boxShadow: SHADOWS.sm,
    border: `1px solid ${COLORS.border}`,
  },

  cardHover: {
    background: COLORS.card,
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.xl,
    boxShadow: SHADOWS.sm,
    border: `1px solid ${COLORS.border}`,
    transition: 'box-shadow 160ms ease, transform 160ms ease, border-color 160ms ease',
    cursor: 'pointer',
  },

  /* Sezione dentro una pagina */
  section: {
    marginBottom: SPACING.lg,
  },

  sectionTitle: {
    margin: `0 0 ${SPACING.md}px 0`,
    fontSize: 14,
    fontWeight: 700,
    color: COLORS.primary,
    textTransform: 'uppercase',
    letterSpacing: '0.6px',
    display: 'flex',
    alignItems: 'center',
    gap: SPACING.sm,
  },

  /* Inputs */
  input: {
    padding: '9px 12px',
    borderRadius: BORDER_RADIUS.sm,
    border: `1px solid ${COLORS.border}`,
    fontSize: 13,
    width: '100%',
    boxSizing: 'border-box',
    background: COLORS.card,
    color: COLORS.text,
    outline: 'none',
    transition: 'border-color 140ms ease, box-shadow 140ms ease',
    fontFamily: FONT.family,
  },

  select: {
    padding: '9px 12px',
    borderRadius: BORDER_RADIUS.sm,
    border: `1px solid ${COLORS.border}`,
    fontSize: 13,
    background: COLORS.card,
    color: COLORS.text,
    boxSizing: 'border-box',
    outline: 'none',
    cursor: 'pointer',
    fontFamily: FONT.family,
  },

  /* Tabelle */
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 13,
    background: COLORS.card,
  },

  tableWrap: {
    overflowX: 'auto',
    WebkitOverflowScrolling: 'touch',
    width: '100%',
    borderRadius: BORDER_RADIUS.md,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.card,
  },

  th: {
    padding: '10px 14px',
    textAlign: 'left',
    fontWeight: 700,
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: '0.4px',
    color: COLORS.textMuted,
    background: COLORS.bgAlt,
    borderBottom: `1px solid ${COLORS.border}`,
    whiteSpace: 'nowrap',
  },

  td: {
    padding: '10px 14px',
    borderBottom: `1px solid ${COLORS.gray[100]}`,
    color: COLORS.text,
    fontSize: 13,
    verticalAlign: 'middle',
  },

  /* Griglie responsive */
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: SPACING.lg,
  },

  kpiGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: SPACING.md,
    marginBottom: SPACING.lg,
  },

  /* Flex utility */
  flexRow: {
    display: 'flex',
    gap: SPACING.sm,
    alignItems: 'center',
    flexWrap: 'wrap',
  },

  flexBetween: {
    display: 'flex',
    gap: SPACING.sm,
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
  },

  /* Tab bar orizzontale */
  tabBar: {
    display: 'flex',
    gap: 6,
    padding: `${SPACING.sm}px ${SPACING.xxl}px`,
    background: COLORS.card,
    borderBottom: `1px solid ${COLORS.border}`,
    flexWrap: 'wrap',
    alignItems: 'center',
  },

  /* KPI / Stat box */
  statBox: {
    background: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderLeft: `3px solid ${COLORS.primary}`,
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.lg,
    boxShadow: SHADOWS.sm,
  },
};

/* ================================================================
   BOTTONI
   ================================================================ */
export function button(type = 'primary', disabled = false) {
  const base = {
    padding: '8px 16px',
    borderRadius: BORDER_RADIUS.sm,
    fontSize: 13,
    fontWeight: 600,
    border: '1px solid transparent',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.55 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    lineHeight: 1.2,
    transition:
      'background 140ms ease, border-color 140ms ease, color 140ms ease, box-shadow 140ms ease',
    fontFamily: FONT.family,
    whiteSpace: 'nowrap',
  };

  if (type === 'primary') {
    return { ...base, background: COLORS.primary, color: '#fff', borderColor: COLORS.primary };
  }
  if (type === 'secondary') {
    return { ...base, background: COLORS.card, color: COLORS.text, borderColor: COLORS.border };
  }
  if (type === 'ghost') {
    return {
      ...base,
      background: 'transparent',
      color: COLORS.textMuted,
      borderColor: 'transparent',
    };
  }
  if (type === 'success') {
    return { ...base, background: COLORS.success, color: '#fff', borderColor: COLORS.success };
  }
  if (type === 'danger') {
    return { ...base, background: COLORS.danger, color: '#fff', borderColor: COLORS.danger };
  }
  if (type === 'info') {
    return { ...base, background: COLORS.info, color: '#fff', borderColor: COLORS.info };
  }
  if (type === 'warning') {
    return { ...base, background: COLORS.warning, color: '#fff', borderColor: COLORS.warning };
  }
  if (type === 'outline') {
    return {
      ...base,
      background: 'transparent',
      color: COLORS.primary,
      borderColor: COLORS.primary,
    };
  }
  return base;
}

/* ================================================================
   BADGE
   ================================================================ */
export function badge(type) {
  const base = {
    padding: '3px 9px',
    borderRadius: BORDER_RADIUS.full,
    fontSize: 11,
    fontWeight: 700,
    display: 'inline-block',
    letterSpacing: '0.2px',
    textTransform: 'uppercase',
    lineHeight: 1.4,
  };
  if (type === 'success')
    return { ...base, background: COLORS.successLight, color: COLORS.success };
  if (type === 'warning')
    return { ...base, background: COLORS.warningLight, color: COLORS.warning };
  if (type === 'danger') return { ...base, background: COLORS.dangerLight, color: COLORS.danger };
  if (type === 'info') return { ...base, background: COLORS.infoLight, color: COLORS.info };
  if (type === 'neutral') return { ...base, background: COLORS.gray[100], color: COLORS.gray[700] };
  if (type === 'primary') return { ...base, background: COLORS.primarySoft, color: COLORS.primary };
  if (type === 'accent') return { ...base, background: COLORS.accentSoft, color: COLORS.accent };
  return { ...base, background: COLORS.gray[100], color: COLORS.gray[700] };
}

/* ================================================================
   FORMATTAZIONE ITALIANA
   ================================================================ */
export function formatDateIT(dateStr) {
  if (!dateStr) return '-';
  try {
    const datePart = dateStr.includes('T') ? dateStr.split('T')[0] : dateStr;
    const parts = datePart.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return dateStr;
  } catch {
    return dateStr;
  }
}

export function parseDateIT(dateStr) {
  if (!dateStr) return null;
  try {
    const parts = dateStr.split('/');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return dateStr;
  } catch {
    return dateStr;
  }
}

export function formatEuro(amount) {
  if (amount === null || amount === undefined) return '€ 0';
  const v = parseFloat(amount);
  if (isNaN(v)) return '€ 0';
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(v));
}

// formatEuroD — con decimali, per tabelle dettaglio e tooltip
export function formatEuroD(amount) {
  if (amount === null || amount === undefined) return '€ 0,00';
  return `€ ${new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  }).format(parseFloat(amount))}`;
}

export function formatDateTimeIT(dateStr) {
  if (!dateStr) return '-';
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export function formatDateShort(dateStr) {
  if (!dateStr) return '-';
  try {
    const datePart = dateStr.includes('T') ? dateStr.split('T')[0] : dateStr;
    const parts = datePart.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}`;
    return dateStr;
  } catch {
    return dateStr;
  }
}

export function formatEuroShort(amount) {
  if (amount === null || amount === undefined) return '0,00';
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  }).format(parseFloat(amount));
}

export function formatEuroStr(amount) {
  if (amount === null || amount === undefined) return '€ 0,00';
  return formatEuro(amount);
}

/* ================================================================
   COSTANTI MESI
   ================================================================ */
export const MESI_SHORT = [
  'Gen',
  'Feb',
  'Mar',
  'Apr',
  'Mag',
  'Giu',
  'Lug',
  'Ago',
  'Set',
  'Ott',
  'Nov',
  'Dic',
];
export const MESI_FULL = [
  '',
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
  { key: '12', value: 12, label: 'Dicembre', short: 'Dic' },
];

/* ================================================================
   RESPONSIVE HELPERS
   ================================================================ */

/** Hook: true se viewport <= breakpoint (default 768) */
export function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = React.useState(
    () => typeof window !== 'undefined' && window.innerWidth <= breakpoint
  );
  React.useEffect(() => {
    const check = () => setIsMobile(window.innerWidth <= breakpoint);
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, [breakpoint]);
  return isMobile;
}

/** gridTemplateColumns responsive rapido */
export function rg(isMobile, desktopCols) {
  return isMobile ? '1fr' : desktopCols;
}

/** Preset grid responsive */
export const RG = {
  col2: m => ({ display: 'grid', gridTemplateColumns: m ? '1fr' : '1fr 1fr', gap: 16 }),
  col3: m => ({ display: 'grid', gridTemplateColumns: m ? '1fr' : 'repeat(3,1fr)', gap: 16 }),
  col4: m => ({ display: 'grid', gridTemplateColumns: m ? '1fr 1fr' : 'repeat(4,1fr)', gap: 12 }),
  col24: m => ({ display: 'grid', gridTemplateColumns: m ? '1fr' : '2fr 4fr', gap: 16 }),
  kpi: m => ({ display: 'grid', gridTemplateColumns: m ? '1fr 1fr' : 'repeat(4,1fr)', gap: 12 }),
  form: m => ({ display: 'grid', gridTemplateColumns: m ? '1fr' : '1fr 1fr', gap: 16 }),
};

/** Padding pagina responsive */
export function pagePad(isMobile) {
  return isMobile ? '12px 14px' : '16px 24px';
}

/* ================================================================
   UTILITY PER TAB ATTIVI (usata nei vari hub)
   ================================================================ */
export function tabStyle(isActive, color) {
  const accent = color || COLORS.primary;
  return {
    padding: '8px 14px',
    borderRadius: BORDER_RADIUS.sm,
    border: `1px solid ${isActive ? accent : COLORS.border}`,
    fontWeight: isActive ? 700 : 500,
    fontSize: 12.5,
    cursor: 'pointer',
    transition: 'all 140ms ease',
    background: isActive ? accent : COLORS.card,
    color: isActive ? '#fff' : COLORS.textMuted,
    boxShadow: isActive ? SHADOWS.sm : 'none',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    fontFamily: FONT.family,
  };
}
