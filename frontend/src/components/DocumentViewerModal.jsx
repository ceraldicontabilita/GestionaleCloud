import React, { useEffect, useState } from 'react';
import api from '../api';

/**
 * Motore condiviso "Vedi Documento": modale in-page per visualizzare
 * qualsiasi documento (fattura AssoInvoice, PDF generico, F24, cedolino,
 * estratto conto, verbale...) senza aprire nuove schede del browser.
 *
 * Prima di questo componente esistevano due implementazioni scollegate:
 * ModalFattura.jsx (solo fatture, riusato in 7 pagine) e un modale inline
 * duplicato dentro Documenti.jsx (documenti generici). Lo stile visivo è
 * quello di ModalFattura, già standard nelle pagine esistenti.
 *
 * Props:
 *  - title:        titolo mostrato nel header (es. "📄 Fattura 123")
 *  - subtitle:     riga secondaria opzionale sotto il titolo
 *  - src:          URL diretto da caricare nell'iframe (già pronto)
 *  - fetchUrl:     in alternativa a src: URL da scaricare via API come blob
 *                  (per endpoint autenticati che non si possono mettere
 *                  direttamente in un iframe); gestisce loading, errore e
 *                  revoca dell'object URL alla chiusura
 *  - mimeType:     tipo del blob per fetchUrl (default application/pdf)
 *  - onClose:      callback di chiusura
 *  - onDownload:   se presente, mostra il bottone "📥 Scarica" nel header
 *  - maxWidth:     larghezza massima del modale (default 960)
 *  - testIdPrefix: prefisso per i data-testid (default "document-viewer")
 */
export default function DocumentViewerModal({
  title,
  subtitle,
  src,
  fetchUrl,
  mimeType = 'application/pdf',
  onClose,
  onDownload,
  maxWidth = 960,
  testIdPrefix = 'document-viewer',
}) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [loadError, setLoadError] = useState(null);

  // Chiudi con tasto ESC
  useEffect(() => {
    const handleKey = e => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  // Modalità blob: scarica il documento via API e revoca l'URL alla chiusura
  useEffect(() => {
    if (!fetchUrl) return undefined;
    let revoked = false;
    let url = null;
    setLoadError(null);
    api
      .get(fetchUrl, { responseType: 'blob' })
      .then(response => {
        if (revoked) return;
        url = window.URL.createObjectURL(new Blob([response.data], { type: mimeType }));
        setBlobUrl(url);
      })
      .catch(error => {
        if (revoked) return;
        const status = error.response?.status;
        setLoadError(
          status === 502 || status === 504
            ? 'Il documento è troppo grande o il servizio è momentaneamente non disponibile. Riprova tra qualche istante.'
            : `Errore visualizzazione documento: ${error.message}`
        );
      });
    return () => {
      revoked = true;
      if (url) window.URL.revokeObjectURL(url);
    };
  }, [fetchUrl, mimeType]);

  const iframeSrc = src || blobUrl;

  return (
    <div
      onClick={onClose}
      data-testid={`${testIdPrefix}-overlay`}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,39,68,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 2000,
        padding: 12,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'white',
          borderRadius: 12,
          width: '100%',
          maxWidth,
          height: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.35)',
        }}
      >
        {/* Header con titolo e X di chiusura ben tappabile */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            padding: '8px 8px 8px 16px',
            background: '#0f2744',
            color: 'white',
            flexShrink: 0,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <h2
              style={{
                margin: 0,
                fontSize: 15,
                fontWeight: 700,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {title}
            </h2>
            {subtitle && (
              <div
                style={{
                  fontSize: 12,
                  opacity: 0.75,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {subtitle}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
            {onDownload && (
              <button
                onClick={onDownload}
                data-testid={`${testIdPrefix}-download`}
                style={{
                  height: 40,
                  padding: '0 12px',
                  background: 'rgba(255,255,255,0.15)',
                  border: 'none',
                  borderRadius: 8,
                  color: 'white',
                  fontSize: 13,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                📥 Scarica
              </button>
            )}
            <button
              onClick={onClose}
              aria-label="Chiudi"
              data-testid={`${testIdPrefix}-close`}
              style={{
                width: 40,
                height: 40,
                flexShrink: 0,
                background: 'rgba(255,255,255,0.15)',
                border: 'none',
                borderRadius: 8,
                color: 'white',
                fontSize: 20,
                lineHeight: 1,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {loadError ? (
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 24,
              textAlign: 'center',
              color: '#64748b',
              background: '#f8fafc',
            }}
          >
            {loadError}
          </div>
        ) : iframeSrc ? (
          <iframe
            title={title}
            src={iframeSrc}
            style={{ flex: 1, width: '100%', border: 'none', background: '#f8fafc' }}
          />
        ) : (
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#64748b',
              background: '#f8fafc',
            }}
          >
            Caricamento documento…
          </div>
        )}
      </div>
    </div>
  );
}
