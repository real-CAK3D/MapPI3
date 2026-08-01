const CACHE_NAME = 'mappi3-field-shell-v1';
const SHELL_URLS = ['/', '/manifest.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_URLS).catch(() => undefined)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
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
