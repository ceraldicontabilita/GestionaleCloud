import React, { useState } from 'react';
import { COLORS, BORDER_RADIUS, FONT } from '../../lib/utils';

/**
 * Input — campo testo standard. Supporta stato di errore e icona a sinistra.
 */
export function Input({ error = false, iconLeft = null, style = {}, onFocus, onBlur, ...props }) {
  const [focused, setFocused] = useState(false);

  const base = {
    padding: iconLeft ? '9px 12px 9px 34px' : '9px 12px',
    borderRadius: BORDER_RADIUS.sm,
    border: `1px solid ${error ? COLORS.danger : COLORS.border}`,
    fontSize: 13,
    width: '100%',
    boxSizing: 'border-box',
    background: COLORS.card,
    color: COLORS.text,
    outline: 'none',
    fontFamily: FONT.family,
    transition: 'border-color 140ms ease, box-shadow 140ms ease',
    ...(focused && !error
      ? { borderColor: COLORS.primaryLight, boxShadow: '0 0 0 3px rgba(30,58,95,0.12)' }
      : {}),
    ...style,
  };

  const handlers = {
    onFocus: e => {
      setFocused(true);
      onFocus?.(e);
    },
    onBlur: e => {
      setFocused(false);
      onBlur?.(e);
    },
  };

  if (!iconLeft) return <input style={base} {...handlers} {...props} />;

  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: '100%', alignItems: 'center' }}>
      <span style={{ position: 'absolute', left: 11, display: 'inline-flex', color: COLORS.textSubtle, pointerEvents: 'none' }}>
        {iconLeft}
      </span>
      <input style={base} {...handlers} {...props} />
    </span>
  );
}

export default Input;
