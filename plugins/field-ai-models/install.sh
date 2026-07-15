#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='field-ai-models'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/field-ai'
install -d -m 0775 '/opt/mappi3/models'

APT_STATUS='not-run'
APT_NOTE='Run on the Pi during online maintenance to install real barcode/OCR backends.'
if command -v apt-get >/dev/null 2>&1; then
  if [ "${MAPPI3_INSTALL_FIELD_AI_BACKENDS:-1}" != "0" ]; then
    export DEBIAN_FRONTEND=noninteractive
    APT_STATUS='attempted'
    if apt-get update && apt-get install -y --no-install-recommends python3-pil python3-pyzbar tesseract-ocr zbar-tools; then
      APT_STATUS='installed'
      APT_NOTE='Installed local barcode/OCR backends: Pillow, pyzbar/libzbar, zbarimg, and Tesseract OCR.'
    else
      APT_STATUS='failed'
      APT_NOTE='Could not install barcode/OCR apt packages; prototype cue pack remains available.'
    fi
  else
    APT_STATUS='skipped'
    APT_NOTE='MAPPI3_INSTALL_FIELD_AI_BACKENDS=0; backend package install skipped.'
  fi
fi

cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"capability_tier":"prototype-cue-pack-plus-barcode-ocr-backends","installed_at":"$(date -Is)","apt_status":"$APT_STATUS","features":["natureAI","plantPrototypeCue","cloudPrototypeCue","fungiPrototypeCue","animalTrackPrototypeCue","bugPrototypeCue","rockPrototypeCue","barcodeOcrPrototypeCue","barcodeZbarBackend","tesseractOcrBackend","injurySafetyRouter","curatedFieldGuideFallbacks","tfliteOnnxModelSlots"],"note":"Offline prototype JSON cue models, safety routers, field-guide fallbacks, and real barcode/OCR backend hooks are enabled. Plant/fungi/animal/cloud/rock species models still require vetted TFLite/ONNX/NCNN files."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
MapPI3 Field AI Model Pack

This pack prepares offline model folders/markers and enables bundled prototype JSON cue models plus curated field-guide fallbacks.

Real backend added now:
- Barcode/QR decode path via pyzbar/libzbar or zbarimg when installed.
- OCR text path via Tesseract/pytesseract or tesseract CLI when installed.

Specialist species/geology/weather classifiers are still model-slot based:
- Add vetted INT8/TFLite, ONNX, or NCNN files under /opt/mappi3/models.
- Verify with /api/field-ai/status and /api/command/field-ai-verify before treating them as live recognition.

$APT_NOTE
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: prototype cue pack + barcode/OCR backend hooks ready; apt=$APT_STATUS."
