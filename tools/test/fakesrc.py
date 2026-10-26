"""Made-up flight data for testing the relay and the boards, on http://127.0.0.1:8095 (env FAKE_PORT for another
port). Started by run_test_relay.py.

It stands in for the position source, adsbdb (routes and aircraft), Flightradar24 (key "goodkey"), Vienna Airport's
flight lists and the airline list (relay 68: a few real rows and made-up ones; EIN6AB, an Aer Lingus flight with no
route listed, is an airline the board's own table lacks), and Planespotters.net's photo API (relay 73: OE-LBN by its
registration, the A380 only by its hex, and for the military C-130's hex another aircraft's photo, which the relay must
pass over). The planes sit around central Vienna (the boards' default location) and include the special cases:
an A380, a rescue helicopter, a military plane, an emergency squawk, a diverted flight, cargo and a business jet,
a landing, a take-off and a take-off roll at Vienna airport, a callsign with a wrong route in the database, and one far away and high.
QUIET=1 leaves out the special planes; HOVER=1 adds a police helicopter hovering overhead; FAR=1 starts the landing 32 km out.
SLOW_NAMES=1: OpenStreetMap's place names take 5 s, and the first lookup of each point fails (live location, 1.93.0.1).
Away from Vienna (more than 30 km) the position source has only a turboprop at 8,000 ft near the place, while
Flightradar24's live positions also have a take-off the free networks can't hear, passing over the place every 6 minutes
(the relay's gap filler, relay 66).
"""
import collections, json, math, os, re, time, urllib.parse
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


# Planes standing at Vienna airport's gates (hex, callsign, type, lat, lon, heading).
APRON = [("440a21", "AUA123", "A320", 48.1209, 16.5615, 200), ("440a22", "AUA455", "E195", 48.1203, 16.5632, 200),
         ("4ca9a1", "RYR4417", "B738", 48.1186, 16.5668, 20), ("471f90", "WZZ6481", "A21N", 48.1180, 16.5683, 20),
         ("3c6589", "DLH2CA", "A20N", 48.1218, 16.5590, 200), ("440a30", "AUA67", "B763", 48.1225, 16.5655, 110)]


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


SVG_PHOTO = """<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" viewBox="0 0 600 300">
<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b86b8"/><stop offset="1" stop-color="#b9cfe6"/></linearGradient></defs>
<rect width="600" height="300" fill="url(#s)"/>
<path d="M120 160 L470 150 Q500 150 505 160 Q500 170 470 172 L120 168 Q100 164 120 160 Z" fill="#f4f4f2"/>
<path d="M455 152 L500 70 L530 70 L500 155 Z" fill="#c8102e"/><path d="M250 166 L330 230 L360 230 L320 166 Z" fill="#d9d9d6"/>
<path d="M240 158 L300 120 L325 120 L300 158 Z" fill="#d9d9d6"/><rect x="140" y="162" width="340" height="3" fill="#c8102e"/>
</svg>"""

# Planespotters.net's photo API (relay 73): which lookups find a photo (id, the photo page's name), and how often each was
# asked (/ps/asked, for flows.py's cache check). Their photos are 420 px wide at most; the stand-in is an evening sky.
PS_PHOTOS = {"reg/OE-LBN": ("1000001", "oe-lbn-austrian-airlines-airbus-a320-214"),
             "hex/896180": ("1000002", "a6-evb-emirates-airbus-a380-861"),
             "hex/44D0AB": ("1000003", "oo-tek-tea-belgium-boeing-737-2q9-adv")}
PS_ASKED = collections.Counter()
NAMES_FAILED = set()        # SLOW_NAMES=1 (run_test_relay.py --slow-names): the points whose first name lookup failed
PS_PHOTO = """<svg xmlns="http://www.w3.org/2000/svg" width="420" height="280" viewBox="0 0 420 280">
<defs><linearGradient id="e" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2d3c63"/><stop offset=".7" stop-color="#d9825b"/><stop offset="1" stop-color="#f2c38b"/></linearGradient></defs>
<rect width="420" height="280" fill="url(#e)"/><rect y="236" width="420" height="44" fill="#3a3f45"/>
<path d="M70 190 L340 182 Q362 182 366 190 Q362 198 340 199 L70 197 Q55 194 70 190 Z" fill="#eceae4"/>
<path d="M330 184 L360 120 L382 120 L362 187 Z" fill="#c8102e"/><path d="M170 196 L230 244 L254 244 L222 196 Z" fill="#cfcfcb"/>
</svg>"""


def away(lat, lon):
    """Planes around a place away from Vienna: (heard, missed). The take-off climbs out from 13 km south-east, passes
    about a kilometre from the place after 2.5 minutes and starts again every 6 minutes; the turboprop circles the place
    10 km out at 8,000 ft and is heard by everyone."""
    kx = 111.32 * math.cos(math.radians(lat))
    def at(x, y, **d):
        return {"lat": lat + y / KY, "lon": lon + x / kx, **d}
    dt = (time.time() - T0) % 360
    s = 305 / 3600 * dt
    th = math.radians(300)
    x0, y0 = 13 * math.sin(math.radians(120)) + 0.6, 13 * math.cos(math.radians(120))
    up = at(x0 + s * math.sin(th), y0 + s * math.cos(th), hex="46f001", flight="TST353", alt_baro=int(1500 + 1500 * dt / 60),
            gs=165, track=300, baro_rate=1500)
    a = math.radians((time.time() - T0) * 2 % 360)
    circ = at(10 * math.sin(a), 10 * math.cos(a), hex="46f002", flight="TST477", alt_baro=8000, gs=180,
              track=int((math.degrees(a) + 90) % 360), baro_rate=0)
    return [circ], [up]


# The airline list (Virtual Radar Server's standing data: a BOM, then Code,Name,ICAO,IATA,...), with enough made-up
# rows that the relay takes it for a whole list.
AIRLINES_CSV = "\ufeffCode,Name,ICAO,IATA,PositioningFlightPattern,CharterFlightPattern\r\n" + "".join(
    f"{c},{n},{c},{i},,\r\n" for c, n, i in [("AUA", "Austrian Airlines", "OS"), ("EIN", "Aer Lingus", "EI"),
                                             ("RYR", "Ryanair", "FR"), ("TST", "Testair", "TS"), ("LDM", "Lauda Europe", "OE")]) + "".join(
    f"Q{a}{b},Made-up Air {a}{b},Q{a}{b},,,\r\n" for a in "ABCDEFGHIJ" for b in "ABCDEFGHIJKL")


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
            def row(fn, s, a, code, text, cs=(), **more):
                return {"fn": fn, "scheduledatetime": iso(s), "actualdatetime": iso(a) if a is not None else None,
                        "status": {"code": code, "description": text}, "codeshares": [{"fn": c} for c in cs], **more}
            if path.endswith("inc.json"):
                rows = [row("OS 411", 5, 17, "EST", "expected"), row("EK 127", 20, 18, "APP", "approaching", ["QF 8127"]),
                        row("LX 1514", 30, 24, "EST", "expected", ["OS 7151"]), row("OS 802", -10, 25, "APP", "approaching"),
                        row("OS 411", 1445, None, "PLN", None)]
            else:
                rows = [row("W6 4307", -40, -12, "AIR", "airborne", gate="D21", gateArea="D"),
                        row("FR 22", -20, -18, "AIR", "airborne", gate=None, gateArea="C"),
                        row("FR 6203", -30, -22, "AIR", "airborne", ["OE 215"], gate="C36", gateArea="C")]
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
                       "SWR1514": ("LX1514", "ZRH", "LSZH", "VIE", "LOWW", "4B1814", "SWR", "SWR", "BCS3"),
                       "TST353": ("TS353", "TSA", "TTSA", "TSB", "TTSB", "46F001", "TST", "TST", "AT76")})
            CAT = {"WZZ4307": "Cargo", "SWR1514": "Business_jets"}
            r = FR.get(cs)
            data = [] if not r else [{"fr24_id": "3c0ffee", "flight": r[0], "callsign": cs, "operated_as": r[6], "painted_as": r[7], "type": r[8],
                     "reg": {"TST353": "TS-TST"}.get(cs, ""),
                     "orig_iata": r[1], "orig_icao": r[2], "dest_iata": r[3], "dest_icao": r[4],
                     "dest_iata_actual": "VIE" if cs == "DLH1234" else None, "dest_icao_actual": "LOWW" if cs == "DLH1234" else None,
                     "hex": r[5], "flight_ended": "false", "category": CAT.get(cs, "Passenger"), "datetime_takeoff": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 41 * 60))}]
            return self.send(200, "application/json", json.dumps({"data": data}).encode())
        if path == "/api/live/flight-positions/light":
            if self.headers.get("Authorization") != "Bearer goodkey" or self.headers.get("Accept-Version") != "v1":
                return self.send(401, "application/json", b'{"message":"Unauthenticated"}')
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            n, s_, w, e = (float(x) for x in (q.get("bounds") or ["0,0,0,0"])[0].split(","))
            lo, hi = (int(x) for x in (q.get("altitude_ranges") or ["0-99999"])[0].split("-"))
            heard, missed = away((n + s_) / 2, (w + e) / 2) if abs((n + s_) / 2 - LAT) > .27 or abs((w + e) / 2 - LON) > .4 else ([], [])
            stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3))
            data = [{"fr24_id": "3f" + a["hex"], "hex": a["hex"].upper(), "callsign": a["flight"], "lat": round(a["lat"], 5),
                     "lon": round(a["lon"], 5), "track": a["track"], "alt": a["alt_baro"], "gspeed": a["gs"], "vspeed": a["baro_rate"],
                     "squawk": "4421", "timestamp": stamp, "source": "ADSB"}
                    for a in heard + missed if s_ <= a["lat"] <= n and w <= a["lon"] <= e and lo <= a["alt_baro"] <= hi]
            return self.send(200, "application/json", json.dumps({"data": data[:int((q.get("limit") or ["20"])[0])]}).encode())
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
        if path == "/airlines.csv":
            return self.send(200, "text/csv", AIRLINES_CSV.encode("utf-8"))
        if path == "/nominatim/reverse":   # relay 63 names where sightings on the go were made: Vienna, else a made-up village
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            lat = float((q.get("lat") or ["0"])[0])
            if os.environ.get("SLOW_NAMES"):   # 1.93.0.1: names take 5 s, and the first lookup of each point fails
                time.sleep(5)
                k = f"{(q.get('lat') or [''])[0]},{(q.get('lon') or [''])[0]}"
                if k not in NAMES_FAILED:
                    NAMES_FAILED.add(k)
                    return self.send(503, "text/plain", b"Busy")
            a = {"city": "Vienna", "state": "Vienna", "country": "Austria"} if 47.9 < lat < 48.5 else \
                {"city": "Ia Municipal Unit", "village": "Testdorf", "island": "Testinsel", "country": "Testland"}
            return self.send(200, "application/json", json.dumps({"name": "", "address": a}).encode())
        if path.startswith("/nominatim/"):
            return self.send(200, "application/json", b"[]")
        if path.startswith("/photo/"):     # a drawn stand-in for an aircraft photo
            return self.send(200, "image/svg+xml", SVG_PHOTO.encode())
        if path.startswith("/ps/pub/photos/"):     # Planespotters.net: like theirs, no answer without a User-Agent naming the app and a contact
            if not re.fullmatch(r"\S+/\S+ \(\+https?://\S+\)", self.headers.get("User-Agent") or ""):
                return self.send(403, "application/json", b'{"title":"Error 1010: Access denied"}')
            kind, _, v = path[len("/ps/pub/photos/"):].partition("/")
            k = f"{kind}/{urllib.parse.unquote(v).upper()}"
            PS_ASKED[k] += 1
            p = PS_PHOTOS.get(k)
            img = lambda w, h, s: {"src": f"http://127.0.0.1:{PORT}/psimg/{p[0]}_{s}.svg", "size": {"width": w, "height": h}}   # noqa: E731
            photos = [{"id": p[0], "thumbnail": img(200, 133, "t"), "thumbnail_large": img(420, 280, "280"),
                       "link": f"https://www.planespotters.net/photo/{p[0]}/{p[1]}?utm_source=api", "photographer": "Test Photographer"}] if p else []
            return self.send(200, "application/json", json.dumps({"photos": photos}).encode())
        if path == "/ps/asked":
            return self.send(200, "application/json", json.dumps(PS_ASKED).encode())
        if path.startswith("/psimg/"):
            return self.send(200, "image/svg+xml", PS_PHOTO.encode())
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
            plane("4ca2b7", "EIN6AB", "A320", -2.5, -9.0, 10, 760, 6000, 0, r="EI-DEO"),          # no route listed (relay 68)
            plane("ae0412", "@@@@@@@@", "C130", 4.0, -7.0, 0, 450, 5000, 0, dbFlags=1),          # no callsign: the sources' "@" (relay 70)
        ]
        for i, (hx, cs, t, la, lo, tr) in enumerate(APRON):     # parked at the gates
            ac.append({"hex": hx, "flight": cs, "t": t, "lat": la, "lon": lo, "alt_baro": "ground", "gs": 0, "track": tr})
        if os.environ.get("QUIET"):   # no special planes, so the pages rotate undisturbed
            ac = [a for a in ac if a.get("flight", "").strip() not in ("UAE127", "OEXEN", "BAF586", "RYR22")]
        if os.environ.get("HOVER"):
            ac.append(plane("44041d", "OEBXB", "EC35", 0.3, 0.4, 90, 25, 1500, 0, r="OE-BXB", category="A7"))  # police helicopter over an incident
        qlat, qlon = (float(x) for x in path.split("/")[2:4])
        if abs(qlat - LAT) > .27 or abs(qlon - LON) > .4:      # a place away from Vienna: only what the free networks hear there
            ac += away(qlat, qlon)[0]
        body = json.dumps({"ac": ac, "now": time.time()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
