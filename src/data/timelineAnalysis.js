import { normalizeTimelineEvent, normalizeTimelineRange } from './timelineModel.js';

const finite = (value) => Number.isFinite(Number(value));
const asNumber = (value, fallback = undefined) => finite(value) ? Number(value) : fallback;
const clamp = (value, min = 0, max = 1) => Math.max(min, Math.min(max, Number(value || 0)));
const mileMeters = 1609.344;

function routePoints(route = {}) {
  return (route.geometry?.coordinates || [])
    .map(([lon, lat], index) => ({ lat: Number(lat), lon: Number(lon), altitudeMeters: asNumber(route.elevationProfile?.[index]?.meters ?? route.elevations?.[index]) }))
    .filter(point => finite(point.lat) && finite(point.lon));
}

function milesBetween(a, b) {
  if (!a || !b) return 0;
  const r = 3958.8;
  const toRad = deg => deg * Math.PI / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(h)));
}

function pointAt(route = {}, ratio = 0) {
  const points = routePoints(route);
  if (!points.length) return null;
  const index = Math.round(clamp(ratio) * (points.length - 1));
  return points[index];
}

function nearestRouteFeet(route = {}, sample = {}) {
  const points = routePoints(route);
  if (!points.length || !finite(sample.lat ?? sample.latitude) || !finite(sample.lon ?? sample.longitude)) return null;
  const p = { lat: Number(sample.lat ?? sample.latitude), lon: Number(sample.lon ?? sample.longitude) };
  let best = Infinity;
  let bestIndex = 0;
  points.forEach((point, index) => {
    const feet = milesBetween(point, p) * 5280;
    if (feet < best) { best = feet; bestIndex = index; }
  });
  return { feet: best, routeIndex: bestIndex, ratio: points.length > 1 ? bestIndex / (points.length - 1) : 0 };
}

function sampleLatLon(sample = {}) {
  const lat = asNumber(sample.lat ?? sample.latitude);
  const lon = asNumber(sample.lon ?? sample.longitude);
  return finite(lat) && finite(lon) ? { lat, lon } : null;
}

function compactGpsSamples(archive = {}, route = {}, progress = 0) {
  const samples = (archive.gpsSamples || []).map(sample => ({ ...sample, lat: Number(sample.lat ?? sample.latitude), lon: Number(sample.lon ?? sample.longitude), timestamp: Number(sample.timestamp || Date.now()) })).filter(sample => finite(sample.lat) && finite(sample.lon) && finite(sample.timestamp)).sort((a, b) => a.timestamp - b.timestamp);
  if (samples.length) return samples.slice(-180);
  const current = pointAt(route, progress) || pointAt(route, 0.34);
  if (!current) return [];
  const now = Date.now();
  return [
    { id: 'estimate-start', timestamp: now - 55 * 60 * 1000, ...pointAt(route, 0) || current, source: 'route estimate' },
    { id: 'estimate-current', timestamp: now, ...current, source: 'route progress estimate' }
  ];
}

function gpsGapRanges(samples = [], tripId, thresholdMs) {
  const ranges = [];
  for (let index = 1; index < samples.length; index += 1) {
    const prev = samples[index - 1];
    const next = samples[index];
    const gap = next.timestamp - prev.timestamp;
    if (gap >= thresholdMs) {
      ranges.push(normalizeTimelineRange({
        id: `range-gps-gap-${prev.timestamp}-${next.timestamp}`,
        tripId,
        rangeType: 'gps-outage',
        category: 'gps',
        severity: 'caution',
        title: 'GPS signal gap',
        description: `No valid local GPS sample for ${Math.round(gap / 60000)} min. MapPI3 does not draw a fake path through this span.`,
        startTimestamp: prev.timestamp,
        endTimestamp: next.timestamp,
        metadata: { thresholdMinutes: Math.round(thresholdMs / 60000), stalePosition: true }
      }));
    }
  }
  return ranges;
}

function restRanges(samples = [], tripId, minMs = 10 * 60 * 1000, radiusFeet = 150) {
  const ranges = [];
  let start = 0;
  for (let index = 1; index <= samples.length; index += 1) {
    const origin = samples[start];
    const current = samples[index];
    const inside = origin && current && milesBetween(origin, current) * 5280 <= radiusFeet;
    if (!inside || index === samples.length) {
      const end = samples[index - 1];
      const duration = end && origin ? end.timestamp - origin.timestamp : 0;
      if (duration >= minMs) {
        ranges.push(normalizeTimelineRange({
          id: `range-rest-${origin.timestamp}-${end.timestamp}`,
          tripId,
          rangeType: 'rest',
          category: 'route',
          title: 'Likely rest/stop',
          description: `Position stayed within about ${radiusFeet} ft for ${Math.round(duration / 60000)} min. Estimate from local samples.`,
          startTimestamp: origin.timestamp,
          endTimestamp: end.timestamp,
          metadata: { radiusFeet, durationMinutes: Math.round(duration / 60000), lat: origin.lat, lon: origin.lon }
        }));
      }
      start = Math.max(0, index - 1);
    }
  }
  return ranges.slice(-6);
}

function deviationSignals(samples = [], route = {}, tripId, thresholdFeet = 250) {
  const events = [];
  const ranges = [];
  let open = null;
  let max = null;
  for (const sample of samples) {
    const nearest = nearestRouteFeet(route, sample);
    if (!nearest) continue;
    const off = nearest.feet >= thresholdFeet;
    if (off && !open) { open = sample; max = { sample, feet: nearest.feet }; }
    if (off && nearest.feet > (max?.feet || 0)) max = { sample, feet: nearest.feet };
    if (!off && open) {
      if (sample.timestamp - open.timestamp >= 2 * 60 * 1000) {
        ranges.push(normalizeTimelineRange({ id:`range-route-dev-${open.timestamp}-${sample.timestamp}`, tripId, rangeType:'route-deviation', category:'warning', severity:'caution', title:'Off-route span', description:`Local samples were beyond ${thresholdFeet} ft from the route. Maximum estimate: ${Math.round(max.feet)} ft.`, startTimestamp:open.timestamp, endTimestamp:sample.timestamp, metadata:{ thresholdFeet, maxFeet:Math.round(max.feet) } }));
        const ll = sampleLatLon(max.sample);
        events.push(normalizeTimelineEvent({ id:`event-route-dev-max-${max.sample.timestamp}`, tripId, category:'warning', eventType:'route-deviation-max', title:'Max off-route estimate', description:`Estimated ${Math.round(max.feet)} ft from route. Verify with real map/compass before acting.`, timestamp:max.sample.timestamp, lat:ll?.lat, lon:ll?.lon, automaticallyGenerated:true, sourceLabel:'local route distance estimate', metadata:{ thresholdFeet, offRouteFeet:Math.round(max.feet) } }));
      }
      open = null; max = null;
    }
  }
  return { events, ranges };
}

function weatherEvents(snapshots = [], conditions = {}, tripId, basePoint, timestamp = Date.now()) {
  const events = [];
  const recent = snapshots.filter(s => s.kind === 'environment' && finite(s.pressureHpa)).slice(-20);
  if (recent.length >= 2) {
    const first = recent[0];
    const last = recent.at(-1);
    const hours = Math.max((last.timestamp - first.timestamp) / 3600000, 0.01);
    const drop = Number(first.pressureHpa) - Number(last.pressureHpa);
    if (drop >= 2 && hours <= 3.25) {
      events.push(normalizeTimelineEvent({ id:`weather-pressure-drop-${first.timestamp}-${last.timestamp}`, tripId, category:'weather', eventType:'pressure-drop', severity:'caution', title:'Rapid pressure drop estimate', description:`Pressure fell ${drop.toFixed(1)} hPa over ${hours.toFixed(1)}h from local samples. Treat as a caution cue, not a guaranteed forecast.`, timestamp:last.timestamp, lat:basePoint?.lat, lon:basePoint?.lon, automaticallyGenerated:true, sourceLabel:'local/sensor weather trend', metadata:{ pressureDropHpa:drop, hours } }));
    }
  }
  if (finite(conditions.tempF)) {
    events.push(normalizeTimelineEvent({ id:`weather-current-${Math.round(timestamp / 900000)}`, tripId, category:'weather', eventType:'environment-sample', title:'Environment sample', description:`${Math.round(Number(conditions.tempF))}°F · humidity ${conditions.humidity ?? '—'}% · ${conditions.source || 'local estimate/cache'}.`, timestamp, lat:basePoint?.lat, lon:basePoint?.lon, automaticallyGenerated:true, sourceLabel:conditions.source || 'local/browser weather cache', metadata:{ tempF:conditions.tempF, humidity:conditions.humidity, pressureHpa:conditions.pressureHpa, source:conditions.source } }));
  }
  return events;
}

function batteryEvents(snapshots = [], batteryPercent, tripId, basePoint, timestamp = Date.now()) {
  const events = [];
  const percent = asNumber(batteryPercent);
  if (!finite(percent)) return events;
  const crossed = percent <= 10 ? 'critical' : percent <= 20 ? 'low' : percent <= 50 ? 'half' : '';
  if (crossed) {
    events.push(normalizeTimelineEvent({ id:`battery-${crossed}-${Math.round(timestamp / 900000)}`, tripId, category: percent <= 10 ? 'emergency' : 'battery', eventType:`battery-${crossed}`, severity:percent <= 20 ? 'caution' : 'info', title:percent <= 10 ? 'Battery critical' : percent <= 20 ? 'Battery low' : 'Battery under 50%', description:`Field kit/browser battery estimate is ${Math.round(percent)}%. Verify actual PiSugar/phone power before relying on it.`, timestamp, lat:basePoint?.lat, lon:basePoint?.lon, automaticallyGenerated:true, sourceLabel:'local battery setting/sample', batterySnapshot:{ percent }, metadata:{ percent } }));
  }
  return events;
}

function elevationProfile(route = {}, samples = []) {
  const routeAlt = routePoints(route).map((point, index) => ({ index, altitudeMeters: point.altitudeMeters })).filter(point => finite(point.altitudeMeters));
  const gpsAlt = samples.map((sample, index) => ({ index, altitudeMeters: asNumber(sample.altitudeMeters ?? sample.altitude ?? sample.elevationMeters) })).filter(point => finite(point.altitudeMeters));
  const source = gpsAlt.length >= 2 ? gpsAlt : routeAlt;
  if (!source.length) return { points: [], stats: null };
  const values = source.map(p => p.altitudeMeters);
  let ascent = 0, descent = 0;
  values.forEach((value, index) => { if (!index) return; const delta = value - values[index - 1]; if (Math.abs(delta) < 1.5) return; if (delta > 0) ascent += delta; else descent += Math.abs(delta); });
  return { points: source.slice(-80), stats: { minMeters: Math.min(...values), maxMeters: Math.max(...values), ascentMeters: ascent, descentMeters: descent, source: gpsAlt.length >= 2 ? 'GPS altitude samples' : 'route elevation profile' } };
}

export function buildTimelineSignalLayers({ archive = {}, route = {}, conditions = {}, launchPlan = {}, settings = {}, progress = 0, elapsed = 0, generatedEvents = [] } = {}) {
  const tripId = archive.activeTripId || archive.trips?.[0]?.id || generatedEvents[0]?.tripId || 'active-trip';
  const samples = compactGpsSamples(archive, route, progress);
  const now = Date.now();
  const basePoint = sampleLatLon(samples.at(-1)) || pointAt(route, progress) || pointAt(route, 0.34);
  const gapThresholdMs = Math.max(5, Number(settings.timelineGpsGapMinutes || 15)) * 60 * 1000;
  const ranges = [...gpsGapRanges(samples, tripId, gapThresholdMs), ...restRanges(samples, tripId)];
  const deviation = deviationSignals(samples, route, tripId, Number(settings.timelineOffRouteFeet || 250));
  const batteryPercent = launchPlan.batteryPercent ?? settings.batteryPercent ?? settings.piBatteryPercent;
  const events = [
    ...deviation.events,
    ...weatherEvents(archive.snapshots || [], conditions, tripId, basePoint, now),
    ...batteryEvents(archive.snapshots || [], batteryPercent, tripId, basePoint, now)
  ];
  const elevation = elevationProfile(route, samples);
  return { events, ranges: [...ranges, ...deviation.ranges], samples, elevation };
}
