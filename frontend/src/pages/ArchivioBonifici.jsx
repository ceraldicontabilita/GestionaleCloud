import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

const formatDate = formatDateIT; // Alias per retrocompatibilità

export default function ArchivioBonifici() {
  const { anno } = useAnnoGlobale();
  const [transfers, setTransfers] = useState([]);
  const [summary, setSummary] = useState({});
  const [count, setCount] = useState(0);
  const [search, setSearch] = useState('');
  const [yearFilter, setYearFilter] = useState('');
  const [ordinanteFilter, setOrdinanteFilter] = useState('');
  const [beneficiarioFilter, setBeneficiarioFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [riconciliazioneStats, setRiconciliazioneStats] = useState(null);
  const [riconciliando, setRiconciliando] = useState(false);
  const [editingNote, setEditingNote] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [associaDropdown, setAssociaDropdown] = useState(null); // ID bonifico con dropdown aperto
  const [operazioniCompatibili, setOperazioniCompatibili] = useState([]);
  const [loadingOperazioni, setLoadingOperazioni] = useState(false);
  const [fattureCompatibili, setFattureCompatibili] = useState([]);
  const [associaFatturaDropdown, setAssociaFatturaDropdown] = useState(null);
  const [loadingFatture, setLoadingFatture] = useState(false);
  const [dipendenteIbanMatch, setDipendenteIbanMatch] = useState(null);
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/archivio-bonifici\/([\w-]+)/);
    return match ? match[1] : 'da_associare';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/archivio-bonifici/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]); // 'da_associare' | 'associati'
  const initialized = useRef(false);
  const dropdownRef = useRef(null);

  // Chiudi dropdown quando si clicca fuori
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        // Chiudi tutti i dropdown
        setAssociaDropdown(null);
        setAssociaFatturaDropdown(null);
        setOperazioniCompatibili([]);
        setFattureCompatibili([]);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Carica dati iniziali
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    
    loadTransfers();
    loadSummary();
    loadCount();
    loadRiconciliazioneStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Ricarica quando cambiano i filtri
  useEffect(() => {
    if (!initialized.current) return;
    const timer = setTimeout(() => {
      loadTransfers();
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, yearFilter, ordinanteFilter, beneficiarioFilter]);

  const loadTransfers = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (yearFilter) params.append('year', yearFilter);
      if (ordinanteFilter) params.append('ordinante', ordinanteFilter);
      if (beneficiarioFilter) params.append('beneficiario', beneficiarioFilter);
      
      const res = await api.get(`/api/archivio-bonifici/transfers?${params.toString()}`);
      setTransfers(res.data || []);
    } catch (error) {
      console.error('Error loading transfers:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    try {
      const res = await api.get(`/api/archivio-bonifici/transfers/summary?anno=${anno}`);
      setSummary(res.data || {});
    } catch (error) {
      console.error('Error loading summary:', error);
    }
  };

  const loadCount = async () => {
    try {
      const res = await api.get(`/api/archivio-bonifici/transfers/count?anno=${anno}`);
      setCount(res.data?.count || 0);
    } catch (error) {
      console.error('Error loading count:', error);
    }
  };

  const loadRiconciliazioneStats = async () => {
    try {
      const res = await api.get(`/api/archivio-bonifici/stato-riconciliazione?anno=${anno}`);
      setRiconciliazioneStats(res.data);
    } catch (error) {
      console.error('Error loading riconciliazione stats:', error);
    }
  };

  const handleRiconcilia = async () => {
    
    
    setRiconciliando(true);
    try {
      // Avvia in background
      const res = await api.post('/api/archivio-bonifici/riconcilia?background=true');
      
      if (res.data.background && res.data.task_id) {
        // Poll per lo stato
        const taskId = res.data.task_id;
        let attempts = 0;
        const maxAttempts = 60; // 2 minuti max
        
        const pollStatus = async () => {
          try {
            const statusRes = await api.get(`/api/archivio-bonifici/riconcilia/task/${taskId}`);
            
            if (statusRes.data.status === 'completed') {
              const result = statusRes.data.result;
              alert(`✅ Riconciliazione completata!\n\nRiconciliati: ${result.riconciliati}\nNon trovati: ${result.non_riconciliati}`);
              await Promise.all([loadTransfers(), loadRiconciliazioneStats()]);
              setRiconciliando(false);
            } else if (statusRes.data.status === 'error') {
              alert(`❌ Errore: ${statusRes.data.error}`);
              setRiconciliando(false);
            } else if (attempts < maxAttempts) {
              attempts++;
              setTimeout(pollStatus, 2000);
            } else {
              alert('⚠️ Timeout raggiunto. Verifica lo stato manualmente.');
              setRiconciliando(false);
            }
          } catch (e) {
            console.error('Poll error:', e);
            setRiconciliando(false);
          }
        };
        
        setTimeout(pollStatus, 1000);
      } else {
        // Fallback sincrono
        alert(`✅ ${res.data.message}\n\nRiconciliati: ${res.data.riconciliati}\nNon trovati: ${res.data.non_riconciliati}`);
        await Promise.all([loadTransfers(), loadRiconciliazioneStats()]);
        setRiconciliando(false);
      }
    } catch (error) {
      alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
      setRiconciliando(false);
    }
  };

  // Elimina bonifico
  const handleDelete = async (id) => {
    
    try {
      await api.delete(`/api/archivio-bonifici/transfers/${id}`);
      loadTransfers();
      loadCount();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Export
  const handleExport = (format) => {
    const baseUrl = window.location.origin;
    window.open(`${baseUrl}/api/archivio-bonifici/export?format=${format}`, '_blank');
  };

  // Download ZIP per anno
  const handleDownloadZip = async (year) => {
    setDownloadingZip(true);
    try {
      const baseUrl = window.location.origin;
      window.open(`${baseUrl}/api/archivio-bonifici/download-zip/${year}`, '_blank');
    } catch (error) {
      alert('Errore download: ' + error.message);
    } finally {
      setTimeout(() => setDownloadingZip(false), 2000);
    }
  };

  // Salva nota bonifico
  const handleSaveNote = async (id) => {
    try {
      await api.put(`/api/archivio-bonifici/transfers/${id}`, { note: noteText });
      setEditingNote(null);
      setNoteText('');
      loadTransfers();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Sincronizza IBAN dai bonifici all'anagrafica dipendenti
  const handleSyncIbanToAnagrafica = async () => {
    
    try {
      const res = await api.post('/api/archivio-bonifici/sync-iban-anagrafica');
      alert(`✅ Sincronizzazione completata!\n\nDipendenti aggiornati: ${res.data.dipendenti_aggiornati}\nBonifici analizzati: ${res.data.totale_bonifici_analizzati}`);
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Carica operazioni salari compatibili per associazione
  const loadOperazioniCompatibili = async (bonifico_id) => {
    setLoadingOperazioni(true);
    setDipendenteIbanMatch(null);
    try {
      const res = await api.get(`/api/archivio-bonifici/operazioni-salari/${bonifico_id}`);
      setOperazioniCompatibili(res.data.operazioni_compatibili || []);
      // Salva info dipendente trovato per IBAN
      if (res.data.dipendente_iban_match) {
        setDipendenteIbanMatch(res.data.dipendente_iban_match);
      }
    } catch (error) {
      console.error('Errore caricamento operazioni:', error);
      setOperazioniCompatibili([]);
    }
    setLoadingOperazioni(false);
  };

  // Toggle dropdown associazione SALARI
  const toggleAssociaDropdown = (bonifico_id) => {
    // Chiudi dropdown fatture se aperto
    setAssociaFatturaDropdown(null);
    setFattureCompatibili([]);
    
    if (associaDropdown === bonifico_id) {
      setAssociaDropdown(null);
      setOperazioniCompatibili([]);
      setDipendenteIbanMatch(null);
    } else {
      setAssociaDropdown(bonifico_id);
      loadOperazioniCompatibili(bonifico_id);
    }
  };

  // Associa bonifico a operazione salari
  const handleAssocia = async (bonifico_id, operazione_id) => {
    try {
      await api.post(`/api/archivio-bonifici/associa-salario?bonifico_id=${bonifico_id}&operazione_id=${operazione_id}`);
      setAssociaDropdown(null);
      setOperazioniCompatibili([]);
      loadTransfers();
    } catch (error) {
      alert('Errore associazione: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Disassocia bonifico da salario (DOPPIA CONFERMA)
  const handleDisassocia = async (bonifico_id, dipendente_nome) => {
    const msg1 = `Rimuovere associazione con "${dipendente_nome || 'salario'}"?`;
    
    
    // Seconda conferma
    const msg2 = `⚠️ CONFERMA RIMOZIONE\n\nQuesta azione rimuoverà l'associazione tra il bonifico e il salario.\n\nSei sicuro di voler procedere?`;
    
    
    try {
      await api.delete(`/api/archivio-bonifici/disassocia-salario/${bonifico_id}`);
      loadTransfers();
    } catch (error) {
      alert('Errore: ' + error.message);
    }
  };

  // === NUOVE FUNZIONI PER FATTURE ===
  const loadFattureCompatibili = async (bonifico_id) => {
    setLoadingFatture(true);
    try {
      const res = await api.get(`/api/archivio-bonifici/fatture-compatibili/${bonifico_id}`);
      setFattureCompatibili(res.data.fatture_compatibili || []);
    } catch (error) {
      console.error('Errore caricamento fatture:', error);
      setFattureCompatibili([]);
    }
    setLoadingFatture(false);
  };

  const toggleAssociaFatturaDropdown = (bonifico_id) => {
    // Chiudi dropdown salari se aperto
    setAssociaDropdown(null);
    setOperazioniCompatibili([]);
    
    if (associaFatturaDropdown === bonifico_id) {
      setAssociaFatturaDropdown(null);
      setFattureCompatibili([]);
    } else {
      setAssociaFatturaDropdown(bonifico_id);
      loadFattureCompatibili(bonifico_id);
    }
  };

  const handleAssociaFattura = async (bonifico_id, fattura_id, collection) => {
    try {
      await api.post(`/api/archivio-bonifici/associa-fattura?bonifico_id=${bonifico_id}&fattura_id=${fattura_id}&collection=${collection}`);
      setAssociaFatturaDropdown(null);
      setFattureCompatibili([]);
      loadTransfers();
    } catch (error) {
      alert('Errore associazione fattura: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDisassociaFattura = async (bonifico_id, fattura_numero) => {
    const msg1 = `Rimuovere associazione con fattura "${fattura_numero || 'N/D'}"?`;
    
    
    // Seconda conferma
    const msg2 = `⚠️ CONFERMA RIMOZIONE\n\nQuesta azione rimuoverà l'associazione tra il bonifico e la fattura.\n\nSei sicuro di voler procedere?`;
    
    
    try {
      await api.delete(`/api/archivio-bonifici/disassocia-fattura/${bonifico_id}`);
      loadTransfers();
    } catch (error) {
      alert('Errore: ' + error.message);
    }
  };

  // Calcola totali e filtra per tab
  const totaleImporto = transfers.reduce((sum, t) => sum + (t.importo || 0), 0);
  
  // Separa bonifici associati da non associati
  const bonificiDaAssociare = transfers.filter(t => !t.salario_associato && !t.fattura_associata);
  const bonificiAssociati = transfers.filter(t => t.salario_associato || t.fattura_associata);
  
  // Dati da mostrare in base al tab
  const transfersToShow = activeTab === 'da_associare' ? bonificiDaAssociare : bonificiAssociati;

  return (
    <PageLayout title="Archivio Bonifici Bancari" subtitle="Visualizzazione e gestione bonifici bancari">
    <div style={{ maxWidth: 1400, margin: '0 auto' }} ref={dropdownRef}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 'bold', color: '#1535a8', marginBottom: 8 }}>
            📂 Archivio Bonifici Bancari
          </h1>
          <p style={{ color: '#64748b', margin: 0 }}>
            Visualizzazione e gestione bonifici bancari
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <a 
            href="/import-export"
            style={{ 
              padding: "10px 20px",
              background: "#1535a8",
              color: "white",
              fontWeight: "bold",
              borderRadius: 8,
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 6
            }}
          >
            📥 Importa Bonifici
          </a>
          <button
            onClick={handleSyncIbanToAnagrafica}
            style={{
              padding: "10px 20px",
              background: "#15803d",
              color: "white",
              fontWeight: "bold",
              border: "none",
              borderRadius: 8,
              cursor: "pointer"
            }}
            title="Sincronizza gli IBAN dei bonifici nell'anagrafica dipendenti"
          >
            🏦 Sync IBAN → Anagrafica
          </button>
          <button
            onClick={() => { loadTransfers(); loadSummary(); loadCount(); }}
            style={{
              padding: "10px 20px",
              background: "#f5f5f5",
              color: "#333",
              border: "1px solid #ddd",
              borderRadius: 8,
              cursor: "pointer"
            }}
          >
            🔄 Aggiorna
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 24 }}>
        <div style={{ background: '#f0f9ff', padding: 20, borderRadius: 12, border: '1px solid #bae6fd' }}>
          <div style={{ fontSize: 13, color: '#0369a1' }}>Bonifici Totali in DB</div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: '#0c4a6e' }}>{count}</div>
        </div>
        <div style={{ background: '#f0fdf4', padding: 20, borderRadius: 12, border: '1px solid #bbf7d0' }}>
          <div style={{ fontSize: 13, color: '#16a34a' }}>Bonifici Filtrati</div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: '#166534' }}>{transfers.length}</div>
        </div>
        <div style={{ background: '#fefce8', padding: 20, borderRadius: 12, border: '1px solid #fef08a' }}>
          <div style={{ fontSize: 13, color: '#ca8a04' }}>Totale Importi Filtrati</div>
          <div style={{ fontSize: 24, fontWeight: 'bold', color: '#854d0e' }}>{formatEuro(totaleImporto)}</div>
        </div>
        {/* Card Riconciliazione */}
        <div style={{ background: riconciliazioneStats?.riconciliati > 0 ? '#f0fdf4' : '#fef2f2', padding: 20, borderRadius: 12, border: `1px solid ${riconciliazioneStats?.riconciliati > 0 ? '#bbf7d0' : '#fecaca'}` }}>
          <div style={{ fontSize: 13, color: riconciliazioneStats?.riconciliati > 0 ? '#16a34a' : '#dc2626' }}>
            ✓ Riconciliati
          </div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: riconciliazioneStats?.riconciliati > 0 ? '#166534' : '#991b1b' }}>
            {riconciliazioneStats?.riconciliati || 0}/{riconciliazioneStats?.totale || 0}
          </div>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
            {riconciliazioneStats?.percentuale || 0}%
          </div>
        </div>
      </div>

      {/* Pulsante Riconciliazione */}
      <div style={{ 
        background: 'linear-gradient(135deg, #0ea5e9, #0369a1)', 
        padding: 16, 
        borderRadius: 12, 
        marginBottom: 24,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        color: 'white'
      }}>
        <div>
          <div style={{ fontWeight: 'bold', fontSize: 16 }}>🔗 Riconciliazione con Estratto Conto</div>
          <div style={{ fontSize: 13, opacity: 0.9 }}>
            Confronta i bonifici con i movimenti bancari per verificare i pagamenti effettivi
          </div>
        </div>
        <button
          onClick={handleRiconcilia}
          disabled={riconciliando}
          style={{
            padding: '12px 24px',
            borderRadius: 8,
            background: riconciliando ? '#94a3b8' : 'white',
            color: '#0369a1',
            border: 'none',
            cursor: riconciliando ? 'not-allowed' : 'pointer',
            fontWeight: 'bold',
            fontSize: 14
          }}
          data-testid="riconcilia-bonifici-btn"
        >
          {riconciliando ? '⏳ Riconciliazione in corso...' : '🚀 Avvia Riconciliazione'}
        </button>
      </div>

      {/* Riepilogo per Anno con Download ZIP */}
      {Object.keys(summary).length > 0 && (
        <div style={{ background: '#f8fafc', padding: 16, borderRadius: 12, marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 'bold', marginBottom: 12, color: '#475569' }}>📊 Riepilogo per Anno (clicca per scaricare ZIP)</h3>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {Object.entries(summary).sort(([a], [b]) => b.localeCompare(a)).map(([year, data]) => (
              <div 
                key={year} 
                style={{ 
                  background: 'white', 
                  padding: '8px 16px', 
                  borderRadius: 8,
                  border: '1px solid #e2e8f0',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onClick={() => handleDownloadZip(year)}
                onMouseOver={(e) => e.currentTarget.style.borderColor = '#1535a8'}
                onMouseOut={(e) => e.currentTarget.style.borderColor = '#e2e8f0'}
              >
                <div style={{ fontWeight: 'bold', color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
                  {year}
                  <span style={{ fontSize: 12, color: '#1535a8' }}>📥</span>
                </div>
                <div style={{ fontSize: 12, color: '#64748b' }}>{data.count} bonifici • {formatEuro(data.total)}</div>
              </div>
            ))}
          </div>
          {downloadingZip && <div style={{ marginTop: 8, fontSize: 12, color: '#1535a8' }}>⏳ Preparazione ZIP in corso...</div>}
        </div>
      )}

      {/* Filters */}
      <div style={{ 
        background: 'white', 
        padding: 16, 
        borderRadius: 12, 
        border: '1px solid #e2e8f0',
        marginBottom: 24,
        display: 'flex',
        gap: 12,
        flexWrap: 'wrap',
        alignItems: 'center'
      }}>
        <input
          type="text"
          placeholder="🔍 Cerca causale, CRO/TRN..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') loadTransfers(); }}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', minWidth: 200 }}
          data-testid="bonifici-search"
        />
        <button
          onClick={loadTransfers}
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            background: '#1535a8',
            color: 'white',
            border: 'none',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 'bold'
          }}
          data-testid="bonifici-search-btn"
        >
          🔍 Cerca
        </button>
        <input
          type="text"
          placeholder="Filtra ordinante..."
          value={ordinanteFilter}
          onChange={(e) => setOrdinanteFilter(e.target.value)}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', minWidth: 150 }}
        />
        <input
          type="text"
          placeholder="Filtra beneficiario..."
          value={beneficiarioFilter}
          onChange={(e) => setBeneficiarioFilter(e.target.value)}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', minWidth: 150 }}
        />
        <input
          type="text"
          placeholder="Anno (es. 2024)"
          value={yearFilter}
          onChange={(e) => setYearFilter(e.target.value)}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', width: 120 }}
        />
        {/* Bottone Reset Filtri */}
        {(search || ordinanteFilter || beneficiarioFilter || yearFilter) && (
          <button
            onClick={() => {
              setSearch('');
              setOrdinanteFilter('');
              setBeneficiarioFilter('');
              setYearFilter('');
            }}
            style={{
              padding: '8px 12px',
              borderRadius: 8,
              background: '#f1f5f9',
              color: '#64748b',
              border: '1px solid #e2e8f0',
              cursor: 'pointer',
              fontSize: 12
            }}
          >
            ✕ Reset
          </button>
        )}
        
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button
            onClick={() => handleExport('xlsx')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              background: '#16a34a',
              color: 'white',
              border: 'none',
              cursor: 'pointer',
              fontSize: 13
            }}
          >
            📥 Export XLSX
          </button>
          <button
            onClick={() => handleExport('csv')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              background: '#64748b',
              color: 'white',
              border: 'none',
              cursor: 'pointer',
              fontSize: 13
            }}
          >
            📥 Export CSV
          </button>
        </div>
      </div>

      {/* TABS */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 0 }}>
        <button
          onClick={() => handleTabChange('da_associare')}
          style={{
            padding: '12px 24px',
            background: activeTab === 'da_associare' ? '#1535a8' : '#f1f5f9',
            color: activeTab === 'da_associare' ? 'white' : '#475569',
            border: 'none',
            borderRadius: '8px 8px 0 0',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
          data-testid="tab-da-associare"
        >
          📋 Da Associare
          <span style={{
            background: activeTab === 'da_associare' ? 'rgba(255,255,255,0.2)' : '#e2e8f0',
            padding: '2px 8px',
            borderRadius: 10,
            fontSize: 12
          }}>
            {bonificiDaAssociare.length}
          </span>
        </button>
        <button
          onClick={() => handleTabChange('associati')}
          style={{
            padding: '12px 24px',
            background: activeTab === 'associati' ? '#16a34a' : '#f1f5f9',
            color: activeTab === 'associati' ? 'white' : '#475569',
            border: 'none',
            borderRadius: '8px 8px 0 0',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginLeft: 4
          }}
          data-testid="tab-associati"
        >
          ✅ Associati
          <span style={{
            background: activeTab === 'associati' ? 'rgba(255,255,255,0.2)' : '#dcfce7',
            color: activeTab === 'associati' ? 'white' : '#16a34a',
            padding: '2px 8px',
            borderRadius: 10,
            fontSize: 12
          }}>
            {bonificiAssociati.length}
          </span>
        </button>
      </div>

      {/* Table */}
      <div style={{ 
        background: 'white', 
        borderRadius: '0 12px 12px 12px', 
        border: '1px solid #e2e8f0',
        overflow: 'hidden'
      }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>⏳ Caricamento...</div>
        ) : transfersToShow.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
            {activeTab === 'da_associare' 
              ? '🎉 Tutti i bonifici sono stati associati!' 
              : 'Nessun bonifico associato. Seleziona il tab "Da Associare" per iniziare.'}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1400, fontSize: 12 }}>
              <thead>
                <tr style={{ background: activeTab === 'associati' ? '#16a34a' : '#1535a8', color: 'white' }}>
                  <th style={{ padding: 8, textAlign: 'center', width: 40 }}>✓</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>Data</th>
                  <th style={{ padding: 8, textAlign: 'right' }}>Importo</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>Beneficiario</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>Causale</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>CRO/TRN</th>
                  <th style={{ padding: 8, textAlign: 'left', width: 180 }}>{activeTab === 'associati' ? 'Salario Associato' : 'Associa Salario'}</th>
                  <th style={{ padding: 8, textAlign: 'left', width: 180 }}>{activeTab === 'associati' ? 'Fattura Associata' : 'Associa Fattura'}</th>
                  <th style={{ padding: 8, textAlign: 'left', width: 100 }}>Note</th>
                  <th style={{ padding: 8, textAlign: 'center', width: 50 }}>🗑️</th>
                </tr>
              </thead>
              <tbody>
                {transfersToShow.map((t, idx) => (
                  <tr key={t.id || idx} style={{ borderBottom: '1px solid #f1f5f9', background: t.riconciliato ? '#f0fdf4' : 'white' }}>
                    <td style={{ padding: 8, textAlign: 'center' }}>
                      {t.riconciliato ? (
                        <span style={{ color: '#16a34a', fontSize: 16 }} title={`Riconciliato: ${t.movimento_descrizione || 'Trovato in estratto conto'}`}>✅</span>
                      ) : (
                        <span style={{ color: '#d1d5db', fontSize: 14 }}>○</span>
                      )}
                    </td>
                    <td style={{ padding: 8, whiteSpace: 'nowrap' }}>{formatDate(t.data)}</td>
                    <td style={{ padding: 8, textAlign: 'right', fontWeight: 'bold', color: '#16a34a', whiteSpace: 'nowrap' }}>
                      {formatEuro(t.importo)}
                    </td>
                    <td style={{ padding: 8 }}>{t.beneficiario?.nome || '-'}</td>
                    <td style={{ padding: 8, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.causale}>
                      {t.causale || '-'}
                    </td>
                    <td style={{ padding: 8, fontSize: 10 }}>{t.cro_trn || '-'}</td>
                    {/* Colonna Associa a Salario */}
                    <td style={{ padding: 8, position: 'relative' }}>
                      {t.salario_associato ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ 
                            background: '#dcfce7', 
                            color: '#16a34a', 
                            padding: '4px 8px', 
                            borderRadius: 6, 
                            fontSize: 10,
                            fontWeight: 500
                          }}>
                            ✓ {t.operazione_salario_desc?.substring(0, 20) || 'Associato'}
                          </span>
                          <button
                            onClick={() => handleDisassocia(t.id, t.operazione_salario_desc)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 10, color: '#dc2626' }}
                            title="Rimuovi associazione (doppia conferma)"
                          >
                            ✗
                          </button>
                        </div>
                      ) : (
                        <div>
                          <button
                            onClick={() => toggleAssociaDropdown(t.id)}
                            style={{
                              padding: '4px 10px',
                              background: associaDropdown === t.id ? '#1535a8' : '#f1f5f9',
                              color: associaDropdown === t.id ? 'white' : '#475569',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              fontSize: 11,
                              fontWeight: 500
                            }}
                            data-testid={`btn-associa-${t.id}`}
                          >
                            {associaDropdown === t.id ? '▼ Seleziona' : '+ Associa'}
                          </button>
                          {/* Dropdown operazioni */}
                          {associaDropdown === t.id && (
                            <div style={{
                              position: 'absolute',
                              top: '100%',
                              left: 0,
                              zIndex: 100,
                              background: 'white',
                              border: '1px solid #e2e8f0',
                              borderRadius: 8,
                              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                              minWidth: 300,
                              maxHeight: 250,
                              overflowY: 'auto'
                            }}>
                              {/* Banner IBAN Match */}
                              {dipendenteIbanMatch && !loadingOperazioni && (
                                <div style={{ 
                                  background: '#ecfdf5', 
                                  borderBottom: '2px solid #16a34a', 
                                  padding: '8px 12px',
                                  fontSize: 10
                                }}>
                                  <div style={{ fontWeight: 600, color: '#16a34a' }}>
                                    🔗 IBAN riconosciuto
                                  </div>
                                  <div style={{ color: '#166534', marginTop: 2 }}>
                                    Dipendente: <strong>{dipendenteIbanMatch.nome_display}</strong>
                                  </div>
                                </div>
                              )}
                              {loadingOperazioni ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
                              ) : operazioniCompatibili.length === 0 ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#6b7280', fontSize: 11 }}>
                                  {dipendenteIbanMatch 
                                    ? `Nessuna operazione in Prima Nota Salari per ${dipendenteIbanMatch.nome_display}` 
                                    : 'Nessuna operazione salari compatibile trovata'}
                                </div>
                              ) : (
                                operazioniCompatibili.map((op, idx) => (
                                  <div
                                    key={op.id || idx}
                                    onClick={() => handleAssocia(t.id, op.id)}
                                    style={{
                                      padding: '10px 12px',
                                      borderBottom: '1px solid #f1f5f9',
                                      cursor: 'pointer',
                                      transition: 'background 0.1s',
                                      background: op.iban_match ? '#ecfdf5' : 'white'
                                    }}
                                    onMouseOver={(e) => e.currentTarget.style.background = op.iban_match ? '#dcfce7' : '#f0f9ff'}
                                    onMouseOut={(e) => e.currentTarget.style.background = op.iban_match ? '#ecfdf5' : 'white'}
                                  >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                      <span style={{ fontWeight: 500, fontSize: 11 }}>
                                        {op.iban_match && <span style={{ color: '#16a34a', marginRight: 4 }}>🔗</span>}
                                        {op.dipendente || op.descrizione || 'Operazione'}
                                      </span>
                                      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                                        {op.iban_match && (
                                          <span style={{ 
                                            background: '#16a34a', 
                                            color: 'white', 
                                            padding: '2px 6px', 
                                            borderRadius: 4, 
                                            fontSize: 8, 
                                            fontWeight: 600 
                                          }}>
                                            IBAN ✓
                                          </span>
                                        )}
                                        <span style={{ 
                                          background: op.compatibilita_score >= 70 ? '#dcfce7' : op.compatibilita_score >= 40 ? '#fef3c7' : '#fee2e2',
                                          color: op.compatibilita_score >= 70 ? '#16a34a' : op.compatibilita_score >= 40 ? '#d97706' : '#dc2626',
                                          padding: '2px 6px',
                                          borderRadius: 4,
                                          fontSize: 9,
                                          fontWeight: 600
                                        }}>
                                          {op.compatibilita_score}%
                                        </span>
                                      </div>
                                    </div>
                                    <div style={{ fontSize: 10, color: '#6b7280', marginTop: 4, display: 'flex', justifyContent: 'space-between' }}>
                                      <span>{op.anno && op.mese ? `${op.mese}/${op.anno}` : formatDate(op.data)}</span>
                                      <span style={{ fontWeight: 600 }}>{formatEuro(op.importo_display)}</span>
                                    </div>
                                  </div>
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    {/* NUOVA COLONNA: Associa a Fattura */}
                    <td style={{ padding: 8, position: 'relative' }}>
                      {t.fattura_associata ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ 
                            background: '#dbeafe', 
                            color: '#1d4ed8', 
                            padding: '4px 8px', 
                            borderRadius: 6, 
                            fontSize: 10,
                            fontWeight: 500
                          }}>
                            📄 {t.fattura_numero?.substring(0, 15) || 'Associata'}
                          </span>
                          <button
                            onClick={() => handleDisassociaFattura(t.id, t.fattura_numero)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 10, color: '#dc2626' }}
                            title="Rimuovi associazione (doppia conferma)"
                          >
                            ✗
                          </button>
                        </div>
                      ) : (
                        <div>
                          <button
                            onClick={() => toggleAssociaFatturaDropdown(t.id)}
                            style={{
                              padding: '4px 10px',
                              background: associaFatturaDropdown === t.id ? '#1d4ed8' : '#f1f5f9',
                              color: associaFatturaDropdown === t.id ? 'white' : '#475569',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              fontSize: 11,
                              fontWeight: 500
                            }}
                            data-testid={`btn-associa-fattura-${t.id}`}
                          >
                            {associaFatturaDropdown === t.id ? '▼ Scegli' : '📄 Fattura'}
                          </button>
                          {/* Dropdown fatture */}
                          {associaFatturaDropdown === t.id && (
                            <div style={{
                              position: 'absolute',
                              top: '100%',
                              left: 0,
                              zIndex: 100,
                              background: 'white',
                              border: '1px solid #e2e8f0',
                              borderRadius: 8,
                              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                              minWidth: 300,
                              maxHeight: 250,
                              overflowY: 'auto'
                            }}>
                              {loadingFatture ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
                              ) : fattureCompatibili.length === 0 ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#6b7280', fontSize: 11 }}>
                                  Nessuna fattura compatibile trovata
                                </div>
                              ) : (
                                fattureCompatibili.map((f, idx) => (
                                  <div
                                    key={f.id || idx}
                                    onClick={() => handleAssociaFattura(t.id, f.id, f.collection)}
                                    style={{
                                      padding: '10px 12px',
                                      borderBottom: '1px solid #f1f5f9',
                                      cursor: 'pointer',
                                      transition: 'background 0.1s'
                                    }}
                                    onMouseOver={(e) => e.currentTarget.style.background = '#eff6ff'}
                                    onMouseOut={(e) => e.currentTarget.style.background = 'white'}
                                  >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                      <span style={{ fontWeight: 500, fontSize: 11 }}>
                                        {f.numero_fattura || 'N/A'} - {f.fornitore?.substring(0, 20) || ''}
                                      </span>
                                      <span style={{ 
                                        background: f.compatibilita_score >= 70 ? '#dcfce7' : f.compatibilita_score >= 40 ? '#fef3c7' : '#fee2e2',
                                        color: f.compatibilita_score >= 70 ? '#16a34a' : f.compatibilita_score >= 40 ? '#d97706' : '#dc2626',
                                        padding: '2px 6px',
                                        borderRadius: 4,
                                        fontSize: 9,
                                        fontWeight: 600
                                      }}>
                                        {f.compatibilita_score}%
                                      </span>
                                    </div>
                                    <div style={{ fontSize: 10, color: '#6b7280', marginTop: 4 }}>
                                      {formatDate(f.data_fattura)} • {formatEuro(f.importo)}
                                    </div>
                                  </div>
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 8 }}>
                      {editingNote === t.id ? (
                        <div style={{ display: 'flex', gap: 4 }}>
                          <input
                            type="text"
                            value={noteText}
                            onChange={(e) => setNoteText(e.target.value)}
                            style={{ padding: 4, borderRadius: 4, border: '1px solid #e2e8f0', fontSize: 11, width: 80 }}
                            autoFocus
                          />
                          <button onClick={() => handleSaveNote(t.id)} style={{ padding: '2px 6px', background: '#16a34a', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 10 }}>✓</button>
                          <button onClick={() => { setEditingNote(null); setNoteText(''); }} style={{ padding: '2px 6px', background: '#94a3b8', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 10 }}>✗</button>
                        </div>
                      ) : (
                        <div 
                          onClick={() => { setEditingNote(t.id); setNoteText(t.note || ''); }}
                          style={{ cursor: 'pointer', color: t.note ? '#1535a8' : '#94a3b8', fontSize: 11 }}
                          title="Clicca per modificare"
                        >
                          {t.note || '+ Nota'}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 8, textAlign: 'center' }}>
                      <button
                        onClick={() => handleDelete(t.id)}
                        style={{ 
                          background: 'none', 
                          border: 'none', 
                          cursor: 'pointer', 
                          fontSize: 14,
                          opacity: 0.6
                        }}
                        title="Elimina"
                      >
                        🗑️
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
    </PageLayout>
  );
}
