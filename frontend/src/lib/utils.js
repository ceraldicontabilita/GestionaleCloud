/* Ceraldi ERP v2 — Design System MaterialM
 * ==========================================
 * REGOLA ASSOLUTA: ogni componente importa da questo file.
 * Nessun colore hardcoded nei componenti. Nessun Tailwind. Nessun Shadcn.
 * Font: Plus Jakarta Sans (caricato in index.html)
 */

export const colors = {
  /* Brand primario — viola MaterialM */
  primary:      '#5D29C7',
  primaryHover: '#4D1FB0',
  primaryLight: '#7C4DDD',
  primaryDark:  '#3D1A8F',
  primaryBg:    '#EDE7FF',
  primaryText:  '#3D1A8F',

  /* Accent blu */
  accent:       '#2196F3',
  accentBg:     '#E3F2FD',
  accentText:   '#0D47A1',

  /* Surface / Layout */
  bg:           '#F0F4FA',
  card:         '#FFFFFF',
  cardHover:    '#FAFBFF',
  sidebar:      '#1E1B4B',
  sidebarHover: '#2D2870',
  sidebarActive:'rgba(255,255,255,0.12)',
  sidebarText:  'rgba(255,255,255,0.72)',
  sidebarTextActive: '#FFFFFF',
  topbar:       '#FFFFFF',

  /* Testo */
  text:         '#1A1A2E',
  textMuted:    '#6B7280',
  textLight:    '#9CA3AF',
  textInverse:  '#FFFFFF',

  /* Bordi */
  border:       '#E8ECF0',
  borderLight:  '#F1F4F8',
  borderFocus:  '#5D29C7',

  /* Semantici */
  success:      '#00B884',
  successBg:    '#E6F9F4',
  successText:  '#006B4F',

  warning:      '#FF9800',
  warningBg:    '#FFF3E0',
  warningText:  '#E65100',

  danger:       '#F44336',
  dangerBg:     '#FEECEB',
  dangerText:   '#B71C1C',

  info:         '#2196F3',
  infoBg:       '#E3F2FD',
  infoText:     '#0D47A1',

  /* Palette grafici */
  chart: ['#5D29C7','#2196F3','#00B884','#FF9800','#F44336','#9C27B0','#FF5722','#00BCD4'],
}

export const font = "'Plus Jakarta Sans', 'DM Sans', sans-serif"

export const shadow = {
  xs:   '0 1px 3px rgba(0,0,0,0.06)',
  sm:   '0 2px 6px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04)',
  md:   '0 4px 16px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04)',
  lg:   '0 8px 28px rgba(0,0,0,0.10), 0 4px 8px rgba(0,0,0,0.04)',
  card: '0 2px 10px rgba(93,41,199,0.07), 0 1px 3px rgba(0,0,0,0.04)',
  btn:  '0 4px 14px rgba(93,41,199,0.35)',
}

export const s = {
  /* ── LAYOUT ────────────────────────────────────────────── */
  page: {
    fontFamily: font,
    background: colors.bg,
    minHeight: '100vh',
    color: colors.text,
  },
  container: {
    maxWidth: 1280,
    margin: '0 auto',
    padding: '28px 24px',
  },

  /* ── CARD ───────────────────────────────────────────────── */
  card: {
    background: colors.card,
    borderRadius: 16,
    boxShadow: shadow.card,
    border: `1px solid ${colors.border}`,
    padding: 24,
    marginBottom: 20,
  },
  cardNoPad: {
    background: colors.card,
    borderRadius: 16,
    boxShadow: shadow.card,
    border: `1px solid ${colors.border}`,
    marginBottom: 20,
    overflow: 'hidden',
  },
  metricCard: {
    background: colors.card,
    borderRadius: 16,
    boxShadow: shadow.card,
    border: `1px solid ${colors.border}`,
    padding: '20px 22px',
  },

  /* ── TIPOGRAFIA ─────────────────────────────────────────── */
  h1: {
    fontSize: 24,
    fontWeight: 700,
    margin: 0,
    color: colors.text,
    letterSpacing: '-0.4px',
    lineHeight: 1.3,
  },
  h2: {
    fontSize: 16,
    fontWeight: 700,
    margin: '0 0 16px 0',
    color: colors.text,
    letterSpacing: '-0.2px',
  },
  h3: {
    fontSize: 13,
    fontWeight: 700,
    margin: '0 0 4px 0',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.7px',
  },
  label: {
    fontSize: 11,
    fontWeight: 700,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.7px',
    marginBottom: 6,
  },
  value: {
    fontSize: 15,
    fontWeight: 500,
    color: colors.text,
  },
  caption: {
    fontSize: 12,
    color: colors.textLight,
  },

  /* ── BADGE ──────────────────────────────────────────────── */
  badge: (color, bg) => ({
    display: 'inline-flex',
    alignItems: 'center',
    fontSize: 11,
    fontWeight: 700,
    padding: '3px 10px',
    borderRadius: 20,
    color,
    background: bg,
    letterSpacing: '0.2px',
    whiteSpace: 'nowrap',
  }),

  /* ── PULSANTI ───────────────────────────────────────────── */
  btn: {
    fontFamily: font,
    fontSize: 13,
    fontWeight: 600,
    padding: '9px 18px',
    borderRadius: 10,
    border: 'none',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    transition: 'all .15s ease',
    letterSpacing: '0.1px',
    textDecoration: 'none',
  },
  btnPrimary: {
    background: `linear-gradient(135deg, ${colors.primary} 0%, ${colors.primaryLight} 100%)`,
    color: '#fff',
    boxShadow: shadow.btn,
  },
  btnOutline: {
    background: 'transparent',
    color: colors.primary,
    border: `1.5px solid ${colors.primary}`,
  },
  btnGhost: {
    background: colors.primaryBg,
    color: colors.primary,
    border: 'none',
  },
  btnDanger: {
    background: colors.danger,
    color: '#fff',
    boxShadow: '0 4px 12px rgba(244,67,54,0.30)',
  },
  btnSuccess: {
    background: colors.success,
    color: '#fff',
  },
  btnNeutral: {
    background: colors.bg,
    color: colors.textMuted,
    border: `1px solid ${colors.border}`,
  },
  btnSmall: {
    fontSize: 12,
    padding: '6px 12px',
    borderRadius: 8,
    gap: 5,
  },
  btnXSmall: {
    fontSize: 11,
    padding: '4px 10px',
    borderRadius: 6,
    gap: 4,
  },

  /* ── TABELLA ────────────────────────────────────────────── */
  table: {
    width: '100%',
    borderCollapse: 'separate',
    borderSpacing: 0,
    fontSize: 13,
  },
  th: {
    textAlign: 'left',
    padding: '11px 16px',
    fontSize: 11,
    fontWeight: 700,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.7px',
    borderBottom: `1.5px solid ${colors.border}`,
    background: '#F8F9FC',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '13px 16px',
    borderBottom: `1px solid ${colors.borderLight}`,
    verticalAlign: 'middle',
    fontSize: 13,
    color: colors.text,
  },
  trHover: {
    cursor: 'pointer',
    transition: 'background .1s',
  },

  /* ── INPUT / SELECT ─────────────────────────────────────── */
  input: {
    fontFamily: font,
    fontSize: 14,
    padding: '10px 14px',
    border: `1.5px solid ${colors.border}`,
    borderRadius: 10,
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
    transition: 'border-color .15s',
    background: '#fff',
    color: colors.text,
  },
  select: {
    fontFamily: font,
    fontSize: 13,
    padding: '9px 14px',
    border: `1.5px solid ${colors.border}`,
    borderRadius: 10,
    outline: 'none',
    background: '#fff',
    cursor: 'pointer',
    color: colors.text,
  },

  /* ── LAYOUT HELPERS ─────────────────────────────────────── */
  flex:         { display: 'flex', alignItems: 'center' },
  flexBetween:  { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  flexEnd:      { display: 'flex', alignItems: 'center', justifyContent: 'flex-end' },
  flexWrap:     { display: 'flex', alignItems: 'center', flexWrap: 'wrap' },
  flexCol:      { display: 'flex', flexDirection: 'column' },
  gap4:         { gap: 4 },
  gap6:         { gap: 6 },
  gap8:         { gap: 8 },
  gap12:        { gap: 12 },
  gap16:        { gap: 16 },
  gap20:        { gap: 20 },
  mt8:          { marginTop: 8 },
  mt12:         { marginTop: 12 },
  mt16:         { marginTop: 16 },
  mt20:         { marginTop: 20 },
  mb8:          { marginBottom: 8 },
  mb12:         { marginBottom: 12 },
  mb16:         { marginBottom: 16 },
  mb20:         { marginBottom: 20 },
}

/* ── UTILITY FUNCTIONS ────────────────────────────────────── */

export function statoBadge(stato) {
  const map = {
    attivo:                  [colors.successText,  colors.successBg],
    cessato:                 [colors.dangerText,   colors.dangerBg],
    ricevuto:                [colors.warningText,  colors.warningBg],
    cessato_rapporto:        [colors.dangerText,   colors.dangerBg],
    dichiarazione_generata:  [colors.infoText,     colors.infoBg],
    dichiarazione_inviata:   [colors.primaryText,  colors.primaryBg],
    in_trattenuta:           [colors.warningText,  colors.warningBg],
    estinto:                 [colors.successText,  colors.successBg],
    da_confermare:           [colors.warningText,  colors.warningBg],
    da_pagare:               [colors.dangerText,   colors.dangerBg],
    pagato:                  [colors.successText,  colors.successBg],
    importato:               [colors.infoText,     colors.infoBg],
  }
  const [color, bg] = map[stato] || [colors.textMuted, colors.borderLight]
  return s.badge(color, bg)
}

export function formatEuro(n) {
  if (n == null || n === '') return '—'
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(n)
}

export function formatOre(decimali) {
  if (!decimali && decimali !== 0) return '—'
  const h = Math.floor(decimali)
  const m = Math.round((decimali - h) * 60)
  if (m === 0) return `${h}h`
  return `${h}h ${String(m).padStart(2,'0')}m`
}

export function statoLabel(stato) {
  const map = {
    ricevuto:               'Ricevuto',
    cessato_rapporto:       'Cessato rapporto',
    dichiarazione_generata: 'Dich. generata',
    dichiarazione_inviata:  'Dich. inviata',
    in_trattenuta:          'In trattenuta',
    estinto:                'Estinto',
    da_confermare:          'Da confermare',
    da_pagare:              'Da pagare',
    pagato:                 'Pagato',
    importato:              'Importato',
  }
  return map[stato] || stato
}

/* Chip colore per codici giustificativo presenze */
export function giustBadge(codice) {
  const map = {
    AI: [colors.dangerText,   colors.dangerBg,   'Ass. ingiust.'],
    FE: [colors.infoText,     colors.infoBg,     'Ferie'],
    MA: [colors.warningText,  colors.warningBg,  'Malattia'],
    PE: [colors.primaryText,  colors.primaryBg,  'Permesso'],
    MT: [colors.successText,  colors.successBg,  'Maternità'],
    RO: [colors.accentText,   colors.accentBg,   'ROL'],
    ST: [colors.primaryText,  colors.primaryBg,  'Straordinario'],
    FS: [colors.textMuted,    colors.borderLight,'Fest. soppressa'],
    AP: [colors.textMuted,    colors.borderLight,'Aspettativa'],
  }
  const [color, bg, label] = map[codice] || [colors.textMuted, colors.borderLight, codice]
  return { color, bg, label }
}
