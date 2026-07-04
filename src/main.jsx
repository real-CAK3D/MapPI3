import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const VERSION = 'V1.0.2';
const tabs = ['Explore', 'Plan', 'Navigate', 'Saved', 'Field Kit', 'Survival', 'Settings'];

const seedRoutes = [
  { id: 'hh-ridge', name: 'Hocking Hills Ridge Loop', place: 'Logan, Ohio', miles: 5.8, time: '2h 42m', gain: '734 ft', tags: ['waterfall', 'loop', 'downloaded'], difficulty: 'Moderate', status: 'Downloaded', size: '184 MB' },
  { id: 'rrg-sky', name: 'Red River Gorge Skyline', place: 'Slade, Kentucky', miles: 7.2, time: '3h 35m', gain: '1,012 ft', tags: ['views', 'shelter', 'offline ready'], difficulty: 'Hard', status: 'Ready', size: '226 MB' },
  { id: 'mohican-scout', name: 'Mohican River Scout Path', place: 'Loudonville, Ohio', miles: 3.4, time: '1h 28m', gain: '282 ft', tags: ['water', 'family', 'custom'], difficulty: 'Easy', status: 'Not saved', size: '92 MB' }
];

const plannerWaypoints = [
  { name: 'Trailhead', type: 'Start', mile: '0.0', icon: '◎' },
  { name: 'Water crossing', type: 'Water', mile: '0.7', icon: '≋' },
  { name: 'Ridge shelter', type: 'Shelter', mile: '1.9', icon: '⌂' },
  { name: 'South overlook', type: 'View', mile: '2.4', icon: '◆' },
  { name: 'Return split', type: 'Waypoint', mile: '4.8', icon: '•' }
];

const savedPacks = [
  ['Hocking Hills Ridge Loop', '184 MB', 'Ready offline', 'Updated today'],
  ['Base survival library', '12 MB', 'Always local', 'V1.0.2'],
  ['Ohio topo sample tiles', '311 MB', 'Wi‑Fi only download', 'Queued']
];

const survivalTips = [
  ['If lost', 'Stop, breathe, mark your location, conserve battery, retrace only if safe.'],
  ['Water', 'Mark water POIs, filter/treat unknown sources, and do not rely on cached labels as proof of safety.'],
  ['Storms', 'Pressure drop + dark clouds = get low, avoid ridges, water, and lone trees.'],
  ['Cold', 'Stay dry, add layers early, watch for shivering, confusion, and clumsy hands.']
];

function Pill({ children, tone = 'default' }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

function Stat({ value, label }) {
  return <div><strong>{value}</strong><span>{label}</span></div>;
}

function RouteMap({ activeTab }) {
  return <section className="map-card">
    <div className="map-toolbar">
      <Pill>Topo</Pill><Pill>Terrain</Pill><Pill tone="warn">Offline pack</Pill><Pill tone="online">{activeTab} mode</Pill>
    </div>
    <div className="fake-map" aria-label="Map preview">
      <div className="grid-lines"></div>
      <div className="contour c1"></div><div className="contour c2"></div><div className="contour c3"></div><div className="contour c4"></div>
      <svg viewBox="0 0 360 240" role="img" aria-label="Route line with live marker">
        <path d="M35 195 C80 140,120 165,150 105 S230 70,260 118 S298 173,330 54" className="route-shadow" />
        <path d="M35 195 C80 140,120 165,150 105 S230 70,260 118 S298 173,330 54" className="route-line" />
        <circle cx="169" cy="96" r="13" className="gps-ring" />
        <circle cx="169" cy="96" r="5" className="gps-dot" />
        <circle cx="260" cy="118" r="7" className="poi water" />
        <circle cx="330" cy="54" r="7" className="poi shelter" />
        <circle cx="112" cy="147" r="6" className="poi view" />
      </svg>
      <div className="north-chip">N ↑</div>
      <div className="elevation-card"><strong>Elev.</strong><span>+734 ft</span><small>2,018 ft high</small></div>
    </div>
    <div className="live-row"><strong>Live Navigation</strong><span>Breadcrumb recording · off-route alert armed · route corridor cached</span></div>
  </section>;
}

function Explore({ routes, onDownload }) {
  return <section className="panel two-col">
    <div>
      <h2>Route results</h2>
      <p className="muted">Search online while connected, then cache the route/map pack to the Pi SD card before the hike.</p>
      {routes.map(route => <article className="route-card" key={route.id}>
        <div className="route-card-head"><div><h3>{route.name}</h3><p>{route.place}</p></div><Pill tone={route.status === 'Downloaded' ? 'online' : 'default'}>{route.status}</Pill></div>
        <div className="route-meta"><span>{route.miles} mi</span><span>{route.time}</span><span>{route.gain}</span><span>{route.size}</span></div>
        <div className="tag-row"><Pill tone="difficulty">{route.difficulty}</Pill>{route.tags.map(t => <Pill key={t}>{t}</Pill>)}</div>
        <button className="primary" onClick={() => onDownload(route.id)}>{route.status === 'Downloaded' ? 'Refresh offline pack' : 'Download to Pi SD'}</button>
      </article>)}
    </div>
    <div className="stack">
      <DownloadPanel />
      <WeatherCard />
    </div>
  </section>;
}

function Plan() {
  return <section className="panel two-col">
    <div>
      <h2>Custom route builder</h2>
      <p className="muted">V1.0.2 mock flow: tap map to add route points, classify POIs, then export/import GPX later.</p>
      <div className="builder-tools">
        {['Draw route', 'Add waypoint', 'Water', 'Shelter', 'Camp', 'Danger', 'GPX import', 'GPX export'].map(tool => <button key={tool}>{tool}</button>)}
      </div>
      <div className="route-summary">
        <Stat value="5" label="waypoints" /><Stat value="5.8" label="planned mi" /><Stat value="734ft" label="gain" /><Stat value="184MB" label="pack est." />
      </div>
    </div>
    <div>
      <h2>Waypoints / POIs</h2>
      {plannerWaypoints.map(point => <div className="poi-row" key={point.name}><strong><span className="poi-icon">{point.icon}</span>{point.name}</strong><span>{point.mile} mi</span><p>{point.type}</p></div>)}
    </div>
  </section>;
}

function Navigate() {
  return <section className="panel dashboard-panel">
    <h2>Active hike</h2>
    <div className="nav-grid">
      <Stat value="4.2" label="mi tracked" /><Stat value="1:18" label="moving" /><Stat value="2.1" label="mi remaining" /><Stat value="±12ft" label="GPS accuracy" />
      <Stat value="2.9mph" label="pace" /><Stat value="NW 318°" label="heading" /><Stat value="14:12" label="sunset" /><Stat value="96%" label="offline pack" />
    </div>
    <div className="alert good">On route · next waypoint: Water crossing in 0.7 mi</div>
  </section>;
}

function Saved() {
  return <section className="panel">
    <h2>Saved offline packs</h2>
    <p className="muted">MapPi3 keeps hike packs modular so the Pi SD card does not get stuffed with areas you are not using.</p>
    {savedPacks.map(([name, size, status, updated]) => <div className="saved-row" key={name}><strong>{name}</strong><span>{size}</span><Pill>{status}</Pill><small>{updated}</small></div>)}
  </section>;
}

function FieldKit() {
  return <section className="panel two-col">
    <div>
      <h2>Sense HAT compass</h2>
      <div className="kit-card big">
        <div className="matrix"><span>↑</span></div>
        <div><h3>LED north arrow</h3><p>Enable this before hiking. Calibrate flat, away from magnets/metal, then use bag mode smoothing. While moving, MapPi3 can fall back to GPS heading.</p><button>Start quick calibration</button></div>
      </div>
    </div>
    <div>
      <h2>Sensor status</h2>
      <div className="sensor-list"><span>GPS lock <b>3D / good</b></span><span>Magnetic field <b>stable</b></span><span>Temp <b>71°F</b></span><span>Pressure trend <b>steady</b></span></div>
    </div>
  </section>;
}

function Survival() {
  return <section className="panel two-col">
    <div>
      <h2>Survival quick cards</h2>
      {survivalTips.map(([title, text]) => <div className="tip-card" key={title}><strong>{title}</strong><p>{text}</p></div>)}
    </div>
    <div className="warning-card"><h2>Safety honesty</h2><p>MapPi3 assists with trail awareness. Carry real navigation, emergency gear, water, first aid, and local guidance. Cached data can be stale.</p></div>
  </section>;
}

function Settings({ mode, setMode }) {
  return <section className="panel two-col">
    <div>
      <h2>Settings</h2>
      <div className="setting-row"><span>Connection mode</span><select value={mode} onChange={e => setMode(e.target.value)}><option>Hotspot</option><option>Known Wi‑Fi</option><option>Offline only</option></select></div>
      <div className="setting-row"><span>Units</span><select defaultValue="Miles / °F"><option>Miles / °F</option><option>Kilometers / °C</option></select></div>
      <div className="setting-row"><span>Map theme</span><select defaultValue="Topo Night"><option>Topo Night</option><option>Trail Day</option><option>Battery Saver</option></select></div>
    </div>
    <div>
      <h2>Integrations later</h2>
      <div className="integration-list"><Pill>GitHub ready</Pill><Pill>Supabase env placeholders</Pill><Pill>Vercel-ready static frontend</Pill><Pill>Pi hotspot first</Pill></div>
    </div>
  </section>;
}

function DownloadPanel() {
  return <div className="mini-panel"><h2>Download workflow</h2><div className="sync-steps"><span>Search online</span><span>Pick route</span><span>Cache to Pi SD</span><span>Hike offline</span></div></div>;
}

function WeatherCard() {
  return <div className="mini-panel"><h2>Weather</h2><div className="weather-line"><strong>68°F</strong><span>cached 24h outlook</span></div><p className="muted">Online forecast when connected. Offline fallback uses last forecast + Sense HAT pressure trend.</p></div>;
}

function ActiveTab({ activeTab, routes, onDownload, mode, setMode }) {
  if (activeTab === 'Explore') return <Explore routes={routes} onDownload={onDownload} />;
  if (activeTab === 'Plan') return <Plan />;
  if (activeTab === 'Navigate') return <Navigate />;
  if (activeTab === 'Saved') return <Saved />;
  if (activeTab === 'Field Kit') return <FieldKit />;
  if (activeTab === 'Survival') return <Survival />;
  return <Settings mode={mode} setMode={setMode} />;
}

function App() {
  const [activeTab, setActiveTab] = useState('Explore');
  const [mode, setMode] = useState('Hotspot');
  const [routes, setRoutes] = useState(seedRoutes);
  const downloadedCount = useMemo(() => routes.filter(r => r.status === 'Downloaded').length, [routes]);
  const onDownload = (id) => setRoutes(rs => rs.map(route => route.id === id ? { ...route, status: 'Downloaded', tags: Array.from(new Set([...route.tags, 'downloaded'])) } : route));

  return <main className="app-shell">
    <section className="hero-card">
      <div className="top-line">
        <span className="brand-mark">△</span>
        <div><h1>MapPi3</h1><p>Trail OS · {VERSION}</p></div>
        <Pill tone="online">{mode}</Pill>
      </div>
      <div className="search-box"><span>⌕</span><input placeholder="Search places, trails, or saved GPX…" defaultValue="Hocking Hills" /></div>
      <div className="quick-stats">
        <Stat value="4.2" label="mi tracked" />
        <Stat value="1:18" label="moving" />
        <Stat value={`${downloadedCount}/3`} label="packs local" />
        <Stat value="±12ft" label="GPS lock" />
      </div>
    </section>

    <RouteMap activeTab={activeTab} />

    <section className="tabs-grid" aria-label="MapPi3 sections">
      {tabs.map(item => <button key={item} className={item === activeTab ? 'active' : ''} onClick={() => setActiveTab(item)}>{item}</button>)}
    </section>

    <ActiveTab activeTab={activeTab} routes={routes} onDownload={onDownload} mode={mode} setMode={setMode} />
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
