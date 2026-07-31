# MapPI3 offline RGB565 map packs

MapPI3's field-map target is phone-free and network-free once a trip pack is built:

```text
OSM extract/style
  -> pre-rendered 256x256 map tiles
  -> RGB565 raw tile conversion
  -> fixed-grid zoom pack on microSD
  -> Pi/Whisplay reads tiles by math offset
```

This document captures the safe start for the pack lane. It does **not** require downloading a giant tile set.

## Budget rule

Every raw RGB565 tile is fixed size:

```text
256 * 256 * 2 bytes = 131,072 bytes per tile
```

That makes storage predictable before any download/conversion.

For broad circular coverage, keep blanket coverage at overview/medium zooms and add high zoom only for selected trail corridors, parks, towns, or route buffers.

## Current-location 150-mile baseline

Using live MapPI3 GPS from `/api/status` on 2026-07-30:

- center: `44.097351415, -70.162873781`
- radius: `150 miles`
- theme: `topo-night`
- generated plan: `public/map-packs/plans/mappi3-current-150mi-topo-night.plan.json`

Recommended blanket:

- z0-z12
- 6,664 tiles
- about 0.813 GiB raw RGB565

Avoid a blanket z14 pack for the whole 150-mile radius unless CAK3D explicitly wants to spend the storage:

- z13 alone adds about 2.359 GiB
- z14 alone adds about 9.299 GiB
- z0-z14 cumulative is about 12.47 GiB raw RGB565 for this 150-mile radius

## Planner command

```bash
npm run map-pack:plan -- \
  --lat 44.097351415 \
  --lon -70.162873781 \
  --radius-miles 150 \
  --blanket-max-zoom 12 \
  --max-zoom 14 \
  --budget-gib 4 \
  --theme topo-night \
  --id mappi3-current-150mi-topo-night \
  --name "MapPI3 current-location 150mi Topo Night" \
  --source "live MapPI3 GPS /api/status 2026-07-30" \
  --out public/map-packs/plans/mappi3-current-150mi-topo-night.plan.json
```

The planner is dry-run only. It creates the size/offset/zoom manifest before any tile download.

## Pack format direction

A future built pack should use a tiny JSON manifest plus one fixed-grid data file per zoom/theme:

```text
/var/lib/mappi3/map-packs/<region>/<theme>/MANIFEST.json
/var/lib/mappi3/map-packs/<region>/<theme>/z0.rgb565pack
/var/lib/mappi3/map-packs/<region>/<theme>/z1.rgb565pack
...
```

Offset formula inside a zoom pack:

```text
offset = ((y - y_min) * width_tiles + (x - x_min)) * 131072
```

No per-tile index is needed because x/y bounds are in the manifest and every tile is fixed-size.

## Browser vs Whisplay

- Whisplay/Pi-native rendering can read RGB565 directly.
- The browser/Leaflet UI still needs PNG/WebP tiles or a canvas layer that converts RGB565 into browser pixels.
- MapPI3 should keep current `/tiles/{z}/{x}/{y}.png` compatibility while adding the native RGB565 fast lane.

## Safety

MapPI3 assists navigation but does not replace official/current maps, compass, emergency comms, training, or weather judgment.
