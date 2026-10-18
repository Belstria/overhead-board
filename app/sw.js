// Fallblatt's service worker: shows the relay's push notifications (the evening summary and "worth going to the
// window") and opens the app when one is tapped; the light version (/light/) uses it too. The app itself always comes
// fresh from the relay; only the translations and the sounds (i18n.js, sounds.js, 1.53.1) are kept here.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

// The app names them with their version (i18n.js?v=...; tools/assets.py), so a copy kept here is right for good and a
// new version has a new address: it is fetched once and replaces the older copy. Then the app opens with them on a poor
// signal; without them it still works (English texts, synthesised sounds).
const KEEP = "fallblatt-files";
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || !/\/(i18n|sounds)\.js$/.test(u.pathname) || !u.searchParams.get("v")) return;
  e.respondWith(caches.open(KEEP).then(async c => {
    const hit = await c.match(e.request);
    if (hit) return hit;
    const r = await fetch(e.request);
    if (r.ok) {
      for (const old of await c.keys()) if (new URL(old.url).pathname === u.pathname) await c.delete(old);
      await c.put(e.request, r.clone());
    }
    return r;
  }));
});

// One notification at a time, always under the same tag: a new one replaces the last (and still rings). With several
// at once Android groups them under a summary that shows its own icon (overlapping squares) instead of the plane.
// While the app is open and in front, the page plays its own chime (the airport bell for special planes) and the
// notification stays silent.
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = {body: e.data ? e.data.text() : ""}; }
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    const front = d.kind ? wins.find(w => w.visibilityState === "visible" && /\/(app|light)\//.test(w.url)) : null;
    if (front) front.postMessage({type: "bell", kind: d.kind});
    for (const n of await self.registration.getNotifications()) n.close();
    await self.registration.showNotification(d.title || "Fallblatt", {
      body: d.body || "", tag: "fallblatt", renotify: true, silent: !!front,
      // the badge is the status bar's little icon: Android uses only its shape, so it is the plane alone (make_badge.py)
      icon: "icon-192.png", badge: "badge-96.png", data: {url: d.url || "/app/"}
    });
  })());
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/app/";
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(list => {
    for (const w of list) if (/\/(app|light)\//.test(w.url) && "focus" in w) { if ("navigate" in w) w.navigate(url); return w.focus(); }
    return self.clients.openWindow(url);
  }));
});
