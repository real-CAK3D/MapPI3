import React, { useMemo } from 'react';

const KIND_COLORS = {
  home: '#ffd36a',
  event: '#5ee7ff',
  gps: '#9ce36c',
  trail: '#ff8bd1',
  walk: '#c69cff',
  route: '#ffffff',
  default: '#5ee7ff'
};

function safePoint(point, index) {
  const lat = Number(point?.lat);
  const lon = Number(point?.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return {
    id: point.id || `atlas-${index}`,
    title: point.name || point.label || 'Trail point',
    type: point.type || point.sourceLabel || point.kind || 'MapPI3 point',
    lat,
    lon,
    kind: point.kind || 'default',
    count: Number(point.count || 1),
    size: Math.max(5, Math.min(22, Number(point.size || 12) / 3)),
    notes: point.notes || ''
  };
}

function radians(value) { return (Number(value) || 0) * Math.PI / 180; }
function projectPoint(point, home) {
  const lat = radians(point.lat);
  const lon = radians(point.lon - (home?.lon || 0));
  const yTilt = radians(Math.max(-42, Math.min(42, (home?.lat || 0) / 2)));
  const cosLat = Math.cos(lat);
  const x = cosLat * Math.sin(lon);
  const y = Math.sin(lat) * Math.cos(yTilt) - cosLat * Math.cos(lon) * Math.sin(yTilt);
  const z = Math.sin(lat) * Math.sin(yTilt) + cosLat * Math.cos(lon) * Math.cos(yTilt);
  return { ...point, x: 250 + x * 178, y: 250 - y * 178, visible: z > -0.18, depth: z };
}
function arcPath(a, b) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2 - Math.max(28, Math.abs(a.x - b.x) * 0.18);
  return `M ${a.x.toFixed(1)} ${a.y.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
}

export default function AdventureGlobeAtlas({ points = [] }) {
  const data = useMemo(() => (points || []).map(safePoint).filter(Boolean), [points]);
  const home = data.find(point => point.kind === 'home') || data[0] || { lat: 0, lon: 0, title: 'Home base' };
  const projected = useMemo(() => data.map(point => projectPoint(point, home)).sort((a, b) => a.depth - b.depth), [data, home]);
  const homeProjected = projected.find(point => point.kind === 'home') || projectPoint(home, home);
  const visiblePoints = projected.filter(point => point.visible).slice(-42);
  const links = visiblePoints.filter(point => point.id !== homeProjected.id && point.visible && homeProjected.visible);

  return <div className="adventure-globe-shell" aria-label="Animated globe travel atlas">
    <svg className="adventure-globe-svg" viewBox="0 0 500 500" role="img" aria-labelledby="adventure-globe-title adventure-globe-desc">
      <title id="adventure-globe-title">MapPI3 globe travel atlas</title>
      <desc id="adventure-globe-desc">Animated CodePen-style globe with home base as the largest point and hike or travel locations as glowing markers.</desc>
      <defs>
        <radialGradient id="globeOcean" cx="38%" cy="28%" r="70%"><stop offset="0%" stopColor="#284f79"/><stop offset="48%" stopColor="#101d34"/><stop offset="100%" stopColor="#03060c"/></radialGradient>
        <radialGradient id="globeGlow" cx="50%" cy="50%" r="50%"><stop offset="70%" stopColor="#5ee7ff" stopOpacity="0"/><stop offset="100%" stopColor="#5ee7ff" stopOpacity="0.36"/></radialGradient>
        <filter id="softGlow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <clipPath id="globeClip"><circle cx="250" cy="250" r="190"/></clipPath>
      </defs>
      <circle cx="250" cy="250" r="202" fill="rgba(94,231,255,.08)"/>
      <circle cx="250" cy="250" r="190" fill="url(#globeOcean)" stroke="#7cf4ff" strokeOpacity=".42" strokeWidth="2"/>
      <g clipPath="url(#globeClip)" className="globe-spin-layer">
        <g className="globe-land" opacity=".72">
          <path d="M115 162c30-32 69-42 101-24 17 10 24 27 47 30 25 3 43-13 66-3 20 9 34 33 29 55-7 30-43 25-65 53-21 27-8 54-30 68-20 13-50-4-67-18-30-24-36-58-62-70-22-10-47 1-59-15-14-19 10-55 40-76z" fill="#172d45" stroke="#5ee7ff" strokeOpacity=".18"/>
          <path d="M302 120c33 3 79 24 91 62 8 27-6 47-28 50-26 4-35-18-61-13-22 4-35 24-52 15-17-9-20-42-8-69 11-25 31-48 58-45z" fill="#182c40" stroke="#5ee7ff" strokeOpacity=".16"/>
          <path d="M188 330c23-18 61-21 84-3 22 18 22 53 2 68-23 18-72 10-92-16-14-18-12-35 6-49z" fill="#152a3d" stroke="#5ee7ff" strokeOpacity=".16"/>
        </g>
        <g className="globe-grid" fill="none" stroke="#78efff" strokeOpacity=".18">
          {[0.36,0.58,0.78,0.94].map((scale, i) => <ellipse key={`lat-${i}`} cx="250" cy="250" rx="190" ry={190 * scale} strokeWidth="1"/>)}
          {[0.22,0.45,0.66,0.84].map((scale, i) => <ellipse key={`lon-${i}`} cx="250" cy="250" rx={190 * scale} ry="190" strokeWidth="1"/>)}
          <line x1="60" x2="440" y1="250" y2="250"/><line x1="250" x2="250" y1="60" y2="440"/>
        </g>
        <g className="globe-links" fill="none" strokeLinecap="round">
          {links.map(point => <path key={`link-${point.id}`} d={arcPath(homeProjected, point)} stroke="#8ffcff" strokeOpacity=".48" strokeWidth="1.7" filter="url(#softGlow)"/>)}
        </g>
        <g className="globe-points">
          {visiblePoints.map(point => {
            const isHome = point.kind === 'home';
            const color = KIND_COLORS[point.kind] || KIND_COLORS.default;
            const radius = isHome ? 15 : point.size;
            return <g key={point.id} transform={`translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})`} className={isHome ? 'globe-point home' : 'globe-point'}>
              <title>{`${point.title} — ${point.type}`}</title>
              <circle r={radius + 9} fill={color} opacity={isHome ? '.20' : '.13'} className="globe-point-halo"/>
              <circle r={radius} fill={color} opacity={isHome ? '.96' : '.84'} stroke="#fff" strokeOpacity={isHome ? '.92' : '.44'} strokeWidth={isHome ? '2.2' : '1'} filter="url(#softGlow)"/>
              {isHome ? <text textAnchor="middle" dy="5" fontSize="16" fontWeight="900" fill="#151008">⌂</text> : null}
            </g>;
          })}
        </g>
      </g>
      <circle cx="250" cy="250" r="190" fill="url(#globeGlow)" pointerEvents="none"/>
      <text x="250" y="475" textAnchor="middle" className="globe-caption">HOME BASE • {home.title}</text>
    </svg>
    <div className="globe-scanline" aria-hidden="true" />
  </div>;
}
