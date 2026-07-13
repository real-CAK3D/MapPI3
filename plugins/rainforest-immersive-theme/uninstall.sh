#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='rainforest-immersive-theme'
rm -rf "/var/lib/mappi3/plugins/$PLUGIN_ID"
echo "MapPI3 plugin $PLUGIN_ID uninstalled marker removed. User data/cache folders are preserved."
