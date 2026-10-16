"""Run the boards against made-up flights: a fake flight data source on port 8095 and a test relay on port 8096 that
serves this repository's boards (/, /test/, /app/) with it. Your real relay, its settings and its data
are not touched: the test relay runs from a temporary folder.

    py tools/test/run_test_relay.py            every kind of plane, including special ones and an emergency
    py tools/test/run_test_relay.py --quiet    no special planes, so the pages rotate undisturbed
    py tools/test/run_test_relay.py --hover    adds a police helicopter hovering overhead
    py tools/test/run_test_relay.py --far      the landing starts 32 km out (its photo, then the runway radar)
    py tools/test/run_test_relay.py --fr24     the relay acts as if it had a Flightradar24 key (served by the fake)

Then open http://localhost:8096/ (or /test/, /app/, /screens). Ctrl+C stops both.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FAKE = "http://127.0.0.1:8095"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--quiet", action="store_true", help="no special planes")
    p.add_argument("--hover", action="store_true", help="add a helicopter hovering overhead")
    p.add_argument("--far", action="store_true", help="the landing starts 32 km out")
    p.add_argument("--fr24", action="store_true", help="pretend the relay has a Flightradar24 key")
    a = p.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="overhead-test-"))
    src = (REPO / "relay" / "serve.py").read_text(encoding="utf-8")
    for real, fake in [("https://api.adsbdb.com", FAKE), ("https://fr24api.flightradar24.com/api", FAKE + "/api"),
                       ("https://viennaairport.com/jart", FAKE + "/jart")]:
        if real not in src:
            raise SystemExit(f"relay/serve.py no longer mentions {real}; update run_test_relay.py")
        src = src.replace(real, fake)
    src = re.sub(r"^FR24_GAP_S = [\d.]+", "FR24_GAP_S = 0.5", src, flags=re.M)
    (tmp / "serve.py").write_text(src, encoding="utf-8")
    env = dict(os.environ, QUIET="1" if a.quiet else "", HOVER="1" if a.hover else "", FAR="1" if a.far else "", PYTHONIOENCODING="utf-8")
    fake = subprocess.Popen([sys.executable, str(HERE / "fakesrc.py")], env=env)
    cmd = [sys.executable, "serve.py", "--port", "8096", "--lat", "48.2085", "--lon", "16.3731", "--place", "Vienna",
           "--home", "VIE", "--local-root", str(REPO), "--source", FAKE + "/ac/{lat}/{lon}/{nm}"]
    if a.fr24:
        cmd += ["--fr24-key", "goodkey"]
    relay = subprocess.Popen(cmd, cwd=tmp, stdin=subprocess.DEVNULL, env=env)  # utf-8: piped output would be cp1252
    print(f"Test relay on http://localhost:8096/ (data in {tmp}). Ctrl+C to stop.", flush=True)
    try:
        while fake.poll() is None and relay.poll() is None:
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (relay, fake):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
