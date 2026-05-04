const CACHE = 'finanzen-v2';
const ASSETS = ['/static/style.css', '/static/script.js', '/static/form.js', '/static/lancamentos.js', '/static/brand/logo-finanzen.svg', '/static/brand/favicon-finanzen.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});

self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {};
  const title = data.title || 'FinanZen';
  const options = {
    body: data.body || '',
    icon: '/static/brand/favicon-finanzen.svg',
    badge: '/static/brand/favicon-finanzen.svg',
    data: { url: data.url || '/dashboard' }
  };
  e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || '/dashboard';
  e.waitUntil(clients.matchAll({ type: 'window' }).then(list => {
    for (const client of list) {
      if (client.url.includes(url) && 'focus' in client) return client.focus();
    }
    return clients.openWindow(url);
  }));
});
