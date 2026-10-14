// Fallblatt's service worker: shows the relay's push notifications (the evening summary and "worth going to the
// window") and opens the app when one is tapped. It caches nothing: the app always comes fresh from the relay.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = {body: e.data ? e.data.text() : ""}; }
  e.waitUntil(self.registration.showNotification(d.title || "Fallblatt", {
    body: d.body || "", tag: d.tag || undefined, renotify: !!d.tag,
    // the badge is the status bar's little icon: Android uses only its shape, so it is the plane alone (make_badge.py)
    icon: "icon-192.png", badge: "badge-96.png", data: {url: d.url || "/app/"}
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/app/";
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(list => {
    for (const w of list) if (w.url.includes("/app/") && "focus" in w) { if ("navigate" in w) w.navigate(url); return w.focus(); }
    return self.clients.openWindow(url);
  }));
});
