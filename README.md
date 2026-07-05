# MapPI3

**Version:** V1.2.29  
**Owner:** CAK3D / Maple  
**Status:** phone-first trail app with local accounts, offline route packs, OSM-backed priority trail geometry, and Supabase/GitHub readiness.

MapPI3 is a mobile-first trail companion for planning, launching, and navigating hikes. It is designed for the current phone/Tailscale workflow and the future Raspberry Pi Zero 2 WH field-kit path.

> Safety: MapPI3 assists route planning and field awareness. It does **not** replace paper maps, a real compass, emergency beacon, official trail maps, local guidance, or emergency services.

## Current highlights

- Route search stays empty until typed; results drill down by area → mountain/cluster → trail.
- Near-me ranking and search radius controls keep local results close unless expanded.
- Maine/Lewiston-Auburn/Grafton Notch/Route 26 route catalog.
- OSM/Overpass geometry imported for priority Grafton routes including Speck Pond, Table Rock, Old Speck/Eyebrow area, and Mahoosuc/AT segment.
- Leaflet/OpenStreetMap route and GPS views.
- Launch checklist with sunrise/sunset, leave-time, turn-around, water/calorie/battery planning.
- Local Account tab for CAK3D, tiny-Z, and Guest device sessions.
- Local completion log for trails; Supabase schema/readiness docs included.

## Quick start

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 8080
```

For phone GPS/location features, use a secure HTTPS origin such as the configured Tailscale Serve URL.

## Build and smoke check

```bash
npm run build
npm run smoke
npm audit --audit-level=high
```

## Supabase

Only browser-safe values belong in the frontend:

```text
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
```

Do **not** commit database passwords, secret/service keys, JWT secrets, or personal access tokens. See:

```text
docs/supabase-schema.sql
docs/integrations.md
```

## Field-data honesty

Routes marked as OSM geometry use real OpenStreetMap/Overpass lines but still require current access, closure, weather, and trail-condition verification before field reliance. Routes still marked as rough seed geometry need GPX/OSM/Supabase enrichment before they should be trusted for exact navigation.
