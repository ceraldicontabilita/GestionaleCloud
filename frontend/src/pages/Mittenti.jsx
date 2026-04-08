import React, { useState, useEffect } from 'react'
import { Mail, Plus, Trash2, Edit2, Check, X, Shield, ShieldOff } from 'lucide-react'
import { s, colors } from '../lib/utils'

const CANALE_COLOR = { pec: '#7c3aed', gmail: '#dc2626' }
const CANALE_BG    = { pec: '#ede9fe', gmail: '#fee2e2' }

const TIPO_OPTIONS = [
  { value: 'fattura_xml',        label: 'Fattura XML (SDI)' },
  { value: 'cedolino',           label: 'Cedolino / Busta paga' },
  { value: 'f24',                label: 'Modello F24' },
  { value: 'verbale',            label: 'Verbale / Bollo auto' },
  { value: 'pagopa',             label: 'PagoPA' },
  { value: 'inps',               label: 'Comunicazione INPS' },
  { value: 'inail',              label: 'Comunicazione INAIL' },
  { value: 'paypal',             label: 'Ricevuta PayPal' },
  { value: 'cartella_esattoriale', label: 'Cartella esattoriale' },
  { value: 'generico',           label: 'Documento generico' },
]

function Badge({ canale }) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
      color: CANALE_COLOR[canale] || colors.textMuted,
      background: CANALE_BG[canale] || '#f3f4f6',
      textTransform: 'uppercase', letterSpacing: '0.5px',
    }}>
      {canale}
    </span>
  )
}

function NuovoMittenteForm({ onSave, onCancel }) {
  const [form, setForm] = useState({
    canale: 'gmail', pattern: '', descrizione: '', tipo_documento: 'generico', attivo: true
  })

  const save = async () => {
    if (!form.pattern.trim()) return
    const res = await fetch('/api/mittenti', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    const data = await res.json()
    if (data.ok) onSave()
    else alert(data.detail || 'Errore')
  }

  return (
    <div style={{ ...s.card, border: `2px solid ${colors.primary}`, marginBottom: 12 }}>
      <div style={{ ...s.flex, gap: 12, flexWrap: 'wrap' }}>
        <select value={form.canale} onChange={e => setForm({ ...form, canale: e.target.value })}
          style={{ ...s.select, width: 120 }}>
          <option value="gmail">Gmail</option>
          <option value="pec">PEC</option>
        </select>
        <input
          placeholder="Pattern mittente (es. @pec.fatturapa.it)"
          value={form.pattern}
          onChange={e => setForm({ ...form, pattern: e.target.value })}
          style={{ ...s.input, flex: 1, minWidth: 200 }}
        />
        <input
          placeholder="Descrizione"
          value={form.descrizione}
          onChange={e => setForm({ ...form, descrizione: e.target.value })}
          style={{ ...s.input, flex: 1, minWidth: 160 }}
        />
        <select value={form.tipo_documento} onChange={e => setForm({ ...form, tipo_documento: e.target.value })}
          style={{ ...s.select, minWidth: 170 }}>
          {TIPO_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <button onClick={save} style={{ ...s.btn, ...s.btnPrimary }}>
          <Check size={15} /> Salva
        </button>
        <button onClick={onCancel} style={{ ...s.btn, ...s.btnOutline }}>
          <X size={15} />
        </button>
      </div>
    </div>
  )
}

function MittenteRow({ item, tipoLabels, onToggle, onDelete, onEdit }) {
  const isBuiltin = item.builtin

  return (
    <tr
      onMouseEnter={e => e.currentTarget.style.background = '#f8f9fb'}
      onMouseLeave={e => e.currentTarget.style.background = ''}
      style={{ opacity: item.attivo ? 1 : 0.5 }}
    >
      <td style={s.td}><Badge canale={item.canale} /></td>
      <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 13, fontWeight: 600, color: colors.primary }}>
        {item.pattern}
      </td>
      <td style={{ ...s.td, fontSize: 13, color: colors.textMuted }}>{item.descrizione || '—'}</td>
      <td style={s.td}>
        <span style={{
          fontSize: 12, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
          color: colors.primary, background: '#dbeafe',
        }}>
          {tipoLabels?.[item.tipo_documento] || item.tipo_documento}
        </span>
      </td>
      <td style={{ ...s.td, textAlign: 'center' }}>
        {isBuiltin && (
          <span style={{ fontSize: 11, color: colors.textMuted, fontStyle: 'italic' }}>sistema</span>
        )}
      </td>
      <td style={{ ...s.td, textAlign: 'right' }}>
        <div style={{ ...s.flex, gap: 6, justifyContent: 'flex-end' }}>
          <button
            onClick={() => onToggle(item)}
            title={item.attivo ? 'Disattiva' : 'Attiva'}
            style={{ ...s.btn, ...s.btnSmall, ...(item.attivo ? s.btnOutline : { background: colors.successBg, color: colors.success, border: 'none' }) }}
          >
            {item.attivo ? <ShieldOff size={13} /> : <Shield size={13} />}
            {item.attivo ? 'Disattiva' : 'Attiva'}
          </button>
          {!isBuiltin && (
            <button
              onClick={() => onDelete(item)}
              style={{ ...s.btn, ...s.btnSmall, ...s.btnDanger }}
              title="Elimina"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

export default function Mittenti() {
  const [items, setItems] = useState([])
  const [tipoLabels, setTipoLabels] = useState({})
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [filtroCanale, setFiltroCanale] = useState('')

  const load = () => {
    setLoading(true)
    const q = filtroCanale ? `?canale=${filtroCanale}` : ''
    fetch(`/api/mittenti${q}`)
      .then(r => r.json())
      .then(d => {
        setItems(d.items || [])
        setTipoLabels(d.tipo_labels || {})
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(load, [filtroCanale])

  const toggle = async (item) => {
    await fetch(`/api/mittenti/${item._id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attivo: !item.attivo }),
    })
    load()
  }

  const del = async (item) => {
    if (!confirm(`Eliminare il mittente "${item.pattern}"?`)) return
    await fetch(`/api/mittenti/${item._id}`, { method: 'DELETE' })
    load()
  }

  const attivi = items.filter(i => i.attivo).length
  const pecItems = items.filter(i => i.canale === 'pec')
  const gmailItems = items.filter(i => i.canale === 'gmail')

  return (
    <div>
      <div style={{ ...s.flexBetween, marginBottom: 20 }}>
        <div style={{ ...s.flex, gap: 12 }}>
          <Mail size={24} color={colors.primary} />
          <h1 style={s.h1}>Mittenti Attendibili</h1>
          <span style={{ fontSize: 13, color: colors.textMuted }}>
            {attivi} attivi su {items.length}
          </span>
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          <select value={filtroCanale} onChange={e => setFiltroCanale(e.target.value)}
            style={{ ...s.select, minWidth: 120 }}>
            <option value="">Tutti</option>
            <option value="pec">Solo PEC</option>
            <option value="gmail">Solo Gmail</option>
          </select>
          <button onClick={() => setShowForm(!showForm)}
            style={{ ...s.btn, ...s.btnPrimary }}>
            <Plus size={15} /> Aggiungi mittente
          </button>
        </div>
      </div>

      {/* Spiegazione */}
      <div style={{ ...s.card, padding: '12px 16px', marginBottom: 16, background: '#f0f6ff', border: '1px solid #bfdbfe' }}>
        <div style={{ fontSize: 13, color: '#1e40af', lineHeight: 1.6 }}>
          <strong>Come funziona:</strong> quando il sistema scarica email dalla PEC o da Gmail,
          accetta solo messaggi da mittenti presenti in questa lista e attivi.
          I mittenti di <em>sistema</em> non si possono eliminare, solo disattivare.
          I corrispettivi XML arrivano <strong>sempre e solo via import manuale</strong> — non da email.
        </div>
      </div>

      {showForm && (
        <NuovoMittenteForm
          onSave={() => { setShowForm(false); load() }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: colors.textMuted }}>Caricamento...</div>
      ) : (
        <>
          {/* PEC */}
          {(!filtroCanale || filtroCanale === 'pec') && (
            <div style={{ ...s.card, padding: 0, overflow: 'hidden', marginBottom: 16 }}>
              <div style={{ padding: '10px 16px', borderBottom: `1px solid ${colors.border}`,
                fontWeight: 700, fontSize: 13, color: CANALE_COLOR.pec, background: CANALE_BG.pec }}>
                PEC — fatturazioneceraldi@pec.it ({pecItems.length} mittenti)
              </div>
              <table style={s.table}>
                <thead><tr>
                  <th style={s.th}>Canale</th>
                  <th style={s.th}>Pattern mittente</th>
                  <th style={s.th}>Descrizione</th>
                  <th style={s.th}>Tipo documento</th>
                  <th style={s.th}></th>
                  <th style={{ ...s.th, textAlign: 'right' }}>Azioni</th>
                </tr></thead>
                <tbody>
                  {pecItems.map(item => (
                    <MittenteRow key={item._id} item={item} tipoLabels={tipoLabels}
                      onToggle={toggle} onDelete={del} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Gmail */}
          {(!filtroCanale || filtroCanale === 'gmail') && (
            <div style={{ ...s.card, padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '10px 16px', borderBottom: `1px solid ${colors.border}`,
                fontWeight: 700, fontSize: 13, color: CANALE_COLOR.gmail, background: CANALE_BG.gmail }}>
                Gmail — ceraldigroupsrl@gmail.com ({gmailItems.length} mittenti)
              </div>
              <table style={s.table}>
                <thead><tr>
                  <th style={s.th}>Canale</th>
                  <th style={s.th}>Pattern mittente</th>
                  <th style={s.th}>Descrizione</th>
                  <th style={s.th}>Tipo documento</th>
                  <th style={s.th}></th>
                  <th style={{ ...s.th, textAlign: 'right' }}>Azioni</th>
                </tr></thead>
                <tbody>
                  {gmailItems.map(item => (
                    <MittenteRow key={item._id} item={item} tipoLabels={tipoLabels}
                      onToggle={toggle} onDelete={del} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
