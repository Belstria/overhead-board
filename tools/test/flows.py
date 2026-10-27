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
- the game's rules since relay 76 (to-do #127), on the relay's functions: the passive tenth and the limits per rarity, the
  scan's full points on top without a limit (relay 79), extras only with scans and promised on the passive award
  ("can"), the daily streak (a missed day, the Monday reset), rule 1's planes not priced again; over HTTP: the rules
  and limits in /game/me, "can" and the scan paying it, Recent points adding up, the league's week, the hangar on any
  sighting (a board at home) with how often the game scored each type and (relay 79) scanned it, counted back first
- Sky view's reports: David's only, from this site, kept up to a cap (2 in the test relay), then rate-limited (relay 72)
- a plane's own photo from Planespotters.net (the fake's): profiles only, asked once and kept, by hex only with the same
  registration on the photo, not kept by the browser; /photo doesn't pass their photos on (relay 73)
- the cards' facts (the fake Wikipedia and Wikidata): a model's infobox and specs (a table or the template), an airline by
  its ICAO code, an airport by its IATA code, cleaned; asked once and kept; none for a missing page or a dissolved
  airline; profiles only. What a profile spotted of an airline, a model or an airport (relay 74)
- Spotted today by place: a saved place at the profile's own spot and the profile's place share one list, each pass
  once, with the same day's numbers; a saved place elsewhere keeps its own (relay 75, to-do #121)
- in the app (browser_checks, with Playwright): a settings change made while the relay can't be reached waits on the
  phone, is sent again and reaches the profile; favourites show at once and go back when they can't be saved (1.64);
  the Remarks by style: Overhead white and only a delay over 30 min, Airport amber with ON TIME and the gate (1.88);
  a Planespotters photo first, credited and linked, never for the share picture, none of another aircraft (1.93)
"""
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
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


def game_rule_checks(expect):
    """Relay 76 (to-do #127): the game's rules on a made-up profile, straight on the relay's functions (no relay needed):
    the passive tenth and the limits per rarity, the scan's full points on top without a limit (relay 79; a top-up in
    relay 76), extras only with scans and what a scan would add on the passive award ("can"), the daily streak (days in a
    row, a missed day, the Monday reset), rule 1's planes kept as they were."""
    import tempfile
    import types
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "relay"))
    import serve
    serve.ARGS = serve.ARGS or types.SimpleNamespace(verbose=False)
    day = ["2026-10-28"]                                  # a Wednesday
    real_day = serve.board_day
    serve.board_day = lambda t=None: day[0]
    try:
        sp = serve.Spot(Path(tempfile.mkdtemp(prefix="fb-rules-")), None, 15)
        sp.ensure_day()
        now = serve.time.time()
        n = [0]

        def plane(tier, tc, cs, km=5.0):
            n[0] += 1
            e = {"id": f"x{n[0]}", "hex": f"{n[0]:06x}", "ts": int(now * 1000) + n[0], "typeCode": tc, "callsign": cs,
                 "tier": tier, "liveMin": km, "liveSeen": now}
            sp.entries.insert(0, e)
            sp.by_hex[e["hex"]] = e
            return e

        def note(e):
            with serve._data_lock:
                return serve.game_note(sp, e)

        g = serve.game_book(sp.book())
        commons = [plane("common", "A320", f"AUA{100 + i}") for i in range(52)]
        for e in commons:
            note(e)
        expect("passive: a tenth of a common's points, 50 a day", [e["gp"] for e in commons[:50]], [1] * 50)
        expect("... the 51st and 52nd get nothing", [e["gp"] for e in commons[50:]], [0, 0])
        expect("... only the first over the limit pops up", [(e["ga"][-1]["k"], e["ga"][-1]["first"]) for e in commons[50:]],
               [("limit", True), ("limit", False)])
        rare = plane("rare", "E195", "BCY777")
        note(rare)
        legs = [plane("legendary", "A388", f"UAE{i}") for i in range(4)]
        for e in legs:
            note(e)
        expect("passive by rarity: rare 10, special 50 up to 3", [rare["gp"]] + [e["gp"] for e in legs], [10, 50, 50, 50, 0])
        expect("the day's points and limits", (g["days"][day[0]], serve._game_limits(g, day[0])),
               (50 + 10 + 150, {"common": 52, "rare": 1, "legendary": 4}))
        expect("extras only with scans: passive awards", sorted({a["k"] for e in sp.entries for a in e["ga"]}), ["limit", "pass"])
        commons[1]["liveMin"] = 1.0
        expect("a plane comes closer: not priced again", (note(commons[1]), commons[1]["gp"], len(commons[1]["ga"])), (True, 1, 1))

        def scan(e):
            r = serve.game_lockon(sp, e["hex"])
            return r.get("bonus"), [(x["k"], x["p"]) for x in r.get("lines", [])] or r.get("why")

        expect("a passive award says what a scan would add (relay 79: can)", (commons[0]["ga"][0].get("can"), commons[51]["ga"][0].get("can")),
               ({"type": 50, "airline": 25}, {"type": 50, "airline": 25}))
        expect("a scan gives a common its full 10 on top of its 1, with a new type, airline and day 1 of the streak (relay 79)", scan(commons[0]),
               (10 + 50 + 25 + 25, [("scan", 10), ("new", 50), ("new", 25), ("streak", 25)]))
        again = plane("common", "A320", "AUA555")
        note(again)
        expect("... after it, a plane of that type and airline promises nothing more", again["ga"][0].get("can"), None)
        expect("the same plane scanned again", scan(commons[0]), (0, "done"))
        expect("a common past the limit: the full 10 from a scan, nothing new", scan(commons[51]), (10, [("scan", 10)]))
        expect("scans have no limit", [scan(e)[0] for e in legs], [500 + 50 + 25, 500, 500, 500])
        expect("the scans counted per type (relay 79; from the start here)", g.get("scanTypes"), None)
        far = plane("common", "A320", "AUA999", km=12.0)
        note(far)
        expect("a plane beyond 10 km can't be scanned", scan(far), (0, "far"))

        def next_day(d, scans=True):
            day[0] = d
            sp.ensure_day()
            e = plane("uncommon", "B738", "RYR1")
            note(e)
            return scan(e)[1][-1] if scans else None

        expect("the streak's second day", next_day("2026-10-29"), ("streak", 50))
        next_day("2026-10-30", scans=False)
        expect("a day without a scan: back to day 1", next_day("2026-10-31"), ("streak", 25))
        expect("... then day 2", next_day("2026-11-01"), ("streak", 50))
        expect("Monday 03:00: the streak starts again", next_day("2026-11-02"), ("streak", 25))
        wk = serve.game3_json(sp.book(), day[0])
        expect("the week's points are the days' since Monday", wk["week"], g["days"]["2026-11-02"])
        expect("the day streak on the Game page", (wk["streak"], wk["scannedToday"]), (1, True))
        # rule 1: a plane scored before relay 76 keeps its points and awards, also when it comes closer
        old = plane("uncommon", "A21N", "WZZ1", km=6.0)
        old.update(gp=36, gk=1.2, gn=3, ga=[{"t": 1, "k": "first", "p": 36}])
        pts = g["points"]
        old["liveMin"] = 0.8
        note(old)
        expect("rule 1's planes not priced again", (old["gp"], len(old["ga"]), g["points"]), (36, 1, pts))
        row = next(r for r in serve.game_today(sp)["rows"] if r["hex"] == old["hex"])
        expect("... and Recent points keeps their reasons", (row["rule"], row["base"], row["gk"]), (1, 30, 1.2))
    finally:
        serve.board_day = real_day


def checks():
    bad = []

    def expect(what, got, want):
        if got != want:
            bad.append(f"{what}: got {got}, expected {want}")

    game_rule_checks(expect)

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

    # relay 75 (to-do #121): a saved place at the profile's own spot ("Home") and the profile's place ("home") share one
    # Spotted today, each pass once; a saved place elsewhere doesn't
    st, _, b = call("/places", "test-device")
    had = json.loads(b).get("places", []) if st == 200 else []
    call("/places", "test-device", body={"places": [{"k": "Home", "n": "Vienna", "lat": 48.2085, "lon": 16.3731, "r": 15},
                                                     {"k": "Away", "n": "Linz", "lat": 48.3069, "lon": 14.2858, "r": 15}]})
    near = "/aircraft/48.2085/16.3731/25"
    call(near + "?pl=Home&pc=48.2085,16.3731&pr=15", "test-device")
    call(near, "test-device")
    call(near + "?pl=Home&pc=48.2085,16.3731&pr=15", "test-device")

    def day_of(place):
        st, _, b = call("/sightings?over=1&deg=45&place=" + urllib.parse.quote(place), "test-device")
        return json.loads(b) if st == 200 else {}
    home, saved, away = day_of("home"), day_of("Home"), day_of("Away")
    ids = lambda d: sorted(e["id"] for e in d.get("entries", []))
    expect("home and the saved place there list the same planes", ids(home) == ids(saved) and len(ids(home)) > 0, True)
    expect("tagged Home, listed for home", {e["id"] for e in home.get("entries", []) if e.get("place") == "Home"} <=
           set(ids(home)), True)
    seen = sorted((e["hex"], e["ts"]) for e in home.get("entries", []))
    expect("each pass once in the merged list", [a for a, b in zip(seen, seen[1:]) if a[0] == b[0] and b[1] - a[1] < 45 * 60000], [])
    expect("the day's numbers alike", (home.get("stats") or {}).get("planes") == (saved.get("stats") or {}).get("planes"), True)
    expect("a saved place elsewhere keeps its own list", [e for e in away.get("entries", []) if e.get("place") != "Away"], [])
    # relay 77 (to-do #126): the Logbook too: a place's numbers are its spot's ("home" and "Home" alike, each sighting
    # once); the whole logbook (the place bar's spots) is checked after the league, which it would ask before its player
    lb = lambda q="": (lambda r: json.loads(r[2]) if r[0] == 200 else {})(call("/logbook" + q, "test-device"))   # noqa: E731
    h1, h2, aw = lb("?place=home"), lb("?place=Home"), lb("?place=Away")
    expect("Logbook: home and Home show the same numbers", (h1.get("sightings"), h1.get("regsCount")) == (h2.get("sightings"), h2.get("regsCount"))
           and h1.get("sightings", 0) > 0, True)
    expect("... a saved place elsewhere keeps its own", aw.get("place"), "Away")
    call("/places", "test-device", body={"places": had})

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
    rows0 = rows
    expect("a scored plane in today's list", bool(hx), True)
    if hx:
        st, _, b = call("/game/me?since=1", "test-device")
        me0 = json.loads(b) if st == 200 else {}
        expect("/game/me: the rules, the limits and the awards for the pop-ups (relay 76)",
               ((me0.get("rules") or {}).get("base", {}).get("rare"), (me0.get("limits") or {}).get("common", [0, 0])[1],
                any(a.get("k") == "pass" and a.get("hex") for a in me0.get("aw", []))), (100, 50, True))
        can = next((a.get("can") or {} for a in me0.get("aw", []) if a.get("k") in ("pass", "limit") and a.get("hex") == hx), None)
        expect("the plane's passive award says what a scan would add (relay 79: can)", can is not None and set(can) <= {"type", "airline"}, True)
        st, _, b = call("/game/lockon", "test-device", body={"hex": hx})
        lk = json.loads(b) if st == 200 else {}
        expect("a scan gives the plane's full points on top of its tenth (relay 79)",
               ((lk.get("lines") or [{}])[0].get("p", -1) == lk.get("full", -2), lk.get("bonus", 0) > lk.get("full", 0) - lk.get("had", 0)), (True, True))
        expect("... and the extras the pass promised", {x["w"]: x["p"] for x in lk.get("lines", []) if x["k"] == "new"}, can or {})
        expect("... the day's first scan brings day 1 of the streak", [x["p"] for x in lk.get("lines", []) if x["k"] == "streak"], [25])
        st, _, b = call("/game/lockon", "test-device", body={"hex": hx})
        expect("the same plane scanned twice", json.loads(b).get("why") if st == 200 else st, "done")
    # relay 71: Recent points, today's awards per plane (relay 76: the passive tenth, the scan and its extras); the
    # profile's own only
    today = lambda ck: json.loads(call("/game/today", ck)[2])     # noqa: E731
    td = today("test-device")
    row = next((r for r in td.get("rows", []) if r.get("hex") == hx), {})
    kinds = [a.get("k") for a in row.get("aw", [])]
    expect("Recent points: the passive points and the scan", ("pass" in kinds, "scan" in kinds, row.get("rule"), [a.get("r") for a in row.get("aw", []) if a.get("k") == "scan"]),
           (True, True, 3, [3]))
    expect("... add up to the plane's", sum(a["p"] for a in row.get("aw", [])), row.get("gp", 0) + row.get("lock", 0) + row.get("gs", 0))
    expect("... the day's total", td.get("today", 0) > 0 and td.get("planes", 0) >= len(td.get("rows", [])) > 0, True)
    expect("... and today's limits", (td.get("limits") or {}).get("legendary", [0, 0])[1], 3)
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
    st, _, b = call("/game/me", "test-device")
    wk = [r["points"] for r in lg.get("rows", []) if r.get("me")]       # (the league is kept for 30 s: at most the week)
    expect("the league's week is the player's week (relay 76)", len(wk) == 1 and 0 < wk[0] <= (json.loads(b).get("week") if st == 200 else 0), True)
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
    expect("... and how often the game scored them (relay 76)", any(t.get("game", 0) > 0 for t in hg.get("types", [])), True)
    # relay 79: the scans per type, counted back from the days the first time (the scan above), then by each scan
    tc = next((str(e.get("typeCode") or "").upper() for e in rows0 if e.get("hex") == hx), "")
    sc0 = {t["code"]: t.get("scans", 0) for t in hg.get("types", [])}
    expect("the hangar counts the scans per type, counted back from the days (relay 79)", (sum(sc0.values()) >= 1, sc0.get(tc, 0) >= 1 if tc else True), (True, True))
    st, _, b = call("/sightings", "test-device")
    rows1 = json.loads(b) if st == 200 else []
    rows1 = rows1.get("entries", rows1) if isinstance(rows1, dict) else rows1
    hx2 = next((e["hex"] for e in rows1 if "gp" in e and not e.get("scan") and e.get("typeCode")), None)
    if hx2:
        lk2 = json.loads(call("/game/lockon", "test-device", body={"hex": hx2})[2])
        if lk2.get("bonus"):
            st, _, b = call("/game/hangar", "test-device")
            sc1 = {t["code"]: t.get("scans", 0) for t in (json.loads(b) if st == 200 else {}).get("types", [])}
            expect("... and then one more with each scan", sum(sc1.values()) - sum(sc0.values()), 1)
    st, _, b = call("/game/hangar", "owner-device")
    hg = json.loads(b) if st == 200 else {}
    expect("the hangar fills on any sighting: a board at home (relay 76)",
           (bool(hg.get("types")), {t.get("game") for t in hg.get("types", [])}), (True, {0}))
    me_row = next((r for r in lg.get("rows", []) if r.get("me")), {})
    st, _, b = call("/game/player?id=" + str(me_row.get("id", "")), "test-device")
    pl = json.loads(b) if st == 200 else {}
    expect("a league player's card", (pl.get("name"), pl.get("level", 0) >= 1, isinstance(pl.get("trophies"), list)), ("Test", True, True))
    expect("the card shows no places", any(k in b.decode() for k in ('"lat"', '"lon"', '"at"', '"place"')), False)
    expect("an unknown player", call("/game/player?id=000000000000", "test-device")[0], 404)
    expect("a player's card for strangers", call("/game/player?id=x")[0] in (401, 403), True)
    # relay 77 (to-do #126): the place bar learns which places are one spot; no doubles in the spot's numbers
    call("/places", "test-device", body={"places": [{"k": "Home", "n": "Vienna", "lat": 48.2085, "lon": 16.3731, "r": 15},
                                                     {"k": "Away", "n": "Linz", "lat": 48.3069, "lon": 14.2858, "r": 15}]})
    al, h1 = lb(), lb("?place=home")
    expect("Logbook: one spot for the place bar", (sorted(al.get("spots", {}).get("Home", [])), "Away" in al.get("spots", {})), (["Home", "home"], False))
    expect("... no doubles: the spot's sightings are its places' added", h1.get("sightings"), sum(n for k, n in al.get("places", []) if k in ("home", "Home")))
    call("/places", "test-device", body={"places": had})

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

    # relay 73: a plane's own photo from Planespotters.net (the fake source's: OE-LBN by registration, the A380 by hex, and
    # for the C-130's hex a photo of OO-TEK, another aircraft)
    fake = f"http://127.0.0.1:{int(BASE.rsplit(':', 1)[1]) - 1}"
    asked = lambda: json.loads(urllib.request.urlopen(fake + "/ps/asked", timeout=5).read())     # noqa: E731
    photo = lambda q, ck="test-device": call("/planephoto?" + q, ck)                            # noqa: E731
    st, h, b = photo("reg=OE-LBN&hex=440a01")
    ph = (json.loads(b).get("photo") or {}) if st == 200 else {}
    expect("/planephoto by registration (status, credit, link, photo)", (st, ph.get("by"), ph.get("link"), ph.get("src", "")[-9:]),
           (200, "Test Photographer", "https://www.planespotters.net/photo/1000001/oe-lbn-austrian-airlines-airbus-a320-214?utm_source=api", "1_280.svg"))
    expect("... not kept by the browser", h.get("Cache-Control"), "no-store")
    photo("reg=oe-lbn&hex=440a01", "owner-device")
    expect("... asked once for two screens", asked().get("reg/OE-LBN"), 1)
    st, _, b = photo("reg=CH-10&hex=44d0ab")
    expect("a photo of another aircraft under the same hex is passed over", (st, json.loads(b).get("photo", "-") if st == 200 else None, asked().get("hex/44D0AB")), (200, None, 1))
    st, _, b = photo("reg=A6-EVB&hex=896180")
    expect("a photo found by hex with the same registration on it", ((json.loads(b).get("photo") or {}).get("link") or "").split("/")[-1] if st == 200 else st,
           "a6-evb-emirates-airbus-a380-861?utm_source=api")
    st, _, b = photo("hex=440a01")
    expect("no registration: no photo, nothing asked", (st, json.loads(b).get("photo", "-") if st == 200 else None, asked().get("hex/440A01")), (200, None, None))
    expect("/planephoto for strangers", call("/planephoto?reg=OE-LBN")[0] in (401, 403), True)
    expect("/photo doesn't pass Planespotters' photos on", call("/photo?u=" + urllib.parse.quote("https://t.plnspttrs.net/1/1_280.jpg", safe=""), "test-device")[0], 400)

    # relay 74: the cards' facts from the fake Wikipedia and Wikidata, cleaned (the infobox, a specs table or template)
    wm = lambda: json.loads(urllib.request.urlopen(fake + "/wm/asked", timeout=5).read())     # noqa: E731
    facts = lambda q, ck="test-device": (lambda r: (r[0], json.loads(r[2]) if r[0] == 200 else {}))(call("/facts?" + q, ck))   # noqa: E731
    st, j = facts("model=" + urllib.parse.quote("Airbus A320 family"))
    f = j.get("facts") or {}
    expect("/facts for a model: the infobox (first flight, in service, built, as of, years, main user)",
           (st, f.get("firstFlight"), f.get("introduced"), f.get("built"), f.get("builtAsOf"), f.get("producedFrom"), f.get("producedTo"), f.get("mainUser")),
           (200, "1987-02-22", "1988-04-18", 12900, "2026-09", 1986, "present", "American Airlines"))
    expect("... and the specifications table's first column (seats, length, span, range, engines)",
           (f.get("seats"), f.get("length"), f.get("span"), f.get("range"), f.get("engines")), (180, 37.57, 35.8, 6112, {"n": 2, "name": "CFM56-5B"}))
    expect("... Wikipedia's words and page", (j.get("text", "")[:24], j.get("url")), ("The Airbus A320 family i", "https://en.wikipedia.org/wiki/Airbus_A320_family"))
    facts("model=" + urllib.parse.quote("Airbus A320 family"), "owner-device")
    expect("... asked once for two screens", wm().get("wiki:Airbus A320 family"), 1)
    st, j = facts("model=" + urllib.parse.quote("Airbus A330neo"))
    f = j.get("facts") or {}
    expect("/facts for a model with the specs template (seats, engines, developed from)", (f.get("seats"), f.get("engines"), f.get("developedFrom")),
           (440, {"n": 2, "name": "Rolls-Royce Trent 7000-72", "kind": "turbofan"}, {"name": "Airbus A330", "page": "Airbus A330"}))
    st, j = facts("airline=AUA")
    f = j.get("facts") or {}
    expect("/facts for an airline by its ICAO code (Wikidata and the infobox)",
           (st, j.get("title"), f.get("founded"), f.get("commenced"), f.get("hubs"), f.get("alliance"), f.get("fleet"), f.get("destinations"), f.get("employees")),
           (200, "Austrian Airlines", "1957-09-30", "1958-03-31", [{"name": "Vienna International Airport", "code": "VIE"}], "Star Alliance", 65, 121, 5659))
    expect("... its photo from Commons", "/commons/OE-LPM_%40_VIE" in j.get("img", ""), True)
    # relay 77 (to-do #122): Austrian has its own name: its own card, "Part of" its group; Wizz Air Malta flies under its
    # group's: the brand's card (Wizz Air, the whole brand's fleet: its own, Malta's and the UK's), "Flown by" it, and
    # its own facts "Part of Wizz Air"; a group by its Wikidata id
    expect("... Austrian keeps its own card, part of the Lufthansa Group", (j.get("flownBy"), j.get("group")), (None, {"name": "Lufthansa Group", "qid": "Q62589018"}))
    st, j = facts("airline=WMT")
    expect("/facts for a company flying under its group's name: the brand's, flown by it",
           (st, j.get("name"), j.get("icao"), (j.get("facts") or {}).get("fleet"), (j.get("facts") or {}).get("fleetAll"), j.get("flownBy"), j.get("group")),
           (200, "Wizz Air", "WZZ", 266, True, {"name": "Wizz Air Malta", "icao": "WMT"}, None))
    st, j = facts("airline=WMT&own=1")
    expect("... its own (Flown by)", (st, j.get("name"), (j.get("facts") or {}).get("fleet"), j.get("flownBy"), j.get("group")),
           (200, "Wizz Air Malta", 127, None, {"name": "Wizz Air", "qid": "Q335147"}))
    expect("... the brand's own card alike", (lambda v: (v.get("name"), (v.get("facts") or {}).get("fleet"), v.get("flownBy")))(facts("airline=WZZ")[1]), ("Wizz Air", 266, None))
    st, j = facts("org=Q62589018")
    expect("/facts for a group by its Wikidata id (Part of)", (st, j.get("name"), (j.get("facts") or {}).get("founded")), (200, "Lufthansa Group", "1926-01-06"))
    expect("/facts with a bad id", call("/facts?org=Q", "test-device")[0], 400)
    expect("an airline that no longer flies has no facts", facts("airline=AZA")[1], {"kind": "airline", "none": True})
    st, j = facts("airport=DXB")
    f = j.get("facts") or {}
    expect("/facts for an airport by its IATA code (passengers and year, elevation in metres, opened, runways)",
           (st, f.get("passengers"), f.get("passengersYear"), f.get("elevation"), f.get("opened"), f.get("runways"), j.get("text", "")[:5]), (200, 95200000, 2025, 19, "1960", 2, "Dubai"))
    expect("a page Wikipedia doesn't have", facts("model=" + urllib.parse.quote("No such aircraft"))[1], {"kind": "model", "none": True})
    expect("/facts without a page or code", call("/facts?airline=X", "test-device")[0], 400)
    expect("/facts for strangers", call("/facts?airline=AUA")[0] in (401, 403), True)
    # ... and what the profile spotted of one airline, model or airport, over every saved day
    sp = lambda q: (lambda r: json.loads(r[2]) if r[0] == 200 else {"status": r[0]})(call("/logbook/spotted?" + q, "test-device"))   # noqa: E731
    al, ty = sp("airline=AUA"), sp("type=A320")
    expect("/logbook/spotted: an airline's sightings and planes (yesterday's Austrian at least)", (al.get("sightings", 0) >= 1, al.get("planes", 0) >= 1, sorted(al)),
           (True, True, ["first", "last", "planes", "sightings"]))
    expect("... a model's", ty.get("planes", 0) >= 2, True)
    expect("... nothing yet", sp("airline=QQQ"), {"sightings": 0, "planes": 0, "first": None, "last": None})
    expect("/logbook/spotted for strangers", call("/logbook/spotted?airline=AUA")[0] in (401, 403), True)

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

    # 1.93: a plane's own photo from Planespotters.net first (the fake's OE-LBN), its credit on it and a link to its page;
    # never in the share picture (noPs); the C-130 (another aircraft's photo under its hex) gets none from there
    pic = "planePic({hex: '%s', r: '%s', t: '%s'}, {}, {}, null%s)"
    for args in (("440a01", "OE-LBN", "A320", ""), ("44d0ab", "CH-10", "C130", "")):
        e(pic % args)                                          # asks the relay; the answer comes in a moment
    pg.wait_for_timeout(2000)
    got = e("(p => [p.kind, picCredit(p), picHtml(p).includes('<a class=\"cPicA\" href=\"https://www.planespotters.net/photo/1000001/oe-lbn-')])(" +
            pic % ("440a01", "OE-LBN", "A320", "") + ")")
    if got != ["ps", "© Test Photographer · Planespotters.net", True]:
        bad.append(f"Planespotters photo in the app: got {got!r}")
    if e((pic % ("440a01", "OE-LBN", "A320", ", true")) + ".kind") == "ps":
        bad.append("the share picture would get a Planespotters photo")
    if e((pic % ("44d0ab", "CH-10", "C130", "")) + ".kind") == "ps":
        bad.append("a photo of another aircraft under the same hex was shown")
    ctx.close()
    for b_ in bad:
        print("flow:", b_)
    print("the app's saves hold" if not bad else f"{len(bad)} app save check(s) failed")
    return bad


if __name__ == "__main__":
    sys.exit(0 if checks() else 1)
