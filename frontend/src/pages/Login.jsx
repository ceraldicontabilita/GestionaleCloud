import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import PinModal from '../components/PinModal';

export default function Login() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const navigate = useNavigate();
  const { loginWithPin, verifyMfaLogin, isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) navigate('/', { replace: true });
  }, [isAuthenticated, navigate]);

  const submitPin = async pin => {
    try {
      const result = await loginWithPin(pin);
      if (result.mfa_required) {
        setMfaChallenge(result.challenge_token);
        return;
      }
      navigate('/', { replace: true });
    } catch (err) {
      const status = err.response?.status;
      throw new Error(!err.response ? 'Connessione assente — riprova'
        : [429, 503].includes(status) ? err.response?.data?.detail || 'Accesso non disponibile'
        : 'PIN non valido');
    }
  };

  const submitMfa = async event => {
    event.preventDefault();
    if (loading || mfaCode.trim().length < 6) return;
    setLoading(true);
    setError('');
    try {
      await verifyMfaLogin(mfaChallenge, mfaCode.trim());
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.response?.data?.detail || 'Codice MFA non valido');
      setMfaCode('');
    } finally {
      setLoading(false);
    }
  };

  if (mfaChallenge) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--c-primary)', padding: 20 }}>
        <div style={{ width: 420, maxWidth: '100%', background: 'var(--c-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }}>
          <div style={{ background: 'var(--c-primary)', padding: 28, color: '#fff' }}>
            <div style={{ fontWeight: 800, fontSize: 19 }}>Verifica in due passaggi</div>
            <div style={{ marginTop: 6, opacity: 0.75, fontSize: 13 }}>Impresa Semplice</div>
          </div>
          <form onSubmit={submitMfa} style={{ padding: 28 }}>
            <p style={{ color: 'var(--c-text-muted)', fontSize: 13, lineHeight: 1.5 }}>
              Inserisci il codice dell'app di autenticazione oppure un codice di recupero.
            </p>
            {error && <div data-testid="mfa-error" style={{ color: 'var(--c-danger)', background: 'var(--c-danger-light)', padding: 10, borderRadius: 8, marginBottom: 14 }}>{error}</div>}
            <input
              autoFocus
              value={mfaCode}
              onChange={event => setMfaCode(event.target.value.toUpperCase())}
              autoComplete="one-time-code"
              inputMode="text"
              placeholder="000000"
              aria-label="Codice MFA"
              data-testid="mfa-code"
              style={{ width: '100%', boxSizing: 'border-box', padding: '14px 16px', border: '1px solid var(--c-border)', borderRadius: 8, fontSize: 20, letterSpacing: 2, textAlign: 'center' }}
            />
            <button type="submit" disabled={loading || mfaCode.trim().length < 6} style={{ width: '100%', marginTop: 16, padding: 13, border: 0, borderRadius: 8, background: 'var(--c-primary)', color: '#fff', fontWeight: 800, cursor: 'pointer' }}>
              {loading ? 'Verifica...' : 'Verifica e accedi'}
            </button>
            <button type="button" onClick={() => { setMfaChallenge(''); setMfaCode(''); setError(''); }} style={{ width: '100%', marginTop: 10, padding: 10, border: 0, background: 'transparent', color: 'var(--c-text-muted)', cursor: 'pointer' }}>
              Torna al PIN
            </button>
          </form>
        </div>
      </div>
    );
  }

  return <PinModal title="Ceraldi ERP" subtitle="Inserisci il PIN di GestionaleCloud"
    color="#5b7a6b" onVerify={submitPin} />;
}
