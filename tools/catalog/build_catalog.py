"""Build MapPI3's mountain catalog near home base from open data.

Inputs (cached by fetch_osm.py): OpenStreetMap named peaks, named trail paths, hiking route relations,
state boundaries and towns. Trailhead elevations come from the open AWS terrain tiles.
Output: public/catalog/mountains.json with every named summit that a named trail reaches, its real
elevation and location, and each trail measured from its trailhead to the summit.

Run: python tools/catalog/fetch_osm.py && python tools/catalog/build_catalog.py
Data (c) OpenStreetMap contributors (ODbL). Terrain: AWS Terrain Tiles (public).
"""
import heapq, io, json, math, pathlib, re, time, urllib.request
from collections import defaultdict

HERE = pathlib.Path(__file__).parent
CACHE = HERE / 'cache'
OUT = HERE.parents[1] / 'public' / 'catalog' / 'mountains.json'
HOME = (44.1004, -70.2148)
MAX_HOME_MI = 105
SUMMIT_REACH_M = 120
SKIP_NAMES = re.compile(r'snowmobile|its \d|^road|\broad$|\brd$|lane$|street|avenue|drive$|highway|ski|xc|nordic|bike|mtb|atv', re.I)

def load(name):
    return json.loads((CACHE / name).read_text(encoding='utf-8'))['elements']

R_M = 6371008.8
def dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_M * math.asin(math.sqrt(h))
def mi(a, b): return dist_m(a, b) / 1609.344

def parse_ele(v):
    if v is None: return None
    s = str(v).strip().lower().replace(',', '.')
    m = re.match(r'^(-?\d+(?:\.\d+)?)\s*(ft|feet|\')?', s)
    if not m: return None
    val = float(m.group(1))
    return val * 0.3048 if m.group(2) else val

# ---------- terrain: trailhead elevation ----------
TCACHE = CACHE / 'terrarium'; TCACHE.mkdir(exist_ok=True)
_tiles = {}
def tile_pixels(z, x, y):
    key = (z, x, y)
    if key in _tiles: return _tiles[key]
    p = TCACHE / f'{z}_{x}_{y}.png'
    if not p.exists():
        url = f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
        for _ in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r: p.write_bytes(r.read()); break
            except Exception: time.sleep(2)
    try:
        from PIL import Image
        img = Image.open(p).convert('RGB'); _tiles[key] = img
    except Exception:
        _tiles[key] = None
    return _tiles[key]
def elevation_m(lat, lon, z=12):
    n = 2 ** z
    fx = (lon + 180) / 360 * n
    fy = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    img = tile_pixels(z, int(fx), int(fy))
    if img is None: return None
    r, g, b = img.getpixel((min(255, int((fx % 1) * 256)), min(255, int((fy % 1) * 256))))
    return r * 256 + g + b / 256 - 32768

# ---------- states and towns ----------
def state_rings():
    out = []
    for rel in load('states.json'):
        segs = []
        for m in rel.get('members', []):
            if m.get('type') == 'way' and m.get('role') in ('outer', '') and m.get('geometry'):
                g = m['geometry']
                segs += [((g[i - 1]['lat'], g[i - 1]['lon']), (g[i]['lat'], g[i]['lon'])) for i in range(1, len(g))]
        out.append((rel['tags']['name'], segs))
    return out
STATES = state_rings()
def state_of(pt):
    lat, lon = pt
    for name, segs in STATES:
        inside = False
        for (y1, x1), (y2, x2) in segs:
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1:
                inside = not inside
        if inside: return name
    return 'Other'
PLACES = [(e['lat'], e['lon'], e['tags']['name'], e['tags'].get('place')) for e in load('places.json')]
def town_of(pt):
    best = min(PLACES, key=lambda p: (p[0] - pt[0]) ** 2 + ((p[1] - pt[1]) * math.cos(math.radians(pt[0]))) ** 2)
    return best[2]

# ---------- peaks ----------
peaks = []
for e in load('peaks.json'):
    t = e.get('tags', {})
    ele = parse_ele(t.get('ele'))
    if not t.get('name') or ele is None: continue
    if mi(HOME, (e['lat'], e['lon'])) > MAX_HOME_MI: continue
    if ele < 150 and not re.search(r'\b(mount|mountain|mt)\b', t['name'], re.I): continue
    peaks.append({'id': e['id'], 'name': t['name'], 'lat': e['lat'], 'lon': e['lon'], 'ele_m': ele})
pgrid = defaultdict(list)
for p in peaks: pgrid[(round(p['lat'] * 50), round(p['lon'] * 50))].append(p)
def peaks_near(pt):
    k = (round(pt[0] * 50), round(pt[1] * 50))
    return [p for dx in (-1, 0, 1) for dy in (-1, 0, 1) for p in pgrid.get((k[0] + dx, k[1] + dy), []) if dist_m(pt, (p['lat'], p['lon'])) <= SUMMIT_REACH_M]

# ---------- trail network: every named path joined where they share points ----------
ways = []
for e in load('named_paths.json'):
    t = e.get('tags', {})
    name = t.get('name', '').strip()
    if not name or SKIP_NAMES.search(name) or t.get('piste:type'): continue
    if t.get('highway') == 'track' and not re.search(r'trail|path', name, re.I): continue
    g = [(round(p['lat'], 6), round(p['lon'], 6)) for p in e.get('geometry', []) if p]
    if len(g) >= 2: ways.append((name, g))
adj = defaultdict(list)
for name, g in ways:
    for i in range(1, len(g)):
        u, v = g[i - 1], g[i]
        if u == v: continue
        w = dist_m(u, v)
        adj[u].append((v, w, name)); adj[v].append((u, w, name))
vgrid = defaultdict(list)
for v in adj: vgrid[(round(v[0] * 100), round(v[1] * 100))].append(v)
def nearest_vertex(pt, max_m):
    k = (round(pt[0] * 100), round(pt[1] * 100)); best, bd = None, max_m
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for v in vgrid.get((k[0] + dx, k[1] + dy), []):
                d = dist_m(pt, v)
                if d < bd: best, bd = v, d
    return best
_ele = {}
def ele_cached(v):
    k = (round(v[0], 4), round(v[1], 4))
    if k not in _ele: _ele[k] = elevation_m(v[0], v[1], z=11)
    return _ele[k]
def dp_simplify(pts, tol_m=12):
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]
    kx = math.cos(math.radians(a[0])) * 111320
    def perp(p):
        ax, ay, bx, by, px, py = a[1] * kx, a[0] * 110540, b[1] * kx, b[0] * 110540, p[1] * kx, p[0] * 110540
        dx, dy = bx - ax, by - ay
        if dx == dy == 0: return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
    i, dmax = max(((i, perp(p)) for i, p in enumerate(pts[1:-1], 1)), key=lambda x: x[1])
    if dmax <= tol_m: return [a, b]
    return dp_simplify(pts[:i + 1], tol_m)[:-1] + dp_simplify(pts[i:], tol_m)
def hike_name(names_in_order, lengths):
    """Named for the trail that carries most of the hike; a second trail joins the name only when it
    covers at least 30% of the distance (e.g. "Brook Trail to Tumbledown Mountain Trail")."""
    total = sum(lengths.values()) or 1
    order = list(dict.fromkeys(names_in_order))
    big = [n for n in order if lengths[n] / total >= 0.30]
    if not big: big = [max(lengths, key=lengths.get)]
    return big[0] if len(big) == 1 else f'{big[0]} to {big[-1]}'

# Trailheads and parking areas: real starting points even where a trail continues across a road.
TH = []
for e in load('trailheads.json'):
    c = e.get('center') or (e if 'lat' in e else None)
    if c: TH.append((c['lat'], c['lon'], e.get('tags', {}).get('highway') == 'trailhead'))
th_vertices = {}
for lat_, lon_, is_th in TH:
    v = nearest_vertex((lat_, lon_), 250)
    if v: th_vertices[v] = th_vertices.get(v, False) or is_th
MAX_M = 7 * 1609.344
mountains = {}
for peak in peaks:
    top = nearest_vertex((peak['lat'], peak['lon']), 150)
    if not top: continue
    dist, prev, heap = {top: 0}, {}, [(0, top)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u] or d > MAX_M: continue
        for v, w, name in adj[u]:
            if d + w < dist.get(v, 1e18): dist[v] = d + w; prev[v] = (u, name, w); heapq.heappush(heap, (d + w, v))
    leaves = [v for v in dist if (len(adj[v]) == 1 or v in th_vertices) and dist[v] >= 400 and dist[v] <= MAX_M]
    if not leaves: continue
    cands = []
    for v in leaves:
        le = ele_cached(v)
        if le is None: continue
        climb_ft = (peak['ele_m'] - le) * 3.28084
        cands.append((v, dist[v], climb_ft))
    if not cands: continue
    top_climb = max(c[2] for c in cands)
    if top_climb < 120: continue
    # A start high on the mountain (network gap) is not a real approach for a tall peak.
    floor_ft = 0.3 * (peak['ele_m'] * 3.28084 - 800) if peak['ele_m'] * 3.28084 > 2500 else 120
    good = [c for c in cands if c[2] >= max(120, 0.55 * top_climb, floor_ft)]
    good.sort(key=lambda c: -(c[2] / 1000 - (c[1] / 1609.344) * 0.18 + (0.45 if c[0] in th_vertices else 0)))
    chosen = []
    for v, d, climb in good:
        if any(dist_m(v, c[0]) < 800 for c in chosen): continue
        path, names, lengths = [v], [], defaultdict(float)
        while path[-1] != top:
            u, name, w = prev[path[-1]]; names.append(name); lengths[name] += w; path.append(u)
        nm = hike_name(names, lengths)
        if any(nm == c[3] for c in chosen): continue
        chosen.append((v, d, climb, nm, path, sorted({p['name'] for q in path[::8] for p in peaks_near(q) if p['id'] != peak['id']})))
        if len(chosen) == 3: break
    m = mountains.setdefault(peak['id'], {'peak': peak, 'trails': []})
    def total_gain_ft(path):
        # Walk the route in 50 m steps on 30 m terrain and add up every climb bigger than 4 m.
        pts = []
        for i in range(1, len(path)):
            a, b = path[i - 1], path[i]; d = dist_m(a, b); n = max(1, int(d // 50))
            pts += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
        pts.append(path[-1])
        el = [elevation_m(p[0], p[1], z=12) for p in pts]
        el = [e for e in el if e is not None]
        if len(el) < 3: return None
        sm = [sum(el[max(0, i - 1):i + 2]) / len(el[max(0, i - 1):i + 2]) for i in range(len(el))]
        gain, low = 0.0, sm[0]
        for e in sm[1:]:
            if e < low: low = e
            elif e - low >= 4: gain += e - low; low = e
        return round(gain * 3.28084)
    for v, d, climb, nm, path, others in chosen:
        hike_mi = round(d / 1609.344 * 2, 1)
        up = total_gain_ft(path) or round(climb)
        up = max(up, round(climb))
        score = up / 1000 + hike_mi / 3
        hours = hike_mi / 2 + up / 2000
        m['trails'].append({'name': nm, 'hikeMi': hike_mi, 'oneWayMi': round(d / 1609.344, 2), 'routeType': 'Out-and-back', 'climbFt': round(climb), 'gainFt': up,
            'difficulty': 'Easy' if score < 1.3 else 'Moderate' if score < 2.8 else 'Hard', 'estimatedTime': f'{int(round(hours * 60)) // 60}h {int(round(hours * 60)) % 60:02d}m',
            'trailhead': [round(v[0], 5), round(v[1], 5)], 'trailheadEleFt': round(peak['ele_m'] * 3.28084 - climb),
            'alsoSummits': others[:4], 'line': [[round(p[1], 5), round(p[0], 5)] for p in dp_simplify(path)]})
mountains = {k: m for k, m in mountains.items() if m['trails']}
print('mountains with real approaches', len(mountains))
out, slugs = [], set()
for m in mountains.values():
    p = m['peak']; pt = (p['lat'], p['lon'])
    trails_sorted = sorted(m['trails'], key=lambda x: x['hikeMi'])
    town = town_of(pt); state = state_of(pt)
    if state == 'Other': continue
    base = re.sub(r'[^a-z0-9]+', '-', p['name'].lower()).strip('-')
    slug = base if base not in slugs else f'{base}-{re.sub(r"[^a-z0-9]+", "-", town.lower())}'
    slugs.add(slug)
    for i, tr in enumerate(trails_sorted): tr['id'] = f'osm-{slug}-{i + 1}'
    out.append({'id': slug, 'name': p['name'], 'eleFt': round(p['ele_m'] * 3.28084), 'lat': round(p['lat'], 5), 'lon': round(p['lon'], 5), 'state': state, 'town': town,
                'homeMi': round(mi(HOME, pt), 1), 'osmId': p['id'], 'trails': trails_sorted})
out.sort(key=lambda m: m['homeMi'])
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({'generatedAt': time.strftime('%Y-%m-%d'), 'home': HOME, 'radiusMi': MAX_HOME_MI,
    'sources': ['© OpenStreetMap contributors (ODbL): peaks, trails, towns, state lines', 'AWS Terrain Tiles: trailhead elevations'],
    'notes': 'hikeMi: out-and-back to the summit measured along the mapped trail. gainFt: total climbing on the way up (30 m terrain). climbFt: summit minus trailhead.',
    'mountains': out}, separators=(',', ':')), encoding='utf-8')
print('mountains', len(out), 'trails', sum(len(m['trails']) for m in out), 'bytes', OUT.stat().st_size)
from collections import Counter
print(Counter(m['state'] for m in out))
