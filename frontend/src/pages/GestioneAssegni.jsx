import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { formatEuro, formatDateIT, formatDateGGMM, STYLES, COLORS, SHADOWS, BORDER_RADIUS, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import ModalFattura from '../components/ModalFattura';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { toast } from 'sonner';
import { Button, Badge, StatCard, Table, TableWrap, Th, Td, Input, RowActions, RowActionButton, ListaAdattiva } from '../components/ds';

// Fornitori mai pagabili con assegno (dettato utente 18/07/2026): arrivano
// su carta di credito o addebito bancario, al limite bonifico — mai assegno.
const FORNITORI_MAI_ASSEGNO = [
  'amazon', 'abc acquedotto', 'acquedotto', 'acqua bene comune', 'fastweb',
  'paypal', 'enel', 'leasys', 'arval',
];

const parseImportoFiltro = value => {
  const raw = String(value ?? '').trim().replace(/\s/g, '');
  if (!raw) return null;
  const normalizzato = raw.includes(',')
    ? raw.replace(/\./g, '').replace(',', '.')
    : raw;
  const numero = Number(normalizzato);
  return Number.isFinite(numero) ? numero : null;
};

export const normalizzaBeneficiarioAssegno = value => {
  const beneficiario = String(value ?? '').trim();
  return ['', '-', 'n/a', 'non disponibile'].includes(beneficiario.toLowerCase())
    ? ''
    : beneficiario;
};

export const residuoFattura = fattura => {
  const totale = Number(fattura?.total_amount || fattura?.importo_totale || 0);
  if (fattura?.importo_residuo !== undefined && fattura?.importo_residuo !== null) {
    return Math.max(0, Number(fattura.importo_residuo) || 0);
  }
  return Math.max(0, totale - (Number(fattura?.importo_pagato) || 0));
};

const TOLLERANZA_ASSEGNO = 0.005;

export const totaleQuoteFatture = fatture =>
  (fatture || []).reduce(
    (somma, fattura) => somma + Number(fattura?.quota ?? fattura?.importo ?? 0),
    0
  );

export const assegnoInteramenteAssociato = (importoAssegno, fatture) => {
  const importo = Number(importoAssegno || 0);
  if (importo <= 0 || !fatture?.length) return false;
  return Math.abs(importo - totaleQuoteFatture(fatture)) <= TOLLERANZA_ASSEGNO;
};

const distanzaFatturaDaAssegno = (fattura, importoAssegno) => {
  const importo = Number(importoAssegno || 0);
  const valori = [residuoFattura(fattura)];
  (fattura?.pagamento_rate || []).forEach(rata => valori.push(Number(rata?.importo) || 0));
  return Math.min(...valori.map(valore => Math.abs(valore - importo)));
};

export function filtraAssegni(assegni, filtri = {}) {
  const {
    fornitore = '', importoEsatto = '', importoMin = '', importoMax = '',
    numeroAssegno = '', numeroFattura = '', soloDaAssociare = false,
  } = filtri;
  const esatto = parseImportoFiltro(importoEsatto);
  const minimo = parseImportoFiltro(importoMin);
  const massimo = parseImportoFiltro(importoMax);
  const cifreNumero = String(numeroAssegno).replace(/\D/g, '');

  return assegni.filter(a => {
    const numero = String(a.numero || a.numero_assegno || '');
    if (!numero) return false;
    const importoVuoto = a.importo === null || a.importo === undefined || a.importo === '';
    const importo = importoVuoto ? null : Number(a.importo) || 0;
    if (fornitore && !String(a.beneficiario || '').toLowerCase().includes(fornitore.toLowerCase())) return false;
    if ((esatto !== null || minimo !== null || massimo !== null) && importoVuoto) return false;
    if (esatto !== null && Math.abs(importo - esatto) > 0.009) return false;
    if (minimo !== null && importo < minimo) return false;
    if (massimo !== null && importo > massimo) return false;
    if (cifreNumero.length >= 3 && !numero.replace(/\D/g, '').includes(cifreNumero)) return false;
    if (numeroFattura && !String(a.numero_fattura || '').toLowerCase().includes(numeroFattura.toLowerCase())) return false;
    if (soloDaAssociare && normalizzaBeneficiarioAssegno(a.beneficiario)) return false;
    return true;
  });
}

const STATI_ASSEGNO = {
  vuoto: { label: 'Valido', variant: 'success' },
  compilato: { label: 'Compilato', variant: 'info' },
  emesso: { label: 'Emesso', variant: 'warning' },
  parzialmente_assegnato: { label: 'Parz. assegnato', variant: 'warning' },
  assegnato: { label: 'Assegnato', variant: 'info' },
  incassato: { label: 'Incassato', variant: 'accent' },
  annullato: { label: 'Annullato', variant: 'danger' },
};

export default function GestioneAssegni() {
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
  const [assegni, setAssegni] = useState([]);
  const [_stats, setStats] = useState({ totale: 0, per_stato: {} });
  const [loading, setLoading] = useState(true);
  const [filterStato, _setFilterStato] = useState('');
  const [search, _setSearch] = useState('');

  // NUOVI FILTRI
  const [filterFornitore, setFilterFornitore] = useState('');
  const [filterImportoEsatto, setFilterImportoEsatto] = useState('');
  const [filterImportoMin, setFilterImportoMin] = useState('');
  const [filterImportoMax, setFilterImportoMax] = useState('');
  const [filterNumeroAssegno, setFilterNumeroAssegno] = useState('');
  const [filterNumeroFattura, setFilterNumeroFattura] = useState('');
  const [filterSoloDaAssociare, setFilterSoloDaAssociare] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  // Niente più stato locale per l'anno: prima "filterAnno" si inizializzava
  // dall'anno globale ma restava locale — cambiando l'anno in alto la
  // pagina ricaricava (era in dependency array) ma continuava a
  // interrogare il vecchio filterAnno, mai riallineato. Si usa sempre e
  // solo "anno" (globale), come tutte le altre pagine dell'app.

  // Responsive (telefono/tablet)
  const isMobile = useIsMobile();

  // Menu "⚙️ Altro" (azioni secondarie consolidate)
  const [showAltroMenu, setShowAltroMenu] = useState(false);
  const altroMenuRef = useRef(null);
  useEffect(() => {
    if (!showAltroMenu) return;
    const handle = e => {
      if (altroMenuRef.current && !altroMenuRef.current.contains(e.target)) {
        setShowAltroMenu(false);
      }
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [showAltroMenu]);

  // Modale visualizzazione fattura in-page ({id, numero}) - niente nuove schede
  const [fatturaView, setFatturaView] = useState(null);

  // Generate modal
  const [showGenerate, setShowGenerate] = useState(false);
  const [generateForm, setGenerateForm] = useState({ numero_primo: '', quantita: 10 });
  const [generating, setGenerating] = useState(false);
  const [newlyGeneratedNumbers, setNewlyGeneratedNumbers] = useState(new Set());

  // Edit inline
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  // Fatture per collegamento
  const [fatture, setFatture] = useState([]);
  const [loadingFatture, setLoadingFatture] = useState(false);
  const [selectedFatture, setSelectedFatture] = useState([]);
  const [showFattureModal, setShowFattureModal] = useState(false);
  const [editingAssegnoForFatture, setEditingAssegnoForFatture] = useState(null);
  const [filterFatturaModal, setFilterFatturaModal] = useState('');

  // Drag state per modal
  const [modalPosition, setModalPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    // RIMOSSO: ricostruisciDatiMancanti() automatico - ora solo manuale in Admin
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterStato, search, anno]);

  /**
   * LOGICA INTELLIGENTE: Ricostruisce automaticamente i dati mancanti.
   *
   * Questa funzione implementa la logica di un commercialista esperto:
   * 1. Estrae beneficiario dalla descrizione bancaria
   * 2. Cerca fatture con lo stesso importo per associazione
   * 3. Gestisce pagamenti parziali/splittati
   *
   * Viene eseguita automaticamente al caricamento della pagina.
   */
  const ricostruisciDatiMancanti = async () => {
    try {
      const res = await api.post('/api/assegni/ricostruisci-dati');
      if (res.data.beneficiari_trovati > 0 || res.data.fatture_associate > 0) {
        
        // Ricarica dopo ricostruzione
        loadData();
      }
    } catch (error) {
      console.warn('Ricostruzione dati non riuscita:', error);
    }
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filterStato) params.append('stato', filterStato);
      if (search) params.append('search', search);
      params.append('anno', anno);

      const [assegniRes, statsRes] = await Promise.all([
        api.get(`/api/assegni?${params}`),
        api.get(`/api/assegni/stats?anno=${anno}`),
      ]);

      // Ordina per numero assegno decrescente (dal più recente al più vecchio)
      const assegniOrdinati = (assegniRes.data || []).sort((a, b) => {
        const numA = parseInt((a.numero || a.numero_assegno || '').replace(/\D/g, '') || '0');
        const numB = parseInt((b.numero || b.numero_assegno || '').replace(/\D/g, '') || '0');
        return numB - numA; // Decrescente
      });

      setAssegni(assegniOrdinati);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Error loading assegni:', error);
    } finally {
      setLoading(false);
    }
  };

  // Carica fatture non pagate per collegamento - SOLO dello stesso fornitore
  const loadFatture = async (beneficiario = '', importoAssegno = 0) => {
    setLoadingFatture(true);
    try {
      const params = new URLSearchParams();
      params.append('anno', anno);
      params.append('limit', '1000');
      // IMPORTANTE: se c'è un beneficiario, filtra SOLO quelle del beneficiario
      const res = await api.get(`/api/invoices?${params}`);
      const items = res.data.items || res.data || [];
      // Escludi soltanto le fatture già pagate. La scelta dell'assegno per
      // una fattura specifica prevale sul metodo abituale cassa/misto del
      // fornitore e viene poi confermata dall'estratto conto.
      let filtered = items.filter(f => {
        if (f.status === 'paid' || f.payment_status === 'paid' || f.pagato === true) return false;
        // Fornitori mai pagabili con assegno (dettato utente 18/07/2026):
        // arrivano su carta di credito o addebito bancario, mai su assegno.
        const fornitoreNome = (f.supplier_name || f.cedente_denominazione || '').toLowerCase();
        if (FORNITORI_MAI_ASSEGNO.some(k => fornitoreNome.includes(k))) {
          return false;
        }
        return true;
      });

      // FILTRO AGGIUNTIVO: Se c'è un beneficiario, mostra SOLO fatture di quel fornitore
      // Questo perché non si può pagare con un assegno fatture di fornitori diversi
      const benefLower = beneficiario.toLowerCase();
      const stessoBeneficiario = fattura => {
        if (!benefLower) return false;
        const fornitore = (fattura.supplier_name || fattura.cedente_denominazione || '').toLowerCase();
        return (
          fornitore.includes(benefLower.substring(0, 5)) ||
          benefLower.includes(fornitore.substring(0, 5)) ||
          fornitore.split(' ').some(word => benefLower.includes(word) && word.length > 3)
        );
      };

      // Prima le fatture con importo piu vicino all'assegno: quando il
      // beneficiario non e ancora noto, la candidata utile resta subito
      // visibile anche con centinaia di fatture nell'anno.
      filtered.sort((a, b) => {
        if (stessoBeneficiario(a) !== stessoBeneficiario(b)) return stessoBeneficiario(a) ? -1 : 1;
        const importoA = distanzaFatturaDaAssegno(a, importoAssegno);
        const importoB = distanzaFatturaDaAssegno(b, importoAssegno);
        if (importoA !== importoB) return importoA - importoB;
        const fornA = (a.supplier_name || a.cedente_denominazione || '').toLowerCase();
        const fornB = (b.supplier_name || b.cedente_denominazione || '').toLowerCase();
        // N/A e vuoti vanno in fondo
        if (!fornA && fornB) return 1;
        if (fornA && !fornB) return -1;
        if (fornA !== fornB) return fornA.localeCompare(fornB);
        // Stesso fornitore: NC (TD04) dopo le fatture normali
        const tipoA = a.tipo_documento || a.document_type || 'TD01';
        const tipoB = b.tipo_documento || b.document_type || 'TD01';
        if (tipoA !== tipoB) return tipoA === 'TD04' ? 1 : -1;
        // Stesso tipo: per data decrescente
        return (b.invoice_date || '').localeCompare(a.invoice_date || '');
      });

      setFatture(filtered);
    } catch (error) {
      console.error('Error loading fatture:', error);
      setFatture([]);
    } finally {
      setLoadingFatture(false);
    }
  };

  const handleGenerate = async () => {
    if (!generateForm.numero_primo) {
      toast.warning('Inserisci il numero del primo assegno');
      return;
    }

    setGenerating(true);
    try {
      const res = await api.post(`/api/assegni/genera`, { ...generateForm, anno });
      const numeri = res.data?.numeri || [];
      setNewlyGeneratedNumbers(new Set(numeri));
      setShowGenerate(false);
      setGenerateForm({ numero_primo: '', quantita: 10 });
      await loadData();
      toast.success(
        `Carnet creato: ${res.data?.generati ?? numeri.length} assegni da ${res.data?.primo} a ${res.data?.ultimo}`
      );
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGenerating(false);
    }
  };

  const handleClearEmpty = async () => {
    try {
      const res = await api.delete(`/api/assegni/clear-generated?stato=vuoto`);
      toast.success(res.data.message);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };
;

  const startEdit = assegno => {
    setEditingId(assegno.id);
    setEditForm({
      beneficiario: assegno.beneficiario || '',
      importo: assegno.importo || '',
      data_fattura: assegno.data_fattura || '',
      numero_fattura: assegno.numero_fattura || '',
      note: assegno.note || '',
      fatture_collegate: assegno.fatture_collegate || [],
    });
  };

  const handleSaveEdit = async () => {
    if (!editingId) return;

    try {
      await api.put(`/api/assegni/${editingId}`, {
        ...editForm,
        stato: editForm.importo && editForm.beneficiario ? 'compilato' : 'vuoto',
      });
      setEditingId(null);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({});
  };

  // Le fatture collegate salvate nel DB hanno lo schema canonico
  // {fattura_id, quota}: qui le arricchiamo coi dati della fattura (numero,
  // fornitore, importo) per poterle mostrare nel modale. Recuperiamo la
  // fattura via API diretta invece di cercarla nell'elenco "disponibili"
  // (che esclude quelle già pagate/di altri filtri) così il collegamento
  // esistente è sempre visibile, anche se la fattura non è più "disponibile".
  const openFattureModal = async assegno => {
    setEditingAssegnoForFatture(assegno);
    setSelectedFatture([]);
    setFilterFatturaModal('');
    setShowFattureModal(true);
    loadFatture(normalizzaBeneficiarioAssegno(assegno.beneficiario), assegno.importo);

    const collegate = assegno.fatture_collegate || [];
    if (collegate.length === 0) return;
    const arricchite = await Promise.all(
      collegate.map(async fc => {
        try {
          const res = await api.get(`/api/invoices/${fc.fattura_id}`);
          const inv = res.data;
          const tipoDoc = inv.tipo_documento || inv.document_type || 'TD01';
          const isNC = tipoDoc === 'TD04';
          return {
            id: fc.fattura_id,
            numero: inv.invoice_number || inv.numero_fattura || fc.fattura_id,
            fornitore: inv.supplier_name || inv.cedente_denominazione || '',
            importo: isNC ? -Math.abs(fc.quota) : fc.quota,
            quota: fc.quota,
            data: inv.invoice_date || inv.data_fattura,
            tipo_documento: tipoDoc,
            is_nota_credito: isNC,
          };
        } catch {
          // Fattura non più raggiungibile (es. cancellata): mostriamo comunque
          // la quota così l'utente vede che l'assegno è impegnato per quella cifra.
          return {
            id: fc.fattura_id,
            numero: fc.fattura_id,
            fornitore: '(fattura non trovata)',
            importo: fc.quota,
            quota: fc.quota,
            data: null,
            tipo_documento: 'TD01',
            is_nota_credito: false,
          };
        }
      })
    );
    setSelectedFatture(arricchite);
  };

  const toggleFattura = fattura => {
    const exists = selectedFatture.find(f => f.id === fattura.id);
    if (exists) {
      setSelectedFatture(selectedFatture.filter(f => f.id !== fattura.id));
    } else if (selectedFatture.length < 4) {
      if (assegnoInteramenteAssociato(editingAssegnoForFatture?.importo, selectedFatture)) {
        toast.info('Assegno già interamente associato', {
          description: 'Rimuovi prima la fattura collegata se devi modificare l’associazione.',
        });
        return;
      }
      // REGOLA CONTABILE: Un assegno può pagare solo fatture dello STESSO fornitore
      const fornitoreNuovo =
        fattura.supplier_name || fattura.cedente_denominazione || fattura.fornitore;
      const fornitoreEsistente = selectedFatture[0]?.fornitore;

      if (
        fornitoreEsistente &&
        fornitoreNuovo &&
        fornitoreNuovo.toLowerCase() !== fornitoreEsistente.toLowerCase()
      ) {
        toast.warning('Non puoi collegare fatture di fornitori diversi allo stesso assegno', {
          description: 'Fornitore selezionato: ' + fornitoreEsistente + ' — stai cercando di aggiungere: ' + fornitoreNuovo,
        });
        return;
      }

      // Usa importo pre-calcolato (negativo per NC)
      const tipoDoc = fattura.tipo_documento || fattura.document_type || 'TD01';
      const isNC = tipoDoc === 'TD04';
      const importoRaw = parseFloat(
        fattura.total_amount || fattura.importo_totale || fattura.importo || 0
      );
      const giaSelezionato = totaleQuoteFatture(selectedFatture);
      const disponibileAssegno = Math.max(
        0, Number(editingAssegnoForFatture?.importo || 0) - giaSelezionato
      );
      const residuo = residuoFattura(fattura) || importoRaw;
      const quota = isNC
        ? -Math.abs(importoRaw)
        : Math.min(residuo, disponibileAssegno);

      if (!isNC && quota <= TOLLERANZA_ASSEGNO) {
        toast.info('L’importo dell’assegno è già completamente coperto');
        return;
      }

      setSelectedFatture([
        ...selectedFatture,
        {
          id: fattura.id,
          numero: fattura.invoice_number || fattura.numero_fattura,
          importo: quota,
          quota,
          data: fattura.invoice_date || fattura.data_fattura,
          fornitore: fornitoreNuovo,
          tipo_documento: tipoDoc,
          is_nota_credito: isNC,
        },
      ]);
    } else {
      toast.warning('Puoi collegare massimo 4 fatture per assegno');
    }
  };

  const saveFattureCollegate = async () => {
    if (!editingAssegnoForFatture) return;

    try {
      // Schema canonico (memoria/LOGICA_OPERATIVA.md): l'assegno mantiene il
      // suo importo nominale, ogni fattura riceve una quota. Il backend
      // aggiorna importo_pagato/assegni_collegati sulle fatture e lo stato
      // dell'assegno (assegnato/parzialmente_assegnato) coerentemente.
      await api.put(`/api/assegni/${editingAssegnoForFatture.id}/fatture-collegate`, {
        fatture: selectedFatture.map(f => ({ fattura_id: f.id, quota: f.quota ?? f.importo })),
      });

      setShowFattureModal(false);
      setEditingAssegnoForFatture(null);
      setSelectedFatture([]);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDelete = async assegno => {
    // Azione distruttiva: conferma esplicita come nelle altre pagine (bonifici,
    // riconciliazione). Prima eliminava l'assegno al primo click senza chiedere.
    const ok = await confirm({
      title: 'Elimina assegno',
      message: `Eliminare l'assegno ${assegno.numero_assegno || assegno.numero || ''}${
        assegno.beneficiario ? ' a ' + assegno.beneficiario : ''
      }? L'operazione non è reversibile.`,
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await api.delete(`/api/assegni/${assegno.id}`);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Auto-associa assegni alle fatture
  const [autoAssociating, setAutoAssociating] = useState(false);
  const [autoAssocResult, setAutoAssocResult] = useState(null);

  // Ambigui auto-match: risoluzione manuale
  const [ambiguiOpen, setAmbiguiOpen] = useState(false);
  const [ambiguiLoading, setAmbiguiLoading] = useState(false);
  const [ambiguiList, setAmbiguiList] = useState([]);
  const [ambiguiSelections, setAmbiguiSelections] = useState({}); // {assegnoId: [fatturaId,...]}
  const [ambiguiResolving, setAmbiguiResolving] = useState({});

  // Learning Machine - nuovi stati
  const [learningLoading, setLearningLoading] = useState(false);
  const [learningResult, setLearningResult] = useState(null);
  const [puliziaLoading, setPuliziaLoading] = useState(false);
  const [puliziaResult, setPuliziaResult] = useState(null);
  const [statsAvanzate, setStatsAvanzate] = useState(null);

  // Associazione combinata (più assegni = 1 fattura)
  const [combinazioneLoading, setCombinazioneLoading] = useState(false);
  const [combinazioneResult, setCombinazioneResult] = useState(null);

  // Selezione multipla per stampa PDF
  const [selectedAssegni, setSelectedAssegni] = useState(new Set());

  // Assegni non associati (per associazione manuale)
  const [assegniNonAssociati, setAssegniNonAssociati] = useState([]);
  const [loadingNonAssociati, setLoadingNonAssociati] = useState(false);
  const [showNonAssociati, setShowNonAssociati] = useState(false);

  // Carica assegni senza beneficiario
  const loadAssegniNonAssociati = async () => {
    setLoadingNonAssociati(true);
    try {
      const res = await api.get('/api/assegni/senza-associazione');
      setAssegniNonAssociati(res.data);
    } catch (error) {
      console.error('Error loading assegni non associati:', error);
    } finally {
      setLoadingNonAssociati(false);
    }
  };

  // Associa manualmente un assegno a una fattura;

  const handleAutoAssocia = async () => {
    setAutoAssociating(true);
    setAutoAssocResult(null);
    try {
      const res = await api.post('/api/assegni/auto-associa');
      setAutoAssocResult(res.data);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setAutoAssociating(false);
    }
  };

  const handleAutoMatch = async () => {
    setAutoAssociating(true);
    setAutoAssocResult(null);
    try {
      const url = `/api/assegni/auto-match?dry_run=true&anno=${anno}`;
      const res = await api.post(url);
      setAutoAssocResult({
        ...res.data,
        _modalita_auto_match: true,
        _dry_run: true,
      });
    } catch (error) {
      toast.error('Errore Auto-Match: ' + (error.response?.data?.detail || error.message));
    } finally {
      setAutoAssociating(false);
    }
  };

  const handleConfirmMatch = async (proposta, livello) => {
    const assegnoIds = proposta.assegno_id
      ? [proposta.assegno_id]
      : (proposta.assegni || []).map(a => (typeof a === 'string' ? a : a.assegno_id));
    const fatturaIds = proposta.fattura_id
      ? [proposta.fattura_id]
      : (proposta.fatture || []).map(f => (typeof f === 'string' ? f : f.fattura_id));
    if (!window.confirm(`Confermi il collegamento di ${assegnoIds.length} assegni a ${fatturaIds.length} fatture?`)) return;
    setAutoAssociating(true);
    try {
      await api.post('/api/assegni/auto-match/conferma', {
        assegno_ids: assegnoIds,
        fattura_ids: fatturaIds,
        livello,
      });
      toast.success('Proposta confermata');
      await loadData();
      await handleAutoMatch();
    } catch (error) {
      toast.error('Conferma non riuscita: ' + (error.response?.data?.detail || error.message));
    } finally {
      setAutoAssociating(false);
    }
  };

  // Carica lista ambigui
  const loadAmbigui = async () => {
    setAmbiguiLoading(true);
    try {
      const res = await api.get('/api/assegni/ambigui');
      setAmbiguiList(res.data?.ambigui || []);
      // default: prima fattura selezionata per ciascuno
      const def = {};
      (res.data?.ambigui || []).forEach(a => {
        def[a.assegno_id] = a.candidates?.[0] ? [a.candidates[0].fattura_id] : [];
      });
      setAmbiguiSelections(def);
    } catch (e) {
      toast.error('Errore caricamento ambigui: ' + (e.response?.data?.detail || e.message));
    } finally {
      setAmbiguiLoading(false);
    }
  };

  const toggleAmbiguiSection = async () => {
    const willOpen = !ambiguiOpen;
    setAmbiguiOpen(willOpen);
    if (willOpen && ambiguiList.length === 0) {
      await loadAmbigui();
    }
  };

  const setAmbiguiSelection = (assegnoId, fatturaId, checked) => {
    setAmbiguiSelections(prev => {
      const cur = prev[assegnoId] || [];
      const next = checked
        ? [...cur.filter(id => id !== fatturaId), fatturaId]
        : cur.filter(id => id !== fatturaId);
      return { ...prev, [assegnoId]: next };
    });
  };

  const resolveAmbiguo = async assegnoId => {
    const fattura_ids = ambiguiSelections[assegnoId] || [];
    if (fattura_ids.length === 0) {
      toast.warning('Seleziona almeno una fattura');
      return;
    }
    setAmbiguiResolving(p => ({ ...p, [assegnoId]: true }));
    try {
      await api.post(`/api/assegni/${assegnoId}/risolvi-ambiguo`, { fattura_ids });
      setAmbiguiList(list => list.filter(a => a.assegno_id !== assegnoId));
      loadData();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setAmbiguiResolving(p => ({ ...p, [assegnoId]: false }));
    }
  };

  // LEARNING MACHINE: Apprende dalle associazioni esistenti
  const handleLearn = async () => {
    setLearningLoading(true);
    setLearningResult(null);
    try {
      const res = await api.post('/api/assegni/learning/learn');
      setLearningResult(res.data);
      // Carica anche le stats aggiornate
      loadStatsAvanzate();
    } catch (error) {
      toast.error('Errore Learning: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLearningLoading(false);
    }
  };

  // LEARNING MACHINE: Associazione Intelligente
  const handleAssociaIntelligente = async () => {
    setAutoAssociating(true);
    setAutoAssocResult(null);
    try {
      const res = await api.post('/api/assegni/learning/associa-intelligente');
      setAutoAssocResult(res.data);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setAutoAssociating(false);
    }
  };

  // PULIZIA DUPLICATI
  const handlePuliziaDuplicati = async (dryRun = true) => {
    setPuliziaLoading(true);
    setPuliziaResult(null);
    try {
      const res = await api.post(`/api/assegni/learning/pulizia-duplicati?dry_run=${dryRun}`);
      setPuliziaResult(res.data);
      if (!dryRun && res.data.record_eliminati > 0) {
        loadData();
      }
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setPuliziaLoading(false);
    }
  };

  // STATS AVANZATE
  const loadStatsAvanzate = async () => {
    try {
      const res = await api.get('/api/assegni/learning/stats-avanzate');
      setStatsAvanzate(res.data);
    } catch (error) {
      console.error('Errore caricamento stats:', error);
    }
  };

  // Carica stats all'avvio
  useEffect(() => {
    loadStatsAvanzate();
  }, []);

  // Nuova funzione: Associazione combinata (somma di più assegni = importo fattura)
  const handleAssociaCombinazioni = async () => {
    setCombinazioneLoading(true);
    setCombinazioneResult(null);
    try {
      const res = await api.post('/api/assegni/cerca-combinazioni-assegni');
      setCombinazioneResult(res.data);
      if (res.data.assegni_associati > 0) {
        loadData();
      }
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setCombinazioneLoading(false);
    }
  };

  // FILTRO ASSEGNI LATO CLIENT
  // useMemo (vincolo ListaAdattiva): la lista resetta la paginazione quando
  // cambia il riferimento di `dati`; senza memo ogni re-render (es. una
  // spunta di selezione) ricreerebbe l'array e riporterebbe la lista a 50 righe.
  const filteredAssegni = useMemo(() => filtraAssegni(assegni, {
    fornitore: filterFornitore,
    importoEsatto: filterImportoEsatto,
    importoMin: filterImportoMin,
    importoMax: filterImportoMax,
    numeroAssegno: filterNumeroAssegno,
    numeroFattura: filterNumeroFattura,
    soloDaAssociare: filterSoloDaAssociare,
  }), [
    assegni,
    filterFornitore,
    filterImportoEsatto,
    filterImportoMin,
    filterImportoMax,
    filterNumeroAssegno,
    filterNumeroFattura,
    filterSoloDaAssociare,
  ]);

  // Reset filtri
  const resetFilters = () => {
    setFilterFornitore('');
    setFilterImportoEsatto('');
    setFilterImportoMin('');
    setFilterImportoMax('');
    setFilterNumeroAssegno('');
    setFilterNumeroFattura('');
    setFilterSoloDaAssociare(false);
  };

  const totaleFattureSelezionate = useMemo(
    () => totaleQuoteFatture(selectedFatture),
    [selectedFatture]
  );
  const differenzaAssegno =
    Number(editingAssegnoForFatture?.importo || 0) - totaleFattureSelezionate;
  const assegnoCoperto = assegnoInteramenteAssociato(
    editingAssegnoForFatture?.importo,
    selectedFatture
  );

  const fattureVisibili = useMemo(() => {
    if (assegnoCoperto) return [];
    const q = filterFatturaModal.trim().toLowerCase();
    if (!q) return fatture.slice(0, 200);
    const qImporto = parseImportoFiltro(q);
    return fatture.filter(f => {
      const testo = [
        f.invoice_number, f.numero_fattura, f.supplier_name,
        f.cedente_denominazione, f.supplier_vat, f.cedente_piva,
      ].filter(Boolean).join(' ').toLowerCase();
      const importo = Number(f.total_amount || f.importo_totale || 0);
      return testo.includes(q) || (qImporto !== null && Math.abs(importo - qImporto) <= 0.01);
    }).slice(0, 200);
  }, [fatture, filterFatturaModal, assegnoCoperto]);

  // Raggruppa assegni per carnet (primi 10 cifre del numero) - usa filteredAssegni
  const groupByCarnet = () => {
    const groups = {};
    filteredAssegni.forEach(a => {
      const prefix = a.numero?.split('-')[0] || 'Senza Carnet';
      if (!groups[prefix]) groups[prefix] = [];
      groups[prefix].push(a);
    });
    return groups;
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const carnets = useMemo(groupByCarnet, [filteredAssegni]);

  // Elenco piatto nell'ordine per carnet: stesse righe, nello stesso ordine,
  // della vecchia tabella desktop che iterava i gruppi carnet.
  const listaAssegni = useMemo(() => Object.values(carnets).flat(), [carnets]);

  // Evidenzia su desktop le righe selezionate, come la vecchia tabella
  const tdSelezione = assegno => {
    if (selectedAssegni.has(assegno.id)) return { background: COLORS.successLight };
    if (newlyGeneratedNumbers.has(assegno.numero)) {
      return { background: COLORS.infoLight, borderTop: `1px solid ${COLORS.info}` };
    }
    return undefined;
  };

  // Apre la fattura collegata nel modale in-page (niente nuove schede)
  const apriFattura = assegno =>
    setFatturaView({
      id: assegno.fattura_collegata || assegno.fatture_collegate?.[0]?.fattura_id,
      numero: assegno.numero_fattura,
    });

  // Genera PDF per un singolo carnet
  const generateCarnetPDF = (carnetId, carnetAssegni) => {
    const doc = new jsPDF();

    // ==========================================
    // INTESTAZIONE AZIENDA (stile Commercialista)
    // ==========================================
    doc.setFontSize(16);
    doc.setTextColor(30, 58, 95);
    doc.setFont(undefined, 'bold');
    doc.text('CERALDI GROUP S.R.L.', 14, 18);

    doc.setFontSize(9);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(80);
    doc.text('Via Roma, 123 - 80100 Napoli (NA)', 14, 24);
    doc.text('P.IVA: 04523831214 - C.F.: 04523831214', 14, 29);

    // Linea separatrice
    doc.setDrawColor(30, 58, 95);
    doc.setLineWidth(0.5);
    doc.line(14, 33, 196, 33);

    // ==========================================
    // TITOLO DOCUMENTO
    // ==========================================
    doc.setFontSize(18);
    doc.setTextColor(30, 58, 95);
    doc.setFont(undefined, 'bold');
    doc.text('CARNET ASSEGNI', 14, 45);

    doc.setFontSize(12);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(80);
    doc.text(`ID Carnet: ${carnetId}`, 14, 52);

    // ==========================================
    // RIEPILOGO
    // ==========================================
    const totale = carnetAssegni.reduce((sum, a) => sum + (parseFloat(a.importo) || 0), 0);
    const assegniCompilati = carnetAssegni.filter(a => a.importo && a.importo > 0).length;

    doc.setFontSize(10);
    doc.setTextColor(60);
    doc.text(`Numero Assegni: ${carnetAssegni.length}`, 14, 62);
    doc.text(`Assegni Compilati: ${assegniCompilati}`, 80, 62);

    doc.setFontSize(12);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(30, 58, 95);
    doc.text(`Totale Importo: ${formatEuro(totale)}`, 140, 62);
    doc.setFont(undefined, 'normal');

    // ==========================================
    // TABELLA ASSEGNI
    // ==========================================
    const tableData = carnetAssegni.map(a => {
      // Estrai data fattura formattata
      let dataFattura = '-';
      if (a.data_fattura) {
        try {
          const d = new Date(a.data_fattura);
          dataFattura = d.toLocaleDateString('it-IT').replaceAll('/', '-');
        } catch {
          dataFattura = formatDateIT(a.data_fattura);
        }
      }

      // Estrai numero fattura dalle fatture collegate o dal campo diretto
      let numFattura = a.numero_fattura || '-';
      if (numFattura === '-' && a.fatture_collegate && a.fatture_collegate.length > 0) {
        numFattura =
          a.fatture_collegate
            .map(f => f.numero)
            .filter(Boolean)
            .join(', ') || '-';
      }

      return [
        a.numero || '-',
        STATI_ASSEGNO[a.stato]?.label || a.stato || '-',
        (a.beneficiario || '-').substring(0, 30),
        formatEuro(a.importo),
        dataFattura,
        numFattura,
        (a.note || '-').substring(0, 25),
      ];
    });

    autoTable(doc, {
      startY: 70,
      head: [
        ['N. Assegno', 'Stato', 'Beneficiario', 'Importo', 'Data Fattura', 'N. Fattura', 'Note'],
      ],
      body: tableData,
      theme: 'striped',
      headStyles: {
        fillColor: [30, 58, 95],
        textColor: 255,
        fontStyle: 'bold',
        fontSize: 9,
      },
      styles: {
        fontSize: 8,
        cellPadding: 3,
      },
      columnStyles: {
        0: { cellWidth: 28 },
        1: { cellWidth: 20 },
        2: { cellWidth: 40 },
        3: { cellWidth: 22, halign: 'right' },
        4: { cellWidth: 22 },
        5: { cellWidth: 25 },
        6: { cellWidth: 30 },
      },
      alternateRowStyles: {
        fillColor: [245, 247, 250],
      },
    });

    // ==========================================
    // FOOTER
    // ==========================================
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(128);
      doc.setDrawColor(200);
      doc.line(14, doc.internal.pageSize.height - 15, 196, doc.internal.pageSize.height - 15);
      doc.text(
        `CERALDI GROUP S.R.L. - Documento generato il ${new Date().toLocaleDateString('it-IT').replaceAll('/', '-')} alle ${new Date().toLocaleTimeString('it-IT')} - Pagina ${i}/${pageCount}`,
        14,
        doc.internal.pageSize.height - 10
      );
    }

    return doc;
  };

  // Stampa singolo carnet;

  // Toggle selezione assegno
  const toggleSelectAssegno = assegnoId => {
    setSelectedAssegni(prev => {
      const newSet = new Set(prev);
      if (newSet.has(assegnoId)) {
        newSet.delete(assegnoId);
      } else {
        newSet.add(assegnoId);
      }
      return newSet;
    });
  };

  // Seleziona/Deseleziona tutti (filtrati)
  const toggleSelectAll = () => {
    if (selectedAssegni.size === filteredAssegni.length) {
      setSelectedAssegni(new Set());
    } else {
      setSelectedAssegni(new Set(filteredAssegni.map(a => a.id)));
    }
  };

  // Genera PDF per assegni selezionati
  const generateSelectedPDF = () => {
    if (selectedAssegni.size === 0) {
      toast.warning('Seleziona almeno un assegno');
      return;
    }

    const selectedList = filteredAssegni.filter(a => selectedAssegni.has(a.id));
    const doc = new jsPDF();

    // ==========================================
    // INTESTAZIONE AZIENDA (stile Commercialista)
    // ==========================================
    doc.setFontSize(16);
    doc.setTextColor(30, 58, 95);
    doc.setFont(undefined, 'bold');
    doc.text('CERALDI GROUP S.R.L.', 14, 18);

    doc.setFontSize(9);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(80);
    doc.text('Via Roma, 123 - 80100 Napoli (NA)', 14, 24);
    doc.text('P.IVA: 04523831214 - C.F.: 04523831214', 14, 29);

    // Linea separatrice
    doc.setDrawColor(30, 58, 95);
    doc.setLineWidth(0.5);
    doc.line(14, 33, 196, 33);

    // ==========================================
    // TITOLO DOCUMENTO
    // ==========================================
    doc.setFontSize(18);
    doc.setTextColor(30, 58, 95);
    doc.setFont(undefined, 'bold');
    doc.text('REPORT ASSEGNI SELEZIONATI', 14, 45);

    doc.setFontSize(12);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(80);
    doc.text(`Data: ${new Date().toLocaleDateString('it-IT').replaceAll('/', '-')}`, 14, 52);

    // ==========================================
    // RIEPILOGO
    // ==========================================
    const totale = selectedList.reduce((sum, a) => sum + (parseFloat(a.importo) || 0), 0);

    doc.setFontSize(10);
    doc.setTextColor(60);
    doc.text(`Numero Assegni: ${selectedList.length}`, 14, 62);

    doc.setFontSize(12);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(30, 58, 95);
    doc.text(`Totale Importo: ${formatEuro(totale)}`, 140, 62);
    doc.setFont(undefined, 'normal');

    // ==========================================
    // TABELLA ASSEGNI
    // ==========================================
    const tableData = selectedList.map(a => {
      // Estrai data fattura formattata
      let dataFattura = '-';
      if (a.data_fattura) {
        try {
          const d = new Date(a.data_fattura);
          dataFattura = d.toLocaleDateString('it-IT').replaceAll('/', '-');
        } catch {
          dataFattura = formatDateIT(a.data_fattura);
        }
      }

      // Estrai numero fattura dalle fatture collegate o dal campo diretto
      let numFattura = a.numero_fattura || '-';
      if (numFattura === '-' && a.fatture_collegate && a.fatture_collegate.length > 0) {
        numFattura =
          a.fatture_collegate
            .map(f => f.numero)
            .filter(Boolean)
            .join(', ') || '-';
      }

      return [
        a.numero || '-',
        STATI_ASSEGNO[a.stato]?.label || a.stato || '-',
        (a.beneficiario || '-').substring(0, 30),
        formatEuro(a.importo),
        dataFattura,
        numFattura,
      ];
    });

    autoTable(doc, {
      startY: 70,
      head: [['N. Assegno', 'Stato', 'Beneficiario', 'Importo', 'Data Fattura', 'N. Fattura']],
      body: tableData,
      theme: 'striped',
      headStyles: {
        fillColor: [30, 58, 95],
        textColor: 255,
        fontStyle: 'bold',
        fontSize: 9,
      },
      styles: {
        fontSize: 9,
        cellPadding: 3,
      },
      columnStyles: {
        0: { cellWidth: 30 },
        1: { cellWidth: 22 },
        2: { cellWidth: 45 },
        3: { cellWidth: 25, halign: 'right' },
        4: { cellWidth: 25 },
        5: { cellWidth: 30 },
      },
      alternateRowStyles: {
        fillColor: [245, 247, 250],
      },
    });

    // ==========================================
    // FOOTER
    // ==========================================
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(128);
      doc.setDrawColor(200);
      doc.line(14, doc.internal.pageSize.height - 15, 196, doc.internal.pageSize.height - 15);
      doc.text(
        `CERALDI GROUP S.R.L. - Documento generato il ${new Date().toLocaleDateString('it-IT').replaceAll('/', '-')} alle ${new Date().toLocaleTimeString('it-IT')} - Pagina ${i}/${pageCount}`,
        14,
        doc.internal.pageSize.height - 10
      );
    }

    doc.save(`Assegni_Selezionati_${new Date().toISOString().slice(0, 10)}.pdf`);

    // Clear selection after print
    setSelectedAssegni(new Set());
  };

  // Stile voce del menu "⚙️ Altro" (pattern dropdown TopNav)
  const menuItemStyle = {
    justifyContent: 'flex-start',
    gap: 8,
    width: '100%',
    padding: '11px 16px',
    minHeight: 44,
    textAlign: 'left',
    fontSize: 13,
    fontWeight: 500,
    color: COLORS.gray[700],
  };

  return (
    <div
      style={{
        maxWidth: 1400,
        margin: '0 auto',
        padding: isMobile ? '12px' : '16px',
        overflowX: 'hidden',
      }}
    >
      {/* Action Bar consolidata: 3 azioni principali + menu "⚙️ Altro" */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 16,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <Button
          variant="success"
          size="lg"
          onClick={() => setShowGenerate(true)}
          data-testid="genera-assegni-btn"
        >
          + Genera Assegni
        </Button>

        {/* Auto-Match rigoroso a 4 livelli (LOGICA_OPERATIVA) */}
        <Button
          variant="success"
          size="lg"
          onClick={() => handleAutoMatch()}
          disabled={autoAssociating}
          data-testid="auto-match-btn"
          title="Auto-match rigoroso: 4 livelli (L1 1→1, L2 N uguali→1, L3 N diversi→1, L4 1→N) con tolleranza ±0,005€"
          style={{ boxShadow: SHADOWS.sm }}
        >
          {autoAssociating ? '🤖 …' : '🤖 Trova proposte'}
        </Button>

        <Button
          variant={showFilters ? 'primary' : 'secondary'}
          size="lg"
          onClick={() => setShowFilters(!showFilters)}
          data-testid="toggle-filters-btn"
        >
          🔍 Filtri{' '}
          {(filterFornitore ||
            filterImportoMin ||
            filterImportoMax ||
            filterNumeroAssegno ||
            filterNumeroFattura) &&
            '●'}
        </Button>

        {/* Menu "⚙️ Altro": tutte le azioni secondarie consolidate qui */}
        <div ref={altroMenuRef} style={{ position: 'relative' }}>
          <Button
            variant={showAltroMenu ? 'primary' : 'secondary'}
            size="lg"
            onClick={() => setShowAltroMenu(v => !v)}
            aria-expanded={showAltroMenu}
            data-testid="altro-menu-btn"
          >
            ⚙️ Altro {showAltroMenu ? '▴' : '▾'}
          </Button>
          {showAltroMenu && (
            <div
              data-testid="altro-menu"
              style={{
                position: 'absolute',
                top: 'calc(100% + 6px)',
                left: 0,
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.lg,
                boxShadow: SHADOWS.xl,
                border: `1px solid ${COLORS.border}`,
                minWidth: 240,
                padding: '6px 0',
                zIndex: 1500,
                maxHeight: '70vh',
                overflowY: 'auto',
              }}
            >
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  handleAutoAssocia();
                }}
                disabled={autoAssociating}
                data-testid="auto-associa-btn"
                style={menuItemStyle}
              >
                🔁 {autoAssociating ? 'Associando...' : 'Auto-Associa'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  handleAutoMatch();
                }}
                disabled={autoAssociating}
                data-testid="auto-match-preview-btn"
                title="Anteprima: mostra cosa collegherebbe senza scrivere sul DB"
                style={menuItemStyle}
              >
                👁️ Anteprima auto-match
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  toggleAmbiguiSection();
                }}
                data-testid="ambigui-toggle-btn"
                style={menuItemStyle}
              >
                ⚠️ {ambiguiOpen ? 'Nascondi ambigui' : 'Risolvi ambigui'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  handleAssociaCombinazioni();
                }}
                disabled={combinazioneLoading}
                data-testid="associa-combinazioni-btn"
                style={menuItemStyle}
              >
                🔗 {combinazioneLoading ? 'Cercando...' : 'Combinazioni'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  generateSelectedPDF();
                }}
                disabled={selectedAssegni.size === 0}
                data-testid="stampa-selezionati-btn"
                style={{
                  ...menuItemStyle,
                  color: selectedAssegni.size === 0 ? COLORS.textSubtle : COLORS.gray[700],
                }}
              >
                🖨️ Stampa Selezionati
                {selectedAssegni.size > 0 ? ` (${selectedAssegni.size})` : ''}
              </Button>
              <div style={{ height: 1, background: COLORS.border, margin: '6px 0' }} />
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  handleLearn();
                }}
                disabled={learningLoading}
                data-testid="learn-btn"
                title="Apprende dai dati esistenti per migliorare le associazioni future"
                style={menuItemStyle}
              >
                🧠 {learningLoading ? 'Learning...' : 'Learn'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  handleAssociaIntelligente();
                }}
                disabled={autoAssociating}
                data-testid="associa-intelligente-btn"
                title="Usa i pattern appresi per associazioni più accurate"
                style={menuItemStyle}
              >
                🤖 Smart
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  handlePuliziaDuplicati(true);
                }}
                disabled={puliziaLoading}
                data-testid="pulizia-duplicati-btn"
                title="Identifica e rimuove duplicati"
                style={menuItemStyle}
              >
                🧹 Pulizia
              </Button>
              <Link
                to="/learning-machine?tab=assegni"
                onClick={() => setShowAltroMenu(false)}
                title="Dashboard Learning Machine completa"
                style={{ ...menuItemStyle, display: 'flex', alignItems: 'center', textDecoration: 'none' }}
              >
                📊 Dashboard Learning
              </Link>
              <div style={{ height: 1, background: COLORS.border, margin: '6px 0' }} />
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAltroMenu(false);
                  handleClearEmpty();
                }}
                data-testid="svuota-btn"
                style={{ ...menuItemStyle, color: COLORS.danger }}
              >
                🗑️ Svuota (assegni vuoti)
              </Button>
            </div>
          )}
        </div>

        {/* Anno: segue sempre il selettore globale in alto (barra di
            navigazione) — prima questa pagina aveva un secondo selettore
            locale ridondante e disallineato, limitato agli "ultimi 5 anni"
            calcolati da new Date() invece degli anni realmente disponibili. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.gray[700] }}>Anno: {anno}</span>
        </div>
      </div>

      {/* Pannello risoluzione ambigui */}
      {ambiguiOpen && (
        <div
          data-testid="ambigui-panel"
          style={{
            marginBottom: 20,
            padding: 16,
            background: COLORS.warningLight,
            border: `1px solid ${COLORS.warning}`,
            borderRadius: BORDER_RADIUS.lg,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 12,
            }}
          >
            <div>
              <strong style={{ color: COLORS.warning, fontSize: 14 }}>
                ⚠ Assegni ambigui — serve la tua decisione
              </strong>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: COLORS.warning }}>
                Per questi assegni l'auto-matcher ha trovato più di una fattura candidata con lo
                stesso importo. Seleziona quale collegare.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadAmbigui}
              disabled={ambiguiLoading}
              style={{ borderColor: COLORS.warning, color: COLORS.warning }}
            >
              {ambiguiLoading ? '⏳ Aggiorno…' : '↻ Ricarica'}
            </Button>
          </div>

          {ambiguiLoading && (
            <div style={{ padding: 12, textAlign: 'center' }}>Caricamento ambigui…</div>
          )}

          {!ambiguiLoading && ambiguiList.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: COLORS.success, fontSize: 14 }}>
              ✅ Nessun assegno ambiguo da risolvere.
            </div>
          )}

          {!ambiguiLoading &&
            ambiguiList.map(a => (
              <div
                key={a.assegno_id}
                data-testid={`ambiguo-${a.assegno_id}`}
                style={{
                  marginTop: 12,
                  padding: 12,
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  border: `1px solid ${COLORS.warningLight}`,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    alignItems: 'flex-start',
                    flexWrap: 'wrap',
                  }}
                >
                  <div style={{ flex: '1 1 280px', minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text }}>
                      [{a.livello}] Assegno n. {a.assegno_numero}
                    </div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                      {a.fornitore_ragione_sociale} — P.IVA {a.fornitore_piva}
                    </div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                      Importo:{' '}
                      <strong style={{ color: COLORS.text }}>€ {a.importo.toFixed(2)}</strong>
                      {a.data_emissione && <> · Emissione: {formatDateIT(a.data_emissione)}</>}
                    </div>
                  </div>
                  <Button
                    variant="success"
                    size="sm"
                    onClick={() => resolveAmbiguo(a.assegno_id)}
                    disabled={ambiguiResolving[a.assegno_id]}
                    data-testid={`risolvi-${a.assegno_id}`}
                  >
                    {ambiguiResolving[a.assegno_id] ? '⏳ …' : '✓ Collega selezionati'}
                  </Button>
                </div>
                {/* Candidate fatture */}
                <div style={{ marginTop: 10, borderTop: `1px dashed ${COLORS.warningLight}`, paddingTop: 10 }}>
                  {(() => {
                    const selezionati = ambiguiSelections[a.assegno_id] || [];
                    if (selezionati.length === 0) return null;
                    const somma = (a.candidates || [])
                      .filter(c => selezionati.includes(c.fattura_id))
                      .reduce((sum, c) => sum + (c.importo_residuo ?? c.importo_totale ?? c.importo ?? 0), 0);
                    const diff = a.importo - somma;
                    return (
                      <div
                        style={{
                          display: 'flex', justifyContent: 'space-between', gap: 8,
                          padding: '6px 8px', marginBottom: 8, borderRadius: BORDER_RADIUS.sm,
                          background: Math.abs(diff) < 1 ? COLORS.successLight : COLORS.warningLight,
                          fontSize: 12, fontWeight: 600,
                        }}
                      >
                        <span>Totale selezionato ({selezionati.length}):</span>
                        <span style={{ fontFamily: 'monospace' }}>
                          € {somma.toFixed(2)} · assegno € {a.importo.toFixed(2)} · diff{' '}
                          <span style={{ color: Math.abs(diff) < 1 ? COLORS.success : COLORS.warning }}>
                            € {diff.toFixed(2)}
                          </span>
                        </span>
                      </div>
                    );
                  })()}
                  {(a.candidates || []).map(c => {
                    const selected = (ambiguiSelections[a.assegno_id] || []).includes(c.fattura_id);
                    return (
                      <label
                        key={c.fattura_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          padding: '6px 8px',
                          background: selected ? COLORS.successLight : 'transparent',
                          borderRadius: BORDER_RADIUS.sm,
                          cursor: 'pointer',
                          gap: 8,
                          fontSize: 12,
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={e =>
                            setAmbiguiSelection(a.assegno_id, c.fattura_id, e.target.checked)
                          }
                        />
                        <span style={{ flex: 1 }}>
                          <strong>{c.numero || c.fattura_id.slice(0, 8)}</strong>
                          {c.data && <span style={{ color: COLORS.textMuted }}> · {formatDateIT(c.data)}</span>}
                          {c.fornitore && (
                            <span style={{ color: COLORS.textMuted }}> · {c.fornitore}</span>
                          )}
                        </span>
                        <span style={{ fontFamily: 'monospace', color: COLORS.text }}>
                          € {(c.importo_residuo ?? c.importo_totale ?? 0).toFixed(2)}
                        </span>
                        {c.fattura_id && (
                          <Button
                            variant="success"
                            size="sm"
                            onClick={e => {
                              e.preventDefault();
                              e.stopPropagation();
                              setFatturaView({ id: c.fattura_id, numero: c.numero });
                            }}
                            style={{ padding: '2px 7px', fontSize: 10 }}
                          >
                            📄 Vedi
                          </Button>
                        )}
                        {c.payment_status === 'partial' && (
                          <Badge variant="info" style={{ padding: '2px 6px' }}>
                            parziale
                          </Badge>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
        </div>
      )}

      {/* STATS AVANZATE */}
      {statsAvanzate && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: isMobile ? 10 : 12,
            marginBottom: 16,
          }}
        >
          <StatCard
            icon="📊"
            label="Health Score"
            value={`${statsAvanzate.health_score}%`}
            accent={
              statsAvanzate.health_score >= 90
                ? 'success'
                : statsAvanzate.health_score >= 70
                  ? 'warning'
                  : 'danger'
            }
          />

          <StatCard
            icon="✅"
            label="Con Beneficiario"
            value={`${statsAvanzate.con_beneficiario}/${statsAvanzate.totale_assegni}`}
            accent="info"
          />

          <StatCard
            icon="📄"
            label="Con Fattura"
            value={`${statsAvanzate.con_fattura}/${statsAvanzate.totale_assegni}`}
            accent="info"
          />

          {statsAvanzate.duplicati > 0 && (
            <StatCard icon="⚠️" label="Duplicati" value={statsAvanzate.duplicati} accent="danger" />
          )}

          {statsAvanzate.senza_beneficiario > 0 && (
            <StatCard
              icon="❓"
              label="Da Associare"
              value={statsAvanzate.senza_beneficiario}
              accent="warning"
              onClick={() => setFilterSoloDaAssociare(v => !v)}
              style={{
                cursor: 'pointer',
                background: filterSoloDaAssociare ? COLORS.warningLight : COLORS.card,
              }}
            />
          )}
          {filterSoloDaAssociare && (
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFilterSoloDaAssociare(false)}
                style={{ borderColor: COLORS.warning, color: COLORS.warning }}
              >
                ✕ Mostra tutti
              </Button>
            </div>
          )}
        </div>
      )}

      {/* RISULTATO LEARNING */}
      {learningResult && (
        <div
          style={{
            marginBottom: 16,
            padding: 15,
            background: COLORS.successLight,
            borderRadius: BORDER_RADIUS.md,
            border: `1px solid ${COLORS.success}`,
          }}
        >
          <div
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
          >
            <div>
              <strong style={{ color: COLORS.success, fontSize: 14 }}>
                🧠 Learning Completato: {learningResult.pattern_appresi} pattern appresi da{' '}
                {learningResult.assegni_analizzati} assegni
              </strong>
              {learningResult.dettagli && learningResult.dettagli.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12 }}>
                  <strong>Top fornitori riconosciuti:</strong>
                  <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
                    {learningResult.dettagli.slice(0, 5).map((d, i) => (
                      <li key={i}>
                        {d.fornitore} ({d.assegni} assegni, {d.range_importi})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <Button
              variant="ghost"
              onClick={() => setLearningResult(null)}
              aria-label="Chiudi"
              style={{ width: 40, height: 40, flexShrink: 0, padding: 0, fontSize: 16 }}
            >
              ✕
            </Button>
          </div>
        </div>
      )}

      {/* RISULTATO PULIZIA */}
      {puliziaResult && (
        <div
          style={{
            marginBottom: 16,
            padding: 15,
            background: puliziaResult.dry_run ? COLORS.warningLight : COLORS.dangerLight,
            borderRadius: BORDER_RADIUS.md,
            border: `1px solid ${puliziaResult.dry_run ? COLORS.warning : COLORS.danger}`,
          }}
        >
          <div
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
          >
            <div>
              <strong
                style={{ color: puliziaResult.dry_run ? COLORS.warning : COLORS.danger, fontSize: 14 }}
              >
                🧹 {puliziaResult.dry_run ? 'PREVIEW Pulizia' : 'Pulizia Completata'}:{' '}
                {puliziaResult.totale_da_eliminare} record da eliminare
              </strong>
              <div style={{ marginTop: 8, fontSize: 13 }}>
                <div>• Record vuoti: {puliziaResult.record_vuoti?.length || 0}</div>
                <div>• Duplicati numero: {puliziaResult.duplicati_numero?.length || 0}</div>
                {!puliziaResult.dry_run && (
                  <div>• Record eliminati: {puliziaResult.record_eliminati}</div>
                )}
              </div>
              {puliziaResult.dry_run && puliziaResult.totale_da_eliminare > 0 && (
                <Button
                  variant="danger"
                  onClick={() => handlePuliziaDuplicati(false)}
                  style={{ marginTop: 10 }}
                >
                  ⚠️ Conferma Eliminazione
                </Button>
              )}
            </div>
            <Button
              variant="ghost"
              onClick={() => setPuliziaResult(null)}
              aria-label="Chiudi"
              style={{ width: 40, height: 40, flexShrink: 0, padding: 0, fontSize: 16 }}
            >
              ✕
            </Button>
          </div>
        </div>
      )}

      {/* PANNELLO FILTRI - FIXED quando aperto */}
      {showFilters && (
        <div
          style={{
            position: 'fixed',
            top: 60,
            left: isMobile ? 12 : 200,
            right: isMobile ? 12 : 20,
            zIndex: 100,
            background: COLORS.bgAlt,
            borderRadius: BORDER_RADIUS.lg,
            padding: '48px 16px 16px',
            border: `1px solid ${COLORS.border}`,
            boxShadow: SHADOWS.xl,
            maxHeight: '80vh',
            overflowY: 'auto',
          }}
        >
          {/* X di chiusura ben tappabile */}
          <Button
            variant="ghost"
            onClick={() => setShowFilters(false)}
            aria-label="Chiudi filtri"
            data-testid="close-filters-btn"
            style={{
              position: 'absolute',
              top: 6,
              right: 6,
              width: 40,
              height: 40,
              padding: 0,
              fontSize: 20,
            }}
          >
            ✕
          </Button>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 12,
            }}
          >
            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                Fornitore/Beneficiario
              </label>
              <Input
                type="text"
                value={filterFornitore}
                onChange={e => setFilterFornitore(e.target.value)}
                placeholder="Cerca fornitore..."
                data-testid="filter-fornitore"
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                Importo esatto (€)
              </label>
              <Input
                type="text"
                inputMode="decimal"
                value={filterImportoEsatto}
                onChange={e => setFilterImportoEsatto(e.target.value)}
                placeholder="es. 1.097,47"
                data-testid="filter-importo-esatto"
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                Importo Min (€)
              </label>
              <Input
                type="number"
                value={filterImportoMin}
                onChange={e => setFilterImportoMin(e.target.value)}
                placeholder="0.00"
                data-testid="filter-importo-min"
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                Importo Max (€)
              </label>
              <Input
                type="number"
                value={filterImportoMax}
                onChange={e => setFilterImportoMax(e.target.value)}
                placeholder="99999"
                data-testid="filter-importo-max"
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                N. Assegno
              </label>
              <Input
                type="text"
                value={filterNumeroAssegno}
                onChange={e => setFilterNumeroAssegno(e.target.value)}
                placeholder="Cerca assegno..."
                data-testid="filter-numero-assegno"
              />
              <div style={{ fontSize: 10, color: COLORS.textSubtle, marginTop: 3 }}>
                Il filtro parte dopo 3 cifre
              </div>
            </div>

            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                N. Fattura
              </label>
              <Input
                type="text"
                value={filterNumeroFattura}
                onChange={e => setFilterNumeroFattura(e.target.value)}
                placeholder="Cerca fattura..."
                data-testid="filter-numero-fattura"
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
              <Button variant="danger" onClick={resetFilters} data-testid="reset-filters-btn">
                Reset
              </Button>
            </div>
          </div>

          {/* Riepilogo filtri attivi */}
          {(filterFornitore ||
            filterImportoEsatto ||
            filterImportoMin ||
            filterImportoMax ||
            filterNumeroAssegno ||
            filterNumeroFattura) && (
            <div style={{ marginTop: 12, fontSize: 13, color: COLORS.primaryLight }}>
              <strong>Risultati:</strong> {filteredAssegni.length} assegni trovati su{' '}
              {assegni.length} totali
            </div>
          )}
        </div>
      )}

      {/* Risultato Auto-Associazione */}
      {autoAssocResult && autoAssocResult._modalita_auto_match && (
        <div
          style={{
            marginBottom: 20,
            padding: 15,
            background: COLORS.successLight,
            borderRadius: BORDER_RADIUS.md,
            border: `1px solid ${COLORS.success}`,
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
            <div style={{ flex: 1 }}>
              <strong style={{ color: COLORS.success, fontSize: 14 }}>
                🤖 Auto-Match {autoAssocResult._dry_run ? '(ANTEPRIMA)' : 'completato'}
              </strong>
              <div
                style={{ marginTop: 8, fontSize: 13, display: 'flex', flexWrap: 'wrap', gap: 12 }}
              >
                <span>
                  📋 Assegni processati: <strong>{autoAssocResult.assegni_processati ?? 0}</strong>
                </span>
                <span>
                  📄 Fatture disponibili:{' '}
                  <strong>{autoAssocResult.fatture_disponibili ?? 0}</strong>
                </span>
                <span>
                  🏦 Prima Nota Banca:{' '}
                  <strong>
                    {autoAssocResult.movimenti_banca_creati > 0
                      ? autoAssocResult.movimenti_banca_creati
                      : 'nessuna — attende estratto conto'}
                  </strong>
                </span>
              </div>
              {autoAssocResult.assegni_vuoti_ignorati > 0 && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: 10,
                      borderRadius: BORDER_RADIUS.sm,
                      background: COLORS.warningLight,
                      color: COLORS.warning,
                      fontSize: 13,
                      fontWeight: 600,
                    }}
                  >
                    {autoAssocResult.assegni_vuoti_ignorati} assegni del carnet sono stati creati
                    correttamente ma, essendo ancora vuoti, non sono inclusi negli assegni
                    processati. Inserisci importo e beneficiario: soltanto dopo potranno generare
                    proposte L1–L4.
                  </div>
                )}
              <div
                style={{ marginTop: 8, fontSize: 13, display: 'flex', flexWrap: 'wrap', gap: 12 }}
              >
                <span style={{ color: COLORS.success }}>
                  ✓ L1 (1=1): <strong>{autoAssocResult.totali?.L1 ?? 0}</strong>
                </span>
                <span style={{ color: COLORS.info }}>
                  ✓ L2 (N uguali→1): <strong>{autoAssocResult.totali?.L2 ?? 0}</strong>
                </span>
                <span style={{ color: COLORS.accent }}>
                  ✓ L3 (N diversi→1): <strong>{autoAssocResult.totali?.L3 ?? 0}</strong>
                </span>
                <span style={{ color: COLORS.warning }}>
                  ✓ L4 (1→N): <strong>{autoAssocResult.totali?.L4 ?? 0}</strong>
                </span>
                <span style={{ color: COLORS.danger }}>
                  ⚠ Ambigui: <strong>{autoAssocResult.totali?.ambigui ?? 0}</strong>
                </span>
                <span style={{ color: COLORS.textMuted }}>
                  ✗ Non trovati: <strong>{autoAssocResult.totali?.non_trovati ?? 0}</strong>
                </span>
              </div>
              {['L1', 'L2', 'L3', 'L4'].flatMap(livello =>
                (autoAssocResult[`match_${livello.toLowerCase()}`] || []).map((proposta, indice) => (
                  <div
                    key={`${livello}-${indice}`}
                    style={{
                      marginTop: 10,
                      padding: 10,
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 12,
                    }}
                  >
                    <span>
                      Proposta <strong>{livello}</strong>: conferma necessaria prima di creare
                      movimenti in Prima Nota.
                    </span>
                    <Button
                      variant="success"
                      size="sm"
                      disabled={autoAssociating}
                      onClick={() => handleConfirmMatch(proposta, livello)}
                    >
                      Conferma proposta
                    </Button>
                  </div>
                ))
              )}
              {/* Dettaglio L2/L3: quali fatture sono state sommate/raggruppate per
                  arrivare al match — prima si vedeva solo il conteggio totale,
                  senza modo di risalire a QUALI fatture componevano la somma. */}
              {autoAssocResult.match_l2?.length > 0 && (
                <details style={{ marginTop: 10, fontSize: 12 }}>
                  <summary style={{ cursor: 'pointer', color: COLORS.info, fontWeight: 600 }}>
                    Vedi dettaglio {autoAssocResult.match_l2.length} match L2 (più assegni
                    uguali → 1 fattura)
                  </summary>
                  <div style={{ margin: '8px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {autoAssocResult.match_l2.map((m, i) => (
                      <div
                        key={i}
                        style={{
                          padding: 8,
                          background: COLORS.card,
                          borderRadius: BORDER_RADIUS.sm,
                          border: `1px solid ${COLORS.border}`,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <span>
                            Fatt. <strong>{m.fattura_numero || m.fattura_id}</strong>
                            {m.fornitore ? ` — ${m.fornitore}` : ''}
                          </span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <strong>{formatEuro(m.fattura_importo || 0)}</strong>
                            {m.fattura_id && (
                              <Button
                                variant="success"
                                size="sm"
                                onClick={() =>
                                  setFatturaView({ id: m.fattura_id, numero: m.fattura_numero })
                                }
                                style={{ padding: '4px 8px', fontSize: 11 }}
                              >
                                📄 Vedi
                              </Button>
                            )}
                          </div>
                        </div>
                        <div style={{ marginTop: 4, paddingLeft: 12, color: COLORS.textMuted }}>
                          {(m.assegni || []).map((a, j) => (
                            <div key={j}>
                              ↳ Assegno {a.assegno_numero || a.assegno_id}: {formatEuro(a.quota || 0)}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              )}
              {autoAssocResult.match_l3?.length > 0 && (
                <details style={{ marginTop: 10, fontSize: 12 }}>
                  <summary style={{ cursor: 'pointer', color: COLORS.accent, fontWeight: 600 }}>
                    Vedi dettaglio {autoAssocResult.match_l3.length} match L3 (più assegni
                    diversi → 1 fattura)
                  </summary>
                  <div style={{ margin: '8px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {autoAssocResult.match_l3.map((m, i) => (
                      <div
                        key={i}
                        style={{
                          padding: 8,
                          background: COLORS.card,
                          borderRadius: BORDER_RADIUS.sm,
                          border: `1px solid ${COLORS.border}`,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <span>
                            Fatt. <strong>{m.fattura_numero || m.fattura_id}</strong>
                            {m.fornitore ? ` — ${m.fornitore}` : ''}
                          </span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <strong>{formatEuro(m.fattura_importo || 0)}</strong>
                            {m.fattura_id && (
                              <Button
                                variant="success"
                                size="sm"
                                onClick={() =>
                                  setFatturaView({ id: m.fattura_id, numero: m.fattura_numero })
                                }
                                style={{ padding: '4px 8px', fontSize: 11 }}
                              >
                                📄 Vedi
                              </Button>
                            )}
                          </div>
                        </div>
                        <div style={{ marginTop: 4, paddingLeft: 12, color: COLORS.textMuted }}>
                          {(m.assegni || []).map((a, j) => (
                            <div key={j}>
                              ↳ Assegno {a.assegno_numero || a.assegno_id}: {formatEuro(a.quota || 0)}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              )}
              {autoAssocResult.ambigui?.length > 0 && (
                <details style={{ marginTop: 10, fontSize: 12 }}>
                  <summary style={{ cursor: 'pointer', color: COLORS.danger, fontWeight: 600 }}>
                    Vedi {autoAssocResult.ambigui.length} assegni ambigui (da confermare
                    manualmente)
                  </summary>
                  <ul style={{ margin: '6px 0', paddingLeft: 18 }}>
                    {autoAssocResult.ambigui.slice(0, 10).map((a, i) => (
                      <li key={i}>
                        [{a.livello}] Assegno {a.assegno_numero} — {a.candidates?.length || 0}{' '}
                        candidate
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
            <Button
              variant="ghost"
              onClick={() => setAutoAssocResult(null)}
              aria-label="Chiudi"
              style={{ width: 40, height: 40, flexShrink: 0, padding: 0, fontSize: 16 }}
            >
              ✕
            </Button>
          </div>
        </div>
      )}

      {/* Risultato Auto-Associazione (legacy) */}
      {autoAssocResult && !autoAssocResult._modalita_auto_match && (
        <div
          style={{
            marginBottom: 20,
            padding: 15,
            background: autoAssocResult.assegni_aggiornati > 0 ? COLORS.successLight : COLORS.warningLight,
            borderRadius: BORDER_RADIUS.md,
            border: `1px solid ${autoAssocResult.assegni_aggiornati > 0 ? COLORS.success : COLORS.warning}`,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <strong
                style={{ color: autoAssocResult.assegni_aggiornati > 0 ? COLORS.success : COLORS.warning }}
              >
                {autoAssocResult.assegni_aggiornati > 0 ? '✓' : '!'} {autoAssocResult.message}
              </strong>
              {autoAssocResult.dettagli && autoAssocResult.dettagli.length > 0 && (
                <div style={{ marginTop: 10, fontSize: 13 }}>
                  <strong>Associazioni effettuate:</strong>
                  <ul style={{ margin: '5px 0', paddingLeft: 20 }}>
                    {autoAssocResult.dettagli.slice(0, 10).map((d, i) => (
                      <li key={i}>
                        Assegno {d.assegno_numero} → Fattura {d.fattura_numero} (
                        {d.fornitore?.substring(0, 30)})
                        {d.tipo === 'multiplo' && (
                          <span style={{ color: COLORS.accent }}> [MULTIPLO]</span>
                        )}
                      </li>
                    ))}
                    {autoAssocResult.dettagli.length > 10 && (
                      <li>...e altri {autoAssocResult.dettagli.length - 10}</li>
                    )}
                  </ul>
                </div>
              )}
            </div>
            <Button
              variant="ghost"
              onClick={() => setAutoAssocResult(null)}
              aria-label="Chiudi"
              style={{ width: 40, height: 40, flexShrink: 0, padding: 0, fontSize: 16 }}
            >
              ✕
            </Button>
          </div>
        </div>
      )}

      {/* Risultato Associazione Combinata */}
      {combinazioneResult && (
        <div
          style={{
            marginBottom: 20,
            padding: 15,
            background: combinazioneResult.match_trovati > 0 ? COLORS.infoLight : COLORS.warningLight,
            borderRadius: BORDER_RADIUS.md,
            border: `1px solid ${combinazioneResult.match_trovati > 0 ? COLORS.info : COLORS.warning}`,
          }}
        >
          <div
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
          >
            <div style={{ flex: 1 }}>
              <strong
                style={{ color: combinazioneResult.match_trovati > 0 ? COLORS.info : COLORS.warning }}
              >
                🔗{' '}
                {combinazioneResult.message ||
                  (combinazioneResult.match_trovati > 0
                    ? `Trovate ${combinazioneResult.match_trovati} combinazioni! (${combinazioneResult.assegni_associati} assegni associati)`
                    : 'Nessuna combinazione trovata')}
              </strong>
              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                Analizzati: {combinazioneResult.assegni_analizzati || 0} assegni • Combinazioni
                testate: {combinazioneResult.combinazioni_testate || 0}
              </div>
              {combinazioneResult.dettagli_match &&
                combinazioneResult.dettagli_match.length > 0 && (
                  <div style={{ marginTop: 10, fontSize: 13 }}>
                    <strong>Combinazioni trovate:</strong>
                    <ul style={{ margin: '5px 0', paddingLeft: 20 }}>
                      {combinazioneResult.dettagli_match.map((d, i) => (
                        <li key={i} style={{ marginBottom: 8 }}>
                          <div>
                            <span style={{ color: COLORS.info, fontWeight: 600 }}>
                              {d.num_assegni} Assegni
                            </span>
                            {' → '}
                            <span style={{ color: COLORS.success, fontWeight: 600 }}>
                              Fattura {d.fattura_numero}
                            </span>
                            {d.fornitore && (
                              <span style={{ color: COLORS.textMuted }}>
                                {' '}
                                ({d.fornitore.substring(0, 25)})
                              </span>
                            )}
                          </div>
                          {/* Struttura per lo stesso fornitore: quali assegni compongono
                              la somma, con il rispettivo importo — prima si vedeva solo
                              la lista dei numeri assegno senza risalire a quanto valeva
                              ciascuno, impossibile verificare la somma a colpo d'occhio. */}
                          {d.assegni?.length > 0 && (
                            <div style={{ fontSize: 11, color: COLORS.gray[600], marginTop: 4, paddingLeft: 10 }}>
                              {d.assegni.map((numAss, j) => (
                                <div key={j}>
                                  ↳ Assegno {numAss}
                                  {d.importi_assegni?.[j] != null
                                    ? `: ${formatEuro(d.importi_assegni[j])}`
                                    : ''}
                                </div>
                              ))}
                            </div>
                          )}
                          <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>
                            Somma: {formatEuro(d.somma_assegni)} = Fattura:{' '}
                            {formatEuro(d.fattura_importo)}
                            {d.differenza !== 0 && (
                              <span style={{ color: COLORS.warning }}>
                                {' '}
                                (diff: {formatEuro(d.differenza)})
                              </span>
                            )}
                            {d.fattura_id && (
                              <Button
                                variant="success"
                                size="sm"
                                onClick={() =>
                                  setFatturaView({ id: d.fattura_id, numero: d.fattura_numero })
                                }
                                style={{ marginLeft: 8, padding: '3px 8px', fontSize: 11 }}
                              >
                                📄 Vedi
                              </Button>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              {combinazioneResult.combinazioni_ambigue &&
                combinazioneResult.combinazioni_ambigue.length > 0 && (
                  <div style={{ marginTop: 10, fontSize: 13 }}>
                    <strong style={{ color: COLORS.warning }}>
                      ⚠️ {combinazioneResult.combinazioni_ambigue.length} combinazioni ambigue (non
                      associate automaticamente):
                    </strong>
                    <ul style={{ margin: '5px 0', paddingLeft: 20 }}>
                      {combinazioneResult.combinazioni_ambigue.map((amb, i) => (
                        <li key={i} style={{ marginBottom: 8, fontSize: 12, color: COLORS.textMuted }}>
                          Assegni {amb.assegni?.join(', ')} (somma {formatEuro(amb.somma_assegni)})
                          corrispondono a più fatture:{' '}
                          {amb.fatture_candidate
                            ?.map(f => `${f.numero} (${f.fornitore || 'N/D'})`)
                            .join(', ')}{' '}
                          — scegli a mano quale associare.
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              {combinazioneResult.assegni_non_associabili &&
                combinazioneResult.assegni_non_associabili.length > 0 && (
                  <div style={{ marginTop: 8, fontSize: 12, color: COLORS.warning }}>
                    ⚠️ {combinazioneResult.assegni_non_associabili.length} assegni rimasti senza
                    corrispondenza
                  </div>
                )}
            </div>
            <Button
              variant="ghost"
              onClick={() => setCombinazioneResult(null)}
              aria-label="Chiudi"
              style={{ width: 40, height: 40, flexShrink: 0, marginLeft: 10, padding: 0, fontSize: 16 }}
            >
              ✕
            </Button>
          </div>
        </div>
      )}

      {/* SEZIONE ASSEGNI NON ASSOCIATI */}
      <div
        style={{
          background: COLORS.card,
          borderRadius: BORDER_RADIUS.lg,
          padding: 16,
          marginBottom: 16,
          boxShadow: SHADOWS.md,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            cursor: 'pointer',
          }}
          onClick={() => {
            if (!showNonAssociati && assegniNonAssociati.totale === undefined) {
              loadAssegniNonAssociati();
            }
            setShowNonAssociati(!showNonAssociati);
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: 16,
              color: COLORS.text,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            ⚠️ Assegni Senza Beneficiario
            {assegniNonAssociati.totale !== undefined && (
              <Badge variant={assegniNonAssociati.totale > 0 ? 'warning' : 'success'}>
                {assegniNonAssociati.totale}
              </Badge>
            )}
          </h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Button
              variant="secondary"
              size="sm"
              onClick={e => {
                e.stopPropagation();
                loadAssegniNonAssociati();
              }}
              disabled={loadingNonAssociati}
            >
              {loadingNonAssociati ? '⏳' : '🔄'} Aggiorna
            </Button>
            <span style={{ fontSize: 18 }}>{showNonAssociati ? '▲' : '▼'}</span>
          </div>
        </div>

        {showNonAssociati && (
          <div style={{ marginTop: 16 }}>
            {loadingNonAssociati ? (
              <div style={{ textAlign: 'center', padding: 20, color: COLORS.textMuted }}>
                ⏳ Caricamento...
              </div>
            ) : assegniNonAssociati.totale === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: 20,
                  background: COLORS.successLight,
                  borderRadius: BORDER_RADIUS.md,
                  color: COLORS.success,
                }}
              >
                ✅ Tutti gli assegni sono stati associati!
              </div>
            ) : (
              <div>
                <p style={{ margin: '0 0 12px', fontSize: 13, color: COLORS.textMuted }}>
                  Questi assegni hanno un importo ma nessun beneficiario. Clicca "Associa" per
                  collegare manualmente a una fattura.
                </p>
                <TableWrap>
                  <Table>
                    <thead>
                      <tr>
                        <Th>Importo</Th>
                        <Th>Numero Assegno</Th>
                        <Th align="center">Azioni</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(assegniNonAssociati.per_importo || {}).map(
                        ([importo, info]) =>
                          info.numeri.map((numero, idx) => (
                            <tr key={numero}>
                              <Td style={{ fontWeight: 600 }}>{importo}</Td>
                              <Td mono>{numero}</Td>
                              <Td align="center">
                                <Button
                                  variant="info"
                                  size="sm"
                                  onClick={() => {
                                    const assegnoData = assegni.find(a => a.numero === numero);
                                    if (assegnoData) {
                                      openFattureModal(assegnoData);
                                    } else {
                                      toast.warning(
                                        `Assegno ${numero} non trovato nella lista. Prova a rimuovere i filtri.`
                                      );
                                    }
                                  }}
                                >
                                  🔗 Associa Fattura
                                </Button>
                              </Td>
                            </tr>
                          ))
                      )}
                    </tbody>
                  </Table>
                </TableWrap>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Assegni Table/Cards */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>Caricamento...</div>
      ) : filteredAssegni.length === 0 ? (
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.lg,
            padding: 60,
            textAlign: 'center',
            boxShadow: SHADOWS.md,
          }}
        >
          <h3 style={{ color: COLORS.textMuted, marginBottom: 10 }}>
            {assegni.length === 0
              ? 'Nessun assegno presente'
              : 'Nessun assegno corrisponde ai filtri'}
          </h3>
          <p style={{ color: COLORS.textSubtle }}>
            {assegni.length === 0
              ? 'Genera i primi assegni per iniziare'
              : 'Prova a modificare i filtri di ricerca'}
          </p>
        </div>
      ) : (
        // Contenitore-card solo su desktop: su mobile le card di ListaAdattiva
        // hanno già sfondo e bordo propri
        <div
          style={
            isMobile
              ? undefined
              : {
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.lg,
                  overflow: 'hidden',
                  boxShadow: SHADOWS.md,
                }
          }
        >
          <div
            style={{
              padding: isMobile ? '12px 0' : 16,
              borderBottom: `1px solid ${COLORS.border}`,
              marginBottom: isMobile ? 12 : 0,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0, fontSize: isMobile ? 16 : undefined }}>
                Lista Assegni ({filteredAssegni.length})
              </h3>
              {newlyGeneratedNumbers.size > 0 && (
                <Badge variant="info">Nuovo carnet: {newlyGeneratedNumbers.size} fogli</Badge>
              )}
            </div>
          </div>
          <ListaAdattiva
            testId="assegni-table"
            dati={listaAssegni}
            pageSize={50}
            chiave={(a, i) => a.id || i}
            colonne={[
              {
                // Selezione: colonna solo desktop; su mobile la spunta
                // sta tra le azioni della card
                key: 'sel',
                ruoloCard: 'omesso',
                align: 'center',
                tdStyle: tdSelezione,
                label: (
                  <input
                    type="checkbox"
                    checked={
                      selectedAssegni.size === filteredAssegni.length &&
                      filteredAssegni.length > 0
                    }
                    onChange={toggleSelectAll}
                    data-testid="select-all-checkbox"
                    style={{ width: 18, height: 18, cursor: 'pointer' }}
                    title="Seleziona tutti"
                  />
                ),
                render: assegno => (
                  <input
                    type="checkbox"
                    checked={selectedAssegni.has(assegno.id)}
                    onChange={() => toggleSelectAssegno(assegno.id)}
                    data-testid={`select-${assegno.id}`}
                    style={{ width: 18, height: 18, cursor: 'pointer' }}
                  />
                ),
              },
              {
                key: 'numero',
                label: 'N. Assegno',
                ruoloCard: 'dettaglio',
                iconaCard: '🔢',
                tdStyle: tdSelezione,
                render: assegno => (
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontWeight: 'bold',
                      color: COLORS.primaryLight,
                      fontSize: 13,
                    }}
                  >
                    {/* Su mobile solo il progressivo: il prefisso carnet
                        è identico su tutto il blocchetto */}
                    {isMobile ? assegno.numero?.split('-')[1] || assegno.numero : assegno.numero}
                  </span>
                ),
              },
              {
                key: 'stato',
                label: 'Stato',
                align: 'center',
                ruoloCard: 'dettaglio',
                tdStyle: tdSelezione,
                render: assegno => (
                  <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Badge variant={STATI_ASSEGNO[assegno.stato]?.variant || 'neutral'}>
                      {STATI_ASSEGNO[assegno.stato]?.label || assegno.stato}
                    </Badge>
                    {newlyGeneratedNumbers.has(assegno.numero) && <Badge variant="info">Nuovo</Badge>}
                  </span>
                ),
              },
              {
                key: 'beneficiario',
                label: 'Beneficiario / Note',
                ruoloCard: 'titolo',
                tdStyle: assegno => ({ maxWidth: 250, ...(tdSelezione(assegno) || {}) }),
                render: assegno =>
                  editingId === assegno.id ? (
                    <Input
                      type="text"
                      value={editForm.beneficiario}
                      onChange={e => setEditForm({ ...editForm, beneficiario: e.target.value })}
                      placeholder="Beneficiario"
                      style={{ padding: 6, fontSize: 12 }}
                    />
                  ) : (
                    <div>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>
                        {assegno.beneficiario ? (
                          assegno.beneficiario
                        ) : assegno.fornitore_fattura ? (
                          <span
                            style={{ fontStyle: 'italic', color: COLORS.textMuted }}
                            title="Fornitore dedotto dalla fattura collegata"
                          >
                            → {assegno.fornitore_fattura}
                          </span>
                        ) : (
                          '-'
                        )}
                      </div>
                      {assegno.note && (
                        <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>
                          {assegno.note}
                        </div>
                      )}
                    </div>
                  ),
              },
              {
                key: 'importo',
                label: 'Importo',
                align: 'right',
                ruoloCard: 'importo',
                tdStyle: tdSelezione,
                render: assegno =>
                  editingId === assegno.id ? (
                    <Input
                      type="number"
                      step="0.01"
                      value={editForm.importo}
                      onChange={e =>
                        setEditForm({ ...editForm, importo: parseFloat(e.target.value) || '' })
                      }
                      placeholder="0.00"
                      style={{ padding: 6, width: 80, textAlign: 'right', fontSize: 12 }}
                    />
                  ) : (
                    <span style={{ fontWeight: 'bold', fontSize: 13 }}>
                      {formatEuro(assegno.importo)}
                    </span>
                  ),
              },
              {
                key: 'fattura',
                label: 'Fattura / Data',
                ruoloCard: 'dettaglio',
                iconaCard: '📄',
                tdStyle: tdSelezione,
                render: assegno =>
                  editingId === assegno.id ? (
                    <div style={{ display: 'flex', gap: 4 }}>
                      <Input
                        type="date"
                        value={editForm.data_fattura}
                        onChange={e => setEditForm({ ...editForm, data_fattura: e.target.value })}
                        style={{ padding: 4, fontSize: 11, width: 110 }}
                      />
                      <Input
                        type="text"
                        value={editForm.numero_fattura}
                        onChange={e =>
                          setEditForm({ ...editForm, numero_fattura: e.target.value })
                        }
                        placeholder="N.Fatt"
                        style={{ padding: 4, fontSize: 11, width: 80 }}
                      />
                    </div>
                  ) : isMobile ? (
                    assegno.numero_fattura || assegno.data_fattura ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        {assegno.numero_fattura && (
                          <span style={{ color: COLORS.info }}>
                            Fatt. {assegno.numero_fattura}
                          </span>
                        )}
                        {/* Su mobile solo GG/MM: l'anno è nel selettore globale */}
                        {assegno.data_fattura && (
                          <span style={{ color: COLORS.textMuted, fontSize: 11 }}>
                            ({formatDateGGMM(assegno.data_fattura)})
                          </span>
                        )}
                        {(assegno.fattura_collegata ||
                          assegno.fatture_collegate?.[0]?.fattura_id) && (
                          <Button
                            variant="success"
                            size="sm"
                            onClick={() => apriFattura(assegno)}
                            title="Visualizza Fattura"
                            data-testid={`view-fattura-${assegno.id}`}
                          >
                            📄 Vedi
                          </Button>
                        )}
                      </span>
                    ) : (
                      '-'
                    )
                  ) : (
                    <div style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                      {/* Pulsante per visualizzare fattura in modale in-page */}
                      {(assegno.fattura_collegata ||
                        assegno.fatture_collegate?.[0]?.fattura_id) && (
                        <Button
                          variant="success"
                          size="sm"
                          onClick={e => {
                            e.stopPropagation();
                            apriFattura(assegno);
                          }}
                          title="Visualizza Fattura"
                          data-testid={`view-fattura-${assegno.id}`}
                        >
                          📄 Vedi
                        </Button>
                      )}
                      {/* Info fattura */}
                      <div>
                        {assegno.numero_fattura && (
                          <div style={{ color: COLORS.info }}>
                            Fatt. {assegno.numero_fattura}
                          </div>
                        )}
                        {assegno.data_fattura && (
                          <div style={{ color: COLORS.textMuted, fontSize: 11 }}>
                            {formatDateIT(assegno.data_fattura)}
                          </div>
                        )}
                      </div>
                    </div>
                  ),
              },
              {
                key: 'azioni',
                label: 'Azioni',
                align: 'center',
                ruoloCard: 'azioni',
                tdStyle: tdSelezione,
                render: assegno => (
                  <RowActions style={{ justifyContent: isMobile ? 'flex-end' : 'center' }}>
                    {isMobile && (
                      <input
                        type="checkbox"
                        checked={selectedAssegni.has(assegno.id)}
                        onChange={() => toggleSelectAssegno(assegno.id)}
                        data-testid={`select-${assegno.id}`}
                        style={{ width: 18, height: 18, cursor: 'pointer' }}
                      />
                    )}
                    {editingId === assegno.id ? (
                      <>
                        <RowActionButton
                          variant="success"
                          onClick={handleSaveEdit}
                          style={{ width: 28, height: 28 }}
                          title="Salva"
                        >
                          ✓
                        </RowActionButton>
                        <RowActionButton
                          variant="danger"
                          onClick={cancelEdit}
                          style={{ width: 28, height: 28 }}
                          title="Annulla"
                        >
                          ✕
                        </RowActionButton>
                      </>
                    ) : (
                      <>
                        <RowActionButton
                          variant="neutral"
                          onClick={() => startEdit(assegno)}
                          data-testid={`edit-${assegno.id}`}
                          title="Modifica"
                        >
                          ✏️
                        </RowActionButton>
                        <RowActionButton
                          variant="neutral"
                          onClick={() => openFattureModal(assegno)}
                          data-testid={`fatture-${assegno.id}`}
                          title="Collega Fatture"
                        >
                          📄
                        </RowActionButton>
                        {/* STAMPA singolo assegno: il carnet è il prefisso
                            del numero, come in groupByCarnet */}
                        <RowActionButton
                          variant="info"
                          onClick={() => {
                            const doc = generateCarnetPDF(
                              assegno.numero?.split('-')[0] || 'Senza Carnet',
                              [assegno]
                            );
                            doc.save(`Assegno_${assegno.numero}.pdf`);
                          }}
                          data-testid={`print-${assegno.id}`}
                          title="Stampa"
                        >
                          🖨️
                        </RowActionButton>
                        <RowActionButton
                          variant="danger"
                          onClick={() => handleDelete(assegno)}
                          data-testid={`delete-${assegno.id}`}
                          title="Elimina"
                        >
                          🗑️
                        </RowActionButton>
                      </>
                    )}
                  </RowActions>
                ),
              },
            ]}
          />
        </div>
      )}
      {/* Generate Modal */}
      {showGenerate && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,39,68,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowGenerate(false)}
        >
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              padding: 24,
              maxWidth: 400,
              width: '90%',
              boxShadow: SHADOWS.modal,
            }}
            onClick={e => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: 8,
              }}
            >
              <h2 style={{ marginTop: 0 }}>Genera 10 Assegni Progressivi</h2>
              <Button
                variant="ghost"
                onClick={() => setShowGenerate(false)}
                aria-label="Chiudi"
                data-testid="close-generate-btn"
                style={{ width: 40, height: 40, flexShrink: 0, padding: 0, fontSize: 18, background: COLORS.bgAlt, color: COLORS.gray[700] }}
              >
                ✕
              </Button>
            </div>
            <p style={{ color: COLORS.textMuted, fontSize: 14, marginBottom: 20 }}>
              Inserisci il numero del primo assegno nel formato PREFISSO-NUMERO
            </p>

            <div style={{ marginBottom: 15 }}>
              <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold' }}>
                Numero Primo Assegno
              </label>
              <Input
                type="text"
                value={generateForm.numero_primo}
                onChange={e => setGenerateForm({ ...generateForm, numero_primo: e.target.value })}
                placeholder="0208769182-11"
                data-testid="numero-primo-input"
                style={{ padding: 12, fontFamily: 'monospace' }}
              />
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Button variant="secondary" onClick={() => setShowGenerate(false)}>
                Annulla
              </Button>
              <Button
                variant="success"
                onClick={handleGenerate}
                disabled={generating}
                data-testid="genera-salva-btn"
              >
                {generating ? 'Generazione...' : 'Genera e Salva'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Collega Fatture - DRAGGABLE */}
      {showFattureModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,39,68,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowFattureModal(false)}
        >
          <div
            style={{
              position: 'absolute',
              left: modalPosition.x || '50%',
              top: modalPosition.y || '50%',
              transform: modalPosition.x ? 'none' : 'translate(-50%, -50%)',
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              padding: 0,
              maxWidth: 560,
              width: '95%',
              maxHeight: '85vh',
              overflow: 'hidden',
              boxShadow: SHADOWS.modal,
              cursor: isDragging ? 'grabbing' : 'default',
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header Draggable */}
            <div
              style={{
                padding: '10px 10px 10px 16px',
                background: COLORS.primary,
                color: 'white',
                cursor: 'grab',
                userSelect: 'none',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
              onMouseDown={e => {
                setIsDragging(true);
                const rect = e.currentTarget.parentElement.getBoundingClientRect();
                setDragOffset({ x: e.clientX - rect.left, y: e.clientY - rect.top });
              }}
              onMouseMove={e => {
                if (isDragging) {
                  setModalPosition({
                    x: e.clientX - dragOffset.x,
                    y: e.clientY - dragOffset.y,
                  });
                }
              }}
              onMouseUp={() => setIsDragging(false)}
              onMouseLeave={() => setIsDragging(false)}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: 16 }}>📄 Collega Fatture all'Assegno</h2>
                <p style={{ margin: '2px 0 0', fontSize: 11, opacity: 0.8 }}>
                  Trascina per spostare
                </p>
              </div>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowFattureModal(false);
                  setSelectedFatture([]);
                  setModalPosition({ x: 0, y: 0 });
                }}
                aria-label="Chiudi"
                data-testid="close-fatture-modal-btn"
                onMouseDown={e => e.stopPropagation()}
                style={{
                  background: 'rgba(255,255,255,0.2)',
                  color: 'white',
                  width: 40,
                  height: 40,
                  flexShrink: 0,
                  padding: 0,
                  fontSize: 20,
                  lineHeight: 1,
                }}
              >
                ✕
              </Button>
            </div>

            {/* Content */}
            <div style={{ padding: 16, maxHeight: 'calc(85vh - 100px)', overflowY: 'auto' }}>
              {/* Info Assegno con Importo */}
              <div
                style={{
                  background: COLORS.bgAlt,
                  padding: 12,
                  borderRadius: BORDER_RADIUS.md,
                  marginBottom: 12,
                  border: `1px solid ${COLORS.border}`,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 4 }}>
                      Assegno N.
                    </div>
                    <div
                      style={{
                        fontSize: 16,
                        fontWeight: 'bold',
                        color: COLORS.text,
                        fontFamily: 'monospace',
                      }}
                    >
                      {editingAssegnoForFatture?.numero}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 4 }}>
                      Importo Assegno
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 'bold', color: COLORS.primaryLight }}>
                      {formatEuro(editingAssegnoForFatture?.importo || 0)}
                    </div>
                  </div>
                </div>
                <p
                  style={{
                    color: COLORS.info,
                    fontSize: 12,
                    margin: '12px 0 0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  {assegnoCoperto ? (
                    <>✓ Importo completamente coperto dalla fattura collegata</>
                  ) : (
                    <>ℹ️ Collega più fatture solo quando la loro somma coincide con l’assegno</>
                  )}
                </p>
              </div>

              {/* Fatture Selezionate */}
              {selectedFatture.length > 0 && (
                <div
                  style={{
                    background: COLORS.successLight,
                    padding: 12,
                    borderRadius: BORDER_RADIUS.md,
                    marginBottom: 12,
                    border: `1px solid ${COLORS.success}`,
                  }}
                >
                  <strong style={{ color: COLORS.success }}>
                    ✓ Fatture collegate: {selectedFatture.length}
                  </strong>
                  <div style={{ marginTop: 10 }}>
                    {selectedFatture.map(f => (
                      <div
                        key={f.id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '8px 0',
                          borderBottom: `1px solid ${COLORS.successLight}`,
                        }}
                      >
                        <span
                          style={{
                            color: f.is_nota_credito ? COLORS.danger : COLORS.success,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                          }}
                        >
                          {f.numero} - {f.fornitore}
                          {f.is_nota_credito && <Badge variant="danger" style={{ fontSize: 9, padding: '1px 5px' }}>NC</Badge>}
                        </span>
                        <span
                          style={{
                            fontWeight: 'bold',
                            color: f.is_nota_credito ? COLORS.danger : COLORS.success,
                          }}
                        >
                          {f.is_nota_credito ? '- ' : ''}
                          {formatEuro(Math.abs(f.importo))}
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          aria-label={`Rimuovi fattura ${f.numero}`}
                          onClick={() => setSelectedFatture(selectedFatture.filter(sf => sf.id !== f.id))}
                        >
                          ×
                        </Button>
                      </div>
                    ))}
                    <div
                      style={{
                        marginTop: 12,
                        paddingTop: 12,
                        borderTop: `2px solid ${COLORS.success}`,
                        display: 'flex',
                        justifyContent: 'space-between',
                        fontWeight: 'bold',
                        fontSize: 16,
                      }}
                    >
                      <span>TOTALE FATTURE:</span>
                      <span style={{ color: COLORS.success }}>
                        {formatEuro(totaleFattureSelezionate)}
                      </span>
                    </div>
                    {/* Differenza con importo assegno */}
                    {editingAssegnoForFatture?.importo > 0 && (
                      <div
                        style={{
                          marginTop: 8,
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontSize: 13,
                          color:
                            Math.abs(differenzaAssegno) <= TOLLERANZA_ASSEGNO
                              ? COLORS.success
                              : COLORS.warning,
                        }}
                      >
                        <span>Differenza:</span>
                        <span style={{ fontWeight: 600 }}>
                          {formatEuro(
                            differenzaAssegno
                          )}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Lista Fatture Disponibili */}
              {assegnoCoperto && (
                <div
                  data-testid="assegno-coperto-message"
                  style={{
                    marginBottom: 15,
                    padding: 14,
                    color: COLORS.success,
                    background: COLORS.successLight,
                    border: `1px solid ${COLORS.success}`,
                    borderRadius: BORDER_RADIUS.md,
                    fontWeight: 600,
                  }}
                >
                  ✓ Associazione completa. Non occorre aggiungere altre fatture.
                </div>
              )}
              <div style={{ marginBottom: 15, display: assegnoCoperto ? 'none' : 'block' }}>
                <label
                  style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: COLORS.gray[700] }}
                >
                  Fatture disponibili (l'assegno prevale sul metodo fornitore)
                </label>
                <Input
                  type="text"
                  value={filterFatturaModal}
                  onChange={e => setFilterFatturaModal(e.target.value)}
                  placeholder="Cerca numero, fornitore, P.IVA o importo..."
                  aria-label="Cerca fattura da associare"
                  style={{ marginBottom: 8 }}
                />

                {loadingFatture ? (
                  <div style={{ padding: 30, textAlign: 'center', color: COLORS.textMuted }}>
                    ⏳ Caricamento...
                  </div>
                ) : fattureVisibili.length === 0 ? (
                  <div
                    style={{
                      padding: 30,
                      textAlign: 'center',
                      color: COLORS.textMuted,
                      background: COLORS.bgAlt,
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    Nessuna fattura disponibile per assegno
                  </div>
                ) : (
                  <div
                    style={{
                      maxHeight: 270,
                      overflow: 'auto',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    {fattureVisibili.map((f, idx) => {
                      const isSelected = selectedFatture.find(sf => sf.id === f.id);
                      const fornitore = f.supplier_name || f.cedente_denominazione || 'N/A';
                      const tipoDoc = f.tipo_documento || f.document_type || 'TD01';
                      const isNotaCredito = tipoDoc === 'TD04';
                      const importoRaw = parseFloat(f.total_amount || f.importo_totale || 0);
                      // Note credito: importo SEMPRE negativo
                      const importo = isNotaCredito ? -Math.abs(importoRaw) : importoRaw;
                      const residuo = residuoFattura(f);

                      // Mostra header fornitore quando cambia
                      const prevFornitore =
                        idx > 0
                          ? fattureVisibili[idx - 1].supplier_name ||
                            fattureVisibili[idx - 1].cedente_denominazione ||
                            ''
                          : '';
                      const showFornitoreHeader =
                        fornitore.toLowerCase() !== prevFornitore.toLowerCase();

                      return (
                        <React.Fragment key={f.id}>
                          {showFornitoreHeader && (
                            <div
                              style={{
                                padding: '8px 14px',
                                background: COLORS.bgAlt,
                                borderBottom: `1px solid ${COLORS.border}`,
                                fontSize: 11,
                                fontWeight: 700,
                                color: COLORS.gray[600],
                                textTransform: 'uppercase',
                                letterSpacing: '0.03em',
                                position: 'sticky',
                                top: 0,
                                zIndex: 1,
                              }}
                            >
                              🏢 {fornitore}
                            </div>
                          )}
                          <div
                            onClick={() =>
                              toggleFattura({
                                ...f,
                                importo_display: importo,
                                importo: importo,
                                fornitore: fornitore,
                              })
                            }
                            style={{
                              padding: '10px 12px',
                              borderBottom: `1px solid ${COLORS.bgAlt}`,
                              cursor: 'pointer',
                              background: isSelected
                                ? COLORS.infoLight
                                : isNotaCredito
                                  ? COLORS.dangerLight
                                  : COLORS.card,
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              transition: 'background 0.15s',
                              borderLeft: isNotaCredito
                                ? `3px solid ${COLORS.danger}`
                                : '3px solid transparent',
                            }}
                          >
                            <div>
                              <div
                                style={{
                                  fontWeight: 600,
                                  color: isSelected
                                    ? COLORS.info
                                    : isNotaCredito
                                      ? COLORS.danger
                                      : COLORS.text,
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 6,
                                }}
                              >
                                {isSelected ? '✓ ' : '○ '}
                                {f.invoice_number || f.numero_fattura || 'N/A'}
                                {isNotaCredito && (
                                  <Badge variant="danger" style={{ fontSize: 9, padding: '2px 6px' }}>
                                    Nota Credito
                                  </Badge>
                                )}
                              </div>
                              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                                {fornitore} • {formatDateIT(f.invoice_date || f.data_fattura)}
                              </div>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div
                                style={{
                                  fontWeight: 'bold',
                                  color: isNotaCredito ? COLORS.danger : COLORS.primaryLight,
                                  fontSize: 15,
                                }}
                              >
                                {isNotaCredito ? '- ' : ''}
                                {formatEuro(Math.abs(importo))}
                                {!isNotaCredito && Math.abs(residuo - importoRaw) > 0.005 && (
                                  <div style={{ fontSize: 10, color: COLORS.textMuted, fontWeight: 500 }}>
                                    residuo {formatEuro(residuo)}
                                  </div>
                                )}
                              </div>
                              <Button
                                variant="success"
                                size="sm"
                                onClick={e => {
                                  e.stopPropagation();
                                  setFatturaView({
                                    id: f.id,
                                    numero: f.invoice_number || f.numero_fattura,
                                  });
                                }}
                                style={{ padding: '3px 7px', fontSize: 10, flexShrink: 0 }}
                              >
                                📄 Vedi
                              </Button>
                            </div>
                          </div>
                        </React.Fragment>
                      );
                    })}
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 8 }}>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setShowFattureModal(false);
                    setSelectedFatture([]);
                    setFilterFatturaModal('');
                    setModalPosition({ x: 0, y: 0 });
                  }}
                >
                  Annulla
                </Button>
                <Button
                  variant="success"
                  onClick={saveFattureCollegate}
                  disabled={selectedFatture.length === 0 && !(editingAssegnoForFatture?.fatture_collegate || []).length}
                  data-testid="salva-fatture-btn"
                >
                  ✓ Salva {selectedFatture.length} fattur
                  {selectedFatture.length === 1 ? 'a' : 'e'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modale visualizzazione fattura in-page (niente nuove schede del browser) */}
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
