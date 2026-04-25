import React, { useState, useCallback, useMemo } from 'react';
import { useAbortableEffect, isCanceledError } from '../../hooks';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Search, Plus, User, Edit2, Save, X, ChevronRight, AlertTriangle,
  FileText, CreditCard, Calendar, Clock, Briefcase, Activity,
  TrendingUp, Shield, Trash2, Check, RefreshCw, ExternalLink,
  Download, ArrowLeft, Users, Award, MapPin, Phone, Mail,
} from 'lucide-react';
import api from '../../api';
import { COLORS, STYLES, SPACING, useIsMobile, pagePad } from '../../lib/utils';
import DedupeDipendentiModal from '../../components/DedupeDipendentiModal';
import ImportDipendentiModal from '../../components/ImportDipendentiModal';

// ─── Costanti ─────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'anagrafica',    label: 'Anagrafica',    icon: User },
  { id: 'contratti',     label: 'Contratti',     icon: Briefcase },
  { id: 'presenze',      label: 'Presenze',      icon: Calendar },
  { id: 'cedolini',      label: 'Cedolini',      icon: FileText },
  { id: 'verbali',       label: 'Verbali',       icon: Shield },
  { id: 'movimenti',     label: 'Movimenti',     icon: CreditCard },
  { id: 'giustificativi',label: 'Giustificativi',icon: Activity },
];

const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i);
const MESI_LABEL = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

// Colori per mansione avatar
const AVATAR_PALETTE = ['#0f2744','#1e3a5f','#b8860b','#15803d','#1d4ed8','#7c3aed','#b45309','#0891b2'];
function avatarColor(name) {
  let h = 0;
  for (let i = 0; i < (name||'').length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return AVATAR_PALETTE[Math.abs(h) % AVATAR_PALETTE.length];
}
function initials(name) {
  if (!name) return '?';
  const p = name.split(' ').filter(Boolean);
  return p.length >= 2 ? (p[0][0]+p[p.length-1][0]).toUpperCase() : name.slice(0,2).toUpperCase();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt€(v) {
  if (v == null || isNaN(Number(v))) return '—';
  return new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(v);
}
function fmtD(d) {
  if (!d) return '—';
  try {
    const p = d.split('T')[0].split('-');
    if (p.length === 3 && p[0].length === 4) return `${p[2]}/${p[1]}/${p[0]}`;
    if (d.includes('/')) return d;
    return new Date(d).toLocaleDateString('it-IT');
  } catch { return d; }
}

// Helper per multi-select: dato due 'YYYY-MM-DD', restituisce array di tutte
// le date intermedie incluse (ordine cronologico ascendente).
function computeDateRange(dsA, dsB) {
  if (!dsA || !dsB) return [];
  const a = new Date(dsA + 'T00:00:00');
  const b = new Date(dsB + 'T00:00:00');
  if (isNaN(a) || isNaN(b)) return [];
  const start = a <= b ? a : b;
  const end = a <= b ? b : a;
  const out = [];
  const cur = new Date(start);
  while (cur <= end) {
    const y = cur.getFullYear();
    const m = String(cur.getMonth() + 1).padStart(2, '0');
    const d = String(cur.getDate()).padStart(2, '0');
    out.push(`${y}-${m}-${d}`);
    cur.setDate(cur.getDate() + 1);
  }
  return out;
}

// Badge stato
function Badge({ label, color, bg }) {
  return (
    <span style={{
      padding:'3px 10px', borderRadius:99, fontSize:11, fontWeight:700,
      background: bg||'#f1f5f9', color: color||COLORS.textMuted, whiteSpace:'nowrap',
    }}>{label}</span>
  );
}

// Card KPI piccola
function KpiCard({ label, value, color, icon: Icon, sub }) {
  return (
    <div style={{
      background:'white', border:`1px solid ${COLORS.border}`, borderRadius:12,
      padding:'14px 16px', borderTop:`3px solid ${color||COLORS.primary}`,
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:6 }}>
        {Icon && <Icon size={14} color={color||COLORS.textMuted} />}
        <span style={{ fontSize:10, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase', letterSpacing:'0.06em' }}>
          {label}
        </span>
      </div>
      <div style={{ fontSize:20, fontWeight:800, color: color||COLORS.text, fontVariantNumeric:'tabular-nums' }}>
        {value ?? '—'}
      </div>
      {sub && <div style={{ fontSize:11, color:COLORS.textMuted, marginTop:3 }}>{sub}</div>}
    </div>
  );
}

// Sezione con titolo
function Section({ title, action, children, style }) {
  return (
    <div style={{ marginBottom:28, ...style }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
        <h3 style={{ margin:0, fontSize:15, fontWeight:700, color:COLORS.text }}>{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

// Campo leggibile/editabile
function Field({ label, value, editMode, onChange, type='text', options, multiline }) {
  const base = {
    width:'100%', padding:'8px 10px',
    border:`1px solid ${COLORS.border}`, borderRadius:8,
    fontSize:14, outline:'none', boxSizing:'border-box',
    background:'white', color:COLORS.text,
  };
  return (
    <div style={{ marginBottom:14 }}>
      <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:4 }}>
        {label}
      </div>
      {editMode ? (
        options ? (
          <select value={value||''} onChange={e=>onChange(e.target.value)} style={base}>
            <option value=''>—</option>
            {options.map(o=><option key={o}>{o}</option>)}
          </select>
        ) : multiline ? (
          <textarea value={value||''} onChange={e=>onChange(e.target.value)} rows={3}
            style={{...base, resize:'vertical', fontFamily:'inherit'}} />
        ) : (
          <input type={type} value={value||''} onChange={e=>onChange(e.target.value)} style={base} />
        )
      ) : (
        <div style={{ fontSize:14, color: value ? COLORS.text : COLORS.textMuted, padding:'8px 0', borderBottom:`1px solid ${COLORS.border}20` }}>
          {value || '—'}
        </div>
      )}
    </div>
  );
}

// Empty state
function EmptyState({ icon: Icon, text, sub }) {
  return (
    <div style={{ padding:'48px 24px', textAlign:'center', color:COLORS.textMuted }}>
      {Icon && <Icon size={36} style={{ marginBottom:12, opacity:0.25 }} />}
      <div style={{ fontWeight:600, marginBottom:6, color:COLORS.text }}>{text}</div>
      {sub && <div style={{ fontSize:13 }}>{sub}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB ANAGRAFICA
// ─────────────────────────────────────────────────────────────────────────────
function TabAnagrafica({ dip, onSaved }) {
  const isMobile = useIsMobile();
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState({ ...dip });
  const [saving, setSaving] = useState(false);

  const reset = () => { setForm({...dip}); setEdit(false); };
  const f = (key, val) => setForm(p=>({...p,[key]:val}));

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/api/dipendenti/${dip.id}`, form);
      onSaved(form);
      setEdit(false);
    } catch(e) { console.error(e); }
    finally { setSaving(false); }
  };

  const prog = form.progressivi || {};

  return (
    <div>
      {/* Header azioni */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{
            width:48, height:48, borderRadius:12,
            background:`${avatarColor(form.nome_completo)}20`,
            color:avatarColor(form.nome_completo),
            display:'flex', alignItems:'center', justifyContent:'center',
            fontWeight:800, fontSize:18,
          }}>
            {initials(form.nome_completo)}
          </div>
          <div>
            <div style={{ fontWeight:700, fontSize:16, color:COLORS.text }}>{form.nome_completo || '—'}</div>
            <div style={{ fontSize:12, color:COLORS.textMuted }}>{form.mansione || form.qualifica || '—'}</div>
          </div>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          {edit ? (
            <>
              <button onClick={reset} style={{padding:'7px 12px',background:'#f1f5f9',border:'none',borderRadius:8,cursor:'pointer',display:'flex',alignItems:'center',gap:5,fontSize:13}}>
                <X size={13}/> Annulla
              </button>
              <button onClick={save} disabled={saving} style={{padding:'7px 16px',background:'#22c55e',color:'white',border:'none',borderRadius:8,cursor:'pointer',display:'flex',alignItems:'center',gap:5,fontSize:13,fontWeight:600}}>
                <Save size={13}/> {saving?'Salvataggio…':'Salva'}
              </button>
            </>
          ) : (
            <button onClick={()=>setEdit(true)} style={{padding:'7px 16px',background:COLORS.primary,color:'white',border:'none',borderRadius:8,cursor:'pointer',display:'flex',alignItems:'center',gap:5,fontSize:13,fontWeight:600}}>
              <Edit2 size={13}/> Modifica
            </button>
          )}
        </div>
      </div>

      {/* Status badge */}
      {form.in_carico === false && (
        <div style={{ background:'#fef2f2', border:'1px solid #fecaca', borderRadius:8, padding:'10px 14px', marginBottom:18, display:'flex', alignItems:'center', gap:8 }}>
          <AlertTriangle size={16} color='#dc2626'/>
          <span style={{ fontSize:13, fontWeight:600, color:'#dc2626' }}>Dipendente NON in carico — il fascicolo è consultabile ma escluso dai flussi attivi.</span>
        </div>
      )}

      <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr':'1fr 1fr', gap:'0 32px' }}>
        <Section title="Dati Personali">
          <Field label="Nome"            value={form.nome}            editMode={edit} onChange={v=>f('nome',v)} />
          <Field label="Cognome"         value={form.cognome}         editMode={edit} onChange={v=>f('cognome',v)} />
          <Field label="Codice Fiscale"  value={form.codice_fiscale}  editMode={edit} onChange={v=>f('codice_fiscale',v)} />
          <Field label="Data di Nascita" value={form.data_nascita}    editMode={edit} onChange={v=>f('data_nascita',v)} type="date" />
          <Field label="Luogo di Nascita" value={form.luogo_nascita}  editMode={edit} onChange={v=>f('luogo_nascita',v)} />
        </Section>

        <Section title="Contatti">
          <Field label="Email"     value={form.email}    editMode={edit} onChange={v=>f('email',v)}    type="email" />
          <Field label="Telefono"  value={form.telefono} editMode={edit} onChange={v=>f('telefono',v)} type="tel" />
          <Field label="Indirizzo" value={form.indirizzo} editMode={edit} onChange={v=>f('indirizzo',v)} />
        </Section>

        <Section title="Rapporto di Lavoro">
          <Field label="Mansione"         value={form.mansione}         editMode={edit} onChange={v=>f('mansione',v)}
            options={['Cameriere','Cuoco','Aiuto Cuoco','Barista','Pizzaiolo','Lavapiatti','Cassiera','Responsabile Sala','Chef','Sommelier','Amministrativo','Magazziniere']} />
          <Field label="Qualifica/Livello" value={form.qualifica || form.livello} editMode={edit} onChange={v=>f('qualifica',v)} />
          <Field label="Tipo Contratto"   value={form.tipo_contratto}   editMode={edit} onChange={v=>f('tipo_contratto',v)}
            options={['Tempo Indeterminato','Tempo Determinato','Apprendistato','Stage/Tirocinio','Collaborazione','Part-time']} />
          <Field label="Data Assunzione"  value={form.data_assunzione}  editMode={edit} onChange={v=>f('data_assunzione',v)} type="date" />
          <Field label="Fine Contratto"   value={form.data_fine_contratto} editMode={edit} onChange={v=>f('data_fine_contratto',v)} type="date" />
          <Field label="Ore Settimanali"  value={form.ore_settimanali}  editMode={edit} onChange={v=>f('ore_settimanali',v)} type="number" />
        </Section>

        <Section title="Dati Retributivi">
          <Field label="IBAN Stipendio"   value={form.iban_cedolino || form.iban} editMode={edit} onChange={v=>{ f('iban',v); f('iban_cedolino',v); }} />
          <Field label="Paga Base (€)"    value={form.paga_base}    editMode={edit} onChange={v=>f('paga_base',v)}    type="number" />
          <Field label="Contingenza (€)"  value={form.contingenza}  editMode={edit} onChange={v=>f('contingenza',v)}  type="number" />
          <Field label="Stipendio Lordo (€)" value={form.stipendio_lordo} editMode={edit} onChange={v=>f('stipendio_lordo',v)} type="number" />
          <Field label="Matricola"        value={form.matricola || form.codice_dipendente} editMode={edit} onChange={v=>f('matricola',v)} />
        </Section>
      </div>

      {/* Progressivi ferie */}
      <Section title="Progressivi Ferie & Permessi">
        <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr 1fr':'repeat(3,1fr)', gap:12 }}>
          {[
            { label:'Ferie Maturate', key:'ferie_maturate', unit:'gg' },
            { label:'Ferie Godute',   key:'ferie_godute',   unit:'gg' },
            { label:'Ferie Residue',  key:'ferie_residue',  unit:'gg', highlight:true },
            { label:'Permessi Mat.',  key:'permessi_maturati', unit:'h' },
            { label:'Permessi Goduti',key:'permessi_goduti',   unit:'h' },
            { label:'Permessi Resid.',key:'permessi_residui',  unit:'h', highlight:true },
            { label:'TFR Accant.',    key:'tfr_accantonato',   unit:'€', euro:true },
          ].map(({ label, key, unit, highlight, euro }) => (
            <div key={key} style={{
              background: highlight ? `${COLORS.primary}08` : 'white',
              border:`1px solid ${highlight ? COLORS.primary+'33' : COLORS.border}`,
              borderRadius:10, padding:'12px 14px',
            }}>
              <div style={{ fontSize:10, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase', letterSpacing:'0.05em' }}>{label}</div>
              <div style={{ fontSize:20, fontWeight:800, color: highlight ? COLORS.primary : COLORS.text, marginTop:4, fontVariantNumeric:'tabular-nums' }}>
                {euro ? fmt€(prog[key]||0) : `${prog[key]||0} ${unit}`}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Note + stato in carico */}
      <Section title="Note">
        <Field label="Note" value={form.note} editMode={edit} onChange={v=>f('note',v)} multiline />
        {edit && (
          <label style={{ display:'flex', alignItems:'center', gap:10, cursor:'pointer', marginTop:8, padding:'12px 14px', background:'#f8fafc', borderRadius:8, border:`1px solid ${COLORS.border}` }}>
            <input type="checkbox" checked={form.in_carico===false}
              onChange={e=>f('in_carico', !e.target.checked)}
              style={{ width:16, height:16 }} />
            <div>
              <div style={{ fontSize:13, fontWeight:600, color:COLORS.text }}>Dipendente NON in carico</div>
              <div style={{ fontSize:11, color:COLORS.textMuted }}>Spunta se cessato — il fascicolo resta consultabile.</div>
            </div>
          </label>
        )}
      </Section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB CONTRATTI
// ─────────────────────────────────────────────────────────────────────────────
function TabContratti({ dip }) {
  const isMobile = useIsMobile();
  const [contratti, setContratti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    tipo_contratto:'Tempo Determinato', data_inizio:'', data_fine:'',
    retribuzione_lorda:0, ore_settimanali:40, livello:'', ccnl:'Turismo - Pubblici Esercizi',
    mansione: dip.mansione||'', note:'',
  });

  const load = useCallback((signal) => {
    setLoading(true);
    api.get(`/api/dipendenti/contratti?dipendente_id=${dip.id}`, { signal })
      .then(r=>{ if(!signal?.aborted) setContratti(Array.isArray(r.data)?r.data:[]); })
      .catch(e=>{ if(!isCanceledError(e)) setContratti([]); })
      .finally(()=>{ if(!signal?.aborted) setLoading(false); });
  }, [dip.id]);

  useAbortableEffect(load, [load]);

  const crea = async () => {
    setSaving(true);
    try {
      await api.post('/api/dipendenti/contratti', { ...form, dipendente_id: dip.id });
      setShowForm(false);
      load();
    } catch(e) { console.error(e); }
    finally { setSaving(false); }
  };

  const termina = async (id, dataFine) => {
    if (!window.confirm('Terminare questo contratto?')) return;
    try {
      await api.post(`/api/dipendenti/contratti/${id}/termina?data_fine=${dataFine || new Date().toISOString().split('T')[0]}&motivo=Cessazione`);
      load();
    } catch(e) { console.error(e); }
  };

  const STATI_COLOR = {
    attivo: { bg:'#dcfce7', color:'#16a34a' },
    terminato: { bg:'#f1f5f9', color:'#64748b' },
    bozza: { bg:'#fef9c3', color:'#a16207' },
  };

  if (loading) return <div style={{padding:40,textAlign:'center',color:COLORS.textMuted}}>Caricamento…</div>;

  return (
    <div>
      <Section title="Storico Contratti" action={
        <button onClick={()=>setShowForm(v=>!v)} style={{padding:'7px 14px',background:COLORS.primary,color:'white',border:'none',borderRadius:8,cursor:'pointer',display:'flex',alignItems:'center',gap:5,fontSize:13,fontWeight:600}}>
          <Plus size={13}/> Nuovo Contratto
        </button>
      }>
        {showForm && (
          <div style={{ border:`1px solid ${COLORS.border}`, borderRadius:12, padding:20, marginBottom:20, background:'#f8fafc' }}>
            <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr':'1fr 1fr', gap:'0 20px' }}>
              <Field label="Tipo Contratto" value={form.tipo_contratto} editMode onChange={v=>setForm(p=>({...p,tipo_contratto:v}))}
                options={['Tempo Indeterminato','Tempo Determinato','Apprendistato','Stage/Tirocinio','Part-time']} />
              <Field label="Mansione" value={form.mansione} editMode onChange={v=>setForm(p=>({...p,mansione:v}))} />
              <Field label="Livello" value={form.livello} editMode onChange={v=>setForm(p=>({...p,livello:v}))} />
              <Field label="CCNL" value={form.ccnl} editMode onChange={v=>setForm(p=>({...p,ccnl:v}))} />
              <Field label="Data Inizio" value={form.data_inizio} editMode onChange={v=>setForm(p=>({...p,data_inizio:v}))} type="date" />
              <Field label="Data Fine (vuoto se indeterminato)" value={form.data_fine} editMode onChange={v=>setForm(p=>({...p,data_fine:v}))} type="date" />
              <Field label="Retribuzione Lorda (€/mese)" value={form.retribuzione_lorda} editMode onChange={v=>setForm(p=>({...p,retribuzione_lorda:v}))} type="number" />
              <Field label="Ore Settimanali" value={form.ore_settimanali} editMode onChange={v=>setForm(p=>({...p,ore_settimanali:v}))} type="number" />
            </div>
            <Field label="Note" value={form.note} editMode onChange={v=>setForm(p=>({...p,note:v}))} multiline />
            <div style={{ display:'flex', gap:8, marginTop:8 }}>
              <button onClick={crea} disabled={saving} style={{padding:'8px 18px',background:'#22c55e',color:'white',border:'none',borderRadius:8,cursor:'pointer',fontWeight:600,fontSize:13}}>
                {saving?'Salvataggio…':'Salva Contratto'}
              </button>
              <button onClick={()=>setShowForm(false)} style={{padding:'8px 14px',background:'#f1f5f9',border:'none',borderRadius:8,cursor:'pointer',fontSize:13}}>Annulla</button>
            </div>
          </div>
        )}

        {contratti.length === 0 ? (
          <EmptyState icon={Briefcase} text="Nessun contratto registrato" sub="Clicca su 'Nuovo Contratto' per aggiungerne uno." />
        ) : contratti.map((c, i) => {
          const sc = STATI_COLOR[c.stato] || STATI_COLOR.bozza;
          const inScadenza = c.data_fine && c.stato === 'attivo' &&
            new Date(c.data_fine) < new Date(Date.now() + 60*24*3600*1000);
          return (
            <div key={c.id||i} style={{
              border:`1px solid ${inScadenza?'#fbbf24':COLORS.border}`,
              borderLeft:`4px solid ${inScadenza?'#f59e0b':COLORS.primary}`,
              borderRadius:10, padding:'14px 16px', marginBottom:10,
              background: i===0?'white':'white',
            }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', flexWrap:'wrap', gap:8 }}>
                <div>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                    <span style={{ fontWeight:700, fontSize:15, color:COLORS.text }}>
                      {c.tipo_contratto || 'Contratto'}
                    </span>
                    <Badge label={c.stato||'—'} bg={sc.bg} color={sc.color} />
                    {inScadenza && <Badge label="⚠ In scadenza" bg="#fef3c7" color="#92400e" />}
                  </div>
                  <div style={{ fontSize:12, color:COLORS.textMuted }}>
                    📅 {fmtD(c.data_inizio)} → {c.data_fine ? fmtD(c.data_fine) : <strong style={{color:COLORS.success}}>In corso</strong>}
                  </div>
                  {c.mansione && <div style={{ fontSize:12, color:COLORS.textMuted, marginTop:2 }}>👤 {c.mansione} — Livello {c.livello||'N/D'}</div>}
                  {c.ccnl && <div style={{ fontSize:12, color:COLORS.textMuted }}>📋 CCNL: {c.ccnl}</div>}
                </div>
                <div style={{ textAlign:'right' }}>
                  <div style={{ fontWeight:800, fontSize:17, color:COLORS.primary }}>{fmt€(c.retribuzione_lorda)}</div>
                  <div style={{ fontSize:11, color:COLORS.textMuted }}>lordo/mese</div>
                  <div style={{ fontSize:11, color:COLORS.textMuted }}>{c.ore_settimanali||40}h/sett.</div>
                  {c.stato === 'attivo' && (
                    <button onClick={()=>termina(c.id, c.data_fine)} style={{
                      marginTop:8, padding:'4px 10px', background:'#fee2e2', color:'#dc2626',
                      border:'none', borderRadius:6, cursor:'pointer', fontSize:11,
                    }}>Termina</button>
                  )}
                </div>
              </div>
              {c.note && <div style={{ fontSize:12, color:COLORS.textMuted, marginTop:8, borderTop:`1px solid ${COLORS.border}30`, paddingTop:8 }}>📝 {c.note}</div>}
            </div>
          );
        })}
      </Section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB PRESENZE
// ─────────────────────────────────────────────────────────────────────────────
function TabPresenze({ dip }) {
  const isMobile = useIsMobile();
  const today = new Date();
  const [anno, setAnno] = useState(today.getFullYear());
  const [mese, setMese] = useState(today.getMonth()+1);
  const [celle, setCelle] = useState({});
  const [tipologie, setTipologie] = useState([]);
  const [loading, setLoading] = useState(true);
  // Editor inline cella
  const [editingDate, setEditingDate] = useState(null);  // 'YYYY-MM-DD' | null
  const [editForm, setEditForm] = useState({ stato:'', ore:8, protocollo:'', note:'' });
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState(null);
  // Bump per riload dati dopo save (evita race con AbortController)
  const [reloadBump, setReloadBump] = useState(0);
  // Multi-select: quando attivo, click su cella la aggiunge/rimuove dall'insieme
  const [multiMode, setMultiMode] = useState(false);
  const [selected, setSelected] = useState(new Set()); // Set di 'YYYY-MM-DD'
  const [showBulkEditor, setShowBulkEditor] = useState(false);
  // Anchor per shift+click range select (ultimo giorno cliccato)
  const [lastClickedDate, setLastClickedDate] = useState(null);

  useAbortableEffect((signal) => {
    api.get('/api/attendance/tipologie-giustificativi', { signal })
      .then(r=>{ if(!signal?.aborted) setTipologie(r.data?.tipologie||[]); })
      .catch(e=>{ if(!isCanceledError(e)) setTipologie([]); });
  }, []);

  useAbortableEffect((signal) => {
    if (!dip?.id) return;
    setLoading(true);
    api.get('/api/attendance/month-grid', { params:{ anno, mese }, signal })
      .then(r=>{
        if (signal?.aborted) return;
        const map = {};
        (r.data?.celle||[]).forEach(c=>{
          if (c.employee_id === dip.id || c.employee_id === dip.codice_fiscale)
            map[c.data] = { stato:c.stato, ore:c.ore, protocollo:c.protocollo, note:c.note };
        });
        setCelle(map);
      })
      .catch(e=>{ if(!isCanceledError(e)) setCelle({}); })
      .finally(()=>{ if(!signal?.aborted) setLoading(false); });
  }, [dip?.id, dip?.codice_fiscale, anno, mese, reloadBump]);

  // Apre editor per una data, precompilando con la cella esistente (se c'è)
  const openEditor = (ds) => {
    const ex = celle[ds] || {};
    setEditForm({
      stato: ex.stato || '',
      ore: ex.ore != null ? Number(ex.ore) : 8,
      protocollo: ex.protocollo || '',
      note: ex.note || '',
    });
    setEditError(null);
    setEditingDate(ds);
  };

  // Click su cella: gestisce 3 casi (single, multi-toggle, shift-range)
  const handleCellClick = (ds, event) => {
    // Modalità singola: apre subito la modale
    if (!multiMode) {
      setLastClickedDate(ds);
      openEditor(ds);
      return;
    }
    // Modalità multi: shift+click selezione range, click semplice toggle singolo
    if (event?.shiftKey && lastClickedDate) {
      const range = computeDateRange(lastClickedDate, ds);
      setSelected(prev => {
        const next = new Set(prev);
        range.forEach(d => next.add(d));
        return next;
      });
    } else {
      setSelected(prev => {
        const next = new Set(prev);
        if (next.has(ds)) next.delete(ds); else next.add(ds);
        return next;
      });
    }
    setLastClickedDate(ds);
  };

  // Quick action: seleziona tutti i giorni feriali del mese (lun-ven)
  const selectWeekdays = () => {
    const next = new Set();
    for (let g = 1; g <= giorniMese; g++) {
      const d = new Date(anno, mese - 1, g);
      const dow = d.getDay();
      if (dow >= 1 && dow <= 5) {
        next.add(`${anno}-${String(mese).padStart(2,'0')}-${String(g).padStart(2,'0')}`);
      }
    }
    setSelected(next);
  };

  // Quick action: seleziona tutti i giorni del mese
  const selectAll = () => {
    const next = new Set();
    for (let g = 1; g <= giorniMese; g++) {
      next.add(`${anno}-${String(mese).padStart(2,'0')}-${String(g).padStart(2,'0')}`);
    }
    setSelected(next);
  };

  const clearSelection = () => {
    setSelected(new Set());
    setLastClickedDate(null);
  };

  const exitMultiMode = () => {
    setMultiMode(false);
    clearSelection();
  };

  const closeEditor = () => {
    setEditingDate(null);
    setEditError(null);
  };

  const saveCell = async () => {
    if (!editingDate) return;
    if (!editForm.stato) {
      setEditError('Seleziona uno stato (FE, MA, RL, ecc.)');
      return;
    }
    // Protocollo obbligatorio per malattia/infortunio/congedo
    if (['MA','SM','IN','CO'].includes(editForm.stato) && !editForm.protocollo.trim()) {
      setEditError('Protocollo INPS o certificato obbligatorio per ' + editForm.stato);
      return;
    }
    setEditLoading(true);
    setEditError(null);
    try {
      await api.post('/api/attendance/batch-insert', {
        employee_ids: [dip.id],
        giorni: [editingDate],
        stato: editForm.stato,
        ore: editForm.ore != null ? Number(editForm.ore) : 8,
        protocollo: editForm.protocollo.trim(),
        note: editForm.note.trim(),
      });
      closeEditor();
      setReloadBump(b => b+1);
    } catch (e) {
      setEditError(e.response?.data?.detail || e.message);
    } finally {
      setEditLoading(false);
    }
  };

  const deleteCell = async () => {
    if (!editingDate) return;
    if (!window.confirm(`Eliminare la presenza del ${editingDate}?`)) return;
    setEditLoading(true);
    setEditError(null);
    try {
      await api.delete('/api/attendance/presenza', {
        params: { employee_id: dip.id, data: editingDate },
      });
      closeEditor();
      setReloadBump(b => b+1);
    } catch (e) {
      setEditError(e.response?.data?.detail || e.message);
    } finally {
      setEditLoading(false);
    }
  };

  // Salva massivamente lo stesso stato/ore/protocollo/note su tutti i giorni
  // selezionati. Usato dal bulk editor in modalità multi-select.
  const bulkSave = async (form) => {
    const giorni = Array.from(selected).sort();
    if (!giorni.length) {
      throw new Error('Nessun giorno selezionato');
    }
    if (!form.stato) {
      throw new Error('Seleziona uno stato');
    }
    if (['MA','SM','IN','CO'].includes(form.stato) && !form.protocollo.trim()) {
      throw new Error('Protocollo obbligatorio per ' + form.stato);
    }
    await api.post('/api/attendance/batch-insert', {
      employee_ids: [dip.id],
      giorni,
      stato: form.stato,
      ore: form.ore != null ? Number(form.ore) : 8,
      protocollo: form.protocollo.trim(),
      note: form.note.trim(),
    });
    setShowBulkEditor(false);
    clearSelection();
    setReloadBump(b => b+1);
  };

  // Cancella tutti i giorni selezionati
  const bulkDelete = async () => {
    const giorni = Array.from(selected).sort();
    if (!giorni.length) return;
    if (!window.confirm(`Eliminare la presenza per ${giorni.length} giorni selezionati?`)) return;
    // Loop sequenziale per evitare flooding API; sono tipicamente ≤31 chiamate
    for (const ds of giorni) {
      try {
        await api.delete('/api/attendance/presenza', {
          params: { employee_id: dip.id, data: ds },
        });
      } catch {
        // continua col prossimo, errori isolati non bloccano
      }
    }
    clearSelection();
    setReloadBump(b => b+1);
  };

  const giorniMese = new Date(anno, mese, 0).getDate();
  const stats = useMemo(()=>{
    const s={ presenti:0, ferie:0, malattia:0, permessi:0, assenti:0, ore:0 };
    Object.values(celle).forEach(c=>{
      const code=(c.stato||'').toUpperCase();
      s.ore+=parseFloat(c.ore||0);
      if(!code||code==='P') s.presenti++;
      else if(code==='FE'||code==='FER'||code==='FR') s.ferie++;
      else if(code==='MA'||code==='IN'||code==='SM') s.malattia++;
      else if(code.startsWith('PE')||code==='RL'||code==='ROL') s.permessi++;
      else if(code==='AI') s.assenti++;
    });
    return s;
  }, [celle]);

  const colorByCode = (code) => {
    if (!code) return null;
    const t = tipologie.find(t=>t.codice===code);
    return t?.colore || null;
  };
  const lighten = hex => hex&&hex.startsWith('#')&&hex.length===7 ? `${hex}22` : '#e2e8f0';

  const MESI = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre'];
  const DOW = ['Dom','Lun','Mar','Mer','Gio','Ven','Sab'];

  return (
    <div>
      {/* Selettori */}
      <div style={{ display:'flex', gap:10, flexWrap:'wrap', marginBottom:16, alignItems:'center' }}>
        <select value={mese} onChange={e=>setMese(parseInt(e.target.value))}
          style={{ padding:'7px 12px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, fontWeight:600, background:'white', cursor:'pointer' }}>
          {MESI.map((m,i)=><option key={i} value={i+1}>{m}</option>)}
        </select>
        <select value={anno} onChange={e=>setAnno(parseInt(e.target.value))}
          style={{ padding:'7px 12px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, fontWeight:600, background:'white', cursor:'pointer' }}>
          {Array.from({length:5},(_,i)=>today.getFullYear()-i).map(a=><option key={a}>{a}</option>)}
        </select>
        <div style={{ flex:1, fontSize:12, color:COLORS.textMuted }}>
          {Object.keys(celle).length} giorni registrati
        </div>
        <button
          onClick={()=>{ if(multiMode) exitMultiMode(); else setMultiMode(true); }}
          title={multiMode?'Esci da modalità multi-select':'Attiva modalità multi-select per applicare lo stesso stato a più giorni'}
          style={{
            padding:'6px 12px',
            background: multiMode ? COLORS.primary : 'transparent',
            color: multiMode ? 'white' : COLORS.primary,
            border: `1px solid ${COLORS.primary}`,
            borderRadius:6, cursor:'pointer', fontSize:12, fontWeight:600,
            display:'flex', alignItems:'center', gap:4,
          }}
        >
          {multiMode ? '✓ Multi-select attivo' : '☑ Multi-select'}
        </button>
        <a href="/presenze" style={{ fontSize:12, color:COLORS.primary, fontWeight:600, display:'flex', alignItems:'center', gap:4 }}>
          <ExternalLink size={12}/> Gestisci presenze
        </a>
      </div>

      {/* Toolbar multi-select (visibile solo in modalità multi) */}
      {multiMode && (
        <div style={{
          marginBottom:14, padding:'12px 14px',
          background:'linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%)',
          border:'1px solid #93c5fd', borderRadius:10,
          display:'flex', alignItems:'center', gap:10, flexWrap:'wrap',
        }}>
          <div style={{ fontSize:13, fontWeight:700, color:'#1e3a8a' }}>
            {selected.size === 0 ? '☑ Seleziona i giorni cliccando' : `📌 ${selected.size} giorn${selected.size===1?'o':'i'} selezionat${selected.size===1?'o':'i'}`}
          </div>
          <div style={{ flex:1, minWidth:8 }}/>
          <button
            onClick={selectWeekdays}
            disabled={selected.size === giorniMese}
            style={smallBtn('#0891b2')}
            title="Seleziona tutti i lunedì-venerdì del mese"
          >
            Lun-Ven
          </button>
          <button
            onClick={selectAll}
            style={smallBtn('#0891b2')}
            title="Seleziona tutti i giorni del mese"
          >
            Tutto il mese
          </button>
          {selected.size > 0 && (
            <>
              <button
                onClick={clearSelection}
                style={smallBtn('#64748b')}
                title="Deseleziona tutti"
              >
                Pulisci
              </button>
              <button
                onClick={bulkDelete}
                style={smallBtn(COLORS.danger)}
                title="Elimina presenze sui giorni selezionati"
              >
                🗑️ Elimina ({selected.size})
              </button>
              <button
                onClick={()=>setShowBulkEditor(true)}
                style={{
                  padding:'6px 14px',
                  background:'linear-gradient(135deg, #16a34a 0%, #15803d 100%)',
                  color:'white', border:'none', borderRadius:6,
                  cursor:'pointer', fontSize:12, fontWeight:700,
                }}
                title="Applica lo stesso stato a tutti i giorni selezionati"
              >
                💾 Applica stato ({selected.size})
              </button>
            </>
          )}
          <button onClick={exitMultiMode} style={smallBtn('#64748b')} title="Esci dalla modalità multi-select">
            ✕ Esci
          </button>
        </div>
      )}

      {/* KPI */}
      <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr 1fr':'repeat(5,1fr)', gap:10, marginBottom:16 }}>
        {[
          {label:'Presenti', value:stats.presenti, color:'#16a34a'},
          {label:'Ferie',    value:stats.ferie,    color:'#1d4ed8'},
          {label:'Malattia', value:stats.malattia, color:'#d97706'},
          {label:'Permessi', value:stats.permessi, color:'#7c3aed'},
          {label:'Ore tot.', value:stats.ore.toFixed(0)+'h', color:COLORS.primary},
        ].map(s=>(
          <div key={s.label} style={{ background:'white', border:`1px solid ${COLORS.border}`, borderRadius:10, padding:'10px 12px', borderTop:`3px solid ${s.color}` }}>
            <div style={{ fontSize:10, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase' }}>{s.label}</div>
            <div style={{ fontSize:18, fontWeight:800, color:s.color, marginTop:2 }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Calendario */}
      {loading ? (
        <div style={{ padding:40, textAlign:'center', color:COLORS.textMuted }}>Caricamento…</div>
      ) : (
        <div style={{ background:'white', border:`1px solid ${COLORS.border}`, borderRadius:12, padding:16 }}>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:5 }}>
            {['Lun','Mar','Mer','Gio','Ven','Sab','Dom'].map(d=>(
              <div key={d} style={{ fontSize:10, fontWeight:700, color:COLORS.textMuted, textAlign:'center', padding:'6px 0', textTransform:'uppercase', letterSpacing:'0.05em' }}>{d}</div>
            ))}
            {Array.from({length:(()=>{ const p=new Date(anno,mese-1,1).getDay(); return p===0?6:p-1; })()},(_,i)=>(
              <div key={'e'+i}/>
            ))}
            {Array.from({length:giorniMese},(_,i)=>{
              const g=i+1;
              const ds=`${anno}-${String(mese).padStart(2,'0')}-${String(g).padStart(2,'0')}`;
              const cella=celle[ds];
              const dow=new Date(anno,mese-1,g).getDay();
              const isWe=dow===0||dow===6;
              const code=cella?.stato;
              const colore=code?colorByCode(code):null;
              const isSelected = multiMode && selected.has(ds);
              const bg = isSelected
                ? '#dbeafe'
                : (code && colore ? lighten(colore) : (isWe ? '#f8fafc' : 'white'));
              const borderColor = isSelected
                ? '#1d4ed8'
                : (code && colore ? colore + '44' : COLORS.border);
              const borderWidth = isSelected ? 2 : 1;
              return (
                <div key={g}
                  onClick={(e) => handleCellClick(ds, e)}
                  title={
                    multiMode
                      ? (isSelected
                          ? `${DOW[dow]} ${g}/${mese} — selezionato (clicca per deselezionare; shift+click per range)`
                          : `${DOW[dow]} ${g}/${mese} — clicca per selezionare (shift+click per range)`)
                      : (cella
                          ? `${DOW[dow]} ${g}/${mese}: ${code||'P'} ${cella.ore||''}h — clicca per modificare`
                          : `${DOW[dow]} ${g}/${mese} — clicca per inserire`)
                  }
                  style={{
                    aspectRatio:'1', padding:4,
                    border:`${borderWidth}px solid ${borderColor}`,
                    borderRadius:8, backgroundColor:bg,
                    display:'flex', flexDirection:'column', justifyContent:'space-between', alignItems:'flex-start',
                    fontSize:11, cursor:'pointer', transition:'transform 0.1s, box-shadow 0.1s',
                    position:'relative',
                  }}
                  onMouseEnter={e=>{ e.currentTarget.style.transform='scale(1.05)'; e.currentTarget.style.boxShadow='0 2px 6px rgba(15,39,68,0.15)'; e.currentTarget.style.zIndex='1'; }}
                  onMouseLeave={e=>{ e.currentTarget.style.transform=''; e.currentTarget.style.boxShadow=''; e.currentTarget.style.zIndex=''; }}
                >
                  <span style={{ fontWeight:700, color:isWe?COLORS.danger:COLORS.text }}>{g}</span>
                  {code && (
                    <span style={{ fontSize:8, fontWeight:800, color:colore||COLORS.text, padding:'1px 4px', borderRadius:3, background:'white', alignSelf:'center' }}>
                      {code}
                    </span>
                  )}
                  {isSelected && (
                    <div style={{
                      position:'absolute', top:2, right:2,
                      background:'#1d4ed8', color:'white',
                      width:14, height:14, borderRadius:'50%',
                      display:'flex', alignItems:'center', justifyContent:'center',
                      fontSize:9, fontWeight:700, lineHeight:1,
                    }}>✓</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Legenda */}
      {tipologie.length > 0 && (
        <div style={{ display:'flex', gap:12, flexWrap:'wrap', marginTop:12, padding:10, background:'#f8fafc', borderRadius:8, fontSize:11 }}>
          {tipologie.slice(0,12).map(t=>(
            <span key={t.codice} style={{ display:'inline-flex', alignItems:'center', gap:4 }}>
              <span style={{ width:10, height:10, borderRadius:3, background:lighten(t.colore), border:`1px solid ${t.colore||COLORS.border}`, display:'inline-block' }}/>
              <strong style={{ color:COLORS.text }}>{t.codice}</strong> {t.nome}
            </span>
          ))}
        </div>
      )}

      <div style={{ marginTop:10, fontSize:11, color:COLORS.textMuted, fontStyle:'italic' }}>
        💡 Clicca su un giorno per inserire/modificare. Attiva <strong>Multi-select</strong> per applicare lo stesso stato a più giorni in una volta (anche con shift+click per range).
      </div>

      {/* Editor cella inline (singolo giorno) */}
      {editingDate && (
        <CellEditorModal
          date={editingDate}
          dipNome={`${dip.cognome||''} ${dip.nome||''}`.trim()}
          form={editForm}
          setForm={setEditForm}
          tipologie={tipologie}
          loading={editLoading}
          error={editError}
          existingCell={celle[editingDate]}
          onSave={saveCell}
          onDelete={deleteCell}
          onClose={closeEditor}
        />
      )}

      {/* Editor bulk (più giorni in modalità multi-select) */}
      {showBulkEditor && selected.size > 0 && (
        <BulkEditorModal
          dipNome={`${dip.cognome||''} ${dip.nome||''}`.trim()}
          giorni={Array.from(selected).sort()}
          tipologie={tipologie}
          onSave={bulkSave}
          onClose={()=>setShowBulkEditor(false)}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Editor inline cella di presenza (popover modale)
// ─────────────────────────────────────────────────────────────────────────────
function CellEditorModal({ date, dipNome, form, setForm, tipologie, loading, error, existingCell, onSave, onDelete, onClose }) {
  // Format data leggibile (es. "Lunedì 15 Aprile 2026")
  const dt = new Date(date + 'T00:00:00');
  const dayName = ['Domenica','Lunedì','Martedì','Mercoledì','Giovedì','Venerdì','Sabato'][dt.getDay()];
  const monthName = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre'][dt.getMonth()];
  const dataLeggibile = `${dayName} ${dt.getDate()} ${monthName} ${dt.getFullYear()}`;

  // Stati comuni in primo piano + tutti gli altri ordinati
  const STATI_COMUNI = ['FE','MA','RL','PE','IN','CO','LU','RC'];
  const stati = useMemo(() => {
    const tipMap = {};
    (tipologie || []).forEach(t => { tipMap[t.codice] = t; });
    const comuni = STATI_COMUNI.filter(c => tipMap[c]).map(c => tipMap[c]);
    const altri = (tipologie || []).filter(t => !STATI_COMUNI.includes(t.codice))
      .sort((a, b) => (a.codice || '').localeCompare(b.codice || ''));
    return [...comuni, ...altri];
  }, [tipologie]);

  const isMA = ['MA','SM','IN','CO'].includes(form.stato);
  const isExisting = !!existingCell?.stato;

  return (
    <div onClick={onClose}
      style={{ position:'fixed', inset:0, background:'rgba(15,39,68,0.6)', zIndex:1100, display:'flex', alignItems:'center', justifyContent:'center', padding:20 }}
    >
      <div onClick={e=>e.stopPropagation()}
        style={{ background:'white', borderRadius:12, width:'100%', maxWidth:520, padding:24, boxShadow:'0 20px 60px rgba(0,0,0,0.3)' }}
      >
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:COLORS.textMuted, textTransform:'uppercase', letterSpacing:'0.05em', fontWeight:700 }}>
            {isExisting ? '✏️ Modifica presenza' : '➕ Inserisci presenza'}
          </div>
          <h2 style={{ margin:'4px 0 2px', fontSize:18, color:COLORS.primary }}>{dataLeggibile}</h2>
          <div style={{ fontSize:12, color:COLORS.textMuted }}>{dipNome}</div>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Stato *</div>
            <select
              value={form.stato}
              onChange={e=>setForm(f=>({...f, stato:e.target.value}))}
              autoFocus
              style={{ width:'100%', padding:'10px 12px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:14, fontWeight:600, background:'white' }}
            >
              <option value="">— Seleziona —</option>
              {stati.map(t => (
                <option key={t.codice} value={t.codice}>
                  {t.codice} — {t.nome}
                </option>
              ))}
            </select>
          </label>

          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Ore</div>
              <input
                type="number"
                step="0.25"
                min="0"
                max="24"
                value={form.ore}
                onChange={e=>setForm(f=>({...f, ore:e.target.value}))}
                style={{ width:'100%', padding:'8px 10px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, boxSizing:'border-box' }}
              />
            </label>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>
                Protocollo {isMA && <span style={{ color:COLORS.danger }}>*</span>}
              </div>
              <input
                type="text"
                value={form.protocollo}
                onChange={e=>setForm(f=>({...f, protocollo:e.target.value}))}
                placeholder={isMA ? 'INPS/Cert. medico' : '(opzionale)'}
                style={{ width:'100%', padding:'8px 10px', border:`1px solid ${isMA && !form.protocollo ? '#fca5a5' : COLORS.border}`, borderRadius:8, fontSize:13, boxSizing:'border-box' }}
              />
            </label>
          </div>

          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Note</div>
            <textarea
              value={form.note}
              onChange={e=>setForm(f=>({...f, note:e.target.value}))}
              rows={2}
              style={{ width:'100%', padding:'8px 10px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, fontFamily:'inherit', resize:'vertical', boxSizing:'border-box' }}
            />
          </label>

          {isMA && (
            <div style={{ padding:8, background:'#fef3c7', border:'1px solid #fcd34d', borderRadius:6, fontSize:11, color:'#92400e' }}>
              ⚠️ Per malattia/infortunio/congedo è obbligatorio inserire un protocollo (INPS o certificato medico)
            </div>
          )}

          {error && (
            <div style={{ padding:10, background:'#fee2e2', border:'1px solid #fca5a5', borderRadius:6, color:'#b91c1c', fontSize:13 }}>
              ⚠️ {error}
            </div>
          )}
        </div>

        <div style={{ marginTop:20, display:'flex', justifyContent:'space-between', alignItems:'center', gap:8 }}>
          <div>
            {isExisting && (
              <button
                onClick={onDelete}
                disabled={loading}
                style={{ padding:'8px 14px', background:'transparent', color:COLORS.danger, border:`1px solid ${COLORS.danger}`, borderRadius:6, cursor:loading?'not-allowed':'pointer', fontSize:12, fontWeight:600 }}
                title="Elimina questa cella di presenza"
              >
                🗑️ Elimina
              </button>
            )}
          </div>
          <div style={{ display:'flex', gap:8 }}>
            <button
              onClick={onClose}
              disabled={loading}
              style={{ padding:'8px 16px', background:'white', color:COLORS.textMuted, border:`1px solid ${COLORS.border}`, borderRadius:6, cursor:'pointer', fontSize:13 }}
            >
              Annulla
            </button>
            <button
              onClick={onSave}
              disabled={loading || !form.stato}
              style={{
                padding:'8px 18px',
                background: form.stato && !loading ? 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)' : '#cbd5e1',
                color:'white', border:'none', borderRadius:6,
                cursor: form.stato && !loading ? 'pointer' : 'not-allowed',
                fontSize:13, fontWeight:600,
              }}
            >
              {loading ? '⏳ Salvataggio…' : '💾 Salva'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper per bottoni piccoli della toolbar multi-select
function smallBtn(color) {
  return {
    padding:'5px 10px',
    background:'transparent',
    color: color,
    border: `1px solid ${color}`,
    borderRadius:6,
    cursor:'pointer',
    fontSize:11,
    fontWeight:600,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Editor BULK: applica stesso stato/ore/protocollo/note a un set di giorni
// ─────────────────────────────────────────────────────────────────────────────
function BulkEditorModal({ dipNome, giorni, tipologie, onSave, onClose }) {
  const [form, setForm] = useState({ stato:'', ore:8, protocollo:'', note:'' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const STATI_COMUNI = ['FE','MA','RL','PE','IN','CO','LU','RC'];
  const stati = useMemo(() => {
    const tipMap = {};
    (tipologie || []).forEach(t => { tipMap[t.codice] = t; });
    const comuni = STATI_COMUNI.filter(c => tipMap[c]).map(c => tipMap[c]);
    const altri = (tipologie || []).filter(t => !STATI_COMUNI.includes(t.codice))
      .sort((a, b) => (a.codice || '').localeCompare(b.codice || ''));
    return [...comuni, ...altri];
  }, [tipologie]);

  const isMA = ['MA','SM','IN','CO'].includes(form.stato);

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      await onSave(form);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  // Range visualizzazione (es. "1-5 e 8-12 Aprile" oppure "12 giorni sparsi")
  const rangeText = useMemo(() => {
    if (giorni.length === 0) return '';
    if (giorni.length === 1) return giorni[0];
    // Raggruppa contigui
    const groups = [];
    let cur = [giorni[0]];
    for (let i = 1; i < giorni.length; i++) {
      const prevDate = new Date(giorni[i-1] + 'T00:00:00');
      const thisDate = new Date(giorni[i] + 'T00:00:00');
      const diff = (thisDate - prevDate) / (1000*60*60*24);
      if (diff === 1) {
        cur.push(giorni[i]);
      } else {
        groups.push(cur);
        cur = [giorni[i]];
      }
    }
    groups.push(cur);
    // Formatta come "1-5", "8" ecc.
    const monthIdx = parseInt(giorni[0].split('-')[1], 10) - 1;
    const monthName = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'][monthIdx];
    return groups.map(g => {
      const startDay = parseInt(g[0].split('-')[2], 10);
      if (g.length === 1) return startDay;
      const endDay = parseInt(g[g.length-1].split('-')[2], 10);
      return `${startDay}-${endDay}`;
    }).join(', ') + ' ' + monthName;
  }, [giorni]);

  return (
    <div onClick={onClose}
      style={{ position:'fixed', inset:0, background:'rgba(15,39,68,0.6)', zIndex:1100, display:'flex', alignItems:'center', justifyContent:'center', padding:20 }}
    >
      <div onClick={e=>e.stopPropagation()}
        style={{ background:'white', borderRadius:12, width:'100%', maxWidth:560, padding:24, boxShadow:'0 20px 60px rgba(0,0,0,0.3)', maxHeight:'90vh', overflowY:'auto' }}
      >
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:COLORS.textMuted, textTransform:'uppercase', letterSpacing:'0.05em', fontWeight:700 }}>
            📌 Applica stato a {giorni.length} giorni
          </div>
          <h2 style={{ margin:'4px 0 2px', fontSize:18, color:COLORS.primary }}>{rangeText}</h2>
          <div style={{ fontSize:12, color:COLORS.textMuted }}>{dipNome}</div>
        </div>

        {/* Anteprima giorni selezionati (collassata se troppi) */}
        <details style={{ marginBottom:14, fontSize:12, color:COLORS.textMuted }}>
          <summary style={{ cursor:'pointer', padding:6 }}>
            Vedi i {giorni.length} giorni selezionati
          </summary>
          <div style={{ marginTop:6, padding:8, background:'#f8fafc', borderRadius:6, fontFamily:'monospace', fontSize:11, lineHeight:1.6 }}>
            {giorni.join(', ')}
          </div>
        </details>

        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Stato *</div>
            <select
              value={form.stato}
              onChange={e=>setForm(f=>({...f, stato:e.target.value}))}
              autoFocus
              style={{ width:'100%', padding:'10px 12px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:14, fontWeight:600, background:'white' }}
            >
              <option value="">— Seleziona —</option>
              {stati.map(t => (
                <option key={t.codice} value={t.codice}>
                  {t.codice} — {t.nome}
                </option>
              ))}
            </select>
          </label>

          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Ore (per giorno)</div>
              <input
                type="number"
                step="0.25"
                min="0"
                max="24"
                value={form.ore}
                onChange={e=>setForm(f=>({...f, ore:e.target.value}))}
                style={{ width:'100%', padding:'8px 10px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, boxSizing:'border-box' }}
              />
            </label>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>
                Protocollo {isMA && <span style={{ color:COLORS.danger }}>*</span>}
              </div>
              <input
                type="text"
                value={form.protocollo}
                onChange={e=>setForm(f=>({...f, protocollo:e.target.value}))}
                placeholder={isMA ? 'INPS/Cert. medico' : '(opzionale)'}
                style={{ width:'100%', padding:'8px 10px', border:`1px solid ${isMA && !form.protocollo ? '#fca5a5' : COLORS.border}`, borderRadius:8, fontSize:13, boxSizing:'border-box' }}
              />
            </label>
          </div>

          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Note</div>
            <textarea
              value={form.note}
              onChange={e=>setForm(f=>({...f, note:e.target.value}))}
              rows={2}
              style={{ width:'100%', padding:'8px 10px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, fontFamily:'inherit', resize:'vertical', boxSizing:'border-box' }}
            />
          </label>

          {isMA && (
            <div style={{ padding:8, background:'#fef3c7', border:'1px solid #fcd34d', borderRadius:6, fontSize:11, color:'#92400e' }}>
              ⚠️ Per malattia/infortunio/congedo è obbligatorio inserire un protocollo (INPS o certificato medico)
            </div>
          )}

          <div style={{ padding:10, background:'#fef3c7', border:'1px solid #fcd34d', borderRadius:6, fontSize:12, color:'#92400e' }}>
            ⚠️ <strong>Attenzione</strong>: l'azione sovrascriverà presenze già esistenti su questi {giorni.length} giorni.
          </div>

          {error && (
            <div style={{ padding:10, background:'#fee2e2', border:'1px solid #fca5a5', borderRadius:6, color:'#b91c1c', fontSize:13 }}>
              ⚠️ {error}
            </div>
          )}
        </div>

        <div style={{ marginTop:20, display:'flex', justifyContent:'flex-end', gap:8 }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{ padding:'8px 16px', background:'white', color:COLORS.textMuted, border:`1px solid ${COLORS.border}`, borderRadius:6, cursor:'pointer', fontSize:13 }}
          >
            Annulla
          </button>
          <button
            onClick={submit}
            disabled={loading || !form.stato}
            style={{
              padding:'8px 18px',
              background: form.stato && !loading ? 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)' : '#cbd5e1',
              color:'white', border:'none', borderRadius:6,
              cursor: form.stato && !loading ? 'pointer' : 'not-allowed',
              fontSize:13, fontWeight:600,
            }}
          >
            {loading ? '⏳ Applicazione…' : `💾 Applica a ${giorni.length} giorni`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB CEDOLINI
// ─────────────────────────────────────────────────────────────────────────────
function TabCedolini({ dip }) {
  const isMobile = useIsMobile();
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  // Modale scalatura acconti per il cedolino selezionato
  const [scalaCedolino, setScalaCedolino] = useState(null); // cedolino object | null
  const [reloadBump, setReloadBump] = useState(0);

  const load = useCallback((signal) => {
    setLoading(true);
    api.get(`/api/cedolini/dipendente/${dip.id || dip.codice_fiscale}?anno=${anno}`, { signal })
      .then(r=>{ if(!signal?.aborted) setData(r.data); })
      .catch(e=>{ if(!isCanceledError(e)) setData(null); })
      .finally(()=>{ if(!signal?.aborted) setLoading(false); });
  }, [dip.id, dip.codice_fiscale, anno, reloadBump]);

  useAbortableEffect(load, [load]);

  const cedolini = data?.cedolini || [];
  const totNetto = cedolini.reduce((s,c)=>s+parseFloat(c.netto||c.netto_mese||0),0);
  const totLordo = cedolini.reduce((s,c)=>s+parseFloat(c.lordo||0),0);
  const totTFR   = cedolini.reduce((s,c)=>s+parseFloat(c.tfr||c.tfr_mese||0),0);

  const MESI_C = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <h3 style={{ margin:0, fontSize:15, fontWeight:700 }}>Cedolini Paga</h3>
        <div style={{ display:'flex', gap:8, alignItems:'center' }}>
          <a href="/cedolini" style={{ fontSize:12, color:COLORS.primary, fontWeight:600, display:'flex', alignItems:'center', gap:4 }}>
            <ExternalLink size={12}/> Import cedolini
          </a>
          <select value={anno} onChange={e=>setAnno(Number(e.target.value))}
            style={{ padding:'6px 12px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, background:'white' }}>
            {ANNI.map(a=><option key={a}>{a}</option>)}
          </select>
        </div>
      </div>

      {/* Riepilogo annuale */}
      {cedolini.length > 0 && (
        <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr':'repeat(3,1fr)', gap:12, marginBottom:20 }}>
          <KpiCard label="Netto Annuale" value={fmt€(totNetto)} color="#16a34a" icon={TrendingUp} sub={`${cedolini.length} cedolini`} />
          <KpiCard label="Lordo Annuale" value={fmt€(totLordo)} color={COLORS.primary} icon={FileText} />
          <KpiCard label="TFR Maturato" value={fmt€(totTFR)} color="#b8860b" icon={Award} />
        </div>
      )}

      {loading ? (
        <div style={{ padding:40, textAlign:'center', color:COLORS.textMuted }}>Caricamento…</div>
      ) : cedolini.length === 0 ? (
        <EmptyState icon={FileText} text={`Nessun cedolino per ${anno}`} sub="Importa i cedolini dalla sezione apposita." />
      ) : (
        <div style={{ background:'white', border:`1px solid ${COLORS.border}`, borderRadius:12, overflow:'hidden' }}>
          {/* Grafico mini a barre */}
          <div style={{ padding:'16px 20px', borderBottom:`1px solid ${COLORS.border}`, display:'flex', gap:4, alignItems:'flex-end', height:70 }}>
            {MESI_C.map((m,i)=>{
              const ced = cedolini.find(c=>(c.mese===i+1||c.mese===String(i+1)));
              const netto = parseFloat(ced?.netto||ced?.netto_mese||0);
              const maxV = Math.max(...cedolini.map(c=>parseFloat(c.netto||c.netto_mese||0)), 1);
              const h = netto>0 ? Math.max(4, (netto/maxV)*44) : 2;
              return (
                <div key={m} title={`${m}: ${fmt€(netto)}`} style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:3 }}>
                  <div style={{ width:'100%', height:h, background: netto>0 ? COLORS.primary : '#e2e8f0', borderRadius:'3px 3px 0 0', transition:'height 0.3s' }}/>
                  <div style={{ fontSize:8, color: ced ? COLORS.primary : COLORS.textMuted, fontWeight:600 }}>{m}</div>
                </div>
              );
            })}
          </div>

          {/* Lista cedolini */}
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
            <thead>
              <tr style={{ background:'#f8fafc' }}>
                {['Mese','Lordo','Netto','TFR','Stato','Acconti'].map(h=>(
                  <th key={h} style={{ padding:'10px 16px', textAlign:'left', fontSize:10, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase', letterSpacing:'0.05em', borderBottom:`1px solid ${COLORS.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cedolini.map((c,i)=>{
                const netto=parseFloat(c.netto||c.netto_mese||0);
                const lordo=parseFloat(c.lordo||0);
                const tfr=parseFloat(c.tfr||c.tfr_mese||0);
                const pagato=c.pagato||c.stato==='pagato';
                return (
                  <tr key={c.id||i} style={{ borderBottom:`1px solid ${COLORS.border}30`, background: i%2===0?'white':'#fafafa' }}>
                    <td style={{ padding:'12px 16px', fontWeight:600, color:COLORS.text }}>
                      {MESI_C[(c.mese||1)-1]} {c.anno||anno}
                    </td>
                    <td style={{ padding:'12px 16px', color:COLORS.textMuted }}>{fmt€(lordo)}</td>
                    <td style={{ padding:'12px 16px', fontWeight:700, color:'#16a34a' }}>{fmt€(netto)}</td>
                    <td style={{ padding:'12px 16px', color:'#b8860b' }}>{tfr>0?fmt€(tfr):'—'}</td>
                    <td style={{ padding:'12px 16px' }}>
                      <Badge label={pagato?'✓ Pagato':'Da pagare'} bg={pagato?'#dcfce7':'#fef9c3'} color={pagato?'#16a34a':'#a16207'} />
                    </td>
                    <td style={{ padding:'12px 16px' }}>
                      {c.id ? (
                        <button
                          onClick={()=>setScalaCedolino(c)}
                          title="Scala acconti registrati su questo cedolino"
                          style={{
                            padding:'5px 10px',
                            background:'transparent',
                            color:COLORS.primary,
                            border:`1px solid ${COLORS.primary}`,
                            borderRadius:6,
                            cursor:'pointer',
                            fontSize:11,
                            fontWeight:600,
                            display:'inline-flex',
                            alignItems:'center',
                            gap:4,
                          }}
                        >
                          🔗 Scala acconti
                        </button>
                      ) : (
                        <span style={{ fontSize:11, color:COLORS.textMuted }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modale scalatura acconti su cedolino */}
      {scalaCedolino && (
        <ScalaAccontiCedolinoModal
          cedolino={scalaCedolino}
          dipNome={`${dip.cognome||''} ${dip.nome||''}`.trim()}
          onClose={()=>setScalaCedolino(null)}
          onScaled={()=>{
            setScalaCedolino(null);
            setReloadBump(b=>b+1);
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Modale: scala acconti su cedolino paga
// Compara acconto_mese_precedente del cedolino con acconti registrati per
// il periodo, mostra match/discrepanza e permette scalatura (eventualmente
// forzata in caso di delta).
// ─────────────────────────────────────────────────────────────────────────────
function ScalaAccontiCedolinoModal({ cedolino, dipNome, onClose, onScaled }) {
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [applying, setApplying] = useState(false);
  const [forza, setForza] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.get(`/api/tfr/cedolini/${cedolino.id}/preview-scalatura-acconti`);
        if (!cancelled) setPreview(res.data);
      } catch (e) {
        if (!cancelled) setError(e.response?.data?.detail || e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [cedolino.id]);

  const applica = async () => {
    setApplying(true);
    setError(null);
    try {
      await api.post(`/api/tfr/cedolini/${cedolino.id}/scala-acconti`, {
        forza_anche_se_discrepanza: forza,
      });
      onScaled();
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (typeof detail === 'object') {
        setError(detail.messaggio || JSON.stringify(detail));
      } else {
        setError(detail || e.message);
      }
      setApplying(false);
    }
  };

  const stato = preview?.stato_match;
  const isQuadra = stato === 'quadra';
  const isDiscrepanza = stato === 'discrepanza';
  const isNessunDato = stato === 'nessun_dato' || stato === 'nessun_dato_cedolino' || stato === 'nessun_acconto';

  // Color scheme per stato match
  const banner = isQuadra
    ? { bg:'#dcfce7', border:'#86efac', color:'#15803d', icon:'✅' }
    : isDiscrepanza
      ? { bg:'#fef3c7', border:'#fcd34d', color:'#92400e', icon:'⚠️' }
      : { bg:'#fee2e2', border:'#fca5a5', color:'#b91c1c', icon:'⛔' };

  return (
    <div onClick={onClose}
      style={{ position:'fixed', inset:0, background:'rgba(15,39,68,0.6)', zIndex:1100, display:'flex', alignItems:'center', justifyContent:'center', padding:20 }}
    >
      <div onClick={e=>e.stopPropagation()}
        style={{ background:'white', borderRadius:12, width:'100%', maxWidth:680, maxHeight:'90vh', display:'flex', flexDirection:'column', boxShadow:'0 20px 60px rgba(0,0,0,0.3)' }}
      >
        {/* Header */}
        <div style={{
          padding:'16px 24px', borderBottom:`1px solid ${COLORS.border}`,
          background: 'linear-gradient(135deg, #0f2744 0%, #1a3a5f 100%)',
          borderRadius:'12px 12px 0 0', color:'white',
        }}>
          <div style={{ fontSize:11, opacity:0.8, textTransform:'uppercase', letterSpacing:'0.06em', fontWeight:700 }}>
            🔗 Scala acconti su cedolino
          </div>
          <div style={{ fontSize:17, fontWeight:700, marginTop:2 }}>
            {['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'][(cedolino.mese||1)-1]} {cedolino.anno}
          </div>
          <div style={{ fontSize:12, opacity:0.85 }}>{dipNome}</div>
        </div>

        {/* Body */}
        <div style={{ flex:1, overflowY:'auto', padding:20 }}>
          {loading && (
            <div style={{ padding:40, textAlign:'center', color:COLORS.textMuted }}>
              ⏳ Analisi cedolino in corso…
            </div>
          )}

          {error && !loading && (
            <div style={{ padding:12, background:'#fee2e2', border:'1px solid #fca5a5', borderRadius:8, color:'#b91c1c', fontSize:13 }}>
              ⚠️ {error}
            </div>
          )}

          {!loading && preview && (
            <>
              {/* Banner stato match */}
              <div style={{
                padding:'12px 14px',
                background: banner.bg,
                border: `1px solid ${banner.border}`,
                borderRadius: 8,
                color: banner.color,
                fontSize: 13,
                marginBottom: 16,
                display:'flex', gap:10, alignItems:'flex-start',
              }}>
                <span style={{ fontSize:18 }}>{banner.icon}</span>
                <div style={{ flex:1 }}>
                  <div style={{ fontWeight:700, marginBottom:2 }}>
                    {isQuadra && 'Match perfetto'}
                    {isDiscrepanza && 'Discrepanza rilevata'}
                    {stato === 'nessun_acconto' && 'Nessun acconto registrato'}
                    {stato === 'nessun_dato_cedolino' && 'Cedolino senza dato AI'}
                    {stato === 'nessun_dato' && 'Nessun dato disponibile'}
                  </div>
                  <div>{preview.messaggio}</div>
                </div>
              </div>

              {/* Confronto numerico */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:16 }}>
                <KpiCard
                  label="Cedolino dichiara"
                  value={preview.acconto_mese_precedente != null
                    ? fmt€(preview.acconto_mese_precedente)
                    : '— non disponibile'
                  }
                  color={preview.acconto_mese_precedente != null ? COLORS.primary : COLORS.textMuted}
                />
                <KpiCard
                  label="Sistema registra"
                  value={fmt€(preview.totale_acconti_registrati)}
                  color={COLORS.primary}
                  sub={`${preview.acconti_registrati.length} acconti`}
                />
              </div>

              {preview.delta != null && Math.abs(preview.delta) >= 0.01 && (
                <div style={{
                  padding:8, background:'#fef3c7', borderRadius:6, marginBottom:14,
                  fontSize:12, color:'#92400e', textAlign:'center', fontWeight:600,
                }}>
                  Delta: {preview.delta > 0 ? '+' : ''}{fmt€(preview.delta)}
                  {preview.delta > 0 ? ' (cedolino > registrati)' : ' (cedolino < registrati)'}
                </div>
              )}

              {/* Lista acconti */}
              {preview.acconti_registrati.length > 0 && (
                <div style={{ border:`1px solid ${COLORS.border}`, borderRadius:8, overflow:'hidden' }}>
                  <div style={{ padding:'8px 12px', background:'#f8fafc', fontSize:11, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase', letterSpacing:'0.04em' }}>
                    Acconti che verranno scalati
                  </div>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                    <tbody>
                      {preview.acconti_registrati.map(a => (
                        <tr key={a.id} style={{ borderTop:`1px solid ${COLORS.border}` }}>
                          <td style={{ padding:'8px 12px', fontWeight:600 }}>{fmtD(a.data)}</td>
                          <td style={{ padding:'8px 12px', color:COLORS.textMuted }}>{a.tipo}</td>
                          <td style={{ padding:'8px 12px' }}>
                            <span style={{
                              fontSize:10, padding:'1px 6px', borderRadius:3, fontWeight:600,
                              background: a.natura_acconto === 'su_pregresso' ? '#fef3c7' : '#dbeafe',
                              color: a.natura_acconto === 'su_pregresso' ? '#b45309' : '#1d4ed8',
                            }}>
                              {a.natura_acconto === 'su_pregresso' ? 'Pregresso' : 'Su futuro'}
                            </span>
                          </td>
                          <td style={{ padding:'8px 12px', textAlign:'right', fontWeight:700, color:COLORS.primary, fontVariantNumeric:'tabular-nums' }}>
                            {fmt€(a.importo)}
                          </td>
                          <td style={{ padding:'8px 12px' }}>
                            <span style={{
                              fontSize:10, padding:'1px 6px', borderRadius:3, fontWeight:600,
                              background: a.stato === 'riconciliato_banca' ? '#dcfce7' : '#f1f5f9',
                              color: a.stato === 'riconciliato_banca' ? '#15803d' : '#475569',
                            }}>
                              {a.stato === 'riconciliato_banca' ? 'Banca ✓' : 'Registrato'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Checkbox forza in caso di discrepanza */}
              {isDiscrepanza && (
                <label style={{
                  display:'flex', gap:10, marginTop:14, padding:10,
                  background:'#fef3c7', border:'1px solid #fcd34d', borderRadius:8,
                  cursor:'pointer',
                }}>
                  <input
                    type="checkbox"
                    checked={forza}
                    onChange={e=>setForza(e.target.checked)}
                    style={{ marginTop:2 }}
                  />
                  <div style={{ fontSize:12, color:'#92400e' }}>
                    <strong>Ho verificato e accetto la discrepanza</strong>: applica comunque la scalatura.
                    {' '}Gli acconti registrati verranno marcati come scalati per il loro importo intero.
                  </div>
                </label>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding:'12px 24px', borderTop:`1px solid ${COLORS.border}`,
          display:'flex', justifyContent:'flex-end', gap:8, background:'#f8fafc',
          borderRadius:'0 0 12px 12px',
        }}>
          <button
            onClick={onClose}
            disabled={applying}
            style={{ padding:'8px 16px', background:'white', color:COLORS.textMuted, border:`1px solid ${COLORS.border}`, borderRadius:6, cursor:'pointer', fontSize:13 }}
          >
            Chiudi
          </button>
          {!loading && preview && !isNessunDato && (
            <button
              onClick={applica}
              disabled={applying || (isDiscrepanza && !forza)}
              style={{
                padding:'8px 18px',
                background: (applying || (isDiscrepanza && !forza))
                  ? '#cbd5e1'
                  : isQuadra
                    ? 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)'
                    : 'linear-gradient(135deg, #b45309 0%, #92400e 100%)',
                color:'white', border:'none', borderRadius:6,
                cursor: (applying || (isDiscrepanza && !forza)) ? 'not-allowed' : 'pointer',
                fontSize:13, fontWeight:600,
              }}
            >
              {applying ? '⏳ Applicazione…' : isDiscrepanza ? '⚠️ Forza scalatura' : '✓ Scala acconti'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB VERBALI
// ─────────────────────────────────────────────────────────────────────────────
function TabVerbali({ dip }) {
  const isMobile = useIsMobile();
  const [verbali, setVerbali] = useState([]);
  const [trattenute, setTrattenute] = useState([]);
  // Trattenute disciplinari (Task 4) - sistema separato dalle vecchie trattenute
  const [trattenuteDisc, setTrattenuteDisc] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showProponiModal, setShowProponiModal] = useState(false);
  const [reloadBump, setReloadBump] = useState(0);

  useAbortableEffect((signal) => {
    setLoading(true);
    const cf = dip.codice_fiscale||'';
    const id = dip.id||'';
    Promise.all([
      api.get(`/api/noleggio/verbali-dipendente?dipendente_id=${id}&codice_fiscale=${cf}`, { signal })
        .catch(()=>({ data:{ verbali:[] } })),
      api.get(`/api/cedolini/dipendente/${id}/trattenute`, { signal })
        .catch(()=>({ data:{ trattenute:[] } })),
      // Trattenute disciplinari (sistema nuovo)
      api.get(`/api/trattenute?dipendente_id=${id}`, { signal })
        .catch(()=>({ data:{ trattenute:[] } })),
    ]).then(([vr, tr, td]) => {
      if (signal?.aborted) return;
      setVerbali(vr.data?.verbali || []);
      setTrattenute(tr.data?.trattenute || []);
      setTrattenuteDisc(td.data?.trattenute || []);
    }).finally(()=>{ if(!signal?.aborted) setLoading(false); });
  }, [dip.id, dip.codice_fiscale, reloadBump]);

  if (loading) return <div style={{padding:40,textAlign:'center',color:COLORS.textMuted}}>Caricamento…</div>;

  const impTotVerbali = verbali.reduce((s,v)=>s+parseFloat(v.importo||0),0);
  const verbaliDaPagare = verbali.filter(v=>v.stato!=='pagato').length;
  const trattDaApplicare = trattenute.filter(t=>t.stato!=='applicata').length;
  const impTratt = trattenute.filter(t=>t.stato!=='applicata').reduce((s,t)=>s+parseFloat(t.importo||0),0);

  return (
    <div>
      {/* KPI */}
      <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr 1fr':'repeat(4,1fr)', gap:12, marginBottom:24 }}>
        <KpiCard label="Verbali Totali"      value={verbali.length}       color={COLORS.text}    icon={Shield} />
        <KpiCard label="Da Pagare"           value={verbaliDaPagare}      color='#dc2626'        icon={AlertTriangle} />
        <KpiCard label="Importo Verbali"     value={fmt€(impTotVerbali)}  color='#d97706'        icon={CreditCard} />
        <KpiCard label="Trattenute Pendenti" value={fmt€(impTratt)}       color='#7c3aed'        icon={FileText} sub={`${trattDaApplicare} da applicare`} />
      </div>

      {/* Lista verbali */}
      <Section title="🚗 Verbali e Multe">
        {verbali.length === 0 ? (
          <EmptyState icon={Shield} text="Nessun verbale associato" sub="I verbali collegati a veicoli aziendali usati da questo dipendente appariranno qui." />
        ) : (
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
              <thead>
                <tr style={{ background:'#f8fafc' }}>
                  {['N. Verbale','Targa','Data','Importo','Stato','Trattenuta'].map(h=>(
                    <th key={h} style={{ padding:'10px 14px', textAlign:'left', fontSize:10, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase', borderBottom:`1px solid ${COLORS.border}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {verbali.map((v,i)=>{
                  const pagato=v.stato==='pagato';
                  return (
                    <tr key={v.id||i} style={{ borderBottom:`1px solid ${COLORS.border}30`, background: i%2===0?'white':'#fafafa' }}>
                      <td style={{ padding:'11px 14px', fontWeight:600, fontFamily:'monospace', fontSize:12 }}>{v.numero_verbale||'—'}</td>
                      <td style={{ padding:'11px 14px' }}><Badge label={v.targa||'—'} bg='#eff6ff' color='#1d4ed8'/></td>
                      <td style={{ padding:'11px 14px', color:COLORS.textMuted }}>{fmtD(v.data_verbale)}</td>
                      <td style={{ padding:'11px 14px', fontWeight:700 }}>{fmt€(v.importo)}</td>
                      <td style={{ padding:'11px 14px' }}>
                        <Badge label={pagato?'✓ Pagato':'Da pagare'} bg={pagato?'#dcfce7':'#fee2e2'} color={pagato?'#16a34a':'#dc2626'}/>
                      </td>
                      <td style={{ padding:'11px 14px' }}>
                        {v.trattenuta_cedolino ? (
                          <Badge label={`Trattenuta ${fmtD(v.data_trattenuta)}`} bg='#f3e8ff' color='#7c3aed'/>
                        ) : <span style={{ color:COLORS.textMuted, fontSize:12 }}>—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Trattenute cedolini */}
      {trattenute.length > 0 && (
        <Section title="💳 Trattenute Cedolini">
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {trattenute.map((t,i)=>{
              const app=t.stato==='applicata';
              return (
                <div key={t.id||i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'12px 16px', border:`1px solid ${app?COLORS.border:'#fecaca'}`, borderRadius:10, background: app?'white':'#fff5f5' }}>
                  <div>
                    <div style={{ fontWeight:600, fontSize:13, color:COLORS.text }}>
                      {t.tipo==='verbale_multa'?'🚗 Verbale':t.tipo||'Trattenuta'}
                      {t.descrizione && <span style={{ fontWeight:400, color:COLORS.textMuted }}> — {t.descrizione}</span>}
                    </div>
                    <div style={{ fontSize:12, color:COLORS.textMuted, marginTop:2 }}>{t.mese}/{t.anno}</div>
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <span style={{ fontWeight:800, color: app?'#16a34a':'#dc2626', fontSize:15 }}>{fmt€(t.importo)}</span>
                    <Badge label={app?'✓ Applicata':'Da applicare'} bg={app?'#dcfce7':'#fee2e2'} color={app?'#16a34a':'#dc2626'}/>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* Trattenute Disciplinari (multe contrattuali, generiche) - Task 4 */}
      <Section
        title="⚖️ Trattenute Disciplinari"
        action={
          <button
            onClick={() => setShowProponiModal(true)}
            style={{
              padding:'7px 14px',
              background: COLORS.primary,
              color:'white',
              border:'none',
              borderRadius:8,
              cursor:'pointer',
              fontSize:13,
              fontWeight:600,
              display:'flex',
              alignItems:'center',
              gap:6,
            }}
          >
            <Plus size={14}/> Proponi trattenuta
          </button>
        }
      >
        {trattenuteDisc.length === 0 ? (
          <EmptyState
            icon={Shield}
            text="Nessuna trattenuta disciplinare"
            sub="Multe contrattuali e trattenute generiche con allegato PDF compaiono qui."
          />
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {trattenuteDisc.map((t) => (
              <TrattenutaDisciplinareCard
                key={t.id}
                trattenuta={t}
                onChange={() => setReloadBump(b => b + 1)}
              />
            ))}
          </div>
        )}
      </Section>

      {/* Modale: proponi trattenuta */}
      {showProponiModal && (
        <ProponiTrattenutaModal
          dip={dip}
          onClose={() => setShowProponiModal(false)}
          onCreated={() => {
            setShowProponiModal(false);
            setReloadBump(b => b + 1);
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Card singola trattenuta disciplinare con azioni inline
// ─────────────────────────────────────────────────────────────────────────────
function TrattenutaDisciplinareCard({ trattenuta: t, onChange }) {
  const [busy, setBusy] = useState(false);
  const stato = t.stato || 'proposta';

  const colorByStato = {
    proposta:  { bg: '#fef3c7', border: '#fcd34d', text: '#92400e', label: '📝 Proposta' },
    approvata: { bg: '#dbeafe', border: '#93c5fd', text: '#1e3a8a', label: '✓ Approvata' },
    applicata: { bg: '#dcfce7', border: '#86efac', text: '#15803d', label: '✓ Applicata' },
    annullata: { bg: '#f1f5f9', border: '#cbd5e1', text: '#64748b', label: '✕ Annullata' },
  };
  const c = colorByStato[stato] || colorByStato.proposta;

  const tipoLabel = t.tipo === 'multa' ? '⚖️ Multa contrattuale' : '📋 Trattenuta generica';

  const downloadPdf = () => {
    window.open(`${api.defaults.baseURL}/api/trattenute/${t.id}/allegato`, '_blank');
  };

  const approva = async () => {
    if (!window.confirm(`Approvare la trattenuta di ${fmt€(t.importo)} su ${t.dipendente_nome}?`)) return;
    setBusy(true);
    try {
      await api.post(`/api/trattenute/${t.id}/approva`);
      onChange();
    } catch (e) {
      alert('Errore approvazione: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  };

  const applica = async () => {
    if (!window.confirm(
      `Applicare la trattenuta di ${fmt€(t.importo)} al cedolino ${t.mese}/${t.anno}?\n\n` +
      `Il netto del cedolino verrà ridotto di ${fmt€(t.importo)}.`
    )) return;
    setBusy(true);
    try {
      await api.post(`/api/trattenute/${t.id}/applica`);
      onChange();
    } catch (e) {
      alert('Errore applicazione: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  };

  const annulla = async () => {
    const motivo = window.prompt(
      `Motivo dell'annullamento (obbligatorio):`,
      ''
    );
    if (!motivo || !motivo.trim()) return;
    setBusy(true);
    try {
      await api.post(`/api/trattenute/${t.id}/annulla`, {
        motivo_annullamento: motivo.trim(),
      });
      onChange();
    } catch (e) {
      alert('Errore annullamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  };

  const elimina = async () => {
    if (!window.confirm('Eliminare definitivamente questa proposta?')) return;
    setBusy(true);
    try {
      await api.delete(`/api/trattenute/${t.id}`);
      onChange();
    } catch (e) {
      alert('Errore eliminazione: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{
      padding: '12px 16px',
      border: `1px solid ${c.border}`,
      borderRadius: 10,
      background: 'white',
      borderLeft: `4px solid ${c.text}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: COLORS.text }}>
              {tipoLabel}
            </span>
            <span style={{
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 10,
              fontWeight: 700,
              background: c.bg,
              color: c.text,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}>
              {c.label}
            </span>
          </div>
          <div style={{ fontSize: 13, color: COLORS.text, marginBottom: 4 }}>
            {t.descrizione}
          </div>
          <div style={{ fontSize: 11, color: COLORS.textMuted, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <span>📅 Evento: {fmtD(t.data_evento)}</span>
            <span>📆 Cedolino target: {String(t.mese).padStart(2,'0')}/{t.anno}</span>
            {t.riferimento_normativo && <span>⚖️ {t.riferimento_normativo}</span>}
          </div>
          {t.proposta_da_nome && (
            <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 4 }}>
              Proposta da {t.proposta_da_nome} · {fmtD(t.proposta_il)}
              {t.approvata_da && ` · Approvata da ${t.approvata_da_nome || t.approvata_da}`}
            </div>
          )}
          {stato === 'annullata' && t.motivo_annullamento && (
            <div style={{ fontSize: 11, color: '#b91c1c', marginTop: 4, fontStyle: 'italic' }}>
              ✕ Annullata: {t.motivo_annullamento}
            </div>
          )}
        </div>

        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontWeight: 800, fontSize: 16, color: stato === 'annullata' ? COLORS.textMuted : COLORS.danger, fontVariantNumeric: 'tabular-nums' }}>
            -{fmt€(t.importo)}
          </div>
        </div>
      </div>

      {/* Azioni */}
      <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <button
          onClick={downloadPdf}
          style={smallActionBtn('#0891b2')}
          title="Scarica PDF allegato"
        >
          📎 PDF
        </button>
        {stato === 'proposta' && (
          <>
            <button onClick={approva} disabled={busy} style={smallActionBtn('#15803d')}>
              ✓ Approva
            </button>
            <button onClick={elimina} disabled={busy} style={smallActionBtn(COLORS.danger)}>
              🗑️ Elimina
            </button>
          </>
        )}
        {stato === 'approvata' && (
          <>
            <button onClick={applica} disabled={busy} style={smallActionBtn('#15803d')}>
              💸 Applica al cedolino
            </button>
            <button onClick={annulla} disabled={busy} style={smallActionBtn(COLORS.danger)}>
              ✕ Annulla
            </button>
          </>
        )}
        {stato === 'applicata' && (
          <button onClick={annulla} disabled={busy} style={smallActionBtn(COLORS.danger)}>
            ↩️ Annulla applicazione
          </button>
        )}
      </div>
    </div>
  );
}

function smallActionBtn(color) {
  return {
    padding: '4px 10px',
    background: 'transparent',
    color: color,
    border: `1px solid ${color}`,
    borderRadius: 5,
    cursor: 'pointer',
    fontSize: 11,
    fontWeight: 600,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Modale: nuova proposta di trattenuta disciplinare con upload PDF
// ─────────────────────────────────────────────────────────────────────────────
function ProponiTrattenutaModal({ dip, onClose, onCreated }) {
  const today = new Date();
  const [form, setForm] = useState({
    tipo: 'multa',
    importo: '',
    descrizione: '',
    data_evento: today.toISOString().slice(0, 10),
    mese: today.getMonth() + 1,
    anno: today.getFullYear(),
    riferimento_normativo: '',
    note: '',
  });
  const [pdfFile, setPdfFile] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    // Validazioni client
    if (!form.descrizione.trim()) {
      setError('La descrizione è obbligatoria');
      return;
    }
    if (!form.importo || parseFloat(form.importo) <= 0) {
      setError("L'importo deve essere positivo");
      return;
    }
    if (!pdfFile) {
      setError('Allegato PDF obbligatorio (lettera contestazione, prova del fatto, ecc.)');
      return;
    }
    if (pdfFile.size > 10 * 1024 * 1024) {
      setError('PDF troppo grande (max 10 MB)');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('dipendente_id', dip.id);
      fd.append('tipo', form.tipo);
      fd.append('importo', String(parseFloat(form.importo)));
      fd.append('descrizione', form.descrizione.trim());
      fd.append('data_evento', form.data_evento);
      fd.append('mese', String(form.mese));
      fd.append('anno', String(form.anno));
      if (form.riferimento_normativo) {
        fd.append('riferimento_normativo', form.riferimento_normativo);
      }
      if (form.note) fd.append('note', form.note);
      fd.append('allegato_pdf', pdfFile);

      await api.post('/api/trattenute', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onCreated();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setLoading(false);
    }
  };

  return (
    <div onClick={onClose} style={{
      position:'fixed', inset:0, background:'rgba(15,39,68,0.6)', zIndex:1100,
      display:'flex', alignItems:'center', justifyContent:'center', padding:20,
    }}>
      <div onClick={e=>e.stopPropagation()} style={{
        background:'white', borderRadius:12, width:'100%', maxWidth:600,
        maxHeight:'90vh', display:'flex', flexDirection:'column',
        boxShadow:'0 20px 60px rgba(0,0,0,0.3)',
      }}>
        <div style={{
          padding:'16px 24px', borderBottom:`1px solid ${COLORS.border}`,
          background:'linear-gradient(135deg, #0f2744 0%, #1a3a5f 100%)',
          color:'white', borderRadius:'12px 12px 0 0',
        }}>
          <div style={{ fontSize:11, opacity:0.8, textTransform:'uppercase', fontWeight:700 }}>
            ⚖️ Nuova trattenuta disciplinare
          </div>
          <div style={{ fontSize:17, fontWeight:700, marginTop:2 }}>
            {dip.cognome} {dip.nome}
          </div>
          <div style={{ fontSize:11, opacity:0.8, marginTop:2 }}>
            La proposta dovrà essere approvata prima di essere applicata al cedolino.
          </div>
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:20, display:'flex', flexDirection:'column', gap:14 }}>
          {/* Tipo */}
          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Tipo *</div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
              {[
                { id:'multa', label:'⚖️ Multa contrattuale', sub:'penale CCNL' },
                { id:'generica', label:'📋 Trattenuta generica', sub:'altro caso' },
              ].map(opt => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={()=>setForm(f=>({ ...f, tipo: opt.id }))}
                  style={{
                    padding:'10px',
                    border:`2px solid ${form.tipo===opt.id ? COLORS.primary : COLORS.border}`,
                    background: form.tipo===opt.id ? `${COLORS.primary}15` : 'white',
                    color: form.tipo===opt.id ? COLORS.primary : COLORS.text,
                    borderRadius:8, cursor:'pointer', textAlign:'left',
                  }}
                >
                  <div style={{ fontWeight: form.tipo===opt.id?700:500, fontSize:13 }}>{opt.label}</div>
                  <div style={{ fontSize:10, color:COLORS.textMuted }}>{opt.sub}</div>
                </button>
              ))}
            </div>
          </label>

          {/* Importo + data evento */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Importo (€) *</div>
              <input
                type="number" step="0.01" min="0"
                value={form.importo}
                onChange={e=>setForm(f=>({ ...f, importo: e.target.value }))}
                placeholder="50.00"
                style={modalInputStyle}
              />
            </label>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Data evento *</div>
              <input
                type="date"
                value={form.data_evento}
                onChange={e=>setForm(f=>({ ...f, data_evento: e.target.value }))}
                style={modalInputStyle}
              />
            </label>
          </div>

          {/* Cedolino target */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Mese cedolino target *</div>
              <select
                value={form.mese}
                onChange={e=>setForm(f=>({ ...f, mese: parseInt(e.target.value, 10) }))}
                style={modalInputStyle}
              >
                {['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre'].map((m,i)=>(
                  <option key={m} value={i+1}>{m}</option>
                ))}
              </select>
            </label>
            <label style={{ display:'block' }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Anno *</div>
              <input
                type="number" min="2020" max="2030"
                value={form.anno}
                onChange={e=>setForm(f=>({ ...f, anno: parseInt(e.target.value, 10) }))}
                style={modalInputStyle}
              />
            </label>
          </div>

          {/* Descrizione */}
          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Descrizione del fatto *</div>
            <textarea
              value={form.descrizione}
              onChange={e=>setForm(f=>({ ...f, descrizione: e.target.value }))}
              rows={3}
              placeholder="Es. Mancato preavviso giorno 12/04/2026, danno smartphone aziendale..."
              style={{ ...modalInputStyle, fontFamily:'inherit', resize:'vertical' }}
            />
          </label>

          {/* Riferimento normativo */}
          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Riferimento normativo</div>
            <input
              type="text"
              value={form.riferimento_normativo}
              onChange={e=>setForm(f=>({ ...f, riferimento_normativo: e.target.value }))}
              placeholder="Es. Art. 24 CCNL Turismo"
              style={modalInputStyle}
            />
          </label>

          {/* PDF allegato */}
          <label style={{
            display:'block', padding:14,
            border:`2px dashed ${pdfFile ? '#15803d' : '#fca5a5'}`,
            borderRadius:8,
            background: pdfFile ? '#dcfce7' : '#fef2f2',
            cursor:'pointer',
          }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:6, textTransform:'uppercase' }}>
              📎 Allegato PDF * <span style={{ color:'#dc2626' }}>(obbligatorio)</span>
            </div>
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={e=>{
                const f = e.target.files?.[0];
                if (f) {
                  setPdfFile(f);
                  setError(null);
                }
              }}
              style={{ width:'100%' }}
            />
            {pdfFile && (
              <div style={{ marginTop:6, fontSize:12, color:'#15803d', fontWeight:600 }}>
                ✓ {pdfFile.name} ({(pdfFile.size/1024).toFixed(1)} KB)
              </div>
            )}
            {!pdfFile && (
              <div style={{ marginTop:6, fontSize:11, color:'#b91c1c' }}>
                Carica la lettera di contestazione, il verbale firmato o la prova del fatto.
              </div>
            )}
          </label>

          {/* Note */}
          <label style={{ display:'block' }}>
            <div style={{ fontSize:11, fontWeight:700, color:COLORS.textMuted, marginBottom:4, textTransform:'uppercase' }}>Note interne</div>
            <textarea
              value={form.note}
              onChange={e=>setForm(f=>({ ...f, note: e.target.value }))}
              rows={2}
              placeholder="(opzionale)"
              style={{ ...modalInputStyle, fontFamily:'inherit', resize:'vertical' }}
            />
          </label>

          {error && (
            <div style={{
              padding:10, background:'#fee2e2', border:'1px solid #fca5a5',
              borderRadius:6, color:'#b91c1c', fontSize:13,
            }}>
              ⚠️ {error}
            </div>
          )}
        </div>

        <div style={{
          padding:'12px 24px', borderTop:`1px solid ${COLORS.border}`,
          display:'flex', justifyContent:'flex-end', gap:8, background:'#f8fafc',
          borderRadius:'0 0 12px 12px',
        }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              padding:'8px 16px', background:'white', color:COLORS.textMuted,
              border:`1px solid ${COLORS.border}`, borderRadius:6, cursor:'pointer', fontSize:13,
            }}
          >
            Annulla
          </button>
          <button
            onClick={submit}
            disabled={loading || !pdfFile}
            style={{
              padding:'8px 18px',
              background: (loading || !pdfFile) ? '#cbd5e1' : 'linear-gradient(135deg, #0f2744 0%, #1a3a5f 100%)',
              color:'white', border:'none', borderRadius:6,
              cursor: (loading || !pdfFile) ? 'not-allowed' : 'pointer',
              fontSize:13, fontWeight:600,
            }}
          >
            {loading ? '⏳ Invio…' : '📝 Crea proposta'}
          </button>
        </div>
      </div>
    </div>
  );
}

const modalInputStyle = {
  width:'100%',
  padding:'8px 10px',
  border:`1px solid ${COLORS.border}`,
  borderRadius:6,
  fontSize:13,
  boxSizing:'border-box',
  background:'white',
};

// ─────────────────────────────────────────────────────────────────────────────
// TAB MOVIMENTI
// ─────────────────────────────────────────────────────────────────────────────
function TabMovimenti({ dip }) {
  const isMobile = useIsMobile();
  const [bonifici, setBonifici] = useState([]);
  const [acconti, setAcconti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ importo:'', data:'', note:'' });
  const [saving, setSaving] = useState(false);

  const nomeDip = dip.nome_completo || `${dip.cognome||''} ${dip.nome||''}`.trim();
  const ibanDip = dip.iban_cedolino || dip.iban || '';

  const load = useCallback((signal) => {
    setLoading(true);
    // Cerca per IBAN (prioritario) + nome
    const ibanParam = ibanDip ? `&iban=${encodeURIComponent(ibanDip)}` : '';
    Promise.all([
      api.get(`/api/dipendenti/${dip.id}/fascicolo?anno=${ANNO_CORRENTE}`, { signal })
        .catch(()=>({ data:{ stipendi_banca:[], acconti_tfr:[] } })),
      api.get(`/api/tfr/acconti/${dip.id}`, { signal })
        .catch(()=>({ data:[] })),
    ]).then(([fRes, aRes])=>{
      if (signal?.aborted) return;
      setBonifici(fRes.data?.stipendi_banca || []);
      setAcconti(Array.isArray(aRes.data) ? aRes.data : aRes.data?.acconti || []);
    }).finally(()=>{ if(!signal?.aborted) setLoading(false); });
  }, [dip.id, nomeDip, ibanDip]);

  useAbortableEffect(load, [load]);

  const salvaAcconto = async () => {
    if (!form.importo) return;
    setSaving(true);
    try {
      await api.post('/api/tfr/acconti', {
        dipendente_id: dip.id,
        importo: Number(form.importo),
        data: form.data || new Date().toISOString().split('T')[0],
        note: form.note,
      });
      setShowForm(false);
      setForm({ importo:'', data:'', note:'' });
      load();
    } catch(e) { console.error(e); }
    finally { setSaving(false); }
  };

  const elimAcconto = async id => {
    if (!window.confirm('Eliminare questo acconto TFR?')) return;
    try { await api.delete(`/api/tfr/acconti/${id}`); load(); }
    catch(e) { console.error(e); }
  };

  const totAcconti = acconti.reduce((s,a)=>s+parseFloat(a.importo||0),0);
  const totBonifici = bonifici.reduce((s,b)=>s+parseFloat(b.importo||0),0);

  if (loading) return <div style={{padding:40,textAlign:'center',color:COLORS.textMuted}}>Caricamento…</div>;

  return (
    <div>
      {/* KPI */}
      <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr 1fr':'repeat(3,1fr)', gap:12, marginBottom:24 }}>
        <KpiCard label="Bonifici Trovati"   value={bonifici.length}     color={COLORS.primary} icon={CreditCard} sub={ibanDip?`IBAN: …${ibanDip.slice(-6)}`:'Match su nome'} />
        <KpiCard label="Totale Erogato"     value={fmt€(totBonifici)}   color='#16a34a'        icon={TrendingUp} />
        <KpiCard label="Acconti TFR"        value={fmt€(totAcconti)}    color='#b8860b'        icon={Award} sub={`${acconti.length} acconti`} />
      </div>

      {/* Acconti TFR */}
      <Section title="Acconti TFR" action={
        <button onClick={()=>setShowForm(v=>!v)} style={{ padding:'7px 14px', background:COLORS.primary, color:'white', border:'none', borderRadius:8, cursor:'pointer', fontSize:13, fontWeight:600, display:'flex', alignItems:'center', gap:5 }}>
          <Plus size={13}/> Nuovo
        </button>
      }>
        {showForm && (
          <div style={{ border:`1px solid ${COLORS.border}`, borderRadius:10, padding:16, marginBottom:16, background:'#f8fafc' }}>
            <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr':'1fr 1fr 2fr', gap:12, marginBottom:12 }}>
              <Field label="Importo (€)" value={form.importo} editMode onChange={v=>setForm(p=>({...p,importo:v}))} type="number" />
              <Field label="Data"        value={form.data}    editMode onChange={v=>setForm(p=>({...p,data:v}))}    type="date" />
              <Field label="Note"        value={form.note}    editMode onChange={v=>setForm(p=>({...p,note:v}))} />
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <button onClick={salvaAcconto} disabled={saving} style={{ padding:'7px 16px', background:'#22c55e', color:'white', border:'none', borderRadius:8, cursor:'pointer', fontWeight:600, fontSize:13 }}>
                {saving?'Salvataggio…':'Salva Acconto'}
              </button>
              <button onClick={()=>setShowForm(false)} style={{ padding:'7px 12px', background:'#f1f5f9', border:'none', borderRadius:8, cursor:'pointer', fontSize:13 }}>Annulla</button>
            </div>
          </div>
        )}
        {acconti.length === 0 ? (
          <EmptyState icon={Award} text="Nessun acconto TFR" />
        ) : acconti.map((a,i)=>(
          <div key={a.id||i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'11px 14px', border:`1px solid ${COLORS.border}`, borderRadius:10, marginBottom:8 }}>
            <div>
              <div style={{ fontWeight:700, fontSize:14, color:COLORS.primary }}>{fmt€(a.importo)}</div>
              <div style={{ fontSize:12, color:COLORS.textMuted }}>{fmtD(a.data)}{a.note?` — ${a.note}`:''}</div>
            </div>
            <button onClick={()=>elimAcconto(a.id)} style={{ padding:'5px 10px', background:'#fee2e2', color:'#dc2626', border:'none', borderRadius:6, cursor:'pointer', fontSize:12 }}>
              <Trash2 size={12}/>
            </button>
          </div>
        ))}
      </Section>

      {/* Bonifici */}
      <Section title={`Bonifici ricevuti${ibanDip?` (IBAN: …${ibanDip.slice(-6)})`:''}` }>
        {bonifici.length === 0 ? (
          <EmptyState icon={CreditCard} text="Nessun bonifico trovato" sub={ibanDip?'Nessun movimento bancario corrisponde a questo IBAN.':'Inserire un IBAN in anagrafica per il match automatico.'} />
        ) : (
          <div style={{ background:'white', border:`1px solid ${COLORS.border}`, borderRadius:12, overflow:'hidden' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
              <thead>
                <tr style={{ background:'#f8fafc' }}>
                  {['Data','Descrizione','Importo','Match'].map(h=>(
                    <th key={h} style={{ padding:'10px 14px', textAlign:'left', fontSize:10, fontWeight:700, color:COLORS.textMuted, textTransform:'uppercase', borderBottom:`1px solid ${COLORS.border}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bonifici.slice(0,30).map((b,i)=>(
                  <tr key={b.id||i} style={{ borderBottom:`1px solid ${COLORS.border}30`, background: i%2===0?'white':'#fafafa' }}>
                    <td style={{ padding:'10px 14px', color:COLORS.textMuted, whiteSpace:'nowrap' }}>{fmtD(b.data_valuta||b.data)}</td>
                    <td style={{ padding:'10px 14px', maxWidth:280, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={b.descrizione}>{b.descrizione||b.causale||'—'}</td>
                    <td style={{ padding:'10px 14px', fontWeight:700, color:'#16a34a', whiteSpace:'nowrap' }}>{fmt€(b.importo)}</td>
                    <td style={{ padding:'10px 14px' }}>
                      <Badge label={b.match_tipo==='iban'?'🔑 IBAN':b.match_tipo==='bonifici_arch'?'📋 Archivio':'📝 Nome'} bg={b.match_tipo==='iban'?'#dcfce7':'#e0e7ff'} color={b.match_tipo==='iban'?'#16a34a':'#4338ca'} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB GIUSTIFICATIVI
// ─────────────────────────────────────────────────────────────────────────────
function TabGiustificativi({ dip }) {
  const isMobile = useIsMobile();
  const [giustificativi, setGiustificativi] = useState([]);
  const [saldo, setSaldo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [anno, setAnno] = useState(ANNO_CORRENTE);

  useAbortableEffect((signal) => {
    setLoading(true);
    Promise.all([
      api.get(`/api/giustificativi/dipendente/${dip.id}/giustificativi?anno=${anno}`, { signal })
        .catch(()=>({ data:{ giustificativi:[] } })),
      api.get(`/api/giustificativi/dipendente/${dip.id}/saldo-ferie?anno=${anno}`, { signal })
        .catch(()=>({ data:null })),
    ]).then(([g, s])=>{
      if (signal?.aborted) return;
      setGiustificativi(Array.isArray(g.data)?g.data:g.data?.giustificativi||[]);
      setSaldo(s.data);
    }).finally(()=>{ if(!signal?.aborted) setLoading(false); });
  }, [dip.id, anno]);

  const TIPO_STYLE = {
    Ferie:    { bg:'#dbeafe', color:'#1d4ed8' },
    Permesso: { bg:'#e0e7ff', color:'#4338ca' },
    Malattia: { bg:'#fef3c7', color:'#92400e' },
    ROL:      { bg:'#dcfce7', color:'#16a34a' },
    'L.104':  { bg:'#f3e8ff', color:'#7c3aed' },
    Congedo:  { bg:'#f0fdf4', color:'#15803d' },
    Altro:    { bg:'#f1f5f9', color:'#64748b' },
  };

  const byTipo = useMemo(()=>{
    const m={};
    giustificativi.forEach(g=>{
      const t=g.tipo||'Altro';
      if(!m[t]) m[t]={count:0,giorni:0};
      m[t].count++;
      m[t].giorni += g.giorni||0;
    });
    return m;
  }, [giustificativi]);

  if (loading) return <div style={{padding:40,textAlign:'center',color:COLORS.textMuted}}>Caricamento…</div>;

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <h3 style={{ margin:0, fontSize:15, fontWeight:700 }}>Giustificativi</h3>
        <div style={{ display:'flex', gap:8, alignItems:'center' }}>
          <a href="/ferie-permessi" style={{ fontSize:12, color:COLORS.primary, fontWeight:600, display:'flex', alignItems:'center', gap:4 }}>
            <ExternalLink size={12}/> Richiedi assenza
          </a>
          <select value={anno} onChange={e=>setAnno(Number(e.target.value))}
            style={{ padding:'6px 12px', border:`1px solid ${COLORS.border}`, borderRadius:8, fontSize:13, background:'white' }}>
            {ANNI.map(a=><option key={a}>{a}</option>)}
          </select>
        </div>
      </div>

      {/* Saldi */}
      {saldo && (
        <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr 1fr':'repeat(4,1fr)', gap:12, marginBottom:20 }}>
          <KpiCard label="Ferie Residue"    value={`${saldo.ferie_residue??'—'} gg`}    color='#1d4ed8' icon={Calendar} />
          <KpiCard label="Permessi Residui" value={`${saldo.permessi_residui??'—'} ore`} color='#7c3aed' icon={Clock} />
          <KpiCard label="Malattia"         value={`${saldo.giorni_malattia??'—'} gg`}   color='#d97706' icon={AlertTriangle} />
          <KpiCard label="ROL Residuo"      value={`${saldo.rol_residuo??saldo.rol_residui??'—'} ore`} color='#16a34a' icon={Activity} />
        </div>
      )}

      {/* Riepilogo per tipo */}
      {Object.keys(byTipo).length > 0 && (
        <div style={{ display:'flex', gap:8, flexWrap:'wrap', marginBottom:20 }}>
          {Object.entries(byTipo).map(([tipo,info])=>{
            const st = TIPO_STYLE[tipo]||TIPO_STYLE.Altro;
            return (
              <div key={tipo} style={{ padding:'8px 14px', borderRadius:10, background:st.bg, color:st.color, fontWeight:600, fontSize:12 }}>
                {tipo}: {info.count} richieste {info.giorni>0?`(${info.giorni} gg)`:''}
              </div>
            );
          })}
        </div>
      )}

      {/* Lista */}
      {giustificativi.length === 0 ? (
        <EmptyState icon={Activity} text={`Nessun giustificativo per ${anno}`} sub="Le richieste di ferie, permessi e assenze appariranno qui." />
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {giustificativi.map((g,i)=>{
            const st = TIPO_STYLE[g.tipo]||TIPO_STYLE.Altro;
            const appr = g.stato==='approvata'||g.approvato;
            const rif = g.stato==='rifiutata';
            return (
              <div key={g.id||i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'12px 16px', border:`1px solid ${COLORS.border}`, borderRadius:10, background:'white' }}>
                <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                  <div style={{ width:36, height:36, borderRadius:8, background:st.bg, color:st.color, display:'flex', alignItems:'center', justifyContent:'center', fontWeight:800, fontSize:11 }}>
                    {(g.tipo||'?').slice(0,3).toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight:600, color:COLORS.text }}>{g.tipo||'Giustificativo'} {g.giorni?`(${g.giorni}gg)`:''}</div>
                    <div style={{ fontSize:12, color:COLORS.textMuted }}>
                      {fmtD(g.data_inizio)} → {fmtD(g.data_fine)} {g.motivazione?`— ${g.motivazione}`:''}
                    </div>
                  </div>
                </div>
                <Badge
                  label={appr?'✓ Approvata':rif?'✗ Rifiutata':'⏳ In attesa'}
                  bg={appr?'#dcfce7':rif?'#fee2e2':'#fef9c3'}
                  color={appr?'#16a34a':rif?'#dc2626':'#a16207'}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// HEADER KPI DIPENDENTE
// ─────────────────────────────────────────────────────────────────────────────
function DipKpiHeader({ dip, kpi }) {
  const isMobile = useIsMobile();
  if (!kpi) return null;
  return (
    <div style={{ display:'grid', gridTemplateColumns: isMobile?'1fr 1fr':'repeat(4,1fr)', gap:10, marginBottom:20 }}>
      <KpiCard label="Netto Ultimo Cedolino" value={kpi.ultimo_netto?fmt€(kpi.ultimo_netto):'—'} color='#16a34a' icon={FileText} sub={kpi.ultimo_cedolino_mese} />
      <KpiCard label="Ferie Residue"         value={`${kpi.ferie_residue??'—'} gg`}              color='#1d4ed8' icon={Calendar} />
      <KpiCard label="Permessi Residui"      value={`${kpi.permessi_residui??'—'} h`}            color='#7c3aed' icon={Clock} />
      <KpiCard label="TFR Accantonato"       value={fmt€(kpi.tfr_accantonato||0)}                color='#b8860b' icon={Award}
        sub={kpi.contratto_in_scadenza ? <span style={{color:'#d97706'}}>⚠ Contratto in scadenza {fmtD(kpi.contratto_scadenza_data)}</span> : null} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTE PRINCIPALE
// ─────────────────────────────────────────────────────────────────────────────
export default function HRDipendenti() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const params = useParams();

  const [dipendenti, setDipendenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterAttivo, setFilterAttivo] = useState('attivi');
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState('anagrafica');
  const [showDedupe, setShowDedupe] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [showNuovo, setShowNuovo] = useState(false);
  const [kpi, setKpi] = useState(null);

  // Nuovo dipendente form
  const [formNuovo, setFormNuovo] = useState({ nome:'', cognome:'', codice_fiscale:'', mansione:'', data_assunzione:'', tipo_contratto:'Tempo Determinato' });
  const [savingNuovo, setSavingNuovo] = useState(false);

  // Load lista
  const loadLista = useCallback((signal) => {
    setLoading(true);
    const inCaricoParam = filterAttivo==='attivi' ? '&in_carico=true' : filterAttivo==='tutti' ? '' : '&in_carico=false';
    api.get(`/api/dipendenti?limit=500${inCaricoParam}`, { signal })
      .then(r=>{ if(!signal?.aborted) setDipendenti(Array.isArray(r.data)?r.data:[]); })
      .catch(e=>{ if(!isCanceledError(e)) setDipendenti([]); })
      .finally(()=>{ if(!signal?.aborted) setLoading(false); });
  }, [filterAttivo]);

  useAbortableEffect(loadLista, [loadLista]);

  // Load KPI quando cambia dipendente selezionato
  useAbortableEffect((signal) => {
    if (!selected?.id) { setKpi(null); return; }
    api.get(`/api/dipendenti/${selected.id}/kpi`, { signal })
      .then(r=>{ if(!signal?.aborted) setKpi(r.data); })
      .catch(()=>setKpi(null));
  }, [selected?.id]);

  // Filtro client-side
  const filtered = useMemo(()=>{
    if (!search) return dipendenti;
    const q = search.toLowerCase();
    return dipendenti.filter(d=>{
      const n=(d.nome_completo||`${d.cognome||''} ${d.nome||''}`).toLowerCase();
      const cf=(d.codice_fiscale||'').toLowerCase();
      const m=(d.mansione||'').toLowerCase();
      return n.includes(q)||cf.includes(q)||m.includes(q);
    });
  }, [dipendenti, search]);

  const creoNuovo = async () => {
    if (!formNuovo.nome && !formNuovo.cognome) return;
    setSavingNuovo(true);
    try {
      const res = await api.post('/api/dipendenti', formNuovo);
      setShowNuovo(false);
      setFormNuovo({ nome:'', cognome:'', codice_fiscale:'', mansione:'', data_assunzione:'', tipo_contratto:'Tempo Determinato' });
      loadLista();
      if (res.data?.id) setSelected(res.data);
    } catch(e) { alert(e.response?.data?.detail || 'Errore creazione dipendente'); }
    finally { setSavingNuovo(false); }
  };

  // Layout: lista sinistra + dettaglio destra su desktop
  const panelW = isMobile ? '100%' : 320;

  return (
    <div style={{ display:'flex', flexDirection: isMobile?'column':'row', height: isMobile?'auto':'calc(100vh - 60px)', overflow:'hidden' }}>

      {/* ── PANNELLO LISTA ── */}
      <div style={{
        width: panelW, minWidth: panelW, maxWidth: panelW,
        borderRight: isMobile?'none':`1px solid ${COLORS.border}`,
        display:'flex', flexDirection:'column', overflow:'hidden',
        background:'white',
      }}>
        {/* Header lista */}
        <div style={{ padding:'14px 16px', borderBottom:`1px solid ${COLORS.border}`, background:COLORS.primary }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
            <div style={{ color:'white', fontWeight:700, fontSize:16, display:'flex', alignItems:'center', gap:6 }}>
              <Users size={18}/> Dipendenti
              <span style={{ fontSize:12, fontWeight:400, opacity:0.75, marginLeft:4 }}>({filtered.length})</span>
            </div>
            <div style={{ display:'flex', gap:6 }}>
              <button onClick={()=>setShowDedupe(true)} title="Deduplica" style={{ padding:'5px 8px', background:'rgba(255,255,255,0.15)', color:'white', border:'1px solid rgba(255,255,255,0.3)', borderRadius:7, cursor:'pointer', fontSize:12 }}>
                🔗
              </button>
              <button onClick={()=>setShowImport(true)} title="Import massivo" style={{ padding:'5px 8px', background:'rgba(255,255,255,0.15)', color:'white', border:'1px solid rgba(255,255,255,0.3)', borderRadius:7, cursor:'pointer', fontSize:12 }}>
                📥
              </button>
              <button onClick={()=>setShowNuovo(v=>!v)} style={{ padding:'5px 10px', background:'rgba(255,255,255,0.2)', color:'white', border:'1px solid rgba(255,255,255,0.35)', borderRadius:7, cursor:'pointer', fontSize:12, display:'flex', alignItems:'center', gap:4, fontWeight:600 }}>
                <Plus size={13}/> Nuovo
              </button>
            </div>
          </div>
          {/* Ricerca */}
          <div style={{ position:'relative' }}>
            <Search size={14} style={{ position:'absolute', left:10, top:'50%', transform:'translateY(-50%)', color:'rgba(255,255,255,0.6)' }}/>
            <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Cerca nome, CF, mansione…"
              style={{ width:'100%', padding:'8px 10px 8px 32px', border:'1px solid rgba(255,255,255,0.3)', borderRadius:8, fontSize:13, outline:'none', boxSizing:'border-box', background:'rgba(255,255,255,0.15)', color:'white', '::placeholder':{ color:'rgba(255,255,255,0.5)' } }}/>
          </div>
          {/* Filtro */}
          <div style={{ display:'flex', gap:4, marginTop:8 }}>
            {[['attivi','In carico'],['tutti','Tutti'],['cessati','Cessati']].map(([v,l])=>(
              <button key={v} onClick={()=>setFilterAttivo(v)}
                style={{ flex:1, padding:'5px 0', background: filterAttivo===v?'rgba(255,255,255,0.25)':'transparent', color:'white', border:'1px solid rgba(255,255,255,0.2)', borderRadius:6, cursor:'pointer', fontSize:11, fontWeight: filterAttivo===v?700:400 }}>
                {l}
              </button>
            ))}
          </div>
        </div>

        {/* Form nuovo dipendente inline */}
        {showNuovo && (
          <div style={{ padding:14, borderBottom:`1px solid ${COLORS.border}`, background:'#f0f9ff' }}>
            <div style={{ fontSize:13, fontWeight:700, color:COLORS.primary, marginBottom:10 }}>➕ Nuovo Dipendente</div>
            {[
              ['Nome',            'nome'],
              ['Cognome',         'cognome'],
              ['Codice Fiscale',  'codice_fiscale'],
              ['Mansione',        'mansione'],
              ['Data Assunzione', 'data_assunzione', 'date'],
            ].map(([lbl, key, type])=>(
              <div key={key} style={{ marginBottom:8 }}>
                <div style={{ fontSize:10, fontWeight:700, color:COLORS.textMuted, marginBottom:2 }}>{lbl}</div>
                <input type={type||'text'} value={formNuovo[key]||''} onChange={e=>setFormNuovo(p=>({...p,[key]:e.target.value}))}
                  style={{ width:'100%', padding:'7px 10px', border:`1px solid ${COLORS.border}`, borderRadius:6, fontSize:13, boxSizing:'border-box' }}/>
              </div>
            ))}
            <div style={{ display:'flex', gap:6, marginTop:8 }}>
              <button onClick={creoNuovo} disabled={savingNuovo} style={{ flex:1, padding:'8px 0', background:'#22c55e', color:'white', border:'none', borderRadius:7, cursor:'pointer', fontWeight:700, fontSize:13 }}>
                {savingNuovo?'Salvataggio…':'✓ Crea'}
              </button>
              <button onClick={()=>setShowNuovo(false)} style={{ padding:'8px 12px', background:'#f1f5f9', border:'none', borderRadius:7, cursor:'pointer', fontSize:13 }}>✕</button>
            </div>
          </div>
        )}

        {/* Lista dipendenti */}
        <div style={{ flex:1, overflowY:'auto', padding:'8px 0' }}>
          {loading ? (
            <div style={{ padding:40, textAlign:'center', color:COLORS.textMuted }}>Caricamento…</div>
          ) : filtered.length === 0 ? (
            <div style={{ padding:32, textAlign:'center', color:COLORS.textMuted, fontSize:13 }}>Nessun dipendente trovato</div>
          ) : filtered.map(d=>{
            const nome = d.nome_completo || `${d.cognome||''} ${d.nome||''}`.trim() || '—';
            const isSelected = selected?.id === d.id;
            const nonInCarico = d.in_carico===false||d.attivo===false;
            return (
              <div key={d.id||d.codice_fiscale} onClick={()=>{ setSelected(d); setActiveTab('anagrafica'); }}
                style={{
                  padding:'11px 16px', cursor:'pointer',
                  background: isSelected ? `${COLORS.primary}10` : 'transparent',
                  borderLeft: isSelected ? `3px solid ${COLORS.primary}` : '3px solid transparent',
                  borderBottom:`1px solid ${COLORS.border}20`,
                  opacity: nonInCarico ? 0.55 : 1,
                  transition:'background 0.15s',
                }}>
                <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                  <div style={{
                    width:36, height:36, borderRadius:10, flexShrink:0,
                    background:`${avatarColor(nome)}20`, color:avatarColor(nome),
                    display:'flex', alignItems:'center', justifyContent:'center',
                    fontWeight:800, fontSize:13,
                  }}>
                    {initials(nome)}
                  </div>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontWeight:600, fontSize:13, color:COLORS.text, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>
                      {nome}
                      {nonInCarico && <span style={{ marginLeft:6, fontSize:10, color:'#dc2626', fontWeight:700 }}>CESSATO</span>}
                    </div>
                    <div style={{ fontSize:11, color:COLORS.textMuted }}>{d.mansione||'—'}</div>
                  </div>
                  <ChevronRight size={14} color={COLORS.textMuted}/>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── PANNELLO DETTAGLIO ── */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', background:'#f8fafc' }}>
        {!selected ? (
          <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:16, color:COLORS.textMuted }}>
            <Users size={56} style={{ opacity:0.15 }}/>
            <div style={{ fontSize:16, fontWeight:600 }}>Seleziona un dipendente</div>
            <div style={{ fontSize:13 }}>Clicca su un dipendente nella lista per vedere il fascicolo completo.</div>
          </div>
        ) : (
          <>
            {/* Header dipendente */}
            <div style={{ padding:'14px 24px', background:'white', borderBottom:`1px solid ${COLORS.border}`, display:'flex', alignItems:'center', gap:16 }}>
              <div style={{
                width:52, height:52, borderRadius:14, flexShrink:0,
                background:`${avatarColor(selected.nome_completo||'')}20`,
                color:avatarColor(selected.nome_completo||''),
                display:'flex', alignItems:'center', justifyContent:'center',
                fontWeight:900, fontSize:20,
              }}>
                {initials(selected.nome_completo||`${selected.cognome||''} ${selected.nome||''}`)}
              </div>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:18, fontWeight:800, color:COLORS.text }}>
                  {selected.nome_completo || `${selected.cognome||''} ${selected.nome||''}`}
                </div>
                <div style={{ fontSize:13, color:COLORS.textMuted, display:'flex', gap:12, flexWrap:'wrap', marginTop:2 }}>
                  {selected.mansione && <span>👤 {selected.mansione}</span>}
                  {selected.tipo_contratto && <span>📋 {selected.tipo_contratto}</span>}
                  {selected.data_assunzione && <span>📅 dal {fmtD(selected.data_assunzione)}</span>}
                  {selected.codice_fiscale && <span style={{ fontFamily:'monospace', fontSize:11 }}>{selected.codice_fiscale}</span>}
                </div>
              </div>
              {selected.in_carico===false && <Badge label="NON IN CARICO" bg='#fef2f2' color='#dc2626'/>}
            </div>

            {/* KPI header */}
            {kpi && (
              <div style={{ padding:'12px 24px', borderBottom:`1px solid ${COLORS.border}`, background:'white' }}>
                <DipKpiHeader dip={selected} kpi={kpi} />
              </div>
            )}

            {/* Tab navigation */}
            <div style={{ display:'flex', gap:2, padding:'0 24px', background:'white', borderBottom:`1px solid ${COLORS.border}`, overflowX:'auto' }}>
              {TABS.map(tab=>{
                const Icon = tab.icon;
                const active = activeTab === tab.id;
                return (
                  <button key={tab.id} onClick={()=>setActiveTab(tab.id)}
                    style={{
                      display:'flex', alignItems:'center', gap:6, padding:'12px 14px',
                      background:'transparent', border:'none', cursor:'pointer',
                      borderBottom: active ? `2px solid ${COLORS.primary}` : '2px solid transparent',
                      color: active ? COLORS.primary : COLORS.textMuted,
                      fontWeight: active ? 700 : 500,
                      fontSize:13, whiteSpace:'nowrap', transition:'all 0.15s',
                    }}>
                    <Icon size={14}/> {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Contenuto tab */}
            <div style={{ flex:1, overflowY:'auto', padding:'24px' }}>
              {activeTab==='anagrafica' &&
                <TabAnagrafica key={selected.id+'-a'} dip={selected} onSaved={upd=>setSelected(p=>({...p,...upd}))} />}
              {activeTab==='contratti' &&
                <TabContratti key={selected.id+'-c'} dip={selected} />}
              {activeTab==='presenze' &&
                <TabPresenze key={selected.id+'-p'} dip={selected} />}
              {activeTab==='cedolini' &&
                <TabCedolini key={selected.id+'-ced'} dip={selected} />}
              {activeTab==='verbali' &&
                <TabVerbali key={selected.id+'-v'} dip={selected} />}
              {activeTab==='movimenti' &&
                <TabMovimenti key={selected.id+'-m'} dip={selected} />}
              {activeTab==='giustificativi' &&
                <TabGiustificativi key={selected.id+'-g'} dip={selected} />}
            </div>
          </>
        )}
      </div>

      {/* Modale deduplica */}
      {showDedupe && <DedupeDipendentiModal onClose={()=>setShowDedupe(false)} onMerged={loadLista} />}
      {showImport && <ImportDipendentiModal onClose={()=>setShowImport(false)} onImported={()=>{ setShowImport(false); loadLista(); }} />}
    </div>
  );
}
