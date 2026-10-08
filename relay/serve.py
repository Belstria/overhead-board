#!/usr/bin/env python3
"""Overhead board home relay.

Serves the board and fetches live aircraft positions from your home connection.
The public ADS-B services don't let browsers on other websites read their data and
turn away cloud servers, so the requests need to come from a machine in your home.

Run:   python serve.py --lat 48.2085 --lon 16.3731 --place Vienna --save
Open:  http://localhost:8080  (or http://<this-computer>:8080 from any screen at home)

Positions come from adsb.lol, adsb.fi and airplanes.live, tried in that order. A source that
answers "too many requests" or "forbidden" is rested for a while and the next one is used.
If every source fails, the board keeps getting the last good answer for up to two minutes.

Standard library only: works with Python 3.8+ on Windows, macOS, Linux or in a container.
"""
import argparse
import collections
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RELAY_VERSION = 3
BOARD_URL = "https://belstria.github.io/overhead-board/"
SOURCES = [
    {"key": "adsblol", "name": "adsb.lol", "url": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"},
    {"key": "adsbfi", "name": "adsb.fi", "url": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}"},
    {"key": "airplaneslive", "name": "airplanes.live", "url": "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}"},
]
ROUTESET = "https://api.adsb.lol/api/0/routeset"
USER_AGENT = "overhead-board home relay (github.com/Belstria/overhead-board)"
FRESH_S = 5      # answer repeat requests from memory for this long
STALE_S = 120    # if every source fails, keep serving the last good answer this long
NUM = r"(-?\d{1,3}(?:\.\d{1,6})?)"
AIRCRAFT = re.compile(rf"^/aircraft/{NUM}/{NUM}/(\d{{1,3}})$")
LEGACY = re.compile(rf"^/(adsblol|airplaneslive)/{NUM}/{NUM}/(\d{{1,3}})$")
PAGE = re.compile(r"^/(?:([a-z0-9-]{1,40})/)?(?:index\.html)?$")   # "/" is the board, "/test/" the test version
CONFIG_FILE = Path(__file__).with_name("overhead.json")   # your saved settings; stays on this computer
SAVED_KEYS = ("lat", "lon", "place", "home", "radius", "units", "sound", "port")

ARGS = None
STARTED = time.time()
STATE = {s["key"]: {"ok": 0, "fail": 0, "strikes": 0, "cooldown_until": 0.0, "last_status": None,
                    "last_error": "", "last_ok": 0.0} for s in SOURCES}
EVENTS = collections.deque(maxlen=200)
_event_id = 0
_positions = {}            # key -> (time, body, source name)
_cache = {}
_lock = threading.Lock()
_fetch_lock = threading.Lock()


def event(level, msg, echo=True):
    """Record something worth knowing; the board's diagnostics panel shows these too."""
    global _event_id
    with _lock:
        _event_id += 1
        EVENTS.append({"id": _event_id, "t": time.time(), "level": level, "msg": msg})
    if echo or ARGS.verbose:
        print(f"{time.strftime('%H:%M:%S')}  {level.upper():5}  {msg}", flush=True)


def fetch(url, data=None, content_type=None, timeout=10):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", "application/json"), r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "text/plain"), e.read(), e.headers
    except Exception as e:  # network down, DNS, timeout
        return 502, "text/plain", f"unreachable: {getattr(e, 'reason', e)}".encode(), {}


def cached(key, ttl, load):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    result = load()
    if 200 <= result[0] < 300:
        with _lock:
            _cache[key] = (now, result)
    return result


def rest_for(status, strikes, retry_after):
    if retry_after:
        try:
            return max(5, min(900, int(retry_after)))
        except ValueError:
            pass
    if status == 429:
        return min(600, 30 * 2 ** (strikes - 1))
    if status in (401, 403):
        return 1800
    return min(300, 10 * 2 ** (strikes - 1))


def aircraft(lat, lon, nm):
    """Positions around a point, from the first source that answers properly."""
    key = f"{lat}/{lon}/{nm}"
    with _fetch_lock:  # one upstream call at a time; other screens wait and get the fresh copy
        now = time.time()
        hit = _positions.get(key)
        if hit and now - hit[0] < FRESH_S:
            return 200, hit[1], hit[2], "fresh"
        tried = []
        for src in SOURCES:
            st = STATE[src["key"]]
            if now < st["cooldown_until"]:
                tried.append(f"{src['name']} resting {int(st['cooldown_until'] - now)} s")
                continue
            t0 = time.time()
            status, _, body, headers = fetch(src["url"].format(lat=lat, lon=lon, nm=nm))
            ms = int((time.time() - t0) * 1000)
            count, problem = None, ""
            if 200 <= status < 300:
                try:
                    data = json.loads(body)
                    planes = data.get("ac", data.get("aircraft"))
                    if isinstance(planes, list):
                        count = len(planes)
                    else:
                        problem = "answer had no aircraft list"
                except ValueError:
                    problem = "answer wasn't JSON"
            else:
                problem = f"HTTP {status} {body[:80].decode('utf-8', 'replace').strip()}"
            if count is not None:
                was_failing = st["strikes"] > 0
                st.update(ok=st["ok"] + 1, strikes=0, last_status=status, last_ok=time.time(), last_error="")
                _positions[key] = (time.time(), body, src["name"])
                if was_failing:
                    event("info", f"{src['name']} answering again")
                event("debug", f"{src['name']}: {count} aircraft in {ms} ms", echo=False)
                return 200, body, src["name"], "live"
            st["fail"] += 1
            st["strikes"] += 1
            st["last_status"] = status
            st["last_error"] = problem
            rest = rest_for(status, st["strikes"], headers.get("Retry-After") if headers else None)
            st["cooldown_until"] = time.time() + rest
            event("warn", f"{src['name']} failed ({problem}); resting it for {rest} s")
            tried.append(f"{src['name']} {problem}")
        if hit and time.time() - hit[0] < STALE_S:
            age = int(time.time() - hit[0])
            event("warn", f"All sources failed; serving last good data ({age} s old)")
            return 200, hit[1], hit[2], f"stale {age}"
        event("error", "All sources failed and no recent data to fall back on")
        body = json.dumps({"error": "no position source available", "tried": tried}).encode()
        return 503, body, "", "none"


def status_json():
    now = time.time()
    sources = []
    for src in SOURCES:
        st = STATE[src["key"]]
        resting = max(0, int(st["cooldown_until"] - now))
        sources.append({
            "name": src["name"],
            "state": "resting" if resting else ("ok" if st["ok"] and not st["strikes"] else ("failing" if st["strikes"] else "untried")),
            "resting_s": resting, "ok": st["ok"], "fail": st["fail"], "last_status": st["last_status"],
            "last_error": st["last_error"], "last_ok_age_s": int(now - st["last_ok"]) if st["last_ok"] else None,
        })
    with _lock:
        events = list(EVENTS)[-80:]
    return {"version": RELAY_VERSION, "uptime_s": int(now - STARTED), "sources": sources, "events": events}


def board_html(sub=""):
    copy = Path(__file__).with_name(f"board-cache{'-' + sub if sub else ''}.html")
    if ARGS.local and not sub:
        html = Path(ARGS.local).read_text(encoding="utf-8")
    else:
        url = BOARD_URL + (sub + "/" if sub else "")
        status, _, body, _ = cached("page:" + sub, 300, lambda: fetch(url, timeout=15))
        if status == 200:
            html = body.decode("utf-8")
            try:
                copy.write_text(html, encoding="utf-8")
            except OSError:
                pass
        elif copy.exists():  # GitHub unreachable: use the last copy we saw
            html = copy.read_text(encoding="utf-8")
        else:
            return None
    defaults = {k: v for k, v in {
        "lat": ARGS.lat, "lon": ARGS.lon, "place": ARGS.place,
        "home": ARGS.home, "radiusKm": ARGS.radius, "units": ARGS.units,
    }.items() if v is not None}
    if ARGS.sound is not None:
        defaults["sound"] = bool(ARGS.sound)
    config = json.dumps(defaults).replace("<", "\\u003c")
    inject = (f"<script>window.OVERHEAD_RELAY=location.origin;window.OVERHEAD_RELAY_VERSION={RELAY_VERSION};"
              f"window.OVERHEAD_DEFAULTS={config};</script>")
    return html.replace("<head>", "<head>\n" + inject, 1)


class Handler(BaseHTTPRequestHandler):
    server_version = f"OverheadRelay/{RELAY_VERSION}"

    def log_message(self, fmt, *args):
        if ARGS.verbose:
            super().log_message(fmt, *args)

    def reply(self, status, content_type, body, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if re.fullmatch(r"/[a-z0-9-]{1,40}", path) and path not in ("/health", "/status"):
            self.send_response(301)  # /test → /test/
            self.send_header("Location", path + "/")
            self.end_headers()
            return
        page = PAGE.match(path)
        if page:
            html = board_html(page.group(1) or "")
            if html is None:
                return self.reply(502, "text/plain; charset=utf-8", b"Couldn't download the board from GitHub yet. Check the internet connection and reload.")
            return self.reply(200, "text/html; charset=utf-8", html.encode("utf-8"))
        if path == "/health":
            return self.reply(200, "text/plain", b"ok")
        if path == "/status":
            return self.reply(200, "application/json", json.dumps(status_json()).encode())
        m = AIRCRAFT.match(path) or LEGACY.match(path)
        if m:
            lat, lon, nm = m.groups()[-3:]
            if abs(float(lat)) > 90 or abs(float(lon)) > 180 or not 1 <= int(nm) <= 50:
                return self.reply(400, "text/plain", b"Out of range")
            status, body, source, freshness = aircraft(lat, lon, nm)
            return self.reply(status, "application/json", body, {"X-Relay-Source": source, "X-Relay-Data": freshness})
        self.reply(404, "text/plain", b"Not found")

    do_HEAD = do_GET

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/routeset":
            return self.reply(404, "text/plain", b"Not found")
        length = int(self.headers.get("Content-Length") or 0)
        if length > 2048:
            return self.reply(413, "text/plain", b"Too large")
        status, ctype, body, _ = fetch(ROUTESET, data=self.rfile.read(length), content_type="application/json")
        self.reply(status, ctype, body)


def lan_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet is sent; this just picks the outgoing interface
            return s.getsockname()[0]
    except OSError:
        return None


def main():
    global ARGS
    p = argparse.ArgumentParser(description="Serve the Overhead board with live flight data from this computer.")
    p.add_argument("--port", type=int, help="port to listen on (default 8080)")
    p.add_argument("--bind", default="0.0.0.0", help="address to listen on (default: all, so other screens at home can reach it)")
    p.add_argument("--lat", type=float, help="latitude of the spot to watch")
    p.add_argument("--lon", type=float, help="longitude of the spot to watch")
    p.add_argument("--place", help="name printed under the title")
    p.add_argument("--home", help="home airport IATA code (default VIE)")
    p.add_argument("--radius", type=float, help="overhead radius in km (default 15)")
    p.add_argument("--units", choices=["metric", "aviation"], help="metric (metres, km/h; the default) or aviation (feet, knots)")
    p.add_argument("--sound", action="store_true", default=None, help="flap sound on (the default)")
    p.add_argument("--mute", action="store_true", help="flap sound off by default")
    p.add_argument("--save", action="store_true", help=f"remember these settings in {CONFIG_FILE.name}, so next time `serve.py` alone is enough")
    p.add_argument("--local", help="serve this index.html instead of the published board")
    p.add_argument("--verbose", action="store_true", help="log every request and every successful update")
    ARGS = p.parse_args()

    saved = {}
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"Couldn't read {CONFIG_FILE.name} ({e}); ignoring it.")
    for key in SAVED_KEYS:          # anything given on the command line wins over the saved file
        if getattr(ARGS, key) is None and key in saved:
            setattr(ARGS, key, saved[key])
    if ARGS.mute:
        ARGS.sound = False
    if ARGS.port is None:
        ARGS.port = 8080
    if ARGS.save:
        keep = {k: getattr(ARGS, k) for k in SAVED_KEYS if getattr(ARGS, k) is not None}
        CONFIG_FILE.write_text(json.dumps(keep, indent=2), encoding="utf-8")
        print(f"Saved your settings to {CONFIG_FILE}. Next time, `serve.py` on its own is enough.")
    if ARGS.lat is None or ARGS.lon is None:
        print("No location set, so the board will watch central Vienna. Add --lat and --lon (and --save to keep them).")

    server = ThreadingHTTPServer((ARGS.bind, ARGS.port), Handler)
    print(f"Overhead relay {RELAY_VERSION} running. Open the board at:")
    print(f"  http://localhost:{ARGS.port}")
    print(f"  http://{socket.gethostname()}:{ARGS.port}")
    ip = lan_address()
    if ip:
        print(f"  http://{ip}:{ARGS.port}")
    print("Problems with the flight data sources are printed below. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
