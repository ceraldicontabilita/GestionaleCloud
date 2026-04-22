/**
 * HRFeriePermessi.jsx — Workflow richieste Ferie/Permessi
 *
 * - Tabella richieste con filtri stato/tipo/dipendente
 * - Azioni approva/rifiuta inline per stato in_attesa
 * - Modal crea/edit richiesta con tipi ITA (Ferie/Permesso/Malattia/ROL/L.104/Congedo/Altro)
 * - Calcolo automatico giorni
 *
 * Design system Ceraldi: navy + oro, inline styles.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Calendar, Check, X, Edit2, Trash2, Clock, AlertCircle } from 'lucide-react';
import api from '../../api';
import { COLORS, SPACING, useIsMobile } from '../../lib/utils';

const TIPI = ['Ferie', 'Permesso', 'Malattia', 'ROL', 'L.104', 'Congedo', 'Altro'];

const TIPO_COLOR = {
  Ferie:    { bg: '#dbeafe', text: '#1d4ed8' },
  Permesso: { bg: '#e0e7ff', text: '#4338ca' },
  Malattia: { bg: '#fef3c7', text: '#92400e' },
  ROL:      { bg: '#dcfce7', text: '#16a34a' },
  'L.104':  { bg: '#f3e8ff', text: '#7c3aed' },
  Congedo:  { bg: '#f0fdf4', text: '#15803d' },
  Altro:    { bg: '#f1f5f9', text: '#64748b' },
};

const STATO_CONFIG = {
  in_attesa: { label: 'In attesa',  bg: COLORS.warningLight, text: COLORS.warning, icon: Clock },
  approvata: { label: 'Approvata',  bg: COLORS.successLight, text: COLORS.success, icon: Check },
  rifiutata: { label: 'Rifiutata',  bg: COLORS.dangerLight,  text: COLORS.danger,  icon: X     },
};

const AVATAR_BG = ['#0f2744', '#1e3a5f', '#b8860b', '#15803d', '#1d4ed8', '#7c3aed', '#b45309', '#b91c1c'];

const DEFAULT_FORM = {
  dipendente_id: '',
  tipo: 'Ferie',
  data_inizio: '',
  data_fine: '',
  motivazione: '',
};

function getInitials(nome = '', cognome = '') {
  const n = (nome || '').trim(), c = (cognome || '').trim();
  if (n && c) return (n[0] + c[0]).toUpperCase();
  if (c) return c.substring(0, 2).toUpperCase();
  if (n) return n.substring(0, 2).toUpperCase();
  return '?';
}
function formatData(d) {
  if (!d) return '—';
  try {
    const parts = d.split('T')[0].split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return d;
  } catch { return d; }
}
function calcGiorni(di, df) {
  if (!di || !df) return 0;
  const a = new Date(di), b = new Date(df);
  if (b < a) return 0;
  return Math.round((b - a) / (1000 * 60 * 60 * 24)) + 1;
}

// ═════════════════════════════════════════════════════════════════════════

export default function HRFeriePermessi() {
  const isMobile = useIsMobile();

  const [dipendenti, setDipendenti] = useState([]);
  const [richieste, setRichieste] = useState([]);
  const [loading, setLoading] = useState(true);

  const [filterStato, setFilterStato] = useState('tutti');
  const [filterTipo, setFilterTipo] = useState('tutti');
  const [filterDip, setFilterDip] = useState('tutti');

  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dipRes, richRes] = await Promise.all([
        api.get('/api/dipendenti'),
        api.get('/api/ferie-richieste'),
      ]);
      setDipendenti(Array.isArray(dipRes.data) ? dipRes.data : []);
      setRichieste(Array.isArray(richRes.data) ? richRes.data : []);
    } catch (e) {
      console.error('[HRFeriePermessi] load error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const openNew = () => {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setShowModal(true);
  };

  const openEdit = (r) => {
    if (r.stato !== 'in_attesa') {
      alert('Solo le richieste in attesa possono essere modificate');
      return;
    }
    setEditingId(r.id);
    setForm({
      dipendente_id: r.dipendente_id || '',
      tipo: r.tipo || 'Ferie',
      data_inizio: (r.data_inizio || '').split('T')[0],
      data_fine: (r.data_fine || '').split('T')[0],
      motivazione: r.motivazione || '',
    });
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingId(null);
    setForm(DEFAULT_FORM);
  };

  const submit = async () => {
    if (!form.dipendente_id || !form.tipo || !form.data_inizio || !form.data_fine) {
      alert('Compila tutti i campi obbligatori'); return;
    }
    if (calcGiorni(form.data_inizio, form.data_fine) <= 0) {
      alert('Data fine deve essere maggiore o uguale a data inizio'); return;
    }
    setSaving(true);
    try {
      if (editingId) await api.put(`/api/ferie-richieste/${editingId}`, form);
      else await api.post('/api/ferie-richieste', form);
      closeModal();
      await loadAll();
    } catch (e) {
      console.error(e);
      alert(e.response?.data?.detail || 'Errore salvataggio');
    } finally { setSaving(false); }
  };

  const approva = async (id) => {
    try {
      await api.post(`/api/ferie-richieste/${id}/approva`, {});
      await loadAll();
    } catch (e) { alert('Errore approvazione'); }
  };

  const rifiuta = async (id) => {
    const note = window.prompt('Motivo del rifiuto (opzionale):') || '';
    try {
      await api.post(`/api/ferie-richieste/${id}/rifiuta`, { note });
      await loadAll();
    } catch (e) { alert('Errore rifiuto'); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Eliminare la richiesta di ${r.tipo}?`)) return;
    try {
      await api.delete(`/api/ferie-richieste/${r.id}`);
      await loadAll();
    } catch (e) { alert('Errore eliminazione'); }
  };

  const dipById = useMemo(() => {
    const m = {};
    dipendenti.forEach((d) => { m[d.id] = d; });
    return m;
  }, [dipendenti]);

  const filtered = useMemo(() => {
    return richieste.filter((r) => {
      if (filterStato !== 'tutti' && r.stato !== filterStato) return false;
      if (filterTipo !== 'tutti' && r.tipo !== filterTipo) return false;
      if (filterDip !== 'tutti' && r.dipendente_id !== filterDip) return false;
      return true;
    });
  }, [richieste, filterStato, filterTipo, filterDip]);

  const stats = useMemo(() => ({
    inAttesa: richieste.filter((r) => r.stato === 'in_attesa').length,
    approvate: richieste.filter((r) => r.stato === 'approvata').length,
    rifiutate: richieste.filter((r) => r.stato === 'rifiutata').length,
  }), [richieste]);

  // ═══════════════════════════════════════════════════════════════════════
  return (
    <div style={{ padding: isMobile ? SPACING.lg : SPACING.xxl, minHeight: '100vh', backgroundColor: COLORS.bg }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: SPACING.md, marginBottom: SPACING.xxl }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: COLORS.text, margin: 0, letterSpacing: '-0.02em' }}>
            Ferie e Permessi
          </h1>
          <p style={{ fontSize: 14, color: COLORS.textMuted, margin: '4px 0 0' }}>
            Workflow di richiesta e approvazione ferie, permessi, malattie
          </p>
        </div>
        <button onClick={openNew} style={btnPrimary}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = COLORS.primaryLight)}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = COLORS.primary)}
          data-testid="nuova-richiesta-btn"
        >
          <Plus size={18} /> Nuova richiesta
        </button>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: SPACING.lg, marginBottom: SPACING.xl }}>
        <KpiCard label="In attesa" value={stats.inAttesa} color={COLORS.warning} bg={COLORS.warningLight} icon={Clock} />
        <KpiCard label="Approvate" value={stats.approvate} color={COLORS.success} bg={COLORS.successLight} icon={Check} />
        <KpiCard label="Rifiutate" value={stats.rifiutate} color={COLORS.danger} bg={COLORS.dangerLight} icon={X} />
      </div>

      {/* Filtri */}
      <div style={{ display: 'flex', gap: SPACING.md, marginBottom: SPACING.xl, flexWrap: 'wrap' }}>
        <select value={filterStato} onChange={(e) => setFilterStato(e.target.value)} style={selectStyle}>
          <option value="tutti">Tutti gli stati</option>
          {Object.entries(STATO_CONFIG).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
        </select>
        <select value={filterTipo} onChange={(e) => setFilterTipo(e.target.value)} style={selectStyle}>
          <option value="tutti">Tutti i tipi</option>
          {TIPI.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={filterDip} onChange={(e) => setFilterDip(e.target.value)} style={selectStyle}>
          <option value="tutti">Tutti i dipendenti</option>
          {dipendenti.map((d) => <option key={d.id} value={d.id}>{d.cognome} {d.nome}</option>)}
        </select>
      </div>

      {/* Tabella richieste */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48, color: COLORS.textMuted }}>Caricamento richieste...</div>
      ) : filtered.length === 0 ? (
        <div style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted, backgroundColor: COLORS.card, border: `1px dashed ${COLORS.border}`, borderRadius: 12 }}>
          {richieste.length === 0 ? 'Nessuna richiesta. Clicca "Nuova richiesta" per iniziare.' : 'Nessuna richiesta corrisponde ai filtri.'}
        </div>
      ) : (
        <div style={{ backgroundColor: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead>
                <tr style={{ backgroundColor: COLORS.bgAlt }}>
                  <th style={{ ...thStyle, textAlign: 'left', paddingLeft: SPACING.xl }}>Dipendente</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>Tipo</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>Periodo</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>Giorni</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>Stato</th>
                  <th style={{ ...thStyle, textAlign: 'right', paddingRight: SPACING.xl }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, idx) => {
                  const dip = dipById[r.dipendente_id];
                  const stato = STATO_CONFIG[r.stato] || STATO_CONFIG.in_attesa;
                  const StatoIcon = stato.icon;
                  const tipoCol = TIPO_COLOR[r.tipo] || TIPO_COLOR.Altro;
                  return (
                    <tr key={r.id} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                      <td style={{ padding: `${SPACING.md}px ${SPACING.xl}px` }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{
                            width: 32, height: 32, borderRadius: '50%',
                            backgroundColor: AVATAR_BG[idx % AVATAR_BG.length],
                            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 12, fontWeight: 600, flexShrink: 0,
                          }}>
                            {dip ? getInitials(dip.nome, dip.cognome) : '?'}
                          </div>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 500, color: COLORS.text }}>
                              {dip ? `${dip.cognome} ${dip.nome}` : '—'}
                            </div>
                            {dip?.ruolo && <div style={{ fontSize: 12, color: COLORS.textMuted }}>{dip.ruolo}</div>}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px` }}>
                        <span style={{
                          padding: '3px 10px', borderRadius: 12,
                          backgroundColor: tipoCol.bg, color: tipoCol.text,
                          fontSize: 12, fontWeight: 500,
                        }}>
                          {r.tipo}
                        </span>
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px`, fontSize: 13, color: COLORS.text }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <Calendar size={13} color={COLORS.textMuted} />
                          {formatData(r.data_inizio)} → {formatData(r.data_fine)}
                        </div>
                        {r.motivazione && (
                          <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2, fontStyle: 'italic' }}>
                            {r.motivazione}
                          </div>
                        )}
                        {r.note_approvazione && (
                          <div style={{ fontSize: 12, color: r.stato === 'rifiutata' ? COLORS.danger : COLORS.success, marginTop: 2 }}>
                            <AlertCircle size={11} style={{ verticalAlign: 'middle' }} /> {r.note_approvazione}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px`, textAlign: 'center', fontSize: 14, fontWeight: 600, color: COLORS.text }}>
                        {r.giorni}
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px`, textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          padding: '4px 10px', borderRadius: 12,
                          backgroundColor: stato.bg, color: stato.text,
                          fontSize: 11, fontWeight: 600,
                        }}>
                          <StatoIcon size={12} /> {stato.label}
                        </span>
                      </td>
                      <td style={{ padding: `${SPACING.md}px ${SPACING.xl}px`, textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: 4 }}>
                          {r.stato === 'in_attesa' && (
                            <>
                              <button onClick={() => approva(r.id)} style={{ ...btnSm, backgroundColor: COLORS.success, color: '#fff' }}>
                                <Check size={13} /> Approva
                              </button>
                              <button onClick={() => rifiuta(r.id)} style={{ ...btnSm, backgroundColor: COLORS.danger, color: '#fff' }}>
                                <X size={13} />
                              </button>
                              <button onClick={() => openEdit(r)} style={{ ...btnSm, backgroundColor: COLORS.infoLight, color: COLORS.info }}>
                                <Edit2 size={13} />
                              </button>
                            </>
                          )}
                          <button onClick={() => remove(r)} style={{ ...btnSm, backgroundColor: COLORS.dangerLight, color: COLORS.danger }}>
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showModal && (
        <ModalRichiesta
          form={form}
          setForm={setForm}
          dipendenti={dipendenti}
          editing={!!editingId}
          saving={saving}
          onClose={closeModal}
          onSubmit={submit}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
function KpiCard({ label, value, color, bg, icon: Icon }) {
  return (
    <div style={{ backgroundColor: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: SPACING.lg, display: 'flex', alignItems: 'center', gap: SPACING.md }}>
      <div style={{ width: 44, height: 44, borderRadius: 10, backgroundColor: bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Icon size={22} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 2 }}>{label}</div>
      </div>
    </div>
  );
}

function ModalRichiesta({ form, setForm, dipendenti, editing, saving, onClose, onSubmit }) {
  const giorni = calcGiorni(form.data_inizio, form.data_fine);
  return (
    <div onClick={onClose} style={overlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalStyle, maxWidth: 560 }}>
        <div style={modalHeader}>
          <h3 style={{ fontSize: 17, fontWeight: 600, color: COLORS.text, margin: 0 }}>
            {editing ? 'Modifica richiesta' : 'Nuova richiesta'}
          </h3>
          <button onClick={onClose} style={closeBtn}><X size={20} /></button>
        </div>

        <div style={{ padding: SPACING.xl }}>
          <FormField label="Dipendente *">
            <select value={form.dipendente_id} onChange={(e) => setForm((f) => ({ ...f, dipendente_id: e.target.value }))} style={inputStyle}>
              <option value="">Seleziona...</option>
              {dipendenti.map((d) => <option key={d.id} value={d.id}>{d.cognome} {d.nome}</option>)}
            </select>
          </FormField>

          <FormField label="Tipo richiesta *">
            <select value={form.tipo} onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))} style={inputStyle}>
              {TIPI.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </FormField>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: SPACING.lg }}>
            <FormField label="Dal *">
              <input type="date" value={form.data_inizio} onChange={(e) => setForm((f) => ({ ...f, data_inizio: e.target.value }))} style={inputStyle} />
            </FormField>
            <FormField label="Al *">
              <input type="date" value={form.data_fine} onChange={(e) => setForm((f) => ({ ...f, data_fine: e.target.value }))} style={inputStyle} />
            </FormField>
          </div>

          {giorni > 0 && (
            <div style={{ padding: 10, backgroundColor: COLORS.primarySoft, borderRadius: 8, fontSize: 13, color: COLORS.primary, textAlign: 'center', marginBottom: SPACING.lg, fontWeight: 500 }}>
              Durata: <strong>{giorni}</strong> {giorni === 1 ? 'giorno' : 'giorni'}
            </div>
          )}

          <FormField label="Motivazione (opzionale)">
            <textarea value={form.motivazione} onChange={(e) => setForm((f) => ({ ...f, motivazione: e.target.value }))}
                      rows={3} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }} />
          </FormField>
        </div>

        <div style={modalFooter}>
          <button onClick={onClose} style={btnSecondary}>Annulla</button>
          <button onClick={onSubmit} disabled={saving} style={{ ...btnPrimary, opacity: saving ? 0.5 : 1 }}>
            {saving ? 'Salvo...' : editing ? 'Salva modifiche' : 'Invia richiesta'}
          </button>
        </div>
      </div>
    </div>
  );
}

function FormField({ label, children }) {
  return (
    <div style={{ marginBottom: SPACING.lg }}>
      <label style={fieldLabel}>{label}</label>
      {children}
    </div>
  );
}

// ═══════ Styles ═══════
const btnPrimary = { display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 18px', backgroundColor: COLORS.primary, color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', transition: 'background-color 0.15s' };
const btnSecondary = { padding: '10px 18px', backgroundColor: 'transparent', color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 14, fontWeight: 500, cursor: 'pointer' };
const btnSm = { display: 'inline-flex', alignItems: 'center', gap: 4, padding: '6px 10px', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 500, cursor: 'pointer' };
const selectStyle = { padding: '10px 12px', fontSize: 13, border: `1px solid ${COLORS.border}`, borderRadius: 8, backgroundColor: COLORS.card, color: COLORS.text, cursor: 'pointer', outline: 'none', minWidth: 160 };
const overlayStyle = { position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 };
const modalStyle = { backgroundColor: COLORS.card, borderRadius: 12, width: '100%', maxHeight: '90vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.25)' };
const modalHeader = { padding: `${SPACING.lg}px ${SPACING.xl}px`, borderBottom: `1px solid ${COLORS.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' };
const modalFooter = { padding: `${SPACING.lg}px ${SPACING.xl}px`, borderTop: `1px solid ${COLORS.border}`, display: 'flex', justifyContent: 'flex-end', gap: SPACING.md };
const closeBtn = { padding: 6, background: 'transparent', border: 'none', borderRadius: 6, cursor: 'pointer', color: COLORS.textMuted };
const thStyle = { padding: '12px 8px', fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: `1px solid ${COLORS.border}` };
const inputStyle = { width: '100%', padding: '10px 12px', fontSize: 14, border: `1px solid ${COLORS.border}`, borderRadius: 8, outline: 'none', boxSizing: 'border-box', backgroundColor: COLORS.card, color: COLORS.text };
const fieldLabel = { display: 'block', fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 };
