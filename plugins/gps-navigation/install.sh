#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='gps-navigation'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/gps'
install -d -m 0775 '/var/lib/mappi3/routes'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["gpsModule", "phoneGps", "gpx", "turnByTurn", "driveGps"],"note":"GPS/navigation hooks, GPX folders, Drive GPS and route handoff ready."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
GPS/navigation hooks, GPX folders, Drive GPS and route handoff ready.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: GPS/navigation hooks, GPX folders, Drive GPS and route handoff ready."
