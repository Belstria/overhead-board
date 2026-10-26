"""The relay's rules and the saves that broke before, checked against a running test relay (smoke.py runs them; on
their own: start tools/test/run_test_relay.py, then `py tools/test/flows.py --port 8096`).

- who gets the admin pages: only David's devices, at home; a device at home without a profile no more (relay 54)
- pages go packed and tagged: an unchanged page is a 304 (relay 54)
- settings round trip through /me, a save from another site refused (relay 54)
- favourites change one at a time, so two devices saving at once keep both (relay 54)
- where a sighting on the go was made is named and found by the search; the hangar; a league player's card (relay 63)
- the hangar's photos (relay 64)
- airline names from the airline list, filled in once for older sightings; Flightradar24's routes kept in the
  sightings, also from the cache at start (relay 68)
- in the app (browser_checks, with Playwright): a settings change made while the relay can't be reached waits on the
  phone, is sent again and reaches the profile; favourites show at once and go back when they can't be saved (1.64)
"""
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else int(os.environ.get("PORT") or 8096)
BASE = f"http://localhost:{PORT}"
AT_HOME = {"X-Forwarded-For": "192.168.1.50"}          # through a proxy on this computer, from a phone at home
OUTSIDE = {"Cf-Connecting-IP": "203.0.113.9"}           # through the tunnel


def call(path, cookie=None, headers=None, body=None, method=None):
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = "overhead=" + cookie
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
        h.setdefault("Origin", BASE)
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def checks():
    bad = []

    def expect(what, got, want):
        if got != want:
            bad.append(f"{what}: got {got}, expected {want}")

    # C1: the admin pages
    expect("/admin at home, no profile", call("/admin", headers=AT_HOME)[0], 403)
    expect("/admin at home, a guest", call("/admin", "test-device", AT_HOME)[0], 403)
    expect("/admin at home, David", call("/admin", "owner-device", AT_HOME)[0], 200)
    expect("/admin from outside, David", call("/admin", "owner-device", OUTSIDE)[0] in (403, 404), True)
    expect("/admin on the relay's own computer", call("/admin")[0], 200)
    expect("/status at home, no profile", call("/status", headers=AT_HOME)[0], 403)

    # packed and tagged pages
    st, h, body = call("/app/", "test-device", {"Accept-Encoding": "gzip"})
    expect("/app/ packed", h.get("Content-Encoding"), "gzip")
    expect("/app/ unpacks to a page", b"<html" in gzip.decompress(body)[:400].lower() if st == 200 else False, True)
    tag = h.get("ETag") or ""
    expect("/app/ has a tag", bool(tag), True)
    expect("/app/ unchanged is a 304", call("/app/", "test-device", {"If-None-Match": tag})[0], 304)
    expect("/app/ for another profile isn't that copy", call("/app/", "owner-device", {"If-None-Match": tag})[0], 200)

    # settings round trip, and a save from another site
    expect("/me save", call("/me", "test-device", body={"settings": {"theme": "classic", "units": "metric"}})[0], 204)
    st, _, b = call("/me", "test-device")
    expect("/me saved theme", (json.loads(b).get("settings") or {}).get("theme") if st == 200 else st, "classic")
    expect("/me save from another site", call("/me", "test-device", {"Origin": "https://evil.example"}, {"settings": {"theme": "frankfurt"}})[0], 403)
    st, _, b = call("/me", "test-device")
    expect("/me after the refused save", (json.loads(b).get("settings") or {}).get("theme") if st == 200 else st, "classic")

    # favourites, one change at a time
    call("/lists", "test-device", body={"fav": []})
    call("/lists", "test-device", body={"op": "add", "list": "fav", "item": {"k": "reg", "v": "OE-LBN", "n": "A321"}})
    st, _, b = call("/lists", "test-device", body={"op": "add", "list": "fav", "item": {"k": "reg", "v": "OE-LZA", "n": "A320"}})
    favs = [i["v"] for i in json.loads(b)["fav"]] if st == 200 else st
    expect("two favourites added one by one", favs, ["OE-LBN", "OE-LZA"])
    st, _, b = call("/lists", "test-device", body={"op": "remove", "list": "fav", "item": {"k": "reg", "v": "OE-LBN"}})
    expect("one removed", [i["v"] for i in json.loads(b)["fav"]] if st == 200 else st, ["OE-LZA"])
    call("/lists", "test-device", body={"fav": []})

    # the plane overhead now, for the Android widget (relay 56)
    st, _, b = call("/now", "test-device")
    expect("/now answers", st == 200 and "plane" in json.loads(b), True)
    expect("/now for strangers", call("/now")[0] in (401, 403), True)
    # the whole logbook searched (relay 55)
    st, _, b = call("/search?q=ZZ9ZZ", "test-device")
    expect("/search answers", (st, json.loads(b).get("rows") if st == 200 else None), (200, []))
    expect("/search for strangers", call("/search?q=A320")[0] in (401, 403), True)

    # relay 61: category words in the search, a category's top ten
    st, _, b = call("/search?q=passenger", "test-device")
    expect("a category word in the search", json.loads(b).get("category") if st == 200 else st, "passenger")
    st, _, b = call("/logbook/category?c=passenger", "test-device")
    expect("a category's top ten", st == 200 and isinstance(json.loads(b).get("types"), list), True)
    expect("an unknown category", call("/logbook/category?c=spaceship", "test-device")[0], 400)

    # the game (relay 59): only a phone on live location scores, within 8 km; Sky view's lock-on once per plane
    live = "?pl=live&pc=48.2085,16.3731&pr=15"
    call("/aircraft/48.2085/16.3731/25" + live, "test-device")
    call("/aircraft/48.2085/16.3731/25", "owner-device")
    st, _, b = call("/logbook", "test-device")
    g = json.loads(b).get("game", {}) if st == 200 else {}
    expect("live planes score", g.get("points", 0) > 0 and g.get("v") == 3, True)
    expect("the level", (g.get("level") or 0) >= 1 and bool(g.get("title")), True)
    expect("the best day, as the boards read it (relay 64)", (g.get("best") or {}).get("points", 0) > 0, True)
    st, _, b = call("/logbook", "owner-device")
    expect("a board without live location doesn't score", json.loads(b).get("game", {}).get("points") if st == 200 else st, 0)
    st, _, b = call("/sightings", "test-device")
    rows = json.loads(b) if st == 200 else []
    rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
    hx = next((e["hex"] for e in rows if "gp" in e), None)
    expect("a scored plane in today's list", bool(hx), True)
    if hx:
        st, _, b = call("/game/lockon", "test-device", body={"hex": hx})
        lk = json.loads(b) if st == 200 else {}
        expect("a lock-on pays at least 15", lk.get("bonus", 0) >= 15 and lk.get("combo") == 1, True)
        st, _, b = call("/game/lockon", "test-device", body={"hex": hx})
        expect("the same plane locked on twice", json.loads(b).get("why") if st == 200 else st, "done")
    expect("a lock-on from another site", call("/game/lockon", "test-device", {"Origin": "https://evil.example"}, {"hex": "abcdef"})[0] in (403, 429), True)
    st, _, b = call("/game/league", "test-device")
    lg = json.loads(b) if st == 200 else {}
    expect("the league has the live player", [r["name"] for r in lg.get("rows", []) if r.get("me")], ["Test"])
    expect("the league shows no places", "lat" in b.decode() or "place" in b.decode(), False)

    # relay 63: where a sighting on the go was made, named in the background and found by the search ("New guest":
    # nobody's home screen saw these planes first); the hangar; a league player's card
    call("/aircraft/48.2085/16.3731/25" + live, "new-device")
    st, _, b = call("/sightings", "new-device")
    rows = json.loads(b) if st == 200 else []
    rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
    expect("a sighting on the go keeps where the phone was", any(e.get("place") == "live" and e.get("at") == [48.21, 16.37] for e in rows), True)
    found = None
    for _ in range(15):
        st, _, b = call("/search?q=vienna", "new-device")
        found = next((p for r in (json.loads(b).get("rows", []) if st == 200 else []) for p in r.get("places", []) if p.get("k") == "live"), None)
        if found:
            break
        time.sleep(1)
    expect("a sighting on the go found by its town", (found or {}).get("n"), "Vienna")
    st, _, b = call("/search?q=austria", "new-device")
    expect("... and by its country", st == 200 and json.loads(b).get("total", 0) > 0, True)
    st, _, b = call("/game/hangar", "test-device")
    hg = json.loads(b) if st == 200 else {}
    expect("the hangar lists the types caught", bool(hg.get("types")) and all(t.get("code") and t.get("tier") for t in hg["types"]), True)
    expect("the hangar has the sets", len(hg.get("sets", [])), 9)
    expect("the hangar's types carry their photo (relay 64)", all("photo" in t and "thumb" in t for t in hg.get("types", [])), True)
    me_row = next((r for r in lg.get("rows", []) if r.get("me")), {})
    st, _, b = call("/game/player?id=" + str(me_row.get("id", "")), "test-device")
    pl = json.loads(b) if st == 200 else {}
    expect("a league player's card", (pl.get("name"), pl.get("level", 0) >= 1, isinstance(pl.get("trophies"), list)), ("Test", True, True))
    expect("the card shows no places", any(k in b.decode() for k in ('"lat"', '"lon"', '"at"', '"place"')), False)
    expect("an unknown player", call("/game/player?id=000000000000", "test-device")[0], 404)
    expect("a player's card for strangers", call("/game/player?id=x")[0] in (401, 403), True)

    # relay 68: airline names from the airline list for flights without a route, and Flightradar24's answers kept in
    # the sightings (the test relay starts with yesterday's EIN1XY, saved without a name, and its answer in the cache)
    st, _, b = call("/airlines?c=EIN,ZZZ", "test-device")
    expect("/airlines", json.loads(b) if st == 200 else st, {"EIN": ["EI", "Aer Lingus"], "ZZZ": None})
    expect("/airlines for strangers", call("/airlines?c=EIN")[0] in (401, 403), True)
    want = {"EIN6AB": ("Aer Lingus", "EI"), "LDM5AB": ("FR6203", "VIE", "PMI", "fr24", "Lauda Europe"),
            "DLH1234": ("VIE", "fr24")}
    got = {}
    for _ in range(30):
        call("/aircraft/48.2085/16.3731/25", "test-device")
        call("/sightings?api=1", "test-device")       # a board with Flightradar24 asks for the day's flights
        st, _, b = call("/sightings", "test-device")
        rows = json.loads(b) if st == 200 else []
        rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
        e = {r.get("callsign"): r for r in rows}
        c = lambda k: (e.get(k) or {}).get
        got = {"EIN6AB": (c("EIN6AB")("airlineName"), c("EIN6AB")("airlineIata")),
               "LDM5AB": (c("LDM5AB")("flightIata"), (c("LDM5AB")("from") or {}).get("code"), (c("LDM5AB")("to") or {}).get("code"),
                          c("LDM5AB")("routeSrc"), c("LDM5AB")("airlineName")),
               "DLH1234": ((c("DLH1234")("divertedTo") or {}).get("code"), c("DLH1234")("routeSrc"))}
        if got == want:
            break
        time.sleep(1)
    for k in want:
        expect(f"{k} in today's sightings (without Flightradar24's overlay)", got.get(k), want[k])
    st, _, b = call("/logbook.csv", "test-device")
    lines = b.decode("utf-8-sig").splitlines() if st == 200 else []
    row = lambda cs: next((ln.split(",") for ln in lines if f",{cs}," in ln), [])
    expect("yesterday's flight got its airline once, and its answer from the cache (CSV)", [row("EIN1XY")[i] for i in (4, 8, 9, 10)] if row("EIN1XY") else None,
           ["EI661", "Aer Lingus", "DUB", "VIE"])
    expect("a name it had stays", row("AUA9")[8] if row("AUA9") else None, "Austrian")
    expect("Flightradar24's flight number in the CSV", row("LDM5AB")[4] if row("LDM5AB") else None, "FR6203")
    # "New guest" has Flightradar24 off: its sighting of the same flight keeps the free route (it recorded LDM5AB on
    # the go above, before Flightradar24 answered)
    st, _, b = call("/sightings", "new-device")
    rows = json.loads(b) if st == 200 else []
    rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
    g = next((r for r in rows if r.get("callsign") == "LDM5AB"), {})
    expect("a profile with Flightradar24 off keeps its free route", (g.get("flightIata"), g.get("routeSrc")), ("OE215", None))
    st, _, b = call("/logbook", "test-device")
    expect("the logbook's airline", ((json.loads(b).get("airlines") or {}).get("EIN") or {}).get("name") if st == 200 else st, "Aer Lingus")

    for b_ in bad:
        print("flow:", b_)
    print("relay rules and saves hold" if not bad else f"{len(bad)} flow check(s) failed")
    return not bad


def browser_checks(browser):
    """The app's saves, in a browser. The app's code runs inside one function; a copy of the page with an eval inside
    it (window.__e) lets the checks call it."""
    bad = []
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_cookies([{"name": "overhead", "value": "test-device", "domain": "localhost", "path": "/"}])

    def hooked(route):
        r = route.fetch()
        t = r.text()
        i = t.rindex("})();")
        route.fulfill(response=r, body=t[:i] + "window.__e = c => eval(c);\n" + t[i:], headers={**r.headers, "content-encoding": "identity"})
    ctx.route("**/app/", hooked)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: bad.append(f"page error: {e}"))
    pg.goto(BASE + "/app/")
    pg.wait_for_timeout(4000)
    e = lambda code: pg.evaluate("c => __e(c)", code)          # noqa: E731
    relay_theme = lambda: pg.evaluate("fetch('/me').then(r => r.json()).then(j => (j.settings || {}).theme)")   # noqa: E731

    pg.route("**/me*", lambda route: route.abort())
    e("S = {...S, theme: 'frankfurt'}; saveSettings()")
    pg.wait_for_timeout(2500)
    if not e("meUnsynced()"):
        bad.append("a settings change the relay didn't get isn't marked Not synced")
    pg.unroute("**/me*")
    pg.wait_for_timeout(9000)
    if relay_theme() != "frankfurt" or e("!!mePending"):
        bad.append("a settings change wasn't sent again once the relay answered")
    pg.route("**/me*", lambda route: route.abort())
    e("S = {...S, theme: 'classic'}; saveSettings(); meFlush()")
    pg.wait_for_timeout(500)
    pg.unroute("**/me*")
    pg.reload()
    pg.wait_for_timeout(5000)
    if relay_theme() != "classic":
        bad.append("a settings change cut off by closing the app wasn't sent on the next start")

    pg.evaluate("fetch('/lists', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fav: [], hide: []})})")
    e("listsLoad(true)")
    pg.wait_for_timeout(800)
    e("listFlip('fav', {k: 'reg', v: 'OE-LBN', n: 'A'}); listFlip('fav', {k: 'reg', v: 'OE-LZA', n: 'B'})")
    if e("userLists.fav.map(i => i.v).join()") != "OE-LBN,OE-LZA":
        bad.append("favourites don't show at once")
    pg.wait_for_timeout(2000)
    if pg.evaluate("fetch('/lists').then(r => r.json()).then(j => j.fav.map(i => i.v).join())") != "OE-LBN,OE-LZA":
        bad.append("two quick favourites didn't both reach the relay")
    pg.route("**/lists*", lambda route: route.abort())
    if e("listFlip('fav', {k: 'reg', v: 'OE-LBN', n: 'A'}).then(() => 'saved', () => userLists.fav.map(i => i.v).join())") != "OE-LBN,OE-LZA":
        bad.append("a favourite that couldn't be saved didn't go back")
    pg.unroute("**/lists*")
    pg.evaluate("fetch('/lists', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fav: [], hide: []})})")
    ctx.close()
    for b_ in bad:
        print("flow:", b_)
    print("the app's saves hold" if not bad else f"{len(bad)} app save check(s) failed")
    return bad


if __name__ == "__main__":
    sys.exit(0 if checks() else 1)
