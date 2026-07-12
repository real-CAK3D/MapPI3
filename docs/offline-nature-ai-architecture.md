# MapPI3 Offline Nature AI Architecture

Target: Raspberry Pi Zero 2 W + phone + Pi hotspot, no internet/cloud after setup.

## Current implementation

- App tab: **Nature AI**
- Pi API: `/api/field-ai/status`, `/api/field-ai/categories`, `/api/field-ai/analyze`, `/api/field-ai/history`
- Storage: `/var/lib/mappi3/field-ai/field_guide.db` SQLite
- Uploads: `/var/lib/mappi3/field-ai/uploads/`
- Model directory: `/opt/mappi3/models/`
- Current analysis mode: safe offline reference/database fallback until specialist TFLite/NCNN models are installed.

## Plugin model

SQLite table `plugins` tracks model/reference modules. Drop model files into `/opt/mappi3/models`, then enable the matching plugin row/config. Zero 2 W policy: load one model at a time; prefer INT8 TensorFlow Lite/NCNN MobileNetV3-Small or nano detectors, 224/320 input.

## Safety

- Never mark plants/mushrooms safe to eat from photo only.
- Never diagnose injury/rash/bite/burn/wound from image. Use fixed emergency red-flag decision trees.
- Clouds are observations, not forecasts.

## Future plugin slots

plants, trees, leaves, bark, flowers, mushrooms/fungi, animals/birds/mammals/fish/reptiles/amphibians, insects/spiders, tracks/scat, clouds, visible injury triage, first aid, survival guide, barcode/QR/OCR, rocks/minerals, water quality, speech recognition, local TTS, AI conversation mode, Bluetooth sensors, backup/restore, Docker/OTA packaging, diagnostics.
