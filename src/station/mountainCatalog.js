// The mountain catalog built from open data (tools/catalog/build_catalog.py -> public/catalog/mountains.json).
// Loaded once on demand; the service worker keeps a copy for offline use.
import { useEffect, useState } from 'react';

let cache = null, pending = null;
const listeners = new Set();
export function loadMountainCatalog() {
  if (cache) return Promise.resolve(cache);
  if (!pending) {
    pending = fetch('/catalog/mountains.json').then(r => (r.ok ? r.json() : null)).then(d => { cache = d; listeners.forEach(fn => fn(d)); return d; }).catch(() => { pending = null; return null; });
  }
  return pending;
}
export function useMountainCatalog() {
  const [data, setData] = useState(cache);
  useEffect(() => { if (!cache) { listeners.add(setData); loadMountainCatalog(); return () => listeners.delete(setData); } return undefined; }, []);
  return data;
}

// A catalog trail as a full MapPI3 route: out to the summit and back along the mapped trail.
export function catalogRoute(mountain, trail) {
  const out = trail.line || [];
  const line = out.length > 1 ? [...out, ...out.slice(0, -1).reverse()] : out;
  const [thLat, thLon] = trail.trailhead || [out[0]?.[1], out[0]?.[0]];
  return {
    id: trail.id,
    schemaVersion: 'mappi3.routePack.v1',
    name: `${mountain.name} via ${trail.name}`,
    place: `${mountain.town}, ${mountain.state}`,
    region: mountain.state,
    mountainArea: mountain.name,
    summary: `Out and back to the ${mountain.eleFt.toLocaleString()} ft summit of ${mountain.name}${trail.alsoSummits?.length ? `, passing ${trail.alsoSummits.join(', ')}` : ''}. Measured along the mapped trail.`,
    difficulty: trail.difficulty,
    routeType: 'Out-and-back',
    status: 'Ready',
    distanceMiles: trail.hikeMi,
    miles: trail.hikeMi,
    elevationGainFt: trail.gainFt,
    gain: `${Number(trail.gainFt || 0).toLocaleString()} ft`,
    estimatedTime: trail.estimatedTime,
    time: trail.estimatedTime,
    catalogCategory: 'mountain trail',
    summitEleFt: mountain.eleFt,
    mountainId: mountain.id,
    fromCatalog: true,
    tags: ['mountain', 'summit', 'openstreetmap', String(mountain.state || '').toLowerCase()],
    geometry: { type: 'LineString', coordinates: line },
    geometryQuality: 'OpenStreetMap trail network',
    source: 'OpenStreetMap contributors (ODbL)',
    waypoints: [
      { id: `${trail.id}-th`, name: `${trail.name.split(' to ')[0]} trailhead`, type: 'Start', mile: 0, lat: thLat, lon: thLon, elevationFt: trail.trailheadEleFt },
      { id: `${trail.id}-summit`, name: `${mountain.name} summit`, type: 'Summit', mile: trail.oneWayMi, lat: mountain.lat, lon: mountain.lon, elevationFt: mountain.eleFt, notes: `${mountain.eleFt.toLocaleString()} ft` },
      { id: `${trail.id}-end`, name: 'Back at the trailhead', type: 'Finish', mile: trail.hikeMi, lat: thLat, lon: thLon }
    ]
  };
}
export function catalogRoutes(catalog) {
  return (catalog?.mountains || []).flatMap(m => m.trails.map(t => catalogRoute(m, t)));
}

// An older catalog trail that the open-data catalog already covers (same mountain, trailhead within
// ~1.2 km) is hidden from search so each hike appears once. Its history still counts.
const normName = s => String(s || '').toLowerCase().replace(/\b(mount|mt\.?|mountain|peak)\b/g, '').replace(/[^a-z]/g, '');
const km = (a, b) => { const t = Math.PI / 180, dl = (b[0] - a[0]) * t, dn = (b[1] - a[1]) * t; const h = Math.sin(dl / 2) ** 2 + Math.cos(a[0] * t) * Math.cos(b[0] * t) * Math.sin(dn / 2) ** 2; return 12742 * Math.asin(Math.sqrt(h)); };
export function catalogTwin(route, catalog, mountainName) {
  if (!catalog || route?.fromCatalog || route?.custom || !mountainName) return null;
  const c = route?.geometry?.coordinates?.[0];
  if (!Array.isArray(c)) return null;
  const n = normName(mountainName);
  for (const m of catalog.mountains || []) {
    if (normName(m.name) !== n) continue;
    const near = m.trails.find(tr => km([c[1], c[0]], tr.trailhead) < 1.2);
    if (near) return near.id;
    // Older entries used rough planning lines, so also match the trail's own words ("Brook", "Parker Ridge").
    const skip = new Set(['trail', 'loop', 'path', 'via', 'the', 'mount', 'mountain', 'summit', ...String(m.name).toLowerCase().split(/[^a-z]+/)]);
    const words = String(route.name || '').toLowerCase().split(/[^a-z]+/).filter(w => w.length > 3 && !skip.has(w));
    const named = words.length && m.trails.find(tr => km([c[1], c[0]], tr.trailhead) < 5 && words.every(w => tr.name.toLowerCase().includes(w)));
    if (named) return named.id;
    if (!words.length && km([c[1], c[0]], [m.lat, m.lon]) < 5) return m.trails[0].id;
  }
  return null;
}
