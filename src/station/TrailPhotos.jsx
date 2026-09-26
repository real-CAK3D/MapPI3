import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { deletePhoto, getPhoto, herbieNote, listPhotos, savePhoto, shrinkImage, updatePhoto } from './photos.js';
import { waypointKind } from './ElevationProfile.jsx';

export function usePhotos(routeId) {
  const [items, setItems] = useState([]);
  useEffect(() => {
    let off = false;
    const load = () => listPhotos({ routeId: routeId || null }).then(list => { if (!off) setItems(list); }).catch(() => {});
    load();
    window.addEventListener('mappi3-photos', load);
    return () => { off = true; window.removeEventListener('mappi3-photos', load); };
  }, [routeId]);
  return items;
}

async function currentFix(piLive) {
  const g = piLive?.gps;
  if (g?.fix && Number.isFinite(Number(g.lat))) return { lat: Number(g.lat), lon: Number(g.lon), alt: Number(g.alt), accuracy: Number(g.eph) || null, source: 'MapPI3 GPS' };
  if (!navigator.geolocation || !window.isSecureContext) return null;
  return new Promise(res => navigator.geolocation.getCurrentPosition(p => res({ lat: p.coords.latitude, lon: p.coords.longitude, alt: p.coords.altitude, accuracy: p.coords.accuracy, source: 'phone GPS' }), () => res(null), { enableHighAccuracy: true, timeout: 8000, maximumAge: 20000 }));
}

// Take a photo (or pick one) and file it with Herbie's note. kind: 'trail' during a hike, 'new-trail'
// while building a trail that is not in the catalog.
export default function TrailPhotos({ route = null, youMile = null, conditions = {}, piLive = null, onTimelineEvent, onAddWaypoint, kind = 'trail', title = 'Trail photos' }) {
  const photos = usePhotos(route?.id || null);
  const camRef = useRef(null), pickRef = useRef(null);
  const [busy, setBusy] = useState('');
  const [markSpot, setMarkSpot] = useState(false);
  const [open, setOpen] = useState(null);
  const handle = async (file) => {
    if (!file) return;
    setBusy('Saving photo…');
    try {
      const [img, fix] = await Promise.all([shrinkImage(file), currentFix(piLive)]);
      const wps = [...(route?.waypoints || []), ...(route?.customWaypoints || [])].filter(w => Number.isFinite(Number(w.mile))).map(w => ({ ...w, mile: Number(w.mile), kind: waypointKind(w, route?.name) }));
      const mile = Number.isFinite(Number(youMile)) ? Number(youMile) : null;
      const near = mile !== null && wps.length ? wps.map(w => ({ name: String(w.name || '').replace(route?.name || '', '').trim() || w.name, dist: Math.abs(w.mile - mile), ahead: w.mile > mile, kind: w.kind })).sort((a, b) => a.dist - b.dist)[0] : null;
      const sense = piLive?.sense;
      const ctx = { takenAt: file.lastModified && Date.now() - file.lastModified < 600000 ? file.lastModified : Date.now(), routeName: route?.name, mile, nearest: near && near.dist < 0.6 ? near : null, elevationFt: Number.isFinite(Number(fix?.alt)) ? Number(fix.alt) * 3.28084 : null, tempF: Number(conditions.tempF), weather: conditions.weatherLabel || '', heading: sense?.ok ? Number(sense.compass) : null, kind };
      const id = `photo-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
      const record = { id, blob: img.blob, thumb: img.thumb, width: img.width, height: img.height, takenAt: ctx.takenAt, routeId: route?.id || null, routeName: route?.name || '', mile, lat: fix?.lat ?? null, lon: fix?.lon ?? null, accuracy: fix?.accuracy ?? null, gpsSource: fix?.source || 'none', nearest: ctx.nearest, elevationFt: ctx.elevationFt, tempF: Number.isFinite(ctx.tempF) ? ctx.tempF : null, heading: ctx.heading, kind, note: herbieNote(ctx), userNote: '' };
      await savePhoto(record);
      onTimelineEvent && onTimelineEvent({ category: 'photo', eventType: 'photo', title: kind === 'new-trail' ? `Photo for new trail ${route?.name || ''}`.trim() : `Photo${ctx.nearest ? ` near ${ctx.nearest.name}` : ''}`, description: record.note, lat: record.lat, lon: record.lon, timestamp: record.takenAt, mediaIds: [id], source: 'trail camera', metadata: { photoId: id, mile } });
      if (markSpot && onAddWaypoint && record.lat) onAddWaypoint({ id: `wp-photo-${Date.now()}`, name: ctx.nearest ? `Photo spot near ${ctx.nearest.name}` : 'Photo spot', type: 'Photo', lat: record.lat, lon: record.lon, mile: mile ?? undefined, notes: record.note, photoId: id, custom: true, editable: true, icon: '◈' });
      setBusy(`Saved. ${record.note}`);
      postHerbie('happy', 'photo saved');
    } catch (e) { setBusy(`Couldn't save that photo: ${e.message}`); }
  };
  return <section className="st-card tp">
    <div className="tp-head"><div className="st-label">{title} · {photos.length}</div></div>
    <div className="tp-actions">
      <button type="button" className="primary" onClick={() => camRef.current?.click()}>Take photo</button>
      <button type="button" className="ghost" onClick={() => pickRef.current?.click()}>From gallery</button>
      {onAddWaypoint && <label className="tp-mark"><input type="checkbox" checked={markSpot} onChange={e => setMarkSpot(e.target.checked)} /> Mark the spot as a waypoint</label>}
      <input ref={camRef} type="file" accept="image/*" capture="environment" hidden onChange={e => { handle(e.target.files?.[0]); e.target.value = ''; }} />
      <input ref={pickRef} type="file" accept="image/*" hidden onChange={e => { handle(e.target.files?.[0]); e.target.value = ''; }} />
    </div>
    {busy && <p className="tp-msg" aria-live="polite">{busy}</p>}
    {photos.length > 0 ? <div className="tp-grid">{photos.slice(0, 12).map(p => <button key={p.id} type="button" onClick={() => setOpen(p.id)} aria-label={`Open photo: ${p.note}`}><img src={p.thumb} alt="" loading="lazy" /></button>)}</div>
      : <p className="muted">Photos you take here are saved on this phone with the spot on the trail, the weather, and a note from Herbie. They also show up on your Adventure timeline.</p>}
    {open && <PhotoViewer id={open} onClose={() => setOpen(null)} />}
  </section>;
}

function postHerbie(event, reason) { fetch('/api/command/herbie-event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event, ttl: 12, reason }) }).catch(() => {}); }

function PhotoViewer({ id, onClose }) {
  const [p, setP] = useState(null);
  const [url, setUrl] = useState('');
  const [note, setNote] = useState('');
  const [confirm, setConfirm] = useState(false);
  useEffect(() => { let u = ''; getPhoto(id).then(r => { if (!r) return; setP(r); setNote(r.userNote || ''); u = URL.createObjectURL(r.blob); setUrl(u); }); return () => { if (u) URL.revokeObjectURL(u); }; }, [id]);
  useEffect(() => { const k = e => { if (e.key === 'Escape') onClose(); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, []);
  return createPortal(<div className="tp-view" role="dialog" aria-label="Photo" onClick={onClose}>
    <div className="tp-view-card" onClick={e => e.stopPropagation()}>
      {url ? <img src={url} alt={p?.note || 'Trail photo'} /> : <div className="tp-view-wait">Loading…</div>}
      {p && <div className="tp-view-info">
        <p className="tp-herbie"><strong>Herbie:</strong> {p.note}</p>
        <label className="tp-note"><span>Your note</span><textarea id={`note-${id}`} value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder="What's in the picture?" /></label>
        <p className="muted">{new Date(p.takenAt).toLocaleString()}{p.lat ? ` · ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)} (${p.gpsSource}${p.accuracy ? ` ±${Math.round(p.accuracy)} m` : ''})` : ' · no location'}</p>
        <div className="tp-view-actions">
          <button type="button" className="primary" onClick={() => { updatePhoto(id, { userNote: note }); onClose(); }}>Save note</button>
          {confirm ? <button type="button" className="ghost danger" onClick={() => { deletePhoto(id); onClose(); }}>Tap again to delete</button> : <button type="button" className="ghost danger" onClick={() => setConfirm(true)}>Delete</button>}
          <button type="button" className="ghost" onClick={onClose}>Close</button>
        </div>
      </div>}
    </div>
  </div>, document.body);
}
