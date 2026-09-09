import axios from 'axios';

const api = axios.create({
  baseURL: '',
  timeout: 120000, // 2 minuti default
});

// =============================================================================
// AUTH INTERCEPTOR
// Aggiunge automaticamente il token JWT a tutte le richieste API
// =============================================================================

// Request interceptor: aggiunge Authorization header
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  error => Promise.reject(error)
);

// Response interceptor: gestisce 401 (token scaduto/invalido) e ritenta
// UNA volta le letture quando il backend sta ripartendo (cold start Render:
// 502/503/504 o richiesta caduta) — evita la pagina d'errore al primo
// accesso della giornata quando il server impiega qualche secondo a salire.
api.interceptors.response.use(
  response => {
    // Sessione scorrevole: il backend rinnova il token mentre usi l'app
    // (scade solo dopo 1 ora di inattività, poi richiede il PIN)
    const rinnovato = response.headers?.['x-token-rinnovato'];
    if (rinnovato) {
      localStorage.setItem('auth_token', rinnovato);
    }
    return response;
  },
  async error => {
    if (error.response?.status === 401) {
      // Token scaduto o invalido - redirect a login
      localStorage.removeItem('auth_token');
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }

    const cfg = error.config || {};
    const status = error.response?.status;
    const transitorio = !error.response || status === 502 || status === 503 || status === 504;
    if (
      transitorio
      && (cfg.method || '').toLowerCase() === 'get'
      && !cfg.__ritentata
      && !cfg.__noRetry
    ) {
      cfg.__ritentata = true;
      await new Promise(r => setTimeout(r, 2000));
      return api.request(cfg);
    }

    return Promise.reject(error);
  }
);

// =============================================================================
// AUTH HELPERS
// =============================================================================

export function setAuthToken(token) {
  localStorage.setItem('auth_token', token);
}

export function clearAuthToken() {
  localStorage.removeItem('auth_token');
}

export function getAuthToken() {
  return localStorage.getItem('auth_token');
}

export function isAuthenticated() {
  return !!localStorage.getItem('auth_token');
}

export async function health() {
  const r = await api.get('/api/health');
  return r.data;
}

// Generic API helper
export default api;
