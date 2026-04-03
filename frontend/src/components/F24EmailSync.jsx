import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { formatEuro, formatDateIT } from '../lib/utils';
import { X, Mail, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

/**
 * Componente che sincronizza automaticamente gli F24 dalle email
 * all'avvio dell'app e mostra un popup con i risultati.
 */
export default function F24EmailSync({ onClose }) {
  const [status, setStatus] = useState('loading'); // loading, success, error, empty
  const [result, setResult] = useState(null);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    syncF24();
  }, []);

  const syncF24 = async () => {
    try {
      setStatus('loading');
      const res = await api.post('/api/documenti/sync-f24-automatico?giorni=30');
      setResult(res.data);

      if (res.data.f24_caricati > 0) {
        setStatus('success');
      } else if (res.data.f24_trovati > 0 && res.data.f24_errori > 0) {
        setStatus('error');
      } else {
        setStatus('empty');
        // Auto-chiudi dopo 3 secondi se non ci sono nuovi F24
        setTimeout(() => {
          setVisible(false);
          if (onClose) onClose();
        }, 3000);
      }
    } catch (error) {
      console.error('Errore sync F24:', error);
      setResult({ error: error.response?.data?.detail || error.message });
      setStatus('error');
    }
  };

  const handleClose = () => {
    setVisible(false);
    if (onClose) onClose();
  };

  if (!visible) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 20,
      right: 20,
      zIndex: 9999,
      maxWidth: 420,
      background: 'white',
      borderRadius: 12,
      boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
      overflow: 'hidden',
      animation: 'slideIn 0.3s ease-out'
    }}>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>

      {/* Header */}
      <div style={{
        padding: '16px 20px',
        background: status === 'loading' ? '#3b82f6' :
          status === 'success' ? '#16a34a' :
            status === 'empty' ? '#64748b' : '#dc2626',
        color: 'white',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {status === 'loading' ? (
            <Loader2 size={20} className="animate-spin" />
          ) : status === 'success' ? (
            <CheckCircle size={20} />
          ) : status === 'empty' ? (
            <Mail size={20} />
          ) : (
            <AlertCircle size={20} />
          )}
          <span style={{ fontWeight: 'bold' }}>
            {status === 'loading' ? 'Controllo Email F24...' :
              status === 'success' ? 'Nuovi F24 Trovati!' :
                status === 'empty' ? 'Nessun Nuovo F24' :
                  'Errore Sync F24'}
          </span>
        </div>
        {status !== 'loading' && (
          <button
            onClick={handleClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'white',
              cursor: 'pointer',
              padding: 4
            }}
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Content */}
      <div style={{ padding: 20 }}>
        {status === 'loading' && (
          <div style={{ textAlign: 'center', padding: 20, color: '#64748b' }}>
            <div style={{ marginBottom: 12 }}>Scaricamento allegati F24 dalle email...</div>
            <div style={{ fontSize: 12 }}>Questo può richiedere qualche secondo</div>
          </div>
        )}

        {status === 'empty' && (
          <div style={{ textAlign: 'center', color: '#64748b' }}>
            <Mail size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
            <div>Nessun nuovo F24 trovato nelle email degli ultimi 30 giorni</div>
          </div>
        )}

        {status === 'success' && result && (
          <div>
            {/* Riepilogo */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 12,
              marginBottom: 16
            }}>
              <div style={{
                padding: 12,
                background: '#dcfce7',
                borderRadius: 8,
                textAlign: 'center'
              }}>
                <div style={{ fontSize: 24, fontWeight: 'bold', color: '#166534' }}>
                  {result.f24_caricati}
                </div>
                <div style={{ fontSize: 12, color: '#166534' }}>F24 Caricati</div>
              </div>
              {result.quietanze_trovate > 0 && (
                <div style={{
                  padding: 12,
                  background: '#dbeafe',
                  borderRadius: 8,
                  textAlign: 'center'
                }}>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1e40af' }}>
                    {result.quietanze_trovate}
                  </div>
                  <div style={{ fontSize: 12, color: '#1e40af' }}>Quietanze</div>
                </div>
              )}
            </div>

            {/* Dettagli F24 */}
            {result.dettagli && result.dettagli.length > 0 && (
              <div>
                <div style={{ fontSize: 13, fontWeight: 'bold', marginBottom: 8, color: '#1e293b' }}>
                  📋 F24 Importati:
                </div>
                <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                  {result.dettagli.map((f24, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: 10,
                        background: '#f8fafc',
                        borderRadius: 6,
                        marginBottom: 8,
                        fontSize: 13
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontWeight: 'bold', color: '#1e293b' }}>
                          <FileText size={14} style={{ display: 'inline', marginRight: 6 }} />
                          {f24.file.length > 30 ? f24.file.substring(0, 30) + '...' : f24.file}
                        </div>
                        <div style={{
                          fontWeight: 'bold',
                          color: '#dc2626',
                          background: '#fef2f2',
                          padding: '2px 8px',
                          borderRadius: 4
                        }}>
                          {formatEuro(f24.importo)}
                        </div>
                      </div>
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                        Scadenza: {formatDateIT(f24.data_scadenza) || 'N/D'} • {f24.tributi} tributi
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Errori */}
            {result.errori && result.errori.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 4 }}>
                  ⚠️ {result.errori.length} file non processati
                </div>
              </div>
            )}

            {/* Link alla pagina F24 */}
            <Link
              to="/f24"
              style={{
                display: 'block',
                marginTop: 16,
                padding: 12,
                background: '#1e40af',
                color: 'white',
                textAlign: 'center',
                borderRadius: 8,
                textDecoration: 'none',
                fontWeight: 'bold'
              }}
            >
              Vai a F24 / Tributi →
            </Link>
          </div>
        )}

        {status === 'error' && result && (
          <div style={{ color: '#dc2626' }}>
            <AlertCircle size={32} style={{ margin: '0 auto 12px', display: 'block' }} />
            <div style={{ textAlign: 'center' }}>
              {result.error || result.messaggio || 'Errore durante la sincronizzazione'}
            </div>
            {result.errori && result.errori.length > 0 && (
              <div style={{ marginTop: 12, fontSize: 12 }}>
                {result.errori.map((e, idx) => (
                  <div key={idx} style={{ padding: 4 }}>
                    • {e.file}: {e.errore}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
