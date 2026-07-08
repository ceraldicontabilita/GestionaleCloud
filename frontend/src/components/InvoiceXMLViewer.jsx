import React from 'react';
import ModalFattura from './ModalFattura';

/**
 * Wrapper retrocompatibile.
 * Manteniamo l'export per le pagine legacy ma la visualizzazione reale
 * passa sempre dal renderer proprietario backend `view-assoinvoice`,
 * basato su XML + foglio stile AssoSoftware.
 */
export default function InvoiceXMLViewer({ invoice, onClose }) {
  if (!invoice) return null;

  const fatturaId = invoice.id || invoice.fattura_id;
  const numero = invoice.invoice_number || invoice.numero || invoice.numero_fattura;

  if (!fatturaId) return null;

  return <ModalFattura fatturaId={fatturaId} numero={numero} onClose={onClose} />;
}
