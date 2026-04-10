/**
 * RiconciliazionePaypal.jsx
 * Gestione completa estratti conto PayPal: import PDF, transazioni, report, riconciliazione banca.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  RefreshCw, CreditCard, AlertTriangle, CheckCircle2, FileText,
  Download, Search, TrendingDown, BarChart3
} from 'lucide-react';
import { toast } from 'sonner';
import { PageLayout } from '../components/PageLayout';

const formatEuro = (v) => new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v || 0);
const formatDate = (d) => { if (!d) return '-'; try { return new Date(d).toLocaleDateString('it-IT'); } catch { return d; } };

const TIPO_LABELS = {
  express_checkout: 'Express Checkout',
  pagamento_utenza: 'Abbonamento',
  pagamento_web: 'Pagamento Web',
  pagamento: 'Pagamento',
  accredito: 'Accredito',
  bonifico_paypal: 'Bonifico PayPal',
  rimborso: 'Rimborso',
  conversione_valuta: 'Conv. Valuta',
  prelievo: 'Prelievo',
  altro: 'Altro'
};

const TIPO_COLORS = {
  express_checkout: '#ef4444',
  pagamento_utenza: '#f59e0b',
  pagamento_web: '#8b5cf6',
  pagamento: '#dc2626',
  accredito: '#22c55e',
  bonifico_paypal: '#3b82f6',
  rimborso: '#06b6d4',
  conversione_valuta: '#6b7280',
  prelievo: '#f97316',
  altro: '#9ca3af'
};

export default function RiconciliazionePaypal() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [report, setReport] = useState(null);
  const [statements, setStatements] = useState([]);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [annoFiltro, setAnnoFiltro] = useState(anno);
  const [soloPagamenti, setSoloPagamenti] = useState(true);
  const [searchTx, setSearchTx] = useState('');

  const loadDashboard = useCallback(async () => {
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-statements/dashboard${params}`);
      setDashboard(res.data);
    } catch (e) { console.error(e); }
  }, [annoFiltro]);

  const loadTransactions = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (annoFiltro) params.append('anno', annoFiltro);
      if (soloPagamenti) params.append('solo_pagamenti', 'true');
      params.append('limit', '1000');
      const res = await api.get(`/api/paypal-statements/transactions?${params}`);
      setTransactions(res.data.transactions || []);
    } catch (e) { console.error(e); }
  }, [annoFiltro, soloPagamenti]);

  const loadReport = useCallback(async () => {
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-statements/report${params}`);
      setReport(res.data);
    } catch (e) { console.error(e); }
  }, [annoFiltro]);

  const loadStatements = useCallback(async () => {
    try {
      const res = await api.get('/api/paypal-statements/statements?limit=50');
      setStatements(res.data.statements || []);
    } catch (e) { console.error(e); }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadDashboard(), loadTransactions(), loadReport(), loadStatements()]);
    setLoading(false);
  }, [loadDashboard, loadTransactions, loadReport, loadStatements]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const filteredTx = transactions.filter(tx => {
    if (!searchTx) return true;
    const s = searchTx.toLowerCase();
    return (tx.nome_controparte || '').toLowerCase().includes(s)
      || (tx.descrizione || '').toLowerCase().includes(s)
      || (tx.email_controparte || '').toLowerCase().includes(s);
  });

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <RefreshCw style={{ width: 32, height: 32, animation: 'spin 1s linear infinite', color: '#0070ba' }} />
      </div>
    );
  }

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: <BarChart3 size={16} /> },
    { id: 'transazioni', label: 'Transazioni', icon: <CreditCard size={16} />, count: dashboard?.total_transactions },
    { id: 'report', label: 'Report Spese', icon: <TrendingDown size={16} /> },
    { id: 'estratti', label: 'Estratti Conto', icon: <FileText size={16} />, count: statements.length },
  ];

  return (
    <PageLayout title="PayPal" subtitle="Estratti conto, transazioni e riconciliazione">
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: 20, padding: '16px 20px',
          background: 'linear-gradient(135deg, #0070ba 0%, #003087 100%)',
          borderRadius: 12, color: 'white'
        }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 10 }}>
              <CreditCard size={24} /> Gestione PayPal
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, opacity: 0.85 }}>
              {dashboard?.total_statements || 0} estratti conto · {dashboard?.total_transactions || 0} transazioni · {formatEuro(Math.abs(dashboard?.totale_speso || 0))} spesi
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select value={annoFiltro || ''} onChange={e => setAnnoFiltro(e.target.value ? parseInt(e.target.value) : null)}
              style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.3)', background: 'rgba(255,255,255,0.15)', color: 'white', fontSize: 13 }}>
              <option value="" style={{ color: '#333' }}>Tutti gli anni</option>
              {[...Array(5)].map((_, i) => { const y = new Date().getFullYear() - i; return <option key={y} value={y} style={{ color: '#333' }}>{y}</option>; })}
            </select>
            <button onClick={() => navigate('/documenti/import')}
              style={{ padding: '8px 14px', background: 'rgba(255,255,255,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.3)', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>
              + Importa PDF
            </button>
          </div>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
          {[
            { label: 'Estratti Conto', value: dashboard?.total_statements, color: '#0070ba' },
            { label: 'Transazioni', value: dashboard?.total_transactions, color: '#6366f1' },
            { label: 'Totale Speso', value: formatEuro(Math.abs(dashboard?.totale_speso || 0)), color: '#ef4444', isText: true },
            { label: 'Riconciliati Banca', value: dashboard?.riconciliati_banca, color: '#22c55e' },
            { label: 'Movimenti Banca', value: dashboard?.movimenti_banca_paypal, color: '#f59e0b' },
          ].map((s) => (
            <div key={s.label} style={{ background: 'white', borderRadius: 10, padding: 16, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', borderLeft: `3px solid ${s.color}` }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>{s.label}</div>
              <div style={{ fontSize: s.isText ? 20 : 28, fontWeight: 'bold', color: s.color }}>{s.value || 0}</div>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, borderBottom: '2px solid #e5e7eb', marginBottom: 16 }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              style={{
                padding: '8px 14px', fontSize: 13, fontWeight: activeTab === t.id ? 'bold' : 'normal',
                borderRadius: '6px 6px 0 0', border: 'none',
                background: activeTab === t.id ? '#0070ba' : 'transparent',
                color: activeTab === t.id ? 'white' : '#6b7280',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6
              }}>
              {t.icon} {t.label}
              {t.count !== undefined && <span style={{ padding: '1px 6px', background: activeTab === t.id ? 'rgba(255,255,255,0.2)' : '#e5e7eb', borderRadius: 8, fontSize: 11 }}>{t.count}</span>}
            </button>
          ))}
        </div>

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && dashboard && (
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 16 }}>
            {/* Top Fornitori */}
            <div style={{ background: 'white', borderRadius: 10, padding: 16, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#1f2937' }}>Top Fornitori PayPal</h3>
              {(dashboard.top_fornitori || []).map((f) => (
                <div key={f.nome || f.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #f3f4f6' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{f.nome}</div>
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>{f.count} transazioni</div>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#ef4444' }}>{formatEuro(Math.abs(f.totale))}</div>
                </div>
              ))}
              {(!dashboard.top_fornitori || dashboard.top_fornitori.length === 0) && (
                <p style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center', padding: 20 }}>Nessun dato. Importa i PDF prima.</p>
              )}
            </div>

            {/* Per Tipo */}
            <div style={{ background: 'white', borderRadius: 10, padding: 16, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#1f2937' }}>Spese per Tipo</h3>
              {(dashboard.per_tipo || []).map((t) => (
                <div key={t.tipo} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #f3f4f6' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: TIPO_COLORS[t.tipo] || '#9ca3af' }} />
                    <span style={{ fontSize: 13 }}>{TIPO_LABELS[t.tipo] || t.tipo}</span>
                  </div>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>{formatEuro(Math.abs(t.totale))}</span>
                    <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>({t.count})</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Report Mensile */}
            {report && report.per_mese && report.per_mese.length > 0 && (
              <div style={{ background: 'white', borderRadius: 10, padding: 16, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', gridColumn: '1 / -1' }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#1f2937' }}>Andamento Mensile</h3>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {report.per_mese.map((m) => {
                    const maxVal = Math.max(...report.per_mese.map(x => Math.abs(x.totale)));
                    const pct = maxVal > 0 ? (Math.abs(m.totale) / maxVal) * 100 : 0;
                    return (
                      <div key={m.mese || m.month} style={{ flex: '1 1 80px', minWidth: 70, textAlign: 'center' }}>
                        <div style={{ height: 120, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
                          <div style={{ width: '70%', height: `${Math.max(pct, 5)}%`, background: '#0070ba', borderRadius: '4px 4px 0 0', minHeight: 4 }} />
                        </div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#374151', marginTop: 4 }}>{formatEuro(Math.abs(m.totale))}</div>
                        <div style={{ fontSize: 10, color: '#9ca3af' }}>{m.mese}</div>
                        <div style={{ fontSize: 10, color: '#9ca3af' }}>{m.count} tx</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Transazioni Tab */}
        {activeTab === 'transazioni' && (
          <div style={{ background: 'white', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: '#9ca3af' }} />
                <input value={searchTx} onChange={e => setSearchTx(e.target.value)}
                  placeholder="Cerca fornitore, descrizione..."
                  style={{ width: '100%', padding: '8px 8px 8px 32px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }} />
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
                <input type="checkbox" checked={soloPagamenti} onChange={e => setSoloPagamenti(e.target.checked)} />
                Solo pagamenti
              </label>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{filteredTx.length} risultati</span>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: 600, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f9fafb', position: 'sticky', top: 0 }}>
                    <th style={{ textAlign: 'left', padding: '10px 12px' }}>Data</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px' }}>Tipo</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px' }}>Descrizione</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px' }}>Controparte</th>
                    <th style={{ textAlign: 'right', padding: '10px 12px' }}>Importo</th>
                    <th style={{ textAlign: 'center', padding: '10px 12px' }}>Banca</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px' }}>ID</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTx.map((tx) => (
                    <tr key={tx.id || tx.transaction_id || tx.data + tx.importo} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>{formatDate(tx.data)}</td>
                      <td style={{ padding: '8px 12px' }}>
                        <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, background: `${TIPO_COLORS[tx.tipo] || '#9ca3af'}15`, color: TIPO_COLORS[tx.tipo] || '#9ca3af', fontWeight: 500 }}>
                          {TIPO_LABELS[tx.tipo] || tx.tipo}
                        </span>
                      </td>
                      <td style={{ padding: '8px 12px', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{tx.descrizione}</td>
                      <td style={{ padding: '8px 12px' }}>
                        <div style={{ fontWeight: 500 }}>{tx.nome_controparte || '-'}</div>
                        {tx.email_controparte && <div style={{ fontSize: 10, color: '#9ca3af' }}>{tx.email_controparte}</div>}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: tx.lordo < 0 ? '#ef4444' : '#22c55e' }}>
                        {formatEuro(tx.lordo)}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                        {tx.riconciliato_banca ? <CheckCircle2 size={16} style={{ color: '#22c55e' }} /> : <span style={{ color: '#d1d5db' }}>—</span>}
                      </td>
                      <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: 10, color: '#9ca3af', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {tx.transaction_id || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filteredTx.length === 0 && (
                <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
                  {dashboard?.total_transactions === 0 ? 'Nessuna transazione. Importa i PDF PayPal.' : 'Nessun risultato per il filtro.'}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Report Tab */}
        {activeTab === 'report' && report && (
          <div>
            <div style={{ background: 'white', borderRadius: 10, padding: 16, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Report Spese PayPal {annoFiltro || 'Totale'}</h3>
                <div style={{ fontSize: 20, fontWeight: 'bold', color: '#ef4444' }}>{formatEuro(Math.abs(report.totale_speso))}</div>
              </div>
              <div style={{ fontSize: 13, color: '#6b7280' }}>{report.totale_transazioni} pagamenti</div>
            </div>

            {/* Per Fornitore */}
            <div style={{ background: 'white', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', fontWeight: 600, fontSize: 14 }}>
                Dettaglio per Fornitore
              </div>
              <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                {(report.per_fornitore || []).map((f) => (
                  <details key={f.nome || f.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <summary style={{ padding: '10px 16px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontWeight: 500, fontSize: 13 }}>{f.nome}</span>
                        {f.email && <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>{f.email}</span>}
                      </div>
                      <div>
                        <span style={{ fontSize: 13, fontWeight: 600, color: '#ef4444' }}>{formatEuro(Math.abs(f.totale))}</span>
                        <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>({f.count} tx)</span>
                      </div>
                    </summary>
                    <div style={{ padding: '0 16px 10px 32px' }}>
                      {(f.transazioni || []).map((t, j) => (
                        <div key={t.id || t.transaction_id || j} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 12, color: '#6b7280' }}>
                          <span>{formatDate(t.data)} - {t.descrizione}</span>
                          <span style={{ fontWeight: 500 }}>{formatEuro(Math.abs(t.importo))}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Estratti Conto Tab */}
        {activeTab === 'estratti' && (
          <div style={{ background: 'white', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>Estratti Conto Importati ({statements.length})</span>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#f9fafb' }}>
                  <th style={{ textAlign: 'left', padding: '10px 12px' }}>Tipo</th>
                  <th style={{ textAlign: 'left', padding: '10px 12px' }}>Periodo</th>
                  <th style={{ textAlign: 'center', padding: '10px 12px' }}>Transazioni</th>
                  <th style={{ textAlign: 'right', padding: '10px 12px' }}>Pag. Inviati</th>
                  <th style={{ textAlign: 'right', padding: '10px 12px' }}>Depositi</th>
                  <th style={{ textAlign: 'right', padding: '10px 12px' }}>Saldo Finale</th>
                  <th style={{ textAlign: 'left', padding: '10px 12px' }}>File</th>
                </tr>
              </thead>
              <tbody>
                {statements.map((s) => (
                  <tr key={s.id || s.statement_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '8px 12px' }}>
                      <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, background: s.tipo_documento === 'CSR' ? '#fef3c7' : '#eff6ff', color: s.tipo_documento === 'CSR' ? '#92400e' : '#1e40af' }}>
                        {s.tipo_documento}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', fontWeight: 500 }}>
                      {formatDate(s.periodo_inizio)} — {formatDate(s.periodo_fine)}
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'center' }}>{s.totale_transazioni}</td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', color: '#ef4444' }}>{formatEuro(s.riepilogo?.pagamenti_inviati)}</td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', color: '#22c55e' }}>{formatEuro(s.riepilogo?.depositi_accrediti)}</td>
                    <td style={{ padding: '8px 12px', textAlign: 'right' }}>{formatEuro(s.riepilogo?.saldo_finale)}</td>
                    <td style={{ padding: '8px 12px', fontSize: 11, color: '#9ca3af' }}>{s.file_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {statements.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>Nessun estratto conto importato.</div>
            )}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
