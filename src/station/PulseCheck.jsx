import React, { useEffect, useRef, useState } from 'react';
import { analyse, fingerOn, liveTrace, quickBpm } from './ppg.js';

// Pulse check with the phone's rear camera and flash. Hold a fingertip over both, keep still,
// breathe normally. 30 s gives heart rate, 60 s adds breathing rate and heart-rate variability.
const LENGTHS = [[30, 'Heart rate · 30 s'], [60, 'Heart + breathing · 60 s']];
const CONTEXTS = ['Resting', 'Just woke up', 'After a hike', 'On the trail'];

export default function PulseCheck({ hiker = {}, setHiker }) {
  const [length, setLength] = useState(60);
  const [context, setContext] = useState('Resting');
  const [state, setState] = useState('idle'); // idle | starting | waiting | measuring | done | error
  const [msg, setMsg] = useState('');
  const [live, setLive] = useState({ secs: 0, bpm: null, trace: [] });
  const [result, setResult] = useState(null);
  const [torch, setTorch] = useState(null);
  const videoRef = useRef(null), streamRef = useRef(null), samplesRef = useRef([]), stopRef = useRef(false), offSinceRef = useRef(0);
  const vitals = hiker.vitals || [];

  const stop = () => {
    stopRef.current = true;
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  };
  useEffect(() => stop, []);

  const start = async () => {
    setResult(null); setMsg(''); samplesRef.current = []; stopRef.current = false; offSinceRef.current = 0;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { setState('error'); setMsg('The camera only works over https. Open the app from its web address (not the Pi hotspot http page) to measure.'); return; }
    setState('starting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 320 }, height: { ideal: 240 }, frameRate: { ideal: 30 } }, audio: false });
      streamRef.current = stream;
      const track = stream.getVideoTracks()[0];
      let lit = false;
      try { if (track.getCapabilities?.().torch) { await track.applyConstraints({ advanced: [{ torch: true }] }); lit = true; } } catch { lit = false; }
      setTorch(lit);
      const v = videoRef.current; v.srcObject = stream; await v.play();
      setState('waiting');
      const cv = document.createElement('canvas'); cv.width = 40; cv.height = 30;
      const ctx = cv.getContext('2d', { willReadFrequently: true });
      let lastUi = 0;
      const frame = (now) => {
        if (stopRef.current) return;
        ctx.drawImage(v, 0, 0, 40, 30);
        const d = ctx.getImageData(0, 0, 40, 30).data;
        let r = 0, g = 0, b = 0; const n = d.length / 4;
        for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; }
        const px = { t: now, r: r / n, g: g / n, b: b / n };
        const s = samplesRef.current;
        if (fingerOn(px)) {
          offSinceRef.current = 0;
          s.push(px);
        } else if (s.length) {
          // A short slip is tolerated; a longer one starts the count again so the waveform stays clean.
          offSinceRef.current ||= now;
          if (now - offSinceRef.current > 800) samplesRef.current = [];
        }
        const secs = s.length > 1 ? (s[s.length - 1].t - s[0].t) / 1000 : 0;
        if (now - lastUi > 250) {
          lastUi = now;
          setState(s.length ? 'measuring' : 'waiting');
          setLive({ secs, bpm: quickBpm(s), trace: liveTrace(s) });
        }
        if (secs >= length) { finish(); return; }
        if (v.requestVideoFrameCallback) v.requestVideoFrameCallback((t) => frame(t)); else requestAnimationFrame(frame);
      };
      if (v.requestVideoFrameCallback) v.requestVideoFrameCallback((t) => frame(t)); else requestAnimationFrame(frame);
    } catch (e) {
      stop(); setState('error');
      setMsg(/denied|NotAllowed/i.test(String(e?.name || e)) ? 'Camera permission was blocked. Allow the camera for this site in your browser settings, then try again.' : `Could not start the camera: ${e?.message || e}`);
    }
  };

  const finish = () => {
    const r = analyse(samplesRef.current);
    stop();
    setResult(r); setState('done');
    if (r.ok && setHiker) {
      const entry = { id: `vital-${Date.now()}`, at: Date.now(), bpm: r.bpm, breathsPerMin: r.breath?.perMin ?? null, breathConfidence: r.breath?.confidence || null, rmssd: r.rmssd, quality: r.quality, seconds: r.seconds, context, source: 'phone camera' };
      setHiker(h => ({ ...h, heartRate: r.bpm, vitals: [entry, ...(h.vitals || [])].slice(0, 300) }));
    }
  };
  const cancel = () => { stop(); setState('idle'); };

  const busy = state === 'starting' || state === 'waiting' || state === 'measuring';
  const pct = Math.min(1, live.secs / length);
  const path = (() => {
    const t = live.trace; if (t.length < 2) return '';
    const lo = Math.min(...t), hi = Math.max(...t), span = hi - lo || 1;
    return t.map((v, i) => `${i ? 'L' : 'M'}${((i / (t.length - 1)) * 300).toFixed(1)} ${(54 - ((v - lo) / span) * 48).toFixed(1)}`).join(' ');
  })();
  const resting = vitals.filter(v => /rest|woke/i.test(v.context || '')).slice(0, 14);
  const restAvg = resting.length ? Math.round(resting.reduce((a, v) => a + v.bpm, 0) / resting.length) : null;

  return <div className="st-card pulse-check">
    <div className="pc-head"><div><div className="st-label">Pulse check · phone camera</div><p className="muted">Cover the rear camera and flash with a fingertip. Rest your hand on something, keep still and breathe normally.</p></div>
      {restAvg && <div className="pc-rest"><b>{restAvg}</b><span>avg resting bpm</span></div>}
    </div>
    <video ref={videoRef} playsInline muted className="pc-video" />
    {!busy && state !== 'done' && <div className="pc-setup">
      <div className="pc-seg">{LENGTHS.map(([s, l]) => <button key={s} type="button" className={length === s ? 'on' : ''} onClick={() => setLength(s)}>{l}</button>)}</div>
      <label className="pc-ctx">When <select value={context} onChange={e => setContext(e.target.value)}>{CONTEXTS.map(c => <option key={c}>{c}</option>)}</select></label>
      <button type="button" className="primary" onClick={start}>Start measuring</button>
    </div>}
    {busy && <div className="pc-live">
      <svg viewBox="0 0 300 60" className="pc-trace" role="img" aria-label="Live pulse waveform"><path d={path} fill="none" stroke="var(--st-bad, #c2410c)" strokeWidth="2.2" strokeLinejoin="round" /></svg>
      <div className="pc-read"><strong>{state === 'measuring' && live.bpm ? live.bpm : '--'}</strong><span>bpm</span></div>
      <div className="pc-bar"><i style={{ width: `${Math.round(pct * 100)}%` }} /></div>
      <p className="muted">{state === 'starting' ? 'Starting the camera…' : state === 'waiting' ? 'Place your fingertip over the camera and flash.' : `${Math.round(live.secs)} of ${length} s · keep still`}{torch === false ? ' Your browser cannot turn on the flash, so measure in bright light.' : ''}</p>
      <button type="button" className="ghost" onClick={cancel}>Cancel</button>
    </div>}
    {state === 'done' && result && <div className="pc-result">
      {result.ok ? <>
        <div className="pc-nums">
          <div><strong>{result.bpm}</strong><span>bpm heart rate</span></div>
          <div><strong>{result.breath ? result.breath.perMin : '—'}</strong><span>breaths / min{result.breath ? ` · ${result.breath.confidence} confidence` : length < 40 ? ' · needs 60 s' : ''}</span></div>
          <div><strong>{result.rmssd ?? '—'}</strong><span>HRV (RMSSD, ms)</span></div>
        </div>
        <p className="muted">Signal {result.quality} · {result.beats} beats over {result.seconds} s · {context.toLowerCase()}. Saved to your health log.</p>
        {result.bpm > 100 && /rest|woke/i.test(context) && <p className="pc-flag">A resting pulse over 100 is higher than usual. Sit for 5 minutes and measure again. If it stays high or you feel unwell, check with a clinician.</p>}
        {result.breath?.perMin > 24 && /rest|woke/i.test(context) && <p className="pc-flag">That breathing rate is fast for rest (typical adults breathe 12 to 20 times a minute). Measure again after sitting quietly.</p>}
      </> : <p className="pc-flag">{result.reason || 'Could not get a clean reading.'}</p>}
      <div className="dh-btns"><button type="button" className="primary" onClick={start}>Measure again</button><button type="button" className="ghost" onClick={() => setState('idle')}>Done</button></div>
    </div>}
    {state === 'error' && <p className="pc-flag">{msg}</p>}
    {vitals.length > 0 && <div className="pc-hist"><div className="st-label">Recent readings</div>
      {vitals.slice(0, 6).map(v => <div key={v.id}><span>{new Date(v.at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span><small>{v.context}</small><b>{v.bpm} bpm{v.breathsPerMin ? ` · ${v.breathsPerMin} br/min` : ''}</b></div>)}
    </div>}
    <p className="dh-note">Camera readings are estimates for fitness tracking, not a medical device. Accuracy drops with movement, cold fingers or dim light.</p>
  </div>;
}
