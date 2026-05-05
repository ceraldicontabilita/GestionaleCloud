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
      role: 'admin'
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

  const logout = useCallback(() => {
    clearAuthToken();
    setUser(null);
  }, []);

  const isAuthenticated = !!user;

  return (
    <AuthContext.Provider value={{ user, login, loginWithPin, logout, isAuthenticated, loading }}>
      {children}
    </AuthContext.Provider>
  );
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

export default AuthContext;
