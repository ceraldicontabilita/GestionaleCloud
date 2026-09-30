import React from 'react';
import { LEGENDA } from '../../lib/legendaRegole';
import { COLORS, FONT } from '../../lib/utils';

/**
 * Legenda delle regole in pagina: chiusa di default, in italiano semplice.
 * `gruppo` sceglie il capitolo di `lib/legendaRegole.js` (f24, tributi,
 * cedolini, protocollo). Sempre nel documento (un <details>): i termini si
 * cercano anche con la ricerca del browser.
 */
export default function LegendaRegole({ gruppo }) {
  const legenda = LEGENDA[gruppo];
  if (!legenda) return null;
  return (
    <details
      data-testid={`legenda-${gruppo}`}
      style={{
        marginTop: 16, background: COLORS.card, border: `1px solid ${COLORS.border}`,
        borderRadius: 12, padding: '4px 14px', fontFamily: FONT.family,
      }}
    >
      <summary style={{ minHeight: 44, display: 'flex', alignItems: 'center', cursor: 'pointer', fontWeight: 700, fontSize: 14 }}>
        {legenda.titolo}
      </summary>
      <dl style={{ margin: '0 0 10px', display: 'grid', gap: 8 }}>
        {legenda.voci.map(([termine, spiegazione]) => (
          <div key={termine} style={{ fontSize: 13, lineHeight: 1.5 }}>
            <dt style={{ fontWeight: 700, display: 'inline' }}>{termine}: </dt>
            <dd style={{ display: 'inline', margin: 0, color: COLORS.textMuted }}>{spiegazione}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
