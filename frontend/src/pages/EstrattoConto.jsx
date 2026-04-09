import React, { useState, useEffect, useCallback } from 'react'
import {
  Landmark, RefreshCw, TrendingUp, TrendingDown, Activity,
  CheckCircle, AlertCircle, Upload, ChevronDown, ChevronUp, Users
} from 'lucide-react'
import { colors, font, shadow, s, formatEuro } from '../lib/utils'

const API = '/api/estratto-conto'

// ─── helpers ────────────────────────────────────────────────────────────────

function fmtData(d) {
  if (!d) return '—'
  const [y, m, g] = d.split('-')
  return `${g}/${m}/${y}`
}

function badgeCategoria(cat) {
  const map = {
    bonifico_uscita: ['#FF9800', 'Bonifico Uscita'],
    bonifico_entrata: ['#00B884', 'Bonifico Entrata'],
    stipendio: ['#5D29C7', 'Stipendio'],
    f24: ['#F44336', 'F24'],
    domiciliazione: ['#2196F3', 'Domiciliazione'],
    commissioni: ['#9E9E9E', 'Commissioni'],
    pos: ['#00B884', 'POS'],
    mutuo: ['#FF5722', 'Mutuo'],
    assegno: ['#607D8B', 'Assegno'],
    prelievo: ['#795548', 'Prelievo'],
    altro: ['#9E9E9E', 'Altro'],
  }
  const [bg, label] = map[cat] || ['#9E9E9E', cat]
  return (
    <span style={{
      background: bg + '22', color: bg,
      border: `1px solid ${bg}44`,
      borderRadius: 20, padding: '2px 10px',
      fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap'
    }}>{label}</span>
  )
}

function badgeRiconciliato(r) {
  return r
    ? <span style={{ color: '#00B884', fontSize: 12, fontWeight: 700 }}>✓ Sì</span>
    : <span style={{ color: '#9E9E9E', fontSize: 12 }}>—</span>
}

function KpiCard({ label, value, icon: Icon, color, sub }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 16, padding: '20px 24px',
      boxShadow: shadow, display: 'flex', alignItems: 'center', gap: 16
    }}>
      <div style={{
        width: 48, height: 48, borderRadius: 12,
        background: color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center'
      }}>
        <Icon size={22} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 1, fontWeight: 700 }}>{label}</div>
        <div style={{ fontSize: 22, fontWeight: 800, color: colors.text, marginTop: 2 }}>{value}</div>
        {sub && <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  )
}

// ─── Tab Saldo ───────────────────────────────────────────────────────────────

function TabSaldo() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/saldo`)
      .then(r => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Caricamento…</div>
  if (!data) return null

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
      <KpiCard label="Saldo Netto" value={formatEuro(data.saldo)} icon={Activity}
        color={data.saldo >= 0 ? '#00B884' : '#F44336'}
        sub={`${data.n_movimenti} movimenti totali`} />
      <KpiCard label="Totale Entrate" value={formatEuro(data.entrate)} icon={TrendingUp} color="#00B884" />
      <KpiCard label="Totale Uscite" value={formatEuro(data.uscite)} icon={TrendingDown} color="#F44336" />
    </div>
  )
}

// ─── Tab Movimenti ───────────────────────────────────────────────────────────

function TabMovimenti() {
  const [items, setItems] = useState([])
  const [totale, setTotale] = useState(0)
  const [loading, setLoading] = useState(false)
  const [categoria, setCategoria] = useState('')
  const [riconciliato, setRiconciliato] = useState('')
  const [dataDa, setDataDa] = useState('')
  const [dataA, setDataA] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)

  const carica = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({ limit: 200 })
    if (categoria) params.set('categoria', categoria)
    if (dataDa) params.set('data_da', dataDa)
    if (dataA) params.set('data_a', dataA)
    if (riconciliato !== '') params.set('riconciliato', riconciliato)
    const r = await fetch(`${API}?${params}`)
    const d = await r.json()
    setItems(d.items || [])
    setTotale(d.totale || 0)
    setLoading(false)
  }, [categoria, dataDa, dataA, riconciliato])

  useEffect(() => { carica() }, [carica])

  async function handleUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    setUploadMsg(null)
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch(`${API}/upload-pdf`, { method: 'POST', body: fd })
    const d = await r.json()
    setUploading(false)
    if (d.ok) {
      setUploadMsg({ ok: true, msg: `Importati ${d.importati} movimenti (${d.duplicati} duplicati)` })
      carica()
    } else {
      setUploadMsg({ ok: false, msg: d.detail || 'Errore upload' })
    }
    e.target.value = ''
  }

  const inputStyle = {
    border: `1px solid ${colors.border}`, borderRadius: 8,
    padding: '7px 12px', fontSize: 13, color: colors.text,
    background: '#fff', outline: 'none'
  }

  return (
    <div>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
        <select value={categoria} onChange={e => setCategoria(e.target.value)} style={inputStyle}>
          <option value="">Tutte le categorie</option>
          {['bonifico_uscita','bonifico_entrata','stipendio','f24','domiciliazione','commissioni','pos','mutuo','assegno','prelievo','altro']
            .map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={riconciliato} onChange={e => setRiconciliato(e.target.value)} style={inputStyle}>
          <option value="">Tutti</option>
          <option value="false">Non riconciliati</option>
          <option value="true">Riconciliati</option>
        </select>
        <input type="date" value={dataDa} onChange={e => setDataDa(e.target.value)} style={inputStyle} placeholder="Da" />
        <input type="date" value={dataA} onChange={e => setDataA(e.target.value)} style={inputStyle} placeholder="A" />
        <label style={{
          ...s.btnPrimary, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
          opacity: uploading ? 0.6 : 1
        }}>
          <Upload size={14} />
          {uploading ? 'Caricamento…' : 'Carica PDF'}
          <input type="file" accept=".pdf" style={{ display: 'none' }} onChange={handleUpload} disabled={uploading} />
        </label>
        <span style={{ color: colors.textMuted, fontSize: 13 }}>{totale} movimenti</span>
      </div>

      {uploadMsg && (
        <div style={{
          padding: '10px 16px', borderRadius: 8, marginBottom: 12,
          background: uploadMsg.ok ? '#00B88422' : '#F4433622',
          color: uploadMsg.ok ? '#00B884' : '#F44336',
          border: `1px solid ${uploadMsg.ok ? '#00B88444' : '#F4433644'}`,
          fontSize: 13, fontWeight: 600
        }}>{uploadMsg.msg}</div>
      )}

      {/* Tabella */}
      <div style={{ overflowX: 'auto' }}>
        <table style={s.table}>
          <thead>
            <tr>
              {['Data Op.','Data Val.','Descrizione','Categoria','Dare','Avere','Ric.'].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>Caricamento…</td></tr>
              : items.length === 0
                ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>Nessun movimento</td></tr>
                : items.map((it, i) => (
                  <tr key={it._id} style={{ background: i % 2 === 0 ? '#fff' : '#F8F9FD' }}>
                    <td style={s.td}>{fmtData(it.data_operazione)}</td>
                    <td style={s.td}>{fmtData(it.data_valuta)}</td>
                    <td style={{ ...s.td, maxWidth: 300, fontSize: 12 }}>{it.descrizione}</td>
                    <td style={s.td}>{badgeCategoria(it.categoria)}</td>
                    <td style={{ ...s.td, textAlign: 'right', color: '#F44336', fontWeight: 600 }}>
                      {it.dare ? formatEuro(it.dare) : ''}
                    </td>
                    <td style={{ ...s.td, textAlign: 'right', color: '#00B884', fontWeight: 600 }}>
                      {it.avere ? formatEuro(it.avere) : ''}
                    </td>
                    <td style={s.td}>{badgeRiconciliato(it.riconciliato)}</td>
                  </tr>
                ))
            }
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Tab Stipendi ────────────────────────────────────────────────────────────

function TabStipendi() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [riconciliando, setRiconciliando] = useState(false)
  const [risultatoRic, setRisultatoRic] = useState(null)
  const [filtroRic, setFiltroRic] = useState('')
  const [anno, setAnno] = useState(new Date().getFullYear())
  const [expanded, setExpanded] = useState({})

  const carica = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({ anno })
    if (filtroRic !== '') params.set('riconciliato', filtroRic)
    const r = await fetch(`${API}/stipendi?${params}`)
    const d = await r.json()
    setItems(d.items || [])
    setLoading(false)
  }, [anno, filtroRic])

  useEffect(() => { carica() }, [carica])

  async function handleRiconcilia() {
    if (!confirm('Avvia riconciliazione stipendi? Cercherà di collegare i movimenti ai cedolini.')) return
    setRiconciliando(true)
    setRisultatoRic(null)
    const r = await fetch(`${API}/riconcilia-stipendi`, { method: 'POST' })
    const d = await r.json()
    setRisultatoRic(d)
    setRiconciliando(false)
    carica()
  }

  const totaleRiconciliati = items.filter(i => i.riconciliato).length
  const totaleNonRiconciliati = items.filter(i => !i.riconciliato).length
  const totalePagato = items.reduce((acc, i) => acc + Math.abs(i.importo || 0), 0)

  const inputStyle = {
    border: `1px solid ${colors.border}`, borderRadius: 8,
    padding: '7px 12px', fontSize: 13, color: colors.text, background: '#fff'
  }

  return (
    <div>
      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 20 }}>
        <KpiCard label="Totale Pagato" value={formatEuro(totalePagato)} icon={TrendingDown} color="#F44336" />
        <KpiCard label="Riconciliati" value={totaleRiconciliati} icon={CheckCircle} color="#00B884" sub="collegati a cedolino" />
        <KpiCard label="Non Riconciliati" value={totaleNonRiconciliati} icon={AlertCircle} color="#FF9800" sub="da verificare" />
        <KpiCard label="Dipendenti" value={new Set(items.map(i => i.cedolino_cf || i.dipendente).filter(Boolean)).size} icon={Users} color="#5D29C7" />
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
        <select value={anno} onChange={e => setAnno(Number(e.target.value))} style={inputStyle}>
          {[2026, 2025, 2024, 2023].map(y => <option key={y} value={y}>{y}</option>)}
        </select>
        <select value={filtroRic} onChange={e => setFiltroRic(e.target.value)} style={inputStyle}>
          <option value="">Tutti</option>
          <option value="false">Non riconciliati</option>
          <option value="true">Riconciliati</option>
        </select>
        <button
          onClick={handleRiconcilia}
          disabled={riconciliando}
          style={{ ...s.btnPrimary, display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <RefreshCw size={14} style={{ animation: riconciliando ? 'spin 1s linear infinite' : 'none' }} />
          {riconciliando ? 'Riconciliazione…' : 'Riconcilia ora'}
        </button>
      </div>

      {/* Risultato riconciliazione */}
      {risultatoRic && (
        <div style={{
          padding: '12px 16px', borderRadius: 10, marginBottom: 16,
          background: '#5D29C722', border: '1px solid #5D29C744'
        }}>
          <div style={{ fontWeight: 700, color: '#5D29C7', marginBottom: 6 }}>
            Riconciliazione completata: {risultatoRic.riconciliati} di {risultatoRic.totale_elaborati} collegati
          </div>
          {risultatoRic.non_trovati?.length > 0 && (
            <div>
              <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4, fontWeight: 600 }}>
                Non trovati ({risultatoRic.non_trovati.length}):
              </div>
              {risultatoRic.non_trovati.map((nf, i) => (
                <div key={i} style={{ fontSize: 12, color: colors.text, padding: '3px 0' }}>
                  {fmtData(nf.data)} — {formatEuro(nf.importo)} — {nf.nome_estratto || nf.descrizione?.slice(0, 50)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tabella */}
      <div style={{ overflowX: 'auto' }}>
        <table style={s.table}>
          <thead>
            <tr>
              {['Data','Dipendente','Importo Bonif.','Cedolino Netto','Mese Ced.','Stato'].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
              <th style={s.th}></th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>Caricamento…</td></tr>
              : items.length === 0
                ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>Nessun movimento stipendio</td></tr>
                : items.map((it, i) => {
                  const nome = it.cedolino_nome || it.dipendente || '—'
                  const isExp = expanded[it._id]
                  const diff = it.riconciliato && it.cedolino_netto
                    ? Math.abs(Math.abs(it.importo) - it.cedolino_netto)
                    : null

                  return (
                    <React.Fragment key={it._id}>
                      <tr style={{ background: i % 2 === 0 ? '#fff' : '#F8F9FD', cursor: 'pointer' }}
                        onClick={() => setExpanded(e => ({ ...e, [it._id]: !e[it._id] }))}>
                        <td style={s.td}>{fmtData(it.data_operazione)}</td>
                        <td style={{ ...s.td, fontWeight: 600 }}>{nome}</td>
                        <td style={{ ...s.td, textAlign: 'right', color: '#F44336', fontWeight: 700 }}>
                          {formatEuro(Math.abs(it.importo || 0))}
                        </td>
                        <td style={{ ...s.td, textAlign: 'right', color: it.cedolino_netto ? colors.text : colors.textMuted }}>
                          {it.cedolino_netto ? formatEuro(it.cedolino_netto) : '—'}
                        </td>
                        <td style={s.td}>
                          {it.cedolino_mese && it.cedolino_anno
                            ? `${String(it.cedolino_mese).padStart(2, '0')}/${it.cedolino_anno}`
                            : '—'}
                        </td>
                        <td style={s.td}>
                          {it.riconciliato
                            ? <span style={{ color: '#00B884', fontWeight: 700, fontSize: 12 }}>✓ Riconciliato</span>
                            : <span style={{ color: '#FF9800', fontWeight: 700, fontSize: 12 }}>⚠ Da verificare</span>}
                        </td>
                        <td style={{ ...s.td, color: colors.textMuted }}>
                          {isExp ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </td>
                      </tr>
                      {isExp && (
                        <tr style={{ background: '#F0F4FA' }}>
                          <td colSpan={7} style={{ padding: '12px 20px' }}>
                            <div style={{ fontSize: 12, color: colors.text, lineHeight: 1.8 }}>
                              <strong>Descrizione:</strong> {it.descrizione}<br />
                              <strong>Categoria:</strong> {it.categoria}<br />
                              {it.cedolino_cf && <><strong>Codice Fiscale:</strong> {it.cedolino_cf}<br /></>}
                              {diff !== null && (
                                <span style={{ color: diff < 0.5 ? '#00B884' : '#FF9800', fontWeight: 600 }}>
                                  Differenza bonifico/cedolino: {formatEuro(diff)}
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })
            }
          </tbody>
        </table>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

// ─── Pagina principale ───────────────────────────────────────────────────────

const TABS = [
  { key: 'saldo', label: 'Saldo' },
  { key: 'stipendi', label: 'Stipendi' },
  { key: 'movimenti', label: 'Tutti i Movimenti' },
]

export default function EstrattoConto() {
  const [tab, setTab] = useState('saldo')

  return (
    <div style={s.page}>
      <div style={{ ...s.flexBetween, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: 'linear-gradient(135deg,#5D29C7,#7C3AED)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Landmark size={22} color="#fff" />
          </div>
          <div>
            <h1 style={s.h1}>Estratto Conto</h1>
            <div style={{ fontSize: 13, color: colors.textMuted }}>Banco BPM — movimenti e riconciliazione stipendi</div>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: `2px solid ${colors.border}` }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '10px 20px', fontSize: 14, fontWeight: 600,
            color: tab === t.key ? '#5D29C7' : colors.textMuted,
            borderBottom: tab === t.key ? '2px solid #5D29C7' : '2px solid transparent',
            marginBottom: -2, transition: 'all .15s'
          }}>{t.label}</button>
        ))}
      </div>

      <div style={s.card}>
        {tab === 'saldo' && <TabSaldo />}
        {tab === 'stipendi' && <TabStipendi />}
        {tab === 'movimenti' && <TabMovimenti />}
      </div>
    </div>
  )
}
