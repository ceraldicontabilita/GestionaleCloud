/**
 * PageLayout - Wrapper di pagina con header opzionale (title/icon/subtitle/actions),
 * renderizzato tramite il design system (ds/PageHeader).
 */

import React from 'react';
import { PageHeader } from './ds/PageHeader';
import { COLORS, SPACING, BORDER_RADIUS, FONT } from '../lib/utils';

export function PageLayout({
  children,
  title,
  icon,
  subtitle,
  actions,
  noPadding = false,
  className = '',
}) {
  return (
    <div
      className={`ds-page-layout ${className}`}
      style={{
        minHeight: '100vh',
        background: COLORS.bgAlt,
        ...(noPadding ? { padding: 0 } : {}),
      }}
    >
      {title && (
        <div style={{ marginBottom: SPACING.lg }}>
          <PageHeader title={title} icon={icon} subtitle={subtitle} actions={actions} />
        </div>
      )}
      {children}
    </div>
  );
}

// Componenti helper per composizione
export function PageSection({ title, icon, children, className = '', style = {} }) {
  return (
    <div
      style={{
        position: 'relative',
        background: COLORS.card,
        borderRadius: BORDER_RADIUS.lg,
        border: `1px solid ${COLORS.border}`,
        padding: SPACING.xl,
        marginBottom: SPACING.lg,
        ...style,
      }}
      className={className}
    >
      {title && (
        <h3
          style={{
            margin: `0 0 ${SPACING.lg}px 0`,
            fontSize: 16,
            fontWeight: 600,
            color: COLORS.primaryLight,
            display: 'flex',
            alignItems: 'center',
            gap: SPACING.sm,
            fontFamily: FONT.family,
          }}
        >
          {icon && <span>{icon}</span>}
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}

export function PageGrid({ cols = 2, gap = 20, minWidth, children }) {
  // auto-fit + minmax invece di repeat(cols, 1fr): su schermi stretti le colonne
  // si riducono finché serve invece di forzare N colonne e scroll orizzontale.
  // minWidth è derivato da cols quando non specificato esplicitamente.
  const mw = minWidth || Math.max(140, Math.floor(960 / cols) - gap);
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fit, minmax(min(${mw}px, 100%), 1fr))`,
        gap,
      }}
    >
      {React.Children.map(children, child => (
        <div style={{ minWidth: 0 }}>{child}</div>
      ))}
    </div>
  );
}

export function PageEmpty({ icon = '□', message = 'Nessun dato disponibile' }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '60px 20px',
        color: COLORS.textMuted,
        fontFamily: FONT.family,
      }}
    >
      <div style={{ fontSize: 48, marginBottom: SPACING.lg }}>{icon}</div>
      <p style={{ margin: 0, fontSize: 15 }}>{message}</p>
    </div>
  );
}

export function PageLoading({ message = 'Caricamento...' }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '60px 20px',
        color: COLORS.textMuted,
        fontFamily: FONT.family,
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          border: `3px solid ${COLORS.border}`,
          borderTop: `3px solid ${COLORS.primary}`,
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
          margin: '0 auto 16px',
        }}
      />
      <p style={{ margin: 0, fontSize: 14 }}>{message}</p>
    </div>
  );
}

export function PageError({ message = 'Si è verificato un errore', onRetry }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '40px 20px',
        background: COLORS.dangerLight,
        borderRadius: BORDER_RADIUS.lg,
        border: `1px solid ${COLORS.danger}`,
        color: COLORS.danger,
        fontFamily: FONT.family,
      }}
    >
      <div style={{ fontSize: 32, marginBottom: SPACING.md }}>!</div>
      <p style={{ margin: `0 0 ${SPACING.lg}px 0`, fontSize: 14 }}>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: '8px 16px',
            background: COLORS.danger,
            color: '#fff',
            border: 'none',
            borderRadius: BORDER_RADIUS.sm,
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: FONT.family,
          }}
        >
          Riprova
        </button>
      )}
    </div>
  );
}

export default PageLayout;
