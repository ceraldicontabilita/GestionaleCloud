import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, User, Gavel, FileText, Download } from 'lucide-react'
import { api } from '../lib/api'
import { s, colors, statoBadge, formatEuro, statoLabel } from '../lib/utils'

export default function DettaglioDipendente() {
  const { id } = useParams()
  const nav = useNavigate()
  const [dip, setDip] = useState(null)
  const [loading, setLoading] = useState(true)
  const [genLoading, setGenLoading] = useState(null)

  const load = () => {
    setLoading(true)
    api.getDipendente(id)
      .then(setDip)
      .catch(e => { console.error(e); nav('/dipendenti') })
      .finally(() => setLoading(false))
  }

  useEffect(load, [id])

  const handleGenera = async (pigId) => {
    setGenLoading(pigId)
    try {
      const res = await api.generaDichiarazione(id, pigId)
      if (res.ok) {
        alert(`Dichiarazione generata: ${res.file}`)
        load()
      }
    } catch (e) {
      alert(`Errore: ${e.message}`)
    }
    setGenLoading(null)
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Caricamento...</div>
  if (!dip) return null

  const pigs = dip.pignoramenti || []
  const totPig = pigs.reduce((a, p) => a + (p.importo || 0), 0)

  return (
    <div>
      <button
        onClick={() => nav('/dipendenti')}
        style={{ ...s.btn, ...s.btnOutline, marginBottom: 16 }}
      >
        <ArrowLeft size={16} /> Torna alla lista
      </button>

      {/* Header */}
      <div style={{ ...s.card, ...s.flexBetween }}>
        <div style={{ ...s.flex, gap: 16 }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            background: dip.stato === 'attivo' ? colors.primary : '#9ca3af',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <User size={22} color="#fff" />
          </div>
          <div>
            <h1 style={{ ...s.h1, fontSize: 20 }}>{dip.cognome} {dip.nome}</h1>
            <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>
              {dip.ruolo || ''} · C.F. {dip.codice_fiscale}
            </div>
          </div>
        </div>
        <span style={statoBadge(dip.stato)}>{dip.stato}</span>
      </div>

      {/* Info grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 20 }}>
        {[
          ['Stipendio', formatEuro(dip.importo_stipendio)],
          ['IBAN', dip.iban || '—'],
          ['Stato', dip.stato],
          ['Data cessazione', dip.data_cessazione || '—'],
        ].map(([label, value]) => (
          <div key={label} style={{ ...s.card, padding: 16 }}>
            <div style={s.label}>{label}</div>
            <div style={{ ...s.value, fontFamily: label === 'IBAN' ? 'monospace' : 'inherit', fontSize: label === 'IBAN' ? 12 : 15 }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Pignoramenti */}
      <div style={s.card}>
        <div style={{ ...s.flexBetween, marginBottom: 16 }}>
          <div style={{ ...s.flex, gap: 8 }}>
            <Gavel size={18} color={colors.primary} />
            <h2 style={{ ...s.h2, margin: 0 }}>Pignoramenti ({pigs.length})</h2>
          </div>
          {totPig > 0 && (
            <span style={{ fontSize: 14, fontWeight: 600, color: colors.danger }}>
              Totale: {formatEuro(totPig)}
            </span>
          )}
        </div>

        {pigs.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: colors.textMuted }}>
            Nessun pignoramento
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead>
                <tr>
                  <th style={s.th}>Doc / Data</th>
                  <th style={s.th}>Ente</th>
                  <th style={s.th}>Targa</th>
                  <th style={s.th}>Anno</th>
                  <th style={{ ...s.th, textAlign: 'right' }}>Importo</th>
                  <th style={s.th}>Stato</th>
                  <th style={s.th}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {pigs.map(p => (
                  <tr key={p.id}>
                    <td style={s.td}>
                      <div style={{ fontSize: 12, fontFamily: 'monospace' }}>{p.numero_documento}</div>
                      <div style={{ fontSize: 12, color: colors.textMuted }}>{p.data_documento}</div>
                    </td>
                    <td style={{ ...s.td, textTransform: 'uppercase', fontSize: 13, fontWeight: 600 }}>
                      {p.ente_creditore}
                    </td>
                    <td style={{ ...s.td, fontFamily: 'monospace', fontWeight: 600 }}>{p.targa}</td>
                    <td style={s.td}>{p.anno_riferimento}</td>
                    <td style={{ ...s.td, textAlign: 'right', fontWeight: 600 }}>{formatEuro(p.importo)}</td>
                    <td style={s.td}>
                      <span style={statoBadge(p.stato)}>{statoLabel(p.stato)}</span>
                    </td>
                    <td style={s.td}>
                      <div style={{ ...s.flex, gap: 6 }}>
                        {p.stato === 'cessato_rapporto' && !p.dichiarazione_pdf_path && (
                          <button
                            onClick={() => handleGenera(p.id)}
                            disabled={genLoading === p.id}
                            style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall, opacity: genLoading === p.id ? 0.6 : 1 }}
                          >
                            <FileText size={14} />
                            {genLoading === p.id ? 'Genero...' : 'Genera Dich.'}
                          </button>
                        )}
                        {p.dichiarazione_pdf_path && (
                          <a
                            href={`/api/dipendenti/download/${p.dichiarazione_pdf_path}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ ...s.btn, ...s.btnOutline, ...s.btnSmall, textDecoration: 'none' }}
                          >
                            <Download size={14} /> PDF
                          </a>
                        )}
                      </div>
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
