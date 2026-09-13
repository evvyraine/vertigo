// Minimal service worker for Vertigo. It exists so the app is installable and
// shows a friendly page when the network is gone; Streamlit's live traffic is
// never cached.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    fetch(event.request).catch(
      () =>
        new Response(
          "<!doctype html><meta charset=utf-8><title>Offline</title>" +
            "<body style='font-family:system-ui;background:#17181c;color:#e7e9ec;" +
            "display:grid;place-items:center;height:100vh;margin:0'>" +
            "<p>Vertigo is offline.</p></body>",
          { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
        )
    )
  );
});
