"""Build app/index.html: the phone layout (head.html, main.js) around the board's own flap engine and data code,
copied from the test-api board (test-api/index.html) by the marker strings below. The app follows the test-api board,
so new features reach the phone together with that board, before the main board.

    py tools/app/build.py                      # test-api/index.html -> app/index.html
    py tools/app/build.py BOARD.html OUT.html

Don't edit app/index.html by hand: change head.html or main.js here (or the board), then build again. If a marker
string below is no longer in the board, the build stops and says which one; update the marker.
"""
import sys
from pathlib import Path

SP = Path(__file__).parent
REPO = SP.parent.parent
board = Path(sys.argv[1] if len(sys.argv) > 1 else REPO / "test-api" / "index.html").read_text(encoding="utf-8")
out = Path(sys.argv[2] if len(sys.argv) > 2 else REPO / "app" / "index.html")


def ex(start, end):
    if start not in board:
        raise SystemExit(f"Marker not found in the board: {start!r}")
    i = board.index(start)
    if end not in board[i + len(start):]:
        raise SystemExit(f"End marker not found after {start!r}: {end!r}")
    j = board.index(end, i + len(start))
    return board[i:j].rstrip() + "\n"


def patched(text, *pairs):
    for a, b in pairs:
        assert text.count(a) == 1, (text.count(a), a[:80])
        text = text.replace(a, b)
    return text


E = {
    "E1": ex("const REDUCED = ", "/* ---------- settings ---------- */"),
    "E2": ex("/* ---------- text helpers ---------- */", "/* ---------- canvas, scaling ---------- */"),
    "E3": ex("/* ---------- tiles: each flap face pre-rendered once ---------- */", "/* ---------- drawing a flap, mid-flip or at rest ---------- */"),
    "E4": ex("// Paints a flap onto the board, or onto the page that is falling away", "function redrawAll(){"),
    "E5": patched(ex("let running = false, lastFrame = 0;", "/* ---------- printed parts of the board ---------- */"),
                  ("if (REDUCED || snapping) {", "if (REDUCED || snapping || c.f.panel.off) {")),
    "E6": ex("function drawPlane(g, cx, cy, size, color){", "const metalCache = "),
    "E8": ex("const shadowSprites = new Map();", "function slots(g){"),
    "E9": ex("function screw(g, x, y, r){", "/* ---------- the aircraft photo"),
    "E10": ex("/* ---------- sound: synthesised flap clatter", "/* ---------- board styles and night mode ---------- */"),
    "E11": ex("/* ---------- reference tables ---------- */", "/* ---------- network ---------- */"),
    "E12": patched(ex("/* ---------- network ---------- */", "/* ---------- demo traffic (clearly sample data) ---------- */"),
                   ("function infoChanged(info){\n  if (feat && feat.info === info) { renderFeatured(); if (isAc(page)) renderAircraft(); }\n}",
                    "function infoChanged(info){\n  if (feat && feat.info === info) { renderFeatured(); renderAircraftInfo(); }\n}")),
    "E13": ex("/* ---------- demo traffic (clearly sample data) ---------- */", "/* ---------- spotted log ---------- */"),
    "E14": ex("const DAY_START_H = 3;", "let spotted = relayV5()"),
    "E15": ex("/* With relay version 5 the relay records every sighting; the board just mirrors its list. */", "async function syncSightings(){"),
    "E16": ex("/* ---------- special aircraft and favourites ---------- */", "/* ---------- tracking ---------- */"),
    "E17": ex("/* ---------- tracking ---------- */", "function setFeat(o, mode, alert = false){"),
    "E18": ex("/* Airtime. Planes that hang around", "const recent = new Map();"),
    "E19": patched(ex("const recent = new Map();", "/* ---------- flight times and delays"),
                   ("  if (!relayV5()) logPlanes(ok, R);    // with relay version 5 the relay keeps the list\n", ""),
                   ("  if (view === \"radar\") renderRadarList();", "  if (tab === \"radar\") renderRadarList();"),
                   ("  renderFeatured();\n  if (feat) { lookupDetails(feat.hex); preloadPhoto(); }\n  noteFeatured();\n  if (isAc(page)) renderPage();\n}",
                    "  renderFeatured();\n  if (feat) lookupDetails(feat.hex);\n  renderAircraftInfo();\n}")),
    "E20": ex("/* ---------- flight times and delays", "/* Recent flights: the planes that were on the top half"),
    "E21": patched(ex("const acDetails = new Map();", "// Load the photo of the plane on the board ahead of time"),
                   ("    if (feat && feat.hex === hex) { preloadPhoto(); if (isAc(page)) renderAircraft(); }",
                    "    if (feat && feat.hex === hex) renderAircraftInfo();")),
    "E22": ex("function legendGroups(){", "function legendChip("),
    "E23": ex("const fmtDay = ts =>", "async function fetchLogbook(){"),
    "E24": ex("function logbookSummary(){", "function renderLogbookBoard(){"),
    "E25": ex("const radar = {raf: 0", "const RADAR_GEO") + ex("function rgba(hex, a)", "function radarBox()") + ex("function altShort(ft){", "function drawRadar(t){"),
    "E26": ex("const lampOf = r =>", "// Spotted today is engraved text, like the legend"),
    "E27": ex("function spottedSummary(){", "const lampOf = r =>"),
    "E28": ex("const LB_CATS = [", "vdef(\"logbook\", \"lvSight\""),
    "E29": ex("function rotaryAngles(n)", "function plateHtml(p){") + ex("function wheelStep(it, part, d){", "function cockpitDirty(){") + ex("/* ---------- Settings: the sounds of the controls", "function applySettings(n){"),
    "E33": ex("/* ---------- languages ----------", "/* ---------- airport mode ----------"),
    "E32": ex("/* ---------- airport mode ----------", "/* ---------- versions and patch notes ----------"),
    "E31": ex("/* ---------- versions and patch notes", "/* ---------- settings: a cockpit panel ----------"),
    "E30": patched(ex("/* ---------- main loop ---------- */", "async function start(){"),
                   ("timer = setTimeout(poll, S.demo ? 2000 :", "timer = setTimeout(poll, document.hidden ? 60000 : S.demo ? 2000 :")),
}
css = ex("/* push buttons: plain ivory caps", "#viewTools{z-index:2}") + ex("/* Settings: a cockpit panel.", "</style>")
head = (SP / "head.html").read_text(encoding="utf-8")
head = head.replace("/*CAPS_AND_COCKPIT*/\n", "").replace("<style>\n", "<style>\n" + css.replace("body.lite", "body.no-lite"), 1)
js = (SP / "main.js").read_text(encoding="utf-8")
for k, v in E.items():
    marker = f"//@{k}\n"
    assert js.count(marker) == 1, k
    js = js.replace(marker, v)
assert "//@E" not in js
out.write_text(head + js, encoding="utf-8", newline="\n")
print("wrote", out, len(head + js), "bytes")
