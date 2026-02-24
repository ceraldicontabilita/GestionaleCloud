import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

/**
 * Ciclo Passivo Integrato
 * 
 * Pagina per la gestione completa del ciclo passivo:
 * 1. Import XML → Carico Magazzino → Prima Nota → Scadenziario
 * 2. Dashboard Riconciliazione con scadenze aperte/saldate
 * 3. Matching manuale tra scadenze e movimenti bancari
 * 4. Tracciabilità lotti
 */

const styles = {
  container: {
    padding: '24px',
    maxWidth: '1600px',
    margin: '0 auto',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  },
  header: {
    marginBottom: '24px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    gap: '16px'
  },
  title: {
    margin: 0,
    fontSize: '28px',
    fontWeight: 'bold',
    color: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    gap: '12px'
  },
  subtitle: {
    margin: '4px 0 0 0',
    color: '#64748b',
    fontSize: '14px'
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
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
    fontSize: '28px',
    fontWeight: 'bold',
    color: color,
    margin: 0
  }),
  statLabel: {
    fontSize: '13px',
    color: '#64748b',
    marginTop: '4px'
  },
  tabs: {
    display: 'flex',
    gap: '4px',
    marginBottom: '24px',
    background: '#f1f5f9',
    padding: '4px',
    borderRadius: '10px',
    width: 'fit-content',
    flexWrap: 'wrap'
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
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '12px'
  },
  cardTitle: {
    margin: 0,
    fontSize: '16px',
    fontWeight: '600',
    color: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    gap: '8px'
  },
  cardBody: {
    padding: '20px'
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
    padding: '10px 18px',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: '14px',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    transition: 'all 0.2s',
    ...(variant === 'primary' ? {
      background: '#1535a8',
      color: 'white'
    } : variant === 'success' ? {
      background: '#15803d',
      color: 'white'
    } : variant === 'danger' ? {
      background: '#ef4444',
      color: 'white'
    } : variant === 'warning' ? {
      background: '#d97706',
      color: 'white'
    } : {
      background: '#f1f5f9',
      color: '#475569',
      border: '1px solid #e2e8f0'
    })
  }),
  uploadZone: {
    border: '2px dashed #cbd5e1',
    borderRadius: '12px',
    padding: '40px 20px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s',
    background: '#f8fafc'
  },
  uploadZoneActive: {
    borderColor: '#1535a8',
    background: '#eff6ff'
  },
  input: {
    padding: '10px 14px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '14px',
    width: '100%',
    boxSizing: 'border-box'
  },
  select: {
    padding: '10px 14px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '14px',
    background: 'white',
    cursor: 'pointer'
  },
  splitView: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '24px'
  },
  emptyState: {
    textAlign: 'center',
    padding: '60px 20px',
    color: '#64748b'
  },
  rowHighlight: {
    background: '#fef3c7',
    cursor: 'pointer'
  },
  rowSelected: {
    background: '#dbeafe'
  },
  modalOverlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000
  },
  modal: {
    background: 'white',
    borderRadius: '16px',
    maxWidth: '600px',
    width: '90%',
    maxHeight: '80vh',
    overflow: 'auto'
  },
  modalHeader: {
    padding: '20px',
    borderBottom: '1px solid #e2e8f0',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  modalBody: {
    padding: '20px'
  },
  flexRow: {
    display: 'flex',
    gap: '12px',
    alignItems: 'center',
    flexWrap: 'wrap'
  }
};

export default function CicloPassivoIntegrato() {
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/ciclo-passivo\/([\w-]+)/);
    return match ? match[1] : 'import';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/ciclo-passivo/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);
  
  // Per riconciliazione manuale
  const [selectedScadenza, setSelectedScadenza] = useState(null);
  const [suggerimenti, setSuggerimenti] = useState([]);
  const [loadingSuggerimenti, setLoadingSuggerimenti] = useState(false);
  
  // Filtri anno/mese
  const { anno } = useAnnoGlobale(); // Anno dal contesto globale
  const [mese, setMese] = useState(null);

  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (anno) params.append('anno', anno);
      if (mese) params.append('mese', mese);
      
      const res = await api.get(`/api/ciclo-passivo/dashboard-riconciliazione?${params}`);
      setDashboard(res.data);
    } catch (e) {
      console.error('Errore caricamento dashboard:', e);
    } finally {
      setLoading(false);
    }
  }, [anno, mese]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    const files = e.dataTransfer?.files;
    if (files?.length > 0) {
      await uploadFiles(files);
    }
  };

  const handleFileSelect = async (e) => {
    const files = e.target.files;
    if (files?.length > 0) {
      await uploadFiles(files);
    }
  };

  const uploadFiles = async (files) => {
    setUploading(true);
    setUploadResult(null);
    
    try {
      const formData = new FormData();
      
      if (files.length === 1) {
        formData.append('file', files[0]);
        const res = await api.post('/api/ciclo-passivo/import-integrato', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        setUploadResult({ success: true, single: true, data: res.data });
      } else {
        for (let i = 0; i < files.length; i++) {
          formData.append('files', files[i]);
        }
        const res = await api.post('/api/ciclo-passivo/import-integrato-batch', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        setUploadResult({ success: true, single: false, data: res.data });
      }
      
      loadDashboard();
    } catch (e) {
      const errorDetail = e.response?.data?.detail;
      setUploadResult({ 
        success: false, 
        error: typeof errorDetail === 'object' ? errorDetail.message : (errorDetail || e.message)
      });
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const loadSuggerimentiMatch = async (scadenzaId) => {
    setLoadingSuggerimenti(true);
    try {
      const res = await api.get(`/api/ciclo-passivo/suggerimenti-match/${scadenzaId}`);
      setSuggerimenti(res.data.suggerimenti || []);
    } catch (e) {
      console.error('Errore caricamento suggerimenti:', e);
      setSuggerimenti([]);
    } finally {
      setLoadingSuggerimenti(false);
    }
  };

  const handleSelectScadenza = (scadenza) => {
    setSelectedScadenza(scadenza);
    loadSuggerimentiMatch(scadenza.id);
  };

  const handleMatchManuale = async (transazioneId) => {
    if (!selectedScadenza) return;
    
    setProcessing(true);
    try {
      await api.post(`/api/ciclo-passivo/match-manuale?scadenza_id=${selectedScadenza.id}&transazione_id=${transazioneId}`);
      alert('✅ Riconciliazione completata con successo!');
      setSelectedScadenza(null);
      setSuggerimenti([]);
      loadDashboard();
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

  const isScadenzaPassata = (dataScadenza) => {
    if (!dataScadenza) return false;
    try {
      return new Date(dataScadenza) < new Date();
    } catch { return false; }
  };

  const stats = dashboard?.statistiche || {};

  return (
    <PageLayout title="Ciclo Passivo Integrato" subtitle="Import XML → Magazzino → Prima Nota → Scadenziario → Riconciliazione">
    <div style={{...styles.container, padding: 0}} data-testid="ciclo-passivo-page">
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>
            <span>📋</span> Ciclo Passivo Integrato
          </h1>
          <p style={styles.subtitle}>
            Import XML → Magazzino → Prima Nota → Scadenziario → Riconciliazione
          </p>
        </div>
        <div style={styles.flexRow}>
          <div 
            style={{ ...styles.select, background: '#f1f5f9', color: '#64748b', fontWeight: 600 }}
            data-testid="anno-display"
          >
            {anno} <span style={{ fontSize: 10, opacity: 0.7 }}>(globale)</span>
          </div>
          <select 
            style={styles.select}
            value={mese || ''}
            onChange={(e) => setMese(e.target.value ? parseInt(e.target.value) : null)}
            data-testid="select-mese"
          >
            <option value="">Tutti i mesi</option>
            {['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'].map((m, i) => (
              <option key={i+1} value={i+1}>{m}</option>
            ))}
          </select>
          <button 
            style={styles.button('default')}
            onClick={loadDashboard}
            disabled={loading}
            data-testid="btn-refresh"
          >
            🔄 Aggiorna
          </button>
        </div>
      </div>

      {/* Stats */}
      <div style={styles.statsGrid}>
        <div style={styles.statCard('#ef4444')}>
          <p style={styles.statValue('#ef4444')}>{stats.num_scadenze_aperte || 0}</p>
          <p style={styles.statLabel}>Scadenze Aperte</p>
        </div>
        <div style={styles.statCard('#d97706')}>
          <p style={styles.statValue('#d97706')}>{formatEuro(stats.totale_debito_aperto || 0)}</p>
          <p style={styles.statLabel}>Debito Aperto</p>
        </div>
        <div style={styles.statCard('#15803d')}>
          <p style={styles.statValue('#15803d')}>{stats.num_scadenze_saldate || 0}</p>
          <p style={styles.statLabel}>Scadenze Saldate</p>
        </div>
        <div style={styles.statCard('#1535a8')}>
          <p style={styles.statValue('#1535a8')}>{formatEuro(stats.totale_pagato || 0)}</p>
          <p style={styles.statLabel}>Totale Pagato</p>
        </div>
        <div style={styles.statCard('#8b5cf6')}>
          <p style={styles.statValue('#8b5cf6')}>{stats.num_movimenti_da_riconciliare || 0}</p>
          <p style={styles.statLabel}>Movimenti da Riconciliare</p>
        </div>
      </div>

      {/* Tabs */}
      <div style={styles.tabs}>
        <button 
          style={styles.tab(activeTab === 'import')}
          onClick={() => handleTabChange('import')}
          data-testid="tab-import"
        >
          📤 Import XML
        </button>
        <button 
          style={styles.tab(activeTab === 'scadenze')}
          onClick={() => handleTabChange('scadenze')}
          data-testid="tab-scadenze"
        >
          📅 Scadenze Aperte
        </button>
        <button 
          style={styles.tab(activeTab === 'riconciliazione')}
          onClick={() => handleTabChange('riconciliazione')}
          data-testid="tab-riconciliazione"
        >
          🔄 Riconciliazione
        </button>
        <button 
          style={styles.tab(activeTab === 'storico')}
          onClick={() => handleTabChange('storico')}
          data-testid="tab-storico"
        >
          ✅ Storico Pagamenti
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'import' && (
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h3 style={styles.cardTitle}>
              <span>📄</span> Import Fatture XML Integrate
            </h3>
          </div>
          <div style={styles.cardBody}>
            <p style={{ marginBottom: '20px', color: '#64748b' }}>
              Carica file XML di fatture passive. Il sistema eseguirà automaticamente:
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
              <div style={{ padding: '16px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                <strong style={{ color: '#166534' }}>1. Magazzino</strong>
                <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: '#15803d' }}>
                  Carico merce e creazione lotti HACCP
                </p>
              </div>
              <div style={{ padding: '16px', background: '#eff6ff', borderRadius: '8px', border: '1px solid #bfdbfe' }}>
                <strong style={{ color: '#1535a8' }}>2. Prima Nota</strong>
                <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: '#1d4ed8' }}>
                  Scritture contabili Dare/Avere
                </p>
              </div>
              <div style={{ padding: '16px', background: '#fef3c7', borderRadius: '8px', border: '1px solid #fde68a' }}>
                <strong style={{ color: '#92400e' }}>3. Scadenziario</strong>
                <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: '#b45309' }}>
                  Scadenze di pagamento
                </p>
              </div>
              <div style={{ padding: '16px', background: '#fce7f3', borderRadius: '8px', border: '1px solid #fbcfe8' }}>
                <strong style={{ color: '#9d174d' }}>4. Riconciliazione</strong>
                <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: '#be185d' }}>
                  Match automatico con banca
                </p>
              </div>
            </div>

            <div 
              style={{
                ...styles.uploadZone,
                ...(dragActive ? styles.uploadZoneActive : {})
              }}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              data-testid="upload-zone"
            >
              <input 
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                accept=".xml"
                multiple
                style={{ display: 'none' }}
                data-testid="file-input"
              />
              {uploading ? (
                <div>
                  <div style={{ fontSize: '48px', marginBottom: '16px' }}>⏳</div>
                  <p style={{ fontSize: '18px', color: '#1535a8', fontWeight: '500' }}>
                    Elaborazione in corso...
                  </p>
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: '48px', marginBottom: '16px' }}>📁</div>
                  <p style={{ fontSize: '18px', color: '#1e293b', fontWeight: '500' }}>
                    Trascina qui i file XML o clicca per selezionare
                  </p>
                  <p style={{ color: '#64748b', marginTop: '8px' }}>
                    Supporta file singoli o multipli
                  </p>
                </div>
              )}
            </div>

            {/* Upload Result */}
            {uploadResult && (
              <div style={{ 
                marginTop: '24px', 
                padding: '20px', 
                borderRadius: '12px',
                background: uploadResult.success ? '#f0fdf4' : '#fef2f2',
                border: `1px solid ${uploadResult.success ? '#bbf7d0' : '#fecaca'}`
              }}>
                {uploadResult.success ? (
                  uploadResult.single ? (
                    <div>
                      <h4 style={{ margin: '0 0 16px 0', color: '#166534' }}>
                        ✅ Fattura importata con successo!
                      </h4>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', fontSize: '14px' }}>
                        <div><strong>Numero:</strong> {uploadResult.data.numero_documento}</div>
                        <div><strong>Fornitore:</strong> {uploadResult.data.fornitore}</div>
                        <div><strong>Importo:</strong> {formatEuro(uploadResult.data.importo_totale)}</div>
                        <div><strong>Fornitore nuovo:</strong> {uploadResult.data.fornitore_nuovo ? 'Sì' : 'No'}</div>
                      </div>
                      {uploadResult.data.magazzino && (
                        <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #bbf7d0' }}>
                          <strong>Magazzino:</strong> {uploadResult.data.magazzino.movimenti_creati} movimenti, {uploadResult.data.magazzino.lotti_creati} lotti
                        </div>
                      )}
                      {uploadResult.data.prima_nota && (
                        <div style={{ marginTop: '8px' }}>
                          <strong>Prima Nota:</strong> {uploadResult.data.prima_nota.status === 'ok' ? '✅ Scrittura generata' : '⚠️ ' + uploadResult.data.prima_nota.error}
                        </div>
                      )}
                      {uploadResult.data.scadenziario && (
                        <div style={{ marginTop: '8px' }}>
                          <strong>Scadenziario:</strong> {uploadResult.data.scadenziario.status === 'ok' ? '✅ Scadenza creata' : '⚠️ ' + uploadResult.data.scadenziario.error}
                        </div>
                      )}
                      {uploadResult.data.riconciliazione && (
                        <div style={{ marginTop: '8px' }}>
                          <strong>Riconciliazione:</strong> {uploadResult.data.riconciliazione.automatica ? '✅ Match automatico trovato!' : '⏳ Da riconciliare manualmente'}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <h4 style={{ margin: '0 0 16px 0', color: '#166534' }}>
                        ✅ Import completato: {uploadResult.data.importate}/{uploadResult.data.totale} fatture
                      </h4>
                      {uploadResult.data.errori > 0 && (
                        <p style={{ color: '#ef4444' }}>⚠️ {uploadResult.data.errori} errori</p>
                      )}
                    </div>
                  )
                ) : (
                  <div>
                    <h4 style={{ margin: '0 0 8px 0', color: '#dc2626' }}>
                      ❌ Errore durante import
                    </h4>
                    <p style={{ color: '#b91c1c' }}>{uploadResult.error}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'scadenze' && (
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h3 style={styles.cardTitle}>
              <span>📅</span> Scadenze di Pagamento Aperte
            </h3>
            <span style={styles.badge('#ef4444')}>
              {dashboard?.scadenze_aperte?.length || 0} scadenze
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            {loading ? (
              <div style={styles.emptyState}>Caricamento...</div>
            ) : dashboard?.scadenze_aperte?.length > 0 ? (
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Scadenza</th>
                    <th style={styles.th}>Fornitore</th>
                    <th style={styles.th}>N. Fattura</th>
                    <th style={styles.th}>Importo</th>
                    <th style={styles.th}>Metodo</th>
                    <th style={styles.th}>Stato</th>
                    <th style={styles.th}>Azioni</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.scadenze_aperte.map((s) => (
                    <tr 
                      key={s.id}
                      style={isScadenzaPassata(s.data_scadenza) ? styles.rowHighlight : {}}
                    >
                      <td style={styles.td}>
                        <strong>{formatDate(s.data_scadenza)}</strong>
                        {isScadenzaPassata(s.data_scadenza) && (
                          <span style={{ ...styles.badge('#ef4444'), marginLeft: '8px' }}>Scaduta</span>
                        )}
                      </td>
                      <td style={styles.td}>{s.fornitore_nome}</td>
                      <td style={styles.td}>{s.numero_fattura}</td>
                      <td style={styles.td}>
                        <strong style={{ color: '#dc2626' }}>{formatEuro(s.importo_totale)}</strong>
                      </td>
                      <td style={styles.td}>
                        <span style={styles.badge('#1535a8')}>{s.metodo_descrizione || s.metodo_pagamento}</span>
                      </td>
                      <td style={styles.td}>
                        <span style={styles.badge('#d97706')}>Da pagare</span>
                      </td>
                      <td style={styles.td}>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          {s.fattura_id && (
                            <a 
                              style={{ ...styles.button('secondary'), padding: '6px 10px', textDecoration: 'none' }}
                              href={`/api/fatture-ricevute/fattura/${s.fattura_id}/view-assoinvoice`}
                              target="_blank"
                              rel="noopener noreferrer"
                              data-testid={`btn-pdf-${s.id}`}
                              title="Visualizza fattura"
                            >
                              📄
                            </a>
                          )}
                          <button 
                            style={styles.button('primary')}
                            onClick={() => {
                              setActiveTab('riconciliazione');
                              handleSelectScadenza(s);
                            }}
                            data-testid={`btn-riconcilia-${s.id}`}
                          >
                            🔗 Riconcilia
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={styles.emptyState}>
                <div style={{ fontSize: '48px', marginBottom: '16px' }}>🎉</div>
                <p>Nessuna scadenza aperta</p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'riconciliazione' && (
        <div style={styles.splitView}>
          {/* Colonna Sinistra: Scadenze */}
          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <h3 style={styles.cardTitle}>
                <span>📋</span> Scadenze da Riconciliare
              </h3>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: '600px' }}>
              {loading ? (
                <div style={styles.emptyState}>Caricamento...</div>
              ) : dashboard?.scadenze_aperte?.length > 0 ? (
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Scadenza</th>
                      <th style={styles.th}>Fornitore</th>
                      <th style={styles.th}>Importo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.scadenze_aperte.map((s) => (
                      <tr 
                        key={s.id}
                        style={{
                          ...styles.td,
                          cursor: 'pointer',
                          ...(selectedScadenza?.id === s.id ? styles.rowSelected : {}),
                          ...(isScadenzaPassata(s.data_scadenza) && selectedScadenza?.id !== s.id ? { background: '#fef3c7' } : {})
                        }}
                        onClick={() => handleSelectScadenza(s)}
                        data-testid={`scadenza-row-${s.id}`}
                      >
                        <td style={styles.td}>
                          <strong>{formatDate(s.data_scadenza)}</strong>
                          <br />
                          <span style={{ fontSize: '12px', color: '#64748b' }}>{s.numero_fattura}</span>
                        </td>
                        <td style={styles.td}>{s.fornitore_nome}</td>
                        <td style={styles.td}>
                          <strong style={{ color: '#dc2626' }}>{formatEuro(s.importo_totale)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={styles.emptyState}>
                  <p>Nessuna scadenza da riconciliare</p>
                </div>
              )}
            </div>
          </div>

          {/* Colonna Destra: Movimenti Bancari Suggeriti */}
          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <h3 style={styles.cardTitle}>
                <span>🏦</span> Movimenti Bancari Suggeriti
              </h3>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: '600px' }}>
              {selectedScadenza ? (
                <>
                  <div style={{ padding: '16px', background: '#eff6ff', borderBottom: '1px solid #e2e8f0' }}>
                    <strong>Scadenza selezionata:</strong> {selectedScadenza.fornitore_nome} - {formatEuro(selectedScadenza.importo_totale)}
                    <br />
                    <span style={{ fontSize: '13px', color: '#64748b' }}>Fatt. {selectedScadenza.numero_fattura} - Scade {formatDate(selectedScadenza.data_scadenza)}</span>
                  </div>
                  {loadingSuggerimenti ? (
                    <div style={styles.emptyState}>Ricerca movimenti...</div>
                  ) : suggerimenti.length > 0 ? (
                    <table style={styles.table}>
                      <thead>
                        <tr>
                          <th style={styles.th}>Data</th>
                          <th style={styles.th}>Descrizione</th>
                          <th style={styles.th}>Importo</th>
                          <th style={styles.th}>Match</th>
                          <th style={styles.th}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {suggerimenti.map((m) => (
                          <tr key={m.id}>
                            <td style={styles.td}>{formatDate(m.data)}</td>
                            <td style={styles.td}>
                              <span style={{ fontSize: '13px' }}>{m.descrizione || m.causale || '-'}</span>
                            </td>
                            <td style={styles.td}>
                              <strong>{formatEuro(m.importo)}</strong>
                              {m.diff_importo > 0 && (
                                <span style={{ fontSize: '11px', color: '#d97706', display: 'block' }}>
                                  Diff: {formatEuro(m.diff_importo)}
                                </span>
                              )}
                            </td>
                            <td style={styles.td}>
                              <span style={styles.badge(m.match_score < 50 ? '#15803d' : m.match_score < 200 ? '#d97706' : '#ef4444')}>
                                {m.match_score < 50 ? '⭐ Ottimo' : m.match_score < 200 ? '🔸 Buono' : '⚠️ Incerto'}
                              </span>
                            </td>
                            <td style={styles.td}>
                              <button 
                                style={styles.button('success')}
                                onClick={() => handleMatchManuale(m.id)}
                                disabled={processing}
                                data-testid={`btn-match-${m.id}`}
                              >
                                ✓ Match
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div style={styles.emptyState}>
                      <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔍</div>
                      <p>Nessun movimento bancario compatibile trovato</p>
                      <p style={{ fontSize: '13px', marginTop: '8px' }}>
                        Verifica che i movimenti bancari siano stati importati
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <div style={styles.emptyState}>
                  <div style={{ fontSize: '48px', marginBottom: '16px' }}>👈</div>
                  <p>Seleziona una scadenza dalla lista a sinistra</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'storico' && (
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h3 style={styles.cardTitle}>
              <span>✅</span> Storico Pagamenti Effettuati
            </h3>
            <span style={styles.badge('#15803d')}>
              {dashboard?.scadenze_saldate?.length || 0} pagamenti
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            {loading ? (
              <div style={styles.emptyState}>Caricamento...</div>
            ) : dashboard?.scadenze_saldate?.length > 0 ? (
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Data Pagamento</th>
                    <th style={styles.th}>Fornitore</th>
                    <th style={styles.th}>N. Fattura</th>
                    <th style={styles.th}>Importo</th>
                    <th style={styles.th}>Metodo</th>
                    <th style={styles.th}>Riconciliato</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.scadenze_saldate.map((s) => (
                    <tr key={s.id}>
                      <td style={styles.td}>{formatDate(s.data_pagamento)}</td>
                      <td style={styles.td}>{s.fornitore_nome}</td>
                      <td style={styles.td}>{s.numero_fattura}</td>
                      <td style={styles.td}>
                        <strong style={{ color: '#15803d' }}>{formatEuro(s.importo_totale)}</strong>
                      </td>
                      <td style={styles.td}>
                        <span style={styles.badge('#1535a8')}>{s.metodo_descrizione || s.metodo_pagamento}</span>
                      </td>
                      <td style={styles.td}>
                        {s.riconciliato ? (
                          <span style={styles.badge('#15803d')}>✓ Sì</span>
                        ) : (
                          <span style={styles.badge('#d97706')}>Manuale</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={styles.emptyState}>
                <div style={{ fontSize: '48px', marginBottom: '16px' }}>📭</div>
                <p>Nessun pagamento registrato</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}
