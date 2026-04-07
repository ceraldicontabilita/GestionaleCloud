import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Gavel, AlertTriangle } from 'lucide-react'
import { api } from '../lib/api'
import { s, colors, statoBadge, formatEuro, statoLabel } from '../lib/utils'

export default function Pignoramenti() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [filtroStato, setFiltroStato] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    api.getDipendenti()
      .then(dips => {
        const all = []
        for (const d of dips) {
          for (const p of d.pignoramenti || []) {
            all.push({ ...p, dipendente_id: d._id, dipendente_nome: `${d.cognome} ${d.nome}`, stato_dip: d.stato })
          }
        }
        all.sort((a, b) => (b.importo || 0) - (a.importo || 0))
        setRows(all)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const filtered = filtroStato ? rows.filter(r => r.stato === filtroStato) : rows
  const totale = filtered.reduce((a, r) => a + (r.importo || 0), 0)

  const statiSet = [...new Set(rows.map(r => r.stato))]

  return (
    <div>
      <div style={{ ...s.flexBetween, marginBottom: 20 }}>
        <div style={{ ...s.flex, gap: 12 }}>
          <Gavel size={24} color={colors.primary} />
          <h1 style={s.h1}>Pignoramenti</h1>
          <span style={{ fontSize: 13, color: colors.textMuted }}>
            {filtered.length} totali · {formatEuro(totale)}
          </span>
        </div>
        <select
          style={{ ...s.select, minWidth: 160 }}
          value={filtroStato}
          onChange={e => setFiltroStato(e.target.value)}
        >
          <option value="">Tutti gli stati</option>
          {statiSet.map(st => <option key={st} value={st}>{statoLabel(st)}</option>)}
        </select>
      </div>

      {/* Riepilogo cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 20 }}>
        <div style={{ ...s.card, padding: 16, borderLeft: `4px solid ${colors.danger}` }}>
          <div style={s.label}>Totale importi</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: colors.danger }}>{formatEuro(totale)}</div>
        </div>
        <div style={{ ...s.card, padding: 16, borderLeft: `4px solid ${colors.warning}` }}>
          <div style={s.label}>N° pignoramenti</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{filtered.length}</div>
        </div>
        <div style={{ ...s.card, padding: 16, borderLeft: `4px solid ${colors.primary}` }}>
          <div style={s.label}>Dipendenti coinvolti</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>
            {new Set(filtered.map(r => r.dipendente_id)).size}
          </div>
        </div>
      </div>

      <div style={{ ...s.card, padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Caricamento...</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Nessun pignoramento</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead>
                <tr>
                  <th style={s.th}>Dipendente</th>
                  <th style={s.th}>Ente</th>
                  <th style={s.th}>Targa</th>
                  <th style={s.th}>Anno</th>
                  <th style={s.th}>Data doc.</th>
                  <th style={{ ...s.th, textAlign: 'right' }}>Importo</th>
                  <th style={s.th}>Stato</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <tr
                    key={r.id}
                    style={s.trHover}
                    onClick={() => nav(`/dipendenti/${r.dipendente_id}`)}
                    onMouseEnter={e => e.currentTarget.style.background = '#f8f9fb'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}
                  >
                    <td style={{ ...s.td, fontWeight: 600 }}>
                      <div style={{ ...s.flex, gap: 8 }}>
                        {r.dipendente_nome}
                        {r.stato_dip === 'cessato' && (
                          <AlertTriangle size={14} color={colors.danger} title="Dipendente cessato" />
                        )}
                      </div>
                    </td>
                    <td style={{ ...s.td, textTransform: 'uppercase', fontSize: 13, fontWeight: 600 }}>
                      {r.ente_creditore}
                    </td>
                    <td style={{ ...s.td, fontFamily: 'monospace', fontWeight: 600 }}>{r.targa}</td>
                    <td style={s.td}>{r.anno_riferimento}</td>
                    <td style={{ ...s.td, fontSize: 13 }}>{r.data_documento}</td>
                    <td style={{ ...s.td, textAlign: 'right', fontWeight: 600 }}>{formatEuro(r.importo)}</td>
                    <td style={s.td}>
                      <span style={statoBadge(r.stato)}>{statoLabel(r.stato)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
