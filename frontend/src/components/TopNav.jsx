import React from 'react'
import { Shield, Link, useLocation } from 'react-router-dom'
import { Shield, Users, Gavel, Home, FileText, Receipt, Landmark, FileCheck, CreditCard, Car, Banknote, Inbox, Mail } from 'lucide-react'
import { Shield, colors, font } from '../lib/utils'

const navStyle = {
  background: colors.primary, padding: '0 20px', display: 'flex',
  alignItems: 'center', height: 54, fontFamily: font, gap: 0, overflowX: 'auto', whiteSpace: 'nowrap',
}
const logoStyle = {
  color: '#fff', fontSize: 16, fontWeight: 700, marginRight: 24, letterSpacing: '0.5px',
  textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 8,
}
const divider = { width: 1, height: 24, background: 'rgba(255,255,255,0.2)', margin: '0 6px', flexShrink: 0 }
const linkBase = {
  color: 'rgba(255,255,255,0.7)', textDecoration: 'none', fontSize: 13, fontWeight: 500,
  padding: '16px 11px', display: 'flex', alignItems: 'center', gap: 5,
  borderBottom: '2px solid transparent', transition: 'color .15s, border-color .15s', flexShrink: 0,
}
const linkActive  = { ...linkBase, color: '#fff', borderBottom: `2px solid ${colors.accent}` }
const linkImporta = { ...linkBase, color: colors.accent, fontWeight: 700, background: 'rgba(232,168,56,0.12)', borderRadius: '6px 6px 0 0' }
const linkImportaActive = { ...linkImporta, borderBottom: `2px solid ${colors.accent}` }
const linkSmall   = { ...linkBase, fontSize: 12, color: 'rgba(255,255,255,0.5)' }
const linkSmallActive = { ...linkSmall, color: 'rgba(255,255,255,0.85)', borderBottom: `2px solid rgba(255,255,255,0.3)` }

const links = [
  { to: '/dipendenti', label: 'Dipendenti',    icon: Users },
  { to: '/pignoramenti', label: 'Pignoramenti', icon: Gavel },
  { to: '/fatture', label: 'Fatture',           icon: FileText },
  { to: '/cedolini', label: 'Cedolini',         icon: Receipt },
  { to: '/estratto-conto', label: 'EC',         icon: Landmark },
  { to: '/distinte', label: 'Distinte',         icon: Banknote },
  { to: '/alert-fiscali', label: '⚠️ Alert Fiscali', icon: Shield },
  { to: '/f24', label: 'F24',                   icon: FileCheck },
  { to: '/f24-privati', label: 'F24 Privati',       icon: Shield },
  { to: '/corrispettivi', label: 'Corrispettivi', icon: CreditCard },
  { to: '/verbali', label: 'Verbali',           icon: Car },
]

export default function TopNav() {
  const loc = useLocation()
  const isImporta = loc.pathname.startsWith('/importa')
  const isMittenti = loc.pathname.startsWith('/mittenti')
  return (
    <nav style={navStyle}>
      <Link to="/" style={logoStyle}><Home size={18} /> CERALDI ERP</Link>
      <Link to="/importa" style={isImporta ? linkImportaActive : linkImporta}>
        <Inbox size={15} /> Importa
      </Link>
      <div style={divider} />
      {links.map(l => (
        <Link key={l.to} to={l.to} style={loc.pathname.startsWith(l.to) ? linkActive : linkBase}>
          <l.icon size={15} /> {l.label}
        </Link>
      ))}
      <div style={divider} />
      <Link to="/mittenti" style={isMittenti ? linkSmallActive : linkSmall}>
        <Mail size={13} /> Mittenti
      </Link>
    </nav>
  )
}
