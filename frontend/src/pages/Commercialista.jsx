import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../api';
import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

// Funzione per formattare valuta come stringa pura (per PDF)
const formatEuroStr = val => {
  if (val == null || isNaN(val)) return '€ 0,00';
  return `€ ${Number(val).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const MESI = [
  '',
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

export default function Commercialista() {
  const isMobile = useIsMobile();
  const [config, setConfig] = useState({
    email: '',
    nome: '',
    alert_giorni: 2,
    smtp_configured: false,
  });
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(null);
  const [message, setMessage] = useState(null);
  const [alertStatus, setAlertStatus] = useState(null);
  const [log, setLog] = useState([]);
  const [segnandoInviata, setSegnandoInviata] = useState(false);

  // Anno dal context globale
  const { anno: selectedYear, setAnno } = useAnnoGlobale();
  const now = new Date();
  const [searchParams] = useSearchParams();
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const mese = parseInt(searchParams.get('mese') || '0');
    return mese > 0 ? mese - 1 : now.getMonth(); // 0-indexed
  });

  // Data states
  const [primaNotaData, setPrimaNotaData] = useState(null);
  const [fattureCassaData, setFattureCassaData] = useState(null);
  const [carnets, setCarnets] = useState([]);
  const [selectedCarnets, setSelectedCarnets] = useState([]); // Array per selezione multipla
  const [carnetSearch, setCarnetSearch] = useState(''); // Barra di ricerca

  // Pre-seleziona anno da URL params se presente
  useEffect(() => {
    const anno = parseInt(searchParams.get('anno') || '0');
    if (anno > 0) setAnno(anno);
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const [configRes, alertRes, logRes] = await Promise.all([
        api.get('/api/commercialista/config'),
        api.get('/api/commercialista/alert-status'),
        api.get('/api/commercialista/log?limit=20'),
      ]);
      setConfig(configRes.data);
      setAlertStatus(alertRes.data);
      setLog(logRes.data.log || []);
    } catch (e) {
      console.error('Error loading config:', e);
    }
  }, []);

  const handleSegnaComeInviata = async () => {
    if (!alertStatus?.show_alert) return;
    setSegnandoInviata(true);
    try {
      await api.post('/api/commercialista/segna-inviata', {
        anno: alertStatus.anno_pendente,
        mese: alertStatus.mese_pendente,
        email: config.email,
      });
      setMessage({
        type: 'success',
        text: `Prima Nota Cassa ${alertStatus.mese_nome} ${alertStatus.anno_pendente} segnata come inviata.`,
      });
      await loadConfig();
    } catch (e) {
      setMessage({ type: 'error', text: 'Errore nel segnare come inviata.' });
    } finally {
      setSegnandoInviata(false);
    }
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const month = selectedMonth + 1; // Convert to 1-indexed

      const [primaNotaRes, fattureCassaRes, assegniRes] = await Promise.all([
        api.get(`/api/commercialista/prima-nota-cassa/${selectedYear}/${month}`),
        api.get(`/api/commercialista/fatture-cassa/${selectedYear}/${month}`),
        api.get(`/api/assegni?anno=${selectedYear}`),
      ]);

      setPrimaNotaData(primaNotaRes.data);
      setFattureCassaData(fattureCassaRes.data);

      // Group assegni by carnet (stessa logica di GestioneAssegni)
      const assegni = assegniRes.data || [];
      const carnetGroups = {};
      assegni.forEach(a => {
        const num = a.numero || a.numero_assegno || '';
        // Carnet = prime 8 cifre del numero assegno
        const carnetId = num.substring(0, 8) || 'Sconosciuto';
        if (!carnetGroups[carnetId]) {
          carnetGroups[carnetId] = {
            id: carnetId,
            assegni: [],
            totale: 0,
          };
        }
        carnetGroups[carnetId].assegni.push(a);
        carnetGroups[carnetId].totale += parseFloat(a.importo || 0);
      });
      setCarnets(Object.values(carnetGroups));
    } catch (e) {
      console.error('Error loading data:', e);
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedMonth]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const showMessage = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  // Generate Prima Nota Cassa PDF
  const generatePrimaNotaPDF = () => {
    if (!primaNotaData) return null;

    const doc = new jsPDF();
    const meseNome = MESI[selectedMonth + 1];

    // ==========================================
    // INTESTAZIONE AZIENDA
    // ==========================================
    doc.setFontSize(16);
    doc.setTextColor(30, 58, 95);
    doc.setFont(undefined, 'bold');
    doc.text('CERALDI GROUP S.R.L.', 14, 18);

    doc.setFontSize(9);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(80);
    doc.text('Piazza Carità, 14 - 80134 Napoli (NA)', 14, 24);
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
    doc.text('PRIMA NOTA CASSA', 14, 45);

    doc.setFontSize(12);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(80);
    doc.text(`Periodo: ${meseNome} ${selectedYear}`, 14, 52);

    // ==========================================
    // RIEPILOGO DETTAGLIATO (2 COLONNE)
    // ==========================================
    const movimenti = primaNotaData.movimenti || [];

    // Entrate per categoria
    const entrateCorresp = movimenti
      .filter(
        m =>
          (m.tipo === 'entrata' || m.type === 'entrata') &&
          (m.categoria === 'Corrispettivi' || m.category === 'Corrispettivi')
      )
      .reduce((sum, m) => sum + parseFloat(m.importo || m.amount || 0), 0);

    const entrateFinSoci = movimenti
      .filter(
        m =>
          (m.tipo === 'entrata' || m.type === 'entrata') &&
          (m.categoria === 'Finanziamento soci' || m.category === 'Finanziamento soci')
      )
      .reduce((sum, m) => sum + parseFloat(m.importo || m.amount || 0), 0);

    const entrateAltro = movimenti
      .filter(
        m =>
          (m.tipo === 'entrata' || m.type === 'entrata') &&
          m.categoria !== 'Corrispettivi' &&
          m.category !== 'Corrispettivi' &&
          m.categoria !== 'Finanziamento soci' &&
          m.category !== 'Finanziamento soci'
      )
      .reduce((sum, m) => sum + parseFloat(m.importo || m.amount || 0), 0);

    // Uscite per categoria
    const usciteFatture = movimenti
      .filter(
        m =>
          (m.tipo === 'uscita' || m.type === 'uscita') &&
          ((m.categoria || m.category || '').toLowerCase().includes('fattura') ||
            (m.categoria || m.category || '').toLowerCase().includes('fornitore'))
      )
      .reduce((sum, m) => sum + parseFloat(m.importo || m.amount || 0), 0);

    const usciteVersamenti = movimenti
      .filter(
        m =>
          (m.tipo === 'uscita' || m.type === 'uscita') &&
          (m.categoria === 'Versamento' ||
            m.category === 'Versamento' ||
            (m.descrizione || m.description || '').toLowerCase().includes('versamento'))
      )
      .reduce((sum, m) => sum + parseFloat(m.importo || m.amount || 0), 0);

    const uscitePOS = movimenti
      .filter(
        m =>
          (m.tipo === 'uscita' || m.type === 'uscita') &&
          ((m.categoria || m.category || '') === 'POS' ||
            (m.descrizione || m.description || '').toLowerCase().includes('pos') ||
            (m.descrizione || m.description || '').toLowerCase().includes('bancomat') ||
            (m.descrizione || m.description || '').toLowerCase().includes('elettronico'))
      )
      .reduce((sum, m) => sum + parseFloat(m.importo || m.amount || 0), 0);

    const usciteAltro = movimenti
      .filter(
        m =>
          (m.tipo === 'uscita' || m.type === 'uscita') &&
          !(m.categoria || m.category || '').toLowerCase().includes('fattura') &&
          !(m.categoria || m.category || '').toLowerCase().includes('fornitore') &&
          m.categoria !== 'Versamento' &&
          m.category !== 'Versamento' &&
          m.categoria !== 'POS' &&
          m.category !== 'POS' &&
          !(m.descrizione || m.description || '').toLowerCase().includes('versamento') &&
          !(m.descrizione || m.description || '').toLowerCase().includes('pos') &&
          !(m.descrizione || m.description || '').toLowerCase().includes('bancomat')
      )
      .reduce((sum, m) => sum + parseFloat(m.importo || m.amount || 0), 0);

    const fmt = v => formatEuroStr(v);
    const totEntrate = primaNotaData.totale_entrate || 0;
    const totUscite = primaNotaData.totale_uscite || 0;
    const saldo = totEntrate - totUscite;

    // Calcola totale POS dai corrispettivi (info, non in cassa)
    const totalePOS = movimenti
      .filter(
        m =>
          (m.tipo === 'entrata' || m.type === 'entrata') &&
          (m.categoria === 'Corrispettivi' || m.category === 'Corrispettivi')
      )
      .reduce((sum, m) => sum + parseFloat(m.pagato_elettronico || 0), 0);

    const totaleGiornata = movimenti
      .filter(
        m =>
          (m.tipo === 'entrata' || m.type === 'entrata') &&
          (m.categoria === 'Corrispettivi' || m.category === 'Corrispettivi')
      )
      .reduce((sum, m) => sum + parseFloat(m.totale_giornata || m.importo || 0), 0);

    // Calcola ultimo giorno del mese per il saldo
    const ultimoGiorno = new Date(selectedYear, selectedMonth + 1, 0).getDate();
    const dataOggi = new Date();
    const isCurrentMonth =
      dataOggi.getFullYear() === selectedYear && dataOggi.getMonth() === selectedMonth;
    const giornoSaldo = isCurrentMonth ? dataOggi.getDate() : ultimoGiorno;
    const dataSaldo = `${String(giornoSaldo).padStart(2, '0')}/${String(selectedMonth + 1).padStart(2, '0')}/${selectedYear}`;

    // ==========================================
    // BOX ENTRATE (colonna sinistra)
    // ==========================================
    doc.setFillColor(240, 255, 240);
    doc.roundedRect(14, 58, 88, 58, 3, 3, 'F');
    doc.setDrawColor(39, 174, 96);
    doc.setLineWidth(0.3);
    doc.roundedRect(14, 58, 88, 58, 3, 3, 'S');

    doc.setFontSize(11);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(39, 174, 96);
    doc.text('ENTRATE', 20, 68);

    doc.setFontSize(9);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(60);
    let yLeft = 76;

    doc.text('Corrispettivi:', 20, yLeft);
    doc.text(fmt(entrateCorresp), 96, yLeft, { align: 'right' });

    if (entrateFinSoci > 0) {
      yLeft += 6;
      doc.text('Finanziamento Soci:', 20, yLeft);
      doc.text(fmt(entrateFinSoci), 96, yLeft, { align: 'right' });
    }
    if (entrateAltro > 0) {
      yLeft += 6;
      doc.text('Altre entrate:', 20, yLeft);
      doc.text(fmt(entrateAltro), 96, yLeft, { align: 'right' });
    }

    yLeft = 106;
    doc.setFont(undefined, 'bold');
    doc.setTextColor(39, 174, 96);
    doc.text('TOTALE ENTRATE:', 20, yLeft);
    doc.text(fmt(totEntrate), 96, yLeft, { align: 'right' });

    // ==========================================
    // BOX USCITE (colonna destra)
    // ==========================================
    doc.setFillColor(255, 240, 240);
    doc.roundedRect(108, 58, 88, 58, 3, 3, 'F');
    doc.setDrawColor(231, 76, 60);
    doc.setLineWidth(0.3);
    doc.roundedRect(108, 58, 88, 58, 3, 3, 'S');

    doc.setFontSize(11);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(231, 76, 60);
    doc.text('USCITE', 114, 68);

    doc.setFontSize(9);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(60);
    let yRight = 76;

    if (usciteFatture > 0) {
      doc.text('Pagamento Fatture:', 114, yRight);
      doc.text(fmt(usciteFatture), 190, yRight, { align: 'right' });
      yRight += 6;
    }
    if (totalePOS > 0) {
      doc.text('Pag. Elettronico → Banca:', 114, yRight);
      doc.text(fmt(totalePOS), 190, yRight, { align: 'right' });
      yRight += 6;
    }
    if (usciteVersamenti > 0) {
      doc.text('Versamenti in banca:', 114, yRight);
      doc.text(fmt(usciteVersamenti), 190, yRight, { align: 'right' });
      yRight += 6;
    }
    if (usciteAltro > 0) {
      doc.text('Altre uscite:', 114, yRight);
      doc.text(fmt(usciteAltro), 190, yRight, { align: 'right' });
      yRight += 6;
    }
    if (usciteFatture === 0 && uscitePOS === 0 && usciteVersamenti === 0 && usciteAltro === 0) {
      doc.text('Nessuna uscita', 114, yRight);
      yRight += 6;
    }

    yRight = 106;
    doc.setFont(undefined, 'bold');
    doc.setTextColor(231, 76, 60);
    doc.text('TOTALE USCITE:', 114, yRight);
    doc.text(fmt(totUscite), 190, yRight, { align: 'right' });

    // ==========================================
    // SALDO CASSA
    // ==========================================
    doc.setFillColor(saldo >= 0 ? 240 : 255, saldo >= 0 ? 248 : 240, saldo >= 0 ? 255 : 240);
    doc.roundedRect(14, 120, 182, 12, 2, 2, 'F');
    doc.setFontSize(12);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(saldo >= 0 ? 39 : 231, saldo >= 0 ? 174 : 76, saldo >= 0 ? 96 : 60);
    doc.text(`SALDO CASSA AL ${dataSaldo}:`, 20, 129);
    doc.text(fmt(saldo), 190, 129, { align: 'right' });

    // ==========================================
    // TABELLA MOVIMENTI CON SALDO PROGRESSIVO
    // ==========================================
    if (movimenti.length > 0) {
      // Ordino cronologicamente ASC per calcolo saldo progressivo corretto
      const movimentiAsc = [...movimenti].sort((a, b) =>
        ((a.date || a.data) || '').localeCompare((b.date || b.data) || '')
      );
      let saldoProgressivo = 0;
      const tableData = movimentiAsc.map(m => {
        const data = m.date || m.data || '';
        const tipo = (m.type || m.tipo || '').toLowerCase();
        const importo = parseFloat(m.amount || m.importo || 0);
        if (tipo === 'entrata' || tipo === 'income' || tipo === 'in') {
          saldoProgressivo += Math.abs(importo);
        } else {
          saldoProgressivo -= Math.abs(importo);
        }

        return [
          formatDateIT(data),
          tipo === 'entrata' ? '↑ ENTRATA' : '↓ USCITA',
          formatEuro(importo),
          (m.description || m.descrizione || '-').substring(0, 45),
          m.category || m.categoria || '-',
          formatEuro(saldoProgressivo),
        ];
      });

      autoTable(doc, {
        startY: 140,
        head: [
          ['Data', 'Tipo', 'Importo', 'Descrizione', 'Categoria', 'Saldo Progr.'],
        ],
        body: tableData,
        theme: 'striped',
        headStyles: {
          fillColor: [30, 58, 95],
          fontSize: 9,
          fontStyle: 'bold',
        },
        styles: {
          fontSize: 8,
          cellPadding: 3,
        },
        columnStyles: {
          0: { cellWidth: 20 },
          1: { cellWidth: 20 },
          2: { cellWidth: 22, halign: 'right' },
          3: { cellWidth: 58 },
          4: { cellWidth: 30 },
          5: { cellWidth: 25, halign: 'right', fontStyle: 'bold' },
        },
        alternateRowStyles: { fillColor: [248, 250, 252] },
      });
    }

    // ==========================================
    // FOOTER
    // ==========================================
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(128);
      doc.text(
        `CERALDI GROUP S.R.L. - Generato il ${new Date().toLocaleDateString('it-IT')} - Pagina ${i}/${pageCount}`,
        14,
        doc.internal.pageSize.height - 10
      );
    }

    return doc;
  };

  // Generate Fatture Cassa PDF
  const generateFattureCassaPDF = () => {
    if (!fattureCassaData) return null;

    const doc = new jsPDF();
    const meseNome = MESI[selectedMonth + 1];

    // Header
    doc.setFontSize(20);
    doc.setTextColor(255, 152, 0);
    doc.text('Fatture Pagate per Cassa', 14, 20);

    doc.setFontSize(14);
    doc.setTextColor(100);
    doc.text(`${meseNome} ${selectedYear}`, 14, 30);

    // Summary
    doc.setFontSize(12);
    doc.setTextColor(0);
    doc.text(`Totale Fatture: ${fattureCassaData.totale_fatture}`, 14, 45);
    doc.setFontSize(14);
    doc.setTextColor(255, 152, 0);
    doc.text(`Totale: ${formatEuroStr(fattureCassaData.totale_importo)}`, 14, 55);

    // Table
    if (fattureCassaData.fatture?.length > 0) {
      const tableData = fattureCassaData.fatture.map(f => {
        const numero = f.invoice_number || f.numero_fattura || '-';
        const dataFattura = formatDateIT(f.invoice_date || f.data_fattura);
        const fornitore = f.supplier_name || f.cedente_denominazione || '-';
        const importo = parseFloat(f.total_amount || f.importo_totale || 0);
        const dataPagamento = formatDateIT(f.data_pagamento) || dataFattura;
        const modalita =
          f.modalita_pagamento ||
          f.metodo_pagamento ||
          f.payment_method ||
          'Contanti';

        return [
          dataFattura,
          fornitore.substring(0, 30),
          numero,
          `${formatEuroStr(importo)}`,
          dataPagamento,
          modalita,
        ];
      });

      autoTable(doc, {
        startY: 65,
        head: [
          [
            'Data Fattura',
            'Fornitore',
            'N. Fattura',
            'Importo',
            'Data Pagamento',
            'Modalità',
          ],
        ],
        body: tableData,
        theme: 'striped',
        headStyles: { fillColor: [255, 152, 0] },
        styles: { fontSize: 8 },
        columnStyles: {
          0: { cellWidth: 22 },
          1: { cellWidth: 52 },
          2: { cellWidth: 28 },
          3: { cellWidth: 24, halign: 'right' },
          4: { cellWidth: 26 },
          5: { cellWidth: 30 },
        },
      });
    }

    // Footer
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(128);
      doc.text(
        `Ceraldi Group S.R.L. - Generato il ${new Date().toLocaleDateString('it-IT')} - Pagina ${i}/${pageCount}`,
        14,
        doc.internal.pageSize.height - 10
      );
    }

    return doc;
  };

  // Generate Carnet PDF
  const generateCarnetPDF = carnet => {
    if (!carnet) return null;

    const doc = new jsPDF();

    // Header
    doc.setFontSize(20);
    doc.setTextColor(76, 175, 80);
    doc.text('Carnet Assegni', 14, 20);

    doc.setFontSize(14);
    doc.setTextColor(100);
    doc.text(`ID: ${carnet.id}`, 14, 30);

    // Summary
    doc.setFontSize(12);
    doc.setTextColor(0);
    doc.text(`Numero Assegni: ${carnet?.assegni?.length}`, 14, 45);
    doc.setFontSize(14);
    doc.setTextColor(76, 175, 80);
    doc.text(`Totale: ${formatEuroStr(carnet.totale)}`, 14, 55);

    // Table
    if (carnet.assegni?.length > 0) {
      const tableData = carnet.assegni.map(a => [
        a.numero || '-',
        a.stato || '-',
        (a.beneficiario || a.fornitore_ragione_sociale || '-').substring(0, 28),
        `${formatEuroStr(a.importo)}`,
        formatDateIT(a.data_fattura) || '-',
        a.numero_fattura || a.fattura_numero || '-',
      ]);

      autoTable(doc, {
        startY: 65,
        head: [['N. Assegno', 'Stato', 'Beneficiario', 'Importo', 'Data Fatt.', 'N. Fattura']],
        body: tableData,
        theme: 'striped',
        headStyles: { fillColor: [76, 175, 80] },
        styles: { fontSize: 8 },
        columnStyles: {
          2: { cellWidth: 40 },
        },
      });
    }

    // Footer
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(128);
      doc.text(
        `Ceraldi Group S.R.L. - Generato il ${new Date().toLocaleDateString('it-IT')} - Pagina ${i}/${pageCount}`,
        14,
        doc.internal.pageSize.height - 10
      );
    }

    return doc;
  };

  // Download PDF
  const downloadPDF = (type, carnetData = null) => {
    let doc;
    let filename;
    const meseNome = MESI[selectedMonth + 1];

    switch (type) {
      case 'prima_nota':
        doc = generatePrimaNotaPDF();
        filename = `Prima_Nota_Cassa_${meseNome}_${selectedYear}.pdf`;
        break;
      case 'fatture_cassa':
        doc = generateFattureCassaPDF();
        filename = `Fatture_Cassa_${meseNome}_${selectedYear}.pdf`;
        break;
      case 'carnet':
        doc = generateCarnetPDF(carnetData);
        filename = `Carnet_Assegni_${carnetData?.id || 'export'}.pdf`;
        break;
      case 'carnet_multi':
        // Genera PDF con tutti i carnet selezionati
        doc = generateCarnetMultiPDF(carnetData);
        filename = `Carnet_Assegni_${carnetData?.length || 0}_carnet.pdf`;
        break;
      default:
        return;
    }

    if (doc) {
      doc.save(filename);
      showMessage(`PDF "${filename}" scaricato con successo!`);
    }
  };

  // Generate PDF for multiple carnets
  const generateCarnetMultiPDF = carnetsArray => {
    if (!carnetsArray || carnetsArray.length === 0) return null;

    const doc = new jsPDF();

    // Header
    doc.setFontSize(20);
    doc.setTextColor(76, 175, 80);
    doc.text('Carnet Assegni Selezionati', 14, 20);

    doc.setFontSize(12);
    doc.setTextColor(100);
    doc.text(
      `${carnetsArray.length} carnet - ${carnetsArray.reduce((sum, c) => sum + c?.assegni?.length, 0)} assegni`,
      14,
      30
    );

    // Summary
    doc.setFontSize(14);
    doc.setTextColor(0);
    const totaleImporto = carnetsArray.reduce((sum, c) => sum + c.totale, 0);
    doc.text(`Totale Generale: ${formatEuroStr(totaleImporto)}`, 14, 42);

    // Tabella con tutti gli assegni raggruppati per carnet
    let currentY = 55;

    carnetsArray.forEach((carnet, _idx) => {
      // Titolo carnet
      if (currentY > 250) {
        doc.addPage();
        currentY = 20;
      }

      doc.setFontSize(12);
      doc.setTextColor(76, 175, 80);
      doc.text(
        `Carnet ${carnet.id} - ${carnet?.assegni?.length} assegni - ${formatEuroStr(carnet.totale)}`,
        14,
        currentY
      );
      currentY += 8;

      // Tabella assegni con dati completi di fattura e fornitore
      const tableData = carnet.assegni.map(a => {
        const dataAssegno =
          formatDateIT(a.data_emissione) ||
          formatDateIT(a.data_incasso) ||
          formatDateIT(a.data_fattura) ||
          '-';
        const fornitore = (
          a.fornitore_ragione_sociale ||
          a.fornitore_fattura ||
          a.beneficiario ||
          '-'
        ).substring(0, 28);
        return [
          a.numero || '-',
          dataAssegno,
          (a.beneficiario || '-').substring(0, 24),
          fornitore,
          a.numero_fattura || a.fattura_numero || '-',
          formatDateIT(a.data_fattura) || '-',
          `${formatEuroStr(a.importo)}`,
          a.stato || '-',
        ];
      });

      autoTable(doc, {
        startY: currentY,
        head: [
          [
            'N. Assegno',
            'Data',
            'Beneficiario',
            'Fornitore',
            'N. Fattura',
            'Data Fattura',
            'Importo',
            'Stato',
          ],
        ],
        body: tableData,
        theme: 'striped',
        headStyles: { fillColor: [76, 175, 80], fontSize: 8 },
        styles: { fontSize: 7, cellPadding: 2 },
        columnStyles: {
          0: { cellWidth: 22 },
          1: { cellWidth: 18 },
          2: { cellWidth: 30 },
          3: { cellWidth: 32 },
          4: { cellWidth: 18 },
          5: { cellWidth: 18 },
          6: { cellWidth: 20, halign: 'right' },
          7: { cellWidth: 20 },
        },
        margin: { left: 14, right: 14 },
      });

      currentY = doc.lastAutoTable.finalY + 15;
    });

    // Footer
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(128);
      doc.text(
        `Ceraldi Group S.R.L. - Generato il ${new Date().toLocaleDateString('it-IT')} - Pagina ${i}/${pageCount}`,
        14,
        doc.internal.pageSize.height - 10
      );
    }

    return doc;
  };

  // Send email with PDF
  const sendEmail = async (type, carnetData = null) => {
    setSending(type === 'carnet_multi' ? 'carnet' : type);

    try {
      let doc;
      let endpoint;
      let payload = { email: config.email };

      switch (type) {
        case 'prima_nota':
          doc = generatePrimaNotaPDF();
          endpoint = '/api/commercialista/invia-prima-nota';
          payload.anno = selectedYear;
          payload.mese = selectedMonth + 1;
          break;
        case 'fatture_cassa':
          doc = generateFattureCassaPDF();
          endpoint = '/api/commercialista/invia-fatture-cassa';
          payload.anno = selectedYear;
          payload.mese = selectedMonth + 1;
          break;
        case 'carnet':
          doc = generateCarnetPDF(carnetData);
          endpoint = '/api/commercialista/invia-carnet';
          payload.carnet_id = carnetData.id;
          payload.assegni_count = carnetData.assegni.length;
          payload.totale_importo = carnetData.totale;
          break;
        case 'carnet_multi':
          doc = generateCarnetMultiPDF(carnetData);
          endpoint = '/api/commercialista/invia-carnet';
          payload.carnet_id = carnetData.map(c => c.id).join(', ');
          payload.assegni_count = carnetData.reduce((sum, c) => sum + c?.assegni?.length, 0);
          payload.totale_importo = carnetData.reduce((sum, c) => sum + c.totale, 0);
          break;
        default:
          return;
      }

      if (doc) {
        // Convert PDF to base64
        const pdfBase64 = doc.output('datauristring').split(',')[1];
        payload.pdf_base64 = pdfBase64;
      }

      const res = await api.post(endpoint, payload);

      if (res.data.success) {
        showMessage(`✅ ${res?.data?.message}`);
        loadConfig(); // Refresh log and alert status
      } else {
        showMessage(`❌ Errore: ${res?.data?.message}`, 'error');
      }
    } catch (e) {
      showMessage(`❌ Errore invio: ${e.response?.data?.detail || e.message}`, 'error');
    } finally {
      setSending(null);
    }
  };

  const formatDate = dateStr => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <PageLayout
      title="Area Commercialista"
      subtitle="Genera e invia documenti PDF al commercialista"
    >
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        <h1 style={{ marginBottom: 5, color: '#1e3a5f' }}>👩‍💼 Area Commercialista</h1>
        <p style={{ color: '#666', marginBottom: 25 }}>
          Genera e invia documenti PDF al commercialista via email
        </p>

        {/* Alert Banner */}
        {alertStatus?.show_alert && (
          <div
            style={{
              background: 'linear-gradient(135deg, #ff9800 0%, #f57c00 100%)',
              color: 'white',
              padding: 20,
              borderRadius: 12,
              marginBottom: 25,
              display: 'flex',
              alignItems: 'center',
              gap: 15,
              boxShadow: '0 4px 15px rgba(255, 152, 0, 0.3)',
            }}
          >
            <span style={{ fontSize: 32 }}>⚠️</span>
            <div style={{ flex: 1 }}>
              <strong style={{ fontSize: 16 }}>{alertStatus.message}</strong>
              <p style={{ margin: '5px 0 0 0', opacity: 0.9, fontSize: 14 }}>
                Scadenza: {formatDate(alertStatus.deadline)}
              </p>
            </div>
            <button
              onClick={() => {
                setAnno(alertStatus.anno_pendente);
                setSelectedMonth(alertStatus.mese_pendente - 1);
              }}
              style={{
                padding: '10px 20px',
                background: 'white',
                color: '#f57c00',
                border: 'none',
                borderRadius: 8,
                fontWeight: 'bold',
                cursor: 'pointer',
              }}
            >
              Vai al mese
            </button>
            <button
              onClick={handleSegnaComeInviata}
              disabled={segnandoInviata}
              style={{
                padding: '10px 20px',
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: '2px solid rgba(255,255,255,0.5)',
                borderRadius: 8,
                fontWeight: 'bold',
                cursor: segnandoInviata ? 'wait' : 'pointer',
                fontSize: 13,
              }}
            >
              {segnandoInviata ? '...' : 'Segna come inviata'}
            </button>
          </div>
        )}

        {/* Message */}
        {message && (
          <div
            style={{
              padding: 15,
              borderRadius: 8,
              marginBottom: 20,
              background: message.type === 'error' ? '#ffebee' : '#e8f5e9',
              color: message.type === 'error' ? '#c62828' : '#2e7d32',
              border: `1px solid ${message.type === 'error' ? '#ffcdd2' : '#c8e6c9'}`,
            }}
          >
            {message.text}
          </div>
        )}

        {/* Config Card */}
        <div
          style={{
            background: 'white',
            borderRadius: 12,
            padding: 20,
            marginBottom: 25,
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          }}
        >
          <h3 style={{ margin: '0 0 15px 0', color: '#1e3a5f' }}>📧 Configurazione Email</h3>
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'center' }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#666', marginBottom: 4 }}>
                Email Commercialista
              </label>
              <input
                type="email"
                value={config.email}
                onChange={e => setConfig({ ...config, email: e.target.value })}
                style={{
                  padding: '10px 15px',
                  borderRadius: 8,
                  border: '1px solid #ddd',
                  width: 280,
                  fontSize: 14,
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#666', marginBottom: 4 }}>
                Nome Commercialista
              </label>
              <input
                type="text"
                value={config.nome}
                onChange={e => setConfig({ ...config, nome: e.target.value })}
                style={{
                  padding: '10px 15px',
                  borderRadius: 8,
                  border: '1px solid #ddd',
                  width: 200,
                  fontSize: 14,
                }}
              />
            </div>
            <div
              style={{
                padding: '8px 15px',
                borderRadius: 8,
                background: config.smtp_configured ? '#e8f5e9' : '#ffebee',
                color: config.smtp_configured ? '#2e7d32' : '#c62828',
                fontSize: 13,
              }}
            >
              {config.smtp_configured ? '✅ SMTP Configurato' : '❌ SMTP Non Configurato'}
            </div>
          </div>
        </div>

        {/* Period Selector */}
        <div
          style={{
            background: 'white',
            borderRadius: 12,
            padding: 20,
            marginBottom: 25,
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          }}
        >
          <h3 style={{ margin: '0 0 15px 0', color: '#1e3a5f' }}>📅 Seleziona Periodo</h3>
          <div style={{ display: 'flex', gap: 15, flexWrap: 'wrap', alignItems: 'center' }}>
            <select
              value={selectedMonth}
              onChange={e => setSelectedMonth(parseInt(e.target.value))}
              style={{
                padding: '10px 15px',
                borderRadius: 8,
                border: '1px solid #ddd',
                fontSize: 14,
                minWidth: 150,
              }}
            >
              {MESI.slice(1).map((m, idx) => (
                <option key={idx} value={idx}>
                  {m}
                </option>
              ))}
            </select>
            <span
              style={{
                padding: '10px 15px',
                borderRadius: 8,
                background: '#e3f2fd',
                fontSize: 14,
                fontWeight: 'bold',
                color: '#1565c0',
              }}
            >
              {selectedYear}
            </span>

            {/* Export Excel Button */}
            <button
              onClick={() => {
                const url = `/api/commercialista/export-excel/${selectedYear}/${selectedMonth + 1}`;
                window.open(url, '_blank');
              }}
              data-testid="export-excel-btn"
              style={{
                marginLeft: 'auto',
                padding: '10px 20px',
                background: 'linear-gradient(135deg, #2e7d32 0%, #43a047 100%)',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 14,
              }}
            >
              📊 Export Excel Commercialista
            </button>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>Caricamento...</div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
              gap: 20,
            }}
          >
            {/* Prima Nota Cassa Card */}
            <div
              style={{
                background: 'white',
                borderRadius: 12,
                overflow: 'hidden',
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              }}
            >
              <div
                style={{
                  background: 'linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)',
                  color: 'white',
                  padding: 20,
                }}
              >
                <h3 style={{ margin: 0 }}>📒 Prima Nota Cassa</h3>
                <p style={{ margin: '5px 0 0 0', opacity: 0.9, fontSize: 14 }}>
                  {MESI[selectedMonth + 1]} {selectedYear}
                </p>
              </div>
              <div style={{ padding: 20 }}>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                    gap: 15,
                    marginBottom: 20,
                  }}
                >
                  <div
                    style={{
                      background: '#e8f5e9',
                      padding: 15,
                      borderRadius: 8,
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: 12, color: '#666' }}>Entrate</div>
                    <div style={{ fontSize: 18, fontWeight: 'bold', color: '#4caf50' }}>
                      {formatEuro(primaNotaData?.totale_entrate)}
                    </div>
                  </div>
                  <div
                    style={{
                      background: '#ffebee',
                      padding: 15,
                      borderRadius: 8,
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: 12, color: '#666' }}>Uscite</div>
                    <div style={{ fontSize: 18, fontWeight: 'bold', color: '#f44336' }}>
                      {formatEuro(primaNotaData?.totale_uscite)}
                    </div>
                  </div>
                </div>
                <div
                  style={{
                    background: '#f5f5f5',
                    padding: 15,
                    borderRadius: 8,
                    textAlign: 'center',
                    marginBottom: 20,
                  }}
                >
                  <div style={{ fontSize: 12, color: '#666' }}>Saldo</div>
                  <div
                    style={{
                      fontSize: 24,
                      fontWeight: 'bold',
                      color: (primaNotaData?.saldo || 0) >= 0 ? '#4caf50' : '#f44336',
                    }}
                  >
                    {formatEuro(primaNotaData?.saldo)}
                  </div>
                  <div style={{ fontSize: 12, color: '#999', marginTop: 5 }}>
                    {primaNotaData?.totale_movimenti || 0} movimenti
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    onClick={() => downloadPDF('prima_nota')}
                    data-testid="download-prima-nota-pdf"
                    style={{
                      flex: 1,
                      padding: '12px',
                      background: '#f5f5f5',
                      color: '#333',
                      border: 'none',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontWeight: 'bold',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                    }}
                  >
                    📥 Scarica PDF
                  </button>
                  <button
                    onClick={() => sendEmail('prima_nota')}
                    disabled={sending === 'prima_nota' || !config.smtp_configured}
                    data-testid="send-prima-nota-email"
                    style={{
                      flex: 1,
                      padding: '12px',
                      background: sending === 'prima_nota' ? '#ccc' : '#2563eb',
                      color: 'white',
                      border: 'none',
                      borderRadius: 8,
                      cursor: sending === 'prima_nota' ? 'wait' : 'pointer',
                      fontWeight: 'bold',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                    }}
                  >
                    {sending === 'prima_nota' ? '⏳ Invio...' : '📧 Invia Email'}
                  </button>
                </div>
              </div>
            </div>

            {/* Fatture Cassa Card */}
            <div
              style={{
                background: 'white',
                borderRadius: 12,
                overflow: 'hidden',
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              }}
            >
              <div
                style={{
                  background: 'linear-gradient(135deg, #ff9800 0%, #f57c00 100%)',
                  color: 'white',
                  padding: 20,
                }}
              >
                <h3 style={{ margin: 0 }}>💵 Fatture Pagate per Cassa</h3>
                <p style={{ margin: '5px 0 0 0', opacity: 0.9, fontSize: 14 }}>
                  {MESI[selectedMonth + 1]} {selectedYear}
                </p>
              </div>
              <div style={{ padding: 20 }}>
                <div
                  style={{
                    background: '#fff3e0',
                    padding: 20,
                    borderRadius: 8,
                    textAlign: 'center',
                    marginBottom: 20,
                  }}
                >
                  <div style={{ fontSize: 12, color: '#666' }}>Totale Fatture</div>
                  <div style={{ fontSize: 28, fontWeight: 'bold', color: '#f57c00' }}>
                    {formatEuro(fattureCassaData?.totale_importo)}
                  </div>
                  <div style={{ fontSize: 12, color: '#999', marginTop: 5 }}>
                    {fattureCassaData?.totale_fatture || 0} fatture
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    onClick={() => downloadPDF('fatture_cassa')}
                    data-testid="download-fatture-cassa-pdf"
                    style={{
                      flex: 1,
                      padding: '12px',
                      background: '#f5f5f5',
                      color: '#333',
                      border: 'none',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontWeight: 'bold',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                    }}
                  >
                    📥 Scarica PDF
                  </button>
                  <button
                    onClick={() => sendEmail('fatture_cassa')}
                    disabled={sending === 'fatture_cassa' || !config.smtp_configured}
                    data-testid="send-fatture-cassa-email"
                    style={{
                      flex: 1,
                      padding: '12px',
                      background: sending === 'fatture_cassa' ? '#ccc' : '#f57c00',
                      color: 'white',
                      border: 'none',
                      borderRadius: 8,
                      cursor: sending === 'fatture_cassa' ? 'wait' : 'pointer',
                      fontWeight: 'bold',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                    }}
                  >
                    {sending === 'fatture_cassa' ? '⏳ Invio...' : '📧 Invia Email'}
                  </button>
                </div>
              </div>
            </div>

            {/* Carnet Assegni Card */}
            <div
              style={{
                background: 'white',
                borderRadius: 12,
                overflow: 'hidden',
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                gridColumn: 'span 1',
              }}
            >
              <div
                style={{
                  background: 'linear-gradient(135deg, #4caf50 0%, #2e7d32 100%)',
                  color: 'white',
                  padding: 20,
                }}
              >
                <h3 style={{ margin: 0 }}>📝 Carnet Assegni</h3>
                <p style={{ margin: '5px 0 0 0', opacity: 0.9, fontSize: 14 }}>
                  Cerca e seleziona carnet da inviare
                </p>
              </div>
              <div style={{ padding: 20 }}>
                {/* Barra di Ricerca */}
                <input
                  type="text"
                  placeholder="🔍 Cerca carnet, beneficiario, importo..."
                  value={carnetSearch}
                  onChange={e => setCarnetSearch(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: 8,
                    border: '1px solid #ddd',
                    marginBottom: 15,
                    fontSize: 14,
                  }}
                />

                {carnets.length === 0 ? (
                  <div style={{ textAlign: 'center', color: '#666', padding: 20 }}>
                    Nessun carnet disponibile
                  </div>
                ) : (
                  <>
                    {/* Lista Carnet con Checkbox */}
                    <div
                      style={{
                        maxHeight: 250,
                        overflowY: 'auto',
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        marginBottom: 15,
                      }}
                    >
                      {carnets
                        .filter(c => {
                          if (!carnetSearch) return true;
                          const search = carnetSearch.toLowerCase();
                          // Cerca in ID carnet
                          if (c.id.toLowerCase().includes(search)) return true;
                          // Cerca in numero assegno, numero fattura, beneficiario, fornitore, importo
                          return c.assegni.some(
                            a =>
                              (a.numero || '').toString().toLowerCase().includes(search) ||
                              (a.numero_fattura || a.fattura_numero || '')
                                .toString()
                                .toLowerCase()
                                .includes(search) ||
                              (a.beneficiario || '').toLowerCase().includes(search) ||
                              (a.fornitore_ragione_sociale || a.fornitore_fattura || '')
                                .toString()
                                .toLowerCase()
                                .includes(search) ||
                              (a.importo || '').toString().includes(search)
                          );
                        })
                        .map(c => {
                          const searchLower = carnetSearch.toLowerCase();
                          // Assegni che matchano la ricerca (se attiva)
                          const assegniMatch = carnetSearch
                            ? c.assegni.filter(
                                a =>
                                  (a.numero || '').toString().toLowerCase().includes(searchLower) ||
                                  (a.numero_fattura || a.fattura_numero || '')
                                    .toString()
                                    .toLowerCase()
                                    .includes(searchLower) ||
                                  (a.beneficiario || '').toLowerCase().includes(searchLower) ||
                                  (a.fornitore_ragione_sociale || a.fornitore_fattura || '')
                                    .toString()
                                    .toLowerCase()
                                    .includes(searchLower) ||
                                  (a.importo || '').toString().includes(searchLower)
                              )
                            : [];
                          return (
                          <label
                            key={c.id}
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              padding: '12px 15px',
                              borderBottom: '1px solid #f3f4f6',
                              cursor: 'pointer',
                              background: selectedCarnets.includes(c.id) ? '#e8f5e9' : 'white',
                              transition: 'background 0.2s',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              <input
                                type="checkbox"
                                checked={selectedCarnets.includes(c.id)}
                                onChange={e => {
                                  if (e.target.checked) {
                                    setSelectedCarnets([...selectedCarnets, c.id]);
                                  } else {
                                    setSelectedCarnets(
                                      selectedCarnets.filter(id => id !== c.id)
                                    );
                                  }
                                }}
                                style={{ marginRight: 12, width: 18, height: 18 }}
                              />
                              <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: 'bold', color: '#1e293b' }}>
                                  Carnet {c.id}
                                </div>
                                <div style={{ fontSize: 12, color: '#64748b' }}>
                                  {c?.assegni?.length} assegni • {formatEuro(c.totale)}
                                  {assegniMatch.length > 0 &&
                                    ` • ${assegniMatch.length} match`}
                                </div>
                              </div>
                            </div>
                            {/* Dettaglio assegni che matchano (solo se search attiva) */}
                            {assegniMatch.length > 0 && (
                              <div
                                style={{
                                  marginTop: 8,
                                  marginLeft: 30,
                                  fontSize: 12,
                                  background: '#fffbeb',
                                  border: '1px solid #fde68a',
                                  borderRadius: 6,
                                  padding: 8,
                                }}
                              >
                                {assegniMatch.map((a, i) => (
                                  <div
                                    key={i}
                                    style={{
                                      padding: '4px 0',
                                      borderBottom:
                                        i < assegniMatch.length - 1
                                          ? '1px dashed #f3d97d'
                                          : 'none',
                                    }}
                                  >
                                    <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                                      N° {a.numero || '-'}
                                    </span>{' '}
                                    <span style={{ color: '#b45309' }}>
                                      {formatEuro(a.importo)}
                                    </span>
                                    {a.beneficiario && (
                                      <span style={{ color: '#374151' }}>
                                        {' '}
                                        · {a.beneficiario}
                                      </span>
                                    )}
                                    {a.numero_fattura && (
                                      <span style={{ color: '#6b7280' }}>
                                        {' '}
                                        · fatt. {a.numero_fattura}
                                      </span>
                                    )}
                                    {a.stato && (
                                      <span
                                        style={{
                                          marginLeft: 6,
                                          padding: '1px 6px',
                                          borderRadius: 4,
                                          fontSize: 10,
                                          background:
                                            a.stato === 'incassato'
                                              ? '#d1fae5'
                                              : a.stato === 'emesso'
                                                ? '#dbeafe'
                                                : '#fee2e2',
                                          color:
                                            a.stato === 'incassato'
                                              ? '#065f46'
                                              : a.stato === 'emesso'
                                                ? '#1e40af'
                                                : '#991b1b',
                                        }}
                                      >
                                        {a.stato}
                                      </span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </label>
                          );
                        })}
                    </div>

                    {/* Riepilogo Selezione */}
                    {selectedCarnets.length > 0 && (
                      <div
                        style={{
                          background: '#e8f5e9',
                          padding: 15,
                          borderRadius: 8,
                          marginBottom: 15,
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            marginBottom: 10,
                          }}
                        >
                          <span>Carnet Selezionati:</span>
                          <strong>{selectedCarnets.length}</strong>
                        </div>
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            marginBottom: 10,
                          }}
                        >
                          <span>Totale Assegni:</span>
                          <strong>
                            {carnets
                              .filter(c => selectedCarnets.includes(c.id))
                              .reduce((sum, c) => sum + c?.assegni?.length, 0)}
                          </strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Importo Totale:</span>
                          <strong style={{ color: '#2e7d32' }}>
                            {formatEuro(
                              carnets
                                .filter(c => selectedCarnets.includes(c.id))
                                .reduce((sum, c) => sum + c.totale, 0)
                            )}
                          </strong>
                        </div>
                      </div>
                    )}

                    {/* Pulsanti */}
                    <div style={{ display: 'flex', gap: 10 }}>
                      <button
                        onClick={() => {
                          const selectedCarnetData = carnets.filter(c =>
                            selectedCarnets.includes(c.id)
                          );
                          if (selectedCarnetData.length > 0) {
                            downloadPDF('carnet_multi', selectedCarnetData);
                          }
                        }}
                        disabled={selectedCarnets.length === 0}
                        data-testid="download-carnet-pdf"
                        style={{
                          flex: 1,
                          padding: '12px',
                          background: selectedCarnets.length === 0 ? '#e5e7eb' : '#f5f5f5',
                          color: selectedCarnets.length === 0 ? '#9ca3af' : '#333',
                          border: 'none',
                          borderRadius: 8,
                          cursor: selectedCarnets.length === 0 ? 'not-allowed' : 'pointer',
                          fontWeight: 'bold',
                        }}
                      >
                        📥 Scarica PDF ({selectedCarnets.length})
                      </button>
                      <button
                        onClick={() => {
                          const selectedCarnetData = carnets.filter(c =>
                            selectedCarnets.includes(c.id)
                          );
                          if (selectedCarnetData.length > 0) {
                            sendEmail('carnet_multi', selectedCarnetData);
                          }
                        }}
                        disabled={
                          selectedCarnets.length === 0 ||
                          sending === 'carnet' ||
                          !config.smtp_configured
                        }
                        data-testid="send-carnet-email"
                        style={{
                          flex: 1,
                          padding: '12px',
                          background:
                            selectedCarnets.length === 0 || sending === 'carnet'
                              ? '#ccc'
                              : '#2e7d32',
                          color: 'white',
                          border: 'none',
                          borderRadius: 8,
                          cursor:
                            selectedCarnets.length === 0 || sending === 'carnet'
                              ? 'not-allowed'
                              : 'pointer',
                          fontWeight: 'bold',
                        }}
                      >
                        {sending === 'carnet'
                          ? '⏳ Invio...'
                          : `📧 Invia Email (${selectedCarnets.length})`}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Log Section */}
        {log.length > 0 && (
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 20,
              marginTop: 25,
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
          >
            <h3 style={{ margin: '0 0 15px 0', color: '#1e3a5f' }}>📋 Storico Invii</h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e5e7eb' }}>
                    <th style={{ padding: 12, textAlign: 'left' }}>Data Invio</th>
                    <th style={{ padding: 12, textAlign: 'left' }}>Tipo</th>
                    <th style={{ padding: 12, textAlign: 'left' }}>Periodo/ID</th>
                    <th style={{ padding: 12, textAlign: 'left' }}>Email</th>
                    <th style={{ padding: 12, textAlign: 'center' }}>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {log.map((entry, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: 12 }}>{formatDate(entry.data_invio)}</td>
                      <td style={{ padding: 12 }}>
                        {entry.tipo === 'prima_nota_cassa' && '📒 Prima Nota'}
                        {entry.tipo === 'fatture_cassa' && '💵 Fatture Cassa'}
                        {entry.tipo === 'carnet_assegni' && '📝 Carnet'}
                      </td>
                      <td style={{ padding: 12 }}>
                        {entry.carnet_id || `${MESI[entry.mese]} ${entry.anno}`}
                      </td>
                      <td style={{ padding: 12 }}>{entry.email}</td>
                      <td style={{ padding: 12, textAlign: 'center' }}>
                        <span
                          style={{
                            padding: '4px 12px',
                            borderRadius: 12,
                            fontSize: 12,
                            fontWeight: 'bold',
                            background: entry.success ? '#e8f5e9' : '#ffebee',
                            color: entry.success ? '#2e7d32' : '#c62828',
                          }}
                        >
                          {entry.success ? '✓ Inviato' : '✕ Errore'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
