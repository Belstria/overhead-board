"""1.114 (to-do #182): the member cards' airline names and home bases, from Wikidata (CC0), for every airline in the board's AIRLINES table.

    py tools/airline_home.py [--dry]

One SPARQL query by ICAO code (P230): the airline's English name, its country (P17 → ISO 3166 code, P297) and its hub
(P113 → the hub's IATA code, P238). Airlines that ended (P576) are left out, as codes get reused. With more than one hub,
the one serving the airline's headquarters city (P159 / P931) wins, then a hub ranked preferred, then the first by code;
HUB below overrides the rest (a few airlines whose Wikidata hubs are many or none). The result replaces the block between
the markers in test/index.html:

    const AIRLINE_HOME = {ICAO: [full name, country ISO, hub IATA], ...};   // "" where Wikidata has none

The app names the country in the reader's language (Intl.DisplayNames) and shows the hub as its IATA code.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BOARD = Path(__file__).resolve().parent.parent / "test" / "index.html"
URL = "https://query.wikidata.org/sparql"
UA = "Fallblatt-airline-home/1.0 (https://github.com/Belstria/overhead-board)"
START, END = "// airline-home:start", "// airline-home:end"
# ICAO: hub IATA, where Wikidata lists several and the rule above picks a secondary one, or lists none
HUB = {"AAL": "DFW", "ACA": "YYZ", "BAW": "LHR", "CES": "PVG", "RYR": "DUB", "SAS": "CPH", "SWR": "ZRH", "SXS": "AYT",
       "NOZ": "OSL", "FHY": "AYT", "HFY": "LIS", "KAL": "ICN", "EJU": "VIE", "EXS": "MAN"}
# ICAO: name, where Wikidata's English label is missing or a company's legal name
NAME = {"KAL": "Korean Air", "SBI": "S7 Airlines", "ELY": "El Al", "LDA": "Lauda Europe", "BTI": "airBaltic", "CFG": "Condor"}
CC = {"KLM": "NL", "CND": "NL", "TFL": "NL"}  # ICAO: country, where Wikidata has none

Q = """SELECT ?icao ?item ?label ?cc ?hub ?rank ?serves ?hq WHERE {
  VALUES ?icao { %s }
  ?item wdt:P230 ?icao .
  FILTER NOT EXISTS { ?item wdt:P576 ?end }
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "en") }
  OPTIONAL { ?item wdt:P17 ?c . ?c wdt:P297 ?cc }
  OPTIONAL { ?item wdt:P159 ?hq }
  OPTIONAL { ?item p:P113 ?st . ?st ps:P113 ?h ; wikibase:rank ?rank . ?h wdt:P238 ?hub . OPTIONAL { ?h wdt:P931 ?serves } }
}"""


def codes():
    text = BOARD.read_text(encoding="utf-8")
    body = text[text.index("const AIRLINES = {"):]
    body = body[:body.index("\n};")]
    return sorted(set(re.findall(r"\b([A-Z0-9]{3}):\[", body)))


def ask(icaos):
    q = Q % " ".join(f'"{c}"' for c in icaos)
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode({"query": q, "format": "json"}),
                                 headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())["results"]["bindings"]
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(int(e.headers.get("retry-after") or 10))


def pick(rows):
    """The facts of one ICAO code: its name and country, and the hub that fits best."""
    v = lambda r, k: (r.get(k) or {}).get("value", "")
    items = sorted({v(r, "item") for r in rows}, key=lambda i: int(i.rsplit("Q", 1)[1]))   # the oldest item if several
    rows = [r for r in rows if v(r, "item") == items[0]]
    name = next((v(r, "label") for r in rows if v(r, "label")), "")
    cc = next((v(r, "cc") for r in rows if v(r, "cc")), "")
    hqs = {v(r, "hq") for r in rows if v(r, "hq")}
    hubs = sorted({(v(r, "serves") in hqs, v(r, "rank").endswith("PreferredRank"), v(r, "hub")) for r in rows if v(r, "hub")},
                  key=lambda h: (not h[0], not h[1], h[2]))
    return name, cc, hubs[0][2] if hubs else ""


def main():
    icaos = codes()
    rows = ask(icaos)
    by = {}
    for r in rows:
        by.setdefault(r["icao"]["value"], []).append(r)
    facts = {}
    for c in icaos:
        name, cc, hub = pick(by[c]) if c in by else ("", "", "")
        facts[c] = [NAME.get(c, name), CC.get(c, cc), HUB.get(c, hub)]
    lines, row = [], ""
    for c in icaos:
        item = f'{c}:{json.dumps(facts[c], ensure_ascii=False, separators=(",", ":"))},'
        if len(row) + len(item) > 116:
            lines.append(row)
            row = ""
        row += item
    lines.append(row.rstrip(","))
    block = (f"{START} (tools/airline_home.py; Wikidata, CC0)\n"
             f"// The member cards' names and home bases by ICAO code: [full name, country ISO, hub IATA] (1.114, to-do #182)\n"
             "const AIRLINE_HOME = {\n  " + "\n  ".join(lines) + f"\n}};\n{END}")
    missing = [c for c in icaos if not all(facts[c])]
    print(f"{len(icaos)} airlines, {len(icaos) - len(missing)} complete; incomplete: {' '.join(missing) or 'none'}")
    if "--dry" in sys.argv:
        print(block)
        return
    text = BOARD.read_text(encoding="utf-8")
    if START in text:
        a, b = text.index(START), text.index(END) + len(END)
        text = text[:a] + block + text[b:]
    else:                                   # the first time: right after AIRLINES
        at = text.index("\n};", text.index("const AIRLINES = {")) + 3
        text = text[:at] + "\n" + block + text[at:]
    BOARD.write_text(text, encoding="utf-8")
    print("written", BOARD)


if __name__ == "__main__":
    main()
