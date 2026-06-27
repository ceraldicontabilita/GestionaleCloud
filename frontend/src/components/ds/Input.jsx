import React from 'react';

/**
 * Input — campo testo standard. Supporta stato di errore e icona a sinistra.
 */
export function Input({ error = false, iconLeft = null, style = {}, ...props }) {
  const base = {
    padding: iconLeft ? '9px 12px 9px 34px' : '9px 12px',
    borderRadius: 'var(--radius-sm)',
    border: `1px solid ${error ? 'var(--c-danger)' : 'var(--c-border)'}`,
    fontSize: 13,
    width: '100%',
    boxSizing: 'border-box',
    background: 'var(--c-card)',
    color: 'var(--c-text)',
    outline: 'none',
    fontFamily: 'var(--font-ui)',
    transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
    ...style,
  };

  if (!iconLeft) return <input style={base} {...props} />;

  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: '100%', alignItems: 'center' }}>
      <span style={{ position: 'absolute', left: 11, display: 'inline-flex', color: 'var(--c-text-subtle)', pointerEvents: 'none' }}>
        {iconLeft}
      </span>
      <input style={base} {...props} />
    </span>
  );
}

export default Input;
