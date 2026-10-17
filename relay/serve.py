#!/usr/bin/env python3
"""Fallblatt (the Overhead board) home relay.

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
All screens show the same list, and it survives restarts. The relay also keeps track of which screens are
using it and prints them coming and going; press Enter in its window for the current list, or open /screens. Airport weather (METAR) comes through
here too, because the weather service doesn't allow direct browser access either.

Standard library only: works with Python 3.8+ on Windows, macOS, Linux or in a container.
"""
import argparse
import base64
import collections
import csv
import datetime
import email.utils
import hashlib
import hmac
import heapq
import html
import http.cookies
import ipaddress
import io
import itertools
import json
import math
import os
import queue
import random
import re
import secrets
import shutil
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RELAY_VERSION = 34
BOARD_URL = "https://belstria.github.io/overhead-board/"
PAGE_TTL = 60               # check GitHub for a newer board at most once a minute
SOURCES = [
    {"key": "adsblol", "name": "adsb.lol", "url": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"},
    {"key": "adsbfi", "name": "adsb.fi", "url": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}"},
    {"key": "airplaneslive", "name": "airplanes.live", "url": "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}"},
]
ROUTESET = "https://api.adsb.lol/api/0/routeset"
USER_AGENT = "overhead-board home relay (github.com/Belstria/overhead-board)"
FRESH_S = 4      # the app polls every 5 s, boards every 10 s; within this window they all share one upstream request
SOURCE_GAP_S = 1.1  # at least this long between two calls to one source (relay 34: adsb.fi answers 429 to a second call within a second)
STALE_S = 120    # if every source fails, keep serving the last good answer this long
NUM = r"(-?\d{1,3}(?:\.\d{1,6})?)"
AIRCRAFT = re.compile(rf"^/aircraft/{NUM}/{NUM}/(\d{{1,3}})$")
LEGACY = re.compile(rf"^/(adsblol|airplaneslive)/{NUM}/{NUM}/(\d{{1,3}})$")
PAGE = re.compile(r"^/(?:([a-z0-9-]{1,40})/)?(?:index\.html)?$")   # "/" is the board, "/test/" the test version
BOARD_FILE = re.compile(r"^/(?:([a-z0-9-]{1,40})/)?([a-z0-9][a-z0-9._-]{0,60}\.(webmanifest|png|svg|ico|js|wav))$")  # the phone app's icons, its service worker
FILE_TYPES = {"webmanifest": "application/manifest+json", "png": "image/png", "svg": "image/svg+xml", "ico": "image/x-icon", "js": "text/javascript", "wav": "audio/wav"}
CONFIG_FILE = Path(__file__).with_name("overhead.json")   # your saved settings; stays on this computer
SAVED_KEYS = ("lat", "lon", "place", "home", "radius", "units", "sound", "port", "source", "fr24_key", "fr24_budget", "public_url", "allow_host")
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
RUNWAYS_CSV = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/runways.csv"
CITY_FIX = {"SAW": "Istanbul", "NCL": "Newcastle", "STN": "London", "LGW": "London", "LTN": "London", "BVA": "Paris",
            "CRL": "Brussels", "NYO": "Stockholm", "BGY": "Milan", "MXP": "Milan", "LIN": "Milan", "CIA": "Rome", "FCO": "Rome"}
ICAO_FOR = {"VIE": "LOWW", "BTS": "LZIB", "GRZ": "LOWG", "LNZ": "LOWL", "SZG": "LOWS", "INN": "LOWI", "KLU": "LOWK",
            "MUC": "EDDM", "FRA": "EDDF", "ZRH": "LSZH", "BUD": "LHBP", "PRG": "LKPR", "LHR": "EGLL", "AMS": "EHAM"}

ARGS = None
STARTED = time.time()
STATE = {s["key"]: {"ok": 0, "fail": 0, "strikes": 0, "cooldown_until": 0.0, "last_status": None,
                    "last_error": "", "last_ok": 0.0, "last_call": 0.0} for s in SOURCES}
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


def cached(key, ttl, load, fail_ttl=0):
    """`load()` at most every `ttl` seconds; with `fail_ttl`, a failure is remembered that long too (relay 33: while
    GitHub was unreachable every page load waited for it again)."""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < (ttl if 200 <= hit[1][0] < 300 else fail_ttl):
            return hit[1]
    result = load()
    with _lock:
        if 200 <= result[0] < 300:
            _cache[key] = (now, result)
        elif fail_ttl:
            _cache[key] = (now, result) if not hit or not 200 <= hit[1][0] < 300 else hit
            if hit and 200 <= hit[1][0] < 300:
                _fail_until[key] = now + fail_ttl
        if len(_cache) > 300:                       # forget what nobody asked for in two hours
            for k in [k for k, v in _cache.items() if now - v[0] > 7200]:
                del _cache[k]
    return result


_fail_until = {}             # key -> until when a failed refresh isn't tried again (the last good copy is used)


def cached_or_stale(key, ttl, load, fail_ttl=60):
    """Like cached(), but a failed refresh keeps handing out the last good answer for `fail_ttl` seconds before
    trying again, instead of trying (and waiting) on every request."""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and 200 <= hit[1][0] < 300 and (now - hit[0] < ttl or _fail_until.get(key, 0) > now):
            return hit[1]
        if hit and not 200 <= hit[1][0] < 300 and now - hit[0] < fail_ttl:
            return hit[1]
    return cached(key, 0, load, fail_ttl)


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
            wait = st["last_call"] + SOURCE_GAP_S - time.time()
            if wait > 0:                          # another place was just asked for; space the calls out
                time.sleep(wait)
            t0 = time.time()
            status, _, body, headers = fetch(src["url"].format(lat=lat, lon=lon, nm=nm))
            st["last_call"] = time.time()
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
                if len(_positions) > 40:          # places nobody watches any more (relay 33: it only ever grew)
                    for k in [k for k, v in _positions.items() if time.time() - v[0] > STALE_S]:
                        del _positions[k]
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


# ---------- sightings and lifetime logbooks: one "spot" per profile ----------
# The home spot (data/) is the relay's own place, shared by every screen at home. Since relay 19 each guest profile
# (friends and family, let in with a personal invite link) has a spot of its own in data/profiles/<id>/, around the
# location they set, so their planes never end up in the home logbook and the other way round.
_data_lock = threading.RLock()
_dirty = set()             # relay-wide files to write: "fr24", "profiles"
_enrich_q = queue.Queue()  # (spot, sighting id)
_route_cache = {}
_aircraft_cache = {}


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def board_day(t=None):
    return time.strftime("%Y-%m-%d", time.localtime((t or time.time()) - DAY_STARTS_H * 3600))


class Spot:
    """Today's sightings and the lifetime logbook of one place. `center()` says where it is (None: unknown) and
    `radius()` how far around it planes count; the home spot without a saved location records around the screen's
    own point, as before relay 19."""

    def __init__(self, folder, center, radius, legacy=False):
        self.dir, self.center, self.radius, self.legacy = folder, center, radius, legacy
        self.day = None
        self.entries = []       # today's sightings, newest first
        self.by_hex = {}        # hex -> its latest entry today
        self.logbook = None
        self.rev = 0
        self.dirty = set()
        self.last_body = None

    def ensure_day(self):
        d = board_day()
        if d != self.day:
            self.day = d
            self.entries = _load(self.dir / f"sightings-{d}.json", [])
            self.by_hex = {}
            for e in reversed(self.entries):
                self.by_hex[e.get("hex", "")] = e

    def book(self):
        if self.logbook is None:
            self.logbook = _load(self.dir / "logbook.json", None) or {"since": time.strftime("%Y-%m-%d"), "startedTs": time.time(),
                                                                       "sightings": 0, "types": {}, "airlines": {}, "regs": {},
                                                                       "gameV": GAME_V, "recordsV": 1, "trophiesV": 1}
            if self.logbook.get("gameV") != GAME_V:
                self.ensure_day()
                _rescore(self)
            if self.logbook.get("recordsV") != 1:
                self.ensure_day()
                _backfill_records(self)
            if self.logbook.get("trophiesV") != 1:
                self.ensure_day()
                _backfill_trophies(self)
        return self.logbook

    def changed(self, *what):
        self.rev += 1
        self.dirty.update(what)

    def files(self):
        """The files to write now (called by the saver, under the lock)."""
        todo, out = set(self.dirty), []
        self.dirty.clear()
        if "day" in todo and self.day:
            out.append((self.dir / f"sightings-{self.day}.json", json.dumps(self.entries, separators=(",", ":"))))
        if "book" in todo and self.logbook is not None:
            out.append((self.dir / "logbook.json", json.dumps(self.logbook, separators=(",", ":"))))
        return out

    def take(self, body, lat, lon, nm, place=None):
        """A screen of this spot got positions around (lat, lon): record them if they cover the spot. Since relay 33 a
        screen can say which of the profile's places it watches (`place`: (key, (lat, lon), radius km); a saved place
        or "live", a phone following its owner); without one it is the profile's own place, "home"."""
        key = place[0] if place else "home"
        if (body, key) == self.last_body:   # the same answer again (several screens, one upstream request)
            return
        self.last_body = (body, key)
        lat, lon = float(lat), float(lon)
        c, radius = (place[1], place[2]) if place else (self.center(), self.radius())
        if c is None:
            if not self.legacy:
                return
            c = (lat, lon)
        elif _dist_km(lat, lon, c[0], c[1]) + radius > int(nm) * 1.852 + 1:
            return                          # looking somewhere else: nothing to count for this spot
        data = json.loads(body)
        planes = data.get("ac", data.get("aircraft"))
        if isinstance(planes, list):
            self.record(planes, c[0], c[1], key, radius)


def _home_center():
    return (ARGS.lat, ARGS.lon) if ARGS.lat is not None and ARGS.lon is not None else None


HOME = Spot(DATA_DIR, _home_center, lambda: ARGS.radius or 15.0, legacy=True)
_guest_spots = {}


def all_spots():
    return [HOME, *_guest_spots.values()]


def _saver():
    """Write changed files every few seconds, atomically, so a crash never leaves half a file."""
    while True:
        time.sleep(4)
        with _data_lock:
            files = [f for sp in all_spots() for f in sp.files()]
            todo = set(_dirty)
            _dirty.clear()
            if "fr24" in todo and _fr24 is not None:
                files.append((FR24_FILE, json.dumps(_fr24, separators=(",", ":"))))
            if "profiles" in todo and _profiles is not None:
                files.append((PROFILES_FILE, json.dumps(_profiles, separators=(",", ":"))))
        for path, text in files:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
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
    if item.get("last"):
        item["prev"] = item["last"]          # the sighting before this one (relay 28: "back after 7 months")
    item["last"] = e["ts"]
    if name and not item.get("name"):
        item["name"] = name


# Lifetime records (relay 28): the closest, lowest and fastest pass and the farthest route, kept in the logbook as
# sightings come in; an older logbook counts them once from its saved days.
def _rec_entry(e, v):
    return {"v": v, "ts": e.get("ts"), "reg": e.get("reg") or "", "type": e.get("typeCode") or "", "callsign": e.get("callsign") or "",
            "flight": e.get("flightIata") or e.get("callsign") or "", "desc": e.get("aircraftType") or e.get("desc") or ""}


def note_records(book, e, center=None):
    r = book.setdefault("records", {})
    def better(k, v, lower):
        cur = r.get(k)
        if v is not None and (cur is None or (v < cur["v"] if lower else v > cur["v"])):
            r[k] = _rec_entry(e, v)
            return True
        return False
    hit = better("closest", e.get("minDist"), True)
    alt = e.get("altAtMin")
    if isinstance(alt, (int, float)) and alt >= 100:           # 0 and below: a glitch or the ground, not a pass
        hit |= better("lowest", alt, True)
    gs = e.get("maxSpeed")
    if isinstance(gs, (int, float)) and 0 < gs <= 750:         # faster than that is a bad reading
        hit |= better("fastest", gs, False)
    if center:
        far = None
        for k in ("from", "to"):
            p = e.get(k) or {}
            if p.get("lat") is not None and p.get("lon") is not None:
                d = _gc_km(center, (float(p["lat"]), float(p["lon"])))
                if far is None or d > far[0]:
                    far = (d, p)
        if far and better("farthest", round(far[0]), False):
            r["farthest"]["place"] = {"code": far[1].get("code") or "", "city": far[1].get("city") or ""}
            hit = True
    return hit


def _gc_km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 12742 * math.asin(min(1, math.sqrt(h)))


def _backfill_records(spot):
    b = spot.logbook
    b["records"] = {}
    c = spot.center() if spot.center else None
    for f in sorted(spot.dir.glob("sightings-*.json")):
        for e in (spot.entries if f.stem[len("sightings-"):] == spot.day else _load(f, [])):
            note_records(b, e, c)
    b["recordsV"] = 1
    spot.changed("book")


def _record(self, planes, lat, lon, key="home", radius=None):
    """Called with every fresh position update: log planes that enter the spotting radius. `key` is the place the
    screen watches; a plane already logged today from another of the profile's places (within the same pass) stays
    one sighting, so two devices never count it twice."""
    radius = radius or self.radius()
    now = time.time()
    try:
        lat, lon = float(lat), float(lon)
    except ValueError:
        return
    with _data_lock:
        self.ensure_day()
        changed = False
        for ac in planes:
            if not isinstance(ac, dict):
                continue
            la, lo, hx = ac.get("lat"), ac.get("lon"), str(ac.get("hex") or "").lower()
            if la is None or lo is None or not hx or ac.get("alt_baro") == "ground":
                continue
            d = _dist_km(lat, lon, la, lo)
            alt = ac.get("alt_baro") if isinstance(ac.get("alt_baro"), (int, float)) else ac.get("alt_geom")
            e = self.by_hex.get(hx)
            if e and now - e.get("lastSeen", 0) > SAME_PASS_S:
                e = None
            if e and (e.get("place") or "home") != key:
                e["lastSeen"] = now                 # the same pass, seen from another place: one sighting
                continue
            if e:
                e["lastSeen"] = now
                moved = False
                if d < e["minDist"] - 0.05:
                    e["minDist"], e["altAtMin"], changed = round(d, 2), alt, True
                    moved = True
                gs = ac.get("gs")
                if isinstance(gs, (int, float)) and gs > e.get("maxSpeed", 0) + 1:
                    e["maxSpeed"], changed = round(gs), True
                    moved = True
                if moved and note_records(self.book(), e):
                    self.changed("book")
                if moved:
                    trophy_pass(self.book(), e)
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
                if key != "home":
                    e["place"] = key
                w = watch_of(hx)
                if w:
                    e["watch"], e["watchOp"] = w
                if e["emergency"]:
                    event("warn", f"Emergency code {e['emergency']} from {cs or hx}, {d:.1f} km away")
                self.entries.insert(0, e)
                del self.entries[5000:]
                self.by_hex[hx] = e
                book = self.book()
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
                score(book, e, self.day)
                note_records(book, e)
                hrs = set(book.get("hours", []))
                if _hour(e) not in hrs:
                    book["hours"] = sorted(hrs | {_hour(e)})
                for k in trophy_check(book, e, self.entries):
                    event("info", f"Trophy won: {k}", echo=False)
                self.changed("book")
                _enrich_q.put((self, e["id"]))
                changed = True
                event("debug", f"Spotted {cs or hx} at {d:.1f} km", echo=False)
        if changed:
            self.changed("day")


Spot.record = _record


# ---------- the spotter's game (relay 24): every sighting gets a rarity tier and points ----------
# Common (grey), uncommon (green), rare (blue), very rare (purple, key "epic") and special (gold, key "legendary": the
# special planes). Since relay 26 the tier goes by how many of the type fly today (FLEET, the same table as the board's),
# not by how often it was seen here. Points go to the day and the logbook; collections are sets of types to complete.
TIER_POINTS = {"common": 1, "uncommon": 3, "rare": 10, "epic": 25, "legendary": 50}
TIERS = list(TIER_POINTS)
GAME_V = 2                  # the scoring rule; a logbook scored by an older one is scored again from its saved days
LEGENDARY_TYPES = {"A388", "B741", "B742", "B743", "B744", "B748", "B74S", "B74R", "A3ST", "A337", "A124", "A225", "AN22", "CONC"}
# Roughly how many of each type fly today (in service, worldwide, 2025; rounded).
FLEET = {t: int(n) for t, n in (p.split(":") for p in "A318:40 A319:1100 A320:4100 A321:1700 A19N:40 A20N:1900 A21N:1500 BCS1:80 BCS3:380 A306:200 A30B:5 A310:30 A332:500 A333:650 A338:10 A339:120 A342:5 A343:50 A345:10 A346:30 A359:600 A35K:90 B712:100 B732:50 B733:100 B734:80 B735:50 B736:40 B737:1000 B738:4500 B739:480 B37M:5 B38M:1400 B39M:150 B752:500 B753:50 B762:30 B763:600 B764:35 B772:300 B77L:280 B77W:800 B778:2 B779:5 B788:400 B789:800 B78X:120 E135:100 E145:300 E170:150 E75L:600 E75S:50 E190:400 E195:130 E290:60 E295:80 CRJ1:50 CRJ2:350 CRJ7:250 CRJ9:400 CRJX:60 F50:30 F70:20 F100:60 B461:10 B462:20 B463:15 RJ85:25 RJ1H:15 SU95:140 AJ27:150 C919:15 T204:15 IL76:120 AN12:40 AN26:100 MD11:50 MD82:40 MD83:40 MD87:10 MD90:20 DC10:15 B703:5 AT43:150 AT45:120 AT72:150 AT75:250 AT76:700 DH8A:60 DH8B:50 DH8C:80 DH8D:450 SF34:150 JS41:30 D328:50 J328:30 L410:300 DHC6:300 B190:400 C208:2500 PC12:1800 TBM7:300 TBM8:300 TBM9:600 BE20:1500 BE9L:1200 B350:1100 C510:300 C525:350 C25A:400 C25B:500 C25C:400 C560:600 C56X:700 C680:450 C68A:450 C700:100 C750:280 CL30:400 CL35:450 CL60:1000 GLEX:900 GL5T:150 GL7T:200 GLF4:450 GLF5:500 GLF6:450 G280:250 GA5C:50 GA6C:100 F2TH:450 F900:400 FA7X:330 FA8X:100 FA50:200 E35L:150 E50P:350 E55P:650 E545:50 E550:100 LJ35:300 LJ45:400 LJ60:250 LJ75:150 PC24:250 HDJT:250 H25B:500 SF50:500 EA50:200 BE40:300 PRM1:50 C150:5000 C152:7000 C172:25000 C182:10000 C206:3000 C210:4000 P28A:15000 P28R:3000 PA34:2000 PA46:1500 PA18:3000 SR20:2000 SR22:7000 DA40:2500 DA42:1500 DA62:300 BE36:5000 BE58:2000 M20P:2000 EC35:900 EC45:1600 EC30:900 EC55:200 EC75:250 AS50:4000 AS55:400 AS65:700 AS32:200 A109:1000 A119:250 A139:1200 A169:200 A189:100 H160:40 B06:3000 B407:1500 B429:400 R22:3500 R44:6000 R66:1200 S76:300 S92:300 NH90:500".split())}
SETS = [
    ["Airbus narrowbodies", ["A318", "A319", "A320", "A321", "A19N", "A20N", "A21N", "BCS1", "BCS3"]],
    ["Airbus widebodies", ["A332", "A333", "A338", "A339", "A343", "A346", "A359", "A35K", "A388"]],
    ["Boeing narrowbodies", ["B736", "B737", "B738", "B739", "B37M", "B38M", "B39M", "B752", "B753"]],
    ["Boeing widebodies", ["B762", "B763", "B764", "B772", "B77L", "B77W", "B788", "B789", "B78X", "B744", "B748"]],
    ["Regional jets", ["E170", "E175", "E75L", "E190", "E195", "E290", "E295", "CRJ7", "CRJ9", "CRJX"]],
    ["Turboprops", ["AT43", "AT45", "AT72", "AT75", "AT76", "DH8A", "DH8C", "DH8D", "SF34", "JS41"]],
    ["Giants", ["A388", "B744", "B748", "A3ST", "A337", "A124", "A225", "C17", "C5M", "A400"]],
    ["Helicopters", ["EC35", "EC45", "EC30", "EC55", "EC75", "AS50", "AS65", "A139", "A169", "H160", "B06", "B407", "R44", "S76", "NH90"]],
    ["Business jets", ["C25A", "C25B", "C560", "C56X", "C680", "C68A", "C750", "CL35", "CL60", "GLF5", "GLF6", "GLEX", "F2TH", "FA7X", "E55P", "LJ45", "PC24"]],
]


def tier_of(book, e):
    t = e.get("typeCode") or ""
    if e.get("emergency") or e.get("military") or e.get("interesting") or t in LEGENDARY_TYPES or t in MILITARY_TYPES:
        return "legendary"
    n = FLEET.get(t)
    if n is None:
        return "uncommon"
    return "common" if n >= 1000 else "uncommon" if n >= 250 else "rare" if n >= 50 else "epic"


def score(book, e, day):
    """Give a new sighting its tier and add its points to the day and the logbook."""
    tier = tier_of(book, e)
    e["tier"] = tier
    pts = TIER_POINTS[tier]
    book["points"] = book.get("points", 0) + pts
    days = book.setdefault("days", {})
    days[day] = days.get(day, 0) + pts
    for k in sorted(days)[:-400]:
        del days[k]
    tiers = book.setdefault("tiers", {})
    tiers[tier] = tiers.get(tier, 0) + 1
    if TIERS.index(tier) >= TIERS.index("rare"):
        rd = book.setdefault("rareDays", [])
        if day not in rd:
            rd.append(day)
            del rd[:-400]


def _rescore(spot):
    """Score a logbook again from its saved days under today's rule (GAME_V): points, days, tiers and each sighting's tier."""
    b = spot.logbook
    for k in ("points", "days", "tiers", "rareDays"):
        b.pop(k, None)
    n = 0
    for f in sorted(spot.dir.glob("sightings-*.json")):
        day = f.stem[len("sightings-"):]
        today = day == spot.day
        entries = spot.entries if today else _load(f, [])
        for e in reversed(entries):                        # oldest first, as they were recorded
            score(b, e, day)
            n += 1
        if today:
            spot.changed("day")
        else:
            try:
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(entries, separators=(",", ":")), encoding="utf-8")
                os.replace(tmp, f)
            except OSError as e:
                event("warn", f"Couldn't save {f.name}: {e}")
    b["gameV"] = GAME_V
    spot.changed("book")
    if n:
        event("info", f"Logbook scored again by fleet size: {n} sightings")


def _streak(book, day):
    rd, streak = set(book.get("rareDays", [])), 0
    d = datetime.date.fromisoformat(day)
    if day not in rd:
        d -= datetime.timedelta(days=1)                       # today doesn't break the streak until it's over
    while d.isoformat() in rd:
        streak += 1
        d -= datetime.timedelta(days=1)
    return streak


# Trophies (relay 29): won once and kept for good (nothing resets), each with the day it was won.
TROPHY_IDS = ["century", "thousand", "busyday", "types50", "airlines25", "a320fam", "giants", "jumbochopper", "oldfriend",
              "nightowl", "aroundclock", "lowpass", "bullseye", "specialday", "streak7", "bingo", "fullcard"]
A320_FAMILY = ("A319", "A320", "A321")


def _hour(e):
    return time.localtime((e.get("ts") or 0) / 1000).tm_hour


def trophy_check(book, e, day_entries, ctx=None):
    """Win what this sighting (and its day so far) earns. ctx: the counts up to this sighting; by default the logbook's
    own (live), or ones rebuilt day by day when an older logbook is counted again."""
    got = book.setdefault("trophies", {})
    ts = e.get("ts") or int(time.time() * 1000)
    won = []
    def win(k, ok):
        if ok and k not in got:
            got[k] = ts
            won.append(k)
    c = ctx or {"n": book.get("sightings", 0), "types": book.get("types", {}), "airlines": book.get("airlines", {}),
                "regs": book.get("regs", {}), "hours": set(book.get("hours", []))}
    types = c["types"]
    win("century", c["n"] >= 100)
    win("thousand", c["n"] >= 1000)
    win("busyday", len(day_entries) >= 100)
    win("types50", len(types) >= 50)
    win("airlines25", len(c["airlines"]) >= 25)
    win("a320fam", all(t in types for t in A320_FAMILY) and any(t in types for t in ("A20N", "A21N", "A19N")))
    win("giants", "A388" in types and any(t.startswith("B74") for t in types))
    r = c["regs"].get(e.get("reg") or "")
    win("oldfriend", bool(r) and (r.get("count", 0) if isinstance(r, dict) else r) >= 25)
    win("jumbochopper", any(str(x.get("typeCode") or "").startswith("B74") for x in day_entries)
        and any(category_of(x) == "helicopter" for x in day_entries))
    win("nightowl", 1 <= _hour(e) <= 3)
    win("aroundclock", len(c["hours"]) >= 24)
    win("specialday", sum(1 for x in day_entries if x.get("tier") == "legendary") >= 3)
    trophy_pass(book, e, got, won)
    return won


def trophy_pass(book, e, got=None, won=None):
    """The trophies of how close or low a pass came (they can still be won as the plane comes closer)."""
    got = got if got is not None else book.setdefault("trophies", {})
    ts = e.get("ts") or int(time.time() * 1000)
    alt, d = e.get("altAtMin"), e.get("minDist")
    for k, ok in (("lowpass", isinstance(alt, (int, float)) and 100 <= alt < 1500 and d is not None and d <= 2),
                  ("bullseye", d is not None and d <= 0.3)):
        if ok and k not in got:
            got[k] = ts
            if won is not None:
                won.append(k)


def _backfill_trophies(spot):
    """An older logbook: win its trophies once from the saved days, on the day they were earned."""
    b = spot.logbook
    b["trophies"], hours = {}, set()
    ctx = {"n": 0, "types": {}, "airlines": {}, "regs": collections.Counter(), "hours": hours}
    for f in sorted(spot.dir.glob("sightings-*.json")):
        day = f.stem[len("sightings-"):]
        entries = spot.entries if day == spot.day else _load(f, [])
        so_far = []
        for e in reversed(entries):
            ctx["n"] += 1
            if e.get("typeCode"):
                ctx["types"][e["typeCode"]] = 1
            m = re.match(r"^([A-Z]{3})\d", e.get("callsign") or "")
            if m:
                ctx["airlines"][m.group(1)] = 1
            if e.get("reg"):
                ctx["regs"][e["reg"]] += 1
            hours.add(_hour(e))
            so_far.append(e)
            trophy_check(b, e, so_far, ctx)
    rd = sorted(b.get("rareDays", []))
    run = 0
    for i, d in enumerate(rd):
        run = run + 1 if i and datetime.date.fromisoformat(d) - datetime.date.fromisoformat(rd[i - 1]) == datetime.timedelta(days=1) else 1
        if run >= 7 and "streak7" not in b["trophies"]:
            b["trophies"]["streak7"] = int(datetime.datetime.fromisoformat(d + "T20:00").timestamp() * 1000)
    b["hours"] = sorted(hours)
    b["trophiesV"] = 1
    spot.changed("book")


# The weekly bingo: nine things to see between Monday and Sunday, drawn afresh each week (the same card on every
# screen of a spot); a line of three wins the Bingo trophy, all nine the Full card.
LH_GROUP, GULF, LOW_COST = {"DLH", "AUA", "SWR", "EWG", "BEL", "CLH"}, {"UAE", "QTR", "ETD"}, {"RYR", "WZZ", "EZY", "EJU", "VLG", "PGT"}
def _al(e):
    m = re.match(r"^([A-Z]{3})\d", str(e.get("callsign") or ""))
    return m.group(1) if m else ""
def _tc(e):
    return str(e.get("typeCode") or "").upper()
BINGO = {
    "heli": lambda e: category_of(e) == "helicopter",
    "a380": lambda e: _tc(e) == "A388",
    "b747": lambda e: _tc(e).startswith("B74"),
    "b777": lambda e: _tc(e).startswith("B77"),
    "b787": lambda e: _tc(e).startswith("B78"),
    "a350": lambda e: _tc(e).startswith("A35"),
    "a330": lambda e: _tc(e).startswith("A33"),
    "embraer": lambda e: re.match(r"^E(1[79]|2[9]|75)", _tc(e)) is not None,
    "turboprop": lambda e: re.match(r"^(AT[47]|DH8|SF34|JS41|D328|L410|B190|C208|PC12)", _tc(e)) is not None,
    "cargo": lambda e: category_of(e) == "cargo",
    "bizjet": lambda e: category_of(e) == "bizjet",
    "private": lambda e: category_of(e) == "private",
    "military": lambda e: category_of(e) == "military",
    "watch": lambda e: bool(e.get("watch")),
    "low": lambda e: isinstance(e.get("altAtMin"), (int, float)) and 100 <= e["altAtMin"] < 2500,
    "close": lambda e: e.get("minDist") is not None and e["minDist"] <= 1,
    "rare": lambda e: e.get("tier") in ("rare", "epic", "legendary"),
    "night": lambda e: _hour(e) >= 23 or _hour(e) <= 4,
    "early": lambda e: 5 <= _hour(e) <= 7,
    "newtype": lambda e: bool(e.get("newType")),
    "lhgroup": lambda e: _al(e) in LH_GROUP,
    "gulf": lambda e: _al(e) in GULF,
    "lowcost": lambda e: _al(e) in LOW_COST,
    "turkish": lambda e: _al(e) == "THY",
    "fast": lambda e: isinstance(e.get("maxSpeed"), (int, float)) and 520 <= e["maxSpeed"] <= 750,
}
BINGO_LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def bingo_json(spot, day):
    """This week's card: its nine goals, which are done (and when), and how many lines are complete."""
    monday = datetime.date.fromisoformat(day) - datetime.timedelta(days=datetime.date.fromisoformat(day).weekday())
    key = (monday.isoformat(), day, spot.rev)
    cached = getattr(spot, "_bingo", None)
    if cached and cached[0] == key:
        return cached[1]
    card = random.Random("fallblatt-" + monday.isoformat()).sample(sorted(BINGO), 9)
    done = {}
    for i in range(7):
        d = (monday + datetime.timedelta(days=i)).isoformat()
        if d > day:
            break
        entries = spot.entries if d == spot.day else _load(spot.dir / f"sightings-{d}.json", [])
        for e in reversed(entries):
            for g in card:
                if g not in done:
                    try:
                        if BINGO[g](e):
                            done[g] = e.get("ts")
                    except Exception:
                        pass
    lines = sum(1 for ln in BINGO_LINES if all(card[i] in done for i in ln))
    book = spot.book()
    got = book.setdefault("trophies", {})
    now = int(time.time() * 1000)
    for k, ok in (("bingo", lines >= 1), ("fullcard", len(done) == 9)):
        if ok and k not in got:
            got[k] = now
            spot.changed("book")
    out = {"week": monday.isoformat(), "card": card, "done": done, "lines": lines}
    spot._bingo = (key, out)
    return out


def game_json(book, day):
    days = book.get("days", {})
    best = max(days.items(), key=lambda kv: kv[1]) if days else None
    streak = _streak(book, day)
    have = book.get("types", {})
    return {"points": book.get("points", 0), "today": days.get(day, 0), "best": {"day": best[0], "points": best[1]} if best else None,
            "streak": streak, "tiers": {t: book.get("tiers", {}).get(t, 0) for t in TIERS},
            "sets": [{"name": n, "have": [t for t in ts if t in have], "total": len(ts)} for n, ts in SETS],
            "trophies": book.get("trophies", {})}


# ---------- the watchlist (relay 29): plane-alert-db, about 17,000 aircraft worth a look (police, air ambulances,
# governments, historic planes ...), keyed by Mode S address. A free list (ODbL 1.0 / DbCL 1.0, credited in the
# README), downloaded once a day; its playful categories become plain remark words for the board.
PLANE_ALERT_CSV = "https://raw.githubusercontent.com/sdr-enthusiasts/plane-alert-db/main/plane-alert-db.csv"
PLANE_ALERT_FILE = DATA_DIR / "plane-alert.json"
WATCH_WORDS = {
    "MILITARY": ["USAF", "Other Air Forces", "Toy Soldiers", "United States Navy", "GAF", "United States Marine Corps", "RAF",
                 "Other Navies", "Special Forces", "Army Air Corps", "Royal Navy Fleet Air Arm", "Gunship", "Zoomies", "UAV",
                 "Oxcart", "Hired Gun", "CAP"],
    "POLICE": ["Police Forces", "UK National Police Air Service"],
    "AMBULANCE": ["Flying Doctors"],
    "RESCUE": ["Coastguard"],
    "FIREFIGHTER": ["Aerial Firefighter", "Fire Fighting"],
    "GOVERNMENT": ["Governments", "Quango", "Dictator Alert", "Head of State"],
    "ROYAL": ["Royal Aircraft"],
    "HISTORIC": ["Historic"],
    "CELEBRITY": ["As Seen on TV", "Football", "Radiohead", "Don't you know who I am?"],
    "VIP": ["Oligarch", "Jesus he Knows me", "Vanity Plate", "PIA", "Climate Crisis", "Bizjets"],
    "SKYDIVING": ["Jump Johnny Jump", "Perfectly Serviceable Aircraft"],
    "AEROBATIC": ["Aerobatic Teams", "Joe Cool"],
    "SURVEY": ["Ptolemy would be proud", "Dogs with Jobs", "Watch Me Fly"],
    "UNUSUAL": ["Distinctive", "You came here in that thing?", "Big Hello", "Gas Bags", "Ukraine", "Da Comrade", "Nuclear"],
}
WATCH_OF_CAT = {c: w for w, cats in WATCH_WORDS.items() for c in cats}
_watch = {"rows": None, "fetched": 0.0}
_watch_lock = threading.Lock()


def _watch_load():
    db = _load(PLANE_ALERT_FILE, None)
    if db and time.time() - db.get("fetched", 0) < 86400:
        _watch.update(rows=db["rows"], fetched=db["fetched"])
        return
    status, _, body, _ = fetch(PLANE_ALERT_CSV, timeout=60)
    if status != 200:
        _watch.update(rows=(db or {}).get("rows") or _watch["rows"] or {}, fetched=time.time() - 86400 + 3600)   # try again in an hour
        event("warn", "Couldn't download the watchlist (plane-alert-db); trying again later", echo=False)
        return
    rows = {}
    for r in csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))):
        hx = (r.get("$ICAO") or "").strip().lower()
        w = WATCH_OF_CAT.get((r.get("Category") or "").strip())
        if re.fullmatch(r"[0-9a-f]{6}", hx) and w:
            rows[hx] = [w, (r.get("$Operator") or "").strip()[:60]]
    _watch.update(rows=rows, fetched=time.time())
    try:
        DATA_DIR.mkdir(exist_ok=True)
        PLANE_ALERT_FILE.write_text(json.dumps({"fetched": _watch["fetched"], "rows": rows}, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass
    event("info", f"Watchlist ready: {len(rows):,} aircraft (plane-alert-db)")


def watch_of(hx):
    """[remark word, operator] for an aircraft on the watchlist, or None. Loads (or refreshes) the list in the
    background; until it is there, nothing is on it."""
    if (_watch["rows"] is None or time.time() - _watch["fetched"] > 86400) and _watch_lock.acquire(blocking=False):
        def load():
            try:
                _watch_load()
            except Exception as e:
                event("warn", f"Watchlist: {e}", echo=False)
            finally:
                _watch_lock.release()
        threading.Thread(target=load, daemon=True).start()
    return (_watch["rows"] or {}).get(str(hx or "").lower())


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


def _backfill_categories(spot):
    """Older logbooks have no categories: count them once from the saved days."""
    b = spot.book()
    if "categories" in b:
        return
    cats = {}
    for f in sorted(spot.dir.glob("sightings-*.json")):
        for e in _load(f, []):
            c = category_of(e)
            cats[c] = cats.get(c, 0) + 1
    b["categories"] = cats
    spot.changed("book")
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
        spot, eid = _enrich_q.get()
        with _data_lock:
            e = next((x for x in spot.entries if x.get("id") == eid), None)
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
        w = watch_of(hx) if hx else None
        with _data_lock:
            if w and not e.get("watch"):              # the watchlist may have arrived after the sighting
                e["watch"], e["watchOp"] = w
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
            book = spot.book()
            if route:
                note_records(book, e, spot.center() if spot.center else None)
            t = book["types"].get(e.get("typeCode") or "")
            if t is not None and not t.get("name") and info:
                t["name"] = " ".join(x for x in (info.get("manufacturer", "").split(" ")[0], info.get("aircraftType")) if x)
            m = re.match(r"^([A-Z]{3})\d", cs or "")
            a = book["airlines"].get(m.group(1)) if m else None
            if a is not None and route:
                a["name"] = a.get("name") or route.get("airlineName", "")
                a["iata"] = a.get("iata") or route.get("airlineIata", "")
            spot.changed("day", "book")
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
_airports = None             # {"iata": {code: [city, lat, lon, icao, name, scheduled]}, "icao": {icao: iata}}
_airports_lock = threading.Lock()


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


def fr24_paced(priority):
    """Spread the monthly budget over the month: each day may spend its share of what is left (unspent credits carry
    over). Past the share, only the plane on the board is still looked up; past one and a half shares, nothing until
    tomorrow. Boards show the free sources' answer meanwhile."""
    with _data_lock:
        u = _fr24_usage()
        today = u.get("creditsToday", 0)
        left = _fr24_budget() - (u.get("credits", 0) - today)
    now = datetime.date.today()
    nxt = (now.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    share = max(0, left) / max(1, (nxt - now).days)
    return today >= share * (1.5 if priority == 0 else 1.0)


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
    if not fr24_on() or not cs or not hx or not re.match(r"^[A-Z0-9]{3,8}$", cs) or fr24_info(cs, hx) or fr24_paced(priority):
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
    if db and db.get("v") == 3 and time.time() - db.get("fetched", 0) < 60 * 86400:
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
            try:
                elev = int(float(r.get("elevation_ft") or 0))
            except ValueError:
                elev = 0
            iata[code] = [city, lat, lon, ic, (r.get("name") or "").strip(), 1 if r.get("scheduled_service") == "yes" else 0, elev]
        if ic:
            icao[ic] = code
    _airports = {"v": 3, "fetched": time.time(), "iata": iata, "icao": icao}
    try:
        DATA_DIR.mkdir(exist_ok=True)
        AIRPORTS_FILE.write_text(json.dumps(_airports, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass
    event("info", f"Airport list ready: {len(iata)} airports")


def _airports_ready():
    """The airport list, loading it in the background the first time; None while it loads."""
    if _airports is not None:
        return _airports
    if _airports_lock.acquire(blocking=False):
        def load():
            try:
                _load_airports()
            finally:
                _airports_lock.release()
        threading.Thread(target=load, daemon=True).start()
    return None


def airports_near(lat, lon, n=3):
    """The airports with scheduled flights nearest to a spot (for Settings → Use current location)."""
    db = _airports_ready()
    if db is None:
        return {"status": "loading"}
    rows = [(code, r) for code, r in (db.get("iata") or {}).items() if len(r) > 5 and r[5]]
    def km(r):
        p1, p2 = math.radians(lat), math.radians(r[1])
        a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(r[2] - lon) / 2) ** 2
        return 12742 * math.asin(math.sqrt(a))
    best = heapq.nsmallest(n, ((km(r), code, r) for code, r in rows))
    return {"status": "ok", "airports": [{"code": code, "icao": r[3], "name": r[4], "city": r[0], "km": round(d, 1)} for d, code, r in best]}


_runways = {}                # ICAO -> [[ident, lat, lon, ident, lat, lon], ...] (hard-surfaced, open), fetched on demand


def runways_of(icao):
    """An airport's runways, ends with their position, from OurAirports (cached in data/runways-<icao>.json)."""
    icao = (icao or "").upper()
    if not icao:
        return []
    if icao in _runways:
        return _runways[icao]
    f = DATA_DIR / f"runways-{re.sub(r'[^A-Z0-9]', '', icao)}.json"
    cached = _load(f, None)
    if cached is not None:
        _runways[icao] = cached
        return cached
    status, _, body, _ = fetch(RUNWAYS_CSV, timeout=60)
    if status != 200:
        return []
    out = []
    for r in csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))):
        if (r.get("airport_ident") or "").upper() != icao or r.get("closed") == "1":
            continue
        try:
            ends = [r["le_ident"], round(float(r["le_latitude_deg"]), 5), round(float(r["le_longitude_deg"]), 5),
                    r["he_ident"], round(float(r["he_latitude_deg"]), 5), round(float(r["he_longitude_deg"]), 5)]
        except (KeyError, ValueError):
            continue
        if not re.match(r"^(ASP|CON|ASPH|CONC|PEM|BIT)", (r.get("surface") or "").upper()) and r.get("lighted") != "1":
            continue
        out.append(ends)
    _runways[icao] = out
    try:
        DATA_DIR.mkdir(exist_ok=True)
        f.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        pass
    return out


def airport_info(code):
    """One airport by its IATA code, for the board's airport mode: its position and (relay 23+) its runways."""
    db = _airports_ready()
    if db is None:
        return {"status": "loading"}
    r = (db.get("iata") or {}).get(code.upper())
    if not r:
        return {"status": "none"}
    return {"status": "ok", "code": code.upper(), "icao": r[3], "name": r[4] if len(r) > 4 else "", "city": r[0], "lat": r[1], "lon": r[2],
            "runways": runways_of(r[3])}


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
            priority, _, key, cs, hx = heapq.heappop(_fr24_q)
        try:
            if not fr24_on() or fr24_info(cs, hx):
                continue
            if fr24_paced(priority):
                if _fr24_state["state"] not in ("paced", "budget"):
                    event("info", "Flightradar24: today's share of the monthly budget is used; more lookups tomorrow")
                    _fr24_state.update(state="paced")
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
                    if not info.get("none"):
                        usage["found"] = usage.get("found", 0) + 1
                        if info.get("divertedTo"):
                            usage["diverted"] = usage.get("diverted", 0) + 1
                        if info.get("livery") and info.get("operator") and info["livery"] != info["operator"]:
                            usage["wetLease"] = usage.get("wetLease", 0) + 1
                _dirty.add("fr24")
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
                if _fr24_state["state"] not in ("ok", "paced"):
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
    state = _fr24_state["state"] if _fr24_state["state"] != "off" else "ready"
    if state == "paced" and not fr24_paced(1):     # a new day
        state = _fr24_state["state"] = "ok"
    if u.get("credits", 0) >= _fr24_budget():
        state = "budget"
    return {"state": state, "error": _fr24_state["error"],
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
            "points": sum(TIER_POINTS.get(e.get("tier"), 0) for e in entries),
            "newAirlines": sum(1 for e in entries if e.get("newAirline")),
            "dayStarts": f"{DAY_STARTS_H:02d}:00"}


def sightings_json(spot, api=False, over_km=3.0, everything_wanted=False, place=None):
    """Today's sightings; with `place`, only those seen from that place (a screen's Spotted today, relay 33)."""
    with _data_lock:
        spot.ensure_day()
        everything = [e for e in spot.entries if place is None or (e.get("place") or "home") == place]
        day, rev = spot.day, spot.rev
    if api:
        everything = fr24_overlay(everything)
    return {"version": RELAY_VERSION, "date": day, "rev": rev, "entries": everything if everything_wanted else everything[:400],
            "stats": day_stats(everything, over_km)}


def logbook_json(spot):
    with _data_lock:
        b = spot.book()
        regs = b.get("regs", {})
        top = sorted(regs.items(), key=lambda kv: -kv[1].get("count", 0))[:15]
        return {"version": RELAY_VERSION, "since": b.get("since"), "sightings": b.get("sightings", 0),
                "learningUntil": int((b.get("startedTs", 0) + LEARN_S) * 1000), "categories": b.get("categories", {}),
                "types": b.get("types", {}), "airlines": b.get("airlines", {}), "regsCount": len(regs),
                "regsTop": [{"reg": k, **v} for k, v in top],
                "regsRecent": [{"reg": k, **v} for k, v in sorted(regs.items(), key=lambda kv: -kv[1].get("first", 0))[:15]],
                "game": {**game_json(b, spot.day or board_day()), "bingo": bingo_json(spot, spot.day or board_day())},
                "records": b.get("records", {})}


def _days_of(spot, prefix=""):
    """(day, entries) for each saved day of a spot, oldest first, today's from memory."""
    for f in sorted(spot.dir.glob(f"sightings-{prefix}*.json")):
        day = f.stem[len("sightings-"):]
        yield day, (spot.entries if day == spot.day else _load(f, []))


def year_json(spot, year):
    """A year in planes (relay 29), for the phone app's year card: totals, the busiest day, the most seen airframe,
    the rarest plane, the year's records and its points."""
    key = (year, spot.rev)
    cached = getattr(spot, "_year", None)
    if cached and cached[0] == key:
        return cached[1]
    n, types, airlines, countries, regs, days, pts = 0, set(), set(), set(), collections.Counter(), {}, 0
    rec, rarest = {}, None
    order = {t: i for i, t in enumerate(TIERS)}
    with _data_lock:
        for day, entries in _days_of(spot, f"{year}-"):
            days[day] = len(entries)
            for e in entries:
                n += 1
                pts += TIER_POINTS.get(e.get("tier"), 0)
                if e.get("typeCode"):
                    types.add(e["typeCode"])
                if _al(e):
                    airlines.add(_al(e))
                if e.get("ownerCountry"):
                    countries.add(e["ownerCountry"])
                if e.get("reg"):
                    regs[e["reg"]] += 1
                note_records(rec, e)
                k = (order.get(e.get("tier"), -1), -FLEET.get(_tc(e), 500))
                if rarest is None or k > rarest[0]:
                    rarest = (k, e)
    top = regs.most_common(1)
    busiest = max(days.items(), key=lambda kv: kv[1]) if days else None
    who = lambda e: {"reg": e.get("reg") or "", "type": e.get("aircraftType") or e.get("typeCode") or "", "callsign": e.get("callsign") or "",
                     "tier": e.get("tier") or "", "ts": e.get("ts")}
    out = {"year": year, "planes": n, "types": len(types), "airlines": len(airlines), "countries": len(countries),
           "airframes": len(regs), "days": len(days), "points": pts,
           "busiest": {"day": busiest[0], "planes": busiest[1]} if busiest else None,
           "mostSeen": {"reg": top[0][0], "count": top[0][1]} if top else None,
           "rarest": who(rarest[1]) if rarest else None, "records": rec.get("records", {})}
    spot._year = (key, out)
    return out


CSV_COLS = ["date", "time", "place", "callsign", "flight", "registration", "type", "aircraft", "airline", "from", "to",
            "closest_km", "altitude_ft", "max_speed_kt", "rarity", "category", "watchlist"]


def _csv_safe(v):
    """A text that a spreadsheet would run as a formula (=, +, -, @ first) gets an apostrophe in front."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def logbook_csv(spot):
    """Every saved sighting of a spot as a spreadsheet (relay 29), for moving the log into a spotting app."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    with _data_lock:
        for day, entries in _days_of(spot):
            for e in reversed(entries):
                p = lambda k: ((e.get(k) or {}).get("code") or "") if isinstance(e.get(k), dict) else ""
                w.writerow([_csv_safe(v) for v in [day, e.get("time") or "", e.get("place") or "home", e.get("callsign") or "", e.get("flightIata") or "", e.get("reg") or "",
                            e.get("typeCode") or "", e.get("aircraftType") or e.get("desc") or "", e.get("airlineName") or "",
                            p("from"), p("to"), e.get("minDist") if e.get("minDist") is not None else "",
                            e.get("altAtMin") if isinstance(e.get("altAtMin"), (int, float)) else "", e.get("maxSpeed") or "",
                            e.get("tier") or "", category_of(e), e.get("watch") or ""]])
    return buf.getvalue().encode("utf-8-sig")


def seen_json(spot, reg):
    """What the logbook knows of one airframe (relay 28): how often it was seen here, first, last and the one before."""
    with _data_lock:
        it = spot.book().get("regs", {}).get(reg)
        if not it:
            return {"reg": reg, "count": 0}
        return {"reg": reg, "count": it.get("count", 0), "first": it.get("first"), "last": it.get("last"), "prev": it.get("prev")}


def metar(ids):
    status, _, body, _ = cached("metar:" + ids, 600, lambda: fetch(
        f"https://aviationweather.gov/api/data/metar?ids={ids}&format=raw&taf=false", timeout=10))
    return status, body


def sky_json(code):
    """The home airport's weather for "above the cloud" (relay 28): the lowest broken or overcast layer, in feet
    above sea level (the METAR gives it above the airport, so the airport's elevation is added), and the visibility."""
    db = _airports_ready() or {}
    r = (db.get("iata") or {}).get(code.upper())
    if not r or not r[3]:
        return {"status": "none"}
    icao, elev = r[3], (r[6] if len(r) > 6 and r[6] is not None else 0)
    status, body = metar(icao)
    raw = (body or b"").decode("utf-8", "replace").strip().splitlines()
    raw = raw[0] if raw else ""
    if status != 200 or not raw:
        return {"status": "none", "icao": icao}
    ceiling, layers = None, []
    for cov, h in re.findall(r"\b(FEW|SCT|BKN|OVC|VV)(\d{3})", raw):
        ft = int(h) * 100 + int(elev)
        layers.append([cov, ft])
        if cov in ("BKN", "OVC", "VV") and (ceiling is None or ft < ceiling):
            ceiling = ft
    vis = 10000 if re.search(r"\bCAVOK\b", raw) else None
    m = re.search(r"\s(\d{4})(?:NDV)?\s", " " + raw + " ")
    if vis is None and m:
        vis = int(m.group(1))
    clear = ceiling is None and bool(re.search(r"\b(CAVOK|NSC|SKC|CLR|NCD)\b", raw) or not layers)
    return {"status": "ok", "icao": icao, "elevation": elev, "ceiling": ceiling, "layers": layers, "visibility": vis,
            "clear": clear, "raw": raw}


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


# ---------- screens: which boards are using the relay ----------
# Every board polls the relay every ten seconds or so, which is enough to tell which screens are open: by address and
# browser, and on the test boards (which send a session id and say hello every minute) by name, size and drawing quality.
# Screens coming and going are printed here and listed in the board's diagnostics; press Enter for the current list,
# or open /screens in a browser.
SCREEN_GONE_S = 60          # a screen that hasn't asked for anything for a minute has been closed or switched off
SCREEN_NEW_S = 6            # wait this long for a new screen's hello before announcing it with what we know
BOARD_PATHS = ("/aircraft/", "/adsblol/", "/airplaneslive/", "/sightings", "/logbook", "/metar", "/flightinfo", "/times",
               "/status", "/hello", "/routeset", "/bye")
_screens = {}
_screens_gone = collections.deque(maxlen=12)
_screens_lock = threading.Lock()
_hosts = {}                 # address -> network name (or None while looking it up / when there is none)


def device_of(ua):
    """A short, human description of the device and browser from its user agent."""
    u = ua or ""
    if not u:
        return "unknown device"
    if "OverheadAndroid/" in u:      # the Android app (android/ in the repository) tags its user agent
        return "Android phone · Fallblatt app"
    m = re.search(r"\bAFT[A-Z0-9]+", u)
    if m:
        return f"Fire TV ({m.group(0)})"
    m = re.search(r"Tizen[ /]?([\d.]+)?", u)
    if m and ("TV" in u or "SMART" in u):
        return f"Samsung TV (Tizen {m.group(1)})" if m.group(1) else "Samsung TV"
    if re.search(r"Web0S|webOS|NetCast", u):
        return "LG TV (webOS)"
    if "CrKey" in u:
        return "Chromecast"
    if re.search(r"Android TV|AndroidTV|GoogleTV|BRAVIA", u):
        return "Android TV"
    browser = ("headless Chrome" if "HeadlessChrome" in u else "Edge" if "Edg/" in u else "Opera" if "OPR/" in u
               else "Samsung Internet" if "SamsungBrowser" in u else "Firefox" if "Firefox/" in u
               else "Silk" if "Silk/" in u else "Chrome" if "Chrome/" in u or "CriOS" in u else "Safari" if "Safari/" in u else "")
    system = ("iPhone" if "iPhone" in u else "iPad" if "iPad" in u else "Android tablet" if "Android" in u and "Mobile" not in u
              else "Android phone" if "Android" in u else "Chromebook" if "CrOS" in u else "Windows PC" if "Windows" in u
              else "Mac" if "Macintosh" in u else "Linux PC" if "Linux" in u else "")
    return " · ".join(x for x in (system, browser) if x) or ua[:40]


def board_of(referer):
    """Which board a request came from: / is PROD, /test/ TEST, /test-api/ TEST-API."""
    if not referer:
        return None
    m = PAGE.match(urllib.parse.urlsplit(referer).path or "/")
    return (m.group(1) or "prod").upper() if m else None


def _lookup_host(ip):
    try:
        name = socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        name = None
    if name:
        name = name.split(".")[0] if not re.fullmatch(r"[\d.:]+", name) else None
    _hosts[ip] = name


def host_of(ip):
    if ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        return "this computer"
    if ip not in _hosts:
        _hosts[ip] = None
        threading.Thread(target=_lookup_host, args=(ip,), daemon=True).start()
    return _hosts.get(ip)


def fmt_for(seconds):
    m = int(seconds // 60)
    if m < 1:
        return "< 1 min"
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} h {m:02d} min"
    d, h = divmod(h, 24)
    return f"{d} d {h} h"


def screen_seen(ip, ua, referer, sid="", hello=None, bye=False):
    """Note a request from a board. Requests from the same browser and board without a session id count as one screen."""
    now = time.time()
    board = board_of(referer)
    sid = re.sub(r"[^a-z0-9]", "", (sid or "").lower())[:16]
    if not sid and not board:       # not from a board page (a check from a script, say)
        return
    key = sid or f"{ip}|{ua}|{board or ''}"
    with _screens_lock:
        s = _screens.get(key)
        if s is None:
            if bye:
                return
            s = {"key": key, "sid": sid, "ip": ip, "ua": ua, "device": device_of(ua), "board": board, "name": "",
                 "since": now, "first": now, "last": now, "requests": 0, "hello": None, "announced": False,
                 "reloads": 0, "pending": "new", "bye": 0.0}
            # The same browser opening the same board while its previous page has just said goodbye or gone quiet
            # is a reload: it keeps its time on.
            for k, o in list(_screens.items()):
                if o["ip"] == ip and o["ua"] == ua and o["board"] == board and o["sid"] and (o["bye"] or now - o["last"] > 15):
                    s.update(since=o["since"], reloads=o["reloads"] + 1, name=o["name"],
                             pending="reload" if o["announced"] else "new", announced=o["announced"])
                    del _screens[k]
                    break
            _screens[key] = s
        s["last"] = now
        s["requests"] += 1
        if board:
            s["board"] = board
        if bye:
            s["bye"] = now
        if hello is not None:
            s["hello"] = hello
            name = hello.get("name", "")
            if s["announced"] and name and s["name"] and name != s["name"]:
                event("info", f"Screen renamed: {s['name']} is now {name}")
            s["name"] = name
    host_of(ip)


def screen_info(s, now=None):
    now = now or time.time()
    h = s["hello"] or {}
    size = f"{h['w']}×{h['h']}" if h.get("w") and h.get("h") else ""
    quality = h.get("q", "")
    return {"sid": s["sid"], "name": s["name"], "device": s["device"], "ip": s["ip"], "host": _hosts.get(s["ip"]) or ("this computer" if s["ip"] in ("127.0.0.1", "::1") else ""),
            "board": s["board"] or "", "since": int(s["since"]), "on_s": int(now - s["since"]), "quiet_s": int(now - s["last"]),
            "reloads": s["reloads"], "requests": s["requests"], "size": size, "quality": quality,
            "hidden": h.get("vis") == "hidden", "ua": s["ua"][:200]}


def describe(i):
    """One line about a screen: its name, device, address, board and size."""
    who = i["name"] or i["device"]
    parts = [i["device"]] if i["name"] else []
    parts.append(i["ip"] + (f" ({i['host']})" if i["host"] else ""))
    if i["board"]:
        parts.append(f"{i['board']} board")
    if i["size"]:
        parts.append(i["size"] + (f", quality {i['quality']}" if i["quality"] else ""))
    return f"{who} — " + ", ".join(parts)


def screens_list():
    now = time.time()
    with _screens_lock:
        live = [screen_info(s, now) for s in _screens.values() if s["announced"] or now - s["first"] > SCREEN_NEW_S]
        gone = list(_screens_gone)
    live.sort(key=lambda i: i["since"])
    return live, gone


def _screen_watch():
    while True:
        time.sleep(3)
        now = time.time()
        say = []
        with _screens_lock:
            for k, s in list(_screens.items()):
                i = screen_info(s, now)
                if s["pending"] and (s["hello"] or now - s["first"] > SCREEN_NEW_S) and not s["bye"]:
                    if s["pending"] == "reload":
                        say.append(f"Screen reloaded the board: {describe(i)} (on for {fmt_for(i['on_s'])})")
                    else:
                        say.append(f"Screen connected: {describe(i)}")
                    s["pending"] = None
                    s["announced"] = True
                elif (s["bye"] and now - s["bye"] > 10) or now - s["last"] > SCREEN_GONE_S:
                    del _screens[k]
                    if s["announced"]:
                        on = s["last"] - s["since"]
                        say.append(f"Screen gone: {describe(i)}, after {fmt_for(on)}" + (" (closed)" if s["bye"] else ""))
                        _screens_gone.appendleft({**i, "on_s": int(on), "left": int(s["last"])})
        for msg in say:
            event("info", msg)


def print_screens():
    live, gone = screens_list()
    lines = [f"{time.strftime('%H:%M:%S')}  Screens using the relay: {len(live) or 'none'}"]
    for i in live:
        extra = []
        if i["reloads"]:
            extra.append(f"reloaded {i['reloads']}×")
        if i["hidden"]:
            extra.append("in the background")
        if i["quiet_s"] > 20:
            extra.append(f"quiet for {i['quiet_s']} s")
        lines.append(f"  · {describe(i)}; on for {fmt_for(i['on_s'])}" + (f" ({', '.join(extra)})" if extra else ""))
    if gone:
        lines.append("  Recently gone:")
        for i in gone[:5]:
            lines.append(f"  · {describe(i)}; left {time.strftime('%H:%M', time.localtime(i['left']))} after {fmt_for(i['on_s'])}")
    print("\n".join(lines), flush=True)


def _console():
    """Pressing Enter in the relay's window lists the screens. Without a console window this simply stops."""
    try:
        while sys.stdin.readline():
            print_screens()
    except (OSError, ValueError, EOFError, RuntimeError):
        pass


def screens_html():
    live, gone = screens_list()
    esc = html.escape

    def row(i, left=None):
        when = f"left {time.strftime('%H:%M', time.localtime(left))} after {fmt_for(i['on_s'])}" if left else f"on for {fmt_for(i['on_s'])}"
        notes = []
        if not left and i["reloads"]:
            notes.append(f"reloaded {i['reloads']}×")
        if not left and i["hidden"]:
            notes.append("in the background")
        if not left and i["quiet_s"] > 20:
            notes.append(f"quiet for {i['quiet_s']} s")
        return (f"<tr><td><b>{esc(i['name'] or '—')}</b></td><td>{esc(i['device'])}</td><td>{esc(i['ip'])}"
                f"{'<br><small>' + esc(i['host']) + '</small>' if i['host'] else ''}</td><td>{esc(i['board'] or '?')}</td>"
                f"<td>{esc(i['size'] or '')}{'<br><small>quality ' + esc(i['quality']) + '</small>' if i['quality'] else ''}</td>"
                f"<td>{esc(when)}{'<br><small>' + esc(', '.join(notes)) + '</small>' if notes else ''}</td>"
                f"<td><small title=\"{esc(i['ua'])}\">{esc(i['ua'][:70])}{'…' if len(i['ua']) > 70 else ''}</small></td></tr>")

    head = "<tr><th>Name</th><th>Device</th><th>Address</th><th>Board</th><th>Drawn at</th><th>Time</th><th>Browser</th></tr>"
    body = (f"<h1>Screens using the relay <span>{len(live)}</span></h1>"
            + (f"<table>{head}{''.join(row(i) for i in live)}</table>" if live else "<p>No screens right now.</p>")
            + (f"<h2>Recently gone</h2><table>{head}{''.join(row(i, i['left']) for i in gone)}</table>" if gone else "")
            + f"<p class=foot>Relay {RELAY_VERSION} · updated {time.strftime('%H:%M:%S')} · refreshes every 10 seconds. "
              "Test boards send their name (Settings → Screen name, or <code>?screen=Living%20room</code>), size and drawing quality; "
              "the live board is known by its address and browser.</p>")
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta http-equiv=refresh content=10><title>Screens · Fallblatt relay</title><style>"
            ":root{color-scheme:dark}body{margin:0;padding:24px 16px;background:#141414;color:#e8e4da;font:15px/1.45 system-ui,sans-serif}"
            "h1{font-size:22px;font-weight:600;margin:0 0 16px}h1 span{color:#f0b03c}h2{font-size:16px;margin:28px 0 10px;color:#aaa}"
            "table{border-collapse:collapse;width:100%;max-width:1200px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #2b2b2b;vertical-align:top}"
            "td:nth-child(n+3):nth-child(-n+6){white-space:nowrap}th{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#f0b03c;font-weight:600}small{color:#8d887d}"
            ".foot{color:#8d887d;font-size:13px;margin-top:24px;max-width:1200px}code{color:#e8e4da}"
            "@media(max-width:760px){table,tbody,tr,td{display:block}th{display:none}tr{padding:8px 0;border-bottom:1px solid #2b2b2b}td{border:0;padding:2px 0}}"
            "</style>" + body)


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
    live, _ = screens_list()
    return {"version": RELAY_VERSION, "uptime_s": int(now - STARTED), "sources": sources, "events": events, "fr24": fr24_status(),
            "vie": vie_status(), "screens": live}


_board_seen = {}
_board_date = {}             # when each board was published (GitHub's Last-Modified), in ms since 1970


def board_file(sub, name, ext):
    """An icon or the web app manifest next to a board (the phone app needs them to go on the home screen)."""
    rel = (sub + "/" if sub else "") + name
    if ARGS.local_root:
        f = Path(ARGS.local_root) / rel
        return (200, f.read_bytes()) if f.is_file() else (404, b"Not found")
    copy = DATA_DIR / "board-files" / rel.replace("/", "--")
    status, _, body, _ = cached_or_stale("file:" + rel, PAGE_TTL * 10, lambda: fetch(f"{BOARD_URL}{rel}?v={int(time.time()) // 600}", timeout=15))
    if status == 200:
        try:
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(body)
        except OSError:
            pass
        return 200, body
    if copy.exists():
        return 200, copy.read_bytes()
    return (404 if status == 404 else 502), b"Not found"


def board_html(sub="", guest=None):
    """The board (or the phone app) with what it needs to know injected: the home location for screens at home, a
    guest's name, id and saved settings for a guest (`guest` is (id, profile))."""
    gid, guest = guest if guest else (None, None)
    copy = Path(__file__).with_name(f"board-cache{'-' + sub if sub else ''}.html")
    if ARGS.local_root:
        f = Path(ARGS.local_root) / sub / "index.html" if sub else Path(ARGS.local_root) / "index.html"
        if not f.is_file():
            return None
        html = f.read_text(encoding="utf-8")
        _board_date[sub] = int(f.stat().st_mtime * 1000)
    elif ARGS.local and not sub:
        html = Path(ARGS.local).read_text(encoding="utf-8")
        _board_date[sub] = int(Path(ARGS.local).stat().st_mtime * 1000)
    else:
        url = BOARD_URL + (sub + "/" if sub else "")
        # GitHub's servers keep a page for up to ten minutes; asking for a fresh address each time skips that wait.
        status, _, body, headers = cached_or_stale("page:" + sub, PAGE_TTL, lambda: fetch(f"{url}?v={int(time.time())}", timeout=15))
        if status == 200:
            html = body.decode("utf-8")
            try:
                _board_date[sub] = int(email.utils.parsedate_to_datetime(headers.get("Last-Modified")).timestamp() * 1000)
            except (AttributeError, TypeError, ValueError):
                pass
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
            _board_date.setdefault(sub, int(copy.stat().st_mtime * 1000))
        else:
            return None
    defaults = {k: v for k, v in {
        "lat": ARGS.lat, "lon": ARGS.lon, "place": ARGS.place,
        "home": ARGS.home, "radiusKm": ARGS.radius, "units": ARGS.units,
    }.items() if v is not None}
    if ARGS.sound is not None:
        defaults["sound"] = bool(ARGS.sound)
    fr24 = fr24_on() and (guest is None or bool(guest.get("fr24")))
    if guest is not None:               # a guest never gets the home location; their own settings come with their profile
        defaults = {"units": ARGS.units} if ARGS.units else {}
    config = json.dumps(defaults).replace("<", "\\u003c")
    who = json.dumps({"id": gid, "name": guest["name"], "settings": guest.get("settings")}).replace("<", "\\u003c") if guest is not None else "null"
    inject = (f"<script>window.OVERHEAD_RELAY=location.origin;window.OVERHEAD_RELAY_VERSION={RELAY_VERSION};"
              f"window.OVERHEAD_DEFAULTS={config};window.OVERHEAD_FR24={'true' if fr24 else 'false'};"
              f"window.OVERHEAD_GUEST={who};window.OVERHEAD_PAGE_DATE={_board_date.get(sub) or 'null'};</script>")
    return html.replace("<head>", "<head>\n" + inject, 1)


# ---------- friends and family: profiles, personal invite links and the admin page (relay 19) ----------
# Screens at home (a direct connection from a private address) are the home profile, as always. Everyone else, which
# through the Cloudflare tunnel is everyone from outside, needs a profile: Dave makes a personal invite link on /admin
# (home only), the first device to open it gets a long-lived cookie, and the link is used up. Only a hash of each
# link and each device's cookie is kept. A guest's settings (their location) are kept with their profile.
PROFILES_FILE = DATA_DIR / "profiles.json"
COOKIE = "overhead"
INVITE_DAYS = 14
GUEST_FR24_DAY = 150        # most Flightradar24 lookups a day for a guest it has been turned on for
_profiles = None            # {"profiles": {id: {...}}, "invites": {hash: {...}}}
_buckets = {}
_made = {}                  # one-off key -> (expires, (name, invite code)): the admin page's last new link


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


# Apps that fetch a link to show its preview in a chat (relay 27: before, opening an invite link claimed it, so WhatsApp
# took the link before the person it was sent to). They get the invite page, never a device.
PREVIEW_BOT = re.compile(r"WhatsApp|facebookexternalhit|Facebot|TelegramBot|Twitterbot|Slackbot|Discordbot|SkypeUriPreview|"
                         r"LinkedInBot|Googlebot|bingbot|Applebot|redditbot|Embedly|vkShare|Iframely|Pinterestbot|"
                         r"Mattermost|Bluesky|Mastodon|crawler|spider|\bbot\b", re.I)



def profiles():
    global _profiles
    if _profiles is None:
        _profiles = _load(PROFILES_FILE, None) or {"profiles": {}, "invites": {}}
        for p in [_profiles.get("home") or {}, *_profiles["profiles"].values()]:     # devices that were only a chat's preview
            keep = [d for d in p.get("devices", []) if not PREVIEW_BOT.search(d.get("device") or "")]
            if len(keep) != len(p.get("devices", [])):
                p["devices"] = keep
                _dirty.add("profiles")
    return _profiles


def peek_invite(code):
    """Whom a still valid invite link is for, without using it up: the profile's name, or None."""
    with _data_lock:
        P = profiles()
        inv = P["invites"].get(_hash(code))
        if not inv or inv["expires"] <= time.time():
            return None
        if inv["profile"] == "home":
            return "Home"
        p = P["profiles"].get(inv["profile"])
        return p["name"] if p else None


def new_invite(name=None, pid=None):
    """A personal invite link: for a new profile (`name`) or another device of an existing one (`pid`)."""
    code = secrets.token_urlsafe(18)
    with _data_lock:
        P = profiles()
        if pid is None:
            pid = secrets.token_hex(4)
            while pid in P["profiles"]:
                pid = secrets.token_hex(4)
            P["profiles"][pid] = {"name": name, "created": time.time(), "lastSeen": 0, "fr24": False, "devices": [],
                                  "settings": None, "fr24Day": "", "fr24Count": 0}
        elif pid != "home" and pid not in P["profiles"]:
            return None
        now = time.time()
        P["invites"] = {h: i for h, i in P["invites"].items() if i["expires"] > now}
        P["invites"][_hash(code)] = {"profile": pid, "created": now, "expires": now + INVITE_DAYS * 86400}
        _dirty.add("profiles")
        who = "a home device" if pid == "home" else P["profiles"][pid]["name"]
    event("info", f"Invite link made for {who}")
    return code


def redeem(code, ua):
    """The first device to open an invite link: a new device of that profile. Returns (profile id, cookie value)."""
    with _data_lock:
        P = profiles()
        inv = P["invites"].pop(_hash(code), None)
        if inv:
            _dirty.add("profiles")
        p = None
        if inv and inv["expires"] > time.time():
            p = P.setdefault("home", {"name": "Home", "devices": [], "push": []}) if inv["profile"] == "home" else P["profiles"].get(inv["profile"])
        if not p:
            return None, None
        token = secrets.token_urlsafe(32)
        p["devices"].append({"token": _hash(token), "device": device_of(ua), "added": time.time(), "lastSeen": time.time()})
        p["lastSeen"] = time.time()
    event("info", f"{p['name']} joined on a {device_of(ua)}")
    return inv["profile"], token


# ---------- accounts (relay 30): a guest's profile can get a username and a way to sign in on a new phone or computer
# without a new invite link: passkeys first (Face ID, a fingerprint, the phone's screen lock; nothing secret is kept
# here, only each passkey's public key), and a password as a backup (kept as a salted scrypt hash). An invite still
# makes the profile; the account is the guest's own choice later, in the app's About or at the end of the welcome.
ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")
_challenges = {}             # challenge -> (purpose, profile id or "", expires)


def _challenge(purpose, pid=""):
    now = time.time()
    with _lock:
        for k in [k for k, v in _challenges.items() if v[2] < now]:
            del _challenges[k]
        c = _b64u(secrets.token_bytes(32))
        _challenges[c] = (purpose, pid, now + 300)
    return c


def _take_challenge(c, purpose, pid=""):
    with _lock:
        v = _challenges.pop(str(c or ""), None)
    return bool(v) and v[0] == purpose and v[1] == pid and v[2] > time.time()


def _cbor(b, i=0):
    """A small CBOR reader, enough for WebAuthn: (value, next index)."""
    ib = b[i]; mt, ai = ib >> 5, ib & 31; i += 1
    if ai < 24:
        n = ai
    elif ai in (24, 25, 26, 27):
        k = 1 << (ai - 24)
        n = int.from_bytes(b[i:i + k], "big"); i += k
    else:
        raise ValueError("indefinite CBOR")
    if mt == 0:
        return n, i
    if mt == 1:
        return -1 - n, i
    if mt == 2:
        return bytes(b[i:i + n]), i + n
    if mt == 3:
        return b[i:i + n].decode("utf-8"), i + n
    if mt == 4:
        out = []
        for _ in range(n):
            v, i = _cbor(b, i); out.append(v)
        return out, i
    if mt == 5:
        out = {}
        for _ in range(n):
            k, i = _cbor(b, i); v, i = _cbor(b, i); out[k] = v
        return out, i
    if mt == 7:
        return {20: False, 21: True, 22: None}.get(ai), i
    raise ValueError("CBOR type")


def _cose_to_spki(cose):
    """A COSE public key (ES256 or RS256) as DER SubjectPublicKeyInfo, and its algorithm."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    alg = cose.get(3)
    if cose.get(1) == 2 and alg == -7 and cose.get(-1) == 1:
        pub = ec.EllipticCurvePublicNumbers(int.from_bytes(cose[-2], "big"), int.from_bytes(cose[-3], "big"), ec.SECP256R1()).public_key()
    elif cose.get(1) == 3 and alg == -257:
        pub = rsa.RSAPublicNumbers(int.from_bytes(cose[-2], "big"), int.from_bytes(cose[-1], "big")).public_key()
    else:
        raise ValueError("unsupported key")
    return pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo), alg


def _client_data(raw, kind, origin):
    cd = json.loads(raw)
    if cd.get("type") != kind or cd.get("origin") != origin:
        raise ValueError("wrong origin or type")
    return cd.get("challenge")


def _auth_data(ad, rp_id):
    if len(ad) < 37 or not hmac.compare_digest(ad[:32], hashlib.sha256(rp_id.encode()).digest()):
        raise ValueError("wrong relying party")
    flags, count = ad[32], int.from_bytes(ad[33:37], "big")
    if not flags & 1:
        raise ValueError("user not present")
    return flags, count


def passkey_register(pid, rp_id, origin, j):
    """Check a new passkey (navigator.credentials.create) and keep its public key. Attestation isn't checked: any
    authenticator will do, it only has to prove the key is new and made for this site."""
    raw = _ub64(str(j.get("clientDataJSON") or ""))
    if not _take_challenge(_client_data(raw, "webauthn.create", origin), "reg", pid):
        raise ValueError("challenge expired; try again")
    att, _ = _cbor(_ub64(str(j.get("attestationObject") or "")))
    ad = att["authData"]
    flags, count = _auth_data(ad, rp_id)
    if not flags & 0x40:
        raise ValueError("no key in the answer")
    n = int.from_bytes(ad[53:55], "big")
    cred_id = ad[55:55 + n]
    cose, _ = _cbor(ad, 55 + n)
    spki, alg = _cose_to_spki(cose)
    with _data_lock:
        p = profiles()["profiles"].get(pid)
        acc = p.setdefault("account", {})
        keys = acc.setdefault("passkeys", [])
        if any(k["id"] == _b64u(cred_id) for k in keys):
            raise ValueError("this passkey is already added")
        keys.append({"id": _b64u(cred_id), "pub": _b64u(spki), "alg": alg, "count": count,
                     "name": str(j.get("name") or "")[:40] or "passkey", "added": time.time(), "used": 0})
        del keys[:-10]
        _dirty.add("profiles")
        event("info", f"{p['name']} added a passkey ({str(j.get('name') or '')[:40]})")


def passkey_signin(rp_id, origin, j):
    """Check a passkey's signature (navigator.credentials.get); returns the profile id it belongs to."""
    from cryptography.hazmat.primitives.asymmetric import padding
    raw = _ub64(str(j.get("clientDataJSON") or ""))
    if not _take_challenge(_client_data(raw, "webauthn.get", origin), "auth"):
        raise ValueError("challenge expired; try again")
    ad = _ub64(str(j.get("authenticatorData") or ""))
    _, count = _auth_data(ad, rp_id)
    cid = str(j.get("id") or "")
    with _data_lock:
        hit = next(((pid, k) for pid, p in profiles()["profiles"].items() for k in (p.get("account") or {}).get("passkeys", []) if k["id"] == cid), None)
    if not hit:
        raise ValueError("this passkey isn't known here (removed, or made for another board)")
    pid, k = hit
    pub = serialization.load_der_public_key(_ub64(k["pub"]))
    msg, sig = ad + hashlib.sha256(raw).digest(), _ub64(str(j.get("signature") or ""))
    if k["alg"] == -7:
        pub.verify(sig, msg, ec.ECDSA(hashes.SHA256()))
    else:
        pub.verify(sig, msg, padding.PKCS1v15(), hashes.SHA256())
    with _data_lock:
        if count and k.get("count") and count <= k["count"]:
            raise ValueError("this passkey looks copied")
        k["count"], k["used"] = count, time.time()
        _dirty.add("profiles")
    return pid


def _pw_hash(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    try:
        h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
        alg = "scrypt"
    except (AttributeError, ValueError):
        h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 400000)
        alg = "pbkdf2"
    return {"alg": alg, "salt": _b64u(salt), "hash": _b64u(h)}


def _pw_ok(rec, pw):
    if not rec:
        return False
    salt = _ub64(rec["salt"])
    if rec.get("alg") == "pbkdf2":
        h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 400000)
    else:
        h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return hmac.compare_digest(h, _ub64(rec["hash"]))


def account_of(user):
    """The profile id with this username, or None."""
    user = str(user or "").strip().lower()
    with _data_lock:
        return next((pid for pid, p in profiles()["profiles"].items() if (p.get("account") or {}).get("user") == user), None)


def account_json(pid, https):
    with _data_lock:
        p = profiles()["profiles"].get(pid) or {}
        a = p.get("account") or {}
        return {"name": p.get("name", ""), "user": a.get("user") or "", "password": bool(a.get("pw")),
                "passkeys": [{"id": k["id"], "name": k.get("name", ""), "added": int(k.get("added", 0) * 1000),
                              "used": int(k.get("used", 0) * 1000)} for k in a.get("passkeys", [])],
                "passkeysOk": PUSH_OK and https}


def add_device(pid, ua, how):
    """A device signing in to an account: a new device of that profile. Returns the cookie value."""
    token = secrets.token_urlsafe(32)
    with _data_lock:
        p = profiles()["profiles"][pid]
        p["devices"].append({"token": _hash(token), "device": device_of(ua), "added": time.time(), "lastSeen": time.time(), "via": how})
        del p["devices"][:-20]
        p["lastSeen"] = time.time()
        _dirty.add("profiles")
    event("info", f"{p['name']} signed in with {how} on a {device_of(ua)}")
    return token


def signin_html():
    return plain_page("Fallblatt: sign in", (
        "<h1>Sign in</h1><p>With your Fallblatt account: your place, logbook and settings come with you to this phone or computer.</p>"
        "<p><button class='go big' type=button id=pk>Sign in with a passkey</button></p>"
        "<form id=pf><p><input type=text id=u autocomplete='username webauthn' placeholder='Username' required> "
        "<input type=password id=pw autocomplete=current-password placeholder='Password' required "
        "style='background:#16171a;color:#e8e2d0;border:1px solid #34363b;border-radius:6px;padding:9px 10px;font:inherit;width:210px'> "
        "<button type=submit>Sign in</button></p></form><p id=msg class=muted></p>"
        "<p class=muted>No account yet? Ask the person who runs this board for an invite link, then create one in the app's About.</p>"
        "<script>" + SIGNIN_JS + "</script>"))


SIGNIN_JS = (
    "var b64u=function(b){return btoa(String.fromCharCode.apply(null,new Uint8Array(b))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'')};"
    "var ub64=function(s){s=s.replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';return Uint8Array.from(atob(s),function(c){return c.charCodeAt(0)})};"
    "var msg=document.getElementById('msg');"
    "var post=function(u,o){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o||{})}).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j})})};"
    "var done=function(){msg.textContent='Signed in.';location.href='/app/'};"
    "var pk=document.getElementById('pk');"
    "if(!window.PublicKeyCredential||!window.isSecureContext){pk.disabled=true;pk.textContent='Passkeys need the https address'}"
    "pk.onclick=function(){msg.textContent='';post('/signin/begin').then(function(o){return navigator.credentials.get({publicKey:{challenge:ub64(o.challenge),rpId:o.rpId,userVerification:'preferred',timeout:120000}})})"
    ".then(function(a){return post('/signin/passkey',{id:a.id,clientDataJSON:b64u(a.response.clientDataJSON),authenticatorData:b64u(a.response.authenticatorData),signature:b64u(a.response.signature)})})"
    ".then(done).catch(function(e){msg.textContent=e.name==='NotAllowedError'?'Cancelled.':(e.message||String(e))})};"
    "document.getElementById('pf').onsubmit=function(ev){ev.preventDefault();msg.textContent='';post('/signin/password',{user:document.getElementById('u').value,password:document.getElementById('pw').value})"
    ".then(done).catch(function(e){msg.textContent=e.message})};")


def profile_for(token):
    """The profile a device's cookie belongs to: (id, profile) or (None, None)."""
    if not token:
        return None, None
    h, now = _hash(token), time.time()
    with _data_lock:
        P = profiles()
        for pid, p in ([("home", P["home"])] if P.get("home") else []) + list(P["profiles"].items()):
            for d in p["devices"]:
                if secrets.compare_digest(d["token"], h):
                    if now - d.get("lastSeen", 0) > 60:     # keep "last seen" without writing on every request
                        d["lastSeen"] = p["lastSeen"] = now
                        _dirty.add("profiles")
                    return pid, p
    return None, None


def remove_device(pid, token):
    with _data_lock:
        p = profiles()["profiles"].get(pid)
        if p:
            h = _hash(token)
            p["devices"] = [d for d in p["devices"] if not secrets.compare_digest(d["token"], h)]
            _dirty.add("profiles")
    if p:
        event("info", f"{p['name']} signed out a device")


def remove_profile(pid):
    with _data_lock:
        p = profiles()["profiles"].pop(pid, None)
        profiles()["invites"] = {h: i for h, i in profiles()["invites"].items() if i["profile"] != pid}
        _guest_spots.pop(pid, None)
        _dirty.add("profiles")
    if p:
        shutil.rmtree(DATA_DIR / "profiles" / pid, ignore_errors=True)
        event("info", f"Removed {p['name']} and their sightings")


def _guest_center(pid):
    def center():
        st = (profiles()["profiles"].get(pid) or {}).get("settings") or {}
        try:
            lat, lon = float(st.get("lat")), float(st.get("lon"))
        except (TypeError, ValueError):
            return None
        return (lat, lon) if abs(lat) <= 90 and abs(lon) <= 180 else None
    return center


def _guest_radius(pid):
    def radius():
        st = (profiles()["profiles"].get(pid) or {}).get("settings") or {}
        try:
            return min(20.0, max(1.0, float(st.get("radiusKm") or 15)))
        except (TypeError, ValueError):
            return 15.0
    return radius


def guest_spot(pid):
    with _data_lock:
        sp = _guest_spots.get(pid)
        if sp is None:
            sp = _guest_spots[pid] = Spot(DATA_DIR / "profiles" / pid, _guest_center(pid), _guest_radius(pid))
            sp.ensure_day()
            sp.book()                       # scored again now if an older rule scored it, not in the middle of a sighting
        return sp


def guest_fr24(p):
    """May this guest's board ask Flightradar24 now? Only if Dave turned it on for them, and within a daily share."""
    if not p.get("fr24") or not fr24_on():
        return False
    with _data_lock:
        today = board_day()
        if p.get("fr24Day") != today:
            p["fr24Day"], p["fr24Count"] = today, 0
        return p.get("fr24Count", 0) < GUEST_FR24_DAY


def allow(key, rate, burst):
    """A token bucket per visitor: `rate` requests a second on average, `burst` at once."""
    now = time.time()
    with _lock:
        tokens, t = _buckets.get(key, (burst, now))
        tokens = min(burst, tokens + (now - t) * rate)
        ok = tokens >= 1
        _buckets[key] = (tokens - 1 if ok else tokens, now)
        if len(_buckets) > 5000:               # drop the quietest half, not everyone's limits at once
            for k in sorted(_buckets, key=lambda k: _buckets[k][1])[:2500]:
                del _buckets[k]
        return ok


_pw_fails = {}               # username -> (failures in a row, not before) (relay 33)
_DUMMY_PW = None


def pw_wait(user):
    """Seconds until this account may try a password again (0: now)."""
    with _lock:
        n, until = _pw_fails.get(user, (0, 0))
    return max(0, int(until - time.time()))


def pw_failed(user, ok):
    """Five wrong passwords in a row, then a wait that doubles with each one more (1 min, 2, 4 … up to an hour)."""
    with _lock:
        if ok:
            _pw_fails.pop(user, None)
            return
        n = _pw_fails.get(user, (0, 0))[0] + 1
        _pw_fails[user] = (n, time.time() + (min(3600, 60 * 2 ** (n - 5)) if n >= 5 else 0))
        if len(_pw_fails) > 2000:
            _pw_fails.clear()


def _ago(t):
    if not t:
        return "never"
    s = time.time() - t
    return "just now" if s < 120 else f"{int(s // 60)} min ago" if s < 3600 else f"{int(s // 3600)} h ago" if s < 86400 else f"{int(s // 86400)} days ago"


PAGE_CSS = """body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0b0c;color:#e8e2d0;
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:620px;padding:32px 22px}
h1{font-size:26px;margin:0 0 10px}h2{font-size:18px;margin:28px 0 8px}p{color:#b9b3a3}a{color:#f2b134}
.word{display:flex;gap:4px;margin:0 0 22px;perspective:400px}.word b{position:relative;display:grid;place-items:center;width:30px;
height:42px;border-radius:4px;background:linear-gradient(#232428 0 49%,#141518 51%);box-shadow:0 2px 0 #000,inset 0 1px 0 rgba(255,255,255,.08);
color:#f4efe2;font:700 26px/1 "Arial Narrow",Arial,sans-serif;transform-origin:50% 50%;animation:flip .5s cubic-bezier(.3,.7,.4,1) both}
.word b::after{content:"";position:absolute;left:0;right:0;top:50%;height:1px;background:rgba(0,0,0,.85)}
.word b:last-child{animation-duration:1.3s;animation-timing-function:cubic-bezier(.15,.85,.25,1)}
@keyframes flip{0%{transform:rotateX(90deg);opacity:0}60%{opacity:1}100%{transform:rotateX(0)}}
@media (prefers-reduced-motion:reduce){.word b{animation:none}}table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:8px 6px;border-bottom:1px solid #26272b;text-align:left;vertical-align:top}th{color:#8d887b;font-weight:600}
input[type=text]{background:#16171a;color:#e8e2d0;border:1px solid #34363b;border-radius:6px;padding:9px 10px;font:inherit;width:210px}
button{background:#2a2c31;color:#e8e2d0;border:1px solid #3a3c42;border-radius:6px;padding:8px 12px;font:inherit;cursor:pointer}
button.go{background:#f2b134;color:#111;border-color:#f2b134;font-weight:700}button.big{margin:8px 0 14px;padding:14px 22px;font-size:18px;border-radius:10px}form{display:inline}
.link{display:block;margin:10px 0;padding:12px;border-radius:8px;background:#16171a;border:1px solid #f2b134;word-break:break-all;user-select:all;-webkit-user-select:all;
font:14px/1.4 ui-monospace,Consolas,monospace;color:#f2b134}.muted{color:#8d887b;font-size:13px}"""


def plain_page(title, body):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{html.escape(title)}</title><style>{PAGE_CSS}</style></head><body><main>'
            f'<div class="word" role="img" aria-label="Fallblatt">{WORDMARK}</div>{body}</main></body></html>').encode("utf-8")


WORDMARK = "".join(f'<b style="animation-delay:{i * 70}ms">{ch}</b>' for i, ch in enumerate("FALLBLATT"))


# Copying the link: the clipboard API only works on https pages, and the admin page is plain http at home, so the
# old way (a hidden text field and the copy command) goes first. "Copied" only when it worked; otherwise the link is
# selected, ready to copy by hand.
COPY_JS = ("function cp(){var t=document.getElementById('lnk').textContent,ok=false,d=document.getElementById('cpd');"
           "try{var a=document.createElement('textarea');a.value=t;a.setAttribute('readonly','');a.style.position='fixed';"
           "a.style.opacity='0';document.body.appendChild(a);a.select();a.setSelectionRange(0,t.length);ok=document.execCommand('copy');"
           "a.remove()}catch(e){}"
           "var done=function(){d.textContent='Copied';d.style.color='#3c3';document.getElementById('lnk').style.borderColor='#3c3'};"
           "var hand=function(){var r=document.createRange();r.selectNodeContents(document.getElementById('lnk'));"
           "var g=getSelection();g.removeAllRanges();g.addRange(r);d.textContent='Selected: copy it with Ctrl+C or the menu';d.style.color=''};"
           "if(ok)return done();if(navigator.clipboard)navigator.clipboard.writeText(t).then(done,hand);else hand()}")


def admin_html(host, made=None):
    esc = html.escape
    base = (ARGS.public_url or "").rstrip("/") or f"http://{host}"
    rows = []
    with _data_lock:
        items = sorted(profiles()["profiles"].items(), key=lambda kv: -kv[1].get("lastSeen", 0))
        pending = collections.Counter(i["profile"] for i in profiles()["invites"].values() if i["expires"] > time.time())
        for pid, p in items:
            kinds = collections.Counter(d.get("device") or "device" for d in p["devices"])
            devs = ", ".join(f"{k} ×{n}" if n > 1 else k for k, n in sorted(kinds.items())) or "not joined yet"
            st = p.get("settings") or {}
            where = esc(str(st.get("place") or "")) or ('location set' if st.get("lat") is not None else "no location yet")
            fr = "on" if p.get("fr24") else "off"
            acc = p.get("account") or {}
            acct = (f"account <b>{esc(acc['user'])}</b>: {len(acc.get('passkeys', []))} passkey{'s' if len(acc.get('passkeys', [])) != 1 else ''}"
                    f"{', password' if acc.get('pw') else ''}" if acc.get("user") else "no account")
            rows.append(
                f"<tr><td><b>{esc(p['name'])}</b><br><span class=muted>{where}<br>{acct}</span></td>"
                f"<td>{esc(devs)}<br><span class=muted>seen {_ago(p.get('lastSeen'))}"
                f"{f' · {pending[pid]} unused link' if pending[pid] else ''}</span></td>"
                f"<td><form method=post action='/admin/fr24'><input type=hidden name=pid value='{pid}'>"
                f"<input type=hidden name=on value='{'0' if p.get('fr24') else '1'}'><button title='Flightradar24 flight numbers, "
                f"at most {GUEST_FR24_DAY} lookups a day'>FR24 {fr}</button></form></td>"
                f"<td><form method=post action='/admin/link'><input type=hidden name=pid value='{pid}'><button>New link</button></form> "
                + (f"<form method=post action='/admin/resetaccount' onsubmit=\"return confirm({esc(json.dumps('Remove ' + p['name'] + chr(39) + 's passkeys and password? They can set them again from a signed-in device.'))})\">"
                   f"<input type=hidden name=pid value='{pid}'><button>Reset sign-in</button></form> " if acc.get("user") else "") +
                f"<form method=post action='/admin/remove' onsubmit=\"return confirm({esc(json.dumps('Remove ' + p['name'] + ' and their sightings?'))})\">"
                f"<input type=hidden name=pid value='{pid}'><button>Remove</button></form></td></tr>")
    made_html = ""
    if made:
        name, code = made
        link = f"{base}/join/{code}"
        made_html = (f"<h2>Link for {esc(name)}</h2><p>Send this to {esc(name)}. It works once, on the first phone or "
                     f"computer that opens it, within {INVITE_DAYS} days.</p><div class=link id=lnk>{esc(link)}</div>"
                     f"<button class=go type=button onclick='cp()'>Copy link</button> <span id=cpd class=muted></span>"
                     f"<script>{COPY_JS}</script>")
        if not ARGS.public_url:
            made_html += ("<p class=muted>The relay doesn't know its public address yet, so this link only works at home. "
                          "Start it once with <code>--public-url https://overhead.example.com --save</code>.</p>")
    table = (f"<table><tr><th>Who</th><th>Devices</th><th></th><th></th></tr>{''.join(rows)}</table>" if rows
             else "<p>Nobody yet. Invite someone below.</p>")
    home = profiles().get("home") or {}
    hd = ", ".join(sorted({d.get("device") or "device" for d in home.get("devices", [])})) or "none yet"
    home_html = (f"<h2>Your own devices</h2><p>Link a phone to Home to use your own place and logbook through the public "
                 f"address, and get notifications. Linked: {html.escape(hd)}.</p><form method=post action='/admin/homelink'>"
                 f"<button class=go>Link a device to Home</button></form> <form method=post action='/admin/homeclear' "
                 f"onsubmit=\"return confirm('Unlink all home devices?')\"><button>Unlink all</button></form>")
    body = (f"<h1>Friends &amp; family</h1><p>Everyone here has their own profile: their own location, Spotted "
            f"today and logbook. This page only opens at home.</p>{made_html}<h2>People</h2>{table}<h2>Invite someone</h2>"
            f"<form method=post action='/admin/invite'><input type=text name=name maxlength=40 placeholder='Name, e.g. Mum' required> "
            f"<button class=go>Make a link</button></form>" + home_html + fr24_admin_html())
    return plain_page("Fallblatt: friends & family", body)


def fr24_admin_html():
    """Flightradar24 this month (relay 28): credits used against the budget, where the month is heading, and what the
    lookups added, to help decide whether the subscription is worth renewing."""
    if not fr24_key():
        return "<h2>Flightradar24</h2><p class=muted>No key: the boards use the free sources only.</p>"
    with _data_lock:
        u = dict(_fr24_usage())
    budget, used, today = _fr24_budget(), u.get("credits", 0), u.get("creditsToday", 0)
    now = datetime.date.today()
    days = ((now.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)).day
    t = time.localtime()
    done = max(.25, now.day - 1 + (t.tm_hour * 3600 + t.tm_min * 60) / 86400)        # days of the month gone so far
    pace = round(used / done * days)
    pct = min(100, round(used / max(1, budget) * 100))
    col = "#3c3" if pace <= budget else "#f2b134" if pace <= budget * 1.1 else "#e0372c"
    st = fr24_status()
    return (f"<h2>Flightradar24</h2><p><b>{used:,}</b> of {budget:,} credits this month · {today:,} today · "
            f"on pace for <b style='color:{col}'>{pace:,}</b></p>"
            f"<div style='height:10px;border-radius:5px;background:#16171a;border:1px solid #34363b;overflow:hidden'>"
            f"<div style='height:100%;width:{pct}%;background:{col}'></div></div>"
            f"<p class=muted>{u.get('lookups', 0):,} lookups · {u.get('found', 0):,} flights found · "
            f"{u.get('wetLease', 0):,} in another airline's livery · {u.get('diverted', 0):,} diverted · "
            f"state: {html.escape(str(st.get('state', '')))}</p>")


# ---------- push notifications (relay 25): the evening summary and "worth going to the window" ----------
# Web Push to browsers (https only: through the public address), encrypted (RFC 8291) and signed (VAPID) with the relay's own
# key in data/vapid.pem. Needs the cryptography package (Debian: python3-cryptography); without it there are no
# notifications and everything else works as before. Subscriptions live with each profile (home: profiles["home"]).
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    PUSH_OK = True
except ImportError:
    PUSH_OK = False
VAPID_FILE = DATA_DIR / "vapid.pem"
_vapid = None
SUMMARY_AT = "22:30"
_sent = {}                  # (subscription endpoint, plane hex) -> time: one window alert per plane


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _ub64(t):
    return base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))


def vapid():
    """The relay's signing key and its public half (base64url), made the first time."""
    global _vapid
    if _vapid or not PUSH_OK:
        return _vapid
    try:
        key = serialization.load_pem_private_key(VAPID_FILE.read_bytes(), None)
    except (OSError, ValueError):
        key = ec.generate_private_key(ec.SECP256R1())
        DATA_DIR.mkdir(exist_ok=True)
        VAPID_FILE.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        try:
            os.chmod(VAPID_FILE, 0o600)
        except OSError:
            pass
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    _vapid = (key, _b64u(pub))
    return _vapid


def _hkdf(salt, info, ikm, n):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def push_send(sub, payload, urgent=False):
    """Send one notification. Returns the HTTP status (404/410: the subscription is gone)."""
    key, pub = vapid()
    ua_pub, auth = _ub64(sub["keys"]["p256dh"]), _ub64(sub["keys"]["auth"])
    eph = ec.generate_private_key(ec.SECP256R1())
    as_pub = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = _hkdf(auth, b"WebPush: info\x00" + ua_pub + as_pub, shared, 32)
    salt = secrets.token_bytes(16)
    cek, nonce = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", ikm, 16), _hkdf(salt, b"Content-Encoding: nonce\x00", ikm, 12)
    body = salt + struct.pack(">I", 4096) + bytes([len(as_pub)]) + as_pub + AESGCM(cek).encrypt(nonce, json.dumps(payload).encode() + b"\x02", None)
    u = urllib.parse.urlsplit(sub["endpoint"])
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": ARGS.public_url or "https://github.com/Belstria/overhead-board"}
    head = _b64u(json.dumps({"typ": "JWT", "alg": "ES256"}).encode()) + "." + _b64u(json.dumps(claims).encode())
    r, s_ = decode_dss_signature(key.sign(head.encode(), ec.ECDSA(hashes.SHA256())))
    jwt = head + "." + _b64u(r.to_bytes(32, "big") + s_.to_bytes(32, "big"))
    status, _, _, _ = fetch(sub["endpoint"], data=body, content_type="application/octet-stream", timeout=15, headers={
        "Authorization": f"vapid t={jwt}, k={pub}", "Content-Encoding": "aes128gcm", "TTL": "3600", "Urgency": "high" if urgent else "normal"})
    return status


# What the notifications say, in the subscriber's language.
PUSH_TEXT = {
    "window": {"en": "Worth going to the window", "de": "Lohnt sich ein Blick aus dem Fenster", "fr": "Ça vaut le coup d'aller à la fenêtre",
               "es": "Vale la pena asomarse a la ventana", "nl": "Even naar het raam"},
    "over": {"en": "{what} passes in about {m} min · look {dir}, {alt}", "de": "{what} kommt in etwa {m} Min. vorbei · Blick nach {dir}, {alt}",
             "fr": "{what} passe dans environ {m} min · regardez vers {dir}, {alt}", "es": "{what} pasa en unos {m} min · mira al {dir}, {alt}",
             "nl": "{what} komt over ongeveer {m} min langs · kijk naar {dir}, {alt}"},
    "overhead": {"en": "{what} passes right overhead in about {m} min, {alt}", "de": "{what} fliegt in etwa {m} Min. direkt drüber, {alt}",
                 "fr": "{what} passe juste au-dessus dans environ {m} min, {alt}", "es": "{what} pasa justo encima en unos {m} min, {alt}",
                 "nl": "{what} komt over ongeveer {m} min recht over, {alt}"},
    "why_emergency": {"en": "Emergency: squawking {x}", "de": "Notfall: Squawk {x}", "fr": "Urgence : transpondeur {x}", "es": "Emergencia: squawk {x}", "nl": "Noodgeval: squawk {x}"},
    "why_special": {"en": "A special plane is coming", "de": "Ein besonderes Flugzeug kommt", "fr": "Un avion spécial arrive", "es": "Llega un avión especial", "nl": "Er komt een bijzonder toestel"},
    "why_watch": {"en": "On the watchlist: {x}", "de": "Auf der Beobachtungsliste: {x}", "fr": "Sur la liste : {x}", "es": "En la lista de vigilancia: {x}", "nl": "Op de volglijst: {x}"},
    "why_military": {"en": "A military plane is coming", "de": "Ein Militärflugzeug kommt", "fr": "Un avion militaire arrive", "es": "Llega un avión militar", "nl": "Er komt een militair toestel"},
    "why_fav": {"en": "One of your favourites", "de": "Einer deiner Favoriten", "fr": "Un de vos favoris", "es": "Uno de tus favoritos", "nl": "Een van je favorieten"},
    "why_newtype": {"en": "A type never seen here", "de": "Ein hier nie gesehener Typ", "fr": "Un type jamais vu ici", "es": "Un tipo nunca visto aquí", "nl": "Een type dat hier nooit gezien is"},
    "why_low": {"en": "Passing very low", "de": "Kommt sehr tief vorbei", "fr": "Passe très bas", "es": "Pasa muy bajo", "nl": "Komt heel laag over"},
    "day": {"en": "Your day in planes", "de": "Dein Tag in Flugzeugen", "fr": "Votre journée en avions", "es": "Tu día en aviones", "nl": "Je dag in vliegtuigen"},
    "sum": {"en": "{n} planes · {p} points{best}{rare}{low}", "de": "{n} Flugzeuge · {p} Punkte{best}{rare}{low}", "fr": "{n} avions · {p} points{best}{rare}{low}",
            "es": "{n} aviones · {p} puntos{best}{rare}{low}", "nl": "{n} vliegtuigen · {p} punten{best}{rare}{low}"},
    "rarest": {"en": " · rarest: {x}", "de": " · am seltensten: {x}", "fr": " · le plus rare : {x}", "es": " · el más raro: {x}", "nl": " · zeldzaamste: {x}"},
    "lowest": {"en": " · lowest: {x}", "de": " · am tiefsten: {x}", "fr": " · le plus bas : {x}", "es": " · el más bajo: {x}", "nl": " · laagste: {x}"},
    "record": {"en": " · a new best day!", "de": " · ein neuer Bestwert!", "fr": " · un nouveau record !", "es": " · ¡un nuevo récord!", "nl": " · een nieuw record!"},
}
DIRS = {"en": "N NE E SE S SW W NW", "de": "N NO O SO S SW W NW", "fr": "N NE E SE S SO O NO", "es": "N NE E SE S SO O NO", "nl": "N NO O ZO Z ZW W NW"}


def ptext(key, lang, **kw):
    t = PUSH_TEXT[key]
    return (t.get(lang) or t["en"]).format(**kw)


def push_targets():
    """Who gets notifications: (who, subscriptions, centre, spot, settings) for home and each guest who has some."""
    out = []
    with _data_lock:
        P = profiles()
        home = P.get("home") or {}
        if home.get("push") and ARGS.lat is not None:
            out.append(("home", home["push"], (ARGS.lat, ARGS.lon), HOME, home.get("settings") or {}))
        for pid, p in P["profiles"].items():
            st = p.get("settings") or {}
            if p.get("push") and st.get("lat") is not None:
                try:
                    out.append((pid, p["push"], (float(st["lat"]), float(st["lon"])), guest_spot(pid), st))
                except (TypeError, ValueError):
                    pass
    return out


PUSH_HOSTS = ("fcm.googleapis.com", ".push.apple.com", "updates.push.services.mozilla.com", ".notify.windows.com",
              "push.services.mozilla.com")


def push_endpoint_ok(ep):
    """A browser's push address: https at one of the push services (relay 33: any https address used to do, so the
    relay could be made to send requests anywhere)."""
    u = urllib.parse.urlsplit(ep)
    h = (u.hostname or "").lower()
    return u.scheme == "https" and any(h == p or (p.startswith(".") and h.endswith(p)) for p in PUSH_HOSTS)


def _deliver(subs, payload, urgent=False):
    gone = []
    for sub in list(subs):
        try:
            status = push_send(sub, payload, urgent)
        except Exception as e:
            event("warn", f"Couldn't send a notification: {e}", echo=False)
            continue
        if status in (404, 410):
            gone.append(sub["endpoint"])
        elif status >= 400:
            event("warn", f"A push service answered HTTP {status}", echo=False)
    if gone:
        with _data_lock:
            subs[:] = [s_ for s_ in subs if s_["endpoint"] not in gone]
            _dirty.add("profiles")


def _fav_tokens(st):
    return [re.sub(r"[\s-]", "", t.strip().upper()) for t in re.split(r"[,;\n]+", str(st.get("favs") or "")) if t.strip()]


# Favourites and hidden planes (relay 31), per profile (home: profiles["home"]): lists of {k: reg|type|airline|flight,
# v: the code, n: a name to show}, set by the phone app and read by the boards and the notifications.
LIST_KINDS = ("reg", "type", "airline", "flight")


def _clean_list(items):
    out, seen = [], set()
    for it in (items if isinstance(items, list) else [])[:200]:
        if not isinstance(it, dict):
            continue
        k, v = str(it.get("k") or ""), re.sub(r"[^A-Z0-9 -]", "", str(it.get("v") or "").upper())[:12].strip()
        if k in LIST_KINDS and v and (k, v) not in seen:
            seen.add((k, v))
            out.append({"k": k, "v": v, "n": re.sub(r"[\x00-\x1f<>]", "", str(it.get("n") or ""))[:40]})
    return out


# Places (relay 33): a profile's saved places ({k: "home" or the label, n: the name shown under the title, lat, lon,
# home: airport code, r: radius km}), shared by its devices; "live" is a phone following its owner. A screen says which
# place it watches with each position request (?pl=key&pc=lat,lon&pr=km), and its sightings carry that key.
PLACE_KEY = re.compile(r"^[^<>\x00-\x1f\"&]{1,24}$")


def place_key(k):
    k = str(k or "").strip()
    return k if PLACE_KEY.match(k) else None


def screen_place(q):
    """(key, (lat, lon), radius km) of the place a screen watches, from its position request; None: the profile's own."""
    k = place_key((q.get("pl") or [""])[0])
    if not k:
        return None
    try:
        lat, lon = (float(x) for x in (q.get("pc") or [""])[0].split(","))
        r = min(20.0, max(1.0, float((q.get("pr") or ["15"])[0])))
        assert abs(lat) <= 90 and abs(lon) <= 180
    except (ValueError, AssertionError):
        return None
    return k, (lat, lon), r


def _clean_places(items):
    out, seen = [], set()
    for it in (items if isinstance(items, list) else [])[:20]:
        if not isinstance(it, dict):
            continue
        k = place_key(it.get("k"))
        try:
            lat, lon, r = float(it.get("lat")), float(it.get("lon")), min(20.0, max(1.0, float(it.get("r") or 15)))
            assert abs(lat) <= 90 and abs(lon) <= 180
        except (TypeError, ValueError, AssertionError):
            continue
        if not k or k.lower() in seen or k.lower() == "live":
            continue
        seen.add(k.lower())
        out.append({"k": k, "n": re.sub(r"[\x00-\x1f<>]", "", str(it.get("n") or ""))[:24], "lat": round(lat, 5), "lon": round(lon, 5),
                    "home": re.sub(r"[^A-Z]", "", str(it.get("home") or "").upper())[:3], "r": r})
    return out


def places_of(pid):
    with _data_lock:
        P = profiles()
        owner = (P["profiles"].get(pid) if pid else P.get("home")) or {}
        return list(owner.get("places") or [])


# The address search (relay 33): OpenStreetMap's Nominatim, through here so its rules are kept in one place: at most one
# request a second, a User-Agent that says who asks, answers kept a day.
NOMINATIM = "https://nominatim.openstreetmap.org"
_geo_lock = threading.Lock()
_geo_last = [0.0]
_geo_cache = {}


def _geo_get(url):
    now = time.time()
    with _lock:
        hit = _geo_cache.get(url)
        if hit and now - hit[0] < 86400:
            return hit[1]
    with _geo_lock:                           # one request a second, as Nominatim asks
        wait = _geo_last[0] + 1.1 - time.time()
        if wait > 0:
            time.sleep(wait)
        status, _, body, _ = fetch(url, timeout=10)
        _geo_last[0] = time.time()
    try:
        out = json.loads(body) if status == 200 else None
    except ValueError:
        out = None
    if out is not None:
        with _lock:
            _geo_cache[url] = (now, out)
            if len(_geo_cache) > 1000:
                _geo_cache.clear()
    return out


def _geo_name(a, fallback=""):
    a = a or {}
    return (a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("suburb")
            or a.get("county") or a.get("state") or fallback or "")


def geo_search(text, lang="en"):
    j = _geo_get(f"{NOMINATIM}/search?format=jsonv2&addressdetails=1&limit=6&accept-language={urllib.parse.quote(lang)}&q={urllib.parse.quote(text)}")
    if j is None:
        return {"status": "error"}
    out = []
    for r in j if isinstance(j, list) else []:
        try:
            town, own = _geo_name(r.get("address")), str(r.get("name") or "")
            short = ", ".join(x for x in dict.fromkeys([own, town]) if x) or town
            out.append({"name": str(r.get("display_name") or "")[:160], "short": short[:60],
                        "lat": round(float(r["lat"]), 5), "lon": round(float(r["lon"]), 5)})
        except (KeyError, TypeError, ValueError):
            pass
    return {"status": "ok", "results": out}


def geo_reverse(lat, lon, lang="en"):
    j = _geo_get(f"{NOMINATIM}/reverse?format=jsonv2&zoom=12&accept-language={urllib.parse.quote(lang)}&lat={lat:.3f}&lon={lon:.3f}")
    if not isinstance(j, dict):
        return {"status": "error"}
    return {"status": "ok", "name": _geo_name(j.get("address"), j.get("name") or "")}


def lists_of(pid):
    """(favourites, hidden) of a profile; pid None is home."""
    with _data_lock:
        P = profiles()
        p = (P.get("home") or {}) if pid is None else (P["profiles"].get(pid) or {})
        L = p.get("lists") or {}
        return list(L.get("fav") or []), list(L.get("hide") or [])


def _list_hit(items, tc, cs, reg, al):
    reg = reg.replace("-", "")
    for it in items:
        v = it["v"].replace("-", "").replace(" ", "")
        if (it["k"] == "reg" and v == reg) or (it["k"] == "type" and v == tc) or (it["k"] == "airline" and v == al) \
                or (it["k"] == "flight" and v == cs.replace(" ", "")):
            return True
    return False


# Notifications (relay 31): which kinds a subscription wants, and how often. The interesting kinds are on by default,
# the rest off; at most one alert every WINDOW_GAP_S per device except emergencies and special planes, and none in
# the quiet hours (22:00-07:00, emergencies excepted) unless turned off.
PUSH_KINDS = {"special": True, "watch": True, "military": True, "fav": True, "newtype": False, "low": False}
WINDOW_GAP_S = 15 * 60
_last_window = {}            # subscription endpoint -> time of its last window alert


def _push_prefs(p):
    p = p if isinstance(p, dict) else {}
    out = {"summary": p.get("summary") is not False, "window": p.get("window") is not False, "quiet": p.get("quiet") is not False}
    for k, d in PUSH_KINDS.items():
        out[k] = bool(p[k]) if k in p else d
    return out


def window_check(who, subs, centre, spot, st):
    """Planes worth going to the window for: passing within 5 km in the next 3 minutes, and of a kind the device asked
    for (special, watchlist, military, favourite, a new type, very low); the alert says why."""
    want = [s_ for s_ in subs if (s_.get("prefs") or {}).get("window", True)]
    if not want:
        return
    # rounded like the screens' requests (relay 34), so the alerts share their answer instead of asking again
    status, body, _, _ = aircraft(f"{centre[0]:.2f}", f"{centre[1]:.2f}", "25")
    if status != 200:
        return
    try:
        planes = json.loads(body).get("ac") or json.loads(body).get("aircraft") or []
    except ValueError:
        return
    lat0, lon0 = centre
    kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57
    with _data_lock:
        book = spot.book()
        types, learning = book.get("types", {}), time.time() - book.get("startedTs", 0) < LEARN_S
    favs = _fav_tokens(st)
    fav_list, hide_list = lists_of(None if who == "home" else who)
    hour = time.localtime().tm_hour
    now = time.time()
    for k in [k for k, t in _sent.items() if now - t > 3 * 3600]:
        del _sent[k]
    for ac in planes:
        if not isinstance(ac, dict) or ac.get("lat") is None or ac.get("alt_baro") == "ground" or not ac.get("gs") or ac.get("track") is None:
            continue
        x, y = (ac["lon"] - lon0) * kx, (ac["lat"] - lat0) * ky
        v = ac["gs"] * 1.852 / 3600
        vx, vy = v * math.sin(math.radians(ac["track"])), v * math.cos(math.radians(ac["track"]))
        t = -(x * vx + y * vy) / (v * v) if v else -1                     # seconds to the closest point
        if not 20 <= t <= 180:
            continue
        cx, cy = x + vx * t, y + vy * t
        cpa = math.hypot(cx, cy)
        alt = ac.get("alt_baro") if isinstance(ac.get("alt_baro"), (int, float)) else ac.get("alt_geom")
        if cpa > 5 or (isinstance(alt, (int, float)) and alt > 20000):
            continue
        tc, cs, reg = str(ac.get("t") or "").upper(), str(ac.get("flight") or "").strip().upper(), str(ac.get("r") or "").upper()
        m_ = re.match(r"^([A-Z]{3})\d", cs)
        al = m_.group(1) if m_ else ""
        if _list_hit(hide_list, tc, cs, reg, al):
            continue
        em, w = _emergency(ac), watch_of(ac.get("hex"))
        kinds = []                         # why it's worth a look, most telling first
        if em:
            kinds.append(("emergency", em))
        if tc in LEGENDARY_TYPES or (ac.get("dbFlags") or 0) & 2:
            kinds.append(("special", ""))
        if w and w[0] != "MILITARY":
            kinds.append(("watch", w[0]))
        if tc in MILITARY_TYPES or (ac.get("dbFlags") or 0) & 1 or (w and w[0] == "MILITARY"):
            kinds.append(("military", ""))
        if any(f in (tc, cs, reg.replace("-", ""), cs[:3]) for f in favs) or _list_hit(fav_list, tc, cs, reg, al):
            kinds.append(("fav", ""))
        if tc and tc not in types and not learning:
            kinds.append(("newtype", ""))
        if isinstance(alt, (int, float)) and alt < 3000 and cpa < 2:
            kinds.append(("low", ""))
        if not kinds:
            continue
        what = " ".join(x_ for x_ in [ac.get("desc") or tc, cs] if x_) or reg or ac.get("hex", "").upper()
        for sub in want:
            key = (sub["endpoint"], ac.get("hex"))
            if key in _sent:
                continue
            pr = _push_prefs(sub.get("prefs"))
            mine = [k for k in kinds if k[0] == "emergency" or pr.get(k[0])]
            if not mine:
                continue
            urgent = mine[0][0] in ("emergency", "special")
            if not urgent and pr["quiet"] and (hour >= 22 or hour < 7):
                continue
            if not urgent and now - _last_window.get(sub["endpoint"], 0) < WINDOW_GAP_S:
                continue
            _sent[key] = now
            if not urgent:                           # emergencies and special planes don't use up the 15 minutes
                _last_window[sub["endpoint"]] = now
            lang = sub.get("lang") or "en"
            d = DIRS.get(lang, DIRS["en"]).split()[int(((math.degrees(math.atan2(cx, cy)) + 360) % 360 + 22.5) // 45) % 8]
            altx = f"{round(alt * .3048 / 50) * 50:,} m" if isinstance(alt, (int, float)) else ""
            m = max(1, round(t / 60))
            k, x = mine[0]
            why = ptext("why_" + k, lang, x=x.title() if k == "watch" else x)
            text = ptext("overhead", lang, what=what, m=m, alt=altx) if cpa < 1.2 else ptext("over", lang, what=what, m=m, dir=d, alt=altx)
            bell = "emergency" if k == "emergency" else "fav" if k == "fav" else "special"
            _deliver([sub], {"title": why, "body": text, "tag": "window-" + str(ac.get("hex")), "kind": bell, "url": "/app/"}, urgent=True)
            event("info", f"Window alert for {who}: {what} ({k})")


def summary_check(who, subs, spot, st):
    """The evening summary, once a day at SUMMARY_AT (local time)."""
    if time.strftime("%H:%M") < SUMMARY_AT:
        return
    with _data_lock:
        spot.ensure_day()
        day, entries = spot.day, list(spot.entries)
        g = game_json(spot.book(), day)
    want = [s_ for s_ in subs if (s_.get("prefs") or {}).get("summary", True) and s_.get("summaryDay") != day]
    if not want or not entries:
        return
    order = {t: i for i, t in enumerate(TIERS)}
    rare = max(entries, key=lambda e: order.get(e.get("tier"), -1))
    low = min((e for e in entries if isinstance(e.get("altAtMin"), (int, float)) and e["altAtMin"] > 0), key=lambda e: e["altAtMin"], default=None)
    for sub in want:
        lang = sub.get("lang") or "en"
        name = lambda e: " ".join(x_ for x_ in [e.get("desc") or e.get("typeCode"), e.get("callsign")] if x_)
        body = ptext("sum", lang, n=len(entries), p=g["today"],
                     best=ptext("record", lang) if g["best"] and g["best"]["day"] == day and g["today"] > 0 else "",
                     rare=ptext("rarest", lang, x=name(rare)) if order.get(rare.get("tier"), 0) >= order["rare"] else "",
                     low=ptext("lowest", lang, x=f"{name(low)}, {round(low['altAtMin'] * .3048 / 10) * 10:,} m") if low else "")
        sub["summaryDay"] = day
        _deliver([sub], {"title": ptext("day", lang), "body": body, "tag": "summary", "url": "/app/#today"})
    with _data_lock:
        _dirty.add("profiles")
    event("info", f"Evening summary sent to {who}")


def _push_watch():
    while True:
        time.sleep(30)
        if not PUSH_OK:
            continue
        for who, subs, centre, spot, st in push_targets():
            try:
                window_check(who, subs, centre, spot, st)
                summary_check(who, subs, spot, st)
            except Exception as e:
                event("warn", f"Notification check failed for {who}: {e}", echo=False)


class Handler(BaseHTTPRequestHandler):
    server_version = f"OverheadRelay/{RELAY_VERSION}"
    timeout = 30                    # a connection that sends nothing for this long is closed

    def log_message(self, fmt, *args):
        if ARGS.verbose:
            super().log_message(fmt, *args)

    def reply(self, status, content_type, body, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def query(self):
        return urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")

    def client_ip(self):
        """The screen's address. Behind a proxy on this computer (the Cloudflare tunnel, say) every request comes from
        this computer, and the proxy names the real one in Cf-Connecting-IP or X-Forwarded-For."""
        ip = self.client_address[0]
        fwd = (self.headers.get("Cf-Connecting-IP") or self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1") and re.fullmatch(r"[0-9a-fA-F.:]{3,45}", fwd):
            return fwd
        return ip

    def at_home(self):
        """A screen at home: a direct connection from a private address, or one a proxy on this computer passes on
        from a private address. Anything through the Cloudflare tunnel (Cf-Connecting-IP) is from outside."""
        if self.headers.get("Cf-Connecting-IP"):
            return False
        try:
            a = ipaddress.ip_address(self.client_ip())
            a = a.ipv4_mapped or a if a.version == 6 else a
            return a.is_private or a.is_loopback
        except ValueError:
            return False

    def identify(self):
        """Who is asking: self.guest = (id, profile) for a guest's device, None at home; self.stranger for anyone else."""
        pid, p = profile_for(self.cookie_token())
        self.homelinked = pid == "home"                  # a device linked to Home: home, from anywhere
        if self.homelinked:
            pid = p = None
        self.guest = (pid, p) if pid else None            # a guest's phone stays the guest, even on the home Wi-Fi
        self.stranger = not self.guest and not self.homelinked and not self.at_home()
        self.spot = guest_spot(pid) if pid else HOME

    def cookie_token(self):
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie") or "")
        except http.cookies.CookieError:
            pass
        return jar[COOKIE].value if COOKIE in jar else ""

    def https(self):
        """Through the tunnel (a proxy on this computer) the proxy says whether the visitor used https; anyone else's
        word for it doesn't count (relay 33)."""
        if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return False
        return (self.headers.get("X-Forwarded-Proto") or "").lower() == "https" or '"https"' in (self.headers.get("Cf-Visitor") or "")

    def host_ok(self):
        """Only the names this relay goes by (relay 33). Another site can't point its own name at the relay's address
        and have a browser at home talk to it as that site ("DNS rebinding"): such a request carries the other site's
        name. Allowed: an IP address, localhost, a name without a dot or ending in a home-network suffix, the public
        address, anything named with --allow-host, and whatever comes through a proxy on this computer (the tunnel)."""
        if self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return True
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return True
        name = host[1:].split("]")[0] if host.startswith("[") else host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        try:
            ipaddress.ip_address(name)
            return True
        except ValueError:
            pass
        if "." not in name or name.endswith((".local", ".lan", ".home", ".home.arpa", ".internal", ".localdomain", ".localhost", ".fritz.box")):
            return True
        pub = urllib.parse.urlsplit(ARGS.public_url or "").hostname or ""
        extra = {h.strip().lower() for h in str(ARGS.allow_host or "").split(",") if h.strip()}
        if name == pub.lower() or name in extra:
            return True
        if allow("hostwarn:" + name, 1 / 600, 1):        # say so now and then, so a screen with an unusual name can be let in
            event("warn", f"Refused a request for {name[:60]} from {self.client_ip()}: not one of this relay's names (start it once with --allow-host {name[:60]} --save if that's one of your screens)")
        return False

    def same_origin(self):
        """A form on the admin page, not another site posting to it."""
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        return urllib.parse.urlsplit(origin).netloc == (self.headers.get("Host") or "")

    def form(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4096:
            return {}
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}

    def refuse(self, path):
        """Not at home and no profile: a friendly page for people, a short answer for scripts."""
        if not allow("stranger:" + self.client_ip(), 1, 20):
            return self.reply(429, "text/plain", b"Too many requests")
        if PAGE.match(path):
            return self.reply(403, "text/html; charset=utf-8", plain_page("Fallblatt", (
                "<h1>This board is private</h1><p>Fallblatt shows the planes flying over your home on a split-flap board, for friends and family. "
                "Open the personal invite link you were sent to get in; it sets up this phone or computer.</p>"
                "<p><a href='/signin'>Sign in with your account</a></p>"
                "<p class=muted>Already in, but on a new device without an account? Ask for a new link.</p>")))
        return self.reply(401, "application/json", b'{"error":"not signed in"}')

    def secure(self):
        """A page browsers treat as secure (passkeys need one): https, or this computer itself while testing."""
        return self.https() or self.rp()[0] in ("localhost", "127.0.0.1")

    def rp(self):
        """This site for passkeys: its host name (the relying party) and its origin."""
        host = self.headers.get("Host") or ""
        return host.split(":")[0], ("https://" if self.https() else "http://") + host

    def json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 16384:
            return {}
        try:
            j = json.loads(self.rfile.read(length) or b"{}")
            return j if isinstance(j, dict) else {}
        except ValueError:
            return {}

    def jerr(self, status, msg):
        return self.reply(status, "application/json", json.dumps({"error": msg}).encode())

    def signed_in(self, pid, how):
        token = add_device(pid, self.headers.get("User-Agent") or "", how)
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Set-Cookie", f"{COOKIE}={token}; Path=/; Max-Age={400 * 86400}; HttpOnly; SameSite=Lax" + ("; Secure" if self.https() else ""))
        self.end_headers()
        self.wfile.write(body)

    def account_post(self, path):
        """The account endpoints: /signin/* for anyone (rate-limited), /account/* for a guest's own device."""
        if not self.same_origin():
            return self.jerr(403, "Only from this site")
        j, ip = self.json_body(), self.client_ip()
        rp_id, origin = self.rp()
        if path.startswith("/signin/"):
            if not allow("signin:" + ip, 0.1, 8):
                return self.jerr(429, "Too many tries; wait a minute")
            if path == "/signin/begin":
                return self.reply(200, "application/json", json.dumps({"challenge": _challenge("auth"), "rpId": rp_id}).encode())
            if path == "/signin/passkey":
                if not PUSH_OK:
                    return self.jerr(501, "Passkeys aren't available on this relay")
                try:
                    pid = passkey_signin(rp_id, origin, j)
                except Exception as e:
                    event("warn", f"A passkey sign-in failed ({ip}): {e}", echo=False)
                    return self.jerr(400, str(e) if isinstance(e, ValueError) else "That passkey didn't check out")
                return self.signed_in(pid, "a passkey")
            if path == "/signin/password":
                global _DUMMY_PW
                user = str(j.get("user") or "").strip().lower()[:30]
                if not allow("signinu:" + user, 0.05, 6):
                    return self.jerr(429, "Too many tries; wait a minute")
                wait = pw_wait(user)
                if wait:
                    return self.jerr(429, f"Too many wrong passwords; try again in {max(1, wait // 60)} min")
                pid = account_of(user)
                with _data_lock:
                    rec = ((profiles()["profiles"].get(pid) or {}).get("account") or {}).get("pw") if pid else None
                if rec is None:                     # check a dummy, so a missing account takes as long as a wrong password
                    _DUMMY_PW = _DUMMY_PW or _pw_hash(secrets.token_hex(8))
                    _pw_ok(_DUMMY_PW, str(j.get("password") or ""))
                ok = bool(rec) and _pw_ok(rec, str(j.get("password") or ""))
                pw_failed(user, ok)
                if not ok:
                    event("warn", f"A password sign-in failed for {user or '?'} ({ip})", echo=False)
                    return self.jerr(401, "Wrong username or password")
                return self.signed_in(pid, "a password")
            return self.jerr(404, "Not found")
        if not self.guest:
            return self.jerr(403, "Accounts are for invited guests")
        pid, p = self.guest
        if not allow("acct:" + pid, 0.5, 10):
            return self.jerr(429, "Too many requests")
        acc = p.get("account") or {}
        if path == "/account/user":
            user = str(j.get("user") or "").strip().lower()
            if not ACCOUNT_RE.match(user):
                return self.jerr(400, "3 to 30 letters, digits, dots, dashes or underscores")
            other = account_of(user)
            if other and other != pid:
                return self.jerr(409, "That username is taken")
            with _data_lock:
                p.setdefault("account", {})["user"] = user
                _dirty.add("profiles")
            event("info", f"{p['name']} has the account {user}")
        elif path == "/account/password":
            pw = str(j.get("password") or "")
            if not acc.get("user"):
                return self.jerr(400, "Choose a username first")
            if acc.get("pw") and not _pw_ok(acc["pw"], str(j.get("current") or "")):
                return self.jerr(401, "The current password is wrong")
            if len(pw) < 8:
                return self.jerr(400, "At least 8 characters")
            with _data_lock:
                p["account"]["pw"] = _pw_hash(pw)
                _dirty.add("profiles")
        elif path == "/account/passkey/begin":
            if not PUSH_OK:
                return self.jerr(501, "Passkeys aren't available on this relay")
            if not acc.get("user"):
                return self.jerr(400, "Choose a username first")
            return self.reply(200, "application/json", json.dumps({
                "challenge": _challenge("reg", pid), "rp": {"id": rp_id, "name": "Fallblatt"},
                "user": {"id": _b64u(("fallblatt:" + pid).encode()), "name": acc["user"], "displayName": p["name"]},
                "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -257}],
                "excludeCredentials": [{"type": "public-key", "id": k["id"]} for k in acc.get("passkeys", [])],
                "authenticatorSelection": {"residentKey": "required", "requireResidentKey": True, "userVerification": "preferred"},
                "timeout": 120000, "attestation": "none"}).encode())
        elif path == "/account/passkey/finish":
            try:
                passkey_register(pid, rp_id, origin, j)
            except Exception as e:
                event("warn", f"Adding a passkey for {p['name']} failed: {e}", echo=False)
                return self.jerr(400, str(e) if isinstance(e, ValueError) else "That passkey didn't check out")
        elif path == "/account/passkey/remove":
            with _data_lock:
                keys = acc.get("passkeys", [])
                keys[:] = [k for k in keys if k["id"] != str(j.get("id") or "")]
                _dirty.add("profiles")
        else:
            return self.jerr(404, "Not found")
        return self.reply(200, "application/json", json.dumps(account_json(pid, self.secure())).encode())

    def join_page(self, code):
        """The invite link opened: a page with a button that takes the invite (a POST). Chat apps fetch the link for
        its preview; they see this page and the link stays unused."""
        if not allow("join:" + self.client_ip(), 0.2, 10):
            return self.reply(429, "text/plain", b"Too many requests")
        name = peek_invite(code)
        if name is None:
            return self.join_gone()
        host = self.headers.get("Host") or ""
        icon = f"{'https' if self.https() else 'http'}://{host}/app/icon-512.png"
        desc = "The planes flying over, on a split-flap board. Open the link to set up this phone or computer."
        page = plain_page("Fallblatt", (
            f"<h1>A board for {html.escape(name)}</h1><p>Fallblatt shows the planes flying over on a split-flap board. "
            "This link sets up this phone or computer, once.</p>"
            f'<form method="post" action="/join/{code}"><button class="go big" type="submit">Open Fallblatt</button></form>'
            "<p class=muted>Not your phone or computer? Leave this page and open the link on yours.</p>")).decode("utf-8")
        meta = (f'<meta property="og:title" content="Fallblatt for {html.escape(name, quote=True)}">'
                f'<meta property="og:description" content="{desc}"><meta property="og:image" content="{html.escape(icon, quote=True)}">'
                '<meta property="og:type" content="website"><meta name="robots" content="noindex">')
        return self.reply(200, "text/html; charset=utf-8", page.replace("</head>", meta + "</head>", 1).encode("utf-8"))

    def join_gone(self):
        return self.reply(410, "text/html; charset=utf-8", plain_page("Fallblatt", (
            "<h1>This link has been used</h1><p>Each invite link works once, on the first phone or computer that "
            "opens it, for two weeks. Ask the person who sent it for a new one.</p>")))

    def join(self, code):
        if not allow("join:" + self.client_ip(), 0.2, 10):
            return self.reply(429, "text/plain", b"Too many requests")
        ua = self.headers.get("User-Agent") or ""
        if PREVIEW_BOT.search(ua) or not self.same_origin():
            return self.join_page(code)
        pid, token = redeem(code, ua)
        if not pid:
            event("warn", f"An invite link was used that has expired or been used before ({self.client_ip()})")
            return self.join_gone()
        cookie = f"{COOKIE}={token}; Path=/; Max-Age={400 * 86400}; HttpOnly; SameSite=Lax" + ("; Secure" if self.https() else "")
        self.send_response(303)
        self.send_header("Location", "/app/")
        self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def note_screen(self, path, hello=None, bye=False):
        if hello is not None and self.guest:
            hello = {**hello, "name": self.guest[1]["name"]}     # a guest's screen is listed under their name
        if path.startswith(BOARD_PATHS):
            try:
                screen_seen(self.client_ip(), self.headers.get("User-Agent") or "", self.headers.get("Referer") or "",
                            (self.query().get("sid") or [""])[0], hello, bye)
            except Exception as e:      # keeping count must never break the board
                event("warn", f"Couldn't note a screen: {e}", echo=False)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if not self.host_ok():
            return self.reply(421, "text/plain", b"This relay doesn't answer to that name (see --allow-host)")
        self.identify()
        m = re.fullmatch(r"/join/([A-Za-z0-9_-]{16,64})", path)
        if m:
            return self.join_page(m.group(1))
        if path == "/signin":
            if not allow("stranger:" + self.client_ip(), 1, 20):
                return self.reply(429, "text/plain", b"Too many requests")
            return self.reply(200, "text/html; charset=utf-8", signin_html())
        if path == "/health" or BOARD_FILE.match(path):
            pass                                  # the app's icons and manifest (fetched without cookies) and the check
        elif self.stranger:
            return self.refuse(path)
        elif self.guest and not allow("guest:" + self.guest[0], 4, 60):
            return self.reply(429, "text/plain", b"Too many requests")
        if path == "/admin" and not self.at_home():
            return self.reply(403, "text/plain", b"Only at home")
        if path == "/push/key":
            v = vapid()
            return self.reply(200, "application/json", json.dumps({"key": v[1] if v else None}).encode())
        if path in ("/screens", "/status", "/admin") and self.guest:
            return self.reply(403, "text/plain", b"Only at home")
        if path == "/admin":
            with _lock:
                hit = _made.get((self.query().get("made") or [""])[0])
            made = hit[1] if hit and hit[0] > time.time() else None
            return self.reply(200, "text/html; charset=utf-8", admin_html(self.headers.get("Host") or "", made))
        if path == "/lists":
            fav, hide = lists_of(self.guest[0] if self.guest else None)
            return self.reply(200, "application/json", json.dumps({"fav": fav, "hide": hide}).encode())
        if path == "/places":
            return self.reply(200, "application/json", json.dumps({"places": places_of(self.guest[0] if self.guest else None)}).encode())
        if path in ("/geo/search", "/geo/reverse"):
            q = self.query()
            if path == "/geo/search":
                text = re.sub(r"[\x00-\x1f]", " ", (q.get("q") or [""])[0]).strip()[:120]
                if len(text) < 2:
                    return self.reply(400, "text/plain", b"q=... is required")
                body = geo_search(text, (q.get("lang") or ["en"])[0][:2])
            else:
                try:
                    lat, lon = float((q.get("lat") or [""])[0]), float((q.get("lon") or [""])[0])
                    assert abs(lat) <= 90 and abs(lon) <= 180
                except (ValueError, AssertionError):
                    return self.reply(400, "text/plain", b"lat and lon are required")
                body = geo_reverse(lat, lon, (q.get("lang") or ["en"])[0][:2])
            return self.reply(200, "application/json", json.dumps(body).encode())
        if path == "/account":
            if not self.guest:
                return self.reply(200, "application/json", b'{"home":true}')
            return self.reply(200, "application/json", json.dumps(account_json(self.guest[0], self.secure())).encode())
        if path == "/me":
            if not self.guest:
                return self.reply(200, "application/json", b'{"home":true}')
            p = self.guest[1]
            return self.reply(200, "application/json", json.dumps({"name": p["name"], "settings": p.get("settings"), "fr24": bool(p.get("fr24"))}).encode())
        if re.fullmatch(r"/[a-z0-9-]{1,40}", path) and path not in ("/health", "/status", "/sightings", "/logbook", "/metar", "/flightinfo", "/times", "/hello", "/screens", "/airport", "/admin", "/me", "/seen", "/sky", "/watch", "/year", "/account", "/signin", "/lists", "/places"):
            self.send_response(301)  # /test → /test/
            self.send_header("Location", path + "/")
            self.end_headers()
            return
        bf = BOARD_FILE.match(path)
        if bf:
            status, body = board_file(bf.group(1) or "", bf.group(2), bf.group(3))
            return self.reply(status, FILE_TYPES[bf.group(3)] if status == 200 else "text/plain", body)
        page = PAGE.match(path)
        if page:
            html = board_html(page.group(1) or "", self.guest)
            if html is None:
                return self.reply(502, "text/plain; charset=utf-8", b"Couldn't download the board from GitHub yet. Check the internet connection and reload.")
            return self.reply(200, "text/html; charset=utf-8", html.encode("utf-8"))
        if path == "/health":
            return self.reply(200, "text/plain", b"ok")
        if path == "/hello":
            q = self.query()
            arg = lambda k, n: re.sub(r"[\x00-\x1f<>]", "", (q.get(k) or [""])[0]).strip()[:n]
            num = lambda k: int(arg(k, 6)) if arg(k, 6).isdigit() else None
            self.note_screen(path, {"name": arg("name", 40), "w": num("w"), "h": num("h"), "q": arg("q", 16), "vis": arg("vis", 10)})
            return self.reply(200, "application/json", b'{"ok":true}')
        if path == "/screens":
            return self.reply(200, "text/html; charset=utf-8", screens_html().encode("utf-8"))
        self.note_screen(path)
        if path == "/sightings":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            try:
                over = min(20.0, max(0.1, float((q.get("over") or ["3"])[0])))
            except ValueError:
                over = 3.0
            api = (q.get("api") or [""])[0] == "1" and (not self.guest or bool(self.guest[1].get("fr24")))
            data = sightings_json(self.spot, api, over, (q.get("all") or [""])[0] == "1", place_key((q.get("place") or [""])[0]))
            if api:
                data["fr24"] = fr24_on()
            return self.reply(200, "application/json", json.dumps(data).encode())
        if path == "/flightinfo":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            cs = (q.get("cs") or [""])[0].strip().upper()[:8]
            hx = (q.get("hex") or [""])[0].strip().lower()[:6]
            if not fr24_on() or (self.guest and not guest_fr24(self.guest[1])):
                body = {"status": "off"}
            else:
                info = fr24_info(cs, hx)
                if info:
                    body = {"status": "none"} if info.get("none") else {"status": "ok", **info}
                elif fr24_paced(0):
                    body = {"status": "none"}
                else:
                    fr24_want(cs, hx, 0)
                    if self.guest:
                        with _data_lock:
                            self.guest[1]["fr24Count"] = self.guest[1].get("fr24Count", 0) + 1
                    body = {"status": "queued" if re.match(r"^[A-Z0-9]{3,8}$", cs) else "none"}
            return self.reply(200, "application/json", json.dumps(body).encode())
        if path == "/times":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            arg = lambda k: (q.get(k) or [""])[0].strip().upper()[:12]
            body = vie_times(arg("fn"), arg("from"), arg("to")) if arg("fn") else {"status": "none"}
            return self.reply(200, "application/json", json.dumps(body).encode())
        if path == "/airport":
            code = re.sub(r"[^A-Za-z]", "", (self.query().get("code") or [""])[0])[:3]
            if len(code) != 3:
                return self.reply(400, "text/plain", b"code=XXX (an IATA airport code) is required")
            return self.reply(200, "application/json", json.dumps(airport_info(code)).encode())
        if path == "/airports/near":
            q = self.query()
            try:
                lat, lon = float((q.get("lat") or [""])[0]), float((q.get("lon") or [""])[0])
            except ValueError:
                return self.reply(400, "text/plain", b"lat and lon are required")
            if abs(lat) > 90 or abs(lon) > 180:
                return self.reply(400, "text/plain", b"Out of range")
            return self.reply(200, "application/json", json.dumps(airports_near(lat, lon)).encode())
        if path == "/logbook":
            return self.reply(200, "application/json", json.dumps(logbook_json(self.spot)).encode())
        if path == "/seen":
            reg = re.sub(r"[^A-Z0-9-]", "", ((self.query().get("reg") or [""])[0]).upper())[:10]
            if not reg:
                return self.reply(400, "text/plain", b"reg=... is required")
            return self.reply(200, "application/json", json.dumps(seen_json(self.spot, reg)).encode())
        if path == "/watch":
            hexes = [h for h in ((self.query().get("hex") or [""])[0]).lower().split(",") if re.fullmatch(r"[0-9a-f]{6}", h)][:80]
            watch_of("")
            if _watch["rows"] is None:                 # still downloading: the board asks again on its next update
                return self.reply(503, "application/json", b'{"loading":true}')
            out = {}
            for h in hexes:
                w = watch_of(h)
                if w:
                    out[h] = w
            return self.reply(200, "application/json", json.dumps(out).encode())
        if path == "/year":
            try:
                y = int((self.query().get("y") or [time.strftime("%Y")])[0])
            except ValueError:
                y = int(time.strftime("%Y"))
            return self.reply(200, "application/json", json.dumps(year_json(self.spot, max(2000, min(2100, y)))).encode())
        if path == "/logbook.csv":
            name = "fallblatt-logbook-" + time.strftime("%Y-%m-%d") + ".csv"
            return self.reply(200, "text/csv; charset=utf-8", logbook_csv(self.spot), {"Content-Disposition": f'attachment; filename="{name}"'})
        if path == "/sky":
            code = re.sub(r"[^A-Za-z]", "", (self.query().get("code") or [""])[0])[:3]
            if len(code) != 3:
                return self.reply(400, "text/plain", b"code=XXX (an IATA airport code) is required")
            return self.reply(200, "application/json", json.dumps(sky_json(code)).encode())
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
            if self.guest and not allow("pos:" + self.guest[0], 0.6, 12):   # a few phones polling every 10 s fit easily
                return self.reply(429, "text/plain", b"Too many requests")
            lat, lon = f"{float(lat):.2f}", f"{float(lon):.2f}"      # within a kilometre is the same question (relay 33)
            status, body, source, freshness = aircraft(lat, lon, nm)
            if status == 200:
                try:
                    with _data_lock:
                        self.spot.take(body, lat, lon, nm, screen_place(self.query()))
                except Exception as e:  # never let history problems break the live board
                    event("warn", f"Couldn't record sightings: {e}")
            return self.reply(status, "application/json", body, {"X-Relay-Source": source, "X-Relay-Data": freshness, "X-Sightings-Rev": str(self.spot.rev)})
        self.reply(404, "text/plain", b"Not found")

    do_HEAD = do_GET

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not self.host_ok():
            return self.reply(421, "text/plain", b"This relay doesn't answer to that name (see --allow-host)")
        self.identify()
        m = re.fullmatch(r"/join/([A-Za-z0-9_-]{16,64})", path)
        if m:
            return self.join(m.group(1))
        if path.startswith("/signin/") or path.startswith("/account/"):
            return self.account_post(path)
        if self.stranger:
            return self.refuse(path)
        if self.guest and not allow("guest:" + self.guest[0], 4, 60):
            return self.reply(429, "text/plain", b"Too many requests")
        if path.startswith("/admin/"):
            if self.guest or not self.at_home() or not self.same_origin():
                return self.reply(403, "text/plain", b"Only from the admin page at home")
            f, made = self.form(), None
            if path == "/admin/invite" and (f.get("name") or "").strip():
                name = re.sub(r"[\x00-\x1f<>]", "", f["name"]).strip()[:40]
                made = (name, new_invite(name=name))
            elif path == "/admin/link" and f.get("pid") in profiles()["profiles"]:
                code = new_invite(pid=f["pid"])
                if code:
                    made = (profiles()["profiles"][f["pid"]]["name"], code)
            elif path == "/admin/homelink":
                made = ("Home", new_invite(pid="home"))
            elif path == "/admin/homeclear":
                with _data_lock:
                    profiles().pop("home", None)
                    _dirty.add("profiles")
            elif path == "/admin/resetaccount" and f.get("pid") in profiles()["profiles"]:
                with _data_lock:
                    a = profiles()["profiles"][f["pid"]].get("account") or {}
                    a.pop("pw", None)
                    a["passkeys"] = []
                    _dirty.add("profiles")
            elif path == "/admin/remove" and f.get("pid"):
                remove_profile(f["pid"])
            elif path == "/admin/fr24" and f.get("pid") in profiles()["profiles"]:
                with _data_lock:
                    profiles()["profiles"][f["pid"]]["fr24"] = f.get("on") == "1"
                    _dirty.add("profiles")
            # Post/Redirect/Get: a refresh reloads the page instead of sending the form again (which made a new invite
            # each time). A new link is kept a few minutes under a one-off key so the page after the redirect can show it.
            loc = "/admin"
            if made:
                key = secrets.token_urlsafe(9)
                with _lock:
                    now = time.time()
                    for k in [k for k, v in _made.items() if v[0] < now]:
                        del _made[k]
                    _made[key] = (now + 600, made)
                loc += "?made=" + key
            self.send_response(303)
            self.send_header("Location", loc)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/places":               # the profile's saved places (relay 33)
            if not self.same_origin():
                return self.reply(403, "text/plain", b"Only from this site")
            j = self.json_body()
            with _data_lock:
                P = profiles()
                owner = self.guest[1] if self.guest else P.setdefault("home", {"name": "Home", "devices": [], "push": []})
                owner["places"] = _clean_places(j.get("places"))
                _dirty.add("profiles")
                out = list(owner["places"])
            return self.reply(200, "application/json", json.dumps({"places": out}).encode())
        if path == "/lists":                # favourites and hidden planes, from the phone app
            if not self.same_origin():
                return self.reply(403, "text/plain", b"Only from this site")
            j = self.json_body()
            with _data_lock:
                P = profiles()
                owner = self.guest[1] if self.guest else P.setdefault("home", {"name": "Home", "devices": [], "push": []})
                L = owner.setdefault("lists", {})
                for k in ("fav", "hide"):
                    if k in j:
                        L[k] = _clean_list(j[k])
                _dirty.add("profiles")
                out = {"fav": L.get("fav", []), "hide": L.get("hide", [])}
            return self.reply(200, "application/json", json.dumps(out).encode())
        if path in ("/push/subscribe", "/push/unsubscribe"):
            length = int(self.headers.get("Content-Length") or 0)
            if length > 4096 or not PUSH_OK:
                return self.reply(400 if PUSH_OK else 501, "text/plain", b"No notifications here")
            if not self.same_origin():
                return self.reply(403, "text/plain", b"Only from this site")
            try:
                j = json.loads(self.rfile.read(length) or b"{}")
                sub = j["subscription"]
                ep, keys = str(sub["endpoint"]), sub["keys"]
                assert push_endpoint_ok(ep) and isinstance(keys.get("p256dh"), str) and isinstance(keys.get("auth"), str)
                assert len(keys["p256dh"]) < 200 and len(keys["auth"]) < 100
            except (ValueError, KeyError, TypeError, AttributeError, AssertionError):
                return self.reply(400, "text/plain", b"subscription missing")
            with _data_lock:
                P = profiles()
                owner = self.guest[1] if self.guest else P.setdefault("home", {"name": "Home", "devices": [], "push": []})
                subs = owner.setdefault("push", [])
                subs[:] = [s_ for s_ in subs if s_["endpoint"] != ep]
                if path == "/push/subscribe":
                    prefs = j.get("prefs") or {}
                    subs.append({"endpoint": ep, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}, "lang": str(j.get("lang") or "en")[:2],
                                 "prefs": _push_prefs(prefs), "added": time.time()})
                    del subs[:-10]
                _dirty.add("profiles")
            return self.reply(204, "text/plain", b"")
        if path == "/me":               # a guest's settings, so their other devices (and the relay) know their place
            length = int(self.headers.get("Content-Length") or 0)
            if not self.guest:
                return self.reply(204, "text/plain", b"")
            if length > 8192:
                return self.reply(413, "text/plain", b"Too large")
            try:
                st = json.loads(self.rfile.read(length) or b"{}").get("settings")
            except (ValueError, AttributeError):
                st = None
            if not isinstance(st, dict):
                return self.reply(400, "text/plain", b"settings missing")
            with _data_lock:
                merged = {**(self.guest[1].get("settings") or {}), **st}
                if len(json.dumps(merged)) > 8192:
                    return self.reply(413, "text/plain", b"Too large")
                self.guest[1]["settings"] = merged
                _dirty.add("profiles")
            return self.reply(204, "text/plain", b"")
        if path == "/signout":          # "Sign out of this device": forget this device; the profile stays
            if self.guest:
                remove_device(self.guest[0], self.cookie_token())
            self.send_response(204)
            self.send_header("Set-Cookie", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" + ("; Secure" if self.https() else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/bye":              # a board page closing or reloading
            self.note_screen(path, bye=True)
            return self.reply(204, "text/plain", b"")
        if path != "/routeset":
            return self.reply(404, "text/plain", b"Not found")
        self.note_screen(path)
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
    p = argparse.ArgumentParser(description="Serve Fallblatt (the split-flap board and phone app) with live flight data from this computer.")
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
    p.add_argument("--local-root", help="serve every board (and the phone app) from this folder, a copy of the repository")
    p.add_argument("--fr24-key", help="Flightradar24 API key, for boards that use it (the test-api board); 'off' turns it off")
    p.add_argument("--fr24-budget", type=int, help=f"most Flightradar24 credits to spend a month (default {FR24_BUDGET:,})")
    p.add_argument("--source", help="use this position source instead of the public ones: a URL with {lat} {lon} {nm} placeholders, or a local receiver's aircraft.json")
    p.add_argument("--public-url", help="the address friends and family reach the relay at (https://overhead.example.com), for invite links")
    p.add_argument("--allow-host", help="other names screens use to reach the relay, comma-separated (IP addresses, names without a dot and .local/.lan names always work)")
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
    threading.Thread(target=_screen_watch, daemon=True).start()
    threading.Thread(target=_push_watch, daemon=True).start()
    with _data_lock:
        HOME.ensure_day()
        HOME.book()
        _fr24_data()
        _backfill_categories(HOME)
        profiles()

    server = ThreadingHTTPServer((ARGS.bind, ARGS.port), Handler)
    print(f"Fallblatt relay {RELAY_VERSION} running. Open the board at:")
    print(f"  http://localhost:{ARGS.port}")
    print(f"  http://{socket.gethostname()}:{ARGS.port}")
    ip = lan_address()
    if ip:
        print(f"  http://{ip}:{ARGS.port}")
    if fr24_key():
        print(f"Flightradar24 lookups are on for boards that use them (at most {_fr24_budget():,} credits a month).")
    print("Problems with the flight data sources and screens coming and going are printed below.")
    print(f"Friends and family: invite them at http://localhost:{ARGS.port}/admin (only opens at home).")
    print("Notifications: " + ("on (through the public https address)" if PUSH_OK else "off: install the cryptography package (Debian: python3-cryptography)"))
    print(f"Press Enter for the screens using the relay (also at http://localhost:{ARGS.port}/screens). Press Ctrl+C to stop.", flush=True)
    threading.Thread(target=_console, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
