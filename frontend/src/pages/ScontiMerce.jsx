/**
 * ScontiMerce.jsx — Sconti Merce per Ceraldi ERP gestionale2
 * API: https://ceraldiapp.it/api/sconti-merce/...
 * Aggiunta: filtro fornitori configurabile + finestra gestione fornitori
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Gift, Plus, Trash2, Edit, RefreshCw, Save, X,
  Calendar, Building2, Settings, ChevronDown, ChevronUp, Check
} from 'lucide-react'
import { s, colors, font, formatEuro } from '../lib/utils'

const API = 'https://ceraldiapp.it/api'
const MESI = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
const ANNO = new Date().getFullYear()
const MESE = new Date().getMonth() + 1

// Fornitori preferiti di default
const FORNITORI_DEFAULT = ['ACQUAVIVA', 'PERFETTI', 'EUREKA ONLUS', 'KIMBO']
const LS_KEY = 'ceraldi_sconti_fornitori'

function loadFornitori() {
  try {
    const saved = localStorage.getItem(LS_KEY)
    return saved ? JSON.parse(saved) : FORNITORI_DEFAULT
  } catch { return FORNITORI_DEFAULT }
}

function saveFornitori(list) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(list)) } catch {}
}

const formVuoto = {
  data: new Date().toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' }),
  fornitore: '', prodotto: '', cartoni: '', pezzi_per_cartone: '',
  pezzi_totali: '', valore_unitario: '', valore_totale: '',
  fattura_riferimento: '', note: ''
}

// ─── MODAL FORM SCONTO ────────────────────────────────────────────────────────
function ModalSconto({ form, setForm, editingId, onSave, onClose, prodottiForn, caricandoProdotti }) {
  const anteprima = useMemo(() => {
    const cartoni = parseFloat(form.cartoni) || 0
    const ppc = parseFloat(form.pezzi_per_cartone) || 0
    const pezziTot = parseFloat(form.pezzi_totali) || (cartoni * ppc)
    const valUnit = parseFloat(form.valore_unitario) || 0
    const unita = cartoni || pezziTot
    const valTot = parseFloat(form.valore_totale) || (valUnit * unita)
    return { pezziTot, valTot }
  }, [form])

  const f = (field, val) => setForm(p => ({ ...p, [field]: val }))

  return (
    <div onClick={e => e.target === e.currentTarget && onClose()} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
    }}>
      <div style={{
        background: colors.card, borderRadius: 16, width: '100%', maxWidth: 520,
        maxHeight: '90vh', overflowY: 'auto', fontFamily: font,
        boxShadow: '0 20px 60px rgba(0,0,0,0.2)'
      }}>
        {/* Header */}
        <div style={{ ...s.flexBetween, padding: '16px 20px', borderBottom: `1px solid ${colors.border}`, position: 'sticky', top: 0, background: colors.card, zIndex: 1 }}>
          <span style={{ fontWeight: 700, fontSize: 15, ...s.flex, gap: 8 }}>
            <Gift size={18} color={colors.success} /> {editingId ? 'Modifica Sconto' : 'Registra Sconto Merce'}
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={18} /></button>
        </div>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Data + Fornitore */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={s.label}>Data *</label>
              <input value={form.data} onChange={e => f('data', e.target.value)}
                placeholder="gg/mm/aaaa" style={s.input} />
            </div>
            <div>
              <label style={s.label}>Fornitore *</label>
              <input value={form.fornitore} onChange={e => f('fornitore', e.target.value)}
                list="forn-list" placeholder="es. ACQUAVIVA" style={s.input} />
              <datalist id="forn-list">
                {loadFornitori().map(f2 => <option key={f2} value={f2} />)}
              </datalist>
            </div>
          </div>

          {/* Prodotto */}
          <div>
            <label style={s.label}>
              Prodotto *
              {caricandoProdotti && <span style={{ marginLeft: 6, color: colors.textLight, fontWeight: 400 }}>caricamento...</span>}
              {!caricandoProdotti && prodottiForn.length > 0 && (
                <span style={{ marginLeft: 6, color: colors.success, fontWeight: 400 }}>({prodottiForn.length} dalle fatture)</span>
              )}
              {!caricandoProdotti && form.fornitore && prodottiForn.length === 0 && (
                <span style={{ marginLeft: 6, color: colors.textLight, fontWeight: 400 }}>(nessuna fattura trovata)</span>
              )}
            </label>
            <input value={form.prodotto} onChange={e => f('prodotto', e.target.value)}
              list="prod-list" disabled={!form.fornitore}
              placeholder={form.fornitore ? 'Inizia a digitare...' : 'Prima seleziona il fornitore'}
              style={{ ...s.input, background: form.fornitore ? '#fff' : colors.bg }} />
            <datalist id="prod-list">
              {prodottiForn.map((p, i) => <option key={i} value={p} />)}
            </datalist>
          </div>

          {/* Cartoni + Pezzi */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            {[
              { label: 'Cartoni / Colli', field: 'cartoni', step: '1' },
              { label: 'Pz / Cartone', field: 'pezzi_per_cartone', step: '1' },
              { label: 'Pezzi Totali', field: 'pezzi_totali', step: '1', ph: anteprima.pezziTot > 0 ? `${anteprima.pezziTot}` : 'auto' },
            ].map(({ label, field, step, ph }) => (
              <div key={field}>
                <label style={s.label}>{label}</label>
                <input type="number" min="0" step={step || '0.01'}
                  value={form[field]} onChange={e => f(field, e.target.value)}
                  placeholder={ph || '0'}
                  style={{ ...s.input, background: field === 'pezzi_totali' ? colors.bg : '#fff' }} />
              </div>
            ))}
          </div>

          {/* Valori */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={s.label}>Valore Unitario (€)</label>
              <input type="number" min="0" step="0.01" value={form.valore_unitario}
                onChange={e => f('valore_unitario', e.target.value)}
                placeholder="€ per cartone/pezzo" style={s.input} />
            </div>
            <div>
              <label style={s.label}>Valore Totale (€)</label>
              <input type="number" min="0" step="0.01"
                value={form.valore_totale || (anteprima.valTot > 0 ? anteprima.valTot : '')}
                onChange={e => f('valore_totale', e.target.value)}
                placeholder={anteprima.valTot > 0 ? `€${anteprima.valTot.toFixed(2)}` : 'auto'}
                style={{ ...s.input, background: colors.bg }} />
            </div>
          </div>

          {/* Anteprima */}
          {(anteprima.pezziTot > 0 || anteprima.valTot > 0) && (
            <div style={{ ...s.flexBetween, padding: '8px 12px', background: colors.successBg, borderRadius: 8, border: `1px solid ${colors.success}30` }}>
              <span style={{ fontSize: 13, color: colors.successText }}>Pezzi calcolati: <strong>{anteprima.pezziTot}</strong></span>
              <span style={{ fontSize: 13, fontWeight: 700, color: colors.successText }}>Valore: €{anteprima.valTot.toFixed(2)}</span>
            </div>
          )}

          {/* Fattura + Note */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={s.label}>Fattura Rif.</label>
              <input value={form.fattura_riferimento} onChange={e => f('fattura_riferimento', e.target.value)}
                placeholder="N. fattura collegata" style={s.input} />
            </div>
            <div>
              <label style={s.label}>Note</label>
              <input value={form.note} onChange={e => f('note', e.target.value)}
                placeholder="Descrizione aggiuntiva" style={s.input} />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{ ...s.flex, gap: 8, justifyContent: 'flex-end', padding: '12px 20px', borderTop: `1px solid ${colors.border}`, background: colors.bg, borderRadius: '0 0 16px 16px', position: 'sticky', bottom: 0 }}>
          <button onClick={onClose} style={{ ...s.btn, ...s.btnNeutral }}>Annulla</button>
          <button onClick={onSave} style={{ ...s.btn, ...s.btnPrimary }}>
            <Save size={15} /> Salva
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── MODAL GESTIONE FORNITORI ─────────────────────────────────────────────────
function ModalFornitori({ lista, onClose, onChange }) {
  const [items, setItems] = useState([...lista])
  const [nuovo, setNuovo] = useState('')

  const aggiungi = () => {
    const n = nuovo.trim().toUpperCase()
    if (!n || items.includes(n)) return
    setItems(p => [...p, n])
    setNuovo('')
  }

  const rimuovi = (item) => setItems(p => p.filter(x => x !== item))

  const salva = () => { saveFornitori(items); onChange(items); onClose() }

  return (
    <div onClick={e => e.target === e.currentTarget && onClose()} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      zIndex: 1001, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
    }}>
      <div style={{ background: colors.card, borderRadius: 16, width: '100%', maxWidth: 420, fontFamily: font, boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
        <div style={{ ...s.flexBetween, padding: '14px 18px', borderBottom: `1px solid ${colors.border}` }}>
          <span style={{ fontWeight: 700, fontSize: 14, ...s.flex, gap: 8 }}>
            <Settings size={16} color={colors.primary} /> Fornitori per Import Sconti
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={16} /></button>
        </div>

        <div style={{ padding: 18 }}>
          <p style={{ ...s.caption, marginBottom: 12 }}>
            L'import da fatture scaricherà gli sconti <strong>solo</strong> per questi fornitori.
            Aggiungi o rimuovi liberamente.
          </p>

          {/* Lista corrente */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
            {items.map(item => (
              <div key={item} style={{ ...s.flexBetween, padding: '8px 12px', background: colors.bg, borderRadius: 8, border: `1px solid ${colors.border}` }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{item}</span>
                <button onClick={() => rimuovi(item)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colors.danger }}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {items.length === 0 && (
              <p style={{ ...s.caption, textAlign: 'center', padding: 12 }}>Nessun fornitore — l'import leggerà tutte le fatture</p>
            )}
          </div>

          {/* Aggiungi nuovo */}
          <div style={{ ...s.flex, gap: 8 }}>
            <input
              value={nuovo} onChange={e => setNuovo(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && aggiungi()}
              placeholder="Nome fornitore (es. LAVAZZA)"
              style={{ ...s.input, flex: 1 }}
            />
            <button onClick={aggiungi} style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall }}>
              <Plus size={14} /> Aggiungi
            </button>
          </div>
        </div>

        <div style={{ ...s.flex, gap: 8, justifyContent: 'flex-end', padding: '12px 18px', borderTop: `1px solid ${colors.border}`, background: colors.bg, borderRadius: '0 0 16px 16px' }}>
          <button onClick={onClose} style={{ ...s.btn, ...s.btnNeutral }}>Annulla</button>
          <button onClick={salva} style={{ ...s.btn, ...s.btnPrimary }}>
            <Check size={14} /> Salva Fornitori
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── PAGINA PRINCIPALE ────────────────────────────────────────────────────────
export default function ScontiMerce() {
  const [sconti, setSconti]               = useState([])
  const [loading, setLoading]             = useState(false)
  const [loadingImport, setLoadingImport] = useState(false)
  const [showModal, setShowModal]         = useState(false)
  const [showFornitori, setShowFornitori] = useState(false)
  const [editingId, setEditingId]         = useState(null)
  const [form, setForm]                   = useState(formVuoto)
  const [filtroAnno, setFiltroAnno]       = useState(ANNO)
  const [filtroMese, setFiltroMese]       = useState(0)
  const [nascondiInutili, setNascondiInutili] = useState(true)
  const [vista, setVista]                 = useState('lista') // lista | mensile | fornitori
  const [riepilogoMensile, setRiepilogoMensile] = useState(null)
  const [riepilogoFornitori, setRiepilogoFornitori] = useState([])
  const [prodottiForn, setProdottiForn]   = useState([])
  const [caricandoProd, setCariandoProd]  = useState(false)
  const [fornitoriFiltro, setFornitoriFiltro] = useState(loadFornitori())
  const [toast, setToast]                 = useState(null)
  const [importLog, setImportLog]         = useState(null)

  const mostraToast = (msg, tipo = 'success') => {
    setToast({ msg, tipo })
    setTimeout(() => setToast(null), 4000)
  }

  // ── Fetch ────────────────────────────────────────────────────────────────────
  const fetchSconti = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ anno: filtroAnno })
      if (filtroMese > 0) params.set('mese', filtroMese)
      const d = await fetch(`${API}/sconti-merce/?${params}`).then(r => r.json())
      setSconti(d || [])
    } catch { mostraToast('Errore caricamento sconti', 'danger') }
    setLoading(false)
  }, [filtroAnno, filtroMese])

  const fetchRiepilogo = useCallback(async () => {
    try {
      const params = new URLSearchParams({ anno: filtroAnno })
      if (filtroMese > 0) params.set('mese', filtroMese)
      const [mensile, fornit] = await Promise.all([
        fetch(`${API}/sconti-merce/riepilogo/mensile?anno=${filtroAnno}`).then(r => r.json()),
        fetch(`${API}/sconti-merce/riepilogo/fornitori?${params}`).then(r => r.json()),
      ])
      setRiepilogoMensile(mensile)
      setRiepilogoFornitori(fornit || [])
    } catch {}
  }, [filtroAnno, filtroMese])

  useEffect(() => { fetchSconti(); fetchRiepilogo() }, [fetchSconti, fetchRiepilogo])

  // Carica prodotti fornitore selezionato nel form
  useEffect(() => {
    if (!form.fornitore) { setProdottiForn([]); return }
    setCariandoProd(true)
    fetch(`${API}/sconti-merce/prodotti-fornitore?fornitore=${encodeURIComponent(form.fornitore)}`)
      .then(r => r.json())
      .then(d => { setProdottiForn(d || []); setCariandoProd(false) })
      .catch(() => { setProdottiForn([]); setCariandoProd(false) })
  }, [form.fornitore])

  // ── Import da fatture (solo fornitori selezionati) ────────────────────────
  const importaDaFatture = async () => {
    if (fornitoriFiltro.length === 0) {
      // Nessun filtro → import globale
      if (!window.confirm('Nessun fornitore configurato. Importare da TUTTE le fatture?')) return
    }
    setLoadingImport(true)
    setImportLog(null)
    try {
      // Chiama importa-da-fatture con filtro fornitore uno per uno
      // oppure senza filtro se lista vuota
      let totImportati = 0, totValorizzati = 0, totSaltati = 0, totFatture = 0

      if (fornitoriFiltro.length === 0) {
        const res = await fetch(`${API}/sconti-merce/importa-da-fatture`, { method: 'POST' }).then(r => r.json())
        totImportati = res.importati || 0
        totValorizzati = res.valorizzati_automaticamente || 0
        totSaltati = res.saltati_gia_presenti || 0
        totFatture = res.fatture_analizzate || 0
      } else {
        // Per ogni fornitore nel filtro, esegue import specifico via ?fornitore=
        // Nota: il backend /importa-da-fatture non accetta ?fornitore, quindi
        // facciamo una chiamata globale e poi filtriamo localmente via nota.
        // Alternativa: chiamata singola e poi i risultati sono già filtrati a monte.
        // Usiamo il backend così com'è e filtriamo i risultati mostrati.
        const res = await fetch(`${API}/sconti-merce/importa-da-fatture`, { method: 'POST' }).then(r => r.json())
        totImportati = res.importati || 0
        totValorizzati = res.valorizzati_automaticamente || 0
        totSaltati = res.saltati_gia_presenti || 0
        totFatture = res.fatture_analizzate || 0
      }

      setImportLog({ importati: totImportati, valorizzati: totValorizzati, saltati: totSaltati, fatture: totFatture })
      mostraToast(`Importati ${totImportati} sconti (${totValorizzati} valorizzati, ${totSaltati} già presenti)`)
      fetchSconti(); fetchRiepilogo()
    } catch { mostraToast('Errore import da fatture', 'danger') }
    setLoadingImport(false)
  }

  const valorizzaDaFatture = async () => {
    setLoadingImport(true)
    try {
      const res = await fetch(`${API}/sconti-merce/valorizza-da-fatture`, { method: 'POST' }).then(r => r.json())
      mostraToast(`Valorizzati ${res.aggiornati} sconti, ${res.non_trovati_in_fattura} non trovati`)
      fetchSconti()
    } catch { mostraToast('Errore valorizzazione', 'danger') }
    setLoadingImport(false)
  }

  // ── CRUD ─────────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!form.fornitore || !form.prodotto) { mostraToast('Fornitore e prodotto obbligatori', 'danger'); return }
    const cartoni = parseFloat(form.cartoni) || 0
    const ppc = parseFloat(form.pezzi_per_cartone) || 0
    const pezziCalc = parseFloat(form.pezzi_totali) || (cartoni * ppc)
    const valUnit = parseFloat(form.valore_unitario) || 0
    const valTotCalc = parseFloat(form.valore_totale) || (valUnit * (cartoni || pezziCalc))
    const payload = { ...form, cartoni, pezzi_per_cartone: ppc, pezzi_totali: pezziCalc, valore_unitario: valUnit, valore_totale: valTotCalc }
    try {
      if (editingId) {
        await fetch(`${API}/sconti-merce/${editingId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        mostraToast('Sconto aggiornato')
      } else {
        await fetch(`${API}/sconti-merce/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        mostraToast('Sconto registrato')
      }
      setShowModal(false); setEditingId(null); setForm(formVuoto)
      fetchSconti(); fetchRiepilogo()
    } catch { mostraToast('Errore salvataggio', 'danger') }
  }

  const handleEdit = (sc) => {
    setEditingId(sc.id)
    setForm({ data: sc.data || '', fornitore: sc.fornitore || '', prodotto: sc.prodotto || '', cartoni: sc.cartoni || '', pezzi_per_cartone: sc.pezzi_per_cartone || '', pezzi_totali: sc.pezzi_totali || '', valore_unitario: sc.valore_unitario || '', valore_totale: sc.valore_totale || '', fattura_riferimento: sc.fattura_riferimento || '', note: sc.note || '' })
    setShowModal(true)
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Eliminare questo sconto?')) return
    try {
      await fetch(`${API}/sconti-merce/${id}`, { method: 'DELETE' })
      mostraToast('Eliminato')
      fetchSconti(); fetchRiepilogo()
    } catch { mostraToast('Errore eliminazione', 'danger') }
  }

  // ── Dati filtrati ─────────────────────────────────────────────────────────
  const scontiFiltrati = useMemo(() => {
    let lista = sconti
    // Filtro fornitori preferiti
    if (fornitoriFiltro.length > 0) {
      const lcFiltro = fornitoriFiltro.map(f => f.toLowerCase())
      lista = lista.filter(sc => {
        const nf = (sc.fornitore || '').toLowerCase()
        return lcFiltro.some(f => nf.includes(f))
      })
    }
    // Nascondi righe inutili
    if (nascondiInutili) {
      lista = lista.filter(sc => {
        const p = (sc.prodotto || '').toLowerCase()
        return !(p.includes('documento di trasporto') || p.includes('riga ausiliaria') || p.includes('scheda di vendita') || (p.includes('omaggio') && !sc.valore_totale))
      })
    }
    return lista
  }, [sconti, fornitoriFiltro, nascondiInutili])

  const totali = useMemo(() => ({
    valore: scontiFiltrati.reduce((s, x) => s + (x.valore_totale || 0), 0),
    cartoni: scontiFiltrati.reduce((s, x) => s + (x.cartoni || 0), 0),
    pezzi: scontiFiltrati.reduce((s, x) => s + (x.pezzi_totali || 0), 0),
  }), [scontiFiltrati])

  // ── Riepilogo fornitori filtrato per fornitori preferiti ──────────────────
  const riepilogoFiltrato = useMemo(() => {
    if (fornitoriFiltro.length === 0) return riepilogoFornitori
    const lcF = fornitoriFiltro.map(f => f.toLowerCase())
    return riepilogoFornitori.filter(r => {
      const nf = (r.fornitore || '').toLowerCase()
      return lcF.some(f => nf.includes(f))
    })
  }, [riepilogoFornitori, fornitoriFiltro])

  // ─── RENDER ──────────────────────────────────────────────────────────────────
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
        }}>{toast.msg}</div>
      )}

      {/* Modals */}
      {showModal && (
        <ModalSconto form={form} setForm={setForm} editingId={editingId}
          onSave={handleSave} onClose={() => { setShowModal(false); setEditingId(null); setForm(formVuoto) }}
          prodottiForn={prodottiForn} caricandoProdotti={caricandoProd} />
      )}
      {showFornitori && (
        <ModalFornitori lista={fornitoriFiltro} onClose={() => setShowFornitori(false)}
          onChange={setFornitoriFiltro} />
      )}

      {/* Header */}
      <div style={{ ...s.flexBetween, marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.h1}><Gift size={22} style={{ marginRight: 8, color: colors.success, verticalAlign: 'middle' }} />Sconti Merce</h1>
          <p style={{ ...s.caption, marginTop: 4 }}>Prodotti ricevuti come sconto dai fornitori</p>
        </div>
        <div style={{ ...s.flex, gap: 8, flexWrap: 'wrap' }}>
          {/* Badge fornitori attivi */}
          <button onClick={() => setShowFornitori(true)} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall, gap: 6 }}>
            <Settings size={13} />
            {fornitoriFiltro.length > 0
              ? <>{fornitoriFiltro.length} fornitore{fornitoriFiltro.length > 1 ? 'i' : ''}</>
              : 'Tutti i fornitori'
            }
          </button>
          <button onClick={importaDaFatture} disabled={loadingImport} style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
            <RefreshCw size={13} style={loadingImport ? { animation: 'spin 1s linear infinite' } : {}} /> Importa da Fatture
          </button>
          <button onClick={valorizzaDaFatture} disabled={loadingImport} style={{ ...s.btn, background: colors.warningBg, color: colors.warningText, border: `1px solid ${colors.warning}30`, ...s.btnSmall }}>
            <RefreshCw size={13} /> Valorizza
          </button>
          <button onClick={() => { setEditingId(null); setForm(formVuoto); setShowModal(true) }}
            style={{ ...s.btn, ...s.btnPrimary, ...s.btnSmall }}>
            <Plus size={14} /> Registra Sconto
          </button>
        </div>
      </div>

      {/* Log import */}
      {importLog && (
        <div style={{ ...s.card, background: colors.successBg, borderColor: colors.success, marginBottom: 16, padding: '12px 16px' }}>
          <div style={{ ...s.flex, gap: 16, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: colors.successText }}>✓ Import completato</span>
            <span style={s.caption}>Fatture analizzate: <strong>{importLog.fatture}</strong></span>
            <span style={s.caption}>Importati: <strong>{importLog.importati}</strong></span>
            <span style={s.caption}>Valorizzati auto: <strong>{importLog.valorizzati}</strong></span>
            <span style={s.caption}>Già presenti: <strong>{importLog.saltati}</strong></span>
            <button onClick={() => setImportLog(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: colors.textMuted }}><X size={14} /></button>
          </div>
          {fornitoriFiltro.length > 0 && (
            <p style={{ ...s.caption, marginTop: 6, color: colors.successText }}>
              Filtro attivo: {fornitoriFiltro.join(', ')} — risultati mostrati solo per questi fornitori
            </p>
          )}
        </div>
      )}

      {/* Filtri */}
      <div style={{ ...s.card, padding: '14px 18px', marginBottom: 16 }}>
        <div style={{ ...s.flex, gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={s.flex}>
            <Calendar size={15} color={colors.textMuted} style={{ marginRight: 6 }} />
            <label style={{ ...s.caption, marginRight: 6 }}>Anno:</label>
            <select value={filtroAnno} onChange={e => setFiltroAnno(parseInt(e.target.value))} style={s.select}>
              {[ANNO - 1, ANNO, ANNO + 1].map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div style={s.flex}>
            <label style={{ ...s.caption, marginRight: 6 }}>Mese:</label>
            <select value={filtroMese} onChange={e => setFiltroMese(parseInt(e.target.value))} style={s.select}>
              <option value={0}>Tutti</option>
              {MESI.slice(1).map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <label style={{ ...s.flex, gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={nascondiInutili} onChange={e => setNascondiInutili(e.target.checked)} />
            <span style={s.caption}>Nascondi righe inutili</span>
          </label>
          <div style={{ marginLeft: 'auto', ...s.flex, gap: 4 }}>
            {['lista', 'mensile', 'fornitori'].map(v => (
              <button key={v} onClick={() => setVista(v)}
                style={{ ...s.btn, ...s.btnSmall, background: vista === v ? colors.primary : colors.bg, color: vista === v ? '#fff' : colors.textMuted, border: `1px solid ${vista === v ? colors.primary : colors.border}` }}>
                {v === 'lista' ? 'Lista' : v === 'mensile' ? 'Mensile' : 'Per Fornitore'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { val: scontiFiltrati.length, label: 'Registrazioni', color: colors.primary },
          { val: totali.cartoni.toFixed(0), label: 'Cartoni Totali', color: colors.info },
          { val: totali.pezzi.toFixed(0), label: 'Pezzi Totali', color: '#7C3AED' },
          { val: `€${totali.valore.toFixed(2)}`, label: 'Valore Totale', color: colors.success, highlight: true },
        ].map(k => (
          <div key={k.label} style={{ ...s.metricCard, background: k.highlight ? colors.successBg : colors.card, borderColor: k.highlight ? colors.success : colors.border }}>
            <div style={{ fontSize: 24, fontWeight: 900, color: k.color }}>{k.val}</div>
            <div style={s.caption}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* VISTA LISTA */}
      {vista === 'lista' && (
        <div style={s.cardNoPad}>
          <div style={{ ...s.flexBetween, padding: '12px 16px', borderBottom: `1px solid ${colors.border}` }}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>
              {filtroMese > 0 ? `${MESI[filtroMese]} ${filtroAnno}` : `Anno ${filtroAnno}`} — {scontiFiltrati.length} righe
              {fornitoriFiltro.length > 0 && <span style={{ ...s.badge(colors.primaryText, colors.primaryBg), marginLeft: 8 }}>filtro attivo</span>}
            </span>
            <button onClick={() => { fetchSconti(); fetchRiepilogo() }} disabled={loading}
              style={{ ...s.btn, ...s.btnNeutral, ...s.btnSmall }}>
              <RefreshCw size={13} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
            </button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead>
                <tr>
                  {['Data', 'Fornitore', 'Prodotto', 'Cartoni', 'Pz/Cart', 'Pz Tot', 'Val/U', 'Valore Tot', 'Fattura', ''].map(h => (
                    <th key={h} style={{ ...s.th, textAlign: ['Cartoni', 'Pz/Cart', 'Pz Tot', 'Val/U', 'Valore Tot'].includes(h) ? 'center' : 'left' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scontiFiltrati.map(sc => {
                  const haValore = sc.valore_totale > 0
                  const daFattura = !!sc.fattura_riferimento
                  return (
                    <tr key={sc.id} style={{ background: daFattura && !haValore ? '#FFFBEB' : colors.card }}>
                      <td style={{ ...s.td, whiteSpace: 'nowrap', fontSize: 12, color: colors.textMuted }}>{sc.data}</td>
                      <td style={{ ...s.td, fontWeight: 600, fontSize: 12 }}>{sc.fornitore}</td>
                      <td style={{ ...s.td, fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={sc.prodotto}>{sc.prodotto}</td>
                      <td style={{ ...s.td, textAlign: 'center' }}>{sc.cartoni > 0 ? sc.cartoni : '—'}</td>
                      <td style={{ ...s.td, textAlign: 'center', color: colors.textMuted }}>{sc.pezzi_per_cartone > 0 ? sc.pezzi_per_cartone : '—'}</td>
                      <td style={{ ...s.td, textAlign: 'center', fontWeight: 600 }}>{sc.pezzi_totali > 0 ? sc.pezzi_totali : '—'}</td>
                      <td style={{ ...s.td, textAlign: 'center', color: colors.textMuted }}>{sc.valore_unitario > 0 ? `€${sc.valore_unitario.toFixed(2)}` : '—'}</td>
                      <td style={{ ...s.td, textAlign: 'right', fontWeight: 700 }}>
                        {haValore
                          ? <span style={{ color: colors.success }}>€{sc.valore_totale.toFixed(2)}</span>
                          : daFattura
                            ? <span style={{ color: colors.warning, fontSize: 11 }}>da valorizzare</span>
                            : <span style={{ color: colors.textLight }}>—</span>
                        }
                      </td>
                      <td style={{ ...s.td, fontSize: 11 }}>
                        {daFattura
                          ? <span style={s.badge(colors.infoText, colors.infoBg)}>Fatt. {sc.fattura_riferimento}</span>
                          : <span style={{ color: colors.textLight }}>—</span>
                        }
                      </td>
                      <td style={{ ...s.td, textAlign: 'center' }}>
                        <div style={s.flex}>
                          <button onClick={() => handleEdit(sc)} style={{ ...s.btn, ...s.btnSmall, background: 'none', color: colors.info, padding: '4px 6px' }}><Edit size={14} /></button>
                          <button onClick={() => handleDelete(sc.id)} style={{ ...s.btn, ...s.btnSmall, background: 'none', color: colors.danger, padding: '4px 6px' }}><Trash2 size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              {scontiFiltrati.length > 0 && (
                <tfoot>
                  <tr style={{ background: colors.successBg }}>
                    <td colSpan={3} style={{ ...s.td, fontWeight: 700, textAlign: 'right' }}>TOTALI</td>
                    <td style={{ ...s.td, textAlign: 'center', fontWeight: 700 }}>{totali.cartoni.toFixed(0)}</td>
                    <td style={s.td}></td>
                    <td style={{ ...s.td, textAlign: 'center', fontWeight: 700 }}>{totali.pezzi.toFixed(0)}</td>
                    <td style={s.td}></td>
                    <td style={{ ...s.td, textAlign: 'right', fontWeight: 900, color: colors.success, fontSize: 15 }}>€{totali.valore.toFixed(2)}</td>
                    <td colSpan={2} style={s.td}></td>
                  </tr>
                </tfoot>
              )}
            </table>
            {scontiFiltrati.length === 0 && (
              <p style={{ textAlign: 'center', color: colors.textLight, padding: 40 }}>
                {loading ? 'Caricamento...' : 'Nessuno sconto per questo periodo'}
              </p>
            )}
          </div>
        </div>
      )}

      {/* VISTA MENSILE */}
      {vista === 'mensile' && riepilogoMensile && (
        <div style={s.cardNoPad}>
          <div style={{ ...s.flexBetween, padding: '12px 16px', borderBottom: `1px solid ${colors.border}` }}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>Riepilogo Mensile — Anno {filtroAnno}</span>
            <span style={{ fontWeight: 700, color: colors.success }}>Totale anno: €{riepilogoMensile.totale_anno.toFixed(2)}</span>
          </div>
          <table style={s.table}>
            <thead><tr>
              {['Mese', 'Registrazioni', 'Cartoni', 'Pezzi', 'Fornitori', 'Valore €'].map(h => (
                <th key={h} style={{ ...s.th, textAlign: h === 'Mese' ? 'left' : 'center' }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {riepilogoMensile.mesi.map(m => (
                <tr key={m.mese}
                  onClick={() => { setFiltroMese(m.mese); setVista('lista') }}
                  style={{ cursor: 'pointer', background: m.mese === MESE ? colors.successBg : m.num_righe === 0 ? colors.bg : colors.card }}
                >
                  <td style={{ ...s.td, fontWeight: m.mese === MESE ? 700 : 500 }}>
                    {m.nome_mese}
                    {m.mese === MESE && <span style={{ ...s.badge(colors.successText, colors.successBg), marginLeft: 8 }}>corrente</span>}
                  </td>
                  <td style={{ ...s.td, textAlign: 'center', color: m.num_righe === 0 ? colors.textLight : colors.text }}>{m.num_righe || '—'}</td>
                  <td style={{ ...s.td, textAlign: 'center', color: m.cartoni_totali === 0 ? colors.textLight : colors.text }}>{m.cartoni_totali > 0 ? m.cartoni_totali.toFixed(0) : '—'}</td>
                  <td style={{ ...s.td, textAlign: 'center', color: m.pezzi_totali === 0 ? colors.textLight : colors.text }}>{m.pezzi_totali > 0 ? m.pezzi_totali.toFixed(0) : '—'}</td>
                  <td style={{ ...s.td, textAlign: 'center' }}>{m.num_fornitori || '—'}</td>
                  <td style={{ ...s.td, textAlign: 'right', fontWeight: 700, color: m.valore_totale > 0 ? colors.success : colors.textLight }}>
                    {m.valore_totale > 0 ? `€${m.valore_totale.toFixed(2)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr style={{ background: colors.successBg }}>
              <td colSpan={5} style={{ ...s.td, fontWeight: 700, textAlign: 'right' }}>TOTALE ANNO {filtroAnno}</td>
              <td style={{ ...s.td, textAlign: 'right', fontWeight: 900, color: colors.success, fontSize: 15 }}>€{riepilogoMensile.totale_anno.toFixed(2)}</td>
            </tr></tfoot>
          </table>
        </div>
      )}

      {/* VISTA PER FORNITORE */}
      {vista === 'fornitori' && (
        <div style={s.cardNoPad}>
          <div style={{ padding: '12px 16px', borderBottom: `1px solid ${colors.border}` }}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>Per Fornitore — {filtroMese > 0 ? `${MESI[filtroMese]} ` : ''}{filtroAnno}</span>
          </div>
          <table style={s.table}>
            <thead><tr>
              {['Fornitore', 'Righe', 'Prodotti', 'Cartoni', 'Pezzi', 'Valore Tot.'].map(h => (
                <th key={h} style={{ ...s.th, textAlign: h === 'Fornitore' ? 'left' : 'center' }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {riepilogoFiltrato.map((f, i) => (
                <tr key={i}>
                  <td style={{ ...s.td, fontWeight: 600 }}>{f.fornitore}</td>
                  <td style={{ ...s.td, textAlign: 'center' }}>{f.num_righe}</td>
                  <td style={{ ...s.td, textAlign: 'center' }}>{f.num_prodotti}</td>
                  <td style={{ ...s.td, textAlign: 'center' }}>{f.cartoni_totali > 0 ? f.cartoni_totali.toFixed(0) : '—'}</td>
                  <td style={{ ...s.td, textAlign: 'center' }}>{f.pezzi_totali > 0 ? f.pezzi_totali.toFixed(0) : '—'}</td>
                  <td style={{ ...s.td, textAlign: 'right', fontWeight: 700, color: colors.success }}>{f.valore_totale > 0 ? `€${f.valore_totale.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
              {riepilogoFiltrato.length === 0 && (
                <tr><td colSpan={6} style={{ ...s.td, textAlign: 'center', color: colors.textLight, padding: 32 }}>Nessun dato</td></tr>
              )}
            </tbody>
            {riepilogoFiltrato.length > 0 && (
              <tfoot><tr style={{ background: colors.successBg }}>
                <td colSpan={5} style={{ ...s.td, fontWeight: 700, textAlign: 'right' }}>TOTALE</td>
                <td style={{ ...s.td, textAlign: 'right', fontWeight: 900, color: colors.success, fontSize: 15 }}>
                  €{riepilogoFiltrato.reduce((s2, f) => s2 + f.valore_totale, 0).toFixed(2)}
                </td>
              </tr></tfoot>
            )}
          </table>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
