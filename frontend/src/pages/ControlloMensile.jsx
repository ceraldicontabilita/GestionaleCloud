import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, COLORS, FONT, SHADOWS, BORDER_RADIUS, formatDateIT } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import { Button, StatCard, TableWrap, Table, Th, Td } from '../components/ds';

const MONO = FONT.mono;

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
    ammontareAnnulliCount: 0,
  });

  // Daily detail data (when viewing a specific month)
  const [dailyComparison, setDailyComparison] = useState([]);

  // Dettaglio versamenti per il mese
  const [versamentiDettaglio, setVersamentiDettaglio] = useState([]);
  const [showVersamentiModal, setShowVersamentiModal] = useState(false);

  const monthNames = [
    'Gennaio',
    'Febbraio',
    'Marzo',
    'Aprile',
    'Maggio',
    'Giugno',
    'Luglio',
    'Agosto',
    'Settembre',
    'Ottobre',
    'Novembre',
    'Dicembre',
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
        data_a: endDate,
      });

      // Carica dati in parallelo da TUTTE le fonti (Cassa, Corrispettivi, Estratto Conto Banca)
      const [cassaRes, corrispRes, estrattoRes] = await Promise.all([
        api
          .get(`/api/prima-nota/cassa?${params}&limit=5000`)
          .catch(() => ({ data: { movimenti: [] } })),
        api
          .get(`/api/corrispettivi?data_da=${startDate}&data_a=${endDate}&limit=500`)
          .catch(() => ({ data: [] })),
        api
          .get(`/api/bank-statement/movements?data_da=${startDate}&data_a=${endDate}&limit=5000`)
          .catch(() => ({ data: { movements: [] } })),
      ]);

      const cassa = cassaRes.data.movimenti || [];
      const corrispettivi = Array.isArray(corrispRes.data)
        ? corrispRes.data
        : corrispRes.data.corrispettivi || [];
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
    let yearPosAuto = 0,
      yearPosManual = 0,
      yearPosBanca = 0,
      yearPosBancaCommissioni = 0;
    let yearCorrispAuto = 0,
      yearCorrispManual = 0;
    let yearVersamenti = 0,
      yearSaldoCassa = 0;
    let yearDocumentiCommerciali = 0;
    let yearAnnulli = 0;
    let yearPagatoNonRiscosso = 0,
      yearPagatoNonRiscossoCount = 0;
    let yearAmmontareAnnulli = 0,
      yearAmmontareAnnulliCount = 0;

    for (let month = 1; month <= 12; month++) {
      const monthStr = String(month).padStart(2, '0');
      const monthPrefix = `${anno}-${monthStr}`;

      // Filtra dati per questo mese
      const monthCassa = cassa.filter(m => m.data?.startsWith(monthPrefix));
      const monthCorrisp = corrispettivi.filter(c => c.data?.startsWith(monthPrefix));
      const monthEstratto = estrattoConto.filter(m => m.data?.startsWith(monthPrefix));

      // ============ POS AUTO (da Corrispettivi XML) ============
      // Il POS automatico è il campo pagato_elettronico estratto dagli XML
      const posAuto = monthCorrisp.reduce(
        (sum, c) => sum + (parseFloat(c.pagato_elettronico) || 0),
        0
      );

      // ============ DOCUMENTI COMMERCIALI (da Corrispettivi XML) ============
      // Numero totale di scontrini/ricevute emessi nel mese
      const documentiCommerciali = monthCorrisp.reduce(
        (sum, c) => sum + (parseInt(c.numero_documenti) || 0),
        0
      );

      // ============ ANNULLI (vecchio campo - per compatibilità) ============
      const annulli = monthCorrisp.reduce((sum, c) => sum + (parseInt(c.annulli) || 0), 0);

      // ============ PAGATO NON RISCOSSO (da Corrispettivi XML) ============
      // Differenza tra (Ammontare + ImportoParziale) - (PagatoContanti + PagatoElettronico)
      const corrispNonRiscosso = monthCorrisp.filter(
        c => (parseFloat(c.pagato_non_riscosso) || 0) > 0
      );
      const pagatoNonRiscosso = corrispNonRiscosso.reduce(
        (sum, c) => sum + (parseFloat(c.pagato_non_riscosso) || 0),
        0
      );
      const pagatoNonRiscossoCount = corrispNonRiscosso.length;

      // ============ AMMONTARE ANNULLI (da Corrispettivi XML - TotaleAmmontareAnnulli) ============
      const corrispAnnulli = monthCorrisp.filter(
        c => (parseFloat(c.totale_ammontare_annulli) || 0) > 0
      );
      const ammontareAnnulli = corrispAnnulli.reduce(
        (sum, c) => sum + (parseFloat(c.totale_ammontare_annulli) || 0),
        0
      );
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
      const _getDataAccreditoAttesa = dataOperazione => {
        const date = new Date(dataOperazione);
        const dayOfWeek = date.getDay(); // 0=Dom, 1=Lun, 2=Mar, 3=Mer, 4=Gio, 5=Ven, 6=Sab

        // Sfasamento: +1 giorno lavorativo
        // Ven/Sab/Dom → Lunedì
        if (dayOfWeek === 5) {
          // Venerdì
          date.setDate(date.getDate() + 3); // +3 = Lunedì
        } else if (dayOfWeek === 6) {
          // Sabato
          date.setDate(date.getDate() + 2); // +2 = Lunedì
        } else if (dayOfWeek === 0) {
          // Domenica
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
          const isVersamento =
            m.categoria === 'Versamento' ||
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

      const hasData =
        posAuto > 0 ||
        posManual > 0 ||
        posBanca > 0 ||
        corrispAuto > 0 ||
        corrispManual > 0 ||
        versamenti > 0;
      const hasDiscrepancy =
        Math.abs(posDiff) > 1 || Math.abs(corrispDiff) > 1 || Math.abs(posBancaDiff) > 1;

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
          corrispCount: monthCorrisp.length,
        },
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
      ammontareAnnulliCount: yearAmmontareAnnulliCount,
    });
  };

  /**
   * CARICA DATI MENSILI (Dettaglio Giornaliero)
   * Recupera i movimenti del mese selezionato e li mostra giorno per giorno
   */
  const loadMonthData = async month => {
    setLoading(true);
    try {
      const monthStr = String(month).padStart(2, '0');
      const daysInMonth = new Date(anno, month, 0).getDate();
      const startDate = `${anno}-${monthStr}-01`;
      const endDate = `${anno}-${monthStr}-${String(daysInMonth).padStart(2, '0')}`;

      const params = new URLSearchParams({
        data_da: startDate,
        data_a: endDate,
      });

      const [cassaRes, corrispRes] = await Promise.all([
        api
          .get(`/api/prima-nota/cassa?${params}&limit=10000`)
          .catch(() => ({ data: { movimenti: [] } })),
        api
          .get(`/api/corrispettivi?data_da=${startDate}&data_a=${endDate}&limit=500`)
          .catch(() => ({ data: [] })),
      ]);

      const cassa = cassaRes.data.movimenti || [];
      const corrispettivi = Array.isArray(corrispRes.data)
        ? corrispRes.data
        : corrispRes.data.corrispettivi || [];

      processDailyData(cassa, corrispettivi, month);

      // Estrai dettaglio versamenti del mese
      const versamentiMese = cassa.filter(m => {
        const isVersamento =
          m.categoria === 'Versamento' ||
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
      dayData.posAuto = dayCorrisp.reduce(
        (sum, c) => sum + (parseFloat(c.pagato_elettronico) || 0),
        0
      );

      // ============ DOCUMENTI COMMERCIALI (da Corrispettivi XML) ============
      dayData.documentiCommerciali = dayCorrisp.reduce(
        (sum, c) => sum + (parseInt(c.numero_documenti) || 0),
        0
      );

      // ============ POS MANUALE (da Prima Nota) ============
      dayData.posManual = dayCassa
        .filter(m => m.categoria?.toUpperCase() === 'POS' || m.source === 'excel_pos')
        .reduce((sum, m) => sum + Math.abs(parseFloat(m.importo) || 0), 0);

      // ============ CORRISPETTIVI AUTO (da XML) ============
      dayData.corrispettivoAuto = dayCorrisp.reduce(
        (sum, c) => sum + (parseFloat(c.totale) || 0),
        0
      );

      // ============ CORRISPETTIVI MANUALI ============
      dayData.corrispettivoManual = dayCassa
        .filter(m => m.categoria === 'Corrispettivi' || m.source === 'excel_corrispettivi')
        .filter(m => m.tipo === 'entrata')
        .reduce((sum, m) => sum + (parseFloat(m.importo) || 0), 0);

      // ============ VERSAMENTO ============
      dayData.versamento = dayCassa
        .filter(m => {
          const isVersamento =
            m.categoria === 'Versamento' ||
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

      dayData.hasData =
        dayData.posAuto > 0 ||
        dayData.posManual > 0 ||
        dayData.corrispettivoAuto > 0 ||
        dayData.corrispettivoManual > 0 ||
        dayData.versamento > 0 ||
        entrateGiorno > 0 ||
        usciteGiorno > 0;
      dayData.hasDiscrepancy =
        Math.abs(dayData.posDiff) > 1 || Math.abs(dayData.corrispettivoDiff) > 1;

      // Debug info
      dayData._debug = {
        cassaCount: dayCassa.length,
        corrispCount: dayCorrisp.length,
        entrateGiorno,
        usciteGiorno,
      };

      comparison.push(dayData);
    }

    setDailyComparison(comparison);
  };

  const formatDate = dateStr => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric' });
  };

  const handleMonthClick = month => {
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
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(15,39,68,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}
        onClick={() => setShowVersamentiModal(false)}
      >
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.md,
            padding: 20,
            maxWidth: 600,
            width: '90%',
            maxHeight: '80vh',
            overflowY: 'auto',
            boxShadow: SHADOWS.modal,
          }}
          onClick={e => e.stopPropagation()}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 15,
            }}
          >
            <h2 style={{ margin: 0, color: COLORS.primary }}>
              Dettaglio Versamenti - {monthNames[meseSelezionato - 1]} {anno}
            </h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowVersamentiModal(false)}
              style={{ fontSize: 16, padding: '4px 10px' }}
            >
              ✕
            </Button>
          </div>

          {versamentiDettaglio.length === 0 ? (
            <p style={{ color: COLORS.textMuted }}>Nessun versamento registrato per questo mese.</p>
          ) : (
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Data</Th>
                    <Th>Descrizione</Th>
                    <Th align="right">Importo</Th>
                  </tr>
                </thead>
                <tbody>
                  {versamentiDettaglio.map((v, i) => (
                    <tr key={i}>
                      <Td>{formatDateIT(v.data)}</Td>
                      <Td>{v.descrizione || v.categoria}</Td>
                      <Td align="right" mono style={{ fontWeight: 'bold', color: COLORS.success }}>
                        {formatEuro(Math.abs(v.importo))}
                      </Td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: COLORS.primary, color: '#fff' }}>
                    <td colSpan={2} style={{ padding: 10, fontWeight: 'bold' }}>
                      TOTALE
                    </td>
                    <td
                      style={{
                        padding: 10,
                        textAlign: 'right',
                        fontWeight: 'bold',
                        fontFamily: FONT.mono,
                      }}
                    >
                      {formatEuro(
                        versamentiDettaglio.reduce(
                          (sum, v) => sum + Math.abs(parseFloat(v.importo) || 0),
                          0
                        )
                      )}
                    </td>
                  </tr>
                </tfoot>
              </Table>
            </TableWrap>
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
      <div
        style={{
          display: 'flex',
          gap: 15,
          marginBottom: 20,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <label style={{ fontWeight: 'bold' }}>Anno:</label>
          <div
            style={{
              padding: '10px 16px',
              borderRadius: BORDER_RADIUS.sm,
              border: `1px solid ${COLORS.border}`,
              fontSize: 16,
              minWidth: 100,
              background: COLORS.bgAlt,
              color: COLORS.textMuted,
              fontWeight: 600,
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
              <Button
                variant="primary"
                size="md"
                onClick={() => {
                  if (meseSelezionato > 1) {
                    setMeseSelezionato(meseSelezionato - 1);
                  }
                }}
                disabled={meseSelezionato <= 1}
                style={{ minHeight: 40 }}
                data-testid="prev-month-btn"
              >
                ◀ {meseSelezionato > 1 ? monthNames[meseSelezionato - 2] : 'Gen'}
              </Button>

              <span
                style={{
                  fontWeight: 'bold',
                  fontSize: 16,
                  padding: '8px 16px',
                  background: COLORS.bgAlt,
                  borderRadius: BORDER_RADIUS.sm,
                  minWidth: 140,
                  textAlign: 'center',
                }}
              >
                {monthNames[meseSelezionato - 1]} {anno}
              </span>

              <Button
                variant="primary"
                size="md"
                onClick={() => {
                  if (meseSelezionato < 12) {
                    setMeseSelezionato(meseSelezionato + 1);
                  }
                  // Non cambia anno - è globale
                }}
                disabled={meseSelezionato >= 12}
                style={{ minHeight: 40 }}
                data-testid="next-month-btn"
              >
                {meseSelezionato < 12 ? monthNames[meseSelezionato] : 'Dic'} ▶
              </Button>
            </div>

            <Button
              variant="secondary"
              size="md"
              onClick={handleBackToYear}
              style={{ minHeight: 40 }}
              data-testid="back-to-year-btn"
            >
              ← Riepilogo Annuale
            </Button>

            <Button
              variant="primary"
              size="md"
              onClick={() => setShowVersamentiModal(true)}
              style={{ minHeight: 40 }}
              data-testid="show-versamenti-btn"
            >
              Versamenti
            </Button>
          </>
        )}

        {viewMode === 'anno' && (
          <span style={{ fontSize: 18, fontWeight: 'bold', marginLeft: 'auto' }}>📅 {anno}</span>
        )}
      </div>

      {/* Summary Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: 12,
          marginBottom: 25,
        }}
      >
        {[
          { icon: null, label: 'POS RT (XML)', value: formatEuro(yearTotals.posAuto), accent: 'primary' },
          {
            icon: null,
            label: 'POS Reale (Tuo)',
            value: formatEuro(yearTotals.posManual),
            accent: 'primary',
          },
          {
            icon: '🏦',
            label: 'POS Banca (PDV)',
            value: formatEuro(yearTotals.posBanca || 0),
            subtext:
              yearTotals.posBancaCommissioni > 0
                ? `Comm.: -${formatEuro(yearTotals.posBancaCommissioni)}`
                : null,
            accent: 'primary',
          },
          {
            icon: null,
            label: 'Corrisp. Auto (XML)',
            value: formatEuro(yearTotals.corrispettiviAuto),
            accent: 'primary',
          },
          {
            icon: null,
            label: 'Corrisp. Manuali',
            value: formatEuro(yearTotals.corrispettiviManual),
            accent: 'primary',
          },
          { icon: null, label: 'Versamenti', value: formatEuro(yearTotals.versamenti), accent: 'primary' },
          {
            icon: null,
            label: 'Saldo Cassa',
            value: formatEuro(yearTotals.saldoCassa),
            accent: yearTotals.saldoCassa >= 0 ? 'success' : 'danger',
          },
          {
            icon: '📄',
            label: 'Doc. Commerciali',
            value: (yearTotals.documentiCommerciali || 0).toLocaleString('it-IT'),
            accent: 'primary',
          },
          {
            icon: '🚫',
            label: 'Annulli',
            value: (yearTotals.annulli || 0).toLocaleString('it-IT'),
            subtext: yearTotals.annulli === 0 || !yearTotals.annulli ? 'N/D negli XML' : null,
            accent: yearTotals.annulli > 0 ? 'danger' : 'primary',
          },
          {
            icon: null,
            label: 'Pagato Non Riscosso',
            value: formatEuro(yearTotals.pagatoNonRiscosso || 0),
            subtext: `${yearTotals.pagatoNonRiscossoCount || 0} occorrenze`,
            accent: (yearTotals.pagatoNonRiscosso || 0) > 0 ? 'warning' : 'primary',
          },
          {
            icon: '🗑️',
            label: 'Ammontare Annulli',
            value: formatEuro(yearTotals.ammontareAnnulli || 0),
            subtext: `${yearTotals.ammontareAnnulliCount || 0} occorrenze`,
            accent: (yearTotals.ammontareAnnulli || 0) > 0 ? 'danger' : 'primary',
          },
        ].map(card => (
          <StatCard
            key={card.label}
            icon={card.icon}
            label={card.label}
            value={card.value}
            subtext={card.subtext}
            accent={card.accent}
          />
        ))}
      </div>

      {/* Info Box */}
      <div
        style={{
          background: COLORS.infoLight,
          border: `1px solid ${COLORS.info}`,
          borderRadius: BORDER_RADIUS.md,
          padding: 15,
          marginBottom: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <span style={{ fontSize: 24 }}>ℹ️</span>
        <div>
          <strong>Fonti dati:</strong>
          <br />• <strong>POS RT (chiusura)</strong> = pagato_elettronico da XML corrispettivi
          (chiusura serale RT)
          <br />• <strong>POS Reale (Tuo)</strong> = Prima Nota Cassa con categoria &quot;POS&quot;
          (inserito manualmente da te)
          <br />• <strong>🏦 POS Banca</strong> = Accrediti PDV 3757283 dall&apos;estratto conto
          bancario
          <br />• <strong>Diff. POS</strong> = POS RT - POS Reale (discrepanze giornaliere)
          <br />• <strong>Diff. Banca</strong> = POS Banca - POS Reale (riconciliazione bancaria)
          <br />• <strong>Pagato Non Riscosso</strong> = (Ammontare + ImportoParziale) - (Contanti +
          Elettronico)
          <br />• <strong>🗑️ Ammontare Annulli</strong> = TotaleAmmontareAnnulli da XML
          corrispettivi
        </div>
      </div>

      {/* Discrepancy Alert */}
      {((viewMode === 'anno' && monthlyData.some(d => d.hasDiscrepancy)) ||
        (viewMode === 'mese' && dailyComparison.some(d => d.hasDiscrepancy))) && (
        <div
          style={{
            background: COLORS.warningLight,
            border: `1px solid ${COLORS.warning}`,
            borderRadius: BORDER_RADIUS.md,
            padding: 15,
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span style={{ fontSize: 24 }}>⚠️</span>
          <div>
            <strong>Attenzione!</strong> Ci sono discrepanze tra i dati automatici (XML) e manuali.
            Le righe evidenziate in giallo richiedono verifica.
          </div>
        </div>
      )}

      {/* Year View - Monthly Table */}
      {viewMode === 'anno' && (
        <TableWrap>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: 13,
              background: COLORS.card,
              fontFamily: FONT.family,
            }}
            data-testid="yearly-table"
          >
            <thead>
              <tr>
                <Th>Mese</Th>
                <Th align="right">POS RT (XML)</Th>
                <Th align="right">POS Reale (Tuo)</Th>
                <Th align="right">🏦 POS Banca</Th>
                <Th align="right">Diff.</Th>
                <Th align="right">Corr. Auto</Th>
                <Th align="right">Corr. Man.</Th>
                <Th align="right">Diff.</Th>
                <Th align="right">Versam.</Th>
                <Th align="right">Saldo</Th>
                <Th align="center"></Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <Td colSpan="11" align="center" style={{ padding: 40 }}>
                    ⏳ Caricamento dati...
                  </Td>
                </tr>
              ) : (
                monthlyData.map(row => (
                  <tr
                    key={row.month}
                    style={{
                      background: row.hasDiscrepancy
                        ? COLORS.warningLight
                        : row.hasData
                          ? COLORS.card
                          : COLORS.bgAlt,
                      opacity: row.hasData ? 1 : 0.5,
                    }}
                    data-testid={`row-month-${row.month}`}
                  >
                    <Td style={{ fontWeight: 600 }}>{row.monthName}</Td>
                    <Td align="right" mono>
                      {row.posAuto > 0 ? formatEuro(row.posAuto) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.posManual > 0 ? formatEuro(row.posManual) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.posBanca > 0 ? formatEuro(row.posBanca) : '-'}
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: Math.abs(row.posDiff) > 1 ? 'bold' : 'normal',
                        color:
                          Math.abs(row.posDiff) > 1
                            ? row.posDiff > 0
                              ? COLORS.success
                              : COLORS.danger
                            : COLORS.textMuted,
                        fontSize: 12,
                      }}
                    >
                      {Math.abs(row.posDiff) > 0.01 ? (
                        <span title="POS RT (XML) - POS Chiusura">
                          {row.posDiff > 0 ? '+' : ''}
                          {formatEuro(row.posDiff)}
                        </span>
                      ) : (
                        '-'
                      )}
                    </Td>
                    <Td align="right" mono>
                      {row.corrispAuto > 0 ? formatEuro(row.corrispAuto) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.corrispManual > 0 ? formatEuro(row.corrispManual) : '-'}
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: Math.abs(row.corrispDiff) > 1 ? 'bold' : 'normal',
                        color:
                          Math.abs(row.corrispDiff) > 1
                            ? row.corrispDiff > 0
                              ? COLORS.success
                              : COLORS.danger
                            : COLORS.textMuted,
                        fontSize: 12,
                      }}
                    >
                      {Math.abs(row.corrispDiff) > 0.01 ? (
                        <span>
                          {row.corrispDiff > 0 ? '+' : ''}
                          {formatEuro(row.corrispDiff)}
                        </span>
                      ) : (
                        '-'
                      )}
                    </Td>
                    <Td align="right" mono style={{ padding: 12 }}>
                      {row.versamenti > 0 ? formatEuro(row.versamenti) : '-'}
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        padding: 12,
                        fontWeight: 'bold',
                        color: row.saldoCassa >= 0 ? COLORS.success : COLORS.danger,
                      }}
                    >
                      {formatEuro(row.saldoCassa)}
                    </Td>
                    <Td align="center">
                      {row.hasData && (
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => handleMonthClick(row.month)}
                          style={{ padding: '4px 8px', fontSize: 11 }}
                          data-testid={`view-month-${row.month}`}
                        >
                          👁️
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr
                style={{ background: COLORS.primary, color: '#fff', fontWeight: 'bold', fontSize: 12 }}
              >
                <td style={{ padding: 10 }}>TOTALE {anno}</td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(yearTotals.posAuto)}
                </td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(yearTotals.posManual)}
                </td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(yearTotals.posBanca || 0)}
                </td>
                <td
                  style={{
                    padding: 10,
                    textAlign: 'right',
                    fontFamily: MONO,
                    color:
                      Math.abs(yearTotals.posAuto - yearTotals.posManual) > 1
                        ? COLORS.accentLight
                        : COLORS.success,
                  }}
                >
                  {formatEuro(yearTotals.posAuto - yearTotals.posManual)}
                </td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(yearTotals.corrispettiviAuto)}
                </td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(yearTotals.corrispettiviManual)}
                </td>
                <td
                  style={{
                    padding: 10,
                    textAlign: 'right',
                    fontFamily: MONO,
                    color:
                      Math.abs(yearTotals.corrispettiviAuto - yearTotals.corrispettiviManual) > 1
                        ? COLORS.accentLight
                        : COLORS.success,
                  }}
                >
                  {formatEuro(yearTotals.corrispettiviAuto - yearTotals.corrispettiviManual)}
                </td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(yearTotals.versamenti)}
                </td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(yearTotals.saldoCassa)}
                </td>
                <td style={{ padding: 10 }}></td>
              </tr>
            </tfoot>
          </table>
        </TableWrap>
      )}

      {/* Month View - Daily Table */}
      {viewMode === 'mese' && (
        <TableWrap>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: 14,
              background: COLORS.card,
              fontFamily: FONT.family,
            }}
            data-testid="monthly-table"
          >
            <thead>
              <tr>
                <Th style={{ padding: 12 }}>Data</Th>
                <Th align="right" style={{ padding: 12 }}>
                  POS RT (XML)
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  POS Reale (Tuo)
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Diff. POS
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Corrisp. Auto
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Corrisp. Man.
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Diff. Corr.
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Versamento
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Saldo Cassa
                </Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <Td colSpan="9" align="center" style={{ padding: 40 }}>
                    ⏳ Caricamento dati...
                  </Td>
                </tr>
              ) : (
                dailyComparison.map(row => (
                  <tr
                    key={row.date}
                    style={{
                      background: row.hasDiscrepancy
                        ? COLORS.warningLight
                        : row.hasData
                          ? COLORS.card
                          : COLORS.bgAlt,
                      opacity: row.hasData ? 1 : 0.5,
                    }}
                    data-testid={`row-${row.date}`}
                  >
                    <Td style={{ fontWeight: 500 }}>{formatDate(row.date)}</Td>
                    <Td align="right" mono>
                      {row.posAuto > 0 ? formatEuro(row.posAuto) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.posManual > 0 ? formatEuro(row.posManual) : '-'}
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: Math.abs(row.posDiff) > 1 ? 'bold' : 'normal',
                        color:
                          Math.abs(row.posDiff) > 1
                            ? row.posDiff > 0
                              ? COLORS.success
                              : COLORS.danger
                            : COLORS.textMuted,
                      }}
                    >
                      {Math.abs(row.posDiff) > 0.01 ? (
                        <span>
                          {row.posDiff > 0 ? '+' : ''}
                          {formatEuro(row.posDiff)}
                        </span>
                      ) : (
                        '-'
                      )}
                    </Td>
                    <Td align="right" mono>
                      {row.corrispettivoAuto > 0 ? formatEuro(row.corrispettivoAuto) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.corrispettivoManual > 0 ? formatEuro(row.corrispettivoManual) : '-'}
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: Math.abs(row.corrispettivoDiff) > 1 ? 'bold' : 'normal',
                        color:
                          Math.abs(row.corrispettivoDiff) > 1
                            ? row.corrispettivoDiff > 0
                              ? COLORS.success
                              : COLORS.danger
                            : COLORS.textMuted,
                      }}
                    >
                      {Math.abs(row.corrispettivoDiff) > 0.01 ? (
                        <span>
                          {row.corrispettivoDiff > 0 ? '+' : ''}
                          {formatEuro(row.corrispettivoDiff)}
                        </span>
                      ) : (
                        '-'
                      )}
                    </Td>
                    <Td align="right" mono>
                      {row.versamento > 0 ? formatEuro(row.versamento) : '-'}
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: 'bold',
                        color: row.saldoCassa >= 0 ? COLORS.success : COLORS.danger,
                      }}
                    >
                      {formatEuro(row.saldoCassa)}
                    </Td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr style={{ background: COLORS.primary, color: '#fff', fontWeight: 'bold' }}>
                <td style={{ padding: 12 }}>
                  TOTALE {monthNames[meseSelezionato - 1].toUpperCase()}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posAuto, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posManual, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posDiff, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.corrispettivoAuto, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.corrispettivoManual, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.corrispettivoDiff, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.versamento, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.saldoCassa, 0))}
                </td>
              </tr>
            </tfoot>
          </table>
        </TableWrap>
      )}

      {/* Legend */}
      <div
        style={{
          marginTop: 20,
          padding: 15,
          background: COLORS.bgAlt,
          borderRadius: BORDER_RADIUS.md,
          fontSize: 13,
        }}
      >
        <strong>Legenda e Logica Calcoli:</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: 10,
            marginTop: 10,
          }}
        >
          <div>
            <strong style={{ color: COLORS.primary }}>POS RT (chiusura)</strong> = Σ
            corrispettivi.pagato_elettronico (da XML)
          </div>
          <div>
            <strong style={{ color: COLORS.primary }}>POS Reale (Tuo)</strong> = Σ prima_nota_cassa
            WHERE categoria="POS"
          </div>
          <div>
            <strong style={{ color: COLORS.warning }}>Corrisp. Auto</strong> = Σ corrispettivi.totale
            (da XML)
          </div>
          <div>
            <strong style={{ color: COLORS.success }}>Corrisp. Man.</strong> = Σ prima_nota_cassa
            WHERE categoria="Corrispettivi" AND tipo="entrata"
          </div>
          <div>
            <strong style={{ color: COLORS.success }}>Versamenti</strong> = Σ prima_nota_cassa WHERE
            categoria="Versamento" AND tipo="uscita"
          </div>
          <div>
            <strong style={{ color: COLORS.info }}>Saldo Cassa</strong> = Σ entrate - Σ uscite (Prima
            Nota Cassa)
          </div>
        </div>
        <div style={{ marginTop: 10, color: COLORS.textMuted }}>
          ⚠️ Righe gialle = Discrepanza &gt; €1 tra dati Auto e Manuali
        </div>
      </div>

      {/* Modal Versamenti */}
      <VersamentiModal />
    </PageLayout>
  );
}
