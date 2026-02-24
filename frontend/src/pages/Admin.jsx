import React, { useState, useEffect, useCallback } from "react";
import { useNavigate, useLocation } from 'react-router-dom';
import api from "../api";
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { STYLES, COLORS, button, badge, formatEuro } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

export default function Admin() {
  const { anno } = useAnnoGlobale();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dbStatus, setDbStatus] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/admin\/([\w-]+)/);
    return match ? match[1] : 'email';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/admin/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
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
    cartelle: ['INBOX']
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

  useEffect(() => {
    loadStats();
    checkHealth();
    loadSchedulerStatus();
    loadEmailAccounts();
    loadParoleChiave();
    loadSyncStatus();
  }, []);

  async function loadStats() {
    try {
      setLoading(true);
      const r = await api.get("/api/admin/stats").catch(() => ({ data: null }));
      setStats(r.data);
    } catch (e) {
      console.error("Error loading stats:", e);
    } finally {
      setLoading(false);
    }
  }

  async function checkHealth() {
    try {
      const r = await api.get("/api/health");
      setDbStatus(r.data);
    } catch (e) {
      setDbStatus({ status: "error", database: "disconnected" });
    }
  }

  async function loadSchedulerStatus() {
    // HACCP Scheduler removed - set null
    setSchedulerStatus(null);
  }

  async function loadEmailAccounts() {
    setLoadingEmails(true);
    try {
      const r = await api.get("/api/config/email-accounts");
      setEmailAccounts(r.data || []);
    } catch (e) {
      console.error("Error loading email accounts:", e);
    } finally {
      setLoadingEmails(false);
    }
  }

  async function loadParoleChiave() {
    try {
      const r = await api.get("/api/config/parole-chiave");
      setParoleChiave(r.data || {});
    } catch (e) {
      console.error("Error loading parole chiave:", e);
    }
  }

  async function saveEmailAccount(account) {
    try {
      if (account.id) {
        await api.put(`/api/config/email-accounts/${account.id}`, account);
      } else {
        await api.post("/api/config/email-accounts", account);
      }
      loadEmailAccounts();
      setEditingAccount(null);
      setShowNewForm(false);
      setNewAccount({ nome: '', email: '', app_password: '', imap_server: 'imap.gmail.com', imap_port: 993, parole_chiave: [], cartelle: ['INBOX'] });
      setNewKeywordInput('');
    } catch (e) {
      alert("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  async function deleteEmailAccount(accountId) {
    
    try {
      await api.delete(`/api/config/email-accounts/${accountId}`);
      loadEmailAccounts();
    } catch (e) {
      alert("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  async function testEmailConnection(accountId) {
    setTestingConnection(accountId);
    try {
      const r = await api.post(`/api/config/email-accounts/${accountId}/test`);
      if (r.data.success) {
        alert(`✅ Connessione riuscita!\n\nEmail nella casella: ${r.data.email_count}`);
      } else {
        alert(`❌ Connessione fallita:\n${r.data.message}`);
      }
    } catch (e) {
      alert("Errore test: " + (e.response?.data?.detail || e.message));
    } finally {
      setTestingConnection(null);
    }
  }

  async function addParolaChiave() {
    if (!newKeyword.parola.trim()) return;
    try {
      await api.post(`/api/config/parole-chiave/aggiungi?categoria=${newKeyword.categoria}&parola=${encodeURIComponent(newKeyword.parola)}`);
      loadParoleChiave();
      setNewKeyword({ ...newKeyword, parola: '' });
    } catch (e) {
      alert("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  async function removeParolaChiave(categoria, parola) {
    try {
      await api.delete(`/api/config/parole-chiave/rimuovi?categoria=${categoria}&parola=${encodeURIComponent(parola)}`);
      loadParoleChiave();
    } catch (e) {
      alert("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  const handleTriggerHACCP = async () => {
    // HACCP Scheduler removed
    alert('Modulo HACCP rimosso');
  };

  // Aggiungi parola chiave all'account (nuovo o in modifica)
  const addKeywordToAccount = (isEditing) => {
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
        parole_chiave: (editingAccount.parole_chiave || []).filter(k => k !== keyword)
      });
    } else {
      setNewAccount({
        ...newAccount,
        parole_chiave: (newAccount.parole_chiave || []).filter(k => k !== keyword)
      });
    }
  };

  // ========== FUNZIONI SINCRONIZZAZIONE ==========
  
  async function loadSyncStatus() {
    try {
      const r = await api.get("/api/sync/stato-sincronizzazione");
      setSyncStatus(r.data);
    } catch (e) {
      console.error("Error loading sync status:", e);
    }
  }
  
  async function verificaEntrateCorrette() {
    setSyncLoading(true);
    try {
      const r = await api.get(`/api/prima-nota/cassa/verifica-entrate-corrispettivi?anno=${anno}`);
      setVerificaCorrispettivi(r.data);
    } catch (e) {
      console.error("Error verifica:", e);
    }
    setSyncLoading(false);
  }
  
  async function correggiCorrispettivi() {
    
    setSyncLoading(true);
    try {
      const r = await api.post(`/api/prima-nota/cassa/fix-corrispettivi-importo?anno=${anno}`);
      alert(`Corretti ${r.data.corretti} movimenti.\nDifferenza totale: €${r.data.totale_differenza_euro?.toLocaleString('it-IT')}`);
      await verificaEntrateCorrette();
      await loadSyncStatus();
    } catch (e) {
      console.error("Error fix:", e);
      alert("Errore durante la correzione");
    }
    setSyncLoading(false);
  }
  
  async function matchFattureCassa() {
    setSyncLoading(true);
    try {
      const r = await api.post("/api/sync/match-fatture-cassa");
      alert(`Match completato:\n- Trovate: ${r.data.matched}\n- Non trovate: ${r.data.not_matched}`);
      await loadSyncStatus();
    } catch (e) {
      console.error("Error match:", e);
      alert("Errore durante il match");
    }
    setSyncLoading(false);
  }
  
  async function impostaFattureBanca() {
    
    setSyncLoading(true);
    try {
      const r = await api.post("/api/sync/fatture-to-banca");
      alert(`Aggiornate ${r.data.updated} fatture`);
      await loadSyncStatus();
    } catch (e) {
      console.error("Error:", e);
      alert("Errore");
    }
    setSyncLoading(false);
  }

  async function matchFattureBanca() {
    setSyncLoading(true);
    try {
      const r = await api.post("/api/sync/match-fatture-banca");
      alert(`Match completato:\n- Associate: ${r.data.matched}\n- Non trovate: ${r.data.not_matched}`);
      await loadSyncStatus();
    } catch (e) {
      console.error("Error match banca:", e);
      alert("Errore durante il match");
    }
    setSyncLoading(false);
  }

  const fmt = (n) => n?.toLocaleString('it-IT') || '0';

  // Styles
  const tabStyle = (isActive) => ({
    padding: '10px 16px',
    borderRadius: 8,
    border: 'none',
    background: isActive ? '#4f46e5' : 'transparent',
    color: isActive ? 'white' : '#374151',
    cursor: 'pointer',
    fontWeight: isActive ? 'bold' : 'normal',
    display: 'flex',
    alignItems: 'center',
    gap: 8
  });

  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    overflow: 'hidden'
  };

  const cardHeaderStyle = {
    padding: '12px 16px',
    borderBottom: '1px solid #dce8f4'
  };

  const cardContentStyle = {
    padding: 16
  };

  const inputStyle = {
    width: '100%',
    padding: '8px 12px',
    border: '1px solid #e2e8f0',
    borderRadius: 6,
    fontSize: 14
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
    gap: 6
  });

  const smallButtonStyle = (bg, color = 'white') => ({
    padding: '6px 12px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 12
  });

  return (
    <PageLayout title="Amministrazione" icon="⚙️" subtitle="Configurazione sistema, email e parametri">
      {/* Tabs */}
      <div style={{ marginBottom: 16, background: '#f1f5f9', padding: 4, borderRadius: 12, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        <button onClick={() => handleTabChange('email')} style={tabStyle(activeTab === 'email')}>📧 Email</button>
        <button onClick={() => handleTabChange('keywords')} style={tabStyle(activeTab === 'keywords')}>🔑 Parole Chiave</button>
        <button onClick={() => handleTabChange('fatture')} style={tabStyle(activeTab === 'fatture')}>📄 Fatture</button>
        <button onClick={() => handleTabChange('system')} style={tabStyle(activeTab === 'system')}>🗄️ Sistema</button>
        <button onClick={() => handleTabChange('sync')} style={tabStyle(activeTab === 'sync')}>🔄 Sincronizzazione</button>
        <button onClick={() => handleTabChange('manutenzione')} style={tabStyle(activeTab === 'manutenzione')}>🔧 Manutenzione</button>
        <button onClick={() => handleTabChange('export')} style={tabStyle(activeTab === 'export')}>📥 Esportazioni</button>
      </div>

      {/* TAB EMAIL */}
      {activeTab === 'email' && (
        <div style={cardStyle}>
          <div style={{ ...cardHeaderStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Account Email Configurati</h3>
            <button onClick={() => setShowNewForm(true)} style={buttonStyle('#4f46e5')}>➕ Aggiungi Email</button>
          </div>
          <div style={cardContentStyle}>
            {loadingEmails ? (
              <div style={{ textAlign: 'center', padding: 20, color: '#6080a0' }}>Caricamento...</div>
            ) : emailAccounts.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 20, color: '#6080a0' }}>Nessun account email configurato</div>
            ) : (
              <div style={{ display: 'grid', gap: 12 }}>
                {emailAccounts.map(acc => (
                  <div key={acc.id} style={{ 
                    border: '1px solid #e2e8f0', 
                    borderRadius: 8, 
                    padding: 16, 
                    background: acc.is_env_default ? '#f0f9ff' : '#f8fafc' 
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 14 }}>
                          📧 {acc.nome}
                          {acc.is_env_default && (
                            <span style={{ fontSize: 10, background: '#dbeafe', color: '#1535a8', padding: '2px 8px', borderRadius: 4 }}>
                              Principale (da .env)
                            </span>
                          )}
                          {acc.attivo ? (
                            <span style={{ fontSize: 10, background: '#dcfce7', color: '#166534', padding: '2px 8px', borderRadius: 4 }}>Attivo</span>
                          ) : (
                            <span style={{ fontSize: 10, background: '#fee2e2', color: '#991b1b', padding: '2px 8px', borderRadius: 4 }}>Disattivo</span>
                          )}
                        </div>
                        <div style={{ fontSize: 12, color: '#6080a0', marginTop: 4 }}>{acc.email}</div>
                      </div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button onClick={() => testEmailConnection(acc.id)} disabled={testingConnection === acc.id} style={smallButtonStyle('#dce8f4', '#374151')}>
                          {testingConnection === acc.id ? '⏳' : 'Test'}
                        </button>
                        <button onClick={() => { setEditingAccount({...acc}); setEditKeywordInput(''); }} style={smallButtonStyle('#dce8f4', '#374151')}>
                          Modifica
                        </button>
                        {!acc.is_env_default && (
                          <button onClick={() => deleteEmailAccount(acc.id)} style={smallButtonStyle('#fee2e2', '#dc2626')}>
                            🗑️
                          </button>
                        )}
                      </div>
                    </div>
                    
                    {/* Password */}
                    <div style={{ fontSize: 12, color: '#6080a0', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>App Password:</span>
                      <span style={{ fontFamily: 'monospace' }}>{showPassword[acc.id] ? acc.app_password : acc.app_password_masked}</span>
                      <button 
                        onClick={() => setShowPassword({...showPassword, [acc.id]: !showPassword[acc.id]})} 
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1535a8' }}
                      >
                        {showPassword[acc.id] ? '🙈' : '👁️'}
                      </button>
                    </div>
                    
                    {/* Parole chiave come tag separati */}
                    <div style={{ fontSize: 12 }}>
                      <span style={{ fontWeight: 500 }}>Parole Chiave:</span>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                        {(acc.parole_chiave || []).map((kw, i) => (
                          <span key={i} style={{ 
                            background: '#e0e7ff', 
                            color: '#3730a3', 
                            padding: '4px 10px', 
                            borderRadius: 20, 
                            fontSize: 11,
                            fontWeight: 500
                          }}>
                            {kw}
                          </span>
                        ))}
                        {(!acc.parole_chiave || acc.parole_chiave.length === 0) && (
                          <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>Nessuna (accetta tutte le email)</span>
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
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>➕ Nuovo Account Email</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Nome Account</label>
                    <input 
                      value={newAccount.nome} 
                      onChange={e => setNewAccount({...newAccount, nome: e.target.value})} 
                      placeholder="es. Commercialista" 
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Email</label>
                    <input 
                      type="email" 
                      value={newAccount.email} 
                      onChange={e => setNewAccount({...newAccount, email: e.target.value})} 
                      placeholder="email@esempio.com" 
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>App Password</label>
                    <input 
                      type="password" 
                      value={newAccount.app_password} 
                      onChange={e => setNewAccount({...newAccount, app_password: e.target.value})} 
                      placeholder="Password app Google" 
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Server IMAP</label>
                    <input 
                      value={newAccount.imap_server} 
                      onChange={e => setNewAccount({...newAccount, imap_server: e.target.value})} 
                      style={inputStyle}
                    />
                  </div>
                  
                  {/* Parole Chiave - Campi separati */}
                  <div style={{ gridColumn: 'span 2' }}>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Parole Chiave</label>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <input 
                        value={newKeywordInput} 
                        onChange={e => setNewKeywordInput(e.target.value)} 
                        placeholder="Aggiungi parola chiave..." 
                        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addKeywordToAccount(false))}
                        style={inputStyle}
                      />
                      <button type="button" onClick={() => addKeywordToAccount(false)} style={smallButtonStyle('#4f46e5')}>➕</button>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {(newAccount.parole_chiave || []).map((kw, i) => (
                        <span key={i} style={{ 
                          background: '#e0e7ff', 
                          color: '#3730a3', 
                          padding: '4px 10px', 
                          borderRadius: 20, 
                          fontSize: 11,
                          fontWeight: 500,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6
                        }}>
                          {kw}
                          <button 
                            onClick={() => removeKeywordFromAccount(kw, false)} 
                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: '#ef4444' }}
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                  <button onClick={() => saveEmailAccount(newAccount)} style={buttonStyle('#16a34a')}>✔️ Salva</button>
                  <button onClick={() => { setShowNewForm(false); setNewKeywordInput(''); }} style={buttonStyle('#dce8f4', '#374151')}>✕ Annulla</button>
                </div>
              </div>
            )}

            {/* Form Modifica Account */}
            {editingAccount && (
              <div style={{ marginTop: 20, borderTop: '1px solid #e2e8f0', paddingTop: 20 }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>
                  ✏️ Modifica Account: {editingAccount.nome}
                  {editingAccount.is_env_default && <span style={{ fontSize: 10, color: '#6080a0', marginLeft: 8 }}>(Email Principale da .env)</span>}
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Nome Account</label>
                    <input 
                      value={editingAccount.nome} 
                      onChange={e => setEditingAccount({...editingAccount, nome: e.target.value})} 
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Email</label>
                    <input 
                      type="email" 
                      value={editingAccount.email} 
                      onChange={e => setEditingAccount({...editingAccount, email: e.target.value})} 
                      disabled={editingAccount.is_env_default}
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>App Password</label>
                    <input 
                      type="password" 
                      value={editingAccount.app_password || ''} 
                      onChange={e => setEditingAccount({...editingAccount, app_password: e.target.value})} 
                      placeholder="Lascia vuoto per non modificare" 
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Attivo</label>
                    <select 
                      value={editingAccount.attivo ? 'true' : 'false'} 
                      onChange={e => setEditingAccount({...editingAccount, attivo: e.target.value === 'true'})} 
                      style={inputStyle}
                    >
                      <option value="true">Si</option>
                      <option value="false">No</option>
                    </select>
                  </div>
                  
                  {/* Parole Chiave - Campi separati */}
                  <div style={{ gridColumn: 'span 2' }}>
                    <label style={{ fontSize: 11, fontWeight: 500, display: 'block', marginBottom: 4 }}>Parole Chiave</label>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <input 
                        value={editKeywordInput} 
                        onChange={e => setEditKeywordInput(e.target.value)} 
                        placeholder="Aggiungi parola chiave..." 
                        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addKeywordToAccount(true))}
                        style={inputStyle}
                      />
                      <button type="button" onClick={() => addKeywordToAccount(true)} style={smallButtonStyle('#4f46e5')}>➕</button>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {(editingAccount.parole_chiave || []).map((kw, i) => (
                        <span key={i} style={{ 
                          background: '#e0e7ff', 
                          color: '#3730a3', 
                          padding: '4px 10px', 
                          borderRadius: 20, 
                          fontSize: 11,
                          fontWeight: 500,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6
                        }}>
                          {kw}
                          <button 
                            onClick={() => removeKeywordFromAccount(kw, true)} 
                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: '#ef4444' }}
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                      {(!editingAccount.parole_chiave || editingAccount.parole_chiave.length === 0) && (
                        <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: 12 }}>Nessuna parola chiave (accetta tutte le email)</span>
                      )}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                  <button onClick={() => saveEmailAccount(editingAccount)} style={buttonStyle('#16a34a')}>✔️ Salva Modifiche</button>
                  <button onClick={() => { setEditingAccount(null); setEditKeywordInput(''); }} style={buttonStyle('#dce8f4', '#374151')}>✕ Annulla</button>
                </div>
              </div>
            )}
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
            <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 16 }}>
              Queste parole chiave vengono usate per categorizzare automaticamente i documenti scaricati dalle email.
            </p>
            
            {/* Aggiungi nuova */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
              <select 
                value={newKeyword.categoria} 
                onChange={e => setNewKeyword({...newKeyword, categoria: e.target.value})} 
                style={{ ...inputStyle, minWidth: 120, width: 'auto' }}
              >
                <option value="generale">Generale</option>
                <option value="fatture">Fatture</option>
                <option value="f24">F24</option>
                <option value="buste_paga">Buste Paga</option>
              </select>
              <input 
                value={newKeyword.parola} 
                onChange={e => setNewKeyword({...newKeyword, parola: e.target.value})} 
                placeholder="Nuova parola chiave..." 
                style={{ ...inputStyle, flex: 1 }}
                onKeyDown={e => e.key === 'Enter' && addParolaChiave()} 
              />
              <button onClick={addParolaChiave} style={buttonStyle('#4f46e5')}>➕ Aggiungi</button>
            </div>

            {/* Lista per categoria */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
              {['generale', 'fatture', 'f24', 'buste_paga'].map(cat => (
                <div key={cat} style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
                  <h5 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, textTransform: 'capitalize' }}>
                    {cat.replace('_', ' ')}
                  </h5>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {(paroleChiave[cat] || []).map((kw) => (
                      <span key={`${cat}-${kw}`} style={{ 
                        background: '#f1f5f9', 
                        padding: '4px 10px', 
                        borderRadius: 20, 
                        fontSize: 11,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6
                      }}>
                        {kw}
                        <button 
                          onClick={() => removeParolaChiave(cat, kw)} 
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: '#ef4444' }}
                          data-testid={`remove-keyword-${cat}-${kw}`}
                        >
                          ✕
                        </button>
                      </span>
                    ))}
                    {(!paroleChiave[cat] || paroleChiave[cat].length === 0) && (
                      <span style={{ color: '#94a3b8', fontSize: 11, fontStyle: 'italic' }}>Nessuna parola chiave</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB FATTURE */}
      {activeTab === 'fatture' && (
        <FattureAdminTab />
      )}

      {/* TAB SISTEMA */}
      {activeTab === 'system' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
          {/* Stato Sistema */}
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>🖥️ Stato Sistema</h3>
            </div>
            <div style={cardContentStyle}>
              {dbStatus && (
                <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Stato:</span>
                    <span style={{ fontWeight: 600, color: dbStatus.status === 'healthy' ? '#16a34a' : '#dc2626' }}>
                      {dbStatus.status === 'healthy' ? '✅ Online' : '❌ Offline'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Database:</span>
                    <span style={{ color: dbStatus.database === 'connected' ? '#16a34a' : '#dc2626' }}>
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
                      <span style={{ fontSize: 11 }}>{new Date(dbStatus.timestamp).toLocaleString('it-IT')}</span>
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
                <div style={{ textAlign: 'center', padding: 20, color: '#6080a0' }}>Caricamento...</div>
              ) : stats ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: 8 }}>
                  {Object.entries(stats).map(([key, value]) => (
                    <div key={key} style={{ background: '#f8fafc', padding: '8px 10px', borderRadius: 6, textAlign: 'center' }}>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#1535a8' }}>{fmt(value)}</div>
                      <div style={{ fontSize: 9, color: '#6080a0', textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: '#6080a0' }}>Nessuna statistica disponibile</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB SINCRONIZZAZIONE */}
      {activeTab === 'sync' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
          
          {/* Status Sincronizzazione */}
          <div style={cardStyle}>
            <div style={{ ...cardHeaderStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>📊 Stato Sincronizzazione</h3>
              <button onClick={loadSyncStatus} disabled={syncLoading} style={smallButtonStyle('#dce8f4', '#374151')}>🔄</button>
            </div>
            <div style={cardContentStyle}>
              {syncStatus ? (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #dce8f4' }}>
                    <span style={{ color: '#6080a0', fontSize: 13 }}>Fatture Totali</span>
                    <span style={{ fontWeight: 600 }}>{fmt(syncStatus.fatture?.totali)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #dce8f4' }}>
                    <span style={{ color: '#6080a0', fontSize: 13 }}>Fatture Pagate</span>
                    <span style={{ fontWeight: 600, color: '#16a34a' }}>{fmt(syncStatus.fatture?.pagate)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #dce8f4' }}>
                    <span style={{ color: '#6080a0', fontSize: 13 }}>Fatture → Cassa</span>
                    <span style={{ fontWeight: 600 }}>{fmt(syncStatus.fatture?.cassa)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #dce8f4' }}>
                    <span style={{ color: '#6080a0', fontSize: 13 }}>Fatture → Banca</span>
                    <span style={{ fontWeight: 600 }}>{fmt(syncStatus.fatture?.banca)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #dce8f4' }}>
                    <span style={{ color: '#6080a0', fontSize: 13 }}>Prima Nota Cassa (Entrate)</span>
                    <span style={{ fontWeight: 600, color: '#16a34a' }}>{fmt(syncStatus.prima_nota_cassa?.entrate)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #dce8f4' }}>
                    <span style={{ color: '#6080a0', fontSize: 13 }}>Prima Nota Cassa (Uscite)</span>
                    <span style={{ fontWeight: 600, color: '#dc2626' }}>{fmt(syncStatus.prima_nota_cassa?.uscite)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
                    <span style={{ color: '#6080a0', fontSize: 13 }}>Corrispettivi</span>
                    <span style={{ fontWeight: 600 }}>{fmt(syncStatus.corrispettivi)}</span>
                  </div>
                </div>
              ) : (
                <div style={{ color: '#6080a0', textAlign: 'center', padding: 20 }}>Caricamento...</div>
              )}
            </div>
          </div>
          
          {/* Verifica Corrispettivi */}
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>⚠️ Verifica Entrate {anno}</h3>
            </div>
            <div style={cardContentStyle}>
              <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                Verifica che le entrate da corrispettivi includano l&apos;IVA (Imponibile + IVA).
              </p>
              <button onClick={verificaEntrateCorrette} disabled={syncLoading} style={{ ...buttonStyle('#4f46e5'), width: '100%', marginBottom: 12 }}>
                {syncLoading ? 'Verifica in corso...' : 'Verifica Corrispettivi'}
              </button>
              
              {verificaCorrispettivi && (
                <div style={{ 
                  background: verificaCorrispettivi.status === 'OK' ? '#f0fdf4' : '#fef2f2', 
                  border: `1px solid ${verificaCorrispettivi.status === 'OK' ? '#86efac' : '#fecaca'}`,
                  borderRadius: 8, 
                  padding: 12,
                  marginTop: 8
                }}>
                  <div style={{ 
                    fontWeight: 600, 
                    color: verificaCorrispettivi.status === 'OK' ? '#16a34a' : '#dc2626',
                    marginBottom: 8
                  }}>
                    {verificaCorrispettivi.status === 'OK' ? '✓ Tutti i corrispettivi sono corretti' : '⚠ Correzione necessaria'}
                  </div>
                  <div style={{ fontSize: 12, color: '#374151' }}>
                    <div>Movimenti: {verificaCorrispettivi.totale_movimenti}</div>
                    <div>Corretti: {verificaCorrispettivi.corretti} | Errati: {verificaCorrispettivi.errati}</div>
                    {verificaCorrispettivi.differenza_totale > 0 && (
                      <div style={{ color: '#dc2626', fontWeight: 600, marginTop: 4 }}>
                        Differenza: €{verificaCorrispettivi.differenza_totale?.toLocaleString('it-IT')}
                      </div>
                    )}
                  </div>
                  
                  {verificaCorrispettivi.status !== 'OK' && (
                    <button 
                      onClick={correggiCorrispettivi} 
                      disabled={syncLoading}
                      style={{ ...buttonStyle('#dc2626'), width: '100%', marginTop: 12 }}
                    >
                      Correggi Importi (Aggiungi IVA)
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
          
          {/* Azioni Sincronizzazione */}
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>🔄 Azioni Sincronizzazione</h3>
            </div>
            <div style={{ ...cardContentStyle, display: 'grid', gap: 12 }}>
              <div>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 8 }}>
                  Cerca corrispondenze tra fatture XML e pagamenti in Prima Nota Cassa.
                </p>
                <button onClick={matchFattureCassa} disabled={syncLoading} style={{ ...buttonStyle('#dce8f4', '#374151'), width: '100%' }}>
                  Match Fatture ↔ Cassa
                </button>
              </div>
              
              <div>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 8 }}>
                  Cerca corrispondenze tra fatture e movimenti estratto conto bancario.
                </p>
                <button onClick={matchFattureBanca} disabled={syncLoading} style={{ ...buttonStyle('#dce8f4', '#374151'), width: '100%' }}>
                  Match Fatture ↔ Banca
                </button>
              </div>
              
              <div>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 8 }}>
                  Imposta le fatture senza metodo pagamento a &quot;Bonifico&quot; (banca).
                </p>
                <button onClick={impostaFattureBanca} disabled={syncLoading} style={{ ...buttonStyle('#dce8f4', '#374151'), width: '100%' }}>
                  Fatture → Bonifico
                </button>
              </div>
            </div>
          </div>
          
        </div>
      )}

      {/* TAB MANUTENZIONE - Logiche Intelligenti */}
      {activeTab === 'manutenzione' && (
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <h3 style={{ margin: 0, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              🔧 Logiche Intelligenti (Manutenzione Dati)
            </h3>
          </div>
          <div style={cardContentStyle}>
            <div style={{ 
              background: '#fef3c7', 
              padding: 12, 
              borderRadius: 8, 
              marginBottom: 20,
              fontSize: 13,
              color: '#92400e'
            }}>
              ⚠️ <strong>Nota:</strong> Queste operazioni erano automatiche ma sono state spostate qui per migliorare le performance del sito.
              Eseguile manualmente quando necessario (es. dopo import massivo di dati).
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
              {/* Ricostruzione Assegni */}
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 8px', color: '#1e293b', fontSize: 14 }}>📝 Assegni</h4>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                  Ricostruisce beneficiari mancanti e associa fatture agli assegni.
                </p>
                <button 
                  onClick={async () => {
                    
                    try {
                      const r = await api.post('/api/manutenzione/ricostruisci-assegni');
                      alert(`✅ Completato:\n• Beneficiari trovati: ${r.data.beneficiari_trovati || 0}\n• Fatture associate: ${r.data.fatture_associate || 0}\n• Date aggiornate: ${r.data.date_aggiornate || 0}`);
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ ...buttonStyle('#1535a8'), width: '100%' }}
                >
                  🔄 Ricostruisci Dati Assegni
                </button>
              </div>
              
              {/* Ricostruzione F24 */}
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 8px', color: '#1e293b', fontSize: 14 }}>📋 F24 e Riconciliazione</h4>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                  Corregge dati F24, riconcilia automaticamente movimenti bancari.
                </p>
                <button 
                  onClick={async () => {
                    
                    try {
                      const r = await api.post('/api/manutenzione/ricostruisci-f24');
                      alert(`✅ Completato:\n• F24 corretti: ${r.data.f24_corretti || 0}\n• Riconciliazioni auto: ${r.data.riconciliazioni_auto || 0}`);
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ ...buttonStyle('#15803d'), width: '100%' }}
                >
                  🔄 Ricostruisci Dati F24
                </button>
              </div>
              
              {/* Ricostruzione Fatture */}
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 8px', color: '#1e293b', fontSize: 14 }}>📄 Fatture Ricevute</h4>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                  Corregge campi mancanti, associa fornitori, rimuove duplicati.
                </p>
                <button 
                  onClick={async () => {
                    
                    try {
                      const r = await api.post('/api/manutenzione/ricostruisci-fatture');
                      alert(`✅ Completato:\n• Campi corretti: ${r.data.campi_corretti || 0}\n• Fornitori associati: ${r.data.fornitori_associati || 0}\n• Duplicati rimossi: ${r.data.duplicati_rimossi || 0}`);
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ ...buttonStyle('#d97706'), width: '100%', marginBottom: 8 }}
                >
                  🔄 Ricostruisci Dati Fatture
                </button>
                <button 
                  onClick={async () => {
                    try {
                      const r = await api.post('/api/fatture-ricevute/aggiorna-metodi-pagamento');
                      alert(`✅ Metodi pagamento aggiornati:\n• Fatture aggiornate: ${r.data.fatture_aggiornate || 0}\n• Senza fornitore/metodo: ${r.data.senza_fornitore_o_metodo || 0}\n• Fornitori con metodo: ${r.data.fornitori_con_metodo || 0}`);
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ ...buttonStyle('#15803d'), width: '100%' }}
                  data-testid="btn-aggiorna-metodi-pagamento"
                >
                  💳 Aggiorna Metodi Pagamento
                </button>
              </div>
              
              {/* Ricostruzione Corrispettivi */}
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 8px', color: '#1e293b', fontSize: 14 }}>🧾 Corrispettivi</h4>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                  Ricalcola IVA, rimuove duplicati nei corrispettivi.
                </p>
                <button 
                  onClick={async () => {
                    
                    try {
                      const r = await api.post('/api/manutenzione/ricostruisci-corrispettivi');
                      alert(`✅ Completato:\n• IVA ricalcolata: ${r.data.iva_ricalcolata || 0}\n• Duplicati rimossi: ${r.data.duplicati_rimossi || 0}`);
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ ...buttonStyle('#8b5cf6'), width: '100%' }}
                >
                  🔄 Ricostruisci Corrispettivi
                </button>
              </div>
              
              {/* Ricostruzione Salari */}
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 8px', color: '#1e293b', fontSize: 14 }}>👥 Salari e Cedolini</h4>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                  Pulisce righe vuote, corregge dati salari.
                </p>
                <button 
                  onClick={async () => {
                    
                    try {
                      const r = await api.post('/api/manutenzione/ricostruisci-salari');
                      alert(`✅ Completato:\n• Dipendenti associati: ${r.data.dipendenti_associati || 0}\n• Netti corretti: ${r.data.netti_corretti || 0}`);
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ ...buttonStyle('#ec4899'), width: '100%' }}
                >
                  🔄 Ricostruisci Dati Salari
                </button>
              </div>
              
              {/* Analytics */}
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 8px', color: '#1e293b', fontSize: 14 }}>📊 Analytics</h4>
                <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                  Visualizza stato delle collezioni database.
                </p>
                <button 
                  onClick={async () => {
                    
                    try {
                      const r = await api.get('/api/manutenzione/stato-collezioni');
                      const cols = r.data.collezioni || {};
                      let msg = '📊 Stato Collezioni:\n\n';
                      for (const [nome, info] of Object.entries(cols)) {
                        msg += `• ${nome}: ${info.documenti || 0} documenti\n`;
                      }
                      alert(msg);
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ ...buttonStyle('#06b6d4'), width: '100%' }}
                >
                  📊 Verifica Stato Collezioni
                </button>
              </div>
            </div>
            
            {/* Pulsante Esegui Tutti */}
            <div style={{ marginTop: 24, padding: 16, background: '#fef2f2', borderRadius: 8, border: '1px solid #fecaca' }}>
              <h4 style={{ margin: '0 0 8px', color: '#991b1b', fontSize: 14 }}>⚠️ Esegui Tutte le Manutenzioni</h4>
              <p style={{ fontSize: 12, color: '#7f1d1d', marginBottom: 12 }}>
                Esegue tutte le operazioni di manutenzione in sequenza. Potrebbe richiedere alcuni minuti.
              </p>
              <button 
                onClick={async () => {
                  
                  try {
                    const results = [];
                    results.push(await api.post('/api/manutenzione/ricostruisci-assegni').catch(e => ({ data: { error: e.message } })));
                    results.push(await api.post('/api/manutenzione/ricostruisci-f24').catch(e => ({ data: { error: e.message } })));
                    results.push(await api.post('/api/manutenzione/ricostruisci-fatture').catch(e => ({ data: { error: e.message } })));
                    results.push(await api.post('/api/manutenzione/ricostruisci-corrispettivi').catch(e => ({ data: { error: e.message } })));
                    results.push(await api.post('/api/manutenzione/ricostruisci-salari').catch(e => ({ data: { error: e.message } })));
                    
                    alert('✅ Tutte le manutenzioni completate!\n\nRicarica la pagina per vedere i risultati.');
                  } catch (e) {
                    alert('Errore: ' + e.message);
                  }
                }}
                style={{ ...buttonStyle('#dc2626'), width: '100%' }}
              >
                🔄 Esegui Tutte le Manutenzioni
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB ESPORTAZIONI */}
      {activeTab === 'export' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>📄 Esporta Fatture</h3>
            </div>
            <div style={cardContentStyle}>
              <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                Esporta tutte le fatture dell&apos;anno {anno} in formato Excel.
              </p>
              <button 
                onClick={() => window.open(`${api.defaults.baseURL}/api/exports/invoices?anno=${anno}`, '_blank')}
                style={{ ...buttonStyle('#4f46e5'), width: '100%' }}
              >
                📥 Scarica Excel Fatture
              </button>
            </div>
          </div>

          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>📄 Esporta Prima Nota</h3>
            </div>
            <div style={cardContentStyle}>
              <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                Esporta prima nota cassa/banca dell&apos;anno {anno}.
              </p>
              <div style={{ display: 'grid', gap: 8 }}>
                <button 
                  onClick={() => window.open(`${api.defaults.baseURL}/api/exports/prima-nota-cassa?anno=${anno}`, '_blank')}
                  style={{ ...buttonStyle('#dce8f4', '#374151'), width: '100%' }}
                >
                  📥 Prima Nota Cassa
                </button>
                <button 
                  onClick={() => window.open(`${api.defaults.baseURL}/api/exports/prima-nota-banca?anno=${anno}`, '_blank')}
                  style={{ ...buttonStyle('#dce8f4', '#374151'), width: '100%' }}
                >
                  📥 Prima Nota Banca
                </button>
              </div>
            </div>
          </div>

          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>📄 Documentazione API</h3>
            </div>
            <div style={cardContentStyle}>
              <p style={{ fontSize: 12, color: '#6080a0', marginBottom: 12 }}>
                Accedi alla documentazione Swagger delle API del sistema.
              </p>
              <button 
                onClick={() => window.open(`${api.defaults.baseURL}/docs`, '_blank')}
                style={{ ...buttonStyle('#dce8f4', '#374151'), width: '100%' }}
              >
                📄 Apri Swagger Docs
              </button>
            </div>
          </div>
        </div>
      )}
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
    overflow: 'hidden'
  };

  const cardHeaderStyle = {
    padding: '12px 16px',
    borderBottom: '1px solid #dce8f4'
  };

  const cardContentStyle = {
    padding: 16
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
    justifyContent: 'center'
  });

  const smallButtonStyle = (bg, color = 'white') => ({
    padding: '6px 12px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 12
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

  const handleSetMetodoPagamento = async (metodo) => {
    if (!confirmAction) {
      setConfirmAction({ type: 'set_metodo', metodo });
      return;
    }
    
    setUpdating(true);
    try {
      const res = await api.post('/api/admin/fatture-set-metodo-pagamento', { metodo_pagamento: metodo });
      alert(`✅ ${res.data.message}\n\nFatture aggiornate: ${res.data.updated}`);
      loadFattureStats();
    } catch (e) {
      alert('❌ Errore: ' + (e.response?.data?.detail || e.message));
    }
    setUpdating(false);
    setConfirmAction(null);
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
      {/* Stats Metodi Pagamento */}
      <div style={cardStyle}>
        <div style={cardHeaderStyle}>
          <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>📄 Metodi di Pagamento Fatture</h3>
        </div>
        <div style={cardContentStyle}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 20, color: '#6080a0' }}>Caricamento...</div>
          ) : fattureStats ? (
            <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f1f5f9' }}>
                <span style={{ fontWeight: 600 }}>Totale Fatture:</span>
                <span style={{ fontWeight: 700, color: '#1535a8' }}>{fattureStats.totale}</span>
              </div>
              
              {fattureStats.metodi_pagamento?.map((m, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <span>{m._id || '(Nessuno)'}</span>
                  <span style={{ fontWeight: 500 }}>{m.count}</span>
                </div>
              ))}
              
              <div style={{ 
                marginTop: 12, 
                padding: 12, 
                background: fattureStats.senza_metodo > 0 ? '#fef3c7' : '#dcfce7', 
                borderRadius: 8,
                border: `1px solid ${fattureStats.senza_metodo > 0 ? '#fcd34d' : '#86efac'}`
              }}>
                <div style={{ fontWeight: 600, color: fattureStats.senza_metodo > 0 ? '#92400e' : '#166534' }}>
                  {fattureStats.senza_metodo > 0 ? '⚠️' : '✅'} Fatture SENZA metodo: {fattureStats.senza_metodo}
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
          <h3 style={{ margin: 0, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>⚙️ Azioni Massive</h3>
        </div>
        <div style={cardContentStyle}>
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ padding: 12, background: '#f8fafc', borderRadius: 8 }}>
              <p style={{ fontSize: 12, color: '#475569', marginBottom: 8 }}>
                Imposta metodo di pagamento <strong>&quot;Bonifico&quot;</strong> per tutte le fatture che non hanno un metodo specificato.
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
                    style={smallButtonStyle('#dce8f4', '#374151')}
                  >
                    ✕ Annulla
                  </button>
                </div>
              ) : (
                <button 
                  onClick={() => handleSetMetodoPagamento('Bonifico')}
                  disabled={loading || (fattureStats?.senza_metodo === 0)}
                  style={buttonStyle(loading || (fattureStats?.senza_metodo === 0) ? '#ccc' : '#4f46e5')}
                >
                  🏦 Imposta &quot;Bonifico&quot; ({fattureStats?.senza_metodo || 0} fatture)
                </button>
              )}
            </div>
            
            <div style={{ padding: 12, background: '#fef2f2', borderRadius: 8, border: '1px solid #fecaca' }}>
              <p style={{ fontSize: 12, color: '#991b1b', marginBottom: 0 }}>
                <strong>⚠️ Attenzione:</strong> Le azioni massive modificano molti record. Usa con cautela.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Refresh */}
      <div style={{ ...cardStyle, gridColumn: 'span 2' }}>
        <div style={{ ...cardContentStyle, display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={loadFattureStats} disabled={loading} style={smallButtonStyle('#dce8f4', '#374151')}>
            🔄 Aggiorna Stats
          </button>
        </div>
      </div>
    </div>
  );
}
