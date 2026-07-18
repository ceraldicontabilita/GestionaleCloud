import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import { COLORS, SPACING, BORDER_RADIUS, FONT, STYLES, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge, Card, Input, Tabs, TableWrap, Table, Th, Td } from '../components/ds';

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
      toast.warning('Inserisci la Partita IVA');
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
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
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
      toast.info(`Stato: ${res.data.status}${res.data.message ? ' - ' + res.data.message : ''}`);
      loadXbrlRequests();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const infoCardStyle = {
    background: COLORS.infoLight,
    border: `1px solid ${COLORS.border}`,
    borderRadius: BORDER_RADIUS.md,
    padding: 20,
    marginBottom: 20,
  };

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '60vh',
        }}
      >
        <div style={{ fontSize: 48 }}>⏳</div>
      </div>
    );
  }

  return (
    <PageLayout>
      <div style={{ padding: `0 ${SPACING.xl}px ${SPACING.xl}px` }}>
        <div style={STYLES.pageHeader}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>
              🔌 Integrazioni OpenAPI.it
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: COLORS.textMuted }}>
              XBRL (Bilanci Camera di Commercio)
            </p>
          </div>
          <Button variant="info" onClick={loadStatus}>
            🔄 Aggiorna Stato
          </Button>
        </div>

        <div style={{ marginTop: SPACING.lg }}>
          {/* Status Card */}
          <div style={{ marginBottom: 24 }}>
            <Card
              title="📊 XBRL - Bilanci"
              actions={
                <Badge variant={xbrlStatus?.api_key_configured ? 'success' : 'danger'}>
                  {xbrlStatus?.api_key_configured ? '✓ Configurato' : '✗ Non configurato'}
                </Badge>
              }
            >
              <div style={{ fontSize: 13, color: COLORS.textMuted }}>
                <div>
                  Stato: <strong>{xbrlStatus?.status || 'N/A'}</strong>
                </div>
                <div>Bilanci aziendali in formato XBRL</div>
              </div>
            </Card>
          </div>

          {/* Tabs */}
          <div style={{ marginBottom: 20 }}>
            <Tabs
              items={[
                { key: 'xbrl', label: '📊 XBRL Bilanci' },
                { key: 'config', label: '⚙️ Configurazione' },
              ]}
              value={activeTab}
              onChange={key => {
                setActiveTab(key);
                if (key === 'xbrl') loadXbrlRequests();
              }}
            />
          </div>

          {/* XBRL Tab Content */}
          {activeTab === 'xbrl' && (
            <div>
              {/* Info Card */}
              <div style={infoCardStyle}>
                <h4 style={{ margin: '0 0 12px', color: COLORS.info }}>
                  📊 Bilanci XBRL Camera di Commercio
                </h4>
                <p style={{ fontSize: 13, color: COLORS.text, marginBottom: 8 }}>
                  Richiedi bilanci ufficiali in formato XBRL dalla Camera di Commercio.
                  <br />I bilanci vengono elaborati in 10-15 minuti.
                </p>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                  <strong>Costo stimato:</strong> {xbrlStatus?.costo_stimato || '€2.95 - €4.50'}{' '}
                  per bilancio
                </div>
              </div>

              {/* Form Richiesta */}
              <div style={{ marginBottom: 16 }}>
                <Card title="📥 Richiedi Bilancio">
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
                          color: COLORS.textMuted,
                          marginBottom: 4,
                        }}
                      >
                        Partita IVA *
                      </label>
                      <Input
                        type="text"
                        value={xbrlPiva}
                        onChange={e => setXbrlPiva(e.target.value)}
                        placeholder="es. 12345678901"
                      />
                    </div>
                    <div>
                      <label
                        style={{
                          display: 'block',
                          fontSize: 12,
                          color: COLORS.textMuted,
                          marginBottom: 4,
                        }}
                      >
                        Anno Chiusura (opzionale)
                      </label>
                      <Input
                        type="number"
                        value={xbrlAnno}
                        onChange={e => setXbrlAnno(e.target.value)}
                        placeholder="es. 2023"
                      />
                    </div>
                    <Button
                      variant="success"
                      onClick={richiediXbrl}
                      disabled={xbrlLoading}
                      style={{ height: 42 }}
                      data-testid="richiedi-xbrl-btn"
                    >
                      {xbrlLoading ? '⏳ Invio...' : '📤 Richiedi Bilancio'}
                    </Button>
                  </div>

                  {xbrlResult && (
                    <div
                      style={{
                        marginTop: 16,
                        padding: 12,
                        background: COLORS.successLight,
                        borderRadius: BORDER_RADIUS.md,
                        fontSize: 13,
                      }}
                    >
                      <strong>✅ {xbrlResult.message}</strong>
                      <br />
                      <span style={{ color: COLORS.textMuted }}>
                        ID Richiesta: {xbrlResult.request_id}
                      </span>
                    </div>
                  )}
                </Card>
              </div>

              {/* Lista Richieste */}
              <div style={{ marginBottom: 16 }}>
                <Card
                  title="📋 Richieste Recenti"
                  actions={
                    <Button variant="secondary" size="sm" onClick={loadXbrlRequests}>
                      🔄 Aggiorna
                    </Button>
                  }
                >
                  {xbrlRequests.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
                      Nessuna richiesta effettuata
                    </div>
                  ) : (
                    <TableWrap style={{ border: 'none' }}>
                      <Table>
                        <thead>
                          <tr>
                            <Th align="left">P.IVA</Th>
                            <Th align="left">Anno</Th>
                            <Th align="left">Stato</Th>
                            <Th align="left">Data Richiesta</Th>
                            <Th align="center">Azioni</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {xbrlRequests.map((r, i) => (
                            <tr key={r.id || i}>
                              <Td>{r.partita_iva}</Td>
                              <Td>{r.anno_chiusura || 'Ultimo'}</Td>
                              <Td>
                                <Badge
                                  variant={
                                    r.status === 'completed'
                                      ? 'success'
                                      : r.status === 'error'
                                        ? 'danger'
                                        : 'warning'
                                  }
                                >
                                  {r.status}
                                </Badge>
                              </Td>
                              <Td>
                                {r.created_at
                                  ? new Date(r.created_at).toLocaleString('it-IT')
                                  : '-'}
                              </Td>
                              <Td align="center">
                                <Button
                                  variant="info"
                                  size="sm"
                                  style={{ padding: '4px 10px', fontSize: 11 }}
                                  onClick={() => checkXbrlStatus(r.id)}
                                >
                                  Verifica
                                </Button>
                                {r.status === 'completed' && r.download_url && (
                                  <a
                                    href={r.download_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      marginLeft: 8,
                                      padding: '4px 10px',
                                      fontSize: 11,
                                      fontWeight: 600,
                                      fontFamily: FONT.family,
                                      borderRadius: BORDER_RADIUS.sm,
                                      background: COLORS.success,
                                      color: '#fff',
                                      textDecoration: 'none',
                                    }}
                                  >
                                    📥 Download
                                  </a>
                                )}
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </TableWrap>
                  )}
                </Card>
              </div>

              <div style={infoCardStyle}>
                <h4 style={{ margin: '0 0 12px', color: COLORS.info }}>ℹ️ Informazioni XBRL</h4>
                <p style={{ fontSize: 13, color: COLORS.text, marginBottom: 12 }}>
                  Il servizio XBRL permette di ottenere i bilanci delle aziende italiane in
                  formato strutturato.
                </p>
                <ul style={{ fontSize: 13, color: COLORS.text, paddingLeft: 20, margin: 0 }}>
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
              <div style={{ marginBottom: 16 }}>
                <Card title="⚙️ Configurazione Attuale">
                  <TableWrap style={{ border: 'none' }}>
                    <Table>
                      <tbody>
                        <tr>
                          <Td style={{ fontWeight: 600, border: 'none' }}>API Key</Td>
                          <Td style={{ border: 'none' }}>
                            <code
                              style={{
                                background: COLORS.gray[100],
                                padding: '4px 8px',
                                borderRadius: BORDER_RADIUS.sm,
                                fontFamily: FONT.mono,
                              }}
                            >
                              ••••••••••••••••
                              {xbrlStatus?.api_key_configured ? '(configurata)' : '(mancante)'}
                            </code>
                          </Td>
                        </tr>
                      </tbody>
                    </Table>
                  </TableWrap>
                </Card>
              </div>

              <div style={infoCardStyle}>
                <h4 style={{ margin: '0 0 12px', color: COLORS.info }}>📘 Aggiornare la API Key</h4>
                <p style={{ fontSize: 13, color: COLORS.text, marginBottom: 12 }}>
                  Per aggiornare le credenziali OpenAPI.it:
                </p>
                <ol style={{ fontSize: 13, color: COLORS.text, paddingLeft: 20 }}>
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
    </PageLayout>
  );
}
