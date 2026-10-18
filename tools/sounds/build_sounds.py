"""Cuts the board's sounds out of the recordings in sounds-src/ (not in the repository; see tools/sounds/README.md for
where they come from) and embeds them in the boards between the `@sounds-begin` and `@sounds-end` lines, as small
22 kHz mono WAVs in base64. Run it from the repository root:

    py tools/sounds/build_sounds.py            (also writes sounds-src/out/*.wav to listen to)

Several takes of the flap and the knob are kept, so repeated flips don't sound identical."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import audio  # noqa: E402

SRC = Path("sounds-src")
OUT = SRC / "out"
BOARDS = [Path("test/index.html")]   # the main board gets them with the next copy


def best_clicks(name, count, gap_ms, length_ms, fade_ms, hp=None):
    """The cleanest `count` clicks of a recording: loud, with quiet just before, cut short of the next click.
    `hp`: a high-pass frequency, to take away a hollow low body."""
    x, rate = audio.read_mono(SRC / name)
    on = audio.onsets(x, rate, gap_ms=gap_ms)
    takes = []
    for i, at in enumerate(on):
        nxt = on[i + 1] if i + 1 < len(on) else len(x)
        room_ms = (nxt - at) * 1000 / rate - 6
        if room_ms < length_ms * .6:
            continue
        clip = audio.cut(x, rate, at, length_ms=min(length_ms, room_ms), fade_ms=fade_ms)
        if hp:
            clip = audio.highpass(clip, rate, hp)
        quiet = audio.peak(x[max(0, at - int(rate * .02)):max(0, at - int(rate * .002))]) + 1e-4
        takes.append((audio.peak(clip) / quiet * audio.peak(clip), clip))
    takes.sort(key=lambda t: -t[0])
    return [audio.halve(audio.normalise(audio.trim_tail(c, rate), .7)) for _, c in takes[:count]], rate // 2


def whole(name, start_s=0.0, end_s=None, to=.7):
    x, rate = audio.read_mono(SRC / name)
    a, b = int(start_s * rate), int(end_s * rate) if end_s else len(x)
    clip = audio.cut(x, rate, a + int(rate * .0015), length_ms=(b - a) * 1000 / rate, fade_ms=6)
    return [audio.halve(audio.normalise(audio.trim_tail(clip, rate), to))], rate // 2


def main():
    sets = {
        # the flaps clack synthesised (1.19.1: chosen over the Pragotron recording, 174056 by matucha)
        "knob": best_clicks("30827__shewbox__clicky-knob-turning.wav", 5, 40, 42, 14, hp=900),   # short and crisp: the detent, not the box
        "switch": whole("119415__joedeshon__rocker_switch.wav"),
        "wheel": whole("139061__joedeshon__push_button_switch_07.wav"),
        "button": whole("eaglaxle-switching-button-2.wav", .06, .32),
        "ding": whole("arunangshubanerjee-airbus-cabin-pa-beep.wav", .45, 2.5),    # both tones (1.46, Dave's choice)
    }
    OUT.mkdir(exist_ok=True)
    lines, total = [], 0
    for key, (clips, rate) in sets.items():
        datas = []
        for i, c in enumerate(clips):
            audio.write(OUT / f"{key}-{i + 1}.wav", c, rate)
            data = base64.b64encode(audio.wav_bytes(c, rate)).decode()
            total += len(data)
            datas.append(f'"{data}"')
        lines.append(f'  {key}: [{", ".join(datas)}],')
        print(f"{key}: {len(clips)} take(s), {', '.join(f'{len(c) * 1000 // rate} ms' for c in clips)}")
    block = ("// @sounds-begin (made by tools/sounds/build_sounds.py from the recordings credited in About; don't edit by hand)\n"
             "const SOUND_DATA = {\n" + "\n".join(lines) + "\n};\n// @sounds-end")
    print(f"embedded: {total / 1024:.0f} KB of base64")
    for f in BOARDS:
        s = f.read_text(encoding="utf-8")
        a, b = s.find("// @sounds-begin"), s.find("// @sounds-end")
        if a < 0 or b < 0:
            print(f"{f}: no @sounds-begin/@sounds-end lines; skipped")
            continue
        s = s[:a] + block + s[b + len("// @sounds-end"):]
        f.write_text(s, encoding="utf-8", newline="\n")
        print(f"{f}: updated")


if __name__ == "__main__":
    main()
