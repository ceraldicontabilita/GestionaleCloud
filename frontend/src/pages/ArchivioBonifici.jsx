import React, { useState, useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { useConfirm } from '../components/ui/ConfirmDialog';
import ModalFattura from '../components/ModalFattura';
import { toast } from 'sonner';

const formatDate = formatDateIT;

export default function ArchivioBonifici() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
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
  const [associaDropdown, setAssociaDropdown] = useState(null);
  const [operazioniCompatibili, setOperazioniCompatibili] = useState([]);
  const [loadingOperazioni, setLoadingOperazioni] = useState(false);
  const [fattureCompatibili, setFattureCompatibili] = useState([]);
  const [associaFatturaDropdown, setAssociaFatturaDropdown] = useState(null);
  const [loadingFatture, setLoadingFatture] = useState(false);
  const [fatturaView, setFatturaView] = useState(null);
  const [dipendenteIbanMatch, setDipendenteIbanMatch] = useState(null);

  const location = useLocation();

  const getTabFromPath = () => {
    const match = location.pathname.match(/\/archivio-bonifici\/([\w-]+)/);
    return match ? match[1] : 'da_associare';
  };

  // Deep link: tab + filtri sincronizzati con URL hash
  const [hs, setHs, setHsMany] = useHashState({
    tab: getTabFromPath(),
    search: '',
    ordinante: '',
    beneficiario: '',
  });
  const activeTab = hs.tab;

  const handleTabChange = tabId => {
    // Il tab Ò��¨ gestito interamente via hash (vedi useHashState sopra): questa
    // pagina Ò��¨ montata solo su /riconciliazione/archivio-bonifici, non esiste
    // una route "/archivio-bonifici/:tab" nel router Ò¢â�a¬â�� un navigate() verso
    // quel percorso finiva sul wildcard "*" e rimandava l'utente alla Dashboard.
    setHs('tab', tabId);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setHs('tab', tab);
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  const initialized = useRef(false);
  const dropdownRef = useRef(null);

  // Chiudi dropdown quando si clicca fuori
  useEffect(() => {
    const handleClickOutside = event => {
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

  // Ricarica quando cambiano i filtri (incluso l'anno globale: prima la
  // tabella movimenti ignorava l'anno globale quando yearFilter era vuoto Ò¢â�a¬â��
  // mostrava TUTTI gli anni mentre riepilogo/count restavano sull'anno
  // globale, con tabella e riepilogo che potevano riferirsi ad anni diversi)
  useEffect(() => {
    if (!initialized.current) return;
    const timer = setTimeout(() => {
      loadTransfers();
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, yearFilter, ordinanteFilter, beneficiarioFilter, anno]);

  const loadTransfers = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      // yearFilter Ò��¨ un override manuale opzionale; di default segue
      // l'anno globale come tutto il resto della pagina (summary/count).
      const annoEffettivo = yearFilter || anno;
      if (annoEffettivo) params.append('year', annoEffettivo);
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
              // Il task in background espone i campi direttamente sull'oggetto
              // (non annidati in "result" Ò¢â�a¬â�� quello non esiste lato backend).
              const riconciliati = statusRes.data.riconciliati || 0;
              const totale = statusRes.data.total || 0;
              toast.success('Riconciliazione completata', {
                description: `Riconciliati: ${riconciliati} Ò¢â�a¬�¢ Non trovati: ${Math.max(totale - riconciliati, 0)}`,
              });
              await Promise.all([loadTransfers(), loadRiconciliazioneStats()]);
              setRiconciliando(false);
            } else if (statusRes.data.status === 'error') {
              toast.error('Riconciliazione non riuscita', {
                description: statusRes.data.message || 'Errore sconosciuto',
              });
              setRiconciliando(false);
            } else if (attempts < maxAttempts) {
              attempts++;
              setTimeout(pollStatus, 2000);
            } else {
              toast.warning('Timeout raggiunto', {
                description: 'Verifica lo stato della riconciliazione manualmente.',
              });
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
        toast.success(res.data.message || 'Riconciliazione completata', {
          description: `Riconciliati: ${res.data.riconciliati} Ò¢â�a¬�¢ Non trovati: ${res.data.non_riconciliati}`,
        });
        await Promise.all([loadTransfers(), loadRiconciliazioneStats()]);
        setRiconciliando(false);
      }
    } catch (error) {
      toast.error('Riconciliazione non riuscita', {
        description: error.response?.data?.detail || error.message,
      });
      setRiconciliando(false);
    }
  };

  // Elimina bonifico
  const handleDelete = async id => {
    const confirmed = await confirm({
      title: 'Elimina bonifico',
      message: 'Eliminare definitivamente questo bonifico?',
      confirmText: 'Elimina',
      cancelText: 'Annulla',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await api.delete(`/api/archivio-bonifici/transfers/${id}`);
      toast.success('Bonifico eliminato');
      loadTransfers();
      loadCount();
    } catch (error) {
      toast.error('Eliminazione non riuscita', {
        description: error.response?.data?.detail || error.message,
      });
    }
  };

  // Export
  const handleExport = format => {
    const baseUrl = window.location.origin;
    window.open(`${baseUrl}/api/archivio-bonifici/export?format=${format}`, '_blank');
  };

  // Download ZIP per anno
  const handleDownloadZip = async year => {
    setDownloadingZip(true);
    try {
      const baseUrl = window.location.origin;
      window.open(`${baseUrl}/api/archivio-bonifici/download-zip/${year}`, '_blank');
    } catch (error) {
      toast.error('Download non riuscito', {
        description: error.message,
      });
    } finally {
      setTimeout(() => setDownloadingZip(false), 2000);
    }
  };

  // Salva nota bonifico
  const handleSaveNote = async id => {
    try {
      await api.put(`/api/archivio-bonifici/transfers/${id}`, { note: noteText });
      setEditingNote(null);
      setNoteText('');
      toast.success('Nota salvata');
      loadTransfers();
    } catch (error) {
      toast.error('Salvataggio non riuscito', {
        description: error.response?.data?.detail || error.message,
      });
    }
  };

  // Sincronizza IBAN dai bonifici all'anagrafica dipendenti
  const handleSyncIbanToAnagrafica = async () => {
    try {
      const res = await api.post('/api/archivio-bonifici/sync-iban-anagrafica');
      toast.success('Sincronizzazione completata', {
        description: `Dipendenti aggiornati: ${res.data.dipendenti_aggiornati} Ò¢â�a¬�¢ Bonifici analizzati: ${res.data.totale_bonifici_analizzati}`,
      });
    } catch (error) {
      toast.error('Sincronizzazione non riuscita', {
        description: error.response?.data?.detail || error.message,
      });
    }
  };

  // Carica operazioni salari compatibili per associazione
  const loadOperazioniCompatibili = async bonifico_id => {
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
  const toggleAssociaDropdown = bonifico_id => {
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
      await api.post(
        `/api/archivio-bonifici/associa-salario?bonifico_id=${bonifico_id}&operazione_id=${operazione_id}`
      );
      setAssociaDropdown(null);
      setOperazioniCompatibili([]);
      toast.success('Salario associato');
      loadTransfers();
    } catch (error) {
      toast.error('Associazione non riuscita', {
        description: error.response?.data?.detail || error.message,
      });
    }
  };

  // Disassocia bonifico da salario (DOPPIA CONFERMA)
  const handleDisassocia = async (bonifico_id, dipendente_nome) => {
    const confirmed = await confirm({
      title: 'Disassocia salario',
      message: `Rimuovere l'associazione con "${dipendente_nome || 'salario'}"?`,
      confirmText: 'Disassocia',
      cancelText: 'Annulla',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await api.delete(`/api/archivio-bonifici/disassocia-salario/${bonifico_id}`);
      toast.success('Associazione rimossa');
      loadTransfers();
    } catch (error) {
      toast.error('Disassociazione non riuscita', {
        description: error.message,
      });
    }
  };

  // === NUOVE FUNZIONI PER FATTURE ===
  const loadFattureCompatibili = async bonifico_id => {
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

  const toggleAssociaFatturaDropdown = bonifico_id => {
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
      await api.post(
        `/api/archivio-bonifici/associa-fattura?bonifico_id=${bonifico_id}&fattura_id=${fattura_id}&collection=${collection}`
      );
      setAssociaFatturaDropdown(null);
      setFattureCompatibili([]);
      toast.success('Fattura associata');
      loadTransfers();
    } catch (error) {
      toast.error('Associazione fattura non riuscita', {
        description: error.response?.data?.detail || error.message,
      });
    }
  };

  const handleDisassociaFattura = async (bonifico_id, fattura_numero) => {
    const confirmed = await confirm({
      title: 'Disassocia fattura',
      message: `Rimuovere l'associazione con la fattura "${fattura_numero || 'N/D'}"?`,
      confirmText: 'Disassocia',
      cancelText: 'Annulla',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await api.delete(`/api/archivio-bonifici/disassocia-fattura/${bonifico_id}`);
      toast.success('Associazione fattura rimossa');
      loadTransfers();
    } catch (error) {
      toast.error('Disassociazione non riuscita', {
        description: error.message,
      });
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
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '16px' }} ref={dropdownRef}>
      {/* Action bar senza titolo duplicato */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          marginBottom: 16,
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        <Link
          to="/import-export"
          style={{
            padding: '8px 14px',
            minHeight: 40,
            background: '#0f2744',
            color: 'white',
            fontWeight: 600,
            fontSize: 13,
            borderRadius: 6,
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          Ò°�&¸â����¥ Importa
        </Link>
        <button
          onClick={handleSyncIbanToAnagrafica}
          style={{
            padding: '8px 14px',
            minHeight: 40,
            background: '#0f2744',
            color: 'white',
            fontWeight: 600,
            fontSize: 13,
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
          }}
          title="Sincronizza gli IBAN dei bonifici nell'anagrafica dipendenti"
        >
          Ò°�&¸��¦ Sync IBAN
        </button>
        <button
          onClick={() => {
            loadTransfers();
            loadSummary();
            loadCount();
          }}
          style={{
            padding: '8px 14px',
            minHeight: 40,
            background: 'white',
            color: '#1e293b',
            border: '1px solid #e2e8f0',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          Ò°�&¸â��â��ž Aggiorna
        </button>
      </div>

      {/* Stats Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div
          style={{
            background: 'white',
            padding: 16,
            borderRadius: 8,
            border: '1px solid #e2e8f0',
            borderLeft: '4px solid #0f2744',
          }}
        >
          <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
            Bonifici Totali in DB
          </div>
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: '#1e293b',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            {count}
          </div>
        </div>
        <div
          style={{
            background: 'white',
            padding: 16,
            borderRadius: 8,
            border: '1px solid #e2e8f0',
            borderLeft: '4px solid #0f2744',
          }}
        >
          <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
            Bonifici Filtrati
          </div>
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: '#1e293b',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            {transfers.length}
          </div>
        </div>
        <div
          style={{
            background: 'white',
            padding: 16,
            borderRadius: 8,
            border: '1px solid #e2e8f0',
            borderLeft: '4px solid #0f2744',
          }}
        >
          <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
            Totale Importi Filtrati
          </div>
          <div
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: '#1e293b',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            {formatEuro(totaleImporto)}
          </div>
        </div>
        {/* Card Riconciliazione */}
        <div
          style={{
            background: 'white',
            padding: 16,
            borderRadius: 8,
            border: '1px solid #e2e8f0',
            borderLeft: '4px solid #0f2744',
          }}
        >
          <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
            Ò¢�&�Sâ��� Riconciliati
          </div>
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: riconciliazioneStats?.riconciliati > 0 ? '#16a34a' : '#dc2626',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            {riconciliazioneStats?.riconciliati || 0}/{riconciliazioneStats?.totale || 0}
          </div>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
            {riconciliazioneStats?.percentuale || 0}%
          </div>
        </div>
      </div>

      {/* Pulsante Riconciliazione */}
      <div
        style={{
          background: '#0f2744',
          padding: 16,
          borderRadius: 8,
          marginBottom: 24,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          color: 'white',
        }}
      >
        <div>
          <div style={{ fontWeight: 'bold', fontSize: 16 }}>
            Ò°�&¸â��â��⬝ Riconciliazione con Estratto Conto
          </div>
          <div style={{ fontSize: 13, opacity: 0.9 }}>
            Confronta i bonifici con i movimenti bancari per verificare i pagamenti effettivi
          </div>
        </div>
        <button
          onClick={handleRiconcilia}
          disabled={riconciliando}
          style={{
            padding: '12px 24px',
            minHeight: 40,
            borderRadius: 6,
            background: riconciliando ? '#94a3b8' : 'white',
            color: '#0f2744',
            border: 'none',
            cursor: riconciliando ? 'not-allowed' : 'pointer',
            fontWeight: 'bold',
            fontSize: 13,
          }}
          data-testid="riconcilia-bonifici-btn"
        >
          {riconciliando ? 'Ò¢��³ Riconciliazione in corso...' : 'Ò°�&¸�&¡â�a¬ Avvia Riconciliazione'}
        </button>
      </div>

      {/* Riepilogo per Anno con Download ZIP */}
      {Object.keys(summary).length > 0 && (
        <div
          style={{
            background: 'white',
            padding: 16,
            borderRadius: 8,
            border: '1px solid #e2e8f0',
            marginBottom: 24,
          }}
        >
          <h3 style={{ fontSize: 14, fontWeight: 'bold', marginBottom: 12, color: '#0f2744' }}>
            Ò°�&¸â����&  Riepilogo per Anno (clicca per scaricare ZIP)
          </h3>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {Object.entries(summary)
              .sort(([a], [b]) => b.localeCompare(a))
              .map(([year, data]) => (
                <div
                  key={year}
                  style={{
                    background: 'white',
                    padding: '8px 16px',
                    minHeight: 40,
                    borderRadius: 6,
                    border: '1px solid #e2e8f0',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onClick={() => handleDownloadZip(year)}
                  onMouseOver={e => (e.currentTarget.style.borderColor = '#3b82f6')}
                  onMouseOut={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                >
                  <div
                    style={{
                      fontWeight: 'bold',
                      color: '#0f2744',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    {year}
                    <span style={{ fontSize: 12, color: '#3b82f6' }}>Ò°�&¸â����¥</span>
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>
                    {data.count} bonifici Ò¢â�a¬�¢ {formatEuro(data.total)}
                  </div>
                </div>
              ))}
          </div>
          {downloadingZip && (
            <div style={{ marginTop: 8, fontSize: 12, color: '#3b82f6' }}>
              Ò¢��³ Preparazione ZIP in corso...
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div
        style={{
          background: 'white',
          padding: 16,
          borderRadius: 8,
          border: '1px solid #e2e8f0',
          marginBottom: 24,
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <input
          type="text"
          placeholder="Ò°�&¸â��� Cerca causale, CRO/TRN..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') loadTransfers();
          }}
          style={{
            padding: '8px 12px',
            minHeight: 40,
            borderRadius: 6,
            border: '1px solid #e2e8f0',
            fontSize: 13,
            minWidth: 200,
          }}
          data-testid="bonifici-search"
        />
        <button
          onClick={loadTransfers}
          style={{
            padding: '8px 16px',
            minHeight: 40,
            borderRadius: 6,
            background: '#0f2744',
            color: 'white',
            border: 'none',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 'bold',
          }}
          data-testid="bonifici-search-btn"
        >
          Ò°�&¸â��� Cerca
        </button>
        <input
          type="text"
          placeholder="Filtra ordinante..."
          value={ordinanteFilter}
          onChange={e => setOrdinanteFilter(e.target.value)}
          style={{
            padding: '8px 12px',
            minHeight: 40,
            borderRadius: 6,
            border: '1px solid #e2e8f0',
            fontSize: 13,
            minWidth: 150,
          }}
        />
        <input
          type="text"
          placeholder="Filtra beneficiario..."
          value={beneficiarioFilter}
          onChange={e => setBeneficiarioFilter(e.target.value)}
          style={{
            padding: '8px 12px',
            minHeight: 40,
            borderRadius: 6,
            border: '1px solid #e2e8f0',
            fontSize: 13,
            minWidth: 150,
          }}
        />
        <input
          type="text"
          placeholder={`Anno (default: ${anno})`}
          title="Lascia vuoto per usare l'anno selezionato in alto"
          value={yearFilter}
          onChange={e => setYearFilter(e.target.value)}
          style={{
            padding: '8px 12px',
            minHeight: 40,
            borderRadius: 6,
            border: '1px solid #e2e8f0',
            fontSize: 13,
            width: 120,
          }}
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
              minHeight: 40,
              borderRadius: 6,
              background: 'white',
              color: '#64748b',
              border: '1px solid #e2e8f0',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            Ò¢�&�Sâ��¢ Reset
          </button>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={() => handleExport('xlsx')}
            style={{
              padding: '8px 16px',
              minHeight: 40,
              borderRadius: 6,
              background: '#0f2744',
              color: 'white',
              border: 'none',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            Ò°�&¸â����¥ Export XLSX
          </button>
          <button
            onClick={() => handleExport('csv')}
            style={{
              padding: '8px 16px',
              minHeight: 40,
              borderRadius: 6,
              background: 'white',
              color: '#1e293b',
              border: '1px solid #e2e8f0',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            Ò°�&¸â����¥ Export CSV
          </button>
        </div>
      </div>

      {/* TABS */}
      <div
        style={{ display: 'flex', gap: 0, marginBottom: 0, alignItems: 'flex-end', flexWrap: 'wrap' }}
      >
        <button
          onClick={() => handleTabChange('da_associare')}
          style={{
            padding: '12px 24px',
            minHeight: 40,
            background: activeTab === 'da_associare' ? '#0f2744' : '#f1f5f9',
            color: activeTab === 'da_associare' ? 'white' : '#475569',
            border: 'none',
            borderRadius: '8px 8px 0 0',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
          data-testid="tab-da-associare"
        >
          Da Associare
          <span
            style={{
              background: activeTab === 'da_associare' ? 'rgba(255,255,255,0.2)' : '#e2e8f0',
              padding: '2px 8px',
              borderRadius: 10,
              fontSize: 12,
            }}
          >
            {bonificiDaAssociare.length}
          </span>
        </button>
        <button
          onClick={() => handleTabChange('associati')}
          style={{
            padding: '12px 24px',
            minHeight: 40,
            background: activeTab === 'associati' ? '#0f2744' : '#f1f5f9',
            color: activeTab === 'associati' ? 'white' : '#475569',
            border: 'none',
            borderRadius: '8px 8px 0 0',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginLeft: 4,
          }}
          data-testid="tab-associati"
        >
          Ò¢�&�Sâ��¦ Associati
          <span
            style={{
              background: activeTab === 'associati' ? 'rgba(255,255,255,0.2)' : '#e2e8f0',
              color: activeTab === 'associati' ? 'white' : '#475569',
              padding: '2px 8px',
              borderRadius: 10,
              fontSize: 12,
            }}
          >
            {bonificiAssociati.length}
          </span>
        </button>
        <div style={{ flex: 1 }} />
        <CopyLinkButton style={{ marginBottom: 4 }} />
      </div>

      {/* Table */}
      <div
        style={{
          background: 'white',
          borderRadius: '0 8px 8px 8px',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
        }}
      >
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
            Ò¢��³ Caricamento...
          </div>
        ) : transfersToShow.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
            {activeTab === 'da_associare'
              ? 'Ò°�&¸�&½â��° Tutti i bonifici sono stati associati!'
              : 'Nessun bonifico associato. Seleziona il tab "Da Associare" per iniziare.'}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr
                  style={{
                    background: '#f8fafc',
                    color: '#64748b',
                    fontSize: 11,
                    textTransform: 'uppercase',
                  }}
                >
                  <th style={{ padding: 8, textAlign: 'center', width: 40 }}>Ò¢�&�Sâ���</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>Data</th>
                  <th style={{ padding: 8, textAlign: 'right' }}>Importo</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>Beneficiario</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>Causale</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>CRO/TRN</th>
                  <th style={{ padding: 8, textAlign: 'left', width: 180 }}>
                    {activeTab === 'associati' ? 'Salario Associato' : 'Associa Salario'}
                  </th>
                  <th style={{ padding: 8, textAlign: 'left', width: 180 }}>
                    {activeTab === 'associati' ? 'Fattura Associata' : 'Associa Fattura'}
                  </th>
                  <th style={{ padding: 8, textAlign: 'left', width: 100 }}>Note</th>
                  <th style={{ padding: 8, textAlign: 'center', width: 50 }}>Ò°�&¸â��⬝â���SÒ¯�¸�</th>
                </tr>
              </thead>
              <tbody>
                {transfersToShow.map((t, idx) => (
                  <tr
                    key={t.id || idx}
                    style={{
                      borderBottom: '1px solid #f1f5f9',
                      background: t.riconciliato ? '#f0fdf4' : 'white',
                    }}
                  >
                    <td style={{ padding: 8, textAlign: 'center' }}>
                      {t.riconciliato ? (
                        <span
                          style={{ color: '#16a34a', fontSize: 16 }}
                          title={`Riconciliato: ${t.movimento_descrizione || 'Trovato in estratto conto'}`}
                        >
                          Ò¢�&�Sâ��¦
                        </span>
                      ) : (
                        <span style={{ color: '#d1d5db', fontSize: 14 }}>Ò¢â��⬝â��¹</span>
                      )}
                    </td>
                    <td style={{ padding: 8, whiteSpace: 'nowrap' }}>{formatDate(t.data)}</td>
                    <td
                      style={{
                        padding: 8,
                        textAlign: 'right',
                        fontWeight: 'bold',
                        color: '#16a34a',
                        whiteSpace: 'nowrap',
                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                      }}
                    >
                      {formatEuro(t.importo)}
                    </td>
                    <td style={{ padding: 8 }}>{t.beneficiario?.nome || '-'}</td>
                    <td
                      style={{
                        padding: 8,
                        maxWidth: 180,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={t.causale}
                    >
                      {t.causale || '-'}
                    </td>
                    <td style={{ padding: 8, fontSize: 10 }}>{t.cro_trn || '-'}</td>
                    {/* Colonna Associa a Salario */}
                    <td style={{ padding: 8, position: 'relative' }}>
                      {t.salario_associato ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span
                            style={{
                              background: '#dcfce7',
                              color: '#16a34a',
                              padding: '4px 8px',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 500,
                            }}
                          >
                            Ò¢�&�Sâ��� {t.operazione_salario_desc?.substring(0, 20) || 'Associato'}
                          </span>
                          <button
                            onClick={() => handleDisassocia(t.id, t.operazione_salario_desc)}
                            style={{
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              fontSize: 10,
                              color: '#dc2626',
                            }}
                            title="Rimuovi associazione (doppia conferma)"
                          >
                            Ò¢�&�Sâ��⬝
                          </button>
                        </div>
                      ) : (
                        <div>
                          <button
                            onClick={() => toggleAssociaDropdown(t.id)}
                            style={{
                              padding: '4px 10px',
                              background: associaDropdown === t.id ? '#0f2744' : '#f1f5f9',
                              color: associaDropdown === t.id ? 'white' : '#475569',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              fontSize: 11,
                              fontWeight: 500,
                            }}
                            data-testid={`btn-associa-${t.id}`}
                          >
                            {associaDropdown === t.id ? 'Ò¢â���S�¼ Seleziona' : '+ Associa'}
                          </button>
                          {/* Dropdown operazioni */}
                          {associaDropdown === t.id && (
                            <div
                              style={{
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
                                overflowY: 'auto',
                              }}
                            >
                              {/* Banner IBAN Match */}
                              {dipendenteIbanMatch && !loadingOperazioni && (
                                <div
                                  style={{
                                    background: '#ecfdf5',
                                    borderBottom: '2px solid #16a34a',
                                    padding: '8px 12px',
                                    fontSize: 10,
                                  }}
                                >
                                  <div style={{ fontWeight: 600, color: '#16a34a' }}>
                                    Ò°�&¸â��â��⬝ IBAN riconosciuto
                                  </div>
                                  <div style={{ color: '#166534', marginTop: 2 }}>
                                    Dipendente: <strong>{dipendenteIbanMatch.nome_display}</strong>
                                  </div>
                                </div>
                              )}
                              {loadingOperazioni ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#6b7280' }}>
                                  Ò¢��³ Caricamento...
                                </div>
                              ) : operazioniCompatibili.length === 0 ? (
                                <div
                                  style={{
                                    padding: 16,
                                    textAlign: 'center',
                                    color: '#6b7280',
                                    fontSize: 11,
                                  }}
                                >
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
                                      background: op.iban_match ? '#ecfdf5' : 'white',
                                    }}
                                    onMouseOver={e =>
                                      (e.currentTarget.style.background = op.iban_match
                                        ? '#dcfce7'
                                        : '#f0f9ff')
                                    }
                                    onMouseOut={e =>
                                      (e.currentTarget.style.background = op.iban_match
                                        ? '#ecfdf5'
                                        : 'white')
                                    }
                                  >
                                    <div
                                      style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                      }}
                                    >
                                      <span style={{ fontWeight: 500, fontSize: 11 }}>
                                        {op.iban_match && (
                                          <span style={{ color: '#16a34a', marginRight: 4 }}>
                                            Ò°�&¸â��â��⬝
                                          </span>
                                        )}
                                        {op.dipendente || op.descrizione || 'Operazione'}
                                      </span>
                                      <div
                                        style={{ display: 'flex', gap: 4, alignItems: 'center' }}
                                      >
                                        {op.iban_match && (
                                          <span
                                            style={{
                                              background: '#16a34a',
                                              color: 'white',
                                              padding: '2px 6px',
                                              borderRadius: 4,
                                              fontSize: 8,
                                              fontWeight: 600,
                                            }}
                                          >
                                            IBAN Ò¢�&�Sâ���
                                          </span>
                                        )}
                                        <span
                                          style={{
                                            background:
                                              op.compatibilita_score >= 70
                                                ? '#dcfce7'
                                                : op.compatibilita_score >= 40
                                                  ? '#fef3c7'
                                                  : '#fee2e2',
                                            color:
                                              op.compatibilita_score >= 70
                                                ? '#16a34a'
                                                : op.compatibilita_score >= 40
                                                  ? '#d97706'
                                                  : '#dc2626',
                                            padding: '2px 6px',
                                            borderRadius: 4,
                                            fontSize: 9,
                                            fontWeight: 600,
                                          }}
                                        >
                                          {op.compatibilita_score}%
                                        </span>
                                      </div>
                                    </div>
                                    <div
                                      style={{
                                        fontSize: 10,
                                        color: '#6b7280',
                                        marginTop: 4,
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                      }}
                                    >
                                      <span>
                                        {op.anno && op.mese
                                          ? `${op.mese}/${op.anno}`
                                          : formatDate(op.data)}
                                      </span>
                                      <span
                                        style={{
                                          fontWeight: 600,
                                          fontFamily:
                                            'ui-monospace, SFMono-Regular, Menlo, monospace',
                                        }}
                                      >
                                        {formatEuro(op.importo_display)}
                                      </span>
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
                          <span
                            style={{
                              background: '#dbeafe',
                              color: '#1e40af',
                              padding: '4px 8px',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 500,
                            }}
                          >
                            Ò°�&¸â���â��ž {t.fattura_numero?.substring(0, 15) || 'Associata'}
                          </span>
                          <button
                            onClick={() => handleDisassociaFattura(t.id, t.fattura_numero)}
                            style={{
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              fontSize: 10,
                              color: '#dc2626',
                            }}
                            title="Rimuovi associazione (doppia conferma)"
                          >
                            Ò¢�&�Sâ��⬝
                          </button>
                        </div>
                      ) : (
                        <div>
                          <button
                            onClick={() => toggleAssociaFatturaDropdown(t.id)}
                            style={{
                              padding: '4px 10px',
                              background: associaFatturaDropdown === t.id ? '#0f2744' : '#f1f5f9',
                              color: associaFatturaDropdown === t.id ? 'white' : '#475569',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              fontSize: 11,
                              fontWeight: 500,
                            }}
                            data-testid={`btn-associa-fattura-${t.id}`}
                          >
                            {associaFatturaDropdown === t.id ? 'Ò¢â���S�¼ Scegli' : 'Ò°�&¸â���â��ž Fattura'}
                          </button>
                          {/* Dropdown fatture */}
                          {associaFatturaDropdown === t.id && (
                            <div
                              style={{
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
                                overflowY: 'auto',
                              }}
                            >
                              {loadingFatture ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#6b7280' }}>
                                  Ò¢��³ Caricamento...
                                </div>
                              ) : fattureCompatibili.length === 0 ? (
                                <div
                                  style={{
                                    padding: 16,
                                    textAlign: 'center',
                                    color: '#6b7280',
                                    fontSize: 11,
                                  }}
                                >
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
                                      transition: 'background 0.1s',
                                    }}
                                    onMouseOver={e =>
                                      (e.currentTarget.style.background = '#eff6ff')
                                    }
                                    onMouseOut={e => (e.currentTarget.style.background = 'white')}
                                  >
                                    <div
                                      style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                      }}
                                    >
                                      <span style={{ fontWeight: 500, fontSize: 11 }}>
                                        {f.numero_fattura || 'N/A'} -{' '}
                                        {f.fornitore?.substring(0, 20) || ''}
                                      </span>
                                      <span
                                        style={{
                                          background:
                                            f.compatibilita_score >= 70
                                              ? '#dcfce7'
                                              : f.compatibilita_score >= 40
                                                ? '#fef3c7'
                                                : '#fee2e2',
                                          color:
                                            f.compatibilita_score >= 70
                                              ? '#16a34a'
                                              : f.compatibilita_score >= 40
                                                ? '#d97706'
                                                : '#dc2626',
                                          padding: '2px 6px',
                                          borderRadius: 4,
                                          fontSize: 9,
                                          fontWeight: 600,
                                        }}
                                      >
                                        {f.compatibilita_score}%
                                      </span>
                                    </div>
                                    <div
                                      style={{
                                        fontSize: 10,
                                        color: '#6b7280',
                                        marginTop: 4,
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        gap: 6,
                                      }}
                                    >
                                      <span>
                                        {formatDate(f.data_fattura)} Ò¢â�a¬�¢ {formatEuro(f.importo)}
                                      </span>
                                      {f.id && (
                                        <button
                                          onClick={e => {
                                            e.stopPropagation();
                                            setFatturaView({ id: f.id, numero: f.numero_fattura || f.numero || f.fornitore });
                                          }}
                                          style={{
                                            padding: '2px 6px',
                                            background: '#10b981',
                                            color: 'white',
                                            border: 'none',
                                            borderRadius: 4,
                                            fontSize: 9,
                                            cursor: 'pointer',
                                            flexShrink: 0,
                                          }}
                                        >
                                          Vedi
                                        </button>
                                      )}
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
                            onChange={e => setNoteText(e.target.value)}
                            style={{
                              padding: 4,
                              borderRadius: 4,
                              border: '1px solid #e2e8f0',
                              fontSize: 11,
                              width: 80,
                            }}
                            autoFocus
                          />
                          <button
                            onClick={() => handleSaveNote(t.id)}
                            style={{
                              padding: '2px 6px',
                              background: '#16a34a',
                              color: 'white',
                              border: 'none',
                              borderRadius: 4,
                              cursor: 'pointer',
                              fontSize: 10,
                            }}
                          >
                            Ò¢�&�Sâ���
                          </button>
                          <button
                            onClick={() => {
                              setEditingNote(null);
                              setNoteText('');
                            }}
                            style={{
                              padding: '2px 6px',
                              background: '#94a3b8',
                              color: 'white',
                              border: 'none',
                              borderRadius: 4,
                              cursor: 'pointer',
                              fontSize: 10,
                            }}
                          >
                            Ò¢�&�Sâ��⬝
                          </button>
                        </div>
                      ) : (
                        <div
                          onClick={() => {
                            setEditingNote(t.id);
                            setNoteText(t.note || '');
                          }}
                          style={{
                            cursor: 'pointer',
                            color: t.note ? '#0f2744' : '#94a3b8',
                            fontSize: 11,
                          }}
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
                          opacity: 0.6,
                        }}
                        title="Elimina"
                      >
                        Ò°�&¸â��⬝â���SÒ¯�¸�
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {fatturaView && (
          <ModalFattura
            fatturaId={fatturaView.id}
            numero={fatturaView.numero}
            onClose={() => setFatturaView(null)}
          />
        )}
    </div>
  );
}
