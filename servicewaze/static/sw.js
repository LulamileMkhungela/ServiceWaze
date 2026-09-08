/* ServiceWaze service worker v3
   - offline-first app shell (install, then run on 3G, 2G or nothing)
   - network-first API with last-known-good cache fallback
   - push notifications for the Prepare Window (before impact, not after) */
const VERSION = "sw-v3.2.0";
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/css/app.css?v=3.2.0",
  "/static/js/app.js?v=3.2.0",
  "/static/icons/icon-180.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/maskable-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VERSION)
      .then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // external (news links, maps) pass through

  // API: network first, cache fallback → offline shows the last good data
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((c) => c || Response.error()))
    );
    return;
  }

  // Shell: cache first, network update
  e.respondWith(
    caches.match(req).then((cached) => {
      const fetched = fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => cached);
      return cached || fetched;
    })
  );
});

/* ---------------- background flush ----------------
   The page queues writes in localStorage when signal dies. When the browser
   reports a connection again (or the OS fires a sync), we wake every open
   ServiceWaze tab so the queue drains even if the app is not in front. */
self.addEventListener("message", (e) => {
  if (e.data === "flush-queue") {
    e.waitUntil(self.clients.matchAll({ includeUncontrolled: true }).then((list) => {
      list.forEach((c) => c.postMessage({ type: "flush-queue" }));
    }));
  }
});

self.addEventListener("sync", (e) => {
  if (e.tag === "sw-queue") {
    e.waitUntil(self.clients.matchAll({ includeUncontrolled: true }).then((list) => {
      list.forEach((c) => c.postMessage({ type: "flush-queue" }));
    }));
  }
});

/* ---------------- push ---------------- */
self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) { data = { body: e.data ? e.data.text() : "" }; }
  const title = data.title || "ServiceWaze";
  const options = {
    body: data.body || "",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    tag: data.tag || "servicewaze",
    renotify: true,
    data: { url: data.url || "/" },
    actions: [{ action: "prepare", title: "Open prepare list" }],
    vibrate: [80, 40, 80],
  };
  e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || "/?tab=prepare";
  e.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) if ("focus" in c) { c.navigate(target); return c.focus(); }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
