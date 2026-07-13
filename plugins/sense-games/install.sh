#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='sense-games'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/sense'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["senseHat", "compass", "liquid", "sos", "flashlight", "magic8", "snake", "hydrationAlarm", "senseProgress", "senseDimmer"],"note":"Sense HAT modes/games/progress/dimmer are built into mappi3-agent."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Sense HAT modes/games/progress/dimmer are built into mappi3-agent.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Sense HAT modes/games/progress/dimmer are built into mappi3-agent."
