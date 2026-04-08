import React, { useState, useEffect, useRef } from 'react'
import {
  Building2, Upload, Globe, FileText, BarChart2,
  CreditCard, RefreshCw, Plus, ChevronDown, ChevronRight,
  TrendingUp, TrendingDown, Minus, ExternalLink, Check,
  AlertTriangle, Loader
} from 'lucide-react'
import { s, colors, shadow, formatEuro, font, statoBadge } from '../lib/utils'

const API = '/api/fornitori'

/* ── Trend badge ──────────────────────────────────────── */
function TrendBadge({ trend, var_pct }) {
  const cfg = {
    crescita: { color: colors.dangerText, bg: colors.dangerBg, Icon: TrendingUp },
    calo:     { color: colors.successText, bg: colors.successBg, Icon: TrendingDown },
    stabile:  { color: colors.textMuted, bg: colors.bg, Icon: Minus },
  }[trend] || { color: colors.textMuted, bg: colors.bg, Icon: Minus }
  const { color, bg, Icon } = cfg
  return (
    <span style={{ ...s.badge(color, bg), gap: 4, fontSize: 10 }}>
      <Icon size={10} /> {var_pct != null ? `${var_pct > 0 ? '+' : ''}${var_pct}%` : trend}
    </span>
  )
}

/* ── Tab Anagrafica ───────────────────────────────────── */
function TabAnagrafica({ fornitore }) {
  const a = fornitore?.anagrafica || {}
  const sede = a.sede || {}
  return (
    <div>
      <div style={{ ...s.card, marginBottom: 12, background: colors.primaryBg,
        border: `1px solid ${colors.primary}30` }}>
        <div style={{ fontSize: 11, color: colors.primary, fontWeight: 600, marginBottom: 8 }}>
          Auto-popolato da fatture XML SDI
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {[
            ['Ragione Sociale', a.ragione_sociale],
            ['P.IVA', a.piva],
            ['Codice Fiscale', a.codice_fiscale],
            ['Codice SDI', a.codice_sdi],
            ['PEC', a.pec],
            ['Regime Fiscale', a.regime_fiscale],
          ].map(([label, val]) => (
            <div key={label}>
              <div style={s.label}>{label}</div>
              <div style={{ fontSize: 13, color: colors.text, fontWeight: 500 }}>
                {val || <span style={{ color: colors.textLight }}>—</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Sede legale</div>
        <div style={{ fontSize: 13, color: colors.text, marginTop: 4 }}>
          {[sede.indirizzo, sede.numero_civico, sede.cap, sede.comune, sede.provincia]
            .filter(Boolean).join(', ') || '—'}
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginTop: 10 }}>
        {[
          ['Prima fattura', a.prima_fattura_data],
          ['Ultima fattura', a.ultima_fattura_data],
          ['N° fatture', a.n_fatture_totali],
        ].map(([label, val]) => (
          <div key={label} style={s.metricCard}>
            <div style={s.label}>{label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: colors.primary }}>{val || '—'}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Tab Schede tecniche ──────────────────────────────── */
function TabSchede({ fornitore, onRefresh }) {
  const fid = fornitore._id
  const [url, setUrl] = useState('')
  const [label, setLabel] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)
  const schede = fornitore?.schede_tecniche || {}
  const urls = schede.urls_scraping || []
  const pdfs = schede.pdf_tecnici || []

  const avviaScraping = async () => {
    if (!url) return
    setLoading(true)
    setMsg(null)
    try {
      const res = await fetch(`${API}/${fid}/scraping`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, label: label || url }),
      })
      const d = await res.json()
      setMsg({ ok: true, testo: d.messaggio })
      setUrl(''); setLabel('')
      setTimeout(onRefresh, 3000)
    } catch (e) {
      setMsg({ ok: false, testo: String(e) })
    }
    setLoading(false)
  }

  const uploadPdf = async (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    await fetch(`${API}/${fid}/pdf?tipo=scheda_tecnica`, { method: 'POST', body: fd })
    onRefresh()
  }

  return (
    <div>
      {/* Import da URL */}
      <div style={{ ...s.card, marginBottom: 12 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10, color: colors.text }}>
          Importa da URL (web scraping)
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input value={label} onChange={e => setLabel(e.target.value)}
            placeholder="Label prodotto (es: Passata 400g)"
            style={{ flex: 1, fontSize: 12, padding: '7px 10px', borderRadius: 8,
              border: `0.5px solid ${colors.border}`, background: colors.bg, color: colors.text }} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={url} onChange={e => setUrl(e.target.value)}
            placeholder="https://fornitore.it/prodotto/..."
            style={{ flex: 1, fontSize: 12, padding: '7px 10px', borderRadius: 8,
              border: `0.5px solid ${colors.border}`, background: colors.bg, color: colors.text }} />
          <button onClick={avviaScraping} disabled={loading || !url}
            style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall, opacity: loading ? 0.6 : 1 }}>
            {loading ? <Loader size={13} /> : <Globe size={13} />}
            {loading ? 'Scraping...' : 'Importa'}
          </button>
        </div>
        {msg && (
          <div style={{ marginTop: 8, fontSize: 12, padding: '6px 10px', borderRadius: 6,
            background: msg.ok ? colors.successBg : colors.dangerBg,
            color: msg.ok ? colors.successText : colors.dangerText }}>
            {msg.testo}
          </div>
        )}
      </div>

      {/* URL salvati */}
      {urls.map((u, i) => (
        <div key={i} style={{ ...s.card, marginBottom: 8, borderLeft: `3px solid ${
          u.stato === 'ok' ? colors.success :
          u.stato === 'errore' ? colors.danger : colors.warning}` }}>
          <div style={{ ...s.flexBetween, marginBottom: 8 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>{u.label}</div>
              <a href={u.url} target="_blank" rel="noreferrer"
                style={{ fontSize: 11, color: colors.primary }}>
                {u.url.length > 60 ? u.url.slice(0, 60) + '...' : u.url}
              </a>
            </div>
            <span style={{ fontSize: 10, color: colors.textLight }}>
              {u.stato === 'in_corso' ? '⏳ Scraping...' :
               u.stato === 'ok' ? '✅ OK' : '❌ Errore'}
            </span>
          </div>
          {u.dati_estratti && Object.keys(u.dati_estratti).length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {u.dati_estratti.prezzo_unitario != null && (
                <span style={{ ...s.badge(colors.successText, colors.successBg), fontSize: 10 }}>
                  €{u.dati_estratti.prezzo_unitario?.toFixed(2)}/pz
                </span>
              )}
              {u.dati_estratti.prezzo_cartone && (
                <span style={{ ...s.badge(colors.successText, colors.successBg), fontSize: 10 }}>
                  €{u.dati_estratti.prezzo_cartone?.toFixed(2)}/crt
                </span>
              )}
              {u.dati_estratti.pezzi_per_cartone && (
                <span style={{ ...s.badge(colors.infoText, colors.infoBg), fontSize: 10 }}>
                  {u.dati_estratti.pezzi_per_cartone} pz/crt
                </span>
              )}
              {u.dati_estratti.peso_prodotto_g && (
                <span style={{ ...s.badge(colors.infoText, colors.infoBg), fontSize: 10 }}>
                  {u.dati_estratti.peso_prodotto_g}g
                </span>
              )}
              {u.dati_estratti.ingredienti && (
                <span style={{ ...s.badge(colors.textMuted, colors.bg), fontSize: 10 }}>
                  Ingredienti ✓
                </span>
              )}
              {u.dati_estratti.immagini?.length > 0 && (
                <span style={{ ...s.badge(colors.textMuted, colors.bg), fontSize: 10 }}>
                  {u.dati_estratti.immagini.length} img
                </span>
              )}
            </div>
          )}
        </div>
      ))}

      {/* PDF tecnici */}
      <div style={{ ...s.card, marginTop: 12 }}>
        <div style={{ ...s.flexBetween, marginBottom: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: colors.text }}>PDF tecnici</div>
          <label style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, cursor: 'pointer' }}>
            <Upload size={12} /> Carica PDF
            <input type="file" accept=".pdf" multiple hidden
                   onChange={e => uploadPdf([...e.target.files])} />
          </label>
        </div>
        {pdfs.length === 0 ? (
          <div style={{ fontSize: 12, color: colors.textLight }}>Nessun PDF caricato</div>
        ) : pdfs.map((p, i) => (
          <div key={i} style={{ ...s.flex, gap: 8, padding: '7px 0',
            borderBottom: i < pdfs.length - 1 ? `0.5px solid ${colors.border}` : 'none' }}>
            <FileText size={14} color={colors.primary} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: colors.text }}>{p.filename}</div>
              <div style={{ fontSize: 10, color: colors.textLight }}>{p.tipo} · {p.caricato_il?.split('T')[0]}</div>
            </div>
            <a href={`${API}/${fornitore._id}/pdf/${p.filename}`} target="_blank"
               style={{ fontSize: 11, color: colors.primary }}>↓ Scarica</a>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Tab Lista Prodotti ───────────────────────────────── */
function TabProdotti({ prodotti }) {
  return prodotti.length === 0 ? (
    <div style={{ ...s.card, textAlign: 'center', color: colors.textLight }}>
      Nessun prodotto — importa una fattura XML per popolare
    </div>
  ) : (
    <div style={s.cardNoPad}>
      <table style={s.table}>
        <thead>
          <tr>
            <th style={s.th}>Codice</th>
            <th style={s.th}>Descrizione</th>
            <th style={s.th}>UM</th>
            <th style={{ ...s.th, textAlign: 'right' }}>Qtà totale</th>
            <th style={s.th}>Ultimo acquisto</th>
            <th style={{ ...s.th, textAlign: 'right' }}>Prezzo attuale</th>
            <th style={s.th}>Trend</th>
          </tr>
        </thead>
        <tbody>
          {prodotti.map((p, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? colors.bg + '40' : 'transparent' }}>
              <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 11 }}>
                {p.codice_articolo || '—'}
              </td>
              <td style={s.td}>{p.descrizione}</td>
              <td style={s.td}>{p.unita_misura}</td>
              <td style={{ ...s.td, textAlign: 'right' }}>
                {p.quantita_totale_acquistata?.toFixed(0)}
              </td>
              <td style={s.td}>{p.ultimo_acquisto}</td>
              <td style={{ ...s.td, textAlign: 'right', fontWeight: 700 }}>
                {p.prezzo_attuale ? formatEuro(p.prezzo_attuale) : '—'}
              </td>
              <td style={s.td}>
                {p.trend && <TrendBadge trend={p.trend} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Tab Listino / Storico ────────────────────────────── */
function TabListino({ storico }) {
  const [aperto, setAperto] = useState(null)
  return storico.length === 0 ? (
    <div style={{ ...s.card, textAlign: 'center', color: colors.textLight }}>
      Nessun dato — importa fatture XML per vedere il listino
    </div>
  ) : (
    <div>
      {storico.map((item, i) => (
        <div key={i} style={{ ...s.card, marginBottom: 8 }}>
          <div style={{ ...s.flexBetween, cursor: 'pointer' }}
               onClick={() => setAperto(aperto === i ? null : i)}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>
                {item.descrizione}
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted }}>
                {item.codice_articolo && `[${item.codice_articolo}] · `}
                {item.storico?.length} rilevazioni
              </div>
            </div>
            <div style={{ ...s.flex, gap: 10, alignItems: 'center' }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 15, fontWeight: 800, color: colors.primary }}>
                  {formatEuro(item.prezzo_attuale)}
                </div>
                <div style={{ fontSize: 10, color: colors.textLight }}>prezzo attuale</div>
              </div>
              <TrendBadge trend={item.trend} var_pct={item.variazione_pct} />
              {aperto === i ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </div>
          </div>

          {aperto === i && item.storico?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <table style={{ ...s.table, margin: 0 }}>
                <thead>
                  <tr>
                    <th style={s.th}>Data</th>
                    <th style={s.th}>Fattura</th>
                    <th style={{ ...s.th, textAlign: 'right' }}>Qtà</th>
                    <th style={{ ...s.th, textAlign: 'right' }}>Prezzo</th>
                    <th style={{ ...s.th, textAlign: 'right' }}>Sconto %</th>
                    <th style={{ ...s.th, textAlign: 'right' }}>Netto</th>
                  </tr>
                </thead>
                <tbody>
                  {[...item.storico].reverse().map((e, j) => (
                    <tr key={j}>
                      <td style={s.td}>{e.data}</td>
                      <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 11 }}>{e.numero_fattura}</td>
                      <td style={{ ...s.td, textAlign: 'right' }}>{e.quantita}</td>
                      <td style={{ ...s.td, textAlign: 'right' }}>{formatEuro(e.prezzo_unitario)}</td>
                      <td style={{ ...s.td, textAlign: 'right' }}>
                        {e.sconto_pct > 0 ? `${e.sconto_pct}%` : '—'}
                      </td>
                      <td style={{ ...s.td, textAlign: 'right', fontWeight: 700 }}>
                        {formatEuro(e.prezzo_netto)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/* ── Tab Pagamento ────────────────────────────────────── */
function TabPagamento({ fornitore, onRefresh }) {
  const pag = fornitore?.pagamento || {}
  const [metodo, setMetodo] = useState(pag.metodo || 'banca')
  const [conto, setConto] = useState(pag.conto_banca || '')
  const [iban, setIban] = useState(pag.iban_fornitore || '')
  const [termini, setTermini] = useState(pag.termini_pagamento || '')
  const [note, setNote] = useState(pag.note || '')
  const [salv, setSalv] = useState(false)

  const salva = async () => {
    await fetch(`${API}/${fornitore._id}/pagamento`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ metodo, conto_banca: conto, iban_fornitore: iban,
                             termini_pagamento: termini, note }),
    })
    setSalv(true)
    setTimeout(() => { setSalv(false); onRefresh() }, 1500)
  }

  const METODI = [
    { id: 'banca', label: '🏦 Bonifico bancario' },
    { id: 'cassa', label: '💵 Cassa contanti' },
    { id: 'carta', label: '💳 Carta di credito' },
    { id: 'assegno', label: '📝 Assegno' },
  ]

  return (
    <div>
      <div style={{ ...s.card, marginBottom: 12, background: colors.infoBg,
        border: `1px solid ${colors.info}30`, fontSize: 12, color: colors.infoText }}>
        Ogni nuova fattura di questo fornitore erediterà automaticamente il metodo selezionato
        per la riconciliazione contabile.
      </div>

      <div style={s.card}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 14, color: colors.text }}>
          Metodo di pagamento
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
          {METODI.map(m => (
            <button key={m.id} onClick={() => setMetodo(m.id)} style={{
              fontFamily: font, fontSize: 13, padding: '10px 14px', borderRadius: 10,
              border: `1.5px solid ${metodo === m.id ? colors.primary : colors.border}`,
              background: metodo === m.id ? colors.primaryBg : colors.bg,
              color: metodo === m.id ? colors.primary : colors.text,
              cursor: 'pointer', fontWeight: metodo === m.id ? 700 : 400,
              textAlign: 'left', transition: 'all .15s',
            }}>
              {m.label}
            </button>
          ))}
        </div>

        {metodo === 'banca' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <div>
              <div style={s.label}>Conto bancario</div>
              <input value={conto} onChange={e => setConto(e.target.value)}
                placeholder="Banco BPM c/c 00005462"
                style={{ width: '100%', padding: '7px 10px', borderRadius: 8, fontSize: 12,
                  border: `0.5px solid ${colors.border}`, background: colors.bg, color: colors.text }} />
            </div>
            <div>
              <div style={s.label}>IBAN fornitore</div>
              <input value={iban} onChange={e => setIban(e.target.value)}
                placeholder="IT60X..."
                style={{ width: '100%', padding: '7px 10px', borderRadius: 8, fontSize: 12,
                  border: `0.5px solid ${colors.border}`, background: colors.bg, color: colors.text }} />
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 10, marginBottom: 16 }}>
          <div>
            <div style={s.label}>Termini di pagamento</div>
            <input value={termini} onChange={e => setTermini(e.target.value)}
              placeholder="30gg, 60gg, ecc."
              style={{ width: '100%', padding: '7px 10px', borderRadius: 8, fontSize: 12,
                border: `0.5px solid ${colors.border}`, background: colors.bg, color: colors.text }} />
          </div>
          <div>
            <div style={s.label}>Note</div>
            <input value={note} onChange={e => setNote(e.target.value)}
              placeholder="Note aggiuntive..."
              style={{ width: '100%', padding: '7px 10px', borderRadius: 8, fontSize: 12,
                border: `0.5px solid ${colors.border}`, background: colors.bg, color: colors.text }} />
          </div>
        </div>

        <button onClick={salva} style={{ ...s.btn, ...s.btnPrimary, gap: 6 }}>
          {salv ? <Check size={14} /> : null}
          {salv ? 'Salvato!' : 'Salva metodo di pagamento'}
        </button>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   COMPONENTE PRINCIPALE
   ═══════════════════════════════════════════════════════ */
export default function Fornitori() {
  const [fornitori, setFornitori] = useState([])
  const [selezionato, setSelezionato] = useState(null)
  const [tab, setTab] = useState('anagrafica')
  const [prodotti, setProdotti] = useState([])
  const [storico, setStorico] = useState([])
  const [loading, setLoading] = useState(true)

  const carica = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}?stato=tutti`)
      const data = await res.json()
      setFornitori(Array.isArray(data) ? data : [])
    } catch {}
    setLoading(false)
  }

  const caricaDettagli = async (f) => {
    setSelezionato(f)
    setTab('anagrafica')
    const [p, l] = await Promise.all([
      fetch(`${API}/${f._id}/prodotti`).then(r => r.json()),
      fetch(`${API}/${f._id}/listino`).then(r => r.json()),
    ])
    setProdotti(Array.isArray(p) ? p : [])
    setStorico(Array.isArray(l) ? l : [])
  }

  const importaXml = async (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    await fetch(`${API}/import-xml`, { method: 'POST', body: fd })
    await carica()
  }

  const refreshFornitore = async () => {
    if (!selezionato) return
    const res = await fetch(`${API}/${selezionato._id}`)
    const f = await res.json()
    setSelezionato(f)
    const [p, l] = await Promise.all([
      fetch(`${API}/${f._id}/prodotti`).then(r => r.json()),
      fetch(`${API}/${f._id}/listino`).then(r => r.json()),
    ])
    setProdotti(Array.isArray(p) ? p : [])
    setStorico(Array.isArray(l) ? l : [])
    setFornitori(prev => prev.map(x => x._id === f._id ? f : x))
  }

  useEffect(() => { carica() }, [])

  const TABS = [
    { id: 'anagrafica', label: 'Anagrafica' },
    { id: 'schede', label: `Schede tecniche` },
    { id: 'prodotti', label: `Prodotti (${prodotti.length})` },
    { id: 'listino', label: `Listino (${storico.length})` },
    { id: 'pagamento', label: 'Pagamento' },
  ]

  return (
    <div style={s.page}>
      <div style={{ ...s.container, display: 'flex', gap: 20, alignItems: 'flex-start' }}>

        {/* ── Lista fornitori (sidebar) ── */}
        <div style={{ width: 280, flexShrink: 0 }}>
          <div style={{ ...s.flexBetween, marginBottom: 14 }}>
            <h1 style={{ ...s.h1, margin: 0 }}>Fornitori</h1>
            <label style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall, cursor: 'pointer' }}>
              <Upload size={12} /> XML
              <input type="file" accept=".xml" multiple hidden
                     onChange={e => importaXml([...e.target.files])} />
            </label>
          </div>

          {loading ? (
            <div style={{ color: colors.textLight, fontSize: 12, textAlign: 'center', padding: 20 }}>
              Caricamento...
            </div>
          ) : fornitori.length === 0 ? (
            <div style={{ ...s.card, textAlign: 'center', color: colors.textLight }}>
              Nessun fornitore — importa una fattura XML
            </div>
          ) : (
            <div>
              {fornitori.map(f => {
                const sel = selezionato?._id === f._id
                return (
                  <div key={f._id} onClick={() => caricaDettagli(f)} style={{
                    padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
                    marginBottom: 6, transition: 'all .15s',
                    background: sel ? colors.primaryBg : colors.bg,
                    border: `1px solid ${sel ? colors.primary : colors.border}`,
                  }}>
                    <div style={{ fontSize: 13, fontWeight: sel ? 700 : 500,
                      color: sel ? colors.primary : colors.text }}>
                      {f.anagrafica?.ragione_sociale || 'Fornitore senza nome'}
                    </div>
                    <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>
                      P.IVA {f.anagrafica?.piva || '—'} · {f.prodotti?.length || 0} prodotti
                    </div>
                    {f.pagamento?.metodo && (
                      <span style={{ ...s.badge(colors.infoText, colors.infoBg), fontSize: 9, marginTop: 4 }}>
                        {f.pagamento.metodo}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Dettaglio fornitore ── */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!selezionato ? (
            <div style={{ ...s.card, textAlign: 'center', color: colors.textLight, padding: 60 }}>
              <Building2 size={32} color={colors.textLight} style={{ margin: '0 auto 12px' }} />
              Seleziona un fornitore o importa una fattura XML
            </div>
          ) : (
            <div>
              {/* Header fornitore */}
              <div style={{ ...s.flexBetween, marginBottom: 16 }}>
                <div style={{ ...s.flex, gap: 12 }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12,
                    background: colors.primaryBg, display: 'flex',
                    alignItems: 'center', justifyContent: 'center' }}>
                    <Building2 size={20} color={colors.primary} />
                  </div>
                  <div>
                    <h2 style={{ ...s.h2, margin: 0 }}>
                      {selezionato.anagrafica?.ragione_sociale}
                    </h2>
                    <div style={{ fontSize: 12, color: colors.textMuted }}>
                      P.IVA {selezionato.anagrafica?.piva} · {selezionato.anagrafica?.n_fatture_totali || 0} fatture
                    </div>
                  </div>
                </div>
                <button onClick={refreshFornitore}
                  style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
                  <RefreshCw size={13} />
                </button>
              </div>

              {/* Tab bar */}
              <div style={{ ...s.flex, gap: 4, marginBottom: 16, flexWrap: 'wrap' }}>
                {TABS.map(t => (
                  <button key={t.id} onClick={() => setTab(t.id)} style={{
                    fontFamily: font, fontSize: 12, fontWeight: 600,
                    padding: '6px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                    background: tab === t.id
                      ? `linear-gradient(135deg, ${colors.primary} 0%, ${colors.primaryLight} 100%)`
                      : colors.bg,
                    color: tab === t.id ? '#fff' : colors.textMuted,
                    boxShadow: tab === t.id ? shadow.btn : 'none',
                  }}>{t.label}</button>
                ))}
              </div>

              {/* Contenuto tab */}
              {tab === 'anagrafica' && <TabAnagrafica fornitore={selezionato} />}
              {tab === 'schede' && <TabSchede fornitore={selezionato} onRefresh={refreshFornitore} />}
              {tab === 'prodotti' && <TabProdotti prodotti={prodotti} />}
              {tab === 'listino' && <TabListino storico={storico} />}
              {tab === 'pagamento' && <TabPagamento fornitore={selezionato} onRefresh={refreshFornitore} />}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
