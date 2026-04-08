import React, { useState, useEffect } from 'react'
import {
  AlertTriangle, CheckCircle, AlertCircle, Shield,
  Clock, TrendingDown, FileText, RefreshCw, ExternalLink,
  Zap, Building2, Receipt
} from 'lucide-react'
import { s, colors, shadow, formatEuro, font } from '../lib/utils'

const API = '/api/alert-fiscali'

/* ── Colori per livello ─────────────────────────────────────── */
function livelloStyle(livello) {
  const map = {
    critical: { bg: colors.dangerBg,  border: colors.danger,  text: colors.dangerText,  icon: colors.danger },
    danger:   { bg: colors.dangerBg,  border: colors.danger,  text: colors.dangerText,  icon: colors.danger },
    warning:  { bg: colors.warningBg, border: colors.warning, text: colors.warningText, icon: colors.warning },
    info:     { bg: colors.infoBg,    border: colors.info,    text: colors.infoText,    icon: colors.info },
    ok:       { bg: colors.successBg, border: colors.success, text: colors.successText, icon: colors.success },
  }
  return map[livello] || map.info
}

/* ── Badge livello ──────────────────────────────────────────── */
function LivBadge({ livello }) {
  const st = livelloStyle(livello)
  const label = { critical:'CRITICO', danger:'URGENTE', warning:'ATTENZIONE', info:'INFO', ok:'OK' }
  return (
    <span style={{ ...s.badge(st.text, st.bg), fontSize: 10 }}>
      {label[livello] || livello.toUpperCase()}
    </span>
  )
}

/* ── Card alert singola ─────────────────────────────────────── */
function AlertCard({ alert, icon: Icon }) {
  const st = livelloStyle(alert.livello)
  return (
    <div style={{
      padding: '14px 18px', borderRadius: 12, marginBottom: 10,
      background: st.bg,
      borderLeft: `4px solid ${st.border}`,
      border: `1px solid ${st.border}30`,
    }}>
      <div style={{ ...s.flexBetween, marginBottom: 8 }}>
        <div style={{ ...s.flex, gap: 8 }}>
          <Icon size={16} color={st.icon} />
          <span style={{ fontWeight: 700, fontSize: 13, color: colors.text }}>
            {alert.tipo?.replace(/_/g, ' ')}
          </span>
          <LivBadge livello={alert.livello} />
        </div>
        {alert.importo > 0 && (
          <span style={{ fontWeight: 800, fontSize: 15, color: st.text }}>
            {formatEuro(alert.importo || alert.importo_totale_non_versato || alert.importo_pagato)}
          </span>
        )}
      </div>

      <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 8, lineHeight: 1.6 }}>
        {alert.testo}
      </div>

      {/* Dettagli specifici */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {alert.periodo && (
          <span style={{ fontSize: 11, color: colors.textMuted, background: colors.bg,
            padding: '3px 8px', borderRadius: 6 }}>
            Periodo: {alert.periodo}
          </span>
        )}
        {alert.scadenza && (
          <span style={{ fontSize: 11, color: colors.textMuted, background: colors.bg,
            padding: '3px 8px', borderRadius: 6 }}>
            Scadenza: {alert.scadenza}
          </span>
        )}
        {alert.giorni_ritardo > 0 && (
          <span style={{ fontSize: 11, fontWeight: 700, color: st.text, background: st.bg,
            padding: '3px 8px', borderRadius: 6, border: `1px solid ${st.border}30` }}>
            {alert.giorni_ritardo}gg di ritardo
          </span>
        )}
        {alert.giorni_al_770 !== undefined && (
          <span style={{ fontSize: 11, fontWeight: 700,
            color: alert.giorni_al_770 < 60 ? colors.dangerText : colors.warningText,
            background: alert.giorni_al_770 < 60 ? colors.dangerBg : colors.warningBg,
            padding: '3px 8px', borderRadius: 6 }}>
            {alert.giorni_al_770 > 0 ? `${alert.giorni_al_770}gg al 770` : `770 scaduto da ${Math.abs(alert.giorni_al_770)}gg`}
          </span>
        )}
        {alert.durc === 'IRREGOLARE' && (
          <span style={{ fontSize: 11, fontWeight: 700, color: colors.dangerText,
            background: colors.dangerBg, padding: '3px 8px', borderRadius: 6,
            border: `1px solid ${colors.danger}40` }}>
            🔴 DURC IRREGOLARE
          </span>
        )}
        {alert.sanzione_pct && (
          <span style={{ fontSize: 11, color: colors.warningText, background: colors.warningBg,
            padding: '3px 8px', borderRadius: 6 }}>
            Sanzione: {alert.sanzione_pct}%
          </span>
        )}
        {alert.ha_quietanza === false && (
          <span style={{ fontSize: 11, color: colors.dangerText, background: colors.dangerBg,
            padding: '3px 8px', borderRadius: 6 }}>
            ❌ Senza quietanza
          </span>
        )}
        {alert.ha_quietanza === true && (
          <span style={{ fontSize: 11, color: colors.successText, background: colors.successBg,
            padding: '3px 8px', borderRadius: 6 }}>
            ✅ Quietanza presente
          </span>
        )}
      </div>

      {/* Alert penale ritenute */}
      {alert.avviso_penale && (
        <div style={{
          marginTop: 10, padding: '8px 12px', borderRadius: 8,
          background: '#7f0000', color: '#fff', fontSize: 12, fontWeight: 700,
          lineHeight: 1.5,
        }}>
          ⚖️ {alert.avviso_penale}
        </div>
      )}

      {/* Alert ravvedimento urgente */}
      {alert.avviso && !alert.avviso_penale && (
        <div style={{
          marginTop: 8, padding: '7px 12px', borderRadius: 8,
          background: colors.warningBg, color: colors.warningText,
          fontSize: 12, lineHeight: 1.5,
        }}>
          ⚡ {alert.avviso}
        </div>
      )}

      {/* Codice atto avviso bonario */}
      {alert.codice_atto && (
        <div style={{ marginTop: 8, fontSize: 11, color: colors.textMuted }}>
          Codice Atto: <code style={{ fontFamily: 'monospace', background: colors.bg,
            padding: '2px 6px', borderRadius: 4 }}>{alert.codice_atto}</code>
          {alert.documento_correlato_trovato
            ? <span style={{ marginLeft: 8, color: colors.successText }}>✅ Documento trovato in archivio</span>
            : <span style={{ marginLeft: 8, color: colors.dangerText }}>⚠️ Verificare in archivio documenti</span>
          }
        </div>
      )}
    </div>
  )
}

/* ── KPI Summary ────────────────────────────────────────────── */
function SummaryKpi({ sommario }) {
  if (!sommario) return null
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
      <div style={{ ...s.metricCard, borderLeft: `3px solid ${sommario.critici_e_danger > 0 ? colors.danger : colors.success}` }}>
        <div style={s.label}>Alert critici</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: sommario.critici_e_danger > 0 ? colors.danger : colors.success }}>
          {sommario.critici_e_danger}
        </div>
      </div>
      <div style={{ ...s.metricCard, borderLeft: `3px solid ${sommario.warning > 0 ? colors.warning : colors.success}` }}>
        <div style={s.label}>Attenzione</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: sommario.warning > 0 ? colors.warning : colors.success }}>
          {sommario.warning}
        </div>
      </div>
      <div style={{ ...s.metricCard, borderLeft: `3px solid ${sommario.durc_a_rischio ? colors.danger : colors.success}` }}>
        <div style={s.label}>DURC</div>
        <div style={{ fontSize: 14, fontWeight: 700,
          color: sommario.durc_a_rischio ? colors.dangerText : colors.successText }}>
          {sommario.durc_a_rischio ? '🔴 A RISCHIO' : '🟢 Regolare'}
        </div>
      </div>
      <div style={{ ...s.metricCard, borderLeft: `3px solid ${sommario.rischio_penale ? '#7f0000' : colors.success}` }}>
        <div style={s.label}>Soglia penale 150k</div>
        <div style={{ fontSize: 14, fontWeight: 700,
          color: sommario.rischio_penale ? '#7f0000' : colors.successText }}>
          {sommario.rischio_penale ? '⚖️ RISCHIO PENALE' : '✅ Sotto soglia'}
        </div>
      </div>
      <div style={{ ...s.metricCard, borderLeft: `3px solid ${sommario.f24_senza_quietanza > 0 ? colors.warning : colors.success}` }}>
        <div style={s.label}>F24 senza quietanza</div>
        <div style={{ fontSize: 24, fontWeight: 800,
          color: sommario.f24_senza_quietanza > 0 ? colors.warning : colors.success }}>
          {sommario.f24_senza_quietanza}
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   COMPONENTE PRINCIPALE
   ═══════════════════════════════════════════════════════════════ */
export default function AlertFiscali() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sezione, setSezione] = useState('tutti')

  const carica = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/dashboard`)
      setData(await res.json())
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  useEffect(() => { carica() }, [])

  if (loading) return (
    <div style={{ padding: 48, textAlign: 'center', color: colors.textLight }}>
      Analisi situazione fiscale in corso...
    </div>
  )

  if (!data) return null

  const { alert_inps, alert_ritenute, alert_avvisi_bonari, alert_f24_orfani, sommario } = data

  const sezioni = [
    { id: 'tutti', label: `Tutti (${sommario?.totale_alert || 0})` },
    { id: 'inps', label: `INPS+DURC (${alert_inps.length})` },
    { id: 'ritenute', label: `Ritenute 1001 (${alert_ritenute.length})` },
    { id: 'avvisi', label: `Avvisi bonari (${alert_avvisi_bonari.length})` },
    { id: 'orfani', label: `Senza quietanza (${alert_f24_orfani.length})` },
  ]

  return (
    <div style={s.page}>
      <div style={s.container}>

        {/* Header */}
        <div style={{ ...s.flexBetween, marginBottom: 24 }}>
          <div style={{ ...s.flex, gap: 12 }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, background: colors.dangerBg,
              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Shield size={22} color={colors.danger} />
            </div>
            <div>
              <h1 style={s.h1}>Alert Fiscali</h1>
              <div style={{ fontSize: 12, color: colors.textLight, marginTop: 2 }}>
                Aggiornato: {data.data_oggi} · Fonte: normativa vigente
              </div>
            </div>
          </div>
          <button onClick={carica} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
            <RefreshCw size={14} /> Aggiorna
          </button>
        </div>

        {/* KPI */}
        <SummaryKpi sommario={sommario} />

        {/* Disclaimer normativo */}
        <div style={{
          padding: '10px 16px', borderRadius: 10, marginBottom: 20,
          background: colors.infoBg, border: `1px solid ${colors.info}30`,
          fontSize: 12, color: colors.infoText, lineHeight: 1.6,
        }}>
          <strong>Riferimenti normativi:</strong> Contributi INPS — scadenza 16° mese succ. (art.19 DL 19/2024, circ. INPS 34/2025, TUR+5.5% max 40%) · 
          Ritenute 1001 — termine 770 (art.10-bis DLgs 74/2000, soglia penale €150.000/anno) · 
          Ravvedimento operoso — (art.13 DLgs 472/97, DLgs 87/2024) · 
          DURC — irregolare da primo giorno di ritardo.
        </div>

        {/* Tab sezioni */}
        <div style={{ ...s.flex, gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
          {sezioni.map(s2 => (
            <button key={s2.id} onClick={() => setSezione(s2.id)} style={{
              fontFamily: font, fontSize: 12, fontWeight: 600,
              padding: '7px 14px', borderRadius: 10, border: 'none', cursor: 'pointer',
              background: sezione === s2.id
                ? `linear-gradient(135deg, ${colors.primary} 0%, ${colors.primaryLight} 100%)`
                : colors.bg,
              color: sezione === s2.id ? '#fff' : colors.textMuted,
              boxShadow: sezione === s2.id ? shadow.btn : 'none',
              transition: 'all .15s',
            }}>{s2.label}</button>
          ))}
        </div>

        {/* ── Alert INPS ────────────────────────────────────── */}
        {(sezione === 'tutti' || sezione === 'inps') && (
          <div>
            {(sezione === 'tutti') && (
              <div style={{ ...s.flex, gap: 8, marginBottom: 12 }}>
                <Building2 size={16} color={colors.primary} />
                <h2 style={{ ...s.h2, margin: 0 }}>Contributi INPS / DURC</h2>
              </div>
            )}
            {alert_inps.length === 0 ? (
              <div style={{ ...s.card, ...s.flex, gap: 10, padding: '14px 18px', marginBottom: 16 }}>
                <CheckCircle size={16} color={colors.success} />
                <span style={{ fontSize: 13, color: colors.successText }}>
                  Nessun alert contributi INPS — DURC regolare ✅
                </span>
              </div>
            ) : alert_inps.map((a, i) => (
              <AlertCard key={i} alert={a} icon={Building2} />
            ))}
          </div>
        )}

        {/* ── Alert Ritenute ────────────────────────────────── */}
        {(sezione === 'tutti' || sezione === 'ritenute') && (
          <div style={{ marginTop: sezione === 'tutti' ? 20 : 0 }}>
            {(sezione === 'tutti') && (
              <div style={{ ...s.flex, gap: 8, marginBottom: 12 }}>
                <Receipt size={16} color={colors.primary} />
                <h2 style={{ ...s.h2, margin: 0 }}>Ritenute IRPEF (cod. 1001)</h2>
              </div>
            )}
            {alert_ritenute.length === 0 ? (
              <div style={{ ...s.card, ...s.flex, gap: 10, padding: '14px 18px', marginBottom: 16 }}>
                <CheckCircle size={16} color={colors.success} />
                <span style={{ fontSize: 13, color: colors.successText }}>
                  Nessuna ritenuta 1001 non versata ✅
                </span>
              </div>
            ) : alert_ritenute.map((a, i) => (
              <AlertCard key={i} alert={{ ...a, importo: a.importo_totale_non_versato }} icon={Receipt} />
            ))}
          </div>
        )}

        {/* ── Avvisi bonari ─────────────────────────────────── */}
        {(sezione === 'tutti' || sezione === 'avvisi') && (
          <div style={{ marginTop: sezione === 'tutti' ? 20 : 0 }}>
            {(sezione === 'tutti') && (
              <div style={{ ...s.flex, gap: 8, marginBottom: 12 }}>
                <AlertCircle size={16} color={colors.primary} />
                <h2 style={{ ...s.h2, margin: 0 }}>Avvisi bonari (cod. 9001/9002)</h2>
              </div>
            )}
            {alert_avvisi_bonari.length === 0 ? (
              <div style={{ ...s.card, ...s.flex, gap: 10, padding: '14px 18px', marginBottom: 16 }}>
                <CheckCircle size={16} color={colors.success} />
                <span style={{ fontSize: 13, color: colors.successText }}>
                  Nessun avviso bonario attivo ✅
                </span>
              </div>
            ) : alert_avvisi_bonari.map((a, i) => (
              <AlertCard key={i} alert={{ ...a, importo: a.importo_pagato || a.importo }} icon={AlertCircle} />
            ))}
          </div>
        )}

        {/* ── F24 senza quietanza ───────────────────────────── */}
        {(sezione === 'tutti' || sezione === 'orfani') && alert_f24_orfani.length > 0 && (
          <div style={{ marginTop: sezione === 'tutti' ? 20 : 0 }}>
            {(sezione === 'tutti') && (
              <div style={{ ...s.flex, gap: 8, marginBottom: 12 }}>
                <FileText size={16} color={colors.warning} />
                <h2 style={{ ...s.h2, margin: 0 }}>F24 senza quietanza ADE</h2>
              </div>
            )}
            <div style={s.cardNoPad}>
              <table style={s.table}>
                <thead>
                  <tr>
                    <th style={s.th}>Scadenza</th>
                    <th style={s.th}>Stato</th>
                    <th style={{ ...s.th, textAlign: 'right' }}>Importo</th>
                    <th style={s.th}>Nota</th>
                  </tr>
                </thead>
                <tbody>
                  {alert_f24_orfani.map((a, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? colors.bg + '60' : 'transparent' }}>
                      <td style={s.td}>{a.scadenza}</td>
                      <td style={s.td}>
                        <span style={{ ...s.badge(colors.warningText, colors.warningBg), fontSize: 10 }}>
                          {a.stato}
                        </span>
                      </td>
                      <td style={{ ...s.td, textAlign: 'right', fontWeight: 700 }}>
                        {formatEuro(a.saldo_finale)}
                      </td>
                      <td style={{ ...s.td, fontSize: 11, color: colors.textLight }}>
                        Caricare quietanza per conferma
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
