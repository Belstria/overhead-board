#!/usr/bin/env python3
"""Overhead board home relay.

Serves the board and fetches live aircraft positions from your home connection.
The public ADS-B services don't let browsers on other websites read their data and
turn away cloud servers, so the requests need to come from a machine in your home.

Run:   python serve.py --lat 48.2085 --lon 16.3731 --place Vienna --sound
Open:  http://localhost:8080  (or http://<this-computer>:8080 from any screen at home)

Standard library only: works with Python 3.8+ on Windows, macOS, Linux or in a container.
"""
import argparse
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BOARD_URL = "https://belstria.github.io/overhead-board/"
SOURCES = {
    "adsblol": "https://api.adsb.lol/v2/point/",
    "airplaneslive": "https://api.airplanes.live/v2/point/",
}
ROUTESET = "https://api.adsb.lol/api/0/routeset"
USER_AGENT = "overhead-board home relay (github.com/Belstria/overhead-board)"
POINT = re.compile(r"^/(adsblol|airplaneslive)/(-?\d{1,2}(?:\.\d{1,6})?)/(-?\d{1,3}(?:\.\d{1,6})?)/(\d{1,3})$")
BOARD_COPY = Path(__file__).with_name("board-cache.html")

ARGS = None
_cache = {}
_lock = threading.Lock()


def fetch(url, data=None, content_type=None, timeout=10):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", "application/json"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "text/plain"), e.read()
    except Exception as e:  # network down, DNS, timeout
        return 502, "text/plain", f"Upstream unreachable: {e}".encode()


def cached(key, ttl, load):
    """Answer repeat requests from memory for a few seconds, so extra screens add no upstream load."""
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


def board_html():
    if ARGS.local:
        html = Path(ARGS.local).read_text(encoding="utf-8")
    else:
        status, _, body = cached("board", 300, lambda: fetch(BOARD_URL, timeout=15))
        if status == 200:
            html = body.decode("utf-8")
            try:
                BOARD_COPY.write_text(html, encoding="utf-8")
            except OSError:
                pass
        elif BOARD_COPY.exists():  # GitHub unreachable: use the last copy we saw
            html = BOARD_COPY.read_text(encoding="utf-8")
        else:
            return None
    defaults = {k: v for k, v in {
        "lat": ARGS.lat, "lon": ARGS.lon, "place": ARGS.place,
        "home": ARGS.home, "radiusKm": ARGS.radius,
    }.items() if v is not None}
    if ARGS.sound:
        defaults["sound"] = True
    config = json.dumps(defaults).replace("<", "\\u003c")
    inject = f"<script>window.OVERHEAD_RELAY=location.origin;window.OVERHEAD_DEFAULTS={config};</script>"
    return html.replace("<head>", "<head>\n" + inject, 1)


class Handler(BaseHTTPRequestHandler):
    server_version = "OverheadRelay/1.0"

    def log_message(self, fmt, *args):
        if ARGS.verbose:
            super().log_message(fmt, *args)

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = board_html()
            if html is None:
                return self.reply(502, "text/plain; charset=utf-8", b"Couldn't download the board from GitHub yet. Check the internet connection and reload.")
            return self.reply(200, "text/html; charset=utf-8", html.encode("utf-8"))
        if path == "/health":
            return self.reply(200, "text/plain", b"ok")
        m = POINT.match(path)
        if m:
            source, lat, lon, nm = m.groups()
            if abs(float(lat)) > 90 or abs(float(lon)) > 180 or not 1 <= int(nm) <= 50:
                return self.reply(400, "text/plain", b"Out of range")
            url = f"{SOURCES[source]}{lat}/{lon}/{nm}"
            return self.reply(*cached(url, 5, lambda: fetch(url)))
        self.reply(404, "text/plain", b"Not found")

    do_HEAD = do_GET

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/routeset":
            return self.reply(404, "text/plain", b"Not found")
        length = int(self.headers.get("Content-Length") or 0)
        if length > 2048:
            return self.reply(413, "text/plain", b"Too large")
        body = self.rfile.read(length)
        self.reply(*fetch(ROUTESET, data=body, content_type="application/json"))


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
    p.add_argument("--port", type=int, default=8080, help="port to listen on (default 8080)")
    p.add_argument("--bind", default="0.0.0.0", help="address to listen on (default: all, so other screens at home can reach it)")
    p.add_argument("--lat", type=float, help="latitude of the spot to watch")
    p.add_argument("--lon", type=float, help="longitude of the spot to watch")
    p.add_argument("--place", help="name printed under the title")
    p.add_argument("--home", help="home airport IATA code (default VIE)")
    p.add_argument("--radius", type=float, help="overhead radius in km (default 4)")
    p.add_argument("--sound", action="store_true", help="flap sound on by default")
    p.add_argument("--local", help="serve this index.html instead of the published board")
    p.add_argument("--verbose", action="store_true", help="log every request")
    ARGS = p.parse_args()

    server = ThreadingHTTPServer((ARGS.bind, ARGS.port), Handler)
    print("Overhead relay running. Open the board at:")
    print(f"  http://localhost:{ARGS.port}")
    print(f"  http://{socket.gethostname()}:{ARGS.port}")
    ip = lan_address()
    if ip:
        print(f"  http://{ip}:{ARGS.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
