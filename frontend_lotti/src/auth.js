import axios from "axios";
import { API } from "@/utils/constants";

const TOKEN_KEY = "lotti_token";

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
};
export const saveToken = (t) => {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); } catch { /* no-op */ }
};
export const clearToken = () => {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* no-op */ }
};

// Accoda il token JWT a un URL di documento aperto in nuova scheda (window.open):
// quelle richieste non possono inviare l'header Authorization, quindi il backend
// accetta lo stesso token via query string (?token=...).
export const withToken = (url) => {
  const t = getToken();
  if (!t) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(t);
};

// ── Cancello a tempo (richiesta Enzo 02/07/2026): il PIN resta valido 2 ORE
// su TUTTE le pagine, anche uscendo/rientrando o riaprendo la scheda.
// (prima era sessionStorage per-scheda: ogni nuova scheda richiedeva il PIN)
const GATE_KEY = "lotti_gate_until";
export const GATE_DURATA_MS = 2 * 60 * 60 * 1000;
export function setGateOk() {
  try { localStorage.setItem(GATE_KEY, String(Date.now() + GATE_DURATA_MS)); } catch { /* no-op */ }
}
export function gateStillValid() {
  try {
    const fino = Number(localStorage.getItem(GATE_KEY) || 0);
    return !!getToken() && fino > Date.now();
  } catch { return false; }
}
export function clearGate() {
  try { localStorage.removeItem(GATE_KEY); } catch { /* no-op */ }
}

// ── PIN amministratore del TABLET kiosk: stessa idea del cancello sopra ma
// per il PIN admin usato per uscire dal kiosk (TabletHome/TabletView),
// SEPARATO dal cancello principale (sistemi diversi: quello è il JWT del
// gestionale, questo è il PIN condiviso del tablet). Dura al massimo due ore
// anche tra schede o riaperture accidentali del browser; l'uscita esplicita
// continua invece a cancellare la sessione operatore.
// Richiesta Enzo 03/07/2026: "deve persistere per due ore" (uscire da una
// card e rientrare non deve richiedere di nuovo il PIN admin).
const ADMIN_GATE_KEY = "tablet_admin_until";
export function setAdminGateOk() {
  try { localStorage.setItem(ADMIN_GATE_KEY, String(Date.now() + GATE_DURATA_MS)); } catch { /* no-op */ }
  try { sessionStorage.removeItem(ADMIN_GATE_KEY); } catch { /* no-op */ }
}
export function adminGateStillValid() {
  try {
    const persisted = Number(localStorage.getItem(ADMIN_GATE_KEY) || 0);
    if (persisted > Date.now()) return true;
    const legacy = Number(sessionStorage.getItem(ADMIN_GATE_KEY) || 0);
    if (legacy > Date.now()) {
      localStorage.setItem(ADMIN_GATE_KEY, String(legacy));
      sessionStorage.removeItem(ADMIN_GATE_KEY);
      return true;
    }
    localStorage.removeItem(ADMIN_GATE_KEY);
    sessionStorage.removeItem(ADMIN_GATE_KEY);
    return false;
  } catch { return false; }
}
export function clearAdminGate() {
  try { localStorage.removeItem(ADMIN_GATE_KEY); } catch { /* no-op */ }
  try { sessionStorage.removeItem(ADMIN_GATE_KEY); } catch { /* no-op */ }
}

const OPNOME_KEY = "lotti_operatore_nome";
export const saveOperatoreNome = (n) => { try { if (n) localStorage.setItem(OPNOME_KEY, n); } catch { /* no-op */ } };
export const getOperatoreNome = () => { try { return localStorage.getItem(OPNOME_KEY) || ""; } catch { return ""; } };

const RUOLO_KEY = "lotti_ruolo";
export const saveRuolo = (r) => { try { if (r) localStorage.setItem(RUOLO_KEY, r); } catch { /* no-op */ } };
export const getRuolo = () => { try { return localStorage.getItem(RUOLO_KEY) || ""; } catch { return ""; } };
export const isAdmin = () => getRuolo() === "amministratore";

/** Logout completo: cancella token e ruolo, azzera il flag di sessione del
 *  cancello e notifica l'app così il LoginGate torna a chiedere il PIN/Google.
 *  Usato dal bottone "Esci" dell'app principale e dallo switch operatore. */
export function logout() {
  clearToken();
  clearGate();
  try { localStorage.removeItem(RUOLO_KEY); } catch { /* no-op */ }
  try { localStorage.removeItem(OPNOME_KEY); } catch { /* no-op */ }
  try { window.dispatchEvent(new Event("lotti-auth-changed")); } catch { /* no-op */ }
}

/** Config già nota in cache, LETTA SUBITO (sincrona): la usiamo per mostrare
 *  il keypad senza aspettare il backend freddo. */
export function cachedAuthConfig() {
  try {
    const c = localStorage.getItem("lotti_auth_cfg");
    if (!c) return null;
    const cfg = JSON.parse(c);
    // Fidati della cache SOLO se è una risposta reale del server. Una vecchia
    // cache di ripiego (senza _reale) non deve poter aprire l'app senza PIN.
    return cfg && cfg._reale ? cfg : null;
  } catch { return null; }
}

let _installed = false;
/** Installa una volta sola gli interceptor axios: allega il token a ogni
 *  richiesta e, su 401, lo azzera e notifica il gate. */
export function setupAxiosAuth() {
  if (_installed) return;
  _installed = true;
  axios.interceptors.request.use((config) => {
    const t = getToken();
    if (t) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${t}`;
    }
    return config;
  });
  axios.interceptors.response.use(
    (r) => r,
    (err) => {
      if (err && err.response && err.response.status === 401) {
        clearToken();
        try { window.dispatchEvent(new Event("lotti-auth-changed")); } catch { /* no-op */ }
      }
      return Promise.reject(err);
    }
  );
}

/** Config pubblica del backend, con MEMORIA: l'ultima config buona resta in
 *  localStorage. Se il backend dorme (cold start Render) NON si finge che
 *  l'enforcement sia spento: si usa l'ultima config nota. Solo al primissimo
 *  avvio in assoluto, senza memoria, si resta aperti per non murare il kiosk. */
const CFG_KEY = "lotti_auth_cfg";
export async function fetchAuthConfig() {
  for (let i = 0; i < 2; i++) {
    try {
      const r = await axios.get(`${API}/auth/config`, { timeout: 15000 });
      const cfg = r.data || { enforce: true, google_enabled: false };
      // Cache SOLO risposte vere del server. Mai memorizzare un fallback:
      // un {enforce:false} di ripiego, se finiva in cache, apriva per sempre
      // l'app senza PIN. (bug visto da Enzo il 14/06/2026)
      try { localStorage.setItem(CFG_KEY, JSON.stringify({ ...cfg, _reale: true })); } catch { /* no-op */ }
      return cfg;
    } catch {
      if (i === 0) await new Promise((res) => setTimeout(res, 4000));
    }
  }
  try {
    const cached = localStorage.getItem(CFG_KEY);
    if (cached) {
      const c = JSON.parse(cached);
      if (c && c._reale) return c;  // usa solo cache REALE
    }
  } catch { /* no-op */ }
  // Nessuna config reale disponibile: default PRUDENTE = serve il PIN.
  return { enforce: true, google_enabled: false };
}

/** Verifica il token lato server.
 *  true  = valido; false = RIFIUTATO dal server (401);
 *  null  = rete giu'/backend freddo: NON si sa. Chi chiama decide la grazia
 *  (un token presente non va buttato perche' Render dormiva: il vero 401
 *  arriva comunque dall'interceptor alla prima richiesta reale). */
export async function validateToken() {
  const t = getToken();
  if (!t) return false;
  try {
    const r = await axios.get(`${API}/auth/me`, { timeout: 25000 });
    return !!(r.data && r.data.ok);
  } catch (err) {
    if (err && err.response && err.response.status === 401) return false;
    return null; // errore di rete: sconosciuto, niente lock punitivo
  }
}

/** Rinnovo automatico: ogni ora chiede un token fresco se ne abbiamo uno valido.
 *  Cosi' il kiosk sempre acceso non scade mai a sorpresa a meta' lavoro. */
let _refreshTimer = null;
export function startTokenAutoRefresh() {
  if (_refreshTimer) return;
  const tick = async () => {
    const t = getToken();
    if (!t) return;
    try {
      const r = await axios.post(`${API}/auth/refresh`, {}, { timeout: 8000 });
      if (r.data && r.data.token) saveToken(r.data.token);
    } catch { /* se fallisce, l'interceptor gestira' l'eventuale 401 */ }
  };
  _refreshTimer = setInterval(tick, 60 * 60 * 1000); // ogni ora
}
