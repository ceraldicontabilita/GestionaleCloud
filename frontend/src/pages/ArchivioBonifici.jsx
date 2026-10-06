import React, { useState, useEffect, useRef } from 'react';
import { Check, X, Trash2 } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
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
import { PageLayout } from '../components/PageLayout';
import { ListaAdattiva } from '../components/ds';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { useConfirm } from '../components/ui/ConfirmDialog';
import ModalFattura from '../components/ModalFattura';
import { VisoreOriginale } from '../components/ApriOriginale';
import { urlOriginale, euroOppure } from '../lib/vista';
import { toast } from 'sonner';

const formatDate = formatDateIT;

/**
 * Card di un bonifico: una sola lettura dall'alto in basso.
 *  1. chi e quanto (beneficiario, importo, data)
 *  2. perche (causale intera, mai troncata)
 *  3. a che punto e (UNA riga di stato con l'azione da fare)
 *  4. in piccolo: riferimenti di banca, PDF, nota, elimina
 * I controlli (scelta fattura/stipendio, nota, elimina) sono gli stessi della tabella: `r` ne e la mappa.
 */
function CardBonifico({ t, r, inHr, onPdf }) {
  const eStipendio = Boolean(t.destinazione_dipendente || inHr || t.salario_associato);
  const collegato = Boolean(t.salario_associato || t.fattura_associata || t.destinazione_automatica);
  const etichetta = { fontSize: 11, color: COLORS.textSubtle, fontWeight: 600, letterSpacing: '0.02em' };
  const riga = { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', minWidth: 0 };
  return (
    <div style={{ display: 'grid', gap: 8, ...(t.riconciliato ? { background: '#f4f8f5' } : null) }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#141413', overflowWrap: 'anywhere' }}>
            {t.beneficiario?.nome || 'Beneficiario non letto'}
          </div>
          <div style={{ fontSize: 12, color: COLORS.textSubtle, marginTop: 2 }}>
            {formatDate(t.data) || '-'}
          </div>
        </div>
        <div
          style={{
            fontWeight: 800, fontSize: 18, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums',
            color: '#141413',
          }}
        >
          {euroOppure(t.importo)}
        </div>
      </div>

      <div style={{ fontSize: 13, color: COLORS.textMuted, overflowWrap: 'anywhere' }}>
        <span style={etichetta}>CAUSALE </span>
        {t.causale || 'non indicata'}
      </div>

      <div
        style={{
          ...riga, padding: '8px 10px', borderRadius: 8,
          background: collegato ? '#eef3ef' : '#fbf3e4',
          border: `1px solid ${collegato ? '#d5e3da' : '#efdcb4'}`,
        }}
      >
        <span style={{ ...etichetta, color: collegato ? '#3d8168' : '#8a6410' }}>
          {collegato ? 'COLLEGATO A' : 'DA COLLEGARE'}
        </span>
        {eStipendio ? r.salario(t) : r.fattura(t)}
        {t.riconciliato && (
          <span
            title={t.movimento_descrizione || 'Trovato in estratto conto'}
            style={{ ...riga, gap: 4, color: '#3d8168', fontSize: 12, fontWeight: 700, marginLeft: 'auto' }}
          >
            <Check size={14} aria-hidden="true" /> In banca
          </span>
        )}
      </div>

      <div style={{ ...riga, justifyContent: 'space-between', fontSize: 11, color: COLORS.textSubtle }}>
        <span style={{ fontVariantNumeric: 'tabular-nums', overflowWrap: 'anywhere' }}>
          {t.cro_trn ? `CRO ${t.cro_trn}` : 'CRO non presente'}
          {t.rif_interno && t.rif_interno !== t.cro_trn ? ` · Rif. ${t.rif_interno}` : ''}
        </span>
        <span style={{ ...riga, gap: 10 }}>
          <button
            type="button"
            data-testid={`bonifico-pdf-${t.id}`}
            onClick={onPdf}
            aria-label={`Vedi e scarica il PDF del bonifico ${t.cro_trn || t.id}`}
            style={{
              minHeight: 36, padding: '4px 12px', border: '1px solid #c15f3c', borderRadius: 6,
              background: 'white', color: '#c15f3c', fontWeight: 700, fontSize: 12, cursor: 'pointer',
            }}
          >
            PDF
          </button>
          {r.note(t)}
          {r.elimina(t)}
        </span>
      </div>
    </div>
  );
}

export default function ArchivioBonifici() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
  const [transfers, setTransfers] = useState([]);
  const [count, setCount] = useState(0);
  const [search, setSearch] = useState('');
  const [yearFilter, setYearFilter] = useState('');
  const [ordinanteFilter, setOrdinanteFilter] = useState('');
  const [beneficiarioFilter, setBeneficiarioFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [riconciliazioneStats, setRiconciliazioneStats] = useState(null);
  const [riconciliando, setRiconciliando] = useState(false);
  const [editingNote, setEditingNote] = useState(null);
  // Il PDF del singolo bonifico: prima si scaricava solo lo ZIP dell'anno.
  const [bonificoPdf, setBonificoPdf] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [associaDropdown, setAssociaDropdown] = useState(null);
  const [operazioniCompatibili, setOperazioniCompatibili] = useState([]);
  const [loadingOperazioni, setLoadingOperazioni] = useState(false);
  const [fattureCompatibili, setFattureCompatibili] = useState([]);
  const [associaFatturaDropdown, setAssociaFatturaDropdown] = useState(null);
  const [loadingFatture, setLoadingFatture] = useState(false);
  const [fatturaView, setFatturaView] = useState(null);
  const [dipendenteIbanMatch, setDipendenteIbanMatch] = useState(null);
  const [salaryBlockReason, setSalaryBlockReason] = useState('');

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
    // Il tab è gestito interamente via hash (vedi useHashState sopra): questa
    // pagina è montata solo su /riconciliazione/archivio-bonifici, non esiste
    // una route "/archivio-bonifici/:tab" nel router — un navigate() verso
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
        setSalaryBlockReason('');
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
    loadCount();
    loadRiconciliazioneStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Ricarica quando cambiano i filtri (incluso l'anno globale: prima la
  // tabella movimenti ignorava l'anno globale quando yearFilter era vuoto —
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
      // yearFilter è un override manuale opzionale; di default segue
      // l'anno globale come tutto il resto della pagina (count).
      const annoEffettivo = yearFilter || anno;
      if (annoEffettivo) params.append('year', annoEffettivo);
      if (ordinanteFilter) params.append('ordinante', ordinanteFilter);
      if (beneficiarioFilter) params.append('beneficiario', beneficiarioFilter);

      const res = await api.get(`/api/archivio-bonifici/transfers?${params.toString()}`);
      setTransfers(res.data || []);
      setLoadError(false);
    } catch (error) {
      // Errore del servizio ≠ "tutti associati": non spacciarlo per successo.
      setLoadError(true);
      toast.error('Bonifici non caricati: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
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
              // (non annidati in "result" — quello non esiste lato backend).
              const riconciliati = statusRes.data.riconciliati || 0;
              const totale = statusRes.data.total || 0;
              toast.success('Riconciliazione completata', {
                description: `Riconciliati: ${riconciliati} • Non trovati: ${Math.max(totale - riconciliati, 0)}`,
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
          description: `Riconciliati: ${res.data.riconciliati} • Non trovati: ${res.data.non_riconciliati}`,
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
        description: `Dipendenti aggiornati: ${res.data.dipendenti_aggiornati} • Bonifici analizzati: ${res.data.totale_bonifici_analizzati}`,
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
    setSalaryBlockReason('');
    try {
      const res = await api.get(`/api/archivio-bonifici/operazioni-salari/${bonifico_id}`);
      setOperazioniCompatibili(res.data.operazioni_compatibili || []);
      setSalaryBlockReason(res.data.motivo_blocco || '');
      // Salva info dipendente trovato per IBAN
      if (res.data.dipendente_iban_match) {
        setDipendenteIbanMatch(res.data.dipendente_iban_match);
      }
    } catch (error) {
      console.error('Errore caricamento operazioni:', error);
      setOperazioniCompatibili([]);
      setSalaryBlockReason(error.response?.data?.detail || 'Periodi salario non disponibili');
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
      setSalaryBlockReason('');
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
  // «Associato» = ha un esito certo: salario, fattura, destinazione letta dall'estratto
  // (`destinazione_automatica`) o stipendio gia' trattato da HR. I doppioni non si associano a niente.
  const stipendioGiaInHr = t => ['arricchito', 'depositato'].includes(t.hr_deposito?.esito);
  const eDoppione = t => t.hr_deposito?.esito === 'duplicato';
  const eAssociato = t => Boolean(t.salario_associato || t.fattura_associata || t.destinazione_automatica || stipendioGiaInHr(t));
  const bonificiDaAssociare = transfers.filter(t => !eAssociato(t) && !eDoppione(t));
  const bonificiAssociati = transfers.filter(eAssociato);

  // Dati da mostrare in base al tab
  const transfersToShow = activeTab === 'da_associare' ? bonificiDaAssociare : bonificiAssociati;

  // Sfondo verde dei bonifici riconciliati: prima era sul <tr> della vecchia
  // tabella, con ListaAdattiva va applicato cella per cella (tdStyle)
  const sfondoRic = t => (t.riconciliato ? { background: '#f0fdf4' } : undefined);

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '16px' }} ref={dropdownRef}>
      {/* Action bar senza titolo duplicato */}
      {/* Riepilogo compatto: una riga di numeri e le tre azioni, la lista resta in vista */}
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
          flexWrap: 'wrap', marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 13, color: '#4a4740', lineHeight: 1.5 }}>
          <strong style={{ fontSize: 15, color: '#141413' }}>{transfers.length}</strong> bonifici
          {count && count !== transfers.length ? ` (su ${count} in archivio)` : ''}
          {' · '}totale <strong style={{ color: '#141413' }}>{formatEuro(totaleImporto)}</strong>
          {' · '}trovati in banca{' '}
          <strong style={{ color: riconciliazioneStats?.riconciliati > 0 ? '#3d8168' : '#b45309' }}>
            {riconciliazioneStats?.riconciliati || 0} su {riconciliazioneStats?.totale || 0}
          </strong>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={handleRiconcilia}
            disabled={riconciliando}
            style={{
              padding: '8px 14px', minHeight: 40, borderRadius: 6, border: 'none',
              background: riconciliando ? '#a19d92' : '#c15f3c', color: 'white', fontWeight: 700,
              fontSize: 13, cursor: riconciliando ? 'not-allowed' : 'pointer',
            }}
            title="Confronta i bonifici con i movimenti dell'estratto conto per verificare i pagamenti effettivi"
            data-testid="riconcilia-bonifici-btn"
          >
            {riconciliando ? 'Riconciliazione in corso...' : 'Controlla con la banca'}
          </button>
          <button
            onClick={handleSyncIbanToAnagrafica}
            style={{
              padding: '8px 14px', minHeight: 40, background: 'white', color: '#2c2b28',
              border: '1px solid #e6e3d9', borderRadius: 6, cursor: 'pointer', fontSize: 13,
            }}
            title="Sincronizza gli IBAN dei bonifici nell'anagrafica dipendenti"
          >
            Sync IBAN
          </button>
          <button
            onClick={() => {
              loadTransfers();
              loadCount();
            }}
            style={{
              padding: '8px 14px', minHeight: 40, background: 'white', color: '#2c2b28',
              border: '1px solid #e6e3d9', borderRadius: 6, cursor: 'pointer', fontSize: 13,
            }}
          >
            Aggiorna
          </button>
        </div>
      </div>

      {/* Filters */}
      <div
        style={{
          background: 'white',
          padding: 16,
          borderRadius: 8,
          border: '1px solid #e6e3d9',
          marginBottom: 24,
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <input
          type="text"
          placeholder="Cerca causale, CRO/TRN..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') loadTransfers();
          }}
          style={{
            padding: '8px 12px',
            minHeight: 40,
            borderRadius: 6,
            border: '1px solid #e6e3d9',
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
            background: '#c15f3c',
            color: 'white',
            border: 'none',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 'bold',
          }}
          data-testid="bonifici-search-btn"
        >
          Cerca
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
            border: '1px solid #e6e3d9',
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
            border: '1px solid #e6e3d9',
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
            border: '1px solid #e6e3d9',
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
              color: '#7a776e',
              border: '1px solid #e6e3d9',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            Reset
          </button>
        )}

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
            background: activeTab === 'da_associare' ? '#c15f3c' : '#f2f0e9',
            color: activeTab === 'da_associare' ? 'white' : '#5f5c55',
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
              background: activeTab === 'da_associare' ? 'rgba(255,255,255,0.2)' : '#e6e3d9',
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
            background: activeTab === 'associati' ? '#c15f3c' : '#f2f0e9',
            color: activeTab === 'associati' ? 'white' : '#5f5c55',
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
          Associati
          <span
            style={{
              background: activeTab === 'associati' ? 'rgba(255,255,255,0.2)' : '#e6e3d9',
              color: activeTab === 'associati' ? 'white' : '#5f5c55',
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
          border: '1px solid #e6e3d9',
          overflow: 'hidden',
        }}
      >
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#7a776e' }}>
            Caricamento...
          </div>
        ) : loadError ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#b0362b' }}>
            Errore nel caricamento dei bonifici. Riprova con «Aggiorna».
          </div>
        ) : transfersToShow.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#7a776e' }}>
            {activeTab === 'da_associare'
              ? 'Tutti i bonifici sono stati associati!'
              : 'Nessun bonifico associato. Seleziona il tab "Da Associare" per iniziare.'}
          </div>
        ) : (
          <div style={{ padding: isMobile ? 10 : 0 }}>
            {(() => {
              const colonne = [
                {
                  key: 'riconciliato',
                  label: 'Riconciliato',
                  align: 'center',
                  ruoloCard: 'dettaglio',
                  tdStyle: sfondoRic,
                  render: t =>
                    t.riconciliato ? (
                      <span
                        style={{ color: COLORS.success, display: 'inline-flex' }}
                        title={`Riconciliato: ${t.movimento_descrizione || 'Trovato in estratto conto'}`}
                      >
                        <Check size={16} role="img" aria-label="Riconciliato" />
                        <span style={{ marginLeft: 4, fontSize: 12 }}>Sì</span>
                      </span>
                    ) : (
                      <span style={{ color: '#d0ccbe', fontSize: 14 }}>—</span>
                    ),
                },
                {
                  key: 'data',
                  label: 'Data',
                  ruoloCard: 'sottotitolo',
                  // Su mobile solo giorno/mese: l'anno è nel selettore globale
                  render: t => (isMobile ? formatDateGGMM(t.data) : formatDate(t.data)) || '-',
                  tdStyle: t => ({ whiteSpace: 'nowrap', ...sfondoRic(t) }),
                },
                {
                  key: 'importo',
                  label: 'Importo',
                  align: 'right',
                  mono: true,
                  ruoloCard: 'importo',
                  render: t => (
                    <span style={{ fontWeight: 'bold', color: '#16a34a' }}>
                      {euroOppure(t.importo)}
                    </span>
                  ),
                  tdStyle: t => ({ whiteSpace: 'nowrap', ...sfondoRic(t) }),
                },
                {
                  key: 'beneficiario',
                  label: 'Beneficiario',
                  ruoloCard: 'titolo',
                  render: t => (
                    <>
                      {t.beneficiario?.nome || '-'}
                    </>
                  ),
                  tdStyle: sfondoRic,
                },
                {
                  key: 'causale',
                  label: 'Causale',
                  ruoloCard: 'dettaglio',
                  render: t => {
                    if (isMobile) {
                      // Causale accorciata: nella card resta su una riga
                      const c = t.causale || '-';
                      return c.length > 30 ? `${c.substring(0, 30)}…` : c;
                    }
                    return (
                      <span
                        title={t.causale}
                        style={{
                          display: 'block',
                          maxWidth: 180,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {t.causale || '-'}
                      </span>
                    );
                  },
                  tdStyle: sfondoRic,
                },
                {
                  key: 'pdf',
                  label: 'PDF',
                  ruoloCard: 'dettaglio',
                  render: t => (
                    <button
                      type="button"
                      data-testid={`bonifico-pdf-${t.id}`}
                      onClick={() => setBonificoPdf(t)}
                      aria-label={`Vedi e scarica il PDF del bonifico ${t.cro_trn || t.id}`}
                      style={{
                        minHeight: 32, padding: '4px 10px', border: '1px solid #c15f3c',
                        borderRadius: 6, background: 'white', color: '#c15f3c',
                        fontWeight: 700, fontSize: 12, cursor: 'pointer',
                      }}
                    >
                      PDF
                    </button>
                  ),
                  tdStyle: sfondoRic,
                },
                {
                  // Il CRO sta sempre accanto al bonifico (anche su smartphone):
                  // il RIF. INTERNO e' quello che l'estratto conto ripete.
                  key: 'cro_trn',
                  label: 'CRO / Rif. interno',
                  ruoloCard: 'dettaglio',
                  render: t => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {t.cro_trn || '-'}
                      {t.rif_interno && t.rif_interno !== t.cro_trn ? (
                        <><br />Rif. interno {t.rif_interno}</>
                      ) : null}
                    </span>
                  ),
                  tdStyle: t => ({ fontSize: 10, ...sfondoRic(t) }),
                },
                {
                  key: 'salario',
                  label: activeTab === 'associati' ? 'Salario Associato' : 'Associa Salario',
                  ruoloCard: 'dettaglio',
                  tdStyle: sfondoRic,
                  // position:relative sul wrapper: ancora il dropdown sia nella
                  // cella desktop sia nella card mobile
                  render: t => (
                    <div style={{ position: 'relative', display: 'inline-block' }}>
                      {t.salario_associato ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span
                            style={{
                              background: '#e2f0e7',
                              color: '#16a34a',
                              padding: '4px 8px',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 500,
                            }}
                          >
                            {t.operazione_salario_desc?.substring(0, 20) || 'Associato'}
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
                            <X size={12} aria-label="Rimuovi" />
                          </button>
                        </div>
                      ) : stipendioGiaInHr(t) ? (
                        <span style={{ fontSize: 11, color: '#3d8168', fontWeight: 600 }}>Stipendio già in HR</span>
                      ) : !t.destinazione_dipendente ? (
                        // Non e' uno stipendio: la colonna del salario non dice niente (prima ripeteva
                        // «Scegli periodo» su ogni riga). Il testo storico resta nel tooltip.
                        <span
                          data-testid={`non-stipendio-${t.id}`}
                          title="Pagamento fattura: nessun periodo. Non è uno stipendio, non serve scegliere il periodo"
                          style={{ fontSize: 11, color: '#7a776e' }}
                        >
                          —
                        </span>
                      ) : (
                        <div>
                          <button
                            onClick={() => toggleAssociaDropdown(t.id)}
                            style={{
                              padding: '4px 10px',
                              background: associaDropdown === t.id ? '#c15f3c' : '#f2f0e9',
                              color: associaDropdown === t.id ? 'white' : '#5f5c55',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              fontSize: 11,
                              fontWeight: 500,
                            }}
                            data-testid={`btn-associa-${t.id}`}
                          >
                            {associaDropdown === t.id ? 'Chiudi' : 'Associa stipendio'}
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
                                border: '1px solid #e6e3d9',
                                borderRadius: 8,
                                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                                minWidth: 300,
                                maxHeight: 250,
                                overflowY: 'auto',
                              }}
                            >
                              {/* Identita dipendente verificata prima di mostrare i periodi */}
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
                                    Dipendente riconosciuto
                                  </div>
                                  <div style={{ color: '#166534', marginTop: 2 }}>
                                    Dipendente: <strong>{dipendenteIbanMatch.nome_display}</strong>
                                  </div>
                                </div>
                              )}
                              {loadingOperazioni ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#7a776e' }}>
                                  Caricamento...
                                </div>
                              ) : operazioniCompatibili.length === 0 ? (
                                <div
                                  style={{
                                    padding: 16,
                                    textAlign: 'center',
                                    color: '#7a776e',
                                    fontSize: 11,
                                  }}
                                >
                                  {dipendenteIbanMatch
                                    ? `Nessuna operazione in Prima Nota Salari per ${dipendenteIbanMatch.nome_display}`
                                    : salaryBlockReason || 'Identifica prima il dipendente del bonifico'}
                                </div>
                              ) : (
                                operazioniCompatibili.map((op, idx) => (
                                  <div
                                    key={op.id || idx}
                                    onClick={() => handleAssocia(t.id, op.id)}
                                    style={{
                                      padding: '10px 12px',
                                      borderBottom: '1px solid #f2f0e9',
                                      cursor: 'pointer',
                                      transition: 'background 0.1s',
                                      background: '#ecfdf5',
                                    }}
                                    onMouseOver={e =>
                                      (e.currentTarget.style.background = '#e2f0e7')
                                    }
                                    onMouseOut={e =>
                                      (e.currentTarget.style.background = '#ecfdf5')
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
                                        {op.dipendente || op.descrizione || 'Operazione'}
                                      </span>
                                      <div
                                        style={{ display: 'flex', gap: 4, alignItems: 'center' }}
                                      >
                                        <span
                                          style={{
                                            background: '#e2f0e7',
                                            color: '#166534',
                                            padding: '2px 6px',
                                            borderRadius: 4,
                                            fontSize: 9,
                                            fontWeight: 600,
                                          }}
                                        >
                                          Identita verificata
                                        </span>
                                      </div>
                                    </div>
                                    <div
                                      style={{
                                        fontSize: 10,
                                        color: '#7a776e',
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
                                        {euroOppure(op.importo_display)}
                                      </span>
                                    </div>
                                  </div>
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'fattura',
                  label: activeTab === 'associati' ? 'Fattura Associata' : 'Associa Fattura',
                  ruoloCard: 'dettaglio',
                  tdStyle: sfondoRic,
                  render: t => (
                    <div style={{ position: 'relative', display: 'inline-block' }}>
                      {t.fattura_associata ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span
                            style={{
                              background: '#f7ebe4',
                              color: '#4c4a44',
                              padding: '4px 8px',
                              borderRadius: 6,
                              fontSize: 10,
                              fontWeight: 500,
                            }}
                          >
                            {t.fattura_numero?.substring(0, 15) || 'Associata'}
                            {t.fattura_esito === 'intero' && ' · saldo'}
                            {t.fattura_esito === 'acconto' && ' · acconto'}
                            {t.fattura_esito === 'eccede' && ' · supera il dovuto'}
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
                            <X size={12} aria-label="Rimuovi" />
                          </button>
                        </div>
                      ) : t.destinazione_automatica ? (
                        <span
                          data-testid={`destinazione-automatica-${t.id}`}
                          title={`Letto dall'estratto conto (rif. ${t.destinazione_automatica.rif_banca || '—'}): nessuna fattura da scegliere`}
                          style={{
                            display: 'inline-block', padding: '4px 8px', borderRadius: 6,
                            background: '#e2f0e7', color: '#3d8168', fontSize: 11, fontWeight: 600,
                          }}
                        >
                          {t.destinazione_automatica.categoria}
                        </span>
                      ) : (t.destinazione_dipendente || stipendioGiaInHr(t)) ? (
                        <span
                          title={
                            t.dipendente_nome_rilevato
                              ? `Pagamento a ${t.dipendente_nome_rilevato}: si associa solo il salario`
                              : 'Causale retributiva: si associa solo il salario'
                          }
                          style={{ fontSize: 11, color: '#7a776e' }}
                        >
                          —
                        </span>
                      ) : (
                        <div>
                          <button
                            onClick={() => toggleAssociaFatturaDropdown(t.id)}
                            style={{
                              padding: '4px 10px',
                              background: associaFatturaDropdown === t.id ? '#c15f3c' : '#f2f0e9',
                              color: associaFatturaDropdown === t.id ? 'white' : '#5f5c55',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              fontSize: 11,
                              fontWeight: 500,
                            }}
                            data-testid={`btn-associa-fattura-${t.id}`}
                          >
                            {associaFatturaDropdown === t.id ? 'Chiudi' : 'Associa fattura'}
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
                                border: '1px solid #e6e3d9',
                                borderRadius: 8,
                                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                                minWidth: 300,
                                maxHeight: 250,
                                overflowY: 'auto',
                              }}
                            >
                              {loadingFatture ? (
                                <div style={{ padding: 16, textAlign: 'center', color: '#7a776e' }}>
                                  Caricamento...
                                </div>
                              ) : fattureCompatibili.length === 0 ? (
                                <div
                                  style={{
                                    padding: 16,
                                    textAlign: 'center',
                                    color: '#7a776e',
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
                                      borderBottom: '1px solid #f2f0e9',
                                      cursor: 'pointer',
                                      transition: 'background 0.1s',
                                    }}
                                    onMouseOver={e =>
                                      (e.currentTarget.style.background = '#eef3ef')
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
                                              ? '#e2f0e7'
                                              : f.compatibilita_score >= 40
                                                ? '#f7eeda'
                                                : '#f8e5e2',
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
                                        color: '#7a776e',
                                        marginTop: 4,
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        gap: 6,
                                      }}
                                    >
                                      <span>
                                        {formatDate(f.data_fattura)} • {euroOppure(f.importo)}
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
                    </div>
                  ),
                },
                {
                  key: 'note',
                  label: 'Note',
                  ruoloCard: 'dettaglio',
                  tdStyle: sfondoRic,
                  render: t =>
                    editingNote === t.id ? (
                        <div style={{ display: 'flex', gap: 4 }}>
                          <input
                            type="text"
                            value={noteText}
                            onChange={e => setNoteText(e.target.value)}
                            style={{
                              padding: 4,
                              borderRadius: 4,
                              border: '1px solid #e6e3d9',
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
                            <Check size={12} aria-label="Salva" />
                          </button>
                          <button
                            onClick={() => {
                              setEditingNote(null);
                              setNoteText('');
                            }}
                            style={{
                              padding: '2px 6px',
                              background: '#a19d92',
                              color: 'white',
                              border: 'none',
                              borderRadius: 4,
                              cursor: 'pointer',
                              fontSize: 10,
                            }}
                          >
                            <X size={12} aria-label="Rimuovi" />
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
                            color: t.note ? '#141413' : '#a19d92',
                            fontSize: 11,
                          }}
                          title="Clicca per modificare"
                        >
                          {t.note || '+ Nota'}
                        </div>
                      ),
                },
                {
                  key: 'elimina',
                  label: 'Elimina',
                  align: 'center',
                  ruoloCard: 'azioni',
                  tdStyle: sfondoRic,
                  render: t => (
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
                      <Trash2 size={14} aria-label="Elimina" />
                    </button>
                  ),
                },
              ];
              const r = {};
              colonne.forEach(c => {
                r[c.key] = c.render;
              });
              return (
                <ListaAdattiva
                  testId="bonifici-table"
                  cardBreakpoint={100000}
                  dati={transfersToShow}
                  pageSize={50}
                  chiave={(t, idx) => t.id || idx}
                  colonne={colonne}
                  renderCard={t => (
                    <CardBonifico
                      t={t}
                      r={r}
                      inHr={stipendioGiaInHr(t)}
                      onPdf={() => setBonificoPdf(t)}
                    />
                  )}
                />
              );
            })()}
          </div>
        )}
      </div>
      {bonificoPdf && (
        <VisoreOriginale
          title={`Bonifico ${bonificoPdf.cro_trn || ''}`.trim()}
          subtitle={`${bonificoPdf.data ? formatDate(bonificoPdf.data) : ''} · ${bonificoPdf.beneficiario_nome || bonificoPdf.beneficiario || ''}`}
          url={urlOriginale({ tipo: 'bonifico', id: bonificoPdf.id })}
          documentType="pdf"
          onClose={() => setBonificoPdf(null)}
          testIdPrefix="bonifico-pdf-viewer"
        />
      )}
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
