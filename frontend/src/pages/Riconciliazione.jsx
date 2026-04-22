import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from 'react-router-dom';
import api from "../api";
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge , useIsMobile, RG, pagePad } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

// Stile comune (stesso di OperazioniDaConfermare)
const pageStyle = {
  container: {
    padding: '24px',
    maxWidth: '1400px',
    margin: '0 auto',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  },
  header: {
    marginBottom: '24px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '16px',
    padding: '15px 20px',
    background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
    borderRadius: '12px',
    color: 'white'
  },
  title: {
    margin: 0,
    fontSize: '22px',
    fontWeight: 'bold',
    color: 'white',
    display: 'flex',
    alignItems: 'center',
    gap: '10px'
  },
  subtitle: {
    margin: '4px 0 0 0',
    color: 'rgba(255,255,255,0.9)',
    fontSize: '13px'
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
    gap: '16px',
    marginBottom: '24px'
  },
  statCard: (color) => ({
    background: `linear-gradient(135deg, ${color}15, ${color}08)`,
    borderRadius: '12px',
    padding: '20px',
    border: `1px solid ${color}30`
  }),
  statValue: (color) => ({
    fontSize: '32px',
    fontWeight: 'bold',
    color: color,
    margin: 0
  }),
  statLabel: {
    fontSize: '13px',
    color: '#64748b',
    marginTop: '4px'
  },
  card: {
    background: 'white',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    overflow: 'hidden',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
    marginBottom: '24px'
  },
  cardHeader: {
    padding: '16px 20px',
    borderBottom: '1px solid #e2e8f0',
    background: '#f8fafc',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  cardTitle: {
    margin: 0,
    fontSize: '16px',
    fontWeight: '600',
    color: '#1e293b'
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '14px'
  },
  th: {
    padding: '12px 16px',
    textAlign: 'left',
    fontWeight: '600',
    color: '#475569',
    borderBottom: '2px solid #e2e8f0',
    background: '#f8fafc'
  },
  td: {
    padding: '12px 16px',
    borderBottom: '1px solid #f1f5f9',
    color: '#334155'
  },
  badge: (color) => ({
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 10px',
    borderRadius: '20px',
    fontSize: '12px',
    fontWeight: '600',
    background: `${color}15`,
    color: color
  }),
  button: (variant = 'primary') => ({
    padding: '8px 16px',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: '13px',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    transition: 'all 0.2s',
    ...(variant === 'primary' ? {
      background: '#3b82f6',
      color: 'white'
    } : variant === 'success' ? {
      background: '#10b981',
      color: 'white'
    } : variant === 'danger' ? {
      background: '#ef4444',
      color: 'white'
    } : {
      background: 'rgba(255,255,255,0.9)',
      color: '#1e3a5f'
    })
  }),
  tabs: {
    display: 'flex',
    gap: '4px',
    marginBottom: '24px',
    background: '#f1f5f9',
    padding: '4px',
    borderRadius: '10px',
    width: 'fit-content'
  },
  tab: (active) => ({
    padding: '10px 20px',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: '14px',
    transition: 'all 0.2s',
    background: active ? 'white' : 'transparent',
    color: active ? '#1e293b' : '#64748b',
    boxShadow: active ? '0 1px 3px rgba(0,0,0,0.1)' : 'none'
  }),
  emptyState: {
    textAlign: 'center',
    padding: '60px 20px',
    color: '#64748b'
  }
};

export default function Riconciliazione() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/riconciliazione\/([\w-]+)/);
    return match ? match[1] : 'automatica';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/riconciliazione/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [processing, setProcessing] = useState(false);
  
  // Dati per riconciliazione manuale
  const [movimentiNonRiconciliati, setMovimentiNonRiconciliati] = useState([]);
  const [fattureNonPagate, setFattureNonPagate] = useState([]);
  const [selectedMovimento, setSelectedMovimento] = useState(null);
  const [matchingFatture, setMatchingFatture] = useState([]);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    loadStats();
  }, [anno]);

  useEffect(() => {
    if (activeTab === "manuale") {
      // Carica in parallelo ma con gestione errori separata
      Promise.all([
        loadMovimentiNonRiconciliati(),
        loadFattureNonPagate()
      ]).catch(e => console.error("Errore caricamento dati manuali:", e));
    }
  }, [activeTab, anno]);

  const loadStats = async () => {
    setLoading(true);
    setLoadError('');
    try {
      const res = await api.get(`/api/riconciliazione-auto/stats-riconciliazione?anno=${anno}`, { timeout: 30000 });
      setStats(res.data);
    } catch (e) {
      console.error("Errore caricamento stats:", e);
      setLoadError('Errore caricamento statistiche - riprova');
    } finally {
      setLoading(false);
    }
  };

  const loadMovimentiNonRiconciliati = async () => {
    try {
      const res = await api.get(`/api/estratto-conto-movimenti/movimenti?riconciliato=false&limit=200&anno=${anno}`);
      setMovimentiNonRiconciliati(res.data.movimenti || []);
    } catch (e) {
      console.error("Errore:", e);
    }
  };

  const loadFattureNonPagate = async () => {
    try {
      // Endpoint BE è /api/invoices con filtro status (non esiste /list né paid=false)
      // Prendiamo tutte le fatture dell'anno e filtriamo lato client quelle non pagate.
      const res = await api.get(`/api/invoices?limit=500&anno=${anno}`);
      const all = res.data.invoices || res.data || [];
      setFattureNonPagate(all.filter((inv) => !inv.pagato && inv.status !== 'paid'));
    } catch (e) {
      console.error("Errore:", e);
    }
  };

  const handleSelectMovimento = (mov) => {
    setSelectedMovimento(mov);
    const importoMov = Math.abs(mov.importo);
    
    const tolleranza = Math.max(importoMov * 0.1, 50);
    const matching = fattureNonPagate.filter(f => {
      const importoFattura = parseFloat(f.total_amount || f.importo || 0);
      return Math.abs(importoFattura - importoMov) <= tolleranza;
    }).sort((a, b) => {
      const diffA = Math.abs(parseFloat(a.total_amount || a.importo || 0) - importoMov);
      const diffB = Math.abs(parseFloat(b.total_amount || b.importo || 0) - importoMov);
      return diffA - diffB;
    });
    
    setMatchingFatture(matching);
  };

  const eseguiRiconciliazioneAutomatica = async () => {
    setProcessing(true);
    try {
      const res = await api.post('/api/riconciliazione-auto/riconcilia-estratto-conto');
      alert(`✅ Riconciliazione completata!\n\n` +
        `Movimenti analizzati: ${res.data.movimenti_analizzati}\n` +
        `Riconciliati: ${res.data.totale_riconciliati}\n` +
        `- Fatture: ${res.data.riconciliati_fatture}\n` +
        `- POS: ${res.data.riconciliati_pos}\n` +
        `- Versamenti: ${res.data.riconciliati_versamenti}\n` +
        `- F24: ${res.data.riconciliati_f24}\n\n` +
        `Da confermare: ${res.data.dubbi}\n` +
        `Non trovati: ${res.data.non_trovati}`
      );
      loadStats();
    } catch (e) {
      alert(`Errore: ${e.response?.data?.detail || e.message}`);
    } finally {
      setProcessing(false);
    }
  };

  const handleRiconciliaManuale = async (fattura) => {
    if (!selectedMovimento || !fattura) return;
    
    setProcessing(true);
    try {
      await api.post("/api/riconciliazione-fornitori/riconcilia-manuale", {
        movimento_id: selectedMovimento.id,
        fattura_id: fattura._id || fattura.id,
        importo_movimento: selectedMovimento.importo,
        data_movimento: selectedMovimento.data
      });
      
      setSelectedMovimento(null);
      setMatchingFatture([]);
      loadFattureNonPagate();
      loadMovimentiNonRiconciliati();
      loadStats();
      
      alert("✅ Riconciliazione completata!");
    } catch (e) {
      alert(`Errore: ${e.response?.data?.detail || e.message}`);
    } finally {
      setProcessing(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    try {
      return formatDateIT(dateStr);
    } catch { return dateStr; }
  };

  return (
    <PageLayout title="Riconciliazione Bancaria" subtitle="Associa i movimenti dell'estratto conto con fatture, POS, versamenti e F24">
    <div style={{...pageStyle.container, padding: 0}} data-testid="riconciliazione-page">
      {/* Header */}
      <div style={pageStyle.header}>
        <div>
          <h1 style={pageStyle.title}>
            <span>🔄</span> Riconciliazione Bancaria
          </h1>
          <p style={pageStyle.subtitle}>
            Associa i movimenti dell'estratto conto con fatture, POS, versamenti e F24
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            style={pageStyle.button('outline')} 
            onClick={loadStats}
            disabled={loading}
          >
            🔄 Aggiorna
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div style={pageStyle.statsGrid}>
          <div style={pageStyle.statCard('#3b82f6')}>
            <p style={pageStyle.statValue('#3b82f6')}>{stats.estratto_conto?.totali || 0}</p>
            <p style={pageStyle.statLabel}>Movimenti Totali EC</p>
          </div>
          <div style={pageStyle.statCard('#10b981')}>
            <p style={pageStyle.statValue('#10b981')}>{stats.estratto_conto?.riconciliati || 0}</p>
            <p style={pageStyle.statLabel}>Riconciliati</p>
          </div>
          <div style={pageStyle.statCard('#8b5cf6')}>
            <p style={pageStyle.statValue('#8b5cf6')}>{stats.estratto_conto?.automatici || 0}</p>
            <p style={pageStyle.statLabel}>Automatici</p>
          </div>
          <div style={pageStyle.statCard('#f59e0b')}>
            <p style={pageStyle.statValue('#f59e0b')}>{stats.operazioni_da_confermare || 0}</p>
            <p style={pageStyle.statLabel}>Da Confermare</p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div style={pageStyle.tabs}>
        <button 
          style={pageStyle.tab(activeTab === 'automatica')}
          onClick={() => handleTabChange('automatica')}
        >
          ⚡ Automatica
        </button>
        <button 
          style={pageStyle.tab(activeTab === 'manuale')}
          onClick={() => handleTabChange('manuale')}
        >
          ✋ Manuale
        </button>
      </div>

      {/* Tab Automatica */}
      {activeTab === 'automatica' && (
        <div style={pageStyle.card}>
          <div style={pageStyle.cardHeader}>
            <h2 style={pageStyle.cardTitle}>Riconciliazione Automatica</h2>
            <button 
              style={pageStyle.button('primary')}
              onClick={eseguiRiconciliazioneAutomatica}
              disabled={processing}
            >
              {processing ? '⏳ Elaborazione...' : '⚡ Avvia Riconciliazione'}
            </button>
          </div>
          <div style={{ padding: '40px', textAlign: 'center' }}>
            <p style={{ fontSize: '48px', marginBottom: '16px' }}>🤖</p>
            <h3 style={{ color: '#1e293b', marginBottom: '12px' }}>Riconciliazione Intelligente</h3>
            <p style={{ color: '#64748b', maxWidth: '500px', margin: '0 auto 24px' }}>
              Il sistema analizzerà automaticamente i movimenti dell'estratto conto e cercherà 
              corrispondenze con fatture, POS, versamenti e F24 importati.
            </p>
            <div style={{ 
              background: '#f8fafc', 
              borderRadius: '12px', 
              padding: '20px', 
              maxWidth: '400px', 
              margin: '0 auto',
              textAlign: 'left'
            }}>
              <p style={{ margin: '0 0 8px', fontSize: '13px', color: '#64748b' }}>
                <strong>Criteri di match:</strong>
              </p>
              <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: '#64748b' }}>
                <li>Fatture: numero + importo (±0.01€)</li>
                <li>POS: logica calendario (Lun-Gio: +1g, Ven-Dom: somma→Lun)</li>
                <li>Versamenti: data + importo esatto</li>
                <li>F24: importo esatto</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab Manuale */}
      {activeTab === 'manuale' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
          {/* Movimenti non riconciliati */}
          <div style={pageStyle.card}>
            <div style={pageStyle.cardHeader}>
              <h2 style={pageStyle.cardTitle}>Movimenti Estratto Conto</h2>
              <span style={{ fontSize: '12px', color: '#64748b' }}>
                {movimentiNonRiconciliati.length} non riconciliati
              </span>
            </div>
            <div style={{ maxHeight: '500px', overflow: 'auto' }}>
              <div style={{overflowX:'auto'}}>
              <table style={pageStyle.table}>
                <thead>
                  <tr>
                    <th style={pageStyle.th}>Data</th>
                    <th style={pageStyle.th}>Descrizione</th>
                    <th style={{ ...pageStyle.th, textAlign: 'right' }}>Importo</th>
                  </tr>
                </thead>
                <tbody>
                  {movimentiNonRiconciliati.slice(0, 50).map((mov) => (
                    <tr 
                      key={mov.id}
                      onClick={() => handleSelectMovimento(mov)}
                      style={{ 
                        cursor: 'pointer',
                        background: selectedMovimento?.id === mov.id ? '#eff6ff' : 'white'
                      }}
                    >
                      <td style={pageStyle.td}>{formatDate(mov.data)}</td>
                      <td style={{ ...pageStyle.td, maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {mov.descrizione || mov.descrizione_originale || '-'}
                      </td>
                      <td style={{ ...pageStyle.td, textAlign: 'right', fontWeight: '600', color: mov.importo < 0 ? '#dc2626' : '#16a34a' }}>
                        {formatEuro(mov.importo)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            </div>
          </div>

          {/* Fatture matching */}
          <div style={pageStyle.card}>
            <div style={pageStyle.cardHeader}>
              <h2 style={pageStyle.cardTitle}>
                {selectedMovimento ? 'Fatture Compatibili' : 'Seleziona un movimento'}
              </h2>
              {selectedMovimento && (
                <span style={pageStyle.badge('#3b82f6')}>
                  {formatEuro(Math.abs(selectedMovimento.importo))}
                </span>
              )}
            </div>
            {!selectedMovimento ? (
              <div style={pageStyle.emptyState}>
                <p>👈 Seleziona un movimento dall'elenco a sinistra</p>
              </div>
            ) : matchingFatture.length === 0 ? (
              <div style={pageStyle.emptyState}>
                <p>Nessuna fattura con importo simile trovata</p>
              </div>
            ) : (
              <div style={{ maxHeight: '500px', overflow: 'auto' }}>
                <div style={{overflowX:'auto'}}>
              <table style={pageStyle.table}>
                  <thead>
                    <tr>
                      <th style={pageStyle.th}>Fornitore</th>
                      <th style={pageStyle.th}>N. Fatt.</th>
                      <th style={{ ...pageStyle.th, textAlign: 'right' }}>Importo</th>
                      <th style={{ ...pageStyle.th, textAlign: 'center' }}>Azione</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matchingFatture.map((f) => (
                      <tr key={f._id || f.id}>
                        <td style={{ ...pageStyle.td, maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {f.supplier_name || f.cedente_denominazione || '-'}
                        </td>
                        <td style={pageStyle.td}>{f.invoice_number || f.numero_fattura || '-'}</td>
                        <td style={{ ...pageStyle.td, textAlign: 'right', fontWeight: '600' }}>
                          {formatEuro(f.total_amount || f.importo)}
                        </td>
                        <td style={{ ...pageStyle.td, textAlign: 'center' }}>
                          <div style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
                            <a
                              style={{ ...pageStyle.button('outline'), padding: '6px 10px', textDecoration: 'none' }}
                              href={`/api/fatture-ricevute/fattura/${f._id || f.id}/view-assoinvoice`}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="Visualizza fattura"
                            >
                              📄
                            </a>
                            <button
                              style={{ ...pageStyle.button('success'), padding: '6px 12px' }}
                              onClick={() => handleRiconciliaManuale(f)}
                              disabled={processing}
                            >
                              ✓ Riconcilia
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}

