import React from 'react';
import { COLORS, BORDER_RADIUS, FONT } from '../../lib/utils';

/**
 * Select — menù a tendina nativo con stile coerente all'Input.
 */
export function Select({ children, style = {}, ...props }) {
  return (
    <select
      style={{
        padding: '9px 12px',
        borderRadius: BORDER_RADIUS.sm,
        border: `1px solid ${COLORS.border}`,
        fontSize: 13,
        background: COLORS.card,
        color: COLORS.text,
        boxSizing: 'border-box',
        outline: 'none',
        cursor: 'pointer',
        fontFamily: FONT.family,
        ...style,
      }}
      {...props}
    >
      {children}
    </select>
  );
}

export default Select;
