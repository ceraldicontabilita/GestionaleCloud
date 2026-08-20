import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import api from '../api';

/**
 * Componente CANONICO "Vedi Documento" (PROMPT_DEFINITIVO §8.2): modale in-page per
 * visualizzare QUALSIASI documento (fattura elettronica HTML/ASSO, fattura PDF,
 * cedolino, F24, quietanza, estratto conto, documento fiscale, allegato email,
 * verbale, ricevuta PagoPA, PDF generico) senza aprire nuove schede del browser.
 *
 * Funzioni §8.2: Chiudi · Scarica · Schermo intero · Zoom +/− · Adatta larghezza ·
 * Adatta pagina · scroll interno · touch/pinch · blocco scroll body · focus trap ·
 * ESC · aria-label · ritorno focus al pulsante origine.
 * Nota: per i PDF lo zoom/pagina/pinch è gestito anche dal viewer PDF nativo del
 * browser dentro l'iframe; lo zoom CSS qui è utile soprattutto per i documenti HTML.
 *
 * Props:
 *  - title:        titolo header (es. "📄 Fattura 123")
 *  - subtitle:     riga secondaria opzionale
 *  - documentType: tipo logico (fattura_html|fattura_pdf|cedolino|f24|quietanza|
 *                  estratto_conto|documento_fiscale|allegato_email|verbale|pagopa|pdf)
 *  - src:          URL diretto per l'iframe (già pronto)
 *  - fetchUrl:     in alternativa a src: URL scaricato via API come blob (endpoint
 *                  autenticati non inseribili direttamente in iframe)
 *  - mimeType:     tipo del blob per fetchUrl (default application/pdf)
 *  - onClose:      callback di chiusura
 *  - onDownload:   se presente mostra "📥 Scarica"
 *  - maxWidth:     larghezza massima del modale (default 960)
 *  - testIdPrefix: prefisso data-testid (default "document-viewer")
 */
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.25;

export default function DocumentViewerModal({
  title,
  subtitle,
  documentType = 'pdf',
  src,
  fetchUrl,
  mimeType = 'application/pdf',
  onClose,
  onDownload,
  extraActions,
  pageNumber = 1,
  maxWidth = 960,
  testIdPrefix = 'document-viewer',
}) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState('width'); // 'width' | 'page' | null
  const cardRef = useRef(null);
  const scrollRef = useRef(null);
  const iframeRef = useRef(null);
  const originRef = useRef(null);

  const zoomIn = useCallback(() => { setFit(null); setZoom(z => Math.min(ZOOM_MAX, z + ZOOM_STEP)); }, []);
  const zoomOut = useCallback(() => { setFit(null); setZoom(z => Math.max(ZOOM_MIN, z - ZOOM_STEP)); }, []);
  const fitWidth = useCallback(() => { setFit('width'); setZoom(1); }, []);
  const fitPage = useCallback(() => { setFit('page'); setZoom(1); }, []);

  // 🖨️ Stampa (richiesta utente 18/07/2026: "non posso neanche stamparla"):
  // stampa il contenuto dell'iframe; se il browser lo impedisce apre il
  // documento in una scheda nuova, da cui si stampa col menu del browser.
  const stampa = useCallback(() => {
    try {
      const w = iframeRef.current?.contentWindow;
      if (w) {
        w.focus();
        w.print();
        return;
      }
    } catch (e) {
      /* cross-origin o viewer PDF: fallback sotto */
    }
    const url = src || blobUrl;
    if (url) window.open(url, '_blank', 'noopener');
  }, [src, blobUrl]);


  // Ricorda il pulsante di origine e ripristina il focus alla chiusura (§8.2).
  useEffect(() => {
    originRef.current = document.activeElement;
    // focus iniziale sul contenitore modale
    const t = setTimeout(() => cardRef.current?.focus(), 0);
    return () => {
      clearTimeout(t);
      if (originRef.current && typeof originRef.current.focus === 'function') {
        originRef.current.focus();
      }
    };
  }, []);

  // ESC per chiudere + focus trap (Tab resta dentro il modale).
  useEffect(() => {
    const handleKey = e => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key === 'Tab') {
        const focusables = cardRef.current?.querySelectorAll(
          'button, [href], input, select, textarea, iframe, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  // Blocca lo scroll del body mentre il viewer è aperto (§8.2); ripristina alla chiusura.
  useEffect(() => {
    const precedente = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = precedente;
    };
  }, []);

  const apriSchermoIntero = () => {
    const el = cardRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen?.();
    else (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
  };

  // Modalità blob: scarica il documento via API e revoca l'URL alla chiusura.
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

  const baseIframeSrc = src || blobUrl;
  const iframeSrc = baseIframeSrc && pageNumber > 1
    ? `${baseIframeSrc.split('#')[0]}#page=${pageNumber}`
    : baseIframeSrc;

  const btn = extra => ({
    width: 40,
    height: 40,
    flexShrink: 0,
    background: 'rgba(255,255,255,0.15)',
    border: 'none',
    borderRadius: 8,
    color: 'white',
    fontSize: 16,
    lineHeight: 1,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    ...extra,
  });

  // Stile dell'iframe: in fit-width riempie la larghezza; con zoom applica una
  // scala CSS e lascia lo scroll interno al contenitore (§8.2 "scroll interno").
  const iframeStyle =
    fit === 'width'
      ? { width: '100%', height: '100%', border: 'none', background: '#f8fafc' }
      : fit === 'page'
        ? { width: '100%', height: '100%', border: 'none', background: '#f8fafc', objectFit: 'contain' }
        : {
            width: `${100 / zoom}%`,
            height: `${100 / zoom}%`,
            transform: `scale(${zoom})`,
            transformOrigin: 'top left',
            border: 'none',
            background: '#f8fafc',
          };

  return createPortal(
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
        // Deve stare sopra anche ai modali contenitori (es. Estratto
        // Fatture fornitori, z-index 10000). Il portal evita inoltre gli
        // stacking context creati dai pannelli della pagina.
        zIndex: 20000,
        padding: 12,
      }}
    >
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-label={title || 'Documento'}
        data-document-type={documentType}
        tabIndex={-1}
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
          outline: 'none',
        }}
      >
        {/* Header: titolo + toolbar (zoom/fit/fullscreen/download/chiudi) */}
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
          <div style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {extraActions}
            <button onClick={zoomOut} aria-label="Riduci zoom" title="Zoom −"
              data-testid={`${testIdPrefix}-zoom-out`} style={btn({ fontSize: 20 })}>−</button>
            <button onClick={zoomIn} aria-label="Aumenta zoom" title="Zoom +"
              data-testid={`${testIdPrefix}-zoom-in`} style={btn({ fontSize: 20 })}>+</button>
            <button onClick={fitWidth} aria-label="Adatta alla larghezza" title="Adatta larghezza"
              data-testid={`${testIdPrefix}-fit-width`}
              style={btn({ width: 'auto', padding: '0 10px', fontSize: 16, opacity: fit === 'width' ? 1 : 0.7 })}>↔</button>
            <button onClick={fitPage} aria-label="Adatta alla pagina" title="Adatta pagina"
              data-testid={`${testIdPrefix}-fit-page`}
              style={btn({ width: 'auto', padding: '0 10px', fontSize: 16, opacity: fit === 'page' ? 1 : 0.7 })}>⤢</button>
            <button onClick={apriSchermoIntero} aria-label="Schermo intero" title="Schermo intero"
              data-testid={`${testIdPrefix}-fullscreen`} style={btn({ fontSize: 18 })}>⛶</button>
            <button onClick={stampa} aria-label="Stampa documento" title="Stampa"
              data-testid={`${testIdPrefix}-print`}
              style={btn({ width: 'auto', padding: '0 12px', fontSize: 13, gap: 6 })}>🖨️ Stampa</button>
            {onDownload && (
              <button onClick={onDownload} aria-label="Scarica documento" title="Scarica"
                data-testid={`${testIdPrefix}-download`}
                style={btn({ width: 'auto', padding: '0 12px', fontSize: 13, gap: 6 })}>📥 Scarica</button>
            )}
            <button onClick={onClose} aria-label="Chiudi" title="Chiudi"
              data-testid={`${testIdPrefix}-close`} style={btn({ fontSize: 20 })}>✕</button>
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
          <div
            ref={scrollRef}
            style={{
              flex: 1,
              overflow: 'auto',
              WebkitOverflowScrolling: 'touch',
              touchAction: 'pinch-zoom',
              background: '#f8fafc',
            }}
          >
            <iframe
              ref={iframeRef} title={title || 'Documento'} src={iframeSrc} style={iframeStyle} />
          </div>
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
    </div>,
    document.body,
  );
}
