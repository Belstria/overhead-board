"""1.68: the app's and the light version's CSS keep to the type scale: every font size is a --fs-* token from
tools/app/head.html's :root (a size outside it is how the look drifted to twenty sizes). Run by smoke.py --syntax.

    py tools/test/tokens.py
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FILES = ["tools/app/head.html"]   # tools/light/light.css is parked (1.71.3)
SIZE = re.compile(r"(?:font-size:\s*|font:\s*(?:italic\s+)?\d{3}\s+)([\d.]+px)")


def check():
    head = (REPO / FILES[0]).read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--(fs-[\w-]+):([\d.]+px)", head))
    bad = []
    for f in FILES:
        for n, line in enumerate((REPO / f).read_text(encoding="utf-8").splitlines(), 1):
            for px in SIZE.findall(line):
                bad.append(f"{f}:{n}: font size {px}: use one of {', '.join(f'var(--{k})' for k in tokens)}")
    for b in bad:
        print(b)
    print(f"type scale: {len(tokens)} sizes, kept" if not bad else f"{len(bad)} font size(s) off the scale")
    return not bad


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
