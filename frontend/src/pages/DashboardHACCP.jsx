/**
 * DashboardHACCP.jsx — Pannello controllo Tracciabilità Lotti
 * Adattato da DashboardView.jsx del repo tracciabilita
 * CSS inline con design system gestionale2 (utils.js)
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Package, BookOpen, Layers, FileText, RefreshCw, AlertTriangle,
  ShoppingCart, Clock, CheckCircle, X, Snowflake, ToggleLeft,
  ToggleRight, Thermometer, Search
} from 'lucide-react'
import { s, colors, font, formatEuro } from '../lib/utils'

const API = 'https://ceraldiapp.it/api'

// ─── UTILITY ─────────────────────────────────────────────────────────────────
function parseData(ds) {
  if (!ds) return null
  try {
    if (ds.includes('/')) {
      const [dd, mm, yyyy] = ds.split('/')
      return new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd))
    }
    return new Date(ds)
  } catch { return null }
}

function diffGiorni(d1, d2) {
  return Math.round((d1 - d2) / (1000 * 60 * 60 * 24))
}

function formatData(d) {
  return d.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}

// ─── POPUP MAGAZZINO SEMILAVORATI ─────────────────────────────────────────────
function PopupMagazzinoSemi({ data, onClose }) {
  if (!data) return null
  const prodotti = data.prodotti || []
  const uscite = data.uscite_per_prodotto || []

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div onClick={e => e.stopPropagation()} style={{
        background: colors.card, borderRadius: 20, width: '100%', maxWidth: 700,
        maxHeight: '90vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 24px 64px rgba(0,0,0,0.22)', fontFamily: font,
      }}>
        {/* Header */}
        <div style={{ ...s.flexBetween, padding: '16px 20px', borderBottom: `1px solid ${colors.border}` }}>
          <div style={s.flex}>
            <div style={{ padding: 8, background: colors.infoBg, borderRadius: 10, marginRight: 12 }}>
              <Snowflake size={18} color={colors.info} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14 }}>Magazzino Congelatore — Semilavorati Vandemoortele</div>
              <div style={{ ...s.caption, marginTop: 2 }}>Da {data.data_inizio} · {data.num_fatture_vandemoortele} fatture · {data.num_referenze} referenze</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={18}/></button>
        </div>

        {/* KPI */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1, padding: 16, borderBottom: `1px solid ${colors.border}`, background: colors.bg }}>
          {[
            { val: data.totale_pezzi_entrati, label: 'Pezzi acquistati', sub: 'dalle fatture Vandemoortele', color: colors.info },
            { val: data.totale_pezzi_usciti,  label: 'Pezzi usati',      sub: 'portati al banco (colazione)', color: colors.warning },
            { val: data.saldo_congelatore,    label: 'In congelatore ora', sub: 'acquistati − usati', color: data.saldo_congelatore > 0 ? colors.info : colors.danger },
          ].map(k => (
            <div key={k.label} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: k.color }}>{k.val}</div>
              <div style={{ ...s.label, marginBottom: 0 }}>{k.label}</div>
              <div style={s.caption}>{k.sub}</div>
            </div>
          ))}
        </div>

        {/* Nota */}
        <div style={{ margin: '12px 16px 4px', padding: '8px 12px', background: colors.infoBg, borderRadius: 8, border: `1px solid ${colors.accentBg}` }}>
          <p style={{ ...s.caption, color: colors.infoText, margin: 0 }}>
            <strong>Logica:</strong> Entrate = cartoni × pezzi/cartone. Uscite = pezzi portati al banco ogni mattina. Gli invenduti non rientrano in congelatore.
          </p>
        </div>

        <div style={{ overflowY: 'auto', flex: 1 }}>
          {/* Entrate */}
          <div style={{ padding: '12px 16px' }}>
            <div style={{ ...s.label, marginBottom: 8 }}>Acquisti da fatture (entrate congelatore)</div>
            {prodotti.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24, color: colors.textMuted }}>
                <Snowflake size={28} style={{ opacity: 0.3, margin: '0 auto 8px', display: 'block' }} />
                <p style={s.caption}>Nessuna fattura Vandemoortele trovata</p>
              </div>
            ) : (
              <table style={s.table}>
                <thead>
                  <tr>
                    {['Prodotto', 'Cartoni', 'Pz/cart', 'Pezzi', 'Costo/pz'].map(h => (
                      <th key={h} style={s.th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {prodotti.map((p, i) => (
                    <tr key={i}>
                      <td style={{ ...s.td, fontSize: 12 }}>{p.descrizione_fattura}</td>
                      <td style={{ ...s.td, textAlign: 'center' }}>{p.cartoni_acquistati}</td>
                      <td style={{ ...s.td, textAlign: 'center', color: colors.textMuted }}>{p.pz_cartone ?? '?'}</td>
                      <td style={{ ...s.td, textAlign: 'center', fontWeight: 700, color: colors.info }}>{p.pezzi_entrati}</td>
                      <td style={{ ...s.td, textAlign: 'center', color: colors.textMuted, fontSize: 11 }}>
                        {p.costo_pezzo > 0 ? `€${p.costo_pezzo.toFixed(4)}` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Uscite */}
          {uscite.length > 0 && (
            <div style={{ padding: '12px 16px', borderTop: `1px solid ${colors.border}` }}>
              <div style={{ ...s.label, marginBottom: 8 }}>Utilizzi al banco (uscite congelatore)</div>
              <table style={s.table}>
                <thead><tr>
                  <th style={s.th}>Prodotto</th>
                  <th style={{ ...s.th, textAlign: 'center' }}>Pezzi usati</th>
                </tr></thead>
                <tbody>
                  {uscite.map((u, i) => (
                    <tr key={i}>
                      <td style={{ ...s.td, textTransform: 'capitalize' }}>{u.nome}</td>
                      <td style={{ ...s.td, textAlign: 'center', fontWeight: 700, color: colors.warning }}>{u.pezzi}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Saldo */}
          <div style={{
            margin: '8px 16px 16px', padding: 12, borderRadius: 12,
            border: `2px solid ${data.saldo_congelatore > 0 ? colors.info : colors.danger}`,
            background: data.saldo_congelatore > 0 ? colors.infoBg : colors.dangerBg,
          }}>
            <div style={s.flexBetween}>
              <span style={{ fontWeight: 700, fontSize: 13, color: data.saldo_congelatore > 0 ? colors.infoText : colors.dangerText }}>
                Saldo = {data.totale_pezzi_entrati} − {data.totale_pezzi_usciti}
              </span>
              <span style={{ fontSize: 24, fontWeight: 900, color: data.saldo_congelatore > 0 ? colors.info : colors.danger }}>
                = {data.saldo_congelatore} pz
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── CELLA GRIGLIA ────────────────────────────────────────────────────────────
function Cella({ value, label, sub, sub2, onClick, highlight, euro }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: '14px 16px',
        borderBottom: `1px solid ${colors.borderLight}`,
        borderRight: `1px solid ${colors.borderLight}`,
        background: highlight ? colors.bg : (onClick ? 'transparent' : 'transparent'),
        cursor: onClick ? 'pointer' : 'default',
        transition: 'background .1s',
      }}
      onMouseEnter={e => { if (onClick) e.currentTarget.style.background = colors.primaryBg }}
      onMouseLeave={e => { e.currentTarget.style.background = highlight ? colors.bg : 'transparent' }}
    >
      {value !== undefined && (
        <div style={{ fontSize: 26, fontWeight: 900, color: colors.text, lineHeight: 1, marginBottom: 4 }}>
          {euro && value !== '—' ? `€${typeof value === 'number' ? value.toFixed(2) : value}` : value}
        </div>
      )}
      {label && <div style={{ fontSize: 13, fontWeight: 600, color: colors.textMuted, lineHeight: 1.3 }}>{label}</div>}
      {sub  && <div style={{ ...s.caption, marginTop: 2 }}>{sub}</div>}
      {sub2 && <div style={s.caption}>{sub2}</div>}
    </div>
  )
}

// ─── HEADER RIGA ─────────────────────────────────────────────────────────────
function RigaHeader({ label }) {
  return (
    <div style={{ gridColumn: '1 / -1', background: colors.bg, borderBottom: `1px solid ${colors.borderLight}`, padding: '8px 16px' }}>
      <span style={s.label}>{label}</span>
    </div>
  )
}

// ─── ALERT LOTTO SCADENZA ─────────────────────────────────────────────────────
function AlertLotto({ lotto, onConsuma }) {
  const sc = parseData(lotto.data_scadenza)
  const giorni = sc ? diffGiorni(sc, new Date()) : 999
  const col = giorni < 0 ? colors.danger : giorni <= 1 ? colors.danger : giorni <= 3 ? colors.warning : '#CA8A04'
  const bg  = giorni < 0 ? colors.dangerBg : giorni <= 1 ? colors.dangerBg : giorni <= 3 ? colors.warningBg : '#FEF9C3'

  return (
    <div style={{ ...s.flex, gap: 10, padding: '10px 12px', borderRadius: 12, border: `1px solid ${col}30`, background: bg }}>
      <AlertTriangle size={15} color={col} style={{ flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: col, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textTransform: 'capitalize' }}>{lotto.prodotto}</div>
        <div style={{ ...s.caption, color: col, opacity: 0.8 }}>{lotto.frigo_numero ? `${lotto.frigo_numero} · ` : ''}{lotto.numero_lotto}</div>
      </div>
      <span style={{ ...s.badge(col === colors.danger ? '#fff' : colors.text, col), flexShrink: 0 }}>
        {giorni < 0 ? `Scad. ${Math.abs(giorni)}gg fa` : giorni === 0 ? 'Oggi!' : `${giorni}gg`}
      </span>
      {onConsuma && (
        <button
          onClick={() => onConsuma(lotto.id, lotto.prodotto)}
          title="Marca come consumato"
          style={{ background: 'rgba(255,255,255,0.7)', border: `1px solid ${colors.danger}30`, borderRadius: 8, padding: 6, cursor: 'pointer', color: colors.dangerText }}
        >
          <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
          </svg>
        </button>
      )}
    </div>
  )
}

// ─── PAGINA PRINCIPALE ────────────────────────────────────────────────────────
export default function DashboardHACCP() {
  const [produzioniOggi, setProduzioniOggi]   = useState([])
  const [venditeOggi, setVenditeOggi]          = useState([])
  const [lottiScadenza, setLottiScadenza]      = useState([])
  const [magazzinoSemi, setMagazzinoSemi]      = useState(null)
  const [giornoProduttivo, setGiornoProduttivo] = useState(true)
  const [loading, setLoading]                  = useState(true)
  const [mostraVendite, setMostraVendite]       = useState(false)
  const [mostraPopupSemi, setMostraPopupSemi]   = useState(false)
  const [loadingToggle, setLoadingToggle]       = useState(false)
  const [toast, setToast]                       = useState(null)

  const mostraToast = (msg, tipo = 'success') => {
    setToast({ msg, tipo })
    setTimeout(() => setToast(null), 3500)
  }

  const caricaDati = useCallback(async () => {
    setLoading(true)
    try {
      const [prodR, vendR, lottiR, semiR, gnpR] = await Promise.allSettled([
        fetch(`${API}/produzioni/per-oggi`).then(r => r.json()),
        fetch(`${API}/vendita-banco/oggi`).then(r => r.json()),
        fetch(`${API}/lotti?limit=300`).then(r => r.json()),
        fetch(`${API}/acquaviva/magazzino-congelatore`).then(r => r.json()),
        fetch(`${API}/chiusure/giorno-non-produttivo/oggi`).then(r => r.json()),
      ])

      if (prodR.status === 'fulfilled') setProduzioniOggi(prodR.value || [])
      if (vendR.status === 'fulfilled') setVenditeOggi(vendR.value || [])

      if (lottiR.status === 'fulfilled') {
        const oggi = new Date(); oggi.setHours(0, 0, 0, 0)
        const tra7 = new Date(oggi); tra7.setDate(tra7.getDate() + 7)
        const scad = (lottiR.value || [])
          .filter(l => {
            if (l.consumato) return false
            const sc = parseData(l.data_scadenza)
            return sc && sc <= tra7
          })
          .sort((a, b) => (parseData(a.data_scadenza) || 0) - (parseData(b.data_scadenza) || 0))
          .slice(0, 10)
        setLottiScadenza(scad)
      }

      if (semiR.status === 'fulfilled') setMagazzinoSemi(semiR.value)
      if (gnpR.status === 'fulfilled') setGiornoProduttivo(!gnpR.value?.non_produttivo)
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { caricaDati() }, [caricaDati])

  const toggleGiorno = async () => {
    setLoadingToggle(true)
    try {
      const nuovoStato = !giornoProduttivo
      await fetch(`${API}/chiusure/giorno-non-produttivo/oggi`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ attivo: nuovoStato, motivo: 'Giorno di riposo' })
      })
      setGiornoProduttivo(!nuovoStato)
      mostraToast(nuovoStato ? 'Giorno marcato come non produttivo' : 'Giorno ripristinato come produttivo')
    } catch { mostraToast('Errore aggiornamento stato', 'danger') }
    setLoadingToggle(false)
  }

  const consumaLotto = async (id, nome) => {
    if (!window.confirm(`Marcare "${nome}" come consumato?`)) return
    try {
      await fetch(`${API}/lotti/${id}/consuma`, { method: 'PATCH' })
      setLottiScadenza(prev => prev.filter(l => l.id !== id))
      mostraToast(`"${nome}" marcato come consumato`)
    } catch { mostraToast('Errore', 'danger') }
  }

  // ─── Calcoli ────────────────────────────────────────────────────────────────
  const isSemi = v => v.fonte === 'colazione' || v.fonte === 'acquaviva'

  const aperte = venditeOggi.filter(v => v.stato === 'aperto')
  const chiuse = venditeOggi.filter(v => v.stato === 'chiuso')

  const pezziProdPast   = produzioniOggi.filter(p => p.reparto === 'pasticceria').reduce((s, p) => s + (p.quantita || 0), 0)
  const pezziProdCucina = produzioniOggi.filter(p => p.reparto === 'rosticceria').reduce((s, p) => s + (p.quantita || 0), 0)

  const pezziPastAlBanco   = venditeOggi.filter(v => v.reparto === 'pasticceria' && !isSemi(v)).reduce((s, v) => s + (v.pezzi_prodotti || 0), 0)
  const pezziCucinaAlBanco = venditeOggi.filter(v => v.reparto === 'rosticceria' && !isSemi(v)).reduce((s, v) => s + (v.pezzi_prodotti || 0), 0)
  const pezziSemiAlBanco   = venditeOggi.filter(isSemi).reduce((s, v) => s + (v.pezzi_prodotti || 0), 0)

  const pezziPastInCella   = Math.max(0, pezziProdPast - pezziPastAlBanco)
  const pezziCucinaInCella = Math.max(0, pezziProdCucina - pezziCucinaAlBanco)

  const vendutiPast   = chiuse.filter(v => v.reparto === 'pasticceria').reduce((s, v) => s + (v.pezzi_venduti || 0), 0)
  const vendutiCucina = chiuse.filter(v => v.reparto === 'rosticceria').reduce((s, v) => s + (v.pezzi_venduti || 0), 0)
  const venduteSemi   = chiuse.filter(isSemi).reduce((s, v) => s + (v.pezzi_venduti || 0), 0)

  const invPast   = chiuse.filter(v => v.reparto === 'pasticceria').reduce((s, v) => s + (v.pezzi_invenduto || 0), 0)
  const invCucina = chiuse.filter(v => v.reparto === 'rosticceria').reduce((s, v) => s + (v.pezzi_invenduto || 0), 0)
  const invSemi   = chiuse.filter(isSemi).reduce((s, v) => s + (v.pezzi_invenduto || 0), 0)

  const incassoPast   = aperte.filter(v => v.reparto === 'pasticceria').reduce((s, v) => s + ((v.prezzo_vendita || 0) * (v.pezzi_prodotti || 0)), 0)
  const incassoCucina = aperte.filter(v => v.reparto === 'rosticceria').reduce((s, v) => s + ((v.prezzo_vendita || 0) * (v.pezzi_prodotti || 0)), 0)
  const incassoSemi   = aperte.filter(isSemi).reduce((s, v) => s + ((v.prezzo_vendita || 0) * (v.pezzi_prodotti || 0)), 0)

  const costoPast   = chiuse.filter(v => v.reparto === 'pasticceria').reduce((s, v) => s + ((v.costo_produzione || 0) * (v.pezzi_invenduto || 0)), 0)
  const costoCucina = chiuse.filter(v => v.reparto === 'rosticceria').reduce((s, v) => s + ((v.costo_produzione || 0) * (v.pezzi_invenduto || 0)), 0)
  const costoSemi   = chiuse.filter(isSemi).reduce((s, v) => s + ((v.costo_produzione || 0) * (v.pezzi_invenduto || 0)), 0)

  const totAlBanco = venditeOggi.reduce((s, v) => s + (v.pezzi_prodotti || 0), 0)
  const totVenduti = chiuse.reduce((s, v) => s + (v.pezzi_venduti || 0), 0)
  const totInvenduti = chiuse.reduce((s, v) => s + (v.pezzi_invenduto || 0), 0)
  const pezziAperte = aperte.reduce((s, v) => s + (v.pezzi_prodotti || 0), 0)

  const semiCongelatore = magazzinoSemi?.saldo_congelatore ?? 0
  const semiEntrati     = magazzinoSemi?.totale_pezzi_entrati ?? 0
  const semiUsciti      = magazzinoSemi?.totale_pezzi_usciti ?? 0

  const lottiCritici = lottiScadenza.filter(l => {
    const sc = parseData(l.data_scadenza)
    return sc && diffGiorni(sc, new Date()) <= 1
  })

  return (
    <div style={{ fontFamily: font }}>
      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: 16, right: 16, zIndex: 2000,
          background: toast.tipo === 'danger' ? colors.dangerBg : colors.successBg,
          color: toast.tipo === 'danger' ? colors.dangerText : colors.successText,
          border: `1px solid ${toast.tipo === 'danger' ? colors.danger : colors.success}`,
          padding: '10px 18px', borderRadius: 10, fontWeight: 600, fontSize: 13,
          boxShadow: '0 4px 20px rgba(0,0,0,0.12)',
        }}>
          {toast.msg}
        </div>
      )}

      {/* Popup semilavorati */}
      {mostraPopupSemi && <PopupMagazzinoSemi data={magazzinoSemi} onClose={() => setMostraPopupSemi(false)} />}

      {/* Header */}
      <div style={{ ...s.flexBetween, marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.h1}>Pannello di Controllo</h1>
          <p style={{ ...s.caption, marginTop: 4 }}>{formatData(new Date())}</p>
        </div>
        <div style={{ ...s.flex, gap: 8 }}>
          <button
            onClick={toggleGiorno}
            disabled={loadingToggle}
            style={{
              ...s.btn,
              background: giornoProduttivo ? colors.card : colors.warningBg,
              color: giornoProduttivo ? colors.textMuted : colors.warningText,
              border: `1px solid ${giornoProduttivo ? colors.border : colors.warning}`,
              fontSize: 13,
            }}
          >
            {giornoProduttivo
              ? <><ToggleLeft size={16} /> Giorno Produttivo</>
              : <><ToggleRight size={16} color={colors.warning} /> Giorno di Riposo</>
            }
          </button>
          <button onClick={caricaDati} style={{ ...s.btn, ...s.btnNeutral }}>
            <RefreshCw size={15} style={loading ? { animation: 'spin 1s linear infinite' } : {}} /> Aggiorna
          </button>
        </div>
      </div>

      {/* Accesso rapido Tablet */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ ...s.label, marginBottom: 10 }}>Accesso Rapido Tablet</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {[
            { href: 'https://ceraldiapp.it/#tablet/rosticceria', label: 'Rosticceria compressa', sub: 'Registra lotti salati', bg: colors.infoBg, border: colors.info, col: colors.infoText },
            { href: 'https://ceraldiapp.it/#tablet/pasticceria', label: 'Pasticceria in compresse', sub: 'Registra + stampa etichetta', bg: colors.warningBg, border: colors.warning, col: colors.warningText },
            { href: 'https://ceraldiapp.it/#tablet/vendita',     label: 'Tablet',                  sub: 'Registro invenduto serale', bg: '#FFF7ED', border: '#F97316', col: '#C2410C' },
          ].map(t => (
            <a key={t.href} href={t.href} target="_blank" rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px',
                borderRadius: 12, border: `2px solid ${t.border}40`, background: t.bg,
                textDecoration: 'none', transition: 'border-color .15s',
              }}
            >
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: t.col }}>{t.label}</div>
                <div style={{ ...s.caption, color: t.col, opacity: 0.8, marginTop: 2 }}>{t.sub}</div>
              </div>
            </a>
          ))}
        </div>
      </div>

      {/* Alert lotti in scadenza */}
      {lottiScadenza.length > 0 && (
        <div style={{ ...s.card, marginBottom: 20 }}>
          <div style={{ ...s.flex, gap: 8, marginBottom: 14 }}>
            <AlertTriangle size={18} color={colors.warning} />
            <span style={{ fontWeight: 700, fontSize: 14 }}>Lotti in Scadenza — prossimi 7 giorni</span>
            <span style={{ ...s.badge(colors.warningText, colors.warningBg), marginLeft: 'auto' }}>{lottiScadenza.length}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            {lottiScadenza.map(l => <AlertLotto key={l.id} lotto={l} onConsuma={consumaLotto} />)}
          </div>
        </div>
      )}

      {/* Griglia 3 colonne */}
      <div style={{ ...s.cardNoPad, marginBottom: 20 }}>
        {/* Intestazioni colonne */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', borderBottom: `2px solid ${colors.border}`, background: colors.bg }}>
          {['PRODOTTI IN PASTICCERIA', 'PRODOTTI IN CUCINA', 'PRODOTTI SEMILAVORATI'].map((h, i) => (
            <div key={h} style={{ padding: '10px 16px', borderRight: i < 2 ? `1px solid ${colors.border}` : 'none' }}>
              <span style={s.label}>{h}</span>
            </div>
          ))}
        </div>

        {/* Riga 1: Prodotti oggi */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <Cella value={pezziProdPast}   label="Prodotti in pasticceria" sub={`${produzioniOggi.filter(p=>p.reparto==='pasticceria').length} lavorazioni`} />
          <Cella value={pezziProdCucina} label="prodotti in cucina"      sub={`${produzioniOggi.filter(p=>p.reparto==='rosticceria').length} lavorazioni`} />
          <Cella value={semiCongelatore} label="In alternativa ora"      sub={`${semiEntrati} ingressi − ${semiUsciti} utenti`} sub2={`${magazzinoSemi?.num_referenze ?? 0} riferimenti Vandemoortele`} onClick={() => setMostraPopupSemi(true)} />
        </div>

        {/* Riga 2: Al banco */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', background: `${colors.info}06` }}>
          <Cella value={pezziPastAlBanco}   label="Al banco oggi" sub={`${pezziPastAlBanco} laboratorio`} sub2={`${aperte.filter(v=>v.reparto==='pasticceria').length} operazioni esterne`} onClick={() => window.open('https://ceraldiapp.it/#tablet/vendita','_blank')} />
          <Cella value={pezziCucinaAlBanco} label="Al banco oggi"                                          sub2={`${aperte.filter(v=>v.reparto==='rosticceria').length} operazioni esterne`} onClick={() => window.open('https://ceraldiapp.it/#tablet/vendita','_blank')} />
          <Cella value={pezziSemiAlBanco}   label="Al banco oggi" sub="pezzi dal sedere"                  sub2={`${aperte.filter(isSemi).length} operazioni esterne`} onClick={() => setMostraPopupSemi(true)} />
        </div>

        {/* Riga 3: In frigo */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <Cella value={pezziPastInCella}   label="In frigo/congelatori" sub={pezziPastInCella > 0 ? 'Non ancora al banco' : 'Tutto al banco'} />
          <Cella value={pezziCucinaInCella} label="In frigo/congelatori" sub={pezziCucinaInCella > 0 ? 'Non ancora al banco' : 'Tutto al banco'} />
          <Cella value={0} label="Rientrati inosservare" sub="Gli invenduti non riciclano" onClick={() => setMostraPopupSemi(true)} />
        </div>

        {/* Riga 4: Venduti */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', background: `${colors.success}08` }}>
          <Cella value={vendutiPast}   label="Venduti oggi" sub={invPast > 0 ? `${invPast} invenduti` : chiuse.filter(v=>v.reparto==='pasticceria').length > 0 ? 'Nessuno spreco' : 'In corso'} onClick={() => setMostraVendite(v => !v)} />
          <Cella value={vendutiCucina} label="Venduti oggi" sub={invCucina > 0 ? `${invCucina} invenduti` : chiuse.filter(v=>v.reparto==='rosticceria').length > 0 ? 'Nessuno spreco' : 'In corso'} onClick={() => setMostraVendite(v => !v)} />
          <Cella value={venduteSemi}   label="Venduti oggi" sub={invSemi > 0 ? `${invSemi} invenduti` : '—'} onClick={() => setMostraVendite(v => !v)} />
        </div>

        {/* Riga 5: Incasso potenziale */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', background: `${colors.primary}05` }}>
          <Cella value={incassoPast   > 0 ? incassoPast.toFixed(2)   : '—'} label="Incasso potenziale" sub="euro" euro={incassoPast > 0} />
          <Cella value={incassoCucina > 0 ? incassoCucina.toFixed(2) : '—'} label="Incasso potenziale" sub="euro" euro={incassoCucina > 0} />
          <Cella value={incassoSemi   > 0 ? incassoSemi.toFixed(2)   : '—'} label="Incasso potenziale" sub="euro" euro={incassoSemi > 0} />
        </div>

        {/* Riga 6: Costo invenduto */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <Cella value={costoPast   > 0 ? costoPast.toFixed(2)   : '—'} label="Costo effettivo" sub="euro (invenduto)" euro={costoPast > 0} highlight />
          <Cella value={costoCucina > 0 ? costoCucina.toFixed(2) : '—'} label="Costo effettivo" sub="euro (invenduto)" euro={costoCucina > 0} highlight />
          <Cella value={costoSemi   > 0 ? costoSemi.toFixed(2)   : '—'} label="Costo effettivo" sub="euro (invenduto)" euro={costoSemi > 0} highlight />
        </div>
      </div>

      {/* Dettaglio banco (aperto al click venduti) */}
      {mostraVendite && venditeOggi.length > 0 && (
        <div style={{ ...s.card, marginBottom: 20 }}>
          <div style={{ ...s.flexBetween, marginBottom: 14 }}>
            <span style={{ fontWeight: 700, fontSize: 14, ...s.flex, gap: 8 }}>
              <ShoppingCart size={16} color={colors.warning} /> Dettaglio Banco Oggi
            </span>
            <button onClick={() => setMostraVendite(false)} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>Chiudi</button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead><tr>
                {['Prodotto','Al banco','Venduti','Invenduti','Stato'].map(h => <th key={h} style={s.th}>{h}</th>)}
              </tr></thead>
              <tbody>
                {venditeOggi.filter(v => (v.pezzi_prodotti || 0) > 0).map(v => (
                  <tr key={v.id}>
                    <td style={{ ...s.td, textTransform: 'capitalize', fontWeight: 500 }}>{v.prodotto_nome}</td>
                    <td style={{ ...s.td, textAlign: 'center' }}>{v.pezzi_prodotti || 0}</td>
                    <td style={{ ...s.td, textAlign: 'center', fontWeight: 700, color: colors.success }}>{v.pezzi_venduti ?? '—'}</td>
                    <td style={{ ...s.td, textAlign: 'center', fontWeight: 700, color: colors.danger }}>{v.pezzi_invenduto ?? '—'}</td>
                    <td style={{ ...s.td, textAlign: 'center' }}>
                      <span style={s.badge(
                        v.stato === 'chiuso' ? colors.successText : colors.warningText,
                        v.stato === 'chiuso' ? colors.successBg   : colors.warningBg
                      )}>{v.stato === 'chiuso' ? 'Chiuso' : 'Aperto'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr>
                <td style={{ ...s.td, fontWeight: 700 }}>Totale</td>
                <td style={{ ...s.td, textAlign: 'center', fontWeight: 700 }}>{totAlBanco}</td>
                <td style={{ ...s.td, textAlign: 'center', fontWeight: 700, color: colors.success }}>{totVenduti}</td>
                <td style={{ ...s.td, textAlign: 'center', fontWeight: 700, color: colors.danger }}>{totInvenduti}</td>
                <td style={s.td}></td>
              </tr></tfoot>
            </table>
          </div>
        </div>
      )}

      {/* KPI Archivio */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ ...s.label, marginBottom: 10 }}>Archivio</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
          {[
            { icon: Package,  bg: colors.infoBg,     col: colors.info,    label: 'Materie Prime',  href: 'https://ceraldiapp.it/#materie' },
            { icon: BookOpen, bg: colors.successBg,  col: colors.success, label: 'Ricette',        href: 'https://ceraldiapp.it/#ricette' },
            { icon: Layers,   bg: colors.primaryBg,  col: colors.primary, label: 'Lotti Totali',   href: 'https://ceraldiapp.it/#lotti' },
            { icon: FileText, bg: '#EEF2FF',          col: '#4338CA',      label: 'Fatture',        href: 'https://ceraldiapp.it/#fatture' },
            { icon: Search,   bg: colors.dangerBg,   col: colors.danger,  label: 'Recall ASL',     href: 'https://ceraldiapp.it/#lotti' },
          ].map(k => (
            <a key={k.label} href={k.href} target="_blank" rel="noopener noreferrer"
              style={{
                ...s.metricCard, display: 'flex', alignItems: 'center', gap: 10,
                textDecoration: 'none', transition: 'box-shadow .15s',
              }}
            >
              <div style={{ padding: 8, background: k.bg, borderRadius: 10, flexShrink: 0 }}>
                <k.icon size={16} color={k.col} />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: colors.text }}>—</div>
                <div style={s.caption}>{k.label}</div>
              </div>
            </a>
          ))}
        </div>
      </div>

      {/* Scadenze critiche + aperti */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 20 }}>
        <div style={{ ...s.metricCard, ...s.flex, gap: 12, cursor: 'pointer' }}>
          <div style={{ padding: 8, borderRadius: 10, background: lottiCritici.length > 0 ? colors.dangerBg : colors.successBg }}>
            {lottiCritici.length > 0
              ? <AlertTriangle size={18} color={colors.danger} />
              : <CheckCircle size={18} color={colors.success} />
            }
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 900, color: colors.text }}>{lottiCritici.length || 'OK'}</div>
            <div style={s.caption}>Scadono oggi/domani</div>
          </div>
        </div>
        <a href="https://ceraldiapp.it/#tablet/vendita" target="_blank" rel="noopener noreferrer"
          style={{ ...s.metricCard, ...s.flex, gap: 12, cursor: 'pointer', textDecoration: 'none' }}>
          <div style={{ padding: 8, borderRadius: 10, background: aperte.length > 0 ? colors.warningBg : colors.successBg }}>
            <Package size={18} color={aperte.length > 0 ? colors.warning : colors.success} />
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 900, color: colors.text }}>
              {aperte.length > 0 ? pezziAperte : totAlBanco}
            </div>
            <div style={s.caption}>{aperte.length > 0 ? `${aperte.length} referenze aperte` : 'Tutti registrati'}</div>
          </div>
        </a>
      </div>

      {/* Produzioni di oggi */}
      {produzioniOggi.length > 0 && (
        <div style={s.card}>
          <div style={{ ...s.flexBetween, marginBottom: 14 }}>
            <span style={{ fontWeight: 700, fontSize: 14, ...s.flex, gap: 8 }}>
              <Clock size={16} color={colors.info} /> Produzioni di Oggi
            </span>
            <a href="https://ceraldiapp.it/#storico_produzioni" target="_blank" rel="noopener noreferrer"
              style={{ ...s.caption, color: colors.primary, textDecoration: 'none', fontWeight: 600 }}>
              Vedi tutte
            </a>
          </div>
          <div>
            {produzioniOggi.slice(0, 8).map(p => (
              <div key={p.id} style={{ ...s.flexBetween, padding: '8px 0', borderBottom: `1px solid ${colors.borderLight}` }}>
                <span style={{ fontSize: 13, fontWeight: 500, textTransform: 'capitalize' }}>{p.ricetta_nome}</span>
                <div style={{ ...s.flex, gap: 10 }}>
                  {p.frigo_numero && <span style={s.badge(colors.infoText, colors.infoBg)}>{p.frigo_numero}</span>}
                  <span style={{ fontWeight: 700, color: colors.info }}>{p.pezzi} pz</span>
                  {p.costo_totale > 0 && <span style={s.caption}>€{p.costo_totale.toFixed(2)}</span>}
                </div>
              </div>
            ))}
            {produzioniOggi.length > 8 && (
              <p style={{ ...s.caption, textAlign: 'center', marginTop: 8 }}>+{produzioniOggi.length - 8} altre produzioni</p>
            )}
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
