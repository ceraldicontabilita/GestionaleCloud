import React from 'react';

/**
 * PageHeader — intestazione pagina con bordo-accento navy a sinistra,
 * titolo, sottotitolo e zona azioni a destra.
 */
export function PageHeader({ title, subtitle = null, icon = null, actions = null, style = {} }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
        padding: '16px 20px',
        background: 'var(--c-card)',
        border: '1px solid var(--c-border)',
        borderLeft: '4px solid var(--c-primary)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-sm)',
        ...style,
      }}
    >
      <div>
        <h1 style={{
          margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--c-primary)',
          letterSpacing: '-0.3px', display: 'flex', alignItems: 'center', gap: 10,
          fontFamily: 'var(--font-ui)',
        }}>
          {icon}{title}
        </h1>
        {subtitle && (
          <p style={{ margin: '2px 0 0 0', fontSize: 13, color: 'var(--c-text-muted)', fontWeight: 500 }}>
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>{actions}</div>}
    </div>
  );
}

export default PageHeader;
