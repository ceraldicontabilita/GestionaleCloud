import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

export default function VerificaCoerenza() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(false);
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/verifica-coerenza\/([\w-]+)/);
    return match ? match[1] : 'riepilogo';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/verifica-coerenza/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [verificaCompleta, setVerificaCompleta] = useState(null);
  const [confrontoIva, setConfrontoIva] = useState(null);
  const [bonifici, setBonifici] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadAll();
  }, [anno]);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [completa, iva, bonif] = await Promise.all([
        api.get(`/api/verifica-coerenza/completa/${anno}`),
        api.get(`/api/verifica-coerenza/confronto-iva-completo/${anno}`),
        api.get(`/api/verifica-coerenza/verifica-bonifici-vs-banca/${anno}`)
      ]);
      setVerificaCompleta(completa.data);
      setConfrontoIva(iva.data);
      setBonifici(bonif.data);
    } catch (err) {
      console.error('Errore caricamento:', err);
      setError('Errore nel caricamento dei dati');
    } finally {
      setLoading(false);
    }
  };

  const getStatoColor = (stato) => {
    switch (stato) {
      case 'OK': return { bg: '#dcfce7', text: '#166534', border: '#bbf7d0' };
      case 'ATTENZIONE': return { bg: '#fef3c7', text: '#92400e', border: '#fde68a' };
      case 'CRITICO': return { bg: '#fef2f2', text: '#991b1b', border: '#fecaca' };
      default: return { bg: '#f1f5f9', text: '#475569', border: '#e2e8f0' };
    }
  };

  const stato = verificaCompleta?.stato_generale || 'OK';
  const statoColors = getStatoColor(stato);

  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    border: '1px solid #e2e8f0',
    overflow: 'hidden'
  };

  const cardHeaderStyle = {
    padding: '12px 16px',
    borderBottom: '1px solid #e2e8f0',
    background: '#f8fafc'
  };

  const cardTitleStyle = {
    margin: 0,
    fontSize: 14,
    fontWeight: 600,
    color: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    gap: 8
  };

  const cardContentStyle = {
    padding: 16
  };

  const tabStyle = (isActive) => ({
    padding: '10px 16px',
    borderRadius: 8,
    border: 'none',
    background: isActive ? '#1535a8' : 'transparent',
    color: isActive ? 'white' : '#64748b',
    fontWeight: 500,
    cursor: 'pointer',
    fontSize: 13,
    display: 'flex',
    alignItems: 'center',
    gap: 8
  });

  return (
    <PageLayout 
      title="Verifica Coerenza Dati" 
      icon="🔍" 
      subtitle={`Controllo automatico - Anno ${anno}`}
      actions={
        <button 
          onClick={loadAll} 
          disabled={loading} 
          data-testid="btn-ricarica-verifica"
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            border: 'none',
            background: '#1535a8',
            color: 'white',
            fontWeight: 500,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.7 : 1,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          🔄 Ricarica
        </button>
      }
    >
      {error && (
        <div style={{ 
          padding: 12, 
          background: '#fef2f2', 
          borderRadius: 8, 
          color: '#991b1b',
          marginBottom: 16,
          fontSize: 13
        }}>
          {error}
        </div>
      )}

      {/* Stato Generale Card */}
      {verificaCompleta && (
        <div style={{ 
          ...cardStyle,
          marginBottom: 16, 
          background: statoColors.bg,
          border: `2px solid ${statoColors.border}`
        }}>
          <div style={{ ...cardContentStyle, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 40 }}>
                  {stato === 'OK' ? '✅' : stato === 'ATTENZIONE' ? '⚠️' : '❌'}
                </span>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 'bold', color: statoColors.text }}>
                    Stato: {stato}
                  </div>
                  <div style={{ color: '#64748b', fontSize: 12 }}>
                    Ultima verifica: {new Date(verificaCompleta.timestamp).toLocaleString('it-IT')}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 20, textAlign: 'center' }}>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: '#dc2626' }}>
                    {verificaCompleta.riepilogo?.critical || 0}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b' }}>Critiche</div>
                </div>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: '#f59e0b' }}>
                    {verificaCompleta.riepilogo?.warning || 0}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b' }}>Avvisi</div>
                </div>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1535a8' }}>
                    {verificaCompleta.riepilogo?.info || 0}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b' }}>Info</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ marginBottom: 16, background: '#f1f5f9', padding: 4, borderRadius: 12, display: 'flex', gap: 4 }}>
        <button onClick={() => handleTabChange('riepilogo')} style={tabStyle(activeTab === 'riepilogo')}>
          📋 Riepilogo
        </button>
        <button onClick={() => handleTabChange('iva')} style={tabStyle(activeTab === 'iva')}>
          📈 IVA Mensile
        </button>
        <button onClick={() => handleTabChange('discrepanze')} style={tabStyle(activeTab === 'discrepanze')}>
          ⚠️ Discrepanze
        </button>
      </div>

      {/* TAB RIEPILOGO */}
      {activeTab === 'riepilogo' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
          
          {/* IVA Annuale */}
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={cardTitleStyle}>🧾 IVA Annuale {anno}</h3>
            </div>
            <div style={cardContentStyle}>
              {verificaCompleta?.verifiche?.iva_annuale && (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: 10, background: '#fef2f2', borderRadius: 6 }}>
                    <span style={{ color: '#991b1b', fontSize: 13 }}>IVA Debito</span>
                    <strong style={{ color: '#dc2626' }}>{formatEuro(verificaCompleta.verifiche.iva_annuale.iva_debito_totale)}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: 10, background: '#dcfce7', borderRadius: 6 }}>
                    <span style={{ color: '#166534', fontSize: 13 }}>IVA Credito</span>
                    <strong style={{ color: '#059669' }}>{formatEuro(verificaCompleta.verifiche.iva_annuale.iva_credito_totale)}</strong>
                  </div>
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    padding: 10, 
                    background: verificaCompleta.verifiche.iva_annuale.saldo_iva > 0 ? '#fef3c7' : '#dbeafe',
                    borderRadius: 6,
                    fontWeight: 'bold'
                  }}>
                    <span style={{ fontSize: 13 }}>Saldo IVA</span>
                    <span style={{ color: verificaCompleta.verifiche.iva_annuale.saldo_iva > 0 ? '#92400e' : '#1535a8' }}>
                      {verificaCompleta.verifiche.iva_annuale.saldo_iva > 0 ? 'Da versare ' : 'A credito '}
                      {formatEuro(Math.abs(verificaCompleta.verifiche.iva_annuale.saldo_iva))}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Versamenti */}
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={cardTitleStyle}>💳 Versamenti Cassa vs Banca</h3>
            </div>
            <div style={cardContentStyle}>
              {verificaCompleta?.verifiche?.versamenti && (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>Versamenti (Cassa)</span>
                    <strong>{formatEuro(verificaCompleta.verifiche.versamenti.versamenti_manuali)}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>Versamenti (Banca)</span>
                    <strong>{formatEuro(verificaCompleta.verifiche.versamenti.versamenti_banca)}</strong>
                  </div>
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between',
                    padding: 10,
                    background: Math.abs(verificaCompleta.verifiche.versamenti.differenza) < 1 ? '#dcfce7' : '#fef2f2',
                    borderRadius: 6
                  }}>
                    <span style={{ fontSize: 13 }}>Differenza</span>
                    <strong style={{ 
                      color: Math.abs(verificaCompleta.verifiche.versamenti.differenza) < 1 ? '#166534' : '#dc2626'
                    }}>
                      {Math.abs(verificaCompleta.verifiche.versamenti.differenza) < 1 ? '✅ OK' : formatEuro(verificaCompleta.verifiche.versamenti.differenza)}
                    </strong>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Saldi */}
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={cardTitleStyle}>🏦 Prima Nota vs E/C</h3>
            </div>
            <div style={cardContentStyle}>
              {verificaCompleta?.verifiche?.saldi && (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>Prima Nota</span>
                    <strong>{formatEuro(verificaCompleta.verifiche.saldi.saldo_prima_nota)}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>Estratto Conto</span>
                    <strong>{formatEuro(verificaCompleta.verifiche.saldi.saldo_estratto_conto)}</strong>
                  </div>
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between',
                    padding: 10,
                    background: Math.abs(verificaCompleta.verifiche.saldi.differenza) < 1 ? '#dcfce7' : '#fef2f2',
                    borderRadius: 6
                  }}>
                    <span style={{ fontSize: 13 }}>Differenza</span>
                    <strong style={{ 
                      color: Math.abs(verificaCompleta.verifiche.saldi.differenza) < 1 ? '#166534' : '#dc2626'
                    }}>
                      {Math.abs(verificaCompleta.verifiche.saldi.differenza) < 1 ? '✅ OK' : formatEuro(verificaCompleta.verifiche.saldi.differenza)}
                    </strong>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Bonifici */}
          <div style={cardStyle}>
            <div style={cardHeaderStyle}>
              <h3 style={cardTitleStyle}>📄 Bonifici vs Banca</h3>
            </div>
            <div style={cardContentStyle}>
              {bonifici && (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>Registrati</span>
                    <strong>{formatEuro(bonifici.bonifici_registrati.totale)} ({bonifici.bonifici_registrati.count})</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>Riconciliati</span>
                    <strong style={{ color: '#059669' }}>{bonifici.bonifici_registrati.riconciliati}/{bonifici.bonifici_registrati.count}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>In Banca</span>
                    <strong>{formatEuro(bonifici.bonifici_banca.totale)} ({bonifici.bonifici_banca.count})</strong>
                  </div>
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between',
                    padding: 10,
                    background: bonifici.coerente ? '#dcfce7' : '#fef2f2',
                    borderRadius: 6
                  }}>
                    <span style={{ fontSize: 13 }}>Stato</span>
                    <strong style={{ color: bonifici.coerente ? '#166534' : '#dc2626' }}>
                      {bonifici.coerente ? '✅ OK' : formatEuro(bonifici.differenza)}
                    </strong>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB IVA MENSILE */}
      {activeTab === 'iva' && confrontoIva && (
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <h3 style={cardTitleStyle}>Confronto IVA Mensile {anno}</h3>
          </div>
          <div style={cardContentStyle}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f1f5f9' }}>
                    <th style={{ padding: 10, textAlign: 'left' }}>Mese</th>
                    <th style={{ padding: 10, textAlign: 'right' }}>IVA Debito</th>
                    <th style={{ padding: 10, textAlign: 'center' }}>N.Corr</th>
                    <th style={{ padding: 10, textAlign: 'right' }}>IVA Credito</th>
                    <th style={{ padding: 10, textAlign: 'center' }}>N.Fatt</th>
                    <th style={{ padding: 10, textAlign: 'right' }}>Saldo</th>
                    <th style={{ padding: 10, textAlign: 'center' }}>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {confrontoIva.mensile?.map((m, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0' }}>
                      <td style={{ padding: 10, fontWeight: 'bold' }}>{m.mese_nome}</td>
                      <td style={{ padding: 10, textAlign: 'right', color: '#dc2626' }}>
                        {formatEuro(m.iva_debito_corrispettivi)}
                      </td>
                      <td style={{ padding: 10, textAlign: 'center', color: '#64748b' }}>
                        {m.num_corrispettivi}
                      </td>
                      <td style={{ padding: 10, textAlign: 'right', color: '#059669' }}>
                        {formatEuro(m.iva_credito_fatture)}
                      </td>
                      <td style={{ padding: 10, textAlign: 'center', color: '#64748b' }}>
                        {m.num_fatture}
                      </td>
                      <td style={{ 
                        padding: 10, 
                        textAlign: 'right', 
                        fontWeight: 'bold',
                        color: m.saldo > 0 ? '#dc2626' : '#059669'
                      }}>
                        {m.saldo > 0 ? '+' : ''}{formatEuro(m.saldo)}
                      </td>
                      <td style={{ padding: 10, textAlign: 'center' }}>
                        {m.da_versare > 0 ? (
                          <span style={{ 
                            padding: '2px 6px', 
                            borderRadius: 4, 
                            background: '#fef3c7', 
                            color: '#92400e',
                            fontSize: 10
                          }}>
                            Versare {formatEuro(m.da_versare)}
                          </span>
                        ) : (
                          <span style={{ 
                            padding: '2px 6px', 
                            borderRadius: 4, 
                            background: '#dbeafe', 
                            color: '#1535a8',
                            fontSize: 10
                          }}>
                            Credito {formatEuro(m.a_credito)}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: '#1e293b', color: 'white', fontWeight: 'bold' }}>
                    <td style={{ padding: 10 }}>TOTALE {anno}</td>
                    <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(confrontoIva.totali?.iva_debito_totale)}</td>
                    <td style={{ padding: 10 }}></td>
                    <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(confrontoIva.totali?.iva_credito_totale)}</td>
                    <td style={{ padding: 10 }}></td>
                    <td style={{ padding: 10, textAlign: 'right' }}>
                      {confrontoIva.totali?.saldo_annuale > 0 ? '+' : ''}{formatEuro(confrontoIva.totali?.saldo_annuale)}
                    </td>
                    <td style={{ padding: 10, textAlign: 'center', fontSize: 10 }}>
                      {confrontoIva.totali?.saldo_annuale > 0 ? 'DA VERSARE' : 'A CREDITO'}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB DISCREPANZE */}
      {activeTab === 'discrepanze' && (
        verificaCompleta?.discrepanze?.length > 0 ? (
          <div style={{ ...cardStyle, border: '2px solid #fecaca' }}>
            <div style={{ ...cardHeaderStyle, background: '#fef2f2' }}>
              <h3 style={{ ...cardTitleStyle, color: '#991b1b' }}>
                ⚠️ Discrepanze Rilevate ({verificaCompleta.discrepanze.length})
              </h3>
            </div>
            <div style={cardContentStyle}>
              <div style={{ display: 'grid', gap: 12 }}>
                {verificaCompleta.discrepanze.map((d, idx) => (
                  <div 
                    key={idx}
                    style={{
                      padding: 14,
                      background: d.severita === 'critical' ? '#fef2f2' : '#fffbeb',
                      borderRadius: 8,
                      border: `1px solid ${d.severita === 'critical' ? '#fecaca' : '#fde68a'}`
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 'bold',
                            background: d.severita === 'critical' ? '#dc2626' : '#f59e0b',
                            color: 'white'
                          }}>
                            {d.severita.toUpperCase()}
                          </span>
                          <strong style={{ color: '#1e293b', fontSize: 13 }}>{d.categoria}</strong>
                          <span style={{ color: '#64748b', fontSize: 12 }}>• {d.sottocategoria}</span>
                        </div>
                        <p style={{ margin: '6px 0', color: '#475569', fontSize: 13 }}>{d.descrizione}</p>
                        {d.periodo && (
                          <span style={{ fontSize: 11, color: '#94a3b8' }}>Periodo: {d.periodo}</span>
                        )}
                      </div>
                      <div style={{ textAlign: 'right', minWidth: 100 }}>
                        <div style={{ fontSize: 11, color: '#64748b' }}>Atteso</div>
                        <div style={{ fontWeight: 'bold', color: '#059669', fontSize: 14 }}>{formatEuro(d.valore_atteso)}</div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>Trovato</div>
                        <div style={{ fontWeight: 'bold', color: '#dc2626', fontSize: 14 }}>{formatEuro(d.valore_trovato)}</div>
                        <div style={{ 
                          marginTop: 6,
                          padding: '3px 8px',
                          background: '#1e293b',
                          color: 'white',
                          borderRadius: 4,
                          fontWeight: 'bold',
                          fontSize: 12
                        }}>
                          Δ {d.differenza > 0 ? '+' : ''}{formatEuro(d.differenza)}
                        </div>
                      </div>
                    </div>
                    {d.suggerimento && (
                      <div style={{ 
                        marginTop: 10, 
                        padding: 10, 
                        background: 'white', 
                        borderRadius: 6,
                        fontSize: 12,
                        color: '#64748b',
                        borderLeft: '3px solid #1535a8'
                      }}>
                        💡 <strong>Suggerimento:</strong> {d.suggerimento}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ ...cardStyle, background: '#dcfce7', border: '2px solid #bbf7d0' }}>
            <div style={{ ...cardContentStyle, padding: 40, textAlign: 'center' }}>
              <div style={{ fontSize: 56, marginBottom: 12 }}>✅</div>
              <h3 style={{ margin: 0, color: '#166534', fontSize: 20 }}>Tutti i Dati sono Coerenti!</h3>
              <p style={{ margin: '8px 0 0', color: '#15803d', fontSize: 13 }}>
                Non sono state rilevate discrepanze tra le varie sezioni del gestionale.
              </p>
            </div>
          </div>
        )
      )}
    </PageLayout>
  );
}
