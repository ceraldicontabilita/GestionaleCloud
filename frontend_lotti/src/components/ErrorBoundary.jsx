import { Component } from "react";

/**
 * ErrorBoundary resiliente — gestisce errori DOM React 19
 * (removeChild, insertBefore, etc.) con auto-recovery.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, retryCount: 0 };
  }

  static getDerivedStateFromError(error) {
    // Errori DOM (removeChild/insertBefore) sono causati da
    // estensioni browser/Google Translate che modificano il DOM.
    // React 19 non riesce a riconciliare → auto-retry.
    const isDomError =
      error?.message?.includes("removeChild") ||
      error?.message?.includes("insertBefore") ||
      error?.message?.includes("not a child");

    return { hasError: true, error, isDomError };
  }

  componentDidCatch(error, info) {
    console.warn("ErrorBoundary caught:", error?.message);

    // Auto-recovery per errori DOM (max 2 tentativi)
    const isDomError =
      error?.message?.includes("removeChild") ||
      error?.message?.includes("insertBefore") ||
      error?.message?.includes("not a child");

    if (isDomError && this.state.retryCount < 2) {
      setTimeout(() => {
        this.setState(prev => ({
          hasError: false,
          error: null,
          retryCount: prev.retryCount + 1,
        }));
      }, 100);
    }
  }

  render() {
    if (this.state.hasError) {
      // Per errori DOM in fase di auto-recovery, mostra null brevemente
      if (this.state.isDomError && this.state.retryCount < 2) {
        return null;
      }

      return (
        <div className="p-8 text-center">
          <p className="text-red-600 font-bold mb-2">Errore nel componente</p>
          <p className="text-gray-500 text-sm mb-4">{this.state.error?.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null, retryCount: 0 })}
            className="px-5 py-2.5 bg-[#5b7a6b] text-white rounded-xl text-sm font-semibold hover:bg-[#4d6a5c]"
          >
            Riprova
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
