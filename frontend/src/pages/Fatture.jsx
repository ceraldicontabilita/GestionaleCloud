import React, { useState, useEffect, useRef } from 'react'
import { FileText, RefreshCw, Upload, AlertCircle, CheckCircle, Clock, Wifi } from 'lucide-react'
import { s, colors, formatEuro } from '../lib/utils'

const columns = [
  { key: 'data', label: 'Data' },
  { key: 'numero', label: 'Numero', mono: true },
  { key: 'fornitore', label: 'Fornitore', render: r => r.fornitore_denominazione || '—' },
  { key: 'piva', label: 'P.IVA', mono: true, render: r => r.fornitore_piva || '—' },
  { key: 'imponibile', label: 'Imponibile', align: 'right', render: r => formatEuro(r.imponibile) },
  { key: 'iva', label: 'IVA', align: 'right', render: r => formatEuro(r.iva) },
  { key: 'importo_totale', label: 'Totale', align: 'right', render: r => formatEuro(r.importo_totale) },
  {
    key: 'source', label: 'Fonte',
    render: r => r.source === 'pec_auto'
      ? <span style={{ fontSize: 11, fontWeight: 600, color: '#2563eb', background: '#dbeafe', padding: '2px 8px', borderRadius: 10 }}>PEC AUTO</span>
      : <span style={{ fontSize: 11, color: colors.textMuted }}>manuale</span>
  },
  { key: 'stato', label: 'Stato', render: r => r.stato || '—' },
]

export default function Fatture() {
  const [items, setItems] = useState([])
  const [totale, setTotale] = useState(0)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [syncResult, setSyncResult] = useState(null)
  const [syncLog, setSyncLog] = useState([])
  const [showLog, setShowLog] = useState(false)
  const [tab, setTab] = useState('fatture') // 'fatture' | 'log'
  const fileRef = useRef()
  const anno = new Date().getFullYear()

  const load = () => {
    setLoading(true)
    fetch('/api/fatture')
      .then(r => r.json())
      .then(d => { setItems(d.items || []); setTotale(d.totale || 0) })
      .catch(console.error)
      .finally(() => setLoading(false))

    fetch(`/api/fatture/stats?anno=${anno}`)
      .then(r => r.json())
      .then(setStats)
      .catch(() => {})

    fetch('/api/fatture/sync-log?limit=10')
      .then(r => r.json())
      .then(d => setSyncLog(d.items || []))
      .catch(() => {})
  }

  useEffect(load, [])

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadResult(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await fetch('/api/fatture/upload-xml', { method: 'POST', body: fd })
      const data = await res.json()
      setUploadResult({ ...data, type: 'upload' })
      if (data.ok) load()
    } catch (err) {
      setUploadResult({ ok: false, error: err.message, type: 'upload' })
    }
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleSync = async (dryRun = false) => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await fetch(`/api/fatture/sync-pec${dryRun ? '?dry_run=true' : ''}`, { method: 'POST' })
      const data = await res.json()
      setSyncResult({ ...data, type: 'sync', dry_run: dryRun })
      if (!dryRun && data.ok) load()
    } catch (err) {
      setSyncResult({ ok: false, error: err.message, type: 'sync' })
    }
    setSyncing(false)
  }

  const lastSync = syncLog[0]

  return (
    <div>
      {/* Header */}
      <div style={{ ...s.flexBetween, marginBottom: 20 }}>
        <div style={{ ...s.flex, gap: 12 }}>
          <FileText size={24} color={colors.primary} />
          <h1 style={s.h1}>Fatture Passive</h1>
          <span style={{ fontSize: 13, color: colors.textMuted }}>{totale} documenti</span>
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          {/* Upload manuale */}
          <label style={{ ...s.btn, ...s.btnOutline, cursor: 'pointer', opacity: uploading ? 0.6 : 1 }}>
            <Upload size={15} />
            {uploading ? 'Caricamento...' : 'Carica XML'}
            <input ref={fileRef} type="file" accept=".xml,.p7m,.zip" onChange={handleUpload}
              style={{ display: 'none' }} disabled={uploading} />
          </label>
          {/* Sync PEC (dry run) */}
          <button
            onClick={() => handleSync(true)}
            disabled={syncing}
            style={{ ...s.btn, ...s.btnOutline, opacity: syncing ? 0.6 : 1 }}
          >
            <Wifi size={15} />
            Anteprima PEC
          </button>
          {/* Sync PEC reale */}
          <button
            onClick={() => handleSync(false)}
            disabled={syncing}
            style={{ ...s.btn, ...s.btnPrimary, opacity: syncing ? 0.6 : 1 }}
          >
            <RefreshCw size={15} style={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }} />
            {syncing ? 'Sync in corso...' : 'Sync PEC SDI'}
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
          {[
            ['Totale fatture', stats.count, null],
            ['Imponibile', formatEuro(stats.imponibile), null],
            ['IVA', formatEuro(stats.iva), null],
            ['Totale', formatEuro(stats.totale), null],
            ['Da PEC auto', stats.da_pec, '#2563eb'],
          ].map(([label, value, color]) => (
            <div key={label} style={{ ...s.card, padding: 14 }}>
              <div style={s.label}>{label}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: color || colors.text }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Ultimo sync */}
      {lastSync && (
        <div style={{ ...s.card, padding: '10px 16px', marginBottom: 12, ...s.flex, gap: 10, background: '#f0fdf4', border: '1px solid #bbf7d0' }}>
          <Clock size={14} color={colors.success} />
          <span style={{ fontSize: 13, color: '#15803d' }}>
            Ultimo sync: {new Date(lastSync.timestamp).toLocaleString('it-IT')} —
            {' '}{lastSync.email_processate} email, {lastSync.inserite} inserite, {lastSync.duplicate} duplicate
          </span>
          <button onClick={() => setTab(tab === 'log' ? 'fatture' : 'log')}
            style={{ ...s.btn, ...s.btnSmall, ...s.btnOutline, marginLeft: 'auto' }}>
            {tab === 'log' ? 'Torna alle fatture' : 'Vedi storico sync'}
          </button>
        </div>
      )}

      {/* Risultato upload */}
      {uploadResult && (
        <div style={{ ...s.card, padding: '12px 16px', marginBottom: 12, borderLeft: `4px solid ${uploadResult.ok ? colors.success : colors.danger}` }}>
          {uploadResult.ok
            ? <span style={{ color: colors.success, fontWeight: 600 }}>
                <CheckCircle size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                Importate {uploadResult.inserite} fatture ({uploadResult.duplicate} duplicate)
              </span>
            : <span style={{ color: colors.danger }}>
                <AlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                {uploadResult.error || 'Errore upload'}
              </span>
          }
        </div>
      )}

      {/* Risultato sync */}
      {syncResult && (
        <div style={{ ...s.card, padding: '12px 16px', marginBottom: 12, borderLeft: `4px solid ${syncResult.ok ? '#2563eb' : colors.danger}` }}>
          {syncResult.ok ? (
            <div>
              <div style={{ fontWeight: 600, color: '#2563eb', marginBottom: syncResult.messaggi?.length ? 8 : 0 }}>
                {syncResult.dry_run ? '🔍 Anteprima PEC: ' : '✅ Sync completata: '}
                {syncResult.email_processate} email SDI trovate
                {!syncResult.dry_run && ` → ${syncResult.inserite} inserite, ${syncResult.duplicate} duplicate`}
              </div>
              {syncResult.messaggi?.length > 0 && (
                <div style={{ fontSize: 13, color: colors.textMuted }}>
                  {syncResult.messaggi.map((m, i) => (
                    <div key={i} style={{ padding: '4px 0', borderBottom: `1px solid ${colors.border}` }}>
                      <span style={{ fontFamily: 'monospace', marginRight: 8 }}>{m.filename}</span>
                      <span style={{ color: colors.textMuted }}>{m.date?.substring(0, 16)}</span>
                      {m.errore && <span style={{ color: colors.danger, marginLeft: 8 }}>⚠ {m.errore}</span>}
                      {!syncResult.dry_run && !m.errore && (
                        <span style={{ color: colors.success, marginLeft: 8 }}>+{m.inserite} fatture</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {syncResult.email_processate === 0 && (
                <span style={{ color: colors.textMuted, fontSize: 13 }}>Nessuna email SDI non letta in PEC</span>
              )}
            </div>
          ) : (
            <span style={{ color: colors.danger }}>
              <AlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              {syncResult.error || 'Errore sync PEC'}
            </span>
          )}
        </div>
      )}

      {/* TAB: Fatture o Log */}
      {tab === 'log' ? (
        <div style={{ ...s.card, padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: `1px solid ${colors.border}`, fontWeight: 600, color: colors.primary }}>
            Storico sincronizzazioni PEC
          </div>
          {syncLog.length === 0
            ? <div style={{ padding: 32, textAlign: 'center', color: colors.textMuted }}>Nessuna sync ancora eseguita</div>
            : syncLog.map((log, i) => (
              <div key={i} style={{ padding: '12px 16px', borderBottom: `1px solid ${colors.border}`, fontSize: 13 }}>
                <div style={{ ...s.flexBetween }}>
                  <span style={{ fontWeight: 600 }}>{new Date(log.timestamp).toLocaleString('it-IT')}</span>
                  <span style={{ color: colors.success }}>+{log.inserite} inserite</span>
                </div>
                <div style={{ color: colors.textMuted, marginTop: 4 }}>
                  {log.email_processate} email · {log.duplicate} duplicate
                </div>
              </div>
            ))
          }
        </div>
      ) : (
        <div style={{ ...s.card, padding: 0, overflow: 'hidden' }}>
          {loading
            ? <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Caricamento...</div>
            : items.length === 0
            ? <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>
                <FileText size={32} color={colors.border} style={{ marginBottom: 8, display: 'block', margin: '0 auto 8px' }} />
                Nessuna fattura. Carica un XML o sincronizza dalla PEC SDI.
              </div>
            : <div style={{ overflowX: 'auto' }}>
                <table style={s.table}>
                  <thead>
                    <tr>{columns.map(c => (
                      <th key={c.key} style={{ ...s.th, ...(c.align === 'right' ? { textAlign: 'right' } : {}) }}>
                        {c.label}
                      </th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {items.map((item, idx) => (
                      <tr key={item._id || idx}
                        onMouseEnter={e => e.currentTarget.style.background = '#f8f9fb'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}>
                        {columns.map(c => (
                          <td key={c.key} style={{
                            ...s.td,
                            ...(c.align === 'right' ? { textAlign: 'right', fontWeight: 600 } : {}),
                            ...(c.mono ? { fontFamily: 'monospace', fontSize: 13 } : {})
                          }}>
                            {c.render ? c.render(item) : (item[c.key] ?? '—')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
          }
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
      `}</style>
    </div>
  )
}
