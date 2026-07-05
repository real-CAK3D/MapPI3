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
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });
}

export default function LiveLeafletMap({ trace = [], center = defaultCenter, active = false, route = null, waypoints = [], onMapClick = null, onWaypointMove = null }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const layerRef = useRef({ marker: null, line: null, route: null, waypoints: [] });
  const routePoints = useMemo(() => routeToPoints(route), [route]);

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
    layerRef.current.waypoints.forEach(layer => layer.remove());
    layerRef.current.waypoints = [];

    if (routePoints.length > 1) {
      layerRef.current.route = L.polyline(routePoints, { color: '#9ce36c', weight: 5, opacity: 0.72, dashArray: '10 8' }).addTo(map);
      (waypoints || []).forEach(point => {
        const marker = L.marker([point.lat, point.lon], { icon: iconFor(point), draggable: Boolean(point.custom && onWaypointMove) })
          .bindTooltip(`${point.name} · ${point.mile} mi${point.custom ? ' · custom' : ''}`, { direction: 'top' })
          .addTo(map);
        if (point.custom && onWaypointMove) {
          marker.on('dragend', event => {
            const latlng = event.target.getLatLng();
            onWaypointMove(point.id, { lat: latlng.lat, lon: latlng.lng });
          });
        }
        layerRef.current.waypoints.push(marker);
      });
    }

    if (tracePoints.length > 1) layerRef.current.line = L.polyline(tracePoints, { color: '#4bd2ff', weight: 6, opacity: 0.9 }).addTo(map);
    else layerRef.current.line = L.polyline(points, { color: '#4bd2ff', weight: 4, opacity: 0.4 }).addTo(map);
    layerRef.current.marker = L.circleMarker(latest, {
      radius: 9,
      color: '#dff1ff',
      weight: 3,
      fillColor: active ? '#58a8ff' : '#9ce36c',
      fillOpacity: 0.9
    }).addTo(map);

    const boundsPoints = [...routePoints, ...tracePoints];
    if (boundsPoints.length > 1) map.fitBounds(L.latLngBounds(boundsPoints), { padding: [24, 24], maxZoom: 17 });
    else map.setView(latest, 15);
  }, [points, tracePoints, routePoints, waypoints, center, active, onWaypointMove]);

  return <div className="leaflet-shell"><div ref={containerRef} className="leaflet-map" /></div>;
}
