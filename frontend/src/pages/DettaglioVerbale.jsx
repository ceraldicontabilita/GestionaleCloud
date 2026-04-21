import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../api";
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge , useIsMobile, RG, pagePad } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

export default function DettaglioVerbale() {
  const isMobile = useIsMobile();
  const { numeroVerbale, prefisso, numero } = useParams();
  const navigate = useNavigate();
  const [verbale, setVerbale] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Costruisci il numero verbale completo
  const verbaleId = prefisso && numero ? `${prefisso}/${numero}` : numeroVerbale;

  const fetchVerbale = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get(`/api/verbali-noleggio/dettaglio/${verbaleId}`);
      setVerbale(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "Errore caricamento verbale");
    } finally {
      setLoading(false);
    }
  }, [verbaleId]);

  useEffect(() => {
    fetchVerbale();
  }, [fetchVerbale]);

  const getStatoColor = (stato) => {
    switch (stato) {
      case 'pagato': return { bg: '#dcfce7', color: '#166534' };
      case 'sospeso': return { bg: '#fef3c7', color: '#92400e' };
      default: return { bg: '#f3f4f6', color: '#374151' };
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>⏳</div>
        <div>Caricamento verbale {verbaleId}...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 40 }}>
        <div style={{ 
          padding: 20, 
          background: '#fee2e2', 
          borderRadius: 12, 
          color: '#dc2626',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>❌</div>
          <div style={{ fontWeight: 'bold', marginBottom: 8 }}>Errore</div>
          <div>{error}</div>
          <div style={{ fontSize: 13, color: '#64748b', marginTop: 8 }}>
            Verbale "{verbaleId}" non trovato nel database. Potrebbe essere stato eliminato o il numero potrebbe non essere corretto.
          </div>
          <button 
            onClick={() => navigate(-1)}
            style={{ 
              marginTop: 16, 
              padding: '10px 20px', 
              background: '#dc2626', 
              color: 'white', 
              border: 'none', 
              borderRadius: 8, 
              cursor: 'pointer' 
            }}
          >
            ← Torna indietro
          </button>
        </div>
      </div>
    );
  }

  const statoStyle = getStatoColor(verbale?.stato_pagamento);

  return (
    <PageLayout title="Dettaglio Verbale" subtitle={`Verbale n° ${verbale?.numero_verbale || 'N/A'}`}>
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ 
        background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
        borderRadius: 16,
        padding: 24,
        color: 'white',
        marginBottom: 24,
        boxShadow: '0 4px 20px rgba(0,0,0,0.15)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 4 }}>VERBALE N°</div>
            <div style={{ fontSize: 28, fontWeight: 'bold', fontFamily: 'monospace' }}>
              {verbale?.numero_verbale || 'N/A'}
            </div>
          </div>
          <div style={{ 
            padding: '8px 16px', 
            background: statoStyle.bg,
            color: statoStyle.color,
            borderRadius: 20,
            fontWeight: 'bold',
            fontSize: 14
          }}>
            {verbale?.stato_pagamento === 'pagato' ? '✓ PAGATO' : 
             verbale?.stato_pagamento === 'sospeso' ? '⚠️ SOSPESO' : '❓ DA VERIFICARE'}
          </div>
        </div>
        
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 24, marginTop: 24 }}>
          <div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>TARGA</div>
            <div style={{ fontSize: 18, fontWeight: 'bold', fontFamily: 'monospace' }}>{verbale?.targa || '-'}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>IMPORTO</div>
            <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(verbale?.importo || 0)}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>DRIVER</div>
            <div style={{ fontSize: 14 }}>{verbale?.driver || verbale?.veicolo_info?.driver || '-'}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>CONTRATTO</div>
            <div style={{ fontSize: 14, fontFamily: 'monospace' }}>{verbale?.contratto || '-'}</div>
          </div>
        </div>
      </div>

      {/* Corpo */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 24 }}>
        {/* Colonna Sinistra */}
        <div>
          {/* Dettagli Verbale */}
          <div style={{ 
            background: 'white', 
            borderRadius: 12, 
            padding: 20, 
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            marginBottom: 24
          }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: 16, color: '#1e3a5f' }}>📋 Dettagli Verbale</h3>
            
            <div style={{ fontSize: 13, lineHeight: 2 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                <span style={{ color: '#6b7280' }}>Numero Verbale:</span>
                <strong style={{ fontFamily: 'monospace' }}>{verbale?.numero_verbale}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                <span style={{ color: '#6b7280' }}>Data Verbale:</span>
                <strong>{formatDateIT(verbale?.data_verbale) || '-'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                <span style={{ color: '#6b7280' }}>Importo:</span>
                <strong style={{ color: '#dc2626' }}>{formatEuro(verbale?.importo)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                <span style={{ color: '#6b7280' }}>Fornitore:</span>
                <strong>{verbale?.fornitore}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280' }}>Descrizione:</span>
              </div>
              <div style={{ 
                background: '#f9fafb', 
                padding: 12, 
                borderRadius: 8, 
                fontSize: 12, 
                marginTop: 8,
                color: '#4b5563',
                lineHeight: 1.5
              }}>
                {verbale?.descrizione || '-'}
              </div>
            </div>
          </div>

          {/* Fattura Associata */}
          <div style={{ 
            background: 'white', 
            borderRadius: 12, 
            padding: 20, 
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
          }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: 16, color: '#1e3a5f' }}>📄 Fattura Associata</h3>
            
            <div style={{ fontSize: 13, lineHeight: 2 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                <span style={{ color: '#6b7280' }}>N° Fattura:</span>
                <strong style={{ fontFamily: 'monospace' }}>{verbale?.numero_fattura || '-'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                <span style={{ color: '#6b7280' }}>Data Fattura:</span>
                <strong>{formatDateIT(verbale?.data_fattura)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280' }}>Fornitore:</span>
                <strong>{verbale?.fornitore}</strong>
              </div>
            </div>
            
            {verbale?.fattura_id && (
              <a 
                href={`/api/fatture-ricevute/fattura/${verbale.fattura_id}/view-assoinvoice`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ 
                  display: 'inline-block',
                  marginTop: 16,
                  padding: '10px 20px', 
                  background: '#dbeafe', 
                  color: '#2563eb', 
                  borderRadius: 8, 
                  textDecoration: 'none',
                  fontWeight: '600'
                }}
              >
                📄 Visualizza Fattura
              </a>
            )}
          </div>
        </div>

        {/* Colonna Destra */}
        <div>
          {/* PDF Verbale */}
          <div style={{ 
            background: 'white', 
            borderRadius: 12, 
            padding: 20, 
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            marginBottom: 24
          }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: 16, color: '#1e3a5f' }}>📎 Documenti PDF</h3>
            
            {verbale?.pdf_disponibili && verbale.pdf_disponibili.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {verbale.pdf_disponibili.map((pdf, idx) => (
                  <button 
                    key={idx}
                    onClick={async () => {
                      try {
                        const res = await api.get(`/api/verbali-noleggio/pdf/${verbale.numero_verbale}?indice=${pdf.indice}`);
                        if (res.data?.content_base64) {
                          const byteCharacters = atob(res.data.content_base64);
                          const byteNumbers = new Array(byteCharacters.length);
                          for (let i = 0; i < byteCharacters.length; i++) {
                            byteNumbers[i] = byteCharacters.charCodeAt(i);
                          }
                          const byteArray = new Uint8Array(byteNumbers);
                          const blob = new Blob([byteArray], { type: 'application/pdf' });
                          const url = window.URL.createObjectURL(blob);
                          window.open(url, '_blank');
                        }
                      } catch (err) {
                        console.error('Errore download PDF:', err);
                        alert('Errore durante il download del PDF');
                      }
                    }}
                    style={{ 
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      padding: 12, 
                      background: '#f0fdf4', 
                      color: '#166534', 
                      borderRadius: 8, 
                      textDecoration: 'none',
                      border: '1px solid #bbf7d0',
                      cursor: 'pointer',
                      width: '100%',
                      textAlign: 'left'
                    }}
                    data-testid={`pdf-download-${idx}`}
                  >
                    <span style={{ fontSize: 24 }}>📄</span>
                    <div>
                      <div style={{ fontWeight: '600' }}>{pdf.filename}</div>
                      <div style={{ fontSize: 11, opacity: 0.8 }}>{Math.round((pdf.size || 0) / 1024)} KB</div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div style={{ 
                padding: 24, 
                background: '#fef3c7', 
                borderRadius: 8, 
                textAlign: 'center',
                color: '#92400e'
              }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}>📭</div>
                <div style={{ fontWeight: 'bold', marginBottom: 4 }}>PDF non ancora scaricato</div>
                <div style={{ fontSize: 12 }}>
                  Il documento del verbale deve essere scaricato dalla posta elettronica
                </div>
                <button
                  onClick={async () => {
                    try {
                      const res = await api.post('/api/verbali-noleggio/scarica-posta');
                      alert(`Scaricati ${res.data.nuovi_verbali} nuovi verbali`);
                      fetchVerbale();
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{ 
                    marginTop: 12,
                    padding: '8px 16px', 
                    background: '#f59e0b', 
                    color: 'white', 
                    border: 'none', 
                    borderRadius: 6, 
                    cursor: 'pointer',
                    fontWeight: '600'
                  }}
                >
                  📧 Scarica da Posta
                </button>
              </div>
            )}
          </div>

          {/* Stato Pagamento */}
          <div style={{ 
            background: 'white', 
            borderRadius: 12, 
            padding: 20, 
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            marginBottom: 24
          }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: 16, color: '#1e3a5f' }}>💳 Stato Pagamento</h3>
            
            {(verbale?.stato === 'pagato' || verbale?.stato_pagamento === 'pagato') ? (
              <div style={{ 
                padding: 16, 
                background: '#dcfce7', 
                borderRadius: 8,
                border: '1px solid #15803d',
              }} data-testid="verbale-stato-pagato">
                <div style={{ fontWeight: 'bold', color: '#166534', fontSize: 16 }}>✅ PAGATO</div>
                <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '120px 1fr', rowGap: 6, fontSize: 13 }}>
                  {verbale?.importo ? (<><span style={{ color: '#666' }}>Importo</span><span style={{ fontWeight: 600 }}>{formatEuro(verbale.importo)}</span></>) : null}
                  {verbale?.data_pagamento ? (<><span style={{ color: '#666' }}>Data</span><span>{formatDateIT(verbale.data_pagamento)}</span></>) : null}
                  {verbale?.psp ? (<><span style={{ color: '#666' }}>PSP</span><span>{verbale.psp}</span></>) : null}
                  {verbale?.metodo_pagamento ? (<><span style={{ color: '#666' }}>Metodo</span><span>{verbale.metodo_pagamento}</span></>) : null}
                  {verbale?.fonte_riconciliazione ? (<><span style={{ color: '#666' }}>Fonte</span><span>{verbale.fonte_riconciliazione}</span></>) : null}
                  {verbale?.iuv ? (<><span style={{ color: '#666' }}>IUV</span><span style={{ fontFamily: 'Courier New', fontSize: 11 }}>{verbale.iuv}</span></>) : null}
                </div>
                {verbale?.pdf_ricevuta_path && (
                  <a
                    href={`/api/verbali-noleggio/${encodeURIComponent(verbale.id || verbale.numero_verbale)}/ricevuta-pdf`}
                    target="_blank" rel="noopener noreferrer"
                    data-testid="verbale-scarica-ricevuta-btn"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 16,
                      padding: '10px 18px', borderRadius: 20, background: '#15803d',
                      color: '#fff', textDecoration: 'none', fontWeight: 600, fontSize: 13,
                    }}
                  >
                    📥 Scarica ricevuta
                  </a>
                )}
              </div>
            ) : (
              <div style={{ 
                padding: 16, 
                background: '#fef3c7', 
                borderRadius: 8, 
                textAlign: 'center',
                border: '1px solid #b45309',
              }} data-testid="verbale-stato-da-verificare">
                <div style={{ fontSize: 36, marginBottom: 8 }}>⚠️</div>
                <div style={{ fontWeight: 'bold', color: '#92400e' }}>
                  {verbale?.stato === 'sospeso' || verbale?.stato_pagamento === 'sospeso' ? 'SOSPESO' : 'DA VERIFICARE'}
                </div>
                <div style={{ fontSize: 12, color: '#b45309', marginTop: 4, marginBottom: 14 }}>
                  Non trovato automaticamente
                </div>
                <button
                  data-testid="verbale-cerca-pagamento-btn"
                  onClick={async () => {
                    try {
                      const vid = verbale?.id || verbale?.numero_verbale;
                      const res = await api.post(`/api/verbali-noleggio/${encodeURIComponent(vid)}/cerca-pagamento`);
                      const d = res.data;
                      if (d.trovato) {
                        alert(`✅ Pagamento trovato!\nFonte: ${d.fonte}\nPSP: ${d.psp}\nImporto: ${formatEuro(d.importo)}\nData: ${d.data_pagamento || ''}`);
                        setTimeout(() => window.location.reload(), 500);
                      } else {
                        alert('Nessun pagamento trovato per questo verbale.');
                      }
                    } catch (e) {
                      alert('Errore: ' + (e.response?.data?.detail || e.message));
                    }
                  }}
                  style={{
                    background: 'linear-gradient(135deg, #0f2744 0%, #1e3a5f 100%)',
                    color: '#fff', border: 'none', padding: '12px 24px',
                    borderRadius: 20, fontWeight: 600, cursor: 'pointer', fontSize: 13,
                  }}
                >
                  🔍 Cerca pagamento
                </button>
              </div>
            )}
            
            {verbale?.movimento_info && (
              <div style={{ marginTop: 16, fontSize: 13 }}>
                <div style={{ fontWeight: 'bold', marginBottom: 8 }}>Movimento bancario associato:</div>
                <div style={{ 
                  background: '#f9fafb', 
                  padding: 12, 
                  borderRadius: 8,
                  fontSize: 12
                }}>
                  <div>Data: {formatDateIT(verbale.movimento_info.data)}</div>
                  <div>Importo: {formatEuro(verbale.movimento_info.importo)}</div>
                  <div>Causale: {verbale.movimento_info.causale || verbale.movimento_info.descrizione}</div>
                </div>
              </div>
            )}
          </div>

          {/* Info Veicolo */}
          {verbale?.veicolo_info && (
            <div style={{ 
              background: 'white', 
              borderRadius: 12, 
              padding: 20, 
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
            }}>
              <h3 style={{ margin: '0 0 16px 0', fontSize: 16, color: '#1e3a5f' }}>🚗 Veicolo</h3>
              
              <div style={{ fontSize: 13, lineHeight: 2 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                  <span style={{ color: '#6b7280' }}>Targa:</span>
                  <strong style={{ fontFamily: 'monospace' }}>{verbale.veicolo_info.targa}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                  <span style={{ color: '#6b7280' }}>Driver:</span>
                  <strong>{verbale.veicolo_info.driver || '-'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                  <span style={{ color: '#6b7280' }}>Fornitore:</span>
                  <strong>{verbale.veicolo_info.fornitore_noleggio}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 8 }}>
                  <span style={{ color: '#6b7280' }}>Contratto:</span>
                  <strong style={{ fontFamily: 'monospace' }}>{verbale.veicolo_info.contratto || '-'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>Periodo:</span>
                  <strong>{formatDateIT(verbale.veicolo_info.data_inizio)} - {formatDateIT(verbale.veicolo_info.data_fine)}</strong>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div style={{ marginTop: 24, textAlign: 'center' }}>
        <button 
          onClick={() => navigate(-1)}
          style={{ 
            padding: '12px 24px', 
            background: '#f3f4f6', 
            color: '#374151', 
            border: 'none', 
            borderRadius: 8, 
            cursor: 'pointer',
            fontSize: 14,
            fontWeight: '600'
          }}
        >
          ← Torna indietro
        </button>
      </div>
    </div>
    </PageLayout>
  );
}
