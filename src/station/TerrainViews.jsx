import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
// MapLibre finds its worker next to its own file, which a bundler moves; point it at the bundled copy.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { AREA_LAYERS } from './offlineArea.js';
import { TERRARIUM_URL, bearingDeg, destination, elevationAt, milesBetween } from './terrain.js';
import { useRouteProfile, waypointKind } from './ElevationProfile.jsx';
import { markerHtml, markerKind } from './markers.js';

// 3D terrain map and a computed "view from the top" panorama. Both read the same terrain and imagery
// tiles that an offline area saves, so they work with no signal once the area is saved.
export default function TerrainViews({ mode = '3d', setMode, route, waypoints = [], osm = null, youPoint = null }) {
  useEffect(() => { const k = e => { if (e.key === 'Escape') setMode(null); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, []);
  return createPortal(<div className="tv-backdrop" role="dialog" aria-label={mode === '3d' ? '3D trail view' : 'View from the top'}>
    <div className="tv-panel">
      <header className="tv-head">
        <div className="tv-tabs" role="tablist"><button type="button" role="tab" aria-selected={mode === '3d'} className={mode === '3d' ? 'on' : ''} onClick={() => setMode('3d')}>3D map</button><button type="button" role="tab" aria-selected={mode === 'panorama'} className={mode === 'panorama' ? 'on' : ''} onClick={() => setMode('panorama')}>View from the top</button></div>
        <strong className="tv-title">{route?.name}</strong>
        <button type="button" className="ghost small" onClick={() => setMode(null)}>Close</button>
      </header>
      {mode === '3d' ? <Terrain3D route={route} waypoints={waypoints} osm={osm} youPoint={youPoint} /> : <Panorama route={route} waypoints={waypoints} osm={osm} />}
    </div>
  </div>, document.body);
}

function Terrain3D({ route, waypoints, osm, youPoint }) {
  const box = useRef(null);
  const mapRef = useRef(null);
  const flyRef = useRef(0);
  const [base, setBase] = useState('satellite');
  const [exag, setExag] = useState(1.5);
  const [status, setStatus] = useState('Loading 3D terrain…');
  const line = useMemo(() => (route?.geometry?.coordinates || []).map(c => [c[0], c[1]]), [route?.id, route?.geometryRefined?.builtAt]);
  useEffect(() => {
    let map, cancelled = false;
    (async () => {
      const mod = await import('maplibre-gl');
      const maplibregl = mod.default?.Map ? mod.default : mod;
      if (import.meta.env.PROD) maplibregl.setWorkerUrl?.(new URL(maplibreWorkerUrl, window.location.href).href);
      await import('maplibre-gl/dist/maplibre-gl.css');
      if (cancelled || !box.current) return;
      const lons = line.map(c => c[0]), lats = line.map(c => c[1]);
      const center = line.length ? [(Math.min(...lons) + Math.max(...lons)) / 2, (Math.min(...lats) + Math.max(...lats)) / 2] : [-70.2, 44.1];
      const t0 = performance.now();
      maplibregl.prewarm?.();
      const create = () => new maplibregl.Map({
        container: box.current,
        attributionControl: { compact: true },
        style: {
          version: 8,
          sources: {
            satellite: { type: 'raster', tiles: [AREA_LAYERS.satellite.url], tileSize: 256, maxzoom: 16, attribution: 'USGS The National Map' },
            topo: { type: 'raster', tiles: [AREA_LAYERS.topo.url], tileSize: 256, maxzoom: 16, attribution: 'USGS The National Map' },
            dem: { type: 'raster-dem', tiles: [TERRARIUM_URL], tileSize: 256, maxzoom: 13, encoding: 'terrarium', attribution: 'Terrain: AWS open data' },
            hill: { type: 'raster-dem', tiles: [TERRARIUM_URL], tileSize: 256, maxzoom: 13, encoding: 'terrarium' }
          },
          layers: [
            { id: 'bg', type: 'background', paint: { 'background-color': '#1f3325' } },
            { id: 'satellite', type: 'raster', source: 'satellite', layout: { visibility: 'visible' } },
            { id: 'topo', type: 'raster', source: 'topo', layout: { visibility: 'none' } },
            { id: 'hillshade', type: 'hillshade', source: 'hill', paint: { 'hillshade-exaggeration': 0.35, 'hillshade-shadow-color': '#1d2a20' } }
          ],
          terrain: { source: 'dem', exaggeration: exag },
          sky: { 'sky-color': '#9cc3d6', 'horizon-color': '#e6dcc3', 'fog-color': '#e6dcc3', 'sky-horizon-blend': 0.5, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.3 }
        },
        center, zoom: 13, pitch: 62, bearing: -20, maxPitch: 80
      });
      map = create();
      // The first map on a page can stall while MapLibre's worker starts; retry once if it does.
      const loaded = await new Promise(res => { const t = setTimeout(() => res(false), 7000); map.once('load', () => { clearTimeout(t); res(true); }); });
      if (cancelled) { map.remove(); return; }
      if (!loaded) console.info(`3D map stalled, retrying after ${Math.round(performance.now() - t0)} ms`);
      if (!loaded) { map.remove(); map = create(); }
      mapRef.current = map;
      if (import.meta.env.DEV) window.__mappi3Map = map;
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
      const onLoad = () => {
        if (osm?.ways?.length) {
          map.addSource('trails', { type: 'geojson', data: { type: 'FeatureCollection', features: osm.ways.map(w => ({ type: 'Feature', properties: { name: w.name }, geometry: { type: 'LineString', coordinates: w.line } })) } });
          map.addLayer({ id: 'trails', type: 'line', source: 'trails', paint: { 'line-color': '#f3e7c4', 'line-width': 1.6, 'line-dasharray': [2, 2], 'line-opacity': 0.8 } });
        }
        if (line.length > 1) {
          map.addSource('route', { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: line } } });
          map.addLayer({ id: 'route-casing', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#1d2a20', 'line-width': 8 } });
          map.addLayer({ id: 'route', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#d9a441', 'line-width': 4.5 } });
          const b = line.reduce((acc, c) => [[Math.min(acc[0][0], c[0]), Math.min(acc[0][1], c[1])], [Math.max(acc[1][0], c[0]), Math.max(acc[1][1], c[1])]], [[180, 90], [-180, -90]]);
          map.fitBounds(b, { padding: 60, pitch: 62, bearing: -20, duration: 0 });
        }
        waypoints.filter(w => Number.isFinite(w.lat)).forEach(w => {
          const el = document.createElement('div');
          el.className = 'tv-pin';
          const label = document.createElement('span');
          label.textContent = String(w.name || '').replace(route?.name || '', '').trim() || w.name || '';
          const pin = document.createElement('div');
          pin.innerHTML = markerHtml({ kind: markerKind(w, route?.name), mile: w.mile, custom: Boolean(w.custom), label: w.name });
          el.append(label, pin.firstChild);
          new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([w.lon, w.lat]).addTo(map);
        });
        if (youPoint && Number.isFinite(youPoint.lat)) { const el = document.createElement('div'); el.className = 'tv-you'; new maplibregl.Marker({ element: el }).setLngLat([youPoint.lon, youPoint.lat]).addTo(map); }
        setStatus('');
      };
      if (map.loaded() || map.isStyleLoaded()) onLoad(); else map.once('load', onLoad);
      map.on('error', (e) => { console.warn('MapLibre', e?.error?.message || e); setStatus(navigator.onLine ? `Some map data did not load (${String(e?.error?.message || 'unknown').slice(0, 80)}).` : 'Offline: showing the parts of this area that are saved.'); });
    })().catch(e => { if (!cancelled) setStatus(`3D view could not start: ${e.message}. It needs WebGL, which some older phones turn off.`); });
    return () => { cancelled = true; cancelAnimationFrame(flyRef.current); map?.remove(); mapRef.current = null; };
  }, [route?.id, route?.geometryRefined?.builtAt]);
  useEffect(() => { const m = mapRef.current; if (!m || !m.isStyleLoaded()) return; m.setLayoutProperty('satellite', 'visibility', base === 'satellite' ? 'visible' : 'none'); m.setLayoutProperty('topo', 'visibility', base === 'topo' ? 'visible' : 'none'); }, [base]);
  useEffect(() => { const m = mapRef.current; if (m?.isStyleLoaded()) m.setTerrain({ source: 'dem', exaggeration: exag }); }, [exag]);
  const fly = () => {
    const m = mapRef.current; if (!m || line.length < 2) return;
    cancelAnimationFrame(flyRef.current);
    const legs = []; let total = 0;
    for (let i = 1; i < line.length; i += 1) { const d = milesBetween({ lat: line[i - 1][1], lon: line[i - 1][0] }, { lat: line[i][1], lon: line[i][0] }); legs.push(d); total += d; }
    const durationMs = Math.min(60000, Math.max(15000, total * 9000));
    const t0 = performance.now();
    let heading = bearingDeg({ lat: line[0][1], lon: line[0][0] }, { lat: line[1][1], lon: line[1][0] });
    const step = (now) => {
      const f = Math.min(1, (now - t0) / durationMs);
      let target = f * total, i = 0;
      while (i < legs.length - 1 && target > legs[i]) { target -= legs[i]; i += 1; }
      const t = legs[i] ? target / legs[i] : 0;
      const a = line[i], b = line[i + 1];
      const want = bearingDeg({ lat: a[1], lon: a[0] }, { lat: b[1], lon: b[0] });
      const delta = ((want - heading + 540) % 360) - 180;
      heading = (heading + delta * 0.04 + 360) % 360;
      m.jumpTo({ center: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], bearing: heading, pitch: 68, zoom: 15.2 });
      if (f < 1) flyRef.current = requestAnimationFrame(step);
    };
    flyRef.current = requestAnimationFrame(step);
  };
  const summit = () => {
    const m = mapRef.current; if (!m) return;
    const hi = waypoints.filter(w => Number.isFinite(w.lat)).find(w => ['view'].includes(waypointKind(w, route?.name))) || waypoints.filter(w => Number.isFinite(w.lat)).at(-1);
    if (hi) m.flyTo({ center: [hi.lon, hi.lat], zoom: 14.2, pitch: 72, bearing: (m.getBearing() + 120) % 360, duration: 3500 });
  };
  return <div className="tv-body">
    <div ref={box} className="tv-map" />
    {status && <div className="tv-status">{status}</div>}
    <div className="tv-controls">
      <div className="tv-seg"><button type="button" className={base === 'satellite' ? 'on' : ''} onClick={() => setBase('satellite')}>Satellite</button><button type="button" className={base === 'topo' ? 'on' : ''} onClick={() => setBase('topo')}>Topo</button></div>
      <label className="tv-exag">Relief <input type="range" min="1" max="3" step="0.25" value={exag} onChange={e => setExag(Number(e.target.value))} /> {exag}×</label>
      <button type="button" className="primary" onClick={fly}>Fly the trail</button>
      <button type="button" className="ghost" onClick={summit}>Summit</button>
      <button type="button" className="ghost" onClick={() => { cancelAnimationFrame(flyRef.current); }}>Stop</button>
    </div>
  </div>;
}

// ---------- View from the top ----------
const R_M = 6371000;
async function computePanorama(pt, onProgress) {
  const eyeM = (await elevationAt(pt.lat, pt.lon, 12)) ?? null;
  if (eyeM === null) return null;
  const h0 = eyeM + 2;
  const bands = [[], [], []]; // near <5 km, mid <15 km, far <40 km
  const dists = []; for (let d = 150; d <= 40000; d *= 1.07) dists.push(d);
  for (let az = 0; az < 360; az += 1) {
    const best = [-90, -90, -90];
    for (const d of dists) {
      const p = destination(pt, az, d / 1609.34);
      const h = await elevationAt(p.lat, p.lon, d < 6000 ? 12 : 10);
      if (h === null) continue;
      const drop = (d * d) / (2 * R_M) * 0.87;
      const ang = (Math.atan2(h - h0 - drop, d) * 180) / Math.PI;
      const band = d < 5000 ? 0 : d < 15000 ? 1 : 2;
      for (let b = band; b < 3; b += 1) best[b] = Math.max(best[b], ang);
    }
    bands[0].push(best[0]); bands[1].push(best[1]); bands[2].push(best[2]);
    if (az % 12 === 11) { onProgress(Math.round(((az + 1) / 360) * 100)); await new Promise(r => setTimeout(r, 0)); }
  }
  return { h0, bands };
}

function Panorama({ route, waypoints, osm }) {
  const profile = useRouteProfile(route);
  const candidates = useMemo(() => {
    const list = waypoints.filter(w => Number.isFinite(w.lat)).map(w => ({ name: String(w.name || '').replace(route?.name || '', '').trim() || w.name, lat: w.lat, lon: w.lon, kind: waypointKind(w, route?.name) }));
    const hi = profile?.source === 'terrain' ? profile.points.reduce((a, p) => (p.ft > a.ft ? p : a), profile.points[0]) : null;
    if (hi) list.unshift({ name: `High point on the trail (${Math.round(hi.ft).toLocaleString()} ft)`, lat: hi.lat, lon: hi.lon, kind: 'view' });
    return list.sort((a, b) => (a.kind === 'view' ? -1 : 0) - (b.kind === 'view' ? -1 : 0));
  }, [route?.id, profile?.source]);
  const [idx, setIdx] = useState(0);
  const [data, setData] = useState(null);
  const [pct, setPct] = useState(0);
  const [err, setErr] = useState('');
  const pt = candidates[idx];
  useEffect(() => {
    if (!pt) return undefined;
    let off = false; setData(null); setErr(''); setPct(0);
    computePanorama(pt, p => !off && setPct(p)).then(r => { if (off) return; if (!r) setErr('Terrain for this spot is not available. Save the area offline while online, then try again.'); else setData(r); });
    return () => { off = true; };
  }, [pt?.lat, pt?.lon]);
  const peaks = useMemo(() => {
    if (!data || !pt) return [];
    const pool = [...(osm?.points || []).filter(p => p.kind === 'peak' && p.name)];
    return pool.map(p => {
      const dM = milesBetween(pt, p) * 1609.34;
      if (dM < 300 || dM > 40000) return null;
      const az = Math.round(bearingDeg(pt, p)) % 360;
      const h = Number.isFinite(p.ele) ? p.ele : null;
      return { ...p, dM, az, h };
    }).filter(Boolean);
  }, [data, osm, pt?.lat]);
  const [visiblePeaks, setVisiblePeaks] = useState([]);
  const [peakCount, setPeakCount] = useState(0);
  useEffect(() => {
    let off = false;
    (async () => {
      if (!data) { setVisiblePeaks([]); return; }
      const out = [];
      for (const p of peaks) {
        const h = p.h ?? (await elevationAt(p.lat, p.lon, 10));
        if (h === null) continue;
        const drop = (p.dM * p.dM) / (2 * R_M) * 0.87;
        const ang = (Math.atan2(h - data.h0 - drop, p.dM) * 180) / Math.PI;
        if (ang >= data.bands[2][p.az] - 0.25) out.push({ ...p, ang, h });
      }
      // Keep the most prominent peaks and skip any whose label would crowd a bigger one nearby.
      const ranked = out.map(p => ({ ...p, prom: p.ang - (data.bands[2][p.az] - 2) + p.h / 3000 })).sort((a, b) => b.prom - a.prom);
      const kept = [];
      ranked.forEach(p => { if (kept.length < 20 && kept.every(k => Math.min(Math.abs(k.az - p.az), 360 - Math.abs(k.az - p.az)) >= 9)) kept.push(p); });
      if (!off) { setVisiblePeaks(kept.sort((a, b) => a.az - b.az)); setPeakCount(out.length); }
    })();
    return () => { off = true; };
  }, [data, peaks]);
  const copy = async () => { try { await navigator.clipboard.writeText(`${pt.lat.toFixed(5)}, ${pt.lon.toFixed(5)}`); } catch { /* shown on screen anyway */ } };
  if (!pt) return <div className="tv-body pano-empty"><p>This trail has no mapped points to look out from.</p></div>;
  const W = 1800, H = 320, pxDeg = W / 360;
  const all = data ? [...data.bands[2]] : [0];
  const maxA = Math.max(2, ...all) + 1.5, minA = Math.min(-3, ...all.map(a => (a < -20 ? -20 : a))) - 0.5;
  const Y = a => H - 34 - ((Math.max(minA, a) - minA) / (maxA - minA)) * (H - 70);
  const ridge = arr => `M0 ${H} ` + arr.map((a, i) => `L${(i * pxDeg).toFixed(1)} ${Y(a).toFixed(1)}`).join(' ') + ` L${W} ${Y(arr[0]).toFixed(1)} L${W} ${H} Z`;
  return <div className="tv-body pano">
    <div className="pano-bar">
      <label>Look out from <select value={idx} onChange={e => setIdx(Number(e.target.value))}>{candidates.map((c, i) => <option key={i} value={i}>{c.name}</option>)}</select></label>
      {data && <span className="muted">Eye height {Math.round(data.h0 * 3.28084).toLocaleString()} ft · looking 40 km (25 mi) out · {peakCount} named peak{peakCount === 1 ? '' : 's'} in view, the {visiblePeaks.length} most prominent labelled</span>}
    </div>
    {!data && !err && <div className="pano-wait"><div className="oa-progress"><div><i style={{ width: `${pct}%` }} /></div><span>Working out the skyline… {pct}%</span></div></div>}
    {err && <p className="pano-wait">{err}</p>}
    {data && <div className="pano-scroll"><svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Skyline panorama">
      <defs><linearGradient id="panoSky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8fb7cc" /><stop offset="1" stopColor="#e9dfc6" /></linearGradient></defs>
      <rect width={W} height={H} fill="url(#panoSky)" />
      <path d={ridge(data.bands[2])} fill="#7f98a0" />
      <path d={ridge(data.bands[1])} fill="#56705a" />
      <path d={ridge(data.bands[0])} fill="#2f4c37" />
      {visiblePeaks.map((p, i) => { const x = p.az * pxDeg, y = Y(p.ang); const up = 16 + (i % 3) * 30; return <g key={p.id} className="pano-peak"><line x1={x} x2={x} y1={y} y2={y - up} /><text x={x} y={y - up - 4} textAnchor="middle">{p.name}</text><text x={x} y={y - up + 10} textAnchor="middle" className="pano-sub">{(p.dM / 1609.34).toFixed(0)} mi</text><title>{`${p.name}: ${(p.dM / 1609.34).toFixed(1)} mi away${p.h ? `, ${Math.round(p.h * 3.28084).toLocaleString()} ft` : ''}`}</title></g>; })}
      {['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'].map((c, i) => <text key={c} x={i * 45 * pxDeg + 4} y={H - 10} className="pano-dir">{c}</text>)}
      {Array.from({ length: 36 }, (_, i) => <line key={i} x1={i * 10 * pxDeg} x2={i * 10 * pxDeg} y1={H - 30} y2={H - 24} className="pano-tick" />)}
    </svg></div>}
    <div className="pano-foot">
      <span>Skyline worked out from terrain data, allowing for the curve of the earth. Peak names from OpenStreetMap (saved with the offline area).</span>
      <span className="pano-hwt">Full panorama with every named feature: open <a href="https://www.heywhatsthat.com/" target="_blank" rel="noreferrer">HeyWhatsThat</a> (needs internet) and paste <code>{pt.lat.toFixed(5)}, {pt.lon.toFixed(5)}</code> <button type="button" className="ghost small" onClick={copy}>Copy</button></span>
    </div>
  </div>;
}
