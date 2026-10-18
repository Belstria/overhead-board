"""A quick check that a change didn't break the pages: run by GitHub Actions on every pull request (.github/workflows/
check.yml), and handy before a commit.

    py tools/test/smoke.py --syntax    the inline scripts of the boards and the apps parse (needs Node)
    py tools/test/smoke.py             the test relay with made-up flights, then /, /test/, /app/, /light/ and /test-api/ in a
                                       headless browser (needs Playwright); fails on any page error

The test relay is the one from run_test_relay.py, started here and stopped at the end.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PAGES = ["index.html", "test/index.html", "app/index.html", "light/index.html"]


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
    print("scripts parse" if not bad else f"{bad} script(s) don't parse")
    return bad == 0


def pages():
    from playwright.sync_api import sync_playwright
    relay = subprocess.Popen([sys.executable, str(REPO / "tools" / "test" / "run_test_relay.py"), "--fr24"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen("http://localhost:8096/health", timeout=2).status == 200:
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
                req = urllib.request.Request("http://localhost:8096/aircraft/48.2085/16.3731/25", headers={"Cookie": "overhead=test-device"})
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
        errors = []
        with sync_playwright() as p:
            b = p.chromium.launch()
            # relay 42: every screen is signed in; without a cookie the relay shows the private page (checked too)
            ctx = b.new_context()
            pg = ctx.new_page()
            pg.goto("http://localhost:8096/test/")
            if "This board is private" not in pg.content():
                errors.append("without a cookie /test/ didn't show the private page")
            ctx.close()
            ctx = b.new_context()
            ctx.add_cookies([{"name": "overhead", "value": "test-device", "domain": "localhost", "path": "/"}])
            for url, size in [("http://localhost:8096/", (1920, 1080)), ("http://localhost:8096/test/", (1920, 1080)), ("http://localhost:8096/app/", (390, 844)),
                              ("http://localhost:8096/app/", (844, 390)),
                              ("http://localhost:8096/light/", (390, 844)), ("http://localhost:8096/light/", (844, 390)), ("http://localhost:8096/test-api/", (1280, 720))]:
                pg = ctx.new_page()
                pg.set_viewport_size({"width": size[0], "height": size[1]})
                pg.on("pageerror", lambda e, url=url, size=size: errors.append(f"{url} {size}: {e}"))
                pg.goto(url)
                pg.wait_for_timeout(8000)
                print(f"{pg.url} at {size[0]}x{size[1]}: loaded")
                pg.close()
            b.close()
        for e in errors:
            print("page error:", e)
        print("no page errors" if not errors else f"{len(errors)} page error(s)")
        return not errors
    finally:
        relay.terminate()


if __name__ == "__main__":
    ok = syntax() if "--syntax" in sys.argv else pages()
    sys.exit(0 if ok else 1)
