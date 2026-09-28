#!/usr/bin/env bash
# Install the MapPI3 mesh service (Meshtastic radio) on the Pi, then the agent + Whisplay updates.
# Run from the PC (Git Bash):  bash tools/pi/deploy_mesh.sh [pi-address]
set -euo pipefail
PI="${1:-10.42.0.1}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o HostKeyAlias=10.42.0.1 "mappi3@$PI")
SCP=(scp -q -o BatchMode=yes -o HostKeyAlias=10.42.0.1)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"; STAGE="/home/mappi3/deploy-mesh-$TS"
"${SSH[@]}" "mkdir -p '$STAGE'"
"${SCP[@]}" "$ROOT/local-pi-imager/mesh/mappi3-mesh.py" "$ROOT/local-pi-imager/mesh/mappi3-mesh.service" "mappi3@$PI:$STAGE/"
"${SSH[@]}" "STAGE='$STAGE' bash -s" <<'REMOTE'
set -euo pipefail
python3 -c "import sys;compile(open(sys.argv[1]).read(),sys.argv[1],'exec')" "$STAGE/mappi3-mesh.py"
if [ ! -x /opt/mappi3/mesh-venv/bin/python ]; then
  echo "== creating venv + installing meshtastic (first time, a few minutes on the Zero)"
  sudo python3 -m venv /opt/mappi3/mesh-venv
  sudo /opt/mappi3/mesh-venv/bin/pip install --quiet --upgrade pip
  sudo /opt/mappi3/mesh-venv/bin/pip install --quiet meshtastic
fi
/opt/mappi3/mesh-venv/bin/python -c "import meshtastic, importlib.metadata as m; print('meshtastic', m.version('meshtastic'))"
sudo usermod -aG dialout mappi3 || true
sudo mkdir -p /var/lib/mappi3 && sudo chown mappi3:mappi3 /var/lib/mappi3
sudo install -o root -g root -m 755 "$STAGE/mappi3-mesh.py" /usr/local/bin/mappi3-mesh.py
sudo install -o root -g root -m 644 "$STAGE/mappi3-mesh.service" /etc/systemd/system/mappi3-mesh.service
sudo systemctl daemon-reload
sudo systemctl enable --now mappi3-mesh.service
sudo systemctl restart mappi3-mesh.service
sleep 6
systemctl is-active mappi3-mesh.service
curl -s -m 3 http://127.0.0.1:5061/state | head -c 300; echo
REMOTE
echo "== agent + Whisplay"
bash "$ROOT/tools/pi/deploy_whisplay.sh" "$PI"
