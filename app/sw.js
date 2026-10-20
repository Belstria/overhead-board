// Fallblatt's service worker: shows the relay's push notifications (the evening summary and "worth going to the
// window") and opens the app when one is tapped; the light version (/light/) uses it too. It keeps the translations and
// the sounds (i18n.js, sounds.js, 1.53.1) and, since 1.64, the last copy of the app itself for when the relay can't be
// reached.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

// The app comes from the relay when it answers within 3 s (it keeps loading in the background and refreshes the copy).
// Otherwise the last copy opens, marked (OVERHEAD_OFFLINE: when it was kept) so the page says it isn't live; it shows
// the last known board (snapLoad) and keeps trying. A refusal (signed out: the private page) forgets the copy.
const SHELL = "fallblatt-shell";
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.mode !== "navigate" || e.request.method !== "GET" || u.origin !== location.origin || !/\/app\/$/.test(u.pathname)) return;
  e.respondWith((async () => {
    const c = await caches.open(SHELL), key = u.origin + u.pathname;
    const net = fetch(e.request).then(async r => {
      if (r.ok && (r.headers.get("Content-Type") || "").startsWith("text/html")) {
        const copy = new Response(await r.clone().text(), {headers: {"Content-Type": "text/html; charset=utf-8", "X-Kept": String(Date.now())}});
        await c.put(key, copy);
      } else if (r.status === 403 || r.status === 401) await c.delete(key);
      return r;
    });
    e.waitUntil(net.catch(() => {}));
    const late = new Promise(ok => setTimeout(ok, 3000));
    const first = await Promise.race([net.catch(() => null), late.then(() => null)]);
    if (first && first.status < 500) return first;
    const kept = await c.match(key);
    if (!kept) return first || net;                 // nothing kept yet: wait for the relay after all
    const at = +kept.headers.get("X-Kept") || Date.now();
    const page = (await kept.text()).replace("<head>", `<head><script>window.OVERHEAD_OFFLINE = ${at};</script>`);
    return new Response(page, {headers: {"Content-Type": "text/html; charset=utf-8"}});
  })());
});

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
