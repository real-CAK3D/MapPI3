import React from 'react';

// Trail Station shell: forest header with page tabs on desktop, a five-slot tab bar plus a
// "More" sheet on phones. Tab ids are the app's existing internal ids so routing/state stay intact.
export const stationNav = [
  { id: 'Overview', label: 'Home', icon: 'home' },
  { id: 'Explore', label: 'Explore', icon: 'search' },
  { id: 'Navigate', label: 'Navigate', icon: 'map' },
  { id: 'Weather', label: 'Weather', icon: 'cloud' },
  { id: 'Exercise', label: 'Health', icon: 'pulse' },
  { id: 'Adventure', label: 'Adventure', icon: 'globe' },
  { id: 'Survival', label: 'Guide', icon: 'book' },
  { id: 'Camp', label: 'Camp', icon: 'tent' },
  { id: 'Settings', label: 'Settings', icon: 'sliders' }
];
const phoneSlots = ['Overview', 'Explore', 'Navigate', 'Exercise'];

const paths = {
  home: <><path d="M3 10l9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></>,
  map: <><path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z" /><path d="M9 3v15M15 6v15" /></>,
  cloud: <><path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 10a4 4 0 0 0 1 8z" /></>,
  pulse: <><path d="M3 12h4l2-5 4 10 2-5h6" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>,
  book: <><path d="M4 5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5" /></>,
  tent: <><path d="M12 4L3 20h18z" /><path d="M12 4v16M9 20l3-6 3 6" /></>,
  sliders: <><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" /></>,
  more: <><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></>,
  mic: <><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
  moon: <><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  auto: <><circle cx="12" cy="12" r="8" /><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" /></>
};
export function StationIcon({ name, size = 20 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.more}</svg>;
}

export default function StationShell({ activeTab, go, version, account = 'Guest', nightMode = 'auto', isNight = false, onCycleNight, onHeyHerbie, moreOpen, setMoreOpen, piOnline = false }) {
  const initials = String(account || 'Guest').replace(/@.*/, '').replace(/[^A-Za-z0-9]/g, '').slice(0, 2).toUpperCase() || 'G';
  const nightIcon = nightMode === 'auto' ? 'auto' : isNight ? 'moon' : 'sun';
  const nightLabel = nightMode === 'auto' ? `Auto (${isNight ? 'night' : 'day'})` : isNight ? 'Night' : 'Day';
  const choose = (id) => { go(id); setMoreOpen(false); };
  return <>
    <header className="station-header">
      <button type="button" className="station-logo" onClick={() => choose('Overview')} aria-label="MapPI3 home"><strong>MAPPI3</strong><small>{version}</small></button>
      <nav className="station-tabs" aria-label="Main pages">
        {stationNav.map(item => <button key={item.id} type="button" className={activeTab === item.id ? 'on' : ''} aria-current={activeTab === item.id ? 'page' : undefined} onClick={() => choose(item.id)}>{item.label}</button>)}
      </nav>
      <div className="station-actions">
        <span className={`station-pi ${piOnline ? 'on' : ''}`} title={piOnline ? 'MapPI3 unit connected' : 'MapPI3 unit not connected'}><i />{piOnline ? 'Pi' : 'No Pi'}</span>
        <button type="button" className="station-round" onClick={onCycleNight} aria-label={`Display mode: ${nightLabel}. Tap to change.`} title={`Display: ${nightLabel}`}><StationIcon name={nightIcon} size={18} /></button>
        <button type="button" className="station-mic" onClick={onHeyHerbie}><StationIcon name="mic" size={16} /><span>Hey Herbie</span></button>
        <button type="button" className="station-avatar" onClick={() => choose('Settings')} aria-label={`Account ${account}`}>{initials}</button>
      </div>
    </header>
    <nav className="station-tabbar" aria-label="Phone navigation">
      {phoneSlots.map(id => { const item = stationNav.find(n => n.id === id); return <button key={id} type="button" className={activeTab === id ? 'on' : ''} onClick={() => choose(id)}><StationIcon name={item.icon} /><span>{item.label}</span></button>; })}
      <button type="button" className={!phoneSlots.includes(activeTab) || moreOpen ? 'on' : ''} onClick={() => setMoreOpen(v => !v)} aria-expanded={moreOpen}><StationIcon name="more" /><span>More</span></button>
    </nav>
    {moreOpen && <div className="station-sheet-backdrop" onClick={() => setMoreOpen(false)}>
      <div className="station-sheet" role="dialog" aria-label="All pages" onClick={e => e.stopPropagation()}>
        <div className="station-sheet-grip" />
        <div className="station-sheet-grid">
          {stationNav.map(item => <button key={item.id} type="button" className={activeTab === item.id ? 'on' : ''} onClick={() => choose(item.id)}><StationIcon name={item.icon} size={22} /><span>{item.label}</span></button>)}
        </div>
        <div className="station-sheet-row">
          <button type="button" onClick={onCycleNight}><StationIcon name={nightIcon} size={18} /> Display: {nightLabel}</button>
          <button type="button" onClick={() => { setMoreOpen(false); onHeyHerbie(); }}><StationIcon name="mic" size={18} /> Hey Herbie</button>
        </div>
      </div>
    </div>}
  </>;
}
