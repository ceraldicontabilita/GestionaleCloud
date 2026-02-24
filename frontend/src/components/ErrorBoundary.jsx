import React from 'react';

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
        <div style={{
          padding: '40px',
          textAlign: 'center',
          minHeight: '300px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px',
          backgroundColor: '#fef2f2',
          borderRadius: '12px',
          margin: '20px',
          border: '1px solid #fecaca'
        }}>
          <div style={{ fontSize: '48px' }}>⚠️</div>
          <h2 style={{ color: '#991b1b', margin: 0, fontSize: '20px' }}>
            Si è verificato un errore
          </h2>
          <p style={{ color: '#7f1d1d', maxWidth: '500px', margin: 0 }}>
            {this.props.message || 'Qualcosa è andato storto in questa sezione. Puoi provare a ricaricare.'}
          </p>
          
          {/* Mostra dettagli errore solo in development */}
          {import.meta.env.DEV && this.state.error && (
            <details style={{
              textAlign: 'left',
              maxWidth: '600px',
              width: '100%',
              padding: '12px',
              backgroundColor: '#fff',
              borderRadius: '8px',
              border: '1px solid #dce8f4',
              fontSize: '12px',
              color: '#6080a0'
            }}>
              <summary style={{ cursor: 'pointer', fontWeight: 'bold', color: '#374151' }}>
                Dettagli errore (dev)
              </summary>
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginTop: '8px' }}>
                {this.state.error.toString()}
                {this.state.errorInfo?.componentStack}
              </pre>
            </details>
          )}

          <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
            <button
              onClick={this.handleReset}
              style={{
                padding: '8px 20px',
                borderRadius: '8px',
                border: '1px solid #d1d5db',
                backgroundColor: '#fff',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#374151'
              }}
            >
              Riprova
            </button>
            <button
              onClick={this.handleReload}
              style={{
                padding: '8px 20px',
                borderRadius: '8px',
                border: 'none',
                backgroundColor: '#dc2626',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              Ricarica pagina
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
