import axios from "axios";
import { API } from "./utils/constants";

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

// ── Cancello (richiesta Enzo, aggiornata 04/09/2026): il PIN inserito resta
// valido su TUTTE le pagine e tra riaperture della scheda finché non si preme
// "Esci" — niente più scadenza a tempo (era 2 ore) indipendente dal token: il
// JWT viene rinnovato ogni ora da startTokenAutoRefresh() e resta vivo finché
// l'app è aperta, ma il vecchio cancello a 2 ore chiedeva comunque di nuovo il
// PIN a metà lavoro anche con un token perfettamente valido. Ora il cancello
// segue lo stesso confine del token: aperto finché c'è un token, richiuso solo
// da un logout esplicito o da un vero 401 del server (intercettato da axios).
const GATE_KEY = "lotti_gate_until";
export function setGateOk() {
  try { localStorage.setItem(GATE_KEY, "1"); } catch { /* no-op */ }
}
export function gateStillValid() {
  try {
    return !!getToken() && localStorage.getItem(GATE_KEY) === "1";
  } catch { return false; }
}
export function clearGate() {
  try { localStorage.removeItem(GATE_KEY); } catch { /* no-op */ }
}

const OPNOME_KEY = "lotti_operatore_nome";
export const saveOperatoreNome = (n) => { try { if (n) localStorage.setItem(OPNOME_KEY, n); } catch { /* no-op */ } };
export const getOperatoreNome = () => { try { return localStorage.getItem(OPNOME_KEY) || ""; } catch { return ""; } };

const RUOLO_KEY = "lotti_ruolo";
export const saveRuolo = (r) => { try { if (r) localStorage.setItem(RUOLO_KEY, r); } catch { /* no-op */ } };
export const getRuolo = () => { try { return localStorage.getItem(RUOLO_KEY) || ""; } catch { return ""; } };
export const isAdmin = () => getRuolo() === "amministratore";

/** Logout completo: cancella token e ruolo, azzera il flag di sessione del
 *  cancello e notifica l'app così il LoginGate torna a chiedere l'accesso.
 *  Usato dal bottone "Esci" dell'app principale e dallo switch operatore. */
export function logout() {
  clearToken();
  clearGate();
  try { localStorage.removeItem(RUOLO_KEY); } catch { /* no-op */ }
  try { localStorage.removeItem(OPNOME_KEY); } catch { /* no-op */ }
  try { window.dispatchEvent(new Event("lotti-auth-changed")); } catch { /* no-op */ }
}

/** Config già nota in cache, LETTA SUBITO (sincrona): la usiamo per mostrare
 *  il cancello senza aspettare il backend freddo. */
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
      const cfg = r.data || { enforce: true };
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
  return { enforce: true };
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

// Pagina chiesta da un link (es. #attendibilita_haccp) da chi non era ancora
// entrato come amministratore: il kiosk la sostituiva con #tablet/home e dopo
// il PIN si finiva sulla dashboard, come se la pagina non esistesse.
const PAGINA_RICHIESTA_KEY = "lotti_pagina_richiesta";
export function ricordaPaginaRichiesta() {
  const h = (window.location.hash || "").replace("#", "");
  if (!h || h.startsWith("tablet")) return;
  try { sessionStorage.setItem(PAGINA_RICHIESTA_KEY, h); } catch { /* no-op */ }
}
export function prendiPaginaRichiesta(ripiego = "dashboard") {
  let h = "";
  try { h = sessionStorage.getItem(PAGINA_RICHIESTA_KEY) || ""; sessionStorage.removeItem(PAGINA_RICHIESTA_KEY); } catch { /* no-op */ }
  return h || ripiego;
}

// ── Sessione unica del gruppo ───────────────────────────────────────────────
// Chi e' gia' entrato nel Gestionale (cookie di sessione dell'ERP, HttpOnly,
// stesso dominio) apre Lotti senza un secondo PIN: il server lo verifica e
// restituisce un token di Lotti. Istanza axios separata: l'intercettore
// normale, su un 401, rilancerebbe il cancello all'infinito.
const _senzaIntercettori = axios.create();

/** Restituisce l'operatore amministratore (nome, dipendente_id se il titolare
 *  ha una scheda HR univoca) oppure false se non c'e' sessione del Gestionale. */
export async function entraDalGestionale() {
  try {
    const r = await _senzaIntercettori.get(`${API}/auth/session`, { timeout: 10000, withCredentials: true });
    const token = r.data && r.data.token;
    if (!token) return false;
    const operatore = { ...(r.data.operatore || {}), ruolo: "amministratore" };
    saveToken(token);
    saveRuolo("amministratore");
    saveOperatoreNome(operatore.nome || "");
    setGateOk();
    return operatore;
  } catch {
    return false;
  }
}

/** Porta al login del Gestionale (separato per poterlo verificare nei test). */
export function vaiAlLoginGestionale(destinazione) {
  window.location.assign(loginGestionale(destinazione));
}

/** Login del Gestionale con ritorno alla pagina di Lotti richiesta. */
export function loginGestionale(destinazione) {
  const next = destinazione || `/lotti/${window.location.hash || ""}`;
  return `/login?next=${encodeURIComponent(next)}`;
}
