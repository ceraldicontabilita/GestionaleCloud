import React from 'react';
import { COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { Button } from './ds/Button';

const STALE_CHUNK_PATTERNS = [
  /failed to fetch dynamically imported module/i,
  /importing a module script failed/i,
  /chunkloaderror/i,
  /loading chunk [\w-]+ failed/i,
  /css_chunk_load_failed/i,
];

export function isStaleChunkError(error) {
  const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error || '');
  return STALE_CHUNK_PATTERNS.some((pattern) => pattern.test(message));
}

/**
 * ErrorBoundary - Cattura errori nei componenti figli e mostra una UI di
 * ripiego. Se il browser ha ancora un vecchio chunk dopo un deploy, esegue
 * una sola ricarica automatica per percorso, evitando cicli infiniti.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null, staleChunk: false };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error, staleChunk: isStaleChunkError(error) };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('ErrorBoundary caught:', error, errorInfo);

    if (!isStaleChunkError(error) || typeof window === 'undefined') return;

    const key = `gestionale:chunk-reload:${window.location.pathname}`;
    try {
      const ultimoTentativo = Number(window.sessionStorage.getItem(key) || 0);
      if (Date.now() - ultimoTentativo > 60_000) {
        window.sessionStorage.setItem(key, String(Date.now()));
        window.location.reload();
      }
    } catch {
      // Storage non disponibile: la UI di ripiego resta utilizzabile.
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null, staleChunk: false });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          data-testid="error-boundary"
          style={{
            padding: 40,
            textAlign: 'center',
            minHeight: 300,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
            backgroundColor: COLORS.dangerLight,
            borderRadius: BORDER_RADIUS.lg,
            margin: 20,
            border: `1px solid ${COLORS.danger}`,
            fontFamily: FONT.family,
          }}
        >
          <div style={{ fontSize: 48 }}>⚠️</div>
          <h2 style={{ color: COLORS.danger, margin: 0, fontSize: 20 }}>
            Si è verificato un errore
          </h2>
          <p style={{ color: COLORS.text, maxWidth: 500, margin: 0 }}>
            {this.state.staleChunk
              ? 'È disponibile una versione aggiornata. Ricarica la pagina per continuare.'
              : this.props.message ||
                'Qualcosa è andato storto in questa sezione. Puoi provare a ricaricare.'}
          </p>

          {import.meta.env.DEV && this.state.error && (
            <details
              style={{
                textAlign: 'left',
                maxWidth: 600,
                width: '100%',
                padding: 12,
                backgroundColor: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                fontSize: 12,
                color: COLORS.textMuted,
              }}
            >
              <summary style={{ cursor: 'pointer', fontWeight: 'bold', color: COLORS.gray[700] }}>
                Dettagli errore (dev)
              </summary>
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginTop: 8 }}>
                {this.state.error.toString()}
                {this.state.errorInfo?.componentStack}
              </pre>
            </details>
          )}

          <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
            <Button variant="secondary" onClick={this.handleReset}>
              Riprova
            </Button>
            <Button variant="danger" onClick={this.handleReload}>
              Ricarica pagina
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
