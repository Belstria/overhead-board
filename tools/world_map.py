"""1.107 (to-do #150): make test/world.js, the passport's map, from Natural Earth's admin-0 countries at 1:110m
(public domain, naturalearthdata.com).

    py tools/world_map.py [ne_110m_admin_0_countries.geojson]

Without a file it downloads Natural Earth's GeoJSON copy. Packed as the mockups' round 2 did: each country's outer rings
only, in 0.1° steps (whole numbers, lon and lat × 10), a point repeated after rounding left out. Each country also gets
its passport region and the point its name goes at (Natural Earth's label point):

    window.WORLD = {CC: [region, label lon × 10, label lat × 10, [[x, y, x, y, ...], ...]], ...}

Regions: E Europe, M Middle East, F Africa, A Asia, N the Americas, O Oceania. The Caucasus and Cyprus count as
Europe, the rest of Western Asia and Iran as the Middle East (as the stamps' shelves have it). Antarctica is left out; Northern
Cyprus and Somaliland (no code of their own) join Cyprus and Somalia, as their airports do in the airport list.
"""
import gzip
import json
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "test" / "world.js"
URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"
REGION = {"Europe": "E", "Africa": "F", "Asia": "A", "Americas": "N", "Oceania": "O", "Seven seas (open ocean)": "F"}
EUROPE_TOO = {"CY", "GE", "AM", "AZ"}
MIDEAST_TOO = {"IR"}
JOIN = {"CYN": "CY", "SOL": "SO"}       # ADM0_A3 of the two without a code


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src:
        d = json.loads(Path(src).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "fallblatt-world-map"}), timeout=60) as r:
            d = json.loads(r.read())
    W = {}
    for f in sorted(d["features"], key=lambda f: f["properties"]["ADM0_A3"]):
        p = f["properties"]
        if p["ADM0_A3"] == "ATA":
            continue
        k = JOIN.get(p["ADM0_A3"]) or p.get("ISO_A2_EH") or p["ISO_A2"]
        if k in ("-99", None):
            raise SystemExit(f"no code for {p['ADMIN']}")
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
        sub = p["SUBREGION"]
        reg = "E" if k in EUROPE_TOO else "M" if sub == "Western Asia" or k in MIDEAST_TOO else REGION[p["REGION_UN"]]
        W[k] = [reg, round(p["LABEL_X"] * 10), round(p["LABEL_Y"] * 10), rings]
    s = json.dumps(W, separators=(",", ":"))
    OUT.write_text("// The passport's map (1.107): Natural Earth admin-0 countries, 1:110m (public domain), packed by tools/world_map.py\n"
                   "window.WORLD=" + s + ";\n", encoding="utf-8", newline="\n")
    print(len(W), "countries,", len(s), "bytes,", len(gzip.compress(s.encode())), "gzipped")


if __name__ == "__main__":
    main()
