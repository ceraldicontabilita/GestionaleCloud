import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge, useIsMobile, RG, pagePad } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import InvoiceXMLViewer from '../components/InvoiceXMLViewer';

export default function Scadenze() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const [scadenze, setScadenze] = useState([]);
  const [scadenzeIva, setScadenzeIva] = useState(null);
  const [scadenzeIvaMensili, setScadenzeIvaMensili] = useState(null);
  const [vistaIva, setVistaIva] = useState('trimestrale'); // 'trimestrale' o 'mensile'
  const [alertWidget, setAlertWidget] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filtroTipo, setFiltroTipo] = useState('');
  const [includePassate, setIncludePassate] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [viewingInvoice, setViewingInvoice] = useState(null);
  const [invoiceData, setInvoiceData] = useState(null);
  const [loadingInvoice, setLoadingInvoice] = useState(false);
  const [documentiRiconciliare, setDocumentiRiconciliare] = useState(null);
  const [pagaModal, setPagaModal] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [paidIds, setPaidIds] = useState(new Set());
  const [nuovaScadenza, setNuovaScadenza] = useState({
    data_scadenza: '',
    descrizione: '',
    tipo: 'CUSTOM',
    importo: '',
    priorita: 'media',
    note: ''
  });

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anno, filtroTipo, includePassate]);

  const loadData = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('anno', anno);
      if (filtroTipo) params.append('tipo', filtroTipo);
      params.append('include_passate', includePassate);
      params.append('limit', '50');
      
      const [scadenzeRes, ivaRes, ivaMensileRes, alertRes, docRiconcRes] = await Promise.all([
        api.get(`/api/scadenze/tutte?${params}`),
        api.get(`/api/scadenze/iva/${anno}`),
        api.get(`/api/scadenze/iva-mensile/${anno}`),
        api.get('/api/scadenze/dashboard-widget').catch(() => ({ data: null })),
        api.get('/api/email-scanner/statistiche').catch(() => ({ data: null }))
      ]);
      
      setScadenze(scadenzeRes.data.scadenze || []);
      setScadenzeIva(ivaRes.data);
      setScadenzeIvaMensili(ivaMensileRes.data);
      setAlertWidget(alertRes.data);
      setDocumentiRiconciliare(docRiconcRes.data);
    } catch (error) {
      console.error('Error loading scadenze:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePagaScadenza = async (scadenza, metodo) => {
    setProcessing(true);
    try {
      await api.post('/api/fatture-ricevute/paga-manuale', {
        fattura_id: scadenza.fattura_id || scadenza.id,
        scadenza_id: scadenza.id,
        importo: Math.abs(scadenza.importo),
        metodo: metodo,
        data_pagamento: new Date().toISOString().split('T')[0],
        fornitore: scadenza.fornitore || '',
        numero_fattura: scadenza.numero_fattura || ''
      });
      setPagaModal(null);
      setPaidIds(prev => new Set([...prev, scadenza.id]));
    } catch (e) {
      alert('Errore pagamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };


  const handleCreaScadenza = async () => {
    if (!nuovaScadenza.data_scadenza || !nuovaScadenza.descrizione) {
      alert('Compila data e descrizione');
      return;
    }
    
    try {
      await api.post('/api/scadenze/crea', {
        ...nuovaScadenza,
        importo: parseFloat(nuovaScadenza.importo) || 0
      });
      setShowModal(false);
      setNuovaScadenza({
        data_scadenza: '',
        descrizione: '',
        tipo: 'CUSTOM',
        importo: '',
        priorita: 'media',
        note: ''
      });
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCompleta = async (id) => {
    try {
      await api.put(`/api/scadenze/completa/${id}`);
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleElimina = async (id) => {
    if (!window.confirm('Eliminare questa scadenza?')) return;
    try {
      await api.delete(`/api/scadenze/${id}`);
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const formatDate = (dateStr) => dateStr ? formatDateIT(dateStr) : '-';

  const getPriorityStyle = (priorita, urgente) => {
    if (urgente) return { bg: '#fef2f2', border: '#dc2626', text: '#dc2626' };
    switch (priorita) {
      case 'critica': return { bg: '#fef2f2', border: '#dc2626', text: '#dc2626' };
      case 'alta': return { bg: '#fff7ed', border: '#ea580c', text: '#ea580c' };
      case 'media': return { bg: '#fefce8', border: '#ca8a04', text: '#ca8a04' };
      default: return { bg: '#f0fdf4', border: '#16a34a', text: '#16a34a' };
    }
  };

  const getTipoIcon = (tipo) => {
    switch (tipo) {
      case 'IVA': return '🧾';
      case 'F24': return '📋';
      case 'FATTURA': return '📄';
      case 'INPS': return '🏛️';
      case 'IRPEF': return '📋';
      default: return '📌';
    }
  };

  return (
    <PageLayout 
      title="Scadenze e Notifiche" 
      icon="📅" 
      subtitle="Gestione scadenze fiscali, pagamenti e promemoria"
      actions={
        <button
          onClick={() => setShowModal(true)}
          style={{
            padding: '10px 20px',
            background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold'
          }}
        >
          ➕ Nuova Scadenza
        </button>
      }
    >
      <div style={{ position: 'relative' }}>
        {/* Page Info Card */}
        {/* Alert Widget - Notifiche Urgenti */}
        {alertWidget && alertWidget.totale_alert > 0 && (
          <div style={{
            background: 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)',
            borderRadius: 12,
            padding: 20,
            marginBottom: 20,
            color: 'white'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 15 }}>
              <span style={{ fontSize: 24 }}>⚠️</span>
              <h3 style={{ margin: 0 }}>{alertWidget.totale_alert} Alert Attivi</h3>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              {alertWidget.libretti_sanitari?.scaduti > 0 && (
                <div 
                  onClick={() => navigate('/dipendenti')}
                  style={{
                    background: 'rgba(255,255,255,0.15)',
                    padding: 12,
                    borderRadius: 8,
                    cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
              >
                <div style={{ fontSize: 28, fontWeight: 700 }}>{alertWidget.libretti_sanitari.scaduti}</div>
                <div style={{ fontSize: 12, opacity: 0.9 }}>🔴 Libretti Scaduti</div>
              </div>
            )}
            {alertWidget.libretti_sanitari?.in_scadenza_30gg > 0 && (
              <div 
                onClick={() => navigate('/dipendenti')}
                style={{
                  background: 'rgba(255,255,255,0.15)',
                  padding: 12,
                  borderRadius: 8,
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
              >
                <div style={{ fontSize: 28, fontWeight: 700 }}>{alertWidget.libretti_sanitari.in_scadenza_30gg}</div>
                <div style={{ fontSize: 12, opacity: 0.9 }}>🟡 Libretti in Scadenza</div>
              </div>
            )}
            {alertWidget.contratti?.in_scadenza_60gg > 0 && (
              <div 
                onClick={() => navigate('/dipendenti')}
                style={{
                  background: 'rgba(255,255,255,0.15)',
                  padding: 12,
                  borderRadius: 8,
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
              >
                <div style={{ fontSize: 28, fontWeight: 700 }}>{alertWidget.contratti.in_scadenza_60gg}</div>
                <div style={{ fontSize: 12, opacity: 0.9 }}>📋 Contratti in Scadenza</div>
              </div>
            )}
            {alertWidget.f24?.da_pagare_30gg > 0 && (
              <div 
                onClick={() => navigate('/contabilita/calendario')}
                style={{
                  background: 'rgba(255,255,255,0.15)',
                  padding: 12,
                  borderRadius: 8,
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
              >
                <div style={{ fontSize: 28, fontWeight: 700 }}>{alertWidget.f24.da_pagare_30gg}</div>
                <div style={{ fontSize: 12, opacity: 0.9 }}>📋 F24 da Pagare</div>
              </div>
            )}
            {alertWidget.fiscali?.prossime > 0 && (
              <div style={{
                background: 'rgba(255,255,255,0.15)',
                padding: 12,
                borderRadius: 8
              }}>
                <div style={{ fontSize: 28, fontWeight: 700 }}>{alertWidget.fiscali.prossime}</div>
                <div style={{ fontSize: 12, opacity: 0.9 }}>📅 Scadenze Fiscali</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Sezione Documenti da Riconciliare */}
      {documentiRiconciliare && (documentiRiconciliare.verbali?.in_attesa_fattura > 0 || documentiRiconciliare.verbali?.estratti_da_fatture - documentiRiconciliare.verbali?.con_pdf_scaricato > 0) && (
        <div style={{ 
          background: 'linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%)',
          borderRadius: 12,
          padding: 20,
          marginBottom: 20,
          color: 'white'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 15 }}>
            <span style={{ fontSize: 24 }}>🔄</span>
            <h3 style={{ margin: 0 }}>Documenti da Riconciliare</h3>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
            {/* Verbali in attesa di fattura */}
            {documentiRiconciliare.verbali?.in_attesa_fattura > 0 && (
              <div 
                onClick={() => navigate('/noleggio')}
                style={{
                  background: 'rgba(255,255,255,0.15)',
                  padding: 15,
                  borderRadius: 10,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  borderLeft: '4px solid #fbbf24'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
                data-testid="verbali-attesa-fattura-card"
              >
                <div style={{ fontSize: 32, fontWeight: 700 }}>{documentiRiconciliare.verbali.in_attesa_fattura}</div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>📧 Verbali in Attesa Fattura</div>
                <div style={{ fontSize: 11, opacity: 0.8 }}>
                  PDF arrivati via email, fattura non ancora ricevuta
                </div>
              </div>
            )}
            
            {/* Fatture in attesa di verbale (PDF) */}
            {documentiRiconciliare.verbali?.estratti_da_fatture - documentiRiconciliare.verbali?.con_pdf_scaricato > 0 && (
              <div 
                onClick={() => navigate('/noleggio')}
                style={{
                  background: 'rgba(255,255,255,0.15)',
                  padding: 15,
                  borderRadius: 10,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  borderLeft: '4px solid #34d399'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
                data-testid="fatture-attesa-verbale-card"
              >
                <div style={{ fontSize: 32, fontWeight: 700 }}>
                  {documentiRiconciliare.verbali.estratti_da_fatture - documentiRiconciliare.verbali.con_pdf_scaricato}
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>📄 Fatture in Attesa Verbale</div>
                <div style={{ fontSize: 11, opacity: 0.8 }}>
                  Fattura ricevuta, PDF verbale non ancora scaricato
                </div>
              </div>
            )}
            
            {/* Esattoriali da processare */}
            {documentiRiconciliare.esattoriali > 0 && (
              <div style={{
                background: 'rgba(255,255,255,0.15)',
                padding: 15,
                borderRadius: 10,
                borderLeft: '4px solid #f87171'
              }}>
                <div style={{ fontSize: 32, fontWeight: 700 }}>{documentiRiconciliare.esattoriali}</div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Cartelle Esattoriali</div>
                <div style={{ fontSize: 11, opacity: 0.8 }}>
                  Da verificare e processare
                </div>
              </div>
            )}
            
            {/* F24/Tributi */}
            {documentiRiconciliare.f24_tributi > 0 && (
              <div style={{
                background: 'rgba(255,255,255,0.15)',
                padding: 15,
                borderRadius: 10,
                borderLeft: '4px solid #60a5fa'
              }}>
                <div style={{ fontSize: 32, fontWeight: 700 }}>{documentiRiconciliare.f24_tributi}</div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>📋 F24/Tributi</div>
                <div style={{ fontSize: 11, opacity: 0.8 }}>
                  Documenti da posta
                </div>
              </div>
            )}
          </div>
          
          {/* Riepilogo totale */}
          <div style={{ 
            marginTop: 15, 
            paddingTop: 15, 
            borderTop: '1px solid rgba(255,255,255,0.2)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div style={{ fontSize: 13, opacity: 0.9 }}>
              Totale documenti scaricati dalla posta: <strong>{documentiRiconciliare.totale_documenti_email}</strong>
            </div>
            <button
              onClick={async () => {
                try {
                  await api.post('/api/email-scanner/associa');
                  loadData();
                  alert('Associazione completata!');
                } catch (err) {
                  alert('Errore: ' + (err.response?.data?.detail || err.message));
                }
              }}
              style={{
                padding: '8px 16px',
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.3)',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: 600
              }}
              data-testid="btn-riconci-automatica"
            >
              🔄 Riconcilia Automaticamente
            </button>
          </div>
        </div>
      )}

      {/* Riepilogo IVA - Trimestrale e Mensile */}
      {(scadenzeIva || scadenzeIvaMensili) && (
        <div style={{ 
          background: 'linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%)',
          borderRadius: 12,
          padding: 20,
          marginBottom: 20,
          color: 'white'
        }}>
          {/* Header con bottoni toggle */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 }}>
            <h3 style={{ margin: 0 }}>🧾 Scadenze IVA {anno}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setVistaIva('trimestrale')}
                style={{
                  padding: '8px 16px',
                  borderRadius: 8,
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                  background: vistaIva === 'trimestrale' ? '#fbbf24' : 'rgba(255,255,255,0.2)',
                  color: vistaIva === 'trimestrale' ? '#000' : '#fff'
                }}
                data-testid="btn-vista-trimestrale"
              >
                📊 Trimestrale
              </button>
              <button
                onClick={() => setVistaIva('mensile')}
                style={{
                  padding: '8px 16px',
                  borderRadius: 8,
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                  background: vistaIva === 'mensile' ? '#34d399' : 'rgba(255,255,255,0.2)',
                  color: vistaIva === 'mensile' ? '#000' : '#fff'
                }}
                data-testid="btn-vista-mensile"
              >
                📅 Mensile
              </button>
            </div>
          </div>

          {/* Vista Trimestrale */}
          {vistaIva === 'trimestrale' && scadenzeIva && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 15 }}>
                {scadenzeIva.scadenze?.map((s, idx) => (
                  <div key={idx} style={{ 
                    background: 'rgba(255,255,255,0.1)', 
                    padding: 15, 
                    borderRadius: 8,
                    borderLeft: `4px solid ${s.da_versare ? '#fbbf24' : '#34d399'}`
                  }}>
                    <div style={{ fontWeight: 'bold', marginBottom: 8 }}>{s.periodo}</div>
                    <div style={{ fontSize: 13, opacity: 0.9 }}>
                      <div>Debito: {formatEuro(s.iva_debito)}</div>
                      <div>Credito: {formatEuro(s.iva_credito)}</div>
                    </div>
                    <div style={{ 
                      marginTop: 10, 
                      padding: '6px 10px', 
                      background: s.da_versare ? '#fbbf24' : '#34d399',
                      borderRadius: 6,
                      color: '#000',
                      fontWeight: 'bold',
                      fontSize: 14,
                      textAlign: 'center'
                    }}>
                      {s.da_versare ? `Versare ${formatEuro(s.importo_versamento)}` : `A credito ${formatEuro(s.a_credito || Math.abs(s.saldo || 0))}`}
                    </div>
                    <div style={{ fontSize: 11, marginTop: 8, opacity: 0.8 }}>
                      Scadenza: {formatDate(s.data_scadenza)}
                      {s.giorni_mancanti !== null && s.giorni_mancanti >= 0 && (
                        <span style={{ marginLeft: 8 }}>
                          ({s.giorni_mancanti === 0 ? 'OGGI' : `tra ${s.giorni_mancanti}g`})
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {scadenzeIva.totale_da_versare > 0 && (
                <div style={{ marginTop: 15, textAlign: 'right', fontSize: 18 }}>
                  Totale da versare: <strong>{formatEuro(scadenzeIva.totale_da_versare)}</strong>
                </div>
              )}
            </>
          )}

          {/* Vista Mensile */}
          {vistaIva === 'mensile' && scadenzeIvaMensili && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
                {scadenzeIvaMensili.scadenze?.map((s, idx) => (
                  <div key={idx} style={{ 
                    background: 'rgba(255,255,255,0.1)', 
                    padding: 12, 
                    borderRadius: 8,
                    borderLeft: `3px solid ${s.da_versare ? '#fbbf24' : '#34d399'}`
                  }}>
                    <div style={{ fontWeight: 'bold', marginBottom: 6, fontSize: 13 }}>{s.mese_nome}</div>
                    <div style={{ fontSize: 11, opacity: 0.9 }}>
                      <div>D: {formatEuro(s.iva_debito)}</div>
                      <div>C: {formatEuro(s.iva_credito)}</div>
                    </div>
                    <div style={{ 
                      marginTop: 8, 
                      padding: '4px 8px', 
                      background: s.da_versare ? '#fbbf24' : '#34d399',
                      borderRadius: 4,
                      color: '#000',
                      fontWeight: 'bold',
                      fontSize: 12,
                      textAlign: 'center'
                    }}>
                      {s.da_versare ? formatEuro(s.importo_versamento) : `- ${formatEuro(s.a_credito || Math.abs(s.saldo || 0))}`}
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 15, display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                <div>
                  Totale a credito: <strong style={{ color: '#34d399' }}>{formatEuro(scadenzeIvaMensili.totale_a_credito)}</strong>
                </div>
                <div>
                  Totale da versare: <strong style={{ color: '#fbbf24' }}>{formatEuro(scadenzeIvaMensili.totale_da_versare)}</strong>
                </div>
                <div>
                  Saldo annuale: <strong style={{ color: scadenzeIvaMensili.saldo_annuale > 0 ? '#fbbf24' : '#34d399' }}>
                    {scadenzeIvaMensili.saldo_annuale > 0 ? `Da versare ${formatEuro(scadenzeIvaMensili.saldo_annuale)}` : `A credito ${formatEuro(Math.abs(scadenzeIvaMensili.saldo_annuale))}`}
                  </strong>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Filtri */}
      <div style={{ 
        display: 'flex', 
        gap: 12, 
        marginBottom: 20, 
        flexWrap: 'wrap',
        alignItems: 'center',
        background: '#f8fafc',
        padding: 15,
        borderRadius: 10
      }}>
        <select
          value={filtroTipo}
          onChange={(e) => setFiltroTipo(e.target.value)}
          style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
        >
          <option value="">Tutti i tipi</option>
          <option value="IVA">IVA</option>
          <option value="F24">F24</option>
          <option value="FATTURA">Fatture</option>
          <option value="INPS">INPS</option>
          <option value="CUSTOM">Personalizzate</option>
        </select>
        
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={includePassate}
            onChange={(e) => setIncludePassate(e.target.checked)}
          />
          <span>Mostra scadenze passate</span>
        </label>
        
        <button
          onClick={loadData}
          style={{
            padding: '8px 16px',
            background: '#e5e7eb',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer'
          }}
        >
          🔄 Aggiorna
        </button>
      </div>

      {/* Lista Scadenze */}
      <div style={{ background: 'white', borderRadius: 12, overflow: 'hidden', border: '1px solid #e5e7eb' }}>
        <div style={{ padding: '16px 20px', background: '#f8fafc', borderBottom: '1px solid #e5e7eb', fontWeight: 'bold' }}>
          📋 Tutte le Scadenze ({scadenze.length})
        </div>
        
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
        ) : scadenze.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            Nessuna scadenza trovata per i filtri selezionati.
          </div>
        ) : (
          <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
            {/* Tabella scadenze */}
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e2e8f0', background: '#f8fafc' }}>
                  <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 700, fontSize: 11, color: '#64748b', textTransform: 'uppercase', width: 70 }}>Tipo</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 700, fontSize: 11, color: '#64748b', textTransform: 'uppercase', width: 90 }}>Importo</th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 700, fontSize: 11, color: '#64748b', textTransform: 'uppercase', width: 70 }}>Data</th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 700, fontSize: 11, color: '#64748b', textTransform: 'uppercase', width: 60 }}>Giorni</th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 700, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>Descrizione</th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 700, fontSize: 11, color: '#64748b', textTransform: 'uppercase', width: 100 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
            {scadenze.map((s, idx) => {
              const style = getPriorityStyle(s.priorita, s.urgente);
              const isPassata = s.giorni_mancanti !== undefined && s.giorni_mancanti < 0;
              
              return (
                <tr
                  key={s.id || `scad-${idx}`}
                  style={{
                    background: isPassata ? '#f9fafb' : style.bg,
                    opacity: isPassata ? 0.6 : 1,
                    borderLeft: `4px solid ${style.border}`,
                    borderBottom: '1px solid #f1f5f9'
                  }}
                >
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                    <span style={{ 
                      padding: '3px 8px', 
                      background: style.border + '20', 
                      borderRadius: 6,
                      color: style.text,
                      fontWeight: '600',
                      fontSize: 11
                    }}>
                      {s.tipo}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 'bold', color: style.text }}>
                    {s.importo > 0 ? formatEuro(s.importo) : '-'}
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'center', color: '#6b7280' }}>
                    {formatDate(s.data)}
                  </td>
                  <td style={{ 
                    padding: '8px 12px', 
                    textAlign: 'center',
                    fontWeight: 'bold',
                    color: isPassata ? '#dc2626' : (s.urgente ? '#dc2626' : '#6b7280')
                  }}>
                    {s.giorni_mancanti === undefined ? '' :
                     s.giorni_mancanti === 0 ? 'OGGI' :
                     s.giorni_mancanti === 1 ? '1g' :
                     s.giorni_mancanti < 0 ? `-${Math.abs(s.giorni_mancanti)}g` :
                     `${s.giorni_mancanti}g`}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 250 }}>
                    {s.descrizione}
                    {s.fornitore && <span style={{ color: '#9ca3af', marginLeft: 8 }}>• {s.fornitore}</span>}
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                  {s.source === 'custom' && (
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                      <button
                        onClick={() => handleCompleta(s.id)}
                        style={{
                          padding: '4px 10px',
                          background: '#10b981',
                          color: 'white',
                          border: 'none',
                          borderRadius: 4,
                          cursor: 'pointer',
                          fontSize: 11
                        }}
                        title="Segna come completata"
                      >
                        ✓
                      </button>
                      <button
                        onClick={() => handleElimina(s.id)}
                        style={{
                          padding: '6px 12px',
                          background: '#ef4444',
                          color: 'white',
                          border: 'none',
                          borderRadius: 6,
                          cursor: 'pointer',
                          fontSize: 12
                        }}
                        title="Elimina"
                      >
                        🗑️
                      </button>
                    </div>
                  )}
                  
                  {/* Pulsanti Visualizza Fattura per scadenze tipo FATTURA */}
                  {(s.tipo === 'FATTURA' || s.source === 'fattura') && (s.fattura_id || s.id) && (
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button
                        onClick={async () => {
                          setLoadingInvoice(true);
                          try {
                            const fattura_id = s.fattura_id || s.id;
                            const res = await api.get(`/api/fatture/${fattura_id}`);
                            if (res.data) {
                              setInvoiceData(res.data);
                              setViewingInvoice(fattura_id);
                            } else {
                              alert('Fattura non trovata');
                            }
                          } catch (err) {
                            console.error('Errore caricamento fattura:', err);
                            alert('Errore nel caricamento della fattura');
                          } finally {
                            setLoadingInvoice(false);
                          }
                        }}
                        disabled={loadingInvoice}
                        style={{
                          padding: '4px 8px',
                          background: loadingInvoice ? '#9ca3af' : '#3b82f6',
                          color: 'white',
                          border: 'none',
                          borderRadius: 4,
                          cursor: loadingInvoice ? 'wait' : 'pointer',
                          fontSize: 10
                        }}
                        title="Visualizza Dettagli Fattura"
                        data-testid={`view-invoice-${s.fattura_id || s.id}`}
                      >
                        {loadingInvoice ? '⏳' : '👁️'}
                      </button>
                      <a
                        href={`/api/fatture-ricevute/fattura/${s.fattura_id || s.id}/view-assoinvoice`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          padding: '4px 8px',
                          background: '#10b981',
                          color: 'white',
                          border: 'none',
                          borderRadius: 4,
                          fontSize: 10,
                          textDecoration: 'none'
                        }}
                        title="Visualizza PDF Fattura"
                        data-testid={`pdf-invoice-${s.fattura_id || s.id}`}
                      >
                        📄
                      </a>
                    </div>
                  )}
                  
                  {/* Bottone Paga Cassa/Banca */}
                  {!paidIds.has(s.id) && (s.tipo === 'FATTURA' || s.source === 'fattura' || s.importo > 0) && (
                    <button
                      onClick={() => setPagaModal(s)}
                      style={{
                        padding: '4px 8px',
                        background: '#f59e0b',
                        color: 'white',
                        border: 'none',
                        borderRadius: 4,
                        cursor: 'pointer',
                        fontSize: 10,
                        fontWeight: 600,
                        marginTop: 4
                      }}
                      title="Registra Pagamento"
                    >
                      💰 Paga
                    </button>
                  )}
                  {paidIds.has(s.id) && (
                    <span style={{ padding: '3px 8px', background: '#dcfce7', color: '#16a34a', borderRadius: 4, fontSize: 10, fontWeight: 700 }}>✓ Pagato</span>
                  )}
                  </td>
                </tr>
              );
            })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Nuova Scadenza */}
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
        }} onClick={() => setShowModal(false)}>
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 24,
            width: '90%',
            maxWidth: 500
          }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 20px 0' }}>➕ Nuova Scadenza</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: 15 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}>Data Scadenza *</label>
                <input
                  type="date"
                  value={nuovaScadenza.data_scadenza}
                  onChange={(e) => setNuovaScadenza({ ...nuovaScadenza, data_scadenza: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
                />
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}>Descrizione *</label>
                <input
                  type="text"
                  value={nuovaScadenza.descrizione}
                  onChange={(e) => setNuovaScadenza({ ...nuovaScadenza, descrizione: e.target.value })}
                  placeholder="Es: Pagamento fornitore XYZ"
                  style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
                />
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 15 }}>
                <div>
                  <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}>Tipo</label>
                  <select
                    value={nuovaScadenza.tipo}
                    onChange={(e) => setNuovaScadenza({ ...nuovaScadenza, tipo: e.target.value })}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
                  >
                    <option value="CUSTOM">Personalizzata</option>
                    <option value="FATTURA">Fattura</option>
                    <option value="F24">F24</option>
                    <option value="IVA">IVA</option>
                    <option value="INPS">INPS</option>
                  </select>
                </div>
                
                <div>
                  <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}>Priorità</label>
                  <select
                    value={nuovaScadenza.priorita}
                    onChange={(e) => setNuovaScadenza({ ...nuovaScadenza, priorita: e.target.value })}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
                  >
                    <option value="bassa">Bassa</option>
                    <option value="media">Media</option>
                    <option value="alta">Alta</option>
                    <option value="critica">Critica</option>
                  </select>
                </div>
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}>Importo (opzionale)</label>
                <input
                  type="number"
                  step="0.01"
                  value={nuovaScadenza.importo}
                  onChange={(e) => setNuovaScadenza({ ...nuovaScadenza, importo: e.target.value })}
                  placeholder="0.00"
                  style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
                />
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}>Note (opzionale)</label>
                <textarea
                  value={nuovaScadenza.note}
                  onChange={(e) => setNuovaScadenza({ ...nuovaScadenza, note: e.target.value })}
                  rows={2}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid #e2e8f0', resize: 'vertical' }}
                />
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowModal(false)}
                style={{
                  padding: '10px 20px',
                  background: '#e5e7eb',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer'
                }}
              >
                Annulla
              </button>
              <button
                onClick={handleCreaScadenza}
                style={{
                  padding: '10px 20px',
                  background: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontWeight: 'bold'
                }}
              >
                Salva Scadenza
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Modal Visualizzazione Fattura AssoInvoice */}
      {viewingInvoice && invoiceData && (
        <InvoiceXMLViewer 
          invoice={invoiceData} 
          onClose={() => {
            setViewingInvoice(null);
            setInvoiceData(null);
          }} 
        />
      )}

      {/* Modal Pagamento Cassa/Banca */}
      {pagaModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => setPagaModal(null)}>
          <div style={{
            background: 'white', borderRadius: 16, padding: 24, maxWidth: 420, width: '90%',
            boxShadow: '0 25px 50px rgba(0,0,0,0.25)'
          }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 8px', fontSize: 18, color: '#1e3a5f' }}>💰 Registra Pagamento</h3>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
              {pagaModal.fornitore || pagaModal.descrizione}
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#1e3a5f', marginBottom: 20, textAlign: 'center' }}>
              {pagaModal.importo > 0 ? `€ ${pagaModal.importo.toFixed(2)}` : '—'}
            </div>
            <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
              <button
                disabled={processing}
                onClick={() => handlePagaScadenza(pagaModal, 'cassa')}
                style={{
                  flex: 1, padding: '14px 20px', borderRadius: 10, border: 'none',
                  background: '#f59e0b', color: 'white', fontWeight: 700, fontSize: 15,
                  cursor: processing ? 'wait' : 'pointer', opacity: processing ? 0.6 : 1
                }}
              >
                🏪 Paga in CASSA
              </button>
              <button
                disabled={processing}
                onClick={() => handlePagaScadenza(pagaModal, 'banca')}
                style={{
                  flex: 1, padding: '14px 20px', borderRadius: 10, border: 'none',
                  background: '#3b82f6', color: 'white', fontWeight: 700, fontSize: 15,
                  cursor: processing ? 'wait' : 'pointer', opacity: processing ? 0.6 : 1
                }}
              >
                🏦 Paga in BANCA
              </button>
            </div>
            <button
              onClick={() => setPagaModal(null)}
              style={{
                width: '100%', padding: '10px', background: '#f3f4f6', color: '#6b7280',
                border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13
              }}
            >
              Annulla
            </button>
          </div>
        </div>
      )}

      </div>
    </PageLayout>
  );
}
