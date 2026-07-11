import React from 'react';
import { useIsMobile } from '../../lib/utils';

/**
 * Barra tab condivisa dagli hub. Su mobile usa una griglia a due colonne:
 * nessun tab può allargare la pagina oltre la viewport e le etichette lunghe
 * possono andare a capo senza comprimere il contenuto.
 */
export function HubTabs({ tabs = [], activeId, onSelect = () => {}, testIdPrefix = 'tab', style = {} }) {
  const isMobile = useIsMobile();

  return (
    <div
      style={{
        display: isMobile ? 'grid' : 'flex',
        gridTemplateColumns: isMobile ? 'repeat(2, minmax(0, 1fr))' : undefined,
        gap: isMobile ? 6 : 8,
        padding: '8px 12px',
        background: 'white',
        borderBottom: '1px solid #e2e8f0',
        borderRadius: '8px 8px 0 0',
        flexWrap: isMobile ? undefined : 'wrap',
        width: '100%',
        minWidth: 0,
        marginBottom: 16,
        ...style,
      }}
    >
      {tabs.map(tab => {
        const { id, label, Icon } = tab;
        const attivo = activeId === id;

        return (
          <button
            key={id}
            type="button"
            data-testid={`${testIdPrefix}-${id}`}
            onClick={() => onSelect(tab)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              width: isMobile ? '100%' : 'auto',
              minWidth: 0,
              padding: isMobile ? '9px 7px' : '9px 13px',
              minHeight: 42,
              flex: isMobile ? undefined : '0 1 auto',
              borderRadius: 6,
              border: `1px solid ${attivo ? '#0f2744' : '#e2e8f0'}`,
              background: attivo ? '#0f2744' : '#fff',
              color: attivo ? '#fff' : '#64748b',
              fontWeight: attivo ? 700 : 500,
              fontSize: isMobile ? 11.5 : 12,
              lineHeight: 1.25,
              whiteSpace: isMobile ? 'normal' : 'nowrap',
              overflowWrap: 'anywhere',
              textAlign: 'center',
              cursor: 'pointer',
              transition: 'all 140ms ease',
              boxShadow: attivo ? '0 1px 2px rgba(15,39,68,0.12)' : 'none',
            }}
          >
            {Icon && <Icon size={14} style={{ flexShrink: 0 }} />}
            <span style={{ minWidth: 0 }}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default HubTabs;
