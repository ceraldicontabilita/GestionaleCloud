/**
 * apiError(e) — estrae sempre un messaggio leggibile da un errore axios,
 * evitando il classico "[object Object]" quando il backend risponde con
 * un detail oggetto/array (es. errori di validazione 422 di FastAPI).
 */
export function apiError(e, fallback = "Errore imprevisto") {
  // Casi COMUNI tradotti in messaggi comprensibili (fase 2, 24/07/2026):
  // niente errori tecnici grezzi in faccia all'operatore.
  if (e?.code === "ECONNABORTED") {
    return "Il server non ha risposto in tempo (forse è in avvio): riprova tra qualche secondo.";
  }
  if (e && !e.response && (e.message === "Network Error" || e.code === "ERR_NETWORK")) {
    return "Server non raggiungibile: controlla la connessione o attendi il riavvio (circa un minuto).";
  }
  const status = e?.response?.status;
  const d = e?.response?.data?.detail ?? e?.response?.data;
  if (status === 401) {
    return typeof d === "string" && d.trim() ? d : "Sessione scaduta: rientra col PIN.";
  }
  if (status === 403) {
    return typeof d === "string" && d.trim() ? d : "Operazione riservata all'amministratore.";
  }
  if (status >= 500) {
    return typeof d === "string" && d.trim() ? d : "Errore del server: riprova tra poco.";
  }
  if (typeof d === "string" && d.trim()) return d;
  if (Array.isArray(d)) {
    const msgs = d.map((x) => x?.msg || x?.message || (typeof x === "string" ? x : JSON.stringify(x))).filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  if (d && typeof d === "object") {
    if (d.msg) return d.msg;
    if (d.message) return d.message;
    try { return JSON.stringify(d); } catch { /* noop */ }
  }
  return e?.message || fallback;
}
