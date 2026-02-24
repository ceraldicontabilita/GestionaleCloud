import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

const MESI = [
  { value: '', label: 'Tutti i mesi' },
  { value: '1', label: 'Gennaio' },
  { value: '2', label: 'Febbraio' },
  { value: '3', label: 'Marzo' },
  { value: '4', label: 'Aprile' },
  { value: '5', label: 'Maggio' },
  { value: '6', label: 'Giugno' },
  { value: '7', label: 'Luglio' },
  { value: '8', label: 'Agosto' },
  { value: '9', label: 'Settembre' },
  { value: '10', label: 'Ottobre' },
  { value: '11', label: 'Novembre' },
  { value: '12', label: 'Dicembre' }
];

// Tabs della pagina unificata - Scadenze rimosso (centralizzato in Dashboard)
const TABS = [
  { id: 'archivio', label: '📋 Archivio', desc: 'Lista e ricerca fatture' },
  { id: 'riconciliazione', label: '🔄 Riconcilia', desc: 'Match con banca' },
  { id: 'storico', label: '✅ Storico', desc: 'Pagamenti effettuati' },
];

// Stili inline (come da DESIGN_SYSTEM.md)
const cardStyle = { background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', border: '1px solid #e5e7eb' };
const btnPrimary = { padding: '10px 20px', background: '#15803d', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold', fontSize: 14 };
const btnSecondary = { padding: '10px 20px', background: '#e5e7eb', color: '#374151', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600', fontSize: 14 };
const inputStyle = { padding: '10px 12px', borderRadius: 8, border: '2px solid #e5e7eb', fontSize: 14, boxSizing: 'border-box' };
const selectStyle = { padding: '10px 12px', borderRadius: 8, border: '2px solid #e5e7eb', fontSize: 14, background: 'white' };

// Stili aggiuntivi per riconciliazione
const styles = {
  badge: (color) => ({
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 10px',
    borderRadius: 20,
    fontSize: 12,
    fontWeight: 600,
    background: `${color}15`,
    color: color
  }),
  button: (variant = 'primary') => ({
    padding: '8px 14px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    fontWeight: 500,
    fontSize: 13,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    transition: 'all 0.2s',
    ...(variant === 'primary' ? { background: '#1535a8', color: 'white' } 
      : variant === 'success' ? { background: '#15803d', color: 'white' }
      : variant === 'danger' ? { background: '#ef4444', color: 'white' }
      : { background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' })
  }),
  uploadZone: {
    border: '2px dashed #cbd5e1',
    borderRadius: 12,
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
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 14 },
  th: { padding: '12px 16px', textAlign: 'left', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', background: '#f8fafc' },
  td: { padding: '12px 16px', borderBottom: '1px solid #f1f5f9', color: '#334155' },
  emptyState: { textAlign: 'center', padding: '60px 20px', color: '#64748b' },
  splitView: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 },
  rowHighlight: { background: '#fef3c7', cursor: 'pointer' },
  rowSelected: { background: '#dbeafe' }
};

export default function ArchivioFatture() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { anno } = useAnnoGlobale();
  
  // Tab attivo
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'archivio');
  
  // Dati archivio
  const [fatture, setFatture] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [statistiche, setStatistiche] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Dati per Scadenze e Riconciliazione
  const [dashboard, setDashboard] = useState(null);
  const [selectedScadenza, setSelectedScadenza] = useState(null);
  const [suggerimenti, setSuggerimenti] = useState([]);
  const [loadingSuggerimenti, setLoadingSuggerimenti] = useState(false);
  const [processing, setProcessing] = useState(false);
  
  // Menu pagamento manuale
  const [showPayMenu, setShowPayMenu] = useState(null); // ID della scadenza con menu aperto
  const [payingScadenza, setPayingScadenza] = useState(null);
  
  // Ref per salvare posizione scroll
  const scrollPositionRef = useRef(0);
  
  // Filtri (anno viene dal contesto globale)
  const [mese, setMese] = useState(searchParams.get('mese') || '');
  const [fornitore, setFornitore] = useState(searchParams.get('fornitore') || searchParams.get('fornitore_piva') || '');
  const [stato, setStato] = useState(searchParams.get('stato') || '');
  const [search, setSearch] = useState(searchParams.get('search') || '');
  
  // Stato per auto-riparazione
  const [autoRepairStatus, setAutoRepairStatus] = useState(null);
  const [autoRepairRunning, setAutoRepairRunning] = useState(false);

  // Funzione per pagare manualmente una scadenza (Cassa o Banca)
  const handlePayManual = async (scadenza, metodo) => {
    scrollPositionRef.current = window.scrollY; // Salva posizione
    setShowPayMenu(null);
    setPayingScadenza(scadenza.id);
    try {
      const dataPagamento = new Date().toISOString().slice(0, 10);
      
      // Registra il pagamento e crea movimento in Prima Nota
      const res = await api.post('/api/fatture-ricevute/paga-manuale', {
        fattura_id: scadenza.fattura_id,
        scadenza_id: scadenza.id,
        importo: scadenza.importo_totale,
        metodo: metodo, // 'cassa' o 'banca'
        data_pagamento: dataPagamento,
        fornitore: scadenza.fornitore_nome,
        numero_fattura: scadenza.numero_fattura
      });
      
      // Ricarica dati
      await fetchDashboard();
      
      // Ripristina posizione scroll
      setTimeout(() => window.scrollTo({ top: scrollPositionRef.current, behavior: 'instant' }), 100);
      
    } catch (error) {
      alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
    } finally {
      setPayingScadenza(null);
      setShowPayMenu(null);
    }
  };

  /**
   * LOGICA INTELLIGENTE: Esegue auto-riparazione dei dati.
   * DISABILITATA: Spostata in Admin per performance. Chiamare manualmente se necessario.
   */
  const eseguiAutoRiparazione = async () => {
    setAutoRepairRunning(true);
    try {
      const res = await api.post('/api/fatture-ricevute/auto-ricostruisci-dati');
      if (res.data.campi_corretti > 0 || res.data.duplicati_rimossi > 0 || res.data.fornitori_associati > 0) {
        console.log('🔧 Auto-riparazione fatture completata:', res.data);
        setAutoRepairStatus(res.data);
        // Ricarica dati dopo riparazione
        fetchFatture();
      }
    } catch (error) {
      console.warn('Auto-riparazione fatture non riuscita:', error);
    } finally {
      setAutoRepairRunning(false);
    }
  };

  useEffect(() => {
    // RIMOSSO per performance - eseguiAutoRiparazione() ora solo manuale
     
  }, []);

  // ==================== FETCH FUNCTIONS ====================
  
  const fetchFatture = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.append('anno', anno);
      if (mese) params.append('mese', mese);
      if (fornitore) params.append('fornitore_piva', fornitore);
      if (stato) params.append('stato', stato);
      if (search) params.append('search', search);
      params.append('limit', '100');
      
      const res = await api.get(`/api/fatture-ricevute/archivio?${params.toString()}`);
      setFatture(res.data.fatture || res.data.items || []);
    } catch (err) {
      console.error('Errore caricamento fatture:', err);
    }
    setLoading(false);
  }, [anno, mese, fornitore, stato, search]);

  const fetchFornitori = async () => {
    try {
      const res = await api.get('/api/fatture-ricevute/fornitori?con_fatture=true&limit=500');
      setFornitori(res.data.items || []);
    } catch (err) {
      console.error('Errore caricamento fornitori:', err);
    }
  };

  const fetchStatistiche = async () => {
    try {
      const params = anno ? `?anno=${anno}` : '';
      const res = await api.get(`/api/fatture-ricevute/statistiche${params}`);
      setStatistiche(res.data);
    } catch (err) {
      console.error('Errore caricamento statistiche:', err);
    }
  };

  const fetchDashboard = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (anno) params.append('anno', anno);
      const res = await api.get(`/api/ciclo-passivo/dashboard-riconciliazione?${params}`);
      setDashboard(res.data);
    } catch (err) {
      console.error('Errore caricamento dashboard:', err);
    }
  }, [anno]);

  // ==================== EFFECTS ====================

  useEffect(() => {
    fetchFatture();
    fetchStatistiche();
  }, [fetchFatture, anno]);

  useEffect(() => {
    fetchFornitori();
  }, []);

  useEffect(() => {
    // Carica dashboard quando si accede ai tab pipeline, scadenze, riconciliazione o storico
    if (['import', 'scadenze', 'riconciliazione', 'storico'].includes(activeTab)) {
      fetchDashboard();
    }
  }, [activeTab, fetchDashboard]);

  // ==================== UPLOAD HANDLERS ====================

  // ==================== RICONCILIAZIONE HANDLERS ====================

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
      fetchDashboard();
    } catch (e) {
      alert(`Errore: ${e.response?.data?.detail || e.message}`);
    } finally {
      setProcessing(false);
    }
  };

  // ==================== HELPERS ====================

  // Usa formatEuro da utils.js (già importato)
  const formatCurrency = formatEuro;
  
  // Usa formatDateIT da utils.js
  const formatDate = formatDateIT;

  const isScadenzaPassata = (dataScadenza) => {
    if (!dataScadenza) return false;
    try {
      return new Date(dataScadenza) < new Date();
    } catch { return false; }
  };

  const getStatoBadge = (fattura) => {
    if (fattura.pagato) {
      let metodo = fattura.metodo_pagamento || '';
      let icon = '✅';
      let label = 'Pagata';
      
      if (fattura.prima_nota_cassa_id || metodo.toLowerCase().includes('cassa') || metodo.toLowerCase().includes('contanti')) {
        icon = '💵'; label = 'Cassa';
      } else if (fattura.prima_nota_banca_id || metodo.toLowerCase().includes('banca') || metodo.toLowerCase().includes('bonifico')) {
        icon = '🏦'; label = 'Banca';
      } else if (metodo.toLowerCase().includes('assegno')) {
        icon = '📝'; label = 'Assegno';
      } else if (metodo.toLowerCase().includes('rid') || metodo.toLowerCase().includes('sdd')) {
        icon = '🔄'; label = 'RID/SDD';
      }
      
      return (
        <span style={{ padding: '4px 10px', background: '#dcfce7', color: '#16a34a', borderRadius: 6, fontSize: 11, fontWeight: '600', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {icon} {label}
        </span>
      );
    }
    if (fattura.stato === 'anomala') {
      return <span style={{ padding: '4px 10px', background: '#fee2e2', color: '#dc2626', borderRadius: 6, fontSize: 12, fontWeight: '600' }}>Anomala</span>;
    }
    return <span style={{ padding: '4px 10px', background: '#fef3c7', color: '#d97706', borderRadius: 6, fontSize: 12, fontWeight: '600' }}>Da pagare</span>;
  };

  const stats = dashboard?.statistiche || {};

  // ==================== RENDER ====================

  return (
    <PageLayout title="Ciclo Passivo - Fatture Ricevute" subtitle={`Gestione fatture anno ${anno}`}>
    <div style={{ maxWidth: 1600, margin: '0 auto', position: 'relative' }} data-testid="ciclo-passivo-unificato">
      {/* Page Info Card */}      
      {/* Header con Tabs */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#1e293b', margin: '0 0 8px' }}>
          📄 Ciclo Passivo - Fatture Ricevute ({anno})
        </h1>
        <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: 14 }}>
          Import → Magazzino → Prima Nota → Scadenziario → Riconciliazione
        </p>
        
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, borderBottom: '2px solid #e5e7eb', overflowX: 'auto', paddingBottom: 2 }}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setSearchParams(prev => { prev.set('tab', tab.id); return prev; });
              }}
              style={{
                padding: '12px 16px',
                background: activeTab === tab.id ? '#1535a8' : 'transparent',
                color: activeTab === tab.id ? 'white' : '#64748b',
                border: 'none',
                borderRadius: '8px 8px 0 0',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 13,
                whiteSpace: 'nowrap',
                transition: 'all 0.2s'
              }}
              data-testid={`tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats Cards (visibili in tutti i tab) */}
      {dashboard && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 20 }}>
          <div style={{ background: 'linear-gradient(135deg, #ef444415, #ef444408)', borderRadius: 12, padding: 16, border: '1px solid #ef444430' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#ef4444' }}>{stats.num_scadenze_aperte || 0}</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Scadenze Aperte</div>
          </div>
          <div style={{ background: 'linear-gradient(135deg, #d9770615, #d9770608)', borderRadius: 12, padding: 16, border: '1px solid #d9770630' }}>
            <div style={{ fontSize: 18, fontWeight: 'bold', color: '#d97706' }}>{formatEuro(stats.totale_debito_aperto || 0)}</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Debito Aperto</div>
          </div>
          <div style={{ background: 'linear-gradient(135deg, #15803d15, #15803d08)', borderRadius: 12, padding: 16, border: '1px solid #15803d30' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#15803d' }}>{stats.num_scadenze_saldate || 0}</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Scadenze Saldate</div>
          </div>
          <div style={{ background: 'linear-gradient(135deg, #1535a815, #1535a808)', borderRadius: 12, padding: 16, border: '1px solid #1535a830' }}>
            <div style={{ fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>{formatEuro(stats.totale_pagato || 0)}</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Totale Pagato</div>
          </div>
        </div>
      )}

      {/* ==================== TAB: ARCHIVIO ==================== */}
      {activeTab === 'archivio' && (
        <>
          {/* Header Archivio */}
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center', 
            marginBottom: 20,
            padding: '15px 20px',
            background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
            borderRadius: 12,
            color: 'white',
            flexWrap: 'wrap',
            gap: 10
          }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold' }}>📋 Archivio Fatture Ricevute</h2>
              <p style={{ margin: '4px 0 0 0', fontSize: 12, opacity: 0.9 }}>Gestione fatture passive con controllo duplicati</p>
            </div>
            <button
              onClick={() => navigate('/import-unificato')}
              style={{ ...btnPrimary, display: 'flex', alignItems: 'center', gap: 8 }}
              data-testid="btn-import-unificato"
            >
              📤 Vai a Import Unificato
            </button>
          </div>

          {/* Statistiche */}
          {statistiche && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, marginBottom: 20 }}>
              <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
                <div style={{ fontSize: 22, fontWeight: 'bold', color: '#1535a8' }}>{statistiche.totale_fatture}</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>Fatture Totali</div>
              </div>
              <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
                <div style={{ fontSize: 18, fontWeight: 'bold', color: '#16a34a' }}>{formatCurrency(statistiche.totale_importo)}</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>Importo Totale</div>
              </div>
              <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
                <div style={{ fontSize: 22, fontWeight: 'bold', color: '#2196f3' }}>{statistiche.fornitori_unici}</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>Fornitori</div>
              </div>
              <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
                <div style={{ fontSize: 22, fontWeight: 'bold', color: statistiche.fatture_anomale > 0 ? '#dc2626' : '#16a34a' }}>{statistiche.fatture_anomale}</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>Anomale</div>
              </div>
            </div>
          )}

          {/* Filtri */}
          <div style={{ ...cardStyle, marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Anno</label>
                <div style={{ ...selectStyle, minWidth: 80, background: '#f1f5f9', color: '#64748b', fontWeight: 600, fontSize: 13 }}>
                  {anno} <span style={{ fontSize: 9, opacity: 0.7 }}>(globale)</span>
                </div>
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Mese</label>
                <select value={mese} onChange={(e) => setMese(e.target.value)} style={{ ...selectStyle, minWidth: 110, fontSize: 13 }}>
                  {MESI.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Fornitore</label>
                <select value={fornitore} onChange={(e) => setFornitore(e.target.value)} style={{ ...selectStyle, minWidth: 180, fontSize: 13 }}>
                  <option value="">Tutti i fornitori</option>
                  {fornitori.map(f => (
                    <option key={f.partita_iva} value={f.partita_iva}>
                      {f.ragione_sociale} ({f.partita_iva})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Stato</label>
                <select value={stato} onChange={(e) => setStato(e.target.value)} style={{ ...selectStyle, minWidth: 100, fontSize: 13 }}>
                  <option value="">Tutti</option>
                  <option value="importata">Importate</option>
                  <option value="anomala">Anomale</option>
                  <option value="pagata">Pagate</option>
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 180 }}>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Ricerca</label>
                <input
                  type="text"
                  placeholder="Numero fattura, fornitore..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && fetchFatture()}
                  style={{ ...inputStyle, width: '100%', fontSize: 13 }}
                />
              </div>
              <div style={{ alignSelf: 'flex-end' }}>
                <button onClick={fetchFatture} style={{ ...btnPrimary, fontSize: 13 }}>🔍 Cerca</button>
              </div>
            </div>
          </div>

          {/* Tabella Fatture */}
          <div style={cardStyle}>
            {loading ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
            ) : fatture.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
                <p style={{ margin: 0 }}>Nessuna fattura trovata</p>
                <p style={{ margin: '8px 0 0 0', fontSize: 14 }}>Vai a Import Unificato per importare fatture</p>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 4px', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#1535a8' }}>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', color: 'white', borderRadius: '8px 0 0 8px' }}>Data</th>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', color: 'white' }}>Numero</th>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', color: 'white' }}>Fornitore</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: '600', color: 'white' }}>Imponibile</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: '600', color: 'white' }}>IVA</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: '600', color: 'white' }}>Totale</th>
                      <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', color: 'white', borderRadius: '0 8px 8px 0', minWidth: 280 }}>Azioni</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fatture.map((f, idx) => {
                      const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
                      // Determina metodo EFFETTIVO del pagamento guardando:
                      // 1. prima_nota_cassa_id / prima_nota_banca_id (fonte primaria)
                      // 2. metodo_pagamento / metodo_pagamento_effettivo (fallback per dati legacy)
                      const hasCassaId = !!f.prima_nota_cassa_id;
                      const hasBancaId = !!f.prima_nota_banca_id;
                      const metodoSalvato = (f.metodo_pagamento_effettivo || f.metodo_pagamento || '').toLowerCase();
                      const isCassaByMetodo = metodoSalvato.includes('contant') || metodoSalvato === 'cassa' || metodoSalvato.includes('cash');
                      const isBancaByMetodo = metodoSalvato.includes('bonifico') || metodoSalvato === 'banca' || metodoSalvato.includes('bank') || metodoSalvato.includes('sepa') || metodoSalvato.includes('rid');
                      
                      // Priorità: ID prima nota > metodo salvato > null
                      const metodoPagEffettivo = hasCassaId ? 'cassa' 
                        : hasBancaId ? 'banca' 
                        : isCassaByMetodo ? 'cassa'
                        : isBancaByMetodo ? 'banca'
                        : null;
                      
                      // Metodo configurato nel fornitore (per default quando non pagato)
                      const metodoFornitore = (f.fornitore_metodo_pagamento || f.metodo_pagamento || '').toLowerCase();
                      const isFornitoreCassa = metodoFornitore.includes('contant') || metodoFornitore === 'cassa';
                      
                      // BLOCCO: Se riconciliata, non permettere modifica
                      const isRiconciliata = f.riconciliato === true;
                      
                      return (
                      <tr key={f.id} style={{ 
                        background: idx % 2 === 0 ? 'white' : '#f8fafc', 
                        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                        transition: 'background 0.2s'
                      }}>
                        <td style={{ padding: '14px 16px', borderRadius: '8px 0 0 8px' }}>{formatDateIT(f.invoice_date || f.data_documento)}</td>
                        <td style={{ padding: '14px 16px', fontWeight: '600', color: '#1535a8' }}>{f.invoice_number || f.numero_documento}</td>
                        <td style={{ padding: '14px 16px' }}>
                          <div style={{ fontWeight: '500', fontSize: 13, color: '#374151' }}>{f.supplier_name || f.fornitore_ragione_sociale}</div>
                          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{f.supplier_vat || f.fornitore_partita_iva}</div>
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(f.imponibile)}</td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', fontFamily: 'monospace', color: '#6b7280' }}>{formatCurrency(f.iva)}</td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 'bold', fontFamily: 'monospace', color: '#1535a8' }}>{formatCurrency(f.total_amount || f.importo_totale)}</td>
                        <td style={{ padding: '14px 16px', textAlign: 'center', borderRadius: '0 8px 8px 0' }}>
                          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center' }}>
                            {/* Badge RICONCILIATA se applicabile */}
                            {isRiconciliata && (
                              <span 
                                style={{ 
                                  padding: '6px 10px', 
                                  background: '#15803d', 
                                  color: 'white', 
                                  borderRadius: 6, 
                                  fontSize: 11, 
                                  fontWeight: 'bold'
                                }}
                                title="Fattura riconciliata con estratto conto - non modificabile"
                              >
                                ✓ RICONC.
                              </span>
                            )}
                            
                            <a
                              href={`/api/fatture-ricevute/fattura/${f.id}/view-assoinvoice`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ padding: '8px 12px', background: '#1535a8', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: '600', textDecoration: 'none' }}
                              title="Visualizza fattura"
                            >
                              📄 Vedi
                            </a>
                            
                            {/* Pulsante Cassa - verde se attivo, grigio se non selezionato - PULSANTE GRANDE */}
                            {/* DISABILITATO se riconciliata */}
                            <button
                              disabled={isRiconciliata}
                              onClick={async () => {
                                if (isRiconciliata) {
                                  alert('⛔ FATTURA RICONCILIATA: Questa fattura è stata riconciliata con l\'estratto conto bancario e non può essere modificata.');
                                  return;
                                }
                                const importo = f.total_amount || f.importo_totale || 0;
                                const dataDoc = f.invoice_date || f.data_documento;
                                const fornitoreNome = f.supplier_name || f.fornitore_ragione_sociale || 'Fornitore';
                                const numFattura = f.invoice_number || f.numero_documento || '';
                                
                                if (isPaid && metodoPagEffettivo === 'cassa') {
                                  return; // Già in cassa, non fare nulla
                                }
                                
                                if (isPaid && metodoPagEffettivo === 'banca') {
                                  // Sposta da banca a cassa DIRETTAMENTE
                                  try {
                                    await api.post('/api/fatture-ricevute/cambia-metodo-pagamento', {
                                      fattura_id: f.id,
                                      importo: importo,
                                      metodo_vecchio: 'banca',
                                      metodo_nuovo: 'cassa',
                                      data_pagamento: dataDoc,
                                      fornitore: fornitoreNome,
                                      numero_fattura: numFattura
                                    });
                                    fetchFatture();
                                  } catch (error) {
                                    alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
                                  }
                                } else {
                                  // Non pagata - registra nuovo pagamento in cassa (senza conferma)
                                  try {
                                    const scrollPos = window.scrollY;
                                    await api.post('/api/fatture-ricevute/paga-manuale', {
                                      fattura_id: f.id,
                                      importo: importo,
                                      metodo: 'cassa',
                                      data_pagamento: dataDoc,
                                      fornitore: fornitoreNome,
                                      numero_fattura: numFattura
                                    });
                                    await fetchFatture();
                                    setTimeout(() => window.scrollTo(0, scrollPos), 100);
                                  } catch (error) {
                                    alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
                                  }
                                }
                              }}
                              style={{ 
                                padding: '8px 14px', 
                                background: isRiconciliata ? '#e5e7eb' : (isPaid && metodoPagEffettivo === 'cassa') ? '#15803d' : '#f0fdf4',
                                color: isRiconciliata ? '#9ca3af' : (isPaid && metodoPagEffettivo === 'cassa') ? 'white' : '#16a34a',
                                border: isRiconciliata ? 'none' : (isPaid && metodoPagEffettivo === 'cassa') ? 'none' : '2px solid #16a34a', 
                                borderRadius: 6, 
                                cursor: isRiconciliata ? 'not-allowed' : (isPaid && metodoPagEffettivo === 'cassa') ? 'default' : 'pointer',
                                fontSize: 12, 
                                fontWeight: '600',
                                minWidth: 70,
                                transition: 'all 0.2s',
                                opacity: isRiconciliata ? 0.5 : 1
                              }}
                              title={isRiconciliata ? '⛔ Riconciliata - non modificabile' : isPaid && metodoPagEffettivo === 'cassa' ? 'Pagata in Cassa' : isPaid ? 'Sposta in Cassa' : 'Paga in Cassa'}
                              data-testid={`btn-cassa-${f.id}`}
                            >
                              💵 {(isPaid && metodoPagEffettivo === 'cassa') ? '✓' : 'Cassa'}
                            </button>
                            
                            {/* Pulsante Banca - blu se attivo, grigio se non selezionato - PULSANTE GRANDE */}
                            {/* DISABILITATO se riconciliata */}
                            <button
                              disabled={isRiconciliata}
                              onClick={async () => {
                                if (isRiconciliata) {
                                  alert('⛔ FATTURA RICONCILIATA: Questa fattura è stata riconciliata con l\'estratto conto bancario e non può essere modificata.');
                                  return;
                                }
                                const importo = f.total_amount || f.importo_totale || 0;
                                const dataDoc = f.invoice_date || f.data_documento;
                                const fornitoreNome = f.supplier_name || f.fornitore_ragione_sociale || 'Fornitore';
                                const numFattura = f.invoice_number || f.numero_documento || '';
                                
                                if (isPaid && metodoPagEffettivo === 'banca') {
                                  return; // Già in banca, non fare nulla
                                }
                                
                                if (isPaid && metodoPagEffettivo === 'cassa') {
                                  // Sposta da cassa a banca DIRETTAMENTE
                                  try {
                                    await api.post('/api/fatture-ricevute/cambia-metodo-pagamento', {
                                      fattura_id: f.id,
                                      importo: importo,
                                      metodo_vecchio: 'cassa',
                                      metodo_nuovo: 'banca',
                                      data_pagamento: dataDoc,
                                      fornitore: fornitoreNome,
                                      numero_fattura: numFattura
                                    });
                                    fetchFatture();
                                  } catch (error) {
                                    alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
                                  }
                                } else {
                                  // Non pagata - registra nuovo pagamento in banca
                                  try {
                                    await api.post('/api/fatture-ricevute/paga-manuale', {
                                      fattura_id: f.id,
                                      importo: importo,
                                      metodo: 'banca',
                                      data_pagamento: dataDoc,
                                      fornitore: fornitoreNome,
                                      numero_fattura: numFattura
                                    });
                                    fetchFatture();
                                  } catch (error) {
                                    alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
                                  }
                                }
                              }}
                              style={{ 
                                padding: '8px 14px', 
                                background: isRiconciliata ? '#e5e7eb' : (isPaid && metodoPagEffettivo === 'banca') ? '#1535a8' : '#eff6ff',
                                color: isRiconciliata ? '#9ca3af' : (isPaid && metodoPagEffettivo === 'banca') ? 'white' : '#1535a8',
                                border: isRiconciliata ? 'none' : (isPaid && metodoPagEffettivo === 'banca') ? 'none' : '2px solid #1535a8', 
                                borderRadius: 6, 
                                cursor: isRiconciliata ? 'not-allowed' : (isPaid && metodoPagEffettivo === 'banca') ? 'default' : 'pointer',
                                fontSize: 12, 
                                fontWeight: '600',
                                minWidth: 70,
                                transition: 'all 0.2s',
                                opacity: isRiconciliata ? 0.5 : 1
                              }}
                              title={isRiconciliata ? '⛔ Riconciliata - non modificabile' : isPaid && metodoPagEffettivo === 'banca' ? 'Pagata in Banca' : isPaid ? 'Sposta in Banca' : 'Paga in Banca'}
                              data-testid={`btn-banca-${f.id}`}
                            >
                              🏦 {(isPaid && metodoPagEffettivo === 'banca') ? '✓' : 'Banca'}
                            </button>
                          </div>
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* ==================== TAB: IMPORT XML INTEGRATO ==================== */}
      {/* ==================== TAB: SCADENZE ==================== */}
      {activeTab === 'scadenze' && (
        <div style={cardStyle}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>📅</span> Scadenze di Pagamento Aperte
            </h3>
            <span style={styles.badge('#ef4444')}>{dashboard?.scadenze_aperte?.length || 0} scadenze</span>
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
                    <tr key={s.id} style={isScadenzaPassata(s.data_scadenza) ? styles.rowHighlight : {}}>
                      <td style={styles.td}>
                        <strong>{formatDate(s.data_scadenza)}</strong>
                        {isScadenzaPassata(s.data_scadenza) && (
                          <span style={{ ...styles.badge('#ef4444'), marginLeft: 8 }}>Scaduta</span>
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
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', position: 'relative' }}>
                          {s.fattura_id && (
                            <a 
                              style={{ ...styles.button('secondary'), padding: '6px 10px', textDecoration: 'none' }}
                              href={`/api/fatture-ricevute/fattura/${s.fattura_id}/view-assoinvoice`}
                              target="_blank"
                              rel="noopener noreferrer"
                              data-testid={`btn-pdf-scadenza-${s.id}`}
                              title="Visualizza fattura"
                            >
                              📄
                            </a>
                          )}
                          
                          {/* Menu Paga Manuale */}
                          <div style={{ position: 'relative' }}>
                            <button 
                              style={{
                                ...styles.button('primary'),
                                background: payingScadenza === s.id ? '#9ca3af' : '#15803d',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4
                              }}
                              onClick={() => setShowPayMenu(showPayMenu === s.id ? null : s.id)}
                              disabled={payingScadenza === s.id}
                              data-testid={`btn-paga-${s.id}`}
                            >
                              {payingScadenza === s.id ? '⏳' : '💳'} Paga ▼
                            </button>
                            
                            {/* Dropdown Menu */}
                            {showPayMenu === s.id && (
                              <div style={{
                                position: 'absolute',
                                top: '100%',
                                left: 0,
                                marginTop: 4,
                                background: 'white',
                                borderRadius: 8,
                                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                                border: '1px solid #e2e8f0',
                                zIndex: 100,
                                minWidth: 140,
                                overflow: 'hidden'
                              }}>
                                <button
                                  onClick={() => handlePayManual(s, 'cassa')}
                                  style={{
                                    width: '100%',
                                    padding: '10px 14px',
                                    border: 'none',
                                    background: 'white',
                                    cursor: 'pointer',
                                    textAlign: 'left',
                                    fontSize: 13,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 8,
                                    borderBottom: '1px solid #f1f5f9'
                                  }}
                                  onMouseOver={(e) => e.target.style.background = '#f0fdf4'}
                                  onMouseOut={(e) => e.target.style.background = 'white'}
                                >
                                  💵 Paga con CASSA
                                </button>
                                <button
                                  onClick={() => handlePayManual(s, 'banca')}
                                  style={{
                                    width: '100%',
                                    padding: '10px 14px',
                                    border: 'none',
                                    background: 'white',
                                    cursor: 'pointer',
                                    textAlign: 'left',
                                    fontSize: 13,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 8
                                  }}
                                  onMouseOver={(e) => e.target.style.background = '#dbeafe'}
                                  onMouseOut={(e) => e.target.style.background = 'white'}
                                >
                                  🏦 Paga con BANCA
                                </button>
                              </div>
                            )}
                          </div>
                          
                          <button 
                            style={styles.button('primary')}
                            onClick={() => {
                              setActiveTab('riconciliazione');
                              setSearchParams(prev => { prev.set('tab', 'riconciliazione'); return prev; });
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
                <div style={{ fontSize: 48, marginBottom: 16 }}>🎉</div>
                <p>Nessuna scadenza aperta</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ==================== TAB: RICONCILIAZIONE ==================== */}
      {activeTab === 'riconciliazione' && (
        <div style={styles.splitView}>
          {/* Colonna Sinistra: Scadenze */}
          <div style={cardStyle}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>📋</span> Scadenze da Riconciliare
              </h3>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: 600 }}>
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
                          <span style={{ fontSize: 12, color: '#64748b' }}>{s.numero_fattura}</span>
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
          <div style={cardStyle}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>🏦</span> Movimenti Bancari Suggeriti
              </h3>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: 600 }}>
              {selectedScadenza ? (
                <>
                  <div style={{ padding: 16, background: '#eff6ff', borderBottom: '1px solid #e2e8f0' }}>
                    <strong>Scadenza selezionata:</strong> {selectedScadenza.fornitore_nome} - {formatEuro(selectedScadenza.importo_totale)}
                    <br />
                    <span style={{ fontSize: 13, color: '#64748b' }}>Fatt. {selectedScadenza.numero_fattura} - Scade {formatDate(selectedScadenza.data_scadenza)}</span>
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
                              <span style={{ fontSize: 13 }}>{m.descrizione || m.causale || '-'}</span>
                            </td>
                            <td style={styles.td}>
                              <strong>{formatEuro(m.importo)}</strong>
                              {m.diff_importo > 0 && (
                                <span style={{ fontSize: 11, color: '#d97706', display: 'block' }}>
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
                      <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
                      <p>Nessun movimento bancario compatibile trovato</p>
                      <p style={{ fontSize: 13, marginTop: 8 }}>Verifica che i movimenti bancari siano stati importati</p>
                    </div>
                  )}
                </>
              ) : (
                <div style={styles.emptyState}>
                  <div style={{ fontSize: 48, marginBottom: 16 }}>👈</div>
                  <p>Seleziona una scadenza dalla lista a sinistra</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ==================== TAB: STORICO ==================== */}
      {activeTab === 'storico' && (
        <div style={cardStyle}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>✅</span> Storico Pagamenti Effettuati
            </h3>
            <span style={styles.badge('#15803d')}>{dashboard?.scadenze_saldate?.length || 0} pagamenti</span>
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
                <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
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
