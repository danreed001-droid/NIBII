// Top 5 Strongest as an installed app: open the latest page when online, the last one seen when offline.
const CACHE = 'top5-v2';
const SHELL = ['scanner.html', 'manifest.webmanifest', 'img/app-192.png', 'img/app-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  const shell = SHELL.some((p) => url.pathname.endsWith('/' + p));
  if (req.mode !== 'navigate' && !shell) return;      // everything else goes straight to the network
  // pages are checked with the server every time (GitHub Pages lets browsers keep them 10 minutes otherwise)
  e.respondWith(fetch(req.mode === 'navigate' ? new Request(req.url, { cache: 'no-cache', credentials: 'same-origin' }) : req)
    .then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(url.pathname, copy));
      }
      return res;
    })
    .catch(() => caches.match(url.pathname).then((hit) => hit || caches.match(new URL('scanner.html', self.registration.scope).pathname))));
});
