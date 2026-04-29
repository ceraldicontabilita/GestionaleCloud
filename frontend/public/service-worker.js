/* Ceraldi ERP — Service Worker minimale.
 *
 * Strategia prudente:
 *   - NIENTE cache di risposte API (/api/*) — sono dati in continua modifica
 *   - Cache statica "stale-while-revalidate" per asset Vite (/assets/*, /logo-*.png)
 *   - Navigate requests: network-first con fallback /index.html (per routing SPA offline)
 *   - Auto-update: al bump della CACHE_VERSION, il vecchio cache viene purgato
 */

const CACHE_VERSION = 'ceraldi-erp-v2';
const STATIC_CACHE = `${CACHE_VERSION}-static`;

// Asset base da precachare al primo install
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/logo-ceraldi.png',
  '/logo_ceraldi.png',
  '/logo_ceraldi_white.png',
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) =>
      cache.addAll(PRECACHE_URLS).catch(() => {})
    )
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => !k.startsWith(CACHE_VERSION))
          .map((k) => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Niente cache per /api (dati real-time)
  if (url.pathname.startsWith('/api/')) return;

  // Niente cache per terze parti (posthog, emergent-badge, …)
  if (url.origin !== self.location.origin) return;

  // Navigate request (index.html fallback per routing SPA offline)
  if (req.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const networkResp = await fetch(req);
          const cache = await caches.open(STATIC_CACHE);
          cache.put('/index.html', networkResp.clone()).catch(() => {});
          return networkResp;
        } catch {
          const cache = await caches.open(STATIC_CACHE);
          return (await cache.match('/index.html')) || Response.error();
        }
      })()
    );
    return;
  }

  // Asset Vite o statici: stale-while-revalidate
  if (
    url.pathname.startsWith('/assets/') ||
    /\.(png|jpg|jpeg|svg|webp|ico|woff2?|css|js)$/i.test(url.pathname)
  ) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(STATIC_CACHE);
        const cached = await cache.match(req);
        const networkPromise = fetch(req)
          .then((resp) => {
            if (resp && resp.ok) cache.put(req, resp.clone()).catch(() => {});
            return resp;
          })
          .catch(() => cached);
        return cached || networkPromise;
      })()
    );
  }
});
