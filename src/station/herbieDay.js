// Herbie's sense of the day, mirrored from the Pi agent's herbie_holiday() so the greeting still
// works when the app is not connected to the MapPI3 unit. Weekday numbers follow Python (Mon=0).
function nthWeekday(year, month, weekday, n) {
  if (n > 0) {
    const first = new Date(year, month - 1, 1);
    const offset = (weekday - ((first.getDay() + 6) % 7) + 7) % 7;
    return new Date(year, month - 1, 1 + offset + (n - 1) * 7);
  }
  const last = new Date(year, month, 0);
  const back = (((last.getDay() + 6) % 7) - weekday + 7) % 7;
  return new Date(year, month - 1, last.getDate() - back);
}
function easter(year) {
  const a = year % 19, b = Math.floor(year / 100), c = year % 100, d = Math.floor(b / 4), e = b % 4;
  const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31), day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(year, month - 1, day);
}
const same = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
export function holidayFor(day = new Date()) {
  const fixed = { '1-1': 'Happy New Year!', '2-14': "Happy Valentine's Day", '3-17': "Happy St. Patrick's Day", '4-22': 'Happy Earth Day', '7-4': 'Happy 4th of July', '10-31': 'Happy Halloween', '11-11': 'Veterans Day', '12-24': 'Christmas Eve', '12-25': 'Merry Christmas', '12-31': "New Year's Eve" };
  const key = `${day.getMonth() + 1}-${day.getDate()}`;
  if (fixed[key]) return fixed[key];
  const y = day.getFullYear();
  const floating = [[nthWeekday(y, 1, 0, 3), 'MLK Day'], [easter(y), 'Happy Easter'], [nthWeekday(y, 5, 6, 2), "Happy Mother's Day"], [nthWeekday(y, 5, 0, -1), 'Memorial Day'],
    [nthWeekday(y, 6, 5, 1), 'National Trails Day'], [nthWeekday(y, 6, 6, 3), "Happy Father's Day"], [nthWeekday(y, 9, 0, 1), 'Labor Day'], [nthWeekday(y, 9, 5, 4), 'National Public Lands Day'],
    [nthWeekday(y, 11, 3, 4), 'Happy Thanksgiving']];
  const hit = floating.find(([d]) => same(d, day));
  return hit ? hit[1] : null;
}

export function partOfDay(hour) {
  return hour < 5 ? 'night' : hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : hour < 21 ? 'evening' : 'night';
}
const clock = (date) => date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
export function hoursFromText(text = '') {
  const s = String(text).toLowerCase();
  const h = Number((s.match(/(\d+(?:\.\d+)?)\s*h/) || [])[1] || 0);
  const m = Number((s.match(/(\d+)\s*m/) || [])[1] || 0);
  return h + m / 60;
}
export function durationText(hours) {
  const total = Math.round(hours * 60);
  const h = Math.floor(total / 60), m = total % 60;
  return h ? `${h} h ${String(m).padStart(2, '0')} m` : `${m} min`;
}

// Builds the lines Herbie says on Home. Every number comes from the app's own data.
export function buildBriefing({ now = new Date(), name = '', calendar = null, route = null, hikeDate = '', sunset = null, driveMinutes = null, weather = null, specialDays = [] }) {
  const pod = partOfDay(now.getHours());
  const who = name && !/^trail hiker$/i.test(name) ? `, ${name.split(' ')[0]}` : '';
  const hello = pod === 'night' ? `Still up${who}?` : `Good ${pod}${who}!`;
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const special = (specialDays || []).find(d => String(d.date) === todayIso || String(d.date) === todayIso.slice(5));
  const holiday = special?.name || holidayFor(now);
  const lines = [];
  let face = pod === 'night' ? 'sleepy' : pod === 'morning' ? 'greetings' : 'happy';
  if (holiday) { lines.push(`It's ${holiday.replace(/^Happy /, '')}.`); face = 'party-mode'; }
  else if (calendar?.reason && calendar.kind !== 'hike') lines.push(`${calendar.reason}.`);
  else lines.push(`Happy ${now.toLocaleDateString([], { weekday: 'long' })}.`);
  const hikeHours = route ? hoursFromText(route.estimatedTime || route.time) : 0;
  let plan = null;
  if (route && hikeDate) {
    const days = Math.round((new Date(`${hikeDate}T12:00:00`) - new Date(`${todayIso}T12:00:00`)) / 86400000);
    const when = days === 0 ? 'today' : days === 1 ? 'tomorrow' : days > 1 && days <= 14 ? `in ${days} days` : days < 0 ? null : `on ${new Date(`${hikeDate}T12:00:00`).toLocaleDateString([], { month: 'short', day: 'numeric' })}`;
    if (when) {
      plan = { route: route.name, when, days, hikeHours };
      if (days === 0) face = 'excited';
      let sentence = `${route.name} is ${when}`;
      if (hikeHours) sentence += `, so plan for ${durationText(hikeHours)} on the trail`;
      lines.push(`${sentence}.`);
      if (sunset && hikeHours && days >= 0) {
        const buffer = 45;
        const startBy = new Date(sunset.getTime() - (hikeHours * 60 + buffer) * 60000);
        if (days === 0 && now > startBy) {
          lines[lines.length - 1] = `${route.name} was planned for today, but it's too late to finish before the ${clock(sunset)} sunset. Pick a new day and I'll replan.`;
          face = 'thinking';
          plan = null;
          return { hello, lines: weatherLine(lines, weather), face, plan, holiday };
        }
        plan.startBy = startBy;
        if (driveMinutes) {
          const leaveBy = new Date(startBy.getTime() - driveMinutes * 60000);
          plan.leaveBy = leaveBy;
          lines.push(`Sunset is ${clock(sunset)}. Leave home by ${clock(leaveBy)} (${Math.round(driveMinutes)} min drive) and start hiking by ${clock(startBy)}.`);
        } else {
          lines.push(`Sunset is ${clock(sunset)}, so start hiking by ${clock(startBy)}.`);
        }
      }
    }
  } else if (route) {
    lines.push(`${route.name} is picked. Set a hike date and I'll plan your day.`);
  } else {
    lines.push('Pick a trail in Explore and I will plan the day around it.');
  }
  return { hello, lines: weatherLine(lines, weather), face, plan, holiday };
}
function weatherLine(lines, weather) {
  if (weather && Number.isFinite(Number(weather.tempF))) {
    const t = Math.round(Number(weather.tempF));
    const rain = Number(weather.rainChance);
    return [...lines, `Right now it's ${t}°F${Number.isFinite(rain) && rain >= 40 ? ` with a ${rain}% chance of rain, so pack the shell` : ''}.`];
  }
  return lines;
}
