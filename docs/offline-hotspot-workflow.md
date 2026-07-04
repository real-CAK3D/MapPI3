# Offline + Hotspot Workflow

## Default field mode

The Pi Zero 2 WH creates a Wi‑Fi hotspot. A phone connects and opens the MapPi3 web UI from the Pi. The app must continue working with no internet.

## Connected mode

When the Pi is connected to known Wi‑Fi or the phone provides internet, MapPi3 may:

- search online geocoders/trail sources
- fetch weather
- download MBTiles/route packs
- upload completed tracks
- sync saved routes through Supabase

## Download-before-hike model

Before a hike, the user searches the destination and taps **Download to Pi SD**. A route pack should include:

- route geometry / GPX / GeoJSON
- waypoints and POIs
- offline map tiles for route corridor
- topo/hillshade/contour overlays where available
- cached weather/sunrise/sunset snapshot
- survival notes relevant to terrain/season where possible

## Storage guardrails

- Show estimated SD card usage before download.
- Let user remove old route packs.
- Keep base app small and packs modular.
