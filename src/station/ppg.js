// Camera pulse (photoplethysmography). A fingertip over the rear camera, lit by the flash, gets a
// little darker each time a pulse of blood arrives. Averaging each frame's color gives a waveform.
//
// Heart rate: band-pass 0.7-3.5 Hz (42-210 bpm), then the spectral peak, refined by beat-to-beat
// intervals from peak detection. Breathing modulates that waveform three ways: baseline (RIIV),
// beat amplitude (RIAV) and beat timing (RIFV, sinus arrhythmia). Each is searched in 0.1-0.5 Hz
// (6-30 breaths/min) and they are fused only when they agree (Karlen et al., IEEE TBME 2013).
// A reading is an estimate for fitness tracking, not a medical device.

export const FS = 30;

// Is this frame a fingertip over a lit lens? Red dominates and the frame is fairly bright.
export function fingerOn({ r, g, b }) { return r > 70 && r > 1.5 * g && r > 1.5 * b; }

export function resample(samples, key, fs = FS) {
  if (samples.length < 2) return [];
  const t0 = samples[0].t, t1 = samples[samples.length - 1].t;
  const n = Math.floor(((t1 - t0) / 1000) * fs);
  const out = new Array(n);
  let j = 0;
  for (let i = 0; i < n; i++) {
    const t = t0 + (i * 1000) / fs;
    while (j < samples.length - 2 && samples[j + 1].t < t) j++;
    const a = samples[j], b = samples[j + 1];
    const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t);
    out[i] = a[key] + (b[key] - a[key]) * Math.max(0, Math.min(1, f));
  }
  return out;
}

// RBJ biquads, run forward and backward so the waveform is not shifted in time.
function biquad(type, fc, fs, q = Math.SQRT1_2) {
  const w = (2 * Math.PI * fc) / fs, c = Math.cos(w), al = Math.sin(w) / (2 * q);
  const b = type === 'low' ? [(1 - c) / 2, 1 - c, (1 - c) / 2] : [(1 + c) / 2, -(1 + c), (1 + c) / 2];
  const a0 = 1 + al;
  return { b: b.map(v => v / a0), a: [(-2 * c) / a0, (1 - al) / a0] };
}
function run({ b, a }, x) {
  const y = new Array(x.length);
  let x1 = x[0], x2 = x[0], y1 = x[0] * (b[0] + b[1] + b[2]) / (1 + a[0] + a[1]), y2 = y1;
  for (let i = 0; i < x.length; i++) { const v = b[0] * x[i] + b[1] * x1 + b[2] * x2 - a[0] * y1 - a[1] * y2; x2 = x1; x1 = x[i]; y2 = y1; y1 = v; y[i] = v; }
  return y;
}
const filtfilt = (f, x) => run(f, run(f, x).reverse()).reverse();
export function bandpass(x, lo, hi, fs = FS) {
  const m = x.reduce((s, v) => s + v, 0) / (x.length || 1);
  let y = x.map(v => v - m);
  y = filtfilt(biquad('high', lo, fs), y);
  y = filtfilt(biquad('high', lo, fs), y);
  y = filtfilt(biquad('low', hi, fs), y);
  return filtfilt(biquad('low', hi, fs), y);
}

// Power over a fine frequency grid (a direct DFT is cheap at these sizes), Hann windowed.
function spectrum(x, fs, lo, hi, step) {
  const n = x.length, w = x.map((v, i) => v * (0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1))));
  const out = [];
  for (let f = lo; f <= hi + 1e-9; f += step) {
    let re = 0, im = 0; const k = (2 * Math.PI * f) / fs;
    for (let i = 0; i < n; i++) { re += w[i] * Math.cos(k * i); im -= w[i] * Math.sin(k * i); }
    out.push({ f, p: re * re + im * im });
  }
  return out;
}
// share = fraction of band power near the peak (and, with harmonics, near 2f and 3f: a pulse is not
// a sine, so a slow heart puts real power in its harmonics).
function peakOf(spec, bw, harmonics = false) {
  let best = 0;
  for (let i = 1; i < spec.length; i++) if (spec[i].p > spec[best].p) best = i;
  const total = spec.reduce((s, v) => s + v.p, 0) || 1;
  const f0 = spec[best].f, hs = harmonics ? [f0, 2 * f0, 3 * f0] : [f0];
  const near = spec.filter(v => hs.some(h => Math.abs(v.f - h) <= bw)).reduce((s, v) => s + v.p, 0);
  let f = spec[best].f;
  if (best > 0 && best < spec.length - 1) { const [a, b, c] = [spec[best - 1].p, spec[best].p, spec[best + 1].p]; const d = a - 2 * b + c; if (d) f += (0.5 * (a - c) / d) * (spec[1].f - spec[0].f); }
  return { f, share: near / total };
}

// Beats: local maxima at least 60% of the dominant period apart, above the local noise floor.
function beats(y, fs, hz) {
  const minGap = Math.max(1, Math.floor((0.6 * fs) / hz));
  const idx = [];
  for (let i = 1; i < y.length - 1; i++) {
    if (y[i] > 0 && y[i] >= y[i - 1] && y[i] > y[i + 1]) {
      if (idx.length && i - idx[idx.length - 1] < minGap) { if (y[i] > y[idx[idx.length - 1]]) idx[idx.length - 1] = i; }
      else idx.push(i);
    }
  }
  return idx;
}
const median = a => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : NaN; };

// A beat-synchronous series (value at each beat time) resampled to 4 Hz for breathing analysis.
function beatSeries(times, values, fs = 4) {
  const pts = times.map((t, i) => ({ t: t * 1000, v: values[i] }));
  return resample(pts, 'v', fs);
}
function breathFrom(series, fs) {
  if (series.length < fs * 20) return null;
  // Interpolating between beats tilts noise toward low frequencies; the first difference flattens it
  // again so slow noise does not pull the estimate down.
  const y = bandpass(series, 0.08, 0.6, fs);
  const d = y.slice(1).map((v, i) => v - y[i]);
  const spec = spectrum(d, fs, 0.1, 0.5, 0.005);
  const pk = peakOf(spec, 0.03);
  return { bpm: pk.f * 60, share: pk.share };
}

// Analyse a recording. samples: [{ t: ms, r, g, b }] with the finger on.
export function analyse(samples) {
  const seconds = samples.length > 1 ? (samples[samples.length - 1].t - samples[0].t) / 1000 : 0;
  if (seconds < 10) return { ok: false, reason: 'Need at least 10 seconds of steady contact.' };
  // Brighter frames = less blood, so flip the sign: beats become peaks.
  const tryChannel = key => {
    const raw = resample(samples, key).map(v => -v);
    const y = bandpass(raw, 0.5, 3.5);
    const spec = spectrum(y, FS, 0.6, 3.5, 0.01);
    let pk = peakOf(spec, 0.12, true);
    // A slow pulse with a strong dicrotic notch can show its 2nd harmonic as the tallest peak.
    // Prefer half the frequency when there is real power there too.
    const at = f => spec.reduce((m, v) => (Math.abs(v.f - f) <= 0.04 ? Math.max(m, v.p) : m), 0);
    const top = at(pk.f);
    if (pk.f / 2 >= 0.6 && at(pk.f / 2) > 0.25 * top) {
      const sub = peakOf(spec.filter(v => Math.abs(v.f - pk.f / 2) <= 0.1), 0.12);
      pk = { f: sub.f, share: 0 };
      const hs = [pk.f, 2 * pk.f, 3 * pk.f], total = spec.reduce((q, v) => q + v.p, 0) || 1;
      pk.share = spec.filter(v => hs.some(h => Math.abs(v.f - h) <= 0.12)).reduce((q, v) => q + v.p, 0) / total;
    }
    return { key, raw, y, pk };
  };
  const ch = [tryChannel('r'), tryChannel('g')].sort((a, b) => b.pk.share - a.pk.share)[0];
  const { raw, y, pk } = ch;
  const idx = beats(y, FS, pk.f);
  const ibis = idx.slice(1).map((v, i) => (v - idx[i]) / FS);
  const expected = 1 / pk.f;
  const clean = ibis.filter(v => Math.abs(v - expected) / expected < 0.3);
  const ibiBpm = clean.length >= 5 ? 60 / median(clean) : null;
  const bpm = ibiBpm && Math.abs(ibiBpm - pk.f * 60) < 8 ? (ibiBpm + pk.f * 60) / 2 : pk.f * 60;
  const regular = ibis.length ? clean.length / ibis.length : 0;
  // RMSSD from consecutive clean intervals, in ms.
  let ss = 0, nn = 0;
  for (let i = 1; i < ibis.length; i++) { const a = ibis[i - 1], b = ibis[i]; if (Math.abs(a - expected) / expected < 0.3 && Math.abs(b - expected) / expected < 0.3) { ss += ((b - a) * 1000) ** 2; nn++; } }
  const rmssd = nn >= 10 ? Math.sqrt(ss / nn) : null; // reported only for good signals, noise inflates it
  const quality = pk.share > 0.45 && regular > 0.8 ? 'good' : pk.share > 0.25 && regular > 0.6 ? 'fair' : 'poor';

  // Breathing, only from 40 s or more of good signal (at least ~6 breaths).
  let breath = null;
  if (seconds >= 40 && quality !== 'poor' && idx.length > 20) {
    const t = idx.map(i => i / FS);
    const troughAt = i => { let m = y[i]; for (let k = Math.max(0, i - Math.round(FS * expected * 0.6)); k < i; k++) m = Math.min(m, y[k]); return m; };
    const base = bandpass(raw, 0.08, 0.6, FS);
    const est = [
      ['baseline', breathFrom(beatSeries(t, idx.map(i => base[i])), 4)],
      ['amplitude', breathFrom(beatSeries(t, idx.map(i => y[i] - troughAt(i))), 4)],
      ['timing', breathFrom(beatSeries(t.slice(1), ibis), 4)]
    ].filter(([, e]) => e && e.share > 0.2);
    if (est.length) {
      const rates = est.map(([, e]) => e.bpm);
      const mean = rates.reduce((s, v) => s + v, 0) / rates.length;
      const spread = Math.sqrt(rates.reduce((s, v) => s + (v - mean) ** 2, 0) / rates.length);
      const best = est.slice().sort((a, b) => b[1].share - a[1].share)[0];
      breath = est.length >= 2 && spread <= 4
        ? { perMin: mean, confidence: est.length === 3 ? 'good' : 'fair', methods: est.map(e => e[0]) }
        : { perMin: best[1].bpm, confidence: 'low', methods: [best[0]] };
    }
  }
  if (breath && quality === 'fair' && breath.confidence === 'good') breath.confidence = 'fair';
  return { ok: quality !== 'poor', bpm: Math.round(bpm), quality, seconds: Math.round(seconds), beats: idx.length, rmssd: quality === 'good' && rmssd ? Math.round(rmssd) : null, channel: ch.key, breath: breath && { ...breath, perMin: Math.round(breath.perMin) }, reason: quality === 'poor' ? 'The signal was too noisy. Keep your fingertip still and covering the lens and flash.' : '' };
}

// Filtered tail for the live trace (last few seconds).
export function liveTrace(samples, seconds = 6) {
  if (samples.length < FS * 3) return [];
  const tail = samples.slice(-Math.round(FS * (seconds + 3)));
  const y = bandpass(resample(tail, 'r').map(v => -v), 0.7, 3.5);
  return y.slice(-FS * seconds);
}
export function quickBpm(samples) {
  if (samples.length < FS * 8) return null;
  const tail = samples.slice(-FS * 12);
  const y = bandpass(resample(tail, 'r').map(v => -v), 0.5, 3.5);
  const pk = peakOf(spectrum(y, FS, 0.7, 3.5, 0.02), 0.12);
  return pk.share > 0.3 ? Math.round(pk.f * 60) : null;
}
