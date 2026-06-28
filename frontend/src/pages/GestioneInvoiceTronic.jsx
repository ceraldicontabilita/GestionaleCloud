import React, { useState, useEffect, useCallback } from 'react';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription } from '../components/ui/alert';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  FileText,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Download,
  ExternalLink,
  Calendar,
  Building2,
  Euro,
} from 'lucide-react';
import { toast } from '../components/ui/sonner';
import api from '../api';

export default function GestioneInvoiceTronic() {
  const isMobile = useIsMobile();
  const [status, setStatus] = useState(null);
  const [fatture, setFatture] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sincronizzaLoading, setSincronizzaLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get('/api/invoicetronic/status');
      setStatus(res.data);
    } catch (error) {
      console.error('Errore fetch status:', error);
    }
  }, []);

  const fetchFatture = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/invoicetronic/fatture-in-arrivo');
      setFatture(res.data?.fatture || []);
    } catch (error) {
      console.error('Errore fetch fatture:', error);
      toast.error('Errore nel caricamento fatture');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchFatture();
  }, [fetchStatus, fetchFatture]);

  const handleSincronizza = async () => {
    setSincronizzaLoading(true);
    try {
      const res = await api.post('/api/invoicetronic/sync-fatture');
      toast.success(
        `Sincronizzazione completata: ${res.data?.fatture_importate || 0} nuove fatture`
      );
      fetchFatture();
    } catch (error) {
      console.error('Errore sincronizzazione:', error);
      toast.error('Errore nella sincronizzazione');
    } finally {
      setSincronizzaLoading(false);
    }
  };

  const getStatusBadge = () => {
    if (!status) return null;

    if (status.connected) {
      return (
        <Badge className="bg-green-100 text-green-800">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Connesso
        </Badge>
      );
    } else {
      return (
        <Badge variant="destructive">
          <AlertCircle className="h-3 w-3 mr-1" />
          Non connesso
        </Badge>
      );
    }
  };

  return (
    <PageLayout
      title="InvoiceTronic - Fatturazione Elettronica"
      subtitle="Gestione fatture elettroniche SDI"
    >
      <div style={{ maxWidth: 1400, margin: '0 auto' }} data-testid="gestione-invoicetronic">
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 20,
            padding: '15px 20px',
            background: '#0f2744',
            borderRadius: 12,
            color: 'white',
            flexWrap: 'wrap',
            gap: 10,
          }}
        >
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 'bold' }}>
              📨 InvoiceTronic - Fatturazione Elettronica
            </h1>
            <p style={{ margin: '4px 0 0 0', fontSize: 13, opacity: 0.9 }}>
              Ricezione automatica fatture passive via SDI
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {status?.connected && (
              <span
                style={{
                  padding: '6px 12px',
                  background: '#22c55e',
                  color: 'white',
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                ✅ Connesso
              </span>
            )}
            {status && !status.connected && (
              <span
                style={{
                  padding: '6px 12px',
                  background: '#ef4444',
                  color: 'white',
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                ❌ Disconnesso
              </span>
            )}
            <button
              onClick={() => {
                fetchStatus();
                fetchFatture();
              }}
              disabled={loading}
              style={{
                padding: '10px 20px',
                background: 'rgba(255,255,255,0.95)',
                color: '#1e3a5f',
                border: 'none',
                borderRadius: 8,
                cursor: loading ? 'not-allowed' : 'pointer',
                fontWeight: '600',
                opacity: loading ? 0.6 : 1,
              }}
              data-testid="refresh-invoicetronic-btn"
            >
              🔄 Aggiorna
            </button>
            <button
              onClick={handleSincronizza}
              disabled={sincronizzaLoading || !status?.connected}
              style={{
                padding: '10px 20px',
                background: sincronizzaLoading || !status?.connected ? '#9ca3af' : '#10b981',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: sincronizzaLoading || !status?.connected ? 'not-allowed' : 'pointer',
                fontWeight: '600',
              }}
              data-testid="sincronizza-invoicetronic-btn"
            >
              📥 Sincronizza SDI
            </button>
          </div>
        </div>

        {/* Info Connessione */}
        {status && (
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              overflow: 'hidden',
              marginBottom: 20,
            }}
          >
            <div
              style={{
                padding: '16px 20px',
                background: '#f8fafc',
                borderBottom: '1px solid #e5e7eb',
              }}
            >
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f2937' }}>
                📡 Stato Connessione
              </h2>
            </div>
            <div style={{ padding: 16 }}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
                  gap: 16,
                }}
              >
                <div>
                  <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Ambiente</p>
                  <p style={{ fontWeight: 500, margin: 0 }}>
                    {status.environment === 'sandbox' ? '🧪 Sandbox (Test)' : '🚀 Produzione'}
                  </p>
                </div>
                <div>
                  <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                    Codice Destinatario
                  </p>
                  <p style={{ fontWeight: 500, margin: 0, fontFamily: 'monospace' }}>
                    {status.codice_destinatario || 'Non configurato'}
                  </p>
                </div>
                <div>
                  <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                    Ultima Sincronizzazione
                  </p>
                  <p style={{ fontWeight: 500, margin: 0 }}>{status.last_sync || 'Mai'}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Alert Sandbox */}
        {status?.environment === 'sandbox' && (
          <div
            style={{
              padding: 12,
              background: '#fef3c7',
              borderRadius: 8,
              borderLeft: '4px solid #f59e0b',
              fontSize: 13,
              color: '#92400e',
              marginBottom: 20,
            }}
          >
            <strong>⚠️ Ambiente Sandbox:</strong> L'integrazione è in modalità test. Per ricevere
            fatture reali, è necessario:
            <ol style={{ margin: '8px 0 0 16px', paddingLeft: 0 }}>
              <li>Accedere al portale dell'Agenzia delle Entrate (Fatture e Corrispettivi)</li>
              <li>
                Registrare il codice destinatario <strong>{status.codice_destinatario}</strong>
              </li>
              <li>Acquistare crediti su InvoiceTronic per l'ambiente di produzione</li>
            </ol>
          </div>
        )}

        {/* Stats Cards */}
        <div
          style={{
            background: 'white',
            borderRadius: 12,
            padding: 16,
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            marginBottom: 20,
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
              gap: 12,
            }}
          >
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                padding: '10px 12px',
                boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                borderLeft: '3px solid #3b82f6',
              }}
            >
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>
                📄 Fatture Ricevute
              </div>
              <div
                style={{ fontSize: 18, fontWeight: 'bold', color: '#3b82f6' }}
                data-testid="stats-totali"
              >
                {fatture.length}
              </div>
            </div>
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                padding: '10px 12px',
                boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                borderLeft: '3px solid #22c55e',
              }}
            >
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>✅ Importate</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: '#22c55e' }}>
                {fatture.filter(f => f.importata).length}
              </div>
            </div>
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                padding: '10px 12px',
                boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                borderLeft: '3px solid #f97316',
              }}
            >
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>⏳ Da Importare</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: '#f97316' }}>
                {fatture.filter(f => !f.importata).length}
              </div>
            </div>
            <div
              style={{
                background: '#1e3a5f',
                borderRadius: 8,
                padding: '10px 12px',
                color: 'white',
              }}
            >
              <div style={{ fontSize: 11, opacity: 0.9, marginBottom: 4 }}>Totale Imponibile</div>
              <div style={{ fontSize: 18, fontWeight: 'bold' }}>
                {formatEuro(fatture.reduce((sum, f) => sum + (f.importo_totale || 0), 0))}
              </div>
            </div>
          </div>
        </div>

        {/* Lista Fatture */}
        <div
          style={{
            background: 'white',
            borderRadius: 12,
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '16px 20px',
              background: '#f8fafc',
              borderBottom: '1px solid #e5e7eb',
            }}
          >
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f2937' }}>
              📄 Fatture Ricevute da SDI
            </h2>
            <p style={{ margin: '4px 0 0 0', fontSize: 13, color: '#6b7280' }}>
              {fatture.length} fatture nel sistema
            </p>
          </div>
          <div style={{ padding: 16 }}>
            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
                <RefreshCw
                  style={{
                    width: 32,
                    height: 32,
                    animation: 'spin 1s linear infinite',
                    color: '#9ca3af',
                  }}
                />
              </div>
            ) : fatture.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af' }}>
                <FileText style={{ width: 48, height: 48, margin: '0 auto 16px', opacity: 0.5 }} />
                <p style={{ margin: 0 }}>Nessuna fattura ricevuta</p>
                <p style={{ fontSize: 13, marginTop: 8 }}>
                  Le fatture arriveranno automaticamente quando i fornitori le invieranno al tuo
                  codice destinatario
                </p>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '12px 16px',
                          fontWeight: 500,
                          color: '#6b7280',
                          fontSize: 13,
                        }}
                      >
                        Data Ricezione
                      </th>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '12px 16px',
                          fontWeight: 500,
                          color: '#6b7280',
                          fontSize: 13,
                        }}
                      >
                        Numero
                      </th>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '12px 16px',
                          fontWeight: 500,
                          color: '#6b7280',
                          fontSize: 13,
                        }}
                      >
                        Fornitore
                      </th>
                      <th
                        style={{
                          textAlign: 'right',
                          padding: '12px 16px',
                          fontWeight: 500,
                          color: '#6b7280',
                          fontSize: 13,
                        }}
                      >
                        Importo
                      </th>
                      <th
                        style={{
                          textAlign: 'center',
                          padding: '12px 16px',
                          fontWeight: 500,
                          color: '#6b7280',
                          fontSize: 13,
                        }}
                      >
                        Stato
                      </th>
                      <th
                        style={{
                          textAlign: 'center',
                          padding: '12px 16px',
                          fontWeight: 500,
                          color: '#6b7280',
                          fontSize: 13,
                        }}
                      >
                        Azioni
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {fatture.map((fattura, idx) => (
                      <tr key={fattura.id || idx} style={{ borderBottom: '1px solid #e5e7eb' }}>
                        <td style={{ padding: '12px 16px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            📅 {formatDateIT(fattura.data_ricezione) || '-'}
                          </div>
                        </td>
                        <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: 13 }}>
                          {fattura.numero || '-'}
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            🏢 {fattura.fornitore || '-'}
                          </div>
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 500 }}>
                          {formatEuro(fattura.importo || 0)}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          {fattura.stato === 'elaborata' ? (
                            <span
                              style={{
                                padding: '4px 8px',
                                background: '#dcfce7',
                                color: '#166534',
                                borderRadius: 4,
                                fontSize: 12,
                                fontWeight: 600,
                              }}
                            >
                              ✅ Elaborata
                            </span>
                          ) : fattura.stato === 'errore' ? (
                            <span
                              style={{
                                padding: '4px 8px',
                                background: '#fee2e2',
                                color: '#991b1b',
                                borderRadius: 4,
                                fontSize: 12,
                                fontWeight: 600,
                              }}
                            >
                              ❌ Errore
                            </span>
                          ) : (
                            <span
                              style={{
                                padding: '4px 8px',
                                background: '#f3f4f6',
                                color: '#374151',
                                borderRadius: 4,
                                fontSize: 12,
                                fontWeight: 600,
                              }}
                            >
                              ⏳ Da Elaborare
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          <button
                            style={{
                              padding: '6px 10px',
                              background: 'transparent',
                              border: '1px solid #e5e7eb',
                              borderRadius: 6,
                              cursor: 'pointer',
                            }}
                            data-testid={`view-fattura-${idx}`}
                          >
                            🔗
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
