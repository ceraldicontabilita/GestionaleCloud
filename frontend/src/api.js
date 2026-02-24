import axios from "axios";

const api = axios.create({
  baseURL: "",
  timeout: 120000, // 2 minuti default
});

// =============================================================================
// AUTH INTERCEPTOR
// Aggiunge automaticamente il token JWT a tutte le richieste API
// =============================================================================

// Request interceptor: aggiunge Authorization header
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: gestisce 401 (token scaduto/invalido)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token scaduto o invalido - redirect a login
      localStorage.removeItem("auth_token");
      // Evita loop se siamo già sulla pagina di login
      if (!window.location.pathname.includes("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

// =============================================================================
// AUTH HELPERS
// =============================================================================

export function setAuthToken(token) {
  localStorage.setItem("auth_token", token);
}

export function clearAuthToken() {
  localStorage.removeItem("auth_token");
}

export function getAuthToken() {
  return localStorage.getItem("auth_token");
}

export function isAuthenticated() {
  return !!localStorage.getItem("auth_token");
}

export async function health() {
  const r = await api.get("/api/health");
  return r.data;
}

export async function dashboardSummary(anno = null) {
  try {
    const params = anno ? `?anno=${anno}` : '';
    const r = await api.get(`/api/dashboard/summary${params}`);
    return r.data;
  } catch (e) {
    console.error("Dashboard summary error:", e);
    return null;
  }
}

export async function uploadDocument(file, kind) {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  const r = await api.post("/api/portal/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return r.data;
}

// Invoices API
export async function getInvoices(skip = 0, limit = 50) {
  const r = await api.get(`/api/invoices?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createInvoice(data) {
  const r = await api.post("/api/invoices", data);
  return r.data;
}

// Suppliers API
export async function getSuppliers(skip = 0, limit = 50) {
  const r = await api.get(`/api/suppliers?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createSupplier(data) {
  const r = await api.post("/api/suppliers", data);
  return r.data;
}

// Warehouse API
export async function getWarehouseProducts(skip = 0, limit = 50) {
  const r = await api.get(`/api/warehouse/products?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createWarehouseProduct(data) {
  const r = await api.post("/api/warehouse/products", data);
  return r.data;
}

// Employees API
export async function getEmployees(skip = 0, limit = 50) {
  const r = await api.get(`/api/employees?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createEmployee(data) {
  const r = await api.post("/api/employees", data);
  return r.data;
}

// Cash Register API
export async function getCashMovements(skip = 0, limit = 50) {
  const r = await api.get(`/api/cash?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createCashMovement(data) {
  const r = await api.post("/api/cash", data);
  return r.data;
}

// Bank API
export async function getBankStatements(skip = 0, limit = 50) {
  const r = await api.get(`/api/bank/statements?skip=${skip}&limit=${limit}`);
  return r.data;
}

// Orders API
export async function getOrders(skip = 0, limit = 50) {
  const r = await api.get(`/api/orders?skip=${skip}&limit=${limit}`);
  return r.data;
}

export async function createOrder(data) {
  const r = await api.post("/api/orders", data);
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
    responseType: format === 'xlsx' ? 'blob' : 'json'
  });
  return r.data;
}

// Generic API helper
export default api;
