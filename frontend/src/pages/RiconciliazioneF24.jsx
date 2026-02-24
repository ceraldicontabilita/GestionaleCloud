import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Eye, Edit, X, Trash2 } from 'lucide-react';
import { PageLayout } from '../components/PageLayout';

/**
 * Riconciliazione F24
 * Gestione F24 commercialista → Quietanza → Riconciliazione
 * Include: upload multiplo, visualizzazione PDF, modifica, riconciliazione automatica
 */
export default function RiconciliazioneF24() {
  const { anno } = useAnnoGlobale();
  const [dashboard, setDashboard] = useState(null);
  const [f24List, setF24List] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [filterStatus, setFilterStatus] = useState('da_pagare');
  
  // Espansione righe per vedere tributi
  const [expandedRows, setExpandedRows] = useState(new Set());
  
  // Modali
  const [showModal, setShowModal] = useState(null);
  const [modalData, setModalData] = useState([]);
  const [quietanzeList, setQuietanzeList] = useState([]);
  
  // Visualizzatore PDF
  const [viewingPdf, setViewingPdf] = useState(null);
  
  // Modifica F24
  const [editingF24, setEditingF24] = useState(null);

  const loadDashboard = useCallback(async () => {
    try {
      const response = await api.get(`/api/f24-riconciliazione/dashboard?anno=${anno}`);
      setDashboard(response.data);
    } catch (err) {
      console.error('Errore caricamento dashboard:', err);
    }
  }, [anno]);

  const loadF24List = useCallback(async () => {
    try {
      const response = await api.get(`/api/f24-riconciliazione/commercialista?status=${filterStatus}&anno=${anno}`);
      setF24List(response.data.f24_list || []);
    } catch (err) {
      console.error('Errore caricamento F24:', err);
    }
  }, [filterStatus, anno]);

  const loadAlerts = useCallback(async () => {
    try {
      const response = await api.get(`/api/f24-riconciliazione/alerts?status=pending&anno=${anno}`);
      setAlerts(response.data.alerts || []);
    } catch (err) {
      console.error('Errore caricamento alerts:', err);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadDashboard(), loadF24List(), loadAlerts()]);
  }, [loadDashboard, loadF24List, loadAlerts]);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await refreshAll();
      setLoading(false);
    };
    loadAll();
  }, [refreshAll]);

  // Upload multiplo F24
  const handleUploadF24 = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    let successCount = 0;
    let errorCount = 0;
    let duplicateCount = 0;
    
    for (let i = 0; i < files.length; i++) {
      try {
        const formData = new FormData();
        formData.append('file', files[i]);
        const response = await api.post('/api/f24-riconciliazione/commercialista/upload', formData);
        if (response.data.success === false) {
          duplicateCount++;
        } else {
          successCount++;
        }
      } catch (err) {
        console.error(`Errore upload ${files[i].name}:`, err);
        errorCount++;
      }
    }
    
    let msg = `✅ Caricati: ${successCount}`;
    if (duplicateCount > 0) msg += `\n⚠️ Già presenti: ${duplicateCount}`;
    if (errorCount > 0) msg += `\n❌ Errori: ${errorCount}`;
    alert(msg);
    
    await refreshAll();
    setUploading(false);
    e.target.value = '';
  };

  // Upload multiplo Quietanze
  const handleUploadQuietanza = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      const formData = new FormData();
      for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
      }
      
      const response = await api.post('/api/f24-riconciliazione/quietanze/upload-multiplo', formData);
      const data = response.data;
      
      let message = `✅ Caricati: ${data.totale_caricati}\n`;
      message += `🔗 Matchati con F24: ${data.totale_matchati}\n`;
      if (data.totale_senza_match > 0) {
        message += `⚠️ Senza match: ${data.totale_senza_match}`;
      }
      
      alert(message);
    } catch (err) {
      alert(`❌ Errore: ${err.response?.data?.detail || err.message}`);
    }
    await refreshAll();
    setUploading(false);
    e.target.value = '';
  };

  // Riconcilia - riassocia F24 a Quietanze
  const handleRiconcilia = async () => {
    
    
    setUploading(true);
    try {
      const response = await api.post('/api/f24-riconciliazione/riconcilia-tutto');
      const data = response.data;
      alert(`✅ Riconciliazione completata!\n${data.f24_riconciliati || 0} F24 riconciliati\n${data.nuovi_match || 0} nuovi match trovati`);
    } catch (err) {
      console.error('Errore riconciliazione:', err);
      alert(`❌ Errore: ${err.response?.data?.detail || err.message}`);
    }
    await refreshAll();
    setUploading(false);
  };

  // Segna come pagato manualmente
  const handleMarkAsPaid = async (f24Id) => {
    
    try {
      await api.put(`/api/f24-riconciliazione/commercialista/${f24Id}/pagato`);
      await refreshAll();
    } catch (err) {
      alert(`❌ Errore: ${err.response?.data?.detail || err.message}`);
    }
  };

  const handleDeleteF24 = async (id) => {
    
    try {
      await api.delete(`/api/f24-riconciliazione/commercialista/${id}`);
      await refreshAll();
    } catch (err) {
      alert(`❌ Errore: ${err.response?.data?.detail || err.message}`);
    }
  };

  // Visualizza PDF
  const handleViewPdf = (f24) => {
    if (f24.file_path) {
      const pdfUrl = `${api.defaults.baseURL}/api/f24-riconciliazione/commercialista/${f24.id}/pdf`;
      setViewingPdf({ url: pdfUrl, name: f24.file_name || 'F24.pdf', f24 });
    } else {
      alert('PDF non disponibile per questo F24');
    }
  };

  // Aggiorna F24
  const handleUpdateF24 = async (f24Id, updates) => {
    try {
      await api.put(`/api/f24-riconciliazione/commercialista/${f24Id}`, updates);
      setEditingF24(null);
      await refreshAll();
    } catch (err) {
      alert(`❌ Errore: ${err.response?.data?.detail || err.message}`);
    }
  };

  // Toggle espansione riga
  const toggleRow = (id) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedRows(newExpanded);
  };

  // Carica dettagli per modale
  const openModal = async (type) => {
    try {
      if (type === 'da_pagare') {
        const response = await api.get(`/api/f24-riconciliazione/commercialista?status=da_pagare&anno=${anno}`);
        setModalData(response.data.f24_list || []);
      } else if (type === 'pagati') {
        const [f24Response, quietanzeResponse] = await Promise.all([
          api.get(`/api/f24-riconciliazione/commercialista?status=pagato&anno=${anno}`),
          api.get('/api/f24-riconciliazione/quietanze')
        ]);
        setModalData(f24Response.data.f24_list || []);
        setQuietanzeList(quietanzeResponse.data.quietanze || []);
      } else if (type === 'quietanze') {
        const response = await api.get('/api/f24-riconciliazione/quietanze');
        setModalData(response.data.quietanze || []);
      } else if (type === 'alert') {
        const response = await api.get(`/api/f24-riconciliazione/alerts?status=pending&anno=${anno}`);
        setModalData(response.data.alerts || []);
      }
      setShowModal(type);
    } catch (err) {
      console.error('Errore caricamento dettagli:', err);
    }
  };

  // Render dettagli tributi (espandibile)
  const renderTributiDetails = (f24) => {
    const sections = [];
    
    if (f24.sezione_erario?.length > 0) {
      sections.push(
        <div key="erario" style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#1535a8', marginBottom: 6 }}>💰 SEZIONE ERARIO</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#dbeafe' }}>
                <th style={{ padding: 6, textAlign: 'left' }}>Codice</th>
                <th style={{ padding: 6, textAlign: 'left' }}>Descrizione</th>
                <th style={{ padding: 6, textAlign: 'left' }}>Periodo</th>
                <th style={{ padding: 6, textAlign: 'right' }}>Debito</th>
                <th style={{ padding: 6, textAlign: 'right' }}>Credito</th>
              </tr>
            </thead>
            <tbody>
              {f24.sezione_erario.map((t, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 6, fontFamily: 'monospace', fontWeight: 600 }}>{t.codice_tributo}</td>
                  <td style={{ padding: 6 }}>{t.descrizione || '-'}</td>
                  <td style={{ padding: 6 }}>{t.periodo_riferimento || t.anno || '-'}</td>
                  <td style={{ padding: 6, textAlign: 'right', color: '#dc2626' }}>{formatEuro(t.importo_debito || 0)}</td>
                  <td style={{ padding: 6, textAlign: 'right', color: '#16a34a' }}>{formatEuro(t.importo_credito || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    
    if (f24.sezione_inps?.length > 0) {
      sections.push(
        <div key="inps" style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#065f46', marginBottom: 6 }}>🏛️ SEZIONE INPS</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#dcfce7' }}>
                <th style={{ padding: 6, textAlign: 'left' }}>Causale</th>
                <th style={{ padding: 6, textAlign: 'left' }}>Matricola</th>
                <th style={{ padding: 6, textAlign: 'left' }}>Periodo</th>
                <th style={{ padding: 6, textAlign: 'right' }}>Debito</th>
              </tr>
            </thead>
            <tbody>
              {f24.sezione_inps.map((t, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 6, fontFamily: 'monospace', fontWeight: 600 }}>{t.causale}</td>
                  <td style={{ padding: 6 }}>{t.matricola || '-'}</td>
                  <td style={{ padding: 6 }}>{t.periodo_riferimento || '-'}</td>
                  <td style={{ padding: 6, textAlign: 'right', color: '#dc2626' }}>{formatEuro(t.importo_debito || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    
    if (f24.sezione_regioni?.length > 0) {
      sections.push(
        <div key="regioni" style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#92400e', marginBottom: 6 }}>🗺️ SEZIONE REGIONI</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#fef3c7' }}>
                <th style={{ padding: 6, textAlign: 'left' }}>Codice</th>
                <th style={{ padding: 6, textAlign: 'left' }}>Regione</th>
                <th style={{ padding: 6, textAlign: 'right' }}>Debito</th>
              </tr>
            </thead>
            <tbody>
              {f24.sezione_regioni.map((t, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 6, fontFamily: 'monospace', fontWeight: 600 }}>{t.codice_tributo}</td>
                  <td style={{ padding: 6 }}>{t.codice_regione || '-'}</td>
                  <td style={{ padding: 6, textAlign: 'right', color: '#dc2626' }}>{formatEuro(t.importo_debito || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    
    if (f24.sezione_tributi_locali?.length > 0) {
      sections.push(
        <div key="locali" style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#7c3aed', marginBottom: 6 }}>🏠 TRIBUTI LOCALI/IMU</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f3e8ff' }}>
                <th style={{ padding: 6, textAlign: 'left' }}>Codice</th>
                <th style={{ padding: 6, textAlign: 'left' }}>Comune</th>
                <th style={{ padding: 6, textAlign: 'right' }}>Debito</th>
              </tr>
            </thead>
            <tbody>
              {f24.sezione_tributi_locali.map((t, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 6, fontFamily: 'monospace', fontWeight: 600 }}>{t.codice_tributo}</td>
                  <td style={{ padding: 6 }}>{t.codice_comune || '-'}</td>
                  <td style={{ padding: 6, textAlign: 'right', color: '#dc2626' }}>{formatEuro(t.importo_debito || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    
    return sections.length > 0 ? sections : <div style={{ color: '#9ca3af', fontStyle: 'italic' }}>Nessun tributo estratto</div>;
  };

  // Card Component cliccabile
  const SummaryCard = ({ title, value, subtitle, color, icon, highlight, onClick }) => (
    <div 
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      style={{
        background: highlight ? `linear-gradient(135deg, ${color} 0%, ${color}dd 100%)` : 'white',
        borderRadius: 12,
        padding: 16,
        boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
        border: highlight ? 'none' : '1px solid #e5e7eb',
        color: highlight ? 'white' : 'inherit',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'transform 0.15s, box-shadow 0.15s',
        userSelect: 'none',
      }}
      onMouseEnter={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
        }
      }}
      onMouseLeave={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.05)';
        }
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, pointerEvents: 'none' }}>
        <span style={{ fontSize: 20 }}>{icon}</span>
        <span style={{ fontSize: 12, color: highlight ? 'rgba(255,255,255,0.8)' : '#6b7280', textTransform: 'uppercase', fontWeight: 500 }}>
          {title}
        </span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: highlight ? 'white' : color, pointerEvents: 'none' }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: highlight ? 'rgba(255,255,255,0.7)' : '#9ca3af', marginTop: 2, pointerEvents: 'none' }}>
        {subtitle}
      </div>
    </div>
  );

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)', padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
          <div style={{ color: '#6b7280' }}>Caricamento...</div>
        </div>
      </div>
    );
  }

  return (
    <PageLayout title="Riconciliazione F24" subtitle="F24 Commercialista → Quietanza → Riconciliazione Banca">
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)' }}>
      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>📋</span> Riconciliazione F24
          </h1>
          <p style={{ margin: '4px 0 0 0', color: '#6b7280', fontSize: 14 }}>
            F24 Commercialista → Quietanza → Riconciliazione Banca
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button
            onClick={handleRiconcilia}
            disabled={uploading}
            style={{ padding: '8px 16px', background: '#8b5cf6', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, fontWeight: 500, opacity: uploading ? 0.6 : 1 }}
          >
            🔄 Riconcilia
          </button>
          <label style={{ cursor: uploading ? 'not-allowed' : 'pointer' }}>
            <input type="file" accept=".pdf" multiple style={{ display: 'none' }} onChange={handleUploadF24} disabled={uploading} />
            <span style={{ padding: '8px 16px', background: '#1535a8', color: 'white', borderRadius: 8, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14, fontWeight: 500, opacity: uploading ? 0.6 : 1 }}>
              {uploading ? '⏳' : '📤'} Carica F24
            </span>
          </label>
          <label style={{ cursor: uploading ? 'not-allowed' : 'pointer' }}>
            <input type="file" accept=".pdf" multiple style={{ display: 'none' }} onChange={handleUploadQuietanza} disabled={uploading} />
            <span style={{ padding: '8px 16px', background: '#15803d', color: 'white', borderRadius: 8, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14, fontWeight: 500, opacity: uploading ? 0.6 : 1 }}>
              📄 Carica Quietanze
            </span>
          </label>
        </div>
      </div>

      {/* Summary Cards - TUTTE CLICCABILI */}
      {dashboard && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
          <SummaryCard
            title="F24 Da Pagare"
            value={dashboard.f24_commercialista?.da_pagare || 0}
            subtitle={formatEuro(dashboard.totale_da_pagare)}
            color="#f97316"
            icon="⏰"
            onClick={() => openModal('da_pagare')}
          />
          <SummaryCard
            title="F24 Pagati"
            value={dashboard.f24_commercialista?.pagato || 0}
            subtitle="Clicca per dettagli"
            color="#15803d"
            icon="✅"
            onClick={() => openModal('pagati')}
          />
          <SummaryCard
            title="Quietanze"
            value={dashboard.quietanze_caricate || 0}
            subtitle={formatEuro(dashboard.totale_pagato_quietanze)}
            color="#1535a8"
            icon="📄"
            onClick={() => openModal('quietanze')}
          />
          <SummaryCard
            title="Alert"
            value={dashboard.alerts_pendenti || 0}
            subtitle="Da gestire"
            color={dashboard.alerts_pendenti > 0 ? '#ef4444' : '#6b7280'}
            icon="⚠️"
            highlight={dashboard.alerts_pendenti > 0}
            onClick={() => openModal('alert')}
          />
        </div>
      )}

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: 4, background: '#f3f4f6', padding: 4, borderRadius: 8, marginBottom: 16, width: 'fit-content' }}>
        {[
          { key: 'da_pagare', label: 'Da Pagare', icon: '⏰' },
          { key: 'pagato', label: 'Pagati', icon: '✅' },
          { key: 'eliminato', label: 'Eliminati', icon: '🗑️' }
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => { setFilterStatus(tab.key); setExpandedRows(new Set()); }}
            style={{
              padding: '8px 16px',
              background: filterStatus === tab.key ? 'white' : 'transparent',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
              fontWeight: filterStatus === tab.key ? 600 : 400,
              color: filterStatus === tab.key ? '#1535a8' : '#6b7280',
              boxShadow: filterStatus === tab.key ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <span>{tab.icon}</span> {tab.label}
          </button>
        ))}
      </div>

      {/* F24 List con righe espandibili */}
      <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
          <strong>Lista F24 ({f24List.length})</strong>
          <span style={{ marginLeft: 8, fontSize: 12, color: '#6b7280' }}>Clicca su una riga per vedere i tributi</span>
        </div>
        
        {f24List.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.5 }}>📭</div>
            <div>Nessun F24 trovato</div>
          </div>
        ) : (
          <div>
            {f24List.map((f24) => (
              <div key={f24.id}>
                {/* Riga principale cliccabile */}
                <div 
                  onClick={() => toggleRow(f24.id)}
                  style={{ 
                    display: 'grid', 
                    gridTemplateColumns: '1fr auto auto auto auto', 
                    gap: 16, 
                    padding: '12px 20px', 
                    borderBottom: '1px solid #f3f4f6',
                    cursor: 'pointer',
                    background: expandedRows.has(f24.id) ? '#f8fafc' : 'white',
                    transition: 'background 0.15s',
                    alignItems: 'center'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                  onMouseLeave={(e) => e.currentTarget.style.background = expandedRows.has(f24.id) ? '#f8fafc' : 'white'}
                >
                  {/* File info */}
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ transform: expandedRows.has(f24.id) ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>▶</span>
                      <div>
                        <div style={{ fontWeight: 500 }}>{f24.file_name || 'F24'}</div>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>
                          Scadenza: {formatDateIT(f24.dati_generali?.data_versamento) || '-'}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Tributi badges */}
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {(f24.sezione_erario?.length || 0) > 0 && (
                      <span style={{ padding: '2px 6px', background: '#dbeafe', color: '#1535a8', borderRadius: 4, fontSize: 11 }}>
                        ERARIO: {f24.sezione_erario.length}
                      </span>
                    )}
                    {(f24.sezione_inps?.length || 0) > 0 && (
                      <span style={{ padding: '2px 6px', background: '#dcfce7', color: '#166534', borderRadius: 4, fontSize: 11 }}>
                        INPS: {f24.sezione_inps.length}
                      </span>
                    )}
                    {(f24.sezione_regioni?.length || 0) > 0 && (
                      <span style={{ padding: '2px 6px', background: '#fef3c7', color: '#92400e', borderRadius: 4, fontSize: 11 }}>
                        REGIONI: {f24.sezione_regioni.length}
                      </span>
                    )}
                  </div>

                  {/* Importo */}
                  <div style={{ fontWeight: 600, fontSize: 16, textAlign: 'right' }}>
                    {formatEuro(f24.totali?.saldo_netto || 0)}
                  </div>

                  {/* Stato */}
                  <span style={{
                    padding: '4px 10px',
                    borderRadius: 9999,
                    fontSize: 11,
                    fontWeight: 600,
                    background: f24.status === 'pagato' ? '#d1fae5' : f24.status === 'eliminato' ? '#fee2e2' : '#fef3c7',
                    color: f24.status === 'pagato' ? '#065f46' : f24.status === 'eliminato' ? '#991b1b' : '#92400e'
                  }}>
                    {f24.status === 'pagato' ? '✅ Pagato' : f24.status === 'eliminato' ? '🗑️ Eliminato' : '⏰ Da Pagare'}
                  </span>

                  {/* Azioni */}
                  <div style={{ display: 'flex', gap: 6 }} onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => handleViewPdf(f24)}
                      style={{ padding: '6px 10px', background: '#8b5cf6', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}
                      title="Visualizza PDF"
                    >
                      <Eye size={12} /> PDF
                    </button>
                    {f24.status === 'da_pagare' && (
                      <button
                        onClick={() => handleMarkAsPaid(f24.id)}
                        style={{ padding: '6px 10px', background: '#15803d', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
                        title="Segna come pagato"
                      >
                        ✅
                      </button>
                    )}
                    <button
                      onClick={() => setEditingF24(f24)}
                      style={{ padding: '6px 10px', background: '#1535a8', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}
                      title="Modifica"
                    >
                      <Edit size={12} />
                    </button>
                    <button
                      onClick={() => handleDeleteF24(f24.id)}
                      style={{ padding: '6px 10px', background: '#ef4444', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}
                      title="Elimina"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>

                {/* Dettagli tributi espandibili */}
                {expandedRows.has(f24.id) && (
                  <div style={{ padding: '16px 20px 16px 48px', background: '#f8fafc', borderBottom: '1px solid #e5e7eb' }}>
                    {renderTributiDetails(f24)}
                    
                    {/* Se pagato, mostra associazione quietanza */}
                    {f24.status === 'pagato' && f24.quietanza_id && (
                      <div style={{ marginTop: 12, padding: 12, background: '#d1fae5', borderRadius: 8 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#065f46', marginBottom: 4 }}>📄 QUIETANZA ASSOCIATA</div>
                        <div style={{ fontSize: 12 }}>
                          Protocollo: <span style={{ fontFamily: 'monospace' }}>{f24.protocollo_quietanza || '-'}</span>
                        </div>
                        {f24.differenza_importo && Math.abs(f24.differenza_importo) > 0.01 && (
                          <div style={{ fontSize: 12, color: '#92400e', marginTop: 4 }}>
                            ⚠️ Differenza: {formatEuro(f24.differenza_importo)}
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

      {/* Info Box */}
      <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 12, padding: 16, marginTop: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span>ℹ️</span>
          <strong style={{ color: '#1535a8' }}>Come funziona</strong>
        </div>
        <ol style={{ margin: 0, paddingLeft: 20, color: '#1535a8', fontSize: 13 }}>
          <li><strong>Carica F24:</strong> Carica i PDF dalla commercialista (anche multipli)</li>
          <li><strong>Carica Quietanze:</strong> Carica le quietanze dall&apos;Agenzia delle Entrate</li>
          <li><strong>Riconcilia:</strong> Associa automaticamente F24 e Quietanze per importo</li>
          <li><strong>Clicca sulla riga:</strong> Per vedere i dettagli dei tributi</li>
        </ol>
      </div>

      {/* MODAL DETTAGLI */}
      {showModal && (
        <div style={{ 
          position: 'fixed', 
          top: 0, 
          left: 0, 
          right: 0, 
          bottom: 0, 
          background: 'rgba(0,0,0,0.5)', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          zIndex: 1000 
        }} onClick={() => setShowModal(null)}>
          <div style={{ 
            background: 'white', 
            borderRadius: 16, 
            padding: 24, 
            maxWidth: 950, 
            width: '95%', 
            maxHeight: '85vh', 
            overflow: 'auto' 
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 20 }}>
                {showModal === 'da_pagare' && '⏰ F24 Da Pagare'}
                {showModal === 'pagati' && '✅ F24 Pagati - Associazioni'}
                {showModal === 'quietanze' && '📄 Quietanze Caricate'}
                {showModal === 'alert' && '⚠️ Alert da Gestire'}
              </h2>
              <button 
                onClick={() => setShowModal(null)}
                style={{ background: 'none', border: 'none', fontSize: 24, cursor: 'pointer', color: '#6b7280' }}
              >
                ×
              </button>
            </div>

            {modalData.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
                <div>Nessun elemento</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {showModal === 'pagati' && modalData.map((f24) => {
                  const quietanza = quietanzeList.find(q => q.id === f24.quietanza_id);
                  return (
                    <div key={f24.id} style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, background: '#f9fafb' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 16, alignItems: 'start' }}>
                        <div style={{ background: 'white', borderRadius: 8, padding: 12, border: '1px solid #dbeafe' }}>
                          <div style={{ fontSize: 11, color: '#1535a8', fontWeight: 600, marginBottom: 8 }}>📤 F24 COMMERCIALISTA</div>
                          <div style={{ fontWeight: 600 }}>{f24.file_name || 'F24'}</div>
                          <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>Scadenza: {formatDateIT(f24.dati_generali?.data_versamento) || '-'}</div>
                          <div style={{ fontSize: 16, fontWeight: 700, color: '#1535a8', marginTop: 8 }}>{formatEuro(f24.totali?.saldo_netto || 0)}</div>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px 0' }}>
                          <div style={{ fontSize: 24 }}>🔗</div>
                        </div>
                        <div style={{ background: 'white', borderRadius: 8, padding: 12, border: '1px solid #d1fae5' }}>
                          <div style={{ fontSize: 11, color: '#15803d', fontWeight: 600, marginBottom: 8 }}>📄 QUIETANZA ADE</div>
                          {quietanza ? (
                            <>
                              <div style={{ fontWeight: 600 }}>{quietanza.filename || 'Quietanza'}</div>
                              <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>Pagamento: {quietanza.data_pagamento || '-'}</div>
                              <div style={{ fontSize: 16, fontWeight: 700, color: '#065f46', marginTop: 8 }}>{formatEuro(quietanza.saldo || 0)}</div>
                              {quietanza.protocollo_telematico && (
                                <div style={{ fontSize: 10, color: '#6b7280', marginTop: 8, fontFamily: 'monospace' }}>
                                  Protocollo: {quietanza.protocollo_telematico}
                                </div>
                              )}
                            </>
                          ) : (
                            <div style={{ color: '#9ca3af', fontStyle: 'italic' }}>Segnato pagato manualmente</div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {showModal === 'quietanze' && modalData.map((q) => (
                  <div key={q.id} style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                      <div>
                        <div style={{ fontWeight: 600 }}>{q.filename || 'Quietanza'}</div>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>Pagamento: {q.data_pagamento || '-'}</div>
                        {q.protocollo_telematico && (
                          <div style={{ fontSize: 10, color: '#6b7280', fontFamily: 'monospace', marginTop: 4 }}>
                            Protocollo: {q.protocollo_telematico}
                          </div>
                        )}
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#1535a8' }}>
                        {formatEuro(q.saldo || 0)}
                      </div>
                    </div>
                  </div>
                ))}
                {showModal === 'da_pagare' && modalData.map((f24) => (
                  <div key={f24.id} style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                      <div>
                        <div style={{ fontWeight: 600 }}>{f24.file_name || 'F24'}</div>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>Scadenza: {formatDateIT(f24.dati_generali?.data_versamento) || '-'}</div>
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#f97316' }}>
                        {formatEuro(f24.totali?.saldo_netto || 0)}
                      </div>
                    </div>
                  </div>
                ))}
                {showModal === 'alert' && modalData.map((alert) => (
                  <div key={alert.id} style={{ border: '1px solid #fecaca', borderRadius: 8, padding: 12, background: '#fef2f2' }}>
                    <div style={{ fontWeight: 500, color: '#991b1b' }}>{alert.message}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* PDF Viewer Modal */}
      {viewingPdf && (
        <div 
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1001
          }}
          onClick={() => setViewingPdf(null)}
        >
          <div 
            style={{
              background: 'white',
              borderRadius: 8,
              width: '90%',
              height: '90%',
              maxWidth: 1200,
              display: 'flex',
              flexDirection: 'column'
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ 
              padding: '12px 20px', 
              borderBottom: '1px solid #eee', 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center' 
            }}>
              <h3 style={{ margin: 0 }}>📄 {viewingPdf.name}</h3>
              <button
                onClick={() => setViewingPdf(null)}
                style={{
                  padding: '8px',
                  background: '#f5f5f5',
                  border: 'none',
                  borderRadius: 4,
                  cursor: 'pointer'
                }}
              >
                <X size={20} />
              </button>
            </div>
            <div style={{ flex: 1, padding: 10 }}>
              <iframe 
                src={viewingPdf.url}
                style={{ 
                  width: '100%', 
                  height: '100%', 
                  border: 'none',
                  borderRadius: 4
                }}
                title="PDF Viewer"
              />
            </div>
          </div>
        </div>
      )}

      {/* Edit F24 Modal */}
      {editingF24 && (
        <div 
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1001
          }}
          onClick={() => setEditingF24(null)}
        >
          <div 
            style={{
              background: 'white',
              borderRadius: 8,
              padding: 24,
              maxWidth: 500,
              width: '90%'
            }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>✏️ Modifica F24</h2>
            
            <div style={{ display: 'grid', gap: 15 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold' }}>File</label>
                <input
                  type="text"
                  value={editingF24.file_name || ''}
                  readOnly
                  style={{ padding: 10, width: '100%', borderRadius: 4, border: '1px solid #ddd', background: '#f5f5f5' }}
                />
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold' }}>Note</label>
                <textarea
                  value={editingF24.note || ''}
                  onChange={(e) => setEditingF24({...editingF24, note: e.target.value})}
                  rows={3}
                  style={{ padding: 10, width: '100%', borderRadius: 4, border: '1px solid #ddd' }}
                />
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
              <button
                onClick={() => setEditingF24(null)}
                style={{ padding: '10px 20px', background: '#9e9e9e', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer' }}
              >
                Annulla
              </button>
              <button
                onClick={() => handleUpdateF24(editingF24.id, { note: editingF24.note })}
                style={{ padding: '10px 20px', background: '#1535a8', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer' }}
              >
                Salva
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}
