import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { FileText, Download, RefreshCw, Mail, CheckCircle, AlertCircle, Users, Calendar, Eye, ChevronDown, ChevronRight, Search, Filter } from 'lucide-react';
import api from '../../api';
import { COLORS, useIsMobile } from '../../lib/utils';

const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i);
const MESI_LABEL = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre'];
const MESI_SHORT = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

function formatEuro(v) {
  if (v == null || isNaN(v) || v === 0) return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
}

function formatEuroAlways(v) {
  if (v == null || isNaN(v)) return '€ 0,00';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
}

function getNomeDipendente(b) {
  if (b.nome_dipendente && b.nome_dipendente !== 'N/A') return b.nome_dipendente;
  if (b.cognome && b.nome) return `${b.cognome} ${b.nome}`.toUpperCase();
  if (b.dipendente_nome) return b.dipendente_nome;
  if (b.dipendente) return b.dipendente;
  return b.filename || '—';
}

function getInitials(name) {
  if (!name || name === '—') return '?';
  const parts = name.split(' ').filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.substring(0, 2).toUpperCase();
}

function Badge({ pagato, small }) {
  return (
    <span data-testid={pagato ? 'badge-pagato' : 'badge-da-pagare'} style={{
      padding: small ? '2px 8px' : '4px 12px',
      borderRadius: 99,
      fontSize: small ? 10 : 11,
      fontWeight: 600,
      background: pagato ? '#dcfce7' : '#fef9c3',
      color: pagato ? '#16a34a' : '#a16207',
      whiteSpace: 'nowrap',
    }}>
      {pagato ? '✓ Pagato' : 'Da pagare'}
    </span>
  );
}

// Colors per avatar dipendente (deterministico per nome)
const AVATAR_COLORS = [
  '#2563eb', '#7c3aed', '#db2777', '#ea580c', '#059669',
  '#0891b2', '#4f46e5', '#c026d3', '#d97706', '#0d9488',
];
function avatarColor(name) {
  let hash = 0;
  for (let i = 0; i < (name || '').length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

export default function HRCedolini() {
  const isMobile = useIsMobile();
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [tab, setTab] = useState('cedolini');
  const [cedolini, setCedolini] = useState([]);
  const [f24, setF24] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedMese, setSelectedMese] = useState(null);
  const [expandedMonths, setExpandedMonths] = useState({});
  const [viewMode, setViewMode] = useState('mese'); // 'mese' | 'dipendente' | 'lista'

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.get('/api/cedolini', { params: { anno, limit: 500 } }),
      api.get('/api/paghe/distinte-f24', { params: { anno } }).catch(() => ({ data: [] })),
    ])
      .then(([cedRes, f24Res]) => {
        const c = cedRes.data?.cedolini || (Array.isArray(cedRes.data) ? cedRes.data : []);
        setCedolini(c);
        const f = f24Res.data?.distinte || (Array.isArray(f24Res.data) ? f24Res.data : []);
        setF24(f);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [anno]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-expand first month
  useEffect(() => {
    if (cedolini.length > 0 && Object.keys(expandedMonths).length === 0) {
      const firstMonth = Math.max(...cedolini.map(c => Number(c.mese) || 0));
      if (firstMonth > 0) setExpandedMonths({ [firstMonth]: true });
    }
  }, [cedolini]);

  const handleImportGmail = async () => {
    setImporting(true);
    setImportResult(null);
    try {
      const res = await api.post('/api/cedolini/import-gmail?since_days=180');
      setImportResult({ success: true, ...res.data });
      loadData();
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Errore durante il download da Gmail';
      setImportResult({ success: false, messaggio: detail });
    } finally {
      setImporting(false);
    }
  };

  // Computed data
  const filteredCedolini = useMemo(() => {
    let list = cedolini;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      list = list.filter(b => {
        const name = getNomeDipendente(b).toLowerCase();
        const cf = (b.codice_fiscale || '').toLowerCase();
        const mansione = (b.mansione || '').toLowerCase();
        return name.includes(term) || cf.includes(term) || mansione.includes(term);
      });
    }
    if (selectedMese) {
      list = list.filter(b => Number(b.mese) === selectedMese);
    }
    return list;
  }, [cedolini, searchTerm, selectedMese]);

  // Group by month
  const groupedByMonth = useMemo(() => {
    const groups = {};
    filteredCedolini.forEach(b => {
      const m = Number(b.mese) || 0;
      if (!groups[m]) groups[m] = [];
      groups[m].push(b);
    });
    // Sort months descending
    return Object.entries(groups)
      .sort(([a], [b]) => Number(b) - Number(a))
      .map(([mese, items]) => ({
        mese: Number(mese),
        label: MESI_LABEL[Number(mese) - 1] || `Mese ${mese}`,
        short: MESI_SHORT[Number(mese) - 1] || mese,
        items: items.sort((a, b) => getNomeDipendente(a).localeCompare(getNomeDipendente(b))),
        totaleNetto: items.reduce((s, c) => s + (Number(c.netto) || Number(c.netto_mese) || 0), 0),
        totaleLordo: items.reduce((s, c) => s + (Number(c.lordo) || 0), 0),
        count: items.length,
      }));
  }, [filteredCedolini]);

  // Group by employee
  const groupedByEmployee = useMemo(() => {
    const groups = {};
    filteredCedolini.forEach(b => {
      const name = getNomeDipendente(b);
      if (!groups[name]) groups[name] = { nome: name, cedolini: [], totalNetto: 0 };
      groups[name].cedolini.push(b);
      groups[name].totalNetto += (Number(b.netto) || Number(b.netto_mese) || 0);
    });
    return Object.values(groups).sort((a, b) => a.nome.localeCompare(b.nome));
  }, [filteredCedolini]);

  // KPI
  const totaleNetto = cedolini.reduce((s, b) => s + (Number(b.netto) || Number(b.netto_mese) || 0), 0);
  const daPagare = cedolini.filter(b => !b.pagato).reduce((s, b) => s + (Number(b.netto) || Number(b.netto_mese) || 0), 0);
  const numDipendenti = new Set(cedolini.map(b => getNomeDipendente(b))).size;
  const numMesi = new Set(cedolini.map(b => b.mese).filter(Boolean)).size;

  const toggleMonth = (mese) => {
    setExpandedMonths(prev => ({ ...prev, [mese]: !prev[mese] }));
  };

  // Styles
  const cardStyle = {
    background: 'white',
    border: `1px solid ${COLORS.border}`,
    borderRadius: 12,
    overflow: 'hidden',
  };

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', marginBottom: 24, flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
        <div>
          <h1 data-testid="page-title" style={{ margin: 0, fontSize: 24, fontWeight: 700, color: COLORS.text }}>
            Cedolini & Paghe
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: COLORS.textMuted }}>
            {cedolini.length} cedolini • {numDipendenti} dipendenti • {numMesi} {numMesi === 1 ? 'mese' : 'mesi'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            data-testid="select-anno-cedolini"
            value={anno}
            onChange={e => setAnno(Number(e.target.value))}
            style={{ padding: '8px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 14, background: 'white', fontWeight: 600 }}
          >
            {ANNI.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <button
            data-testid="btn-refresh-cedolini"
            onClick={loadData}
            disabled={loading}
            style={{ padding: '8px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 13, background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Aggiorna
          </button>
          <button
            data-testid="btn-import-gmail"
            onClick={handleImportGmail}
            disabled={importing}
            style={{
              padding: '8px 16px', border: 'none', borderRadius: 8, fontSize: 13,
              background: importing ? COLORS.border : '#1a40b5',
              color: 'white', cursor: importing ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600,
            }}
          >
            <Mail size={14} />
            {importing ? 'Download…' : 'Importa da Gmail'}
          </button>
        </div>
      </div>

      {/* Import Result */}
      {importResult && (
        <div data-testid="import-result-banner" style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px', borderRadius: 10, marginBottom: 16,
          background: importResult.success ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${importResult.success ? '#bbf7d0' : '#fecaca'}`,
          color: importResult.success ? '#15803d' : '#dc2626', fontSize: 14,
        }}>
          {importResult.success ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          <span style={{ fontWeight: 600 }}>{importResult.messaggio}</span>
          {importResult.success && importResult.trovati > 0 && (
            <span style={{ color: '#64748b', fontWeight: 400 }}>
              — {importResult.trovati} allegati, {importResult.duplicati_saltati} già presenti
            </span>
          )}
          <button onClick={() => setImportResult(null)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: '#94a3b8' }}>×</button>
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Cedolini', value: cedolini.length, icon: <FileText size={18} />, color: '#2563eb' },
          { label: 'Dipendenti', value: numDipendenti, icon: <Users size={18} />, color: '#7c3aed' },
          { label: 'Netto Totale', value: formatEuroAlways(totaleNetto), icon: <span style={{fontSize:16}}>💰</span>, color: '#059669' },
          { label: 'Da Pagare', value: formatEuroAlways(daPagare), icon: <span style={{fontSize:16}}>⏳</span>, color: daPagare > 0 ? '#ea580c' : '#64748b', highlight: daPagare > 0 },
        ].map(s => (
          <div key={s.label} style={{
            background: 'white',
            border: `1px solid ${s.highlight ? s.color + '40' : COLORS.border}`,
            borderRadius: 12, padding: '16px 20px',
            borderLeft: `4px solid ${s.color}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ color: s.color }}>{s.icon}</span>
              <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</span>
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ ...cardStyle, marginBottom: 0 }}>
        <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}`, alignItems: 'center', flexWrap: 'wrap' }}>
          {[
            { id: 'cedolini', label: 'Cedolini / Buste Paga', icon: <FileText size={14} /> },
            { id: 'f24', label: 'Distinte F24', icon: <span style={{fontSize:12}}>📋</span> },
          ].map(t => (
            <button key={t.id} data-testid={`tab-cedolini-${t.id}`} onClick={() => setTab(t.id)}
              style={{
                padding: '14px 20px', background: 'none', border: 'none',
                borderBottom: tab === t.id ? `3px solid #1a40b5` : '3px solid transparent',
                color: tab === t.id ? '#1a40b5' : COLORS.textMuted,
                fontWeight: tab === t.id ? 700 : 500, cursor: 'pointer', fontSize: 13,
                display: 'flex', alignItems: 'center', gap: 6, marginBottom: -1,
              }}
            >{t.icon}{t.label}</button>
          ))}

          {/* View mode toggles - right aligned */}
          {tab === 'cedolini' && (
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 2, padding: '8px 12px' }}>
              {[
                { id: 'mese', label: 'Per Mese', icon: <Calendar size={13} /> },
                { id: 'dipendente', label: 'Per Dipendente', icon: <Users size={13} /> },
              ].map(v => (
                <button key={v.id} data-testid={`view-${v.id}`} onClick={() => setViewMode(v.id)}
                  style={{
                    padding: '6px 12px', border: `1px solid ${viewMode === v.id ? '#1a40b5' : COLORS.border}`,
                    borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    background: viewMode === v.id ? '#1a40b510' : 'white',
                    color: viewMode === v.id ? '#1a40b5' : COLORS.textMuted,
                    fontWeight: viewMode === v.id ? 600 : 400,
                    display: 'flex', alignItems: 'center', gap: 4,
                  }}
                >{v.icon}{!isMobile && v.label}</button>
              ))}
            </div>
          )}
        </div>

        {/* Search bar */}
        {tab === 'cedolini' && !loading && cedolini.length > 0 && (
          <div style={{ padding: '12px 20px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: COLORS.textMuted }} />
              <input
                data-testid="search-cedolini"
                type="text"
                placeholder="Cerca dipendente, cod. fiscale, mansione..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                style={{
                  width: '100%', padding: '8px 12px 8px 32px',
                  border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 13,
                  outline: 'none',
                }}
              />
            </div>
            {selectedMese && (
              <button onClick={() => setSelectedMese(null)} style={{
                padding: '6px 12px', border: `1px solid #1a40b5`, borderRadius: 8,
                background: '#1a40b510', color: '#1a40b5', fontSize: 12, fontWeight: 600,
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
              }}>
                <Filter size={12} /> {MESI_LABEL[selectedMese - 1]} ✕
              </button>
            )}
          </div>
        )}

        <div style={{ padding: 0 }}>
          {loading && (
            <div style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}>
              <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', marginBottom: 12 }} />
              <div style={{ fontSize: 14 }}>Caricamento cedolini…</div>
            </div>
          )}

          {/* =================== CEDOLINI TAB =================== */}
          {!loading && tab === 'cedolini' && (
            cedolini.length === 0 ? (
              <div style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}>
                <Mail size={48} style={{ marginBottom: 16, opacity: 0.3 }} />
                <div style={{ fontSize: 16, marginBottom: 8, fontWeight: 600 }}>Nessun cedolino per il {anno}</div>
                <div style={{ fontSize: 13 }}>Usa <strong>Importa da Gmail</strong> per scaricare le buste paga.</div>
              </div>
            ) : viewMode === 'mese' ? (
              /* ---- VIEW: PER MESE ---- */
              <div>
                {groupedByMonth.map(group => (
                  <div key={group.mese} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                    {/* Month header */}
                    <button
                      data-testid={`month-toggle-${group.mese}`}
                      onClick={() => toggleMonth(group.mese)}
                      style={{
                        width: '100%', padding: '14px 20px', background: expandedMonths[group.mese] ? '#f8fafc' : 'white',
                        border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12,
                        textAlign: 'left', transition: 'background 0.15s',
                      }}
                    >
                      {expandedMonths[group.mese] ? <ChevronDown size={16} color="#1a40b5" /> : <ChevronRight size={16} color={COLORS.textMuted} />}
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 15, fontWeight: 700, color: expandedMonths[group.mese] ? '#1a40b5' : COLORS.text }}>
                          {group.label} {anno}
                        </span>
                        <span style={{ marginLeft: 10, fontSize: 12, color: COLORS.textMuted, fontWeight: 400 }}>
                          {group.count} cedolini
                        </span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 15, fontWeight: 700, color: '#059669' }}>
                          {formatEuroAlways(group.totaleNetto)}
                        </div>
                        <div style={{ fontSize: 11, color: COLORS.textMuted }}>netto totale</div>
                      </div>
                    </button>

                    {/* Expanded month content */}
                    {expandedMonths[group.mese] && (
                      <div style={{ padding: '0 20px 16px' }}>
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                            <thead>
                              <tr>
                                {['Dipendente', 'Mansione', 'Livello', 'Netto', 'TFR Mese', 'Stato', ''].map(h => (
                                  <th key={h} style={{
                                    padding: '10px 12px', textAlign: 'left', fontSize: 11,
                                    fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase',
                                    borderBottom: `2px solid ${COLORS.border}`, letterSpacing: '0.03em',
                                    whiteSpace: 'nowrap',
                                  }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {group.items.map((b, i) => {
                                const name = getNomeDipendente(b);
                                const netto = Number(b.netto) || Number(b.netto_mese) || 0;
                                return (
                                  <tr key={b.id || i} data-testid={`cedolino-row-${i}`} style={{
                                    borderBottom: `1px solid ${COLORS.border}`,
                                    transition: 'background 0.1s',
                                  }}
                                    onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                                  >
                                    <td style={{ padding: '12px', display: 'flex', alignItems: 'center', gap: 10 }}>
                                      <div style={{
                                        width: 32, height: 32, borderRadius: 8,
                                        background: avatarColor(name),
                                        color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        fontSize: 11, fontWeight: 700, flexShrink: 0,
                                      }}>
                                        {getInitials(name)}
                                      </div>
                                      <div>
                                        <div style={{ fontWeight: 600, color: COLORS.text, fontSize: 13 }}>{name}</div>
                                        {b.codice_fiscale && (
                                          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: 'monospace' }}>{b.codice_fiscale}</div>
                                        )}
                                      </div>
                                    </td>
                                    <td style={{ padding: '12px', color: COLORS.textMuted, fontSize: 12 }}>{b.mansione || '—'}</td>
                                    <td style={{ padding: '12px', fontSize: 12 }}>
                                      {b.livello ? (
                                        <span style={{ padding: '2px 8px', borderRadius: 4, background: '#f1f5f9', fontSize: 11, fontWeight: 500 }}>
                                          {b.livello}
                                        </span>
                                      ) : '—'}
                                    </td>
                                    <td style={{ padding: '12px', fontWeight: 700, color: '#059669', fontSize: 14 }}>
                                      {formatEuroAlways(netto)}
                                    </td>
                                    <td style={{ padding: '12px', fontSize: 12, color: COLORS.textMuted }}>
                                      {formatEuro(b.tfr_mese || b.tfr_quota_anno)}
                                    </td>
                                    <td style={{ padding: '12px' }}>
                                      <Badge pagato={b.pagato} small />
                                    </td>
                                    <td style={{ padding: '12px', textAlign: 'right' }}>
                                      {b.id && (
                                        <button
                                          data-testid={`btn-view-pdf-${i}`}
                                          onClick={() => window.open(`${api.defaults.baseURL}/api/cedolini/${b.id}/download`, '_blank')}
                                          title="Scarica PDF"
                                          style={{
                                            padding: '4px 8px', border: `1px solid ${COLORS.border}`,
                                            borderRadius: 6, background: 'white', cursor: 'pointer',
                                            display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11,
                                            color: COLORS.textMuted, transition: 'all 0.15s',
                                          }}
                                          onMouseEnter={e => { e.currentTarget.style.borderColor = '#1a40b5'; e.currentTarget.style.color = '#1a40b5'; }}
                                          onMouseLeave={e => { e.currentTarget.style.borderColor = COLORS.border; e.currentTarget.style.color = COLORS.textMuted; }}
                                        >
                                          <Download size={12} /> PDF
                                        </button>
                                      )}
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
                ))}
                {filteredCedolini.length === 0 && searchTerm && (
                  <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
                    Nessun risultato per "{searchTerm}"
                  </div>
                )}
              </div>
            ) : (
              /* ---- VIEW: PER DIPENDENTE ---- */
              <div style={{ padding: 20 }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
                  {groupedByEmployee.map(emp => (
                    <div key={emp.nome} data-testid={`employee-card-${emp.nome}`} style={{
                      border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16,
                      background: 'white', transition: 'box-shadow 0.15s',
                    }}
                      onMouseEnter={e => e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.08)'}
                      onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                        <div style={{
                          width: 40, height: 40, borderRadius: 10,
                          background: avatarColor(emp.nome),
                          color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 14, fontWeight: 700,
                        }}>
                          {getInitials(emp.nome)}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 700, fontSize: 14, color: COLORS.text }}>{emp.nome}</div>
                          <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                            {emp.cedolini[0]?.mansione || emp.cedolini[0]?.livello || '—'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: 16, fontWeight: 700, color: '#059669' }}>
                            {formatEuroAlways(emp.totalNetto)}
                          </div>
                          <div style={{ fontSize: 11, color: COLORS.textMuted }}>netto anno</div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {emp.cedolini
                          .sort((a, b) => (Number(a.mese) || 0) - (Number(b.mese) || 0))
                          .map((c, ci) => (
                          <div key={ci} style={{
                            padding: '4px 10px', borderRadius: 6,
                            background: c.pagato ? '#dcfce7' : '#f1f5f9',
                            fontSize: 11, fontWeight: 500,
                            color: c.pagato ? '#16a34a' : COLORS.text,
                            display: 'flex', alignItems: 'center', gap: 4,
                          }}>
                            <span>{MESI_SHORT[Number(c.mese) - 1] || '?'}</span>
                            <span style={{ fontWeight: 700 }}>{formatEuroAlways(Number(c.netto) || Number(c.netto_mese) || 0)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                {filteredCedolini.length === 0 && searchTerm && (
                  <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
                    Nessun risultato per "{searchTerm}"
                  </div>
                )}
              </div>
            )
          )}

          {/* =================== F24 TAB =================== */}
          {!loading && tab === 'f24' && (
            f24.length === 0
              ? <div style={{ padding: 60, textAlign: 'center', color: COLORS.textMuted }}>
                  <span style={{ fontSize: 40, display: 'block', marginBottom: 12, opacity: 0.3 }}>📋</span>
                  <div style={{ fontSize: 15, fontWeight: 600 }}>Nessuna distinta F24 per il {anno}</div>
                </div>
              : (
                <div style={{ overflowX: 'auto', padding: 20 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr>
                        {['Riferimento', 'Mese', 'Importo', 'Scadenza', 'Stato'].map(h => (
                          <th key={h} style={{
                            padding: '10px 12px', textAlign: 'left', fontSize: 11,
                            fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase',
                            borderBottom: `2px solid ${COLORS.border}`,
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {f24.map((f, i) => (
                        <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '12px', fontWeight: 600 }}>{f.riferimento || f.codice || `F24 ${i + 1}`}</td>
                          <td style={{ padding: '12px' }}>{MESI_LABEL[Number(f.mese) - 1] || f.mese || '—'}</td>
                          <td style={{ padding: '12px', fontWeight: 700, color: '#059669' }}>{formatEuro(f.importo || f.totale)}</td>
                          <td style={{ padding: '12px' }}>{f.scadenza ? new Date(f.scadenza).toLocaleDateString('it-IT') : '—'}</td>
                          <td style={{ padding: '12px' }}><Badge pagato={f.pagato} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
