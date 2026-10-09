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

The relay also keeps the shared history: every plane that comes within the spotting radius is
recorded once per pass (in data/sightings-<date>.json), looked up for its route and aircraft details,
and added to a lifetime logbook of aircraft types, airlines and registrations (data/logbook.json).
All screens show the same list, and it survives restarts. Airport weather (METAR) comes through
here too, because the weather service doesn't allow direct browser access either.

Standard library only: works with Python 3.8+ on Windows, macOS, Linux or in a container.
"""
import argparse
import collections
import csv
import datetime
import heapq
import io
import itertools
import json
import math
import os
import queue
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RELAY_VERSION = 11
BOARD_URL = "https://belstria.github.io/overhead-board/"
PAGE_TTL = 60               # check GitHub for a newer board at most once a minute
SOURCES = [
    {"key": "adsblol", "name": "adsb.lol", "url": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"},
    {"key": "adsbfi", "name": "adsb.fi", "url": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}"},
    {"key": "airplaneslive", "name": "airplanes.live", "url": "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}"},
]
ROUTESET = "https://api.adsb.lol/api/0/routeset"
USER_AGENT = "overhead-board home relay (github.com/Belstria/overhead-board)"
FRESH_S = 9      # screens poll every 10 s; within this window they all share one upstream request
STALE_S = 120    # if every source fails, keep serving the last good answer this long
NUM = r"(-?\d{1,3}(?:\.\d{1,6})?)"
AIRCRAFT = re.compile(rf"^/aircraft/{NUM}/{NUM}/(\d{{1,3}})$")
LEGACY = re.compile(rf"^/(adsblol|airplaneslive)/{NUM}/{NUM}/(\d{{1,3}})$")
PAGE = re.compile(r"^/(?:([a-z0-9-]{1,40})/)?(?:index\.html)?$")   # "/" is the board, "/test/" the test version
CONFIG_FILE = Path(__file__).with_name("overhead.json")   # your saved settings; stays on this computer
SAVED_KEYS = ("lat", "lon", "place", "home", "radius", "units", "sound", "port", "source", "fr24_key", "fr24_budget")
DATA_DIR = Path(__file__).with_name("data")
LOGBOOK_FILE = DATA_DIR / "logbook.json"
SAME_PASS_S = 45 * 60       # the same aircraft within 45 minutes is one pass
DAY_STARTS_H = 3            # "today" runs from 03:00 to 03:00, so late flights count to the evening they belong to
LEARN_S = 24 * 3600         # a new logbook spends its first day learning what is normal here
FR24_API = "https://fr24api.flightradar24.com/api"
FR24_FILE = DATA_DIR / "fr24.json"
FR24_KEEP_S = 2 * 86400     # only today's flights are needed (Flightradar24 allows keeping its data 30 days at most)
FR24_GAP_S = 6.5            # the Explorer plan allows 10 requests a minute
FR24_BUDGET = 27000         # credits a month the relay may spend unless told otherwise (Explorer includes 30,000)
AIRPORTS_CSV = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
AIRPORTS_FILE = DATA_DIR / "airports.json"
CITY_FIX = {"SAW": "Istanbul", "NCL": "Newcastle", "STN": "London", "LGW": "London", "LTN": "London", "BVA": "Paris",
            "CRL": "Brussels", "NYO": "Stockholm", "BGY": "Milan", "MXP": "Milan", "LIN": "Milan", "CIA": "Rome", "FCO": "Rome"}
ICAO_FOR = {"VIE": "LOWW", "BTS": "LZIB", "GRZ": "LOWG", "LNZ": "LOWL", "SZG": "LOWS", "INN": "LOWI", "KLU": "LOWK",
            "MUC": "EDDM", "FRA": "EDDF", "ZRH": "LSZH", "BUD": "LHBP", "PRG": "LKPR", "LHR": "EGLL", "AMS": "EHAM"}

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


def fetch(url, data=None, content_type=None, timeout=10, headers=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html", **(headers or {})}
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
                text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body[:400].decode("utf-8", "replace"))).strip()
                problem = f"HTTP {status}" + (f" {text[:60]}" if text and not text.startswith(str(status)) else "")
            if count is not None:
                was_failing = st["strikes"] > 0
                st.update(ok=st["ok"] + 1, strikes=0, last_status=status, last_ok=time.time(), last_error="")
                _positions[key] = (time.time(), body, src["name"])
                try:
                    record(planes, lat, lon)
                except Exception as e:  # never let history problems break the live board
                    event("warn", f"Couldn't record sightings: {e}")
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


# ---------- shared sightings and lifetime logbook ----------
_data_lock = threading.RLock()
_day = None
_entries = []          # today's sightings, newest first
_by_hex = {}           # hex -> its latest entry today
_logbook = None
_rev = 0
_dirty = set()
_enrich_q = queue.Queue()
_route_cache = {}
_aircraft_cache = {}


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def board_day(t=None):
    return time.strftime("%Y-%m-%d", time.localtime((t or time.time()) - DAY_STARTS_H * 3600))


def _ensure_day():
    global _day, _entries, _by_hex
    d = board_day()
    if d != _day:
        _day = d
        _entries = _load(DATA_DIR / f"sightings-{d}.json", [])
        _by_hex = {}
        for e in reversed(_entries):
            _by_hex[e.get("hex", "")] = e


def _book():
    global _logbook
    if _logbook is None:
        _logbook = _load(LOGBOOK_FILE, None) or {"since": time.strftime("%Y-%m-%d"), "startedTs": time.time(),
                                                 "sightings": 0, "types": {}, "airlines": {}, "regs": {}}
    return _logbook


def _changed(*what):
    global _rev
    _rev += 1
    _dirty.update(what)


def _saver():
    """Write changed files every few seconds, atomically, so a crash never leaves half a file."""
    while True:
        time.sleep(4)
        with _data_lock:
            todo = set(_dirty)
            _dirty.clear()
            files = []
            if "day" in todo and _day:
                files.append((DATA_DIR / f"sightings-{_day}.json", json.dumps(_entries, separators=(",", ":"))))
            if "fr24" in todo and _fr24 is not None:
                files.append((FR24_FILE, json.dumps(_fr24, separators=(",", ":"))))
            if "book" in todo and _logbook is not None:
                files.append((LOGBOOK_FILE, json.dumps(_logbook, separators=(",", ":"))))
        for path, text in files:
            try:
                DATA_DIR.mkdir(exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, path)
            except OSError as e:
                event("warn", f"Couldn't save {path.name}: {e}")


def _dist_km(lat1, lon1, lat2, lon2):
    kx = 111.32 * math.cos(math.radians(lat1))
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 110.57)


def _emergency(ac):
    sq = str(ac.get("squawk") or "")
    if sq in ("7500", "7600", "7700"):
        return sq
    em = ac.get("emergency")
    return em if em and em != "none" else ""


def _note_first(book, key, name, e, flag, learning=False):
    item = book.get(key)
    if item is None:
        item = book[key] = {"name": name or "", "first": e["ts"], "count": 0}
        if not learning:  # during the first day everything is new, so nothing is marked
            e[flag] = True
    item["count"] += 1
    item["last"] = e["ts"]
    if name and not item.get("name"):
        item["name"] = name


def record(planes, lat, lon):
    """Called with every fresh position update: log planes that enter the spotting radius."""
    radius = ARGS.radius or 15.0
    now = time.time()
    try:
        lat, lon = float(lat), float(lon)
    except ValueError:
        return
    with _data_lock:
        _ensure_day()
        changed = False
        for ac in planes:
            if not isinstance(ac, dict):
                continue
            la, lo, hx = ac.get("lat"), ac.get("lon"), str(ac.get("hex") or "").lower()
            if la is None or lo is None or not hx or ac.get("alt_baro") == "ground":
                continue
            d = _dist_km(lat, lon, la, lo)
            alt = ac.get("alt_baro") if isinstance(ac.get("alt_baro"), (int, float)) else ac.get("alt_geom")
            e = _by_hex.get(hx)
            if e and now - e.get("lastSeen", 0) > SAME_PASS_S:
                e = None
            if e:
                e["lastSeen"] = now
                if d < e["minDist"] - 0.05:
                    e["minDist"], e["altAtMin"], changed = round(d, 2), alt, True
                gs = ac.get("gs")
                if isinstance(gs, (int, float)) and gs > e.get("maxSpeed", 0) + 1:
                    e["maxSpeed"], changed = round(gs), True
                em = _emergency(ac)
                if em and em != e.get("emergency"):
                    e["emergency"], changed = em, True
                    event("warn", f"Emergency code {em} from {e.get('callsign') or hx}")
            elif d <= radius:
                cs = str(ac.get("flight") or "").strip().upper()
                flags = ac.get("dbFlags") or 0
                e = {"id": f"{hx}-{int(now)}", "ts": int(now * 1000), "time": time.strftime("%H:%M"), "hex": hx,
                     "callsign": cs, "reg": ac.get("r") or "", "typeCode": str(ac.get("t") or "").upper(),
                     "desc": ac.get("desc") or "", "minDist": round(d, 2), "altAtMin": alt,
                     "maxSpeed": round(ac.get("gs") or 0), "lastSeen": now,
                     "pos": [round(la, 4), round(lo, 4), ac.get("track")],
                     "military": bool(flags & 1), "interesting": bool(flags & 2), "emergency": _emergency(ac),
                     "adsbCat": str(ac.get("category") or "")}
                if e["emergency"]:
                    event("warn", f"Emergency code {e['emergency']} from {cs or hx}, {d:.1f} km away")
                _entries.insert(0, e)
                del _entries[5000:]
                _by_hex[hx] = e
                book = _book()
                book["sightings"] = book.get("sightings", 0) + 1
                cats = book.setdefault("categories", {})
                cat = category_of(e)
                cats[cat] = cats.get(cat, 0) + 1
                learning = now - book.get("startedTs", 0) < LEARN_S
                if e["typeCode"]:
                    _note_first(book["types"], e["typeCode"], e["desc"], e, "newType", learning)
                if e["reg"]:
                    _note_first(book["regs"], e["reg"], e["typeCode"], e, "newReg", learning)
                m = re.match(r"^([A-Z]{3})\d", cs)
                if m:
                    _note_first(book["airlines"], m.group(1), "", e, "newAirline", learning)
                _changed("book")
                _enrich_q.put(e["id"])
                changed = True
                event("debug", f"Spotted {cs or hx} at {d:.1f} km", echo=False)
        if changed:
            _changed("day")


# ---------- what kind of flight a sighting is, from free data only (the logbook stays the same with or without
# a paid source). Order matters: a military helicopter counts as military.
CARGO_AIRLINES = {"FDX", "UPS", "BCS", "DHK", "DHX", "DAE", "CLX", "ICV", "GEC", "BOX", "ABW", "CKS", "GTI", "PAC", "NCA",
                  "CAO", "CKK", "MPH", "SQC", "TAY", "SWN", "ABR", "NPT", "CLU", "AHK", "MSX", "QAC", "CSB", "TPA", "LCO"}
HELICOPTERS = {"EC35", "EC45", "EC30", "EC55", "EC75", "AS50", "AS55", "AS65", "AS32", "A109", "A119", "A139", "A169", "A189",
               "H160", "H175", "B06", "B407", "B412", "B429", "B505", "R22", "R44", "R66", "S76", "S92", "NH90", "UH1",
               "H60", "BK17", "EH10", "MI8", "AW09"}
MILITARY_TYPES = {"C17", "C5M", "A400", "C130", "C30J", "K35R", "EUFI", "F16", "F35", "P3", "C295", "E390", "C160", "KC2",
                  "A332M", "MRTT", "E3TF", "P8", "PC7", "PC9", "SB39", "L159", "C27J"}
BIZJETS = {"C25A", "C25B", "C25C", "C25M", "C501", "C510", "C525", "C550", "C551", "C55B", "C560", "C56X", "C650", "C680",
           "C68A", "C700", "C750", "CL30", "CL35", "CL60", "GL5T", "GL6T", "GL7T", "GLEX", "GLF2", "GLF3", "GLF4", "GLF5",
           "GLF6", "G150", "G200", "G280", "GALX", "FA10", "FA20", "FA50", "FA6X", "FA7X", "FA8X", "F2TH", "F900", "LJ31",
           "LJ35", "LJ40", "LJ45", "LJ60", "LJ70", "LJ75", "H25B", "H25C", "E50P", "E55P", "E545", "E550", "PC24", "PRM1",
           "HDJT", "BE40", "SF50", "EA50", "ASTR", "E135L", "E35L", "CRJ2B"}
LIGHT = {"C150", "C152", "C162", "C170", "C172", "C177", "C182", "C206", "C210", "P28A", "P28B", "P28R", "PA28", "PA32",
         "PA34", "PA44", "PA46", "P46T", "DA20", "DA40", "DA42", "DA50", "DA62", "SR20", "SR22", "S22T", "BE33", "BE35",
         "BE36", "BE58", "BE20", "B350", "M20P", "M20T", "TB10", "TB20", "TBM7", "TBM8", "TBM9", "PC12", "PC6", "EV97",
         "C42", "DR40", "AT3", "SIRA", "WT9", "P208", "G115", "RV7", "RV8", "C208", "AA5", "P32R", "P32T", "PA24",
         "PA18", "PA38", "A210", "DV20", "C441", "C421", "C414", "C340", "C310", "C337", "C185", "C180", "C140", "BE9L",
         "BE10", "BE55", "BE76", "BE23", "BE24", "DA62", "P68", "P180", "PC21", "M20J", "M20R", "M20K", "SR2T", "TOBA",
         "S205", "Z42", "Z43", "ZLIN", "TB9", "TB21", "AC11", "MAGI", "SAVG", "VIRS", "PIVI", "FDCT", "ECHO", "SHRK",
         "TECN", "DIMO", "HUSK", "CRUZ", "PNR2", "BR23", "GLID", "ULAC"}


def category_of(e):
    t, cs = str(e.get("typeCode") or "").upper(), str(e.get("callsign") or "").upper()
    adsb = str(e.get("adsbCat") or "").upper()
    m = re.match(r"^([A-Z]{3})\d", cs)
    if e.get("military") or t in MILITARY_TYPES:
        return "military"
    if t in HELICOPTERS or adsb == "A7":
        return "helicopter"
    if m and m.group(1) in CARGO_AIRLINES:
        return "cargo"
    if t in BIZJETS:
        return "bizjet"
    if t in LIGHT or (adsb == "A1" and not m):
        return "private"
    if m:
        return "passenger"
    if re.match(r"^[A-Z0-9]{3,7}$", cs):     # a registration as callsign (OEKON, DELFH, N60063): general aviation
        return "private"
    return "other"


def _backfill_categories():
    """Older logbooks have no categories: count them once from the saved days."""
    b = _book()
    if "categories" in b:
        return
    cats = {}
    for f in sorted(DATA_DIR.glob("sightings-*.json")):
        for e in _load(f, []):
            c = category_of(e)
            cats[c] = cats.get(c, 0) + 1
    b["categories"] = cats
    _changed("book")
    if cats:
        event("info", f"Logbook categories counted from {sum(cats.values())} saved sightings")


def _route_for(cs):
    if cs in _route_cache:
        return _route_cache[cs]
    out = None
    status, _, body, _ = fetch(f"https://api.adsbdb.com/v0/callsign/{cs}")
    if status == 200:
        try:
            fr = json.loads(body).get("response", {}).get("flightroute") or {}
            o, d, al = fr.get("origin") or {}, fr.get("destination") or {}, fr.get("airline") or {}
            if o and d:
                out = {"from": {"code": o.get("iata_code") or o.get("icao_code"), "city": o.get("municipality") or o.get("name"),
                                "lat": o.get("latitude"), "lon": o.get("longitude")},
                       "to": {"code": d.get("iata_code") or d.get("icao_code"), "city": d.get("municipality") or d.get("name"),
                              "lat": d.get("latitude"), "lon": d.get("longitude")},
                       "flightIata": fr.get("callsign_iata") or "", "airlineName": al.get("name") or "",
                       "airlineIata": al.get("iata") or "", "airlineIcao": al.get("icao") or ""}
        except (ValueError, AttributeError):
            pass
    if status in (200, 404):
        _route_cache[cs] = out
    return out


def _route_fits(route, pos):
    """Callsigns get reused (Ryanair's RYR3EG is listed as Newcastle to Dublin, whatever it is flying today),
    so a listed route only counts when the plane is actually along it and heading the right way."""
    f, t = (route or {}).get("from") or {}, (route or {}).get("to") or {}
    if not pos or None in (f.get("lat"), f.get("lon"), t.get("lat"), t.get("lon")):
        return True
    la, lo, track = pos
    r = math.radians

    def ang(a1, o1, a2, o2):
        c = math.sin(r(a1)) * math.sin(r(a2)) + math.cos(r(a1)) * math.cos(r(a2)) * math.cos(r(o2 - o1))
        return math.acos(max(-1.0, min(1.0, c)))

    def brg(a1, o1, a2, o2):
        return math.atan2(math.sin(r(o2 - o1)) * math.cos(r(a2)),
                          math.cos(r(a1)) * math.sin(r(a2)) - math.sin(r(a1)) * math.cos(r(a2)) * math.cos(r(o2 - o1)))

    R = 6371.0
    length = ang(f["lat"], f["lon"], t["lat"], t["lon"]) * R
    d13 = ang(f["lat"], f["lon"], la, lo)
    if min(d13 * R, ang(la, lo, t["lat"], t["lon"]) * R) < 80:
        return True
    off = brg(f["lat"], f["lon"], la, lo) - brg(f["lat"], f["lon"], t["lat"], t["lon"])
    xt = math.asin(math.sin(d13) * math.sin(off)) * R
    at = math.acos(max(-1.0, min(1.0, math.cos(d13) / math.cos(xt / R)))) * R * (-1 if math.cos(off) < 0 else 1)
    if abs(xt) > max(120.0, length * 0.3) or at < -100 or at > length + 100:
        return False
    if isinstance(track, (int, float)):
        want = (math.degrees(brg(la, lo, t["lat"], t["lon"])) + 360) % 360
        if abs(((track - want + 540) % 360) - 180) > 100:
            return False
    return True


def _routeset_for(cs, pos):
    """adsb.lol's route service, which also knows where the plane is."""
    if not pos:
        return None
    status, _, body, _ = fetch(ROUTESET, data=json.dumps({"planes": [{"callsign": cs, "lat": pos[0], "lng": pos[1]}]}).encode(),
                               content_type="application/json")
    if status != 200:
        return None
    try:
        r = (json.loads(body) or [None])[0] or {}
        ap = r.get("_airports") or []
        if len(ap) < 2 or r.get("plausible") in (False, 0):
            return None
        a, b = ap[0], ap[-1]
        out = {"from": {"code": a.get("iata") or a.get("icao"), "city": a.get("location") or a.get("name"), "lat": a.get("lat"), "lon": a.get("lon")},
               "to": {"code": b.get("iata") or b.get("icao"), "city": b.get("location") or b.get("name"), "lat": b.get("lat"), "lon": b.get("lon")}}
        return out if _route_fits(out, pos) else None
    except (ValueError, AttributeError, IndexError, TypeError):
        return None


def _aircraft_for(hx):
    if hx in _aircraft_cache:
        return _aircraft_cache[hx]
    out = None
    status, _, body, _ = fetch(f"https://api.adsbdb.com/v0/aircraft/{hx}")
    if status == 200:
        try:
            a = json.loads(body).get("response", {}).get("aircraft") or {}
            if a:
                out = {"aircraftType": a.get("type") or "", "manufacturer": a.get("manufacturer") or "",
                       "icaoType": a.get("icao_type") or "", "regFromDb": a.get("registration") or "",
                       "owner": a.get("registered_owner") or "", "ownerCountry": a.get("registered_owner_country_name") or "",
                       "photo": a.get("url_photo") or "", "photoThumb": a.get("url_photo_thumbnail") or ""}
        except (ValueError, AttributeError):
            pass
    if status in (200, 404):
        _aircraft_cache[hx] = out
    return out


def _enricher():
    """Look up route and aircraft details for new sightings, one at a time, gently."""
    while True:
        eid = _enrich_q.get()
        with _data_lock:
            e = next((x for x in _entries if x.get("id") == eid), None)
            cs, hx = (e or {}).get("callsign", ""), (e or {}).get("hex", "")
        if not e:
            continue
        route = _route_for(cs) if cs else None
        airline = {k: route[k] for k in ("airlineName", "airlineIata", "airlineIcao") if route and route.get(k)}
        if route and not _route_fits(route, e.get("pos")):
            event("info", f"Ignoring the listed route {route['from']['code']} → {route['to']['code']} for {cs}: "
                          "the plane is nowhere near it (the callsign is used for other flights too)")
            route = _routeset_for(cs, e.get("pos"))
            if route:
                route.update(airline)
        info = _aircraft_for(hx) if hx else None
        with _data_lock:
            if airline:
                e.update(airline)
            if route:
                e.update(route)
            if info:
                e.update({k: v for k, v in info.items() if v})
                if not e.get("reg") and info.get("regFromDb"):
                    e["reg"] = info["regFromDb"]
                if not e.get("typeCode") and info.get("icaoType"):
                    e["typeCode"] = info["icaoType"]
            book = _book()
            t = book["types"].get(e.get("typeCode") or "")
            if t is not None and not t.get("name") and info:
                t["name"] = " ".join(x for x in (info.get("manufacturer", "").split(" ")[0], info.get("aircraftType")) if x)
            m = re.match(r"^([A-Z]{3})\d", cs or "")
            a = book["airlines"].get(m.group(1)) if m else None
            if a is not None and route:
                a["name"] = a.get("name") or route.get("airlineName", "")
                a["iata"] = a.get("iata") or route.get("airlineIata", "")
            _changed("day", "book")
        time.sleep(.4)


# ---------- Flightradar24 (optional, paid): real flight numbers and routes ----------
# Only boards that ask for it (the test-api board) trigger lookups, so the other boards stay on free data and
# nothing is spent while no such board is open. The key lives in overhead.json on this computer only.
_fr24 = None                 # {"flights": {hex|callsign: info}, "usage": {...}}
_fr24_q = []                 # (priority, order, key, callsign, hex): 0 = a board is showing it, 1 = Spotted today
_fr24_queued = set()
_fr24_cv = threading.Condition()
_fr24_order = itertools.count()
_fr24_state = {"state": "off", "error": ""}
_airports = None             # {"iata": {code: [city, lat, lon, icao]}, "icao": {icao: iata}}


def fr24_key():
    k = (ARGS.fr24_key or "").strip()
    return "" if k.lower() in ("", "off", "none", "0") else k


def fr24_on():
    """Lookups happen while there is a key, it hasn't been refused in the last six hours, and the budget isn't spent."""
    if not fr24_key():
        return False
    if _fr24_state["state"] == "refused" and time.time() - _fr24_state.get("refusedAt", 0) < 6 * 3600:
        return False
    with _data_lock:
        return _fr24_usage().get("credits", 0) < _fr24_budget()


def _fr24_data():
    global _fr24
    if _fr24 is None:
        _fr24 = _load(FR24_FILE, None) or {"flights": {}, "usage": {}}
        _fr24_prune()
    return _fr24


def _fr24_prune():
    cutoff = time.time() - FR24_KEEP_S
    fl = _fr24["flights"]
    for k in [k for k, v in fl.items() if v.get("t", 0) < cutoff]:
        del fl[k]


def _fr24_usage():
    u = _fr24_data()["usage"]
    month, day = time.strftime("%Y-%m"), time.strftime("%Y-%m-%d")
    if u.get("month") != month:
        u.clear()
        u.update({"month": month, "credits": 0, "lookups": 0})
    if u.get("day") != day:
        u.update({"day": day, "creditsToday": 0, "lookupsToday": 0})
        _fr24_prune()
    return u


def _fr24_budget():
    try:
        return int(ARGS.fr24_budget) if ARGS.fr24_budget is not None else FR24_BUDGET
    except (TypeError, ValueError):
        return FR24_BUDGET


def fr24_info(cs, hx):
    """What Flightradar24 said about this flight, if it was looked up and is still fresh."""
    with _data_lock:
        info = _fr24_data()["flights"].get(f"{hx}|{cs}")
    if not info:
        return None
    age = time.time() - info.get("t", 0)
    if info.get("none") and age > 3 * 3600:     # nothing found: worth another try later
        return None
    return info if age < 14 * 3600 else None


def fr24_want(cs, hx, priority):
    """Queue a lookup for a flight with a callsign (airline, cargo, business or private)."""
    if not fr24_on() or not cs or not hx or not re.match(r"^[A-Z0-9]{3,8}$", cs) or fr24_info(cs, hx):
        return
    key = f"{hx}|{cs}"
    with _fr24_cv:
        if key in _fr24_queued or len(_fr24_q) > 300:
            return
        _fr24_queued.add(key)
        heapq.heappush(_fr24_q, (priority, next(_fr24_order), key, cs, hx))
        _fr24_cv.notify()


def _airport(iata, icao):
    iata, icao = (iata or "").upper(), (icao or "").upper()
    db = _airports or {}
    if not iata and icao:
        iata = (db.get("icao") or {}).get(icao, "")
    row = (db.get("iata") or {}).get(iata)
    out = {"code": iata or icao}
    if row:
        out.update({"city": row[0], "lat": row[1], "lon": row[2]})
    return out if out["code"] else None


def _load_airports():
    """City names for airport codes, from the free OurAirports list (refreshed every two months)."""
    global _airports
    db = _load(AIRPORTS_FILE, None)
    if db and time.time() - db.get("fetched", 0) < 60 * 86400:
        _airports = db
        return
    status, _, body, _ = fetch(AIRPORTS_CSV, timeout=60)
    if status != 200:
        _airports = db or {}
        event("warn", "Couldn't download the airport list; routes from Flightradar24 show airport codes only")
        return
    iata, icao = {}, {}
    for r in csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))):
        code = (r.get("iata_code") or "").strip().upper()
        if len(code) != 3 or r.get("type") == "closed":
            continue
        try:
            lat, lon = round(float(r["latitude_deg"]), 4), round(float(r["longitude_deg"]), 4)
        except (KeyError, ValueError):
            continue
        city = CITY_FIX.get(code) or (r.get("municipality") or r.get("name") or "").split(",")[0].strip()
        ic = (r.get("icao_code") or r.get("gps_code") or r.get("ident") or "").strip().upper()
        if code not in iata or r.get("type") == "large_airport":
            iata[code] = [city, lat, lon, ic]
        if ic:
            icao[ic] = code
    _airports = {"fetched": time.time(), "iata": iata, "icao": icao}
    try:
        DATA_DIR.mkdir(exist_ok=True)
        AIRPORTS_FILE.write_text(json.dumps(_airports, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass
    event("info", f"Airport list ready: {len(iata)} airports")


def _fr24_lookup(cs, hx):
    """One flight-summary request: the most recent flight with this callsign. Returns (info or None, http status)."""
    now = time.time()
    q = urllib.parse.urlencode({
        "flight_datetime_from": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now - 20 * 3600)),
        "flight_datetime_to": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now + 120)),
        "callsigns": cs, "sort": "desc", "limit": 1})
    status, _, body, _ = fetch(f"{FR24_API}/flight-summary/full?{q}", timeout=15, headers={
        "Authorization": f"Bearer {fr24_key()}", "Accept": "application/json", "Accept-Version": "v1"})
    if status != 200:
        return None, status, 0
    try:
        rows = (json.loads(body) or {}).get("data") or []
    except ValueError:
        return None, 502, 0
    if not rows:
        return {"none": True, "t": now}, 200, 1
    r = rows[0]
    ended = str(r.get("flight_ended")).lower() == "true"
    credits = 3 if ended else 2
    if str(r.get("hex") or "").lower() not in ("", hx.lower()):
        return {"none": True, "t": now, "note": "different aircraft"}, 200, credits
    dest = r.get("dest_iata") or r.get("destination_iata")
    dest_icao = r.get("dest_icao") or r.get("destination_icao")
    actual = r.get("dest_iata_actual") or ""
    actual_icao = r.get("dest_icao_actual") or r.get("destination_icao_actual") or ""
    info = {"t": now, "flight": (r.get("flight") or "").upper(), "callsign": cs,
            "from": _airport(r.get("orig_iata"), r.get("orig_icao") or r.get("origin_icao")),
            "to": _airport(dest, dest_icao),
            "operator": r.get("operated_as") or "", "livery": r.get("painted_as") or "",
            "category": r.get("category") or "", "type": r.get("type") or "", "reg": r.get("reg") or "",
            "takeoff": r.get("datetime_takeoff") or "", "runwayTakeoff": r.get("runway_takeoff") or "",
            "runwayLanded": r.get("runway_landed") or "", "ended": ended}
    if actual_icao and dest_icao and actual_icao != dest_icao:
        info["divertedTo"] = _airport(actual, actual_icao)
    return info, 200, credits


def _fr24_worker():
    if fr24_key():
        _load_airports()
    while True:
        with _fr24_cv:
            while not _fr24_q:
                _fr24_cv.wait()
            _, _, key, cs, hx = heapq.heappop(_fr24_q)
        try:
            if not fr24_on() or fr24_info(cs, hx):
                continue
            with _data_lock:
                usage = _fr24_usage()
                if usage.get("credits", 0) >= _fr24_budget():
                    if _fr24_state["state"] != "budget":
                        event("warn", f"Flightradar24: this month's budget of {_fr24_budget():,} credits is used up; "
                                      "boards use the free sources until next month")
                    _fr24_state.update(state="budget")
                    continue
            info, status, credits = _fr24_lookup(cs, hx)
            with _data_lock:
                usage = _fr24_usage()
                usage["credits"] = usage.get("credits", 0) + credits
                usage["creditsToday"] = usage.get("creditsToday", 0) + credits
                if credits:
                    usage["lookups"] = usage.get("lookups", 0) + 1
                    usage["lookupsToday"] = usage.get("lookupsToday", 0) + 1
                if info:
                    _fr24_data()["flights"][key] = info
                _changed("fr24")
            if status in (401, 403):
                _fr24_state.update(state="refused", error=f"key refused (HTTP {status})", refusedAt=time.time())
                event("warn", f"Flightradar24 refused the API key (HTTP {status}): boards use the free sources. "
                              "Check the key, or the subscription has ended.")
                with _fr24_cv:
                    _fr24_q.clear()
                    _fr24_queued.clear()
            elif status == 429:
                _fr24_state.update(state="ok", error="too many requests; slowing down")
                time.sleep(60)
            elif status != 200:
                _fr24_state.update(state="error", error=f"HTTP {status}")
                event("warn", f"Flightradar24 lookup for {cs} failed (HTTP {status})", echo=False)
            else:
                if _fr24_state["state"] != "ok":
                    event("info", "Flightradar24 lookups working")
                _fr24_state.update(state="ok", error="")
                if info and not info.get("none"):
                    f, t = info.get("from") or {}, info.get("to") or {}
                    event("debug", f"Flightradar24: {cs} is {info['flight'] or '?'} {f.get('code', '?')} → {t.get('code', '?')}", echo=False)
        except Exception as e:  # never let the paid extra break the relay
            _fr24_state.update(state="error", error=str(e))
        finally:
            with _fr24_cv:
                _fr24_queued.discard(key)
        time.sleep(FR24_GAP_S)


def fr24_status():
    if not fr24_key():
        return {"state": "off"}
    with _data_lock:
        u = dict(_fr24_usage())
    return {"state": _fr24_state["state"] if _fr24_state["state"] != "off" else "ready", "error": _fr24_state["error"],
            "credits": u.get("credits", 0), "budget": _fr24_budget(), "lookups": u.get("lookups", 0),
            "creditsToday": u.get("creditsToday", 0), "lookupsToday": u.get("lookupsToday", 0),
            "queue": len(_fr24_q), "airports": len((_airports or {}).get("iata") or {})}


def fr24_overlay(entries):
    """Spotted today for boards that use Flightradar24: its flight numbers and routes over the free ones."""
    out, now = [], time.time()
    for e in entries:
        cs, hx = e.get("callsign") or "", e.get("hex") or ""
        info = fr24_info(cs, hx) if cs else None
        if info and not info.get("none"):
            e = dict(e)
            if info.get("flight"):
                e["flightIata"] = info["flight"]
            if info.get("from") and info.get("to"):
                e["from"], e["to"] = info["from"], info["to"]
            e.update({"fr24": True, "category": info.get("category"), "operator": info.get("operator"),
                      "livery": info.get("livery"), "divertedTo": info.get("divertedTo")})
        elif not info and now - e.get("ts", 0) / 1000 < 3 * 3600:
            fr24_want(cs, hx, 1)
        out.append(e)
    return out


def day_stats(entries, over_km):
    """Today in numbers, over every sighting of the day (the list itself only sends the newest ones)."""
    airlines, types, hours, counts, names = set(), set(), collections.Counter(), collections.Counter(), {}
    overhead, low, high, fast = 0, None, None, None
    for e in entries:
        m = re.match(r"^([A-Z]{3})\d", e.get("callsign") or "")
        al = m.group(1) if m else ""
        if al:
            airlines.add(al)
            counts[al] += 1
            names[al] = names.get(al) or e.get("airlineName") or ""
        if e.get("typeCode"):
            types.add(e["typeCode"])
        md, alt, sp = e.get("minDist"), e.get("altAtMin"), e.get("maxSpeed")
        if isinstance(md, (int, float)) and md <= over_km:
            overhead += 1
        hours[int(time.strftime("%H", time.localtime(e.get("ts", 0) / 1000)))] += 1
        if isinstance(alt, (int, float)) and alt > 0:
            if low is None or alt < low["altAtMin"]:
                low = e
            if high is None or alt > high["altAtMin"]:
                high = e
        if isinstance(sp, (int, float)) and sp > 0 and (fast is None or sp > fast["maxSpeed"]):
            fast = e
    first = min(entries, key=lambda e: e.get("ts", 0)) if entries else None
    top = counts.most_common(1)

    def slim(e):
        return {k: e.get(k) for k in ("callsign", "flightIata", "hex", "reg", "airlineIata", "airlineName", "time", "ts",
                                      "altAtMin", "maxSpeed", "typeCode")} if e else None

    return {"planes": len(entries), "airlines": len(airlines), "types": len(types), "overhead": overhead,
            "busiestHour": hours.most_common(1)[0][0] if hours else None,
            "lowest": slim(low), "highest": slim(high), "fastest": slim(fast), "first": slim(first),
            "topAirline": {"code": top[0][0], "name": names.get(top[0][0], ""), "count": top[0][1]} if top else None,
            "newTypes": sum(1 for e in entries if e.get("newType")),
            "newAirlines": sum(1 for e in entries if e.get("newAirline")),
            "dayStarts": f"{DAY_STARTS_H:02d}:00"}


def sightings_json(api=False, over_km=3.0, everything_wanted=False):
    with _data_lock:
        _ensure_day()
        everything = list(_entries)
        day, rev = _day, _rev
    if api:
        everything = fr24_overlay(everything)
    return {"version": RELAY_VERSION, "date": day, "rev": rev, "entries": everything if everything_wanted else everything[:400],
            "stats": day_stats(everything, over_km)}


def logbook_json():
    with _data_lock:
        b = _book()
        regs = b.get("regs", {})
        top = sorted(regs.items(), key=lambda kv: -kv[1].get("count", 0))[:15]
        return {"version": RELAY_VERSION, "since": b.get("since"), "sightings": b.get("sightings", 0),
                "learningUntil": int((b.get("startedTs", 0) + LEARN_S) * 1000), "categories": b.get("categories", {}),
                "types": b.get("types", {}), "airlines": b.get("airlines", {}), "regsCount": len(regs),
                "regsTop": [{"reg": k, **v} for k, v in top],
                "regsRecent": [{"reg": k, **v} for k, v in sorted(regs.items(), key=lambda kv: -kv[1].get("first", 0))[:15]]}


def metar(ids):
    status, _, body, _ = cached("metar:" + ids, 600, lambda: fetch(
        f"https://aviationweather.gov/api/data/metar?ids={ids}&format=raw&taf=false", timeout=10))
    return status, body


# ---------- Vienna Airport's arrivals and departures: planned and expected times, so the board can show delays.
# The airport publishes them for its own website. Read at most every three minutes, and only while a board asks.
VIE_FLIGHTS = "https://viennaairport.com/jart/prj3/va/data/flights/{}.json"      # inc = arrivals, out = departures
_vie = {"t": 0.0, "ok": 0.0, "index": {}, "busy": False, "error": "", "counts": (0, 0)}
_vie_lock = threading.Lock()


def vie_on():
    return (ARGS.home or "VIE").upper() == "VIE"


def fn_key(fn):
    """OS 007, OS7 and OS 0007 are the same flight."""
    m = re.match(r"^\s*([A-Z0-9]{2,3})\s*0*(\d{1,5})([A-Z]?)\s*$", str(fn or "").upper())
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else ""


def _iso_ms(v):
    if not v:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return int(d.timestamp() * 1000)
    except ValueError:
        return None


def _vie_load():
    index, counts = {}, []
    try:
        for kind, name in (("arr", "inc"), ("dep", "out")):
            status, _, body, _ = fetch(VIE_FLIGHTS.format(name), timeout=15,
                                       headers={"Accept": "application/json", "Referer": "https://viennaairport.com/"})
            if status != 200:
                raise ValueError(f"HTTP {status}")
            mon = json.loads(body.decode("utf-8")).get("monitor") or {}
            rows = mon.get("departure") or mon.get("arrival") or []
            counts.append(len(rows))
            for r in rows:
                st = r.get("status") or {}
                e = {"kind": kind, "fn": r.get("fn") or "", "sched": _iso_ms(r.get("scheduledatetime")),
                     "actual": _iso_ms(r.get("actualdatetime")), "code": st.get("code") or "", "text": st.get("description") or ""}
                for fn in [r.get("fn")] + [c.get("fn") for c in (r.get("codeshares") or []) if isinstance(c, dict)]:
                    k = fn_key(fn)
                    if k:
                        index.setdefault(k, []).append(e)
        first = not _vie["ok"] or _vie["error"]
        with _vie_lock:
            _vie.update(index=index, ok=time.time(), error="", counts=tuple(counts))
        if first:
            event("info", f"Vienna Airport's flight lists read: {counts[0]} arrivals, {counts[1]} departures")
    except Exception as ex:  # the site changed, or is down: try again in a minute
        with _vie_lock:
            was = _vie["error"]
            _vie.update(error=str(ex), t=time.time() - 120)
        if not was:
            event("warn", f"Couldn't read Vienna Airport's flight lists ({ex}); the times row stays empty")
    finally:
        with _vie_lock:
            _vie["busy"] = False


def vie_refresh():
    with _vie_lock:
        if _vie["busy"] or time.time() - _vie["t"] < 180:
            return
        _vie["busy"], _vie["t"] = True, time.time()
    threading.Thread(target=_vie_load, daemon=True).start()


def vie_times(fn, frm, to):
    """The airport's entry for this flight, from the list it belongs to, closest to now."""
    if not vie_on():
        return {"status": "none", "why": "home airport isn't Vienna"}
    vie_refresh()
    with _vie_lock:
        cands = list(_vie["index"].get(fn_key(fn), []))
        loaded = bool(_vie["ok"])
    if not loaded:
        return {"status": "pending"}
    if to == "VIE":
        cands = [e for e in cands if e["kind"] == "arr"]
    elif frm == "VIE":
        cands = [e for e in cands if e["kind"] == "dep"]
    now = time.time() * 1000
    cands = [e for e in cands if (e["actual"] or e["sched"]) and abs((e["actual"] or e["sched"]) - now) < 4 * 3600e3]
    if not cands:
        return {"status": "none"}
    e = min(cands, key=lambda e: abs((e["actual"] or e["sched"]) - now))
    final = e["code"] in ("BLI", "AIR")             # landed / airborne: the time is what happened, not an estimate
    delay = round((e["actual"] - e["sched"]) / 60000) if e["actual"] and e["sched"] else None
    return {"status": "ok", "airport": "VIE", **e, "final": final, "delay": delay}


def vie_status():
    with _vie_lock:
        return {"on": vie_on(), "ageS": int(time.time() - _vie["ok"]) if _vie["ok"] else None,
                "arrivals": _vie["counts"][0], "departures": _vie["counts"][1], "error": _vie["error"]}


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
    return {"version": RELAY_VERSION, "uptime_s": int(now - STARTED), "sources": sources, "events": events, "fr24": fr24_status(),
            "vie": vie_status()}


_board_seen = {}


def board_html(sub=""):
    copy = Path(__file__).with_name(f"board-cache{'-' + sub if sub else ''}.html")
    if ARGS.local and not sub:
        html = Path(ARGS.local).read_text(encoding="utf-8")
    else:
        url = BOARD_URL + (sub + "/" if sub else "")
        # GitHub's servers keep a page for up to ten minutes; asking for a fresh address each time skips that wait.
        status, _, body, _ = cached("page:" + sub, PAGE_TTL, lambda: fetch(f"{url}?v={int(time.time())}", timeout=15))
        if status == 200:
            html = body.decode("utf-8")
            seen = _board_seen.get(sub)
            if seen and seen != html:
                event("info", f"Downloaded a newer {'test ' if sub else ''}board from GitHub; screens pick it up when they reload")
            _board_seen[sub] = html
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
              f"window.OVERHEAD_DEFAULTS={config};window.OVERHEAD_FR24={'true' if fr24_on() else 'false'};</script>")
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
        if re.fullmatch(r"/[a-z0-9-]{1,40}", path) and path not in ("/health", "/status", "/sightings", "/logbook", "/metar", "/flightinfo", "/times"):
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
        if path == "/sightings":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            try:
                over = min(20.0, max(0.1, float((q.get("over") or ["3"])[0])))
            except ValueError:
                over = 3.0
            api = (q.get("api") or [""])[0] == "1"
            data = sightings_json(api, over, (q.get("all") or [""])[0] == "1")
            if api:
                data["fr24"] = fr24_on()
            return self.reply(200, "application/json", json.dumps(data).encode())
        if path == "/flightinfo":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            cs = (q.get("cs") or [""])[0].strip().upper()[:8]
            hx = (q.get("hex") or [""])[0].strip().lower()[:6]
            if not fr24_on():
                body = {"status": "off"}
            else:
                info = fr24_info(cs, hx)
                if info:
                    body = {"status": "none"} if info.get("none") else {"status": "ok", **info}
                else:
                    fr24_want(cs, hx, 0)
                    body = {"status": "queued" if re.match(r"^[A-Z0-9]{3,8}$", cs) else "none"}
            return self.reply(200, "application/json", json.dumps(body).encode())
        if path == "/times":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            arg = lambda k: (q.get(k) or [""])[0].strip().upper()[:12]
            body = vie_times(arg("fn"), arg("from"), arg("to")) if arg("fn") else {"status": "none"}
            return self.reply(200, "application/json", json.dumps(body).encode())
        if path == "/logbook":
            return self.reply(200, "application/json", json.dumps(logbook_json()).encode())
        if path == "/metar":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            ids = (re.search(r"ids=([A-Za-z]{4})", q) or [None, ""])[1].upper()
            if not ids:
                return self.reply(400, "text/plain", b"ids=XXXX (an ICAO airport code) is required")
            status, body = metar(ids)
            return self.reply(status if status != 204 else 200, "text/plain; charset=utf-8", body or b"")
        if path == "/status":
            return self.reply(200, "application/json", json.dumps(status_json()).encode())
        m = AIRCRAFT.match(path) or LEGACY.match(path)
        if m:
            lat, lon, nm = m.groups()[-3:]
            if abs(float(lat)) > 90 or abs(float(lon)) > 180 or not 1 <= int(nm) <= 50:
                return self.reply(400, "text/plain", b"Out of range")
            status, body, source, freshness = aircraft(lat, lon, nm)
            return self.reply(status, "application/json", body, {"X-Relay-Source": source, "X-Relay-Data": freshness, "X-Sightings-Rev": str(_rev)})
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
    p.add_argument("--fr24-key", help="Flightradar24 API key, for boards that use it (the test-api board); 'off' turns it off")
    p.add_argument("--fr24-budget", type=int, help=f"most Flightradar24 credits to spend a month (default {FR24_BUDGET:,})")
    p.add_argument("--source", help="use this position source instead of the public ones: a URL with {lat} {lon} {nm} placeholders, or a local receiver's aircraft.json")
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

    if ARGS.source:
        SOURCES[:] = [{"key": "custom", "name": re.sub(r"^https?://([^/]+).*$", r"\1", ARGS.source), "url": ARGS.source}]
        STATE.clear()
        STATE["custom"] = {"ok": 0, "fail": 0, "strikes": 0, "cooldown_until": 0.0, "last_status": None, "last_error": "", "last_ok": 0.0}
    threading.Thread(target=_saver, daemon=True).start()
    threading.Thread(target=_enricher, daemon=True).start()
    threading.Thread(target=_fr24_worker, daemon=True).start()
    with _data_lock:
        _ensure_day()
        _book()
        _fr24_data()
        _backfill_categories()

    server = ThreadingHTTPServer((ARGS.bind, ARGS.port), Handler)
    print(f"Overhead relay {RELAY_VERSION} running. Open the board at:")
    print(f"  http://localhost:{ARGS.port}")
    print(f"  http://{socket.gethostname()}:{ARGS.port}")
    ip = lan_address()
    if ip:
        print(f"  http://{ip}:{ARGS.port}")
    if fr24_key():
        print(f"Flightradar24 lookups are on for boards that use them (at most {_fr24_budget():,} credits a month).")
    print("Problems with the flight data sources are printed below. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
