import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ds';

export default function Login() {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { loginWithPin, isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async e => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await loginWithPin(pin);
      navigate('/', { replace: true });
    } catch (err) {
      setError('PIN non valido');
    } finally {
      setLoading(false);
    }
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
            }}>{error}</div>
          )}

          <form onSubmit={handleSubmit}>
            <input
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={e => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="••••••"
              autoFocus
              style={{
                width: '100%',
                boxSizing: 'border-box',
                padding: '14px 16px',
                fontSize: 24,
                textAlign: 'center',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--c-bg-alt)',
                color: 'var(--c-text)',
                border: '1px solid var(--c-border)',
                letterSpacing: 8,
                fontFamily: 'var(--font-mono)',
                outline: 'none',
              }}
            />

            <Button
              type="submit"
              disabled={loading || pin.length !== 6}
              iconRight={<ArrowRight size={16} />}
              style={{ width: '100%', marginTop: 18, padding: '11px 16px', fontSize: 14 }}
            >
              {loading ? 'Accesso…' : 'Entra'}
            </Button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 16, fontSize: 11, color: 'var(--c-text-subtle)' }}>
            Uso interno · Tutti i diritti riservati
          </div>
        </div>
      </div>
    </div>
  );
}
