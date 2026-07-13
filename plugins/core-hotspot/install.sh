#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='core-hotspot'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/plugins/core-hotspot'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["hotspot", "phonePortal", "updates"],"note":"Core hotspot/captive portal controls are built into the image."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Core hotspot/captive portal controls are built into the image.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Core hotspot/captive portal controls are built into the image."
