import React, { useState, useEffect } from 'react';
import api from '../api';
import { STYLES, COLORS, formatEuro, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

export default function IntegrazioniOpenAPI() {
  const [sdiStatus, setSdiStatus] = useState(null);
  const [xbrlStatus, setXbrlStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('sdi');
  
  // SDI State
  const [notifiche, setNotifiche] = useState([]);
  const [invioLoading, setInvioLoading] = useState(false);
  const [ricezioneLoading, setRicezioneLoading] = useState(false);
  const [ricezioneResult, setRicezioneResult] = useState(null);
  
  // XBRL State
  const [xbrlPiva, setXbrlPiva] = useState('');
  const [xbrlAnno, setXbrlAnno] = useState('');
  const [xbrlLoading, setXbrlLoading] = useState(false);
  const [xbrlResult, setXbrlResult] = useState(null);
  const [xbrlRequests, setXbrlRequests] = useState([]);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const [sdi, xbrl] = await Promise.all([
        api.get('/api/openapi/sdi/status').catch(() => ({ data: { status: 'error' } })),
        api.get('/api/openapi/xbrl/status').catch(() => ({ data: { status: 'error' } }))
      ]);
      setSdiStatus(sdi.data);
      setXbrlStatus(xbrl.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadNotifiche = async () => {
    try {
      const res = await api.get('/api/openapi/sdi/notifiche');
      setNotifiche(res.data.notifiche || []);
    } catch (e) {
      console.error(e);
    }
  };

  const riceviFatture = async () => {
    setRicezioneLoading(true);
    setRicezioneResult(null);
    try {
      const res = await api.get('/api/openapi/sdi/ricevi-fatture');
      setRicezioneResult(res.data);
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setRicezioneLoading(false);
    }
  };
  
  // XBRL Functions
  const richiediXbrl = async () => {
    if (!xbrlPiva) {
      alert('Inserisci la Partita IVA');
      return;
    }
    setXbrlLoading(true);
    setXbrlResult(null);
    try {
      const payload = { partita_iva: xbrlPiva };
      if (xbrlAnno) payload.anno_chiusura = parseInt(xbrlAnno);
      const res = await api.post('/api/openapi/xbrl/richiedi-bilancio', payload);
      setXbrlResult(res.data);
      // Refresh lista richieste
      loadXbrlRequests();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setXbrlLoading(false);
    }
  };
  
  const loadXbrlRequests = async () => {
    try {
      const res = await api.get('/api/openapi/xbrl/storico-richieste?limit=20');
      setXbrlRequests(res.data.richieste || []);
    } catch (e) {
      console.error('Errore load richieste XBRL:', e);
    }
  };
  
  const checkXbrlStatus = async (requestId) => {
    try {
      const res = await api.get(`/api/openapi/xbrl/bilancio/${requestId}`);
      alert(`Stato: ${res.data.status}\n${res.data.message || ''}`);
      loadXbrlRequests();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const cardStyle = {
    background: '#fff',
    borderRadius: 12,
    border: '1px solid #e2e8f0',
    padding: 20,
    marginBottom: 16
  };

  const tabStyle = (isActive) => ({
    padding: '12px 24px',
    background: isActive ? '#1535a8' : 'transparent',
    color: isActive ? '#fff' : '#64748b',
    border: 'none',
    borderRadius: '8px 8px 0 0',
    cursor: 'pointer',
    fontWeight: isActive ? 600 : 500,
    fontSize: 14
  });

  if (loading) {
    return (
      <div style={{ ...STYLES.pageWrapper, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ fontSize: 48 }}>⏳</div>
      </div>
    );
  }

  return (
    <PageLayout title="Integrazioni OpenAPI.it" subtitle="SDI (Fatturazione Elettronica) & XBRL (Bilanci)">
    <div style={{...STYLES.pageWrapper, padding: 0}}>
      <div style={STYLES.pageContainer}>
        <div style={STYLES.pageHeader}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>
              🔌 Integrazioni OpenAPI.it
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
              SDI (Fatturazione Elettronica) & XBRL (Bilanci)
            </p>
          </div>
          <button onClick={loadStatus} style={button('#1535a8')}>
            🔄 Aggiorna Stato
          </button>
        </div>

        <div style={STYLES.pageContent}>
          {/* Status Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16, marginBottom: 24 }}>
            {/* SDI Status */}
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>📄 SDI - Fatturazione Elettronica</h3>
                <span style={badge(sdiStatus?.api_key_configured ? 'success' : 'error')}>
                  {sdiStatus?.api_key_configured ? '✓ Configurato' : '✗ Non configurato'}
                </span>
              </div>
              <div style={{ fontSize: 13, color: '#64748b' }}>
                <div>Ambiente: <strong>{sdiStatus?.environment || 'N/A'}</strong></div>
                <div>Base URL: <code style={{ fontSize: 11 }}>{sdiStatus?.base_url}</code></div>
              </div>
            </div>

            {/* XBRL Status */}
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>📊 XBRL - Bilanci</h3>
                <span style={badge(xbrlStatus?.api_key_configured ? 'success' : 'error')}>
                  {xbrlStatus?.api_key_configured ? '✓ Configurato' : '✗ Non configurato'}
                </span>
              </div>
              <div style={{ fontSize: 13, color: '#64748b' }}>
                <div>Stato: <strong>{xbrlStatus?.status || 'N/A'}</strong></div>
                <div>Bilanci aziendali in formato XBRL</div>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', marginBottom: 20 }}>
            <button style={tabStyle(activeTab === 'sdi')} onClick={() => setActiveTab('sdi')}>
              📄 SDI
            </button>
            <button style={tabStyle(activeTab === 'xbrl')} onClick={() => { setActiveTab('xbrl'); loadXbrlRequests(); }}>
              📊 XBRL Bilanci
            </button>
            <button style={tabStyle(activeTab === 'config')} onClick={() => setActiveTab('config')}>
              ⚙️ Configurazione
            </button>
          </div>

          {/* Tab Content */}
          {activeTab === 'sdi' && (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
                {/* Ricevi Fatture */}
                <div style={cardStyle}>
                  <h4 style={{ margin: '0 0 12px', fontSize: 14 }}>📥 Ricevi Fatture</h4>
                  <p style={{ fontSize: 12, color: '#64748b', marginBottom: 12 }}>
                    Scarica le fatture passive ricevute dallo SDI.
                  </p>
                  <button 
                    onClick={riceviFatture}
                    disabled={ricezioneLoading}
                    style={{ ...button('#15803d'), width: '100%' }}
                  >
                    {ricezioneLoading ? '⏳ Caricamento...' : '📥 Ricevi Fatture SDI'}
                  </button>
                  {ricezioneResult && (
                    <div style={{ marginTop: 12, padding: 10, background: '#f0fdf4', borderRadius: 6, fontSize: 12 }}>
                      ✅ Ricevute: {ricezioneResult.fatture_ricevute}<br/>
                      📥 Importate: {ricezioneResult.fatture_importate}
                    </div>
                  )}
                </div>

                {/* Invia Fatture */}
                <div style={cardStyle}>
                  <h4 style={{ margin: '0 0 12px', fontSize: 14 }}>📤 Invia Fatture</h4>
                  <p style={{ fontSize: 12, color: '#64748b', marginBottom: 12 }}>
                    Invia le fatture attive allo SDI per la trasmissione.
                  </p>
                  <button 
                    onClick={() => alert('Vai su Fatture Emesse per inviare singole fatture')}
                    style={{ ...button('#1535a8'), width: '100%' }}
                  >
                    📤 Gestione Invii
                  </button>
                </div>

                {/* Notifiche */}
                <div style={cardStyle}>
                  <h4 style={{ margin: '0 0 12px', fontSize: 14 }}>🔔 Notifiche SDI</h4>
                  <p style={{ fontSize: 12, color: '#64748b', marginBottom: 12 }}>
                    Verifica esiti, scarti e mancate consegne.
                  </p>
                  <button 
                    onClick={loadNotifiche}
                    style={{ ...button('#d97706'), width: '100%' }}
                  >
                    🔔 Carica Notifiche
                  </button>
                </div>
              </div>

              {/* Notifiche List */}
              {notifiche.length > 0 && (
                <div style={cardStyle}>
                  <h4 style={{ margin: '0 0 12px' }}>Notifiche Recenti</h4>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        <th style={{ padding: 10, textAlign: 'left' }}>Data</th>
                        <th style={{ padding: 10, textAlign: 'left' }}>Tipo</th>
                        <th style={{ padding: 10, textAlign: 'left' }}>Messaggio</th>
                      </tr>
                    </thead>
                    <tbody>
                      {notifiche.map((n, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid #e2e8f0' }}>
                          <td style={{ padding: 10 }}>{n.date || '-'}</td>
                          <td style={{ padding: 10 }}>
                            <span style={badge(n.type === 'error' ? 'error' : 'info')}>
                              {n.type}
                            </span>
                          </td>
                          <td style={{ padding: 10 }}>{n.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
          
          {/* XBRL Tab Content */}
          {activeTab === 'xbrl' && (
            <div>
              {/* Info Card */}
              <div style={{ ...cardStyle, background: '#f0f9ff', border: '1px solid #bae6fd', marginBottom: 20 }}>
                <h4 style={{ margin: '0 0 12px', color: '#0369a1' }}>📊 Bilanci XBRL Camera di Commercio</h4>
                <p style={{ fontSize: 13, color: '#0c4a6e', marginBottom: 8 }}>
                  Richiedi bilanci ufficiali in formato XBRL dalla Camera di Commercio.<br/>
                  I bilanci vengono elaborati in 10-15 minuti.
                </p>
                <div style={{ fontSize: 12, color: '#64748b' }}>
                  <strong>Costo stimato:</strong> {xbrlStatus?.costo_stimato || '€2.95 - €4.50'} per bilancio
                </div>
              </div>
              
              {/* Form Richiesta */}
              <div style={cardStyle}>
                <h4 style={{ margin: '0 0 16px' }}>📥 Richiedi Bilancio</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 12, alignItems: 'end' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>Partita IVA *</label>
                    <input 
                      type="text"
                      value={xbrlPiva}
                      onChange={(e) => setXbrlPiva(e.target.value)}
                      placeholder="es. 12345678901"
                      style={{ 
                        width: '100%', 
                        padding: '10px 12px', 
                        border: '1px solid #e2e8f0', 
                        borderRadius: 6, 
                        fontSize: 13 
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>Anno Chiusura (opzionale)</label>
                    <input 
                      type="number"
                      value={xbrlAnno}
                      onChange={(e) => setXbrlAnno(e.target.value)}
                      placeholder="es. 2023"
                      style={{ 
                        width: '100%', 
                        padding: '10px 12px', 
                        border: '1px solid #e2e8f0', 
                        borderRadius: 6, 
                        fontSize: 13 
                      }}
                    />
                  </div>
                  <button 
                    onClick={richiediXbrl}
                    disabled={xbrlLoading}
                    style={{ ...button('#15803d'), height: 42 }}
                    data-testid="richiedi-xbrl-btn"
                  >
                    {xbrlLoading ? '⏳ Invio...' : '📤 Richiedi Bilancio'}
                  </button>
                </div>
                
                {xbrlResult && (
                  <div style={{ marginTop: 16, padding: 12, background: '#f0fdf4', borderRadius: 8, fontSize: 13 }}>
                    <strong>✅ {xbrlResult.message}</strong><br/>
                    <span style={{ color: '#64748b' }}>ID Richiesta: {xbrlResult.request_id}</span>
                  </div>
                )}
              </div>
              
              {/* Lista Richieste */}
              <div style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <h4 style={{ margin: 0 }}>📋 Richieste Recenti</h4>
                  <button onClick={loadXbrlRequests} style={{ ...button('#64748b'), padding: '6px 12px', fontSize: 12 }}>
                    🔄 Aggiorna
                  </button>
                </div>
                
                {xbrlRequests.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
                    Nessuna richiesta effettuata
                  </div>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        <th style={{ padding: 10, textAlign: 'left' }}>P.IVA</th>
                        <th style={{ padding: 10, textAlign: 'left' }}>Anno</th>
                        <th style={{ padding: 10, textAlign: 'left' }}>Stato</th>
                        <th style={{ padding: 10, textAlign: 'left' }}>Data Richiesta</th>
                        <th style={{ padding: 10, textAlign: 'center' }}>Azioni</th>
                      </tr>
                    </thead>
                    <tbody>
                      {xbrlRequests.map((r, i) => (
                        <tr key={r.id || i} style={{ borderBottom: '1px solid #e2e8f0' }}>
                          <td style={{ padding: 10 }}>{r.partita_iva}</td>
                          <td style={{ padding: 10 }}>{r.anno_chiusura || 'Ultimo'}</td>
                          <td style={{ padding: 10 }}>
                            <span style={badge(r.status === 'completed' ? 'success' : r.status === 'error' ? 'error' : 'warning')}>
                              {r.status}
                            </span>
                          </td>
                          <td style={{ padding: 10 }}>{r.created_at ? new Date(r.created_at).toLocaleString('it-IT') : '-'}</td>
                          <td style={{ padding: 10, textAlign: 'center' }}>
                            <button 
                              onClick={() => checkXbrlStatus(r.id)}
                              style={{ ...button('#1535a8'), padding: '4px 10px', fontSize: 11 }}
                            >
                              Verifica
                            </button>
                            {r.status === 'completed' && r.download_url && (
                              <a 
                                href={r.download_url} 
                                target="_blank" 
                                rel="noreferrer"
                                style={{ marginLeft: 8, ...button('#15803d'), padding: '4px 10px', fontSize: 11, textDecoration: 'none' }}
                              >
                                📥 Download
                              </a>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}

          {activeTab === 'xbrl' && (
            <div>
              <div style={cardStyle}>
                <h4 style={{ margin: '0 0 16px' }}>📊 Richiedi Bilancio XBRL</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 12, alignItems: 'end' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                      Partita IVA *
                    </label>
                    <input
                      type="text"
                      value={xbrlPiva}
                      onChange={(e) => setXbrlPiva(e.target.value)}
                      placeholder="es. 12345678901"
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        border: '1px solid #d1d5db',
                        borderRadius: 6,
                        fontSize: 14
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                      Anno Chiusura (opzionale)
                    </label>
                    <input
                      type="number"
                      value={xbrlAnno}
                      onChange={(e) => setXbrlAnno(e.target.value)}
                      placeholder="es. 2023"
                      min="2010"
                      max="2030"
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        border: '1px solid #d1d5db',
                        borderRadius: 6,
                        fontSize: 14
                      }}
                    />
                  </div>
                  <button
                    onClick={richiediXbrl}
                    disabled={xbrlLoading || !xbrlPiva}
                    style={{
                      ...button('#15803d'),
                      minWidth: 120,
                      height: 40
                    }}
                  >
                    {xbrlLoading ? '⏳' : '📊 Richiedi'}
                  </button>
                </div>
                
                {xbrlResult && (
                  <div style={{ 
                    marginTop: 16, 
                    padding: 12, 
                    background: xbrlResult.success ? '#f0fdf4' : '#fef2f2', 
                    borderRadius: 6, 
                    fontSize: 13 
                  }}>
                    {xbrlResult.success ? '✅' : '❌'} {xbrlResult.message}
                    {xbrlResult.request_id && (
                      <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
                        ID Richiesta: <code>{xbrlResult.request_id}</code>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Lista Richieste XBRL */}
              {xbrlRequests.length > 0 && (
                <div style={cardStyle}>
                  <h4 style={{ margin: '0 0 16px' }}>📋 Richieste XBRL</h4>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f8fafc' }}>
                          <th style={{ padding: 10, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>ID</th>
                          <th style={{ padding: 10, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>P.IVA</th>
                          <th style={{ padding: 10, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Anno</th>
                          <th style={{ padding: 10, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Stato</th>
                          <th style={{ padding: 10, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Data</th>
                          <th style={{ padding: 10, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Azioni</th>
                        </tr>
                      </thead>
                      <tbody>
                        {xbrlRequests.map((req, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: 10 }}>
                              <code style={{ fontSize: 11 }}>{req.id}</code>
                            </td>
                            <td style={{ padding: 10 }}>{req.partita_iva}</td>
                            <td style={{ padding: 10 }}>{req.anno_chiusura || '-'}</td>
                            <td style={{ padding: 10 }}>
                              <span style={badge(
                                req.status === 'completed' ? 'success' : 
                                req.status === 'failed' ? 'error' : 'warning'
                              )}>
                                {req.status}
                              </span>
                            </td>
                            <td style={{ padding: 10 }}>
                              {req.created_at ? new Date(req.created_at).toLocaleDateString('it-IT') : '-'}
                            </td>
                            <td style={{ padding: 10, textAlign: 'center' }}>
                              <button
                                onClick={() => checkXbrlStatus(req.id)}
                                style={{
                                  ...button('#1535a8'),
                                  fontSize: 11,
                                  padding: '4px 8px'
                                }}
                              >
                                🔍 Verifica
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div style={{ ...cardStyle, background: '#f0f9ff', border: '1px solid #bae6fd' }}>
                <h4 style={{ margin: '0 0 12px', color: '#0369a1' }}>ℹ️ Informazioni XBRL</h4>
                <p style={{ fontSize: 13, color: '#0c4a6e', marginBottom: 12 }}>
                  Il servizio XBRL permette di ottenere i bilanci delle aziende italiane in formato strutturato.
                </p>
                <ul style={{ fontSize: 13, color: '#0c4a6e', paddingLeft: 20, margin: 0 }}>
                  <li>Inserisci la Partita IVA dell&apos;azienda di cui vuoi il bilancio</li>
                  <li>Opzionalmente specifica l&apos;anno di chiusura del bilancio</li>
                  <li>La richiesta viene elaborata in modo asincrono</li>
                  <li>Usa il pulsante &quot;Verifica&quot; per controllare lo stato della richiesta</li>
                </ul>
              </div>
            </div>
          )}

          {activeTab === 'config' && (
            <div>
              <div style={cardStyle}>
                <h4 style={{ margin: '0 0 16px' }}>⚙️ Configurazione Attuale</h4>
                <table style={{ width: '100%', fontSize: 13 }}>
                  <tbody>
                    <tr>
                      <td style={{ padding: '8px 0', fontWeight: 600 }}>API Key</td>
                      <td style={{ padding: '8px 0' }}>
                        <code style={{ background: '#f1f5f9', padding: '4px 8px', borderRadius: 4 }}>
                          ••••••••••••••••{sdiStatus?.api_key_configured ? '(configurata)' : '(mancante)'}
                        </code>
                      </td>
                    </tr>
                    <tr>
                      <td style={{ padding: '8px 0', fontWeight: 600 }}>Ambiente</td>
                      <td style={{ padding: '8px 0' }}>
                        <span style={badge(sdiStatus?.environment === 'sandbox' ? 'warning' : 'success')}>
                          {sdiStatus?.environment || 'N/A'}
                        </span>
                      </td>
                    </tr>
                    <tr>
                      <td style={{ padding: '8px 0', fontWeight: 600 }}>Codice Destinatario</td>
                      <td style={{ padding: '8px 0' }}><code>USAL8PV</code> (OpenAPI.it)</td>
                    </tr>
                    <tr>
                      <td style={{ padding: '8px 0', fontWeight: 600 }}>Base URL SDI</td>
                      <td style={{ padding: '8px 0' }}><code>{sdiStatus?.base_url}</code></td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div style={{ ...cardStyle, background: '#f0f9ff', border: '1px solid #bae6fd' }}>
                <h4 style={{ margin: '0 0 12px', color: '#0369a1' }}>📘 Passare a Produzione</h4>
                <p style={{ fontSize: 13, color: '#0c4a6e', marginBottom: 12 }}>
                  Per passare dall&apos;ambiente Sandbox a Produzione:
                </p>
                <ol style={{ fontSize: 13, color: '#0c4a6e', paddingLeft: 20 }}>
                  <li>Genera una nuova API Key di produzione su OpenAPI.it</li>
                  <li>Aggiorna la variabile <code>OPENAPI_IT_KEY</code> nel file .env</li>
                  <li>Imposta <code>OPENAPI_IT_ENV=&quot;production&quot;</code></li>
                  <li>Riavvia il backend</li>
                </ol>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
    </PageLayout>
  );
}
