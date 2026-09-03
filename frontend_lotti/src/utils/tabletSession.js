const SESSION_KEY = "tablet_operatore";

export const TABLET_SESSION_MS = 2 * 60 * 60 * 1000;
export const TABLET_ACTION_AUTH_MS = 10 * 60 * 1000;

function readRaw() {
  try {
    const persisted = localStorage.getItem(SESSION_KEY);
    if (persisted) return JSON.parse(persisted);

    // Migrazione trasparente dalla vecchia memoria legata alla singola scheda:
    // evita di richiedere di nuovo il PIN dopo aggiornamento o apertura di una
    // nuova scheda, mantenendo comunque la scadenza temporale della sessione.
    const legacy = sessionStorage.getItem(SESSION_KEY);
    if (!legacy) return null;
    localStorage.setItem(SESSION_KEY, legacy);
    sessionStorage.removeItem(SESSION_KEY);
    return JSON.parse(legacy);
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
  if (!session?.id || !session?.nome) return null;
  // Migra senza interrompere chi era gia entrato prima dell'aggiornamento.
  const legacyStartedAt = Number(session.startedAt || session.ts || 0);
  const expiresAt = Number(session.expiresAt || (legacyStartedAt ? legacyStartedAt + TABLET_SESSION_MS : 0));
  if (!allowExpired && (!expiresAt || expiresAt <= Date.now())) {
    clearTabletSession();
    return null;
  }
  return session.expiresAt ? session : { ...session, startedAt: legacyStartedAt, expiresAt };
}

export function saveTabletSession(operatore, reparto, { actionVerified = false } = {}) {
  const now = Date.now();
  const previous = readRaw() || {};
  const sameOperator = previous.id && previous.id === operatore?.id;
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
  // Compatibilita temporanea con viste ancora in migrazione.
  session.ts = session.startedAt;
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
