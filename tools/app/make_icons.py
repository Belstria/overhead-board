"""Draws the app icons with a title badge (1.61): app/icon-192-<badge>.png, icon-512-<badge>.png,
icon-maskable-512-<badge>.png and apple-touch-icon-<badge>.png, one set per badge in the board's STYLES. The look is
the plain icons' (a yellow split flap) with the badge's silhouette in place of the plane, drawn by the board's own
code (badgeGlyph, drawPlaneShape, iconDraw, copied out of test/index.html), so the logo, the browser tab and the app
icon match. The relay hands a profile with a badge a manifest naming these (relay 53).

Needs Playwright (as tools/test/shoot.py):  py tools/app/make_icons.py
Run it again when a badge is added or its drawing changes.
"""
import asyncio
import base64
import re
from pathlib import Path

from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parent.parent.parent
board = (REPO / "test" / "index.html").read_text(encoding="utf-8")


def fn(name):
    m = re.search(r"^function " + name + r"\(.*?^}\n", board, re.S | re.M)
    if not m:
        raise SystemExit(f"function {name} not found in the board")
    return m.group(0)


badges = re.search(r'\["badge", "Title badge", \[(.*?)\]\]\]', board, re.S).group(1)
IDS = [i for i in re.findall(r'\["([a-z]*)"', badges) if i]
# file name, size, glyph half-size (share of the side), rounded corners: the maskable one keeps to the middle 80 %
SETS = [("icon-192-{}.png", 192, .3), ("icon-512-{}.png", 512, .3), ("icon-maskable-512-{}.png", 512, .24),
        ("apple-touch-icon-{}.png", 180, .3)]
JS = fn("badgeGlyph") + fn("drawPlaneShape") + fn("iconDraw") + """
window.draw = (id, n, k) => { const cv = document.createElement("canvas"); cv.width = cv.height = n;
  iconDraw(cv.getContext("2d"), n, id, k); return cv.toDataURL("image/png"); };"""


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        page = await b.new_page()
        await page.set_content(f"<script>{JS}</script>")
        for i in IDS:
            for name, n, k in SETS:
                url = await page.evaluate("([i, n, k]) => draw(i, n, k)", [i, n, k])
                out = REPO / "app" / name.format(i)
                out.write_bytes(base64.b64decode(url.split(",", 1)[1]))
                print("wrote", out.relative_to(REPO))
        await b.close()

asyncio.run(main())
