"""Comments out of the built app (1.129.21, to-do #305): every phone downloads app/index.html again with each version,
and about a quarter of it was comments. Only comments go: no renaming, no other squeezing, so the connection log and
stack traces keep their names. Blank lines left by a removed comment go too; line breaks between code stay (JavaScript's
automatic semicolons depend on them).

    strip_page(html)   the page: comments in its inline scripts, its <style> blocks and its HTML
    strip_js(src)      one script's comments, strings, template literals and regular expressions kept as they are

Checked against a real JavaScript parser (tools/test/strip_check.py): the same tokens, the same line breaks between
them, before and after.
"""
import re

# After these a "/" starts a regular expression, not a division
_RE_WORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case", "do", "else", "yield",
             "await"}
_IDENT = re.compile(r"[A-Za-z0-9_$\u0080-￿]")


def strip_js(src):
    out = []                 # pieces of the result
    n, i = len(src), 0
    prev = ""                # the last significant token's kind: "id" (word, number), ")" "]" "}" or "op"
    word = ""                # the last word, if prev is "id"
    stack = []               # template literal nesting: brace depth at each ${

    def drop_comment(end, keep_break):
        """Remove a comment ending at `end`. If it was alone on its line, the line goes."""
        nonlocal i
        # trailing spaces before it on the output line
        while out and out[-1] in (" ", "\t"):
            out.pop()
        at_line_start = not out or out[-1].endswith("\n")
        i = end
        if keep_break and not at_line_start:
            out.append("\n")
        elif not at_line_start and i < n and src[i] not in "\r\n":
            out.append(" ")  # a/**/b stays two tokens
        if at_line_start:    # the whole line was the comment (and spaces): its line break goes too
            while i < n and src[i] in " \t":
                i += 1
            if i < n and src[i] == "\n":
                i += 1

    def template():
        """Copy a template literal's text from i (after ` or }) up to and including ` or ${."""
        nonlocal i
        while i < n:
            c = src[i]
            if c == "\\":
                out.append(src[i:i + 2]); i += 2; continue
            if c == "`":
                out.append(c); i += 1; return "end"
            if c == "$" and src.startswith("${", i):
                out.append("${"); i += 2; return "expr"
            out.append(c); i += 1
        raise ValueError("an unclosed template literal")

    while i < n:
        c = src[i]
        if c in " \t\r\n":
            out.append(c); i += 1; continue
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            drop_comment(n if j < 0 else j, False)
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise ValueError("an unclosed /* comment")
            drop_comment(j + 2, "\n" in src[i:j])
            continue
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 1
                elif src[j] == "\n":
                    raise ValueError("a line break inside a string at %d" % i)
                j += 1
            out.append(src[i:j + 1]); i = j + 1; prev = "id"; word = ""
            continue
        if c == "`":
            out.append(c); i += 1
            if template() == "expr":
                stack.append(0)
            prev = "id"; word = ""
            continue
        if c == "/":       # a regular expression or a division
            regex = prev in ("", "op") or (prev == "id" and word in _RE_WORDS)
            if regex:
                j, cls = i + 1, False
                while j < n:
                    d = src[j]
                    if d == "\\":
                        j += 2; continue
                    if d == "\n":
                        raise ValueError("a line break inside a regular expression at %d" % i)
                    if d == "[":
                        cls = True
                    elif d == "]":
                        cls = False
                    elif d == "/" and not cls:
                        break
                    j += 1
                j += 1
                while j < n and _IDENT.match(src[j]):
                    j += 1
                out.append(src[i:j]); i = j; prev = "id"; word = ""
                continue
            out.append(c); i += 1; prev = "op"
            continue
        if _IDENT.match(c):
            j = i + 1
            while j < n and _IDENT.match(src[j]):
                j += 1
            if c.isdigit() or c == ".":
                pass
            word = src[i:j]
            out.append(word); i = j; prev = "id"
            continue
        if c == "{" and stack:
            stack[-1] += 1
        if c == "}" and stack:
            if stack[-1] == 0:          # back into the template literal
                stack.pop()
                out.append(c); i += 1
                if template() == "expr":
                    stack.append(0)
                prev = "id"; word = ""
                continue
            stack[-1] -= 1
        out.append(c); i += 1
        prev = c if c in ")]}" else "op"
        word = ""
    if stack:
        raise ValueError("an unclosed ${ in a template literal")
    return "".join(out)


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_PART = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)|(<style\b[^>]*>)(.*?)(</style>)", re.S | re.I)


def _strip_css(css):
    # a comment alone on its line takes the line with it; one after a rule leaves the rule
    css = re.sub(r"^[ \t]*/\*.*?\*/[ \t]*\n", "", css, flags=re.S | re.M)
    return re.sub(r"[ \t]*/\*.*?\*/", "", css, flags=re.S)


def _strip_html(html):
    html = re.sub(r"^[ \t]*<!--.*?-->[ \t]*\n", "", html, flags=re.S | re.M)
    return _HTML_COMMENT.sub("", html)


def strip_page(html):
    out, at = [], 0
    for m in _PART.finditer(html):
        out.append(_strip_html(html[at:m.start()]))
        if m.group(1):
            body = m.group(2)
            if "src=" not in m.group(1) and "json" not in m.group(1).lower():
                body = strip_js(body)
            out.append(m.group(1) + body + m.group(3))
        else:
            out.append(m.group(4) + _strip_css(m.group(5)) + m.group(6))
        at = m.end()
    out.append(_strip_html(html[at:]))
    return "".join(out)
