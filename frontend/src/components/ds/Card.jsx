import React from 'react';
import { COLORS, SHADOWS, BORDER_RADIUS } from '../../lib/utils';

/**
 * Card — contenitore base bianco con bordo e ombra leggera.
 * Con `title` mostra un'intestazione separata da bordo.
 */
export function Card({ title, icon = null, actions = null, children, style = {}, bodyStyle = {} }) {
  return (
    <div
      style={{
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: BORDER_RADIUS.md,
        boxShadow: SHADOWS.sm,
        overflow: 'hidden',
        ...style,
      }}
    >
      {title && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          gap: 12, padding: '12px 16px', borderBottom: `1px solid ${COLORS.border}`,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            fontSize: 14, fontWeight: 700, color: COLORS.primary,
          }}>
            {icon}{title}
          </div>
          {actions}
        </div>
      )}
      <div style={{ padding: 20, ...bodyStyle }}>{children}</div>
    </div>
  );
}

export default Card;
