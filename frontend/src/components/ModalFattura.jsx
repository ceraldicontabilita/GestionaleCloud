import React, { useEffect } from 'react';

/**
 * Modale in-page per visualizzare una fattura (view-assoinvoice) in un iframe,
 * senza aprire nuove schede del browser.
 *
 * Props:
 *  - fatturaId: id della fattura da visualizzare
 *  - numero:    numero fattura (per il titolo, opzionale)
 *  - onClose:   callback di chiusura
 */
export default function ModalFattura({ fatturaId, numero, onClose }) {
  // Chiudi con tasto ESC
  useEffect(() => {
    const handleKey = e => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  if (!fatturaId) return null;

  return (
    <div
      onClick={onClose}
      data-testid="modal-fattura-overlay"
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
          maxWidth: 960,
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
            📄 Fattura {numero || fatturaId}
          </h2>
          <button
            onClick={onClose}
            aria-label="Chiudi"
            data-testid="modal-fattura-close"
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

        <iframe
          title={`Fattura ${numero || fatturaId}`}
          src={`/api/fatture-ricevute/fattura/${fatturaId}/view-assoinvoice`}
          style={{ flex: 1, width: '100%', border: 'none', background: '#f8fafc' }}
        />
      </div>
    </div>
  );
}
