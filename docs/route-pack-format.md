# MapPi3 Route Pack Format — V1.0.4

MapPi3 route packs are the local/offline unit that will eventually be downloaded to the Pi SD card before a hike.

## Current files

- `src/data/routePacks.json` — sample route-pack catalog.
- `src/data/routePacks.js` — mapper that converts route packs into UI cards while preserving raw geometry/offline metadata.

## Schema name

```text
mappi3.routePack.v1
```

## Core fields

| Field | Purpose |
| --- | --- |
| `id` | Stable local/sync identifier. |
| `schemaVersion` | Route-pack schema version. |
| `name`, `place`, `region` | Human-readable route discovery fields. |
| `summary` | Route-card/detail description. |
| `difficulty`, `routeType`, `tags` | Explore/search filters. |
| `status` | Local UI/cache state: `Downloaded`, `Ready`, `Not saved`, etc. |
| `distanceMiles`, `estimatedTime`, `elevationGainFt` | Trail stats. |
| `storageEstimateMb` | SD-card planning estimate before download. |
| `sync` | Future Supabase/public/private sync status. |
| `offline` | MBTiles/cache corridor plan. |
| `geometry` | GeoJSON-style route geometry. |
| `mapPreviewPath` | Temporary SVG preview path until real map rendering lands. |
| `waypoints` | Ordered navigation points. |
| `pois` | Water/shelter/view/caution/camp/custom field markers. |

## Offline field

```json
{
  "required": true,
  "tileFormat": "MBTiles",
  "tileBounds": [-82.552, 39.421, -82.522, 39.438],
  "minZoom": 11,
  "maxZoom": 16,
  "layers": ["trail", "topo", "hillshade", "contours"]
}
```

This models the future download-before-hike flow: MapPi3 searches online when connected, estimates storage, downloads a corridor/area bundle, then serves the map locally over the Pi hotspot.

## Supabase readiness

The route pack shape intentionally separates browser-safe public catalog fields from future privileged sync work. Public route metadata can be read by the frontend. Writes, private packs, and public publishing should go through Supabase RLS and/or Edge Functions later.

## Safety note

Route packs can be stale. Water, shelter, trail closures, hazards, and weather must be treated as advisory field context, not guaranteed truth.
