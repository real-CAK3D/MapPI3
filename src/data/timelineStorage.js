import { TIMELINE_MODEL_VERSION, buildSampleTimelineRanges, makeTimelineTrip, mergeTimelineEvents, normalizeTimelineEvent, normalizeTimelineRange } from './timelineModel.js';

export const TIMELINE_STORAGE_KEY = 'mappi3.timeline.v1';

export function createEmptyTimelineArchive(route = {}) {
  const trip = makeTimelineTrip(route);
  return {
    schemaVersion: TIMELINE_MODEL_VERSION,
    activeTripId: trip.id,
    trips: [trip],
    events: [],
    ranges: [],
    gpsSamples: [],
    snapshots: [],
    updatedAt: new Date().toISOString()
  };
}

export function migrateTimelineArchive(raw, route = {}) {
  const empty = createEmptyTimelineArchive(route);
  if (!raw || typeof raw !== 'object') return empty;
  const trips = Array.isArray(raw.trips) && raw.trips.length ? raw.trips.map((trip, index) => makeTimelineTrip(route, { ...trip, id: trip.id || `trip-migrated-${index}` })) : empty.trips;
  const activeTripId = raw.activeTripId || trips[0]?.id || empty.activeTripId;
  const events = Array.isArray(raw.events) ? mergeTimelineEvents(raw.events.map(event => normalizeTimelineEvent(event, { tripId: activeTripId }))) : [];
  const ranges = Array.isArray(raw.ranges) ? raw.ranges.map(range => normalizeTimelineRange(range, { tripId: activeTripId })) : [];
  const gpsSamples = Array.isArray(raw.gpsSamples) ? raw.gpsSamples.filter(sample => Number.isFinite(Number(sample?.lat ?? sample?.latitude)) && Number.isFinite(Number(sample?.lon ?? sample?.longitude))).slice(-500) : [];
  const snapshots = Array.isArray(raw.snapshots) ? raw.snapshots.slice(-200) : [];
  return {
    schemaVersion: TIMELINE_MODEL_VERSION,
    activeTripId,
    trips,
    events,
    ranges,
    gpsSamples,
    snapshots,
    updatedAt: raw.updatedAt || new Date().toISOString()
  };
}

export function loadTimelineArchive(route = {}) {
  if (typeof window === 'undefined') return createEmptyTimelineArchive(route);
  try {
    const raw = window.localStorage.getItem(TIMELINE_STORAGE_KEY);
    return migrateTimelineArchive(raw ? JSON.parse(raw) : null, route);
  } catch {
    return createEmptyTimelineArchive(route);
  }
}

export function saveTimelineArchive(archive) {
  if (typeof window === 'undefined') return archive;
  const safe = migrateTimelineArchive({ ...archive, updatedAt: new Date().toISOString() });
  window.localStorage.setItem(TIMELINE_STORAGE_KEY, JSON.stringify(safe));
  return safe;
}

export function upsertTimelineEvent(archive, event) {
  const activeTripId = archive?.activeTripId || archive?.trips?.[0]?.id || 'active-trip';
  const normalized = normalizeTimelineEvent(event, { tripId: activeTripId });
  const without = (archive.events || []).filter(item => item.id !== normalized.id);
  return saveTimelineArchive({ ...archive, events: mergeTimelineEvents(without, [normalized]) });
}

export function addTimelineRange(archive, range) {
  const activeTripId = archive?.activeTripId || archive?.trips?.[0]?.id || 'active-trip';
  const normalized = normalizeTimelineRange(range, { tripId: activeTripId });
  const without = (archive.ranges || []).filter(item => item.id !== normalized.id);
  return saveTimelineArchive({ ...archive, ranges: [...without, normalized].sort((a, b) => a.startTimestamp - b.startTimestamp) });
}

export function addTimelineGpsSample(archive, sample = {}) {
  const normalized = {
    id: sample.id || `gps-${sample.timestamp || Date.now()}`,
    tripId: sample.tripId || archive.activeTripId,
    timestamp: Number(sample.timestamp || Date.now()),
    latitude: Number(sample.latitude ?? sample.lat),
    longitude: Number(sample.longitude ?? sample.lon),
    accuracyMeters: Number(sample.accuracyMeters ?? sample.accuracy ?? 0) || undefined,
    source: sample.source || 'browser navigation trace'
  };
  if (!Number.isFinite(normalized.latitude) || !Number.isFinite(normalized.longitude)) return archive;
  return saveTimelineArchive({ ...archive, gpsSamples: [...(archive.gpsSamples || []), normalized].slice(-500) });
}

export function seedTimelineRangesIfEmpty(archive, trip, events) {
  if ((archive.ranges || []).length) return archive;
  const ranges = buildSampleTimelineRanges(trip, events);
  if (!ranges.length) return archive;
  return saveTimelineArchive({ ...archive, ranges });
}
