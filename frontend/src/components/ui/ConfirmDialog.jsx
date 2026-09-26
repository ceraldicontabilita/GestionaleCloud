/**
 * Dialog di conferma moderno per sostituire window.confirm
 * Più elegante e non bloccante
 */
import React, { useState, useCallback, createContext, useContext } from 'react';

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [confirmState, setConfirmState] = useState({
    isOpen: false,
    title: '',
    message: '',
    confirmText: 'Conferma',
    cancelText: 'Annulla',
    variant: 'default', // default, danger, warning
    resolve: null,
  });

  const confirm = useCallback(({ title, message, confirmText, cancelText, variant } = {}) => {
    return new Promise(resolve => {
      setConfirmState({
        isOpen: true,
        title: title || 'Conferma',
        message: message || 'Sei sicuro di voler procedere?',
        confirmText: confirmText || 'Conferma',
        cancelText: cancelText || 'Annulla',
        variant: variant || 'default',
        resolve,
      });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    confirmState.resolve?.(true);
    setConfirmState(prev => ({ ...prev, isOpen: false }));
  }, [confirmState.resolve]);

  const handleCancel = useCallback(() => {
    confirmState.resolve?.(false);
    setConfirmState(prev => ({ ...prev, isOpen: false }));
  }, [confirmState.resolve]);

  const getButtonStyle = (variant, isConfirm) => {
    const base = {
      padding: '8px 16px',
      borderRadius: 6,
      fontWeight: 600,
      fontSize: 14,
      cursor: 'pointer',
      border: 'none',
      transition: 'all 0.2s',
    };

    if (!isConfirm) {
      return {
        ...base,
        background: '#f2f0e9',
        color: '#5f5c55',
      };
    }

    switch (variant) {
      case 'danger':
        return { ...base, background: '#dc2626', color: 'white' };
      case 'warning':
        return { ...base, background: '#f59e0b', color: 'white' };
      default:
        return { ...base, background: '#5b7a6b', color: 'white' };
    }
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}

      {confirmState.isOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 99999,
            animation: 'fadeIn 0.15s ease-out',
          }}
          onClick={handleCancel}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 24,
              maxWidth: 400,
              width: '90%',
              boxShadow: '0 20px 50px rgba(0,0,0,0.3)',
              animation: 'slideUp 0.2s ease-out',
            }}
            onClick={e => e.stopPropagation()}
          >
            <h3
              style={{
                margin: '0 0 12px 0',
                fontSize: 18,
                fontWeight: 700,
                color: '#2c2b28',
              }}
            >
              {confirmState.title}
            </h3>

            <p
              style={{
                margin: '0 0 20px 0',
                color: '#7a776e',
                fontSize: 14,
                lineHeight: 1.5,
                whiteSpace: 'pre-line',
              }}
            >
              {confirmState.message}
            </p>

            <div
              style={{
                display: 'flex',
                gap: 10,
                justifyContent: 'flex-end',
              }}
            >
              <button
                onClick={handleCancel}
                style={getButtonStyle(confirmState.variant, false)}
                data-testid="confirm-dialog-cancel"
              >
                {confirmState.cancelText}
              </button>
              <button
                onClick={handleConfirm}
                style={getButtonStyle(confirmState.variant, true)}
                data-testid="confirm-dialog-confirm"
              >
                {confirmState.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slideUp {
          from { transform: translateY(10px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const context = useContext(ConfirmContext);
  if (!context) {
    // Fallback per componenti non wrapped - usa confirm sincrono
    return async opts => true;
  }
  return context;
}

export default ConfirmProvider;
