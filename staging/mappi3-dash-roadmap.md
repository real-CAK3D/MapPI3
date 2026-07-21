# MapPI3 Dash Roadmap — directions, compass, weather, buddy, pages

Status: draft for Pi/Whisplay + mobile mirror. Public safety stance: MapPI3 assists planning/navigation/reference only; carry real map/compass/phone/SOS tools.

## 1. Dash page set

### Buddy Home
- Foreground Whisplay-friendly happy trail buddy face.
- Quick status chips: GPS fix, compass source, weather age, battery/power mode, hotspot/client state.
- Event popups: Sense HAT Pac-Man/game events, hydration reminders, route warnings, GPS fix/loss, weather alerts.
- One-button/joystick actions once input path is healthy: next card, acknowledge popup, quick mark waypoint.

### Navigate
- Route title, distance remaining, bearing arrow, next waypoint, ETA/stamina estimate.
- Offline-first route geometry and GPX breadcrumbs; warn when geometry is seed/rough instead of verified GPX.
- Large field-readable states: `On route`, `Off route?`, `GPS weak`, `Backtrack suggested`, `Stop / observe / plan`.
- Directions are guidance only, not legal/safety authority.

### Compass + Level
- Sense HAT compass when on Pi; phone compass/mobile simulator when in Vercel/cloud mode.
- Modes: big cardinal, bearing-to-next, bubble level, mounted-orientation calibration, rotation test.
- Calibration page links: metal warning, figure-eight reminder, mounted rotation selection.

### Weather + Sky
- Current weather card: temp, wind, precipitation, humidity, pressure trend, last refresh age.
- NOAA/offline fallback panel when network is absent.
- Trail risk chips: heat/cold, wind, storm, daylight, precipitation, air quality if available.
- Sky page can reuse heading/pitch for basic object finder later.

### Route / Marker Pages
- Route list, active route, waypoints/POIs, water/dog stops, trailhead/parking, offline pack status.
- Quick marker creation: note, hazard, water, photo later, backtrack point.
- GPX import/export and offline map pack cache status.

### Field Kit / Power
- Pi stats: CPU, memory, disk, temp, Wi-Fi/hotspot, Bluetooth PAN, Tailscale, GPS, Sense HAT.
- Power profiles: bright/home, field, low-power, emergency beacon/SOS.
- Recovery actions: restart web, GPS diagnose, Sense diagnose, network status; dangerous actions require confirmation.

### Games / Break Mode
- Whisplay mini-games and Sense HAT animations run low-power, pauseable, and non-critical.
- Game events may raise buddy popups, but should never mask safety/weather/navigation alerts.

## 2. Data contracts

### `/api/sense`
- Keep `sense.mode`, `sense.ok`, orientation/weather fields, and display-specific payloads.
- Pac-Man now exposes `sense.pacman_display.events[]` and `last_event_id` for bridges.
- Events include `id`, `seq`, `type`, `label`, `score_delta`, `score`, `fruit_count`, `map_index`, and optional event-specific fields.

### Whisplay dashboard polling
- Poll `/api/sense` locally from the Pi.
- De-dupe event IDs in-process.
- Render short 2–3 second popups, then return to active Dash page.
- Never require joystick for popups; joystick can later acknowledge/advance once hardware events work.

## 3. Implementation phases

1. **Event bridge baseline** — Pac-Man event queue in Sense cache + Whisplay Dash popup renderer. Local build/compile verified.
2. **Dash cards** — split current MapPI3 Dash into explicit Home, Navigate, Compass, Weather, Safety, Field Kit pages.
3. **Live route feed** — active route + next waypoint + distance/bearing + off-route warning endpoint.
4. **Weather risk feed** — summarize NOAA/local weather into field-readable risk chips with stale/offline states.
5. **Buddy animation layer** — happy/default face plus weather/power/GPS/surprise expressions; scared/mad only for rare real warnings.
6. **Input bridge** — once Linux joystick events are healthy, route input through `joystick_mode = smart | whisplay | sense`.
7. **Offline sync** — queue markers/events offline and sync route notes later.

## 4. Verification checklist

- `python3 -m py_compile local-pi-imager/boot-partition-copy/mappi3-agent.py`
- Extract/compile embedded `mappi3_whisplay_dashboard.py` from installer.
- `bash -n staging/install-whisplay-mappi3-apps-and-bt-tether.sh staging/verify-whisplay-mappi3-apps-and-bt-tether.sh`
- `npm run build`
- On live Pi after approval/connectivity: install script, restart `mappi3-web.service`/Whisplay as needed, set Sense mode to Pac-Man, verify `/api/sense` events and Whisplay popup display.
