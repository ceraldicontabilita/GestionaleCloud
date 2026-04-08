import React, { useState, useEffect, useCallback } from 'react'
import {
  User, Upload, FileText, ChevronDown, ChevronUp,
  Download, RefreshCw, Shield, AlertTriangle, CheckCircle
} from 'lucide-react'
import { s, colors, shadow, formatEuro, font } from '../lib/utils'

const API = '/api/f24-privati'

const SEZIONI_COLOR = {
  ERARIO:  [colors.primaryText,  colors.primaryBg],
  INPS:    [colors.successText,  colors.successBg],
  REGIONI: [colors.infoText,     colors.infoBg],
  IMU:     [colors.warningText,  colors.warningBg],
  INAIL:   [colors.dangerText,   colors.dangerBg],
}

function Badge({ text, sezione }) {
  const [color, bg] = SEZIONI_COLOR[sezione] || [colors.textMuted, colors.borderLight]
  return <span style={{ ...s.badge(color, bg), fontSize: 10 }}>{text}</span>
}

function RigaF24({ doc }) {
  const [espanso, setEspanso] = useState(false)
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
          <div style={{ fontWeight: 600 }}>{doc.scadenza}</div>
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
        <td style={{ ...s.td, textAlign: 'right' }}>
          {doc.note_ravvedimento && (
            <AlertTriangle size={13} color={colors.warning} style={{ marginRight: 6 }} />
          )}
          <span style={{ fontWeight: 700, fontSize: 15, color: colors.primary }}>
            {formatEuro(doc.saldo_finale)}
          </span>
        </td>
        <td style={{ ...s.td, width: 80, textAlign: 'right' }}>
          <a href={`${API}/${doc._id}/pdf`} target="_blank" rel="noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ ...s.btn, ...s.btnGhost, ...s.btnXSmall, textDecoration: 'none' }}>
            <Download size={12} />
          </a>
        </td>
      </tr>
      {espanso && (
        <tr>
          <td colSpan={5} style={{ padding: '0 16px 16px 48px', background: colors.primaryBg }}>
            <div style={{ borderTop: `1px solid ${colors.border}`, paddingTop: 12 }}>
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
                        {t.mese_rif && <span style={{ fontWeight: 400, color: colors.textLight }}> m.{t.mese_rif}</span>}
                        {t.anno_rif && <span style={{ fontWeight: 400, color: colors.textLight }}> / {t.anno_rif}</span>}
                      </div>
                      <div style={{ color: colors.textMuted, fontSize: 10 }}>{t.descrizione}</div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      {t.debito > 0 && <div style={{ fontWeight: 700, color: colors.dangerText, fontSize: 12 }}>-{formatEuro(t.debito)}</div>}
                      {t.credito > 0 && <div style={{ fontWeight: 700, color: colors.successText, fontSize: 12 }}>+{formatEuro(t.credito)}</div>}
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
   PAGINA F24 PRIVATI
   ═══════════════════════════════════════════════════════════ */
export default function F24PrivatiPage() {
  const [soggetti, setSoggetti]   = useState([])
  const [cfSelezionato, setCf]    = useState(null)
  const [anno, setAnno]           = useState(new Date().getFullYear())
  const [lista, setLista]         = useState([])
  const [riepilogo, setRiepilogo] = useState(null)
  const [loading, setLoading]     = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)

  // Carica lista soggetti
  useEffect(() => {
    fetch(`${API}/soggetti`).then(r => r.json()).then(d => {
      setSoggetti(d)
      if (d.length > 0 && !cfSelezionato) setCf(d[0].cf)
    })
  }, [])

  // Carica F24 del soggetto selezionato
  const carica = useCallback(async () => {
    if (!cfSelezionato) return
    setLoading(true)
    const [l, r] = await Promise.all([
      fetch(`${API}?cf=${cfSelezionato}&anno=${anno}`).then(r => r.json()),
      fetch(`${API}/riepilogo/${cfSelezionato}/${anno}`).then(r => r.json()),
    ])
    setLista(Array.isArray(l) ? l.filter(d => (d.pagina || 1) === 1) : [])
    setRiepilogo(r)
    setLoading(false)
  }, [cfSelezionato, anno])

  useEffect(() => { carica() }, [carica])

  const handleUpload = async (e) => {
    const files = e.target.files
    if (!files?.length) return
    setUploading(true)
    setUploadMsg(null)
    const fd = new FormData()
    Array.from(files).forEach(f => fd.append('files', f))
    try {
      const res = await fetch(`${API}/upload-pdf`, { method: 'POST', body: fd })
      const data = await res.json()
      setUploadMsg(data.risultati || [])
      carica()
    } catch (e) {
      setUploadMsg([{ ok: false, errore: e.message }])
    }
    setUploading(false)
    e.target.value = ''
  }

  const soggettoCorrente = soggetti.find(s => s.cf === cfSelezionato)

  return (
    <div style={s.page}>
      <div style={s.container}>

        {/* ── Header ─────────────────────────────────────── */}
        <div style={{ ...s.flexBetween, marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
          <div style={{ ...s.flex, ...s.gap12 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12,
              background: colors.primaryBg,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Shield size={22} color={colors.primary} />
            </div>
            <div>
              <h1 style={s.h1}>F24 Privati</h1>
              <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>
                Sezione riservata — persone fisiche non aziendali
              </div>
            </div>
          </div>
          <label style={{ ...s.btn, ...s.btnGhost, ...s.btnSmall, cursor: 'pointer', opacity: uploading ? 0.7 : 1 }}>
            <Upload size={14} />
            {uploading ? 'Caricamento...' : 'Importa PDF'}
            <input type="file" accept=".pdf,.PDF" multiple onChange={handleUpload}
              style={{ display: 'none' }} disabled={uploading} />
          </label>
        </div>

        {/* Upload feedback */}
        {uploadMsg && (
          <div style={{ marginBottom: 16 }}>
            {uploadMsg.map((r, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 14px', borderRadius: 8, marginBottom: 6,
                background: r.ok ? colors.successBg : colors.dangerBg,
              }}>
                {r.ok
                  ? <CheckCircle size={14} color={colors.success} />
                  : <AlertTriangle size={14} color={colors.danger} />}
                <span style={{ fontSize: 12, fontWeight: 600,
                  color: r.ok ? colors.successText : colors.dangerText }}>
                  {r.ok
                    ? `${r.contribuente} — ${r.azione} (scadenza ${r.scadenza}, ${formatEuro(r.saldo_finale)})`
                    : r.errore}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* ── Soggetti ───────────────────────────────────── */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
          {soggetti.map(sog => (
            <button key={sog.cf} onClick={() => setCf(sog.cf)} style={{
              fontFamily: font, padding: '10px 18px', borderRadius: 12,
              border: `2px solid ${cfSelezionato === sog.cf ? colors.primary : colors.border}`,
              background: cfSelezionato === sog.cf ? colors.primary : colors.card,
              color: cfSelezionato === sog.cf ? '#fff' : colors.text,
              cursor: 'pointer', transition: 'all .15s',
              boxShadow: cfSelezionato === sog.cf ? shadow.btn : shadow.xs,
              display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <User size={16} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{sog.nome}</div>
                <div style={{ fontSize: 10, opacity: 0.75, fontFamily: 'monospace' }}>{sog.cf}</div>
              </div>
              {sog.n_f24 > 0 && (
                <span style={{
                  background: cfSelezionato === sog.cf ? 'rgba(255,255,255,0.25)' : colors.primaryBg,
                  color: cfSelezionato === sog.cf ? '#fff' : colors.primary,
                  borderRadius: 20, fontSize: 11, fontWeight: 700, padding: '2px 8px',
                }}>
                  {sog.n_f24} F24
                </span>
              )}
            </button>
          ))}
        </div>

        {cfSelezionato && (
          <>
            {/* ── Anagrafica soggetto ─────────────────────── */}
            {riepilogo?.anagrafica && (
              <div style={{ ...s.card, marginBottom: 16, background: colors.primaryBg, border: `1px solid ${colors.primary}20` }}>
                <div style={{ ...s.flex, ...s.gap16, flexWrap: 'wrap' }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: colors.primary,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <User size={22} color="#fff" />
                  </div>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: colors.primaryText }}>
                      {riepilogo.anagrafica.nome}
                    </div>
                    <div style={{ fontSize: 12, color: colors.primaryText, opacity: 0.75, marginTop: 2 }}>
                      CF: {cfSelezionato}
                      {riepilogo.anagrafica.data_nascita && ` · nato il ${riepilogo.anagrafica.data_nascita} a ${riepilogo.anagrafica.comune_nascita}`}
                    </div>
                    {riepilogo.anagrafica.domicilio && (
                      <div style={{ fontSize: 12, color: colors.primaryText, opacity: 0.75 }}>
                        {riepilogo.anagrafica.domicilio}
                      </div>
                    )}
                  </div>
                  <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: colors.primaryText, opacity: 0.7, marginBottom: 4 }}>
                      Totale versato {anno}
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: colors.primary }}>
                      {formatEuro(riepilogo.totale_versato || 0)}
                    </div>
                    <div style={{ fontSize: 11, color: colors.primaryText, opacity: 0.7 }}>
                      {riepilogo.n_f24 || 0} F24
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Selettore anno */}
            <div style={{ ...s.flexBetween, marginBottom: 16 }}>
              <div style={{ ...s.flex, ...s.gap8 }}>
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

            {/* ── Lista F24 ──────────────────────────────── */}
            {loading ? (
              <div style={{ ...s.card, textAlign: 'center', padding: 40, color: colors.textLight }}>
                Caricamento...
              </div>
            ) : lista.length === 0 ? (
              <div style={{ ...s.card, textAlign: 'center', padding: 48 }}>
                <FileText size={36} color={colors.border} style={{ marginBottom: 12 }} />
                <div style={{ fontSize: 14, fontWeight: 600, color: colors.textMuted, marginBottom: 6 }}>
                  Nessun F24 per {soggettoCorrente?.nome} nel {anno}
                </div>
                <div style={{ fontSize: 12, color: colors.textLight }}>
                  Importa i PDF con il pulsante in alto
                </div>
              </div>
            ) : (
              <div style={s.cardNoPad}>
                <table style={s.table}>
                  <thead>
                    <tr>
                      <th style={{ ...s.th, width: 32 }} />
                      <th style={s.th}>Scadenza</th>
                      <th style={s.th}>Sezioni</th>
                      <th style={{ ...s.th, textAlign: 'right' }}>Saldo finale</th>
                      <th style={{ ...s.th, width: 80, textAlign: 'right' }}>PDF</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lista.map(doc => <RigaF24 key={doc._id} doc={doc} />)}
                  </tbody>
                  <tfoot>
                    <tr style={{ background: colors.primaryBg }}>
                      <td colSpan={3} style={{ ...s.td, fontWeight: 700, color: colors.primaryText }}>
                        TOTALE {anno} — {soggettoCorrente?.nome}
                      </td>
                      <td style={{ ...s.td, textAlign: 'right', fontWeight: 800, fontSize: 16, color: colors.primary }}>
                        {formatEuro(lista.reduce((acc, d) => acc + (d.saldo_finale || 0), 0))}
                      </td>
                      <td style={s.td} />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
