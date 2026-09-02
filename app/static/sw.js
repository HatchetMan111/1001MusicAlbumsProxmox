/* AlbumsDashboard – Service Worker (PWA)
 * Offline-Shell: App-Assets (CSS/JS/Icons/Manifest) werden gecacht, damit
 * die App einmal besucht auch ohne Server/Netz startet (LXC down, WLAN weg).
 * Dynamische Seiten (/) werden NIE aus dem Cache ausgeliefert – der
 * Hör-Fortschritt ist Nutzerdaten und muss immer frisch sein (no-store).
 */
var CACHE = "albumsdashboard-v1";
var ASSETS = [
  "/static/style.css?v=4",
  "/static/app.js?v=4",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/manifest.webmanifest",
  "/gehoert"  /* Shell fuer offline Navigation zur Gehoert-Rubrik */
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      /* addAll ist atomar; wenn ein Asset fehlt (Server down), failt die
       * Installation still und der alte SW bleibt aktiv – genau richtig. */
      return cache.addAll(ASSETS).catch(function () { /* siehe fetch */ });
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE; })
            .map(function (k) { return caches.delete(k); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);

  /* Nur eigene Herkunft; alles andere (iTunes-Cover!) durchreichen. */
  if (url.origin !== self.location.origin) return;

  /* HTML-/ dynamische Seiten: immer Netzwerk zuerst (Fortschritt frisch),
   * offline dann die gecachte Shell als Fallback. */
  if (event.request.mode === "navigate" || !url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(event.request).catch(function () {
        return caches.match(event.request).then(function (hit) {
          if (hit) return hit;
          /* Navigations-Ziel nicht im Cache: versuche Startseite/Shell. */
          return caches.match("/") || caches.match("/gehoert");
        });
      })
    );
    return;
  }

  /* Statische Assets: Cache-first (schnell, versioniert per ?v=). */
  event.respondWith(
    caches.match(event.request).then(function (hit) {
      return hit || fetch(event.request).then(function (res) {
        if (res.ok) {
          var copy = res.clone();
          caches.open(CACHE).then(function (cache) { cache.put(event.request, copy); });
        }
        return res;
      });
    })
  );
});
