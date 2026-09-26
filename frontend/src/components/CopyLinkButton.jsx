/**
 * CopyLinkButton — Copia il link corrente (con hash) negli appunti
 *
 * Uso:
 *   <CopyLinkButton />
 *   <CopyLinkButton label="Condividi vista" />
 *
 * Il pulsante appare solo quando c'è uno stato attivo nell'hash (#mese=3&stato=pagata ecc.)
 * oppure sempre se showAlways=true.
 */
import React, { useState } from 'react';

export function CopyLinkButton({ label = 'Copia Link', showAlways = false, style = {} }) {
  const [copied, setCopied] = useState(false);

  const hasHash = Boolean(window.location.hash && window.location.hash.length > 1);

  if (!showAlways && !hasHash) return null;

  const handleCopy = async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback per browser senza clipboard API
      const el = document.createElement('textarea');
      el.value = url;
      el.style.position = 'fixed';
      el.style.opacity = '0';
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      onClick={handleCopy}
      title={copied ? 'Copiato!' : `Copia: ${window.location.href}`}
      data-testid="copy-link-btn"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 12px',
        background: copied ? '#e2f0e7' : '#f2f0e9',
        color: copied ? '#2f7a4f' : '#5f5c55',
        border: `1px solid ${copied ? '#86efac' : '#d0ccbe'}`,
        borderRadius: 8,
        fontSize: 12,
        fontWeight: 600,
        cursor: 'pointer',
        transition: 'all 0.2s',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {copied ? (
        <>
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
          Copiato!
        </>
      ) : (
        <>
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
          </svg>
          {label}
        </>
      )}
    </button>
  );
}

export default CopyLinkButton;
