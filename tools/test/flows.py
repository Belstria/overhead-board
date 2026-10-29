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
  fresh one does; a hidden page's (bg=1, relay 81) like a stale one, only for a live place; a callsign of "@"s is none, also in sightings saved before (relay 70)
- Recent points: today's awards per plane (the first score, a close-pass top-up, the lock-on), the profile's own only (relay 71)
- bingo lines and trophies pay once (relay 83): a line +50, the full card +500, a rank 50 to 250, a one-off 100; earlier
  wins unpaid, every total kept; a restart, a rescore and the backfills pay nothing again; a new card each Monday
- the game's rules since relay 76 (to-do #127), on the relay's functions: the passive points (relay 80: 5, 10, 15, 25, 50; a rule-3 game starts unchanged on the new relay) and the limits per rarity, the
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
- the facts database (relay 78, to-do #129): facts.json's entries moved in (not relay 74's airlines); a key not in it
  looked up on its first tap; the monthly refresh (the owner's /facts?refresh=1) against the fakes in batches (the
  query service's lists, 50 items or pages a request, introductions continued, a maxlag waited out), every answer the
  same as the first tap's (the brand rule too) but the photo's own address at 500 px, then read from the database alone
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


def rule4_checks(serve, expect, day):
    """Relay 80 (to-do #136): a game scored under rule 3 (the tenths 1, 3, 10, 25, 50) gives exactly the same totals,
    days, league week, logbook and awards when the new relay starts on it; only new planes score by rule 4."""
    import json as _j
    import tempfile
    from pathlib import Path
    old_rule, old_passive = serve.GAME_RULE, serve.GAME_PASSIVE
    day[0] = "2026-11-04"                                 # a Wednesday
    folder = Path(tempfile.mkdtemp(prefix="fb-rule4-"))
    now = serve.time.time()

    def mk(sp, n, tier, tc, cs):
        e = {"id": f"y{n}", "hex": f"{n + 900:06x}", "ts": int(now * 1000) + n, "typeCode": tc, "callsign": cs, "tier": tier,
             "liveMin": 4.0, "liveSeen": now}
        sp.entries.insert(0, e)
        sp.by_hex[e["hex"]] = e
        return e

    def snap(sp):
        with serve._data_lock:
            sp.ensure_day()
            serve.game_book(sp.book())
            return [_j.dumps(x, sort_keys=True) for x in (sp.book(), sp.entries, {k: v for k, v in serve.game3_json(sp.book(), day[0]).items() if k != "rules"},
                                                           serve.game_today(sp), serve.game_awards(sp, 0))]

    def save(sp):
        with serve._data_lock:
            files = sp.files()
        for path, text in files:
            path.write_text(text)

    try:
        serve.GAME_RULE, serve.GAME_PASSIVE = 3, {"common": 1, "uncommon": 3, "rare": 10, "epic": 25, "legendary": 50}
        a = serve.Spot(folder, None, 15)
        a.ensure_day()
        olds = [mk(a, 1, "common", "A320", "AUA1"), mk(a, 2, "rare", "E195", "BCY2"), mk(a, 3, "legendary", "A388", "UAE3")]
        with serve._data_lock:
            for e in olds:
                serve.game_note(a, e)
        serve.game_lockon(a, olds[0]["hex"])
        with serve._data_lock:
            pts3 = serve.game_book(a.book())["points"]
            gp3 = [e["gp"] for e in olds]
            rules3 = {x["r"] for e in olds for x in e["ga"]}
            a.changed("book", "day")
        save(a)
        before = snap(a)
    finally:
        serve.GAME_RULE, serve.GAME_PASSIVE = old_rule, old_passive
    expect("rule 3's game: scored by the tenths, awards say rule 3", (gp3, rules3, pts3 > 0), ([1, 10, 50], {3}, True))
    b = serve.Spot(folder, None, 15)                      # the new relay starts on the saved game
    after = snap(b)
    expect("the new relay on a rule-3 game: logbook, sightings, game page (but its rules), Recent points, awards identical",
           [x == y for x, y in zip(after, before)], [True] * 5)
    with serve._data_lock:
        gb = serve.game_book(b.book())
        v = (gb.get("v"), b.book().get("gameV"), gb["points"])
    expect("... GAME3_V and GAME_V not raised, points the same", v, (1, 2, pts3))
    new = mk(b, 9, "common", "B738", "RYR9")
    with serve._data_lock:
        serve.game_note(b, new)
        gb = serve.game_book(b.book())
    expect("a new plane scores by rule 4 (5 for a common), earlier ones keep theirs",
           (new["gp"], new["ga"][0]["r"], new["gr"], gb["points"]), (5, 4, 4, pts3 + 5))
    row = {r["hex"]: r for r in serve.game_today(b)["rows"]}
    expect("... Recent points: the old planes say rule 3, the new one rule 4",
           (row[olds[0]["hex"]]["rule"], row[olds[1]["hex"]]["rule"], row[new["hex"]]["rule"]), (3, 3, 4))
    save(b)
    reload = serve.Spot(folder, None, 15)
    with serve._data_lock:
        reload.ensure_day()
        old_e = {e["hex"]: e for e in reload.entries}
    expect("... the old planes' points and awards on disk untouched",
           ([old_e[e["hex"]]["gp"] for e in olds], {x["r"] for e in olds for x in old_e[e["hex"]]["ga"]}), ([1, 10, 50], {3}))


def screens_checks(expect):
    """Relay 80 (to-do #137): a screen whose latest hello said hidden counts as left 15 s later (Recently gone), whatever it
    asks for meanwhile; back within 15 s it stays; a hello saying visible is a new visit, not announced; the 60 s rule for
    silent visible screens and the immediate bye stay. On the relay's functions, with a clock of its own."""
    import types
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "relay"))
    import serve
    serve.ARGS = serve.ARGS or types.SimpleNamespace(verbose=False)
    clock = [1_800_000_000.0]

    class Clock:                                          # the relay's `time`, with time() as we say
        def __getattr__(self, name):
            return getattr(real_time, name)

        @staticmethod
        def time():
            return clock[0]

    real_time = serve.time
    serve.time = Clock()
    said = []
    real_event = serve.event
    serve.event = lambda level, msg, echo=True: said.append(msg)
    serve._screens.clear()
    serve._screens_left.clear()
    serve._screens_gone.clear()
    try:
        def seen(sid, hello=None, bye=False):
            serve.screen_seen("127.0.0.1", "Mozilla/5.0 (iPhone)", "", sid, hello, bye)

        def hello(vis):
            return {"name": "", "w": 390, "h": 844, "q": "", "vis": vis}

        def at(dt):
            clock[0] += dt
            serve._screen_sweep(clock[0])

        def live():
            return sorted(i["sid"] for i in serve.screens_list()[0])

        seen("aaaa", hello("visible"))
        seen("bbbb", hello("visible"))
        seen("cccc", hello("visible"))
        at(7)
        expect("screens: three open, announced", (live(), len(said)), (["aaaa", "bbbb", "cccc"], 3))
        seen("aaaa", hello("hidden"))                     # a goes to the background, b too
        seen("bbbb", hello("hidden"))
        at(10)
        seen("bbbb", hello("visible"))                    # b is back within 15 s
        seen("aaaa")                                      # a still asks for things meanwhile
        at(4)
        expect("screens: hidden for 10 s still on, back in time stays", live(), ["aaaa", "bbbb", "cccc"])
        at(3)
        seen("aaaa")                                      # ... and its requests don't keep it on
        seen("cccc")
        at(1)
        expect("screens: hidden for 15 s counts as left, despite its requests", live(), ["bbbb", "cccc"])
        expect("... listed in Recently gone, left at the moment it went to the background",
               [(g["sid"], g["left"]) for g in serve.screens_list()[1]], [("aaaa", int(1_800_000_007.0))])
        n = len(said)
        seen("aaaa")
        seen("aaaa", hello("hidden"))
        seen("aaaa", bye=True)
        at(5)
        expect("... its later requests, hellos and bye bring nothing back", (live(), len(said), len(serve.screens_list()[1])), (["bbbb", "cccc"], n, 1))
        seen("aaaa", hello("visible"))
        expect("a hello saying visible: a new visit, on for 0 s", [(i["sid"], i["on_s"], i["reloads"]) for i in serve.screens_list()[0] if i["sid"] == "aaaa"], [("aaaa", 0, 0)])
        at(10)
        expect("... not announced again", len(said), n)
        seen("aaaa", hello("hidden"))
        at(16)
        expect("hidden again: left again, once more in Recently gone", (live(), len(serve.screens_list()[1])), (["bbbb", "cccc"], 2))
        # the old rules: 60 s of silence while visible, and the bye at once
        seen("bbbb", hello("visible"))
        at(50)
        seen("bbbb")
        at(20)
        expect("a silent visible screen is gone after 60 s (cccc); a busy one stays", live(), ["bbbb"])
        seen("bbbb", bye=True)
        at(11)
        expect("bye: gone after 10 s, closed", (live(), "(closed)" in said[-1]), ([], True))
    finally:
        serve.time = real_time
        serve.event = real_event
        serve._screens.clear()
        serve._screens_left.clear()
        serve._screens_gone.clear()


def game_rule_checks(expect):
    """Relay 76 (to-do #127): the game's rules on a made-up profile, straight on the relay's functions (no relay needed):
    the passive points and the limits per rarity, the scan's full points on top without a limit (relay 79; a top-up in
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
        expect("passive: 5 for a common (relay 80, rule 4), 50 a day", [e["gp"] for e in commons[:50]], [5] * 50)
        expect("... the 51st and 52nd get nothing", [e["gp"] for e in commons[50:]], [0, 0])
        expect("... only the first over the limit pops up", [(e["ga"][-1]["k"], e["ga"][-1]["first"]) for e in commons[50:]],
               [("limit", True), ("limit", False)])
        rare = plane("rare", "E195", "BCY777")
        note(rare)
        legs = [plane("legendary", "A388", f"UAE{i}") for i in range(4)]
        for e in legs:
            note(e)
        expect("passive by rarity: rare 15, special 50 up to 3", [rare["gp"]] + [e["gp"] for e in legs], [15, 50, 50, 50, 0])
        tro = {a["n"]: a["p"] for e in sp.entries for a in e["ga"] if a["k"] == "trophy"}   # relay 83: trophies pay
        expect("the day's points and limits (and the Special day trophy's 100, relay 83)",
               (g["days"][day[0]], serve._game_limits(g, day[0]), tro.get("specialday")),
               (250 + 15 + 150 + sum(tro.values()), {"common": 52, "rare": 1, "legendary": 4}, 100))
        expect("extras only with scans: passive awards", sorted({a["k"] for e in sp.entries for a in e["ga"]} - {"trophy"}), ["limit", "pass"])
        commons[1]["liveMin"] = 1.0
        expect("a plane comes closer: not priced again", (note(commons[1]), commons[1]["gp"], len(commons[1]["ga"])), (True, 5, 1))

        def scan(e):
            r = serve.game_lockon(sp, e["hex"])
            return r.get("bonus"), [(x["k"], x["p"]) for x in r.get("lines", [])] or r.get("why")

        expect("a passive award says what a scan would add (relay 79: can)", (commons[0]["ga"][0].get("can"), commons[51]["ga"][0].get("can")),
               ({"type": 50, "airline": 25}, {"type": 50, "airline": 25}))
        expect("a scan gives a common its full 10 on top of its 5, with a new type, airline and day 1 of the streak (relay 79)", scan(commons[0]),
               (10 + 50 + 25 + 25, [("scan", 10), ("new", 50), ("new", 25), ("streak", 25)]))
        again = plane("common", "A320", "AUA555")
        note(again)
        expect("... after it, a plane of that type and airline promises nothing more", again["ga"][0].get("can"), None)
        expect("the same plane scanned again", scan(commons[0]), (0, "done"))
        expect("a common past the limit: the full 10 from a scan, nothing new", scan(commons[51]), (10, [("scan", 10)]))
        expect("scans have no limit", [scan(e)[0] for e in legs], [500 + 50 + 25, 500, 500, 500])
        expect("the scans counted per type (relay 79; from the start here)", g.get("scanTypes"), None)
        far = plane("uncommon", "A320", "AUA999", km=12.0)
        note(far)
        expect("a plane at 12 km scores (relay 82) but can't be scanned", (far["gp"], scan(far)), (10, (0, "closer")))

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
        expect("the rules for the app: passive 5, 10, 15, 25, 50; the scan's full points as before",
               ([serve.game_rules()["passive"][t] for t in serve.TIERS], serve.game_rules()["base"]),
               ([5, 10, 15, 25, 50], {"common": 10, "uncommon": 30, "rare": 100, "epic": 250, "legendary": 500}))
        rule4_checks(serve, expect, day)
    finally:
        serve.board_day = real_day


def bingo_trophy_checks(expect):
    """Relay 83 (to-do #147): bingo lines and trophies pay, once: a line +50, the full card +500 more, a trophy's rank
    by its medal (50 to 250), a one-off trophy +100; on the plane that won them (Recent points), in the day, the week
    (the league) and the level. Only wins from now on: a game with lines and trophies won by relay 82 keeps every total
    when relay 83 starts on it; a restart, a rescore of the logbook from its saved days and the trophies' backfill pay
    nothing again; the next Monday's card starts unpaid."""
    import json as _j
    import tempfile
    import types
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "relay"))
    import serve
    serve.ARGS = serve.ARGS or types.SimpleNamespace(verbose=False)
    day = ["2026-10-28"]                                  # a Wednesday; its card (week of 26 Oct) below
    real_day, real_bingo, real_tro = serve.board_day, serve._game_bingo, serve._game_trophies
    serve.board_day = lambda t=None: day[0]
    noon = lambda d, h=12: int(serve.time.mktime(serve.time.strptime(f"{d} {h:02d}", "%Y-%m-%d %H")) * 1000)
    # a plane for each bingo goal; the rest of it does none of them (an A320 of no listed airline, at noon)
    GOAL = {"heli": {"adsbCat": "A7"}, "a380": {"typeCode": "A388"}, "b747": {"typeCode": "B744"}, "b777": {"typeCode": "B77W"},
            "b787": {"typeCode": "B788"}, "a350": {"typeCode": "A359"}, "a330": {"typeCode": "A333"}, "embraer": {"typeCode": "E190"},
            "turboprop": {"typeCode": "AT76"}, "cargo": {"callsign": "FDX1"}, "bizjet": {"typeCode": "C56X"},
            "private": {"callsign": "OEXYZ"}, "military": {"military": True}, "watch": {"watch": True}, "low": {"altAtMin": 2000},
            "close": {"minDist": 0.5}, "rare": {"tier": "rare"}, "night": {"h": 23}, "early": {"h": 6}, "newtype": {"newType": True},
            "lhgroup": {"callsign": "DLH1"}, "gulf": {"callsign": "UAE1"}, "lowcost": {"callsign": "RYR1"},
            "turkish": {"callsign": "THY1"}, "fast": {"maxSpeed": 600}}
    folder = Path(tempfile.mkdtemp(prefix="fb-pay-"))
    n = [0]

    def plane(sp, goal=None, **more):
        n[0] += 1
        now = serve.time.time()
        x = {**(GOAL[goal] if goal else {}), **more}
        e = {"id": f"p{n[0]}", "hex": f"{n[0] + 4000:06x}", "ts": noon(day[0], x.pop("h", 12)) + n[0], "typeCode": "A320",
             "callsign": "ZZZ1", "tier": "common", "liveMin": 4.0, "liveSeen": now, **x}
        sp.entries.insert(0, e)
        sp.by_hex[e["hex"]] = e
        with serve._data_lock:
            serve.game_note(sp, e)
        return e

    def save(sp):
        with serve._data_lock:
            sp.changed("book", "day")
            files = sp.files()
        for path, text in files:
            path.write_text(text)

    def spot():
        sp = serve.Spot(folder, None, 15)
        with serve._data_lock:
            sp.ensure_day()
            return sp, serve.game_book(sp.book())

    def snap(sp):
        with serve._data_lock:
            g = serve.game_book(sp.book())
            return _j.dumps([g, {k: v for k, v in serve.game3_json(sp.book(), day[0]).items() if k != "rules"},
                             serve.bingo_json(sp, day[0])], sort_keys=True)

    paid = lambda e: [(a["k"], a["p"], a.get("n")) for a in e.get("ga", []) if a["k"] in ("bingo", "card", "trophy")]
    try:
        for k, x in GOAL.items():                         # each plane does its goal only
            e = {"typeCode": "A320", "callsign": "ZZZ1", "tier": "common", "ts": noon(day[0], x.get("h", 12)),
                 **{a: b for a, b in x.items() if a != "h"}}
            hits = [g for g in serve.BINGO if serve.BINGO[g](e)]
            if hits != [k]:
                expect(f"the test's plane for bingo goal {k}", hits, [k])
        card = serve.random.Random("fallblatt-2026-10-26").sample(sorted(serve.BINGO), 9)
        expect("the week's card (rows: new type, turboprop, low; helicopter, Turkish, bizjet; Gulf, fast, private)", card,
               ["newtype", "turboprop", "low", "heli", "turkish", "bizjet", "gulf", "fast", "private"])
        # relay 82 (before): the middle row made and the Bingo trophy won, unpaid
        serve._game_bingo = serve._game_trophies = lambda *a: None
        sp, g = spot()
        for k in ("heli", "turkish", "bizjet"):
            plane(sp, k)
        with serve._data_lock:
            b = serve.bingo_json(sp, day[0])
        expect("relay 82: a line made, the Bingo trophy won", (b["lines"], "bingo" in g["trophies"], "paid" in b), (1, True, False))
        save(sp)
        serve._game_bingo, serve._game_trophies = real_bingo, real_tro
        sp, g = spot()                                    # relay 83 starts on it
        before = snap(sp)
        pts0, day0 = g["points"], g["days"][day[0]]
        expect("relay 83 on it: nothing changes at the start", snap(sp), before)
        e = plane(sp)
        expect("... the next plane pays nothing for the earlier line or trophy", (paid(e), g["points"], g["days"][day[0]]),
               ([], pts0 + 5, day0 + 5))
        expect("... the earlier line counts as had, unpaid", (g["bingoPay"]["week"], g["bingoPay"]["lines"], g["bingoPay"]["had"]),
               ("2026-10-26", [1], {"lines": 1, "card": False}))
        pts0 = g["points"]
        rows = [plane(sp, k) for k in ("newtype", "turboprop", "low")]
        expect("a line made: +50 on the plane that made it, once", [paid(e) for e in rows], [[], [], [("bingo", 50, 0)]])
        expect("... in the plane's gb, the points, the day", (rows[2]["gb"], g["points"], g["days"][day[0]]),
               (50, pts0 + 15 + 50, day0 + 5 + 15 + 50))
        gulf, fast = plane(sp, "gulf"), plane(sp, "fast")
        expect("the left column and a diagonal, then the middle column", (paid(gulf), paid(fast)),
               ([("bingo", 50, 3), ("bingo", 50, 7)], [("bingo", 50, 4)]))
        pts0 = g["points"]
        last = plane(sp, "private")
        expect("the full card: three lines +50, the card +500, the Full card trophy +100",
               paid(last), [("bingo", 50, 2), ("bingo", 50, 5), ("bingo", 50, 6), ("card", 500, None), ("trophy", 100, "fullcard")])
        expect("... 750 more, and the Bingo trophy (won before) never paid",
               (g["points"] - pts0, last["gb"], sorted(g["trophyPaid"])), (5 + 750, 750, ["fullcard"]))
        again = plane(sp, "private")
        expect("the card done: nothing more this week; the points it brought win High scorer (1,000 points, bronze) +50",
               (paid(again), sorted(g["bingoPay"]["lines"])), ([("trophy", 50, "points1k")], list(range(8))))
        total = 11 * 5 + 7 * 50 + 500 + 100 + 50
        g3 = serve.game3_json(sp.book(), day[0])
        with serve._data_lock:
            b = serve.bingo_json(sp, day[0])
        expect("the day, the week (the league's) and the level count them", (g["days"][day[0]], g3["week"], g3["level"]),
               (total, total, serve.level_of(total)[0]))
        expect("bingo_json: the lines and the card that paid; game3_json: the trophies that paid",
               (b["paid"], g3["trophyPaid"]), ({"lines": 7, "full": True, "line": 50, "card": 500},
                                               {"fullcard": 100, "points1k": 50}))
        row = next(r for r in serve.game_today(sp)["rows"] if r["hex"] == last["hex"])
        expect("Recent points: the plane's gb and its awards", (row["gb"], [a["k"] for a in row["aw"]]),
               (750, ["pass", "bingo", "bingo", "bingo", "card", "trophy"]))
        # a restart, then a rescore of the logbook and the trophies' backfill: nothing paid again
        save(sp)
        before = snap(sp)
        sp, g = spot()
        expect("a restart: the same game", snap(sp), before)
        for x in sp.entries:
            x["liveMin"] -= 1.0                       # every plane comes closer: priced again? no
        with serve._data_lock:
            for x in list(sp.entries):
                serve.game_note(sp, x)
        expect("... planes coming closer pay nothing again", (g["points"], g["bingoPay"]["lines"].__len__()), (total, 8))
        save(sp)
        lb = _j.loads((folder / "logbook.json").read_text())
        lb["gameV"], lb["trophiesV"], lb["cardsV"] = 0, 0, 0
        (folder / "logbook.json").write_text(_j.dumps(lb))
        sp, g = spot()
        expect("a rescore from the saved days and the trophies' backfill: the game's totals the same",
               (g["points"], g["days"], g["trophyPaid"], g["bingoPay"]["lines"].__len__()),
               (total, {day[0]: total}, {"fullcard": 100, "points1k": 50}, 8))
        # trophies: each rank its medal, a one-off +100, once
        expect("a rank by its medal: bronze 50 to diamond 250; a one-off 100",
               [serve._trophy_pts(k)[0] for k in ("century", "thousand", "planes10k", "planes50k", "planes100k", "airlines25",
                                                  "airlines100", "regs10k", "streak30", "beluga", "bingo")],
               [50, 100, 150, 200, 250, 50, 150, 150, 100, 100, 100])
        day[0] = "2026-10-29"
        with serve._data_lock:
            sp.ensure_day()
        pts0 = g["points"]
        bel = [plane(sp, None, typeCode="A3ST") for _ in range(2)]
        expect("Whale watcher (one-off): +100 once", (paid(bel[0]), paid(bel[1]), g["points"] - pts0),
               ([("trophy", 100, "beluga")], [], 10 + 100))
        busy = [plane(sp) for _ in range(298)]
        tro = [(i, p) for i, e in enumerate(busy, 3) for p in paid(e)]
        expect("100 planes in a day: Busy sky bronze +50; 300: Rush hour silver +100 (and the game's 100th plane: Century +50)",
               tro, [(89, ("trophy", 50, "century")), (100, ("trophy", 50, "busyday")), (300, ("trophy", 100, "busy300"))])
        a = next(x for x in busy[97]["ga"] if x["k"] == "trophy")
        expect("... the award says its rank (m: 0 bronze)", a.get("m"), 0)
        # the next Monday: a new card, nothing paid on it yet; its first line pays again
        day[0] = "2026-11-02"
        with serve._data_lock:
            sp.ensure_day()
        card2 = serve.random.Random("fallblatt-2026-11-02").sample(sorted(serve.BINGO), 9)
        first = plane(sp)
        expect("Monday: a new card, nothing paid", (paid(first), g["bingoPay"]["week"], g["bingoPay"]["lines"]), ([], "2026-11-02", []))
        row0 = [plane(sp, k) for k in card2[:3]]
        expect("... its top row pays +50 again", paid(row0[2])[:1], [("bingo", 50, 0)])
        save(sp)
    finally:
        serve.board_day, serve._game_bingo, serve._game_trophies = real_day, real_bingo, real_tro


def scan_circle_checks(expect):
    """Relay 82 (to-do #145, #146): the two circles through record() on a live place: passive points within 15 km, the
    scan and the list of scannable planes (/game/me's "scan") within 10 km; a live place looks at least 15 km round; a game
    scored with relay 81's single 10 km circle (rules 3 and 4) keeps every total when relay 82 starts on it."""
    import json as _j
    import tempfile
    import types
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "relay"))
    import serve
    serve.ARGS = serve.ARGS or types.SimpleNamespace(verbose=False)
    real = serve.where_name, serve.watch_of
    serve.where_name, serve.watch_of = (lambda lat, lon: {}), (lambda hx: None)     # no lookups from here
    lat, lon = 48.2085, 16.3731
    try:
        sp = serve.Spot(Path(tempfile.mkdtemp(prefix="fb-circles-")), None, lambda: 3)
        sp.ensure_day()

        def ac(hx, km, t="A320", cs="AUA1"):
            return {"hex": hx, "lat": lat + km / 111.2, "lon": lon, "alt_baro": 3000, "gs": 200, "t": t, "flight": cs}

        def seen(*planes):
            sp.record(list(planes), str(lat), str(lon), key="live")

        def listed():
            with serve._data_lock:
                return [x["hex"] for x in serve.game_scannable(sp)]
        expect("the circles: passive 15 km, scan 10 km; GAME_RULE, GAME3_V and GAME_V as they were",
               (serve.GAME_KM, serve.SCAN_KM, serve.GAME_RULE, serve.GAME3_V, serve.GAME_V), (15, 10, 4, 1, 2))
        seen(ac("a00012", 12), ac("a00016", 16.2, cs="AUA16"), ac("a00008", 8, t="B738", cs="RYR8"))
        e12, e8 = sp.by_hex.get("a00012"), sp.by_hex.get("a00008") or {}
        expect("a live place's radius reaches 15 km (a 3 km profile): 12 km logged, 16 km not",
               (bool(e12), "a00016" in sp.by_hex), (True, False))
        expect("a live plane at 12 km scores its passive points (5), isn't in the scan list",
               ((e12 or {}).get("gp"), "a00012" in listed()), (5, False))
        expect("... and its scan answers: come closer", serve.game_lockon(sp, "a00012").get("why"), "closer")
        with serve._data_lock:
            sc = {x["hex"]: x for x in serve.game_scannable(sp)}.get("a00008") or {}
        expect("a plane at 8 km scores, is in the list with its rarity, full points, extras and time",
               (e8.get("gp", 0) > 0, sc.get("tier") == e8.get("tier"), sc.get("full") == serve.TIER_BASE.get(sc.get("tier")),
                sc.get("can"), sc.get("callsign"), sc.get("until", 0) - sc.get("seen", 0)),
               (True, True, True, {"type": 50, "airline": 25}, "RYR8", 120000))
        r = serve.game_lockon(sp, "a00008")
        expect("... its scan works and it leaves the list", (r.get("bonus", 0) > 0, "a00008" in listed()), (True, False))
        seen(ac("a00012", 9.5))
        expect("the 12 km plane comes within 10 km: in the list, not priced again",       # (at night the night-owl trophy pays too)
               ("a00012" in listed(), e12["gp"], len([a for a in e12["ga"] if a["k"] != "trophy"])), (True, 5, 1))
        e12["liveSeen"] -= serve.LOCK_FRESH_S + 1
        expect("... not seen live for 120 s: out of the list, and the scan says gone", ("a00012" in listed(), serve.game_lockon(sp, "a00012").get("why")),
               (False, "gone"))
        g3 = serve.game3_json(sp.book(), sp.day)
        expect("the game for the app: both circles, the rules too", (g3["km"], g3["scanKm"], g3["rules"]["km"], g3["rules"]["scanKm"]), (15, 10, 15, 10))

        # relay 81's game (one 10 km circle; a rule-3 plane, rule-4 planes, a scan), then relay 82 on it
        folder = Path(tempfile.mkdtemp(prefix="fb-relay81-"))
        keep = serve.GAME_KM, serve.SCAN_KM, serve.GAME_RULE, serve.GAME_PASSIVE

        def snap(s):
            with serve._data_lock:
                s.ensure_day()
                serve.game_book(s.book())
                return [_j.dumps(x, sort_keys=True) for x in (s.book(), s.entries, {k: v for k, v in serve.game3_json(s.book(), s.day).items()
                                                                                     if k not in ("rules", "km", "scanKm")},
                                                               serve.game_today(s), serve.game_awards(s, 0))]
        try:
            serve.GAME_KM = serve.SCAN_KM = 10
            old = serve.Spot(folder, None, lambda: 3)
            old.ensure_day()
            serve.GAME_RULE, serve.GAME_PASSIVE = 3, {"common": 1, "uncommon": 3, "rare": 10, "epic": 25, "legendary": 50}
            old.record([ac("b00001", 4, "E195", "BCY1")], str(lat), str(lon), key="live")
            serve.GAME_RULE, serve.GAME_PASSIVE = keep[2:]
            old.record([ac("b00002", 6, "A320", "AUA2"), ac("b00003", 9, "A21N", "WZZ3"), ac("b00004", 12, "B738", "RYR4")],
                       str(lat), str(lon), key="live")
            serve.game_lockon(old, "b00002")
            with serve._data_lock:
                rules = sorted({a["r"] for e in old.entries for a in e.get("ga") or []})
                pts = serve.game_book(old.book())["points"]
                old.changed("book", "day")
                for path, text in old.files():
                    path.write_text(text)
            before = snap(old)
        finally:
            serve.GAME_KM, serve.SCAN_KM, serve.GAME_RULE, serve.GAME_PASSIVE = keep
        expect("relay 81's game: rules 3 and 4, the 12 km plane not scored", (rules, "gp" in old.by_hex.get("b00004", {})), ([3, 4], False))
        new = serve.Spot(folder, None, lambda: 3)
        expect("relay 82 on it: logbook, sightings, game page, Recent points and awards identical",
               [x == y for x, y in zip(snap(new), before)], [True] * 5)
        with serve._data_lock:
            expect("... the points the same", serve.game_book(new.book())["points"], pts)
            listed_new = sorted(x["hex"] for x in serve.game_scannable(new))
        expect("... the unscanned planes within 10 km can be scanned, the scanned one not", listed_new, ["b00001", "b00003"])
    finally:
        serve.where_name, serve.watch_of = real


def school_checks(expect):
    """Relay 85 (to-do #153): the flight school. Each of the five missions pays +50 once, as an award without a plane, in
    the day, the week and the level; the fifth sets the wings (nothing more paid). A game scored before keeps every
    total when relay 85 starts on it; one at level 4 or above gets its wings at once without points and never pays a
    mission; a restart, planes coming closer and a rescore of the logbook pay nothing again."""
    import json as _j
    import tempfile
    import types
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "relay"))
    import serve
    serve.ARGS = serve.ARGS or types.SimpleNamespace(verbose=False)
    day = "2026-10-28"                                    # a Wednesday: the week of 26 Oct's card has the helicopter
    real_day, real_pass, real_gold = serve.board_day, serve.school_pass, serve.game_gold
    serve.board_day = lambda t=None: day
    serve.game_gold = lambda d, h: False
    n = [0]

    def plane(sp, **more):
        n[0] += 1
        now = serve.time.time()
        e = {"id": f"s{n[0]}", "hex": f"{n[0] + 7000:06x}", "ts": int(now * 1000) + n[0], "typeCode": "A320", "callsign": "ZZZ1",
             "tier": "common", "liveMin": 4.0, "liveSeen": now, **more}
        sp.entries.insert(0, e)
        sp.by_hex[e["hex"]] = e
        with serve._data_lock:
            serve.game_note(sp, e)
        return e

    def save(sp):
        with serve._data_lock:
            sp.changed("book", "day")
            files = sp.files()
        for path, text in files:
            path.write_text(text)

    def spot(folder):
        sp = serve.Spot(folder, None, 15)
        with serve._data_lock:
            sp.ensure_day()
            return sp, serve.game_book(sp.book())

    def snap(sp, school=True):
        with serve._data_lock:
            g = {k: v for k, v in serve.game_book(sp.book()).items() if school or k != "school"}
            g3 = {k: v for k, v in serve.game3_json(sp.book(), day).items() if k != "rules" and (school or k not in ("school", "wings"))}
            return _j.dumps([g, g3], sort_keys=True)

    def relay84(folder, extra=0):
        """A game scored by relay 84 (no school), saved: a plane, a scan, a bingo square; `extra` points on top."""
        serve.school_pass = lambda *a, **k: None
        try:
            sp, g = spot(folder)
            e = plane(sp, tier="rare")
            plane(sp, adsbCat="A7")
            serve.game_lockon(sp, e["hex"])
            if extra:
                serve._game_add(g, day, extra)
            g.pop("school", None)
            save(sp)
        finally:
            serve.school_pass = real_pass
        return snap(sp, False)

    school = lambda g: [(a["n"], a["p"], a["i"], bool(a.get("wings"))) for a in g["school"]["aw"]]   # noqa: E731
    try:
        # a game scored before (level 1): relay 85 starts on it with every total kept; the school starts empty
        f1 = Path(tempfile.mkdtemp(prefix="fb-school-"))
        before = relay84(f1)
        sp, g = spot(f1)
        expect("relay 85 on a game scored before: every total kept", snap(sp, False), before)
        expect("... the school starts empty (nothing from before counts)", (g["school"]["done"], g["school"]["aw"], g["school"].get("wings")),
               ({}, [], None))
        pts0 = g["points"]
        plane(sp)
        expect("a common plane: no mission", (g["points"] - pts0, g["school"]["done"]), (5, {}))
        up = plane(sp, tier="uncommon")
        expect("the first uncommon that scores: +50 once", (school(g), g["points"] - pts0), ([("uncommon", 50, 1, False)], 5 + 10 + 50))
        plane(sp, tier="epic")
        expect("... a second (rarer) one: nothing more", (len(g["school"]["aw"]), g["points"] - pts0), (1, 5 + 10 + 50 + 25))
        pts0 = g["points"]
        plane(sp, callsign="THY1")                       # a square new to the week's card (Turkish Airlines)
        expect("the first bingo square: +50", (school(g)[-1], g["points"] - pts0), (("bingo", 50, 2, False), 5 + 50))
        plane(sp, typeCode="C56X")                       # another square (a business jet)
        expect("... another square: nothing more", len(g["school"]["aw"]), 2)
        pts0 = g["points"]
        with serve._data_lock:
            lk = serve.game_lockon(sp, up["hex"])
        expect("the first scan: +50, not in the scan's bonus", (school(g)[-1], g["points"] - pts0, lk["points"]),
               (("scan", 50, 3, False), lk["bonus"] + 50, g["points"]))
        with serve._data_lock:
            again = serve.game_lockon(sp, plane(sp, tier="rare")["hex"])
        expect("... another scan: nothing more", (len(g["school"]["aw"]), again["bonus"] > 0), (3, True))
        pts0 = g["points"]
        with serve._data_lock:
            fav = serve.school_pass(sp, g, "fav")
            twice = serve.school_pass(sp, g, "fav")
            odd = serve.school_pass(sp, g, "wings")
        expect("a favourite: +50 once; no such mission", (fav["p"], twice, odd, g["points"] - pts0), (50, None, None, 50))
        expect("... four of five: no wings yet", (g["school"].get("wings"), serve.game3_json(sp.book(), day)["wings"]), (None, False))
        with serve._data_lock:
            card = serve.school_pass(sp, g, "card")
        expect("the fifth (a plane's card): +50 and the wings, nothing more for them",
               (card["p"], bool(card.get("wings")), g["points"] - pts0, [x[0] for x in school(g)]),
               (50, True, 100, ["uncommon", "bingo", "scan", "fav", "card"]))
        g3 = serve.game3_json(sp.book(), day)
        expect("game3_json: the wings and the school", (g3["wings"], sorted(g3["school"]["done"]), bool(g3["school"]["wings"]), g3["school"]["pre"]),
               (True, sorted(serve.SCHOOL), True, False))
        expect("five awards of 50 today, in the day, the week (the league's) and the level",
               (sum(a["p"] for a in g["school"]["aw"] if a["day"] == day), g3["week"], g3["points"], g3["level"]),
               (250, g["days"][day], g["points"], serve.level_of(g["points"])[0]))
        with serve._data_lock:
            aw = serve.game_awards(sp, 1)
            td = serve.game_today(sp)
        expect("the awards for the pop-ups (no plane) and Recent points' school", ([a["n"] for a in aw if a["k"] == "school"],
               [a["n"] for a in td["school"]], any(a.get("hex") for a in aw if a["k"] == "school")),
               (["uncommon", "bingo", "scan", "fav", "card"], ["uncommon", "bingo", "scan", "fav", "card"], False))
        with serve._data_lock:
            late = [serve.school_pass(sp, g, m) for m in serve.SCHOOL]
        expect("with the wings: no mission pays again", late, [None] * 5)
        # a restart, planes coming closer, a rescore of the logbook: nothing paid again
        save(sp)
        before, total = snap(sp), g["points"]
        sp, g = spot(f1)
        expect("a restart: the same game", snap(sp), before)
        for x in sp.entries:
            x["liveMin"] -= 1.0
        with serve._data_lock:
            for x in list(sp.entries):
                serve.game_note(sp, x)
        expect("... planes coming closer pay nothing again", (g["points"], len(g["school"]["aw"])), (total, 5))
        save(sp)
        lb = _j.loads((f1 / "logbook.json").read_text())
        lb["gameV"], lb["trophiesV"], lb["cardsV"] = 0, 0, 0
        (f1 / "logbook.json").write_text(_j.dumps(lb))
        sp, g = spot(f1)
        expect("a rescore from the saved days: the game's totals the same", (g["points"], len(g["school"]["aw"]), bool(g["school"]["wings"])),
               (total, 5, True))
        # a game at level 4 or above when relay 85 starts: the wings at once, no points, the school never shown
        f2 = Path(tempfile.mkdtemp(prefix="fb-school-"))
        need4 = 500 + 625 + 781
        before = relay84(f2, need4)
        sp, g = spot(f2)
        g3 = serve.game3_json(sp.book(), day)
        expect("level 4 when relay 85 starts: every total kept", snap(sp, False), before)
        expect("... the wings at once, without points", (g3["level"] >= 4, g3["wings"], g3["school"]["pre"], g3["school"]["done"], g["school"]["aw"]),
               (True, True, True, {}, []))
        pts0 = g["points"]
        e = plane(sp, tier="uncommon")
        with serve._data_lock:
            pay = [serve.school_pass(sp, g, m) for m in serve.SCHOOL]
        expect("... and no mission pays (only the plane's own points)", (pay, g["school"]["aw"], g["points"] - pts0),
               ([None] * 5, [], e["gp"] + e.get("gb", 0)))
        # level 3 when it starts: the school (it counts the level then, not later)
        f3 = Path(tempfile.mkdtemp(prefix="fb-school-"))
        relay84(f3, 500 + 625)
        sp, g = spot(f3)
        expect("level 3 when relay 85 starts: the school", (serve.level_of(g["points"])[0], g["school"].get("wings"), g["school"].get("pre")),
               (3, None, None))
        expect("the league's and the player card's wings (read only): as the school has them, else by the level",
               [serve.school_wings(x) for x in (g, {"points": need4}, {"points": need4 - 1}, {"points": 0, "school": {"wings": 1}})],
               [False, True, False, True])
    finally:
        serve.board_day, serve.school_pass, serve.game_gold = real_day, real_pass, real_gold


def golden_checks(expect):
    """Relay 84 (to-do #148): golden tickets. About one plane in 20, from a hash of a salt kept in data/ (made once, mode
    600), the day and the plane: the same for every profile all day, kept over a restart, different with another salt.
    A golden scan pays the plane's full points twice, the extras and the streak as ever; a plain scan is unchanged; a game
    scored before keeps every total and award."""
    import json as _j
    import os as _os
    import stat
    import tempfile
    import types
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "relay"))
    import serve
    serve.ARGS = serve.ARGS or types.SimpleNamespace(verbose=False)
    real = serve.where_name, serve.watch_of, serve.GOLD_FILE, serve._gold_salt
    serve.where_name, serve.watch_of = (lambda lat, lon: {}), (lambda hx: None)
    lat, lon = 48.2085, 16.3731
    tmp = Path(tempfile.mkdtemp(prefix="fb-golden-"))
    try:
        serve.GOLD_FILE, serve._gold_salt = tmp / "gold.key", None
        key = serve._gold_key()
        expect("the salt: made once in data/, 32 hex digits, only the relay's user can read it",
               (serve.GOLD_FILE.read_text().strip() == key, len(key), stat.S_IMODE(_os.stat(serve.GOLD_FILE).st_mode)), (True, 32, 0o600))
        hexes = [f"{i:06x}" for i in range(0x400000, 0x400000 + 20000)]
        day = "2026-10-29"
        golds = {h for h in hexes if serve.game_gold(day, h)}
        expect("about one plane in 20 is gold (20,000 planes: 4.4 to 5.6 %)", 880 <= len(golds) <= 1120, True)
        expect("... the same planes when asked again, in capitals too",
               (golds == {h for h in hexes if serve.game_gold(day, h)}, all(serve.game_gold(day, h.upper()) for h in list(golds)[:50])), (True, True))
        expect("... other planes the next day", len(golds & {h for h in hexes if serve.game_gold("2026-10-30", h)}) < len(golds) // 5, True)
        serve._gold_salt = None                         # a restart: the salt comes back from data/
        expect("a restart doesn't re-roll them", {h for h in hexes if serve.game_gold(day, h)} == golds, True)
        serve._gold_salt = "0" * 32
        expect("another salt picks other planes (they can't be worked out without it)",
               len(golds & {h for h in hexes if serve.game_gold(day, h)}) < len(golds) // 5, True)
        serve._gold_salt = None

        def ac(hx, km, t="A320", cs="AUA1"):
            return {"hex": hx, "lat": lat + km / 111.2, "lon": lon, "alt_baro": 3000, "gs": 200, "t": t, "flight": cs}

        def spot(name):
            sp = serve.Spot(tmp / name, None, lambda: 3)
            sp.ensure_day()
            return sp
        a, b = spot("a"), spot("b")
        gh = next(f"c{i:05x}" for i in range(99999) if serve.game_gold(a.day, f"c{i:05x}"))
        nh = next(f"c{i:05x}" for i in range(99999) if not serve.game_gold(a.day, f"c{i:05x}"))
        for sp in (a, b):
            sp.record([ac(gh, 8, "B738", "RYR8"), ac(nh, 7, "A21N", "WZZ3")], str(lat), str(lon), key="live")

        def listed(sp):
            with serve._data_lock:
                return {x["hex"]: x.get("gold", False) for x in serve.game_scannable(sp)}
        expect("the scan list marks the golden plane, for every profile alike", (listed(a), listed(b)), ({gh: True, nh: False},) * 2)
        e = a.by_hex[gh]
        full, gp = serve.TIER_BASE[e["tier"] if e.get("tier") in serve.TIER_BASE else "uncommon"], e["gp"]
        with serve._data_lock:
            p0 = serve.game_book(a.book())["points"]
        r = serve.game_lockon(a, gh)
        expect("a golden scan: the plane's full points twice, the new type, the new airline and the streak as ever",
               (r.get("gold"), [(x["k"], x["p"], x.get("gold")) for x in r.get("lines", [])], r.get("bonus")),
               (True, [("scan", 2 * full, 2), ("new", 50, None), ("new", 25, None), ("streak", serve.GAME_STREAK, None)],
                2 * full + 75 + serve.GAME_STREAK))
        with serve._data_lock:
            expect("... the points and the plane's scan count it once, its passive points stay",
                   (serve.game_book(a.book())["points"] - p0, e["lock"], e["gp"], e["ga"][-4]["gold"]), (r["bonus"], 2 * full + 75, gp, 2))
        e2 = a.by_hex[nh]
        full2 = serve.TIER_BASE[e2["tier"] if e2.get("tier") in serve.TIER_BASE else "uncommon"]
        r2 = serve.game_lockon(a, nh)
        expect("a plain scan as before: the full points once, nothing golden",
               (r2.get("gold"), [(x["k"], x["p"], x.get("gold")) for x in r2.get("lines", [])]),
               (False, [("scan", full2, None), ("new", 50, None), ("new", 25, None)]))
        expect("the golden plane leaves the list once scanned; the other profile's ticket stays gold", (gh in listed(a), listed(b)),
               (False, {gh: True, nh: False}))

        # a game scored before golden tickets (none gold), then relay 84 with a salt that makes its scanned plane gold
        folder = tmp / "before"
        folder.mkdir()

        def snap(sp):
            with serve._data_lock:
                sp.ensure_day()
                serve.game_book(sp.book())
                return [_j.dumps(x, sort_keys=True) for x in (sp.book(), sp.entries, serve.game3_json(sp.book(), sp.day),
                                                               serve.game_today(sp), serve.game_awards(sp, 0))]
        keep = serve.game_gold
        try:
            serve.game_gold = lambda d, h: False
            old = serve.Spot(folder, None, lambda: 3)
            old.ensure_day()
            old.record([ac("d00001", 6, "A320", "AUA2"), ac("d00002", 9, "E195", "BCY1")], str(lat), str(lon), key="live")
            serve.game_lockon(old, "d00001")
            with serve._data_lock:
                pts = serve.game_book(old.book())["points"]
                old.changed("book", "day")
                for path, text in old.files():
                    path.write_text(text)
            before = snap(old)
        finally:
            serve.game_gold = keep
        for i in range(20000):                          # a salt that makes both its planes gold today
            serve._gold_salt = f"{i:032x}"
            if serve.game_gold(old.day, "d00001") and serve.game_gold(old.day, "d00002"):
                break
        new = serve.Spot(folder, None, lambda: 3)
        expect("relay 84 on it (its scanned plane gold now): logbook, sightings, game page, Recent points and awards identical",
               [x == y for x, y in zip(snap(new), before)], [True] * 5)
        with serve._data_lock:
            expect("... the points the same", serve.game_book(new.book())["points"], pts)
        expect("... its unscanned plane comes up gold, the scanned one stays scanned", listed(new), {"d00002": True})
    finally:
        serve.where_name, serve.watch_of, serve.GOLD_FILE, serve._gold_salt = real


def live_hidden_checks(expect):
    """Relay 81 (to-do #140): live_stale() on its own. A live request from a hidden page (bg=1) is stale, though its fix is
    fresh; a saved place and home never are; a page that sends no flag counts as visible."""
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "relay"))
    import serve
    pc = "pc=48.2,16.3&pr=15&"

    def stale(qs, pl=""):
        q = urllib.parse.parse_qs(pl + qs)
        return serve.live_stale(q, serve.screen_place(q))
    expect("live_stale: a live request with a fresh fix is visible, with bg=1 hidden, with an empty flag visible (an old page)",
           (stale("&fix=5", "pl=live&" + pc), stale("&fix=5&bg=1", "pl=live&" + pc), stale("&fix=5&bg=", "pl=live&" + pc)), (False, True, False))
    expect("... a saved place and home are never stale from a hidden page", (stale("bg=1&fix=-1", "pl=Rome&" + pc), stale("bg=1")), (False, False))
    expect("... a live request without a fix is stale as before (relay 72)", stale("", "pl=live&" + pc), True)


def checks():
    bad = []

    def expect(what, got, want):
        if got != want:
            bad.append(f"{what}: got {got}, expected {want}")

    school_checks(expect)
    import serve                    # relay 85: no flight school in the other checks (its +50s would change their totals)
    serve.school_pass = lambda *a, **k: None
    golden_checks(expect)
                                    # relay 84: no golden tickets in the other checks (data/'s salt would make 1 in 20 gold)
    serve.game_gold = lambda day, hx: False
    game_rule_checks(expect)
    bingo_trophy_checks(expect)
    scan_circle_checks(expect)
    screens_checks(expect)
    live_hidden_checks(expect)

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
    rows0 = rows
    expect("a scored plane in today's list", any("gp" in e for e in rows), True)
    st, _, b = call("/game/me?since=1", "test-device")
    me0 = json.loads(b) if st == 200 else {}
    # relay 82: the planes a scan counts for (within 10 km, seen live in the last 2 min), both circles for the app
    hx = next((x["hex"] for x in me0.get("scan") or []), None)
    expect("/game/me: both circles and the scan list (relay 82)", (me0.get("km"), me0.get("scanKm"), bool(hx),
           all(x.get("km") is not None and x["km"] <= 10 for x in me0.get("scan") or [])), (15, 10, True, True))
    if hx:
        expect("/game/me: the rules, the limits and the awards for the pop-ups (relay 76)",
               ((me0.get("rules") or {}).get("base", {}).get("rare"), (me0.get("limits") or {}).get("common", [0, 0])[1],
                any(a.get("k") == "pass" and a.get("hex") for a in me0.get("aw", []))), (100, 50, True))
        can = next((a.get("can") or {} for a in me0.get("aw", []) if a.get("k") in ("pass", "limit") and a.get("hex") == hx), None)
        expect("the plane's passive award says what a scan would add (relay 79: can)", can is not None and set(can) <= {"type", "airline"}, True)
        st, _, b = call("/game/lockon", "test-device", body={"hex": hx})
        lk = json.loads(b) if st == 200 else {}
        expect("a scan gives the plane's full points on top of its passive points (relay 79)",
               ((lk.get("lines") or [{}])[0].get("p", -1) == lk.get("full", -2), lk.get("bonus", 0) > lk.get("full", 0) - lk.get("had", 0)), (True, True))
        expect("... and the extras the pass promised", {x["w"]: x["p"] for x in lk.get("lines", []) if x["k"] == "new"}, can or {})
        expect("... the day's first scan brings day 1 of the streak", [x["p"] for x in lk.get("lines", []) if x["k"] == "streak"], [25])
        st, _, b = call("/game/lockon", "test-device", body={"hex": hx})
        expect("the same plane scanned twice", json.loads(b).get("why") if st == 200 else st, "done")
        st, _, b = call("/game/me", "test-device")
        expect("... and it left the scan list (relay 82)", hx in [x["hex"] for x in (json.loads(b) if st == 200 else {}).get("scan") or []], False)
    # relay 85: the flight school over HTTP: the scan above and the favourite added earlier were missions; a plane's
    # card is the app's call, paid once
    sc = (json.loads(call("/game/me", "test-device")[2]).get("school") or {})
    if not sc.get("pre"):
        expect("the school: the scan and the favourite counted", ("scan" in sc.get("done", {}), "fav" in sc.get("done", {})), (bool(hx), True))
    card_paid = [json.loads(b).get("paid") if st == 200 else st for st, _, b in (call("/game/school", "test-device", body={"m": "card"}) for _ in range(2))]
    expect("a plane's card: +50, then nothing", card_paid, [0, 0] if sc.get("pre") else [50, 0])
    expect("... the relay sees the other missions itself", call("/game/school", "test-device", body={"m": "scan"})[0], 400)
    expect("... from another site", call("/game/school", "test-device", {"Origin": "https://evil.example"}, {"m": "card"})[0] in (403, 429), True)
    expect("... from a stranger", call("/game/school", None, None, {"m": "card"})[0] in (401, 403), True)
    me = json.loads(call("/game/me?since=1", "test-device")[2])
    expect("/game/me: the school's awards (no plane) and the card done", ([a["n"] for a in me.get("aw", []) if a.get("k") == "school"][-1:],
           "card" in (me.get("school") or {}).get("done", {})), ([] if sc.get("pre") else ["card"], not sc.get("pre")))
    lgw = json.loads(call("/game/league", "test-device")[2])
    mine = next((r for r in lgw.get("rows", []) if r.get("me")), {})
    pw = json.loads(call(f"/game/player?id={mine.get('id', '')}", "test-device")[2]) if mine.get("id") else {}
    expect("the wings in /game/me, the league's rows and the player card (the rank's pin)",
           (type(me.get("wings")), type(mine.get("wings")), type(pw.get("wings"))), (bool, bool, bool))
    # relay 71: Recent points, today's awards per plane (relay 76: the passive tenth, the scan and its extras); the
    # profile's own only
    today = lambda ck: json.loads(call("/game/today", ck)[2])     # noqa: E731
    td = today("test-device")
    row = next((r for r in td.get("rows", []) if r.get("hex") == hx), {})
    kinds = [a.get("k") for a in row.get("aw", [])]
    expect("Recent points: the passive points (or a limit) and the scan", (bool({"pass", "limit"} & set(kinds)), "scan" in kinds, row.get("rule"), [a.get("r") for a in row.get("aw", []) if a.get("k") == "scan"]),
           (True, True, 4, [4]))
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
    hx2 = next((e["hex"] for e in rows1 if "gp" in e and not e.get("scan") and e.get("typeCode") and (e.get("liveMin") or 0) <= 10), None)
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
    # relay 81 (to-do #140): nothing counts while the app is in the background. A hidden page says bg=1: a live request
    # with it, though its fix is fresh, is stale too. Only a live place: a saved place or home (a TV board) is as before
    st, h, _ = call(far + "&fix=20&bg=1", "owner-device")
    expect("a hidden live request with a fresh fix starts no gap filler", (st, h.get("X-Relay-Fill")), (200, None))
    st, _, b = call("/logbook", "owner-device")
    expect("... records no live sightings and scores nothing", (len(live_rows()), json.loads(b).get("game", {}).get("points") if st == 200 else st), (0, 0))
    st, h, _ = call(far + "&fix=20", "owner-device")      # (the same request, visible: the app is back)
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
    # relay 78 (to-do #129): the facts database. facts.json's entries moved in at start (relay 74's airlines not: AUA
    # above was looked up); a key not in it yet is looked up on its first tap (above, and VIE here, the photo through
    # Commons' redirect); the monthly refresh against the fakes, in batches; then every card the same from the database
    st, j = facts("model=" + urllib.parse.quote("Seeded Model"))
    expect("facts.json's kept facts moved into the database", (st, j.get("text"), wm().get("wiki:Seeded Model")), (200, "Kept in facts.json.", None))
    st, vie = facts("airport=VIE")
    expect("a key not in the database: looked up on its first tap", (st, (vie.get("facts") or {}).get("runways"), wm().get("wiki:Vienna International Airport"),
                                                                     "/commons/Flughafen_Wien.jpg?width=640" in vie.get("img", "")), (200, 2, 1, True))
    cards = ["model=" + urllib.parse.quote("Airbus A320 family"), "model=" + urllib.parse.quote("Airbus A330neo"), "airline=AUA", "airline=WMT",
             "airline=WMT&own=1", "airline=WZZ", "airline=UAE", "org=Q62589018", "airline=AZA", "airport=DXB", "airport=VIE"]
    before, wm0 = {c: facts(c)[1] for c in cards}, wm()
    expect("/facts?status=1 is the owner's", (call("/facts?status=1", "test-device")[0], call("/facts?refresh=1")[0] in (401, 403)), (403, True))
    st, _, b = call("/facts?refresh=1", "owner-device")
    for _ in range(120):
        s = json.loads(call("/facts?status=1", "owner-device")[2])
        if not s.get("running"):
            break
        time.sleep(0.5)
    last, n = s.get("last") or {}, s.get("entries") or {}
    expect("the monthly refresh (owner, now): done in one go, nothing left over", (st, bool(s.get("running")), s.get("run"), last.get("left"), last.get("nights")),
           (200, False, None, 0, 1))
    expect("... every airline still flying, airport and model page, and what the cards open (groups, companies)",
           (n.get("airline"), n.get("airport"), n.get("model", 0) > 300, n.get("org", 0) >= 2, n.get("airline-own")), (6, 2, True, True, 2))
    expect("... in batches: three lists, several items and pages a request, a maxlag waited out, introductions continued, photos together",
           (wm().get("sparql"), wm().get("lagged"), wm().get("batch:wd", 0) >= 3, wm().get("batch:wiki", 0) >= 7, wm().get("batch:wiki-continued", 0) >= 1, wm().get("commons", 0) >= 1, last.get("requests", 0) < 60),
           (3, 1, True, True, True, True, True))
    d = lambda k: wm().get(k, 0) - wm0.get(k, 0)       # noqa: E731
    expect("... a city's name only (Austrian's headquarters), not its statements", (d("props:Q874848:claims|labels"), d("props:Q874848:labels") > 0), (0, True))
    asked = dict(wm())
    after = {c: facts(c)[1] for c in cards}
    same = lambda v: {k: x for k, x in v.items() if k != "img"}           # noqa: E731
    expect("... every card's answer as on its first tap (the brand rule too)", [c for c in cards if same(after[c]) != same(before[c])], [])
    expect("... the photos' own addresses at the cards' size", (after["airport=VIE"].get("img", "").split("/")[-1], after["airline=AUA"].get("img", "").split("/")[-1]),
           ("500px-Flughafen%20Wien.jpg", "500px-OE-LPM%20%40%20VIE%2C%202024-08-30.jpg"))
    expect("... and read from the database: nothing asked again", dict(wm()) == asked, True)
    expect("... the database on disk", s.get("bytes", 0) > 4096, True)
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
