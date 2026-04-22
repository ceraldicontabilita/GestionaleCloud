/**
 * HRDocumenti.jsx — Gestione Documenti HR dei Dipendenti
 *
 * Layout ispirato a dipendenti-cloud:
 *   - Tabella documenti con ricerca e filtri per tipo/dipendente
 *   - Alert documenti in scadenza < 30 giorni
 *   - Pulsante Nuovo documento → modale
 *   - Edit inline via riga
 *
 * Design system Ceraldi: navy + oro, inline styles.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, FileText, Search, AlertTriangle, Edit2, Trash2, X, Download, Calendar, User } from 'lucide-react';
import api from '../../api';
import { COLORS, SPACING, useIsMobile } from '../../lib/utils';

const TIPI_DOCUMENTO = [
  'Codice Fiscale', 'Carta Identità', 'Patente', 'Permesso Soggiorno',
  'Unilav', 'Contratto', 'CUD', 'Certificato Medico', 'Altro',
];

const AVATAR_BG = ['#0f2744', '#1e3a5f', '#b8860b', '#15803d', '#1d4ed8', '#7c3aed', '#b45309', '#b91c1c'];

const DEFAULT_FORM = {
  dipendente_id: '',
  titolo: '',
  tipo: TIPI_DOCUMENTO[0],
  scadenza: '',
  file_url: '',
  note: '',
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

function giorniAScadenza(scadenza) {
  if (!scadenza) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const s = new Date(scadenza.split('T')[0]);
  return Math.ceil((s - today) / (1000 * 60 * 60 * 24));
}

// ═════════════════════════════════════════════════════════════════════════

export default function HRDocumenti() {
  const isMobile = useIsMobile();

  const [dipendenti, setDipendenti] = useState([]);
  const [documenti, setDocumenti] = useState([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [filterTipo, setFilterTipo] = useState('tutti');
  const [filterDip, setFilterDip] = useState('tutti');

  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dipRes, docRes] = await Promise.all([
        api.get('/api/dipendenti'),
        api.get('/api/hr-documenti'),
      ]);
      setDipendenti(Array.isArray(dipRes.data) ? dipRes.data : []);
      setDocumenti(Array.isArray(docRes.data) ? docRes.data : []);
    } catch (e) {
      console.error('[HRDocumenti] load error:', e);
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

  const openEdit = (d) => {
    setEditingId(d.id);
    setForm({
      dipendente_id: d.dipendente_id || '',
      titolo: d.titolo || '',
      tipo: d.tipo || TIPI_DOCUMENTO[0],
      scadenza: (d.scadenza || '').split('T')[0],
      file_url: d.file_url || '',
      note: d.note || '',
    });
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingId(null);
    setForm(DEFAULT_FORM);
  };

  const submit = async () => {
    if (!form.dipendente_id || !form.titolo.trim() || !form.tipo.trim()) {
      alert('Compila i campi obbligatori'); return;
    }
    setSaving(true);
    try {
      const payload = { ...form, scadenza: form.scadenza || null };
      if (editingId) await api.put(`/api/hr-documenti/${editingId}`, payload);
      else await api.post('/api/hr-documenti', payload);
      closeModal();
      await loadAll();
    } catch (e) {
      console.error('[HRDocumenti] submit error:', e);
      alert('Errore nel salvataggio');
    } finally { setSaving(false); }
  };

  const remove = async (d) => {
    if (!window.confirm(`Eliminare il documento "${d.titolo}"?`)) return;
    try {
      await api.delete(`/api/hr-documenti/${d.id}`);
      await loadAll();
    } catch (e) { alert('Errore eliminazione'); }
  };

  const dipById = useMemo(() => {
    const m = {};
    dipendenti.forEach((d) => { m[d.id] = d; });
    return m;
  }, [dipendenti]);

  const filtered = useMemo(() => {
    const s = search.toLowerCase().trim();
    return documenti.filter((d) => {
      if (filterTipo !== 'tutti' && d.tipo !== filterTipo) return false;
      if (filterDip !== 'tutti' && d.dipendente_id !== filterDip) return false;
      if (s) {
        const dip = dipById[d.dipendente_id];
        const hay = `${d.titolo} ${d.tipo} ${dip?.cognome || ''} ${dip?.nome || ''}`.toLowerCase();
        if (!hay.includes(s)) return false;
      }
      return true;
    });
  }, [documenti, dipById, search, filterTipo, filterDip]);

  const inScadenza = useMemo(() => {
    return documenti.filter((d) => {
      const g = giorniAScadenza(d.scadenza);
      return g !== null && g >= 0 && g <= 30;
    });
  }, [documenti]);

  // ═══════════════════════════════════════════════════════════════════════
  return (
    <div style={{ padding: isMobile ? SPACING.lg : SPACING.xxl, minHeight: '100vh', backgroundColor: COLORS.bg }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: SPACING.md, marginBottom: SPACING.xxl }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: COLORS.text, margin: 0, letterSpacing: '-0.02em' }}>
            Documenti HR
          </h1>
          <p style={{ fontSize: 14, color: COLORS.textMuted, margin: '4px 0 0' }}>
            Archivio documenti personali dei dipendenti con alert scadenze
          </p>
        </div>
        <button
          onClick={openNew}
          style={btnPrimary}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = COLORS.primaryLight)}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = COLORS.primary)}
          data-testid="nuovo-documento-btn"
        >
          <Plus size={18} /> Nuovo documento
        </button>
      </div>

      {/* Alert documenti in scadenza */}
      {inScadenza.length > 0 && (
        <div style={{
          backgroundColor: COLORS.warningLight, border: `1px solid ${COLORS.warning}40`,
          borderRadius: 10, padding: SPACING.lg, marginBottom: SPACING.xl,
          display: 'flex', alignItems: 'center', gap: SPACING.md,
        }}>
          <AlertTriangle size={20} color={COLORS.warning} />
          <div style={{ fontSize: 14, color: COLORS.warning }}>
            <strong>{inScadenza.length}</strong> {inScadenza.length === 1 ? 'documento' : 'documenti'} in scadenza nei prossimi 30 giorni.
          </div>
        </div>
      )}

      {/* Filtri */}
      <div style={{ display: 'flex', gap: SPACING.md, marginBottom: SPACING.xl, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: '1 1 240px', minWidth: 200 }}>
          <Search size={16} color={COLORS.textMuted} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca per titolo, tipo, dipendente..."
            style={{ ...inputStyle, paddingLeft: 36 }}
          />
        </div>
        <select value={filterTipo} onChange={(e) => setFilterTipo(e.target.value)} style={selectStyle}>
          <option value="tutti">Tutti i tipi</option>
          {TIPI_DOCUMENTO.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={filterDip} onChange={(e) => setFilterDip(e.target.value)} style={selectStyle}>
          <option value="tutti">Tutti i dipendenti</option>
          {dipendenti.map((d) => <option key={d.id} value={d.id}>{d.cognome} {d.nome}</option>)}
        </select>
      </div>

      {/* Tabella */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48, color: COLORS.textMuted }}>Caricamento documenti...</div>
      ) : filtered.length === 0 ? (
        <div style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted, backgroundColor: COLORS.card, border: `1px dashed ${COLORS.border}`, borderRadius: 12 }}>
          {documenti.length === 0 ? 'Nessun documento archiviato.' : 'Nessun documento corrisponde ai filtri.'}
        </div>
      ) : (
        <div style={{ backgroundColor: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 800 }}>
              <thead>
                <tr style={{ backgroundColor: COLORS.bgAlt }}>
                  <th style={{ ...thStyle, textAlign: 'left', paddingLeft: SPACING.xl }}>Dipendente</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>Documento</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>Tipo</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>Scadenza</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>Caricato</th>
                  <th style={{ ...thStyle, textAlign: 'right', paddingRight: SPACING.xl }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((d, idx) => {
                  const dip = dipById[d.dipendente_id];
                  const giorni = giorniAScadenza(d.scadenza);
                  const isExpiring = giorni !== null && giorni >= 0 && giorni <= 30;
                  const isExpired = giorni !== null && giorni < 0;
                  return (
                    <tr key={d.id} style={{ borderTop: `1px solid ${COLORS.border}` }}>
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
                          <div style={{ fontSize: 14, color: COLORS.text }}>
                            {dip ? `${dip.cognome} ${dip.nome}` : '—'}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px` }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <FileText size={16} color={COLORS.primary} />
                          <span style={{ fontSize: 14, fontWeight: 500, color: COLORS.text }}>{d.titolo}</span>
                        </div>
                        {d.note && (
                          <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2, marginLeft: 24 }}>
                            {d.note}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px` }}>
                        <span style={{
                          padding: '3px 10px', borderRadius: 12,
                          backgroundColor: COLORS.primarySoft, color: COLORS.primary,
                          fontSize: 12, fontWeight: 500,
                        }}>
                          {d.tipo}
                        </span>
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px`, textAlign: 'center' }}>
                        {d.scadenza ? (
                          <div>
                            <div style={{ fontSize: 13, color: isExpired ? COLORS.danger : isExpiring ? COLORS.warning : COLORS.text }}>
                              {formatData(d.scadenza)}
                            </div>
                            {giorni !== null && (
                              <div style={{ fontSize: 11, color: isExpired ? COLORS.danger : isExpiring ? COLORS.warning : COLORS.textMuted, fontWeight: 500 }}>
                                {isExpired ? `Scaduto da ${Math.abs(giorni)}gg` : giorni === 0 ? 'Oggi' : `tra ${giorni}gg`}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span style={{ fontSize: 13, color: COLORS.textSubtle }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: `${SPACING.md}px 8px`, textAlign: 'center', fontSize: 13, color: COLORS.textMuted }}>
                        {formatData(d.data_caricamento)}
                      </td>
                      <td style={{ padding: `${SPACING.md}px ${SPACING.xl}px`, textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: 4 }}>
                          {d.file_url && (
                            <a href={d.file_url} target="_blank" rel="noopener noreferrer"
                               style={{ ...btnSm, backgroundColor: COLORS.successLight, color: COLORS.success, textDecoration: 'none' }}>
                              <Download size={13} />
                            </a>
                          )}
                          <button onClick={() => openEdit(d)} style={{ ...btnSm, backgroundColor: COLORS.infoLight, color: COLORS.info }}>
                            <Edit2 size={13} />
                          </button>
                          <button onClick={() => remove(d)} style={{ ...btnSm, backgroundColor: COLORS.dangerLight, color: COLORS.danger }}>
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
        <ModalDocumento
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
function ModalDocumento({ form, setForm, dipendenti, editing, saving, onClose, onSubmit }) {
  return (
    <div onClick={onClose} style={overlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalStyle, maxWidth: 560 }}>
        <div style={modalHeader}>
          <h3 style={{ fontSize: 17, fontWeight: 600, color: COLORS.text, margin: 0 }}>
            {editing ? 'Modifica documento' : 'Nuovo documento'}
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

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: SPACING.lg }}>
            <FormField label="Titolo *">
              <input value={form.titolo} onChange={(e) => setForm((f) => ({ ...f, titolo: e.target.value }))}
                     placeholder="Es. Carta identità n.XYZ123" style={inputStyle} />
            </FormField>
            <FormField label="Tipo *">
              <select value={form.tipo} onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))} style={inputStyle}>
                {TIPI_DOCUMENTO.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </FormField>
          </div>

          <FormField label="Data scadenza (opzionale)">
            <input type="date" value={form.scadenza} onChange={(e) => setForm((f) => ({ ...f, scadenza: e.target.value }))} style={inputStyle} />
          </FormField>

          <FormField label="URL file (opzionale)">
            <input type="url" value={form.file_url} onChange={(e) => setForm((f) => ({ ...f, file_url: e.target.value }))}
                   placeholder="https://drive.google.com/..." style={inputStyle} />
          </FormField>

          <FormField label="Note (opzionale)">
            <textarea value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                      rows={2} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }} />
          </FormField>
        </div>

        <div style={modalFooter}>
          <button onClick={onClose} style={btnSecondary}>Annulla</button>
          <button onClick={onSubmit} disabled={saving} style={{ ...btnPrimary, opacity: saving ? 0.5 : 1 }}>
            {saving ? 'Salvo...' : editing ? 'Salva modifiche' : 'Crea documento'}
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
