"""Run the boards against made-up flights: a fake flight data source on port 8095 and a test relay on port 8096 that
serves this repository's boards (/, /test/, /app/) with it. Your real relay, its settings and its data
are not touched: the test relay runs from a temporary folder.

    py tools/test/run_test_relay.py            every kind of plane, including special ones and an emergency
    py tools/test/run_test_relay.py --quiet    no special planes, so the pages rotate undisturbed
    py tools/test/run_test_relay.py --hover    adds a police helicopter hovering overhead
    py tools/test/run_test_relay.py --far      the landing starts 32 km out (its photo, then the runway radar)
    py tools/test/run_test_relay.py --ring     two more planes from the south: one comes within 15 km (passive points and its
                                               scan ticket) and then within 10 km, the other passes 12 km out (1.98)
    py tools/test/run_test_relay.py --fr24     the relay acts as if it had a Flightradar24 key (served by the fake); David's
                                               screens more than 30 km from the test point (Live location) also get the
                                               gap filler's take-off that only Flightradar24 hears (relay 66)
    py tools/test/run_test_relay.py --gold     golden tickets (relay 84): every plane in the scan list is gold (--gold HEX,HEX:
                                               only those); without it none is, so tests don't depend on the salt
    py tools/test/run_test_relay.py --hue      a fake Hue Bridge (fakehue.py, two ports below the relay) for the admin
                                               page's Hue lights: Find the bridge finds it, Pair works on the second try
    py tools/test/run_test_relay.py --club     the Test profile has a game from the old rules (1.112's move at start: level 9
                                               kept above its points, styles, three showcase spots, mastery up to platinum)
                                               and 40 airlines in the wallet, Platinum down to 4 with no scan (no card) (1.114, 1.124)
    py tools/test/run_test_relay.py --live-photos   the planes' photos from the real Planespotters.net (needs the internet;
                                               for screenshots) instead of the fake's (relay 73)
    py tools/test/run_test_relay.py --live-facts   the cards' facts (relay 74) from the real Wikipedia and Wikidata (needs the
                                               internet; for screenshots) instead of the fake's few pages
    py tools/test/run_test_relay.py --slow-names   place names (OpenStreetMap's reverse lookup) take 5 s, and the first lookup
                                               of each point fails: live location says ON THE GO until the name comes, and
                                               asks again a minute on (1.93.0.1)
    py tools/test/run_test_relay.py --port 8296   other ports (the fake source then on 8295), so test relays of
                                                  several checkouts don't answer for each other (or env PORT)

Then open http://localhost:8096/ (or /test/, /app/, /screens). Ctrl+C stops both.

Since relay 42 every screen is a signed-in profile. The test relay starts with two: "Test" (watching central Vienna;
its device cookie is overhead=test-device, which shoot.py and smoke.py send) and "New guest" (no place yet, for the
welcome: overhead=new-device); since relay 43 also "David", the owner, the only profile the admin pages open for
(overhead=owner-device). In a browser, open http://localhost:8096/test-signin once for the Test cookie (or
/test-signin?as=new). sounds-src/emirates-boarding.m4a, if there, is served as /media/emirates-boarding.m4a.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--quiet", action="store_true", help="no special planes")
    p.add_argument("--hover", action="store_true", help="add a helicopter hovering overhead")
    p.add_argument("--far", action="store_true", help="the landing starts 32 km out")
    p.add_argument("--ring", action="store_true", help="a plane coming within 15, then 10 km, and one passing 12 km out (both can be scanned)")
    p.add_argument("--fr24", action="store_true", help="pretend the relay has a Flightradar24 key")
    p.add_argument("--gold", nargs="?", const="all", default="", help="golden tickets: all planes in the scan list, or HEX,HEX")
    p.add_argument("--hue", action="store_true", help="a fake Hue Bridge for the admin page's Hue lights")
    p.add_argument("--club", action="store_true", help="the Test profile has a game from the old rules (relay 96's move: a kept "
                                                       "level, styles, showcase spots, mastery steps up to platinum) and 36 Frequent flyer cards (4 more airlines with no scan)")
    p.add_argument("--live-photos", action="store_true", help="the planes' photos from the real Planespotters.net")
    p.add_argument("--live-facts", action="store_true", help="the cards' facts from the real Wikipedia and Wikidata")
    p.add_argument("--slow-names", action="store_true", help="place names take 5 s, the first lookup of each point fails")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8096), help="relay port (default 8096; the fake source one below)")
    a = p.parse_args()
    # TERM and INT end it like Ctrl+C (children stopped, copy removed); a wrapper started with & from sh would otherwise ignore INT
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    tmp = Path(tempfile.mkdtemp(prefix="overhead-test-"))
    procs = []
    try:
        run(a, tmp, procs)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # a second signal must not interrupt the clean-up
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def run(a, tmp, procs):
    fake_port = a.port - 1
    FAKE = f"http://127.0.0.1:{fake_port}"
    src = (REPO / "relay" / "serve.py").read_text(encoding="utf-8")
    fakes = [("https://api.adsbdb.com", FAKE), ("https://fr24api.flightradar24.com/api", FAKE + "/api"),
             ("https://viennaairport.com/jart", FAKE + "/jart"),
             ("https://nominatim.openstreetmap.org", FAKE + "/nominatim"),
             ("https://raw.githubusercontent.com/vradarserver/standing-data/main/airlines/schema-01/airlines.csv", FAKE + "/airlines.csv")]
    if not a.live_photos:
        fakes.append(("https://api.planespotters.net/pub/photos", FAKE + "/ps/pub/photos"))
    if not a.live_facts:                  # relay 74: the cards' facts from the fake's few pages
        fakes += [("https://en.wikipedia.org/w/api.php", FAKE + "/wiki/w/api.php"), ("https://www.wikidata.org/w/api.php", FAKE + "/wikidata/w/api.php"),
                  ("https://commons.wikimedia.org/wiki/Special:FilePath/", FAKE + "/commons/"),
                  ("https://commons.wikimedia.org/w/api.php", FAKE + "/commons-api/w/api.php"), ("https://query.wikidata.org/sparql", FAKE + "/sparql")]
    for real, fake in fakes:
        if real not in src:
            raise SystemExit(f"relay/serve.py no longer mentions {real}; update run_test_relay.py")
        src = src.replace(real, fake)
    # the share picture's photos and Planespotters' (relay 73): the fake source draws them (SVG, at 127.0.0.1), so this
    # copy lets those through, and asks the fake Planespotters without waiting a second between lookups
    swaps = [('PHOTO_HOSTS = (', 'PHOTO_HOSTS = ("127.0.0.1", '), ('PHOTO_TYPES = (', 'PHOTO_TYPES = ("image/svg+xml", '),
             ('PS_IMG = (', 'PS_IMG = ("http://127.0.0.1:", '), ("https://discovery.meethue.com", f"http://127.0.0.1:{a.port - 2}/discovery")]
    if not a.live_photos:
        swaps.append(("600, 1.0, 4.0, 1800", "600, 0.1, 4.0, 1800"))       # PS_GAP
    for real, fake in swaps:
        if real not in src:
            raise SystemExit(f"relay/serve.py no longer has {real}; update run_test_relay.py")
        src = src.replace(real, fake, 1)
    src = re.sub(r"^FR24_GAP_S = [\d.]+", "FR24_GAP_S = 0.5", src, flags=re.M)
    src = re.sub(r"^SKY_REPORTS_MAX = \d+", "SKY_REPORTS_MAX = 2", src, flags=re.M)   # flows.py checks the cap
    gold = "    return int(h[:8], 16) % GOLD_ONE_IN == 0"    # relay 84: golden tickets only as asked (--gold)
    if gold not in src:
        raise SystemExit("relay/serve.py's game_gold changed; update run_test_relay.py")
    src = src.replace(gold, "    return " + ("True" if a.gold == "all" else f"str(hx or '').lower() in {a.gold.lower().split(',') if a.gold else []!r}"), 1)
    # A page that sets a test profile's cookie (only in this copy of the relay).
    hook = '        if path == "/signin":'
    if hook not in src:
        raise SystemExit("relay/serve.py changed around /signin; update run_test_relay.py")
    src = src.replace(hook, "\n".join([
        '        if path == "/test-signin":',
        '            tok = "new-device" if (self.query().get("as") or [""])[0] == "new" else "test-device"',
        '            self.send_response(303)',
        '            self.send_header("Location", "/test/")',
        '            self.send_header("Set-Cookie", f"{COOKIE}={tok}; Path=/; Max-Age=86400; HttpOnly; SameSite=Lax")',
        '            self.send_header("Content-Length", "0")',
        '            self.end_headers()',
        '            return',
        hook]), 1)
    (tmp / "serve.py").write_text(src, encoding="utf-8")
    h = lambda t: hashlib.sha256(t.encode()).hexdigest()
    now = time.time()
    dev = lambda t: [{"token": h(t), "device": "Test browser", "added": now, "lastSeen": now, "via": "test"}]
    (tmp / "data").mkdir()
    (tmp / "data" / "profiles.json").write_text(json.dumps({"homeMerged": {"v": 1, "at": now, "into": None}, "invites": {}, "profiles": {
        "test0001": {"name": "Test", "created": now, "lastSeen": now, "fr24": True, "devices": dev("test-device"),
                     "settings": {"lat": 48.2085, "lon": 16.3731, "place": "Vienna", "home": "VIE", "radiusKm": 15, "located": True}},
        "new00001": {"name": "New guest", "created": now, "lastSeen": 0, "fr24": False, "devices": dev("new-device"), "settings": None},
        "own00001": {"name": "David", "created": now, "lastSeen": now, "fr24": True, "devices": dev("owner-device"),
                     "settings": {"lat": 48.2085, "lon": 16.3731, "place": "Vienna", "home": "VIE", "radiusKm": 15, "located": True}}}}),
        encoding="utf-8")
    # relay 68: a sighting from yesterday saved before the relay knew airline names (the Test profile), which the relay
    # fills in once; the Austrian one already has its name and must stay as it is
    day = time.strftime("%Y-%m-%d", time.localtime(now - 86400))
    old = [{"id": "old-ein", "hex": "4ca2b8", "callsign": "EIN1XY", "ts": int((now - 86400) * 1000), "time": "12:00",
            "typeCode": "A320", "minDist": 6.2, "altAtMin": 9000, "looked": True},
           {"id": "old-aua", "hex": "440a99", "callsign": "AUA9", "ts": int((now - 86400) * 1000) - 60000, "time": "11:59",
            "typeCode": "A320", "minDist": 7.1, "altAtMin": 9500, "looked": True, "airlineName": "Austrian"},
           # relay 70: a plane without a callsign, saved as the sources' "@@@@@@@@", cleaned once at start
           {"id": "old-at", "hex": "ae0413", "callsign": "@@@@@@@@", "reg": "TEST-AT", "ts": int((now - 86400) * 1000) - 120000,
            "time": "11:58", "typeCode": "C130", "minDist": 5.0, "altAtMin": 5000, "looked": True}]
    (tmp / "data" / "profiles" / "test0001").mkdir(parents=True)
    (tmp / "data" / "profiles" / "test0001" / f"sightings-{day}.json").write_text(json.dumps(old), encoding="utf-8")
    if a.club:
        # relay 96 (1.112): a game from before the move: 9,950 points (level 9 by the old totals, 8 by the new), mastery
        # steps by the old numbers (A320 gold at 120 scans, DH8D bronze at 7), no showcase pins; the relay moves it at start
        v = {k: int(re.search(rf"^{k} = (\d+)", src, re.M).group(1)) for k in ("GAME_V", "TROPHIES_V", "GAME3_V")}
        t0, today = int((now - 86400 * 20) * 1000), time.strftime("%Y-%m-%d", time.localtime(now))
        names = {"A320": "Airbus A320", "B744": "Boeing 747-400", "DH8D": "Dash 8-400", "E195": "Embraer 195", "B789": "Boeing 787-9"}
        scans = {"A320": 120, "B744": 60, "DH8D": 7, "E195": 30, "B789": 3}
        types = {tc: {"count": n + 2, "first": t0 + i, "last": t0 + 86400000 * (5 + i), "name": names[tc]} for i, (tc, n) in enumerate(scans.items())}
        types["B77W"] = {"count": 2, "first": t0, "last": t0 + 86400000 * 12, "name": "Boeing 777-300ER"}   # seen, never scanned
        # relay 97 (1.114): a wallet of 40 airlines, Platinum down to no scan (no card), with the scans' times and types
        wal = {"AUA": 486, "DLH": 231, "RYR": 172, "EWG": 120, "WZZ": 88, "LDA": 64, "AEE": 51, "SWR": 44, "THY": 39, "EZY": 31, "BAW": 27,
               "AFR": 22, "KLM": 20, "LOT": 18, "ITY": 15, "TAP": 13, "IBE": 12, "UAE": 11, "QTR": 10, "SAS": 9, "FIN": 8, "CTN": 7, "VLG": 6,
               "TVS": 6, "EJU": 5, "BTI": 5, "CSA": 4, "ROT": 4, "BEL": 3, "ELY": 3, "CFG": 2, "PGT": 2, "SXS": 2, "ETD": 1, "ICE": 1, "TUI": 1,
               "DAL": 0, "UAL": 0, "ACA": 0, "SVA": 0}
        fleet, now_ms = ["A320", "A321", "B738", "E195", "A20N"], int(now * 1000)
        g_airlines = {al: {"name": "", "first": t0 + 3600000 * i, "count": n + 5 + i % 37, "last": now_ms - 3600000 * (i + 1)}
                      for i, (al, n) in enumerate(wal.items())}
        g_info = {al: {"first": t0 + 86400000 * (i % 17) + 3600000, "last": now_ms - 3600000 * (2 * i + 1),
                       "types": {fleet[(i + k) % 5]: (n - n // 3 - n // 5 if k == 0 else n // 3 if k == 1 else n // 5) for k in range(3)
                                 if (n - n // 3 - n // 5 if k == 0 else n // 3 if k == 1 else n // 5)}}
                  for i, (al, n) in enumerate(wal.items()) if n}
        (tmp / "data" / "profiles" / "test0001" / "logbook.json").write_text(json.dumps({
            "since": day, "startedTs": now - 86400 * 20, "sightings": 230, "types": types, "airlines": {}, "regs": {},
            "gameV": v["GAME_V"], "recordsV": 1, "trophiesV": v["TROPHIES_V"], "cardsV": 1, "flightsV": 1,
            "game3": {"v": v["GAME3_V"], "since": t0, "sightings": 230, "types": types, "airlines": g_airlines, "regs": {}, "countries": {},
                      "categories": {}, "hours": [], "points": 9950, "days": {today: 9950}, "planes": {}, "tiers": {"common": 200},
                      "rareDays": [], "records": {}, "trophies": {}, "bingoCards": {}, "best": {}, "lock": {"at": 0, "n": 220},
                      "scanned": {"types": sorted(scans), "airlines": sorted(g_info)}, "scanTypes": scans,
                      "scanAirlines": {al: n for al, n in wal.items() if n}, "scanAirlineInfo": g_info,
                      "mastery": {"A320": 3, "B744": 2, "DH8D": 1, "E195": 2}}}), encoding="utf-8")
    # ... and Flightradar24's answer about it, still in the cache: written into the sighting at start
    (tmp / "data" / "fr24.json").write_text(json.dumps({"usage": {}, "flights": {"4ca2b8|EIN1XY": {
        "t": now - 86400 + 300, "flight": "EI661", "callsign": "EIN1XY", "from": {"code": "DUB", "city": "Dublin"},
        "to": {"code": "VIE", "city": "Vienna"}, "operator": "EIN", "livery": "EIN", "category": "Passenger"}}}), encoding="utf-8")
    # relay 78: relay 74–77's kept facts, moved into the facts database at start (relay 74's airline answers aren't)
    (tmp / "data" / "facts.json").write_text(json.dumps({
        "model:Seeded Model": {"t": now - 3600, "v": {"kind": "model", "title": "Seeded Model", "text": "Kept in facts.json.", "facts": {"built": 7}}},
        "airline:AUA": {"t": now - 3600, "v": {"kind": "airline", "title": "Relay 74's Austrian", "facts": {}}}}), encoding="utf-8")
    music = REPO / "sounds-src" / "emirates-boarding.m4a"
    if music.is_file():
        (tmp / "data" / "media").mkdir()
        shutil.copy(music, tmp / "data" / "media" / music.name)
    env = dict(os.environ, QUIET="1" if a.quiet else "", HOVER="1" if a.hover else "", FAR="1" if a.far else "", RING="1" if a.ring else "",
               SLOW_NAMES="1" if a.slow_names else "", PYTHONIOENCODING="utf-8",
               FAKE_PORT=str(fake_port))
    fake = subprocess.Popen([sys.executable, str(HERE / "fakesrc.py")], env=env)
    procs.append(fake)
    if a.hue:
        procs.append(subprocess.Popen([sys.executable, str(HERE / "fakehue.py"), str(a.port - 2)], env=env))
    cmd = [sys.executable, "serve.py", "--port", str(a.port), "--lat", "48.2085", "--lon", "16.3731", "--place", "Vienna",
           "--home", "VIE", "--local-root", str(REPO), "--source", FAKE + "/ac/{lat}/{lon}/{nm}"]
    if a.fr24:
        cmd += ["--fr24-key", "goodkey"]
    relay = subprocess.Popen(cmd, cwd=tmp, stdin=subprocess.DEVNULL, env=env)  # utf-8: piped output would be cp1252
    procs.append(relay)
    print(f"Test relay on http://localhost:{a.port}/ (data in {tmp}). Ctrl+C, kill or kill -INT to stop.", flush=True)
    while fake.poll() is None and relay.poll() is None:
        time.sleep(.5)


if __name__ == "__main__":
    main()
