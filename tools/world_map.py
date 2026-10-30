"""1.107 (to-do #150): make test/world.js, the passport's map, from Natural Earth's admin-0 countries at 1:110m
(public domain, naturalearthdata.com).

    py tools/world_map.py [ne_110m_admin_0_countries.geojson ne_50m_admin_0_countries.geojson]

Without files it downloads Natural Earth's GeoJSON copies. Packed as the mockups' round 2 did: each country's outer rings
only, in 0.1° steps (whole numbers, lon and lat × 10), a point repeated after rounding left out. Each country also gets
its passport region and the point its name goes at (Natural Earth's label point):

    window.WORLD = {CC: [region, label lon × 10, label lat × 10, [[x, y, x, y, ...], ...]], ...}

1.113 (to-do #179): 13 regions, the UN's subregions joined: WE Western, NE Northern, SE Southern and EE Eastern Europe,
ME the Middle East, NAF North Africa, SSA Sub-Saharan Africa, CSA Central & South Asia, EA East Asia, SEA Southeast Asia,
NCA North & Central America (the Caribbean too), SAM South America, OC Oceania. Cyprus counts as Southern Europe and the
Caucasus as Eastern Europe, the rest of Western Asia and Iran as the Middle East. The small countries 1:110m lacks
(Malta, Singapore, ...) come from 1:50m as a label point without rings (the map draws a dot). Places without an airport
(the French Southern Lands, Heard Island, South Georgia, the Pitcairn Islands, the Chagos) get region "" (land, never a
goal). Antarctica is left out; Northern Cyprus and Somaliland (no code of their own) join Cyprus and Somalia, as their
airports do in the airport list.
"""
import gzip
import json
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "test" / "world.js"
URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_{}_admin_0_countries.geojson"
REGION = {"Western Europe": "WE", "Northern Europe": "NE", "Southern Europe": "SE", "Eastern Europe": "EE", "Western Asia": "ME",
          "Northern Africa": "NAF", "Eastern Africa": "SSA", "Middle Africa": "SSA", "Southern Africa": "SSA", "Western Africa": "SSA",
          "Central Asia": "CSA", "Southern Asia": "CSA", "Eastern Asia": "EA", "South-Eastern Asia": "SEA",
          "Northern America": "NCA", "Central America": "NCA", "Caribbean": "NCA", "South America": "SAM",
          "Australia and New Zealand": "OC", "Melanesia": "OC", "Micronesia": "OC", "Polynesia": "OC"}
OWN = {"CY": "SE", "GE": "EE", "AM": "EE", "AZ": "EE", "IR": "ME", "TF": "", "HM": "", "GS": "", "PN": "", "IO": ""}
JOIN = {"CYN": "CY", "SOL": "SO"}       # ADM0_A3 of the two without a code


def load(i, scale):
    if len(sys.argv) > i:
        return json.loads(Path(sys.argv[i]).read_text(encoding="utf-8"))
    with urllib.request.urlopen(urllib.request.Request(URL.format(scale), headers={"User-Agent": "fallblatt-world-map"}), timeout=60) as r:
        return json.loads(r.read())


def code(p, must=True):
    k = JOIN.get(p["ADM0_A3"]) or p.get("ISO_A2_EH") or p["ISO_A2"]
    if k in ("-99", None) and must:
        raise SystemExit(f"no code for {p['ADMIN']}")
    return k if k not in ("-99", None) else None


def region(k, p):
    return OWN[k] if k in OWN else REGION[p["SUBREGION"]]


def main():
    d = load(1, "110m")
    W = {}
    for f in sorted(d["features"], key=lambda f: f["properties"]["ADM0_A3"]):
        p = f["properties"]
        if p["ADM0_A3"] == "ATA":
            continue
        k = code(p)
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = []
        for poly in polys:
            out, last = [], None
            for x, y in poly[0]:                # the outer ring only
                q = (round(x * 10), round(y * 10))
                if q != last:
                    out += q
                    last = q
            if len(out) >= 6:
                rings.append(out)
        if k in W:
            W[k][3].extend(rings)
            continue
        W[k] = [region(k, p), round(p["LABEL_X"] * 10), round(p["LABEL_Y"] * 10), rings]
    for f in sorted(load(2, "50m")["features"], key=lambda f: f["properties"]["ADM0_A3"]):
        p = f["properties"]
        k = code(p, False)                      # (the Siachen Glacier and the like have none: left out)
        if k and p["ADM0_A3"] != "ATA" and k not in W:          # 1.113: too small for 1:110m, a dot
            W[k] = [region(k, p), round(p["LABEL_X"] * 10), round(p["LABEL_Y"] * 10), []]
    s = json.dumps(W, separators=(",", ":"))
    OUT.write_text("// The passport's map (1.107; 13 regions and the small countries 1.113): Natural Earth admin-0 countries, 1:110m (public domain), packed by tools/world_map.py\n"
                   "window.WORLD=" + s + ";\n", encoding="utf-8", newline="\n")
    print(len(W), "countries,", len(s), "bytes,", len(gzip.compress(s.encode())), "gzipped")


if __name__ == "__main__":
    main()
