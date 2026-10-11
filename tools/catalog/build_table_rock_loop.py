"""Build the full Table Rock loop (Grafton Notch) from OpenStreetMap and measure it.

Loop: Grafton Notch parking -> AT a few hundred feet -> Table Rock Trail (orange, steep, boulder scramble)
up to the ledge -> connector path up to the Appalachian Trail -> AT back down to the parking lot.
Writes the geometry, distance, climb and mile-marked waypoints into src/data/routePacks.json.
"""
import json, math, pathlib

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent.parent
area = {e['id']: [(p['lat'], p['lon']) for p in e['geometry']] for e in json.load(open(HERE / 'cache' / 'table_rock_area.json'))['elements']}
TRT, CONNECTOR, AT_UP, AT_LINK = area[243581100], area[243581114], area[913319332], area[913319330]

def dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))
def nearest(line, pt):
    i = min(range(len(line)), key=lambda k: dist_m(line[k], pt)); return i, dist_m(line[i], pt)

parking = AT_LINK[-1]                                   # Grafton Notch lot, where the AT leaves Route 26
i_trt, d1 = nearest(AT_UP, TRT[0])                      # Table Rock Trail turnoff on the AT
i_top, d2 = nearest(AT_UP, CONNECTOR[0])                # where the connector rejoins the AT higher up
i_lot, d3 = nearest(AT_UP, AT_LINK[0])
j_ledge, d4 = nearest(CONNECTOR, TRT[-1])               # connector meets the ledge end of Table Rock Trail
print('junction gaps (m):', round(d1), round(d2), round(d3), round(d4))

def seg(line, a, b):
    return line[a:b + 1] if a <= b else list(reversed(line[b:a + 1]))
loop = [parking] + list(reversed(AT_LINK))[1:]          # lot -> start of AT_UP
loop += seg(AT_UP, i_lot, i_trt)[1:]                    # short AT piece to the turnoff
loop += TRT[1:] if dist_m(TRT[0], loop[-1]) < 80 else TRT
loop += seg(CONNECTOR, j_ledge, 0)[1:]                  # ledge -> up to the AT
loop += seg(AT_UP, i_top, i_lot)[1:]                    # AT back down
loop += AT_LINK[1:]                                     # into the lot

# measure: length along the line, climb from terrain tiles (same method as the mountain catalog)
src = (HERE / 'build_catalog.py').read_text(encoding='utf-8')
ns = {'__file__': str(HERE / 'build_catalog.py'), '__name__': 'trl'}
exec(src[:src.index('# ---------- states and towns ----------')], ns)
elev = ns['elevation_m']
cum = [0.0]
for a, b in zip(loop, loop[1:]): cum.append(cum[-1] + dist_m(a, b))
pts = []
for a, b in zip(loop, loop[1:]):
    n = max(1, int(dist_m(a, b) // 20))
    pts += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
pts.append(loop[-1])
el = [e for e in (elev(p[0], p[1], z=13) for p in pts) if e is not None]
sm = [sum(el[max(0, i - 2):i + 3]) / len(el[max(0, i - 2):i + 3]) for i in range(len(el))]
gain, low = 0.0, sm[0]
for e in sm[1:]:
    if e < low: low = e
    elif e - low >= 3: gain += e - low; low = e
miles = cum[-1] / 1609.344
gain_ft = round(gain * 3.28084)
mi_at = lambda pt, end=False: round(cum[-1 if end else nearest(loop, pt)[0]] / 1609.344, 2)   # the lot is both ends
top_ft = round(max(el) * 3.28084); lot_ft = round(el[0] * 3.28084)
print(f'loop {miles:.2f} mi, climb {gain_ft} ft, lot {lot_ft} ft, high point {top_ft} ft, {len(loop)} points')

ledge = TRT[-1]
wps = [
    ('Grafton Notch parking', 'Start', parking, 'Route 26 lot. Day-use fee for Grafton Notch State Park.'),
    ('Table Rock Trail turnoff', 'Junction', AT_UP[i_trt], 'Leave the AT here: orange-blazed Table Rock Trail, steep.'),
    ('Boulder scramble', 'Climb', TRT[len(TRT) // 3], 'Hands-on rock steps; slow down when wet.'),
    ('Table Rock ledge', 'View', ledge, 'Big drop-offs. Stay back from the edge. Then follow the connector path up to the AT.'),
    ('Rejoin the Appalachian Trail', 'Junction', AT_UP[i_top], 'Turn left (west) on the AT, downhill to the lot.'),
    ('Back at the parking lot', 'Finish', loop[-1], ''),
]
packs_path = ROOT / 'src' / 'data' / 'routePacks.json'
packs = json.load(open(packs_path, encoding='utf-8'))
r = next(p for p in packs if p['id'] == 'me-grafton-table-rock')
hours = miles / 1.5 + gain_ft / 1000 * 0.5          # slower than flat: steep scramble on the way up
r.update({
    'name': 'Table Rock Loop (Grafton Notch)',
    'routeType': 'Loop', 'distanceMiles': round(miles, 1), 'elevationGainFt': gain_ft,
    'estimatedTime': f'{int(hours)}h {int(round((hours % 1) * 60)):02d}m',
    'summary': f'Steep Table Rock Trail up to the ledge, then down the Appalachian Trail. {round(miles, 1)} mi loop with {gain_ft:,} ft of climbing from the Route 26 lot ({lot_ft:,} ft) to about {top_ft:,} ft. Boulder scramble and cliff edges at the top.',
    'geometry': {'type': 'LineString', 'coordinates': [[round(lo, 6), round(la, 6)] for la, lo in loop]},
    'geometryQuality': 'OpenStreetMap trails (Table Rock Trail, connector, Appalachian Trail)',
    'statsCheck': {'status': 'measured', 'checked': '2026-10-10', 'note': f'Measured along the mapped OpenStreetMap trails, with climbing from terrain elevation data ({round(miles, 2)} mi, {gain_ft} ft).'},
    'waypoints': [{'id': f'tr-{i}', 'name': n, 'type': t, 'mile': mi_at(pt, t == 'Finish'), 'lat': round(pt[0], 6), 'lon': round(pt[1], 6), 'notes': note} for i, (n, t, pt, note) in enumerate(wps)],
    'segments': [
        {'id': 'seg-1', 'name': 'AT to the Table Rock Trail turnoff', 'startMile': 0.0, 'endMile': mi_at(AT_UP[i_trt]), 'color': '#9ce36c'},
        {'id': 'seg-2', 'name': 'Table Rock Trail climb', 'startMile': mi_at(AT_UP[i_trt]), 'endMile': mi_at(ledge), 'color': '#ff8a4b'},
        {'id': 'seg-3', 'name': 'Connector up to the AT', 'startMile': mi_at(ledge), 'endMile': mi_at(AT_UP[i_top]), 'color': '#4bd2ff'},
        {'id': 'seg-4', 'name': 'Appalachian Trail down to the lot', 'startMile': mi_at(AT_UP[i_top]), 'endMile': round(miles, 2), 'color': '#ffd36a'},
    ],
    'noCatalogTwin': True,
})
for k in ('gain', 'time', 'miles'):
    if k in r: r[k] = {'gain': f'{gain_ft:,} ft', 'time': r['estimatedTime'], 'miles': round(miles, 1)}[k]
open(packs_path, 'w', encoding='utf-8', newline='\n').write(json.dumps(packs, indent=2) + '\n')
print('waypoints:', [(w['name'], w['mile']) for w in r['waypoints']])
