#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='coastal-tidal-theme'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/themes/coastal-tidal-theme'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["coastal_tidal"],"note":"Theme metadata installed; UI theme is bundled in the web app."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Theme metadata installed; UI theme is bundled in the web app.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Theme metadata installed; UI theme is bundled in the web app."
