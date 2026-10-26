"""A quick check that a change didn't break the pages: run by GitHub Actions on every pull request (.github/workflows/
check.yml), and handy before a commit.

    py tools/test/smoke.py --syntax    the inline scripts of the boards and the apps and their separate files (i18n.js,
                                       sounds.js) parse, and the boards name those files' current versions (needs Node);
                                       the code map is complete (tools/codemap.py --check)
    py tools/test/smoke.py             the test relay with made-up flights, its rules and saves (flows.py), then /, /test/, /app/,
                                       and /test-api/ in a headless browser (needs Playwright); fails on any page error
    py tools/test/smoke.py --port 8296 the test relay on another port (or env PORT; default 8096), so parallel
                                       checkouts don't test each other's relay

The test relay is the one from run_test_relay.py, started here and stopped at the end.
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else int(os.environ.get("PORT") or 8096)
BASE = f"http://localhost:{PORT}"
PAGES = ["index.html", "test/index.html", "app/index.html"]   # light/ and glass/ are parked (1.71.3)
sys.path.insert(0, str(REPO / "tools"))
import assets  # noqa: E402  (tools/assets.py)


def syntax():
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node isn't installed; the syntax check needs it")
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for page in PAGES:
            html = (REPO / page).read_text(encoding="utf-8")
            for i, js in enumerate(re.findall(r"<script>([\s\S]*?)</script>", html)):
                f = Path(tmp) / f"{page.replace('/', '_')}-{i}.js"
                f.write_text(js, encoding="utf-8")
                r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
                if r.returncode:
                    bad += 1
                    print(f"{page}, script {i + 1}:\n{r.stderr.strip()}\n")
        for f in [REPO / d / n for d in ("", "test") for n in assets.ASSETS if (REPO / d / n).is_file()]:
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                bad += 1
                print(f"{f.relative_to(REPO).as_posix()}:\n{r.stderr.strip()}\n")
    stale = assets.stamp(check=True)
    if stale:
        bad += 1
        print(f"{', '.join(stale)} don't name the current i18n.js/sounds.js: run py tools/assets.py (or tools/app/build.py)")
    sys.path.insert(0, str(REPO / "tools" / "test"))
    import tokens                                  # 1.68: the app's CSS keeps to the type scale
    if not tokens.check():
        bad += 1
    import lint                                    # 1.68: no undefined names in the pages' code (ESLint)
    if not lint.check():
        bad += 1
    import codemap                                 # to-do #109: every function and CSS rule is in an area of the code map
    if not codemap.check():
        bad += 1
    print("scripts parse" if not bad else f"{bad} script(s) don't parse")
    return bad == 0


def pages():
    from playwright.sync_api import sync_playwright
    relay = subprocess.Popen([sys.executable, str(REPO / "tools" / "test" / "run_test_relay.py"), "--fr24", "--port", str(PORT)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(BASE + "/health", timeout=2).status == 200:
                    break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("the test relay didn't start")
        # the relay must hand out positions too (relay 34 failed every request with a custom source and nobody saw it)
        import json
        ac = []
        for _ in range(10):
            try:
                req = urllib.request.Request(BASE + "/aircraft/48.2085/16.3731/25", headers={"Cookie": "overhead=test-device"})
                ac = json.loads(urllib.request.urlopen(req, timeout=10).read()).get("ac") or []
            except (OSError, ValueError):
                ac = []
            if ac:
                break
            time.sleep(1)
        if not ac:
            print("the test relay served no positions at /aircraft/48.2085/16.3731/25")
            return False
        print(f"positions: {len(ac)} aircraft")
        # relay 54: who gets the admin pages, packed pages, the saves (tools/test/flows.py)
        sys.path.insert(0, str(REPO / "tools" / "test"))
        import flows
        flows.BASE = BASE
        if not flows.checks():
            return False
        # 1.53.1: the board's translations and sounds, by the version the board names, kept for good (relay 48)
        board = (REPO / "test" / "index.html").read_text(encoding="utf-8")
        for name in assets.ASSETS:
            m = re.search(re.escape(name) + r"\?v=([0-9a-f]+)", board)
            r = urllib.request.urlopen(f"{BASE}/test/{name}?v={m.group(1)}", timeout=10) if m else None
            if not r or r.status != 200 or "immutable" not in (r.headers.get("Cache-Control") or ""):
                print(f"/test/{name} isn't served as a lasting file by its version")
                return False
        errors = []
        with sync_playwright() as p:
            b = p.chromium.launch()
            errors += [f"app saves: {x}" for x in flows.browser_checks(b)]      # 1.64 (flows.py)
            # relay 42: every screen is signed in; without a cookie the relay shows the private page (checked too)
            ctx = b.new_context()
            pg = ctx.new_page()
            pg.goto(BASE + "/test/")
            if "This board is private" not in pg.content():
                errors.append("without a cookie /test/ didn't show the private page")
            ctx.close()
            ctx = b.new_context()
            ctx.add_cookies([{"name": "overhead", "value": "test-device", "domain": "localhost", "path": "/"}])
            for url, size in [(BASE + "/", (1920, 1080)), (BASE + "/test/", (1920, 1080)), (BASE + "/app/", (390, 844)),
                              (BASE + "/app/", (844, 390)),
                              (BASE + "/test-api/", (1280, 720))]:
                pg = ctx.new_page()
                pg.set_viewport_size({"width": size[0], "height": size[1]})
                pg.on("pageerror", lambda e, url=url, size=size: errors.append(f"{url} {size}: {e}"))
                pg.goto(url)
                pg.wait_for_timeout(8000)
                if not pg.evaluate("!document.querySelector('script[src*=\"i18n.js\"]') || (window.I18N_ROWS || []).length"):
                    errors.append(f"{url} {size}: no translations (i18n.js didn't load)")
                print(f"{pg.url} at {size[0]}x{size[1]}: loaded")
                pg.close()
            # 1.58 (#47 step 5): at a Fire TV's size every Settings and Account & device plate must fit (a TV can't scroll)
            from plates import OVERFLOW_JS, FIRE_TV
            ctx = b.new_context(**FIRE_TV)
            ctx.add_cookies([{"name": "overhead", "value": "test-device", "domain": "localhost", "path": "/"}])
            pg = ctx.new_page()
            pg.goto(BASE + "/test/")
            pg.wait_for_timeout(6000)
            pg.keyboard.press("s")
            pg.wait_for_timeout(1500)
            for o in pg.evaluate(OVERFLOW_JS):
                errors.append(f"Fire TV Settings: plate {o}")
            pg.evaluate("document.querySelector('#cockpit [data-act=account]').click()")
            pg.wait_for_timeout(2000)
            for o in pg.evaluate(OVERFLOW_JS):
                errors.append(f"Fire TV Account & device: plate {o}")
            # 1.93.0.1: and About's (its Keys and About plates ran past their edges, the last credits cut off)
            pg.evaluate("location.hash = '#about'")
            pg.wait_for_timeout(1500)
            if pg.evaluate("document.querySelectorAll('#cockpit:not([hidden]) .plate').length") != 3:
                errors.append("Fire TV About: the view didn't open with its three plates")
            for o in pg.evaluate(OVERFLOW_JS):
                errors.append(f"Fire TV About: plate {o}")
            # 1.92: the Logbook's plates at that size: its buttons end above them, the remote's ring is on a plate, and
            # a plate's card opens
            pg.evaluate("location.hash = '#logbook'")
            pg.wait_for_timeout(2500)
            lb = pg.evaluate("""() => { const s = document.getElementById('stage').getBoundingClientRect(), k = s.height / 1080,
              t = document.getElementById('viewTools').getBoundingClientRect(), a = document.activeElement;
              return {gap: 266 * k - (t.bottom - s.top), plates: document.querySelectorAll('#lbHits button').length, ring: (a && a.dataset && a.dataset.k) || ''}; }""")
            if lb["gap"] < 0:
                errors.append(f"Fire TV Logbook: its buttons run {-lb['gap']:.1f} px into the plates")
            if lb["plates"] != 7 or not lb["ring"]:
                errors.append(f"Fire TV Logbook: {lb['plates']} plates, the remote's ring on {lb['ring'] or 'none'}")
            pg.evaluate("document.querySelector('#lbHits [data-k=types]').click()")
            pg.wait_for_timeout(800)
            if not pg.evaluate("!!document.querySelector('#cardBox:not([hidden]) .lbCard')"):
                errors.append("Fire TV Logbook: a plate's card didn't open")
            print("plates fit at 960x540 (Fire TV)" if not any(e.startswith("Fire TV") for e in errors) else "plates overflow at 960x540")
            ctx.close()
            b.close()
        for e in errors:
            print("page error:", e)
        print("no page errors" if not errors else f"{len(errors)} page error(s)")
        return not errors
    finally:
        # the test relay's own two processes go with it (a plain terminate left them running on Windows)
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(relay.pid)], capture_output=True)
        else:
            relay.send_signal(signal.SIGINT)
            try:
                relay.wait(10)
            except subprocess.TimeoutExpired:
                relay.kill()


if __name__ == "__main__":
    ok = syntax() if "--syntax" in sys.argv else pages()
    sys.exit(0 if ok else 1)
