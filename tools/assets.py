"""The board's separate files (1.53.1): the translations (test/i18n.js) and the recorded sounds (test/sounds.js) live
next to the test board instead of inside it, so the board file is half the size and a screen keeps them in its cache.
The board names each with a version: the start of its SHA-256, as `i18n.js?v=0123456789`. A new version has a new
address, so the relay (48+) and the app's service worker can keep a copy for a long time and still load a changed one.

    py tools/assets.py              stamp the current versions into test/index.html (and index.html, if it uses them)
    py tools/assets.py --check      only say whether they are current (exit 1 if not)

tools/app/build.py stamps before it builds, and build_sounds.py after writing sounds.js, so normally there is nothing
to run by hand. The app and the light version load the test board's copies (../test/i18n.js); the main board
(index.html) loads its own copies in the repository root, copied by tools/push_main.py.
"""
import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSETS = ("i18n.js", "sounds.js", "signature.js", "world.js")   # 1.103: the flight school's signature font; 1.107: the passport's map


def version(f):
    return hashlib.sha256(Path(f).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:10]   # the same on a CRLF checkout


def stamped(html, folder):
    """`html` with every `name?v=...` of an asset changed to the version of that file in `folder`."""
    for name in ASSETS:
        f = Path(folder) / name
        if f.is_file():
            html = re.sub(re.escape(name) + r"\?v=[0-9a-f]*", f"{name}?v={version(f)}", html)
    return html


def stamp(check=False):
    stale = []
    for page in (REPO / "test" / "index.html", REPO / "index.html"):
        html = page.read_text(encoding="utf-8")
        new = stamped(html, page.parent)
        if new != html:
            stale.append(page.relative_to(REPO).as_posix())
            if not check:
                page.write_text(new, encoding="utf-8", newline="\n")
    return stale


if __name__ == "__main__":
    check = "--check" in sys.argv
    stale = stamp(check)
    if check and stale:
        raise SystemExit(f"out of date: {', '.join(stale)} (run py tools/assets.py)")
    print(("stamped: " if stale else "up to date") + ", ".join(stale))
