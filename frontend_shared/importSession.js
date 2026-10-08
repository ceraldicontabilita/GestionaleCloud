// File e risultati appartengono all'import, non al ciclo di vita della pagina.
// La memoria mantiene il lavoro durante la navigazione SPA; IndexedDB conserva
// anche i File quando si passa fra ERP e HR o si ricarica il browser.
const stores = new Map();
let database;
function openDatabase() {
  if (!database) database = new Promise((resolve, reject) => {
    const request = indexedDB.open('ceraldi-import-session', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('sessions');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return database;
}
function sessionKey(scope) {
  let tab = sessionStorage.getItem('ceraldi-import-tab');
  if (!tab) { tab = crypto.randomUUID(); sessionStorage.setItem('ceraldi-import-tab', tab); }
  return `${tab}:${scope}`;
}
function getStore(scope, initial) {
  const key = sessionKey(scope);
  if (stores.has(key)) return stores.get(key);
  let snapshot = { state: initial, ready: false, error: null };
  let timer;
  let closed = false;
  const listeners = new Set();
  const emit = () => listeners.forEach(fn => fn());
  const persist = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const db = await openDatabase();
        if (closed) return;
        const tx = db.transaction('sessions', 'readwrite');
        tx.objectStore('sessions').put(snapshot.state, key);
        tx.onerror = () => { snapshot = { ...snapshot, error: 'Impossibile conservare i file sul dispositivo. Mantieni aperta questa pagina fino al termine.' }; emit(); };
      } catch {
        snapshot = { ...snapshot, error: 'Salvataggio locale non disponibile. Mantieni aperta questa pagina fino al termine.' }; emit();
      }
    }, 0);
  };
  const store = {
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    getSnapshot: () => snapshot,
    setField(field, value) {
      if (closed) return;
      snapshot = { ...snapshot, state: { ...snapshot.state, [field]: typeof value === 'function' ? value(snapshot.state[field]) : value } };
      emit(); persist();
    },
  };
  stores.set(key, store);
  window.addEventListener('ceraldi-logout', () => {
    closed = true;
    clearTimeout(timer);
    snapshot = { state: initial, ready: true, error: null };
    emit();
    stores.delete(key);
  }, { once: true });
  openDatabase().then(db => new Promise((resolve, reject) => {
    const request = db.transaction('sessions').objectStore('sessions').get(key);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  })).then(saved => {
    if (closed) return;
    snapshot = { ...snapshot, ready: true, state: saved ? {
      ...initial, ...saved, uploading: false, importing: false,
      interrupted: Boolean(saved.uploading || saved.importing || saved.interrupted),
      files: saved.files?.map(f => f.status === 'uploading' ? { ...f, status: 'preview' } : f) || initial.files,
    } : initial };
    emit();
  }).catch(() => { snapshot = { ...snapshot, ready: true, error: 'Recupero locale non disponibile.' }; emit(); });
  return store;
}

// Ogni app fornisce la propria copia React: il modulo condiviso non importa
// dipendenze dal node_modules di un'altra app del monorepo.
export function createUseImportSession({ useMemo, useSyncExternalStore }) {
  return function useImportSession(scope, initial) {
    const store = useMemo(() => getStore(scope, initial), [scope]);
    const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
    return { ...snapshot, setField: store.setField };
  };
}
