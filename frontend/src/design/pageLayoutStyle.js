/**
 * Page Layout Style System
 *
 * Sistema di layout unificato per tutte le pagine dell'applicazione.
 * Garantisce consistenza visiva e accessibilità.
 *
 * USO:
 * import { PAGE_WRAPPER, PAGE_CONTAINER, PAGE_HEADER, PAGE_CONTENT } from '@/design/pageLayoutStyle';
 */

// Colori del tema - ALLINEATI con lib/utils.js
const COLORS = {
  primary: '#1e3a5f',
  primaryLight: '#2d5a87',
  primaryDark: '#152a47',
  background: '#f9fafb',
  surface: '#ffffff',
  text: '#1f2937',
  textSecondary: '#6b7280',
  border: '#e5e7eb',
  success: '#16a34a',
  successLight: '#dcfce7',
  warning: '#f59e0b',
  warningLight: '#fef3c7',
  error: '#dc2626',
  errorLight: '#fee2e2',
  info: '#2563eb',
  infoLight: '#dbeafe',
};

// Wrapper principale della pagina - sfondo e padding esterno
export const PAGE_WRAPPER = {
  minHeight: '100vh',
  background: `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.primaryLight} 100%)`,
  padding: '20px',
  boxSizing: 'border-box',
};

// Container della pagina - card bianca con ombra
export const PAGE_CONTAINER = {
  background: COLORS.surface,
  borderRadius: '16px',
  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)',
  minHeight: 'calc(100vh - 40px)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
};

// Header della pagina - titolo e azioni
export const PAGE_HEADER = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '20px 24px',
  borderBottom: `1px solid ${COLORS.border}`,
  background: COLORS.background,
  flexWrap: 'wrap',
  gap: '16px',
};

// Contenuto principale della pagina
export const PAGE_CONTENT = {
  flex: 1,
  padding: '24px',
  overflow: 'auto',
};

// Stili per il titolo della pagina
export const PAGE_TITLE = {
  margin: 0,
  fontSize: '22px',
  fontWeight: 700,
  color: COLORS.text,
};

// Stili per il sottotitolo
export const PAGE_SUBTITLE = {
  margin: '4px 0 0 0',
  fontSize: '13px',
  color: COLORS.textSecondary,
  opacity: 0.9,
};

// Container per le azioni dell'header
export const HEADER_ACTIONS = {
  display: 'flex',
  gap: '12px',
  alignItems: 'center',
  flexWrap: 'wrap',
};

// Stile per card/sezioni interne
export const CARD_STYLE = {
  background: COLORS.surface,
  borderRadius: '12px',
  border: `1px solid ${COLORS.border}`,
  padding: '20px',
  marginBottom: '16px',
};

// Stile per tabelle
export const TABLE_CONTAINER = {
  overflowX: 'auto',
  borderRadius: '8px',
  border: `1px solid ${COLORS.border}`,
};

export const TABLE_STYLE = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '14px',
};

export const TH_STYLE = {
  padding: '12px 16px',
  textAlign: 'left',
  fontWeight: 600,
  color: COLORS.text,
  background: COLORS.background,
  borderBottom: `2px solid ${COLORS.border}`,
  whiteSpace: 'nowrap',
};

export const TD_STYLE = {
  padding: '12px 16px',
  borderBottom: `1px solid ${COLORS.border}`,
  verticalAlign: 'middle',
};

// Stile per tabs
export const TABS_CONTAINER = {
  display: 'flex',
  gap: '4px',
  borderBottom: `1px solid ${COLORS.border}`,
  marginBottom: '20px',
  paddingBottom: '0',
  overflowX: 'auto',
};

export const TAB_STYLE = isActive => ({
  padding: '12px 20px',
  background: isActive ? COLORS.primary : 'transparent',
  color: isActive ? '#fff' : COLORS.textSecondary,
  border: 'none',
  borderRadius: '8px 8px 0 0',
  cursor: 'pointer',
  fontWeight: isActive ? 600 : 500,
  fontSize: '14px',
  transition: 'all 0.2s ease',
  whiteSpace: 'nowrap',
});

// Stile per pulsanti
export const BUTTON_PRIMARY = {
  padding: '10px 20px',
  background: COLORS.primary,
  color: '#fff',
  border: 'none',
  borderRadius: '8px',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: '14px',
  transition: 'all 0.2s ease',
};

export const BUTTON_SECONDARY = {
  padding: '10px 20px',
  background: 'transparent',
  color: COLORS.primary,
  border: `1px solid ${COLORS.primary}`,
  borderRadius: '8px',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: '14px',
  transition: 'all 0.2s ease',
};

export const BUTTON_DANGER = {
  padding: '10px 20px',
  background: COLORS.error,
  color: '#fff',
  border: 'none',
  borderRadius: '8px',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: '14px',
  transition: 'all 0.2s ease',
};

// Stile per badge/status
export const BADGE_STYLE = (type = 'default') => {
  const colors = {
    default: { bg: '#e2e8f0', color: '#4a5568' },
    success: { bg: '#c6f6d5', color: '#276749' },
    warning: { bg: '#fefcbf', color: '#975a16' },
    error: { bg: '#fed7d7', color: '#c53030' },
    info: { bg: '#bee3f8', color: '#2b6cb0' },
  };
  const c = colors[type] || colors.default;
  return {
    display: 'inline-block',
    padding: '4px 10px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: 600,
    background: c.bg,
    color: c.color,
  };
};

// Stile per input
export const INPUT_STYLE = {
  padding: '10px 14px',
  borderRadius: '8px',
  border: `1px solid ${COLORS.border}`,
  fontSize: '14px',
  width: '100%',
  boxSizing: 'border-box',
  transition: 'border-color 0.2s ease',
};

// Stile per select
export const SELECT_STYLE = {
  padding: '10px 14px',
  borderRadius: '8px',
  border: `1px solid ${COLORS.border}`,
  fontSize: '14px',
  cursor: 'pointer',
  background: '#fff',
};

// Stile per messaggi di stato (empty state, loading, error)
export const EMPTY_STATE = {
  textAlign: 'center',
  padding: '60px 20px',
  color: COLORS.textSecondary,
};

export const LOADING_STATE = {
  textAlign: 'center',
  padding: '60px 20px',
  color: COLORS.textSecondary,
};

export const ERROR_STATE = {
  textAlign: 'center',
  padding: '40px 20px',
  background: '#fff5f5',
  borderRadius: '12px',
  border: `1px solid ${COLORS.error}`,
  color: COLORS.error,
};

// Grid layout helpers
export const GRID_2_COLS = {
  display: 'grid',
  gridTemplateColumns: 'repeat(2, 1fr)',
  gap: '20px',
};

export const GRID_3_COLS = {
  display: 'grid',
  gridTemplateColumns: 'repeat(3, 1fr)',
  gap: '20px',
};

export const GRID_4_COLS = {
  display: 'grid',
  gridTemplateColumns: 'repeat(4, 1fr)',
  gap: '20px',
};

// Export tutto come oggetto per import facile
export default {
  PAGE_WRAPPER,
  PAGE_CONTAINER,
  PAGE_HEADER,
  PAGE_CONTENT,
  PAGE_TITLE,
  PAGE_SUBTITLE,
  HEADER_ACTIONS,
  CARD_STYLE,
  TABLE_CONTAINER,
  TABLE_STYLE,
  TH_STYLE,
  TD_STYLE,
  TABS_CONTAINER,
  TAB_STYLE,
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  BUTTON_DANGER,
  BADGE_STYLE,
  INPUT_STYLE,
  SELECT_STYLE,
  EMPTY_STATE,
  LOADING_STATE,
  ERROR_STATE,
  GRID_2_COLS,
  GRID_3_COLS,
  GRID_4_COLS,
  COLORS,
};
