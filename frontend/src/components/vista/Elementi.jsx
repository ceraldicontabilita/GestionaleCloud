import React from 'react';
import { COLORS, FONT } from '../../lib/utils';
import { NON_DISPONIBILE } from '../../lib/vista';

/** Coppia etichetta/valore delle schede. Valore mancante = «Dato non disponibile». */
export function Campo({ etichetta, children, mono = false, testId }) {
  const manca = children === null || children === undefined || children === '';
  return (
    <div style={{ minWidth: 0 }} data-testid={testId}>
      <dt style={{ fontSize: 11.5, fontWeight: 700, color: COLORS.textMuted, letterSpacing: '0.02em' }}>{etichetta}</dt>
      <dd style={{
        margin: '2px 0 0', fontSize: 14, overflowWrap: 'anywhere',
        color: manca ? COLORS.textMuted : COLORS.text,
        ...(mono ? { fontFamily: FONT.mono, fontVariantNumeric: 'tabular-nums' } : {}),
      }}>
        {manca ? NON_DISPONIBILE : children}
      </dd>
    </div>
  );
}

export function GrigliaCampi({ children }) {
  return (
    <dl style={{ margin: 0, display: 'grid', gap: '12px 20px', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
      {children}
    </dl>
  );
}

export function Riquadro({ titolo, children, testId, style }) {
  return (
    <section data-testid={testId} style={{
      background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12,
      padding: '14px 16px', marginTop: 14, ...style,
    }}>
      {titolo && <h2 style={{ margin: '0 0 10px', fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em' }}>{titolo}</h2>}
      {children}
    </section>
  );
}

/** Stato vuoto o errore, sempre con parole e mai un riquadro muto. */
export function Messaggio({ tono = 'neutro', children, testId }) {
  const colore = tono === 'errore' ? COLORS.danger : COLORS.textMuted;
  return (
    <div role={tono === 'errore' ? 'alert' : 'status'} data-testid={testId} style={{
      padding: 24, textAlign: 'center', color: colore, background: COLORS.card,
      border: `1px solid ${COLORS.border}`, borderRadius: 12, marginTop: 14, fontSize: 14,
    }}>
      {children}
    </div>
  );
}

export const paginaStile = { maxWidth: 1280, margin: '0 auto', fontFamily: FONT.family };
