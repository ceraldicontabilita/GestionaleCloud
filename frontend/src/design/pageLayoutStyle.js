/**
 * PAGE LAYOUT STYLE — Wrapper di compatibilità
 * 
 * ⚠️  Per nuove pagine, importa direttamente da './tokens.js'
 * 
 * Questo file re-esporta tutto da tokens.js per retrocompatibilità.
 * I colori sono ora allineati: primary = #1535a8 (non più #1e3a5f o #2563eb)
 */

export {
  COLOR,
  SPACE,
  RADIUS,
  SHADOW,
  FONT,
  STYLES,
  PAGE_WRAPPER,
  PAGE_CONTAINER,
  PAGE_HEADER,
  PAGE_CONTENT,
  PAGE_TITLE,
  PAGE_SUBTITLE,
  HEADER_ACTIONS,
  TABS_CONTAINER,
  TAB_STYLE,
} from './tokens.js';

// ─── EXTRA STYLES specifici per PageLayout ───────────────
// (usati solo da PageLayout.jsx, non globali)
import { COLOR, SPACE, RADIUS, SHADOW, FONT } from './tokens.js';

export const SECTION_TITLE = {
  fontSize: FONT.lg,
  fontWeight: 700,
  color: COLOR.ink,
  marginBottom: SPACE.md,
};

export const SECTION_SUBTITLE = {
  fontSize: FONT.base,
  color: COLOR.ink3,
};

export const CARD_GRID = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: SPACE.lg,
};

export const KPI_GRID = {
  display: 'grid',
  gridTemplateColumns: 'repeat(4, 1fr)',
  gap: SPACE.md,
  marginBottom: SPACE.xl,
};

// Bottone primario stile nav (header bianco su sfondo blu)
export const BTN_HEADER_PRIMARY = {
  background: COLOR.surface,
  color: COLOR.brand,
  border: 'none',
  borderRadius: RADIUS.md,
  padding: '7px 14px',
  fontSize: FONT.md,
  fontWeight: 700,
  cursor: 'pointer',
  fontFamily: 'inherit',
  transition: 'all .14s',
};

export const BTN_HEADER_OUTLINE = {
  background: 'rgba(255,255,255,.15)',
  color: COLOR.surface,
  border: '1px solid rgba(255,255,255,.3)',
  borderRadius: RADIUS.md,
  padding: '7px 14px',
  fontSize: FONT.md,
  fontWeight: 700,
  cursor: 'pointer',
  fontFamily: 'inherit',
  transition: 'all .14s',
};
