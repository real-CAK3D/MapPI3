// Terrain from the open AWS Terrain Tiles (Terrarium PNG encoding, public data, CORS-enabled).
// Tiles fetched here go through the service worker, so an area saved offline keeps working.
export const TERRARIUM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
export const tileUrl = (tpl, z, x, y) => tpl.replace('{z}', z).replace('{x}', x).replace('{y}', y);

export const lonToTileX = (lon, z) => ((lon + 180) / 360) * 2 ** z;
export const latToTileY = (lat, z) => { const r = (lat * Math.PI) / 180; return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 2 ** z; };
export const tileXToLon = (x, z) => (x / 2 ** z) * 360 - 180;
export const tileYToLat = (y, z) => { const n = Math.PI - (2 * Math.PI * y) / 2 ** z; return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))); };

const R_MI = 3958.8;
export function milesBetween(a, b) {
  const toR = d => (d * Math.PI) / 180;
  const dLat = toR(b.lat - a.lat), dLon = toR(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toR(a.lat)) * Math.cos(toR(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R_MI * Math.asin(Math.sqrt(h));
}
export function bearingDeg(a, b) {
  const toR = d => (d * Math.PI) / 180;
  const y = Math.sin(toR(b.lon - a.lon)) * Math.cos(toR(b.lat));
  const x = Math.cos(toR(a.lat)) * Math.sin(toR(b.lat)) - Math.sin(toR(a.lat)) * Math.cos(toR(b.lat)) * Math.cos(toR(b.lon - a.lon));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}
export function destination(p, bearing, miles) {
  const toR = d => (d * Math.PI) / 180, toD = r => (r * 180) / Math.PI;
  const d = miles / R_MI, br = toR(bearing), la = toR(p.lat), lo = toR(p.lon);
  const la2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(br));
  const lo2 = lo + Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(la2));
  return { lat: toD(la2), lon: ((toD(lo2) + 540) % 360) - 180 };
}

const pixelCache = new Map(); // "z/x/y" -> Promise<Uint8ClampedArray|null>
function loadTilePixels(z, x, y) {
  const key = `${z}/${x}/${y}`;
  if (pixelCache.has(key)) return pixelCache.get(key);
  const job = (async () => {
    try {
      const res = await fetch(tileUrl(TERRARIUM_URL, z, x, y), { mode: 'cors' });
      if (!res.ok) return null;
      const bitmap = await createImageBitmap(await res.blob());
      const canvas = typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(256, 256) : Object.assign(document.createElement('canvas'), { width: 256, height: 256 });
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(bitmap, 0, 0);
      return ctx.getImageData(0, 0, 256, 256).data;
    } catch { return null; }
  })();
  pixelCache.set(key, job);
  if (pixelCache.size > 400) pixelCache.delete(pixelCache.keys().next().value);
  return job;
}

// Elevation in metres, or null when the tile is not reachable (offline and not saved).
export async function elevationAt(lat, lon, z = 12) {
  const fx = lonToTileX(lon, z), fy = latToTileY(lat, z);
  const x = Math.floor(fx), y = Math.floor(fy);
  const px = await loadTilePixels(z, x, y);
  if (!px) return null;
  const ix = Math.min(255, Math.floor((fx - x) * 256)), iy = Math.min(255, Math.floor((fy - y) * 256));
  const i = (iy * 256 + ix) * 4;
  return px[i] * 256 + px[i + 1] + px[i + 2] / 256 - 32768;
}

export function lineFromRoute(route) {
  return (route?.geometry?.coordinates || []).filter(c => Number.isFinite(c?.[0]) && Number.isFinite(c?.[1])).map(([lon, lat]) => ({ lat, lon }));
}

// Walks the line and samples the terrain every step. The route's own distance is kept as the
// mile scale so waypoint miles line up even when the stored geometry is simplified.
export async function profileForRoute(route, samples = 140) {
  const line = lineFromRoute(route);
  if (line.length < 2) return null;
  const legs = [];
  let total = 0;
  for (let i = 1; i < line.length; i += 1) { const d = milesBetween(line[i - 1], line[i]); legs.push(d); total += d; }
  if (!total) return null;
  const routeMiles = Number(route.distanceMiles || route.miles || total);
  const scale = routeMiles / total;
  const pts = [];
  for (let s = 0; s <= samples; s += 1) {
    let target = (total * s) / samples, i = 0;
    while (i < legs.length - 1 && target > legs[i]) { target -= legs[i]; i += 1; }
    const t = legs[i] ? Math.min(1, target / legs[i]) : 0;
    const a = line[i], b = line[i + 1];
    pts.push({ lat: a.lat + (b.lat - a.lat) * t, lon: a.lon + (b.lon - a.lon) * t, mile: ((total * s) / samples) * scale });
  }
  const elevs = await Promise.all(pts.map(p => elevationAt(p.lat, p.lon)));
  if (elevs.filter(v => v !== null).length < pts.length * 0.6) return null;
  let last = elevs.find(v => v !== null);
  const out = pts.map((p, i) => { if (elevs[i] !== null) last = elevs[i]; return { ...p, ft: last * 3.28084 }; });
  // Light smoothing removes single-pixel spikes without flattening real climbs.
  const smooth = out.map((p, i) => ({ ...p, ft: (out[Math.max(0, i - 1)].ft + p.ft * 2 + out[Math.min(out.length - 1, i + 1)].ft) / 4 }));
  let gain = 0;
  for (let i = 1; i < smooth.length; i += 1) gain += Math.max(0, smooth[i].ft - smooth[i - 1].ft);
  const listed = Number(route.elevationGainFt || 0);
  // A simplified planning line can miss the climb entirely. If the terrain along it disagrees badly
  // with the trail's listed gain, trust the listing until a detailed trail line is saved.
  if (listed > 300 && (gain < listed * 0.45 || gain > listed * 2.5)) return { ...estimatedProfile(route), note: `estimate · saved trail line is approximate (terrain along it: ${Math.round(gain)} ft)` };
  return { points: smooth, gainFt: Math.round(gain), minFt: Math.round(Math.min(...smooth.map(p => p.ft))), maxFt: Math.round(Math.max(...smooth.map(p => p.ft))), source: 'terrain' };
}

// Fallback when terrain tiles are unavailable: a straight climb from the route's stated gain.
export function estimatedProfile(route, samples = 40) {
  const miles = Number(route?.distanceMiles || route?.miles || 1);
  const start = Number(route?.waypoints?.[0]?.elevationFt || 1000);
  const gain = Number(route?.elevationGainFt || 0);
  const out = /out-and-back/i.test(route?.routeType || '');
  const points = Array.from({ length: samples + 1 }, (_, i) => { const f = i / samples; const shape = out ? Math.sin(Math.PI * f) : Math.sin((Math.PI / 2) * f); return { mile: miles * f, ft: start + gain * shape }; });
  return { points, gainFt: gain, minFt: Math.round(start), maxFt: Math.round(start + gain), source: 'estimate' };
}
