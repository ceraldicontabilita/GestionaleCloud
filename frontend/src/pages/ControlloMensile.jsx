import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, COLORS, FONT, SHADOWS, BORDER_RADIUS, formatDateIT } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import { Button, Esito, StatCard, TableWrap, Table, Th, Td } from '../components/ds';

/**
 * I due terminali restano separati: NUMIA (chiusura serale scritta a mano)
 * accredita su BPM, SumUp (letto dall'app) paga sulla carta Mastercard
 * SumUp. La banca BPM si confronta quindi col solo NUMIA; il registratore,
 * che somma tutto l'elettronico, con NUMIA + SumUp.
 */
export function circuitiGiorno(g) {
  const c = (g && g.pos_per_circuito) || {};
  return { numia: parseFloat(c.numia) || 0, sumup: parseFloat(c.sumup) || 0 };
}

/**
 * Totali di Cassa e corrispettivi XML del periodo: li calcola il server
 * (``/api/prima-nota/controllo-mensile``, prima_nota_module/controllo_mensile.py)
 * sulle stesse righe che la pagina scaricava. In Cassa entra solo la quota
 * contanti dell'XML: ``differenza_contanti`` e' contanti XML − corrispettivi in
 * Cassa, ``null`` se un XML del periodo non dichiara i contanti.
 */
const PERIODO_VUOTO = {
  corrispettivi_xml: 0, contanti_xml: 0, xml_senza_contanti: 0, documenti_commerciali: 0,
  annulli: 0, pagato_non_riscosso: 0, pagato_non_riscosso_count: 0, ammontare_annulli: 0,
  ammontare_annulli_count: 0, corrispettivi_cassa: 0, differenza_contanti: 0, versamenti: 0,
  entrate_cassa: 0, uscite_cassa: 0, saldo_cassa: 0, movimenti_cassa: 0, righe_xml: 0,
};

export function periodoDa(riepilogo, periodo) {
  return (riepilogo?.periodi || []).find(p => p.periodo === periodo) || { ...PERIODO_VUOTO, periodo };
}

/** Esito di un giorno o di un mese secondo la regola unica del colore. */
export function esitoRiga({ hasData, intervento, verificare }) {
  if (intervento) return 'intervento';
  if (verificare) return 'verificare';
  return hasData ? 'chiuso' : 'nessun_dato';
}

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
 * CALCOLI (le somme di Cassa e XML le fa il server,
 * GET /api/prima-nota/controllo-mensile; il browser non scarica le righe):
 * --------
 * - POS RT / POS Reale / POS Banca e relativi stati arrivano dal motore canonico
 * - Corrisp. Auto = Σ corrispettivi.totale (da XML)
 * - Corrisp. Man. = Σ prima_nota_cassa WHERE categoria = "Corrispettivi" AND tipo = "entrata"
 * - Diff. Corr. = Σ corrispettivi.pagato_contanti (XML) - Corrisp. Man.: in Cassa
 *   entra solo la quota contanti, mai il totale (la quota POS va in Banca)
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
      // Il motore POS a due fasi è la fonte canonica per XML, chiusura
      // serale e accrediti banca. Non replichiamo qui le sue regole.
      // Cassa e corrispettivi XML arrivano già sommati per mese dal server:
      // la pagina non scarica più le singole righe.
      // Con allSettled si distingue quale fonte è caduta: un errore del servizio
      // non deve sparire dietro a un mese "senza dati".
      const fonti = [
        { nome: 'Cassa e corrispettivi', vuoto: { data: { periodi: [] } },
          req: api.get(`/api/prima-nota/controllo-mensile?anno=${anno}`) },
        { nome: 'Controllo POS-banca', vuoto: { data: { giorni: [] } },
          req: api.get(`/api/pos-corrispettivi/controllo-due-fasi?anno=${anno}`) },
        { nome: 'Registro contabile', vuoto: { data: { completezza_registro: null } },
          req: api.get(`/api/contabilita-gestionale/bilancio-verifica?anno=${anno}`) },
      ];
      const esiti = await Promise.allSettled(fonti.map(f => f.req));
      const falliteNomi = [];
      const [riepilogoRes, controlloPosRes, registroRes] = esiti.map((e, i) => {
        if (e.status === 'fulfilled') return e.value;
        falliteNomi.push(fonti[i].nome);
        return fonti[i].vuoto;
      });
      setFontiErrore(falliteNomi);

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

      processYearData(riepilogoRes.data, controlloPos);
    } catch (error) {
      console.error('Error loading year data:', error);
    } finally {
      setLoading(false);
    }
  };

  /**
   * PROCESSA DATI ANNUALI
   * Mette accanto, mese per mese, i totali del server (Cassa, XML) e i giorni
   * del motore POS a due fasi (POS RT, POS reale, POS banca).
   */
  const processYearData = (riepilogo, controlloPos = []) => {
    const monthly = [];
    let yearPosAuto = 0,
      yearPosManual = 0,
      yearPosBanca = 0,
      yearPosNumia = 0,
      yearPosSumup = 0;

    for (let month = 1; month <= 12; month++) {
      const monthStr = String(month).padStart(2, '0');
      const monthPrefix = `${anno}-${monthStr}`;
      const periodo = periodoDa(riepilogo, monthPrefix);
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
      const posNumia = monthPos.reduce((sum, g) => sum + circuitiGiorno(g).numia, 0);
      const posSumup = monthPos.reduce((sum, g) => sum + circuitiGiorno(g).sumup, 0);

      const corrispAuto = periodo.corrispettivi_xml;
      const corrispManual = periodo.corrispettivi_cassa;
      const versamenti = periodo.versamenti;
      const saldoCassa = periodo.saldo_cassa;

      // ============ DIFFERENZE ============
      // CONTROLLO GIORNALIERO: POS XML (chiusura serale RT) vs POS Manuale (tuo incasso reale)
      const posDiff = posAuto - posManual;
      // RICONCILIAZIONE BANCARIA: POS arrivato in banca vs POS Manuale (tuo incasso reale)
      const posBancaDiff = posBanca - posManual; // Banca vs TUO dato reale
      // In Cassa entra solo la quota contanti: il confronto e' con quella.
      const corrispDiff = periodo.differenza_contanti;
      const posFiscalIssue = monthPos.some(g =>
        ['differenza_in_piu_da_registrare', 'in_attesa_xml'].includes(g.stato_serale)
      );
      const posBankIssue = monthPos.some(g =>
        ['mancante', 'differenza', 'extra'].includes(g.stato_accredito)
      );
      const esitoRegistratore = esitoRiga({
        hasData: monthPos.length > 0,
        intervento: monthPos.some(g => g.stato_serale === 'differenza_in_piu_da_registrare'),
        verificare: monthPos.some(g => g.stato_serale === 'in_attesa_xml'),
      });
      const esitoBanca = esitoRiga({
        hasData: posNumia > 0,
        intervento: monthPos.some(g => g.stato_accredito === 'mancante'),
        verificare: monthPos.some(g => ['differenza', 'extra'].includes(g.stato_accredito)),
      });

      const hasData =
        posAuto > 0 ||
        posManual > 0 ||
        posBanca > 0 ||
        corrispAuto > 0 ||
        corrispManual > 0 ||
        versamenti > 0;
      const hasDiscrepancy =
        posFiscalIssue || posBankIssue || (corrispDiff !== null && Math.abs(corrispDiff) > 1);

      monthly.push({
        month,
        monthName: monthNames[month - 1],
        posAuto,
        posManual,
        posBanca,
        posNumia,
        posSumup,
        esitoRegistratore,
        esitoBanca,
        posDiff,
        posBancaDiff,
        posFiscalIssue,
        posBankIssue,
        corrispAuto,
        corrispManual,
        corrispDiff,
        versamenti,
        saldoCassa,
        documentiCommerciali: periodo.documenti_commerciali,
        annulli: periodo.annulli,
        pagatoNonRiscosso: periodo.pagato_non_riscosso,
        pagatoNonRiscossoCount: periodo.pagato_non_riscosso_count,
        ammontareAnnulli: periodo.ammontare_annulli,
        ammontareAnnulliCount: periodo.ammontare_annulli_count,
        hasData,
        hasDiscrepancy,
      });

      yearPosAuto += posAuto;
      yearPosManual += posManual;
      yearPosBanca += posBanca;
      yearPosNumia += posNumia;
      yearPosSumup += posSumup;
    }

    // Totali dell'anno di Cassa e XML: quelli del server, sulle stesse righe.
    const totale = riepilogo?.totale || PERIODO_VUOTO;
    setMonthlyData(monthly);
    setYearTotals({
      posAuto: yearPosAuto,
      posManual: yearPosManual,
      posBanca: yearPosBanca,
      posNumia: yearPosNumia,
      posSumup: yearPosSumup,
      corrispettiviAuto: totale.corrispettivi_xml,
      corrispettiviManual: totale.corrispettivi_cassa,
      versamenti: totale.versamenti,
      saldoCassa: totale.saldo_cassa,
      documentiCommerciali: totale.documenti_commerciali,
      annulli: totale.annulli,
      pagatoNonRiscosso: totale.pagato_non_riscosso,
      pagatoNonRiscossoCount: totale.pagato_non_riscosso_count,
      ammontareAnnulli: totale.ammontare_annulli,
      ammontareAnnulliCount: totale.ammontare_annulli_count,
    });
  };

  /**
   * CARICA DATI MENSILI (Dettaglio Giornaliero)
   * Totali del server giorno per giorno e dettaglio dei versamenti del mese.
   */
  const loadMonthData = async month => {
    setLoading(true);
    try {
      const monthStr = String(month).padStart(2, '0');
      const daysInMonth = new Date(anno, month, 0).getDate();
      const startDate = `${anno}-${monthStr}-01`;
      const endDate = `${anno}-${monthStr}-${String(daysInMonth).padStart(2, '0')}`;

      const fonti = [
        { nome: 'Cassa e corrispettivi', vuoto: { data: { periodi: [], versamenti_dettaglio: [] } },
          req: api.get(`/api/prima-nota/controllo-mensile?anno=${anno}&mese=${month}`) },
        { nome: 'Controllo POS-banca', vuoto: { data: { giorni: [] } },
          req: api.get(
            `/api/pos-corrispettivi/controllo-due-fasi?data_da=${startDate}&data_a=${endDate}`
          ) },
      ];
      const esiti = await Promise.allSettled(fonti.map(f => f.req));
      const falliteNomi = [];
      const [riepilogoRes, controlloPosRes] = esiti.map((e, i) => {
        if (e.status === 'fulfilled') return e.value;
        falliteNomi.push(fonti[i].nome);
        return fonti[i].vuoto;
      });
      setFontiErrore(falliteNomi);

      const controlloPos = controlloPosRes.data.giorni || [];
      processDailyData(riepilogoRes.data, controlloPos, month);
      setVersamentiDettaglio(riepilogoRes.data.versamenti_dettaglio || []);
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
  const processDailyData = (riepilogo, controlloPos, month) => {
    const daysInMonth = new Date(anno, month, 0).getDate();
    const comparison = [];
    const monthStr = String(month).padStart(2, '0');

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${anno}-${monthStr}-${String(day).padStart(2, '0')}`;
      const dayData = { date: dateStr, day };
      const periodo = periodoDa(riepilogo, dateStr);
      const dayPos = controlloPos.find(g => g.data === dateStr);

      // Valori già verificati dal motore canonico POS/XML/banca.
      dayData.posAuto = parseFloat(dayPos?.xml_elettronico) || 0;
      dayData.posManual = parseFloat(dayPos?.pos_manuale) || 0;
      dayData.posBanca = parseFloat(dayPos?.accredito_banca) || 0;
      dayData.posNumia = circuitiGiorno(dayPos).numia;
      dayData.posSumup = circuitiGiorno(dayPos).sumup;
      dayData.posDiff = parseFloat(dayPos?.diff_serale) || 0;
      dayData.posBancaDiff = parseFloat(dayPos?.diff_accredito) || 0;
      dayData.statoSerale = dayPos?.stato_serale || 'no_dati';
      dayData.statoBanca = dayPos?.stato_accredito || 'no_pos_manuale';

      dayData.documentiCommerciali = periodo.documenti_commerciali;
      dayData.corrispettivoAuto = periodo.corrispettivi_xml;
      dayData.corrispettivoManual = periodo.corrispettivi_cassa;
      dayData.versamento = periodo.versamenti;
      dayData.saldoCassa = periodo.saldo_cassa;
      // In Cassa entra solo la quota contanti dell'XML, mai il totale.
      dayData.corrispettivoDiff = periodo.differenza_contanti;

      dayData.hasData =
        dayData.posAuto > 0 ||
        dayData.posManual > 0 ||
        dayData.posBanca > 0 ||
        dayData.corrispettivoAuto > 0 ||
        dayData.corrispettivoManual > 0 ||
        dayData.versamento > 0 ||
        periodo.entrate_cassa > 0 ||
        periodo.uscite_cassa > 0;
      dayData.hasDiscrepancy =
        ['differenza_in_piu_da_registrare', 'in_attesa_xml'].includes(dayData.statoSerale) ||
        ['mancante', 'differenza', 'extra'].includes(dayData.statoBanca) ||
        (dayData.corrispettivoDiff !== null && Math.abs(dayData.corrispettivoDiff) > 1);
      dayData.esito = esitoRiga({
        hasData: dayData.hasData,
        intervento: dayData.statoSerale === 'differenza_in_piu_da_registrare' || dayData.statoBanca === 'mancante',
        verificare: dayData.hasDiscrepancy,
      });

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
          background: 'rgba(20, 20, 19,0.5)',
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
            <h2 style={{ margin: 0, color: COLORS.text }}>
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
    <PageLayout title="Controllo mensile">
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
        <StatCard label="Elettronico secondo il registratore" value={formatEuro(yearTotals.posAuto)} accent="primary" />
        <StatCard label="POS Numia, chiusura serale" value={formatEuro(yearTotals.posNumia || 0)} accent="primary" />
        <StatCard label="POS SumUp, dall'app" value={formatEuro(yearTotals.posSumup || 0)} accent="primary" />
        <StatCard label="Accreditato su BPM" subtext="Solo Numia: SumUp paga sulla sua carta" value={formatEuro(yearTotals.posBanca || 0)} accent="primary" />
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
            <strong>Attenzione:</strong> alcuni {viewMode === 'anno' ? 'mesi' : 'giorni'} non tornano.
            La colonna «Esito» dice quali: «Da sistemare» serve un intervento, «Da verificare» va guardato.
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
                <Th align="right">Elettronico secondo il registratore</Th>
                <Th align="right">POS Numia, chiusura serale</Th>
                <Th align="right">POS SumUp, dall'app</Th>
                <Th align="right">Accreditato su BPM</Th>
                <Th align="center">Registratore contro terminali</Th>
                <Th align="center">BPM contro Numia</Th>
                <Th align="center"></Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <Td colSpan="8" align="center" style={{ padding: 40 }}>
                    Caricamento dei dati…
                  </Td>
                </tr>
              ) : (
                monthlyData.map(row => (
                  <tr
                    key={row.month}
                    style={{ background: COLORS.card, borderBottom: `1px solid ${COLORS.border}` }}
                    data-testid={`row-month-${row.month}`}
                  >
                    <Td style={{ fontWeight: 600 }}>{row.monthName}</Td>
                    <Td align="right" mono>
                      {row.posAuto > 0 ? formatEuro(row.posAuto) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.posNumia > 0 ? formatEuro(row.posNumia) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.posSumup > 0 ? formatEuro(row.posSumup) : '-'}
                    </Td>
                    <Td align="right" mono>
                      {row.posBanca > 0 ? formatEuro(row.posBanca) : '-'}
                    </Td>
                    <Td align="center"><Esito esito={row.esitoRegistratore} /></Td>
                    <Td align="center"><Esito esito={row.esitoBanca} /></Td>
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
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>{formatEuro(yearTotals.posNumia || 0)}</td>
                <td style={{ padding: 10, textAlign: 'right', fontFamily: MONO }}>{formatEuro(yearTotals.posSumup || 0)}</td>
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
                <Th align="right" style={{ padding: 12 }}>Elettronico secondo il registratore</Th>
                <Th align="right" style={{ padding: 12 }}>POS Numia, chiusura serale</Th>
                <Th align="right" style={{ padding: 12 }}>POS SumUp, dall'app</Th>
                <Th align="right" style={{ padding: 12 }}>Accreditato su BPM</Th>
                <Th align="right" style={{ padding: 12 }}>Registratore − (Numia + SumUp)</Th>
                <Th align="right" style={{ padding: 12 }}>BPM − Numia</Th>
                <Th align="center" style={{ padding: 12 }}>Esito</Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <Td colSpan="8" align="center" style={{ padding: 40 }}>
                    Caricamento dei dati…
                  </Td>
                </tr>
              ) : (
                dailyComparison.map(row => (
                  <tr
                    key={row.date}
                    style={{ background: COLORS.card, borderBottom: `1px solid ${COLORS.border}` }}
                    data-testid={`row-${row.date}`}
                  >
                    <Td style={{ fontWeight: 500 }}>{formatDate(row.date)}</Td>
                    <Td align="right" mono>{row.posAuto > 0 ? formatEuro(row.posAuto) : '-'}</Td>
                    <Td align="right" mono>{row.posNumia > 0 ? formatEuro(row.posNumia) : '-'}</Td>
                    <Td align="right" mono>{row.posSumup > 0 ? formatEuro(row.posSumup) : '-'}</Td>
                    <Td align="right" mono>{row.posBanca > 0 ? formatEuro(row.posBanca) : '-'}</Td>
                    <Td align="right" mono>
                      {Math.abs(row.posDiff) > 0.01 ? `${row.posDiff > 0 ? '+' : ''}${formatEuro(row.posDiff)}` : '-'}
                    </Td>
                    <Td align="right" mono>
                      {Math.abs(row.posBancaDiff) > 0.01 ? `${row.posBancaDiff > 0 ? '+' : ''}${formatEuro(row.posBancaDiff)}` : '-'}
                    </Td>
                    <Td align="center"><Esito esito={row.esito} /></Td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr style={{ background: COLORS.primary, color: '#fff', fontWeight: 'bold' }}>
                <td style={{ padding: 12 }}>
                  TOTALE {monthNames[meseSelezionato - 1].toUpperCase()}
                </td>
                {['posAuto', 'posNumia', 'posSumup', 'posBanca', 'posDiff', 'posBancaDiff'].map(k => (
                  <td key={k} style={{ padding: 12, textAlign: 'right', fontFamily: MONO }}>
                    {formatEuro(dailyComparison.reduce((s, d) => s + (d[k] || 0), 0))}
                  </td>
                ))}
                <td />
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
