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
 * SCOPO: Confrontare XML RT, chiusura POS reale, accrediti bancari e Prima Nota.
 *
 * FONTI DATI:
 * -----------
 * 1. MOTORE POS A DUE FASI (/api/pos-corrispettivi/controllo-due-fasi)
 *    - XML RT = pagamento elettronico fiscale
 *    - POS reale = chiusura serale manuale
 *    - POS banca = accrediti reali associati al giorno vendita dalla causale
 *
 * 2. PRIMA NOTA CASSA (collection: prima_nota_cassa)
 *    - categoria "POS" = POS Manuale Reale (inserito da te la sera)
 *    - categoria "Corrispettivi" = Corrispettivi Manuali
 *    - categoria "Versamento" con tipo "uscita" = Versamenti in banca
 *    - Saldo Cassa = Σ entrate - Σ uscite
 *
 * 3. CORRISPETTIVI XML e REGISTRO DEFINITIVO
 *    - totali, documenti, annulli e documenti ancora da registrare
 *
 * COLONNE TABELLA:
 * ----------------
 * | Mese/Data | POS Agenzia | POS Chiusura | Diff. POS | Corrisp. Auto | Corrisp. Man. | Diff. Corr. | Versamenti | Saldo Cassa | Dettagli |
 *
 * CALCOLI:
 * --------
 * - POS RT / POS Reale / POS Banca e relativi stati arrivano dal motore canonico
 * - Corrisp. Auto = Σ corrispettivi.totale (da XML)
 * - Corrisp. Man. = Σ prima_nota_cassa WHERE categoria = "Corrispettivi" AND tipo = "entrata"
 * - Diff. Corr. = Corrisp. Auto - Corrisp. Man.
 * - Versamenti = Σ prima_nota_cassa WHERE (categoria = "Versamento" OR descrizione CONTAINS "versamento") AND tipo = "uscita"
 * - Saldo Cassa = Σ entrate - Σ uscite (tutti i movimenti cassa del periodo)
 *
 * NOTA IMPORTANTE:
 * ----------------
 * - Una differenza non viene risolta né confermata dal frontend.
 * - XML, chiusura reale e banca restano tre evidenze distinte e tracciabili.
 * =====================================================================
 */

export default function ControlloMensile() {
  const [loading, setLoading] = useState(true);
  const [fontiErrore, setFontiErrore] = useState([]);
  const { anno } = useAnnoGlobale(); // Anno dal contesto globale
  const [viewMode, setViewMode] = useState('anno'); // 'anno' or 'mese'
  const [meseSelezionato, setMeseSelezionato] = useState(null);

  // Monthly summary data
  const [monthlyData, setMonthlyData] = useState([]);
  const [yearTotals, setYearTotals] = useState({
    posAuto: 0,
    posManual: 0,
    posBanca: 0,
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
  const [completezzaRegistro, setCompletezzaRegistro] = useState({
    scritture_registrate: 0,
    fatture_da_registrare: 0,
    corrispettivi_da_registrare: 0,
    documenti_da_registrare: 0,
    completo: false,
  });

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

      // Il motore POS a due fasi è la fonte canonica per XML, chiusura
      // serale e accrediti banca. Non replichiamo qui le sue regole.
      // Con allSettled si distingue quale fonte è caduta: un errore del servizio
      // non deve sparire dietro a un mese "senza dati".
      const fonti = [
        { nome: 'Cassa', vuoto: { data: { movimenti: [] } },
          req: api.get(`/api/prima-nota/cassa?${params}&limit=10000`) },
        { nome: 'Corrispettivi', vuoto: { data: [] },
          req: api.get(`/api/corrispettivi?data_da=${startDate}&data_a=${endDate}&limit=10000`) },
        { nome: 'Controllo POS-banca', vuoto: { data: { giorni: [] } },
          req: api.get(`/api/pos-corrispettivi/controllo-due-fasi?anno=${anno}`) },
        { nome: 'Registro contabile', vuoto: { data: { completezza_registro: null } },
          req: api.get(`/api/contabilita-gestionale/bilancio-verifica?anno=${anno}`) },
      ];
      const esiti = await Promise.allSettled(fonti.map(f => f.req));
      const falliteNomi = [];
      const [cassaRes, corrispRes, controlloPosRes, registroRes] = esiti.map((e, i) => {
        if (e.status === 'fulfilled') return e.value;
        falliteNomi.push(fonti[i].nome);
        return fonti[i].vuoto;
      });
      setFontiErrore(falliteNomi);

      const cassa = cassaRes.data.movimenti || [];
      const corrispettivi = Array.isArray(corrispRes.data)
        ? corrispRes.data
        : corrispRes.data.corrispettivi || [];
      const controlloPos = controlloPosRes.data.giorni || [];
      setCompletezzaRegistro(
        registroRes.data.completezza_registro || {
          scritture_registrate: 0,
          fatture_da_registrare: 0,
          corrispettivi_da_registrare: 0,
          documenti_da_registrare: 0,
          completo: false,
        }
      );

      processYearData(cassa, corrispettivi, controlloPos);
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
  const processYearData = (cassa, corrispettivi, controlloPos = []) => {
    const monthly = [];
    let yearPosAuto = 0,
      yearPosManual = 0,
      yearPosBanca = 0;
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
      const monthPos = controlloPos.filter(g => g.data?.startsWith(monthPrefix));

      // Valori già controllati dal motore canonico a due fasi.
      const posAuto = monthPos.reduce(
        (sum, g) => sum + (parseFloat(g.xml_elettronico) || 0),
        0
      );
      const posManual = monthPos.reduce(
        (sum, g) => sum + (parseFloat(g.pos_manuale) || 0),
        0
      );
      const posBanca = monthPos.reduce(
        (sum, g) => sum + (parseFloat(g.accredito_banca) || 0),
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
      const posFiscalIssue = monthPos.some(g =>
        ['differenza_in_piu_da_registrare', 'in_attesa_xml'].includes(g.stato_serale)
      );
      const posBankIssue = monthPos.some(g =>
        ['mancante', 'differenza', 'extra'].includes(g.stato_accredito)
      );

      const hasData =
        posAuto > 0 ||
        posManual > 0 ||
        posBanca > 0 ||
        corrispAuto > 0 ||
        corrispManual > 0 ||
        versamenti > 0;
      const hasDiscrepancy = posFiscalIssue || posBankIssue || Math.abs(corrispDiff) > 1;

      monthly.push({
        month,
        monthName: monthNames[month - 1],
        posAuto,
        posManual,
        posBanca,
        posDiff,
        posBancaDiff,
        posFiscalIssue,
        posBankIssue,
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
          controlloPosCount: monthPos.length,
          corrispCount: monthCorrisp.length,
        },
      });

      yearPosAuto += posAuto;
      yearPosManual += posManual;
      yearPosBanca += posBanca;
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

      const fonti = [
        { nome: 'Cassa', vuoto: { data: { movimenti: [] } },
          req: api.get(`/api/prima-nota/cassa?${params}&limit=10000`) },
        { nome: 'Corrispettivi', vuoto: { data: [] },
          req: api.get(`/api/corrispettivi?data_da=${startDate}&data_a=${endDate}&limit=10000`) },
        { nome: 'Controllo POS-banca', vuoto: { data: { giorni: [] } },
          req: api.get(
            `/api/pos-corrispettivi/controllo-due-fasi?data_da=${startDate}&data_a=${endDate}`
          ) },
      ];
      const esiti = await Promise.allSettled(fonti.map(f => f.req));
      const falliteNomi = [];
      const [cassaRes, corrispRes, controlloPosRes] = esiti.map((e, i) => {
        if (e.status === 'fulfilled') return e.value;
        falliteNomi.push(fonti[i].nome);
        return fonti[i].vuoto;
      });
      setFontiErrore(falliteNomi);

      const cassa = cassaRes.data.movimenti || [];
      const corrispettivi = Array.isArray(corrispRes.data)
        ? corrispRes.data
        : corrispRes.data.corrispettivi || [];
      const controlloPos = controlloPosRes.data.giorni || [];

      processDailyData(cassa, corrispettivi, controlloPos, month);

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
  const processDailyData = (cassa, corrispettivi, controlloPos, month) => {
    const daysInMonth = new Date(anno, month, 0).getDate();
    const comparison = [];
    const monthStr = String(month).padStart(2, '0');

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${anno}-${monthStr}-${String(day).padStart(2, '0')}`;
      const dayData = { date: dateStr, day };

      // Filtra movimenti del giorno
      const dayCassa = cassa.filter(m => m.data === dateStr);
      const dayCorrisp = corrispettivi.filter(c => c.data === dateStr);
      const dayPos = controlloPos.find(g => g.data === dateStr);

      // Valori già verificati dal motore canonico POS/XML/banca.
      dayData.posAuto = parseFloat(dayPos?.xml_elettronico) || 0;
      dayData.posManual = parseFloat(dayPos?.pos_manuale) || 0;
      dayData.posBanca = parseFloat(dayPos?.accredito_banca) || 0;
      dayData.posDiff = parseFloat(dayPos?.diff_serale) || 0;
      dayData.posBancaDiff = parseFloat(dayPos?.diff_accredito) || 0;
      dayData.statoSerale = dayPos?.stato_serale || 'no_dati';
      dayData.statoBanca = dayPos?.stato_accredito || 'no_pos_manuale';

      // ============ DOCUMENTI COMMERCIALI (da Corrispettivi XML) ============
      dayData.documentiCommerciali = dayCorrisp.reduce(
        (sum, c) => sum + (parseInt(c.numero_documenti) || 0),
        0
      );

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
      dayData.corrispettivoDiff = dayData.corrispettivoAuto - dayData.corrispettivoManual;

      dayData.hasData =
        dayData.posAuto > 0 ||
        dayData.posManual > 0 ||
        dayData.posBanca > 0 ||
        dayData.corrispettivoAuto > 0 ||
        dayData.corrispettivoManual > 0 ||
        dayData.versamento > 0 ||
        entrateGiorno > 0 ||
        usciteGiorno > 0;
      dayData.hasDiscrepancy =
        ['differenza_in_piu_da_registrare', 'in_attesa_xml'].includes(dayData.statoSerale) ||
        ['mancante', 'differenza', 'extra'].includes(dayData.statoBanca) ||
        Math.abs(dayData.corrispettivoDiff) > 1;

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
          background: 'rgba(42, 51, 41,0.5)',
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
      title="Controllo POS"
      subtitle="Registratore, chiusura serale e banca."
    >
      {fontiErrore.length > 0 && (
        <div
          style={{
            background: COLORS.dangerLight, color: COLORS.danger,
            border: `1px solid ${COLORS.danger}`, borderRadius: BORDER_RADIUS.md,
            padding: '10px 14px', marginBottom: 16, fontSize: 14,
          }}
        >
          ⚠️ Errore nel caricamento di: {fontiErrore.join(', ')}. I totali possono essere
          incompleti — non è detto che il periodo sia senza movimenti. Riprova.
        </div>
      )}

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
          <span style={{ fontSize: 16, fontWeight: 700, marginLeft: 'auto' }}>{anno}</span>
        )}
      </div>

      {viewMode === 'anno' && (
        <p data-testid="controllo-sintesi" style={{ margin: '0 0 12px', fontSize: 15 }}>
          {monthlyData.filter(d => d.hasDiscrepancy).length === 0
            ? `${anno}: nessun mese da verificare.`
            : `${anno}: ${monthlyData.filter(d => d.hasDiscrepancy).length} mesi da verificare.`}
        </p>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 12 }}>
        <StatCard label="Registratore (RT)" value={formatEuro(yearTotals.posAuto)} accent="primary" />
        <StatCard label="Chiusura serale" value={formatEuro(yearTotals.posManual)} accent="primary" />
        <StatCard label="In banca" value={formatEuro(yearTotals.posBanca || 0)} accent="primary" />
      </div>
      <p style={{ margin: '0 0 16px', fontSize: 13, color: COLORS.textMuted }}>
        Fatture da registrare {(completezzaRegistro.fatture_da_registrare || 0).toLocaleString('it-IT')}
        {completezzaRegistro.corrispettivi_da_registrare ? ` · corrispettivi da registrare ${completezzaRegistro.corrispettivi_da_registrare}` : ''}
        {' · '}
        <a href="/prima-nota#sezione=cassa" style={{ color: '#5b7a6b', fontWeight: 700 }}>Saldo in Prima Nota</a>
      </p>

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
                <Th align="right">Registratore</Th>
                <Th align="right">Chiusura</Th>
                <Th align="right">Banca</Th>
                <Th align="center">RT</Th>
                <Th align="center">Banca</Th>
                <Th align="center"></Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <Td colSpan="7" align="center" style={{ padding: 40 }}>
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
                    <Td align="center">{row.posFiscalIssue ? 'Da vedere' : row.hasData ? 'Ok' : '—'}</Td>
                    <Td align="center">{row.posBankIssue ? 'Da vedere' : row.hasData ? 'Ok' : '—'}</Td>
                    <Td align="center">
                      {row.hasData && (
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => handleMonthClick(row.month)}
                          style={{ padding: '4px 8px', fontSize: 11 }}
                          data-testid={`view-month-${row.month}`}
                        >
                          Giorni
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
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>{formatEuro(yearTotals.posAuto)}</td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>{formatEuro(yearTotals.posManual)}</td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>{formatEuro(yearTotals.posBanca || 0)}</td>
                <td></td>
                <td></td>
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
                  POS Banca
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Diff. RT
                </Th>
                <Th align="right" style={{ padding: 12 }}>
                  Diff. Banca
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
                  <Td colSpan="11" align="center" style={{ padding: 40 }}>
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
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: ['mancante', 'differenza', 'extra'].includes(row.statoBanca)
                          ? 'bold'
                          : 'normal',
                        color: ['mancante', 'differenza', 'extra'].includes(row.statoBanca)
                          ? COLORS.danger
                          : COLORS.textMuted,
                      }}
                    >
                      {Math.abs(row.posBancaDiff) > 0.01 ? (
                        <span>
                          {row.posBancaDiff > 0 ? '+' : ''}
                          {formatEuro(row.posBancaDiff)}
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
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posBanca, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posDiff, 0))}
                </td>
                <td style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                  {formatEuro(dailyComparison.reduce((s, d) => s + d.posBancaDiff, 0))}
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

      {/* Modal Versamenti */}
      <VersamentiModal />
    </PageLayout>
  );
}
