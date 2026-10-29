"""1.68: a check of the pages' code beyond "it parses" (smoke.py --syntax runs it): ESLint over the inline scripts of
the board, the app and the light version, failing on a name that isn't defined anywhere (a deleted helper still
called, a typo), a name declared twice, a constant assigned to. Unused names are counted, not failed.

    py tools/test/lint.py          (needs Node; ESLint is fetched once into .cache/lint, which git ignores)

Three pages share code, so some names exist on only one of them; the shared code reaches them behind a typeof check or
an element that only that page has. Those are OPTIONAL below; add a name there only for such a guarded use.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / ".cache" / "lint"
PAGES = ["test/index.html", "app/index.html"]   # light/ and glass/ are parked (1.71.3)
OPTIONAL = ["LIGHT", "achSpecial", "nvGoing", "gStripRender", "gme", "cardSheetPre", "cardSheetPost", "cardSheetClose", "cardSheetGrow", "WEAK_TV", "plusOn", "drawStatic", "recentInfo", "switchView", "rwyChanged", "glass", "page", "preloadPhoto",
            "noteFeatured", "renderPage", "renderAircraftInfo", "appApPage", "aboutShow", "renderPush", "arFeed", "showTab", "schoolMission", "stylesPage"]
CONFIG = """import globals from "globals";
export default [{
  files: ["src/*.js"],
  languageOptions: {ecmaVersion: 2022, sourceType: "script",
    globals: {...globals.browser, I18N_ROWS: "readonly", SOUND_DATA: "readonly", %s}},
  rules: {"no-undef": "error", "no-redeclare": "error", "no-const-assign": "error", "no-func-assign": "error", "no-dupe-keys": "error",
    "no-unused-vars": ["warn", {vars: "local", args: "none", caughtErrors: "none", ignoreRestSiblings: true}]},
}];
""" % ", ".join(f"{n}: \"readonly\"" for n in OPTIONAL)


def check():
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Node isn't installed; the lint needs it")
    if not (CACHE / "node_modules" / "eslint").is_dir():
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "package.json").write_text('{"private": true}\n')
        subprocess.run([npm, "install", "--silent", "--no-audit", "--no-fund", "eslint@9.13.0", "globals@15.11.0"], cwd=CACHE, check=True)
    src = CACHE / "src"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir()
    for page in PAGES:
        for i, js in enumerate(re.findall(r"<script>([\s\S]*?)</script>", (REPO / page).read_text(encoding="utf-8"))):
            (src / f"{page.replace('/', '_')}-{i}.js").write_text(js, encoding="utf-8")
    (CACHE / "eslint.config.mjs").write_text(CONFIG, encoding="utf-8")
    r = subprocess.run([str(CACHE / "node_modules" / ".bin" / "eslint"), "src", "--format", "json"], cwd=CACHE, capture_output=True, text=True)
    errors, unused = 0, 0
    for f in json.loads(r.stdout or "[]"):
        name = Path(f["filePath"]).name
        for m in f["messages"]:
            if m["severity"] == 2:
                errors += 1
                print(f"{name}:{m['line']}: {m['message']}")
            else:
                unused += 1
    print(f"lint: {'no' if not errors else errors} error(s), {unused} unused name(s)")
    return not errors


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
