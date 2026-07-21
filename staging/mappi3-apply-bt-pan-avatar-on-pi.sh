#!/usr/bin/env bash
set -euo pipefail
bundle="${1:-/tmp/mappi3-bt-pan-avatar.tar.gz}"
if [ ! -f "$bundle" ]; then echo "BUNDLE_MISSING $bundle"; exit 2; fi
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="/opt/mappi3/backups/live-deploy-bt-pan-avatar-$stamp"
echo "BACKUP=$backup"
sudo install -d -m 0755 "$backup"
sudo cp -a /opt/mappi3/app "$backup/app"
sudo cp -a /usr/local/bin/mappi3-agent.py "$backup/mappi3-agent.py"
if [ -f /usr/local/bin/mappi3-bluetooth-pan-phone-tether ]; then sudo cp -a /usr/local/bin/mappi3-bluetooth-pan-phone-tether "$backup/mappi3-bluetooth-pan-phone-tether.before"; fi
(systemctl is-enabled bluetooth.service 2>&1 || true) | sudo tee "$backup/bluetooth.service.enabled.before" >/dev/null
(systemctl is-active bluetooth.service 2>&1 || true) | sudo tee "$backup/bluetooth.service.active.before" >/dev/null
(nmcli -t -f NAME,UUID,TYPE,DEVICE,AUTOCONNECT con show 2>&1 || true) | sudo tee "$backup/nm-connections.before" >/dev/null
(ip route 2>&1 || true) | sudo tee "$backup/ip-route.before" >/dev/null
sudo sha256sum "$bundle" | sudo tee "$backup/package.sha256" >/dev/null
work="/tmp/mappi3-bt-pan-avatar-$stamp"
rm -rf "$work"; mkdir -p "$work"
tar -xzf "$bundle" -C "$work"
sudo rm -rf /opt/mappi3/app
sudo mkdir -p /opt/mappi3/app
sudo cp -a "$work/dist/." /opt/mappi3/app/
sudo install -m 0755 "$work/mappi3-agent.py" /usr/local/bin/mappi3-agent.py
sudo install -m 0755 "$work/mappi3-bluetooth-pan-phone-tether.sh" /usr/local/bin/mappi3-bluetooth-pan-phone-tether
sudo python3 -m py_compile /usr/local/bin/mappi3-agent.py
sudo systemctl restart mappi3-web.service
sleep 3
echo "SERVICE=$(systemctl is-active mappi3-web.service || true)"
python3 - <<'PY'
import json, urllib.request
for url in ['http://127.0.0.1:5050/api/status','http://127.0.0.1:5050/api/network/status','http://127.0.0.1:5050/api/bluetooth/pan/status','http://127.0.0.1:5050/api/sense']:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data=json.load(r)
            print(url, 'HTTP', r.status, 'ok=', data.get('ok'), 'summary=', data.get('summary') or data.get('bluetooth_pan',{}).get('summary') or '')
    except Exception as e:
        print(url, 'FAIL', e)
PY
echo "ROLLBACK_APP=sudo rm -rf /opt/mappi3/app && sudo cp -a $backup/app /opt/mappi3/app && sudo install -m 0755 $backup/mappi3-agent.py /usr/local/bin/mappi3-agent.py && sudo systemctl restart mappi3-web.service"
echo "ROLLBACK_BT=sudo systemctl disable --now bluetooth.service  # only if bluetooth was disabled before; see $backup/bluetooth.service.*.before"
