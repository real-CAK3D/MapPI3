// Trail photos live in the browser's IndexedDB (localStorage is far too small for images).
// Each photo keeps a resized JPEG, a small thumbnail, and where/when/what: GPS, trail mile,
// nearest stop, elevation, weather, heading, plus Herbie's note and the hiker's own note.
const DB = 'mappi3-photos', STORE = 'photos';
function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => { const s = req.result.createObjectStore(STORE, { keyPath: 'id' }); s.createIndex('routeId', 'routeId'); s.createIndex('takenAt', 'takenAt'); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function tx(mode, fn) { const db = await open(); return new Promise((resolve, reject) => { const t = db.transaction(STORE, mode); const out = fn(t.objectStore(STORE)); t.oncomplete = () => resolve(out?.result ?? out); t.onerror = () => reject(t.error); }); }
const notify = () => window.dispatchEvent(new CustomEvent('mappi3-photos'));

export async function savePhoto(record) { await tx('readwrite', s => s.put(record)); notify(); return record; }
export async function deletePhoto(id) { await tx('readwrite', s => s.delete(id)); notify(); }
export async function updatePhoto(id, patch) { const cur = await getPhoto(id); if (cur) await savePhoto({ ...cur, ...patch }); }
export async function getPhoto(id) { return tx('readonly', s => s.get(id)); }
export async function listPhotos({ routeId = null, limit = 200 } = {}) {
  const all = await tx('readonly', s => (routeId ? s.index('routeId').getAll(routeId) : s.getAll()));
  return (all || []).sort((a, b) => b.takenAt - a.takenAt).slice(0, limit).map(({ blob, ...rest }) => rest);
}

// Resize on the phone before saving: full photos from a phone camera are 3-8 MB each.
export async function shrinkImage(file, max = 1600, quality = 0.82) {
  const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' }).catch(() => null);
  const src = bmp || await new Promise((res, rej) => { const img = new Image(); img.onload = () => res(img); img.onerror = rej; img.src = URL.createObjectURL(file); });
  const w = src.width, h = src.height, k = Math.min(1, max / Math.max(w, h));
  const draw = (scale, q) => { const c = document.createElement('canvas'); c.width = Math.round(w * scale); c.height = Math.round(h * scale); c.getContext('2d').drawImage(src, 0, 0, c.width, c.height); return new Promise(r => c.toBlob(b => r(b), 'image/jpeg', q)); };
  const blob = await draw(k, quality);
  const thumbBlob = await draw(Math.min(1, 320 / Math.max(w, h)), 0.7);
  const thumb = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(thumbBlob); });
  return { blob, thumb, width: Math.round(w * k), height: Math.round(h * k) };
}

// Herbie writes a short field note from what the app knows at that moment.
export function herbieNote(ctx) {
  const parts = [];
  const t = new Date(ctx.takenAt || Date.now());
  const time = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (ctx.routeName && Number.isFinite(ctx.mile)) parts.push(`Mile ${ctx.mile.toFixed(1)} of ${ctx.routeName} at ${time}`);
  else parts.push(`Snapped at ${time}${ctx.lat ? '' : ' (no GPS fix)'}`);
  if (ctx.nearest) parts.push(ctx.nearest.dist < 0.05 ? `right at ${ctx.nearest.name}` : `${ctx.nearest.dist.toFixed(2)} mi ${ctx.nearest.ahead ? 'before' : 'past'} ${ctx.nearest.name}`);
  const conditions = [Number.isFinite(ctx.elevationFt) ? `${Math.round(ctx.elevationFt).toLocaleString()} ft` : '', Number.isFinite(ctx.tempF) ? `${Math.round(ctx.tempF)}°F` : '', ctx.weather || '', Number.isFinite(ctx.heading) ? `facing ${['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(ctx.heading / 45) % 8]}` : ''].filter(Boolean);
  if (conditions.length) parts.push(conditions.join(', '));
  const kind = ctx.nearest?.kind;
  const flavor = kind === 'view' ? 'What a view. Worth the climb!' : kind === 'water' ? 'Good spot to refill, just filter it first.' : kind === 'camp' ? 'Could be a comfy place to camp.' : ctx.kind === 'new-trail' ? 'New trail for the logbook!' : (t.getHours() >= 20 || t.getHours() < 5) ? 'Night shot! Headlamp on and watch your footing.' : t.getHours() >= 17 ? 'Golden hour looks good on you.' : t.getHours() < 8 ? 'Early start. Nice.' : 'Saved to the trail log.';
  return `${parts.join(' · ')}. ${flavor}`;
}
