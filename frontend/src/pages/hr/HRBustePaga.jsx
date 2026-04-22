/**
 * HRBustePaga.jsx — Riepilogo mensile buste paga dipendenti
 *
 * Layout stile prototipo Ceraldi (navy + oro):
 *   - Header con titolo e selettore competenza (YYYY-MM)
 *   - 4 KPI card: dipendenti, ore ordinarie, totale netto, acconti
 *   - Tabella buste paga del mese con: dipendente, ore, netto, acconti,
 *     differenza da pagare, azione elimina
 *
 * Endpoints:
 *   GET /api/buste-paga/competenze           lista mesi disponibili
 *   GET /api/buste-paga/riepilogo-mensile/{competenza}   riepilogo + buste
 *   DELETE /api/buste-paga/{competenza}/{nome}           elimina singola
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Users, Clock, Euro, AlertCircle, RefreshCw, Trash2, FileText,
} from 'lucide-react';
import api from '../../api';
import { COLORS, SPACING, useIsMobile } from '../../lib/utils';

// ═══════════════════════════════════════════════════════════════════════
// Costanti
// ═══════════════════════════════════════════════════════════════════════
const MESI = [
  'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
];

const AVATAR_COLORS = [
  '#0f2744', '#b8860b', '#15803d', '#1d4ed8',
  '#7c3aed', '#b45309', '#b91c1c', '#1e3a5f',
];

// ═══════════════════════════════════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════════════════════════════════
function formatEuro(v) {
  if (v == null || isNaN(v)) return '—';
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: 'EUR',
  }).format(v);
}

function formatOre(v) {
  if (v == null || isNaN(v)) return '—';
  return `${Number(v).toFixed(1)}h`;
}

function parseCompetenza(c) {
  // "2026-04" -> { anno: 2026, mese: 4, label: "Aprile 2026" }
  if (!c || typeof c !== 'string' || c.length < 7) return null;
  const [y, m] = c.split('-');
  const anno = parseInt(y, 10);
  const mese = parseInt(m, 10);
  if (!anno || !mese) return null;
  return { anno, mese, label: `${MESI[mese - 1]} ${anno}` };
}

function currentCompetenza() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function initialsFromName(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  if (parts[0]) return parts[0].substring(0, 2).toUpperCase();
  return '?';
}

// ═══════════════════════════════════════════════════════════════════════
// Componente
// ═══════════════════════════════════════════════════════════════════════
export default function HRBustePaga() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const { competenza: competenzaFromUrl } = useParams();

  const [competenze, setCompetenze] = useState([]);
  // Inizializzazione: se l'URL contiene /buste-paga/YYYY-MM e il formato è valido,
  // uso quello (supporto deep-link/bookmark). Altrimenti fallback a mese corrente.
  // (fix Codex P2 #2)
  const [competenza, setCompetenza] = useState(() => {
    const fromUrl = (competenzaFromUrl || '').trim();
    if (/^\d{4}-(0[1-9]|1[0-2])$/.test(fromUrl)) return fromUrl;
    return currentCompetenza();
  });
  const [riepilogo, setRiepilogo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingCompetenze, setLoadingCompetenze] = useState(true);

  // Quando il parametro URL cambia (es. utente clicca link o usa back/forward),
  // aggiorno lo stato interno di conseguenza.
  useEffect(() => {
    const fromUrl = (competenzaFromUrl || '').trim();
    if (/^\d{4}-(0[1-9]|1[0-2])$/.test(fromUrl) && fromUrl !== competenza) {
      setCompetenza(fromUrl);
    }
    // Intenzionalmente NON dipende da `competenza` per evitare loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [competenzaFromUrl]);

  // Quando l'utente cambia competenza via select, aggiorno anche l'URL
  // (così è bookmark-abile e torna indietro con il browser back).
  const setCompetenzaAndUrl = useCallback(
    (c) => {
      setCompetenza(c);
      navigate(`/buste-paga/${c}`, { replace: true });
    },
    [navigate]
  );

  // ────── Load competenze ──────
  // Solo fetch dell'elenco: NESSUNA auto-selezione qui dentro. L'auto-select
  // è fatto in un useEffect dedicato che dipende esplicitamente sia da
  // `competenze` che da `competenza`, così il linter è soddisfatto e non
  // abbiamo il bug Codex P2 #1 (la callback era stale).
  const loadCompetenze = useCallback(async () => {
    setLoadingCompetenze(true);
    try {
      const { data } = await api.get('/api/buste-paga/competenze');
      const list = Array.isArray(data?.competenze) ? data.competenze : [];
      setCompetenze(list);
    } catch (e) {
      console.error('[HRBustePaga] competenze error', e);
      setCompetenze([]);
    } finally {
      setLoadingCompetenze(false);
    }
  }, []);

  useEffect(() => {
    loadCompetenze();
  }, [loadCompetenze]);

  // Auto-select: se la competenza corrente NON è nell'elenco disponibile
  // (es. primo caricamento con mese corrente senza dati), cado sulla prima
  // disponibile. Eccezione: se l'URL ha una competenza esplicita, la lascio
  // anche se vuota — l'utente ha deep-linkato quel mese specifico.
  // Se la corrente è già valida, non tocco nulla (fix Codex P2 #1).
  useEffect(() => {
    if (competenze.length === 0) return;
    if (competenze.includes(competenza)) return;
    // Se l'URL ha una competenza esplicita valida, rispetto la sua scelta
    const fromUrl = (competenzaFromUrl || '').trim();
    if (/^\d{4}-(0[1-9]|1[0-2])$/.test(fromUrl)) return;
    // Nessuna preferenza esplicita dall'URL → fallback sulla più recente
    setCompetenzaAndUrl(competenze[0]);
  }, [competenze, competenza, competenzaFromUrl, setCompetenzaAndUrl]);

  // ────── Load riepilogo ──────
  const loadRiepilogo = useCallback(async (signal) => {
    if (!competenza) return;
    setLoading(true);
    try {
      const { data } = await api.get(
        `/api/buste-paga/riepilogo-mensile/${competenza}`,
        { signal }
      );
      if (signal?.aborted) return;
      setRiepilogo(data || null);
    } catch (e) {
      if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return;
      console.error('[HRBustePaga] riepilogo error', e);
      setRiepilogo(null);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [competenza]);

  useEffect(() => {
    // Race guard: cambio rapido competenza non deve sovrascrivere con risposta obsoleta
    const controller = new AbortController();
    loadRiepilogo(controller.signal);
    return () => controller.abort();
  }, [loadRiepilogo]);

  // ────── Handlers ──────
  const eliminaBusta = async (b) => {
    if (
      !window.confirm(
        `Eliminare la busta paga di ${b.nome} per ${parseCompetenza(competenza)?.label}?\n\nQuesta azione non può essere annullata.`
      )
    )
      return;
    try {
      await api.delete(`/api/buste-paga/${competenza}/${encodeURIComponent(b.nome)}`);
      await loadRiepilogo();
      await loadCompetenze();
    } catch (e) {
      console.error('[HRBustePaga] delete error', e);
      alert('Errore eliminazione: ' + (e.response?.data?.detail || e.message));
    }
  };

  // ────── Derived ──────
  const compLabel = useMemo(() => {
    const p = parseCompetenza(competenza);
    return p?.label || competenza;
  }, [competenza]);

  const buste = useMemo(
    () => (Array.isArray(riepilogo?.buste) ? riepilogo.buste : []),
    [riepilogo]
  );

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
              fontSize: 26,
              fontWeight: 700,
              color: COLORS.text,
              margin: 0,
              letterSpacing: '-0.02em',
            }}
          >
            Buste Paga Mensili
          </h1>
          <p style={{ fontSize: 13, color: COLORS.textMuted, margin: '4px 0 0' }}>
            Riepilogo mensile con netto, acconti, ore lavorate e differenza da pagare
          </p>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            value={competenza}
            onChange={(e) => setCompetenzaAndUrl(e.target.value)}
            style={{
              padding: '9px 14px',
              fontSize: 14,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              backgroundColor: COLORS.card,
              color: COLORS.text,
              cursor: 'pointer',
              fontWeight: 600,
              minWidth: 180,
            }}
            data-testid="select-competenza"
            disabled={loadingCompetenze}
          >
            {loadingCompetenze && (
              <option value={competenza}>Caricamento…</option>
            )}
            {!loadingCompetenze && competenze.length === 0 && (
              <option value={competenza}>{compLabel}</option>
            )}
            {competenze.map((c) => {
              const p = parseCompetenza(c);
              return (
                <option key={c} value={c}>
                  {p?.label || c}
                </option>
              );
            })}
          </select>
          <button
            onClick={loadRiepilogo}
            style={{
              padding: '9px 14px',
              backgroundColor: 'transparent',
              color: COLORS.text,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
            title="Aggiorna"
          >
            <RefreshCw
              size={14}
              style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
            />
            Aggiorna
          </button>
        </div>
      </div>

      {/* KPI */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
          gap: SPACING.lg,
          marginBottom: SPACING.xl,
        }}
      >
        <Kpi
          icon={<Users size={20} color={COLORS.primary} />}
          label="Dipendenti"
          value={(riepilogo?.dipendenti ?? 0).toString()}
          sub={compLabel}
          accent={COLORS.primary}
        />
        <Kpi
          icon={<Clock size={20} color={COLORS.accent} />}
          label="Ore lavorate"
          value={formatOre(riepilogo?.totale_ore ?? 0)}
          sub="ordinarie totali"
          accent={COLORS.accent}
        />
        <Kpi
          icon={<Euro size={20} color={COLORS.success} />}
          label="Netto totale"
          value={formatEuro(riepilogo?.totale_netto ?? 0)}
          sub="da cedolini"
          accent={COLORS.success}
        />
        <Kpi
          icon={
            <AlertCircle
              size={20}
              color={(riepilogo?.totale_differenza ?? 0) > 0 ? COLORS.warning : COLORS.info}
            />
          }
          label="Differenza"
          value={formatEuro(riepilogo?.totale_differenza ?? 0)}
          sub={`Acconti: ${formatEuro(riepilogo?.totale_acconti ?? 0)}`}
          accent={(riepilogo?.totale_differenza ?? 0) > 0 ? COLORS.warning : COLORS.info}
        />
      </div>

      {/* Tabella buste */}
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
            flexWrap: 'wrap',
            gap: 10,
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
            <FileText size={16} color={COLORS.primary} />
            Buste paga — {compLabel} ({buste.length})
          </h3>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ backgroundColor: COLORS.bgAlt }}>
                <th style={{ ...thStyle, textAlign: 'left', paddingLeft: SPACING.lg }}>
                  Dipendente
                </th>
                <th style={thStyle}>Ore ordinarie</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Netto</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Acconti</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Differenza</th>
                <th style={{ ...thStyle, width: 80 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td
                    colSpan={6}
                    style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}
                  >
                    Caricamento…
                  </td>
                </tr>
              )}
              {!loading && buste.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}
                  >
                    <FileText size={48} style={{ marginBottom: 12, opacity: 0.3 }} />
                    <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
                      Nessuna busta paga per {compLabel}
                    </div>
                    <div style={{ fontSize: 12 }}>
                      Le buste paga vengono create importando i cedolini in formato PDF
                      dalla pagina Cedolini.
                    </div>
                  </td>
                </tr>
              )}
              {!loading &&
                buste.map((b, idx) => {
                  const diff = parseFloat(b.differenza) || 0;
                  const dipColor = AVATAR_COLORS[idx % AVATAR_COLORS.length];
                  return (
                    <tr
                      key={`${b.competenza}-${b.nome}-${idx}`}
                      style={{ borderTop: `1px solid ${COLORS.border}` }}
                    >
                      <td style={{ ...tdStyle, paddingLeft: SPACING.lg }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div
                            style={{
                              width: 28,
                              height: 28,
                              borderRadius: '50%',
                              backgroundColor: dipColor,
                              color: '#fff',
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: 11,
                              fontWeight: 700,
                              flexShrink: 0,
                            }}
                          >
                            {initialsFromName(b.nome)}
                          </div>
                          <span style={{ fontWeight: 500 }}>{b.nome || '—'}</span>
                        </div>
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          textAlign: 'center',
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {formatOre(b.ore_ordinarie)}
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
                        {formatEuro(b.netto)}
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          textAlign: 'right',
                          color: COLORS.textMuted,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {formatEuro(b.acconto)}
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          textAlign: 'right',
                          fontWeight: 700,
                          color: diff > 0.01 ? COLORS.warning : COLORS.success,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {formatEuro(b.differenza)}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <button
                          onClick={() => eliminaBusta(b)}
                          style={{
                            padding: 6,
                            backgroundColor: COLORS.dangerLight,
                            color: COLORS.danger,
                            border: 'none',
                            borderRadius: 6,
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                          title="Elimina"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
            {!loading && buste.length > 0 && (
              <tfoot>
                <tr
                  style={{
                    backgroundColor: COLORS.bgAlt,
                    borderTop: `2px solid ${COLORS.borderDark}`,
                  }}
                >
                  <td
                    style={{
                      ...tdStyle,
                      paddingLeft: SPACING.lg,
                      fontSize: 11,
                      fontWeight: 700,
                      color: COLORS.textMuted,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                    }}
                  >
                    Totale
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      textAlign: 'center',
                      fontWeight: 700,
                      fontSize: 14,
                      color: COLORS.text,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {formatOre(riepilogo?.totale_ore ?? 0)}
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
                    {formatEuro(riepilogo?.totale_netto ?? 0)}
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      textAlign: 'right',
                      fontWeight: 700,
                      fontSize: 14,
                      color: COLORS.textMuted,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {formatEuro(riepilogo?.totale_acconti ?? 0)}
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      textAlign: 'right',
                      fontWeight: 700,
                      fontSize: 15,
                      color:
                        (riepilogo?.totale_differenza ?? 0) > 0
                          ? COLORS.warning
                          : COLORS.success,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {formatEuro(riepilogo?.totale_differenza ?? 0)}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════════════
function Kpi({ icon, label, value, sub, accent }) {
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

// ═══════════════════════════════════════════════════════════════════════
// Styles
// ═══════════════════════════════════════════════════════════════════════
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
