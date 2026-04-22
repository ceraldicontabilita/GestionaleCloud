import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

export default function PrevisioniAcquisti() {
  const { anno: annoGlobale } = useAnnoGlobale();
  const [activeTab, setActiveTab] = useState('statistiche');
  const [statistiche, setStatistiche] = useState([]);
  const [previsioni, setPrevisioni] = useState([]);
  const [loading, setLoading] = useState(false);
  const [popolando, setPopolando] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [settimanePrevisione, setSettimanePrevisione] = useState(4);
  const [costoTotale, setCostoTotale] = useState(0);
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    loadData();
  }, [annoGlobale, activeTab, settimanePrevisione]);

  const loadData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'statistiche') {
        const res = await api.get(`/api/previsioni-acquisti/statistiche?anno=${annoGlobale}`);
        setStatistiche(res.data.statistiche || []);
      } else {
        const annoRif = annoGlobale - 1;
        const res = await api.get(
          `/api/previsioni-acquisti/previsioni?anno_riferimento=${annoRif}&settimane_previsione=${settimanePrevisione}`
        );
        setPrevisioni(res.data.previsioni || []);
        setCostoTotale(res.data.costo_totale_stimato || 0);
      }
    } catch (error) {
      console.error('Errore:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePopolaStorico = async () => {
    setPopolando(true);
    try {
      const res = await api.post('/api/previsioni-acquisti/popola-storico');
      alert(
        `✅ Storico popolato!\n\nFatture processate: ${res.data.fatture_processate}\nProdotti registrati: ${res.data.prodotti_registrati}`
      );
      loadData();
    } catch (error) {
      alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
    } finally {
      setPopolando(false);
    }
  };

  const filteredData =
    activeTab === 'statistiche'
      ? statistiche.filter(s => s.descrizione?.toLowerCase().includes(searchTerm.toLowerCase()))
      : previsioni.filter(p => p.prodotto?.toLowerCase().includes(searchTerm.toLowerCase()));

  const getTrendColor = trend => {
    if (trend === '↑') return '#16a34a';
    if (trend === '↓') return '#dc2626';
    return '#64748b';
  };

  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    border: '1px solid #e2e8f0',
    overflow: 'hidden',
  };

  const cardHeaderStyle = {
    padding: '16px 20px',
    borderBottom: '1px solid #e2e8f0',
    background: '#f8fafc',
  };

  const cardTitleStyle = {
    margin: 0,
    fontSize: 16,
    fontWeight: 600,
    color: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  };

  const cardContentStyle = {
    padding: 20,
  };

  const buttonStyle = (variant = 'default') => ({
    padding: '8px 16px',
    borderRadius: 8,
    border: variant === 'outline' ? '1px solid #e2e8f0' : 'none',
    background: variant === 'outline' ? 'transparent' : variant === 'green' ? '#059669' : '#3b82f6',
    color: variant === 'outline' ? '#64748b' : 'white',
    fontWeight: 500,
    cursor: 'pointer',
    fontSize: 13,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  });

  return (
    <PageLayout title="Previsioni Acquisti" subtitle="Analisi consumi e previsioni ordinazioni">
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'wrap',
              marginBottom: 8,
            }}
          >
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 'bold', color: '#1e293b' }}>
              📊 Previsioni Acquisti
            </h1>
            <span
              style={{
                padding: '4px 10px',
                background: '#8b5cf6',
                color: 'white',
                borderRadius: 16,
                fontSize: 12,
                fontWeight: 'bold',
              }}
            >
              {annoGlobale}
            </span>
          </div>
          <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>
            Analisi storico acquisti e previsioni basate sui consumi
          </p>
        </div>

        {/* Tabs e Controlli */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            marginBottom: 16,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <button
            onClick={() => setActiveTab('statistiche')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: activeTab === 'statistiche' ? '#3b82f6' : '#e2e8f0',
              color: activeTab === 'statistiche' ? 'white' : '#64748b',
              fontWeight: 'bold',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            📈 Statistiche {annoGlobale}
          </button>
          <button
            onClick={() => setActiveTab('previsioni')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: activeTab === 'previsioni' ? '#8b5cf6' : '#e2e8f0',
              color: activeTab === 'previsioni' ? 'white' : '#64748b',
              fontWeight: 'bold',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            🔮 Previsioni
          </button>

          <div style={{ flex: 1 }} />

          {activeTab === 'previsioni' && (
            <select
              value={settimanePrevisione}
              onChange={e => setSettimanePrevisione(Number(e.target.value))}
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                fontSize: 13,
              }}
            >
              <option value={1}>1 settimana</option>
              <option value={2}>2 settimane</option>
              <option value={4}>4 settimane</option>
              <option value={8}>8 settimane</option>
              <option value={12}>12 settimane</option>
            </select>
          )}

          <button
            onClick={loadData}
            disabled={loading}
            style={buttonStyle('outline')}
            data-testid="refresh-btn"
          >
            🔄
          </button>

          <button
            onClick={handlePopolaStorico}
            disabled={popolando}
            style={buttonStyle('green')}
            data-testid="popola-storico-btn"
          >
            {popolando ? 'Popolando...' : '🔄 Popola Storico'}
          </button>
        </div>

        {/* Ricerca */}
        <div style={{ marginBottom: 16, position: 'relative' }}>
          <span
            style={{
              position: 'absolute',
              left: 12,
              top: '50%',
              transform: 'translateY(-50%)',
              fontSize: 16,
            }}
          >
            🔍
          </span>
          <input
            type="text"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Cerca prodotto (es: caffè, prosecco, farina...)"
            style={{
              width: '100%',
              padding: '10px 12px 10px 40px',
              borderRadius: 8,
              border: '1px solid #e2e8f0',
              fontSize: 14,
              boxSizing: 'border-box',
            }}
            data-testid="search-input"
          />
        </div>

        {/* Riepilogo Previsioni */}
        {activeTab === 'previsioni' && costoTotale > 0 && (
          <div
            style={{
              ...cardStyle,
              marginBottom: 16,
              background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
            }}
          >
            <div style={{ ...cardContentStyle, paddingTop: 16 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  color: 'white',
                }}
              >
                <div>
                  <div style={{ fontSize: 13, opacity: 0.9 }}>
                    Costo stimato prossime {settimanePrevisione} settimane
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 'bold' }}>{formatEuro(costoTotale)}</div>
                </div>
                <span style={{ fontSize: 40, opacity: 0.3 }}>🛒</span>
              </div>
            </div>
          </div>
        )}

        {/* Lista Prodotti */}
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <h2 style={cardTitleStyle}>
              {activeTab === 'statistiche' ? (
                <>
                  📊 Consumi {annoGlobale} vs {annoGlobale - 1}
                </>
              ) : (
                <>📦 Acquisti Previsti ({filteredData.length} prodotti)</>
              )}
            </h2>
          </div>
          <div style={cardContentStyle}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
                <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
                Caricamento...
              </div>
            ) : filteredData.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
                <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>📦</div>
                <p>Nessun dato trovato</p>
                <p style={{ fontSize: 13 }}>
                  Clicca &quot;Popola Storico&quot; per importare i dati dalle fatture
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {filteredData.slice(0, 50).map((item, idx) => (
                  <div
                    key={item.id || idx}
                    style={{
                      padding: 12,
                      background: '#f8fafc',
                      borderRadius: 8,
                      border: '1px solid #e2e8f0',
                    }}
                    data-testid={`product-item-${idx}`}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        cursor: 'pointer',
                      }}
                      onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                    >
                      <div style={{ flex: 1 }}>
                        <div
                          style={{
                            fontWeight: 'bold',
                            fontSize: 14,
                            color: '#1e293b',
                            marginBottom: 4,
                          }}
                        >
                          {activeTab === 'statistiche' ? item.descrizione : item.prodotto}
                        </div>
                        <div
                          style={{
                            display: 'flex',
                            gap: 12,
                            fontSize: 12,
                            color: '#64748b',
                            flexWrap: 'wrap',
                          }}
                        >
                          {activeTab === 'statistiche' ? (
                            <>
                              <span>
                                📦 {item.quantita_totale?.toFixed(1)} {item.unita_misura}
                              </span>
                              <span>📅 Media/gg: {item.media_giornaliera}</span>
                              <span>📆 Media/sett: {item.media_settimanale}</span>
                            </>
                          ) : (
                            <>
                              <span>
                                Prev: {item.quantita_prevista?.toFixed(1)} {item.unita_misura}
                              </span>
                              <span>{item.media_settimanale}/sett</span>
                              <span>{formatEuro(item.costo_stimato)}</span>
                            </>
                          )}
                        </div>
                      </div>

                      {activeTab === 'statistiche' && item.trend && (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4,
                            padding: '4px 8px',
                            borderRadius: 4,
                            background:
                              item.trend === '↑'
                                ? '#dcfce7'
                                : item.trend === '↓'
                                  ? '#fee2e2'
                                  : '#f3f4f6',
                            color: getTrendColor(item.trend),
                            fontSize: 12,
                            fontWeight: 'bold',
                          }}
                        >
                          {item.trend === '↑' ? '📈' : item.trend === '↓' ? '📉' : ''}
                          {item.variazione_pct > 0 ? '+' : ''}
                          {item.variazione_pct}%
                        </div>
                      )}

                      <span style={{ marginLeft: 8 }}>{expandedId === item.id ? '▲' : '▼'}</span>
                    </div>

                    {/* Dettagli espansi */}
                    {expandedId === item.id && (
                      <div
                        style={{
                          marginTop: 12,
                          paddingTop: 12,
                          borderTop: '1px solid #e2e8f0',
                          fontSize: 12,
                          color: '#64748b',
                        }}
                      >
                        {activeTab === 'statistiche' ? (
                          <div
                            style={{
                              display: 'grid',
                              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                              gap: 8,
                            }}
                          >
                            <div>
                              <strong>Spesa totale:</strong> {formatEuro(item.spesa_totale)}
                            </div>
                            <div>
                              <strong>N. ordini:</strong> {item.num_acquisti}
                            </div>
                            <div>
                              <strong>Ogni:</strong> {item.frequenza_giorni} giorni
                            </div>
                            <div>
                              <strong>Anno prec.:</strong> {item.quantita_anno_prec?.toFixed(1)}{' '}
                              {item.unita_misura}
                            </div>
                            <div>
                              <strong>Primo:</strong> {item.primo_acquisto}
                            </div>
                            <div>
                              <strong>Ultimo:</strong> {item.ultimo_acquisto}
                            </div>
                          </div>
                        ) : (
                          <div
                            style={{
                              display: 'grid',
                              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                              gap: 8,
                            }}
                          >
                            <div>
                              <strong>Anno rif.:</strong> {item.quantita_anno_rif?.toFixed(1)}{' '}
                              {item.unita_misura}
                            </div>
                            <div>
                              <strong>Prezzo medio:</strong> {formatEuro(item.prezzo_medio)}
                            </div>
                            <div>
                              <strong>Ordina ogni:</strong>{' '}
                              {item.frequenza_ordine_settimane?.toFixed(1)} sett.
                            </div>
                            <div>
                              <strong>Prossimo ordine:</strong> tra{' '}
                              {item.prossimo_ordine_tra_giorni} gg
                            </div>
                            {item.fornitori_abituali?.length > 0 && (
                              <div style={{ gridColumn: 'span 2' }}>
                                <strong>Fornitori:</strong> {item.fornitori_abituali.join(', ')}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Info */}
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: '#f0fdf4',
            borderRadius: 8,
            fontSize: 12,
            color: '#166534',
          }}
        >
          💡 <strong>Come funziona:</strong> Il sistema analizza lo storico acquisti dalle fatture
          XML. Calcola medie giornaliere/settimanali e confronta con l&apos;anno precedente per
          suggerirti gli acquisti.
          <br />
          📊 <strong>Statistiche:</strong> Mostra consumi dell&apos;anno corrente vs anno
          precedente.
          <br />
          🔮 <strong>Previsioni:</strong> Propone quantità da ordinare basate sui consumi storici.
        </div>
      </div>
    </PageLayout>
  );
}
