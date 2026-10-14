"""Draws app/badge-96.png: the logo's plane, white on transparent, for Android's status bar (it shows only a
notification badge's shape, so the square app icon came out as a white square). Standard library only.

    py tools/app/make_badge.py
"""
import math, struct, zlib
from pathlib import Path

N, SS = 96, 4                                   # size, and 4x4 samples per pixel for smooth edges
# the plane of the logo (tools/app/head.html #splash, the board's drawPlane), in a 100x100 box, nose up
BODY = (45.5, 8, 54.5, 90, 4.5)
WING = [(50, 34), (92, 56), (92, 63), (50, 52), (8, 63), (8, 56)]
TAIL = [(50, 76), (67, 86), (67, 91), (50, 87), (33, 91), (33, 86)]


def inside(poly, x, y):
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def in_body(x, y):
    x0, y0, x1, y1, r = BODY
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cy = min(max(y, y0 + r), y1 - r)            # rounded ends
    return (x - (x0 + x1) / 2) ** 2 + (y - cy) ** 2 <= r * r or y0 + r <= y <= y1 - r


def plane(px, py):
    # turned 45 degrees like the logo, and a little larger than in the logo's square: the badge is the plane alone
    s, a = 100 / (N * .98), math.radians(-45)
    u, v = (px - N / 2) * s, (py - N / 2) * s
    x, y = u * math.cos(a) - v * math.sin(a) + 50, u * math.sin(a) + v * math.cos(a) + 50
    return in_body(x, y) or inside(WING, x, y) or inside(TAIL, x, y)


rows = []
for j in range(N):
    row = bytearray([0])
    for i in range(N):
        hit = sum(plane(i + (a + .5) / SS, j + (b + .5) / SS) for a in range(SS) for b in range(SS))
        row += bytes([255, 255, 255, round(255 * hit / SS / SS)])
    rows.append(bytes(row))
chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
out = Path(__file__).resolve().parents[2] / "app" / "badge-96.png"
out.write_bytes(png)
print("wrote", out, len(png), "bytes")
