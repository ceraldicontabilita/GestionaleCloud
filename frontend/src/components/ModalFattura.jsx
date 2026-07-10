import React from 'react';
import DocumentViewerModal from './DocumentViewerModal';

/**
 * Modale in-page per visualizzare una fattura (view-assoinvoice), senza
 * aprire nuove schede del browser. Wrapper sottile sul motore condiviso
 * DocumentViewerModal: stesso aspetto e stessi data-testid di sempre.
 *
 * Props:
 *  - fatturaId: id della fattura da visualizzare
 *  - numero:    numero fattura (per il titolo, opzionale)
 *  - onClose:   callback di chiusura
 */
export default function ModalFattura({ fatturaId, numero, onClose }) {
  if (!fatturaId) return null;

  return (
    <DocumentViewerModal
      title={`📄 Fattura ${numero || fatturaId}`}
      src={`/api/fatture-ricevute/fattura/${fatturaId}/view-assoinvoice`}
      onClose={onClose}
      testIdPrefix="modal-fattura"
    />
  );
}
