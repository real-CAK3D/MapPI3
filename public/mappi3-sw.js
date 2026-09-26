const CACHE_NAME = 'mappi3-field-shell-v3';
// Offline areas (map, satellite, terrain tiles and trail data) live in their own cache and are
// never cleared by an app update.
const AREA_CACHE = 'mappi3-areas-v1';
const TILE_HOSTS = /(^|\.)(basemap\.nationalmap\.gov|elevation-tiles-prod\.s3\.amazonaws\.com)$|^s3\.amazonaws\.com$/;
const SHELL_URLS = ['/', '/manifest.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_URLS).catch(() => undefined)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('mappi3-field-shell') && key !== CACHE_NAME).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  // Live Pi data must never be answered from cache: a stale /api/status or /api/gps would show
  // old sensor readings as current when the Pi is unreachable.
  const url = new URL(req.url);
  if (url.pathname.startsWith('/api/')) return;
  // Saved trail data for an offline area: cache only.
  if (url.origin === self.location.origin && url.pathname.startsWith('/offline-area/')) {
    event.respondWith(caches.open(AREA_CACHE).then(cache => cache.match(req.url)).then(hit => hit || new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } })));
    return;
  }
  // Map, satellite and terrain tiles: use a saved copy first so the area works with no signal.
  if (TILE_HOSTS.test(url.hostname) && (url.hostname !== 's3.amazonaws.com' || url.pathname.startsWith('/elevation-tiles-prod/'))) {
    event.respondWith(caches.open(AREA_CACHE).then(cache => cache.match(req.url)).then(hit => hit || fetch(req)));
    return;
  }
  event.respondWith(fetch(req).then(res => {
    const copy = res.clone();
    if (new URL(req.url).origin === self.location.origin) caches.open(CACHE_NAME).then(cache => cache.put(req, copy)).catch(() => undefined);
    return res;
  }).catch(() => caches.match(req).then(hit => hit || caches.match('/'))));
});
self.addEventListener('message', event => {
  const data = event.data || {};
  if (data.type === 'MAPPI3_NOTIFY') {
    event.waitUntil(self.registration.showNotification(data.title || 'MapPI3 Trail Alert', {
      body: data.body || data.message || 'Trail Buddy check-in.',
      tag: data.tag || 'mappi3-field-alert',
      badge: '/favicon.svg',
      icon: '/favicon.svg',
      data: data.data || { url: '/' },
      requireInteraction: Boolean(data.requireInteraction)
    }));
  }
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(clients.matchAll({ type:'window', includeUncontrolled:true }).then(list => {
    for (const client of list) {
      if ('focus' in client) { client.navigate(targetUrl).catch(() => undefined); return client.focus(); }
    }
    return clients.openWindow(targetUrl);
  }));
});
