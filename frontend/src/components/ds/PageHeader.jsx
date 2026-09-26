import React from 'react';
import { Pencil } from 'lucide-react';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../../lib/utils';

/**
 * PageHeader — l'unica testata di pagina dell'ERP (anche PageLayout passa da qui).
 *
 * Tre parti, dal documento di design del titolare (23/09):
 * 1. `title`: cosa stai guardando; sopra, se passata, la `famiglia` della
 *    pagina (lo stesso gruppo e lo stesso punto colorato della colonna di
 *    navigazione);
 * 2. `subtitle`: una riga sola sul PERCHÉ la pagina esiste, in parole
 *    semplici;
 * 3. `pastiglie`: da due a quattro numeri che rispondono alla domanda che ha
 *    portato qui, ognuno con l'etichetta sopra e una riga di contesto sotto.
 *    Il `tono` dice il giudizio: 'ok' (verificato, chiuso), 'attenzione' (da
 *    verificare), 'male' (serve un intervento), 'neutro' (nessun giudizio, il
 *    default). Il colore non è mai l'unica informazione: l'etichetta c'è sempre.
 *
 * I numeri li calcola la pagina: la testata li mostra e basta.
 */
const TONI = {
  ok: COLORS.success,
  attenzione: COLORS.warning,
  male: COLORS.danger,
  neutro: COLORS.text,
};

function Pastiglia({ etichetta, valore, nota, tono = 'neutro', azione }) {
  const colore = TONI[tono] || TONI.neutro;
  return (
    <div
      data-testid="pastiglia"
      data-tono={tono}
      style={{
        minWidth: 0,
        padding: '10px 14px',
        background: COLORS.bgAlt,
        border: `1px solid ${COLORS.border}`,
        borderTop: `3px solid ${tono === 'neutro' ? COLORS.border : colore}`,
        borderRadius: BORDER_RADIUS.md,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: COLORS.textMuted, letterSpacing: '0.02em' }}>
          {etichetta}
        </span>
        {azione && (
          <button
            type="button"
            onClick={azione.onClick}
            data-testid={azione.testId}
            aria-label={azione.etichetta}
            title={azione.etichetta}
            style={{
              width: 44, height: 44, margin: '-10px -10px -10px 0', flexShrink: 0,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              background: 'transparent', border: 'none', borderRadius: BORDER_RADIUS.sm,
              color: COLORS.primaryLight, cursor: 'pointer',
            }}
          >
            <Pencil size={16} />
          </button>
        )}
      </div>
      <div
        style={{
          marginTop: 2, fontSize: 18, fontWeight: 800, color: colore,
          fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}
      >
        {valore ?? '—'}
      </div>
      {nota && <div style={{ marginTop: 2, fontSize: 11.5, color: COLORS.textMuted }}>{nota}</div>}
    </div>
  );
}

export function PageHeader({
  title, subtitle = null, icon = null, actions = null, style = {},
  famiglia = null, pastiglie = null,
}) {
  const conPastiglie = Array.isArray(pastiglie) && pastiglie.length > 0;
  return (
    <div
      data-testid="testata-pagina"
      style={{
        padding: '16px 20px',
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderLeft: `4px solid ${famiglia?.colore || COLORS.primary}`,
        borderRadius: BORDER_RADIUS.md,
        boxShadow: SHADOWS.sm,
        ...style,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          {famiglia && (
            <div
              data-testid="testata-famiglia"
              style={{
                display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2,
                fontSize: 10.5, fontWeight: 800, letterSpacing: '0.06em', color: COLORS.textMuted,
              }}
            >
              <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: '50%', background: famiglia.colore }} />
              {famiglia.titolo}
            </div>
          )}
          <h1 style={{
            margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text,
            letterSpacing: '-0.3px', display: 'flex', alignItems: 'center', gap: 10,
            fontFamily: FONT.family,
          }}>
            {icon}{title}
          </h1>
          {subtitle && (
            <p style={{ margin: '2px 0 0 0', fontSize: 13, color: COLORS.textMuted, fontWeight: 500 }}>
              {subtitle}
            </p>
          )}
        </div>
        {actions && <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>{actions}</div>}
      </div>
      {conPastiglie && (
        <div
          style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
            gap: 10, marginTop: 14,
          }}
        >
          {pastiglie.map(p => <Pastiglia key={p.etichetta} {...p} />)}
        </div>
      )}
    </div>
  );
}

export default PageHeader;
