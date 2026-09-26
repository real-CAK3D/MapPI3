import React, { useEffect, useMemo, useState } from 'react';
import { usePhotos } from './TrailPhotos.jsx';
import { mountainFor, stateOf as mtState, townOf, trailKey } from './mountains.js';

// Trail Passport: every mountain area is a stamp you earn by hiking any trail there, plus tiered
// badges and a rank built from everything you have done. All from local history; nothing is invented.
const SEEN_KEY = 'mappi3.passportSeen';
const hash = s => { let h = 2166136261; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
const seasonOf = d => { const m = d.getMonth(); return m >= 2 && m <= 4 ? 'spring' : m >= 5 && m <= 7 ? 'summer' : m >= 8 && m <= 10 ? 'autumn' : 'winter'; };
const stateOf = r => { const s = `${r?.place || ''} ${r?.region || ''}`; const m = s.match(/(Maine|New Hampshire|Vermont|Massachusetts|New York|Pennsylvania|West Virginia|Kentucky|Ohio|Connecticut|Rhode Island|Virginia|North Carolina|Tennessee)/i); return m ? m[1] : (r?.region || '').trim(); };
const RANKS = [[0, 'Trailhead Rookie'], [300, 'Blaze Follower'], [800, 'Ridge Walker'], [1600, 'Summit Seeker'], [3000, 'Peak Bagger'], [5000, 'Mountain Legend']];
const TIER = ['', 'Bronze', 'Silver', 'Gold'];

// A mountain that colors in from the base up as you hike the trails around it. Same peak drawing and
// colors as the original Home skyline: grey until hiked, blue as it fills, lifted when it is your trail.
const PEAK = 'M2 30 14 8l5 8 7-13 12 27H2z';
const FACET = 'M14 8 19 16l3-5 4 6 0-14 12 27H2z';
function MountainBadge({ area, town, done, total, miles, current, recent, onClick }) {
  const seed = hash(area);
  const frac = total ? done / total : 0;
  const conquered = total > 0 && done >= total;
  const id = `mb-${seed}`;
  const fillTop = 30 - 27 * frac;
  const name = area.length > 24 ? `${area.slice(0, 23)}…` : area;
  return <button type="button" className={`mb overview-peak ${conquered ? 'conquered completed' : done ? 'started' : 'untouched'} ${current ? 'current' : ''} ${recent ? 'recent' : ''}`} onClick={onClick} title={`${area} · ${done} of ${total} trail${total === 1 ? '' : 's'} hiked${Number.isFinite(miles) ? ` · ${Math.round(miles)} mi from home` : ''}`}>
    <span className="mb-art">
      <svg viewBox="0 0 40 32" aria-hidden="true">
        <defs><clipPath id={`${id}-c`}><rect x="0" y={fillTop} width="40" height={32 - fillTop} /></clipPath></defs>
        <path className="peak-shadow" d={PEAK} />
        <path className="peak-snow" d={FACET} />
        {done > 0 && <g clipPath={`url(#${id}-c)`}><path className="mb-fill" d={PEAK} /><path className="mb-fill-facet" d={FACET} /></g>}
        {conquered && <path className="mb-flag" d="M26 3.2V-3.5l4.5 1.6-4.5 1.6" />}
      </svg>
      <small>{conquered ? '✓' : `${done}/${total}`}</small>
    </span>
    <strong>{name}</strong>
    <span className="mb-sub">{town ? `${town} · ` : ''}{Number.isFinite(miles) ? `${Math.round(miles)} mi` : ''}</span>
    <span className="mb-sub">{done} of {total} trail{total === 1 ? '' : 's'}</span>
  </button>;
}

export function computePassport({ completedTrails = [], routes = [], savedWalks = [], healthHistory = [], photoCount = 0, home = null }) {
  const byId = new Map(routes.map(r => [r.id, r]));
  const byName = new Map(routes.map(r => [String(r.name || '').toLowerCase(), r]));
  const hikes = completedTrails.map(c => ({ ...c, route: byId.get(c.routeId) || byName.get(String(c.routeName || c.name || '').toLowerCase()) || null, at: new Date(Number(c.completedAt || c.endedAt || c.savedAt || Date.now())) }));
  // Group by the mountain each trail climbs; the same trail listed twice counts once.
  const areas = new Map();
  routes.forEach(r => {
    const m = mountainFor(r); if (!m) return;
    if (!areas.has(m)) areas.set(m, { area: m, routes: [], trails: new Map() });
    const a = areas.get(m); a.routes.push(r);
    const k = trailKey(r, m); if (!a.trails.has(k)) a.trails.set(k, []); a.trails.get(k).push(r.id);
  });
  const mode = xs => { const c = {}; xs.filter(Boolean).forEach(x => { c[x] = (c[x] || 0) + 1; }); return Object.keys(c).sort((a, b) => c[b] - c[a])[0] || ''; };
  areas.forEach(a => { a.state = mode(a.routes.map(mtState)); a.town = mode(a.routes.map(townOf)); });
  hikes.forEach(h => { if (!h.route) return; const a = areas.get(mountainFor(h.route)); if (!a) return; a.first = a.first && a.first < h.at ? a.first : h.at; (a.doneKeys ||= new Set()).add(trailKey(h.route, a.area)); });
  const centerOf = rs => { const pts = rs.map(r => r.geometry?.coordinates?.[0]).filter(c => Array.isArray(c) && Number.isFinite(c[0])); if (!pts.length) return null; return { lat: pts.reduce((s, c) => s + c[1], 0) / pts.length, lon: pts.reduce((s, c) => s + c[0], 0) / pts.length }; };
  const miFrom = (a, b) => { if (!a || !b) return NaN; const R = 3958.8, t = Math.PI / 180; const dl = (b.lat - a.lat) * t, dn = (b.lon - a.lon) * t; const h = Math.sin(dl / 2) ** 2 + Math.cos(a.lat * t) * Math.cos(b.lat * t) * Math.sin(dn / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); };
  const stamps = [...areas.values()].map(a => { const center = centerOf(a.routes); return { ...a, center, miles: miFrom(home, center), earned: Boolean(a.first), done: a.doneKeys?.size || 0, total: a.trails.size, date: a.first ? a.first.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase() : '' }; });
  const hikeMiles = hikes.reduce((s, h) => s + Number(h.miles || h.route?.distanceMiles || 0), 0);
  const walkMiles = savedWalks.reduce((s, w) => s + Number(w.distanceMiles || w.miles || 0), 0);
  const gains = hikes.map(h => Number(h.route?.elevationGainFt || 0));
  const totalGain = gains.reduce((a, b) => a + b, 0);
  const starts = hikes.map(h => new Date(h.at.getTime() - Number(h.durationSeconds || 0) * 1000));
  const weeks = [...new Set(hikes.map(h => Math.floor((h.at.getTime() - 4 * 86400000) / (7 * 86400000))))].sort((a, b) => a - b);
  let streak = weeks.length ? 1 : 0, run = 1;
  for (let i = 1; i < weeks.length; i += 1) { run = weeks[i] === weeks[i - 1] + 1 ? run + 1 : 1; streak = Math.max(streak, run); }
  const earnedStamps = stamps.filter(s => s.earned);
  const badges = [
    { id: 'hikes', name: 'On the Trail', desc: 'Hikes completed', icon: 'boot', value: hikes.length, tiers: [1, 5, 20] },
    { id: 'miles', name: 'Mileage', desc: 'Trail miles, hikes and walks', icon: 'path', value: Math.round(hikeMiles + walkMiles), unit: 'mi', tiers: [10, 50, 150] },
    { id: 'vertical', name: 'Vertical', desc: 'Feet climbed on completed hikes', icon: 'up', value: totalGain, unit: 'ft', tiers: [5000, 20000, 50000] },
    { id: 'big-climb', name: 'Big Climb', desc: 'Biggest climb in one hike', icon: 'peak', value: Math.max(0, ...gains), unit: 'ft', tiers: [1000, 2000, 3000] },
    { id: 'peaks', name: 'Peak Collector', desc: 'Passport stamps earned', icon: 'stamp', value: earnedStamps.length, tiers: [3, 10, 25] },
    { id: 'whole', name: 'Whole Mountain', desc: 'Mountains with every trail hiked', icon: 'flag', value: stamps.filter(s => s.earned && s.done >= s.total).length, tiers: [1, 3, 6] },
    { id: 'states', name: 'Explorer', desc: 'States hiked', icon: 'map', value: new Set(earnedStamps.map(s => s.state).filter(Boolean)).size, tiers: [2, 4, 6] },
    { id: 'seasons', name: 'All Seasons', desc: 'Seasons with a hike', icon: 'leaf', value: new Set(hikes.map(h => seasonOf(h.at))).size, tiers: [2, 3, 4] },
    { id: 'early', name: 'Early Bird', desc: 'Hikes started before 8 AM', icon: 'sun', value: starts.filter(d => d.getHours() < 8).length, tiers: [1, 5, 10] },
    { id: 'night', name: 'Night Owl', desc: 'Hikes finished after 7 PM', icon: 'moon', value: hikes.filter(h => h.at.getHours() >= 19).length, tiers: [1, 3, 10] },
    { id: 'streak', name: 'Streak', desc: 'Weeks in a row with a hike', icon: 'fire', value: streak, tiers: [2, 4, 8] },
    { id: 'photos', name: 'Shutterbug', desc: 'Trail photos taken', icon: 'camera', value: photoCount, tiers: [10, 50, 200] },
    { id: 'fuel', name: 'Well Fueled', desc: 'Days with food logged', icon: 'fork', value: healthHistory.length, tiers: [3, 14, 30] },
    { id: 'reviews', name: 'Trail Critic', desc: 'Hikes you rated', icon: 'star', value: hikes.filter(h => h.review).length, tiers: [1, 5, 15] }
  ].map(b => { const tier = b.tiers.filter(t => b.value >= t).length; const next = b.tiers[tier]; const prev = tier ? b.tiers[tier - 1] : 0; return { ...b, tier, next, pct: next ? Math.min(1, (b.value - prev) / (next - prev)) : 1 }; });
  const points = Math.round(earnedStamps.length * 100 + (hikeMiles + walkMiles) * 10 + totalGain / 100 + badges.reduce((s, b) => s + b.tier * 50, 0));
  const rankIdx = RANKS.reduce((idx, r, i) => (points >= r[0] ? i : idx), 0);
  const rank = { name: RANKS[rankIdx][1], next: RANKS[rankIdx + 1] || null, floor: RANKS[rankIdx][0], points };
  return { stamps, badges, rank, totals: { hikes: hikes.length, miles: hikeMiles + walkMiles, gain: totalGain, stamps: earnedStamps.length } };
}

const BI = {
  boot: <path d="M6 4h5v7l6 3c2 1 2 3 2 3v3H5z M5 17h14" />, path: <path d="M6 20c0-5 12-4 12-9S9 7 9 4" />, up: <path d="M4 19 10 9l4 5 6-9M16 5h4v4" />,
  peak: <path d="M3 19 10 7l3 5 2-3 6 10z" />, stamp: <><circle cx="12" cy="12" r="8" /><path d="M8 14l2.5-4 1.5 2 1-1.5L16 14z" /></>, flag: <path d="M6 21V4h11l-2 3.5 2 3.5H6" />,
  map: <path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z M9 4v14M15 6v14" />, leaf: <path d="M5 19c9 0 14-5 14-14-9 0-14 5-14 14zM5 19 13 11" />, sun: <><circle cx="12" cy="13" r="4" /><path d="M12 4v2M4 13h2M18 13h2M6.5 7.5l1.4 1.4M17.5 7.5l-1.4 1.4M3 19h18" /></>,
  moon: <path d="M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5z" />, fire: <path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-3 2-4 2-7 1 1 2 2 3 2 0-2 0-3 0-5z" />,
  camera: <><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.2" /></>, fork: <path d="M7 3v8a2 2 0 0 0 4 0V3M9 11v10M16 3c-2 1-2 5-2 8h3v10" />, star: <path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z" />
};

export default function TrailPassport({ completedTrails = [], routes = [], savedWalks = [], healthHistory = [], selectedRoute = null, faceUrl, onHerbieEvent, onPickArea, home = null, homeLabel = 'home', radius = 100, setRadius }) {
  const photos = usePhotos(null);
  const pp = useMemo(() => computePassport({ completedTrails, routes, savedWalks, healthHistory, photoCount: photos.length, home }), [completedTrails, routes, savedWalks, healthHistory, photos.length, home?.lat, home?.lon]);
  const [showAll, setShowAll] = useState(false);
  const [toast, setToast] = useState(null);
  // Celebrate badges earned since the passport was last seen. The first visit records silently.
  useEffect(() => {
    const now = pp.badges.filter(b => b.tier).map(b => `${b.id}:${b.tier}`).concat(pp.stamps.filter(s => s.earned).map(s => `stamp:${s.area}`));
    let seen = null;
    try { seen = JSON.parse(localStorage.getItem(SEEN_KEY) || 'null'); } catch { /* ignore */ }
    try { localStorage.setItem(SEEN_KEY, JSON.stringify(now)); } catch { /* ignore */ }
    if (!seen) return;
    const fresh = now.filter(k => !seen.includes(k));
    if (!fresh.length) return;
    const k = fresh[0];
    const b = pp.badges.find(x => k.startsWith(`${x.id}:`));
    const text = k.startsWith('stamp:') ? `New passport stamp: ${k.slice(6)}` : `${TIER[b.tier]} badge: ${b.name}`;
    setToast({ text, more: fresh.length - 1 });
    onHerbieEvent && onHerbieEvent('goal-done', 60, text);
    const t = setTimeout(() => setToast(null), 9000);
    return () => clearTimeout(t);
  }, [pp.rank.points]);
  // The board: mountains within the chosen distance of home, hiked ones first, then nearest first.
  const inRange = pp.stamps.filter(m => !radius || !Number.isFinite(m.miles) || m.miles <= radius);
  const stateDist = {}; inRange.forEach(m => { stateDist[m.state] = Math.min(stateDist[m.state] ?? 9999, m.miles || 9999); });
  const board = [...inRange].sort((a, b) => (stateDist[a.state] - stateDist[b.state]) || a.state.localeCompare(b.state) || (b.done > 0) - (a.done > 0) || (a.miles || 9999) - (b.miles || 9999));
  const shown = showAll ? board : board.slice(0, 18);
  const colored = inRange.filter(m => m.done > 0).length, conquered = inRange.filter(m => m.done >= m.total && m.total).length;
  const rk = pp.rank;
  const toNext = rk.next ? Math.min(1, (rk.points - rk.floor) / (rk.next[0] - rk.floor)) : 1;
  return <section className="panel pp">
    <div className="pp-head">
      <div className="pp-rank">
        <div className="st-eyebrow">Trail Passport</div>
        <h2>{rk.name}</h2>
        <div className="pp-bar"><i style={{ width: `${Math.round(toNext * 100)}%` }} /></div>
        <p className="muted">{rk.points.toLocaleString()} points{rk.next ? ` · ${(rk.next[0] - rk.points).toLocaleString()} to ${rk.next[1]}` : ' · top rank'}</p>
      </div>
      <div className="pp-totals">
        <div><strong>{pp.totals.stamps}</strong><span>stamps</span></div>
        <div><strong>{pp.totals.hikes}</strong><span>hikes</span></div>
        <div><strong>{Math.round(pp.totals.miles).toLocaleString()}</strong><span>miles</span></div>
        <div><strong>{pp.totals.gain.toLocaleString()}</strong><span>ft climbed</span></div>
      </div>
    </div>
    {toast && <div className="pp-toast" role="status">{faceUrl && <img src={faceUrl('party-mode')} alt="" />}<div><strong>{toast.text}</strong>{toast.more > 0 && <span> and {toast.more} more</span>}</div><button type="button" className="ghost small" onClick={() => setToast(null)}>Nice!</button></div>}
    <div className="mb-head"><div className="st-label">Mountain board · {colored} of {inRange.length} colored in{conquered ? ` · ${conquered} conquered` : ''}</div>
      {setRadius && <label className="mb-radius">Within <select value={radius} onChange={e => setRadius(Number(e.target.value))}>{[25, 50, 100, 200, 0].map(r => <option key={r} value={r}>{r ? `${r} mi` : 'any distance'}</option>)}</select> of {homeLabel}</label>}</div>
    {[...new Set(shown.map(m => m.state))].map(st => { const list = shown.filter(m => m.state === st); const all = inRange.filter(m => m.state === st); return <div key={st} className="mb-state">
      <div className="mb-state-head"><strong>{st}</strong><span>{all.filter(m => m.done).length} of {all.length} colored in</span></div>
      <div className="mb-grid">{list.map(m => <MountainBadge key={m.area} {...m} current={Boolean(selectedRoute) && m.routes.some(r => r.id === selectedRoute.id)} recent={Boolean(m.first) && Date.now() - m.first.getTime() < 21 * 86400000} onClick={() => onPickArea && onPickArea(m)} />)}</div>
    </div>; })}
    {board.length > shown.length && <button type="button" className="ghost small pp-more" onClick={() => setShowAll(true)}>Show all {board.length} mountains</button>}
    {!inRange.length && <p className="muted">No mountains in the trail catalog within {radius} miles of {homeLabel}. Try a bigger distance.</p>}
    {inRange.length > 0 && !colored && <p className="muted">Each trail you finish around a mountain colors in part of it. Hike every trail around it to conquer it. Tap a mountain to see its trails.</p>}
    <div className="st-label" style={{ marginTop: 14 }}>Badges</div>
    <div className="pp-badges">{pp.badges.map(b => <div key={b.id} className={`pp-badge t${b.tier}`} title={`${b.desc}: ${b.value.toLocaleString()}${b.unit ? ` ${b.unit}` : ''}`}>
      <div className="pp-medal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{BI[b.icon]}</svg></div>
      <div className="pp-badge-copy"><strong>{b.name}{b.tier ? <em>{TIER[b.tier]}</em> : null}</strong><span>{b.desc}</span>
        <div className="pp-bar small"><i style={{ width: `${Math.round(b.pct * 100)}%` }} /></div>
        <small>{b.value.toLocaleString()}{b.unit ? ` ${b.unit}` : ''}{b.next ? ` of ${b.next.toLocaleString()} for ${TIER[b.tier + 1]}` : ' · maxed out'}</small></div>
    </div>)}</div>
  </section>;
}
