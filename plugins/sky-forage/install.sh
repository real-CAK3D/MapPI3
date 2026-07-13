#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='sky-forage'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/field-guides/sky'
install -d -m 0775 '/var/lib/mappi3/field-guides/forage'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["sky", "cameraOverlay", "forage", "wildFoodSafety"],"note":"Sky/forage guide storage ready; pages are built into the app."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Sky/forage guide storage ready; pages are built into the app.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Sky/forage guide storage ready; pages are built into the app."
