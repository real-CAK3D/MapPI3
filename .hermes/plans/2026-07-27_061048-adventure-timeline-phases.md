# MapPI3 Adventure Timeline Implementation Phases

> **For Hermes:** Use subagent-driven-development skill to implement each approved phase task-by-task. Do not deploy to the live Pi or restart services without CAK3D approval and a rollback path.

**Goal:** Turn the `mappi3new.txt` Adventure Timeline idea into MapPI3's primary interactive trip-memory feature while preserving current offline-first Pi Zero 2 W constraints.

**Architecture:** Build from the current React/Vite single-page app first, using local/sample data and existing route/walk/journal/wildlife state. Then add durable local trip/event/sample models and Pi agent endpoints in later phases. Keep timeline rendering virtualized/windowed before adding replay, search, export, and automatic detectors.

**Tech Stack:** React/Vite frontend in `/home/ubuntu/MapPi3/src/main.jsx`, CSS in `/home/ubuntu/MapPi3/src/styles.css`, map helper in `/home/ubuntu/MapPi3/src/components/LiveLeafletMap.jsx`, route/manual data in `/home/ubuntu/MapPi3/src/data/`, Pi backend in `/home/ubuntu/MapPi3/local-pi-imager/boot-partition-copy/mappi3-agent.py`.

---

## Current Context

Source prompt file reviewed on NukeBox:

```text
C:\Users\CAK3D\OneDrive\Desktop\CAK3D_Codex\mappi3new.txt
```

Current MapPI3 already covers most broad offline trail OS lanes:

- Offline AI / route-aware helper lanes.
- Offline mapping, route packs, local tiles, GPX/JSON route import/export, custom POIs.
- Hiking dashboard, active navigation, Daily Exercise recording, route progress/off-route feet.
- Weather, sky/astronomy, survival guide, medical guide, nature guide, AI vision, emergency mode, gear manager.
- Sense HAT LED modes/status/SOS/compass/liquid/joystick flows.

Primary gap: a real Adventure Timeline that links GPS, map, sensor history, journal, media, sightings, warnings, and replay into one scrub-able journey memory.

---

## Phase 0 — Safety/Scope Guardrails Before Code

**Goal:** Agree on boundaries before implementation.

**Approved assumptions unless CAK3D says otherwise:**

1. Start with browser/local MVP; no Pi service restart required.
2. Keep all core timeline behavior offline/local by default.
3. Do not add heavy dependencies for the Pi Zero 2 W path.
4. Do not present AI identifications as edible/safe guarantees.
5. Do not add cloud upload/sync unless explicit later approval.
6. Any Pi backend/service/deploy work needs rollback and user approval.

**Review checkpoint:** CAK3D approves moving into Phase 1.

---

## Phase 1 — Adventure Timeline MVP UI

**Goal:** Create the first visible Adventure Timeline screen with a fixed playhead, draggable/scrollable timeline, event pins, details, layers, and map sync using existing local data and generated safe demo events.

**Why first:** It lets CAK3D feel the feature immediately without risking Pi services or backend storage.

### Phase 1.1 — Add Timeline tab/hub entry

**Files likely to change:**

- Modify: `src/main.jsx`
- Modify: `src/styles.css`

**Tasks:**

1. Add `Adventure` or `Timeline` to the top-level tab list or Navigate/Survival hub.
2. Create placeholder `AdventureTimeline` component.
3. Route selected tab to the component in `ActiveTab`.
4. Add field-readable empty state: “No trip loaded yet — use selected route/demo trip/local walk.”

**Verify:**

```bash
cd /home/ubuntu/MapPi3
npm run build
npm run smoke
```

Expected: build and smoke pass; timeline tab appears in browser.

### Phase 1.2 — Define lightweight frontend timeline sample builder

**Files likely to change:**

- Modify or create: `src/data/timelineSamples.js`
- Modify: `src/main.jsx`

**Tasks:**

1. Build demo events from selected route waypoints, saved walks, completed trails, journal draft, wildlife draft, weather conditions, battery/status fallbacks.
2. Normalize events into a common shape:
   - `id`
   - `timestamp`
   - `category`
   - `eventType`
   - `title`
   - `description`
   - `lat`, `lon`, `altitudeMeters`
   - `severity`
   - `source`
   - `bookmarked`
   - `metadata`
3. Keep this frontend-only for Phase 1.

**Verify:** timeline loads route-aware sample pins without crashing when no walk exists.

### Phase 1.3 — Add fixed playhead + horizontal scrubber

**Files likely to change:**

- Modify: `src/main.jsx`
- Modify: `src/styles.css`

**Tasks:**

1. Add central playhead/cursor.
2. Add horizontally scrollable track.
3. Support touch swipe, mouse drag, wheel/trackpad scroll.
4. Add keyboard left/right navigation.
5. Add previous/next event buttons.
6. Add jump to beginning/current/end buttons.

**Verify:** On desktop and mobile viewport, scrubber moves while playhead stays centered.

### Phase 1.4 — Add visible event pins

**Files likely to change:**

- Modify: `src/main.jsx`
- Modify: `src/styles.css`

**Tasks:**

1. Render category pins at their time position.
2. Use icons/colors/text labels:
   - trip start/end
   - photo/media
   - note
   - wildlife
   - nature ID
   - water
   - campsite/shelter
   - summit/view
   - weather
   - warning
   - emergency
   - battery
   - GPS status
3. Keep labels readable and non-color-only.
4. Add selected/near-playhead highlight.

**Verify:** Pins appear and selected pin updates when scrubbing.

### Phase 1.5 — Add event details bottom sheet

**Files likely to change:**

- Modify: `src/main.jsx`
- Modify: `src/styles.css`

**Tasks:**

1. Selecting pin opens detail sheet.
2. Display recorded facts vs calculated vs user-entered vs AI suggestion labels.
3. Include time, location, route mile, sensor snapshot, notes, AI confidence when present.
4. Add non-destructive buttons: bookmark/favorite, view on map, close.
5. Do not implement delete/edit mutations yet unless simple local-only.

**Verify:** Details open/close reliably on touch and desktop.

### Phase 1.6 — Add timeline layers/filters

**Files likely to change:**

- Modify: `src/main.jsx`
- Modify: `src/styles.css`

**Tasks:**

1. Layer toggles: route, weather, journal, wildlife, nature, water, campsites, warnings, emergency, battery, GPS.
2. Store layer state in localStorage, e.g. `mappi3.timelineLayers`.
3. Filtering hides events but never permanently deletes data.
4. Critical events should show “critical filtered” notice if hidden.

**Verify:** Toggle persistence survives page refresh.

### Phase 1.7 — Sync timeline to existing map

**Files likely to change:**

- Modify: `src/main.jsx`
- Possibly modify: `src/components/LiveLeafletMap.jsx`

**Tasks:**

1. Move map marker to selected timeline event/location.
2. Show selected route and nearby route waypoints.
3. If selected time has no GPS, label “location unavailable / last known.”
4. Add “follow map” toggle so map does not fight the user.

**Verify:** Selecting event focuses map without breaking existing Navigate/Explore maps.

**Phase 1 acceptance criteria:**

- Timeline is visible and mobile-first.
- User can scrub/drag/tap through events.
- Pins and details work.
- Layers persist locally.
- Map can follow selected event.
- No backend/service/deploy changes required.
- `npm run build` and `npm run smoke` pass.

**Review checkpoint:** CAK3D decides what Phase 1 UI needs before Phase 2.

---

## Phase 2 — Real Local Trip/Event Model

**Goal:** Move from demo/generated timeline data toward durable, structured trip memory that survives refresh/restart.

### Phase 2.1 — Add shared timeline model helpers

**Files likely to change:**

- Create: `src/data/timelineModel.js`
- Modify: `src/main.jsx`

**Core shapes:**

```js
export const TIMELINE_EVENT_CATEGORIES = [
  'route','photo','journal','wildlife','nature','water','campsite','weather',
  'warning','emergency','battery','gps','device','manual'
];
```

Event fields should mirror the source spec but stay optional:

- `id`
- `tripId`
- `timestamp`
- `eventType`
- `category`
- `severity`
- `title`
- `description`
- `latitude`, `longitude`, `altitudeMeters`
- `gpsAccuracyMeters`, `headingDegrees`, `speedMetersPerSecond`
- `distanceIntoTripMeters`
- `sensorSnapshot`
- `batterySnapshot`
- `mediaIds`
- `journalEntryId`
- `identificationId`
- `waypointId`
- `source`
- `automaticallyGenerated`
- `bookmarked`
- `metadata`
- `createdAt`, `updatedAt`

### Phase 2.2 — Add localStorage trip archive

**Files likely to change:**

- Modify: `src/main.jsx`
- Create or modify: `src/data/timelineStorage.js`

**Tasks:**

1. Persist active trip summary.
2. Persist timeline events.
3. Persist GPS samples from current browser walk/navigation trace.
4. Persist sensor/weather/battery snapshots when available.
5. Add schema version, e.g. `mappi3.timeline.v1`.
6. Add defensive migration/default handling for malformed localStorage.

**Verify:** Refresh browser while timeline remains available.

### Phase 2.3 — Manual event creation

**Files likely to change:**

- Modify: `src/main.jsx`
- Modify: `src/styles.css`

**Tasks:**

1. Add “Add event” button.
2. Support event at current time, selected timeline time, or selected map point.
3. Types: bookmark, note, wildlife, water source, campsite, hazard, injury, gear issue, trail obstruction, custom.
4. Prefill route, timestamp, coordinates, weather snapshot, battery snapshot when available.
5. Save locally.

**Verify:** Create manual event, refresh, event persists.

### Phase 2.4 — Journal/wildlife/AI integration into timeline

**Files likely to change:**

- Modify: `src/main.jsx`
- Possibly split existing `SurvivalHub`, `NatureAI`, or journal helper code later.

**Tasks:**

1. When journal draft saved, optionally create/update a journal timeline event.
2. When wildlife draft saved, optionally create/update wildlife event.
3. When Nature AI / image ID saves a result, generate nature ID event with caution labels.
4. Keep edits local and transparent.

**Verify:** Saving a journal/wildlife entry produces an event visible on the timeline.

### Phase 2.5 — Time-range data model

**Files likely to change:**

- Modify: `src/data/timelineModel.js`
- Modify: `src/main.jsx`
- Modify: `src/styles.css`

**Tasks:**

1. Add `TimelineRange` shape:
   - rest period
   - GPS outage
   - route deviation
   - emergency mode
   - device shutdown
2. Render ranges as shaded bands.
3. Attach start/end events where useful.

**Verify:** Sample GPS gap/rest/deviation ranges render as bands.

**Phase 2 acceptance criteria:**

- Timeline uses a normalized local data model.
- Events persist across refresh.
- Manual events work.
- Journal/wildlife/AI entries can become events.
- Ranges render separately from pins.
- Build/smoke pass.

**Review checkpoint:** CAK3D decides whether local browser persistence is enough for now or if Pi-backed persistence starts next.

---

## Phase 3 — Sensor, Weather, GPS Gap, Route Deviation, Battery, Elevation Layers

**Goal:** Make the timeline tell the actual field story: movement, environment, power, warnings, and route accuracy.

### Phase 3.1 — GPS gaps

**Tasks:**

1. Detect no valid GPS fix longer than configurable threshold.
2. Open GPS outage range.
3. Close range when GPS returns.
4. Label stale positions clearly.
5. Avoid drawing a fake straight route through long gaps.

### Phase 3.2 — Rest periods

**Tasks:**

1. Detect speed below threshold and location within radius for minimum duration.
2. Create rest range.
3. Avoid short-stop spam.
4. Display duration/location/weather during rest.

### Phase 3.3 — Route deviation detection

**Tasks:**

1. Calculate nearest route segment/point.
2. Track off-route distance.
3. Require consecutive samples.
4. Create deviation start, max deviation, return-to-route events/range.
5. Avoid one event per sample.

### Phase 3.4 — Weather/environment layers

**Tasks:**

1. Store temp/humidity/pressure samples.
2. Add pressure trend/rate.
3. Create rapid pressure drop warning using threshold such as 2 hPa / 3h.
4. Label estimates as local/sensor-based, not guaranteed forecasts.
5. Render weather bands/charts lightly.

### Phase 3.5 — Elevation layer

**Tasks:**

1. Add simplified elevation profile under the timeline.
2. Highlight selected elevation.
3. Track ascent/descent/highest/lowest.
4. Mark summits and milestones.
5. Filter noisy GPS altitude.

### Phase 3.6 — Battery layer

**Tasks:**

1. Store battery samples if available from browser/Pi/PiSugar status.
2. Create events for 50%, low, critical, charging start/stop, external power.
3. Render line or warning band.

**Phase 3 acceptance criteria:**

- GPS gaps/rest/deviations are represented honestly.
- Weather/elevation/battery appear as optional layers.
- Safety language distinguishes estimates from facts.
- No timeline event spam.
- Build/smoke pass.

---

## Phase 4 — Replay Mode and Search

**Goal:** Make completed trips replayable and searchable.

### Phase 4.1 — Replay controls

**Tasks:**

1. Add play/pause/rewind/stop.
2. Add speed selector: 0.5x, 1x, 2x, 5x, 10x, 20x, maybe 60x later.
3. Use `requestAnimationFrame` loop.
4. Advance selected time without mutating trip records.
5. Limit visual update rate for Pi/browser performance.

### Phase 4.2 — Event reveal during replay

**Tasks:**

1. Emphasize pin as replay passes it.
2. Show compact notification.
3. Do not auto-open full panels unless configured.
4. Critical events get stronger emphasis.

### Phase 4.3 — Skip inactive time

**Tasks:**

1. Optionally compress long rest/campsite periods.
2. Clearly label compressed time.
3. Preserve original timestamps.

### Phase 4.4 — Timeline search and jump

**Tasks:**

1. Search title, description, journal text, species name, location, waypoint, category, date, tag, warning type.
2. Show results list.
3. Jump timeline to selected event.
4. Focus map/detail panel.

**Phase 4 acceptance criteria:**

- Completed trip can replay smoothly.
- Replay does not alter data.
- Search can jump to important events.
- Build/smoke pass.

---

## Phase 5 — Pi-Backed Recorder and Timeline APIs

**Goal:** Promote the timeline from browser-local memory to real Pi field-kit trip recording.

**Requires explicit CAK3D approval before changes/deploy.**

### Phase 5.1 — Decide storage backend

Options:

1. SQLite on Pi local disk — recommended for field use.
2. JSONL files per trip — simplest/robust but less queryable.
3. Browser localStorage only — not enough for Pi reboot survival.
4. Optional Supabase later — not core/offline.

Recommended: SQLite with JSON export.

### Phase 5.2 — Add Pi local recorder schema

**Files likely to change:**

- Modify: `local-pi-imager/boot-partition-copy/mappi3-agent.py`
- Possibly create: `local-pi-imager/boot-partition-copy/mappi3-timeline-schema.sql`

Tables/indexes:

- `trips`
- `gps_samples`
- `sensor_samples`
- `timeline_events`
- `timeline_ranges`
- `media_items`

Indexes:

```sql
CREATE INDEX idx_gps_trip_timestamp ON gps_samples (trip_id, timestamp);
CREATE INDEX idx_sensor_trip_timestamp ON sensor_samples (trip_id, timestamp);
CREATE INDEX idx_event_trip_timestamp ON timeline_events (trip_id, timestamp);
CREATE INDEX idx_event_trip_category_timestamp ON timeline_events (trip_id, category, timestamp);
CREATE INDEX idx_range_trip_start ON timeline_ranges (trip_id, start_timestamp);
CREATE INDEX idx_media_trip_timestamp ON media_items (trip_id, captured_at);
```

### Phase 5.3 — Add timeline API endpoints

Endpoints from spec:

- `GET /api/trips`
- `POST /api/trips/start`
- `POST /api/trips/:tripId/pause`
- `POST /api/trips/:tripId/resume`
- `POST /api/trips/:tripId/end`
- `GET /api/trips/:tripId/timeline?start=&end=&zoom=&layers=`
- `GET /api/trips/:tripId/state-at?timestamp=`
- `GET /api/trips/:tripId/events/:eventId`
- `POST /api/trips/:tripId/events`
- `PATCH /api/trips/:tripId/events/:eventId`
- `DELETE /api/trips/:tripId/events/:eventId` or safer hide/dismiss
- `GET /api/trips/:tripId/timeline/search?query=`

### Phase 5.4 — Persist active trip through reboot

Persist:

- active trip ID
- trip state
- last committed GPS/sensor sample
- open ranges
- event generator states
- cumulative distance
- route deviation/rest state

After reboot:

1. Reopen unfinished trip.
2. Create device restart event.
3. Start GPS gap if location unavailable.
4. Avoid misleading route line across downtime.

### Phase 5.5 — Windowed timeline retrieval

**Tasks:**

1. Browser requests visible time window + buffer.
2. API returns visible events/ranges, simplified GPS path, aggregated sensor data, clusters, summary metadata.
3. Debounce API requests during drag.
4. Avoid loading entire trip into browser.

**Phase 5 acceptance criteria:**

- Pi can record a trip to local storage.
- Browser can query timeline windows.
- Active trip survives service/browser restart.
- Missing GPS/sensor data is explicit.
- Python compile/build/smoke/live endpoint checks pass.
- Rollback path exists for Pi deploy.

---

## Phase 6 — Performance, Clustering, Multi-Day Trips, Export, Privacy

**Goal:** Make the feature durable enough for full-day/overnight hikes.

### Phase 6.1 — Pin clustering and lanes

**Tasks:**

1. Cluster dense nearby events.
2. Show cluster counts.
3. Expand cluster on select.
4. Use vertical lanes to prevent overlaps.
5. Keep critical warnings visible.

### Phase 6.2 — Virtualization/render budgets

Initial targets:

- Max visible event pins: 100–200.
- Max visible clusters: 50–100.
- Max visible route points: 500–1,500.
- Max chart points per layer: 300–600.
- Timeline visual updates up to 30 fps.
- Heavy recalculation 5–10 fps.

### Phase 6.3 — Multi-day trip timeline

**Tasks:**

1. Show day boundaries.
2. Sunrise/sunset markers.
3. Campsite/sleep periods.
4. Day selector and daily summary.
5. Preserve continuous selected timestamp.

### Phase 6.4 — Export

Formats:

- JSON archive.
- GPX.
- GeoJSON.
- CSV summary.
- Markdown trip story.
- Printable report.

### Phase 6.5 — Privacy controls

**Tasks:**

1. Local-only storage by default.
2. Explicit export only.
3. Clear warning before sharing location history.
4. Remove exact start/end from exports.
5. Reduce coordinate precision in shared reports.
6. Optional PIN later.

**Phase 6 acceptance criteria:**

- Dense trips remain usable.
- Long trips do not blow browser memory.
- Multi-day trips are understandable.
- Export and privacy controls work offline.

---

## Phase 7 — Emergency Upgrade and Survival Trainer

**Goal:** Finish the remaining `mappi3new.txt` ideas that are adjacent to timeline but safety/education focused.

### Phase 7.1 — Emergency mode upgrade

Add:

- Current lat/lon.
- Multiple coordinate formats: decimal, DMS, UTM if lightweight, Plus Code if feasible offline.
- Altitude.
- GPS accuracy.
- Last reliable fix time.
- Direction/distance to nearest known road/exit/ranger station/town when locally stored.
- Timeline emergency event/range.
- High-visibility UI.
- Prevent accidental dismissal.
- Sense HAT SOS pattern.

### Phase 7.2 — Survival trainer/quizzes

Add optional offline quizzes:

- tree/mushroom/track identification practice.
- knot steps.
- weather/nav/survival scenarios.
- first-aid decision prompts with caution labels.

**Phase 7 acceptance criteria:**

- Emergency UI is clearer and harder to misuse.
- Survival trainer is educational, not safety-authoritative.
- All safety disclaimers remain honest.

---

## Global Verification Commands

Run before claiming app work done:

```bash
cd /home/ubuntu/MapPi3
npm run build
npm run smoke
npm run audit:pages || true
git diff --check
```

For Pi agent changes:

```bash
cd /home/ubuntu/MapPi3
python3 -m py_compile local-pi-imager/boot-partition-copy/mappi3-agent.py
```

For live Pi deployment, only after CAK3D approval:

1. Create rollback backup on Pi.
2. Upload verified bundle.
3. Apply and restart service.
4. Check `mappi3-web.service` active.
5. Verify `/`, `/api/status`, `/api/sense`, and new timeline endpoints.
6. Verify via hotspot and/or Tailscale from outside the Pi.

---

## Recommended Review Flow With CAK3D

1. Review Phase 1 scope and visual behavior.
2. Implement Phase 1 only.
3. Verify locally with build/smoke and browser check.
4. Review screenshot/live preview.
5. Repeat for each phase.
6. Do not combine backend/Pi deploy phases with frontend-only phases unless explicitly approved.

---

## First Phase to Discuss Next

Phase 1 is the best starting point:

- It produces the scroll/click-drag timeline CAK3D specifically liked.
- It reuses existing data instead of inventing a backend first.
- It gives quick visual feedback.
- It avoids Pi service risk.

Suggested Phase 1 approval wording:

```text
Approve Phase 1: add frontend Adventure Timeline MVP only, no Pi backend/service deploy yet.
```
