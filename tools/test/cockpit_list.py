"""List every control of Settings (the cockpit plates) on the board, the phone app and the light version, in order:
each plate's title and columns, then each cell's label, width and controls (data-k and the special hooks such as
data-loc, data-live, data-places, data-gq, data-lsave, data-favs, data-act). Made for #47 (1.53.2): run it before and
after a change to the shared COCKPIT definition and compare (no difference = nothing got lost on the way).

    py tools/test/cockpit_list.py [--port 8696] [--html DIR] > before.txt

Needs the test relay running (run_test_relay.py, same port) and Playwright.
"""
import asyncio
import hashlib
import sys
from pathlib import Path

from playwright.async_api import async_playwright

PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8096
HTML_DIR = sys.argv[sys.argv.index("--html") + 1] if "--html" in sys.argv else ""   # also write each one's markup there
BASE = f"http://localhost:{PORT}"

DUMP = r"""() => {
  const out = [];
  for (const p of document.querySelectorAll("#cockpit .plate")) {
    const h = p.querySelector("h3");
    out.push(`PLATE ${h ? h.textContent : "?"} cols=${p.style.getPropertyValue("--cols") || "-"}`);
    for (const c of p.querySelectorAll(":scope > .inst, :scope > p, :scope > .acts, :scope > .acts > *")) {
      if (!c.classList.contains("inst")) {
        if (c.matches("[data-act]")) out.push(`  act ${c.dataset.act} "${c.textContent}"`);
        continue;
      }
      const cap = c.querySelector(":scope > span:last-child");
      out.push(`  CELL "${cap ? cap.textContent : ""}" class="${c.className}" span=${c.style.getPropertyValue("--span") || "-"} hint=${c.dataset.hint ? "y" : "n"}`);
      for (const el of c.querySelectorAll("*")) {
        const ds = Object.keys(el.dataset).filter(k => k !== "hint");
        if (!ds.length) continue;
        out.push(`    ${el.tagName.toLowerCase()}.${el.className || "-"} ` + ds.map(k => el.dataset[k] ? `${k}=${el.dataset[k]}` : k).join(" ") +
          (el.hidden ? " hidden" : "") + (el.disabled ? " disabled" : ""));
      }
    }
  }
  const save = document.querySelector("#saveBtn, #cockpit [data-act=save]");
  out.push(`HTML ${document.querySelector("#cockpit").innerHTML.length}`);
  out.push(`SAVE ${save ? save.id || "plate" : "none"} pressed=${save && save.getAttribute("aria-pressed")}`);
  return out;
}"""


async def dump(p, name, url, open_settings, phone):
    opts = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True} if phone else {"viewport": {"width": 1920, "height": 1080}}
    ctx = await p.new_context(**opts)
    await ctx.add_cookies([{"name": "overhead", "value": "test-device", "domain": "localhost", "path": "/"}])
    page = await ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto(url)
    await page.wait_for_timeout(4000)
    await open_settings(page)
    await page.wait_for_timeout(1500)
    lines = await page.evaluate(DUMP)
    html = await page.evaluate("document.querySelector('#cockpit').innerHTML")
    if HTML_DIR:
        (Path(HTML_DIR) / f"{name}.html").write_text(html.replace("><", ">\n<"), encoding="utf-8")
    lines.append("HTML sha1 " + hashlib.sha1(html.encode()).hexdigest())
    print(f"=== {name}")
    print("\n".join(lines))
    if errors:
        print("PAGE ERRORS:", errors)
    await ctx.close()


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()

        async def board(page):
            await page.keyboard.press("s")

        async def app(page):
            await page.evaluate("document.querySelector('[data-tab=settings]').click()")
        await dump(b, "board", f"{BASE}/test/", board, False)
        await dump(b, "app", f"{BASE}/app/", app, True)
        await dump(b, "light", f"{BASE}/light/", app, True)
        await b.close()

asyncio.run(main())
