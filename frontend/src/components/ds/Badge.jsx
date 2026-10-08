import React from 'react';
import { COLORS, BORDER_RADIUS, FONT } from '../../lib/utils';

/**
 * Badge — pill di stato uppercase. Usato per stati record nelle tabelle.
 */
export function Badge({ variant = 'neutral', children, style = {}, ...props }) {
  const variants = {
    success: { background: COLORS.successLight, color: COLORS.success },
    warning: { background: COLORS.warningLight, color: COLORS.warning },
    danger: { background: COLORS.dangerLight, color: COLORS.danger },
    info: { background: COLORS.infoLight, color: COLORS.info },
    primary: { background: COLORS.primarySoft, color: COLORS.primary },
    accent: { background: COLORS.accentSoft, color: COLORS.accent },
    neutral: { background: COLORS.gray[100], color: COLORS.gray[700] },
  };

  return (
    <span
      style={{
        display: 'inline-block',
        padding: '3px 9px',
        borderRadius: BORDER_RADIUS.full,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.2px',
        textTransform: 'uppercase',
        lineHeight: 1.4,
        fontFamily: FONT.family,
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
