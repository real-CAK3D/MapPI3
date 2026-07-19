import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const defaultCenter = [44.1004, -70.2148];

function routeToPoints(route) {
  return route?.geometry?.coordinates?.map(([lon, lat]) => [lat, lon]) || [];
}

function iconFor(point) {
  return L.divIcon({
    className: `mappi3-waypoint-icon ${point.custom ? 'custom' : 'stock'}`,
    html: `<span>${point.icon || (point.custom ? '✚' : '•')}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15]
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

export default function LiveLeafletMap({ trace = [], center = defaultCenter, active = false, route = null, waypoints = [], onMapClick = null, onWaypointMove = null }) {
  const [tileStatus, setTileStatus] = useState('loading map tiles');
  const formatCoord = (point) => Array.isArray(point) ? `${Number(point[0]).toFixed(5)}, ${Number(point[1]).toFixed(5)}` : 'GPS pending';
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const layerRef = useRef({ marker: null, line: null, route: null, segments: [], waypoints: [] });
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
    const localTiles = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 18, attribution: 'MapPI3 offline tiles', errorTileUrl: '' });
    const osmTiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors', crossOrigin: true, detectRetina: true });
    let activeLayer = null;
    let goodTiles = 0;
    let switched = false;
    const useLayer = (layer, label) => {
      if (activeLayer && activeLayer !== layer) map.removeLayer(activeLayer);
      activeLayer = layer;
      if (!map.hasLayer(layer)) layer.addTo(map);
      setTileStatus(label);
    };
    const markGood = (label) => { goodTiles += 1; if (goodTiles >= 1) setTileStatus(label); };
    localTiles.on('tileload', () => markGood('offline Pi map tiles'));
    osmTiles.on('tileload', () => markGood('live OpenStreetMap tiles'));
    localTiles.on('tileerror', () => {
      if (!switched && isPiLocal) { switched = true; useLayer(osmTiles, 'checking live OpenStreetMap tiles'); }
      else if (!goodTiles) setTileStatus('offline topo fallback · route/POIs still usable');
    });
    osmTiles.on('tileerror', () => { if (!goodTiles) setTileStatus(isPiLocal ? 'GPS live · tile pack/internet unavailable · route/POIs still usable' : 'GPS live · offline topo fallback · route/POIs still usable'); });
    useLayer(isPiLocal ? localTiles : osmTiles, isPiLocal ? 'checking offline Pi tiles' : 'checking live OpenStreetMap tiles');
    setTimeout(() => { if (!goodTiles) setTileStatus(isPiLocal ? 'GPS live · tile pack/internet unavailable · route/POIs still usable' : 'GPS live · offline topo fallback · route/POIs still usable'); }, 4500);
  }, [center]);

  useEffect(() => {
    if (!mapRef.current) return undefined;
    const handler = (event) => onMapClick && onMapClick({ lat: event.latlng.lat, lon: event.latlng.lng });
    mapRef.current.on('click', handler);
    return () => mapRef.current && mapRef.current.off('click', handler);
  }, [onMapClick]);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const latest = points[points.length - 1] || center;
    if (layerRef.current.line) layerRef.current.line.remove();
    if (layerRef.current.marker) layerRef.current.marker.remove();
    if (layerRef.current.route) layerRef.current.route.remove();
    layerRef.current.segments.forEach(layer => layer.remove());
    layerRef.current.waypoints.forEach(layer => layer.remove());
    layerRef.current.segments = [];
    layerRef.current.waypoints = [];

    if (routePoints.length > 1) {
      const segments = route?.segments || [];
      if (segments.length) {
        segments.forEach(segment => {
          const segmentPoints = segmentSlice(routePoints, routeMiles, segment);
          if (segmentPoints.length > 1) {
            const layer = L.polyline(segmentPoints, { color: segment.color || route?.color || '#9ce36c', weight: 6, opacity: 0.86 }).bindTooltip(`${segment.name || 'Route segment'} · ${segment.startMile ?? 0}-${segment.endMile ?? ''} mi`).addTo(map);
            layerRef.current.segments.push(layer);
          }
        });
      } else {
        layerRef.current.route = L.polyline(routePoints, { color: route?.color || '#9ce36c', weight: 6, opacity: 0.78 }).addTo(map);
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
    else layerRef.current.line = L.polyline(points, { color: '#4bd2ff', weight: 4, opacity: 0.4 }).addTo(map);
    layerRef.current.marker = L.circleMarker(latest, {
      radius: 9,
      color: '#dff1ff',
      weight: 3,
      fillColor: active ? '#58a8ff' : (route?.color || '#9ce36c'),
      fillOpacity: 0.9
    }).bindTooltip(`Live GPS / map point · ${formatCoord(latest)}`, { direction: 'top' }).bindPopup(`<strong>Live GPS / map point</strong><br>${formatCoord(latest)}<br>${active ? 'tracking live movement' : 'selected route/start point'}`).addTo(map);

    const waypointPoints = (waypoints || []).filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lon)).map(point => [point.lat, point.lon]);
    const boundsPoints = [...routePoints, ...tracePoints, ...waypointPoints];
    if (boundsPoints.length > 1) map.fitBounds(L.latLngBounds(boundsPoints), { padding: [24, 24], maxZoom: 17 });
    else map.setView(latest, 15);
  }, [points, tracePoints, routePoints, routeMiles, waypoints, center, active, onWaypointMove, route]);

  const latestPoint = points[points.length - 1] || center;
  return <div className={`leaflet-shell ${onMapClick ? 'draw-active' : ''}`} data-tile-status={tileStatus}><div className="map-fallback-label">{tileStatus} · GPS {formatCoord(latestPoint)}</div>{onMapClick && <div className="draw-map-hint">tap map to place point</div>}<div ref={containerRef} className="leaflet-map" /></div>;
}
