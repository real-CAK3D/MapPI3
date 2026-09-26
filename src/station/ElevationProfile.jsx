import React, { useEffect, useMemo, useRef, useState } from 'react';
import { estimatedProfile, profileForRoute } from './terrain.js';

// Classifies a waypoint by its type first, then by its own name with the trail's name removed
// (so "Tumbledown Brook Trail first bearing check" is not mistaken for a brook).
export function waypointKind(w = {}, routeName = '') {
  const type = String(w.type || w.category || '').toLowerCase();
  const typed = kindFromText(type);
  if (typed !== 'wp') return typed;
  let name = String(w.name || '').toLowerCase();
  const rn = String(routeName || w.routeName || '').toLowerCase().trim();
  if (rn) name = name.replace(rn, ' ');
  name = name.replace(/\b(trail|path|loop|route)\b/g, ' ');
  return kindFromText(name);
}
function kindFromText(s) {
  if (/water|stream|creek|brook|spring|pond|lake|river|falls|waterfall/.test(s)) return 'water';
  if (/view|scenic|overlook|summit|peak|vista|lookout/.test(s)) return 'view';
  if (/camp|shelter|lean-?to|tent/.test(s)) return 'camp';
  if (/start|trailhead|finish|turnaround|end/.test(s)) return 'flag';
  if (/hazard|danger|caution|ledge|cliff/.test(s)) return 'hazard';
  return 'wp';
}
const kindLabel = { water: 'Water', view: 'View', camp: 'Camp', flag: 'Start / end', hazard: 'Hazard', wp: 'Waypoint' };
const profileCache = new Map();

export function useRouteProfile(route) {
  const key = route ? `${route.id}:${route.geometryRefined?.builtAt || 0}` : '';
  const [profile, setProfile] = useState(() => (key && profileCache.get(key)) || (route ? estimatedProfile(route) : null));
  useEffect(() => {
    if (!route) { setProfile(null); return undefined; }
    if (profileCache.has(key)) { setProfile(profileCache.get(key)); return undefined; }
    let cancelled = false;
    setProfile(estimatedProfile(route));
    profileForRoute(route).then(p => { if (p && !cancelled) { profileCache.set(key, p); setProfile(p); } });
    return () => { cancelled = true; };
  }, [key]);
  return profile;
}

function useWidth(ref, fallback = 600) {
  const [w, setW] = useState(fallback);
  useEffect(() => {
    if (!ref.current || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(200, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return w;
}

// The trail's climb with everything that matters placed on it: you, water, views, camps, the finish,
// and Herbie's upcoming cues. Miles on the x axis, feet on the y axis.
export default function ElevationProfile({ route, youMile = null, waypoints = [], height = 150, compact = false, faceUrl = null }) {
  const wrapRef = useRef(null);
  const width = useWidth(wrapRef);
  const profile = useRouteProfile(route);
  const [hover, setHover] = useState(null);
  const miles = Number(route?.distanceMiles || route?.miles || profile?.points?.at(-1)?.mile || 1);
  const marks = useMemo(() => (waypoints || []).filter(w => Number.isFinite(Number(w.mile))).map(w => ({ ...w, mile: Number(w.mile), kind: waypointKind(w, route?.name) })), [waypoints, route?.name]);
  if (!route || !profile?.points?.length) return <div className="elev-profile empty" ref={wrapRef}><span className="muted">Pick a trail to see its elevation profile.</span></div>;
  const pad = { l: compact ? 6 : 42, r: 10, t: compact ? 8 : 26, b: compact ? 6 : 24 };
  const min = profile.minFt, max = Math.max(profile.maxFt, min + 50);
  const X = m => pad.l + ((width - pad.l - pad.r) * Math.max(0, Math.min(miles, m))) / miles;
  const Y = f => height - pad.b - ((height - pad.t - pad.b) * (f - min)) / (max - min);
  const ftAt = (m) => { const pts = profile.points; const i = pts.findIndex(p => p.mile >= m); if (i <= 0) return pts[0].ft; const a = pts[i - 1], b = pts[i]; return a.ft + ((b.ft - a.ft) * (m - a.mile)) / ((b.mile - a.mile) || 1); };
  const line = profile.points.map((p, i) => `${i ? 'L' : 'M'}${X(p.mile).toFixed(1)} ${Y(p.ft).toFixed(1)}`).join(' ');
  const area = `${line} L${X(miles).toFixed(1)} ${height - pad.b} L${X(0).toFixed(1)} ${height - pad.b} Z`;
  const you = Number.isFinite(Number(youMile)) ? Math.max(0, Math.min(miles, Number(youMile))) : null;
  const done = you !== null ? profile.points.filter(p => p.mile <= you).map((p, i) => `${i ? 'L' : 'M'}${X(p.mile).toFixed(1)} ${Y(p.ft).toFixed(1)}`).join(' ') + ` L${X(you).toFixed(1)} ${Y(ftAt(you)).toFixed(1)}` : '';
  const steep = [];
  for (let i = 1; i < profile.points.length; i += 1) {
    const a = profile.points[i - 1], b = profile.points[i];
    const grade = (b.ft - a.ft) / (((b.mile - a.mile) || 0.001) * 5280);
    if (grade > 0.15) steep.push([a.mile, b.mile]);
  }
  const ticks = compact ? [] : [min, (min + max) / 2, max].map(v => Math.round(v / 50) * 50);
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const m = Math.max(0, Math.min(miles, ((e.clientX - r.left - pad.l) / (r.width - pad.l - pad.r)) * miles));
    setHover({ m, ft: ftAt(m) });
  };
  // Labels for the notable stops, skipping any that would overlap the one before it.
  const labels = [];
  let lastRight = -Infinity;
  const ordered = marks.filter(w => w.kind !== 'wp').map(w => ({ ...w, label: w.kind === 'flag' ? (w.mile < miles * 0.05 ? 'Start' : 'End') : `${kindLabel[w.kind]} ${w.mile}` }));
  ordered.forEach(w => { const est = w.label.length * 6.4; const x = X(w.mile); const left = w.mile < miles * 0.05 ? x : w.mile > miles * 0.95 ? x - est : x - est / 2; if (left > lastRight + 6) { labels.push(w); lastRight = left + est; } else if (w.mile > miles * 0.95 && labels.length) { labels[labels.length - 1] = w; lastRight = left + est; } });
  const nextAhead = you !== null ? marks.find(w => w.mile > you + 0.02) : null;
  return <div className={`elev-profile ${compact ? 'compact' : ''}`} ref={wrapRef}>
    {!compact && <div className="elev-head"><span className="label">Elevation · {Math.round(profile.gainFt).toLocaleString()} ft gain · {profile.minFt.toLocaleString()}–{profile.maxFt.toLocaleString()} ft</span><span className="elev-src">{profile.source === 'terrain' ? 'terrain data' : profile.note || 'estimate from listed gain'}</span></div>}
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Elevation profile for ${route.name}`} onMouseMove={compact ? undefined : onMove} onMouseLeave={() => setHover(null)}>
      {steep.map(([a, b], i) => <rect key={i} x={X(a)} y={pad.t} width={Math.max(1, X(b) - X(a))} height={height - pad.t - pad.b} className="elev-steep" />)}
      {ticks.map(v => <g key={v}><line x1={pad.l} x2={width - pad.r} y1={Y(v)} y2={Y(v)} className="elev-grid" /><text x={pad.l - 6} y={Y(v) + 4} textAnchor="end" className="elev-tick">{v.toLocaleString()}</text></g>)}
      <path d={area} className="elev-area" />
      <path d={line} className="elev-line" />
      {done && <path d={done} className="elev-done" />}
      {marks.map((w, i) => { const x = X(w.mile), y = Y(ftAt(w.mile)); return <g key={`${w.id || w.name}-${i}`} className={`elev-mark k-${w.kind}`}><line x1={x} x2={x} y1={y} y2={height - pad.b} /><circle cx={x} cy={y} r={w.kind === 'wp' ? 3.5 : 5} /><title>{`${w.name} · mile ${w.mile} · ${kindLabel[w.kind]}`}</title></g>; })}
      {!compact && labels.map((w, i) => <text key={`t${i}`} x={X(w.mile)} y={height - 8} textAnchor={w.mile < miles * 0.05 ? 'start' : w.mile > miles * 0.95 ? 'end' : 'middle'} className={`elev-label k-${w.kind}`}>{w.label}</text>)}
      {you !== null && <g className="elev-you"><line x1={X(you)} x2={X(you)} y1={pad.t - 4} y2={height - pad.b} /><circle cx={X(you)} cy={Y(ftAt(you))} r="6.5" />{!compact && <><rect x={X(you) - 32} y={2} width="64" height="17" rx="4" /><text x={X(you)} y={14} textAnchor="middle">YOU {you.toFixed(1)}</text></>}</g>}
      {hover && <g className="elev-hover"><line x1={X(hover.m)} x2={X(hover.m)} y1={pad.t} y2={height - pad.b} /><text x={Math.min(width - 90, X(hover.m) + 6)} y={pad.t + 12}>{hover.m.toFixed(2)} mi · {Math.round(hover.ft).toLocaleString()} ft</text></g>}
    </svg>
    {!compact && nextAhead && <div className="elev-next">{faceUrl && <img src={faceUrl} alt="" />}<span><strong>Next: {nextAhead.name}</strong> · {(nextAhead.mile - you).toFixed(2)} mi · {Math.round(ftAt(nextAhead.mile) - ftAt(you)) >= 0 ? '+' : ''}{Math.round(ftAt(nextAhead.mile) - ftAt(you))} ft</span></div>}
  </div>;
}
