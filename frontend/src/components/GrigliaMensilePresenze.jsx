/**
 * GrigliaMensilePresenze.jsx — Griglia mensile multi-select per inserimento
 * giustificativi di massa.
 *
 * Layout: dipendenti (righe) × giorni del mese (colonne).
 * Selezione: click, shift+click, ctrl/cmd+click, drag, checkbox riga,
 *            header colonna giorno, "seleziona tutto".
 * Applicazione: modale con riuso endpoint POST /api/attendance/batch-insert.
 *
 * Design system Ceraldi (inline-style, COLORS/SPACING, palette navy+oro).
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, X } from 'lucide-react';
import api from '../api';
import { COLORS, SPACING } from '../lib/utils';

// ═══════════════════════════════════════════════════════════════════════
// Costanti
// ═══════════════════════════════════════════════════════════════════════
const DOW = ['D', 'L', 'M', 'M', 'G', 'V', 'S']; // dom=0
const MESI = [
  'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
];

// Palette avatar (deterministica per indice)
const AVATAR_COLORS = [
  '#0f2744', '#b8860b', '#15803d', '#1d4ed8',
  '#7c3aed', '#b45309', '#b91c1c', '#1e3a5f',
];

// ═══════════════════════════════════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════════════════════════════════
function daysInMonth(y, m) {
  return new Date(y, m + 1, 0).getDate();
}
function dateStr(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}
function keyOf(empId, ds) {
  return `${empId}_${ds}`;
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
// Componente principale
// ═══════════════════════════════════════════════════════════════════════
export default function GrigliaMensilePresenze({ dipendenti = [], onSaved }) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-indexed

  const [tipologie, setTipologie] = useState([]);
  const [presenzeMap, setPresenzeMap] = useState({}); // key -> { stato, ore, ... }
  const [selection, setSelection] = useState(() => new Set());
  const [anchor, setAnchor] = useState(null); // { empIdx, dayIdx }
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  // Drag state (ref per evitare re-render continuo)
  const dragRef = useRef({ start: null, isDragging: false, additive: false });
  const [dragPreview, setDragPreview] = useState(null); // { a, b } per highlight dashed

  const days = daysInMonth(year, month);
  const dipendentiAttivi = useMemo(
    () => dipendenti.filter((d) => (d.stato || d.status || 'attivo') !== 'cessato'),
    [dipendenti]
  );

  // ───── Load tipologie (1x) ─────
  useEffect(() => {
    api
      .get('/api/attendance/tipologie-giustificativi')
      .then((r) => setTipologie(r.data?.tipologie || []))
      .catch(() => setTipologie([]));
  }, []);

  // ───── Load presenze mese ─────
  const loadPresenze = useCallback(async (signal) => {
    if (dipendentiAttivi.length === 0) return;
    setLoading(true);
    try {
      // Provo prima il riepilogo mensile unificato
      const { data } = await api.get('/api/attendance/month-grid', {
        params: { anno: year, mese: month + 1 },
        signal,
      });
      if (signal?.aborted) return;
      const map = {};
      (data?.celle || []).forEach((c) => {
        if (c.stato && c.stato !== 'P') {
          map[keyOf(c.employee_id, c.data)] = {
            stato: c.stato,
            ore: c.ore,
            protocollo: c.protocollo,
            note: c.note,
          };
        }
      });
      setPresenzeMap(map);
    } catch (e) {
      if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return;
      // Fallback silenzioso: se l'endpoint non esiste mostro griglia vuota
      setPresenzeMap({});
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [dipendentiAttivi.length, year, month]);

  useEffect(() => {
    // Race guard: cambio rapido mese non deve sovrascrivere con risposta obsoleta
    const controller = new AbortController();
    loadPresenze(controller.signal);
    setSelection(new Set());
    setAnchor(null);
    return () => controller.abort();
  }, [loadPresenze]);

  // ═══════════════════════════════════════════════════════════════════════
  // Selezione: utility
  // ═══════════════════════════════════════════════════════════════════════
  const getRectKeys = useCallback(
    (a, b) => {
      const e1 = Math.min(a.empIdx, b.empIdx);
      const e2 = Math.max(a.empIdx, b.empIdx);
      const d1 = Math.min(a.dayIdx, b.dayIdx);
      const d2 = Math.max(a.dayIdx, b.dayIdx);
      const keys = [];
      for (let ei = e1; ei <= e2; ei++) {
        for (let di = d1; di <= d2; di++) {
          keys.push(keyOf(dipendentiAttivi[ei].id, dateStr(year, month, di + 1)));
        }
      }
      return keys;
    },
    [dipendentiAttivi, year, month]
  );

  // ═══════════════════════════════════════════════════════════════════════
  // Mouse handlers
  // ═══════════════════════════════════════════════════════════════════════
  const onCellMouseDown = (e, empIdx, dayIdx) => {
    if (e.button !== 0) return;
    dragRef.current = {
      start: { empIdx, dayIdx },
      isDragging: false,
      additive: e.ctrlKey || e.metaKey,
    };
  };

  const onCellMouseEnter = (e, empIdx, dayIdx) => {
    if (!dragRef.current.start) return;
    dragRef.current.isDragging = true;
    setDragPreview({ a: dragRef.current.start, b: { empIdx, dayIdx } });
  };

  useEffect(() => {
    const onUp = () => {
      const { start, isDragging, additive } = dragRef.current;
      if (start && isDragging && dragPreview) {
        const keys = getRectKeys(dragPreview.a, dragPreview.b);
        setSelection((prev) => {
          const next = additive ? new Set(prev) : new Set();
          keys.forEach((k) => next.add(k));
          return next;
        });
        setAnchor(dragPreview.b);
      }
      dragRef.current = { start: null, isDragging: false, additive: false };
      setDragPreview(null);
    };
    window.addEventListener('mouseup', onUp);
    return () => window.removeEventListener('mouseup', onUp);
  }, [dragPreview, getRectKeys]);

  const onCellClick = (e, empIdx, dayIdx) => {
    // Ignoro il click se è stato un drag (già gestito su mouseup)
    if (dragRef.current.isDragging) return;
    const k = keyOf(dipendentiAttivi[empIdx].id, dateStr(year, month, dayIdx + 1));
    const info = { empIdx, dayIdx };

    if (e.shiftKey && anchor) {
      const keys = getRectKeys(anchor, info);
      setSelection((prev) => {
        const next = new Set(prev);
        keys.forEach((x) => next.add(x));
        return next;
      });
    } else if (e.ctrlKey || e.metaKey) {
      setSelection((prev) => {
        const next = new Set(prev);
        if (next.has(k)) next.delete(k);
        else next.add(k);
        return next;
      });
      setAnchor(info);
    } else {
      setSelection((prev) => {
        if (prev.size === 1 && prev.has(k)) return new Set();
        return new Set([k]);
      });
      setAnchor(info);
    }
  };

  // ═══════════════════════════════════════════════════════════════════════
  // Selezioni rapide
  // ═══════════════════════════════════════════════════════════════════════
  const selectDayColumn = (day, event) => {
    const ds = dateStr(year, month, day);
    const additive = event?.ctrlKey || event?.metaKey;
    setSelection((prev) => {
      const next = additive ? new Set(prev) : new Set();
      const allSel = dipendentiAttivi.every((d) => prev.has(keyOf(d.id, ds)));
      if (allSel && !additive) {
        dipendentiAttivi.forEach((d) => next.delete(keyOf(d.id, ds)));
      } else {
        dipendentiAttivi.forEach((d) => next.add(keyOf(d.id, ds)));
      }
      return next;
    });
  };

  const toggleEmployeeRow = (empId, checked) => {
    setSelection((prev) => {
      const next = new Set(prev);
      for (let d = 1; d <= days; d++) {
        const k = keyOf(empId, dateStr(year, month, d));
        if (checked) next.add(k);
        else next.delete(k);
      }
      return next;
    });
  };

  const toggleSelectAll = (checked) => {
    if (!checked) {
      setSelection(new Set());
      return;
    }
    const next = new Set();
    dipendentiAttivi.forEach((dip) => {
      for (let d = 1; d <= days; d++) {
        next.add(keyOf(dip.id, dateStr(year, month, d)));
      }
    });
    setSelection(next);
  };

  const clearSelection = () => {
    setSelection(new Set());
    setAnchor(null);
  };

  // ═══════════════════════════════════════════════════════════════════════
  // Month nav
  // ═══════════════════════════════════════════════════════════════════════
  const changeMonth = (delta) => {
    let m = month + delta;
    let y = year;
    if (m < 0) { m = 11; y -= 1; }
    if (m > 11) { m = 0; y += 1; }
    setMonth(m);
    setYear(y);
    setSelection(new Set());
    setAnchor(null);
  };

  // ═══════════════════════════════════════════════════════════════════════
  // Apply modal (richiama /api/attendance/batch-insert)
  // ═══════════════════════════════════════════════════════════════════════
  const openModal = () => { if (selection.size > 0) setModalOpen(true); };
  const closeModal = () => setModalOpen(false);

  const applyGiustificativo = async (payload) => {
    // Raggruppo selection per dipendente (employee_ids → giorni)
    const byEmp = {};
    [...selection].forEach((k) => {
      const idx = k.indexOf('_');
      const empId = k.slice(0, idx);
      const date = k.slice(idx + 1);
      (byEmp[empId] ||= []).push(date);
    });

    const errors = [];
    let okCount = 0;

    for (const [empId, giorni] of Object.entries(byEmp)) {
      try {
        await api.post('/api/attendance/batch-insert', {
          employee_ids: [empId],
          giorni,
          stato: payload.stato,
          ore: payload.ore,
          protocollo: payload.protocollo || null,
          note: payload.note || null,
        });
        okCount++;
      } catch (err) {
        const dip = dipendenti.find((d) => d.id === empId);
        errors.push(`${dip?.cognome || '?'}: ${err.response?.data?.detail || err.message}`);
      }
    }

    closeModal();
    clearSelection();
    await loadPresenze();
    if (onSaved) onSaved();

    if (errors.length > 0) {
      alert(`Alcuni dipendenti non sono stati aggiornati:\n\n${errors.join('\n')}`);
    }
  };

  // ═══════════════════════════════════════════════════════════════════════
  // Derived
  // ═══════════════════════════════════════════════════════════════════════
  const isRowFullySelected = (empId) => {
    for (let d = 1; d <= days; d++) {
      if (!selection.has(keyOf(empId, dateStr(year, month, d)))) return false;
    }
    return true;
  };

  const allSelected =
    dipendentiAttivi.length > 0 &&
    dipendentiAttivi.every((dip) => isRowFullySelected(dip.id));

  const previewKeys = useMemo(() => {
    if (!dragPreview) return null;
    return new Set(getRectKeys(dragPreview.a, dragPreview.b));
  }, [dragPreview, getRectKeys]);

  const selStats = useMemo(() => {
    if (selection.size === 0) return null;
    const emps = new Set();
    const giorni = new Set();
    selection.forEach((k) => {
      const idx = k.indexOf('_');
      emps.add(k.slice(0, idx));
      giorni.add(k.slice(idx + 1));
    });
    return { celle: selection.size, dipendenti: emps.size, giorni: giorni.size };
  }, [selection]);

  // Legenda colori da tipologie (prime 6 più comuni)
  const legendCodes = ['FE', 'RL', 'MA', 'PE', 'L1', 'AI'];

  // ═══════════════════════════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════════════════════════
  return (
    <div style={{ userSelect: 'none' }}>
      {/* Toolbar mese + legenda */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
          padding: 12,
          backgroundColor: COLORS.card,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 10,
          marginBottom: 12,
        }}
      >
        <button onClick={() => changeMonth(-1)} style={navBtnStyle} aria-label="Mese precedente">
          <ChevronLeft size={16} />
        </button>
        <div
          style={{
            fontSize: 16,
            fontWeight: 600,
            color: COLORS.text,
            minWidth: 180,
            textAlign: 'center',
          }}
        >
          {MESI[month]} {year}
        </div>
        <button onClick={() => changeMonth(1)} style={navBtnStyle} aria-label="Mese successivo">
          <ChevronRight size={16} />
        </button>

        <div style={{ flex: 1 }} />

        <div
          style={{
            display: 'flex',
            gap: 12,
            flexWrap: 'wrap',
            alignItems: 'center',
            fontSize: 11,
            color: COLORS.textMuted,
          }}
        >
          {legendCodes.map((code) => {
            const t = tipologie.find((x) => x.codice === code);
            if (!t) return null;
            return (
              <span
                key={code}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
              >
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 3,
                    backgroundColor: lightenColor(t.colore),
                    display: 'inline-block',
                  }}
                />
                <strong style={{ color: COLORS.text }}>{code}</strong> {t.nome}
              </span>
            );
          })}
        </div>
      </div>

      {/* Help bar */}
      <div
        style={{
          display: 'flex',
          gap: 16,
          padding: '8px 14px',
          backgroundColor: COLORS.bgAlt,
          borderRadius: 8,
          fontSize: 11,
          color: COLORS.textMuted,
          marginBottom: 10,
          flexWrap: 'wrap',
        }}
      >
        <span><Kbd>Click</Kbd> singolo</span>
        <span><Kbd>Shift</Kbd> + Click per range rettangolare</span>
        <span><Kbd>Ctrl</Kbd>/<Kbd>⌘</Kbd> + Click aggiunge/toglie</span>
        <span><Kbd>Trascina</Kbd> per selezionare area</span>
        <span>Click su <strong>checkbox</strong> o <strong>header giorno</strong></span>
      </div>

      {/* Status bar */}
      {selStats ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            padding: '10px 16px',
            background: `${COLORS.primary}`,
            color: '#fff',
            borderRadius: 10,
            marginBottom: 10,
            fontSize: 13,
            fontWeight: 500,
            flexWrap: 'wrap',
          }}
        >
          <span>
            Selezionate{' '}
            <strong style={{ color: '#fcd34d' }}>{selStats.celle}</strong> celle —{' '}
            <strong style={{ color: '#fcd34d' }}>{selStats.dipendenti}</strong> dipendenti ×{' '}
            <strong style={{ color: '#fcd34d' }}>{selStats.giorni}</strong> giorni
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={openModal}
            style={{
              padding: '6px 14px',
              backgroundColor: COLORS.accent,
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
            data-testid="btn-applica-giustificativo"
          >
            Applica giustificativo →
          </button>
          <button
            onClick={clearSelection}
            style={{
              padding: '6px 12px',
              backgroundColor: 'transparent',
              color: '#fff',
              border: '1px solid rgba(255,255,255,0.3)',
              borderRadius: 6,
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            Pulisci
          </button>
        </div>
      ) : (
        <div
          style={{
            padding: '10px 14px',
            backgroundColor: COLORS.bgAlt,
            border: `1px dashed ${COLORS.border}`,
            borderRadius: 10,
            marginBottom: 10,
            fontSize: 13,
            color: COLORS.textMuted,
          }}
        >
          Nessuna cella selezionata — clicca, trascina, o usa checkbox/header per iniziare.
        </div>
      )}

      {/* Griglia */}
      <div
        style={{
          backgroundColor: COLORS.card,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 12,
          overflow: 'auto',
          maxHeight: 'calc(100vh - 360px)',
          position: 'relative',
        }}
      >
        {loading && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(255,255,255,0.8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10,
              fontSize: 13,
              color: COLORS.textMuted,
            }}
          >
            Caricamento…
          </div>
        )}

        <table
          style={{
            borderCollapse: 'separate',
            borderSpacing: 0,
            width: 'max-content',
            minWidth: '100%',
            fontSize: 12,
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  position: 'sticky',
                  top: 0,
                  left: 0,
                  zIndex: 6,
                  backgroundColor: COLORS.bgAlt,
                  minWidth: 220,
                  padding: '8px 12px',
                  textAlign: 'left',
                  borderBottom: `1px solid ${COLORS.border}`,
                  borderRight: `2px solid ${COLORS.borderDark}`,
                }}
              >
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    fontSize: 11,
                    fontWeight: 600,
                    color: COLORS.text,
                    cursor: 'pointer',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) => toggleSelectAll(e.target.checked)}
                  />
                  Dipendente ({dipendentiAttivi.length})
                </label>
              </th>
              {Array.from({ length: days }, (_, i) => i + 1).map((d) => {
                const dt = new Date(year, month, d);
                const dow = dt.getDay();
                const isWeekend = dow === 0 || dow === 6;
                return (
                  <th
                    key={d}
                    onClick={(e) => selectDayColumn(d, e)}
                    title={`Seleziona tutti per giorno ${d}`}
                    style={{
                      position: 'sticky',
                      top: 0,
                      zIndex: 5,
                      backgroundColor: isWeekend ? '#fef7f7' : COLORS.bgAlt,
                      padding: '6px 4px',
                      textAlign: 'center',
                      minWidth: 36,
                      borderBottom: `1px solid ${COLORS.border}`,
                      borderRight: `1px solid ${COLORS.border}`,
                      cursor: 'pointer',
                      color: isWeekend ? COLORS.danger : COLORS.textMuted,
                      fontWeight: 600,
                      fontSize: 10,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                    }}
                  >
                    <div style={{ fontSize: 9, letterSpacing: '0.08em' }}>{DOW[dow]}</div>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: isWeekend ? COLORS.danger : COLORS.text,
                        marginTop: 1,
                      }}
                    >
                      {d}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {dipendentiAttivi.map((dip, empIdx) => {
              const rowSel = isRowFullySelected(dip.id);
              return (
                <tr key={dip.id}>
                  <td
                    style={{
                      position: 'sticky',
                      left: 0,
                      zIndex: 4,
                      backgroundColor: rowSel ? COLORS.primarySoft : COLORS.card,
                      minWidth: 220,
                      padding: '8px 12px',
                      textAlign: 'left',
                      borderRight: `2px solid ${COLORS.borderDark}`,
                      borderBottom: `1px solid ${COLORS.border}`,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input
                        type="checkbox"
                        checked={rowSel}
                        onChange={(e) => toggleEmployeeRow(dip.id, e.target.checked)}
                        onClick={(e) => e.stopPropagation()}
                        style={{ cursor: 'pointer' }}
                      />
                      <div
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: '50%',
                          backgroundColor: AVATAR_COLORS[empIdx % AVATAR_COLORS.length],
                          color: '#fff',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: 11,
                          fontWeight: 700,
                          flexShrink: 0,
                        }}
                      >
                        {initials(dip.nome, dip.cognome)}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 600,
                            color: COLORS.text,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {dip.cognome} {dip.nome}
                        </div>
                        {(dip.ruolo || dip.mansione) && (
                          <div
                            style={{
                              fontSize: 11,
                              color: COLORS.textMuted,
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}
                          >
                            {dip.ruolo || dip.mansione}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  {Array.from({ length: days }, (_, i) => i + 1).map((d) => {
                    const dayIdx = d - 1;
                    const dt = new Date(year, month, d);
                    const dow = dt.getDay();
                    const isWeekend = dow === 0 || dow === 6;
                    const ds = dateStr(year, month, d);
                    const k = keyOf(dip.id, ds);
                    const sel = selection.has(k);
                    const preset = presenzeMap[k];
                    const inPreview = previewKeys?.has(k);
                    const tip = preset
                      ? tipologie.find((t) => t.codice === preset.stato)
                      : null;

                    let bg = COLORS.card;
                    if (isWeekend) bg = '#fafbfc';
                    if (preset && !sel) bg = lightenColor(tip?.colore || COLORS.gray[400]);
                    if (sel) bg = COLORS.primary;

                    return (
                      <td
                        key={d}
                        onMouseDown={(e) => onCellMouseDown(e, empIdx, dayIdx)}
                        onMouseEnter={(e) => onCellMouseEnter(e, empIdx, dayIdx)}
                        onClick={(e) => onCellClick(e, empIdx, dayIdx)}
                        style={{
                          minWidth: 36,
                          height: 38,
                          textAlign: 'center',
                          verticalAlign: 'middle',
                          cursor: 'pointer',
                          backgroundColor: bg,
                          color: sel ? '#fff' : tip?.colore || COLORS.textSubtle,
                          fontSize: sel ? 13 : 10,
                          fontWeight: 700,
                          borderRight: `1px solid ${COLORS.border}`,
                          borderBottom: `1px solid ${COLORS.border}`,
                          boxShadow: sel
                            ? `inset 0 0 0 2px ${COLORS.accent}`
                            : inPreview
                            ? `inset 0 0 0 2px ${COLORS.accentLight}`
                            : 'none',
                          transition: 'background-color 0.05s',
                        }}
                      >
                        {sel ? (
                          <Check size={14} />
                        ) : preset ? (
                          preset.stato
                        ) : (
                          ''
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {dipendentiAttivi.length === 0 && (
              <tr>
                <td
                  colSpan={days + 1}
                  style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}
                >
                  Nessun dipendente attivo.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modale Apply */}
      {modalOpen && (
        <ApplyModal
          selection={selection}
          dipendenti={dipendentiAttivi}
          tipologie={tipologie}
          onClose={closeModal}
          onApply={applyGiustificativo}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Modale apply
// ═══════════════════════════════════════════════════════════════════════
function ApplyModal({ selection, dipendenti, tipologie, onClose, onApply }) {
  const [stato, setStato] = useState('FE');
  const [ore, setOre] = useState(8);
  const [protocollo, setProtocollo] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  const tip = tipologie.find((t) => t.codice === stato);
  const protocolloObbligatorio = tip?.protocollo_obbligatorio;

  // Preview raggruppato
  const preview = useMemo(() => {
    const byEmp = {};
    [...selection].forEach((k) => {
      const idx = k.indexOf('_');
      const empId = k.slice(0, idx);
      const date = k.slice(idx + 1);
      (byEmp[empId] ||= []).push(date);
    });
    return Object.entries(byEmp).map(([empId, dates]) => {
      const d = dipendenti.find((x) => x.id === empId);
      dates.sort();
      return {
        empId,
        label: d ? `${d.cognome} ${d.nome}` : empId,
        count: dates.length,
        dates,
      };
    });
  }, [selection, dipendenti]);

  // Auto-ore su cambio tipologia
  useEffect(() => {
    if (tip?.ore_default) setOre(tip.ore_default);
  }, [stato, tip?.ore_default]);

  const submit = async () => {
    if (protocolloObbligatorio && !protocollo.trim()) {
      alert(`Protocollo obbligatorio per ${tip.nome}`);
      return;
    }
    setSaving(true);
    try {
      await onApply({
        stato,
        ore: parseFloat(ore) || 8,
        protocollo: protocollo.trim(),
        note: note.trim(),
      });
    } finally {
      setSaving(false);
    }
  };

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
          maxWidth: 540,
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
            Applica giustificativo di massa
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
          <Field label="Selezione corrente">
            <div
              style={{
                padding: '10px 12px',
                backgroundColor: COLORS.bgAlt,
                borderRadius: 8,
                fontSize: 12,
                color: COLORS.textMuted,
                maxHeight: 140,
                overflowY: 'auto',
              }}
            >
              {preview.map((p) => (
                <div key={p.empId} style={{ marginBottom: 4 }}>
                  <strong style={{ color: COLORS.text }}>{p.label}</strong>: {p.count} giorni
                  {p.count <= 3
                    ? ` (${p.dates.map((d) => d.slice(-2)).join(', ')})`
                    : ` (${p.dates[0].slice(-2)}…${p.dates[p.count - 1].slice(-2)})`}
                </div>
              ))}
            </div>
          </Field>

          <Field label="Tipo giustificativo">
            <select value={stato} onChange={(e) => setStato(e.target.value)} style={inputStyle}>
              {tipologie.map((t) => (
                <option key={t.codice} value={t.codice}>
                  {t.codice} — {t.nome}
                  {t.protocollo_obbligatorio ? ' (protocollo obbligatorio)' : ''}
                </option>
              ))}
            </select>
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 16 }}>
            <Field label="Ore per giorno">
              <input
                type="number"
                value={ore}
                onChange={(e) => setOre(e.target.value)}
                min="0"
                max="24"
                step="0.5"
                style={inputStyle}
              />
            </Field>
            <Field
              label={
                protocolloObbligatorio
                  ? 'Protocollo (obbligatorio)'
                  : 'Protocollo (opzionale)'
              }
            >
              <input
                type="text"
                value={protocollo}
                onChange={(e) => setProtocollo(e.target.value)}
                placeholder="Es. INPS/2026/12345"
                style={inputStyle}
              />
            </Field>
          </div>

          <Field label="Note">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Note aggiuntive"
              style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
            />
          </Field>
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
          <button
            onClick={onClose}
            style={{
              padding: '9px 16px',
              backgroundColor: 'transparent',
              color: COLORS.text,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Annulla
          </button>
          <button
            onClick={submit}
            disabled={saving}
            style={{
              padding: '9px 18px',
              backgroundColor: COLORS.primary,
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              cursor: saving ? 'not-allowed' : 'pointer',
              opacity: saving ? 0.5 : 1,
            }}
          >
            {saving ? 'Applicando…' : 'Applica'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Piccoli helper visivi
// ═══════════════════════════════════════════════════════════════════════
function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
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

function Kbd({ children }) {
  return (
    <kbd
      style={{
        display: 'inline-block',
        padding: '1px 6px',
        border: `1px solid ${COLORS.borderDark}`,
        borderRadius: 4,
        backgroundColor: '#fff',
        fontSize: 10,
        fontFamily: 'inherit',
        boxShadow: `0 1px 0 ${COLORS.borderDark}`,
      }}
    >
      {children}
    </kbd>
  );
}

/**
 * Ritorna una variante "tinta chiara" (20% opacity) del colore passato,
 * compatibile con qualsiasi formato esadecimale a 6 caratteri.
 */
function lightenColor(hex) {
  if (!hex || !hex.startsWith('#') || hex.length !== 7) return '#e2e8f0';
  return `${hex}20`; // aggiungi alpha 12% in notazione #RRGGBBAA
}

const navBtnStyle = {
  width: 32,
  height: 32,
  borderRadius: 8,
  border: `1px solid ${COLORS.border}`,
  backgroundColor: COLORS.card,
  color: COLORS.text,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
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
