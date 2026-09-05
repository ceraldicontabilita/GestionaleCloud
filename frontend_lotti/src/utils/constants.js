// Nome namespaced apposta (04/09/2026): dentro GestionaleCloud questo build
// gira nello stesso processo di build di frontend_menu (script build_frontends.sh),
// che legge il proprio REACT_APP_BACKEND_URL — un vecchio REACT_APP_BACKEND_URL
// generico rimasto nelle env di Render (dal backend Lotti standalone
// lotti-backend-2wwb.onrender.com) veniva quindi letto anche da questo build
// al posto del valore corretto "/lotti" in .env.production, mandando ogni
// chiamata (login PIN incluso) a un host esterno spento/non raggiungibile da
// qui: da fuori sembrava un server lento ("Avvio del server in corso..."),
// in realtà la richiesta non arrivava mai al servizio giusto.
export const BACKEND_URL = process.env.REACT_APP_LOTTI_BACKEND_URL || "https://lotti-backend-f2fg.onrender.com";
export const API = `${BACKEND_URL.replace(/\/$/, "")}/api`;

/**
 * Risolve l'URL di una foto in base a dove il file viene pubblicato.
 *
 * - /api e /uploads sono serviti dal backend;
 * - /saima e gli altri asset statici sono inclusi nel frontend;
 * - gli URL assoluti restano invariati.
 *
 * In precedenza ogni percorso relativo veniva inviato al backend: le immagini
 * SAIMA esistevano nel frontend, ma il browser le chiedeva al servizio sbagliato
 * e riceveva 404.
 */
export function fotoSrc(u) {
  if (!u) return null;
  const url = String(u).trim();
  if (!url) return null;
  if (/^(?:https?:)?\/\//i.test(url) || /^(?:data|blob):/i.test(url)) return url;
  if (/^\/(?:api|uploads)(?:\/|$)/i.test(url)) {
    return `${BACKEND_URL.replace(/\/$/, "")}${url}`;
  }
  return url.startsWith("/") ? url : `/${url}`;
}

/**
 * Accoda il token JWT a un URL aperto in nuova scheda (window.open / link a PDF):
 * quelle richieste non possono inviare l'header Authorization, quindi il backend
 * accetta lo stesso token via query string (?token=...). Senza token, URL invariato.
 */
export function withToken(url) {
  let t = "";
  try { t = localStorage.getItem("lotti_token") || ""; } catch { /* no-op */ }
  if (!t) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(t);
}

export const MESI_IT = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
];

export const ALFABETO = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'Z'];

/**
 * Formatta una data ISO (YYYY-MM-DD) o datetime ISO in formato italiano DD/MM/YYYY.
 * @param {string} d - data in formato ISO
 * @param {boolean} conOra - se true aggiunge HH:MM
 * @returns {string}
 */
export function formatDate(d, conOra = false) {
  if (!d) return "—";
  try {
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return d;
    const day = String(dt.getUTCDate()).padStart(2, '0');
    const mon = String(dt.getUTCMonth() + 1).padStart(2, '0');
    const yr  = dt.getUTCFullYear();
    if (!conOra) return `${day}/${mon}/${yr}`;
    const h = String(dt.getUTCHours()).padStart(2, '0');
    const m = String(dt.getUTCMinutes()).padStart(2, '0');
    return `${day}/${mon}/${yr} ${h}:${m}`;
  } catch {
    return d;
  }
}

/**
 * Converte data italiana DD/MM/YYYY → ISO YYYY-MM-DD.
 */
export function dateToISO(d) {
  if (!d) return "";
  if (d.includes('-')) return d;
  const [dd, mm, yyyy] = d.split('/');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Data odierna in formato ISO YYYY-MM-DD (UTC).
 */
export function oggiISO() {
  return new Date().toISOString().split('T')[0];
}
