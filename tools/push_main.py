""""Push to main": make the main board (index.html) a copy of the test board, when Dave says so.

    py tools/push_main.py

Copies test/index.html to index.html with the two lines that differ (the title, and the comment that this copy is the
test board), and the board's separate files (tools/assets.py: i18n.js, sounds.js) from test/ to the repository root,
then stamps their versions. The main board loads its own copies, so the test board's later changes to them don't reach
it before the next push to main. Then commit and push as usual.
"""
import shutil
from pathlib import Path

import assets

REPO = assets.REPO
DIFFERS = [
    ("<title>Fallblatt (Test)</title>", "<title>Fallblatt</title>"),
    ("// This copy of the board (the test board) also gets real flight numbers and routes from Flightradar24, through the home",
     "// The main board also gets real flight numbers and routes from Flightradar24, through the home"),
    # 1.79.2: the main board sits at the top, so the typefaces are next to it (../ works through the relay but not on
    # GitHub Pages' own address, where it leaves the project)
    ('<link rel="stylesheet" href="../fonts/fonts.css">', '<link rel="stylesheet" href="fonts/fonts.css">'),
]

html = (REPO / "test" / "index.html").read_text(encoding="utf-8")
for a, b in DIFFERS:
    if html.count(a) != 1:
        raise SystemExit(f"test/index.html changed: {a[:60]!r} should be there once (update DIFFERS here)")
    html = html.replace(a, b)
for name in assets.ASSETS:
    shutil.copyfile(REPO / "test" / name, REPO / name)
(REPO / "index.html").write_text(html, encoding="utf-8", newline="\n")
assets.stamp()
print("index.html, " + ", ".join(assets.ASSETS) + ": copied from test/ (commit them together)")
