# MapPi3 V1.0.1 Product Spec

## Mission

MapPi3 is a phone-first trail navigation system for Raspberry Pi Zero 2 WH. The Pi hosts a local hotspot and serves a rich trail app that supports route discovery, custom planning, waypoints, POIs, offline map packs, live GPS tracking, weather context, Sense HAT compass behavior, and survival reference content.

## Operating model

1. At home/camp/network: search locations and route packs online, sync saved tracks, download offline map/route bundles to the Pi SD card.
2. On trail: connect phone to Pi hotspot, open MapPi3 locally, navigate with GPS, record breadcrumb trail, and use downloaded data only.
3. After hike: reconnect to a network and upload/sync tracks if enabled.

## AllTrails-like but original

MapPi3 should feel polished and familiar to a hiking-app user: search, route cards, map layers, saved hikes, custom route drawing, waypoints, POIs, and live stats. It must not copy AllTrails branding, proprietary assets, protected UI art, or data.

## Priority features

- Mobile-first PWA shell
- Explore/search flow
- Download-to-Pi route/map pack flow
- Custom route builder
- GPX import/export
- Live GPS marker and breadcrumb track
- Waypoints and POIs: water, shelter, camp, view, danger, parking, restroom, crossing, custom
- Weather online + cached/offline fallback
- Survival tips stored locally
- Sense HAT LED north arrow with calibration
- Settings and customization

## Future integrations

- GitHub repo and CI
- Supabase browser-safe sync plus Edge Functions for privileged work
- Vercel hosted companion/marketing/admin app
- Raspberry Pi Imager `.img.xz` OS image pipeline
