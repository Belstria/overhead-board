"""Run the boards against made-up flights: a fake flight data source on port 8095 and a test relay on port 8096 that
serves this repository's boards (/, /test/, /app/) with it. Your real relay, its settings and its data
are not touched: the test relay runs from a temporary folder.

    py tools/test/run_test_relay.py            every kind of plane, including special ones and an emergency
    py tools/test/run_test_relay.py --quiet    no special planes, so the pages rotate undisturbed
    py tools/test/run_test_relay.py --hover    adds a police helicopter hovering overhead
    py tools/test/run_test_relay.py --far      the landing starts 32 km out (its photo, then the runway radar)
    py tools/test/run_test_relay.py --fr24     the relay acts as if it had a Flightradar24 key (served by the fake)

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
FAKE = "http://127.0.0.1:8095"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--quiet", action="store_true", help="no special planes")
    p.add_argument("--hover", action="store_true", help="add a helicopter hovering overhead")
    p.add_argument("--far", action="store_true", help="the landing starts 32 km out")
    p.add_argument("--fr24", action="store_true", help="pretend the relay has a Flightradar24 key")
    a = p.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="overhead-test-"))
    src = (REPO / "relay" / "serve.py").read_text(encoding="utf-8")
    for real, fake in [("https://api.adsbdb.com", FAKE), ("https://fr24api.flightradar24.com/api", FAKE + "/api"),
                       ("https://viennaairport.com/jart", FAKE + "/jart")]:
        if real not in src:
            raise SystemExit(f"relay/serve.py no longer mentions {real}; update run_test_relay.py")
        src = src.replace(real, fake)
    src = re.sub(r"^FR24_GAP_S = [\d.]+", "FR24_GAP_S = 0.5", src, flags=re.M)
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
    music = REPO / "sounds-src" / "emirates-boarding.m4a"
    if music.is_file():
        (tmp / "data" / "media").mkdir()
        shutil.copy(music, tmp / "data" / "media" / music.name)
    env = dict(os.environ, QUIET="1" if a.quiet else "", HOVER="1" if a.hover else "", FAR="1" if a.far else "", PYTHONIOENCODING="utf-8")
    fake = subprocess.Popen([sys.executable, str(HERE / "fakesrc.py")], env=env)
    cmd = [sys.executable, "serve.py", "--port", "8096", "--lat", "48.2085", "--lon", "16.3731", "--place", "Vienna",
           "--home", "VIE", "--local-root", str(REPO), "--source", FAKE + "/ac/{lat}/{lon}/{nm}"]
    if a.fr24:
        cmd += ["--fr24-key", "goodkey"]
    relay = subprocess.Popen(cmd, cwd=tmp, stdin=subprocess.DEVNULL, env=env)  # utf-8: piped output would be cp1252
    print(f"Test relay on http://localhost:8096/ (data in {tmp}). Ctrl+C to stop.", flush=True)
    try:
        while fake.poll() is None and relay.poll() is None:
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (relay, fake):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
