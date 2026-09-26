import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Navigate } from 'react-router-dom';
import api, { setAuthToken, clearAuthToken, getAuthToken } from '../api';
import { pulisciSessioneGruppoBrowser } from '../../../frontend_shared/SessioneGruppo';
import {
  INTERVALLO_GUSCIO_MS,
  attesaProssimoGiro,
  leggiCacheGuscio,
  scriviCacheGuscio,
} from '../lib/cacheGuscio';

const CHIAVE_VERIFY = '/api/auth/verify';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const applyAuthentication = useCallback(data => {
    setAuthToken(data.access_token);
    const userData = {
      id: data.user_id,
      email: data.email,
      name: data.name,
      role: data.user?.role || data.role || 'admin',
      auth_method: data.auth_method,
      mfa_enabled: data.user?.mfa_enabled ?? true,
      mfa_verified: !!data.mfa_verified,
    };
    setUser(userData);
    scriviCacheGuscio(CHIAVE_VERIFY, userData);
    return data;
  }, []);

  // All'avvio ogni errore chiude la sessione (come prima); nel giro
  // periodico solo un rifiuto del backend, non un 502 durante un deploy.
  const verifica = useCallback((avvio = false) => (
    api.get(CHIAVE_VERIFY)
      .then(res => {
        scriviCacheGuscio(CHIAVE_VERIFY, res.data.user);
        setUser(res.data.user);
      })
      .catch(e => {
        const status = e?.response?.status;
        if (avvio || status === 401 || status === 403) {
          clearAuthToken();
          setUser(null);
        }
      })
  ), []);

  // Verifica token all'avvio: una sola chiamata, o nessuna se la stessa
  // sessione l'ha verificata meno di 120 s fa (ricaricamento della pagina).
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      return;
    }
    const copia = leggiCacheGuscio(CHIAVE_VERIFY);
    if (copia) {
      setUser(copia.dati);
      setLoading(false);
    } else {
      verifica(true).finally(() => setLoading(false));
    }
  }, [verifica]);

  // Poi un giro ogni 120 s finché la sessione è aperta.
  const autenticato = !!user;
  useEffect(() => {
    if (!autenticato) return undefined;
    let timer;
    let chiuso = false;
    const giro = async () => {
      if (!getAuthToken()) return;
      await verifica();
      if (!chiuso) timer = setTimeout(giro, INTERVALLO_GUSCIO_MS);
    };
    timer = setTimeout(giro, attesaProssimoGiro(CHIAVE_VERIFY) || INTERVALLO_GUSCIO_MS);
    return () => {
      chiuso = true;
      clearTimeout(timer);
    };
  }, [autenticato, verifica]);

  const login = useCallback(async (email, password) => {
    const res = await api.post('/api/auth/login', { email, password });
    if (res.data.mfa_required) return res.data;
    return applyAuthentication(res.data);
  }, [applyAuthentication]);

  const loginWithPin = useCallback(async pin => {
    const res = await api.post('/api/auth/pin-login', { pin });
    if (res.data.mfa_required) return res.data;
    return applyAuthentication(res.data);
  }, [applyAuthentication]);

  const verifyMfaLogin = useCallback(async (challengeToken, code) => {
    const res = await api.post('/api/auth/mfa/verify-login', {
      challenge_token: challengeToken,
      code,
    });
    return applyAuthentication(res.data);
  }, [applyAuthentication]);

  const applyMfaStepUp = useCallback(data => {
    setAuthToken(data.access_token);
    setUser(prev => prev ? { ...prev, mfa_enabled: true, mfa_verified: true } : prev);
    return data;
  }, []);

  const logout = useCallback(async () => {
    // Revoca il token lato server prima di scartarlo (audit sicurezza
    // 19/07/2026, review Codex su PR #65: prima logout() cancellava solo
    // lo stato locale, la blacklist server-side non veniva mai popolata).
    // Fail-closed: se la revoca non viene registrata, conserviamo la sessione
    // locale per permettere all'utente di riprovare senza dichiarare un logout
    // sicuro che in realtà non è avvenuto.
    await api.post('/api/auth/logout');
    pulisciSessioneGruppoBrowser();
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
      verifyMfaLogin, applyMfaStepUp,
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
