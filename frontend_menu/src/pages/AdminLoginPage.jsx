import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../hooks/use-toast';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

// Stile allineato al cancello PIN di Lotti (frontend_lotti/.../LoginGate.jsx +
// PinKeypad): stessa cream/sage/ink della palette Ceraldi, card centrata con
// ombra morbida, invece del vecchio riquadro scuro generico in inglese —
// richiesta del titolare 05/09/2026: "unifica la grafica fin dove è possibile".
// Rimosso anche il testo con la password di default visibile a chiunque apra
// la pagina, mai accettabile su un form di login pubblico.
const AdminLoginPage = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await axios.post(`${BACKEND_URL}/api/qrcode/login`, {
        username,
        password
      });

      if (response.data.success) {
        localStorage.setItem('admin_token', response.data.token);
        toast({
          title: 'Accesso effettuato',
          description: 'Benvenuto nel pannello di amministrazione'
        });
        navigate('/admin');
      } else {
        toast({
          title: 'Accesso non riuscito',
          description: response.data.message,
          variant: 'destructive'
        });
      }
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Accesso non riuscito. Riprova.',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    width: '100%',
    boxSizing: 'border-box',
    padding: '12px 14px',
    borderRadius: 12,
    border: '1.5px solid #e6e0d4',
    background: '#fffefb',
    color: '#2a3329',
    fontSize: 15,
    outline: 'none',
  };

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#faf7f0', padding: 16 }}>
      <div style={{ width: 'min(400px, 94vw)', background: '#fffefb', borderRadius: 26, padding: '30px 24px', boxShadow: '0 24px 70px rgba(42,51,41,0.35)' }}>
        <div style={{ textAlign: 'center', marginBottom: 22 }}>
          <div style={{ fontSize: 34, marginBottom: 8 }}>🔐</div>
          <h1 style={{ margin: 0, fontSize: 21, fontWeight: 700, color: '#2a3329' }}>Accesso amministratore</h1>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: '#6b7669' }}>Inserisci le tue credenziali per gestire il Menu</p>
        </div>
        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label htmlFor="username" style={{ display: 'block', fontSize: 13, fontWeight: 700, color: '#2a3329', marginBottom: 6 }}>Nome utente</label>
            <input
              id="username"
              type="text"
              placeholder="admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={inputStyle}
            />
          </div>
          <div>
            <label htmlFor="password" style={{ display: 'block', fontSize: 13, fontWeight: 700, color: '#2a3329', marginBottom: 6 }}>Password</label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={inputStyle}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: 6, padding: 13, border: 'none', borderRadius: 14,
              background: '#5b7a6b', color: '#fff', fontSize: 15, fontWeight: 800,
              cursor: loading ? 'wait' : 'pointer', opacity: loading ? 0.6 : 1,
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