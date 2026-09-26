// Small offline astronomy: where things are in the sky for a place and time.
// Sun, Moon and planets use Paul Schlyter's orbital elements (good to ~1°, plenty for pointing a
// phone); stars use J2000 coordinates. Everything returns altitude/azimuth in degrees (azimuth
// clockwise from true north).
const rad = Math.PI / 180, deg = 180 / Math.PI;
const rev = x => ((x % 360) + 360) % 360;
const sind = x => Math.sin(x * rad), cosd = x => Math.cos(x * rad);

function dayNumber(date) { return date.getTime() / 86400000 + 2440587.5 - 2451543.5; } // days since 2000 Jan 0.0 UT
function gmstDeg(date) { const jd = date.getTime() / 86400000 + 2440587.5; return rev(280.46061837 + 360.98564736629 * (jd - 2451545)); }

export function altAz(raDeg, decDeg, lat, lon, date) {
  const ha = rev(gmstDeg(date) + lon - raDeg);
  const alt = Math.asin(sind(lat) * sind(decDeg) + cosd(lat) * cosd(decDeg) * cosd(ha)) * deg;
  const az = rev(Math.atan2(sind(ha), cosd(ha) * sind(lat) - Math.tan(decDeg * rad) * cosd(lat)) * deg + 180);
  return { alt, az };
}

function kepler(M, e) { let E = M + e * deg * sind(M) * (1 + e * cosd(M)); for (let i = 0; i < 5; i += 1) E = E - (E - e * deg * sind(E) - M) / (1 - e * cosd(E)); return E; }
function sunEcl(d) {
  const w = 282.9404 + 4.70935e-5 * d, e = 0.016709 - 1.151e-9 * d, M = rev(356.047 + 0.9856002585 * d);
  const E = kepler(M, e); const xv = cosd(E) - e, yv = Math.sqrt(1 - e * e) * sind(E);
  const v = Math.atan2(yv, xv) * deg, r = Math.hypot(xv, yv), lon = rev(v + w);
  return { x: r * cosd(lon), y: r * sind(lon), lon, M };
}
function eclToEq(x, y, z, d) {
  const ob = 23.4393 - 3.563e-7 * d;
  const xe = x, ye = y * cosd(ob) - z * sind(ob), ze = y * sind(ob) + z * cosd(ob);
  return { ra: rev(Math.atan2(ye, xe) * deg), dec: Math.atan2(ze, Math.hypot(xe, ye)) * deg, dist: Math.hypot(xe, ye, ze) };
}
function orbit(el, d) {
  const N = el.N[0] + el.N[1] * d, i = el.i[0] + el.i[1] * d, w = el.w[0] + el.w[1] * d, a = el.a, e = el.e[0] + el.e[1] * d, M = rev(el.M[0] + el.M[1] * d);
  const E = kepler(M, e); const xv = a * (cosd(E) - e), yv = a * Math.sqrt(1 - e * e) * sind(E);
  const v = Math.atan2(yv, xv) * deg, r = Math.hypot(xv, yv);
  return { x: r * (cosd(N) * cosd(v + w) - sind(N) * sind(v + w) * cosd(i)), y: r * (sind(N) * cosd(v + w) + cosd(N) * sind(v + w) * cosd(i)), z: r * sind(v + w) * sind(i), M, w, N };
}
const PLANETS = {
  Mercury: { N: [48.3313, 3.24587e-5], i: [7.0047, 5e-8], w: [29.1241, 1.01444e-5], a: 0.387098, e: [0.205635, 5.59e-10], M: [168.6562, 4.0923344368] },
  Venus: { N: [76.6799, 2.4659e-5], i: [3.3946, 2.75e-8], w: [54.891, 1.38374e-5], a: 0.72333, e: [0.006773, -1.302e-9], M: [48.0052, 1.6021302244] },
  Mars: { N: [49.5574, 2.11081e-5], i: [1.8497, -1.78e-8], w: [286.5016, 2.92961e-5], a: 1.523688, e: [0.093405, 2.516e-9], M: [18.6021, 0.5240207766] },
  Jupiter: { N: [100.4542, 2.76854e-5], i: [1.303, -1.557e-7], w: [273.8777, 1.64505e-5], a: 5.20256, e: [0.048498, 4.469e-9], M: [19.895, 0.0830853001] },
  Saturn: { N: [113.6634, 2.3898e-5], i: [2.4886, -1.081e-7], w: [339.3939, 2.97661e-5], a: 9.55475, e: [0.055546, -9.499e-9], M: [316.967, 0.0334442282] }
};
const MOON = { N: [125.1228, -0.0529538083], i: [5.1454, 0], w: [318.0634, 0.1643573223], a: 60.2666, e: [0.0549, 0], M: [115.3654, 13.0649929509] };

export function sunPosition(lat, lon, date = new Date()) {
  const d = dayNumber(date), s = sunEcl(d), eq = eclToEq(s.x, s.y, 0, d);
  return { ...altAz(eq.ra, eq.dec, lat, lon, date), ra: eq.ra, dec: eq.dec };
}
export function moonPosition(lat, lon, date = new Date()) {
  const d = dayNumber(date);
  const m = orbit(MOON, d), s = sunEcl(d);
  let lonE = rev(Math.atan2(m.y, m.x) * deg), latE = Math.atan2(m.z, Math.hypot(m.x, m.y)) * deg;
  const Ms = s.M, Mm = rev(m.M), Ls = rev(s.lon), Lm = rev(m.N + m.w + Mm), D = rev(Lm - Ls), F = rev(Lm - m.N);
  lonE += -1.274 * sind(Mm - 2 * D) + 0.658 * sind(2 * D) - 0.186 * sind(Ms) - 0.059 * sind(2 * Mm - 2 * D) - 0.057 * sind(Mm - 2 * D + Ms) + 0.053 * sind(Mm + 2 * D);
  latE += -0.173 * sind(F - 2 * D) - 0.055 * sind(Mm - F - 2 * D) - 0.046 * sind(Mm + F - 2 * D);
  const eq = eclToEq(cosd(lonE) * cosd(latE), sind(lonE) * cosd(latE), sind(latE), d);
  const p = altAz(eq.ra, eq.dec, lat, lon, date);
  const phase = (1 - cosd(rev(lonE - s.lon))) / 2; // illuminated fraction
  return { alt: p.alt - Math.asin(1 / 60.27) * deg * cosd(p.alt), az: p.az, illumination: phase, waxing: rev(lonE - s.lon) < 180 };
}
export function planetPosition(name, lat, lon, date = new Date()) {
  const d = dayNumber(date), p = orbit(PLANETS[name], d), s = sunEcl(d);
  const eq = eclToEq(p.x + s.x, p.y + s.y, p.z, d);
  return { ...altAz(eq.ra, eq.dec, lat, lon, date), dist: eq.dist };
}

// Bright stars and the anchor star of each constellation MapPI3 teaches (RA hours, Dec degrees, magnitude).
export const STARS = [
  ['Sirius', 6.752, -16.72, -1.46, 'Brightest star in the sky, low in the south on winter nights.'],
  ['Arcturus', 14.261, 19.18, -0.05, 'Follow the arc of the Big Dipper handle to "arc to Arcturus".'],
  ['Vega', 18.616, 38.78, 0.03, 'Blue-white summer star, one corner of the Summer Triangle.'],
  ['Capella', 5.278, 46.0, 0.08, 'Bright yellow star high in the northeast on autumn evenings.'],
  ['Rigel', 5.242, -8.2, 0.13, "Orion's blue-white foot."],
  ['Procyon', 7.655, 5.22, 0.34, 'Little Dog star, east of Orion.'],
  ['Betelgeuse', 5.919, 7.41, 0.5, "Orion's red shoulder."],
  ['Altair', 19.846, 8.87, 0.77, 'Summer Triangle star in Aquila.'],
  ['Aldebaran', 4.599, 16.51, 0.85, 'Orange eye of Taurus, near the Pleiades.'],
  ['Antares', 16.49, -26.43, 0.96, 'Red heart of Scorpius, low in the south in summer.'],
  ['Spica', 13.42, -11.16, 0.97, 'Follow the arc past Arcturus to "speed on to Spica".'],
  ['Pollux', 7.755, 28.03, 1.14, 'Brighter of the Gemini twins.'],
  ['Fomalhaut', 22.961, -29.62, 1.16, 'Lonely bright star low in the south in autumn.'],
  ['Deneb', 20.69, 45.28, 1.25, 'Tail of Cygnus, the Northern Cross.'],
  ['Regulus', 10.139, 11.97, 1.35, 'Heart of Leo.'],
  ['Castor', 7.577, 31.89, 1.58, 'Second Gemini twin.'],
  ['Polaris', 2.53, 89.26, 1.98, 'The North Star. Its height above the horizon equals your latitude.'],
  ['Dubhe', 11.062, 61.75, 1.79, 'Pointer star of the Big Dipper, lines up with Polaris.'],
  ['Schedar', 0.675, 56.54, 2.24, 'Brightest star of the Cassiopeia W.'],
  ['Mirfak', 3.405, 49.86, 1.79, 'Brightest star of Perseus.']
];
export const CONSTELLATIONS = [
  { id: 'orion', name: 'Orion', ra: 5.6, dec: 0, notes: 'Three-star belt; bright Betelgeuse and Rigel. Great beginner anchor.' },
  { id: 'big-dipper', name: 'Big Dipper / Ursa Major', ra: 12.25, dec: 56, notes: 'Use the pointer stars to find Polaris, the North Star.' },
  { id: 'cassiopeia', name: 'Cassiopeia', ra: 0.9, dec: 60, notes: 'W-shaped, opposite the Big Dipper around Polaris.' },
  { id: 'cygnus', name: 'Cygnus / Northern Cross', ra: 20.6, dec: 42, notes: 'Bright Deneb; follows the Milky Way band.' },
  { id: 'scorpius', name: 'Scorpius', ra: 16.9, dec: -30, notes: 'Low southern hook; needs an open southern horizon.' },
  { id: 'pleiades', name: 'Pleiades', ra: 3.79, dec: 24.1, notes: 'Tiny dipper-shaped star cluster; good naked-eye test.' },
  { id: 'polaris', name: 'Polaris / North Star', ra: 2.53, dec: 89.26, notes: 'Its height matches your latitude; a reliable north check.' },
  { id: 'summer-triangle', name: 'Summer Triangle', ra: 19.7, dec: 31, notes: 'Vega, Deneb and Altair: the big triangle of summer and early autumn.' },
  { id: 'leo', name: 'Leo', ra: 10.7, dec: 16, notes: 'Backwards question mark (the Sickle) with Regulus at the bottom.' }
];

// Everything worth pointing at right now, brightest first, with a short "how to find it".
export function skyNow(lat, lon, date = new Date()) {
  const sun = sunPosition(lat, lon, date);
  const out = [];
  const moon = moonPosition(lat, lon, date);
  out.push({ id: 'moon', name: 'Moon', kind: 'moon', alt: moon.alt, az: moon.az, mag: -12, notes: `${Math.round(moon.illumination * 100)}% lit, ${moon.waxing ? 'waxing' : 'waning'}.` });
  Object.keys(PLANETS).forEach(n => { const p = planetPosition(n, lat, lon, date); out.push({ id: n.toLowerCase(), name: n, kind: 'planet', alt: p.alt, az: p.az, mag: { Mercury: 0, Venus: -4, Mars: 0.5, Jupiter: -2.3, Saturn: 0.7 }[n], notes: { Mercury: 'Only low in twilight, close to the Sun.', Venus: 'Dazzling "evening/morning star"; never far from the Sun.', Mars: 'Steady orange-red point.', Jupiter: 'Bright, steady and creamy white. Binoculars show its moons.', Saturn: 'Steady golden point; a small scope shows the rings.' }[n] }); });
  STARS.forEach(([name, raH, dec, mag, notes]) => { const p = altAz(raH * 15, dec, lat, lon, date); out.push({ id: name.toLowerCase(), name, kind: 'star', alt: p.alt, az: p.az, mag, notes }); });
  CONSTELLATIONS.forEach(c => { const p = altAz(c.ra * 15, c.dec, lat, lon, date); out.push({ id: c.id, name: c.name, kind: 'constellation', alt: p.alt, az: p.az, mag: 1.5, notes: c.notes }); });
  return { sun, dark: sun.alt < -12, twilight: sun.alt < -0.8 && sun.alt >= -12, objects: out };
}

// Where the phone's back camera points, from DeviceOrientation (W3C: R = Rz(alpha)·Rx(beta)·Ry(gamma)).
// alphaNorth must be measured from north (absolute). Returns compass heading and altitude of the view.
export function cameraPointing(alphaNorth, beta, gamma) {
  const cA = cosd(alphaNorth), sA = sind(alphaNorth), cB = cosd(beta), sB = sind(beta), cG = cosd(gamma), sG = sind(gamma);
  const x = -cA * sG - sA * sB * cG, y = -sA * sG + cA * sB * cG, z = -cB * cG;
  return { heading: rev(Math.atan2(x, y) * deg), alt: Math.asin(Math.max(-1, Math.min(1, z))) * deg };
}

// Magnetic declination (east positive) for the area MapPI3's trail packs cover, from NOAA WMM
// values at reference points, blended by distance. Good to about 1°; Settings can override it.
const DECL = [[44.7, -70.5, -15.3], [45.9, -68.9, -15.9], [44.3, -68.2, -15.9], [43.2, -71.5, -14.8], [44.3, -72.9, -14.1], [42.4, -71.9, -14.0], [41.4, -74.0, -12.9], [40.9, -77.8, -10.9], [39.0, -79.4, -9.0], [37.8, -83.7, -5.9], [39.6, -82.4, -7.6], [47.0, -69.0, -16.3], [44.1, -70.2, -15.5]];
export function approxDeclination(lat, lon) {
  let wsum = 0, v = 0;
  for (const [a, b, dcl] of DECL) { const dd = Math.hypot(lat - a, (lon - b) * cosd(lat)) + 0.05; const w = 1 / (dd * dd); wsum += w; v += w * dcl; }
  return wsum ? v / wsum : 0;
}
