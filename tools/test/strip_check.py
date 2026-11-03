"""1.129.21 (to-do #305): the app is written without comments (tools/app/strip.py). This checks that only comments went:
it builds the app once more with them, reads every inline script of both with ESLint's own JavaScript parser (espree,
installed by tools/test/lint.py) and compares them token by token, and whether a line break stands before each token
(JavaScript's automatic semicolons depend on it). Part of `smoke.py --syntax`; alone: py tools/test/strip_check.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "test"))
sys.path.insert(0, str(REPO / "tools" / "app"))
import lint  # noqa: E402  (its CACHE has ESLint, and espree with it)

COMPARE = r"""
const espree = require(process.argv[2]), fs = require("fs");
const LB = new RegExp("[\\n\\r" + String.fromCharCode(0x2028, 0x2029) + "]");
const toks = src => { const t = espree.tokenize(src, {ecmaVersion: "latest", range: true});
  return t.map((x, i) => [x.type, x.value, LB.test(src.slice(i ? t[i - 1].range[1] : 0, x.range[0]))]); };
const out = [];
for (const [a, b] of JSON.parse(fs.readFileSync(process.argv[3], "utf8"))) {
  const A = toks(fs.readFileSync(a, "utf8")), B = toks(fs.readFileSync(b, "utf8"));
  let i = 0; while (i < A.length && i < B.length && JSON.stringify(A[i]) === JSON.stringify(B[i])) i++;
  if (i < A.length || i < B.length) out.push(`${b}: token ${i} differs: ${JSON.stringify(A[i])} with comments, ${JSON.stringify(B[i])} without`);
}
console.log(out.join("\n"));
"""


def check():
    import build
    espree = lint.CACHE / "node_modules" / "espree"
    if not espree.is_dir():
        lint.check()                       # installs ESLint (and espree) into its cache
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = tmp / "full.html"
        E, css = build.extract((REPO / "test" / "index.html").read_text(encoding="utf-8"))
        build.assemble((build.SP / "head.html").read_text(encoding="utf-8"), (build.SP / "main.js").read_text(encoding="utf-8"),
                       E, css, full)
        kept = build.strip_page(full.read_text(encoding="utf-8"))
        built = (REPO / "app" / "index.html").read_text(encoding="utf-8")
        if kept != built:
            print("strip: app/index.html isn't the built app without comments: run py tools/app/build.py")
            return False
        a = re.findall(r"<script>([\s\S]*?)</script>", full.read_text(encoding="utf-8"))
        b = re.findall(r"<script>([\s\S]*?)</script>", built)
        if len(a) != len(b):
            print(f"strip: {len(a)} scripts with comments, {len(b)} without")
            return False
        pairs = []
        for i, (x, y) in enumerate(zip(a, b)):
            (tmp / f"a{i}.js").write_text(x, encoding="utf-8"); (tmp / f"b{i}.js").write_text(y, encoding="utf-8")
            pairs.append([str(tmp / f"a{i}.js"), str(tmp / f"b{i}.js")])
        (tmp / "pairs.json").write_text(json.dumps(pairs), encoding="utf-8")
        (tmp / "compare.js").write_text(COMPARE, encoding="utf-8")
        r = subprocess.run(["node", str(tmp / "compare.js"), str(espree), str(tmp / "pairs.json")], capture_output=True, text=True)
        if r.returncode or r.stdout.strip():
            print("strip: removing the comments changed the app's code:\n" + (r.stdout + r.stderr).strip())
            return False
    print(f"strip: the app's {len(a)} scripts are the same code without comments")
    return True


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
