#!/usr/bin/env bash
# Installs the MapPI3 Bluetooth LE phone link as a systemd service. Needs root (the plugin manager
# runs as root). Uses BlueZ + python3-dbus + python3-gi, which the MapPI3 image already has.
set -euo pipefail
PLUGIN_ID='ble-link'
HERE="$(cd "$(dirname "$0")" && pwd)"
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
python3 -c 'import dbus, gi' || { echo "python3-dbus/python3-gi missing: apt install python3-dbus python3-gi"; exit 1; }
install -d -m 0775 "$MARKER_DIR" /run/mappi3
install -m 0755 "$HERE/mappi3_ble_link.py" /usr/local/bin/mappi3-ble-link.py
cat > /etc/systemd/system/mappi3-ble-link.service <<'UNIT'
[Unit]
Description=MapPI3 Bluetooth LE phone link
After=bluetooth.service mappi3-web.service
Requires=bluetooth.service

[Service]
Type=simple
ExecStartPre=/bin/mkdir -p /run/mappi3
ExecStart=/usr/bin/python3 /usr/local/bin/mappi3-ble-link.py
Restart=on-failure
RestartSec=5
Nice=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now mappi3-ble-link.service
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["bleStatus","bleHerbieEvents","blePairWindow"],"note":"Bluetooth LE phone link running as mappi3-ble-link.service."}
JSON
echo "MapPI3 plugin $PLUGIN_ID installed: Bluetooth LE phone link running."
