import React, { useState, useEffect, useMemo } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { 
  FileText, Download, Search, Filter, ChevronDown, ChevronRight,
  CheckCircle, AlertTriangle, Eye, EyeOff, RefreshCw, Printer
} from 'lucide-react';

const TIPO_COLORS = {
  attivo:  { bg: '#ecfdf5', color: '#059669', label: 'Attivo' },
  passivo: { bg: '#fef2f2', color: '#dc2626', label: 'Passivo' },
  ricavo:  { bg: '#eff6ff', color: '#1535a8', label: 'Ricavo' },
  costo:   { bg: '#fffbeb', color: '#d97706', label: 'Costo' }
};

const GRUPPI_CONTI = {
  '01': 'Attività',
  '02': 'Passività',
  '03': 'Patrimonio Netto',
  '04': 'Ricavi',
  '05': 'Costi'
};

export default function BilancioVerifica() {
  const { anno } = useAnnoGlobale();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dettaglio, setDettaglio] = useState(false);
  const [search, setSearch] = useState('');
  const [filtroTipo, setFiltroTipo] = useState('tutti');
  const [soloMovimentati, setSoloMovimentati] = useState(true);
  const [expandedConti, setExpandedConti] = useState(new Set());
  const [showSaldi, setShowSaldi] = useState(true); // mostra saldo dare/avere separati

  useEffect(() => { loadData(); }, [anno, dettaglio]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/contabilita-gestionale/bilancio-verifica?anno=${anno}&dettaglio=${dettaglio}`);
      setData(res.data);
    } catch (err) {
      console.error('Errore BV:', err);
    } finally {
      setLoading(false);
    }
  };

  const contiFiltered = useMemo(() => {
    if (!data?.conti) return [];
    return data.conti.filter(c => {
      if (filtroTipo !== 'tutti' && c.tipo !== filtroTipo) return false;
      if (search) {
        const s = search.toLowerCase();
        if (!c.codice.toLowerCase().includes(s) && !c.nome.toLowerCase().includes(s)) return false;
      }
      return true;
    });
  }, [data, filtroTipo, search]);

  // Raggruppa per prefisso codice (01.xx, 02.xx, etc.)
  const contiRaggruppati = useMemo(() => {
    const gruppi = {};
    for (const c of contiFiltered) {
      const prefix = c.codice.substring(0, 2);
      if (!gruppi[prefix]) {
        gruppi[prefix] = {
          codice: prefix,
          nome: GRUPPI_CONTI[prefix] || `Gruppo ${prefix}`,
          conti: [],
          totale_dare: 0,
          totale_avere: 0
        };
      }
      gruppi[prefix].conti.push(c);
      gruppi[prefix].totale_dare += c.dare;
      gruppi[prefix].totale_avere += c.avere;
    }
    return Object.values(gruppi).sort((a, b) => a.codice.localeCompare(b.codice));
  }, [contiFiltered]);

  const toggleExpand = (codice) => {
    setExpandedConti(prev => {
      const next = new Set(prev);
      next.has(codice) ? next.delete(codice) : next.add(codice);
      return next;
    });
  };

  const expandAll = () => setExpandedConti(new Set(contiRaggruppati.map(g => g.codice)));
  const collapseAll = () => setExpandedConti(new Set());

  const handleExportCSV = () => {
    if (!data?.conti) return;
    const rows = [['Codice', 'Conto', 'Tipo', 'Dare', 'Avere', 'Saldo Dare', 'Saldo Avere'].join(';')];
    for (const c of data.conti) {
      rows.push([c.codice, `"${c.nome}"`, c.tipo, c.dare.toFixed(2), c.avere.toFixed(2), c.saldo_dare.toFixed(2), c.saldo_avere.toFixed(2)].join(';'));
    }
    rows.push(['', 'TOTALI', '', data.totali.dare.toFixed(2), data.totali.avere.toFixed(2), data.totali.saldo_dare.toFixed(2), data.totali.saldo_avere.toFixed(2)].join(';'));
    const blob = new Blob(['\uFEFF' + rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bilancio-verifica-${anno}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handlePrint = () => {
    window.print();
  };

  const SummaryCards = () => {
    if (!data) return null;
    const { totali, quadratura, riepilogo } = data;
    return (
      <PageGrid cols={5} gap={16}>
        <div style={{ background: '#ecfdf5', padding: 16, borderRadius: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: '#059669', fontWeight: 600 }}>TOTALE DARE</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#059669', marginTop: 4 }}>{formatEuro(totali.dare)}</div>
        </div>
        <div style={{ background: '#fef2f2', padding: 16, borderRadius: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>TOTALE AVERE</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#dc2626', marginTop: 4 }}>{formatEuro(totali.avere)}</div>
        </div>
        <div style={{ background: '#eff6ff', padding: 16, borderRadius: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: '#1535a8', fontWeight: 600 }}>SALDO DARE</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#1535a8', marginTop: 4 }}>{formatEuro(totali.saldo_dare)}</div>
        </div>
        <div style={{ background: '#fdf4ff', padding: 16, borderRadius: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: '#9333ea', fontWeight: 600 }}>SALDO AVERE</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#9333ea', marginTop: 4 }}>{formatEuro(totali.saldo_avere)}</div>
        </div>
        <div style={{ 
          background: quadratura ? '#ecfdf5' : '#fef2f2', 
          padding: 16, borderRadius: 12, textAlign: 'center',
          border: `2px solid ${quadratura ? '#22c55e' : '#ef4444'}`
        }}>
          <div style={{ fontSize: 12, color: quadratura ? '#059669' : '#dc2626', fontWeight: 600 }}>QUADRATURA</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: quadratura ? '#059669' : '#dc2626', marginTop: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            {quadratura ? <CheckCircle size={20} /> : <AlertTriangle size={20} />}
            {quadratura ? 'OK' : formatEuro(totali.sbilancio)}
          </div>
          <div style={{ fontSize: 11, color: '#6080a0', marginTop: 4 }}>
            {riepilogo.n_conti} conti • {riepilogo.n_conti_attivo}A {riepilogo.n_conti_passivo}P {riepilogo.n_conti_ricavo}R {riepilogo.n_conti_costo}C
          </div>
        </div>
      </PageGrid>
    );
  };

  return (
    <PageLayout
      title="Bilancio di Verifica"
      icon={<FileText size={28} />}
      subtitle={`Saldi dare/avere di tutti i conti – Anno ${anno}`}
      actions={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={loadData} disabled={loading}
            style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e8f0', background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 500 }}>
            <RefreshCw size={14} /> Aggiorna
          </button>
          <button onClick={handleExportCSV} disabled={!data}
            style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: '#1535a8', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}>
            <Download size={14} /> CSV
          </button>
          <button onClick={handlePrint}
            style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e8f0', background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 500 }}>
            <Printer size={14} /> Stampa
          </button>
        </div>
      }
    >
      {loading ? (
        <PageLoading message="Generazione bilancio di verifica..." />
      ) : data ? (
        <>
          <SummaryCards />

          {/* Filtri */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '20px 0', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
              <Search size={16} style={{ position: 'absolute', left: 12, top: 10, color: '#94a3b8' }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Cerca per codice o nome conto..."
                style={{ width: '100%', padding: '8px 12px 8px 36px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }}
              />
            </div>
            <select value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)}
              style={{ padding: '8px 16px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, fontWeight: 500 }}>
              <option value="tutti">Tutti i tipi</option>
              <option value="attivo">Attivo</option>
              <option value="passivo">Passivo</option>
              <option value="ricavo">Ricavi</option>
              <option value="costo">Costi</option>
            </select>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={dettaglio} onChange={e => setDettaglio(e.target.checked)} />
              Dettaglio movimenti
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={showSaldi} onChange={e => setShowSaldi(e.target.checked)} />
              Colonne Saldo
            </label>
            <button onClick={expandAll} style={{ padding: '6px 12px', border: '1px solid #e2e8f0', borderRadius: 6, background: 'white', fontSize: 12, cursor: 'pointer' }}>
              Espandi tutti
            </button>
            <button onClick={collapseAll} style={{ padding: '6px 12px', border: '1px solid #e2e8f0', borderRadius: 6, background: 'white', fontSize: 12, cursor: 'pointer' }}>
              Comprimi tutti
            </button>
          </div>

          {/* Tabella principale */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: '#1e293b', color: 'white' }}>
                  <th style={{ padding: '12px 8px', textAlign: 'left', width: 100 }}>Codice</th>
                  <th style={{ padding: '12px 8px', textAlign: 'left' }}>Conto</th>
                  <th style={{ padding: '12px 8px', textAlign: 'center', width: 80 }}>Tipo</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', width: 130 }}>Dare</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', width: 130 }}>Avere</th>
                  {showSaldi && (
                    <>
                      <th style={{ padding: '12px 8px', textAlign: 'right', width: 130, background: '#334155' }}>Saldo Dare</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right', width: 130, background: '#334155' }}>Saldo Avere</th>
                    </>
                  )}
                  <th style={{ padding: '12px 8px', textAlign: 'center', width: 50 }}>Mov.</th>
                </tr>
              </thead>
              <tbody>
                {contiRaggruppati.map((gruppo) => {
                  const isExpanded = expandedConti.has(gruppo.codice);
                  const saldoGruppo = gruppo.totale_dare - gruppo.totale_avere;
                  return (
                    <React.Fragment key={gruppo.codice}>
                      {/* Riga gruppo */}
                      <tr 
                        onClick={() => toggleExpand(gruppo.codice)}
                        style={{ background: '#f1f5f9', cursor: 'pointer', borderTop: '2px solid #cbd5e1' }}
                      >
                        <td style={{ padding: '10px 8px', fontWeight: 700, fontSize: 13 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            {gruppo.codice}
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px', fontWeight: 700, fontSize: 13 }}>
                          {gruppo.nome} ({gruppo.conti.length} conti)
                        </td>
                        <td style={{ padding: '10px 8px' }}></td>
                        <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: '#059669' }}>
                          {formatEuro(gruppo.totale_dare)}
                        </td>
                        <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: '#dc2626' }}>
                          {formatEuro(gruppo.totale_avere)}
                        </td>
                        {showSaldi && (
                          <>
                            <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: '#059669', background: '#e8f0fe' }}>
                              {saldoGruppo > 0 ? formatEuro(saldoGruppo) : '-'}
                            </td>
                            <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: '#dc2626', background: '#e8f0fe' }}>
                              {saldoGruppo < 0 ? formatEuro(Math.abs(saldoGruppo)) : '-'}
                            </td>
                          </>
                        )}
                        <td style={{ padding: '10px 8px', textAlign: 'center', color: '#64748b', fontSize: 12 }}>
                          {gruppo.conti.reduce((s, c) => s + c.n_movimenti, 0)}
                        </td>
                      </tr>

                      {/* Righe conti (se espanso) */}
                      {isExpanded && gruppo.conti.map((conto, idx) => {
                        const tc = TIPO_COLORS[conto.tipo] || { bg: '#f2f6fd', color: '#6080a0', label: conto.tipo };
                        return (
                          <React.Fragment key={conto.codice}>
                            <tr style={{ background: idx % 2 === 0 ? 'white' : '#fafafa', borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '8px 8px 8px 28px', fontFamily: 'monospace', fontSize: 13, color: '#475569' }}>
                                {conto.codice}
                              </td>
                              <td style={{ padding: '8px', color: '#1e293b' }}>{conto.nome}</td>
                              <td style={{ padding: '8px', textAlign: 'center' }}>
                                <span style={{ 
                                  padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
                                  background: tc.bg, color: tc.color 
                                }}>
                                  {tc.label}
                                </span>
                              </td>
                              <td style={{ padding: '8px', textAlign: 'right', fontWeight: 500, color: conto.dare > 0 ? '#059669' : '#cbd5e1' }}>
                                {formatEuro(conto.dare)}
                              </td>
                              <td style={{ padding: '8px', textAlign: 'right', fontWeight: 500, color: conto.avere > 0 ? '#dc2626' : '#cbd5e1' }}>
                                {formatEuro(conto.avere)}
                              </td>
                              {showSaldi && (
                                <>
                                  <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600, color: '#059669', background: '#f8fafc' }}>
                                    {conto.saldo_dare > 0 ? formatEuro(conto.saldo_dare) : '-'}
                                  </td>
                                  <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600, color: '#dc2626', background: '#f8fafc' }}>
                                    {conto.saldo_avere > 0 ? formatEuro(conto.saldo_avere) : '-'}
                                  </td>
                                </>
                              )}
                              <td style={{ padding: '8px', textAlign: 'center', fontSize: 12, color: '#64748b' }}>
                                {conto.n_movimenti}
                              </td>
                            </tr>
                            {/* Dettaglio movimenti */}
                            {dettaglio && conto.movimenti?.length > 0 && (
                              <tr>
                                <td colSpan={showSaldi ? 8 : 6} style={{ padding: '0 0 0 48px', background: '#fafbfc' }}>
                                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                                    <thead>
                                      <tr style={{ color: '#94a3b8' }}>
                                        <th style={{ padding: '4px 8px', textAlign: 'left' }}>Data</th>
                                        <th style={{ padding: '4px 8px', textAlign: 'left' }}>Descrizione</th>
                                        <th style={{ padding: '4px 8px', textAlign: 'right' }}>Dare</th>
                                        <th style={{ padding: '4px 8px', textAlign: 'right' }}>Avere</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {conto.movimenti.map((m, mi) => (
                                        <tr key={mi} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                          <td style={{ padding: '3px 8px', color: '#6080a0' }}>{m.data}</td>
                                          <td style={{ padding: '3px 8px', color: '#374151' }}>{m.descrizione}</td>
                                          <td style={{ padding: '3px 8px', textAlign: 'right', color: '#059669' }}>
                                            {m.dare > 0 ? formatEuro(m.dare) : ''}
                                          </td>
                                          <td style={{ padding: '3px 8px', textAlign: 'right', color: '#dc2626' }}>
                                            {m.avere > 0 ? formatEuro(m.avere) : ''}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </React.Fragment>
                  );
                })}
              </tbody>
              {/* Totali */}
              <tfoot>
                <tr style={{ background: '#1e293b', color: 'white', fontWeight: 700, fontSize: 15 }}>
                  <td colSpan={2} style={{ padding: '14px 8px' }}>TOTALE GENERALE</td>
                  <td></td>
                  <td style={{ padding: '14px 8px', textAlign: 'right' }}>{formatEuro(data.totali.dare)}</td>
                  <td style={{ padding: '14px 8px', textAlign: 'right' }}>{formatEuro(data.totali.avere)}</td>
                  {showSaldi && (
                    <>
                      <td style={{ padding: '14px 8px', textAlign: 'right', background: '#334155' }}>{formatEuro(data.totali.saldo_dare)}</td>
                      <td style={{ padding: '14px 8px', textAlign: 'right', background: '#334155' }}>{formatEuro(data.totali.saldo_avere)}</td>
                    </>
                  )}
                  <td style={{ padding: '14px 8px', textAlign: 'center' }}>
                    {data.conti.reduce((s, c) => s + c.n_movimenti, 0)}
                  </td>
                </tr>
                <tr style={{ background: data.quadratura ? '#dcfce7' : '#fee2e2' }}>
                  <td colSpan={showSaldi ? 8 : 6} style={{ padding: '10px 8px', textAlign: 'center', fontWeight: 600, fontSize: 14, color: data.quadratura ? '#166534' : '#991b1b' }}>
                    {data.quadratura 
                      ? '✓ Il bilancio di verifica quadra — Totale Dare = Totale Avere'
                      : `✗ SBILANCIO: ${formatEuro(data.totali.sbilancio)} — Verificare le registrazioni`
                    }
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Note */}
          <div style={{ marginTop: 24, padding: 16, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
            <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
              <strong>Fonti dati:</strong> Fatture ricevute, Corrispettivi, Prima Nota (Cassa + Banca + Salari), Cespiti/Ammortamenti. 
              Generato il {data.data_generazione ? new Date(data.data_generazione).toLocaleString('it-IT') : '-'}.
            </p>
          </div>
        </>
      ) : (
        <div style={{ textAlign: 'center', padding: 60, color: '#64748b' }}>
          <FileText size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
          <p>Nessun dato disponibile per l'anno {anno}</p>
        </div>
      )}
    </PageLayout>
  );
}
