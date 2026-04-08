import React, { useState, useEffect, useCallback } from 'react'
import {
  Upload, Search, FileText, CheckCircle, AlertTriangle,
  ChevronDown, ChevronUp, Download, RefreshCw, Calendar,
  TrendingUp, Shield, Info, X, Printer
} from 'lucide-react'
import { s, colors, shadow, formatEuro, font } from '../lib/utils'

const API = '/api/f24'

/* ── Label codici tributo ─────────────────────────────────── */
const CODICI_LABEL = {
  '1001': 'IRPEF rit. dipendenti', '1701': 'Add. regionale IRPEF', '1704': 'Add. comunale IRPEF',
  '1713': 'Add. comunale IRPEF (saldo)', '1627': 'IRES 2° acconto', '1631': 'IRES/IRPEF saldo (comp.)',
  '1668': 'Interessi rateazione', '2003': 'IVA mensile',
  'CXX': 'INPS contributi sede', 'DM10': 'INPS DM10',
  '3802': 'IRAP', '3796': 'IRAP (credito)', '3847': 'IMU acconto', '3848': 'IMU saldo',
  '3797': 'IMU (credito)', 'INAIL': 'INAIL premi',
}

const SEZIONI_COLOR = {
  ERARIO:  [colors.primaryText,  colors.primaryBg],
  INPS:    [colors.successText,  colors.successBg],
  REGIONI: [colors.infoText,     colors.infoBg],
  IMU:     [colors.warningText,  colors.warningBg],
  INAIL:   [colors.dangerText,   colors.dangerBg],
}

/* ── Componenti ───────────────────────────────────────────── */
function Badge({ text, sezione }) {
  const [color, bg] = SEZIONI_COLOR[sezione] || [colors.textMuted, colors.borderLight]
  return (
    <span style={{ ...s.badge(color, bg), fontSize: 10 }}>{text}</span>
  )
}

function StatCard({ label, value, sub, icon: Icon, color: c, bg }) {
  return (
    <div style={{ ...s.metricCard, display: 'flex', alignItems: 'center', gap: 14 }}>
      <div style={{ width: 44, height: 44, borderRadius: 12, background: bg || colors.primaryBg,
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon size={20} color={c || colors.primary} />
      </div>
      <div>
        <div style={{ ...s.label, marginBottom: 2 }}>{label}</div>
        <div style={{ fontSize: 20, fontWeight: 700, color: colors.text, lineHeight: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: colors.textLight, marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  )
}

/* ── Sezione Upload ───────────────────────────────────────── */
function UploadZone({ onUploaded }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [risultati, setRisultati] = useState(null)

  const doUpload = async (files) => {
    if (!files.length) return
    setUploading(true)
    setRisultati(null)
    const fd = new FormData()
    Array.from(files).forEach(f => fd.append('files', f))
    try {
      const res = await fetch(`${API}/upload-pdf`, { method: 'POST', body: fd })
      const data = await res.json()
      setRisultati(data.risultati || [])
      onUploaded()
    } catch (e) {
      setRisultati([{ ok: false, errore: e.message }])
    }
    setUploading(false)
  }

  return (
    <div style={s.card}>
      <div style={{ ...s.flexBetween, marginBottom: 16 }}>
        <h2 style={{ ...s.h2, margin: 0 }}>Importa F24 da PDF</h2>
        <span style={{ fontSize: 12, color: colors.textLight }}>
          Formato Entratel — Azienda 000026
        </span>
      </div>

      <label
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); doUpload(e.dataTransfer.files) }}
        style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          padding: '32px 24px', borderRadius: 12, cursor: 'pointer',
          border: `2px dashed ${dragging ? colors.primary : colors.border}`,
          background: dragging ? colors.primaryBg : colors.bg,
          transition: 'all .15s', marginBottom: risultati ? 16 : 0,
        }}
      >
        <Upload size={28} color={dragging ? colors.primary : colors.textLight} style={{ marginBottom: 10 }} />
        <div style={{ fontSize: 14, fontWeight: 600, color: dragging ? colors.primary : colors.textMuted, marginBottom: 4 }}>
          {uploading ? 'Caricamento in corso...' : 'Trascina qui i PDF oppure clicca'}
        </div>
        <div style={{ fontSize: 12, color: colors.textLight }}>
          Supporta più file contemporaneamente (F24 con pagine multiple incluse)
        </div>
        <input type="file" accept=".pdf" multiple onChange={e => doUpload(e.target.files)}
          style={{ display: 'none' }} disabled={uploading} />
      </label>

      {risultati && (
        <div style={{ marginTop: 12 }}>
          {risultati.map((r, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 12px', borderRadius: 8, marginBottom: 6,
              background: r.ok ? colors.successBg : colors.dangerBg,
            }}>
              {r.ok
                ? <CheckCircle size={14} color={colors.success} />
                : <AlertTriangle size={14} color={colors.danger} />}
              <span style={{ fontSize: 12, fontWeight: 600,
                color: r.ok ? colors.successText : colors.dangerText }}>
                {r.file} — {r.ok
                  ? `${r.azione} (scadenza ${r.scadenza}, €${r.saldo_finale?.toFixed(2)})`
                  : r.errore}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Ricerca Tributo (per Avvisi ADR/ADE) ─────────────────── */
function RicercaTributo() {
  const [codice, setCodice] = useState('')
  const [anno, setAnno] = useState('')
  const [mese, setMese] = useState('')
  const [risultato, setRisultato] = useState(null)
  const [loading, setLoading] = useState(false)

  const cerca = async () => {
    if (!codice) return
    setLoading(true)
    const params = new URLSearchParams({ codice })
    if (anno) params.append('anno_rif', anno)
    if (mese) params.append('mese_rif', mese.padStart(4, '0'))
    const res = await fetch(`${API}/ricerca-tributo?${params}`)
    const data = await res.json()
    setRisultato(data)
    setLoading(false)
  }

  return (
    <div style={s.card}>
      <div style={{ ...s.flex, ...s.gap8, marginBottom: 16 }}>
        <Shield size={18} color={colors.primary} />
        <h2 style={{ ...s.h2, margin: 0 }}>Ricerca tributo — Avvisi bonari / Cartelle</h2>
      </div>
      <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 16, lineHeight: 1.6 }}>
        Inserisci il codice tributo dall'avviso ADE/ADR per verificare se è già stato pagato con F24
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px 100px auto', gap: 10, alignItems: 'end' }}>
        <div>
          <div style={s.label}>Codice tributo</div>
          <input
            value={codice} onChange={e => setCodice(e.target.value.toUpperCase())}
            placeholder="es. 1001, 1704, 3802..."
            style={{ ...s.input }}
            onKeyDown={e => e.key === 'Enter' && cerca()}
          />
        </div>
        <div>
          <div style={s.label}>Anno rif.</div>
          <input value={anno} onChange={e => setAnno(e.target.value)}
            placeholder="2024" style={{ ...s.input }} />
        </div>
        <div>
          <div style={s.label}>Mese (mmaa)</div>
          <input value={mese} onChange={e => setMese(e.target.value)}
            placeholder="0102" style={{ ...s.input }} />
        </div>
        <button onClick={cerca} disabled={loading || !codice}
          style={{ ...s.btn, ...s.btnPrimary, height: 42, opacity: loading ? 0.7 : 1 }}>
          <Search size={15} />
          Cerca
        </button>
      </div>

      {risultato && (
        <div style={{ marginTop: 20 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px',
            borderRadius: 12,
            background: risultato.trovati > 0 ? colors.successBg : colors.dangerBg,
            border: `1.5px solid ${risultato.trovati > 0 ? colors.success : colors.danger}30`,
            marginBottom: 14,
          }}>
            {risultato.trovati > 0
              ? <CheckCircle size={22} color={colors.success} />
              : <AlertTriangle size={22} color={colors.danger} />}
            <div>
              <div style={{ fontSize: 15, fontWeight: 700,
                color: risultato.trovati > 0 ? colors.successText : colors.dangerText }}>
                {risultato.esito}
              </div>
              <div style={{ fontSize: 12, color: risultato.trovati > 0 ? colors.success : colors.danger, marginTop: 2 }}>
                Codice {risultato.codice}
                {risultato.anno_rif && ` · anno ${risultato.anno_rif}`}
                {risultato.trovati > 0 && ` · ${risultato.trovati} F24 trovati`}
              </div>
            </div>
          </div>

          {risultato.pagamenti?.map((pag, i) => (
            <div key={i} style={{
              padding: '14px 16px', borderRadius: 12, marginBottom: 8,
              border: `1px solid ${colors.border}`, background: colors.card,
            }}>
              <div style={{ ...s.flexBetween, marginBottom: 10 }}>
                <div>
                  <span style={{ fontWeight: 700, fontSize: 14, color: colors.text }}>
                    Scadenza: {pag.scadenza}
                  </span>
                  {pag.data_pagamento && (
                    <span style={{ fontSize: 12, color: colors.textMuted, marginLeft: 12 }}>
                      Pagato il: <strong>{pag.data_pagamento}</strong>
                    </span>
                  )}
                </div>
                <div style={{ ...s.flex, ...s.gap8 }}>
                  <span style={{ fontWeight: 700, fontSize: 16, color: colors.primary }}>
                    {formatEuro(pag.saldo_finale)}
                  </span>
                  {pag._id && (
                    <a href={`${API}/${pag._id}/pdf`} target="_blank" rel="noreferrer"
                      style={{ ...s.btn, ...s.btnGhost, ...s.btnXSmall, textDecoration: 'none' }}>
                      <Download size={12} /> PDF
                    </a>
                  )}
                </div>
              </div>
              {/* Righi trovati */}
              {pag.righi_trovati?.map((r, j) => (
                <div key={j} style={{
                  display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
                  padding: '6px 10px', borderRadius: 8, background: colors.bg, marginBottom: 4,
                }}>
                  <Badge text={r.sezione} sezione={r.sezione} />
                  <span style={{ fontWeight: 600, color: colors.text }}>{r.codice_tributo}</span>
                  <span style={{ color: colors.textMuted }}>—</span>
                  <span style={{ color: colors.text }}>{r.descrizione}</span>
                  <span style={{ marginLeft: 'auto', fontWeight: 700, color: colors.successText }}>
                    {formatEuro(r.debito)}
                  </span>
                  {r.credito > 0 && (
                    <span style={{ fontWeight: 700, color: colors.infoText }}>
                      comp. {formatEuro(r.credito)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Riga F24 con espandibile ─────────────────────────────── */
function RigaF24({ doc, onStampaPdf }) {
  const [espanso, setEspanso] = useState(false)
  const hasRavvedimento = doc.note_ravvedimento

  return (
    <>
      <tr
        onClick={() => setEspanso(e => !e)}
        style={{ ...s.trHover, background: espanso ? colors.primaryBg : 'transparent' }}
        onMouseEnter={e => !espanso && (e.currentTarget.style.background = colors.bg)}
        onMouseLeave={e => !espanso && (e.currentTarget.style.background = 'transparent')}
      >
        <td style={{ ...s.td, width: 32 }}>
          {espanso ? <ChevronUp size={14} color={colors.primary} /> : <ChevronDown size={14} color={colors.textLight} />}
        </td>
        <td style={s.td}>
          <div style={{ fontWeight: 600, color: colors.text }}>{doc.scadenza}</div>
          {doc.data_pagamento && doc.data_pagamento !== doc.scadenza && (
            <div style={{ fontSize: 11, color: colors.textLight }}>pag. {doc.data_pagamento}</div>
          )}
        </td>
        <td style={s.td}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {[...new Set((doc.tributi_flat || []).map(t => t.sezione))].map(sez => (
              <Badge key={sez} text={sez} sezione={sez} />
            ))}
          </div>
        </td>
        <td style={{ ...s.td }}>
          <div style={{ fontSize: 11, color: colors.textMuted }}>
            {doc.banca?.split(' ')[0]}
          </div>
        </td>
        <td style={{ ...s.td, textAlign: 'right' }}>
          {hasRavvedimento && (
            <span title="Contiene codici ravvedimento" style={{ marginRight: 8 }}>
              <AlertTriangle size={13} color={colors.warning} />
            </span>
          )}
          <span style={{ fontWeight: 700, fontSize: 15, color: colors.primary }}>
            {formatEuro(doc.saldo_finale)}
          </span>
        </td>
        <td style={{ ...s.td, width: 120 }}>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <a href={`${API}/${doc._id}/pdf`} target="_blank" rel="noreferrer"
              onClick={e => e.stopPropagation()}
              style={{ ...s.btn, ...s.btnGhost, ...s.btnXSmall, textDecoration: 'none' }}>
              <Printer size={12} />
            </a>
          </div>
        </td>
      </tr>

      {espanso && (
        <tr>
          <td colSpan={6} style={{ padding: '0 16px 16px 48px', background: colors.primaryBg }}>
            <div style={{ borderTop: `1px solid ${colors.border}`, paddingTop: 12, marginBottom: 8 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 }}>
                {(doc.tributi_flat || []).map((t, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
                    padding: '7px 12px', borderRadius: 8,
                    background: colors.card, border: `1px solid ${colors.border}`,
                  }}>
                    <Badge text={t.sezione} sezione={t.sezione} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 700, color: colors.text, fontSize: 11 }}>
                        {t.codice_tributo}
                        {t.mese_rif && <span style={{ fontWeight: 400, color: colors.textLight }}> mese {t.mese_rif}</span>}
                        {t.anno_rif && <span style={{ fontWeight: 400, color: colors.textLight }}> / {t.anno_rif}</span>}
                      </div>
                      <div style={{ color: colors.textMuted, fontSize: 10, lineHeight: 1.3 }}>
                        {CODICI_LABEL[t.codice_tributo] || t.descrizione}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      {t.debito > 0 && (
                        <div style={{ fontWeight: 700, color: colors.dangerText, fontSize: 12 }}>
                          -{formatEuro(t.debito)}
                        </div>
                      )}
                      {t.credito > 0 && (
                        <div style={{ fontWeight: 700, color: colors.successText, fontSize: 12 }}>
                          +{formatEuro(t.credito)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

/* ═══════════════════════════════════════════════════════════
   PAGINA PRINCIPALE F24
   ═══════════════════════════════════════════════════════════ */
export default function F24Page() {
  const [anno, setAnno] = useState(new Date().getFullYear())
  const [lista, setLista] = useState([])
  const [riepilogo, setRiepilogo] = useState(null)
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState('lista') // 'lista' | 'upload' | 'avvisi'

  const carica = useCallback(async () => {
    setLoading(true)
    const [l, r] = await Promise.all([
      fetch(`${API}?anno=${anno}`).then(r => r.json()),
      fetch(`${API}/riepilogo/${anno}`).then(r => r.json()),
    ])
    setLista(Array.isArray(l) ? l : [])
    setRiepilogo(r)
    setLoading(false)
  }, [anno])

  useEffect(() => { carica() }, [carica])

  const MESI_LABEL = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic']

  // Raggruppa per mese
  const listaPagina1 = lista.filter(d => (d.pagina || 1) === 1)

  return (
    <div style={{ ...s.page }}>
      <div style={s.container}>

        {/* ── Header ─────────────────────────────────────── */}
        <div style={{ ...s.flexBetween, marginBottom: 24 }}>
          <div>
            <h1 style={s.h1}>F24 Contributi</h1>
            <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>
              CERALDI GROUP S.R.L. · CF 04523831214
            </div>
          </div>
          <div style={{ ...s.flex, ...s.gap8 }}>
            {/* Anno */}
            <div style={{ ...s.flex, ...s.gap4, background: colors.card, borderRadius: 10, padding: '4px 6px', border: `1px solid ${colors.border}` }}>
              <button onClick={() => setAnno(a => a - 1)} style={{ ...s.btn, ...s.btnXSmall, ...s.btnNeutral, padding: '4px 8px' }}>‹</button>
              <span style={{ fontSize: 15, fontWeight: 700, minWidth: 44, textAlign: 'center' }}>{anno}</span>
              <button onClick={() => setAnno(a => a + 1)} style={{ ...s.btn, ...s.btnXSmall, ...s.btnNeutral, padding: '4px 8px' }}>›</button>
            </div>
            <button onClick={carica} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
              <RefreshCw size={14} /> Aggiorna
            </button>
          </div>
        </div>

        {/* ── KPI ────────────────────────────────────────── */}
        {riepilogo && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 24 }}>
            <StatCard label="Totale versato" value={formatEuro(riepilogo.totale_versato)}
              sub={`${anno}`} icon={TrendingUp} color={colors.primary} bg={colors.primaryBg} />
            <StatCard label="F24 pagati" value={riepilogo.n_f24}
              sub="documenti" icon={CheckCircle} color={colors.success} bg={colors.successBg} />
            <StatCard label="Media mensile" value={formatEuro((riepilogo.totale_versato || 0) / Math.max(riepilogo.n_f24, 1))}
              icon={Calendar} color={colors.info} bg={colors.infoBg} />
          </div>
        )}

        {/* ── Tab bar ────────────────────────────────────── */}
        <div style={{ ...s.flex, ...s.gap4, marginBottom: 20,
          background: colors.card, borderRadius: 14, padding: 6,
          boxShadow: shadow.xs, border: `1px solid ${colors.border}`, width: 'fit-content' }}>
          {[
            { id: 'lista', label: `Lista F24 (${listaPagina1.length})` },
            { id: 'upload', label: 'Importa PDF' },
            { id: 'avvisi', label: '🔍 Ricerca avvisi' },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              fontFamily: font, fontSize: 13, fontWeight: 600,
              padding: '8px 18px', borderRadius: 10, border: 'none', cursor: 'pointer',
              background: tab === t.id
                ? `linear-gradient(135deg, ${colors.primary} 0%, ${colors.primaryLight} 100%)`
                : 'transparent',
              color: tab === t.id ? '#fff' : colors.textMuted,
              boxShadow: tab === t.id ? shadow.btn : 'none',
              transition: 'all .15s',
            }}>{t.label}</button>
          ))}
        </div>

        {/* ── Upload ─────────────────────────────────────── */}
        {tab === 'upload' && (
          <UploadZone onUploaded={() => { carica(); setTab('lista') }} />
        )}

        {/* ── Ricerca avvisi ─────────────────────────────── */}
        {tab === 'avvisi' && <RicercaTributo />}

        {/* ── Lista F24 ──────────────────────────────────── */}
        {tab === 'lista' && (
          loading ? (
            <div style={{ ...s.card, textAlign: 'center', padding: 40, color: colors.textLight }}>
              Caricamento...
            </div>
          ) : listaPagina1.length === 0 ? (
            <div style={{ ...s.card, textAlign: 'center', padding: 48 }}>
              <FileText size={40} color={colors.border} style={{ marginBottom: 12 }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: colors.textMuted, marginBottom: 6 }}>
                Nessun F24 per il {anno}
              </div>
              <div style={{ fontSize: 13, color: colors.textLight, marginBottom: 16 }}>
                Importa i PDF F24 dalla tab "Importa PDF"
              </div>
              <button onClick={() => setTab('upload')} style={{ ...s.btn, ...s.btnPrimary }}>
                <Upload size={14} /> Importa ora
              </button>
            </div>
          ) : (
            <div style={s.cardNoPad}>
              <table style={s.table}>
                <thead>
                  <tr>
                    <th style={{ ...s.th, width: 32 }} />
                    <th style={s.th}>Scadenza</th>
                    <th style={s.th}>Sezioni</th>
                    <th style={s.th}>Banca</th>
                    <th style={{ ...s.th, textAlign: 'right' }}>Saldo finale</th>
                    <th style={{ ...s.th, textAlign: 'right', width: 100 }}>PDF</th>
                  </tr>
                </thead>
                <tbody>
                  {listaPagina1.map(doc => (
                    <RigaF24 key={doc._id} doc={doc} />
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: colors.primaryBg }}>
                    <td colSpan={4} style={{ ...s.td, fontWeight: 700, color: colors.primaryText }}>
                      TOTALE {anno}
                    </td>
                    <td style={{ ...s.td, textAlign: 'right', fontWeight: 800, fontSize: 16, color: colors.primary }}>
                      {formatEuro(listaPagina1.reduce((acc, d) => acc + (d.saldo_finale || 0), 0))}
                    </td>
                    <td style={s.td} />
                  </tr>
                </tfoot>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  )
}
