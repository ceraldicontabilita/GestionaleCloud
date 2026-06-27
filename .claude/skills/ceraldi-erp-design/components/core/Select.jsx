import React from 'react';

/**
 * Select — menù a tendina nativo con stile coerente all'Input.
 */
export function Select({ children, style = {}, ...props }) {
  return (
    <select
      style={{
        padding: '9px 12px',
        borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--c-border)',
        fontSize: 13,
        background: 'var(--c-card)',
        color: 'var(--c-text)',
        boxSizing: 'border-box',
        outline: 'none',
        cursor: 'pointer',
        fontFamily: 'var(--font-ui)',
        ...style,
      }}
      {...props}
    >
      {children}
    </select>
  );
}

export default Select;
