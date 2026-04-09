import React, { useState, useEffect, useCallback } from 'react'
import {
  BookOpen, Landmark, Wallet, Clock, Plus, Trash2, Check, CheckCheck,
  RefreshCw, Download, Filter, ChevronDown, ChevronUp, Edit2, X
} from 'lucide-react'
import { s, colors, font, formatEuro } from '../lib/utils'

const API = '/api/prima-nota'

const SEZIONI = [
  { id: 'cassa', label: 'Cassa', icon: Wallet, color: '#059669', bg: '#d1fae5', desc: 'Incassi giornalieri, corrispettivi RT' },
  { id: 'banca', label: 'Banca', icon: Landmark, color: '#2563eb', bg: '#dbeafe', desc: 'Movimenti c/c Banco BPM, F24, stipendi' },
  { id: 'provvisoria', label: 'Provvisoria', icon: Clock, color: '#d97706', bg: '#fef3c7', desc: 'Fatture da pagare, crediti da incassare' },
]

const CATEGORIE = {
  cassa: ['incasso_corrispettivo', 'incasso_pos', 'prelievo', 'versamento', 'altro'],
  banca: ['bonifico_uscita', 'bonifico_entrata', 'f24', 'stipendio', 'pos', 'domiciliazione', 'commissioni', 'prelievo', 'mutuo', 'altro'],
  provvisoria: ['fornitore', 'tributo', 'utenza', 'altro'],
}

function SaldoCard({ sez, saldi, onGenera, loading }) {
  const cfg = SEZIONI.find(s => s.id === sez)
  const Icon = cfg.icon
  const d = saldi || {}
  return (
    <div style={{ ...s.card, borderLeft: `4px solid ${cfg.color}`, padding: 16 }}>
      <div style={{ ...s.flex, gap: 8, marginBottom: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: cfg.bg,
          display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={18} color={cfg.color} />
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: cfg.color }}>{cfg.label}</div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>{cfg.desc}</div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>Saldo</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: (d.saldo || 0) >= 0 ? colors.success : colors.danger }}>
            {formatEuro(d.saldo || 0)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>Entrate</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: colors.success }}>{formatEuro(d.entrate || 0)}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>Uscite</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: colors.danger }}>{formatEuro(d.uscite || 0)}</div>
        </div>
      </div>
      <div style={{ ...s.flex, gap: 8 }}>
        <span style={{ fontSize: 11, color: colors.textMuted }}>{d.n_movimenti || 0} movimenti</span>
        {(d.da_confermare || 0) > 0 && (
          <span style={{ ...s.badge, background: '#FEF3C7', color: '#92400E', fontSize: 10 }}>
            {d.da_confermare} da confermare
          </span>
        )}
      </div>
    </div>
  )
}

function MovimentoRow({ mov, onDelete, onConferma, onEdit }) {
  const isEntrata = mov.importo > 0
  const isAuto = mov.tipo !== 'manuale'
  return (
    <tr style={{ background: !mov.confermato ? '#FFFBEB' : '#fff' }}>
      <td style={s.td}><span style={{ fontSize: 12 }}>{mov.data}</span></td>
      <td style={s.td}>
        <div style={{ fontSize: 13, fontWeight: 500 }}>{mov.causale}</div>
        {mov.fornitore && <div style={{ fontSize: 11, color: colors.textMuted }}>{mov.fornitore}</div>}
        {mov.riferimento && <div style={{ fontSize: 10, color: colors.primary }}>{mov.riferimento}</div>}
      </td>
      <td style={s.td}>
        <span style={{ ...s.badge, fontSize: 10,
          background: isAuto ? '#E0E7FF' : '#F3F4F6', color: isAuto ? '#3730A3' : '#374151' }}>
          {mov.tipo === 'manuale' ? 'Manuale' : 'Auto'}
        </span>
      </td>
      <td style={s.td}>
        <span style={{ ...s.badge, fontSize: 10 }}>{mov.categoria}</span>
      </td>
      <td style={{ ...s.td, textAlign: 'right', fontWeight: 600, fontFamily: 'monospace',
        color: isEntrata ? colors.success : colors.danger }}>
        {isEntrata ? '+' : ''}{formatEuro(mov.importo)}
      </td>
      <td style={{ ...s.td, textAlign: 'right' }}>
        <div style={{ ...s.flex, gap: 4, justifyContent: 'flex-end' }}>
          {!mov.confermato && (
            <button onClick={() => onConferma(mov.id)} title="Conferma"
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: colors.success, padding: 2 }}>
              <Check size={14} />
            </button>
          )}
          <button onClick={() => onDelete(mov.id)} title="Elimina"
            style={{ border: 'none', background: 'none', cursor: 'pointer', color: colors.textMuted, padding: 2 }}>
            <Trash2 size={14} />
          </button>
        </div>
      </td>
    </tr>
  )
}

function FormNuovoMovimento({ sezione, onSave, onCancel }) {
  const [data, setData] = useState(new Date().toISOString().slice(0, 10))
  const [causale, setCausale] = useState('')
  const [categoria, setCategoria] = useState(CATEGORIE[sezione]?.[0] || 'altro')
  const [importo, setImporto] = useState('')
  const [tipo_flusso, setTipoFlusso] = useState('entrata')
  const [riferimento, setRiferimento] = useState('')
  const [fornitore, setFornitore] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!causale || !importo) return
    setSaving(true)
    const val = parseFloat(importo)
    const imp = tipo_flusso === 'uscita' ? -Math.abs(val) : Math.abs(val)
    try {
      const res = await fetch(`${API}/movimenti`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data, sezione, causale, categoria, importo: imp, riferimento, fornitore, note })
      })
      if (res.ok) onSave()
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const inputStyle = { padding: '8px 12px', border: `1px solid ${colors.border}`, borderRadius: 8,
    fontSize: 13, fontFamily: font, width: '100%', boxSizing: 'border-box' }

  return (
    <div style={{ ...s.card, marginBottom: 16, border: `2px solid ${colors.primary}20` }}>
      <div style={{ ...s.flexBetween, marginBottom: 12 }}>
        <h3 style={{ ...s.h2, margin: 0 }}>Nuovo movimento — {sezione}</h3>
        <button onClick={onCancel} style={{ border: 'none', background: 'none', cursor: 'pointer' }}><X size={18} /></button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
        <div>
          <label style={s.label}>Data</label>
          <input type="date" value={data} onChange={e => setData(e.target.value)} style={inputStyle} />
        </div>
        <div>
          <label style={s.label}>Tipo</label>
          <select value={tipo_flusso} onChange={e => setTipoFlusso(e.target.value)} style={inputStyle}>
            <option value="entrata">+ Entrata</option>
            <option value="uscita">- Uscita</option>
          </select>
        </div>
        <div>
          <label style={s.label}>Importo (€)</label>
          <input type="number" step="0.01" value={importo} onChange={e => setImporto(e.target.value)}
            placeholder="0.00" style={inputStyle} />
        </div>
        <div>
          <label style={s.label}>Categoria</label>
          <select value={categoria} onChange={e => setCategoria(e.target.value)} style={inputStyle}>
            {(CATEGORIE[sezione] || []).map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 10, marginBottom: 12 }}>
        <div>
          <label style={s.label}>Causale</label>
          <input value={causale} onChange={e => setCausale(e.target.value)} placeholder="Descrizione movimento" style={inputStyle} />
        </div>
        <div>
          <label style={s.label}>Fornitore</label>
          <input value={fornitore} onChange={e => setFornitore(e.target.value)} placeholder="(opzionale)" style={inputStyle} />
        </div>
        <div>
          <label style={s.label}>Riferimento</label>
          <input value={riferimento} onChange={e => setRiferimento(e.target.value)} placeholder="N° fattura, ecc." style={inputStyle} />
        </div>
      </div>
      <button onClick={handleSave} disabled={saving || !causale || !importo}
        style={{ ...s.btn, ...s.btnPrimary, opacity: saving ? 0.7 : 1 }}>
        <Plus size={14} /> {saving ? 'Salvataggio...' : 'Inserisci movimento'}
      </button>
    </div>
  )
}

export default function PrimaNota() {
  const [sezione, setSezione] = useState('cassa')
  const [riepilogo, setRiepilogo] = useState({})
  const [movimenti, setMovimenti] = useState([])
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [generando, setGenerando] = useState(false)
  const anno = new Date().getFullYear()

  const loadRiepilogo = useCallback(async () => {
    try {
      const r = await fetch(`${API}/riepilogo-annuale?anno=${anno}`).then(r => r.json())
      setRiepilogo(r)
    } catch {}
  }, [anno])

  const loadMovimenti = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/movimenti?sezione=${sezione}&limit=300`).then(r => r.json())
      setMovimenti(r)
    } catch {}
    setLoading(false)
  }, [sezione])

  useEffect(() => { loadRiepilogo() }, [loadRiepilogo])
  useEffect(() => { loadMovimenti() }, [loadMovimenti])

  const handleGenera = async () => {
    if (!confirm('Generare movimenti automatici da corrispettivi, estratto conto, fatture e F24?')) return
    setGenerando(true)
    try {
      await fetch(`${API}/genera-tutto?anno=${anno}`, { method: 'POST' })
      await loadRiepilogo()
      await loadMovimenti()
    } catch {}
    setGenerando(false)
  }

  const handleConferma = async (id) => {
    await fetch(`${API}/movimenti/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confermato: true })
    })
    loadMovimenti(); loadRiepilogo()
  }

  const handleConfermaTutti = async () => {
    if (!confirm(`Confermare tutti i movimenti automatici in ${sezione}?`)) return
    await fetch(`${API}/conferma-tutti?sezione=${sezione}`, { method: 'POST' })
    loadMovimenti(); loadRiepilogo()
  }

  const handleDelete = async (id) => {
    if (!confirm('Eliminare questo movimento?')) return
    await fetch(`${API}/movimenti/${id}`, { method: 'DELETE' })
    loadMovimenti(); loadRiepilogo()
  }

  const cfg = SEZIONI.find(s => s.id === sezione)
  const nonConfermati = movimenti.filter(m => !m.confermato).length

  return (
    <div>
      <div style={{ ...s.flexBetween, marginBottom: 20 }}>
        <div style={{ ...s.flex, gap: 12 }}>
          <BookOpen size={24} color={colors.primary} />
          <h1 style={{ ...s.h1, margin: 0 }}>Prima Nota</h1>
          <span style={{ fontSize: 13, color: colors.textMuted }}>Anno {anno}</span>
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          <button onClick={handleGenera} disabled={generando}
            style={{ ...s.btn, ...s.btnNeutral, opacity: generando ? 0.7 : 1 }}>
            <RefreshCw size={14} className={generando ? 'spin' : ''} />
            {generando ? 'Generazione...' : 'Genera da documenti'}
          </button>
        </div>
      </div>

      {/* Saldi 3 sezioni */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
        {SEZIONI.map(sez => (
          <div key={sez.id} onClick={() => setSezione(sez.id)} style={{ cursor: 'pointer' }}>
            <SaldoCard sez={sez.id} saldi={riepilogo[sez.id]} />
          </div>
        ))}
      </div>

      {/* Tab sezione attiva */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: `2px solid ${colors.border}` }}>
        {SEZIONI.map(sez => (
          <button key={sez.id} onClick={() => setSezione(sez.id)}
            style={{
              padding: '10px 20px', fontSize: 13, fontWeight: 600, fontFamily: font,
              border: 'none', background: sezione === sez.id ? `${cfg.color}10` : 'transparent',
              color: sezione === sez.id ? cfg.color : colors.textMuted,
              borderBottom: sezione === sez.id ? `3px solid ${cfg.color}` : '3px solid transparent',
              cursor: 'pointer', borderRadius: '6px 6px 0 0',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
            <sez.icon size={15} /> {sez.label}
          </button>
        ))}
      </div>

      {/* Azioni */}
      <div style={{ ...s.flex, gap: 8, marginBottom: 12 }}>
        <button onClick={() => setShowForm(!showForm)} style={{ ...s.btn, ...s.btnPrimary }}>
          <Plus size={14} /> Nuovo movimento
        </button>
        {nonConfermati > 0 && (
          <button onClick={handleConfermaTutti} style={{ ...s.btn, ...s.btnNeutral }}>
            <CheckCheck size={14} /> Conferma tutti ({nonConfermati})
          </button>
        )}
      </div>

      {showForm && (
        <FormNuovoMovimento sezione={sezione}
          onSave={() => { setShowForm(false); loadMovimenti(); loadRiepilogo() }}
          onCancel={() => setShowForm(false)} />
      )}

      {/* Tabella movimenti */}
      <div style={{ ...s.cardNoPad, overflow: 'auto' }}>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Data</th>
              <th style={s.th}>Causale</th>
              <th style={s.th}>Tipo</th>
              <th style={s.th}>Categoria</th>
              <th style={{ ...s.th, textAlign: 'right' }}>Importo</th>
              <th style={{ ...s.th, width: 60 }}></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} style={{ ...s.td, textAlign: 'center', color: colors.textMuted }}>Caricamento...</td></tr>
            ) : movimenti.length === 0 ? (
              <tr><td colSpan={6} style={{ ...s.td, textAlign: 'center', color: colors.textMuted }}>
                Nessun movimento in {cfg.label}. Clicca "Genera da documenti" per importare automaticamente.
              </td></tr>
            ) : movimenti.map(m => (
              <MovimentoRow key={m.id} mov={m} onDelete={handleDelete} onConferma={handleConferma} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
