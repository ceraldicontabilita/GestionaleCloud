import React from 'react';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../../lib/utils';

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
    primary: COLORS.primary,
    success: COLORS.success,
    warning: COLORS.warning,
    danger: COLORS.danger,
    info: COLORS.info,
    accent: COLORS.accent,
    none: 'transparent',
  };
  const accentColor = accents[accent] || accents.primary;

  return (
    <div
      onClick={onClick || undefined}
      style={{
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderLeft: accent === 'none' ? `1px solid ${COLORS.border}` : `3px solid ${accentColor}`,
        borderRadius: BORDER_RADIUS.md,
        padding: '16px 18px',
        boxShadow: SHADOWS.sm,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow 160ms ease, transform 160ms ease',
        minWidth: 0,
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {icon && <span style={{ color: accentColor === 'transparent' ? COLORS.textMuted : accentColor, display: 'inline-flex' }}>{icon}</span>}
        <span style={{
          fontSize: 11, color: COLORS.textMuted, fontWeight: 600,
          textTransform: 'uppercase', letterSpacing: '0.4px',
        }}>{label}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: COLORS.primary, lineHeight: 1.2, fontFamily: FONT.family }}>
        {value}
      </div>
      {subtext && (
        <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 6 }}>{subtext}</div>
      )}
    </div>
  );
}

export default StatCard;
