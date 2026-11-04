"""The relay's space station passes (relay 110), checked against published pass times.

    py tools/test/iss_passes.py

The orbit below is CelesTrak's of 3 Nov 2026; Heavens-Above (heavens-above.com, Pass summary for the ISS at central
Vienna, 48.2085 N 16.3731 E, 170 m, fetched on 4 Nov 2026 with that orbit current) listed these visible passes. The
relay's must start, peak and end within 10 s of them and as high (within 1°). The pass of 12 Nov at 19:22, three seconds
long, is one the relay leaves out (shorter than 10 s). Needs the sgp4 package (pip install sgp4, or Debian's
python3-sgp4); without it the test says so and fails.
"""
import calendar
import importlib.util
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TLE = ("1 25544U 98067A   26307.53092409  .00005389  00000+0  10530-3 0  9996",
       "2 25544  51.6330 330.5488 0007153 343.6919  16.3838 15.49164192593358")
LAT, LON = 48.2085, 16.3731
# Heavens-Above, times in CET (UTC+1): (day, start, max, end, max elevation)
PUBLISHED = [(11, "18:34:03", "18:34:57", "18:34:57", 16), (12, "17:47:05", "17:49:22", "17:49:29", 17),
             (13, "17:00:51", "17:01:53", "17:02:54", 11), (13, "18:34:47", "18:36:53", "18:36:53", 34)]


def utc(day, hms):
    h, m, s = map(int, hms.split(":"))
    return calendar.timegm((2026, 11, day, h, m, s)) - 3600


def main():
    spec = importlib.util.spec_from_file_location("serve", REPO / "relay" / "serve.py")
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    if not serve.ISS_OK:
        sys.exit("The sgp4 package is missing: pip install sgp4")
    t0 = calendar.timegm((2026, 11, 4, 0, 0, 0))
    got = serve.iss_passes(TLE, LAT, LON, t0, hours=24 * 10)
    bad = []
    if len(got) != len(PUBLISHED):
        bad.append(f"{len(got)} passes, Heavens-Above lists {len(PUBLISHED)} (one under 10 s left out)")
    for want, p in zip(PUBLISHED, got):
        day, s, m, e, el = want
        for name, w, g in (("start", utc(day, s), p["start"]), ("highest", utc(day, m), p["top"]), ("end", utc(day, e), p["end"])):
            if abs(w - g) > 10:
                bad.append(f"{day} Nov {s}: {name} {time.strftime('%H:%M:%S', time.gmtime(g + 3600))}, published {time.strftime('%H:%M:%S', time.gmtime(w + 3600))}")
        if abs(p["maxEl"] - el) > 1:
            bad.append(f"{day} Nov {s}: {p['maxEl']}° up, published {el}°")
        if not 400 < p["km"] < 440 or not 7.5 < p["kms"] < 7.8 or len(p["pts"]) < 2:
            bad.append(f"{day} Nov {s}: height {p['km']} km, speed {p['kms']} km/s, {len(p['pts'])} points")
    # the made-up pass of the test relay (--iss): from the west, high in the south-south-east, gone in the east-south-east
    f = serve.iss_fake(1000)
    if not (f["start"] == 1000 and 55 < f["maxEl"] < 70 and 255 < f["startAz"] < 290 and 100 < f["endAz"] < 125):
        bad.append(f"the made-up pass: {f['maxEl']}° up, from {f['startAz']}°, to {f['endAz']}°")
    title, body = serve.iss_text({**got[3], "start": utc(13, "18:34:47"), "end": utc(13, "18:36:53")})
    if not title.startswith("Space station ISS · look up at ") or not body.startswith("From the south-west, low in the south-west, gone at "):
        bad.append(f"the notification: {title} / {body}")
    # the orbit kept on disk: CelesTrak down, yesterday's is used (and asked again only an hour later); back up, the
    # new one replaces it; older than ISS_TLE_MAX_DAYS, none
    import os
    import tempfile
    serve.event = lambda *a, **k: None
    with tempfile.TemporaryDirectory() as d:
        serve.ISS_TLE_FILE = Path(d) / "iss-tle.txt"
        serve.ISS_TLE_FILE.write_text("ISS (ZARYA)\n" + "\n".join(TLE) + "\n", encoding="ascii")
        os.utime(serve.ISS_TLE_FILE, (time.time() - 2 * 86400,) * 2)
        asked = []
        serve.fetch = lambda *a, **k: (asked.append(1), (502, "text/plain", b"unreachable", {}))[1]
        if serve.iss_tle() != TLE or serve.iss_tle() != TLE or len(asked) != 1:
            bad.append(f"CelesTrak down: the kept orbit wasn't used ({len(asked)} asks)")
        new = (TLE[0].replace("26307.53092409", "26308.53092409"), TLE[1])
        serve.fetch = lambda *a, **k: (200, "text/plain", ("ISS (ZARYA)\n" + "\n".join(new) + "\n").encode(), {})
        serve._iss.update(tried=0)
        if serve.iss_tle() != new or "26308" not in serve.ISS_TLE_FILE.read_text(encoding="ascii"):
            bad.append("CelesTrak back: the new orbit wasn't kept")
        serve._iss.update(tle=None, at=0, tried=time.time())
        os.utime(serve.ISS_TLE_FILE, (time.time() - 20 * 86400,) * 2)
        if serve.iss_tle() is not None:
            bad.append("an orbit 20 days old was still used")
    for b in bad:
        print("FAIL", b)
    if bad:
        sys.exit(1)
    print(f"ok: {len(got)} passes within 10 s of Heavens-Above's")


if __name__ == "__main__":
    main()
