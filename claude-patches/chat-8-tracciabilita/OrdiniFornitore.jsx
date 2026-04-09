/**
 * OrdiniFornitore.jsx — Sistema Ordini Ceraldi ERP
 *
 * Flusso:
 *  1. Operatore: seleziona prodotti dal catalogo → invia bozza
 *  2. Admin: rivede l'ordine, vede comparazione prezzi, modifica, approva
 *  3. Admin: genera testo e invia via email o WhatsApp al fornitore
 *
 * API usate (gestionale2 backend):
 *  GET /api/ordini/catalogo?search=...    → catalogo prodotti con prezzi fornitori
 *  GET /api/ordini/prezzi/{nome}          → comparazione prezzi per prodotto
 *  GET /api/ordini                        → lista ordini (admin)
 *  POST /api/ordini                       → crea bozza (operatore)
 *  PUT /api/ordini/{id}                   → modifica/approva (admin)
 *  DELETE /api/ordini/{id}                → elimina
 *  GET /api/ordini/{id}/testo-invio?fornitore=X → genera testo ordine
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  ShoppingCart, Search, Plus, Minus, Send, Check, X, RefreshCw,
  ChevronDown, ChevronUp, Building2, Mail, MessageSquare,
  Edit, Trash2, Package, TrendingDown, Clock, Users,
  Copy, ExternalLink, AlertTriangle, Star
} from 'lucide-react'
import { s, colors, font, formatEuro } from '../lib/utils'

const API = '/api'
const HACCP_API = '/api/tr'

const REPARTI = ['Pasticceria', 'Rosticceria', 'Bar', 'Deposito', 'Cucina']
const STATI_COLOR = {
  bozza:      { bg: colors.warningBg,  text: colors.warningText  },
  approvato:  { bg: colors.primaryBg,  text: colors.primaryText  },
  inviato:    { bg: colors.successBg,  text: colors.successText  },
  completato: { bg: colors.bg,         text: colors.textMuted    },
}

// ─── UTILS ───────────────────────────────────────────────────────────────────
function copia(testo) {
  navigator.clipboard?.writeText(testo).catch(() => {})
}

// ─── MODAL COMPARAZIONE PREZZI ────────────────────────────────────────────────
function ModalPrezzi({ nomeProdotto, onClose, onScegli }) {
  const [dati, setDati] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/ordini/prezzi/${encodeURIComponent(nomeProdotto)}`)
      .then(r => r.json())
      .then(setDati)
      .catch(() => setDati({ risultati: [] }))
      .finally(() => setLoading(false))
  }, [nomeProdotto])

  return (
    <div onClick={e => e.target === e.currentTarget && onClose()} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
    }}>
      <div style={{
        background: colors.card, borderRadius: 16, width: '100%', maxWidth: 540,
        maxHeight: '85vh', overflowY: 'auto', fontFamily: font,
        boxShadow: '0 20px 60px rgba(0,0,0,0.2)'
      }}>
        <div style={{ ...s.flexBetween, padding: '16px 20px', borderBottom: `1px solid ${colors.border}`, position: 'sticky', top: 0, background: colors.card }}>
          <div>
            <span style={{ fontWeight: 700, fontSize: 14 }}>Comparazione Prezzi</span>
            <div style={{ ...s.caption, marginTop: 2 }}>{nomeProdotto}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={18}/></button>
        </div>

        <div style={{ padding: 16 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>
              <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
              <p style={{ marginTop: 8 }}>Analisi fatture in corso...</p>
            </div>
          ) : !dati?.risultati?.length ? (
            <div style={{ textAlign: 'center', padding: 32, color: colors.textMuted }}>
              <Package size={28} style={{ opacity: 0.3, margin: '0 auto 8px', display: 'block' }} />
              <p>Nessuna fattura trovata per questo prodotto.</p>
              <p style={s.caption}>Il sistema ha analizzato le ultime fatture di tutti i fornitori.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {dati.risultati.map((r, i) => (
                <div
                  key={i}
                  onClick={() => { onScegli(r.fornitore, r.prezzo_medio_ultime_fatture, r.unita_misura); onClose() }}
                  style={{
                    border: `2px solid ${r.e_il_migliore ? colors.success : colors.border}`,
                    borderRadius: 12, padding: '12px 14px', cursor: 'pointer',
                    background: r.e_il_migliore ? colors.successBg : colors.card,
                    transition: 'border-color .15s',
                  }}
                >
                  <div style={s.flexBetween}>
                    <div style={s.flex}>
                      {r.e_il_migliore && <Star size={14} color={colors.success} style={{ marginRight: 6, flexShrink: 0 }} />}
                      <span style={{ fontWeight: 700, fontSize: 13 }}>{r.fornitore}</span>
                    </div>
                    <span style={{ fontSize: 18, fontWeight: 900, color: r.e_il_migliore ? colors.success : colors.primary }}>
                      €{r.prezzo_medio_ultime_fatture.toFixed(4)}/{r.unita_misura || 'u'}
                    </span>
                  </div>
                  <div style={{ ...s.flex, gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
                    <span style={s.caption}>{r.descrizione_fattura}</span>
                    <span style={s.caption}>·</span>
                    <span style={s.caption}>{r.num_fatture} fatture analizzate</span>
                    {r.ultima_data && <span style={s.caption}>· ultima: {r.ultima_data}</span>}
                  </div>
                  {r.e_il_migliore && (
                    <div style={{ marginTop: 6 }}>
                      <span style={s.badge(colors.successText, colors.successBg)}>⭐ Prezzo migliore</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── MODAL TESTO INVIO ────────────────────────────────────────────────────────
function ModalInvio({ ordineId, fornitore, onClose }) {
  const [dati, setDati] = useState(null)
  const [loading, setLoading] = useState(true)
  const [copiato, setCopiato] = useState(false)

  useEffect(() => {
    fetch(`${API}/ordini/${ordineId}/testo-invio?fornitore=${encodeURIComponent(fornitore)}`)
      .then(r => r.json())
      .then(setDati)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [ordineId, fornitore])

  const copiaTesto = (testo) => {
    copia(testo)
    setCopiato(true)
    setTimeout(() => setCopiato(false), 2000)
  }

  const apriEmail = () => {
    if (!dati) return
    const mailto = `mailto:${dati.email_fornitore}?subject=${encodeURIComponent(dati.oggetto)}&body=${encodeURIComponent(dati.corpo)}`
    window.open(mailto)
  }

  const apriWhatsApp = () => {
    if (!dati) return
    const wa = `https://wa.me/?text=${encodeURIComponent(dati.whatsapp_testo)}`
    window.open(wa)
  }

  return (
    <div onClick={e => e.target === e.currentTarget && onClose()} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
    }}>
      <div style={{
        background: colors.card, borderRadius: 16, width: '100%', maxWidth: 580,
        maxHeight: '90vh', overflowY: 'auto', fontFamily: font,
        boxShadow: '0 20px 60px rgba(0,0,0,0.2)'
      }}>
        <div style={{ ...s.flexBetween, padding: '16px 20px', borderBottom: `1px solid ${colors.border}`, position: 'sticky', top: 0, background: colors.card }}>
          <div>
            <span style={{ fontWeight: 700, fontSize: 14 }}>Invia Ordine — {fornitore}</span>
            {dati?.email_fornitore && <div style={s.caption}>{dati.email_fornitore}</div>}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={18}/></button>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        ) : dati ? (
          <div style={{ padding: 20 }}>
            {/* Pulsanti azione */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
              <button onClick={apriEmail} style={{ ...s.btn, ...s.btnPrimary, justifyContent: 'center' }}>
                <Mail size={16}/> Apri in Mail
              </button>
              <button onClick={apriWhatsApp} style={{ ...s.btn, background: '#25D366', color: '#fff', justifyContent: 'center', borderRadius: 10 }}>
                <MessageSquare size={16}/> Apri WhatsApp
              </button>
            </div>

            {/* Oggetto */}
            <div style={{ marginBottom: 12 }}>
              <label style={s.label}>Oggetto email</label>
              <div style={{ ...s.flex, gap: 8 }}>
                <div style={{ ...s.input, flex: 1, fontSize: 13, padding: '8px 12px', background: colors.bg }}>
                  {dati.oggetto}
                </div>
                <button onClick={() => copiaTesto(dati.oggetto)} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
                  <Copy size={13}/>
                </button>
              </div>
            </div>

            {/* Testo */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ ...s.flexBetween, marginBottom: 6 }}>
                <label style={{ ...s.label, marginBottom: 0 }}>Testo ordine</label>
                <button onClick={() => copiaTesto(dati.corpo)} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
                  {copiato ? <><Check size={12}/> Copiato</> : <><Copy size={12}/> Copia</>}
                </button>
              </div>
              <pre style={{
                background: colors.bg, borderRadius: 10, padding: 14,
                fontSize: 12, fontFamily: font, whiteSpace: 'pre-wrap',
                border: `1px solid ${colors.border}`, maxHeight: 300, overflowY: 'auto',
                color: colors.text, margin: 0, lineHeight: 1.6
              }}>{dati.corpo}</pre>
            </div>

            {/* Info contatto */}
            {dati.telefono_fornitore && (
              <div style={{ ...s.flex, gap: 8, padding: '8px 12px', background: colors.bg, borderRadius: 8 }}>
                <span style={s.caption}>Tel: {dati.telefono_fornitore}</span>
              </div>
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 32, color: colors.textMuted }}>
            Errore caricamento testo ordine
          </div>
        )}
      </div>
    </div>
  )
}

// ─── VISTA OPERATORE ──────────────────────────────────────────────────────────
function VistaOperatore({ onOrdineSalvato }) {
  const [catalogo, setCatalogo] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [searchDebounced, setSearchDebounced] = useState('')
  const [righe, setRighe] = useState([])   // { nome, quantita, unita, note }
  const [reparto, setReparto] = useState('Deposito')
  const [operatore, setOperatore] = useState('')
  const [noteOrdine, setNoteOrdine] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [modalPrezzi, setModalPrezzi] = useState(null) // nome prodotto

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setSearchDebounced(search), 350)
    return () => clearTimeout(t)
  }, [search])

  const fetchCatalogo = useCallback(async () => {
    setLoading(true)
    try {
      const url = `${HACCP_API}/ordini-fornitori/prodotti-suggeriti?limit=700`
      const d = await fetch(url).then(r => r.json())
      // Adatta struttura: tracciabilita ritorna array piatto
      const lista = (d || []).map(p => ({
        nome: p.nome || p.nome_normalizzato || '',
        fornitore_migliore: p.fornitore || '',
        prezzo_migliore: p.prezzo_kg || 0,
        unita: p.unita_confezione || 'kg',
        peso_confezione: p.peso_confezione || 1,
        foto_url: p.foto_url || null,
        sotto_scorta: p.sotto_scorta || false,
        fornitori: p.fornitore ? [{ fornitore: p.fornitore, prezzo_medio: p.prezzo_kg, unita_misura: p.unita_confezione || 'kg' }] : [],
      }))
      setCatalogo(lista)
    } catch {}
    setLoading(false)
  }, [searchDebounced])

  useEffect(() => { fetchCatalogo() }, [fetchCatalogo])

  const aggiungiProdotto = (nome, unita = 'kg', quantita = 1) => {
    setRighe(prev => {
      const idx = prev.findIndex(r => r.nome.toLowerCase() === nome.toLowerCase())
      if (idx >= 0) {
        const n = [...prev]
        n[idx] = { ...n[idx], quantita: n[idx].quantita + quantita }
        return n
      }
      return [...prev, { nome, quantita, unita, note: '', fornitore_selezionato: '' }]
    })
  }

  const rimuoviRiga = (i) => setRighe(prev => prev.filter((_, j) => j !== i))
  const aggiornaQty = (i, v) => setRighe(prev => { const n=[...prev]; n[i]={...n[i],quantita:Math.max(0.1,v)}; return n })
  const aggiornaNota = (i, v) => setRighe(prev => { const n=[...prev]; n[i]={...n[i],note:v}; return n })

  const salvaOrdine = async () => {
    if (!righe.length) return
    setSalvando(true)
    try {
      const res = await fetch(`${API}/ordini`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operatore, reparto, righe, note: noteOrdine })
      }).then(r => r.json())
      onOrdineSalvato(res.ordine)
    } catch {}
    setSalvando(false)
  }

  return (
    <div>
      {modalPrezzi && (
        <ModalPrezzi
          nomeProdotto={modalPrezzi}
          onClose={() => setModalPrezzi(null)}
          onScegli={(forn, prezzo, unita) => {
            // Trova la riga corrispondente e aggiorna fornitore
            setRighe(prev => prev.map(r =>
              r.nome.toLowerCase() === modalPrezzi.toLowerCase()
                ? { ...r, fornitore_selezionato: forn }
                : r
            ))
          }}
        />
      )}

      {/* Header operatore */}
      <div style={{ ...s.card, marginBottom: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <div>
            <label style={s.label}>Chi sei?</label>
            <input value={operatore} onChange={e => setOperatore(e.target.value)}
              placeholder="Es. Mario (pasticcere)" style={s.input} />
          </div>
          <div>
            <label style={s.label}>Reparto</label>
            <select value={reparto} onChange={e => setReparto(e.target.value)} style={{ ...s.select, width: '100%' }}>
              {REPARTI.map(r => <option key={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={s.label}>Note</label>
            <input value={noteOrdine} onChange={e => setNoteOrdine(e.target.value)}
              placeholder="Es. Urgente entro venerdì" style={s.input} />
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 16, alignItems: 'start' }}>
        {/* Catalogo prodotti */}
        <div>
          <div style={{ ...s.flex, gap: 10, marginBottom: 12 }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search size={15} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: colors.textLight }} />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Cerca: farina, caffè, burro..."
                style={{ ...s.input, paddingLeft: 36 }} />
            </div>
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: colors.textMuted }}>
              <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: '65vh', overflowY: 'auto' }}>
              {catalogo.map((prod, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '10px 14px', borderRadius: 10,
                    border: `1px solid ${colors.border}`, background: colors.card,
                    cursor: 'pointer', transition: 'border-color .15s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = colors.primary}
                  onMouseLeave={e => e.currentTarget.style.borderColor = colors.border}
                  onClick={() => aggiungiProdotto(prod.nome, prod.unita || 'kg', prod.peso_confezione || 1)}
                >
                  <div style={{
                    width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                    background: colors.primaryBg, display: 'flex', alignItems: 'center', justifyContent: 'center'
                  }}>
                    <Package size={16} color={colors.primary} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, textTransform: 'capitalize',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {prod.nome}
                    </div>
                    <div style={{ ...s.caption, marginTop: 2 }}>
                      {prod.fornitore_migliore && (
                        <span style={{ color: colors.success, fontWeight: 600 }}>
                          ⭐ {prod.fornitore_migliore} — €{prod.prezzo_migliore.toFixed(4)}/u
                        </span>
                      )}
                      {prod.fornitori.length > 1 && (
                        <span style={{ color: colors.textLight, marginLeft: 8 }}>
                          +{prod.fornitori.length - 1} fornitore{prod.fornitori.length > 2 ? 'i' : ''}
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ flexShrink: 0, ...s.flex, gap: 6 }}>
                    {prod.fornitori.length > 1 && (
                      <button
                        onClick={e => { e.stopPropagation(); setModalPrezzi(prod.nome) }}
                        style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, padding: '4px 8px' }}
                        title="Confronta prezzi fornitori"
                      >
                        <TrendingDown size={13}/> Prezzi
                      </button>
                    )}
                    <button
                      onClick={e => { e.stopPropagation(); aggiungiProdotto(prod.nome, prod.unita || 'kg', prod.peso_confezione || 1) }}
                      style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall, padding: '4px 10px' }}
                    >
                      <Plus size={14}/>
                    </button>
                  </div>
                </div>
              ))}
              {catalogo.length === 0 && !loading && (
                <div style={{ textAlign: 'center', padding: 32, color: colors.textMuted }}>
                  {search ? `Nessun prodotto trovato per "${search}"` : 'Nessun prodotto nel catalogo'}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Carrello ordine */}
        <div style={{ position: 'sticky', top: 20 }}>
          <div style={s.card}>
            <h2 style={{ ...s.h2, ...s.flex, gap: 8 }}>
              <ShoppingCart size={17} color={colors.primary} /> Il tuo ordine
              {righe.length > 0 && <span style={s.badge(colors.primaryText, colors.primaryBg)}>{righe.length}</span>}
            </h2>

            {righe.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24, color: colors.textLight }}>
                <ShoppingCart size={24} style={{ opacity: 0.3, margin: '0 auto 8px', display: 'block' }} />
                <p style={s.caption}>Clicca sui prodotti per aggiungerli</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
                {righe.map((riga, i) => (
                  <div key={i} style={{ border: `1px solid ${colors.border}`, borderRadius: 10, padding: '10px 12px' }}>
                    <div style={{ ...s.flexBetween, marginBottom: 6 }}>
                      <span style={{ fontWeight: 600, fontSize: 13, textTransform: 'capitalize' }}>{riga.nome}</span>
                      <button onClick={() => rimuoviRiga(i)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.danger, padding: 2 }}>
                        <X size={14}/>
                      </button>
                    </div>
                    <div style={{ ...s.flex, gap: 6, marginBottom: 6 }}>
                      <button onClick={() => aggiornaQty(i, riga.quantita - (riga.unita === 'kg' ? 1 : 1))}
                        style={{ ...s.btn, ...s.btnNeutral, width: 28, height: 28, padding: 0, justifyContent: 'center' }}>
                        <Minus size={12}/>
                      </button>
                      <input type="number" min="0.1" step="0.5" value={riga.quantita}
                        onChange={e => aggiornaQty(i, parseFloat(e.target.value) || 0.1)}
                        style={{ ...s.input, width: 60, textAlign: 'center', padding: '4px 8px', fontSize: 13 }} />
                      <span style={{ ...s.caption, minWidth: 24 }}>{riga.unita}</span>
                      <button onClick={() => aggiornaQty(i, riga.quantita + (riga.unita === 'kg' ? 1 : 1))}
                        style={{ ...s.btn, ...s.btnNeutral, width: 28, height: 28, padding: 0, justifyContent: 'center' }}>
                        <Plus size={12}/>
                      </button>
                    </div>
                    <div style={{ ...s.flex, gap: 6 }}>
                      <input value={riga.note} onChange={e => aggiornaNota(i, e.target.value)}
                        placeholder="Note (opzionale)" style={{ ...s.input, fontSize: 11, padding: '4px 8px', flex: 1 }} />
                      <button onClick={() => setModalPrezzi(riga.nome)}
                        title="Confronta prezzi" style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, padding: '4px 8px' }}>
                        <TrendingDown size={12}/>
                      </button>
                    </div>
                    {riga.fornitore_selezionato && (
                      <div style={{ marginTop: 4 }}>
                        <span style={s.badge(colors.successText, colors.successBg)}>
                          <Building2 size={10} style={{ marginRight: 3 }} />{riga.fornitore_selezionato}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={salvaOrdine}
              disabled={salvando || !righe.length}
              style={{
                ...s.btn, ...s.btnPrimary, width: '100%', justifyContent: 'center',
                opacity: !righe.length ? 0.5 : 1,
              }}
            >
              {salvando ? <RefreshCw size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={15}/>}
              {salvando ? 'Salvataggio...' : `Invia ordine (${righe.length} prodotti)`}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── VISTA ADMIN ──────────────────────────────────────────────────────────────
function VistaAdmin() {
  const [ordini, setOrdini] = useState([])
  const [loading, setLoading] = useState(true)
  const [filtroStato, setFiltroStato] = useState('tutti')
  const [espanso, setEspanso] = useState(null)
  const [modalInvio, setModalInvio] = useState(null)  // { ordineId, fornitore }
  const [modalPrezzi, setModalPrezzi] = useState(null)

  const fetchOrdini = useCallback(async () => {
    setLoading(true)
    try {
      const url = `${API}/ordini${filtroStato !== 'tutti' ? `?stato=${filtroStato}` : ''}`
      const d = await fetch(url).then(r => r.json())
      setOrdini(d || [])
    } catch {}
    setLoading(false)
  }, [filtroStato])

  useEffect(() => { fetchOrdini() }, [fetchOrdini])

  const cambiaStato = async (id, stato) => {
    await fetch(`${API}/ordini/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stato })
    })
    fetchOrdini()
  }

  const eliminaOrdine = async (id) => {
    if (!window.confirm('Eliminare questo ordine?')) return
    await fetch(`${API}/ordini/${id}`, { method: 'DELETE' })
    fetchOrdini()
  }

  // Raggruppa righe per fornitore
  const fornitoreDaRighe = (righe) => {
    const map = {}
    for (const r of righe) {
      const f = r.fornitore_selezionato || '—'
      if (!map[f]) map[f] = []
      map[f].push(r)
    }
    return map
  }

  return (
    <div>
      {modalPrezzi && (
        <ModalPrezzi nomeProdotto={modalPrezzi} onClose={() => setModalPrezzi(null)}
          onScegli={() => {}} />
      )}
      {modalInvio && (
        <ModalInvio ordineId={modalInvio.ordineId} fornitore={modalInvio.fornitore}
          onClose={() => setModalInvio(null)} />
      )}

      {/* Filtri */}
      <div style={{ ...s.flex, gap: 6, marginBottom: 16 }}>
        {['tutti', 'bozza', 'approvato', 'inviato', 'completato'].map(stato => (
          <button key={stato} onClick={() => setFiltroStato(stato)}
            style={{
              ...s.btn, ...s.btnSmall,
              background: filtroStato === stato ? colors.primary : colors.bg,
              color: filtroStato === stato ? '#fff' : colors.textMuted,
              border: `1px solid ${filtroStato === stato ? colors.primary : colors.border}`,
              textTransform: 'capitalize',
            }}>
            {stato === 'tutti' ? 'Tutti' : stato}
          </button>
        ))}
        <button onClick={fetchOrdini} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, marginLeft: 'auto' }}>
          <RefreshCw size={13} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: colors.textMuted }}>
          <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite' }} />
        </div>
      ) : ordini.length === 0 ? (
        <div style={{ ...s.card, textAlign: 'center', padding: 60, color: colors.textMuted }}>
          <ShoppingCart size={32} style={{ opacity: 0.3, margin: '0 auto 12px', display: 'block' }} />
          <p>Nessun ordine trovato</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {ordini.map(ordine => {
            const aperto = espanso === ordine.id
            const colori = STATI_COLOR[ordine.stato] || STATI_COLOR.bozza
            const forniMap = fornitoreDaRighe(ordine.righe || [])
            const fornitori = Object.keys(forniMap).filter(f => f !== '—')

            return (
              <div key={ordine.id} style={{ ...s.cardNoPad, overflow: 'hidden' }}>
                {/* Header ordine */}
                <div
                  style={{ ...s.flexBetween, padding: '14px 16px', cursor: 'pointer', flexWrap: 'wrap', gap: 8 }}
                  onClick={() => setEspanso(aperto ? null : ordine.id)}
                >
                  <div style={s.flex}>
                    {aperto ? <ChevronUp size={16} color={colors.textMuted}/> : <ChevronDown size={16} color={colors.textMuted}/>}
                    <div style={{ marginLeft: 10 }}>
                      <div style={{ ...s.flex, gap: 8, flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, fontSize: 14 }}>
                          {ordine.reparto || 'Ordine'} — {ordine.operatore || 'Staff'}
                        </span>
                        <span style={s.badge(colori.text, colori.bg)}>{ordine.stato}</span>
                        <span style={s.badge(colors.textMuted, colors.borderLight)}>
                          {(ordine.righe || []).length} prodotti
                        </span>
                      </div>
                      <div style={{ ...s.caption, marginTop: 3 }}>
                        <Clock size={11} style={{ marginRight: 4 }} />
                        {new Date(ordine.created_at).toLocaleString('it-IT')}
                        {ordine.note && ` · ${ordine.note}`}
                      </div>
                    </div>
                  </div>

                  <div style={{ ...s.flex, gap: 6 }} onClick={e => e.stopPropagation()}>
                    {ordine.stato === 'bozza' && (
                      <button onClick={() => cambiaStato(ordine.id, 'approvato')}
                        style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall }}>
                        <Check size={13}/> Approva
                      </button>
                    )}
                    {(ordine.stato === 'approvato' || ordine.stato === 'inviato') && fornitori.length > 0 && (
                      fornitori.map(f => (
                        <button key={f} onClick={() => setModalInvio({ ordineId: ordine.id, fornitore: f })}
                          style={{ ...s.btn, background: colors.success, color: '#fff', ...s.btnSmall }}>
                          <Send size={13}/> Invia a {f.split(' ')[0]}
                        </button>
                      ))
                    )}
                    {ordine.stato === 'approvato' && fornitori.length === 0 && (
                      <button onClick={() => setModalInvio({ ordineId: ordine.id, fornitore: 'Fornitore' })}
                        style={{ ...s.btn, background: colors.success, color: '#fff', ...s.btnSmall }}>
                        <Send size={13}/> Genera Testo
                      </button>
                    )}
                    {ordine.stato !== 'completato' && (
                      <button onClick={() => cambiaStato(ordine.id, 'completato')}
                        style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
                        <Check size={13}/>
                      </button>
                    )}
                    <button onClick={() => eliminaOrdine(ordine.id)}
                      style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, color: colors.danger }}>
                      <Trash2 size={13}/>
                    </button>
                  </div>
                </div>

                {/* Dettaglio espanso */}
                {aperto && (
                  <div style={{ borderTop: `1px solid ${colors.border}`, padding: '12px 16px' }}>
                    {/* Per fornitore */}
                    {Object.entries(forniMap).map(([forn, righe]) => (
                      <div key={forn} style={{ marginBottom: 12 }}>
                        <div style={{ ...s.flex, gap: 8, marginBottom: 6 }}>
                          <Building2 size={14} color={colors.primary} />
                          <span style={{ fontWeight: 700, fontSize: 13, color: colors.primary }}>{forn}</span>
                          {forn !== '—' && (
                            <button onClick={() => setModalInvio({ ordineId: ordine.id, fornitore: forn })}
                              style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, padding: '2px 8px', fontSize: 11 }}>
                              <Send size={11}/> Invia
                            </button>
                          )}
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          {righe.map((r, i) => (
                            <div key={i} style={{ ...s.flexBetween, padding: '6px 10px', background: colors.bg, borderRadius: 8 }}>
                              <span style={{ fontSize: 13, textTransform: 'capitalize' }}>{r.nome}</span>
                              <div style={s.flex}>
                                {r.note && <span style={{ ...s.caption, marginRight: 10, fontStyle: 'italic' }}>{r.note}</span>}
                                <span style={{ fontWeight: 700, fontSize: 13 }}>{r.quantita} {r.unita}</span>
                                <button onClick={() => setModalPrezzi(r.nome)} title="Confronta prezzi"
                                  style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, padding: '2px 6px', marginLeft: 6 }}>
                                  <TrendingDown size={11}/>
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── PAGINA PRINCIPALE ────────────────────────────────────────────────────────
export default function OrdiniFornitore() {
  const [vista, setVista] = useState('operatore') // operatore | admin
  const [confermaSalvato, setConfermaSalvato] = useState(null)

  const handleOrdineSalvato = (ordine) => {
    setConfermaSalvato(ordine)
  }

  if (confermaSalvato) {
    return (
      <div style={{ maxWidth: 500, margin: '40px auto', fontFamily: font }}>
        <div style={{ ...s.card, textAlign: 'center', background: colors.successBg, borderColor: colors.success }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>✅</div>
          <h2 style={{ ...s.h1, color: colors.successText }}>Ordine inviato!</h2>
          <p style={{ ...s.caption, marginTop: 8 }}>
            L'amministratore riceverà l'ordine e lo approverà prima dell'invio al fornitore.
          </p>
          <div style={{ marginTop: 16, ...s.flex, gap: 10, justifyContent: 'center' }}>
            <button onClick={() => setConfermaSalvato(null)}
              style={{ ...s.btn, ...s.btnPrimary }}>
              Nuovo ordine
            </button>
            <button onClick={() => { setConfermaSalvato(null); setVista('admin') }}
              style={{ ...s.btn, ...s.btnNeutral }}>
              Vai all'admin
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ fontFamily: font }}>
      {/* Header */}
      <div style={{ ...s.flexBetween, marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.h1}>
            <ShoppingCart size={22} style={{ marginRight: 8, color: colors.primary, verticalAlign: 'middle' }} />
            Ordini Fornitori
          </h1>
          <p style={{ ...s.caption, marginTop: 4 }}>
            {vista === 'operatore'
              ? 'Seleziona i prodotti da ordinare — il sistema troverà il prezzo migliore'
              : 'Gestione ordini — approva e invia ai fornitori'
            }
          </p>
        </div>
        <div style={{ ...s.flex, gap: 6 }}>
          <button onClick={() => setVista('operatore')}
            style={{
              ...s.btn, ...s.btnSmall,
              background: vista === 'operatore' ? colors.primary : colors.bg,
              color: vista === 'operatore' ? '#fff' : colors.textMuted,
              border: `1px solid ${vista === 'operatore' ? colors.primary : colors.border}`,
            }}>
            <Users size={14}/> Operatore
          </button>
          <button onClick={() => setVista('admin')}
            style={{
              ...s.btn, ...s.btnSmall,
              background: vista === 'admin' ? colors.primary : colors.bg,
              color: vista === 'admin' ? '#fff' : colors.textMuted,
              border: `1px solid ${vista === 'admin' ? colors.primary : colors.border}`,
            }}>
            <Edit size={14}/> Admin
          </button>
        </div>
      </div>

      {vista === 'operatore'
        ? <VistaOperatore onOrdineSalvato={handleOrdineSalvato} />
        : <VistaAdmin />
      }

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
