import React, { useEffect, useRef } from 'react';

// Background effects behind the page: rain, snow, fog, sun glow, drifting leaves, fireflies.
// Battery rules: capped at ~24 fps, pixel ratio capped at 1.5, particle count scaled to the screen,
// paused while the tab is hidden, and a single still frame when the device asks for reduced motion.
const leafColors = {
  spring: ['#8fbf5a', '#b7d67a', '#e8a8b8'],
  summer: ['#4f8a3a', '#6fa84a', '#3d6e2e'],
  autumn: ['#c8641e', '#d9a441', '#a23b1f', '#e0842f'],
  winter: ['#9fb4c0', '#c9d6de', '#7d8f99']
};

export default function AmbientLayer({ effect = 'none', season = 'autumn', night = false, intensity = 1 }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || effect === 'none') return undefined;
    const ctx = canvas.getContext('2d');
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const dpr = Math.min(1.5, window.devicePixelRatio || 1);
    let W = 0, H = 0, raf = 0, last = 0, parts = [];
    const area = () => (W * H) / (1280 * 800);
    const make = () => {
      const n = Math.round(({ rain: 90, storm: 140, snow: 70, leaves: 18, fireflies: 22, fog: 5, sun: 1 }[effect] || 0) * Math.min(1.6, Math.max(0.35, area())) * intensity);
      parts = Array.from({ length: n }, () => spawn(true));
    };
    const spawn = (anywhere) => {
      const x = Math.random() * W, y = anywhere ? Math.random() * H : -20;
      if (effect === 'rain' || effect === 'storm') return { x, y, v: 9 + Math.random() * 7, l: 10 + Math.random() * 14 };
      if (effect === 'snow') return { x, y, v: 0.6 + Math.random() * 1.2, r: 1 + Math.random() * 2.4, p: Math.random() * 6.28 };
      if (effect === 'leaves') { const cols = leafColors[season] || leafColors.autumn; return { x, y, v: 0.5 + Math.random() * 0.9, r: 5 + Math.random() * 6, a: Math.random() * 6.28, s: (Math.random() - 0.5) * 0.04, p: Math.random() * 6.28, c: cols[Math.floor(Math.random() * cols.length)] }; }
      if (effect === 'fireflies') return { x, y: Math.random() * H, vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.3, p: Math.random() * 6.28 };
      if (effect === 'fog') return { x: Math.random() * W, y: H * (0.2 + Math.random() * 0.7), r: 180 + Math.random() * 260, v: 0.12 + Math.random() * 0.2 };
      return { x: W * 0.85, y: H * 0.08 };
    };
    const resize = () => {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      make();
    };
    let flash = 0;
    const draw = (t) => {
      ctx.clearRect(0, 0, W, H);
      if (effect === 'rain' || effect === 'storm') {
        ctx.strokeStyle = night ? 'rgba(255,190,110,.22)' : 'rgba(40,70,90,.28)'; ctx.lineWidth = 1.1; ctx.beginPath();
        parts.forEach(p => { ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - 2, p.y + p.l); p.y += p.v; p.x -= 0.6; if (p.y > H) Object.assign(p, spawn(false)); });
        ctx.stroke();
        if (effect === 'storm') { if (flash > 0) { ctx.fillStyle = `rgba(255,255,255,${flash * 0.18})`; ctx.fillRect(0, 0, W, H); flash -= 0.08; } else if (Math.random() < 0.0025) flash = 1; }
      } else if (effect === 'snow') {
        ctx.fillStyle = night ? 'rgba(255,220,170,.55)' : 'rgba(255,255,255,.9)';
        parts.forEach(p => { ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.28); ctx.fill(); p.p += 0.02; p.y += p.v; p.x += Math.sin(p.p) * 0.5; if (p.y > H + 5) Object.assign(p, spawn(false)); });
      } else if (effect === 'leaves') {
        parts.forEach(p => {
          ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.a); ctx.globalAlpha = night ? 0.35 : 0.55; ctx.fillStyle = p.c;
          ctx.beginPath(); ctx.moveTo(0, -p.r); ctx.quadraticCurveTo(p.r * 0.9, 0, 0, p.r); ctx.quadraticCurveTo(-p.r * 0.9, 0, 0, -p.r); ctx.fill();
          ctx.strokeStyle = 'rgba(0,0,0,.18)'; ctx.lineWidth = 0.8; ctx.beginPath(); ctx.moveTo(0, -p.r); ctx.lineTo(0, p.r); ctx.stroke(); ctx.restore();
          p.p += 0.015; p.y += p.v; p.x += Math.sin(p.p) * 0.8 + 0.25; p.a += p.s;
          if (p.y > H + 20 || p.x > W + 20) Object.assign(p, spawn(false));
        });
      } else if (effect === 'fireflies') {
        parts.forEach(p => { p.p += 0.04; p.x += p.vx + Math.sin(p.p) * 0.2; p.y += p.vy + Math.cos(p.p * 0.7) * 0.15; if (p.x < 0 || p.x > W || p.y < 0 || p.y > H) Object.assign(p, spawn(true)); const g = Math.max(0, Math.sin(p.p)); ctx.fillStyle = `rgba(255,${night ? 190 : 214},90,${0.15 + g * 0.6})`; ctx.beginPath(); ctx.arc(p.x, p.y, 1.6 + g * 1.4, 0, 6.28); ctx.fill(); });
      } else if (effect === 'fog') {
        parts.forEach(p => { const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r); g.addColorStop(0, night ? 'rgba(90,70,40,.16)' : 'rgba(255,255,255,.42)'); g.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = g; ctx.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2); p.x += p.v; if (p.x - p.r > W) p.x = -p.r; });
      } else if (effect === 'sun') {
        const p = parts[0] || spawn(true); const pulse = 0.85 + Math.sin(t / 2400) * 0.15;
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, Math.max(W, H) * 0.55 * pulse); g.addColorStop(0, 'rgba(255,214,120,.32)'); g.addColorStop(1, 'rgba(255,214,120,0)'); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      }
    };
    const loop = (t) => { raf = requestAnimationFrame(loop); if (t - last < 42) return; last = t; draw(t); };
    const onVis = () => { cancelAnimationFrame(raf); if (!document.hidden && !reduce) raf = requestAnimationFrame(loop); };
    resize();
    if (reduce) draw(0); else raf = requestAnimationFrame(loop);
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', onVis);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); document.removeEventListener('visibilitychange', onVis); };
  }, [effect, season, night, intensity]);
  if (effect === 'none') return null;
  return <canvas ref={ref} className="st-ambient" aria-hidden="true" />;
}

// A still treeline along the bottom of the page for the Forest look.
export function ForestSilhouette() {
  const trees = [];
  for (let i = 0; i < 46; i += 1) {
    const x = i * 44 + (i % 3) * 9, h = 70 + ((i * 37) % 60), w = 26 + ((i * 13) % 14);
    trees.push(`M${x} 200 L${x + w / 2} ${200 - h} L${x + w} 200 Z`);
  }
  const back = trees.map((d, i) => d.replace(/(\d+(?:\.\d+)?) (\d+(?:\.\d+)?)/g, (m, a, b) => `${Number(a) + 18} ${Math.min(200, Number(b) + 26)}`)).join(' ');
  return <svg className="st-forest" viewBox="0 0 2000 200" preserveAspectRatio="xMidYMax slice" aria-hidden="true"><path d={back} className="st-forest-back" /><path d={trees.join(' ')} className="st-forest-front" /></svg>;
}
