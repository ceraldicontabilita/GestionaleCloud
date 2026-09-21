import { logout } from "../auth";

const SESSION_KEY = "tablet_operatore";

export const TABLET_SESSION_MS = 2 * 60 * 60 * 1000;
export const TABLET_ACTION_AUTH_MS = 10 * 60 * 1000;

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

export function getTabletSession({ allowExpired = false } = {}) {
  const session = readRaw();
  if (!session?.dipendente_id || !session?.nome) {
    if (session) {
      clearTabletSession();
      logout();
    }
    return null;
  }
  const expiresAt = Number(session.expiresAt || 0);
  if (!allowExpired && (!expiresAt || expiresAt <= Date.now())) {
    clearTabletSession();
    return null;
  }
  return session;
}

export function saveTabletSession(operatore, reparto, { actionVerified = false } = {}) {
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
    expiresAt: now + TABLET_SESSION_MS,
    actionVerifiedAt: actionVerified
      ? now
      : (sameOperator ? Number(previous.actionVerifiedAt || 0) : 0),
  };
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

export function actionAuthorizationStillValid(session = getTabletSession()) {
  const verifiedAt = Number(session?.actionVerifiedAt || 0);
  return !!verifiedAt && Date.now() - verifiedAt < TABLET_ACTION_AUTH_MS;
}

export function markTabletActionAuthorized(operatore, reparto) {
  return saveTabletSession(operatore, reparto, { actionVerified: true });
}
