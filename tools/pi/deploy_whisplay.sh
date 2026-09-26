#!/usr/bin/env bash
# Install the Whisplay dashboard + AI app + agent Herbie mirror on the MapPI3 Pi, with backups.
# Run from the PC (Git Bash):  bash tools/pi/deploy_whisplay.sh [pi-address]
# pi-address defaults to the hotspot 10.42.0.1; Tailscale (100.111.199.92) works too.
# Only run this after CAK3D approves a Pi deploy.
set -euo pipefail
PI="${1:-10.42.0.1}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o HostKeyAlias=10.42.0.1 "mappi3@$PI")
SCP=(scp -q -o BatchMode=yes -o HostKeyAlias=10.42.0.1)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="/home/mappi3/deploy-whisplay-$TS"
W="$ROOT/local-pi-imager/whisplay"

echo "== upload to $STAGE"
"${SSH[@]}" "mkdir -p '$STAGE/apps'"
"${SCP[@]}" "$W/mappi3_whisplay_common.py" "$W/mappi3_whisplay_dashboard.py" "$W/mappi3_whisplay_ai_chat.py" "mappi3@$PI:$STAGE/"
"${SCP[@]}" "$W/apps/"*.json "mappi3@$PI:$STAGE/apps/"
"${SCP[@]}" "$ROOT/local-pi-imager/boot-partition-copy/mappi3-agent.py" "mappi3@$PI:$STAGE/"

"${SSH[@]}" "STAGE='$STAGE' TS='$TS' bash -s" <<'REMOTE'
set -euo pipefail
EX=/opt/whisplay/Whisplay-main/example
APPS=/home/mappi3/.whisplay-daemon/app
BK=/opt/mappi3/backups/whisplay-$TS
echo "== syntax check"
for f in "$STAGE"/*.py; do python3 -c "import sys;compile(open(sys.argv[1]).read(),sys.argv[1],'exec')" "$f"; done
echo "== backup to $BK"
sudo mkdir -p "$BK/apps"
sudo cp -a "$EX"/mappi3_whisplay_*.py "$BK/" 2>/dev/null || true
sudo cp -a "$APPS"/*.json "$BK/apps/"
sudo cp -a /usr/local/bin/mappi3-agent.py "$BK/"
echo "== install Whisplay apps"
for f in mappi3_whisplay_common.py mappi3_whisplay_dashboard.py mappi3_whisplay_ai_chat.py; do sudo install -o mappi3 -g mappi3 -m 755 "$STAGE/$f" "$EX/$f"; done
install -m 644 "$STAGE"/apps/*.json "$APPS/"
# Leftover test entry with no launch command (tops the menu and errors when tapped). Leaves the menu at next daemon start.
[ -f "$APPS/mappi3-rgb565-render-test.json" ] && mv "$APPS/mappi3-rgb565-render-test.json" "$BK/removed-mappi3-rgb565-render-test.json" || true
echo "== install agent + restart web"
sudo install -o root -g root -m 755 "$STAGE/mappi3-agent.py" /usr/local/bin/mappi3-agent.py
sudo systemctl restart mappi3-web
for i in $(seq 1 30); do curl -fsS -m 2 http://127.0.0.1:5050/api/status >/dev/null 2>&1 && break; sleep 1; done
curl -fsS -m 3 http://127.0.0.1:5050/api/status >/dev/null && echo "agent up"
echo "== relaunch dashboard (exit, then launch)"
python3 - <<'PY'
import json, socket, time
def rpc(cmd, payload=None):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.connect('/tmp/whisplay-daemon.sock')
        c.sendall((json.dumps({'version': 1, 'cmd': cmd, 'payload': payload or {}}) + '\n').encode())
        return json.loads(c.makefile('r').readline() or '{}')
app = 'whisplay-mappi3-dashboard'
print('exit', rpc('app.exit.request', {'app_id': app}))
for _ in range(40):
    time.sleep(0.5)
    r = rpc('app.launch', {'app_id': app})
    if r.get('ok'):
        print('launch', r); break
else:
    print('launch did not succeed; check the screen')
PY
sleep 6
ls -la /tmp/whisplay-fb-* 2>/dev/null || true
python3 - <<'PY'
import glob, os
fbs = sorted(glob.glob('/tmp/whisplay-fb-whisplay-mappi3-dashboard-*.bin'), key=os.path.getmtime)
print('framebuffers:', len(fbs))
if fbs:
    data = open(fbs[-1], 'rb').read()
    print('newest non-zero bytes:', sum(1 for b in data[:200000] if b))
PY
echo "== Herbie mirror"
sleep 3; curl -fsS -m 3 http://127.0.0.1:5050/api/herbie/now; echo
echo "done. backup: $BK"
REMOTE
