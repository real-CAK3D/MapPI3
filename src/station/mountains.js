// Which mountain a trail climbs. The catalog's mountainArea mixes regions ("Western Maine"), roads
// ("Grafton Notch / Route 26") and themes ("Maine waterfalls"), so the Mountain Board works from the
// actual peak instead. Trails that do not climb a mountain (falls, pools, bridges, river walks) return null.
const OVERRIDES = [
  [/tumbledown/i, 'Tumbledown Mountain'],
  [/speck/i, 'Old Speck Mountain'],
  [/table rock|baldpate (west|east)/i, 'Baldpate Mountain'],
  [/bald pate/i, 'Bald Pate Mountain'],
  [/beehive|precipice/i, 'Champlain Mountain'],
  [/knife edge|katahdin/i, 'Katahdin'],
  [/maiden cliff|camden hills/i, 'Mount Megunticook'],
  [/franconia ridge/i, 'Franconia Ridge'],
  [/welch-?dickey/i, 'Welch and Dickey Mountains'],
  [/cascade and porter/i, 'Cascade Mountain'],
  [/old rag/i, 'Old Rag Mountain'],
  [/pinnacle and pulpit/i, 'The Pinnacle'],
  [/seneca rocks/i, 'Seneca Rocks'],
  [/breakneck ridge/i, 'Breakneck Ridge'],
  [/bigelow|avery peak/i, 'Bigelow Mountain'],
  [/mahoosuc notch/i, 'Mahoosuc Arm'],
  [/whitecap/i, 'Sunday River Whitecap'],
  [/blue hills skyline/i, 'Great Blue Hill'],
  [/camel.?s hump/i, "Camel's Hump"]
];
const NOT_A_MOUNTAIN = /falls|pool|swimming|bridge|riverwalk|river walk|shoreline|gorge|cave|canyon|water access|sanctuary|nature trail|conservation|bold coast|lake loop|overlook walk|hocking|gulf hagas|dolly sods|scout path|homestead|river preserve/i;
// Words that follow a mountain's name in a trail name but are not part of it.
const TAIL = new Set(['Trail', 'Loop', 'Path', 'Main', 'South', 'North', 'West', 'East', 'Summit', 'Circuit', 'Via', 'via', 'Indian', 'Cheshire', 'Ridge', 'Park', 'Ledges', 'Stone', 'Piper']);

export function mountainFor(route) {
  const name = String(route?.name || '');
  for (const [re, mountain] of OVERRIDES) if (re.test(name)) return mountain;
  if (NOT_A_MOUNTAIN.test(name)) return null;
  const words = name.replace(/[–—]/g, ' ').split(/\s+/);
  // "Mount X" / "Mt X": the next one or two capitalized words that are not trail words.
  const at = words.findIndex(w => /^(Mount|Mt\.?)$/.test(w));
  if (at >= 0 && words[at + 1]) {
    const parts = [words[at + 1]];
    if (words[at + 2] && /^[A-Z]/.test(words[at + 2]) && !TAIL.has(words[at + 2])) parts.push(words[at + 2]);
    return `Mount ${parts.join(' ')}`;
  }
  // "X Mountain" / "X Peak" / "X Hill" etc.
  const kind = words.findIndex(w => /^(Mountain|Peak|Hill|Dome|Knob)s?$/.test(w));
  if (kind > 0) {
    const parts = [words[kind - 1]];
    if (kind > 1 && /^[A-Z]/.test(words[kind - 2]) && !TAIL.has(words[kind - 2]) && !/^(Sebago|Acadia|Grafton|Camden|Baxter)$/.test(words[kind - 2])) parts.unshift(words[kind - 2]);
    return `${parts.join(' ')} ${words[kind].replace(/s$/, '')}`;
  }
  return Number(route?.elevationGainFt || 0) >= 1500 ? name.replace(/\s+(Trail|Loop|Path|Circuit)\b.*$/i, '') : null;
}

const STATES = ['Maine', 'New Hampshire', 'Vermont', 'Massachusetts', 'New York', 'Pennsylvania', 'West Virginia', 'Virginia', 'Kentucky', 'Ohio', 'Connecticut', 'Rhode Island'];
export function stateOf(route) {
  const s = `${route?.place || ''} ${route?.region || ''}`;
  return STATES.find(st => new RegExp(`\\b${st}\\b`, 'i').test(s)) || (route?.region || 'Other');
}
// Town for the badge subtitle: "Weld, Maine" -> "Weld", "Evans Notch / Stow, Maine" -> "Stow".
export function townOf(route) {
  const p = String(route?.place || '').split(',')[0].trim();
  return p && !STATES.includes(p) ? p.replace(/^.*\/\s*/, '').replace(/ trailhead.*$/i, '').trim() : '';
}
// Two catalog entries are the same trail when their names match once the mountain, town and filler
// words are removed (e.g. "Table Rock Trail" and "Grafton Notch Table Rock").
export function trailKey(route, mountain) {
  const drop = new Set(`${mountain || ''} ${route?.place || ''} ${route?.mountainArea || ''} trail loop via the and route mountain mt mount maine new hampshire approach real poi`.toLowerCase().split(/[^a-z0-9]+/));
  const words = String(route?.name || '').toLowerCase().split(/[^a-z0-9]+/).filter(w => w && !drop.has(w));
  return words.join(' ') || String(route?.id);
}
