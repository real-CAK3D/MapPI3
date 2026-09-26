"""Fetch named peaks and hiking route relations around home base from OpenStreetMap (Overpass)."""
import json, sys, time, urllib.parse, urllib.request, pathlib
HOME = (44.1004, -70.2148)
RADIUS_M = 165000
OUT = pathlib.Path(__file__).parent / 'cache'
def overpass(q, name):
    p = OUT / name
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    data = urllib.parse.urlencode({'data': q}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request('https://overpass-api.de/api/interpreter', data=data, headers={'User-Agent': 'MapPI3-catalog-builder/1.0 (personal trail app)'})
            with urllib.request.urlopen(req, timeout=300) as r:
                js = json.loads(r.read().decode())
            p.write_text(json.dumps(js), encoding='utf-8')
            return js
        except Exception as e:
            print('retry', name, e, file=sys.stderr); time.sleep(20)
    raise SystemExit('overpass failed')
lat, lon = HOME
peaks = overpass(f'[out:json][timeout:240];node["natural"="peak"]["name"](around:{RADIUS_M},{lat},{lon});out body;', 'peaks.json')
routes = overpass(f'[out:json][timeout:280];relation["route"="hiking"]["name"](around:{RADIUS_M},{lat},{lon});out body geom;', 'hiking_routes.json')
print('peaks', len(peaks['elements']), 'with ele', sum(1 for e in peaks['elements'] if e.get('tags', {}).get('ele')))
print('hiking relations', len(routes['elements']))
paths = overpass(f'[out:json][timeout:300][maxsize:1073741824];way["highway"~"^(path|footway|track|bridleway|steps)$"]["name"](around:{RADIUS_M},{lat},{lon});out tags geom qt;', 'named_paths.json')
print('named paths', len(paths['elements']))
states = overpass('[out:json][timeout:300][maxsize:1073741824];relation["boundary"="administrative"]["admin_level"="4"]["name"~"^(Maine|New Hampshire|Vermont|Massachusetts)$"];out geom;', 'states.json')
print('states', [e['tags']['name'] for e in states['elements']])
places = overpass(f'[out:json][timeout:200];node["place"~"^(city|town|village)$"]["name"](around:{RADIUS_M + 30000},{lat},{lon});out body;', 'places.json')
print('places', len(places['elements']))
ths = overpass(f'[out:json][timeout:240];(node["highway"="trailhead"](around:{RADIUS_M},{lat},{lon});nwr["amenity"="parking"](around:{RADIUS_M},{lat},{lon}););out center tags;', 'trailheads.json')
print('trailheads+parking', len(ths['elements']))
