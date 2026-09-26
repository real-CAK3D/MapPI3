import React, { useEffect, useRef, useState } from 'react';
import { waypointKind } from './ElevationProfile.jsx';

// Hey Herbie: answers trail questions from the app's real data (route, waypoints, GPS, weather,
// Pi sensors). No network model is needed, so it works offline on the MapPI3 hotspot.
const clock = d => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const mins = m => { m = Math.max(0, Math.round(m)); const h = Math.floor(m / 60); return h ? `${h} hour${h > 1 ? 's' : ''}${m % 60 ? ` ${m % 60} minutes` : ''}` : `${m} minute${m === 1 ? '' : 's'}`; };
const pick = arr => arr[Math.floor(Math.random() * arr.length)];

export function answerHerbie(question, ctx) {
  const q = String(question || '').toLowerCase().replace(/^(hey|ok|okay)?\s*herbie[,!.\s]*/, '').trim();
  const now = new Date();
  const route = ctx.route;
  const total = Number(route?.distanceMiles || route?.miles || 0);
  const you = total ? Math.max(0, Math.min(total, Number(ctx.progress || 0) * total)) : 0;
  const pace = Number(ctx.paceMph || 2);
  const wps = [...(route?.waypoints || []), ...(route?.customWaypoints || [])].filter(w => Number.isFinite(Number(w.mile))).map(w => ({ ...w, mile: Number(w.mile), kind: waypointKind(w, route?.name) })).sort((a, b) => a.mile - b.mile);
  const ahead = kind => wps.find(w => w.mile > you + 0.02 && (!kind || w.kind === kind));
  const behind = kind => [...wps].reverse().find(w => w.mile <= you + 0.02 && w.kind === kind);
  const eta = miles => mins((miles / pace) * 60);
  const noRoute = "We don't have a trail picked yet. Choose one in Explore and I'll know every stop on it.";
  const g = ctx.piLive?.gps || {}, s = ctx.piLive?.sense || {}, p = ctx.piLive?.power || {};
  const c = ctx.conditions || {};

  if (!q || /^(hi|hello|hey|yo|sup|what'?s up)\b/.test(q)) return pick(['Hey! Ready when you are.', "Herbie here. What do you need?", "Hi! Ask me about water, sunset, miles left, or the weather."]);
  if (/who are you|your name|what are you/.test(q)) return "I'm Herbie, your trail buddy. I live on the MapPI3 and keep an eye on the map, the sky and your snacks.";
  if (/thank/.test(q)) return pick(["Anytime!", "That's what trail buddies are for.", "You got it."]);
  if (/joke|funny/.test(q)) return pick(["Why did the hiker bring a pencil? To draw a better trail.", "I'd tell you a trail joke, but I'm still working my way up to the punchline.", "What do you call a sleeping bag? A nap sack."]);
  if (/what time|time is it|the time/.test(q)) return `It's ${clock(now)}.`;
  if (/what day|date|today/.test(q) && !/hike/.test(q)) return `Today is ${now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}.${ctx.calendar?.reason ? ` ${ctx.calendar.reason}.` : ''}`;
  if (/sunset|dark|daylight|light left|sun go/.test(q)) {
    if (!ctx.sunset) return "I can't work out sunset without a location.";
    const left = (ctx.sunset - now) / 60000;
    return left > 0 ? `Sunset is at ${clock(ctx.sunset)}, about ${mins(left)} from now.${route && total - you > 0 && (total - you) / pace * 60 > left ? ' That is less time than the trail needs, so bring the headlamp.' : ''}` : `The sun set at ${clock(ctx.sunset)}. Headlamp time.`;
  }
  if (/sunrise|sun come up/.test(q)) return ctx.sunrise ? `Sunrise is at ${clock(ctx.sunrise)}.` : "I can't work out sunrise without a location.";
  if (/water|drink|refill|thirsty|stream|creek|brook|spring/.test(q)) {
    if (!route) return noRoute;
    const w = ahead('water'), b = behind('water');
    if (w) return `${w.name} is ${(w.mile - you).toFixed(1)} miles ahead, about ${eta(w.mile - you)} at your pace.${b && you - b.mile < w.mile - you ? ` ${b.name} is closer, ${(you - b.mile).toFixed(1)} miles back.` : ''}`;
    if (b) return `No more marked water ahead. The last one was ${b.name}, ${(you - b.mile).toFixed(1)} miles back.`;
    return "This trail has no marked water. Ration what you carry.";
  }
  if (/camp|shelter|sleep|tent/.test(q)) { if (!route) return noRoute; const w = ahead('camp'); return w ? `${w.name} is ${(w.mile - you).toFixed(1)} miles ahead, about ${eta(w.mile - you)}.` : 'No marked camp or shelter ahead on this trail.'; }
  if (/view|scenic|overlook|summit|top|peak/.test(q)) { if (!route) return noRoute; const w = ahead('view'); return w ? `${w.name} is ${(w.mile - you).toFixed(1)} miles ahead, about ${eta(w.mile - you)}. Binoculars ready.` : 'No more marked viewpoints ahead, but keep looking around.'; }
  if (/how far|miles left|remaining|how much longer|to go|finish|the end|done yet|are we there/.test(q)) {
    if (!route) return noRoute;
    const left = total - you;
    return left <= 0.05 ? "We're there! Nice work." : `${left.toFixed(1)} miles to go on ${route.name}, about ${eta(left)}${ctx.sunset ? `, so you'd finish around ${clock(new Date(now.getTime() + (left / pace) * 3600000))}` : ''}.`;
  }
  if (/next (stop|waypoint|marker)|what'?s next|coming up/.test(q)) { if (!route) return noRoute; const w = ahead(); return w ? `Next up is ${w.name}, ${(w.mile - you).toFixed(1)} miles ahead.` : 'Nothing else marked. Just the finish.'; }
  if (/off (the )?trail|on (the )?trail|lost|am i on/.test(q)) {
    if (!Number.isFinite(ctx.offTrailM)) return "I need a GPS fix to tell. Start the hike on the Navigate page.";
    return ctx.offTrailM > (ctx.offTrailLimitM || 15) ? `You're about ${Math.round(ctx.offTrailM)} meters off the trail. Head back toward the line on the map.` : `You're on the trail, ${Math.round(ctx.offTrailM)} meters from the centerline.`;
  }
  if (/where am i|location|coordinates|gps/.test(q)) {
    if (g.fix) return `You're at ${Number(g.lat).toFixed(5)}, ${Number(g.lon).toFixed(5)}${route ? `, mile ${you.toFixed(1)} of ${route.name}` : ''}. ${g.satellites || 0} satellites locked.`;
    return `No GPS fix right now${g.satellites ? `, I can see ${g.satellites} satellites` : ''}. Find some open sky.`;
  }
  if (/which way|north|heading|compass|direction/.test(q)) return s.ok && Number.isFinite(Number(s.compass)) ? `You're facing ${Math.round(Number(s.compass))} degrees, ${s.compass_cardinal || ''}.` : "My compass isn't reporting right now.";
  if (/elevation|altitude|how high/.test(q)) return Number.isFinite(Number(g.alt)) ? `We're at about ${Math.round(Number(g.alt) * 3.28084).toLocaleString()} feet.` : "I need a GPS fix with altitude for that.";
  if (/battery|charge|power/.test(q)) return Number.isFinite(Number(p.percent)) && p.percent !== null ? `My battery is at ${Math.round(p.percent)} percent${p.charging ? ' and charging' : ''}.` : "I can't read my battery right now. The PiSugar may be off.";
  if (/weather|rain|temperature|cold|hot|warm|storm|forecast/.test(q)) {
    if (!Number.isFinite(Number(c.tempF))) return "I don't have weather yet.";
    const soon = (c.hourly || []).slice(0, 6);
    const rain = soon.length ? Math.max(...soon.map(h => Number(h.precip || 0))) : null;
    return `It's ${Math.round(c.tempF)}°F with ${c.humidity ?? '?'}% humidity.${rain !== null ? ` Rain chance over the next few hours tops out at ${rain}%.` : ''}${/storm/.test(q) && rain !== null && rain < 30 ? ' No storms showing.' : ''}`;
  }
  if (/next hike|when.*hike|hike.*when|plan/.test(q)) return route && ctx.launchPlan?.hikeDate ? `${route.name}, planned for ${new Date(`${ctx.launchPlan.hikeDate}T12:00:00`).toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' })}.` : 'No hike date set yet. Pick one on the hike plan.';
  if (/food|eat|snack|hungry|lunch/.test(q)) return now.getHours() >= 11 && now.getHours() <= 13 ? "It's lunchtime. Find a rock with a view and eat something." : 'Snack every hour or so on the trail. Log it in Health so I can track your calories.';
  return "I don't know that one yet. Try asking about water, sunset, miles left, the weather, or the time.";
}

export default function HeyHerbiePanel({ onClose, faceUrl, ctx }) {
  const [log, setLog] = useState([{ who: 'herbie', text: "Hey! What do you want to know?" }]);
  const [text, setText] = useState('');
  const [listening, setListening] = useState(false);
  const [piVoice, setPiVoice] = useState(() => { try { return localStorage.getItem('mappi3.herbieVoicePi') === 'true'; } catch { return false; } });
  const recRef = useRef(null);
  const endRef = useRef(null);
  const Rec = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [log]);
  useEffect(() => { try { localStorage.setItem('mappi3.herbieVoicePi', String(piVoice)); } catch { /* ignore */ } }, [piVoice]);
  useEffect(() => { const onKey = e => { if (e.key === 'Escape') onClose(); }; window.addEventListener('keydown', onKey); return () => { window.removeEventListener('keydown', onKey); recRef.current?.abort?.(); }; }, []);
  const speak = (reply) => {
    try { if (window.speechSynthesis) { window.speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(reply); u.rate = 1.03; u.pitch = 1.15; window.speechSynthesis.speak(u); } } catch { /* no local voice */ }
    if (piVoice) fetch('/api/command/audio-tts-test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: reply }) }).catch(() => {});
  };
  const ask = (q) => {
    const question = String(q || '').trim();
    if (!question) return;
    const reply = answerHerbie(question, ctx);
    setLog(l => [...l, { who: 'me', text: question }, { who: 'herbie', text: reply }].slice(-30));
    setText('');
    speak(reply);
  };
  const listen = () => {
    if (!Rec) return;
    if (listening) { recRef.current?.stop(); return; }
    const rec = new Rec();
    rec.lang = navigator.language || 'en-US';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = e => ask(e.results[0][0].transcript);
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  };
  const quick = ['How far to water?', 'When is sunset?', 'How far is left?', "What's the weather?", 'What time is it?', 'Am I on the trail?'];
  return <div className="hh-backdrop" onClick={onClose}>
    <section className="hh-panel" role="dialog" aria-label="Hey Herbie" onClick={e => e.stopPropagation()}>
      <header className="hh-head"><img src={faceUrl(listening ? 'curious' : 'happy')} alt="" /><div><h2>Hey Herbie</h2><p>Answers from your trail, GPS and weather. Works offline.</p></div><button type="button" className="ghost small" onClick={onClose}>Close</button></header>
      <div className="hh-log" aria-live="polite">{log.map((m, i) => <div key={i} className={`hh-msg ${m.who}`}>{m.text}</div>)}<div ref={endRef} /></div>
      <div className="hh-quick">{quick.map(qq => <button key={qq} type="button" onClick={() => ask(qq)}>{qq}</button>)}</div>
      <form className="hh-input" onSubmit={e => { e.preventDefault(); ask(text); }}>
        <label className="sr-only" htmlFor="hh-q">Ask Herbie</label>
        <input id="hh-q" value={text} onChange={e => setText(e.target.value)} placeholder="Ask about water, sunset, miles left…" autoComplete="off" />
        {Rec && <button type="button" className={`hh-mic ${listening ? 'on' : ''}`} onClick={listen} aria-label={listening ? 'Stop listening' : 'Speak your question'}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg></button>}
        <button type="submit" className="primary">Ask</button>
      </form>
      <label className="hh-toggle"><input type="checkbox" checked={piVoice} onChange={e => setPiVoice(e.target.checked)} /> Also speak answers on the MapPI3 speaker</label>
    </section>
  </div>;
}
