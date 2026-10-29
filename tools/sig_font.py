"""1.103: make test/signature.js, the flight school's signature font, from EMS Allure's SVG font file.

    py tools/sig_font.py EMSAllure.svg          # from https://gitlab.com/oskay/svg-fonts (fonts/EMS/EMSAllure.svg)

EMS Allure is a single-stroke script (each letter a pen's path), so the app can write a name stroke by stroke. Kept:
U+0020-U+007E and U+00C0-U+00FF, coordinates rounded to whole units (about 30 KB, 9 KB compressed).
"""
import html
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "test" / "signature.js"
HEAD = """// The flight school's signature (1.103, the phone app): the player's name written as with a pen. The letters are
// EMS Allure, a single-stroke script font (each letter a pen's path, not an outline), so the app can draw them stroke
// by stroke. Fetched only when the signature is drawn. Made by tools/sig_font.py from the font's SVG file: Latin
// letters, digits and signs (U+0020-U+007E, U+00C0-U+00FF), coordinates rounded; y up, 1000 units to the em, the
// baseline at 0. Each glyph: [advance, SVG path].
//
// EMS Allure: created by Sheldon B. Michaels, SVG font conversion by Windell H. Oskay (Evil Mad Scientist
// Laboratories, https://gitlab.com/oskay/svg-fonts). A derivative of Allura, designed by Rob Leuschke, TypeSETit
// (Copyright (c) 2012 by TypeSETit, LLC, with Reserved Font Name "Allura").
// Licensed under the SIL Open Font License, Version 1.1 (its full text: fonts/OFL.txt): the font may be used, bundled
// and changed freely, provided this notice stays with it, it isn't sold on its own and a changed version doesn't use
// the reserved name. This file is such a changed version (a subset, rounded), named EMS Allure as its source.
"""


def glyphs(svg):
    out = {}
    for m in re.finditer(r'<glyph unicode="([^"]*)"[^>]*?horiz-adv-x="([\d.]+)"(?:[^>]*?d="([^"]*)")?', svg):
        ch = html.unescape(m.group(1))
        if len(ch) != 1 or not (32 <= ord(ch) < 127 or 0xC0 <= ord(ch) <= 0xFF):
            continue
        d = re.sub(r"-?\d+(\.\d+)?", lambda n: str(round(float(n.group()))), m.group(3) or "")
        out[ch] = [round(float(m.group(2))), re.sub(r"\s*([MLC])\s*", r"\1", d).strip()]
    return out


if __name__ == "__main__":
    G = glyphs(Path(sys.argv[1]).read_text(encoding="utf-8"))
    body = "window.SIG_FONT = {\n" + ",\n".join(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, separators=(',', ':'))}"
                                               for k, v in G.items()) + "\n};\n"
    OUT.write_text(HEAD + body, encoding="utf-8", newline="\n")
    print("wrote", OUT, len((HEAD + body).encode()), "bytes,", len(G), "glyphs")
