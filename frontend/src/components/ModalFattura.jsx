import React, { useEffect, useState } from 'react';
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
  const [documentiPagamento, setDocumentiPagamento] = useState([]);
  const [pagamentoSelezionato, setPagamentoSelezionato] = useState(null);

  useEffect(() => {
    if (!fatturaId) return undefined;
    let active = true;
    api.get(`/api/fatture-ricevute/fattura/${fatturaId}/documenti-pagamento`)
      .then(response => {
        if (active) setDocumentiPagamento(response.data?.documenti || []);
      })
      .catch(() => {
        if (active) setDocumentiPagamento([]);
      });
    return () => { active = false; };
  }, [fatturaId]);

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
      title={pagamentoSelezionato
        ? `Pagamento ${pagamentoSelezionato.nome_file || ''}`.trim()
        : `Fattura ${numero || fatturaId}`}
      subtitle={pagamentoSelezionato
        ? `${pagamentoSelezionato.data || ''} · € ${Number(pagamentoSelezionato.importo || 0).toLocaleString('it-IT', { minimumFractionDigits: 2 })}`
        : undefined}
      src={pagamentoSelezionato ? undefined : `/api/fatture-ricevute/fattura/${fatturaId}/view-assoinvoice`}
      fetchUrl={pagamentoSelezionato?.view_url}
      onClose={onClose}
      onDownload={pagamentoSelezionato ? undefined : scaricaXmlOriginale}
      extraActions={pagamentoSelezionato ? (
        <button type="button" onClick={() => setPagamentoSelezionato(null)}
          aria-label="Torna alla fattura" title="Torna alla fattura"
          style={{ minHeight: 40, padding: '0 12px', border: 0, borderRadius: 8, background: 'rgba(255,255,255,0.15)', color: 'white', fontWeight: 700, cursor: 'pointer' }}>
          Fattura
        </button>
      ) : documentiPagamento.map((documento, index) => (
        <button type="button" key={documento.id}
          onClick={() => setPagamentoSelezionato(documento)}
          aria-label={`Vedi pagamento ${index + 1}`} title={documento.nome_file || 'Vedi pagamento'}
          style={{ minHeight: 40, padding: '0 12px', border: 0, borderRadius: 8, background: '#15803d', color: 'white', fontWeight: 700, cursor: 'pointer' }}>
          Pagamento {documentiPagamento.length > 1 ? index + 1 : ''}
        </button>
      ))}
      testIdPrefix="modal-fattura"
    />
  );
}
