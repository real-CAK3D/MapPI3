#!/usr/bin/env bash
set -euo pipefail
bundle="${1:-/tmp/mappi3-pi-deploy-current.tar.gz}"
if [ ! -f "$bundle" ]; then echo "BUNDLE_MISSING $bundle"; exit 2; fi
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="/opt/mappi3/backups/live-deploy-$stamp"
echo "BACKUP=$backup"
sudo mkdir -p "$backup"
sudo cp -a /opt/mappi3/app "$backup/app"
sudo cp -a /usr/local/bin/mappi3-agent.py "$backup/mappi3-agent.py"
sudo sha256sum "$bundle" | sudo tee "$backup/package.sha256" >/dev/null
work="/tmp/mappi3-deploy-$stamp"
rm -rf "$work"; mkdir -p "$work"
tar -xzf "$bundle" -C "$work"
sudo rm -rf /opt/mappi3/app
sudo mkdir -p /opt/mappi3/app
sudo cp -a "$work/dist/." /opt/mappi3/app/
sudo install -m 0755 "$work/mappi3-agent.py" /usr/local/bin/mappi3-agent.py
sudo python3 -m py_compile /usr/local/bin/mappi3-agent.py
sudo systemctl restart mappi3-web.service
sleep 3
echo "SERVICE=$(systemctl is-active mappi3-web.service || true)"
python3 - <<'PY'
import json, urllib.request
for url in ['http://127.0.0.1:5050/api/status','http://127.0.0.1:5050/api/network/status','http://127.0.0.1:5050/releases/mappi3-packages.json']:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            body=r.read(600).decode('utf-8','replace')
            print(url, r.status, body[:240].replace('\n',' '))
    except Exception as e:
        print(url, 'FAIL', e)
PY
