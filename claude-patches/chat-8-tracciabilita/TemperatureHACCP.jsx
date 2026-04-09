import { useState, useEffect, useCallback } from 'react'
import { Thermometer, Snowflake, ChevronLeft, ChevronRight, RefreshCw, Printer, AlertTriangle } from 'lucide-react'
import { s, colors, font } from '../lib/utils'

const API = '/api/tr'
const MESI = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno',
               'Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']

function giorniNelMese(m, a) { return new Date(a, m, 0).getDate() }

// ─── CELLA TEMPERATURA ───────────────────────────────────────────────────────
function CellaTemp({ record, tempMin, tempMax, colore }) {
  if (!record) return <span style={{ color: colors.textLight, fontSize: 11 }}>—</span>
  if (record.is_chiuso) return <span title="CHIUSO" style={{ fontSize: 12 }}>🚫</span>
  if (record.is_manutenzione) return <span title="MANUTENZIONE" style={{ fontSize: 12 }}>🔧</span>
  if (record.is_non_usato) return <span title="NON USATO" style={{ fontSize: 12 }}>⏸</span>
  const temp = record.temp ?? record
  if (temp == null) return <span style={{ color: colors.textLight, fontSize: 11 }}>—</span>
  const fuori = temp > tempMax || temp < tempMin
  return (
    <span
      title={record.operatore ? `${temp}°C – ${record.operatore}` : `${temp}°C`}
      style={{
        fontSize: 11, fontWeight: fuori ? 700 : 500,
        color: fuori ? colors.dangerText : colore,
        background: fuori ? colors.dangerBg : 'transparent',
        borderRadius: 4, padding: fuori ? '1px 3px' : 0,
      }}
    >{temp}°</span>
  )
}

// ─── GRIGLIA COMUNE ──────────────────────────────────────────────────────────
function GrigliaTemperature({ schede, mese, anno, numApparecchi, nomi, tempMin, tempMax, colore, labelCol }) {
  const nGiorni = giorniNelMese(mese, anno)
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ ...s.table, minWidth: numApparecchi * 58 + 50 }}>
        <thead>
          <tr>
            <th style={{ ...s.th, width: 40, position: 'sticky', left: 0, zIndex: 2 }}>G</th>
            {Array.from({ length: numApparecchi }, (_, i) => (
              <th key={i+1} style={{ ...s.th, minWidth: 56, textAlign: 'center', fontSize: 10 }}>
                {nomi[i+1] || `${labelCol}${i+1}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: nGiorni }, (_, gi) => {
            const g = gi + 1
            return (
              <tr key={g} style={{ background: g % 2 === 0 ? colors.bg : colors.card }}>
                <td style={{ ...s.td, fontWeight: 700, position: 'sticky', left: 0, background: 'inherit', width: 40, padding: '6px 10px' }}>{g}</td>
                {Array.from({ length: numApparecchi }, (_, ai) => {
                  const n = ai + 1
                  const record = schede[n]?.temperature?.[String(mese)]?.[String(g)]
                  return (
                    <td key={n} style={{ ...s.td, textAlign: 'center', padding: '4px 2px' }}>
                      <CellaTemp record={record} tempMin={tempMin} tempMax={tempMax} colore={colore} />
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── PANNELLO TEMPERATURE (riusabile per positiva/negativa) ──────────────────
function PannelloTemperature({ tipo }) {
  const isPos = tipo === 'positiva'
  const [mese, setMese] = useState(new Date().getMonth() + 1)
  const [anno, setAnno] = useState(new Date().getFullYear())
  const [schede, setSchede] = useState({})
  const [nomi, setNomi] = useState({})
  const [loading, setLoading] = useState(true)
  const [errore, setErrore] = useState(null)

  const endpoint = isPos ? 'temperature-positive' : 'temperature-negative'
  const keyNum = isPos ? 'frigorifero_numero' : 'congelatore_numero'
  const keyNome = isPos ? 'frigorifero_nome' : 'congelatore_nome'
  const tempMin = isPos ? 0 : -22
  const tempMax = isPos ? 4 : -18
  const range = isPos ? '0°C / +4°C' : '-22°C / -18°C'
  const colore = isPos ? '#C2410C' : '#0E7490'

  const fetch12Schede = useCallback(async () => {
    setLoading(true); setErrore(null)
    try {
      const results = await Promise.all(
        Array.from({ length: 12 }, (_, i) =>
          fetch(`${API}/${endpoint}/scheda/${anno}/${i + 1}`).then(r => r.json())
        )
      )
      const map = {}, nomiMap = {}
      results.forEach((d, i) => {
        map[i + 1] = d
        nomiMap[i + 1] = d[keyNome] || (isPos ? `F${i+1}` : `C${i+1}`)
      })
      setSchede(map); setNomi(nomiMap)
    } catch { setErrore('Errore connessione API tracciabilità') }
    setLoading(false)
  }, [anno, endpoint, keyNome, isPos])

  useEffect(() => { fetch12Schede() }, [fetch12Schede])

  const cambiaMese = (d) => {
    let nm = mese + d, na = anno
    if (nm < 1) { nm = 12; na-- }
    if (nm > 12) { nm = 1; na++ }
    setMese(nm); setAnno(na)
  }

  // Conta allarmi del mese
  const allarmi = Object.values(schede).reduce((acc, sch) => {
    const giorni = sch?.temperature?.[String(mese)] || {}
    Object.values(giorni).forEach(r => {
      if (r && !r.is_chiuso && !r.is_manutenzione && !r.is_non_usato) {
        const t = r.temp ?? r
        if (t != null && (t > tempMax || t < tempMin)) acc++
      }
    })
    return acc
  }, 0)

  return (
    <div>
      {/* Sub-header */}
      <div style={{ ...s.flexBetween, marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <div style={s.flex}>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={() => cambiaMese(-1)}><ChevronLeft size={15}/></button>
          <span style={{ fontFamily: font, fontWeight: 600, minWidth: 130, textAlign: 'center', margin: '0 4px' }}>{MESI[mese-1]} {anno}</span>
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={() => cambiaMese(1)}><ChevronRight size={15}/></button>
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          {allarmi > 0 && (
            <span style={s.badge(colors.dangerText, colors.dangerBg)}>
              <AlertTriangle size={12} style={{ marginRight: 4 }} />{allarmi} fuori range
            </span>
          )}
          <button style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }} onClick={fetch12Schede}><RefreshCw size={13}/></button>
        </div>
      </div>

      {/* Info strip */}
      <div style={{ ...s.flex, gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={s.badge(colors.infoText, colors.infoBg)}>Range: {range}</span>
        <span style={{ ...s.caption }}>Operatori: Pocci Salvatore, Vincenzo Ceraldi</span>
        <span style={{ ...s.caption }}>Reg. CE 852/2004 • D.Lgs. 193/2007</span>
      </div>

      {errore && <div style={{ ...s.card, background: colors.dangerBg, color: colors.dangerText, marginBottom: 12 }}>{errore}</div>}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>
          <RefreshCw size={22} style={{ animation: 'spin 1s linear infinite' }} />
          <p style={{ marginTop: 8 }}>Caricamento schede...</p>
        </div>
      ) : (
        <div style={s.cardNoPad}>
          <GrigliaTemperature
            schede={schede} mese={mese} anno={anno}
            numApparecchi={12} nomi={nomi}
            tempMin={tempMin} tempMax={tempMax}
            colore={colore}
            labelCol={isPos ? 'F' : 'C'}
          />
        </div>
      )}

      {/* Legenda */}
      <div style={{ ...s.flex, gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
        <span style={s.badge(colore, isPos ? '#FFF7ED' : '#ECFEFF')}>Temp OK</span>
        <span style={s.badge(colors.dangerText, colors.dangerBg)}>Fuori range</span>
        <span style={s.badge(colors.textMuted, colors.bg)}>🚫 Chiuso</span>
        <span style={s.badge(colors.warningText, colors.warningBg)}>🔧 Manutenzione</span>
        <span style={s.badge(colors.textMuted, colors.borderLight)}>⏸ Non usato</span>
      </div>
    </div>
  )
}

// ─── PAGINA PRINCIPALE ───────────────────────────────────────────────────────
export default function TemperatureHACCP() {
  const [tab, setTab] = useState('positiva')

  const tabs = [
    { key: 'positiva', label: 'Frigoriferi (+)', icon: Thermometer, colore: colors.warning },
    { key: 'negativa', label: 'Congelatori (−)', icon: Snowflake,   colore: colors.info },
  ]

  return (
    <div>
      <div style={{ ...s.flexBetween, marginBottom: 20 }}>
        <div>
          <h1 style={s.h1}>
            {tab === 'positiva'
              ? <><Thermometer size={22} style={{ marginRight: 8, color: colors.warning, verticalAlign: 'middle' }} />Temperature Frigoriferi</>
              : <><Snowflake size={22} style={{ marginRight: 8, color: colors.info, verticalAlign: 'middle' }} />Temperature Congelatori</>
            }
          </h1>
          <p style={{ ...s.caption, marginTop: 4 }}>HACCP — Ceraldi Group S.R.L.</p>
        </div>
      </div>

      {/* Tab switcher */}
      <div style={{ ...s.flex, gap: 4, marginBottom: 20, borderBottom: `2px solid ${colors.border}`, paddingBottom: 0 }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              ...s.btn, gap: 6, borderRadius: '8px 8px 0 0',
              padding: '8px 18px',
              background: tab === t.key ? colors.card : 'transparent',
              color: tab === t.key ? t.colore : colors.textMuted,
              fontWeight: tab === t.key ? 700 : 500,
              borderBottom: tab === t.key ? `2px solid ${t.colore}` : '2px solid transparent',
              marginBottom: -2,
              transition: 'all .15s',
            }}
          >
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>

      <PannelloTemperature tipo={tab} />

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
