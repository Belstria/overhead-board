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
- the owner's Relay plate (/relayinfo): David only, also from outside; another profile or a stranger no (relay 69);
  only David's page says owner, /pageversion (a page built without a profile) answers, a saved "</script>" stays escaped
- live location: a request with a stale or missing fix (relay 72: or none sent) records nothing, scores nothing and starts no gap filler; a
  fresh one does; a callsign of "@"s is none, also in sightings saved before (relay 70)
- Recent points: today's awards per plane (the first score, a close-pass top-up, the lock-on), the profile's own only (relay 71)
- Sky view's reports: David's only, from this site, kept up to a cap (2 in the test relay), then rate-limited (relay 72)
- in the app (browser_checks, with Playwright): a settings change made while the relay can't be reached waits on the
  phone, is sent again and reaches the profile; favourites show at once and go back when they can't be saved (1.64);
  the Remarks by style: Overhead white and only a delay over 30 min, Airport amber with ON TIME and the gate (1.88)
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
    # relay 69: the page knows the owner (and only the owner); without a profile (the update check) it still builds,
    # and what a profile saved stays escaped inside the page's script
    st, _, b = call("/pageversion?p=test", "test-device")
    expect("/pageversion", (st, bool(json.loads(b).get("v")) if st == 200 else None), (200, True))
    page = lambda ck: gzip.decompress(call("/app/", ck, {"Accept-Encoding": "gzip"})[2]).decode()   # noqa: E731
    guest = lambda ck: page(ck).split("window.OVERHEAD_GUEST=", 1)[-1].split(";window.OVERHEAD_PAGE_DATE", 1)[0]   # noqa: E731
    expect("the owner's page says owner", '"owner": true' in guest("owner-device"), True)
    expect("another profile's page doesn't", '"owner"' in guest("test-device"), False)
    st, _, b = call("/me", "test-device")
    was = (json.loads(b).get("settings") or {}).get("place") if st == 200 else None
    call("/me", "test-device", body={"settings": {"place": "X</script><b>y"}})
    html = page("test-device")
    expect("a saved </script> stays escaped", ("X</script><b>y" in html, "X\\u003c/script>\\u003cb>y" in html), (False, True))
    call("/me", "test-device", body={"settings": {"place": was or "Vienna"}})

    # relay 69: the owner's Relay plate, also away from home; nobody else
    st, _, b = call("/relayinfo", "owner-device", OUTSIDE)
    ri = json.loads(b) if st == 200 else {}
    expect("/relayinfo for David from outside", (st, [s.get("role") for s in ri.get("sources", [])][:1], sorted(ri)),
           (200, ["first"], ["backup", "fr24", "screens", "sources", "up", "version"]))
    expect("/relayinfo shows no addresses", any(k in b.decode() for k in ('"ip"', '"host"', '"ua"', "192.168.")), False)
    expect("/relayinfo for another profile", call("/relayinfo", "test-device", AT_HOME)[0], 403)
    expect("/relayinfo for strangers", call("/relayinfo")[0] in (401, 403), True)
    expect("/relayinfo for strangers at home", call("/relayinfo", headers=AT_HOME)[0] in (401, 403), True)

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
    live = "?pl=live&pc=48.2085,16.3731&pr=15&fix=5"   # relay 72: a live request without fix is stale
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
    # relay 71: Recent points, today's awards per plane (the first score, a close-pass top-up, the lock-on); the
    # profile's own only
    today = lambda ck: json.loads(call("/game/today", ck)[2])     # noqa: E731
    td = today("test-device")
    row = next((r for r in td.get("rows", []) if r.get("hex") == hx), {})
    kinds = [a.get("k") for a in row.get("aw", [])]
    expect("Recent points: the first score and the lock-on", ("first" in kinds, "lock" in kinds), (True, True))
    lock = next((a for a in row.get("aw", []) if a.get("k") == "lock"), {})
    expect("... the lock-on's share and points", (lock.get("pct"), lock.get("p") == row.get("lock")), (0.25, True))
    expect("... the day's total", td.get("today", 0) > 0 and td.get("planes", 0) >= len(td.get("rows", [])) > 0, True)
    far_one = next((r for r in td.get("rows", []) if (r.get("km") or 0) > 4.5 and len(r.get("aw", [])) == 1), None)
    expect("a scored plane more than 4.5 km away", bool(far_one), True)
    if far_one:
        st, _, b = call("/aircraft/48.2085/16.3731/25", "test-device")
        ac = next((a for a in json.loads(b).get("ac", []) if a.get("hex") == far_one["hex"]), None) if st == 200 else None
        if ac:
            at = f"{ac['lat']:.4f}/{ac['lon']:.4f}"
            call(f"/aircraft/{at}/25?pl=live&pc={at.replace('/', ',')}&pr=15&fix=5", "test-device")
            row = next((r for r in today("test-device").get("rows", []) if r.get("hex") == far_one["hex"]), {})
            close = next((a for a in row.get("aw", []) if a.get("k") == "close"), {})
            expect("a close pass tops up its plane", (close.get("p", 0) > 0, (close.get("d") or 99) <= 1.5), (True, True))
            expect("... and the plane's total follows", sum(a["p"] for a in row.get("aw", []) if a["k"] != "lock"), row.get("gp"))
    expect("Recent points for another profile", today("owner-device").get("rows"), [])
    expect("Recent points for strangers", call("/game/today")[0] in (401, 403), True)
    expect("a lock-on from another site", call("/game/lockon", "test-device", {"Origin": "https://evil.example"}, {"hex": "abcdef"})[0] in (403, 429), True)
    # Sky view's reports (relay 72)
    rep = {"v": 1, "gap": 3.2, "lat": 48.2, "readings": [[0, 1.5, 2.5]]}
    expect("a Sky view report from another profile", call("/skyreport", "test-device", OUTSIDE, rep)[0], 403)
    expect("a Sky view report from a stranger", call("/skyreport", None, OUTSIDE, rep)[0] in (401, 403), True)
    expect("a Sky view report from another site", call("/skyreport", "owner-device", {**OUTSIDE, "Origin": "https://evil.example"}, rep)[0], 403)
    kept = [json.loads(b).get("kept") if st == 200 else st for st, _, b in (call("/skyreport", "owner-device", OUTSIDE, rep) for _ in range(3))]
    expect("Sky view reports kept up to the cap", kept, [1, 2, 2])
    expect("a fourth Sky view report at once", call("/skyreport", "owner-device", OUTSIDE, rep)[0], 429)
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

    # relay 70: a live position counts only while the screen's fix is fresh (&fix=seconds, -1: none yet). David's phone
    # asks around a place far from home: stale, it records nothing and starts no gap filler; fresh, it does both
    far = "/aircraft/41.39/2.17/25?pl=live&pc=41.3900,2.1700&pr=15"

    def live_rows():
        st, _, b = call("/sightings", "owner-device")
        rows = json.loads(b) if st == 200 else []
        return [e for e in (rows.get("entries", rows) if isinstance(rows, dict) else rows) if e.get("place") == "live"]
    for fix in ("-1", "301", "x", None):        # relay 72: no fix at all (an old cached app) is stale too
        st, h, _ = call(far + ("&fix=" + fix if fix else ""), "owner-device")
        expect(f"a live request with a stale fix ({fix}) starts no gap filler", (st, h.get("X-Relay-Fill")), (200, None))
    expect("... and records no live sightings", len(live_rows()), 0)
    st, _, b = call("/logbook", "owner-device")
    expect("... and scores nothing", json.loads(b).get("game", {}).get("points") if st == 200 else st, 0)
    st, h, _ = call(far + "&fix=20", "owner-device")
    expect("a live request with a fresh fix starts the gap filler", h.get("X-Relay-Fill") is not None, True)
    expect("... and records live sightings", len(live_rows()) > 0, True)
    st, _, b = call("/logbook", "owner-device")
    expect("... that score", (json.loads(b).get("game", {}).get("points") or 0) > 0 if st == 200 else st, True)

    # relay 70: the sources' "@@@@@@@@" (no callsign) is no callsign: in the answer, today's sightings, and saved ones
    st, _, b = call("/aircraft/48.2085/16.3731/25", "test-device")
    ac = next((a for a in json.loads(b).get("ac", []) if a.get("hex") == "ae0412"), None) if st == 200 else None
    expect("a plane without a callsign in the positions", (ac or {}).get("flight", "missing"), "")
    st, _, b = call("/sightings", "test-device")
    rows = json.loads(b) if st == 200 else []
    rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
    expect("... and in today's sightings", next((e.get("callsign") for e in rows if e.get("hex") == "ae0412"), "missing"), "")
    st, _, b = call("/logbook.csv", "test-device")
    old = next((ln.split(",") for ln in (b.decode("utf-8-sig").splitlines() if st == 200 else []) if ",TEST-AT," in ln), None)
    expect("a saved one cleaned at start (CSV callsign, flight)", old[3:5] if old else None, ["", ""])

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

    # 1.88: the Remarks in the Overhead style are white and only name a delay over 30 minutes; the Airport style keeps
    # them amber with ON TIME, every delay and the gate
    e("window.__tf = timesFor; window.__md = S.mode; timesFor = () => window.__t")
    inf = "{from: {code: 'VIE'}, to: {code: 'LHR'}}"
    got = {}
    for mode in ("overhead", "airport"):
        for delay in (45, 10, 0):
            got[mode, delay] = e(f"S.mode = '{mode}'; window.__t = {{kind: 'dep', delay: {delay}, gate: 'C35'}}; vieLines({inf}).join('|')")
        got[mode] = e(f"S.mode = '{mode}'; renderFeatured(); fields.seen.style || 'white'")
    e("timesFor = window.__tf; S.mode = window.__md; renderFeatured()")
    want = {("overhead", 45): "DELAY 45 MIN", ("overhead", 10): "", ("overhead", 0): "", "overhead": "white",
            ("airport", 45): "DELAY 45 MIN|GATE C35", ("airport", 10): "DELAY 10 MIN|GATE C35", ("airport", 0): "ON TIME|GATE C35", "airport": "amber"}
    for k, v in want.items():
        if got[k] != v:
            bad.append(f"Remarks {k}: got {got[k]!r}, expected {v!r}")
    ctx.close()
    for b_ in bad:
        print("flow:", b_)
    print("the app's saves hold" if not bad else f"{len(bad)} app save check(s) failed")
    return bad


if __name__ == "__main__":
    sys.exit(0 if checks() else 1)
