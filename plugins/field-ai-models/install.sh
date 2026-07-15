#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='field-ai-models'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/field-ai'
install -d -m 0775 '/opt/mappi3/models'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"capability_tier":"prototype-cue-pack","installed_at":"$(date -Is)","features":["natureAI","plantPrototypeCue","cloudPrototypeCue","fungiPrototypeCue","animalTrackPrototypeCue","bugPrototypeCue","rockPrototypeCue","barcodeOcrPrototypeCue","injurySafetyRouter","curatedFieldGuideFallbacks"],"note":"Offline prototype JSON cue models, safety routers, and field-guide fallbacks are enabled. Real specialist TFLite/NCNN/OCR models are not installed by this pack."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
MapPI3 Field AI Prototype Cue Pack

This pack prepares offline model folders/markers and enables bundled prototype JSON cue models plus curated field-guide fallbacks.
It does not install real specialist TFLite/NCNN/OCR recognition binaries.
Use MapPI3 status/self-test endpoints to verify prototype cues and keep safety wording honest.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: prototype cue pack + curated fallbacks ready; specialist models not installed."
