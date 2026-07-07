import React, { useState, useEffect, useCallback } from 'react';
import { Download, X, Share } from 'lucide-react';
import { COLORS } from '../lib/utils';

function isStandalone() {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  );
}

function isIos() {
  const ua = window.navigator.userAgent || '';
  const isIDevice = /iPad|iPhone|iPod/.test(ua);
  const isIpadOsAsMac = ua.includes('Macintosh') && 'ontouchend' in document;
  return isIDevice || isIpadOsAsMac;
}

/**
 * Bottone "Installa app" in TopNav. Su Chrome/Edge/Android usa il prompt
 * nativo (beforeinstallprompt). Su iOS Safari, che non espone questa API,
 * mostra le istruzioni manuali per "Aggiungi a Home". Sparisce del tutto
 * se l'app è già installata (display-mode: standalone).
 */
export default function InstallAppButton() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [showIosHelp, setShowIosHelp] = useState(false);
  const [installed, setInstalled] = useState(() => isStandalone());
  const [ios] = useState(() => isIos());

  useEffect(() => {
    if (installed) return;
    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    const onInstalled = () => {
      setInstalled(true);
      setDeferredPrompt(null);
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    window.addEventListener('appinstalled', onInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, [installed]);

  const handleClick = useCallback(async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') setInstalled(true);
      setDeferredPrompt(null);
      return;
    }
    if (ios) {
      setShowIosHelp(true);
    }
  }, [deferredPrompt, ios]);

  if (installed) return null;
  // Mostra il bottone solo se abbiamo un modo reale di installare:
  // prompt nativo pronto, oppure iOS (istruzioni manuali sempre disponibili).
  if (!deferredPrompt && !ios) return null;

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        title="Installa Ceraldi ERP come app"
        aria-label="Installa Ceraldi ERP come app"
        style={{
          flexShrink: 0,
          width: 34,
          height: 34,
          borderRadius: 8,
          background: 'rgba(255,255,255,0.1)',
          border: '1px solid rgba(255,255,255,0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          color: 'rgba(255,255,255,0.85)',
        }}
      >
        <Download size={15} />
      </button>

      {showIosHelp && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setShowIosHelp(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.55)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 2000,
            padding: 16,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#fff',
              borderRadius: 10,
              maxWidth: 360,
              width: '100%',
              padding: 20,
              position: 'relative',
              boxShadow: '0 20px 50px rgba(0,0,0,0.25)',
            }}
          >
            <button
              type="button"
              onClick={() => setShowIosHelp(false)}
              aria-label="Chiudi"
              style={{
                position: 'absolute',
                top: 8,
                right: 8,
                width: 40,
                height: 40,
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: COLORS.textMuted,
              }}
            >
              <X size={18} />
            </button>
            <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 700, color: COLORS.text }}>
              Installa Ceraldi ERP
            </h3>
            <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: COLORS.text, lineHeight: 1.8 }}>
              <li>
                Tocca l'icona <Share size={13} style={{ verticalAlign: -2 }} /> <strong>Condividi</strong> nella
                barra di Safari
              </li>
              <li>Scorri e scegli <strong>"Aggiungi a Home"</strong></li>
              <li>Conferma con <strong>"Aggiungi"</strong></li>
            </ol>
          </div>
        </div>
      )}
    </>
  );
}
