import axios from 'axios';
import { toast } from 'sonner';

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

// Il servizio riparte a ogni rilascio (Render): per uno o due minuti risponde
// 502/503/504. Una lettura non deve mostrare un errore rosso per questo: si
// riprova con attese crescenti (circa un minuto in tutto) e nel frattempo
// un solo avviso dice cosa sta succedendo. Solo le letture (GET): una
// scrittura ripetuta alla cieca potrebbe duplicare.
export const ATTESE_RITENTATIVI_MS = [2000, 4000, 8000, 12000, 16000, 20000];
const ID_AVVISO_RIAVVIO = 'riavvio-servizio';

export function eErroreTransitorio(error) {
  const status = error?.response?.status;
  return !error?.response || status === 502 || status === 503 || status === 504;
}

// Response interceptor: gestisce 401 (token scaduto/invalido) e ritenta le
// letture mentre il backend sta ripartendo.
api.interceptors.response.use(
  response => {
    // Sessione scorrevole: il backend rinnova il token mentre usi l'app
    // (scade solo dopo 1 ora di inattività, poi richiede il PIN)
    const rinnovato = response.headers?.['x-token-rinnovato'];
    if (rinnovato) {
      localStorage.setItem('auth_token', rinnovato);
    }
    if (response.config?.__tentativi) toast.dismiss(ID_AVVISO_RIAVVIO);
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
    const fatti = cfg.__tentativi || 0;
    if (
      eErroreTransitorio(error)
      && (cfg.method || '').toLowerCase() === 'get'
      && !cfg.__noRetry
      && fatti < ATTESE_RITENTATIVI_MS.length
    ) {
      cfg.__tentativi = fatti + 1;
      toast.loading('Il gestionale si sta aggiornando, riprovo…', { id: ID_AVVISO_RIAVVIO, duration: Infinity });
      await new Promise(r => setTimeout(r, ATTESE_RITENTATIVI_MS[fatti]));
      return api.request(cfg);
    }
    if (fatti) toast.dismiss(ID_AVVISO_RIAVVIO);

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

/**
 * Messaggio leggibile da un errore Axios, in un posto solo.
 *
 * Contratto del backend (app/middleware/error_handler.py): `message` e' il
 * testo per l'utente, `detail` resta quello che l'endpoint ha sollevato
 * (stringa oppure oggetto con i suoi campi), `correlation_id` serve a
 * ritrovare la riga nei log. Una risposta HTML (pagina della SPA: la
 * chiamata e' finita fuori da /api) non e' un messaggio: si dice cos'e'.
 */
export function messaggioErrore(e, predefinito = 'Operazione non riuscita') {
  const data = e?.response?.data;
  let testo = '';
  if (data && typeof data === 'object') {
    const d = data.detail;
    testo = data.message
      || (typeof d === 'string' ? d : '')
      || (d && typeof d === 'object' && typeof d.message === 'string' ? d.message : '');
  } else if (typeof data === 'string' && data.trim().startsWith('<')) {
    testo = 'Il server ha risposto con una pagina invece che con dei dati';
  }
  if (!testo && e?.response?.status === 405) testo = 'Operazione non disponibile a questo indirizzo';
  if (!testo) testo = e?.message || predefinito;
  const rif = data && typeof data === 'object' ? data.correlation_id : null;
  return rif ? `${testo} (rif. ${rif})` : testo;
}

export async function health() {
  const r = await api.get('/api/health');
  return r.data;
}

// Generic API helper
export default api;
