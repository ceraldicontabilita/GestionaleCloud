import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuth();

  // Redirect se già autenticato
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      navigate('/', { replace: true });
    } catch (err) {
      const msg = err.response?.data?.message || err.response?.data?.detail || 'Credenziali non valide';
      setError(typeof msg === 'string' ? msg : 'Errore di autenticazione');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
    }}>
      {/* Pannello sinistro - Brand */}
      <div style={{
        flex: '0 0 45%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '60px',
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'radial-gradient(ellipse at 30% 50%, rgba(59,130,246,0.08) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />
        
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{
            fontSize: 48,
            fontWeight: 800,
            color: '#f8fafc',
            letterSpacing: '-1px',
            lineHeight: 1.1,
            marginBottom: 16,
          }}>
            Ceraldi<span style={{ color: '#1535a8' }}>.</span>
          </div>
          <div style={{
            fontSize: 22,
            color: '#94a3b8',
            fontWeight: 300,
            marginBottom: 40,
            lineHeight: 1.5,
          }}>
            Impresa Semplice Online
          </div>
          
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}>
            {[
              { icon: '📊', text: 'Dashboard operativa in tempo reale' },
              { icon: '🏦', text: 'Prima nota, corrispettivi, riconciliazione' },
              { icon: '👥', text: 'Gestione dipendenti e cedolini' },
              { icon: '📋', text: 'F24, IVA, scadenze fiscali' },
            ].map((item, i) => (
              <div key={i} style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                color: '#cbd5e1',
                fontSize: 15,
              }}>
                <span style={{ fontSize: 20 }}>{item.icon}</span>
                {item.text}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Pannello destro - Login form */}
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 40,
      }}>
        <div style={{
          width: '100%',
          maxWidth: 400,
          background: '#1e293b',
          borderRadius: 16,
          padding: '48px 40px',
          border: '1px solid rgba(148,163,184,0.1)',
          boxShadow: '0 25px 50px rgba(0,0,0,0.4)',
        }}>
          <h2 style={{
            color: '#f8fafc',
            fontSize: 24,
            fontWeight: 700,
            marginBottom: 8,
            marginTop: 0,
          }}>
            Accedi
          </h2>
          <p style={{
            color: '#64748b',
            fontSize: 14,
            marginBottom: 32,
            marginTop: 0,
          }}>
            Inserisci le credenziali per accedere al gestionale
          </p>

          {error && (
            <div style={{
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 8,
              padding: '12px 16px',
              marginBottom: 24,
              color: '#fca5a5',
              fontSize: 14,
            }}>
              ⚠️ {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 20 }}>
              <label style={{
                display: 'block',
                color: '#94a3b8',
                fontSize: 13,
                fontWeight: 500,
                marginBottom: 8,
              }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                placeholder="admin@ceraldi.it"
                style={{
                  width: '100%',
                  padding: '12px 16px',
                  background: '#0f172a',
                  border: '1px solid rgba(148,163,184,0.2)',
                  borderRadius: 8,
                  color: '#f8fafc',
                  fontSize: 15,
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                }}
                onFocus={(e) => e.target.style.borderColor = '#1535a8'}
                onBlur={(e) => e.target.style.borderColor = 'rgba(148,163,184,0.2)'}
              />
            </div>

            <div style={{ marginBottom: 32 }}>
              <label style={{
                display: 'block',
                color: '#94a3b8',
                fontSize: 13,
                fontWeight: 500,
                marginBottom: 8,
              }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                style={{
                  width: '100%',
                  padding: '12px 16px',
                  background: '#0f172a',
                  border: '1px solid rgba(148,163,184,0.2)',
                  borderRadius: 8,
                  color: '#f8fafc',
                  fontSize: 15,
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                }}
                onFocus={(e) => e.target.style.borderColor = '#1535a8'}
                onBlur={(e) => e.target.style.borderColor = 'rgba(148,163,184,0.2)'}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-btn"
              style={{
                width: '100%',
                padding: '14px',
                background: loading ? '#1535a8' : '#1535a8',
                color: '#fff',
                border: 'none',
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                opacity: loading ? 0.7 : 1,
              }}
              onMouseEnter={(e) => { if (!loading) e.target.style.background = '#1535a8'; }}
              onMouseLeave={(e) => { if (!loading) e.target.style.background = '#1535a8'; }}
            >
              {loading ? '⏳ Accesso in corso...' : 'Accedi →'}
            </button>
          </form>

          {/* Divider */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            margin: '24px 0',
            gap: 12,
          }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(148,163,184,0.2)' }} />
            <span style={{ color: '#64748b', fontSize: 12 }}>oppure</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(148,163,184,0.2)' }} />
          </div>

          {/* Google Login Button */}
          {/* REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH */}
          <button
            type="button"
            data-testid="google-login-btn"
            onClick={() => {
              const redirectUrl = window.location.origin + '/';
              window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
            }}
            style={{
              width: '100%',
              padding: '14px',
              background: '#fff',
              color: '#1f2937',
              border: '1px solid rgba(148,163,184,0.3)',
              borderRadius: 8,
              fontSize: 15,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
            }}
            onMouseEnter={(e) => { e.target.style.background = '#f8fafc'; }}
            onMouseLeave={(e) => { e.target.style.background = '#fff'; }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continua con Google
          </button>

          {/* Link alla registrazione */}
          <p style={{ 
            textAlign: 'center', 
            color: '#94a3b8', 
            fontSize: 14,
            marginTop: 20,
          }}>
            Non hai un account?{' '}
            <Link 
              to="/register" 
              style={{ color: '#1535a8', textDecoration: 'none', fontWeight: 500 }}
              data-testid="goto-register-link"
            >
              Registrati
            </Link>
          </p>

          <div style={{
            marginTop: 32,
            paddingTop: 20,
            borderTop: '1px solid rgba(148,163,184,0.1)',
            textAlign: 'center',
            color: '#475569',
            fontSize: 12,
          }}>
            Impresasempliceonline © {new Date().getFullYear()} Ceraldi Group
          </div>
        </div>
      </div>

      {/* Responsive: nasconde pannello sinistro su mobile */}
      <style>{`
        @media (max-width: 768px) {
          div:first-child > div:first-child {
            display: none !important;
          }
        }
      `}</style>
    </div>
  );
}
