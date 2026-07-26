#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='sky-forage'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFLINE_PACK_ROOT='/var/lib/mappi3/offline-packs/sky-forage'
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/field-guides/sky'
install -d -m 0775 '/var/lib/mappi3/field-guides/forage'
install -d -m 0775 "$OFFLINE_PACK_ROOT"
if [ -d "$SOURCE_DIR/offline-data" ]; then
  find "$OFFLINE_PACK_ROOT" -mindepth 1 -maxdepth 1 -type f -delete
  cp -a "$SOURCE_DIR/offline-data/." "$OFFLINE_PACK_ROOT/"
  chmod -R a+rX "$OFFLINE_PACK_ROOT"
fi
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["sky", "cameraOverlay", "forage", "wildFoodSafety", "offlineTrailPack", "offlineSkyPack", "networkOnlyLabels"],"offline_pack_root":"$OFFLINE_PACK_ROOT","offline_manifest":"$OFFLINE_PACK_ROOT/MANIFEST.json","note":"Sky/forage guide storage plus compact trail/sky offline starter pack installed. Live public APIs remain network-only unless cached/precomputed."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Sky/forage guide storage ready; pages are built into the app.
Compact offline pack files install to: $OFFLINE_PACK_ROOT
Live trail/map/weather/astronomy API sources are labeled network-only unless a dated cache/precomputed export is present in the offline pack folder.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Sky/forage guide storage and compact offline trail/sky pack ready."
