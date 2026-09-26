import React, { useEffect, useMemo, useState } from 'react';
import LiveLeafletMap from '../components/LiveLeafletMap.jsx';
import { listPhotos } from './photos.js';
import { kgOf, trailActive, trailMiles, walkActive, workoutActive } from './energy.js';

// The Adventure journal: what you actually did, day by day, from the records the app keeps. Hikes,
// walks and drives with their tracks, photos with Herbie's notes, food, water, workouts, pulse checks,
// markers you placed, trip plans and your own notes. Nothing here is generated filler.

const dayKey = t => new Date(Number(t)).toLocaleDateString('en-CA');
const clock = t => new Date(Number(t)).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const dur = s => { const m = Math.round(Number(s || 0) / 60); return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : `${m} min`; };
const load = (k, f) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : f; } catch { return f; } };
const pts = list => (list || []).map(p => (Array.isArray(p) ? { lat: p[0], lon: p[1] } : { lat: Number(p.lat), lon: Number(p.lon) })).filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon));
const milesOf = trace => { let d = 0; for (let i = 1; i < trace.length; i++) { const a = trace[i - 1], b = trace[i], r = Math.PI / 180; const h = Math.sin((b.lat - a.lat) * r / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin((b.lon - a.lon) * r / 2) ** 2; d += 7917.6 * Math.asin(Math.sqrt(h)); } return d; };

const KINDS = {
  hike: { label: 'Hikes', icon: '▲', tone: 'hike' }, walk: { label: 'Walks', icon: '👣', tone: 'walk' }, drive: { label: 'Drives', icon: '🚙', tone: 'drive' },
  photo: { label: 'Photos', icon: '📷', tone: 'photo' }, food: { label: 'Food', icon: '🍎', tone: 'food' }, workout: { label: 'Workouts', icon: '💪', tone: 'walk' },
  pulse: { label: 'Health', icon: '♥', tone: 'pulse' }, marker: { label: 'Markers', icon: '📍', tone: 'marker' }, plan: { label: 'Plans', icon: '🗺', tone: 'plan' }, note: { label: 'Notes', icon: '✎', tone: 'note' }
};
const FILTERS = ['hike', 'walk', 'drive', 'photo', 'food', 'pulse', 'note'];
const GROUP = { workout: 'walk', marker: 'note', plan: 'note' };

// A small outline of a track, drawn to fit a box (north up).
function TrackShape({ trace, w = 88, h = 56 }) {
  if (!trace || trace.length < 2) return null;
  const lat0 = trace[0].lat * Math.PI / 180, k = Math.cos(lat0);
  const xs = trace.map(p => p.lon * k), ys = trace.map(p => p.lat);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const s = Math.min((w - 8) / Math.max(1e-9, x1 - x0), (h - 8) / Math.max(1e-9, y1 - y0));
  const ox = (w - (x1 - x0) * s) / 2, oy = (h - (y1 - y0) * s) / 2;
  const step = Math.max(1, Math.floor(trace.length / 160));
  const d = trace.filter((_, i) => i % step === 0 || i === trace.length - 1).map((p, i) => `${i ? 'L' : 'M'}${(ox + (p.lon * k - x0) * s).toFixed(1)} ${(h - oy - (p.lat - y0) * s).toFixed(1)}`).join(' ');
  return <svg className="aj-shape" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" /></svg>;
}

export function buildJournal({ completedTrails = [], savedWalks = [], workoutLog = [], healthHistory = [], hiker = {}, routes = [], timelineArchive = null, photos = [] }) {
  const kg = kgOf(hiker);
  const byId = new Map(routes.map(r => [r.id, r]));
  const out = [];
  completedTrails.forEach((t, i) => {
    const route = byId.get(t.routeId);
    const trace = pts(t.trace?.length ? t.trace : route?.geometry?.coordinates?.map(([lon, lat]) => [lat, lon]));
    const end = Number(t.completedAt) || 0, start = Number(t.startedAt) || (end - Number(t.durationSeconds || 0) * 1000);
    const miles = trailMiles(t);
    const stars = t.review?.stars ? '★'.repeat(t.review.stars) : null;
    const camp = t.campName || route?.mountainArea || String(t.routeName || '').split(' via ')[0] || 'camp';
    // An overnight that spans two days reads as: hike in, night at camp, hike out.
    if (t.overnight && start && dayKey(start) !== dayKey(end)) {
      const half = Math.ceil(trace.length / 2);
      const inT = { ...t, trackMiles: miles / 2, miles: miles / 2, gainFt: t.gainInFt ?? Math.round(Number(t.gainFt || 0) * 0.75) };
      const outT = { ...t, trackMiles: miles / 2, miles: miles / 2, gainFt: t.gainOutFt ?? Math.round(Number(t.gainFt || 0) * 0.25) };
      const hIn = miles / 2 / 2 + inT.gainFt / 2000, hOut = miles / 2 / 2 + outT.gainFt / 2000;
      const arrive = start + hIn * 3600e3, leave = end - hOut * 3600e3;
      out.push({ id: `hike-${t.id || i}-in`, kind: 'hike', at: arrive, start, title: `Hiked in to ${camp}`, sub: t.routeName, stats: [`${(miles / 2).toFixed(1)} mi`, `${Number(inT.gainFt).toLocaleString()} ft climb`, `~${dur(hIn * 3600)}`, `${Math.round(trailActive(inT, kg)).toLocaleString()} cal`], trace: trace.slice(0, half), traceIsPlan: !t.trace?.length, miles: miles / 2, climb: Number(inT.gainFt), kcal: trailActive(inT, kg) });
      out.push({ id: `camp-${t.id || i}`, kind: 'hike', icon: '⛺', at: Math.max(arrive + 60e3, new Date(`${dayKey(start)}T21:00:00`).getTime()), title: `Night at ${camp}`, sub: 'Overnight', stats: [], point: trace[half - 1] || null });
      out.push({ id: `hike-${t.id || i}-out`, kind: 'hike', at: end, start: leave, title: `Hiked out from ${camp}`, sub: [t.source, stars].filter(Boolean).join(' · '), stats: [`${(miles / 2).toFixed(1)} mi`, `${Number(outT.gainFt).toLocaleString()} ft climb`, `${Math.round(trailActive(outT, kg)).toLocaleString()} cal`], trace: trace.slice(half - 1), traceIsPlan: !t.trace?.length, note: t.review?.note, miles: miles / 2, climb: Number(outT.gainFt), kcal: trailActive(outT, kg) });
      return;
    }
    const stats = [`${miles.toFixed(1)} mi`, t.gainFt ? `${Number(t.gainFt).toLocaleString()} ft climb` : null, t.durationSeconds ? dur(t.durationSeconds) : null, `${Math.round(trailActive(t, kg)).toLocaleString()} cal`].filter(Boolean);
    out.push({ id: `hike-${t.id || i}`, kind: 'hike', at: end || start, start, title: t.routeName || 'Hike', sub: [t.overnight ? `Overnight at ${camp}` : null, t.source, stars].filter(Boolean).join(' · '), stats, trace, traceIsPlan: !t.trace?.length, note: t.review?.note, miles, climb: Number(t.gainFt || 0), kcal: trailActive(t, kg) });
  });
  savedWalks.forEach((w, i) => {
    const trace = pts(w.trace);
    const at = Number(w.endedAt || w.savedAt || 0);
    const miles = Number(w.distanceMiles || 0) || milesOf(trace);
    out.push({ id: `walk-${w.id || i}`, kind: 'walk', at, start: Number(w.startedAt || at), title: w.plannedRouteName ? `Walk · ${w.plannedRouteName}` : 'Walk', sub: w.source || '', stats: [`${miles.toFixed(2)} mi`, w.durationSeconds ? dur(w.durationSeconds) : null, `${Math.round(walkActive(w, kg))} cal`].filter(Boolean), trace, miles, kcal: walkActive(w, kg) });
  });
  load('mappi3.driveHistory', []).forEach((d, i) => {
    const trace = pts(d.trace);
    const at = Number(d.at || 0), start = Number(trace[0]?.t || d.trace?.[0]?.t || at);
    out.push({ id: `drive-${d.id || i}`, kind: 'drive', at, start, title: `Drive to ${d.destination?.label || d.name || 'destination'}`, sub: d.destination?.address || '', stats: [trace.length > 1 ? `${milesOf(trace).toFixed(1)} mi driven` : d.routeMiles ? `${Number(d.routeMiles).toFixed(1)} mi route` : null].filter(Boolean), trace });
  });
  workoutLog.forEach((w, i) => out.push({ id: `wo-${w.id || i}`, kind: 'workout', at: Number(w.at || w.createdAt || 0), title: w.type || 'Workout', sub: `${w.intensity || 'moderate'} effort`, stats: [`${w.minutes || 0} min`, `${Math.round(workoutActive(w, kg))} cal`], kcal: workoutActive(w, kg) }));
  // Food: one entry per meal, from today's log and the saved days.
  const mealEntries = (meals, fallbackDay) => Object.entries(meals || {}).forEach(([slot, list]) => {
    const items = (list || []).filter(Boolean); if (!items.length) return;
    const at = Math.max(...items.map(x => Number(x.at || 0))) || new Date(`${fallbackDay}T${({ breakfast: '08', brunch: '10', lunch: '12', snack: '15', dinner: '18' })[slot] || '12'}:00:00`).getTime();
    const cal = items.reduce((a, x) => a + Number(x.calories || 0), 0);
    out.push({ id: `food-${fallbackDay}-${slot}`, kind: 'food', at, title: slot[0].toUpperCase() + slot.slice(1), sub: items.map(x => x.name).join(', '), stats: [`${cal.toLocaleString()} cal`], kcalIn: cal });
  });
  mealEntries(hiker.meals, hiker.intakeDate || dayKey(Date.now()));
  healthHistory.forEach(h => { if (h?.meals && Object.values(h.meals).some(l => l?.length)) mealEntries(h.meals, h.date); else if (h?.calories) out.push({ id: `food-${h.date}`, kind: 'food', at: new Date(`${h.date}T19:00:00`).getTime(), title: 'Food for the day', sub: `${h.itemCount || ''} items`, stats: [`${Number(h.calories).toLocaleString()} cal`], kcalIn: Number(h.calories) }); });
  (hiker.vitals || []).forEach(v => out.push({ id: v.id, kind: 'pulse', at: v.at, title: 'Pulse check', sub: v.context || '', stats: [`${v.bpm} bpm`, v.breathsPerMin ? `${v.breathsPerMin} breaths/min` : null, v.rmssd ? `HRV ${v.rmssd} ms` : null].filter(Boolean) }));
  // Markers you placed (their ids carry the time they were made).
  Object.entries(load('mappi3.customWaypointsByRoute', {})).forEach(([key, list]) => (list || []).forEach(w => {
    const ts = Number(String(w.id || '').match(/custom-(\d{12,})/)?.[1]); if (!ts) return;
    const routeId = key.split(':').slice(1).join(':');
    out.push({ id: `mk-${w.id}`, kind: 'marker', at: ts, title: `${w.icon || ''} ${w.name || w.type || 'Marker'}`.trim(), sub: `${byId.get(routeId)?.name || 'trail'}${Number.isFinite(Number(w.mile)) ? ` · mile ${Number(w.mile).toFixed(2)}` : ''}`, stats: [], point: { lat: Number(w.lat), lon: Number(w.lon) } });
  }));
  load('mappi3.readinessLog', []).forEach((l, i) => out.push({ id: `plan-${l.id || i}`, kind: 'plan', at: Number(l.at || 0), title: `Planned ${l.routeName || 'a hike'}`, sub: [l.trailLeaveTime && `leave ${l.trailLeaveTime}`, l.expectedReturn && `back ${l.expectedReturn}`, `${l.readyCount}/${l.total} ready`].filter(Boolean).join(' · '), stats: [] }));
  (timelineArchive?.events || []).filter(e => e && !e.automaticallyGenerated && /manual|user/i.test(`${e.source || ''} ${e.sourceLabel || ''}`)).forEach(e => out.push({ id: `note-${e.id}`, kind: 'note', at: Number(e.timestamp || 0), title: e.title || 'Note', sub: e.description || '', stats: [], point: e.lat != null && e.lon != null && Number.isFinite(Number(e.lat)) ? { lat: Number(e.lat), lon: Number(e.lon) } : null }));
  photos.forEach(p => out.push({ id: `ph-${p.id}`, kind: 'photo', at: Number(p.takenAt || 0), title: p.routeName ? `Photo · ${p.routeName}` : 'Photo', sub: p.userNote || '', herbie: p.note || '', stats: [p.mile != null ? `mile ${Number(p.mile).toFixed(1)}` : null, p.elevationFt ? `${Math.round(p.elevationFt).toLocaleString()} ft` : null].filter(Boolean), thumb: p.thumb, point: p.lat != null && p.lon != null ? { lat: Number(p.lat), lon: Number(p.lon) } : null }));
  return out.filter(e => Number.isFinite(e.at) && e.at > 0).sort((a, b) => b.at - a.at);
}

export default function AdventureJournal({ completedTrails, savedWalks, workoutLog, healthHistory, hiker, routes = [], timelineArchive, onAddNote, recording, selectedRoute, progress = 0, onOpenRoute }) {
  const [photos, setPhotos] = useState([]);
  useEffect(() => { const get = () => listPhotos({ limit: 500 }).then(setPhotos).catch(() => setPhotos([])); get(); window.addEventListener('mappi3-photos', get); return () => window.removeEventListener('mappi3-photos', get); }, []);
  const [filters, setFilters] = useState(() => new Set(load('mappi3.journalFilters', FILTERS)));
  useEffect(() => { try { localStorage.setItem('mappi3.journalFilters', JSON.stringify([...filters])); } catch { /* optional */ } }, [filters]);
  const [q, setQ] = useState('');
  const [days, setDays] = useState(14);
  const [selId, setSelId] = useState('');
  const [noteOpen, setNoteOpen] = useState(false);
  // Phones get the map under the entry you tap; wider screens keep it beside the list.
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(max-width: 900px)').matches);
  useEffect(() => { const mq = window.matchMedia?.('(max-width: 900px)'); if (!mq) return undefined; const on = () => setNarrow(mq.matches); mq.addEventListener?.('change', on); return () => mq.removeEventListener?.('change', on); }, []);
  const [draft, setDraft] = useState({ title: '', text: '' });
  const all = useMemo(() => buildJournal({ completedTrails, savedWalks, workoutLog, healthHistory, hiker, routes, timelineArchive, photos }), [completedTrails, savedWalks, workoutLog, healthHistory, hiker, routes, timelineArchive, photos]);
  const needle = q.trim().toLowerCase();
  const shown = all.filter(e => filters.has(GROUP[e.kind] || e.kind) && (!needle || `${e.title} ${e.sub} ${e.stats.join(' ')}`.toLowerCase().includes(needle)));
  const byDay = useMemo(() => { const m = new Map(); shown.forEach(e => { const k = dayKey(e.at); if (!m.has(k)) m.set(k, []); m.get(k).push(e); }); return [...m.entries()]; }, [shown]);
  const visibleDays = byDay.slice(0, days);
  const sel = all.find(e => e.id === selId) || shown.find(e => e.trace?.length > 1) || shown[0];
  const mapTrace = sel?.trace?.length > 1 ? sel.trace : [];
  const mapCenter = mapTrace[0] || sel?.point || null;
  const dayPhotos = sel ? photos.filter(p => dayKey(p.takenAt) === dayKey(sel.at) && p.lat != null && p.lon != null).map(p => ({ id: `ph-${p.id}`, name: p.userNote || p.note || 'Photo', type: 'Photo', lat: Number(p.lat), lon: Number(p.lon), photoId: p.id })) : [];

  // Totals for the last 7 and 30 days.
  const since = n => Date.now() - n * 864e5;
  const total = n => { const list = all.filter(e => e.at >= since(n)); return { hikes: list.filter(e => e.kind === 'hike').length, miles: list.reduce((a, e) => a + (e.miles || 0), 0), climb: list.reduce((a, e) => a + (e.climb || 0), 0), kcal: list.reduce((a, e) => a + (e.kcal || 0), 0), photos: list.filter(e => e.kind === 'photo').length }; };
  const w = total(7), mo = total(30);
  // Calendar dots for the current month.
  const now = new Date(); const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const activeDays = new Set(all.filter(e => ['hike', 'walk', 'drive', 'photo'].includes(e.kind)).map(e => dayKey(e.at)));
  const cells = Array.from({ length: new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() }, (_, i) => new Date(now.getFullYear(), now.getMonth(), i + 1));
  const jumpDay = k => { const i = byDay.findIndex(([d]) => d === k); if (i < 0) return; if (i >= days) setDays(i + 1); requestAnimationFrame(() => document.getElementById(`aj-day-${k}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })); const first = byDay[i][1].find(e => e.trace?.length > 1) || byDay[i][1][0]; if (first) setSelId(first.id); };
  const toggle = k => setFilters(f => { const n = new Set(f); n.has(k) ? n.delete(k) : n.add(k); return n.size ? n : new Set(FILTERS); });
  const saveNote = () => { if (!draft.title.trim() && !draft.text.trim()) return; onAddNote && onAddNote(draft.title.trim() || 'Note', draft.text.trim()); setDraft({ title: '', text: '' }); setNoteOpen(false); };

  const mapBox = <div className="aj-map st-card">{mapCenter ? <><LiveLeafletMap trace={mapTrace} center={[mapCenter.lat, mapCenter.lon]} waypoints={[...(sel?.point && !mapTrace.length ? [{ id: 'sel', name: sel.title, type: sel.kind === 'photo' ? 'Photo' : 'Waypoint', lat: sel.point.lat, lon: sel.point.lon }] : []), ...dayPhotos]} showCenterMarker={false} /><p className="muted aj-map-cap">{sel?.title}{sel?.traceIsPlan ? ' · planned line (no GPS track was saved for this hike)' : mapTrace.length ? ` · ${mapTrace.length} GPS points` : ''}</p></> : <p className="muted">Pick an entry with a place to see it on the map.</p>}</div>;
  return <section className="aj">
    <div className="aj-top">
      <div className="aj-head"><div><h2>Journal</h2><p className="muted">Everything you did, day by day, from the records on this device.</p></div>
        <button type="button" className="primary aj-add" onClick={() => setNoteOpen(o => !o)}>{noteOpen ? 'Close' : '+ Add a note'}</button></div>
      {noteOpen && <div className="aj-note-form st-card"><input value={draft.title} onChange={e => setDraft(d => ({ ...d, title: e.target.value }))} placeholder="Title (e.g. Moose at the pond)" /><textarea rows={3} value={draft.text} onChange={e => setDraft(d => ({ ...d, text: e.target.value }))} placeholder="What happened?" /><button type="button" className="primary small" onClick={saveNote}>Save note</button></div>}
      <div className="aj-totals">
        <div><span className="st-label">Last 7 days</span><b>{w.hikes} hike{w.hikes === 1 ? '' : 's'}</b><small>{w.miles.toFixed(1)} mi · {Math.round(w.climb).toLocaleString()} ft · {Math.round(w.kcal).toLocaleString()} cal</small></div>
        <div><span className="st-label">Last 30 days</span><b>{mo.hikes} hike{mo.hikes === 1 ? '' : 's'}</b><small>{mo.miles.toFixed(1)} mi · {Math.round(mo.climb).toLocaleString()} ft · {mo.photos} photo{mo.photos === 1 ? '' : 's'}</small></div>
        <div className="aj-cal"><span className="st-label">{now.toLocaleDateString([], { month: 'long' })}</span><div className="aj-cal-grid" style={{ '--offset': monthStart.getDay() }}>{cells.map(d => { const k = d.toLocaleDateString('en-CA'); const on = activeDays.has(k); return <button key={k} type="button" className={`${on ? 'on' : ''} ${k === dayKey(Date.now()) ? 'today' : ''}`} disabled={!byDay.some(([x]) => x === k)} onClick={() => jumpDay(k)} aria-label={d.toDateString()}>{d.getDate()}</button>; })}</div></div>
      </div>
      {recording && selectedRoute && <div className="aj-live"><b>Hiking now</b> {selectedRoute.name} · {Math.round(progress * 100)}% · <button type="button" className="ghost small" onClick={() => onOpenRoute && onOpenRoute()}>Open Navigate</button></div>}
      <div className="aj-bar"><div className="aj-chips">{FILTERS.map(k => <button key={k} type="button" className={filters.has(k) ? 'on' : ''} onClick={() => toggle(k)}>{KINDS[k].icon} {KINDS[k].label}</button>)}</div><input className="aj-search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search your journal" /></div>
    </div>
    <div className={`aj-body ${narrow ? 'narrow' : ''}`}>
      {!narrow && mapBox}
      <div className="aj-days">
        {!visibleDays.length && <div className="st-card aj-empty"><b>Nothing here yet.</b><p className="muted">Finish a hike, save a walk or drive, take a trail photo or log food and it shows up here.</p></div>}
        {visibleDays.map(([k, list]) => {
          const d = new Date(`${k}T12:00:00`);
          const miles = list.reduce((a, e) => a + (e.miles || 0), 0), climb = list.reduce((a, e) => a + (e.climb || 0), 0), burn = list.reduce((a, e) => a + (e.kcal || 0), 0), eat = list.reduce((a, e) => a + (e.kcalIn || 0), 0);
          return <div key={k} id={`aj-day-${k}`} className="aj-day">
            <div className="aj-day-head"><h3>{d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' })}</h3>
              <span>{[miles ? `${miles.toFixed(1)} mi` : null, climb ? `${Math.round(climb).toLocaleString()} ft` : null, burn ? `${Math.round(burn).toLocaleString()} cal burned` : null, eat ? `${eat.toLocaleString()} cal eaten` : null].filter(Boolean).join(' · ')}</span></div>
            <ol className="aj-list">{[...list].sort((a, b) => (a.start || a.at) - (b.start || b.at)).map(e => <li key={e.id} className={`aj-item k-${KINDS[e.kind]?.tone || e.kind} ${sel?.id === e.id ? 'sel' : ''}`}>
              <button type="button" onClick={() => setSelId(e.id)}>
                <span className="aj-time">{e.start && e.start < e.at - 60000 ? `${clock(e.start)}–${clock(e.at)}` : clock(e.at)}</span>
                <span className="aj-ic" aria-hidden="true">{e.icon || KINDS[e.kind]?.icon}</span>
                <span className="aj-main"><b>{e.title}</b>{e.sub && <small>{e.sub}</small>}{e.herbie && <small className="aj-herbie">Herbie: {e.herbie}</small>}{e.stats.length > 0 && <span className="aj-stats">{e.stats.map(s => <i key={s}>{s}</i>)}</span>}{e.note && <small>“{e.note}”</small>}</span>
                {e.thumb ? <img className="aj-thumb" src={e.thumb} alt="" /> : e.trace?.length > 1 ? <TrackShape trace={e.trace} /> : null}
              </button>{narrow && sel?.id === e.id && (e.trace?.length > 1 || e.point) && mapBox}</li>)}</ol>
          </div>;
        })}
        {byDay.length > days && <button type="button" className="ghost aj-more" onClick={() => setDays(n => n + 14)}>Show earlier days ({byDay.length - days} more)</button>}
      </div>
    </div>
  </section>;
}
