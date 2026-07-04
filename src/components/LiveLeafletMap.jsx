import { useEffect, useMemo, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const defaultCenter = [44.1004, -70.2148];

export default function LiveLeafletMap({ trace = [], center = defaultCenter, active = false }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const layerRef = useRef({ marker: null, line: null });

  const points = useMemo(() => {
    if (!trace.length) return [center];
    return trace.map(point => [point.lat, point.lon]);
  }, [trace, center]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = L.map(containerRef.current, { zoomControl: true, attributionControl: true }).setView(center, 15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(mapRef.current);
  }, [center]);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const latest = points[points.length - 1] || center;
    if (layerRef.current.line) layerRef.current.line.remove();
    if (layerRef.current.marker) layerRef.current.marker.remove();
    layerRef.current.line = L.polyline(points, { color: '#4bd2ff', weight: 6, opacity: 0.9 }).addTo(map);
    layerRef.current.marker = L.circleMarker(latest, {
      radius: 9,
      color: '#dff1ff',
      weight: 3,
      fillColor: active ? '#58a8ff' : '#9ce36c',
      fillOpacity: 0.9
    }).addTo(map);
    if (points.length > 1) map.fitBounds(layerRef.current.line.getBounds(), { padding: [24, 24], maxZoom: 17 });
    else map.setView(latest, 15);
  }, [points, center, active]);

  return <div className="leaflet-shell"><div ref={containerRef} className="leaflet-map" /></div>;
}
