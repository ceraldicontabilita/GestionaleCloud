import React from 'react';

/**
 * Badge — pill di stato uppercase. Usato per stati record nelle tabelle.
 */
export function Badge({ variant = 'neutral', children, style = {}, ...props }) {
  const variants = {
    success: { background: 'var(--c-success-light)', color: 'var(--c-success)' },
    warning: { background: 'var(--c-warning-light)', color: 'var(--c-warning)' },
    danger:  { background: 'var(--c-danger-light)', color: 'var(--c-danger)' },
    info:    { background: 'var(--c-info-light)', color: 'var(--c-info)' },
    primary: { background: 'var(--c-primary-soft)', color: 'var(--c-primary)' },
    accent:  { background: 'var(--c-accent-soft)', color: 'var(--c-accent)' },
    neutral: { background: 'var(--gray-100)', color: 'var(--gray-700)' },
  };

  return (
    <span
      style={{
        display: 'inline-block',
        padding: '3px 9px',
        borderRadius: 'var(--radius-full)',
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.2px',
        textTransform: 'uppercase',
        lineHeight: 1.4,
        fontFamily: 'var(--font-ui)',
        ...(variants[variant] || variants.neutral),
        ...style,
      }}
      {...props}
    >
      {children}
    </span>
  );
}

export default Badge;
