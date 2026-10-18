"""Made-up flight data for testing the relay and the boards, on http://127.0.0.1:8095 (env FAKE_PORT for another
port). Started by run_test_relay.py.

It stands in for the position source, adsbdb (routes and aircraft), Flightradar24 (key "goodkey") and Vienna Airport's
flight lists. The planes sit around central Vienna (the boards' default location) and include the special cases:
an A380, a rescue helicopter, a military plane, an emergency squawk, a diverted flight, cargo and a business jet,
a landing, a take-off and a take-off roll at Vienna airport, a callsign with a wrong route in the database, and one far away and high.
QUIET=1 leaves out the special planes; HOVER=1 adds a police helicopter hovering overhead; FAR=1 starts the landing 32 km out.
"""
import json, math, os, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

LAT, LON = 48.2085, 16.3731
KX = 111.32 * math.cos(math.radians(LAT)); KY = 110.57
T0 = time.time()
VIE = ((16.5697 - LON) * KX, (48.1103 - LAT) * KY)


def plane(hex_, cs, t, x0, y0, track, gs_kmh, alt, rate=0, **extra):
    dt = time.time() - T0
    s = gs_kmh / 3600 * dt
    th = math.radians(track)
    x, y = x0 + s * math.sin(th), y0 + s * math.cos(th)
    d = {"hex": hex_, "flight": cs, "t": t, "r": extra.pop("r", ""), "lat": LAT + y / KY, "lon": LON + x / KX,
         "alt_baro": int(alt + rate * dt / 60), "baro_rate": rate, "gs": gs_kmh / 1.852, "track": track}
    d.update(extra)
    return d


def along(base, brg, km):
    return base[0] + km * math.sin(math.radians(brg)), base[1] + km * math.cos(math.radians(brg))


ROUTES = {"AUA411": ("OS411", "Austrian Airlines", "OS", "FRA", "Frankfurt am Main", "VIE", "Vienna"),
          "UAE127": ("EK127", "Emirates", "EK", "DXB", "Dubai", "VIE", "Vienna"),
          "DLH1234": ("LH1234", "Lufthansa", "LH", "FRA", "Frankfurt am Main", "BUD", "Budapest"),
          "RYR22": ("FR22", "Ryanair", "FR", "VIE", "Vienna", "STN", "London"),
          "WZZ4307": ("W64307", "Wizz Air", "W6", "VIE", "Vienna", "TLV", "Tel Aviv"),
          "AUA802": ("OS802", "Austrian Airlines", "OS", "ATH", "Athens", "VIE", "Vienna"),
          "LDM5AB": ("OE215", "Lauda Europe", "OE", "VIE", "Vienna", "PMI", "Palma de Mallorca"),
          "SWR1514": ("LX1514", "Swiss", "LX", "ZRH", "Zurich", "VIE", "Vienna")}
PORT = int(os.environ.get("FAKE_PORT") or 8095)
PHOTO = f"http://127.0.0.1:{PORT}/photo/{{}}.svg"
AIRCRAFT = {"440b11": {"type": "A320 271N", "icao_type": "A20N", "manufacturer": "Airbus SAS", "registration": "OE-LBW",
                       "registered_owner": "Austrian Airlines", "registered_owner_country_name": "Austria", "url_photo": PHOTO.format("440b11")},
            "440a01": {"type": "A320 214", "icao_type": "A320", "manufacturer": "Airbus SAS", "registration": "OE-LBN",
                       "registered_owner": "Austrian Airlines", "registered_owner_country_name": "Austria", "url_photo": PHOTO.format("440a01")},
            "896180": {"type": "A380 861", "icao_type": "A388", "manufacturer": "Airbus SAS", "registration": "A6-EVB",
                       "registered_owner": "Emirates", "registered_owner_country_name": "United Arab Emirates", "url_photo": PHOTO.format("896180")},
            "440c33": {"type": "EC135 T2+", "icao_type": "EC35", "manufacturer": "Airbus Helicopters", "registration": "OE-XEN",
                       "registered_owner": "Christophorus Flugrettungsverein", "registered_owner_country_name": "Austria", "url_photo": ""}}


SVG_PHOTO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 300">
<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b86b8"/><stop offset="1" stop-color="#b9cfe6"/></linearGradient></defs>
<rect width="600" height="300" fill="url(#s)"/>
<path d="M120 160 L470 150 Q500 150 505 160 Q500 170 470 172 L120 168 Q100 164 120 160 Z" fill="#f4f4f2"/>
<path d="M455 152 L500 70 L530 70 L500 155 Z" fill="#c8102e"/><path d="M250 166 L330 230 L360 230 L320 166 Z" fill="#d9d9d6"/>
<path d="M240 158 L300 120 L325 120 L300 158 Z" fill="#d9d9d6"/><rect x="140" y="162" width="340" height="3" fill="#c8102e"/>
</svg>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/jart/prj3/va/data/flights/"):
            import datetime as _dt
            iso = lambda m: (_dt.datetime.utcnow() + _dt.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:00Z")
            def row(fn, s, a, code, text, cs=()):
                return {"fn": fn, "scheduledatetime": iso(s), "actualdatetime": iso(a) if a is not None else None,
                        "status": {"code": code, "description": text}, "codeshares": [{"fn": c} for c in cs]}
            if path.endswith("inc.json"):
                rows = [row("OS 411", 5, 17, "EST", "expected"), row("EK 127", 20, 18, "APP", "approaching", ["QF 8127"]),
                        row("LX 1514", 30, 24, "EST", "expected", ["OS 7151"]), row("OS 802", -10, 25, "APP", "approaching"),
                        row("OS 411", 1445, None, "PLN", None)]
            else:
                rows = [row("W6 4307", -40, -12, "AIR", "airborne"), row("FR 22", -20, -18, "AIR", "airborne"),
                        row("FR 6203", -30, -22, "AIR", "airborne", ["OE 215"])]
            return self.send(200, "application/json", json.dumps({"monitor": {"type": "json", "departure": rows}}).encode())
        if path == "/api/flight-summary/full":
            if self.headers.get("Authorization") != "Bearer goodkey" or self.headers.get("Accept-Version") != "v1":
                return self.send(401, "application/json", b'{"message":"Unauthenticated"}')
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            cs = (q.get("callsigns") or [""])[0]
            FR = {"RYR3EG": ("FR1234", "VIE", "LOWW", "STN", "EGSS", "4CA9F1", "RYR", "RYR", "B38M"),
                  "AUA411": ("OS411", "FRA", "EDDF", "VIE", "LOWW", "440A01", "AUA", "AUA", "A320"),
                  "UAE127": ("EK127", "DXB", "OMDB", "VIE", "LOWW", "896180", "UAE", "UAE", "A388"),
                  "LDM5AB": ("FR6203", "VIE", "LOWW", "PMI", "LEPA", "440B12", "LDM", "RYR", "A320")}
            FR.update({"DLH1234": ("LH1234", "FRA", "EDDF", "BUD", "LHBP", "3C6744", "DLH", "DLH", "A321"),
                       "WZZ4307": ("W64307", "VIE", "LOWW", "TLV", "LLBG", "471F8D", "WZZ", "WZZ", "A21N"),
                       "SWR1514": ("LX1514", "ZRH", "LSZH", "VIE", "LOWW", "4B1814", "SWR", "SWR", "BCS3")})
            CAT = {"WZZ4307": "Cargo", "SWR1514": "Business_jets"}
            r = FR.get(cs)
            data = [] if not r else [{"fr24_id": "3c0ffee", "flight": r[0], "callsign": cs, "operated_as": r[6], "painted_as": r[7], "type": r[8],
                     "orig_iata": r[1], "orig_icao": r[2], "dest_iata": r[3], "dest_icao": r[4],
                     "dest_iata_actual": "VIE" if cs == "DLH1234" else None, "dest_icao_actual": "LOWW" if cs == "DLH1234" else None,
                     "hex": r[5], "flight_ended": "false", "category": CAT.get(cs, "Passenger"), "datetime_takeoff": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 41 * 60))}]
            return self.send(200, "application/json", json.dumps({"data": data}).encode())
        if path.startswith("/v0/callsign/") and path.endswith("/RYR3EG"):
            fr = {"callsign_iata": "FR3EG", "airline": {"name": "Ryanair", "iata": "FR", "icao": "RYR"},
                  "origin": {"iata_code": "NCL", "municipality": "Newcastle", "latitude": 55.037498, "longitude": -1.69167},
                  "destination": {"iata_code": "DUB", "municipality": "Dublin", "latitude": 53.421299, "longitude": -6.27007}}
            return self.send(200, "application/json", json.dumps({"response": {"flightroute": fr}}).encode())
        if path.startswith("/v0/callsign/"):
            r = ROUTES.get(path.rsplit("/", 1)[1].upper())
            if not r:
                return self.send(404, "application/json", b'{"response":"unknown callsign"}')
            iata, name, al, f, fc, t, tc = r
            fr = {"callsign_iata": iata, "airline": {"name": name, "iata": al, "icao": path.rsplit("/", 1)[1][:3].upper()},
                  "origin": {"iata_code": f, "municipality": fc}, "destination": {"iata_code": t, "municipality": tc}}
            return self.send(200, "application/json", json.dumps({"response": {"flightroute": fr}}).encode())
        if path.startswith("/v0/aircraft/"):
            a = AIRCRAFT.get(path.rsplit("/", 1)[1].lower())
            if not a:
                return self.send(404, "application/json", b'{"response":"unknown aircraft"}')
            return self.send(200, "application/json", json.dumps({"response": {"aircraft": a}}).encode())
        if path.startswith("/photo/"):     # a drawn stand-in for an aircraft photo
            return self.send(200, "image/svg+xml", SVG_PHOTO.encode())
        if not path.startswith("/ac/"):
            self.send_response(404); self.end_headers(); return
        far = os.environ.get("FAR")      # the landing still far out: it reaches its final approach about 4 minutes later
        arr = along(VIE, 115, 32 if far else 9)
        dep = along(VIE, 295, 4)
        ac = [
            plane("440a01", "AUA411", "A320", 0.6, -5.0, 0, 700, 2600, -300, r="OE-LBN"),       # inbound, then overhead
            plane("896180", "UAE127", "A388", 2.2, -11.0, 5, 650, 3800, -500, r="A6-EVB"),      # superjumbo passing close by
            plane("440c33", "OEXEN", "EC35", -7.0, 5.0, 90, 180, 1200, 0, r="OE-XEN"),         # rescue helicopter
            plane("44d0ab", "BAF586", "C130", 6.0, 4.0, 200, 450, 6000, 0, r="CH-10", dbFlags=1),  # military
            plane("4ca7b4", "RYR22", "B738", -5.0, 6.0, 300, 800, 4000, 1500, r="EI-DCL", squawk="7700"),  # emergency
            plane("3c6744", "DLH1234", "A321", 8.0, -12.0, 0, 800, 9000, 0, r="D-AISN"),        # flying by
            plane("471f8d", "WZZ4307", "A21N", -9.0, -3.0, 45, 780, 7000, 1800, r="HA-LVF"),    # outbound-ish
            plane("440b11", "AUA802", "A20N", arr[0], arr[1], 295, 300, 9000 if far else 2600, -1400 if far else -700, r="OE-LBW"),  # landing on 29
            plane("440b12", "LDM5AB", "A320", dep[0], dep[1], 295, 380, 2500, 2200, r="OE-LMA"),  # taking off from 29
            plane("440c55", "AUA411X", "E195", along(VIE, 115, 1.2)[0], along(VIE, 115, 1.2)[1], 295, 220, 0, 0,
                  r="OE-LWA", alt_baro="ground"),                                              # take-off roll on 29
            plane("4b1814", "SWR1514", "BCS3", 18.0, 10.0, 250, 750, 12000, -1200, r="HB-JCA"),
            plane("4ca9f1", "RYR3EG", "B38M", 3.0, -6.0, 300, 800, 5000, 0, r="9H-QEG"),       # stale route in the database
            plane("4ca123", "EIN2AB", "A320", 30.0, 30.0, 220, 800, 36000, 0),                   # far and high
        ]
        if os.environ.get("QUIET"):   # no special planes, so the pages rotate undisturbed
            ac = [a for a in ac if a.get("flight", "").strip() not in ("UAE127", "OEXEN", "BAF586", "RYR22")]
        if os.environ.get("HOVER"):
            ac.append(plane("44041d", "OEBXB", "EC35", 0.3, 0.4, 90, 25, 1500, 0, r="OE-BXB", category="A7"))  # police helicopter over an incident
        body = json.dumps({"ac": ac, "now": time.time()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
