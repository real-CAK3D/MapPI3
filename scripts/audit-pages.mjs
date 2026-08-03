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
async function openTopTab(top) {
  const directBottom = [...window.document.querySelectorAll('.bottom-nav .nav-link')].find(btn => norm(btn.textContent) === ({ Overview:'Home', Explore:'Search', Exercise:'Saved', Settings:'Settings' }[top] || top));
  if (directBottom) {
    directBottom.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
    await new Promise(r => window.setTimeout(r, 160));
    return directBottom;
  }
  const menu = window.document.querySelector('.hamburger-button');
  if (!menu) throw new Error('Missing hamburger navigation button');
  menu.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
  await new Promise(r => window.setTimeout(r, 120));
  const tabButton = [...window.document.querySelectorAll('.drawer-grid button')].find(btn => norm(btn.querySelector('strong')?.textContent || btn.textContent) === top);
  if (!tabButton) throw new Error(`Missing hamburger top tab: ${top}`);
  tabButton.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
  await new Promise(r => window.setTimeout(r, 160));
  return tabButton;
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
results.push(await assertLoads('Navigation shell', ['MapPI3 Trail OS','Home','Search','Saved','Settings']));
const bottomLabels = [...window.document.querySelectorAll('.bottom-nav .nav-link')].map(btn => norm(btn.textContent));
results.push({ label:'Bottom nav IA', ok: JSON.stringify(bottomLabels) === JSON.stringify(['Home','Search','Saved','Settings']), bottomLabels, snippet: bottomLabels.join(' | ') });
for (const top of ['Explore','Navigate','Camp','Adventure','Exercise','Survival','Settings']) {
  failures.length = 0;
  await openTopTab(top);
  results.push(await assertLoads(`Top tab: ${top}`, top === 'Navigate' ? ['Active hike navigation','Drive GPS','Return-to-Car + TrailNav','Detailed map intelligence','Guide AI'] : top === 'Camp' ? ['Camp','camp mode','Camp Plan','Games'] : top === 'Adventure' ? ['Adventure Timeline','Add event','mobile calm view','Replay + search'] : top === 'Survival' ? ['Survival + MapPI3new','Emergency Mode','Survival Trainer'] : top === 'Settings' ? ['Pi connection summary','Network','Hardware','Bluetooth','Sense HAT'] : top));
}
await openTopTab('Adventure');
await clickText('Play replay');
results.push(await assertLoads('Adventure replay controls', ['Replay + search','Play replay','Speed']));
const searchInput = [...window.document.querySelectorAll('input')].find(el => String(el.placeholder || '').includes('Search notes'));
if (!searchInput) throw new Error('Missing Adventure timeline search input');
const valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
valueSetter.call(searchInput, 'water');
searchInput.dispatchEvent(new window.Event('input', { bubbles: true }));
await new Promise(r => window.setTimeout(r, 160));
results.push(await assertLoads('Adventure search results', ['Water','water','Search']));
await openTopTab('Survival');
for (const sub of ['Emergency Mode','Survival Trainer']) {
  failures.length = 0;
  await clickText(sub);
  const expect = sub === 'Emergency Mode' ? ['Decimal degrees','DMS','UTM','Save timeline emergency event','MapPI3 does not contact 911/SAR'] : ['Survival trainer','Lost trail scenario','First aid decision','Never eat wild foods'];
  results.push(await assertLoads(`Survival subtab: ${sub}`, expect));
}
await openTopTab('Explore');
for (const sub of ['Routes','Weather','Plan','Pack','Brief']) {
  failures.length = 0;
  await clickText(sub);
  const expect = sub === 'Routes' ? 'Route results' : sub === 'Weather' ? 'Weather center' : sub === 'Plan' ? ['Trail Draw Zone','No trail is selected yet'] : sub === 'Pack' ? 'Pack bags' : 'Hike brief + launch';
  results.push(await assertLoads(`Explore subtab: ${sub}`, expect));
}
await openTopTab('Navigate');
for (const sub of ['Current Hike','Drive GPS','Field Kit','Sky','Guide AI']) {
  failures.length = 0;
  await clickText(sub);
  const expect = sub === 'Current Hike' ? ['Active hike navigation','Detailed map intelligence','Legend','3D view'] : sub === 'Guide AI' ? ['Navigate Guide AI','Offline packs'] : sub;
  results.push(await assertLoads(`Navigate subtab: ${sub}`, expect));
}
await openTopTab('Camp');
for (const sub of ['Camp Plan','Games','Ambiance','Weather Watch','Area Risks','Nature AI']) {
  failures.length = 0;
  await clickText(sub);
  const expect = sub === 'Camp Plan' ? ['Camp','camp mode'] : sub === 'Games' ? ['Mini games','Sense HAT joystick'] : sub === 'Ambiance' ? 'Camp Ambiance' : sub === 'Weather Watch' ? 'Weather center' : sub === 'Area Risks' ? 'Survival' : 'Nature AI';
  results.push(await assertLoads(`Camp subtab: ${sub}`, expect));
}
await openTopTab('Settings');
for (const sub of ['Bluetooth','Sense HAT']) {
  failures.length = 0;
  await clickText(sub);
  const expect = sub === 'Bluetooth' ? ['Bluetooth manager','PAN'] : ['Sense HAT','LED matrix'];
  results.push(await assertLoads(`Settings subtab: ${sub}`, expect));
}

const failed = results.filter(r => !r.ok);
console.log(JSON.stringify({ ok: failed.length === 0, failed, results }, null, 2));
process.exit(failed.length ? 1 : 0);
