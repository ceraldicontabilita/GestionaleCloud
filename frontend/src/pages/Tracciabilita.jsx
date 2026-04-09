import React, { useState } from 'react'
import { LayoutDashboard, Thermometer, Sparkles, Bug, Gift, ShoppingBag } from 'lucide-react'
import { s, colors, font } from '../lib/utils'

import DashboardHACCP from './DashboardHACCP'
import TemperatureHACCP from './TemperatureHACCP'
import SanificazioneHACCP from './SanificazioneHACCP'
import DisinfestazioneHACCP from './DisinfestazioneHACCP'
import ScontiMerce from './ScontiMerce'
import OrdiniFornitore from './OrdiniFornitore'

const TABS = [
  { id: 'dashboard',       label: 'Dashboard',       icon: LayoutDashboard, component: DashboardHACCP },
  { id: 'temperature',     label: 'Temperature',     icon: Thermometer,     component: TemperatureHACCP },
  { id: 'sanificazione',   label: 'Sanificazione',   icon: Sparkles,        component: SanificazioneHACCP },
  { id: 'disinfestazione', label: 'Disinfestazione', icon: Bug,             component: DisinfestazioneHACCP },
  { id: 'sconti',          label: 'Sconti Merce',    icon: Gift,            component: ScontiMerce },
  { id: 'ordini',          label: 'Ordini Fornitori', icon: ShoppingBag,    component: OrdiniFornitore },
]

const tabBar = {
  display: 'flex', gap: 4, marginBottom: 20, overflowX: 'auto',
  borderBottom: `2px solid ${colors.border}`, paddingBottom: 0,
}
const tabBase = {
  padding: '10px 18px', fontSize: 13, fontWeight: 600, fontFamily: font,
  border: 'none', borderBottom: '3px solid transparent',
  background: 'transparent', color: colors.textMuted, cursor: 'pointer',
  display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
  transition: 'color .15s, border-color .15s',
  borderRadius: '6px 6px 0 0',
}
const tabActive = {
  ...tabBase, color: colors.primary, borderBottomColor: colors.primary,
  background: `${colors.primary}10`,
}

export default function Tracciabilita() {
  const [tab, setTab] = useState('dashboard')
  const current = TABS.find(t => t.id === tab) || TABS[0]
  const Comp = current.component

  return (
    <div>
      <h1 style={{ ...s.h1, marginBottom: 16 }}>Tracciabilità & HACCP</h1>
      <div style={tabBar}>
        {TABS.map(t => {
          const Icon = t.icon
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={tab === t.id ? tabActive : tabBase}>
              <Icon size={15} /> {t.label}
            </button>
          )
        })}
      </div>
      <Comp />
    </div>
  )
}
