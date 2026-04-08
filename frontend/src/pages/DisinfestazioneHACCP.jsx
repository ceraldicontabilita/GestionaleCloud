import { useState, useEffect, useCallback } from 'react'
import { Bug, ChevronLeft, ChevronRight, RefreshCw, Check, AlertTriangle, Plus, Edit, Save, X, Printer } from 'lucide-react'
import { s, colors, font } from '../lib/utils'

const API = 'https://ceraldiapp.it/api'
const MESI = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno',
               'Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']

const DITTA = {
  ragione_sociale: 'ANTHIRAT CONTROL S.R.L.',
  partita_iva: '07764320631',
  indirizzo: 'VIA CAMALDOLILLI 142 - 80131 - NAPOLI (NA)',
  pec: 'anthiratcontrol@pec.it',
  rea: '657008',
}

// ─── MODAL REGISTRA INTERVENTO ───────────────────────────────────────────────
function ModalIntervento({ anno, mese, interventoEsistente, onClose, onSalvato }) {
  const oggi = new Date()
  const [giorno, setGiorno] = useState(interventoEsistente?.giorno || 15)
  const [esito, setEsito] = useState(interventoEsistente?.esito || 'OK - Nessuna infestazione rilevata')
  const [note, setNote] = useState(interventoEsistente?.note || 'Derattizzazione e disinfestazione eseguite come da contratto')
  const [saving, setSaving] = useState(false)

  const salva = async () => {
    setSaving(true)
    try {
      await window.fetch(
        `${API}/disinfestazione/registra-intervento/${anno}/${mese}?giorno=${giorno}&esito=${encodeURIComponent(esito)}&note=${encodeURIComponent(note)}`,
        { method: 'POST' }
      )
      onSalvato()
      onClose()
    } catch {}
    setSaving(false)
  }

  const overlay = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
    zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
  }
  const modal = {
    background: colors.card, borderRadius: 16, boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
    width: '100%', maxWidth: 440, fontFamily: font,
  }

  return (
    <div style={overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={modal}>
        <div style={{ ...s.flexBetween, padding: '16px 20px', borderBottom: `1px solid ${colors.border}` }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>Intervento — {MESI[mese-1]} {anno}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={18}/></button>
        </div>
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={s.label}>Giorno del mese</label>
            <input
              type="number" min={1} max={31} value={giorno}
              onChange={e => setGiorno(parseInt(e.target.value) || 1)}
              style={s.input}
            />
          </div>
          <div>
            <label style={s.label}>Esito</label>
            <select value={esito} onChange={e => setEsito(e.target.value)} style={{ ...s.select, width: '100%' }}>
              <option>OK - Nessuna infestazione rilevata</option>
              <option>OK - Presenza minima, gestita</option>
              <option>Richiede intervento straordinario</option>
              <option>Presenza infestanti — trattamento effettuato</option>
            </select>
          </div>
          <div>
            <label style={s.label}>Note</label>
            <textarea
              value={note} onChange={e => setNote(e.target.value)} rows={3}
              style={{ ...s.input, resize: 'none' }}
              placeholder="Note sull'intervento..."
            />
          </div>
        </div>
        <div style={{ ...s.flex, gap: 8, padding: '12px 20px', borderTop: `1px solid ${colors.border}`, background: colors.bg, borderRadius: '0 0 16px 16px' }}>
          <button onClick={onClose} style={{ ...s.btn, ...s.btnNeutral, flex: 1 }}>Annulla</button>
          <button onClick={salva} disabled={saving} style={{ ...s.btn, ...s.btnPrimary, flex: 1 }}>
            {saving ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={14} />}
            Salva
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── MODAL MONITORAGGIO APPARECCHIO ──────────────────────────────────────────
function ModalApparecchio({ anno, mese, apparecchio, datiAttuali, onClose, onSalvato }) {
  const [esito, setEsito] = useState(datiAttuali?.esito || 'OK')
  const [note, setNote] = useState(datiAttuali?.note || '')
  const [saving, setSaving] = useState(false)

  const salva = async () => {
    setSaving(true)
    try {
      await window.fetch(
        `${API}/disinfestazione/registra-monitoraggio/${anno}/${mese}?apparecchio=${encodeURIComponent(apparecchio)}&esito=${encodeURIComponent(esito)}&note=${encodeURIComponent(note)}`,
        { method: 'POST' }
      )
      onSalvato()
      onClose()
    } catch {}
    setSaving(false)
  }

  const overlay = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
    zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
  }

  return (
    <div style={overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{ background: colors.card, borderRadius: 16, boxShadow: '0 20px 60px rgba(0,0,0,0.25)', width: '100%', maxWidth: 380, fontFamily: font }}>
        <div style={{ ...s.flexBetween, padding: '14px 18px', borderBottom: `1px solid ${colors.border}` }}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>{apparecchio}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={16}/></button>
        </div>
        <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={s.label}>Esito Controllo</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { val: 'OK', label: 'OK — Nessun problema', color: colors.success, bg: colors.successBg },
              { val: 'Richiede intervento', label: 'Richiede intervento', color: colors.danger, bg: colors.dangerBg },
            ].map(opt => (
              <button
                key={opt.val}
                onClick={() => setEsito(opt.val)}
                style={{
                  ...s.btn, flexDirection: 'column', gap: 4, padding: '12px 8px',
                  borderRadius: 10, border: `2px solid ${esito === opt.val ? opt.color : colors.border}`,
                  background: esito === opt.val ? opt.bg : colors.card,
                  color: esito === opt.val ? opt.color : colors.textMuted,
                  fontWeight: esito === opt.val ? 700 : 500,
                }}
              >
                {opt.val === 'OK' ? <Check size={16} /> : <AlertTriangle size={16} />}
                <span style={{ fontSize: 11 }}>{opt.label}</span>
              </button>
            ))}
          </div>
          <div>
            <label style={s.label}>Note (opzionale)</label>
            <input type="text" value={note} onChange={e => setNote(e.target.value)}
              placeholder="es. Tracce rilevate in angolo sinistro" style={s.input} />
          </div>
        </div>
        <div style={{ ...s.flex, gap: 8, padding: '10px 18px', borderTop: `1px solid ${colors.border}`, background: colors.bg, borderRadius: '0 0 16px 16px' }}>
          <button onClick={onClose} style={{ ...s.btn, ...s.btnNeutral, flex: 1 }}>Annulla</button>
          <button onClick={salva} disabled={saving} style={{ ...s.btn, ...s.btnPrimary, flex: 1 }}>
            {saving ? <RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={13} />}
            Salva
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── CARD APPARECCHIO ────────────────────────────────────────────────────────
function CardApparecchio({ nome, numero, labelTipo, dati, onClick }) {
  const ok = dati?.esito === 'OK'
  const problema = dati?.controllato && !ok
  const nonCtrl = !dati?.controllato

  return (
    <button
      onClick={onClick}
      title={dati?.note || (nonCtrl ? 'Clicca per registrare' : dati?.esito)}
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        padding: '8px 6px', borderRadius: 10, border: `2px solid`,
        borderColor: ok ? colors.success : problema ? colors.danger : colors.border,
        background: ok ? colors.successBg : problema ? colors.dangerBg : colors.bg,
        minWidth: 58, cursor: 'pointer', fontFamily: font, transition: 'all .12s',
      }}
    >
      <span style={{ fontSize: 9, color: colors.textMuted, fontWeight: 600 }}>{labelTipo}</span>
      <span style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.2 }}>{numero}</span>
      <div style={{
        width: 20, height: 20, borderRadius: '50%', marginTop: 2,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: ok ? colors.success : problema ? colors.danger : colors.borderLight,
      }}>
        {ok ? <Check size={12} color="#fff" /> : problema ? <AlertTriangle size={10} color="#fff" /> : <Plus size={10} color={colors.textMuted} />}
      </div>
    </button>
  )
}

// ─── PAGINA PRINCIPALE ───────────────────────────────────────────────────────
export default function DisinfestazioneHACCP() {
  const [mese, setMese] = useState(new Date().getMonth() + 1)
  const [anno, setAnno] = useState(new Date().getFullYear())
  const [scheda, setScheda] = useState(null)
  const [loading, setLoading] = useState(true)
  const [modalIntervento, setModalIntervento] = useState(false)
  const [modalApp, setModalApp] = useState(null) // { nome, dati }

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const d = await window.fetch(`${API}/disinfestazione/scheda-annuale/${anno}`).then(r => r.json())
      setScheda(d)
    } catch {}
    setLoading(false)
  }, [anno])

  useEffect(() => { fetch() }, [fetch])

  const cambiaMese = (d) => {
    let nm = mese + d, na = anno
    if (nm < 1) { nm = 12; na-- }
    if (nm > 12) { nm = 1; na++ }
    setMese(nm); setAnno(na)
  }

  const getMonitoraggio = (nome) => scheda?.monitoraggio_apparecchi?.[nome]?.[String(mese)] || null
  const intervento = scheda?.interventi_mensili?.[String(mese)] || null

  // Costruisce liste frigo/congelatori da monitoraggio_apparecchi
  const nomiMonitoraggio = Object.keys(scheda?.monitoraggio_apparecchi || {})
  const frigoriferi = nomiMonitoraggio.filter(n => n.includes('Frigorifero')).sort((a,b) => {
    const na = parseInt(a.match(/\d+/)?.[0] || 0), nb = parseInt(b.match(/\d+/)?.[0] || 0)
    return na - nb
  })
  const congelatori = nomiMonitoraggio.filter(n => n.includes('Congelatore')).sort((a,b) => {
    const na = parseInt(a.match(/\d+/)?.[0] || 0), nb = parseInt(b.match(/\d+/)?.[0] || 0)
    return na - nb
  })

  const totApp = [...frigoriferi, ...congelatori]
  const totControllati = totApp.filter(n => getMonitoraggio(n)?.controllato).length
  const totOk = totApp.filter(n => getMonitoraggio(n)?.esito === 'OK').length

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 60, color: colors.textMuted }}>
      <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite' }} />
    </div>
  )

  return (
    <div>
      {/* Modals */}
      {modalIntervento && (
        <ModalIntervento anno={anno} mese={mese} interventoEsistente={intervento}
          onClose={() => setModalIntervento(false)} onSalvato={fetch} />
      )}
      {modalApp && (
        <ModalApparecchio anno={anno} mese={mese} apparecchio={modalApp.nome} datiAttuali={modalApp.dati}
          onClose={() => setModalApp(null)} onSalvato={fetch} />
      )}

      {/* Header */}
      <div style={{ ...s.flexBetween, marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.h1}><Bug size={22} style={{ marginRight: 8, color: colors.danger, verticalAlign: 'middle' }} />Registro Disinfestazione</h1>
          <p style={{ ...s.caption, marginTop: 4 }}>Ceraldi Group S.R.L. — Monitoraggio Pest Control</p>
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={() => cambiaMese(-1)}><ChevronLeft size={15}/></button>
          <span style={{ fontFamily: font, fontWeight: 600, minWidth: 130, textAlign: 'center' }}>{MESI[mese-1]} {anno}</span>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={() => cambiaMese(1)}><ChevronRight size={15}/></button>
          <button
            onClick={() => window.open(`${API}/disinfestazione/export-pdf/${anno}`, '_blank')}
            style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}
          ><Printer size={13}/> PDF</button>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={fetch}><RefreshCw size={13}/></button>
        </div>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        <div style={s.metricCard}>
          <div style={{ fontSize: 22, fontWeight: 700, color: colors.warning }}>{totControllati}/{totApp.length}</div>
          <div style={s.caption}>Apparecchi controllati</div>
        </div>
        <div style={{ ...s.metricCard, background: totOk === totControllati && totControllati > 0 ? colors.successBg : colors.warningBg }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: totOk === totControllati && totControllati > 0 ? colors.success : colors.warning }}>{totOk}</div>
          <div style={s.caption}>Senza problemi</div>
        </div>
        <div style={{ ...s.metricCard, background: intervento ? colors.successBg : colors.bg }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: intervento ? colors.success : colors.textLight }}>
            {intervento ? `Gg ${intervento.giorno}` : '—'}
          </div>
          <div style={s.caption}>Intervento mese</div>
        </div>
        <div style={s.metricCard}>
          <div style={{ fontSize: 13, fontWeight: 600, color: colors.text, lineHeight: 1.3 }}>{DITTA.ragione_sociale}</div>
          <div style={s.caption}>Ditta incaricata</div>
        </div>
      </div>

      {/* Intervento mensile */}
      <div style={{
        ...s.card,
        background: intervento ? colors.successBg : colors.warningBg,
        borderColor: intervento ? colors.success : colors.warning,
        marginBottom: 16,
      }}>
        <div style={s.flexBetween}>
          <div>
            <div style={{ ...s.flex, gap: 8, marginBottom: 4 }}>
              <Bug size={15} color={colors.danger} />
              <span style={{ fontWeight: 700 }}>Intervento {MESI[mese-1]} {anno}</span>
            </div>
            {intervento ? (
              <p style={{ margin: 0, fontSize: 13, color: colors.successText }}>
                <strong>Giorno {intervento.giorno}</strong> — {intervento.esito?.split(' - ')[0]}
                {intervento.note && <span style={{ marginLeft: 8, color: colors.textMuted, fontSize: 12 }}>{intervento.note}</span>}
              </p>
            ) : (
              <p style={{ margin: 0, fontSize: 13, color: colors.warningText }}>Nessun intervento registrato per questo mese</p>
            )}
          </div>
          <button
            onClick={() => setModalIntervento(true)}
            style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall }}
          >
            {intervento ? <><Edit size={13}/> Modifica</> : <><Plus size={13}/> Registra</>}
          </button>
        </div>
      </div>

      {/* Frigoriferi */}
      <div style={{ ...s.cardNoPad, marginBottom: 16 }}>
        <div style={{ ...s.flexBetween, padding: '10px 16px', background: colors.infoBg, borderBottom: `1px solid ${colors.border}` }}>
          <span style={{ fontWeight: 700, color: colors.infoText, fontSize: 13 }}>Frigoriferi — {MESI[mese-1]} {anno}</span>
          <span style={s.badge(colors.infoText, colors.infoBg)}>
            {frigoriferi.filter(n => getMonitoraggio(n)?.controllato).length}/{frigoriferi.length} controllati
          </span>
        </div>
        <p style={{ ...s.caption, padding: '6px 16px 0' }}>Clicca su un frigorifero per registrare il controllo</p>
        <div style={{ padding: '8px 12px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {frigoriferi.map((nome, i) => (
            <CardApparecchio key={nome} nome={nome} numero={i+1} labelTipo="Frigo"
              dati={getMonitoraggio(nome)} onClick={() => setModalApp({ nome, dati: getMonitoraggio(nome) })} />
          ))}
        </div>
      </div>

      {/* Congelatori */}
      <div style={{ ...s.cardNoPad, marginBottom: 16 }}>
        <div style={{ ...s.flexBetween, padding: '10px 16px', background: '#ECFEFF', borderBottom: `1px solid ${colors.border}` }}>
          <span style={{ fontWeight: 700, color: '#0E7490', fontSize: 13 }}>Congelatori — {MESI[mese-1]} {anno}</span>
          <span style={s.badge('#0E7490', '#ECFEFF')}>
            {congelatori.filter(n => getMonitoraggio(n)?.controllato).length}/{congelatori.length} controllati
          </span>
        </div>
        <p style={{ ...s.caption, padding: '6px 16px 0' }}>Clicca su un congelatore per registrare il controllo</p>
        <div style={{ padding: '8px 12px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {congelatori.map((nome, i) => (
            <CardApparecchio key={nome} nome={nome} numero={i+1} labelTipo="Cong"
              dati={getMonitoraggio(nome)} onClick={() => setModalApp({ nome, dati: getMonitoraggio(nome) })} />
          ))}
        </div>
      </div>

      {/* Riepilogo annuale */}
      <div style={s.cardNoPad}>
        <div style={{ padding: '10px 16px', background: colors.bg, borderBottom: `1px solid ${colors.border}` }}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>Riepilogo Interventi {anno}</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={s.table}>
            <thead>
              <tr>
                {MESI.map((m, i) => (
                  <th key={i}
                    onClick={() => setMese(i+1)}
                    style={{
                      ...s.th, cursor: 'pointer', textAlign: 'center',
                      background: mese === i+1 ? colors.primaryBg : '#F8F9FC',
                      color: mese === i+1 ? colors.primaryText : colors.textMuted,
                    }}
                  >{m.slice(0,3)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {MESI.map((_, idx) => {
                  const int = scheda?.interventi_mensili?.[String(idx+1)]
                  return (
                    <td key={idx}
                      onClick={() => setMese(idx+1)}
                      style={{
                        ...s.td, textAlign: 'center', cursor: 'pointer',
                        background: mese === idx+1 ? colors.primaryBg : 'transparent',
                        padding: '8px 4px',
                      }}
                    >
                      {int ? (
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                          <span style={{ fontWeight: 700, fontSize: 13 }}>{int.giorno}</span>
                          <div style={{
                            width: 16, height: 16, borderRadius: '50%',
                            background: int.esito?.includes('OK') ? colors.successBg : colors.warningBg,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}>
                            <Check size={10} color={int.esito?.includes('OK') ? colors.success : colors.warning} />
                          </div>
                        </div>
                      ) : (
                        <span style={{ color: colors.borderLight, fontSize: 16 }}>·</span>
                      )}
                    </td>
                  )
                })}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Legenda */}
      <div style={{ ...s.flex, gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
        <span style={s.badge(colors.successText, colors.successBg)}><Check size={11} style={{ marginRight: 3 }} />OK</span>
        <span style={s.badge(colors.dangerText, colors.dangerBg)}><AlertTriangle size={11} style={{ marginRight: 3 }} />Richiede intervento</span>
        <span style={s.badge(colors.textMuted, colors.borderLight)}><Plus size={11} style={{ marginRight: 3 }} />Non controllato</span>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
