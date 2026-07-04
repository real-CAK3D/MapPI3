import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const routes = [
  { name: 'Hocking Hills Ridge Loop', place: 'Logan, Ohio', miles: 5.8, time: '2h 42m', gain: '734 ft', tags: ['waterfall', 'loop', 'downloaded'], difficulty: 'Moderate' },
  { name: 'Red River Gorge Skyline', place: 'Slade, Kentucky', miles: 7.2, time: '3h 35m', gain: '1,012 ft', tags: ['views', 'shelter', 'offline ready'], difficulty: 'Hard' },
  { name: 'Mohican River Scout Path', place: 'Loudonville, Ohio', miles: 3.4, time: '1h 28m', gain: '282 ft', tags: ['water', 'family', 'custom'], difficulty: 'Easy' }
];

const pois = [
  ['Water', '0.7 mi', 'Spring crossing marked safe last sync'],
  ['Shelter', '1.9 mi', 'Lean-to near ridge split'],
  ['View', '2.4 mi', 'South overlook waypoint'],
  ['Caution', '3.1 mi', 'Steep washout / check footing']
];

function Pill({ children, tone='default' }) { return <span className={`pill ${tone}`}>{children}</span>; }

function App() {
  return <main className="app-shell">
    <section className="hero-card">
      <div className="top-line">
        <span className="brand-mark">△</span>
        <div><h1>MapPi3</h1><p>Trail OS · V1.0.1</p></div>
        <Pill tone="online">Hotspot</Pill>
      </div>
      <div className="search-box"><span>⌕</span><input placeholder="Search places, trails, or saved GPX…" defaultValue="Hocking Hills" /></div>
      <div className="quick-stats">
        <div><strong>4.2</strong><span>mi tracked</span></div>
        <div><strong>1:18</strong><span>moving</span></div>
        <div><strong>87%</strong><span>Pi battery*</span></div>
        <div><strong>±12ft</strong><span>GPS lock</span></div>
      </div>
    </section>

    <section className="map-card">
      <div className="map-toolbar"><Pill>Topo</Pill><Pill>Terrain</Pill><Pill tone="warn">Offline pack</Pill></div>
      <div className="fake-map" aria-label="Map preview">
        <div className="contour c1"></div><div className="contour c2"></div><div className="contour c3"></div>
        <svg viewBox="0 0 360 240" role="img" aria-label="Route line with live marker">
          <path d="M35 195 C80 140,120 165,150 105 S230 70,260 118 S298 173,330 54" className="route-shadow" />
          <path d="M35 195 C80 140,120 165,150 105 S230 70,260 118 S298 173,330 54" className="route-line" />
          <circle cx="169" cy="96" r="11" className="gps-ring" />
          <circle cx="169" cy="96" r="5" className="gps-dot" />
          <circle cx="260" cy="118" r="6" className="poi water" />
          <circle cx="330" cy="54" r="6" className="poi shelter" />
        </svg>
        <div className="north-chip">N ↑</div>
      </div>
      <div className="live-row"><strong>Live Navigation</strong><span>Breadcrumb recording · off-route alert armed</span></div>
    </section>

    <section className="tabs-grid">
      {['Explore','Plan','Navigate','Saved','Field Kit','Survival','Settings'].map((item, idx) => <button key={item} className={idx===2?'active':''}>{item}</button>)}
    </section>

    <section className="panel two-col">
      <div>
        <h2>Route results</h2>
        {routes.map(route => <article className="route-card" key={route.name}>
          <div><h3>{route.name}</h3><p>{route.place}</p></div>
          <div className="route-meta"><span>{route.miles} mi</span><span>{route.time}</span><span>{route.gain}</span></div>
          <div className="tag-row"><Pill tone="difficulty">{route.difficulty}</Pill>{route.tags.map(t => <Pill key={t}>{t}</Pill>)}</div>
          <button className="primary">Download to Pi SD</button>
        </article>)}
      </div>
      <div>
        <h2>Field Kit</h2>
        <div className="kit-card">
          <div className="matrix"><span>↑</span></div>
          <div><h3>LED compass</h3><p>North arrow mode waits for quick calibration before hike. Bag mode smooths sensor noise and falls back to GPS heading while moving.</p><button>Calibrate Sense HAT</button></div>
        </div>
        <h2>POI / Survival</h2>
        {pois.map(([name, dist, note]) => <div className="poi-row" key={name}><strong>{name}</strong><span>{dist}</span><p>{note}</p></div>)}
      </div>
    </section>

    <section className="panel sync-panel">
      <h2>Online when available, local when hiking</h2>
      <p>At home/camp Wi‑Fi: search, sync, upload tracks, download maps/routes. On trail: everything needed lives on the Pi SD card over hotspot.</p>
      <div className="sync-steps"><span>Search online</span><span>Download route pack</span><span>Hike offline</span><span>Upload later</span></div>
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
