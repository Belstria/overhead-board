"""Build glass/index.html: the glass version (1.71, designed with Gemini: "Glasshouse"), a light, map-first phone app.
It is the light version (tools/light/: the phone app's code without the split flaps) with a layer on top: glass.js's
regions replace light.js's where it has them (always its `extra` region: the full-screen map, the floating plane card,
the pages that slide over the map), and glass.css comes after light.css. So it keeps every feature of the app.

    py tools/glass/build.py                    # test/index.html -> glass/index.html

Don't edit glass/index.html by hand. Rebuild it whenever the app or the light version is rebuilt.
"""
import sys
from pathlib import Path

GP = Path(__file__).parent
REPO = GP.parent.parent
sys.path.insert(0, str(REPO / "tools" / "app"))
import build as app  # noqa: E402  (tools/app/build.py)


def patched(text, *pairs):
    for a, b in pairs:
        if text.count(a) != 1:
            raise SystemExit(f"head.html changed: {a[:70]!r} should be there once")
        text = text.replace(a, b)
    return text


app.assets.stamp()
E, css = app.extract((REPO / "test" / "index.html").read_text(encoding="utf-8"))
head = (REPO / "tools" / "app" / "head.html").read_text(encoding="utf-8")
ui = head[head.index("<script>/*@ui*/"):]
ui = ui[:ui.index("</script>\n") + len("</script>\n")]
head = patched(head,
               ("<title>Fallblatt</title>", "<title>Fallblatt Glass</title>"),
               ('<meta name="theme-color" content="#141517">', '<meta name="theme-color" content="#faf9f6">'),
               ('href="manifest.webmanifest"', 'href="../app/manifest.webmanifest"'),
               ('href="icon-192.png"', 'href="../app/icon-192.png"'),
               ('href="apple-touch-icon.png"', 'href="../app/apple-touch-icon.png"'),
               (ui, ""),
               ('<p class="brandline">Fallblatt</p>', '<p class="brandline">Fallblatt</p>'),
               ('data-t="Turn the knobs and flip the switches, then press Save.">Turn the knobs and flip the switches, then press Save.',
                'data-t="Change the settings, then press Save.">Change the settings, then press Save.'))
regions = {name: code for name, code in app.REGION.findall((REPO / "tools" / "light" / "light.js").read_text(encoding="utf-8"))}
regions.update({name: code for name, code in app.REGION.findall((GP / "glass.js").read_text(encoding="utf-8"))})
out = REPO / "glass" / "index.html"
out.parent.mkdir(exist_ok=True)
app.assemble(head, (REPO / "tools" / "app" / "main.js").read_text(encoding="utf-8"), E, css, out, regions=regions,
             extra_css=(REPO / "tools" / "light" / "light.css").read_text(encoding="utf-8") + "\n" + (GP / "glass.css").read_text(encoding="utf-8"))
