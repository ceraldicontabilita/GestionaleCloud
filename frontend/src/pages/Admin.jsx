import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { toast } from 'sonner';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, SHADOWS, BORDER_RADIUS, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useHashState } from '../hooks/useHashState';
import { Button, Badge, StatCard, Card, Tabs, Input, Select } from '../components/ds';
import { Trash2, AlertTriangle, X, Loader2, CheckCircle2 } from 'lucide-react';
import PannelloSumUp from '../components/PannelloSumUp';

export default function Admin() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dbStatus, setDbStatus] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  // Deep link: tab sincronizzato con URL hash (#tab=email, #tab=system, ecc.)
  const getTabFromPath = () => {
    const match = location.pathname.match(/\/admin\/([\w-]+)/);
    return match ? match[1] : 'email';
  };

  const [hs, setHs] = useHashState({ tab: getTabFromPath() });
  const activeTab = hs.tab;

  const handleTabChange = tabId => {
    setHs('tab', tabId);
    navigate(`/admin/${tabId}`);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setHs('tab', tab);
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  const [triggerLoading, setTriggerLoading] = useState(false);

  // Email accounts
  const [emailAccounts, setEmailAccounts] = useState([]);
  const [loadingEmails, setLoadingEmails] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [showPassword, setShowPassword] = useState({});
  const [newAccount, setNewAccount] = useState({
    nome: '',
    email: '',
    app_password: '',
    imap_server: 'imap.gmail.com',
    imap_port: 993,
    parole_chiave: [],
    cartelle: ['INBOX'],
  });
  const [showNewForm, setShowNewForm] = useState(false);
  const [testingConnection, setTestingConnection] = useState(null);
  const [newKeywordInput, setNewKeywordInput] = useState('');
  const [editKeywordInput, setEditKeywordInput] = useState('');

  // Parole chiave globali
  const [paroleChiave, setParoleChiave] = useState({});
  const [newKeyword, setNewKeyword] = useState({ categoria: 'generale', parola: '' });

  // Sincronizzazione dati
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [verificaCorrispettivi, setVerificaCorrispettivi] = useState(null);
  const [initialLoad, setInitialLoad] = useState(true);
  const [bankRules, setBankRules] = useState([]);
  const [bankRule, setBankRule] = useState({ reference_text: '', supplier_name: '', supplier_vat: '' });
  const [bankRulesLoading, setBankRulesLoading] = useState(false);
  const [bankReprocessResult, setBankReprocessResult] = useState(null);
  const [bankImportResult, setBankImportResult] = useState(null);
  const [bankCsvText, setBankCsvText] = useState('');

  const loadBankRules = useCallback(async () => {
    const response = await api.get('/api/admin/bank-supplier-rules');
    setBankRules(response.data || []);
  }, []);

  async function saveBankRule() {
    try {
      await api.post('/api/admin/bank-supplier-rules', bankRule);
      setBankRule({ reference_text: '', supplier_name: '', supplier_vat: '' });
      await loadBankRules();
      toast.success('Riferimento bancario salvato');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Salvataggio non riuscito');
    }
  }

  async function reprocessBankRules() {
    setBankRulesLoading(true);
    try {
      const response = await api.post(`/api/admin/bank-supplier-rules/reprocess/${anno}`);
      setBankReprocessResult(response.data);
      toast.success(`${response.data.linked_count} fatture associate e pagate`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Riprocessamento non riuscito');
    } finally {
      setBankRulesLoading(false);
    }
  }

  async function importBankStatement(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBankRulesLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await api.post('/api/estratto-conto-movimenti/import', form);
      setBankImportResult(response.data);
      toast.success('Estratto conto acquisito');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Importazione estratto non riuscita');
    } finally {
      setBankRulesLoading(false);
      event.target.value = '';
    }
  }

  async function importBankCsvText() {
    if (!bankCsvText.trim()) return;
    setBankRulesLoading(true);
    try {
      const form = new FormData();
      form.append('file', new File([bankCsvText], `estratto-${anno}.csv`, { type: 'text/csv' }));
      const response = await api.post('/api/estratto-conto-movimenti/import', form);
      setBankImportResult(response.data);
      setBankCsvText('');
      toast.success('Estratto conto acquisito');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Importazione estratto non riuscita');
    } finally {
      setBankRulesLoading(false);
    }
  }

  // Carica tutti i dati dalla dashboard aggregata in un'unica chiamata
  const loadDashboardSummary = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const r = await api.get('/api/admin/dashboard-summary').catch(() => ({ data: null }));
      if (r.data) {
        if (r.data.stats) setStats(r.data.stats);
        if (r.data.health) setDbStatus(r.data.health);
        if (r.data.sync) setSyncStatus(r.data.sync);
        // alert count e agenti count vengono gestiti da AgentiPanel/NotificationBell
      }
    } catch (e) {
      console.error('Error loading dashboard summary:', e);
    } finally {
      if (!silent) setLoading(false);
      setInitialLoad(false);
    }
  }, []);

  useEffect(() => {
    // Caricamento iniziale
    loadDashboardSummary(false);
    loadEmailAccounts();
    loadParoleChiave();
    loadBankRules().catch(e => console.error('Error loading bank rules:', e));

    // Polling silenzioso ogni 5 minuti
    const interval = setInterval(() => loadDashboardSummary(true), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [loadDashboardSummary, loadBankRules]);

  async function loadStats() {
    try {
      setLoading(true);
      const r = await api.get('/api/admin/stats').catch(() => ({ data: null }));
      setStats(r.data);
    } catch (e) {
      console.error('Error loading stats:', e);
    } finally {
      setLoading(false);
    }
  }

  async function checkHealth() {
    try {
      const r = await api.get('/api/health');
      setDbStatus(r.data);
    } catch (e) {
      setDbStatus({ status: 'error', database: 'disconnected' });
    }
  }

  async function loadEmailAccounts() {
    setLoadingEmails(true);
    try {
      const r = await api.get('/api/config/email-accounts');
      setEmailAccounts(r.data || []);
    } catch (e) {
      console.error('Error loading email accounts:', e);
    } finally {
      setLoadingEmails(false);
    }
  }

  async function loadParoleChiave() {
    try {
      const r = await api.get('/api/config/parole-chiave');
      setParoleChiave(r.data || {});
    } catch (e) {
      console.error('Error loading parole chiave:', e);
    }
  }

  async function saveEmailAccount(account) {
    try {
      if (account.id) {
        await api.put(`/api/config/email-accounts/${account.id}`, account);
      } else {
        await api.post('/api/config/email-accounts', account);
      }
      loadEmailAccounts();
      setEditingAccount(null);
      setShowNewForm(false);
      setNewAccount({
        nome: '',
        email: '',
        app_password: '',
        imap_server: 'imap.gmail.com',
        imap_port: 993,
        parole_chiave: [],
        cartelle: ['INBOX'],
      });
      setNewKeywordInput('');
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function deleteEmailAccount(accountId) {
    try {
      await api.delete(`/api/config/email-accounts/${accountId}`);
      loadEmailAccounts();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function testEmailConnection(accountId) {
    setTestingConnection(accountId);
    try {
      const r = await api.post(`/api/config/email-accounts/${accountId}/test`);
      if (r.data.success) {
        toast.success('Connessione riuscita', { description: `Email nella casella: ${r?.data?.email_count}` });
      } else {
        toast.error('Connessione fallita', { description: r?.data?.message });
      }
    } catch (e) {
      toast.error('Errore test: ' + (e.response?.data?.detail || e.message));
    } finally {
      setTestingConnection(null);
    }
  }

  async function addParolaChiave() {
    if (!newKeyword.parola.trim()) return;
    try {
      await api.post(
        `/api/config/parole-chiave/aggiungi?categoria=${newKeyword.categoria}&parola=${encodeURIComponent(newKeyword.parola)}`
      );
      loadParoleChiave();
      setNewKeyword({ ...newKeyword, parola: '' });
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function removeParolaChiave(categoria, parola) {
    try {
      await api.delete(
        `/api/config/parole-chiave/rimuovi?categoria=${categoria}&parola=${encodeURIComponent(parola)}`
      );
      loadParoleChiave();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  // Aggiungi parola chiave all'account (nuovo o in modifica)
  const addKeywordToAccount = isEditing => {
    const input = isEditing ? editKeywordInput : newKeywordInput;
    if (!input.trim()) return;
    if (isEditing && editingAccount) {
      const kws = editingAccount.parole_chiave || [];
      if (!kws.includes(input.trim())) {
        setEditingAccount({ ...editingAccount, parole_chiave: [...kws, input.trim()] });
      }
      setEditKeywordInput('');
    } else {
      const kws = newAccount.parole_chiave || [];
      if (!kws.includes(input.trim())) {
        setNewAccount({ ...newAccount, parole_chiave: [...kws, input.trim()] });
      }
      setNewKeywordInput('');
    }
  };

  // Rimuovi parola chiave dall'account
  const removeKeywordFromAccount = (keyword, isEditing) => {
    if (isEditing && editingAccount) {
      setEditingAccount({
        ...editingAccount,
        parole_chiave: (editingAccount.parole_chiave || []).filter(k => k !== keyword),
      });
    } else {
      setNewAccount({
        ...newAccount,
        parole_chiave: (newAccount.parole_chiave || []).filter(k => k !== keyword),
      });
    }
  };

  // ========== FUNZIONI SINCRONIZZAZIONE ==========

  async function loadSyncStatus() {
    try {
      const r = await api.get('/api/sync/stato-sincronizzazione');
      setSyncStatus(r.data);
    } catch (e) {
      console.error('Error loading sync status:', e);
    }
  }

  async function verificaEntrateCorrette() {
    setSyncLoading(true);
    try {
      const r = await api.get(`/api/prima-nota/cassa/verifica-entrate-corrispettivi?anno=${anno}`);
      setVerificaCorrispettivi(r.data);
    } catch (e) {
      console.error('Error verifica:', e);
    }
    setSyncLoading(false);
  }

  async function correggiCorrispettivi() {
    setSyncLoading(true);
    try {
      const r = await api.post(`/api/prima-nota/cassa/fix-corrispettivi-importo?anno=${anno}`);
      toast.success(`Corretti ${r?.data?.corretti} movimenti`, {
        description: `Differenza totale: €${r?.data?.totale_differenza_euro?.toLocaleString('it-IT')}`,
      });
      await verificaEntrateCorrette();
      await loadSyncStatus();
    } catch (e) {
      console.error('Error fix:', e);
      toast.error('Errore durante la correzione');
    }
    setSyncLoading(false);
  }

  async function matchFattureCassa() {
    setSyncLoading(true);
    try {
      const r = await api.post('/api/sync/match-fatture-cassa');
      toast.success('Match completato', {
        description: `Trovate: ${r?.data?.matched} — non trovate: ${r?.data?.not_matched}`,
      });
      await loadSyncStatus();
    } catch (e) {
      console.error('Error match:', e);
      toast.error('Errore durante il match');
    }
    setSyncLoading(false);
  }

  async function matchFattureBanca() {
    setSyncLoading(true);
    try {
      const r = await api.post('/api/sync/match-fatture-banca');
      toast.success('Match completato', {
        description: `Associate: ${r?.data?.matched} — non trovate: ${r?.data?.not_matched}`,
      });
      await loadSyncStatus();
    } catch (e) {
      console.error('Error match banca:', e);
      toast.error('Errore durante il match');
    }
    setSyncLoading(false);
  }

  const tabItems = [
    { key: 'email', label: 'Email', icon: '📧' },
    { key: 'keywords', label: 'Parole Chiave', icon: '🔑' },
    { key: 'rollback', label: 'Rollback Dati', icon: '🗑️' },
    { key: 'collaudo', label: 'Collaudo', icon: '🧪' },
    { key: 'bank-rules', label: 'Riferimenti bancari', icon: '🏦' },
    { key: 'drive-ledger', label: 'Registro Drive', icon: '📊' },
  ];

  return (
    <PageLayout
      title="Amministrazione"
      icon="⚙️"
      subtitle="Configurazione sistema, email e parametri"
    >
      {/* Tabs */}
      <Tabs items={tabItems} value={activeTab} onChange={handleTabChange} style={{ marginBottom: 16 }} />

      {/* TAB EMAIL */}
      {activeTab === 'email' && (
        <div style={{ display: 'grid', gap: 16 }}>
          <div style={{
            padding: 14, borderRadius: BORDER_RADIUS.md,
            border: `1px solid ${COLORS.info}`, background: COLORS.infoLight,
            color: COLORS.text, fontSize: 13, lineHeight: 1.55,
          }}>
            <strong>Smistamento controllato:</strong> gli account servono solo a leggere la posta.
            Il sistema conserva nell'app esclusivamente allegati amministrativi riconosciuti
            (F24, cedolini, avvisi bonari, verbali, cartelle esattoriali e documenti equivalenti),
            li classifica dal contenuto/nome del documento e ne archivia una copia nella cartella
            Drive corrispondente. Gli allegati non pertinenti vengono ignorati; il tipo del mittente
            non puo piu sovrascrivere una classificazione documentale certa.
          </div>
          <Card
            title="Account Email Configurati"
            actions={
              <Button variant="primary" size="sm" onClick={() => setShowNewForm(true)} iconLeft="➕">
                Aggiungi Email
              </Button>
            }
          >
            {loadingEmails ? (
              <div style={{ textAlign: 'center', padding: 20, color: COLORS.textMuted }}>
                Caricamento...
              </div>
            ) : emailAccounts.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 20, color: COLORS.textMuted }}>
                Nessun account email configurato
              </div>
            ) : (
              <div style={{ display: 'grid', gap: 12 }}>
                {emailAccounts.map(acc => (
                  <div
                    key={acc.id}
                    style={{
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      padding: 16,
                      background: acc.is_env_default ? COLORS.infoLight : COLORS.bgAlt,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        marginBottom: 12,
                      }}
                    >
                      <div>
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            fontWeight: 600,
                            fontSize: 14,
                          }}
                        >
                          📧 {acc.nome}
                          {acc.is_env_default && <Badge variant="info">Principale (da .env)</Badge>}
                          {acc.attivo ? (
                            <Badge variant="success">Attivo</Badge>
                          ) : (
                            <Badge variant="danger">Disattivo</Badge>
                          )}
                        </div>
                        <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                          {acc.email}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => testEmailConnection(acc.id)}
                          disabled={testingConnection === acc.id}
                        >
                          {testingConnection === acc.id ? '⏳' : 'Test'}
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            setEditingAccount({ ...acc });
                            setEditKeywordInput('');
                          }}
                        >
                          Modifica
                        </Button>
                        {!acc.is_env_default && (
                          <Button variant="danger" size="sm" onClick={() => deleteEmailAccount(acc.id)}>
                            🗑️
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Password */}
                    <div
                      style={{
                        fontSize: 12,
                        color: COLORS.textMuted,
                        marginBottom: 8,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      <span>App Password:</span>
                      <span style={{ fontFamily: 'monospace' }}>
                        {showPassword[acc.id] ? acc.app_password : acc.app_password_masked}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setShowPassword({ ...showPassword, [acc.id]: !showPassword[acc.id] })
                        }
                        style={{ color: COLORS.primaryLight, padding: '2px 6px' }}
                      >
                        {showPassword[acc.id] ? '🙈' : '👁️'}
                      </Button>
                    </div>

                    {/* Parole chiave come tag separati */}
                    <div style={{ fontSize: 12 }}>
                      <span style={{ fontWeight: 500 }}>Parole Chiave:</span>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                        {(acc.parole_chiave || []).map((kw, i) => (
                          <Badge key={i} variant="primary">
                            {kw}
                          </Badge>
                        ))}
                        {(!acc.parole_chiave || acc.parole_chiave.length === 0) && (
                          <span style={{ color: COLORS.textSubtle, fontStyle: 'italic' }}>
                            Nessuna (accetta tutte le email)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Form Nuovo Account */}
            {showNewForm && (
              <div
                style={{ marginTop: 20, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}
              >
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>
                  ➕ Nuovo Account Email
                </h4>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)',
                    gap: 12,
                  }}
                >
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Nome Account
                    </label>
                    <Input
                      value={newAccount.nome}
                      onChange={e => setNewAccount({ ...newAccount, nome: e.target.value })}
                      placeholder="es. Commercialista"
                    />
                  </div>
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Email
                    </label>
                    <Input
                      type="email"
                      value={newAccount.email}
                      onChange={e => setNewAccount({ ...newAccount, email: e.target.value })}
                      placeholder="email@esempio.com"
                    />
                  </div>
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      App Password
                    </label>
                    <Input
                      type="password"
                      value={newAccount.app_password}
                      onChange={e =>
                        setNewAccount({ ...newAccount, app_password: e.target.value })
                      }
                      placeholder="Password app Google"
                    />
                  </div>
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Server IMAP
                    </label>
                    <Input
                      value={newAccount.imap_server}
                      onChange={e =>
                        setNewAccount({ ...newAccount, imap_server: e.target.value })
                      }
                    />
                  </div>

                  {/* Parole Chiave - Campi separati */}
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Parole Chiave
                    </label>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <Input
                        value={newKeywordInput}
                        onChange={e => setNewKeywordInput(e.target.value)}
                        placeholder="Aggiungi parola chiave..."
                        onKeyDown={e =>
                          e.key === 'Enter' && (e.preventDefault(), addKeywordToAccount(false))
                        }
                      />
                      <Button type="button" variant="primary" size="sm" onClick={() => addKeywordToAccount(false)}>
                        ➕
                      </Button>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {(newAccount.parole_chiave || []).map((kw, i) => (
                        <Badge
                          key={i}
                          variant="primary"
                          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                        >
                          {kw}
                          <button
                            onClick={() => removeKeywordFromAccount(kw, false)}
                            style={{
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              padding: 0,
                              color: COLORS.danger,
                            }}
                          >
                            ✕
                          </button>
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                  <Button variant="success" onClick={() => saveEmailAccount(newAccount)}>
                    ✔️ Salva
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowNewForm(false);
                      setNewKeywordInput('');
                    }}
                  >
                    ✕ Annulla
                  </Button>
                </div>
              </div>
            )}

            {/* Form Modifica Account */}
            {editingAccount && (
              <div
                style={{ marginTop: 20, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}
              >
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>
                  ✏️ Modifica Account: {editingAccount.nome}
                  {editingAccount.is_env_default && (
                    <span style={{ fontSize: 10, color: COLORS.textMuted, marginLeft: 8 }}>
                      (Email Principale da .env)
                    </span>
                  )}
                </h4>{' '}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)',
                    gap: 12,
                  }}
                >
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Nome Account
                    </label>
                    <Input
                      value={editingAccount.nome}
                      onChange={e =>
                        setEditingAccount({ ...editingAccount, nome: e.target.value })
                      }
                    />
                  </div>
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Email
                    </label>
                    <Input
                      type="email"
                      value={editingAccount.email}
                      onChange={e =>
                        setEditingAccount({ ...editingAccount, email: e.target.value })
                      }
                      disabled={editingAccount.is_env_default}
                    />
                  </div>
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      App Password
                    </label>
                    <Input
                      type="password"
                      value={editingAccount.app_password || ''}
                      onChange={e =>
                        setEditingAccount({ ...editingAccount, app_password: e.target.value })
                      }
                      placeholder="Lascia vuoto per non modificare"
                    />
                  </div>
                  <div>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Attivo
                    </label>
                    <Select
                      value={editingAccount.attivo ? 'true' : 'false'}
                      onChange={e =>
                        setEditingAccount({
                          ...editingAccount,
                          attivo: e.target.value === 'true',
                        })
                      }
                    >
                      <option value="true">Si</option>
                      <option value="false">No</option>
                    </Select>
                  </div>

                  {/* Parole Chiave - Campi separati */}
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label
                      style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                    >
                      Parole Chiave
                    </label>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <Input
                        value={editKeywordInput}
                        onChange={e => setEditKeywordInput(e.target.value)}
                        placeholder="Aggiungi parola chiave..."
                        onKeyDown={e =>
                          e.key === 'Enter' && (e.preventDefault(), addKeywordToAccount(true))
                        }
                      />
                      <Button type="button" variant="primary" size="sm" onClick={() => addKeywordToAccount(true)}>
                        ➕
                      </Button>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {(editingAccount.parole_chiave || []).map((kw, i) => (
                        <Badge
                          key={i}
                          variant="primary"
                          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                        >
                          {kw}
                          <button
                            onClick={() => removeKeywordFromAccount(kw, true)}
                            style={{
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              padding: 0,
                              color: COLORS.danger,
                            }}
                          >
                            ✕
                          </button>
                        </Badge>
                      ))}
                      {(!editingAccount.parole_chiave ||
                        editingAccount.parole_chiave.length === 0) && (
                        <span style={{ color: COLORS.textSubtle, fontStyle: 'italic', fontSize: 12 }}>
                          Nessuna parola chiave (accetta tutte le email)
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                  <Button variant="success" onClick={() => saveEmailAccount(editingAccount)}>
                    ✔️ Salva Modifiche
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setEditingAccount(null);
                      setEditKeywordInput('');
                    }}
                  >
                    ✕ Annulla
                  </Button>
                </div>
              </div>
            )}
          </Card>

          {/* In Admin resta soltanto lo stato tecnico: i dati operativi sono in Prima Nota. */}
          <PannelloSumUp />
        </div>
      )}

      {/* TAB PAROLE CHIAVE GLOBALI */}
      {activeTab === 'keywords' && (
        <Card title="Parole Chiave per Filtro Email (Globali)">
          <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 16 }}>
            Queste parole chiave vengono usate per categorizzare automaticamente i documenti
            scaricati dalle email.
          </p>

          {/* Aggiungi nuova */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
            <Select
              value={newKeyword.categoria}
              onChange={e => setNewKeyword({ ...newKeyword, categoria: e.target.value })}
              style={{ minWidth: 120, width: 'auto' }}
            >
              <option value="generale">Generale</option>
              <option value="fatture">Fatture</option>
              <option value="f24">F24</option>
              <option value="buste_paga">Buste Paga</option>
            </Select>
            <Input
              value={newKeyword.parola}
              onChange={e => setNewKeyword({ ...newKeyword, parola: e.target.value })}
              placeholder="Nuova parola chiave..."
              style={{ flex: 1 }}
              onKeyDown={e => e.key === 'Enter' && addParolaChiave()}
            />
            <Button variant="primary" onClick={addParolaChiave}>
              ➕ Aggiungi
            </Button>
          </div>

          {/* Lista per categoria */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)',
              gap: 16,
            }}
          >
            {['generale', 'fatture', 'f24', 'buste_paga'].map(cat => (
              <div
                key={cat}
                style={{ border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: 12 }}
              >
                <h5
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    marginBottom: 8,
                    textTransform: 'capitalize',
                  }}
                >
                  {cat.replace('_', ' ')}
                </h5>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {(paroleChiave[cat] || []).map(kw => (
                    <Badge
                      key={`${cat}-${kw}`}
                      variant="neutral"
                      style={{ display: 'flex', alignItems: 'center', gap: 6, textTransform: 'none' }}
                    >
                      {kw}
                      <button
                        onClick={() => removeParolaChiave(cat, kw)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                          color: COLORS.danger,
                        }}
                        data-testid={`remove-keyword-${cat}-${kw}`}
                      >
                        ✕
                      </button>
                    </Badge>
                  ))}
                  {(!paroleChiave[cat] || paroleChiave[cat].length === 0) && (
                    <span style={{ color: COLORS.textSubtle, fontSize: 11, fontStyle: 'italic' }}>
                      Nessuna parola chiave
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {activeTab === 'rollback' && <RollbackDatiTab />}

      {activeTab === 'collaudo' && <CollaudoTab />}

      {activeTab === 'drive-ledger' && <GoogleSheetsLedgerTab />}

      {activeTab === 'bank-rules' && (
        <Card title="Riferimenti bancari ricorrenti">
          <p style={{ fontSize: 13, color: COLORS.textMuted }}>
            Associa una dicitura certa dell'estratto conto a un fornitore. Il riprocessamento
            collega solo importi identici al centesimo e fatture temporalmente compatibili.
          </p>
          <div style={{ padding: 12, marginBottom: 14, background: COLORS.infoLight, borderRadius: BORDER_RADIUS.sm }}>
            <strong>1. Carica o aggiorna l'estratto conto</strong>
            <Input type="file" accept=".csv,.pdf" onChange={importBankStatement} disabled={bankRulesLoading} style={{ marginTop: 8 }} />
            <textarea value={bankCsvText} onChange={e => setBankCsvText(e.target.value)} placeholder="Oppure incolla qui il contenuto CSV" rows={4} style={{ width: '100%', marginTop: 8, padding: 10, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.sm }} />
            <Button size="sm" variant="secondary" onClick={importBankCsvText} disabled={bankRulesLoading || !bankCsvText.trim()}>Importa CSV incollato</Button>
            {bankImportResult && <small>Importati: {bankImportResult.importati ?? bankImportResult.movimenti_importati ?? 0} · Duplicati: {bankImportResult.duplicati ?? 0}</small>}
          </div>
          <strong>2. Salva i riferimenti certi</strong>
          <div style={{ display: 'grid', gap: 10, gridTemplateColumns: isMobile ? '1fr' : '2fr 1fr 1fr auto' }}>
            <Input value={bankRule.reference_text} onChange={e => setBankRule({ ...bankRule, reference_text: e.target.value })} placeholder="Dicitura bancaria completa" />
            <Input value={bankRule.supplier_name} onChange={e => setBankRule({ ...bankRule, supplier_name: e.target.value })} placeholder="Fornitore (es. FASTWEB)" />
            <Input value={bankRule.supplier_vat} onChange={e => setBankRule({ ...bankRule, supplier_vat: e.target.value })} placeholder="P.IVA facoltativa" />
            <Button variant="primary" onClick={saveBankRule}>Salva</Button>
          </div>
          <div style={{ display: 'grid', gap: 8, marginTop: 16 }}>
            {bankRules.map(rule => (
              <div key={rule.id} style={{ padding: 10, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.sm, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span><strong>{rule.supplier_name}</strong><br /><small>{rule.reference_text}</small></span>
                <Button variant="danger" size="sm" onClick={async () => { await api.delete(`/api/admin/bank-supplier-rules/${rule.id}`); await loadBankRules(); }}>Elimina</Button>
              </div>
            ))}
          </div>
          <Button style={{ marginTop: 16 }} variant="success" disabled={bankRulesLoading} onClick={reprocessBankRules}>
            {bankRulesLoading ? 'Elaborazione...' : `3. Riprocessa pagamenti ${anno}`}
          </Button>
          {bankReprocessResult && (
            <div style={{ marginTop: 12, padding: 12, background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.sm }}>
              Associate: <strong>{bankReprocessResult.linked_count}</strong> · Ambigue: <strong>{bankReprocessResult.ambiguous_count}</strong> · Senza fattura: <strong>{bankReprocessResult.no_invoice_count}</strong>
            </div>
          )}
        </Card>
      )}

      {/* TAB SINCRONIZZAZIONE */}

      {/* TAB MANUTENZIONE - Logiche Intelligenti */}

      {/* TAB ESPORTAZIONI */}
    </PageLayout>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB ROLLBACK DATI — elimina dati per intervallo di tempo, per sezione.
// Strumento per controlli di precisione: elimina gli ultimi N giorni di una
// sezione, poi re-importa e verifica che i calcoli tornino corretti.
// ═══════════════════════════════════════════════════════════════════════════
// Card "Pulizia cartella Drive fatture per anno" (tab Rollback).
// Incolli l'URL (o l'ID) della cartella Drive, scegli gli anni, CONTI
// (nessun file toccato) e solo dopo sposti nel CESTINO Drive — recuperabile
// per 30 giorni. L'anno viene letto dalla data del documento dentro l'XML;
// i file con anno non determinabile NON vengono mai toccati.
// Selettore globale "anno di importazione attivo" (richiesta utente
// 14/07/2026): governa sia l'import Drive fatture sia l'import Drive
// corrispettivi — solo i documenti con data nell'anno scelto entrano nel
// flusso attivo (Prima Nota/scadenzario/alert/magazzino), gli altri anni
// vengono archiviati per sola consultazione. Un'unica impostazione
// condivisa (non una per canale), come scelto dall'utente.
function PuliziaDriveFattureCard() {
  const confirm = useConfirm();
  const [folder, setFolder] = useState('');
  const [anni, setAnni] = useState({ 2023: true, 2024: true, 2025: true });
  const [contaRes, setContaRes] = useState(null);
  const [busy, setBusy] = useState(null); // 'conta' | 'elimina' | null
  const [errore, setErrore] = useState(null);

  const anniScelti = Object.entries(anni)
    .filter(([, v]) => v)
    .map(([k]) => parseInt(k));

  const lancia = async elimina => {
    if (!folder.trim()) {
      setErrore('Incolla l\'URL o l\'ID della cartella Drive');
      return;
    }
    if (anniScelti.length === 0) {
      setErrore('Seleziona almeno un anno');
      return;
    }
    if (
      elimina &&
      !(await confirm({
        title: 'Sposta file nel cestino Drive',
        message: `Spostare nel CESTINO Drive ${contaRes?.da_eliminare ?? '?'} file fattura degli anni ${anniScelti.join(', ')}? I file restano recuperabili dal cestino Drive per 30 giorni.`,
        variant: 'warning',
      }))
    ) {
      return;
    }
    setBusy(elimina ? 'elimina' : 'conta');
    setErrore(null);
    try {
      const res = await api.post(
        `/api/admin/rollback/drive-fatture/${elimina ? 'elimina' : 'conta'}`,
        { folder: folder.trim(), anni: anniScelti }
      );
      if (res.data.status === 'error') {
        setErrore(res.data.message);
      } else {
        setContaRes(res.data);
      }
    } catch (e) {
      setErrore(e.response?.data?.detail || e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      style={{
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: BORDER_RADIUS.lg,
        padding: 14,
        marginBottom: 12,
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 14, color: COLORS.primary, marginBottom: 4 }}>
        📁 Cartella Drive fatture — pulizia per anno
      </div>
      <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 10 }}>
        Dopo il rollback di un anno, i file XML/P7M su Drive vanno rimossi anche da qui,
        altrimenti la sincronizzazione li reimporta. Legge l'anno dalla data del documento
        dentro ogni file (sottocartelle incluse, anche &quot;Elaborate&quot;) e sposta nel{' '}
        <strong>cestino</strong> Drive (recuperabile 30 giorni). I file con anno non
        determinabile non vengono toccati.
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <input
          type="text"
          value={folder}
          onChange={e => setFolder(e.target.value)}
          placeholder="URL o ID della cartella Drive (es. https://drive.google.com/drive/folders/…)"
          data-testid="input-drive-pulizia-folder"
          style={{
            flex: '1 1 320px',
            padding: '9px 12px',
            border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md,
            fontSize: 13,
          }}
        />
        {[2023, 2024, 2025].map(a => (
          <label
            key={a}
            style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, fontWeight: 600, color: COLORS.text, cursor: 'pointer' }}
          >
            <input
              type="checkbox"
              checked={!!anni[a]}
              onChange={e => setAnni(prev => ({ ...prev, [a]: e.target.checked }))}
            />
            {a}
          </label>
        ))}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => lancia(false)}
          disabled={busy !== null}
          data-testid="btn-drive-pulizia-conta"
        >
          {busy === 'conta' ? '⏳ Conto…' : '🔍 Conta (nessuna modifica)'}
        </Button>
        <Button
          variant="danger"
          size="sm"
          onClick={() => lancia(true)}
          disabled={busy !== null || !contaRes || contaRes.da_eliminare === 0}
          title={!contaRes ? 'Prima esegui il conteggio' : undefined}
          data-testid="btn-drive-pulizia-elimina"
        >
          {busy === 'elimina' ? '⏳ Sposto nel cestino…' : '🗑️ Sposta nel cestino Drive'}
        </Button>
      </div>
      {errore && (
        <div style={{ marginTop: 10, fontSize: 13, fontWeight: 600, color: COLORS.danger }}>
          ⚠️ {errore}
        </div>
      )}
      {contaRes && (
        <div
          style={{
            marginTop: 10,
            background: COLORS.bgAlt,
            border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md,
            padding: '10px 12px',
            fontSize: 13,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>
            {contaRes.dry_run
              ? `Trovati ${contaRes.da_eliminare} file da spostare nel cestino`
              : `✅ Spostati nel cestino ${contaRes.eliminati} file`}{' '}
            <span style={{ fontWeight: 500, color: COLORS.textMuted }}>
              (esaminati {contaRes.esaminati}, altri anni {contaRes.altri_anni}, anno non
              determinabile {contaRes.non_determinati}, errori {contaRes.errori})
            </span>
          </div>
          <div style={{ color: COLORS.textMuted }}>
            {Object.entries(contaRes.per_anno || {})
              .map(([a, n]) => `${a}: ${n}`)
              .join(' · ')}
          </div>
        </div>
      )}
    </div>
  );
}

function GoogleSheetsLedgerTab() {
  const [config, setConfig] = useState({ spreadsheet_id: '', folder_id: '' });
  const [manifest, setManifest] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [duplicateAudit, setDuplicateAudit] = useState(null);
  const [driveFolderLinks, setDriveFolderLinks] = useState('');

  const load = useCallback(async () => {
    const [cfg, man] = await Promise.all([
      api.get('/api/admin/google-sheets-ledger/config'),
      api.get('/api/admin/google-sheets-ledger/manifest'),
    ]);
    setConfig({ spreadsheet_id: cfg.data.spreadsheet_id || '', folder_id: cfg.data.folder_id || '' });
    setManifest(man.data.fogli || []);
  }, []);

  useEffect(() => { load().catch(() => {}); }, [load]);

  async function saveConfig() {
    setBusy(true);
    try {
      await api.post('/api/admin/google-sheets-ledger/config', config);
      toast.success('Registro Drive configurato');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Configurazione non riuscita');
    } finally { setBusy(false); }
  }

  async function auditDuplicates() {
    setBusy(true);
    try {
      const response = await api.get('/api/admin/google-sheets-ledger/duplicate-audit');
      setDuplicateAudit(response.data);
      toast.success(`Controllati ${response.data.totale_file || 0} file Drive`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Audit duplicati non riuscito');
    } finally { setBusy(false); }
  }

  async function auditFolderDuplicates() {
    const folderIds = [...driveFolderLinks.matchAll(/folders\/([A-Za-z0-9_-]+)/g)].map(match => match[1]);
    if (!folderIds.length) return toast.error('Incolla almeno un link cartella Drive');
    setBusy(true);
    try {
      const response = await api.post('/api/admin/google-sheets-ledger/duplicate-audit-folders', { folder_ids: [...new Set(folderIds)] });
      setDuplicateAudit(response.data);
      toast.success(`Controllati ${response.data.totale_file || 0} file in ${response.data.cartelle_visitate || 0} cartelle`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Audit cartelle non riuscito');
    } finally { setBusy(false); }
  }

  async function run(action) {
    setBusy(true);
    try {
      const started = await api.post(`/api/admin/google-sheets-ledger/jobs/${action}`);
      let job = started.data;
      while (job.status === 'running') {
        await new Promise(resolve => setTimeout(resolve, 5000));
        job = (await api.get(`/api/admin/google-sheets-ledger/jobs/${job.job_id}`)).data;
      }
      if (job.status === 'failed') throw new Error(job.error || 'Elaborazione non riuscita');
      const data = job.result || {};
      setResult({ action, ...data });
      setConfig(current => ({ ...current, spreadsheet_id: data.spreadsheet_id || current.spreadsheet_id }));
      if (action === 'audit') {
        if (data.pronto_cutover) toast.success('Archivio Drive pronto per il passaggio');
        else toast.error('Passaggio bloccato: archivi mancanti o non coerenti');
        return;
      }
      const errors = (data.fogli || []).reduce((sum, row) => sum + (row.numero_errori || 0), 0);
      if (errors) toast.error(`${errors} errori nel registro`);
      else toast.success(action === 'sync' ? 'Registro Google Sheets sincronizzato' : 'Registro ricostruibile');
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || 'Operazione non riuscita');
    } finally { setBusy(false); }
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Card title="Registro dati su Google Drive">
        <p style={{ fontSize: 13, color: COLORS.textMuted, lineHeight: 1.6 }}>
          Un solo file Google Sheets, un foglio per ogni archivio. Ogni foglio ha un
          progressivo proprio; canonical_id conserva l'identità originale e operation_id
          collega fattura, pagamento e movimento bancario. Il payload JSON permette la ricostruzione completa.
        </p>
        <div style={{ display: 'grid', gap: 10, gridTemplateColumns: '1fr 1fr auto' }}>
          <Input value={config.spreadsheet_id} onChange={e => setConfig({ ...config, spreadsheet_id: e.target.value })} placeholder="ID file Google Sheets (se esiste)" />
          <Input value={config.folder_id} onChange={e => setConfig({ ...config, folder_id: e.target.value })} placeholder="ID cartella Drive (per crearlo)" />
          <Button onClick={saveConfig} disabled={busy || (!config.spreadsheet_id && !config.folder_id)}>Salva</Button>
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
          <Button variant="primary" onClick={() => run('sync')} disabled={busy || (!config.spreadsheet_id && !config.folder_id)}>
            {busy ? 'Elaborazione...' : 'Sincronizza tutto'}
          </Button>
          <Button variant="secondary" onClick={() => run('validate')} disabled={busy || !config.spreadsheet_id}>
            Verifica ricostruzione
          </Button>
          <Button variant="secondary" onClick={() => run('audit')} disabled={busy || !config.spreadsheet_id}>
            Audit migrazione
          </Button>
          <Button variant="secondary" onClick={auditDuplicates} disabled={busy || !config.folder_id}>
            Controlla duplicati Drive
          </Button>
          {result?.spreadsheet_url && <a href={result.spreadsheet_url} target="_blank" rel="noreferrer">Apri Google Sheets</a>}
        </div>
      </Card>
      {duplicateAudit && (
        <Card title="Duplicati Drive (sola lettura)">
          <div>{duplicateAudit.totale_file || 0} file · {duplicateAudit.gruppi_duplicati || 0} gruppi · {duplicateAudit.file_duplicati_eccedenti || 0} copie eccedenti · {((duplicateAudit.spazio_recuperabile_bytes || 0) / 1048576).toFixed(2)} MB recuperabili</div>
          {(duplicateAudit.duplicati || []).map(group => (
            <div key={group.chiave} style={{ padding: '8px 0', borderBottom: `1px solid ${COLORS.border}` }}>
              <strong>{group.file?.[0]?.name || group.chiave}</strong> · {group.file?.length || 0} copie · {group.metodo}
            </div>
          ))}
        </Card>
      )}
      <Card title="Controllo cartelle Drive indicate">
        <textarea value={driveFolderLinks} onChange={e => setDriveFolderLinks(e.target.value)} placeholder="Incolla uno o più link di cartelle Drive" rows={5} style={{ width: '100%', padding: 10, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.sm }} />
        <Button variant="secondary" onClick={auditFolderDuplicates} disabled={busy || !driveFolderLinks.trim()} style={{ marginTop: 10 }}>
          Controlla ricorsivamente
        </Button>
      </Card>
      <Card title={`Fogli previsti (${manifest.length})`}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 8 }}>
          {manifest.map(item => (
            <div key={item.foglio} style={{ padding: 10, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.sm }}>
              <strong>{item.foglio}</strong><br />
              <small>{item.prefisso}-00000001 · {item.collezione}</small>
            </div>
          ))}
        </div>
      </Card>
      {result && (
        <Card title={result.action === 'audit' ? 'Audit migrazione MongoDB → Drive' : (result.action === 'validate' ? 'Esito verifica ricostruzione' : 'Esito sincronizzazione')}>
          {result.action === 'audit' && (
            <div style={{ marginBottom: 12, color: result.pronto_cutover ? COLORS.success : COLORS.danger }}>
              <strong>{result.pronto_cutover ? 'PRONTO AL PASSAGGIO' : 'PASSAGGIO BLOCCATO'}</strong>
              <div>{(result.collezioni_non_migrate || []).length} collezioni non migrate · {result.totale_non_migrate || 0} righe</div>
            </div>
          )}
          {(result.fogli || []).map(item => (
            <div key={item.foglio} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${COLORS.border}` }}>
              <span>{item.foglio}</span>
              <strong>{result.action === 'audit' ? `${item.sorgente ?? 0} → ${item.drive ?? 0}` : (item.righe ?? item.valide ?? 0)}{(item.numero_errori || item.errori) ? ` · ${item.numero_errori || item.errori} errori` : ''}</strong>
            </div>
          ))}
          {result.action === 'audit' && (result.collezioni_non_migrate || []).map(item => (
            <div key={item.collezione} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${COLORS.border}` }}>
              <span>{item.collezione}</span><strong>{item.righe}</strong>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}


function RollbackDatiTab() {
  const [sezioni, setSezioni] = useState([]);
  const [periodi, setPeriodi] = useState([]);
  const [loading, setLoading] = useState(true);
  const [conferma, setConferma] = useState(null); // { sezione, periodo, totale, dettaglio } | null
  const [contando, setContando] = useState(null); // `${sezione}:${periodo}` in corso
  const [eliminando, setEliminando] = useState(false);
  const [esito, setEsito] = useState(null); // { tipo: 'ok'|'errore', messaggio } | null

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/admin/rollback/sezioni');
        setSezioni(res.data.sezioni || []);
        setPeriodi(res.data.periodi || []);
      } catch (e) {
        setEsito({ tipo: 'errore', messaggio: 'Impossibile caricare le sezioni: ' + (e.response?.data?.detail || e.message) });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const chiediConferma = async (sezioneChiave, sezioneLabel, periodoChiave, periodoLabel) => {
    const key = `${sezioneChiave}:${periodoChiave}`;
    setContando(key);
    setEsito(null);
    try {
      const res = await api.get(`/api/admin/rollback/${sezioneChiave}/conta`, { params: { periodo: periodoChiave } });
      setConferma({
        sezioneChiave, sezioneLabel, periodoChiave, periodoLabel,
        totale: res.data.totale, dettaglio: res.data.dettaglio,
        dataDa: res.data.data_da, dataA: res.data.data_a,
      });
    } catch (e) {
      setEsito({ tipo: 'errore', messaggio: 'Errore nel conteggio: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setContando(null);
    }
  };

  const confermaEliminazione = async () => {
    if (!conferma) return;
    setEliminando(true);
    try {
      const res = await api.delete(`/api/admin/rollback/${conferma.sezioneChiave}`, { params: { periodo: conferma.periodoChiave } });
      setEsito({
        tipo: 'ok',
        messaggio: `Eliminati ${res.data.totale_eliminati} record da "${conferma.sezioneLabel}" (${conferma.periodoLabel}, dal ${conferma.dataDa} al ${conferma.dataA}).`,
      });
      setConferma(null);
    } catch (e) {
      setEsito({ tipo: 'errore', messaggio: 'Errore durante l\'eliminazione: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setEliminando(false);
    }
  };

  if (loading) {
    return <div style={{ padding: 24, color: COLORS.textMuted }}>Caricamento sezioni...</div>;
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
          background: COLORS.warningLight,
          border: `1px solid ${COLORS.warningLight}`,
          borderRadius: BORDER_RADIUS.md,
          padding: '12px 14px',
          marginBottom: 16,
          fontSize: 13,
          color: COLORS.warning,
        }}
      >
        <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <strong>Strumento per controlli di precisione.</strong> Elimina i dati reali di un
          periodo da una sezione — usalo per verificare che, dopo un re-import, i calcoli
          tornino corretti. L'operazione è irreversibile: viene sempre mostrato il numero
          esatto di record coinvolti prima di chiedere conferma.
        </div>
      </div>

      {esito && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 14px',
            borderRadius: BORDER_RADIUS.md,
            marginBottom: 16,
            fontSize: 13,
            fontWeight: 600,
            background: esito.tipo === 'ok' ? COLORS.successLight : COLORS.dangerLight,
            color: esito.tipo === 'ok' ? COLORS.success : COLORS.danger,
          }}
        >
          {esito.tipo === 'ok' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          {esito.messaggio}
        </div>
      )}

      {/* Pulizia cartella DRIVE per anno: complemento del rollback — senza
          questa, i file XML restano su Drive e la sincronizzazione oraria
          + la quadratura reimporterebbero tutto (richiesta utente 10/07). */}
      <PuliziaDriveFattureCard />

      <div style={{ display: 'grid', gap: 12 }}>
        {sezioni.map(sez => (
          <div
            key={sez.chiave}
            style={{
              background: COLORS.card,
              border: `1px solid ${COLORS.border}`,
              borderRadius: BORDER_RADIUS.lg,
              padding: 14,
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 14, color: COLORS.primary, marginBottom: 10 }}>
              {sez.label}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {periodi.map(p => {
                const key = `${sez.chiave}:${p.chiave}`;
                const isLoading = contando === key;
                return (
                  <Button
                    key={p.chiave}
                    variant="danger"
                    size="sm"
                    onClick={() => chiediConferma(sez.chiave, sez.label, p.chiave, p.label)}
                    disabled={isLoading}
                    iconLeft={isLoading ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                  >
                    {p.label}
                  </Button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Modale di conferma */}
      {conferma && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => !eliminando && setConferma(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.55)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 2000, padding: 16,
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: COLORS.card, borderRadius: BORDER_RADIUS.lg, maxWidth: 440, width: '100%',
              padding: 20, position: 'relative', boxShadow: SHADOWS.modal,
            }}
          >
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => !eliminando && setConferma(null)}
              aria-label="Chiudi"
              style={{
                position: 'absolute', top: 8, right: 8, width: 40, height: 40, padding: 0,
                color: COLORS.textMuted,
              }}
            >
              <X size={18} />
            </Button>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, color: COLORS.danger }}>
              <AlertTriangle size={20} />
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Confermi l'eliminazione?</h3>
            </div>

            <p style={{ fontSize: 13, color: COLORS.text, margin: '0 0 12px' }}>
              Stai per eliminare in modo permanente <strong>{conferma.totale}</strong> record
              da <strong>{conferma.sezioneLabel}</strong> — periodo <strong>{conferma.periodoLabel}</strong>
              {' '}(dal {conferma.dataDa} al {conferma.dataA}).
            </p>

            {conferma.dettaglio && conferma.dettaglio.length > 0 && (
              <div style={{ background: COLORS.bgAlt, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: '8px 12px', marginBottom: 16, fontSize: 12 }}>
                {conferma.dettaglio.map(d => (
                  <div key={d.collezione} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                    <span style={{ color: COLORS.textMuted }}>{d.collezione}</span>
                    <span style={{ fontWeight: 700 }}>{d.count}</span>
                  </div>
                ))}
              </div>
            )}

            {conferma.totale === 0 ? (
              <div style={{ fontSize: 12, color: COLORS.textMuted, fontStyle: 'italic' }}>
                Nessun record da eliminare in questo periodo.
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <Button variant="secondary" onClick={() => setConferma(null)} disabled={eliminando}>
                  Annulla
                </Button>
                <Button
                  variant="danger"
                  onClick={confermaEliminazione}
                  disabled={eliminando}
                  iconLeft={eliminando ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                >
                  Elimina definitivamente
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Collaudo automatico (richiesta utente 18/07/2026, audit esterno P-residuo
// "Pagina Admin Esito ultimo collaudo"): mostra l'ultimo report degli
// invarianti (nightly 4:30 + esecuzione on-demand), lo storico e il
// dettaglio delle violazioni per check.
function CollaudoTab() {
  const [ultimo, setUltimo] = useState(null);
  const [storico, setStorico] = useState([]);
  const [loading, setLoading] = useState(true);
  const [eseguendo, setEseguendo] = useState(false);
  const [secondiEsecuzione, setSecondiEsecuzione] = useState(0);
  const [espanso, setEspanso] = useState(null); // nome check aperto
  const [errore, setErrore] = useState(null);

  const carica = async () => {
    setErrore(null);
    try {
      const [u, s] = await Promise.all([
        api.get('/api/collaudo/ultimo'),
        api.get('/api/collaudo/storico?limit=15'),
      ]);
      setUltimo(u.data?.checks ? u.data : null);
      setStorico(s.data?.reports || []);
    } catch (e) {
      setErrore('Impossibile caricare i report: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { carica(); }, []);

  useEffect(() => {
    if (!eseguendo) {
      setSecondiEsecuzione(0);
      return undefined;
    }
    const timer = window.setInterval(() => setSecondiEsecuzione(s => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [eseguendo]);

  const eseguiOra = async () => {
    setEseguendo(true);
    setErrore(null);
    try {
      await api.post('/api/collaudo/esegui', null, { timeout: 180000 });
      await carica();
      toast.success('Collaudo eseguito');
    } catch (e) {
      setErrore('Errore durante il collaudo: ' + (e.response?.data?.detail || e.message));
    } finally {
      setEseguendo(false);
    }
  };

  if (loading) {
    return <div style={{ padding: 24, color: COLORS.textMuted }}>Caricamento ultimo collaudo...</div>;
  }

  const formatData = iso => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('it-IT');
    } catch {
      return iso;
    }
  };

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ fontSize: 13, color: COLORS.textMuted }}>
          {ultimo?.checks_totali || 14} invarianti contabili/POS/documentali (sola lettura), eseguiti ogni notte
          alle 4:30 e on-demand qui. Ogni violazione genera un alert idempotente,
          risolto automaticamente quando il check torna pulito.
        </div>
        <Button variant="primary" onClick={eseguiOra} disabled={eseguendo} iconLeft={eseguendo ? undefined : '🧪'}>
          {eseguendo ? 'Eseguo...' : 'Esegui ora'}
        </Button>
      </div>

      {errore && (
        <div style={{ padding: '10px 14px', background: COLORS.dangerLight, color: COLORS.danger, borderRadius: BORDER_RADIUS.md, fontSize: 13 }}>
          {errore}
        </div>
      )}

      {eseguendo && (
        <div role="status" style={{ padding: '10px 14px', background: COLORS.primarySoft, color: COLORS.primary, borderRadius: BORDER_RADIUS.md, fontSize: 13 }}>
          Collaudo in corso da {secondiEsecuzione}s. I valori sotto sono il risultato precedente e verranno aggiornati al termine.
        </div>
      )}

      {!ultimo && !errore && (
        <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted, background: COLORS.card, borderRadius: BORDER_RADIUS.md, border: `1px solid ${COLORS.border}` }}>
          Nessun collaudo ancora eseguito. Premi "Esegui ora" per il primo.
        </div>
      )}

      {ultimo && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
            <StatCard icon="🕐" label="Ultimo collaudo" value={formatData(ultimo.eseguito_at)} accent="primary" />
            <StatCard icon="✅" label="Check puliti" value={`${ultimo.checks_totali - ultimo.checks_violati - ultimo.checks_in_errore}/${ultimo.checks_totali}`} accent={ultimo.checks_violati === 0 ? 'success' : 'primary'} />
            <StatCard icon="⚠️" label="Check con violazioni" value={ultimo.checks_violati} accent={ultimo.checks_violati > 0 ? 'warning' : 'success'} />
            <StatCard icon="❌" label="Violazioni totali" value={ultimo.violazioni_totali} accent={ultimo.violazioni_totali > 0 ? 'danger' : 'success'} />
            <StatCard icon="!" label="Check in errore" value={ultimo.checks_in_errore || 0} accent={(ultimo.checks_in_errore || 0) > 0 ? 'danger' : 'success'} />
          </div>

          <Card title="Dettaglio invarianti">
            <div style={{ display: 'grid', gap: 8 }}>
              {(ultimo.checks || []).map(c => {
                const inErrore = c.violazioni < 0;
                const pulito = c.violazioni === 0;
                const aperto = espanso === c.nome;
                return (
                  <div
                    key={c.nome}
                    style={{
                      border: `1px solid ${pulito ? COLORS.border : inErrore ? COLORS.danger : COLORS.warning}`,
                      borderRadius: BORDER_RADIUS.md,
                      background: pulito ? COLORS.card : inErrore ? COLORS.dangerLight : COLORS.warningLight,
                    }}
                  >
                    <button
                      onClick={() => setEspanso(aperto ? null : c.nome)}
                      style={{
                        width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        gap: 10, padding: '10px 14px', background: 'transparent', border: 'none', cursor: 'pointer',
                        textAlign: 'left', fontSize: 13,
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                        <span>{pulito ? '✅' : inErrore ? '❌' : '⚠️'}</span>
                        <span style={{ fontWeight: 600, color: COLORS.text }}>{c.nome}</span>
                      </span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                        <Badge variant={pulito ? 'success' : inErrore ? 'danger' : 'warning'}>
                          {inErrore ? 'errore' : `${c.violazioni} violazioni`}
                        </Badge>
                        <span style={{ color: COLORS.textMuted }}>{aperto ? '▲' : '▼'}</span>
                      </span>
                    </button>
                    {aperto && (
                      <div style={{ padding: '0 14px 12px', fontSize: 12.5, color: COLORS.textMuted }}>
                        <div style={{ marginBottom: 6 }}>{c.descrizione}</div>
                        {c.esempi?.length > 0 && (
                          <pre style={{
                            margin: 0, padding: 10, background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.sm,
                            overflowX: 'auto', fontSize: 11.5, maxHeight: 220,
                          }}>
                            {JSON.stringify(c.esempi, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        </>
      )}

      {storico.length > 1 && (
        <Card title="Storico">
          <div style={{ display: 'grid', gap: 6 }}>
            {storico.map(r => (
              <div
                key={r.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap',
                  padding: '8px 12px', borderRadius: BORDER_RADIUS.sm, background: COLORS.bgAlt, fontSize: 12.5,
                }}
              >
                <span>{formatData(r.eseguito_at)}</span>
                <span style={{ display: 'flex', gap: 10 }}>
                  <span style={{ color: r.checks_violati > 0 ? COLORS.warning : COLORS.success }}>
                    {r.checks_violati}/{r.checks_totali} check con violazioni
                  </span>
                  <span style={{ color: COLORS.textMuted }}>{r.durata_ms} ms</span>
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

