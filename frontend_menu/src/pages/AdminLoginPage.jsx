import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../hooks/use-toast';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const AdminLoginPage = () => {
  const [pin, setPin] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!pin) return;
    setLoading(true);

    try {
      const response = await axios.post(`${BACKEND_URL}/api/qrcode/login`, { pin });

      if (response.data.success) {
        localStorage.setItem('admin_token', response.data.token);
        toast({
          title: 'Accesso effettuato',
          description: 'Benvenuto nel pannello di amministrazione'
        });
        navigate('/admin');
      } else {
        setPin('');
        toast({
          title: 'Accesso non riuscito',
          description: response.data.message || 'PIN non valido',
          variant: 'destructive'
        });
      }
    } catch (error) {
      setPin('');
      const detail = error?.response?.data?.detail;
      toast({
        title: 'Errore',
        description: detail || 'Accesso non riuscito. Riprova.',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    width: '100%',
    boxSizing: 'border-box',
    padding: '15px 14px',
    borderRadius: 12,
    border: '1.5px solid #e6e0d4',
    background: '#fffefb',
    color: '#2a3329',
    fontSize: 24,
    letterSpacing: 8,
    textAlign: 'center',
    outline: 'none',
  };

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#faf7f0', padding: 16 }}>
      <div style={{ width: 'min(400px, 94vw)', background: '#fffefb', borderRadius: 26, padding: '30px 24px', boxShadow: '0 24px 70px rgba(42,51,41,0.35)' }}>
        <div style={{ textAlign: 'center', marginBottom: 22 }}>
          <div style={{ fontSize: 34, marginBottom: 8 }}>🔐</div>
          <h1 style={{ margin: 0, fontSize: 21, fontWeight: 700, color: '#2a3329' }}>Accesso amministratore</h1>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: '#6b7669' }}>Inserisci il PIN unico del gestionale</p>
        </div>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label htmlFor="pin" style={{ display: 'block', fontSize: 13, fontWeight: 700, color: '#2a3329', marginBottom: 6 }}>PIN</label>
            <input
              id="pin"
              type="password"
              inputMode="numeric"
              autoComplete="current-password"
              aria-label="PIN amministratore"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 12))}
              required
              autoFocus
              style={inputStyle}
            />
          </div>

          <button
            type="submit"
            disabled={loading || !pin}
            style={{
              marginTop: 6,
              padding: 13,
              border: 'none',
              borderRadius: 14,
              background: '#5b7a6b',
              color: '#fff',
              fontSize: 15,
              fontWeight: 800,
              cursor: loading ? 'wait' : 'pointer',
              opacity: loading || !pin ? 0.6 : 1,
            }}
          >
            {loading ? 'Accesso in corso…' : 'Accedi'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AdminLoginPage;
