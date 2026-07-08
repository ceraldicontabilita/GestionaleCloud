import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, SHADOWS, BORDER_RADIUS, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useHashState } from '../hooks/useHashState';
import { Button, Badge, StatCard, Card, Tabs, Input, Select } from '../components/ds';
import { Trash2, AlertTriangle, X, Loader2, CheckCircle2 } from 'lucide-react';

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

  // Google Drive — import fatture
  const [driveStatus, setDriveStatus] = useState(null);
  const [syncingDrive, setSyncingDrive] = useState(false);
  const [driveMsg, setDriveMsg] = useState(null);

  // Sincronizzazione dati
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [verificaCorrispettivi, setVerificaCorrispettivi] = useState(null);
  const [initialLoad, setInitialLoad] = useState(true);

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
    loadDriveStatus();

    // Polling silenzioso ogni 5 minuti
    const interval = setInterval(() => loadDashboardSummary(true), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [loadDashboardSummary]);

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

  async function loadDriveStatus() {
    try {
      const r = await api.get('/api/fatture/drive/status');
      setDriveStatus(r.data || null);
    } catch (e) {
      console.error('Error loading Drive status:', e);
    }
  }

  async function syncDriveNow() {
    setSyncingDrive(true);
    setDriveMsg(null);
    try {
      // Il backend avvia il sync in background e risponde subito:
      // qui si fa polling dello stato finché il giro non è finito
      // (niente più timeout HTTP con tanti file da elaborare).
      const r = await api.post('/api/fatture/drive/sync');
      const d = r.data || {};
      if (d.status === 'not_configured' || d.status === 'error') {
        setDriveMsg({ ok: false, testo: d.message || 'Sincronizzazione non riuscita' });
        return;
      }
      const inizio = Date.now();
      let stato = null;
      while (Date.now() - inizio < 15 * 60 * 1000) {
        await new Promise(res => setTimeout(res, 4000));
        try {
          const s = await api.get('/api/fatture/drive/status');
          stato = s.data || null;
          if (stato && !stato.sync_running) break;
        } catch {
          // errore transitorio: riprova al prossimo giro
        }
      }
      if (stato) setDriveStatus(stato);
      if (stato?.last_error) {
        setDriveMsg({ ok: false, testo: `Sincronizzazione fallita: ${stato.last_error}` });
      } else if (stato?.sync_running) {
        setDriveMsg({
          ok: true,
          testo: 'Sincronizzazione ancora in corso: la card si aggiornerà al prossimo caricamento.',
        });
      } else {
        const lr = stato?.last_result || {};
        const dettagliErrori = (lr.details || [])
          .slice(0, 3)
          .map(x => `${x.file}: ${x.error}`)
          .join(' · ');
        setDriveMsg({
          ok: (lr.errors || 0) === 0,
          testo:
            `Sync completato: ${lr.imported || 0} importate, ${lr.duplicates || 0} già presenti, ${lr.errors || 0} errori (su ${lr.total || 0} file trovati)` +
            (dettagliErrori ? ` — ${dettagliErrori}` : ''),
        });
      }
    } catch (e) {
      setDriveMsg({
        ok: false,
        testo:
          e.response?.data?.detail ||
          e.response?.data?.message ||
          `Errore durante la sincronizzazione (${e.response?.status || e.message})`,
      });
    } finally {
      setSyncingDrive(false);
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
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function deleteEmailAccount(accountId) {
    try {
      await api.delete(`/api/config/email-accounts/${accountId}`);
      loadEmailAccounts();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function testEmailConnection(accountId) {
    setTestingConnection(accountId);
    try {
      const r = await api.post(`/api/config/email-accounts/${accountId}/test`);
      if (r.data.success) {
        alert(`✅ Connessione riuscita!\n\nEmail nella casella: ${r?.data?.email_count}`);
      } else {
        alert(`❌ Connessione fallita:\n${r?.data?.message}`);
      }
    } catch (e) {
      alert('Errore test: ' + (e.response?.data?.detail || e.message));
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
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function removeParolaChiave(categoria, parola) {
    try {
      await api.delete(
        `/api/config/parole-chiave/rimuovi?categoria=${categoria}&parola=${encodeURIComponent(parola)}`
      );
      loadParoleChiave();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
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
      alert(
        `Corretti ${r?.data?.corretti} movimenti.\nDifferenza totale: €${r?.data?.totale_differenza_euro?.toLocaleString('it-IT')}`
      );
      await verificaEntrateCorrette();
      await loadSyncStatus();
    } catch (e) {
      console.error('Error fix:', e);
      alert('Errore durante la correzione');
    }
    setSyncLoading(false);
  }

  async function matchFattureCassa() {
    setSyncLoading(true);
    try {
      const r = await api.post('/api/sync/match-fatture-cassa');
      alert(
        `Match completato:\n- Trovate: ${r?.data?.matched}\n- Non trovate: ${r?.data?.not_matched}`
      );
      await loadSyncStatus();
    } catch (e) {
      console.error('Error match:', e);
      alert('Errore durante il match');
    }
    setSyncLoading(false);
  }

  async function impostaFattureBanca() {
    setSyncLoading(true);
    try {
      const r = await api.post('/api/admin/fatture-set-metodo-pagamento', {
        metodo_pagamento: 'Bonifico',
      });
      alert(`Aggiornate ${r?.data?.updated || r.data.modified_count || 0} fatture`);
      await loadSyncStatus();
    } catch (e) {
      console.error('Error:', e);
      alert('Errore');
    }
    setSyncLoading(false);
  }

  async function matchFattureBanca() {
    setSyncLoading(true);
    try {
      const r = await api.post('/api/sync/match-fatture-banca');
      alert(
        `Match completato:\n- Associate: ${r?.data?.matched}\n- Non trovate: ${r?.data?.not_matched}`
      );
      await loadSyncStatus();
    } catch (e) {
      console.error('Error match banca:', e);
      alert('Errore durante il match');
    }
    setSyncLoading(false);
  }

  const fmt = n => n?.toLocaleString('it-IT') || '0';

  const tabItems = [
    { key: 'email', label: 'Email', icon: '📧' },
    { key: 'keywords', label: 'Parole Chiave', icon: '🔑' },
    { key: 'fatture', label: 'Fatture', icon: '📄' },
    { key: 'system', label: 'Sistema', icon: '🗄️' },
    { key: 'rollback', label: 'Rollback Dati', icon: '🗑️' },
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
                  <div style={{ gridColumn: 'span 2' }}>
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
                  <div style={{ gridColumn: 'span 2' }}>
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

          {/* CARD GOOGLE DRIVE — import fatture */}
          <div data-testid="drive-fatture-card">
            <Card
              title={
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  📂 Google Drive — Import Fatture XML
                  {driveStatus?.configured ? (
                    <Badge variant="success">Configurato</Badge>
                  ) : (
                    <Badge variant="warning">Non configurato</Badge>
                  )}
                </span>
              }
              actions={
                <Button
                  variant="primary"
                  size="sm"
                  data-testid="drive-sync-btn"
                  onClick={syncDriveNow}
                  disabled={syncingDrive || !driveStatus?.configured}
                >
                  {syncingDrive ? '⏳ Sincronizzazione...' : '🔄 Sincronizza ora'}
                </Button>
              }
            >
              <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 16 }}>
                Importa automaticamente le fatture XML e P7M (firmate) dalla cartella Google Drive configurata
                (anche ogni 15 minuti in automatico). Le credenziali (cartella + service account)
                vanno impostate come variabili d'ambiente sul backend.
              </p>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                <StatCard
                  accent="none"
                  label="Cartella (ID)"
                  value={
                    <span style={{ fontSize: 13, wordBreak: 'break-all' }}>
                      {driveStatus?.folder_id || 'non impostata'}
                    </span>
                  }
                />
                <StatCard
                  accent="none"
                  label="Ultimo sync"
                  value={
                    <span style={{ fontSize: 14 }}>
                      {driveStatus?.last_sync
                        ? new Date(driveStatus.last_sync).toLocaleString('it-IT').replaceAll('/', '-')
                        : 'mai eseguito'}
                    </span>
                  }
                />
                <StatCard
                  accent="none"
                  label="Fatture importate (totale)"
                  value={<span style={{ fontSize: 14 }}>{driveStatus?.total_imported ?? 0}</span>}
                />
              </div>

              {driveStatus?.credenziali_errore && (
                <div
                  style={{
                    marginBottom: 12,
                    padding: '8px 12px',
                    borderRadius: BORDER_RADIUS.md,
                    background: COLORS.dangerLight,
                    border: `1px solid ${COLORS.dangerLight}`,
                    fontSize: 13,
                    color: COLORS.danger,
                  }}
                >
                  ✗ Problema credenziali: {driveStatus.credenziali_errore}
                </div>
              )}

              {driveStatus?.last_result && (
                <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>
                  Ultimo giro: {driveStatus.last_result.total ?? 0} file trovati,{' '}
                  {driveStatus.last_result.imported ?? 0} importati,{' '}
                  {driveStatus.last_result.duplicates ?? 0} già presenti,{' '}
                  {driveStatus.last_result.errors ?? 0} errori.
                  {(driveStatus.last_result.details || []).length > 0 && (
                    <ul style={{ margin: '6px 0 0', paddingLeft: 18, color: COLORS.danger }}>
                      {driveStatus.last_result.details.map((d, i) => (
                        <li key={i} style={{ wordBreak: 'break-all' }}>
                          <code style={{ fontSize: 11 }}>{d.file}</code>: {d.error}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {driveMsg && (
                <div
                  style={{
                    padding: '8px 12px',
                    borderRadius: BORDER_RADIUS.md,
                    background: driveMsg.ok ? COLORS.successLight : COLORS.dangerLight,
                    border: `1px solid ${driveMsg.ok ? COLORS.successLight : COLORS.dangerLight}`,
                    fontSize: 13,
                    color: driveMsg.ok ? COLORS.success : COLORS.danger,
                  }}
                >
                  {driveMsg.ok ? '✓ ' : '✗ '}
                  {driveMsg.testo}
                </div>
              )}

              {!driveStatus?.configured && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: COLORS.primarySoft,
                    borderRadius: BORDER_RADIUS.md,
                    fontSize: 12,
                    color: COLORS.primary,
                  }}
                >
                  Imposta <code>GOOGLE_DRIVE_FATTURE_FOLDER_ID</code> e{' '}
                  <code>GOOGLE_DRIVE_SA_JSON</code> tra le variabili d'ambiente del backend, poi
                  riavvia il servizio.
                </div>
              )}
            </Card>
          </div>
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

      {/* TAB FATTURE */}
      {activeTab === 'fatture' && <FattureAdminTab />}

      {/* TAB SISTEMA */}
      {activeTab === 'system' && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: 16,
          }}
        >
          {/* Stato Sistema */}
          <Card title="🖥️ Stato Sistema">
            {dbStatus && (
              <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Stato:</span>
                  <span
                    style={{
                      fontWeight: 600,
                      color: dbStatus.status === 'healthy' ? COLORS.success : COLORS.danger,
                    }}
                  >
                    {dbStatus.status === 'healthy' ? '✅ Online' : '❌ Offline'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Database:</span>
                  <span
                    style={{ color: dbStatus.database === 'connected' ? COLORS.success : COLORS.danger }}
                  >
                    {dbStatus.database}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Versione:</span>
                  <span>{dbStatus.version}</span>
                </div>
                {dbStatus.timestamp && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Timestamp:</span>
                    <span style={{ fontSize: 11 }}>
                      {new Date(dbStatus.timestamp).toLocaleString('it-IT')}
                    </span>
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Statistiche Collections */}
          <Card title="📊 Statistiche Database" style={{ gridColumn: 'span 2' }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 20, color: COLORS.textMuted }}>
                Caricamento...
              </div>
            ) : stats ? (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                  gap: 8,
                }}
              >
                {Object.entries(stats).map(([key, value]) => (
                  <StatCard
                    key={key}
                    accent="primary"
                    label={key.replace(/_/g, ' ')}
                    value={fmt(value)}
                  />
                ))}
              </div>
            ) : (
              <div style={{ color: COLORS.textMuted }}>Nessuna statistica disponibile</div>
            )}
          </Card>
        </div>
      )}

      {activeTab === 'rollback' && <RollbackDatiTab />}

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

// Componente per gestione fatture admin
function FattureAdminTab() {
  const [fattureStats, setFattureStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);

  const loadFattureStats = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/admin/fatture-stats');
      setFattureStats(res.data);
    } catch (e) {
      console.error('Errore caricamento stats fatture:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadFattureStats();
  }, [loadFattureStats]);

  const handleSetMetodoPagamento = async metodo => {
    if (!confirmAction) {
      setConfirmAction({ type: 'set_metodo', metodo });
      return;
    }

    setUpdating(true);
    try {
      const res = await api.post('/api/admin/fatture-set-metodo-pagamento', {
        metodo_pagamento: metodo,
      });
      alert(`✅ ${res?.data?.message}\n\nFatture aggiornate: ${res?.data?.updated}`);
      loadFattureStats();
    } catch (e) {
      alert('❌ Errore: ' + (e.response?.data?.detail || e.message));
    }
    setUpdating(false);
    setConfirmAction(null);
  };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 16,
      }}
    >
      {/* Stats Metodi Pagamento */}
      <Card title="📄 Metodi di Pagamento Fatture">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 20, color: COLORS.textMuted }}>Caricamento...</div>
        ) : fattureStats ? (
          <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '8px 0',
                borderBottom: `1px solid ${COLORS.gray[100]}`,
              }}
            >
              <span style={{ fontWeight: 600 }}>Totale Fatture:</span>
              <span style={{ fontWeight: 700, color: COLORS.info }}>{fattureStats.totale}</span>
            </div>

            {fattureStats.metodi_pagamento?.map((m, i) => (
              <div
                key={i}
                style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}
              >
                <span>{m._id || '(Nessuno)'}</span>
                <span style={{ fontWeight: 500 }}>{m.count}</span>
              </div>
            ))}

            <div
              style={{
                marginTop: 12,
                padding: 12,
                background: fattureStats.senza_metodo > 0 ? COLORS.warningLight : COLORS.successLight,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${fattureStats.senza_metodo > 0 ? COLORS.warningLight : COLORS.successLight}`,
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  color: fattureStats.senza_metodo > 0 ? COLORS.warning : COLORS.success,
                }}
              >
                {fattureStats.senza_metodo > 0 ? '⚠️' : '✅'} Fatture SENZA metodo:{' '}
                {fattureStats.senza_metodo}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ color: COLORS.danger }}>Errore caricamento dati</div>
        )}
      </Card>

      {/* Azioni Massive */}
      <Card title="⚙️ Azioni Massive">
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={{ padding: 12, background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.md }}>
            <p style={{ fontSize: 12, color: COLORS.gray[600], marginBottom: 8 }}>
              Imposta metodo di pagamento <strong>&quot;Bonifico&quot;</strong> per tutte le
              fatture che non hanno un metodo specificato.
            </p>

            {confirmAction?.type === 'set_metodo' ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  variant="success"
                  onClick={() => handleSetMetodoPagamento(confirmAction.metodo)}
                  disabled={updating}
                  style={{ flex: 1 }}
                >
                  {updating ? '⏳ Aggiornando...' : '✓ Conferma'}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setConfirmAction(null)}
                  disabled={updating}
                >
                  ✕ Annulla
                </Button>
              </div>
            ) : (
              <Button
                variant="primary"
                onClick={() => handleSetMetodoPagamento('Bonifico')}
                disabled={loading || fattureStats?.senza_metodo === 0}
                style={{ width: '100%' }}
              >
                🏦 Imposta &quot;Bonifico&quot; ({fattureStats?.senza_metodo || 0} fatture)
              </Button>
            )}
          </div>

          <div
            style={{
              padding: 12,
              background: COLORS.dangerLight,
              borderRadius: BORDER_RADIUS.md,
              border: `1px solid ${COLORS.dangerLight}`,
            }}
          >
            <p style={{ fontSize: 12, color: COLORS.danger, marginBottom: 0 }}>
              <strong>⚠️ Attenzione:</strong> Le azioni massive modificano molti record. Usa con
              cautela.
            </p>
          </div>
        </div>
      </Card>

      {/* Refresh */}
      <Card style={{ gridColumn: 'span 2' }} bodyStyle={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button variant="secondary" size="sm" onClick={loadFattureStats} disabled={loading}>
          🔄 Aggiorna Stats
        </Button>
      </Card>
    </div>
  );
}
