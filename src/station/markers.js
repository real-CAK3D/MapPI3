// Trail Station map markers: "blaze" pins. A teardrop head in the kind's color with a line icon,
// a mile tag underneath, and a brass rim on waypoints you added yourself. Used by the 2D map and 3D view.
import { waypointKind } from './ElevationProfile.jsx';

const G = {
  water: '<path d="M12 4c3 4 5.5 7 5.5 10a5.5 5.5 0 0 1-11 0C6.5 11 9 8 12 4z"/>',
  view: '<circle cx="8" cy="14" r="3.2"/><circle cx="16" cy="14" r="3.2"/><path d="M8 10.8 9.5 6h5l1.5 4.8M11.2 14h1.6"/>',
  camp: '<path d="M12 5 4 19h16z"/><path d="M12 5v14M9.5 19 12 14.5l2.5 4.5"/>',
  start: '<path d="M6 20V5M6 5h10l-2 3.5 2 3.5H6"/>',
  finish: '<path d="M6 20V5M6 5h11v7H6"/><path d="M9 5v7M12 5v7M15 5v7M6 8.5h11" stroke-width="1.3"/>',
  hazard: '<path d="M12 4 21 19H3z"/><path d="M12 10v4M12 16.8v.2"/>',
  photo: '<path d="M4 8.5h3l1.8-2.5h6.4L17 8.5h3V18H4z"/><circle cx="12" cy="13" r="3"/>',
  junction: '<path d="M12 21V5M12 7h6l2 2-2 2h-6M12 12H6l-2 2 2 2h6"/>',
  summit: '<path d="M3 19 10 7l3 5 2-3 6 10z"/><path d="M8.5 10.5 10 8.5l1.5 2" />',
  home: '<path d="M4 11 12 4l8 7v9h-5v-5H9v5H4z"/>',
  done: '<path d="M5 12.5 10 17 19 7"/>',
  walk: '<circle cx="13" cy="5" r="1.8"/><path d="M11 20l2-6-3-2 1-4 4 3 3 1M9 12l-3 2"/>',
  gps: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>',
  wp: '<circle cx="12" cy="12" r="3.2"/>'
};
const byClass = { 'home-base': 'home', 'trail-stop': 'wp', 'gps-sample': 'gps', 'completed-trail': 'done', 'saved-walk': 'walk', 'route-preview': 'wp' };

// Marker kind from a waypoint (type first, then its own name), or from an older markerClass.
export function markerKind(point = {}, routeName = '') {
  if (point.markerClass && byClass[point.markerClass]) return byClass[point.markerClass];
  const t = `${point.type || ''} ${point.name || ''}`.toLowerCase();
  if (/photo/.test(point.type || '') || point.photoId) return 'photo';
  if (/junction|fork|intersection|sign/.test(t)) return 'junction';
  if (/summit|peak|top of/.test(t)) return 'summit';
  const k = waypointKind(point, routeName);
  if (k === 'flag') return /finish|end|turnaround/.test(t) && !/start|trailhead/.test(String(point.type || '').toLowerCase()) ? 'finish' : 'start';
  return k;
}
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

export function markerHtml({ kind = 'wp', mile = null, custom = false, focused = false, label = '' } = {}) {
  const glyph = G[kind] || G.wp;
  const m = Number.isFinite(Number(mile)) && mile !== '' && mile !== null ? `<span class="st-pin-mile">${Number(mile).toFixed(Number(mile) < 10 ? 1 : 0)}</span>` : '';
  return `<div class="st-pin k-${kind}${custom ? ' custom' : ''}${focused ? ' focused' : ''}" aria-label="${esc(label)}"><div class="st-pin-head"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${glyph}</svg></div>${m}</div>`;
}
export const PIN_SIZE = [34, 46];
export const PIN_ANCHOR = [17, 40];
