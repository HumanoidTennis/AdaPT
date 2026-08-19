// Service Worker — cache-first for small homepage assets only.
// The MuJoCo/ONNX viewer is versioned by Vite and must always bypass this
// service worker; otherwise ordinary browser refresh can keep serving an old
// viewer bundle while hard refresh appears correct.
const CACHE_NAME = 'omnicontact-site-v20260604-stackbox-nair-new-pushstack-final-h264';

// Assets to pre-cache on install (critical CSS/JS)
const PRECACHE = [
  'static/css/bulma.min.css',
  'static/css/index.css',
  'static/js/index.js',
  'static/images/omnicontact-overview.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Clean up old caches
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET, cross-origin, and chrome-extension requests
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (
    url.pathname.includes('/static/humanoid-policy-viewer/') ||
    url.pathname.endsWith('/policy-viewer.html') ||
    url.pathname.endsWith('/sw.js')
  ) {
    event.respondWith(fetch(event.request, { cache: 'no-store' }));
    return;
  }

  // HTML pages: network-first (always get fresh content)
  if (event.request.mode === 'navigate' || event.request.destination === 'document') {
    event.respondWith(
      fetch(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets (CSS, JS, fonts, images): cache-first
  const isStatic =
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.woff2') ||
    url.pathname.endsWith('.woff') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.jpg') ||
    url.pathname.endsWith('.svg');

  if (isStatic) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }
});
