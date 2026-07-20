import React from 'react';
import { toast } from 'sonner';
import api from '../api';
import DocumentViewerModal from './DocumentViewerModal';

/**
 * Modale in-page per visualizzare una fattura (view-assoinvoice), senza
 * aprire nuove schede del browser. Wrapper sottile sul motore condiviso
 * DocumentViewerModal: stesso aspetto e stessi data-testid di sempre.
 *
 * Include sempre il pulsante "Scarica" per l'XML FatturaPA ORIGINALE
 * (richiesta utente 19/07/2026: "io ho bisogno di vedere sempre
 * l'originale la fattura così come arriva" — la vista principale può
 * mostrare un riepilogo ricostruito quando l'XML non è disponibile o non
 * è renderizzabile via XSLT, ma l'originale grezzo deve restare sempre
 * scaricabile per il controllo).
 *
 * Props:
 *  - fatturaId: id della fattura da visualizzare
 *  - numero:    numero fattura (per il titolo/nome file, opzionale)
 *  - onClose:   callback di chiusura
 */
export default function ModalFattura({ fatturaId, numero, onClose }) {
  if (!fatturaId) return null;

  const scaricaXmlOriginale = async () => {
    try {
      const response = await api.get(`/api/fatture-ricevute/fattura/${fatturaId}/xml-originale`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/xml' }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `fattura_${numero || fatturaId}.xml`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      toast.error('XML originale non disponibile', {
        description: error.response?.data?.detail || error.message,
      });
    }
  };

  return (
    <DocumentViewerModal
      title={`📄 Fattura ${numero || fatturaId}`}
      src={`/api/fatture-ricevute/fattura/${fatturaId}/view-assoinvoice`}
      onClose={onClose}
      onDownload={scaricaXmlOriginale}
      testIdPrefix="modal-fattura"
    />
  );
}
