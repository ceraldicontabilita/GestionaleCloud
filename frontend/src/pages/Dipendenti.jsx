import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Users, Search, Filter } from 'lucide-react'
import { api } from '../lib/api'
import { s, colors, statoBadge, formatEuro } from '../lib/utils'

export default function Dipendenti() {
  const [dips, setDips] = useState([])
  const [loading, setLoading] = useState(true)
  const [filtro, setFiltro] = useState('')
  const [search, setSearch] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    setLoading(true)
    api.getDipendenti(filtro || undefined)
      .then(setDips)
      .catch(e => console.error(e))
      .finally(() => setLoading(false))
  }, [filtro])

  const filtered = dips.filter(d => {
    if (!search) return true
    const q = search.toLowerCase()
    return `${d.cognome} ${d.nome}`.toLowerCase().includes(q) ||
      (d.codice_fiscale || '').toLowerCase().includes(q)
  })

  const totPig = dips.reduce((a, d) => a + (d.pignoramenti?.length || 0), 0)

  return (
    <div>
      <div style={{ ...s.flexBetween, marginBottom: 20 }}>
        <div style={{ ...s.flex, gap: 12 }}>
          <Users size={24} color={colors.primary} />
          <h1 style={s.h1}>Dipendenti</h1>
          <span style={{ fontSize: 13, color: colors.textMuted, marginLeft: 4 }}>
            {dips.length} totali · {totPig} pignoramenti
          </span>
        </div>
      </div>

      <div style={{ ...s.card, padding: '12px 16px', ...s.flex, gap: 12 }}>
        <Search size={16} color={colors.textMuted} />
        <input
          style={{ ...s.input, border: 'none', padding: '4px 0' }}
          placeholder="Cerca per nome o C.F..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <Filter size={16} color={colors.textMuted} />
        <select
          style={{ ...s.select, minWidth: 130 }}
          value={filtro}
          onChange={e => setFiltro(e.target.value)}
        >
          <option value="">Tutti</option>
          <option value="attivo">Attivi</option>
          <option value="cessato">Cessati</option>
        </select>
      </div>

      <div style={{ ...s.card, padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Caricamento...</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Nessun dipendente trovato</div>
        ) : (
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>Cognome / Nome</th>
                <th style={s.th}>C.F.</th>
                <th style={s.th}>Ruolo</th>
                <th style={s.th}>Stipendio</th>
                <th style={s.th}>Stato</th>
                <th style={{ ...s.th, textAlign: 'center' }}>Pign.</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(d => (
                <tr
                  key={d._id}
                  onClick={() => nav(`/dipendenti/${d._id}`)}
                  style={s.trHover}
                  onMouseEnter={e => e.currentTarget.style.background = '#f8f9fb'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ ...s.td, fontWeight: 600 }}>
                    {d.cognome} {d.nome}
                  </td>
                  <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 13 }}>
                    {d.codice_fiscale}
                  </td>
                  <td style={s.td}>{d.ruolo || '—'}</td>
                  <td style={s.td}>{formatEuro(d.importo_stipendio)}</td>
                  <td style={s.td}>
                    <span style={statoBadge(d.stato)}>{d.stato}</span>
                  </td>
                  <td style={{ ...s.td, textAlign: 'center' }}>
                    {d.pignoramenti?.length || 0}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
