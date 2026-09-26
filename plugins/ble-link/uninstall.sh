#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='ble-link'
systemctl disable --now mappi3-ble-link.service 2>/dev/null || true
rm -f /etc/systemd/system/mappi3-ble-link.service /usr/local/bin/mappi3-ble-link.py
systemctl daemon-reload || true
rm -rf "/var/lib/mappi3/plugins/$PLUGIN_ID"
echo "MapPI3 plugin $PLUGIN_ID removed. Bluetooth itself is left as it was."
