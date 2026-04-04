import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Search, Plus, User, Edit2, Save, X, ChevronRight } from 'lucide-react';
import api from '../../api';
import { COLORS, STYLES, SPACING } from '../../lib/utils';

const TABS = [
  { id: 'anagrafica',   label: 'Anagrafica' },
  { id: 'contratti',    label: 'Contratti' },
  { id: 'cedolini',     label: 'Cedolini' },
  { id: 'movimenti',    label: 'Movimenti' },
  { id: 'giustificativi', label: 'Giustificativi' },
];

const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = [ANNO_CORRENTE, ANNO_CORRENTE - 1, ANNO_CORRENTE - 2];

function formatEuro(v) {
  if (v == null || isNaN(v)) return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
}
function formatData(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('it-IT');
}

// ─── Anagrafica ───────────────────────────────────────────────────────────────
function TabAnagrafica({ dip, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState({ ...dip });
  const [saving, setSaving] = useState(false);

  useEffect(() => { setForm({ ...dip }); setEdit(false); }, [dip]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/api/dipendenti/${dip.id}`, form);
      onSaved(form);
      setEdit(false);
    } catch (e) {
      console.error(e);
    } finally { setSaving(false); }
  };

  const field = (label, key, type = 'text') => (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
      {edit
        ? <input
            value={form[key] || ''}
            onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
            type={type}
            style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, outline: 'none', boxSizing: 'border-box' }}
          />
        : <div style={{ fontSize: 14, color: form[key] ? COLORS.text : COLORS.textMuted, padding: '8px 0' }}>{form[key] || '—'}</div>
      }
    </div>
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: COLORS.text }}>Dati Personali</h3>
        {!edit
          ? <button data-testid="btn-modifica-anagrafica" onClick={() => setEdit(true)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: COLORS.primary, color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>
              <Edit2 size={14} /> Modifica
            </button>
          : <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => { setEdit(false); setForm({ ...dip }); }} style={{ padding: '7px 12px', background: '#f1f5f9', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>
                <X size={14} />
              </button>
              <button data-testid="btn-salva-anagrafica" onClick={save} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: '#22c55e', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>
                <Save size={14} /> {saving ? 'Salvataggio…' : 'Salva'}
              </button>
            </div>
        }
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 32px' }}>
        {field('Nome', 'nome')}
        {field('Cognome', 'cognome')}
        {field('Codice Fiscale', 'codice_fiscale')}
        {field('Email', 'email', 'email')}
        {field('Telefono', 'telefono', 'tel')}
        {field('Data Assunzione', 'data_assunzione', 'date')}
        {field('Mansione', 'mansione')}
        {field('Livello', 'livello')}
        {field('Tipo Contratto', 'tipo_contratto')}
        {field('IBAN', 'iban')}
        {field('Banca', 'banca')}
        {field('Importo Netto Mensile', 'importo_netto', 'number')}
      </div>
    </div>
  );
}

// ─── Contratti ────────────────────────────────────────────────────────────────
function TabContratti({ dip }) {
  const [contratti, setContratti] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/dipendenti/contratti?dipendente_id=${dip.id}`)
      .then(r => setContratti(Array.isArray(r.data) ? r.data : []))
      .catch(() => setContratti([]))
      .finally(() => setLoading(false));
  }, [dip.id]);

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>;
  if (contratti.length === 0) return (
    <div style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}>
      <User size={40} style={{ marginBottom: 12, opacity: 0.3 }} />
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Nessun contratto registrato</div>
      <div style={{ fontSize: 13 }}>Aggiungi i contratti del dipendente per tracciarne la storia contrattuale.</div>
    </div>
  );

  return (
    <div>
      <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: COLORS.text }}>Storico Contratti</h3>
      {contratti.map((c, i) => (
        <div key={i} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '14px 16px', marginBottom: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14, color: COLORS.text }}>{c.tipo_contratto || c.tipo || 'Contratto'}</div>
              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>{formatData(c.data_inizio)} → {c.data_fine ? formatData(c.data_fine) : 'In corso'}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: COLORS.primary }}>{formatEuro(c.importo_lordo || c.lordo)}</div>
              <div style={{ fontSize: 11, color: COLORS.textMuted }}>lordo/mese</div>
            </div>
          </div>
          {c.note && <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 8, borderTop: `1px solid ${COLORS.border}`, paddingTop: 8 }}>{c.note}</div>}
        </div>
      ))}
    </div>
  );
}

// ─── Cedolini ─────────────────────────────────────────────────────────────────
function TabCedolini({ dip }) {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/cedolini/dipendente/${dip.id}?anno=${anno}`)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [dip.id, anno]);

  const cedolini = data?.cedolini || [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: COLORS.text }}>Cedolini Paga</h3>
        <select
          data-testid="select-anno-cedolini"
          value={anno}
          onChange={e => setAnno(Number(e.target.value))}
          style={{ padding: '6px 12px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 13, background: 'white' }}
        >
          {ANNI.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>

      {loading && <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>}

      {!loading && cedolini.length === 0 && (
        <div style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Nessun cedolino per il {anno}</div>
          <div style={{ fontSize: 13 }}>Prova a selezionare un anno diverso.</div>
        </div>
      )}

      {!loading && cedolini.length > 0 && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 24 }}>
            {[
              { label: 'Cedolini', value: data?.totale_cedolini },
              { label: 'Totale Lordo', value: formatEuro(data?.totale_lordo) },
              { label: 'Totale Netto', value: formatEuro(data?.totale_netto) },
            ].map(s => (
              <div key={s.label} style={{ background: '#f8fafc', borderRadius: 8, padding: '12px 16px' }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, marginTop: 4 }}>{s.value ?? '—'}</div>
              </div>
            ))}
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {['Mese', 'Lordo', 'Netto', 'Contributi', 'Stato'].map(h => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cedolini.map((c, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600 }}>{['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'][Number(c.mese) - 1] || c.mese}</td>
                  <td style={{ padding: '10px 12px' }}>{formatEuro(c.lordo)}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: COLORS.primary }}>{formatEuro(c.netto)}</td>
                  <td style={{ padding: '10px 12px' }}>{formatEuro(c.contributi)}</td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{ padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 600, background: c.pagato ? '#dcfce7' : '#fef9c3', color: c.pagato ? '#16a34a' : '#a16207' }}>
                      {c.pagato ? 'Pagato' : 'Da pagare'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

// ─── Movimenti ────────────────────────────────────────────────────────────────
function TabMovimenti({ dip }) {
  const [bonifici, setBonifici] = useState([]);
  const [acconti, setAcconti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showFormAcconto, setShowFormAcconto] = useState(false);
  const [formAcconto, setFormAcconto] = useState({ importo: '', data: '', note: '' });
  const [saving, setSaving] = useState(false);

  const nomeDip = dip.nome_completo || `${dip.cognome || ''} ${dip.nome || ''}`.trim();

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.get(`/api/archivio-bonifici/transfers?beneficiario=${encodeURIComponent(nomeDip)}`),
      api.get(`/api/tfr/acconti/${dip.id}`),
    ])
      .then(([b, a]) => {
        setBonifici(Array.isArray(b.data) ? b.data : []);
        setAcconti(Array.isArray(a.data) ? a.data : a.data?.acconti || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [dip.id, nomeDip]);

  useEffect(() => { load(); }, [load]);

  const salvaAcconto = async () => {
    if (!formAcconto.importo) return;
    setSaving(true);
    try {
      await api.post('/api/tfr/acconti', {
        dipendente_id: dip.id,
        importo: Number(formAcconto.importo),
        data: formAcconto.data || new Date().toISOString().split('T')[0],
        note: formAcconto.note,
      });
      setShowFormAcconto(false);
      setFormAcconto({ importo: '', data: '', note: '' });
      load();
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  const eliminaAcconto = async (id) => {
    if (!window.confirm('Eliminare questo acconto TFR?')) return;
    try { await api.delete(`/api/tfr/acconti/${id}`); load(); } catch (e) { console.error(e); }
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>;

  return (
    <div>
      {/* Sezione Acconti TFR */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: COLORS.text }}>Acconti TFR</h3>
          <button data-testid="btn-nuovo-acconto" onClick={() => setShowFormAcconto(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: COLORS.primary, color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>
            <Plus size={14} /> Nuovo
          </button>
        </div>

        {showFormAcconto && (
          <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 16, marginBottom: 16, background: '#f8fafc' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 2fr', gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>IMPORTO (€)</label>
                <input type="number" value={formAcconto.importo} onChange={e => setFormAcconto(p => ({ ...p, importo: e.target.value }))} placeholder="0.00" style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>DATA</label>
                <input type="date" value={formAcconto.data} onChange={e => setFormAcconto(p => ({ ...p, data: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>NOTE</label>
                <input value={formAcconto.note} onChange={e => setFormAcconto(p => ({ ...p, note: e.target.value }))} placeholder="Note opzionali" style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={salvaAcconto} disabled={saving} style={{ padding: '7px 16px', background: '#22c55e', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
                {saving ? 'Salvataggio…' : 'Salva Acconto'}
              </button>
              <button onClick={() => setShowFormAcconto(false)} style={{ padding: '7px 12px', background: '#f1f5f9', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>Annulla</button>
            </div>
          </div>
        )}

        {acconti.length === 0
          ? <div style={{ padding: '24px', textAlign: 'center', color: COLORS.textMuted, background: '#f8fafc', borderRadius: 8 }}>Nessun acconto TFR registrato</div>
          : acconti.map((a, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 8, marginBottom: 8 }}>
              <div>
                <div style={{ fontWeight: 600, color: COLORS.text }}>{formatEuro(a.importo)}</div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>{formatData(a.data)}{a.note ? ` — ${a.note}` : ''}</div>
              </div>
              <button data-testid={`btn-elimina-acconto-${i}`} onClick={() => eliminaAcconto(a.id)} style={{ padding: '5px 10px', background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}>Elimina</button>
            </div>
          ))
        }
      </div>

      {/* Sezione Bonifici */}
      <div>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: COLORS.text }}>Bonifici Ricevuti</h3>
        {bonifici.length === 0
          ? <div style={{ padding: '24px', textAlign: 'center', color: COLORS.textMuted, background: '#f8fafc', borderRadius: 8 }}>Nessun bonifico trovato</div>
          : bonifici.slice(0, 20).map((b, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 8, marginBottom: 6 }}>
              <div>
                <div style={{ fontWeight: 600, color: COLORS.text }}>{b.descrizione || b.causale || 'Bonifico'}</div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>{formatData(b.data_valuta || b.data)}</div>
              </div>
              <div style={{ fontWeight: 700, color: COLORS.primary }}>{formatEuro(b.importo)}</div>
            </div>
          ))
        }
      </div>
    </div>
  );
}

// ─── Giustificativi ───────────────────────────────────────────────────────────
function TabGiustificativi({ dip }) {
  const [giustificativi, setGiustificativi] = useState([]);
  const [saldo, setSaldo] = useState(null);
  const [loading, setLoading] = useState(true);
  const anno = ANNO_CORRENTE;

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get(`/api/giustificativi/dipendente/${dip.id}/giustificativi?anno=${anno}`),
      api.get(`/api/giustificativi/dipendente/${dip.id}/saldo-ferie?anno=${anno}`),
    ])
      .then(([g, s]) => {
        setGiustificativi(Array.isArray(g.data) ? g.data : g.data?.giustificativi || []);
        setSaldo(s.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [dip.id]);

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>;

  return (
    <div>
      {saldo && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Ferie Residue', value: `${saldo.ferie_residue ?? '—'} gg` },
            { label: 'Permessi Residui', value: `${saldo.permessi_residui ?? '—'} ore` },
            { label: 'Malattie {anno}', value: `${saldo.giorni_malattia ?? '—'} gg` },
          ].map(s => (
            <div key={s.label} style={{ background: '#f8fafc', borderRadius: 8, padding: '12px 16px' }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase' }}>{s.label.replace('{anno}', anno)}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, marginTop: 4 }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: COLORS.text }}>Giustificativi {anno}</h3>
      {giustificativi.length === 0
        ? <div style={{ padding: '24px', textAlign: 'center', color: COLORS.textMuted, background: '#f8fafc', borderRadius: 8 }}>Nessun giustificativo per il {anno}</div>
        : giustificativi.map((g, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 8, marginBottom: 6 }}>
            <div>
              <div style={{ fontWeight: 600, color: COLORS.text }}>{g.tipo || 'Giustificativo'}</div>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>{formatData(g.data_inizio)} → {formatData(g.data_fine)} {g.note ? `— ${g.note}` : ''}</div>
            </div>
            <span style={{ padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600, background: g.approvato ? '#dcfce7' : '#fef9c3', color: g.approvato ? '#16a34a' : '#a16207' }}>
              {g.approvato ? 'Approvato' : 'In attesa'}
            </span>
          </div>
        ))
      }
    </div>
  );
}

// ─── Pagina principale ────────────────────────────────────────────────────────
export default function HRDipendenti() {
  const { tab = 'anagrafica' } = useParams();
  const navigate = useNavigate();

  const [dipendenti, setDipendenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ricerca, setRicerca] = useState('');
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState(tab);

  useEffect(() => {
    api.get('/api/dipendenti')
      .then(r => {
        const list = Array.isArray(r.data) ? r.data : r.data?.dipendenti || [];
        setDipendenti(list);
      })
      .catch(() => setDipendenti([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { setActiveTab(tab); }, [tab]);

  const handleTabChange = (t) => {
    setActiveTab(t);
    navigate(`/dipendenti/${t}`);
  };

  const filtrati = dipendenti.filter(d => {
    const q = ricerca.toLowerCase();
    const nome = `${d.nome || ''} ${d.cognome || ''} ${d.nome_completo || ''}`.toLowerCase();
    const mansione = (d.mansione || '').toLowerCase();
    return nome.includes(q) || mansione.includes(q);
  });

  return (
    <div style={{ height: 'calc(100vh - 110px)', display: 'flex', background: '#f8fafc' }}>

      {/* ── Sidebar lista dipendenti ── */}
      <div style={{ width: 280, minWidth: 280, background: 'white', borderRight: `1px solid ${COLORS.border}`, display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ padding: '16px 16px 12px', borderBottom: `1px solid ${COLORS.border}` }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.text, marginBottom: 10 }}>
            Dipendenti ({dipendenti.length})
          </div>
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: COLORS.textMuted }} />
            <input
              data-testid="input-ricerca-dipendente"
              value={ricerca}
              onChange={e => setRicerca(e.target.value)}
              placeholder="Cerca dipendente…"
              style={{ width: '100%', paddingLeft: 32, paddingRight: 10, paddingTop: 8, paddingBottom: 8, border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 13, outline: 'none', boxSizing: 'border-box' }}
            />
          </div>
        </div>

        {/* Lista */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {loading && <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted, fontSize: 13 }}>Caricamento…</div>}
          {!loading && filtrati.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted, fontSize: 13 }}>Nessun dipendente trovato</div>
          )}
          {filtrati.map(d => {
            const isSelected = selected?.id === d.id;
            const nome = d.nome_completo || `${d.cognome || ''} ${d.nome || ''}`.trim();
            return (
              <div
                key={d.id}
                data-testid={`dip-${d.id}`}
                onClick={() => setSelected(d)}
                style={{
                  padding: '10px 16px',
                  cursor: 'pointer',
                  background: isSelected ? `${COLORS.primary}10` : 'transparent',
                  borderLeft: isSelected ? `3px solid ${COLORS.primary}` : '3px solid transparent',
                  transition: 'all 0.1s',
                }}
              >
                <div style={{ fontWeight: isSelected ? 700 : 500, fontSize: 13, color: isSelected ? COLORS.primary : COLORS.text }}>{nome}</div>
                <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>{d.mansione || '—'}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Area dettaglio ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {!selected ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.textMuted }}>
            <div style={{ textAlign: 'center' }}>
              <User size={48} style={{ marginBottom: 16, opacity: 0.2 }} />
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 8 }}>Seleziona un dipendente</div>
              <div style={{ fontSize: 13 }}>Clicca su un dipendente nella lista per vedere i dettagli</div>
            </div>
          </div>
        ) : (
          <>
            {/* Header dipendente selezionato */}
            <div style={{ background: 'white', borderBottom: `1px solid ${COLORS.border}`, padding: '16px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 40, height: 40, borderRadius: '50%', background: `${COLORS.primary}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <User size={20} color={COLORS.primary} />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16, color: COLORS.text }}>
                    {selected.nome_completo || `${selected.cognome || ''} ${selected.nome || ''}`.trim()}
                  </div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted }}>{selected.mansione || ''} {selected.livello ? `· Livello ${selected.livello}` : ''}</div>
                </div>
              </div>
            </div>

            {/* Tab bar */}
            <div style={{ background: 'white', borderBottom: `2px solid ${COLORS.border}`, padding: '0 24px', display: 'flex', gap: 0 }}>
              {TABS.map(t => (
                <button
                  key={t.id}
                  data-testid={`tab-${t.id}`}
                  onClick={() => handleTabChange(t.id)}
                  style={{
                    padding: '12px 18px',
                    background: 'none',
                    border: 'none',
                    borderBottom: activeTab === t.id ? `3px solid ${COLORS.primary}` : '3px solid transparent',
                    color: activeTab === t.id ? COLORS.primary : COLORS.textMuted,
                    fontWeight: activeTab === t.id ? 700 : 400,
                    cursor: 'pointer',
                    fontSize: 13,
                    marginBottom: -2,
                    transition: 'color 0.15s, border-color 0.15s',
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Contenuto tab */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
              {activeTab === 'anagrafica'     && <TabAnagrafica     dip={selected} onSaved={d => setSelected({ ...selected, ...d })} />}
              {activeTab === 'contratti'      && <TabContratti      dip={selected} />}
              {activeTab === 'cedolini'       && <TabCedolini       dip={selected} />}
              {activeTab === 'movimenti'      && <TabMovimenti      dip={selected} />}
              {activeTab === 'giustificativi' && <TabGiustificativi dip={selected} />}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
