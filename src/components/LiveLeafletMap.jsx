import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const defaultCenter = [44.1004, -70.2148];

function routeToPoints(route) {
  return route?.geometry?.coordinates?.map(([lon, lat]) => [lat, lon]) || [];
}

function iconFor(point) {
  const size = Math.max(24, Math.min(54, Number(point.size || 30)));
  return L.divIcon({
    className: `mappi3-waypoint-icon ${point.custom ? 'custom' : 'stock'} ${point.markerClass || ''}`,
    html: `<span>${point.icon || (point.custom ? '✚' : '•')}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2]
  });
}

function segmentSlice(routePoints, routeMiles, segment) {
  if (!routePoints.length || !routeMiles.length || !segment) return routePoints;
  const start = Number(segment.startMile || 0);
  const end = Number(segment.endMile || routeMiles.at(-1) || start);
  const kept = routePoints.filter((_, index) => routeMiles[index] >= start && routeMiles[index] <= end);
  if (kept.length >= 2) return kept;
  const startIndex = routeMiles.findIndex(value => value >= start);
  const endIndex = routeMiles.findIndex(value => value >= end);
  return routePoints.slice(Math.max(0, startIndex - 1), Math.max(startIndex + 1, endIndex + 1));
}

const onlineTileModes = {
  street: {
    label: 'Street',
    status: 'live OpenStreetMap street tiles',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors', crossOrigin: true, detectRetina: true }
  },
  terrain: {
    label: 'Terrain',
    status: 'live OpenTopoMap terrain tiles',
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    options: { maxZoom: 17, attribution: 'Map data &copy; OpenStreetMap contributors, SRTM | OpenTopoMap', crossOrigin: true, detectRetina: true }
  },
  topo: {
    label: 'Topo',
    status: 'USGS topo map · works offline when the area is saved',
    url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
    options: { maxZoom: 19, maxNativeZoom: 16, attribution: 'USGS The National Map', crossOrigin: true }
  },
  // Satellite and hybrid use USGS imagery (public domain) so a saved area shows them offline.
  satellite: {
    label: 'Satellite',
    status: 'USGS satellite imagery · works offline when the area is saved',
    url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}',
    options: { maxZoom: 19, maxNativeZoom: 16, attribution: 'USGS The National Map: imagery', crossOrigin: true }
  },
  hybrid: {
    label: 'Hybrid',
    status: 'USGS imagery with roads and names',
    url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}',
    options: { maxZoom: 19, maxNativeZoom: 16, attribution: 'USGS The National Map', crossOrigin: true }
  }
};

export default function LiveLeafletMap({ trace = [], center = defaultCenter, active = false, route = null, waypoints = [], onMapClick = null, onWaypointMove = null, onViewChange = null, showCenterMarker = true, tilePath = '/tiles/{z}/{x}/{y}.png', tileMaxZoom = 18, tileLabel = 'offline Pi map tiles', trailLines = null, accuracyM = null }) {
  const [tileStatus, setTileStatus] = useState('loading map tiles');
  const [mapMode, setMapMode] = useState(() => localStorage.getItem('mappi3.mapMode') || 'street');
  const [pitch3d, setPitch3d] = useState(() => localStorage.getItem('mappi3.mapPitch3d') === 'true');
  const formatCoord = (point) => Array.isArray(point) ? `${Number(point[0]).toFixed(5)}, ${Number(point[1]).toFixed(5)}` : 'GPS pending';
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const tileRef = useRef({ activeLayer: null, overlayLayer: null, goodTiles: 0, switched: false, localTiles: null, modes: {} });
  const layerRef = useRef({ marker: null, line: null, route: null, shadow: null, grade: null, segments: [], waypoints: [], trails: null, accuracy: null });
  const routePoints = useMemo(() => routeToPoints(route), [route]);
  const routeMiles = useMemo(() => {
    const total = Number(route?.distanceMiles || route?.miles || 0);
    const count = Math.max(1, routePoints.length - 1);
    return routePoints.map((_, index) => total * (index / count));
  }, [routePoints, route]);

  const tracePoints = useMemo(() => {
    if (!trace.length) return [];
    return trace.map(point => [point.lat, point.lon]);
  }, [trace]);

  const points = tracePoints.length ? tracePoints : (routePoints.length ? routePoints : [center]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = L.map(containerRef.current, { zoomControl: true, attributionControl: true, preferCanvas: true }).setView(center, 15);
    const map = mapRef.current;
    const host = typeof window !== 'undefined' ? window.location.hostname : '';
    const isPiLocal = /^(mappi3\.local|10\.42\.0\.1|localhost|127\.0\.0\.1)$/i.test(host);
    const localTiles = L.tileLayer(tilePath, { maxZoom: tileMaxZoom, attribution: tileLabel, errorTileUrl: '' });
    const modes = Object.fromEntries(Object.entries(onlineTileModes).map(([key, mode]) => [key, L.tileLayer(mode.url, mode.options)]));
    tileRef.current = { activeLayer: null, overlayLayer: null, goodTiles: 0, switched: false, localTiles, modes, isPiLocal };
    const useLayer = (layer, label) => {
      if (tileRef.current.activeLayer && tileRef.current.activeLayer !== layer) map.removeLayer(tileRef.current.activeLayer);
      tileRef.current.activeLayer = layer;
      if (!map.hasLayer(layer)) layer.addTo(map);
      setTileStatus(label);
    };
    const markGood = (label) => { tileRef.current.goodTiles += 1; if (tileRef.current.goodTiles >= 1) setTileStatus(label); };
    localTiles.on('tileload', () => markGood('offline Pi map tiles'));
    Object.entries(modes).forEach(([key, layer]) => layer.on('tileload', () => markGood(onlineTileModes[key]?.status || 'live map tiles')));
    localTiles.on('tileerror', () => {
      if (!tileRef.current.switched && isPiLocal) { tileRef.current.switched = true; useLayer(modes[mapMode] || modes.street, onlineTileModes[mapMode]?.status || 'checking live map tiles'); }
      else if (!tileRef.current.goodTiles) setTileStatus('offline topo fallback · route/POIs still usable');
    });
    Object.entries(modes).forEach(([key, layer]) => layer.on('tileerror', () => { if (!tileRef.current.goodTiles) setTileStatus(isPiLocal ? 'GPS live · tile pack/internet unavailable · route/POIs still usable' : `${onlineTileModes[key]?.label || 'Map'} unavailable · offline topo fallback · route/POIs still usable`); }));
    useLayer(isPiLocal ? localTiles : (modes[mapMode] || modes.street), isPiLocal ? 'checking offline Pi tiles' : (onlineTileModes[mapMode]?.status || 'checking live map tiles'));
    setTimeout(() => { if (!tileRef.current.goodTiles) setTileStatus(isPiLocal ? 'GPS live · tile pack/internet unavailable · route/POIs still usable' : 'GPS live · offline topo fallback · route/POIs still usable'); }, 4500);
  }, [center, tilePath, tileMaxZoom, tileLabel]);

  useEffect(() => {
    if (!mapRef.current || !tileRef.current.modes) return;
    localStorage.setItem('mappi3.mapMode', mapMode);
    localStorage.setItem('mappi3.mapPitch3d', String(pitch3d));
    const map = mapRef.current;
    const { modes, isPiLocal, localTiles } = tileRef.current;
    const nextLayer = isPiLocal && mapMode === 'street' ? localTiles : (modes[mapMode] || modes.street);
    if (tileRef.current.activeLayer && tileRef.current.activeLayer !== nextLayer) map.removeLayer(tileRef.current.activeLayer);
    tileRef.current.activeLayer = nextLayer;
    if (nextLayer && !map.hasLayer(nextLayer)) nextLayer.addTo(map);
    if (tileRef.current.overlayLayer) { map.removeLayer(tileRef.current.overlayLayer); tileRef.current.overlayLayer = null; }

    setTileStatus(isPiLocal && mapMode === 'street' ? 'offline Pi map tiles' : (onlineTileModes[mapMode]?.status || 'live map tiles'));
  }, [mapMode, pitch3d]);

  useEffect(() => {
    if (!mapRef.current) return undefined;
    const clickHandler = (event) => onMapClick && onMapClick({ lat: event.latlng.lat, lon: event.latlng.lng });
    const viewHandler = () => {
      if (!onViewChange || !mapRef.current) return;
      const c = mapRef.current.getCenter();
      onViewChange({ lat: c.lat, lon: c.lng, zoom: mapRef.current.getZoom() });
    };
    mapRef.current.on('click', clickHandler);
    mapRef.current.on('moveend zoomend', viewHandler);
    viewHandler();
    return () => {
      if (!mapRef.current) return;
      mapRef.current.off('click', clickHandler);
      mapRef.current.off('moveend zoomend', viewHandler);
    };
  }, [onMapClick, onViewChange]);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const latest = points[points.length - 1] || center;
    if (layerRef.current.line) layerRef.current.line.remove();
    if (layerRef.current.marker) layerRef.current.marker.remove();
    if (layerRef.current.route) layerRef.current.route.remove();
    if (layerRef.current.shadow) layerRef.current.shadow.remove();
    if (layerRef.current.grade) layerRef.current.grade.remove();
    layerRef.current.segments.forEach(layer => layer.remove());
    layerRef.current.waypoints.forEach(layer => layer.remove());
    layerRef.current.segments = [];
    layerRef.current.waypoints = [];

    if (routePoints.length > 1) {
      layerRef.current.shadow = L.polyline(routePoints, { color: pitch3d ? '#07120b' : '#0d160e', weight: pitch3d ? 14 : 10, opacity: pitch3d ? 0.48 : 0.22, lineCap: 'round', lineJoin: 'round' }).addTo(map);
      const segments = route?.segments || [];
      if (segments.length) {
        segments.forEach(segment => {
          const segmentPoints = segmentSlice(routePoints, routeMiles, segment);
          if (segmentPoints.length > 1) {
            const layer = L.polyline(segmentPoints, { color: segment.color || route?.color || '#9ce36c', weight: pitch3d ? 8 : 6, opacity: 0.9, lineCap: 'round', lineJoin: 'round' }).bindTooltip(`${segment.name || 'Route segment'} · ${segment.startMile ?? 0}-${segment.endMile ?? ''} mi`).addTo(map);
            layerRef.current.segments.push(layer);
          }
        });
      } else {
        layerRef.current.route = L.polyline(routePoints, { color: route?.color || '#9ce36c', weight: pitch3d ? 8 : 6, opacity: 0.86, lineCap: 'round', lineJoin: 'round' }).addTo(map);
      }
      const gain = Number(route?.elevationGainFt || route?.gainFt || 0);
      if (gain || pitch3d) {
        const mid = routePoints[Math.floor(routePoints.length / 2)];
        layerRef.current.grade = L.marker(mid, { icon: L.divIcon({ className: 'mappi3-elevation-badge', html: `<strong>${gain ? gain.toLocaleString() : '3D'}</strong><span>${gain ? 'ft gain' : 'terrain'}</span>`, iconSize: [86, 42], iconAnchor: [43, 21] }), keyboard: false }).addTo(map);
      }
    }

    (waypoints || []).filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lon)).forEach(point => {
      const marker = L.marker([point.lat, point.lon], { icon: iconFor(point), draggable: Boolean((point.custom || point.editable) && onWaypointMove), keyboard: false, autoPan: true })
        .bindTooltip(`${point.name} · ${point.type || 'Waypoint'} · ${point.mile ?? '—'} mi${point.custom || point.editable ? ' · drag to move' : ''}`, { direction: 'top' })
        .addTo(map);
      marker.bindPopup(`<strong>${point.name}</strong><br>${point.type || 'Waypoint'} · ${point.mile ?? '—'} mi${point.notes ? `<br>${point.notes}` : ''}${point.custom || point.editable ? '<br><em>Drag this marker to move it.</em>' : ''}`);
      if ((point.custom || point.editable) && onWaypointMove) {
        marker.on('dragstart', () => map.dragging.disable());
        marker.on('dragend', event => {
          map.dragging.enable();
          const latlng = event.target.getLatLng();
          onWaypointMove(point.id, { lat: latlng.lat, lon: latlng.lng });
        });
      }
      if (point.focused) setTimeout(() => marker.openPopup(), 80);
      layerRef.current.waypoints.push(marker);
    });

    if (tracePoints.length > 1) layerRef.current.line = L.polyline(tracePoints, { color: '#4bd2ff', weight: 6, opacity: 0.9 }).addTo(map);
    else layerRef.current.line = null;
    if (showCenterMarker) {
      layerRef.current.marker = L.circleMarker(latest, {
        radius: 9,
        color: '#dff1ff',
        weight: 3,
        fillColor: active ? '#58a8ff' : (route?.color || '#9ce36c'),
        fillOpacity: 0.9
      }).bindTooltip(`Live GPS / map point · ${formatCoord(latest)}`, { direction: 'top' }).bindPopup(`<strong>Live GPS / map point</strong><br>${formatCoord(latest)}<br>${active ? 'tracking live movement' : 'selected route/start point'}`).addTo(map);
    } else {
      layerRef.current.marker = null;
    }

    const waypointPoints = (waypoints || []).filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lon)).map(point => [point.lat, point.lon]);
    const boundsPoints = [...routePoints, ...tracePoints, ...waypointPoints];
    if (boundsPoints.length > 1) map.fitBounds(L.latLngBounds(boundsPoints), { padding: [24, 24], maxZoom: 17 });
    else map.setView(latest, 15);
  }, [points, tracePoints, routePoints, routeMiles, waypoints, center, active, onWaypointMove, route, showCenterMarker, pitch3d]);

  // Real trail lines from OpenStreetMap for a saved area: thin dashed lines under the route.
  useEffect(() => {
    if (!mapRef.current) return;
    if (layerRef.current.trails) { layerRef.current.trails.remove(); layerRef.current.trails = null; }
    const ways = trailLines?.ways || [];
    const water = trailLines?.water || [];
    if (!ways.length && !water.length) return;
    const group = L.layerGroup();
    water.forEach(w => L.polyline(w.line.map(([lon, lat]) => [lat, lon]), { color: '#3d7f95', weight: w.kind === 'water' ? 1.5 : 2, opacity: 0.7, interactive: false }).addTo(group));
    ways.forEach(w => L.polyline(w.line.map(([lon, lat]) => [lat, lon]), { color: w.kind === 'track' ? '#8a6420' : '#6b3f1d', weight: 2.2, opacity: 0.85, dashArray: '5 4' }).bindTooltip(w.name || (w.kind === 'track' ? 'Track' : 'Trail'), { sticky: true }).addTo(group));
    group.addTo(mapRef.current);
    group.eachLayer(l => l.bringToBack && l.bringToBack());
    layerRef.current.trails = group;
  }, [trailLines]);
  // GPS accuracy circle around the live position.
  useEffect(() => {
    if (!mapRef.current) return;
    if (layerRef.current.accuracy) { layerRef.current.accuracy.remove(); layerRef.current.accuracy = null; }
    const last = points[points.length - 1];
    if (!active || !accuracyM || !last) return;
    layerRef.current.accuracy = L.circle(last, { radius: accuracyM, color: '#58a8ff', weight: 1, fillOpacity: 0.12, interactive: false }).addTo(mapRef.current);
  }, [points, accuracyM, active]);

  const latestPoint = points[points.length - 1] || center;
  const gainLabel = Number(route?.elevationGainFt || route?.gainFt || 0) ? `${Number(route?.elevationGainFt || route?.gainFt || 0).toLocaleString()} ft gain` : 'elevation pending';
  return <div className={`leaflet-shell ${onMapClick ? 'draw-active' : ''} ${pitch3d ? 'pitch-3d' : ''}`} data-tile-status={tileStatus} data-map-mode={mapMode}>
    <div className="map-fallback-label">{tileStatus} · {tracePoints.length ? 'GPS' : routePoints.length ? 'Trail' : 'Map center'} {formatCoord(latestPoint)}</div>
    <div className="map-mode-dock" aria-label="Map view modes">
      {Object.entries(onlineTileModes).map(([id, mode]) => <button key={id} type="button" className={mapMode === id ? 'active' : ''} onClick={() => setMapMode(id)}>{mode.label}</button>)}
      <button type="button" className={pitch3d ? 'active' : ''} onClick={() => setPitch3d(value => !value)}>3D</button>
    </div>
    <div className="elevation-chip"><strong>{gainLabel}</strong><span>{pitch3d ? 'raised route view' : 'tap 3D for relief'}</span></div>
    {onMapClick && <><div className="map-center-crosshair" aria-hidden="true">⌖</div><div className="draw-map-hint">pan/zoom map, tap + or use Add map center</div></>}
    <div ref={containerRef} className="leaflet-map" />
  </div>;
}
