/* ServiceWaze service worker — offline-capable PWA shell + push notifications */
const VERSION = "sw-v2.1";
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/maskable-512.png",
  "/static/icons/icon-180.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // let external requests pass (news links etc.)

  // API calls: network-first, cache fallback (offline shows last data)
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then((c) => c || Response.error()))
    );
    return;
  }

  // Shell & static: cache-first, network fallback (update cache)
  e.respondWith(
    caches.match(req).then((cached) => {
      const fetched = fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
        return res;
      }).catch(() => cached);
      return cached || fetched;
    })
  );
});

/* ---- push notifications ---- */
self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) { data = { body: e.data ? e.data.text() : "" }; }
  const title = data.title || "ServiceWaze";
  const options = {
    body: data.body || "",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    data: { url: data.url || "/" },
    tag: data.tag || "servicewaze"
  };
  e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = e.notification.data && e.notification.data.url ? e.notification.data.url : "/";
  e.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ("focus" in client) { client.navigate(url); return client.focus(); }
      }
      return clients.openWindow(url);
    })
  );
});
