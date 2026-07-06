import React, { useState, useEffect } from 'react';
import api from '../api';
import { STYLES, badge, useIsMobile, button } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

export default function IntegrazioniOpenAPI() {
  const isMobile = useIsMobile();
  const [xbrlStatus, setXbrlStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('xbrl');

  // XBRL State
  const [xbrlPiva, setXbrlPiva] = useState('');
  const [xbrlAnno, setXbrlAnno] = useState('');
  const [xbrlLoading, setXbrlLoading] = useState(false);
  const [xbrlResult, setXbrlResult] = useState(null);
  const [xbrlRequests, setXbrlRequests] = useState([]);

  useEffect(() => {
    loadStatus();
    loadXbrlRequests();
  }, []);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const xbrl = await api.get('/api/openapi/xbrl/status').catch(() => ({ data: { status: 'error' } }));
      setXbrlStatus(xbrl.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
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

  const checkXbrlStatus = async requestId => {
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
    marginBottom: 16,
  };

  const tabStyle = isActive => ({
    padding: '12px 24px',
    background: isActive ? '#1e3a5f' : 'transparent',
    color: isActive ? '#fff' : '#64748b',
    border: 'none',
    borderRadius: '8px 8px 0 0',
    cursor: 'pointer',
    fontWeight: isActive ? 600 : 500,
    fontSize: 14,
  });

  if (loading) {
    return (
      <div
        style={{
          ...STYLES.pageWrapper,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        <div style={{ fontSize: 48 }}>⏳</div>
      </div>
    );
  }

  return (
    <PageLayout title="Integrazioni OpenAPI.it" subtitle="XBRL (Bilanci Camera di Commercio)">
      <div style={{ ...STYLES.pageWrapper, padding: 0 }}>
        <div style={STYLES.pageContainer}>
          <div style={STYLES.pageHeader}>
            <div>
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>
                🔌 Integrazioni OpenAPI.it
              </h1>
              <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
                XBRL (Bilanci Camera di Commercio)
              </p>
            </div>
            <button onClick={loadStatus} style={button('#3b82f6')}>
              🔄 Aggiorna Stato
            </button>
          </div>

          <div style={STYLES.pageContent}>
            {/* Status Card */}
            <div style={{ marginBottom: 24 }}>
              <div style={cardStyle}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 12,
                  }}
                >
                  <h3 style={{ margin: 0, fontSize: 16 }}>📊 XBRL - Bilanci</h3>
                  <span style={badge(xbrlStatus?.api_key_configured ? 'success' : 'error')}>
                    {xbrlStatus?.api_key_configured ? '✓ Configurato' : '✗ Non configurato'}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: '#64748b' }}>
                  <div>
                    Stato: <strong>{xbrlStatus?.status || 'N/A'}</strong>
                  </div>
                  <div>Bilanci aziendali in formato XBRL</div>
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', marginBottom: 20 }}>
              <button
                style={tabStyle(activeTab === 'xbrl')}
                onClick={() => {
                  setActiveTab('xbrl');
                  loadXbrlRequests();
                }}
              >
                📊 XBRL Bilanci
              </button>
              <button
                style={tabStyle(activeTab === 'config')}
                onClick={() => setActiveTab('config')}
              >
                ⚙️ Configurazione
              </button>
            </div>

            {/* XBRL Tab Content */}
            {activeTab === 'xbrl' && (
              <div>
                {/* Info Card */}
                <div
                  style={{
                    ...cardStyle,
                    background: '#f0f9ff',
                    border: '1px solid #bae6fd',
                    marginBottom: 20,
                  }}
                >
                  <h4 style={{ margin: '0 0 12px', color: '#0369a1' }}>
                    📊 Bilanci XBRL Camera di Commercio
                  </h4>
                  <p style={{ fontSize: 13, color: '#0c4a6e', marginBottom: 8 }}>
                    Richiedi bilanci ufficiali in formato XBRL dalla Camera di Commercio.
                    <br />I bilanci vengono elaborati in 10-15 minuti.
                  </p>
                  <div style={{ fontSize: 12, color: '#64748b' }}>
                    <strong>Costo stimato:</strong> {xbrlStatus?.costo_stimato || '€2.95 - €4.50'}{' '}
                    per bilancio
                  </div>
                </div>

                {/* Form Richiesta */}
                <div style={cardStyle}>
                  <h4 style={{ margin: '0 0 16px' }}>📥 Richiedi Bilancio</h4>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr auto',
                      gap: 12,
                      alignItems: 'end',
                    }}
                  >
                    <div>
                      <label
                        style={{
                          display: 'block',
                          fontSize: 12,
                          color: '#64748b',
                          marginBottom: 4,
                        }}
                      >
                        Partita IVA *
                      </label>
                      <input
                        type="text"
                        value={xbrlPiva}
                        onChange={e => setXbrlPiva(e.target.value)}
                        placeholder="es. 12345678901"
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          border: '1px solid #e2e8f0',
                          borderRadius: 6,
                          fontSize: 13,
                        }}
                      />
                    </div>
                    <div>
                      <label
                        style={{
                          display: 'block',
                          fontSize: 12,
                          color: '#64748b',
                          marginBottom: 4,
                        }}
                      >
                        Anno Chiusura (opzionale)
                      </label>
                      <input
                        type="number"
                        value={xbrlAnno}
                        onChange={e => setXbrlAnno(e.target.value)}
                        placeholder="es. 2023"
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          border: '1px solid #e2e8f0',
                          borderRadius: 6,
                          fontSize: 13,
                        }}
                      />
                    </div>
                    <button
                      onClick={richiediXbrl}
                      disabled={xbrlLoading}
                      style={{ ...button('#10b981'), height: 42 }}
                      data-testid="richiedi-xbrl-btn"
                    >
                      {xbrlLoading ? '⏳ Invio...' : '📤 Richiedi Bilancio'}
                    </button>
                  </div>

                  {xbrlResult && (
                    <div
                      style={{
                        marginTop: 16,
                        padding: 12,
                        background: '#f0fdf4',
                        borderRadius: 8,
                        fontSize: 13,
                      }}
                    >
                      <strong>✅ {xbrlResult.message}</strong>
                      <br />
                      <span style={{ color: '#64748b' }}>
                        ID Richiesta: {xbrlResult.request_id}
                      </span>
                    </div>
                  )}
                </div>

                {/* Lista Richieste */}
                <div style={cardStyle}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 16,
                    }}
                  >
                    <h4 style={{ margin: 0 }}>📋 Richieste Recenti</h4>
                    <button
                      onClick={loadXbrlRequests}
                      style={{ ...button('#64748b'), padding: '6px 12px', fontSize: 12 }}
                    >
                      🔄 Aggiorna
                    </button>
                  </div>

                  {xbrlRequests.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
                      Nessuna richiesta effettuata
                    </div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
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
                                <span
                                  style={badge(
                                    r.status === 'completed'
                                      ? 'success'
                                      : r.status === 'error'
                                        ? 'error'
                                        : 'warning'
                                  )}
                                >
                                  {r.status}
                                </span>
                              </td>
                              <td style={{ padding: 10 }}>
                                {r.created_at
                                  ? new Date(r.created_at).toLocaleString('it-IT')
                                  : '-'}
                              </td>
                              <td style={{ padding: 10, textAlign: 'center' }}>
                                <button
                                  onClick={() => checkXbrlStatus(r.id)}
                                  style={{ ...button('#3b82f6'), padding: '4px 10px', fontSize: 11 }}
                                >
                                  Verifica
                                </button>
                                {r.status === 'completed' && r.download_url && (
                                  <a
                                    href={r.download_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{
                                      marginLeft: 8,
                                      ...button('#10b981'),
                                      padding: '4px 10px',
                                      fontSize: 11,
                                      textDecoration: 'none',
                                    }}
                                  >
                                    📥 Download
                                  </a>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div style={{ ...cardStyle, background: '#f0f9ff', border: '1px solid #bae6fd' }}>
                  <h4 style={{ margin: '0 0 12px', color: '#0369a1' }}>ℹ️ Informazioni XBRL</h4>
                  <p style={{ fontSize: 13, color: '#0c4a6e', marginBottom: 12 }}>
                    Il servizio XBRL permette di ottenere i bilanci delle aziende italiane in
                    formato strutturato.
                  </p>
                  <ul style={{ fontSize: 13, color: '#0c4a6e', paddingLeft: 20, margin: 0 }}>
                    <li>Inserisci la Partita IVA dell&apos;azienda di cui vuoi il bilancio</li>
                    <li>Opzionalmente specifica l&apos;anno di chiusura del bilancio</li>
                    <li>La richiesta viene elaborata in modo asincrono</li>
                    <li>
                      Usa il pulsante &quot;Verifica&quot; per controllare lo stato della richiesta
                    </li>
                  </ul>
                </div>
              </div>
            )}

            {activeTab === 'config' && (
              <div>
                <div style={cardStyle}>
                  <h4 style={{ margin: '0 0 16px' }}>⚙️ Configurazione Attuale</h4>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', fontSize: 13 }}>
                      <tbody>
                        <tr>
                          <td style={{ padding: '8px 0', fontWeight: 600 }}>API Key</td>
                          <td style={{ padding: '8px 0' }}>
                            <code
                              style={{ background: '#f1f5f9', padding: '4px 8px', borderRadius: 4 }}
                            >
                              ••••••••••••••••
                              {xbrlStatus?.api_key_configured ? '(configurata)' : '(mancante)'}
                            </code>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <div style={{ ...cardStyle, background: '#f0f9ff', border: '1px solid #bae6fd' }}>
                  <h4 style={{ margin: '0 0 12px', color: '#0369a1' }}>📘 Aggiornare la API Key</h4>
                  <p style={{ fontSize: 13, color: '#0c4a6e', marginBottom: 12 }}>
                    Per aggiornare le credenziali OpenAPI.it:
                  </p>
                  <ol style={{ fontSize: 13, color: '#0c4a6e', paddingLeft: 20 }}>
                    <li>Genera una nuova API Key su OpenAPI.it</li>
                    <li>
                      Aggiorna la variabile <code>OPENAPI_IT_KEY</code> nel file .env
                    </li>
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
