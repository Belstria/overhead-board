"""Build app/index.html: the phone layout (head.html, main.js) around the board's own flap engine and data code,
copied from the test board (test/index.html) by the marker strings below. The app follows the test board,
so new features reach the phone together with that board, before the main board.

    py tools/app/build.py                      # test/index.html -> app/index.html
    py tools/app/build.py BOARD.html OUT.html

tools/light/build.py builds the light version (no split flaps) from the same pieces with extract() and assemble().

Don't edit app/index.html by hand: change head.html or main.js here (or the board), then build again. If a marker
string below is no longer in the board, the build stops and says which one; update the marker.

The translations and the sounds aren't copied (1.53.1): the app loads the test board's i18n.js and sounds.js
(../test/, with the versions tools/assets.py stamps into the board first).
"""
import re
import sys
from pathlib import Path

SP = Path(__file__).parent
REPO = SP.parent.parent
sys.path.insert(0, str(REPO / "tools"))
import assets  # noqa: E402  (tools/assets.py)
board = ""


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


def extract(text):
    """The board's code the app copies (E, by marker) and the CSS of its push buttons and Settings plates."""
    global board
    board = text
    E = {
        "E1": ex("const REDUCED = ", "/* ---------- settings ---------- */"),
        "E2": ex("/* ---------- text helpers ---------- */", "/* ---------- canvas, scaling ---------- */"),
        "E3": ex("/* ---------- tiles: each flap face pre-rendered once ---------- */", "/* ---------- drawing a flap, mid-flip or at rest ---------- */"),
        "E4": ex("// Paints a flap onto the board, or onto the page that is falling away", "function redrawAll(){"),
        "E5": patched(ex("let running = false, lastFrame = 0;", "/* ---------- printed parts of the board ---------- */"),
                      ("if (REDUCED || snapping) {", "if (REDUCED || snapping || c.f.panel.off || flapsHeld) {")),
        "E6": ex("function drawPlane(g, cx, cy, size, color){", "const metalCache = "),
        "E8": ex("const shadowSprites = new Map();", "function slots(g){"),
        "E9": ex("function screw(g, x, y, r){", "/* ---------- the aircraft photo"),
        "E10": patched(ex("/* ---------- sound: recorded flap clatter", "/* ---------- board styles and night mode ---------- */"),
                       ('const SOUNDS_JS = "sounds.js?v=', 'const SOUNDS_JS = "../test/sounds.js?v='),
                       ('const SIG_JS = "signature.js?v=', 'const SIG_JS = "../test/signature.js?v='),
                       ('const WORLD_JS = "world.js?v=', 'const WORLD_JS = "../test/world.js?v=')),
        "E11": ex("/* ---------- reference tables ---------- */", "/* ---------- network ---------- */"),
        "E12": patched(ex("/* ---------- network ---------- */", "/* ---------- demo traffic (clearly sample data) ---------- */"),
                       ("  if (feat && feat.info === info) { renderFeatured(); if (isAc(page)) renderAircraft(); }\n}",
                        "  if (feat && feat.info === info) { renderFeatured(); renderAircraftInfo(); }\n}")),
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
                        "    if (feat && feat.hex === hex) renderAircraftInfo();"),
                       ("if (feat && feat.hex === hex && isAc(page)) renderAircraft(); });",
                        "if (feat && feat.hex === hex) renderAircraftInfo(); });")),
        "E22": ex("function legendGroups(){", "function legendChip("),
        "E23": ex("const fmtDay = ts =>", "async function fetchLogbook(){"),
        "E24": ex("function logbookSummary(noPts){", "function renderLogbookBoard(){"),
        "E25": ex("const radar = {raf: 0", "const RADAR_GEO") + ex("function rgba(hex, a)", "function radarBox()") + ex("function altShort(ft){", "function drawRadar(t){"),
        "E26": ex("const lampOf = r =>", "// Spotted today is engraved text, like the legend"),
        "E27": ex("function spottedSummary(){", "const lampOf = r =>"),
        "E28": ex("const LB_CATS = [", "vdef(\"logbook\", \"lvSight\""),
        # Settings (1.53.2): the shared plates (COCKPIT, cockpitFor), the controls, their wiring, Save/Cancel; main.js's
        # cockpit region says which screen (COCKPIT_FOR) and the app's own cockpitDone/cockpitMark go with it
        "E29": ex("/* Settings, once for every screen", "function plateHtml(p){") + ex("/* ---------- Settings: the sounds of the controls", "function applySettings(n){"),
        # 1.119: the app's tips say "OK" (the board keeps "Got it")
        "E33": patched(ex("/* ---------- languages ----------", "/* ---------- airport mode ----------"),
                       ('L.querySelector(".tipOk").textContent = T("Got it");', 'L.querySelector(".tipOk").textContent = T("OK");')),
        "E32": ex("/* ---------- airport mode ----------", "/* ---------- versions and patch notes ----------"),
        "E31": ex("/* ---------- versions and patch notes", "/* ---------- settings: a cockpit panel ----------"),
        "E30": patched(ex("/* ---------- main loop ---------- */", "async function start(){"),
                       ("timer = setTimeout(poll, S.demo ? 2000 :", "timer = setTimeout(poll, document.hidden ? 60000 : S.demo ? 2000 :")),
    }
    css = ex("/* push buttons: plain ivory caps", "#viewTools{z-index:2}") + ex("/* Settings: a cockpit panel.", "</style>")
    return E, css


# main.js marks the parts that only the split flaps need with //@L:name ... //@L:end; the light version
# (tools/light/build.py) puts its own code there, the app keeps them as they are.
REGION = re.compile(r"^//@L:(\w+)\n(.*?)^//@L:end\n", re.S | re.M)


def assemble(head, js, E, css, out, regions=None, extra_css=""):
    """Put the page together: the board's CSS into head's <style>, the board's code into main.js's //@E markers.
    `regions` replaces main.js's //@L regions by name (the light version); without it they stay as they are."""
    def region(m):
        if regions is None:
            return m.group(2)
        if m.group(1) not in regions:
            raise SystemExit(f"The light version has no code for main.js's region {m.group(1)!r}")
        return regions[m.group(1)]
    js = REGION.sub(region, js)
    m = re.search(r'<script src="i18n\.js\?v=[0-9a-f]+"></script>', board)
    if not m:
        raise SystemExit("The board doesn't load i18n.js (<script src=\"i18n.js?v=...\">)")
    i = head.rindex("<script>\n")              # the translations before the app's own script, from the test board
    head = head[:i] + m.group(0).replace('src="', 'src="../test/') + "\n" + head[i:]
    assert "//@L:" not in js, "an unclosed //@L region in main.js"
    head = head.replace("/*CAPS_AND_COCKPIT*/\n", extra_css).replace("<style>\n", "<style>\n" + css.replace("body.lite", "body.no-lite"), 1)
    for k, v in E.items():
        marker = f"//@{k}\n"
        n = js.count(marker)
        assert n == 1 or (n == 0 and regions is not None), k   # the light version leaves the flap engine out
        js = js.replace(marker, v)
    assert "//@E" not in js
    out.write_text(head + js, encoding="utf-8", newline="\n")
    print("wrote", out, len(head + js), "bytes")


if __name__ == "__main__":
    assets.stamp()
    E, css = extract(Path(sys.argv[1] if len(sys.argv) > 1 else REPO / "test" / "index.html").read_text(encoding="utf-8"))
    assemble((SP / "head.html").read_text(encoding="utf-8"), (SP / "main.js").read_text(encoding="utf-8"), E, css,
             Path(sys.argv[2] if len(sys.argv) > 2 else REPO / "app" / "index.html"))
