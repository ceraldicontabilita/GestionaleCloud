import React, { useState, useEffect, useRef } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';

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
  // La pagina è responsive e funziona sia su desktop che mobile
  return <PrimaNotaDesktop />;
}

/**
 * CassaRebuildBar - Toolbar per ricostruire Prima Nota Cassa dai corrispettivi.
 * Logica: DARE = totale (con IVA), AVERE = pagato_elettronico (POS → banca)
 */
function CassaRebuildBar({ selectedYear, onRebuild }) {
  const [loading, setLoading] = React.useState(false);
  const [lastResult, setLastResult] = React.useState(null);

  const handleRebuild = async (tuttiAnni = false) => {
    const msg = tuttiAnni
      ? `⚠️ Ricostruisce TUTTI gli anni della Prima Nota Cassa.\nI pagamenti fornitori manuali vengono preservati.\n\nContinuare?`
      : `⚠️ Ricostruisce Prima Nota Cassa per l'anno ${selectedYear}.\nI movimenti corrispettivi/POS esistenti verranno sostituiti.\n\nContinuare?`;
    if (!window.confirm(msg)) return;

    setLoading(true);
    setLastResult(null);
    try {
      const params = tuttiAnni ? {} : { anno: selectedYear };
      const res = await api.post('/api/prima-nota/cassa/rebuild-da-corrispettivi', null, { params });
      const d = res.data;
      setLastResult(d);
      alert(
        `✅ ${d.message}\n\nAnno: ${d.anno}\nCorrispettivi processati: ${d.corrispettivi_processati}\nRighe inserite: ${d.righe_inserite}\n\nDAR€ (Ricavi lordi): €${d.totale_dare?.toLocaleString('it-IT', {minimumFractionDigits: 2})}\nAVERE (POS → Banca): €${d.totale_avere?.toLocaleString('it-IT', {minimumFractionDigits: 2})}\nSALDO CASSA: €${d.saldo_cassa?.toLocaleString('it-IT', {minimumFractionDigits: 2})}`
      );
      onRebuild();
    } catch (err) {
      alert('Errore: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      background: '#f0fdf4', border: '1px solid #86efac',
      borderRadius: 10, padding: '10px 14px', marginBottom: 14,
      display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap'
    }}>
      <div style={{ fontSize: 12, color: '#15803d', fontWeight: 600 }}>
        📊 Prima Nota Cassa — Logica:
        <span style={{ fontWeight: 400 }}>
          {' '}DARE = Totale corrispettivo (IVA inclusa) | AVERE = POS/Elettronico (→ Banca)
          | Saldo = Contanti in cassa
        </span>
      </div>
      <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
        <button
          data-testid="btn-rebuild-cassa-anno"
          onClick={() => handleRebuild(false)}
          disabled={loading}
          style={{
            padding: '7px 14px', background: loading ? '#9ca3af' : '#16a34a',
            color: 'white', border: 'none', borderRadius: 7,
            cursor: loading ? 'not-allowed' : 'pointer', fontWeight: 600, fontSize: 12
          }}
        >
          {loading ? '...' : `🔄 Ricostruisci ${selectedYear}`}
        </button>
        <button
          data-testid="btn-rebuild-cassa-tutti"
          onClick={() => handleRebuild(true)}
          disabled={loading}
          style={{
            padding: '7px 14px', background: loading ? '#9ca3af' : '#dc2626',
            color: 'white', border: 'none', borderRadius: 7,
            cursor: loading ? 'not-allowed' : 'pointer', fontWeight: 600, fontSize: 12
          }}
        >
          {loading ? '...' : '🗑️ Ricostruisci Tutti gli Anni'}
        </button>
      </div>
    </div>
  );
}


function PrimaNotaDesktop() {
  const { anno: selectedYear } = useAnnoGlobale();
  const currentYear = new Date().getFullYear();
  
  // Data default: se anno globale = anno corrente usa oggi, altrimenti usa 1 gennaio dell'anno selezionato
  const getDefaultDate = (year) => {
    if (year === currentYear) return new Date().toISOString().split('T')[0];
    return `${year}-01-01`;
  };
  const today = getDefaultDate(selectedYear);
  
  // Anno selezionato viene dal context globale
  const [_availableYears, setAvailableYears] = useState([currentYear]);
  
  // Sezione attiva
  const [activeSection, setActiveSection] = useState('cassa');
  
  // Data state
  const [cassaData, setCassaData] = useState({ movimenti: [], saldo: 0, totale_entrate: 0, totale_uscite: 0 });
  const [bancaData, setBancaData] = useState({ movimenti: [], saldo: 0, totale_entrate: 0, totale_uscite: 0 });
  const [loading, setLoading] = useState(true);
  
  // Filters - ora basati su mese (null = tutti i mesi)
  const [selectedMonth, setSelectedMonth] = useState(null);
  
  // Quick entry forms - CASSA
  const [corrispettivo, setCorrispettivo] = useState({ data: today, importo: '' });
  const [pos, setPos] = useState({ data: today, pos1: '', pos2: '', pos3: '' });
  const [versamento, setVersamento] = useState({ data: today, importo: '' });
  const [movimento, setMovimento] = useState({ data: today, tipo: 'uscita', importo: '', descrizione: '' });
  
  // Saving states
  const [savingCorrisp, setSavingCorrisp] = useState(false);
  const [savingPos, setSavingPos] = useState(false);
  const [savingVers, setSavingVers] = useState(false);
  const [savingMov, setSavingMov] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [importingCSV, setImportingCSV] = useState(false);
  const cassaCSVRef = useRef(null);
  const bancaCSVRef = useRef(null);

  // Nomi mesi
  const mesiNomi = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

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

      const [cassaRes, estrattoContoRes] = await Promise.all([
        api.get(`/api/prima-nota/cassa?${params}`),
        api.get(`/api/estratto-conto-movimenti/movimenti?${ecParams}`)
      ]);

      setCassaData(cassaRes.data);
      
      // Trasforma i dati dell'estratto conto nel formato della Prima Nota Banca
      const ecData = estrattoContoRes.data;
      const movimenti = (ecData.movimenti || []).map(m => ({
        ...m,
        tipo: m.tipo || (m.importo >= 0 ? 'entrata' : 'uscita'),
        importo: Math.abs(m.importo || 0),
        descrizione: m.descrizione || m.descrizione_originale || '',
        categoria: m.categoria || 'Movimento bancario',
        fattura_id: m.fattura_id || m.dettagli_riconciliazione?.fattura_id || null,
        bonifico_pdf_id: m.bonifico_pdf_id || null
      }));
      
      const saldoPrec = ecData.saldo_precedente || 0;
      const saldoAnno = (ecData.totale_entrate || 0) - (ecData.totale_uscite || 0);
      setBancaData({
        movimenti: movimenti,
        saldo: ecData.saldo || saldoPrec + saldoAnno,
        saldo_anno: ecData.saldo_anno || saldoAnno,
        saldo_precedente: saldoPrec,
        totale_entrate: ecData.totale_entrate || 0,
        totale_uscite: ecData.totale_uscite || 0,
        count: ecData.totale || movimenti.length
      });
      
      // Aggiorna anni disponibili dopo caricamento
      loadAvailableYears();
    } catch (error) {
      console.error('Error loading prima nota:', error);
    } finally {
      setLoading(false);
    }
  };

  // Sincronizza fatture pagate con Prima Nota
  const handleSyncFatture = async () => {
    
    
    setSyncing(true);
    try {
      const res = await api.post(`/api/prima-nota/cassa/sync-fatture-pagate?anno=${selectedYear}`);
      alert(`${res.data.message}\nCassa: € ${res.data.totale_cassa?.toLocaleString('it-IT') || 0}\nBanca: € ${res.data.totale_banca?.toLocaleString('it-IT') || 0}`);
      loadAllData();
    } catch (error) {
      alert('Errore sincronizzazione: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSyncing(false);
    }
  };

  // Import CSV Prima Nota Cassa
  // === I movimenti di cassa si inseriscono manualmente (corrispettivi, POS, versamenti) ===
  // === L'estratto conto bancario si importa dalla sezione Estratto Conto ===

  // Import CSV estratto conto (aggiornamento incrementale - salta duplicati)
  const handleImportCSVBanca = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setImportingCSV(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post("/api/estratto-conto-movimenti/import", formData);
      const msg = `${res.data.message}\nInseriti: ${res.data.movimenti_importati || res.data.inseriti || 0}\nDuplicati saltati: ${res.data.duplicati_saltati || 0}`;
      alert(msg);
      loadAllData();
    } catch (error) {
      alert('Errore import: ' + (error.response?.data?.detail || error.message));
    } finally {
      setImportingCSV(false);
      if (bancaCSVRef.current) bancaCSVRef.current.value = "";
    }
  };

  // FORZA REIMPORT: cancella anni del CSV e reinserisce tutto (per correggere saldo)
  const bancaForceReimportRef = useRef(null);
  const [forceReimporting, setForceReimporting] = useState(false);
  
  const handleForceReimportBanca = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    if (!window.confirm('⚠️ ATTENZIONE: Questa operazione cancellerà tutti i movimenti degli anni presenti nel CSV e li reinserirà completamente (incluse commissioni duplicate).\n\nContinuare?')) {
      if (bancaForceReimportRef.current) bancaForceReimportRef.current.value = "";
      return;
    }
    
    setForceReimporting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post("/api/estratto-conto-movimenti/force-reimport", formData);
      const d = res.data;
      alert(`✅ ${d.message}\n\nAnni aggiornati: ${d.anni_aggiornati?.join(', ')}\nRecord cancellati: ${d.record_cancellati}\nMovimenti importati: ${d.movimenti_importati}\n\nEntrate: € ${d.totale_entrate?.toLocaleString('it-IT')}\nUscite: € ${d.totale_uscite?.toLocaleString('it-IT')}\nSaldo: € ${d.saldo?.toLocaleString('it-IT')}`);
      loadAllData();
    } catch (error) {
      alert('Errore reimport: ' + (error.response?.data?.detail || error.message));
    } finally {
      setForceReimporting(false);
      if (bancaForceReimportRef.current) bancaForceReimportRef.current.value = "";
    }
  };

  // Download template CSV
  const handleDownloadTemplate = async (tipo) => {
    try {
      const res = await api.get(`/api/prima-nota/${tipo}/template-csv`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `template_prima_nota_${tipo}.csv`;
      a.click();
    } catch (error) {
      alert('Errore download: ' + (error.response?.data?.detail || error.message));
    }
  };

  // === SAVE HANDLERS CASSA ===
  
  // Corrispettivo (DARE/Entrata) - Importo al LORDO IVA
  // NOTA: Questo è un dato PROVVISORIO per vedere il saldo cassa.
  // Quando arriva l'XML dei corrispettivi, questo verrà SOVRASCRITTO.
  const handleSaveCorrispettivo = async () => {
    if (!corrispettivo.importo) return alert('Inserisci importo');
    if (corrispettivo.data && !corrispettivo.data.startsWith(selectedYear.toString())) {
      if (!confirm(`⚠️ La data ${corrispettivo.data} non è dell'anno ${selectedYear}. Continuare?`)) return;
    }
    setSavingCorrisp(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: corrispettivo.data,
        tipo: 'entrata',  // DARE
        importo: parseFloat(corrispettivo.importo),
        descrizione: `Corrispettivo giornaliero ${corrispettivo.data} (provvisorio)`,
        categoria: 'Corrispettivi',
        source: 'manual_entry',
        provvisorio: true  // Sarà sovrascritto quando arriva XML
      });
      setCorrispettivo({ data: today, importo: '' });
      loadAllData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSavingCorrisp(false);
    }
  };

  // POS (AVERE/Uscita) - Escono dalla cassa - Campo unificato
  // NOTA: Questo è un dato PROVVISORIO per vedere il saldo cassa.
  // Quando arriva l'XML dei corrispettivi, questo verrà SOVRASCRITTO.
  const handleSavePos = async () => {
    const totale = parseFloat(pos.pos1) || 0;
    if (totale === 0) return alert('Inserisci importo POS');
    if (pos.data && !pos.data.startsWith(selectedYear.toString())) {
      if (!confirm(`⚠️ La data ${pos.data} non è dell'anno ${selectedYear}. Continuare?`)) return;
    }
    setSavingPos(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: pos.data,
        tipo: 'uscita',  // AVERE - escono dalla cassa
        importo: totale,
        descrizione: `POS giornaliero ${pos.data} (provvisorio)`,
        categoria: 'POS',
        source: 'manual_pos',
        provvisorio: true  // Sarà sovrascritto quando arriva XML
      });
      setPos({ data: today, pos1: '', pos2: '', pos3: '' });
      loadAllData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSavingPos(false);
    }
  };

  // Versamento (AVERE/Uscita da cassa)
  const handleSaveVersamento = async () => {
    if (!versamento.importo) return alert('Inserisci importo');
    if (versamento.data && !versamento.data.startsWith(selectedYear.toString())) {
      if (!confirm(`⚠️ La data ${versamento.data} non è dell'anno ${selectedYear}. Continuare?`)) return;
    }
    setSavingVers(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: versamento.data,
        tipo: 'uscita',  // AVERE
        importo: parseFloat(versamento.importo),
        descrizione: `Versamento in banca ${versamento.data}`,
        categoria: 'Versamento',
        source: 'manual_entry'
      });
      setVersamento({ data: today, importo: '' });
      loadAllData();
      alert('✅ Versamento salvato!');
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSavingVers(false);
    }
  };

  // Movimento generico
  const handleSaveMovimento = async () => {
    if (!movimento.importo || !movimento.descrizione) return alert('Compila tutti i campi');
    if (movimento.data && !movimento.data.startsWith(selectedYear.toString())) {
      if (!confirm(`⚠️ La data ${movimento.data} non è dell'anno ${selectedYear}. Continuare?`)) return;
    }
    setSavingMov(true);
    try {
      await api.post('/api/prima-nota/cassa', {
        data: movimento.data,
        tipo: movimento.tipo,
        importo: parseFloat(movimento.importo),
        descrizione: movimento.descrizione,
        categoria: movimento.tipo === 'entrata' ? 'Incasso' : 'Spese',
        source: 'manual_entry'
      });
      setMovimento({ data: today, tipo: 'uscita', importo: '', descrizione: '' });
      loadAllData();
      alert('✅ Movimento salvato!');
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSavingMov(false);
    }
  };

  const handleDeleteMovimento = async (tipo, id) => {
    try {
      await api.delete(`/api/prima-nota/${tipo}/${id}`);
      loadAllData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
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
        a: a
      });
      loadAllData();
      // Feedback visivo opzionale
      if (res.data.fattura_aggiornata) {
        console.log(`Fattura ${res.data.fattura_id} aggiornata con nuovo metodo`);
      }
    } catch (error) {
      alert('Errore spostamento: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Format helpers
  const formatDate = (dateStr) => formatDateIT(dateStr);
  
  const posTotale = (parseFloat(pos.pos1) || 0) + (parseFloat(pos.pos2) || 0) + (parseFloat(pos.pos3) || 0);

  // Calculate category totals for Cassa
  const totalePOS = cassaData.movimenti?.filter(m => m.categoria === 'POS').reduce((s, m) => s + m.importo, 0) || 0;
  const totaleVersamenti = cassaData.movimenti?.filter(m => m.categoria === 'Versamento').reduce((s, m) => s + m.importo, 0) || 0;
  const totaleFattureCassa = cassaData.movimenti?.filter(m => m.categoria === 'Pagamento fornitore').reduce((s, m) => s + m.importo, 0) || 0;
  const totaleCorrispettivi = cassaData.movimenti?.filter(m => m.categoria === 'Corrispettivi').reduce((s, m) => s + m.importo, 0) || 0;

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
    boxSizing: 'border-box'
  };

  // eslint-disable-next-line no-unused-vars
  const buttonStyle = (color, disabled) => button(color === COLORS.success ? 'primary' : 'secondary', disabled);

  const buttonStyleCompact = (color, disabled) => ({
    padding: '6px 12px',
    background: disabled ? '#ccc' : color,
    color: 'white',
    border: 'none',
    borderRadius: 6,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontWeight: 'bold',
    fontSize: 12,
    width: '100%'
  });

  return (
    <div style={{...STYLES.page, padding: 0}}>
      
      {/* HEADER COMPATTO */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 16px',
        background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
        borderRadius: 8,
        marginBottom: 12
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ 
            padding: '6px 14px',
            fontSize: 14,
            fontWeight: 'bold',
            borderRadius: 6,
            background: 'rgba(255,255,255,0.9)',
            color: COLORS.primary,
          }}>
            📅 Anno: {selectedYear}
          </span>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={handleSyncFatture}
            disabled={syncing}
            style={{
              padding: '6px 12px',
              background: syncing ? '#999' : '#ff9800',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: syncing ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              fontSize: 12
            }}
            title="Importa fatture pagate in Prima Nota"
          >
            {syncing ? '...' : '📤 Sync Fatture'}
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
              fontWeight: '500'
            }}
          >
            🔄
          </button>
        </div>
      </div>
      
      {/* SECTION BUTTONS - Sticky su mobile */}
      <div style={{ 
        display: 'flex', 
        gap: 8, 
        marginBottom: 16,
        position: 'sticky',
        top: 0,
        zIndex: 100,
        background: '#f9fafb',
        padding: '8px 0'
      }}>
        <button
          data-testid="btn-prima-nota-cassa"
          onClick={() => setActiveSection('cassa')}
          style={{
            flex: 1,
            padding: '12px 16px',
            fontSize: 14,
            fontWeight: 'bold',
            background: activeSection === 'cassa' 
              ? 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)' 
              : '#f3f4f6',
            color: activeSection === 'cassa' ? 'white' : '#374151',
            border: 'none',
            borderRadius: 10,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            boxShadow: activeSection === 'cassa' ? '0 4px 15px rgba(79, 70, 229, 0.4)' : 'none'
          }}
        >
          <span style={{ fontSize: 18 }}>💵</span>
          CASSA {selectedYear}
        </button>
        
        <button
          data-testid="btn-prima-nota-banca"
          onClick={() => setActiveSection('banca')}
          style={{
            flex: 1,
            padding: '12px 16px',
            fontSize: 14,
            fontWeight: 'bold',
            background: activeSection === 'banca' 
              ? 'linear-gradient(135deg, #1e3a5f 0%, #1d4ed8 100%)' 
              : '#f3f4f6',
            color: activeSection === 'banca' ? 'white' : '#374151',
            border: 'none',
            borderRadius: 10,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            boxShadow: activeSection === 'banca' ? '0 4px 15px rgba(37, 99, 235, 0.4)' : 'none'
          }}
        >
          <span style={{ fontSize: 18 }}>🏦</span>
          BANCA {selectedYear}
        </button>
      </div>

      {/* ========== SEZIONE CASSA ========== */}
      {activeSection === 'cassa' && (
        <section>
          {/* Summary Cards Cassa - Compatti */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 16 }}>
            <MiniCard title={`Entrate (DARE) ${selectedYear}`} value={formatEuro(cassaData.totale_entrate)} color="#4caf50" />
            <MiniCard title={`Uscite (AVERE) ${selectedYear}`} value={formatEuro(cassaData.totale_uscite)} color="#ef4444" />
            <MiniCard title={`Saldo ${selectedYear}`} value={formatEuro(cassaData.saldo_anno || (cassaData.totale_entrate - cassaData.totale_uscite))} color={(cassaData.saldo_anno || (cassaData.totale_entrate - cassaData.totale_uscite)) >= 0 ? '#4caf50' : '#ef4444'} highlight />
            {cassaData.saldo_precedente !== 0 && cassaData.saldo_precedente !== undefined && (
              <MiniCard title="Riporto Anni Prec." value={formatEuro(cassaData.saldo_precedente)} color="#6b7280" />
            )}
            {cassaData.saldo_precedente !== 0 && cassaData.saldo_precedente !== undefined && (
              <MiniCard title="Saldo Cumulativo" value={formatEuro(cassaData.saldo)} color="#1e3a5f" highlight />
            )}
          </div>

          {/* Logica Corrispettivi - Toolbar Ricostruzione */}
          <CassaRebuildBar selectedYear={selectedYear} onRebuild={loadAllData} />

          {/* Dettaglio - Compatto */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8, marginBottom: 16 }}>
            <TinyStatCard title="Corrispettivi" value={formatEuro(totaleCorrispettivi)} color="#ff9800" />
            <TinyStatCard title="POS" value={formatEuro(totalePOS)} color="#1e3a5f" />
            <TinyStatCard title="Versamenti" value={formatEuro(totaleVersamenti)} color="#4caf50" />
            <TinyStatCard title="Fatture" value={formatEuro(totaleFattureCassa)} color="#ef4444" />
          </div>

          {/* Chiusure Giornaliere - Menu Compatto a Tendina */}
          <div style={{ background: '#f8fafc', borderRadius: 10, padding: 12, marginBottom: 16, border: '1px solid #e2e8f0' }}>
            <details style={{ cursor: 'pointer' }}>
              <summary style={{ 
                fontSize: 14, 
                fontWeight: 'bold', 
                display: 'flex', 
                alignItems: 'center', 
                gap: 8,
                padding: '4px 0',
                userSelect: 'none'
              }}>
                <span>⚡</span> Chiusure Giornaliere
                <span style={{ 
                  marginLeft: 'auto', 
                  fontSize: 11, 
                  background: '#dbeafe', 
                  color: '#1d4ed8', 
                  padding: '2px 8px', 
                  borderRadius: 4 
                }}>
                  Clicca per espandere
                </span>
              </summary>
              
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginTop: 12 }}>
                {/* Corrispettivo - Ultra compatto */}
                <div style={{ background: 'white', borderRadius: 8, padding: 10, borderLeft: '3px solid #ff9800' }}>
                  <div style={{ fontSize: 11, fontWeight: 'bold', color: '#92400e', marginBottom: 6 }}>📊 Corrispettivo</div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <input type="date" value={corrispettivo.data} onChange={(e) => setCorrispettivo({...corrispettivo, data: e.target.value})} style={{ ...inputStyleCompact, flex: 1, padding: '4px 6px', fontSize: 11 }} />
                    <input type="number" step="0.01" placeholder="€" value={corrispettivo.importo} onChange={(e) => setCorrispettivo({...corrispettivo, importo: e.target.value})} style={{ ...inputStyleCompact, width: 70, padding: '4px 6px', fontSize: 11 }} />
                    <button onClick={handleSaveCorrispettivo} disabled={savingCorrisp} style={{ ...buttonStyleCompact('#92400e', savingCorrisp), padding: '4px 8px', minWidth: 32 }}>
                      {savingCorrisp ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>

                {/* POS - Ultra compatto */}
                <div style={{ background: 'white', borderRadius: 8, padding: 10, borderLeft: '3px solid #1e3a5f' }}>
                  <div style={{ fontSize: 11, fontWeight: 'bold', color: '#1d4ed8', marginBottom: 6 }}>💳 POS</div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <input type="date" value={pos.data} onChange={(e) => setPos({...pos, data: e.target.value})} style={{ ...inputStyleCompact, flex: 1, padding: '4px 6px', fontSize: 11 }} />
                    <input type="number" step="0.01" placeholder="€" value={pos.pos1} onChange={(e) => setPos({...pos, pos1: e.target.value, pos2: '', pos3: ''})} style={{ ...inputStyleCompact, width: 70, padding: '4px 6px', fontSize: 11 }} />
                    <button onClick={handleSavePos} disabled={savingPos} style={{ ...buttonStyleCompact('#1d4ed8', savingPos), padding: '4px 8px', minWidth: 32 }}>
                      {savingPos ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>

                {/* Versamento - Ultra compatto */}
                <div style={{ background: 'white', borderRadius: 8, padding: 10, borderLeft: '3px solid #4caf50' }}>
                  <div style={{ fontSize: 11, fontWeight: 'bold', color: '#059669', marginBottom: 6 }}>🏦 Versamento</div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <input type="date" value={versamento.data} onChange={(e) => setVersamento({...versamento, data: e.target.value})} style={{ ...inputStyleCompact, flex: 1, padding: '4px 6px', fontSize: 11 }} />
                    <input type="number" step="0.01" placeholder="€" value={versamento.importo} onChange={(e) => setVersamento({...versamento, importo: e.target.value})} style={{ ...inputStyleCompact, width: 70, padding: '4px 6px', fontSize: 11 }} />
                    <button onClick={handleSaveVersamento} disabled={savingVers} style={{ ...buttonStyleCompact('#059669', savingVers), padding: '4px 8px', minWidth: 32 }}>
                      {savingVers ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>

                {/* Movimento Altro - Ultra compatto */}
                <div style={{ background: 'white', borderRadius: 8, padding: 10, borderLeft: '3px solid #f97316' }}>
                  <div style={{ fontSize: 11, fontWeight: 'bold', color: '#ea580c', marginBottom: 6 }}>✏️ Altro</div>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    <input type="date" value={movimento.data} onChange={(e) => setMovimento({...movimento, data: e.target.value})} style={{ ...inputStyleCompact, width: 100, padding: '4px 6px', fontSize: 11 }} />
                    <select value={movimento.tipo} onChange={(e) => setMovimento({...movimento, tipo: e.target.value})} style={{ ...inputStyleCompact, width: 60, padding: '4px 4px', fontSize: 10 }}>
                      <option value="uscita">-</option>
                      <option value="entrata">+</option>
                    </select>
                    <input type="number" step="0.01" placeholder="€" value={movimento.importo} onChange={(e) => setMovimento({...movimento, importo: e.target.value})} style={{ ...inputStyleCompact, width: 60, padding: '4px 6px', fontSize: 11 }} />
                    <input type="text" placeholder="Desc." value={movimento.descrizione} onChange={(e) => setMovimento({...movimento, descrizione: e.target.value})} style={{ ...inputStyleCompact, flex: 1, padding: '4px 6px', fontSize: 11, minWidth: 80 }} />
                    <button onClick={handleSaveMovimento} disabled={savingMov} style={{ ...buttonStyleCompact('#ea580c', savingMov), padding: '4px 8px', minWidth: 32 }}>
                      {savingMov ? '⏳' : '💾'}
                    </button>
                  </div>
                </div>
              </div>
            </details>
          </div>

          {/* Filter - Bottoni Mesi */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: '#6b7280', marginRight: 4 }}>📅 Mese:</span>
            <button 
              onClick={() => setSelectedMonth(null)} 
              style={{ 
                padding: '6px 12px', 
                background: selectedMonth === null ? '#4f46e5' : '#f3f4f6', 
                color: selectedMonth === null ? 'white' : '#374151', 
                border: 'none', 
                borderRadius: 6, 
                cursor: 'pointer', 
                fontSize: 11,
                fontWeight: selectedMonth === null ? 'bold' : 'normal'
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
                  background: selectedMonth === i ? '#4f46e5' : '#f3f4f6', 
                  color: selectedMonth === i ? 'white' : '#374151', 
                  border: 'none', 
                  borderRadius: 6, 
                  cursor: 'pointer', 
                  fontSize: 11,
                  fontWeight: selectedMonth === i ? 'bold' : 'normal'
                }}
              >
                {nome}
              </button>
            ))}
            {giornoRecord && (
              <span style={{ marginLeft: 'auto', fontSize: 11, color: '#92400e', background: '#fef3c7', padding: '4px 8px', borderRadius: 4 }}>
                🏆 Record: {formatDate(giornoRecord.data)} - {formatEuro(giornoRecord.importo)}
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
            onDelete={(id) => handleDeleteMovimento('cassa', id)}
            onEdit={(updated) => handleEditMovimento('cassa', updated)}
            onSposta={handleSpostaMovimento}
            saldoPrecedente={cassaData.saldo_precedente || 0}
          />
        </section>
      )}

      {/* ========== SEZIONE BANCA ========== */}
      {activeSection === 'banca' && (
        <section>
          {/* Summary Cards Banca */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 20 }}>
            <SummaryCard
              title={`Accrediti ${selectedYear}`}
              value={formatEuro(bancaData.totale_entrate)}
              color="#4caf50" icon="📈"
              subtitle="Totale accrediti bancari (POS + bonifici + altro)"
            />
            <SummaryCard
              title={`Pagamenti ${selectedYear}`}
              value={formatEuro(bancaData.totale_uscite)}
              color="#ef4444" icon="📉"
              subtitle="Totale addebiti (fornitori, tasse, stipendi)"
            />
            <SummaryCard
              title={`Saldo Banca ${selectedYear}`}
              value={formatEuro(bancaData.saldo_anno || (bancaData.totale_entrate - bancaData.totale_uscite))}
              color={(bancaData.saldo_anno || (bancaData.totale_entrate - bancaData.totale_uscite)) >= 0 ? '#4caf50' : '#ef4444'}
              icon="📊"
              subtitle={`Accrediti - Pagamenti ${selectedYear}`}
            />
            {bancaData.saldo_precedente !== undefined && bancaData.saldo_precedente !== 0 && bancaData.saldo_precedente > 0 && (
              <SummaryCard title="Saldo Cumulativo" value={formatEuro(bancaData.saldo)} color="#1e3a5f" icon="🏦" subtitle="Saldo totale complessivo" highlight />
            )}
            {bancaData.saldo_precedente !== undefined && bancaData.saldo_precedente !== 0 && bancaData.saldo_precedente > 0 && (
              <SummaryCard title="Riporto Anni Prec." value={formatEuro(bancaData.saldo_precedente)} color="#6b7280" icon="📅" subtitle="Saldo al 31/12 anno prec." />
            )}
          </div>

          {/* Nota banca */}
          <div style={{ background: '#fefce8', border: '1px solid #ca8a04', borderRadius: 10, padding: '10px 16px', marginBottom: 14, fontSize: 13, color: '#854d0e' }}>
            ⚠️ <strong>Nota contabile:</strong> Gli "Accrediti" mostrano tutti i movimenti in entrata sul conto bancario (POS, bonifici, depositi, finanziamenti). <strong>I ricavi reali dell'azienda sono nei Corrispettivi</strong>, visibili nella sezione Cassa. Alcuni accrediti (es. bonifici interni, finanziamenti) non sono ricavi.
          </div>

          {/* Import CSV toolbar */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '10px 14px' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Estratto Conto:</span>
            
            {/* Import incrementale */}
            <input
              ref={bancaCSVRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={handleImportCSVBanca}
              data-testid="input-import-csv-banca"
            />
            <button
              data-testid="btn-import-csv-banca"
              onClick={() => bancaCSVRef.current?.click()}
              disabled={importingCSV}
              style={{
                padding: '7px 14px',
                background: importingCSV ? '#9ca3af' : '#3b82f6',
                color: 'white', border: 'none', borderRadius: 7,
                cursor: importingCSV ? 'not-allowed' : 'pointer',
                fontWeight: 600, fontSize: 12
              }}
              title="Aggiorna incrementalmente: salta movimenti già presenti"
            >
              {importingCSV ? '...' : '📥 Importa CSV'}
            </button>

            {/* Force reimport */}
            <input
              ref={bancaForceReimportRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={handleForceReimportBanca}
              data-testid="input-force-reimport-banca"
            />
            <button
              data-testid="btn-force-reimport-banca"
              onClick={() => bancaForceReimportRef.current?.click()}
              disabled={forceReimporting}
              style={{
                padding: '7px 14px',
                background: forceReimporting ? '#9ca3af' : '#dc2626',
                color: 'white', border: 'none', borderRadius: 7,
                cursor: forceReimporting ? 'not-allowed' : 'pointer',
                fontWeight: 600, fontSize: 12
              }}
              title="Cancella e reimporta completamente gli anni del CSV (mantiene commissioni duplicate)"
            >
              {forceReimporting ? '...' : '🔄 Forza Aggiornamento'}
            </button>

            <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 4 }}>
              <strong>Forza Aggiornamento</strong> = cancella e reimporta gli anni del CSV (corregge saldo e commissioni)
            </span>
          </div>

          {/* Filter - Bottoni Mesi */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, color: '#6b7280', marginRight: 8 }}>📅 Mese:</span>
            <button 
              onClick={() => setSelectedMonth(null)} 
              style={{ 
                padding: '8px 14px', 
                background: selectedMonth === null ? '#1e3a5f' : '#f3f4f6', 
                color: selectedMonth === null ? 'white' : '#374151', 
                border: 'none', 
                borderRadius: 8, 
                cursor: 'pointer', 
                fontWeight: selectedMonth === null ? 'bold' : 'normal'
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
                  background: selectedMonth === i ? '#1e3a5f' : '#f3f4f6', 
                  color: selectedMonth === i ? 'white' : '#374151', 
                  border: 'none', 
                  borderRadius: 8, 
                  cursor: 'pointer', 
                  fontWeight: selectedMonth === i ? 'bold' : 'normal'
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
            onDelete={(id) => handleDeleteMovimento('banca', id)}
            onEdit={(updated) => handleEditMovimento('banca', updated)}
            onSposta={handleSpostaMovimento}
            readOnly={false}
            saldoPrecedente={0}
          />
        </section>
      )}
    </div>
  );
}

// Sub-components

function MiniCard({ title, value, color, highlight }) {
  return (
    <div style={{ 
      background: highlight ? `${color}15` : 'white',
      borderRadius: 8, 
      padding: 10, 
      border: highlight ? `2px solid ${color}` : '1px solid #e5e7eb'
    }}>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 2 }}>{title}</div>
      <div style={{ fontSize: 18, fontWeight: 'bold', color }}>{value}</div>
    </div>
  );
}

function TinyStatCard({ title, value, color }) {
  return (
    <div style={{ background: 'white', borderRadius: 6, padding: 8, border: '1px solid #e5e7eb', borderLeft: `3px solid ${color}` }}>
      <div style={{ fontSize: 10, color: '#6b7280' }}>{title}</div>
      <div style={{ fontSize: 13, fontWeight: 'bold', color }}>{value}</div>
    </div>
  );
}

function CompactEntryCard({ title, color, children }) {
  return (
    <div style={{ 
      background: `${color}10`,
      borderRadius: 8, 
      padding: 10,
      border: `1px solid ${color}30`
    }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 12, fontWeight: 'bold', color }}>{title}</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {children}
      </div>
    </div>
  );
}

function SummaryCard({ title, value, color, icon, highlight, subtitle }) {
  return (
    <div style={{ 
      background: highlight ? `linear-gradient(135deg, ${color}15 0%, ${color}25 100%)` : 'white',
      borderRadius: 12, 
      padding: 16, 
      border: highlight ? `2px solid ${color}` : '1px solid #e5e7eb'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 13, color: '#6b7280' }}>{title}</span>
        <span style={{ fontSize: 18 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 'bold', color }}>{value}</div>
      {subtitle && <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>{subtitle}</div>}
    </div>
  );
}

// eslint-disable-next-line no-unused-vars
function MiniStatCard({ title, value, color }) {
  return (
    <div style={{ background: 'white', borderRadius: 8, padding: 12, border: '1px solid #e5e7eb', borderLeft: `4px solid ${color}` }}>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 16, fontWeight: 'bold', color }}>{value}</div>
    </div>
  );
}

// eslint-disable-next-line no-unused-vars
function QuickEntryCard({ title, color, children }) {
  return (
    <div style={{ 
      background: `linear-gradient(135deg, ${color}20 0%, ${color}10 100%)`,
      borderRadius: 12, 
      padding: 16,
      border: `2px solid ${color}30`
    }}>
      <h4 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 'bold' }}>{title}</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {children}
      </div>
    </div>
  );
}

function MovementsTable({ movimenti, tipo, loading, formatEuro, formatDate, onDelete, onEdit, onSposta, readOnly = false, saldoPrecedente = 0 }) {
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
  
  // Lista categorie uniche
  const categorieUniche = [...new Set(movimenti.map(m => m.categoria).filter(Boolean))].sort();
  
  if (loading) {
    return <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>⏳ Caricamento...</div>;
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
    if (!isNaN(min)) movimentiFiltrati = movimentiFiltrati.filter(m => Math.abs(m.importo || 0) >= min);
  }
  // Filtro importo max
  if (filtroImportoMax !== '') {
    const max = parseFloat(filtroImportoMax);
    if (!isNaN(max)) movimentiFiltrati = movimentiFiltrati.filter(m => Math.abs(m.importo || 0) <= max);
  }

  const totalPages = Math.ceil(movimentiFiltrati.length / itemsPerPage);
  const start = (currentPage - 1) * itemsPerPage;
  const _currentMovimenti = movimentiFiltrati.slice(start, start + itemsPerPage);

  // Calculate running balance using reduce - ordina FORWARD (cronologico ASC) per calcolo corretto
  const saldoIniziale = saldoPrecedente || 0;
  // Crea copia ordinata cronologicamente (ASC) per il calcolo del saldo progressivo
  const movimentiForward = [...movimentiFiltrati].sort((a, b) => (a.data || '').localeCompare(b.data || ''));
  const balanceMap = {};
  movimentiForward.reduce((prevBal, m) => {
    const newBal = m.tipo === 'entrata' ? prevBal + (m.importo || 0) : prevBal - (m.importo || 0);
    balanceMap[m.id || m.data + m.importo] = newBal;
    return newBal;
  }, saldoIniziale);
  // Applica il saldo progressivo ai movimenti nell'ordine originale (DESC per display)
  const movimentiWithBalance = movimentiFiltrati.map(m => ({
    ...m,
    saldoProgressivo: balanceMap[m.id || m.data + m.importo] ?? saldoIniziale
  }));

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
    setCurrentPage(1);
  };

  const hasActiveFilters = filtroDescrizione || filtroCategoria || filtroDareAvere || filtroDataDa || filtroDataA || filtroImportoMin !== '' || filtroImportoMax !== '';

  return (
    <div style={{ background: 'white', borderRadius: 12, overflow: 'hidden', border: '1px solid #e5e7eb' }}>
      {/* Modal Modifica Movimento - solo se non readOnly */}
      {!readOnly && editingMovimento && (
        <EditMovimentoModal
          movimento={editingMovimento}
          tipo={tipo}
          onClose={() => setEditingMovimento(null)}
          onSave={(updated) => {
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
      <div style={{ 
        padding: '12px 16px', 
        background: '#f8fafc', 
        borderBottom: '1px solid #e5e7eb',
      }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontWeight: 600, fontSize: 12, color: '#374151' }}>🔍 Filtri:</span>
          
          {/* Filtro Descrizione */}
          <input
            type="text"
            placeholder="Cerca descrizione..."
            value={filtroDescrizione}
            onChange={(e) => { setFiltroDescrizione(e.target.value); setCurrentPage(1); }}
            style={{ padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12, width: 180 }}
            data-testid="filtro-descrizione"
          />
          
          {/* Filtro Categoria */}
          <select
            value={filtroCategoria}
            onChange={(e) => { setFiltroCategoria(e.target.value); setCurrentPage(1); }}
            style={{ padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12, background: 'white' }}
            data-testid="filtro-categoria"
          >
            <option value="">Tutte le categorie</option>
            {categorieUniche.map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
          
          {/* Filtro DARE/AVERE */}
          <select
            value={filtroDareAvere}
            onChange={(e) => { setFiltroDareAvere(e.target.value); setCurrentPage(1); }}
            style={{ padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12, background: 'white' }}
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
              onChange={(e) => { setFiltroDataDa(e.target.value); setCurrentPage(1); }}
              style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12 }}
              data-testid="filtro-data-da"
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280' }}>A</label>
            <input
              type="date"
              value={filtroDataA}
              onChange={(e) => { setFiltroDataA(e.target.value); setCurrentPage(1); }}
              style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12 }}
              data-testid="filtro-data-a"
            />
          </div>
          
          <span style={{ fontWeight: 600, fontSize: 12, color: '#374151', marginLeft: 8 }}>💶 Importo:</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280' }}>Min €</label>
            <input
              type="number"
              placeholder="0"
              value={filtroImportoMin}
              onChange={(e) => { setFiltroImportoMin(e.target.value); setCurrentPage(1); }}
              style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12, width: 90 }}
              data-testid="filtro-importo-min"
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280' }}>Max €</label>
            <input
              type="number"
              placeholder="∞"
              value={filtroImportoMax}
              onChange={(e) => { setFiltroImportoMax(e.target.value); setCurrentPage(1); }}
              style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12, width: 90 }}
              data-testid="filtro-importo-max"
            />
          </div>
          
          {/* Contatore risultati */}
          <span style={{ fontSize: 12, color: '#6b7280', marginLeft: 8 }}>
            {movimentiFiltrati.length} / {movimenti.length} movimenti
          </span>
          
          {/* Reset Filtri */}
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              style={{ padding: '6px 12px', background: '#ef4444', color: 'white', border: 'none', borderRadius: 6, fontSize: 12, cursor: 'pointer' }}
              data-testid="btn-reset-filtri"
            >
              ✕ Reset filtri
            </button>
          )}
        </div>
      </div>
      
      {/* Pagination Header */}
      {totalPages > 1 && (
        <div style={{ 
          padding: '12px 16px', 
          background: tipo === 'cassa' ? '#4f46e5' : '#1e3a5f', 
          color: 'white',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span>📄 Pagina {currentPage} di {totalPages} ({movimenti.length} movimenti)</span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button onClick={() => setCurrentPage(1)} disabled={currentPage === 1} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === 1 ? 0.5 : 1 }}>⏮️</button>
            <button onClick={() => setCurrentPage(p => Math.max(1, p-1))} disabled={currentPage === 1} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === 1 ? 0.5 : 1 }}>◀️</button>
            <button onClick={() => setCurrentPage(p => Math.min(totalPages, p+1))} disabled={currentPage === totalPages} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === totalPages ? 0.5 : 1 }}>▶️</button>
            <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === totalPages ? 0.5 : 1 }}>⏭️</button>
          </div>
        </div>
      )}

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
              <th style={{ padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11 }}>Data</th>
              <th style={{ padding: '8px 8px', textAlign: 'center', fontWeight: 600, fontSize: 11, width: 40 }}>T</th>
              <th style={{ padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11 }}>Cat.</th>
              <th style={{ padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11 }}>Descrizione</th>
              <th style={{ padding: '8px 8px', textAlign: 'right', fontWeight: 600, fontSize: 11 }}>DARE</th>
              <th style={{ padding: '8px 8px', textAlign: 'right', fontWeight: 600, fontSize: 11 }}>AVERE</th>
              <th style={{ padding: '8px 8px', textAlign: 'right', fontWeight: 600, fontSize: 11 }}>Saldo</th>
              <th style={{ padding: '8px 8px', textAlign: 'center', fontWeight: 600, fontSize: 11 }}>Documento</th>
              {!readOnly && <th style={{ padding: '8px 8px', textAlign: 'center', fontWeight: 600, fontSize: 11 }}>Azioni</th>}
            </tr>
          </thead>
          <tbody>
            {currentWithBalance.map((mov, idx) => (
              <tr 
                key={mov.id || idx} 
                style={{ 
                  borderBottom: '1px solid #e5e7eb', 
                  background: idx % 2 === 0 ? 'white' : '#f9fafb'
                }}
                data-testid={`movimento-row-${mov.id || idx}`}
              >
                <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 11 }}>{formatDate(mov.data)}</td>
                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                  <span style={{
                    padding: '2px 6px',
                    borderRadius: 4,
                    fontSize: 9,
                    fontWeight: 'bold',
                    background: mov.tipo === 'entrata' ? '#dcfce7' : '#fee2e2',
                    color: mov.tipo === 'entrata' ? '#166534' : '#991b1b'
                  }}>
                    {mov.tipo === 'entrata' ? '↑' : '↓'}
                  </span>
                </td>
                <td style={{ padding: '6px 8px' }}>
                  <span style={{ background: '#f3f4f6', padding: '2px 4px', borderRadius: 3, fontSize: 10 }}>
                    {mov.categoria || '-'}
                  </span>
                </td>
                <td style={{ padding: '6px 8px', maxWidth: 400, wordBreak: 'break-word', whiteSpace: 'pre-wrap', fontSize: 11, lineHeight: 1.3 }}>
                  {mov.descrizione || mov.descrizione_originale || '-'}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'right', color: '#166534', fontWeight: mov.tipo === 'entrata' ? 'bold' : 'normal', fontSize: 12 }}>
                  {mov.tipo === 'entrata' ? formatEuro(mov.importo) : '-'}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'right', color: '#991b1b', fontWeight: mov.tipo === 'uscita' ? 'bold' : 'normal', fontSize: 12 }}>
                  {mov.tipo === 'uscita' ? formatEuro(mov.importo) : '-'}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 'bold', color: mov.saldoProgressivo >= 0 ? '#166534' : '#991b1b', fontSize: 12 }}>
                  {formatEuro(mov.saldoProgressivo)}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                  {/* Pulsante VEDI documento - Supporta: Fattura, F24, Corrispettivi, Bonifici */}
                  {mov.fattura_id ? (
                    <a
                      href={`/api/fatture-ricevute/fattura/${mov.fattura_id}/view-assoinvoice`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#2196f3',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                        textDecoration: 'none'
                      }}
                      title="Visualizza Fattura"
                      data-testid={`view-fattura-${mov.id || idx}`}
                    >
                      📄 Fattura
                    </a>
                  ) : mov.bonifico_pdf_id ? (
                    <a
                      href={`/api/archivio-bonifici/transfers/${mov.bonifico_pdf_id}/pdf`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#9c27b0',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                        textDecoration: 'none'
                      }}
                      title="Visualizza Bonifico PDF"
                      data-testid={`view-bonifico-${mov.id || idx}`}
                    >
                      📎 Bonifico
                    </a>
                  ) : mov.f24_id ? (
                    <a
                      href={`/api/f24/${mov.f24_id}/view`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#ef4444',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                        textDecoration: 'none'
                      }}
                      title="Visualizza F24"
                      data-testid={`view-f24-${mov.id || idx}`}
                    >
                      🏛️ F24
                    </a>
                  ) : mov.corrispettivo_id || mov.xml_filename ? (
                    <a
                      href={mov.corrispettivo_id ? `/api/corrispettivi/${mov.corrispettivo_id}/view` : `/api/corrispettivi/view-by-filename?filename=${encodeURIComponent(mov.xml_filename)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#4caf50',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 'bold',
                        textDecoration: 'none'
                      }}
                      title="Visualizza Corrispettivo"
                      data-testid={`view-corrispettivo-${mov.id || idx}`}
                    >
                      🧾 Corrisp.
                    </a>
                  ) : mov.categoria === 'F24' || (mov.descrizione && mov.descrizione.includes('F24')) ? (
                    <span 
                      style={{
                        display: 'inline-block',
                        padding: '6px 12px',
                        background: '#fef3c7',
                        color: '#92400e',
                        border: '1px solid #ff9800',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 'bold'
                      }}
                      title="F24 - Documento da allegare"
                    >
                      🏛️ F24
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
                        background: tipo === 'cassa' ? '#1e3a5f' : '#7c3aed', 
                        color: 'white',
                        border: 'none', 
                        borderRadius: 4,
                        padding: '3px 6px',
                        cursor: spostando === mov.id ? 'wait' : 'pointer', 
                        fontSize: 10,
                        marginRight: 4,
                        opacity: spostando === mov.id ? 0.6 : 1
                      }}
                      title={tipo === 'cassa' ? 'Sposta in Banca' : 'Sposta in Cassa'}
                      data-testid={`sposta-movimento-${mov.id}`}
                    >
                      {spostando === mov.id ? '⏳' : (tipo === 'cassa' ? '🏦' : '💵')}
                    </button>
                    <button 
                      onClick={() => setEditingMovimento(mov)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, marginRight: 4 }}
                      title="Modifica"
                      data-testid={`edit-movimento-${mov.id}`}
                    >
                      ✏️
                    </button>
                    <button 
                      onClick={() => onDelete(mov.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14 }}
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
          {readOnly ? 'Nessun movimento nell\'estratto conto. Importa un file CSV dalla pagina Import/Export.' : 'Nessun movimento trovato'}
        </div>
      )}

      {/* Footer con Paginazione ANCHE IN BASSO */}
      {movimenti.length > 0 && (
        <div style={{ padding: 12, background: '#f9fafb', borderTop: '1px solid #e5e7eb', fontSize: 12, color: '#6b7280' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Mostrando {start + 1}-{Math.min(start + itemsPerPage, movimenti.length)} di {movimenti.length} movimenti</span>
            {totalPages > 1 && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span>📄 Pagina {currentPage} di {totalPages}</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button onClick={() => setCurrentPage(1)} disabled={currentPage === 1} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === 1 ? 0.5 : 1, background: '#e5e7eb' }}>⏮️</button>
                  <button onClick={() => setCurrentPage(p => Math.max(1, p-1))} disabled={currentPage === 1} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === 1 ? 0.5 : 1, background: '#e5e7eb' }}>◀️</button>
                  <button onClick={() => setCurrentPage(p => Math.min(totalPages, p+1))} disabled={currentPage === totalPages} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === totalPages ? 0.5 : 1, background: '#e5e7eb' }}>▶️</button>
                  <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', opacity: currentPage === totalPages ? 0.5 : 1, background: '#e5e7eb' }}>⏭️</button>
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
  const [form, setForm] = useState({
    data: movimento.data || '',
    tipo: movimento.tipo || 'uscita',
    importo: movimento.importo || '',
    descrizione: movimento.descrizione || '',
    categoria: movimento.categoria || '',
    riferimento: movimento.riferimento || '',
    note: movimento.note || ''
  });
  const [saving, setSaving] = useState(false);

  const categorie = tipo === 'cassa' 
    ? ['Corrispettivi', 'POS', 'Versamento', 'Pagamento fornitore', 'Incasso', 'Spese', 'Altro']
    : ['Pagamento fornitore', 'Bonifico', 'Assegno', 'F24', 'Altro'];

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.importo || !form.descrizione) {
      alert('Compila importo e descrizione');
      return;
    }
    
    setSaving(true);
    try {
      const endpoint = tipo === 'cassa' 
        ? `/api/prima-nota/cassa/${movimento.id}`
        : `/api/prima-nota/banca/${movimento.id}`;
      
      await api.put(endpoint, {
        data: form.data,
        tipo: form.tipo,
        importo: parseFloat(form.importo),
        descrizione: form.descrizione,
        categoria: form.categoria,
        riferimento: form.riferimento,
        note: form.note
      });
      
      onSave({ ...movimento, ...form, importo: parseFloat(form.importo) });
    } catch (error) {
      console.error('Errore salvataggio:', error);
      alert('Errore nel salvataggio: ' + (error.response?.data?.message || error.message));
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
    outline: 'none'
  };

  const labelStyle = {
    display: 'block',
    fontSize: 12,
    fontWeight: 600,
    color: '#374151',
    marginBottom: 4
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
        padding: 20
      }}
      onClick={onClose}
    >
      <div 
        style={{
          background: 'white',
          borderRadius: 16,
          width: '100%',
          maxWidth: 500,
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid #e5e7eb',
          background: tipo === 'cassa' ? '#4f46e5' : '#1e3a5f',
          borderRadius: '16px 16px 0 0',
          color: 'white',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
            ✏️ Modifica Movimento {tipo === 'cassa' ? 'Cassa' : 'Banca'}
          </h3>
          <button 
            onClick={onClose}
            style={{ background: 'rgba(255,255,255,0.2)', border: 'none', borderRadius: 8, padding: '4px 8px', cursor: 'pointer', color: 'white' }}
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ padding: 24 }}>
          <div style={{ display: 'grid', gap: 16 }}>
            {/* Data e Tipo */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={labelStyle}>Data</label>
                <input
                  type="date"
                  value={form.data}
                  onChange={(e) => setForm({ ...form, data: e.target.value })}
                  style={inputStyle}
                  required
                />
              </div>
              <div>
                <label style={labelStyle}>Tipo</label>
                <select
                  value={form.tipo}
                  onChange={(e) => setForm({ ...form, tipo: e.target.value })}
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
                onChange={(e) => setForm({ ...form, importo: e.target.value })}
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
                onChange={(e) => setForm({ ...form, categoria: e.target.value })}
                style={inputStyle}
              >
                <option value="">-- Seleziona --</option>
                {categorie.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>

            {/* Descrizione */}
            <div>
              <label style={labelStyle}>Descrizione</label>
              <input
                type="text"
                value={form.descrizione}
                onChange={(e) => setForm({ ...form, descrizione: e.target.value })}
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
                onChange={(e) => setForm({ ...form, riferimento: e.target.value })}
                style={inputStyle}
                placeholder="N. fattura, documento, ecc."
              />
            </div>

            {/* Note */}
            <div>
              <label style={labelStyle}>Note (opzionale)</label>
              <textarea
                value={form.note}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
                style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
                placeholder="Note aggiuntive..."
              />
            </div>
          </div>

          {/* Footer */}
          <div style={{ 
            marginTop: 24, 
            paddingTop: 16, 
            borderTop: '1px solid #e5e7eb',
            display: 'flex', 
            justifyContent: 'flex-end', 
            gap: 12 
          }}>
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
                fontWeight: 500
              }}
            >
              Annulla
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: '10px 20px',
                borderRadius: 8,
                border: 'none',
                background: tipo === 'cassa' ? '#4f46e5' : '#1e3a5f',
                color: 'white',
                cursor: saving ? 'not-allowed' : 'pointer',
                fontSize: 14,
                fontWeight: 600,
                opacity: saving ? 0.7 : 1
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

