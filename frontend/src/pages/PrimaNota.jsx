import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { useConfirm } from '../components/ui/ConfirmDialog';
import ModalFattura from '../components/ModalFattura';

/**
 * Prima Nota - Due sezioni separate: Cassa e Banca
 *
 * CASSA:
 * - DARE (Entrate): Corrispettivi (al lordo IVA), Finanziamento soci
 * - AVERE (Uscite): POS, Versamenti, Fatture pagate cassa
 *
 * BANCA:
 * - AVERE (Uscite): Fatture riconciliate (pagate bonifico/assegno)
 * - Dati da estratto conto
 */
export default function PrimaNota() {
  const isMobile = useIsMobile();
  // La pagina è responsive e funziona sia su desktop che mobile
  return <PrimaNotaDesktop />;
}

function PrimaNotaDesktop() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { anno: selectedYear } = useAnnoGlobale();
  const currentYear = new Date().getFullYear();

  // Data default: se anno globale = anno corrente usa oggi, altrimenti usa 1 gennaio dell'anno selezionato
  const getDefaultDate = year => {
    if (year === currentYear) return new Date().toISOString().split('T')[0];
    return `${year}-01-01`;
  };
  const today = getDefaultDate(selectedYear);

  // Anno selezionato viene dal context globale
  const [_availableYears, setAvailableYears] = useState([currentYear]);

  // Deep link: sezione e mese sincronizzati con URL hash
  // es: /prima-nota#sezione=banca&mese=3
  const [hs, setHs] = useHashState({ sezione: 'cassa', mese: '' });
  const activeSection = hs.sezione || 'cassa';
  const setActiveSection = v => setHs('sezione', v);
  const selectedMonth = hs.mese === '' ? null : parseInt(hs.mese, 10);
  const setSelectedMonth = v => setHs('mese', v === null ? '' : String(v));

  // Data state
  const [cassaData, setCassaData] = useState({
    movimenti: [],
    saldo: 0,
    totale_entrate: 0,
    totale_uscite: 0,
  });
  const [bancaData, setBancaData] = useState({
    movimenti: [],
    saldo: 0,
    totale_entrate: 0,
    totale_uscite: 0,
  });
  const [loading, setLoading] = useState(true);

  // Provvisori
  const [provvisori, setProvvisori] = useState([]);
  // Fatture annunciate dalle notifiche email Aruba, XML non ancora arrivato
  const [attese, setAttese] = useState([]);
  const [provLoading, setProvLoading] = useState(false);
  // Modale "Pagamento parziale" (Misto) — sostituisce il vecchio prompt()
  // del browser, che non mostrava un riepilogo e non permetteva di
  // correggere l'importo prima di confermare.
  const [parzialeModal, setParzialeModal] = useState(null); // provvisorio | null
  const [parzialeImportoCassa, setParzialeImportoCassa] = useState('');
  const [parzialeSaving, setParzialeSaving] = useState(false);
  const [resolveModal, setResolveModal] = useState(null);
  const [feedbackModal, setFeedbackModal] = useState(null);
  const [fatturaView, setFatturaView] = useState(null);

  // Quick entry forms - CASSA
  const [corrispettivo, setCorrispettivo] = useState({ data: today, importo: '' });
  const [pos, setPos] = useState({ data: today, pos1: '', pos2: '', pos3: '' });
  const [versamento, setVersamento] = useState({ data: today, importo: '' });
  const [movimento, setMovimento] = useState({
    data: today,
    tipo: 'uscita',
    importo: '',
    descrizione: '',
  });

  // Saving states
  const [savingCorrisp, setSavingCorrisp] = useState(false);
  const [savingPos, setSavingPos] = useState(false);
  const [savingVers, setSavingVers] = useState(false);
  const [savingMov, setSavingMov] = useState(false);
  const [importingCSV, setImportingCSV] = useState(false);
  const cassaCSVRef = useRef(null);
  const bancaCSVRef = useRef(null);

  // Nomi mesi
  const mesiNomi = [
    'Gen',
    'Feb',
    'Mar',
    'Apr',
    'Mag',
    'Giu',
    'Lug',
    'Ago',
    'Set',
    'Ott',
    'Nov',
    'Dic',
  ];

  // Carica anni disponibili all'avvio
  useEffect(() => {
    loadAvailableYears();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Carica dati quando cambia l'anno o il mese selezionato
  useEffect(() => {
    loadAllData();
    // Reset form dates quando cambia anno
    const defDate = getDefaultDate(selectedYear);
    setCorrispettivo(p => ({ ...p, data: defDate }));
    setPos(p => ({ ...p, data: defDate }));
    setVersamento(p => ({ ...p, data: defDate }));
    setMovimento(p => ({ ...p, data: defDate }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear, selectedMonth]);

  // Funzione per caricare gli anni disponibili
  const loadAvailableYears = async () => {
    try {
      const res = await api.get('/api/prima-nota/anni-disponibili');
      const years = res.data.anni || [currentYear];
      // Assicurati che l'anno corrente sia sempre presente
      if (!years.includes(currentYear)) {
        years.push(currentYear);
      }
      setAvailableYears(years.sort((a, b) => b - a)); // Ordina decrescente
    } catch (error) {
      console.error('Error loading available years:', error);
      setAvailableYears([currentYear]);
    }
  };

  const loadAllData = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('limit', '10000');
      params.append('anno', selectedYear.toString());

      // Se è selezionato un mese specifico, aggiungi filtro date
      if (selectedMonth !== null) {
        const monthStr = String(selectedMonth + 1).padStart(2, '0');
        const daysInMonth = new Date(selectedYear, selectedMonth + 1, 0).getDate();
        params.append('data_da', `${selectedYear}-${monthStr}-01`);
        params.append('data_a', `${selectedYear}-${monthStr}-${daysInMonth}`);
      }

      // Parametri per estratto conto
      const ecParams = new URLSearchParams();
      ecParams.append('limit', '6000');
      ecParams.append('anno', selectedYear.toString());
      if (selectedMonth !== null) {
        ecParams.append('mese', String(selectedMonth + 1));
      }

      const [cassaRes, estrattoContoRes, bancaManRes, provRes, atteseRes] = await Promise.all([
        api.get(`/api/prima-nota/cassa?${params}`),
        api.get(`/api/estratto-conto-movimenti/movimenti?${ecParams}`),
        api.get(`/api/prima-nota/banca?${params}`),
        api
          .get(`/api/prima-nota/provvisori?anno=${selectedYear}`)
          .catch(() => ({ data: { provvisori: [] } })),
        api
          .get(`/api/prima-nota/attese?anno=${selectedYear}`)
          .catch(() => ({ data: { attese: [] } })),
      ]);
      setProvvisori(provRes.data?.provvisori || []);
      setAttese(atteseRes.data?.attese || []);

      setCassaData(cassaRes.data);

      // Trasforma i dati dell'estratto conto nel formato della Prima Nota Banca
      const ecData = estrattoContoRes.data;
      const movimentiEC = (ecData.movimenti || []).map(m => ({
        ...m,
        tipo: m.tipo || (m.importo >= 0 ? 'entrata' : 'uscita'),
        importo: Math.abs(m.importo || 0),
        descrizione: m.descrizione || m.descrizione_originale || '',
        categoria: m.categoria || 'Movimento bancario',
        fattura_id: m.fattura_id || m.dettagli_riconciliazione?.fattura_id || null,
        bonifico_pdf_id: m.bonifico_pdf_id || null,
        _source: 'estratto_conto',
      }));

      // Aggiunge i movimenti manuali di prima_nota_banca (pagamenti fatture, etc.)
      // che non sono già presenti nell'estratto conto (dedup per id)
      const ecIds = new Set(movimentiEC.map(m => m.id));
      const movimentiManualiRaw = (bancaManRes.data?.movimenti || [])
        .filter(m => !ecIds.has(m.id))
        .map(m => ({ ...m, _source: 'prima_nota_banca' }));

      // Dedup INTERNO ai manuali: mantieni il record CON fattura_id quando c'è duplicato (stessa data+importo+tipo)
      const seenManualiKeys = new Map();
      for (const m of movimentiManualiRaw) {
        const key = `${m.data}|${Math.round((m.importo || 0) * 100)}|${m.tipo}`;
        const existing = seenManualiKeys.get(key);
        if (!existing || (!existing.fattura_id && m.fattura_id)) {
          seenManualiKeys.set(key, m);
        }
      }
      const movimentiManuali = Array.from(seenManualiKeys.values());

      // Dedup avanzato: rimuovi dall'estratto conto i record che corrispondono
      // a un pagamento manuale (stessa data + stesso importo + stesso tipo)
      // per evitare di mostrare la stessa transazione due volte
      const manualiKeys = new Set(seenManualiKeys.keys());
      const movimentiECDedup = movimentiEC.filter(m => {
        const key = `${m.data}|${Math.round((m.importo || 0) * 100)}|${m.tipo}`;
        return !manualiKeys.has(key);
      });

      // Unisci: prima i manuali (con fattura_id linkati), poi l'estratto conto deduppato
      const movimentiUniti = [...movimentiManuali, ...movimentiECDedup];

      const saldoPrec = ecData.saldo_precedente || 0;
      const saldoAnno = (ecData.totale_entrate || 0) - (ecData.totale_uscite || 0);
      setBancaData({
        movimenti: movimentiUniti,
        // Totali coerenti con la TABELLA: estratto conto + movimenti manuali
        // di prima nota banca (prima le card ignoravano questi ultimi)
        totale_entrate: movimentiUniti
          .filter(m => m.tipo === 'entrata')
          .reduce((sum, m) => sum + Math.abs(m.importo || 0), 0),
        totale_uscite: movimentiUniti
          .filter(m => m.tipo === 'uscita')
          .reduce((sum, m) => sum + Math.abs(m.importo || 0), 0),
        saldo_anno: saldoAnno,
        saldo_precedente: saldoPrec,
        saldo:
          saldoPrec +
          movimentiUniti.reduce(
            (sum, m) => sum + (m.tipo === 'entrata' ? 1 : -1) * Math.abs(m.importo || 0),
            0
          ),
        count: movimentiUniti.length,
      });

      // Aggiorna anni disponibili dopo caricamento
      loadAvailableYears();
    } catch (error) {
      console.error('Error loading prima nota:', error);
    } finally {
      setLoading(false);
    }
  };

  const getErrorMessage = error =>
    error?.response?.data?.detail || error?.response?.data?.message || error?.message || 'Errore imprevisto';

  const showFeedback = (title, message, tone = 'info') => {
    setFeedbackModal({ title, message, tone });
  };

  const confirmYearMismatch = async data => {
    if (!data || data.startsWith(selectedYear.toString())) return true;
    return confirm({
      title: 'Data fuori anno',
      message: `La data ${formatDateIT(data)} non appartiene all'anno ${selectedYear} selezionato in alto.\n\nVuoi procedere comunque?`,
      confirmText: 'Procedi',
      cancelText: 'Correggi data',
      variant: 'warning',
    });
  };

  const handleResolveProvvisorio = async (provvisorio, metodo) => {
    if (!provvisorio?.fattura_id) return;
    if (metodo === 'misto') {
      setParzialeImportoCassa('');
      setParzialeModal(provvisorio);
      return;
    }

    try {
      const res = await api.post('/api/prima-nota/provvisori/conferma', {
        fattura_id: provvisorio.fattura_id,
        metodo,
      });

      if (metodo === 'sospesa') {
        if (res.data?.success) {
          setProvvisori(v =>
            v.map(x => (x.fattura_id === provvisorio.fattura_id ? { ...x, suggerimento: 'sospesa' } : x))
          );
        } else {
          showFeedback(
            'Operazione non completata',
            `Il backend ha risposto senza conferma valida.\n\n${JSON.stringify(res.data)}`,
            'warning'
          );
        }
        return;
      }

      setProvvisori(v => v.filter(x => x.fattura_id !== provvisorio.fattura_id));
    } catch (error) {
      showFeedback('Errore conferma provvisorio', getErrorMessage(error), 'danger');
    }
  };

  // La sincronizzazione fatture/corrispettivi/riconciliazione gira in
  // AUTOMATICO sul server ogni 30 minuti (job "Automazioni Prima Nota"):
  // nessun pulsante manuale da ricordare.

  // Import CSV Prima Nota Cassa
  // === I movimenti di cassa si inseriscono manualmente (corrispettivi, POS, versamenti) ===
  // === L'estratto conto bancario si importa dalla sezione Estratto Conto ===

  // Import CSV estratto conto (aggiornamento incrementale - salta duplicati)
  const handleImportCSVBanca = async e => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImportingCSV(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/api/estratto-conto-movimenti/import', formData);
      const sync = res.data.sync_prima_nota || {};
      const msg = `${res.data.message}\nInseriti: ${res.data.movimenti_importati || res.data.inseriti || 0}\nDuplicati saltati: ${res.data.duplicati_saltati || 0}\nRegistrati in Prima Nota Banca: ${sync.inseriti_banca || 0}\nRegistrati in Prima Nota Cassa (prelievi/versamenti): ${sync.inseriti_cassa || 0}`;
      showFeedback('Import completato', msg);
      loadAllData();
    } catch (error) {
      showFeedback('Errore import', getErrorMessage(error), 'danger');
    } finally {
      setImportingCSV(false);
      if (bancaCSVRef.current) bancaCSVRef.current.value = '';
    }
  };

  // FORZA REIMPORT: cancella anni del CSV e reinserisce tutto (per correggere saldo)
  const bancaForceReimportRef = useRef(null);
  const [forceReimporting, setForceReimporting] = useState(false);

  const handleForceReimportBanca = async e => {
    const file = e.target.files?.[0];
    if (!file) return;

    const confirmed = await confirm({
      title: 'Forza reimport estratto conto',
      message:
        'Questa operazione cancellerà tutti i movimenti degli anni presenti nel CSV e li reinserirà completamente, incluse eventuali commissioni duplicate.\n\nVuoi continuare?',
      confirmText: 'Reimporta',
      cancelText: 'Annulla',
      variant: 'warning',
    });
    if (!confirmed) {
      if (bancaForceReimportRef.current) bancaForceReimportRef.current.value = '';
      return;
    }

    setForceReimporting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/api/estratto-conto-movimenti/force-reimport', formData);
      const d = res.data;
      showFeedback(
        'Reimport completato',
        `✅ ${d.message}\n\nAnni aggiornati: ${d.anni_aggiornati?.join(', ')}\nRecord cancellati: ${d.record_cancellati}\nMovimenti importati: ${d.movimenti_importati}\n\nEntrate: € ${d.totale_entrate?.toLocaleString('it-IT')}\nUscite: € ${d.totale_uscite?.toLocaleString('it-IT')}\nSaldo: € ${d.saldo?.toLocaleString('it-IT')}`
      );
      loadAllData();
    } catch (error) {
      showFeedback('Errore reimport', getErrorMessage(error), 'danger');
    } finally {
      setForceReimporting(false);
      if (bancaForceReimportRef.current) bancaForceReimportRef.current.value = '';
    }
  };

  // Download template CSV
  const handleDownloadTemplate = async tipo => {
    try {
      const res = await api.get(`/api/prima-nota/${tipo}/template-csv`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `template_prima_nota_${tipo}.csv`;
      a.click();
    } catch (error) {
      showFeedback('Errore download template', getErrorMessage(error), 'danger');
    }
  };

  // === SAVE HANDLERS CASSA ===

  // Corrispettivo (DARE/Entrata) - Importo al LORDO IVA
  // NOTA: Questo è un dato PROVVISORIO per vedere il saldo cassa.
  // Quando arriva l'XML dei corrispettivi, questo verrà SOVRASCRITTO.
  const handleSaveCorrispettivo = async () => {
    if (!corrispettivo.importo) {
      showFeedback('Dato mancante', "Inserisci l'importo del corrispettivo.", 'warning');
      return;
    }
    if (!(await confirmYearMismatch(corrispettivo.data))) return;
    setSavingCorrisp(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: corrispettivo.data,
        tipo: 'entrata', // DARE
        importo: parseFloat(corrispettivo.importo),
        descrizione: `Corrispettivo giornaliero ${corrispettivo.data} (provvisorio)`,
        categoria: 'Corrispettivi',
        source: 'manual_entry',
        provvisorio: true, // Sarà sovrascritto quando arriva XML
      });
      setCorrispettivo({ data: today, importo: '' });
      loadAllData();
    } catch (error) {
      showFeedback('Errore salvataggio corrispettivo', getErrorMessage(error), 'danger');
    } finally {
      setSavingCorrisp(false);
    }
  };

  // POS (AVERE/Uscita) - Escono dalla cassa - Campo unificato
  // NOTA: Questo è un dato PROVVISORIO per vedere il saldo cassa.
  // Quando arriva l'XML dei corrispettivi, questo verrà SOVRASCRITTO.
  const handleSavePos = async () => {
    const totale = parseFloat(pos.pos1) || 0;
    if (totale === 0) {
      showFeedback('Dato mancante', "Inserisci l'importo POS.", 'warning');
      return;
    }
    if (!(await confirmYearMismatch(pos.data))) return;
    setSavingPos(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: pos.data,
        tipo: 'uscita', // AVERE - escono dalla cassa
        importo: totale,
        descrizione: `POS giornaliero ${pos.data} (provvisorio)`,
        categoria: 'POS',
        source: 'manual_pos',
        provvisorio: true, // Sarà sovrascritto quando arriva XML
      });
      setPos({ data: today, pos1: '', pos2: '', pos3: '' });
      loadAllData();
    } catch (error) {
      showFeedback('Errore salvataggio POS', getErrorMessage(error), 'danger');
    } finally {
      setSavingPos(false);
    }
  };

  // Versamento (AVERE/Uscita da cassa)
  const handleSaveVersamento = async () => {
    if (!versamento.importo) {
      showFeedback('Dato mancante', "Inserisci l'importo del versamento.", 'warning');
      return;
    }
    if (!(await confirmYearMismatch(versamento.data))) return;
    setSavingVers(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: versamento.data,
        tipo: 'uscita', // AVERE
        importo: parseFloat(versamento.importo),
        descrizione: `Versamento in banca ${versamento.data}`,
        categoria: 'Versamento',
        source: 'manual_entry',
      });
      setVersamento({ data: today, importo: '' });
      loadAllData();
      showFeedback('Versamento salvato', 'Il movimento è stato registrato correttamente.');
    } catch (error) {
      showFeedback('Errore salvataggio versamento', getErrorMessage(error), 'danger');
    } finally {
      setSavingVers(false);
    }
  };

  // Movimento generico
  const handleSaveMovimento = async () => {
    if (!movimento.importo || !movimento.descrizione) {
      showFeedback('Campi mancanti', 'Compila importo e descrizione del movimento.', 'warning');
      return;
    }
    if (!(await confirmYearMismatch(movimento.data))) return;
    setSavingMov(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: movimento.data,
        tipo: movimento.tipo,
        importo: parseFloat(movimento.importo),
        descrizione: movimento.descrizione,
        categoria: movimento.tipo === 'entrata' ? 'Incasso' : 'Spese',
        source: 'manual_entry',
      });
      setMovimento({ data: today, tipo: 'uscita', importo: '', descrizione: '' });
      loadAllData();
      showFeedback('Movimento salvato', 'Il movimento è stato registrato correttamente.');
    } catch (error) {
      showFeedback('Errore salvataggio movimento', getErrorMessage(error), 'danger');
    } finally {
      setSavingMov(false);
    }
  };

  const handleDeleteMovimento = async (tipo, id) => {
    try {
      const res = await api.delete(`/api/prima-nota/${tipo}/${id}`);
      if (res.data?.require_force) {
        const avvisi = (res.data.warnings || []).join('\n');
        const confirmed = await confirm({
          title: 'Eliminazione con impatti collegati',
          message: `${avvisi}\n\nVuoi eliminare comunque questo movimento?`,
          confirmText: 'Elimina comunque',
          cancelText: 'Annulla',
          variant: 'danger',
        });
        if (confirmed) {
          await api.delete(`/api/prima-nota/${tipo}/${id}?force=true`);
        }
      }
      loadAllData();
    } catch (error) {
      showFeedback('Errore eliminazione movimento', getErrorMessage(error), 'danger');
    }
  };

  const handleEditMovimento = async (tipo, updated) => {
    // Ricarica i dati dopo la modifica
    loadAllData();
  };

  // Sposta movimento tra Cassa e Banca
  const handleSpostaMovimento = async (movimentoId, da, a) => {
    try {
      const res = await api.post('/api/prima-nota/sposta-movimento', {
        movimento_id: movimentoId,
        da: da,
        a: a,
      });
      loadAllData();
      // Feedback visivo opzionale
      if (res.data.fattura_aggiornata) {
        
      }
    } catch (error) {
      showFeedback('Errore spostamento movimento', getErrorMessage(error), 'danger');
    }
  };

  // Format helpers
  const formatDate = dateStr => formatDateIT(dateStr);

  const posTotale =
    (parseFloat(pos.pos1) || 0) + (parseFloat(pos.pos2) || 0) + (parseFloat(pos.pos3) || 0);

  // Calculate category totals for Cassa
  const totalePOS =
    cassaData.movimenti?.filter(m => m.categoria === 'POS').reduce((s, m) => s + m.importo, 0) || 0;
  const totaleVersamenti =
    cassaData.movimenti
      ?.filter(m => m.categoria === 'Versamento')
      .reduce((s, m) => s + m.importo, 0) || 0;
  const totaleFattureCassa =
    cassaData.movimenti
      ?.filter(m => ['Pagamento fornitore', 'Fatture', 'fornitori'].includes(m.categoria))
      .reduce((s, m) => s + m.importo, 0) || 0;
  const totaleCorrispettivi =
    cassaData.movimenti
      ?.filter(m => m.categoria === 'Corrispettivi')
      .reduce((s, m) => s + m.importo, 0) || 0;

  // Giorno record
  const giornoRecord = cassaData.movimenti?.reduce((best, m) => {
    if (m.tipo === 'entrata' && m.importo > (best?.importo || 0)) return m;
    return best;
  }, null);

  // eslint-disable-next-line no-unused-vars
  const inputStyle = STYLES.input;

  const inputStyleCompact = {
    padding: '6px 8px',
    borderRadius: 6,
    border: `1px solid ${COLORS.grayLight}`,
    fontSize: 12,
    width: '100%',
    boxSizing: 'border-box',
  };

  // eslint-disable-next-line no-unused-vars
  const buttonStyle = (color, disabled) =>
    button(color === COLORS.success ? 'primary' : 'secondary', disabled);

  const buttonStyleCompact = (color, disabled) => ({
    padding: '6px 12px',
    background: disabled ? '#ccc' : color,
    color: 'white',
    border: 'none',
    borderRadius: 6,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontWeight: 'bold',
    fontSize: 12,
    width: '100%',
  });

  return (
    <div style={{ ...STYLES.page, padding: 0 }}>
      {/* HEADER COMPATTO */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 16px',
          background: '#0f2744',
          borderRadius: 8,
          marginBottom: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              padding: '6px 14px',
              fontSize: 14,
              fontWeight: 'bold',
              borderRadius: 6,
              background: 'rgba(255,255,255,0.9)',
              color: COLORS.primary,
            }}
          >
            📅 Anno: {selectedYear}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => navigate('/prima-nota/pulizia')}
            style={{
              padding: '6px 12px',
              background: 'rgba(255,255,255,0.2)',
              color: 'white',
              border: '1px solid rgba(255,255,255,0.3)',
              borderRadius: 6,
              cursor: 'pointer',
              fontWeight: '600',
              fontSize: 12,
            }}
            title="Pulisci duplicati fatture e corrispettivi mancanti"
          >
            🗑️ Pulisci duplicati
          </button>

          <button
            onClick={loadAllData}
            style={{
              padding: '6px 12px',
              background: 'rgba(255,255,255,0.2)',
              color: 'white',
              border: '1px solid rgba(255,255,255,0.3)',
              borderRadius: 6,
              cursor: 'pointer',
              fontWeight: '500',
            }}
          >
            🔄
          </button>
        </div>
      </div>


      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          marginBottom: 16,
          position: 'sticky',
          top: 0,
          zIndex: 100,
          background: '#f1f5f9',
          padding: '8px 0',
        }}
      >
        <button
          data-testid="btn-prima-nota-cassa"
          onClick={() => setActiveSection('cassa')}
          style={{
            flex: 1,
            padding: isMobile ? '10px 6px' : '12px 16px',
            fontSize: isMobile ? 12 : 14,
            fontWeight: 'bold',
            background: activeSection === 'cassa' ? '#0f2744' : '#fff',
            color: activeSection === 'cassa' ? 'white' : '#64748b',
            border: `1px solid ${activeSection === 'cassa' ? '#0f2744' : '#e2e8f0'}`,
            borderRadius: 6,
            minHeight: 40,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: isMobile ? 4 : 8,
            whiteSpace: 'nowrap',
          }}
        >
          <span style={{ fontSize: isMobile ? 15 : 18 }}>💵</span>
          {isMobile ? 'CASSA' : `CASSA ${selectedYear}`}
        </button>

        <button
          data-testid="btn-prima-nota-banca"
          onClick={() => setActiveSection('banca')}
          style={{
            flex: 1,
            padding: isMobile ? '10px 6px' : '12px 16px',
            fontSize: isMobile ? 12 : 14,
            fontWeight: 'bold',
            background: activeSection === 'banca' ? '#0f2744' : '#fff',
            color: activeSection === 'banca' ? 'white' : '#64748b',
            border: `1px solid ${activeSection === 'banca' ? '#0f2744' : '#e2e8f0'}`,
            borderRadius: 6,
            minHeight: 40,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: isMobile ? 4 : 8,
            whiteSpace: 'nowrap',
          }}
        >
          <span style={{ fontSize: isMobile ? 15 : 18 }}>🏦</span>
          {isMobile ? 'BANCA' : `BANCA ${selectedYear}`}
        </button>
        <button
          data-testid="btn-prima-nota-provvisori"
          onClick={() => setActiveSection('provvisori')}
          style={{
            flex: 1,
            padding: isMobile ? '10px 6px' : '12px 16px',
            fontSize: isMobile ? 12 : 14,
            fontWeight: 'bold',
            background: activeSection === 'provvisori' ? '#0f2744' : '#fff',
            color: activeSection === 'provvisori' ? 'white' : '#64748b',
            border: `1px solid ${activeSection === 'provvisori' ? '#0f2744' : '#e2e8f0'}`,
            borderRadius: 6,
            minHeight: 40,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: isMobile ? 4 : 8,
            whiteSpace: 'nowrap',
          }}
        >
          <span style={{ fontSize: isMobile ? 15 : 18 }}>⚠️</span>
          PROVVISORI{provvisori.length > 0 ? ` (${provvisori.length})` : ''}
        </button>
        {!isMobile && <CopyLinkButton style={{ flexShrink: 0 }} />}
      </div>

      {/* ===== FATTURE ANNUNCIATE DA EMAIL (in arrivo) ===== */}
      {activeSection === 'provvisori' && attese.length > 0 && (
        <div
          style={{
            background: '#eff6ff',
            border: '1px solid #2563eb',
            borderRadius: 12,
            padding: '14px 16px',
            marginBottom: 16,
          }}
        >
          <div style={{ fontWeight: 800, color: '#1e40af', fontSize: 15, marginBottom: 4 }}>
            📩 {attese.length} Fatture annunciate (in arrivo)
          </div>
          <div style={{ fontSize: 12, color: '#1e40af', marginBottom: 10 }}>
            Avvisi da Aruba: l&apos;XML non è ancora arrivato. Se il fornitore ha metodo
            certo l&apos;anticipo è già registrato da solo; qui decidi tu i casi dubbi.
            All&apos;arrivo dell&apos;XML tutto si aggancia da solo, senza doppioni.
          </div>
          {attese.map(a => (
            <div
              key={a.id}
              style={{
                background: 'white',
                borderRadius: 10,
                padding: '12px 14px',
                marginBottom: 8,
                border: '1px solid #bfdbfe',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 8,
              }}
            >
              <div style={{ flex: 1, minWidth: 160 }}>
                <span style={{ fontWeight: 700, fontSize: 14, color: '#0f2744' }}>
                  {(a.fornitore_nome || 'Fornitore da verificare').substring(0, 32)}
                </span>
                <span style={{ fontSize: 12, color: '#94a3b8', marginLeft: 6 }}>
                  #{a.numero_fattura || '?'}
                </span>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                  📧 {formatDate((a.email_date || '').slice(0, 10))}
                  {a.stato === 'confermata_anticipo' && (
                    <span style={{ color: '#16a34a', fontWeight: 700, marginLeft: 8 }}>
                      ✓ anticipo in {a.metodo_confermato}
                      {a.conferma_fonte === 'auto_metodo_fornitore' ? ' (auto)' : ''}
                    </span>
                  )}
                  {a.stato === 'da_verificare' && (
                    <span style={{ color: '#dc2626', fontWeight: 700, marginLeft: 8 }}>
                      ⚠ dati incompleti
                    </span>
                  )}
                </div>
              </div>
              <span style={{ fontWeight: 800, fontSize: 15, color: '#0f2744' }}>
                {a.importo ? formatEuro(a.importo) : '—'}
              </span>
              {a.stato === 'in_attesa_xml' && (
                <div style={{ display: 'flex', gap: 6 }}>
                  {['cassa', 'banca'].map(m => (
                    <button
                      key={m}
                      onClick={async () => {
                        try {
                          await api.post('/api/prima-nota/attese/conferma', {
                            attesa_id: a.id,
                            metodo: m,
                          });
                          await loadAllData();
                          showFeedback(
                            'Anticipo registrato',
                            `Fattura ${a.numero_fattura || ''} registrata in ${m}: sarà agganciata all'XML in automatico.`
                          );
                        } catch (error) {
                          showFeedback('Errore', getErrorMessage(error), 'danger');
                        }
                      }}
                      style={{
                        padding: '6px 10px',
                        background:
                          a.suggerimento === m ? '#0f2744' : '#fff',
                        color: a.suggerimento === m ? 'white' : '#64748b',
                        border: `1px solid ${a.suggerimento === m ? '#0f2744' : '#e2e8f0'}`,
                        borderRadius: 6,
                        fontWeight: 700,
                        fontSize: 12,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                      title={
                        a.suggerimento === m
                          ? 'Metodo suggerito dal fornitore'
                          : `Registra in ${m}`
                      }
                    >
                      {m === 'cassa' ? '💵 Cassa' : '🏦 Banca'}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ===== TAB PROVVISORI ===== */}
      {activeSection === 'provvisori' && provvisori.length > 0 && (
        <div
          style={{
            background: '#fffbeb',
            border: '1px solid #d97706',
            borderRadius: 12,
            padding: '16px',
            marginBottom: 16,
            position: 'relative',
            zIndex: 10,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 12,
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <span style={{ fontWeight: 800, color: '#92400e', fontSize: 16 }}>
              ⚠️ {provvisori.length} Fatture da Confermare
            </span>
            <button
              onClick={async () => {
                // "sospesa" non è un metodo di registrazione: il backend la
                // lascia intenzionalmente nei provvisori (nessuna
                // destinazione certa, richiede scelta manuale cassa/banca).
                // Includerla qui dava l'impressione di un bottone rotto:
                // "Conferma Tutte" sembrava non fare nulla per la
                // maggioranza delle fatture (spesso in sospesa).
                const confermabili = provvisori.filter(
                  p => p.suggerimento === 'cassa' || p.suggerimento === 'banca'
                );
                const confermaMassiva = await confirm({
                  title: 'Conferma provvisori con metodo certo',
                  message: `Verranno confermate ${confermabili.length} fatture con metodo già suggerito.\nLe altre ${provvisori.length - confermabili.length} resteranno in sospeso finché non le risolvi manualmente.\n\nVuoi procedere?`,
                  confirmText: 'Conferma tutte',
                  cancelText: 'Annulla',
                  variant: 'warning',
                });
                if (!confermaMassiva) return;
                const sospeseCount = provvisori.length - confermabili.length;
                let ok = 0;
                let errori = 0;
                for (const p of confermabili) {
                  try {
                    await api.post('/api/prima-nota/provvisori/conferma', {
                      fattura_id: p.fattura_id,
                      metodo: p.suggerimento,
                    });
                    ok += 1;
                  } catch {
                    errori += 1;
                  }
                }
                await loadAllData();
                const msgErrori = errori > 0 ? `, ${errori} errori` : '';
                const msgSospese =
                  sospeseCount > 0
                    ? `\n${sospeseCount} restano in sospeso: nessun metodo certo, vanno risolte una per una dal pulsante "Risolvi".`
                    : '';
                showFeedback('Conferma completata', `✅ ${ok} fatture confermate${msgErrori}.${msgSospese}`);
              }}
              style={{
                padding: '8px 16px',
                background: '#16a34a',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                fontWeight: 700,
                fontSize: 14,
                cursor: 'pointer',
              }}
            >
              ✅ Conferma Tutte
            </button>
          </div>

          {provvisori.length > 30 && (
            <div style={{ fontSize: 12, color: '#92400e', marginBottom: 8 }}>
              Mostrate le prime 30 di {provvisori.length} — "Conferma Tutte" agisce comunque su
              tutte, non solo su quelle visibili.
            </div>
          )}

          {provvisori.slice(0, 30).map(p => {
            const isCassa = p.suggerimento === 'cassa';
            const isSospesa = p.suggerimento === 'sospesa';
            const badgeBg = isCassa ? '#fef3c7' : isSospesa ? '#fee2e2' : '#0f2744';
            const badgeColor = isCassa ? '#92400e' : isSospesa ? '#dc2626' : 'white';
            const badgeBorder = isCassa
              ? '2px solid #d97706'
              : isSospesa
                ? '2px solid #dc2626'
                : '2px solid #0f2744';
            const badgeText = isCassa ? '💵 CASSA' : isSospesa ? '⏳ SOSPESA' : '🏦 BANCA';
            return (
              <div
                key={p.fattura_id}
                style={{
                  background: 'white',
                  borderRadius: 10,
                  padding: '14px 16px',
                  marginBottom: 8,
                  border: '1px solid #fde68a',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 6,
                    flexWrap: 'wrap',
                    gap: 4,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 150 }}>
                    <span style={{ fontWeight: 700, fontSize: 15, color: '#0f2744' }}>
                      {(p.fornitore || '').substring(0, 30)}
                    </span>
                    <span style={{ fontSize: 12, color: '#94a3b8', marginLeft: 6 }}>
                      #{p.fattura_numero}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 800, fontSize: 18, color: '#16a34a', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                      € {(p.importo || 0).toFixed(2)}
                    </span>
                    <span
                      style={{
                        padding: '4px 12px',
                        borderRadius: 99,
                        fontSize: 13,
                        fontWeight: 800,
                        background: badgeBg,
                        color: badgeColor,
                        border: badgeBorder,
                      }}
                    >
                      {badgeText}
                    </span>
                  </div>
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: 6,
                  }}
                >
                  <div>
                    <span style={{ fontSize: 13, color: '#6b7280' }}>{formatDateIT(p.fattura_data)}</span>
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        marginLeft: 8,
                        color:
                          p.stato_match === 'confermato'
                            ? '#16a34a'
                            : p.stato_match === 'probabile'
                              ? '#d97706'
                              : '#6b7280',
                      }}
                    >
                      {p.stato_match === 'confermato'
                        ? '✅ Verificato'
                        : p.stato_match === 'probabile'
                          ? '~ Probabile'
                          : '⏳ Attesa'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {/* Vedi fattura — prima assente qui, presente solo nella
                        tabella movimenti principale: impossibile controllare
                        il documento prima di confermare cassa/banca/sospesa. */}
                    {p.fattura_id && (
                      <button
                        onClick={() =>
                          setFatturaView({
                            id: p.fattura_id,
                            numero: p.fattura_numero || p.numero_fattura || p.fornitore,
                          })
                        }
                        style={{
                          padding: '6px 10px',
                          minHeight: 32,
                          display: 'inline-flex',
                          alignItems: 'center',
                          background: '#e0f2fe',
                          color: '#0369a1',
                          border: 'none',
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: 'pointer',
                        }}
                      >
                        Vedi fattura
                      </button>
                    )}
                    <button
                      onClick={() => setResolveModal(p)}
                      style={{
                        padding: '6px 14px',
                        background: '#0f2744',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        fontWeight: 700,
                        fontSize: 12,
                        cursor: 'pointer',
                      }}
                    >
                      Risolvi
                    </button>
                  </div>
                </div>
              </div>
            );
          })}

          {provvisori.length > 30 && (
            <div style={{ textAlign: 'center', padding: 8, fontSize: 13, color: '#92400e' }}>
              ...e altre {provvisori.length - 30}
            </div>
          )}
        </div>
      )}

      {/* SECTION BUTTONS - Sticky su mobile */}      {activeSection === 'provvisori' && provvisori.length === 0 && (
        <div
          style={{
            background: 'white', border: '1px solid #e5e7eb', borderRadius: 12,
            padding: 40, textAlign: 'center', color: '#6b7280', marginBottom: 16,
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 8 }}>✅</div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Nessuna fattura provvisoria</div>
          <div style={{ fontSize: 13 }}>
            Le fatture con metodo fornitore impostato vengono registrate in automatico
            (job ogni 30 minuti). Qui restano solo sospese, misto e fornitori senza metodo.
          </div>
        </div>
      )}

      {/* ========== SEZIONE CASSA ========== */}
      {activeSection === 'cassa' && (
        <section>
          {/* Summary Cards Cassa - Compatti */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
              gap: 10,
              marginBottom: 16,
            }}
          >
            <MiniCard
              title={`Entrate (DARE) ${selectedYear}`}
              value={formatEuro(cassaData.totale_entrate)}
              color="#16a34a"
            />
            <MiniCard
              title={`Uscite (AVERE) ${selectedYear}`}
              value={formatEuro(cassaData.totale_uscite)}
              color="#dc2626"
            />
            <MiniCard
              title={`Saldo Cassa ${selectedYear}`}
              value={formatEuro(
                cassaData.saldo_anno || cassaData.totale_entrate - cassaData.totale_uscite
              )}
              color={
                (cassaData.saldo_anno || cassaData.totale_entrate - cassaData.totale_uscite) >= 0
                  ? '#16a34a'
                  : '#dc2626'
              }
              highlight
            />
          </div>

          {/* Logica Corrispettivi - Toolbar Ricostruzione */}

          {/* Dettaglio - Compatto */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
              gap: 8,
              marginBottom: 16,
            }}
          >
            <TinyStatCard
              title="Corrispettivi"
              value={formatEuro(totaleCorrispettivi)}
              color="#d97706"
            />
            <TinyStatCard title="POS" value={formatEuro(totalePOS)} color="#0f2744" />
            <TinyStatCard title="Versamenti" value={formatEuro(totaleVersamenti)} color="#16a34a" />
            <TinyStatCard title="Fatture" value={formatEuro(totaleFattureCassa)} color="#dc2626" />
          </div>

          {/* Chiusure Giornaliere - Menu Compatto a Tendina */}
          <div
            style={{
              background: '#f8fafc',
              borderRadius: 10,
              padding: 12,
              marginBottom: 16,
              border: '1px solid #e2e8f0',
            }}
          >
            <details style={{ cursor: 'pointer' }}>
              <summary
                style={{
                  fontSize: 14,
                  fontWeight: 'bold',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 0',
                  userSelect: 'none',
                }}
              >
                <span>📝</span> Chiusure Giornaliere
                <span
                  style={{
                    marginLeft: 'auto',
                    fontSize: 11,
                    background: '#dbeafe',
                    color: '#0f2744',
                    padding: '2px 8px',
                    borderRadius: 4,
                  }}
                >
                  Clicca per espandere
                </span>
              </summary>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
                  gap: 10,
                  marginTop: 12,
                }}
              >
                {/* Corrispettivo - Ultra compatto */}
                <div
                  style={{
                    background: 'white',
                    borderRadius: 8,
                    padding: 10,
                    borderLeft: '3px solid #d97706',
                  }}
                >
                  <div
                    style={{ fontSize: 11, fontWeight: 'bold', color: '#92400e', marginBottom: 6 }}
                  >
                    🧾 Corrispettivo
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <input
                      type="date"
                      value={corrispettivo.data}
                      onChange={e => setCorrispettivo({ ...corrispettivo, data: e.target.value })}
                      style={{ ...inputStyleCompact, flex: 1, padding: '4px 6px', fontSize: 11 }}
                    />
                    <input
                      type="number"
                      step="0.01"
                      placeholder="€"
                      value={corrispettivo.importo}
                      onChange={e =>
                        setCorrispettivo({ ...corrispettivo, importo: e.target.value })
                      }
                      style={{ ...inputStyleCompact, width: 70, padding: '4px 6px', fontSize: 11 }}
                    />
                    <button
                      onClick={handleSaveCorrispettivo}
                      disabled={savingCorrisp}
                      style={{
                        ...buttonStyleCompact('#0f2744', savingCorrisp),
                        padding: '4px 8px',
                        minWidth: 32,
                      }}
                    >
                      {savingCorrisp ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>

                {/* POS - Ultra compatto */}
                <div
                  style={{
                    background: 'white',
                    borderRadius: 8,
                    padding: 10,
                    borderLeft: '3px solid #0f2744',
                  }}
                >
                  <div
                    style={{ fontSize: 11, fontWeight: 'bold', color: '#0f2744', marginBottom: 6 }}
                  >
                    💳 POS
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <input
                      type="date"
                      value={pos.data}
                      onChange={e => setPos({ ...pos, data: e.target.value })}
                      style={{ ...inputStyleCompact, flex: 1, padding: '4px 6px', fontSize: 11 }}
                    />
                    <input
                      type="number"
                      step="0.01"
                      placeholder="€"
                      value={pos.pos1}
                      onChange={e => setPos({ ...pos, pos1: e.target.value, pos2: '', pos3: '' })}
                      style={{ ...inputStyleCompact, width: 70, padding: '4px 6px', fontSize: 11 }}
                    />
                    <button
                      onClick={handleSavePos}
                      disabled={savingPos}
                      style={{
                        ...buttonStyleCompact('#0f2744', savingPos),
                        padding: '4px 8px',
                        minWidth: 32,
                      }}
                    >
                      {savingPos ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>

                {/* Versamento - Ultra compatto */}
                <div
                  style={{
                    background: 'white',
                    borderRadius: 8,
                    padding: 10,
                    borderLeft: '3px solid #16a34a',
                  }}
                >
                  <div
                    style={{ fontSize: 11, fontWeight: 'bold', color: '#16a34a', marginBottom: 6 }}
                  >
                    💰 Versamento
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <input
                      type="date"
                      value={versamento.data}
                      onChange={e => setVersamento({ ...versamento, data: e.target.value })}
                      style={{ ...inputStyleCompact, flex: 1, padding: '4px 6px', fontSize: 11 }}
                    />
                    <input
                      type="number"
                      step="0.01"
                      placeholder="€"
                      value={versamento.importo}
                      onChange={e => setVersamento({ ...versamento, importo: e.target.value })}
                      style={{ ...inputStyleCompact, width: 70, padding: '4px 6px', fontSize: 11 }}
                    />
                    <button
                      onClick={handleSaveVersamento}
                      disabled={savingVers}
                      style={{
                        ...buttonStyleCompact('#0f2744', savingVers),
                        padding: '4px 8px',
                        minWidth: 32,
                      }}
                    >
                      {savingVers ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>

                {/* Movimento Altro - Ultra compatto */}
                <div
                  style={{
                    background: 'white',
                    borderRadius: 8,
                    padding: 10,
                    borderLeft: '3px solid #d97706',
                  }}
                >
                  <div
                    style={{ fontSize: 11, fontWeight: 'bold', color: '#d97706', marginBottom: 6 }}
                  >
                    📝 Altro
                  </div>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    <input
                      type="date"
                      value={movimento.data}
                      onChange={e => setMovimento({ ...movimento, data: e.target.value })}
                      style={{ ...inputStyleCompact, width: 100, padding: '4px 6px', fontSize: 11 }}
                    />
                    <select
                      value={movimento.tipo}
                      onChange={e => setMovimento({ ...movimento, tipo: e.target.value })}
                      style={{ ...inputStyleCompact, width: 60, padding: '4px 4px', fontSize: 10 }}
                    >
                      <option value="uscita">-</option>
                      <option value="entrata">+</option>
                    </select>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="€"
                      value={movimento.importo}
                      onChange={e => setMovimento({ ...movimento, importo: e.target.value })}
                      style={{ ...inputStyleCompact, width: 60, padding: '4px 6px', fontSize: 11 }}
                    />
                    <input
                      type="text"
                      placeholder="Desc."
                      value={movimento.descrizione}
                      onChange={e => setMovimento({ ...movimento, descrizione: e.target.value })}
                      style={{
                        ...inputStyleCompact,
                        flex: 1,
                        padding: '4px 6px',
                        fontSize: 11,
                        minWidth: 80,
                      }}
                    />
                    <button
                      onClick={handleSaveMovimento}
                      disabled={savingMov}
                      style={{
                        ...buttonStyleCompact('#0f2744', savingMov),
                        padding: '4px 8px',
                        minWidth: 32,
                      }}
                    >
                      {savingMov ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>
              </div>
            </details>
          </div>

          {/* Filter - Bottoni Mesi */}
          <div
            style={{
              display: 'flex',
              gap: 6,
              alignItems: 'center',
              marginBottom: 12,
              flexWrap: 'wrap',
            }}
          >
            <span style={{ fontSize: 12, color: '#6b7280', marginRight: 4 }}>📅 Mese:</span>
            <button
              onClick={() => setSelectedMonth(null)}
              style={{
                padding: '6px 12px',
                minHeight: 40,
                background: selectedMonth === null ? '#0f2744' : '#f3f4f6',
                color: selectedMonth === null ? 'white' : '#374151',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: selectedMonth === null ? 'bold' : 'normal',
              }}
            >
              Tutti
            </button>
            {mesiNomi.map((nome, i) => (
              <button
                key={i}
                onClick={() => setSelectedMonth(i)}
                style={{
                  padding: '6px 10px',
                  minHeight: 40,
                  background: selectedMonth === i ? '#0f2744' : '#f3f4f6',
                  color: selectedMonth === i ? 'white' : '#374151',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: selectedMonth === i ? 'bold' : 'normal',
                }}
              >
                {nome}
              </button>
            ))}
            {giornoRecord && (
              <span
                style={{
                  marginLeft: 'auto',
                  fontSize: 11,
                  color: '#92400e',
                  background: '#fef3c7',
                  padding: '4px 8px',
                  borderRadius: 4,
                }}
              >
                🏆  Record: {formatDate(giornoRecord.data)} - {formatEuro(giornoRecord.importo)}
              </span>
            )}
          </div>

          {/* Movements Table Cassa */}
          <MovementsTable
            movimenti={cassaData.movimenti || []}
            tipo="cassa"
            loading={loading}
            formatEuro={formatEuro}
            formatDate={formatDate}
            onDelete={id => handleDeleteMovimento('cassa', id)}
            onEdit={updated => handleEditMovimento('cassa', updated)}
            onSposta={handleSpostaMovimento}
            saldoPrecedente={0}
          />
        </section>
      )}

      {/* ========== SEZIONE BANCA ========== */}
      {activeSection === 'banca' && (
        <section>
          {/* Summary Cards Banca */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 16,
              marginBottom: 20,
            }}
          >
            <SummaryCard
              title={`Accrediti ${selectedYear}`}
              value={formatEuro(bancaData.totale_entrate)}
              color="#16a34a"
              icon="📈"
              subtitle="Totale accrediti bancari (POS + bonifici + altro)"
            />
            <SummaryCard
              title={`Pagamenti ${selectedYear}`}
              value={formatEuro(bancaData.totale_uscite)}
              color="#dc2626"
              icon="📉"
              subtitle="Totale addebiti (fornitori, tasse, stipendi)"
            />
            <SummaryCard
              title={`Saldo Banca ${selectedYear}`}
              value={formatEuro(
                bancaData.saldo_anno || bancaData.totale_entrate - bancaData.totale_uscite
              )}
              color={
                (bancaData.saldo_anno || bancaData.totale_entrate - bancaData.totale_uscite) >= 0
                  ? '#16a34a'
                  : '#dc2626'
              }
              icon="🏦"
              subtitle={`Accrediti - Pagamenti ${selectedYear}`}
            />
            {bancaData.saldo_precedente !== undefined && bancaData.saldo_precedente !== 0 && (
              <SummaryCard
                title="Saldo Cumulativo"
                value={formatEuro(bancaData.saldo)}
                color="#0f2744"
                icon="💰"
                subtitle="Saldo totale complessivo"
                highlight
              />
            )}
            {bancaData.saldo_precedente !== undefined && bancaData.saldo_precedente !== 0 && (
              <SummaryCard
                title="Riporto Anni Prec."
                value={formatEuro(bancaData.saldo_precedente)}
                color="#6b7280"
                icon="↩️"
                subtitle="Saldo al 31/12 anno prec."
              />
            )}
          </div>

          {/* Nota banca */}
          <div
            style={{
              background: '#fefce8',
              border: '1px solid #d97706',
              borderRadius: 10,
              padding: '10px 16px',
              marginBottom: 14,
              fontSize: 13,
              color: '#854d0e',
            }}
          >
            📝 <strong>Nota contabile:</strong> Gli "Accrediti" mostrano tutti i movimenti in
            entrata sul conto bancario (POS, bonifici, depositi, finanziamenti).{' '}
            <strong>I ricavi reali dell'azienda sono nei Corrispettivi</strong>, visibili nella
            sezione Cassa. Alcuni accrediti (es. bonifici interni, finanziamenti) non sono ricavi.
          </div>

          {/* Filter - Bottoni Mesi */}
          <div
            style={{
              display: 'flex',
              gap: 6,
              alignItems: 'center',
              marginBottom: 16,
              flexWrap: 'wrap',
            }}
          >
            <span style={{ fontSize: 14, color: '#6b7280', marginRight: 8 }}>📅 Mese:</span>
            <button
              onClick={() => setSelectedMonth(null)}
              style={{
                padding: '8px 14px',
                minHeight: 40,
                background: selectedMonth === null ? '#0f2744' : '#f3f4f6',
                color: selectedMonth === null ? 'white' : '#374151',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: selectedMonth === null ? 'bold' : 'normal',
              }}
            >
              Tutti
            </button>
            {mesiNomi.map((nome, i) => (
              <button
                key={i}
                onClick={() => setSelectedMonth(i)}
                style={{
                  padding: '8px 12px',
                  minHeight: 40,
                  background: selectedMonth === i ? '#0f2744' : '#f3f4f6',
                  color: selectedMonth === i ? 'white' : '#374151',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontWeight: selectedMonth === i ? 'bold' : 'normal',
                }}
              >
                {nome}
              </button>
            ))}
          </div>

          {/* Movements Table Banca - Estratto Conto con possibilità di spostare */}
          <MovementsTable
            movimenti={bancaData.movimenti || []}
            tipo="banca"
            loading={loading}
            formatEuro={formatEuro}
            formatDate={formatDate}
            onDelete={id => handleDeleteMovimento('banca', id)}
            onEdit={updated => handleEditMovimento('banca', updated)}
            onSposta={handleSpostaMovimento}
            readOnly={false}
            saldoPrecedente={bancaData.saldo_precedente || 0}
          />
        </section>
      )}

      {/* Modale "Pagamento parziale" (Misto) — sostituisce il vecchio
          prompt() del browser: mostra fornitore, totale, importo cassa da
          scegliere e residuo banca calcolato, con riepilogo prima di
          confermare invece di un singolo campo testo senza contesto. */}
      {parzialeModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 2000,
          }}
          onClick={() => !parzialeSaving && setParzialeModal(null)}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 24,
              width: '92%',
              maxWidth: 420,
              boxShadow: '0 20px 40px rgba(15,39,68,0.25)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 4px', fontSize: 17, color: '#0f2744' }}>
              Pagamento parziale (Misto)
            </h3>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
              {(parzialeModal.fornitore || '').substring(0, 40)} — Fatt. #
              {parzialeModal.fattura_numero}
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '10px 12px',
                background: '#f8fafc',
                borderRadius: 8,
                marginBottom: 16,
                fontSize: 14,
              }}
            >
              <span>Totale fattura</span>
              <strong>€ {(parzialeModal.importo || 0).toFixed(2)}</strong>
            </div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
              Importo pagato in CASSA
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              max={parzialeModal.importo || 0}
              autoFocus
              value={parzialeImportoCassa}
              onChange={e => setParzialeImportoCassa(e.target.value)}
              placeholder="0.00"
              style={{
                width: '100%',
                padding: '10px 12px',
                border: '1px solid #d1d5db',
                borderRadius: 8,
                fontSize: 15,
                boxSizing: 'border-box',
              }}
            />
            {(() => {
              const ci = parseFloat(parzialeImportoCassa);
              const valido = !isNaN(ci) && ci > 0 && ci <= (parzialeModal.importo || 0);
              const residuoBanca = valido
                ? Math.round(((parzialeModal.importo || 0) - ci) * 100) / 100
                : null;
              return (
                <>
                  {valido && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        padding: '10px 12px',
                        background: '#eff6ff',
                        borderRadius: 8,
                        marginTop: 10,
                        fontSize: 14,
                      }}
                    >
                      <span>Residuo in BANCA</span>
                      <strong>€ {residuoBanca.toFixed(2)}</strong>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                    <button
                      onClick={() => setParzialeModal(null)}
                      disabled={parzialeSaving}
                      style={{
                        flex: 1,
                        padding: '10px 16px',
                        background: '#f1f5f9',
                        color: '#374151',
                        border: 'none',
                        borderRadius: 8,
                        fontSize: 14,
                        fontWeight: 600,
                        cursor: parzialeSaving ? 'wait' : 'pointer',
                      }}
                    >
                      Annulla
                    </button>
                    <button
                      onClick={async () => {
                        setParzialeSaving(true);
                        try {
                          await api.post('/api/pagamenti/registra', {
                            fattura_id: parzialeModal.fattura_id,
                            importo: ci,
                            metodo: 'contanti',
                            data: parzialeModal.fattura_data,
                            note: `€${ci} di €${parzialeModal.importo}`,
                          });
                          if (residuoBanca > 0) {
                            await api.post('/api/pagamenti/registra', {
                              fattura_id: parzialeModal.fattura_id,
                              importo: residuoBanca,
                              metodo: 'bonifico',
                              data: parzialeModal.fattura_data,
                              note: `Residuo banca €${residuoBanca}`,
                            });
                          }
                          setProvvisori(v =>
                            v.filter(x => x.fattura_id !== parzialeModal.fattura_id)
                          );
                          setParzialeModal(null);
                        } catch (e) {
                          showFeedback(
                            'Errore pagamento parziale',
                            e.response?.data?.detail || e.response?.data?.message || e.message,
                            'danger'
                          );
                        } finally {
                          setParzialeSaving(false);
                        }
                      }}
                      disabled={!valido || parzialeSaving}
                      style={{
                        flex: 1,
                        padding: '10px 16px',
                        background: valido ? '#0f2744' : '#94a3b8',
                        color: 'white',
                        border: 'none',
                        borderRadius: 8,
                        fontSize: 14,
                        fontWeight: 700,
                        cursor: valido && !parzialeSaving ? 'pointer' : 'not-allowed',
                      }}
                    >
                      {parzialeSaving ? 'Salvataggio...' : 'Conferma'}
                    </button>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      )}
      {resolveModal && (
        <ResolveProvvisorioModal
          provvisorio={resolveModal}
          onClose={() => setResolveModal(null)}
          onResolve={async metodo => {
            const current = resolveModal;
            setResolveModal(null);
            await handleResolveProvvisorio(current, metodo);
          }}
        />
      )}
      {feedbackModal && (
        <FeedbackModal
          title={feedbackModal.title}
          message={feedbackModal.message}
          tone={feedbackModal.tone}
          onClose={() => setFeedbackModal(null)}
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

// Sub-components

function FeedbackModal({ title, message, tone = 'info', onClose }) {
  const tones = {
    info: { accent: '#0f2744', bg: '#eff6ff' },
    warning: { accent: '#b45309', bg: '#fff7ed' },
    danger: { accent: '#b91c1c', bg: '#fef2f2' },
  };
  const palette = tones[tone] || tones.info;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 2100,
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 460,
          background: 'white',
          borderRadius: 10,
          boxShadow: '0 24px 48px rgba(15,39,68,0.24)',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '14px 16px', background: palette.bg, borderBottom: `1px solid ${palette.accent}22` }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: palette.accent }}>{title}</div>
        </div>
        <div style={{ padding: 16, fontSize: 14, color: '#334155', whiteSpace: 'pre-line', lineHeight: 1.5 }}>
          {message}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: 16, borderTop: '1px solid #e2e8f0' }}>
          <button onClick={onClose} style={{ ...button('primary'), minWidth: 110 }}>
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
}

function ResolveProvvisorioModal({ provvisorio, onClose, onResolve }) {
  const suggerimento = provvisorio?.suggerimento || 'sospesa';
  const opzioni = [
    { key: 'cassa', label: 'Registra in Cassa', hint: 'Pagamento immediato in contanti.' },
    { key: 'banca', label: 'Registra in Banca', hint: 'Pagamento tracciato da bonifico o addebito.' },
    { key: 'sospesa', label: 'Lascia Sospesa', hint: 'La fattura resta nei provvisori in attesa di decisione.' },
    { key: 'misto', label: 'Pagamento Parziale', hint: 'Divide il pagamento tra cassa e banca.' },
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 2050,
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 520,
          background: 'white',
          borderRadius: 10,
          boxShadow: '0 24px 48px rgba(15,39,68,0.24)',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: 16, borderBottom: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: 17, fontWeight: 700, color: '#0f2744' }}>Risolvi provvisorio</div>
          <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
            {(provvisorio?.fornitore || '').substring(0, 50)} — Fatt. #{provvisorio?.fattura_numero} — €{' '}
            {(provvisorio?.importo || 0).toFixed(2)}
          </div>
        </div>
        <div style={{ padding: 16, display: 'grid', gap: 10 }}>
          {opzioni.map(opzione => {
            const isSuggested = suggerimento === opzione.key;
            return (
              <button
                key={opzione.key}
                onClick={() => onResolve(opzione.key)}
                style={{
                  textAlign: 'left',
                  padding: 14,
                  borderRadius: 8,
                  border: isSuggested ? '2px solid #b8860b' : '1px solid #dbe2ea',
                  background: isSuggested ? '#fffbeb' : 'white',
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: '#0f2744' }}>{opzione.label}</span>
                  {isSuggested && (
                    <span style={{ fontSize: 11, fontWeight: 700, color: '#92400e' }}>Suggerito</span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{opzione.hint}</div>
              </button>
            );
          })}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: 16, borderTop: '1px solid #e2e8f0' }}>
          <button onClick={onClose} style={{ ...button('secondary'), minWidth: 110 }}>
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
}

function MiniCard({ title, value, color, highlight: _highlight }) {
  return (
    <div
      style={{
        background: 'white',
        borderRadius: 8,
        padding: 10,
        border: '1px solid #e2e8f0',
        borderLeft: '4px solid #0f2744',
      }}
    >
      <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>{title}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{value}</div>
    </div>
  );
}

function TinyStatCard({ title, value, color }) {
  return (
    <div
      style={{
        background: 'white',
        borderRadius: 6,
        padding: 8,
        border: '1px solid #e2e8f0',
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5 }}>{title}</div>
      <div style={{ fontSize: 13, fontWeight: 700, color, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{value}</div>
    </div>
  );
}

function CompactEntryCard({ title, color, children }) {
  return (
    <div
      style={{
        background: `${color}10`,
        borderRadius: 8,
        padding: 10,
        border: `1px solid ${color}30`,
      }}
    >
      <h4 style={{ margin: '0 0 8px 0', fontSize: 12, fontWeight: 'bold', color }}>{title}</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>{children}</div>
    </div>
  );
}

function SummaryCard({ title, value, color, icon, highlight: _highlight, subtitle }) {
  return (
    <div
      style={{
        background: 'white',
        borderRadius: 8,
        padding: 16,
        border: '1px solid #e2e8f0',
        borderLeft: '4px solid #0f2744',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
        }}
      >
        <span style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5 }}>{title}</span>
        <span style={{ fontSize: 18 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{value}</div>
      {subtitle && <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>{subtitle}</div>}
    </div>
  );
}

// eslint-disable-next-line no-unused-vars
function MiniStatCard({ title, value, color }) {
  return (
    <div
      style={{
        background: 'white',
        borderRadius: 8,
        padding: 12,
        border: '1px solid #e5e7eb',
        borderLeft: `4px solid ${color}`,
      }}
    >
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 16, fontWeight: 'bold', color }}>{value}</div>
    </div>
  );
}

// eslint-disable-next-line no-unused-vars
function QuickEntryCard({ title, color, children }) {
  return (
    <div
      style={{
        background: `${color}`,
        borderRadius: 12,
        padding: 16,
        border: `2px solid ${color}30`,
      }}
    >
      <h4 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 'bold' }}>{title}</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{children}</div>
    </div>
  );
}


// Estrae il numero fattura dal movimento: campo dedicato se presente,
// altrimenti dal prefisso della descrizione ("Fatt. 123 - Fornitore").
function splitNumeroFattura(mov) {
  const desc = mov.descrizione || mov.descrizione_originale || '';
  const m = desc.match(
    /^(?:Fatt\.|Pagamento fattura|Incasso fattura|Nota credito(?: fornitore)?)\s+(\S+)\s*-\s*(.+)$/i
  );
  if (mov.numero_fattura) return { numero: mov.numero_fattura, descr: m ? m[2] : desc };
  if (m) return { numero: m[1], descr: m[2] };
  return { numero: '', descr: desc };
}

function MovementsTable({
  movimenti,
  tipo,
  loading,
  formatEuro,
  formatDate,
  onDelete,
  onEdit,
  onSposta,
  readOnly = false,
  saldoPrecedente = 0,
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [editingMovimento, setEditingMovimento] = useState(null);
  const [spostando, setSpostando] = useState(null);
  const itemsPerPage = 50;

  // FILTRI AVANZATI
  const [filtroDescrizione, setFiltroDescrizione] = useState('');
  const [filtroCategoria, setFiltroCategoria] = useState('');
  const [filtroTipo, setFiltroTipo] = useState('');
  const [filtroDareAvere, setFiltroDareAvere] = useState(''); // dare = entrata, avere = uscita
  const [filtroDataDa, setFiltroDataDa] = useState(''); // YYYY-MM-DD
  const [filtroDataA, setFiltroDataA] = useState('');
  const [filtroImportoMin, setFiltroImportoMin] = useState('');
  const [filtroImportoMax, setFiltroImportoMax] = useState('');
  const [filtroNumeroFattura, setFiltroNumeroFattura] = useState('');
  const [filtroDataText, setFiltroDataText] = useState('');

  // Lista categorie uniche
  const categorieUniche = [...new Set(movimenti.map(m => m.categoria).filter(Boolean))].sort();

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>⏳ Caricamento...</div>
    );
  }

  // Applica filtri
  let movimentiFiltrati = movimenti;

  if (filtroDescrizione) {
    movimentiFiltrati = movimentiFiltrati.filter(m =>
      (m.descrizione || '').toLowerCase().includes(filtroDescrizione.toLowerCase())
    );
  }

  if (filtroCategoria) {
    movimentiFiltrati = movimentiFiltrati.filter(m => m.categoria === filtroCategoria);
  }

  if (filtroNumeroFattura) {
    const q = filtroNumeroFattura.toLowerCase();
    movimentiFiltrati = movimentiFiltrati.filter(m =>
      splitNumeroFattura(m).numero.toLowerCase().includes(q)
    );
  }

  if (filtroDataText) {
    const q = filtroDataText.trim();
    movimentiFiltrati = movimentiFiltrati.filter(m => {
      const iso = m.data || '';
      const it = iso.length >= 10 ? `${iso.slice(8, 10)}-${iso.slice(5, 7)}-${iso.slice(0, 4)}` : '';
      return iso.includes(q) || it.includes(q);
    });
  }

  if (filtroTipo) {
    movimentiFiltrati = movimentiFiltrati.filter(m => m.tipo === filtroTipo);
  }

  if (filtroDareAvere === 'dare') {
    movimentiFiltrati = movimentiFiltrati.filter(m => m.tipo === 'entrata');
  } else if (filtroDareAvere === 'avere') {
    movimentiFiltrati = movimentiFiltrati.filter(m => m.tipo === 'uscita');
  }

  // Filtro data da
  if (filtroDataDa) {
    movimentiFiltrati = movimentiFiltrati.filter(m => (m.data || '') >= filtroDataDa);
  }
  // Filtro data a
  if (filtroDataA) {
    movimentiFiltrati = movimentiFiltrati.filter(m => (m.data || '') <= filtroDataA);
  }
  // Filtro importo min
  if (filtroImportoMin !== '') {
    const min = parseFloat(filtroImportoMin);
    if (!isNaN(min))
      movimentiFiltrati = movimentiFiltrati.filter(m => Math.abs(m.importo || 0) >= min);
  }
  // Filtro importo max
  if (filtroImportoMax !== '') {
    const max = parseFloat(filtroImportoMax);
    if (!isNaN(max))
      movimentiFiltrati = movimentiFiltrati.filter(m => Math.abs(m.importo || 0) <= max);
  }

  const totalPages = Math.ceil(movimentiFiltrati.length / itemsPerPage);
  const start = (currentPage - 1) * itemsPerPage;
  const _currentMovimenti = movimentiFiltrati.slice(start, start + itemsPerPage);

  // Calculate running balance using reduce - ordina FORWARD (cronologico ASC) per calcolo corretto
  const saldoIniziale = saldoPrecedente || 0;
  // Il saldo progressivo va calcolato SEMPRE su tutti i movimenti del
  // periodo (mai su "movimentiFiltrati"): filtrando per es. "F24" o una
  // fattura, il saldo progressivo diventava il saldo della sola selezione
  // filtrata, non il saldo reale del conto — fuorviante e potenzialmente
  // letto come "quanto ho davvero in cassa/banca". Si calcola una volta
  // sola sull'elenco completo e si applica ai movimenti filtrati per id.
  // Ordine: cronologico per data movimento; a parità di data, per ordine di
  // inserimento (created_at) — così l'uscita POS segue sempre l'entrata
  // corrispettivo dello stesso giorno e il saldo intermedio è coerente.
  const movimentiForward = [...movimenti].sort(
    (a, b) =>
      (a.data || '').localeCompare(b.data || '') ||
      (a.created_at || '').localeCompare(b.created_at || '')
  );
  const balanceMap = {};
  movimentiForward.reduce((prevBal, m) => {
    const newBal = m.tipo === 'entrata' ? prevBal + (m.importo || 0) : prevBal - (m.importo || 0);
    balanceMap[m.id || m.data + m.importo] = newBal;
    return newBal;
  }, saldoIniziale);
  // Applica il saldo progressivo REALE (dal conto completo) ai movimenti
  // filtrati mostrati in tabella.
  const movimentiWithBalance = movimentiFiltrati.map(m => ({
    ...m,
    saldoProgressivo: balanceMap[m.id || m.data + m.importo] ?? saldoIniziale,
  }));

  // Totale della sola selezione filtrata (entrate - uscite), mostrato a
  // parte dal saldo reale per non essere confuso con esso.
  const totaleSelezioneFiltrata = movimentiFiltrati.reduce(
    (sum, m) => sum + (m.tipo === 'entrata' ? (m.importo || 0) : -(m.importo || 0)),
    0
  );

  const currentWithBalance = movimentiWithBalance.slice(start, start + itemsPerPage);

  // Reset pagina quando cambiano i filtri
  const resetFilters = () => {
    setFiltroDescrizione('');
    setFiltroCategoria('');
    setFiltroTipo('');
    setFiltroDareAvere('');
    setFiltroDataDa('');
    setFiltroDataA('');
    setFiltroImportoMin('');
    setFiltroImportoMax('');
    setFiltroNumeroFattura('');
    setFiltroDataText('');
    setCurrentPage(1);
  };

  const hasActiveFilters =
    filtroDescrizione ||
    filtroCategoria ||
    filtroDareAvere ||
    filtroDataDa ||
    filtroDataA ||
    filtroImportoMin !== '' ||
    filtroImportoMax !== '' ||
    filtroNumeroFattura ||
    filtroDataText;

  return (
    <div
      style={{
        background: 'white',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid #e5e7eb',
      }}
    >
      {/* Modal Modifica Movimento - solo se non readOnly */}
      {!readOnly && editingMovimento && (
        <EditMovimentoModal
          movimento={editingMovimento}
          tipo={tipo}
          onClose={() => setEditingMovimento(null)}
          onSave={updated => {
            onEdit(updated);
            // Trova l'indice del movimento corrente e passa al successivo
            const currentIndex = currentWithBalance.findIndex(m => m.id === editingMovimento.id);
            const nextIndex = currentIndex + 1;
            if (nextIndex < currentWithBalance.length) {
              // C'è un movimento successivo nella pagina corrente
              setEditingMovimento(currentWithBalance[nextIndex]);
            } else if (currentPage < totalPages) {
              // Vai alla pagina successiva e apri il primo movimento
              setCurrentPage(currentPage + 1);
              // Il movimento verrà aperto dopo il cambio pagina
              setTimeout(() => {
                const firstOfNextPage = movimentiWithBalance[start + itemsPerPage];
                if (firstOfNextPage) {
                  setEditingMovimento(firstOfNextPage);
                } else {
                  setEditingMovimento(null);
                }
              }, 100);
            } else {
              // Fine lista
              setEditingMovimento(null);
            }
          }}
        />
      )}

      {/* FILTRI AVANZATI */}
      <div
        style={{
          padding: '12px 16px',
          background: '#f8fafc',
          borderBottom: '1px solid #e5e7eb',
        }}
      >
        <div
          style={{
            display: 'flex',
            gap: 12,
            flexWrap: 'wrap',
            alignItems: 'center',
            marginBottom: 8,
          }}
        >
          <span style={{ fontWeight: 600, fontSize: 12, color: '#374151' }}>🔍 Filtri:</span>

          {/* Filtro Descrizione */}
          <input
            type="text"
            placeholder="Cerca descrizione..."
            value={filtroDescrizione}
            onChange={e => {
              setFiltroDescrizione(e.target.value);
              setCurrentPage(1);
            }}
            style={{
              padding: '6px 10px',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              fontSize: 12,
              width: 180,
            }}
            data-testid="filtro-descrizione"
          />

          {/* Filtro Categoria */}
          <select
            value={filtroCategoria}
            onChange={e => {
              setFiltroCategoria(e.target.value);
              setCurrentPage(1);
            }}
            style={{
              padding: '6px 10px',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              fontSize: 12,
              background: 'white',
            }}
            data-testid="filtro-categoria"
          >
            <option value="">Tutte le categorie</option>
            {categorieUniche.map(cat => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>

          {/* Filtro DARE/AVERE */}
          <select
            value={filtroDareAvere}
            onChange={e => {
              setFiltroDareAvere(e.target.value);
              setCurrentPage(1);
            }}
            style={{
              padding: '6px 10px',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              fontSize: 12,
              background: 'white',
            }}
            data-testid="filtro-dare-avere"
          >
            <option value="">DARE + AVERE</option>
            <option value="dare">Solo DARE (Entrate)</option>
            <option value="avere">Solo AVERE (Uscite)</option>
          </select>
        </div>

        {/* Seconda riga filtri: Data e Importo */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, fontSize: 12, color: '#374151' }}>📅 Data:</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280' }}>Da</label>
            <input
              type="date"
              value={filtroDataDa}
              onChange={e => {
                setFiltroDataDa(e.target.value);
                setCurrentPage(1);
              }}
              style={{
                padding: '5px 8px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                fontSize: 12,
              }}
              data-testid="filtro-data-da"
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280' }}>A</label>
            <input
              type="date"
              value={filtroDataA}
              onChange={e => {
                setFiltroDataA(e.target.value);
                setCurrentPage(1);
              }}
              style={{
                padding: '5px 8px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                fontSize: 12,
              }}
              data-testid="filtro-data-a"
            />
          </div>

          <span style={{ fontWeight: 600, fontSize: 12, color: '#374151', marginLeft: 8 }}>
            💰 Importo:
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280' }}>Min €</label>
            <input
              type="number"
              placeholder="0"
              value={filtroImportoMin}
              onChange={e => {
                setFiltroImportoMin(e.target.value);
                setCurrentPage(1);
              }}
              style={{
                padding: '5px 8px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                fontSize: 12,
                width: 90,
              }}
              data-testid="filtro-importo-min"
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280' }}>Max €</label>
            <input
              type="number"
              placeholder="∞"
              value={filtroImportoMax}
              onChange={e => {
                setFiltroImportoMax(e.target.value);
                setCurrentPage(1);
              }}
              style={{
                padding: '5px 8px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                fontSize: 12,
                width: 90,
              }}
              data-testid="filtro-importo-max"
            />
          </div>

          {/* Contatore risultati */}
          <span style={{ fontSize: 12, color: '#6b7280', marginLeft: 8 }}>
            {movimentiFiltrati.length} / {movimenti.length} movimenti
          </span>

          {/* Totale della selezione filtrata — separato dal saldo reale del
              conto (colonna Saldo in tabella) per non essere confuso con
              esso: filtrando per es. "F24" questo NON è "quanto c'è in
              cassa/banca", è solo entrate-uscite dei soli movimenti filtrati. */}
          {hasActiveFilters && (
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: totaleSelezioneFiltrata >= 0 ? '#16a34a' : '#dc2626',
                marginLeft: 8,
                padding: '2px 8px',
                background: '#f1f5f9',
                borderRadius: 4,
              }}
              title="Somma entrate-uscite dei soli movimenti filtrati (non è il saldo reale del conto)"
            >
              Totale selezione: {formatEuro(totaleSelezioneFiltrata)}
            </span>
          )}

          {/* Reset Filtri */}
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              style={{
                padding: '6px 12px',
                background: '#dc2626',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                fontSize: 12,
                cursor: 'pointer',
              }}
              data-testid="btn-reset-filtri"
            >
              🔄 Reset filtri
            </button>
          )}
        </div>
      </div>

      {/* Pagination Header */}
      {totalPages > 1 && (
        <div
          style={{
            padding: '12px 16px',
            background: '#0f2744',
            color: 'white',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>
            📄 Pagina {currentPage} di {totalPages} ({movimenti.length} movimenti)
          </span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
              style={{
                padding: '4px 8px',
                borderRadius: 4,
                border: 'none',
                cursor: 'pointer',
                opacity: currentPage === 1 ? 0.5 : 1,
              }}
            >
              «
            </button>
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              style={{
                padding: '4px 8px',
                borderRadius: 4,
                border: 'none',
                cursor: 'pointer',
                opacity: currentPage === 1 ? 0.5 : 1,
              }}
            >
              ‹
            </button>
            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              style={{
                padding: '4px 8px',
                borderRadius: 4,
                border: 'none',
                cursor: 'pointer',
                opacity: currentPage === totalPages ? 0.5 : 1,
              }}
            >
              ›
            </button>
            <button
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages}
              style={{
                padding: '4px 8px',
                borderRadius: 4,
                border: 'none',
                cursor: 'pointer',
                opacity: currentPage === totalPages ? 0.5 : 1,
              }}
            >
              »
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
              <th style={{ padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
                Data
              </th>
              <th
                style={{
                  padding: '8px 8px',
                  textAlign: 'center',
                  fontWeight: 600,
                  fontSize: 11,
                  color: '#64748b',
                  textTransform: 'uppercase',
                  width: 40,
                }}
              >
                T
              </th>
              <th style={{ padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
                Cat.
              </th>
              <th style={{ padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
                Descrizione
              </th>
              <th style={{ padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
                N. Fattura
              </th>
              <th style={{ padding: '8px 8px', textAlign: 'right', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
                DARE
              </th>
              <th style={{ padding: '8px 8px', textAlign: 'right', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
                AVERE
              </th>
              <th style={{ padding: '8px 8px', textAlign: 'right', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>
                Saldo
              </th>
              <th
                style={{ padding: '8px 8px', textAlign: 'center', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}
              >
                Documento
              </th>
              {!readOnly && (
                <th
                  style={{ padding: '8px 8px', textAlign: 'center', fontWeight: 600, fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}
                >
                  Azioni
                </th>
              )}
            </tr>
            <tr style={{ background: '#f3f4f6', borderBottom: '1px solid #e5e7eb' }}>
              <th style={{ padding: '4px 6px' }}>
                <input value={filtroDataText} onChange={e => { setFiltroDataText(e.target.value); setCurrentPage(1); }}
                  placeholder="gg-mm&" style={{ width: '100%', padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 10, boxSizing: 'border-box' }} />
              </th>
              <th style={{ padding: '4px 6px' }}>
                <select value={filtroDareAvere} onChange={e => { setFiltroDareAvere(e.target.value); setCurrentPage(1); }}
                  style={{ width: '100%', padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 10, boxSizing: 'border-box' }}>
                  <option value="">"</option>
                  <option value="dare">↑</option>
                  <option value="avere">↓</option>
                </select>
              </th>
              <th style={{ padding: '4px 6px' }}>
                <select value={filtroCategoria} onChange={e => { setFiltroCategoria(e.target.value); setCurrentPage(1); }}
                  style={{ width: '100%', padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 10, boxSizing: 'border-box' }}>
                  <option value="">Tutte</option>
                  {categorieUniche.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </th>
              <th style={{ padding: '4px 6px' }}>
                <input value={filtroDescrizione} onChange={e => { setFiltroDescrizione(e.target.value); setCurrentPage(1); }}
                  placeholder="Cerca&" style={{ width: '100%', padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 10, boxSizing: 'border-box' }} />
              </th>
              <th style={{ padding: '4px 6px' }}>
                <input value={filtroNumeroFattura} onChange={e => { setFiltroNumeroFattura(e.target.value); setCurrentPage(1); }}
                  placeholder="N.&" style={{ width: '100%', padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 10, boxSizing: 'border-box' }} />
              </th>
              <th style={{ padding: '4px 6px' }}>
                <input value={filtroImportoMin} onChange={e => { setFiltroImportoMin(e.target.value); setCurrentPage(1); }}
                  placeholder="Min €" style={{ width: '100%', padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 10, boxSizing: 'border-box' }} />
              </th>
              <th style={{ padding: '4px 6px' }}>
                <input value={filtroImportoMax} onChange={e => { setFiltroImportoMax(e.target.value); setCurrentPage(1); }}
                  placeholder="Max €" style={{ width: '100%', padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 10, boxSizing: 'border-box' }} />
              </th>
              <th />
              <th />
              {!readOnly && <th />}
            </tr>
          </thead>
          <tbody>
            {currentWithBalance.map((mov, idx) => (
              <tr
                key={mov.id || idx}
                style={{
                  borderBottom: '1px solid #f1f5f9',
                  background: idx % 2 === 0 ? 'white' : '#f8fafc',
                }}
                data-testid={`movimento-row-${mov.id || idx}`}
              >
                <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 11 }}>
                  {formatDate(mov.data)}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                  <span
                    style={{
                      padding: '2px 6px',
                      borderRadius: 4,
                      fontSize: 9,
                      fontWeight: 'bold',
                      background: mov.tipo === 'entrata' ? '#dcfce7' : '#fee2e2',
                      color: mov.tipo === 'entrata' ? '#166534' : '#991b1b',
                    }}
                  >
                    {mov.tipo === 'entrata' ? '↑' : '↓'}
                  </span>
                </td>
                <td style={{ padding: '6px 8px' }}>
                  <span
                    style={{
                      background: '#f3f4f6',
                      padding: '2px 4px',
                      borderRadius: 3,
                      fontSize: 10,
                    }}
                  >
                    {mov.categoria || '-'}
                  </span>
                </td>
                <td
                  style={{
                    padding: '6px 8px',
                    maxWidth: 400,
                    wordBreak: 'break-word',
                    whiteSpace: 'pre-wrap',
                    fontSize: 11,
                    lineHeight: 1.3,
                  }}
                >
                  {splitNumeroFattura(mov).descr || '-'}
                </td>
                <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 11, whiteSpace: 'nowrap' }}>
                  {splitNumeroFattura(mov).numero || '-'}
                </td>
                <td
                  style={{
                    padding: '6px 8px',
                    textAlign: 'right',
                    color: '#16a34a',
                    fontWeight: mov.tipo === 'entrata' ? 'bold' : 'normal',
                    fontSize: 12,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  }}
                >
                  {mov.tipo === 'entrata' ? formatEuro(mov.importo) : '-'}
                </td>
                <td
                  style={{
                    padding: '6px 8px',
                    textAlign: 'right',
                    color: '#dc2626',
                    fontWeight: mov.tipo === 'uscita' ? 'bold' : 'normal',
                    fontSize: 12,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  }}
                >
                  {mov.tipo === 'uscita' ? formatEuro(mov.importo) : '-'}
                </td>
                <td
                  style={{
                    padding: '6px 8px',
                    textAlign: 'right',
                    fontWeight: 'bold',
                    color: mov.saldoProgressivo >= 0 ? '#16a34a' : '#dc2626',
                    fontSize: 12,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  }}
                >
                  {formatEuro(mov.saldoProgressivo)}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                  {/* Pulsante VEDI documento - Supporta: Fattura, F24, Corrispettivi, Bonifici */}
                  {mov.fattura_id ? (
                    <button
                      onClick={() =>
                        setFatturaView({
                          id: mov.fattura_id,
                          numero: mov.numero_fattura || mov.numero || mov.descrizione,
                        })
                      }
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#3b82f6',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                      }}
                      title="Visualizza Fattura"
                      data-testid={`view-fattura-${mov.id || idx}`}
                    >
                      Fattura
                    </button>
                  ) : mov.bonifico_pdf_id ? (
                    <a
                      href={`/api/archivio-bonifici/transfers/${mov.bonifico_pdf_id}/pdf`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#0f2744',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                        textDecoration: 'none',
                      }}
                      title="Visualizza Bonifico PDF"
                      data-testid={`view-bonifico-${mov.id || idx}`}
                    >
                      Bonifico
                    </a>
                  ) : mov.f24_id ? (
                    <a
                      href={`/api/f24/${mov.f24_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#dc2626',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                        textDecoration: 'none',
                      }}
                      title="Visualizza F24"
                      data-testid={`view-f24-${mov.id || idx}`}
                    >
                      📄 F24
                    </a>
                  ) : mov.corrispettivo_id || mov.xml_filename ? (
                    <a
                      href={
                        mov.corrispettivo_id
                          ? `/api/corrispettivi/${mov.corrispettivo_id}/view`
                          : `/api/corrispettivi/view-by-filename?filename=${encodeURIComponent(mov.xml_filename)}`
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#16a34a',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                        textDecoration: 'none',
                      }}
                      title="Visualizza Corrispettivo"
                      data-testid={`view-corrispettivo-${mov.id || idx}`}
                    >
                      🧾 Corrisp.
                    </a>
                  ) : mov.categoria === 'F24' ||
                    (mov.descrizione && mov.descrizione.includes('F24')) ? (
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#fef3c7',
                        color: '#92400e',
                        border: '1px solid #d97706',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 'bold',
                      }}
                      title="F24 - Documento da allegare"
                    >
                      📄 F24
                    </span>
                  ) : (
                    <span style={{ color: '#9ca3af', fontSize: 11 }}>-</span>
                  )}
                </td>
                {!readOnly && (
                  <td style={{ padding: '6px 8px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    <button
                      onClick={async () => {
                        setSpostando(mov.id);
                        try {
                          await onSposta(mov.id, tipo, tipo === 'cassa' ? 'banca' : 'cassa');
                        } finally {
                          setSpostando(null);
                        }
                      }}
                      disabled={spostando === mov.id}
                      style={{
                        background: '#0f2744',
                        color: 'white',
                        border: 'none',
                        borderRadius: 4,
                        padding: '3px 6px',
                        cursor: spostando === mov.id ? 'wait' : 'pointer',
                        fontSize: 10,
                        marginRight: 4,
                        opacity: spostando === mov.id ? 0.6 : 1,
                      }}
                      title={tipo === 'cassa' ? 'Sposta in Banca' : 'Sposta in Cassa'}
                      data-testid={`sposta-movimento-${mov.id}`}
                    >
                      {spostando === mov.id ? '⏳' : tipo === 'cassa' ? '🏦' : '💵'}
                    </button>
                    <button
                      onClick={() => setEditingMovimento(mov)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: 14,
                        marginRight: 4,
                      }}
                      title="Modifica"
                      data-testid={`edit-movimento-${mov.id}`}
                    >
                      📝
                    </button>
                    <button
                      onClick={() => onDelete(mov.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: 14,
                      }}
                      title="Elimina"
                    >
                      🗑️
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {movimenti.length === 0 && (
        <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
          {readOnly ? (
            "Nessun movimento nell'estratto conto. Importa un file CSV dalla pagina Import/Export."
          ) : tipo === 'cassa' ? (
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: '#374151' }}>
                Nessun movimento in Cassa
              </div>
              <div style={{ fontSize: 13, color: '#6b7280', maxWidth: 400, margin: '0 auto' }}>
                La cassa è vuota. Aggiungi movimenti tramite le{' '}
                <strong>Chiusure Giornaliere</strong> (Corrispettivo, POS, Versamento). Le fatture
                pagate in contanti vengono importate <strong>automaticamente</strong> ogni 30 minuti.
              </div>
            </div>
          ) : (
            'Nessun movimento trovato'
          )}
        </div>
      )}

      {/* Footer con Paginazione ANCHE IN BASSO */}
      {movimenti.length > 0 && (
        <div
          style={{
            padding: 12,
            background: '#f9fafb',
            borderTop: '1px solid #e5e7eb',
            fontSize: 12,
            color: '#6b7280',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              Mostrando {start + 1}-{Math.min(start + itemsPerPage, movimenti.length)} di{' '}
              {movimenti.length} movimenti
            </span>
            {totalPages > 1 && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span>
                  📄 Pagina {currentPage} di {totalPages}
                </span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    onClick={() => setCurrentPage(1)}
                    disabled={currentPage === 1}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 4,
                      border: 'none',
                      cursor: 'pointer',
                      opacity: currentPage === 1 ? 0.5 : 1,
                      background: '#e5e7eb',
                    }}
                  >
                    «
                  </button>
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 4,
                      border: 'none',
                      cursor: 'pointer',
                      opacity: currentPage === 1 ? 0.5 : 1,
                      background: '#e5e7eb',
                    }}
                  >
                    ‹
                  </button>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 4,
                      border: 'none',
                      cursor: 'pointer',
                      opacity: currentPage === totalPages ? 0.5 : 1,
                      background: '#e5e7eb',
                    }}
                  >
                    ›
                  </button>
                  <button
                    onClick={() => setCurrentPage(totalPages)}
                    disabled={currentPage === totalPages}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 4,
                      border: 'none',
                      cursor: 'pointer',
                      opacity: currentPage === totalPages ? 0.5 : 1,
                      background: '#e5e7eb',
                    }}
                  >
                    »
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Componente Modal per Modifica Movimento
function EditMovimentoModal({ movimento, tipo, onClose, onSave }) {
  const isMobile = useIsMobile();
  const [errorMsg, setErrorMsg] = useState('');
  const [form, setForm] = useState({
    data: movimento.data || '',
    tipo: movimento.tipo || 'uscita',
    importo: movimento.importo || '',
    descrizione: movimento.descrizione || '',
    categoria: movimento.categoria || '',
    riferimento: movimento.riferimento || '',
    note: movimento.note || '',
  });
  const [saving, setSaving] = useState(false);

  const categorie =
    tipo === 'cassa'
      ? ['Corrispettivi', 'POS', 'Versamento', 'Pagamento fornitore', 'Incasso', 'Spese', 'Altro']
      : ['Pagamento fornitore', 'Bonifico', 'Assegno', 'F24', 'Altro'];

  const handleSubmit = async e => {
    e.preventDefault();
    if (!form.importo || !form.descrizione) {
      setErrorMsg('Compila importo e descrizione.');
      return;
    }

    setErrorMsg('');
    setSaving(true);
    try {
      const endpoint =
        tipo === 'cassa'
          ? `/api/prima-nota/cassa/${movimento.id}`
          : `/api/prima-nota/banca/${movimento.id}`;

      await api.put(endpoint, {
        data: form.data,
        tipo: form.tipo,
        importo: parseFloat(form.importo),
        descrizione: form.descrizione,
        categoria: form.categoria,
        riferimento: form.riferimento,
        note: form.note,
      });

      onSave({ ...movimento, ...form, importo: parseFloat(form.importo) });
    } catch (error) {
      console.error('Errore salvataggio:', error);
      setErrorMsg(error.response?.data?.message || error.message || 'Errore nel salvataggio.');
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid #d1d5db',
    borderRadius: 8,
    fontSize: 14,
    outline: 'none',
  };

  const labelStyle = {
    display: 'block',
    fontSize: 12,
    fontWeight: 600,
    color: '#374151',
    marginBottom: 4,
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'white',
          borderRadius: 10,
          width: '100%',
          maxWidth: 500,
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 24px',
            borderBottom: '1px solid #e5e7eb',
            background: '#0f2744',
            borderRadius: '10px 10px 0 0',
            color: 'white',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
            📝 Modifica Movimento {tipo === 'cassa' ? 'Cassa' : 'Banca'}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(255,255,255,0.2)',
              border: 'none',
              borderRadius: 8,
              minWidth: 40,
              minHeight: 40,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: 'white',
            }}
            aria-label="Chiudi"
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ padding: 24 }}>
          <div style={{ display: 'grid', gap: 16 }}>
            {errorMsg && (
              <div
                style={{
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  color: '#b91c1c',
                  borderRadius: 8,
                  padding: '10px 12px',
                  fontSize: 13,
                }}
              >
                {errorMsg}
              </div>
            )}
            {/* Data e Tipo */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                gap: 12,
              }}
            >
              <div>
                <label style={labelStyle}>Data</label>
                <input
                  type="date"
                  value={form.data}
                  onChange={e => setForm({ ...form, data: e.target.value })}
                  style={inputStyle}
                  required
                />
              </div>
              <div>
                <label style={labelStyle}>Tipo</label>
                <select
                  value={form.tipo}
                  onChange={e => setForm({ ...form, tipo: e.target.value })}
                  style={inputStyle}
                >
                  <option value="entrata">↑ DARE (Entrata)</option>
                  <option value="uscita">↓ AVERE (Uscita)</option>
                </select>
              </div>
            </div>

            {/* Importo */}
            <div>
              <label style={labelStyle}>Importo (€)</label>
              <input
                type="number"
                step="0.01"
                value={form.importo}
                onChange={e => setForm({ ...form, importo: e.target.value })}
                style={inputStyle}
                placeholder="0.00"
                required
              />
            </div>

            {/* Categoria */}
            <div>
              <label style={labelStyle}>Categoria</label>
              <select
                value={form.categoria}
                onChange={e => setForm({ ...form, categoria: e.target.value })}
                style={inputStyle}
              >
                <option value="">-- Seleziona --</option>
                {categorie.map(cat => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>

            {/* Descrizione */}
            <div>
              <label style={labelStyle}>Descrizione</label>
              <input
                type="text"
                value={form.descrizione}
                onChange={e => setForm({ ...form, descrizione: e.target.value })}
                style={inputStyle}
                placeholder="Descrizione movimento"
                required
              />
            </div>

            {/* Riferimento */}
            <div>
              <label style={labelStyle}>Riferimento (opzionale)</label>
              <input
                type="text"
                value={form.riferimento}
                onChange={e => setForm({ ...form, riferimento: e.target.value })}
                style={inputStyle}
                placeholder="N. fattura, documento, ecc."
              />
            </div>

            {/* Note */}
            <div>
              <label style={labelStyle}>Note (opzionale)</label>
              <textarea
                value={form.note}
                onChange={e => setForm({ ...form, note: e.target.value })}
                style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
                placeholder="Note aggiuntive..."
              />
            </div>
          </div>

          {/* Footer */}
          <div
            style={{
              marginTop: 24,
              paddingTop: 16,
              borderTop: '1px solid #e5e7eb',
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 12,
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '10px 20px',
                borderRadius: 8,
                border: '1px solid #d1d5db',
                background: 'white',
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: 500,
              }}
            >
              Annulla
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: '10px 20px',
                borderRadius: 6,
                border: 'none',
                background: '#0f2744',
                color: 'white',
                cursor: saving ? 'not-allowed' : 'pointer',
                fontSize: 14,
                fontWeight: 600,
                opacity: saving ? 0.7 : 1,
              }}
            >
              {saving ? 'Salvataggio...' : '💾 Salva Modifiche'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
