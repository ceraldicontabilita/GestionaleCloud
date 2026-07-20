import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Navigate } from 'react-router-dom';
import api, { setAuthToken, clearAuthToken, getAuthToken } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Verifica token all'avvio
  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      api.get('/api/auth/verify')
        .then(res => {
          setUser(res.data.user);
        })
        .catch(() => {
          clearAuthToken();
          setUser(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (email, password) => {
    const res = await api.post('/api/auth/login', { email, password });
    const { access_token, user_id, email: userEmail, name } = res.data;
    setAuthToken(access_token);
    const userData = {
      id: user_id,
      email: userEmail,
      name: name,
      // Il ruolo lo decide il server (res.data.user.role); l'admin via env
      // resta 'admin'.
      role: res.data.user?.role || 'admin'
    };
    setUser(userData);
    return res.data;
  }, []);

  const loginWithPin = useCallback(async pin => {
    const res = await api.post('/api/auth/pin-login', { pin });
    const { access_token, user_id, email: userEmail, name, role, auth_method } = res.data;
    setAuthToken(access_token);
    const userData = {
      id: user_id,
      email: userEmail,
      name: name,
      role: role || 'admin',
      auth_method: auth_method || 'pin'
    };
    setUser(userData);
    return res.data;
  }, []);

  const logout = useCallback(async () => {
    // Revoca il token lato server prima di scartarlo (audit sicurezza
    // 19/07/2026, review Codex su PR #65: prima logout() cancellava solo
    // lo stato locale, la blacklist server-side non veniva mai popolata).
    // Fail-closed: se la revoca non viene registrata, conserviamo la sessione
    // locale per permettere all'utente di riprovare senza dichiarare un logout
    // sicuro che in realtà non è avvenuto.
    await api.post('/api/auth/logout');
    clearAuthToken();
    setUser(null);
  }, []);

  const isAuthenticated = !!user;
  // Ruolo assente/sconosciuto: nessun privilegio implicito, coerente con il
  // backend fail-closed (app/utils/ruoli.py normalizza_ruolo).
  const role = user?.role && ['admin', 'operatore', 'sola_lettura'].includes(user.role)
    ? user.role
    : 'non_autorizzato';
  const isAdmin = role === 'admin';
  const isReadOnly = role === 'sola_lettura';
  const canWrite = role === 'admin' || role === 'operatore';

  return (
    <AuthContext.Provider value={{
      user, login, loginWithPin, logout, isAuthenticated, loading,
      role, isAdmin, isReadOnly, canWrite,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Nasconde i figli a chi non ha il ruolo richiesto.
 * <SoloAdmin>...</SoloAdmin>  → visibile solo all'admin
 * <SeScrittura>...</SeScrittura> → nascosto agli utenti in sola lettura
 */
export function SoloAdmin({ children, fallback = null }) {
  const { isAdmin } = useAuth();
  return isAdmin ? children : fallback;
}

export function SeScrittura({ children, fallback = null }) {
  const { canWrite } = useAuth();
  return canWrite ? children : fallback;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: '#0f172a'
      }}>
        <div style={{ color: '#94a3b8', fontSize: 18 }}>Caricamento...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

/** Instrada solo l'admin; gli altri ruoli vengono rimandati alla Dashboard. */
export function RequireAdmin({ children }) {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: '#0f172a'
      }}>
        <div style={{ color: '#94a3b8', fontSize: 18 }}>Caricamento...</div>
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!isAdmin) return <Navigate to="/" replace />;
  return children;
}

export default AuthContext;
