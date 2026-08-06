import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import api from '../api';
import {
  formatEuro,
  formatDateIT,
  formatDateGGMM,
  STYLES,
  COLORS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { ListaAdattiva } from '../components/ds';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { toast } from 'sonner';
import { ExportButton } from '../components/ExportButton';
import { PageLayout } from '../components/PageLayout';
import DocumentViewerModal from '../components/DocumentViewerModal';

const RiconciliazionePaypalLazy = lazy(() => import('./RiconciliazionePaypal.jsx'));

/**
 * RICONCILIAZIONE UNIFICATA
 *
 * Una sola pagina smart con:
 * - Dashboard riepilogo
 * - Tab: Banca | Assegni | F24 | Stipendi
 * - Auto-matching intelligente
 * - Flussi a cascata automatici
 * - URL con tab: /riconciliazione/banca, /riconciliazione/assegni, etc.
 */

const TABS = [
  { id: 'dashboard', label: '📊 Dashboard', color: '#0f2744' },
  { id: 'banca', label: '🏦 Banca', color: '#0f2744' },
  { id: 'assegni', label: '📝 Prelievi Assegno', color: '#0f2744' },
  { id: 'f24', label: '📄 F24', color: '#0f2744' },
  { id: 'stipendi', label: '👤 Stipendi', color: '#0f2744' },
  { id: 'documenti', label: '📎 Documenti', color: '#0f2744' },
  { id: 'paypal', label: '💳 PayPal', color: '#0f2744' },
];

export default function RiconciliazioneUnificata() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const confirm = useConfirm();

  // Ottieni tab dall'URL (es. /riconciliazione-unificata/banca -> banca)
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/riconciliazione(?:-unificata)?\/(\w+)/);
    if (match && TABS.find(t => t.id === match[1])) {
      return match[1];
    }
    return 'dashboard';
  };

  const [activeTab, setActiveTab] = useState(getTabFromPath());
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [processing, setProcessing] = useState(null);
  const [loadError, setLoadError] = useState(null);

  // Aggiorna URL quando cambia tab. Usa sempre il prefisso "/riconciliazione":
  // è l'unico effettivamente instradato in main.jsx — "/riconciliazione-unificata"
  // esiste solo come redirect legacy verso "/riconciliazione" SENZA sotto-tab,
  // quindi navigare a "/riconciliazione-unificata/<tab>" cadeva sul catch-all e
  // rimandava l'utente alla Dashboard invece di cambiare tab.
  const handleTabChange = tabId => {
    setActiveTab(tabId);
    if (tabId === 'dashboard') {
      navigate('/riconciliazione');
    } else {
      navigate(`/riconciliazione/${tabId}`);
    }
  };

  // Sincronizza tab con URL al mount e quando cambia URL
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) {
      setActiveTab(tab);
    }
  }, [location.pathname]);

  // Dati per ogni sezione
  const [stats, setStats] = useState({});
  const [movimentiBanca, setMovimentiBanca] = useState([]);
  const [assegni, setAssegni] = useState([]);
  const [f24Pendenti, setF24Pendenti] = useState([]);
  const [stipendiPendenti, setStipendiPendenti] = useState([]);
  const [documentiNonAssociati, setDocumentiNonAssociati] = useState([]);
  const [documentiStats, setDocumentiStats] = useState(null);

  // Paginazione
  const [currentLimit, setCurrentLimit] = useState(25);
  const [hasMore, setHasMore] = useState(true);

  // Filtri avanzati
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    dataFrom: '',
    dataTo: '',
    importoMin: '',
    importoMax: '',
    search: '',
  });

  // Auto-match stats
  const [autoMatchStats, setAutoMatchStats] = useState({ matched: 0, pending: 0 });

  // Applica filtri ai movimenti
  const applyFilters = movimenti => {
    return movimenti.filter(m => {
      // Usa data o data_emissione
      const dataMovimento = m.data || m.data_emissione;

      // Filtro data
      if (filters.dataFrom && dataMovimento < filters.dataFrom) return false;
      if (filters.dataTo && dataMovimento > filters.dataTo) return false;

      // Filtro importo
      const importo = Math.abs(parseFloat(m.importo) || 0);
      if (filters.importoMin && importo < parseFloat(filters.importoMin)) return false;
      if (filters.importoMax && importo > parseFloat(filters.importoMax)) return false;

      // Filtro ricerca testo
      if (filters.search) {
        const search = filters.search.toLowerCase();
        const desc = (m.descrizione || '').toLowerCase();
        const tipo = (m.tipo || '').toLowerCase();
        if (!desc.includes(search) && !tipo.includes(search)) return false;
      }

      return true;
    });
  };

  // Movimenti filtrati
  const movimentiBancaFiltrati = applyFilters(movimentiBanca);
  const assegniFiltrati = applyFilters(assegni);
  const stipendiFiltrati = applyFilters(stipendiPendenti);

  // Stato per auto-riparazione
  const [autoRepairStatus, setAutoRepairStatus] = useState(null);
  const [autoRepairRunning, setAutoRepairRunning] = useState(false);

  /**
   * LOGICA INTELLIGENTE: Esegue auto-riparazione dei dati al caricamento.
   * Questa funzione implementa la logica di un commercialista esperto.
   */
  const eseguiAutoRiparazione = async () => {
    setAutoRepairRunning(true);
    try {
      const res = await api.post('/api/fatture-ricevute/auto-ricostruisci-dati');
      if (res.data.riconciliazioni_auto > 0 || res.data.f24_corretti > 0) {
        setAutoRepairStatus(res.data);
        // Ricarica dati dopo riparazione
        loadAllData();
      } else {
        toast.info('Auto-riparazione completata: niente da correggere.');
      }
    } catch (error) {
      // Errore del servizio ≠ "niente da riparare": va segnalato.
      toast.error('Auto-riparazione non riuscita: ' + (error.response?.data?.detail || error.message));
    } finally {
      setAutoRepairRunning(false);
    }
  };

  // Auto-riparazione DISABILITATA per performance - eseguire manualmente
  // useEffect(() => {
  //   eseguiAutoRiparazione();
  // }, []);

  useEffect(() => {
    loadAllData();
  }, [anno]);

  const loadAllData = async (limit = 50) => {
    setLoading(true);
    setLoadError(null);
    try {
      // Carica dati primari: usa /smart/analizza per suggerimenti + assegni da banca-veloce.
      // Ogni chiamata ha un fallback silenzioso (pagina comunque utilizzabile se una sola
      // fonte fallisce), ma se TUTTE falliscono l'utente deve saperlo: prima la pagina
      // restava semplicemente vuota in ogni tab, senza nessuna indicazione dell'errore.
      const erroriCaricamento = [];
      const [analizzaRes, assegniRes, stipendiRes] = await Promise.all([
        api
          .get(`/api/operazioni-da-confermare/smart/analizza?limit=${limit}`)
          .catch(e => {
            erroriCaricamento.push(e.response?.data?.detail || e.message);
            return { data: { movimenti: [], stats: {} } };
          }),
        api
          .get(`/api/operazioni-da-confermare/smart/banca-veloce?limit=50&anno=${anno}`)
          .catch(e => {
            erroriCaricamento.push(e.response?.data?.detail || e.message);
            return { data: { movimenti: [], stats: {}, assegni: [] } };
          }),
        api
          .get('/api/operazioni-da-confermare/smart/cerca-stipendi')
          .catch(e => {
            erroriCaricamento.push(e.response?.data?.detail || e.message);
            return { data: { stipendi: [] } };
          }),
      ]);
      if (erroriCaricamento.length > 0) {
        setLoadError(
          `Alcuni dati non si sono caricati correttamente (${erroriCaricamento.length}/3 sorgenti in errore): ${erroriCaricamento[0]}`
        );
      }

      const movimenti = analizzaRes.data?.movimenti || [];
      const assegniDaApi = (assegniRes.data?.assegni || []).map(a => ({
        ...a,
        numero_assegno: a.numero_assegno || a.numero,
        data: a.data || a.data_emissione,
        descrizione:
          a.descrizione ||
          a.causale ||
          a.beneficiario ||
          `Assegno ${a.numero || a.numero_assegno || ''}`,
      }));

      setHasMore(movimenti.length >= limit);
      setCurrentLimit(limit);
      setStats(assegniRes.data?.stats || analizzaRes.data?.stats || {});

      // Movimenti banca (escludi prelievi assegno)
      setMovimentiBanca(
        movimenti.filter(m => !m.descrizione?.toUpperCase()?.includes('PRELIEVO ASSEGNO'))
      );

      // Assegni da riconciliare (già filtrati dal backend)
      setAssegni(assegniDaApi);

      const stipendi = stipendiRes.data?.stipendi || [];

      setStipendiPendenti(stipendi);

      // Aggiorna stats iniziali (F24 caricato su richiesta)
      setStats({
        totale: movimenti.length,
        banca: movimenti.length,
        assegni: assegniDaApi.length,
        f24: 0, // Caricato su richiesta manuale
        stipendi: stipendi.length,
        documenti: 0, // Caricato dopo
        fatture_da_pagare: assegniRes.data?.stats?.fatture_da_pagare || 0,
      });

      // Auto-match stats (da analizza)
      setAutoMatchStats({
        matched: analizzaRes.data?.stats?.riconciliati || assegniRes.data?.stats?.riconciliati || 0,
        pending:
          analizzaRes.data?.stats?.non_riconciliati ||
          assegniRes.data?.stats?.non_riconciliati ||
          0,
      });

      setLoading(false);

      // F24: RIMOSSO dal caricamento automatico (prendeva ~35s e causava un "reload visivo")
      // Caricato solo quando l'utente apre il tab F24 — vedi loadF24OnDemand()

      // Carica Documenti Non Associati in background
      api
        .get('/api/documenti-non-associati/lista?limit=100')
        .then(docsRes => {
          const docs = docsRes.data?.documenti || [];
          setDocumentiNonAssociati(docs);
          setStats(prev => ({ ...prev, documenti: docs.length }));
        })
        .catch(() => {
          console.warn('Documenti non caricati');
        });

      // Carica statistiche documenti
      api
        .get('/api/documenti-non-associati/statistiche')
        .then(statsRes => {
          setDocumentiStats(statsRes.data);
        })
        .catch(() => {});
    } catch (e) {
      console.error('Errore caricamento:', e);
      setLoading(false);
    }
  };

  // Carica altri movimenti
  const loadMore = async () => {
    const newLimit = currentLimit + 25;
    setLoadingMore(true);
    try {
      const bancaRes = await api.get(
        `/api/operazioni-da-confermare/smart/banca-veloce?limit=${newLimit}`
      );
      const movimenti = bancaRes.data?.movimenti || [];
      const assegniDaApi = (bancaRes.data?.assegni || []).map(a => ({
        ...a,
        numero_assegno: a.numero_assegno || a.numero,
        data: a.data || a.data_emissione,
        descrizione:
          a.descrizione ||
          a.causale ||
          a.beneficiario ||
          `Assegno ${a.numero || a.numero_assegno || ''}`,
      }));

      setHasMore(movimenti.length >= newLimit);
      setCurrentLimit(newLimit);

      setMovimentiBanca(
        movimenti.filter(m => !m.descrizione?.toUpperCase()?.includes('PRELIEVO ASSEGNO'))
      );
      setAssegni(assegniDaApi);
      setStats(bancaRes.data?.stats || {});
    } catch (e) {
      toast.error('Caricamento non riuscito: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoadingMore(false);
    }
  };

  // Auto-riconcilia tutti i movimenti con match esatto
  const [f24Loading, setF24Loading] = useState(false);

  // Carica F24 solo su richiesta esplicita (evita il "reload visivo" da ~35s)
  const loadF24OnDemand = async () => {
    setF24Loading(true);
    try {
      const f24Res = await api.get(`/api/operazioni-da-confermare/smart/cerca-f24?anno=${anno}`);
      const f24 = f24Res.data?.f24 || [];
      setF24Pendenti(f24);
      setStats(prev => ({ ...prev, f24: f24.length }));
    } catch (e) {
      toast.error('F24 non caricati: ' + (e.response?.data?.detail || e.message));
    } finally {
      setF24Loading(false);
    }
  };

  const handleAutoRiconcilia = async () => {
    setProcessing('auto');
    try {
      // Le regole contabili appartengono al backend: numeri fattura
      // espliciti, quadratura aggregata POS e PayPal biunivoco. La UI non
      // conferma piu' in ciclo suggerimenti parziali o basati sull'importo.
      const res = await api.post(
        `/api/operazioni-da-confermare/smart/riconcilia-auto?limit=${currentLimit}`
      );
      const matched = res.data?.riconciliati || 0;
      const errori = res.data?.errori || [];
      setAutoMatchStats({ matched, pending: stats.totale - matched });
      toast.success(`Auto-riconciliati ${matched} movimenti`, {
        description:
          errori.length > 0
            ? `${errori.length} motori in errore: ${errori
                .slice(0, 3)
                .map(e => e.error || String(e))
                .join('; ')}`
            : undefined,
      });
      await loadAllData();
    } catch (e) {
      toast.error('Auto-riconciliazione non completata', {
        description: e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  // Conferma singolo movimento
  const handleConferma = async (movimento, tipo, associazioni) => {
    setProcessing(movimento.movimento_id || movimento.id);
    try {
      const tipoEff = tipo || movimento.tipo;
      if (tipoEff === 'stipendio' && !movimento.movimento_id) {
        // Riga stipendio pendente (prima_nota_salari): cerca in estratto
        // conto il bonifico "FAVORE <nome dipendente>" e associa (18/07/2026)
        const res = await api.post('/api/operazioni-da-confermare/smart/riconcilia-stipendio', {
          stipendio_id: movimento.id,
        });
        if (res.data?.success) {
          const d = res.data.dettaglio?.[0];
          toast.success('Bonifico associato', {
            description: d ? `${d.dipendente}: € ${d.importo} del ${d.data_bonifico}` : undefined,
          });
        } else {
          toast.error('Nessun bonifico trovato', {
            description: res.data?.message,
          });
        }
        loadAllData();
        return;
      }
      await api.post('/api/operazioni-da-confermare/smart/riconcilia-manuale', {
        movimento_id: movimento.movimento_id,
        tipo: tipoEff,
        associazioni: associazioni || movimento.suggerimenti?.slice(0, 1) || [],
        categoria: movimento.categoria,
      });
      toast.success('Movimento riconciliato');
      loadAllData();
    } catch (e) {
      toast.error('Riconciliazione non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  // Ignora movimento
  const handleIgnora = async movimento => {
    setProcessing(movimento.movimento_id || movimento.id);
    try {
      await api.post('/api/operazioni-da-confermare/smart/ignora', {
        movimento_id: movimento.movimento_id || movimento.id,
      });
      toast.success('Movimento ignorato');
      loadAllData();
    } catch (e) {
      console.error('Errore ignora:', e);
      toast.error('Operazione non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  // Elimina movimento (rimuove completamente dal database)
  const handleElimina = async movimento => {
    const movId = movimento.id || movimento.movimento_id;
    if (!movId) {
      toast.error('ID movimento non trovato');
      return;
    }

    const confirmed = await confirm({
      title: 'Elimina movimento',
      message: 'Eliminare definitivamente questo movimento?',
      confirmText: 'Elimina',
      cancelText: 'Annulla',
      variant: 'danger',
    });
    if (!confirmed) {
      return;
    }

    setProcessing(movId);
    try {
      await api.delete(`/api/estratto-conto-movimenti/${movId}`);
      toast.success('Movimento eliminato');
      loadAllData();
    } catch (e) {
      toast.error('Eliminazione non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  // Incassa assegno (segna come incassato e crea movimento in Prima Nota Banca)
  const handleIncassaAssegno = async assegno => {
    setProcessing(assegno.id);
    try {
      // 1. Segna assegno come incassato
      await api.post(`/api/assegni/${assegno.id}/incassa`);

      // 2. Se vuoi anche creare movimento in Prima Nota Banca, decommentare:
      // await api.post('/api/prima-nota-banca/crea', {
      //   data: assegno.data || new Date().toISOString().split('T')[0],
      //   tipo: 'uscita',
      //   importo: Math.abs(assegno.importo),
      //   descrizione: `Assegno ${assegno.numero || ''} - ${assegno.beneficiario || ''}`,
      //   categoria: 'assegno'
      // });

      toast.success('Assegno incassato');
      loadAllData();
    } catch (e) {
      toast.error('Incasso assegno non riuscito', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 'clamp(12px, 3vw, 20px)' }}>
        {/* Header con Gradiente anche durante il caricamento */}
        <div
          style={{
            marginBottom: 20,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '15px 20px',
            background: '#0f2744',
            borderRadius: 8,
            color: 'white',
          }}
        >
          <div>
            <h1 style={{ margin: 0, fontSize: 'clamp(18px, 4vw, 22px)', fontWeight: 'bold' }}>
              🔗 Riconciliazione Unificata
            </h1>
            <p style={{ margin: '4px 0 0', opacity: 0.9, fontSize: 13 }}>
              Associa movimenti bancari a fatture, F24, stipendi e assegni
            </p>
          </div>
        </div>
        <div style={{ padding: 40, textAlign: 'center', background: 'white', borderRadius: 8, border: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⏳</div>
          <div style={{ color: '#64748b' }}>Caricamento riconciliazione...</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', padding: '16px' }}>
      {loadError && (
        <div
          style={{
            marginBottom: 16,
            padding: '12px 16px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: 8,
            color: '#991b1b',
            fontSize: 13,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span>⚠️ {loadError}</span>
          <button
            onClick={() => loadAllData(currentLimit)}
            style={{
              padding: '6px 12px',
              background: '#991b1b',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            Riprova
          </button>
        </div>
      )}
      {/* Action Bar - senza cornice blu */}
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <button
          onClick={eseguiAutoRiparazione}
          disabled={autoRepairRunning}
          data-testid="btn-auto-repair"
          style={{
            padding: '8px 14px',
            minHeight: 40,
            flex: isMobile ? '1 1 auto' : '0 1 auto',
            background: autoRepairRunning ? '#9ca3af' : '#0f2744',
            color: 'white',
            border: '1px solid #0f2744',
            borderRadius: 6,
            fontWeight: 600,
            fontSize: 13,
            cursor: autoRepairRunning ? 'wait' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {autoRepairRunning ? '⏳ Riparazione...' : '🔧 Auto-Ripara'}
        </button>
        {autoRepairStatus && autoRepairStatus.riconciliazioni_auto > 0 && (
          <span
            style={{
              padding: '6px 10px',
              background: '#dcfce7',
              color: '#16a34a',
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            ✓ {autoRepairStatus.riconciliazioni_auto} riparazioni
          </span>
        )}

        {/* Pulsante Auto-Riconcilia */}
        <button
          onClick={handleAutoRiconcilia}
          disabled={processing}
          style={{
            padding: '8px 14px',
            minHeight: 40,
            flex: isMobile ? '1 1 auto' : '0 1 auto',
            background: '#0f2744',
            color: 'white',
            border: '1px solid #0f2744',
            borderRadius: 6,
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {processing === 'auto' ? '⏳' : '⚡'} Auto-Riconcilia
        </button>
        <button
          onClick={() => loadAllData(currentLimit)}
          disabled={processing}
          style={{
            padding: '8px 14px',
            minHeight: 40,
            flex: isMobile ? '1 1 auto' : '0 1 auto',
            background: 'white',
            color: '#0f2744',
            border: '1px solid #e2e8f0',
            borderRadius: 6,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 13,
            whiteSpace: 'nowrap',
          }}
        >
          🔄 Aggiorna
        </button>

        {/* Bottone Filtri */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          style={{
            padding: '8px 14px',
            minHeight: 40,
            flex: isMobile ? '1 1 auto' : '0 1 auto',
            background: showFilters ? '#0f2744' : 'white',
            color: showFilters ? 'white' : '#0f2744',
            border: `1px solid ${showFilters ? '#0f2744' : '#e2e8f0'}`,
            borderRadius: 6,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 13,
            whiteSpace: 'nowrap',
          }}
        >
          🔍 Filtri {showFilters ? '▲' : '▼'}
        </button>
      </div>

      {/* Pannello Filtri Avanzati */}
      {showFilters && (
        <div
          style={{
            background: 'white',
            borderRadius: 8,
            padding: 16,
            marginBottom: 16,
            border: '1px solid #e2e8f0',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
              📅 Data Da
            </label>
            <input
              type="date"
              value={filters.dataFrom}
              onChange={e => setFilters({ ...filters, dataFrom: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
              📅 Data A
            </label>
            <input
              type="date"
              value={filters.dataTo}
              onChange={e => setFilters({ ...filters, dataTo: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
              Importo Min (€)
            </label>
            <input
              type="number"
              placeholder="0"
              value={filters.importoMin}
              onChange={e => setFilters({ ...filters, importoMin: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
              Importo Max (€)
            </label>
            <input
              type="number"
              placeholder="999999"
              value={filters.importoMax}
              onChange={e => setFilters({ ...filters, importoMax: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
              🔎 Cerca
            </label>
            <input
              type="text"
              placeholder="Descrizione, tipo..."
              value={filters.search}
              onChange={e => setFilters({ ...filters, search: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              onClick={() =>
                setFilters({ dataFrom: '', dataTo: '', importoMin: '', importoMax: '', search: '' })
              }
              style={{
                padding: '8px 16px',
                minHeight: 40,
                background: '#fee2e2',
                color: '#dc2626',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 13,
              }}
            >
              ✕ Reset
            </button>
          </div>
        </div>
      )}

      {/* Tab Navigation — stessa grafica delle barre tab degli hub:
          attivo navy pieno, inattivo bianco con bordo. Su mobile i bottoni
          riempiono la riga in modo uniforme con font ridotto.
          PAGINA F24 (richiesta utente 10/07): quando si è su /riconciliazione/f24
          si vedono SOLO gli F24 — niente barra tab (dashboard, banca, stipendi,
          documenti, PayPal hanno il loro posto altrove) e F24 non compare
          nemmeno come tab della pagina Riconciliazione. */}
      {activeTab !== 'f24' && (
      <div
        style={{
          display: 'flex',
          gap: isMobile ? 6 : 8,
          marginBottom: 20,
          flexWrap: 'wrap',
          background: 'white',
          padding: 8,
          borderRadius: 8,
          border: '1px solid #e2e8f0',
        }}
      >
        {TABS.filter(t => t.id !== 'f24').map(tab => {
          const count = tab.id === 'dashboard' ? null : (stats[tab.id] ?? null);
          const attivo = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              style={{
                padding: isMobile ? '8px 8px' : '9px 13px',
                minHeight: 40,
                flex: isMobile ? '1 1 auto' : '0 1 auto',
                justifyContent: 'center',
                background: attivo ? tab.color : '#fff',
                color: attivo ? 'white' : '#64748b',
                border: `1px solid ${attivo ? tab.color : '#e2e8f0'}`,
                borderRadius: 6,
                fontWeight: attivo ? 700 : 500,
                cursor: 'pointer',
                fontSize: isMobile ? 11.5 : 12,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                whiteSpace: 'nowrap',
              }}
            >
              {tab.label}
              {count !== null && (
                <span
                  style={{
                    background: attivo ? 'rgba(255,255,255,0.3)' : tab.color,
                    color: 'white',
                    padding: '2px 8px',
                    borderRadius: 10,
                    fontSize: 11,
                  }}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      )}

      {/* Tab Content */}
      <div
        style={{
          background: 'white',
          borderRadius: 8,
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
        }}
      >
        {activeTab === 'dashboard' && (
          <DashboardTab stats={stats} autoMatchStats={autoMatchStats} />
        )}
        {activeTab === 'banca' && (
          <MovimentiTab
            movimenti={movimentiBancaFiltrati}
            onConferma={handleConferma}
            onIgnora={handleIgnora}
            onElimina={handleElimina}
            processing={processing}
            title="Movimenti Bancari"
            emptyText="Tutti i movimenti sono stati riconciliati"
            vistaLista
          />
        )}
        {activeTab === 'assegni' && (
          <MovimentiTab
            movimenti={assegniFiltrati}
            onConferma={handleIncassaAssegno}
            onIgnora={handleIgnora}
            onElimina={handleElimina}
            processing={processing}
            title="Prelievi Assegno"
            emptyText="Nessun assegno da riconciliare"
            showFattura
          />
        )}
        {activeTab === 'f24' && (
          <F24Tab
            f24={f24Pendenti}
            processing={processing}
            onLoadF24={loadF24OnDemand}
            f24Loading={f24Loading}
            onRefresh={loadAllData}
            anno={anno}
          />
        )}
        {activeTab === 'stipendi' && (
          <MovimentiTab
            movimenti={stipendiFiltrati}
            onConferma={m => handleConferma(m, 'stipendio')}
            onIgnora={handleIgnora}
            onElimina={handleElimina}
            processing={processing}
            title="Stipendi"
            emptyText="Nessuno stipendio da riconciliare"
          />
        )}
        {activeTab === 'documenti' && (
          <DocumentiTab
            documenti={documentiNonAssociati}
            stats={documentiStats}
            onRefresh={loadAllData}
            processing={processing}
          />
        )}
        {activeTab === 'paypal' && (
          <Suspense
            fallback={
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    border: '3px solid #e2e8f0',
                    borderTop: '3px solid #0f2744',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto 12px',
                  }}
                />
                Caricamento PayPal...
              </div>
            }
          >
            <div style={{ padding: 20 }}>
              <RiconciliazionePaypalLazy />
            </div>
          </Suspense>
        )}
      </div>

      {/* Bottone Carica Altri */}
      {hasMore && ['banca', 'assegni', 'stipendi'].includes(activeTab) && (
        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <button
            onClick={loadMore}
            disabled={loadingMore}
            style={{
              padding: '12px 28px',
              minHeight: 40,
              background: loadingMore ? '#94a3b8' : '#0f2744',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              fontWeight: 600,
              fontSize: 13,
              cursor: loadingMore ? 'wait' : 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {loadingMore ? '⏳ Caricamento...' : `📥 Carica altri (${currentLimit} caricati)`}
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================
// TAB COMPONENTS
// ============================================

function DashboardTab({ stats, autoMatchStats }) {
  return (
    <div style={{ padding: 24, textAlign: 'center' }}>
      <div
        style={{
          padding: 40,
          background: '#0f2744',
          borderRadius: 8,
          color: 'white',
          maxWidth: 500,
          margin: '0 auto',
        }}
      >
        <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
        <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>Riconciliazione</div>
        <div style={{ fontSize: 14, opacity: 0.9, marginBottom: 16 }}>
          Seleziona una sezione dal menu per iniziare la riconciliazione
        </div>
        {autoMatchStats.matched > 0 && (
          <div
            style={{
              fontSize: 13,
              marginTop: 16,
              padding: '8px 16px',
              background: 'rgba(255,255,255,0.2)',
              borderRadius: 8,
              display: 'inline-block',
            }}
          >
            ✅ {autoMatchStats.matched} elementi auto-riconciliati
          </div>
        )}
      </div>
    </div>
  );
}

function MovimentiTab({
  movimenti,
  onConferma,
  onIgnora,
  onElimina,
  processing,
  title,
  emptyText,
  showFattura,
  // vistaLista: solo la tab Banca usa ListaAdattiva (tabella su desktop,
  // card compatte su mobile); le altre tab restano su MovimentoCard.
  vistaLista = false,
}) {
  const isMobile = useIsMobile();

  if (movimenti.length === 0) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>
        <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}>✅</div>
        <div>{emptyText}</div>
      </div>
    );
  }

  // Azioni per riga: stessi bottoni (e stili) di MovimentoCard
  const renderAzioni = m => {
    const inCorso = processing === m.movimento_id || processing === m.id;
    return (
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <button
          onClick={() => onConferma(m)}
          disabled={inCorso}
          style={{
            padding: '8px 16px',
            minHeight: 40,
            background: '#0f2744',
            color: 'white',
            border: 'none',
            borderRadius: 6,
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          {inCorso ? '⏳' : '✓'} Conferma
        </button>
        <button
          onClick={() => onIgnora(m)}
          disabled={inCorso}
          style={{
            padding: '8px 12px',
            minHeight: 40,
            minWidth: 40,
            background: 'white',
            color: '#64748b',
            border: '1px solid #e2e8f0',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          ✕
        </button>
        {onElimina && (
          <button
            onClick={() => onElimina(m)}
            disabled={inCorso}
            data-testid="btn-elimina-movimento"
            title="Elimina definitivamente"
            style={{
              padding: '8px 12px',
              minHeight: 40,
              minWidth: 40,
              background: '#fee2e2',
              color: '#dc2626',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            🗑️
          </button>
        )}
      </div>
    );
  };

  const nominativoDi = m =>
    m.ragione_sociale ||
    m.fornitore ||
    m.dipendente?.nome_completo ||
    m.dipendente ||
    m.nome_estratto;

  return (
    <div>
      <div style={{ padding: 16, background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#0f2744' }}>
          {title} ({movimenti.length})
        </h3>
      </div>
      {vistaLista ? (
        <div style={{ padding: isMobile ? '0 10px 10px' : 0 }}>
          {/* pageSize alto (200): la paginazione vera resta quella lato server
              ("Carica altri" sotto il tab, currentLimit/hasMore) — così la barra
              interna di ListaAdattiva non si sovrappone finché non superiamo
              200 righe caricate. */}
          <ListaAdattiva
            testId="movimenti-banca-lista"
            dati={movimenti}
            pageSize={200}
            chiave={(m, i) => m.movimento_id || m.id || i}
            colonne={[
              {
                key: 'data',
                label: 'Data',
                ruoloCard: 'dettaglio',
                iconaCard: '📅',
                // Su mobile solo giorno/mese (l'anno è nel selettore globale)
                render: m => {
                  const d = m.data || m.data_emissione;
                  if (!d) return 'Data N/D';
                  return isMobile ? formatDateGGMM(d) : formatDateIT(d);
                },
                tdStyle: { whiteSpace: 'nowrap', fontSize: 13 },
              },
              {
                key: 'nominativo',
                label: 'Nominativo',
                ruoloCard: 'sottotitolo',
                render: m => nominativoDi(m) || '-',
                tdStyle: { fontWeight: 700, color: '#1e293b', fontSize: 13 },
              },
              {
                key: 'descrizione',
                label: 'Descrizione',
                ruoloCard: 'titolo',
                render: m => {
                  const desc =
                    m.descrizione?.substring(0, 100) ||
                    m.descrizione_originale?.substring(0, 100) ||
                    '-';
                  if (isMobile) return desc.substring(0, 60);
                  const numeroFattura = m.numero_fattura || m.fattura_collegata;
                  return (
                    <div>
                      <div style={{ fontSize: 12, color: '#94a3b8', fontWeight: 400 }}>{desc}</div>
                      {m.periodo && (
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                          Periodo: {m.periodo || m.mese_riferimento}
                        </div>
                      )}
                      {numeroFattura && (
                        <div style={{ fontSize: 11, color: '#3b82f6', marginTop: 2 }}>
                          📄 Fattura: {numeroFattura}
                        </div>
                      )}
                      {m.beneficiario && (
                        <div style={{ fontSize: 11, color: '#d97706', marginTop: 2 }}>
                          👤 Beneficiario: {m.beneficiario}
                        </div>
                      )}
                    </div>
                  );
                },
              },
              {
                key: 'stato',
                label: 'Stato',
                ruoloCard: 'dettaglio',
                render: m => {
                  const sugg = m.suggerimenti?.[0];
                  const hasMatch = m.associazione_automatica && sugg;
                  const datiIncompleti = m.dati_incompleti || m.stato === 'vuoto';
                  if (hasMatch) {
                    return (
                      <span
                        style={{
                          padding: '2px 8px',
                          background: '#dcfce7',
                          color: '#16a34a',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        ✅ Match:{' '}
                        {sugg.fornitore || sugg.nome || sugg.dipendente || 'Match'}{' '}
                        {formatEuro(sugg.importo || 0)}
                      </span>
                    );
                  }
                  if (datiIncompleti) {
                    return (
                      <span
                        style={{
                          padding: '2px 8px',
                          background: '#fef3c7',
                          color: '#92400e',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        ⚠️ Dati incompleti
                      </span>
                    );
                  }
                  return (
                    <span
                      style={{
                        padding: '2px 8px',
                        background: '#f1f5f9',
                        color: '#64748b',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Da riconciliare
                    </span>
                  );
                },
              },
              {
                key: 'importo',
                label: 'Importo',
                align: 'right',
                mono: true,
                ruoloCard: 'importo',
                render: m => (
                  <span
                    style={{
                      color: m.importo < 0 ? '#dc2626' : '#16a34a',
                      fontWeight: 700,
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {/* Su mobile il segno rende esplicito entrata/uscita;
                        su desktop resta il valore assoluto come prima */}
                    {isMobile
                      ? `${m.importo < 0 ? '-' : '+'}${formatEuro(Math.abs(m.importo || 0))}`
                      : m.importo
                        ? formatEuro(Math.abs(m.importo))
                        : '€ 0,00'}
                  </span>
                ),
              },
              {
                key: 'movimento_id',
                label: 'ID',
                mono: true,
                ruoloCard: 'omesso',
                render: m => m.movimento_id || m.id || '-',
                tdStyle: { fontSize: 11, color: '#94a3b8' },
              },
              {
                key: 'azioni',
                label: 'Azioni',
                align: 'center',
                ruoloCard: 'azioni',
                render: renderAzioni,
              },
            ]}
          />
        </div>
      ) : (
        <div>
          {movimenti.map((m, idx) => (
            <MovimentoCard
              key={m.movimento_id || m.id || idx}
              movimento={m}
              onConferma={onConferma}
              onIgnora={onIgnora}
              onElimina={onElimina}
              processing={processing === m.movimento_id || processing === m.id}
              showFattura={showFattura}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function MovimentoCard({ movimento, onConferma, onIgnora, onElimina, processing, showFattura }) {
  const suggerimento = movimento.suggerimenti?.[0];
  const hasMatch = movimento.associazione_automatica && suggerimento;

  // Estrai info extra dal movimento
  const ragioneSociale =
    movimento.ragione_sociale ||
    movimento.fornitore ||
    movimento.dipendente?.nome_completo ||
    movimento.dipendente ||
    movimento.nome_estratto;
  const numeroFattura = movimento.numero_fattura || movimento.fattura_collegata;
  const datiIncompleti = movimento.dati_incompleti || movimento.stato === 'vuoto';

  return (
    <div
      style={{
        padding: 16,
        borderBottom: '1px solid #f1f5f9',
        opacity: processing ? 0.5 : 1,
        background: hasMatch ? '#f0fdf4' : datiIncompleti ? '#fef3c7' : 'white',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: hasMatch
              ? '#dcfce7'
              : datiIncompleti
                ? '#fef3c7'
                : ragioneSociale
                  ? '#e0f2fe'
                  : '#f1f5f9',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
          }}
        >
          {hasMatch ? '✅' : datiIncompleti ? '⚠️' : ragioneSociale ? '👤' : '📝'}
        </div>

        <div style={{ flex: 1 }}>
          {/* NOME DIPENDENTE/FORNITORE - In evidenza */}
          {ragioneSociale && (
            <div
              style={{
                fontWeight: 700,
                fontSize: 15,
                color: '#1e293b',
                marginBottom: 4,
              }}
            >
              {ragioneSociale}
            </div>
          )}

          <div
            style={{
              fontWeight: 500,
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: '#64748b',
            }}
          >
            <span>
              {movimento.data || movimento.data_emissione
                ? formatDateIT(movimento.data || movimento.data_emissione)
                : 'Data N/D'}
            </span>
            <span>•</span>
            <span
              style={{
                color: movimento.importo < 0 ? '#dc2626' : '#16a34a',
                fontWeight: 700,
                fontSize: 15,
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              }}
            >
              {movimento.importo ? formatEuro(Math.abs(movimento.importo)) : '€ 0,00'}
            </span>
            {movimento.periodo && (
              <>
                <span>•</span>
                <span style={{ fontSize: 11, color: '#64748b' }}>
                  Periodo: {movimento.periodo || movimento.mese_riferimento}
                </span>
              </>
            )}
            {datiIncompleti && (
              <span
                style={{
                  fontSize: 10,
                  padding: '2px 6px',
                  background: '#fef3c7',
                  color: '#92400e',
                  borderRadius: 4,
                  fontWeight: 500,
                }}
              >
                DATI INCOMPLETI
              </span>
            )}
          </div>

          {/* Descrizione */}
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
            {movimento.descrizione?.substring(0, 100) ||
              movimento.descrizione_originale?.substring(0, 100) ||
              '-'}
          </div>

          {/* Numero Fattura */}
          {numeroFattura && (
            <div
              style={{
                marginTop: 2,
                fontSize: 11,
                color: '#3b82f6',
              }}
            >
              📄 Fattura: {numeroFattura}
            </div>
          )}

          {/* Info assegno se presente */}
          {movimento.numero_assegno && (
            <div
              style={{
                marginTop: 4,
                fontSize: 11,
                color: '#d97706',
                display: 'flex',
                flexWrap: 'wrap',
                gap: 8,
                alignItems: 'center',
              }}
            >
              <span>📝 Assegno N. {movimento.numero_assegno}</span>
              <span>• Stato: {movimento.stato || 'N/D'}</span>
              {movimento.beneficiario && (
                <span style={{ color: '#3b82f6', fontWeight: 600 }}>
                  • 👤 {movimento.beneficiario}
                </span>
              )}
              {movimento.fornitore && !movimento.beneficiario && (
                <span style={{ color: '#3b82f6', fontWeight: 600 }}>
                  • 👤 {movimento.fornitore}
                </span>
              )}
            </div>
          )}

          {/* Confronto importi per assegni con fattura */}
          {movimento.numero_assegno && movimento.numero_fattura && (
            <div
              style={{
                marginTop: 6,
                padding: '6px 10px',
                background: '#fef3c7',
                borderRadius: 6,
                fontSize: 11,
                display: 'inline-flex',
                flexWrap: 'wrap',
                gap: 12,
                alignItems: 'center',
              }}
            >
              <span>
                <b>Assegno:</b> {formatEuro(Math.abs(movimento.importo || 0))}
              </span>
              {movimento.importo_fattura !== undefined && (
                <>
                  <span>•</span>
                  <span>
                    📄 <b>Fattura:</b> {formatEuro(Math.abs(movimento.importo_fattura || 0))}
                  </span>
                  {Math.abs((movimento.importo || 0) - (movimento.importo_fattura || 0)) > 0.01 && (
                    <>
                      <span>•</span>
                      <span style={{ color: '#dc2626', fontWeight: 600 }}>
                        ⚠️ Diff:{' '}
                        {formatEuro(
                          Math.abs((movimento.importo || 0) - (movimento.importo_fattura || 0))
                        )}
                      </span>
                    </>
                  )}
                </>
              )}
              {/* Info pagamento rateale */}
              {movimento.info_rate && movimento?.info_rate?.numero_rate > 1 && (
                <div
                  style={{
                    width: '100%',
                    marginTop: 4,
                    padding: '4px 8px',
                    background: '#dbeafe',
                    borderRadius: 4,
                    color: '#1e40af',
                  }}
                >
                  📊 <b>Pagamento in {movimento?.info_rate?.numero_rate} rate</b>: Totale rate{' '}
                  {formatEuro(movimento.info_rate.totale_rate)}
                  {movimento.importo_fattura > 0 && (
                    <span> su fattura di {formatEuro(movimento.importo_fattura)}</span>
                  )}
                </div>
              )}
              {/* Nota TD24 */}
              {movimento.nota_td24 && (
                <div
                  style={{
                    width: '100%',
                    marginTop: 4,
                    padding: '4px 8px',
                    background: '#dbeafe',
                    borderRadius: 4,
                    color: '#1e40af',
                  }}
                >
                  ℹ️ {movimento.nota_td24}
                </div>
              )}
            </div>
          )}

          {/* Info beneficiario per assegni senza numero */}
          {!movimento.numero_assegno && movimento.beneficiario && (
            <div
              style={{
                marginTop: 2,
                fontSize: 11,
                color: '#d97706',
              }}
            >
              👤 Beneficiario: {movimento.beneficiario}
            </div>
          )}

          {hasMatch && suggerimento && (
            <div
              style={{
                marginTop: 8,
                padding: '6px 10px',
                background: '#dcfce7',
                borderRadius: 6,
                fontSize: 12,
                display: 'inline-block',
              }}
            >
              🔗 {suggerimento.fornitore || suggerimento.nome || suggerimento.dipendente || 'Match'}
              : {formatEuro(suggerimento.importo || 0)}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={() => onConferma(movimento)}
            disabled={processing}
            style={{
              padding: '8px 16px',
              minHeight: 40,
              background: '#0f2744',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {processing ? '⏳' : '✓'} Conferma
          </button>
          <button
            onClick={() => onIgnora(movimento)}
            disabled={processing}
            style={{
              padding: '8px 12px',
              minHeight: 40,
              minWidth: 40,
              background: 'white',
              color: '#64748b',
              border: '1px solid #e2e8f0',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            ✕
          </button>
          {onElimina && (
            <button
              onClick={() => onElimina(movimento)}
              disabled={processing}
              data-testid="btn-elimina-movimento"
              title="Elimina definitivamente"
              style={{
                padding: '8px 12px',
                minHeight: 40,
                minWidth: 40,
                background: '#fee2e2',
                color: '#dc2626',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              🗑️
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Tabella §20 della specifica F24 (memoria/SPECIFICA_F24_CEDOLINI_...) ──
// Periodo di competenza, scadenza naturale, data pagamento, giorni di
// ritardo, stato, tipo versamento, causale INPS, documento collegato,
// possibile duplicazione e motivazione automatica. Il "pagato in ritardo"
// è evidenziato con scadenza naturale e data effettiva, come da specifica.
const STILI_STATO_F24 = {
  pagato_nei_termini: { label: '✅ Pagato nei termini', bg: '#dcfce7', color: '#166534' },
  pagato_in_ritardo: { label: '⚠️ PAGATO IN RITARDO', bg: '#fee2e2', color: '#991b1b' },
  non_pagato: { label: '❌ Non pagato', bg: '#ffedd5', color: '#9a3412' },
  in_scadenza: { label: '🕐 In scadenza', bg: '#dbeafe', color: '#1e40af' },
  periodo_ignoto: { label: '❓ Periodo ignoto', bg: '#f1f5f9', color: '#64748b' },
};

const STILI_DUP_F24 = {
  da_verificare: { label: '🚨 Da verificare', bg: '#fee2e2', color: '#991b1b' },
  collegato_no_duplicato: { label: '🔗 Collegato (no doppio)', bg: '#dbeafe', color: '#1e40af' },
  no: { label: 'No', bg: '#f1f5f9', color: '#64748b' },
};

function TabellaAnalisiF24({ anno }) {
  const [righe, setRighe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errore, setErrore] = useState(null);
  const [soloAnno, setSoloAnno] = useState(true);

  const carica = async filtraAnno => {
    setLoading(true);
    setErrore(null);
    try {
      const qs = filtraAnno && anno ? `?anno=${anno}` : '';
      const res = await api.get(`/api/f24-analisi/tabella${qs}`);
      setRighe(res.data.righe || []);
    } catch (e) {
      setErrore(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const cellaTh = {
    padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11,
    color: '#64748b', textTransform: 'uppercase', whiteSpace: 'nowrap',
  };
  const cella = { padding: '6px 8px', fontSize: 12, verticalAlign: 'top' };

  return (
    <div style={{ padding: 16, borderBottom: '1px solid #e2e8f0', background: 'white' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 15, color: '#0f2744' }}>
          📋 Analisi F24 — scadenze, ravvedimenti e duplicazioni
        </h3>
        <button
          data-testid="btn-carica-analisi-f24"
          onClick={() => carica(soloAnno)}
          disabled={loading}
          style={{
            padding: '8px 14px', minHeight: 38, background: '#0f2744', color: 'white',
            border: 'none', borderRadius: 6, cursor: loading ? 'wait' : 'pointer',
            fontWeight: 600, fontSize: 12.5,
          }}
        >
          {loading ? '⏳ Analizzo…' : righe ? '🔄 Ricarica' : '📊 Carica analisi'}
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12.5, color: '#334155', cursor: 'pointer' }}>
          <input type="checkbox" checked={soloAnno} onChange={e => setSoloAnno(e.target.checked)} />
          Solo anno {anno}
        </label>
        {righe && (
          <span style={{ fontSize: 12, color: '#64748b' }}>
            {righe.length} modelli · in ritardo:{' '}
            {righe.filter(r => r.stato_pagamento === 'pagato_in_ritardo').length} · possibili
            duplicazioni: {righe.filter(r => r.possibile_duplicazione === 'da_verificare').length}
          </span>
        )}
      </div>

      {errore && (
        <div style={{ marginTop: 10, fontSize: 13, color: '#dc2626', fontWeight: 600 }}>
          ⚠️ {errore}
        </div>
      )}

      {righe && righe.length === 0 && (
        <div style={{ marginTop: 12, fontSize: 13, color: '#64748b' }}>
          Nessun F24 trovato{soloAnno ? ` per l'anno ${anno}` : ''}.
        </div>
      )}

      {righe && righe.length > 0 && (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                <th style={cellaTh}>Periodo competenza</th>
                <th style={cellaTh}>Scadenza naturale</th>
                <th style={cellaTh}>Pagamento effettivo</th>
                <th style={{ ...cellaTh, textAlign: 'center' }}>Giorni ritardo</th>
                <th style={cellaTh}>Stato pagamento</th>
                <th style={cellaTh}>Tipo versamento</th>
                <th style={cellaTh}>Causale INPS</th>
                <th style={cellaTh}>Documento collegato</th>
                <th style={cellaTh}>Possibile duplicazione</th>
                <th style={cellaTh}>Motivazione</th>
              </tr>
            </thead>
            <tbody>
              {righe.map((r, idx) => {
                const stato = STILI_STATO_F24[r.stato_pagamento] || STILI_STATO_F24.periodo_ignoto;
                const dup = STILI_DUP_F24[r.possibile_duplicazione] || STILI_DUP_F24.no;
                const inRitardo = r.stato_pagamento === 'pagato_in_ritardo';
                return (
                  <tr
                    key={r.f24_id || idx}
                    data-testid={`riga-analisi-f24-${r.f24_id || idx}`}
                    style={{
                      borderBottom: '1px solid #f1f5f9',
                      background: inRitardo ? '#fff7f7' : idx % 2 ? '#f8fafc' : 'white',
                    }}
                  >
                    <td style={{ ...cella, fontWeight: 700, whiteSpace: 'nowrap' }}>
                      {r.periodo_competenza || '—'}
                      {r.file && (
                        <div style={{ fontSize: 10.5, color: '#94a3b8', fontWeight: 400, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {r.file}
                        </div>
                      )}
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap', fontFamily: 'monospace' }}>
                      {r.scadenza_naturale || '—'}
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap', fontFamily: 'monospace', fontWeight: inRitardo ? 700 : 400, color: inRitardo ? '#991b1b' : '#0f172a' }}>
                      {r.data_pagamento || '—'}
                    </td>
                    <td style={{ ...cella, textAlign: 'center', fontWeight: 700, color: r.giorni_ritardo > 0 ? '#dc2626' : '#16a34a' }}>
                      {r.giorni_ritardo ?? '—'}
                    </td>
                    <td style={cella}>
                      <span style={{ padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700, background: stato.bg, color: stato.color, whiteSpace: 'nowrap' }}>
                        {stato.label}
                      </span>
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap' }}>
                      {r.tipo_versamento === 'ordinario' ? 'Ordinario'
                        : r.tipo_versamento === 'regolarizzazione' ? '🔁 Regolarizzazione'
                          : '🔁 Ravvedimento'}
                    </td>
                    <td style={{ ...cella, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                      {(r.causali_inps || []).join(', ') || '—'}
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap' }}>
                      {r.documento_collegato?.quietanza_id ? '🧾 Quietanza' : '—'}
                    </td>
                    <td style={cella}>
                      <span style={{ padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700, background: dup.bg, color: dup.color, whiteSpace: 'nowrap' }}>
                        {dup.label}
                      </span>
                    </td>
                    <td style={{ ...cella, minWidth: 220, color: '#475569' }}>{r.motivazione}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function F24Tab({ f24, onConfermaF24, processing, onLoadF24, f24Loading, onRefresh, anno }) {
  const [selezionati, setSelezionati] = useState(new Set());
  const [pdfViewer, setPdfViewer] = useState(null); // {title, src} — viewer canonico §8
  const [metodoBatch] = useState('banca');
  const [salvandoBatch, setSalvandoBatch] = useState(false);
  const confirm = useConfirm();

  // Filtra F24 con importo > 0
  const f24Validi = f24.filter(f => (f.importo_totale || f.importo || 0) > 0);

  if (f24Validi.length === 0) {
    return (
      <div>
      <TabellaAnalisiF24 anno={anno} />
      <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>
        <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}>📄</div>
        <div>Nessun F24 pendente da pagare</div>
        {onLoadF24 && (
          <button
            data-testid="btn-carica-f24"
            onClick={onLoadF24}
            disabled={f24Loading}
            style={{
              marginTop: 16,
              padding: '10px 20px',
              minHeight: 40,
              background: '#0f2744',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: f24Loading ? 'wait' : 'pointer',
              fontWeight: 600,
              fontSize: 13,
            }}
          >
            {f24Loading ? '⏳ Caricamento F24...' : '🔍 Carica F24 pendenti'}
          </button>
        )}
      </div>
      </div>
    );
  }

  const totale = f24Validi.reduce((sum, f) => sum + (f.importo_totale || f.importo || 0), 0);
  const totaleSelezionati = f24Validi
    .filter(f => selezionati.has(f.id))
    .reduce((sum, f) => sum + (f.importo_totale || f.importo || 0), 0);

  const toggleSelezione = id => {
    setSelezionati(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const toggleTutti = () => {
    if (selezionati.size === f24Validi.length) {
      setSelezionati(new Set());
    } else {
      setSelezionati(new Set(f24Validi.map(f => f.id)));
    }
  };

  const confermaBatch = async () => {
    if (selezionati.size === 0) {
      toast.error('Seleziona almeno un F24');
      return;
    }

    setSalvandoBatch(true);
    try {
      const operazioni = f24Validi
        .filter(f => selezionati.has(f.id))
        .map(f => ({
          operazione_id: f.id,
          metodo_pagamento: metodoBatch,
          tipo: 'f24',
        }));

      await api.post('/api/operazioni-da-confermare/smart/conferma-f24', { operazioni });
      toast.success(`Confermati ${selezionati.size} F24`);
      setSelezionati(new Set());
      // Ricarica dati senza reload pagina
      onRefresh?.();
    } catch (e) {
      toast.error('Conferma F24 non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setSalvandoBatch(false);
    }
  };

  const confermaF24Singolo = async (f24Item, metodo) => {
    try {
      await api.post('/api/operazioni-da-confermare/smart/conferma-f24', {
        operazioni: [
          {
            operazione_id: f24Item.id,
            metodo_pagamento: metodo,
            tipo: 'f24',
          },
        ],
      });
      toast.success('F24 confermato');
      onRefresh?.();
    } catch (e) {
      toast.error('Conferma F24 non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    }
  };

  return (
    <div>
      <TabellaAnalisiF24 anno={anno} />
      <div style={{ padding: 16, background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 16, color: '#0f2744' }}>
            📄 F24 Pendenti ({f24Validi.length})
          </h3>
          <div
            style={{
              fontWeight: 700,
              color: '#dc2626',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            Totale: {formatEuro(totale)}
          </div>
        </div>

        {/* Azioni batch */}
        <div
          style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}
        >
          <button
            onClick={toggleTutti}
            style={{
              padding: '8px 12px',
              minHeight: 40,
              background: 'white',
              color: '#1e293b',
              border: '1px solid #e2e8f0',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {selezionati.size === f24Validi.length ? '☐ Deseleziona' : '☑ Seleziona tutti'}
          </button>

          {selezionati.size > 0 && (
            <>
              <span
                style={{
                  padding: '8px 12px',
                  border: '1px solid #dc2626',
                  borderRadius: 6,
                  fontSize: 13,
                  background: '#fee2e2',
                  fontWeight: 600,
                  color: '#991b1b',
                }}
              >
                🏦 Pagamento Banca
              </span>

              <button
                onClick={confermaBatch}
                disabled={salvandoBatch}
                style={{
                  padding: '8px 16px',
                  minHeight: 40,
                  background: '#0f2744',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: 13,
                }}
              >
                {salvandoBatch ? '⏳' : '✅'} Conferma {selezionati.size} (
                {formatEuro(totaleSelezionati)})
              </button>
            </>
          )}
        </div>
      </div>

      <div>
        {f24Validi.map((f, idx) => {
          const importo = f.importo_totale || f.importo || 0;
          const scadenzaStr = formatDateIT(f.data_scadenza);

          return (
            <div
              key={f.id || idx}
              style={{
                padding: 16,
                borderBottom: '1px solid #f1f5f9',
                background: selezionati.has(f.id) ? '#fef2f2' : 'white',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: 12,
                }}
              >
                {/* Checkbox */}
                <input
                  type="checkbox"
                  checked={selezionati.has(f.id)}
                  onChange={() => toggleSelezione(f.id)}
                  style={{ marginTop: 4, width: 18, height: 18, cursor: 'pointer' }}
                />

                {/* Info F24 */}
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>
                    {f.contribuente || 'F24'}
                    {f.codici_tributo?.length > 0 && (
                      <span style={{ fontSize: 12, color: '#64748b', marginLeft: 8 }}>
                        Tributi: {f.codici_tributo.join(', ')}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                    Periodo: {f.periodo || '-'} • Scadenza: {scadenzaStr}
                  </div>
                </div>

                {/* Importo e azioni */}
                <div style={{ textAlign: 'right' }}>
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 18,
                      color: '#dc2626',
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    }}
                  >
                    {formatEuro(importo)}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      gap: 4,
                      marginTop: 8,
                      justifyContent: 'flex-end',
                      flexWrap: 'wrap',
                    }}
                  >
                    <button
                      onClick={() => confermaF24Singolo(f, 'banca')}
                      style={{
                        padding: '4px 10px',
                        minHeight: 40,
                        background: '#16a34a',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                      }}
                      title="Conferma pagamento F24 tramite Banca"
                    >
                      🏦 Paga con Banca
                    </button>
                    <button
                      onClick={async () => {
                        if (f.pdf_url) {
                          setPdfViewer({ title: `📄 F24 ${f.descrizione || f.numero || ''}`, src: f.pdf_url });
                        } else if (f.file_path) {
                          setPdfViewer({
                            title: `📄 F24 ${f.descrizione || f.numero || ''}`,
                            src: `/api/download/${encodeURIComponent(f.file_path)}`,
                          });
                        } else {
                          await confirm({
                            title: 'PDF non disponibile',
                            message: 'Carica il PDF F24 dalla sezione Import per poterlo visualizzare.',
                            confirmText: 'Ho capito',
                            cancelText: null,
                          });
                        }
                      }}
                      style={{
                        padding: '4px 10px',
                        minHeight: 40,
                        background: f.pdf_url || f.file_path ? '#0f2744' : '#94a3b8',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                      }}
                      title={
                        f.pdf_url || f.file_path ? 'Visualizza PDF F24' : 'PDF non disponibile'
                      }
                    >
                      👁️ Vedi PDF
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {pdfViewer && (
        <DocumentViewerModal
          title={pdfViewer.title}
          src={pdfViewer.src}
          documentType="f24"
          onClose={() => setPdfViewer(null)}
        />
      )}
    </div>
  );
}

function DocumentiTab({ documenti, stats, onRefresh, processing }) {
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [pdfViewer, setPdfViewer] = useState(null); // {title, src} — viewer canonico §8
  const [collezioni, setCollezioni] = useState([]);
  const [associazioneForm, setAssociazioneForm] = useState({ collezione: '', campiJson: '' });
  const [message, setMessage] = useState(null);
  const [loadingCollezioni, setLoadingCollezioni] = useState(false);
  const confirm = useConfirm();

  // Documenti associati di recente (per poter annullare un'associazione
  // sbagliata — richiesta utente 18/07/2026: "ho cliccato F24 ed ho
  // sbagliato, come riclassifico?" prima non c'era modo di tornare
  // indietro).
  const [recenti, setRecenti] = useState([]);
  const [mostraRecenti, setMostraRecenti] = useState(false);
  const [annullando, setAnnullando] = useState(null);

  const caricaRecenti = async () => {
    try {
      const res = await api.get('/api/documenti-non-associati/associati-di-recente?limit=20');
      setRecenti(res.data?.documenti || []);
    } catch (e) {
      console.warn('Errore caricamento documenti associati di recente:', e);
    }
  };

  const annullaAssociazione = async doc => {
    const ok = await confirm({
      title: 'Annullare questa associazione?',
      message: `${doc.filename || 'Documento'} — collegato a "${doc.associato_a || '—'}". Verrà rimosso il record creato per errore e il documento tornerà tra quelli da associare.`,
      confirmText: 'Annulla associazione', danger: true,
    });
    if (!ok) return;
    setAnnullando(doc.id);
    try {
      await api.post('/api/documenti-non-associati/de-associa', { documento_id: doc.id });
      setMessage({ type: 'success', text: 'Associazione annullata: il documento è tornato tra quelli da associare.' });
      await caricaRecenti();
      onRefresh?.();
    } catch (e) {
      setMessage({ type: 'error', text: 'Errore: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setAnnullando(null);
    }
  };

  // Carica collezioni disponibili
  useEffect(() => {
    const loadCollezioni = async () => {
      setLoadingCollezioni(true);
      try {
        const res = await api.get('/api/documenti-non-associati/collezioni-disponibili');
        setCollezioni(res.data || []);
      } catch (e) {
        console.warn('Errore caricamento collezioni:', e);
      }
      setLoadingCollezioni(false);
    };
    loadCollezioni();
  }, []);

  const handleViewPdf = doc => {
    // fetchUrl (non src): l'endpoint richiede il Bearer token, un <iframe
    // src> diretto non lo allega e la richiesta viene rifiutata (401) senza
    // nessun errore visibile — il PDF restava sempre vuoto (segnalato
    // dall'utente 18/07/2026). Il viewer scarica il blob via axios (stesso
    // pattern di Documenti.jsx/FattureEstereVerifica.jsx).
    setPdfViewer({
      title: `📄 ${doc.filename || doc.nome || 'Documento'}`,
      fetchUrl: `/api/documenti-non-associati/pdf/${doc.id}`,
    });
  };

  const handleAssocia = async () => {
    if (!selectedDoc || !associazioneForm.collezione) {
      setMessage({ type: 'error', text: 'Seleziona una collezione' });
      return;
    }

    try {
      let campi = {};
      if (associazioneForm.campiJson) {
        try {
          campi = JSON.parse(associazioneForm.campiJson);
        } catch {
          setMessage({ type: 'error', text: 'JSON campi non valido' });
          return;
        }
      }

      // Aggiungi campi dalla proposta
      if (selectedDoc.proposta) {
        if (selectedDoc?.proposta?.anno_suggerito) campi.anno = selectedDoc?.proposta?.anno_suggerito;
        if (selectedDoc?.proposta?.mese_suggerito) campi.mese = selectedDoc?.proposta?.mese_suggerito;
      }

      await api.post('/api/documenti-non-associati/associa', {
        documento_id: selectedDoc.id,
        collezione_target: associazioneForm.collezione,
        crea_nuovo: true,
        campi_associazione: campi,
      });

      setMessage({ type: 'success', text: 'Documento associato!' });
      setSelectedDoc(null);
      setAssociazioneForm({ collezione: '', campiJson: '' });
      if (onRefresh) onRefresh();
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || 'Errore associazione' });
    }
  };

  const handleDelete = async docId => {
    const confirmed = await confirm({
      title: 'Elimina documento',
      message: 'Eliminare questo documento?',
      confirmText: 'Elimina',
      cancelText: 'Annulla',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await api.delete(`/api/documenti-non-associati/${docId}`);
      setMessage({ type: 'success', text: 'Documento eliminato' });
      setSelectedDoc(null);
      if (onRefresh) onRefresh();
    } catch (e) {
      setMessage({ type: 'error', text: 'Errore eliminazione' });
    }
  };

  const getCategoryColor = category => {
    const colors = {
      fattura: '#3b82f6',
      f24: '#dc2626',
      busta_paga: '#16a34a',
      verbale: '#d97706',
      cartella: '#0f2744',
    };
    return colors[category] || '#64748b';
  };

  if (documenti.length === 0) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>
        <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}>📎</div>
        <div>Nessun documento da associare</div>
        <div style={{ fontSize: 12, marginTop: 8 }}>
          Tutti i documenti scaricati sono stati associati
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header con stats */}
      <div style={{ padding: 16, background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 16, color: '#0f2744' }}>
            📎 Documenti Non Associati ({documenti.length})
          </h3>
          {stats && (
            <div style={{ display: 'flex', gap: 16, fontSize: 13 }}>
              <span style={{ color: '#64748b' }}>
                Totali: <strong>{stats.totale || 0}</strong>
              </span>
              <span style={{ color: '#16a34a' }}>
                Associati: <strong>{stats.associati || 0}</strong>
              </span>
              <span style={{ color: '#dc2626' }}>
                Da fare: <strong>{stats.da_associare || 0}</strong>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Message */}
      {message && (
        <div
          style={{
            padding: 12,
            margin: 12,
            borderRadius: 8,
            background: message.type === 'success' ? '#dcfce7' : '#fee2e2',
            color: message.type === 'success' ? '#15803d' : '#dc2626',
            fontSize: 13,
          }}
        >
          {message.text}
        </div>
      )}

      {/* Layout a due colonne */}
      <div
        style={{ display: 'grid', gridTemplateColumns: selectedDoc ? '1fr 1fr' : '1fr', gap: 0 }}
      >
        {/* Lista documenti */}
        <div
          style={{
            maxHeight: 600,
            overflow: 'auto',
            borderRight: selectedDoc ? '1px solid #e5e7eb' : 'none',
          }}
        >
          {documenti.map(doc => (
            <div
              key={doc.id}
              onClick={() => setSelectedDoc(doc)}
              style={{
                padding: 14,
                borderBottom: '1px solid #f1f5f9',
                cursor: 'pointer',
                background: selectedDoc?.id === doc.id ? '#f8fafc' : 'white',
                borderLeft:
                  selectedDoc?.id === doc.id ? '3px solid #0f2744' : '3px solid transparent',
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: '#1e293b',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  marginBottom: 4,
                }}
              >
                {doc.filename}
              </div>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6 }}>
                {doc.email_subject?.substring(0, 60) || 'Nessun oggetto'}
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span
                  style={{
                    padding: '2px 8px',
                    fontSize: 11,
                    borderRadius: 4,
                    background: getCategoryColor(doc.category) + '20',
                    color: getCategoryColor(doc.category),
                  }}
                >
                  {doc.category || 'altro'}
                </span>
                {doc.proposta?.anno_suggerito && (
                  <span
                    style={{
                      padding: '2px 8px',
                      fontSize: 11,
                      borderRadius: 4,
                      background: '#dbeafe',
                      color: '#1e40af',
                    }}
                  >
                    {doc?.proposta?.anno_suggerito}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Pannello dettaglio */}
        {selectedDoc && (
          <div style={{ padding: 16, background: '#fafafa' }}>
            <div style={{ marginBottom: 16 }}>
              <button
                onClick={() => handleViewPdf(selectedDoc)}
                data-testid="documenti-tab-view-pdf"
                style={{
                  width: '100%',
                  padding: 14,
                  minHeight: 40,
                  background: '#0f2744',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: 13,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                👁️ Apri PDF
              </button>
            </div>

            {/* Info file */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 2 }}>File</div>
              <div style={{ fontSize: 14, fontWeight: 500, wordBreak: 'break-all' }}>
                {selectedDoc.filename}
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 2 }}>Categoria</div>
              <div style={{ fontSize: 14 }}>{selectedDoc.category || 'Non classificato'}</div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 2 }}>Dimensione</div>
              <div style={{ fontSize: 14 }}>
                {Math.round((selectedDoc.size_bytes || selectedDoc.pdf_size || 0) / 1024)} KB
              </div>
            </div>

            {/* Proposta AI */}
            {selectedDoc.proposta &&
              (selectedDoc?.proposta?.anno_suggerito || selectedDoc?.proposta?.tipo_suggerito) && (
                <div
                  style={{
                    background: '#eff6ff',
                    border: '1px solid #bfdbfe',
                    borderRadius: 8,
                    padding: 12,
                    marginBottom: 16,
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#1e40af', marginBottom: 8 }}>
                    💡 Proposta Intelligente
                  </div>
                  {selectedDoc?.proposta?.tipo_suggerito && (
                    <div style={{ fontSize: 12, color: '#475569', marginBottom: 4 }}>
                      Tipo: <strong>{selectedDoc?.proposta?.tipo_suggerito}</strong>
                    </div>
                  )}
                  {selectedDoc?.proposta?.anno_suggerito && (
                    <div style={{ fontSize: 12, color: '#475569', marginBottom: 4 }}>
                      Anno: <strong>{selectedDoc?.proposta?.anno_suggerito}</strong>
                    </div>
                  )}
                  {selectedDoc?.proposta?.mese_suggerito && (
                    <div style={{ fontSize: 12, color: '#475569' }}>
                      Mese: <strong>{selectedDoc?.proposta?.mese_suggerito}</strong>
                    </div>
                  )}
                </div>
              )}

            {/* Form associazione */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                Associa a collezione
              </div>
              <select
                value={associazioneForm.collezione}
                onChange={e =>
                  setAssociazioneForm({ ...associazioneForm, collezione: e.target.value })
                }
                style={{
                  width: '100%',
                  padding: 10,
                  fontSize: 14,
                  border: '1px solid #e2e8f0',
                  borderRadius: 6,
                  marginBottom: 12,
                }}
              >
                <option value="">-- Seleziona --</option>
                {collezioni.map(c => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>

              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                Campi aggiuntivi (JSON)
              </div>
              <textarea
                value={associazioneForm.campiJson}
                onChange={e =>
                  setAssociazioneForm({ ...associazioneForm, campiJson: e.target.value })
                }
                placeholder='{"anno": 2024, "importo": 150.00}'
                style={{
                  width: '100%',
                  padding: 10,
                  fontSize: 13,
                  fontFamily: 'monospace',
                  border: '1px solid #e2e8f0',
                  borderRadius: 6,
                  minHeight: 60,
                  resize: 'vertical',
                }}
              />
            </div>

            {/* Bottoni azione */}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button
                onClick={handleAssocia}
                disabled={!associazioneForm.collezione}
                style={{
                  flex: 1,
                  padding: 12,
                  minHeight: 40,
                  background: associazioneForm.collezione ? '#16a34a' : '#94a3b8',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  fontWeight: 600,
                  cursor: associazioneForm.collezione ? 'pointer' : 'not-allowed',
                  fontSize: 13,
                }}
              >
                ✓ Associa
              </button>
              <button
                onClick={() => handleDelete(selectedDoc.id)}
                style={{
                  padding: '12px 16px',
                  minHeight: 40,
                  minWidth: 40,
                  background: '#fee2e2',
                  color: '#dc2626',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                🗑️
              </button>
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: 16, padding: 16, background: '#fafafa', borderRadius: 8 }}>
        <button
          onClick={() => { setMostraRecenti(m => !m); if (!mostraRecenti && recenti.length === 0) caricaRecenti(); }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
            fontSize: 13, fontWeight: 600, color: '#0f2744', display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          {mostraRecenti ? '▼' : '▶'} Documenti associati di recente — sbagliato collezione? Annulla qui
        </button>
        {mostraRecenti && (
          <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
            {recenti.length === 0 && (
              <div style={{ fontSize: 12.5, color: '#64748b' }}>Nessun documento associato di recente.</div>
            )}
            {recenti.map(doc => (
              <div
                key={doc.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                  padding: '8px 12px', background: 'white', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 12.5,
                }}
              >
                <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.filename || 'Documento'} → <strong>{doc.associato_a || '—'}</strong>
                </span>
                <button
                  onClick={() => annullaAssociazione(doc)}
                  disabled={annullando === doc.id}
                  style={{
                    flexShrink: 0, padding: '5px 10px', background: '#fef2f2', color: '#dc2626',
                    border: '1px solid #fecaca', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    opacity: annullando === doc.id ? 0.5 : 1,
                  }}
                >
                  {annullando === doc.id ? '⏳…' : '↩️ Annulla'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {pdfViewer && (
        <DocumentViewerModal
          title={pdfViewer.title}
          src={pdfViewer.src}
          fetchUrl={pdfViewer.fetchUrl}
          documentType="documento_fiscale"
          onClose={() => setPdfViewer(null)}
        />
      )}
    </div>
  );
}
