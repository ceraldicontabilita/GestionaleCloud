/**
 * HRAcconti.jsx — Gestione Acconti Dipendenti
 *
 * Layout stile prototipo Ceraldi (navy + oro):
 *   - 4 KPI card in alto (totale, conteggio, tipo più usato, ultimo acconto)
 *   - Filtri: anno, mese, tipo, dipendente
 *   - Tabella acconti con azioni inline (modifica/elimina)
 *   - Modale create/edit (anche TFR con caveat)
 *
 * CRUD usa gli endpoint già esistenti in tfr.py:
 *   POST/PUT/DELETE /api/tfr/acconti     (scrive su collection acconti_dipendenti)
 * La lista e il riepilogo passano per i nuovi /api/acconti.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Plus, Edit2, Trash2, Euro, Users, Calendar, AlertCircle, X, RefreshCw,
} from 'lucide-react';
import api from '../../api';
import { COLORS, SPACING, useIsMobile } from '../../lib/utils';

// ═══════════════════════════════════════════════════════════════════════
// Costanti
// ═══════════════════════════════════════════════════════════════════════
const TIPI = [
  { id: 'stipendio', label: 'Acconto stipendio', color: '#0f2744' },
  { id: 'tredicesima', label: 'Acconto 13ª', color: '#b8860b' },
  { id: 'quattordicesima', label: 'Acconto 14ª', color: '#1d4ed8' },
  { id: 'ferie', label: 'Acconto ferie', color: '#15803d' },
  { id: 'tfr', label: 'Acconto TFR', color: '#b45309' },
  { id: 'prestito', label: 'Prestito', color: '#7c3aed' },
];
const TIPI_MAP = TIPI.reduce((acc, t) => ((acc[t.id] = t), acc), {});

const MESI = [
  'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
];
const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i);

const AVATAR_COLORS = [
  '#0f2744', '#b8860b', '#15803d', '#1d4ed8',
  '#7c3aed', '#b45309', '#b91c1c', '#1e3a5f',
];

// ═══════════════════════════════════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════════════════════════════════
function formatEuro(v) {
  if (v == null || isNaN(v)) return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
}
function formatData(d) {
  if (!d) return '—';
  try {
    if (d.includes('-') && d.length >= 10) {
      const [y, m, g] = d.split('T')[0].split('-');
      return `${g}/${m}/${y}`;
    }
    return d;
  } catch {
    return d;
  }
}
function initials(nome = '', cognome = '') {
  const n = (nome || '').trim();
  const c = (cognome || '').trim();
  if (n && c) return (n[0] + c[0]).toUpperCase();
  if (c) return c.substring(0, 2).toUpperCase();
  if (n) return n.substring(0, 2).toUpperCase();
  return '?';
}

// ═══════════════════════════════════════════════════════════════════════
// Componente
// ═══════════════════════════════════════════════════════════════════════
export default function HRAcconti() {
  const isMobile = useIsMobile();

  // Data
  const [dipendenti, setDipendenti] = useState([]);
  const [acconti, setAcconti] = useState([]);
  const [totale, setTotale] = useState(0);
  const [loading, setLoading] = useState(true);

  // Filtri
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState(''); // '' = tutti
  const [tipoFilter, setTipoFilter] = useState('');
  const [dipFilter, setDipFilter] = useState('');

  // Modale
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null); // acconto da modificare, null = nuovo
  const [form, setForm] = useState(() => defaultForm());
  const [saving, setSaving] = useState(false);

  // ───── Load ─────
  const loadData = useCallback(async (signal) => {
    setLoading(true);
    try {
      const params = { anno };
      if (mese) params.mese = parseInt(mese, 10);
      if (tipoFilter) params.tipo = tipoFilter;
      if (dipFilter) params.dipendente_id = dipFilter;

      const [dipRes, accRes] = await Promise.all([
        api.get('/api/dipendenti', { signal }),
        api.get('/api/acconti', { params, signal }),
      ]);

      if (signal?.aborted) return;

      const dipList = Array.isArray(dipRes.data)
        ? dipRes.data
        : dipRes.data?.dipendenti || [];
      setDipendenti(dipList);
      setAcconti(accRes.data?.acconti || []);
      setTotale(accRes.data?.totale || 0);
    } catch (e) {
      // Ignora cancellation: non è un errore reale
      if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return;
      console.error('[HRAcconti] load error', e);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [anno, mese, tipoFilter, dipFilter]);

  useEffect(() => {
    // Race guard (Codex P2 pattern): cambi rapidi di filtro generano richieste
    // sovrapposte. Abortiamo la precedente prima di lanciare la nuova per
    // evitare che una risposta obsoleta sovrascriva lo stato.
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  // ───── KPI ─────
  const kpi = useMemo(() => {
    const perTipo = {};
    acconti.forEach((a) => {
      const k = a.tipo || 'non_specificato';
      perTipo[k] = (perTipo[k] || 0) + (parseFloat(a.importo) || 0);
    });
    const tipoPiuUsato = Object.entries(perTipo).sort((a, b) => b[1] - a[1])[0];
    const ultimo = acconti[0]; // già ordinato per data desc
    return {
      totale,
      count: acconti.length,
      tipoLabel: tipoPiuUsato ? TIPI_MAP[tipoPiuUsato[0]]?.label || tipoPiuUsato[0] : '—',
      tipoImporto: tipoPiuUsato ? tipoPiuUsato[1] : 0,
      ultimo,
    };
  }, [acconti, totale]);

  // ───── Handlers ─────
  const openNew = () => {
    setEditing(null);
    setForm(defaultForm());
    setModalOpen(true);
  };

  const openEdit = (a) => {
    setEditing(a);
    setForm({
      dipendente_id: a.dipendente_id || '',
      tipo: a.tipo || 'stipendio',
      importo: a.importo || '',
      data: a.data || new Date().toISOString().slice(0, 10),
      note: a.note || '',
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditing(null);
  };

  const submit = async () => {
    if (!form.dipendente_id) {
      alert('Seleziona un dipendente');
      return;
    }
    const importo = parseFloat(form.importo);
    if (!importo || importo <= 0) {
      alert('L\'importo deve essere positivo');
      return;
    }
    if (!form.data) {
      alert('La data è obbligatoria');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        dipendente_id: form.dipendente_id,
        tipo: form.tipo,
        importo,
        data: form.data,
        note: form.note || '',
      };
      if (editing) {
        await api.put(`/api/tfr/acconti/${editing.id}`, payload);
      } else {
        await api.post('/api/tfr/acconti', payload);
      }
      closeModal();
      await loadData();
    } catch (e) {
      console.error('[HRAcconti] submit error', e);
      alert('Errore nel salvataggio: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  const eliminaAcconto = async (a) => {
    const dip = dipendenti.find((d) => d.id === a.dipendente_id);
    const name = dip ? `${dip.cognome} ${dip.nome}` : a.dipendente_nome || '?';
    if (
      !window.confirm(
        `Eliminare l'acconto di ${formatEuro(a.importo)} del ${formatData(
          a.data
        )} a ${name}?\n\nQuesta azione non può essere annullata.${
          a.tipo === 'tfr'
            ? '\n\nATTENZIONE: trattandosi di acconto TFR, il TFR accantonato del dipendente verrà ripristinato.'
            : ''
        }`
      )
    )
      return;
    try {
      await api.delete(`/api/tfr/acconti/${a.id}`);
      await loadData();
    } catch (e) {
      console.error('[HRAcconti] delete error', e);
      alert('Errore nell\'eliminazione: ' + (e.response?.data?.detail || e.message));
    }
  };

  // ═══════════════════════════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════════════════════════
  return (
    <div
      style={{
        padding: isMobile ? SPACING.lg : SPACING.xxl,
        minHeight: '100vh',
        backgroundColor: COLORS.bg,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: SPACING.md,
          marginBottom: SPACING.xl,
        }}
      >
        <div>
          <h1
            style={{
              fontSize: 26,
              fontWeight: 700,
              color: COLORS.text,
              margin: 0,
              letterSpacing: '-0.02em',
            }}
          >
            Gestione Acconti
          </h1>
          <p style={{ fontSize: 13, color: COLORS.textMuted, margin: '4px 0 0' }}>
            Anticipi stipendio, 13ª/14ª, TFR, ferie e prestiti ai dipendenti
          </p>
        </div>
        <button
          onClick={openNew}
          style={btnPrimary}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = COLORS.primaryLight)}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = COLORS.primary)}
          data-testid="btn-nuovo-acconto"
        >
          <Plus size={16} /> Nuovo acconto
        </button>
      </div>

      {/* KPI Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
          gap: SPACING.lg,
          marginBottom: SPACING.xl,
        }}
      >
        <KpiCard
          icon={<Euro size={20} color={COLORS.primary} />}
          label="Totale erogato"
          value={formatEuro(kpi.totale)}
          sub={`${anno}${mese ? ' · ' + MESI[mese - 1] : ''}`}
          accent={COLORS.primary}
        />
        <KpiCard
          icon={<Calendar size={20} color={COLORS.accent} />}
          label="Numero acconti"
          value={kpi.count.toString()}
          sub={kpi.count === 1 ? 'operazione' : 'operazioni'}
          accent={COLORS.accent}
        />
        <KpiCard
          icon={<Users size={20} color={COLORS.info} />}
          label="Tipo prevalente"
          value={kpi.tipoLabel}
          sub={formatEuro(kpi.tipoImporto)}
          accent={COLORS.info}
        />
        <KpiCard
          icon={<AlertCircle size={20} color={COLORS.success} />}
          label="Ultimo acconto"
          value={kpi.ultimo ? formatEuro(kpi.ultimo.importo) : '—'}
          sub={kpi.ultimo ? formatData(kpi.ultimo.data) : 'Nessuno'}
          accent={COLORS.success}
        />
      </div>

      {/* Filtri */}
      <div
        style={{
          display: 'flex',
          gap: SPACING.md,
          flexWrap: 'wrap',
          padding: SPACING.md,
          backgroundColor: COLORS.card,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 10,
          marginBottom: SPACING.lg,
          alignItems: 'center',
        }}
      >
        <Select value={anno} onChange={(v) => setAnno(parseInt(v, 10))} label="Anno">
          {ANNI.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </Select>
        <Select value={mese} onChange={setMese} label="Mese">
          <option value="">Tutti</option>
          {MESI.map((m, i) => (
            <option key={m} value={i + 1}>
              {m}
            </option>
          ))}
        </Select>
        <Select value={tipoFilter} onChange={setTipoFilter} label="Tipo">
          <option value="">Tutti</option>
          {TIPI.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </Select>
        <Select value={dipFilter} onChange={setDipFilter} label="Dipendente">
          <option value="">Tutti</option>
          {dipendenti.map((d) => (
            <option key={d.id} value={d.id}>
              {d.cognome} {d.nome}
            </option>
          ))}
        </Select>
        <div style={{ flex: 1 }} />
        <button
          onClick={loadData}
          style={btnGhost}
          data-testid="btn-ricarica"
          title="Ricarica"
        >
          <RefreshCw
            size={14}
            style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
          />
          Aggiorna
        </button>
      </div>

      {/* Tabella acconti */}
      <div
        style={{
          backgroundColor: COLORS.card,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 12,
          overflow: 'hidden',
          marginBottom: SPACING.xxl,
        }}
      >
        <div
          style={{
            padding: `${SPACING.md}px ${SPACING.lg}px`,
            borderBottom: `1px solid ${COLORS.border}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <h3
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: COLORS.text,
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Euro size={16} color={COLORS.primary} />
            Elenco acconti ({acconti.length})
          </h3>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ backgroundColor: COLORS.bgAlt }}>
                <th style={thStyle}>Data</th>
                <th style={{ ...thStyle, textAlign: 'left' }}>Dipendente</th>
                <th style={thStyle}>Tipo</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Importo</th>
                <th style={{ ...thStyle, textAlign: 'left' }}>Note</th>
                <th style={{ ...thStyle, width: 90 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
                    Caricamento…
                  </td>
                </tr>
              )}
              {!loading && acconti.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}>
                    Nessun acconto trovato per i filtri selezionati.
                  </td>
                </tr>
              )}
              {!loading &&
                acconti.map((a, idx) => {
                  const tipo = TIPI_MAP[a.tipo] || { label: a.tipo, color: COLORS.gray[400] };
                  const dip = dipendenti.find((d) => d.id === a.dipendente_id);
                  return (
                    <tr
                      key={a.id || idx}
                      style={{ borderTop: `1px solid ${COLORS.border}` }}
                    >
                      <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 600 }}>
                        {formatData(a.data)}
                      </td>
                      <td style={tdStyle}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div
                            style={{
                              width: 28,
                              height: 28,
                              borderRadius: '50%',
                              backgroundColor:
                                AVATAR_COLORS[idx % AVATAR_COLORS.length],
                              color: '#fff',
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: 11,
                              fontWeight: 700,
                              flexShrink: 0,
                            }}
                          >
                            {dip
                              ? initials(dip.nome, dip.cognome)
                              : initials('', a.dipendente_nome || '')}
                          </div>
                          <span style={{ fontWeight: 500 }}>
                            {dip
                              ? `${dip.cognome} ${dip.nome}`
                              : a.dipendente_nome || '—'}
                          </span>
                        </div>
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '3px 10px',
                            borderRadius: 6,
                            fontSize: 11,
                            fontWeight: 700,
                            backgroundColor: `${tipo.color}20`,
                            color: tipo.color,
                          }}
                        >
                          {tipo.label}
                        </span>
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          textAlign: 'right',
                          fontWeight: 700,
                          color: COLORS.primary,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {formatEuro(a.importo)}
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          color: COLORS.textMuted,
                          fontSize: 12,
                          maxWidth: 300,
                        }}
                      >
                        {a.note || '—'}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <div style={{ display: 'inline-flex', gap: 4 }}>
                          <button
                            onClick={() => openEdit(a)}
                            style={iconBtn(COLORS.info, COLORS.infoLight)}
                            title="Modifica"
                          >
                            <Edit2 size={13} />
                          </button>
                          <button
                            onClick={() => eliminaAcconto(a)}
                            style={iconBtn(COLORS.danger, COLORS.dangerLight)}
                            title="Elimina"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
            {!loading && acconti.length > 0 && (
              <tfoot>
                <tr style={{ backgroundColor: COLORS.bgAlt, borderTop: `2px solid ${COLORS.borderDark}` }}>
                  <td colSpan={3} style={{ ...tdStyle, fontWeight: 600, textAlign: 'right', color: COLORS.textMuted, textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.05em' }}>
                    Totale
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      textAlign: 'right',
                      fontWeight: 700,
                      fontSize: 15,
                      color: COLORS.primary,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {formatEuro(totale)}
                  </td>
                  <td colSpan={2}></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>

      {/* Modale create/edit */}
      {modalOpen && (
        <AccontoModal
          form={form}
          setForm={setForm}
          editing={editing}
          dipendenti={dipendenti}
          saving={saving}
          onClose={closeModal}
          onSubmit={submit}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════════════

function defaultForm() {
  return {
    dipendente_id: '',
    tipo: 'stipendio',
    importo: '',
    data: new Date().toISOString().slice(0, 10),
    note: '',
  };
}

function KpiCard({ icon, label, value, sub, accent }) {
  return (
    <div
      style={{
        backgroundColor: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 12,
        padding: SPACING.lg,
        borderTop: `3px solid ${accent || COLORS.primary}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {icon}
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: COLORS.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          {label}
        </span>
      </div>
      <div
        style={{
          fontSize: 22,
          fontWeight: 700,
          color: COLORS.text,
          fontVariantNumeric: 'tabular-nums',
          marginBottom: 2,
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 12, color: COLORS.textMuted }}>{sub}</div>
    </div>
  );
}

function Select({ value, onChange, label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <label
        style={{
          fontSize: 10,
          fontWeight: 600,
          color: COLORS.textMuted,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '7px 10px',
          fontSize: 13,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 8,
          backgroundColor: COLORS.card,
          color: COLORS.text,
          outline: 'none',
          cursor: 'pointer',
          minWidth: 120,
        }}
      >
        {children}
      </select>
    </div>
  );
}

function AccontoModal({ form, setForm, editing, dipendenti, saving, onClose, onSubmit }) {
  const isTFR = form.tipo === 'tfr';
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: COLORS.card,
          borderRadius: 12,
          width: '100%',
          maxWidth: 500,
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
        }}
      >
        <div
          style={{
            padding: '16px 20px',
            borderBottom: `1px solid ${COLORS.border}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
            {editing ? 'Modifica acconto' : 'Nuovo acconto'}
          </h3>
          <button
            onClick={onClose}
            style={{
              padding: 4,
              background: 'transparent',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
              color: COLORS.textMuted,
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{ padding: 20 }}>
          <FormField label="Dipendente *">
            <select
              value={form.dipendente_id}
              onChange={(e) => setForm((f) => ({ ...f, dipendente_id: e.target.value }))}
              style={inputStyle}
              data-testid="select-dipendente"
              disabled={!!editing}
            >
              <option value="">— Seleziona —</option>
              {dipendenti.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.cognome} {d.nome}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Tipo acconto *">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: 8,
              }}
            >
              {TIPI.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, tipo: t.id }))}
                  style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    border: `2px solid ${form.tipo === t.id ? t.color : COLORS.border}`,
                    backgroundColor:
                      form.tipo === t.id ? `${t.color}15` : COLORS.card,
                    color: form.tipo === t.id ? t.color : COLORS.text,
                    fontSize: 13,
                    fontWeight: form.tipo === t.id ? 700 : 500,
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </FormField>

          {isTFR && (
            <div
              style={{
                padding: '10px 12px',
                backgroundColor: COLORS.warningLight,
                borderRadius: 8,
                fontSize: 12,
                color: COLORS.warning,
                marginBottom: SPACING.lg,
                display: 'flex',
                gap: 8,
              }}
            >
              <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>
                L'acconto TFR decrementa automaticamente il TFR accantonato del
                dipendente e registra un movimento contabile.
              </span>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: SPACING.md }}>
            <FormField label="Importo (€) *">
              <input
                type="number"
                value={form.importo}
                onChange={(e) => setForm((f) => ({ ...f, importo: e.target.value }))}
                step="0.01"
                min="0.01"
                placeholder="0,00"
                style={inputStyle}
                data-testid="input-importo"
              />
            </FormField>
            <FormField label="Data *">
              <input
                type="date"
                value={form.data}
                onChange={(e) => setForm((f) => ({ ...f, data: e.target.value }))}
                style={inputStyle}
              />
            </FormField>
          </div>

          <FormField label="Note">
            <textarea
              value={form.note}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              rows={3}
              placeholder="Modalità (bonifico/contanti), riferimenti, ecc."
              style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
            />
          </FormField>
        </div>

        <div
          style={{
            padding: '14px 20px',
            borderTop: `1px solid ${COLORS.border}`,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 10,
          }}
        >
          <button onClick={onClose} style={btnGhost}>
            Annulla
          </button>
          <button
            onClick={onSubmit}
            disabled={saving}
            style={{
              ...btnPrimary,
              opacity: saving ? 0.5 : 1,
              cursor: saving ? 'not-allowed' : 'pointer',
            }}
            data-testid="btn-salva-acconto"
          >
            {saving ? 'Salvo…' : editing ? 'Salva modifiche' : 'Crea acconto'}
          </button>
        </div>
      </div>
    </div>
  );
}

function FormField({ label, children }) {
  return (
    <div style={{ marginBottom: SPACING.lg }}>
      <label
        style={{
          display: 'block',
          fontSize: 10,
          fontWeight: 600,
          color: COLORS.textMuted,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          marginBottom: 6,
        }}
      >
        {label}
      </label>
      {children}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Styles
// ═══════════════════════════════════════════════════════════════════════
const btnPrimary = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  padding: '9px 18px',
  backgroundColor: COLORS.primary,
  color: '#fff',
  border: 'none',
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'background-color 0.15s',
};

const btnGhost = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '8px 14px',
  backgroundColor: 'transparent',
  color: COLORS.text,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
};

const thStyle = {
  padding: '10px 12px',
  fontSize: 10,
  fontWeight: 700,
  color: COLORS.textMuted,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  borderBottom: `1px solid ${COLORS.border}`,
  textAlign: 'center',
};

const tdStyle = {
  padding: '10px 12px',
  verticalAlign: 'middle',
};

const inputStyle = {
  width: '100%',
  padding: '9px 12px',
  fontSize: 13,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 8,
  outline: 'none',
  backgroundColor: COLORS.card,
  color: COLORS.text,
  boxSizing: 'border-box',
  fontFamily: 'inherit',
};

function iconBtn(color, bg) {
  return {
    padding: 6,
    backgroundColor: bg,
    color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  };
}
