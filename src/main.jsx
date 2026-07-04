import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { primaryMapPreviewPath, primaryRoutePack, primaryWaypoints, seedRoutes } from './data/routePacks.js';
import './styles.css';

const VERSION = 'V1.1.4';
const tabs = ['Explore', 'Plan', 'Navigate', 'Saved', 'Health', 'Field Kit', 'Survival', 'Settings'];
const routePath = primaryMapPreviewPath;
const plannerWaypoints = primaryWaypoints;

const survivalTips = [
  ['If lost', 'Stop, breathe, mark your location, conserve battery, retrace only if safe.'],
  ['Water', 'Mark water POIs, filter/treat unknown sources, and do not rely on cached labels as proof of safety.'],
  ['Storms', 'Pressure drop + dark clouds = get low, avoid ridges, water, and lone trees.'],
  ['Cold', 'Stay dry, add layers early, watch for shivering, confusion, and clumsy hands.']
];

const defaultHiker = {
  name: 'Trail Hiker', birthday: '1990-01-01', weightLb: 180, heightIn: 70,
  foodCalories: 650, waterOz: 32, heartRate: 118, systolic: 120, diastolic: 78,
  pulseCount: 30, pulseSeconds: 15, normalWalkPaceMph: 3.0
};
const defaultConditions = { tempF: 68, humidity: 54, airQuality: 42, elevationFt: 2018 };

function loadStored(key, fallback) {
  try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch { return fallback; }
}
function formatClock(seconds) {
  const h = Math.floor(seconds / 3600); const m = Math.floor((seconds % 3600) / 60); const s = seconds % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}
function yearsOld(dateString) {
  const birth = new Date(dateString); if (Number.isNaN(birth.getTime())) return 0;
  const now = new Date(); let age = now.getFullYear() - birth.getFullYear();
  const beforeBirthday = now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate());
  return beforeBirthday ? age - 1 : age;
}
function calcHealth({ hiker, conditions, elapsed, progress }) {
  const hours = Math.max(elapsed / 3600, 1 / 60);
  const miles = progress * primaryRoutePack.distanceMiles;
  const weightKg = Number(hiker.weightLb || 0) * 0.453592;
  const paceMph = miles / hours;
  const gradeLoad = primaryRoutePack.elevationGainFt / Math.max(primaryRoutePack.distanceMiles * 5280, 1);
  const heatFactor = Number(conditions.tempF) >= 80 ? 1.08 : Number(conditions.tempF) <= 40 ? 1.05 : 1;
  const humidityFactor = Number(conditions.humidity) >= 70 ? 1.05 : 1;
  const altitudeFactor = Number(conditions.elevationFt) >= 5000 ? 1.06 : 1;
  const packTerrainFactor = 1 + Math.min(0.28, gradeLoad * 10);
  const met = Math.max(3.3, Math.min(9.5, 2.8 + paceMph * 0.9)) * packTerrainFactor * heatFactor * humidityFactor * altitudeFactor;
  const caloriesBurned = met * weightKg * hours;
  const normalWalkCalories = 3.5 * weightKg * hours;
  const pulseBpm = Number(hiker.pulseSeconds) > 0 ? Math.round((Number(hiker.pulseCount || 0) / Number(hiker.pulseSeconds)) * 60) : 0;
  const netCalories = Number(hiker.foodCalories || 0) - caloriesBurned;
  const waterTargetOz = Math.max(12, hours * (18 + (Number(conditions.tempF) > 75 ? 8 : 0) + (Number(conditions.humidity) > 65 ? 4 : 0)));
  const waterBalance = Number(hiker.waterOz || 0) - waterTargetOz;
  const effortScore = Math.round(Math.min(100, (caloriesBurned / Math.max(normalWalkCalories, 1)) * 45 + progress * 35 + (Number(hiker.heartRate || pulseBpm) > 130 ? 10 : 0)));
  return { hours, miles, paceMph, met, caloriesBurned, normalWalkCalories, pulseBpm, netCalories, waterTargetOz, waterBalance, effortScore };
}
function makeGpx() {
  const points = plannerWaypoints.map(p => `    <wpt lat="${p.lat}" lon="${p.lon}"><name>${p.name}</name><type>${p.type}</type></wpt>`).join('\n');
  const rtepts = plannerWaypoints.map(p => `      <rtept lat="${p.lat}" lon="${p.lon}"><name>${p.name}</name></rtept>`).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="MapPi3 ${VERSION}" xmlns="http://www.topografix.com/GPX/1/1">\n  <metadata><name>${primaryRoutePack.name} - MapPi3 Sample</name></metadata>\n${points}\n  <rte><name>${primaryRoutePack.name}</name>\n${rtepts}\n  </rte>\n</gpx>\n`;
}
function Pill({ children, tone = 'default' }) { return <span className={`pill ${tone}`}>{children}</span>; }
function Stat({ value, label }) { return <div><strong>{value}</strong><span>{label}</span></div>; }
function NumberField({ label, value, onChange, suffix = '', min = 0 }) { return <label className="field-line"><span>{label}</span><div><input type="number" min={min} value={value} onChange={e => onChange(Number(e.target.value))} />{suffix && <em>{suffix}</em>}</div></label>; }

function RouteMap({ activeTab, progress, recording }) {
  const index = Math.min(routePath.length - 1, Math.floor(progress * (routePath.length - 1))); const [x, y] = routePath[index]; const dashOffset = 100 - Math.round(progress * 100);
  return <section className="map-card"><div className="map-toolbar"><Pill>Topo</Pill><Pill>Terrain</Pill><Pill tone="warn">Offline pack</Pill><Pill tone="online">{activeTab} mode</Pill>{recording && <Pill tone="recording">REC</Pill>}</div><div className="fake-map" aria-label="Map preview"><div className="grid-lines"></div><div className="contour c1"></div><div className="contour c2"></div><div className="contour c3"></div><div className="contour c4"></div><svg viewBox="0 0 360 240" role="img" aria-label="Route line with simulated live marker"><path d="M35 195 C80 140,120 165,150 105 S230 70,260 118 S298 173,330 54" className="route-shadow" /><path d="M35 195 C80 140,120 165,150 105 S230 70,260 118 S298 173,330 54" className="route-line muted-line" /><path d="M35 195 C80 140,120 165,150 105 S230 70,260 118 S298 173,330 54" className="route-progress" style={{ strokeDashoffset: dashOffset }} /><circle cx={x} cy={y} r="13" className="gps-ring" /><circle cx={x} cy={y} r="5" className="gps-dot" /><circle cx="260" cy="118" r="7" className="poi water" /><circle cx="330" cy="54" r="7" className="poi shelter" /><circle cx="112" cy="147" r="6" className="poi view" /></svg><div className="north-chip">N ↑</div><div className="elevation-card"><strong>Elev.</strong><span>+734 ft</span><small>{Math.round(progress * primaryRoutePack.distanceMiles * 10) / 10} mi in</small></div></div><div className="live-row"><strong>Live Navigation</strong><span>{recording ? 'Simulated GPS moving · breadcrumb recording' : 'Simulator paused · route corridor cached'}</span></div></section>;
}
function Explore({ routes, onDownload }) { return <section className="panel two-col"><div><h2>Route results</h2><p className="muted">Search online while connected, then cache the route/map pack to the Pi SD card before the hike.</p>{routes.map(route => <article className="route-card" key={route.id}><div className="route-card-head"><div><h3>{route.name}</h3><p>{route.place}</p></div><Pill tone={route.status === 'Downloaded' ? 'online' : 'default'}>{route.status}</Pill></div><div className="route-meta"><span>{route.miles} mi</span><span>{route.time}</span><span>{route.gain}</span><span>{route.size}</span></div><div className="tag-row"><Pill tone="difficulty">{route.difficulty}</Pill>{route.tags.map(t => <Pill key={t}>{t}</Pill>)}</div><button className="primary" onClick={() => onDownload(route.id)}>{route.status === 'Downloaded' ? 'Refresh offline pack' : 'Download to Pi SD'}</button></article>)}</div><div className="stack"><DownloadPanel /><WeatherCard /></div></section>; }
function Plan({ gpxStatus, onExportGpx, onImportGpx }) { return <section className="panel two-col"><div><h2>Custom route builder</h2><p className="muted">V1.1.4 route-pack flow: tap tools, export a real sample GPX file, and simulate an imported GPX being staged for offline use.</p><div className="builder-tools">{['Draw route', 'Add waypoint', 'Water', 'Shelter', 'Camp', 'Danger'].map(tool => <button key={tool}>{tool}</button>)}<button onClick={onImportGpx}>GPX import</button><button onClick={onExportGpx}>GPX export</button></div><div className="route-summary"><Stat value={plannerWaypoints.length} label="waypoints" /><Stat value={primaryRoutePack.distanceMiles} label="planned mi" /><Stat value={`${primaryRoutePack.elevationGainFt}ft`} label="gain" /><Stat value={`${primaryRoutePack.storageEstimateMb}MB`} label="pack est." /></div><div className="alert info">{gpxStatus}</div></div><div><h2>Waypoints / POIs</h2>{plannerWaypoints.map(point => <div className="poi-row" key={point.name}><strong><span className="poi-icon">{point.icon}</span>{point.name}</strong><span>{point.mile} mi</span><p>{point.type}</p></div>)}</div></section>; }
function Navigate({ recording, setRecording, elapsed, progress, resetTrack }) { const miles = Math.round(progress * primaryRoutePack.distanceMiles * 10) / 10; const remaining = Math.max(0, Math.round((primaryRoutePack.distanceMiles - miles) * 10) / 10); return <section className="panel dashboard-panel"><div className="section-head"><h2>Active hike simulator</h2><div className="button-row"><button className="primary small" onClick={() => setRecording(!recording)}>{recording ? 'Pause recording' : 'Start recording'}</button><button className="ghost small" onClick={resetTrack}>Reset</button></div></div><div className="nav-grid"><Stat value={miles.toFixed(1)} label="mi tracked" /><Stat value={formatClock(elapsed)} label="elapsed" /><Stat value={remaining.toFixed(1)} label="mi remaining" /><Stat value="±12ft" label="GPS accuracy" /><Stat value={recording ? '2.9mph' : '0.0mph'} label="pace" /><Stat value="NW 318°" label="heading" /><Stat value="14:12" label="sunset" /><Stat value={`${Math.round(progress * 100)}%`} label="route progress" /></div><div className="alert good">{recording ? 'Recording simulated track · next waypoint updates as marker moves' : 'Paused · ready to record when hike starts'}</div></section>; }
function Saved({ routes }) { const downloaded = routes.filter(r => r.status === 'Downloaded'); return <section className="panel"><h2>Saved offline packs</h2><p className="muted">Route cards come from route-pack JSON; later this becomes the Pi SD route-pack database.</p>{downloaded.map(route => <div className="saved-row" key={route.id}><strong>{route.name}</strong><span>{route.size}</span><Pill>Ready offline</Pill><small>Local browser state</small></div>)}<div className="saved-row"><strong>Base survival library</strong><span>12 MB</span><Pill>Always local</Pill><small>{VERSION}</small></div></section>; }

function Health({ hiker, setHiker, conditions, setConditions, elapsed, progress }) {
  const metrics = calcHealth({ hiker, conditions, elapsed, progress });
  const updateHiker = (key, value) => setHiker(h => ({ ...h, [key]: value }));
  const updateCondition = (key, value) => setConditions(c => ({ ...c, [key]: value }));
  return <section className="panel health-panel"><div className="section-head"><div><h2>Hiker Health</h2><p className="muted">Field estimates for calories, hydration, effort, vitals, and condition-adjusted improvement. Not medical advice.</p></div><Pill tone="warn">estimates only</Pill></div><div className="health-grid"><div className="health-card"><h3>Hiker profile</h3><label className="field-line"><span>Name</span><input value={hiker.name} onChange={e => updateHiker('name', e.target.value)} /></label><label className="field-line"><span>Birthday</span><input type="date" value={hiker.birthday} onChange={e => updateHiker('birthday', e.target.value)} /></label><NumberField label="Weight" value={hiker.weightLb} suffix="lb" onChange={v => updateHiker('weightLb', v)} /><NumberField label="Height" value={hiker.heightIn} suffix="in" onChange={v => updateHiker('heightIn', v)} /><div className="mini-readout"><span>Age</span><b>{yearsOld(hiker.birthday)}</b></div></div><div className="health-card"><h3>Intake</h3><NumberField label="Food eaten" value={hiker.foodCalories} suffix="cal" onChange={v => updateHiker('foodCalories', v)} /><NumberField label="Water drank" value={hiker.waterOz} suffix="oz" onChange={v => updateHiker('waterOz', v)} /><div className="mini-readout"><span>Net calories</span><b>{Math.round(metrics.netCalories)} cal</b></div><div className="mini-readout"><span>Water balance</span><b>{Math.round(metrics.waterBalance)} oz</b></div></div><div className="health-card"><h3>Vitals</h3><NumberField label="Heart rate" value={hiker.heartRate} suffix="bpm" onChange={v => updateHiker('heartRate', v)} /><div className="split-fields"><NumberField label="Systolic" value={hiker.systolic} onChange={v => updateHiker('systolic', v)} /><NumberField label="Diastolic" value={hiker.diastolic} onChange={v => updateHiker('diastolic', v)} /></div><div className="pulse-box"><span>Pulse timer helper</span><div className="split-fields"><NumberField label="Beats" value={hiker.pulseCount} onChange={v => updateHiker('pulseCount', v)} /><NumberField label="Seconds" value={hiker.pulseSeconds} onChange={v => updateHiker('pulseSeconds', v)} /></div><b>{metrics.pulseBpm} bpm calculated</b></div></div><div className="health-card"><h3>Conditions</h3><NumberField label="Temperature" value={conditions.tempF} suffix="°F" onChange={v => updateCondition('tempF', v)} /><NumberField label="Humidity" value={conditions.humidity} suffix="%" onChange={v => updateCondition('humidity', v)} /><NumberField label="Air quality" value={conditions.airQuality} suffix="AQI" onChange={v => updateCondition('airQuality', v)} /><NumberField label="Elevation" value={conditions.elevationFt} suffix="ft" onChange={v => updateCondition('elevationFt', v)} /></div></div><div className="health-stats"><Stat value={Math.round(metrics.caloriesBurned)} label="calories burned" /><Stat value={Math.round(metrics.normalWalkCalories)} label="normal walk cal" /><Stat value={metrics.paceMph.toFixed(1)} label="mph adjusted" /><Stat value={metrics.met.toFixed(1)} label="MET estimate" /><Stat value={Math.round(metrics.waterTargetOz)} label="water target oz" /><Stat value={`${metrics.effortScore}/100`} label="effort score" /></div><div className="alert info">Readout: compared with a normal walk for the same time, this hike is burning about {Math.round(metrics.caloriesBurned - metrics.normalWalkCalories)} extra calories under current terrain/weather inputs. Muscle gain is not measurable from one hike here, so MapPi3 tracks workload, consistency, calories, hydration, heart-rate response, and recovery trends instead.</div></section>;
}

function FieldKit() { return <section className="panel two-col"><div><h2>Sense HAT compass</h2><div className="kit-card big"><div className="matrix"><span>↑</span></div><div><h3>LED north arrow</h3><p>Enable this before hiking. Calibrate flat, away from magnets/metal, then use bag mode smoothing. While moving, MapPi3 can fall back to GPS heading.</p><button>Start quick calibration</button></div></div></div><div><h2>Sensor status</h2><div className="sensor-list"><span>GPS lock <b>3D / good</b></span><span>Magnetic field <b>stable</b></span><span>Temp <b>71°F</b></span><span>Pressure trend <b>steady</b></span></div></div></section>; }
function Survival() { return <section className="panel two-col"><div><h2>Survival quick cards</h2>{survivalTips.map(([title, text]) => <div className="tip-card" key={title}><strong>{title}</strong><p>{text}</p></div>)}</div><div className="warning-card"><h2>Safety honesty</h2><p>MapPi3 assists with trail awareness. Carry real navigation, emergency gear, water, first aid, and local guidance. Cached data can be stale.</p></div></section>; }
function Settings({ settings, setSettings, clearLocalState }) { const update = (key, value) => setSettings(s => ({ ...s, [key]: value })); return <section className="panel two-col"><div><h2>Settings</h2><div className="setting-row"><span>Connection mode</span><select value={settings.mode} onChange={e => update('mode', e.target.value)}><option>Hotspot</option><option>Known Wi‑Fi</option><option>Offline only</option></select></div><div className="setting-row"><span>Units</span><select value={settings.units} onChange={e => update('units', e.target.value)}><option>Miles / °F</option><option>Kilometers / °C</option></select></div><div className="setting-row"><span>Map theme</span><select value={settings.theme} onChange={e => update('theme', e.target.value)}><option>Topo Night</option><option>Trail Day</option><option>Battery Saver</option></select></div><button className="ghost full" onClick={clearLocalState}>Reset local {VERSION} state</button></div><div><h2>Integrations later</h2><div className="integration-list"><Pill>GitHub ready</Pill><Pill>Supabase env placeholders</Pill><Pill>Vercel-ready static frontend</Pill><Pill>Pi hotspot first</Pill><Pill>health estimates local</Pill></div></div></section>; }
function DownloadPanel() { return <div className="mini-panel"><h2>Download workflow</h2><div className="sync-steps"><span>Search online</span><span>Pick route</span><span>Cache to Pi SD</span><span>Hike offline</span></div></div>; }
function WeatherCard() { return <div className="mini-panel"><h2>Weather</h2><div className="weather-line"><strong>68°F</strong><span>cached 24h outlook</span></div><p className="muted">Online forecast when connected. Offline fallback uses last forecast + Sense HAT pressure trend.</p></div>; }
function ActiveTab(props) { if (props.activeTab === 'Explore') return <Explore routes={props.routes} onDownload={props.onDownload} />; if (props.activeTab === 'Plan') return <Plan gpxStatus={props.gpxStatus} onExportGpx={props.onExportGpx} onImportGpx={props.onImportGpx} />; if (props.activeTab === 'Navigate') return <Navigate recording={props.recording} setRecording={props.setRecording} elapsed={props.elapsed} progress={props.progress} resetTrack={props.resetTrack} />; if (props.activeTab === 'Saved') return <Saved routes={props.routes} />; if (props.activeTab === 'Health') return <Health hiker={props.hiker} setHiker={props.setHiker} conditions={props.conditions} setConditions={props.setConditions} elapsed={props.elapsed} progress={props.progress} />; if (props.activeTab === 'Field Kit') return <FieldKit />; if (props.activeTab === 'Survival') return <Survival />; return <Settings settings={props.settings} setSettings={props.setSettings} clearLocalState={props.clearLocalState} />; }

function App() {
  const [activeTab, setActiveTab] = useState(() => loadStored('mappi3.activeTab', 'Explore'));
  const [settings, setSettings] = useState(() => loadStored('mappi3.settings', { mode: 'Hotspot', units: 'Miles / °F', theme: 'Topo Night' }));
  const [hiker, setHiker] = useState(() => loadStored('mappi3.hiker', defaultHiker));
  const [conditions, setConditions] = useState(() => loadStored('mappi3.conditions', defaultConditions));
  const [routes, setRoutes] = useState(() => { const stored = loadStored('mappi3.routes', null); if (!stored) return seedRoutes; const storedById = Object.fromEntries(stored.map(route => [route.id, route])); return seedRoutes.map(route => ({ ...route, status: storedById[route.id]?.status ?? route.status, tags: storedById[route.id]?.tags ?? route.tags })); });
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(() => loadStored('mappi3.elapsed', 0));
  const [progress, setProgress] = useState(() => loadStored('mappi3.progress', 0.34));
  const [gpxStatus, setGpxStatus] = useState('GPX tools ready. Export downloads a sample route file; import stages a mock uploaded GPX.');
  const downloadedCount = useMemo(() => routes.filter(r => r.status === 'Downloaded').length, [routes]);
  const healthMetrics = useMemo(() => calcHealth({ hiker, conditions, elapsed, progress }), [hiker, conditions, elapsed, progress]);

  useEffect(() => localStorage.setItem('mappi3.activeTab', JSON.stringify(activeTab)), [activeTab]);
  useEffect(() => localStorage.setItem('mappi3.settings', JSON.stringify(settings)), [settings]);
  useEffect(() => localStorage.setItem('mappi3.routes', JSON.stringify(routes)), [routes]);
  useEffect(() => localStorage.setItem('mappi3.elapsed', JSON.stringify(elapsed)), [elapsed]);
  useEffect(() => localStorage.setItem('mappi3.progress', JSON.stringify(progress)), [progress]);
  useEffect(() => localStorage.setItem('mappi3.hiker', JSON.stringify(hiker)), [hiker]);
  useEffect(() => localStorage.setItem('mappi3.conditions', JSON.stringify(conditions)), [conditions]);
  useEffect(() => { if (!recording) return undefined; const timer = setInterval(() => { setElapsed(e => e + 1); setProgress(p => (p >= 0.98 ? 0.02 : Math.min(0.99, p + 0.012))); }, 1000); return () => clearInterval(timer); }, [recording]);

  const onDownload = (id) => setRoutes(rs => rs.map(route => route.id === id ? { ...route, status: 'Downloaded', tags: Array.from(new Set([...route.tags, 'downloaded'])) } : route));
  const resetTrack = () => { setRecording(false); setElapsed(0); setProgress(0); };
  const onExportGpx = () => { const blob = new Blob([makeGpx()], { type: 'application/gpx+xml' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'mappi3-sample-route.gpx'; link.click(); URL.revokeObjectURL(url); setGpxStatus(`Exported mappi3-sample-route.gpx from ${primaryRoutePack.name}.`); };
  const onImportGpx = () => setGpxStatus('Mock import staged: sample GPX would be parsed into route geometry, waypoints, POIs, and an offline pack request.');
  const clearLocalState = () => { ['mappi3.activeTab','mappi3.settings','mappi3.routes','mappi3.elapsed','mappi3.progress','mappi3.hiker','mappi3.conditions'].forEach(k => localStorage.removeItem(k)); location.reload(); };

  return <main className="app-shell"><section className="hero-card"><div className="top-line"><span className="brand-mark">△</span><div><h1>MapPi3</h1><p>Trail OS · {VERSION}</p></div><Pill tone="online">{settings.mode}</Pill></div><div className="search-box"><span>⌕</span><input placeholder="Search places, trails, or saved GPX…" defaultValue="Hocking Hills" /></div><div className="quick-stats"><Stat value={(progress * primaryRoutePack.distanceMiles).toFixed(1)} label="mi tracked" /><Stat value={formatClock(elapsed)} label="elapsed" /><Stat value={Math.round(healthMetrics.caloriesBurned)} label="cal burned" /><Stat value={`${downloadedCount}/3`} label="packs local" /></div></section><RouteMap activeTab={activeTab} progress={progress} recording={recording} /><section className="tabs-grid" aria-label="MapPi3 sections">{tabs.map(item => <button key={item} className={item === activeTab ? 'active' : ''} onClick={() => setActiveTab(item)}>{item}</button>)}</section><ActiveTab activeTab={activeTab} routes={routes} onDownload={onDownload} settings={settings} setSettings={setSettings} recording={recording} setRecording={setRecording} elapsed={elapsed} progress={progress} resetTrack={resetTrack} gpxStatus={gpxStatus} onExportGpx={onExportGpx} onImportGpx={onImportGpx} clearLocalState={clearLocalState} hiker={hiker} setHiker={setHiker} conditions={conditions} setConditions={setConditions} /></main>;
}

createRoot(document.getElementById('root')).render(<App />);
