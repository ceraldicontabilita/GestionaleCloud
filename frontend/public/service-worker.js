/* Ceraldi ERP — Service Worker minimo per installabilità PWA.
 *
 * NON fa cache di nulla: ogni richiesta va sempre in rete (pass-through).
 * Un SW precedente qui faceva cache aggressiva e serviva bundle JS vecchi
 * dopo un deploy (bug stale-cache) — per questo era stato sostituito da un
 * kill-switch che si disinstallava da solo. Questa versione esiste solo
 * per soddisfare il criterio di installabilità di Chrome/Android (serve un
 * SW registrato con un handler 'fetch'), senza correre lo stesso rischio:
 * zero caching, quindi zero possibilità di servire contenuti stale.
 */

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Nessun intercept reale: lascia che ogni richiesta vada normalmente in rete.
self.addEventListener('fetch', () => {});
