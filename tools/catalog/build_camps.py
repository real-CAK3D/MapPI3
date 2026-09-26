"""Backcountry campsites, lean-tos and huts with real approaches from trailheads.

Uses the same trail network, trailheads and terrain as build_catalog.py (run fetch_osm.py and
fetch_camps.py first). Writes public/catalog/camps.json.
Each approach is measured along the mapped trail from a trailhead or parking area to the site, with
the climb going in and the climb coming back out. Drive-in campgrounds are listed without approaches.
"""
import json, math, pathlib, re, time, heapq
from collections import defaultdict

HERE = pathlib.Path(__file__).parent
src = (HERE / 'build_catalog.py').read_text(encoding='utf-8')
ns = {'__file__': str(HERE / 'build_catalog.py'), '__name__': 'camps'}
exec(src[:src.index('MAX_M = 7 * 1609.344')], ns)
g = ns
dist_m, mi, adj, nearest_vertex, th_vertices = g['dist_m'], g['mi'], g['adj'], g['nearest_vertex'], g['th_vertices']
elevation_m, dp_simplify, hike_name, state_of, town_of, HOME = g['elevation_m'], g['dp_simplify'], g['hike_name'], g['state_of'], g['town_of'], g['HOME']
MAX_HOME_MI = g['MAX_HOME_MI']

def total_gain_ft(path):
    pts = []
    for i in range(1, len(path)):
        a, b = path[i - 1], path[i]; d = dist_m(a, b); n = max(1, int(d // 50))
        pts += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    pts.append(path[-1])
    el = [elevation_m(p[0], p[1], z=12) for p in pts]
    el = [e for e in el if e is not None]
    if len(el) < 3: return 0
    sm = [sum(el[max(0, i - 1):i + 2]) / len(el[max(0, i - 1):i + 2]) for i in range(len(el))]
    gain, low = 0.0, sm[0]
    for e in sm[1:]:
        if e < low: low = e
        elif e - low >= 4: gain += e - low; low = e
    return round(gain * 3.28084)

SKIP_SHELTER = {'gazebo', 'picnic_shelter', 'public_transport', 'pavilion', 'sun_shelter', 'field_shelter', 'rock_shelter'}
feats = json.loads((HERE / 'cache' / 'camps_v2.json').read_text(encoding='utf-8'))['elements']
MAX_M = 12 * 1609.344
out, seen = [], set()
for e in feats:
    t = e.get('tags', {}); name = (t.get('name') or '').strip()
    c = e.get('center') or (e if 'lat' in e else None)
    if not name or not c: continue
    if t.get('amenity') == 'shelter' and t.get('shelter_type') in SKIP_SHELTER: continue
    pt = (c['lat'], c['lon'])
    if mi(HOME, pt) > MAX_HOME_MI: continue
    key = (name.lower(), round(pt[0], 3), round(pt[1], 3))
    if key in seen: continue
    seen.add(key)
    state = state_of(pt)
    if state == 'Other': continue
    kind = 'hut' if t.get('tourism') in ('wilderness_hut', 'alpine_hut') else 'shelter' if t.get('amenity') == 'shelter' else 'campsite'
    # Spurs to a site are often unnamed paths missing from the network, so the walk can join the
    # trail anywhere within 250 m; that last bit counts as straight-line distance x 1.3.
    k = (round(pt[0] * 100), round(pt[1] * 100))
    joins = [v for dx in (-1, 0, 1) for dy in (-1, 0, 1) for v in g['vgrid'].get((k[0] + dx, k[1] + dy), []) if dist_m(pt, v) <= 250]
    camp_v = pt if joins else None
    approaches = []
    if camp_v:
        dist, prev, heap = {camp_v: 0}, {}, [(0, camp_v)]
        for v in joins:
            w = dist_m(pt, v) * 1.3
            if w < dist.get(v, 1e18): dist[v] = w; prev[v] = (camp_v, None, w); heapq.heappush(heap, (w, v))
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u] or d > MAX_M: continue
            if u == camp_v: continue
            for v, w, nm in adj[u]:
                if d + w < dist.get(v, 1e18): dist[v] = d + w; prev[v] = (u, nm, w); heapq.heappush(heap, (d + w, v))
        starts = sorted((v for v in dist if v in th_vertices and dist[v] >= 300), key=lambda v: dist[v] - (400 if th_vertices[v] else 0))
        for v in starts:
            if any(dist_m(v, a['_v']) < 1500 for a in approaches): continue
            path, names, lengths = [v], [], defaultdict(float)
            while path[-1] != camp_v:
                u, nm, w = prev[path[-1]]
                if nm: names.append(nm); lengths[nm] += w
                path.append(u)
            nm = hike_name(names, lengths) if lengths else "Access path"
            gin, gout = total_gain_ft(path), total_gain_ft(path[::-1])
            one = dist[v] / 1609.344
            hours = one / 2 + gin / 2000
            th_e = elevation_m(v[0], v[1], z=12)
            approaches.append({'_v': v, 'name': nm, 'oneWayMi': round(one, 2), 'gainInFt': gin, 'gainOutFt': gout,
                'estimatedTime': f'{int(round(hours * 60)) // 60}h {int(round(hours * 60)) % 60:02d}m',
                'trailhead': [round(v[0], 5), round(v[1], 5)], 'trailheadEleFt': round(th_e * 3.28084) if th_e is not None else None,
                'line': [[round(p[1], 5), round(p[0], 5)] for p in dp_simplify(path)]})
            if len(approaches) == 3: break
    near_road = bool(approaches) and approaches[0]['oneWayMi'] < 0.25
    backcountry = t.get('backcountry') == 'yes' or kind in ('hut', 'shelter') or (bool(approaches) and not near_road and t.get('backcountry') != 'no')
    if not backcountry: kind = 'campground'
    ele = elevation_m(pt[0], pt[1], z=12)
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    base, n = slug, 2
    while any(o['id'] == slug for o in out): slug = f'{base}-{n}'; n += 1
    for i, a in enumerate(approaches): a.pop('_v'); a['id'] = f'camp-{slug}-{i + 1}'
    out.append({'id': slug, 'name': name, 'kind': kind, 'lat': round(pt[0], 5), 'lon': round(pt[1], 5),
        'eleFt': round(ele * 3.28084) if ele is not None else None, 'state': state, 'town': town_of(pt), 'homeMi': round(mi(HOME, pt), 1),
        'operator': t.get('operator'), 'fee': t.get('fee'), 'reservation': t.get('reservation'), 'capacity': t.get('capacity'),
        'water': t.get('drinking_water') or t.get('water_source'), 'fire': t.get('openfire') or t.get('fireplace'), 'website': t.get('website'),
        'approaches': approaches if kind != 'campground' else []})
out.sort(key=lambda c: c['homeMi'])
dest = HERE.parent.parent / 'public' / 'catalog' / 'camps.json'
dest.write_text(json.dumps({'generatedAt': time.strftime('%Y-%m-%d'), 'home': HOME,
    'sources': ['© OpenStreetMap contributors (ODbL): campsites, shelters, trails', 'AWS Terrain Tiles: elevation'],
    'notes': 'oneWayMi measured along the mapped trail from a trailhead or parking area. gainInFt: climbing on the way in; gainOutFt: climbing on the way back out.',
    'camps': out}, separators=(',', ':')), encoding='utf-8')
from collections import Counter
print('camps', len(out), Counter(c['kind'] for c in out), 'with approaches', sum(1 for c in out if c['approaches']), 'bytes', dest.stat().st_size)
sp = [c for c in out if 'Speck' in c['name']]
for c in sp: print(c['name'], c['operator'], c['fee'], [(a['name'], a['oneWayMi'], a['gainInFt'], a['gainOutFt'], a['trailhead']) for a in c['approaches']])
