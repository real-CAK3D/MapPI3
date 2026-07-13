#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='noaa-weather'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/noaa'
install -d -m 0775 '/var/lib/mappi3/noaa/radar-cache'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["satelliteWeather", "nwsText", "radarTiles", "sdrFuture"],"note":"NOAA/NWS cache folders ready; live refresh works when online."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
NOAA/NWS cache folders ready; live refresh works when online.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: NOAA/NWS cache folders ready; live refresh works when online."
