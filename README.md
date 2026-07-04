# MapPi3

**Version:** V1.0.1  
**Status:** phone-first trail OS/app seed  
**Owner:** CAK3D / Maple

MapPi3 is a Raspberry Pi Zero 2 WH trail-navigation OS/app concept: an AllTrails-style, offline-first field companion that runs from a Pi hotspot, serves a polished mobile web app, reads GPS, manages route packs, and later integrates Sense HAT compass/LED matrix, Supabase sync, GitHub, Vercel, and Raspberry Pi Imager OS builds.

> Safety: MapPi3 assists route planning and field awareness. It does **not** replace paper maps, a real compass, emergency beacon, local guidance, or emergency services.

## V1.0.1 contents

- Git-ready repo scaffold
- Vite/React mobile PWA-style UI prototype
- Offline/hotspot-first product docs
- Supabase/Vercel/GitHub placeholders without secrets
- Route/map/download/sync UX mock data
- Sense HAT LED compass calibration flow design

## Quick start

```bash
cd /home/ubuntu/MapPi3
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://<pi-or-vm-ip>:5173` on a phone/tablet.

## Build check

```bash
npm run build
npm run smoke
```

## Rollback for V1.0.1

This is a new project. To roll back this pass before any remote push:

```bash
rm -rf /home/ubuntu/MapPi3
```

After GitHub exists, rollback should use branches/tags/releases instead of deleting the workspace.
