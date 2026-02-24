import React, { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';

/**
 * AuthCallback - Gestisce il ritorno da Google OAuth
 * Processa il session_id dall'URL fragment e crea la sessione locale
 * 
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Previene doppia esecuzione in StrictMode
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processGoogleAuth = async () => {
      try {
        // Estrai session_id dall'URL fragment
        const hash = location.hash;
        const sessionIdMatch = hash.match(/session_id=([^&]+)/);
        
        if (!sessionIdMatch) {
          console.error('[AuthCallback] session_id non trovato nel fragment');
          navigate('/login', { replace: true });
          return;
        }

        const sessionId = sessionIdMatch[1];
        console.log('[AuthCallback] Processando session_id...');

        // Chiama il backend per validare e creare la sessione
        const response = await api.post('/api/auth/google/session', {
          session_id: sessionId
        });

        if (response.data.success && response.data.user) {
          console.log('[AuthCallback] Login Google riuscito:', response.data.user.email);
          
          // Salva token nel localStorage per compatibilità con AuthContext
          if (response.data.access_token) {
            localStorage.setItem('token', response.data.access_token);
          }
          
          // Naviga alla dashboard con i dati utente
          navigate('/', { 
            replace: true,
            state: { user: response.data.user }
          });
        } else {
          throw new Error('Risposta non valida dal server');
        }
      } catch (error) {
        console.error('[AuthCallback] Errore:', error);
        navigate('/login', { 
          replace: true,
          state: { error: 'Errore durante il login con Google. Riprova.' }
        });
      }
    };

    processGoogleAuth();
  }, [navigate, location]);

  // Mostra un loading minimo durante il processo
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
      color: '#f8fafc',
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 48,
          height: 48,
          border: '3px solid #1535a8',
          borderTopColor: 'transparent',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
          margin: '0 auto 16px',
        }} />
        <p style={{ color: '#94a3b8', fontSize: 14 }}>
          Accesso con Google in corso...
        </p>
      </div>
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
