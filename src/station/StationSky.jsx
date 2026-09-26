import React, { useEffect, useMemo, useRef, useState } from 'react';
import { approxDeclination, cameraPointing, skyNow } from './astro.js';

// Sky: real positions for your place and time, drawn over the phone camera where they actually are.
// Pointing comes from the phone's motion sensors (corrected for magnetic declination), or from the
// MapPI3 Sense HAT compass when the phone has none.
const cardinal = h => ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'][Math.round(((h % 360) + 360) % 360 / 22.5) % 16];
const wrap = d => ((d + 540) % 360) - 180;

export default function StationSky({ originPoint, piLive, settings = {}, setSettings }) {
  const gps = piLive?.gps?.fix ? { lat: Number(piLive.gps.lat), lon: Number(piLive.gps.lon), label: 'MapPI3 GPS' } : null;
  const place = gps || { lat: Number(originPoint?.lat || 44.1), lon: Number(originPoint?.lon || -70.2), label: originPoint?.label || 'home base' };
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 20000); return () => clearInterval(t); }, []);
  const sky = useMemo(() => skyNow(place.lat, place.lon, now), [place.lat, place.lon, Math.floor(now.getTime() / 20000)]);
  const autoDecl = approxDeclination(place.lat, place.lon);
  const decl = settings.skyDeclination === undefined || settings.skyDeclination === 'auto' ? autoDecl : Number(settings.skyDeclination);

  const [sensor, setSensor] = useState({ state: 'off', heading: null, alt: null, source: '' });
  const smooth = useRef({ x: 0, y: 1, a: 0, n: 0, absolute: false });
  const [needsTap, setNeedsTap] = useState(typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function');
  useEffect(() => {
    const onEvent = (e, absoluteEvent) => {
      if (e.beta === null || e.gamma === null) return;
      let alphaNorth = null, source = '';
      if (typeof e.webkitCompassHeading === 'number' && e.webkitCompassHeading >= 0) { alphaNorth = 360 - e.webkitCompassHeading; source = 'iPhone compass'; }
      else if ((absoluteEvent || e.absolute) && e.alpha !== null) { alphaNorth = e.alpha; source = 'phone compass'; smooth.current.absolute = true; }
      else if (!smooth.current.absolute && e.alpha !== null) { alphaNorth = e.alpha; source = 'phone motion (not north-referenced)'; }
      else return;
      const p = cameraPointing(alphaNorth, e.beta, e.gamma);
      const heading = (p.heading + decl + 360) % 360;
      const s = smooth.current, k = s.n < 3 ? 1 : 0.18;
      s.x = s.x + k * (Math.sin(heading * Math.PI / 180) - s.x); s.y = s.y + k * (Math.cos(heading * Math.PI / 180) - s.y); s.a = s.a + k * (p.alt - s.a); s.n += 1;
      setSensor({ state: 'on', heading: (Math.atan2(s.x, s.y) * 180 / Math.PI + 360) % 360, alt: s.a, source });
    };
    const abs = e => onEvent(e, true), rel = e => onEvent(e, false);
    window.addEventListener('deviceorientationabsolute', abs, true);
    window.addEventListener('deviceorientation', rel, true);
    return () => { window.removeEventListener('deviceorientationabsolute', abs, true); window.removeEventListener('deviceorientation', rel, true); };
  }, [decl]);
  const askMotion = async () => {
    try { const r = await DeviceOrientationEvent.requestPermission(); setNeedsTap(r !== 'granted'); if (r !== 'granted') setSensor(s => ({ ...s, state: 'denied' })); } catch { setSensor(s => ({ ...s, state: 'denied' })); }
  };
  // Sense HAT fallback: the Pi's compass (magnetic) and pitch.
  const sense = piLive?.sense;
  const pointing = sensor.state === 'on' ? sensor
    : sense?.ok && Number.isFinite(Number(sense.compass)) ? { heading: (Number(sense.compass) + decl + 360) % 360, alt: Number(sense.orientation?.pitch || 0), source: 'MapPI3 Sense HAT' } : null;

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [camera, setCamera] = useState('off');
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }, audio: false });
      streamRef.current = stream; if (videoRef.current) videoRef.current.srcObject = stream; setCamera('on');
    } catch (e) { setCamera(`blocked: ${e.message}`); }
  };
  const stopCamera = () => { streamRef.current?.getTracks().forEach(t => t.stop()); streamRef.current = null; setCamera('off'); };
  useEffect(() => () => streamRef.current?.getTracks().forEach(t => t.stop()), []);
  useEffect(() => { const onHide = () => { if (document.hidden) stopCamera(); }; document.addEventListener('visibilitychange', onHide); return () => document.removeEventListener('visibilitychange', onHide); }, []);

  const [target, setTarget] = useState(null);
  const visible = sky.objects.filter(o => o.alt > 0).sort((a, b) => a.mag - b.mag);
  const hidden = sky.objects.filter(o => o.alt <= 0 && o.kind !== 'constellation');
  const tgt = target && sky.objects.find(o => o.id === target);
  const hFov = 52, vFov = 68;
  const inView = pointing ? sky.objects.filter(o => o.alt > -3).map(o => ({ ...o, dx: wrap(o.az - pointing.heading), dy: o.alt - pointing.alt })).filter(o => Math.abs(o.dx) < hFov / 2 + 4 && Math.abs(o.dy) < vFov / 2 + 4) : [];
  const guide = tgt && pointing ? { turn: wrap(tgt.az - pointing.heading), tilt: tgt.alt - pointing.alt } : null;
  return <section className="panel sky-screen st-sky">
    <div className="section-head"><div><h2>Sky</h2><p className="muted">What's up right now from {place.label} ({place.lat.toFixed(2)}, {place.lon.toFixed(2)}). {sky.dark ? 'It is dark: good viewing.' : sky.twilight ? 'Twilight: bright stars and planets are showing.' : 'Daytime: only the Moon and Venus are easy to see.'}</p></div></div>
    <div className="st-sky-grid">
      <div className={`st-sky-view ${camera === 'on' ? 'cam' : ''}`}>
        <video ref={videoRef} autoPlay playsInline muted />
        <div className="st-sky-horizon" style={pointing ? { top: `${50 + (pointing.alt / vFov) * 100}%` } : { display: 'none' }}><span>horizon</span></div>
        {inView.map(o => <button key={o.id} type="button" className={`st-sky-obj k-${o.kind} ${o.id === target ? 'on' : ''}`} style={{ left: `${50 + (o.dx / hFov) * 100}%`, top: `${50 - (o.dy / vFov) * 100}%` }} onClick={() => setTarget(o.id)}><i /><span>{o.name}</span></button>)}
        <div className="st-sky-reticle" aria-hidden="true" />
        <div className="st-sky-hud">{pointing ? <><strong>{Math.round(pointing.heading)}° {cardinal(pointing.heading)}</strong><span>looking {pointing.alt >= 0 ? 'up' : 'down'} {Math.abs(Math.round(pointing.alt))}° · {pointing.source}</span></> : <span>Turn on motion sensors to aim the phone at the sky.</span>}</div>
        {guide && <div className="st-sky-guide">{Math.abs(guide.turn) < 4 && Math.abs(guide.tilt) < 4 ? <strong>{tgt.name} is right in the middle.</strong> : <><strong>{tgt.name}</strong><span>{Math.abs(guide.turn) >= 4 ? `turn ${guide.turn > 0 ? 'right' : 'left'} ${Math.abs(Math.round(guide.turn))}°` : 'straight ahead'} · {Math.abs(guide.tilt) >= 4 ? `look ${guide.tilt > 0 ? 'up' : 'down'} ${Math.abs(Math.round(guide.tilt))}°` : 'level'}</span></>}</div>}
        <div className="st-sky-actions">
          {needsTap && <button type="button" className="primary" onClick={askMotion}>Turn on motion sensors</button>}
          {camera === 'on' ? <button type="button" className="ghost" onClick={stopCamera}>Camera off</button> : <button type="button" className="primary" onClick={startCamera}>Camera view</button>}
        </div>
        {camera.startsWith('blocked') && <p className="st-sky-note">Camera {camera}. Allow camera access for this site in your browser settings, or use the sky map without the camera.</p>}
      </div>
      <div className="st-sky-side">
        <div className="st-label">Up now · tap to find</div>
        <div className="st-sky-list">{visible.map(o => <button key={o.id} type="button" className={o.id === target ? 'on' : ''} onClick={() => setTarget(o.id === target ? null : o.id)}><strong>{o.name}</strong><span>{cardinal(o.az)} · {Math.round(o.alt)}° up{o.kind === 'planet' ? ' · planet' : o.kind === 'moon' ? ' · moon' : ''}</span><small>{o.notes}</small></button>)}</div>
        {hidden.length > 0 && <details className="st-sky-below"><summary>Below the horizon now ({hidden.length})</summary><p className="muted">{hidden.map(o => o.name).join(', ')}</p></details>}
        <div className="st-sky-cal"><span>Magnetic declination {decl.toFixed(1)}° {settings.skyDeclination === undefined || settings.skyDeclination === 'auto' ? '(auto)' : '(set)'}</span>
          {setSettings && <select value={settings.skyDeclination ?? 'auto'} onChange={e => setSettings(s => ({ ...s, skyDeclination: e.target.value === 'auto' ? 'auto' : Number(e.target.value) }))}><option value="auto">Auto for this area</option>{Array.from({ length: 41 }, (_, i) => -20 + i).map(v => <option key={v} value={v}>{v}°</option>)}</select>}
          <small>Phone compasses read magnetic north; MapPI3 turns that into true north. Hold the phone away from metal and wave it in a figure-8 if the heading drifts.</small></div>
      </div>
    </div>
  </section>;
}
