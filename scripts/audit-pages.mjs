import { JSDOM } from 'jsdom';
import fs from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(process.cwd(), 'dist');
const html = await fs.readFile(path.join(root, 'index.html'), 'utf8');
const scriptMatch = html.match(/<script[^>]+src="([^"]+\.js)"/);
if (!scriptMatch) throw new Error('No bundle script found in dist/index.html');
const scriptPath = path.join(root, scriptMatch[1].replace(/^\//, ''));
const bundle = await fs.readFile(scriptPath, 'utf8');

const failures = [];
const logs = [];
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`, {
  url: 'http://127.0.0.1:5179/',
  pretendToBeVisual: true,
  runScripts: 'dangerously',
  resources: 'usable',
  beforeParse(window) {
    const record = (level, args) => logs.push([level, ...args.map(a => a?.stack || String(a))]);
    window.console = {
      log: (...args) => record('log', args),
      info: (...args) => record('info', args),
      warn: (...args) => record('warn', args),
      debug: (...args) => record('debug', args),
      error: (...args) => { record('error', args); failures.push(['console.error', args.map(a => a?.stack || String(a)).join(' ')]); },
      group: (...args) => record('group', args),
      groupCollapsed: (...args) => record('groupCollapsed', args),
      groupEnd: () => {},
      table: (...args) => record('table', args),
    };
    window.requestAnimationFrame = (cb) => window.setTimeout(() => cb(Date.now()), 0);
    window.cancelAnimationFrame = (id) => window.clearTimeout(id);
    window.scrollTo = () => {};
    window.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
    window.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
    window.URL.createObjectURL = () => 'blob:mappi3-audit';
    window.URL.revokeObjectURL = () => {};
    const canvasContext = {
      setTransform(){}, resetTransform(){}, clearRect(){}, fillRect(){}, strokeRect(){}, beginPath(){}, arc(){}, fill(){}, stroke(){}, moveTo(){}, lineTo(){}, closePath(){}, rect(){}, clip(){}, drawImage(){}, getImageData(){ return { data: new Uint8ClampedArray(4) }; }, putImageData(){}, createLinearGradient(){ return { addColorStop(){} }; }, createPattern(){ return null; }, measureText(){ return { width: 0 }; }, fillText(){}, strokeText(){}, save(){}, restore(){}, translate(){}, rotate(){}, scale(){}, setLineDash(){},
    };
    window.HTMLCanvasElement.prototype.getContext = () => canvasContext;
    window.navigator.geolocation = {
      getCurrentPosition: (_ok, err) => err && err({ message: 'audit geolocation disabled' }),
      watchPosition: (_ok, err) => { err && err({ message: 'audit geolocation disabled' }); return 1; },
      clearWatch: () => {},
    };
    window.fetch = async (url) => {
      const text = String(url);
      if (text.includes('open-meteo')) return { ok: true, json: async () => ({ current: { temperature_2m: 63, relative_humidity_2m: 55, weather_code: 0 }, hourly: { time: [], temperature_2m: [], relative_humidity_2m: [], precipitation_probability: [], weather_code: [] }, daily: { time: [], temperature_2m_max: [], temperature_2m_min: [], precipitation_probability_max: [], weather_code: [] } }) };
      if (text.includes('air-quality')) return { ok: true, json: async () => ({ current: { us_aqi: 20 } }) };
      return { ok: false, json: async () => ({ ok: false, error: 'audit offline' }), text: async () => '' };
    };
    window.addEventListener('error', event => failures.push(['error', event.error?.stack || event.message]));
    window.addEventListener('unhandledrejection', event => failures.push(['unhandledrejection', event.reason?.stack || String(event.reason)]));
  }
});

const { window } = dom;
window.eval(bundle + '\n//# sourceURL=mappi3-dist-bundle.js');
await new Promise(r => window.setTimeout(r, 500));

function norm(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }
function buttonsByText(text) { return [...window.document.querySelectorAll('button,a')].filter(el => norm(el.textContent).includes(text)); }
async function clickText(text) {
  const btn = buttonsByText(text)[0];
  if (!btn) throw new Error(`Missing clickable text: ${text}`);
  btn.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
  await new Promise(r => window.setTimeout(r, 120));
  return btn;
}
async function assertLoads(label, expectedText) {
  await new Promise(r => window.setTimeout(r, 120));
  const body = norm(window.document.body.textContent);
  const hasExpected = Array.isArray(expectedText) ? expectedText.some(t => body.includes(t)) : body.includes(expectedText);
  const hasRoot = window.document.querySelector('#root')?.children.length > 0;
  const errCount = failures.length;
  if (!hasRoot || !hasExpected || errCount) {
    return { label, ok:false, hasRoot, hasExpected, errCount, snippet: body.slice(0, 500), failures: [...failures] };
  }
  return { label, ok:true, buttonCount: window.document.querySelectorAll('button').length, snippet: body.slice(0, 180) };
}

const results = [];
results.push(await assertLoads('Overview initial', 'Overview'));
for (const top of ['Explore','Navigate','Exercise','Survival','Settings']) {
  failures.length = 0;
  await clickText(top);
  results.push(await assertLoads(`Top tab: ${top}`, top === 'Navigate' ? ['Active hike navigation','Drive GPS'] : top));
}
await clickText('Explore');
for (const sub of ['Routes','Weather','Plan','Pack','Brief']) {
  failures.length = 0;
  await clickText(sub);
  const expect = sub === 'Routes' ? 'Route results' : sub === 'Weather' ? 'Weather center' : sub === 'Plan' ? ['Trail Draw Zone','No trail is selected yet'] : sub === 'Pack' ? 'Pack bags' : 'Hike brief + launch';
  results.push(await assertLoads(`Explore subtab: ${sub}`, expect));
}
await clickText('Navigate');
for (const sub of ['Current Hike','Drive GPS','Field Kit','Bluetooth','Sense HAT','Sky','Nature AI','Ambiance','Games']) {
  failures.length = 0;
  await clickText(sub);
  const expect = sub === 'Current Hike' ? 'Active hike navigation' : sub === 'Ambiance' ? 'Offline Library' : sub;
  results.push(await assertLoads(`Navigate subtab: ${sub}`, expect));
}

const failed = results.filter(r => !r.ok);
console.log(JSON.stringify({ ok: failed.length === 0, failed, results }, null, 2));
process.exit(failed.length ? 1 : 0);
