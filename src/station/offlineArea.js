// Offline areas: save everything needed to hike an area with no signal: map, satellite, terrain
// (for the profile, 3D view and summit panorama) and OpenStreetMap trail lines and points.
// Sources are ones that allow offline caching: USGS National Map (public domain), AWS open
// terrain tiles, and a single Overpass API query per area (OpenStreetMap data, ODbL).
import { TERRARIUM_URL, destination, latToTileY, lonToTileX, milesBetween, tileUrl } from './terrain.js';

export const AREA_CACHE = 'mappi3-areas-v1';
export const AREA_LAYERS = {
  topo: { label: 'Topo map', url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}', zmin: 10, zmax: 16, kb: 22 },
  satellite: { label: 'Satellite', url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}', zmin: 10, zmax: 16, kb: 26 },
  hybrid: { label: 'Satellite + labels', url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}', zmin: 12, zmax: 16, kb: 30 },
  terrain: { label: 'Terrain (3D + profile)', url: TERRARIUM_URL, zmin: 9, zmax: 13, kb: 105 }
};
const OVERPASS = 'https://overpass-api.de/api/interpreter';
const osmKey = id => `/offline-area/${encodeURIComponent(id)}/osm.json`;
const LIST_KEY = 'mappi3.offlineAreas';

export function listAreas() { try { return JSON.parse(localStorage.getItem(LIST_KEY) || '[]'); } catch { return []; } }
function saveList(list) { try { localStorage.setItem(LIST_KEY, JSON.stringify(list)); } catch { /* ignore */ } window.dispatchEvent(new CustomEvent('mappi3-areas')); }
export function areaForRoute(routeId) { return listAreas().find(a => a.routeId === routeId) || null; }

// Box around the whole route plus a margin, so side trails and nearby water are included.
export function bboxForRoute(route, marginMi = 1.5) {
  const pts = [...(route?.geometry?.coordinates || []).map(([lon, lat]) => ({ lat, lon })), ...(route?.waypoints || []).filter(w => Number.isFinite(w.lat)).map(w => ({ lat: w.lat, lon: w.lon }))];
  if (!pts.length) return null;
  let s = 90, w = 180, n = -90, e = -180;
  pts.forEach(p => { s = Math.min(s, p.lat); n = Math.max(n, p.lat); w = Math.min(w, p.lon); e = Math.max(e, p.lon); });
  const sw = destination(destination({ lat: s, lon: w }, 180, marginMi), 270, marginMi);
  const ne = destination(destination({ lat: n, lon: e }, 0, marginMi), 90, marginMi);
  return { s: sw.lat, w: sw.lon, n: ne.lat, e: ne.lon };
}
function tilesFor(bbox, zmin, zmax) {
  const out = [];
  for (let z = zmin; z <= zmax; z += 1) {
    const x0 = Math.floor(lonToTileX(bbox.w, z)), x1 = Math.floor(lonToTileX(bbox.e, z));
    const y0 = Math.floor(latToTileY(bbox.n, z)), y1 = Math.floor(latToTileY(bbox.s, z));
    for (let x = x0; x <= x1; x += 1) for (let y = y0; y <= y1; y += 1) out.push({ z, x, y });
  }
  return out;
}
// The summit panorama looks 40 km out, so terrain is also saved at low zoom around the high point.
function panoramaTiles(center) {
  if (!center) return [];
  const r = 26;
  const box = { n: destination(center, 0, r).lat, s: destination(center, 180, r).lat, e: destination(center, 90, r).lon, w: destination(center, 270, r).lon };
  return tilesFor(box, 10, 10);
}

export function planDownload(route, layers = ['topo', 'satellite', 'terrain'], marginMi = 1.5) {
  const bbox = bboxForRoute(route, marginMi);
  if (!bbox) return null;
  const jobs = [];
  let kb = 0;
  layers.forEach(key => { const L = AREA_LAYERS[key]; tilesFor(bbox, L.zmin, L.zmax).forEach(t => { jobs.push({ key, url: tileUrl(L.url, t.z, t.x, t.y) }); kb += L.kb; }); });
  if (layers.includes('terrain')) {
    const hi = (route.waypoints || []).find(w => /summit|peak|view|top|pond|turnaround/i.test(`${w.type} ${w.name}`)) || route.waypoints?.at(-1);
    panoramaTiles(hi && Number.isFinite(hi.lat) ? { lat: hi.lat, lon: hi.lon } : null).forEach(t => { const url = tileUrl(TERRARIUM_URL, t.z, t.x, t.y); if (!jobs.some(j => j.url === url)) { jobs.push({ key: 'terrain', url }); kb += AREA_LAYERS.terrain.kb; } });
  }
  const areaSqMi = milesBetween({ lat: bbox.s, lon: bbox.w }, { lat: bbox.s, lon: bbox.e }) * milesBetween({ lat: bbox.s, lon: bbox.w }, { lat: bbox.n, lon: bbox.w });
  return { bbox, jobs, tiles: jobs.length, estMb: Math.round(kb / 102.4) / 10, areaSqMi: Math.round(areaSqMi * 10) / 10 };
}

// Trails, water, camps, viewpoints and peaks in the box (plus peaks 40 km around for the panorama).
async function fetchOsm(bbox, center) {
  const b = `${bbox.s},${bbox.w},${bbox.n},${bbox.e}`;
  const around = center ? `node["natural"="peak"](around:40000,${center.lat},${center.lon});` : '';
  const q = `[out:json][timeout:60];(way["highway"~"^(path|footway|track|bridleway|steps)$"](${b});node["natural"~"^(peak|spring|saddle)$"](${b});node["tourism"~"^(viewpoint|camp_site|alpine_hut|wilderness_hut)$"](${b});node["amenity"~"^(shelter|drinking_water|toilets|parking)$"](${b});way["waterway"~"^(stream|river)$"](${b});node["waterway"="waterfall"](${b});way["natural"="water"](${b});${around});out body geom qt;`;
  const res = await fetch(OVERPASS, { method: 'POST', body: `data=${encodeURIComponent(q)}`, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  if (!res.ok) throw new Error(`OpenStreetMap query failed (${res.status})`);
  const raw = await res.json();
  const ways = [], points = [], water = [];
  (raw.elements || []).forEach(el => {
    const t = el.tags || {};
    if (el.type === 'way' && el.geometry) {
      const line = el.geometry.map(g => [Number(g.lon.toFixed(6)), Number(g.lat.toFixed(6))]);
      if (t.highway) ways.push({ id: el.id, name: t.name || t.ref || '', kind: t.highway, nodes: el.nodes, line });
      else water.push({ id: el.id, name: t.name || '', kind: t.waterway || 'water', line });
    } else if (el.type === 'node') {
      const kind = t.natural || t.tourism || t.amenity || t.waterway;
      points.push({ id: el.id, lat: el.lat, lon: el.lon, kind, name: t.name || '', ele: t.ele ? Number(t.ele) : null });
    }
  });
  return { fetchedAt: Date.now(), bbox, ways, water, points, attribution: '© OpenStreetMap contributors (ODbL)' };
}

export async function loadAreaOsm(areaId) {
  try { const cache = await caches.open(AREA_CACHE); const hit = await cache.match(osmKey(areaId)); return hit ? await hit.json() : null; } catch { return null; }
}

// Downloads an area. onProgress({ done, total, failed, phase }). Returns the saved area record.
export async function downloadArea(route, { layers = ['topo', 'satellite', 'terrain'], marginMi = 1.5, onProgress = () => {}, signal } = {}) {
  if (!('caches' in window)) throw new Error('This browser cannot save offline maps. Use Chrome, Edge or Safari over HTTPS or the MapPI3 hotspot.');
  const plan = planDownload(route, layers, marginMi);
  if (!plan) throw new Error('This trail has no map line to save around.');
  const id = `area-${route.id}`;
  const cache = await caches.open(AREA_CACHE);
  try { if (navigator.storage?.persist) await navigator.storage.persist(); } catch { /* optional */ }
  let done = 0, failed = 0, bytes = 0;
  const queue = [...plan.jobs];
  const worker = async () => {
    while (queue.length) {
      if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
      const job = queue.shift();
      try {
        const have = await cache.match(job.url);
        if (have) { done += 1; } else {
          const res = await fetch(job.url, { mode: 'cors', signal });
          if (res.ok) { const blob = await res.blob(); bytes += blob.size; await cache.put(job.url, new Response(blob, { headers: { 'Content-Type': res.headers.get('Content-Type') || 'image/png' } })); } else failed += 1;
          done += 1;
        }
      } catch (e) { if (e.name === 'AbortError') throw e; failed += 1; done += 1; }
      if (done % 8 === 0 || !queue.length) onProgress({ done, total: plan.tiles, failed, phase: 'tiles', mb: Math.round(bytes / 104857.6) / 10 });
    }
  };
  await Promise.all(Array.from({ length: 6 }, worker));
  onProgress({ done, total: plan.tiles, failed, phase: 'trails' });
  let osm = null, osmError = '';
  try {
    const hi = (route.waypoints || []).at(-1);
    osm = await fetchOsm(plan.bbox, hi && Number.isFinite(hi.lat) ? { lat: hi.lat, lon: hi.lon } : null);
    await cache.put(osmKey(id), new Response(JSON.stringify(osm), { headers: { 'Content-Type': 'application/json' } }));
  } catch (e) { osmError = e.message; }
  const record = { id, routeId: route.id, name: route.name, bbox: plan.bbox, layers, tiles: plan.tiles, failed, mb: Math.round(bytes / 104857.6) / 10, trails: osm ? osm.ways.length : 0, points: osm ? osm.points.length : 0, osmError, savedAt: Date.now() };
  saveList([record, ...listAreas().filter(a => a.id !== id)]);
  onProgress({ done, total: plan.tiles, failed, phase: 'done' });
  return record;
}

export async function deleteArea(id) {
  const area = listAreas().find(a => a.id === id);
  if (area) {
    try {
      const cache = await caches.open(AREA_CACHE);
      const plan = { bbox: area.bbox };
      const keep = new Set();
      listAreas().filter(a => a.id !== id).forEach(a => a.layers.forEach(k => { const L = AREA_LAYERS[k]; tilesFor(a.bbox, L.zmin, L.zmax).forEach(t => keep.add(tileUrl(L.url, t.z, t.x, t.y))); }));
      await Promise.all(area.layers.flatMap(k => { const L = AREA_LAYERS[k]; return tilesFor(plan.bbox, L.zmin, L.zmax).map(t => tileUrl(L.url, t.z, t.x, t.y)).filter(u => !keep.has(u)).map(u => cache.delete(u)); }));
      await cache.delete(osmKey(id));
    } catch { /* cache already gone */ }
  }
  saveList(listAreas().filter(a => a.id !== id));
}

// ---- Trail geometry from OpenStreetMap ----
const M_PER_DEG = 111320;
function segDistM(p, a, b) {
  const kx = Math.cos((p.lat * Math.PI) / 180) * M_PER_DEG, ky = M_PER_DEG;
  const ax = (a[0] - p.lon) * kx, ay = (a[1] - p.lat) * ky, bx = (b[0] - p.lon) * kx, by = (b[1] - p.lat) * ky;
  const vx = bx - ax, vy = by - ay, len2 = vx * vx + vy * vy || 1;
  const t = Math.max(0, Math.min(1, -(ax * vx + ay * vy) / len2));
  return Math.hypot(ax + vx * t, ay + vy * t);
}
// Distance in metres from a point to the nearest mapped trail, and that trail's name.
export function nearestTrail(osm, p) {
  let best = { m: Infinity, name: '' };
  (osm?.ways || []).forEach(w => { for (let i = 1; i < w.line.length; i += 1) { const d = segDistM(p, w.line[i - 1], w.line[i]); if (d < best.m) best = { m: d, name: w.name, kind: w.kind }; } });
  return best;
}

// Rebuilds a detailed trail line by routing over the OpenStreetMap path network from the trailhead to
// the far end, preferring ways that follow the planning line and carry the trail's name.
export function refineRouteLine(route, osm) {
  return refineByName(route, osm) || refineByCorridor(route, osm);
}

// First choice: the OSM ways that carry the trail's own name. "Tumbledown Brook Trail" in the
// Tumbledown area matches ways named "Brook Trail"; area words like "Tumbledown" are ignored.
function refineByName(route, osm) {
  const ways = osm?.ways || [];
  const stop = new Set(['trail', 'trails', 'loop', 'path', 'via', 'the', 'and', 'mount', 'mountain', 'approach', 'alternate', 'route', 'road', 'from', 'with']);
  const areaWords = new Set(`${route.mountainArea || ''} ${route.place || ''} ${route.region || ''}`.toLowerCase().split(/[^a-z]+/));
  const words = String(route.name || '').toLowerCase().split(/[^a-z]+/).filter(w => w.length > 2 && !stop.has(w));
  const distinctive = words.filter(w => !areaWords.has(w));
  const want = distinctive.length ? distinctive : words;
  if (!want.length) return null;
  const score = w => want.filter(x => String(w.name || '').toLowerCase().includes(x)).length;
  const top = Math.max(0, ...ways.map(score));
  if (!top) return null;
  const chosen = ways.filter(w => score(w) === top && w.line.length > 1);
  const key = c => `${c[0].toFixed(6)},${c[1].toFixed(6)}`;
  const g = new Map();
  const link = (a, b) => { const ka = key(a), kb = key(b); const w = milesBetween({ lat: a[1], lon: a[0] }, { lat: b[1], lon: b[0] }); if (!g.has(ka)) g.set(ka, { c: a, e: [] }); if (!g.has(kb)) g.set(kb, { c: b, e: [] }); g.get(ka).e.push({ to: kb, w }); g.get(kb).e.push({ to: ka, w }); };
  chosen.forEach(w => { for (let i = 1; i < w.line.length; i += 1) link(w.line[i - 1], w.line[i]); });
  const coarseStart = (route.geometry?.coordinates || [])[0];
  if (!coarseStart) return null;
  const start0 = { lat: coarseStart[1], lon: coarseStart[0] };
  const ends = [...g.entries()].filter(([, n]) => n.e.length === 1);
  const pool = ends.length ? ends : [...g.entries()];
  const [startKey] = pool.reduce((best, cur) => { const d = milesBetween(start0, { lat: cur[1].c[1], lon: cur[1].c[0] }); return d < best[1] ? [cur[0], d] : best; }, [null, Infinity]);
  if (!startKey || milesBetween(start0, { lat: g.get(startKey).c[1], lon: g.get(startKey).c[0] }) > 2) return null;
  const { dist, prev } = dijkstra(g, startKey);
  let endKey = null, far = -1;
  dist.forEach((d, k) => { if (d > far) { far = d; endKey = k; } });
  if (!endKey || far < 0.2) return null;
  const path = [];
  for (let k = endKey; k; k = prev.get(k)) { path.push(g.get(k).c); if (k === startKey) break; }
  path.reverse();
  return finishLine(route, path, `OpenStreetMap "${chosen[0].name}"`);
}
function dijkstra(g, startKey) {
  const dist = new Map([[startKey, 0]]), prev = new Map(), heap = [[0, startKey]];
  const push = (item) => { heap.push(item); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
  const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
  while (heap.length) { const [d, k] = pop(); if (d > (dist.get(k) ?? Infinity)) continue; g.get(k).e.forEach(({ to, w }) => { const nd = d + w; if (nd < (dist.get(to) ?? Infinity)) { dist.set(to, nd); prev.set(to, k); push([nd, to]); } }); }
  return { dist, prev };
}
function finishLine(route, path, source) {
  if (path.length < 3) return null;
  const out = /out-and-back/i.test(route.routeType || '');
  let oneWay = 0;
  for (let i = 1; i < path.length; i += 1) oneWay += milesBetween({ lat: path[i - 1][1], lon: path[i - 1][0] }, { lat: path[i][1], lon: path[i][0] });
  // An out-and-back listing covers the trail twice; only double it if the listed distance says so.
  const listed = Number(route.distanceMiles || 0);
  const doubled = out && listed && Math.abs(oneWay * 2 - listed) < Math.abs(oneWay - listed);
  const line = doubled ? [...path, ...path.slice(0, -1).reverse()] : path;
  const miles = doubled ? oneWay * 2 : oneWay;
  return { coordinates: line, miles: Math.round(miles * 100) / 100, points: line.length, source, builtAt: Date.now() };
}

function refineByCorridor(route, osm) {
  const ways = osm?.ways || [];
  if (!ways.length) return null;
  const coarse = (route.geometry?.coordinates || []).map(([lon, lat]) => ({ lat, lon }));
  if (coarse.length < 2) return null;
  const key = c => `${c[0].toFixed(6)},${c[1].toFixed(6)}`;
  const nodes = new Map(); // key -> {c, edges:[{to, w}]}
  const words = String(route.name || '').toLowerCase().replace(/trail|loop|path|via|the/g, ' ').split(/\s+/).filter(w => w.length > 3);
  const add = (a, b, w) => { const ka = key(a), kb = key(b); if (!nodes.has(ka)) nodes.set(ka, { c: a, e: [] }); if (!nodes.has(kb)) nodes.set(kb, { c: b, e: [] }); nodes.get(ka).e.push({ to: kb, w }); nodes.get(kb).e.push({ to: ka, w }); };
  const nearCoarse = (c) => { let m = Infinity; for (let i = 1; i < coarse.length; i += 1) m = Math.min(m, segDistM({ lat: c[1], lon: c[0] }, [coarse[i - 1].lon, coarse[i - 1].lat], [coarse[i].lon, coarse[i].lat])); return m; };
  ways.forEach(w => {
    const named = words.some(x => String(w.name || '').toLowerCase().includes(x));
    for (let i = 1; i < w.line.length; i += 1) {
      const a = w.line[i - 1], b = w.line[i];
      const len = milesBetween({ lat: a[1], lon: a[0] }, { lat: b[1], lon: b[0] }) * 1609.34;
      const off = nearCoarse([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
      const cost = len * (1 + Math.min(4, off / 250)) * (named ? 0.55 : 1) * (w.kind === 'track' ? 1.3 : 1);
      add(a, b, cost);
    }
  });
  const nearestNode = (p) => { let best = null, bd = Infinity; nodes.forEach((n, k) => { const d = milesBetween(p, { lat: n.c[1], lon: n.c[0] }); if (d < bd) { bd = d; best = k; } }); return { k: best, mi: bd }; };
  const start = nearestNode(coarse[0]);
  const out = /out-and-back/i.test(route.routeType || '');
  const farWp = (route.waypoints || []).filter(w => Number.isFinite(w.lat)).sort((a, b) => Number(b.mile) - Number(a.mile))[0];
  const endPoint = out ? (farWp ? { lat: farWp.lat, lon: farWp.lon } : coarse[Math.floor(coarse.length / 2)]) : coarse.at(-1);
  const end = nearestNode(endPoint);
  if (!start.k || !end.k || start.mi > 0.75 || end.mi > 0.75) return null;
  // Dijkstra with a simple binary heap.
  const dist = new Map([[start.k, 0]]), prev = new Map(), heap = [[0, start.k]];
  const push = (item) => { heap.push(item); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
  const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
  while (heap.length) {
    const [d, k] = pop();
    if (k === end.k) break;
    if (d > (dist.get(k) ?? Infinity)) continue;
    nodes.get(k).e.forEach(({ to, w }) => { const nd = d + w; if (nd < (dist.get(to) ?? Infinity)) { dist.set(to, nd); prev.set(to, k); push([nd, to]); } });
  }
  if (!dist.has(end.k)) return null;
  const path = [];
  for (let k = end.k; k; k = prev.get(k)) { path.push(nodes.get(k).c); if (k === start.k) break; }
  path.reverse();
  if (path.length < 3) return null;
  const line = out ? [...path, ...path.slice(0, -1).reverse()] : path;
  let miles = 0;
  for (let i = 1; i < line.length; i += 1) miles += milesBetween({ lat: line[i - 1][1], lon: line[i - 1][0] }, { lat: line[i][1], lon: line[i][0] });
  return { coordinates: line, miles: Math.round(miles * 100) / 100, points: line.length, source: 'OpenStreetMap trail network', builtAt: Date.now() };
}
