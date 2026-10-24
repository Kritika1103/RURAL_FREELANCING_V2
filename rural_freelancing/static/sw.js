/* Minimal service worker: makes the site installable and shows an offline page.
   It never caches HTML pages (they contain logged-in user data) - only static assets. */
const CACHE = "rural-static-v1";
const PRECACHE = ["/offline", "/static/css/style.css", "/static/js/main.js", "/static/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (req.mode === "navigate") {                       // pages: network only, offline page as fallback
    e.respondWith(fetch(req).catch(() => caches.match("/offline")));
  } else if (url.pathname.startsWith("/static/") && !url.pathname.startsWith("/static/uploads/")) {
    e.respondWith(fetch(req).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return r; })
      .catch(() => caches.match(req)));                // static assets: network first, cache when offline
  }
});
