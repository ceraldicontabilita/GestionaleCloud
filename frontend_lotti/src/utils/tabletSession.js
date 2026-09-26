import { getToken, isAdmin, logout } from "../auth";

const SESSION_KEY = "tablet_operatore";

function readRaw() {
  try {
    const persisted = localStorage.getItem(SESSION_KEY);
    if (persisted) return JSON.parse(persisted);
    if (sessionStorage.getItem(SESSION_KEY)) {
      sessionStorage.removeItem(SESSION_KEY);
      logout();
    }
    return null;
  } catch {
    return null;
  }
}

export function clearTabletSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch { /* no-op */ }
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* no-op */ }
}

export function getTabletSession() {
  const session = readRaw();
  if (!getToken()) {
    if (session) clearTabletSession();
    return null;
  }
  if (!session?.dipendente_id || !session?.nome) {
    if (session) {
      clearTabletSession();
      logout();
    }
    return null;
  }
  return session;
}

export function saveTabletSession(operatore, reparto) {
  if (!operatore?.dipendente_id) throw new Error("ID dipendente obbligatorio");
  const now = Date.now();
  const previous = readRaw() || {};
  const sameOperator = previous.dipendente_id && previous.dipendente_id === operatore.dipendente_id;
  const session = {
    ...previous,
    ...operatore,
    reparto: reparto || previous.reparto || "",
    startedAt: sameOperator ? Number(previous.startedAt || now) : now,
    lastSeenAt: now,
  };
  delete session.actionVerifiedAt;
  try { localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch { /* no-op */ }
  // Rimuove l'eventuale copia legacy per non avere due fonti discordanti.
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* no-op */ }
  return session;
}

export function moveTabletSessionTo(reparto) {
  const session = getTabletSession();
  if (!session) return null;
  return saveTabletSession(session, reparto);
}

/** Il titolare e' entrato dal Gestionale (token amministratore di Lotti). */
export function sessioneTitolareAttiva() {
  return !!getToken() && isAdmin();
}

/**
 * Dopo l'ingresso dal Gestionale il token e' del titolare: la persona del
 * tablet deve essere la stessa, o un dipendente rimasto identificato
 * firmerebbe col token del titolare. Se il titolare ha una scheda HR diventa
 * lui l'operatore; altrimenti l'operatore si azzera e la prossima card di
 * reparto chiede il PIN.
 */
export function allineaSessioneTitolare(titolare, reparto) {
  if (titolare?.dipendente_id) {
    return saveTabletSession({ ...titolare, ruolo: "amministratore" }, reparto);
  }
  clearTabletSession();
  return null;
}
