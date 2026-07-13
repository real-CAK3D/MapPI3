#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='ambient-sounds'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/media/ambient'
install -d -m 0775 '/var/lib/mappi3/media/ambient/starter-pack'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["ambientSounds", "rainLoop", "creekLoop", "forestLoop", "nightLoop", "sensePulse"],"note":"Ambient starter slots ready; browser synth fallback works without files."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Ambient starter slots ready; browser synth fallback works without files.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Ambient starter slots ready; browser synth fallback works without files."
