export const TIMELINE_MODEL_VERSION = 1;

export const TIMELINE_EVENT_CATEGORIES = [
  'route', 'photo', 'journal', 'wildlife', 'nature', 'water', 'campsite', 'weather',
  'warning', 'emergency', 'battery', 'gps', 'device', 'manual'
];

export const TIMELINE_RANGE_TYPES = [
  'rest', 'gps-outage', 'route-deviation', 'emergency-mode', 'device-shutdown'
];

export const TIMELINE_EVENT_TYPES = [
  'bookmark', 'note', 'wildlife', 'water-source', 'campsite', 'hazard', 'injury',
  'gear-issue', 'trail-obstruction', 'journal-entry', 'nature-id', 'custom'
];

export const finiteNumber = (value) => Number.isFinite(Number(value));
export const asNumber = (value, fallback = undefined) => finiteNumber(value) ? Number(value) : fallback;
export const nowIso = () => new Date().toISOString();

export function makeTimelineTrip(route = {}, patch = {}) {
  const now = Date.now();
  const startedAt = patch.startedAt || now;
  const routeName = route.name || patch.routeName || 'selected route';
  return {
    schemaVersion: TIMELINE_MODEL_VERSION,
    id: patch.id || `trip-${route.id || 'local'}-${startedAt}`,
    name: patch.name || `${routeName} adventure`,
    routeId: patch.routeId || route.id || 'local-route',
    routeName,
    startedAt,
    endedAt: patch.endedAt || null,
    distanceMiles: asNumber(patch.distanceMiles ?? route.distanceMiles ?? route.miles, 0),
    source: patch.source || 'local browser trip archive',
    createdAt: patch.createdAt || nowIso(),
    updatedAt: patch.updatedAt || nowIso(),
    metadata: patch.metadata || {}
  };
}

export function normalizeTimelineEvent(event = {}, defaults = {}) {
  const createdAt = event.createdAt || nowIso();
  const updatedAt = event.updatedAt || createdAt;
  const category = TIMELINE_EVENT_CATEGORIES.includes(event.category) ? event.category : (defaults.category || 'manual');
  const timestamp = asNumber(event.timestamp ?? defaults.timestamp, Date.now());
  const latitude = asNumber(event.latitude ?? event.lat ?? defaults.latitude ?? defaults.lat);
  const longitude = asNumber(event.longitude ?? event.lon ?? defaults.longitude ?? defaults.lon);
  const distanceIntoTripMeters = asNumber(event.distanceIntoTripMeters ?? defaults.distanceIntoTripMeters);
  const idSeed = `${category}-${timestamp}-${Math.random().toString(16).slice(2, 8)}`;
  return {
    schemaVersion: TIMELINE_MODEL_VERSION,
    id: event.id || `event-${idSeed}`,
    tripId: event.tripId || defaults.tripId || 'active-trip',
    timestamp,
    eventType: event.eventType || defaults.eventType || category,
    category,
    severity: event.severity || defaults.severity || (['warning', 'emergency'].includes(category) ? 'caution' : 'info'),
    title: event.title || defaults.title || 'Timeline event',
    description: event.description || defaults.description || '',
    latitude,
    longitude,
    lat: latitude,
    lon: longitude,
    altitudeMeters: asNumber(event.altitudeMeters ?? defaults.altitudeMeters),
    gpsAccuracyMeters: asNumber(event.gpsAccuracyMeters ?? defaults.gpsAccuracyMeters),
    headingDegrees: asNumber(event.headingDegrees ?? defaults.headingDegrees),
    speedMetersPerSecond: asNumber(event.speedMetersPerSecond ?? defaults.speedMetersPerSecond),
    distanceIntoTripMeters,
    sensorSnapshot: event.sensorSnapshot || defaults.sensorSnapshot || null,
    batterySnapshot: event.batterySnapshot || defaults.batterySnapshot || null,
    mediaIds: Array.isArray(event.mediaIds) ? event.mediaIds : [],
    journalEntryId: event.journalEntryId || defaults.journalEntryId || null,
    identificationId: event.identificationId || defaults.identificationId || null,
    waypointId: event.waypointId || defaults.waypointId || null,
    source: event.source || defaults.source || 'local',
    sourceLabel: event.sourceLabel || defaults.sourceLabel || event.source || defaults.source || 'local',
    automaticallyGenerated: Boolean(event.automaticallyGenerated ?? defaults.automaticallyGenerated ?? false),
    bookmarked: Boolean(event.bookmarked ?? defaults.bookmarked ?? false),
    metadata: event.metadata || defaults.metadata || {},
    createdAt,
    updatedAt
  };
}

export function normalizeTimelineRange(range = {}, defaults = {}) {
  const timestamp = asNumber(range.startTimestamp ?? range.timestamp ?? defaults.startTimestamp, Date.now());
  const endTimestamp = asNumber(range.endTimestamp ?? defaults.endTimestamp, timestamp + 15 * 60 * 1000);
  const type = TIMELINE_RANGE_TYPES.includes(range.rangeType || range.type) ? (range.rangeType || range.type) : (defaults.rangeType || 'rest');
  return {
    schemaVersion: TIMELINE_MODEL_VERSION,
    id: range.id || `range-${type}-${timestamp}`,
    tripId: range.tripId || defaults.tripId || 'active-trip',
    rangeType: type,
    category: range.category || defaults.category || 'device',
    severity: range.severity || defaults.severity || 'info',
    title: range.title || defaults.title || type.replace(/-/g, ' '),
    description: range.description || defaults.description || '',
    startTimestamp: Math.min(timestamp, endTimestamp),
    endTimestamp: Math.max(timestamp, endTimestamp),
    source: range.source || defaults.source || 'local range model',
    automaticallyGenerated: Boolean(range.automaticallyGenerated ?? defaults.automaticallyGenerated ?? true),
    metadata: range.metadata || defaults.metadata || {},
    createdAt: range.createdAt || nowIso(),
    updatedAt: range.updatedAt || nowIso()
  };
}

export function mergeTimelineEvents(...eventLists) {
  const byId = new Map();
  eventLists.flat().filter(Boolean).forEach(event => {
    const normalized = normalizeTimelineEvent(event);
    byId.set(normalized.id, { ...byId.get(normalized.id), ...normalized });
  });
  return [...byId.values()].sort((a, b) => Number(a.timestamp || 0) - Number(b.timestamp || 0));
}

export function buildSampleTimelineRanges(trip = {}, events = []) {
  const start = Number(events[0]?.timestamp || trip.startedAt || Date.now());
  const rawEnd = Number(events.at?.(-1)?.timestamp || trip.endedAt || 0);
  const end = rawEnd > start ? rawEnd : start + 90 * 60 * 1000;
  const span = end - start;
  return [
    normalizeTimelineRange({ tripId: trip.id, rangeType: 'rest', category: 'route', title: 'Planned rest window', description: 'Sample shaded band for Phase 2 range rendering.', startTimestamp: start + span * 0.32, endTimestamp: start + span * 0.42, metadata: { sample: true } }),
    normalizeTimelineRange({ tripId: trip.id, rangeType: 'gps-outage', category: 'gps', severity: 'caution', title: 'GPS weak-signal sample', description: 'Sample GPS gap band. Real recorder gaps come later.', startTimestamp: start + span * 0.58, endTimestamp: start + span * 0.66, metadata: { sample: true } })
  ];
}
