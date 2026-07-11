import React from 'react';
import { useIsMobile } from '../../lib/utils';

/**
 * HubTabs — barra tab standard degli hub (Fatture, Prima Nota,
 * Riconciliazione, Contabilità, Admin, Dashboard, Integrazioni).
 * Stessa grafica ovunque: tab attivo navy #0f2744 pieno, inattivo bianco
 * con bordo. Su mobile i bottoni si allargano a riempire la riga
 * (flex: 1) con padding e font leggermente ridotti: 3 tab stanno su una
 * riga sola e con più tab le righe si riempiono in modo uniforme invece
 * di andare a capo in modo irregolare.
 *
 * tabs: [{ id, label, Icon }] — onSelect riceve l'intero oggetto tab.
 */
export function HubTabs({ tabs = [], activeId, onSelect = () => {}, testIdPrefix = 'tab', style = {} }) {
  const isMobile = useIsMobile();

  // Su telefono, oltre 6 tab diventano una muraglia di bottoni su 4-5 righe
  // (es. Contabilità: 13 voci) che spinge il contenuto fuori schermo:
  // meglio un menù a tendina nativo, una riga sola.
  if (isMobile && tabs.length > 6) {
    return (
      <div
        style={{
          padding: '8px 12px',
          background: 'white',
          borderBottom: '1px solid #e2e8f0',
          borderRadius: '8px 8px 0 0',
          marginBottom: 16,
          ...style,
        }}
      >
        <select
          value={activeId}
          onChange={e => {
            const tab = tabs.find(t => t.id === e.target.value);
            if (tab) onSelect(tab);
          }}
          data-testid={`${testIdPrefix}-select`}
          style={{
            width: '100%',
            minHeight: 40,
            padding: '8px 10px',
            borderRadius: 6,
            border: '1px solid #0f2744',
            background: '#0f2744',
            color: '#fff',
            fontWeight: 700,
            fontSize: 13,
          }}
        >
          {tabs.map(t => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        gap: isMobile ? 6 : 8,
        padding: '8px 12px',
        background: 'white',
        borderBottom: '1px solid #e2e8f0',
        borderRadius: '8px 8px 0 0',
        flexWrap: 'wrap',
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
            data-testid={`${testIdPrefix}-${id}`}
            onClick={() => onSelect(tab)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              padding: isMobile ? '8px 8px' : '9px 13px',
              minHeight: 40,
              flex: isMobile ? '1 1 auto' : '0 1 auto',
              borderRadius: 6,
              border: `1px solid ${attivo ? '#0f2744' : '#e2e8f0'}`,
              background: attivo ? '#0f2744' : '#fff',
              color: attivo ? '#fff' : '#64748b',
              fontWeight: attivo ? 700 : 500,
              fontSize: isMobile ? 11.5 : 12,
              whiteSpace: 'nowrap',
              cursor: 'pointer',
              transition: 'all 140ms ease',
              boxShadow: attivo ? '0 1px 2px rgba(15,39,68,0.12)' : 'none',
            }}
          >
            {Icon && <Icon size={14} />}
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default HubTabs;
