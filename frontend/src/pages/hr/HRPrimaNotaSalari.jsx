/**
 * HRPrimaNotaSalari.jsx — Vista collettiva Prima Nota Salari (Task 5)
 *
 * Mostra la matrice di tutti i dipendenti × tutti i mesi dell'anno con saldo
 * DARE/AVERE per ogni cella, oppure un singolo mese con dettaglio.
 *
 * Backend: /api/prima-nota-salari-v2/collettiva?anno=YYYY[&mese=N]
 *
 * Layout stile prototipo Ceraldi (navy + oro):
 *   - 4 KPI in alto (totale dare, totale avere, saldo, dipendenti con saldo aperto)
 *   - Selettore anno + mese (mese opzionale per drill-down)
 *   - Tabella dipendenti: una riga per ognuno, 12 celle mese o 1 cella mese
 *   - Click sulla riga → vai al fascicolo del dipendente, tab Prima Nota
 */
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp, FileText, CreditCard, Check, AlertCircle, RefreshCw,
} from 'lucide-react';
import api from '../../api';
import { COLORS, useIsMobile } from '../../lib/utils';

const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i);
const MESI = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];
const MESI_NOMI = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];

const STATO_COLORS = {
  quadrato:     { bg: '#dcfce7', text: '#15803d', label: '✓' },
  in_pagamento: { bg: '#fef3c7', text: '#92400e', label: '⏳' },
  anticipato:   { bg: '#dbeafe', text: '#1e3a8a', label: '↗' },
  vuoto:        { bg: '#f8fafc', text: COLORS.textMuted, label: '—' },
};

function fmt€(v) {
  const n = parseFloat(v) || 0;
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(n);
}

export default function HRPrimaNotaSalari() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState(null); // null = tutti i mesi
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ anno: String(anno), solo_attivi: 'true' });
      if (mese) params.set('mese', String(mese));
      const res = await api.get(`/api/prima-nota-salari-v2/collettiva?${params.toString()}`);
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [anno, mese]);

  useEffect(() => { load(); }, [load]);

  // Calcoli derivati
  const kpi = useMemo(() => {
    if (!data) return { dare: 0, avere: 0, saldo: 0, aperti: 0 };
    const tg = data.totali_globali || {};
    const aperti = (data.dipendenti || []).filter(
      d => Math.abs(d.saldo) >= 0.01
    ).length;
    return {
      dare: tg.dare || 0,
      avere: tg.avere || 0,
      saldo: tg.saldo || 0,
      aperti,
    };
  }, [data]);

  const dipendenti = data?.dipendenti || [];

  return (
    <div style={{ padding: isMobile ? 12 : 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, color: COLORS.primary, margin: 0 }}>
          Prima Nota Salari
        </h1>
        <p style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 4 }}>
          Vista DARE / AVERE consolidata per tutti i dipendenti.
          Quanto deve l'azienda (cedolini) vs quanto ha già pagato (acconti + bonifici).
        </p>
      </div>

      {/* Filtri */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 16,
        flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <select
          value={anno}
          onChange={e => setAnno(Number(e.target.value))}
          style={{ padding: '8px 12px', border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 13, background: 'white' }}
        >
          {ANNI.map(a => <option key={a}>{a}</option>)}
        </select>

        <select
          value={mese ?? 'all'}
          onChange={e => setMese(e.target.value === 'all' ? null : Number(e.target.value))}
          style={{ padding: '8px 12px', border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 13, background: 'white' }}
        >
          <option value="all">Tutto l'anno (matrice)</option>
          {MESI_NOMI.map((m, i) => (
            <option key={m} value={i + 1}>{m}</option>
          ))}
        </select>

        <button
          onClick={load}
          disabled={loading}
          style={{
            padding: '8px 14px',
            background: 'white',
            color: COLORS.textMuted,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 8,
            cursor: loading ? 'wait' : 'pointer',
            fontSize: 13,
            display: 'flex',
            gap: 6,
            alignItems: 'center',
          }}
        >
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          Ricarica
        </button>

        {data && (
          <span style={{ fontSize: 12, color: COLORS.textMuted, marginLeft: 'auto' }}>
            {data.totale_dipendenti} dipendenti con movimenti
          </span>
        )}
      </div>

      {/* Errore */}
      {error && (
        <div style={{
          padding: 12,
          background: '#fee2e2',
          border: '1px solid #fca5a5',
          borderRadius: 8,
          color: '#b91c1c',
          fontSize: 13,
          marginBottom: 16,
          display: 'flex',
          gap: 8,
          alignItems: 'flex-start',
        }}>
          <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
          <div>{error}</div>
        </div>
      )}

      {/* KPI */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
        gap: 12,
        marginBottom: 20,
      }}>
        <KpiBox
          label="Totale Dare"
          value={fmt€(kpi.dare)}
          color={COLORS.primary}
          icon={FileText}
          sub={mese ? `${MESI_NOMI[mese - 1]} ${anno}` : `Anno ${anno}`}
        />
        <KpiBox
          label="Totale Avere"
          value={fmt€(kpi.avere)}
          color="#16a34a"
          icon={TrendingUp}
          sub="Acconti + bonifici"
        />
        <KpiBox
          label="Saldo Globale"
          value={fmt€(kpi.saldo)}
          color={Math.abs(kpi.saldo) < 0.01 ? '#16a34a' : '#dc2626'}
          icon={CreditCard}
          sub={Math.abs(kpi.saldo) < 0.01 ? 'Quadrato ✓' : (kpi.saldo > 0 ? 'Da pagare' : 'Anticipato')}
        />
        <KpiBox
          label="Saldi Aperti"
          value={kpi.aperti}
          color="#b45309"
          icon={AlertCircle}
          sub={`su ${dipendenti.length} dipendenti`}
        />
      </div>

      {/* Loading */}
      {loading && !data && (
        <div style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}>
          <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
          <div style={{ marginTop: 8, fontSize: 13 }}>Caricamento prima nota…</div>
        </div>
      )}

      {/* Tabella */}
      {!loading && dipendenti.length === 0 && (
        <div style={{
          padding: 40,
          textAlign: 'center',
          background: '#f8fafc',
          borderRadius: 10,
          color: COLORS.textMuted,
        }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
          <div style={{ fontWeight: 600, color: COLORS.text, marginBottom: 4 }}>
            Nessun movimento per il periodo
          </div>
          <div style={{ fontSize: 12 }}>
            Non risultano cedolini né acconti per i dipendenti in questo periodo.
          </div>
        </div>
      )}

      {!loading && dipendenti.length > 0 && (
        <div style={{
          background: 'white',
          border: `1px solid ${COLORS.border}`,
          borderRadius: 10,
          overflow: 'hidden',
          overflowX: 'auto',
        }}>
          {mese ? (
            <TabellaSingoloMese dipendenti={dipendenti} mese={mese} navigate={navigate} />
          ) : (
            <MatriceAnnuale dipendenti={dipendenti} navigate={navigate} anno={anno} />
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Vista matrice: tutti i mesi dell'anno, una colonna per mese
// ─────────────────────────────────────────────────────────────────────────────
function MatriceAnnuale({ dipendenti, navigate, anno }) {
  const goToFascicolo = (dipId) => {
    navigate(`/hr/dipendenti?dip=${dipId}&tab=prima_nota`);
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
      <thead>
        <tr style={{ background: '#f8fafc' }}>
          <th style={{
            padding: '10px 14px',
            textAlign: 'left',
            fontSize: 10,
            fontWeight: 700,
            color: COLORS.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            borderBottom: `1px solid ${COLORS.border}`,
            position: 'sticky',
            left: 0,
            background: '#f8fafc',
            zIndex: 1,
          }}>
            Dipendente
          </th>
          {MESI.map((m, i) => (
            <th key={m} style={{
              padding: '10px 6px',
              textAlign: 'center',
              fontSize: 9,
              fontWeight: 700,
              color: COLORS.textMuted,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderBottom: `1px solid ${COLORS.border}`,
              minWidth: 70,
            }}>
              {m}
            </th>
          ))}
          <th style={{
            padding: '10px 12px',
            textAlign: 'right',
            fontSize: 10,
            fontWeight: 700,
            color: COLORS.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            borderBottom: `1px solid ${COLORS.border}`,
            background: '#f1f5f9',
          }}>
            Saldo Anno
          </th>
        </tr>
      </thead>
      <tbody>
        {dipendenti.map((d, i) => (
          <tr
            key={d.dipendente_id}
            onClick={() => goToFascicolo(d.dipendente_id)}
            style={{
              borderBottom: `1px solid ${COLORS.border}30`,
              background: i % 2 === 0 ? 'white' : '#fafafa',
              cursor: 'pointer',
            }}
            onMouseEnter={e => e.currentTarget.style.background = '#f0f9ff'}
            onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'white' : '#fafafa'}
          >
            <td style={{
              padding: '8px 14px',
              fontWeight: 600,
              color: COLORS.text,
              position: 'sticky',
              left: 0,
              background: 'inherit',
              zIndex: 1,
              whiteSpace: 'nowrap',
            }}>
              {d.nome_completo}
            </td>
            {d.mesi.map(m => {
              const stato = STATO_COLORS[m.stato] || STATO_COLORS.vuoto;
              return (
                <td key={m.mese} style={{ padding: 4, textAlign: 'center' }}>
                  <CellaMese mese={m} stato={stato} />
                </td>
              );
            })}
            <td style={{
              padding: '8px 12px',
              textAlign: 'right',
              fontWeight: 700,
              fontVariantNumeric: 'tabular-nums',
              color: Math.abs(d.saldo) < 0.01 ? '#15803d' : (d.saldo > 0 ? '#dc2626' : '#1e3a8a'),
              background: '#f1f5f9',
              borderLeft: `2px solid ${COLORS.border}`,
            }}>
              {d.saldo > 0 ? '+' : ''}{fmt€(d.saldo)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Cella mensile compatta
// ─────────────────────────────────────────────────────────────────────────────
function CellaMese({ mese: m, stato }) {
  if (m.stato === 'vuoto') {
    return (
      <div style={{ fontSize: 16, color: COLORS.textMuted, opacity: 0.4 }}>—</div>
    );
  }
  return (
    <div
      title={`Dare: ${fmt€(m.totale_dare)} • Avere: ${fmt€(m.totale_avere)} • Saldo: ${fmt€(m.saldo)}`}
      style={{
        padding: '4px 6px',
        background: stato.bg,
        color: stato.text,
        borderRadius: 4,
        fontSize: 10,
        fontWeight: 700,
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      <div>{stato.label} {fmt€(m.saldo)}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Vista singolo mese: tabella dettaglio con dare/avere/saldo per ogni dipendente
// ─────────────────────────────────────────────────────────────────────────────
function TabellaSingoloMese({ dipendenti, mese, navigate }) {
  const goToFascicolo = (dipId) => {
    navigate(`/hr/dipendenti?dip=${dipId}&tab=prima_nota`);
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr style={{ background: '#f8fafc' }}>
          {['Dipendente', 'Voci dare', 'Dare', 'Voci avere', 'Avere', 'Saldo', 'Stato'].map(h => (
            <th key={h} style={{
              padding: '10px 14px',
              textAlign: 'left',
              fontSize: 10,
              fontWeight: 700,
              color: COLORS.textMuted,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              borderBottom: `1px solid ${COLORS.border}`,
            }}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {dipendenti.map((d, i) => {
          // Solo un mese: prendo il primo (e unico)
          const m = d.mesi[0] || { totale_dare: 0, totale_avere: 0, saldo: 0, stato: 'vuoto', n_voci_dare: 0, n_voci_avere: 0 };
          const stato = STATO_COLORS[m.stato] || STATO_COLORS.vuoto;
          return (
            <tr
              key={d.dipendente_id}
              onClick={() => goToFascicolo(d.dipendente_id)}
              style={{
                borderBottom: `1px solid ${COLORS.border}30`,
                background: i % 2 === 0 ? 'white' : '#fafafa',
                cursor: 'pointer',
              }}
              onMouseEnter={e => e.currentTarget.style.background = '#f0f9ff'}
              onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'white' : '#fafafa'}
            >
              <td style={{ padding: '11px 14px', fontWeight: 600, color: COLORS.text }}>
                {d.nome_completo}
              </td>
              <td style={{ padding: '11px 14px', color: COLORS.textMuted, fontSize: 11 }}>
                {m.n_voci_dare > 0 ? `${m.n_voci_dare} cedolino` : '—'}
              </td>
              <td style={{ padding: '11px 14px', fontWeight: 700, color: COLORS.primary, fontVariantNumeric: 'tabular-nums' }}>
                {fmt€(m.totale_dare)}
              </td>
              <td style={{ padding: '11px 14px', color: COLORS.textMuted, fontSize: 11 }}>
                {m.n_voci_avere > 0 ? `${m.n_voci_avere} voci` : '—'}
              </td>
              <td style={{ padding: '11px 14px', fontWeight: 700, color: '#15803d', fontVariantNumeric: 'tabular-nums' }}>
                {fmt€(m.totale_avere)}
              </td>
              <td style={{
                padding: '11px 14px',
                fontWeight: 800,
                fontVariantNumeric: 'tabular-nums',
                color: Math.abs(m.saldo) < 0.01 ? '#15803d' : (m.saldo > 0 ? '#dc2626' : '#1e3a8a'),
              }}>
                {m.saldo > 0 ? '+' : ''}{fmt€(m.saldo)}
              </td>
              <td style={{ padding: '11px 14px' }}>
                <span style={{
                  padding: '2px 8px',
                  background: stato.bg,
                  color: stato.text,
                  borderRadius: 4,
                  fontSize: 10,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}>
                  {stato.label} {m.stato.replace('_', ' ')}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// KPI box
// ─────────────────────────────────────────────────────────────────────────────
function KpiBox({ label, value, color, icon: Icon, sub }) {
  return (
    <div style={{
      padding: 14,
      background: 'white',
      border: `1px solid ${COLORS.border}`,
      borderRadius: 10,
      borderLeft: `4px solid ${color}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {label}
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>
            {value}
          </div>
          {sub && (
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>
              {sub}
            </div>
          )}
        </div>
        {Icon && <Icon size={20} style={{ color, opacity: 0.6 }} />}
      </div>
    </div>
  );
}
