import { useState, useEffect, useCallback } from 'react'
import { Tablet, RefreshCw, ChefHat, Cake, CheckCircle, Clock, AlertTriangle } from 'lucide-react'
import { s, colors, font, formatEuro } from '../lib/utils'

const API_EXT = '/api/tr'

const REPARTI = [
  { key: 'rosticceria', label: 'Rosticceria', icon: ChefHat, colore: '#C2410C', bg: '#FFF7ED', border: '#F97316' },
  { key: 'pasticceria', label: 'Pasticceria', icon: Cake,    colore: '#7C3AED', bg: '#F5F3FF', border: '#8B5CF6' },
]

function fmtData(d) {
  if (!d) return '—'
  try { return new Date(d).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) }
  catch { return d }
}

// ─── KPI CARD ────────────────────────────────────────────────────────────────
function KpiCard({ label, value, icon: Icon, colore, bg }) {
  return (
    <div style={{
      background: bg || '#fff', borderRadius: 12, padding: '14px 18px',
      border: `1px solid ${colore}30`,
      display: 'flex', alignItems: 'center', gap: 12
    }}>
      <div style={{
        width: 38, height: 38, borderRadius: 10,
        background: colore + '20', display: 'flex', alignItems: 'center', justifyContent: 'center'
      }}>
        <Icon size={18} color={colore} />
      </div>
      <div>
        <div style={{ fontSize: 10, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 1, fontWeight: 700 }}>{label}</div>
        <div style={{ fontSize: 20, fontWeight: 800, color: colors.text }}>{value}</div>
      </div>
    </div>
  )
}

// ─── PANNELLO REPARTO ────────────────────────────────────────────────────────
function PannelloReparto({ reparto }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [errore, setErrore] = useState(null)
  const [ultimoAggio, setUltimoAggio] = useState(null)

  const carica = useCallback(async () => {
    setLoading(true); setErrore(null)
    try {
      const r = await fetch(`${API_EXT}/tablet/${reparto.key}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d = await r.json()
      setData(d)
      setUltimoAggio(new Date())
    } catch (e) {
      setErrore(`Errore connessione ceraldiapp.it: ${e.message}`)
    }
    setLoading(false)
  }, [reparto.key])

  useEffect(() => { carica() }, [carica])

  // Auto-refresh ogni 60 secondi
  useEffect(() => {
    const t = setInterval(carica, 60000)
    return () => clearInterval(t)
  }, [carica])

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 48, color: colors.textMuted }}>
      <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite' }} />
      <p style={{ marginTop: 10 }}>Caricamento {reparto.label}…</p>
    </div>
  )

  if (errore) return (
    <div style={{
      padding: 20, borderRadius: 12, background: '#FEF2F2',
      border: '1px solid #FECACA', color: '#DC2626',
      display: 'flex', alignItems: 'center', gap: 10
    }}>
      <AlertTriangle size={18} />
      <div>
        <div style={{ fontWeight: 700 }}>Errore di connessione</div>
        <div style={{ fontSize: 13, marginTop: 2 }}>{errore}</div>
      </div>
      <button onClick={carica} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, marginLeft: 'auto' }}>
        <RefreshCw size={13} /> Riprova
      </button>
    </div>
  )

  if (!data) return null

  // Struttura tipica di /api/tablet/{reparto}:
  // { lotti: [], operatori: [], produzione_oggi: [], riepilogo: {} }
  const lotti      = data.lotti || data.lotti_attivi || []
  const operatori  = data.operatori || []
  const produzioni = data.produzione_oggi || data.produzioni || []
  const riepilogo  = data.riepilogo || {}

  const lottiAttivi   = lotti.filter(l => l.stato !== 'consumato' && l.stato !== 'scaduto')
  const lottiInScad   = lotti.filter(l => {
    if (!l.data_scadenza) return false
    const diff = (new Date(l.data_scadenza) - new Date()) / 86400000
    return diff >= 0 && diff <= 3
  })

  return (
    <div>
      {/* Header reparto + ultimo aggiornamento */}
      <div style={{ ...s.flexBetween, marginBottom: 16 }}>
        <div style={{ ...s.flex, gap: 8 }}>
          <div style={{
            padding: '6px 14px', borderRadius: 20,
            background: reparto.bg, border: `1px solid ${reparto.border}40`,
            color: reparto.colore, fontWeight: 700, fontSize: 13
          }}>
            <reparto.icon size={13} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            {reparto.label}
          </div>
          {lottiInScad.length > 0 && (
            <span style={{ ...s.badge('#F44336', '#FEF2F2'), display: 'flex', alignItems: 'center', gap: 4 }}>
              <AlertTriangle size={11} /> {lottiInScad.length} in scadenza
            </span>
          )}
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          {ultimoAggio && (
            <span style={{ fontSize: 11, color: colors.textMuted }}>
              <Clock size={10} style={{ marginRight: 3 }} />
              Aggiornato {ultimoAggio.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button onClick={carica} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
            <RefreshCw size={12} />
          </button>
          <a
            href={`https://ceraldiapp.it/#tablet/${reparto.key}`}
            target="_blank" rel="noopener noreferrer"
            style={{ ...s.btnPrimary, ...s.btn, fontSize: 12, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5 }}
          >
            <Tablet size={13} /> Apri Tablet
          </a>
        </div>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 20 }}>
        <KpiCard label="Lotti Attivi"    value={lottiAttivi.length}   icon={CheckCircle} colore={reparto.colore} />
        <KpiCard label="Produzioni Oggi" value={produzioni.length}    icon={reparto.icon} colore={reparto.colore} />
        <KpiCard label="Operatori"       value={operatori.length}     icon={ChefHat}     colore="#5D29C7" />
        {riepilogo.pezzi_totali != null && (
          <KpiCard label="Pezzi Totali"  value={riepilogo.pezzi_totali} icon={CheckCircle} colore="#00B884" />
        )}
      </div>

      {/* Operatori */}
      {operatori.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ ...s.label, marginBottom: 8 }}>Operatori in turno</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {operatori.map((op, i) => (
              <span key={i} style={{
                padding: '5px 12px', borderRadius: 20,
                background: reparto.bg, border: `1px solid ${reparto.border}40`,
                color: reparto.colore, fontSize: 13, fontWeight: 600
              }}>
                {typeof op === 'string' ? op : op.nome || op.operatore || JSON.stringify(op)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Lotti attivi */}
      {lottiAttivi.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ ...s.label, marginBottom: 8 }}>Lotti attivi</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead>
                <tr>
                  {['Lotto','Prodotto','Quantità','Scadenza','Stato'].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lottiAttivi.map((l, i) => {
                  const inScad = lottiInScad.includes(l)
                  return (
                    <tr key={l._id || i} style={{ background: i % 2 === 0 ? '#fff' : '#F8F9FD' }}>
                      <td style={{ ...s.td, fontWeight: 700, color: reparto.colore, fontFamily: 'monospace', fontSize: 12 }}>
                        {l.codice_lotto || l.lotto || l._id?.slice(-6) || '—'}
                      </td>
                      <td style={{ ...s.td, fontSize: 13 }}>{l.prodotto || l.nome_prodotto || '—'}</td>
                      <td style={{ ...s.td, textAlign: 'right' }}>
                        {l.quantita != null ? `${l.quantita} ${l.unita || 'pz'}` : '—'}
                      </td>
                      <td style={{ ...s.td, color: inScad ? '#F44336' : colors.text, fontWeight: inScad ? 700 : 400 }}>
                        {l.data_scadenza ? new Date(l.data_scadenza).toLocaleDateString('it-IT') : '—'}
                        {inScad && ' ⚠'}
                      </td>
                      <td style={s.td}>
                        <span style={{
                          ...s.badge(
                            l.stato === 'attivo' ? '#00B884' : l.stato === 'in_uso' ? reparto.colore : '#9E9E9E',
                            l.stato === 'attivo' ? '#ECFDF5' : l.stato === 'in_uso' ? reparto.bg : '#F5F5F5'
                          )
                        }}>{l.stato || '—'}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Produzioni oggi */}
      {produzioni.length > 0 && (
        <div>
          <div style={{ ...s.label, marginBottom: 8 }}>Produzioni di oggi</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead>
                <tr>
                  {['Ora','Prodotto','Pezzi','Operatore','Lotto'].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {produzioni.map((p, i) => (
                  <tr key={p._id || i} style={{ background: i % 2 === 0 ? '#fff' : '#F8F9FD' }}>
                    <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 12 }}>
                      {fmtData(p.timestamp || p.created_at)}
                    </td>
                    <td style={{ ...s.td, fontSize: 13 }}>{p.prodotto || p.nome_prodotto || '—'}</td>
                    <td style={{ ...s.td, textAlign: 'right', fontWeight: 600 }}>{p.pezzi ?? p.quantita ?? '—'}</td>
                    <td style={{ ...s.td, fontSize: 13 }}>{p.operatore || '—'}</td>
                    <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 11, color: reparto.colore }}>
                      {p.codice_lotto || p.lotto_id?.slice(-6) || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Nessun dato */}
      {lottiAttivi.length === 0 && produzioni.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>
          <reparto.icon size={32} style={{ opacity: 0.2, marginBottom: 10 }} />
          <p>Nessun dato disponibile per {reparto.label} oggi</p>
          <a href={`https://ceraldiapp.it/#tablet/${reparto.key}`} target="_blank" rel="noopener noreferrer"
            style={{ ...s.btnPrimary, ...s.btn, marginTop: 12, textDecoration: 'none', display: 'inline-flex' }}>
            <Tablet size={14} /> Apri Tablet
          </a>
        </div>
      )}
    </div>
  )
}

// ─── PAGINA PRINCIPALE ───────────────────────────────────────────────────────
export default function TabletCucina() {
  const [tab, setTab] = useState('rosticceria')
  const reparto = REPARTI.find(r => r.key === tab)

  return (
    <div style={s.page}>
      <div style={{ ...s.flexBetween, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: 'linear-gradient(135deg,#5D29C7,#7C3AED)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Tablet size={22} color="#fff" />
          </div>
          <div>
            <h1 style={s.h1}>Tablet Cucina</h1>
            <div style={{ fontSize: 13, color: colors.textMuted }}>
              Stato produzione in tempo reale — ceraldiapp.it
            </div>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: `2px solid ${colors.border}` }}>
        {REPARTI.map(r => (
          <button key={r.key} onClick={() => setTab(r.key)} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '10px 20px', fontSize: 14, fontWeight: 600,
            color: tab === r.key ? r.colore : colors.textMuted,
            borderBottom: tab === r.key ? `2px solid ${r.colore}` : '2px solid transparent',
            marginBottom: -2, transition: 'all .15s',
            display: 'flex', alignItems: 'center', gap: 6
          }}>
            <r.icon size={15} /> {r.label}
          </button>
        ))}
      </div>

      <div style={s.card}>
        <PannelloReparto reparto={reparto} />
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
