import React from 'react';
import { COLORS } from '../../lib/utils';

/**
 * HubTabs — le schede di un hub (Fatture, Riconciliazione, Admin, …), TUTTE
 * visibili, a capo quando non ci stanno.
 *
 * Sono schede disegnate da schede, come nell'artefatto: una riga di testo,
 * la sottolineatura su quella aperta, nessuna icona e nessun riquadro che
 * prometta «ti porto altrove». Niente menu' a tendina (nascondeva quattordici
 * sezioni su quindici) e niente «← Indietro»: con la colonna di navigazione
 * sempre in vista, «indietro dove?» non ha risposta.
 *
 * API: tabs [{ id, label }], activeId, onSelect(tab). Con una sola scheda
 * non si disegna niente.
 */
export function HubTabs({
  tabs = [], activeId, onSelect = () => {}, testIdPrefix = 'tab', style = {},
}) {
  if (tabs.length <= 1) return null;

  return (
    <div
      role="tablist"
      aria-label="Sezioni principali"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 4,
        borderBottom: `1px solid ${COLORS.border}`,
        marginBottom: 16,
        ...style,
      }}
    >
      {tabs.map(t => {
        const active = t.id === activeId;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={active}
            data-testid={`${testIdPrefix}-${t.id}`}
            onClick={() => onSelect(t)}
            style={{
              flex: '0 0 auto',
              minHeight: 44,
              padding: '10px 12px',
              marginBottom: -1,
              background: 'transparent',
              border: 'none',
              borderBottom: `2px solid ${active ? COLORS.primary : 'transparent'}`,
              color: active ? COLORS.text : COLORS.textMuted,
              fontSize: 13.5,
              fontWeight: active ? 700 : 500,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export default HubTabs;
