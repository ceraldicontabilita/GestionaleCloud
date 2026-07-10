import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Delete } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const PIN_LENGTH = 6;

export default function Login() {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { loginWithPin, isAuthenticated } = useAuth();
  // Evita doppio submit se l'utente preme rapidamente l'ultima cifra due volte
  const submittingRef = useRef(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const submitPin = useCallback(
    async fullPin => {
      if (submittingRef.current) return;
      submittingRef.current = true;
      setError('');
      setLoading(true);
      try {
        await loginWithPin(fullPin);
        navigate('/', { replace: true });
      } catch (err) {
        const status = err.response?.status;
        setError(
          status === 429
            ? err.response?.data?.detail || 'Troppi tentativi, riprova tra poco'
            : 'PIN non valido'
        );
        setPin('');
      } finally {
        setLoading(false);
        submittingRef.current = false;
      }
    },
    [loginWithPin, navigate]
  );

  // Aggiunge una cifra; alla sesta parte il login automaticamente
  const pressDigit = useCallback(
    digit => {
      if (loading) return;
      setError('');
      setPin(prev => {
        if (prev.length >= PIN_LENGTH) return prev;
        const next = prev + digit;
        if (next.length === PIN_LENGTH) {
          submitPin(next);
        }
        return next;
      });
    },
    [loading, submitPin]
  );

  const pressBackspace = useCallback(() => {
    if (loading) return;
    setError('');
    setPin(prev => prev.slice(0, -1));
  }, [loading]);

  // Tastiera fisica: cifre, Backspace, Invio (per uso desktop)
  useEffect(() => {
    const handleKey = e => {
      if (/^[0-9]$/.test(e.key)) {
        pressDigit(e.key);
      } else if (e.key === 'Backspace') {
        pressBackspace();
      } else if (e.key === 'Enter' && pin.length === PIN_LENGTH) {
        submitPin(pin);
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [pressDigit, pressBackspace, submitPin, pin]);

  const keypadButtonStyle = {
    height: 56,
    fontSize: 22,
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
    color: 'var(--c-text)',
    background: 'var(--c-bg-alt)',
    border: '1px solid var(--c-border)',
    borderRadius: 'var(--radius-md)',
    cursor: loading ? 'default' : 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    userSelect: 'none',
    touchAction: 'manipulation',
    opacity: loading ? 0.5 : 1,
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--c-primary)',
      padding: 20,
    }}>
      <div style={{
        width: 380,
        maxWidth: '100%',
        background: 'var(--c-card)',
        borderRadius: 'var(--radius-xl)',
        boxShadow: 'var(--shadow-xl)',
        overflow: 'hidden',
      }}>
        {/* Navy header with CG monogram + wordmark */}
        <div style={{ background: 'var(--c-primary)', padding: '28px 28px 24px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 46, height: 46, background: 'rgba(255,255,255,0.15)',
            border: '1px solid rgba(255,255,255,0.3)', borderRadius: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 800, fontSize: 18, color: '#fff', letterSpacing: 0.5,
          }}>CG</div>
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 18 }}>Ceraldi ERP</div>
            <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>Gestionale interno · Ceraldi Group SRL</div>
          </div>
        </div>

        {/* Body: PIN access */}
        <div style={{ padding: 28 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--c-text)', marginBottom: 4 }}>Accesso rapido</div>
          <div style={{ fontSize: 12, color: 'var(--c-text-muted)', marginBottom: 16 }}>Inserisci il PIN</div>

          {error && (
            <div style={{
              fontSize: 13, color: 'var(--c-danger)', background: 'var(--c-danger-light)',
              border: '1px solid var(--c-danger)', borderRadius: 'var(--radius-sm)',
              padding: '8px 12px', marginBottom: 14,
            }} data-testid="pin-error">{error}</div>
          )}

          {/* Pallini PIN */}
          <div
            data-testid="pin-dots"
            style={{
              display: 'flex',
              justifyContent: 'center',
              gap: 14,
              padding: '10px 0 22px',
            }}
          >
            {Array.from({ length: PIN_LENGTH }).map((_, i) => (
              <span
                key={i}
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: '50%',
                  border: '1.5px solid var(--c-border)',
                  background: i < pin.length ? 'var(--c-primary)' : 'var(--c-bg-alt)',
                  transition: 'background 0.1s',
                }}
              />
            ))}
          </div>

          {/* Tastierino numerico */}
          <div
            data-testid="pin-keypad"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 10,
            }}
          >
            {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(d => (
              <button
                key={d}
                type="button"
                onClick={() => pressDigit(d)}
                disabled={loading}
                data-testid={`pin-key-${d}`}
                style={keypadButtonStyle}
              >
                {d}
              </button>
            ))}
            {/* cella vuota per allineare lo 0 al centro */}
            <span aria-hidden="true" />
            <button
              type="button"
              onClick={() => pressDigit('0')}
              disabled={loading}
              data-testid="pin-key-0"
              style={keypadButtonStyle}
            >
              0
            </button>
            <button
              type="button"
              onClick={pressBackspace}
              disabled={loading}
              aria-label="Cancella ultima cifra"
              data-testid="pin-key-backspace"
              style={{ ...keypadButtonStyle, fontSize: 18 }}
            >
              <Delete size={22} />
            </button>
          </div>

          <div style={{ textAlign: 'center', marginTop: 14, fontSize: 12, color: 'var(--c-text-muted)', minHeight: 16 }}>
            {loading ? 'Accesso…' : ' '}
          </div>

          <div style={{ textAlign: 'center', marginTop: 8, fontSize: 11, color: 'var(--c-text-subtle)' }}>
            Uso interno · Tutti i diritti riservati
          </div>
        </div>
      </div>
    </div>
  );
}
