#!/usr/bin/env bash
# Build the web app and install it on the MapPI3 Pi (/opt/mappi3/app), with a backup.
# Run from the PC (Git Bash):  bash tools/pi/deploy_web.sh [pi-address]   (default 10.42.0.1)
set -euo pipefail
PI="${1:-10.42.0.1}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o HostKeyAlias=10.42.0.1 "mappi3@$PI")
SCP=(scp -q -r -o BatchMode=yes -o HostKeyAlias=10.42.0.1)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
TS="$(date -u +%Y%m%dT%H%M%SZ)"; STAGE="/home/mappi3/deploy-web-$TS"
echo "== build"; npx vite build --config tools/pi/vite.deploy.config.mjs >/dev/null
mkdir -p dist-deploy/catalog && cp public/catalog/*.json dist-deploy/catalog/ && cp public/mappi3-sw.js dist-deploy/
echo "== upload"; "${SSH[@]}" "mkdir -p '$STAGE'"; "${SCP[@]}" dist-deploy/* "mappi3@$PI:$STAGE/"
"${SSH[@]}" "STAGE='$STAGE' TS='$TS' bash -s" <<'REMOTE'
set -euo pipefail
APP=/opt/mappi3/app; BK=/opt/mappi3/backups/web-$TS
sudo mkdir -p "$BK"; sudo cp -a "$APP/index.html" "$APP/mappi3-sw.js" "$BK/" 2>/dev/null || true
sudo cp -a "$APP/assets" "$BK/assets-code" 2>/dev/null || true
sudo install -o mappi3 -g mappi3 -m 644 "$STAGE/index.html" "$STAGE/mappi3-sw.js" "$APP/"
sudo mkdir -p "$APP/catalog" && sudo install -o mappi3 -g mappi3 -m 644 "$STAGE"/catalog/*.json "$APP/catalog/"
sudo cp -r "$STAGE"/assets/. "$APP/assets/" && sudo chown -R mappi3:mappi3 "$APP/assets"
curl -fsS -m 5 http://127.0.0.1:5050/ | grep -o 'assets/index-[^"]*' | head -2
curl -fsS -m 5 -o /dev/null -w "catalog %{http_code}\n" http://127.0.0.1:5050/catalog/camps.json
echo "done. backup: $BK"
REMOTE
