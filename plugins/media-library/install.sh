#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='media-library'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/media'
install -d -m 0775 '/var/lib/mappi3/media/ambient'
install -d -m 0775 '/var/lib/mappi3/media/music'
install -d -m 0775 '/var/lib/mappi3/media/videos'
install -d -m 0775 '/var/lib/mappi3/media/playlists'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["mediaLibrary", "music", "video", "playlists", "storageScan"],"note":"Media folders ready; user media is preserved."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Media folders ready; user media is preserved.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Media folders ready; user media is preserved."
