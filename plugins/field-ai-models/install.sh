#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='field-ai-models'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/field-ai'
install -d -m 0775 '/opt/mappi3/models'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["natureAI", "plantModel", "cloudModel", "fungiModel", "animalModel", "bugModel", "rocks", "barcode", "ocr"],"note":"Prototype offline field-AI model slots and DB folders ready."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Prototype offline field-AI model slots and DB folders ready.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Prototype offline field-AI model slots and DB folders ready."
