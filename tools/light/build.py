"""Build light/index.html: the light version of the phone app, without split flaps. It is the phone app (tools/app/:
head.html, main.js and the board's code it copies), with the parts main.js marks //@L:name ... //@L:end replaced by
light.js here (plain fields in place of the flap engine, no metal, its own Settings), light.css added after the
app's styles, and a few strings of head.html changed below. So it follows the app and the test board by itself.

    py tools/light/build.py                    # test/index.html -> light/index.html

Don't edit light/index.html by hand. Rebuild it whenever the app is rebuilt (the check on pull requests does both).
"""
import sys
from pathlib import Path

LP = Path(__file__).parent
REPO = LP.parent.parent
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
               ("<title>Fallblatt</title>", "<title>Fallblatt Light</title>"),
               ('<meta name="theme-color" content="#141517">', '<meta name="theme-color" content="#0b0b0c">'),
               ('href="manifest.webmanifest"', 'href="../app/manifest.webmanifest"'),           # the app's: the same app
               ('href="icon-192.png"', 'href="../app/icon-192.png"'),
               ('href="apple-touch-icon.png"', 'href="../app/apple-touch-icon.png"'),
               (ui, ""),                                                                     # no "open the light version"
               ('<p class="brandline">Fallblatt</p>', '<p class="brandline">Fallblatt Light</p>'),
               ('data-t="Turn the knobs and flip the switches, then press Save.">Turn the knobs and flip the switches, then press Save.',
                'data-t="Change the settings, then press Save.">Change the settings, then press Save.'))
regions = {name: code for name, code in app.REGION.findall((LP / "light.js").read_text(encoding="utf-8"))}
app.assemble(head, (REPO / "tools" / "app" / "main.js").read_text(encoding="utf-8"), E, css, REPO / "light" / "index.html",
             regions=regions, extra_css=(LP / "light.css").read_text(encoding="utf-8"))
