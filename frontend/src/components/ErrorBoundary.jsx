import React from 'react';
import { COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { Button } from './ds/Button';

/**
 * ErrorBoundary - Cattura errori nei componenti figli e mostra fallback UI.
 * Previene che un crash in una pagina renda tutta l'app bianca.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    // Log per debug
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      // Fallback UI personalizzata
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
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
            {this.props.message ||
              'Qualcosa è andato storto in questa sezione. Puoi provare a ricaricare.'}
          </p>

          {/* Mostra dettagli errore solo in development */}
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
