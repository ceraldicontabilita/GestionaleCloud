import React from 'react';

/**
 * StatCard / KPICard — riquadro statistica con icona, label e valore.
 * Bordo sinistro accentato opzionale (accent prop).
 */
export function StatCard({
  icon = null,
  label,
  value,
  subtext = null,
  accent = 'primary',
  onClick = null,
  style = {},
}) {
  const accents = {
    primary: 'var(--c-primary)',
    success: 'var(--c-success)',
    warning: 'var(--c-warning)',
    danger:  'var(--c-danger)',
    info:    'var(--c-info)',
    accent:  'var(--c-accent)',
    none:    'transparent',
  };
  const accentColor = accents[accent] || accents.primary;

  return (
    <div
      onClick={onClick || undefined}
      style={{
        background: 'var(--c-card)',
        border: '1px solid var(--c-border)',
        borderLeft: accent === 'none' ? '1px solid var(--c-border)' : `3px solid ${accentColor}`,
        borderRadius: 'var(--radius-md)',
        padding: '16px 18px',
        boxShadow: 'var(--shadow-sm)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow var(--t-normal), transform var(--t-normal)',
        minWidth: 0,
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {icon && <span style={{ color: accentColor === 'transparent' ? 'var(--c-text-muted)' : accentColor, display: 'inline-flex' }}>{icon}</span>}
        <span style={{
          fontSize: 11, color: 'var(--c-text-muted)', fontWeight: 600,
          textTransform: 'uppercase', letterSpacing: '0.4px',
        }}>{label}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--c-primary)', lineHeight: 1.2, fontFamily: 'var(--font-ui)' }}>
        {value}
      </div>
      {subtext && (
        <div style={{ fontSize: 11, color: 'var(--c-text-subtle)', marginTop: 6 }}>{subtext}</div>
      )}
    </div>
  );
}

export default StatCard;
