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
  /* Primari */
  primary:       '#0f2744',   // navy profondo — brand
  primaryLight:  '#1e3a5f',
  primaryDark:   '#081425',
  primarySoft:   '#e8eef7',   // bg tab attivo chiaro
  /* Accent oro */
  accent:        '#b8860b',
  accentLight:   '#d4a017',
  accentSoft:    '#fdf6e3',
  /* Stato */
  success:       '#15803d',
  successLight:  '#dcfce7',
  warning:       '#b45309',
  warningLight:  '#fef3c7',
  danger:        '#b91c1c',
  dangerLight:   '#fee2e2',
  info:          '#1d4ed8',
  infoLight:     '#dbeafe',
  /* Neutri */
  bg:            '#f1f5f9',   // sfondo pagina
  bgAlt:         '#f8fafc',
  card:          '#ffffff',
  border:        '#e2e8f0',
  borderDark:    '#cbd5e1',
  text:          '#0f172a',
  textMuted:     '#64748b',
  textSubtle:    '#94a3b8',
  /* Grays */
  gray: {
    50:  '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1',
    400: '#94a3b8', 500: '#64748b', 600: '#475569', 700: '#334155',
    800: '#1e293b', 900: '#0f172a',
  },
  /* Legacy aliases (per retro-compatibilità) */
  white:       '#ffffff',
  grayLight:   '#e2e8f0',
  grayBg:      '#f8fafc',
  purple:      '#7c3aed',
};

/* Theme alias: usato in diverse pagine legacy */
export const THEME = {
  primary:       COLORS.primary,
  primaryLight:  COLORS.primaryLight,
  primaryDark:   COLORS.primaryDark,
  success:       COLORS.success,
  successLight:  COLORS.successLight,
  warning:       COLORS.warning,
  warningLight:  COLORS.warningLight,
  error:         COLORS.danger,
  errorLight:    COLORS.dangerLight,
  info:          COLORS.info,
  infoLight:     COLORS.infoLight,
  gray:          COLORS.gray,
};

/* ---------- SPAZIATURE ---------- */
export const SPACING = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };

/* ---------- OMBRE ---------- */
export const SHADOWS = {
  sm: '0 1px 2px rgba(15,39,68,0.06)',
  md: '0 2px 8px rgba(15,39,68,0.08)',
  lg: '0 6px 16px rgba(15,39,68,0.10)',
  xl: '0 12px 32px rgba(15,39,68,0.14)',
};

/* ---------- RADIUS ---------- */
export const BORDER_RADIUS = { sm: 6, md: 8, lg: 10, xl: 14, full: 9999 };

/* ---------- TIPOGRAFIA ---------- */
export const FONT = {
  family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  mono:   "'SF Mono', Menlo, Monaco, Consolas, 'Courier New', monospace",
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
    transition: 'background 140ms ease, border-color 140ms ease, color 140ms ease, box-shadow 140ms ease',
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
    return { ...base, background: 'transparent', color: COLORS.textMuted, borderColor: 'transparent' };
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
    return { ...base, background: 'transparent', color: COLORS.primary, borderColor: COLORS.primary };
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
  if (type === 'success') return { ...base, background: COLORS.successLight, color: COLORS.success };
  if (type === 'warning') return { ...base, background: COLORS.warningLight, color: COLORS.warning };
  if (type === 'danger')  return { ...base, background: COLORS.dangerLight,  color: COLORS.danger  };
  if (type === 'info')    return { ...base, background: COLORS.infoLight,    color: COLORS.info    };
  if (type === 'neutral') return { ...base, background: COLORS.gray[100],    color: COLORS.gray[700] };
  if (type === 'primary') return { ...base, background: COLORS.primarySoft,  color: COLORS.primary };
  if (type === 'accent')  return { ...base, background: COLORS.accentSoft,   color: COLORS.accent  };
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
  } catch { return dateStr; }
}

export function parseDateIT(dateStr) {
  if (!dateStr) return null;
  try {
    const parts = dateStr.split('/');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return dateStr;
  } catch { return dateStr; }
}

export function formatEuro(amount) {
  if (amount === null || amount === undefined) return '€ 0,00';
  return `€ ${new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: true,
  }).format(parseFloat(amount))}`;
}

export function formatDateTimeIT(dateStr) {
  if (!dateStr) return '-';
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('it-IT', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return dateStr; }
}

export function formatDateShort(dateStr) {
  if (!dateStr) return '-';
  try {
    const datePart = dateStr.includes('T') ? dateStr.split('T')[0] : dateStr;
    const parts = datePart.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}`;
    return dateStr;
  } catch { return dateStr; }
}

export function formatEuroShort(amount) {
  if (amount === null || amount === undefined) return '0,00';
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: true,
  }).format(parseFloat(amount));
}

export function formatEuroStr(amount) {
  if (amount === null || amount === undefined) return '€ 0,00';
  return formatEuro(amount);
}

/* ================================================================
   COSTANTI MESI
   ================================================================ */
export const MESI_SHORT = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];
export const MESI_FULL  = ['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre'];
export const MESI = [
  { key: '01', value: 1,  label: 'Gennaio',   short: 'Gen' },
  { key: '02', value: 2,  label: 'Febbraio',  short: 'Feb' },
  { key: '03', value: 3,  label: 'Marzo',     short: 'Mar' },
  { key: '04', value: 4,  label: 'Aprile',    short: 'Apr' },
  { key: '05', value: 5,  label: 'Maggio',    short: 'Mag' },
  { key: '06', value: 6,  label: 'Giugno',    short: 'Giu' },
  { key: '07', value: 7,  label: 'Luglio',    short: 'Lug' },
  { key: '08', value: 8,  label: 'Agosto',    short: 'Ago' },
  { key: '09', value: 9,  label: 'Settembre', short: 'Set' },
  { key: '10', value: 10, label: 'Ottobre',   short: 'Ott' },
  { key: '11', value: 11, label: 'Novembre',  short: 'Nov' },
  { key: '12', value: 12, label: 'Dicembre',  short: 'Dic' },
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
  col2:  (m) => ({ display:'grid', gridTemplateColumns: m ? '1fr'     : '1fr 1fr',          gap: 16 }),
  col3:  (m) => ({ display:'grid', gridTemplateColumns: m ? '1fr'     : 'repeat(3,1fr)',    gap: 16 }),
  col4:  (m) => ({ display:'grid', gridTemplateColumns: m ? '1fr 1fr' : 'repeat(4,1fr)',    gap: 12 }),
  col24: (m) => ({ display:'grid', gridTemplateColumns: m ? '1fr'     : '2fr 4fr',          gap: 16 }),
  kpi:   (m) => ({ display:'grid', gridTemplateColumns: m ? '1fr 1fr' : 'repeat(4,1fr)',    gap: 12 }),
  form:  (m) => ({ display:'grid', gridTemplateColumns: m ? '1fr'     : '1fr 1fr',          gap: 16 }),
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
