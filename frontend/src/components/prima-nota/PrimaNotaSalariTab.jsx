/**
 * Tab Prima Nota Salari - Componente ottimizzato
 * Usa Zustand per state management e componenti memoizzati
 */
import React, { memo, useCallback, useState, useEffect } from 'react';
import { usePrimaNotaStore } from '../../stores/primaNotaStore';
import {
  YearExclusionButtons,
  SummaryCard,
  PeriodFilters,
  ActionButtons,
  VirtualizedSalariTable,
  AggiustamentoModal,
  ImportResultAlert,
} from './PrimaNotaComponents';
import api from '../../api';
import { toast } from 'sonner';

const PrimaNotaSalariTab = memo(function PrimaNotaSalariTab() {
  // Zustand store
  const {
    salariMovimenti,
    dipendentiLista,
    loading,
    importing,
    importResult,
    anniEsclusi,
    filtroDipendente,
    selectedMonth,
    selectedYear,
    setFiltroDipendente,
    setSelectedMonth,
    setSelectedYear,
    toggleAnnoEscluso,
    resetAnniEsclusi,
    fetchSalari,
    fetchDipendentiLista,
    importPaghe,
    importBonifici,
    clearImportResult,
    deleteRecord,
    resetAllData,
  } = usePrimaNotaStore();

  // Local state for modal
  const [showAggiustamentoModal, setShowAggiustamentoModal] = useState(false);

  // Stato per auto-riparazione
  const [autoRepairStatus, setAutoRepairStatus] = useState(null);
  const [autoRepairRunning, setAutoRepairRunning] = useState(false);

  /**
   * LOGICA INTELLIGENTE: Esegue auto-riparazione dei dati.
   * DISABILITATA: Spostata in Admin per performance. Chiamare manualmente se necessario.
   */
  const eseguiAutoRiparazione = useCallback(async () => {
    setAutoRepairRunning(true);
    try {
      const res = await api.post('/api/prima-nota/salari/auto-ricostruisci-dati');
      if (res.data.righe_pulite > 0 || res.data.correzioni > 0) {
        console.log('🔧 Auto-riparazione salari completata:', res.data);
        setAutoRepairStatus(res.data);
        fetchSalari();
      }
    } catch (error) {
      console.warn('Auto-riparazione salari non riuscita:', error);
    } finally {
      setAutoRepairRunning(false);
    }
  }, [fetchSalari]);

  // Load data on mount and when filters change
  useEffect(() => {
    // RIMOSSO per performance - eseguiAutoRiparazione() ora solo manuale
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchSalari();
    fetchDipendentiLista();
  }, [selectedYear, selectedMonth, filtroDipendente, fetchSalari, fetchDipendentiLista]);

  // Computed: filtered data (excludes selected years)
  const filteredData = React.useMemo(() => {
    return salariMovimenti.filter(m => !anniEsclusi.includes(m.anno));
  }, [salariMovimenti, anniEsclusi]);

  // Computed: righe vuote (busta e bonifico entrambi 0 o null)
  const righeVuote = React.useMemo(() => {
    return salariMovimenti.filter(
      m =>
        (!m.importo_busta || m.importo_busta === 0) &&
        (!m.importo_bonifico || m.importo_bonifico === 0)
    ).length;
  }, [salariMovimenti]);

  // Computed: totals
  const totals = React.useMemo(() => {
    return {
      records: filteredData.length,
      totalRecords: salariMovimenti.length,
      totaleBuste: filteredData.reduce((sum, m) => sum + (m.importo_busta || 0), 0),
      totaleBonifici: filteredData.reduce((sum, m) => sum + (m.importo_bonifico || 0), 0),
      differenza: filteredData.reduce(
        (sum, m) => sum + (m.importo_bonifico || 0) - (m.importo_busta || 0),
        0
      ),
      righeVuote,
    };
  }, [filteredData, salariMovimenti.length, righeVuote]);

  // Handlers with useCallback for stable references
  const handleToggleAnno = useCallback(
    async anno => {
      toggleAnnoEscluso(anno);
      // Ricalcola progressivi dopo toggle
      try {
        const nuoviAnni = anniEsclusi.includes(anno)
          ? anniEsclusi.filter(a => a !== anno)
          : [...anniEsclusi, anno];

        const params = new URLSearchParams();
        params.append('force_reset', 'true');
        if (nuoviAnni.length > 0) {
          params.append('anni_esclusi', nuoviAnni.join(','));
        }
        if (filtroDipendente) {
          params.append('dipendente', filtroDipendente);
        }
        await api.post(`/api/prima-nota-salari/ricalcola-progressivi?${params.toString()}`);
        await fetchSalari();
      } catch (err) {
        console.error('Errore ricalcolo:', err);
      }
    },
    [anniEsclusi, filtroDipendente, toggleAnnoEscluso, fetchSalari]
  );

  const handleResetAnni = useCallback(async () => {
    resetAnniEsclusi();
    try {
      const params = new URLSearchParams();
      params.append('force_reset', 'true');
      if (filtroDipendente) {
        params.append('dipendente', filtroDipendente);
      }
      await api.post(`/api/prima-nota-salari/ricalcola-progressivi?${params.toString()}`);
      await fetchSalari();
    } catch (err) {
      console.error('Errore ricalcolo:', err);
    }
  }, [filtroDipendente, resetAnniEsclusi, fetchSalari]);

  const handleImportPaghe = useCallback(
    async file => {
      await importPaghe(file);
    },
    [importPaghe]
  );

  const handleImportBonifici = useCallback(
    async file => {
      await importBonifici(file);
    },
    [importBonifici]
  );

  const handleExport = useCallback(async () => {
    try {
      let url = `/api/prima-nota-salari/export-excel?`;
      const params = [];
      if (selectedYear) params.push(`anno=${selectedYear}`);
      if (selectedMonth) params.push(`mese=${selectedMonth}`);
      url += params.join('&');

      const response = await api.get(url, { responseType: 'blob' });
      const blob = new Blob([response.data]);
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      const filename = selectedYear
        ? `prima_nota_salari_${selectedYear}.xlsx`
        : 'prima_nota_salari_tutti.xlsx';
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      toast.error('Errore export: ' + (error.response?.data?.detail || error.message));
    }
  }, [selectedYear, selectedMonth]);

  const handleReset = useCallback(async () => {
    const success = await resetAllData();
    if (success) toast.success('Dati eliminati');
  }, [resetAllData]);

  const handlePulisciVuote = useCallback(async () => {
    try {
      const res = await api.delete('/api/prima-nota-salari/pulisci-righe-vuote');
      toast.success(`Eliminate ${res.data.righe_eliminate} righe vuote`);
      await fetchSalari();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  }, [righeVuote, fetchSalari]);

  const handleDelete = useCallback(
    async recordId => {
      await deleteRecord(recordId);
    },
    [deleteRecord]
  );

  const handleAggiustamento = useCallback(
    async formData => {
      try {
        const importo = parseFloat(formData.importo);
        const payload = {
          dipendente: formData.dipendente,
          anno: parseInt(formData.anno),
          mese: parseInt(formData.mese),
          importo_busta: importo < 0 ? Math.abs(importo) : 0,
          importo_bonifico: importo > 0 ? importo : 0,
          descrizione: formData.descrizione || 'Aggiustamento saldo',
        };
        await api.post('/api/prima-nota-salari/salari/aggiustamento', payload);
        await fetchSalari();
        toast.success('Aggiustamento inserito');
        return true;
      } catch (error) {
        toast.error('Errore: ' + (error.response?.data?.detail || error.message));
        return false;
      }
    },
    [fetchSalari]
  );

  return (
    <>
      {/* Filtri periodo */}
      <PeriodFilters
        selectedMonth={selectedMonth}
        selectedYear={selectedYear}
        filtroDipendente={filtroDipendente}
        dipendentiLista={dipendentiLista}
        onChangeMonth={setSelectedMonth}
        onChangeYear={setSelectedYear}
        onChangeDipendente={setFiltroDipendente}
      />

      {/* Bottoni esclusione anni */}
      <YearExclusionButtons
        anniEsclusi={anniEsclusi}
        onToggleAnno={handleToggleAnno}
        onReset={handleResetAnni}
      />

      {/* Bottoni azioni */}
      <ActionButtons
        importing={importing}
        onImportPaghe={handleImportPaghe}
        onImportBonifici={handleImportBonifici}
        onExport={handleExport}
        onReset={handleReset}
        onRefresh={fetchSalari}
        onPulisciVuote={handlePulisciVuote}
        hasData={salariMovimenti.length > 0}
        righeVuote={righeVuote}
      />

      {/* Alert risultato import */}
      <ImportResultAlert result={importResult} onClose={clearImportResult} />

      {/* Card riepilogo */}
      <SummaryCard
        totals={totals}
        anniEsclusi={anniEsclusi}
        selectedMonth={selectedMonth}
        selectedYear={selectedYear}
        filtroDipendente={filtroDipendente}
        onOpenAggiustamento={() => setShowAggiustamentoModal(true)}
      />

      {/* Tabella virtualizzata */}
      <VirtualizedSalariTable
        data={filteredData}
        loading={loading}
        onDelete={handleDelete}
        onEdit={() => {}}
        height={450}
      />

      {/* Modal aggiustamento */}
      <AggiustamentoModal
        isOpen={showAggiustamentoModal}
        onClose={() => setShowAggiustamentoModal(false)}
        onSubmit={handleAggiustamento}
        dipendentiLista={dipendentiLista}
      />
    </>
  );
});

export default PrimaNotaSalariTab;
