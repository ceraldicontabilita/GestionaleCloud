import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

const STATI_ASSEGNO = {
  vuoto: { label: 'Valido', color: '#4caf50' },
  compilato: { label: 'Compilato', color: '#2196f3' },
  emesso: { label: 'Emesso', color: '#ff9800' },
  incassato: { label: 'Incassato', color: '#9c27b0' },
  annullato: { label: 'Annullato', color: '#f44336' },
};

export default function GestioneAssegni() {
  const { anno } = useAnnoGlobale();
  const [assegni, setAssegni] = useState([]);
  const [_stats, setStats] = useState({ totale: 0, per_stato: {} });
  const [loading, setLoading] = useState(true);
  const [filterStato, _setFilterStato] = useState('');
  const [search, _setSearch] = useState('');

  // NUOVI FILTRI
  const [filterFornitore, setFilterFornitore] = useState('');
  const [filterImportoMin, setFilterImportoMin] = useState('');
  const [filterImportoMax, setFilterImportoMax] = useState('');
  const [filterNumeroAssegno, setFilterNumeroAssegno] = useState('');
  const [filterNumeroFattura, setFilterNumeroFattura] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [filterAnno, setFilterAnno] = useState(anno); // Filtro anno - inizia da anno globale

  // Generate modal
  const [showGenerate, setShowGenerate] = useState(false);
  const [generateForm, setGenerateForm] = useState({ numero_primo: '', quantita: 10 });
  const [generating, setGenerating] = useState(false);

  // Edit inline
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  // Fatture per collegamento
  const [fatture, setFatture] = useState([]);
  const [loadingFatture, setLoadingFatture] = useState(false);
  const [selectedFatture, setSelectedFatture] = useState([]);
  const [showFattureModal, setShowFattureModal] = useState(false);
  const [editingAssegnoForFatture, setEditingAssegnoForFatture] = useState(null);

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
  }, [filterStato, search, filterAnno, anno]);

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
      if (filterAnno) params.append('anno', filterAnno);

      const [assegniRes, statsRes] = await Promise.all([
        api.get(`/api/assegni?${params}`),
        api.get(`/api/assegni/stats?anno=${filterAnno || anno}`),
      ]);

      // Ordina per numero assegno decrescente (dal più recente al più vecchio)
      const assegniOrdinati = (assegniRes.data || []).sort((a, b) => {
        const numA = parseInt(a.numero_assegno?.replace(/\D/g, '') || '0');
        const numB = parseInt(b.numero_assegno?.replace(/\D/g, '') || '0');
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
  const loadFatture = async (beneficiario = '') => {
    setLoadingFatture(true);
    try {
      const params = new URLSearchParams();
      params.append('status', 'imported');
      // IMPORTANTE: se c'è un beneficiario, filtra SOLO quelle del beneficiario
      if (beneficiario) {
        params.append('fornitore', beneficiario);
      }
      const res = await api.get(`/api/invoices?${params}&limit=200`);
      const items = res.data.items || res.data || [];
      // Escludi fatture già pagate E fornitori pagati per contanti
      let filtered = items.filter(f => {
        if (f.status === 'paid') return false;
        // Escludi se il metodo di pagamento è contanti
        const paymentMethod = (f.payment_method || f.metodo_pagamento || '').toLowerCase();
        if (
          paymentMethod.includes('contant') ||
          paymentMethod.includes('cash') ||
          paymentMethod === 'contanti'
        ) {
          return false;
        }
        return true;
      });

      // FILTRO AGGIUNTIVO: Se c'è un beneficiario, mostra SOLO fatture di quel fornitore
      // Questo perché non si può pagare con un assegno fatture di fornitori diversi
      if (beneficiario) {
        const benefLower = beneficiario.toLowerCase();
        filtered = filtered.filter(f => {
          const fornitore = (f.supplier_name || f.cedente_denominazione || '').toLowerCase();
          // Match fuzzy: il beneficiario deve contenere parte del nome fornitore o viceversa
          return (
            fornitore.includes(benefLower.substring(0, 5)) ||
            benefLower.includes(fornitore.substring(0, 5)) ||
            fornitore.split(' ').some(word => benefLower.includes(word) && word.length > 3)
          );
        });
      }

      // ORDINA PER FORNITORE (raggruppamento visivo) poi per data decrescente
      filtered.sort((a, b) => {
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
      alert('Inserisci il numero del primo assegno');
      return;
    }

    setGenerating(true);
    try {
      await api.post(`/api/assegni/genera`, generateForm);
      setShowGenerate(false);
      setGenerateForm({ numero_primo: '', quantita: 10 });
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGenerating(false);
    }
  };

  const handleClearEmpty = async () => {
    try {
      const res = await api.delete(`/api/assegni/clear-generated?stato=vuoto`);
      alert(res.data.message);
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
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
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({});
  };

  const openFattureModal = assegno => {
    setEditingAssegnoForFatture(assegno);
    setSelectedFatture(assegno.fatture_collegate || []);
    loadFatture(assegno.beneficiario);
    setShowFattureModal(true);
  };

  const toggleFattura = fattura => {
    const exists = selectedFatture.find(f => f.id === fattura.id);
    if (exists) {
      setSelectedFatture(selectedFatture.filter(f => f.id !== fattura.id));
    } else if (selectedFatture.length < 4) {
      // REGOLA CONTABILE: Un assegno può pagare solo fatture dello STESSO fornitore
      const fornitoreNuovo =
        fattura.supplier_name || fattura.cedente_denominazione || fattura.fornitore;
      const fornitoreEsistente = selectedFatture[0]?.fornitore;

      if (
        fornitoreEsistente &&
        fornitoreNuovo &&
        fornitoreNuovo.toLowerCase() !== fornitoreEsistente.toLowerCase()
      ) {
        alert(
          '⚠️ Non puoi collegare fatture di fornitori diversi allo stesso assegno!\n\nFornitore selezionato: ' +
            fornitoreEsistente +
            '\nStai cercando di aggiungere: ' +
            fornitoreNuovo
        );
        return;
      }

      // Usa importo pre-calcolato (negativo per NC)
      const tipoDoc = fattura.tipo_documento || fattura.document_type || 'TD01';
      const isNC = tipoDoc === 'TD04';
      const importoRaw = parseFloat(
        fattura.total_amount || fattura.importo_totale || fattura.importo || 0
      );
      const importo = isNC ? -Math.abs(importoRaw) : importoRaw;

      setSelectedFatture([
        ...selectedFatture,
        {
          id: fattura.id,
          numero: fattura.invoice_number || fattura.numero_fattura,
          importo: importo,
          data: fattura.invoice_date || fattura.data_fattura,
          fornitore: fornitoreNuovo,
          tipo_documento: tipoDoc,
          is_nota_credito: isNC,
        },
      ]);
    } else {
      alert('Puoi collegare massimo 4 fatture per assegno');
    }
  };

  const saveFattureCollegate = async () => {
    if (!editingAssegnoForFatture) return;

    const totaleImporto = selectedFatture.reduce((sum, f) => sum + (f.importo || 0), 0);
    const numeriFacture = selectedFatture.map(f => f.numero).join(', ');
    const beneficiario = selectedFatture[0]?.fornitore || '';
    // Prendi il primo fattura_id come fattura_collegata
    const fatturaCollegata = selectedFatture[0]?.id || null;

    try {
      await api.put(`/api/assegni/${editingAssegnoForFatture.id}`, {
        fatture_collegate: selectedFatture,
        fattura_collegata: fatturaCollegata, // Aggiunto per il pulsante "Vedi Fattura"
        importo: totaleImporto,
        numero_fattura: numeriFacture,
        beneficiario: beneficiario,
        note: `Fatture: ${numeriFacture}`,
        stato: selectedFatture.length > 0 ? 'compilato' : 'vuoto',
      });

      setShowFattureModal(false);
      setEditingAssegnoForFatture(null);
      setSelectedFatture([]);
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDelete = async assegno => {
    try {
      await api.delete(`/api/assegni/${assegno.id}`);
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
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
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setAutoAssociating(false);
    }
  };

  const handleAutoMatch = async (dryRun = false) => {
    setAutoAssociating(true);
    setAutoAssocResult(null);
    try {
      const url = `/api/assegni/auto-match${dryRun ? '?dry_run=true' : ''}`;
      const res = await api.post(url);
      setAutoAssocResult({
        ...res.data,
        _modalita_auto_match: true,
        _dry_run: dryRun,
      });
      if (!dryRun) loadData();
    } catch (error) {
      alert('Errore Auto-Match: ' + (error.response?.data?.detail || error.message));
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
      alert('Errore caricamento ambigui: ' + (e.response?.data?.detail || e.message));
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
      alert('Seleziona almeno una fattura');
      return;
    }
    setAmbiguiResolving(p => ({ ...p, [assegnoId]: true }));
    try {
      await api.post(`/api/assegni/${assegnoId}/risolvi-ambiguo`, { fattura_ids });
      setAmbiguiList(list => list.filter(a => a.assegno_id !== assegnoId));
      loadData();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
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
      alert('Errore Learning: ' + (error.response?.data?.detail || error.message));
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
      alert('Errore: ' + (error.response?.data?.detail || error.message));
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
      alert('Errore: ' + (error.response?.data?.detail || error.message));
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
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setCombinazioneLoading(false);
    }
  };

  // FILTRO ASSEGNI LATO CLIENT
  const filteredAssegni = assegni.filter(a => {
    // Escludi assegni sporchi (senza numero o importo null)
    if (!a.numero || a.importo === null || a.importo === undefined) {
      return false;
    }
    // Filtro fornitore/beneficiario
    if (filterFornitore && !a.beneficiario?.toLowerCase().includes(filterFornitore.toLowerCase())) {
      return false;
    }
    // Filtro importo min
    if (filterImportoMin && (parseFloat(a.importo) || 0) < parseFloat(filterImportoMin)) {
      return false;
    }
    // Filtro importo max
    if (filterImportoMax && (parseFloat(a.importo) || 0) > parseFloat(filterImportoMax)) {
      return false;
    }
    // Filtro numero assegno
    if (
      filterNumeroAssegno &&
      !a.numero?.toLowerCase().includes(filterNumeroAssegno.toLowerCase())
    ) {
      return false;
    }
    // Filtro numero fattura
    if (
      filterNumeroFattura &&
      !a.numero_fattura?.toLowerCase().includes(filterNumeroFattura.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  // Reset filtri
  const resetFilters = () => {
    setFilterFornitore('');
    setFilterImportoMin('');
    setFilterImportoMax('');
    setFilterNumeroAssegno('');
    setFilterNumeroFattura('');
  };

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

  const carnets = groupByCarnet();

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
          dataFattura = d.toLocaleDateString('it-IT');
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
        `CERALDI GROUP S.R.L. - Documento generato il ${new Date().toLocaleDateString('it-IT')} alle ${new Date().toLocaleTimeString('it-IT')} - Pagina ${i}/${pageCount}`,
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
      alert('Seleziona almeno un assegno');
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
    doc.text(`Data: ${new Date().toLocaleDateString('it-IT')}`, 14, 52);

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
          dataFattura = d.toLocaleDateString('it-IT');
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
        `CERALDI GROUP S.R.L. - Documento generato il ${new Date().toLocaleDateString('it-IT')} alle ${new Date().toLocaleTimeString('it-IT')} - Pagina ${i}/${pageCount}`,
        14,
        doc.internal.pageSize.height - 10
      );
    }

    doc.save(`Assegni_Selezionati_${new Date().toISOString().slice(0, 10)}.pdf`);

    // Clear selection after print
    setSelectedAssegni(new Set());
  };

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '16px' }}>
      {/* Action Bar - responsive */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 16,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <button
          onClick={() => setShowGenerate(true)}
          data-testid="genera-assegni-btn"
          style={{
            padding: '10px 16px',
            background: '#4caf50',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: 13,
          }}
        >
          + Genera Assegni
        </button>

        <button
          onClick={handleAutoAssocia}
          disabled={autoAssociating}
          data-testid="auto-associa-btn"
          style={{
            padding: '10px 16px',
            background: autoAssociating ? '#ccc' : '#2196f3',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: autoAssociating ? 'not-allowed' : 'pointer',
            fontWeight: 'bold',
            fontSize: 13,
          }}
        >
          {autoAssociating ? 'Associando...' : 'Auto-Associa'}
        </button>

        {/* Nuovo: Auto-Match rigoroso a 4 livelli (LOGICA_OPERATIVA) */}
        <button
          onClick={() => handleAutoMatch(false)}
          disabled={autoAssociating}
          data-testid="auto-match-btn"
          title="Auto-match rigoroso: 4 livelli (L1 1→1, L2 N uguali→1, L3 N diversi→1, L4 1→N) con tolleranza ±0,005€"
          style={{
            padding: '10px 16px',
            background: autoAssociating
              ? '#ccc'
              : '#15803d',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: autoAssociating ? 'not-allowed' : 'pointer',
            fontWeight: 'bold',
            fontSize: 13,
            boxShadow: '0 2px 4px rgba(5,150,105,0.3)',
          }}
        >
          {autoAssociating ? '🤖 …' : '🤖 Auto-collega'}
        </button>
        <button
          onClick={() => handleAutoMatch(true)}
          disabled={autoAssociating}
          data-testid="auto-match-preview-btn"
          title="Anteprima: mostra cosa collegherebbe senza scrivere sul DB"
          style={{
            padding: '10px 14px',
            background: '#f3f4f6',
            color: '#374151',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            cursor: autoAssociating ? 'not-allowed' : 'pointer',
            fontWeight: 600,
            fontSize: 12,
          }}
        >
          👁️ Anteprima
        </button>

        <button
          onClick={toggleAmbiguiSection}
          data-testid="ambigui-toggle-btn"
          style={{
            flexShrink: 0,
            padding: '10px 14px',
            background: ambiguiOpen ? '#fef3c7' : 'white',
            color: '#92400e',
            border: '1px solid #fcd34d',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 12,
          }}
        >
          {ambiguiOpen ? '▲ Nascondi ambigui' : '⚠ Risolvi ambigui'}
        </button>
      </div>

      {/* Pannello risoluzione ambigui */}
      {ambiguiOpen && (
        <div
          data-testid="ambigui-panel"
          style={{
            marginBottom: 20,
            padding: 16,
            background: '#fffbeb',
            border: '1px solid #fcd34d',
            borderRadius: 10,
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
              <strong style={{ color: '#92400e', fontSize: 14 }}>
                ⚠ Assegni ambigui — serve la tua decisione
              </strong>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: '#78350f' }}>
                Per questi assegni l'auto-matcher ha trovato più di una fattura candidata con lo
                stesso importo. Seleziona quale collegare.
              </p>
            </div>
            <button
              onClick={loadAmbigui}
              disabled={ambiguiLoading}
              style={{
                padding: '6px 10px',
                background: 'white',
                border: '1px solid #d97706',
                borderRadius: 6,
                color: '#b45309',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              {ambiguiLoading ? '⏳ Aggiorno…' : '↻ Ricarica'}
            </button>
          </div>

          {ambiguiLoading && (
            <div style={{ padding: 12, textAlign: 'center' }}>Caricamento ambigui…</div>
          )}

          {!ambiguiLoading && ambiguiList.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: '#059669', fontSize: 14 }}>
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
                  background: 'white',
                  borderRadius: 8,
                  border: '1px solid #fde68a',
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
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#1f2937' }}>
                      [{a.livello}] Assegno n. {a.assegno_numero}
                    </div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                      {a.fornitore_ragione_sociale} — P.IVA {a.fornitore_piva}
                    </div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                      Importo:{' '}
                      <strong style={{ color: '#111827' }}>€ {a.importo.toFixed(2)}</strong>
                      {a.data_emissione && <> · Emissione: {a.data_emissione}</>}
                    </div>
                  </div>
                  <button
                    onClick={() => resolveAmbiguo(a.assegno_id)}
                    disabled={ambiguiResolving[a.assegno_id]}
                    data-testid={`risolvi-${a.assegno_id}`}
                    style={{
                      padding: '8px 14px',
                      background: ambiguiResolving[a.assegno_id]
                        ? '#9ca3af'
                        : '#15803d',
                      color: 'white',
                      border: 'none',
                      borderRadius: 6,
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: 12,
                    }}
                  >
                    {ambiguiResolving[a.assegno_id] ? '⏳ …' : '✓ Collega selezionati'}
                  </button>
                </div>
                {/* Candidate fatture */}
                <div style={{ marginTop: 10, borderTop: '1px dashed #fde68a', paddingTop: 10 }}>
                  {(a.candidates || []).map(c => {
                    const selected = (ambiguiSelections[a.assegno_id] || []).includes(c.fattura_id);
                    return (
                      <label
                        key={c.fattura_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          padding: '6px 8px',
                          background: selected ? '#ecfdf5' : 'transparent',
                          borderRadius: 4,
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
                          {c.data && <span style={{ color: '#6b7280' }}> · {c.data}</span>}
                          {c.fornitore && (
                            <span style={{ color: '#6b7280' }}> · {c.fornitore}</span>
                          )}
                        </span>
                        <span style={{ fontFamily: 'monospace', color: '#111827' }}>
                          € {(c.importo_residuo ?? c.importo_totale ?? 0).toFixed(2)}
                        </span>
                        {c.payment_status === 'partial' && (
                          <span
                            style={{
                              fontSize: 10,
                              background: '#dbeafe',
                              color: '#1e40af',
                              padding: '2px 6px',
                              borderRadius: 3,
                            }}
                          >
                            parziale
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
        </div>
      )}

      {/* chiusura bottoniera originale continua dopo */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        {/* Pulsante Associazione Combinata (somma assegni = fattura) */}
        <button
          onClick={handleAssociaCombinazioni}
          disabled={combinazioneLoading}
          data-testid="associa-combinazioni-btn"
          style={{
            padding: '10px 16px',
            background: combinazioneLoading
              ? '#ccc'
              : '#0f2744',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: combinazioneLoading ? 'not-allowed' : 'pointer',
            fontWeight: 'bold',
            fontSize: 13,
            boxShadow: '0 2px 4px rgba(102,126,234,0.3)',
          }}
        >
          {combinazioneLoading ? '⏳ Cercando...' : '🔗 Combinazioni'}
        </button>

        {/* Pulsante Sync da EC */}
        <button
          onClick={async () => {
            try {
              const res = await api.post('/api/assegni/sync-da-estratto-conto');
              alert(`Sincronizzati ${res.data.assegni_creati} nuovi assegni dall'estratto conto`);
              loadData();
            } catch (e) {
              alert('Errore sincronizzazione: ' + (e.response?.data?.detail || e.message));
            }
          }}
          data-testid="sync-ec-btn"
          style={{
            padding: '10px 16px',
            background: '#ff9800',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: 13,
          }}
        >
          🔄 Sync da E/C
        </button>

        {/* Pulsante Stampa Selezionati */}
        {selectedAssegni.size > 0 && (
          <button
            onClick={generateSelectedPDF}
            data-testid="stampa-selezionati-btn"
            style={{
              padding: '10px 16px',
              background: '#9c27b0',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 'bold',
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            🖨️ Stampa {selectedAssegni.size} Selezionati
          </button>
        )}

        <button
          onClick={() => setShowFilters(!showFilters)}
          data-testid="toggle-filters-btn"
          style={{
            padding: '10px 16px',
            background: showFilters ? '#1e3a5f' : 'transparent',
            color: showFilters ? 'white' : '#1e3a5f',
            border: '1px solid #1e3a5f',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: 13,
          }}
        >
          🔍 Filtri{' '}
          {(filterFornitore ||
            filterImportoMin ||
            filterImportoMax ||
            filterNumeroAssegno ||
            filterNumeroFattura) &&
            '●'}
        </button>

        {/* Selettore Anno */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Anno:</span>
          <select
            value={filterAnno}
            onChange={e => setFilterAnno(parseInt(e.target.value))}
            data-testid="select-anno"
            style={{
              padding: '10px 16px',
              border: '2px solid #1e3a5f',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 'bold',
              color: '#1e3a5f',
              background: 'white',
              cursor: 'pointer',
            }}
          >
            {[...Array(5)].map((_, i) => {
              const y = new Date().getFullYear() - i;
              return (
                <option key={y} value={y}>
                  {y}
                </option>
              );
            })}
          </select>
        </div>

        <button
          onClick={handleClearEmpty}
          data-testid="svuota-btn"
          style={{
            padding: '10px 16px',
            background: 'transparent',
            color: '#666',
            border: '1px solid #ddd',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          Svuota
        </button>

        {/* === LEARNING MACHINE BUTTONS === */}
        <div
          style={{
            display: 'flex',
            gap: 6,
            marginLeft: 'auto',
            padding: '4px 8px',
            background: '#0f2744',
            borderRadius: 8,
          }}
        >
          <button
            onClick={handleLearn}
            disabled={learningLoading}
            data-testid="learn-btn"
            title="Apprende dai dati esistenti per migliorare le associazioni future"
            style={{
              padding: '8px 12px',
              background: learningLoading ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.15)',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: learningLoading ? 'not-allowed' : 'pointer',
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {learningLoading ? '⏳' : '🧠'} Learn
          </button>

          <button
            onClick={handleAssociaIntelligente}
            disabled={autoAssociating}
            data-testid="associa-intelligente-btn"
            title="Usa i pattern appresi per associazioni più accurate"
            style={{
              padding: '8px 12px',
              background: autoAssociating ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.15)',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: autoAssociating ? 'not-allowed' : 'pointer',
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {autoAssociating ? '⏳' : '🤖'} Smart
          </button>

          <button
            onClick={() => handlePuliziaDuplicati(true)}
            disabled={puliziaLoading}
            data-testid="pulizia-duplicati-btn"
            title="Identifica e rimuove duplicati"
            style={{
              padding: '8px 12px',
              background: puliziaLoading ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.15)',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: puliziaLoading ? 'not-allowed' : 'pointer',
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {puliziaLoading ? '⏳' : '🧹'} Pulizia
          </button>

          <Link
            to="/learning-machine?tab=assegni"
            style={{
              padding: '8px 12px',
              background: 'rgba(255,255,255,0.15)',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              textDecoration: 'none',
              fontSize: 12,
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
            title="Dashboard Learning Machine completa"
          >
            📊 Dashboard
          </Link>
        </div>
      </div>

      {/* STATS AVANZATE BADGE */}
      {statsAvanzate && (
        <div
          style={{
            display: 'flex',
            gap: 16,
            marginBottom: 16,
            padding: 12,
            background: '#dbeafe',
            borderRadius: 10,
            border: '1px solid #bae6fd',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 20 }}>📊</span>
            <div>
              <div style={{ fontSize: 11, color: '#64748b' }}>Health Score</div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color:
                    statsAvanzate.health_score >= 90
                      ? '#16a34a'
                      : statsAvanzate.health_score >= 70
                        ? '#ca8a04'
                        : '#dc2626',
                }}
              >
                {statsAvanzate.health_score}%
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 20 }}>✅</span>
            <div>
              <div style={{ fontSize: 11, color: '#64748b' }}>Con Beneficiario</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#1e293b' }}>
                {statsAvanzate.con_beneficiario}/{statsAvanzate.totale_assegni}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 20 }}>📄</span>
            <div>
              <div style={{ fontSize: 11, color: '#64748b' }}>Con Fattura</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#1e293b' }}>
                {statsAvanzate.con_fattura}/{statsAvanzate.totale_assegni}
              </div>
            </div>
          </div>

          {statsAvanzate.duplicati > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 20 }}>⚠️</span>
              <div>
                <div style={{ fontSize: 11, color: '#dc2626' }}>Duplicati</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#dc2626' }}>
                  {statsAvanzate.duplicati}
                </div>
              </div>
            </div>
          )}

          {statsAvanzate.senza_beneficiario > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 20 }}>❓</span>
              <div>
                <div style={{ fontSize: 11, color: '#ca8a04' }}>Da Associare</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#ca8a04' }}>
                  {statsAvanzate.senza_beneficiario}
                </div>
              </div>
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
            background: '#dcfce7',
            borderRadius: 8,
            border: '1px solid #6ee7b7',
          }}
        >
          <div
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
          >
            <div>
              <strong style={{ color: '#059669', fontSize: 14 }}>
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
            <button
              onClick={() => setLearningResult(null)}
              style={{
                padding: '4px 8px',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* RISULTATO PULIZIA */}
      {puliziaResult && (
        <div
          style={{
            marginBottom: 16,
            padding: 15,
            background: puliziaResult.dry_run ? '#fffbeb' : '#fef2f2',
            borderRadius: 8,
            border: `1px solid ${puliziaResult.dry_run ? '#fcd34d' : '#fca5a5'}`,
          }}
        >
          <div
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
          >
            <div>
              <strong
                style={{ color: puliziaResult.dry_run ? '#b45309' : '#dc2626', fontSize: 14 }}
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
                <button
                  onClick={() => handlePuliziaDuplicati(false)}
                  style={{
                    marginTop: 10,
                    padding: '8px 16px',
                    background: '#dc2626',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  ⚠️ Conferma Eliminazione
                </button>
              )}
            </div>
            <button
              onClick={() => setPuliziaResult(null)}
              style={{
                padding: '4px 8px',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* PANNELLO FILTRI - FIXED quando aperto */}
      {showFilters && (
        <div
          style={{
            position: 'fixed',
            top: 60,
            left: 200,
            right: 20,
            zIndex: 100,
            background: '#f8fafc',
            borderRadius: 12,
            padding: 16,
            border: '1px solid #e2e8f0',
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 12,
            }}
          >
            <div>
              <label style={{ fontSize: 12, color: '#666', display: 'block', marginBottom: 4 }}>
                Fornitore/Beneficiario
              </label>
              <input
                type="text"
                value={filterFornitore}
                onChange={e => setFilterFornitore(e.target.value)}
                placeholder="Cerca fornitore..."
                data-testid="filter-fornitore"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ddd',
                  borderRadius: 6,
                  fontSize: 14,
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: '#666', display: 'block', marginBottom: 4 }}>
                Importo Min (€)
              </label>
              <input
                type="number"
                value={filterImportoMin}
                onChange={e => setFilterImportoMin(e.target.value)}
                placeholder="0.00"
                data-testid="filter-importo-min"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ddd',
                  borderRadius: 6,
                  fontSize: 14,
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: '#666', display: 'block', marginBottom: 4 }}>
                Importo Max (€)
              </label>
              <input
                type="number"
                value={filterImportoMax}
                onChange={e => setFilterImportoMax(e.target.value)}
                placeholder="99999"
                data-testid="filter-importo-max"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ddd',
                  borderRadius: 6,
                  fontSize: 14,
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: '#666', display: 'block', marginBottom: 4 }}>
                N. Assegno
              </label>
              <input
                type="text"
                value={filterNumeroAssegno}
                onChange={e => setFilterNumeroAssegno(e.target.value)}
                placeholder="Cerca assegno..."
                data-testid="filter-numero-assegno"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ddd',
                  borderRadius: 6,
                  fontSize: 14,
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: '#666', display: 'block', marginBottom: 4 }}>
                N. Fattura
              </label>
              <input
                type="text"
                value={filterNumeroFattura}
                onChange={e => setFilterNumeroFattura(e.target.value)}
                placeholder="Cerca fattura..."
                data-testid="filter-numero-fattura"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ddd',
                  borderRadius: 6,
                  fontSize: 14,
                }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
              <button
                onClick={resetFilters}
                data-testid="reset-filters-btn"
                style={{
                  padding: '8px 16px',
                  background: '#ef4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                Reset
              </button>
              <button
                onClick={() => setShowFilters(false)}
                style={{
                  padding: '8px 12px',
                  background: '#64748b',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                ✕
              </button>
            </div>
          </div>

          {/* Riepilogo filtri attivi */}
          {(filterFornitore ||
            filterImportoMin ||
            filterImportoMax ||
            filterNumeroAssegno ||
            filterNumeroFattura) && (
            <div style={{ marginTop: 12, fontSize: 13, color: '#1e3a5f' }}>
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
            background: '#ecfdf5',
            borderRadius: 8,
            border: '1px solid #6ee7b7',
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
              <strong style={{ color: '#047857', fontSize: 14 }}>
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
                  🏦 Movimenti banca creati:{' '}
                  <strong>{autoAssocResult.movimenti_banca_creati ?? 0}</strong>
                </span>
              </div>
              <div
                style={{ marginTop: 8, fontSize: 13, display: 'flex', flexWrap: 'wrap', gap: 12 }}
              >
                <span style={{ color: '#059669' }}>
                  ✓ L1 (1=1): <strong>{autoAssocResult.totali?.L1 ?? 0}</strong>
                </span>
                <span style={{ color: '#0369a1' }}>
                  ✓ L2 (N uguali→1): <strong>{autoAssocResult.totali?.L2 ?? 0}</strong>
                </span>
                <span style={{ color: '#7c3aed' }}>
                  ✓ L3 (N diversi→1): <strong>{autoAssocResult.totali?.L3 ?? 0}</strong>
                </span>
                <span style={{ color: '#ea580c' }}>
                  ✓ L4 (1→N): <strong>{autoAssocResult.totali?.L4 ?? 0}</strong>
                </span>
                <span style={{ color: '#dc2626' }}>
                  ⚠ Ambigui: <strong>{autoAssocResult.totali?.ambigui ?? 0}</strong>
                </span>
                <span style={{ color: '#6b7280' }}>
                  ✗ Non trovati: <strong>{autoAssocResult.totali?.non_trovati ?? 0}</strong>
                </span>
              </div>
              {autoAssocResult.ambigui?.length > 0 && (
                <details style={{ marginTop: 10, fontSize: 12 }}>
                  <summary style={{ cursor: 'pointer', color: '#dc2626', fontWeight: 600 }}>
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
            <button onClick={() => setAutoAssocResult(null)} style={{ padding: '5px 10px' }}>
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Risultato Auto-Associazione (legacy) */}
      {autoAssocResult && !autoAssocResult._modalita_auto_match && (
        <div
          style={{
            marginBottom: 20,
            padding: 15,
            background: autoAssocResult.assegni_aggiornati > 0 ? '#e8f5e9' : '#fff3e0',
            borderRadius: 8,
            border: `1px solid ${autoAssocResult.assegni_aggiornati > 0 ? '#c8e6c9' : '#ffe0b2'}`,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <strong
                style={{ color: autoAssocResult.assegni_aggiornati > 0 ? '#2e7d32' : '#e65100' }}
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
                          <span style={{ color: '#9c27b0' }}> [MULTIPLO]</span>
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
            <button onClick={() => setAutoAssocResult(null)} style={{ padding: '5px 10px' }}>
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Risultato Associazione Combinata */}
      {combinazioneResult && (
        <div
          style={{
            marginBottom: 20,
            padding: 15,
            background: combinazioneResult.match_trovati > 0 ? '#e3f2fd' : '#fff3e0',
            borderRadius: 8,
            border: `1px solid ${combinazioneResult.match_trovati > 0 ? '#90caf9' : '#ffe0b2'}`,
          }}
        >
          <div
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
          >
            <div style={{ flex: 1 }}>
              <strong
                style={{ color: combinazioneResult.match_trovati > 0 ? '#1565c0' : '#e65100' }}
              >
                🔗{' '}
                {combinazioneResult.message ||
                  (combinazioneResult.match_trovati > 0
                    ? `Trovate ${combinazioneResult.match_trovati} combinazioni! (${combinazioneResult.assegni_associati} assegni associati)`
                    : 'Nessuna combinazione trovata')}
              </strong>
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
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
                            <span style={{ color: '#1565c0', fontWeight: 600 }}>
                              {d.num_assegni} Assegni
                            </span>
                            {' → '}
                            <span style={{ color: '#2e7d32', fontWeight: 600 }}>
                              Fattura {d.fattura_numero}
                            </span>
                            {d.fornitore && (
                              <span style={{ color: '#666' }}>
                                {' '}
                                ({d.fornitore.substring(0, 25)})
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>
                            Assegni: {d.assegni?.join(', ')} • Somma: {formatEuro(d.somma_assegni)}{' '}
                            = Fattura: {formatEuro(d.fattura_importo)}
                            {d.differenza !== 0 && (
                              <span style={{ color: '#f59e0b' }}>
                                {' '}
                                (diff: {formatEuro(d.differenza)})
                              </span>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              {combinazioneResult.assegni_non_associabili &&
                combinazioneResult.assegni_non_associabili.length > 0 && (
                  <div style={{ marginTop: 8, fontSize: 12, color: '#f59e0b' }}>
                    ⚠️ {combinazioneResult.assegni_non_associabili.length} assegni rimasti senza
                    corrispondenza
                  </div>
                )}
            </div>
            <button
              onClick={() => setCombinazioneResult(null)}
              style={{ padding: '5px 10px', marginLeft: 10 }}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* SEZIONE ASSEGNI NON ASSOCIATI */}
      <div
        style={{
          background: 'white',
          borderRadius: 12,
          padding: 16,
          marginBottom: 16,
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
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
              color: '#1e293b',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            ⚠️ Assegni Senza Beneficiario
            {assegniNonAssociati.totale !== undefined && (
              <span
                style={{
                  background: assegniNonAssociati.totale > 0 ? '#fef3c7' : '#dcfce7',
                  color: assegniNonAssociati.totale > 0 ? '#92400e' : '#166534',
                  padding: '2px 8px',
                  borderRadius: 12,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                {assegniNonAssociati.totale}
              </span>
            )}
          </h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={e => {
                e.stopPropagation();
                loadAssegniNonAssociati();
              }}
              disabled={loadingNonAssociati}
              style={{
                padding: '6px 12px',
                background: '#f1f5f9',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              {loadingNonAssociati ? '⏳' : '🔄'} Aggiorna
            </button>
            <span style={{ fontSize: 18 }}>{showNonAssociati ? '▲' : '▼'}</span>
          </div>
        </div>

        {showNonAssociati && (
          <div style={{ marginTop: 16 }}>
            {loadingNonAssociati ? (
              <div style={{ textAlign: 'center', padding: 20, color: '#64748b' }}>
                ⏳ Caricamento...
              </div>
            ) : assegniNonAssociati.totale === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: 20,
                  background: '#f0fdf4',
                  borderRadius: 8,
                  color: '#166534',
                }}
              >
                ✅ Tutti gli assegni sono stati associati!
              </div>
            ) : (
              <div>
                <p style={{ margin: '0 0 12px', fontSize: 13, color: '#64748b' }}>
                  Questi assegni hanno un importo ma nessun beneficiario. Clicca "Associa" per
                  collegare manualmente a una fattura.
                </p>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#fef3c7' }}>
                        <th style={{ padding: 10, textAlign: 'left' }}>Importo</th>
                        <th style={{ padding: 10, textAlign: 'left' }}>Numero Assegno</th>
                        <th style={{ padding: 10, textAlign: 'center' }}>Azioni</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(assegniNonAssociati.per_importo || {}).map(
                        ([importo, info]) =>
                          info.numeri.map((numero, idx) => (
                            <tr key={numero} style={{ borderTop: '1px solid #e2e8f0' }}>
                              <td style={{ padding: 10, fontWeight: 600, color: '#1e293b' }}>
                                {importo}
                              </td>
                              <td style={{ padding: 10, fontFamily: 'monospace' }}>{numero}</td>
                              <td style={{ padding: 10, textAlign: 'center' }}>
                                <button
                                  onClick={() => {
                                    const assegnoData = assegni.find(a => a.numero === numero);
                                    if (assegnoData) {
                                      openFattureModal(assegnoData);
                                    } else {
                                      alert(
                                        `Assegno ${numero} non trovato nella lista. Prova a rimuovere i filtri.`
                                      );
                                    }
                                  }}
                                  style={{
                                    padding: '6px 14px',
                                    background: '#3b82f6',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: 6,
                                    cursor: 'pointer',
                                    fontSize: 12,
                                    fontWeight: 500,
                                  }}
                                >
                                  🔗 Associa Fattura
                                </button>
                              </td>
                            </tr>
                          ))
                      )}
                    </tbody>
                  </table>
                </div>
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
            background: 'white',
            borderRadius: 12,
            padding: 60,
            textAlign: 'center',
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          }}
        >
          <h3 style={{ color: '#666', marginBottom: 10 }}>
            {assegni.length === 0
              ? 'Nessun assegno presente'
              : 'Nessun assegno corrisponde ai filtri'}
          </h3>
          <p style={{ color: '#999' }}>
            {assegni.length === 0
              ? 'Genera i primi assegni per iniziare'
              : 'Prova a modificare i filtri di ricerca'}
          </p>
        </div>
      ) : (
        <>
          {/* MOBILE CARDS VIEW */}
          <div className="md:hidden" style={{ display: 'block' }}>
            <style>{`
              @media (min-width: "100%"px) {
                .mobile-cards-assegni { display: none !important; }
                .desktop-table-assegni { display: block !important; }
              }
              @media (max-width: "100%"px) {
                .mobile-cards-assegni { display: block !important; }
                .desktop-table-assegni { display: none !important; }
              }
            `}</style>
            <div className="mobile-cards-assegni">
              <div style={{ padding: '12px 0', borderBottom: '1px solid #eee', marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>
                  Lista Assegni ({filteredAssegni.length})
                </h3>
              </div>
              {Object.entries(carnets).map(([carnetId, carnetAssegni], carnetIdx) => (
                <div key={carnetId} style={{ marginBottom: 16 }}>
                  {/* Carnet Header Mobile */}
                  <div
                    style={{
                      background: '#f0f9ff',
                      padding: '10px 12px',
                      borderRadius: '8px 8px 0 0',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <div>
                      <strong style={{ fontSize: 14 }}>Carnet {carnetIdx + 1}</strong>
                      <span style={{ color: '#666', marginLeft: 8, fontSize: 12 }}>
                        ({carnetAssegni.length} assegni)
                      </span>
                    </div>
                    <div style={{ fontWeight: 'bold', color: '#1e3a5f', fontSize: 14 }}>
                      {formatEuro(
                        carnetAssegni.reduce((s, a) => s + (parseFloat(a.importo) || 0), 0)
                      )}
                    </div>
                  </div>

                  {/* Assegni Cards */}
                  {carnetAssegni.map((assegno, idx) => (
                    <div
                      key={assegno.id}
                      style={{
                        background: selectedAssegni.has(assegno.id)
                          ? '#e8f5e9'
                          : idx % 2 === 0
                            ? 'white'
                            : '#fafafa',
                        padding: 12,
                        borderBottom: '1px solid #eee',
                        borderLeft: '1px solid #eee',
                        borderRight: '1px solid #eee',
                        ...(idx === carnetAssegni.length - 1
                          ? { borderRadius: '0 0 8px 8px' }
                          : {}),
                      }}
                    >
                      {/* Row 1: Checkbox + Numero + Stato + Importo */}
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: 8,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <input
                            type="checkbox"
                            checked={selectedAssegni.has(assegno.id)}
                            onChange={() => toggleSelectAssegno(assegno.id)}
                            style={{ width: 18, height: 18, cursor: 'pointer' }}
                          />
                          <span
                            style={{
                              fontFamily: 'monospace',
                              fontWeight: 'bold',
                              color: '#1e3a5f',
                              fontSize: 13,
                            }}
                          >
                            {assegno.numero?.split('-')[1] || assegno.numero}
                          </span>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: 10,
                              fontSize: 10,
                              fontWeight: 'bold',
                              background: STATI_ASSEGNO[assegno.stato]?.color || '#9e9e9e',
                              color: 'white',
                            }}
                          >
                            {STATI_ASSEGNO[assegno.stato]?.label || assegno.stato}
                          </span>
                        </div>
                        <span style={{ fontWeight: 'bold', fontSize: 15, color: '#1e3a5f' }}>
                          {formatEuro(assegno.importo)}
                        </span>
                      </div>

                      {/* Row 2: Beneficiario */}
                      {assegno.beneficiario && (
                        <div style={{ fontSize: 13, marginBottom: 6 }}>
                          <span style={{ color: '#666' }}>👤</span> {assegno.beneficiario}
                        </div>
                      )}

                      {/* Row 3: Fattura (se presente) */}
                      {assegno.numero_fattura && (
                        <div
                          style={{
                            fontSize: 12,
                            color: '#2196f3',
                            marginBottom: 6,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                          }}
                        >
                          <span>📄 Fatt. {assegno.numero_fattura}</span>
                          {assegno.data_fattura && (
                            <span style={{ color: '#666' }}>
                              ({formatDateIT(assegno.data_fattura)})
                            </span>
                          )}
                          {/* Link alla fattura - usa fattura_collegata o prima di fatture_collegate */}
                          {(assegno.fattura_collegata ||
                            assegno.fatture_collegate?.[0]?.fattura_id) && (
                            <a
                              href={`/api/fatture-ricevute/fattura/${assegno.fattura_collegata || assegno.fatture_collegate?.[0]?.fattura_id}/view-assoinvoice`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                padding: '2px 8px',
                                background: '#4caf50',
                                color: 'white',
                                borderRadius: 4,
                                fontSize: 11,
                                textDecoration: 'none',
                              }}
                            >
                              Vedi
                            </a>
                          )}
                        </div>
                      )}

                      {/* Row 4: Azioni */}
                      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <button
                          onClick={() => startEdit(assegno)}
                          style={{
                            flex: 1,
                            padding: '8px',
                            background: '#f5f5f5',
                            border: 'none',
                            borderRadius: 6,
                            cursor: 'pointer',
                            fontSize: 12,
                          }}
                        >
                          ✏️ Modifica
                        </button>
                        <button
                          onClick={() => openFattureModal(assegno)}
                          style={{
                            flex: 1,
                            padding: '8px',
                            background: '#e3f2fd',
                            border: 'none',
                            borderRadius: 6,
                            cursor: 'pointer',
                            fontSize: 12,
                          }}
                        >
                          📄 Fatture
                        </button>
                        <button
                          onClick={() => handleDelete(assegno)}
                          style={{
                            padding: '8px 12px',
                            background: '#ffebee',
                            border: 'none',
                            borderRadius: 6,
                            cursor: 'pointer',
                            color: '#c62828',
                            fontSize: 12,
                          }}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* DESKTOP TABLE VIEW */}
          <div
            className="desktop-table-assegni"
            style={{
              background: 'white',
              borderRadius: 12,
              overflow: 'hidden',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
          >
            <div style={{ padding: 16, borderBottom: '1px solid #eee' }}>
              <h3 style={{ margin: 0 }}>Lista Assegni ({filteredAssegni.length})</h3>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e5e7eb' }}>
                    <th
                      style={{
                        padding: '10px 8px',
                        textAlign: 'center',
                        fontWeight: 600,
                        fontSize: 12,
                        width: 40,
                      }}
                    >
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
                    </th>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'left',
                        fontWeight: 600,
                        fontSize: 12,
                      }}
                    >
                      N. Assegno
                    </th>
                    <th
                      style={{
                        padding: '10px 6px',
                        textAlign: 'center',
                        fontWeight: 600,
                        fontSize: 12,
                      }}
                    >
                      Stato
                    </th>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'left',
                        fontWeight: 600,
                        fontSize: 12,
                      }}
                    >
                      Beneficiario / Note
                    </th>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'right',
                        fontWeight: 600,
                        fontSize: 12,
                      }}
                    >
                      Importo
                    </th>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'left',
                        fontWeight: 600,
                        fontSize: 12,
                      }}
                    >
                      Fattura / Data
                    </th>
                    <th
                      style={{
                        padding: '10px 6px',
                        textAlign: 'center',
                        fontWeight: 600,
                        fontSize: 12,
                      }}
                    >
                      Azioni
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(carnets).map(([carnetId, carnetAssegni], carnetIdx) => (
                    <React.Fragment key={carnetId}>
                      {carnetAssegni.map((assegno, idx) => (
                        <tr
                          key={assegno.id}
                          style={{
                            borderBottom: '1px solid #eee',
                            background: selectedAssegni.has(assegno.id) ? '#e8f5e9' : 'white',
                          }}
                        >
                          {/* Checkbox selezione */}
                          <td style={{ padding: '8px', textAlign: 'center' }}>
                            <input
                              type="checkbox"
                              checked={selectedAssegni.has(assegno.id)}
                              onChange={() => toggleSelectAssegno(assegno.id)}
                              data-testid={`select-${assegno.id}`}
                              style={{ width: 18, height: 18, cursor: 'pointer' }}
                            />
                          </td>

                          {/* Numero Assegno */}
                          <td style={{ padding: '8px 12px' }}>
                            <span
                              style={{
                                fontFamily: 'monospace',
                                fontWeight: 'bold',
                                color: '#1e3a5f',
                                fontSize: 13,
                              }}
                            >
                              {assegno.numero}
                            </span>
                          </td>

                          {/* Stato */}
                          <td style={{ padding: '8px 6px', textAlign: 'center' }}>
                            <span
                              style={{
                                padding: '3px 8px',
                                borderRadius: 10,
                                fontSize: 10,
                                fontWeight: 'bold',
                                background: STATI_ASSEGNO[assegno.stato]?.color || '#9e9e9e',
                                color: 'white',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {STATI_ASSEGNO[assegno.stato]?.label || assegno.stato}
                            </span>
                          </td>

                          {/* Beneficiario + Note in colonna unica */}
                          <td style={{ padding: '8px 12px', maxWidth: 250 }}>
                            {editingId === assegno.id ? (
                              <input
                                type="text"
                                value={editForm.beneficiario}
                                onChange={e =>
                                  setEditForm({ ...editForm, beneficiario: e.target.value })
                                }
                                placeholder="Beneficiario"
                                style={{
                                  padding: 6,
                                  borderRadius: 4,
                                  border: '1px solid #ddd',
                                  width: '100%',
                                  fontSize: 12,
                                }}
                              />
                            ) : (
                              <div>
                                <div style={{ fontWeight: 500, fontSize: 13 }}>
                                  {assegno.beneficiario || '-'}
                                </div>
                                {assegno.note && (
                                  <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>
                                    {assegno.note}
                                  </div>
                                )}
                              </div>
                            )}
                          </td>

                          {/* Importo */}
                          <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                            {editingId === assegno.id ? (
                              <input
                                type="number"
                                step="0.01"
                                value={editForm.importo}
                                onChange={e =>
                                  setEditForm({
                                    ...editForm,
                                    importo: parseFloat(e.target.value) || '',
                                  })
                                }
                                placeholder="0.00"
                                style={{
                                  padding: 6,
                                  borderRadius: 4,
                                  border: '1px solid #ddd',
                                  width: 80,
                                  textAlign: 'right',
                                  fontSize: 12,
                                }}
                              />
                            ) : (
                              <span style={{ fontWeight: 'bold', fontSize: 13 }}>
                                {formatEuro(assegno.importo)}
                              </span>
                            )}
                          </td>

                          {/* Data + N.Fattura combinati */}
                          <td style={{ padding: '8px 12px' }}>
                            {editingId === assegno.id ? (
                              <div style={{ display: 'flex', gap: 4 }}>
                                <input
                                  type="date"
                                  value={editForm.data_fattura}
                                  onChange={e =>
                                    setEditForm({ ...editForm, data_fattura: e.target.value })
                                  }
                                  style={{
                                    padding: 4,
                                    borderRadius: 4,
                                    border: '1px solid #ddd',
                                    fontSize: 11,
                                    width: 110,
                                  }}
                                />
                                <input
                                  type="text"
                                  value={editForm.numero_fattura}
                                  onChange={e =>
                                    setEditForm({ ...editForm, numero_fattura: e.target.value })
                                  }
                                  placeholder="N.Fatt"
                                  style={{
                                    padding: 4,
                                    borderRadius: 4,
                                    border: '1px solid #ddd',
                                    fontSize: 11,
                                    width: 80,
                                  }}
                                />
                              </div>
                            ) : (
                              <div
                                style={{
                                  fontSize: 12,
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 6,
                                }}
                              >
                                {/* Pulsante per visualizzare fattura */}
                                {(assegno.fattura_collegata ||
                                  assegno.fatture_collegate?.[0]?.fattura_id) && (
                                  <a
                                    href={`/api/fatture-ricevute/fattura/${assegno.fattura_collegata || assegno.fatture_collegate?.[0]?.fattura_id}/view-assoinvoice`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={e => e.stopPropagation()}
                                    style={{
                                      padding: '3px 8px',
                                      background: '#4caf50',
                                      color: 'white',
                                      border: 'none',
                                      borderRadius: 4,
                                      cursor: 'pointer',
                                      fontSize: 11,
                                      fontWeight: 'bold',
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: 3,
                                      textDecoration: 'none',
                                    }}
                                    title="Visualizza Fattura"
                                    data-testid={`view-fattura-${assegno.id}`}
                                  >
                                    📄 Vedi
                                  </a>
                                )}
                                {/* Info fattura */}
                                <div>
                                  {assegno.numero_fattura && (
                                    <div style={{ color: '#2196f3' }}>
                                      Fatt. {assegno.numero_fattura}
                                    </div>
                                  )}
                                  {assegno.data_fattura && (
                                    <div style={{ color: '#666', fontSize: 11 }}>
                                      {formatDateIT(assegno.data_fattura)}
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </td>

                          {/* Azioni - STAMPA ed ELIMINA nella stessa riga */}
                          <td style={{ padding: '6px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                              {editingId === assegno.id ? (
                                <>
                                  <button
                                    onClick={handleSaveEdit}
                                    style={{
                                      padding: '4px 8px',
                                      cursor: 'pointer',
                                      background: '#4caf50',
                                      color: 'white',
                                      border: 'none',
                                      borderRadius: 4,
                                      fontSize: 11,
                                    }}
                                  >
                                    ✓
                                  </button>
                                  <button
                                    onClick={cancelEdit}
                                    style={{
                                      padding: '4px 8px',
                                      cursor: 'pointer',
                                      background: '#f44336',
                                      color: 'white',
                                      border: 'none',
                                      borderRadius: 4,
                                      fontSize: 11,
                                    }}
                                  >
                                    ✕
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button
                                    onClick={() => startEdit(assegno)}
                                    data-testid={`edit-${assegno.id}`}
                                    style={{
                                      padding: '4px 6px',
                                      cursor: 'pointer',
                                      background: '#f5f5f5',
                                      border: 'none',
                                      borderRadius: 4,
                                    }}
                                    title="Modifica"
                                  >
                                    ✏️
                                  </button>
                                  <button
                                    onClick={() => openFattureModal(assegno)}
                                    data-testid={`fatture-${assegno.id}`}
                                    style={{
                                      padding: '4px 6px',
                                      cursor: 'pointer',
                                      background: '#f5f5f5',
                                      border: 'none',
                                      borderRadius: 4,
                                    }}
                                    title="Collega Fatture"
                                  >
                                    📄
                                  </button>
                                  {/* STAMPA singolo assegno */}
                                  <button
                                    onClick={() => {
                                      const doc = generateCarnetPDF(carnetId, [assegno]);
                                      doc.save(`Assegno_${assegno.numero}.pdf`);
                                    }}
                                    data-testid={`print-${assegno.id}`}
                                    style={{
                                      padding: '4px 6px',
                                      cursor: 'pointer',
                                      background: '#2196f3',
                                      color: 'white',
                                      border: 'none',
                                      borderRadius: 4,
                                    }}
                                    title="Stampa"
                                  >
                                    🖨️
                                  </button>
                                  {/* ELIMINA */}
                                  <button
                                    onClick={() => handleDelete(assegno)}
                                    data-testid={`delete-${assegno.id}`}
                                    style={{
                                      padding: '4px 6px',
                                      cursor: 'pointer',
                                      background: '#ffebee',
                                      border: 'none',
                                      borderRadius: 4,
                                      color: '#c62828',
                                    }}
                                    title="Elimina"
                                  >
                                    🗑️
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
      {/* Generate Modal */}
      {showGenerate && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowGenerate(false)}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 24,
              maxWidth: 400,
              width: '90%',
            }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>Genera 10 Assegni Progressivi</h2>
            <p style={{ color: '#666', fontSize: 14, marginBottom: 20 }}>
              Inserisci il numero del primo assegno nel formato PREFISSO-NUMERO
            </p>

            <div style={{ marginBottom: 15 }}>
              <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold' }}>
                Numero Primo Assegno
              </label>
              <input
                type="text"
                value={generateForm.numero_primo}
                onChange={e => setGenerateForm({ ...generateForm, numero_primo: e.target.value })}
                placeholder="0208769182-11"
                data-testid="numero-primo-input"
                style={{
                  padding: 12,
                  width: '100%',
                  borderRadius: 8,
                  border: '1px solid #ddd',
                  fontFamily: 'monospace',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowGenerate(false)}
                style={{
                  padding: '10px 20px',
                  background: '#9e9e9e',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              >
                Annulla
              </button>
              <button
                onClick={handleGenerate}
                disabled={generating}
                data-testid="genera-salva-btn"
                style={{
                  padding: '10px 20px',
                  background: '#4caf50',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: 'bold',
                }}
              >
                {generating ? 'Generazione...' : 'Genera e Salva'}
              </button>
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
            background: 'rgba(0,0,0,0.3)',
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
              background: 'white',
              borderRadius: 12,
              padding: 0,
              maxWidth: 700,
              width: '95%',
              maxHeight: '85vh',
              overflow: 'hidden',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
              cursor: isDragging ? 'grabbing' : 'default',
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header Draggable */}
            <div
              style={{
                padding: '16px 24px',
                background: '#0f2744',
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
                <h2 style={{ margin: 0, fontSize: 18 }}>📄 Collega Fatture all'Assegno</h2>
                <p style={{ margin: '4px 0 0', fontSize: 12, opacity: 0.8 }}>
                  Trascina per spostare
                </p>
              </div>
              <button
                onClick={() => {
                  setShowFattureModal(false);
                  setSelectedFatture([]);
                  setModalPosition({ x: 0, y: 0 });
                }}
                style={{
                  background: 'rgba(255,255,255,0.2)',
                  border: 'none',
                  color: 'white',
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  cursor: 'pointer',
                  fontSize: 18,
                }}
              >
                ×
              </button>
            </div>

            {/* Content */}
            <div style={{ padding: 24, maxHeight: 'calc(85vh - 120px)', overflowY: 'auto' }}>
              {/* Info Assegno con Importo */}
              <div
                style={{
                  background: '#f8fafc',
                  padding: 16,
                  borderRadius: 8,
                  marginBottom: 20,
                  border: '1px solid #e2e8f0',
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
                    <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                      Assegno N.
                    </div>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 'bold',
                        color: '#1e293b',
                        fontFamily: 'monospace',
                      }}
                    >
                      {editingAssegnoForFatture?.numero}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                      Importo Assegno
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 'bold', color: '#1e3a5f' }}>
                      {formatEuro(editingAssegnoForFatture?.importo || 0)}
                    </div>
                  </div>
                </div>
                <p
                  style={{
                    color: '#3b82f6',
                    fontSize: 12,
                    margin: '12px 0 0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  ℹ️ Puoi collegare fino a <strong>4 fatture</strong> a un singolo assegno
                </p>
              </div>

              {/* Fatture Selezionate */}
              {selectedFatture.length > 0 && (
                <div
                  style={{
                    background: '#ecfdf5',
                    padding: 16,
                    borderRadius: 8,
                    marginBottom: 20,
                    border: '1px solid #a7f3d0',
                  }}
                >
                  <strong style={{ color: '#065f46' }}>
                    ✓ Fatture Selezionate ({selectedFatture.length}/4):
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
                          borderBottom: '1px solid #d1fae5',
                        }}
                      >
                        <span
                          style={{
                            color: f.is_nota_credito ? '#dc2626' : '#065f46',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                          }}
                        >
                          {f.numero} - {f.fornitore}
                          {f.is_nota_credito && (
                            <span
                              style={{
                                fontSize: 9,
                                fontWeight: 700,
                                padding: '1px 5px',
                                borderRadius: 3,
                                background: '#fee2e2',
                                color: '#dc2626',
                              }}
                            >
                              NC
                            </span>
                          )}
                        </span>
                        <span
                          style={{
                            fontWeight: 'bold',
                            color: f.is_nota_credito ? '#dc2626' : '#047857',
                          }}
                        >
                          {f.is_nota_credito ? '- ' : ''}
                          {formatEuro(Math.abs(f.importo))}
                        </span>
                      </div>
                    ))}
                    <div
                      style={{
                        marginTop: 12,
                        paddingTop: 12,
                        borderTop: '2px solid #10b981',
                        display: 'flex',
                        justifyContent: 'space-between',
                        fontWeight: 'bold',
                        fontSize: 16,
                      }}
                    >
                      <span>TOTALE FATTURE:</span>
                      <span style={{ color: '#047857' }}>
                        {formatEuro(selectedFatture.reduce((sum, f) => sum + (f.importo || 0), 0))}
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
                            Math.abs(
                              (editingAssegnoForFatture?.importo || 0) -
                                selectedFatture.reduce((sum, f) => sum + (f.importo || 0), 0)
                            ) < 1
                              ? '#10b981'
                              : '#f59e0b',
                        }}
                      >
                        <span>Differenza:</span>
                        <span style={{ fontWeight: 600 }}>
                          {formatEuro(
                            (editingAssegnoForFatture?.importo || 0) -
                              selectedFatture.reduce((sum, f) => sum + (f.importo || 0), 0)
                          )}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Lista Fatture Disponibili */}
              <div style={{ marginBottom: 15 }}>
                <label
                  style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#374151' }}
                >
                  Fatture Disponibili (esclusi pagamenti in contanti)
                </label>

                {loadingFatture ? (
                  <div style={{ padding: 30, textAlign: 'center', color: '#64748b' }}>
                    ⏳ Caricamento...
                  </div>
                ) : fatture.length === 0 ? (
                  <div
                    style={{
                      padding: 30,
                      textAlign: 'center',
                      color: '#64748b',
                      background: '#f8fafc',
                      borderRadius: 8,
                    }}
                  >
                    Nessuna fattura disponibile per assegno
                  </div>
                ) : (
                  <div
                    style={{
                      maxHeight: 280,
                      overflow: 'auto',
                      border: '1px solid #e2e8f0',
                      borderRadius: 8,
                    }}
                  >
                    {fatture.map((f, idx) => {
                      const isSelected = selectedFatture.find(sf => sf.id === f.id);
                      const fornitore = f.supplier_name || f.cedente_denominazione || 'N/A';
                      const tipoDoc = f.tipo_documento || f.document_type || 'TD01';
                      const isNotaCredito = tipoDoc === 'TD04';
                      const importoRaw = parseFloat(f.total_amount || f.importo_totale || 0);
                      // Note credito: importo SEMPRE negativo
                      const importo = isNotaCredito ? -Math.abs(importoRaw) : importoRaw;

                      // Mostra header fornitore quando cambia
                      const prevFornitore =
                        idx > 0
                          ? fatture[idx - 1].supplier_name ||
                            fatture[idx - 1].cedente_denominazione ||
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
                                background: '#f1f5f9',
                                borderBottom: '1px solid #e2e8f0',
                                fontSize: 11,
                                fontWeight: 700,
                                color: '#475569',
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
                              padding: 14,
                              borderBottom: '1px solid #f1f5f9',
                              cursor: 'pointer',
                              background: isSelected
                                ? '#dbeafe'
                                : isNotaCredito
                                  ? '#fef2f2'
                                  : 'white',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              transition: 'background 0.15s',
                              borderLeft: isNotaCredito
                                ? '3px solid #ef4444'
                                : '3px solid transparent',
                            }}
                          >
                            <div>
                              <div
                                style={{
                                  fontWeight: 600,
                                  color: isSelected
                                    ? '#1e40af'
                                    : isNotaCredito
                                      ? '#dc2626'
                                      : '#1e293b',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 6,
                                }}
                              >
                                {isSelected ? '✓ ' : '○ '}
                                {f.invoice_number || f.numero_fattura || 'N/A'}
                                {isNotaCredito && (
                                  <span
                                    style={{
                                      fontSize: 9,
                                      fontWeight: 700,
                                      padding: '2px 6px',
                                      borderRadius: 4,
                                      background: '#fee2e2',
                                      color: '#dc2626',
                                      textTransform: 'uppercase',
                                    }}
                                  >
                                    Nota Credito
                                  </span>
                                )}
                              </div>
                              <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
                                {fornitore} • {formatDateIT(f.invoice_date || f.data_fattura)}
                              </div>
                            </div>
                            <div
                              style={{
                                fontWeight: 'bold',
                                color: isNotaCredito ? '#dc2626' : '#1e3a5f',
                                fontSize: 15,
                              }}
                            >
                              {isNotaCredito ? '- ' : ''}
                              {formatEuro(Math.abs(importo))}
                            </div>
                          </div>
                        </React.Fragment>
                      );
                    })}
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 8 }}>
                <button
                  onClick={() => {
                    setShowFattureModal(false);
                    setSelectedFatture([]);
                    setModalPosition({ x: 0, y: 0 });
                  }}
                  style={{
                    padding: '10px 20px',
                    background: '#64748b',
                    color: 'white',
                    border: 'none',
                    borderRadius: 8,
                    cursor: 'pointer',
                  }}
                >
                  Annulla
                </button>
                <button
                  onClick={saveFattureCollegate}
                  disabled={selectedFatture.length === 0}
                  data-testid="salva-fatture-btn"
                  style={{
                    padding: '10px 24px',
                    background: selectedFatture.length > 0 ? '#10b981' : '#9ca3af',
                    color: 'white',
                    border: 'none',
                    borderRadius: 8,
                    cursor: selectedFatture.length > 0 ? 'pointer' : 'not-allowed',
                    fontWeight: 'bold',
                  }}
                >
                  ✓ Collega {selectedFatture.length} Fattur
                  {selectedFatture.length === 1 ? 'a' : 'e'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
