const CACHE = 'finanzen-v1';
const ASSETS = ['/static/style.css', '/static/script.js', '/static/form.js', '/static/lancamentos.js', '/static/brand/logo-finanzen.svg', '/static/brand/favicon-finanzen.svg'];

self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))));
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
