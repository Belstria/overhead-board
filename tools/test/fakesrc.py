"""Made-up flight data for testing the relay and the boards, on http://127.0.0.1:8095 (env FAKE_PORT for another
port). Started by run_test_relay.py.

It stands in for the position source, adsbdb (routes and aircraft), Flightradar24 (key "goodkey"), Vienna Airport's
flight lists and the airline list (relay 68: a few real rows and made-up ones; EIN6AB, an Aer Lingus flight with no
route listed, is an airline the board's own table lacks), and Planespotters.net's photo API (relay 73: OE-LBN by its
registration, the A380 only by its hex, and for the military C-130's hex another aircraft's photo, which the relay must
pass over), and Wikipedia and Wikidata for the cards' facts (relay 74: two model pages, two airlines, two airports, and
Commons photos as a drawing). The planes sit around central Vienna (the boards' default location) and include the special cases:
an A380, a rescue helicopter, a military plane, an emergency squawk, a diverted flight, cargo and a business jet,
a landing, a take-off and a take-off roll at Vienna airport, a callsign with a wrong route in the database, and one far away and high.
QUIET=1 leaves out the special planes; HOVER=1 adds a police helicopter hovering overhead; FAR=1 starts the landing 32 km out.
RING=1 (1.98, the game's two circles) adds two planes from the south: one comes within 15 km after about 30 s (passive
points and, since 1.126.1, its scan ticket) and within 10 km after about 55 s; the other passes 12 km out from about 65 s on
(passive points and a scan, too: one circle since 1.126.1).
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
             "hex/44D0AB": ("1000003", "oo-tek-tea-belgium-boeing-737-2q9-adv"),
             # relay 95: photos of the aircraft that had the registration before (a list: photos in their order)
             "reg/N700GR": [("1000004", "n700gr-goodrich-bombardier-global-5000-bd-700-1a11")],
             "reg/N800GR": [("1000005", "n800gr-private-bombardier-global-6000-bd-700-1a10"),
                            ("1000006", "n800gr-private-piper-pa-46-600tp-m700-fury")]}
PS_ASKED = collections.Counter()
NAMES_FAILED = set()        # SLOW_NAMES=1 (run_test_relay.py --slow-names): the points whose first name lookup failed
PS_PHOTO = """<svg xmlns="http://www.w3.org/2000/svg" width="420" height="280" viewBox="0 0 420 280">
<defs><linearGradient id="e" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2d3c63"/><stop offset=".7" stop-color="#d9825b"/><stop offset="1" stop-color="#f2c38b"/></linearGradient></defs>
<rect width="420" height="280" fill="url(#e)"/><rect y="236" width="420" height="44" fill="#3a3f45"/>
<path d="M70 190 L340 182 Q362 182 366 190 Q362 198 340 199 L70 197 Q55 194 70 190 Z" fill="#eceae4"/>
<path d="M330 184 L360 120 L382 120 L362 187 Z" fill="#c8102e"/><path d="M170 196 L230 244 L254 244 L222 196 Z" fill="#cfcfcb"/>
</svg>"""


# Wikipedia and Wikidata for the cards' facts (relay 74): two model pages (one with the specs template, one with an
# airliner's specifications table), Austrian Airlines and Emirates by their ICAO codes, Vienna and Dubai airports by
# their IATA codes; any other page is missing. How often each was asked: /wm/asked (flows.py: asked once, then kept).
WIKI = {
    "Airbus A320 family": ("The Airbus A320 family is a series of narrow-body airliners developed and produced by Airbus.\nIt was "
                           "launched in March 1984.", """{{Infobox aircraft begin|name=Airbus A320 family}}{{Infobox aircraft type
| status = In service
| primary_user = [[American Airlines]]
| more_users = {{ubl|[[China Eastern Airlines]]|[[EasyJet|easyJet]]}}<!-- three at most -->
| first_flight = {{start date and age|1987|2|22|df=y}}
| introduction = 18 April 1988 with [[Air France]]
| produced = 1986{{ndash}}present
| number_built = 12,900 {{as of|2026|09|lc=y}}<ref name=od>{{cite web |title=O&D}}</ref>
| developed_into = [[Airbus A320neo family]]
}}
'''Airbus A320 family''' text.
==Specifications==
{| class="wikitable"
!Variant
!A320
!A321
|-
!Exit limit
|180
|236
|-
!Length
|{{cvt|37.57|m|ft}}
|{{cvt|44.51|m|ft}}
|-
!Wingspan
|colspan=2 |{{cvt|35.80|m|ftin}}{{efn|with sharklets}}
|-
!Engines (×2)
|colspan=2 |[[CFM International CFM56|CFM56-5B]]<br>[[IAE V2500|IAE V2500A5]]
|-
!Range
|{{cvt|3,300|nmi|km}}
|{{cvt|3,200|nmi|km}}
|}
==Notes=="""),
    "Airbus A330neo": ("The Airbus A330neo is a wide-body airliner developed by Airbus from the original Airbus A330.", """{{Infobox aircraft
| name = Airbus A330neo
| status = In service
| primary_user = [[Delta Air Lines]]
| number_built = 199 {{as of|2026|09|lc=yes}}
| construction_date = 2015{{ndash}}present
| introduction = 15 December 2018 with [[TAP Air Portugal]]<ref name=TAP15dec2018/>
| first_flight = {{start date and age|2017|10|19|df=y}}
| developed_from = [[Airbus A330]]
}}
==Specifications==
{{Aircraft specs
|crew=2
|capacity=440 passengers and either 33 [[Unit load device|LD3s]] or 9 pallets
|length m=63.69
|span m=64
|range km=13334
|eng1 number=2
|eng1 name=[[Rolls-Royce Trent 7000|Rolls-Royce Trent 7000-72]]
|eng1 type=[[turbofan]] engines
}}"""),
    "Austrian Airlines": ("Austrian Airlines AG is the flag carrier of Austria.", """{{Infobox airline
| callsign = AUSTRIAN
| parent = [[Lufthansa Group]]
| commenced = {{start date and age|1958|03|31|df=yes}}
| hubs = {{nowrap|[[Vienna International Airport]]}}
| alliance = [[Star Alliance]]
| fleet size = 65
| destinations = [[List of Austrian Airlines destinations|121]]
| num employees = 5,659 (as of December 2022)
}}"""),
    "Emirates (airline)": ("Emirates is one of two flag carriers of the United Arab Emirates.", """{{Infobox airline
| callsign = EMIRATES
| commenced = 25 October 1985
| fleet size = 262
| destinations = 152
}}"""),
    # relay 77 (to-do #122): Wizz Air Malta flies under its group's name (the brand's card, its fleet with Malta's and
    # the UK's); Austrian keeps its own, part of the Lufthansa Group
    "Wizz Air": ("Wizz Air is a Hungarian ultra-low-cost airline.", """{{Infobox airline
| callsign = WIZZ AIR
| fleet size = 118
| destinations = 194
}}"""),
    "Wizz Air Malta": ("Wizz Air Malta is a Maltese low-cost airline, a subsidiary of Wizz Air.", """{{Infobox airline
| fleet size = 127
}}"""),
    "Wizz Air UK": ("Wizz Air UK is a British low-cost airline.", """{{Infobox airline
| fleet size = 21
}}"""),
    "Lufthansa Group": ("The Lufthansa Group is a German airline group.", """{{Infobox company
| founded = 1926
}}"""),
    "Vienna International Airport": ("Vienna International Airport is the international airport of Vienna.", ""),
    "Dubai International Airport": ("Dubai International Airport is the primary international airport serving Dubai.", ""),
}
WD_ITEM = lambda v: {"mainsnak": {"datavalue": {"value": {"entity-type": "item", "id": v}}}, "rank": "normal"}           # noqa: E731
WD_STR = lambda v: {"mainsnak": {"datavalue": {"value": v}}, "rank": "normal"}                                           # noqa: E731
WD_TIME = lambda y, m=0, d=0, p=9: {"mainsnak": {"datavalue": {"value": {"time": f"+{y}-{m:02d}-{d:02d}T00:00:00Z", "precision": p}}}, "rank": "normal"}  # noqa: E731
WD_QTY = lambda n, unit="1", year=None: {"mainsnak": {"datavalue": {"value": {"amount": f"+{n}", "unit": unit}}}, "rank": "normal",   # noqa: E731
                                          **({"qualifiers": {"P585": [{"datavalue": {"value": {"time": f"+{year}-00-00T00:00:00Z", "precision": 9}}}]}} if year else {})}
WIKIDATA = {
    "Q781770": ("Austrian Airlines", "Austrian Airlines", {"P230": [WD_STR("AUA")], "P571": [WD_TIME(1957, 9, 30, 11)], "P113": [WD_ITEM("Q191588")],
                                                          "P114": [WD_ITEM("Q189208")], "P159": [WD_ITEM("Q874848")], "P127": [WD_ITEM("Q9325")],
                                                          "P749": [WD_ITEM("Q62589018")],
                                                          "P18": [WD_STR("OE-LPM @ VIE, 2024-08-30.jpg")]}),
    "Q190811": ("Emirates", "Emirates (airline)", {"P230": [WD_STR("UAE")], "P571": [WD_TIME(1985)], "P113": [WD_ITEM("Q193439")]}),
    "Q11187": ("Alitalia", "Alitalia", {"P230": [WD_STR("AZA")], "P576": [WD_TIME(2021, 10, 14, 11)]}),
    "Q335147": ("Wizz Air", "Wizz Air", {"P230": [WD_STR("WZZ")], "P571": [WD_TIME(2003, 9, 0, 10)], "P749": [WD_ITEM("Q114314826")]}),
    "Q113637091": ("Wizz Air Malta", "Wizz Air Malta", {"P230": [WD_STR("WMT")], "P571": [WD_TIME(2022)], "P749": [WD_ITEM("Q114314826"), WD_ITEM("Q335147")]}),
    "Q55525155": ("Wizz Air UK", "Wizz Air UK", {"P230": [WD_STR("WUK")], "P571": [WD_TIME(2017)], "P749": [WD_ITEM("Q114314826")]}),
    "Q114314826": ("Wizz Air Holdings", "", {}), "Q62589018": ("Lufthansa Group", "Lufthansa Group", {"P571": [WD_TIME(1926, 1, 6, 11)]}),
    "Q191588": ("Vienna International Airport", "Vienna International Airport", {
        "P238": [WD_STR("VIE")], "P3872": [WD_QTY(29530000, year=2023), WD_QTY(31700000, year=2024)], "P2044": [WD_QTY(600, "http://www.wikidata.org/entity/Q3710")],
        "P1619": [WD_TIME(1938)], "P529": [WD_STR("11/29"), WD_STR("16/34")], "P137": [WD_ITEM("Q699346")], "P931": [WD_ITEM("Q1741")], "P17": [WD_ITEM("Q40")],
        "P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 48.1103, "longitude": 16.5697}}}, "rank": "normal"}], "P18": [WD_STR("Flughafen Wien.jpg")]}),
    "Q193439": ("Dubai International Airport", "Dubai International Airport", {
        "P238": [WD_STR("DXB")], "P3872": [WD_QTY(92331506, year=2024), WD_QTY(95200000, year=2025)], "P2044": [WD_QTY(62, "http://www.wikidata.org/entity/Q3710")],
        "P1619": [WD_TIME(1960)], "P529": [WD_STR("12L/30R"), WD_STR("12R/30L")], "P931": [WD_ITEM("Q612")], "P17": [WD_ITEM("Q878")],
        "P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 25.2528, "longitude": 55.3644}}}, "rank": "normal"}], "P18": [WD_STR("Dubai Airport.jpg")]}),
    "Q189208": ("Star Alliance", "", {}), "Q874848": ("Schwechat", "", {}), "Q9325": ("Lufthansa Group", "", {}),
    "Q699346": ("Flughafen Wien AG", "", {}), "Q1741": ("Vienna", "", {}), "Q612": ("Dubai", "", {}), "Q40": ("Austria", "", {}),
    "Q878": ("United Arab Emirates", "", {}),
}
WM_ASKED = collections.Counter()


def wikipedia(q):
    """The fake Wikipedia API (formatversion 2): a page's wikitext and introduction, or missing. Relay 78's refresh asks
    for several titles at once: their introductions come one at a time here (Wikipedia's 20), the rest after "continue"."""
    ts = (q.get("titles") or [""])[0].split("|")
    if len(ts) > 1:
        WM_ASKED["batch:wiki"] += 1
    start = int((q.get("excontinue") or ["0"])[0])
    pages, intros = [], 0
    WM_ASKED["batch:wiki-continued"] += bool(start)
    for i, t in enumerate(ts):
        WM_ASKED["wiki:" + t] += not start
        if t not in WIKI:
            pages.append({"title": t, "missing": True})
            continue
        intro, wt = WIKI[t]
        p = {"title": t} if start else {"title": t, "revisions": [{"slots": {"main": {"content": wt}}}]}
        if i >= start and intros < 1:
            p["extract"], intros = intro, intros + 1
        pages.append(p)
    later = [i for i, t in enumerate(ts) if t in WIKI and i >= start][1:]
    return {"query": {"pages": pages}, **({"continue": {"excontinue": str(later[0]), "continue": "||"}} if later else {})}


def wikidata(q):
    """The fake Wikidata API: haswbstatement searches by P230 and P238 (and by an item, as P749), and wbgetentities
    by ids or by English page titles."""
    if (q.get("action") or [""])[0] == "query":
        m = re.match(r"haswbstatement:(P\d+)=(\w+)$", (q.get("srsearch") or [""])[0])
        WM_ASKED["find:" + (m.group(2) if m else "")] += 1
        val = lambda s: s["mainsnak"]["datavalue"]["value"]       # noqa: E731
        hits = [k for k, (_, _, c) in WIKIDATA.items() if m and any(val(s) == m.group(2) or isinstance(val(s), dict) and val(s).get("id") == m.group(2)
                                                                   for s in c.get(m.group(1), []))]
        return {"query": {"search": [{"title": k} for k in hits]}}
    ents = {}
    if q.get("titles"):                  # (several at once in relay 78's refresh, as Wikidata takes them: not normalized)
        ts, ids = q["titles"][0].split("|"), []
        for n, t in enumerate(ts):
            hit = next((k for k, (_, page, _) in WIKIDATA.items() if page and (page == t or len(ts) == 1 and page.casefold() == t.casefold())), None)
            if hit:
                ids.append(hit)
            else:
                ents[str(-1 - n)] = {"site": "enwiki", "title": t, "missing": ""}
        q = {"ids": ["|".join(ids)], "props": q.get("props")}
    ids = [k for k in (q.get("ids") or [""])[0].split("|") if k]
    if len(ids) > 1:
        WM_ASKED["batch:wd"] += 1
        if q.get("maxlag") and not WM_ASKED["lagged"]:     # the refresh's first: Wikidata is lagging (it waits as asked, tries again)
            WM_ASKED["lagged"] += 1
            return "maxlag"
    props = (q.get("props") or ["claims|sitelinks|labels"])[0].split("|")
    for k in ids:
        if k in WIKIDATA:
            label, page, claims = WIKIDATA[k]
            WM_ASKED[f"props:{k}:" + "|".join(sorted(props))] += 1
            ents[k] = {"id": k, "labels": {"en": {"value": label}}, **({"claims": claims} if "claims" in props else {}),
                       **({"sitelinks": {"enwiki": {"title": page}} if page else {}} if "sitelinks" in props else {})}
        else:
            ents[k] = {"id": k, "missing": ""}
    return {"entities": ents}


def sparql(q):
    """The fake Wikidata query service (relay 78's refresh): the items with an ICAO code (and whether they stopped
    flying), with an IATA code, and the airlines under a company."""
    text, rows = (q.get("query") or [""])[0], []
    WM_ASKED["sparql"] += 1
    val = lambda s: s["mainsnak"]["datavalue"]["value"]       # noqa: E731
    ent = lambda k: {"type": "uri", "value": "http://www.wikidata.org/entity/" + k}   # noqa: E731
    for k, (_, _, c) in WIKIDATA.items():
        if "P230/ps:P230" in text:
            rows += [{"i": ent(k), "c": {"value": val(s)}, "gone": {"value": "true" if "P576" in c else "false"}} for s in c.get("P230", [])]
        elif "P238/ps:P238" in text:
            rows += [{"i": ent(k), "c": {"value": val(s)}} for s in c.get("P238", [])]
        elif "P749/ps:P749" in text and "P230" in c:
            rows += [{"i": ent(k), "p": ent(val(s)["id"])} for s in c.get("P749", [])]
    return {"head": {"vars": []}, "results": {"bindings": rows}}


def commons(q):
    """The fake Commons API (relay 78's refresh): each photo's own address at the asked width (imageinfo)."""
    WM_ASKED["commons"] += 1
    w = (q.get("iiurlwidth") or ["0"])[0]
    return {"query": {"pages": [{"title": t, "imageinfo": [{"url": f"http://127.0.0.1:{PORT}/commons/{urllib.parse.quote(t[5:])}",
                                                             "thumburl": f"http://127.0.0.1:{PORT}/commons/{w}px-{urllib.parse.quote(t[5:])}"}]}
                                for t in (q.get("titles") or [""])[0].split("|")]}}


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
# Relay 106: a few of Virtual Radar Server's routes, for the flights ROUTES lacks (EIN6AB flies north past Vienna), and the
# airports the fake flights name, as OurAirports lists them.
VRS_HEAD = "\ufeffCallsign,Code,Number,AirlineCode,AirportCodes\r\n"
VRS_ROUTES = {"EIN-all.csv": VRS_HEAD + "EIN6AB,EIN,6AB,EIN,LIRF-EPWA\r\nEIN2AB,EIN,2AB,EIN,EIDW-EGLL\r\n"}
AIRPORTS_CSV = "ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,municipality,scheduled_service,icao_code,iata_code,gps_code\r\n" + "".join(
    f"{ic},large_airport,{c} Airport,{la},{lo},500,{ct},{cc},{c},yes,{ic},{ia},{ic}\r\n" for ia, ic, c, la, lo, ct, cc in [
        ("VIE", "LOWW", "Vienna", 48.1103, 16.5697, "EU", "AT"), ("FRA", "EDDF", "Frankfurt am Main", 50.0333, 8.5706, "EU", "DE"),
        ("DXB", "OMDB", "Dubai", 25.2528, 55.3644, "AS", "AE"), ("STN", "EGSS", "London", 51.885, 0.235, "EU", "GB"),
        ("TLV", "LLBG", "Tel Aviv", 32.0114, 34.8867, "AS", "IL"), ("ATH", "LGAV", "Athens", 37.9364, 23.9445, "EU", "GR"),
        ("PMI", "LEPA", "Palma", 39.5517, 2.7388, "EU", "ES"), ("ZRH", "LSZH", "Zurich", 47.4647, 8.5492, "EU", "CH"),
        ("FCO", "LIRF", "Rome", 41.8003, 12.2389, "EU", "IT"), ("WAW", "EPWA", "Warsaw", 52.1657, 20.9671, "EU", "PL"),
        ("DUB", "EIDW", "Dublin", 53.4213, -6.2701, "EU", "IE"), ("LHR", "EGLL", "London", 51.47, -0.4543, "EU", "GB"),
        ("NCL", "EGNT", "Newcastle", 55.0375, -1.6917, "EU", "GB")])
AIRLINES_CSV = "\ufeffCode,Name,ICAO,IATA,PositioningFlightPattern,CharterFlightPattern\r\n" + "".join(
    f"{c},{n},{c},{i},,\r\n" for c, n, i in [("AUA", "Austrian Airlines", "OS"), ("EIN", "Aer Lingus", "EI"),
                                             ("RYR", "Ryanair", "FR"), ("TST", "Testair", "TS"), ("LDM", "Lauda Europe", "OE"),
                                             ("WZZ", "Wizz Air", "W6"), ("WMT", "Wizz Air Malta", "W4")]) + "".join(
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
            if cs.startswith("LTE"):       # relay 107: the route back-fill (run_test_relay.py --late-routes): the window is logged,
                print("late-route", cs, q["flight_datetime_from"][0], q["flight_datetime_to"][0], flush=True)  # the odd number's found, then hex, then none
                n = int(cs[3:]) % 3
                data = [] if n == 2 else [{"flight": "LT" + cs[3:], "callsign": cs, "orig_iata": "FRA", "orig_icao": "EDDF", "dest_iata": "VIE", "dest_icao": "LOWW",
                                           "hex": "ffffff" if n == 1 else cs[:3].lower() + "000", "flight_ended": "true"}]
                return self.send(200, "application/json", json.dumps({"data": data}).encode())
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
        if path == "/airports.csv":
            return self.send(200, "text/csv", AIRPORTS_CSV.encode("utf-8"))
        if path.startswith("/vrs-routes/"):     # relay 106: one airline's routes; any other file isn't there
            body = VRS_ROUTES.get(path.rsplit("/", 1)[1])
            if os.environ.get("VRS_DOWN"):
                return self.send(503, "text/plain", b"down")
            if body is None:
                return self.send(404, "text/plain", b"404: Not Found")
            return self.send(200, "text/plain", body.encode("utf-8"))
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
            ps = PS_PHOTOS.get(k) or []
            img = lambda p, w, h, s: {"src": f"http://127.0.0.1:{PORT}/psimg/{p[0]}_{s}.svg", "size": {"width": w, "height": h}}   # noqa: E731
            photos = [{"id": p[0], "thumbnail": img(p, 200, 133, "t"), "thumbnail_large": img(p, 420, 280, "280"),
                       "link": f"https://www.planespotters.net/photo/{p[0]}/{p[1]}?utm_source=api", "photographer": "Test Photographer"}
                      for p in (ps if isinstance(ps, list) else [ps])]
            return self.send(200, "application/json", json.dumps({"photos": photos}).encode())
        if path == "/ps/asked":
            return self.send(200, "application/json", json.dumps(PS_ASKED).encode())
        if path in ("/wiki/w/api.php", "/wikidata/w/api.php"):      # relay 74: the cards' facts
            if not re.fullmatch(r"\S+/\S+ \(\+https?://\S+\)", self.headers.get("User-Agent") or ""):   # Wikimedia wants a name and a contact
                return self.send(403, "text/plain", b"Please set a user-agent and respect our robot policy")
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            j = (wikipedia if path.startswith("/wiki/") else wikidata)(q)
            if j == "maxlag":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "1")
                self.end_headers()
                return self.wfile.write(json.dumps({"error": {"code": "maxlag", "info": "Waiting for a database server: 6 seconds lagged."}}).encode())
            return self.send(200, "application/json", json.dumps(j).encode())
        if path in ("/sparql", "/commons-api/w/api.php"):   # relay 78: the facts database's monthly refresh
            if not re.fullmatch(r"\S+/\S+ \(\+https?://\S+\)", self.headers.get("User-Agent") or ""):
                return self.send(403, "text/plain", b"Please set a user-agent and respect our robot policy")
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            return self.send(200, "application/json", json.dumps((sparql if path == "/sparql" else commons)(q)).encode())
        if path == "/wm/asked":
            return self.send(200, "application/json", json.dumps(WM_ASKED).encode())
        if path.startswith("/commons/"):   # a Commons photo (an airline's plane, an airport): the drawn stand-in
            return self.send(200, "image/svg+xml", SVG_PHOTO.encode())
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
        if os.environ.get("RING"):    # 1.98: the passive circle (15 km) and the scan's (10 km; 15 since 1.126.1)
            ac.append(plane("4400aa", "AUA171", "A20N", 6.0, -22.0, 0, 900, 4000, 0, r="OE-LXA"))   # 15 km at ~33 s, 10 km at ~56 s
            ac.append(plane("4400bb", "AUA173", "E195", 12.0, -26.0, 0, 900, 4500, 0, r="OE-LWB"))  # 15 km at ~68 s, never within 12
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
