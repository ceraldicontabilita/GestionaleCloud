import React from 'react';

/**
 * PageLoader — spinner di caricamento pagina UNICO del design system.
 * Prima ogni hub (Dashboard, Fatture, Contabilità, Riconciliazione, …)
 * definiva il proprio loader quasi identico, alcuni reiniettando anche
 * i @keyframes: un solo componente, una sola animazione.
 */
export function PageLoader({ label = 'Caricamento...' }) {
  return (
    <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
      <div
        style={{
          width: 32,
          height: 32,
          border: '3px solid #e2e8f0',
          borderTop: '3px solid #0f2744',
          borderRadius: '50%',
          animation: 'ds-page-loader-spin 1s linear infinite',
          margin: '0 auto 12px',
        }}
      />
      <style>{`@keyframes ds-page-loader-spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
      {label}
    </div>
  );
}

export default PageLoader;
