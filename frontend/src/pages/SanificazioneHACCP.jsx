import { useState, useEffect, useCallback } from 'react'
import { Sparkles, Refrigerator, Snowflake, ChevronLeft, ChevronRight, RefreshCw, Save, Check, X, Printer } from 'lucide-react'
import { s, colors, font } from '../lib/utils'

const API = '/api/tr'
const MESI = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno',
               'Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
const OPERATORE = 'SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA'

function giorniNelMese(m, a) { return new Date(a, m, 0).getDate() }

// ─── TAB ATTREZZATURE ────────────────────────────────────────────────────────
function TabAttrezzature({ mese, anno }) {
  const [scheda, setScheda] = useState(null)
  const [attrezzature, setAttrezzature] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const nGiorni = giorniNelMese(mese, anno)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const [schedaR, attrR] = await Promise.all([
        window.fetch(`${API}/sanificazione/scheda/${anno}/${mese}`).then(r => r.json()),
        window.fetch(`${API}/sanificazione/attrezzature`).then(r => r.json()),
      ])
      // Se scheda è vuota → popola automaticamente
      const hasData = Object.values(schedaR?.registrazioni || {}).some(g => Object.keys(g).length > 0)
      if (!hasData) {
        try {
          await window.fetch(`${API}/haccp/popola-sanificazione?anno=${anno}&mese=${mese}`, { method: 'POST' })
          const nuova = await window.fetch(`${API}/sanificazione/scheda/${anno}/${mese}`).then(r => r.json())
          setScheda(nuova)
        } catch { setScheda(schedaR) }
      } else {
        setScheda(schedaR)
      }
      setAttrezzature(attrR)
      setDirty(false)
    } catch {}
    setLoading(false)
  }, [mese, anno])

  useEffect(() => { fetch() }, [fetch])

  const toggleCella = (attr, giorno) => {
    if (!scheda) return
    const reg = { ...scheda.registrazioni }
    if (!reg[attr]) reg[attr] = {}
    reg[attr][String(giorno)] = reg[attr][String(giorno)] === 'X' ? '' : 'X'
    setScheda({ ...scheda, registrazioni: reg })
    setDirty(true)
  }

  const marcaGiorno = async (giorno) => {
    // Ottimistico: aggiorna UI subito
    const reg = { ...scheda.registrazioni }
    attrezzature.forEach(a => {
      if (!reg[a]) reg[a] = {}
      reg[a][String(giorno)] = 'X'
    })
    setScheda({ ...scheda, registrazioni: reg })
    setDirty(true)
    // Poi chiama API singola
    try {
      await window.fetch(`${API}/sanificazione/scheda/${anno}/${mese}/giorno-completo?giorno=${giorno}`, { method: 'POST' })
      setDirty(false)
    } catch {}
  }

  const salva = async () => {
    setSaving(true)
    try {
      await window.fetch(`${API}/sanificazione/scheda/${anno}/${mese}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ registrazioni: scheda.registrazioni, operatore: '' })
      })
      setDirty(false)
    } catch {}
    setSaving(false)
  }

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>
      <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
    </div>
  )

  return (
    <div>
      {/* Toolbar "marca tutto giorno" */}
      <div style={{ ...s.flex, gap: 4, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ ...s.label, marginBottom: 0, marginRight: 4 }}>Marca tutto:</span>
        {Array.from({ length: nGiorni }, (_, i) => (
          <button
            key={i+1}
            onClick={() => marcaGiorno(i+1)}
            style={{
              ...s.btn, ...s.btnSmall,
              background: colors.infoBg, color: colors.infoText,
              border: `1px solid ${colors.info}`, padding: '4px 8px', fontSize: 11,
            }}
          >{i+1}</button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={fetch}><RefreshCw size={13}/></button>
          <button
            style={{ ...s.btn, ...(dirty ? s.btnPrimary : s.btnNeutral), ...s.btnSmall }}
            onClick={salva} disabled={saving || !dirty}
          >
            <Save size={13}/> {saving ? 'Salvo...' : 'Salva'}
          </button>
        </div>
      </div>

      {/* Griglia */}
      <div style={s.cardNoPad}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ ...s.table, minWidth: nGiorni * 30 + 220 }}>
            <thead>
              <tr>
                <th style={{ ...s.th, minWidth: 210, position: 'sticky', left: 0, zIndex: 2, textAlign: 'left' }}>Attrezzatura</th>
                {Array.from({ length: nGiorni }, (_, i) => (
                  <th key={i+1} style={{ ...s.th, width: 28, minWidth: 28, textAlign: 'center', padding: '8px 2px' }}>{i+1}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {attrezzature.map((attr, ri) => (
                <tr key={attr} style={{ background: ri % 2 === 0 ? colors.card : colors.bg }}>
                  <td style={{ ...s.td, fontWeight: 500, fontSize: 12, position: 'sticky', left: 0, background: 'inherit', padding: '8px 12px' }}>
                    {attr}
                  </td>
                  {Array.from({ length: nGiorni }, (_, i) => {
                    const g = i + 1
                    const val = scheda?.registrazioni?.[attr]?.[String(g)] || ''
                    return (
                      <td key={g} style={{ ...s.td, textAlign: 'center', padding: '4px 2px' }}>
                        <button
                          onClick={() => toggleCella(attr, g)}
                          title={val === 'X' ? 'Sanificato — clicca per rimuovere' : 'Clicca per segnare'}
                          style={{
                            width: 22, height: 22, borderRadius: 4, border: 'none',
                            cursor: 'pointer', fontSize: 11, fontWeight: 700,
                            background: val === 'X' ? colors.primary : colors.borderLight,
                            color: val === 'X' ? '#fff' : colors.textLight,
                            transition: 'all .1s',
                          }}
                        >{val === 'X' ? 'X' : ''}</button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer */}
      <div style={{ ...s.flexBetween, marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
        <span style={s.caption}>Responsabile: <strong>{scheda?.operatore_responsabile || OPERATORE}</strong></span>
        {dirty && <span style={s.badge(colors.warningText, colors.warningBg)}>Modifiche non salvate</span>}
        <button
          onClick={() => window.open(`${API}/sanificazione/export-pdf/${anno}/${mese}`, '_blank')}
          style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}
        ><Printer size={13}/> PDF</button>
      </div>
    </div>
  )
}

// ─── TAB APPARECCHI REFRIGERANTI ─────────────────────────────────────────────
function TabApparecchi({ mese, anno }) {
  const [scheda, setScheda] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const d = await window.fetch(`${API}/sanificazione/apparecchi/${anno}`).then(r => r.json())
      setScheda(d)
    } catch {}
    setLoading(false)
  }, [anno])

  useEffect(() => { fetch() }, [fetch])

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>
      <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
    </div>
  )

  const getSanifMese = (tipo, numero) => {
    const key = String(numero)
    const lista = tipo === 'frigo'
      ? scheda?.registrazioni_frigoriferi?.[key] || []
      : scheda?.registrazioni_congelatori?.[key] || []
    return lista.filter(s => s.mese === mese)
  }

  const StatsTipo = ({ tipo, label, icona: Icona, bgColor, textCol }) => {
    const totEseguite = Array.from({ length: 12 }, (_, i) => getSanifMese(tipo, i+1))
      .flat().filter(s => s.eseguita).length
    const tot = Array.from({ length: 12 }, (_, i) => getSanifMese(tipo, i+1)).flat().length
    return (
      <div style={{ ...s.flex, gap: 10, marginBottom: 8 }}>
        <Icona size={16} style={{ color: textCol }} />
        <span style={{ fontWeight: 600, color: textCol }}>{label}</span>
        <span style={s.badge(textCol, bgColor)}>{totEseguite}/{tot} eseguite</span>
      </div>
    )
  }

  const GrigliaApparecchi = ({ tipo, label, colore, bgHdr, textHdr }) => {
    const nGiorni = new Date(anno, mese, 0).getDate()
    return (
      <div style={{ ...s.cardNoPad, marginBottom: 16 }}>
        <div style={{ padding: '10px 16px', background: bgHdr, borderBottom: `1px solid ${colors.border}` }}>
          <span style={{ fontWeight: 700, color: textHdr, fontSize: 13 }}>{label} — {MESI[mese-1]} {anno}</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ ...s.table, minWidth: 13 * 58 + 50 }}>
            <thead>
              <tr>
                <th style={{ ...s.th, width: 40, position: 'sticky', left: 0, zIndex: 2 }}>G</th>
                {Array.from({ length: 12 }, (_, i) => (
                  <th key={i+1} style={{ ...s.th, minWidth: 56, textAlign: 'center', fontSize: 10 }}>
                    {tipo === 'frigo' ? `F${i+1}` : `C${i+1}`}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: nGiorni }, (_, gi) => {
                const g = gi + 1
                return (
                  <tr key={g} style={{ background: g % 2 === 0 ? colors.bg : colors.card }}>
                    <td style={{ ...s.td, fontWeight: 700, position: 'sticky', left: 0, background: 'inherit', width: 40, padding: '5px 10px' }}>{g}</td>
                    {Array.from({ length: 12 }, (_, ai) => {
                      const n = ai + 1
                      const sanifs = getSanifMese(tipo, n)
                      const sanif = sanifs.find(s => s.giorno === g)
                      return (
                        <td key={n} style={{ ...s.td, textAlign: 'center', padding: '3px 2px' }}>
                          {sanif ? (
                            <div
                              title={sanif.eseguita ? 'Pulizia eseguita' : 'Non eseguita'}
                              style={{
                                width: 20, height: 20, borderRadius: '50%', margin: '0 auto',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: sanif.eseguita ? colors.success : colors.dangerBg,
                              }}
                            >
                              {sanif.eseguita
                                ? <Check size={12} color="#fff" />
                                : <X size={12} color={colors.dangerText} />
                              }
                            </div>
                          ) : (
                            <div style={{ width: 20, height: 20, margin: '0 auto' }} />
                          )}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  // Statistiche mese corrente
  const totFrigo = Array.from({ length: 12 }, (_, i) => getSanifMese('frigo', i+1)).flat()
  const totCong = Array.from({ length: 12 }, (_, i) => getSanifMese('cong', i+1)).flat()
  const esegFrigo = totFrigo.filter(s => s.eseguita).length
  const esegCong = totCong.filter(s => s.eseguita).length

  return (
    <div>
      {/* Operatore + KPI */}
      <div style={{ ...s.card, background: colors.primaryBg, borderColor: colors.primary, marginBottom: 16 }}>
        <div style={{ ...s.flex, gap: 8, marginBottom: 6 }}>
          <span style={{ ...s.label, marginBottom: 0 }}>Operatore sanificazione:</span>
          <span style={{ fontWeight: 600, fontSize: 13, color: colors.primaryText }}>{OPERATORE}</span>
        </div>
        <p style={{ ...s.caption, margin: 0 }}>Pulizia ogni 7-10 giorni per apparecchio • Un solo apparecchio per giorno</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        {[
          { label: 'Sanif. frigo', val: `${esegFrigo}/${totFrigo.length}`, color: colors.warning },
          { label: 'Sanif. cong.', val: `${esegCong}/${totCong.length}`, color: colors.info },
          { label: 'Eseguite', val: esegFrigo + esegCong, color: colors.success },
          { label: 'Non eseguite', val: (totFrigo.length + totCong.length) - (esegFrigo + esegCong), color: colors.danger },
        ].map(k => (
          <div key={k.label} style={s.metricCard}>
            <div style={{ fontSize: 22, fontWeight: 700, color: k.color }}>{k.val}</div>
            <div style={{ ...s.caption, marginTop: 2 }}>{k.label} — {MESI[mese-1]}</div>
          </div>
        ))}
      </div>

      <GrigliaApparecchi tipo="frigo"  label="Frigoriferi (0°C / +4°C)" colore={colors.warning} bgHdr={colors.warningBg} textHdr={colors.warningText} />
      <GrigliaApparecchi tipo="cong"   label="Congelatori (-22°C / -18°C)" colore={colors.info}  bgHdr={colors.infoBg}    textHdr={colors.infoText}    />

      {/* Legenda */}
      <div style={{ ...s.flex, gap: 16, flexWrap: 'wrap' }}>
        <span style={s.badge(colors.successText, colors.successBg)}><Check size={11} style={{ marginRight: 3 }} />Eseguita</span>
        <span style={s.badge(colors.dangerText, colors.dangerBg)}><X size={11} style={{ marginRight: 3 }} />Non eseguita</span>
        <span style={s.badge(colors.textMuted, colors.borderLight)}>vuoto = non programmata</span>
      </div>
    </div>
  )
}

// ─── PAGINA PRINCIPALE ───────────────────────────────────────────────────────
export default function SanificazioneHACCP() {
  const [tab, setTab] = useState('attrezzature')
  const [mese, setMese] = useState(new Date().getMonth() + 1)
  const [anno, setAnno] = useState(new Date().getFullYear())

  const cambiaMese = (d) => {
    let nm = mese + d, na = anno
    if (nm < 1) { nm = 12; na-- }
    if (nm > 12) { nm = 1; na++ }
    setMese(nm); setAnno(na)
  }

  const tabs = [
    { key: 'attrezzature', label: 'Attrezzature', icon: Sparkles },
    { key: 'apparecchi',   label: 'Apparecchi Refrigeranti', icon: Refrigerator },
  ]

  return (
    <div>
      {/* Header */}
      <div style={{ ...s.flexBetween, marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.h1}><Sparkles size={22} style={{ marginRight: 8, color: colors.primary, verticalAlign: 'middle' }} />Registro Sanificazione</h1>
          <p style={{ ...s.caption, marginTop: 4 }}>Ceraldi Group S.R.L. — Sala e Servizi</p>
        </div>
        <div style={s.flex}>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={() => cambiaMese(-1)}><ChevronLeft size={15}/></button>
          <span style={{ fontFamily: font, fontWeight: 600, minWidth: 130, textAlign: 'center', margin: '0 4px' }}>{MESI[mese-1]} {anno}</span>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={() => cambiaMese(1)}><ChevronRight size={15}/></button>
        </div>
      </div>

      {/* Tab switcher */}
      <div style={{ ...s.flex, gap: 4, marginBottom: 20, borderBottom: `2px solid ${colors.border}` }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              ...s.btn, gap: 6, borderRadius: '8px 8px 0 0', padding: '8px 16px',
              background: tab === t.key ? colors.card : 'transparent',
              color: tab === t.key ? colors.primary : colors.textMuted,
              fontWeight: tab === t.key ? 700 : 500,
              borderBottom: tab === t.key ? `2px solid ${colors.primary}` : '2px solid transparent',
              marginBottom: -2, transition: 'all .15s',
            }}
          >
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'attrezzature'
        ? <TabAttrezzature mese={mese} anno={anno} />
        : <TabApparecchi mese={mese} anno={anno} />
      }

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
