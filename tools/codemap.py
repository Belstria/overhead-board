"""The code map (to-do #109): where each part of Fallblatt lives, so a session reads only the lines it needs instead of
whole files. The areas (tools/codemap_areas.txt) name every place a part has in every file (functions, constants, CSS
rules, markup ids, relay endpoints, tests, README and history notes); this tool finds their current lines.

    py tools/codemap.py                  the areas, one line each: pick the one you're working on first
    py tools/codemap.py AREA             every place of that area, file by file, with its lines and its comment
    py tools/codemap.py --uses NAME      every line in the sources, tests and docs that mentions NAME, and where it sits
    py tools/codemap.py --find WORD      functions, sections, CSS and areas whose name or comment has WORD
    py tools/codemap.py --file PATH [WORD]  a file's outline: sections, functions, line ranges (only those matching WORD)
    py tools/codemap.py --build          what tools/app/build.py copies out of the board, and where it lands in the app
    py tools/codemap.py --diff [REV [REV2]]  the places changed since REV (origin/main), and the areas that list them
    py tools/codemap.py --check          what belongs to no area, and places that no longer exist (smoke.py --syntax runs it)

docs/code-map.md says how to read the code with it and which changes go together. Standard library only.
"""
import ast
import bisect
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AREAS = REPO / "tools" / "codemap_areas.txt"
BOARD, MAIN, HEAD, RELAY = "test/index.html", "tools/app/main.js", "tools/app/head.html", "relay/serve.py"
CHECKED = (BOARD, MAIN, RELAY)                  # every top-level function, const and class belongs to an area
CHECKED_CSS = (BOARD, HEAD)                     # and every CSS rule
# --uses leaves out copies, generated files, data and the parked versions (docs/architecture.md: don't keep those in step)
SKIP_USES = re.compile(r"^(index\.html|i18n\.js|sounds\.js|app/index\.html|test/sounds\.js|test-api/|light/|glass/|"
                       r"tools/light/|tools/glass/|fonts/|android/app/src/main/res/|.*\.(png|jpg|wav|woff2|ico|COF|jar)$)")
WIDTH = 150


def clip(s, n=WIDTH):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def sentence(text, n=110):
    """A comment's first sentence, or its start, on one line."""
    t = " ".join(text.split())
    m = re.search(r"(?<=[.!?])\s(?=[A-Z0-9(`\"'])", t)
    if m and m.start() <= n:
        t = t[:m.start()]
    return clip(t, n)


def read(rel):
    try:
        return (REPO / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# ---------- outlines: what a file has, by line ----------

class Item:
    """A place in a file: a function, constant, class, section, CSS rule, markup id or top-level statement."""
    __slots__ = ("kind", "name", "start", "end", "note", "code", "anchor")

    def __init__(self, kind, name, start, end, note="", code=""):
        self.kind, self.name, self.start, self.end, self.note, self.code = kind, name, start, end, note, code
        self.anchor = None                          # a top-level statement: the function or constant above it

    def lines(self):
        return f"{self.start}" if self.end <= self.start else f"{self.start}-{self.end}"


class Outline:
    def __init__(self, rel, text):
        self.rel, self.text = rel, text
        self.lines = text.split("\n")
        self.items = []        # functions, constants, classes, methods, statements (in order)
        self.sections = []     # section markers: Item("section", title, start, end)
        self.css = []          # CSS rules: Item("css", key, start, end, note, selector)
        self.markup = []       # (start, end) of the HTML outside <script> and <style>
        self.scripts = []      # (start, end) of inline scripts
        self.comments = set()  # the script lines that are only a comment
        self._starts = None

    def at(self, line):
        """The function or statement a line is in (None between them)."""
        if self._starts is None:
            self._starts = [it.start for it in self.items]
        i = bisect.bisect_right(self._starts, line) - 1
        while i >= 0:
            it = self.items[i]
            if it.start <= line <= it.end:
                return it
            if it.end < line and it.start < line - 4000:
                break
            i -= 1
        return None

    def section_at(self, line):
        best = None
        for s in self.sections:
            if s.start <= line <= s.end:
                best = s
        return best

    def css_at(self, line):
        for c in self.css:
            if c.start <= line <= c.end:
                return c
        return None


def comment_above(lines, i, py=False):
    """The comment block right above line i (0-based), as text; not a section marker's."""
    out, j = [], i - 1
    while j >= 0:
        s = lines[j].strip()
        if s.startswith("//@"):                     # main.js's build markers (//@E12, //@L:name) aren't comments
            break
        if py:
            if s.startswith("#") and not lines[j].startswith(" "):
                out.append(s.lstrip("#").strip())
                j -= 1
                continue
            if s.startswith("@"):            # a decorator
                j -= 1
                continue
            break
        if s.startswith("//"):
            out.append(s[2:].strip())
            j -= 1
            continue
        if s.endswith("*/"):
            k = j
            while k >= 0 and "/*" not in lines[k]:
                k -= 1
            if k < 0:
                break
            block = " ".join(x.strip() for x in lines[k:j + 1])
            out.append(block.split("/*", 1)[1].rsplit("*/", 1)[0].strip().lstrip("*").strip())
            j = k - 1
            continue
        break
    text = " ".join(reversed(out))
    if re.match(r"-{6,}", text) or re.match(r"#?\s*-{6,}", text):
        return ""
    return text


def trailing_comment(line, py=False):
    m = re.search(r"\s#\s+(.*)$" if py else r"[;,{)\]]\s*//\s?(.*)$", line)
    if m and line[:m.start()].count('"') % 2 == 0 and line[:m.start()].count("'") % 2 == 0 and line[:m.start()].count("`") % 2 == 0:
        return m.group(1)
    return ""


SECTION = re.compile(r"^(?:/\*|#|\s*/\*)\s*-{6,}\s*(.*?)\s*(?:-{6,}\s*(?:\*/)?\s*)?$")


def section_title(line):
    m = SECTION.match(line)
    return m.group(1).rstrip(" */") if m else None


# The script scanner: for each line, the bracket depth at its start and what it starts in: "c" code, "t" a template
# literal, "b" a block comment. Enough of JavaScript to find the top-level statements of the board and main.js.
_JS_CH = re.compile(r"[\"'`/(){}\[\]\n]")
_RX_BEFORE = set("(,=:[!&|?{};+-*%<>~^\n")
_RX_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "instanceof", "yield", "await"}


def js_lines(text):
    starts = [(0, "c")]
    depth, i, n = 0, 0, len(text)
    tmpl = []                                       # the depth each open ${ … } of a template literal started at

    def template(i):                                # inside a template literal's text, from i: returns where code goes on
        nonlocal depth
        while i < n:
            c = text[i]
            if c == "\\":
                i += 2
                continue
            if c == "`":
                return i + 1
            if c == "\n":
                starts.append((depth, "t"))
            elif c == "$" and text.startswith("${", i):
                tmpl.append(depth)
                depth += 1
                return i + 2
            i += 1
        return n

    while i < n:
        m = _JS_CH.search(text, i)
        if not m:
            break
        j = m.start()
        c = text[j]
        if c == "\n":
            starts.append((depth, "c"))
            i = j + 1
        elif c in "([{":
            depth += 1
            i = j + 1
        elif c in ")]}":
            depth -= 1
            i = j + 1
            if c == "}" and tmpl and tmpl[-1] == depth:
                tmpl.pop()
                i = template(i)
        elif c in "\"'":
            k = j + 1
            while k < n and text[k] != c and text[k] != "\n":
                k += 2 if text[k] == "\\" else 1
            i = k + 1 if k < n and text[k] == c else k
        elif c == "`":
            i = template(j + 1)
        else:                                       # "/": a comment, a regular expression or a division
            nx = text[j + 1:j + 2]
            if nx == "/":
                k = text.find("\n", j)
                i = n if k < 0 else k
            elif nx == "*":
                k = text.find("*/", j + 2)
                k = n if k < 0 else k
                starts.extend([(depth, "b")] * text.count("\n", j, k))
                i = k + 2
            else:
                p = j - 1
                while p >= 0 and text[p] in " \t":
                    p -= 1
                pc = text[p] if p >= 0 else "\n"
                w = re.search(r"[A-Za-z_$][\w$]*$", text[max(0, p - 12):p + 1]) if pc.isalnum() or pc in "_$" else None
                if pc in _RX_BEFORE or (w and w.group(0) in _RX_WORDS):
                    k, cls = j + 1, False
                    while k < n and text[k] != "\n":
                        ch = text[k]
                        if ch == "\\":
                            k += 2
                            continue
                        if ch == "[":
                            cls = True
                        elif ch == "]":
                            cls = False
                        elif ch == "/" and not cls:
                            break
                        k += 1
                    i = k + 1
                else:
                    i = j + 1
    return starts


_JS_DECL = re.compile(r"^(?:(async\s+)?function\s*\*?\s*([\w$]+)|class\s+([\w$]+)|(const|let|var)\s+(.*))")
_STRIP_LIT = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`|(?<=[=(,:!&|?])\s*/(?![*/])(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n])+/[a-z]*')


def js_declared(rest):
    """The names a const/let/var statement declares (`let a = 1, b = 2;` → a, b)."""
    s = _STRIP_LIT.sub('""', rest)
    names, depth, k, start = [], 0, 0, 0
    parts = []
    while k < len(s):
        c = s[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(s[start:k])
            start = k + 1
        elif c == ";" and depth == 0:
            break
        k += 1
    parts.append(s[start:k])
    for p in parts:
        m = re.match(r"\s*([\w$]+)\s*(=|$)", p)
        if m:
            names.append(m.group(1))
        elif re.match(r"\s*[\[{]", p):                       # destructuring: every name bound
            pat = p.split("=", 1)[0] if "}" in p.split("=", 1)[0] or "]" in p.split("=", 1)[0] else p
            names += [x for x in re.findall(r"(?:^|[{\[,:]|\.\.\.)\s*([A-Za-z_$][\w$]*)\s*(?=[,}\]=]|$)", pat)]
    return names


def outline_js(o, first, last, iife=True):
    """The top-level items of the script on lines first..last (1-based) of the outline's file."""
    lines = o.lines[first - 1:last]
    starts = js_lines("\n".join(lines))
    for k, (_, st) in enumerate(starts[:len(lines)]):
        if st == "b" or (st == "c" and lines[k].lstrip().startswith(("//", "/*"))):
            o.comments.add(first + k)
    base = 0
    if iife:
        for k, l in enumerate(lines):
            if l.strip() and not l.startswith("//"):
                if re.match(r"^\((?:\(\)\s*=>|function\s*\(\))\s*\{\s*$", l):
                    base = starts[k + 1][0] if k + 1 < len(starts) else 0
                break
    tops = []                                       # (index, kind, names, note, code)
    for k, l in enumerate(lines):
        if k >= len(starts):
            break
        depth, code = starts[k][0], starts[k][1] == "c"
        if not code or depth != base or not l or l[0] in " \t}])" or l.startswith(("//", "/*", "*", "<")):
            title = section_title(l) if code and depth == base and l.startswith("/*") else None
            if title:
                o.sections.append(Item("section", title, first + k, first + k))
            continue
        if l.startswith(('"use strict"', "'use strict'")):
            continue
        m = _JS_DECL.match(l)
        note = comment_above(lines, k)
        if m and m.group(2):
            tops.append((k, "function", [m.group(2)], note, l))
        elif m and m.group(3):
            tops.append((k, "class", [m.group(3)], note, l))
        elif m and m.group(4):
            tops.append((k, m.group(4), js_declared(m.group(5)), note, l))
        else:
            tops.append((k, "statement", [statement_name(l)], note, l))
    for t, (k, kind, names, note, code) in enumerate(tops):
        nxt = tops[t + 1][0] if t + 1 < len(tops) else len(lines)
        e = min(nxt, len(starts)) - 1
        while e > k and (not lines[e].strip() or starts[e][1] == "b" or (starts[e][1] == "c" and lines[e].startswith(("//", "/*")))):
            e -= 1                                  # not the blank lines and comments above the next one
        note = note or trailing_comment(code)
        for nm in names:
            o.items.append(Item(kind, nm, first + k, first + e, note, code))
    # A statement goes with the function or constant above it, or with the one its first line names (`layout();`,
    # `queueMicrotask(() => { recentFlights = loadRecent(); })`), the everywhere ones (S, $, T) aside.
    block = [it for it in o.items if first <= it.start <= last]
    names = {it.name for it in block if it.kind != "statement"} - {"S", "$", "T", "W", "H", "M", "K", "PX", "IW"}
    anchor, above, at = None, set(), None
    for it in block:
        if it.kind != "statement":
            if it.start != at:
                above, at = set(), it.start
            above.add(it.name)
            anchor = it.name
            continue
        ids = re.findall(r"[A-Za-z_$][\w$]*", it.code)
        it.anchor = next((x for x in ids if x in above), None) or next((x for x in ids if x in names), None) or anchor
    # a section runs to the next one
    secs = sorted(o.sections, key=lambda s: s.start)
    for a, b in zip(secs, secs[1:] + [None]):
        a.end = (b.start - 1) if b else last


def statement_name(l):
    """A short name for a top-level statement: `addEventListener("keydown"`, `$("photoImg").onload`, `setInterval`."""
    s = l.strip()
    m = re.match(r'^((?:document\.|window\.|[\w$]+\.|\$\("[\w-]+"\)\.)?addEventListener)\(\s*("[^"]*"|\w+)', s)
    if m:
        return f"{m.group(1)}({m.group(2)})"
    m = re.match(r'^(\$\("[\w-]+"\)(?:\.[\w$]+)+)\s*=', s)
    if m:
        return m.group(1)
    m = re.match(r"^([\w$.]+(?:\[[^\]]*\])?)\s*=[^=]", s)
    if m:
        return m.group(1)
    m = re.match(r"^([\w$.]+)\(", s)
    if m:
        return m.group(1)
    return clip(s, 40)


def outline_py(o):
    try:
        tree = ast.parse(o.text)
    except SyntaxError:
        return
    L = o.lines
    for k, l in enumerate(L):
        t = section_title(l) if l.startswith("# -") else None
        if t:
            o.sections.append(Item("section", t, k + 1, k + 1))

    def note_of(node, line):
        doc = ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
        return doc or comment_above(L, line - 1, py=True) or trailing_comment(L[line - 1], py=True)

    for node in tree.body:
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        end = getattr(node, "end_lineno", node.lineno)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            o.items.append(Item("def", node.name, start, end, note_of(node, start), L[node.lineno - 1]))
        elif isinstance(node, ast.ClassDef):
            o.items.append(Item("class", node.name, start, end, note_of(node, start), L[node.lineno - 1]))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    s = min([sub.lineno] + [d.lineno for d in sub.decorator_list])
                    o.items.append(Item("method", f"{node.name}.{sub.name}", s, sub.end_lineno, note_of(sub, s), L[sub.lineno - 1]))
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = []
            for t in targets:
                for x in ([t] if not isinstance(t, (ast.Tuple, ast.List)) else t.elts):
                    if isinstance(x, ast.Name):
                        names.append(x.id)
            kind = "assign" if not isinstance(node, ast.AugAssign) else "statement"
            for nm in names:
                o.items.append(Item(kind, nm, start, end, note_of(node, start), L[start - 1]))
            if not names:
                o.items.append(Item("statement", clip(L[start - 1].strip(), 40), start, end, "", L[start - 1]))
        elif not (isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant)) \
                and not isinstance(node, (ast.Import, ast.ImportFrom)):
            o.items.append(Item("statement", clip(L[start - 1].strip(), 40), start, end, comment_above(L, start - 1, py=True), L[start - 1]))
    o.items.sort(key=lambda it: (it.start, it.kind == "method"))
    secs = o.sections
    for a, b in zip(secs, secs[1:] + [None]):
        a.end = (b.start - 1) if b else len(L)


def css_key(selector):
    """A rule's key: the ids, classes and element of its first selector's first part (`.cap:hover` → .cap,
    `body.real .x` → body.real, `#nightView[hidden]` → #nightView)."""
    first = selector.split(",")[0].strip()
    comp = re.match(r"[^\s>+~]+", first)
    comp = comp.group(0) if comp else first
    comp = re.sub(r"\[[^\]]*\]", "", comp)
    comp = re.sub(r"::?[\w-]+(\((?:[^()]|\([^()]*\))*\))?", "", comp)
    return comp or first


def css_parts(key):
    return re.findall(r"[#.]?[^#.]+", key)


def outline_css(o, first, last):
    """The rules of the stylesheet on lines first..last: one Item per rule, keyed by css_key."""
    text = "\n".join(o.lines[first - 1:last])
    stack, j, n, cur = [], 0, len(text), 0
    last_comment, last_comment_end = "", -1
    while j < n:
        c = text[j]
        if text.startswith("/*", j):
            k = text.find("*/", j + 2)
            k = n if k < 0 else k
            body = text[j + 2:k].strip()
            line = first + text.count("\n", 0, j)
            t = section_title(o.lines[line - 1])
            if t and o.lines[line - 1].lstrip().startswith("/* -"):
                o.sections.append(Item("section", t, line, line))
            elif not re.fullmatch(r"[A-Z_@:]+", body):   # not a build marker (/*CAPS_AND_COCKPIT*/)
                last_comment, last_comment_end = body, k + 2
            j = k + 2
            cur = j
            continue
        if c == "{":
            sel = text[cur:j].strip()
            line = first + text.count("\n", 0, j) - sel.count("\n")
            if sel.startswith("@keyframes"):
                d, k = 1, j + 1
                while k < n and d:
                    d += {"{": 1, "}": -1}.get(text[k], 0)
                    k += 1
                o.css.append(Item("keyframes", "@" + sel.split()[1], line, first + text.count("\n", 0, k), "", sel))
                j = k
                cur = j
                continue
            if sel.startswith("@"):
                stack.append(None)                  # @media and the like: their rules count on their own
            else:
                raw = text[cur:j]
                above = last_comment_end >= 0 and not text[last_comment_end:cur + len(raw) - len(raw.lstrip())].strip()
                stack.append(Item("css", css_key(sel), line, line, sentence(last_comment) if above else "", sel))
            j += 1
            cur = j
            continue
        if c == "}":
            it = stack.pop() if stack else None
            if it is not None:
                it.end = first + text.count("\n", 0, j)
                o.css.append(it)
            j += 1
            cur = j
            continue
        if c in "\"'":
            k = j + 1
            while k < n and text[k] != c:
                k += 2 if text[k] == "\\" else 1
            j = k + 1
            continue
        if c == ";" and not stack:
            cur = j + 1
        j += 1
    o.css.sort(key=lambda it: it.start)
    secs = sorted([s for s in o.sections if first <= s.start <= last], key=lambda s: s.start)
    for a, b in zip(secs, secs[1:] + [None]):
        a.end = (b.start - 1) if b else last


def outline_html(o):
    L = o.lines
    k, n = 0, len(L)
    markup_from = 1
    while k < n:
        l = L[k]
        m = re.search(r"<(style|script)(?![^>]*\bsrc=)[^>]*>", l)
        if not m:
            k += 1
            continue
        tag = m.group(1)
        if markup_from <= k:
            o.markup.append((markup_from, k + 1))
        close = f"</{tag}>"
        if close in l[m.end():]:                     # a one-line script or style
            if tag == "script":
                o.scripts.append((k + 1, k + 1))
            k += 1
            markup_from = k + 1
            continue
        e = k + 1
        while e < n and close not in L[e]:
            e += 1
        body_first, body_last = k + 2, min(e, n)     # 1-based lines of the contents
        if tag == "style":
            outline_css(o, body_first, body_last)
        else:
            o.scripts.append((body_first, body_last))
            outline_js(o, body_first, body_last)
        k = e + 1
        markup_from = k + 1
    if markup_from <= n:
        o.markup.append((markup_from, n))
    o.items.sort(key=lambda it: it.start)
    o.sections.sort(key=lambda s: s.start)


def outline_md(o):
    for k, l in enumerate(o.lines):
        m = re.match(r"^(#{1,4})\s+(.*)", l)
        if m:
            o.sections.append(Item("section", m.group(2).strip(), k + 1, k + 1))
            continue
        m = re.match(r"^- (?:\*\*(.+?)\*\*|((?:\d+\.[\d.]+|Relay \d+)[^:]*?)[:(])", l)
        if m:
            name = m.group(1) or m.group(2)
            o.items.append(Item("entry", clip(name, 70), k + 1, k + 1, "", l))
    heads = [s.start for s in o.sections]
    for a, b in zip(o.items, o.items[1:] + [None]):
        e = min([(b.start - 1) if b else len(o.lines)] + [h - 1 for h in heads if h > a.start])   # to the next bullet or heading
        while e > a.start and not o.lines[e - 1].strip():
            e -= 1
        a.end = e
    for a, b in zip(o.sections, o.sections[1:] + [None]):
        a.end = (b.start - 1) if b else len(o.lines)


_OUTLINES = {}


def git_show(rev, rel):
    try:
        return subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=REPO, capture_output=True, check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        return None


def outline(rel, rev=None):
    """A file's outline, as it is now or (rev) in a git commit."""
    if (rel, rev) in _OUTLINES:
        return _OUTLINES[(rel, rev)]
    text = read(rel) if rev is None else git_show(rev, rel)
    if text is None:
        _OUTLINES[(rel, rev)] = None
        return None
    o = Outline(rel, text)
    if rel.endswith(".html"):
        outline_html(o)
    elif rel.endswith(".js"):
        outline_js(o, 1, len(o.lines))
    elif rel.endswith(".py"):
        outline_py(o)
    elif rel.endswith(".md"):
        outline_md(o)
    _OUTLINES[(rel, rev)] = o
    return o


def offsets(o):
    if not hasattr(o, "_off"):
        o._off = [0] + [m.end() for m in re.finditer("\n", o.text)]
    return o._off


def line_of(o, pos):
    return bisect.bisect_right(offsets(o), pos)


def find_lines(o, needle, after=None):
    """The lines that contain needle (`after`: a character class the next character mustn't be in)."""
    out, i, n = [], o.text.find(needle), len(needle)
    while i >= 0:
        if not (after and re.match(after, o.text[i + n:i + n + 1])):
            ln = line_of(o, i)
            if not out or out[-1] != ln:
                out.append(ln)
        i = o.text.find(needle, i + 1)
    return out


def ids_of(o):
    if not hasattr(o, "_ids"):
        o._ids = {}
        for m in re.finditer(r'\bid=\\?["\']([\w-]+)\\?["\']', o.text):
            o._ids.setdefault(m.group(1), []).append(line_of(o, m.start()))
    return o._ids


KIND = {"function": "fn", "statement": "top", "method": "def", "assign": "var", "keyframes": "@keyframes"}


def where(o, ln):
    """What line ln of a file is part of, in a few words."""
    it = o.at(ln) if o.items else None
    if it and it.kind != "entry":
        return f"{KIND.get(it.kind, it.kind)} {it.name}"
    c = o.css_at(ln) if o.css else None
    if c:
        return f"css {c.name}"
    if any(a <= ln <= b for a, b in o.markup):
        return "markup"
    s = o.section_at(ln)
    return clip(s.name, 40) if s else ""


def mentions(selector):
    """The classes and ids a selector names anywhere (`#cardBox .lbRow b, .cardish .x` → #cardBox .lbRow .cardish .x)."""
    return set(re.findall(r"[#.][A-Za-z_][\w-]*", re.sub(r"\[[^\]]*\]|url\([^)]*\)", "", selector)))


def css_match(tok, key):
    """`.cap` takes .cap, .cap.big (and .cap:hover, which is keyed .cap); an element (css:body) only itself."""
    return key == tok or (tok[0] in "#." and key.startswith(tok) and key[len(tok)] in ".#")


def ranges(nums):
    nums = sorted(set(nums))
    out, a, b = [], None, None
    for x in nums:
        if a is None:
            a = b = x
        elif x <= b + 3:
            b = x
        else:
            out.append(f"{a}" if a == b else f"{a}-{b}")
            a = b = x
    if a is not None:
        out.append(f"{a}" if a == b else f"{a}-{b}")
    return ", ".join(out)


GATE = re.compile(r"OVERHEAD_RELAY_VERSION\s*\|\|\s*0\)\s*(>=|<=|<|>)\s*(\d+)|\b(relayV\d+)\(\)")


def gate_list(text):
    found = []
    for m in GATE.finditer(text):
        g = m.group(3) or f"{m.group(1)} {m.group(2)}"
        if g not in found:
            found.append(g)
    return found


def gates(o, it):
    """The relay versions a function checks for: `(window.OVERHEAD_RELAY_VERSION || 0) >= 73`, relayV12(), or through a
    short check it calls (`psOk()` → >= 73 via psOk)."""
    if not it or (it.kind == "statement" and it.end - it.start > 200):
        return ""
    if not hasattr(o, "_gated"):                    # the short checks: a one- or two-line function or const with a gate
        raw = {x.name: gate_list("\n".join(o.lines[x.start - 1:x.end])) for x in o.items
               if x.kind != "statement" and x.end - x.start < 2}
        raw = {k: v for k, v in raw.items() if v}
        o._gated = {k: [g for g in v if g not in raw] or v for k, v in raw.items()}
    body = "\n".join(o.lines[it.start - 1:it.end])
    found = [g for g in gate_list(body) if g not in o._gated]          # relayV5() is told as ">= 5 via relayV5"
    for name in sorted(set(re.findall(r"\b([A-Za-z_$][\w$]*)\(", body)) & set(o._gated) - {it.name}):
        found += [f"{g} via {name}" for g in o._gated[name] if g not in found]
    return f" (relay {', '.join(found)})" if found else ""


def resolve(rel, tok):
    """Where a place is in a file now: [(start, end, label, note)]; [] when it isn't there; None when the file isn't."""
    o = outline(rel)
    if o is None:
        return None
    if tok[0] in "\"'":
        text = tok[1:-1]
        return [(ln, ln, f'"{clip(text, 60)}"', where(o, ln)) for ln in find_lines(o, text)]
    if tok[0] == "@":
        return [(c.start, c.end, f"@keyframes {c.name[1:]}", "") for c in o.css if c.kind == "keyframes" and c.name == tok]
    if tok.startswith("css:") or tok[0] in "#.":
        key = tok[4:] if tok.startswith("css:") else tok
        rules = [c for c in o.css if c.kind == "css" and css_match(key, c.name)]
        parts = set(css_parts(key)) if re.fullmatch(r"([#.][\w-]+)+", key) else None
        if not hasattr(o, "_named"):
            o._named = [(c, mentions(c.code)) for c in o.css if c.kind == "css"]
        inside = [c for c, named in o._named if parts and parts <= named and c not in rules] if parts else []
        out = []
        if rules:
            n = len(rules)
            out.append((rules[0].start, rules[-1].end, f"css {key} ({n} rule{'s' * (n != 1)}: {ranges([r.start for r in rules])})",
                        next((r.note for r in rules if r.note), "")))
        if inside:                                  # its rules inside other selectors (#cardBox .cCr, .seg.svPlaces,.seg.jumpSeg)
            n, keys = len(inside), sorted({r.name for r in inside})
            out.append((inside[0].start, inside[-1].end, f"css {key} (in {n} rule{'s' * (n != 1)} of {', '.join(keys[:4])}"
                        f"{' …' if len(keys) > 4 else ''}: {ranges([r.start for r in inside])})", next((r.note for r in inside if r.note), "")))
        if tok[0] == "#":
            lines = ids_of(o).get(tok[1:]) or ([] if rules else
                                               find_lines(o, f'$("{tok[1:]}")') or find_lines(o, f'getElementById("{tok[1:]}")'))
            out += [(ln, ln, f"#{tok[1:]}", where(o, ln)) for ln in lines]
        return out
    if tok[0] == "/":
        out = []
        for ln in find_lines(o, tok, r"[\w-]"):
            line = o.lines[ln - 1]
            if rel == RELAY and not re.search(r"[\"']" + re.escape(tok), line):
                continue                            # the relay: its code, not a comment that names the path
            it = o.at(ln) if o.items else None
            lists = re.search(r"^(\w+_PATHS) =|(path not in \()", line)
            note = (f"in {lists.group(1)}" if lists and lists.group(1) else "in the paths that aren't redirected to path/ (301)" if lists
                    else where(o, ln) + (gates(o, it) if rel.endswith((".html", ".js")) else ""))
            out.append((ln, ln, tok, note))
        return out
    items = [it for it in o.items if it.name == tok]
    if any(it.kind != "statement" for it in items):         # `def` the function, not its twenty calls
        items = [it for it in items if it.kind != "statement"]
    return [(it.start, it.end, f"{KIND.get(it.kind, it.kind)} {it.name}", it.note or
             ("" if it.kind in ("function", "def", "method", "class") else value_of(it))) for it in items]


def value_of(it):
    """A constant without a comment: its value (`const PHOTO = {w: 600, h: 300};` → = {w: 600, h: 300};)."""
    code = it.code.strip()
    m = re.match(r"(?:const|let|var)\s+[^=]+?=\s*|[\w, ]+=\s*", code) if it.kind != "statement" else None
    return clip(("= " + code[m.end():]) if m else code, 90)


# ---------- the areas (tools/codemap_areas.txt) ----------

class Area:
    def __init__(self, name, about, line):
        self.name, self.about, self.line = name, about, line
        self.places = {}                            # file -> [(token, line of the areas file)]
        self.touched = set()                        # (file, token) another area owns: listed here with a +
        self.changelog = ""

    def add(self, rel, raw, n):
        for t in TOKEN.findall(raw):
            if t.startswith("+") and len(t) > 1:
                t = t[1:]
                self.touched.add((rel, t))
            self.places[rel].append((t, n))


TOKEN = re.compile(r'\+?"[^"]*"|\+?\'[^\']*\'|\S+')
AREAS_REL = "tools/codemap_areas.txt"


def load_areas():
    areas, problems, cur, last = [], [], None, None
    for n, raw in enumerate(AREAS.read_text(encoding="utf-8").split("\n"), 1):
        if not raw.strip() or raw.startswith("#"):
            continue
        m = re.match(r"^\[([\w-]+)\]\s*(.*)$", raw)
        if m:
            if any(a.name == m.group(1) for a in areas):
                problems.append(f"{AREAS_REL}:{n}: [{m.group(1)}] is there twice")
            cur, last = Area(m.group(1), m.group(2).strip(), n), None
            areas.append(cur)
            continue
        if cur is None or (raw[0] in " \t" and last is None):
            problems.append(f"{AREAS_REL}:{n}: a line outside an area's file list: {clip(raw, 60)}")
            continue
        if raw[0] in " \t":
            cur.add(last, raw, n)
            continue
        m = re.match(r"^([\w./-]+):(.*)$", raw)
        if not m:
            problems.append(f"{AREAS_REL}:{n}: not \"path: places\": {clip(raw, 60)}")
            continue
        if m.group(1) == "changelog":
            cur.changelog, last = m.group(2).strip(), None
            continue
        last = m.group(1)
        cur.places.setdefault(last, [])
        cur.add(last, m.group(2), n)
    return areas, problems


def pick(areas, word):
    w = word.lower().strip("[]")
    for test in (lambda a: a.name == w, lambda a: a.name.startswith(w), lambda a: w in a.name,
                 lambda a: w in a.about.lower()):
        hits = [a for a in areas if test(a)]
        if hits:
            return hits
    return []


# ---------- what the app build copies (tools/app/build.py) ----------

def build_parts():
    """[(key, [(start marker, end marker)], [patched strings])] from build.py's extract(), in its order."""
    try:
        tree = ast.parse(read("tools/app/build.py") or "")
    except SyntaxError:
        return []
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "extract"), None)
    parts = []

    def calls(node):
        exs, pats = [], []
        for c in ast.walk(node):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name):
                args = [a.value if isinstance(a, ast.Constant) else None for a in c.args]
                if c.func.id == "ex" and len(args) == 2 and None not in args:
                    exs.append(tuple(args))
                elif c.func.id == "patched":
                    pats += [t.elts[0].value for t in c.args[1:] if isinstance(t, ast.Tuple) and isinstance(t.elts[0], ast.Constant)]
        return exs, pats

    for node in (fn.body if fn else []):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                parts.append((k.value, *calls(v)))
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "css":
            parts.append(("css", *calls(node.value)))
    return parts


def build_map():
    """[(key, [(board start, board end)], main.js marker line, [(patched string, board line)])]."""
    if hasattr(build_map, "cache"):
        return build_map.cache
    o, main = outline(BOARD), outline(MAIN)
    out = []
    for key, exs, pats in build_parts():
        rs = []
        for a, b in sorted(exs, key=lambda se: o.text.find(se[0])):
            i = o.text.find(a)
            j = o.text.find(b, i + len(a)) if i >= 0 else -1
            rs.append((line_of(o, i), line_of(o, j) - 1) if i >= 0 and j >= 0 else (0, 0))
        mark = find_lines(main, f"//@{key}\n") if main and key != "css" else []
        out.append((key, rs, mark[0] if mark else 0, [(p, (find_lines(o, p) or [0])[0]) for p in pats]))
    build_map.cache = out
    return out


def copied(line):
    """Which part of the board the app build copies line is in ("E21"), or ""."""
    for key, rs, _, _ in build_map():
        if any(a <= line <= b for a, b in rs):
            return key
    return ""


def show_build():
    o, app = outline(BOARD), outline("app/index.html")
    print("What tools/app/build.py copies out of the board (test/index.html) into the app: board lines → the //@E marker in\n"
          "tools/app/main.js (the CSS goes into head.html's <style>) → the line it starts on in the built app/index.html.\n"
          "A marker string that changes stops the build; a patched string that changes fails its assert.\n"
          "Rebuild after a change to any of these lines: py tools/app/build.py\n")
    ok = True
    for key, rs, mark, pats in build_map():
        inside = [it for a, b in rs for it in o.items if a <= it.start <= b]
        names = f"{inside[0].name} … {inside[-1].name} ({len(inside)} items)" if len(inside) > 1 else inside[0].name if inside else ""
        board = " + ".join(f"{a}-{b}" if a else "MARKER NOT FOUND" for a, b in rs)
        ok = ok and all(a for a, _ in rs)
        land = ""
        if app and rs and rs[0][0]:
            hit = find_lines(app, o.lines[rs[0][0] - 1])
            land = f"app {hit[0]}" if hit else "not in app (rebuild)"
        dest = f"main.js {mark}" if mark else "head.html <style>" if key == "css" else "no //@ marker!"
        print(f"  {key:<4} board {board:<22} → {dest:<17} {land:<10} {names}")
        for p, ln in pats:
            ok = ok and bool(ln)
            print(f"{'':>7}patched: board {ln or 'NOT FOUND'}: {clip(p, 100)}")
    return ok


# ---------- output ----------

CODE_ORDER = [BOARD, HEAD, MAIN, RELAY]
TOGETHER = ("README.md", "docs/history.md", "CLAUDE.md", "docs/architecture.md", "docs/code-map.md", "test/i18n.js")
EVERY = "every-change"                              # the area of what every change goes with (shown under each area)
SHARED = (BOARD, MAIN, HEAD, RELAY, "test/i18n.js", "tools/test/flows.py", "tools/test/smoke.py", "tools/test/fakesrc.py",
          "tools/test/run_test_relay.py") + TOGETHER       # files many areas share: a change there needs its own place


def i18n_rows():
    """{English text: its line in test/i18n.js}"""
    if not hasattr(i18n_rows, "cache"):
        rows = {}
        o = outline("test/i18n.js")
        for k, l in enumerate(o.lines if o else []):
            if l.startswith("  ["):
                try:
                    rows.setdefault(json.loads(l.strip().rstrip(","))[0], k + 1)
                except (ValueError, IndexError):
                    pass
        i18n_rows.cache = rows
    return i18n_rows.cache


T_CALL = re.compile(r'\bT\(\s*"((?:\\.|[^"\\])*)"')
STRING = re.compile(r'"((?:\\.|[^"\\\n]){1,120})"')


def area_texts(spans, rows=None):
    """The T("…") texts of these (file, start, end) spans and the data-t texts of head.html's markup; with `rows`, also
    the other strings that are an i18n row's English (texts that reach T() through a variable: "SUN", "NE")."""
    texts = []
    for rel, a, b in spans:
        o = outline(rel)
        for ln in range(a, b + 1):
            line = o.lines[ln - 1]
            found = T_CALL.findall(line) + (re.findall(r'data-t="([^"]*)"', line) if rel == HEAD else [])
            if rows:
                found += [s for s in STRING.findall(line) if s in rows]
            for t in found:
                t = t.replace('\\"', '"')
                if t not in texts:
                    texts.append(t)
    return texts


def changelog_notes():
    o = outline(BOARD)
    it = next((x for x in o.items if x.name == "CHANGELOG"), None)
    notes, v = [], ""
    for ln in range(it.start, it.end + 1) if it else []:
        line = o.lines[ln - 1]
        m = re.search(r'\bv:\s*"([^"]+)"', line)
        if m:
            v = m.group(1)
        for t in re.findall(r'"((?:\\.|[^"\\]){12,})"', line):
            notes.append((v, ln, t))
    return notes


def history_hits(names):
    """docs/history.md's entries that name any of these in `code`, in the file's order (newest first in each part)."""
    o = outline("docs/history.md")
    out = []
    for e in (o.items if o else []):
        toks = set()
        for s in re.findall(r"`([^`]+)`", "\n".join(o.lines[e.start - 1:e.end])):
            toks.update(re.findall(r"[\w$#.-]+", s))
            toks.update(re.findall(r"/[\w/-]+", s))
        if toks & names:
            sec = o.section_at(e.start)
            out.append((sec.name if sec else "", e))
    return out


def endpoint_calls(paths):
    """[(path, ["board:4904 fn fetchLogbook (relay >= 5)", …])]: where the board, the app and flows.py call each relay
    path, and the relay version each caller checks first."""
    out = []
    for tok in paths:
        hits = {}
        for rel, short in ((BOARD, "board"), (MAIN, "main.js"), ("tools/test/flows.py", "flows.py")):
            o = outline(rel)
            for ln in find_lines(o, tok, r"[\w-]") if o else []:
                it = o.at(ln) if o.items else None
                if (it and it.name == "CHANGELOG") or ln in o.comments or (it is None and rel.endswith(".py")):
                    continue
                key = f"{short} {where(o, ln)}" + (gates(o, it) if rel != "tools/test/flows.py" else "")
                hits.setdefault(key, []).append(ln)
        out.append((tok, [f"{k.split(' ', 1)[0]}:{ranges(v)} {k.split(' ', 1)[1]}" for k, v in hits.items()] or ["(no caller found)"]))
    return out


def show_area(a, areas):
    print(f"[{a.name}] {a.about}")
    print("Its places now (lines), file by file; + marks another area's place that this one touches too.\n"
          "Before you change a name: py tools/codemap.py --uses NAME\n")
    owner = {}                                      # (file, token) -> the areas that list it as their own
    for b in areas:
        for rel, toks in b.places.items():
            for tok, _ in toks:
                if (rel, tok) not in b.touched:
                    owner.setdefault((rel, tok), []).append(b.name)
    files = sorted(a.places, key=lambda r: (r not in CODE_ORDER, CODE_ORDER.index(r) if r in CODE_ORDER else 0,
                                            r in TOGETHER or r.startswith("tools/test/"), r))
    spans, names, together = [], set(), []
    for rel in files:
        res = []
        for tok, n in a.places[rel]:
            r = resolve(rel, tok)
            if r is None:
                res.append((0, 0, f"{tok}: no such file", "", False))
            elif not r:
                res.append((0, 0, f"{tok}: NOT FOUND (see --check)", "", False))
            mine = (rel, tok) not in a.touched
            others = [x for x in owner.get((rel, tok), []) if x != a.name]
            res += [(s, e, ("+" if not mine else "") + label + (f" [{', '.join(others)}]" if not mine and others else ""), note, mine)
                    for s, e, label, note in r or []]
            if r and mine and rel in (BOARD, MAIN, HEAD) and tok[0] not in "\"'" and (rel == HEAD or not tok.startswith(("css:", "#", ".", "@"))):
                spans += [(rel, s, e) for s, e, _, _ in r]
            if r and mine and tok[0] not in "\"'" and rel not in TOGETHER:
                names.update({tok, tok.split(".")[-1], tok.lstrip("#.@")})
        if rel in (BOARD, MAIN):                    # the top-level statements that go with its functions
            named = named_statements(rel, areas)
            for st in anchored(rel, {t for t, _ in a.places[rel]}):
                if st.start in named:
                    continue                        # an area names it itself
                mine = (rel, st.anchor) not in a.touched
                res.append((st.start, st.end, ("" if mine else "+") + f"top {st.name}", st.note or f"(goes with {st.anchor})", mine))
                if mine:
                    spans.append((rel, st.start, st.end))
        rows, last = [], None
        for s, e, label, note, mine in sorted(res, key=lambda x: (x[0], x[2])):
            m = re.match(r"(\+?(?:fn|const|let|var|class|def|top|@keyframes)) (\S+)(.*)$", label)
            kind, name = (m.group(1), m.group(2) + m.group(3)) if m else ("#", label) if re.fullmatch(r"\+?#[\w-]+", label) \
                else ("/", label) if label.startswith("/") else (label, "")
            if last and last[0] == (s, e, note, kind):
                if name not in last[1]:
                    last[1].append(name)            # one line for `let a = 1, b = 2`, ids on one line of markup, paths in a list
                continue
            run = kind.endswith("top") or kind.lstrip("+").startswith(('"', "'"))
            if run and last and last[0][3] == kind and last[1] == [name] and s <= last[0][1] + 2:
                last[0] = (last[0][0], e, last[0][2] if kind.endswith("top") else "", kind)
                last[3] += 1                        # twenty `def(…)` lines in a row, or a text on each of them: one line
                continue
            last = [(s, e, note, kind), [name], rel == BOARD and s and copied(s), 1]
            rows.append(last)
        out = []
        for (s, e, note, kind), nm, k, times in rows:
            rng = f"{s}" if e <= s else f"{s}-{e}"
            label = " ".join(nm) if kind in ("#", "/") else f"{kind} {', '.join(nm)}" if nm != [""] else kind
            label += f" ×{times}" if times > 1 else ""
            out.append(f"  {rng:>11}  {label}" + (f"  — {clip(note, 110)}" if note else "") + (f"  [app {k}]" if k else ""))
        if rel in TOGETHER or rel.startswith("tools/test/"):
            together.append([rel] + out)
        else:
            print("\n".join([rel] + out))
    calls = endpoint_calls([tok for tok, _ in a.places.get(RELAY, []) if tok.startswith("/")])
    if calls:
        print("Its endpoints' callers (the board, the app, flows.py) and the relay version they check:")
        for tok, where_ in calls:
            print(f"  {tok:<18} " + " · ".join(where_))
    print("\nGoes together")
    rows = i18n_rows()
    texts = area_texts(spans, rows)
    have = sorted((rows[t], t) for t in texts if t in rows)
    miss = [t for t in texts if t not in rows]
    if texts:
        print(f"test/i18n.js: {len(have)} row(s) of this area's texts" + (f"; {len(miss)} without a row (they show in English)" if miss else ""))
        line = "  "
        for ln, t in have:
            piece = f"{ln} {clip(t, 34)}  ·  "
            if len(line) + len(piece) > WIDTH:
                print(line.rstrip(" ·"))
                line = "  "
            line += piece
        if line.strip():
            print(line.rstrip(" ·"))
        if miss:
            print("  no row: " + " · ".join(clip(t, 40) for t in miss[:12]) + (" …" if len(miss) > 12 else ""))
    more = sorted({rows[t] for t in area_texts_of(a) if t in rows} - {ln for ln, _ in have})
    if more:
        print(f"  and {len(more)} more row(s) in the places it touches (+): lines {ranges(more)}")
    for block in together:
        print("\n".join(block))
    hist = history_hits(names)
    if hist:
        print(f"docs/history.md: {len(hist)} entr{'y' if len(hist) == 1 else 'ies'} name this area's code; the newest in each part:")
        shown = {}
        for sec, e in hist:
            if shown.get(sec, 0) < 3:
                shown[sec] = shown.get(sec, 0) + 1
                print(f"  {e.start:>9}  {clip(sec, 20):<20} {clip(e.code.lstrip('- '), 110)}")
    if a.changelog:
        try:
            rx = re.compile(a.changelog, re.I)
        except re.error as err:
            rx = None
            print(f"CHANGELOG: the pattern {a.changelog!r} doesn't work: {err}")
        hits = [(v, ln, t) for v, ln, t in changelog_notes() if rx and rx.search(t)]
        if hits:
            print(f"CHANGELOG in test/index.html (a new note goes at the top): {len(hits)} note(s) match /{a.changelog}/; the newest:")
            for v, ln, t in hits[:4]:
                print(f"  {ln:>9}  {v:<9} {clip(t, 120)}")
    every = next((b for b in areas if b.name == EVERY), None)
    if every and a is not every:
        print(f"With every change ([{EVERY}]): " + " · ".join(
            f"{rel}:{r[0][0]} {clip(tok.strip(chr(34) + chr(39)), 40)}" for rel, toks in every.places.items() for tok, _ in toks
            for r in [resolve(rel, tok)] if r))
    return True


def show_areas():
    areas, problems = load_areas()
    print(f"Fallblatt's code map: {len(areas)} areas ({AREAS_REL}). Pick yours, then py tools/codemap.py AREA (the start of\n"
          "its name will do). Also --uses NAME, --find WORD, --file PATH [WORD], --build, --diff: docs/code-map.md says when.\n")
    w = max(len(a.name) for a in areas) if areas else 0
    for a in areas:
        print(f"  {a.name:<{w}}  {a.about}")
    for p in problems:
        print(p)
    return True


def source_files():
    try:
        files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split("\n")
    except (OSError, subprocess.CalledProcessError):
        files = [p.relative_to(REPO).as_posix() for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [f for f in files if f and not SKIP_USES.match(f) and not f.startswith(".claude/")]


def uses(name, limit=250):
    """Every line that mentions name, in every source, test and doc file (not the copies, generated or parked files).
    A .class is looked for in the code only: in the docs its word is mostly prose."""
    bare = name.split(".", 1)[1] if re.match(r"^(Handler|Spot)\.\w+$", name) else name
    cls = bool(re.fullmatch(r"\.[\w-]+", bare))
    bare = bare[1:] if re.fullmatch(r"[#.][\w-]+", bare) else bare
    edge = r"[\w$-]" if name[0] in "#./" else r"[\w$]"
    rx = re.compile((f"(?<!{edge})" if re.match(r"[\w$]", bare) else "") + re.escape(bare) + (f"(?!{edge})" if re.search(r"[\w$]$", bare) else ""))
    if cls:                                         # .times: as a class, not the word (.x, class="… x", classList.add("x"))
        w = re.escape(bare)
        rx = re.compile(rf"\.{w}(?![\w-])|class(?:Name)?=\\?[\"'][^\"'>]*(?<![\w-]){w}(?![\w-])|classList\.\w+\([^)]*[\"']{w}[\"']|[\"']{w}[\"']")
    total, shown, more = 0, 0, []
    for rel in source_files():
        text = None if cls and rel.endswith(".md") else read(rel)
        if not text or not rx.search(text):
            continue
        o = outline(rel) if rel.endswith((".html", ".js", ".py", ".md")) else None
        lines = o.lines if o else text.split("\n")
        hits = []
        for m in rx.finditer(text):
            ln = line_of(o, m.start()) if o else text.count("\n", 0, m.start()) + 1
            if hits and hits[-1][0] == ln:
                continue
            col = m.start() - (text.rfind("\n", 0, m.start()) + 1)
            lo = max(0, col - 50)
            hits.append((ln, where(o, ln) if o else "", ("…" if lo else "") + lines[ln - 1][lo:lo + 110].strip()))
        total += len(hits)
        if shown >= limit:
            more.append(f"{rel} ({len(hits)})")
            continue
        print(f"{rel} ({len(hits)})")
        for ln, wh, snip in hits:
            if shown >= limit:
                break
            shown += 1
            print(f"  {ln:>5}  {clip(wh, 26):<26} {clip(snip, 112)}")
    if total > shown:
        print(f"… {total - shown} more lines not shown" + (f" (also in {', '.join(more)})" if more else "") +
              ": narrow it down with grep -n over one file")
    if not total:
        print(f"Nothing mentions {name}.")
    return True


def find(word, limit=150):
    w = word.lower()
    areas, _ = load_areas()
    out = [f"  area [{a.name}]  {a.about}" for a in areas if w in a.name or w in a.about.lower()]
    code = [f for f in source_files() if f.endswith((".py", ".js", ".html")) and f not in CODE_ORDER]
    for rel in CODE_ORDER + code:
        o = outline(rel)
        if not o:
            continue
        for s in o.sections:
            if w in s.name.lower():
                out.append(f"  {rel}:{s.start}-{s.end}  § {clip(s.name, 100)}")
        for it in o.items:
            if w in it.name.lower() or w in it.note.lower():
                out.append(f"  {rel}:{it.lines()}  {KIND.get(it.kind, it.kind)} {it.name}" + (f"  — {clip(it.note, 100)}" if it.note else ""))
        keys = {}
        for c in o.css:
            if w in c.name.lower() or w in c.note.lower():
                keys.setdefault(c.name, []).append(c)
        for k, cs in keys.items():
            out.append(f"  {rel}:{ranges([c.start for c in cs])}  css {k}" + (f"  — {clip(cs[0].note, 90)}" if cs[0].note else ""))
    for line in out[:limit]:
        print(line)
    if len(out) > limit:
        print(f"… {len(out) - limit} more: try a longer word")
    if not out:
        print(f"Nothing is named or commented {word!r}. Try --uses {word}")
    return True


def show_file(rel, word=None):
    o = outline(rel)
    if o is None:
        print(f"No such file: {rel}")
        return False
    w = (word or "").lower()
    rows = []
    for s in o.sections:
        if not w or w in s.name.lower():
            rows.append((s.start, 0, f"{s.start}-{s.end}", f"§ {clip(s.name, 110)}"))
    same = {}                                       # `let a = 1, b = 2`: one row
    for it in o.items:
        if not w or w in it.name.lower() or w in it.note.lower():
            same.setdefault((it.start, it.kind), []).append(it)
    for (start, kind), its in same.items():
        it, k = its[0], copied(start) if rel == BOARD else ""
        rows.append((start, 1, it.lines(), f"  {KIND.get(kind, kind)} {', '.join(x.name for x in its)}" +
                     (f"  — {clip(it.note, 90)}" if it.note else "") + (f"  [app {k}]" if k else "")))
    keys = {}
    for c in o.css:
        if not w or w in c.name.lower() or w in c.note.lower():
            keys.setdefault(c.name, []).append(c)
    for k, cs in keys.items():
        rows.append((cs[0].start, 1, ranges([c.start for c in cs]), f"  css {k}" + (f"  — {clip(cs[0].note, 80)}" if cs[0].note else "")))
    for a, b in o.markup:
        ids = sorted({i for i, ls in ids_of(o).items() for ln in ls if a <= ln <= b and (not w or w in i.lower())})
        if ids:
            rows.append((a, 0, f"{a}-{b}", "markup: " + " ".join("#" + i for i in ids)))
    print(f"{rel}: {len(o.lines)} lines, {len(o.items)} items, {len(o.css)} CSS rules" + (f"; those matching {word!r}" if w else ""))
    for _, _, rng, text in sorted(rows, key=lambda r: (r[0], r[1])):
        print(f"{rng:>11}  {text}")
    return True


# ---------- the check (smoke.py --syntax) ----------

def neighbours(o, it, claimed):
    """The areas of the nearest items above and below that have one (where a new item probably goes)."""
    i = o.items.index(it)
    near = []
    for step in (-1, 1):
        j = i + step
        while 0 <= j < len(o.items) and not claimed.get(o.items[j].name):
            j += step
        if 0 <= j < len(o.items):
            near += [a for a in claimed[o.items[j].name] if a not in near]
    return near


def check(quiet=False):
    """Every top-level function, const and class of the board, main.js and the relay, and every CSS rule of the board and
    head.html, is in an area; every place an area names is still there. True when all is well."""
    areas, problems = load_areas()
    places, gone = 0, {}
    for a in areas:
        for rel, toks in a.places.items():
            for tok, n in toks:
                places += 1
                r = resolve(rel, tok)
                if r is None:
                    problems.append(f"{AREAS_REL}:{n} [{a.name}]: there is no file {rel}")
                    break
                if not r:
                    gone.setdefault(rel, []).append(tok)
                    problems.append(f"{AREAS_REL}:{n} [{a.name}]: {rel} has no {tok} any more: rename or remove it there")
                elif len(r) > 1 and all(label.startswith("top ") for _, _, label, _ in r):
                    problems.append(f"{AREAS_REL}:{n} [{a.name}]: {rel} has {len(r)} top-level statements named {tok}: "
                                    f"name the one you mean by a text in it (\"…\")")
    for rel in CHECKED:
        o = outline(rel)
        claimed = {}
        for a in areas:
            for tok, _ in a.places.get(rel, []):
                claimed.setdefault(tok, []).append(a.name)
        for it in o.items:
            if it.kind not in ("statement", "section", "entry") and it.name not in claimed:
                near = neighbours(o, it, claimed)
                was = difflib.get_close_matches(it.name, gone.get(rel, []), n=1, cutoff=.7)
                hint = (f" (renamed from {was[0]}? then rename it there)" if was else
                        f" (its neighbours are in {', '.join('[' + x + ']' for x in near[:3])})" if near else "")
                problems.append(f"{rel}:{it.start}: {KIND.get(it.kind, it.kind)} {it.name} is in no area: add it to the {rel}: line"
                                f" of the area it belongs to in {AREAS_REL}{hint}")
    for rel in CHECKED_CSS:
        o = outline(rel)
        toks = [tok[4:] if tok.startswith("css:") else tok for a in areas for tok, _ in a.places.get(rel, [])
                if tok.startswith(("css:", "#", ".", "@"))]
        seen = set()
        for c in o.css:
            if c.name in seen:
                continue
            ok = c.name in toks if c.kind == "keyframes" else any(t[0] != "@" and css_match(t, c.name) for t in toks)
            if not ok:
                seen.add(c.name)
                tok = c.name if c.name[0] in "#.@" else "css:" + c.name
                problems.append(f"{rel}:{c.start}: the CSS of {c.name} is in no area: add {tok} to the {rel}: line of its area"
                                f" in {AREAS_REL}")
    for p in problems:
        print(p)
    if not quiet or problems:
        print(f"code map: {len(areas)} areas, {places} places, all there and nothing left out" if not problems else
              f"code map: {len(problems)} thing(s) to fix in {AREAS_REL} (docs/code-map.md says how)")
    return not problems


# ---------- what a change touched (--diff) ----------

SKIP_DIFF = re.compile(r"^(index\.html|i18n\.js|sounds\.js|app/index\.html|test/sounds\.js)$")   # copies and generated


def diff_lines(a, b=None):
    """{file: (lines changed in the new version, lines only removed from the old one)} from commit a to b (or the files now)."""
    r = subprocess.run(["git", "diff", "-U0", "--no-color", "--no-renames", a] + ([b] if b else []) + ["--"], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(f"git diff {a} {b or ''}: {r.stderr.strip()}")
    files, old, cur = {}, None, None
    for line in r.stdout.split("\n"):
        if line.startswith("--- "):
            old = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else old
            files.setdefault(cur, ([], []))
        else:
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m and cur:
                a0, an, b0, bn = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)
                files[cur][0].extend(range(b0, b0 + bn) if bn else [])
                files[cur][1].extend(range(a0, a0 + an) if an and not bn else [])
    return {f: v for f, v in files.items() if f and not SKIP_DIFF.match(f)}


def places_at(o, ln):
    """The places line ln of an outline is part of: [(kind, name[, its text[, the function a statement goes with]])]."""
    rel, n = o.rel, len(o.lines)
    line = o.lines[ln - 1] if 0 < ln <= n else ""
    if rel == "test/i18n.js":
        k = ln
        while k < n and o.lines[k - 1].lstrip().startswith("//") and ln > 5:
            k += 1                                  # a comment between the rows: the row under it
        try:
            return [("i18n", json.loads(o.lines[k - 1].strip().rstrip(","))[0])] if o.lines[k - 1].startswith("  [") else [("file", rel)]
        except (ValueError, IndexError):
            return [("line", clip(line, 60))]
    if rel.endswith(".md"):
        it = o.at(ln) if o.items else None
        if it and it.kind == "entry":
            return [("history" if rel == "docs/history.md" else "entry", it.code, "\n".join(o.lines[it.start - 1:it.end]))]
        s = o.section_at(ln)
        a, b = ln, ln                               # a paragraph: the lines around it up to blank ones
        while a > 1 and o.lines[a - 2].strip() and not o.lines[a - 2].startswith("#"):
            a -= 1
        while b < n and o.lines[b].strip() and not o.lines[b].startswith("#"):
            b += 1
        head = o.lines[s.start - 1] if s else ""
        return [("section", s.name if s else "top", head + "\n" + "\n".join(o.lines[a - 1:b]))]
    c = o.css_at(ln) if o.css else None
    if c is None and o.css and not (o.items and o.at(ln)):
        c = next((x for x in o.css if ln < x.start <= ln + 4), None)    # a comment above a rule: that rule
    if c:
        return [(c.kind, c.name, c.code)]
    if any(a <= ln <= b for a, b in o.markup):
        for k in range(ln, max(0, ln - 12) if line[:1] in " \t" else ln - 1, -1):   # the element with an id it is in
            ids = re.findall(r'\bid="([\w-]+)"', o.lines[k - 1])
            if ids:
                return [("ids", " ".join(ids) if k == ln else ids[-1])]
        return [("markup", clip(line, 60), line)]
    it = o.at(ln) if o.items else None
    if it is None:                                  # a comment or blank line: the item it stands above
        nxt = next((x for x in o.items if x.start > ln), None)
        if nxt and all(not o.lines[k - 1].strip() or k in o.comments or o.lines[k - 1].lstrip().startswith("#")
                       for k in range(ln, nxt.start)):
            it = nxt
    if it is None:
        if rel.endswith(".py"):
            return [("file", rel)]                  # the docstring or the imports
        s = o.section_at(ln)
        return [("section", s.name)] if s else [("line", clip(line, 60))]
    if it.name == "CHANGELOG":
        return [("changelog", t) for t in re.findall(r'"((?:\\.|[^"\\]){12,})"', line)]   # not the {v: …} lines
    if it.kind == "statement":
        return [("statement", it.name, "\n".join(o.lines[it.start - 1:it.end]), it.anchor)]
    out = [(it.kind, it.name)]
    if rel == RELAY and re.search(r"^\w+_PATHS = |path not in \(", line):
        return [("paths", line)]                    # a list of paths: the endpoints named in it
    if rel.endswith(".py") and it.end - it.start > 40:     # a long function: which endpoint or check in it
        for k in range(ln, it.start - 1, -1):
            s = o.lines[k - 1]
            m = re.search(r'path(?:\.startswith\(| ==) ?"(/[^"]*)"|re\.fullmatch\(r"(/[\w-]+/)', s)
            c = re.search(r"\b([A-Z_]+)\.match\(path\)", s)
            if c:                                   # `m = AIRCRAFT.match(path)`: the path in that pattern
                pat = next((x.code for x in o.items if x.name == c.group(1)), "")
                c = re.search(r"\^(/[\w-]+/)", pat)
            if m or c:
                return [("endpoint", (m.group(1) or m.group(2)) if m else c.group(1))]   # the endpoint, not the handler
            if rel.startswith("tools/test/") and re.match(r"\s+# ", s) and not re.match(r"\s+# ", o.lines[k - 2]):
                e = k
                while e < n and re.match(r"\s+# ", o.lines[e]):
                    e += 1                          # the whole comment: two checks may stand one under the other
                return [("check", s.strip(), "\n".join(o.lines[k - 1:e]))]
    return out


def anchored(rel, names):
    """The top-level statements that go with these functions and constants (the one each comes after)."""
    o = outline(rel)
    return [it for it in (o.items if o else []) if it.kind == "statement" and it.anchor in names and it.name not in names]


def named_statements(rel, areas):
    """The start lines of the top-level statements some area names itself (by its name, or a text in it)."""
    key = ("named", rel)
    if key not in _OUTLINES:
        o, starts = outline(rel), set()
        for a in areas:
            for tok, _ in a.places.get(rel, []):
                for s, e, label, _ in resolve(rel, tok) or []:
                    st = o.at(s) if tok[0] in "\"'" else None
                    if label.startswith("top ") or (st and st.kind == "statement"):
                        starts.add(st.start if st else s)
        _OUTLINES[key] = starts
    return _OUTLINES[key]


def area_texts_of(a):
    """The T() and data-t texts of every place an area lists (its own and the ones it touches)."""
    if not hasattr(a, "_texts"):
        spans = []
        for rel in (BOARD, MAIN, HEAD):
            toks = [tok for tok, _ in a.places.get(rel, [])]
            for tok in toks:
                if tok[0] not in "\"'" and (rel == HEAD or not tok.startswith(("css:", "#", ".", "@"))):
                    spans += [(rel, s, e) for s, e, _, _ in resolve(rel, tok) or []]
            spans += [(rel, it.start, it.end) for it in anchored(rel, set(toks))]
        a._texts = set(area_texts(spans, i18n_rows()))
    return a._texts


def area_names(a):
    if not hasattr(a, "_names"):
        a._names = set()
        for rel, toks in a.places.items():
            for tok, _ in toks:
                if tok[0] not in "\"'" and rel not in TOGETHER and (rel, tok) not in a.touched:
                    a._names.update({tok, tok.split(".")[-1], tok.lstrip("#.@")})
    return a._names


def lists(a, rel, kind, name, text="", anchor=None, line=""):
    """Does area a list this place? `text`: the place's own lines (a rule's selector, a statement, a bullet), for places
    the areas name by a quoted text; `anchor`: the function a top-level statement goes with; `line`: the changed line,
    which a quoted text the area names may point at."""
    toks = [t for t, _ in a.places.get(rel, [])]
    quoted = [t[1:-1] for t in toks if t[0] in "\"'"]
    text = text or name
    if kind == "file" or (rel not in SHARED and rel in a.places):
        return rel in a.places                      # a small file of the area's own: all of it
    if line and (any(q and q in line for q in quoted) or
                 any(re.search(re.escape(t) + r"(?![\w-])", line) for t in toks if t[0] == "/" and len(t) > 2)):
        return True
    if kind == "ids":
        return any("#" + i in toks for i in name.split())
    if kind == "css":
        named = mentions(text)
        return any(css_match(t[4:] if t.startswith("css:") else t, name) for t in toks if t.startswith(("css:", "#", "."))) or \
            any(set(css_parts(t)) <= named for t in toks if re.fullmatch(r"([#.][\w-]+)+", t))
    if kind == "keyframes":
        return name in toks
    if kind == "id":
        return "#" + name in toks
    if kind == "i18n":
        return name in area_texts_of(a)
    if kind == "changelog":
        return bool(a.changelog and re.search(a.changelog, name, re.I))
    if kind == "paths":
        return any(re.search(re.escape(t) + r"(?![\w-])", text) for t in toks if t.startswith("/"))
    if kind == "history":
        found = set()
        for s in re.findall(r"`([^`]+)`", text):
            found.update(re.findall(r"[\w$#.-]+", s))
            found.update(re.findall(r"/[\w/-]+", s))
        return bool(found & area_names(a)) or any(q in text for q in quoted)
    if kind == "endpoint":
        return name in toks or name in quoted
    if name in toks or (kind == "statement" and anchor and anchor in toks):
        return True
    return any(q and q in text for q in quoted)


def exists(o, kind, name, text=None):
    """Is the place still there in this outline (a removed one needs no area)? A CSS rule by its selector (`text`)."""
    if o is None:
        return True
    if kind == "i18n":
        return any(l.startswith("  [" + json.dumps(name, ensure_ascii=False)) for l in o.lines)
    if kind in ("css", "keyframes"):
        return any(c.name == name and (text is None or c.code == text) for c in o.css)
    if kind == "id":
        return name in ids_of(o)
    if kind == "ids":
        return any(i in ids_of(o) for i in name.split())
    if kind in ("function", "const", "let", "var", "class", "def", "method", "assign"):
        return any(it.name == name for it in o.items)
    if kind in ("statement", "entry", "history"):           # its first line, word for word
        first = name.rstrip("…").strip()
        return any(first in l for l in o.lines)
    return True


def diff_report(a_rev, b_rev=None):
    """[(file, line, kind, name, [areas], its text)] for every place the change from a_rev to b_rev (or the files now)
    touched; a place it removed has ["removed"]."""
    areas, _ = load_areas()
    out = []
    for rel, (new, gone) in sorted(diff_lines(a_rev, b_rev).items()):
        found = {}                                  # (kind, name) -> [first line, text, anchor, changed lines, removed?]
        newest = outline(rel, b_rev) if rel.endswith((".html", ".js", ".py", ".md")) else None
        for rev, lines in ((b_rev, new), (a_rev, gone)):
            o = outline(rel, rev) if rel.endswith((".html", ".js", ".py", ".md")) else None
            for ln in lines:
                if o is not None and 0 < ln <= len(o.lines) and not o.lines[ln - 1].strip():
                    continue                        # a blank line is no place
                for p in (places_at(o, ln) if o is not None else [("file", rel)]):
                    kind, name, text, anchor = (tuple(p) + (None, None))[:4]
                    if text is None and o is not None and kind in ("line", "markup"):
                        text = o.lines[ln - 1]
                    f = found.setdefault((kind, name) if kind != "css" else (kind, name, text),
                                         [ln, text, anchor, [], rev == a_rev and not exists(newest, kind, name, text)])
                    f[3].append(o.lines[ln - 1] if o is not None and 0 < ln <= len(o.lines) else "")
        for (kind, name, *_), (ln, text, anchor, changed, removed) in found.items():
            hit = ["removed"] if removed else [a.name for a in areas if lists(a, rel, kind, name, text, anchor, "\n".join(changed))]
            out.append((rel, ln, kind, name, hit, text))
    return out


def show_diff(a_rev, b_rev=None):
    rows = diff_report(a_rev, b_rev)
    if not rows:
        print("No changes.")
        return True
    count = {}
    for *_, hit, _ in rows:
        for h in hit:
            count[h] = count.get(h, 0) + 1
    print(f"The places changed since {a_rev}{' up to ' + b_rev if b_rev else ''}, and the areas that list them.\n"
          f"Areas touched: {', '.join(f'{k} ({v})' for k, v in sorted(count.items(), key=lambda x: -x[1]))}\n"
          "Run py tools/codemap.py AREA for each: what else of the area goes with these changes?\n")
    last = None
    for rel, ln, kind, name, hit, _ in rows:
        if rel != last:
            print(rel)
            last = rel
        print(f"  {ln:>6}  {KIND.get(kind, kind)} {clip(name, 70)}  " + (f"[{', '.join(hit)}]" if hit else "IN NO AREA"))
    missing = [r for r in rows if not r[4] and r[2] not in ("line", "section", "markup", "file")]
    if missing:
        print(f"\n{len(missing)} changed place(s) in no area: add them to {AREAS_REL} (see docs/code-map.md)")
    return True


def main(argv):
    if len(argv) < 2:
        return show_areas()
    if argv[1] == "--diff":
        return show_diff(argv[2] if len(argv) > 2 else "origin/main", argv[3] if len(argv) > 3 else None)
    cmd = argv[1]
    if cmd == "--check":
        return check()
    if cmd == "--build":
        return show_build()
    if cmd in ("--uses", "--find", "--file") and len(argv) < 3 or cmd in ("-h", "--help"):
        print(__doc__)
        return cmd in ("-h", "--help")
    if cmd == "--uses":
        return uses(argv[2])
    if cmd == "--find":
        return find(" ".join(argv[2:]))
    if cmd == "--file":
        rel = argv[2].replace("\\", "/")
        return show_file(rel[2:] if rel.startswith("./") else rel, argv[3] if len(argv) > 3 else None)
    if cmd.startswith("-"):
        print(__doc__)
        return False
    areas, _ = load_areas()
    hits = pick(areas, cmd)
    if len(hits) == 1:
        return show_area(hits[0], areas)
    print(f"No area {cmd!r}." if not hits else f"{cmd!r} could be: " + ", ".join(a.name for a in hits))
    if not hits:
        show_areas()
    return False


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        ok = main(sys.argv)
        sys.stdout.flush()
    except BrokenPipeError:                         # `| head`: the rest isn't wanted
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        ok = True
    sys.exit(0 if ok else 1)
