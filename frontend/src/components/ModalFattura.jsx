import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import api from '../api';
import DocumentViewerModal from './DocumentViewerModal';
import { messaggioErroreOriginale, scaricaOriginale } from '../lib/scaricaOriginale';
import { urlOriginale } from '../lib/vista';

/**
 * Modale in-page per visualizzare una fattura (view-assoinvoice), senza
 * aprire nuove schede del browser. Wrapper sottile sul motore condiviso
 * DocumentViewerModal: stesso aspetto e stessi data-testid di sempre.
 *
 * XML con foglio AssoSoftware; per le fatture estere apre il PDF originale.
 * Il download mantiene formato e nome dichiarati dal reader canonico.
 *
 * Props:
 *  - fatturaId: id della fattura da visualizzare
 *  - numero:    numero fattura (per il titolo/nome file, opzionale)
 *  - onClose:   callback di chiusura
 */
export default function ModalFattura({ fatturaId, numero, onClose }) {
  const [documentiPagamento, setDocumentiPagamento] = useState([]);
  const [pagamentoSelezionato, setPagamentoSelezionato] = useState(null);
  // Il PDF che il fornitore allega dentro l'XML (<Allegati>): prima non si
  // vedeva da nessuna parte.
  const [allegati, setAllegati] = useState([]);

  useEffect(() => {
    if (!fatturaId) return undefined;
    let active = true;
    api.get(`/api/fatture-ricevute/fattura/${fatturaId}/allegati`)
      .then(response => {
        if (active) setAllegati(response.data?.allegati || []);
      })
      .catch(() => {
        if (active) setAllegati([]);
      });
    return () => { active = false; };
  }, [fatturaId]);

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

  const scaricaFatturaOriginale = async () => {
    try {
      await scaricaOriginale(
        urlOriginale({ tipo: 'fattura', id: fatturaId }),
        `fattura_${numero || fatturaId}`,
      );
    } catch (error) {
      toast.error('Originale non disponibile', {
        description: await messaggioErroreOriginale(error, error.message),
      });
    }
  };

  return (
    <DocumentViewerModal
      title={pagamentoSelezionato
        ? `${pagamentoSelezionato.allegato ? 'Allegato' : 'Pagamento'} ${pagamentoSelezionato.nome_file || ''}`.trim()
        : `Fattura ${numero || fatturaId}`}
      subtitle={pagamentoSelezionato && !pagamentoSelezionato.allegato
        ? `${pagamentoSelezionato.data || ''} · € ${Number(pagamentoSelezionato.importo || 0).toLocaleString('it-IT', { minimumFractionDigits: 2 })}`
        : undefined}
      key={`${fatturaId}:${pagamentoSelezionato?.id || 'fattura'}`}
      fetchUrl={pagamentoSelezionato?.view_url || `/api/fatture-ricevute/fattura/${fatturaId}/view-assoinvoice`}
      onClose={onClose}
      onDownload={pagamentoSelezionato ? undefined : scaricaFatturaOriginale}
      extraActions={pagamentoSelezionato ? (
        <button type="button" onClick={() => setPagamentoSelezionato(null)}
          aria-label="Torna alla fattura" title="Torna alla fattura"
          style={{ minHeight: 40, padding: '0 12px', border: 0, borderRadius: 8, background: 'rgba(255,255,255,0.15)', color: 'white', fontWeight: 700, cursor: 'pointer' }}>
          Fattura
        </button>
      ) : [
        ...allegati.map(allegato => (
          <button type="button" key={`allegato-${allegato.indice}`}
            data-testid={`modal-fattura-allegato-${allegato.indice}`}
            onClick={() => setPagamentoSelezionato({
              id: `allegato-${allegato.indice}`,
              nome_file: allegato.nome,
              view_url: urlOriginale({ tipo: 'allegato_fattura', id: fatturaId, indice: allegato.indice }),
              allegato: true,
            })}
            aria-label={`Vedi allegato ${allegato.nome}`} title={allegato.descrizione || allegato.nome}
            style={{ minHeight: 40, padding: '0 12px', border: 0, borderRadius: 8, background: '#c15f3c', color: 'white', fontWeight: 700, cursor: 'pointer' }}>
            {allegati.length > 1 ? `Allegato ${allegato.indice + 1}` : 'PDF del fornitore'}
          </button>
        )),
        ...documentiPagamento.map((documento, index) => (
        <button type="button" key={documento.id}
          onClick={() => setPagamentoSelezionato(documento)}
          aria-label={`Vedi pagamento ${index + 1}`} title={documento.nome_file || 'Vedi pagamento'}
          style={{ minHeight: 40, padding: '0 12px', border: 0, borderRadius: 8, background: '#2f7a4f', color: 'white', fontWeight: 700, cursor: 'pointer' }}>
          Pagamento {documentiPagamento.length > 1 ? index + 1 : ''}
        </button>
        )),
      ]}
      testIdPrefix="modal-fattura"
    />
  );
}
