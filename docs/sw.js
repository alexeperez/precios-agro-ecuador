// Service worker: permite abrir la app sin conexión con los últimos datos vistos.
// Estrategia "red primero": siempre intenta traer datos frescos y, si no hay
// señal, usa la copia guardada.
const CACHE = "precios-agro-v1";

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["./", "index.html", "manifest.json", "icon.svg", "data/catalogo.json"])));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  // Los archivos propios se revalidan siempre, para ver los datos del día.
  const propio = new URL(e.request.url).origin === location.origin;
  e.respondWith(
    fetch(propio ? new Request(e.request.url, { cache: "no-cache" }) : e.request)
      .then(r => {
        if (r.ok) { const copia = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copia)); }
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});
