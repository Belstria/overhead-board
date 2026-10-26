"""Run the boards against made-up flights: a fake flight data source on port 8095 and a test relay on port 8096 that
serves this repository's boards (/, /test/, /app/) with it. Your real relay, its settings and its data
are not touched: the test relay runs from a temporary folder.

    py tools/test/run_test_relay.py            every kind of plane, including special ones and an emergency
    py tools/test/run_test_relay.py --quiet    no special planes, so the pages rotate undisturbed
    py tools/test/run_test_relay.py --hover    adds a police helicopter hovering overhead
    py tools/test/run_test_relay.py --far      the landing starts 32 km out (its photo, then the runway radar)
    py tools/test/run_test_relay.py --fr24     the relay acts as if it had a Flightradar24 key (served by the fake); David's
                                               screens more than 30 km from the test point (Live location) also get the
                                               gap filler's take-off that only Flightradar24 hears (relay 66)
    py tools/test/run_test_relay.py --hue      a fake Hue Bridge (fakehue.py, two ports below the relay) for the admin
                                               page's Hue lights: Find the bridge finds it, Pair works on the second try
    py tools/test/run_test_relay.py --live-photos   the planes' photos from the real Planespotters.net (needs the internet;
                                               for screenshots) instead of the fake's (relay 73)
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
    p.add_argument("--fr24", action="store_true", help="pretend the relay has a Flightradar24 key")
    p.add_argument("--hue", action="store_true", help="a fake Hue Bridge for the admin page's Hue lights")
    p.add_argument("--live-photos", action="store_true", help="the planes' photos from the real Planespotters.net")
    p.add_argument("--slow-names", action="store_true", help="place names take 5 s, the first lookup of each point fails")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8096), help="relay port (default 8096; the fake source one below)")
    a = p.parse_args()
    fake_port = a.port - 1
    FAKE = f"http://127.0.0.1:{fake_port}"
    tmp = Path(tempfile.mkdtemp(prefix="overhead-test-"))
    src = (REPO / "relay" / "serve.py").read_text(encoding="utf-8")
    fakes = [("https://api.adsbdb.com", FAKE), ("https://fr24api.flightradar24.com/api", FAKE + "/api"),
             ("https://viennaairport.com/jart", FAKE + "/jart"),
             ("https://nominatim.openstreetmap.org", FAKE + "/nominatim"),
             ("https://raw.githubusercontent.com/vradarserver/standing-data/main/airlines/schema-01/airlines.csv", FAKE + "/airlines.csv")]
    if not a.live_photos:
        fakes.append(("https://api.planespotters.net/pub/photos", FAKE + "/ps/pub/photos"))
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
    day = time.strftime("%Y-%m-%d", time.localtime(now - 3 * 3600 - 86400))
    old = [{"id": "old-ein", "hex": "4ca2b8", "callsign": "EIN1XY", "ts": int((now - 86400) * 1000), "time": "12:00",
            "typeCode": "A320", "minDist": 6.2, "altAtMin": 9000, "looked": True},
           {"id": "old-aua", "hex": "440a99", "callsign": "AUA9", "ts": int((now - 86400) * 1000) - 60000, "time": "11:59",
            "typeCode": "A320", "minDist": 7.1, "altAtMin": 9500, "looked": True, "airlineName": "Austrian"},
           # relay 70: a plane without a callsign, saved as the sources' "@@@@@@@@", cleaned once at start
           {"id": "old-at", "hex": "ae0413", "callsign": "@@@@@@@@", "reg": "TEST-AT", "ts": int((now - 86400) * 1000) - 120000,
            "time": "11:58", "typeCode": "C130", "minDist": 5.0, "altAtMin": 5000, "looked": True}]
    (tmp / "data" / "profiles" / "test0001").mkdir(parents=True)
    (tmp / "data" / "profiles" / "test0001" / f"sightings-{day}.json").write_text(json.dumps(old), encoding="utf-8")
    # ... and Flightradar24's answer about it, still in the cache: written into the sighting at start
    (tmp / "data" / "fr24.json").write_text(json.dumps({"usage": {}, "flights": {"4ca2b8|EIN1XY": {
        "t": now - 86400 + 300, "flight": "EI661", "callsign": "EIN1XY", "from": {"code": "DUB", "city": "Dublin"},
        "to": {"code": "VIE", "city": "Vienna"}, "operator": "EIN", "livery": "EIN", "category": "Passenger"}}}), encoding="utf-8")
    music = REPO / "sounds-src" / "emirates-boarding.m4a"
    if music.is_file():
        (tmp / "data" / "media").mkdir()
        shutil.copy(music, tmp / "data" / "media" / music.name)
    env = dict(os.environ, QUIET="1" if a.quiet else "", HOVER="1" if a.hover else "", FAR="1" if a.far else "",
               SLOW_NAMES="1" if a.slow_names else "", PYTHONIOENCODING="utf-8",
               FAKE_PORT=str(fake_port))
    fake = subprocess.Popen([sys.executable, str(HERE / "fakesrc.py")], env=env)
    hue = subprocess.Popen([sys.executable, str(HERE / "fakehue.py"), str(a.port - 2)], env=env) if a.hue else None
    cmd = [sys.executable, "serve.py", "--port", str(a.port), "--lat", "48.2085", "--lon", "16.3731", "--place", "Vienna",
           "--home", "VIE", "--local-root", str(REPO), "--source", FAKE + "/ac/{lat}/{lon}/{nm}"]
    if a.fr24:
        cmd += ["--fr24-key", "goodkey"]
    relay = subprocess.Popen(cmd, cwd=tmp, stdin=subprocess.DEVNULL, env=env)  # utf-8: piped output would be cp1252
    print(f"Test relay on http://localhost:{a.port}/ (data in {tmp}). Ctrl+C to stop.", flush=True)
    try:
        while fake.poll() is None and relay.poll() is None:
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (relay, fake, hue):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
