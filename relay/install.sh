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

if ! command -v python3 >/dev/null || ! command -v curl >/dev/null || ! python3 -c "import cryptography" 2>/dev/null; then
  apt-get update -q && apt-get install -y -q python3 curl python3-cryptography   # cryptography: push notifications
fi
id overhead >/dev/null 2>&1 || useradd --system --home-dir "$DIR" --shell /usr/sbin/nologin overhead
mkdir -p "$DIR/data"

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
