import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

/**
 * =====================================================================
 * CONTROLLO MENSILE - DOCUMENTAZIONE LOGICA
 * =====================================================================
 * 
 * SCOPO: Confrontare i dati automatici (da XML) con quelli manuali (da Excel/Prima Nota)
 * 
 * FONTI DATI:
 * -----------
 * 1. CORRISPETTIVI XML (collection: corrispettivi)
 *    - pagato_elettronico = POS Chiusura Serale RT (cosa dice la macchina)
 *    - totale = Corrispettivi Auto (incasso totale giornaliero)
 *    - pagato_contanti = Contanti (per calcolo saldo cassa)
 * 
 * 2. PRIMA NOTA CASSA (collection: prima_nota_cassa)
 *    - categoria "POS" = POS Manuale Reale (inserito da te la sera)
 *    - categoria "Corrispettivi" = Corrispettivi Manuali
 *    - categoria "Versamento" con tipo "uscita" = Versamenti in banca
 *    - Saldo Cassa = Σ entrate - Σ uscite
 * 
 * 3. PRIMA NOTA BANCA (collection: prima_nota_banca)
 *    - Usata per verifiche incrociate sui versamenti
 * 
 * COLONNE TABELLA:
 * ----------------
 * | Mese/Data | POS Agenzia | POS Chiusura | Diff. POS | Corrisp. Auto | Corrisp. Man. | Diff. Corr. | Versamenti | Saldo Cassa | Dettagli |
 * 
 * CALCOLI:
 * --------
 * - POS RT = Σ corrispettivi.pagato_elettronico (da XML chiusura serale)
 * - POS Reale = Σ prima_nota_cassa WHERE categoria = "POS" (inserito manualmente da te)
 * - Diff. POS = POS RT (XML) - POS Reale (Tuo)
 * - Corrisp. Auto = Σ corrispettivi.totale (da XML)
 * - Corrisp. Man. = Σ prima_nota_cassa WHERE categoria = "Corrispettivi" AND tipo = "entrata"
 * - Diff. Corr. = Corrisp. Auto - Corrisp. Man.
 * - Versamenti = Σ prima_nota_cassa WHERE (categoria = "Versamento" OR descrizione CONTAINS "versamento") AND tipo = "uscita"
 * - Saldo Cassa = Σ entrate - Σ uscite (tutti i movimenti cassa del periodo)
 * 
 * NOTA IMPORTANTE:
 * ----------------
 * - Il POS in Prima Nota può essere sia "entrata" che "uscita" a seconda di come è stato registrato
 * - Il dato più affidabile per il POS è quello dai corrispettivi XML (pagato_elettronico)
 * - Se i dati XML sono diversi da quelli manuali, i dati XML hanno priorità
 * =====================================================================
 */

export default function ControlloMensile() {
  const [loading, setLoading] = useState(true);
  const currentYear = new Date().getFullYear();
  const { anno } = useAnnoGlobale(); // Anno dal contesto globale
  const [viewMode, setViewMode] = useState('anno'); // 'anno' or 'mese'
  const [meseSelezionato, setMeseSelezionato] = useState(null);
  
  // Monthly summary data
  const [monthlyData, setMonthlyData] = useState([]);
  const [yearTotals, setYearTotals] = useState({
    posAuto: 0,
    posManual: 0,
    posBanca: 0,
    posBancaCommissioni: 0,
    corrispettiviAuto: 0,
    corrispettiviManual: 0,
    versamenti: 0,
    saldoCassa: 0,
    documentiCommerciali: 0,
    annulli: 0,
    pagatoNonRiscosso: 0,
    pagatoNonRiscossoCount: 0,
    ammontareAnnulli: 0,
    ammontareAnnulliCount: 0
  });
  
  // Daily detail data (when viewing a specific month)
  const [dailyComparison, setDailyComparison] = useState([]);
  
  // Dettaglio versamenti per il mese
  const [versamentiDettaglio, setVersamentiDettaglio] = useState([]);
  const [showVersamentiModal, setShowVersamentiModal] = useState(false);

  const monthNames = [
    'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
    'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'
  ];

  useEffect(() => {
    if (viewMode === 'anno') {
      loadYearData();
    } else if (meseSelezionato) {
      loadMonthData(meseSelezionato);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anno, viewMode, meseSelezionato]);

  /**
   * CARICA DATI ANNUALI
   * Recupera tutti i movimenti dell'anno e li aggrega per mese
   * Include: Prima Nota Cassa, Prima Nota Banca, Corrispettivi
   */
  const loadYearData = async () => {
    setLoading(true);
    try {
      const startDate = `${anno}-01-01`;
      const endDate = `${anno}-12-31`;
      
      const params = new URLSearchParams({
        data_da: startDate,
        data_a: endDate
      });

      // Carica dati in parallelo da TUTTE le fonti (Cassa, Corrispettivi, Estratto Conto Banca)
      const [cassaRes, corrispRes, estrattoRes] = await Promise.all([
        api.get(`/api/prima-nota/cassa?${params}&limit=5000`).catch(() => ({ data: { movimenti: [] } })),
        api.get(`/api/corrispettivi?data_da=${startDate}&data_a=${endDate}&limit=500`).catch(() => ({ data: [] })),
        api.get(`/api/bank-statement/movements?data_da=${startDate}&data_a=${endDate}&limit=5000`).catch(() => ({ data: { movements: [] } }))
      ]);

      const cassa = cassaRes.data.movimenti || [];
      const corrispettivi = Array.isArray(corrispRes.data) ? corrispRes.data : (corrispRes.data.corrispettivi || []);
      const estrattoConto = estrattoRes.data.movements || [];
      
      processYearData(cassa, corrispettivi, estrattoConto);
    } catch (error) {
      console.error('Error loading year data:', error);
    } finally {
      setLoading(false);
    }
  };

  /**
   * PROCESSA DATI ANNUALI
   * Aggrega i dati per mese calcolando tutti i totali
   * Include: POS RT (XML), POS Reale (Tuo), POS Banca (da Estratto Conto Bancario)
   */
  const processYearData = (cassa, corrispettivi, estrattoConto = []) => {
    const monthly = [];
    let yearPosAuto = 0, yearPosManual = 0, yearPosBanca = 0, yearPosBancaCommissioni = 0;
    let yearCorrispAuto = 0, yearCorrispManual = 0;
    let yearVersamenti = 0, yearSaldoCassa = 0;
    let yearDocumentiCommerciali = 0;
    let yearAnnulli = 0;
    let yearPagatoNonRiscosso = 0, yearPagatoNonRiscossoCount = 0;
    let yearAmmontareAnnulli = 0, yearAmmontareAnnulliCount = 0;

    for (let month = 1; month <= 12; month++) {
      const monthStr = String(month).padStart(2, '0');
      const monthPrefix = `${anno}-${monthStr}`;
      
      // Filtra dati per questo mese
      const monthCassa = cassa.filter(m => m.data?.startsWith(monthPrefix));
      const monthCorrisp = corrispettivi.filter(c => c.data?.startsWith(monthPrefix));
      const monthEstratto = estrattoConto.filter(m => m.data?.startsWith(monthPrefix));

      // ============ POS AUTO (da Corrispettivi XML) ============
      // Il POS automatico è il campo pagato_elettronico estratto dagli XML
      const posAuto = monthCorrisp.reduce((sum, c) => sum + (parseFloat(c.pagato_elettronico) || 0), 0);

      // ============ DOCUMENTI COMMERCIALI (da Corrispettivi XML) ============
      // Numero totale di scontrini/ricevute emessi nel mese
      const documentiCommerciali = monthCorrisp.reduce((sum, c) => sum + (parseInt(c.numero_documenti) || 0), 0);

      // ============ ANNULLI (vecchio campo - per compatibilità) ============
      const annulli = monthCorrisp.reduce((sum, c) => sum + (parseInt(c.annulli) || 0), 0);

      // ============ PAGATO NON RISCOSSO (da Corrispettivi XML) ============
      // Differenza tra (Ammontare + ImportoParziale) - (PagatoContanti + PagatoElettronico)
      const corrispNonRiscosso = monthCorrisp.filter(c => (parseFloat(c.pagato_non_riscosso) || 0) > 0);
      const pagatoNonRiscosso = corrispNonRiscosso.reduce((sum, c) => sum + (parseFloat(c.pagato_non_riscosso) || 0), 0);
      const pagatoNonRiscossoCount = corrispNonRiscosso.length;

      // ============ AMMONTARE ANNULLI (da Corrispettivi XML - TotaleAmmontareAnnulli) ============
      const corrispAnnulli = monthCorrisp.filter(c => (parseFloat(c.totale_ammontare_annulli) || 0) > 0);
      const ammontareAnnulli = corrispAnnulli.reduce((sum, c) => sum + (parseFloat(c.totale_ammontare_annulli) || 0), 0);
      const ammontareAnnulliCount = corrispAnnulli.length;

      // ============ POS MANUALE (da Prima Nota Cassa) ============
      // Il POS manuale è registrato con categoria "POS" in Prima Nota Cassa
      const posManual = monthCassa
        .filter(m => m.categoria?.toUpperCase() === 'POS' || m.source === 'excel_pos')
        .reduce((sum, m) => sum + Math.abs(parseFloat(m.importo) || 0), 0);

      // ============ POS BANCA (da Estratto Conto Bancario) ============
      // Logica: cercare "PDV 3757283" o "PDV: 3757283" nella descrizione
      // - Importi positivi (tipo=entrata) = Accrediti POS
      // - Importi negativi (tipo=uscita) = Commissioni/Spese POS
      // 
      // SFASAMENTO ACCREDITI: Gli accrediti bancari avvengono il giorno lavorativo successivo
      // - Lun→Mar, Mar→Mer, Mer→Gio, Gio→Ven, Ven/Sab/Dom→Lun
      // - Se festivo → giorno lavorativo successivo
      
      // Filtra movimenti POS per codice PDV 3757283
      const posBancaMovimenti = estrattoConto.filter(m => {
        const desc = (m.descrizione || '').toUpperCase();
        return desc.includes('PDV 3757283') || desc.includes('PDV: 3757283');
      });
      
      // Calcola data accredito attesa in base alla regola di sfasamento
      const _getDataAccreditoAttesa = (dataOperazione) => {
        const date = new Date(dataOperazione);
        const dayOfWeek = date.getDay(); // 0=Dom, 1=Lun, 2=Mar, 3=Mer, 4=Gio, 5=Ven, 6=Sab
        
        // Sfasamento: +1 giorno lavorativo
        // Ven/Sab/Dom → Lunedì
        if (dayOfWeek === 5) { // Venerdì
          date.setDate(date.getDate() + 3); // +3 = Lunedì
        } else if (dayOfWeek === 6) { // Sabato
          date.setDate(date.getDate() + 2); // +2 = Lunedì
        } else if (dayOfWeek === 0) { // Domenica
          date.setDate(date.getDate() + 1); // +1 = Lunedì
        } else {
          date.setDate(date.getDate() + 1); // +1 giorno
        }
        
        // Festivi italiani (approssimazione - principali festività)
        const festiviItaliani = [
          '01-01', // Capodanno
          '01-06', // Epifania
          '04-25', // Liberazione
          '05-01', // Festa del Lavoro
          '06-02', // Festa della Repubblica
          '08-15', // Ferragosto
          '11-01', // Tutti i Santi
          '12-08', // Immacolata
          '12-25', // Natale
          '12-26', // Santo Stefano
        ];
        
        // Controllo festivi (loop max 5 giorni per sicurezza)
        for (let i = 0; i < 5; i++) {
          const mmdd = date.toISOString().slice(5, 10);
          const dow = date.getDay();
          if (festiviItaliani.includes(mmdd) || dow === 0 || dow === 6) {
            date.setDate(date.getDate() + 1);
          } else {
            break;
          }
        }
        
        return date.toISOString().slice(0, 10);
      };
      
      // Raggruppa per mese di ACCREDITO (non di operazione)
      // La data nell'estratto conto è già la data accredito effettivo
      const posBancaAccrediti = posBancaMovimenti
        .filter(m => m.tipo === 'entrata' && m.data?.startsWith(monthPrefix))
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);
      
      const posBancaCommissioni = posBancaMovimenti
        .filter(m => m.tipo === 'uscita' && m.data?.startsWith(monthPrefix))
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);
      
      // POS Banca = Accrediti (il valore principale da mostrare)
      const posBanca = posBancaAccrediti;

      // ============ CORRISPETTIVI AUTO (da XML) ============
      // Totale incassi giornalieri dai corrispettivi XML
      const corrispAuto = monthCorrisp.reduce((sum, c) => sum + (parseFloat(c.totale) || 0), 0);

      // ============ CORRISPETTIVI MANUALI (da Prima Nota) ============
      // Corrispettivi registrati manualmente o importati da Excel
      const corrispManual = monthCassa
        .filter(m => m.categoria === 'Corrispettivi' || m.source === 'excel_corrispettivi')
        .filter(m => m.tipo === 'entrata')
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);

      // ============ VERSAMENTI ============
      // Versamenti = uscite dalla cassa verso banca
      const versamenti = monthCassa
        .filter(m => {
          const isVersamento = m.categoria === 'Versamento' || 
                              m.categoria?.toLowerCase().includes('versamento') ||
                              m.descrizione?.toLowerCase().includes('versamento');
          return isVersamento && m.tipo === 'uscita';
        })
        .reduce((sum, m) => sum + Math.abs(parseFloat(m.importo) || 0), 0);

      // ============ SALDO CASSA ============
      // Saldo Cassa = Entrate cassa - Uscite cassa del mese
      const entrateCassa = monthCassa
        .filter(m => m.tipo === 'entrata')
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);
      const usciteCassa = monthCassa
        .filter(m => m.tipo === 'uscita')
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);
      const saldoCassa = entrateCassa - usciteCassa;

      // ============ DIFFERENZE ============
      // CONTROLLO GIORNALIERO: POS XML (chiusura serale RT) vs POS Manuale (tuo incasso reale)
      const posDiff = posAuto - posManual;
      // RICONCILIAZIONE BANCARIA: POS arrivato in banca vs POS Manuale (tuo incasso reale)
      const posBancaDiff = posBanca - posManual; // Banca vs TUO dato reale
      const corrispDiff = corrispAuto - corrispManual;
      
      const hasData = posAuto > 0 || posManual > 0 || posBanca > 0 || corrispAuto > 0 || corrispManual > 0 || versamenti > 0;
      const hasDiscrepancy = Math.abs(posDiff) > 1 || Math.abs(corrispDiff) > 1 || Math.abs(posBancaDiff) > 1;

      monthly.push({
        month,
        monthName: monthNames[month - 1],
        posAuto,
        posManual,
        posBanca,
        posBancaCommissioni,
        posDiff,
        posBancaDiff,
        corrispAuto,
        corrispManual,
        corrispDiff,
        versamenti,
        saldoCassa,
        documentiCommerciali,
        annulli,
        pagatoNonRiscosso,
        pagatoNonRiscossoCount,
        ammontareAnnulli,
        ammontareAnnulliCount,
        hasData,
        hasDiscrepancy,
        // Debug info
        _debug: {
          cassaCount: monthCassa.length,
          estrattoCount: monthEstratto.length,
          corrispCount: monthCorrisp.length
        }
      });

      yearPosAuto += posAuto;
      yearPosManual += posManual;
      yearPosBanca += posBanca;
      yearPosBancaCommissioni += posBancaCommissioni;
      yearCorrispAuto += corrispAuto;
      yearCorrispManual += corrispManual;
      yearVersamenti += versamenti;
      yearSaldoCassa += saldoCassa;
      yearDocumentiCommerciali += documentiCommerciali;
      yearAnnulli += annulli;
      yearPagatoNonRiscosso += pagatoNonRiscosso;
      yearPagatoNonRiscossoCount += pagatoNonRiscossoCount;
      yearAmmontareAnnulli += ammontareAnnulli;
      yearAmmontareAnnulliCount += ammontareAnnulliCount;
    }

    setMonthlyData(monthly);
    setYearTotals({
      posAuto: yearPosAuto,
      posManual: yearPosManual,
      posBanca: yearPosBanca,
      posBancaCommissioni: yearPosBancaCommissioni,
      corrispettiviAuto: yearCorrispAuto,
      corrispettiviManual: yearCorrispManual,
      versamenti: yearVersamenti,
      saldoCassa: yearSaldoCassa,
      documentiCommerciali: yearDocumentiCommerciali,
      annulli: yearAnnulli,
      pagatoNonRiscosso: yearPagatoNonRiscosso,
      pagatoNonRiscossoCount: yearPagatoNonRiscossoCount,
      ammontareAnnulli: yearAmmontareAnnulli,
      ammontareAnnulliCount: yearAmmontareAnnulliCount
    });
  };

  /**
   * CARICA DATI MENSILI (Dettaglio Giornaliero)
   * Recupera i movimenti del mese selezionato e li mostra giorno per giorno
   */
  const loadMonthData = async (month) => {
    setLoading(true);
    try {
      const monthStr = String(month).padStart(2, '0');
      const daysInMonth = new Date(anno, month, 0).getDate();
      const startDate = `${anno}-${monthStr}-01`;
      const endDate = `${anno}-${monthStr}-${String(daysInMonth).padStart(2, '0')}`;
      
      const params = new URLSearchParams({
        data_da: startDate,
        data_a: endDate
      });

      const [cassaRes, corrispRes] = await Promise.all([
        api.get(`/api/prima-nota/cassa?${params}&limit=2000`).catch(() => ({ data: { movimenti: [] } })),
        api.get(`/api/corrispettivi?data_da=${startDate}&data_a=${endDate}&limit=500`).catch(() => ({ data: [] }))
      ]);

      const cassa = cassaRes.data.movimenti || [];
      const corrispettivi = Array.isArray(corrispRes.data) ? corrispRes.data : (corrispRes.data.corrispettivi || []);
      
      processDailyData(cassa, corrispettivi, month);
      
      // Estrai dettaglio versamenti del mese
      const versamentiMese = cassa.filter(m => {
        const isVersamento = m.categoria === 'Versamento' || 
                            m.categoria?.toLowerCase().includes('versamento') ||
                            m.descrizione?.toLowerCase().includes('versamento');
        return isVersamento && m.tipo === 'uscita';
      });
      setVersamentiDettaglio(versamentiMese);
      
    } catch (error) {
      console.error('Error loading month data:', error);
    } finally {
      setLoading(false);
    }
  };

  /**
   * PROCESSA DATI GIORNALIERI
   * Crea una riga per ogni giorno del mese con tutti i totali
   */
  const processDailyData = (cassa, corrispettivi, month) => {
    const daysInMonth = new Date(anno, month, 0).getDate();
    const comparison = [];
    const monthStr = String(month).padStart(2, '0');

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${anno}-${monthStr}-${String(day).padStart(2, '0')}`;
      const dayData = { date: dateStr, day };

      // Filtra movimenti del giorno
      const dayCassa = cassa.filter(m => m.data === dateStr);
      const dayCorrisp = corrispettivi.filter(c => c.data === dateStr);

      // ============ POS AUTO (da Corrispettivi XML) ============
      dayData.posAuto = dayCorrisp.reduce((sum, c) => sum + (parseFloat(c.pagato_elettronico) || 0), 0);

      // ============ DOCUMENTI COMMERCIALI (da Corrispettivi XML) ============
      dayData.documentiCommerciali = dayCorrisp.reduce((sum, c) => sum + (parseInt(c.numero_documenti) || 0), 0);

      // ============ POS MANUALE (da Prima Nota) ============
      dayData.posManual = dayCassa
        .filter(m => m.categoria?.toUpperCase() === 'POS' || m.source === 'excel_pos')
        .reduce((sum, m) => sum + Math.abs(parseFloat(m.importo) || 0), 0);

      // ============ CORRISPETTIVI AUTO (da XML) ============
      dayData.corrispettivoAuto = dayCorrisp.reduce((sum, c) => sum + (parseFloat(c.totale) || 0), 0);

      // ============ CORRISPETTIVI MANUALI ============
      dayData.corrispettivoManual = dayCassa
        .filter(m => m.categoria === 'Corrispettivi' || m.source === 'excel_corrispettivi')
        .filter(m => m.tipo === 'entrata')
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);

      // ============ VERSAMENTO ============
      dayData.versamento = dayCassa
        .filter(m => {
          const isVersamento = m.categoria === 'Versamento' || 
                              m.categoria?.toLowerCase().includes('versamento') ||
                              m.descrizione?.toLowerCase().includes('versamento');
          return isVersamento && m.tipo === 'uscita';
        })
        .reduce((sum, m) => sum + Math.abs(parseFloat(m.importo) || 0), 0);

      // ============ SALDO CASSA ============
      const entrateGiorno = dayCassa
        .filter(m => m.tipo === 'entrata')
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);
      const usciteGiorno = dayCassa
        .filter(m => m.tipo === 'uscita')
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);
      dayData.saldoCassa = entrateGiorno - usciteGiorno;

      // Differenze
      dayData.posDiff = dayData.posAuto - dayData.posManual;
      dayData.corrispettivoDiff = dayData.corrispettivoAuto - dayData.corrispettivoManual;
      
      dayData.hasData = dayData.posAuto > 0 || dayData.posManual > 0 || 
                        dayData.corrispettivoAuto > 0 || dayData.corrispettivoManual > 0 ||
                        dayData.versamento > 0 || entrateGiorno > 0 || usciteGiorno > 0;
      dayData.hasDiscrepancy = Math.abs(dayData.posDiff) > 1 || Math.abs(dayData.corrispettivoDiff) > 1;

      // Debug info
      dayData._debug = {
        cassaCount: dayCassa.length,
        corrispCount: dayCorrisp.length,
        entrateGiorno,
        usciteGiorno
      };

      comparison.push(dayData);
    }

    setDailyComparison(comparison);
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric' });
  };

  const handleMonthClick = (month) => {
    setMeseSelezionato(month);
    setViewMode('mese');
  };

  const handleBackToYear = () => {
    setViewMode('anno');
    setMeseSelezionato(null);
  };

  // Generate year options (last 5 years)
  const yearOptions = [];
  for (let y = currentYear; y >= currentYear - 4; y--) {
    yearOptions.push(y);
  }

  // Modal Versamenti
  const VersamentiModal = () => {
    if (!showVersamentiModal) return null;
    
    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000
      }} onClick={() => setShowVersamentiModal(false)}>
        <div style={{
          background: 'white', borderRadius: 12, padding: 20, maxWidth: 600, width: '90%',
          maxHeight: '80vh', overflowY: 'auto'
        }} onClick={e => e.stopPropagation()}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 }}>
            <h2 style={{ margin: 0 }}>💰 Dettaglio Versamenti - {monthNames[meseSelezionato - 1]} {anno}</h2>
            <button onClick={() => setShowVersamentiModal(false)} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
          </div>
          
          {versamentiDettaglio.length === 0 ? (
            <p style={{ color: '#666' }}>Nessun versamento registrato per questo mese.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  <th style={{ padding: 10, textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>Data</th>
                  <th style={{ padding: 10, textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>Descrizione</th>
                  <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0' }}>Importo</th>
                </tr>
              </thead>
              <tbody>
                {versamentiDettaglio.map((v, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #e2e8f0' }}>
                    <td style={{ padding: 10 }}>{v.data}</td>
                    <td style={{ padding: 10 }}>{v.descrizione || v.categoria}</td>
                    <td style={{ padding: 10, textAlign: 'right', fontWeight: 'bold', color: '#16a34a' }}>
                      {formatEuro(Math.abs(v.importo))}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ background: '#1e293b', color: 'white' }}>
                  <td colSpan={2} style={{ padding: 10, fontWeight: 'bold' }}>TOTALE</td>
                  <td style={{ padding: 10, textAlign: 'right', fontWeight: 'bold' }}>
                    {formatEuro(versamentiDettaglio.reduce((sum, v) => sum + Math.abs(parseFloat(v.importo) || 0), 0))}
                  </td>
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      </div>
    );
  };

  return (
    <PageLayout 
      title={`Controllo ${viewMode === 'anno' ? 'Annuale' : 'Mensile'}`} 
      icon="📊" 
      subtitle="Confronto dati automatici (XML) vs manuali (Prima Nota/Excel)"
    >
      {/* Year Selector & View Toggle */}
      <div style={{ display: 'flex', gap: 15, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <label style={{ fontWeight: 'bold' }}>Anno:</label>
          <div
            style={{ 
              padding: '10px 16px', 
              borderRadius: 8, 
              border: '2px solid #e0e0e0', 
              fontSize: 16,
              minWidth: 100,
              background: '#f1f5f9',
              color: '#6b7280',
              fontWeight: 600
            }}
            data-testid="year-display"
          >
            {anno} <span style={{ fontSize: 10, opacity: 0.7 }}>(globale)</span>
          </div>
        </div>

        {viewMode === 'mese' && (
          <>
            {/* Navigazione Mesi */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                onClick={() => {
                  if (meseSelezionato > 1) {
                    setMeseSelezionato(meseSelezionato - 1);
                  }
                }}
                disabled={meseSelezionato <= 1}
                style={{
                  padding: '8px 14px',
                  background: meseSelezionato > 1 ? '#1535a8' : '#94a3b8',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: meseSelezionato > 1 ? 'pointer' : 'not-allowed',
                  fontWeight: 'bold',
                  fontSize: 14
                }}
                data-testid="prev-month-btn"
              >
                ◀ {meseSelezionato > 1 ? monthNames[meseSelezionato - 2] : 'Gen'}
              </button>
              
              <span style={{ 
                fontWeight: 'bold', 
                fontSize: 16, 
                padding: '8px 16px',
                background: '#f0f9ff',
                borderRadius: 8,
                minWidth: 140,
                textAlign: 'center'
              }}>
                {monthNames[meseSelezionato - 1]} {anno}
              </span>
              
              <button
                onClick={() => {
                  if (meseSelezionato < 12) {
                    setMeseSelezionato(meseSelezionato + 1);
                  }
                  // Non cambia anno - è globale
                }}
                disabled={meseSelezionato >= 12}
                style={{
                  padding: '8px 14px',
                  background: meseSelezionato < 12 ? '#1535a8' : '#94a3b8',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: meseSelezionato < 12 ? 'pointer' : 'not-allowed',
                  fontWeight: 'bold',
                  fontSize: 14
                }}
                data-testid="next-month-btn"
              >
                {meseSelezionato < 12 ? monthNames[meseSelezionato] : 'Dic'} ▶
              </button>
            </div>
            
            <button
              onClick={handleBackToYear}
              style={{
                padding: '8px 16px',
                background: '#6b7280',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
              data-testid="back-to-year-btn"
            >
              ← Riepilogo Annuale
            </button>
            
            <button
              onClick={() => setShowVersamentiModal(true)}
              style={{
                padding: '8px 16px',
                background: '#16a34a',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
              data-testid="show-versamenti-btn"
            >
              💰 Versamenti
            </button>
          </>
        )}

        {viewMode === 'anno' && (
          <span style={{ fontSize: 18, fontWeight: 'bold', marginLeft: 'auto' }}>
            📅 {anno}
          </span>
        )}
      </div>

      {/* Summary Cards */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', 
        gap: 12, 
        marginBottom: 25 
      }}>
        <div style={{ background: 'linear-gradient(135deg, #1535a8 0%, #1d4ed8 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>POS RT (XML)</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.posAuto)}</div>
        </div>
        <div style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>POS Reale (Tuo)</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.posManual)}</div>
        </div>
        <div style={{ background: 'linear-gradient(135deg, #ec4899 0%, #be185d 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>🏦 POS Banca (PDV)</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.posBanca || 0)}</div>
          {yearTotals.posBancaCommissioni > 0 && (
            <div style={{ fontSize: 9, opacity: 0.8, marginTop: 2 }}>
              Comm.: -{formatEuro(yearTotals.posBancaCommissioni)}
            </div>
          )}
        </div>
        <div style={{ background: 'linear-gradient(135deg, #d97706 0%, #d97706 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>Corrisp. Auto (XML)</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.corrispettiviAuto)}</div>
        </div>
        <div style={{ background: 'linear-gradient(135deg, #15803d 0%, #059669 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>Corrisp. Manuali</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.corrispettiviManual)}</div>
        </div>
        <div style={{ background: 'linear-gradient(135deg, #16a34a 0%, #16a34a 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>Versamenti</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.versamenti)}</div>
        </div>
        <div style={{ background: 'linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>Saldo Cassa</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.saldoCassa)}</div>
        </div>
        <div style={{ background: 'linear-gradient(135deg, #6b7280 0%, #475569 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>📄 Doc. Commerciali</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{(yearTotals.documentiCommerciali || 0).toLocaleString('it-IT')}</div>
        </div>
        <div style={{ background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)', borderRadius: 12, padding: 14, color: 'white', position: 'relative' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>🚫 Annulli</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{(yearTotals.annulli || 0).toLocaleString('it-IT')}</div>
          {(yearTotals.annulli === 0 || !yearTotals.annulli) && (
            <div style={{ fontSize: 9, opacity: 0.7, marginTop: 4 }}>N/D negli XML</div>
          )}
        </div>
        {/* Card Pagato Non Riscosso */}
        <div style={{ background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>💰 Pagato Non Riscosso</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.pagatoNonRiscosso || 0)}</div>
          <div style={{ fontSize: 10, opacity: 0.8, marginTop: 2 }}>
            {yearTotals.pagatoNonRiscossoCount || 0} occorrenze
          </div>
        </div>
        {/* Card Ammontare Annulli */}
        <div style={{ background: 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)', borderRadius: 12, padding: 14, color: 'white' }}>
          <div style={{ fontSize: 11, opacity: 0.9 }}>🗑️ Ammontare Annulli</div>
          <div style={{ fontSize: 18, fontWeight: 'bold' }}>{formatEuro(yearTotals.ammontareAnnulli || 0)}</div>
          <div style={{ fontSize: 10, opacity: 0.8, marginTop: 2 }}>
            {yearTotals.ammontareAnnulliCount || 0} occorrenze
          </div>
        </div>
      </div>

      {/* Info Box */}
      <div style={{ 
        background: '#e0f2fe', 
        border: '2px solid #0284c7', 
        borderRadius: 8, 
        padding: 15, 
        marginBottom: 20,
        display: 'flex',
        alignItems: 'center',
        gap: 10
      }}>
        <span style={{ fontSize: 24 }}>ℹ️</span>
        <div>
          <strong>Fonti dati:</strong><br/>
          • <strong>POS RT (chiusura)</strong> = pagato_elettronico da XML corrispettivi (chiusura serale RT)<br/>
          • <strong>POS Reale (Tuo)</strong> = Prima Nota Cassa con categoria &quot;POS&quot; (inserito manualmente da te)<br/>
          • <strong>🏦 POS Banca</strong> = Accrediti PDV 3757283 dall&apos;estratto conto bancario<br/>
          • <strong>Diff. POS</strong> = POS RT - POS Reale (discrepanze giornaliere)<br/>
          • <strong>Diff. Banca</strong> = POS Banca - POS Reale (riconciliazione bancaria)<br/>
          • <strong>💰 Pagato Non Riscosso</strong> = (Ammontare + ImportoParziale) - (Contanti + Elettronico)<br/>
          • <strong>🗑️ Ammontare Annulli</strong> = TotaleAmmontareAnnulli da XML corrispettivi
        </div>
      </div>

      {/* Discrepancy Alert */}
      {((viewMode === 'anno' && monthlyData.some(d => d.hasDiscrepancy)) || 
        (viewMode === 'mese' && dailyComparison.some(d => d.hasDiscrepancy))) && (
        <div style={{ 
          background: '#fef3c7', 
          border: '2px solid #d97706', 
          borderRadius: 8, 
          padding: 15, 
          marginBottom: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 10
        }}>
          <span style={{ fontSize: 24 }}>⚠️</span>
          <div>
            <strong>Attenzione!</strong> Ci sono discrepanze tra i dati automatici (XML) e manuali.
            Le righe evidenziate in giallo richiedono verifica.
          </div>
        </div>
      )}

      {/* Year View - Monthly Table */}
      {viewMode === 'anno' && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }} data-testid="yearly-table">
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={{ padding: 10, textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>Mese</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#dbeafe' }}>POS RT (XML)</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#ede9fe' }}>POS Reale (Tuo)</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#fce7f3' }}>🏦 POS Banca</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0' }}>Diff.</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#fef3c7' }}>Corr. Auto</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#d1fae5' }}>Corr. Man.</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0' }}>Diff.</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#ecfdf5' }}>Versam.</th>
                <th style={{ padding: 10, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#e0f2fe' }}>Saldo</th>
                <th style={{ padding: 10, textAlign: 'center', borderBottom: '2px solid #e2e8f0' }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="11" style={{ textAlign: 'center', padding: 40 }}>
                    ⏳ Caricamento dati...
                  </td>
                </tr>
              ) : (
                monthlyData.map((row) => (
                  <tr 
                    key={row.month} 
                    style={{ 
                      background: row.hasDiscrepancy ? '#fef3c7' : (row.hasData ? 'white' : '#f9fafb'),
                      opacity: row.hasData ? 1 : 0.5
                    }}
                    data-testid={`row-month-${row.month}`}
                  >
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', fontWeight: 600 }}>
                      {row.monthName}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#f0f9ff' }}>
                      {row.posAuto > 0 ? formatEuro(row.posAuto) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#faf5ff' }}>
                      {row.posManual > 0 ? formatEuro(row.posManual) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#fdf2f8' }}>
                      {row.posBanca > 0 ? formatEuro(row.posBanca) : '-'}
                    </td>
                    <td style={{ 
                      padding: 10, 
                      borderBottom: '1px solid #e2e8f0', 
                      textAlign: 'right',
                      fontWeight: Math.abs(row.posDiff) > 1 ? 'bold' : 'normal',
                      color: Math.abs(row.posDiff) > 1 ? (row.posDiff > 0 ? '#16a34a' : '#dc2626') : '#666',
                      fontSize: 12
                    }}>
                      {Math.abs(row.posDiff) > 0.01 ? (
                        <span title="POS RT (XML) - POS Chiusura">{row.posDiff > 0 ? '+' : ''}{formatEuro(row.posDiff)}</span>
                      ) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#fffbeb' }}>
                      {row.corrispAuto > 0 ? formatEuro(row.corrispAuto) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#ecfdf5' }}>
                      {row.corrispManual > 0 ? formatEuro(row.corrispManual) : '-'}
                    </td>
                    <td style={{ 
                      padding: 10, 
                      borderBottom: '1px solid #e2e8f0', 
                      textAlign: 'right',
                      fontWeight: Math.abs(row.corrispDiff) > 1 ? 'bold' : 'normal',
                      color: Math.abs(row.corrispDiff) > 1 ? (row.corrispDiff > 0 ? '#16a34a' : '#dc2626') : '#666',
                      fontSize: 12
                    }}>
                      {Math.abs(row.corrispDiff) > 0.01 ? (
                        <span>{row.corrispDiff > 0 ? '+' : ''}{formatEuro(row.corrispDiff)}</span>
                      ) : '-'}
                    </td>
                    <td style={{ padding: 12, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#f0fdf4' }}>
                      {row.versamenti > 0 ? formatEuro(row.versamenti) : '-'}
                    </td>
                    <td style={{ 
                      padding: 12, 
                      borderBottom: '1px solid #e2e8f0', 
                      textAlign: 'right', 
                      background: '#e0f2fe',
                      fontWeight: 'bold',
                      color: row.saldoCassa >= 0 ? '#16a34a' : '#dc2626'
                    }}>
                      {formatEuro(row.saldoCassa)}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>
                      {row.hasData && (
                        <button
                          onClick={() => handleMonthClick(row.month)}
                          style={{
                            padding: '4px 8px',
                            background: '#1535a8',
                            color: 'white',
                            border: 'none',
                            borderRadius: 6,
                            cursor: 'pointer',
                            fontSize: 11,
                            fontWeight: 'bold'
                          }}
                          data-testid={`view-month-${row.month}`}
                        >
                          👁️
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr style={{ background: '#1e293b', color: 'white', fontWeight: 'bold', fontSize: 12 }}>
                <td style={{ padding: 10 }}>TOTALE {anno}</td>
                <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(yearTotals.posAuto)}</td>
                <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(yearTotals.posManual)}</td>
                <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(yearTotals.posBanca || 0)}</td>
                <td style={{ 
                  padding: 10, 
                  textAlign: 'right',
                  color: Math.abs(yearTotals.posAuto - yearTotals.posManual) > 1 ? '#fbbf24' : '#16a34a'
                }}>
                  {formatEuro(yearTotals.posAuto - yearTotals.posManual)}
                </td>
                <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(yearTotals.corrispettiviAuto)}</td>
                <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(yearTotals.corrispettiviManual)}</td>
                <td style={{ 
                  padding: 10, 
                  textAlign: 'right',
                  color: Math.abs(yearTotals.corrispettiviAuto - yearTotals.corrispettiviManual) > 1 ? '#fbbf24' : '#16a34a'
                }}>
                  {formatEuro(yearTotals.corrispettiviAuto - yearTotals.corrispettiviManual)}
                </td>
                <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(yearTotals.versamenti)}</td>
                <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(yearTotals.saldoCassa)}</td>
                <td style={{ padding: 10 }}></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Month View - Daily Table */}
      {viewMode === 'mese' && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }} data-testid="monthly-table">
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={{ padding: 12, textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>Data</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#dbeafe' }}>POS RT (XML)</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#ede9fe' }}>POS Reale (Tuo)</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0' }}>Diff. POS</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#fef3c7' }}>Corrisp. Auto</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#d1fae5' }}>Corrisp. Man.</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0' }}>Diff. Corr.</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#ecfdf5' }}>Versamento</th>
                <th style={{ padding: 12, textAlign: 'right', borderBottom: '2px solid #e2e8f0', background: '#e0f2fe' }}>Saldo Cassa</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="9" style={{ textAlign: 'center', padding: 40 }}>
                    ⏳ Caricamento dati...
                  </td>
                </tr>
              ) : (
                dailyComparison.map((row) => (
                  <tr 
                    key={row.date} 
                    style={{ 
                      background: row.hasDiscrepancy ? '#fef3c7' : (row.hasData ? 'white' : '#f9fafb'),
                      opacity: row.hasData ? 1 : 0.5
                    }}
                    data-testid={`row-${row.date}`}
                  >
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', fontWeight: 500 }}>
                      {formatDate(row.date)}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#f0f9ff' }}>
                      {row.posAuto > 0 ? formatEuro(row.posAuto) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#faf5ff' }}>
                      {row.posManual > 0 ? formatEuro(row.posManual) : '-'}
                    </td>
                    <td style={{ 
                      padding: 10, 
                      borderBottom: '1px solid #e2e8f0', 
                      textAlign: 'right',
                      fontWeight: Math.abs(row.posDiff) > 1 ? 'bold' : 'normal',
                      color: Math.abs(row.posDiff) > 1 ? (row.posDiff > 0 ? '#16a34a' : '#dc2626') : '#666'
                    }}>
                      {Math.abs(row.posDiff) > 0.01 ? (
                        <span>{row.posDiff > 0 ? '+' : ''}{formatEuro(row.posDiff)}</span>
                      ) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#fffbeb' }}>
                      {row.corrispettivoAuto > 0 ? formatEuro(row.corrispettivoAuto) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#ecfdf5' }}>
                      {row.corrispettivoManual > 0 ? formatEuro(row.corrispettivoManual) : '-'}
                    </td>
                    <td style={{ 
                      padding: 10, 
                      borderBottom: '1px solid #e2e8f0', 
                      textAlign: 'right',
                      fontWeight: Math.abs(row.corrispettivoDiff) > 1 ? 'bold' : 'normal',
                      color: Math.abs(row.corrispettivoDiff) > 1 ? (row.corrispettivoDiff > 0 ? '#16a34a' : '#dc2626') : '#666'
                    }}>
                      {Math.abs(row.corrispettivoDiff) > 0.01 ? (
                        <span>{row.corrispettivoDiff > 0 ? '+' : ''}{formatEuro(row.corrispettivoDiff)}</span>
                      ) : '-'}
                    </td>
                    <td style={{ padding: 10, borderBottom: '1px solid #e2e8f0', textAlign: 'right', background: '#f0fdf4' }}>
                      {row.versamento > 0 ? formatEuro(row.versamento) : '-'}
                    </td>
                    <td style={{ 
                      padding: 10, 
                      borderBottom: '1px solid #e2e8f0', 
                      textAlign: 'right', 
                      background: '#e0f2fe',
                      fontWeight: 'bold',
                      color: row.saldoCassa >= 0 ? '#16a34a' : '#dc2626'
                    }}>
                      {formatEuro(row.saldoCassa)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr style={{ background: '#1e293b', color: 'white', fontWeight: 'bold' }}>
                <td style={{ padding: 12 }}>TOTALE {monthNames[meseSelezionato - 1].toUpperCase()}</td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posAuto, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posManual, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posDiff, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.corrispettivoAuto, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.corrispettivoManual, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.corrispettivoDiff, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.versamento, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right' }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.saldoCassa, 0))}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Legend */}
      <div style={{ 
        marginTop: 20, 
        padding: 15, 
        background: '#f8fafc', 
        borderRadius: 8,
        fontSize: 13 
      }}>
        <strong>Legenda e Logica Calcoli:</strong>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 10, marginTop: 10 }}>
          <div>
            <strong style={{ color: '#1535a8' }}>POS RT (chiusura)</strong> = Σ corrispettivi.pagato_elettronico (da XML)
          </div>
          <div>
            <strong style={{ color: '#8b5cf6' }}>POS Reale (Tuo)</strong> = Σ prima_nota_cassa WHERE categoria="POS"
          </div>
          <div>
            <strong style={{ color: '#d97706' }}>Corrisp. Auto</strong> = Σ corrispettivi.totale (da XML)
          </div>
          <div>
            <strong style={{ color: '#15803d' }}>Corrisp. Man.</strong> = Σ prima_nota_cassa WHERE categoria="Corrispettivi" AND tipo="entrata"
          </div>
          <div>
            <strong style={{ color: '#16a34a' }}>Versamenti</strong> = Σ prima_nota_cassa WHERE categoria="Versamento" AND tipo="uscita"
          </div>
          <div>
            <strong style={{ color: '#0ea5e9' }}>Saldo Cassa</strong> = Σ entrate - Σ uscite (Prima Nota Cassa)
          </div>
        </div>
        <div style={{ marginTop: 10, color: '#666' }}>
          ⚠️ Righe gialle = Discrepanza &gt; €1 tra dati Auto e Manuali
        </div>
      </div>
      
      {/* Modal Versamenti */}
      <VersamentiModal />
    </PageLayout>
  );
}
