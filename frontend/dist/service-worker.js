/* Ceraldi ERP — KILL SWITCH service worker.
 *
 * Questo SW non fa cache. Il suo unico scopo è:
 *   1. Disinstallare se stesso (unregister)
 *   2. Cancellare TUTTE le cache (anche quelle del SW v1/v2/v3 precedenti)
 *   3. Forzare reload di tutti i client che lo controllavano
 *
 * Effetto: qualsiasi dispositivo con SW vecchio viene "ripulito" al primo
 * refresh e da quel momento il sito gira come SPA pura, senza SW di mezzo.
 */

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      } catch {}
      try {
        await self.registration.unregister();
      } catch {}
      try {
        const wins = await self.clients.matchAll({ type: 'window' });
        wins.forEach((c) => { try { c.navigate(c.url); } catch {} });
      } catch {}
    })()
  );
});

// Pass-through totale: nessun intercept, fetch va al network normale
self.addEventListener('fetch', () => {});
