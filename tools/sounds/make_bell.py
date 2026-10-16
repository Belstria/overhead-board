"""Renders the airport bell (the boards' airportBell(), Settings → Special bell) to app/airport-bell.wav, so it can be
picked as Fallblatt's notification sound on Android. Standard library only; keep the notes and partials equal to
BELL_NOTES and airportBell() in the boards.

    py tools/sounds/make_bell.py
"""
import math, struct, wave
from pathlib import Path

RATE = 22050
NOTES = [(392.00, 0, 2.6), (523.25, .55, 2.6), (659.25, 1.1, 4.0)]       # frequency, start, ring (s)
PARTIALS = [(1, .30, 1.0), (4, .055, .3), (10, .012, .1)]              # multiple, level, share of the ring
LENGTH = 5.4

n = int(RATE * LENGTH)
dry = [0.0] * n
for f, start, ring in NOTES:
    t0 = int(start * RATE)
    for i in range(int((ring + .05) * RATE)):
        t = i / RATE
        if t0 + i >= n:
            break
        trem = .84 + .16 * math.sin(2 * math.pi * 4.6 * t)
        v = 0.0
        for mult, amp, share in PARTIALS:
            dec = ring * share
            if t > dec:
                continue
            env = min(1, t / .006) * math.exp(math.log(.004) * t / dec) if amp else 0
            v += amp * env * math.sin(2 * math.pi * f * mult * t)
        dry[t0 + i] += v * trem
# a small room: a few delays fed back, like the boards' sound output
wet = dry[:]
for delay, gain in ((.031, .28), (.047, .22), (.071, .16), (.113, .1)):
    d = int(delay * RATE)
    for i in range(d, n):
        wet[i] += wet[i - d] * gain * .5
peak = max(abs(x) for x in wet) or 1
frames = b"".join(struct.pack("<h", int(max(-1, min(1, x / peak * .7)) * 32767)) for x in wet)
out = Path(__file__).resolve().parents[2] / "app" / "airport-bell.wav"
with wave.open(str(out), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(frames)
print("wrote", out, out.stat().st_size, "bytes")
