/* sw.js — SV Code Scanner service worker.
   1. Offline: cache-first for the app shell + decoder scripts.
   2. Share target: POST /share-receive (from OS share sheet) -> stash the
      image in a cache, redirect to /?shared; the page picks it up. */
"use strict";

const SHELL = "sv-shell-v2";
const SHARE = "sv-share-v1";
const CORE = [
  "/", "/index.html",
  "/js/svc.js", "/js/decoder.js", "/js/scanner.js", "/js/reveal.js",
  "/js/encoder.js", "/js/spv.js", "/js/anchor.js", "/js/miniwallet.js",
  "/manifest.webmanifest",
  "/icons/icon-192.png", "/icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys
        .filter((k) => ![SHELL, SHARE].includes(k))
        .map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // OS share sheet: image arrives here as multipart POST
  if (url.pathname === "/share-receive" && e.request.method === "POST") {
    e.respondWith((async () => {
      try {
        const form = await e.request.formData();
        const file = form.get("image");
        if (file && file.size) {
          const cache = await caches.open(SHARE);
          await cache.put("/__shared-image", new Response(file, {
            headers: { "Content-Type": file.type || "application/octet-stream" },
          }));
        }
      } catch (err) { /* fall through to the plain page */ }
      return Response.redirect("/?shared=1", 303);
    })());
    return;
  }

  if (e.request.method !== "GET") return;

  // cache-first for shell assets; network-first for everything else
  if (CORE.some((p) => url.pathname === p)) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(SHELL).then((c) => c.put(e.request, copy));
        return res;
      }))
    );
  } else {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res.ok && url.origin === location.origin) {
            const copy = res.clone();
            caches.open(SHELL).then((c) => c.put(e.request, copy));
          }
          return res;
        })
        .catch(() => caches.match(e.request))
    );
  }
});
