import React from 'react';

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
              borderRadius: 'var(--radius-sm)',
              border: `1px solid ${active ? 'var(--c-primary)' : 'var(--c-border)'}`,
              fontWeight: active ? 700 : 500,
              fontSize: 12.5,
              cursor: 'pointer',
              background: active ? 'var(--c-primary)' : 'var(--c-card)',
              color: active ? '#fff' : 'var(--c-text-muted)',
              boxShadow: active ? 'var(--shadow-sm)' : 'none',
              whiteSpace: 'nowrap',
              fontFamily: 'var(--font-ui)',
              transition: 'all var(--t-fast)',
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
