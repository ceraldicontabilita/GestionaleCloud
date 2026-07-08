import React, { useState } from 'react';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../../lib/utils';

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
  onMouseEnter,
  onMouseLeave,
  ...props
}) {
  const [hoverRaw, setHover] = useState(false);
  const hover = hoverRaw && !disabled;

  const sizes = {
    sm: { padding: '6px 12px', fontSize: 12 },
    md: { padding: '8px 16px', fontSize: 13 },
    lg: { padding: '10px 20px', fontSize: 14 },
  };

  const variants = {
    primary: {
      background: hover ? COLORS.primaryLight : COLORS.primary,
      color: '#fff',
      borderColor: hover ? COLORS.primaryLight : COLORS.primary,
      boxShadow: hover ? SHADOWS.sm : 'none',
    },
    secondary: {
      background: hover ? COLORS.bgAlt : COLORS.card,
      color: COLORS.text,
      borderColor: COLORS.border,
    },
    ghost: {
      background: hover ? COLORS.bgAlt : 'transparent',
      color: COLORS.textMuted,
      borderColor: 'transparent',
    },
    outline: {
      background: hover ? COLORS.primarySoft : 'transparent',
      color: COLORS.primary,
      borderColor: COLORS.primary,
    },
    success: { background: COLORS.success, color: '#fff', borderColor: COLORS.success },
    danger: { background: COLORS.danger, color: '#fff', borderColor: COLORS.danger },
    info: { background: COLORS.info, color: '#fff', borderColor: COLORS.info },
    warning: { background: COLORS.warning, color: '#fff', borderColor: COLORS.warning },
  };

  return (
    <button
      disabled={disabled}
      onMouseEnter={e => {
        setHover(true);
        onMouseEnter?.(e);
      }}
      onMouseLeave={e => {
        setHover(false);
        onMouseLeave?.(e);
      }}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 7,
        borderRadius: BORDER_RADIUS.sm,
        border: '1px solid transparent',
        fontWeight: 600,
        lineHeight: 1.2,
        whiteSpace: 'nowrap',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
        fontFamily: FONT.family,
        transition: 'background 140ms ease, border-color 140ms ease, color 140ms ease, box-shadow 140ms ease',
        ...sizes[size],
        ...(variants[variant] || variants.primary),
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
