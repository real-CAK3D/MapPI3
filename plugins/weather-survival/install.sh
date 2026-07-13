#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='weather-survival'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/weather'
install -d -m 0775 '/var/lib/mappi3/survival'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["weather", "survival", "weatherAlerts", "weatherCache"],"note":"Weather cache and survival reference folders ready."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Weather cache and survival reference folders ready.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Weather cache and survival reference folders ready."
