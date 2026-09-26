import React, { useMemo, useState } from 'react';

// Weather page: now, a 48-hour chart, 10 days, the best hiking window for the planned day,
// daylight, and the Sense HAT pressure trend. The older Weather Center (NOAA, Pi refresh) sits below.
const hourLabel = t => new Date(t).toLocaleTimeString([], { hour: 'numeric' });
const dayLabel = d => new Date(`${d}T12:00:00`).toLocaleDateString([], { weekday: 'short', month: 'numeric', day: 'numeric' });
const timeOf = iso => iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—';
const compass = deg => Number.isFinite(Number(deg)) ? ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(Number(deg) / 45) % 8] : '';

function HourlyChart({ hours }) {
  const [hover, setHover] = useState(null);
  if (!hours.length) return <p className="muted">No hourly forecast cached yet. It fills in the next time the app or Pi has internet.</p>;
  const W = 960, H = 210, pad = { l: 36, r: 12, t: 16, b: 34 };
  const temps = hours.map(h => Number(h.tempF));
  const tMin = Math.floor(Math.min(...temps) / 5) * 5 - 5, tMax = Math.ceil(Math.max(...temps) / 5) * 5 + 5;
  const X = i => pad.l + ((W - pad.l - pad.r) * i) / Math.max(1, hours.length - 1);
  const Y = t => H - pad.b - ((H - pad.t - pad.b) * (t - tMin)) / (tMax - tMin || 1);
  const bw = (W - pad.l - pad.r) / hours.length;
  const line = hours.map((h, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(Number(h.tempF)).toFixed(1)}`).join(' ');
  const ticks = [tMin, Math.round((tMin + tMax) / 2), tMax];
  return <div className="wx-chart-wrap"><svg viewBox={`0 0 ${W} ${H}`} className="wx-chart" role="img" aria-label="Temperature and rain chance, next 48 hours" onMouseLeave={() => setHover(null)}>
    {ticks.map(t => <g key={t}><line x1={pad.l} x2={W - pad.r} y1={Y(t)} y2={Y(t)} className="wx-grid" /><text x={pad.l - 6} y={Y(t) + 4} textAnchor="end" className="wx-tick">{t}°</text></g>)}
    {hours.map((h, i) => <rect key={`p${i}`} x={X(i) - bw / 2 + 1} width={Math.max(1, bw - 2)} y={H - pad.b - ((H - pad.t - pad.b) * Number(h.precip || 0)) / 100} height={((H - pad.t - pad.b) * Number(h.precip || 0)) / 100} className="wx-rain" />)}
    <path d={line} className="wx-temp" />
    {hours.map((h, i) => i % 6 === 0 && <text key={`x${i}`} x={X(i)} y={H - 12} textAnchor="middle" className="wx-tick">{new Date(h.time).getHours() === 0 ? new Date(h.time).toLocaleDateString([], { weekday: 'short' }) : hourLabel(h.time)}</text>)}
    {hours.map((h, i) => <rect key={`h${i}`} x={X(i) - bw / 2} width={bw} y={pad.t} height={H - pad.t - pad.b} fill="transparent" onMouseEnter={() => setHover(i)} onTouchStart={() => setHover(i)} />)}
    {hover !== null && <g><line x1={X(hover)} x2={X(hover)} y1={pad.t} y2={H - pad.b} className="wx-hover" /><circle cx={X(hover)} cy={Y(Number(hours[hover].tempF))} r="4.5" className="wx-dot" /></g>}
  </svg>
  <div className="wx-readout">{hover !== null ? <>{new Date(hours[hover].time).toLocaleString([], { weekday: 'short', hour: 'numeric' })} · <strong>{Math.round(hours[hover].tempF)}°F</strong>{Number.isFinite(Number(hours[hover].feelsF)) && ` (feels ${Math.round(hours[hover].feelsF)}°)`} · rain {hours[hover].precip ?? 0}%{Number.isFinite(Number(hours[hover].windMph)) && ` · wind ${Math.round(hours[hover].windMph)} mph`}{Number.isFinite(Number(hours[hover].uv)) && ` · UV ${Math.round(hours[hover].uv)}`}</> : <span className="muted">Line: temperature. Bars: chance of rain. Hover or tap for details.</span>}</div></div>;
}

// Scores each daylight hour for hiking: dry, mild, light wind. Returns the best block of `hours` hours.
function bestWindow(hours, dateKey, needHours) {
  const day = hours.filter(h => String(h.time).startsWith(dateKey)).filter(h => { const hr = new Date(h.time).getHours(); return hr >= 6 && hr <= 19; });
  if (day.length < Math.max(2, Math.ceil(needHours))) return null;
  const score = h => { const t = Number(h.feelsF ?? h.tempF); const comfort = Math.max(0, 1 - Math.abs(t - 58) / 35); return Number(h.precip || 0) * -1.2 + comfort * 40 - Math.max(0, Number(h.windMph || 0) - 12) * 2; };
  const n = Math.max(1, Math.ceil(needHours));
  let best = null;
  for (let i = 0; i + n <= day.length; i += 1) {
    const block = day.slice(i, i + n);
    const s = block.reduce((a, h) => a + score(h), 0) / n;
    if (!best || s > best.score) best = { score: s, start: block[0].time, end: block[block.length - 1].time, rain: Math.max(...block.map(h => Number(h.precip || 0))), lo: Math.min(...block.map(h => Number(h.tempF))), hi: Math.max(...block.map(h => Number(h.tempF))) };
  }
  return best;
}

export default function WeatherPage({ conditions = {}, piLive = null, selectedRoute = null, launchPlan = {}, labelFor, iconFor, Animation, children }) {
  const hours = (conditions.hourly || []).slice(0, 48);
  const days = (conditions.daily || []).slice(0, 10);
  const today = days[0] || {};
  const todayIso = new Date().toLocaleDateString('en-CA');
  const hikeDate = launchPlan?.hikeDate && (launchPlan.hikeDateChosen || launchPlan.hikeDate > todayIso) ? launchPlan.hikeDate : '';
  const needHours = useMemo(() => { const s = String(selectedRoute?.estimatedTime || ''); return Number((s.match(/(\d+(?:\.\d+)?)\s*h/) || [])[1] || 0) + Number((s.match(/(\d+)\s*m/) || [])[1] || 0) / 60 || 3; }, [selectedRoute?.id]);
  const hikeDay = days.find(d => d.date === hikeDate);
  const window = hikeDay ? bestWindow(conditions.hourly || [], hikeDate, needHours) : null;
  const sense = piLive?.sense || {};
  const hpa = Number(sense.pressure);
  const next6 = (conditions.hourly || []).slice(0, 6);
  const stormSoon = next6.some(h => [95, 96, 99].includes(Number(h.code)));
  const rainSoon = next6.length ? Math.max(...next6.map(h => Number(h.precip || 0))) : 0;
  const updated = conditions.fetchedAt ? new Date(conditions.fetchedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : null;
  return <div className="wx-page">
    <section className="wx-now st-card">
      <div className="wx-now-main">
        {Animation && <Animation code={conditions.weatherCode} tempF={conditions.tempF} precip={rainSoon} label="Current weather" />}
        <div><div className="st-eyebrow">{conditions.location || 'Forecast point'}</div><div className="wx-temp-now">{Number.isFinite(Number(conditions.tempF)) ? `${Math.round(conditions.tempF)}°F` : '—'}</div><div className="wx-cond">{labelFor ? labelFor(conditions.weatherCode, conditions.tempF) : ''}{Number.isFinite(Number(conditions.feelsF)) && ` · feels ${Math.round(conditions.feelsF)}°`}</div></div>
      </div>
      <div className="wx-now-grid">
        <div><strong>{Number.isFinite(Number(today.maxF)) ? `${Math.round(today.minF)}–${Math.round(today.maxF)}°` : '—'}</strong><span>today</span></div>
        <div><strong>{rainSoon}%</strong><span>rain next 6 h</span></div>
        <div><strong>{Number.isFinite(Number(conditions.windMph)) ? `${conditions.windMph} ${compass(conditions.windDir)}` : '—'}</strong><span>wind mph{conditions.gustMph ? ` · gusts ${conditions.gustMph}` : ''}</span></div>
        <div><strong>{conditions.humidity ?? '—'}%</strong><span>humidity</span></div>
        <div><strong>{today.uvMax != null ? Math.round(today.uvMax) : '—'}</strong><span>UV max</span></div>
        <div><strong>{conditions.airQuality ?? '—'}</strong><span>air quality</span></div>
        <div><strong>{timeOf(today.sunrise)}</strong><span>sunrise</span></div>
        <div><strong>{timeOf(today.sunset)}</strong><span>sunset</span></div>
      </div>
      <div className="wx-source">{/live/i.test(conditions.source || '') ? `Live · updated ${updated}` : `Offline · showing forecast saved ${updated || 'earlier'}`}</div>
    </section>
    {(stormSoon || rainSoon >= 60) && <div className={`alert ${stormSoon ? 'danger' : 'warn'}`}><strong>{stormSoon ? 'Thunderstorms in the next 6 hours.' : `Rain likely (${rainSoon}%) in the next 6 hours.`}</strong> {stormSoon ? 'Get below treeline and off ridges before it arrives.' : 'Pack the rain shell and keep electronics dry.'}</div>}
    <div className="wx-row">
      <section className="st-card wx-hike">
        <div className="st-label">Your hike</div>
        {selectedRoute && hikeDate ? (hikeDay ? <>
          <h3>{selectedRoute.name}</h3>
          <p className="muted">{dayLabel(hikeDate)} · {iconFor ? iconFor(hikeDay.code, hikeDay.maxF) : ''} {labelFor ? labelFor(hikeDay.code, hikeDay.maxF) : ''} · {Math.round(hikeDay.minF)}–{Math.round(hikeDay.maxF)}°F · rain {hikeDay.precip ?? 0}%</p>
          {window ? <div className="wx-window"><strong>Best window: {new Date(window.start).toLocaleTimeString([], { hour: 'numeric' })} to {new Date(new Date(window.end).getTime() + 3600000).toLocaleTimeString([], { hour: 'numeric' })}</strong><span>{Math.round(window.lo)}–{Math.round(window.hi)}°F · rain up to {window.rain}% · fits the {needHours.toFixed(1)} h hike</span></div> : <p className="muted">Hourly detail for that day arrives within 3 days of the hike.</p>}
        </> : <p className="muted">{dayLabel(hikeDate)} is past the 10-day forecast. Check back closer to the date.</p>) : <p className="muted">Pick a trail and a hike date, and this finds the best hours to be on it.</p>}
      </section>
      <section className="st-card wx-pressure">
        <div className="st-label">Barometer · MapPI3 Sense HAT</div>
        {Number.isFinite(hpa) && hpa ? <><div className="wx-hpa">{hpa.toFixed(1)} <small>hPa</small></div><p className="muted">{hpa < 1000 ? 'Low pressure. Unsettled weather is likely.' : hpa > 1022 ? 'High pressure. Usually settled and clear.' : 'Normal range.'} A drop of 3 hPa or more in 3 hours often means a storm is coming.</p></> : <p className="muted">Connect to the MapPI3 unit to read its barometer. It keeps working with no internet.</p>}
      </section>
    </div>
    <section className="st-card"><div className="st-label">Next 48 hours</div><HourlyChart hours={hours} /></section>
    <section className="st-card"><div className="st-label">10 days</div>
      <div className="wx-days">{days.length ? days.map(d => { const span = 110; const lo = Math.min(...days.map(x => Number(x.minF))), hi = Math.max(...days.map(x => Number(x.maxF))); const L = ((Number(d.minF) - lo) / ((hi - lo) || 1)) * span, R = ((Number(d.maxF) - lo) / ((hi - lo) || 1)) * span; return <div key={d.date} className={`wx-day ${d.date === hikeDate ? 'hike' : ''}`}><span className="wx-day-name">{d.date === hikeDate ? 'Hike · ' : ''}{dayLabel(d.date)}</span><span className="wx-day-icon" aria-hidden="true">{iconFor ? iconFor(d.code, d.maxF) : ''}</span><span className="wx-day-rain">{d.precip ?? 0}%</span><span className="wx-day-lo">{Math.round(d.minF)}°</span><span className="wx-day-bar"><i style={{ left: `${L}px`, width: `${Math.max(4, R - L)}px` }} /></span><span className="wx-day-hi">{Math.round(d.maxF)}°</span></div>; }) : <p className="muted">No daily forecast cached yet.</p>}</div>
    </section>
    <details className="wx-legacy"><summary>Weather Center: NOAA alerts, Pi refresh and more</summary>{children}</details>
  </div>;
}
