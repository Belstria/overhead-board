"""Cuts the board's sounds out of the recordings in sounds-src/ (not in the repository; see tools/sounds/README.md for
where they come from) and writes them to test/sounds.js (since 1.53.1 a file next to the board, loaded by the boards
and the app; before, they were embedded in the board), as small 22 kHz mono WAVs in base64, then stamps the new version
into the test board (tools/assets.py). Run it from the repository root:

    py tools/sounds/build_sounds.py            (also writes sounds-src/out/*.wav to listen to)

Several takes of the flap and the knob are kept, so repeated flips don't sound identical."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import audio  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent))
import assets  # noqa: E402  (tools/assets.py)

SRC = Path("sounds-src")
OUT = SRC / "out"
FILE = Path("test/sounds.js")   # the main board gets its copy with the next push to main (tools/push_main.py)


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


def barks(name, start_s, end_s, fade_ms, gate_at):
    """The Airbus "barking dog" (1.49): the PTU's bark-bark-bark with the cabin's hum between the barks turned down
    (a high-pass for the rumble, then a gentle gate), faded out at the end, at a quarter of the rate (11 kHz: it is all
    below 4 kHz) to keep the board small."""
    x, rate = audio.read_mono(SRC / name)
    clip = x[int(start_s * rate):int(end_s * rate)]
    clip = audio.gate(audio.highpass(clip, rate, 150), rate, gate_at, floor=.15)
    clip = audio.normalise(audio.fade_out(audio.cut(clip, rate, 0, pre_ms=0, length_ms=(end_s - start_s) * 1000, fade_ms=6), rate, fade_ms), .7)
    return [audio.halve(audio.halve(clip))], rate // 4


def main():
    sets = {
        # the flaps clack synthesised (1.19.1: chosen over the Pragotron recording, 174056 by matucha)
        "knob": best_clicks("30827__shewbox__clicky-knob-turning.wav", 5, 40, 42, 14, hp=900),   # short and crisp: the detent, not the box
        "switch": whole("119415__joedeshon__rocker_switch.wav"),
        "wheel": whole("139061__joedeshon__push_button_switch_07.wav"),
        "button": whole("eaglaxle-switching-button-2.wav", .06, .32),
        "ding": whole("arunangshubanerjee-airbus-cabin-pa-beep.wav", .45, 2.5),    # both tones (1.46, Dave's choice)
        "dog": barks("arunangshubanerjee-airbus-ptu-barking-dog.wav", 3.9, 7.25, 1000, .12),   # About, tapped 7 times
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
    FILE.write_text("// Fallblatt's recorded sounds (made by tools/sounds/build_sounds.py from the recordings credited in About; don't edit by\n"
                    "// hand): short WAVs in base64, loaded by the boards and the app when sound is on (1.53.1: a file of its own).\n"
                    "window.SOUND_DATA = {\n" + "\n".join(lines) + "\n};\n", encoding="utf-8", newline="\n")
    print(f"{FILE}: {total / 1024:.0f} KB of base64")
    print("stamped:", ", ".join(assets.stamp()) or "nothing changed")


if __name__ == "__main__":
    main()
