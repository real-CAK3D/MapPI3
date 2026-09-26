import React, { useEffect, useState } from 'react';
import { buildBriefing } from './herbieDay.js';

// ---- Herbie event log: every event the app sends to Herbie is also kept locally (last 60). ----
const LOG_KEY = 'mappi3.herbieLog';
export function logHerbieEvent(event, reason = '') {
  try {
    const items = JSON.parse(localStorage.getItem(LOG_KEY) || '[]');
    const last = items[0];
    if (last && last.event === event && Date.now() - last.at < 60000) return;
    const next = [{ event, reason, at: Date.now() }, ...items].slice(0, 60);
    localStorage.setItem(LOG_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent('mappi3-herbie-log'));
  } catch { /* storage unavailable: the Pi still gets the event */ }
}
export function useHerbieLog() {
  const read = () => { try { return JSON.parse(localStorage.getItem(LOG_KEY) || '[]'); } catch { return []; } };
  const [items, setItems] = useState(read);
  useEffect(() => { const on = () => setItems(read()); window.addEventListener('mappi3-herbie-log', on); window.addEventListener('storage', on); return () => { window.removeEventListener('mappi3-herbie-log', on); window.removeEventListener('storage', on); }; }, []);
  return items;
}
const eventText = { 'gps-locked': 'GPS locked', 'gps-searching': 'Searching for GPS', 'off-route': 'Off trail', 'near-water': 'Water nearby', 'near-waterfall': 'Waterfall nearby', viewpoint: 'Viewpoint', 'near-camp': 'Campsite nearby', trailhead: 'Trailhead', 'finish-line': 'Finish', summit: 'Summit', hungry: 'Lunch time', halfway: 'Halfway', 'almost-there': 'Almost there', 'turn-around': 'Turn around', 'sunset-soon': 'Sunset soon', climb: 'Climb ahead', hazard: 'Hazard', junction: 'Junction', bridge: 'Bridge' };
export function HerbieEventLog({ limit = 6 }) {
  const items = useHerbieLog().slice(0, limit);
  return <div className="st-log">{items.length ? items.map((e, i) => <div key={i}><b>{new Date(e.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</b><span>{eventText[e.event] || e.event}{e.reason ? ` · ${e.reason}` : ''}</span></div>) : <p className="muted">Herbie's trail events show up here as they happen.</p>}</div>;
}

// ---- Pi readings: honest tiles, "—" when a sensor is not reporting. ----
export function PiTelemetry({ piLive, gpsAccuracyM = null }) {
  if (!piLive) return <div className="st-tiles offline"><div className="st-tile wide"><strong>Not connected</strong><span>Join the MapPI3 Wi-Fi for live GPS, compass and battery.</span></div></div>;
  const g = piLive.gps || {}, s = piLive.sense || {}, p = piLive.power || {}, sys = piLive.system || {};
  const pct = Number.isFinite(Number(p.percent)) && p.percent !== null ? Math.round(p.percent) : null;
  const hpa = Number(s.pressure);
  const tiles = [
    { k: 'GPS', v: g.fix ? `${g.mode === 3 || g.mode === '3' ? '3D' : 'Fix'} · ${g.satellites || 0} sat` : `No fix (${g.satellites || 0})`, tone: g.fix ? 'good' : 'warn' },
    { k: 'Accuracy', v: gpsAccuracyM ? `±${Math.round(gpsAccuracyM)} m` : Number.isFinite(Number(g.eph)) ? `±${Math.round(Number(g.eph))} m` : '—', tone: '' },
    { k: 'Heading', v: s.ok && Number.isFinite(Number(s.compass)) ? `${Math.round(Number(s.compass))}° ${s.compass_cardinal || ''}` : '—', tone: '' },
    { k: 'Pressure', v: Number.isFinite(hpa) && hpa ? `${Math.round(hpa)} hPa` : '—', tone: '' },
    { k: 'Pi temp', v: Number.isFinite(Number(sys.temperature_c)) ? `${Math.round(sys.temperature_c)} °C` : '—', tone: Number(sys.temperature_c) > 75 ? 'bad' : '' },
    { k: 'Battery', v: pct !== null ? `${pct}%${p.charging ? ' ⚡' : ''}` : p.pisugar_board_reachable === false ? 'Off' : '—', tone: pct === null ? 'warn' : pct < 20 ? 'bad' : 'good' }
  ];
  return <div className="st-tiles">{tiles.map(t => <div key={t.k} className={`st-tile ${t.tone}`}><strong>{t.v}</strong><span>{t.k}</span></div>)}</div>;
}

// ---- Herbie's good-morning card for Home. ----
export function HerbieBriefingCard({ faceUrl, name, calendar, route, hikeDate, sunset, driveMinutes, weather, specialDays, onPlan, onDrive, onPack }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 60000); return () => clearInterval(t); }, []);
  const b = buildBriefing({ now, name, calendar, route, hikeDate, sunset, driveMinutes, weather, specialDays });
  return <section className="st-briefing">
    <div className="st-briefing-face"><img src={faceUrl(b.face)} alt={`Herbie, ${b.face.replace('-', ' ')}`} /></div>
    <div className="st-briefing-copy">
      <div className="st-eyebrow">{now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })} · {now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</div>
      <h2>{b.hello}</h2>
      {b.lines.map((l, i) => <p key={i}>{l}</p>)}
      <div className="st-briefing-actions">
        {route ? <button type="button" className="primary" onClick={onDrive}>Drive to trailhead</button> : <button type="button" className="primary" onClick={onPlan}>Find a trail</button>}
        {route && <button type="button" className="ghost" onClick={onPack}>Check my pack</button>}
        {route && <button type="button" className="ghost" onClick={onPlan}>Hike plan</button>}
      </div>
    </div>
    {b.plan?.startBy && <div className="st-briefing-plan">
      {b.plan.leaveBy && <div><strong>{b.plan.leaveBy.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</strong><span>leave home</span></div>}
      <div><strong>{b.plan.startBy.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</strong><span>start hiking</span></div>
      <div><strong>{sunset.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</strong><span>sunset</span></div>
    </div>}
    {b.plan?.startBy && route && <HikeDayTimeline route={route} plan={b.plan} sunset={sunset} now={now} />}
  </section>;
}

// Live navigation facts shared with Hey Herbie (set by the Navigate page on each GPS fix).
export const navShared = { offTrailM: undefined, accuracyM: undefined, updatedAt: 0 };

// The hike day on one line: leave home, trailhead, each stop at the planned pace, finish, sunset.
function HikeDayTimeline({ route, plan, sunset, now }) {
  const miles = Number(route.distanceMiles || route.miles || 0);
  const hours = plan.hikeHours || 3;
  const at = mile => new Date(plan.startBy.getTime() + (mile / Math.max(0.1, miles)) * hours * 3600000);
  const wps = [...(route.waypoints || [])].filter(w => Number(w.mile) > 0 && Number(w.mile) < miles).sort((a, b) => Number(a.mile) - Number(b.mile));
  const finish = new Date(plan.startBy.getTime() + hours * 3600000);
  const stops = [
    ...(plan.leaveBy ? [{ t: plan.leaveBy, name: 'Leave home', kind: 'drive' }] : []),
    { t: plan.startBy, name: 'Trailhead', kind: 'start' },
    ...wps.map(w => ({ t: at(Number(w.mile)), name: String(w.name || '').replace(route.name, '').replace(/^[\s·:-]+/, '').trim() || w.name, kind: 'stop', mile: Number(w.mile) })),
    { t: finish, name: 'Finish', kind: 'finish', mile: miles },
    ...(sunset ? [{ t: sunset, name: 'Sunset', kind: 'sunset' }] : [])
  ].sort((a, b) => a.t - b.t);
  const t0 = stops[0].t.getTime(), t1 = stops[stops.length - 1].t.getTime();
  const X = t => `${(((t.getTime() - t0) / Math.max(1, t1 - t0)) * 100).toFixed(2)}%`;
  const nowIn = now.getTime() >= t0 && now.getTime() <= t1;
  return <div className="st-daytl" aria-label="Hike day timeline">
    <div className="st-daytl-track">
      {stops.map((s, i) => <div key={i} className={`st-daytl-stop k-${s.kind} ${i % 2 ? 'low' : ''}`} style={{ left: X(s.t) }}><i /><strong>{s.t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</strong><span>{s.name}{s.mile ? ` · mi ${s.mile}` : ''}</span></div>)}
      {nowIn && <div className="st-daytl-now" style={{ left: X(now) }}><span>now</span></div>}
    </div>
  </div>;
}
