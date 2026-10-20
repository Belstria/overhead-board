"""Fetch the board's three typefaces (Archivo Narrow, Oswald, Barlow Condensed; SIL Open Font License) from Google Fonts
into fonts/, with fonts/fonts.css naming them by file. Since 1.64 the boards, the app and the light version load the
fonts from there (the relay or GitHub Pages), so opening a board no longer asks Google for them.

    py tools/fonts.py          run again only to change the typefaces or their weights

Only the Latin and Latin Extended parts are kept (the five languages of the board). The files are named by their
content, so a screen may keep them for good.
"""
import hashlib
import re
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "fonts"
CSS = ("https://fonts.googleapis.com/css2?family=Archivo+Narrow:wght@400;500;600;700&family=Oswald:wght@400;500;600;700"
       "&family=Barlow+Condensed:wght@400;500;600;700&display=swap")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"   # woff2
KEEP = ("latin", "latin-ext")


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()


def main():
    css = get(CSS).decode()
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.woff2"):
        old.unlink()
    out, names = [], {}
    for subset, face in re.findall(r"/\* ([a-z-]+) \*/\s*(@font-face \{.*?\})", css, re.S):
        if subset not in KEEP:
            continue
        url = re.search(r"url\((https://[^)]+)\)", face).group(1)
        if url not in names:
            body = get(url)
            family = re.search(r"font-family: '([^']+)'", face).group(1).lower().replace(" ", "-")
            names[url] = f"{family}-{subset}-{hashlib.sha256(body).hexdigest()[:10]}.woff2"
            (OUT / names[url]).write_bytes(body)
        out.append(f"/* {subset} */\n" + face.replace(url, names[url]))
    (OUT / "fonts.css").write_text("/* Made by tools/fonts.py from Google Fonts (SIL Open Font License, fonts/OFL.txt). */\n"
                                   + "\n".join(out) + "\n", encoding="utf-8")
    print(f"{len(names)} font files, {len(out)} faces in fonts/fonts.css")


if __name__ == "__main__":
    main()
