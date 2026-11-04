"""The board's voice (relay 112, to-do #314): the words of a call and the relay's audio.

    py tools/test/voice_calls.py                 the spelling rule, and /voice without Piper and with a stand-in for it
    py tools/test/voice_calls.py --piper DIR     also the real Piper in DIR (laid out as relay/install.sh makes it:
                                                 DIR/venv/bin/python, DIR/en_GB-cori-medium.onnx and .onnx.json)

The words are the cases of Dave's pick (VoiceA-words, 4 Nov 2026) and a few more. Without Piper the relay must say so
(503) and not offer the voice; with the stand-in (a fake worker that writes a few bytes) the call is made once, kept,
served again from the file, and the worker stops when idle. With the real Piper a call is an MP3 of 15-80 KB.
"""
import importlib.util
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORDS = [   # (voice_words arguments, what it says)
    (dict(airline="Austrian", flight="OS 411", frm="Vienna", to="Paris", way="out", typ="Airbus A320"),
     "Austrian four one one, to Paris. An A three-twenty, overhead now."),
    (dict(callsign="OR325", typ="Boeing 737-800", now="soon"),
     "O R three two five. A seven-three-seven, coming over now."),
    (dict(callsign="OEXEN", reg="OE-XEN", kind="helicopter", typ="Airbus H135"),
     "Helicopter O E X E N. An H one-thirty-five, overhead now."),
    (dict(callsign="GAF612", kind="military", typ="Airbus A400M", now="soon"),
     "Military flight G A F six one two. An A four-hundred M, coming over now."),
    (dict(airline="Aer Lingus", flight="EI 6AB", frm="Rome", to="Warsaw", typ="Airbus A320", now="soon"),
     "Aer Lingus six A B, from Rome to Warsaw. An A three-twenty, coming over now."),
    (dict(airline="Austrian", flight="OS 802", frm="Athens", to="Vienna", way="in", typ="Airbus A320neo", now="soon"),
     "Austrian eight zero two, from Athens. An A three-twenty neo, coming over now."),
    (dict(airline="Emirates", flight="EK 127", frm="Dubai", to="Vienna", way="in", typ="Airbus A380"),
     "Emirates one two seven, from Dubai. An A three-eighty, overhead now."),
    (dict(airline="Air Dolomiti", flight="EN 8231", frm="Frankfurt am Main", to="Florence", typ="Embraer E195"),
     "Air Dolomiti eight two three one, from Frankfurt am Main to Florence. An E one-ninety-five, overhead now."),
    (dict(airline="Swiss International Air Lines", flight="LX 1578", frm="Vienna", to="Zurich", way="out", typ="Airbus A220-300"),
     "Swiss one five seven eight, to Zurich. An A two-twenty, overhead now."),
    (dict(airline="Turkish Airlines", flight="TK 1888", typ="Boeing 737 MAX 8"),
     "Turkish one eight eight eight. A seven-three-seven Max eight, overhead now."),
    (dict(reg="OE-KAT", typ="Cessna 172"), "O E K A T. A Cessna one-seventy-two, overhead now."),
    (dict(callsign="EJU12AB", typ="ATR 72-600"), "E J U one two A B. An A T R seventy-two, overhead now."),
    (dict(callsign="RCH871", kind="military", typ="Boeing C-17"), "Military flight R C H eight seven one. A C seventeen, overhead now."),
    (dict(typ="Bombardier CRJ900"), "An aircraft. A Bombardier C R J nine-hundred, overhead now."),
    (dict(kind="helicopter"), "A helicopter. Overhead now."),
    (dict(callsign="DLH9X", frm="Munich"), "D L H nine X, from Munich. Overhead now."),
    (dict(airline="Lufthansa", flight="LH 1234", typ="Global 7500"), "Lufthansa one two three four. A Global seventy-five hundred, overhead now."),
]


def load():
    spec = importlib.util.spec_from_file_location("serve", REPO / "relay" / "serve.py")
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    serve.event = lambda *a, **k: None
    return serve


FAKE = r'''import sys, json
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    q = json.loads(line)
    open(q["out"], "wb").write(b"ID3fake" + q["text"].encode())
    print(json.dumps({"ok": True}), flush=True)
'''


def main():
    serve = load()
    bad = []
    for args, want in WORDS:
        shown, said = serve.voice_words(**args)
        if shown != want:
            bad.append(f"words: {args}\n   says: {shown}\n   want: {want}")
        if "[[" in shown or "\x01" in said or said.replace("[[ ˈeɪ ]]", "A") != shown:
            bad.append(f"Piper's text: {said}")
    for args, want in ((WORDS[0][0], "Austrian four one one, to Paris. An [[ ˈeɪ ]] three-twenty, overhead now."),
                       (WORDS[1][0], WORDS[1][1]),     # the article A stays a word
                       (WORDS[4][0], "Aer Lingus six [[ ˈeɪ ]] B, from Rome to Warsaw. An [[ ˈeɪ ]] three-twenty, coming over now.")):
        if serve.voice_words(**args)[1] != want:
            bad.append(f"Piper's text: {serve.voice_words(**args)[1]}")
    # what a request may ask for: no free text, no markup for Piper
    a = serve.voice_args({"airline": ["Austrian [[ x ]]"], "flight": ["OS 411<b>"], "kind": ["pirate"], "from": ["Paris\n"], "now": ["soon"]})
    if a["airline"] != "Austrian  x" or a["flight"] != "OS 411b" or a["kind"] or a["frm"] != "Paris" or a["now"] != "soon":
        bad.append(f"voice_args let through: {a}")
    # no Piper: not offered, and /voice says so
    with tempfile.TemporaryDirectory() as d:
        serve.VOICE_DIR = Path(d) / "voice"
        if serve.voice_ready() or serve.voice_call(dict(callsign="OR325"))[0] != 503:
            bad.append("without Piper the voice was offered")
        # a stand-in for Piper: made once, kept, served from the file, stopped when idle
        v = serve.VOICE_DIR
        (v / "venv" / "bin").mkdir(parents=True)
        py = v / "venv" / "bin" / "python"
        py.write_text(f"#!/bin/sh\nexec {sys.executable} -c '{FAKE}'\n")
        py.chmod(py.stat().st_mode | stat.S_IXUSR)
        (v / "venv" / ".installed").write_text("stand-in")
        for ext in (".onnx", ".onnx.json"):
            (v / (serve.VOICE_NAME + ext)).write_text("{}")
        if not serve.voice_ready():
            bad.append("the stand-in wasn't seen as installed")
        st, body, shown = serve.voice_call(dict(airline="Austrian", flight="OS 411", frm="Vienna", to="Paris", way="out", typ="Airbus A320"))
        if st != 200 or not body.startswith(b"ID3fake") or "[[ \xcb\x88e\xc9\xaa ]]".encode("latin-1").decode("utf-8") not in body.decode():
            bad.append(f"the first call: {st} {body[:60]!r}")
        made = serve._voice["made"]
        st2, body2, _ = serve.voice_call(dict(airline="Austrian", flight="OS 411", frm="Vienna", to="Paris", way="out", typ="Airbus A320"))
        if st2 != 200 or body2 != body or serve._voice["made"] != made:
            bad.append("the same call again wasn't served from the file")
        if not serve.voice_status()["running"]:
            bad.append("the worker isn't running after a call")
        serve._voice["used"] = time.time() - serve.VOICE_IDLE_S - 1
        with serve._voice_lock:
            serve._voice_stop("test")
        if serve.voice_status()["running"]:
            bad.append("the worker didn't stop")
        serve.VOICE_KEEP = 2
        for n in range(4):
            serve.voice_call(dict(callsign=f"TEST{n}"))
        if len(list((v / "cache").glob("*.mp3"))) != 2:
            bad.append("the cache keeps more than VOICE_KEEP calls")
        # a worker that dies at once: a 503, no crash
        py.write_text("#!/bin/sh\nexit 3\n")
        with serve._voice_lock:
            serve._voice_stop("test")
        if serve.voice_call(dict(callsign="DEAD1"))[0] != 503 or not serve.voice_status()["error"]:
            bad.append("a broken Piper didn't give a 503")
    # the real Piper
    if "--piper" in sys.argv:
        serve.VOICE_DIR = Path(sys.argv[sys.argv.index("--piper") + 1]).resolve()
        with tempfile.TemporaryDirectory() as d:
            real = serve.VOICE_DIR
            # its own cache: a scratch folder with links to Piper and the voice
            v = Path(d) / "voice"
            v.mkdir()
            for x in ("venv", serve.VOICE_NAME + ".onnx", serve.VOICE_NAME + ".onnx.json"):
                os.symlink(real / x, v / x)
            serve.VOICE_DIR = v
            for args, want in WORDS[:2]:
                t = time.time()
                st, body, shown = serve.voice_call(args)
                took = time.time() - t
                ok = st == 200 and (body[:3] == b"ID3" or body[0] == 0xFF and body[1] & 0xE0 == 0xE0) and 15000 < len(body) < 80000
                print(f"Piper: {shown!r}: {st}, {len(body)} bytes, {took:.2f} s")
                if not ok:
                    bad.append(f"Piper's call: {st}, {len(body)} bytes {body[:4]!r}")
            with serve._voice_lock:
                serve._voice_stop("test")
    for b in bad:
        print("FAIL", b)
    print("voice: %s" % ("ok" if not bad else f"{len(bad)} failed"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
