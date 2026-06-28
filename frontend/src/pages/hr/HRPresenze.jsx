import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useAbortableEffect, isCanceledError } from '../../hooks';
import {
  Calendar,
  Clock,
  Users,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Plus,
} from 'lucide-react';
import api from '../../api';
import { COLORS, useIsMobile } from '../../lib/utils';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import BatchGiustificativoModal from '../../components/BatchGiustificativoModal';
import GrigliaMensilePresenze from '../../components/GrigliaMensilePresenze';

const MESI_LABEL = [
  'Gennaio',
  'Febbraio',
  'Marzo',
  'Aprile',
  'Maggio',
  'Giugno',
  'Luglio',
  'Agosto',
  'Settembre',
  'Ottobre',
  'Novembre',
  'Dicembre',
];
const GIORNI_SETTIMANA = ['LU', 'MA', 'ME', 'GI', 'VE', 'SA', 'DO'];

// Colori giustificativi
const GIUSTIFICATIVO_COLORS = {
  FE: { bg: '#dbeafe', text: '#1d4ed8', label: 'Ferie' },
  RL: { bg: '#dcfce7', text: '#16a34a', label: 'Rol' },
  MA: { bg: '#fef3c7', text: '#92400e', label: 'Malattia' },
  SM: { bg: '#fef3c7', text: '#d97706', label: 'Malattia Certificata' },
  AI: { bg: '#fee2e2', text: '#dc2626', label: 'Ass.za ingiustif.' },
  L1: { bg: '#f3e8ff', text: '#7c3aed', label: 'L.104' },
  PE: { bg: '#e0e7ff', text: '#4338ca', label: 'Permesso' },
  EF: { bg: '#cffafe', text: '#0891b2', label: 'Ex Festività' },
  CO: { bg: '#f0fdf4', text: '#15803d', label: 'Congedo' },
  IN: { bg: '#fef2f2', text: '#ef4444', label: 'Infortunio' },
  default: { bg: '#f1f5f9', text: '#64748b', label: 'Altro' },
};

function getGiustColor(code) {
  return GIUSTIFICATIVO_COLORS[code] || GIUSTIFICATIVO_COLORS['default'];
}

function getInitials(name) {
  if (!name) return '?';
  const parts = name.split(' ').filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.substring(0, 2).toUpperCase();
}

const AVATAR_COLORS = [
  '#2563eb',
  '#7c3aed',
  '#db2777',
  '#ea580c',
  '#059669',
  '#0891b2',
  '#4f46e5',
  '#c026d3',
  '#d97706',
  '#0d9488',
];
function avatarColor(name) {
  let hash = 0;
  for (let i = 0; i < (name || '').length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

export default function HRPresenze() {
  const isMobile = useIsMobile();
  const { anno: annoGlobale } = useAnnoGlobale();
  const [anno, setAnno] = useState(annoGlobale);
  const [mese, setMese] = useState(null); // null = tutti i mesi
  const [presenze, setPresenze] = useState([]);
  const [richieste, setRichieste] = useState([]);
  const [dipendenti, setDipendenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [anniDisponibili, setAnniDisponibili] = useState([]);
  const [mesiDisponibili, setMesiDisponibili] = useState([]);
  const [expandedEmployee, setExpandedEmployee] = useState(null);
  const [tab, setTab] = useState('calendario'); // 'calendario' | 'richieste'
  const [legenda, setLegenda] = useState({});
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [batchModalOpen, setBatchModalOpen] = useState(false);

  const loadData = useCallback(async (signal) => {
    setLoading(true);
    try {
      const params = { anno };
      if (mese) params.mese = mese;

      const [presRes, reqRes, dipRes] = await Promise.all([
        api.get('/api/attendance/libro-unico', { params, signal }),
        api.get('/api/attendance/richieste-pending', { signal })
          .catch((e) => { if (isCanceledError(e)) throw e; return { data: { richieste: [] } }; }),
        api.get('/api/dipendenti?limit=200', { signal })
          .catch((e) => { if (isCanceledError(e)) throw e; return { data: [] }; }),
      ]);

      if (signal?.aborted) return;

      const pData = presRes.data;
      setPresenze(pData.presenze || []);
      setAnniDisponibili(pData.anni_disponibili || [anno]);
      setMesiDisponibili(pData.mesi_per_anno?.[String(anno)] || []);

      const req = Array.isArray(reqRes.data) ? reqRes.data : reqRes.data?.richieste || [];
      setRichieste(req);

      const dip = Array.isArray(dipRes.data) ? dipRes.data : dipRes.data?.dipendenti || [];
      setDipendenti(dip);

      // Collect all legenda
      const allLeg = {};
      (pData.presenze || []).forEach(p => {
        if (p.legenda) Object.assign(allLeg, p.legenda);
      });
      setLegenda(allLeg);
    } catch (err) {
      if (isCanceledError(err)) return;
      console.error('Errore caricamento presenze:', err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [anno, mese]);

  useAbortableEffect((signal) => {
    loadData(signal);
  }, [loadData]);

  // Upload PDF handler
  const handleUploadPDF = async e => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/api/attendance/libro-unico/import-pdf', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setUploadResult({ success: true, ...res.data });
      loadData(); // Ricarica dati
    } catch (err) {
      setUploadResult({ success: false, message: err?.response?.data?.detail || 'Errore upload' });
    } finally {
      setUploading(false);
      e.target.value = ''; // Reset file input
    }
  };

  // Stats
  const numDipendenti = presenze.length;
  const oreTotali = presenze.reduce((sum, p) => sum + (p.totali?.ore_ordinarie || 0), 0);
  const giustificativiCount = presenze.reduce((sum, p) => {
    const t = p.totali || {};
    return sum + Object.keys(t).filter(k => k !== 'ore_ordinarie').length;
  }, 0);

  const toggleEmployee = cf => {
    setExpandedEmployee(prev => (prev === cf ? null : cf));
  };

  const cardStyle = {
    background: 'white',
    border: `1px solid ${COLORS.border}`,
    borderRadius: 12,
    overflow: 'hidden',
  };

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: isMobile ? 'flex-start' : 'center',
          marginBottom: 20,
          flexDirection: isMobile ? 'column' : 'row',
          gap: 12,
        }}
      >
        <div>
          <h1
            data-testid="page-title-presenze"
            style={{ margin: 0, fontSize: 24, fontWeight: 700, color: COLORS.text }}
          >
            Presenze & Calendario
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: COLORS.textMuted }}>
            Libro Unico del Lavoro — Dati importati dal consulente
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            value={anno}
            onChange={e => {
              setAnno(Number(e.target.value));
              setMese(null);
            }}
            data-testid="select-anno-presenze"
            style={{
              padding: '8px 14px',
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              fontSize: 14,
              background: 'white',
              fontWeight: 600,
            }}
          >
            {(anniDisponibili.length > 0 ? anniDisponibili : [annoGlobale]).map(a => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <select
            value={mese || ''}
            onChange={e => setMese(e.target.value ? Number(e.target.value) : null)}
            data-testid="select-mese-presenze"
            style={{
              padding: '8px 14px',
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              fontSize: 14,
              background: 'white',
            }}
          >
            <option value="">Tutti i mesi</option>
            {mesiDisponibili.map(m => (
              <option key={m} value={m}>
                {MESI_LABEL[m - 1]}
              </option>
            ))}
          </select>
          <button
            onClick={loadData}
            disabled={loading}
            data-testid="btn-refresh-presenze"
            style={{
              padding: '8px 14px',
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              fontSize: 13,
              background: 'white',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <RefreshCw
              size={14}
              style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
            />
            Aggiorna
          </button>
          <label
            data-testid="btn-upload-pdf"
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: 8,
              fontSize: 13,
              background: uploading ? COLORS.border : '#1a40b5',
              color: 'white',
              cursor: uploading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontWeight: 600,
            }}
          >
            <Calendar size={14} />
            {uploading ? 'Importazione…' : 'Importa PDF Libro Unico'}
            <input
              type="file"
              accept=".pdf"
              onChange={handleUploadPDF}
              style={{ display: 'none' }}
              disabled={uploading}
            />
          </label>
          <button
            data-testid="btn-batch-giustificativo"
            onClick={() => setBatchModalOpen(true)}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: 8,
              fontSize: 13,
              background: '#15803d',
              color: 'white',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontWeight: 600,
            }}
          >
            <Plus size={14} />
            Inserimento massivo
          </button>
        </div>
      </div>

      <BatchGiustificativoModal
        open={batchModalOpen}
        onClose={() => setBatchModalOpen(false)}
        dipendenti={dipendenti}
        onSaved={loadData}
      />

      {/* Upload Result */}
      {uploadResult && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '12px 16px',
            borderRadius: 10,
            marginBottom: 16,
            background: uploadResult.success ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${uploadResult.success ? '#bbf7d0' : '#fecaca'}`,
            color: uploadResult.success ? '#15803d' : '#dc2626',
            fontSize: 14,
          }}
        >
          <span style={{ fontWeight: 600 }}>{uploadResult.message}</span>
          {uploadResult.importati > 0 && (
            <span style={{ color: '#64748b' }}>
              — {uploadResult.importati} importati, {uploadResult.aggiornati || 0} aggiornati
            </span>
          )}
          <button
            onClick={() => setUploadResult(null)}
            style={{
              marginLeft: 'auto',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 16,
              color: '#94a3b8',
            }}
          >
            ×
          </button>
        </div>
      )}

      {/* KPI */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
          gap: 12,
          marginBottom: 20,
        }}
      >
        {[
          {
            label: 'Dipendenti',
            value: numDipendenti,
            icon: <Users size={18} />,
            color: '#2563eb',
          },
          {
            label: 'Ore Ordinarie',
            value: oreTotali.toFixed(1),
            icon: <Clock size={18} />,
            color: '#059669',
          },
          {
            label: 'Mesi Disponibili',
            value: mesiDisponibili.length,
            icon: <Calendar size={18} />,
            color: '#7c3aed',
          },
          {
            label: 'Richieste Pendenti',
            value: richieste.length,
            icon: <span style={{ fontSize: 16 }}>⏳</span>,
            color: richieste.length > 0 ? '#ea580c' : '#64748b',
            highlight: richieste.length > 0,
          },
        ].map(s => (
          <div
            key={s.label}
            style={{
              background: 'white',
              border: `1px solid ${s.highlight ? s.color + '40' : COLORS.border}`,
              borderRadius: 12,
              padding: '16px 20px',
              borderLeft: `4px solid ${s.color}`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ color: s.color }}>{s.icon}</span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: COLORS.textMuted,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                {s.label}
              </span>
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>
              {loading ? '…' : s.value}
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ ...cardStyle }}>
        <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}` }}>
          {[
            {
              id: 'calendario',
              label: 'Calendario Presenze',
              icon: <Calendar size={14} />,
              count: presenze.length,
            },
            {
              id: 'griglia',
              label: 'Griglia Mensile',
              icon: <Users size={14} />,
              count: 0,
            },
            {
              id: 'richieste',
              label: 'Richieste Assenza',
              icon: <Clock size={14} />,
              count: richieste.length,
            },
          ].map(t => (
            <button
              key={t.id}
              data-testid={`tab-presenze-${t.id}`}
              onClick={() => setTab(t.id)}
              style={{
                padding: '14px 20px',
                background: 'none',
                border: 'none',
                borderBottom: tab === t.id ? '3px solid #1a40b5' : '3px solid transparent',
                color: tab === t.id ? '#1a40b5' : COLORS.textMuted,
                fontWeight: tab === t.id ? 700 : 500,
                cursor: 'pointer',
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                marginBottom: -1,
              }}
            >
              {t.icon} {t.label}
              {t.count > 0 && (
                <span
                  style={{
                    background: tab === t.id ? '#1a40b5' : COLORS.border,
                    color: tab === t.id ? 'white' : COLORS.textMuted,
                    padding: '2px 8px',
                    borderRadius: 99,
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                >
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}>
            <RefreshCw
              size={24}
              style={{ animation: 'spin 1s linear infinite', marginBottom: 12 }}
            />
            <div>Caricamento presenze…</div>
          </div>
        )}

        {/* === CALENDARIO TAB === */}
        {!loading &&
          tab === 'calendario' &&
          (presenze.length === 0 ? (
            <div style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}>
              <Calendar size={48} style={{ marginBottom: 16, opacity: 0.3 }} />
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
                Nessuna presenza registrata
              </div>
              <div style={{ fontSize: 13 }}>
                {mese
                  ? `Nessun dato per ${MESI_LABEL[mese - 1]} ${anno}`
                  : `Nessun dato per il ${anno}`}
                . Le presenze vengono importate dal Libro Unico del consulente.
              </div>
            </div>
          ) : (
            <div>
              {/* Legenda */}
              {Object.keys(legenda).length > 0 && (
                <div
                  style={{
                    padding: '12px 20px',
                    borderBottom: `1px solid ${COLORS.border}`,
                    display: 'flex',
                    gap: 8,
                    flexWrap: 'wrap',
                    alignItems: 'center',
                  }}
                >
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: COLORS.textMuted,
                      marginRight: 4,
                    }}
                  >
                    LEGENDA:
                  </span>
                  {Object.entries(legenda).map(([code, desc]) => {
                    const c = getGiustColor(code);
                    return (
                      <span
                        key={code}
                        style={{
                          padding: '3px 10px',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          background: c.bg,
                          color: c.text,
                        }}
                      >
                        {code} = {desc}
                      </span>
                    );
                  })}
                </div>
              )}

              {/* Employee list */}
              {presenze.map((p, idx) => {
                const nome = `${p.cognome || ''} ${p.nome || ''}`.trim();
                const cf = p.codice_fiscale || '';
                const isExpanded = expandedEmployee === cf;
                const giorni = p.giorni || [];
                const totali = p.totali || {};

                return (
                  <div key={cf || idx} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                    {/* Employee header */}
                    <button
                      data-testid={`employee-presenze-${idx}`}
                      onClick={() => toggleEmployee(cf)}
                      style={{
                        width: '100%',
                        padding: '14px 20px',
                        background: isExpanded ? '#f8fafc' : 'white',
                        border: 'none',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                        textAlign: 'left',
                      }}
                    >
                      {isExpanded ? (
                        <ChevronDown size={16} color="#1a40b5" />
                      ) : (
                        <ChevronRight size={16} color={COLORS.textMuted} />
                      )}
                      <div
                        style={{
                          width: 36,
                          height: 36,
                          borderRadius: 8,
                          background: avatarColor(nome),
                          color: 'white',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: 12,
                          fontWeight: 700,
                          flexShrink: 0,
                        }}
                      >
                        {getInitials(nome)}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: 14,
                            color: isExpanded ? '#1a40b5' : COLORS.text,
                          }}
                        >
                          {nome}
                        </div>
                        <div style={{ fontSize: 11, color: COLORS.textMuted }}>
                          {p.periodo_label || `${MESI_LABEL[(p.mese || 1) - 1]} ${p.anno}`}
                          {p.codice_dipendente && ` • Cod. ${p.codice_dipendente}`}
                        </div>
                      </div>
                      {/* Totali quick view */}
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {totali.ore_ordinarie > 0 && (
                          <span
                            style={{
                              padding: '3px 10px',
                              borderRadius: 6,
                              fontSize: 11,
                              fontWeight: 600,
                              background: '#dcfce7',
                              color: '#16a34a',
                            }}
                          >
                            Ore: {totali.ore_ordinarie}
                          </span>
                        )}
                        {Object.entries(totali)
                          .filter(([k, v]) => k !== 'ore_ordinarie' && v > 0)
                          .map(([k, v]) => {
                            const c = getGiustColor(k);
                            return (
                              <span
                                key={k}
                                style={{
                                  padding: '3px 10px',
                                  borderRadius: 6,
                                  fontSize: 11,
                                  fontWeight: 600,
                                  background: c.bg,
                                  color: c.text,
                                }}
                              >
                                {k}: {v}h
                              </span>
                            );
                          })}
                      </div>
                    </button>

                    {/* Expanded calendar */}
                    {isExpanded && (
                      <div style={{ padding: '0 20px 20px' }}>
                        <div style={{ overflowX: 'auto' }}>
                          <table
                            style={{
                              width: '100%',
                              borderCollapse: 'collapse',
                              fontSize: 12,
                              minWidth: 600,
                            }}
                          >
                            <thead>
                              <tr>
                                <th
                                  style={{
                                    padding: '8px 6px',
                                    textAlign: 'center',
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: COLORS.textMuted,
                                    borderBottom: `2px solid ${COLORS.border}`,
                                  }}
                                >
                                  G.
                                </th>
                                <th
                                  style={{
                                    padding: '8px 6px',
                                    textAlign: 'center',
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: COLORS.textMuted,
                                    borderBottom: `2px solid ${COLORS.border}`,
                                  }}
                                >
                                  GIORNO
                                </th>
                                <th
                                  style={{
                                    padding: '8px 6px',
                                    textAlign: 'center',
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: COLORS.textMuted,
                                    borderBottom: `2px solid ${COLORS.border}`,
                                  }}
                                >
                                  ORE ORD.
                                </th>
                                <th
                                  style={{
                                    padding: '8px 6px',
                                    textAlign: 'left',
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: COLORS.textMuted,
                                    borderBottom: `2px solid ${COLORS.border}`,
                                  }}
                                >
                                  GIUSTIFICATIVI
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {giorni.map((g, gi) => {
                                const isFestivo =
                                  g.festivo ||
                                  g.giorno_settimana === 'DO' ||
                                  g.giorno_settimana === 'SA';
                                const hasGiust = (g.giustificativi || []).some(j => j.ore > 0);
                                return (
                                  <tr
                                    key={gi}
                                    style={{
                                      borderBottom: `1px solid ${COLORS.border}`,
                                      background: isFestivo ? '#f8fafc' : 'white',
                                      opacity: !g.ore_ordinarie && !hasGiust && isFestivo ? 0.6 : 1,
                                    }}
                                  >
                                    <td
                                      style={{
                                        padding: '6px',
                                        textAlign: 'center',
                                        fontWeight: 600,
                                        fontSize: 13,
                                      }}
                                    >
                                      {g.giorno}
                                    </td>
                                    <td
                                      style={{
                                        padding: '6px',
                                        textAlign: 'center',
                                        fontWeight: 500,
                                        color: isFestivo ? '#dc2626' : COLORS.text,
                                      }}
                                    >
                                      {g.giorno_settimana}
                                    </td>
                                    <td
                                      style={{
                                        padding: '6px',
                                        textAlign: 'center',
                                        fontWeight: 600,
                                        color: g.ore_ordinarie > 0 ? '#059669' : COLORS.textMuted,
                                      }}
                                    >
                                      {g.ore_ordinarie > 0 ? g.ore_ordinarie.toFixed(1) : '—'}
                                    </td>
                                    <td style={{ padding: '6px' }}>
                                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                        {(g.giustificativi || [])
                                          .filter(j => j.ore > 0)
                                          .map((j, ji) => {
                                            const c = getGiustColor(j.codice);
                                            return (
                                              <span
                                                key={ji}
                                                style={{
                                                  padding: '2px 8px',
                                                  borderRadius: 4,
                                                  fontSize: 10,
                                                  fontWeight: 600,
                                                  background: c.bg,
                                                  color: c.text,
                                                }}
                                              >
                                                {j.codice} {j.ore.toFixed(1)}h
                                              </span>
                                            );
                                          })}
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
                  </div>
                );
              })}
            </div>
          ))}

        {/* === GRIGLIA MENSILE TAB === */}
        {!loading && tab === 'griglia' && (
          <div style={{ padding: 16 }}>
            <GrigliaMensilePresenze
              dipendenti={dipendenti}
              onSaved={() => loadData()}
            />
          </div>
        )}

        {/* === RICHIESTE TAB === */}
        {!loading &&
          tab === 'richieste' &&
          (richieste.length === 0 ? (
            <div style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}>
              <Check size={48} style={{ marginBottom: 16, opacity: 0.3, color: '#22c55e' }} />
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
                Nessuna richiesta in attesa
              </div>
              <div style={{ fontSize: 13 }}>Tutte le richieste di assenza sono state gestite.</div>
            </div>
          ) : (
            <div style={{ padding: 20 }}>
              {richieste.map((r, i) => (
                <div
                  key={r.id || i}
                  style={{
                    padding: 16,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: 10,
                    marginBottom: 10,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600 }}>
                      {r.dipendente_nome || r.employee_name || '—'}
                    </div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                      {r.tipo || r.tipo_assenza || '—'} • {r.data_inizio || r.dal} →{' '}
                      {r.data_fine || r.al}
                    </div>
                    {r.note && (
                      <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                        "{r.note}"
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={async () => {
                        try {
                          await api.put(`/api/attendance/richiesta-assenza/${r.id}/approva`);
                          loadData();
                        } catch { /* approva richiesta — errore gestito dalla UI sopra */ }
                      }}
                      style={{
                        padding: '6px 14px',
                        background: '#dcfce7',
                        color: '#16a34a',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontWeight: 600,
                        fontSize: 12,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <Check size={14} /> Approva
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          await api.put(`/api/attendance/richiesta-assenza/${r.id}/rifiuta`, {
                            motivo: 'Rifiutata',
                          });
                          loadData();
                        } catch { /* approva richiesta — errore gestito dalla UI sopra */ }
                      }}
                      style={{
                        padding: '6px 14px',
                        background: '#fee2e2',
                        color: '#dc2626',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontWeight: 600,
                        fontSize: 12,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <X size={14} /> Rifiuta
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ))}
      </div>

      <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
