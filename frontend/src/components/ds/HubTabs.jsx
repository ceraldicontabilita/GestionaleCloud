import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useIsMobile } from '../../lib/utils';

/**
 * HubTabs — barra degli hub (Fatture, Riconciliazione, Admin, …): il
 * pulsante «← Indietro» e, se l'hub ha piu' sezioni, le sue schede TUTTE
 * visibili, a capo quando non ci stanno.
 *
 * Niente menu' a tendina: un <select> «Vai a sezione» nascondeva
 * quattordici sezioni su quindici e non diceva quante fossero. Da quando
 * ogni sezione sta nella colonna di navigazione a sinistra, la tendina non
 * serve piu' a raggiungerle.
 *
 * API: tabs [{ id, label, Icon }], activeId, onSelect(tab).
 */
export function HubTabs({
  tabs = [], activeId, onSelect = () => {}, testIdPrefix = 'tab', style = {},
}) {
  const isMobile = useIsMobile();
  const navigate = useNavigate();

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        background: 'white',
        borderBottom: '1px solid #e2e8f0',
        borderRadius: '8px 8px 0 0',
        marginBottom: 16,
        ...style,
      }}
    >
      <button
        type="button"
        onClick={() => navigate(-1)}
        data-testid={`${testIdPrefix}-indietro`}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: isMobile ? '8px 12px' : '9px 14px',
          minHeight: 40,
          borderRadius: 6,
          border: '1px solid #2a3329',
          background: '#2a3329',
          color: '#fff',
          fontWeight: 700,
          fontSize: isMobile ? 12.5 : 13,
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        <ArrowLeft size={16} />
        Indietro
      </button>

      {tabs.length > 1 && (
        <div
          role="tablist"
          aria-label="Sezioni principali"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 6,
            flex: 1,
          }}
        >
          {tabs.map(t => {
            const active = t.id === activeId;
            const Icon = t.Icon;
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`${testIdPrefix}-${t.id}`}
                onClick={() => onSelect(t)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  flex: '0 0 auto',
                  minHeight: 40,
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: `1px solid ${active ? '#2a3329' : '#cbd5e1'}`,
                  background: active ? '#2a3329' : '#fff',
                  color: active ? '#fff' : '#2a3329',
                  fontWeight: active ? 700 : 600,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                {Icon ? <Icon size={15} /> : null}
                {t.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default HubTabs;
