import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { STYLES, COLORS, button, badge, formatEuro, useIsMobile, RG, pagePad } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useHashState } from '../hooks/useHashState';

export default function Admin() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dbStatus, setDbStatus] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
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

  async function loadSchedulerStatus() {
    // HACCP Scheduler removed - set null
    setSchedulerStatus(null);
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

  const handleTriggerHACCP = async () => {
    // HACCP Scheduler removed
    alert('Modulo HACCP rimosso');
  };

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

  // Styles
  const tabStyle = isActive => ({
    padding: '10px 16px',
    borderRadius: 8,
    border: 'none',
    background: isActive ? '#4f46e5' : 'transparent',
    color: isActive ? 'white' : '#374151',
    cursor: 'pointer',
    fontWeight: isActive ? 'bold' : 'normal',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  });

  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    overflow: 'hidden',
  };

  const cardHeaderStyle = {
    padding: '12px 16px',
    borderBottom: '1px solid #e5e7eb',
  };

  const cardContentStyle = {
    padding: 16,
  };

  const inputStyle = {
    width: '100%',
    padding: '8px 12px',
    border: '1px solid #e2e8f0',
    borderRadius: 6,
    fontSize: 14,
  };

  const buttonStyle = (bg, color = 'white') => ({
    padding: '8px 16px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: 13,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
  });

  const smallButtonStyle = (bg, color = 'white') => ({
    padding: '6px 12px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 12,
  });

  return (
    <PageLayout
      title="Amministrazione"
      icon="⚙️"
      subtitle="Configurazione sistema, email e parametri"
    >
      {/* Tabs */}
      <div
        style={{
          marginBottom: 16,
          background: '#f1f5f9',
          padding: 4,
          borderRadius: 12,
          display: 'flex',
          flexWrap: 'wrap',
          gap: 4,
        }}
      >
        <button onClick={() => handleTabChange('email')} style={tabStyle(activeTab === 'email')}>
          📧 Email
        </button>
        <button
          onClick={() => handleTabChange('keywords')}
          style={tabStyle(activeTab === 'keywords')}
        >
          🔑 Parole Chiave
        </button>
        <button
          onClick={() => handleTabChange('fatture')}
          style={tabStyle(activeTab === 'fatture')}
        >
          📄 Fatture
        </button>
        <button onClick={() => handleTabChange('system')} style={tabStyle(activeTab === 'system')}>
          🗄️ Sistema
        </button>
      </div>

      {/* TAB EMAIL */}
      {activeTab === 'email' && (
        <div style={{ display: 'grid', gap: 16 }}>
          <div style={cardStyle}>
            <div
              style={{
                ...cardHeaderStyle,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <h3 style={{ margin: 0, fontSize: 16 }}>Account Email Configurati</h3>
              <button onClick={() => setShowNewForm(true)} style={buttonStyle('#4f46e5')}>
                ➕ Aggiungi Email
              </button>
            </div>
            <div style={cardContentStyle}>
              {loadingEmails ? (
                <div style={{ textAlign: 'center', padding: 20, color: '#6b7280' }}>
                  Caricamento...
                </div>
              ) : emailAccounts.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 20, color: '#6b7280' }}>
                  Nessun account email configurato
                </div>
              ) : (
                <div style={{ display: 'grid', gap: 12 }}>
                  {emailAccounts.map(acc => (
                    <div
                      key={acc.id}
                      style={{
                        border: '1px solid #e2e8f0',
                        borderRadius: 8,
                        padding: 16,
                        background: acc.is_env_default ? '#f0f9ff' : '#f8fafc',
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
                            {acc.is_env_default && (
                              <span
                                style={{
                                  fontSize: 10,
                                  background: '#dbeafe',
                                  color: '#1d4ed8',
                                  padding: '2px 8px',
                                  borderRadius: 4,
                                }}
                              >
                                Principale (da .env)
                              </span>
                            )}
                            {acc.attivo ? (
                              <span
                                style={{
                                  fontSize: 10,
                                  background: '#dcfce7',
                                  color: '#166534',
                                  padding: '2px 8px',
                                  borderRadius: 4,
                                }}
                              >
                                Attivo
                              </span>
                            ) : (
                              <span
                                style={{
                                  fontSize: 10,
                                  background: '#fee2e2',
                                  color: '#991b1b',
                                  padding: '2px 8px',
                                  borderRadius: 4,
                                }}
                              >
                                Disattivo
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                            {acc.email}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button
                            onClick={() => testEmailConnection(acc.id)}
                            disabled={testingConnection === acc.id}
                            style={smallButtonStyle('#e5e7eb', '#374151')}
                          >
                            {testingConnection === acc.id ? '⏳' : 'Test'}
                          </button>
                          <button
                            onClick={() => {
                              setEditingAccount({ ...acc });
                              setEditKeywordInput('');
                            }}
                            style={smallButtonStyle('#e5e7eb', '#374151')}
                          >
                            Modifica
                          </button>
                          {!acc.is_env_default && (
                            <button
                              onClick={() => deleteEmailAccount(acc.id)}
                              style={smallButtonStyle('#fee2e2', '#dc2626')}
                            >
                              🗑️
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Password */}
                      <div
                        style={{
                          fontSize: 12,
                          color: '#6b7280',
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
                        <button
                          onClick={() =>
                            setShowPassword({ ...showPassword, [acc.id]: !showPassword[acc.id] })
                          }
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            color: '#1e3a5f',
                          }}
                        >
                          {showPassword[acc.id] ? '🙈' : '👁️'}
                        </button>
                      </div>

                      {/* Parole chiave come tag separati */}
                      <div style={{ fontSize: 12 }}>
                        <span style={{ fontWeight: 500 }}>Parole Chiave:</span>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                          {(acc.parole_chiave || []).map((kw, i) => (
                            <span
                              key={i}
                              style={{
                                background: '#e0e7ff',
                                color: '#3730a3',
                                padding: '4px 10px',
                                borderRadius: 20,
                                fontSize: 11,
                                fontWeight: 500,
                              }}
                            >
                              {kw}
                            </span>
                          ))}
                          {(!acc.parole_chiave || acc.parole_chiave.length === 0) && (
                            <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>
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
                <div style={{ marginTop: 20, borderTop: '1px solid #e2e8f0', paddingTop: 20 }}>
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
                      <input
                        value={newAccount.nome}
                        onChange={e => setNewAccount({ ...newAccount, nome: e.target.value })}
                        placeholder="es. Commercialista"
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        Email
                      </label>
                      <input
                        type="email"
                        value={newAccount.email}
                        onChange={e => setNewAccount({ ...newAccount, email: e.target.value })}
                        placeholder="email@esempio.com"
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        App Password
                      </label>
                      <input
                        type="password"
                        value={newAccount.app_password}
                        onChange={e =>
                          setNewAccount({ ...newAccount, app_password: e.target.value })
                        }
                        placeholder="Password app Google"
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        Server IMAP
                      </label>
                      <input
                        value={newAccount.imap_server}
                        onChange={e =>
                          setNewAccount({ ...newAccount, imap_server: e.target.value })
                        }
                        style={inputStyle}
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
                        <input
                          value={newKeywordInput}
                          onChange={e => setNewKeywordInput(e.target.value)}
                          placeholder="Aggiungi parola chiave..."
                          onKeyDown={e =>
                            e.key === 'Enter' && (e.preventDefault(), addKeywordToAccount(false))
                          }
                          style={inputStyle}
                        />
                        <button
                          type="button"
                          onClick={() => addKeywordToAccount(false)}
                          style={smallButtonStyle('#4f46e5')}
                        >
                          ➕
                        </button>
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {(newAccount.parole_chiave || []).map((kw, i) => (
                          <span
                            key={i}
                            style={{
                              background: '#e0e7ff',
                              color: '#3730a3',
                              padding: '4px 10px',
                              borderRadius: 20,
                              fontSize: 11,
                              fontWeight: 500,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                            }}
                          >
                            {kw}
                            <button
                              onClick={() => removeKeywordFromAccount(kw, false)}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                padding: 0,
                                color: '#ef4444',
                              }}
                            >
                              ✕
                            </button>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                    <button
                      onClick={() => saveEmailAccount(newAccount)}
                      style={buttonStyle('#16a34a')}
                    >
                      ✔️ Salva
                    </button>
                    <button
                      onClick={() => {
                        setShowNewForm(false);
                        setNewKeywordInput('');
                      }}
                      style={buttonStyle('#e5e7eb', '#374151')}
                    >
                      ✕ Annulla
                    </button>
                  </div>
                </div>
              )}

              {/* Form Modifica Account */}
              {editingAccount && (
                <div style={{ marginTop: 20, borderTop: '1px solid #e2e8f0', paddingTop: 20 }}>
                  <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>
                    ✏️ Modifica Account: {editingAccount.nome}
                    {editingAccount.is_env_default && (
                      <span style={{ fontSize: 10, color: '#6b7280', marginLeft: 8 }}>
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
                      <input
                        value={editingAccount.nome}
                        onChange={e =>
                          setEditingAccount({ ...editingAccount, nome: e.target.value })
                        }
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        Email
                      </label>
                      <input
                        type="email"
                        value={editingAccount.email}
                        onChange={e =>
                          setEditingAccount({ ...editingAccount, email: e.target.value })
                        }
                        disabled={editingAccount.is_env_default}
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        App Password
                      </label>
                      <input
                        type="password"
                        value={editingAccount.app_password || ''}
                        onChange={e =>
                          setEditingAccount({ ...editingAccount, app_password: e.target.value })
                        }
                        placeholder="Lascia vuoto per non modificare"
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        Attivo
                      </label>
                      <select
                        value={editingAccount.attivo ? 'true' : 'false'}
                        onChange={e =>
                          setEditingAccount({
                            ...editingAccount,
                            attivo: e.target.value === 'true',
                          })
                        }
                        style={inputStyle}
                      >
                        <option value="true">Si</option>
                        <option value="false">No</option>
                      </select>
                    </div>

                    {/* Parole Chiave - Campi separati */}
                    <div style={{ gridColumn: 'span 2' }}>
                      <label
                        style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        Parole Chiave
                      </label>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                        <input
                          value={editKeywordInput}
                          onChange={e => setEditKeywordInput(e.target.value)}
                          placeholder="Aggiungi parola chiave..."
                          onKeyDown={e =>
                            e.key === 'Enter' && (e.preventDefault(), addKeywordToAccount(true))
                          }
                          style={inputStyle}
                        />
                        <button
                          type="button"
                          onClick={() => addKeywordToAccount(true)}
                          style={smallButtonStyle('#4f46e5')}
                        >
                          ➕
                        </button>
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {(editingAccount.parole_chiave || []).map((kw, i) => (
                          <span
                            key={i}
                            style={{
                              background: '#e0e7ff',
                              color: '#3730a3',
                              padding: '4px 10px',
                              borderRadius: 20,
                              fontSize: 11,
                              fontWeight: 500,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                            }}
                          >
                            {kw}
                            <button
                              onClick={() => removeKeywordFromAccount(kw, true)}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                padding: 0,
                                color: '#ef4444',
                              }}
                            >
                              ✕
                            </button>
                          </span>
                        ))}
                        {(!editingAccount.parole_chiave ||
                          editingAccount.parole_chiave.length === 0) && (
                          <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: 12 }}>
                            Nessuna parola chiave (accetta tutte le email)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                    <button
                      onClick={() => saveEmailAccount(editingAccount)}
                      style={buttonStyle('#16a34a')}
                    >
                      ✔️ Salva Modifiche
                    </button>
                    <button
                      onClick={() => {
                        setEditingAccount(null);
                        setEditKeywordInput('');
                      }}
                      style={buttonStyle('#e5e7eb', '#374151')}
                    >
                      ✕ Annulla
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* CARD GOOGLE DRIVE — import fatture */}
          <div style={cardStyle} data-testid="drive-fatture-card">
            <div
              style={{
                ...cardHeaderStyle,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <h3
                style={{ margin: 0, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}
              >
                📂 Google Drive — Import Fatture XML
                {driveStatus?.configured ? (
                  <span
                    style={{
                      fontSize: 10,
                      background: 'var(--c-success-light)',
                      color: 'var(--c-success)',
                      padding: '2px 8px',
                      borderRadius: 4,
                    }}
                  >
                    Configurato
                  </span>
                ) : (
                  <span
                    style={{
                      fontSize: 10,
                      background: 'var(--c-warning-light)',
                      color: 'var(--c-warning)',
                      padding: '2px 8px',
                      borderRadius: 4,
                    }}
                  >
                    Non configurato
                  </span>
                )}
              </h3>
              <button
                data-testid="drive-sync-btn"
                onClick={syncDriveNow}
                disabled={syncingDrive || !driveStatus?.configured}
                style={buttonStyle(
                  syncingDrive || !driveStatus?.configured ? '#9ca3af' : '#1e3a5f'
                )}
              >
                {syncingDrive ? '⏳ Sincronizzazione...' : '🔄 Sincronizza ora'}
              </button>
            </div>
            <div style={cardContentStyle}>
              <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
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
                <div
                  style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: 6,
                    padding: '8px 12px',
                  }}
                >
                  <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 2, fontWeight: 500 }}>
                    Cartella (ID)
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: '#1e293b',
                      wordBreak: 'break-all',
                    }}
                  >
                    {driveStatus?.folder_id || 'non impostata'}
                  </div>
                </div>
                <div
                  style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: 6,
                    padding: '8px 12px',
                  }}
                >
                  <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 2, fontWeight: 500 }}>
                    Ultimo sync
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>
                    {driveStatus?.last_sync
                      ? new Date(driveStatus.last_sync).toLocaleString('it-IT').replaceAll('/', '-')
                      : 'mai eseguito'}
                  </div>
                </div>
                <div
                  style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: 6,
                    padding: '8px 12px',
                  }}
                >
                  <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 2, fontWeight: 500 }}>
                    Fatture importate (totale)
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>
                    {driveStatus?.total_imported ?? 0}
                  </div>
                </div>
              </div>

              {driveStatus?.credenziali_errore && (
                <div
                  style={{
                    marginBottom: 12,
                    padding: '8px 12px',
                    borderRadius: 8,
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    fontSize: 13,
                    color: '#dc2626',
                  }}
                >
                  ✗ Problema credenziali: {driveStatus.credenziali_errore}
                </div>
              )}

              {driveStatus?.last_result && (
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
                  Ultimo giro: {driveStatus.last_result.total ?? 0} file trovati,{' '}
                  {driveStatus.last_result.imported ?? 0} importati,{' '}
                  {driveStatus.last_result.duplicates ?? 0} già presenti,{' '}
                  {driveStatus.last_result.errors ?? 0} errori.
                  {(driveStatus.last_result.details || []).length > 0 && (
                    <ul style={{ margin: '6px 0 0', paddingLeft: 18, color: '#b91c1c' }}>
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
                    borderRadius: 8,
                    background: driveMsg.ok ? '#f0fdf4' : '#fef2f2',
                    border: `1px solid ${driveMsg.ok ? '#bbf7d0' : '#fecaca'}`,
                    fontSize: 13,
                    color: driveMsg.ok ? '#16a34a' : '#dc2626',
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
                    background: 'var(--c-primary-soft)',
                    borderRadius: 8,
                    fontSize: 12,
                    color: 'var(--c-primary)',
                  }}
                >
                  Imposta <code>GOOGLE_DRIVE_FATTURE_FOLDER_ID</code> e{' '}
                  <code>GOOGLE_DRIVE_SA_JSON</code> tra le variabili d'ambiente del backend, poi
                  riavvia il servizio.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB PAROLE CHIAVE GLOBALI */}
      {activeTab === 'keywords' && (
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Parole Chiave per Filtro Email (Globali)</h3>
          </div>
          <div style={cardContentStyle}>
            <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
              Queste parole chiave vengono usate per categorizzare automaticamente i documenti
              scaricati dalle email.
            </p>

            {/* Aggiungi nuova */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
              <select
                value={newKeyword.categoria}
                onChange={e => setNewKeyword({ ...newKeyword, categoria: e.target.value })}
                style={{ ...inputStyle, minWidth: 120, width: 'auto' }}
              >
                <option value="generale">Generale</option>
                <option value="fatture">Fatture</option>
                <option value="f24">F24</option>
                <option value="buste_paga">Buste Paga</option>
              </select>
              <input
                value={newKeyword.parola}
                onChange={e => setNewKeyword({ ...newKeyword, parola: e.target.value })}
                placeholder="Nuova parola chiave..."
                style={{ ...inputStyle, flex: 1 }}
                onKeyDown={e => e.key === 'Enter' && addParolaChiave()}
              />
              <button onClick={addParolaChiave} style={buttonStyle('#4f46e5')}>
                ➕ Aggiungi
              </button>
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
                  style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}
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
                      <span
                        key={`${cat}-${kw}`}
                        style={{
                          background: '#f1f5f9',
                          padding: '4px 10px',
                          borderRadius: 20,
                          fontSize: 11,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        {kw}
                        <button
                          onClick={() => removeParolaChiave(cat, kw)}
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            padding: 0,
                            color: '#ef4444',
                          }}
                          data-testid={`remove-keyword-${cat}-${kw}`}
                        >
                          ✕
                        </button>
                      </span>
                    ))}
                    {(!paroleChiave[cat] || paroleChiave[cat].length === 0) && (
                      <span style={{ color: '#94a3b8', fontSize: 11, fontStyle: 'italic' }}>
                        Nessuna parola chiave
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
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
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3
                style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}
              >
                🖥️ Stato Sistema
              </h3>
            </div>
            <div style={cardContentStyle}>
              {dbStatus && (
                <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Stato:</span>
                    <span
                      style={{
                        fontWeight: 600,
                        color: dbStatus.status === 'healthy' ? '#16a34a' : '#dc2626',
                      }}
                    >
                      {dbStatus.status === 'healthy' ? '✅ Online' : '❌ Offline'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Database:</span>
                    <span
                      style={{ color: dbStatus.database === 'connected' ? '#16a34a' : '#dc2626' }}
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
            </div>
          </div>

          {/* Statistiche Collections */}
          <div style={{ ...cardStyle, gridColumn: 'span 2' }}>
            <div style={cardHeaderStyle}>
              <h3 style={{ margin: 0, fontSize: 14 }}>📊 Statistiche Database</h3>
            </div>
            <div style={cardContentStyle}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: 20, color: '#6b7280' }}>
                  Caricamento...
                </div>
              ) : stats ? (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))',
                    gap: 8,
                  }}
                >
                  {Object.entries(stats).map(([key, value]) => (
                    <div
                      key={key}
                      style={{
                        background: '#f8fafc',
                        padding: '8px 10px',
                        borderRadius: 6,
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#1e3a5f' }}>
                        {fmt(value)}
                      </div>
                      <div style={{ fontSize: 9, color: '#6b7280', textTransform: 'capitalize' }}>
                        {key.replace(/_/g, ' ')}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: '#6b7280' }}>Nessuna statistica disponibile</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB SINCRONIZZAZIONE */}

      {/* TAB MANUTENZIONE - Logiche Intelligenti */}

      {/* TAB ESPORTAZIONI */}
    </PageLayout>
  );
}

// Componente per gestione fatture admin
function FattureAdminTab() {
  const [fattureStats, setFattureStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);

  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    overflow: 'hidden',
  };

  const cardHeaderStyle = {
    padding: '12px 16px',
    borderBottom: '1px solid #e5e7eb',
  };

  const cardContentStyle = {
    padding: 16,
  };

  const buttonStyle = (bg, color = 'white') => ({
    padding: '8px 16px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: 13,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    width: '100%',
    justifyContent: 'center',
  });

  const smallButtonStyle = (bg, color = 'white') => ({
    padding: '6px 12px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 12,
  });

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
      <div style={cardStyle}>
        <div style={cardHeaderStyle}>
          <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            📄 Metodi di Pagamento Fatture
          </h3>
        </div>
        <div style={cardContentStyle}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 20, color: '#6b7280' }}>Caricamento...</div>
          ) : fattureStats ? (
            <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '8px 0',
                  borderBottom: '1px solid #f1f5f9',
                }}
              >
                <span style={{ fontWeight: 600 }}>Totale Fatture:</span>
                <span style={{ fontWeight: 700, color: '#1e40af' }}>{fattureStats.totale}</span>
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
                  background: fattureStats.senza_metodo > 0 ? '#fef3c7' : '#dcfce7',
                  borderRadius: 8,
                  border: `1px solid ${fattureStats.senza_metodo > 0 ? '#fcd34d' : '#86efac'}`,
                }}
              >
                <div
                  style={{
                    fontWeight: 600,
                    color: fattureStats.senza_metodo > 0 ? '#92400e' : '#166534',
                  }}
                >
                  {fattureStats.senza_metodo > 0 ? '⚠️' : '✅'} Fatture SENZA metodo:{' '}
                  {fattureStats.senza_metodo}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ color: '#dc2626' }}>Errore caricamento dati</div>
          )}
        </div>
      </div>

      {/* Azioni Massive */}
      <div style={cardStyle}>
        <div style={cardHeaderStyle}>
          <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            ⚙️ Azioni Massive
          </h3>
        </div>
        <div style={cardContentStyle}>
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ padding: 12, background: '#f8fafc', borderRadius: 8 }}>
              <p style={{ fontSize: 12, color: '#475569', marginBottom: 8 }}>
                Imposta metodo di pagamento <strong>&quot;Bonifico&quot;</strong> per tutte le
                fatture che non hanno un metodo specificato.
              </p>

              {confirmAction?.type === 'set_metodo' ? (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => handleSetMetodoPagamento(confirmAction.metodo)}
                    disabled={updating}
                    style={{ ...buttonStyle('#16a34a'), flex: 1 }}
                  >
                    {updating ? '⏳ Aggiornando...' : '✓ Conferma'}
                  </button>
                  <button
                    onClick={() => setConfirmAction(null)}
                    disabled={updating}
                    style={smallButtonStyle('#e5e7eb', '#374151')}
                  >
                    ✕ Annulla
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => handleSetMetodoPagamento('Bonifico')}
                  disabled={loading || fattureStats?.senza_metodo === 0}
                  style={buttonStyle(
                    loading || fattureStats?.senza_metodo === 0 ? '#ccc' : '#4f46e5'
                  )}
                >
                  🏦 Imposta &quot;Bonifico&quot; ({fattureStats?.senza_metodo || 0} fatture)
                </button>
              )}
            </div>

            <div
              style={{
                padding: 12,
                background: '#fef2f2',
                borderRadius: 8,
                border: '1px solid #fecaca',
              }}
            >
              <p style={{ fontSize: 12, color: '#991b1b', marginBottom: 0 }}>
                <strong>⚠️ Attenzione:</strong> Le azioni massive modificano molti record. Usa con
                cautela.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Refresh */}
      <div style={{ ...cardStyle, gridColumn: 'span 2' }}>
        <div style={{ ...cardContentStyle, display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={loadFattureStats}
            disabled={loading}
            style={smallButtonStyle('#e5e7eb', '#374151')}
          >
            🔄 Aggiorna Stats
          </button>
        </div>
      </div>
    </div>
  );
}
