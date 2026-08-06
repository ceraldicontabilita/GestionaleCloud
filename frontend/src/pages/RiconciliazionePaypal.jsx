/**
 * RiconciliazionePaypal.jsx
 * Gestione documenti e transazioni PayPal con riconciliazione dei movimenti bancari.
 */
import React, { useState, useEffect, useCallback } from 'react';
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
  Plus,
  Mail,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { PageLayout } from '../components/PageLayout';
import ModalFattura from '../components/ModalFattura';
import PaypalTransactionDetailModal from '../components/PaypalTransactionDetailModal';
import { Button, Badge, Card, Input, Select, StatCard, TableWrap, Table, Th, Td } from '../components/ds';
import { COLORS, SPACING, SHADOWS, BORDER_RADIUS, FONT } from '../lib/utils';
import { useConfirm } from '../components/ui/ConfirmDialog';

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

// Colore del pallino nella lista "Spese per Tipo" del dashboard.
const TIPO_COLORS = {
  express_checkout: COLORS.danger,
  pagamento_utenza: COLORS.warning,
  pagamento_web: COLORS.primary,
  pagamento: COLORS.danger,
  accredito: COLORS.success,
  bonifico_paypal: COLORS.info,
  rimborso: COLORS.success,
  conversione_valuta: COLORS.textMuted,
  prelievo: COLORS.accent,
  altro: COLORS.textMuted,
};

// Variante <Badge> corrispondente, usata per la pillola "Tipo" in tabella.
const TIPO_VARIANT = {
  express_checkout: 'danger',
  pagamento_utenza: 'warning',
  pagamento_web: 'primary',
  pagamento: 'danger',
  accredito: 'success',
  bonifico_paypal: 'info',
  rimborso: 'success',
  conversione_valuta: 'neutral',
  prelievo: 'accent',
  altro: 'neutral',
};

export default function RiconciliazionePaypal() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const confirm = useConfirm();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [dashboard, setDashboard] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [report, setReport] = useState(null);
  const [paypalSources, setPaypalSources] = useState([]);
  const [bankMovements, setBankMovements] = useState([]);
  const [bankSummary, setBankSummary] = useState(null);
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
  const [invoiceStatus, setInvoiceStatus] = useState('tutti');
  const [modalTxId, setModalTxId] = useState(null); // transaction_id aperto nel modale
  const [fatturaView, setFatturaView] = useState(null);
  const [mappingData, setMappingData] = useState(null);
  const [mappingLoading, setMappingLoading] = useState(false);
  const [selectedForn, setSelectedForn] = useState({}); // {paypal_account_id: fornitore_id}
  const [createModal, setCreateModal] = useState(null); // {paypal_account_id, nome_controparte, ...} | null
  const [syncMesi, setSyncMesi] = useState(3);
  const [syncing, setSyncing] = useState(false);
  const [apiStatus, setApiStatus] = useState(null);
  const [searchBank, setSearchBank] = useState('');
  const [bankStatus, setBankStatus] = useState('tutti');
  const [bankDirection, setBankDirection] = useState('tutte');
  const [reconcilingBank, setReconcilingBank] = useState(false);

  const loadApiStatus = useCallback(async () => {
    try {
      const res = await api.get('/api/paypal-api/status');
      setApiStatus(res.data);
    } catch (e) {
      console.error(e);
      setLoadError(true);
    }
  }, []);

  const loadDashboard = useCallback(async () => {
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-statements/dashboard${params}`);
      setDashboard(res.data);
    } catch (e) {
      console.error(e);
      setLoadError(true);
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
      setLoadError(true);
    }
  }, [annoFiltro, soloPagamenti]);

  const loadReport = useCallback(async () => {
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-statements/report${params}`);
      setReport(res.data);
    } catch (e) {
      console.error(e);
      setLoadError(true);
    }
  }, [annoFiltro]);

  const loadStatements = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: '50' });
      if (annoFiltro) params.append('anno', annoFiltro);
      const res = await api.get(`/api/paypal-statements/statements?${params}`);
      setPaypalSources(res.data.fonti || res.data.statements || []);
    } catch (e) {
      console.error(e);
      setLoadError(true);
    }
  }, [annoFiltro]);

  const loadBankMovements = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (annoFiltro) params.append('anno', annoFiltro);
      params.append('limit', '5000');
      const res = await api.get(`/api/paypal-statements/bank-movements?${params}`);
      setBankMovements(res.data.movimenti || []);
      setBankSummary(res.data || null);
    } catch (e) {
      console.error(e);
      setLoadError(true);
    }
  }, [annoFiltro]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    await Promise.all([
      loadDashboard(), loadTransactions(), loadReport(), loadStatements(),
      loadBankMovements(), loadApiStatus(),
    ]);
    setLoading(false);
  }, [loadDashboard, loadTransactions, loadReport, loadStatements, loadBankMovements, loadApiStatus]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const loadMapping = useCallback(async () => {
    setMappingLoading(true);
    try {
      const params = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/paypal-api/account-ids-non-mappati${params}`);
      setMappingData(res.data);
      // Pre-seleziona solo una denominazione esatta e univoca. La conferma
      // resta comunque esplicita: il nome non sostituisce P.IVA/CF.
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
    const ok = await confirm({
      title: 'Mappatura automatica',
      message: `Mappare automaticamente ${certi.length} fornitori con match certo?`,
      confirmText: 'Mappa tutti',
    });
    if (!ok) return;
    let mappati = 0;
    let falliti = 0;
    for (const item of certi) {
      try {
        await api.post('/api/paypal-api/mappa-fornitore', {
          paypal_account_id: item.paypal_account_id,
          fornitore_id: item.suggested_fornitore_id,
        });
        mappati++;
      } catch {
        falliti++;
      }
    }
    // Non spacciare per successo un batch fallito: se nessuna mappatura è
    // andata a buon fine è un errore, non "0 da mappare".
    if (mappati === 0 && falliti > 0) {
      toast.error(`Mappatura fallita su tutti i ${falliti} fornitori (errore del servizio).`);
    } else if (falliti > 0) {
      toast.error(`Mappati ${mappati}/${certi.length}; ${falliti} falliti per errore del servizio.`);
    } else {
      toast.success(`Mappati ${mappati}/${certi.length} fornitori`);
    }
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
      toast.success(`Mappato: ${res.data.fornitore}`);
      loadMapping();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const [cercandoEmail, setCercandoEmail] = useState(null); // paypal_account_id in corso

  const handleCercaFatturaEmail = async paypalAccountId => {
    setCercandoEmail(paypalAccountId);
    try {
      const res = await api.post(
        `/api/paypal-api/account/${encodeURIComponent(paypalAccountId)}/cerca-fattura-email`
      );
      const r = res.data || {};
      if (r.ok === false) {
        toast.error(`${r.errore || 'Ricerca email non disponibile'}. ${r.azione || ''}`.trim());
        return;
      }
      const trovati = r.stats?.new_documents ?? 0;
      if (trovati > 0) {
        toast.success(
          `Trovati ${trovati} documenti in posta per "${r.cercato_per}" — vai su Documenti per vederli`
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
    if (
      invoiceStatus !== 'tutti' &&
      tx.stato_collegamento_fattura !== invoiceStatus
    ) return false;
    if (!searchTx) return true;
    const s = searchTx.toLowerCase();
    return (
      (tx.nome_controparte || '').toLowerCase().includes(s) ||
      (tx.descrizione || '').toLowerCase().includes(s) ||
      (tx.email_controparte || '').toLowerCase().includes(s)
    );
  });

  const filteredBankMovements = bankMovements.filter(mov => {
    if (bankStatus === 'riconciliati' && !mov.riconciliato_paypal) return false;
    if (bankStatus === 'da_associare' && mov.riconciliato_paypal) return false;
    if (bankDirection === 'uscite' && mov.importo >= 0) return false;
    if (bankDirection === 'entrate' && mov.importo <= 0) return false;
    if (!searchBank) return true;
    const needle = searchBank.toLowerCase();
    return `${mov.descrizione || ''} ${mov.paypal_transaction_id || ''} ${mov.id || ''}`
      .toLowerCase()
      .includes(needle);
  });

  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          display: 'flex',
          gap: 10,
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
        }}
      >
        <RefreshCw
          style={{ width: 32, height: 32, animation: 'spin 1s linear infinite', color: COLORS.primary }}
        />
        <span>Caricamento dati PayPal…</span>
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
      label: 'Movimenti Banca',
      icon: <Link2 size={16} />,
      count: dashboard?.movimenti_banca_paypal,
    },
    {
      id: 'documenti',
      label: 'Fonti PayPal',
      icon: <FileText size={16} />,
      count: paypalSources.length,
    },
    {
      id: 'mapping',
      label: 'Mapping Fornitori',
      icon: <Link2 size={16} />,
      count: mappingData?.totale_non_mappati,
    },
  ];

  return (
    <PageLayout>
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        {loadError && (
          <div
            role="alert"
            style={{
              background: COLORS.dangerLight, color: COLORS.danger,
              border: `1px solid ${COLORS.danger}`, borderRadius: BORDER_RADIUS.md,
              padding: '10px 14px', marginBottom: 12, fontSize: 14,
            }}
          >
            ⚠️ Alcuni dati PayPal non sono stati caricati per un errore del servizio
            (i valori mostrati potrebbero essere incompleti). Riprova con «Aggiorna».
          </div>
        )}
        {dashboard?.anomalia_fonti_mancanti && (
          <div
            role="alert"
            style={{
              background: COLORS.warningLight, color: COLORS.warning,
              border: `1px solid ${COLORS.warning}`, borderRadius: BORDER_RADIUS.md,
              padding: '10px 14px', marginBottom: 12, fontSize: 14,
            }}
          >
            <strong>Fonte PayPal mancante:</strong> in banca risultano{' '}
            {dashboard.movimenti_banca_senza_sorgente_paypal} movimenti PayPal per {annoFiltro},
            ma non è presente alcuna transazione PayPal da riconciliare. Importa il documento da
            “Documenti” oppure configura la sincronizzazione API.
          </div>
        )}
        {apiStatus && !apiStatus.api_configurata && (
          <div
            role="status"
            style={{
              background: COLORS.infoLight, color: COLORS.info,
              border: `1px solid ${COLORS.info}`, borderRadius: BORDER_RADIUS.md,
              padding: '10px 14px', marginBottom: 12, fontSize: 14,
            }}
          >
            La sincronizzazione automatica PayPal non è configurata. Nessuna credenziale viene
            mostrata: per ora usa l'importazione controllata da “Documenti”.
          </div>
        )}
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: SPACING.md,
            marginBottom: SPACING.xl,
            padding: '16px 20px',
            background: COLORS.primary,
            borderRadius: BORDER_RADIUS.md,
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
                fontFamily: FONT.family,
                color: 'white',
              }}
            >
              <CreditCard size={24} /> Gestione PayPal
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, opacity: 0.85 }}>
              {dashboard?.total_statements || 0} documenti PayPal ·{' '}
              {dashboard?.total_transactions || 0} transazioni ·{' '}
              {formatEuro(Math.abs(dashboard?.totale_speso || 0))} spesi
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <Button
              variant="secondary"
              size="sm"
              iconLeft={<Download size={14} />}
              onClick={() => navigate('/documenti/import')}
              style={{
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                borderColor: 'rgba(255,255,255,0.3)',
              }}
            >
              Importa documenti
            </Button>
            <Select
              value={syncMesi}
              onChange={e => setSyncMesi(parseInt(e.target.value))}
              style={{
                background: 'rgba(255,255,255,0.15)',
                color: 'white',
                borderColor: 'rgba(255,255,255,0.3)',
              }}
            >
              <option value={1} style={{ color: COLORS.text }}>
                Ultimo mese
              </option>
              <option value={3} style={{ color: COLORS.text }}>
                Ultimi 3 mesi
              </option>
              <option value={6} style={{ color: COLORS.text }}>
                Ultimi 6 mesi
              </option>
              <option value={12} style={{ color: COLORS.text }}>
                Ultimo anno
              </option>
            </Select>
            <Button
              data-testid="sync-paypal-api-btn"
              disabled={syncing || apiStatus?.api_configurata === false}
              iconLeft={
                syncing ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : null
              }
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
                    `Sync OK — ${r.total || 0} transazioni (${r.enriched || 0} arricchite), riconciliazione in corso…`
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
                    toast.success(`Riconciliazione OK — ${fatt} transazioni associate a fatture`);
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
                background: 'rgba(184, 134, 11, 0.35)',
                color: 'white',
                borderColor: 'rgba(184, 134, 11, 0.7)',
              }}
              title={apiStatus?.api_configurata === false
                ? 'Configura prima le credenziali PayPal sul server'
                : 'Sincronizza le transazioni PayPal via API e le riconcilia con fatture/banca'}
            >
              {syncing ? 'Sync…' : 'Sync PayPal API'}
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: SPACING.md,
            marginBottom: SPACING.xl,
          }}
        >
          <StatCard
            icon={<FileText size={16} />}
            label="Documenti PayPal"
            value={dashboard?.total_statements || 0}
            accent="primary"
          />
          <StatCard
            icon={<CreditCard size={16} />}
            label="Transazioni"
            value={dashboard?.total_transactions || 0}
            accent="primary"
          />
          <StatCard
            icon={<TrendingDown size={16} />}
            label="Totale Speso"
            value={formatEuro(Math.abs(dashboard?.totale_speso || 0))}
            accent="danger"
          />
          <StatCard
            icon={<CheckCircle2 size={16} />}
            label="Riconciliati Banca"
            value={dashboard?.riconciliati_banca || 0}
            accent="success"
          />
          <StatCard
            icon={<Link2 size={16} />}
            label="Movimenti Banca"
            value={dashboard?.movimenti_banca_paypal || 0}
            accent="info"
          />
        </div>

        {/* Tabs */}
        <div
          style={{
            display: 'flex',
            gap: 4,
            flexWrap: 'wrap',
            borderBottom: `2px solid ${COLORS.border}`,
            marginBottom: 16,
          }}
        >
          {tabs.map(t => (
            <Button
              key={t.id}
              variant={activeTab === t.id ? 'primary' : 'ghost'}
              size="sm"
              iconLeft={t.icon}
              onClick={() => setActiveTab(t.id)}
              style={{ borderRadius: '6px 6px 0 0', border: 'none', boxShadow: 'none' }}
            >
              {t.label}
              {t.count !== undefined && (
                <Badge
                  variant="neutral"
                  style={{
                    marginLeft: 4,
                    background: activeTab === t.id ? 'rgba(255,255,255,0.2)' : COLORS.border,
                    color: activeTab === t.id ? '#fff' : COLORS.textMuted,
                  }}
                >
                  {t.count}
                </Badge>
              )}
            </Button>
          ))}
        </div>

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && dashboard && (
          <div
            style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 16 }}
          >
            {/* Top Fornitori */}
            <Card title="Top Fornitori PayPal">
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
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
                    cursor: 'pointer',
                  }}
                  title={`Vedi le transazioni di ${f.nome}`}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{f.nome}</div>
                    <div style={{ fontSize: 11, color: COLORS.textSubtle }}>{f.count} transazioni</div>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.danger }}>
                    {formatEuro(Math.abs(f.totale))}
                  </div>
                </div>
              ))}
              {(!dashboard.top_fornitori || dashboard.top_fornitori.length === 0) && (
                <p style={{ color: COLORS.textSubtle, fontSize: 13, textAlign: 'center', padding: 20 }}>
                  Nessun dato. Importa i documenti da “Documenti” o sincronizza PayPal API.
                </p>
              )}
            </Card>

            {/* Per Tipo */}
            <Card title="Spese per Tipo">
              {(dashboard.per_tipo || []).map(t => (
                <div
                  key={t.tipo}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: BORDER_RADIUS.full,
                        background: TIPO_COLORS[t.tipo] || COLORS.textSubtle,
                      }}
                    />
                    <span style={{ fontSize: 13 }}>{TIPO_LABELS[t.tipo] || t.tipo}</span>
                  </div>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.gray[700] }}>
                      {formatEuro(Math.abs(t.totale))}
                    </span>
                    <span style={{ fontSize: 11, color: COLORS.textSubtle, marginLeft: 8 }}>
                      ({t.count})
                    </span>
                  </div>
                </div>
              ))}
            </Card>

            {/* Report Mensile */}
            {report && report.per_mese && report.per_mese.length > 0 && (
              <Card title="Andamento Mensile" style={{ gridColumn: '1 / -1' }}>
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
                              background: COLORS.primary,
                              borderRadius: '4px 4px 0 0',
                              minHeight: 4,
                            }}
                          />
                        </div>
                        <div
                          style={{ fontSize: 11, fontWeight: 600, color: COLORS.gray[700], marginTop: 4 }}
                        >
                          {formatEuro(Math.abs(m.totale))}
                        </div>
                        <div style={{ fontSize: 10, color: COLORS.textSubtle }}>{m.mese}</div>
                        <div style={{ fontSize: 10, color: COLORS.textSubtle }}>{m.count} tx</div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}
          </div>
        )}

        {/* Transazioni Tab */}
        {activeTab === 'transazioni' && (
          <Card bodyStyle={{ padding: 0 }}>
            <div
              style={{
                padding: '12px 16px',
                borderBottom: `1px solid ${COLORS.border}`,
                display: 'flex',
                gap: 12,
                alignItems: 'center',
                flexWrap: 'wrap',
              }}
            >
              <div style={{ flex: 1, minWidth: 220 }}>
                <Input
                  iconLeft={<Search size={14} />}
                  value={searchTx}
                  onChange={e => setSearchTx(e.target.value)}
                  placeholder="Cerca fornitore, descrizione..."
                />
              </div>
              <Select
                aria-label="Stato collegamento fattura"
                value={invoiceStatus}
                onChange={e => setInvoiceStatus(e.target.value)}
                style={{ minWidth: 190 }}
              >
                <option value="tutti">Tutte le fatture</option>
                <option value="associata_validata">Associate e validate</option>
                <option value="non_associata">Senza fattura</option>
                <option value="da_rivalidare">Da rivalidare</option>
              </Select>
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
              <span style={{ fontSize: 12, color: COLORS.textMuted }}>{filteredTx.length} risultati</span>
            </div>
            {isMobile ? (
              <div
                data-testid="paypal-transaction-cards"
                style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12 }}
              >
                {filteredTx.map(tx => (
                  <button
                    type="button"
                    key={tx.id || tx.transaction_id || tx.data + tx.importo}
                    onClick={() => (tx.transaction_id || tx.id) && setModalTxId(tx.transaction_id || tx.id)}
                    style={{
                      appearance: 'none',
                      width: '100%',
                      textAlign: 'left',
                      background: COLORS.card,
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      padding: 12,
                      color: COLORS.text,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                      <strong>{tx.nome_controparte || 'Controparte non indicata'}</strong>
                      <span style={{ color: tx.lordo < 0 ? COLORS.danger : COLORS.success, fontWeight: 700 }}>
                        {formatEuro(tx.importo_eur ?? tx.lordo)}
                      </span>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12, color: COLORS.textMuted }}>
                      {formatDate(tx.data)} · {TIPO_LABELS[tx.tipo] || tx.tipo || 'Operazione'}
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12 }}>{tx.descrizione || 'Nessuna descrizione'}</div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                      <Badge variant={tx.riconciliato_banca ? 'success' : 'neutral'}>
                        {tx.riconciliato_banca ? 'Banca collegata' : 'Banca da associare'}
                      </Badge>
                      <Badge
                        variant={
                          tx.stato_collegamento_fattura === 'associata_validata'
                            ? 'success'
                            : tx.stato_collegamento_fattura === 'da_rivalidare'
                              ? 'warning'
                              : 'neutral'
                        }
                      >
                        {tx.stato_collegamento_fattura === 'associata_validata'
                          ? 'Fattura validata'
                          : tx.stato_collegamento_fattura === 'da_rivalidare'
                            ? 'Fattura da rivalidare'
                            : 'Fattura mancante'}
                      </Badge>
                    </div>
                  </button>
                ))}
                {filteredTx.length === 0 && (
                  <div style={{ padding: 28, textAlign: 'center', color: COLORS.textSubtle }}>
                    {dashboard?.total_transactions === 0
                      ? 'Nessuna transazione. Importa da “Documenti” o sincronizza PayPal API.'
                      : 'Nessun risultato per il filtro.'}
                  </div>
                )}
              </div>
            ) : (
            <TableWrap data-testid="paypal-transactions-table" style={{ maxHeight: 600, overflowY: 'auto', border: 'none', borderRadius: 0 }}>
              <Table>
                <thead>
                  <tr style={{ position: 'sticky', top: 0 }}>
                    <Th>Data</Th>
                    <Th>Tipo</Th>
                    <Th>Descrizione</Th>
                    <Th>Controparte</Th>
                    <Th align="right">Importo</Th>
                    <Th align="center">Banca</Th>
                    <Th align="center">Fattura</Th>
                    <Th>ID</Th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTx.map(tx => (
                    <tr
                      key={tx.id || tx.transaction_id || tx.data + tx.importo}
                      onClick={() => (tx.transaction_id || tx.id) && setModalTxId(tx.transaction_id || tx.id)}
                      style={{
                        cursor: (tx.transaction_id || tx.id) ? 'pointer' : 'default',
                        transition: 'background 120ms',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = COLORS.bgAlt)}
                      onMouseLeave={e => (e.currentTarget.style.background = '')}
                      title="Clicca per vedere il dettaglio completo"
                    >
                      <Td style={{ whiteSpace: 'nowrap' }}>{formatDate(tx.data)}</Td>
                      <Td>
                        <Badge variant={TIPO_VARIANT[tx.tipo] || 'neutral'}>
                          {TIPO_LABELS[tx.tipo] || tx.tipo}
                        </Badge>
                      </Td>
                      <Td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {tx.descrizione}
                      </Td>
                      <Td>
                        <div style={{ fontWeight: 500 }}>{tx.nome_controparte || '-'}</div>
                        {tx.email_controparte && (
                          <div style={{ fontSize: 10, color: COLORS.textSubtle }}>
                            {tx.email_controparte}
                          </div>
                        )}
                      </Td>
                      <Td
                        align="right"
                        mono
                        style={{ fontWeight: 600, color: tx.lordo < 0 ? COLORS.danger : COLORS.success }}
                      >
                        {/* Pagamento in valuta estera: mostra l'EURO reale
                            (dalla conversione T0200 accoppiata dal backend)
                            e la valuta originale come dettaglio */}
                        {tx.importo_eur != null ? (
                          <>
                            {formatEuro(tx.importo_eur)}
                            <div style={{ fontSize: 10, color: COLORS.textSubtle, fontWeight: 400 }}>
                              {Math.abs(tx.importo_valuta).toFixed(2)} {tx.valuta_originale}
                            </div>
                          </>
                        ) : (
                          <>
                            {formatEuro(tx.lordo)}
                            {tx.is_conversione && (
                              <div style={{ fontSize: 10, color: COLORS.textSubtle, fontWeight: 400 }}>
                                conversione valuta
                              </div>
                            )}
                          </>
                        )}
                      </Td>
                      <Td align="center">
                        {tx.riconciliato_banca ? (
                          <CheckCircle2 size={16} style={{ color: COLORS.success }} />
                        ) : (
                          <span style={{ color: COLORS.borderDark }}>—</span>
                        )}
                      </Td>
                      <Td align="center" onClick={e => e.stopPropagation()}>
                        {tx.stato_collegamento_fattura === 'associata_validata' ? (
                          <Badge
                            variant="info"
                            onClick={() =>
                              setFatturaView({
                                id: tx.fattura_associata.fattura_id,
                                numero:
                                  tx.fattura_associata.numero || tx.fattura_associata.fornitore,
                              })
                            }
                            title={`Fatt. ${tx.fattura_associata.numero || ''} — ${tx.fattura_associata.fornitore || ''} — numero, importo e fornitore validati`}
                            style={{ cursor: 'pointer' }}
                          >
                            Vedi fattura
                          </Badge>
                        ) : tx.stato_collegamento_fattura === 'da_rivalidare' ? (
                          <Badge
                            variant="warning"
                            title="Collegamento storico conservato come traccia, ma non valido finché numero fattura, importo al centesimo e fornitore non sono tutti provati"
                          >
                            Da rivalidare
                          </Badge>
                        ) : tx.gmail_associata?.gmail_link ? (
                          <a
                            href={tx.gmail_associata.gmail_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={`Email trovata su Gmail: ${tx.gmail_associata.subject || ''} — apri in Gmail`}
                            style={{ color: COLORS.info, display: 'inline-flex' }}
                          >
                            <Mail size={15} />
                          </a>
                        ) : (
                          <span
                            style={{ color: COLORS.borderDark }}
                            title="Ricerca automatica in corso (fatture + Gmail ogni 30 min)"
                          >
                            —
                          </span>
                        )}
                      </Td>
                      <Td
                        mono
                        style={{
                          fontSize: 10,
                          color: COLORS.textSubtle,
                          maxWidth: 140,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {tx.transaction_id || '-'}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              {filteredTx.length === 0 && (
                <div style={{ padding: 40, textAlign: 'center', color: COLORS.textSubtle }}>
                  {dashboard?.total_transactions === 0
                    ? 'Nessuna transazione. Importa da “Documenti” o sincronizza PayPal API.'
                    : 'Nessun risultato per il filtro.'}
                </div>
              )}
            </TableWrap>
            )}
          </Card>
        )}

        {/* Report Tab */}
        {activeTab === 'report' && report && (
          <div>
            <Card
              style={{ marginBottom: 16 }}
              title={`Report Spese PayPal ${annoFiltro || 'Totale'}`}
              actions={
                <div style={{ fontSize: 20, fontWeight: 'bold', color: COLORS.danger, fontFamily: FONT.mono }}>
                  {formatEuro(Math.abs(report.totale_speso))}
                </div>
              }
            >
              <div style={{ fontSize: 13, color: COLORS.textMuted }}>
                {report.totale_transazioni} pagamenti
              </div>
            </Card>

            {/* Per Fornitore */}
            <Card title="Dettaglio per Fornitore" bodyStyle={{ padding: 0 }}>
              <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                {(report.per_fornitore || []).map(f => (
                  <details key={f.nome || f.id} style={{ borderBottom: `1px solid ${COLORS.gray[100]}` }}>
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
                          <span style={{ fontSize: 11, color: COLORS.textSubtle, marginLeft: 8 }}>
                            {f.email}
                          </span>
                        )}
                      </div>
                      <div>
                        <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.danger }}>
                          {formatEuro(Math.abs(f.totale))}
                        </span>
                        <span style={{ fontSize: 11, color: COLORS.textSubtle, marginLeft: 8 }}>
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
                            onMouseEnter={e => { if (txId) e.currentTarget.style.background = COLORS.gray[100]; }}
                            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              padding: '6px 8px',
                              fontSize: 12,
                              color: COLORS.textMuted,
                              cursor: txId ? 'pointer' : 'default',
                              borderRadius: BORDER_RADIUS.sm,
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
            </Card>
          </div>
        )}

        {/* Movimenti bancari PayPal */}
        {activeTab === 'estratti' && (
          <Card
            title={`Movimenti bancari PayPal (${filteredBankMovements.length})`}
            bodyStyle={{ padding: 0 }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : 'minmax(240px, 1fr) 180px 160px auto',
                gap: 8,
                padding: 12,
                borderBottom: `1px solid ${COLORS.border}`,
              }}
            >
              <Input
                value={searchBank}
                onChange={e => setSearchBank(e.target.value)}
                placeholder="Cerca causale, ID PayPal o movimento…"
                iconLeft={<Search size={15} />}
                aria-label="Cerca nei movimenti bancari PayPal"
              />
              <Select
                value={bankStatus}
                onChange={e => setBankStatus(e.target.value)}
                aria-label="Filtra per stato riconciliazione"
              >
                <option value="tutti">Tutti gli stati</option>
                <option value="da_associare">Da associare</option>
                <option value="riconciliati">Riconciliati</option>
              </Select>
              <Select
                value={bankDirection}
                onChange={e => setBankDirection(e.target.value)}
                aria-label="Filtra per direzione del movimento"
              >
                <option value="tutte">Entrate e uscite</option>
                <option value="entrate">Solo entrate</option>
                <option value="uscite">Solo uscite</option>
              </Select>
              <Button
                disabled={reconcilingBank}
                iconLeft={
                  <RefreshCw
                    size={14}
                    style={reconcilingBank ? { animation: 'spin 1s linear infinite' } : undefined}
                  />
                }
                onClick={async () => {
                  setReconcilingBank(true);
                  try {
                    const previewRes = await api.post(
                      `/api/paypal-statements/riconcilia-banca?anno=${annoFiltro}&conferma=false`
                    );
                    const preview = previewRes.data || {};
                    if ((preview.proposte || 0) === 0) {
                      toast.info(
                        `Nessun match univoco da applicare; ${preview.ambigui || 0} casi restano da verificare`
                      );
                      return;
                    }
                    const ok = await confirm({
                      title: 'Conferma riconciliazione PayPal',
                      message:
                        `${preview.proposte} abbinamenti biunivoci per ${formatEuro(preview.importo_proposto)}. ` +
                        `${preview.ambigui || 0} casi ambigui resteranno sospesi. Applicare?`,
                      confirmText: 'Applica abbinamenti',
                    });
                    if (!ok) return;
                    const res = await api.post(
                      `/api/paypal-statements/riconcilia-banca?anno=${annoFiltro}&conferma=true`
                    );
                    const r = res.data || {};
                    toast.success(
                      `${r.riconciliati || 0} movimenti riconciliati; ` +
                        `${r.ambigui || 0} lasciati da verificare`
                    );
                    await Promise.all([loadBankMovements(), loadTransactions(), loadDashboard()]);
                  } catch (err) {
                    toast.error(
                      'Riconciliazione non completata: ' +
                        (err.response?.data?.detail || err.message)
                    );
                  } finally {
                    setReconcilingBank(false);
                  }
                }}
              >
                {reconcilingBank ? 'Verifica abbinamenti…' : 'Verifica e riconcilia'}
              </Button>
            </div>
            <div
              style={{
                display: 'flex',
                gap: 14,
                flexWrap: 'wrap',
                padding: '9px 12px',
                color: COLORS.textMuted,
                fontSize: 12,
                borderBottom: `1px solid ${COLORS.border}`,
              }}
            >
              <span>Totale banca: <b>{bankSummary?.totale_banca_paypal || 0}</b></span>
              <span>Riconciliati: <b>{bankSummary?.riconciliati || 0}</b></span>
              <span>Da associare: <b>{bankSummary?.da_associare || 0}</b></span>
              <span>Importo e data da soli non confermano casi ambigui.</span>
            </div>
            {isMobile ? (
              <div
                data-testid="paypal-bank-cards"
                style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12 }}
              >
                {filteredBankMovements.map(mov => (
                  <article
                    key={mov.id}
                    style={{
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      padding: 12,
                      background: COLORS.card,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                      <strong>{formatDate(mov.data)}</strong>
                      <span
                        style={{
                          color: mov.importo < 0 ? COLORS.danger : COLORS.success,
                          fontFamily: FONT.mono,
                          fontWeight: 700,
                        }}
                      >
                        {formatEuro(mov.importo)}
                      </span>
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13 }}>{mov.descrizione || '—'}</div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
                      <Badge variant={mov.importo < 0 ? 'danger' : 'success'}>
                        {mov.importo < 0 ? 'Uscita' : 'Entrata'}
                      </Badge>
                      <Badge variant={mov.riconciliato_paypal ? 'success' : 'warning'}>
                        {mov.riconciliato_paypal ? 'Riconciliato' : 'Da associare'}
                      </Badge>
                    </div>
                    {mov.paypal_transaction_id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        style={{ marginTop: 8 }}
                        onClick={() => {
                          setSearchTx(mov.paypal_transaction_id);
                          setActiveTab('transazioni');
                        }}
                      >
                        Apri transazione {mov.paypal_transaction_id}
                      </Button>
                    )}
                  </article>
                ))}
              </div>
            ) : (
            <TableWrap data-testid="paypal-bank-table" style={{ border: 'none', borderRadius: 0 }}>
              <Table>
                <thead>
                  <tr>
                    <Th>Data</Th>
                    <Th>Causale banca</Th>
                    <Th>Direzione</Th>
                    <Th align="right">Importo</Th>
                    <Th>Stato</Th>
                    <Th>Transazione PayPal</Th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBankMovements.map(mov => (
                    <tr key={mov.id}>
                      <Td style={{ whiteSpace: 'nowrap' }}>{formatDate(mov.data)}</Td>
                      <Td style={{ minWidth: 260 }}>{mov.descrizione || '—'}</Td>
                      <Td>
                        <Badge variant={mov.importo < 0 ? 'danger' : 'success'}>
                          {mov.importo < 0 ? 'Uscita' : 'Entrata'}
                        </Badge>
                      </Td>
                      <Td
                        align="right"
                        mono
                        style={{ color: mov.importo < 0 ? COLORS.danger : COLORS.success }}
                      >
                        {formatEuro(mov.importo)}
                      </Td>
                      <Td>
                        <Badge variant={mov.riconciliato_paypal ? 'success' : 'warning'}>
                          {mov.riconciliato_paypal ? 'Riconciliato' : 'Da associare'}
                        </Badge>
                      </Td>
                      <Td>
                        {mov.paypal_transaction_id ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSearchTx(mov.paypal_transaction_id);
                              setActiveTab('transazioni');
                            }}
                          >
                            {mov.paypal_transaction_id}
                          </Button>
                        ) : '—'}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
            )}
            {filteredBankMovements.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', color: COLORS.textSubtle }}>
                Nessun movimento bancario PayPal con i filtri selezionati.
              </div>
            )}
          </Card>
        )}

        {/* Fonti PayPal: API e documenti restano distinti */}
        {activeTab === 'documenti' && (
          <Card title={`Fonti PayPal (${paypalSources.length})`} bodyStyle={{ padding: 0 }}>
            <div
              style={{
                padding: '12px 16px',
                color: COLORS.textMuted,
                fontSize: 12,
                borderBottom: `1px solid ${COLORS.border}`,
              }}
            >
              I periodi sincronizzati via API sono dati strutturati, non PDF. I documenti
              importati restano indicati separatamente con il relativo nome file.
            </div>
            {isMobile ? (
              <div
                data-testid="paypal-source-cards"
                style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12 }}
              >
                {paypalSources.map(s => (
                  <article
                    key={s.id || s.statement_id}
                    style={{
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      padding: 12,
                      background: COLORS.card,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                      <Badge
                        variant={
                          s.source_type === 'api'
                            ? 'success'
                            : s.tipo_documento === 'CSR'
                              ? 'warning'
                              : 'info'
                        }
                      >
                        {s.source_type === 'api' ? 'PayPal API' : s.tipo_documento}
                      </Badge>
                      <strong>
                        {s.riepilogo?.pagamenti_inviati == null
                          ? '—'
                          : formatEuro(s.riepilogo.pagamenti_inviati)}
                      </strong>
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13 }}>
                      {formatDate(s.periodo_inizio)} — {formatDate(s.periodo_fine)}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 12, color: COLORS.textMuted }}>
                      {s.totale_transazioni || 0} operazioni · {s.totale_pagamenti ?? '—'} pagamenti
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12, color: COLORS.textSubtle }}>
                      {s.documento_presente ? s.file_name : 'Nessun file: fonte API'}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
            <TableWrap data-testid="paypal-source-table" style={{ border: 'none', borderRadius: 0 }}>
              <Table>
                <thead>
                  <tr>
                    <Th>Fonte</Th>
                    <Th>Periodo</Th>
                    <Th align="center">Operazioni</Th>
                    <Th align="center">Pagamenti</Th>
                    <Th align="right">Pag. inviati</Th>
                    <Th align="right">Depositi</Th>
                    <Th align="right">Saldo finale</Th>
                    <Th>Documento</Th>
                  </tr>
                </thead>
                <tbody>
                  {paypalSources.map(s => (
                    <tr key={s.id || s.statement_id}>
                      <Td>
                        <Badge
                          variant={
                            s.source_type === 'api'
                              ? 'success'
                              : s.tipo_documento === 'CSR'
                                ? 'warning'
                                : 'info'
                          }
                        >
                          {s.source_type === 'api' ? 'PayPal API' : s.tipo_documento}
                        </Badge>
                      </Td>
                      <Td style={{ fontWeight: 500 }}>
                        {formatDate(s.periodo_inizio)} — {formatDate(s.periodo_fine)}
                      </Td>
                      <Td align="center">{s.totale_transazioni}</Td>
                      <Td align="center">{s.totale_pagamenti ?? '—'}</Td>
                      <Td align="right" mono style={{ color: COLORS.danger }}>
                        {s.riepilogo?.pagamenti_inviati == null
                          ? '—'
                          : formatEuro(s.riepilogo.pagamenti_inviati)}
                      </Td>
                      <Td align="right" mono style={{ color: COLORS.success }}>
                        {s.riepilogo?.depositi_accrediti == null
                          ? '—'
                          : formatEuro(s.riepilogo.depositi_accrediti)}
                      </Td>
                      <Td align="right" mono>
                        {s.riepilogo?.saldo_finale == null
                          ? '—'
                          : formatEuro(s.riepilogo.saldo_finale)}
                      </Td>
                      <Td style={{ fontSize: 11, color: COLORS.textSubtle }}>
                        {s.documento_presente ? s.file_name : 'Nessun file: fonte API'}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
            )}
            {paypalSources.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', color: COLORS.textSubtle }}>
                Nessuna fonte PayPal disponibile per l'anno selezionato.
              </div>
            )}
          </Card>
        )}

        {/* Mapping Fornitori Tab */}
        {activeTab === 'mapping' && (
          <div
            data-testid="mapping-fornitori-panel"
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.md,
              border: `1px solid ${COLORS.border}`,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '14px 18px',
                background: COLORS.bgAlt,
                borderBottom: `1px solid ${COLORS.border}`,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 10,
              }}
            >
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Link2 size={15} /> Account PayPal da mappare ai Fornitori
                  {mappingData?.totale_non_mappati !== undefined && (
                    <Badge variant="warning" style={{ marginLeft: 4 }}>
                      {mappingData.totale_non_mappati} non mappati
                    </Badge>
                  )}
                </div>
                <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                  Associa l'ID PayPal del beneficiario al fornitore corretto per abilitare la
                  riconciliazione automatica delle fatture.
                </div>
              </div>
              <Button
                data-testid="reload-mapping-btn"
                onClick={loadMapping}
                disabled={mappingLoading}
                variant="primary"
                iconLeft={
                  <RefreshCw
                    size={14}
                    style={mappingLoading ? { animation: 'spin 1s linear infinite' } : undefined}
                  />
                }
              >
                {mappingLoading ? 'Caricamento...' : 'Ricarica'}
              </Button>
            </div>

            {/* Banner azione massiva match certi */}
            {mappingData && mappingData.items.some(i => i.suggested_fornitore_id) && (
              <div
                style={{
                  padding: '12px 18px',
                  background: COLORS.successLight,
                  borderBottom: `1px solid ${COLORS.success}`,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 12,
                }}
              >
                <div style={{ fontSize: 13, color: COLORS.success }}>
                  Proposte da confermare{' '}
                  <strong>
                    {mappingData.items.filter(i => i.suggested_fornitore_id).length} denominazioni esatte e univoche
                  </strong>{' '}
                  trovate tramite il nome PayPal.
                </div>
                <Button data-testid="mappa-tutti-certi-btn" onClick={mappaTuttiCerti} variant="primary">
                  Verifica e collega
                </Button>
              </div>
            )}

            {mappingLoading && !mappingData && (
              <div style={{ padding: 40, textAlign: 'center', color: COLORS.textSubtle }}>
                <RefreshCw
                  style={{
                    width: 24,
                    height: 24,
                    animation: 'spin 1s linear infinite',
                    color: COLORS.primary,
                  }}
                />
              </div>
            )}

            {mappingData && mappingData.items.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', color: COLORS.success, fontWeight: 600 }}>
                Tutti gli account PayPal sono mappati!
              </div>
            )}

            {mappingData &&
              mappingData.items.map(item => (
                <div
                  key={item.paypal_account_id}
                  data-testid={`mapping-row-${item.paypal_account_id}`}
                  style={{
                    padding: '14px 18px',
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
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
                        style={{ fontSize: 13, fontWeight: 700, color: COLORS.gray[800], marginBottom: 4 }}
                      >
                        {item.nome_controparte}
                      </div>
                    )}
                    <div
                      style={{
                        fontFamily: FONT.mono,
                        fontSize: 11,
                        fontWeight: 600,
                        color: COLORS.primary,
                      }}
                    >
                      {item.paypal_account_id}
                    </div>
                    <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 3 }}>
                      {item.n_tx} tx · {formatEuro(item.importo_totale)}
                    </div>
                    <div style={{ fontSize: 10, color: COLORS.textSubtle }}>
                      Media: {formatEuro(item.importo_medio)} · Ultima:{' '}
                      {formatDate(item.ultima_data)}
                    </div>
                    {item.email_controparte && (
                      <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Mail size={10} /> {item.email_controparte}
                      </div>
                    )}
                    {item.invoice_ids?.length > 0 && (
                      <div style={{ fontSize: 10, color: COLORS.textSubtle, marginTop: 3 }}>
                        Invoice: {item.invoice_ids.slice(0, 2).join(', ')}
                      </div>
                    )}
                  </div>

                  {/* Colonna 2: selezione fornitore con badge match certo */}
                  <div>
                    {item.suggested_fornitore_id && (
                      <Badge variant="success" style={{ marginBottom: 4 }}>
                        Denominazione PayPal coincidente — da confermare
                      </Badge>
                    )}
                    <Select
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
                        border:
                          item.suggested_fornitore_id &&
                          selectedForn[item.paypal_account_id] === item.suggested_fornitore_id
                            ? `2px solid ${COLORS.success}`
                            : `1px solid ${COLORS.border}`,
                      }}
                    >
                      <option value="">— Seleziona fornitore —</option>
                      {item.candidati?.filter(c => c.source === 'nome_paypal_exact').length >
                        0 && (
                        <optgroup label="Denominazione esatta">
                          {item.candidati
                            .filter(c => c.source === 'nome_paypal_exact')
                            .map(c => (
                              <option key={c.fornitore_id} value={c.fornitore_id}>
                                {c.nome} — P.IVA {c.piva} — score {c.score}
                              </option>
                            ))}
                        </optgroup>
                      )}
                      {item.candidati?.filter(c => ['nome_paypal_partial', 'nome_paypal_fuzzy'].includes(c.source)).length > 0 && (
                        <optgroup label="Nomi simili — verifica necessaria">
                          {item.candidati
                            .filter(c => ['nome_paypal_partial', 'nome_paypal_fuzzy'].includes(c.source))
                            .map(c => (
                              <option key={c.fornitore_id} value={c.fornitore_id}>
                                {c.nome} — P.IVA {c.piva} — score {c.score}
                              </option>
                            ))}
                        </optgroup>
                      )}
                      {item.candidati?.filter(c => c.source === 'nome_e_fatture_coerenti').length > 0 && (
                        <optgroup label="Fornitori coerenti con nome e fatture">
                          {item.candidati
                            .filter(c => c.source === 'nome_e_fatture_coerenti')
                            .map(c => (
                              <option key={c.fornitore_id} value={c.fornitore_id}>
                                {c.nome} — P.IVA {c.piva} — {c.n_fatture_simili} fatture
                              </option>
                            ))}
                        </optgroup>
                      )}
                    </Select>
                    {item.candidati?.length === 0 && (
                      <div style={{ fontSize: 11, color: COLORS.danger, marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <AlertTriangle size={11} /> Nessun candidato. Crea il fornitore in anagrafica.
                      </div>
                    )}
                  </div>

                  {/* Colonna 3: bottoni azione */}
                  <div style={{ display: 'flex', gap: 8, flexDirection: 'column' }}>
                    <Button
                      data-testid={`mappa-btn-${item.paypal_account_id}`}
                      variant="primary"
                      onClick={() =>
                        mappaFornitore(item.paypal_account_id, selectedForn[item.paypal_account_id])
                      }
                      disabled={!selectedForn[item.paypal_account_id]}
                    >
                      Collega
                    </Button>
                    <Button
                      data-testid={`crea-forn-btn-${item.paypal_account_id}`}
                      variant="outline"
                      size="sm"
                      iconLeft={<Plus size={12} />}
                      onClick={() => setCreateModal({
                        paypal_account_id: item.paypal_account_id,
                        nome_controparte: item.nome_controparte || '',
                        email_controparte: item.email_controparte || '',
                        importo_totale: item.importo_totale || 0,
                        n_tx: item.n_tx || 0,
                      })}
                      title="Crea un nuovo fornitore in anagrafica e mappalo subito"
                      style={{ borderStyle: 'dashed', fontSize: 11 }}
                    >
                      Crea nuovo
                    </Button>
                    <Button
                      data-testid={`cerca-email-btn-${item.paypal_account_id}`}
                      variant="ghost"
                      size="sm"
                      disabled={cercandoEmail === item.paypal_account_id}
                      iconLeft={
                        cercandoEmail === item.paypal_account_id ? (
                          <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />
                        ) : (
                          <Mail size={12} />
                        )
                      }
                      onClick={() => handleCercaFatturaEmail(item.paypal_account_id)}
                      title="Cerca la fattura nella posta (fornitori esteri: mai su Drive/PEC, esiste solo come PDF via email)"
                      style={{ border: `1px dashed ${COLORS.borderDark}`, fontSize: 11 }}
                    >
                      {cercandoEmail === item.paypal_account_id ? 'Cerco nella posta…' : 'Cerca fattura via email'}
                    </Button>
                  </div>
                </div>
              ))}

            {mappingData && mappingData.items.length > 0 && (
              <div
                style={{
                  padding: '14px 18px',
                  background: COLORS.infoLight,
                  borderTop: `2px solid ${COLORS.primary}`,
                  fontSize: 12,
                  color: COLORS.info,
                }}
              >
                <strong>Suggerimento</strong>: una volta mappati i fornitori, esegui{' '}
                <code style={{ padding: '1px 4px', background: COLORS.primarySoft, borderRadius: BORDER_RADIUS.sm }}>
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
        onOpenInvoice={invoice => setFatturaView(invoice)}
      />
      {fatturaView && (
        <ModalFattura
          fatturaId={fatturaView.id}
          numero={fatturaView.numero}
          onClose={() => setFatturaView(null)}
        />
      )}

      {/* Modale crea fornitore + mappa */}
      {createModal && (
        <CreaFornitorePaypalModal
          context={createModal}
          onClose={() => setCreateModal(null)}
          onCreated={() => {
            setCreateModal(null);
            loadMapping();
            toast.success('Fornitore creato e mappato');
          }}
        />
      )}
    </PageLayout>
  );
}

// ------ Modale: crea fornitore inline + mappa al paypal_account_id ------
function CreaFornitorePaypalModal({ context, onClose, onCreated }) {
  const [form, setForm] = useState({
    ragione_sociale: context.nome_controparte || '',
    piva: '',
    nazione: 'IT',
    email: context.email_controparte || '',
    metodo_pagamento: 'paypal',
    esclude_magazzino: true,
    note: `Creato da PayPal mapping (${context.n_tx} transazioni, totale ${Math.abs(context.importo_totale).toFixed(2)})`,
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
        position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)',
        zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: COLORS.card, borderRadius: BORDER_RADIUS.lg, width: '100%', maxWidth: 560,
          padding: 24, boxShadow: SHADOWS.modal, position: 'relative',
        }}
      >
        <Button
          variant="ghost"
          onClick={onClose}
          aria-label="Chiudi"
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            padding: 0,
            width: 40,
            height: 40,
          }}
        >
          <X size={18} />
        </Button>
        <div style={{ marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: COLORS.primary, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Plus size={18} /> Crea fornitore PayPal
          </h2>
          <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
            Account ID: <code>{context.paypal_account_id}</code> · {context.n_tx} transazioni
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Field label="Ragione sociale *" required>
            <Input
              type="text"
              value={form.ragione_sociale}
              onChange={e => setForm(f => ({ ...f, ragione_sociale: e.target.value }))}
              autoFocus
            />
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
            <Field label="P.IVA / VAT">
              <Input
                type="text"
                value={form.piva}
                onChange={e => setForm(f => ({ ...f, piva: e.target.value.toUpperCase() }))}
                placeholder="es. IE9952657T"
              />
            </Field>
            <Field label="Nazione">
              <Select
                value={form.nazione}
                onChange={e => setForm(f => ({ ...f, nazione: e.target.value }))}
              >
                <option value="IT">Italia</option>
                <option value="IE">Irlanda</option>
                <option value="NL">Paesi Bassi</option>
                <option value="DE">Germania</option>
                <option value="FR">Francia</option>
                <option value="ES">Spagna</option>
                <option value="GB">Regno Unito</option>
                <option value="US">USA</option>
                <option value="LU">Lussemburgo</option>
                <option value="OTHER">Altro</option>
              </Select>
            </Field>
          </div>

          <Field label="Email">
            <Input
              type="email"
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
            />
          </Field>

          <Field label="Note">
            {/* Textarea nativa: nessun componente ds dedicato al testo multi-riga. */}
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
              background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.sm, fontSize: 12,
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
              marginTop: 12, padding: 10, background: COLORS.dangerLight,
              border: `1px solid ${COLORS.danger}`, borderRadius: BORDER_RADIUS.sm, color: COLORS.danger, fontSize: 13,
              display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Annulla
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            disabled={loading || !form.ragione_sociale.trim()}
            iconLeft={<Plus size={14} />}
          >
            {loading ? 'Creazione…' : 'Crea e mappa'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: 'block' }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      {children}
    </label>
  );
}

const inputStyle = {
  width: '100%',
  padding: '8px 10px',
  border: `1px solid ${COLORS.border}`,
  borderRadius: BORDER_RADIUS.sm,
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: FONT.family,
};
