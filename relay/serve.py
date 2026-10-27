#!/usr/bin/env python3
"""Fallblatt (the Overhead board) home relay.

Serves the board and fetches live aircraft positions from your home connection.
The public ADS-B services don't let browsers on other websites read their data and
turn away cloud servers, so the requests need to come from a machine in your home.

Run:   python serve.py --lat 48.2085 --lon 16.3731 --place Vienna --save
Open:  http://localhost:8080  (or http://<this-computer>:8080 from any screen at home)

Positions come from adsb.fi, adsb.lol (in reserve, relay 68) and airplanes.live, tried in that order. A source that
answers "too many requests" or "forbidden" is rested for a while and the next one is used. AvioADSB is the
emergency backup: asked only when all of those fail or rest, at most every 15 s and 90 times a day.
If every source fails, the board keeps getting the last good answer for up to two minutes. Away from home, the owner's
screens also get the low planes only Flightradar24 hears (with a key; see "Flightradar24 fills the gaps").

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
import functools
import gzip
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
import signal
import socket
import sqlite3
import struct
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RELAY_VERSION = 78
BOARD_URL = "https://belstria.github.io/overhead-board/"
PAGE_TTL = 60               # check GitHub for a newer board at most once a minute
SOURCES = [
    # Relay 68: adsb.fi first, adsb.lol in reserve. adsb.lol allows 500 requests a UTC day per address; asked first, it
    # had used them up within hours and rested until midnight, so it wasn't there when adsb.fi failed.
    {"key": "adsbfi", "name": "adsb.fi", "url": "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}"},
    {"key": "adsblol", "name": "adsb.lol", "url": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}", "allow": 500},
    {"key": "airplaneslive", "name": "airplanes.live", "url": "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}"},
    # Emergency only (relay 36): its free anonymous tier allows 1 request per 10 s and 100 a day per network, for
    # personal, non-commercial use (data CC BY 4.0, credited in the boards' About). Asked only once every source above
    # has failed or rests; within its gap it is skipped (not waited for) and the last good answer is served instead.
    {"key": "avioadsb", "name": "AvioADSB", "url": "https://avioadsb.org/v1/point/{lat}/{lon}/{nm}",
     "gap": 15, "day_cap": 90, "max_nm": 100},
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
BOARD_FILE = re.compile(r"^/(?:([a-z0-9-]{1,40})/)?([a-z0-9][a-z0-9._-]{0,60}\.(webmanifest|png|svg|ico|js|wav|css|woff2))$")  # the phone app's icons, its service worker
PACKED_TYPES = ("text/", "application/json", "application/manifest+json", "image/svg+xml")   # worth packing (relay 54)
FILE_TYPES = {"webmanifest": "application/manifest+json", "png": "image/png", "svg": "image/svg+xml", "ico": "image/x-icon", "js": "text/javascript; charset=utf-8", "wav": "audio/wav",
              "css": "text/css; charset=utf-8", "woff2": "font/woff2"}   # relay 54: the typefaces (fonts/)
CONFIG_FILE = Path(__file__).with_name("overhead.json")   # your saved settings; stays on this computer
SAVED_KEYS = ("lat", "lon", "place", "home", "radius", "units", "sound", "port", "source", "fr24_key", "fr24_budget", "fr24_reset_day", "fr24_budget_promo", "fr24_promo_until", "public_url", "allow_host")
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
FR24_REUSE_S = 6 * 3600     # relay 45: an answer serves the same aircraft and callsign all day, or this long past midnight
FR24_EDGE = 0.75            # relay 45: a sighting that stayed in the outer quarter of the radius isn't looked up
FILL_AWAY_KM = 30           # relay 66: Flightradar24 fills in what the free sources miss only this far from home,
FILL_KM = 20                # ... asked about a box this far each way (the radius and a minute's flying: details come first)
FILL_FT = 10000             # ... for planes up to this high (the free networks hear the higher ones; relay 67: from 15,000)
FILL_EVERY_S = 30           # ... every 30 s while a screen looks on; every 15 s while a plane it added is within GAME_KM
FILL_FAST_S = 15            #     (relay 67: from 20 and 10 s; an answer costs 6 credits for each plane in it)
FILL_SLOW_S = 300           # ... and every 5 min once 20 answers in a row (ten minutes) had nothing the free sources lacked
FILL_MAX = 10               # ... at most this many planes an answer (6 credits each, 1 for none)
FILL_SHARE = 0.8            # ... and only while the profile has spent less than this part of its daily credits
AIRPORTS_CSV = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
AIRPORTS_FILE = DATA_DIR / "airports.json"
# Relay 68: airline names by ICAO code, from Virtual Radar Server's standing data (public domain), for the flights the
# route database has no route for (it brings the airline only with one). Refreshed weekly; the old copy stays on a failure.
AIRLINES_CSV = "https://raw.githubusercontent.com/vradarserver/standing-data/main/airlines/schema-01/airlines.csv"
AIRLINES_FILE = DATA_DIR / "airlines.json"
AIRLINES_EVERY_S = 7 * 86400
RUNWAYS_CSV = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/runways.csv"
CITY_FIX = {"SAW": "Istanbul", "NCL": "Newcastle", "STN": "London", "LGW": "London", "LTN": "London", "BVA": "Paris",
            "CRL": "Brussels", "NYO": "Stockholm", "BGY": "Milan", "MXP": "Milan", "LIN": "Milan", "CIA": "Rome", "FCO": "Rome"}
ICAO_FOR = {"VIE": "LOWW", "BTS": "LZIB", "GRZ": "LOWG", "LNZ": "LOWL", "SZG": "LOWS", "INN": "LOWI", "KLU": "LOWK",
            "MUC": "EDDM", "FRA": "EDDF", "ZRH": "LSZH", "BUD": "LHBP", "PRG": "LKPR", "LHR": "EGLL", "AMS": "EHAM"}

ARGS = None
STARTED = time.time()
STATE = {s["key"]: {"ok": 0, "fail": 0, "strikes": 0, "cooldown_until": 0.0, "last_status": None,
                    "last_error": "", "last_ok": 0.0, "last_call": 0.0, "day": "", "used": 0,
                    "askedDay": "", "asked": 0} for s in SOURCES}      # relay 69: requests this UTC day, for the owner's panel
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


def rest_for(status, strikes, retry_after, reset=None):
    if reset:       # relay 66: a day's allowance is gone (adsb.lol: 500 an address); rest until it starts again
        try:
            s = float(reset)
            s = s - time.time() if s > 1e9 else s     # a time, or seconds from now
            return int(max(60, min(86400, s + 30)))
        except ValueError:
            pass
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
            cap = src.get("day_cap")
            if cap:                               # a daily allowance (AvioADSB counts its day in UTC)
                day = time.strftime("%Y-%m-%d", time.gmtime())
                if st.get("day") != day:
                    st["day"], st["used"] = day, 0
                if st["used"] >= cap:
                    tried.append(f"{src['name']} used up for today")
                    continue
            wait = st.get("last_call", 0.0) + src.get("gap", SOURCE_GAP_S) - time.time()
            if wait > 0 and src.get("gap"):       # a slow backup: don't hold every screen up, try again later
                tried.append(f"{src['name']} waiting {int(wait) + 1} s")
                continue
            if wait > 0:                          # another place was just asked for; space the calls out
                time.sleep(wait)
            if cap:
                st["used"] += 1
            utc = time.strftime("%Y-%m-%d", time.gmtime())
            if st["askedDay"] != utc:
                st["askedDay"], st["asked"] = utc, 0
            st["asked"] += 1
            t0 = time.time()
            status, _, body, headers = fetch(src["url"].format(lat=lat, lon=lon, nm=min(int(nm), src.get("max_nm", 999))))
            st["last_call"] = time.time()
            if cap and headers and str(headers.get("X-RateLimit-Remaining", "")).strip() == "0":
                st["used"] = cap                  # its own count says the day's allowance is gone
            ms = int((time.time() - t0) * 1000)
            count, problem = None, ""
            if 200 <= status < 300:
                body = AT_CS.sub(b'"flight":""', body)      # relay 70: a blank callsign comes as "@@@@@@@@"
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
            out = status == 429 and headers and str(headers.get("X-RateLimit-Remaining", "")).strip() == "0"
            rest = rest_for(status, st["strikes"], headers.get("Retry-After") if headers else None,
                            headers.get("X-RateLimit-Reset") if out else None)
            st["cooldown_until"] = time.time() + rest
            event("warn", f"{src['name']} failed ({problem}); resting it for " +
                  (f"{rest // 3600} h {rest % 3600 // 60} min, until its allowance starts again" if rest >= 3600 else f"{rest} s"))
            tried.append(f"{src['name']} {problem}")
        _health_seen["posFail"] = time.time()     # relay 45: every source failed (or rested) for this request
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
_dirty = set()             # relay-wide files to write: "fr24", "profiles", "facts" (relay 74)
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
    """Today's sightings and the lifetime logbook of one profile. `center()` says where it is (None: unknown) and
    `radius()` how far around it planes count."""

    def __init__(self, folder, center, radius):
        self.dir, self.center, self.radius = folder, center, radius
        self.day = None
        self.entries = []       # today's sightings, newest first
        self.by_hex = {}        # hex -> its latest entry today
        self.logbook = None
        self.rev = 0
        self.dirty = set()
        self.last_body = None
        self.days = {}          # relay 68: older days changed after the fact (day -> entries), written by the saver

    def day_entries(self, day):
        """The sightings of a saved day: today's live list, a changed day still to write, or the file."""
        if day == self.day:
            return self.entries
        if day in self.days:
            return self.days[day]
        return _load(self.dir / f"sightings-{day}.json", [])

    def day_changed(self, day, entries):
        if day == self.day:
            self.changed("day")
            return
        self.days[day] = entries
        _place_days.pop((str(self.dir), day), None)
        self.changed()

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
                                                                       "gameV": GAME_V, "recordsV": 1, "trophiesV": TROPHIES_V, "cardsV": 1}
            if self.logbook.get("gameV") != GAME_V:
                self.ensure_day()
                _rescore(self)
            if self.logbook.get("recordsV") != 1:
                self.ensure_day()
                _backfill_records(self)
            if self.logbook.get("trophiesV") != TROPHIES_V:
                self.ensure_day()
                _backfill_trophies(self)
            if self.logbook.get("cardsV") != 1:
                self.ensure_day()
                _backfill_cards(self)
            if self.logbook.get("flightsV") != 1:
                self.ensure_day()
                _backfill_flights(self)
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
        for day, entries in self.days.items():
            out.append((self.dir / f"sightings-{day}.json", json.dumps(entries, separators=(",", ":"))))
        self.days = {}
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
            return
        if _dist_km(lat, lon, c[0], c[1]) + radius > int(nm) * 1.852 + 1:
            return                          # looking somewhere else: nothing to count for this spot
        data = json.loads(body)
        planes = data.get("ac", data.get("aircraft"))
        if isinstance(planes, list):
            self.record(planes, c[0], c[1], key, radius)


_guest_spots = {}


def all_spots():
    return list(_guest_spots.values())


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
    if key == "live":
        radius = max(radius, GAME_KM)       # relay 59: the game's circle is the same for everyone
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
            if e and key == "live" and d < e.get("liveMin", 999):
                e["liveMin"] = round(d, 2)          # relay 59: how close the phone following its owner saw it (the game)
            if e and key == "live":
                e["liveSeen"] = now
                changed |= game_note(self, e)
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
                cs = no_cs(ac.get("flight"))
                flags = ac.get("dbFlags") or 0
                e = {"id": f"{hx}-{int(now)}", "ts": int(now * 1000), "time": time.strftime("%H:%M"), "hex": hx,
                     "callsign": cs, "reg": ac.get("r") or "", "typeCode": str(ac.get("t") or "").upper(),
                     "desc": ac.get("desc") or "", "minDist": round(d, 2), "altAtMin": alt,
                     "maxSpeed": round(ac.get("gs") or 0), "lastSeen": now,
                     "pos": [round(la, 4), round(lo, 4), ac.get("track")],
                     "military": bool(flags & 1), "interesting": bool(flags & 2), "emergency": _emergency(ac),
                     "adsbCat": str(ac.get("category") or "")}
                if ac.get("src") == "fr24":
                    e["src"] = "fr24"               # relay 66: only Flightradar24 had it (the gap filler)
                if key != "home":
                    e["place"] = key
                if key == "live":
                    e["liveMin"], e["liveSeen"] = round(d, 2), now
                    e["at"] = [round(lat, 2), round(lon, 2)]     # relay 63: where the phone was (to about a km), for its name
                    where_name(lat, lon)
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
                    _note_first(book.setdefault("flights", {}), cs, "", e, "newFlight", learning)   # relay 38
                score(book, e, self.day)
                note_records(book, e)
                hrs = set(book.get("hours", []))
                if _hour(e) not in hrs:
                    book["hours"] = sorted(hrs | {_hour(e)})
                for k in trophy_check(book, e, self.entries):
                    event("info", f"Trophy won: {k}", echo=False)
                if key == "live":
                    game_note(self, e)
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


# Trophies (relay 29): won once and kept for good (nothing resets), each with the day it was won. Relay 50 (to-do #55):
# more of them, most in tiers (100, 1,000, 10,000 planes ...), and the counts behind them for the boards' progress bars.
TROPHIES_V = 2                 # an older logbook wins the new ones once from its saved days (keeping what it has)
TROPHY_LADDER = {              # id: (what is counted, how many)
    "century": ("planes", 100), "thousand": ("planes", 1000), "planes10k": ("planes", 10000), "planes50k": ("planes", 50000),
    "planes100k": ("planes", 100000),
    "types50": ("types", 50), "types100": ("types", 100), "types150": ("types", 150), "types200": ("types", 200),
    "airlines25": ("airlines", 25), "airlines50": ("airlines", 50), "airlines100": ("airlines", 100), "airlines150": ("airlines", 150),
    "regs1k": ("regs", 1000), "regs5k": ("regs", 5000), "regs10k": ("regs", 10000),
    "countries10": ("countries", 10), "countries25": ("countries", 25), "countries50": ("countries", 50),
    "points1k": ("points", 1000), "points10k": ("points", 10000), "points100k": ("points", 100000),
    "legend10": ("legendary", 10), "legend100": ("legendary", 100), "legend500": ("legendary", 500),
    "busyday": ("today", 100), "busy300": ("today", 300), "busy500": ("today", 500),
    "oldfriend": ("friend", 25), "regular100": ("friend", 100),
    "streak7": ("streak", 7), "streak30": ("streak", 30),
}
TROPHY_IDS = list(TROPHY_LADDER) + ["a320fam", "giants", "jumbochopper", "nightowl", "aroundclock", "lowpass", "bullseye",
                                    "stratos", "specialday", "daytypes40", "dayairlines40", "beluga", "antonov", "allsets",
                                    "bingo", "fullcard"]
A320_FAMILY = ("A319", "A320", "A321")


def _hour(e):
    return time.localtime((e.get("ts") or 0) / 1000).tm_hour


def trophy_counts(book, day_entries=None, day=None):
    """What the tiers count, as the logbook has it now (also the boards' progress bars)."""
    regs = book.get("regs", {})
    return {"planes": book.get("sightings", 0), "types": len(book.get("types", {})), "airlines": len(book.get("airlines", {})),
            "regs": len(regs), "countries": len(book.get("countries", {})), "points": book.get("points", 0),
            "legendary": book.get("tiers", {}).get("legendary", 0), "today": len(day_entries or []),
            "friend": max((r.get("count", 0) if isinstance(r, dict) else r for r in regs.values()), default=0),
            "streak": _streak(book, day or board_day())}


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
                "regs": book.get("regs", {}), "hours": set(book.get("hours", [])), "countries": book.get("countries", {}),
                "points": book.get("points", 0), "legendary": book.get("tiers", {}).get("legendary", 0)}
    types = c["types"]
    r = c["regs"].get(e.get("reg") or "")
    have = {"planes": c["n"], "types": len(types), "airlines": len(c["airlines"]), "regs": len(c["regs"]),
            "countries": len(c.get("countries") or ()), "points": c.get("points", 0), "legendary": c.get("legendary", 0),
            "today": len(day_entries), "friend": (r.get("count", 0) if isinstance(r, dict) else r) if r else 0,
            "streak": c["streak"] if "streak" in c else _streak(book, board_day())}
    for k, (what, n) in TROPHY_LADDER.items():
        win(k, have[what] >= n)
    win("a320fam", all(t in types for t in A320_FAMILY) and any(t in types for t in ("A20N", "A21N", "A19N")))
    win("giants", "A388" in types and any(t.startswith("B74") for t in types))
    win("jumbochopper", any(str(x.get("typeCode") or "").startswith("B74") for x in day_entries)
        and any(category_of(x) == "helicopter" for x in day_entries))
    win("nightowl", 1 <= _hour(e) <= 3)
    win("aroundclock", len(c["hours"]) >= 24)
    win("specialday", sum(1 for x in day_entries if x.get("tier") == "legendary") >= 3)
    if len(day_entries) >= 40:
        win("daytypes40", len({_tc(x) for x in day_entries} - {""}) >= 40)
        win("dayairlines40", len({_al(x) for x in day_entries} - {""}) >= 40)
    win("beluga", _tc(e) in ("A3ST", "A337"))
    win("antonov", _tc(e) in ("A124", "A225", "AN22"))
    win("allsets", all(all(t in types for t in ts) for _, ts in SETS))
    trophy_pass(book, e, got, won)
    return won


def trophy_pass(book, e, got=None, won=None):
    """The trophies of how close or low a pass came (they can still be won as the plane comes closer)."""
    got = got if got is not None else book.setdefault("trophies", {})
    ts = e.get("ts") or int(time.time() * 1000)
    alt, d = e.get("altAtMin"), e.get("minDist")
    for k, ok in (("lowpass", isinstance(alt, (int, float)) and 100 <= alt < 1500 and d is not None and d <= 2),
                  ("bullseye", d is not None and d <= 0.3),
                  ("stratos", isinstance(alt, (int, float)) and alt >= 43000 and d is not None and d <= 2)):
        if ok and k not in got:
            got[k] = ts
            if won is not None:
                won.append(k)


def _backfill_flights(spot):
    """Relay 38 counts airline flight numbers (callsigns) like types and aircraft; an older logbook learns them once
    from its saved days, so "first time" for a flight means it."""
    b = spot.logbook
    flights = b["flights"] = {}
    for f in sorted(spot.dir.glob("sightings-*.json")):
        day = f.stem[len("sightings-"):]
        for e in reversed(spot.entries if day == spot.day else _load(f, [])):
            cs = str(e.get("callsign") or "").strip().upper()
            if re.match(r"^[A-Z]{3}\d", cs):
                it = flights.get(cs)
                ts = e.get("ts") or 0
                if it is None:
                    flights[cs] = {"name": "", "first": ts, "count": 1, "last": ts}
                else:
                    it["count"] += 1
                    it["prev"], it["last"] = it["last"], ts
    b["flightsV"] = 1
    spot.changed("book")


def _backfill_trophies(spot):
    """An older logbook: win its trophies once from the saved days, on the day they were earned (relay 50: keeping the
    ones it has, and learning the countries its aircraft are registered in)."""
    b = spot.logbook
    b["trophies"], hours = b.get("trophies") or {}, set()
    countries = {}
    ctx = {"n": 0, "types": {}, "airlines": {}, "regs": collections.Counter(), "hours": hours, "countries": countries,
           "points": 0, "legendary": 0, "streak": 0}
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
            if e.get("ownerCountry") and e["ownerCountry"] not in countries:
                countries[e["ownerCountry"]] = e.get("ts") or 0
            ctx["points"] += TIER_POINTS.get(e.get("tier"), 0)
            ctx["legendary"] += e.get("tier") == "legendary"
            hours.add(_hour(e))
            so_far.append(e)
            trophy_check(b, e, so_far, ctx)
    rd = sorted(b.get("rareDays", []))
    run = 0
    for i, d in enumerate(rd):
        run = run + 1 if i and datetime.date.fromisoformat(d) - datetime.date.fromisoformat(rd[i - 1]) == datetime.timedelta(days=1) else 1
        for k, n in (("streak7", 7), ("streak30", 30)):
            if run >= n and k not in b["trophies"]:
                b["trophies"][k] = int(datetime.datetime.fromisoformat(d + "T20:00").timestamp() * 1000)
    b["hours"] = sorted(hours)
    b["countries"] = {**countries, **(b.get("countries") or {})}
    b["trophiesV"] = TROPHIES_V
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


def _bingo_week(spot, monday, day, live=False):
    """A week's card and which of its goals were done (and when), up to `day`. `live`: only planes that scored in the
    game (relay 59)."""
    card = random.Random("fallblatt-" + monday.isoformat()).sample(sorted(BINGO), 9)
    done = {}
    for i in range(7):
        d = (monday + datetime.timedelta(days=i)).isoformat()
        if d > day:
            break
        entries = spot.entries if d == spot.day else _load(spot.dir / f"sightings-{d}.json", [])
        for e in reversed(entries):
            if live and "gp" not in e:
                continue
            for g in card:
                if g not in done:
                    try:
                        if BINGO[g](e):
                            done[g] = e.get("ts")
                    except Exception:
                        pass
    return card, done


def _backfill_cards(spot):
    """Relay 51 (to-do #66): the weeks whose bingo card was full, counted once from the saved days (they unlock the
    title badges)."""
    b = spot.logbook
    cards = b.setdefault("bingoCards", {})
    days = sorted(f.stem[len("sightings-"):] for f in spot.dir.glob("sightings-*.json"))
    mondays = sorted({(datetime.date.fromisoformat(d) - datetime.timedelta(days=datetime.date.fromisoformat(d).weekday())) for d in days})
    for monday in mondays:
        _, done = _bingo_week(spot, monday, (monday + datetime.timedelta(days=6)).isoformat())
        if len(done) == 9 and monday.isoformat() not in cards:
            cards[monday.isoformat()] = max(v or 0 for v in done.values())
    b["cardsV"] = 1
    spot.changed("book")


def bingo_json(spot, day):
    """This week's card: its nine goals, which are done (and when), and how many lines are complete."""
    monday = datetime.date.fromisoformat(day) - datetime.timedelta(days=datetime.date.fromisoformat(day).weekday())
    key = (monday.isoformat(), day, spot.rev)
    cached = getattr(spot, "_bingo", None)
    if cached and cached[0] == key:
        return cached[1]
    card, done = _bingo_week(spot, monday, day, live=True)
    lines = sum(1 for ln in BINGO_LINES if all(card[i] in done for i in ln))
    book = game_book(spot.book())           # relay 59: the game's card, from live planes only
    if len(done) == 9 and monday.isoformat() not in book.setdefault("bingoCards", {}):     # relay 51: full cards
        book["bingoCards"][monday.isoformat()] = max(v or 0 for v in done.values())
        spot.changed("book")
    got = book.setdefault("trophies", {})
    now = int(time.time() * 1000)
    for k, ok in (("bingo", lines >= 1), ("fullcard", len(done) == 9)):
        if ok and k not in got:
            got[k] = now
            spot.changed("book")
    nxt = datetime.datetime.combine(monday + datetime.timedelta(days=7), datetime.time(DAY_STARTS_H))
    out = {"week": monday.isoformat(), "card": card, "done": done, "lines": lines, "resets": int(nxt.timestamp() * 1000)}
    spot._bingo = (key, out)
    return out


# Styles the owner can grant by hand (relay 52): the ones with an unlock rule on the board, [id, name].
STYLE_GRANTS = [("heathrow", "Heathrow yellow"), ("solari", "Solari green"), ("ice", "Ice blue"), ("sunset", "Sunset"),
                ("white", "Black on white"), ("brass", "Brass trim"), ("enamel", "Worn enamel"), ("led", "LED dots"),
                ("star", "Star"), ("prop", "Propeller"), ("heli", "Helicopter"), ("jumbo", "Jumbo"), ("jet", "Fighter jet"),
                ("concorde", "Concorde"), ("frankfurt70", "Frankfurt 1970s"), ("tokyo", "Tokyo night"), ("goldleaf", "Gold leaf"),
                ("firstclass", "First Class")]


def style_grants(p):
    """A profile's hand-granted styles: "all", or a list of ids (relay 52); the board counts them like earned ones."""
    g = (p or {}).get("styleGrants")
    if g == "all":
        return "all"
    ids = {i for i, _ in STYLE_GRANTS}
    return [i for i in g if i in ids] if isinstance(g, list) else []


def game_json(book, day):
    days = book.get("days", {})
    best = max(days.items(), key=lambda kv: kv[1]) if days else None
    streak = _streak(book, day)
    have = book.get("types", {})
    return {"points": book.get("points", 0), "today": days.get(day, 0), "best": {"day": best[0], "points": best[1]} if best else None,
            "streak": streak, "tiers": {t: book.get("tiers", {}).get(t, 0) for t in TIERS},
            "sets": [{"name": n, "have": [t for t in ts if t in have], "total": len(ts)} for n, ts in SETS],
            "trophies": book.get("trophies", {}), "trophyCounts": trophy_counts(book, day=day),
            "bingoCards": len(book.get("bingoCards", {}))}


# ---------- the game since relay 59 (1.72): only planes spotted with live location score ----------
# A plane scores once a pass, the first time a phone following its owner (place "live") sees it within GAME_KM, the
# same circle for everyone whatever their radius. Relay 76 (1.96, to-do #127, Dave's rules): passively a tenth of its
# rarity's points (TIER_BASE), for up to GAME_LIMIT planes of each rarity a day; Sky view's scan tops the plane up to its
# full points, without a limit, and only scans earn the extras (a type or an airline new to the game) and the week's
# daily streak. Everything of the game (points, collections, bingo, trophies, records) lives in the logbook's "game3"
# part, a small logbook of its own that started empty; the logbook keeps every plane. Never raise GAME3_V: that empties
# everyone's game.
GAME3_V = 1
GAME_KM = 10                # relay 60: 10 km (8 in relay 59)
GAME_RULE = 2               # relay 76: the rule a plane was scored by (e["gr"], each award's "r"); rule 1's stay as they were
TIER_BASE = {"common": 10, "uncommon": 30, "rare": 100, "epic": 250, "legendary": 500}
GAME_PASSIVE = 10           # a plane within GAME_KM: a tenth of its points
GAME_LIMIT = {"common": 50, "uncommon": 30, "rare": 15, "epic": 5, "legendary": 3}    # passive planes a day per rarity
GAME_NEW = (("type", 50), ("airline", 25))          # at the first scan of a type or an airline new to the game
GAME_STREAK = 25            # the day's first scan: +25 × the day of the week's streak (25 … 175)
GAME1_NEW = (("gNewType", 50), ("gNewAirline", 25), ("gNewReg", 5))   # rule 1's extras (Recent points of the switch day)
LOCK_FRESH_S = 120          # a scan counts for a plane seen live this recently
LEVEL_TITLES = ["Plane Watcher", "Window Spotter", "Fence Spotter", "Logkeeper", "Tail Reader", "Contrail Chaser", "Cadet",
                "Second Officer", "First Officer", "Senior First Officer", "Captain", "Senior Captain", "Training Captain",
                "Check Captain", "Fleet Captain", "Chief Pilot", "Wing Commander", "Air Commodore", "Ace", "Legend"]


def game_book(book):
    """The game's own small logbook inside the logbook (made empty the first time: the reset of relay 59). Its keys are
    the logbook's, so trophies, records, sets and the streak work on it unchanged; its "rareDays" are the days with a
    live plane. Relay 76: "scanned" holds the types and airlines that earned their extra with a scan (those the game
    knew before count as had); "scanDays" the days with a scan (the daily streak); "limits" today's planes by rarity."""
    g = book.get("game3")
    if not isinstance(g, dict) or g.get("v") != GAME3_V:
        g = book["game3"] = {"v": GAME3_V, "since": int(time.time() * 1000), "sightings": 0, "types": {}, "airlines": {},
                             "regs": {}, "countries": {}, "categories": {}, "hours": [], "points": 0, "days": {}, "planes": {},
                             "tiers": {}, "rareDays": [], "records": {}, "trophies": {}, "bingoCards": {}, "best": {},
                             "lock": {"at": 0, "n": 0}}
    if "scanned" not in g:
        g["scanned"] = {"types": sorted(g.get("types") or {}), "airlines": sorted(g.get("airlines") or {})}
        g["rule2"] = int(time.time() * 1000)
    return g


def _monday(day):
    d = datetime.date.fromisoformat(day)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def _scan_streak(g, day):
    """Relay 76: the daily streak: the days in a row with a Sky view scan, back from today (from yesterday while today
    has none yet), counted from this week's Monday on (it starts again with the league)."""
    rd, wk, n = set(g.get("scanDays") or []), _monday(day), 0
    d = datetime.date.fromisoformat(day)
    if day not in rd:
        d -= datetime.timedelta(days=1)
    while d.isoformat() >= wk and d.isoformat() in rd:
        n += 1
        d -= datetime.timedelta(days=1)
    return n


def _game_limits(g, day):
    """Relay 76: today's planes by rarity that came within GAME_KM (the passive limits count them), {tier: n}."""
    lim = g.get("limits") or {}
    return lim.get("n", {}) if lim.get("day") == day else {}


def _next_day_ms(day):
    """When the game day after `day` starts (03:00), in ms."""
    nxt = datetime.datetime.combine(datetime.date.fromisoformat(day) + datetime.timedelta(days=1), datetime.time(DAY_STARTS_H))
    return int(nxt.timestamp() * 1000)


def game_rules():
    """Relay 76: the rules for the app (one source for the points it shows)."""
    return {"base": TIER_BASE, "passive": {t: v // GAME_PASSIVE for t, v in TIER_BASE.items()}, "limit": GAME_LIMIT,
            "new": dict(GAME_NEW), "streak": GAME_STREAK, "km": GAME_KM}


def level_of(points):
    """The level for a points total: each level needs a quarter more than the one before (500, 625, ...), from level
    20 on the same as level 20. Returns (level, title, points into it, points it needs)."""
    lv, need, left = 1, 500.0, max(0, int(points))
    while left >= round(need):
        left -= round(need)
        lv += 1
        if lv < 20:
            need *= 1.25
    title = LEVEL_TITLES[lv - 1] if lv <= 20 else f"Legend {lv - 19}"
    return lv, title, left, round(need)


def _game_add(g, day, pts):
    g["points"] = g.get("points", 0) + pts
    days = g.setdefault("days", {})
    days[day] = days.get(day, 0) + pts
    for k in sorted(days)[:-400]:
        del days[k]


def game_note(spot, e):
    """A live sighting came within GAME_KM or closer: score it the first time (relay 76: a tenth of its points, or
    nothing past its rarity's limit for the day). A plane already scored is never priced again (rule 1's planes neither:
    their points stay); a closer look still counts for the records and the trophies of a pass. Call under _data_lock.
    True when something changed."""
    d = e.get("liveMin")
    if d is None or d > GAME_KM:
        return False
    book, day = spot.book(), spot.day
    g = game_book(book)
    if "gp" not in e:
        planes = g.setdefault("planes", {})
        n = planes[day] = planes.get(day, 0) + 1
        for k in sorted(planes)[:-400]:
            del planes[k]
        rd = g.setdefault("rareDays", [])
        if day not in rd:
            rd.append(day)
            del rd[:-400]
        g["sightings"] = g.get("sightings", 0) + 1
        cats = g.setdefault("categories", {})
        cat = category_of(e)
        cats[cat] = cats.get(cat, 0) + 1
        if e.get("typeCode"):
            _note_first(g["types"], e["typeCode"], e.get("desc") or "", e, "gNewType")
        if e.get("reg"):
            _note_first(g["regs"], e["reg"], e.get("typeCode") or "", e, "gNewReg")
        m = re.match(r"^([A-Z]{3})\d", e.get("callsign") or "")
        if m:
            _note_first(g["airlines"], m.group(1), "", e, "gNewAirline")
        tier = e.get("tier") if e.get("tier") in TIER_BASE else "uncommon"
        tiers = g.setdefault("tiers", {})
        tiers[tier] = tiers.get(tier, 0) + 1
        hrs = set(g.get("hours", []))
        if _hour(e) not in hrs:
            g["hours"] = sorted(hrs | {_hour(e)})
        lim = g.get("limits") or {}
        if lim.get("day") != day:
            lim = g["limits"] = {"day": day, "n": {}}
        k = lim["n"][tier] = lim["n"].get(tier, 0) + 1
        e["gr"], e["gn"], e["gt"], e["gMin"] = GAME_RULE, n, k, d
        if k <= GAME_LIMIT[tier]:
            e["gp"] = TIER_BASE[tier] // GAME_PASSIVE
            _game_award(e, "pass", e["gp"], tier=tier, n=k)
        else:
            e["gp"] = 0                         # past the limit: listed, with the reason; only the first one pops up
            _game_award(e, "limit", 0, tier=tier, n=k, first=k == GAME_LIMIT[tier] + 1)
        _game_add(g, day, e["gp"])
        note_records(g, e)
        for t in trophy_check(g, e, [x for x in spot.entries if "gp" in x]):
            event("info", f"Trophy won: {t}", echo=False)
        _game_best(g, day, e)
    else:
        if d >= e.get("gMin", 99) - 0.05:
            return False
        e["gMin"] = d
        note_records(g, e)
        trophy_pass(g, e)
    spot.changed("book")
    return True


def _game_award(e, kind, pts, **more):
    """Relay 71: what a sighting scored and when, for the app's Recent points and (relay 76) its pop-ups. Relay 76's
    kinds: "pass" (the passive tenth), "limit" (nothing: past the rarity's limit), "scan" (Sky view's top-up), "new" (a
    type or an airline at its first scan), "streak" (the day's first scan); each with its rule ("r"). Rule 1's were
    "first", "close", "fix" and "lock"."""
    a = {"t": int(time.time() * 1000), "k": kind, "p": pts, "r": GAME_RULE, **more}
    if kind in ("pass", "limit") and e.get("liveMin") is not None:
        a["d"] = round(e["liveMin"], 1)
    aw = e.setdefault("ga", [])
    aw.append(a)
    del aw[:-8]


PLANE_KEYS = ("hex", "callsign", "flightIata", "airlineIata", "airlineName", "reg", "typeCode", "desc", "aircraftType", "manufacturer")


def game_today(spot):
    """Relay 71: today's scored planes for the app's Recent points, newest award first: the plane, its total and its
    awards. Sightings scored before relay 71 have no awards (only their totals); rule 1's (before relay 76) keep their
    reasons (base, new, gk, gn)."""
    with _data_lock:
        spot.ensure_day()
        g = game_book(spot.book())
        day = spot.day
        rows = [e for e in spot.entries if "gp" in e]
        total, planes = g.get("days", {}).get(day, 0), g.get("planes", {}).get(day, 0)
        lim = _game_limits(g, day)
        out = []
        for e in rows:
            aw = [dict(a) for a in e.get("ga") or []]
            # the fields the boards' fromRelay() names a plane from, so it reads as in Spotted today
            r = {**{k: e.get(k) or "" for k in PLANE_KEYS}, "tier": e.get("tier") or "", "km": e.get("liveMin"),
                 "gp": e["gp"], "lock": e.get("lock", 0), "gs": e.get("gs", 0), "rule": e.get("gr", 1), "ts": e.get("ts"), "aw": aw}
            if r["rule"] < GAME_RULE:
                r.update(base=TIER_BASE.get(e.get("tier"), 30), new=[[k[4:].lower(), v] for k, v in GAME1_NEW if e.get(k)],
                         gk=e.get("gk") or 1.0, gn=e.get("gn") or 1)
            out.append(r)
    out.sort(key=lambda r: max([a["t"] for a in r["aw"]] or [r["ts"] or 0]), reverse=True)
    return {"day": day, "today": total, "planes": planes, "rows": out, "limits": {t: [lim.get(t, 0), GAME_LIMIT[t]] for t in TIERS},
            "resets": _next_day_ms(day)}


def game_awards(spot, since):
    """Relay 76: today's awards after `since` (ms), oldest first, with their plane: the app's pop-ups (/game/me)."""
    out = []
    for e in spot.entries:
        for a in e.get("ga") or []:
            if a.get("t", 0) > since and a.get("r") == GAME_RULE:
                out.append({**a, **{k: e.get(k) or "" for k in PLANE_KEYS}, "km": e.get("liveMin")})
    out.sort(key=lambda a: a["t"])
    return out[-20:]


def _game_best(g, day, e):
    """The week's best plane (the board's league shows it): its points without the streak."""
    wk, total = _monday(day), e["gp"] + e.get("lock", 0)
    best = g.setdefault("best", {})
    if total > (best.get(wk) or {}).get("pts", 0):
        best[wk] = {"pts": total, "type": e.get("typeCode") or "", "flight": e.get("callsign") or "", "ts": e.get("ts")}
        for k in sorted(best)[:-12]:
            del best[k]


def game_lockon(spot, hx):
    """Sky view held a plane in its ring for 1.5 s: the scan (relay 76). Once a pass, for a plane that came within
    GAME_KM and was seen live a moment ago, without a limit: it tops the plane up to its full points; a type or an airline
    new to the game adds its extra, and the day's first scan the daily streak (+25 × the day of the week's streak)."""
    now = time.time()
    with _data_lock:
        spot.ensure_day()
        e = spot.by_hex.get(str(hx or "").lower())
        if not e or "gp" not in e:
            return {"bonus": 0, "why": "far"}
        if now - e.get("liveSeen", 0) > LOCK_FRESH_S:
            return {"bonus": 0, "why": "gone"}
        if e.get("lock") or e.get("scan"):
            return {"bonus": 0, "why": "done", "had": e.get("lock", 0)}
        g, day = game_book(spot.book()), spot.day
        tier = e.get("tier") if e.get("tier") in TIER_BASE else "uncommon"
        full = TIER_BASE[tier]
        lines = [{"k": "scan", "p": max(0, full - e["gp"]), "tier": tier, "full": full, "had": e["gp"]}]
        sc = g["scanned"]
        tc = e.get("typeCode") or ""
        if tc and tc not in sc["types"]:
            sc["types"].append(tc)
            lines.append({"k": "new", "p": dict(GAME_NEW)["type"], "w": "type", "n": tc})
        m = re.match(r"^([A-Z]{3})\d", e.get("callsign") or "")
        if m and m.group(1) not in sc["airlines"]:
            sc["airlines"].append(m.group(1))
            lines.append({"k": "new", "p": dict(GAME_NEW)["airline"], "w": "airline", "n": m.group(1)})
        streak = 0
        sd = g.setdefault("scanDays", [])
        if day not in sd:
            streak = _scan_streak(g, day) + 1
            sd.append(day)
            del sd[:-60]
            lines.append({"k": "streak", "p": GAME_STREAK * streak, "n": streak})
        for a in lines:
            _game_award(e, a["k"], a["p"], **{k: v for k, v in a.items() if k not in ("k", "p")})
        bonus = sum(a["p"] for a in lines)
        e["scan"] = int(now * 1000)
        e["gs"] = GAME_STREAK * streak
        e["lock"] = bonus - e["gs"]
        L = g.setdefault("lock", {"at": 0, "n": 0})
        L.update(at=now, n=L.get("n", 0) + 1, last={"ts": int(now * 1000), "flight": e.get("callsign") or "",
                                                     "type": e.get("typeCode") or "", "pts": e["lock"]})
        _game_add(g, day, bonus)
        _game_best(g, day, e)
        spot.changed("book", "day")
        lv = level_of(g["points"])
        return {"bonus": bonus, "lines": lines, "tier": tier, "full": full, "had": e["gp"], "streak": streak,
                "points": g["points"], "level": lv[0], **{k: e.get(k) or "" for k in PLANE_KEYS}, "km": e.get("liveMin")}


def game3_json(book, day):
    """The game for the boards: game_json's shape on the game's own logbook, with the level and this week; relay 76: the
    daily streak is the week's scan streak, with today's planes by rarity against their limits."""
    g = game_book(book)
    out = game_json(g, day)
    lv, title, into, need = level_of(g.get("points", 0))
    wk = _monday(day)
    days = g.get("days", {})
    week = sum(v for k, v in days.items() if k >= wk)
    L = g.get("lock") or {}
    lim = _game_limits(g, day)
    # relay 64: the week's best plane is weekBest; as "best" it hid game_json's best day, which the boards show
    out.update(v=3, since=g.get("since"), km=GAME_KM, level=lv, title=title, into=into, need=need, week=week,
               planesToday=g.get("planes", {}).get(day, 0), lockons=L.get("n", 0), weekBest=(g.get("best") or {}).get(wk),
               records=g.get("records", {}), streak=_scan_streak(g, day), scannedToday=day in (g.get("scanDays") or []),
               limits={t: [lim.get(t, 0), GAME_LIMIT[t]] for t in TIERS}, resets=_next_day_ms(day), rules=game_rules())
    return out


_league_cache = {}
_LEAGUE_SALT = secrets.token_hex(8)


def _league_id(pid):
    """Relay 63: a league row's handle for its player card; not the profile's id (a fresh salt every start)."""
    return hashlib.sha256((_LEAGUE_SALT + pid).encode()).hexdigest()[:12]


def league_json(me=None):
    """The league (relay 59): every profile that has points and didn't leave it (Settings → Game), this week (Monday
    03:00 on) and all time, by first name; last week's winner wears the crown. Never places."""
    day = board_day()
    wk = _monday(day)
    last = (datetime.date.fromisoformat(wk) - datetime.timedelta(days=7)).isoformat()
    key = (day, int(time.time() // 30))
    rows = _league_cache.get(key)
    if rows is None:
        with _data_lock:
            pids = [(pid, p) for pid, p in profiles()["profiles"].items() if (p.get("settings") or {}).get("league", True) is not False]
        rows = []
        for pid, p in pids:
            try:
                sp = guest_spot(pid)
                with _data_lock:
                    g = (sp.book().get("game3") or {})
            except Exception:
                continue
            if not g.get("points"):
                continue
            days = g.get("days", {})
            rows.append({"pid": pid, "name": (str(p.get("name") or "?").strip().split() or ["?"])[0][:14],
                         "week": sum(v for k, v in days.items() if k >= wk),
                         "before": sum(v for k, v in days.items() if wk <= k < day),
                         "lastWeek": sum(v for k, v in days.items() if last <= k < wk), "all": g.get("points", 0),
                         "level": level_of(g.get("points", 0))[0], "best": (g.get("best") or {}).get(wk),
                         "lock": (g.get("lock") or {}).get("last")})
        _league_cache.clear()
        _league_cache[key] = rows
    champ = max((r for r in rows if r["lastWeek"] > 0), key=lambda r: r["lastWeek"], default=None)
    prev = {r["pid"]: i for i, r in enumerate(sorted((r for r in rows if r["before"] > 0), key=lambda r: -r["before"]))}
    def out(r, i, order):
        o = {"name": r["name"], "points": r[order], "all": r["all"], "level": r["level"], "rank": i + 1,
             "crown": bool(champ and r["pid"] == champ["pid"]), "me": r["pid"] == me, "id": _league_id(r["pid"])}
        if order == "week":
            o["best"] = r["best"]
            if r["pid"] in prev and day != wk:
                o["was"] = prev[r["pid"]] + 1
        return o
    week = [out(r, i, "week") for i, r in enumerate(sorted(rows, key=lambda r: -r["week"])) if r["week"] > 0 or r["pid"] == me]
    alltime = [out(r, i, "all") for i, r in enumerate(sorted(rows, key=lambda r: -r["all"]))]
    lock = max((r["lock"] for r in rows if r.get("lock")), key=lambda x: x.get("ts", 0), default=None)
    if lock:
        lock = {**lock, "name": next(r["name"] for r in rows if r.get("lock") is lock)}
    nxt = datetime.datetime.combine(datetime.date.fromisoformat(wk) + datetime.timedelta(days=7), datetime.time(DAY_STARTS_H))
    return {"week": wk, "resets": int(nxt.timestamp() * 1000), "rows": week, "allTime": alltime, "lastLock": lock,
            "champion": champ["name"] if champ else None, "championMe": bool(champ and champ["pid"] == me)}


def player_json(hid, me=None):
    """Relay 63 (Dave's to-do 6): a league player's card: level, this week and all time, the trophies won (the app
    shows them as medals), how many of each rarity, the rarest type and the week's best plane, the streak. Only for
    players in the league; never places."""
    day = board_day()
    wk = _monday(day)
    with _data_lock:
        pids = [(pid, p) for pid, p in profiles()["profiles"].items() if (p.get("settings") or {}).get("league", True) is not False]
    hit = next(((pid, p) for pid, p in pids if _league_id(pid) == hid), None)
    if not hit:
        return None
    pid, p = hit
    try:
        sp = guest_spot(pid)
    except Exception:
        return None
    with _data_lock:
        g = sp.book().get("game3") or {}
        pts = g.get("points", 0)
        if not pts:
            return None
        lv, title, into, need = level_of(pts)
        days, types = g.get("days", {}), g.get("types") or {}
        rare = lambda tc: TIERS.index(tier_of({}, {"typeCode": tc}))
        top = max(types.items(), key=lambda kv: (rare(kv[0]), -(kv[1].get("first") or 0)), default=None)
        counts = trophy_counts(g, day=day)
        out = {"id": hid, "name": (str(p.get("name") or "?").strip().split() or ["?"])[0][:14], "me": pid == me,
               "level": lv, "title": title, "into": into, "need": need, "points": pts,
               "week": sum(v for k, v in days.items() if k >= wk), "streak": _scan_streak(g, day),
               "tiers": {t: (g.get("tiers") or {}).get(t, 0) for t in TIERS},
               "counts": {k: counts.get(k) for k in ("planes", "types", "airlines", "countries")},
               "trophies": sorted(k for k, v in (g.get("trophies") or {}).items() if v),
               "rarest": {"code": top[0], "name": top[1].get("name") or "", "tier": tier_of({}, {"typeCode": top[0]})} if top else None,
               "best": (g.get("best") or {}).get(wk), "lockons": (g.get("lock") or {}).get("n", 0), "since": g.get("since")}
    lg = league_json(me)
    r = next((x for x in lg["rows"] if x["id"] == hid), None)
    out.update(rank=r["rank"] if r else None, crown=bool(r and r["crown"]))
    return out


_hangar_cache = {}


def hangar_json(spot):
    """Relay 63 (Dave's to-do 4): the Spotters' Club hangar: every type seen, each with the first aircraft of it (since
    relay 64 with its photo and thumbnail) and its rarity, the newest first; and the sets with all their types. Relay 76
    (to-do #127): from the logbook (any sighting, from any screen; it was the game's own logbook), with how often the
    game caught it ("game", 0: never)."""
    with _data_lock:
        book = spot.book()
        game = {tc: (t or {}).get("count", 0) for tc, t in (game_book(book).get("types") or {}).items()}
        types = {tc: dict(t) for tc, t in (book.get("types") or {}).items()}
        for tc in game:
            types.setdefault(tc, dict(game_book(book)["types"][tc]))
    key = (str(spot.dir), len(types), sum(game.values()), spot.day)
    hit = _hangar_cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    want, first = {tc: t.get("first") for tc, t in types.items()}, {}
    for e in _logbook_entries(spot):
        tc = str(e.get("typeCode") or "").upper()
        if tc in want and tc not in first and e.get("ts") == want[tc]:
            first[tc] = e
    out = []
    for tc, t in types.items():
        e = first.get(tc) or {}
        out.append({"code": tc, "name": t.get("name") or "", "first": t.get("first"), "count": t.get("count", 0), "game": game.get(tc, 0),
                    "tier": e.get("tier") or tier_of({}, {"typeCode": tc}), "reg": e.get("reg") or "", "hex": e.get("hex") or "",
                    "flight": e.get("flightIata") or e.get("callsign") or "", "airline": e.get("airlineName") or "",
                    "photo": e.get("photo") or "", "thumb": e.get("photoThumb") or ""})          # relay 64: its own photo, when adsbdb has one
    out.sort(key=lambda x: -(x["first"] or 0))
    res = {"types": out, "sets": [{"name": n, "types": ts} for n, ts in SETS]}
    _hangar_cache.clear()
    _hangar_cache[key] = (time.time(), res)
    return res


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


_airlines = None             # relay 68: {ICAO code: [name, IATA code]} from AIRLINES_CSV, None until loaded


def airline_fields(cs):
    """The airline of an airline-style callsign (AUA411, EIN6AB) from the standing data: {airlineName, airlineIata,
    airlineIcao}, or {} (another kind of callsign, an unknown code, or the table not loaded)."""
    m = re.match(r"^([A-Z]{3})\d", cs or "")
    row = (_airlines or {}).get(m.group(1)) if m else None
    if not row or not row[0]:
        return {}
    out = {"airlineName": row[0], "airlineIcao": m.group(1)}
    if row[1]:
        out["airlineIata"] = row[1]
    return out


def _load_airlines(force=False):
    """The airline table: the copy in data/ while it is under a week old (or the download fails), else downloaded.
    True when it was downloaded now."""
    global _airlines
    db = _load(AIRLINES_FILE, None)
    if isinstance(db, dict) and db.get("v") == 1 and isinstance(db.get("codes"), dict):
        _airlines = db["codes"]
        if not force and time.time() - db.get("fetched", 0) < AIRLINES_EVERY_S:
            return False
    status, _, body, _ = fetch(AIRLINES_CSV, timeout=60)
    codes = {}
    if status == 200:
        for r in csv.DictReader(io.StringIO(body.decode("utf-8-sig", "replace"))):
            icao, name = (r.get("ICAO") or "").strip().upper(), (r.get("Name") or "").strip()
            if re.fullmatch(r"[A-Z]{3}", icao) and name:
                codes[icao] = [name, (r.get("IATA") or "").strip().upper()[:2]]
    if len(codes) < 100:                       # a failed or broken download: keep what we have
        if _airlines is None:
            _airlines = {}
        event("warn", "Couldn't download the airline list" + (f" (HTTP {status})" if status != 200 else "") +
              ("; keeping the copy from before" if _airlines else "; flights without a route show no airline name for now"))
        return False
    _airlines = codes
    try:
        DATA_DIR.mkdir(exist_ok=True)
        tmp = AIRLINES_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"v": 1, "fetched": time.time(), "codes": codes}, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, AIRLINES_FILE)
    except OSError:
        pass
    event("info", f"Airline list ready: {len(codes)} airlines")
    return True


def _airline_fill(e):
    """Give a saved sighting without an airline name the table's. True when it changed."""
    if e.get("airlineName"):
        return False
    add = airline_fields(str(e.get("callsign") or "").strip().upper())
    if not add:
        return False
    for k, v in add.items():
        if not e.get(k):
            e[k] = v
    return True


def _backfill_airlines(spot):
    """Relay 68, once per profile: the sightings and logbook from before the airline list get its names (only the
    airline's name and codes; nothing else in the files changes). Call under _data_lock."""
    b = spot.book()
    n = 0
    for f in sorted(spot.dir.glob("sightings-*.json")):
        day = f.stem[len("sightings-"):]
        entries = spot.day_entries(day)
        hits = sum(1 for e in entries if _airline_fill(e))
        if hits:
            spot.day_changed(day, entries)
            n += hits
    for code, a in (b.get("airlines") or {}).items():
        row = (_airlines or {}).get(code)
        if row and isinstance(a, dict):
            if not a.get("name"):
                a["name"] = row[0]
            if not a.get("iata") and row[1]:
                a["iata"] = row[1]
    b["airlinesV"] = 1
    spot.changed("book")
    return n


AT_CS = re.compile(rb'"flight"\s*:\s*"\s*@+\s*"')


def no_cs(v):
    """A callsign as the sources give it, cleaned. Relay 70: they fill a blank one with "@" ("@@@@@@@@"): no callsign."""
    v = str(v or "").strip().upper()
    return v if v.strip("@") else ""


def _at_cs(v):
    return isinstance(v, str) and bool(v.strip()) and not v.strip().strip("@")


def _scrub_at(o):
    """Relay 70: the all-"@" callsigns saved before, anywhere in a sightings list or logbook: as a "callsign" or "flight"
    value it becomes "", as a key (the logbook's and game's "flights") it goes. Returns how many it changed."""
    n = 0
    if isinstance(o, dict):
        for k in list(o):
            if _at_cs(k):
                del o[k]
                n += 1
            elif k in ("callsign", "flight") and _at_cs(o[k]):
                o[k] = ""
                n += 1
            else:
                n += _scrub_at(o[k])
    elif isinstance(o, list):
        for v in o:
            n += _scrub_at(v)
    return n


def _scrub_at_spot(spot):
    """Once per profile (the logbook's "atCsV"): clean its saved days and logbook of all-"@" callsigns. Call under
    _data_lock."""
    n = 0
    for f in sorted(spot.dir.glob("sightings-*.json")):
        day = f.stem[len("sightings-"):]
        entries = spot.day_entries(day)
        hits = _scrub_at(entries)
        if hits:
            spot.day_changed(day, entries)
            n += hits
    b = spot.book()
    n += _scrub_at(b)
    b["atCsV"] = 1
    spot.changed("book")
    return n


def _scrub_at_all():
    try:
        for sp in _all_profile_spots():
            with _data_lock:
                if sp.book().get("atCsV") != 1:
                    n = _scrub_at_spot(sp)
                    if n:
                        event("info", f"Removed {n} blank (\"@\") callsigns from earlier sightings", echo=False)
    except Exception as e:  # never let the clean-up break the relay
        event("warn", f"Cleaning blank callsigns: {e}")


def _all_profile_spots():
    """Every profile's spot that has a folder (loading the ones no screen has asked for yet)."""
    with _data_lock:
        pids = [pid for pid in profiles()["profiles"] if (DATA_DIR / "profiles" / pid).is_dir()]
    return [guest_spot(pid) for pid in pids]


def _airlines_worker():
    """Load the airline list, fill in the names missing from before (once), and refresh the list weekly."""
    while True:
        try:
            _load_airlines()
            if _airlines:
                for sp in _all_profile_spots():
                    with _data_lock:
                        if sp.book().get("airlinesV") != 1:
                            n = _backfill_airlines(sp)
                            if n:
                                event("info", f"Airline names filled in for {n} earlier sightings", echo=False)
        except Exception as e:  # never let the list break the relay
            event("warn", f"Airline list: {e}")
        time.sleep(6 * 3600 if not _airlines else AIRLINES_EVERY_S / 7)


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
        for k, v in airline_fields(cs).items():      # relay 68: no route (or a route without its airline): the table's
            airline.setdefault(k, v)
        if route and not _route_fits(route, e.get("pos")):
            event("info", f"Ignoring the listed route {route['from']['code']} → {route['to']['code']} for {cs}: "
                          "the plane is nowhere near it (the callsign is used for other flights too)")
            route = _routeset_for(cs, e.get("pos"))
            if route:
                route.update(airline)
        info = _aircraft_for(hx) if hx else None
        w = watch_of(hx) if hx else None
        with _data_lock:
            e["looked"] = True                        # relay 41: route and aircraft looked up (boards show "/" for what's missing)
            if w and not e.get("watch"):              # the watchlist may have arrived after the sighting
                e["watch"], e["watchOp"] = w
            if airline:
                e.update(airline)
            if route and e.get("routeSrc") == "fr24":   # relay 68: Flightradar24 answered first; its route stays
                route = None
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
            ctry = e.get("ownerCountry")
            if ctry and ctry not in book.setdefault("countries", {}):        # relay 50: countries for the trophies
                book["countries"][ctry] = e.get("ts") or int(time.time() * 1000)
            if info and e in spot.entries:
                for k in trophy_check(book, e, spot.entries):
                    event("info", f"Trophy won: {k}", echo=False)
            t = book["types"].get(e.get("typeCode") or "")
            if t is not None and not t.get("name") and info:
                t["name"] = " ".join(x for x in (info.get("manufacturer", "").split(" ")[0], info.get("aircraftType")) if x)
            m = re.match(r"^([A-Z]{3})\d", cs or "")
            a = book["airlines"].get(m.group(1)) if m else None
            if a is not None and airline:
                a["name"] = a.get("name") or airline.get("airlineName", "")
                a["iata"] = a.get("iata") or airline.get("airlineIata", "")
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


def _fr24_reset_day():
    try:
        return min(28, max(1, int(ARGS.fr24_reset_day or 1)))
    except (TypeError, ValueError):
        return 1


def fr24_period(today=None):
    """The plan's current month (relay 40): from its renewal day (--fr24-reset-day, or the admin page) to the next one.
    Returns (first day, next renewal day)."""
    today = today or datetime.date.today()
    d = _fr24_reset_day()
    start = today.replace(day=d) if today.day >= d else (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=d)
    nxt = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=d)
    return start, nxt


def _fr24_usage():
    u = _fr24_data()["usage"]
    month, day = fr24_period()[0].isoformat(), time.strftime("%Y-%m-%d")
    if u.get("month") != month:
        # relay 40: a count kept under a calendar month ("2026-10") or under another renewal day carries on while it
        # started within this period's month; an older one starts again from nothing.
        try:
            was = datetime.date.fromisoformat(u["month"] + ("-01" if u["month"].count("-") == 1 else ""))
        except (KeyError, TypeError, ValueError):
            was = None
        start = datetime.date.fromisoformat(month)
        if was and start - datetime.timedelta(days=27) < was <= datetime.date.today():
            u["month"] = month
        else:
            u.clear()
            u.update({"month": month, "credits": 0, "lookups": 0})
    if u.get("day") != day:
        u.update({"day": day, "creditsToday": 0, "lookupsToday": 0, "savedReuseToday": 0, "savedEdgeToday": 0, "filledToday": 0})
        _fr24_prune()
    return u


def _fr24_base_budget():
    try:
        return int(ARGS.fr24_budget) if ARGS.fr24_budget is not None else FR24_BUDGET
    except (TypeError, ValueError):
        return FR24_BUDGET


def _fr24_promo():
    """(budget, last day) of a temporary higher budget still running (relay 40: Dave's plan is doubled until the
    billing month starting 9 Dec 2026), or None."""
    try:
        until = datetime.date.fromisoformat(str(ARGS.fr24_promo_until))
        n = int(ARGS.fr24_budget_promo)
    except (TypeError, ValueError):
        return None
    return (n, until) if n > 0 and datetime.date.today() <= until else None


def _fr24_budget():
    p = _fr24_promo()
    return p[0] if p else _fr24_base_budget()


def fr24_paced(priority):
    """Spread the monthly budget over the month: each day may spend its share of what is left (unspent credits carry
    over). Past the share, only the plane on the board is still looked up; past one and a half shares, nothing until
    tomorrow. Boards show the free sources' answer meanwhile."""
    with _data_lock:
        u = _fr24_usage()
        today = u.get("creditsToday", 0)
        left = _fr24_budget() - (u.get("credits", 0) - today)
    now = datetime.date.today()
    share = max(0, left) / max(1, (fr24_period(now)[1] - now).days)
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
    # Relay 45: the same aircraft under the same callsign is the same flight for the rest of the day (or a few hours
    # past midnight); another aircraft with this callsign has its own key, so it is never handed this answer.
    same_day = time.strftime("%Y-%m-%d", time.localtime(info.get("t", 0))) == time.strftime("%Y-%m-%d")
    return info if same_day or age < FR24_REUSE_S else None


def _fr24_saved(e, why):
    """Count a lookup the relay didn't need (relay 45, for the admin page): `why` is "reuse" (an answer from an earlier
    sighting of the same flight) or "edge" (the plane only grazed the edge of the radius). Once per sighting."""
    if e.get("fr24Saved"):
        return
    e["fr24Saved"] = why
    with _data_lock:
        u = _fr24_usage()
        k = "saved" + why.capitalize()
        u[k] = u.get(k, 0) + 1
        u[k + "Today"] = u.get(k + "Today", 0) + 1
        _dirty.add("fr24")


def fr24_want(cs, hx, priority, who="Lists and alerts", pid=None):
    """Queue a lookup for a flight with a callsign (airline, cargo, business or private). `who` asked for it (relay 40:
    the admin page shows the credits by account and device), `pid` is that profile (relay 42: its credits count towards
    its daily limit). True when it was queued now."""
    if not fr24_on() or not cs or not hx or not re.match(r"^[A-Z0-9]{3,8}$", cs) or fr24_info(cs, hx) or fr24_paced(priority):
        return False
    key = f"{hx}|{cs}"
    with _fr24_cv:
        if key in _fr24_queued or len(_fr24_q) > 300:
            return False
        _fr24_queued.add(key)
        heapq.heappush(_fr24_q, (priority, next(_fr24_order), key, cs, hx, who, pid))
        _fr24_cv.notify()
    return True


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


_fr24_slot_lock = threading.Lock()
_fr24_next = 0.0             # relay 66: when the next request may go (the lookups and the gap filler take turns)


def fr24_slot(pause=0):
    """Wait for a turn: Flightradar24 allows 10 requests a minute for the lookups and the gap filler together. `pause`
    (after a "too many requests") holds both back that long."""
    global _fr24_next
    with _fr24_slot_lock:
        if pause:
            _fr24_next = max(_fr24_next, time.time() + pause)
            return
        wait = _fr24_next - time.time()
        if wait > 0:
            time.sleep(wait)
        _fr24_next = time.time() + FR24_GAP_S


def fr24_spent(credits, who, pid, lookups=1):
    """Count credits spent on one request: the month, today, who asked (the admin page) and the profile's daily limit
    (relay 42). Call under _data_lock."""
    usage = _fr24_usage()
    usage["credits"] = usage.get("credits", 0) + credits
    usage["creditsToday"] = usage.get("creditsToday", 0) + credits
    if not credits:
        return
    usage["lookups"] = usage.get("lookups", 0) + lookups
    usage["lookupsToday"] = usage.get("lookupsToday", 0) + lookups
    by = usage.setdefault("by", {}).setdefault(who, {"credits": 0, "lookups": 0})
    by["credits"] += credits
    by["lookups"] += lookups
    p = profiles()["profiles"].get(pid) if pid else None
    if p is not None:                 # relay 42: the profile's own count, for its daily limit
        pu = fr24_use(p)
        pu["today"] += credits
        pu["credits"] += credits
        pu["lookupsToday"] += lookups
        pu["lookups"] += lookups
        _dirty.add("profiles")
    _dirty.add("fr24")


def _fr24_worker():
    if fr24_key():
        _load_airports()
    while True:
        with _fr24_cv:
            while not _fr24_q:
                _fr24_cv.wait()
            priority, _, key, cs, hx, who, pid = heapq.heappop(_fr24_q)
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
            fr24_slot()
            info, status, credits = _fr24_lookup(cs, hx)
            with _data_lock:
                fr24_spent(credits, who, pid)
                usage = _fr24_usage()
                if info:
                    _fr24_data()["flights"][key] = info
                    fr24_keep(key, info)
                    for sp in all_spots():            # relay 41: lists showing this flight fetch again for the answer
                        if any(x.get("hex") == hx and x.get("callsign") == cs for x in sp.entries[:400]):
                            sp.rev += 1
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
                fr24_slot(pause=60)
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


def _fr24_same_flight(info, e):
    """Is this sighting the flight Flightradar24 answered about? By fr24_info's rules: the same day, or within
    FR24_REUSE_S (the caller has checked the aircraft and callsign)."""
    t, ts = info.get("t", 0), (e.get("ts") or 0) / 1000
    return time.strftime("%Y-%m-%d", time.localtime(t)) == time.strftime("%Y-%m-%d", time.localtime(ts)) or \
        abs(t - ts) < FR24_REUSE_S


def fr24_keep(key, info, spots=None, loaded=None):
    """Relay 68: write a Flightradar24 answer into the sightings of that flight (of its day, and of the day before
    when it came shortly after the day turned), so the logbook, search, the CSV and the records keep the flight actually flown: its flight number,
    route (over the route database's) and diversion, marked routeSrc "fr24". The airline stays the callsign's. Only
    profiles with Flightradar24 on (their "fr24" flag, as for fr24_overlay) get it. Returns the sightings changed
    (`loaded` keeps the days read, for many answers at once). Call under _data_lock."""
    if not info or info.get("none"):
        return 0
    hx, _, cs = key.partition("|")
    n = 0
    for sp in spots if spots is not None else all_spots():
        if not (profiles()["profiles"].get(sp.dir.name) or {}).get("fr24"):     # a spot's folder is named by its profile
            continue
        sp.ensure_day()
        t = info.get("t", 0)
        days = {board_day(t), board_day(t - FR24_REUSE_S)}
        book = None
        for day in sorted(days):
            if day != sp.day and not (sp.dir / f"sightings-{day}.json").exists():
                continue
            if loaded is None:
                entries = sp.day_entries(day)
            else:
                entries = loaded.get((str(sp.dir), day))
                if entries is None or day == sp.day or day in sp.days:
                    entries = loaded[(str(sp.dir), day)] = sp.day_entries(day)
            hit = False
            for e in entries:
                if e.get("hex") != hx or e.get("callsign") != cs or not _fr24_same_flight(info, e):
                    continue
                new = {}
                if info.get("flight"):
                    new["flightIata"] = info["flight"]
                if info.get("from") and info.get("to"):
                    new["from"], new["to"] = info["from"], info["to"]
                if info.get("divertedTo"):
                    new["divertedTo"] = info["divertedTo"]
                if not new:
                    continue
                new["routeSrc"] = "fr24"
                if all(e.get(k) == v for k, v in new.items()):
                    continue
                e.update(new)
                book = book or sp.book()
                note_records(book, e, sp.center() if sp.center else None)
                hit = True
                n += 1
            if hit:
                sp.day_changed(day, entries)
                sp.changed("book")
    return n


def _fr24_keep_cached():
    """Once, at start: the answers still in the cache into their sightings (relay 68)."""
    try:
        spots = _all_profile_spots()
        with _data_lock:
            flights = dict(_fr24_data()["flights"])
            loaded = {}
            n = sum(fr24_keep(k, v, spots, loaded) for k, v in flights.items())
        if n:
            event("info", f"Flightradar24's routes kept in {n} sightings", echo=False)
    except Exception as e:
        event("warn", f"Keeping Flightradar24's routes failed: {e}")


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
            "queue": len(_fr24_q), "airports": len((_airports or {}).get("iata") or {}),
            "fill": {"places": len(_fill), "filled": u.get("filled", 0), "filledToday": u.get("filledToday", 0)}}


def fr24_overlay(entries, radius=15.0, over_km=3.0):
    """Spotted today for boards that use Flightradar24: its flight numbers and routes over the free ones. Relay 45:
    planes that stay in the outer quarter of the radius (and outside the overhead distance) aren't looked up, until
    they come closer."""
    out, now = [], time.time()
    edge = max(over_km, radius * FR24_EDGE)
    for e in entries:
        cs, hx = e.get("callsign") or "", e.get("hex") or ""
        info = fr24_info(cs, hx) if cs else None
        if info and not info.get("none") and info.get("t", 0) < e.get("ts", 0) / 1000 - 1800 and fr24_key():
            _fr24_saved(e, "reuse")               # answered for an earlier sighting of this flight
        if not info and cs and (e.get("minDist") or 0) > edge:
            if now - e.get("lastSeen", now) > 300 and fr24_key():
                _fr24_saved(e, "edge")            # passed by at the edge without coming closer
            out.append(e)
            continue
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
            with _fr24_cv:
                waiting = f"{hx}|{cs}" in _fr24_queued
            if waiting:                               # relay 41: still to answer, so boards don't show "/" yet
                e = {**e, "fr24Wait": True}
        out.append(e)
    return out


# ---------- Flightradar24 fills the gaps (relay 66) ----------
# Away from big cities the free networks can be deaf down low: on an island adsb.fi first heard the planes leaving its
# airport at 9,000 ft and 22 km out, minutes after they had flown over the house (airplanes.live heard them, but lets
# only its feeders in). So while a screen of the owner's profile watches a place more than FILL_AWAY_KM from home, the
# relay also asks Flightradar24 for the low planes around it and adds the ones the free answer lacks. Where ten minutes
# of answers bring nothing new it asks only every few minutes; at home it never asks. Relay 67, as each answer costs
# 6 credits a plane: one record per profile, following its screens (a phone finding itself made three in a minute, each
# paying for the same plane), and only while a screen is looked at (a page in the background says bg=1).
_fill = []                   # a record per profile: pid, lat, lon, want (asked for), who, at (asked), t (answered), planes
_fill_cv = threading.Condition()


def fill_home():
    """The relay's own place, where the free sources hear everything."""
    try:
        return float(ARGS.lat), float(ARGS.lon)
    except (TypeError, ValueError):
        return 48.2085, 16.3731              # what boards watch when no place is set


def fill_for(p):
    """Does this profile's screen get the gap filler? The owner's (Dave's travels), while Flightradar24 is on for it and
    it has spent less than FILL_SHARE of its daily credits (the rest stays for routes)."""
    if str(p.get("name") or "").strip().lower() != HOME_OWNER.lower() or not p.get("fr24") or not fr24_on() or fr24_paced(1):
        return False
    with _data_lock:
        return fr24_use(p)["today"] < fr24_limit(p) * FILL_SHARE


def fill_want(lat, lon, pid, p, who):
    """A screen of profile `p` asks for positions around (lat, lon): the profile's gap-filler record, moved here (made
    when it has none), or None where the filler stays off. Somewhere else altogether, it starts afresh there."""
    lat, lon = float(lat), float(lon)
    if _dist_km(lat, lon, *fill_home()) < FILL_AWAY_KM or not fill_for(p):
        return None
    with _fill_cv:
        rec = next((r for r in _fill if r["pid"] == pid), None)
        if rec is None:
            if not _fill:
                event("info", f"Flightradar24 fills in what the free sources miss around {p.get('name')}'s screen, away from home")
            rec = {"pid": pid, "at": 0.0, "t": 0.0, "planes": [], "free": set(), "first": {}, "useless": 0, "near": False}
            _fill.append(rec)
            _fill_cv.notify()
        elif _dist_km(lat, lon, rec["lat"], rec["lon"]) > FILL_KM:
            rec.update(at=0.0, t=0.0, planes=[], useless=0, near=False)
            _fill_cv.notify()
        rec.update(lat=lat, lon=lon, want=time.time(), who=who)
    return rec


def fill_merge(body, rec, lat, lon, km):
    """The free answer for a screen watching `km` around (lat, lon) with the planes in that circle Flightradar24 last saw
    around `rec` that it lacks, aged to the answer's time. Returns (body for the screen, body for the sightings, planes
    added): a plane joins the sightings once its type and registration are looked up (or after 20 s), so its logbook
    entry is complete."""
    try:
        data = json.loads(body)
    except ValueError:
        return body, body, 0
    planes = data.get("ac", data.get("aircraft"))
    if not isinstance(planes, list):
        return body, body, 0
    have = {str(a.get("hex") or "").lower() for a in planes if isinstance(a, dict)}
    now = time.time()
    with _fill_cv:
        rec["free"] = have
        fresh = rec["planes"] if now - rec["t"] < 60 else []
        first = dict(rec["first"])
    n = data.get("now")
    t0 = n / 1000 if isinstance(n, (int, float)) and n > 1e11 else n if isinstance(n, (int, float)) and n > 1e9 else now
    add, hold = [], set()
    for f in fresh:
        if f["hex"] in have or _dist_km(lat, lon, f["lat"], f["lon"]) > km:
            continue
        a = {k: v for k, v in f.items() if k != "ts"}
        a["seen_pos"] = a["seen"] = round(max(0.0, t0 - f["ts"]), 1)
        info = fr24_info(f["flight"], f["hex"]) if f["flight"] else None
        if info and not info.get("none"):
            a["t"], a["r"] = info.get("type") or "", info.get("reg") or ""
        elif not info and f["flight"] and now - first.get(f["hex"], now) < 20:
            hold.add(f["hex"])
        add.append(a)
    if not add:
        return body, body, 0
    key = "ac" if "ac" in data else "aircraft"
    data[key] = planes + add
    out = json.dumps(data, separators=(",", ":")).encode()
    if not hold:
        return out, out, len(add)
    data[key] = planes + [a for a in add if a["hex"] not in hold]
    return out, json.dumps(data, separators=(",", ":")).encode(), len(add)


def _fill_ask(lat, lon):
    """One live-positions request for the low planes around (lat, lon). Returns (planes or None, status, credits)."""
    dy, dx = FILL_KM / 110.57, FILL_KM / (111.32 * max(0.1, math.cos(math.radians(lat))))
    q = urllib.parse.urlencode({"bounds": f"{min(89.9, lat + dy):.3f},{max(-89.9, lat - dy):.3f},{lon - dx:.3f},{lon + dx:.3f}",
                                "altitude_ranges": f"100-{FILL_FT}", "data_sources": "ADSB,MLAT,UAT", "limit": FILL_MAX})
    status, _, body, _ = fetch(f"{FR24_API}/live/flight-positions/light?{q}", timeout=15, headers={
        "Authorization": f"Bearer {fr24_key()}", "Accept": "application/json", "Accept-Version": "v1"})
    if status != 200:
        return None, status, 0
    try:
        rows = (json.loads(body) or {}).get("data") or []
    except ValueError:
        return None, 502, 0
    planes = []
    for r in rows:
        hx = str(r.get("hex") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{6}", hx) or not isinstance(r.get("lat"), (int, float)) or not isinstance(r.get("lon"), (int, float)):
            continue
        try:
            ts = datetime.datetime.strptime(str(r.get("timestamp"))[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            ts = time.time()
        planes.append({"hex": hx, "flight": str(r.get("callsign") or "").strip().upper(), "lat": r["lat"], "lon": r["lon"],
                       "alt_baro": r.get("alt"), "gs": r.get("gspeed"), "track": r.get("track"), "baro_rate": r.get("vspeed"),
                       "squawk": str(r.get("squawk") or ""), "src": "fr24", "ts": min(ts, time.time())})
    return planes, 200, 6 * len(rows) if rows else 1


def _fill_worker():
    """Asks Flightradar24 about each profile's place in turn while one of its screens looks on (asked within 30 s): every
    FILL_EVERY_S, FILL_FAST_S while a plane it added is close, FILL_SLOW_S where twenty answers in a row held nothing
    new. A record no screen asked about for two minutes is dropped."""
    while True:
        with _fill_cv:
            now = time.time()
            for r in [r for r in _fill if now - r["want"] > 120]:
                _fill.remove(r)
            every = lambda r: FILL_SLOW_S if r["useless"] >= 20 else FILL_FAST_S if r["near"] else FILL_EVERY_S
            due = [r for r in _fill if now - r["want"] < 30 and now - r["at"] >= every(r)]
            if not due:
                _fill_cv.wait(1)
                continue
            rec = min(due, key=lambda r: r["at"])
            rec["at"] = now
            lat, lon, who, pid = rec["lat"], rec["lon"], rec["who"], rec["pid"]
        try:
            p = profiles()["profiles"].get(pid)
            if not p or not fill_for(p):
                continue
            fr24_slot()
            planes, status, credits = _fill_ask(lat, lon)
            with _data_lock:
                fr24_spent(credits, who, pid)
            if status in (401, 402, 403):
                _fr24_state.update(state="refused", error=f"key refused (HTTP {status})", refusedAt=time.time())
                event("warn", f"Flightradar24 refused the gap filler (HTTP {status}): boards use the free sources. "
                              "Check the key, the credits, or the subscription has ended.")
                continue
            if status == 429:
                fr24_slot(pause=60)
                continue
            if planes is None:
                event("warn", f"Flightradar24 gap filler failed (HTTP {status})", echo=False)
                continue
            new = []
            with _fill_cv:
                missing = [f for f in planes if f["hex"] not in rec["free"]]
                if missing:
                    rec["useless"] = 0
                elif planes:
                    rec["useless"] += 1
                rec["near"] = any(_dist_km(rec["lat"], rec["lon"], f["lat"], f["lon"]) < GAME_KM for f in missing)
                rec["planes"], rec["t"] = planes, time.time()
                for f in missing:
                    if f["hex"] not in rec["first"]:
                        rec["first"][f["hex"]] = rec["t"]
                        new.append(f)
                for hx in [hx for hx, t in rec["first"].items() if rec["t"] - t > 3600]:
                    del rec["first"][hx]
            for f in new:
                if f["flight"]:
                    fr24_want(f["flight"], f["hex"], 0, who, pid)     # its type and registration, for the sighting
                event("debug", f"Flightradar24 filled in {f['flight'] or f['hex']} at {f['alt_baro']} ft, "
                               f"{_dist_km(lat, lon, f['lat'], f['lon']):.1f} km away: the free sources don't have it", echo=False)
            if new:
                with _data_lock:
                    u = _fr24_usage()
                    u["filled"] = u.get("filled", 0) + len(new)
                    u["filledToday"] = u.get("filledToday", 0) + len(new)
        except Exception as e:  # never let the paid extra break the relay
            event("warn", f"Flightradar24 gap filler: {e}", echo=False)


def day_stats(entries, over_km, over_deg=0.0):
    """Today in numbers, over every sighting of the day (the list itself only sends the newest ones). Relay 65: with
    `over_deg` a plane counts as overhead within over_km at any height or once it stood that many degrees up (the
    boards' rule since 1.84: 1 km or 45°)."""
    tan = math.tan(math.radians(over_deg)) if 0 < over_deg < 90 else 0
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
        if isinstance(md, (int, float)) and (md <= over_km or (tan and isinstance(alt, (int, float)) and alt > 0 and md <= alt * .3048 / 1000 / tan)):
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
            "points": sum(e.get("gp", 0) + e.get("lock", 0) for e in entries),
            "newAirlines": sum(1 for e in entries if e.get("newAirline")),
            "dayStarts": f"{DAY_STARTS_H:02d}:00"}


def same_spot(spot, places, key):
    """Relay 75 (to-do #121): the place `key` and the profile's other places at the same spot (centre within 1 km, a
    radius no larger), so a phone on the profile's own place ("home") and a board on a saved place there ("Home") share
    one Spotted today. A pass is recorded once whichever of them saw it (_record), so the merged list has no doubles."""
    if not key or key == "live":
        return {key} if key else None
    spots = {"home": (spot.center(), spot.radius())}
    for p in places or []:
        if isinstance(p, dict) and p.get("k"):
            spots.setdefault(p["k"], ((p.get("lat"), p.get("lon")), p.get("r") or 15))
    c, r = spots.get(key, (None, 0))
    out = {key}
    if c is None or None in c:
        return out
    for k, (cc, rr) in spots.items():
        try:
            if _dist_km(c[0], c[1], cc[0], cc[1]) <= 1.0 and float(rr) <= float(r) + 0.5:
                out.add(k)
        except (TypeError, ValueError):
            pass
    return out


def sightings_json(spot, api=False, over_km=3.0, everything_wanted=False, place=None, over_deg=0.0):
    """Today's sightings; with `place`, only those seen from that place (a screen's Spotted today, relay 33; relay 75:
    a set of places, see same_spot)."""
    if isinstance(place, str):
        place = {place}
    with _data_lock:
        spot.ensure_day()
        everything = [e for e in spot.entries if place is None or (e.get("place") or "home") in place]
        day, rev = spot.day, spot.rev
    if api:
        everything = fr24_overlay(everything, spot.radius(), over_km)
    return {"version": RELAY_VERSION, "date": day, "rev": rev, "entries": everything if everything_wanted else everything[:400],
            "stats": day_stats(everything, over_km, over_deg)}


# Relay 61: category words in the logbook search ("military austria", "cargo A330"), the logbook's categories as
# category_of names them.
CATEGORY_WORDS = {"military": ("MILITARY", "MIL", "ARMY", "AIRFORCE", "NAVY"), "helicopter": ("HELICOPTER", "HELICOPTERS", "HELI", "CHOPPER"),
                  "cargo": ("CARGO", "FREIGHT", "FREIGHTER"), "bizjet": ("BIZJET", "BIZJETS", "BUSINESS"),
                  "private": ("PRIVATE", "LIGHT", "GA"), "passenger": ("PASSENGER", "AIRLINER", "AIRLINERS")}


def _logbook_entries(spot):
    """Every sighting of every saved day (today's as it is now)."""
    with _data_lock:
        spot.ensure_day()
        files = sorted(spot.dir.glob("sightings-*.json"))
        today, sday = list(spot.entries), spot.day
    for f in files:
        day = f.stem[len("sightings-"):]
        for e in (today if day == sday else _load(f, [])):
            if isinstance(e, dict):
                yield e


def search_json(spot, q):
    """Relay 55: the whole logbook searched (every saved day): a registration, a flight, a type or an airline. Matches
    are grouped by flight when the words name one, else by aircraft: how often, first and last seen, how close.
    Relay 61: a category word narrows it to that category (alone, it lists the category). Relay 63: where it was seen
    counts too (a saved place's name, "home", or on the go the town, the area round it or the country: "Oia",
    "Santorini", "Greece"), and each row says where it was seen (places, the newest first). Relay 74 (the plane card):
    also the closest pass's height, the sighting before the latest, the newest route, how many different flights (or
    aircraft: nOther), the hex and the registered owner and country."""
    words = [w for w in re.sub(r"[^A-Z0-9 -]", " ", _fold(q)).split() if w][:5]
    cat = next((c for w in words for c, ws in CATEGORY_WORDS.items() if w in ws), None)
    if cat:
        words = [w for w in words if w not in CATEGORY_WORDS[cat]][:4]
    tight = lambda t: re.sub(r"[\s-]", "", str(t or "").upper())
    if not cat and (not words or len("".join(words)) < 2):
        return {"q": q, "total": 0, "rows": []}
    groups, total = {}, 0
    with _data_lock:
        spot.ensure_day()
        files = sorted(spot.dir.glob("sightings-*.json"))
        today = list(spot.entries)
    for f in files:
        day = f.stem[len("sightings-"):]
        entries = today if day == spot.day else _load(f, [])
        est = where_estimates(entries)
        for e in entries:
            if not isinstance(e, dict):
                continue
            place = e.get("place") or "home"
            w = where_of(e, est)
            flight, reg = tight(e.get("flightIata") or e.get("callsign")), tight(e.get("reg"))
            hay = _fold(" ".join(str(e.get(k) or "") for k in ("reg", "callsign", "flightIata", "icaoType", "typeCode", "aircraftType",
                                                             "manufacturer", "airlineName", "airlineIcao", "airlineIata", "owner"))
                        + " " + " ".join([place if place != "live" else "", w.get("n", ""), w.get("a", ""), w.get("c", "")]))
            if not all(w2 in hay or tight(w2) in tight(hay) for w2 in words):
                continue
            if cat and category_of(e) != cat:
                continue
            total += 1
            by_flight = flight and any(tight(w2) in (flight, tight(e.get("callsign"))) for w2 in words)
            key = ("f", flight) if by_flight else ("r", reg or str(e.get("hex") or ""))
            g = groups.get(key)
            if not g:
                g = groups[key] = {"by": key[0], "key": key[1], "reg": e.get("reg") or "", "flight": e.get("flightIata") or e.get("callsign") or "",
                                   "type": e.get("aircraftType") or e.get("icaoType") or e.get("typeCode") or "", "airline": e.get("airlineName") or "",
                                   "typeCode": e.get("typeCode") or "", "callsign": e.get("callsign") or "", "airlineIata": e.get("airlineIata") or "",
                                   "n": 0, "first": None, "last": None, "minDist": None, "flights": [], "regs": [], "_pl": {},
                                   "hex": e.get("hex") or "", "prev": None, "_fl": set(), "_rt": -1}    # relay 74: for the cards
            g["n"] += 1
            t = e.get("ts") or e.get("time")
            if isinstance(t, (int, float)):
                g["first"] = t if g["first"] is None else min(g["first"], t)
                if g["last"] is None or t > g["last"]:              # relay 74: and the sighting before the latest
                    g["prev"], g["last"] = g["last"], t
                elif t < g["last"] and (g["prev"] is None or t > g["prev"]):
                    g["prev"] = t
            md = e.get("minDist")
            if isinstance(md, (int, float)) and (g["minDist"] is None or md < g["minDist"]):
                g["minDist"], g["altAtMin"] = md, e.get("altAtMin")
            other = ("flights", e.get("flightIata") or e.get("callsign")) if key[0] == "r" else ("regs", e.get("reg"))
            if other[1]:
                g["_fl"].add(other[1])
            if other[1] and other[1] not in g[other[0]] and len(g[other[0]]) < 5:
                g[other[0]].append(other[1])
            fr, to = e.get("from"), e.get("to")
            if isinstance(fr, dict) and isinstance(to, dict) and fr.get("code") and to.get("code") and (t or 0) >= g["_rt"]:
                g["_rt"], g["route"] = t or 0, {k: {"code": p.get("code"), "city": p.get("city") or ""} for k, p in (("from", fr), ("to", to))}
            for k in ("owner", "ownerCountry"):
                if e.get(k) and not g.get(k):
                    g[k] = e[k]
            pk = (place, w.get("n", ""), w.get("c", ""))
            seen = t if isinstance(t, (int, float)) else 0
            if pk not in g["_pl"] or seen > g["_pl"][pk][0]:
                g["_pl"][pk] = (seen, {"k": place, **({k: w[k] for k in ("n", "a", "c") if w.get(k)} if place == "live" else {})})
    for g in groups.values():
        g["places"] = [v for _, v in sorted(g.pop("_pl").values(), key=lambda x: -x[0])][:4]
        g["nOther"] = len(g.pop("_fl"))                    # relay 74: how many different flights (or aircraft)
        g.pop("_rt")
    rows = sorted(groups.values(), key=lambda g: -(g["last"] or 0))[:40]
    return {"q": q, "total": total, "rows": rows, "category": cat, "text": " ".join(words).lower()}


_cat_cache = {}


def category_top_json(spot, cat, places=None):
    """Relay 61: one category of the logbook (the app's Logbook → Categories, tapped): its top ten types, aircraft and
    operators over every saved day, optionally for some places only."""
    key = (str(spot.dir), cat, tuple(places or ()), spot.day, spot.rev // 5)
    hit = _cat_cache.get(key)
    if hit and time.time() - hit[0] < 120:
        return hit[1]
    types, regs, ops, total = {}, {}, {}, 0
    for e in _logbook_entries(spot):
        if category_of(e) != cat or (places and (e.get("place") or "home") not in places):
            continue
        total += 1
        tc = str(e.get("typeCode") or "").upper()
        if tc:
            t = types.setdefault(tc, {"code": tc, "name": e.get("aircraftType") or e.get("desc") or tc, "n": 0})
            t["n"] += 1
        if e.get("reg"):
            r = regs.setdefault(e["reg"], {"reg": e["reg"], "type": e.get("aircraftType") or tc, "n": 0})
            r["n"] += 1
        m = re.match(r"^([A-Z]{3})\d", str(e.get("callsign") or ""))
        on = e.get("airlineName") or e.get("owner") or e.get("watchOp") or (m.group(1) if m else "")
        if on:
            o = ops.setdefault(on, {"name": on, "icao": m.group(1) if m else "", "iata": e.get("airlineIata") or "", "n": 0})
            o["n"] += 1
    top = lambda d: sorted(d.values(), key=lambda x: -x["n"])[:10]
    out = {"category": cat, "total": total, "types": top(types), "regs": top(regs), "operators": top(ops)}
    _cat_cache.clear()
    _cat_cache[key] = (time.time(), out)
    return out


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
                "game": {**game3_json(b, spot.day or board_day()), "bingo": bingo_json(spot, spot.day or board_day()),
                         "trophyToday": sum(1 for e in spot.entries if "gp" in e)},
                "records": game_book(b).get("records", {}),          # relay 59: the game's records
                "places": sorted(([k, p["n"]] for k, p in place_logbook(spot).items()), key=lambda kp: -kp[1])}


# The logbook by place (relay 37): one logbook keeps every place's planes together; for one place the relay works its
# numbers out from the saved days. A past day never changes, so its per-place summary is kept in memory once made;
# today's is made fresh.
_place_days = {}             # (spot folder, day) -> {place: summary}


def _place_summary(entries):
    out = {}
    for e in entries:
        k = e.get("place") or "home"
        p = out.setdefault(k, {"n": 0, "types": {}, "airlines": {}, "regs": {}, "cats": {}, "book": {}, "first": None})
        p["n"] += 1
        ts = e.get("ts") or 0
        p["first"] = ts if p["first"] is None else min(p["first"], ts)
        def note(d, key, name):
            if not key:
                return
            it = d.get(key)
            if it is None:
                it = d[key] = {"name": name or "", "first": ts, "count": 0, "last": ts}
            it["count"] += 1
            it["first"], it["last"] = min(it["first"], ts), max(it["last"], ts)
            if name and not it["name"]:
                it["name"] = name
        note(p["types"], e.get("typeCode"), e.get("aircraftType") or e.get("desc"))
        m = re.match(r"^([A-Z]{3})\d", str(e.get("callsign") or ""))
        note(p["airlines"], m.group(1) if m else "", e.get("airlineName"))
        note(p["regs"], e.get("reg"), e.get("typeCode"))
        c = category_of(e)
        p["cats"][c] = p["cats"].get(c, 0) + 1
        note_records(p["book"], e)
    return out


def _merge_items(into, items):
    for key, it in items.items():
        cur = into.get(key)
        if cur is None:
            into[key] = dict(it)
        else:
            cur["count"] += it["count"]
            cur["first"], cur["last"] = min(cur["first"], it["first"]), max(cur["last"], it["last"])
            cur["name"] = cur["name"] or it["name"]


def place_logbook(spot, place=None):
    """{place: merged summary} over all saved days (or just `place`; relay 40: a tuple of places is merged into one,
    under the tuple)."""
    many = isinstance(place, tuple)
    want = set(place) if many else None
    with _data_lock:
        spot.ensure_day()
        days = sorted(f.stem[len("sightings-"):] for f in spot.dir.glob("sightings-*.json"))
        today = spot.day
        merged = {}
        for day in days:
            key = (str(spot.dir), day)
            if day == today:
                summ = _place_summary(spot.entries)
            else:
                summ = _place_days.get(key)
                if summ is None:
                    summ = _place_days[key] = _place_summary(_load(spot.dir / f"sightings-{day}.json", []))
            for k, p in summ.items():
                if many and k not in want or not many and place is not None and k != place:
                    continue
                m = merged.setdefault(place if many else k, {"n": 0, "types": {}, "airlines": {}, "regs": {}, "cats": {}, "records": {}, "first": None, "since": day})
                m["n"] += p["n"]
                m["first"] = p["first"] if m["first"] is None else min(m["first"], p["first"] or m["first"])
                for part in ("types", "airlines", "regs"):
                    _merge_items(m[part], p[part])
                for c, n in p["cats"].items():
                    m["cats"][c] = m["cats"].get(c, 0) + n
                for rk, rv in (p["book"].get("records") or {}).items():
                    cur = m["records"].get(rk)
                    lower = rk in ("closest", "lowest")
                    if cur is None or (rv["v"] < cur["v"] if lower else rv["v"] > cur["v"]):
                        m["records"][rk] = rv
        return merged


def place_logbook_json(spot, place):
    m = place_logbook(spot, place).get(place)
    place = list(place) if isinstance(place, tuple) else place
    if not m:
        return {"version": RELAY_VERSION, "place": place, "sightings": 0, "types": {}, "airlines": {}, "regsCount": 0,
                "regsTop": [], "regsRecent": [], "categories": {}, "records": {}}
    regs = m["regs"]
    return {"version": RELAY_VERSION, "place": place, "since": m["since"], "sightings": m["n"], "categories": m["cats"],
            "types": m["types"], "airlines": m["airlines"], "regsCount": len(regs),
            "regsTop": [{"reg": k, **v} for k, v in sorted(regs.items(), key=lambda kv: -kv[1]["count"])[:15]],
            "regsRecent": [{"reg": k, **v} for k, v in sorted(regs.items(), key=lambda kv: -kv[1]["first"])[:15]],
            "records": m["records"]}


def _days_of(spot, prefix=""):
    """(day, entries) for each saved day of a spot, oldest first, today's from memory."""
    for f in sorted(spot.dir.glob(f"sightings-{prefix}*.json")):
        day = f.stem[len("sightings-"):]
        yield day, spot.day_entries(day)


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
                pts += e.get("gp", 0) + e.get("lock", 0)
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


# Week and month in review (relay 46, to-do #44): like Today in numbers, over a calendar week (Monday to Sunday, board
# days) or month, from the saved days. A finished period never changes, so its numbers are kept once made; the current
# one is made again when a sighting comes in (like year_json).
REVIEW_SPANS = ("week", "month")
REVIEW_WEEK_AT = (6, "20:00")     # Sunday evening: the week
REVIEW_MONTH_AT = (1, "09:00")    # the 1st of the month, morning: the month before
_reviews = {}                     # (spot folder, span, start) -> numbers of a finished period


def review_range(span, back=0, day=None):
    """(first day, last day) of the week or month `back` periods before the one holding `day` (today)."""
    d = datetime.date.fromisoformat(day or board_day())
    if span == "week":
        start = d - datetime.timedelta(days=d.weekday(), weeks=back)
        return start.isoformat(), (start + datetime.timedelta(days=6)).isoformat()
    y, m = d.year, d.month - back
    while m < 1:
        y, m = y - 1, m + 12
    nxt = datetime.date(y + m // 12, m % 12 + 1, 1)
    return datetime.date(y, m, 1).isoformat(), (nxt - datetime.timedelta(days=1)).isoformat()


def review_json(spot, span, back=0, prev=True):
    span = span if span in REVIEW_SPANS else "week"
    back = max(0, min(60, int(back or 0)))
    with _data_lock:
        spot.ensure_day()
        today = spot.day
        start, end = review_range(span, back, today)
        done = end < today
        key = (str(spot.dir), span, start)
        out = _reviews.get(key) if done else None
        cached = getattr(spot, "_review", {}).get(key)
        if out is None and cached and cached[0] == spot.rev:
            out = cached[1]
        if out is None:
            days = {f.stem[len("sightings-"):] for f in spot.dir.glob("sightings-*.json")}
            if spot.entries:
                days.add(today)
            n, pts, rare, types, airlines, regs, per_day, rec, rarest = 0, 0, 0, set(), {}, collections.Counter(), {}, {}, None
            new_types, new_regs, new_al = {}, 0, 0
            order = {t: i for i, t in enumerate(TIERS)}
            centre = spot.center() if spot.center else None
            for day in sorted(d for d in days if start <= d <= end):
                entries = spot.entries if day == today else _load(spot.dir / f"sightings-{day}.json", [])
                per_day[day] = len(entries)
                for e in entries:
                    n += 1
                    pts += e.get("gp", 0) + e.get("lock", 0)
                    rare += order.get(e.get("tier"), -1) >= order["rare"]
                    if e.get("typeCode"):
                        types.add(e["typeCode"])
                        if e.get("newType"):
                            new_types.setdefault(e["typeCode"], e.get("aircraftType") or e.get("desc") or "")
                    al = _al(e)
                    if al:
                        a = airlines.setdefault(al, {"code": al, "name": e.get("airlineName") or "", "count": 0})
                        a["count"] += 1
                        a["name"] = a["name"] or e.get("airlineName") or ""
                    if e.get("reg"):
                        regs[e["reg"]] += 1
                    new_regs += bool(e.get("newReg"))
                    new_al += bool(e.get("newAirline"))
                    note_records(rec, e, centre)
                    k = (order.get(e.get("tier"), -1), -FLEET.get(_tc(e), 500))
                    if rarest is None or k > rarest[0]:
                        rarest = (k, e)
            busiest = max(per_day.items(), key=lambda kv: (kv[1], kv[0])) if per_day else None
            top_al = max(airlines.values(), key=lambda a: a["count"]) if airlines else None
            top = regs.most_common(1)
            who = lambda e: {"reg": e.get("reg") or "", "type": e.get("aircraftType") or e.get("typeCode") or "",
                             "callsign": e.get("callsign") or "", "tier": e.get("tier") or "", "ts": e.get("ts")}
            out = {"span": span, "start": start, "end": end, "complete": done, "planes": n, "days": sum(1 for v in per_day.values() if v),
                   "types": len(types), "airlines": len(airlines), "airframes": len(regs), "points": pts, "rare": rare,
                   "newTypes": [{"type": t, "name": nm} for t, nm in list(new_types.items())[:12]], "newTypeCount": len(new_types),
                   "newAircraft": new_regs, "newAirlines": new_al,
                   "busiest": {"day": busiest[0], "planes": busiest[1]} if busiest and busiest[1] else None,
                   "topAirline": top_al, "mostSeen": {"reg": top[0][0], "count": top[0][1]} if top else None,
                   "rarest": who(rarest[1]) if rarest else None, "records": rec.get("records", {})}
            if done:
                _reviews[key] = out
            else:
                if not hasattr(spot, "_review"):
                    spot._review = {}
                spot._review[key] = (spot.rev, out)
    res = {"version": RELAY_VERSION, "back": back, **out}
    if prev:
        res["prevPlanes"] = review_json(spot, span, back + 1, prev=False)["planes"]
    return res


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


def seen_json(spot, reg, part="regs"):
    """What the logbook knows of one airframe (relay 28), or of one flight number (`part` "flights", relay 38): how
    often it was seen here, first, last and the one before."""
    with _data_lock:
        it = spot.book().get(part, {}).get(reg)
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
                if kind == "dep":           # relay 46: departures have a gate (once it is given out) in a pier
                    e.update(gate=str(r.get("gate") or ""), gateArea=str(r.get("gateArea") or ""))
                else:                       # arrivals have no gate in the list, only the baggage belt
                    e["belt"] = str((r.get("belt") or {}).get("belt") or "") if isinstance(r.get("belt"), dict) else ""
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
            **({"backup": True, "used_today": st.get("used", 0), "day_cap": src["day_cap"]} if src.get("day_cap") else {}),
        })
    with _lock:
        events = list(EVENTS)[-80:]
    live, _ = screens_list()
    return {"version": RELAY_VERSION, "uptime_s": int(now - STARTED), "sources": sources, "events": events, "fr24": fr24_status(),
            "health": {k: v["down"] for k, v in _health.items()},
            "vie": vie_status(), "screens": live}


BACKUP_FILE = DATA_DIR / "backup.json"    # relay 69: written by the nightly backup on the host, read for the owner's panel
BACKUP_LATE_S = 36 * 3600


def relay_panel_json():
    """Relay 69: the owner's Relay plate in the app's Settings → About: the position sources, Flightradar24, the nightly
    backup and the screens online. Read-only, and no addresses or secrets."""
    now = time.time()
    utc = time.strftime("%Y-%m-%d", time.gmtime())
    sources = []
    for i, src in enumerate(SOURCES):
        st = STATE[src["key"]]
        resting = st["cooldown_until"] > now
        state = "resting" if resting else "ok" if st["ok"] and not st["strikes"] else "failing" if st["strikes"] else "standby"
        sources.append({"name": src["name"], "role": "emergency" if src.get("day_cap") else "first" if i == 0 else "reserve",
                        "state": state, "until": int(st["cooldown_until"]) if resting else None,
                        "http": st["last_status"] if state in ("resting", "failing") else None,
                        "okAge": int(now - st["last_ok"]) if st["last_ok"] else None,
                        "today": st["asked"] if st["askedDay"] == utc else 0, "allow": src.get("allow")})
    fr = {"on": False}
    if fr24_key():
        with _data_lock:
            u = _fr24_usage()
            # the per-user rows start again with the month's total (_fr24_usage clears them together)
            fill = sum(v.get("credits", 0) for k, v in (u.get("by") or {}).items() if k.endswith(" · Gap filler"))
            fr = {"on": True, "credits": u.get("credits", 0), "budget": _fr24_budget(), "creditsToday": u.get("creditsToday", 0),
                  "lookupsToday": u.get("lookupsToday", 0), "fill": fill}
    b = _load(BACKUP_FILE, None)
    backup = None
    if isinstance(b, dict) and isinstance(b.get("t"), (int, float)):
        num = lambda k: b[k] if isinstance(b.get(k), int) else None
        backup = {"t": int(b["t"]), "ok": b.get("ok") is True, "bytes": num("bytes"), "kept": num("kept"),
                  "error": str(b.get("error") or "")[:120], "late": now - b["t"] > BACKUP_LATE_S}
    live, _ = screens_list()
    screens = [{"who": i["name"], "device": i["device"], "kind": "app" if i["board"] == "APP" else "board",
                "on": i["on_s"], "quiet": i["quiet_s"], "hidden": i["hidden"]} for i in live]
    return {"version": RELAY_VERSION, "up": int(now - STARTED), "sources": sources, "fr24": fr, "backup": backup, "screens": screens}


_board_seen = {}
_board_date = {}             # when each board was published (GitHub's Last-Modified), in ms since 1970


_board_file_try = {}         # rel -> when a copy was last fetched for a version the cached one isn't (relay 48)


def file_version(body):
    """The version a board names a file by (`i18n.js?v=...`, tools/assets.py): its SHA-256 (the board uses the start)."""
    return hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest()   # line ends as in the repository


def board_file(sub, name, ext, want=""):
    """An icon or the web app manifest next to a board (the phone app needs them to go on the home screen), or since
    relay 48 the board's translations and sounds (i18n.js, sounds.js). `want`: the version the board asked for; a copy
    that isn't it is fetched again (GitHub may have the new board before this relay's copy is ten minutes old). Returns
    (status, body, whether the body is that version, so the screen may keep it for good)."""
    rel = (sub + "/" if sub else "") + name
    if ARGS.local_root:
        f = Path(ARGS.local_root) / rel
        if not f.is_file():
            return 404, b"Not found", False
        body = f.read_bytes()
        return 200, body, bool(want) and file_version(body).startswith(want)
    copy = DATA_DIR / "board-files" / rel.replace("/", "--")
    load = lambda: fetch(f"{BOARD_URL}{rel}?v={want or int(time.time()) // 600}", timeout=15)
    status, _, body, _ = cached_or_stale("file:" + rel, PAGE_TTL * 10, load)
    if want and status == 200 and not file_version(body).startswith(want) and time.time() - _board_file_try.get(rel, 0) > 20:
        _board_file_try[rel] = time.time()          # at most every 20 s, whatever version a request names
        status, _, body, _ = cached("file:" + rel, 0, load)
    if status == 200:
        try:
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(body)
        except OSError:
            pass
        return 200, body, bool(want) and file_version(body).startswith(want)
    if copy.exists():
        body = copy.read_bytes()
        return 200, body, bool(want) and file_version(body).startswith(want)
    return (404 if status == 404 else 502), b"Not found", False


BADGES = ("star", "prop", "heli", "jumbo", "jet", "concorde")   # the board's title badges (STYLES), relay 53


def badge_manifest(body, badge):
    """The phone app's manifest for a profile with a title badge (relay 53): the icons with that badge
    (app/icon-192-<badge>.png ..., tools/app/make_icons.py). A phone picks the new icon up when it next refreshes the
    installed app's manifest (the browser decides when; Chrome on Android checks about once a day while the app is used)."""
    try:
        m = json.loads(body)
        for ic in m.get("icons") or []:
            ic["src"] = re.sub(r"^((?:icon(?:-maskable)?-\d+)|apple-touch-icon)\.png$", lambda x: f"{x.group(1)}-{badge}.png", ic.get("src", ""))
        return json.dumps(m, indent=2).encode()
    except (ValueError, AttributeError, TypeError):
        return body


def board_html(sub="", guest=None):
    """The board (or the phone app) with what it needs to know injected: the profile's name, id and saved settings
    (`guest` is (id, profile)), and for a profile without a place yet the relay's own location, to start the welcome
    from (relay 42)."""
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
    if guest is not None and (guest.get("settings") or {}).get("located"):     # their own settings come with their profile
        defaults = {"units": ARGS.units} if ARGS.units else {}
    elif guest is not None:     # relay 43: a new guest's welcome starts from the city and airport, never the relay's own point
        defaults.pop("lat", None)
        defaults.pop("lon", None)
    config = json.dumps(defaults).replace("<", "\\u003c")
    who = "null"
    if guest is not None:
        me = {"id": gid, "name": guest["name"], "settings": guest.get("settings")}
        if str(guest["name"] or "").strip().lower() == HOME_OWNER.lower():
            me["owner"] = True                  # relay 69: the app shows the owner the Relay plate
        who = json.dumps(me).replace("<", "\\u003c")
    inject = (f"<script>window.OVERHEAD_RELAY=location.origin;window.OVERHEAD_RELAY_VERSION={RELAY_VERSION};"
              f"window.OVERHEAD_DEFAULTS={config};window.OVERHEAD_FR24={'true' if fr24 else 'false'};"
              f"window.OVERHEAD_GUEST={who};window.OVERHEAD_PAGE_DATE={_board_date.get(sub) or 'null'};"
              f"window.OVERHEAD_FCM={'true' if fcm_ready() else 'false'};</script>")
    return html.replace("<head>", "<head>\n" + inject, 1)


# ---------- friends and family: profiles, personal invite links and the admin page (relay 19) ----------
# Every screen belongs to a profile (relay 42: there is no Home any more; a device without one gets the private page,
# with a QR code to sign it in from a phone). Dave makes a personal invite link on /admin (home network only), the
# first device to open it gets a long-lived cookie, and the link is used up; an account (username, passkeys, password)
# signs in more devices. Only a hash of each link and each device's cookie is kept. A profile's settings (its
# location) are kept with it.
PROFILES_FILE = DATA_DIR / "profiles.json"
COOKIE = "overhead"
INVITE_DAYS = 14
FR24_DAY_GUEST = 500        # relay 42: most Flightradar24 credits a day for a profile without an account (it is turned on for)
FR24_DAY_ACCOUNT = 2000     # ... and with one: a fallback against a bug or a lost device, not a limit anyone should reach
_profiles = None            # {"profiles": {id: {...}}, "invites": {hash: {...}}}
_buckets = {}
_made = {}                  # one-off key -> (expires, (name, invite code)): the admin page's last new link


@functools.lru_cache(maxsize=16)
def _gzip(body):
    """A page or file packed for sending; the same page is packed once (relay 54)."""
    return gzip.compress(body, 6, mtime=0)


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
        for p in _profiles["profiles"].values():          # devices that were only a chat's preview
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
            P["profiles"][pid] = {"name": name, "created": time.time(), "lastSeen": 0, "fr24": False, "devices": [], "settings": None}
        elif pid not in P["profiles"]:
            return None
        now = time.time()
        P["invites"] = {h: i for h, i in P["invites"].items() if i["expires"] > now}
        P["invites"][_hash(code)] = {"profile": pid, "created": now, "expires": now + INVITE_DAYS * 86400}
        _dirty.add("profiles")
        who = P["profiles"][pid]["name"]
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
            p = P["profiles"].get(inv["profile"])
        if not p:
            return None, None
        token = secrets.token_urlsafe(32)
        p["devices"].append({"token": _hash(token), "device": device_of(ua), "added": time.time(), "lastSeen": time.time()})
        p["lastSeen"] = time.time()
    event("info", f"{p['name']} joined on a {device_of(ua)}")
    return inv["profile"], token


# ---------- QR codes (relay 39): a small encoder for the TV's sign-in code (byte mode, error correction M, versions
# 1-10, which hold up to 213 bytes), drawn as SVG. After Project Nayuki's reference implementation of ISO/IEC 18004.
_QR_ECC = (10, 16, 26, 18, 24, 16, 18, 22, 22, 26)      # error correction codewords per block, level M, versions 1-10
_QR_BLOCKS = (1, 1, 1, 2, 2, 4, 4, 4, 5, 5)


def _qr_raw_modules(ver):
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        na = ver // 7 + 2
        n -= (25 * na - 10) * na - 55
        if ver >= 7:
            n -= 36
    return n


def _rs_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def _rs_ecc(data, degree):
    div = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            div[j] = _rs_mul(div[j], root)
            if j + 1 < degree:
                div[j] ^= div[j + 1]
        root = _rs_mul(root, 0x02)
    res = [0] * degree
    for b in data:
        f = b ^ res.pop(0)
        res.append(0)
        for i, c in enumerate(div):
            res[i] ^= _rs_mul(c, f)
    return res


def qr_matrix(text):
    data = text.encode("utf-8")
    for ver in range(1, 11):
        cap = _qr_raw_modules(ver) // 8 - _QR_ECC[ver - 1] * _QR_BLOCKS[ver - 1]
        if 4 + (8 if ver < 10 else 16) + 8 * len(data) <= cap * 8:
            break
    else:
        raise ValueError("too long for a QR code here")
    bits = []
    put = lambda v, n: bits.extend((v >> i) & 1 for i in range(n - 1, -1, -1))
    put(4, 4); put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, cap * 8 - len(bits)))
    put(0, -len(bits) % 8)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(cw) < cap:
        cw.append(pad); pad ^= 0xEC ^ 0x11
    nb, ecc, raw = _QR_BLOCKS[ver - 1], _QR_ECC[ver - 1], _qr_raw_modules(ver) // 8
    short, slen = nb - raw % nb, raw // nb
    blocks, k = [], 0
    for i in range(nb):
        d = cw[k:k + slen - ecc + (0 if i < short else 1)]
        k += len(d)
        e = _rs_ecc(d, ecc)
        if i < short:
            d = d + [None]
        blocks.append(d + e)
    final = [b[i] for i in range(len(blocks[0])) for b in blocks if b[i] is not None]
    size = ver * 4 + 17
    M = [[False] * size for _ in range(size)]
    F = [[False] * size for _ in range(size)]

    def fn(x, y, dark):
        M[y][x] = dark; F[y][x] = True
    for i in range(size):
        fn(6, i, i % 2 == 0); fn(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    fn(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    if ver > 1:
        na = ver // 7 + 2
        step = (ver * 4 + na * 2 + 1) // (na * 2 - 2) * 2
        pos = [6] + sorted(size - 7 - i * step for i in range(na - 1))
        for i, ax in enumerate(pos):
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, na - 1), (na - 1, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        fn(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)

    def format_bits(mask):
        d = mask                                      # level M is 00
        rem = d
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        b = (d << 10 | rem) ^ 0x5412
        bit = lambda i: (b >> i) & 1 == 1
        for i in range(6):
            fn(8, i, bit(i))
        fn(8, 7, bit(6)); fn(8, 8, bit(7)); fn(7, 8, bit(8))
        for i in range(9, 15):
            fn(14 - i, 8, bit(i))
        for i in range(8):
            fn(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            fn(8, size - 15 + i, bit(i))
        fn(8, size - 8, True)
    format_bits(0)
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        b = ver << 12 | rem
        for i in range(18):
            dark = (b >> i) & 1 == 1
            a, c = size - 11 + i % 3, i // 3
            fn(a, c, dark); fn(c, a, dark)
    i = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                y = size - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not F[y][x] and i < len(final) * 8:
                    M[y][x] = (final[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2
    masks = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
             lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
             lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)

    def apply(m):
        for y in range(size):
            for x in range(size):
                if not F[y][x] and masks[m](x, y):
                    M[y][x] = not M[y][x]

    def penalty():
        p = 0
        for rows in (M, list(zip(*M))):
            for row in rows:
                run, prev = 0, None
                for v in row:
                    run = run + 1 if v == prev else 1
                    prev = v
                    if run == 5:
                        p += 3
                    elif run > 5:
                        p += 1
        for y in range(size - 1):
            for x in range(size - 1):
                if M[y][x] == M[y][x + 1] == M[y + 1][x] == M[y + 1][x + 1]:
                    p += 3
        dark = sum(map(sum, M))
        p += abs(dark * 20 - size * size * 10) // (size * size) * 10
        return p
    best = None
    for m in range(8):
        apply(m); format_bits(m)
        sc = penalty()
        if best is None or sc < best[0]:
            best = (sc, m)
        apply(m)
    apply(best[1]); format_bits(best[1])
    return M


def qr_svg(text, px=6):
    M = qr_matrix(text)
    n, q = len(M), 4
    path = "".join(f"M{x + q},{y + q}h1v1h-1z" for y in range(n) for x in range(n) if M[y][x])
    w = n + 2 * q
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {w}" width="{w * px}" height="{w * px}" '
            f'shape-rendering="crispEdges"><rect width="{w}" height="{w}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')


# ---------- sign in a TV from a phone (relay 39): the private page on a screen that isn't signed in asks for a pairing
# (/pair/new: a short code and a secret), shows the code as a QR code and waits (/pair/wait). A signed-in phone opens
# /pair/<code> (scanning it), says yes, and the screen's next wait gets a new device of that profile and its cookie.
PAIR_ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIR_S = 600
_pairs = {}                  # code -> {"secret": hash, "t": created, "pid": None or the profile that said yes, "device"}


def pair_new(ua):
    now = time.time()
    with _lock:
        for k in [k for k, v in _pairs.items() if now - v["t"] > PAIR_S]:
            del _pairs[k]
        if len(_pairs) > 300:
            return None, None
        code = "".join(secrets.choice(PAIR_ALPHA) for _ in range(6))
        while code in _pairs:
            code = "".join(secrets.choice(PAIR_ALPHA) for _ in range(6))
        secret = secrets.token_urlsafe(24)
        _pairs[code] = {"secret": _hash(secret), "t": now, "pid": None, "device": device_of(ua)}
    return code, secret


def pair_find(code):
    with _lock:
        pr = _pairs.get(code)
        return pr if pr and time.time() - pr["t"] <= PAIR_S else None


def pair_html(body):
    return plain_page("Fallblatt: sign in a screen", f"<h1>Sign in a screen</h1>{body}")


def pair_page_js():
    """The private page's part that pairs: asks for a code, shows it, waits for a phone to say yes, then reloads."""
    return ("<div id=qrBox style='margin:22px 0 6px;display:flex;gap:22px;align-items:center;flex-wrap:wrap'></div>"
            "<p id=qrMsg class=muted></p><script>(function(){var box=document.getElementById('qrBox'),msg=document.getElementById('qrMsg'),s='';"
            "function post(u,o){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o||{})}).then(function(r){return r.json()})}"
            "function start(){post('/pair/new').then(function(j){if(!j.code){msg.textContent=j.error||'';setTimeout(start,60000);return}s=j.secret;"
            "box.innerHTML='<div style=\"background:#fff;padding:8px;border-radius:10px;line-height:0\">'+j.svg+'</div>'+"
            "'<div style=\"max-width:300px\"><p style=\"margin:0 0 6px\">Scan this with your phone, where you are signed in to Fallblatt, to sign in this screen.</p>'+"
            "'<p style=\"margin:0;color:#8d887d\">Or open <b style=\"color:#e8e2d0\">'+j.host+'/pair</b> on your phone and type</p>'+"
            "'<p style=\"margin:4px 0 0;font:700 34px/1.2 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.18em;color:#f2b134\">'+j.code+'</p></div>';"
            "setTimeout(wait,2500)}).catch(function(){setTimeout(start,15000)})}"
            "function wait(){post('/pair/wait',{secret:s}).then(function(j){if(j.ok){msg.textContent='Signed in. Opening the board…';location.reload();return}"
            "if(j.gone){start();return}setTimeout(wait,2500)}).catch(function(){setTimeout(wait,5000)})}start()})();</script>")


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
        P = profiles()
        p = P["profiles"][pid]
        p["devices"].append({"token": _hash(token), "device": device_of(ua), "added": time.time(), "lastSeen": time.time(), "via": how})
        del p["devices"][:-20]
        p["lastSeen"] = time.time()
        _dirty.add("profiles")
    event("info", f"{p['name']} signed in with {how} on a {device_of(ua)}")
    return token


def signin_html(next_url="/app/"):
    return plain_page("Fallblatt: sign in", (
        "<h1>Sign in</h1><p>With your Fallblatt account: your place, logbook and settings come with you to this phone or computer.</p>"
        "<p><button class='go big' type=button id=pk>Sign in with a passkey</button></p>"
        "<form id=pf><p><input type=text id=u autocomplete='username webauthn' placeholder='Username' required> "
        "<input type=password id=pw autocomplete=current-password placeholder='Password' required "
        "style='background:#16171a;color:#e8e2d0;border:1px solid #34363b;border-radius:6px;padding:9px 10px;font:inherit;width:210px'> "
        "<button type=submit>Sign in</button></p></form><p id=msg class=muted></p>"
        "<p class=muted>No account yet? Ask the person who runs this board for an invite link, then create one in the app's About.</p>"
        "<script>var NEXT=" + json.dumps(next_url).replace("<", "\\u003c") + ";" + SIGNIN_JS + "</script>"))


SIGNIN_JS = (
    "var b64u=function(b){return btoa(String.fromCharCode.apply(null,new Uint8Array(b))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'')};"
    "var ub64=function(s){s=s.replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';return Uint8Array.from(atob(s),function(c){return c.charCodeAt(0)})};"
    "var msg=document.getElementById('msg');"
    "var post=function(u,o){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o||{})}).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j})})};"
    "var done=function(){msg.textContent='Signed in.';location.href=NEXT};"
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
        for pid, p in P["profiles"].items():
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


SKY_REPORTS_MAX = 200      # relay 72: Sky view's reports kept per profile (the oldest go)
SKY_REPORT_DROP = {"lat", "lon", "latitude", "longitude", "place", "here", "pos", "position", "image", "picture"}


def sky_report_clean(v, depth=0):
    """A Sky view report (relay 72) as numbers, flags and short words only: no picture, no place, nothing long."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(v, 3) if math.isfinite(v) else None
    if isinstance(v, str):
        return re.sub(r"[\x00-\x1f]", "", v)[:120]
    if isinstance(v, list) and depth < 3:
        return [sky_report_clean(x, depth + 1) for x in v[:240]]
    if isinstance(v, dict) and depth < 3:
        return {k: sky_report_clean(x, depth + 1) for k, x in list(v.items())[:40]
                if isinstance(k, str) and re.fullmatch(r"[A-Za-z0-9_]{1,24}", k) and k.lower() not in SKY_REPORT_DROP}
    return None


def sky_report_save(pid, rep):
    """Adds a report to the profile's skyreports.jsonl, keeping the newest SKY_REPORTS_MAX. Returns how many are kept."""
    f = DATA_DIR / "profiles" / pid / "skyreports.jsonl"
    with _data_lock:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        lines = (lines + [json.dumps(rep, separators=(",", ":"))])[-SKY_REPORTS_MAX:]
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, f)
    return len(lines)


def fr24_limit(p):
    """A profile's Flightradar24 credits a day (relay 42): set on the admin page, else by whether it has an account."""
    v = p.get("fr24Limit")
    if isinstance(v, int) and v >= 0:
        return v
    return FR24_DAY_ACCOUNT if (p.get("account") or {}).get("user") else FR24_DAY_GUEST


def fr24_use(p):
    """A profile's Flightradar24 credits and lookups today and in the plan's month (call under _data_lock)."""
    u = p.setdefault("fr24Use", {})
    day, month = time.strftime("%Y-%m-%d"), fr24_period()[0].isoformat()
    if u.get("day") != day:
        u.update(day=day, today=0, lookupsToday=0)
    if u.get("month") != month:
        u.update(month=month, credits=0, lookups=0)
    return u


def guest_fr24(p):
    """May this profile's board ask Flightradar24 now? Only if Dave turned it on for them, and within its daily limit."""
    if not p.get("fr24") or not fr24_on():
        return False
    with _data_lock:
        return fr24_use(p)["today"] < fr24_limit(p)


# ---------- relay 42: the old Home profile merges into its owner's, once ----------
# Before relay 42 a screen on the home network without a cookie was "Home": the relay's own location, data/'s sightings
# and logbook, and profiles["home"] (places, favourites, notifications, linked devices). Dave's own devices had already
# become his profile, so Home's history goes there: the days of sightings joined (a plane both recorded in the same pass
# is one sighting), the logbook counted again from the joined days, and the rest added to his. The old files are kept
# in data/home-before-merge/. It runs at start until it has been done (profiles.json "homeMerged").
HOME_OWNER = "David"
SKIP_FILL = {"id", "place", "newType", "newReg", "newAirline", "newFlight"}


def _merge_day(*lists):
    """One day's sightings from several lists (newest first) as one list: the same plane in the same pass is one."""
    out, last = [], {}
    for e in sorted((e for l in lists for e in l), key=lambda e: e.get("ts") or 0):
        prev = last.get(e.get("hex", ""))
        if prev and (e.get("ts") or 0) / 1000 - prev.get("lastSeen", (prev.get("ts") or 0) / 1000) <= SAME_PASS_S:
            prev["lastSeen"] = max(prev.get("lastSeen", 0), e.get("lastSeen", 0))
            if e.get("minDist") is not None and (prev.get("minDist") is None or e["minDist"] < prev["minDist"]):
                prev["minDist"], prev["altAtMin"] = e["minDist"], e.get("altAtMin")
            prev["maxSpeed"] = max(prev.get("maxSpeed") or 0, e.get("maxSpeed") or 0)
            for k, v in e.items():                 # what only the other one learned (route, airline, Flightradar24)
                if k not in SKIP_FILL and prev.get(k) in (None, "", [], {}) and v not in (None, "", [], {}):
                    prev[k] = v
            continue
        out.append(e)
        last[e.get("hex", "")] = e
    return out[::-1]


def _rebuild_book(folder, old_books):
    """A logbook counted afresh from a folder's saved days; scores, records, trophies and flights follow when it is
    loaded (Spot.book, as for an older logbook). Names and the start come from the old logbooks."""
    b = {"since": min([x.get("since") for x in old_books if x.get("since")] or [time.strftime("%Y-%m-%d")]),
         "startedTs": min([x.get("startedTs") for x in old_books if x.get("startedTs")] or [time.time()]),
         "sightings": 0, "types": {}, "airlines": {}, "regs": {}, "categories": {}}
    hours = set()
    for f in sorted(folder.glob("sightings-*.json")):
        for e in reversed(_load(f, [])):
            b["sightings"] += 1
            c = category_of(e)
            b["categories"][c] = b["categories"].get(c, 0) + 1
            x = dict(e)                            # the days keep their own "new" marks
            if e.get("typeCode"):
                _note_first(b["types"], e["typeCode"], e.get("desc") or "", x, "newType", True)
            if e.get("reg"):
                _note_first(b["regs"], e["reg"], e.get("typeCode") or "", x, "newReg", True)
            m = re.match(r"^([A-Z]{3})\d", e.get("callsign") or "")
            if m:
                _note_first(b["airlines"], m.group(1), "", x, "newAirline", True)
            hours.add(_hour(e))
    for part in ("types", "airlines", "regs"):
        for x in old_books:
            for k, it in (x.get(part) or {}).items():
                if k in b[part] and not b[part][k].get("name") and isinstance(it, dict) and it.get("name"):
                    b[part][k]["name"] = it["name"]
    b["hours"] = sorted(hours)
    return b


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def merge_home():
    """Merge the old Home into HOME_OWNER's profile (called once at start, under _data_lock)."""
    P = profiles()
    if P.get("homeMerged"):
        return
    days, home = sorted(DATA_DIR.glob("sightings-*.json")), P.get("home")
    if not days and not LOGBOOK_FILE.exists() and not home:
        P["homeMerged"] = {"v": 1, "at": time.time(), "into": None}
        _write_json(PROFILES_FILE, P)
        return
    hits = [pid for pid, p in P["profiles"].items() if str(p.get("name") or "").strip().lower() == HOME_OWNER.lower()]
    if len(hits) != 1:
        event("warn", f"Home's sightings and logbook were not merged: {len(hits)} profiles are named {HOME_OWNER}, one is "
                      "needed. Nothing was changed; Home's devices can't sign in until it is done (rename the profiles "
                      "and restart the relay).")
        return
    pid = hits[0]
    p, dest, keep = P["profiles"][pid], DATA_DIR / "profiles" / pid, DATA_DIR / "home-before-merge"
    keep.mkdir(parents=True, exist_ok=True)
    before = sum(len(_load(f, [])) for f in days)
    for f in days:
        mine = dest / f.name
        _write_json(mine, _merge_day(_load(f, []), _load(mine, [])))
    old_books = [b for b in (_load(LOGBOOK_FILE, None), _load(dest / "logbook.json", None)) if isinstance(b, dict)]
    book = _rebuild_book(dest, old_books)
    _write_json(dest / "logbook.json", book)
    for f in days + ([LOGBOOK_FILE] if LOGBOOK_FILE.exists() else []):
        os.replace(f, keep / f.name)
    home = home or {}
    have = {d["token"] for d in p.setdefault("devices", [])}
    p["devices"] += [{**d, "via": d.get("via") or "Home"} for d in home.get("devices", []) if d.get("token") not in have]
    eps = {x["endpoint"] for x in p.setdefault("push", [])}
    p["push"] += [x for x in home.get("push", []) if x.get("endpoint") not in eps]
    p["places"] = _clean_places((p.get("places") or []) + (home.get("places") or []))
    L, HL = p.setdefault("lists", {}), home.get("lists") or {}
    for k in ("fav", "hide"):
        L[k] = _clean_list((L.get(k) or []) + (HL.get(k) or []))
    st = p.get("settings") or {}
    for k, v in (("lat", ARGS.lat), ("lon", ARGS.lon), ("place", ARGS.place), ("home", ARGS.home), ("radiusKm", ARGS.radius)):
        if st.get(k) in (None, "") and v is not None:
            st[k] = v
    for k, v in (home.get("settings") or {}).items():
        st.setdefault(k, v)
    if st.get("lat") is not None:
        st["located"] = True
    p["settings"] = st
    p["fr24"] = True                                   # Home always had Flightradar24
    P.pop("home", None)
    P["invites"] = {h: i for h, i in P["invites"].items() if i.get("profile") != "home"}
    P["homeMerged"] = {"v": 1, "at": time.time(), "into": pid, "days": len(days), "sightings": before, "logbook": book["sightings"]}
    _guest_spots.pop(pid, None)
    _write_json(PROFILES_FILE, P)
    event("info", f"Home merged into {p['name']}: {len(days)} days with {before} sightings, the logbook counted again "
                  f"({book['sightings']} sightings), {len(home.get('devices', []))} devices, {len(home.get('push', []))} "
                  f"notification subscriptions; the old files are in {keep.name}/")


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


def plain_page(title, body, refresh=None):
    meta = f'<meta http-equiv="refresh" content="{int(refresh)}">' if refresh else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1">{meta}<title>{html.escape(title)}</title><style>{PAGE_CSS}</style></head><body><main>'
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


ADMIN_CSS = ("<style>.prof{border:1px solid #26272b;border-radius:10px;padding:12px 14px;margin:0 0 12px;background:#111214}"
             ".prof h3{margin:0;font-size:17px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}"
             ".tag{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;border-radius:4px;padding:2px 6px}"
             ".tag.g{background:#2a2c31;color:#b9b3a3}.tag.a{background:#f2b134;color:#111}"
             ".prof ul{list-style:none;margin:6px 0;padding:0;font-size:14px}.prof li{padding:3px 0;border-bottom:1px solid #1d1e21}"
             ".prof .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 0;font-size:14px}"
             ".prof input[type=text],.prof input[type=password],.prof input[type=number]{background:#16171a;color:#e8e2d0;border:1px solid #34363b;"
             "border-radius:6px;padding:6px 8px;font:inherit;font-size:14px;width:150px}.prof input[type=number]{width:90px}"
             ".prof .stats{margin:6px 0;font-size:14px;line-height:1.5;color:#cfc9b8}button.sm{padding:3px 8px;font-size:12px}details summary{cursor:pointer;color:#b9b3a3;font-size:14px;margin-top:8px}</style>")


def _pform(action, pid, inner, confirm=None):
    esc = html.escape
    guard = f" onsubmit=\"return confirm({esc(json.dumps(confirm))})\"" if confirm else ""
    return f"<form method=post action='{action}'{guard}><input type=hidden name=pid value='{esc(pid, quote=True)}'>{inner}</form>"


def admin_stats(pid, p, live):
    """One profile's numbers for the admin page (relay 46, to-do #44/#45): planes today, this week and in all, what the
    logbook gained this week and month, the rare planes, and its screens on now. No ranking between profiles."""
    esc = html.escape
    try:
        sp = guest_spot(pid)
        w, m = review_json(sp, "week", 0, prev=False), review_json(sp, "month", 0, prev=False)
        b = sp.book()
    except Exception as e:                  # a damaged file must not take the admin page down
        return f"<p class=muted>Numbers unavailable ({esc(str(e))})</p>"
    ra = m["rarest"] or {}
    rare = f"{m['rare']:,} rare this month" + (f" (rarest {esc(ra.get('type') or ra.get('reg') or '')})" if ra.get("tier") in ("rare", "epic", "legendary") else "")
    on = [i for i in live if i["name"] == p["name"]]
    scr = ", ".join(esc(f"{i['device']} ({i['board'] or 'main'} board)") for i in on) or "none"
    return (f"<p class=stats><b>{len(sp.entries):,}</b> planes today · <b>{w['planes']:,}</b> this week · <b>{b.get('sightings', 0):,}</b> in all"
            f"<br>New this week: {w['newAircraft']:,} aircraft, {w['newTypeCount']:,} types · this month: {m['newAircraft']:,} aircraft, "
            f"{m['newTypeCount']:,} types · {len(b.get('types', {})):,} types in the logbook<br>{rare} · screens on now: {scr}</p>")


def admin_html(host, made=None):
    """Relay 42 (to-do #34): every profile is a Guest (no account yet: an invite link brings in a device) or an Account
    (a username: devices sign in with it, so there is no link any more), with its devices, Flightradar24 use and limit."""
    esc = html.escape
    base = (ARGS.public_url or "").rstrip("/") or f"http://{host}"
    cards = []
    live = screens_list()[0]
    with _data_lock:
        by = (_fr24_usage().get("by") or {})
        items = sorted(profiles()["profiles"].items(), key=lambda kv: -kv[1].get("lastSeen", 0))
        pending = collections.Counter(i["profile"] for i in profiles()["invites"].values() if i["expires"] > time.time())
        for pid, p in items:
            acc = p.get("account") or {}
            user = acc.get("user") or ""
            st = p.get("settings") or {}
            where = esc(str(st.get("place") or "")) or ("location set" if st.get("lat") is not None else "no location yet")
            pu = fr24_use(p)
            month = max(pu["credits"], sum(b["credits"] for w, b in by.items() if w.startswith(p["name"] + " · ")))
            lim, own = fr24_limit(p), isinstance(p.get("fr24Limit"), int)
            nk = len(acc.get("passkeys", []))
            how = ", ".join(([f"{nk} passkey{'s' if nk != 1 else ''}"] if nk else []) + (["password"] if acc.get("pw") else [])) or "no passkey or password yet"
            head = (f"<span class='tag a'>Account</span> <b>{esc(p['name'])}</b> <span class=muted>username <b>{esc(user)}</b> · {how}</span>" if user
                    else f"<span class='tag g'>Guest</span> <b>{esc(p['name'])}</b> <span class=muted>no account yet</span>")
            devs = sorted(p.get("devices", []), key=lambda d: -d.get("lastSeen", 0))
            dl = "".join(f"<li>{esc(d.get('device') or 'device')} <span class=muted>· {esc(d.get('via') or 'invite link')} · "
                         f"seen {_ago(d.get('lastSeen'))}</span> " + _pform("/admin/device", pid, f"<input type=hidden name=d value='{esc(d['token'][:16])}'>"
                         "<button class=sm>Sign out</button>", f"Sign out this {d.get('device') or 'device'} of {p['name']}?") + "</li>" for d in devs)
            link = "" if user else (_pform("/admin/link", pid, "<button>New invite link</button>") +
                                    (f" <span class=muted>{pending[pid]} unused link{'s' if pending[pid] != 1 else ''}</span>" if pending[pid] else ""))
            fr = (_pform("/admin/fr24", pid, f"<input type=hidden name=on value='{'0' if p.get('fr24') else '1'}'>"
                         f"<button>Flightradar24 {'on' if p.get('fr24') else 'off'}</button>") +
                  f" <span class=muted>{pu['today']:,} credits today · {month:,} this month</span> " +
                  _pform("/admin/limit", pid, f"<label class=muted>limit a day <input type=number name=limit min=0 max=100000 step=50 "
                         f"value='{lim if own else ''}' placeholder='{lim}'></label> <button class=sm>Set</button>") +
                  (" <span class=muted>(set here)</span>" if own else " <span class=muted>(automatic)</span>"))
            sg = style_grants(p)
            st = (_pform("/admin/styles", pid, "<input type=hidden name=mode value=all><button class=sm>Unlock all</button>") + " " +
                  _pform("/admin/styles", pid, "<input type=hidden name=mode value=earned><button class=sm>Back to earned only</button>") +
                  " <span class=muted>" + ("all granted" if sg == "all" else f"{len(sg)} granted" if sg else "earned only") + "</span>" +
                  "<details><summary>Pick styles</summary>" +
                  _pform("/admin/styles", pid, "<input type=hidden name=mode value=pick>" + " ".join(
                      f"<label><input type=checkbox name=grant value='{i}'{' checked' if sg == 'all' or i in sg else ''}> {esc(n)}</label>"
                      for i, n in STYLE_GRANTS) + " <button class=sm>Save</button>") + "</details>")
            acct = ("<details><summary>Account</summary><div class=row>" +
                    _pform("/admin/username", pid, f"<input type=text name=user maxlength=30 placeholder='username' value='{esc(user, quote=True)}' "
                           "autocomplete=off> <button class=sm>" + ("Change username" if user else "Create account") + "</button>") + "</div>" +
                    (f"<div class=row>" + _pform("/admin/password", pid, "<input type=password name=pw minlength=8 placeholder='new password' "
                     "autocomplete=new-password> <button class=sm>Set password</button>") + " " +
                     _pform("/admin/resetaccount", pid, "<button class=sm>Reset sign-in</button>",
                            f"Remove {p['name']}'s passkeys and password? They can set them again from a signed-in device.") + "</div>" if user else "") +
                    "</details>")
            cards.append(f"<div class=prof><h3>{head}</h3><p class=muted style='margin:4px 0'>{where} · seen {_ago(p.get('lastSeen'))}</p>"
                         + admin_stats(pid, p, live) +
                         f"<ul>{dl or '<li class=muted>not joined yet</li>'}</ul><div class=row>{link}</div><div class=row>{fr}</div><div class=row><span class=muted>Styles</span> {st}</div>{acct}"
                         "<div class=row>" + _pform("/admin/remove", pid, "<button class=sm>Remove</button>", f"Remove {p['name']} and their sightings?") +
                         "</div></div>")
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
    people = "".join(cards) or "<p>Nobody yet. Invite someone below.</p>"
    body = (ADMIN_CSS + f"<h1>Friends &amp; family</h1><p>Everyone has their own profile: their own location, Spotted today and "
            f"logbook. A guest joins with an invite link; once they create an account, they sign in with it instead. A screen "
            f"without a profile shows a QR code to sign it in from a phone. This page only opens at home.</p>{made_html}"
            f"<h2>People</h2>{people}<p class=muted>Flightradar24 a day: {FR24_DAY_GUEST:,} credits for a guest, {FR24_DAY_ACCOUNT:,} "
            f"with an account, unless set here.</p><h2>Invite someone</h2>"
            f"<form method=post action='/admin/invite'><input type=text name=name maxlength=40 placeholder='Name, e.g. Mum' required> "
            f"<button class=go>Make a link</button></form>" + fr24_admin_html() + hue_admin_html())
    return plain_page("Fallblatt: friends & family", body, refresh=3 if hue_pairing() else None)


def fr24_admin_html():
    """Flightradar24 this month (relay 28): credits used against the budget, where the month is heading, and what the
    lookups added, to help decide whether the subscription is worth renewing."""
    if not fr24_key():
        return "<h2>Flightradar24</h2><p class=muted>No key: the boards use the free sources only.</p>"
    with _data_lock:
        u = dict(_fr24_usage())
    budget, used, today = _fr24_budget(), u.get("credits", 0), u.get("creditsToday", 0)
    now = datetime.date.today()
    start, nxt = fr24_period(now)
    days = (nxt - start).days
    t = time.localtime()
    done = max(.25, (now - start).days + (t.tm_hour * 3600 + t.tm_min * 60) / 86400)  # days of the plan's month gone
    pace = round(used / done * days)
    pct = min(100, round(used / max(1, budget) * 100))
    col = "#3c3" if pace <= budget else "#f2b134" if pace <= budget * 1.1 else "#e0372c"
    st = fr24_status()
    left = (nxt - now).days
    promo = _fr24_promo()
    promo_line = (f"<p class=muted>{promo[0]:,} a month until {promo[1].day} {promo[1].strftime('%b %Y')}, then {_fr24_base_budget():,}.</p>"
                  if promo else "")
    by = sorted((u.get("by") or {}).items(), key=lambda kv: -kv[1]["credits"])
    rows = "".join(f"<tr><td>{html.escape(w)}</td><td style='text-align:right'>{b['credits']:,}</td>"
                   f"<td style='text-align:right'>{b['lookups']:,}</td><td style='text-align:right'>{round(b['credits'] / max(1, used) * 100)}%</td></tr>"
                   for w, b in by)
    table = (f"<table style='width:100%;border-collapse:collapse;margin:10px 0'><tr style='color:#8d887d;text-align:left'><th>Asked by</th>"
             f"<th style='text-align:right'>Credits</th><th style='text-align:right'>Lookups</th><th style='text-align:right'>Share</th></tr>{rows}</table>"
             if rows else "<p class=muted>Who used them shows from the next lookup on.</p>")
    return (f"<h2>Flightradar24</h2><p><b>{used:,}</b> of {budget:,} credits this month · <b>{max(0, budget - used):,}</b> left · "
            f"{today:,} today · on pace for <b style='color:{col}'>{pace:,}</b></p>"
            f"<p>Renews on <b>{nxt.day} {nxt.strftime('%b %Y')}</b> ({left} day{'s' if left != 1 else ''} to go; the month runs from the "
            f"{start.day}{'st' if start.day in (1, 21) else 'nd' if start.day in (2, 22) else 'rd' if start.day in (3, 23) else 'th'}).</p>" + promo_line +
            f"<div style='height:10px;border-radius:5px;background:#16171a;border:1px solid #34363b;overflow:hidden'>"
            f"<div style='height:100%;width:{pct}%;background:{col}'></div></div>"
            f"<p class=muted>{u.get('lookups', 0):,} lookups · {u.get('found', 0):,} flights found · "
            f"{u.get('wetLease', 0):,} in another airline's livery · {u.get('diverted', 0):,} diverted · "
            f"state: {html.escape(str(st.get('state', '')))}</p>"
            f"<p class=muted>Lookups saved this month: <b>{u.get('savedReuse', 0) + u.get('savedEdge', 0):,}</b> "
            f"({u.get('savedReuseToday', 0) + u.get('savedEdgeToday', 0):,} today) · {u.get('savedReuse', 0):,} answered from an "
            f"earlier sighting of the same flight · {u.get('savedEdge', 0):,} only passed the edge of the radius</p>" + table +
            f"<form method=post action='/admin/fr24plan'><p>Plan renews on day <input type=number name=day min=1 max=28 value={_fr24_reset_day()} "
            f"style='width:64px'> · spend at most <input type=number name=budget min=0 max=1000000 step=500 value={_fr24_base_budget()} style='width:110px'> credits "
            f"a month</p><p>For a while: <input type=number name=promo min=0 max=1000000 step=500 value={ARGS.fr24_budget_promo or ''} style='width:110px'> "
            f"credits a month until <input type=date name=until value={html.escape(str(ARGS.fr24_promo_until or ''), quote=True)}> "
            f"(empty: none) <button>Save</button></p></form>")


def save_config():
    """Write the saved settings back (relay 40: the admin page's Flightradar24 plan), as `--save` does."""
    keep = {k: getattr(ARGS, k) for k in SAVED_KEYS if getattr(ARGS, k) is not None}
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(keep, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_FILE)


# ---------- push notifications (relay 25): the evening summary and "worth going to the window" ----------
# Web Push to browsers (https only: through the public address), encrypted (RFC 8291) and signed (VAPID) with the relay's own
# key in data/vapid.pem. Needs the cryptography package (Debian: python3-cryptography); without it there are no
# notifications and everything else works as before. Subscriptions live with each profile.
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding
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


# Relay 57: the Android app's notifications through Firebase Cloud Messaging (its WebView has no Web Push). The
# project's service account key, fcm.json next to the relay (root/the relay's user only; never in the repository),
# signs a token for Google's FCM v1 API. Without the file the app says notifications aren't set up.
FCM_FILE = DATA_DIR / "fcm.json"   # copied onto the relay by hand (relay 58: no upload page any more)
_fcm = {"token": "", "until": 0}


def fcm_ready():
    return PUSH_OK and FCM_FILE.is_file()


def _fcm_token():
    """An OAuth access token from the service account (RS256 JWT), kept until shortly before it runs out."""
    if _fcm["token"] and time.time() < _fcm["until"]:
        return _fcm["token"], _fcm["project"]
    sa = json.loads(FCM_FILE.read_text(encoding="utf-8"))
    now = int(time.time())
    claims = {"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/firebase.messaging",
              "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}
    head = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + "." + _b64u(json.dumps(claims).encode())
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    jwt = head + "." + _b64u(key.sign(head.encode(), padding.PKCS1v15(), hashes.SHA256()))
    status, _, body, _ = fetch("https://oauth2.googleapis.com/token", content_type="application/x-www-form-urlencoded", timeout=15,
                               data=urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt}).encode())
    if status != 200:
        raise RuntimeError(f"Firebase sign-in failed (HTTP {status})")
    j = json.loads(body)
    _fcm.update(token=j["access_token"], until=time.time() + int(j.get("expires_in", 3600)) - 300, project=sa["project_id"])
    return _fcm["token"], _fcm["project"]


def fcm_send(sub, payload, urgent):
    """One notification to the Android app: a data message its PushService shows (as the service worker does)."""
    token, project = _fcm_token()
    data = {k: ("1" if v is True else "" if v is False else str(v)) for k, v in payload.items() if v is not None}
    msg = {"message": {"token": sub["fcm"], "data": data, "android": {"priority": "high" if urgent else "normal", "ttl": "3600s"}}}
    status, _, body, _ = fetch(f"https://fcm.googleapis.com/v1/projects/{project}/messages:send", data=json.dumps(msg).encode(),
                               content_type="application/json", timeout=15, headers={"Authorization": f"Bearer {token}"})
    if status == 401:
        _fcm["token"] = ""
    if status == 400 and b"registration-token-not-registered" in body.lower():
        return 410
    return 410 if status == 404 else status


def push_send(sub, payload, urgent=False):
    """Send one notification. Returns the HTTP status (404/410: the subscription is gone)."""
    if sub.get("fcm"):
        return fcm_send(sub, payload, urgent)
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
    "cd_over": {"en": "{what} · overhead in {left}", "de": "{what} · über dir in {left}", "fr": "{what} · au-dessus dans {left}",
                "es": "{what} · encima en {left}", "nl": "{what} · recht boven in {left}"},
    "cd_pass": {"en": "{what} · passing in {left}", "de": "{what} · kommt vorbei in {left}", "fr": "{what} · passe dans {left}",
                "es": "{what} · pasa en {left}", "nl": "{what} · komt langs over {left}"},
    "cd_now": {"en": "Look up now: {what}", "de": "Jetzt hochschauen: {what}", "fr": "Levez les yeux : {what}", "es": "Mira arriba ahora: {what}",
               "nl": "Kijk nu omhoog: {what}"},
    "cd_look": {"en": "look {dir}", "de": "Blick nach {dir}", "fr": "regardez vers {dir}", "es": "mira al {dir}", "nl": "kijk naar {dir}"},
    "cd_up": {"en": "straight up", "de": "direkt nach oben", "fr": "juste au-dessus", "es": "justo encima", "nl": "recht omhoog"},
    "test": {"en": "Notifications work. This is how a plane worth a look will show up.", "de": "Benachrichtigungen funktionieren. So erscheint ein Flugzeug, das einen Blick wert ist.",
             "fr": "Les notifications fonctionnent. Voici comment un avion à voir s'affichera.", "es": "Las notificaciones funcionan. Así aparecerá un avión que merece la pena.",
             "nl": "Meldingen werken. Zo verschijnt een vliegtuig dat het bekijken waard is."},
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
    "week": {"en": "Your week in planes", "de": "Deine Woche in Flugzeugen", "fr": "Votre semaine en avions", "es": "Tu semana en aviones", "nl": "Je week in vliegtuigen"},
    "month": {"en": "Your month in planes", "de": "Dein Monat in Flugzeugen", "fr": "Votre mois en avions", "es": "Tu mes en aviones", "nl": "Je maand in vliegtuigen"},
    "rsum": {"en": "{n} planes · {t} types · {a} airlines{new}{rare}", "de": "{n} Flugzeuge · {t} Typen · {a} Airlines{new}{rare}",
             "fr": "{n} avions · {t} types · {a} compagnies{new}{rare}", "es": "{n} aviones · {t} tipos · {a} aerolíneas{new}{rare}",
             "nl": "{n} vliegtuigen · {t} types · {a} maatschappijen{new}{rare}"},
    "newtypes": {"en": " · {x} new types", "de": " · {x} neue Typen", "fr": " · {x} nouveaux types", "es": " · {x} tipos nuevos", "nl": " · {x} nieuwe types"},
    "record": {"en": " · a new best day!", "de": " · ein neuer Bestwert!", "fr": " · un nouveau record !", "es": " · ¡un nuevo récord!", "nl": " · een nieuw record!"},
}
DIRS = {"en": "N NE E SE S SW W NW", "de": "N NO O SO S SW W NW", "fr": "N NE E SE S SO O NO", "es": "N NE E SE S SO O NO", "nl": "N NO O ZO Z ZW W NW"}


def ptext(key, lang, **kw):
    t = PUSH_TEXT[key]
    return (t.get(lang) or t["en"]).format(**kw)


def push_targets():
    """Who gets notifications: (who, subscriptions, centre, spot, settings) for each profile that has some."""
    out = []
    with _data_lock:
        P = profiles()
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


# Favourites and hidden planes (relay 31), per profile: lists of {k: reg|type|airline|flight,
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


# Relay 70: a live position counts only while the screen's fix is fresh. Boards since 1.88.0.1 send its age with each
# position request (&fix=seconds, -1: none yet); a stale one (a saved spot from a trip, before the first fix) records no
# sightings, scores nothing and starts no gap filler. Relay 72: a live request without it is stale too (only an old
# copy of the app, kept in a phone's cache, leaves it out; one logged a plane 1,100 km away from a trip's spot).
LIVE_FRESH_S = 300


def live_stale(q, place):
    if not place or place[0] != "live":
        return False
    if "fix" not in q:
        return True
    try:
        return not 0 <= float(q["fix"][0]) <= LIVE_FRESH_S
    except ValueError:
        return True


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
        return list((P["profiles"].get(pid) or {}).get("places") or [])


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


# relay 62: names that are an administrative area rather than a place (Greece's municipal units come as Nominatim's
# "city": "Ia Municipal Unit" above the village Oia, "Thira Municipal Unit" above the town Fira)
_GEO_ADMIN = re.compile(r"(?i)\b(municipal unit|regional unit|municipal district|municipality|community of|gemeindebezirk|regionalbezirk)\b")


def _geo_admin_clean(v):
    v = re.sub(r"(?i)\b(municipality|community|district|county) of\s+", "", v)
    v = re.sub(r"(?i)\s*\b(municipal unit|regional unit|municipal district|municipality|gemeindebezirk|regionalbezirk)\b\s*", " ", v)
    return re.sub(r"\s+", " ", v).strip(" ,-")


def _geo_name(a, fallback=""):
    """A place's name from Nominatim's address: the city, town or village before the area round it. Relay 62: a name
    that is an administrative area is passed over for the next one, and only cleaned up when nothing else is there."""
    a = a or {}
    near = ("city", "town", "village", "suburb", "hamlet")
    for k in near:                                   # a place, not an area
        v = str(a.get(k) or "").strip()
        if v and not _GEO_ADMIN.search(v):
            return v
    for k in near + ("city_district", "municipality", "county", "state"):   # else the nearest area, without the words
        v = _geo_admin_clean(str(a.get(k) or ""))
        if v:
            return v
    return fallback or ""


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
    # relay 62: zoom 13 (villages and suburbs; 12 stopped at the area above a village, "Ia Municipal Unit" for Oia)
    j = _geo_get(f"{NOMINATIM}/reverse?format=jsonv2&zoom=13&accept-language={urllib.parse.quote(lang)}&lat={lat:.3f}&lon={lon:.3f}")
    if not isinstance(j, dict):
        return {"status": "error"}
    return {"status": "ok", "name": _geo_name(j.get("address"), j.get("name") or "")}


# Relay 63 (Dave's to-do 3): where a sighting on the go was made, by name ("Oia, Santorini"), for the logbook search.
# A new sighting on the go keeps the phone's place to about a kilometre ("at"); each 0.02° cell is named once by
# Nominatim in the background (_where_worker) and kept in data/where.json. Older sightings on the go have no "at":
# the planes of their day, grouped within 30 km, stand in for where the phone was.
WHERE_FILE = DATA_DIR / "where.json"
WHERE_CELL = 0.02
_where = None               # "lat,lon" cell -> {"n": the place, "a": the area round it, "c": the country}; "" when unknown
_where_todo = []
_where_lock = threading.Lock()


def _fold(s):
    """Upper case without accents, for matching ("Zürich" finds "ZURICH")."""
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()


def _where_cell(lat, lon):
    r = lambda v: round(round(float(v) / WHERE_CELL) * WHERE_CELL, 2)
    return f"{r(lat)},{r(lon)}"


def where_name(lat, lon):
    """A place's name ({} until it is known: then it is asked for in the background)."""
    global _where
    k = _where_cell(lat, lon)
    with _where_lock:
        if _where is None:
            _where = _load(WHERE_FILE, {})
        w = _where.get(k)
        if w is None and k not in _where_todo and len(_where_todo) < 500:
            _where_todo.append(k)
    return w or {}


def geo_where(lat, lon):
    """The town or village at a place, the area round it (an island, a county, a state) and the country; None when
    Nominatim couldn't be asked."""
    j = _geo_get(f"{NOMINATIM}/reverse?format=jsonv2&zoom=13&accept-language=en&lat={lat:.3f}&lon={lon:.3f}")
    if not isinstance(j, dict):
        return None
    a = j.get("address") or {}
    n = _geo_name(a, "" if j.get("error") else str(j.get("name") or ""))
    area = next((v for v in (_geo_admin_clean(str(a.get(k) or "")) for k in ("island", "archipelago", "county", "state_district", "state"))
                 if v and v.lower() != n.lower()), "")
    return {"n": n[:60], "a": area[:60], "c": str(a.get("country") or "")[:60]}


def _where_sweep():
    """Once, a little after a start: every profile's older sightings on the go asked to be named, so the search finds them."""
    time.sleep(20)
    with _data_lock:
        pids = list(profiles()["profiles"])
    for pid in pids:
        try:
            sp = guest_spot(pid)
            for f in sorted(sp.dir.glob("sightings-*.json")):
                entries = _load(f, [])
                est = where_estimates(entries)
                for e in entries:
                    if isinstance(e, dict):
                        where_of(e, est)
        except Exception:
            continue


def _where_worker():
    """Names the places on the go, one a few seconds (Nominatim asks for one request a second at most)."""
    while True:
        time.sleep(3)
        with _where_lock:
            k = _where_todo[0] if _where_todo else None
        if not k:
            continue
        try:
            w = geo_where(*map(float, k.split(",")))
        except Exception:
            w = None
        with _where_lock:
            if k in _where_todo:
                _where_todo.remove(k)
            if w is not None:
                _where[k] = w
                try:
                    tmp = WHERE_FILE.with_suffix(".tmp")
                    tmp.write_text(json.dumps(_where, separators=(",", ":")), encoding="utf-8")
                    tmp.replace(WHERE_FILE)
                except OSError:
                    pass
        if w is None:
            time.sleep(60)                  # no answer: ask again later


def where_estimates(entries):
    """Sightings on the go from before relay 63 have no "at": the day's planes, grouped (each within 30 km of its
    group's middle), stand in for where the phone was. {sighting id: (lat, lon)}."""
    groups = []
    for e in entries:
        if not isinstance(e, dict) or e.get("place") != "live" or e.get("at") or not isinstance(e.get("pos"), list):
            continue
        la, lo = e["pos"][0], e["pos"][1]
        g = next((g for g in groups if _dist_km(g["lat"], g["lon"], la, lo) <= 30), None)
        if g:
            g["n"] += 1
            g["lat"] += (la - g["lat"]) / g["n"]
            g["lon"] += (lo - g["lon"]) / g["n"]
            g["ids"].append(e.get("id"))
        else:
            groups.append({"lat": la, "lon": lo, "n": 1, "ids": [e.get("id")]})
    return {i: (g["lat"], g["lon"]) for g in groups for i in g["ids"]}


def where_of(e, est=None):
    """Where a sighting on the go was made ({} when not known yet, or not on the go). One from before relay 63 has no
    "at": its place is only guessed from the day's planes, which can land on the wrong side of a bay, so since relay 64
    (Dave's choice) it gives only the country."""
    if e.get("place") != "live":
        return {}
    if e.get("at"):
        return where_name(*e["at"])
    at = (est or {}).get(e.get("id"))
    w = where_name(*at) if at else {}
    return {"c": w["c"]} if w.get("c") else {}


def lists_of(pid):
    """(favourites, hidden) of a profile."""
    with _data_lock:
        p = profiles()["profiles"].get(pid) or {}
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
_countdown = {}              # relay 56: (endpoint, hex) -> the first alert's {t, why, kind}: the live countdown that follows


def _push_prefs(p):
    p = p if isinstance(p, dict) else {}
    out = {"summary": p.get("summary") is not False, "window": p.get("window") is not False, "quiet": p.get("quiet") is not False}
    out["review"] = p.get("review") is not False          # relay 46: the week and month in review
    out["countdown"] = p.get("countdown") is not False    # relay 56: the alert counts down to the plane
    for k, d in PUSH_KINDS.items():
        out[k] = bool(p[k]) if k in p else d
    return out


def now_json(pid, st):
    """Relay 56: the plane over a profile's place right now, for the Android app's home-screen widget: the nearest one
    in the air within the spotting radius (hidden planes left out), with its status in the boards' words, its route
    when the callsign's listed one fits, and today's count. {"plane": None} when the sky is empty."""
    try:
        lat0, lon0 = float(st["lat"]), float(st["lon"])
    except (KeyError, TypeError, ValueError):
        return {"plane": None, "error": "no place"}
    radius, over = float(st.get("radiusKm") or 15), float(st.get("overKm") or 3)
    status, body, _, _ = aircraft(f"{lat0:.2f}", f"{lon0:.2f}", "25")
    try:
        planes = (json.loads(body).get("ac") or json.loads(body).get("aircraft") or []) if status == 200 else []
    except ValueError:
        planes = []
    kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57
    _, hide_list = lists_of(pid)
    best = None
    for ac in planes:
        if not isinstance(ac, dict) or ac.get("lat") is None or ac.get("alt_baro") == "ground":
            continue
        x, y = (ac["lon"] - lon0) * kx, (ac["lat"] - lat0) * ky
        d = math.hypot(x, y)
        tc, cs, reg = str(ac.get("t") or "").upper(), no_cs(ac.get("flight")), str(ac.get("r") or "").upper()
        m_ = re.match(r"^([A-Z]{3})\d", cs)
        if d > radius or _list_hit(hide_list, tc, cs, reg, m_.group(1) if m_ else ""):
            continue
        if not best or d < best[0]:
            best = (d, x, y, ac, cs, tc, reg)
    spot = guest_spot(pid)
    with _data_lock:
        spot.ensure_day()
        today = len(spot.entries)
    if not best:
        return {"plane": None, "today": today}
    d, x, y, ac, cs, tc, reg = best
    closing = False
    if ac.get("gs") and ac.get("track") is not None:
        vx, vy = math.sin(math.radians(ac["track"])), math.cos(math.radians(ac["track"]))
        closing = x * vx + y * vy < 0
    word = "OVERHEAD" if d <= over else "APPROACHING" if closing else "LEAVING"
    route = _route_for(cs) if re.fullmatch(r"[A-Z0-9]{3,8}", cs or "") else None
    if route and not _route_fits(route, (ac["lat"], ac["lon"], ac.get("track") or 0)):
        route = None
    alt = ac.get("alt_baro") if isinstance(ac.get("alt_baro"), (int, float)) else ac.get("alt_geom")
    dirs = DIRS["en"].split()
    flight = re.sub(r"^([A-Z0-9]{2})(\d)", r"\1 \2", (route or {}).get("flightIata") or "") or cs or reg or str(ac.get("hex") or "").upper()
    return {"plane": {"flight": flight,
                      "airline": (route or {}).get("airlineName") or "", "type": ac.get("desc") or tc, "reg": reg,
                      "from": (route or {}).get("from"), "to": (route or {}).get("to"), "status": word,
                      "dist": round(d, 1), "dir": dirs[int(((math.degrees(math.atan2(x, y)) + 360) % 360 + 22.5) // 45) % 8],
                      "altM": round(alt * .3048 / 10) * 10 if isinstance(alt, (int, float)) else None}, "today": today, "at": int(time.time())}


def window_planes(who, centre, spot, st):
    """Planes worth going to the window for: passing within 5 km in the next 3 minutes, with why (special, watchlist,
    military, favourite, a new type, very low; most telling first). Relay 47: shared by the alerts and the Hue pulse."""
    # rounded like the screens' requests (relay 34), so the alerts share their answer instead of asking again
    status, body, _, _ = aircraft(f"{centre[0]:.2f}", f"{centre[1]:.2f}", "25")
    if status != 200:
        return []
    try:
        planes = json.loads(body).get("ac") or json.loads(body).get("aircraft") or []
    except ValueError:
        return []
    lat0, lon0 = centre
    kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57
    with _data_lock:
        book = spot.book()
        types, learning = book.get("types", {}), time.time() - book.get("startedTs", 0) < LEARN_S
    favs = _fav_tokens(st)
    fav_list, hide_list = lists_of(who)
    out = []
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
        tc, cs, reg = str(ac.get("t") or "").upper(), no_cs(ac.get("flight")), str(ac.get("r") or "").upper()
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
        out.append({"ac": ac, "kinds": kinds, "what": what, "t": t, "cpa": cpa, "cx": cx, "cy": cy, "alt": alt, "airline": al})
    return out


def window_check(who, subs, centre, spot, st):
    """The alerts: each plane worth a look (window_planes) to the devices that asked for its kind; the alert says why."""
    want = [s_ for s_ in subs if (s_.get("prefs") or {}).get("window", True)]
    if not want:
        return
    hour = time.localtime().tm_hour
    now = time.time()
    for k in [k for k, t in _sent.items() if now - t > 3 * 3600]:
        del _sent[k]
    planes = window_planes(who, centre, spot, st)
    live = {(sub["endpoint"], pl["ac"].get("hex")) for sub in want for pl in planes}
    for k in [k for k in _countdown if k[0] in {s_["endpoint"] for s_ in want} and k not in live]:
        del _countdown[k]                            # passed (or gone): the last notification stays as it is
    for pl in planes:
        ac, kinds, what, t, cpa, cx, cy, alt = (pl[k] for k in ("ac", "kinds", "what", "t", "cpa", "cx", "cy", "alt"))
        for sub in want:
            key = (sub["endpoint"], ac.get("hex"))
            if key in _sent:
                if key in _countdown:
                    countdown_send(sub, key, pl)
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
            if pr.get("countdown"):
                _countdown[key] = {"t0": t, "why": why, "kind": bell, "at": now, "now": False}


def countdown_send(sub, key, pl):
    """Relay 56: the alert after it went out, replaced every half minute (silently) by one that counts down, with a bar
    of how much of the wait is gone; under 50 s it rings once more: "Look up now". It stops once the plane has passed."""
    c, now = _countdown[key], time.time()
    if now - c["at"] < 25:
        return
    c["at"] = now
    lang = sub.get("lang") or "en"
    t, cpa, alt = pl["t"], pl["cpa"], pl["alt"]
    d = DIRS.get(lang, DIRS["en"]).split()[int(((math.degrees(math.atan2(pl["cx"], pl["cy"])) + 360) % 360 + 22.5) // 45) % 8]
    altx = f"{round(alt * .3048 / 50) * 50:,} m" if isinstance(alt, (int, float)) else ""
    left = f"{int(t // 60)}:{int(t % 60):02d}"
    done = max(0, min(10, round(10 * (1 - t / max(c["t0"], 1)))))
    bar = "▰" * done + "▱" * (10 - done)
    ring = t <= 50 and not c["now"]
    if t <= 50:
        c["now"] = True
        title = ptext("cd_now", lang, what=pl["what"])
    else:
        title = ptext("cd_over" if cpa < 1.2 else "cd_pass", lang, what=pl["what"], left=left)
    body = " · ".join(x_ for x_ in [c["why"], ptext("cd_look", lang, dir=d) if cpa >= 1.2 else ptext("cd_up", lang), altx] if x_) + "\n" + bar + " " + left
    _deliver([sub], {"title": title, "body": body, "tag": "window-" + str(pl["ac"].get("hex")), "kind": c["kind"], "url": "/app/",
                     "update": not ring}, urgent=True)


def summary_check(who, subs, spot, st):
    """The evening summary, once a day at SUMMARY_AT (local time)."""
    if time.strftime("%H:%M") < SUMMARY_AT:
        return
    with _data_lock:
        spot.ensure_day()
        day, entries = spot.day, list(spot.entries)
        g = game3_json(spot.book(), day)
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


def review_check(who, subs, spot, st):
    """The week in review on Sunday at 20:00 and the month before on the 1st at 9:00 (local time; relay 46). Both are
    outside the quiet hours. A period without a plane sends nothing."""
    now = time.localtime()
    hm = time.strftime("%H:%M", now)
    due = []
    if now.tm_wday == REVIEW_WEEK_AT[0] and hm >= REVIEW_WEEK_AT[1]:
        due.append(("week", 0))
    if now.tm_mday == REVIEW_MONTH_AT[0] and hm >= REVIEW_MONTH_AT[1]:
        due.append(("month", 1))
    for span, back in due:
        r = None
        mark = "review" + span.capitalize()
        for sub in subs:
            if not (sub.get("prefs") or {}).get("review", True):
                continue
            if r is None:
                r = review_json(spot, span, back, prev=False)
            if sub.get(mark) == r["start"]:
                continue
            sub[mark] = r["start"]
            if not r["planes"]:
                continue
            lang = sub.get("lang") or "en"
            ra = r["rarest"] or {}
            body = ptext("rsum", lang, n=r["planes"], t=r["types"], a=r["airlines"],
                         new=ptext("newtypes", lang, x=r["newTypeCount"]) if r["newTypeCount"] else "",
                         rare=ptext("rarest", lang, x=ra.get("type") or ra.get("reg")) if ra.get("tier") in ("rare", "epic", "legendary") else "")
            _deliver([sub], {"title": ptext(span, lang), "body": body, "tag": "review", "url": f"/app/#review-{span}-{back}"})
            event("info", f"The {span} in review sent to {who}")
        if r is not None:
            with _data_lock:
                _dirty.add("profiles")


# A plane's photo for the boards' share picture (relay 47, to-do #51): a browser can't save a picture that has another
# site's photo in it, so the relay passes the photo on, from the photo sites the boards use only, images only, a few MB
# at most. The last few are kept an hour. Relay 73: never Planespotters.net's photos (their terms forbid passing them on);
# Wikipedia's model pictures now also come from thumb.wikimedia.org.
PHOTO_HOSTS = ("upload.wikimedia.org", "thumb.wikimedia.org", "airport-data.com", ".airport-data.com", "cdn.jetphotos.com")
PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
PHOTO_MAX = 4 * 1024 * 1024
_photos = collections.OrderedDict()        # url -> (time, content type, bytes)


def _photo_host_ok(u):
    sp = urllib.parse.urlsplit(u)
    h = (sp.hostname or "").lower()
    return sp.scheme in ("http", "https") and any(h == p or (p.startswith(".") and h.endswith(p)) for p in PHOTO_HOSTS)


def photo_get(u):
    """(status, content type, body) for a photo URL."""
    if not _photo_host_ok(u):
        return 400, "text/plain", b"Not a photo site"
    with _lock:
        hit = _photos.get(u)
        if hit and time.time() - hit[0] < 3600:
            _photos.move_to_end(u)
            return 200, hit[1], hit[2]
    req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if not _photo_host_ok(r.geturl()) or ctype not in PHOTO_TYPES:
                return 415, "text/plain", b"Not a photo"
            body = r.read(PHOTO_MAX + 1)
    except Exception:
        return 502, "text/plain", b"Couldn't get the photo"
    if len(body) > PHOTO_MAX:
        return 413, "text/plain", b"Too big"
    with _lock:
        _photos[u] = (time.time(), ctype, body)
        while len(_photos) > 30:
            _photos.popitem(last=False)
    return 200, ctype, body


# A plane's own photo from Planespotters.net (relay 73, to-do #95), for This aircraft and the plane cards: asked by
# registration (by hex only when that finds none) and kept only when the photo's page names the same registration (a
# hex can belong to another aircraft by now: 44D0AB gave OO-TEK's photo, not the Belgian Air Force's CH-10). Their
# terms (planespotters.net/photo/api): a User-Agent naming the app with a contact address; answers kept 24 hours at
# most (23 here, the boards keep theirs an hour more at most); the photo itself loaded only by the screen that shows
# it, straight from the address given, never kept or passed on (so not through /photo, nor in the share picture); every
# address used unchanged; the photographer credited next to the photo, which links to its page.
PS_API = "https://api.planespotters.net/pub/photos"
PS_AGENT = f"Fallblatt/{RELAY_VERSION} (+https://github.com/Belstria/overhead-board)"
PS_KEEP, PS_FAIL, PS_GAP, PS_WAIT, PS_REST = 23 * 3600, 600, 1.0, 4.0, 1800
PS_IMG = ("https://",)                     # the photo's own address must be one of these
_ps_cache = collections.OrderedDict()      # registration -> (time, photo or None, answered)
_ps_next = [0.0]                           # the earliest time for the next request: one a second
_ps_rest = [0.0]                           # refused (403, 429): no requests until then


def _ps_like(reg):
    """A registration as the start of a photo page's name (/photo/<id>/oe-lbp-austrian-airlines-...): its letters and
    digits in order, a dash allowed between them, then a dash or the end."""
    chars = re.sub(r"[^a-z0-9]", "", reg.lower())
    return re.compile("-?".join(chars) + "(-|$)") if chars else None


def _ps_first(photos, like):
    """The board's part of the first photo in an answer that shows this registration, with addresses that are theirs."""
    for p in photos or []:
        try:
            img, link = p["thumbnail_large"], p["link"]
            src, size, page = img["src"], img.get("size") or {}, urllib.parse.urlsplit(link)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        name = page.path.rstrip("/").rsplit("/", 1)[-1].lower()
        if (like and like.match(name) and page.scheme == "https" and (page.hostname or "").endswith("planespotters.net")
                and str(src).startswith(PS_IMG)):
            return {"src": src, "w": size.get("width"), "h": size.get("height"), "link": link,
                    "by": str(p.get("photographer") or "").strip()[:80]}
    return None


def _ps_ask(kind, value):
    """Planespotters' photos for a registration or a hex (a list, maybe empty), or None when they can't be asked now
    (refused a while ago, too many lookups waiting) or didn't answer."""
    now = time.time()
    with _lock:
        if now < _ps_rest[0]:
            return None
        at = max(now, _ps_next[0])
        if at - now > PS_WAIT:
            return None
        _ps_next[0] = at + PS_GAP
    if at > now:
        time.sleep(at - now)
    status, _, body, _ = fetch(f"{PS_API}/{kind}/{urllib.parse.quote(value, safe='')}", timeout=8,
                               headers={"User-Agent": PS_AGENT, "Accept": "application/json"})
    if status in (403, 429):
        with _lock:
            _ps_rest[0] = time.time() + PS_REST
        event("warn", f"Planespotters.net refused a photo lookup (HTTP {status}); asking again in {PS_REST // 60} minutes")
        return None
    try:
        j = json.loads(body) if status == 200 else None
    except ValueError:
        j = None
    if not isinstance(j, dict):
        return None
    return j["photos"] if isinstance(j.get("photos"), list) else [] if "error" in j else None   # "Reg input missing": none


def plane_photo(reg, hex_=""):
    """{"photo": {src, w, h, link, by} or None} for a registration, or None when Planespotters couldn't be asked."""
    key = re.sub(r"[^A-Z0-9-]", "", str(reg or "").upper())[:12]
    hex_ = re.sub(r"[^0-9A-F]", "", str(hex_ or "").upper())[:6]
    like = _ps_like(key)
    if not like:
        return {"photo": None}
    now = time.time()
    with _lock:
        hit = _ps_cache.get(key)
        if hit and now - hit[0] < (PS_KEEP if hit[2] else PS_FAIL):
            return {"photo": hit[1]} if hit[2] else None
    photos = _ps_ask("reg", key)
    photo = _ps_first(photos, like)
    if photos is not None and not photo and len(hex_) == 6:
        photos = _ps_ask("hex", hex_)
        photo = _ps_first(photos, like)
    answered = photos is not None
    with _lock:
        _ps_cache[key] = (now, photo, answered)
        _ps_cache.move_to_end(key)
        while len(_ps_cache) > 3000:
            _ps_cache.popitem(last=False)
    return {"photo": photo} if answered else None


# ---------- the cards' facts (relay 74, to-do #113) ----------
# The model, airline and airport cards' facts from Wikipedia and Wikidata, cleaned here once per page and kept about 30
# days (data/facts.json), so the boards get plain values: Wikipedia's infobox and specs table need their templates,
# references and units taken apart. A model by its Wikipedia page (the one the board's model lookup found); an airline by
# its ICAO code through Wikidata (P230: the very company, subsidiaries too; by name, TUI and DHL found the wrong one);
# an airport by its IATA code (P238). Wikipedia's words are CC BY-SA (the cards link the page); Wikidata's are CC0.
# Relay 78 (1.96.2, to-do #129): the facts database. They live in data/facts.db (SQLite, read per card, not held in
# memory; facts.json's moved in once), and once a month at night a background job (_facts_worker) refreshes every
# airline still flying, every airport with an IATA code and the models (MODEL_TITLES, and every page a card asked for),
# so a first tap finds its facts at once. The cards' lookups below stay the same: run in the job they ask for what they
# need (_Need), the job fetches it for 50 cards together (50 items or pages a request) and runs them again. A key the
# database doesn't have yet (a new type) is still looked up on its first tap.
WM_AGENT = f"Fallblatt/{RELAY_VERSION} (+https://github.com/Belstria/overhead-board)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
SPARQL_API = "https://query.wikidata.org/sparql"
FACTS_FILE = DATA_DIR / "facts.json"          # relay 74–77's; moved into FACTS_DB once (and left as it was)
FACTS_DB = DATA_DIR / "facts.db"
FACTS_KEEP, FACTS_FAIL, FACTS_GAP = 40 * 86400, 900, 0.2
FACTS_EVERY = 28 * 86400       # the whole database is refreshed this often ...
FACTS_NIGHT = (4 * 60 + 10, 6 * 60)   # ... between these minutes of the night (the relay's time): after the 03:40 backup
FACTS_IMG_W = 500              # the photos' width on the cards (the refresh keeps the photo's own address at this size)
FACTS_TEXT = 1500              # Wikipedia's introduction, at most this many characters (More info)
_facts_busy = {}               # "kind:key" -> threading.Event while one request looks it up (the others wait for it)
_facts_failed = {}             # "kind:key" -> when Wikimedia last couldn't be asked about it
_wm_next = [0.0]               # the next request to Wikimedia, at most five a second
# The board's model pages (its TYPES and MODEL_PAGES as its model lookup finds them): node tools/test/model_pics.js --relay
MODEL_TITLES ="ATR 42|ATR 72|Aero Commander 500 family|Aero L-39 Albatros|AgustaWestland AW101|AgustaWestland AW109|AgustaWestland AW119 Koala|AgustaWestland AW139|AgustaWestland AW169|AgustaWestland AW189|Airbus A220|Airbus A300|Airbus A310|Airbus A318|Airbus A319|Airbus A320 family|Airbus A320neo family|Airbus A321|Airbus A321neo|Airbus A330|Airbus A330neo|Airbus A340|Airbus A350|Airbus A380|Airbus A400M Atlas|Airbus Beluga|Airbus BelugaXL|Airbus C295|Airbus Helicopters H160|Airbus Helicopters H175|Airship|Antonov An-12|Antonov An-124 Ruslan|Antonov An-140|Antonov An-148|Antonov An-2|Antonov An-22|Antonov An-225 Mriya|Antonov An-24|Antonov An-26|Antonov An-28|Antonov An-30|Antonov An-32|Antonov An-72|Aquila A 210|Autogyro|Aviat Husky|Aérospatiale Alouette II|Aérospatiale Alouette III|Aérospatiale Corvette|Aérospatiale Gazelle|Aérospatiale N 262|BAC One-Eleven|Beechcraft 1900|Beechcraft Baron|Beechcraft Bonanza|Beechcraft Duke|Beechcraft King Air|Beechcraft Model 18|Beechcraft Model 99|Beechcraft Premier I|Beechcraft Super King Air|Bell 206|Bell 212|Bell 407|Bell 412|Bell 429 GlobalRanger|Bell 505 Jet Ranger X|Bell UH-1 Iroquois|Beriev Be-200|Boeing 707|Boeing 717|Boeing 720|Boeing 727|Boeing 737|Boeing 737 Classic|Boeing 737 MAX|Boeing 737 Next Generation|Boeing 747|Boeing 747-400|Boeing 747-8|Boeing 747SP|Boeing 757|Boeing 767|Boeing 777|Boeing 777X|Boeing 787 Dreamliner|Boeing AH-64 Apache|Boeing B-52 Stratofortress|Boeing C-17 Globemaster III|Boeing CH-47 Chinook|Boeing Dreamlifter|Boeing E-3 Sentry|Boeing KC-135 Stratotanker|Boeing P-8 Poseidon|Boeing RC-135|Bombardier CRJ100/200|Bombardier CRJ700 series|Bombardier Challenger 300|Bombardier Challenger 600 series|Bombardier Global 7500|Bombardier Global Express|British Aerospace 125|British Aerospace 146|British Aerospace ATP|British Aerospace Jetstream|British Aerospace Jetstream 41|Britten-Norman BN-2 Islander|CASA C-212 Aviocar|CASA/IPTN CN-235|Canadair CL-415|Cessna 150|Cessna 152|Cessna 170|Cessna 172|Cessna 177 Cardinal|Cessna 180 Skywagon|Cessna 182 Skylane|Cessna 185 Skywagon|Cessna 206|Cessna 208 Caravan|Cessna 210 Centurion|Cessna 310|Cessna 340|Cessna 402|Cessna 404 Titan|Cessna 408 SkyCourier|Cessna 414|Cessna 421 Golden Eagle|Cessna 441 Conquest II|Cessna Citation Excel|Cessna Citation I|Cessna Citation II|Cessna Citation III|Cessna Citation Latitude|Cessna Citation Longitude|Cessna Citation Mustang|Cessna Citation Sovereign|Cessna Citation V|Cessna Citation X|Cessna CitationJet/M2|Cessna Skymaster|Cessna T303 Crusader|Cirrus SR20|Cirrus SR22|Cirrus Vision SF50|Comac C909|Comac C919|Concorde|Convair CV-240 family|Daher Kodiak|Dassault Falcon 10|Dassault Falcon 20|Dassault Falcon 2000|Dassault Falcon 50|Dassault Falcon 6X|Dassault Falcon 7X|Dassault Falcon 900|Dassault Rafale|De Havilland Canada DHC-5 Buffalo|De Havilland Canada DHC-6 Twin Otter|De Havilland Canada Dash 7|De Havilland Canada Dash 8|Diamond DA20 Katana|Diamond DA40 Diamond Star|Diamond DA42 Twin Star|Diamond DA50|Diamond DA62|Diamond HK36 Super Dimona|Dornier 228|Dornier 328|Douglas DC-3|Douglas DC-8|Eclipse 500|Embraer C-390 Millennium|Embraer E-Jet E2 family|Embraer E-Jet family|Embraer EMB 110 Bandeirante|Embraer EMB 120 Brasilia|Embraer ERJ family|Embraer Legacy 450/500 and Praetor 500/600|Embraer Legacy 600|Embraer Phenom 100|Embraer Phenom 300|Enstrom F-28|Eurocopter AS332 Super Puma|Eurocopter AS350 Écureuil|Eurocopter AS355 Écureuil 2|Eurocopter AS365 Dauphin|Eurocopter EC120 Colibri|Eurocopter EC130|Eurocopter EC135|Eurocopter EC145|Eurocopter EC155|Eurocopter EC725|Eurocopter Tiger|Eurofighter Typhoon|Evektor SportStar|Extra EA-300|Fairchild Dornier 328JET|Fairchild Swearingen Metroliner|Fokker 100|Fokker 50|Fokker 70|Fokker F27 Friendship|Fokker F28 Fellowship|GAF Nomad|General Dynamics F-16 Fighting Falcon|Glider (sailplane)|Grob G 109|Grob G 115|Grob G 120|Grumman G-73 Mallard|Grumman Gulfstream I|Guimbal Cabri G2|Gulfstream G100|Gulfstream G200|Gulfstream G280|Gulfstream G400/G500/G600|Gulfstream G550|Gulfstream G650/G700/G800|Gulfstream III|Gulfstream IV|Harbin Y-12|Hawker 400|Hawker 4000|Hawker 800|Hawker Siddeley HS 748|Honda HA-420 HondaJet|Hot air balloon|IAI Westwind|Ilyushin Il-114|Ilyushin Il-18|Ilyushin Il-62|Ilyushin Il-76|Ilyushin Il-86|Ilyushin Il-96|Junkers Ju 52|Kamov Ka-27|Learjet 31|Learjet 35|Learjet 40|Learjet 45|Learjet 55|Learjet 60|Learjet 70/75|Leonardo M-346|Let L-410 Turbolet|Lockheed C-130 Hercules|Lockheed C-5 Galaxy|Lockheed L-1011 TriStar|Lockheed L-188 Electra|Lockheed Martin C-130J Super Hercules|Lockheed Martin F-35 Lightning II|Lockheed P-3 Orion|MBB Bo 105|MBB/Kawasaki BK 117|MD Helicopters MD 500|MD Helicopters MD Explorer|McDonnell Douglas DC-10|McDonnell Douglas DC-9|McDonnell Douglas MD-11|McDonnell Douglas MD-80|McDonnell Douglas MD-90|Mil Mi-24|Mil Mi-8|Mitsubishi MU-2|Mooney M20|Mudry CAP 10|NAMC YS-11|NHIndustries NH90|Panavia Tornado|Partenavia P.68|Piaggio P.180 Avanti|Pilatus PC-12|Pilatus PC-21|Pilatus PC-24|Pilatus PC-6 Porter|Pilatus PC-7|Pilatus PC-9|Piper Aerostar|Piper J-3 Cub|Piper PA-18 Super Cub|Piper PA-20 Pacer|Piper PA-24 Comanche|Piper PA-28 Cherokee|Piper PA-30 Twin Comanche|Piper PA-31 Navajo|Piper PA-31T Cheyenne|Piper PA-32 Cherokee Six|Piper PA-32R|Piper PA-34 Seneca|Piper PA-38 Tomahawk|Piper PA-42 Cheyenne|Piper PA-44 Seminole|Piper PA-46|Reims-Cessna F406 Caravan II|Robin DR400|Robinson R22|Robinson R44|Robinson R66|SOCATA TB family|SOCATA TBM|Saab 105|Saab 2000|Saab 340|Schweizer S300|Short 330|Short 360|Short Belfast|Short SC.7 Skyvan|Sikorsky S-76|Sikorsky S-92|Sikorsky UH-60 Black Hawk|Tupolev Tu-134|Tupolev Tu-154|Tupolev Tu-204|Ultralight aviation|Yakovlev SJ-100|Yakovlev Yak-40|Yakovlev Yak-42".split("|")
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def _wm_get(url, params):
    """A Wikimedia API answer (JSON), or None."""
    with _lock:
        at = max(time.time(), _wm_next[0])
        _wm_next[0] = at + FACTS_GAP
    if at > time.time():
        time.sleep(at - time.time())
    status, _, body, _ = fetch(url + "?" + urllib.parse.urlencode({"format": "json", "formatversion": "2", **params}), timeout=12,
                               headers={"User-Agent": WM_AGENT, "Accept": "application/json"})
    if status != 200:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


class _Need(Exception):
    """In the monthly refresh: a card's lookup needs something not fetched yet (in _wm_batch.need)."""


class _Stop(Exception):
    """The monthly refresh stops for tonight: the night is over, or Wikimedia doesn't answer."""


_wm_batch = threading.local()  # the refresh's own thread: .on, .since, .stop_at, .need, .stats and what it fetched


def _batch():
    """The monthly refresh's state when this thread is the refresh, else None (a card asked: the lookups ask alone)."""
    return _wm_batch if getattr(_wm_batch, "on", False) else None


def _need(what):
    _wm_batch.need.update(what)
    raise _Need()


def _wm_batch_get(url, params, timeout=60):
    """One request of the refresh: Wikimedia's answer (JSON). One at a time, waiting as Retry-After and maxlag ask, and
    again after an error (five times, longer each time); _Stop when it still doesn't answer or the night is over."""
    b, sparql = _wm_batch, url == SPARQL_API
    params = {"format": "json", **({} if sparql else {"formatversion": "2", "maxlag": "5"}), **params}
    status = None
    for i in range(6):
        with _lock:
            at = max(time.time(), _wm_next[0])
            _wm_next[0] = at + FACTS_GAP
        if at > time.time():
            time.sleep(at - time.time())
        if time.time() > b.stop_at:
            raise _Stop("the night is over")
        status, _, body, hdrs = fetch(url + "?" + urllib.parse.urlencode(params), timeout=timeout, headers={
            "User-Agent": WM_AGENT, "Accept": "application/sparql-results+json" if sparql else "application/json"})
        b.stats["requests"] += 1
        b.stats["bytes"] += len(body or b"")
        try:
            j = json.loads(body) if status == 200 else None
        except ValueError:
            j = None
        err = (j.get("error") or {}) if isinstance(j, dict) else {}
        if isinstance(j, dict) and not err:
            return j
        if err and err.get("code") not in ("maxlag", "ratelimited", "internal_api_error_DBQueryTimeoutError"):
            event("warn", f"Card facts refresh: Wikimedia said {err.get('code')} ({str(err.get('info'))[:120]})", echo=False)
            return {}                                   # (those cards get what the others had; not the whole night stopped)
        wait = _num(str((hdrs or {}).get("Retry-After") or "")) if status in (429, 503) or err else None
        time.sleep(min(600, max(1, wait) if wait else 15 * 3 ** i))
    raise _Stop(f"Wikimedia didn't answer ({status})")


def _wm_pages(url, titles, params):
    """Pages by title in one request (and its continuations: extracts come 20 at a time, long pages later): {asked
    title: page or None}, through normalized titles and redirects."""
    pages, alias, cont = {}, {}, {"continue": ""}
    while cont:
        j = _wm_batch_get(url, {"action": "query", "titles": "|".join(titles), "redirects": "1", **params, **cont})
        q, cont = j.get("query") or {}, j.get("continue")
        for x in (q.get("normalized") or []) + (q.get("redirects") or []):
            alias[x.get("from")] = x.get("to")
        for p in q.get("pages") or []:
            have = pages.setdefault(p.get("title"), {})
            have.update({k: v for k, v in p.items() if not have.get(k)})
    out = {}
    for t in titles:
        f = t
        for _ in range(4):
            f = alias.get(f, f)
        out[t] = pages.get(f)
    return out


def _wt_templates(text, prefixes):
    """The bodies (without the braces) of the templates in wikitext whose name starts with one of `prefixes`."""
    out, low = [], text.lower()
    for pre in prefixes:
        i = 0
        while True:
            i = low.find("{{" + pre, i)
            if i < 0:
                break
            depth, j = 0, i
            while j < len(text):
                two = text[j:j + 2]
                if two == "{{":
                    depth, j = depth + 1, j + 2
                elif two == "}}":
                    depth, j = depth - 1, j + 2
                    if depth == 0:
                        break
                else:
                    j += 1
            out.append(text[i + 2:j - 2])
            i = j
    return out


def _wt_split(body):
    """A template's parts at its own "|" (not those inside a nested template or link)."""
    parts, cur, depth, i = [], [], 0, 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur.append(two)
            i += 2
        elif two in ("}}", "]]"):
            depth -= 1
            cur.append(two)
            i += 2
        elif body[i] == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(body[i])
            i += 1
    parts.append("".join(cur))
    return parts


def _wt_strip(v):
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"<ref[^>/]*/>", "", v, flags=re.I)
    return re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.S | re.I)


def _wt_params(body):
    """A template's named parameters, keys in lower case with spaces (first_flight and "first flight" alike)."""
    out = {}
    for p in _wt_split(_wt_strip(body))[1:]:
        k, eq, v = p.partition("=")
        if eq:
            out[re.sub(r"[\s_]+", " ", k).strip().lower()] = v.strip()
    return out


def _wt_tpl(inner):
    """What a template shows, as far as the cards care (innermost templates first)."""
    parts = [p.strip() for p in _wt_split(inner)]
    name, args = parts[0].lower().replace("_", " ").strip(), parts[1:]
    pos = [a for a in args if not re.match(r"^[\w ]+=", a)]
    if re.match(r"^(start date|start-date|end date|birth date|dts|date)\b", name):
        n = [a for a in pos if re.fullmatch(r"\d{1,4}", a)]
        if n:
            return "-".join([n[0]] + [f"{int(x):02d}" for x in n[1:3]])
        return pos[0] if pos else ""
    if name.startswith("as of"):
        n = [a for a in pos if re.fullmatch(r"\d{1,4}", a)]
        return f" (as of {'-'.join([n[0]] + [f'{int(x):02d}' for x in n[1:2]])})" if n else ""
    if name in ("ubl", "unbulleted list", "plainlist", "plain list", "flatlist", "flat list", "hlist", "bulleted list", "ublist", "collapsible list", "unbulleted"):
        return "\n".join(re.sub(r"^\s*\*\s*", "", x) for a in pos for x in a.split("\n") if x.strip())
    if name in ("ndash", "snd", "spaced ndash", "–", "spnd", "nbsp", "sndash", "en dash"):
        return "–" if "nbsp" not in name else " "
    if name in ("mdash", "spaced mdash"):
        return "—"
    if name in ("convert", "cvt") and len(pos) >= 2:
        return f"{pos[0]} {pos[1]}" if pos[1] not in ("-", "–", "to", "and") or len(pos) < 4 else f"{pos[0]}–{pos[2]} {pos[3]}"
    if name.startswith("#expr:"):                                     # a sum the page works out: 1945-226-709-86
        e = parts[0].split(":", 1)[1].replace(" ", "")
        if re.fullmatch(r"\d+(?:\.\d+)?(?:[+-]\d+(?:\.\d+)?){0,9}", e):
            v = sum(float(n) * (-1 if s == "-" else 1) for s, n in re.findall(r"([+-]?)(\d+(?:\.\d+)?)", e))
            return str(int(v) if v.is_integer() else round(v, 2))
        return ""
    if name in ("nowrap", "nobr", "small", "sic", "big", "nobold", "noitalic", "nts", "ntsh", "val", "formatnum", "abbr", "flagcountry", "flag",
                "flagicon", "lang", "lang-fr", "transl", "nowrap begin") and pos:
        return pos[1] if name == "lang" and len(pos) > 1 else pos[0] if name != "flagicon" else ""
    if name.startswith(("efn", "sfn", "refn", "cn", "citation needed", "r|", "rp", "cite", "notetag", "#tag", "update", "when", "clarify", "dubious",
                        "better source", "verify", "fact", "by whom", "which", "failed verification", "inflation", "ref", "nbsp")) or name in ("r",):
        return ""
    return pos[0] if len(pos) == 1 else ""


def _wt_text(v):
    """Wikitext as plain text: no references, notes or markup; links as their words; line breaks kept as "\n"."""
    v = _wt_strip(v or "")
    v = re.sub(r"<br\s*/?>", "\n", v, flags=re.I)
    for _ in range(8):
        w = re.sub(r"\{\{([^{}]*)\}\}", lambda m: _wt_tpl(m.group(1)), v)
        if w == v:
            break
        v = w
    v = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", v, flags=re.I)
    v = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", v)
    v = re.sub(r"\[https?://\S+\]", "", v)
    v = re.sub(r"'{2,}", "", v)
    v = re.sub(r"<[^>]+>", "", v)
    v = html.unescape(v).replace(" ", " ")
    v = re.sub(r"[ \t]+", " ", v)
    return "\n".join(x.strip(" ,;") for x in v.split("\n") if x.strip(" ,;")).strip()


def _wt_link(v):
    """The page the first link in a value leads to ("" for none)."""
    m = re.search(r"\[\[([^\]|#]+)", _wt_strip(v or ""))
    return m.group(1).strip() if m and not re.match(r"(?i)(file|image|category):", m.group(1)) else ""


def _num(s):
    """The first number in a text (4,442; 199; 1.5 million as 1500000), or None. An "as of" note doesn't count."""
    s = re.sub(r"\(as of[^)]*\)", "", str(s or ""), flags=re.I)
    s = re.sub(r"(?i)^\s*(as of|in|by)\s+[^,]*\d{4}\s*,\s*", "", s)
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(million|billion)?", s)
    if not m:
        return None
    n = float(m.group(1).replace(",", "") + (m.group(2) or ""))
    n *= {"million": 1e6, "billion": 1e9}.get((m.group(3) or "").lower(), 1)
    return int(n) if n == int(n) else n


def _date(s):
    """A text's first date as "YYYY-MM-DD", "YYYY-MM" or "YYYY" (1850-2099), or ""."""
    s = str(s or "")
    m = re.search(r"\b(1[89]\d\d|20\d\d)-(\d\d)(?:-(\d\d))?\b", s)
    if m:
        return "-".join(x for x in m.groups() if x)
    mo = "|".join(_MONTHS)
    m = re.search(rf"(?i)\b(\d{{1,2}})\s+({mo})\s+(1[89]\d\d|20\d\d)\b", s) or re.search(rf"(?i)\b({mo})\s+(\d{{1,2}}),?\s+(1[89]\d\d|20\d\d)\b", s)
    if m:
        g = m.groups()
        d, mon = (g[0], g[1]) if g[0].isdigit() else (g[1], g[0])
        return f"{g[2]}-{_MONTHS.index(mon.lower()) + 1:02d}-{int(d):02d}"
    m = re.search(rf"(?i)\b({mo})\s+(1[89]\d\d|20\d\d)\b", s)
    if m:
        return f"{m.group(2)}-{_MONTHS.index(m.group(1).lower()) + 1:02d}"
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", s)
    return m.group(1) if m else ""


def _wiki_page(title):
    """An English Wikipedia page: (title, wikitext, its introduction as plain text), or None; False when not answered."""
    b = _batch()
    if b:
        if not b.pages.get(title, (False,))[0]:
            _need([("page", title)])
        p = b.pages[title][1]
    else:
        j = _wm_get(WIKI_API, {"action": "query", "prop": "revisions|extracts|pageprops", "rvprop": "content", "rvslots": "main",
                               "exintro": "1", "explaintext": "1", "ppprop": "disambiguation", "redirects": "1", "titles": title})
        if j is None:
            return False
        p = ((j.get("query") or {}).get("pages") or [{}])[0]
    if p.get("missing") or p.get("invalid") or "disambiguation" in (p.get("pageprops") or {}):
        return None
    try:
        wt = p["revisions"][0]["slots"]["main"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return p.get("title") or title, wt, _intro(p.get("extract") or "")


def _intro(text):
    """Wikipedia's introduction for More info: whole paragraphs up to FACTS_TEXT characters (at least the first)."""
    paras, out = [p.strip() for p in text.split("\n") if p.strip()], []
    for p in paras:
        if out and sum(len(x) + 1 for x in out) + len(p) > FACTS_TEXT:
            break
        out.append(p)
    t = "\n".join(out)
    return t if len(t) <= FACTS_TEXT + 400 else t[:FACTS_TEXT].rsplit(" ", 1)[0] + " …"


def _wiki_extract(title):
    """A page's introduction for More info (an airport's, without its wikitext), or None: not answered."""
    b = _batch()
    if b:
        if title not in b.pages:
            _need([("extract", title)])
        p = b.pages[title][1]
    else:
        j = _wm_get(WIKI_API, {"action": "query", "prop": "extracts", "exintro": "1", "explaintext": "1", "redirects": "1", "titles": title})
        if j is None:
            return None
        p = ((j.get("query") or {}).get("pages") or [{}])[0]
    return _intro(p.get("extract") or "")


def _wiki_url(title):
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="()_,'-")


def _infobox(wt, prefixes):
    """The named parameters of the page's infobox templates (several, as "Infobox aircraft begin" and "... type"),
    from its introduction only (later infoboxes are about something else)."""
    head = re.split(r"\n==[^=]", wt, maxsplit=1)[0]
    out = {}
    for b in _wt_templates(head, prefixes):
        for k, v in _wt_params(b).items():
            out.setdefault(k, v)
    return out


def _spec_rows(wt):
    """The first table of the page's Specifications section, as (label, first value) in wikitext: airliners give their
    numbers there (one column per variant; the first is the page's main one) instead of the specs template."""
    m = re.search(r"\n==\s*(?:technical )?specifications?\b[^=\n]*==\s*\n", wt, flags=re.I)
    if not m:
        return []
    sec = re.split(r"\n==[^=]", wt[m.end():], maxsplit=1)[0]
    t = sec.find("{|")
    if t < 0:
        return []
    rows = []
    for row in re.split(r"\n\|-[^\n]*", sec[t:].split("\n|}", 1)[0]):
        label, vals = "", []
        for ln in row.split("\n"):
            if ln.startswith("!") and not label:
                cells = ln[1:].split("!!")
                label = re.sub(r'^\s*[\w-]+\s*=\s*"?[^|"\[\]{}]*"?\s*\|(?!\|)', "", cells[0])
                vals += [c for c in cells[1:] if c.strip()]
                if "||" in label:
                    label, *more = label.split("||")
                    vals += more
            elif ln.startswith("|") and not ln.startswith(("|}", "|+", "|-")):
                vals += ln[1:].split("||")
        if label and vals:
            v = re.sub(r'^\s*(?:[\w-]+\s*=\s*"?[^|"\[\]{}]*"?\s*)+\|(?!\|)', "", vals[0])
            rows.append((_wt_text(label).lower(), v))
    return rows


_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                                     "seventeen eighteen nineteen twenty".split())}


def _qty(text, units):
    """The first "<number> <unit>" of these units in a text: (number, unit), or (None, "")."""
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(" + "|".join(units) + r")\b", text or "")
    return (float(m.group(1).replace(",", "")), m.group(2)) if m else (None, "")


def _seats(text):
    """The most passengers a capacity text names ("three passengers", "396 (two classes) or 365 ... passengers")."""
    t = re.sub(r"(?i)\b(" + "|".join(_WORDS) + r")\b", lambda m: str(_WORDS[m.group(1).lower()]), text or "")
    out = []
    for part in re.split(r"(?<!\d),|,(?!\d{3})|[;\n]", t):
        if not re.search(r"(?i)passeng|seat|pax|people|persons|occupants|troops", part):
            continue
        part = re.sub(r"(?i)(\d{1,3}(,\d{3})+|\d+)(?:\.\d+)?\s*(?:lb|kg|m3|m2|cu ?ft|ft|in(?!\s+[a-z])|cm|t|l|us gal|ld3s?)\b", "", part)
        part = re.sub(r"(?i)\b\d+\s*-?\s*class(es)?\b|\b\d+\s*(?:crew|pilots?)\b", "", part)
        out += [int(x.replace(",", "")) for x in re.findall(r"\b(\d{1,3}(?:,\d{3})?)\b", part)]
    out = [n for n in out if 1 <= n <= 900]
    return max(out) if out else None


def _first(*vals):
    return next((v for v in vals if v), "")


def _list(v, n=3):
    """A value's items (a list template, lines or commas), as text."""
    t = _wt_text(v)
    items = [x.strip() for x in re.split(r"\n|•|·|;", t) if x.strip()]
    if len(items) == 1 and t.count(",") >= 1 and not re.search(r"\d,\d", t):
        items = [x.strip() for x in t.split(",") if x.strip()]
    return items[:n]


def model_facts(title):
    """A model's facts from its Wikipedia page (the infobox and the first specs table), or None; False: not answered."""
    pg = _wiki_page(title)
    if not pg:
        return pg
    title, wt, text = pg
    ib = _infobox(wt, ("infobox aircraft", "infobox_aircraft", "infobox military aircraft", "infobox helicopter", "infobox weapon"))
    specs = next((_wt_params(b) for b in _wt_templates(wt, ("aircraft specs", "aircraft specifications", "aerospecs"))), {})
    f = {}
    for k, keys in (("firstFlight", ("first flight",)), ("introduced", ("introduction", "introduced", "introduced date", "entered service"))):
        d = _date(_wt_text(_first(*(ib.get(x) for x in keys))))
        if d:
            f[k] = d
    st = _wt_text(ib.get("status", "")).split("\n")[0]
    if st and len(st) < 60:
        f["status"] = st
    users = _list(ib.get("primary user", ""), 1) + _list(ib.get("more users", ""), 3)
    users = [re.sub(r"\s*\((?:historical|former|retired|formerly)\)\s*$", "", u, flags=re.I) for u in users]
    users = [u for u in users if 2 < len(u) < 60 and not re.search(r"(?i)see |list of|various|private|civil(ian)? (operators|users)", u)]
    if users:
        f["mainUser"] = users[0]
        if users[1:]:
            f["moreUsers"] = users[1:4]
    built = re.sub(r"\(\s*\(as of", "(as of", _wt_text(_first(ib.get("number built"), ib.get("built")))).replace("))", ")")
    n = _num(built)
    if n and n >= 1:
        f["built"] = int(n)
        if re.search(r"(?i)^\s*(over|more than|at least)|\+", built):
            f["builtMore"] = True                                        # "44,000+": at least
        m = re.search(r"\(as of (\d{4}(?:-\d\d)?)\)", built)
        asof = m.group(1) if m else _date(re.split(r"(?i)as of|at end of|by end of|in\b", built, maxsplit=1)[1]) if re.search(r"(?i)as of|at end of|by end of", built) else ""
        if asof:
            f["builtAsOf"] = asof
    prod = _wt_text(_first(ib.get("produced"), ib.get("construction date"), ib.get("production"), ib.get("manufactured")))
    ys = re.findall(r"\b(1[89]\d\d|20\d\d)\b", prod)
    if ys:
        f["producedFrom"] = int(ys[0])
        if re.search(r"(?i)present|today|ongoing|current", prod):
            f["producedTo"] = "present"
        elif len(ys) > 1:
            f["producedTo"] = int(ys[-1])
    dev = _first(ib.get("developed from"), ib.get("developed_from"))
    if dev:
        dt, dl = _list(dev, 1), _wt_link(dev)
        if dt:
            f["developedFrom"] = {"name": dt[0], "page": dl or dt[0]}
    rows = [] if specs else _spec_rows(wt)                       # no specs template: the table (airliners)
    row = lambda rx, no=r"$^": next((v for k, v in rows if re.search(rx, k) and not re.search(no, k)), "")   # noqa: E731
    seats = _seats(_wt_text(specs.get("capacity", "")))
    if not specs:
        seats = max([n for k, v in rows if re.search(r"seat|passeng|pax|capacity|exit limit|class", k) and not re.search(r"cargo|fuel|crew|freight|volume|payload|baggage", k)
                     for n in [_num(_wt_text(v))] if n and 1 <= n <= 900], default=None)
    if seats:
        f["seats"] = int(seats)
    for k, base, rx in (("length", "length", r"^(overall )?length"), ("span", "span", r"wingspan|^span|^wing$|^wings$"), ("height", "height", r"^(overall )?height"),
                        ("rotor", "main rotor diameter", r"rotor diameter")):
        v = _num(_wt_text(specs.get(base + " m", "")))
        if not v and _num(_wt_text(specs.get(base + " ft", ""))):
            v = _num(_wt_text(specs.get(base + " ft"))) * 0.3048 + (_num(_wt_text(specs.get(base + " in", ""))) or 0) * 0.0254
        if not v and rows:
            q, u = _qty(_wt_text(row(rx, r"cabin|fuselage|wheel|area|sweep loading")), ("m", "ft"))
            v = q * 0.3048 if q and u == "ft" else q
        if v and 1 < v < 150:
            f[k] = round(v, 2)
    rng = _num(_wt_text(specs.get("range km", "")))
    if not rng and _num(_wt_text(specs.get("range nmi", ""))):
        rng = _num(_wt_text(specs.get("range nmi"))) * 1.852
    if not rng and _num(_wt_text(specs.get("range miles", ""))):
        rng = _num(_wt_text(specs.get("range miles"))) * 1.609344
    if not rng and rows:
        q, u = _qty(_wt_text(row(r"range", r"ferry|combat")), ("km", "nmi", "mi", "miles"))
        rng = q and q * {"km": 1, "nmi": 1.852}.get(u, 1.609344)
    if rng and 50 < rng < 25000:
        f["range"] = int(round(rng))
    spd = _num(_wt_text(_first(specs.get("max speed kmh"), specs.get("cruise speed kmh"))))
    if not spd and _num(_wt_text(_first(specs.get("max speed kts"), specs.get("cruise speed kts")))):
        spd = _num(_wt_text(_first(specs.get("max speed kts"), specs.get("cruise speed kts")))) * 1.852
    if spd and 50 < spd < 4000:
        f["speed"] = int(round(spd))
    en, name, kind = _num(_wt_text(specs.get("eng1 number", ""))), _wt_text(specs.get("eng1 name", "")), _wt_text(specs.get("eng1 type", "")).lower()
    if not specs and rows:
        lab = next((k for k, v in rows if re.search(r"^engines?\b|powerplant|^engine \(", k)), "")
        name = re.split(r",|\(", _wt_text(row(r"^engines?\b|powerplant|^engine \(")).split("\n")[0])[0].strip()
        m = re.search(r"[×x]\s*(\d)", lab) or re.match(r"(\d)\s*[×x]\s*", name)
        en = int(m.group(1)) if m else None
        name = re.sub(r"\s+(or|and|/)$", "", re.sub(r"^\d\s*[×x]\s*", "", name)).strip()
        if name and not en:
            f["engines"] = {"name": name[:60]}
    kind = next((k for k in ("turbofan", "turboprop", "turboshaft", "turbojet", "piston", "electric") if k in kind), "")
    if en and 1 <= en <= 10 and (name or kind):
        f["engines"] = {"n": int(en), **({"name": name.split("\n")[0][:60]} if name else {}), **({"kind": kind} if kind else {})}
    return {"kind": "model", "title": title, "url": _wiki_url(title), "text": text, "facts": f}


def _wd_find(prop, value):
    """The Wikidata items with this identifier (an airline's ICAO code, an airport's IATA code): their ids, or None."""
    b = _batch()
    if b and prop in b.find:                     # the refresh has the whole list from Wikidata's query service
        return list(b.find[prop].get(value, []))
    j = _wm_get(WIKIDATA_API, {"action": "query", "list": "search", "srlimit": "10", "srsearch": f"haswbstatement:{prop}={value}"})
    if j is None:
        return None
    return [h["title"] for h in (j.get("query") or {}).get("search") or [] if re.fullmatch(r"Q\d+", h.get("title", ""))]


def _wd_items(ids, props="claims|sitelinks|labels"):
    if not ids:
        return {}
    b = _batch()
    if b:
        want = set(props.split("|"))
        miss = [q for q in ids[:50] if not want <= b.ents.get(q, (set(), None))[0]]
        if miss:
            _need(("ent", props, q) for q in miss)
        return {q: b.ents[q][1] for q in ids[:50] if b.ents[q][1] is not None}
    j = _wm_get(WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(ids[:50]), "props": props, "languages": "en", "sitefilter": "enwiki"})
    return (j or {}).get("entities") or {}


def _wd_claims(e, p, current=True):
    """An item's statements of one property, the preferred first, without those that ended (current)."""
    cs = [c for c in (e.get("claims") or {}).get(p, []) if c.get("rank") != "deprecated"]
    if current:
        cs = [c for c in cs if "P582" not in (c.get("qualifiers") or {})] or cs
    return sorted(cs, key=lambda c: c.get("rank") != "preferred")


def _wd_val(c):
    return ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")


def _wd_time(v):
    """A Wikidata time as "YYYY-MM-DD", "YYYY-MM" or "YYYY", as precise as it is."""
    m = re.match(r"\+?(\d{4})-(\d\d)-(\d\d)", (v or {}).get("time", "")) if isinstance(v, dict) else None
    if not m:
        return ""
    p = v.get("precision", 9)
    return m.group(1) if p <= 9 or m.group(2) == "00" else f"{m.group(1)}-{m.group(2)}" if p == 10 or m.group(3) == "00" else "-".join(m.groups())


def _wd_label(e):
    return ((e or {}).get("labels") or {}).get("en", {}).get("value", "")


def _wd_pick(ids, items):
    """Of several items with the same code, the one still going (no dissolution date) with an English page and the most statements."""
    return max(ids, key=lambda q: ("P576" not in (items.get(q, {}).get("claims") or {}), "enwiki" in (items.get(q, {}).get("sitelinks") or {}),
                                   len(items.get(q, {}).get("claims") or {})), default=None)


def _commons(name, w=640):
    b = _batch() if name else None
    if b:                                        # the refresh: the photo's own address at the cards' size (no redirects)
        if name not in b.imgs:
            _need([("img", name)])
        if b.imgs[name]:
            return b.imgs[name]
    return COMMONS_FILE + urllib.parse.quote(name.replace(" ", "_")) + f"?width={w}" if name else ""


def _wd_title(title):
    """The Wikidata item of an English Wikipedia page: (id, item), (None, {}) when there is none; None: not answered."""
    b = _batch()
    if b:
        if title not in b.titles:
            _need([("title", title)])
        return b.titles[title]
    j = _wm_get(WIKIDATA_API, {"action": "wbgetentities", "sites": "enwiki", "titles": title, "props": "claims|sitelinks|labels",
                               "languages": "en", "sitefilter": "enwiki", "normalize": "1"})
    if j is None:
        return None
    return next(((q, e) for q, e in (j.get("entities") or {}).items() if re.fullmatch(r"Q\d+", q)), (None, {}))


# relay 77 (to-do #122): an airline flying under its group's name (Wizz Air Malta, easyJet Europe, Eurowings Europe,
# Lufthansa CityLine) shows the brand's card, "Flown by" the company; one with its own name (Austrian, Lauda Europe)
# keeps its own, "Part of" its group. The brand: a parent (P749 parent organization, P127 owned by) whose name without
# a company word ("Wizz Air Holdings" → "Wizz Air") begins the company's name; the brand's card is the airline of that
# name (an ICAO code and an English page: Wizz Air, the Hungarian airline whose page tells the whole group's fleet).
CORP_TAIL = re.compile(r"(?:\s+(?:holdings?|group|plc|ag|se|sa|s\.a\.|ltd\.?|limited|gmbh|inc\.?|n\.v\.|company|corporation))+$", re.I)


def _airline_parents(e):
    """An airline's parents (current P749, then P127), each once: {id: item}, in that order, each marked "_part" when
    it is a parent organization or owns at least half (a group, not a shareholder as BlackRock); None: not answered."""
    ids, part = [], set()
    for p in ("P749", "P127"):
        for c in _wd_claims(e, p)[:4]:
            v, share = _wd_val(c), ((c.get("qualifiers") or {}).get("P1107") or [{}])[0].get("datavalue", {}).get("value", {}).get("amount")
            if isinstance(v, dict) and re.fullmatch(r"Q\d+", v.get("id", "")):
                if v["id"] not in ids:
                    ids.append(v["id"])
                if p == "P749" or (_num(share) or 0) >= 0.5:
                    part.add(v["id"])
    if not ids:
        return {}
    items = _wd_items(ids)
    if not items:
        return None
    is_person = lambda x: any((_wd_val(c) or {}).get("id") == "Q5" for c in _wd_claims(x, "P31", False))   # noqa: E731  (an owner, not a group)
    return {q: {**items[q], "_part": q in part} for q in ids if q in items and not is_person(items[q])}


def _airline_brand(q, e, parents):
    """The brand an airline flies under, when it is a part of it with the brand's name: (id, name), None when it has
    its own; False: not answered."""
    name = _wd_label(e).casefold()
    is_airline = lambda x: "P230" in (x.get("claims") or {}) and "enwiki" in (x.get("sitelinks") or {}) and "P576" not in (x.get("claims") or {})  # noqa: E731
    for pq, pe in parents.items():
        brand = CORP_TAIL.sub("", _wd_label(pe)).strip()
        if len(brand) < 3 or not name.startswith(brand.casefold() + " "):
            continue
        if pq != q and is_airline(pe) and _wd_label(pe).casefold() == brand.casefold():
            return pq, _wd_label(pe)
        hit = _wd_title(brand)                                   # Wizz Air Holdings → the page "Wizz Air"
        if hit is None:
            return False
        bq, be = hit
        if bq and bq != q and is_airline(be):
            return bq, _wd_label(be) or brand
        if pq != q and is_airline(pe):
            return pq, _wd_label(pe)
    return None


def airline_facts(icao):
    """The facts for an airline's card by its ICAO code: its brand's (with flownBy: {name, icao}) when it flies under
    its group's name, else its own. None: none there; False: not answered."""
    ids = _wd_find("P230", icao)
    if ids is None:
        return False
    items = _wd_items(ids)
    q = _wd_pick(ids, items)
    if not q or "P576" in (items[q].get("claims") or {}):          # only a dissolved one (AZA, Alitalia's): not today's flights
        return None
    parents = _airline_parents(items[q])
    if parents is None:
        return False
    brand = _airline_brand(q, items[q], parents)
    if brand is False:
        return False
    v = facts_json("org", brand[0] if brand else q)
    if v is None:
        return False
    if v.get("none"):
        return None
    return {**v, "flownBy": {"name": _wd_label(items[q]) or icao, "icao": icao}} if brand else v


def airline_own_facts(icao):
    """An airline's own facts by its ICAO code (also when it flies under its group's name): "Flown by" opens these."""
    ids = _wd_find("P230", icao)
    if ids is None:
        return False
    items = _wd_items(ids)
    q = _wd_pick(ids, items)
    if not q or "P576" in (items[q].get("claims") or {}):
        return None
    return _airline_item_facts(q, items[q])


def org_facts(q):
    """An airline's or an airline group's facts by its Wikidata id (an airline's card, its brand's, or the group "Part
    of" opens). A brand's fleet is the whole brand's: when its page counts only its own company (Wizz Air's 118, its
    page pointing to Wizz Air Malta's and Wizz Air UK's), the companies with its name (under it or its holding without a
    page) are added (fleetAll: true); a page counting them already (easyJet's 356) has the larger number and stays."""
    items = _wd_items([q])
    if not items:
        return False
    e = items.get(q)
    if not e or "missing" in e:
        return None
    parents = _airline_parents(e)
    if parents is None:
        return False
    v = _airline_item_facts(q, e, parents)
    f = (v or {}).get("facts") or {}
    if not v or not f.get("fleet") or "P230" not in (e.get("claims") or {}):
        return v
    brand = CORP_TAIL.sub("", _wd_label(e)).strip().casefold()
    kids = []
    for h in [q] + [pq for pq, pe in parents.items() if "enwiki" not in (pe.get("sitelinks") or {})][:2]:
        ids = _wd_find("P749", h)
        if ids is None:
            return False
        kids += [k for k in ids if k != q and k not in kids]
    ki = _wd_items(kids[:20]) if kids else {}
    kids = [k for k, ke in ki.items() if "P230" in (ke.get("claims") or {}) and "P576" not in (ke.get("claims") or {})
            and "enwiki" in (ke.get("sitelinks") or {}) and _wd_label(ke).casefold().startswith(brand + " ")][:8]
    fleets, need = [], False
    for k in kids:
        try:
            kv = _airline_item_facts(k, ki[k], {})
        except _Need:                          # the refresh: what all the companies need, asked for together
            need = True
            continue
        if kv is False:
            return False
        if kv and (kv.get("facts") or {}).get("fleet") and kv.get("text") != v.get("text"):    # not a page leading back to the brand's (KLM Asia)
            fleets.append(kv["facts"]["fleet"])
    if need:
        raise _Need()
    if sum(fleets) > f["fleet"]:
        f["fleet"], f["fleetAll"] = f["fleet"] + sum(fleets), True
    return v


def _airline_item_facts(q, e, parents=None):
    """One airline's (or group's) facts: Wikidata (the company, hubs, alliance, owners, photo, group) and its Wikipedia
    page's infobox (fleet, destinations, founded, first flight, employees). None: none there; False: not answered."""
    if parents is None:
        parents = _airline_parents(e)
        if parents is None:
            return False
    title = ((e.get("sitelinks") or {}).get("enwiki") or {}).get("title", "")
    pg = _wiki_page(title) if title else None
    if pg is False:
        return False
    ib, text = (_infobox(pg[1], ("infobox airline", "infobox company")), pg[2]) if pg else ({}, "")
    refs = {}
    for p in ("P113", "P114", "P159", "P127", "P749"):
        for c in _wd_claims(e, p)[:4]:
            v = _wd_val(c)
            if isinstance(v, dict) and v.get("id"):
                refs[v["id"]] = None
    b = _batch()
    if b:                                    # the refresh: their names only, a hub's code from the airports' list (their statements are large)
        more = _wd_items(list(refs), "labels") if refs else {}
    else:
        more = _wd_items(list(refs), "labels|claims") if refs else {}
    lab = lambda c: _wd_label(more.get((_wd_val(c) or {}).get("id")))           # noqa: E731
    f = {}
    founded = _first(_wd_time(_wd_val(next(iter(_wd_claims(e, "P571", False)), {}))), _date(_wt_text(ib.get("founded", ""))))
    if founded:
        f["founded"] = founded
    com = _date(_wt_text(ib.get("commenced", "")))
    if com:
        f["commenced"] = com
    hubs = []
    for c in _wd_claims(e, "P113")[:4]:
        h = more.get((_wd_val(c) or {}).get("id")) or {}
        code = b.iata.get((_wd_val(c) or {}).get("id"), "") if b else next((str(_wd_val(x) or "") for x in _wd_claims(h, "P238")), "")
        if _wd_label(h):
            hubs.append({"name": _wd_label(h), **({"code": code} if re.fullmatch(r"[A-Z]{3}", code) else {})})
    if not hubs:
        hubs = [{"name": x} for x in _list(ib.get("hubs", ""), 3) if len(x) < 60]
    if hubs:
        f["hubs"] = hubs
    al = next((lab(c) for c in _wd_claims(e, "P114")), "") or _first(*_list(ib.get("alliance", ""), 1))
    if re.fullmatch(r"(?i)star alliance|skyteam|oneworld|vanilla alliance|u-fly alliance|value alliance", al or ""):   # not "TUI Travel"
        f["alliance"] = al
    hq = next((lab(c) for c in _wd_claims(e, "P159")), "") or _first(*_list(ib.get("headquarters", ""), 1))
    if hq and len(hq) < 60:
        f["headquarters"] = hq
    owners = []
    for c in _wd_claims(e, "P127")[:3]:
        share = ((c.get("qualifiers") or {}).get("P1107") or [{}])[0].get("datavalue", {}).get("value", {}).get("amount")
        if lab(c):
            owners.append({"name": lab(c), **({"share": round(float(share) * 100)} if share else {})})
    if not owners:
        p = next((lab(c) for c in _wd_claims(e, "P749")), "") or _first(*_list(_first(ib.get("parent"), ib.get("owner")), 1))
        if p and len(p) < 60:
            owners = [{"name": p}]
    if owners:
        f["owners"] = owners
    for k, key in (("fleet", "fleet size"), ("destinations", "destinations")):
        n = _num(_wt_text(ib.get(key, "")))
        if n and 1 <= n <= 5000:
            f[k] = int(n)
    emp = _wt_text(_first(ib.get("num employees"), ib.get("employees")))
    n = _num(emp)
    if n and n >= 5:
        f["employees"] = int(n)
    else:
        c = next(iter(_wd_claims(e, "P1128", False)), None)
        if c and _num((_wd_val(c) or {}).get("amount")):
            f["employees"] = int(_num((_wd_val(c) or {}).get("amount")))
    cs = _wt_text(ib.get("callsign", "")).split("\n")[0]
    if cs and len(cs) < 30:
        f["callsign"] = cs.upper()
    img = next((str(_wd_val(c) or "") for c in _wd_claims(e, "P18")), "")
    out = {"kind": "airline", "title": title or _wd_label(e), "name": _wd_label(e), "qid": q, "text": text, "facts": f}
    code = next((str(_wd_val(c) or "") for c in _wd_claims(e, "P230")), "")
    if re.fullmatch(r"[A-Z]{3}", code):
        out["icao"] = code
    # its group, for "Part of": the first parent with an English page (not a holding without one, as Wizz Air's), else
    # the page's infobox parent (Lauda Europe's Ryanair Holdings is only there)
    g = next(((pq, pe) for pq, pe in parents.items() if pq != q and pe.get("_part") and "enwiki" in (pe.get("sitelinks") or {}) and _wd_label(pe)), None)
    if not g:
        m = re.search(r"\[\[([^\]|#]+)", _first(ib.get("parent"), ib.get("parent company"), ib.get("owner")) or "")
        hit = _wd_title(m.group(1).strip()) if m else None
        if hit and hit[0] and hit[0] != q and _wd_label(hit[1]):
            g = hit
    if g:
        out["group"] = {"name": _wd_label(g[1]), "qid": g[0]}
    if title:
        out["url"] = _wiki_url(title)
    if img:
        out["img"] = _commons(img)
    return out


def airport_facts(iata):
    """An airport's facts by its IATA code from Wikidata (passengers a year, elevation, opened, runways, operator,
    photo) with its Wikipedia page's introduction. None: none there; False: not answered."""
    ids = _wd_find("P238", iata)
    if ids is None:
        return False
    items = _wd_items(ids)
    ids = [q for q in ids if any(str(_wd_val(c) or "").upper() == iata for c in _wd_claims(items.get(q, {}), "P238", False))] or ids
    q = _wd_pick(ids, items)
    if not q:
        return None
    e = items[q]
    title = ((e.get("sitelinks") or {}).get("enwiki") or {}).get("title", "")
    f, text = {}, ""
    if title:
        text = _wiki_extract(title)
        if text is None:
            return False
    pax = []
    for c in _wd_claims(e, "P3872", False):
        v, qy = _wd_val(c) or {}, (((c.get("qualifiers") or {}).get("P585") or [{}])[0].get("datavalue") or {}).get("value")
        n, y = _num(v.get("amount")), _wd_time(qy)[:4]
        if n and y:
            pax.append((y, c.get("rank") == "preferred", n))
    if pax:
        y, _, n = max(pax)
        f["passengers"], f["passengersYear"] = int(n), int(y)
    c = next(iter(_wd_claims(e, "P2044", False)), None)
    if c:
        v = _wd_val(c) or {}
        n = _num(v.get("amount"))
        if n is not None:
            f["elevation"] = int(round(n * 0.3048 if str(v.get("unit", "")).endswith("/Q3710") else n))
    op = _first(_wd_time(_wd_val(next(iter(_wd_claims(e, "P1619", False)), {}))), _wd_time(_wd_val(next(iter(_wd_claims(e, "P571", False)), {}))))
    if op:
        f["opened"] = op
    rw = [str(_wd_val(c) or "") for c in _wd_claims(e, "P529", False)]
    if rw:
        f["runways"] = len(rw)
    refs = {(_wd_val(c) or {}).get("id"): 0 for p in ("P137", "P931", "P17") for c in _wd_claims(e, p)[:2] if isinstance(_wd_val(c), dict)}
    more = _wd_items([r for r in refs if r], "labels") if any(refs) else {}
    for k, p in (("operator", "P137"), ("serves", "P931"), ("country", "P17")):     # its operator, city and country
        v = next((_wd_label(more.get((_wd_val(c) or {}).get("id"))) for c in _wd_claims(e, p)), "")
        if v:
            f[k] = v
    co = _wd_val(next(iter(_wd_claims(e, "P625", False)), {})) or {}
    if isinstance(co, dict) and co.get("latitude") is not None:
        f["lat"], f["lon"] = round(co["latitude"], 4), round(co["longitude"], 4)
    img = next((str(_wd_val(c) or "") for c in _wd_claims(e, "P18")), "")
    out = {"kind": "airport", "title": title or _wd_label(e), "name": _wd_label(e), "qid": q, "text": text, "facts": f}
    if title:
        out["url"] = _wiki_url(title)
    if img:
        out["img"] = _commons(img)
    return out


FACTS_KINDS = {"model": model_facts, "airline": airline_facts, "airline-own": airline_own_facts, "org": org_facts, "airport": airport_facts}
FACTS_VER = {"airline": "2"}   # relay 77: an airline's card is its brand's now (to-do #122): relay 74's kept answers are asked again
_FACTS_PREFIX = {f"{kind}{FACTS_VER.get(kind, '')}": kind for kind in FACTS_KINDS}    # a key's beginning -> its kind


_fdb = None                    # the facts database's connection (relay 78), shared by the threads under _fdb_lock
_fdb_lock = threading.Lock()


def _facts_db():
    """The facts database, opened the first time; relay 74–77's facts.json moves in once (and stays as it was)."""
    global _fdb
    moved = 0
    with _fdb_lock:
        if _fdb is None:
            FACTS_DB.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(FACTS_DB), check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.execute("CREATE TABLE IF NOT EXISTS facts (k TEXT PRIMARY KEY, t REAL NOT NULL, v TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
            if not db.execute("SELECT 1 FROM meta WHERE k = 'moved'").fetchone():
                raw, now = _load(FACTS_FILE, {}), set(_FACTS_PREFIX)
                rows = [(k, float(v["t"]), json.dumps(v.get("v"), separators=(",", ":"))) for k, v in (raw if isinstance(raw, dict) else {}).items()
                        if isinstance(v, dict) and isinstance(v.get("t"), (int, float)) and k.split(":", 1)[0] in now]   # not relay 74's airlines
                with db:
                    db.executemany("INSERT OR IGNORE INTO facts VALUES (?, ?, ?)", rows)
                    db.execute("INSERT INTO meta VALUES ('moved', ?)", (json.dumps({"at": time.time(), "entries": len(rows)}),))
                moved = len(rows)
            _fdb = db
    if moved:
        event("info", f"Moved {moved} cards' facts into {FACTS_DB.name}", echo=False)
    return _fdb


def _facts_get(k):
    """A kept answer: {"t": when, "v": the facts or None (nothing there)}, or None."""
    db = _facts_db()
    with _fdb_lock:
        r = db.execute("SELECT t, v FROM facts WHERE k = ?", (k,)).fetchone()
    return {"t": r[0], "v": json.loads(r[1]) if r[1] else None} if r else None


def _facts_put(k, v):
    db = _facts_db()
    with _fdb_lock, db:
        db.execute("INSERT OR REPLACE INTO facts VALUES (?, ?, ?)", (k, time.time(), json.dumps(v, separators=(",", ":"))))


def _facts_meta(k, v=...):
    """The database's notes (the refresh going on, its last one): one read, or set (None removes it)."""
    db = _facts_db()
    with _fdb_lock:
        if v is ...:
            r = db.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
            return json.loads(r[0]) if r else None
        with db:
            if v is None:
                db.execute("DELETE FROM meta WHERE k = ?", (k,))
            else:
                db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (k, json.dumps(v)))


def _facts_keys(since=None):
    """The kept keys by kind ({kind: [key, ...]}), all or those refreshed since then."""
    db, out = _facts_db(), {}
    with _fdb_lock:
        rows = db.execute("SELECT k FROM facts" + (" WHERE t >= ?" if since else ""), (since,) if since else ()).fetchall()
    for (k,) in rows:
        pre, _, key = k.partition(":")
        if pre in _FACTS_PREFIX:
            out.setdefault(_FACTS_PREFIX[pre], []).append(key)
    return out


def facts_json(kind, key):
    """The facts for one card: {kind, title, name, url, text, img, facts}, or {kind, none: true} when there are none;
    None when Wikipedia or Wikidata can't be asked now (and nothing older is kept). One lookup per page a month: a
    second screen asking meanwhile waits for the first one's answer. The monthly refresh asks again what it hasn't
    refreshed yet."""
    k, hit, b = f"{kind}{FACTS_VER.get(kind, '')}:{key}", None, _batch()
    for _ in range(2):
        hit = _facts_get(k)
        with _data_lock:
            if hit and time.time() - hit["t"] < FACTS_KEEP and (not b or hit["t"] >= b.since):
                return hit["v"] or {"kind": kind, "none": True}
            if time.time() - _facts_failed.get(k, 0) < FACTS_FAIL:
                return (hit["v"] or {"kind": kind, "none": True}) if hit else None
            busy, mine = _facts_busy.get(k), False
            if not busy:
                busy, mine = _facts_busy.setdefault(k, threading.Event()), True
        if mine:
            break
        busy.wait(40)
    else:
        return None
    v = _Need
    try:
        v = FACTS_KINDS[kind](key)
    except _Need:                              # the refresh: fetched with other cards' needs first, then asked again
        raise
    except Exception as e:                     # a page this code doesn't understand must never break the relay
        event("warn", f"Couldn't read the facts for {k}: {e!r}", echo=False)
        v = None
    finally:
        try:
            if v is not False and v is not _Need:
                _facts_put(k, v)
        finally:
            with _data_lock:
                _facts_busy.pop(k, None)
                if v is False:
                    _facts_failed[k] = time.time()
            busy.set()
    if v is False:
        return (hit["v"] or {"kind": kind, "none": True}) if hit else None    # the old answer while it can't be asked
    return v or {"kind": kind, "none": True}


# ---------- the facts database's monthly refresh (relay 78, to-do #129) ----------
_facts_running = threading.Lock()   # held while a refresh runs
_facts_progress = {}           # what the refresh going on is doing (the owner's /facts?status=1)


def _facts_lists():
    """What the refresh covers, from Wikidata's query service (three requests): the items by airline ICAO code (P230),
    airport IATA code (P238) and the airlines under each company (P749, a brand's whole fleet), as _wd_find finds them
    ({prop: {value: [ids]}}); the ICAO codes of the airlines still flying (an item without a dissolution date, P576)
    and the IATA codes; each airport's code by its id."""
    def ask(q):
        rows = (_wm_batch_get(SPARQL_API, {"query": q}, timeout=120).get("results") or {}).get("bindings") or []
        return [{k: str((v or {}).get("value", "")).rsplit("/", 1)[-1] for k, v in r.items()} for r in rows]

    find, flying = {"P230": {}, "P238": {}, "P749": {}}, set()

    def add(prop, value, q):
        if re.fullmatch(r"Q\d+", q) and q not in find[prop].setdefault(value, []):
            find[prop][value].append(q)
    for r in ask("SELECT ?i ?c ?gone WHERE { ?i p:P230/ps:P230 ?c . BIND(EXISTS { ?i p:P576 [] } AS ?gone) }"):
        c = r.get("c", "").strip().upper()
        if re.fullmatch(r"[A-Z]{3}", c):
            add("P230", c, r.get("i", ""))
            if r.get("gone") != "true":
                flying.add(c)
    iata = {}                                    # an airport's code (its current one first): an airline's hubs
    for r in ask("SELECT ?i ?c ?best WHERE { ?i p:P238/ps:P238 ?c . BIND(EXISTS { ?i wdt:P238 ?c } AS ?best) }"):
        c = r.get("c", "").strip().upper()
        if re.fullmatch(r"[A-Z]{3}", c):
            add("P238", c, r.get("i", ""))
            if r.get("best") == "true" or r.get("i") not in iata:
                iata[r.get("i")] = c
    for r in ask("SELECT ?i ?p WHERE { ?i p:P749/ps:P749 ?p . ?i p:P230 [] }"):   # (only those with an ICAO code count)
        add("P749", r.get("p", ""), r.get("i", ""))
    for m in find.values():
        for ids in m.values():
            ids.sort(key=lambda q: int(q[1:]))
    return find, sorted(flying), sorted(find["P238"]), iata


def _facts_fetch(b):
    """Fetch what the refresh's cards asked for (_Need), together: 50 items, pages or photos a request (introductions
    alone, 20)."""
    need, b.need, groups = b.need, set(), collections.defaultdict(list)
    for n in sorted(need):
        if n[0] == "ent":                      # an item asked for again with more: all of it
            groups[("ent", "|".join(sorted(set(n[1].split("|")) | b.ents.get(n[2], (set(), None))[0])))].append(n[2])
        else:
            groups[(n[0], "")].append(n[1])
    for (kind, props), keys in sorted(groups.items(), key=lambda g: ["ent", "title", "page", "extract", "img"].index(g[0][0])):
        keys = list(dict.fromkeys(keys))
        if kind == "ent":
            for i in range(0, len(keys), 50):
                c = keys[i:i + 50]
                es = _wm_batch_get(WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(c), "props": props, "languages": "en",
                                                  "sitefilter": "enwiki"}).get("entities") or {}
                for q in c:
                    b.ents[q] = (set(props.split("|")), es.get(q))
        elif kind == "title":
            for i in range(0, len(keys), 50):
                c = [t for t in keys[i:i + 50] if "|" not in t]
                es = _wm_batch_get(WIKIDATA_API, {"action": "wbgetentities", "sites": "enwiki", "titles": "|".join(c), "props": "claims|sitelinks|labels",
                                                  "languages": "en", "sitefilter": "enwiki"}).get("entities") or {} if c else {}
                by = {((e.get("sitelinks") or {}).get("enwiki") or {}).get("title"): (q, e) for q, e in es.items() if re.fullmatch(r"Q\d+", q)}
                for t in keys[i:i + 50]:
                    hit = by.get(t)
                    if not hit and t in c:     # not under this very title (another spelling, a redirect): asked alone, normalized
                        es = _wm_batch_get(WIKIDATA_API, {"action": "wbgetentities", "sites": "enwiki", "titles": t, "props": "claims|sitelinks|labels",
                                                          "languages": "en", "sitefilter": "enwiki", "normalize": "1"}).get("entities") or {}
                        hit = next(((q, e) for q, e in es.items() if re.fullmatch(r"Q\d+", q)), None)
                    b.titles[t] = hit or (None, {})
                    if hit:
                        b.ents[hit[0]] = ({"claims", "sitelinks", "labels"}, hit[1])
        elif kind in ("page", "extract"):      # (a page asked for whole has its introduction too)
            full = kind == "page"
            keys = [t for t in keys if not (t in b.pages and (b.pages[t][0] or not full))]
            for t in [t for t in keys if "|" in t or not t.strip()]:
                b.pages[t] = (True, {"title": t, "invalid": True})
            keys = [t for t in keys if not (t in b.pages and b.pages[t][1].get("invalid"))]
            n, params = (50, {"prop": "revisions|extracts|pageprops", "rvprop": "content", "rvslots": "main", "ppprop": "disambiguation",
                              **({"rvsection": "0"} if b.lead else {})}) if full else (20, {"prop": "extracts"})
            for i in range(0, len(keys), n):
                c = keys[i:i + n]
                got = _wm_pages(WIKI_API, c, {**params, "exintro": "1", "explaintext": "1", "exlimit": "max"})
                for t in c:
                    b.pages[t] = (full, got.get(t) or {"title": t, "missing": True})
        elif kind == "img":                    # the photo's own address at the cards' size, from Commons
            for i in range(0, len(keys), 50):
                c = [x for x in keys[i:i + 50] if "|" not in x]
                got = _wm_pages(COMMONS_API, ["File:" + x for x in c], {"prop": "imageinfo", "iiprop": "url", "iiurlwidth": str(FACTS_IMG_W)}) if c else {}
                for x in keys[i:i + 50]:
                    b.imgs[x] = ((((got.get("File:" + x) or {}).get("imageinfo") or [{}])[0]).get("thumburl") or "").split("?utm_")[0]   # (without Commons' tracking)


def _facts_chunk(b, keys):
    """Refresh some cards together: run their lookups, fetch what they ask for for all of them at once, run them
    again (a brand's card needs its company, then its group, then the group's page ...). How many are left over."""
    for _ in range(20):
        left = []
        for kind, key in keys:
            try:
                facts_json(kind, key)
            except _Need:
                left.append((kind, key))
        if not left:
            return 0
        keys = left
        _facts_fetch(b)
    b.need.clear()
    event("warn", f"Card facts refresh: still asking after 20 rounds: {', '.join(f'{k}:{v}' for k, v in keys[:5])}", echo=False)
    return len(keys)


def facts_refresh(stop_at):
    """One night's part of the monthly refresh: the models (MODEL_TITLES), every airline still flying, the groups and
    companies their cards open, every airport with an IATA code, and every other key a card asked for, 50 at a time;
    what isn't done by `stop_at` goes on next time (the keys refreshed since the run began are skipped). True when
    the whole run is done."""
    if not _facts_running.acquire(blocking=False):
        return False
    b, t0, why = _wm_batch, time.time(), ""
    run = _facts_meta("run") or {"since": t0, "requests": 0, "bytes": 0, "seconds": 0, "nights": 0, "left": 0}
    b.on, b.since, b.stop_at, b.need, b.stats = True, run["since"], stop_at, set(), {"requests": 0, "bytes": 0}
    b.ents, b.pages, b.titles, b.imgs, b.find, b.iata, b.lead = {}, {}, {}, {}, {}, {}, False
    _facts_progress.clear()
    _facts_progress.update(stage="lists", started=t0, stats=b.stats)
    try:
        b.find, airlines, airports, b.iata = _facts_lists()
        known = _facts_keys()
        for kind in ("model", "airline", "org", "airline-own", "airport"):
            keys = {"model": MODEL_TITLES, "airline": airlines, "airport": airports}.get(kind, [])
            if kind in ("org", "airline-own"):         # what the airline cards open: their group (Part of), their company (Flown by)
                for v in _facts_opens():
                    keys.append(((v.get("group") or {}).get("qid") if kind == "org" else (v.get("flownBy") or {}).get("icao")) or "")
            keys = list(dict.fromkeys(k for k in keys + known.get(kind, []) if k))
            b.lead = kind != "model"            # an airline's or group's page: only its first section (the infobox; a model's specs are further down)
            _facts_progress.update(stage=kind, of=len(keys), done=0)
            n = 100 if kind == "airport" else 50         # (an airport needs fewer and smaller things: more go together)
            for i in range(0, len(keys), n):
                run["left"] += _facts_chunk(b, [(kind, k) for k in keys[i:i + n]])
                _facts_progress["done"] = min(len(keys), i + n)
                b.pages, b.imgs, b.titles = {}, {}, {}     # kept for the next cards: only names (a country, a city, an alliance)
                b.ents = {q: x for q, x in b.ents.items() if x[0] == {"labels"}} if len(b.ents) < 20000 else {}
    except _Stop as e:
        why = str(e)
    finally:
        b.on = False
        b.ents, b.pages, b.titles, b.imgs, b.find, b.iata = {}, {}, {}, {}, {}, {}
        run["requests"] += b.stats["requests"]
        run["bytes"] += b.stats["bytes"]
        run["seconds"] += round(time.time() - t0)
        run["nights"] += 1
        _facts_progress.clear()
        try:
            _facts_meta("run", run)                     # (also when something unforeseen stopped it)
        finally:
            _facts_running.release()
    if why:
        event("info", f"Card facts: the refresh goes on next night ({why})", echo=False)
        return False
    counts = facts_status()["entries"]
    _facts_meta("done", {"at": time.time(), "since": run["since"], "requests": run["requests"], "mb": round(run["bytes"] / 1e6, 1),
                         "minutes": round(run["seconds"] / 60, 1), "nights": run["nights"], "left": run["left"], "entries": counts})
    _facts_meta("run", None)
    event("info", f"Card facts refreshed ({', '.join(f'{n} {k}' for k, n in counts.items())}): {run['requests']} requests, "
                  f"{run['bytes'] / 1e6:.0f} MB, {run['seconds'] / 60:.0f} min", echo=False)
    return True


def _facts_opens():
    """The airline cards refreshed in this run (what they open: their group, their company)."""
    db = _facts_db()
    with _fdb_lock:
        rows = db.execute("SELECT v FROM facts WHERE k LIKE ? AND t >= ?", (f"airline{FACTS_VER.get('airline', '')}:%", _wm_batch.since)).fetchall()
    return [v for v in (json.loads(r[0]) for r in rows if r[0]) if isinstance(v, dict)]


def facts_status():
    """The facts database for the owner: entries per kind, its size (with its journal), the refresh going on and the last one."""
    db = _facts_db()
    with _fdb_lock:
        rows = db.execute("SELECT substr(k, 1, instr(k, ':') - 1), count(*) FROM facts GROUP BY 1").fetchall()
    return {"entries": {_FACTS_PREFIX[p]: n for p, n in rows if p in _FACTS_PREFIX},
            "bytes": sum(f.stat().st_size for f in FACTS_DB.parent.glob(FACTS_DB.name + "*")),
            "running": {k: v for k, v in _facts_progress.items()} if _facts_running.locked() else None,
            "run": _facts_meta("run"), "last": _facts_meta("done")}


def _facts_worker():
    """Moves facts.json into the database, then refreshes it once a month at night (FACTS_NIGHT, the relay's time),
    going on the next night with what one night didn't finish (or when Wikimedia didn't answer)."""
    try:
        _facts_db()
    except (OSError, sqlite3.Error) as e:
        event("warn", f"Card facts database: {e}")
        return
    while True:
        time.sleep(300)
        try:
            lt = time.localtime()
            m = lt.tm_hour * 60 + lt.tm_min
            if not FACTS_NIGHT[0] <= m < FACTS_NIGHT[1]:
                continue
            if not _facts_meta("run") and time.time() - (_facts_meta("done") or {}).get("at", 0) < FACTS_EVERY:
                continue
            end = time.time() + (FACTS_NIGHT[1] - m) * 60
            facts_refresh(end)
            time.sleep(max(0, end - time.time()))    # done, or stopped: not again tonight
        except Exception as e:  # never let the refresh break the relay
            event("warn", f"Card facts refresh: {e!r}")


# What a profile spotted of one airline, model or airport (relay 74, the cards' Spotted): its planes (different
# airframes, by registration, else by hex) and sightings over every saved day. The logbook's registrations don't keep
# their airline, so the days are read: a past day once (its summary kept in memory, as _place_days), today's fresh.
_spotted_days = {}           # (spot folder, day) -> {"al": {icao: [n, first, last, {airframes}]}, "ty": {...}, "ap": {...}}


def _spotted_summary(entries):
    out = {"al": {}, "ty": {}, "ap": {}}
    for e in entries:
        if not isinstance(e, dict):
            continue
        ts, plane = e.get("ts") or 0, str(e.get("reg") or e.get("hex") or "").upper()
        m = re.match(r"^([A-Z]{3})\d", str(e.get("callsign") or ""))
        keys = [("al", m.group(1) if m else ""), ("ty", str(e.get("typeCode") or "").upper())]
        keys += [("ap", str((e.get(k) or {}).get("code") or "").upper()) for k in ("from", "to") if isinstance(e.get(k), dict)]
        for part, key in dict.fromkeys(keys):
            if not key:
                continue
            s = out[part].setdefault(key, [0, ts, ts, set()])
            s[0] += 1
            s[1], s[2] = min(s[1], ts), max(s[2], ts)
            if plane:
                s[3].add(plane)
    return out


def spotted_json(spot, part, key):
    """{"sightings", "planes", "first", "last"} of one airline ("al", ICAO code), model ("ty", type code) or airport
    ("ap", IATA code: flights to or from it) over the profile's whole logbook."""
    with _data_lock:
        spot.ensure_day()
        days = sorted(f.stem[len("sightings-"):] for f in spot.dir.glob("sightings-*.json"))
        today, entries = spot.day, list(spot.entries)
    n, first, last, planes = 0, None, None, set()
    for day in days:
        if day == today:
            summ = _spotted_summary(entries)
        else:
            summ = _spotted_days.get((str(spot.dir), day))
            if summ is None:
                summ = _spotted_days[(str(spot.dir), day)] = _spotted_summary(_load(spot.dir / f"sightings-{day}.json", []))
        s = summ[part].get(key)
        if s:
            n += s[0]
            first, last = s[1] if first is None else min(first, s[1]), s[2] if last is None else max(last, s[2])
            planes |= s[3]
    return {"sightings": n, "planes": len(planes), "first": first, "last": last}


# Hue light pulse (relay 47, to-do #46; a test feature, the owner's only). When a special or favourite plane is about to
# pass the owner's place (the moments the window alerts ring for, window_planes), the chosen Philips Hue lamps glow
# briefly in the airline's colour (amber when it has none here) through the Hue Bridge on the home network, its local
# API only (no cloud), and then go back to how they were. At most once per plane and once a minute, never in the quiet
# hours (22:00-07:00) unless turned off. Set up on the admin page: find the bridge (Philips' discovery service, or type
# its address), press its link button and Pair, pick the lamps. The bridge's username lives in data/hue.json only.
HUE_FILE = DATA_DIR / "hue.json"           # {addr, name, user, on, quiet, lights: [ids]}
HUE_DISCOVERY = "https://discovery.meethue.com"
HUE_GAP_S = 60
HUE_PAIR_S = 30
HUE_AMBER = (255, 170, 0)
HUE_COLOURS = {   # an airline's colour (ICAO code): bright enough for a lamp, so not always the darkest brand colour
    "AUA": (225, 10, 30), "LDM": (225, 10, 30), "DLH": (250, 180, 0), "SWR": (225, 0, 20), "EWG": (170, 20, 90),
    "RYR": (20, 60, 170), "EZY": (255, 100, 0), "EJU": (255, 100, 0), "WZZ": (200, 0, 130), "WMT": (200, 0, 130),
    "WUK": (200, 0, 130), "BAW": (30, 60, 180), "AFR": (0, 50, 170), "KLM": (0, 160, 225), "THY": (200, 15, 45),
    "PGT": (255, 200, 0), "UAE": (210, 20, 30), "QTR": (120, 10, 70), "ETD": (200, 150, 80), "AEE": (0, 60, 160),
    "LOT": (20, 60, 150), "SAS": (0, 50, 150), "FIN": (0, 80, 180), "TAP": (0, 170, 80), "IBE": (215, 20, 30),
    "VLG": (255, 200, 0), "ITY": (0, 80, 200), "EVA": (0, 130, 70), "SIA": (255, 160, 0), "CCA": (215, 20, 30),
    "KAL": (0, 140, 210), "UAL": (0, 70, 170), "DAL": (200, 20, 50), "AAL": (0, 120, 215), "ELY": (0, 60, 160),
    "NOZ": (215, 25, 35), "ICE": (0, 70, 150), "FDX": (90, 30, 160), "BCS": (255, 200, 0), "DHK": (255, 200, 0),
    "CLX": (0, 100, 180), "ETH": (0, 150, 60), "SVA": (0, 120, 80), "FDB": (0, 90, 180), "BTI": (180, 220, 0)}
_hue = None
_hue_lock = threading.Lock()
_hue_seen = {}                             # plane hex -> when it pulsed (once per plane)
_hue_run = {"pairUntil": 0.0, "last": 0.0, "busy": False, "msg": None, "lastWhat": ""}


def hue_state():
    """The Hue settings (a copy)."""
    global _hue
    with _hue_lock:
        if _hue is None:
            try:
                _hue = json.loads(HUE_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _hue = {}
        return dict(_hue)


def hue_save(**kw):
    global _hue
    hue_state()
    with _hue_lock:
        _hue.update(kw)
        _hue = {k: v for k, v in _hue.items() if v is not None}
        _write_json(HUE_FILE, _hue)
        try:
            os.chmod(HUE_FILE, 0o600)
        except OSError:
            pass


def hue_say(text, ok=True):
    _hue_run["msg"] = (time.time(), text, ok)
    event("info" if ok else "warn", f"Hue: {text}")


def hue_pairing():
    return _hue_run["pairUntil"] > time.time()


def hue_addr(text):
    """A bridge address on the home network (an IPv4 address, :port optional), or None."""
    m = re.fullmatch(r"\s*(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?\s*", str(text or ""))
    if not m:
        return None
    try:
        a = ipaddress.ip_address(m.group(1))
    except ValueError:
        return None
    if not (a.is_private or a.is_loopback) or (m.group(2) and not 0 < int(m.group(2)) < 65536):
        return None
    return m.group(1) + (f":{int(m.group(2))}" if m.group(2) and int(m.group(2)) != 80 else "")


def hue_call(method, path, body=None, addr=None, timeout=4):
    """The bridge's local API (v1, plain http on the home network): the answer as JSON, or None."""
    addr = addr or hue_state().get("addr")
    if not addr:
        return None
    req = urllib.request.Request(f"http://{addr}/api{path}", data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(2_000_000) or b"null")
    except Exception:
        return None


def _hue_error(r):
    """The bridge's error (type, description) in an answer, or None."""
    e = r[0].get("error") if isinstance(r, list) and r and isinstance(r[0], dict) else None
    return (e.get("type"), e.get("description") or "") if isinstance(e, dict) else None


def hue_find():
    """Look for the bridge with Philips' discovery service (it lists the bridges on the network this request comes
    from) and check it answers here."""
    status, _, body, _ = fetch(HUE_DISCOVERY, timeout=8)
    try:
        found = json.loads(body) if status == 200 else []
    except ValueError:
        found = []
    for b in found if isinstance(found, list) else []:
        port = b.get("port") if isinstance(b, dict) else None
        addr = hue_addr(f"{b.get('internalipaddress')}" + (f":{port}" if port not in (None, 80, 443) else "")) if isinstance(b, dict) else None
        cfg = hue_call("GET", "/config", addr=addr) if addr else None
        if isinstance(cfg, dict) and cfg.get("bridgeid"):
            hue_save(addr=addr, name=str(cfg.get("name") or "Hue Bridge")[:40], user=None, lights=None)
            return hue_say(f"found {cfg.get('name') or 'the bridge'} at {addr}")
    hue_say("no bridge found (Philips' discovery service didn't list one that answers): type its address instead", False)


def hue_use(text):
    addr = hue_addr(text)
    if not addr:
        return hue_say("that isn't an address on the home network (like 192.168.1.20)", False)
    cfg = hue_call("GET", "/config", addr=addr)
    if not (isinstance(cfg, dict) and cfg.get("bridgeid")):
        return hue_say(f"no Hue Bridge answers at {addr}", False)
    hue_save(addr=addr, name=str(cfg.get("name") or "Hue Bridge")[:40], user=None, lights=None)
    hue_say(f"found {cfg.get('name') or 'the bridge'} at {addr}")


def hue_pair():
    """Ask the bridge for a username for HUE_PAIR_S seconds, every 2 s: it gives one within 30 s of its link button
    being pressed, so the button can be pressed just before or after Pair."""
    if hue_pairing() or not hue_state().get("addr"):
        return
    _hue_run["pairUntil"] = time.time() + HUE_PAIR_S
    hue_say("waiting for the bridge's link button")

    def run():
        try:
            while hue_pairing():
                r = hue_call("POST", "", {"devicetype": "fallblatt#relay"})
                ok = r[0].get("success") if isinstance(r, list) and r and isinstance(r[0], dict) else None
                if isinstance(ok, dict) and ok.get("username"):
                    hue_save(user=str(ok["username"]), on=False, quiet=True, lights=[])
                    return hue_say("paired: now pick the lamps")
                err = _hue_error(r)
                if r is None or (err and err[0] != 101):           # 101: the link button hasn't been pressed
                    return hue_say("the bridge didn't answer" if r is None else f"the bridge said: {err[1]}", False)
                time.sleep(2)
            hue_say("the link button wasn't pressed within 30 seconds: press it, then Pair again", False)
        finally:
            _hue_run["pairUntil"] = 0.0
    threading.Thread(target=run, daemon=True).start()


def hue_lamps():
    """(rooms, names): the bridge's rooms [(name, [light ids])] (lamps in no room last) and {light id: name}; None when
    the bridge doesn't answer or no longer knows the relay."""
    st = hue_state()
    if not st.get("user"):
        return None
    lights = hue_call("GET", f"/{st['user']}/lights")
    if not isinstance(lights, dict):
        return None
    groups = hue_call("GET", f"/{st['user']}/groups") or {}
    names = {i: str((l or {}).get("name") or f"Lamp {i}") for i, l in lights.items()}
    rooms, placed = [], set()
    for g in (groups.values() if isinstance(groups, dict) else []):
        if isinstance(g, dict) and g.get("type") == "Room":
            ids = [i for i in g.get("lights") or [] if i in names]
            if ids:
                rooms.append((str(g.get("name") or "Room"), ids))
                placed.update(ids)
    rest = [i for i in names if i not in placed]
    if rest:
        rooms.append(("Other lamps", rest))
    return rooms, names


def _xy(rgb):
    """An sRGB colour as Hue's CIE xy."""
    lin = [((c / 255 + .055) / 1.055) ** 2.4 if c / 255 > .04045 else c / 255 / 12.92 for c in rgb]
    X = lin[0] * .4124 + lin[1] * .3576 + lin[2] * .1805
    Y = lin[0] * .2126 + lin[1] * .7152 + lin[2] * .0722
    Z = lin[0] * .0193 + lin[1] * .1192 + lin[2] * .9505
    t = X + Y + Z
    return [round(X / t, 4), round(Y / t, 4)] if t else [.3227, .329]


def hue_pulse(rgb, what):
    """Glow the chosen lamps in this colour (up, a little down, up again: about 4 s), then put each back as it was:
    its brightness and colour, and off again if it was off. In a thread; False if it can't start."""
    st = hue_state()
    user, ids = st.get("user"), [str(i) for i in st.get("lights") or []]
    if not (user and ids and st.get("addr")) or _hue_run["busy"]:
        return False
    _hue_run.update(busy=True, last=time.time(), lastWhat=what)

    def run():
        try:
            saved = {}
            for i in ids:
                r = hue_call("GET", f"/{user}/lights/{i}")
                if isinstance(r, dict) and isinstance(r.get("state"), dict) and r["state"].get("reachable", True):
                    saved[i] = r["state"]
            xy = _xy(rgb)
            for step, wait in (({"on": True, "bri": 254, "xy": xy, "transitiontime": 3}, 1.2), ({"bri": 110, "transitiontime": 5}, .7),
                               ({"bri": 254, "transitiontime": 5}, 1.8)):
                for i in saved:
                    hue_call("PUT", f"/{user}/lights/{i}/state", step)
                time.sleep(wait)
            for i, was in saved.items():
                back = {"bri": was.get("bri"), "transitiontime": 8}
                if was.get("colormode") == "xy" and was.get("xy"):
                    back["xy"] = was["xy"]
                elif was.get("colormode") == "ct" and was.get("ct"):
                    back["ct"] = was["ct"]
                elif was.get("colormode") == "hs":
                    back.update(hue=was.get("hue"), sat=was.get("sat"))
                hue_call("PUT", f"/{user}/lights/{i}/state", {k: v for k, v in back.items() if v is not None})
            time.sleep(1)
            for i, was in saved.items():
                if not was.get("on"):
                    hue_call("PUT", f"/{user}/lights/{i}/state", {"on": False, "transitiontime": 6})
        except Exception as e:
            event("warn", f"Hue pulse failed: {e}", echo=False)
        finally:
            _hue_run["busy"] = False
    threading.Thread(target=run, daemon=True).start()
    return True


def _hue_quiet(st):
    h = time.localtime().tm_hour
    return st.get("quiet", True) and (h >= 22 or h < 7)


def hue_check():
    """A special or favourite plane about to pass the owner's place: pulse, once per plane, once a minute at most."""
    st = hue_state()
    if not (st.get("on") and st.get("user") and st.get("lights")) or _hue_quiet(st):
        return
    now = time.time()
    for k in [k for k, t in _hue_seen.items() if now - t > 3 * 3600]:
        del _hue_seen[k]
    if now - _hue_run["last"] < HUE_GAP_S:
        return
    with _data_lock:
        own = [(pid, p.get("settings") or {}) for pid, p in profiles()["profiles"].items()
               if str(p.get("name") or "").strip().lower() == HOME_OWNER.lower()]
    if len(own) != 1 or own[0][1].get("lat") is None:
        return
    pid, ost = own[0]
    try:
        centre = (float(ost["lat"]), float(ost["lon"]))
    except (TypeError, ValueError, KeyError):
        return
    for pl in window_planes(pid, centre, guest_spot(pid), ost):
        kind = next((k for k, _ in pl["kinds"] if k in ("special", "fav")), None)
        hx = pl["ac"].get("hex")
        if not kind or hx in _hue_seen:
            continue
        _hue_seen[hx] = now
        if hue_pulse(HUE_COLOURS.get(pl["airline"], HUE_AMBER), pl["what"]):
            event("info", f"Hue pulse: {pl['what']} ({kind})")
        return


def _hue_watch():
    while True:
        time.sleep(15)
        try:
            hue_check()
        except Exception as e:
            event("warn", f"Hue check failed: {e}", echo=False)


def hue_admin_html():
    """The admin page's Hue section (the admin page is the owner's only)."""
    esc = html.escape
    st, msg = hue_state(), _hue_run["msg"]
    note = (f"<p style='color:{'#3c3' if msg[2] else '#f2b134'}'>{esc(msg[1][:1].upper() + msg[1][1:])} "
            f"<span class=muted>({_ago(msg[0])})</span></p>" if msg and time.time() - msg[0] < 600 else "")
    form = lambda action, inner, extra="": f"<form method=post action='/admin/hue/{action}' style='display:inline'{extra}>{inner}</form>"
    out = ("<h2>Hue lights <span class='tag g'>test</span></h2><p>When a special plane or a favourite is about to pass, chosen "
           "Philips Hue lamps glow for a few seconds in the airline's colour (amber otherwise), then go back to how they were. "
           "Only for this profile's place; through the Hue Bridge at home, no cloud.</p>" + note)
    if not st.get("addr"):
        return out + (f"<div class=row>{form('find', '<button class=go>Find the bridge</button>')} or "
                      f"{form('use', '<input type=text name=addr maxlength=21 placeholder=192.168.1.20 style=width:150px> <button>Use this address</button>')}</div>"
                      "<p class=muted>The address is in the Hue app: Settings → Hue Bridges → ⓘ.</p>")
    where = f"<b>{esc(st.get('name') or 'Hue Bridge')}</b> at {esc(st['addr'])}"
    forget = form("forget", "<button class=sm>Forget the bridge</button>", " onsubmit=\"return confirm('Forget the bridge?')\"")
    if not st.get("user"):
        if hue_pairing():
            left = max(0, round(_hue_run["pairUntil"] - time.time()))
            return out + (f"<p>{where}</p><p style='font-size:20px'><b>Press the round link button on top of the bridge now.</b> "
                          f"<span class=muted>Waiting {left} s …</span></p>")
        return out + (f"<p>{where} · not paired yet</p><p>Press the round <b>link button</b> on top of the bridge, then click "
                      f"Pair within 30 seconds (or click Pair first and press the button while this page waits).</p>"
                      f"<div class=row>{form('pair', '<button class=go>Pair</button>')} {forget}</div>")
    lamps = hue_lamps()
    if lamps is None:
        return out + (f"<p>{where} · paired, but the bridge doesn't answer or no longer knows the relay.</p>"
                      f"<div class=row>{form('pair', '<button>Pair again</button>')} {forget}</div>")
    rooms, names = lamps
    chosen = {str(i) for i in st.get("lights") or []}
    boxes = "".join(f"<fieldset style='border:1px solid #26272b;border-radius:8px;margin:6px 0;padding:6px 10px'><legend class=muted>{esc(r)}</legend>"
                    + "".join(f"<label style='margin-right:14px;white-space:nowrap'><input type=checkbox name='l_{esc(i, quote=True)}' value=1"
                              f"{' checked' if i in chosen else ''}> {esc(names[i])}</label>" for i in ids) + "</fieldset>" for r, ids in rooms)
    sw = lambda k, on, label: form(k, f"<input type=hidden name=on value='{'0' if on else '1'}'><button{' class=go' if on else ''}>{label}: {'on' if on else 'off'}</button>")
    last = (f" <span class=muted>Last pulse {_ago(_hue_run['last'])}: {esc(_hue_run['lastWhat'])}</span>" if _hue_run["last"] else "")
    return out + (f"<p>{where} · paired · {len(chosen)} lamp{'s' if len(chosen) != 1 else ''} chosen</p>"
                  f"<div class=row>{sw('switch', bool(st.get('on')), 'Pulse')} {sw('quiet', st.get('quiet', True) is not False, 'Quiet 22:00–07:00')} "
                  f"{form('test', '<button>Test pulse</button>')}{last}</div>"
                  f"<form method=post action='/admin/hue/lamps'>{boxes or '<p class=muted>The bridge has no lamps.</p>'}<button>Save lamps</button></form>"
                  f"<div class=row style='margin-top:10px'>{forget}</div>")


def hue_admin_post(what, f):
    global _hue
    if what == "find":
        hue_find()
    elif what == "use":
        hue_use(f.get("addr"))
    elif what == "pair":
        hue_pair()
    elif what == "forget":
        with _hue_lock:
            _hue = {}
        try:
            HUE_FILE.unlink()
        except OSError:
            pass
        hue_say("forgot the bridge")
    elif what in ("switch", "quiet") and hue_state().get("user"):
        hue_save(**{"on" if what == "switch" else "quiet": f.get("on") == "1"})
    elif what == "lamps" and hue_state().get("user"):
        lamps = hue_lamps()
        known = set(lamps[1]) if lamps else set()
        hue_save(lights=[k[2:] for k in f if k.startswith("l_") and k[2:] in known][:50])
        hue_say(f"{len(hue_state().get('lights') or [])} lamps chosen")
    elif what == "test":
        hue_say("test pulse" if hue_pulse(HUE_AMBER, "test") else "no lamps chosen yet (or a pulse is running)", bool(hue_state().get("lights")))


# Health watch (relay 45): Dave (the profile named HOME_OWNER) gets a notification when something breaks, and once when
# it is fine again; at most one alert an hour for each kind. Each is in the journal too.
HEALTH_FILE = DATA_DIR / "alive.json"      # {"t": last minute alive, "clean": stopped on purpose}
HEALTH_REPEAT_S = 3600
HEALTH_SOURCES_S = 15 * 60                 # every position source failing this long
HEALTH_DISK = 0.90                         # the data disk this full
_health_seen = {"posFail": 0.0}
_health = {}                               # kind -> {"down": bool, "sent": time of the last alert}
HEALTH_TEXT = {"sources": ("No flight positions: every source has failed for {m} minutes", "Flight positions are back"),
               "fr24": ("Flightradar24 refused the key: the boards use the free sources", "Flightradar24 lookups work again"),
               "disk": ("The relay's disk is {pct}% full", "The relay's disk has room again ({pct}% full)"),
               "restart": ("The relay restarted unexpectedly (last alive at {at}); it is running again", "")}


def _owner_push():
    """The owner's push subscriptions (the list itself, so gone ones can be removed), or []."""
    with _data_lock:
        for p in profiles()["profiles"].values():
            if str(p.get("name") or "").strip().lower() == HOME_OWNER.lower():
                return p.setdefault("push", [])
    return []


def _health_say(kind, down, **kw):
    text = HEALTH_TEXT[kind][0 if down else 1].format(**kw)
    event("warn" if down else "info", f"Health: {text}")
    subs = _owner_push() if PUSH_OK else []
    if subs:
        _deliver(subs, {"title": "Fallblatt relay", "body": text, "tag": "health-" + kind, "url": "/admin"}, urgent=down)


def _health_set(kind, down, **kw):
    """Note a kind's state; alert on going down (not twice within the hour) and once on coming back after an alert."""
    h = _health.setdefault(kind, {"down": False, "sent": 0.0, "alerted": False})
    if down == h["down"]:
        return
    h["down"] = down
    now = time.time()
    if down and now - h["sent"] >= HEALTH_REPEAT_S:
        h["sent"], h["alerted"] = now, True
        _health_say(kind, True, **kw)
    elif not down and h["alerted"]:
        h["alerted"] = False
        _health_say(kind, False, **kw)


def _health_alive(clean=False):
    try:
        DATA_DIR.mkdir(exist_ok=True)
        HEALTH_FILE.write_text(json.dumps({"t": time.time(), "clean": clean, "restartSent": _health_seen.get("restartSent", 0)}),
                               encoding="utf-8")
    except OSError:
        pass


def health_check():
    now = time.time()
    last_ok = max([STARTED] + [st.get("last_ok", 0.0) for st in STATE.values()])
    failing = now - _health_seen["posFail"] < 300 and _health_seen["posFail"] > last_ok
    _health_set("sources", failing and now - last_ok > HEALTH_SOURCES_S, m=int((now - last_ok) / 60))
    if fr24_key():
        _health_set("fr24", _fr24_state["state"] == "refused")
    try:
        du = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else DATA_DIR.parent)
        used = du.used / max(1, du.total)
        h = _health.get("disk") or {}
        _health_set("disk", used > HEALTH_DISK or (h.get("down") and used > HEALTH_DISK - .02), pct=round(used * 100))
    except OSError:
        pass


def _health_watch():
    try:
        was = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        was = None
    _health_seen["restartSent"] = (was or {}).get("restartSent", 0)
    _health_alive()
    if was and not was.get("clean") and time.time() - _health_seen["restartSent"] >= HEALTH_REPEAT_S:
        _health_seen["restartSent"] = time.time()
        _health_alive()
        time.sleep(20)                        # the owner's subscriptions and the push key are loaded by then
        _health_say("restart", True, at=time.strftime("%d %b %H:%M", time.localtime(was.get("t", 0))))
    while True:
        time.sleep(60)
        _health_alive()
        try:
            health_check()
        except Exception as e:
            event("warn", f"Health check failed: {e}", echo=False)


def _push_watch():
    while True:
        time.sleep(30)
        if not PUSH_OK:
            continue
        for who, subs, centre, spot, st in push_targets():
            try:
                window_check(who, subs, centre, spot, st)
                summary_check(who, subs, spot, st)
                review_check(who, subs, spot, st)
            except Exception as e:
                event("warn", f"Notification check failed for {who}: {e}", echo=False)


ADMIN_PATHS = ("/admin", "/screens", "/status")     # the home network only, and only for HOME_OWNER or a device without a profile (relay 43)
MEDIA_DIR = DATA_DIR / "media"
MEDIA = {"emirates-boarding.m4a": "audio/mp4"}     # relay 42: the Emirates airline card's boarding music (copyrighted: never in the repository)


class Handler(BaseHTTPRequestHandler):
    server_version = f"OverheadRelay/{RELAY_VERSION}"
    timeout = 30                    # a connection that sends nothing for this long is closed

    def log_message(self, fmt, *args):
        if ARGS.verbose:
            super().log_message(fmt, *args)

    # Relay 68: a client that went away before its answer was written (a phone locked mid-save) is no error worth a
    # traceback in the journal: one short line under --verbose.
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
            if ARGS and ARGS.verbose:
                print(f"{time.strftime('%H:%M:%S')} {self.command or '?'} {self.path.split('?')[0] if hasattr(self, 'path') else '?'}: the client went away before the answer", flush=True)

    def finish(self):
        try:
            super().finish()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def reply(self, status, content_type, body, extra=None):
        extra = dict(extra or {})
        if status == 200 and len(body) > 1024 and content_type.startswith(PACKED_TYPES):
            # relay 54: pages and data go packed (gzip) and tagged, so an unchanged page is a short "304" and a changed
            # one about a fifth of its size. Pages may hold a profile's place: kept by the browser only, and checked
            # with the relay on every open ("no-cache").
            tag = '"' + hashlib.sha256(body).hexdigest()[:24] + '"'
            if content_type.startswith("text/html"):
                extra.setdefault("Cache-Control", "private, no-cache")
            extra.update({"ETag": tag, "Vary": "Accept-Encoding, Cookie"})
            if tag in (self.headers.get("If-None-Match") or "") and extra.get("Cache-Control") != "no-store":
                status, body = 304, b""
            elif "gzip" in (self.headers.get("Accept-Encoding") or ""):
                body, extra["Content-Encoding"] = _gzip(body), "gzip"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", extra.pop("Cache-Control", "no-store"))
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

    def owner_ok(self):
        """The admin pages are Dave's (relay 43): a device of the one profile named HOME_OWNER. Other guests are turned
        away, even at home. A device without a profile only while there is no such profile yet (a fresh relay making its
        first invite), or on the relay's own computer (relay 54: before, any device at home without a profile got in)."""
        with _data_lock:
            hits = [pid for pid, p in profiles()["profiles"].items()
                    if str(p.get("name") or "").strip().lower() == HOME_OWNER.lower()]
        if self.guest:
            return hits == [self.guest[0]]
        return not hits or self.on_this_computer()

    def on_this_computer(self):
        """A request made on the relay's own computer (curl in an SSH session), not passed on by a proxy or the tunnel."""
        if self.headers.get("Cf-Connecting-IP") or self.headers.get("X-Forwarded-For"):
            return False
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def identify(self):
        """Who is asking: self.guest = (id, profile) for a signed-in device; anyone else is a stranger (relay 42: there
        is no Home any more; the home network only opens the admin pages, ADMIN_PATHS)."""
        pid, p = profile_for(self.cookie_token())
        self.guest = (pid, p) if pid else None
        self.stranger = not self.guest
        self.spot = guest_spot(pid) if pid else None

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
        return {k: ",".join(v) if k == "grant" else v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}

    def refuse(self, path):
        """No profile: a friendly page with the QR sign-in for people, a short answer for scripts."""
        if not allow("stranger:" + self.client_ip(), 1, 20):
            return self.reply(429, "text/plain", b"Too many requests")
        if PAGE.match(path):
            return self.reply(403, "text/html; charset=utf-8", plain_page("Fallblatt", (
                "<h1>This board is private</h1><p>Fallblatt shows the planes flying over your home on a split-flap board, for friends and family. "
                "Open the personal invite link you were sent to get in; it sets up this phone or computer.</p>"
                "<p><a href='/signin'>Sign in with your account</a></p>" + pair_page_js() +
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
            return self.jerr(403, "Sign in first")
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
                new = not (p.get("account") or {}).get("user")
                p.setdefault("account", {})["user"] = user
                if new:                         # relay 42: from now on they sign in; an unused invite link is void
                    P = profiles()
                    P["invites"] = {h: i for h, i in P["invites"].items() if i["profile"] != pid}
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

    def pair_who(self):
        """Who a phone would sign a screen in as: (profile id, name), or None for a phone that isn't signed in."""
        return (self.guest[0], self.guest[1]["name"]) if self.guest else None

    def pair_page(self, path):
        if not allow("pair:" + self.client_ip(), 0.5, 20):
            return self.reply(429, "text/plain", b"Too many requests")
        if path == "/pair":                                  # typing the code
            return self.reply(200, "text/html; charset=utf-8", pair_html(
                "<p>Type the code the screen shows.</p><form onsubmit=\"location.href='/pair/'+this.c.value.trim().toUpperCase();return false\">"
                "<p><input name=c maxlength=6 autocapitalize=characters autocomplete=off required "
                "style='background:#16171a;color:#f2b134;border:1px solid #34363b;border-radius:6px;padding:9px 10px;"
                "font:700 24px ui-monospace,monospace;letter-spacing:.18em;width:170px;text-transform:uppercase'> "
                "<button class=go type=submit>Next</button></p></form>"))
        code = path[len("/pair/"):].upper()
        pr = pair_find(code) if re.fullmatch(f"[{PAIR_ALPHA}]{{6}}", code) else None
        if not pr:
            return self.reply(404, "text/html; charset=utf-8", pair_html(
                "<p>That code isn't waiting any more. Codes last ten minutes; the screen shows a new one by itself.</p>"
                "<p><a href='/pair'>Type the code again</a></p>"))
        who = self.pair_who()
        if not who:
            return self.reply(200, "text/html; charset=utf-8", signin_html("/pair/" + code))
        if pr["pid"]:
            return self.reply(200, "text/html; charset=utf-8", pair_html("<p>Done: the screen signs itself in now.</p>"))
        return self.reply(200, "text/html; charset=utf-8", pair_html(
            f"<p>Sign in the screen showing <b style='color:#f2b134;letter-spacing:.12em'>{code}</b> ({html.escape(pr['device'])}) as "
            f"<b>{html.escape(who[1])}</b>?</p><p class=muted>Only for a screen in front of you: it gets your place, logbook and settings.</p>"
            f"<form method=post action='/pair/{code}'><button class='go big' type=submit>Sign in the screen</button></form>"))

    def pair_post(self, path):
        if not self.same_origin():
            return self.jerr(403, "Only from this site")
        ip = self.client_ip()
        if path == "/pair/new":
            if not allow("pairnew:" + ip, 0.05, 6):
                return self.jerr(429, "Too many codes; wait a minute")
            code, secret = pair_new(self.headers.get("User-Agent") or "")
            if not code:
                return self.jerr(503, "Busy; try again in a few minutes")
            host = (urllib.parse.urlsplit(ARGS.public_url).netloc if ARGS.public_url else "") or self.headers.get("Host") or ""
            base = (ARGS.public_url or "").rstrip("/") or f"{'https' if self.https() else 'http'}://{host}"
            return self.reply(200, "application/json", json.dumps({"code": code, "secret": secret, "host": host,
                                                                   "svg": qr_svg(f"{base}/pair/{code}")}).encode())
        if path == "/pair/wait":
            if not allow("pairwait:" + ip, 1, 30):
                return self.jerr(429, "Too many requests")
            h = _hash(str(self.json_body().get("secret") or ""))
            with _lock:
                hit = next(((c, pr) for c, pr in _pairs.items() if secrets.compare_digest(pr["secret"], h)), None)
                if hit and time.time() - hit[1]["t"] > PAIR_S:
                    del _pairs[hit[0]]
                    hit = None
                if hit and hit[1]["pid"]:
                    del _pairs[hit[0]]
            if not hit:
                return self.reply(200, "application/json", b'{"gone":true}')
            if not hit[1]["pid"]:
                return self.reply(200, "application/json", b'{"wait":true}')
            return self.signed_in(hit[1]["pid"], "a phone (QR code)")
        code = path[len("/pair/"):].upper()
        who = self.pair_who()
        pr = pair_find(code) if re.fullmatch(f"[{PAIR_ALPHA}]{{6}}", code) else None
        if not who or not pr:
            return self.pair_page("/pair/" + code)
        with _lock:
            pr["pid"] = pr["pid"] or who[0]
        event("info", f"{who[1]} signed in a {pr['device']} with a QR code")
        return self.reply(200, "text/html; charset=utf-8", pair_html("<p>Done: the screen signs itself in now.</p>"))

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

    def media(self, name):
        """Relay 42: a sound the boards play that can't be in the public repository (data/media/, MEDIA only), for
        signed-in devices, with byte ranges so a browser can stream it. 404 while the file isn't there."""
        ctype = MEDIA.get(name)
        f = MEDIA_DIR / name if ctype else None
        if not f or not f.is_file():
            return self.reply(404, "text/plain", b"Not found")
        size = f.stat().st_size
        a, b, part = 0, size - 1, False
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                a, b = int(m.group(1)), min(size - 1, int(m.group(2))) if m.group(2) else size - 1
            else:
                a = max(0, size - int(m.group(2)))
            if a > b or a >= size:
                return self.reply(416, "text/plain", b"", {"Content-Range": f"bytes */{size}"})
            part = True
        self.send_response(206 if part else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(b - a + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        if part:
            self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(f, "rb") as fh:
                fh.seek(a)
                left = b - a + 1
                while left > 0:
                    chunk = fh.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass                                # the board stopped listening (the card was closed)

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
        if path == "/pair" or path.startswith("/pair/"):
            return self.pair_page(path)
        if path == "/health" or BOARD_FILE.match(path):
            pass                                  # the app's icons and manifest (the manifest with cookies since relay 53) and the check
        elif path in ADMIN_PATHS and self.at_home():
            if not self.owner_ok():
                return self.reply(403, "text/plain", b"Only for the owner")
        elif self.stranger:
            return self.refuse(path)
        elif not allow("guest:" + self.guest[0], 8, 120):
            return self.reply(429, "text/plain", b"Too many requests")
        if path in ADMIN_PATHS and not self.at_home():
            return self.reply(403, "text/plain", b"Only at home")
        if path == "/push/key":
            v = vapid()
            return self.reply(200, "application/json", json.dumps({"key": v[1] if v else None}).encode())
        if path.startswith("/media/"):
            return self.media(path[len("/media/"):])
        if path == "/admin":
            with _lock:
                hit = _made.get((self.query().get("made") or [""])[0])
            made = hit[1] if hit and hit[0] > time.time() else None
            return self.reply(200, "text/html; charset=utf-8", admin_html(self.headers.get("Host") or "", made))
        if path == "/lists":
            fav, hide = lists_of(self.guest[0])
            return self.reply(200, "application/json", json.dumps({"fav": fav, "hide": hide}).encode())
        if path == "/places":
            return self.reply(200, "application/json", json.dumps({"places": places_of(self.guest[0])}).encode())
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
            return self.reply(200, "application/json", json.dumps(account_json(self.guest[0], self.secure())).encode())
        if path == "/photo":                # relay 47: a plane's photo for the share picture
            if not allow("photo:" + self.guest[0], 1, 20):
                return self.reply(429, "text/plain", b"Too many requests")
            status, ctype, body = photo_get((self.query().get("u") or [""])[0])
            return self.reply(status, ctype, body)
        if path == "/planephoto":           # relay 73: a plane's own photo from Planespotters.net
            if not allow("pphoto:" + self.guest[0], 2, 30):
                return self.reply(429, "text/plain", b"Too many requests")
            q = self.query()
            r = plane_photo((q.get("reg") or [""])[0], (q.get("hex") or [""])[0])
            if r is None:
                return self.reply(503, "text/plain", b"Planespotters.net can't be asked right now", {"Retry-After": "120"})
            return self.reply(200, "application/json", json.dumps(r).encode(), {"Cache-Control": "no-store"})
        if path == "/facts" and {"status", "refresh"} & set(self.query()):   # relay 78: the owner's look at the facts database
            if not self.owner_ok():
                return self.reply(403, "text/plain", b"Only for the owner")
            if "refresh" in self.query() and not _facts_running.locked():      # the monthly refresh now (three hours at most)
                threading.Thread(target=facts_refresh, args=(time.time() + 3 * 3600,), daemon=True).start()
                time.sleep(0.2)
            return self.reply(200, "application/json", json.dumps(facts_status()).encode(), {"Cache-Control": "no-store"})
        if path == "/facts":                # relay 74: a model's, airline's or airport's facts for its card
            if not allow("facts:" + self.guest[0], 2, 20):
                return self.reply(429, "text/plain", b"Too many requests")
            q = self.query()
            model = re.sub(r"[\x00-\x1f<>\[\]{}|#]", "", (q.get("model") or [""])[0]).strip()[:120]
            airline = re.sub(r"[^A-Z]", "", (q.get("airline") or [""])[0].upper())
            airport = re.sub(r"[^A-Z]", "", (q.get("airport") or [""])[0].upper())
            org = (q.get("org") or [""])[0].strip().upper()           # relay 77: a brand or group by its Wikidata id
            org = org if re.fullmatch(r"Q\d{1,12}", org) else ""
            own = (q.get("own") or [""])[0] == "1"                     # an airline's own facts, not its brand's ("Flown by")
            kind, key = (("model", model) if model else ("airline-own" if own else "airline", airline) if len(airline) == 3 else
                         ("airport", airport) if len(airport) == 3 else ("org", org) if org else ("", ""))
            if not kind:
                return self.reply(400, "text/plain", b"model=..., airline=... (ICAO), airport=... (IATA) or org=... (Wikidata) is required")
            r = facts_json(kind, key)
            if r is None:
                return self.reply(503, "text/plain", b"Wikipedia can't be asked right now", {"Retry-After": "300"})
            return self.reply(200, "application/json", json.dumps(r).encode(), {"Cache-Control": "private, max-age=3600"})
        if path == "/relayinfo":           # relay 69: the owner's Relay plate (also away from home, through the tunnel)
            if not self.owner_ok():
                return self.reply(403, "text/plain", b"Only for the owner")
            return self.reply(200, "application/json", json.dumps(relay_panel_json()).encode(), {"Cache-Control": "no-store"})
        if path == "/me":
            p = self.guest[1]
            return self.reply(200, "application/json", json.dumps({"name": p["name"], "settings": p.get("settings"), "fr24": bool(p.get("fr24"))}).encode())
        if re.fullmatch(r"/[a-z0-9-]{1,40}", path) and path not in ("/health", "/status", "/sightings", "/logbook", "/metar", "/flightinfo", "/times", "/hello", "/screens", "/airport", "/admin", "/me", "/seen", "/sky", "/watch", "/year", "/review", "/account", "/signin", "/lists", "/places", "/pageversion", "/photo", "/planephoto", "/search", "/now", "/airlines", "/relayinfo", "/facts"):
            self.send_response(301)  # /test → /test/
            self.send_header("Location", path + "/")
            self.end_headers()
            return
        bf = BOARD_FILE.match(path)
        if bf:
            want = (self.query().get("v") or [""])[0]
            want = want.lower() if re.fullmatch(r"[0-9a-fA-F]{8,64}", want) else ""
            status, body, exact = board_file(bf.group(1) or "", bf.group(2), bf.group(3), want)
            badge = ((self.guest[1].get("settings") or {}).get("badge") if self.guest else "") or ""
            if status == 200 and bf.group(2) == "manifest.webmanifest" and badge in BADGES:   # relay 53: the profile's badge
                return self.reply(200, FILE_TYPES["webmanifest"], badge_manifest(body, badge), {"Cache-Control": "no-cache", "Vary": "Cookie"})
            # relay 48: a file the board names by its version (i18n.js?v=...) is that version for good: kept a year
            keep = {"Cache-Control": "public, max-age=31536000, immutable"} if exact or bf.group(3) == "woff2" else {"Cache-Control": "no-cache"} if bf.group(3) == "css" else None   # fonts are named by content
            return self.reply(status, FILE_TYPES[bf.group(3)] if status == 200 else "text/plain", body, keep)
        page = PAGE.match(path)
        if page:
            html = board_html(page.group(1) or "", self.guest)
            if html is None:
                return self.reply(502, "text/plain; charset=utf-8", b"Couldn't download the board from GitHub yet. Check the internet connection and reload.")
            return self.reply(200, "text/html; charset=utf-8", html.encode("utf-8"))
        if path == "/pageversion":          # relay 45: the newest published version of a board, for its update notice
            sub = (self.query().get("p") or [""])[0]
            html = board_html(sub) if re.fullmatch(r"[a-z0-9-]{0,40}", sub) else None
            m = re.search(r'\{v: "(\d[\d.]*)"', html or "")
            body = {"v": m.group(1) if m else None, "date": _board_date.get(sub)}
            return self.reply(200, "application/json", json.dumps(body).encode(), {"Cache-Control": "no-store"})
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
            try:
                deg = min(89.0, max(0.0, float((q.get("deg") or ["0"])[0])))     # relay 65: the boards' angle (45)
            except ValueError:
                deg = 0.0
            api = (q.get("api") or [""])[0] == "1" and bool(self.guest[1].get("fr24"))
            place = same_spot(self.spot, places_of(self.guest[0]) if self.guest else [], place_key((q.get("place") or [""])[0]))
            data = sightings_json(self.spot, api, over, (q.get("all") or [""])[0] == "1", place, deg)
            if api:
                data["fr24"] = fr24_on()
            return self.reply(200, "application/json", json.dumps(data).encode())
        if path == "/flightinfo":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            cs = no_cs((q.get("cs") or [""])[0])[:8]
            hx = (q.get("hex") or [""])[0].strip().lower()[:6]
            # Relay 41: what is already in the cache costs nothing, so it is handed out even past a guest's daily share
            # or the budget; "off" (the board stops asking for a while) only without a key or for guests without it.
            info = fr24_info(cs, hx) if fr24_key() else None
            pid, p = self.guest
            if not fr24_key() or not p.get("fr24"):
                body = {"status": "off"}
            elif info:
                body = {"status": "none"} if info.get("none") else {"status": "ok", **info}
            elif not fr24_on():
                body = {"status": "off"}
            elif fr24_paced(0) or not guest_fr24(p):    # relay 42: past the profile's daily limit (credits), "none"
                body = {"status": "none"}
            else:
                fr24_want(cs, hx, 0, f"{p['name']} · {device_of(self.headers.get('User-Agent') or '')}", pid)
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
        if path == "/airlines":             # relay 68: names for the airline codes the board's own table lacks
            body = {}
            for c in re.findall(r"[A-Z]{3}", ((self.query().get("c") or [""])[0]).upper())[:40]:
                f = airline_fields(c + "1")
                body[c] = [f.get("airlineIata", ""), f["airlineName"]] if f else None
            return self.reply(200, "application/json", json.dumps(body).encode(), {"Cache-Control": "private, max-age=86400"} if _airlines else None)
        if path == "/airports/near":
            q = self.query()
            try:
                lat, lon = float((q.get("lat") or [""])[0]), float((q.get("lon") or [""])[0])
            except ValueError:
                return self.reply(400, "text/plain", b"lat and lon are required")
            if abs(lat) > 90 or abs(lon) > 180:
                return self.reply(400, "text/plain", b"Out of range")
            return self.reply(200, "application/json", json.dumps(airports_near(lat, lon)).encode())
        if path == "/game/me":            # relay 59: the score strip, often (small: no collections, no trophies)
            try:
                since = int((self.query().get("since") or ["0"])[0])
            except ValueError:
                since = 0
            with _data_lock:
                self.spot.ensure_day()
                g = game3_json(self.spot.book(), self.spot.day)
                aw = game_awards(self.spot, since) if since > 0 else None
            lg = league_json(self.guest[0])
            me = next((r for r in lg["rows"] if r["me"]), None)
            keep = ("points", "today", "level", "title", "into", "need", "week", "planesToday", "streak", "scannedToday", "km",
                    "lockons", "limits", "resets", "rules")      # relay 76: the limits, the rules; no more combo
            out = {k: g.get(k) for k in keep}
            if aw is not None:
                out["aw"] = aw                  # relay 76: the awards since ?since= (the app's pop-ups)
            out.update(rank=(me or {}).get("rank"), was=(me or {}).get("was"), champion=lg["championMe"],
                       below=(lg["rows"][me["rank"]]["name"] if me and me["rank"] < len(lg["rows"]) else None), players=len(lg["rows"]))
            return self.reply(200, "application/json", json.dumps(out).encode())
        if path == "/game/today":         # relay 71: Recent points, today's scored planes and their awards
            return self.reply(200, "application/json", json.dumps(game_today(self.spot)).encode())
        if path == "/game/league":        # relay 59: the league, for the app's Game page and the board's League page
            return self.reply(200, "application/json", json.dumps(league_json(self.guest[0] if self.guest else None)).encode())
        if path == "/game/player":        # relay 63: a league player's card
            if not allow("player:" + (self.guest[0] if self.guest else self.client_ip()), 1, 10):
                return self.reply(429, "text/plain", b"Too many requests")
            body = player_json(((self.query().get("id") or [""])[0])[:12], self.guest[0] if self.guest else None)
            return self.reply(200, "application/json", json.dumps(body).encode()) if body else self.reply(404, "text/plain", b"No such player")
        if path == "/game/hangar":        # relay 63: the Spotters' Club hangar
            return self.reply(200, "application/json", json.dumps(hangar_json(self.spot)).encode())
        if path == "/logbook/spotted":    # relay 74: one airline's, model's or airport's Spotted (the cards)
            q = self.query()
            part, key = next(((p, re.sub(r"[^A-Z0-9]", "", (q.get(n) or [""])[0].upper())[:4]) for n, p in (("airline", "al"), ("type", "ty"), ("airport", "ap"))
                              if q.get(n)), ("", ""))
            if not key:
                return self.reply(400, "text/plain", b"airline=..., type=... or airport=... is required")
            if not allow("spotted:" + (self.guest[0] if self.guest else self.client_ip()), 2, 10):
                return self.reply(429, "text/plain", b"Too many requests")
            return self.reply(200, "application/json", json.dumps(spotted_json(self.spot, part, key)).encode())
        if path == "/logbook/category":   # relay 61: one category's top ten (types, aircraft, operators)
            q = self.query()
            cat = (q.get("c") or [""])[0]
            if cat not in ("passenger", "cargo", "bizjet", "private", "helicopter", "military", "other"):
                return self.reply(400, "text/plain", b"category?")
            if not allow("cat:" + (self.guest[0] if self.guest else self.client_ip()), 1, 6):
                return self.reply(429, "text/plain", b"Too many requests")
            places = [place_key(k) for k in (q.get("place") or [])[:6] if place_key(k)]
            return self.reply(200, "application/json", json.dumps(category_top_json(self.spot, cat, places)).encode())
        if path == "/logbook":
            raw = [place_key(k) for k in (self.query().get("place") or [""])[:6]]
            # relay 40: place=a&place=b, merged; relay 77 (to-do #126): with the profile's places at the same spot
            # (same_spot: "Home" and "home"), each sighting once (one place each)
            mine = places_of(self.guest[0]) if self.guest else []
            keys = sorted(set().union(*(same_spot(self.spot, mine, k) for k in raw))) if all(raw) else []
            place = (keys[0] if len(keys) == 1 else tuple(keys)) if keys else None
            body = place_logbook_json(self.spot, place) if place else logbook_json(self.spot)
            if not place:     # relay 77: each place's others at the same spot, so the place bar shows one place for one spot
                ks = {k for k, _ in body.get("places", [])} | {p["k"] for p in mine if isinstance(p, dict) and p.get("k")}
                body["spots"] = {k: sorted(o) for k in sorted(ks) for o in [same_spot(self.spot, mine, k) or set()] if len(o) > 1}
            if not place and self.guest and isinstance(body.get("game"), dict):
                body["game"]["styleGrants"] = style_grants(self.guest[1])      # relay 52
                lg = league_json(self.guest[0])                                 # relay 59: the crown and the Champion style
                body["game"]["champion"] = lg["championMe"]
                me = next((r for r in lg["rows"] if r["me"]), None)
                body["game"]["rank"], body["game"]["was"] = (me or {}).get("rank"), (me or {}).get("was")
            return self.reply(200, "application/json", json.dumps(body).encode())
        if path == "/now":              # relay 56: the plane overhead now, for the Android app's widget
            if not allow("now:" + self.guest[0], 1, 4):
                return self.reply(429, "text/plain", b"Too many requests")
            return self.reply(200, "application/json", json.dumps(now_json(self.guest[0], self.guest[1].get("settings") or {})).encode())
        if path == "/search":           # relay 55: the whole logbook searched (the app's Logbook tab)
            if not allow("search:" + (self.guest[0] if self.guest else self.client_ip()), 1, 6):
                return self.reply(429, "text/plain", b"Too many requests")
            q = ((self.query().get("q") or [""])[0])[:60]
            return self.reply(200, "application/json", json.dumps(search_json(self.spot, q)).encode())
        if path == "/seen":
            cs = re.sub(r"[^A-Z0-9]", "", ((self.query().get("cs") or [""])[0]).upper())[:8]
            if cs:
                return self.reply(200, "application/json", json.dumps(seen_json(self.spot, cs, "flights")).encode())
            reg = re.sub(r"[^A-Z0-9-]", "", ((self.query().get("reg") or [""])[0]).upper())[:10]
            if not reg:
                return self.reply(400, "text/plain", b"reg=... or cs=... is required")
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
        if path == "/review":                   # relay 46: the week or month in review
            q = self.query()
            try:
                back = int((q.get("back") or ["0"])[0])
            except ValueError:
                back = 0
            return self.reply(200, "application/json", json.dumps(review_json(self.spot, (q.get("span") or ["week"])[0], back)).encode())
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
            if not allow("pos:" + self.guest[0], 2, 30):       # relay 42: one profile can be a whole house of screens
                return self.reply(429, "text/plain", b"Too many requests")
            lat, lon = f"{float(lat):.2f}", f"{float(lon):.2f}"      # within a kilometre is the same question (relay 33)
            status, body, source, freshness = aircraft(lat, lon, nm)
            extra = {"X-Relay-Source": source, "X-Relay-Data": freshness}
            if status == 200:
                seen, q = body, self.query()
                place = screen_place(q)
                stale = live_stale(q, place)
                try:                    # relay 66: away from home, Flightradar24 adds the low planes the free sources miss
                    rec = None if q.get("bg") or stale else fill_want(lat, lon, *self.guest, f"{self.guest[1].get('name')} · Gap filler")
                    if rec:
                        body, seen, n = fill_merge(body, rec, float(lat), float(lon), int(nm) * 1.852)
                        extra["X-Relay-Fill"] = str(n)
                except Exception as e:  # never let the paid extra break the live board
                    event("warn", f"Flightradar24 gap filler: {e}", echo=False)
                try:
                    if not stale:
                        with _data_lock:
                            self.spot.take(seen, lat, lon, nm, place)
                except Exception as e:  # never let history problems break the live board
                    event("warn", f"Couldn't record sightings: {e}")
            return self.reply(status, "application/json", body, {**extra, "X-Sightings-Rev": str(self.spot.rev)})
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
        if path == "/pair" or path.startswith("/pair/"):
            return self.pair_post(path)
        if path.startswith("/admin/"):
            if not self.at_home() or not self.same_origin():
                return self.reply(403, "text/plain", b"Only from the admin page at home")
            if not self.owner_ok():
                return self.reply(403, "text/plain", b"Only for the owner")
            return self.admin_post(path)
        if self.stranger:
            return self.refuse(path)
        if not allow("guest:" + self.guest[0], 8, 120):
            return self.reply(429, "text/plain", b"Too many requests")
        if path == "/places":               # the profile's saved places (relay 33)
            if not self.same_origin():
                return self.reply(403, "text/plain", b"Only from this site")
            j = self.json_body()
            with _data_lock:
                owner = self.guest[1]
                owner["places"] = _clean_places(j.get("places"))
                _dirty.add("profiles")
                out = list(owner["places"])
            return self.reply(200, "application/json", json.dumps({"places": out}).encode())
        return self.profile_post(path)

    def admin_post(self, path):
        """The admin page's forms (home network only, same origin)."""
        f, made = self.form(), None
        if path == "/admin/invite" and (f.get("name") or "").strip():
            name = re.sub(r"[\x00-\x1f<>]", "", f["name"]).strip()[:40]
            made = (name, new_invite(name=name))
        elif path == "/admin/link" and f.get("pid") in profiles()["profiles"]:
            code = new_invite(pid=f["pid"])
            if code:
                made = (profiles()["profiles"][f["pid"]]["name"], code)
        elif path == "/admin/fr24plan":
            try:
                ARGS.fr24_reset_day = min(28, max(1, int(f.get("day") or 1)))
                ARGS.fr24_budget = min(1000000, max(0, int(f.get("budget") or FR24_BUDGET)))
                promo, until = (f.get("promo") or "").strip(), (f.get("until") or "").strip()
                if promo and until:
                    ARGS.fr24_budget_promo = min(1000000, max(0, int(promo)))
                    ARGS.fr24_promo_until = datetime.date.fromisoformat(until).isoformat()
                else:
                    ARGS.fr24_budget_promo = ARGS.fr24_promo_until = None
                save_config()
                p = _fr24_promo()
                event("info", f"Flightradar24: the plan renews on day {ARGS.fr24_reset_day}, at most {_fr24_budget():,} credits a month"
                              + (f" until {p[1].isoformat()}, then {_fr24_base_budget():,}" if p else ""))
            except (ValueError, OSError) as e:
                event("warn", f"Couldn't save the Flightradar24 plan: {e}")
        elif path == "/admin/limit" and f.get("pid") in profiles()["profiles"]:
            with _data_lock:              # relay 42: the profile's Flightradar24 credits a day; empty is automatic
                p = profiles()["profiles"][f["pid"]]
                v = (f.get("limit") or "").strip()
                if v.isdigit():
                    p["fr24Limit"] = min(100000, int(v))
                else:
                    p.pop("fr24Limit", None)
                _dirty.add("profiles")
            event("info", f"Flightradar24 for {p['name']}: at most {fr24_limit(p):,} credits a day" + ("" if v.isdigit() else " (automatic)"))
        elif path == "/admin/styles" and f.get("pid") in profiles()["profiles"]:
            with _data_lock:              # relay 52: styles granted by hand: mode all | earned | pick (grant = ids, repeated or comma-separated)
                p = profiles()["profiles"][f["pid"]]
                mode = (f.get("mode") or "").strip()
                if mode == "all":
                    p["styleGrants"] = "all"
                elif mode == "pick":
                    ids = {i for i, _ in STYLE_GRANTS}
                    p["styleGrants"] = [i for i in (f.get("grant") or "").split(",") if i in ids]
                else:
                    p.pop("styleGrants", None)
                if p.get("styleGrants") == []:
                    p.pop("styleGrants", None)
                _dirty.add("profiles")
            event("info", f"Styles for {p['name']}: " + ("earned only" if "styleGrants" not in p else "all granted" if p["styleGrants"] == "all" else f"{len(p['styleGrants'])} granted"))
        elif path == "/admin/username" and f.get("pid") in profiles()["profiles"]:
            user = (f.get("user") or "").strip().lower()
            other = account_of(user)
            if ACCOUNT_RE.match(user) and (not other or other == f["pid"]):
                with _data_lock:
                    p = profiles()["profiles"][f["pid"]]
                    p.setdefault("account", {})["user"] = user
                    P = profiles()
                    P["invites"] = {h: i for h, i in P["invites"].items() if i["profile"] != f["pid"]}
                    _dirty.add("profiles")
                event("info", f"{p['name']} has the username {user} (admin page)")
            else:
                event("warn", f"Username {user[:30] or '(empty)'} not set: " + ("taken" if other else "3 to 30 letters, digits, dots, dashes or underscores"))
        elif path == "/admin/password" and f.get("pid") in profiles()["profiles"]:
            pw = f.get("pw") or ""
            with _data_lock:
                p = profiles()["profiles"][f["pid"]]
                ok = len(pw) >= 8 and (p.get("account") or {}).get("user")
                if ok:
                    p["account"]["pw"] = _pw_hash(pw)
                    _dirty.add("profiles")
            if ok:
                pw_failed(p["account"]["user"], True)
            event("info" if ok else "warn", f"{p['name']}'s password " + ("set on the admin page" if ok else "not set: at least 8 characters, and a username first"))
        elif path == "/admin/device" and f.get("pid") in profiles()["profiles"]:
            d = (f.get("d") or "")[:16]
            with _data_lock:
                p = profiles()["profiles"][f["pid"]]
                n = len(p["devices"])
                if len(d) == 16:
                    p["devices"] = [x for x in p["devices"] if x["token"][:16] != d]
                _dirty.add("profiles")
            if len(p["devices"]) < n:
                event("info", f"Signed out one of {p['name']}'s devices (admin page)")
        elif path == "/admin/resetaccount" and f.get("pid") in profiles()["profiles"]:
            with _data_lock:
                a = profiles()["profiles"][f["pid"]].get("account") or {}
                a.pop("pw", None)
                a["passkeys"] = []
                _dirty.add("profiles")
        elif path == "/admin/remove" and f.get("pid"):
            remove_profile(f["pid"])
        elif path.startswith("/admin/hue/"):
            hue_admin_post(path[len("/admin/hue/"):], f)
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

    def profile_post(self, path):
        """The rest of the POSTs, from a signed-in device."""
        if path == "/handover":             # relay 54: the Android app on the Wi-Fi moves to the https address (TLS proves
            pub = (ARGS.public_url or "").rstrip("/")   # it's this relay): a one-time link for this phone's profile there
            if not self.same_origin() or not pub.startswith("https://"):
                return self.reply(404 if self.same_origin() else 403, "text/plain", b"No https address")
            if self.https() or not allow("handover:" + self.guest[0], 1 / 600, 3):
                return self.reply(429, "text/plain", b"Not now")
            code = new_invite(pid=self.guest[0])
            return self.reply(200, "application/json", json.dumps({"link": f"{pub}/join/{code}"}).encode())
        if path == "/game/lockon":          # relay 59: Sky view held a plane in its ring
            if not self.same_origin() or not allow("lock:" + self.guest[0], 1, 4):
                return self.reply(429, "text/plain", b"Not now")
            hx = str(self.json_body().get("hex") or "")
            if not re.fullmatch(r"~?[0-9a-fA-F]{6}", hx):
                return self.reply(400, "text/plain", b"hex missing")
            out = game_lockon(self.spot, hx)
            if out.get("bonus"):
                event("info", f"Sky view scan for {self.guest[1].get('name')}: +{out['bonus']}")
            return self.reply(200, "application/json", json.dumps(out).encode())
        if path == "/skyreport":            # relay 72: Sky view's sensor readings, for tuning the compass (the owner's)
            if not self.same_origin():
                return self.reply(403, "text/plain", b"Only from this site")
            if not self.guest or not self.owner_ok():   # (strangers never get here; owner_ok lets the relay's own computer in)
                return self.reply(403, "text/plain", b"Only for the owner")
            if not allow("skyrep:" + self.guest[0], 1 / 10, 3):
                return self.reply(429, "text/plain", b"Not now")
            j = sky_report_clean(self.json_body())
            if not j:
                return self.reply(400, "text/plain", b"Nothing to keep")
            j["at"] = int(time.time())
            n = sky_report_save(self.guest[0], j)
            event("info", f"Sky view report from {self.guest[1].get('name')} ({n} kept)")
            return self.reply(200, "application/json", json.dumps({"ok": True, "kept": n}).encode())
        if path == "/lists":                # favourites and hidden planes, from the phone app
            if not self.same_origin():
                return self.reply(403, "text/plain", b"Only from this site")
            j = self.json_body()
            with _data_lock:
                L = self.guest[1].setdefault("lists", {})
                ops = j.get("ops") if isinstance(j.get("ops"), list) else [j]
                for o in ops[:4]:               # relay 54: changes, not whole lists, so two devices saving at once keep both
                    op, which = (o.get("op"), o.get("list")) if isinstance(o, dict) else (None, None)
                    if op not in ("add", "remove") or which not in ("fav", "hide"):
                        continue
                    item = _clean_list([o.get("item")])
                    keep = [i for i in L.get(which, []) if not item or (i.get("k"), i.get("v")) != (item[0].get("k"), item[0].get("v"))]
                    L[which] = _clean_list(keep[-199:] + item if op == "add" else keep)
                for k in ("fav", "hide"):
                    if k in j:
                        L[k] = _clean_list(j[k])
                _dirty.add("profiles")
                out = {"fav": L.get("fav", []), "hide": L.get("hide", [])}
            return self.reply(200, "application/json", json.dumps(out).encode())
        if path == "/push/test":            # relay 57: Settings → Notifications → Send a test, to this profile's devices
            if not self.same_origin() or not PUSH_OK or not allow("pushtest:" + self.guest[0], 1 / 20, 3):
                return self.reply(429, "text/plain", b"Not now")
            with _data_lock:
                subs = self.guest[1].get("push") or []
            if not subs:
                return self.reply(404, "text/plain", b"No notifications are on")
            threading.Thread(target=_deliver, args=(subs, {"title": "Fallblatt", "body": ptext("test", (subs[-1].get("lang") or "en")),
                                                           "tag": "test", "url": "/app/"}), daemon=True).start()
            return self.reply(204, "text/plain", b"")
        if path in ("/push/subscribe", "/push/unsubscribe"):
            length = int(self.headers.get("Content-Length") or 0)
            if length > 4096 or not PUSH_OK:
                return self.reply(400 if PUSH_OK else 501, "text/plain", b"No notifications here")
            if not self.same_origin():
                return self.reply(403, "text/plain", b"Only from this site")
            try:
                j = json.loads(self.rfile.read(length) or b"{}")
                sub = j["subscription"]
                fcm = str(sub.get("fcm") or "")
                if fcm:                     # relay 57: the Android app, through Firebase
                    assert fcm_ready() and re.fullmatch(r"[A-Za-z0-9:_-]{20,400}", fcm)
                    ep, keys = "fcm:" + fcm, {}
                else:
                    ep, keys = str(sub["endpoint"]), sub["keys"]
                    assert push_endpoint_ok(ep) and isinstance(keys.get("p256dh"), str) and isinstance(keys.get("auth"), str)
                    assert len(keys["p256dh"]) < 200 and len(keys["auth"]) < 100
            except (ValueError, KeyError, TypeError, AttributeError, AssertionError):
                return self.reply(400, "text/plain", b"subscription missing")
            with _data_lock:
                subs = self.guest[1].setdefault("push", [])
                subs[:] = [s_ for s_ in subs if s_["endpoint"] != ep]
                if path == "/push/subscribe":
                    prefs = j.get("prefs") or {}
                    one = {"endpoint": ep, "lang": str(j.get("lang") or "en")[:2], "prefs": _push_prefs(prefs), "added": time.time()}
                    one.update({"fcm": fcm} if fcm else {"keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}})
                    subs.append(one)
                    del subs[:-10]
                _dirty.add("profiles")
            return self.reply(204, "text/plain", b"")
        if path == "/me":               # a guest's settings, so their other devices (and the relay) know their place
            if (self.headers.get("Origin") or self.headers.get("Referer")) and not self.same_origin():   # relay 54, like the other saves
                return self.reply(403, "text/plain", b"Only from this site")
            length = int(self.headers.get("Content-Length") or 0)
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
    p.add_argument("--fr24-reset-day", type=int, help="the day of the month the Flightradar24 plan renews (default 1)")
    p.add_argument("--fr24-budget-promo", type=int, help="a higher monthly budget for a while (a promotion), until --fr24-promo-until")
    p.add_argument("--fr24-promo-until", help="the last day (YYYY-MM-DD) the promotion's budget applies; then --fr24-budget again")
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
        STATE["custom"] = {"ok": 0, "fail": 0, "strikes": 0, "cooldown_until": 0.0, "last_status": None, "last_error": "", "last_ok": 0.0,
                           "last_call": 0.0, "day": "", "used": 0, "askedDay": "", "asked": 0}   # relay 35: without it, relay 34 failed every request to a --source
    threading.Thread(target=_saver, daemon=True).start()
    threading.Thread(target=_enricher, daemon=True).start()
    threading.Thread(target=_fr24_worker, daemon=True).start()
    threading.Thread(target=_fill_worker, daemon=True).start()
    threading.Thread(target=_screen_watch, daemon=True).start()
    threading.Thread(target=_push_watch, daemon=True).start()
    threading.Thread(target=_health_watch, daemon=True).start()
    threading.Thread(target=_hue_watch, daemon=True).start()
    threading.Thread(target=_where_worker, daemon=True).start()
    threading.Thread(target=_where_sweep, daemon=True).start()
    with _data_lock:
        _fr24_data()
        profiles()
        merge_home()
    threading.Thread(target=_airlines_worker, daemon=True).start()
    threading.Thread(target=_scrub_at_all, daemon=True).start()
    threading.Thread(target=_fr24_keep_cached, daemon=True).start()
    threading.Thread(target=_facts_worker, daemon=True).start()

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

    def stop(*_):                             # systemd stops with SIGTERM: a stop on purpose, not a crash (relay 45)
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, stop)
    except (ValueError, OSError):
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    _health_alive(clean=True)


if __name__ == "__main__":
    main()
