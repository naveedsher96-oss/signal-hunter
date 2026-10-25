// Signal Hunter service worker.
// Caches only the install icons/manifest - everything else (pages, API, lead
// data) always goes to the network so scans are never served stale.
const CACHE = "sh-v1";
const STATIC = ["/manifest.json", "/pwa/icon-180.png", "/pwa/icon-192.png",
                "/pwa/icon-512.png", "/pwa/icon-512-maskable.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => clients.claim()));
});

self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  if (STATIC.includes(u.pathname)) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
