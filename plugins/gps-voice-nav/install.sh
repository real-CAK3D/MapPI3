#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='gps-voice-nav'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/voice'
install -d -m 0775 '/var/lib/mappi3/voice/prompts'
cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"installed_at":"$(date -Is)","features":["voiceCommands", "offlineTts", "turnByTurn", "hydrationByDistance"],"note":"Voice prompt manifest ready; phone speech fallback works, offline TTS engine is future optional."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
Voice prompt manifest ready; phone speech fallback works, offline TTS engine is future optional.
Installed by MapPI3 plugin installer. This marker is safe to remove via uninstall.sh.
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: Voice prompt manifest ready; phone speech fallback works, offline TTS engine is future optional."
