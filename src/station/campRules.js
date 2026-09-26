// Camping rules for where a trail goes, so an overnight is never planned somewhere it is not allowed.
// Rules come from the land manager named in each entry. They change, so every label says to confirm
// before you go. Areas the app does not know yet say so plainly instead of guessing.
import { mountainFor } from './mountains.js';

// status: no | designated | permit | dispersed | unknown
const AREAS = [
  { re: /tumbledown/i, status: 'no', manager: 'Maine Bureau of Parks and Lands (Tumbledown Public Lands)',
    text: 'No camping on Tumbledown Mountain or at Tumbledown Pond. Plan it as a day hike; Mount Blue State Park in Weld has a campground.' },
  { re: /acadia|precipice|beehive|champlain|cadillac|dorr|gorham|penobscot|sargent|pemetic|bubble|jordan pond|great head/i, status: 'no', manager: 'Acadia National Park',
    text: 'No backcountry camping anywhere in Acadia. Camp only in the park campgrounds (Blackwoods, Seawall, Schoodic Woods).' },
  { re: /katahdin|knife edge|baxter|big niagara|little niagara|chimney pond|south turner|doubletop/i, status: 'designated', manager: 'Baxter State Park',
    text: 'Camping only at reserved campsites and lean-tos. Reservations are required before you go.' },
  { re: /table rock|eyebrow|screw auger|moose cave|mother walker|grafton notch/i, status: 'designated', manager: 'Grafton Notch State Park / Maine Appalachian Trail Club',
    text: 'No camping in the state park itself. Overnight only at the designated Appalachian Trail shelters and campsites (Baldpate, Speck Pond).' },
  { re: /mount blue|center hill/i, status: 'designated', manager: 'Mount Blue State Park',
    text: 'Camp in the state park campground only; no camping on the mountain trails.' },
  { re: /bradbury/i, status: 'designated', manager: 'Bradbury Mountain State Park', text: 'Camp in the state park campground only.' },
  { re: /megunticook|maiden cliff|camden hills|mount battie/i, status: 'designated', manager: 'Camden Hills State Park', text: 'Camp in the state park campground only.' },
  { re: /cascade and porter|cascade mountain.*(ny|new york)|porter mountain|adirondack|high peaks/i, status: 'dispersed', manager: 'NYS DEC (Adirondack Forest Preserve)',
    text: 'Camp at designated sites, or at least 150 ft from trails, roads and water. No camping above 3,500 ft except at designated sites.' },
  { re: /mount jo/i, status: 'designated', manager: 'Adirondack Mountain Club (Heart Lake)', text: 'Private land: camp only at the Adirondak Loj campground.' },
  { re: /old rag|shenandoah/i, status: 'permit', manager: 'Shenandoah National Park',
    text: 'Backcountry camping needs a permit, and camping is not allowed on the upper part of Old Rag.' },
  { re: /camel.?s hump/i, status: 'designated', manager: 'Vermont Department of Forests, Parks and Recreation / Green Mountain Club',
    text: 'Stay at the designated Long Trail shelters and sites; no camping in the alpine zone.' },
  { re: /greylock|cheshire harbor/i, status: 'designated', manager: 'Massachusetts DCR (Mount Greylock State Reservation)', text: 'Camp only at designated sites and Appalachian Trail shelters.' },
  { re: /blue hills|great blue hill/i, status: 'no', manager: 'Massachusetts DCR (Blue Hills Reservation)', text: 'No camping in the reservation.' },
  { re: /wachusett/i, status: 'no', manager: 'Massachusetts DCR (Wachusett Mountain State Reservation)', text: 'Day use only; no camping.' },
  { re: /hocking|old man.?s cave|ash cave|cedar falls/i, status: 'designated', manager: 'Ohio DNR (Hocking Hills State Park)', text: 'Camp only in the state park campground.' }
];
// White Mountain National Forest, roughly (NH Whites plus Evans Notch in Maine).
const inWhites = (lat, lon) => lat > 43.85 && lat < 44.6 && lon > -71.95 && lon < -70.9;
const WHITES = { status: 'dispersed', manager: 'White Mountain National Forest',
  text: 'Dispersed camping is allowed outside Forest Protection Areas: not above treeline, not within 200 ft of trails or water, and not within ¼ mile of huts, shelters, roads or designated sites where posted. Use a shelter or tentsite where there is one.' };
const UNKNOWN = { status: 'unknown', manager: '', text: 'Camping rules for this area are not in the app yet. Check with the land manager before planning a night out.' };

export const CAMP_LABEL = { no: 'No camping', designated: 'Designated sites only', permit: 'Permit required', dispersed: 'Dispersed camping allowed', unknown: 'Camping rules unknown' };

export function campRule(route) {
  if (route?.campRule) return route.campRule;
  const name = `${route?.name || ''} ${route?.mountainArea || ''} ${route?.place || ''} ${mountainFor(route) || ''}`;
  const hit = AREAS.find(a => a.re.test(name));
  if (hit) return hit;
  const c = route?.geometry?.coordinates?.[0];
  if (Array.isArray(c) && inWhites(c[1], c[0])) return WHITES;
  return UNKNOWN;
}

// Rule for a campsite itself, from what OpenStreetMap records about it.
export function siteRule(camp) {
  const bits = [];
  if (camp.operator) bits.push(`Run by ${camp.operator}.`);
  if (camp.fee === 'yes') bits.push('Fee charged in season.');
  if (camp.fee === 'no') bits.push('No fee.');
  if (camp.reservation === 'required') bits.push('Reservation required.');
  if (camp.capacity) bits.push(`Capacity ${camp.capacity}.`);
  if (camp.water) bits.push(`Water: ${camp.water.replace(/_/g, ' ')}.`);
  bits.push('Designated site: camp here, not along the way.');
  return { status: 'designated', manager: camp.operator || '', text: bits.join(' ') };
}
