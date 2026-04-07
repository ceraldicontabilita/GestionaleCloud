import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Users, Gavel, Home } from 'lucide-react'
import { colors, font } from '../lib/utils'

const navStyle = {
  background: colors.primary,
  padding: '0 20px',
  display: 'flex',
  alignItems: 'center',
  height: 54,
  fontFamily: font,
  gap: 0,
}

const logoStyle = {
  color: '#fff',
  fontSize: 16,
  fontWeight: 700,
  marginRight: 32,
  letterSpacing: '0.5px',
  textDecoration: 'none',
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const linkBase = {
  color: 'rgba(255,255,255,0.7)',
  textDecoration: 'none',
  fontSize: 14,
  fontWeight: 500,
  padding: '16px 16px',
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  borderBottom: '2px solid transparent',
  transition: 'color .15s, border-color .15s',
}

const linkActive = {
  ...linkBase,
  color: '#fff',
  borderBottom: `2px solid ${colors.accent}`,
}

const links = [
  { to: '/dipendenti', label: 'Dipendenti', icon: Users },
  { to: '/pignoramenti', label: 'Pignoramenti', icon: Gavel },
]

export default function TopNav() {
  const loc = useLocation()
  return (
    <nav style={navStyle}>
      <Link to="/" style={logoStyle}>
        <Home size={18} /> CERALDI ERP
      </Link>
      {links.map(l => (
        <Link
          key={l.to}
          to={l.to}
          style={loc.pathname.startsWith(l.to) ? linkActive : linkBase}
        >
          <l.icon size={16} /> {l.label}
        </Link>
      ))}
    </nav>
  )
}
