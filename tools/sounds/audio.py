"""Small WAV helpers in pure Python (no numpy on this PC): read any 16/24-bit WAV as mono floats, find clicks, cut,
fade, normalise and write 16-bit mono WAVs. Used by build_sounds.py."""
import math
import struct
import wave


def read_mono(path):
    """(samples as floats in -1..1, sample rate), channels averaged."""
    with wave.open(str(path)) as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        vals = struct.unpack(f"<{n * ch}h", raw)
        scale = 32768.0
    elif width == 3:
        vals = [int.from_bytes(raw[i:i + 3], "little", signed=True) for i in range(0, len(raw), 3)]
        scale = 8388608.0
    else:
        raise ValueError(f"{path}: {8 * width}-bit WAVs aren't handled")
    if ch == 1:
        return [v / scale for v in vals], rate
    return [sum(vals[i:i + ch]) / (ch * scale) for i in range(0, len(vals), ch)], rate


def envelope(x, rate, ms=1.0):
    """A fast peak envelope: the loudest sample in each `ms` window."""
    step = max(1, int(rate * ms / 1000))
    return [max(abs(v) for v in x[i:i + step]) for i in range(0, len(x), step)], step


def onsets(x, rate, gap_ms=30, rise=4.0, floor=0.02):
    """Sample positions where the sound jumps up sharply: louder than `floor` and `rise` times the level just before,
    at least `gap_ms` apart."""
    env, step = envelope(x, rate)
    out, last = [], -10 ** 9
    for i in range(3, len(env)):
        before = max(env[i - 3:i]) + 1e-4
        if env[i] > floor and env[i] / before > rise and (i - last) * step * 1000 / rate >= gap_ms:
            out.append(i * step)
            last = i
    return out


def peak(x):
    return max((abs(v) for v in x), default=0.0)


def cut(x, rate, at, pre_ms=1.5, length_ms=60, fade_ms=8):
    """A clip from just before `at`, with a tiny fade-in and a smooth fade-out."""
    a = max(0, at - int(rate * pre_ms / 1000))
    b = min(len(x), a + int(rate * length_ms / 1000))
    clip = list(x[a:b])
    fi = int(rate * 0.0004)
    for i in range(min(fi, len(clip))):
        clip[i] *= i / fi
    fo = min(len(clip), int(rate * fade_ms / 1000))
    for i in range(fo):
        clip[len(clip) - fo + i] *= math.cos(i / fo * math.pi / 2) ** 2
    return clip


def trim_tail(x, rate, below=0.004, keep_ms=4):
    """Drop the quiet end of a clip (keeping a little air)."""
    end = len(x)
    while end > 1 and abs(x[end - 1]) < below:
        end -= 1
    return x[:min(len(x), end + int(rate * keep_ms / 1000))]


def highpass(x, rate, f, q=0.707):
    """A 12 dB/octave high-pass (RBJ biquad): takes away the low body of a clip."""
    w = 2 * math.pi * f / rate
    al = math.sin(w) / (2 * q)
    c = math.cos(w)
    b0, b1, b2 = (1 + c) / 2, -(1 + c), (1 + c) / 2
    a0, a1, a2 = 1 + al, -2 * c, 1 - al
    y, x1, x2, y1, y2 = [], 0.0, 0.0, 0.0, 0.0
    for v in x:
        o = (b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0
        x2, x1, y2, y1 = x1, v, y1, o
        y.append(o)
    return y


def normalise(x, to=0.7):
    p = peak(x)
    return [v * to / p for v in x] if p else x


def halve(x):
    """44.1 kHz to 22.05 kHz: a gentle low-pass (3-tap) and every other sample."""
    y = [(x[max(0, i - 1)] + 2 * x[i] + x[min(len(x) - 1, i + 1)]) / 4 for i in range(len(x))]
    return y[::2]


def write(path, x, rate):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(x)}h", *[max(-32768, min(32767, int(round(v * 32767)))) for v in x]))


def wav_bytes(x, rate):
    data = struct.pack(f"<{len(x)}h", *[max(-32768, min(32767, int(round(v * 32767)))) for v in x])
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


def gate(x, rate, thresh, floor=0.2, ratio=2.0, attack_ms=4, release_ms=80):
    """A gentle noise gate (a downward expander): quieter than `thresh` (the level between the sounds worth keeping),
    the background is turned down by up to `floor`, smoothly, so the room is softened rather than cut out."""
    att, rel = math.exp(-1 / (rate * attack_ms / 1000)), math.exp(-1 / (rate * release_ms / 1000))
    env, gain, y = 0.0, 1.0, []
    for v in x:
        a = abs(v)
        env = att * env + (1 - att) * a if a > env else rel * env + (1 - rel) * a
        g = 1.0 if env >= thresh else max(floor, (env / thresh) ** (ratio - 1))
        gain = g if g > gain else .999 * gain + .001 * g      # opens at once, closes slowly
        y.append(v * gain)
    return y


def fade_out(x, rate, ms):
    """A long, smooth fade to silence over the last `ms`."""
    n = min(len(x), int(rate * ms / 1000))
    y = list(x)
    for i in range(n):
        y[len(y) - n + i] *= math.cos(i / n * math.pi / 2) ** 2
    return y
