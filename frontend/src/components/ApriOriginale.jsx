import React, { useState } from 'react';
import { FileText } from 'lucide-react';
import { Button } from './ds';
import DocumentViewerModal from './DocumentViewerModal';
import { urlOriginale } from '../lib/vista';
import { COLORS } from '../lib/utils';

/**
 * L'unico modo di aprire l'originale (PDF, XML, immagine) di un documento
 * (DRV-04): un indirizzo solo, `/api/originale`, che il server risolve dove
 * l'originale sta (record, archivio, Drive). Nessuna pagina compone da sola
 * un indirizzo di download.
 *
 * Si indica `tipo` + `id` (f24, quietanza, cedolino, fattura, documento,
 * verbale, ricevuta_pagopa, atto, estratto, bonifico, protocollo...) oppure
 * `driveId` / `sha256`, oppure `url` gia' scritto dal server. Senza chiave si
 * dice «Originale non disponibile»: mai un bottone che non apre niente.
 * Se il server non trova l'originale lo dice nel visualizzatore, con il
 * riferimento dell'errore. Con `children` il bottone porta quel testo (es.
 * l'importo versato).
 */
export default function ApriOriginale({
  tipo, id, indice, driveId, sha256, url, titolo = 'Documento', documentType = 'documento_fiscale',
  children, variante = 'secondary', testId, style,
}) {
  const [aperto, setAperto] = useState(false);
  const indirizzo = urlOriginale({ tipo, id, indice, driveId, sha256, url });
  if (!indirizzo) {
    return (
      <span style={{ fontSize: 12.5, color: COLORS.textMuted }} data-testid={testId ? `${testId}-assente` : undefined}>
        Originale non disponibile
      </span>
    );
  }
  return (
    <>
      <Button
        type="button" size="sm" variant={variante} data-testid={testId}
        style={{ minHeight: 44, ...style }} onClick={() => setAperto(true)}
        aria-label={children ? undefined : `Apri ${titolo}`}
      >
        {children || <><FileText size={14} aria-hidden="true" /> Apri originale</>}
      </Button>
      {aperto && (
        <VisoreOriginale url={indirizzo} titolo={titolo} documentType={documentType} onClose={() => setAperto(false)} />
      )}
    </>
  );
}

/**
 * Il visualizzatore dell'originale, per le pagine che hanno gia' un proprio
 * stato «documento aperto» (elenchi con tanti bottoni): stesso modale di
 * `ApriOriginale`, con «Scarica», schermo intero e messaggio d'errore leggibile.
 */
export function VisoreOriginale({ url, titolo, title, documentType = 'documento_fiscale', ...resto }) {
  return (
    <DocumentViewerModal title={title ?? titolo ?? 'Documento'} fetchUrl={url} documentType={documentType} {...resto} />
  );
}
