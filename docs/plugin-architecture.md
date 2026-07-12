# MapPI3 Plugin Architecture Roadmap

MapPI3 should ship as:

1. **Basic Pi Zero 2 WH image** — app, hotspot/captive portal, GPS hooks, weather cache, route packs, safety/SOS essentials.
2. **Full image** — preloads proven optional packs for larger SD cards/lab builds.
3. **Plugin Library** — per-plugin install folders/scripts that can be queued in the app and installed when the Pi has internet.

## Plugin pack shape

Each plugin should live under `plugins/<id>/` with:

- `plugin.json` metadata: id, name, targets, required hardware, disk/RAM estimate, services, app feature toggles.
- `install.sh` idempotent installer.
- `uninstall.sh` rollback/removal path.
- optional `assets/`, `systemd/`, `models/`, `docs/`.

## Planned packs

- `media-library`: stream `/var/lib/mappi3/media` music/videos to phone; larger SD card recommended.
- `ambient-sounds`: offline rain/creek/forest/night loops; Sense HAT pulse/on-off toggle.
- `sense-games`: Magic 8 Ball, Snake, color/border themes, hydration icon alarms.
- `field-ai-models`: prototype JSON/TFLite model packs.
- `noaa-weather`: NOAA/NWS text products when online, weather cache, future RTL-SDR/weather satellite receiver path.
- `gps-voice-nav`: phone speech/notifications triggered by GPS route markers.

## Satellite/weather note

Without extra radio hardware, MapPI3 can fetch satellite/weather *data products* over internet (NOAA/NWS/Open-Meteo). Direct satellite reception would require a receiver such as RTL-SDR/weather-satellite hardware and belongs in a separate plugin pack.

## Nested feature toggles

Plugin packs can expose nested features in addition to top-level app toggles. Example: `sense-games` owns the Sense HAT base but exposes Compass, Liquid, SOS, Flashlight, Magic 8 Ball, Snake, hydration alarms, and color/border themes. The app stores these under `settings.pluginSubFeatures[packId][featureId]`. Installers should read/write compatible feature defaults without breaking the base app when optional packages are absent.
