import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api';

export default function Register() {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    name: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  const handleChange = e => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError('');
  };

  const handleSubmit = async e => {
    e.preventDefault();
    setError('');

    // Validazione
    if (!formData.email || !formData.password || !formData.name) {
      setError('Tutti i campi sono obbligatori');
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setError('Le password non coincidono');
      return;
    }

    if (formData.password.length < 8) {
      setError('La password deve essere di almeno 8 caratteri');
      return;
    }

    setLoading(true);

    try {
      await api.post('/api/auth/register', {
        email: formData.email,
        password: formData.password,
        name: formData.name,
      });

      setSuccess(true);
      setTimeout(() => {
        navigate('/login');
      }, 2000);
    } catch (err) {
      const msg =
        err.response?.data?.message ||
        err.response?.data?.detail ||
        'Errore durante la registrazione';
      setError(typeof msg === 'string' ? msg : 'Errore durante la registrazione');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0f2744',
        padding: '20px',
      }}
    >
      <div
        style={{
          display: 'flex',
          width: '100%',
          maxWidth: 900,
          gap: 60,
          alignItems: 'center',
        }}
      >
        {/* Left side - Branding */}
        <div
          style={{ flex: 1, display: 'none', '@media (min-width: 768px)': { display: 'block' } }}
          className="hidden md:block"
        >
          <h1 style={{ fontSize: 42, fontWeight: 700, color: '#f8fafc', marginBottom: 8 }}>
            Ceraldi<span style={{ color: '#3b82f6' }}>.</span>
          </h1>
          <p style={{ color: '#94a3b8', fontSize: 18, marginBottom: 32 }}>
            Impresa Semplice Online
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[
              { icon: '📊', text: 'Dashboard operativa in tempo reale' },
              { icon: '🏦', text: 'Prima nota, corrispettivi, riconciliazione' },
              { icon: '👥', text: 'Gestione dipendenti e cedolini' },
              { icon: '📋', text: 'F24, IVA, scadenze fiscali' },
            ].map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 20 }}>{item.icon}</span>
                <span style={{ color: '#cbd5e1', fontSize: 14 }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right side - Registration Form */}
        <div
          style={{
            flex: 1,
            maxWidth: 400,
            background: 'rgba(30, 41, 59, 0.5)',
            backdropFilter: 'blur(10px)',
            borderRadius: 16,
            padding: 32,
            border: '1px solid rgba(148, 163, 184, 0.1)',
          }}
        >
          <h2 style={{ color: '#f8fafc', fontSize: 24, fontWeight: 600, marginBottom: 8 }}>
            Registrati
          </h2>
          <p style={{ color: '#94a3b8', fontSize: 14, marginBottom: 24 }}>
            Crea il tuo account per accedere al gestionale
          </p>

          {success ? (
            <div
              style={{
                background: 'rgba(34, 197, 94, 0.1)',
                border: '1px solid rgba(34, 197, 94, 0.3)',
                borderRadius: 8,
                padding: 16,
                color: '#22c55e',
                textAlign: 'center',
              }}
            >
              ✅ Registrazione completata! Reindirizzamento al login...
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              {error && (
                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    borderRadius: 8,
                    padding: 12,
                    marginBottom: 16,
                    color: '#ef4444',
                    fontSize: 14,
                  }}
                >
                  ⚠️ {error}
                </div>
              )}

              <div style={{ marginBottom: 16 }}>
                <label
                  style={{ display: 'block', color: '#94a3b8', fontSize: 13, marginBottom: 6 }}
                >
                  Nome completo
                </label>
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  placeholder="Mario Rossi"
                  data-testid="register-name-input"
                  style={{
                    width: '100%',
                    padding: '12px 14px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: 8,
                    color: '#f8fafc',
                    fontSize: 15,
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label
                  style={{ display: 'block', color: '#94a3b8', fontSize: 13, marginBottom: 6 }}
                >
                  Email
                </label>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="nome@azienda.it"
                  data-testid="register-email-input"
                  style={{
                    width: '100%',
                    padding: '12px 14px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: 8,
                    color: '#f8fafc',
                    fontSize: 15,
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label
                  style={{ display: 'block', color: '#94a3b8', fontSize: 13, marginBottom: 6 }}
                >
                  Password
                </label>
                <input
                  type="password"
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  placeholder="Minimo 8 caratteri"
                  data-testid="register-password-input"
                  style={{
                    width: '100%',
                    padding: '12px 14px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: 8,
                    color: '#f8fafc',
                    fontSize: 15,
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ marginBottom: 24 }}>
                <label
                  style={{ display: 'block', color: '#94a3b8', fontSize: 13, marginBottom: 6 }}
                >
                  Conferma Password
                </label>
                <input
                  type="password"
                  name="confirmPassword"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  placeholder="Ripeti la password"
                  data-testid="register-confirm-password-input"
                  style={{
                    width: '100%',
                    padding: '12px 14px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: 8,
                    color: '#f8fafc',
                    fontSize: 15,
                    outline: 'none',
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                data-testid="register-submit-btn"
                style={{
                  width: '100%',
                  padding: '14px',
                  background: loading ? '#1e40af' : '#3b82f6',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  fontSize: 15,
                  fontWeight: 600,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  transition: 'all 0.2s',
                  opacity: loading ? 0.7 : 1,
                  marginBottom: 16,
                }}
              >
                {loading ? '⏳ Registrazione in corso...' : 'Registrati'}
              </button>

              <p style={{ textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>
                Hai già un account?{' '}
                <Link
                  to="/login"
                  style={{ color: '#3b82f6', textDecoration: 'none' }}
                  data-testid="goto-login-link"
                >
                  Accedi
                </Link>
              </p>
            </form>
          )}

          <p
            style={{
              textAlign: 'center',
              color: '#64748b',
              fontSize: 11,
              marginTop: 24,
            }}
          >
            Impresasempliceonline © 2026 Ceraldi Group
          </p>
        </div>
      </div>
    </div>
  );
}
