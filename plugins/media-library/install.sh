#!/usr/bin/env bash
set -euo pipefail
install -d -m 0775 /var/lib/mappi3/media /var/lib/mappi3/media/ambient /var/lib/mappi3/media/music /var/lib/mappi3/media/videos
echo "Media library folders ready under /var/lib/mappi3/media. Copy your own audio/video files and scan from the app."
