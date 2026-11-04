#!/bin/sh
# Installs or updates the Overhead relay as a service on Debian or Ubuntu (an LXC container on the homelab, say).
# Run as root. With serve.py and overhead-relay.service next to this script it installs those; otherwise it fetches
# the published ones from GitHub. Running it again updates the relay and restarts it; settings (overhead.json) and
# the logbook (data/) in /opt/overhead-relay are kept.
#
# Update copies (relay 68): before an update replaces serve.py, data/ is saved as /root/data-before-relay<N>.tgz (N:
# the version about to be installed, so data-before-relay68.tgz is the data just before relay 68 went in). Only the
# newest 3 of those (by time) are kept; older /root/data-before-relay*.tgz are removed.
# Nothing else in /root is touched.
#
#   curl -fsSL https://raw.githubusercontent.com/Belstria/overhead-board/main/relay/install.sh | sh
set -eu
DIR=/opt/overhead-relay
SRC=https://raw.githubusercontent.com/Belstria/overhead-board/main/relay
HERE=/nonexistent
[ -f "$0" ] && HERE=$(cd "$(dirname "$0")" && pwd)       # run as a file: use the copies next to it (not when piped)

if ! command -v python3 >/dev/null || ! command -v curl >/dev/null || ! python3 -c "import cryptography" 2>/dev/null || ! python3 -c "import sgp4" 2>/dev/null; then
  # cryptography: push notifications; sgp4 (relay 110, 0.4 MB on disk, under 2 MB of memory): the space station's passes
  apt-get update -q && apt-get install -y -q python3 curl python3-cryptography python3-sgp4
fi
id overhead >/dev/null 2>&1 || useradd --system --home-dir "$DIR" --shell /usr/sbin/nologin overhead
mkdir -p "$DIR/data"

# The board's voice (relay 112): Piper, a free text-to-speech engine (github.com/OHF-Voice/piper1-gpl), in its own
# Python environment in voice/, and one English voice ("Cori", medium quality) from Piper's official voice collection
# on Hugging Face, checked against its SHA-256. About 260 MB on disk (200 MB Piper and onnxruntime, 64 MB the voice);
# about 230 MB of memory while it speaks (it stops after ten idle minutes). Run again, it only checks what is there.
# Without it (no room, no network, OVERHEAD_NO_VOICE=1) the relay works as before and the boards don't offer VOICE.
VOICE_DIR="$DIR/voice"
VOICE_NAME=en_GB-cori-medium
VOICE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/cori/medium
VOICE_SHA=1899f98e5fb8310154f3c2973f4b8a929ba7245e722b3d3a85680b833d95f10d
VOICE_JSON_SHA=e262c16d7f192f69d4edd6b4ef8a5915379e67495fcc402f1ab15eeb33da3d36
VOICE_PIP="piper-tts==1.8.0 lameenc==1.9.0"
install_voice(){
  if [ "$(sha256sum "$VOICE_DIR/$VOICE_NAME.onnx" 2>/dev/null | cut -c1-64)" != "$VOICE_SHA" ] || [ ! -f "$VOICE_DIR/venv/.installed" ] \
     || [ "$(cat "$VOICE_DIR/venv/.installed")" != "$VOICE_PIP" ]; then
    FREE=$(df -Pm "$DIR" | awk 'NR==2 {print $4}')
    [ "${FREE:-0}" -ge 600 ] || { echo "Not enough room for the voice (${FREE} MB free, 600 MB wanted)"; return 1; }
  fi
  python3 -c "import ensurepip" 2>/dev/null || apt-get install -y -q python3-venv || return 1
  mkdir -p "$VOICE_DIR" || return 1
  if [ ! -f "$VOICE_DIR/venv/.installed" ] || [ "$(cat "$VOICE_DIR/venv/.installed")" != "$VOICE_PIP" ]; then
    echo "Installing Piper for the board's voice (about 200 MB)"
    rm -rf "$VOICE_DIR/venv"
    python3 -m venv "$VOICE_DIR/venv" || return 1
    # shellcheck disable=SC2086
    "$VOICE_DIR/venv/bin/pip" install -q --disable-pip-version-check --no-cache-dir $VOICE_PIP || return 1
    "$VOICE_DIR/venv/bin/python" -I -c "import piper, lameenc, numpy" || return 1
    echo "$VOICE_PIP" > "$VOICE_DIR/venv/.installed"     # the relay offers the voice only with this
  fi
  for f in "$VOICE_NAME.onnx:$VOICE_SHA" "$VOICE_NAME.onnx.json:$VOICE_JSON_SHA"; do
    name=${f%%:*}; sum=${f##*:}
    [ "$(sha256sum "$VOICE_DIR/$name" 2>/dev/null | cut -c1-64)" = "$sum" ] && continue
    echo "Fetching the voice: $name"
    curl -fsSL "$VOICE_URL/$name" -o "$VOICE_DIR/$name.part" || return 1
    [ "$(sha256sum "$VOICE_DIR/$name.part" | cut -c1-64)" = "$sum" ] || { rm -f "$VOICE_DIR/$name.part"; echo "$name: wrong checksum"; return 1; }
    mv "$VOICE_DIR/$name.part" "$VOICE_DIR/$name"
  done
}
if [ "${OVERHEAD_NO_VOICE:-}" = 1 ]; then
  echo "The board's voice is left out (OVERHEAD_NO_VOICE=1)"
elif ! install_voice; then
  echo "The board's voice was not installed; the relay works without it (boards don't offer VOICE). Run this again to retry."
fi

fetch(){ # fetch NAME DEST: the copy next to this script, or the published one
  if [ -f "$HERE/$1" ]; then cp "$HERE/$1" "$2"; else curl -fsSL "$SRC/$1" -o "$2"; fi
}
fetch serve.py "$DIR/serve.py.new"
python3 -m py_compile "$DIR/serve.py.new"            # never replace a working relay with a broken file
NEW=$(grep -m1 -o 'RELAY_VERSION = [0-9]*' "$DIR/serve.py.new" | grep -o '[0-9]*$' || true)
if [ -n "$NEW" ] && [ -f "$DIR/serve.py" ] && [ -n "$(ls -A "$DIR/data" 2>/dev/null)" ]; then
  # tar while the relay runs: a file written meanwhile makes tar say so (exit 1); the copy is still good
  tar -czf "/root/data-before-relay$NEW.tgz" -C "$DIR" data || [ $? -eq 1 ]
  echo "Saved data/ as /root/data-before-relay$NEW.tgz"
  ls -1t /root/data-before-relay*.tgz | tail -n +4 | while read -r f; do rm -f "$f" && echo "Removed the older copy $f"; done
fi
mv "$DIR/serve.py.new" "$DIR/serve.py"
rm -rf "$DIR/__pycache__"
fetch overhead-relay.service /etc/systemd/system/overhead-relay.service

chown -R overhead:overhead "$DIR"
[ -f "$DIR/overhead.json" ] && chmod 600 "$DIR/overhead.json"   # holds the Flightradar24 key
systemctl daemon-reload
systemctl enable -q overhead-relay
systemctl restart overhead-relay
sleep 2
systemctl is-active overhead-relay >/dev/null && echo "Overhead relay $(grep -m1 -o 'RELAY_VERSION = [0-9]*' "$DIR/serve.py" | grep -o '[0-9]*$') is running on port 8080." \
  || { echo "The relay did not start. See: journalctl -u overhead-relay -n 50"; exit 1; }
[ "$(date +%Z)" = "UTC" ] && echo "Note: this machine is on UTC. Days in the logbook follow the local time zone; set it (e.g. timedatectl set-timezone Europe/Vienna) and run this again."
exit 0
