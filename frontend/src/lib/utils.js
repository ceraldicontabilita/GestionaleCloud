/* Ceraldi ERP v2 — Stili condivisi (CSS inline) */

export const colors = {
  primary: '#1a3a5c',
  primaryLight: '#2a5a8c',
  accent: '#e8a838',
  bg: '#f4f5f7',
  card: '#ffffff',
  text: '#1a1a2e',
  textMuted: '#6b7280',
  border: '#e2e5ea',
  success: '#16a34a',
  successBg: '#dcfce7',
  warning: '#d97706',
  warningBg: '#fef3c7',
  danger: '#dc2626',
  dangerBg: '#fee2e2',
  infoBg: '#dbeafe',
}

export const font = "'DM Sans', sans-serif"

export const s = {
  page: {
    fontFamily: font,
    background: colors.bg,
    minHeight: '100vh',
    color: colors.text,
  },
  container: {
    maxWidth: 1200,
    margin: '0 auto',
    padding: '24px 20px',
  },
  card: {
    background: colors.card,
    borderRadius: 10,
    border: `1px solid ${colors.border}`,
    padding: 24,
    marginBottom: 16,
  },
  h1: {
    fontSize: 22,
    fontWeight: 700,
    margin: 0,
    color: colors.primary,
  },
  h2: {
    fontSize: 17,
    fontWeight: 600,
    margin: '0 0 12px 0',
    color: colors.text,
  },
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: 4,
  },
  value: {
    fontSize: 15,
    fontWeight: 500,
    color: colors.text,
  },
  badge: (color, bg) => ({
    display: 'inline-block',
    fontSize: 12,
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: 20,
    color,
    background: bg,
  }),
  btn: {
    fontFamily: font,
    fontSize: 13,
    fontWeight: 600,
    padding: '8px 16px',
    borderRadius: 6,
    border: 'none',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    transition: 'opacity .15s',
  },
  btnPrimary: {
    background: colors.primary,
    color: '#fff',
  },
  btnOutline: {
    background: 'transparent',
    color: colors.primary,
    border: `1px solid ${colors.border}`,
  },
  btnDanger: {
    background: colors.danger,
    color: '#fff',
  },
  btnSmall: {
    fontSize: 12,
    padding: '5px 10px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 14,
  },
  th: {
    textAlign: 'left',
    padding: '10px 12px',
    fontSize: 12,
    fontWeight: 600,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
    borderBottom: `2px solid ${colors.border}`,
  },
  td: {
    padding: '12px',
    borderBottom: `1px solid ${colors.border}`,
    verticalAlign: 'middle',
  },
  trHover: {
    cursor: 'pointer',
  },
  input: {
    fontFamily: font,
    fontSize: 14,
    padding: '8px 12px',
    border: `1px solid ${colors.border}`,
    borderRadius: 6,
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
  },
  select: {
    fontFamily: font,
    fontSize: 14,
    padding: '8px 12px',
    border: `1px solid ${colors.border}`,
    borderRadius: 6,
    outline: 'none',
    background: '#fff',
    cursor: 'pointer',
  },
  flex: { display: 'flex', alignItems: 'center' },
  flexBetween: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  gap8: { gap: 8 },
  gap16: { gap: 16 },
  mt16: { marginTop: 16 },
  mb8: { marginBottom: 8 },
}

export function statoBadge(stato) {
  switch (stato) {
    case 'attivo': return s.badge(colors.success, colors.successBg)
    case 'cessato': return s.badge(colors.danger, colors.dangerBg)
    case 'ricevuto': return s.badge(colors.warning, colors.warningBg)
    case 'cessato_rapporto': return s.badge(colors.danger, colors.dangerBg)
    case 'dichiarazione_generata': return s.badge('#2563eb', colors.infoBg)
    case 'dichiarazione_inviata': return s.badge('#2563eb', colors.infoBg)
    case 'in_trattenuta': return s.badge(colors.warning, colors.warningBg)
    case 'estinto': return s.badge(colors.success, colors.successBg)
    default: return s.badge(colors.textMuted, '#f3f4f6')
  }
}

export function formatEuro(n) {
  if (n == null) return '—'
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(n)
}

export function statoLabel(stato) {
  const map = {
    ricevuto: 'Ricevuto',
    cessato_rapporto: 'Cessato rapporto',
    dichiarazione_generata: 'Dichiaraz. generata',
    dichiarazione_inviata: 'Dichiaraz. inviata',
    in_trattenuta: 'In trattenuta',
    estinto: 'Estinto',
  }
  return map[stato] || stato
}
