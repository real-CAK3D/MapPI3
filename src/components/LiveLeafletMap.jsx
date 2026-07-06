import { useEffect, useMemo, useRef } from 'react';
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
    mapRef.current = L.map(containerRef.current, { zoomControl: true, attributionControl: true }).setView(center, 15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(mapRef.current);
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
      const marker = L.marker([point.lat, point.lon], { icon: iconFor(point), draggable: Boolean(point.custom && onWaypointMove) })
        .bindTooltip(`${point.name} · ${point.type || 'Waypoint'} · ${point.mile ?? '—'} mi${point.custom ? ' · custom' : ''}`, { direction: 'top' })
        .addTo(map);
      marker.bindPopup(`<strong>${point.name}</strong><br>${point.type || 'Waypoint'} · ${point.mile ?? '—'} mi${point.notes ? `<br>${point.notes}` : ''}`);
      if (point.custom && onWaypointMove) {
        marker.on('dragend', event => {
          const latlng = event.target.getLatLng();
          onWaypointMove(point.id, { lat: latlng.lat, lon: latlng.lng });
        });
      }
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
    }).addTo(map);

    const waypointPoints = (waypoints || []).filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lon)).map(point => [point.lat, point.lon]);
    const boundsPoints = [...routePoints, ...tracePoints, ...waypointPoints];
    if (boundsPoints.length > 1) map.fitBounds(L.latLngBounds(boundsPoints), { padding: [24, 24], maxZoom: 17 });
    else map.setView(latest, 15);
  }, [points, tracePoints, routePoints, routeMiles, waypoints, center, active, onWaypointMove, route]);

  return <div className="leaflet-shell"><div ref={containerRef} className="leaflet-map" /></div>;
}
