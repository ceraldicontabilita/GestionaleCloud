import { formatDateIT } from '../lib/utils';
import React, { useState } from 'react';

/**
 * Visualizzatore Fattura XML - Stile AssoInvoice
 * Tre modalità di visualizzazione:
 * 1. Semplificata - Solo dati fiscalmente rilevanti (compatta)
 * 2. Completa - Tutti i dati incluse info gestionali
 * 3. Ministeriale - Formato ufficiale Agenzia Entrate/Sogei
 */
export default function InvoiceXMLViewer({ invoice: rawInvoice, onClose }) {
  const [viewMode, setViewMode] = useState('completa'); // 'semplificata', 'completa', 'ministeriale'

  // Normalizza i dati della fattura per supportare diversi formati
  const normalizeInvoice = inv => {
    if (!inv) return null;

    // Converti le linee dal formato DB al formato visualizzatore
    const lineItems = (inv.linee || inv.line_items || []).map(l => ({
      description: l.descrizione || l.description || '-',
      quantity: parseFloat(l.quantita || l.quantity || 1),
      unit_price: parseFloat(l.prezzo_unitario || l.unit_price || l.price || 0),
      price: parseFloat(l.prezzo_totale || l.prezzo_unitario || l.price || 0),
      vat_rate: parseFloat(l.aliquota_iva || l.vat_rate || 22),
      unit: l.unita_misura || l.unit || '',
    }));

    return {
      ...inv,
      line_items: lineItems,
      taxable_amount: inv.imponibile || inv.taxable_amount || 0,
      vat_amount: inv.iva || inv.vat_amount || 0,
      total_amount: inv.total_amount || 0,
      supplier_cf: inv.supplier_cf || inv.supplier_vat,
    };
  };

  const invoice = normalizeInvoice(rawInvoice);

  const formatCurrency = val => {
    return new Intl.NumberFormat('it-IT', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val || 0);
  };

  const formatDate = dateStr => {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  // Helper per tipo documento
  const getTipoDocumento = tipo => {
    const tipi = {
      TD01: 'Fattura',
      TD02: 'Acconto/Anticipo su fattura',
      TD03: 'Acconto/Anticipo su parcella',
      TD04: 'Nota di Credito',
      TD05: 'Nota di Debito',
      TD06: 'Parcella',
      TD16: 'Integrazione fattura reverse charge',
      TD17: 'Integrazione per acquisto servizi estero',
      TD18: 'Integrazione acquisto beni intracomunitari',
      TD19: 'Integrazione per acquisto beni art.17',
      TD20: 'Autofattura per regolarizzazione',
      TD24: 'Fattura differita art.21',
      TD25: 'Fattura differita terzo periodo',
      TD26: 'Cessione beni ammortizzabili',
      TD27: 'Autoconsumo/cessioni gratuite',
    };
    return tipi[tipo] || 'Fattura';
  };

  // Helper per modalità pagamento (codici SdI)
  const getModalitaPagamento = metodo => {
    const modalita = {
      bonifico: 'MP05 - Bonifico',
      banca: 'MP05 - Bonifico',
      assegno: 'MP02 - Assegno',
      cassa: 'MP01 - Contanti',
      carta: 'MP08 - Carta di pagamento',
      misto: 'Pagamento misto',
      cassa_da_confermare: 'Da verificare',
    };
    return modalita[metodo] || metodo || '-';
  };

  // Genera PDF/Stampa
  const generatePDFFromHTML = () => {
    if (!invoice) return;
    const isMinisteriale = viewMode === 'ministeriale';

    let bodyContent = '';
    if (isMinisteriale) {
      bodyContent = buildMinisterialeHTML();
    } else {
      bodyContent = buildAssoSoftwareHTML();
    }

    const html = `<!DOCTYPE html>
<html>
<head>
  <title>Fattura ${invoice.invoice_number}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: ${isMinisteriale ? "'Times New Roman', serif" : "'Arial', sans-serif"};
      padding: 20px; max-width: 800px; margin: 0 auto;
      color: #333; line-height: 1.4; font-size: 11px;
    }
    table { width: 100%; border-collapse: collapse; margin: 10px 0; }
    th, td { padding: 6px 8px; text-align: left; border: 1px solid #ccc; }
    th { background: #f0f0f0; font-weight: bold; font-size: 10px; }
    .header-box { border: 2px solid #333; padding: 15px; margin-bottom: 15px; }
    .section { margin-bottom: 15px; }
    .section-title { font-weight: bold; font-size: 12px; margin-bottom: 8px; padding: 5px; background: #e8e8e8; }
    .row { display: flex; margin-bottom: 4px; }
    .label { width: 150px; font-weight: bold; color: #555; }
    .value { flex: 1; }
    .total-box { border: 2px solid #333; padding: 10px; margin-top: 15px; }
    .total-row { display: flex; justify-content: space-between; padding: 4px 0; }
    .total-row.main { font-weight: bold; font-size: 14px; border-top: 2px solid #333; padding-top: 8px; margin-top: 8px; }
    @media print { body { padding: 0; } }
  </style>
</head>
<body>
  ${bodyContent}
  <script>window.onload = function() { window.print(); }<\/script>
</body>
</html>`;

    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const printWindow = window.open(url, '_blank');
    if (printWindow) {
      printWindow.addEventListener('load', () => URL.revokeObjectURL(url));
    }
  };

  // Costruisce HTML formato AssoSoftware (semplificata/completa)
  const buildAssoSoftwareHTML = () => {
    const isSemplificata = viewMode === 'semplificata';
    return `
      <div class="header-box" style="text-align: center;">
        <h1 style="font-size: 18px; margin-bottom: 5px;">FATTURA</h1>
        <div style="font-size: 12px;">N. ${invoice.invoice_number} del ${formatDate(invoice.invoice_date)}</div>
      </div>
      
      <div style="display: flex; gap: 20px; margin-bottom: 15px;">
        <div style="flex: 1; border: 1px solid #ccc; padding: 10px;">
          <div style="font-weight: bold; font-size: 11px; margin-bottom: 8px; color: #666;">CEDENTE / PRESTATORE</div>
          <div style="font-weight: bold; font-size: 13px;">${invoice.supplier_name || '-'}</div>
          <div>P.IVA: ${invoice.supplier_vat || '-'}</div>
          ${!isSemplificata && invoice.supplier_address ? `<div>${invoice.supplier_address}</div>` : ''}
        </div>
        <div style="flex: 1; border: 1px solid #ccc; padding: 10px;">
          <div style="font-weight: bold; font-size: 11px; margin-bottom: 8px; color: #666;">CESSIONARIO / COMMITTENTE</div>
          <div style="font-weight: bold; font-size: 13px;">CERALDI GROUP S.R.L.</div>
          <div>P.IVA: 12345678901</div>
        </div>
      </div>
      
      ${
        !isSemplificata
          ? `
      <div class="section">
        <div class="section-title">DATI DOCUMENTO</div>
        <div class="row"><span class="label">Tipo Documento:</span><span class="value">${invoice.tipo_documento || 'TD01'} - ${getTipoDocumento(invoice.tipo_documento)}</span></div>
        <div class="row"><span class="label">Data Ricezione:</span><span class="value">${formatDate(invoice.received_date)}</span></div>
      </div>
      `
          : ''
      }
      
      <div class="section">
        <div class="section-title">DETTAGLIO BENI E SERVIZI</div>
        <table>
          <thead>
            <tr>
              ${!isSemplificata ? '<th>Nr.</th>' : ''}
              <th style="width: 45%;">Descrizione</th>
              <th style="text-align: center;">Qtà</th>
              <th style="text-align: right;">Prezzo Unit.</th>
              <th style="text-align: center;">Aliq. IVA</th>
              <th style="text-align: right;">Importo</th>
            </tr>
          </thead>
          <tbody>
            ${(invoice.line_items || [])
              .map(
                (item, idx) => `
              <tr>
                ${!isSemplificata ? `<td>${idx + 1}</td>` : ''}
                <td>${item.description || '-'}</td>
                <td style="text-align: center;">${item.quantity || 1}</td>
                <td style="text-align: right;">€ ${formatCurrency(item.unit_price || item.price)}</td>
                <td style="text-align: center;">${item.vat_rate || 22}%</td>
                <td style="text-align: right;">€ ${formatCurrency((item.quantity || 1) * (item.unit_price || item.price || 0))}</td>
              </tr>
            `
              )
              .join('')}
          </tbody>
        </table>
      </div>
      
      ${
        !isSemplificata
          ? `
      <div class="section">
        <div class="section-title">RIEPILOGO IVA</div>
        <table>
          <thead>
            <tr>
              <th>Aliquota</th>
              <th style="text-align: right;">Imponibile</th>
              <th style="text-align: right;">Imposta</th>
              <th>Esigibilità</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>22%</td>
              <td style="text-align: right;">€ ${formatCurrency(invoice.taxable_amount)}</td>
              <td style="text-align: right;">€ ${formatCurrency(invoice.vat_amount)}</td>
              <td>Immediata</td>
            </tr>
          </tbody>
        </table>
      </div>
      `
          : ''
      }
      
      <div class="total-box">
        <div class="total-row"><span>Totale Imponibile:</span><span>€ ${formatCurrency(invoice.taxable_amount)}</span></div>
        <div class="total-row"><span>Totale IVA:</span><span>€ ${formatCurrency(invoice.vat_amount)}</span></div>
        <div class="total-row main"><span>TOTALE DOCUMENTO:</span><span>€ ${formatCurrency(invoice.total_amount)}</span></div>
      </div>
      
      ${
        !isSemplificata && (invoice.metodo_pagamento || invoice.payment_terms)
          ? `
      <div class="section" style="margin-top: 15px;">
        <div class="section-title">DATI PAGAMENTO</div>
        <div class="row"><span class="label">Modalità:</span><span class="value">${getModalitaPagamento(invoice.metodo_pagamento)}</span></div>
        ${invoice.payment_due_date ? `<div class="row"><span class="label">Scadenza:</span><span class="value">${formatDate(invoice.payment_due_date)}</span></div>` : ''}
      </div>
      `
          : ''
      }
      
      <div style="margin-top: 20px; text-align: center; font-size: 9px; color: #999; border-top: 1px solid #ccc; padding-top: 10px;">
        Documento generato il ${formatDateIT(new Date())} - Sistema ERP Azienda Semplice
      </div>
    `;
  };

  // Costruisce HTML formato Ministeriale (Agenzia Entrate)
  const buildMinisterialeHTML = () => {
    return `
      <div class="header-box" style="text-align: center; background: #f5f5f5;">
        <h1 style="font-size: 14px; text-transform: uppercase; letter-spacing: 2px;">FATTURA ELETTRONICA</h1>
        <div style="font-size: 11px; margin-top: 5px;">${getTipoDocumento(invoice.tipo_documento)}</div>
      </div>
      
      <div class="section">
        <div class="section-title">1. DATI TRASMISSIONE</div>
        <div class="row"><span class="label">Identificativo SdI:</span><span class="value">${invoice.sdi_id || invoice.id || '-'}</span></div>
        <div class="row"><span class="label">Data Ricezione:</span><span class="value">${formatDate(invoice.received_date)}</span></div>
      </div>
      
      <div class="section">
        <div class="section-title">1.2 CEDENTE / PRESTATORE</div>
        <div class="row"><span class="label">Denominazione:</span><span class="value">${invoice.supplier_name || '-'}</span></div>
        <div class="row"><span class="label">Partita IVA:</span><span class="value">${invoice.supplier_vat || '-'}</span></div>
        <div class="row"><span class="label">Codice Fiscale:</span><span class="value">${invoice.supplier_cf || invoice.supplier_vat || '-'}</span></div>
        ${invoice.supplier_address ? `<div class="row"><span class="label">Sede:</span><span class="value">${invoice.supplier_address}</span></div>` : ''}
      </div>
      
      <div class="section">
        <div class="section-title">1.4 CESSIONARIO / COMMITTENTE</div>
        <div class="row"><span class="label">Denominazione:</span><span class="value">CERALDI GROUP S.R.L.</span></div>
        <div class="row"><span class="label">Partita IVA:</span><span class="value">12345678901</span></div>
      </div>
      
      <div class="section">
        <div class="section-title">2. DATI GENERALI DOCUMENTO</div>
        <div class="row"><span class="label">Tipo Documento:</span><span class="value">${invoice.tipo_documento || 'TD01'} - ${getTipoDocumento(invoice.tipo_documento)}</span></div>
        <div class="row"><span class="label">Data:</span><span class="value">${formatDate(invoice.invoice_date)}</span></div>
        <div class="row"><span class="label">Numero:</span><span class="value">${invoice.invoice_number || '-'}</span></div>
        <div class="row"><span class="label">Importo Totale:</span><span class="value">€ ${formatCurrency(invoice.total_amount)}</span></div>
      </div>
      
      <div class="section">
        <div class="section-title">2.2 DATI BENI / SERVIZI</div>
        <table>
          <thead>
            <tr>
              <th>Nr.</th>
              <th style="width: 40%;">Descrizione</th>
              <th style="text-align: right;">Quantità</th>
              <th style="text-align: right;">Prezzo Unit.</th>
              <th style="text-align: center;">Aliq. IVA</th>
              <th style="text-align: right;">Prezzo Tot.</th>
            </tr>
          </thead>
          <tbody>
            ${(invoice.line_items || [])
              .map(
                (item, idx) => `
              <tr>
                <td>${idx + 1}</td>
                <td>${item.description || '-'}</td>
                <td style="text-align: right;">${item.quantity || 1}</td>
                <td style="text-align: right;">€ ${formatCurrency(item.unit_price || item.price)}</td>
                <td style="text-align: center;">${item.vat_rate || 22}%</td>
                <td style="text-align: right;">€ ${formatCurrency((item.quantity || 1) * (item.unit_price || item.price || 0))}</td>
              </tr>
            `
              )
              .join('')}
          </tbody>
        </table>
      </div>
      
      <div class="section">
        <div class="section-title">2.2.2 DATI RIEPILOGO</div>
        <table>
          <thead>
            <tr>
              <th>Aliquota IVA</th>
              <th style="text-align: right;">Imponibile</th>
              <th style="text-align: right;">Imposta</th>
              <th>Esigibilità IVA</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>22%</td>
              <td style="text-align: right;">€ ${formatCurrency(invoice.taxable_amount)}</td>
              <td style="text-align: right;">€ ${formatCurrency(invoice.vat_amount)}</td>
              <td>I - Immediata</td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div class="total-box">
        <div class="total-row"><span>Totale Imponibile:</span><span>€ ${formatCurrency(invoice.taxable_amount)}</span></div>
        <div class="total-row"><span>Totale Imposta:</span><span>€ ${formatCurrency(invoice.vat_amount)}</span></div>
        <div class="total-row main"><span>IMPORTO TOTALE DOCUMENTO:</span><span>€ ${formatCurrency(invoice.total_amount)}</span></div>
      </div>
      
      ${
        invoice.metodo_pagamento || invoice.payment_terms
          ? `
      <div class="section" style="margin-top: 15px;">
        <div class="section-title">2.4 DATI PAGAMENTO</div>
        <div class="row"><span class="label">Condizioni Pagamento:</span><span class="value">${invoice.payment_terms || 'Pagamento completo'}</span></div>
        <div class="row"><span class="label">Modalità Pagamento:</span><span class="value">${getModalitaPagamento(invoice.metodo_pagamento)}</span></div>
        ${invoice.payment_due_date ? `<div class="row"><span class="label">Data Scadenza:</span><span class="value">${formatDate(invoice.payment_due_date)}</span></div>` : ''}
      </div>
      `
          : ''
      }
      
      <div style="margin-top: 20px; text-align: center; font-size: 9px; color: #666; border-top: 1px solid #ccc; padding-top: 10px;">
        Documento informatico conforme alle specifiche tecniche dell'Agenzia delle Entrate<br>
        Visualizzazione generata il ${formatDateIT(new Date())} - Sistema ERP Azienda Semplice
      </div>
    `;
  };

  if (!invoice) {
    return (
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
      >
        <div style={{ background: 'white', padding: 40, borderRadius: 12, textAlign: 'center' }}>
          <p>❌ Fattura non trovata</p>
          <button onClick={onClose} style={{ marginTop: 16, padding: '8px 16px' }}>
            Chiudi
          </button>
        </div>
      </div>
    );
  }

  // ============================================
  // RENDER FORMATO SEMPLIFICATA
  // ============================================
  const renderSemplificataView = () => (
    <div style={{ fontFamily: 'Arial, sans-serif' }}>
      {/* Header compatto */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '15px 20px',
          background: '#f8f9fa',
          borderRadius: 8,
          marginBottom: 20,
        }}
      >
        <div>
          <div style={{ fontSize: 11, color: '#666', textTransform: 'uppercase' }}>Fattura N.</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#1e3a5f' }}>
            {invoice.invoice_number}
          </div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 11, color: '#666', textTransform: 'uppercase' }}>Data</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{formatDate(invoice.invoice_date)}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 11, color: '#666', textTransform: 'uppercase' }}>Totale</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#1e3a5f' }}>
            € {formatCurrency(invoice.total_amount)}
          </div>
        </div>
      </div>

      {/* Parti - compatto */}
      <div style={{ display: 'flex', gap: 15, marginBottom: 20 }}>
        <div
          style={{
            flex: 1,
            padding: 12,
            background: '#e3f2fd',
            borderRadius: 6,
            borderLeft: '3px solid #1976d2',
          }}
        >
          <div
            style={{ fontSize: 10, color: '#1565c0', textTransform: 'uppercase', marginBottom: 4 }}
          >
            Fornitore
          </div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{invoice.supplier_name}</div>
          <div style={{ fontSize: 12, color: '#666' }}>P.IVA: {invoice.supplier_vat}</div>
        </div>
        <div
          style={{
            flex: 1,
            padding: 12,
            background: '#e8f5e9',
            borderRadius: 6,
            borderLeft: '3px solid #388e3c',
          }}
        >
          <div
            style={{ fontSize: 10, color: '#2e7d32', textTransform: 'uppercase', marginBottom: 4 }}
          >
            Cliente
          </div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>CERALDI GROUP S.R.L.</div>
          <div style={{ fontSize: 12, color: '#666' }}>P.IVA: 12345678901</div>
        </div>
      </div>

      {/* Righe - compatto */}
      <div
        style={{
          background: 'white',
          borderRadius: 8,
          overflow: 'hidden',
          border: '1px solid #e0e0e0',
          overflowX: 'auto',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>
                Descrizione
              </th>
              <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600, width: 60 }}>
                Qtà
              </th>
              <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600, width: 90 }}>
                Prezzo
              </th>
              <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600, width: 50 }}>
                IVA
              </th>
              <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600, width: 90 }}>
                Totale
              </th>
            </tr>
          </thead>
          <tbody>
            {(invoice.line_items || []).map((item, idx) => (
              <tr key={idx} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: '8px 12px' }}>{item.description}</td>
                <td style={{ padding: '8px 12px', textAlign: 'center' }}>{item.quantity || 1}</td>
                <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                  € {formatCurrency(item.unit_price || item.price)}
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'center' }}>{item.vat_rate || 22}%</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 500 }}>
                  € {formatCurrency((item.quantity || 1) * (item.unit_price || item.price || 0))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Totali compatti */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 15 }}>
        <div
          style={{
            background: '#f8f9fa',
            padding: 15,
            borderRadius: 8,
            minWidth: 220,
            border: '1px solid #e0e0e0',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: 12,
              marginBottom: 6,
            }}
          >
            <span style={{ color: '#666' }}>Imponibile:</span>
            <span>€ {formatCurrency(invoice.taxable_amount)}</span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: 12,
              marginBottom: 10,
            }}
          >
            <span style={{ color: '#666' }}>IVA:</span>
            <span>€ {formatCurrency(invoice.vat_amount)}</span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              paddingTop: 10,
              borderTop: '2px solid #1e3a5f',
            }}
          >
            <span style={{ fontWeight: 700, color: '#1e3a5f' }}>TOTALE:</span>
            <span style={{ fontWeight: 700, fontSize: 16, color: '#1e3a5f' }}>
              € {formatCurrency(invoice.total_amount)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );

  // ============================================
  // RENDER FORMATO COMPLETA (AssoSoftware standard)
  // ============================================
  const renderCompletaView = () => (
    <div style={{ fontFamily: 'Arial, sans-serif' }}>
      {/* Header tipo fattura cartacea */}
      <div
        style={{
          textAlign: 'center',
          padding: 20,
          border: '2px solid #1e3a5f',
          borderRadius: 8,
          marginBottom: 20,
          background: '#f8fafc',
        }}
      >
        <h2
          style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#1e3a5f', letterSpacing: 1 }}
        >
          FATTURA
        </h2>
        <div style={{ fontSize: 13, color: '#666', marginTop: 5 }}>
          N. <strong>{invoice.invoice_number}</strong> del{' '}
          <strong>{formatDate(invoice.invoice_date)}</strong>
        </div>
        <div style={{ fontSize: 11, color: '#888', marginTop: 3 }}>
          {invoice.tipo_documento || 'TD01'} - {getTipoDocumento(invoice.tipo_documento)}
        </div>
      </div>

      {/* Cedente / Cessionario - layout tradizionale */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <div
          style={{
            border: '1px solid #ccc',
            borderRadius: 6,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              background: '#e3f2fd',
              padding: '8px 12px',
              fontSize: 11,
              fontWeight: 600,
              color: '#1565c0',
              textTransform: 'uppercase',
              borderBottom: '1px solid #bbdefb',
            }}
          >
            Cedente / Prestatore
          </div>
          <div style={{ padding: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>
              {invoice.supplier_name}
            </div>
            <div style={{ fontSize: 12, color: '#555', lineHeight: 1.6 }}>
              <div>P.IVA: {invoice.supplier_vat}</div>
              {invoice.supplier_cf && <div>C.F.: {invoice.supplier_cf}</div>}
              {invoice.supplier_address && <div>{invoice.supplier_address}</div>}
            </div>
          </div>
        </div>
        <div
          style={{
            border: '1px solid #ccc',
            borderRadius: 6,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              background: '#e8f5e9',
              padding: '8px 12px',
              fontSize: 11,
              fontWeight: 600,
              color: '#2e7d32',
              textTransform: 'uppercase',
              borderBottom: '1px solid #c8e6c9',
            }}
          >
            Cessionario / Committente
          </div>
          <div style={{ padding: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>
              CERALDI GROUP S.R.L.
            </div>
            <div style={{ fontSize: 12, color: '#555', lineHeight: 1.6 }}>
              <div>P.IVA: 12345678901</div>
            </div>
          </div>
        </div>
      </div>

      {/* Info documento */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          marginBottom: 20,
          padding: 12,
          background: '#fafafa',
          borderRadius: 6,
          border: '1px solid #e0e0e0',
        }}
      >
        <div>
          <div style={{ fontSize: 10, color: '#666', textTransform: 'uppercase' }}>
            Data Ricezione
          </div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{formatDate(invoice.received_date)}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#666', textTransform: 'uppercase' }}>ID SdI</div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{invoice.sdi_id || '-'}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#666', textTransform: 'uppercase' }}>Stato</div>
          <div
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: invoice.pagato ? '#2e7d32' : '#e65100',
            }}
          >
            {invoice.pagato ? '✓ Pagata' : '⏳ Da Pagare'}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#666', textTransform: 'uppercase' }}>Metodo Pag.</div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{invoice.metodo_pagamento || '-'}</div>
        </div>
      </div>

      {/* Dettaglio Linee */}
      <div style={{ marginBottom: 20 }}>
        <div
          style={{
            background: '#1e3a5f',
            color: 'white',
            padding: '10px 15px',
            fontWeight: 600,
            fontSize: 12,
            textTransform: 'uppercase',
            borderRadius: '6px 6px 0 0',
          }}
        >
          Dettaglio Beni e Servizi
        </div>
        <div
          style={{
            border: '1px solid #1e3a5f',
            borderTop: 'none',
            borderRadius: '0 0 6px 6px',
            overflow: 'hidden',
            overflowX: 'auto',
          }}
        >
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f0f4f8' }}>
                <th
                  style={{
                    padding: '10px',
                    textAlign: 'center',
                    fontWeight: 600,
                    width: 40,
                    borderRight: '1px solid #e0e0e0',
                  }}
                >
                  Nr.
                </th>
                <th
                  style={{
                    padding: '10px',
                    textAlign: 'left',
                    fontWeight: 600,
                    borderRight: '1px solid #e0e0e0',
                  }}
                >
                  Descrizione
                </th>
                <th
                  style={{
                    padding: '10px',
                    textAlign: 'center',
                    fontWeight: 600,
                    width: 60,
                    borderRight: '1px solid #e0e0e0',
                  }}
                >
                  Qtà
                </th>
                <th
                  style={{
                    padding: '10px',
                    textAlign: 'right',
                    fontWeight: 600,
                    width: 90,
                    borderRight: '1px solid #e0e0e0',
                  }}
                >
                  Prezzo Unit.
                </th>
                <th
                  style={{
                    padding: '10px',
                    textAlign: 'center',
                    fontWeight: 600,
                    width: 60,
                    borderRight: '1px solid #e0e0e0',
                  }}
                >
                  Aliq.
                </th>
                <th style={{ padding: '10px', textAlign: 'right', fontWeight: 600, width: 100 }}>
                  Importo
                </th>
              </tr>
            </thead>
            <tbody>
              {(invoice.line_items || []).map((item, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid #e8e8e8' }}>
                  <td
                    style={{
                      padding: '8px 10px',
                      textAlign: 'center',
                      borderRight: '1px solid #f0f0f0',
                    }}
                  >
                    {idx + 1}
                  </td>
                  <td style={{ padding: '8px 10px', borderRight: '1px solid #f0f0f0' }}>
                    {item.description}
                  </td>
                  <td
                    style={{
                      padding: '8px 10px',
                      textAlign: 'center',
                      borderRight: '1px solid #f0f0f0',
                    }}
                  >
                    {item.quantity || 1}
                  </td>
                  <td
                    style={{
                      padding: '8px 10px',
                      textAlign: 'right',
                      borderRight: '1px solid #f0f0f0',
                    }}
                  >
                    € {formatCurrency(item.unit_price || item.price)}
                  </td>
                  <td
                    style={{
                      padding: '8px 10px',
                      textAlign: 'center',
                      borderRight: '1px solid #f0f0f0',
                    }}
                  >
                    {item.vat_rate || 22}%
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 500 }}>
                    € {formatCurrency((item.quantity || 1) * (item.unit_price || item.price || 0))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Riepilogo IVA */}
      <div style={{ marginBottom: 20 }}>
        <div
          style={{
            background: '#455a64',
            color: 'white',
            padding: '8px 15px',
            fontWeight: 600,
            fontSize: 11,
            textTransform: 'uppercase',
            borderRadius: '6px 6px 0 0',
          }}
        >
          Riepilogo IVA
        </div>
        <div
          style={{
            border: '1px solid #455a64',
            borderTop: 'none',
            borderRadius: '0 0 6px 6px',
            overflow: 'hidden',
            overflowX: 'auto',
          }}
        >
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f5f5f5' }}>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600 }}>
                  Aliquota
                </th>
                <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600 }}>
                  Imponibile
                </th>
                <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600 }}>
                  Imposta
                </th>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600 }}>
                  Esigibilità
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '8px 10px' }}>22%</td>
                <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                  € {formatCurrency(invoice.taxable_amount)}
                </td>
                <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                  € {formatCurrency(invoice.vat_amount)}
                </td>
                <td style={{ padding: '8px 10px' }}>Immediata (I)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Totali */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <div
          style={{
            border: '2px solid #1e3a5f',
            borderRadius: 8,
            overflow: 'hidden',
            minWidth: 280,
          }}
        >
          <div style={{ padding: '10px 15px', background: '#f8fafc' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: 6,
                fontSize: 13,
              }}
            >
              <span>Totale Imponibile:</span>
              <span>€ {formatCurrency(invoice.taxable_amount)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <span>Totale IVA:</span>
              <span>€ {formatCurrency(invoice.vat_amount)}</span>
            </div>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              padding: '12px 15px',
              background: '#1e3a5f',
              color: 'white',
              fontWeight: 700,
              fontSize: 15,
            }}
          >
            <span>TOTALE DOCUMENTO:</span>
            <span>€ {formatCurrency(invoice.total_amount)}</span>
          </div>
        </div>
      </div>

      {/* Dati Pagamento */}
      {(invoice.metodo_pagamento || invoice.payment_terms) && (
        <div
          style={{
            marginTop: 20,
            padding: 15,
            background: '#fff8e1',
            borderRadius: 8,
            borderLeft: '4px solid #ffc107',
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 8, color: '#f57c00' }}>
            DATI PAGAMENTO
          </div>
          <div style={{ fontSize: 13 }}>
            <span style={{ color: '#666' }}>Modalità: </span>
            <span style={{ fontWeight: 500 }}>
              {getModalitaPagamento(invoice.metodo_pagamento)}
            </span>
          </div>
          {invoice.payment_due_date && (
            <div style={{ fontSize: 13, marginTop: 4 }}>
              <span style={{ color: '#666' }}>Scadenza: </span>
              <span style={{ fontWeight: 500 }}>{formatDate(invoice.payment_due_date)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );

  // ============================================
  // RENDER FORMATO MINISTERIALE (Agenzia Entrate)
  // ============================================
  const renderMinisterialeView = () => (
    <div style={{ fontFamily: "'Times New Roman', Georgia, serif", fontSize: 12 }}>
      {/* Header Ministeriale */}
      <div
        style={{
          textAlign: 'center',
          border: '2px solid #000',
          padding: 15,
          marginBottom: 20,
          background: '#f5f5f5',
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: 15,
            fontWeight: 'bold',
            textTransform: 'uppercase',
            letterSpacing: 2,
          }}
        >
          FATTURA ELETTRONICA
        </h2>
        <div style={{ fontSize: 12, marginTop: 5 }}>{getTipoDocumento(invoice.tipo_documento)}</div>
      </div>

      {/* Sezione 1 - Dati Trasmissione */}
      <div style={{ border: '1px solid #000', marginBottom: 12 }}>
        <div
          style={{
            background: '#e0e0e0',
            padding: '5px 10px',
            fontWeight: 'bold',
            fontSize: 11,
            textTransform: 'uppercase',
            borderBottom: '1px solid #000',
          }}
        >
          1. Dati Trasmissione
        </div>
        <div style={{ padding: 10 }}>
          <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Identificativo SdI:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>{invoice.sdi_id || invoice.id || '-'}</span>
          </div>
          <div style={{ display: 'flex', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Data Ricezione:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>{formatDate(invoice.received_date)}</span>
          </div>
        </div>
      </div>

      {/* Sezione 1.2 - Cedente/Prestatore */}
      <div style={{ border: '1px solid #000', marginBottom: 12 }}>
        <div
          style={{
            background: '#e0e0e0',
            padding: '5px 10px',
            fontWeight: 'bold',
            fontSize: 11,
            textTransform: 'uppercase',
            borderBottom: '1px solid #000',
          }}
        >
          1.2 Cedente / Prestatore
        </div>
        <div style={{ padding: 10 }}>
          <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Denominazione:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>{invoice.supplier_name || '-'}</span>
          </div>
          <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Partita IVA:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>{invoice.supplier_vat || '-'}</span>
          </div>
          <div style={{ display: 'flex', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Codice Fiscale:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>
              {invoice.supplier_cf || invoice.supplier_vat || '-'}
            </span>
          </div>
        </div>
      </div>

      {/* Sezione 1.4 - Cessionario/Committente */}
      <div style={{ border: '1px solid #000', marginBottom: 12 }}>
        <div
          style={{
            background: '#e0e0e0',
            padding: '5px 10px',
            fontWeight: 'bold',
            fontSize: 11,
            textTransform: 'uppercase',
            borderBottom: '1px solid #000',
          }}
        >
          1.4 Cessionario / Committente
        </div>
        <div style={{ padding: 10 }}>
          <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Denominazione:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>CERALDI GROUP S.R.L.</span>
          </div>
          <div style={{ display: 'flex', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Partita IVA:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>12345678901</span>
          </div>
        </div>
      </div>

      {/* Sezione 2 - Dati Generali Documento */}
      <div style={{ border: '1px solid #000', marginBottom: 12 }}>
        <div
          style={{
            background: '#e0e0e0',
            padding: '5px 10px',
            fontWeight: 'bold',
            fontSize: 11,
            textTransform: 'uppercase',
            borderBottom: '1px solid #000',
          }}
        >
          2. Dati Generali Documento
        </div>
        <div style={{ padding: 10 }}>
          <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Tipo Documento:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>
              {invoice.tipo_documento || 'TD01'} - {getTipoDocumento(invoice.tipo_documento)}
            </span>
          </div>
          <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Data:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>{formatDate(invoice.invoice_date)}</span>
          </div>
          <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Numero:
            </span>
            <span style={{ flex: 1, fontSize: 11 }}>{invoice.invoice_number || '-'}</span>
          </div>
          <div style={{ display: 'flex', padding: '4px 0' }}>
            <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
              Importo Totale:
            </span>
            <span style={{ flex: 1, fontSize: 11, fontWeight: 'bold' }}>
              € {formatCurrency(invoice.total_amount)}
            </span>
          </div>
        </div>
      </div>

      {/* Sezione 2.2 - Dati Beni/Servizi */}
      <div style={{ border: '1px solid #000', marginBottom: 12 }}>
        <div
          style={{
            background: '#e0e0e0',
            padding: '5px 10px',
            fontWeight: 'bold',
            fontSize: 11,
            textTransform: 'uppercase',
            borderBottom: '1px solid #000',
          }}
        >
          2.2 Dati Beni / Servizi
        </div>
        <div style={{ padding: 10, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
            <thead>
              <tr>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'left',
                    fontSize: 9,
                    textTransform: 'uppercase',
                  }}
                >
                  Nr.
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'left',
                    fontSize: 9,
                    textTransform: 'uppercase',
                  }}
                >
                  Descrizione
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'right',
                    fontSize: 9,
                    textTransform: 'uppercase',
                  }}
                >
                  Qtà
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'right',
                    fontSize: 9,
                    textTransform: 'uppercase',
                  }}
                >
                  Prezzo
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'center',
                    fontSize: 9,
                    textTransform: 'uppercase',
                  }}
                >
                  IVA
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'right',
                    fontSize: 9,
                    textTransform: 'uppercase',
                  }}
                >
                  Totale
                </th>
              </tr>
            </thead>
            <tbody>
              {(invoice.line_items || []).map((item, idx) => (
                <tr key={idx}>
                  <td style={{ border: '1px solid #ccc', padding: 5 }}>{idx + 1}</td>
                  <td style={{ border: '1px solid #ccc', padding: 5 }}>{item.description}</td>
                  <td style={{ border: '1px solid #ccc', padding: 5, textAlign: 'right' }}>
                    {item.quantity || 1}
                  </td>
                  <td style={{ border: '1px solid #ccc', padding: 5, textAlign: 'right' }}>
                    € {formatCurrency(item.unit_price || item.price)}
                  </td>
                  <td style={{ border: '1px solid #ccc', padding: 5, textAlign: 'center' }}>
                    {item.vat_rate || 22}%
                  </td>
                  <td style={{ border: '1px solid #ccc', padding: 5, textAlign: 'right' }}>
                    € {formatCurrency((item.quantity || 1) * (item.unit_price || item.price || 0))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Sezione 2.2.2 - Dati Riepilogo */}
      <div style={{ border: '1px solid #000', marginBottom: 12 }}>
        <div
          style={{
            background: '#e0e0e0',
            padding: '5px 10px',
            fontWeight: 'bold',
            fontSize: 11,
            textTransform: 'uppercase',
            borderBottom: '1px solid #000',
          }}
        >
          2.2.2 Dati Riepilogo
        </div>
        <div style={{ padding: 10, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
            <thead>
              <tr>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    fontSize: 9,
                  }}
                >
                  Aliquota IVA
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'right',
                    fontSize: 9,
                  }}
                >
                  Imponibile
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    textAlign: 'right',
                    fontSize: 9,
                  }}
                >
                  Imposta
                </th>
                <th
                  style={{
                    background: '#e8e8e8',
                    border: '1px solid #999',
                    padding: 5,
                    fontSize: 9,
                  }}
                >
                  Esigibilità IVA
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ border: '1px solid #ccc', padding: 5 }}>22%</td>
                <td style={{ border: '1px solid #ccc', padding: 5, textAlign: 'right' }}>
                  € {formatCurrency(invoice.taxable_amount)}
                </td>
                <td style={{ border: '1px solid #ccc', padding: 5, textAlign: 'right' }}>
                  € {formatCurrency(invoice.vat_amount)}
                </td>
                <td style={{ border: '1px solid #ccc', padding: 5 }}>I - Immediata</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Totali */}
      <div style={{ border: '2px solid #000', marginBottom: 12 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '8px 12px',
            borderBottom: '1px solid #000',
          }}
        >
          <span>Totale Imponibile:</span>
          <span>€ {formatCurrency(invoice.taxable_amount)}</span>
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '8px 12px',
            borderBottom: '1px solid #000',
          }}
        >
          <span>Totale Imposta:</span>
          <span>€ {formatCurrency(invoice.vat_amount)}</span>
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '10px 12px',
            background: '#f0f0f0',
            fontWeight: 'bold',
            fontSize: 13,
          }}
        >
          <span>IMPORTO TOTALE DOCUMENTO:</span>
          <span>€ {formatCurrency(invoice.total_amount)}</span>
        </div>
      </div>

      {/* Sezione 2.4 - Dati Pagamento */}
      {(invoice.metodo_pagamento || invoice.payment_terms) && (
        <div style={{ border: '1px solid #000' }}>
          <div
            style={{
              background: '#e0e0e0',
              padding: '5px 10px',
              fontWeight: 'bold',
              fontSize: 11,
              textTransform: 'uppercase',
              borderBottom: '1px solid #000',
            }}
          >
            2.4 Dati Pagamento
          </div>
          <div style={{ padding: 10 }}>
            <div style={{ display: 'flex', borderBottom: '1px solid #ddd', padding: '4px 0' }}>
              <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
                Condizioni Pagamento:
              </span>
              <span style={{ flex: 1, fontSize: 11 }}>
                {invoice.payment_terms || 'TP02 - Pagamento completo'}
              </span>
            </div>
            <div style={{ display: 'flex', padding: '4px 0' }}>
              <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
                Modalità Pagamento:
              </span>
              <span style={{ flex: 1, fontSize: 11 }}>
                {getModalitaPagamento(invoice.metodo_pagamento)}
              </span>
            </div>
            {invoice.payment_due_date && (
              <div style={{ display: 'flex', padding: '4px 0' }}>
                <span style={{ width: 180, fontWeight: 'bold', fontSize: 10, color: '#555' }}>
                  Data Scadenza:
                </span>
                <span style={{ flex: 1, fontSize: 11 }}>
                  {formatDate(invoice.payment_due_date)}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

  // Determina quale view renderizzare
  const renderCurrentView = () => {
    switch (viewMode) {
      case 'semplificata':
        return renderSemplificataView();
      case 'ministeriale':
        return renderMinisterialeView();
      case 'completa':
      default:
        return renderCompletaView();
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 20,
      }}
    >
      <div
        style={{
          background: 'white',
          width: '100%',
          maxWidth: 900,
          maxHeight: '90vh',
          borderRadius: 16,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '12px 20px',
            background: viewMode === 'ministeriale' ? '#37474f' : '#1e3a5f',
            color: 'white',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 10,
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 16 }}>📄 Fattura {invoice.invoice_number}</h2>
            <p style={{ margin: '2px 0 0', opacity: 0.8, fontSize: 12 }}>{invoice.supplier_name}</p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Toggle View Mode - 3 opzioni come AssoInvoice */}
            <div
              style={{
                display: 'flex',
                background: 'rgba(255,255,255,0.15)',
                borderRadius: 6,
                overflow: 'hidden',
              }}
            >
              <button
                onClick={() => setViewMode('semplificata')}
                style={{
                  padding: '5px 10px',
                  background: viewMode === 'semplificata' ? 'rgba(255,255,255,0.3)' : 'transparent',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: viewMode === 'semplificata' ? 600 : 400,
                }}
                title="Visualizzazione Semplificata - Solo dati fiscali essenziali"
                data-testid="view-mode-semplificata"
              >
                Semplificata
              </button>
              <button
                onClick={() => setViewMode('completa')}
                style={{
                  padding: '5px 10px',
                  background: viewMode === 'completa' ? 'rgba(255,255,255,0.3)' : 'transparent',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: viewMode === 'completa' ? 600 : 400,
                }}
                title="Visualizzazione Completa - Tutti i dati incluse info gestionali"
                data-testid="view-mode-completa"
              >
                Completa
              </button>
              <button
                onClick={() => setViewMode('ministeriale')}
                style={{
                  padding: '5px 10px',
                  background: viewMode === 'ministeriale' ? 'rgba(255,255,255,0.3)' : 'transparent',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: viewMode === 'ministeriale' ? 600 : 400,
                }}
                title="Visualizzazione Ministeriale - Formato ufficiale Agenzia Entrate"
                data-testid="view-mode-ministeriale"
              >
                Ministeriale
              </button>
            </div>
            <button
              onClick={generatePDFFromHTML}
              style={{
                padding: '6px 14px',
                background: '#4caf50',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 12,
              }}
              data-testid="print-invoice-btn"
            >
              🖨️ Stampa
            </button>
            <button
              onClick={onClose}
              style={{
                padding: '6px 14px',
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 12,
              }}
              data-testid="close-invoice-viewer"
            >
              ✕ Chiudi
            </button>
          </div>
        </div>

        {/* Content */}
        <div
          style={{
            flex: 1,
            overflow: 'auto',
            padding: 20,
            background: viewMode === 'ministeriale' ? '#fafafa' : '#f8fafc',
          }}
        >
          {renderCurrentView()}
        </div>
      </div>
    </div>
  );
}
