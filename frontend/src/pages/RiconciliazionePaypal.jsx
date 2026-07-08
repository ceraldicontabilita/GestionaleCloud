/**
 * RiconciliazionePaypal.jsx
 * Gestione completa estratti conto PayPal: import PDF, transazioni, report, riconciliazione banca.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useIsMobile } from '../hooks/useData';
import {
  RefreshCw,
  CreditCard,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Download,
  Search,
  TrendingDown,
  BarChart3,
  Link2,
} from 'lucide-react';
import { toast } from 'sonner';
import { PageLayout } from '../components/PageLayout';
import PaypalTransactionDetailModal from '../components/PaypalTransactionDetailModal';

const formatEuro = v =>
  new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v || 0);
const formatDate = d => {
  if (!d) return '-';
  try {
    return new Date(d).toLocaleDateString('it-IT').replaceAll('/', '-');
  } catch {
    return d;
  }
};

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
  altro: 'Altro',
};

const TIPO_COLORS = {
  express_checkout: '#dc2626',
  pagamento_utenza: '#d97706',
  pagamento_web: '#0f2744',
  pagamento: '#dc2626',
  accredito: '#16a34a',
  bonifico_paypal: '#3b82f6',
  rimborso: '#16a34a',
  conversione_valuta: '#64748b',
  prelievo: '#b8860b',
  altro: '#64748b',
};

export default function RiconciliazionePaypal() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [report, setReport] = useState(null);
  const [statements, setStatements] = useState([]);
  // Deep link ?tab=mapping (usato dal bottone "Mappa fornitore" del modale
  // dettaglio transazione, PaypalTransactionDetailModal.jsx) — prima veniva
  // ignorato e la pagina apriva sempre su "dashboard".
  const [activeTab, setActiveTab] = useState(
    () => new URLSearchParams(location.search).get('tab') || 'dashboard'
  );
  useEffect(() => {
    const tab = new URLSearchParams(location.search).get('tab');
    if (tab) setActiveTab(tab);
  }, [location.search]);
  // Anno unico e globale (barra di navigazione in alto) — nessun selettore
  // locale duplicato: una pagina con un filtro anno proprio, indipendente
  // da quello globale, dava l'impressione che cambiare l'anno in alto non
  // avesse alcun effetto sulla pagina.
  const annoFiltro = anno;
  const [soloPagamenti, setSoloPagamenti] = useState(true);
  const [searchTx, setSearchTx] = useState('');
  const [modalTxId, setModalTxId] = useState(null); // transaction_id aperto nel modale
  const [mappingData, setMappingData] = useState(null);
  const [mappingLoading, setMappingLoading] = useState(false);
  const [selectedForn, setSelectedForn] = useState({}); // {paypal_account_id: fornitore_id}
  const [createModal, setCreateModal] = useState(null); // {paypal_account_id, nome_controparte, ...} | null
  const [importingCsv, setImportingCsv] = useState(false);
  const csvInputRef = useRef(null);
  const [syncMesi, setSyncMesi] = useState(3);
  const [syncing, setSyncing] = useState(false);

  const loadDashboard = useCallback(async () => {
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-statements/dashboard${params}`);
      setDashboard(res.data);
    } catch (e) {
      console.error(e);
    }
  }, [annoFiltro]);

  const loadTransactions = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (annoFiltro) params.append('anno', annoFiltro);
      if (soloPagamenti) params.append('solo_pagamenti', 'true');
      params.append('limit', '1000');
      const res = await api.get(`/api/paypal-statements/transactions?${params}`);
      setTransactions(res.data.transactions || []);
    } catch (e) {
      console.error(e);
    }
  }, [annoFiltro, soloPagamenti]);

  const loadReport = useCallback(async () => {
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-statements/report${params}`);
      setReport(res.data);
    } catch (e) {
      console.error(e);
    }
  }, [annoFiltro]);

  const loadStatements = useCallback(async () => {
    try {
      const res = await api.get('/api/paypal-statements/statements?limit=50');
      setStatements(res.data.statements || []);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadDashboard(), loadTransactions(), loadReport(), loadStatements()]);
    setLoading(false);
  }, [loadDashboard, loadTransactions, loadReport, loadStatements]);

  const handleImportCsv = async e => {
    const file = e.target.files?.[0];
    e.target.value = ''; // permette di ricaricare lo stesso file due volte
    if (!file) return;
    setImportingCsv(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/api/paypal-statements/import-csv', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const r = res.data || {};
      toast.success(
        `✓ CSV importato — ${r.transazioni_inserite} transazioni (${r.transazioni_duplicate} già presenti), ` +
          `${r.riconciliazione?.riconciliati || 0} riconciliate con la banca`
      );
      await loadAll();
    } catch (err) {
      toast.error('Errore import CSV: ' + (err.response?.data?.detail || err.message));
    } finally {
      setImportingCsv(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const loadMapping = useCallback(async () => {
    setMappingLoading(true);
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-api/account-ids-non-mappati${params}`);
      setMappingData(res.data);
      // Pre-seleziona automaticamente i fornitori con match certo (nome_controparte ↔ ragione_sociale)
      const autoSelect = {};
      for (const item of res.data.items || []) {
        if (item.suggested_fornitore_id) {
          autoSelect[item.paypal_account_id] = item.suggested_fornitore_id;
        }
      }
      if (Object.keys(autoSelect).length > 0) {
        setSelectedForn(prev => ({ ...autoSelect, ...prev }));
      }
    } catch (e) {
      toast.error('Errore caricamento mapping: ' + (e.response?.data?.detail || e.message));
    } finally {
      setMappingLoading(false);
    }
  }, [annoFiltro]);

  const mappaTuttiCerti = async () => {
    if (!mappingData) return;
    const certi = mappingData.items.filter(i => i.suggested_fornitore_id);
    if (certi.length === 0) {
      toast.info('Nessun match certo da mappare');
      return;
    }
    if (!confirm(`Mappare automaticamente ${certi.length} fornitori con match certo?`)) return;
    let ok = 0;
    for (const item of certi) {
      try {
        await api.post('/api/paypal-api/mappa-fornitore', {
          paypal_account_id: item.paypal_account_id,
          fornitore_id: item.suggested_fornitore_id,
        });
        ok++;
      } catch {
        // continua col prossimo
      }
    }
    toast.success(`✓ Mappati ${ok}/${certi.length} fornitori`);
    loadMapping();
  };

  const mappaFornitore = async (paypalAccountId, fornitoreId) => {
    if (!fornitoreId) {
      toast.error('Seleziona prima un fornitore');
      return;
    }
    try {
      const res = await api.post('/api/paypal-api/mappa-fornitore', {
        paypal_account_id: paypalAccountId,
        fornitore_id: fornitoreId,
      });
      toast.success(`✓ Mappato: ${res.data.fornitore}`);
      loadMapping();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const [cercandoEmail, setCercandoEmail] = useState(null); // paypal_account_id in corso

  const handleCercaFatturaEmail = async paypalAccountId => {
    setCercandoEmail(paypalAccountId);
    try {
      const res = await api.post(`/api/paypal-api/account/${paypalAccountId}/cerca-fattura-email`);
      const r = res.data || {};
      const trovati = r.stats?.new_documents ?? 0;
      if (trovati > 0) {
        toast.success(
          `✓ Trovati ${trovati} documenti in posta per "${r.cercato_per}" — vai su Documenti per vederli`
        );
      } else {
        toast.info(
          `Nessun nuovo documento trovato in posta per "${r.cercato_per}" (${r.stats?.emails_found ?? 0} email esaminate)`
        );
      }
    } catch (e) {
      toast.error('Errore ricerca email: ' + (e.response?.data?.detail || e.message));
    } finally {
      setCercandoEmail(null);
    }
  };

  useEffect(() => {
    if (activeTab === 'mapping') {
      loadMapping();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, annoFiltro]);

  const filteredTx = transactions.filter(tx => {
    if (!searchTx) return true;
    const s = searchTx.toLowerCase();
    return (
      (tx.nome_controparte || '').toLowerCase().includes(s) ||
      (tx.descrizione || '').toLowerCase().includes(s) ||
      (tx.email_controparte || '').toLowerCase().includes(s)
    );
  });

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
        }}
      >
        <RefreshCw
          style={{ width: 32, height: 32, animation: 'spin 1s linear infinite', color: '#0f2744' }}
        />
      </div>
    );
  }

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: <BarChart3 size={16} /> },
    {
      id: 'transazioni',
      label: 'Transazioni',
      icon: <CreditCard size={16} />,
      count: dashboard?.total_transactions,
    },
    { id: 'report', label: 'Report Spese', icon: <TrendingDown size={16} /> },
    {
      id: 'estratti',
      label: 'Estratti Conto',
      icon: <FileText size={16} />,
      count: statements.length,
    },
    {
      id: 'mapping',
      label: 'Mapping Fornitori',
      icon: <Link2 size={16} />,
      count: mappingData?.totale_non_mappati,
    },
  ];

  return (
    <PageLayout title="PayPal" subtitle="Estratti conto, transazioni e riconciliazione">
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 20,
            padding: '16px 20px',
            background: '#0f2744',
            borderRadius: 8,
            color: 'white',
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: 22,
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
              }}
            >
              <CreditCard size={24} /> Gestione PayPal
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, opacity: 0.85 }}>
              {dashboard?.total_statements || 0} estratti conto ·{' '}
              {dashboard?.total_transactions || 0} transazioni ·{' '}
              {formatEuro(Math.abs(dashboard?.totale_speso || 0))} spesi
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/documenti/import')}
              style={{
                padding: '8px 14px',
                minHeight: 40,
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.3)',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              + Importa PDF
            </button>
            <input
              ref={csvInputRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={handleImportCsv}
            />
            <button
              onClick={() => csvInputRef.current?.click()}
              disabled={importingCsv}
              style={{
                padding: '8px 14px',
                minHeight: 40,
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.3)',
                borderRadius: 6,
                cursor: importingCsv ? 'default' : 'pointer',
                fontSize: 13,
                opacity: importingCsv ? 0.6 : 1,
              }}
              title="Importa estratto conto PayPal esportato in CSV"
            >
              {importingCsv ? 'Import…' : '+ Importa CSV'}
            </button>
            <select
              value={syncMesi}
              onChange={e => setSyncMesi(parseInt(e.target.value))}
              style={{
                padding: '8px 10px',
                minHeight: 40,
                borderRadius: 6,
                border: '1px solid rgba(255,255,255,0.3)',
                background: 'rgba(255,255,255,0.15)',
                color: 'white',
                fontSize: 13,
              }}
            >
              <option value={1} style={{ color: '#333' }}>
                Ultimo mese
              </option>
              <option value={3} style={{ color: '#333' }}>
                Ultimi 3 mesi
              </option>
              <option value={6} style={{ color: '#333' }}>
                Ultimi 6 mesi
              </option>
              <option value={12} style={{ color: '#333' }}>
                Ultimo anno
              </option>
            </select>
            <button
              data-testid="sync-paypal-api-btn"
              disabled={syncing}
              onClick={async () => {
                setSyncing(true);
                try {
                  toast.info('Sincronizzazione PayPal API in corso…');
                  const today = new Date();
                  const end = today.toISOString().slice(0, 10);
                  const startDate = new Date(today.getFullYear(), today.getMonth() - syncMesi, 1);
                  const start = startDate.toISOString().slice(0, 10);
                  const res = await api.post('/api/paypal-api/sync', {
                    start_date: start,
                    end_date: end,
                  });
                  const r = res.data || {};
                  toast.success(
                    `✓ Sync OK — ${r.total || 0} transazioni (${r.enriched || 0} arricchite), riconciliazione in corso…`
                  );
                  // Dopo la sync, riconcilia subito con fatture/banca — senza
                  // questo passaggio le transazioni restavano senza riferimento
                  // a fattura/controparte finché qualcuno non lo lanciava a mano.
                  try {
                    const ric = await api.post('/api/paypal-api/riconcilia', {
                      start_date: start,
                      end_date: end,
                    });
                    const fatt = ric.data?.fatture?.riconciliati ?? 0;
                    toast.success(`✓ Riconciliazione OK — ${fatt} transazioni associate a fatture`);
                  } catch (ricErr) {
                    toast.error(
                      'Sync OK ma riconciliazione fallita: ' +
                        (ricErr.response?.data?.detail || ricErr.message)
                    );
                  }
                  loadDashboard();
                  loadTransactions();
                } catch (e) {
                  toast.error('Errore sync: ' + (e.response?.data?.detail || e.message));
                } finally {
                  setSyncing(false);
                }
              }}
              style={{
                padding: '8px 14px',
                minHeight: 40,
                background: 'rgba(184, 134, 11, 0.35)',
                color: 'white',
                border: '1px solid rgba(184, 134, 11, 0.7)',
                borderRadius: 6,
                cursor: syncing ? 'default' : 'pointer',
                fontSize: 13,
                fontWeight: 600,
                opacity: syncing ? 0.6 : 1,
              }}
              title="Sincronizza le transazioni PayPal via API (Transaction Search) e le riconcilia con fatture/banca"
            >
              {syncing ? '⏳ Sync…' : '🔄 Sync PayPal API'}
            </button>
          </div>
        </div>

        {/* Stats */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 12,
            marginBottom: 20,
          }}
        >
          {[
            { label: 'Estratti Conto', value: dashboard?.total_statements },
            { label: 'Transazioni', value: dashboard?.total_transactions },
            {
              label: 'Totale Speso',
              value: formatEuro(Math.abs(dashboard?.totale_speso || 0)),
              color: '#dc2626',
              isText: true,
            },
            {
              label: 'Riconciliati Banca',
              value: dashboard?.riconciliati_banca,
              color: '#16a34a',
            },
            { label: 'Movimenti Banca', value: dashboard?.movimenti_banca_paypal },
          ].map(s => (
            <div
              key={s.label}
              style={{
                background: 'white',
                borderRadius: 8,
                padding: 16,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: '#64748b',
                  textTransform: 'uppercase',
                  marginBottom: 4,
                }}
              >
                {s.label}
              </div>
              <div
                style={{
                  fontSize: s.isText ? 20 : 24,
                  fontWeight: 700,
                  color: s.color || '#1e293b',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                }}
              >
                {s.value || 0}
              </div>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div
          style={{
            display: 'flex',
            gap: 4,
            flexWrap: 'wrap',
            borderBottom: '2px solid #e2e8f0',
            marginBottom: 16,
          }}
        >
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              style={{
                padding: '8px 14px',
                minHeight: 40,
                fontSize: 13,
                fontWeight: activeTab === t.id ? 'bold' : 'normal',
                borderRadius: '6px 6px 0 0',
                border: 'none',
                background: activeTab === t.id ? '#0f2744' : 'transparent',
                color: activeTab === t.id ? 'white' : '#64748b',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              {t.icon} {t.label}
              {t.count !== undefined && (
                <span
                  style={{
                    padding: '1px 6px',
                    background: activeTab === t.id ? 'rgba(255,255,255,0.2)' : '#e2e8f0',
                    borderRadius: 8,
                    fontSize: 11,
                  }}
                >
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && dashboard && (
          <div
            style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 16 }}
          >
            {/* Top Fornitori */}
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                padding: 16,
                border: '1px solid #e2e8f0',
              }}
            >
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#1f2937' }}>
                Top Fornitori PayPal
              </h3>
              {(dashboard.top_fornitori || []).map(f => (
                <div
                  key={f.nome || f.id}
                  onClick={() => {
                    setSearchTx(f.nome && f.nome !== 'N/D' ? f.nome : '');
                    setActiveTab('transazioni');
                  }}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: '1px solid #f1f5f9',
                    cursor: 'pointer',
                  }}
                  title={`Vedi le transazioni di ${f.nome}`}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{f.nome}</div>
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>{f.count} transazioni</div>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#dc2626' }}>
                    {formatEuro(Math.abs(f.totale))}
                  </div>
                </div>
              ))}
              {(!dashboard.top_fornitori || dashboard.top_fornitori.length === 0) && (
                <p style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center', padding: 20 }}>
                  Nessun dato. Importa i PDF prima.
                </p>
              )}
            </div>

            {/* Per Tipo */}
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                padding: 16,
                border: '1px solid #e2e8f0',
              }}
            >
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#1f2937' }}>
                Spese per Tipo
              </h3>
              {(dashboard.per_tipo || []).map(t => (
                <div
                  key={t.tipo}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: '1px solid #f1f5f9',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: '50%',
                        background: TIPO_COLORS[t.tipo] || '#9ca3af',
                      }}
                    />
                    <span style={{ fontSize: 13 }}>{TIPO_LABELS[t.tipo] || t.tipo}</span>
                  </div>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
                      {formatEuro(Math.abs(t.totale))}
                    </span>
                    <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>
                      ({t.count})
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Report Mensile */}
            {report && report.per_mese && report.per_mese.length > 0 && (
              <div
                style={{
                  background: 'white',
                  borderRadius: 8,
                  padding: 16,
                  border: '1px solid #e2e8f0',
                  gridColumn: '1 / -1',
                }}
              >
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#1f2937' }}>
                  Andamento Mensile
                </h3>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {report.per_mese.map(m => {
                    const maxVal = Math.max(...report.per_mese.map(x => Math.abs(x.totale)));
                    const pct = maxVal > 0 ? (Math.abs(m.totale) / maxVal) * 100 : 0;
                    return (
                      <div
                        key={m.mese || m.month}
                        style={{ flex: '1 1 80px', minWidth: 70, textAlign: 'center' }}
                      >
                        <div
                          style={{
                            height: 120,
                            display: 'flex',
                            alignItems: 'flex-end',
                            justifyContent: 'center',
                          }}
                        >
                          <div
                            style={{
                              width: '70%',
                              height: `${Math.max(pct, 5)}%`,
                              background: '#0f2744',
                              borderRadius: '4px 4px 0 0',
                              minHeight: 4,
                            }}
                          />
                        </div>
                        <div
                          style={{ fontSize: 11, fontWeight: 600, color: '#374151', marginTop: 4 }}
                        >
                          {formatEuro(Math.abs(m.totale))}
                        </div>
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
          <div
            style={{
              background: 'white',
              borderRadius: 8,
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '12px 16px',
                borderBottom: '1px solid #e2e8f0',
                display: 'flex',
                gap: 12,
                alignItems: 'center',
                flexWrap: 'wrap',
              }}
            >
              <div style={{ position: 'relative', flex: 1 }}>
                <Search
                  size={14}
                  style={{ position: 'absolute', left: 10, top: 10, color: '#9ca3af' }}
                />
                <input
                  value={searchTx}
                  onChange={e => setSearchTx(e.target.value)}
                  placeholder="Cerca fornitore, descrizione..."
                  style={{
                    width: '100%',
                    padding: '8px 8px 8px 32px',
                    border: '1px solid #e2e8f0',
                    borderRadius: 6,
                    fontSize: 13,
                  }}
                />
              </div>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={soloPagamenti}
                  onChange={e => setSoloPagamenti(e.target.checked)}
                />
                Solo pagamenti
              </label>
              <span style={{ fontSize: 12, color: '#64748b' }}>{filteredTx.length} risultati</span>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: 600, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#f8fafc', position: 'sticky', top: 0 }}>
                    <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Data</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Tipo</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Descrizione</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Controparte</th>
                    <th style={{ textAlign: 'right', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Importo</th>
                    <th style={{ textAlign: 'center', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Banca</th>
                    <th style={{ textAlign: 'center', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Fattura</th>
                    <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>ID</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTx.map(tx => (
                    <tr
                      key={tx.id || tx.transaction_id || tx.data + tx.importo}
                      onClick={() => (tx.transaction_id || tx.id) && setModalTxId(tx.transaction_id || tx.id)}
                      style={{
                        borderBottom: '1px solid #f1f5f9',
                        cursor: (tx.transaction_id || tx.id) ? 'pointer' : 'default',
                        transition: 'background 120ms',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                      onMouseLeave={e => (e.currentTarget.style.background = '')}
                      title="Clicca per vedere il dettaglio completo"
                    >
                      <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                        {formatDate(tx.data)}
                      </td>
                      <td style={{ padding: '8px 12px' }}>
                        <span
                          style={{
                            padding: '2px 8px',
                            borderRadius: 8,
                            fontSize: 11,
                            background: `${TIPO_COLORS[tx.tipo] || '#9ca3af'}15`,
                            color: TIPO_COLORS[tx.tipo] || '#9ca3af',
                            fontWeight: 500,
                          }}
                        >
                          {TIPO_LABELS[tx.tipo] || tx.tipo}
                        </span>
                      </td>
                      <td
                        style={{
                          padding: '8px 12px',
                          maxWidth: 200,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {tx.descrizione}
                      </td>
                      <td style={{ padding: '8px 12px' }}>
                        <div style={{ fontWeight: 500 }}>{tx.nome_controparte || '-'}</div>
                        {tx.email_controparte && (
                          <div style={{ fontSize: 10, color: '#9ca3af' }}>
                            {tx.email_controparte}
                          </div>
                        )}
                      </td>
                      <td
                        style={{
                          padding: '8px 12px',
                          textAlign: 'right',
                          fontWeight: 600,
                          color: tx.lordo < 0 ? '#dc2626' : '#16a34a',
                          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                        }}
                      >
                        {formatEuro(tx.lordo)}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                        {tx.riconciliato_banca ? (
                          <CheckCircle2 size={16} style={{ color: '#16a34a' }} />
                        ) : (
                          <span style={{ color: '#cbd5e1' }}>—</span>
                        )}
                      </td>
                      <td
                        style={{ padding: '8px 12px', textAlign: 'center' }}
                        onClick={e => e.stopPropagation()}
                      >
                        {tx.fattura_associata ? (
                          <a
                            href={
                              tx.fattura_associata.view_url ||
                              `/api/fatture-ricevute/fattura/${tx.fattura_associata.fattura_id}/view-assoinvoice`
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                            title={
                              tx.fattura_associata.match === 'solo_importo'
                                ? `⚠️ Match SOLO per importo (da verificare): Fatt. ${tx.fattura_associata.numero || ''} · ${tx.fattura_associata.fornitore || ''} — apri`
                                : `Fatt. ${tx.fattura_associata.numero || ''} · ${tx.fattura_associata.fornitore || ''} — apri`
                            }
                            style={{ textDecoration: 'none', fontSize: 15 }}
                          >
                            {tx.fattura_associata.match === 'solo_importo' ? '📄⚠️' : '📄'}
                          </a>
                        ) : tx.gmail_associata?.gmail_link ? (
                          <a
                            href={tx.gmail_associata.gmail_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={`Email trovata su Gmail: ${tx.gmail_associata.subject || ''} — apri in Gmail`}
                            style={{ textDecoration: 'none', fontSize: 15 }}
                          >
                            ✉️
                          </a>
                        ) : (
                          <span style={{ color: '#cbd5e1' }} title="Ricerca automatica in corso (fatture + Gmail ogni 30 min)">
                            —
                          </span>
                        )}
                      </td>
                      <td
                        style={{
                          padding: '8px 12px',
                          fontFamily: 'monospace',
                          fontSize: 10,
                          color: '#9ca3af',
                          maxWidth: 140,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {tx.transaction_id || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filteredTx.length === 0 && (
                <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
                  {dashboard?.total_transactions === 0
                    ? 'Nessuna transazione. Importa i PDF PayPal.'
                    : 'Nessun risultato per il filtro.'}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Report Tab */}
        {activeTab === 'report' && report && (
          <div>
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                padding: 16,
                border: '1px solid #e2e8f0',
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 16,
                }}
              >
                <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
                  Report Spese PayPal {annoFiltro || 'Totale'}
                </h3>
                <div
                  style={{
                    fontSize: 20,
                    fontWeight: 'bold',
                    color: '#dc2626',
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  }}
                >
                  {formatEuro(Math.abs(report.totale_speso))}
                </div>
              </div>
              <div style={{ fontSize: 13, color: '#64748b' }}>
                {report.totale_transazioni} pagamenti
              </div>
            </div>

            {/* Per Fornitore */}
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  padding: '12px 16px',
                  background: '#f8fafc',
                  borderBottom: '1px solid #e2e8f0',
                  fontWeight: 600,
                  fontSize: 14,
                }}
              >
                Dettaglio per Fornitore
              </div>
              <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                {(report.per_fornitore || []).map(f => (
                  <details key={f.nome || f.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <summary
                      style={{
                        padding: '10px 16px',
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <span style={{ fontWeight: 500, fontSize: 13 }}>{f.nome}</span>
                        {f.email && (
                          <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>
                            {f.email}
                          </span>
                        )}
                      </div>
                      <div>
                        <span style={{ fontSize: 13, fontWeight: 600, color: '#dc2626' }}>
                          {formatEuro(Math.abs(f.totale))}
                        </span>
                        <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>
                          ({f.count} tx)
                        </span>
                      </div>
                    </summary>
                    <div style={{ padding: '0 16px 10px 32px' }}>
                      {(f.transazioni || []).map((t, j) => {
                        const txId = t.transaction_id || t.id;
                        return (
                          <div
                            key={t.id || t.transaction_id || j}
                            onClick={() => txId && setModalTxId(txId)}
                            onMouseEnter={e => { if (txId) e.currentTarget.style.background = '#f1f5f9'; }}
                            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              padding: '6px 8px',
                              fontSize: 12,
                              color: '#64748b',
                              cursor: txId ? 'pointer' : 'default',
                              borderRadius: 4,
                              transition: 'background 120ms',
                            }}
                            title={txId ? 'Clicca per il dettaglio' : ''}
                          >
                            <span>
                              {formatDate(t.data)} - {t.descrizione}
                            </span>
                            <span style={{ fontWeight: 500 }}>{formatEuro(Math.abs(t.importo))}</span>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Estratti Conto Tab */}
        {activeTab === 'estratti' && (
          <div
            style={{
              background: 'white',
              borderRadius: 8,
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '12px 16px',
                background: '#f8fafc',
                borderBottom: '1px solid #e2e8f0',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 14 }}>
                Estratti Conto Importati ({statements.length})
              </span>
            </div>
            <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Tipo</th>
                  <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Periodo</th>
                  <th style={{ textAlign: 'center', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Transazioni</th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Pag. Inviati</th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Depositi</th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>Saldo Finale</th>
                  <th style={{ textAlign: 'left', padding: '10px 12px', fontSize: 11, textTransform: 'uppercase', color: '#64748b' }}>File</th>
                </tr>
              </thead>
              <tbody>
                {statements.map(s => (
                  <tr key={s.id || s.statement_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 12px' }}>
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: 8,
                          fontSize: 11,
                          background: s.tipo_documento === 'CSR' ? '#fef3c7' : '#eff6ff',
                          color: s.tipo_documento === 'CSR' ? '#92400e' : '#1e40af',
                        }}
                      >
                        {s.tipo_documento}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', fontWeight: 500 }}>
                      {formatDate(s.periodo_inizio)} — {formatDate(s.periodo_fine)}
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                      {s.totale_transazioni}
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', color: '#dc2626', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                      {formatEuro(s.riepilogo?.pagamenti_inviati)}
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', color: '#16a34a', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                      {formatEuro(s.riepilogo?.depositi_accrediti)}
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                      {formatEuro(s.riepilogo?.saldo_finale)}
                    </td>
                    <td style={{ padding: '8px 12px', fontSize: 11, color: '#9ca3af' }}>
                      {s.file_name}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            {statements.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
                Nessun estratto conto importato.
              </div>
            )}
          </div>
        )}

        {/* Mapping Fornitori Tab */}
        {activeTab === 'mapping' && (
          <div
            data-testid="mapping-fornitori-panel"
            style={{
              background: 'white',
              borderRadius: 8,
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '14px 18px',
                background: '#f8fafc',
                borderBottom: '1px solid #e2e8f0',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 10,
              }}
            >
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>
                  🔗 Account PayPal da mappare ai Fornitori
                  {mappingData?.totale_non_mappati !== undefined && (
                    <span
                      style={{
                        marginLeft: 10,
                        padding: '2px 10px',
                        borderRadius: 8,
                        background: '#fef3c7',
                        color: '#92400e',
                        fontSize: 12,
                      }}
                    >
                      {mappingData.totale_non_mappati} non mappati
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                  Associa l'ID PayPal del beneficiario al fornitore corretto per abilitare la
                  riconciliazione automatica delle fatture.
                </div>
              </div>
              <button
                data-testid="reload-mapping-btn"
                onClick={loadMapping}
                disabled={mappingLoading}
                style={{
                  padding: '8px 14px',
                  minHeight: 40,
                  background: '#0f2744',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                {mappingLoading ? '⏳ Caricamento...' : '🔄 Ricarica'}
              </button>
            </div>

            {/* Banner azione massiva match certi */}
            {mappingData && mappingData.items.some(i => i.suggested_fornitore_id) && (
              <div
                style={{
                  padding: '12px 18px',
                  background: '#dcfce7',
                  borderBottom: '1px solid #16a34a',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 12,
                }}
              >
                <div style={{ fontSize: 13, color: '#166534' }}>
                  🎯{' '}
                  <strong>
                    {mappingData.items.filter(i => i.suggested_fornitore_id).length} match certi
                  </strong>{' '}
                  trovati tramite nome PayPal. Puoi mapparli tutti con un click.
                </div>
                <button
                  data-testid="mappa-tutti-certi-btn"
                  onClick={mappaTuttiCerti}
                  style={{
                    padding: '8px 18px',
                    minHeight: 40,
                    background: '#0f2744',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}
                >
                  🚀 Mappa tutti i certi
                </button>
              </div>
            )}

            {mappingLoading && !mappingData && (
              <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
                <RefreshCw
                  style={{
                    width: 24,
                    height: 24,
                    animation: 'spin 1s linear infinite',
                    color: '#0f2744',
                  }}
                />
              </div>
            )}

            {mappingData && mappingData.items.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', color: '#16a34a', fontWeight: 600 }}>
                ✅ Tutti gli account PayPal sono mappati!
              </div>
            )}

            {mappingData &&
              mappingData.items.map(item => (
                <div
                  key={item.paypal_account_id}
                  data-testid={`mapping-row-${item.paypal_account_id}`}
                  style={{
                    padding: '14px 18px',
                    borderBottom: '1px solid #f1f5f9',
                    display: 'grid',
                    gridTemplateColumns: isMobile ? '1fr' : '260px 1fr 260px',
                    gap: 14,
                    alignItems: 'center',
                  }}
                >
                  {/* Colonna 1: info account */}
                  <div>
                    {item.nome_controparte && (
                      <div
                        style={{ fontSize: 13, fontWeight: 700, color: '#1e293b', marginBottom: 4 }}
                      >
                        🏢 {item.nome_controparte}
                      </div>
                    )}
                    <div
                      style={{
                        fontFamily: 'Courier New, monospace',
                        fontSize: 11,
                        fontWeight: 600,
                        color: '#0f2744',
                      }}
                    >
                      {item.paypal_account_id}
                    </div>
                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>
                      {item.n_tx} tx · {formatEuro(item.importo_totale)}
                    </div>
                    <div style={{ fontSize: 10, color: '#9ca3af' }}>
                      Media: {formatEuro(item.importo_medio)} · Ultima:{' '}
                      {formatDate(item.ultima_data)}
                    </div>
                    {item.email_controparte && (
                      <div style={{ fontSize: 10, color: '#64748b', marginTop: 3 }}>
                        ✉️ {item.email_controparte}
                      </div>
                    )}
                    {item.invoice_ids?.length > 0 && (
                      <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 3 }}>
                        Invoice: {item.invoice_ids.slice(0, 2).join(', ')}
                      </div>
                    )}
                  </div>

                  {/* Colonna 2: selezione fornitore con badge match certo */}
                  <div>
                    {item.suggested_fornitore_id && (
                      <div
                        style={{
                          fontSize: 11,
                          color: '#166534',
                          fontWeight: 700,
                          marginBottom: 4,
                          background: '#dcfce7',
                          padding: '3px 8px',
                          borderRadius: 8,
                          display: 'inline-block',
                        }}
                      >
                        🎯 Match certo da nome PayPal
                      </div>
                    )}
                    <select
                      data-testid={`select-fornitore-${item.paypal_account_id}`}
                      value={selectedForn[item.paypal_account_id] || ''}
                      onChange={e =>
                        setSelectedForn({
                          ...selectedForn,
                          [item.paypal_account_id]: e.target.value,
                        })
                      }
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        border:
                          item.suggested_fornitore_id &&
                          selectedForn[item.paypal_account_id] === item.suggested_fornitore_id
                            ? '2px solid #16a34a'
                            : '1px solid #e2e8f0',
                        borderRadius: 6,
                        fontSize: 13,
                        background: 'white',
                      }}
                    >
                      <option value="">— Seleziona fornitore —</option>
                      {item.candidati?.filter(c => c.source?.startsWith('nome_paypal')).length >
                        0 && (
                        <optgroup label="🎯 Match certo (nome PayPal)">
                          {item.candidati
                            .filter(c => c.source?.startsWith('nome_paypal'))
                            .map(c => (
                              <option key={c.fornitore_id} value={c.fornitore_id}>
                                {c.nome} · P.IVA {c.piva} · score {c.score}
                              </option>
                            ))}
                        </optgroup>
                      )}
                      {item.candidati?.filter(c => c.source === 'importo_simile').length > 0 && (
                        <optgroup label="💡 Candidati (importo simile)">
                          {item.candidati
                            .filter(c => c.source === 'importo_simile')
                            .map(c => (
                              <option key={c.fornitore_id} value={c.fornitore_id}>
                                {c.nome} · P.IVA {c.piva} · {c.n_fatture_simili} fatture
                              </option>
                            ))}
                        </optgroup>
                      )}
                    </select>
                    {item.candidati?.length === 0 && (
                      <div style={{ fontSize: 11, color: '#dc2626', marginTop: 4 }}>
                        Nessun candidato. Crea il fornitore in anagrafica.
                      </div>
                    )}
                  </div>

                  {/* Colonna 3: bottoni azione */}
                  <div style={{ display: 'flex', gap: 8, flexDirection: 'column' }}>
                    <button
                      data-testid={`mappa-btn-${item.paypal_account_id}`}
                      onClick={() =>
                        mappaFornitore(item.paypal_account_id, selectedForn[item.paypal_account_id])
                      }
                      disabled={!selectedForn[item.paypal_account_id]}
                      style={{
                        padding: '10px 16px',
                        minHeight: 40,
                        background: selectedForn[item.paypal_account_id]
                          ? '#0f2744'
                          : '#e2e8f0',
                        color: selectedForn[item.paypal_account_id] ? 'white' : '#9ca3af',
                        border: 'none',
                        borderRadius: 6,
                        cursor: selectedForn[item.paypal_account_id] ? 'pointer' : 'not-allowed',
                        fontWeight: 600,
                        fontSize: 13,
                      }}
                    >
                      🔗 Collega
                    </button>
                    <button
                      data-testid={`crea-forn-btn-${item.paypal_account_id}`}
                      onClick={() => setCreateModal({
                        paypal_account_id: item.paypal_account_id,
                        nome_controparte: item.nome_controparte || '',
                        email_controparte: item.email_controparte || '',
                        importo_totale: item.importo_totale || 0,
                        n_tx: item.n_tx || 0,
                      })}
                      style={{
                        padding: '8px 14px',
                        minHeight: 40,
                        background: 'transparent',
                        color: '#0f2744',
                        border: '1px dashed #0f2744',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontWeight: 600,
                        fontSize: 11,
                      }}
                      title="Crea un nuovo fornitore in anagrafica e mappalo subito"
                    >
                      ➕ Crea nuovo
                    </button>
                    <button
                      data-testid={`cerca-email-btn-${item.paypal_account_id}`}
                      disabled={cercandoEmail === item.paypal_account_id}
                      onClick={() => handleCercaFatturaEmail(item.paypal_account_id)}
                      style={{
                        padding: '8px 14px',
                        minHeight: 40,
                        background: 'transparent',
                        color: '#64748b',
                        border: '1px dashed #9ca3af',
                        borderRadius: 6,
                        cursor: cercandoEmail === item.paypal_account_id ? 'wait' : 'pointer',
                        fontWeight: 600,
                        fontSize: 11,
                        opacity: cercandoEmail === item.paypal_account_id ? 0.6 : 1,
                      }}
                      title="Cerca la fattura nella posta (fornitori esteri: mai su Drive/PEC, esiste solo come PDF via email)"
                    >
                      {cercandoEmail === item.paypal_account_id
                        ? '⏳ Cerco nella posta…'
                        : '📧 Cerca fattura via email'}
                    </button>
                  </div>
                </div>
              ))}

            {mappingData && mappingData.items.length > 0 && (
              <div
                style={{
                  padding: '14px 18px',
                  background: '#f0f9ff',
                  borderTop: '2px solid #0f2744',
                  fontSize: 12,
                  color: '#075985',
                }}
              >
                💡 <strong>Suggerimento</strong>: una volta mappati i fornitori, esegui{' '}
                <code style={{ padding: '1px 4px', background: '#dbeafe', borderRadius: 3 }}>
                  POST /api/paypal-api/riconcilia
                </code>{' '}
                per riconciliare tutte le fatture commerciali PayPal.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modale dettaglio transazione PayPal */}
      <PaypalTransactionDetailModal
        open={!!modalTxId}
        transactionId={modalTxId}
        onClose={() => setModalTxId(null)}
      />

      {/* Modale crea fornitore + mappa */}
      {createModal && (
        <CreaFornitorePaypalModal
          context={createModal}
          onClose={() => setCreateModal(null)}
          onCreated={() => {
            setCreateModal(null);
            loadMapping();
            toast.success('✓ Fornitore creato e mappato');
          }}
        />
      )}
    </PageLayout>
  );
}

// ─── Modale: crea fornitore inline + mappa al paypal_account_id ──────────────
function CreaFornitorePaypalModal({ context, onClose, onCreated }) {
  const [form, setForm] = useState({
    ragione_sociale: context.nome_controparte || '',
    piva: '',
    nazione: 'IT',
    email: context.email_controparte || '',
    metodo_pagamento: 'paypal',
    esclude_magazzino: true,
    note: `Creato da PayPal mapping (${context.n_tx} transazioni, totale €${Math.abs(context.importo_totale).toFixed(2)})`,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    if (!form.ragione_sociale.trim()) {
      setError('La ragione sociale è obbligatoria');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.post('/api/paypal-api/crea-fornitore-e-mappa', {
        paypal_account_id: context.paypal_account_id,
        ...form,
      });
      onCreated();
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Errore sconosciuto');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'white', borderRadius: 10, width: '100%', maxWidth: 560,
          padding: 24, boxShadow: '0 20px 60px rgba(0,0,0,0.3)', position: 'relative',
        }}
      >
        <button
          onClick={onClose}
          aria-label="Chiudi"
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            width: 40,
            height: 40,
            background: 'transparent',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 18,
            color: '#64748b',
            lineHeight: 1,
          }}
        >
          ✕
        </button>
        <div style={{ marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: '#0f2744' }}>
            ➕ Crea fornitore PayPal
          </h2>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
            Account ID: <code>{context.paypal_account_id}</code> · {context.n_tx} transazioni
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Field label="Ragione sociale *" required>
            <input
              type="text"
              value={form.ragione_sociale}
              onChange={e => setForm(f => ({ ...f, ragione_sociale: e.target.value }))}
              autoFocus
              style={inputStyle}
            />
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
            <Field label="P.IVA / VAT">
              <input
                type="text"
                value={form.piva}
                onChange={e => setForm(f => ({ ...f, piva: e.target.value.toUpperCase() }))}
                placeholder="es. IE9952657T"
                style={inputStyle}
              />
            </Field>
            <Field label="Nazione">
              <select
                value={form.nazione}
                onChange={e => setForm(f => ({ ...f, nazione: e.target.value }))}
                style={inputStyle}
              >
                <option value="IT">🇮🇹 Italia</option>
                <option value="IE">🇮🇪 Irlanda</option>
                <option value="NL">🇳🇱 Paesi Bassi</option>
                <option value="DE">🇩🇪 Germania</option>
                <option value="FR">🇫🇷 Francia</option>
                <option value="ES">🇪🇸 Spagna</option>
                <option value="GB">🇬🇧 Regno Unito</option>
                <option value="US">🇺🇸 USA</option>
                <option value="LU">🇱🇺 Lussemburgo</option>
                <option value="OTHER">Altro</option>
              </select>
            </Field>
          </div>

          <Field label="Email">
            <input
              type="email"
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              style={inputStyle}
            />
          </Field>

          <Field label="Note">
            <textarea
              value={form.note}
              onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
              rows={2}
              style={{ ...inputStyle, fontFamily: 'inherit', resize: 'vertical' }}
            />
          </Field>

          <label
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 8, padding: 10,
              background: '#f8fafc', borderRadius: 6, fontSize: 12,
            }}
          >
            <input
              type="checkbox"
              checked={form.esclude_magazzino}
              onChange={e => setForm(f => ({ ...f, esclude_magazzino: e.target.checked }))}
              style={{ marginTop: 2 }}
            />
            <span>
              <strong>Escludi da magazzino</strong> (consigliato per fornitori PayPal: SaaS, servizi cloud, abbonamenti)
            </span>
          </label>
        </div>

        {error && (
          <div
            style={{
              marginTop: 12, padding: 10, background: '#fee2e2',
              border: '1px solid #fca5a5', borderRadius: 6, color: '#b91c1c', fontSize: 13,
            }}
          >
            ⚠️ {error}
          </div>
        )}

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              padding: '8px 16px', minHeight: 40, background: 'white', color: '#64748b',
              border: '1px solid #e2e8f0', borderRadius: 6, cursor: 'pointer', fontSize: 13,
            }}
          >
            Annulla
          </button>
          <button
            onClick={submit}
            disabled={loading || !form.ragione_sociale.trim()}
            style={{
              padding: '8px 18px',
              minHeight: 40,
              background: form.ragione_sociale.trim() && !loading
                ? '#0f2744'
                : '#cbd5e1',
              color: 'white', border: 'none', borderRadius: 6,
              cursor: form.ragione_sociale.trim() && !loading ? 'pointer' : 'not-allowed',
              fontSize: 13, fontWeight: 600,
            }}
          >
            {loading ? '⏳ Creazione…' : '➕ Crea e mappa'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: 'block' }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: '#64748b', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      {children}
    </label>
  );
}

const inputStyle = {
  width: '100%',
  padding: '8px 10px',
  border: '1px solid #e2e8f0',
  borderRadius: 6,
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
};
