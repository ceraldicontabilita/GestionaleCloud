import React from 'react';
import { COLORS, BORDER_RADIUS, FONT } from '../../lib/utils';

/**
 * Table / Th / Td — tabella dati standard del Ceraldi ERP: intestazione
 * uppercase su sfondo slate, celle 13px, separatori 1px, colonne numeriche
 * allineate a destra con font mono (usare `mono`/`align="right"` su <Td>).
 * `TableWrap` fornisce lo scroll orizzontale su schermi stretti.
 */
export function TableWrap({ children, style = {} }) {
  return (
    <div
      style={{
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        width: '100%',
        borderRadius: BORDER_RADIUS.md,
        border: `1px solid ${COLORS.border}`,
        background: COLORS.card,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function Table({ children, style = {} }) {
  return (
    <table
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: 13,
        background: COLORS.card,
        fontFamily: FONT.family,
        ...style,
      }}
    >
      {children}
    </table>
  );
}

export function Th({ children, align = 'left', style = {}, ...props }) {
  return (
    <th
      style={{
        padding: '10px 14px',
        textAlign: align,
        fontWeight: 700,
        fontSize: 12,
        textTransform: 'uppercase',
        letterSpacing: '0.4px',
        color: COLORS.textMuted,
        background: COLORS.bgAlt,
        borderBottom: `1px solid ${COLORS.border}`,
        whiteSpace: 'nowrap',
        ...style,
      }}
      {...props}
    >
      {children}
    </th>
  );
}

export function Td({ children, align = 'left', mono = false, style = {}, ...props }) {
  return (
    <td
      style={{
        padding: '10px 14px',
        borderBottom: `1px solid ${COLORS.gray[100]}`,
        color: COLORS.text,
        fontSize: 13,
        verticalAlign: 'middle',
        textAlign: align,
        fontFamily: mono ? FONT.mono : undefined,
        ...style,
      }}
      {...props}
    >
      {children}
    </td>
  );
}

/** Coppia di bottoni icon-only (occhio/cestino ecc.) a fine riga, stile chip tinta. */
export function RowActions({ children, style = {} }) {
  return (
    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', ...style }}>
      {children}
    </div>
  );
}

export function RowActionButton({ variant = 'neutral', children, style = {}, ...props }) {
  const variants = {
    neutral: { background: COLORS.gray[100], color: COLORS.textMuted },
    primary: { background: COLORS.primarySoft, color: COLORS.primary },
    info: { background: COLORS.infoLight, color: COLORS.info },
    danger: { background: COLORS.dangerLight, color: COLORS.danger },
    success: { background: COLORS.successLight, color: COLORS.success },
  };
  return (
    <button
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 28,
        height: 28,
        borderRadius: BORDER_RADIUS.sm,
        border: 'none',
        cursor: 'pointer',
        transition: 'background 140ms ease',
        ...(variants[variant] || variants.neutral),
        ...style,
      }}
      {...props}
    >
      {children}
    </button>
  );
}

export default Table;
