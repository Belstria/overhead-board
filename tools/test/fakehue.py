"""A fake Philips Hue Bridge for the test relay (run_test_relay.py --hue starts it, two ports below the relay): the
local API's few calls the relay uses (/api/config, pairing, lights, rooms, light states) and Philips' discovery list
at /discovery. The link button counts as pressed from the second pairing attempt on. Every change to a lamp is
printed, and /log lists them, so a test can check the pulse and that each lamp went back to how it was.

    py tools/test/fakehue.py 8494
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8494
USER = "fakehueuser0123456789"
LIGHTS = {
    "1": {"name": "Desk lamp", "state": {"on": False, "bri": 120, "xy": [.4, .4], "ct": 300, "colormode": "xy", "reachable": True}},
    "2": {"name": "Sofa", "state": {"on": True, "bri": 200, "ct": 366, "xy": [.45, .41], "colormode": "ct", "reachable": True}},
    "3": {"name": "Hall", "state": {"on": True, "bri": 60, "hue": 8000, "sat": 140, "xy": [.5, .4], "colormode": "hs", "reachable": True}},
}
GROUPS = {"1": {"name": "Living room", "type": "Room", "lights": ["1", "2"]}, "7": {"name": "All", "type": "LightGroup", "lights": ["1", "2", "3"]}}
LOG = []
tries = {"n": 0}
lock = threading.Lock()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, status=200):
        b = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/discovery":
            return self.send([{"id": "001788fffe00beef", "internalipaddress": "127.0.0.1", "port": PORT}])
        if p == "/log":
            return self.send(LOG)
        if p == "/api/config":
            return self.send({"name": "Fake Hue Bridge", "bridgeid": "001788FFFE00BEEF", "apiversion": "1.65.0"})
        if p.startswith("/api/" + USER):
            rest = p[len("/api/" + USER):]
            with lock:
                if rest == "/lights":
                    return self.send(LIGHTS)
                if rest == "/groups":
                    return self.send(GROUPS)
                if rest.startswith("/lights/") and rest[8:] in LIGHTS:
                    return self.send(LIGHTS[rest[8:]])
        if p.startswith("/api/"):
            return self.send([{"error": {"type": 1, "address": p, "description": "unauthorized user"}}])
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") == "/api":
            b = self.body()
            tries["n"] += 1
            if tries["n"] < 2:
                return self.send([{"error": {"type": 101, "address": "", "description": "link button not pressed"}}])
            print(f"fakehue: paired {b.get('devicetype')}", flush=True)
            return self.send([{"success": {"username": USER}}])
        self.send({"error": "not found"}, 404)

    def do_PUT(self):
        p = self.path.rstrip("/")
        pre = f"/api/{USER}/lights/"
        if p.startswith(pre) and p.endswith("/state") and p[len(pre):-6] in LIGHTS:
            i, b = p[len(pre):-6], self.body()
            with lock:
                st = LIGHTS[i]["state"]
                if not st["on"] and b.get("on") is not True and any(k in b for k in ("bri", "xy", "ct", "hue", "sat")):
                    return self.send([{"error": {"type": 201, "description": "parameter, xy, is not modifiable. Device is set to off."}}])
                for k, v in b.items():
                    if k != "transitiontime":
                        st[k] = v
                if "xy" in b:
                    st["colormode"] = "xy"
                elif "ct" in b:
                    st["colormode"] = "ct"
                elif "hue" in b:
                    st["colormode"] = "hs"
                LOG.append({"t": time.time(), "light": i, "set": b})
            print(f"fakehue: lamp {i} <- {json.dumps(b)}", flush=True)
            return self.send([{"success": {f"/lights/{i}/state/{k}": v}} for k, v in b.items()])
        self.send({"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"Fake Hue Bridge on http://127.0.0.1:{PORT}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
