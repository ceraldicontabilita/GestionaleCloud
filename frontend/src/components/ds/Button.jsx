import React from 'react';

/**
 * Button — bottone primario del Ceraldi ERP.
 * Variante navy piena (primary), neutra (secondary), ghost e colori di stato.
 */
export function Button({
  variant = 'primary',
  size = 'md',
  disabled = false,
  iconLeft = null,
  iconRight = null,
  children,
  style = {},
  ...props
}) {
  const sizes = {
    sm: { padding: '6px 12px', fontSize: 12 },
    md: { padding: '8px 16px', fontSize: 13 },
    lg: { padding: '10px 20px', fontSize: 14 },
  };

  const variants = {
    primary:   { background: 'var(--c-primary)', color: '#fff', borderColor: 'var(--c-primary)' },
    secondary: { background: 'var(--c-card)', color: 'var(--c-text)', borderColor: 'var(--c-border)' },
    ghost:     { background: 'transparent', color: 'var(--c-text-muted)', borderColor: 'transparent' },
    outline:   { background: 'transparent', color: 'var(--c-primary)', borderColor: 'var(--c-primary)' },
    success:   { background: 'var(--c-success)', color: '#fff', borderColor: 'var(--c-success)' },
    danger:    { background: 'var(--c-danger)', color: '#fff', borderColor: 'var(--c-danger)' },
    info:      { background: 'var(--c-info)', color: '#fff', borderColor: 'var(--c-info)' },
    warning:   { background: 'var(--c-warning)', color: '#fff', borderColor: 'var(--c-warning)' },
  };

  return (
    <button
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 7,
        borderRadius: 'var(--radius-sm)',
        border: '1px solid transparent',
        fontWeight: 600,
        lineHeight: 1.2,
        whiteSpace: 'nowrap',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
        fontFamily: 'var(--font-ui)',
        transition: 'background var(--t-fast), border-color var(--t-fast), color var(--t-fast), box-shadow var(--t-fast)',
        ...sizes[size],
        ...variants[variant],
        ...style,
      }}
      {...props}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}

export default Button;
