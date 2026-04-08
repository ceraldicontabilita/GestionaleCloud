import React, { useState, useRef, useCallback } from 'react'
import {
  Upload, FileText, CheckCircle, AlertCircle, X,
  FileCheck, Receipt, Landmark, CreditCard, Car, Banknote, Inbox
} from 'lucide-react'
import { s, colors, formatEuro } from '../lib/utils'

// Icona per tipo documento
const TIPO_CONFIG = {
  fattura_xml:      { icon: FileText,  color: '#2563eb', bg: '#dbeafe', label: 'Fattura XML (SDI)',       accept: '.xml,.p7m,.zip' },
  corrispettivo_xml:{ icon: CreditCard, color: '#7c3aed', bg: '#ede9fe', label: 'Corrispettivo RT (XML)', accept: '.xml' },
  cedolino:         { icon: Receipt,   color: '#0891b2', bg: '#cffafe', label: 'Cedolino Zucchetti',      accept: '.pdf' },
  estratto_conto:   { icon: Landmark,  color: '#059669', bg: '#d1fae5', label: 'Estratto Conto BPM',      accept: '.pdf' },
  distinta:         { icon: Banknote,  color: '#d97706', bg: '#fef3c7', label: 'Distinta Pagamento BPM',  accept: '.pdf' },
  f24:              { icon: FileCheck, color: '#dc2626', bg: '#fee2e2', label: 'Modello F24',              accept: '.pdf' },
  verbale:          { icon: Car,       color: '#9f1239', bg: '#ffe4e6', label: 'Verbale / Bollo auto',     accept: '.pdf' },
  sconosciuto:      { icon: AlertCircle, color: colors.textMuted, bg: '#f3f4f6', label: 'Non riconosciuto', accept: '' },
}

function StatusBadge({ result }) {
  if (!result) return null
  if (result.errore) return (
    <span style={{ color: colors.danger, fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
      <AlertCircle size={12} /> {result.errore}
    </span>
  )
  if (result.ok === false) return (
    <span style={{ color: colors.danger, fontSize: 12 }}>Errore importazione</span>
  )
  const ins = result.inserite ?? 0
  const dup = result.duplicate ?? 0
  return (
    <span style={{ color: colors.success, fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
      <CheckCircle size={12} />
      {ins > 0 ? `${ins} importati` : 'Già presente'}
      {dup > 0 && <span style={{ color: colors.textMuted }}> · {dup} dup.</span>}
      {result.totale != null && <span style={{ color: colors.textMuted }}> · {formatEuro(result.totale)}</span>}
      {result.n_tributi != null && <span style={{ color: colors.textMuted }}> · {result.n_tributi} tributi</span>}
      {result.n_bonifici != null && <span style={{ color: colors.textMuted }}> · {result.n_bonifici} bonifici</span>}
    </span>
  )
}

function FileRow({ item, onRemove }) {
  const cfg = TIPO_CONFIG[item.tipo] || TIPO_CONFIG.sconosciuto
  const Icon = cfg.icon

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '10px 14px',
      borderBottom: `1px solid ${colors.border}`,
      background: item.result?.ok === false || item.result?.errore ? '#fff8f8' : '#fff',
    }}>
      {/* Icona tipo */}
      <div style={{
        width: 36, height: 36, borderRadius: 8, flexShrink: 0,
        background: cfg.bg, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={18} color={cfg.color} />
      </div>

      {/* Nome file + tipo */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: colors.text,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.filename}
        </div>
        <div style={{ fontSize: 11, color: cfg.color, fontWeight: 600, marginTop: 2 }}>
          {cfg.label}
        </div>
      </div>

      {/* Stato */}
      <div style={{ flexShrink: 0, minWidth: 160, textAlign: 'right' }}>
        {item.loading
          ? <span style={{ fontSize: 12, color: colors.textMuted }}>Importazione...</span>
          : item.result
          ? <StatusBadge result={item.result} />
          : <span style={{ fontSize: 12, color: colors.textMuted }}>In attesa</span>
        }
      </div>

      {/* Rimuovi */}
      {!item.loading && (
        <button onClick={() => onRemove(item.id)}
          style={{ border: 'none', background: 'none', cursor: 'pointer', color: colors.textMuted, padding: 4, flexShrink: 0 }}>
          <X size={14} />
        </button>
      )}
    </div>
  )
}

export default function ImportaDocumenti() {
  const [files, setFiles] = useState([])
  const [dragging, setDragging] = useState(false)
  const [globalLoading, setGlobalLoading] = useState(false)
  const fileRef = useRef()
  let idCounter = useRef(0)

  const addFiles = useCallback(async (rawFiles) => {
    const newItems = Array.from(rawFiles).map(f => ({
      id: ++idCounter.current,
      filename: f.name,
      file: f,
      tipo: 'detecting',
      loading: false,
      result: null,
    }))

    // Rilevamento automatico tipo (detect endpoint — senza importare)
    const withTypes = await Promise.all(newItems.map(async item => {
      try {
        const fd = new FormData()
        fd.append('file', item.file)
        const res = await fetch('/api/import/detect', { method: 'POST', body: fd })
        const data = await res.json()
        return { ...item, tipo: data.tipo }
      } catch {
        return { ...item, tipo: 'sconosciuto' }
      }
    }))

    setFiles(prev => [...prev, ...withTypes])
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files)
  }, [addFiles])

  const handleSelect = (e) => {
    if (e.target.files.length) addFiles(e.target.files)
    e.target.value = ''
  }

  const removeFile = (id) => setFiles(prev => prev.filter(f => f.id !== id))

  const importAll = async () => {
    const pending = files.filter(f => !f.result && f.tipo !== 'sconosciuto')
    if (!pending.length) return

    setGlobalLoading(true)

    for (const item of pending) {
      setFiles(prev => prev.map(f => f.id === item.id ? { ...f, loading: true } : f))
      try {
        const fd = new FormData()
        fd.append('file', item.file)
        const res = await fetch('/api/import/upload', { method: 'POST', body: fd })
        const data = await res.json()
        setFiles(prev => prev.map(f => f.id === item.id
          ? { ...f, loading: false, result: data }
          : f))
      } catch (err) {
        setFiles(prev => prev.map(f => f.id === item.id
          ? { ...f, loading: false, result: { ok: false, errore: err.message } }
          : f))
      }
    }

    setGlobalLoading(false)
  }

  const clearAll = () => setFiles([])

  const pending = files.filter(f => !f.result && f.tipo !== 'sconosciuto')
  const done = files.filter(f => f.result)
  const errors = files.filter(f => f.tipo === 'sconosciuto' || f.result?.ok === false || f.result?.errore)

  return (
    <div>
      {/* Header */}
      <div style={{ ...s.flexBetween, marginBottom: 20 }}>
        <div style={{ ...s.flex, gap: 12 }}>
          <Inbox size={24} color={colors.primary} />
          <h1 style={s.h1}>Importa Documenti</h1>
          {files.length > 0 && (
            <span style={{ fontSize: 13, color: colors.textMuted }}>
              {files.length} file · {done.length} importati
              {errors.length > 0 && <span style={{ color: colors.danger }}> · {errors.length} errori</span>}
            </span>
          )}
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          {files.length > 0 && (
            <button onClick={clearAll} style={{ ...s.btn, ...s.btnOutline }}>
              Svuota lista
            </button>
          )}
          {pending.length > 0 && (
            <button onClick={importAll} disabled={globalLoading}
              style={{ ...s.btn, ...s.btnPrimary, opacity: globalLoading ? 0.7 : 1 }}>
              <Upload size={15} />
              {globalLoading ? 'Importazione...' : `Importa tutti (${pending.length})`}
            </button>
          )}
        </div>
      </div>

      {/* Drop zone */}
      <div
        onClick={() => fileRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        style={{
          border: `2px dashed ${dragging ? colors.primary : colors.border}`,
          borderRadius: 12,
          padding: '40px 24px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragging ? '#f0f6ff' : colors.card,
          transition: 'all .2s',
          marginBottom: 20,
        }}
      >
        <Upload size={36} color={dragging ? colors.primary : colors.border} style={{ marginBottom: 12 }} />
        <div style={{ fontSize: 16, fontWeight: 600, color: dragging ? colors.primary : colors.text }}>
          Trascina qui i documenti oppure clicca per selezionarli
        </div>
        <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 8 }}>
          Il sistema riconosce automaticamente il tipo — puoi caricare file misti
        </div>
        <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 6 }}>
          Accettati: <code>.xml</code> · <code>.p7m</code> · <code>.zip</code> · <code>.pdf</code>
        </div>
        <input ref={fileRef} type="file" multiple
          accept=".xml,.p7m,.zip,.pdf" onChange={handleSelect}
          style={{ display: 'none' }} />
      </div>

      {/* Lista file */}
      {files.length > 0 && (
        <div style={{ ...s.card, padding: 0, overflow: 'hidden' }}>
          {files.map(item => (
            <FileRow key={item.id} item={item} onRemove={removeFile} />
          ))}
        </div>
      )}

      {/* Riepilogo tipi riconoscibili */}
      {files.length === 0 && (
        <div style={{ ...s.card }}>
          <h2 style={{ ...s.h2, marginBottom: 16 }}>Documenti riconosciuti automaticamente</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
            {[
              {
                tipo: 'fattura_xml',
                esempi: ['IT01234567890_00001.xml', 'fattura.p7m', 'lotto_fatture.zip'],
                dettagli: 'FatturaPA, lotti SDI, firma P7M, ZIP con XML interno',
                campi: 'Fornitore, P.IVA, numero, data, imponibile, IVA, totale, linee dettaglio',
              },
              {
                tipo: 'corrispettivo_xml',
                esempi: ['corrispettivi_20240315.xml'],
                dettagli: 'XML registratore telematico (DatiCorrispettivi)',
                campi: 'Data, matricola RT, numero chiusura, totali per aliquota IVA',
              },
              {
                tipo: 'cedolino',
                esempi: ['cedolini_marzo_2026.pdf'],
                dettagli: 'PDF multi-dipendente Zucchetti (Aut. 301 + Aut. 299)',
                campi: 'Codice fiscale, nome, mese/anno, lordo, netto, IRPEF, IBAN',
              },
              {
                tipo: 'estratto_conto',
                esempi: ['estratto_conto_bpm_gen2026.pdf'],
                dettagli: 'PDF estratto conto mensile Banco BPM',
                campi: 'Movimenti con data, valuta, descrizione, dare/avere, categoria auto',
              },
              {
                tipo: 'distinta',
                esempi: ['distinta_stipendi_marzo.pdf'],
                dettagli: 'PDF distinta pagamento bonifici Banco BPM',
                campi: 'Lista beneficiari, IBAN, importo, causale + riconciliazione dipendenti',
              },
              {
                tipo: 'f24',
                esempi: ['f24_marzo_2026.pdf'],
                dettagli: 'PDF modello F24 (commercialista o AdE)',
                campi: 'Data versamento, codici tributo IRPEF/IVA/INPS/IRAP, totale',
              },
              {
                tipo: 'verbale',
                esempi: ['verbale_cds_BA782XR.pdf', 'bollo_auto_2024.pdf'],
                dettagli: 'PDF verbali CdS, avvisi bollo auto, notifiche PagoPA',
                campi: 'Numero verbale, targa, importo, data, ente, IUV PagoPA',
              },
            ].map(({ tipo, esempi, dettagli, campi }) => {
              const cfg = TIPO_CONFIG[tipo]
              const Icon = cfg.icon
              return (
                <div key={tipo} style={{
                  border: `1px solid ${colors.border}`, borderRadius: 8, padding: 16,
                  borderLeft: `4px solid ${cfg.color}`,
                }}>
                  <div style={{ ...s.flex, gap: 8, marginBottom: 8 }}>
                    <div style={{
                      width: 30, height: 30, borderRadius: 6, flexShrink: 0,
                      background: cfg.bg, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Icon size={16} color={cfg.color} />
                    </div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: cfg.color }}>{cfg.label}</div>
                  </div>
                  <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 6 }}>{dettagli}</div>
                  <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 6 }}>
                    <strong>Campi estratti:</strong> {campi}
                  </div>
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: colors.primary, background: '#f8f9fb', padding: '4px 8px', borderRadius: 4 }}>
                    {esempi.join(' · ')}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
