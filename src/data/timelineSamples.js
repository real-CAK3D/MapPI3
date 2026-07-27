const categoryDefaults = {
  route: { icon: '🥾', color: '#9ce36c', layer: 'route' },
  journal: { icon: '📝', color: '#ffd36a', layer: 'journal' },
  wildlife: { icon: '🦌', color: '#f1b56b', layer: 'wildlife' },
  nature: { icon: '🍄', color: '#b9ff9c', layer: 'nature' },
  water: { icon: '💧', color: '#4bd2ff', layer: 'water' },
  campsite: { icon: '⛺', color: '#ffb86b', layer: 'campsites' },
  weather: { icon: '⛅', color: '#90c7ff', layer: 'weather' },
  warning: { icon: '⚠️', color: '#ffdd66', layer: 'warnings' },
  emergency: { icon: '🆘', color: '#ff7777', layer: 'emergency' },
  battery: { icon: '🔋', color: '#7cffb2', layer: 'battery' },
  gps: { icon: '📡', color: '#c5d3ff', layer: 'gps' },
  device: { icon: '🥧', color: '#e6a3ff', layer: 'gps' },
  photo: { icon: '📷', color: '#f6f7eb', layer: 'journal' }
};

const finite = (value) => Number.isFinite(Number(value));
const asNumber = (value, fallback = 0) => finite(value) ? Number(value) : fallback;
const routeMiles = (route = {}) => asNumber(route.distanceMiles ?? route.miles, 0);
const routePointList = (route = {}) => {
  const coords = route.geometry?.coordinates || [];
  return coords.map(([lon, lat]) => ({ lat: Number(lat), lon: Number(lon) })).filter(p => finite(p.lat) && finite(p.lon));
};
const pointAtRatio = (route = {}, ratio = 0) => {
  const points = routePointList(route);
  if (!points.length) return null;
  const index = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
  return points[index];
};
const readLocalJson = (key, fallback = null) => {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
};
const textPreview = (value, max = 150) => String(value || '').trim().replace(/\s+/g, ' ').slice(0, max);
const eventAt = (base, minutes) => base + minutes * 60 * 1000;
const normalizeWaypointType = (point = {}) => String(point.type || point.role || point.name || '').toLowerCase();
const categoryForWaypoint = (point = {}) => {
  const t = normalizeWaypointType(point);
  if (/water|spring|brook|stream|pond|river/.test(t)) return 'water';
  if (/camp|shelter|tent|lean-to|site/.test(t)) return 'campsite';
  if (/summit|view|vista|lookout|peak/.test(t)) return 'route';
  if (/hazard|caution|steep|crossing|road|bail/.test(t)) return 'warning';
  return 'route';
};
const severityForCategory = (category) => ['warning','emergency'].includes(category) ? 'caution' : 'info';

export const TIMELINE_LAYERS = [
  { id: 'route', label: 'Route', icon: '🥾' },
  { id: 'weather', label: 'Weather', icon: '⛅' },
  { id: 'journal', label: 'Journal/media', icon: '📝' },
  { id: 'wildlife', label: 'Wildlife', icon: '🦌' },
  { id: 'nature', label: 'Nature', icon: '🍄' },
  { id: 'water', label: 'Water', icon: '💧' },
  { id: 'campsites', label: 'Camp/shelter', icon: '⛺' },
  { id: 'warnings', label: 'Warnings', icon: '⚠️' },
  { id: 'emergency', label: 'Emergency', icon: '🆘' },
  { id: 'battery', label: 'Battery', icon: '🔋' },
  { id: 'gps', label: 'GPS/device', icon: '📡' }
];

export const defaultTimelineLayerState = () => Object.fromEntries(TIMELINE_LAYERS.map(layer => [layer.id, true]));
export const timelineCategoryMeta = (category) => categoryDefaults[category] || categoryDefaults.route;

export function buildAdventureTimeline({ selectedRoute = {}, customWaypoints = [], completedTrails = [], savedWalks = [], conditions = {}, progress = 0, elapsed = 0, launchPlan = {} } = {}) {
  const now = Date.now();
  const start = now - Math.max(45, Math.min(480, Math.round(Math.max(elapsed, 1) / 60) || 105)) * 60 * 1000;
  const totalMiles = routeMiles(selectedRoute);
  const waypoints = [...(selectedRoute.waypoints || []), ...(selectedRoute.pois || []), ...(customWaypoints || [])]
    .filter(point => finite(point.lat) && finite(point.lon));
  const trailhead = waypoints[0] || pointAtRatio(selectedRoute, 0) || selectedRoute.center || null;
  const finish = waypoints[waypoints.length - 1] || pointAtRatio(selectedRoute, 1) || trailhead;
  const event = (patch, index = 0) => {
    const category = patch.category || 'route';
    const meta = timelineCategoryMeta(category);
    const timestamp = patch.timestamp || eventAt(start, index * 18);
    const lat = asNumber(patch.lat ?? patch.latitude, NaN);
    const lon = asNumber(patch.lon ?? patch.longitude, NaN);
    return {
      id: patch.id || `demo-${category}-${index}-${timestamp}`,
      tripId: patch.tripId || `phase1-${selectedRoute.id || 'local-route'}`,
      timestamp,
      category,
      layer: patch.layer || meta.layer,
      eventType: patch.eventType || category,
      title: patch.title || 'Trail event',
      description: patch.description || '',
      lat: Number.isFinite(lat) ? lat : undefined,
      lon: Number.isFinite(lon) ? lon : undefined,
      altitudeMeters: patch.altitudeMeters,
      distanceIntoTripMeters: patch.distanceIntoTripMeters,
      severity: patch.severity || severityForCategory(category),
      source: patch.source || 'phase-1 local sample builder',
      sourceLabel: patch.sourceLabel || 'generated from current local MapPI3 state',
      automaticallyGenerated: patch.automaticallyGenerated ?? true,
      bookmarked: Boolean(patch.bookmarked),
      icon: patch.icon || meta.icon,
      color: patch.color || meta.color,
      metadata: patch.metadata || {}
    };
  };

  const events = [];
  if (trailhead) events.push(event({ category:'route', eventType:'trip-start', title:`Start · ${selectedRoute.name || 'selected route'}`, description:`Timeline seeded from ${selectedRoute.name || 'your selected route'} for Phase 1. Recorder/API comes later.`, lat:trailhead.lat, lon:trailhead.lon, distanceIntoTripMeters:0, sourceLabel:'route pack' }, 0));

  waypoints.slice(0, 12).forEach((point, idx) => {
    const category = categoryForWaypoint(point);
    const mile = asNumber(point.mile, totalMiles ? totalMiles * ((idx + 1) / Math.max(2, waypoints.length + 1)) : idx * 0.4);
    events.push(event({
      category,
      eventType: point.type || point.role || 'waypoint',
      title: point.name || `Waypoint ${idx + 1}`,
      description: point.notes || `${point.type || 'Waypoint'} at mile ${mile.toFixed(1)} on the selected route.`,
      lat: point.lat,
      lon: point.lon,
      distanceIntoTripMeters: mile * 1609.344,
      sourceLabel: point.custom || point.editable ? 'local custom marker' : 'route waypoint',
      metadata: { mile: Number(mile.toFixed(2)), type: point.type || point.role || 'waypoint' }
    }, idx + 1));
  });

  const journalDraft = textPreview(readLocalJson('mappi3.trailJournalDraft', ''));
  if (journalDraft) {
    const p = pointAtRatio(selectedRoute, 0.42) || trailhead;
    events.push(event({ category:'journal', eventType:'journal-draft', title:'Trail journal draft', description:journalDraft, lat:p?.lat, lon:p?.lon, sourceLabel:'local draft', automaticallyGenerated:false, bookmarked:true }, 4));
  }
  const wildlifeDraft = textPreview(readLocalJson('mappi3.wildlifeDraft', ''));
  if (wildlifeDraft) {
    const p = pointAtRatio(selectedRoute, 0.58) || trailhead;
    events.push(event({ category:'wildlife', eventType:'wildlife-note', title:'Wildlife note draft', description:wildlifeDraft, lat:p?.lat, lon:p?.lon, sourceLabel:'local draft', automaticallyGenerated:false }, 6));
  }

  const temp = finite(conditions.tempF) ? `${Math.round(Number(conditions.tempF))}°F` : 'field weather pending';
  const weatherPoint = pointAtRatio(selectedRoute, 0.25) || trailhead;
  events.push(event({ category:'weather', eventType:'weather-snapshot', title:'Weather snapshot', description:`${temp} · humidity ${conditions.humidity ?? '—'}% · ${conditions.source || 'offline/weather cache pending'}`, lat:weatherPoint?.lat, lon:weatherPoint?.lon, sourceLabel: conditions.source || 'local weather cache', metadata:{ tempF:conditions.tempF, humidity:conditions.humidity, airQuality:conditions.airQuality } }, 3));

  const currentPoint = pointAtRatio(selectedRoute, Math.max(0, Math.min(1, Number(progress || 0.34)))) || trailhead;
  events.push(event({ category:'gps', eventType:'playhead-estimate', title:'Current playhead estimate', description:`Current UI progress ${(Math.max(0, Math.min(1, Number(progress || 0))) * 100).toFixed(0)}%. Live recorder is Phase 5; this is a safe frontend estimate.`, lat:currentPoint?.lat, lon:currentPoint?.lon, distanceIntoTripMeters: totalMiles * 1609.344 * Math.max(0, Math.min(1, Number(progress || 0))), sourceLabel:'browser state' }, 7));

  const batteryPoint = pointAtRatio(selectedRoute, 0.7) || trailhead;
  events.push(event({ category:'battery', eventType:'battery-check', title:'Field kit battery checkpoint', description:'PiSugar / browser battery lane placeholder. Phase 5 will attach real Pi recorder samples.', lat:batteryPoint?.lat, lon:batteryPoint?.lon, sourceLabel:'Phase 1 placeholder', metadata:{ phase:'frontend-only' } }, 8));

  savedWalks.slice(0, 2).forEach((walk, idx) => {
    const trace = walk.trace || [];
    const point = trace.find(p => finite(p.lat) && finite(p.lon)) || trailhead;
    events.push(event({ category:'journal', eventType:'saved-walk', title:walk.name || `Saved walk ${idx + 1}`, description:`${asNumber(walk.distanceMiles ?? walk.miles, 0).toFixed(2)} mi saved walk · ${Math.round(asNumber(walk.durationSeconds, 0) / 60)} min`, lat:point?.lat, lon:point?.lon, sourceLabel:'saved Daily Exercise walk', bookmarked:idx === 0 }, 9 + idx));
  });

  completedTrails.slice(0, 2).forEach((trail, idx) => {
    const p = pointAtRatio(selectedRoute, idx ? 0.85 : 0.75) || finish;
    events.push(event({ category:'route', eventType:'completed-trail', title:`Completed · ${trail.routeName || trail.name || selectedRoute.name || 'trail'}`, description:`Prior completion memory: ${asNumber(trail.miles ?? trail.distanceMiles, totalMiles).toFixed(1)} mi.`, lat:p?.lat, lon:p?.lon, sourceLabel:'completed trails log', bookmarked:true }, 11 + idx));
  });

  if (finish) events.push(event({ category:'route', eventType:'trip-finish', title:'Finish / turnaround', description:`End marker for ${selectedRoute.name || 'selected route'} · ${totalMiles ? `${totalMiles.toFixed(1)} mi` : 'distance pending'}.`, lat:finish.lat, lon:finish.lon, distanceIntoTripMeters: totalMiles * 1609.344, sourceLabel:'route pack' }, 15));

  const unique = new Map(events.filter(Boolean).map(item => [item.id, item]));
  const sorted = [...unique.values()].sort((a, b) => a.timestamp - b.timestamp);
  return {
    trip: {
      id: `phase1-${selectedRoute.id || 'local-route'}`,
      name: selectedRoute.name || 'Phase 1 demo trip',
      routeName: selectedRoute.name || 'selected route',
      distanceMiles: totalMiles,
      source: 'frontend-only Phase 1 timeline builder',
      startedAt: sorted[0]?.timestamp || start,
      endedAt: sorted.at(-1)?.timestamp || eventAt(start, 160),
      launchPlan
    },
    events: sorted
  };
}
