#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='bluetooth-sensors'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/sensors/bluetooth'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["bluetoothSensors", "bleHeartbeat", "externalSensors"],"note":"Bluetooth sensor bridge folders/manifest ready; external BLE hardware is future optional."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Bluetooth sensor bridge folders/manifest ready; external BLE hardware is future optional.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Bluetooth sensor bridge folders/manifest ready; external BLE hardware is future optional."
