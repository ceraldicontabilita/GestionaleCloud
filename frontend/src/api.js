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
  response => response,
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
    if (transitorio && (cfg.method || '').toLowerCase() === 'get' && !cfg.__ritentata) {
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

export async function dashboardSummary(anno = null) {
  try {
    const params = anno ? `?anno=${anno}` : '';
    const r = await api.get(`/api/dashboard/summary${params}`);
    return r.data;
  } catch (e) {
    console.error('Dashboard summary error:', e);
    return null;
  }
}

// Invoices API
export async function getInvoices(skip = 0, limit = 50) {
  const r = await api.get(`/api/invoices?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createInvoice(data) {
  const r = await api.post('/api/invoices', data);
  return r.data;
}

// Suppliers API
export async function getSuppliers(skip = 0, limit = 50) {
  const r = await api.get(`/api/suppliers?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createSupplier(data) {
  const r = await api.post('/api/suppliers', data);
  return r.data;
}

// Warehouse API
export async function getWarehouseProducts(skip = 0, limit = 50) {
  const r = await api.get(`/api/warehouse/products?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createWarehouseProduct(data) {
  const r = await api.post('/api/warehouse/products', data);
  return r.data;
}

// Cash Register API
export async function getCashMovements(skip = 0, limit = 50) {
  const r = await api.get(`/api/cash?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createCashMovement(data) {
  const r = await api.post('/api/cash', data);
  return r.data;
}

// Bank API
export async function getBankStatements(skip = 0, limit = 50) {
  const r = await api.get(`/api/bank/statements?skip=${skip}&limit=${limit}`);
  return r.data;
}

// F24 API
export async function getF24Models(skip = 0, limit = 50) {
  const r = await api.get(`/api/f24?skip=${skip}&limit=${limit}`);
  return r.data;
}

// Export API
export async function exportData(format, dataType) {
  const r = await api.get(`/api/exports/${dataType}?format=${format}`, {
    responseType: format === 'xlsx' ? 'blob' : 'json',
  });
  return r.data;
}

// Generic API helper
export default api;
