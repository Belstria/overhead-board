"""Screenshots of a board or the phone app, for checking a change before it goes out.

Needs Playwright once:  py -m pip install playwright  and  py -m playwright install chromium

    py tools/test/shoot.py URL OUT STEP...

OUT is a file name prefix (shot:now writes OUT-now.png). Steps run in order:
    wait:MS          wait this many milliseconds
    key:NAME         press a key (t, l, r, s, Escape, Digit3, ...)
    click:X,Y        click at a point          tap:CSS      click an element, e.g. tap:[data-tab=today]
    scroll:Y         scroll the page to Y      js:EXPR      print the value of a JavaScript expression
    shot:NAME        screenshot                full:NAME    whole-page screenshot (the phone app scrolls)
    clip:X,Y,W,H,NAME  screenshot of part of the page
    seq:SECONDS      watch which page button is lit, once a second, and print the order
Set PHONE=390x844 (or another size) for a phone: 3x pixels, touch, an iPhone browser. Otherwise 1920x1080 (UA= sets the user agent, e.g. a Fire TV's); SIZE=960x540
and DPR=2 for the Fire TV. The test relay's "Test" profile is signed in (COOKIE=test-device; COOKIE=new-device is the
new guest, COOKIE= nobody).
Prints page errors and console errors at the end. Route and aircraft lookups (adsbdb) go to the fake data source
from run_test_relay.py, so names and routes match the made-up planes.

Example, the phone app's Today tab against the test relay:
    set PHONE=390x844 && py tools/test/shoot.py http://localhost:8096/app/ out wait:8000 tap:[data-tab=today] wait:2000 shot:today
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright


async def route(r):
    url = r.request.url
    if "api.adsbdb.com" in url:
        res = await r.fetch(url=url.replace("https://api.adsbdb.com", "http://127.0.0.1:8095"))
        return await r.fulfill(response=res)
    return await r.continue_()


async def main():
    url, out, steps = sys.argv[1], sys.argv[2], sys.argv[3:]
    phone = os.environ.get("PHONE")
    if phone:
        w, h = (int(v) for v in phone.lower().split("x"))
        opts = {"viewport": {"width": w, "height": h}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True,
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"}
    else:
        w, h = (int(v) for v in os.environ.get("SIZE", "1920x1080").lower().split("x"))
        opts = {"viewport": {"width": w, "height": h}, "device_scale_factor": float(os.environ.get("DPR", "1"))}
        if os.environ.get("UA"):          # e.g. a Fire TV's, for WEAK_TV
            opts["user_agent"] = os.environ["UA"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        ctx = await browser.new_context(**opts)
        cookie = os.environ.get("COOKIE", "test-device")
        if cookie:
            host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
            await ctx.add_cookies([{"name": "overhead", "value": cookie, "domain": host, "path": "/"}])
        page = await ctx.new_page()
        errors, console = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        await page.route("**/*", route)
        await page.goto(url)
        for st in steps:
            kind, _, arg = st.partition(":")
            if kind == "wait":
                await page.wait_for_timeout(int(arg))
            elif kind == "key":
                await page.keyboard.press(arg)
            elif kind == "click":
                x, y = arg.split(",")
                await page.mouse.click(int(x), int(y))
            elif kind == "tap":
                await page.click(arg)
            elif kind == "scroll":
                await page.evaluate(f"window.scrollTo(0, {int(arg)})")
            elif kind == "js":
                print("js:", json.dumps(await page.evaluate(arg))[:1500])
            elif kind == "shot":
                await page.screenshot(path=f"{out}-{arg}.png")
            elif kind == "full":
                await page.screenshot(path=f"{out}-{arg}.png", full_page=True)
            elif kind == "clip":
                x, y, w, h, name = arg.split(",")
                await page.screenshot(path=f"{out}-{name}.png", clip={"x": int(x), "y": int(y), "width": int(w), "height": int(h)})
            elif kind == "seq":
                seen = []
                for t in range(int(arg)):
                    cur = await page.evaluate("(document.querySelector('#railPages [aria-current]') || {dataset: {}}).dataset.page || '-'")
                    if not seen or seen[-1][1] != cur:
                        seen.append((t, cur))
                    await page.wait_for_timeout(1000)
                print("pages:", " → ".join(f"{c}@{t}s" for t, c in seen))
            else:
                raise SystemExit(f"Unknown step: {st}")
        status = await page.evaluate("(document.querySelector('#statusText') || document.querySelector('.statusText') || {}).textContent")
        print("status line:", status)
        print("page errors:", errors or "none")
        print("console errors:", console[:10] or "none")
        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
