"""The aircraft models' Wikipedia pages by type code (1.93.1.1, to-do #112): MODEL_PAGES in test/index.html, the first
place the model pictures look (modelTitles). Made from Wikipedia's "List of aircraft type designators" (the page each
code links to) with the fixes and the more common light aircraft, helicopters and military types added below (codes as
in ICAO Doc 8643), and checked against Wikipedia: every title must lead to a page about an aircraft (not missing, not a
disambiguation, a company or a list). A code whose name in the board's TYPES already leads to such a page is left out:
that name is tried right after. A kind of aircraft (BALL, GLID ...) is marked with "*" and comes last, after the names.

    py tools/model_pages.py           check, and write MODEL_PAGES into test/index.html (py tools/app/build.py after)
    py tools/model_pages.py --check   only check and show what would change

Needs the network (one request for the list, one for every 20 titles); run it by hand now and then.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOARD = REPO / "test" / "index.html"
API = "https://en.wikipedia.org/w/api.php?format=json&formatversion=2&"
UA = "Fallblatt-model-pages/1.0 (https://github.com/Belstria/overhead-board)"   # Wikimedia asks for a name and a contact

# The list's own mistakes: PAY2, the Cheyenne II, is a PA-31T; C130 is mostly the military Hercules; AC90 links the
# company. H25B flies as the Hawker 800 series (750 to 900XP); the BAe 125's page shows a 1960s RAF trainer.
FIX = {"PAY2": "Piper PA-31T Cheyenne", "C130": "Lockheed C-130 Hercules", "AC90": "Aero Commander 500 family", "H25B": "Hawker 800"}
ADD = {
    "AC68": "Aero Commander 500 family", "AC6L": "Aero Commander 500 family", "AC95": "Aero Commander 500 family",
    "C150": "Cessna 150", "C152": "Cessna 152", "C170": "Cessna 170", "C177": "Cessna 177 Cardinal", "C77R": "Cessna 177 Cardinal",
    "C180": "Cessna 180 Skywagon", "C185": "Cessna 185 Skywagon", "C206": "Cessna 206", "C207": "Cessna 206", "C210": "Cessna 210 Centurion",
    "P210": "Cessna 210 Centurion", "T210": "Cessna 210 Centurion", "C303": "Cessna T303 Crusader", "C310": "Cessna 310",
    "C337": "Cessna Skymaster", "C340": "Cessna 340", "C402": "Cessna 402", "C404": "Cessna 404 Titan", "C414": "Cessna 414",
    "C421": "Cessna 421 Golden Eagle", "C441": "Cessna 441 Conquest II", "C25M": "Cessna CitationJet/M2", "C501": "Cessna Citation I",
    "C551": "Cessna Citation II", "C55B": "Cessna Citation II",
    "P28B": "Piper PA-28 Cherokee", "P28R": "Piper PA-28 Cherokee", "P28T": "Piper PA-28 Cherokee", "PA18": "Piper PA-18 Super Cub",
    "PA22": "Piper PA-20 Pacer", "PA24": "Piper PA-24 Comanche", "PA30": "Piper PA-30 Twin Comanche", "PA31": "Piper PA-31 Navajo",
    "PA32": "Piper PA-32 Cherokee Six", "P32R": "Piper PA-32R", "P32T": "Piper PA-32R", "PA34": "Piper PA-34 Seneca",
    "PA38": "Piper PA-38 Tomahawk", "PA44": "Piper PA-44 Seminole", "PA46": "Piper PA-46", "P46T": "Piper PA-46",
    "PAY1": "Piper PA-31T Cheyenne", "PAY3": "Piper PA-42 Cheyenne", "PAY4": "Piper PA-42 Cheyenne", "J3": "Piper J-3 Cub",
    "AEST": "Piper Aerostar",
    "BE33": "Beechcraft Bonanza", "BE35": "Beechcraft Bonanza", "BE36": "Beechcraft Bonanza", "BE55": "Beechcraft Baron",
    "BE58": "Beechcraft Baron", "BE60": "Beechcraft Duke", "BE9L": "Beechcraft King Air", "BE9T": "Beechcraft King Air",
    "BE10": "Beechcraft King Air", "B350": "Beechcraft Super King Air", "BE30": "Beechcraft Super King Air", "BE18": "Beechcraft Model 18",
    "PRM1": "Beechcraft Premier I", "M20P": "Mooney M20", "M20T": "Mooney M20", "SR20": "Cirrus SR20", "SR22": "Cirrus SR22",
    "S22T": "Cirrus SR22", "SF50": "Cirrus Vision SF50", "DV20": "Diamond DA20 Katana", "DA50": "Diamond DA50",
    "DIMO": "Diamond HK36 Super Dimona", "G115": "Grob G 115", "G120": "Grob G 120", "G109": "Grob G 109",
    "TB20": "SOCATA TB family", "TB21": "SOCATA TB family", "TOBA": "SOCATA TB family", "TBM7": "SOCATA TBM", "TBM8": "SOCATA TBM",
    "TBM9": "SOCATA TBM", "K100": "Daher Kodiak", "K900": "Daher Kodiak", "DR40": "Robin DR400", "E300": "Extra EA-300",
    "CP10": "Mudry CAP 10", "EVSS": "Evektor SportStar", "A210": "Aquila A 210", "HUSK": "Aviat Husky", "P68": "Partenavia P.68",
    "PC6T": "Pilatus PC-6 Porter", "PC7": "Pilatus PC-7", "PC9": "Pilatus PC-9", "PC21": "Pilatus PC-21",
    "BN2P": "Britten-Norman BN-2 Islander",
    "LJ31": "Learjet 31", "LJ40": "Learjet 40", "LJ55": "Learjet 55", "LJ70": "Learjet 70/75", "LJ75": "Learjet 70/75",
    "HA4T": "Hawker 4000", "FA10": "Dassault Falcon 10", "FA20": "Dassault Falcon 20", "FA8X": "Dassault Falcon 7X",
    "GA5C": "Gulfstream G400/G500/G600", "GA6C": "Gulfstream G400/G500/G600", "GLF3": "Gulfstream III",
    "B412": "Bell 412", "B429": "Bell 429 GlobalRanger", "B505": "Bell 505 Jet Ranger X", "B212": "Bell 212", "UH1": "Bell UH-1 Iroquois",
    "R22": "Robinson R22", "EC20": "Eurocopter EC120 Colibri", "AS55": "Eurocopter AS355 Écureuil 2", "AS65": "Eurocopter AS365 Dauphin",
    "AS32": "Eurocopter AS332 Super Puma", "AS3B": "Eurocopter AS332 Super Puma", "EC25": "Eurocopter EC725", "TIGR": "Eurocopter Tiger",
    "EC55": "Eurocopter EC155", "EC75": "Airbus Helicopters H175", "H160": "Airbus Helicopters H160", "B105": "MBB Bo 105", "BK17": "MBB/Kawasaki BK 117",
    "ALO3": "Aérospatiale Alouette III", "ALO2": "Aérospatiale Alouette II", "GAZL": "Aérospatiale Gazelle",
    "EH10": "AgustaWestland AW101", "A109": "AgustaWestland AW109", "A119": "AgustaWestland AW119 Koala", "A189": "AgustaWestland AW189",
    "S92": "Sikorsky S-92", "H60": "Sikorsky UH-60 Black Hawk", "H500": "MD Helicopters MD 500", "EXPL": "MD Helicopters MD Explorer",
    "G2CA": "Guimbal Cabri G2", "H269": "Schweizer S300", "EN28": "Enstrom F-28", "H47": "Boeing CH-47 Chinook",
    "H64": "Boeing AH-64 Apache", "MI8": "Mil Mi-8", "MI24": "Mil Mi-24", "KA27": "Kamov Ka-27", "NH90": "NHIndustries NH90",
    "RFAL": "Dassault Rafale", "TOR": "Panavia Tornado", "E3TF": "Boeing E-3 Sentry", "R135": "Boeing RC-135", "SB05": "Saab 105",
    "M346": "Leonardo M-346", "L39": "Aero L-39 Albatros", "AN2": "Antonov An-2", "DC3": "Douglas DC-3", "JU52": "Junkers Ju 52",
}
ANY = {"BALL": "Hot air balloon", "GLID": "Glider (sailplane)", "GYRO": "Autogyro", "SHIP": "Airship", "ULAC": "Ultralight aviation"}


def get(params):
    url = API + urllib.parse.urlencode(params)
    for _ in range(6):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(int(e.headers.get("retry-after") or 10) + 1)    # Wikimedia's limit: wait as long as it says
    raise SystemExit("Wikipedia keeps saying: too many requests")


def designators():
    """code -> the page its row links to (the first link, without a #section)."""
    wt = get({"action": "parse", "prop": "wikitext", "page": "List of aircraft type designators"})["parse"]["wikitext"]
    out = {}
    for line in wt.splitlines():
        m = re.match(r"^\|\s*([A-Z0-9]{2,4})\s*\|\|[^|]*\|\|\s*(.*)$", line)
        link = m and re.search(r"\[\[([^\]|#]+)", m.group(2))
        if link and m.group(1) not in out:
            out[m.group(1)] = link.group(1).strip()
    return out


def board_bits():
    html = BOARD.read_text(encoding="utf-8")
    types = dict(re.findall(r'(\w+):"([^"]*)"', re.search(r"const TYPES = \{(.*?)\};", html, re.S).group(1)))
    like, nope = (re.search(rf"const {n} = /(.*)/i;", html).group(1) for n in ("MODEL_LIKE", "MODEL_NOT"))
    return html, types, re.compile(like, re.I), re.compile(nope, re.I)


def pages(titles, like, nope):
    """title -> (the page it leads to, or None when that isn't a page about an aircraft; why not)."""
    out = {}
    for i in range(0, len(titles), 20):               # Wikipedia gives the first words of 20 pages at most
        chunk = titles[i:i + 20]
        q = get({"action": "query", "redirects": 1, "prop": "pageimages|description|pageprops|extracts", "piprop": "thumbnail",
                 "pithumbsize": 500, "ppprop": "disambiguation", "exintro": 1, "explaintext": 1, "exchars": 200, "exlimit": 20,
                 "titles": "|".join(chunk)})["query"]
        to = {r["from"]: r["to"] for r in q.get("normalized", []) + q.get("redirects", [])}
        got = {p["title"]: p for p in q.get("pages", [])}
        for t in chunk:
            k = t
            for _ in range(3):
                k = to.get(k, k)
            p = got.get(k, {})
            desc, text = p.get("description", ""), p.get("extract", "")
            why = ("no such page" if not p or p.get("missing") or p.get("invalid") else "a disambiguation" if "disambiguation" in p.get("pageprops", {})
                   else f"not an aircraft: {desc!r}" if nope.search(re.sub(r"\([^)]*\)", "", desc)) or not like.search(desc + " " + text) else "")
            out[t] = (None, why) if why else (k, "" if p.get("thumbnail") else "no picture")
        time.sleep(0.5)
    return out


def main():
    check = "--check" in sys.argv
    html, types, like, nope = board_bits()
    want = {**designators(), **FIX, **ADD}
    found = pages(sorted(set(want.values()) | set(ANY.values()) | set(types.values())), like, nope)
    bad = [f"{c} {t}: {found[t][1]}" for c, t in {**want, **ANY}.items() if not found[t][0]]
    if bad:
        raise SystemExit("These pages don't fit (fix FIX/ADD):\n  " + "\n  ".join(sorted(bad)))
    rows, kept = {}, 0
    for c, t in sorted(want.items()):
        page, note = found[t]
        mine = types.get(c, c).upper() != c and found[types[c]][0]
        if mine:                                   # the board's name for it leads to a page: that one is tried right after
                                                   # (not one that is the code itself, "NH90": the code is never a name)
            if mine != page:
                print(f"  {c}: TYPES {types[c]!r} leads to {mine!r}, the list to {page!r} (TYPES is used)")
            continue
        rows[c] = page
        kept += 1
        if note:
            print(f"  {c}: {page} has {note} (Wikidata's may stand in)")
    for c, t in ANY.items():
        rows[c] = "*" + found[t][0]
    for c, n in sorted(types.items()):            # a board type that would have no page by its code alone
        if c not in rows and not (n.upper() != c and found[n][0]):
            print(f"  {c}: TYPES {n!r} leads to no page about an aircraft and the table has none: add one to ADD")
    line = 'const MODEL_PAGES = Object.fromEntries("' + "|".join(f"{c}={t}" for c, t in sorted(rows.items())) + '".split("|").map(p => p.split("=")));'
    new = re.sub(r"^const MODEL_PAGES = .*$", lambda m: line, html, count=1, flags=re.M)
    print(f"{kept} codes with a page of their own, {len(ANY)} kinds, {len(want) - kept} left to TYPES; the line is {len(line)} characters")
    if new == html:
        print("MODEL_PAGES is up to date")
    elif check:
        raise SystemExit("MODEL_PAGES would change (run py tools/model_pages.py)")
    else:
        BOARD.write_text(new, encoding="utf-8", newline="\n")
        print("written into test/index.html; rebuild the app: py tools/app/build.py")


if __name__ == "__main__":
    main()
