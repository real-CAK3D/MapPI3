const DAY_MS = 86400000;
const DEFAULT_RENDER_BUDGET = {
  maxPins: 160,
  maxClusters: 80,
  maxRoutePoints: 1200,
  maxChartPoints: 420,
  laneCount: 4,
  bucketPercent: 1.8,
};

const finite = value => Number.isFinite(Number(value));
const asNumber = (value, fallback = undefined) => finite(value) ? Number(value) : fallback;
const pad = value => String(value).padStart(2, '0');
const slug = value => String(value || 'mappi3-trip').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'mappi3-trip';
const xmlEscape = value => String(value ?? '').replace(/[<>&"']/g, char => ({ '<':'&lt;', '>':'&gt;', '&':'&amp;', '"':'&quot;', "'":'&apos;' }[char]));
const csvEscape = value => `"${String(value ?? '').replace(/"/g, '""')}"`;

export function timestampDayKey(timestamp) {
  const date = new Date(asNumber(timestamp, Date.now()));
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatExportTimestamp(timestamp) {
  return new Date(asNumber(timestamp, Date.now())).toISOString();
}

export function buildTimelineRenderPlan(events = [], ranges = [], options = {}) {
  const budget = { ...DEFAULT_RENDER_BUDGET, ...(options.budget || {}) };
  const cleanEvents = [...events]
    .filter(event => finite(event?.timestamp))
    .sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
  const start = asNumber(options.start, cleanEvents[0]?.timestamp || Date.now());
  const end = Math.max(start + 1, asNumber(options.end, cleanEvents.at(-1)?.timestamp || start + 1));
  const duration = Math.max(1, end - start);
  const criticalEvents = new Set(cleanEvents.filter(event => ['warning', 'emergency'].includes(event.category) || event.severity === 'critical').map(event => event.id));
  const buckets = new Map();
  cleanEvents.forEach((event, order) => {
    const position = Math.max(0, Math.min(100, ((Number(event.timestamp) - start) / duration) * 100));
    const forced = criticalEvents.has(event.id) || event.id === options.selectedId || event.bookmarked;
    const bucket = forced ? `force-${event.id}` : `${Math.floor(position / budget.bucketPercent)}`;
    const list = buckets.get(bucket) || [];
    list.push({ ...event, position, order, forced });
    buckets.set(bucket, list);
  });
  const markers = [...buckets.values()].map((items, index) => {
    const representative = items.reduce((best, item) => {
      if (item.id === options.selectedId) return item;
      if (best.id === options.selectedId) return best;
      if (item.bookmarked && !best.bookmarked) return item;
      return item.timestamp < best.timestamp ? item : best;
    }, items[0]);
    const lane = index % Math.max(1, budget.laneCount);
    if (items.length === 1 || representative.forced) {
      return { kind: 'event', id: representative.id, event: representative, count: 1, position: representative.position, lane, startTimestamp: representative.timestamp, endTimestamp: representative.timestamp };
    }
    return {
      kind: 'cluster',
      id: `cluster-${Math.round(representative.position * 10)}-${items[0].timestamp}`,
      event: representative,
      events: items,
      count: items.length,
      categories: [...new Set(items.map(item => item.category).filter(Boolean))].slice(0, 4),
      title: `${items.length} events near ${new Date(representative.timestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`,
      position: representative.position,
      lane,
      startTimestamp: items[0].timestamp,
      endTimestamp: items.at(-1).timestamp,
    };
  });
  const forced = markers.filter(marker => marker.kind === 'event' && criticalEvents.has(marker.id));
  const normal = markers.filter(marker => !(marker.kind === 'event' && criticalEvents.has(marker.id)));
  const capped = [...forced, ...normal.slice(0, Math.max(0, budget.maxPins + budget.maxClusters - forced.length))]
    .sort((a, b) => Number(a.startTimestamp) - Number(b.startTimestamp));
  const rangeMarkers = ranges
    .filter(range => finite(range?.startTimestamp) && finite(range?.endTimestamp))
    .map(range => {
      const left = Math.max(0, Math.min(100, ((Number(range.startTimestamp) - start) / duration) * 100));
      const right = Math.max(left + 0.8, Math.min(100, ((Number(range.endTimestamp) - start) / duration) * 100));
      return { ...range, position: left, width: right - left };
    })
    .slice(0, budget.maxPins);
  return {
    markers: capped,
    ranges: rangeMarkers,
    hiddenCount: Math.max(0, cleanEvents.length - capped.reduce((sum, marker) => sum + (marker.count || 1), 0)),
    totalEvents: cleanEvents.length,
    clusterCount: capped.filter(marker => marker.kind === 'cluster').length,
    budget,
    start,
    end,
  };
}

export function buildTimelineDaySummaries(events = [], ranges = []) {
  const byDay = new Map();
  events.filter(event => finite(event?.timestamp)).forEach(event => {
    const key = timestampDayKey(event.timestamp);
    const day = byDay.get(key) || { key, startTimestamp: new Date(`${key}T00:00:00`).getTime(), eventCount: 0, warningCount: 0, bookmarkedCount: 0, categories: new Set(), ranges: 0 };
    day.eventCount += 1;
    if (['warning', 'emergency'].includes(event.category) || event.severity === 'critical') day.warningCount += 1;
    if (event.bookmarked) day.bookmarkedCount += 1;
    if (event.category) day.categories.add(event.category);
    byDay.set(key, day);
  });
  ranges.filter(range => finite(range?.startTimestamp)).forEach(range => {
    const key = timestampDayKey(range.startTimestamp);
    const day = byDay.get(key) || { key, startTimestamp: new Date(`${key}T00:00:00`).getTime(), eventCount: 0, warningCount: 0, bookmarkedCount: 0, categories: new Set(), ranges: 0 };
    day.ranges += 1;
    byDay.set(key, day);
  });
  return [...byDay.values()].sort((a, b) => a.startTimestamp - b.startTimestamp).map(day => ({ ...day, categories: [...day.categories].slice(0, 6), label: new Date(day.startTimestamp).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }) }));
}

export function privacyCoordinate(value, mode = 'shared') {
  if (!finite(value)) return undefined;
  const places = mode === 'private' ? 6 : 3;
  return Number(Number(value).toFixed(places));
}

export function sanitizeTimelineForExport({ trip = {}, events = [], ranges = [], gpsSamples = [], snapshots = [] } = {}, options = {}) {
  const privacy = options.privacy || 'shared';
  const sortedEvents = [...events].filter(event => finite(event?.timestamp)).sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
  const sortedGps = [...gpsSamples].filter(sample => finite(sample?.timestamp)).sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
  const scrubEnds = privacy !== 'private';
  const scrubSet = new Set(scrubEnds ? [sortedEvents[0]?.id, sortedEvents.at(-1)?.id].filter(Boolean) : []);
  const mapPoint = point => ({
    ...point,
    latitude: privacyCoordinate(point.latitude ?? point.lat, privacy),
    longitude: privacyCoordinate(point.longitude ?? point.lon, privacy),
    lat: undefined,
    lon: undefined,
  });
  return {
    schemaVersion: 'mappi3-adventure-timeline-export-v1',
    exportedAt: formatExportTimestamp(Date.now()),
    privacyMode: privacy,
    privacyNote: privacy === 'private' ? 'Private export keeps higher coordinate precision. Share carefully.' : 'Shared export reduces coordinate precision and removes exact first/last event coordinates.',
    trip: { ...trip, metadata: trip.metadata || {} },
    events: sortedEvents.map(event => {
      const scrub = scrubSet.has(event.id);
      const { lat: _lat, lon: _lon, latitude: _latitude, longitude: _longitude, ...rest } = event;
      return mapPoint({ ...rest, latitude: scrub ? undefined : _latitude ?? _lat, longitude: scrub ? undefined : _longitude ?? _lon, metadata: { ...(event.metadata || {}), exactEndpointLocationRemoved: scrub || undefined } });
    }),
    ranges: [...ranges].sort((a, b) => Number(a.startTimestamp || 0) - Number(b.startTimestamp || 0)),
    gpsSamples: sortedGps.map((sample, index) => {
      const scrub = scrubEnds && (index === 0 || index === sortedGps.length - 1);
      const { lat: _lat, lon: _lon, latitude: _latitude, longitude: _longitude, ...rest } = sample;
      return mapPoint({ ...rest, latitude: scrub ? undefined : _latitude ?? _lat, longitude: scrub ? undefined : _longitude ?? _lon, exactEndpointLocationRemoved: scrub || undefined });
    }),
    snapshots: [...snapshots].slice(-500),
  };
}

export function makeTimelineJsonExport(payload, options = {}) {
  return JSON.stringify(sanitizeTimelineForExport(payload, options), null, 2);
}

export function makeTimelineGeoJsonExport(payload, options = {}) {
  const safe = sanitizeTimelineForExport(payload, options);
  const features = safe.events.filter(event => finite(event.latitude) && finite(event.longitude)).map(event => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [event.longitude, event.latitude] },
    properties: { id: event.id, timestamp: event.timestamp, time: formatExportTimestamp(event.timestamp), category: event.category, eventType: event.eventType, title: event.title, description: event.description, source: event.sourceLabel || event.source, severity: event.severity }
  }));
  return JSON.stringify({ type: 'FeatureCollection', name: safe.trip?.name || 'MapPI3 Adventure Timeline', properties: { schemaVersion: safe.schemaVersion, privacyMode: safe.privacyMode, privacyNote: safe.privacyNote }, features }, null, 2);
}

export function makeTimelineGpxExport(payload, options = {}) {
  const safe = sanitizeTimelineForExport(payload, options);
  const points = safe.gpsSamples.filter(sample => finite(sample.latitude) && finite(sample.longitude)).map(sample => `      <trkpt lat="${sample.latitude}" lon="${sample.longitude}"><time>${formatExportTimestamp(sample.timestamp)}</time></trkpt>`).join('\n');
  const waypoints = safe.events.filter(event => finite(event.latitude) && finite(event.longitude)).map(event => `  <wpt lat="${event.latitude}" lon="${event.longitude}"><name>${xmlEscape(event.title)}</name><type>${xmlEscape(event.category)}</type><desc>${xmlEscape(`${event.description || ''} (${event.sourceLabel || event.source || 'local'})`)}</desc><time>${formatExportTimestamp(event.timestamp)}</time></wpt>`).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="MapPI3 Adventure Timeline" xmlns="http://www.topografix.com/GPX/1/1">\n  <metadata><name>${xmlEscape(safe.trip?.name || 'MapPI3 Adventure Timeline')}</name><desc>${xmlEscape(safe.privacyNote)}</desc></metadata>\n${waypoints}\n  <trk><name>${xmlEscape(safe.trip?.name || 'Timeline track')}</name><trkseg>\n${points}\n  </trkseg></trk>\n</gpx>\n`;
}

export function makeTimelineCsvSummary(payload, options = {}) {
  const safe = sanitizeTimelineForExport(payload, options);
  const rows = [['time','category','eventType','severity','title','source','latitude','longitude','description']];
  safe.events.forEach(event => rows.push([formatExportTimestamp(event.timestamp), event.category, event.eventType, event.severity, event.title, event.sourceLabel || event.source, event.latitude ?? '', event.longitude ?? '', event.description || '']));
  return rows.map(row => row.map(csvEscape).join(',')).join('\n');
}

export function makeTimelineMarkdownStory(payload, options = {}) {
  const safe = sanitizeTimelineForExport(payload, options);
  const days = buildTimelineDaySummaries(safe.events, safe.ranges);
  const lines = [`# ${safe.trip?.name || 'MapPI3 Adventure Timeline'}`, '', `Exported: ${safe.exportedAt}`, '', `> ${safe.privacyNote}`, ''];
  days.forEach(day => {
    lines.push(`## ${day.label}`);
    lines.push(`Events: ${day.eventCount} · Warnings: ${day.warningCount} · Ranges: ${day.ranges}`);
    safe.events.filter(event => timestampDayKey(event.timestamp) === day.key).forEach(event => {
      const loc = finite(event.latitude) && finite(event.longitude) ? ` · ${event.latitude}, ${event.longitude}` : '';
      lines.push(`- **${new Date(event.timestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}** ${event.title} _${event.category}/${event.eventType}_${loc}`);
      if (event.description) lines.push(`  - ${event.description}`);
    });
    lines.push('');
  });
  lines.push('Safety note: MapPI3 records field memory and assists planning; it does not replace real navigation, weather, medical, or emergency tools.');
  return lines.join('\n');
}

export function timelineExportFilename(trip = {}, extension = 'json', privacy = 'shared') {
  const base = slug(trip.name || trip.routeName || trip.id || 'mappi3-adventure-timeline');
  return `${base}-${privacy}-timeline.${extension}`;
}

export const TIMELINE_EXPORT_FORMATS = [
  { id: 'json', label: 'JSON archive', extension: 'json', mime: 'application/json', make: makeTimelineJsonExport },
  { id: 'gpx', label: 'GPX track + waypoints', extension: 'gpx', mime: 'application/gpx+xml', make: makeTimelineGpxExport },
  { id: 'geojson', label: 'GeoJSON events', extension: 'geojson', mime: 'application/geo+json', make: makeTimelineGeoJsonExport },
  { id: 'csv', label: 'CSV event summary', extension: 'csv', mime: 'text/csv', make: makeTimelineCsvSummary },
  { id: 'markdown', label: 'Markdown trip story', extension: 'md', mime: 'text/markdown', make: makeTimelineMarkdownStory },
];
