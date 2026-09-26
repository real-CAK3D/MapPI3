import React, { useEffect, useMemo } from 'react';

// Daily health: food in against a calorie budget, activity out, and water, the way a phone health app
// shows a day. Hike-aware: it plans fuel the day before, paces food and water during, and counts the hike.
const dayKey = (d = new Date()) => d.toLocaleDateString('en-CA');
const sameDay = (t, key) => t && dayKey(new Date(Number(t))) === key;
const ozToL = oz => (Number(oz || 0) * 0.0295735);

function Ring({ pct, r, color, width = 12 }) {
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(1, pct));
  return <><circle r={r} fill="none" stroke="var(--st-line)" strokeWidth={width} /><circle r={r} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeDasharray={`${(c * p).toFixed(1)} ${c.toFixed(1)}`} transform="rotate(-90)" /></>;
}

export default function DailyHealth({ hiker = {}, setHiker, healthHistory = [], setHealthHistory, savedWalks = [], workoutLog = [], completedTrails = [], launchPlan = {}, selectedRoute = null, recording = false, hikeCaloriesNow = 0, elapsed = 0, foodCatalog = [], onOpenLog }) {
  const today = dayKey();
  // New day: file yesterday's intake into history and start fresh. Older data without a date is
  // simply stamped with today so nothing is lost.
  useEffect(() => {
    if (!setHiker) return;
    if (!hiker.intakeDate) { setHiker(h => ({ ...h, intakeDate: today })); return; }
    if (hiker.intakeDate !== today) {
      const meals = hiker.meals || {};
      const items = Object.values(meals).flat();
      const calories = items.reduce((a, i) => a + Number(i.calories || 0), 0);
      if (items.length || Number(hiker.waterOz || 0)) setHealthHistory && setHealthHistory(list => [{ id: `health-${Date.now()}`, date: hiker.intakeDate, calories, waterOz: Number(hiker.waterOz || 0), meals, itemCount: items.length, note: 'saved automatically at the end of the day' }, ...(list || []).filter(e => e.date !== hiker.intakeDate)].slice(0, 60));
      setHiker(h => ({ ...h, meals: { breakfast: [], brunch: [], lunch: [], snack: [], dinner: [] }, foods: [], waterOz: 0, intakeDate: today }));
    }
  }, [today, hiker.intakeDate]);

  const kg = Number(hiker.weightLb || 180) * 0.453592;
  const cm = (Number(hiker.heightFt || 5) * 12 + Number(hiker.heightIn || 10)) * 2.54;
  const age = hiker.birthday ? Math.max(12, Math.floor((Date.now() - new Date(hiker.birthday)) / 31557600000)) : 35;
  const sexAdj = hiker.sex === 'male' ? 5 : hiker.sex === 'female' ? -161 : -78;
  const bmr = Math.round(10 * kg + 6.25 * cm - 5 * age + sexAdj);
  const now = new Date();
  const dayFrac = (now.getHours() * 60 + now.getMinutes()) / 1440;

  const meals = hiker.meals || {};
  const items = Object.entries(meals).flatMap(([slot, list]) => (list || []).map(i => ({ ...i, slot })));
  const eaten = items.reduce((a, i) => a + Number(i.calories || 0), 0) || (hiker.foods || []).reduce((a, f) => a + Number(f[1] || 0), 0);
  const walkCal = savedWalks.filter(w => sameDay(w.endedAt || w.savedAt, today)).reduce((a, w) => a + Number(w.calories || w.caloriesBurned || Number(w.distanceMiles || 0) * kg * 1.05 * 0.72), 0);
  const workoutCal = workoutLog.filter(w => sameDay(w.at || w.createdAt, today)).reduce((a, w) => a + Number(w.calories || 0), 0);
  const hikeDoneToday = completedTrails.filter(t => sameDay(t.completedAt, today));
  const hikeCal = recording ? hikeCaloriesNow : hikeDoneToday.reduce((a, t) => a + Number(t.miles || 0) * kg * 0.75 + Number(t.gainFt || 0) * 0.12, 0);
  const active = Math.round(walkCal + workoutCal + hikeCal);
  const budget = Math.round(bmr * 1.2 + active);
  const left = budget - eaten;
  const moveGoal = Number(hiker.moveGoalCal || 400);
  const waterGoalOz = Math.round(Number(hiker.weightLb || 180) * 0.5 + (recording || hikeDoneToday.length ? 32 : 0));
  const water = Number(hiker.waterOz || 0);

  const hikeDate = launchPlan?.hikeDate && (launchPlan.hikeDateChosen || launchPlan.hikeDate > today) ? launchPlan.hikeDate : '';
  const daysToHike = hikeDate ? Math.round((new Date(`${hikeDate}T12:00:00`) - new Date(`${today}T12:00:00`)) / 86400000) : null;
  const hikeEst = selectedRoute ? Math.round(Number(selectedRoute.distanceMiles || 0) * kg * 0.75 + Number(selectedRoute.elevationGainFt || 0) * 0.12) : 0;
  const hikeHours = selectedRoute ? (() => { const s = String(selectedRoute.estimatedTime || ''); return Number((s.match(/(\d+(?:\.\d+)?)\s*h/) || [])[1] || 0) + Number((s.match(/(\d+)\s*m/) || [])[1] || 0) / 60; })() : 0;
  let coach;
  if (recording) {
    const hrs = elapsed / 3600;
    coach = { title: 'On the trail', text: `You've burned about ${Math.round(hikeCaloriesNow)} calories. Aim for 200 to 300 calories and 16 to 24 oz of water each hour. That's about ${Math.round(hrs * 250)} calories and ${Math.round(hrs * 20)} oz by now.` };
  } else if (daysToHike === 1 || (daysToHike === 0 && now.getHours() < 10)) {
    coach = { title: daysToHike === 0 ? 'Hike day' : 'Hike tomorrow', text: `${selectedRoute?.name || 'Your hike'} burns roughly ${hikeEst.toLocaleString()} calories over ${hikeHours ? `${hikeHours.toFixed(1)} hours` : 'the day'}. ${daysToHike === 1 ? 'Eat a carb-rich dinner tonight and drink an extra 16 oz before bed.' : 'Eat a real breakfast and drink 16 oz before you start.'} Pack about ${Math.round(Math.max(1, hikeHours) * 250).toLocaleString()} calories of snacks.` };
  } else if (hikeDoneToday.length) {
    coach = { title: 'Recovery', text: `Nice hike! Refuel with protein and carbs in the next 2 hours, and keep drinking. You have ${Math.max(0, left).toLocaleString()} calories left today.` };
  } else {
    coach = { title: 'Today', text: left >= 0 ? `${left.toLocaleString()} calories left in today's budget, ${Math.max(0, waterGoalOz - water)} oz of water to go.` : `${Math.abs(left).toLocaleString()} calories over today's budget. A walk would help balance it.` };
  }

  const week = useMemo(() => {
    const byDate = Object.fromEntries((healthHistory || []).map(e => [e.date, e]));
    return Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() - (6 - i)); const k = dayKey(d); const e = k === today ? { calories: eaten, waterOz: water } : byDate[k]; return { k, label: d.toLocaleDateString([], { weekday: 'short' }), cal: Number(e?.calories || 0), water: Number(e?.waterOz || 0), hike: completedTrails.some(t => sameDay(t.completedAt, k)) }; });
  }, [healthHistory, eaten, water, completedTrails.length, today]);
  const maxCal = Math.max(budget, ...week.map(w => w.cal), 1);

  const addWater = oz => setHiker && setHiker(h => ({ ...h, waterOz: Number(h.waterOz || 0) + oz, intakeDate: today }));
  const slotNow = now.getHours() < 10 ? 'breakfast' : now.getHours() < 12 ? 'brunch' : now.getHours() < 15 ? 'lunch' : now.getHours() < 18 ? 'snack' : 'dinner';
  const addSnack = (item) => setHiker && setHiker(h => { const m = { breakfast: [], brunch: [], lunch: [], snack: [], dinner: [], ...(h.meals || {}) }; m[slotNow] = [...(m[slotNow] || []), { id: `meal-${Date.now()}`, name: item[0], calories: Number(item[1] || 0), at: Date.now() }]; return { ...h, meals: m, foods: [], intakeDate: today }; });
  const quick = (foodCatalog || []).filter(f => /granola|trail mix|banana|apple|jerky|peanut|energy|protein bar|oatmeal/i.test(f[0])).slice(0, 6);

  return <section className="dh">
    <div className="dh-top st-card">
      <svg className="dh-rings" width="190" height="190" viewBox="-95 -95 190 190" role="img" aria-label={`Food ${eaten} of ${budget} calories, activity ${active} of ${moveGoal}, water ${water} of ${waterGoalOz} ounces`}>
        <Ring pct={eaten / Math.max(1, budget)} r={82} color="var(--st-brass)" />
        <Ring pct={active / Math.max(1, moveGoal)} r={64} color="var(--st-good)" />
        <Ring pct={water / Math.max(1, waterGoalOz)} r={46} color="var(--st-water)" />
      </svg>
      <div className="dh-summary">
        <div className="st-eyebrow">{now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}</div>
        <div className="dh-big"><strong>{Math.max(0, left).toLocaleString()}</strong><span>{left >= 0 ? 'calories left' : `over by ${Math.abs(left).toLocaleString()}`}</span></div>
        <div className="dh-legend">
          <div><i style={{ background: 'var(--st-brass)' }} />Food <b>{eaten.toLocaleString()} / {budget.toLocaleString()}</b></div>
          <div><i style={{ background: 'var(--st-good)' }} />Activity <b>{active.toLocaleString()} / {moveGoal} cal</b></div>
          <div><i style={{ background: 'var(--st-water)' }} />Water <b>{water} / {waterGoalOz} oz</b></div>
        </div>
        <p className="dh-note">Budget = resting burn ({bmr.toLocaleString()} cal) × 1.2 + today's walks, workouts and hikes. Estimates, not medical advice.</p>
      </div>
      <div className={`dh-coach ${recording ? 'live' : ''}`}><div className="st-label">{coach.title}</div><p>{coach.text}</p></div>
    </div>
    <div className="dh-row">
      <div className="st-card dh-quick"><div className="st-label">Quick add</div>
        <div className="dh-btns"><button type="button" className="primary" onClick={() => addWater(8)}>+ 8 oz water</button><button type="button" className="ghost" onClick={() => addWater(16)}>+ 16 oz</button><button type="button" className="ghost" onClick={() => addWater(-8)} disabled={water < 8}>− 8 oz</button></div>
        {quick.length > 0 && <div className="dh-snacks">{quick.map(f => <button key={f[0]} type="button" onClick={() => addSnack(f)}>{f[0]} <b>{f[1]}</b></button>)}</div>}
        <button type="button" className="ghost dh-more" onClick={onOpenLog}>Log a meal or drink</button>
      </div>
      <div className="st-card dh-today"><div className="st-label">Eaten today · {items.length} item{items.length === 1 ? '' : 's'}</div>
        {items.length ? <div className="dh-items">{items.sort((a, b) => Number(a.at || 0) - Number(b.at || 0)).map(i => <div key={i.id}><span>{i.name}</span><small>{i.slot}{i.at ? ` · ${new Date(i.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}</small><b>{i.calories}</b></div>)}</div> : <p className="muted">Nothing logged yet today.</p>}
      </div>
      <div className="st-card dh-week"><div className="st-label">Last 7 days · calories eaten</div>
        <div className="dh-bars">{week.map(w => <div key={w.k} className={w.k === today ? 'today' : ''} title={`${w.label}: ${w.cal} cal, ${w.water} oz water${w.hike ? ', hiked' : ''}`}><span className="dh-bar"><i style={{ height: `${Math.round((w.cal / maxCal) * 100)}%` }} /><em style={{ bottom: `${Math.round((budget / maxCal) * 100)}%` }} /></span><small>{w.label}{w.hike ? ' ▲' : ''}</small></div>)}</div>
        <p className="dh-note">Dashed line: today's budget. ▲ = hike day.</p>
      </div>
    </div>
  </section>;
}
