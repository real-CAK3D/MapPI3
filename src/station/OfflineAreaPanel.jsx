import React, { useEffect, useRef, useState } from 'react';
import { AREA_LAYERS, areaForRoute, deleteArea, downloadArea, listAreas, loadAreaOsm, planDownload, refineRouteLine } from './offlineArea.js';

export function useAreas() {
  const [areas, setAreas] = useState(listAreas);
  useEffect(() => { const on = () => setAreas(listAreas()); window.addEventListener('mappi3-areas', on); window.addEventListener('storage', on); return () => { window.removeEventListener('mappi3-areas', on); window.removeEventListener('storage', on); }; }, []);
  return areas;
}
// OpenStreetMap trails/points for the route's saved area (null until saved).
export function useAreaOsm(routeId) {
  const areas = useAreas();
  const area = areas.find(a => a.routeId === routeId);
  const [osm, setOsm] = useState(null);
  useEffect(() => { let off = false; setOsm(null); if (area) loadAreaOsm(area.id).then(d => { if (!off) setOsm(d); }); return () => { off = true; }; }, [area?.id, area?.savedAt]);
  return { area, osm };
}

const ago = t => { const d = Math.round((Date.now() - t) / 86400000); return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d} days ago`; };

export default function OfflineAreaPanel({ route, refined = null, onRefined, onOpen3D, onOpenPanorama }) {
  const { area, osm } = useAreaOsm(route?.id);
  const [layers, setLayers] = useState(['topo', 'satellite', 'terrain']);
  const [margin, setMargin] = useState(1.5);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState('');
  const abortRef = useRef(null);
  if (!route) return null;
  const plan = planDownload(route, layers, margin);
  const online = typeof navigator === 'undefined' || navigator.onLine;
  const start = async () => {
    setMsg(''); const ac = new AbortController(); abortRef.current = ac;
    setBusy({ done: 0, total: plan?.tiles || 0, phase: 'tiles' });
    try {
      const rec = await downloadArea(route, { layers, marginMi: margin, signal: ac.signal, onProgress: p => setBusy(p) });
      setMsg(`Saved ${rec.tiles - rec.failed} tiles (${rec.mb} MB) and ${rec.trails} trail lines.${rec.failed ? ` ${rec.failed} tiles could not be downloaded; save again to retry them.` : ''}${rec.osmError ? ` Trail data failed: ${rec.osmError}.` : ''}`);
      const data = await loadAreaOsm(rec.id);
      const line = data && refineRouteLine(route, data);
      if (line && onRefined) { onRefined(route.id, line); setMsg(m => `${m} Built a detailed trail line from OpenStreetMap: ${line.points} points, ${line.miles} mi.`); }
    } catch (e) { setMsg(e.name === 'AbortError' ? 'Download cancelled. Tiles already saved are kept.' : e.message); }
    setBusy(null);
  };
  const rebuild = () => { const line = osm && refineRouteLine(route, osm); if (line) { onRefined(route.id, line); setMsg(`Detailed trail line: ${line.points} points, ${line.miles} mi (listed ${route.distanceMiles} mi).`); } else setMsg("Couldn't match this trail to the OpenStreetMap paths nearby. The planning line stays in use."); };
  const toggle = k => setLayers(ls => ls.includes(k) ? ls.filter(x => x !== k) : [...ls, k]);
  const pct = busy && busy.total ? Math.round((busy.done / busy.total) * 100) : 0;
  return <section className="st-card oa">
    <div className="oa-head"><div><div className="st-label">Offline area</div><h3>{area ? 'Saved for offline use' : 'Save this area offline'}</h3></div>{area && <span className="oa-badge">Saved {ago(area.savedAt)}</span>}</div>
    {area ? <p className="muted">{area.tiles - area.failed} map tiles ({area.mb} MB) · {(area.layers || []).map(k => AREA_LAYERS[k]?.label).join(', ')} · {area.trails} trail lines and {area.points} places from OpenStreetMap. The map, satellite, 3D view and summit view all work here with no signal.</p>
      : <p className="muted">Downloads the map, satellite photos and terrain around {route.name}, plus the real trail lines, water, camps and viewpoints from OpenStreetMap. Do this at home on Wi-Fi.</p>}
    {refined ? <p className="oa-line">Detailed trail line in use · {refined.points} points · {refined.miles} mi · from {refined.source}</p> : area && osm ? <p className="oa-line warn">Using the planning line. <button type="button" className="ghost small" onClick={rebuild}>Build detailed trail line</button></p> : null}
    {!busy && <div className="oa-opts">
      {Object.entries(AREA_LAYERS).map(([k, L]) => <label key={k}><input type="checkbox" checked={layers.includes(k)} onChange={() => toggle(k)} /> {L.label}</label>)}
      <label>Margin <select value={margin} onChange={e => setMargin(Number(e.target.value))}><option value={0.75}>¾ mile</option><option value={1.5}>1½ miles</option><option value={3}>3 miles</option></select></label>
    </div>}
    {plan && !busy && <p className="oa-est">{plan.tiles.toLocaleString()} tiles · about {plan.estMb} MB · {plan.areaSqMi} sq mi</p>}
    {busy && <div className="oa-progress" role="progressbar" aria-valuenow={pct} aria-valuemin="0" aria-valuemax="100"><div><i style={{ width: `${busy.phase === 'trails' ? 100 : pct}%` }} /></div><span>{busy.phase === 'trails' ? 'Getting trail lines from OpenStreetMap…' : `${busy.done.toLocaleString()} of ${busy.total.toLocaleString()} tiles${busy.mb ? ` · ${busy.mb} MB` : ''}`}</span></div>}
    <div className="oa-actions">
      {busy ? <button type="button" className="ghost" onClick={() => abortRef.current?.abort()}>Cancel</button>
        : <button type="button" className="primary" disabled={!online || !layers.length} onClick={start}>{area ? 'Update saved area' : 'Save area offline'}</button>}
      {onOpen3D && <button type="button" className="ghost" onClick={onOpen3D}>3D view</button>}
      {onOpenPanorama && <button type="button" className="ghost" onClick={onOpenPanorama}>View from the top</button>}
      {area && !busy && <button type="button" className="ghost danger" onClick={() => { deleteArea(area.id); setMsg('Offline area removed.'); }}>Remove</button>}
    </div>
    {!online && !area && <p className="muted">You're offline. Connect to Wi-Fi to save this area.</p>}
    {msg && <p className="oa-msg" aria-live="polite">{msg}</p>}
    <p className="oa-credit">Maps: USGS The National Map. Terrain: AWS open terrain tiles. Trails: © OpenStreetMap contributors.</p>
  </section>;
}
