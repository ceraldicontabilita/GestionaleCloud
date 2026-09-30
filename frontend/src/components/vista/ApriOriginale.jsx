import React, { useState } from 'react';
import { FileText } from 'lucide-react';
import { Button } from '../ds';
import DocumentViewerModal from '../DocumentViewerModal';
import { urlOriginale } from '../../lib/vista';
import { COLORS } from '../../lib/utils';

/**
 * L'unico bottone che apre l'originale (PDF) di un documento nelle viste
 * fiscali e del personale: pezzo di frontend di DRV-04. Usa il visualizzatore
 * canonico (`DocumentViewerModal`, download autenticato via blob): mai un
 * indirizzo Drive aperto da fuori.
 *
 * `tipo` + `id` (f24, quietanza, cedolino) oppure `url` gia' pronto. Senza
 * originale il bottone non c'e': si dice «Originale non disponibile».
 * Con `children` il bottone e' il testo passato (es. l'importo versato).
 */
export default function ApriOriginale({
  tipo, id, url, titolo = 'Documento', documentType = 'documento_fiscale',
  children, variante = 'secondary', testId, style,
}) {
  const [aperto, setAperto] = useState(false);
  const indirizzo = urlOriginale({ tipo, id, url });
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
        <DocumentViewerModal
          title={titolo} fetchUrl={indirizzo} documentType={documentType}
          onClose={() => setAperto(false)}
        />
      )}
    </>
  );
}
