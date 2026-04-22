/**
 * HRTurni.jsx — Gestione Turni
 *
 * Layout ispirato a dipendenti-cloud:
 *   1. Card tipi turno in griglia (nome, orario, colore, edit/delete on hover)
 *   2. Tabella pianificazione settimanale (dipendenti × giorni Lun..Dom) con select per assegnare
 *   3. Legenda in fondo
 *   4. Modal nuovo/modifica turno con name/orari/colore
 *
 * Design system Ceraldi: palette navy + oro, inline-styles via COLORS/SPACING.
 * Backend: /api/shifts/tipi, /api/shifts/assegnazioni.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Edit2, Trash2, X, Clock, Users } from 'lucide-react';
import api from '../../api';
import { COLORS, SPACING, useIsMobile } from '../../lib/utils';

const GIORNI = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];

// Palette colori suggeriti per i turni (navy + accenti Ceraldi)
const COLORI_TURNO = [
  COLORS.primary,      // navy #0f2744
  COLORS.primaryLight, // #1e3a5f
  COLORS.accent,       // oro #b8860b
  COLORS.success,      // verde
  COLORS.warning,      // arancio
  COLORS.info,         // blu
  COLORS.danger,       // rosso
  COLORS.purple,       // viola
];

const DEFAULT_FORM = {
  nome: '',
  orario_inizio: '08:00',
  orario_fine: '16:00',
  colore: COLORS.primary,
};

// Utility: inizialale per avatar
function getInitials(nome = '', cognome = '') {
  const n = (nome || '').trim();
  const c = (cognome || '').trim();
  if (n && c) return (n[0] + c[0]).toUpperCase();
  if (c) return c.substring(0, 2).toUpperCase();
  if (n) return n.substring(0, 2).toUpperCase();
  return '?';
}

// Lista di colori per avatar (stabili per indice)
const AVATAR_BG = [
  '#0f2744', '#1e3a5f', '#b8860b', '#15803d',
  '#1d4ed8', '#7c3aed', '#b45309', '#b91c1c',
];

// ═══════════════════════════════════════════════════════════════════════
// Componente
// ═══════════════════════════════════════════════════════════════════════

export default function HRTurni() {
  const isMobile = useIsMobile();

  const [dipendenti, setDipendenti] = useState([]);
  const [turni, setTurni] = useState([]);
  const [assegnazioni, setAssegnazioni] = useState({}); // key: `${dipId}_${giorno}` -> turno_id
  const [loading, setLoading] = useState(true);

  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  // ────── Data loading ──────
  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dipRes, turniRes, assRes] = await Promise.all([
        api.get('/api/dipendenti'),
        api.get('/api/shifts/tipi'),
        api.get('/api/shifts/assegnazioni'),
      ]);
      setDipendenti(Array.isArray(dipRes.data) ? dipRes.data : []);
      setTurni(Array.isArray(turniRes.data) ? turniRes.data : []);

      const assMap = {};
      (Array.isArray(assRes.data) ? assRes.data : []).forEach((a) => {
        assMap[`${a.dipendente_id}_${a.giorno}`] = a.turno_id;
      });
      setAssegnazioni(assMap);
    } catch (e) {
      console.error('[HRTurni] load error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ────── Handlers ──────
  const openNew = () => {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setShowModal(true);
  };

  const openEdit = (turno) => {
    setEditingId(turno.id);
    setForm({
      nome: turno.nome || '',
      orario_inizio: turno.orario_inizio || '08:00',
      orario_fine: turno.orario_fine || '16:00',
      colore: turno.colore || COLORS.primary,
    });
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingId(null);
    setForm(DEFAULT_FORM);
  };

  const submitTurno = async () => {
    if (!form.nome.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/api/shifts/tipi/${editingId}`, form);
      } else {
        await api.post('/api/shifts/tipi', form);
      }
      closeModal();
      await loadAll();
    } catch (e) {
      console.error('[HRTurni] submit turno error:', e);
      alert('Errore nel salvataggio del turno');
    } finally {
      setSaving(false);
    }
  };

  const deleteTurno = async (turno) => {
    if (!window.confirm(`Eliminare il turno "${turno.nome}"?`)) return;
    try {
      await api.delete(`/api/shifts/tipi/${turno.id}`);
      await loadAll();
    } catch (e) {
      console.error('[HRTurni] delete turno error:', e);
      alert('Errore nell\'eliminazione del turno');
    }
  };

  const assegnaTurno = async (dipId, giorno, turnoId) => {
    const key = `${dipId}_${giorno}`;
    // UI ottimistica
    setAssegnazioni((prev) => ({ ...prev, [key]: turnoId || null }));
    try {
      await api.post('/api/shifts/assegnazioni', {
        dipendente_id: dipId,
        giorno,
        turno_id: turnoId || null,
      });
    } catch (e) {
      console.error('[HRTurni] assegna error:', e);
      // rollback
      await loadAll();
    }
  };

  // ────── Derived ──────
  const dipendentiAttivi = useMemo(
    () => dipendenti.filter((d) => (d.stato || 'attivo') === 'attivo'),
    [dipendenti]
  );

  const turnoById = useCallback(
    (id) => turni.find((t) => t.id === id) || null,
    [turni]
  );

  // ────── KPI ──────
  const totAssegnazioni = Object.keys(assegnazioni).length;
  const copertoGg = useMemo(() => {
    const daysWithAny = new Set(Object.keys(assegnazioni).map((k) => k.split('_')[1]));
    return daysWithAny.size;
  }, [assegnazioni]);

  // ═══════════════════════════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════════════════════════

  return (
    <div style={{ padding: isMobile ? SPACING.lg : SPACING.xxl, minHeight: '100vh', backgroundColor: COLORS.bg }}>
      {/* HEADER */}
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
              fontSize: 28,
              fontWeight: 700,
              color: COLORS.text,
              margin: 0,
              letterSpacing: '-0.02em',
            }}
          >
            Gestione Turni
          </h1>
          <p style={{ fontSize: 14, color: COLORS.textMuted, margin: '4px 0 0' }}>
            Assegnazione turni settimanali — Ceraldi Group SRL
          </p>
        </div>
        <button
          onClick={openNew}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 18px',
            backgroundColor: COLORS.primary,
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'background-color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = COLORS.primaryLight)}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = COLORS.primary)}
          data-testid="nuovo-turno-btn"
        >
          <Plus size={18} /> Nuovo turno
        </button>
      </div>

      {/* KPI */}
      {!loading && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
            gap: SPACING.lg,
            marginBottom: SPACING.lg,
          }}
        >
          <KpiTurni
            icon={<Clock size={20} color={COLORS.primary} />}
            label="Tipi turno"
            value={turni.length.toString()}
            sub="definiti"
            accent={COLORS.primary}
          />
          <KpiTurni
            icon={<Users size={20} color={COLORS.accent} />}
            label="Dipendenti attivi"
            value={dipendentiAttivi.length.toString()}
            sub="coinvolti"
            accent={COLORS.accent}
          />
          <KpiTurni
            icon={<Clock size={20} color={COLORS.info} />}
            label="Assegnazioni"
            value={totAssegnazioni.toString()}
            sub="celle occupate"
            accent={COLORS.info}
          />
          <KpiTurni
            icon={<Users size={20} color={COLORS.success} />}
            label="Giorni coperti"
            value={`${copertoGg}/7`}
            sub="della settimana"
            accent={COLORS.success}
          />
        </div>
      )}

      {/* Help bar */}
      {!loading && turni.length > 0 && (
        <div
          style={{
            padding: '10px 14px',
            backgroundColor: COLORS.bgAlt,
            borderRadius: 8,
            fontSize: 12,
            color: COLORS.textMuted,
            marginBottom: SPACING.lg,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: COLORS.primary,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              padding: '2px 8px',
              borderRadius: 4,
              backgroundColor: COLORS.primarySoft,
            }}
          >
            Suggerimento
          </span>
          <span>
            Clicca una cella della tabella e scegli il turno dall'elenco. L'assegnazione si salva automaticamente.
          </span>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 48, color: COLORS.textMuted }}>
          Caricamento turni...
        </div>
      ) : (
        <>
          {/* CARDS TIPI TURNO */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(auto-fill, minmax(${isMobile ? '160px' : '220px'}, 1fr))`,
              gap: SPACING.lg,
              marginBottom: SPACING.xxl,
            }}
          >
            {turni.map((t) => (
              <TurnoCard
                key={t.id}
                turno={t}
                onEdit={() => openEdit(t)}
                onDelete={() => deleteTurno(t)}
              />
            ))}
            {turni.length === 0 && (
              <div
                style={{
                  gridColumn: '1/-1',
                  padding: 48,
                  textAlign: 'center',
                  color: COLORS.textMuted,
                  backgroundColor: COLORS.card,
                  border: `1px dashed ${COLORS.border}`,
                  borderRadius: 12,
                }}
              >
                Nessun turno definito. Clicca &ldquo;Nuovo turno&rdquo; per crearne uno.
              </div>
            )}
          </div>

          {/* TABELLA PIANIFICAZIONE SETTIMANALE */}
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
                padding: `${SPACING.lg}px ${SPACING.xl}px`,
                borderBottom: `1px solid ${COLORS.border}`,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: SPACING.md,
              }}
            >
              <h3
                style={{
                  fontSize: 16,
                  fontWeight: 600,
                  color: COLORS.text,
                  margin: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Users size={18} color={COLORS.primary} />
                Pianificazione Settimanale
              </h3>
              <p style={{ fontSize: 13, color: COLORS.textMuted, margin: 0 }}>
                Clicca su una cella per assegnare un turno
              </p>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  minWidth: 800,
                }}
              >
                <thead>
                  <tr style={{ backgroundColor: COLORS.bgAlt }}>
                    <th
                      style={{
                        ...thStyle,
                        minWidth: 220,
                        textAlign: 'left',
                        paddingLeft: SPACING.xl,
                      }}
                    >
                      Dipendente
                    </th>
                    {GIORNI.map((g) => (
                      <th key={g} style={{ ...thStyle, textAlign: 'center', minWidth: 110 }}>
                        {g}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dipendentiAttivi.map((dip, idx) => (
                    <tr key={dip.id} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                      <td style={{ padding: `${SPACING.md}px ${SPACING.xl}px` }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div
                            style={{
                              width: 32,
                              height: 32,
                              borderRadius: '50%',
                              backgroundColor: AVATAR_BG[idx % AVATAR_BG.length],
                              color: '#fff',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: 12,
                              fontWeight: 600,
                              flexShrink: 0,
                            }}
                          >
                            {getInitials(dip.nome, dip.cognome)}
                          </div>
                          <div style={{ minWidth: 0 }}>
                            <div
                              style={{
                                fontSize: 14,
                                fontWeight: 600,
                                color: COLORS.text,
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                              }}
                            >
                              {dip.cognome} {dip.nome}
                            </div>
                            {dip.ruolo && (
                              <div
                                style={{
                                  fontSize: 12,
                                  color: COLORS.textMuted,
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}
                              >
                                {dip.ruolo}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      {GIORNI.map((g, i) => {
                        const key = `${dip.id}_${g}`;
                        const turnoId = assegnazioni[key];
                        const turno = turnoId ? turnoById(turnoId) : null;
                        const isWeekend = i >= 5;
                        return (
                          <td key={g} style={{ padding: `${SPACING.sm}px ${SPACING.xs}px`, textAlign: 'center' }}>
                            <select
                              value={turno?.id || ''}
                              onChange={(e) => assegnaTurno(dip.id, g, e.target.value)}
                              style={{
                                width: '100%',
                                fontSize: 12,
                                fontWeight: turno ? 600 : 400,
                                padding: '6px 8px',
                                border: 'none',
                                borderRadius: 6,
                                cursor: 'pointer',
                                backgroundColor: turno
                                  ? `${turno.colore}20`
                                  : isWeekend
                                  ? COLORS.gray[100]
                                  : COLORS.bgAlt,
                                color: turno ? turno.colore : COLORS.textMuted,
                                outline: 'none',
                              }}
                              data-testid={`turno-${dip.id}-${g}`}
                            >
                              <option value="">{isWeekend ? 'Riposo' : '— —'}</option>
                              {turni.map((t) => (
                                <option key={t.id} value={t.id}>
                                  {t.nome}
                                </option>
                              ))}
                            </select>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {dipendentiAttivi.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}>
                        Nessun dipendente attivo.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* LEGENDA */}
          {turni.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: SPACING.xl,
                padding: SPACING.lg,
                backgroundColor: COLORS.card,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 12,
              }}
            >
              {turni.map((t) => (
                <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: 4,
                      backgroundColor: t.colore,
                    }}
                  />
                  <span style={{ fontSize: 13, color: COLORS.text }}>
                    <strong>{t.nome}</strong>{' '}
                    <span style={{ color: COLORS.textMuted }}>
                      ({t.orario_inizio}–{t.orario_fine})
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* MODAL */}
      {showModal && (
        <ModalNuovoTurno
          form={form}
          setForm={setForm}
          editing={!!editingId}
          saving={saving}
          onClose={closeModal}
          onSubmit={submitTurno}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════════════

function TurnoCard({ turno, onEdit, onDelete }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: 'relative',
        backgroundColor: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 12,
        padding: SPACING.lg,
        transition: 'box-shadow 0.15s, border-color 0.15s',
        boxShadow: hover ? '0 2px 8px rgba(15,39,68,0.08)' : 'none',
        borderColor: hover ? COLORS.borderDark : COLORS.border,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            backgroundColor: `${turno.colore}20`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Clock size={18} color={turno.colore} />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: COLORS.text,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {turno.nome}
          </div>
          <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 2 }}>
            {turno.orario_inizio} – {turno.orario_fine}
          </div>
        </div>
      </div>
      {hover && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            display: 'flex',
            gap: 4,
          }}
        >
          <button
            onClick={onEdit}
            title="Modifica"
            style={{
              padding: 6,
              backgroundColor: COLORS.infoLight,
              color: COLORS.info,
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            <Edit2 size={13} />
          </button>
          <button
            onClick={onDelete}
            title="Elimina"
            style={{
              padding: 6,
              backgroundColor: COLORS.dangerLight,
              color: COLORS.danger,
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            <Trash2 size={13} />
          </button>
        </div>
      )}
    </div>
  );
}

function ModalNuovoTurno({ form, setForm, editing, saving, onClose, onSubmit }) {
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
          maxWidth: 480,
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
        }}
      >
        {/* Header modale */}
        <div
          style={{
            padding: `${SPACING.lg}px ${SPACING.xl}px`,
            borderBottom: `1px solid ${COLORS.border}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <h3 style={{ fontSize: 17, fontWeight: 600, color: COLORS.text, margin: 0 }}>
            {editing ? 'Modifica turno' : 'Nuovo turno'}
          </h3>
          <button
            onClick={onClose}
            style={{
              padding: 6,
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

        {/* Body modale */}
        <div style={{ padding: SPACING.xl }}>
          <FormField label="Nome turno *">
            <input
              value={form.nome}
              onChange={(e) => setForm((f) => ({ ...f, nome: e.target.value }))}
              placeholder="Es: Mattina, Pomeriggio, Serale..."
              style={inputStyle}
              data-testid="input-nome-turno"
            />
          </FormField>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: SPACING.lg }}>
            <FormField label="Orario inizio">
              <input
                type="time"
                value={form.orario_inizio}
                onChange={(e) => setForm((f) => ({ ...f, orario_inizio: e.target.value }))}
                style={inputStyle}
              />
            </FormField>
            <FormField label="Orario fine">
              <input
                type="time"
                value={form.orario_fine}
                onChange={(e) => setForm((f) => ({ ...f, orario_fine: e.target.value }))}
                style={inputStyle}
              />
            </FormField>
          </div>

          <FormField label="Colore">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <input
                type="color"
                value={form.colore}
                onChange={(e) => setForm((f) => ({ ...f, colore: e.target.value }))}
                style={{
                  width: 48,
                  height: 40,
                  padding: 2,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              />
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {COLORI_TURNO.map((c) => (
                  <button
                    key={c}
                    onClick={() => setForm((f) => ({ ...f, colore: c }))}
                    title={c}
                    style={{
                      width: 30,
                      height: 30,
                      borderRadius: '50%',
                      backgroundColor: c,
                      border: form.colore === c ? `3px solid ${COLORS.text}` : '3px solid transparent',
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  />
                ))}
              </div>
            </div>
          </FormField>
        </div>

        {/* Footer modale */}
        <div
          style={{
            padding: `${SPACING.lg}px ${SPACING.xl}px`,
            borderTop: `1px solid ${COLORS.border}`,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: SPACING.md,
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '10px 18px',
              backgroundColor: 'transparent',
              color: COLORS.text,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Annulla
          </button>
          <button
            onClick={onSubmit}
            disabled={!form.nome.trim() || saving}
            style={{
              padding: '10px 18px',
              backgroundColor: COLORS.primary,
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: !form.nome.trim() || saving ? 'not-allowed' : 'pointer',
              opacity: !form.nome.trim() || saving ? 0.5 : 1,
            }}
            data-testid="salva-turno-btn"
          >
            {saving ? 'Salvo...' : editing ? 'Salva modifiche' : 'Crea turno'}
          </button>
        </div>
      </div>
    </div>
  );
}

function KpiTurni({ icon, label, value, sub, accent }) {
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

function FormField({ label, children }) {
  return (
    <div style={{ marginBottom: SPACING.lg }}>
      <label
        style={{
          display: 'block',
          fontSize: 11,
          fontWeight: 600,
          color: COLORS.textMuted,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
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

const thStyle = {
  padding: '12px 8px',
  fontSize: 11,
  fontWeight: 600,
  color: COLORS.textMuted,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  borderBottom: `1px solid ${COLORS.border}`,
};

const inputStyle = {
  width: '100%',
  padding: '10px 12px',
  fontSize: 14,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 8,
  outline: 'none',
  boxSizing: 'border-box',
  backgroundColor: COLORS.card,
  color: COLORS.text,
};
