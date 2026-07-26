#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ID='field-ai-models'
MARKER_DIR="/var/lib/mappi3/plugins/$PLUGIN_ID"
install -d -m 0775 "$MARKER_DIR"
install -d -m 0775 '/var/lib/mappi3/field-ai'
install -d -m 0775 '/opt/mappi3/models'

APT_STATUS='not-run'
APT_NOTE='Run on the Pi during online maintenance to install real barcode/OCR/TFLite backends.'
TFLITE_RUNNER_STATUS='not-run'
TFLITE_RUNNER_NOTE='TensorFlow Lite C runner not attempted.'
if command -v apt-get >/dev/null 2>&1; then
  if [ "${MAPPI3_INSTALL_FIELD_AI_BACKENDS:-1}" != "0" ]; then
    export DEBIAN_FRONTEND=noninteractive
    APT_STATUS='attempted'
    APT_PACKAGES=(python3-pil python3-pyzbar tesseract-ocr zbar-tools)
    if [ "${MAPPI3_INSTALL_TFLITE_RUNNER:-1}" != "0" ]; then
      APT_PACKAGES+=(g++ pkg-config libtensorflow-lite-dev)
    fi
    if apt-get update && apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"; then
      APT_STATUS='installed'
      APT_NOTE='Installed local barcode/OCR backends and requested lightweight TensorFlow Lite runner dependencies.'
    else
      APT_STATUS='failed'
      APT_NOTE='Could not install all Field AI apt packages; prototype cue pack remains available.'
    fi
  else
    APT_STATUS='skipped'
    APT_NOTE='MAPPI3_INSTALL_FIELD_AI_BACKENDS=0; backend package install skipped.'
  fi
fi

if [ "${MAPPI3_INSTALL_TFLITE_RUNNER:-1}" != "0" ]; then
  TFLITE_RUNNER_STATUS='attempted'
  SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if command -v g++ >/dev/null 2>&1 && command -v pkg-config >/dev/null 2>&1 && pkg-config --exists tensorflow-lite && [ -f "$SRC_DIR/mappi3-tflite-runner.cc" ]; then
    install -d -m 0755 /opt/mappi3/runners
    install -m 0644 "$SRC_DIR/mappi3-tflite-runner.cc" /opt/mappi3/runners/mappi3-tflite-runner.cc
    if g++ -std=c++17 -O2 "$SRC_DIR/mappi3-tflite-runner.cc" -o /usr/local/bin/mappi3-tflite-runner $(pkg-config --cflags --libs tensorflow-lite); then
      chmod 0755 /usr/local/bin/mappi3-tflite-runner
      TFLITE_RUNNER_STATUS='installed'
      TFLITE_RUNNER_NOTE='Installed /usr/local/bin/mappi3-tflite-runner using TensorFlow Lite C API. Run it against a verified .tflite model before marking image classifiers active.'
    else
      TFLITE_RUNNER_STATUS='failed-build'
      TFLITE_RUNNER_NOTE='Could not compile mappi3-tflite-runner; keep image classifier runtime inactive.'
    fi
  else
    TFLITE_RUNNER_STATUS='missing-deps'
    TFLITE_RUNNER_NOTE='Missing g++, pkg-config, tensorflow-lite pkg-config entry, or runner source; keep image classifier runtime inactive.'
  fi
else
  TFLITE_RUNNER_STATUS='skipped'
  TFLITE_RUNNER_NOTE='MAPPI3_INSTALL_TFLITE_RUNNER=0; TensorFlow Lite runner skipped.'
fi

cat > "$MARKER_DIR/installed.json" <<JSON
{"id":"$PLUGIN_ID","status":"installed","offline_safe":true,"capability_tier":"prototype-cue-pack-plus-barcode-ocr-tflite-runner","installed_at":"$(date -Is)","apt_status":"$APT_STATUS","tflite_runner_status":"$TFLITE_RUNNER_STATUS","features":["natureAI","plantPrototypeCue","cloudPrototypeCue","fungiPrototypeCue","animalTrackPrototypeCue","bugPrototypeCue","rockPrototypeCue","barcodeOcrPrototypeCue","barcodeZbarBackend","tesseractOcrBackend","tfliteCapiRunner","injurySafetyRouter","curatedFieldGuideFallbacks","tfliteNcnnModelSlots"],"note":"Offline prototype JSON cue models, safety routers, field-guide fallbacks, real barcode/OCR backend hooks, and an optional TensorFlow Lite C runner are enabled. Specialist recognition still requires vetted model files plus live inference verification."}
JSON
cat > "$MARKER_DIR/README.txt" <<TXT
MapPI3 Field AI Model Pack

This pack prepares offline model folders/markers and enables bundled prototype JSON cue models plus curated field-guide fallbacks.

Real backend added now:
- Barcode/QR decode path via pyzbar/libzbar or zbarimg when installed.
- OCR text path via Tesseract/pytesseract or tesseract CLI when installed.
- Optional TensorFlow Lite C API runner at /usr/local/bin/mappi3-tflite-runner when libtensorflow-lite-dev is available.

Specialist/cue-router model policy:
- Keep unverified candidates under /opt/mappi3/model-candidates with MANIFEST.json.
- Add only vetted INT8/TFLite or NCNN files under /opt/mappi3/models for active specialist work.
- Verify with /api/field-ai/status and a real runner smoke before treating image classification as live.
- Do not use Debian ONNX runtime on the Zero 2 W lane unless a Pi-safe build is proven.

$APT_NOTE
$TFLITE_RUNNER_NOTE
TXT
echo "MapPI3 plugin $PLUGIN_ID installed: prototype cue pack + barcode/OCR backend hooks + optional TFLite runner; apt=$APT_STATUS; tflite_runner=$TFLITE_RUNNER_STATUS."
