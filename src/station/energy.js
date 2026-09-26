// One energy model for the whole app, so the Today rings, walks, workouts and hikes agree.
//
// Sources:
// - Resting burn: Mifflin-St Jeor (1990). Male +5, female -161; unknown uses the midpoint.
// - Walking and hiking: ACSM metabolic equations. Net oxygen cost is 0.1 mL/kg per metre walked
//   and 1.8 mL/kg per metre climbed; running on the flat is 0.2 mL/kg per metre. 1 L O2 ≈ 5 kcal.
//   Trail surfaces cost more than pavement. Pandolf's terrain factor is about 1.1 on a dirt road
//   and 1.2 in light brush, so hikes use 1.2.
// - Workouts: Compendium of Physical Activities (2024) MET values. "Active" calories are net
//   ((MET - 1) × kg × hours), because resting burn is already in the daily budget.
const KCAL_PER_L = 5;
const M_PER_MI = 1609.34, M_PER_FT = 0.3048;

export const kgOf = hiker => Number(hiker?.weightLb || 180) * 0.453592;

export function bmr(hiker = {}) {
  const kg = kgOf(hiker);
  const cm = (Number(hiker.heightFt || 5) * 12 + Number(hiker.heightIn || 10)) * 2.54;
  const age = hiker.birthday ? Math.max(12, Math.floor((Date.now() - new Date(hiker.birthday)) / 31557600000)) : 35;
  const sexAdj = hiker.sex === 'male' ? 5 : hiker.sex === 'female' ? -161 : -78;
  return Math.round(10 * kg + 6.25 * cm - 5 * age + sexAdj);
}

// Net (active) calories to cover a distance on foot. mph picks walking vs running cost: walking up to
// 4 mph, running from 5 mph, and a blend in between. gainFt is total climbing.
export function footKcal({ kg, miles = 0, gainFt = 0, mph = 3, terrain = 1 }) {
  const runShare = Math.max(0, Math.min(1, (Number(mph) - 4) / 1));
  const perM = (0.1 * (1 - runShare) + 0.2 * runShare) * terrain;
  const mlPerKg = perM * Number(miles || 0) * M_PER_MI + 1.8 * Number(gainFt || 0) * M_PER_FT;
  return Math.max(0, mlPerKg * kg / 1000 * KCAL_PER_L);
}
export const hikeKcal = ({ kg, miles, gainFt }) => footKcal({ kg, miles, gainFt, mph: 2, terrain: 1.2 });

// Compendium METs (moderate effort) for the workout types the app logs.
export const WORKOUT_MET = {
  'Strength training': 3.5, 'Kayak / paddle': 5.0, Cycling: 6.8, 'Stretching / mobility': 2.3,
  'Yard work / carry': 4.0, 'Ruck / weighted walk': 6.5, Swimming: 5.8, Other: 4.0
};
// The type box is free text, so common names map to their Compendium value too.
const KEYWORDS = [
  [/run|jog/i, 8.0], [/hik|trek/i, 6.0], [/ruck|backpack|weighted/i, 6.5], [/walk/i, 3.5], [/bik|cycl|spin/i, 6.8],
  [/swim/i, 5.8], [/kayak|canoe|paddl|row/i, 5.0], [/ski|snowshoe/i, 6.8], [/climb|boulder/i, 7.5],
  [/yoga|stretch|mobility|pilates/i, 2.5], [/strength|weight|lift|gym/i, 3.5], [/hiit|circuit|crossfit|burpee/i, 8.0],
  [/yard|garden|shovel|wood|carry/i, 4.0], [/danc/i, 5.0], [/basketball|soccer|hockey|tennis/i, 7.0]
];
const metOf = type => WORKOUT_MET[type] ?? (KEYWORDS.find(([re]) => re.test(String(type || ''))) || [null, WORKOUT_MET.Other])[1];
const INTENSITY = { easy: 0.75, moderate: 1, hard: 1.35 };
export function workoutKcal({ kg, type = 'Other', minutes = 0, intensity = 'moderate' }) {
  const met = metOf(type) * (INTENSITY[intensity] ?? 1);
  return Math.max(0, Math.round((met - 1) * kg * Number(minutes || 0) / 60));
}

// Active calories for things already logged. Older records stored gross calories from a heavier
// formula, so they are recomputed from their distance and time instead of trusted.
export function walkActive(w, kg) {
  if (Number.isFinite(Number(w?.activeCalories))) return Number(w.activeCalories);
  const miles = Number(w?.distanceMiles || 0), hrs = Number(w?.durationSeconds || 0) / 3600;
  return footKcal({ kg, miles, mph: hrs > 0 ? miles / hrs : 3 });
}
export function workoutActive(w, kg) {
  if (Number.isFinite(Number(w?.activeCalories))) return Number(w.activeCalories);
  return workoutKcal({ kg, type: w?.type, minutes: w?.minutes, intensity: w?.intensity });
}
// Walked distance from the GPS track when it is plausible (jitter and detours can inflate a track);
// otherwise the planned distance.
export const trailMiles = t => { const plan = Number(t?.miles || t?.distanceMiles || 0), track = Number(t?.trackMiles || 0); return track && (!plan || (track >= plan * 0.75 && track <= plan * 1.3)) ? track : plan; };
export const trailActive = (t, kg) => hikeKcal({ kg, miles: trailMiles(t), gainFt: Number(t?.gainFt || t?.elevationGainFt || 0) });
// An overnight hike splits across its two days: the way in on the start day, the way out on the finish day.
export function trailActiveOn(t, kg, key, dayKeyOf) {
  const done = t?.completedAt ? dayKeyOf(Number(t.completedAt)) : null;
  const began = t?.startedAt ? dayKeyOf(Number(t.startedAt)) : done;
  if (!done || (key !== done && key !== began)) return 0;
  if (began === done || t.gainInFt == null) return key === done ? trailActive(t, kg) : 0;
  const half = trailMiles(t) / 2;
  return hikeKcal({ kg, miles: half, gainFt: Number(key === began ? t.gainInFt : t.gainOutFt) || 0 });
}

const dayKey = d => new Date(d).toLocaleDateString('en-CA');
const stamp = x => Number(x?.endedAt || x?.savedAt || x?.at || x?.createdAt || x?.completedAt || 0);

// Everything for one calendar day: eaten, water, active burn and what it came from.
export function dayTotals(key, { hiker = {}, healthHistory = [], savedWalks = [], workoutLog = [], completedTrails = [], vitals = [] }, today = dayKey(Date.now())) {
  const kg = kgOf(hiker);
  const on = x => stamp(x) && dayKey(stamp(x)) === key;
  const walks = savedWalks.filter(on), workouts = workoutLog.filter(on), hikes = completedTrails.filter(t => trailActiveOn(t, kg, key, dayKey) > 0);
  let eaten = 0, water = 0;
  if (key === today) {
    eaten = Object.values(hiker.meals || {}).flat().reduce((a, i) => a + Number(i?.calories || 0), 0);
    water = Number(hiker.waterOz || 0);
  } else {
    const e = healthHistory.find(h => h.date === key);
    eaten = Number(e?.calories || 0); water = Number(e?.waterOz || 0);
  }
  const walkCal = walks.reduce((a, w) => a + walkActive(w, kg), 0);
  const workoutCal = workouts.reduce((a, w) => a + workoutActive(w, kg), 0);
  const hikeCal = hikes.reduce((a, t) => a + trailActiveOn(t, kg, key, dayKey), 0);
  const miles = walks.reduce((a, w) => a + Number(w.distanceMiles || 0), 0) + hikes.reduce((a, t) => a + (t.overnight && t.startedAt && dayKey(Number(t.startedAt)) !== dayKey(Number(t.completedAt)) ? trailMiles(t) / 2 : trailMiles(t)), 0);
  const pulses = vitals.filter(v => v.at && dayKey(v.at) === key && v.bpm);
  return {
    key, eaten: Math.round(eaten), water, active: Math.round(walkCal + workoutCal + hikeCal), walkCal: Math.round(walkCal), workoutCal: Math.round(workoutCal), hikeCal: Math.round(hikeCal),
    miles, hikes: hikes.length, walks: walks.length, workouts: workouts.length, logged: eaten > 0 || water > 0,
    restingBpm: pulses.length ? Math.min(...pulses.map(v => v.bpm)) : null
  };
}
export function rangeTotals(days, data, end = new Date()) {
  return Array.from({ length: days }, (_, i) => { const d = new Date(end); d.setDate(d.getDate() - (days - 1 - i)); return { date: d, ...dayTotals(dayKey(d), data) }; });
}
