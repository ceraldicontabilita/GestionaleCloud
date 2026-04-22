/**
 * PageLayout - Componente wrapper SEMPLIFICATO
 * Renderizza solo il contenuto senza titoli/header duplicati
 * I titoli sono già gestiti dalla TopNav e SecondaryTabs
 */

import React from 'react';

export function PageLayout({ children, noPadding = false, className = '' }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#f8fafc',
        padding: noPadding ? 0 : '8px 16px',
      }}
      className={className}
    >
      {children}
    </div>
  );
}

// Componenti helper per composizione
export function PageSection({ title, icon, children, className = '', style = {} }) {
  return (
    <div
      style={{
        background: '#fff',
        borderRadius: 12,
        border: '1px solid #e2e8f0',
        padding: 20,
        marginBottom: 16,
        ...style,
      }}
      className={className}
    >
      {title && (
        <h3
          style={{
            margin: '0 0 16px 0',
            fontSize: 16,
            fontWeight: 600,
            color: '#1e3a5f',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          {icon && <span>{icon}</span>}
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}

export function PageGrid({ cols = 2, gap = 20, children }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gap,
      }}
    >
      {children}
    </div>
  );
}

export function PageEmpty({ icon = '📭', message = 'Nessun dato disponibile' }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '60px 20px',
        color: '#64748b',
      }}
    >
      <div style={{ fontSize: 48, marginBottom: 16 }}>{icon}</div>
      <p style={{ margin: 0, fontSize: 15 }}>{message}</p>
    </div>
  );
}

export function PageLoading({ message = 'Caricamento...' }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '60px 20px',
        color: '#64748b',
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          border: '3px solid #e2e8f0',
          borderTop: '3px solid #2563eb',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
          margin: '0 auto 16px',
        }}
      />
      <p style={{ margin: 0, fontSize: 14 }}>{message}</p>
    </div>
  );
}

export function PageError({ message = 'Si è verificato un errore', onRetry }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '40px 20px',
        background: '#fef2f2',
        borderRadius: 12,
        border: '1px solid #fca5a5',
        color: '#dc2626',
      }}
    >
      <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
      <p style={{ margin: '0 0 16px 0', fontSize: 14 }}>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: '8px 16px',
            background: '#dc2626',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          Riprova
        </button>
      )}
    </div>
  );
}

export default PageLayout;
