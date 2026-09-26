"""Fetch named backcountry campsites, lean-tos and huts around home base from OpenStreetMap (Overpass)."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
src = (pathlib.Path(__file__).parent / 'fetch_osm.py').read_text(encoding='utf-8')
ns = {'__file__': str(pathlib.Path(__file__).parent / 'fetch_osm.py'), '__name__': 'fetch'}
exec(src[:src.index('lat, lon = HOME')], ns)
lat, lon = ns['HOME']; R = ns['RADIUS_M']
q = f'''[out:json][timeout:240];(
  nwr["tourism"~"^(camp_site|wilderness_hut|alpine_hut)$"](around:{R},{lat},{lon});
  nwr["amenity"="shelter"]["name"](around:{R},{lat},{lon});
);out center tags;'''
camps = ns['overpass'](q, 'camps_v2.json')
print('camp features', len(camps['elements']), 'named', sum(1 for e in camps['elements'] if e.get('tags', {}).get('name')))
