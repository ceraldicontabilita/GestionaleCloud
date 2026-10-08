import React from 'react';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../../lib/utils';

/**
 * Tabs — barra di tab a pillola. Tab attivo navy pieno.
 * items: [{ key, label, icon? }]
 */
export function Tabs({ items = [], value, onChange = () => {}, style = {} }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', ...style }}>
      {items.map((it) => {
        const active = it.key === value;
        return (
          <button
            key={it.key}
            onClick={() => onChange(it.key)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 14px',
              borderRadius: BORDER_RADIUS.sm,
              border: `1px solid ${active ? COLORS.primary : COLORS.border}`,
              fontWeight: active ? 700 : 500,
              fontSize: 12.5,
              cursor: 'pointer',
              background: active ? COLORS.primary : COLORS.card,
              color: active ? '#fff' : COLORS.textMuted,
              boxShadow: active ? SHADOWS.sm : 'none',
              whiteSpace: 'nowrap',
              fontFamily: FONT.family,
              transition: 'all 140ms ease',
            }}
          >
            {it.icon}
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;
