#!/usr/bin/env python3
import importlib.util, pathlib, tempfile, json, random
path = pathlib.Path('local-pi-imager/boot-partition-copy/mappi3-agent.py')
spec = importlib.util.spec_from_file_location('mappi3_agent_verify', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
tmp = pathlib.Path(tempfile.mkdtemp(prefix='mappi3-sense-'))
mod.STATE = tmp / 'state.json'
mod.APP_DIR = tmp / 'app'
mod.APP_DIR.mkdir(parents=True, exist_ok=True)

class FakeSense:
    def __init__(self):
        self.frames = []
        self.messages = []
        self.clears = []
    def set_pixels(self, pixels):
        assert isinstance(pixels, list) and len(pixels) == 64
        for px in pixels:
            assert isinstance(px, list) and len(px) == 3
            assert all(isinstance(v, int) and 0 <= v <= 255 for v in px), px
        self.frames.append([p[:] for p in pixels])
    def clear(self, r=0, g=0, b=0):
        self.clears.append([int(r), int(g), int(b)])
        self.frames.append([[int(r), int(g), int(b)] for _ in range(64)])
    def show_message(self, text, text_colour=None, scroll_speed=0.06):
        self.messages.append((str(text), list(text_colour or []), scroll_speed))

def lit(pixels):
    return {i for i, c in enumerate(pixels) if c != [0, 0, 0]}

def xy(i):
    return (i % 8, i // 8)

base_state = {
    'sense_brightness_level': 4,
    'sense_rotation': 0,
    'sense_color': '#00aa55',
    'route_progress': 0.42,
    'route_distance_miles': 4.2,
    'sense_message': 'MAPPI3 TEST',
    'sense_custom_pixels': [[0, 0, 0] for _ in range(64)],
}
orient = {'roll': 3.0, 'pitch': -2.0}
results = []
for mode in mod.SENSE_MODES:
    sense = FakeSense()
    st = dict(base_state)
    mod.write_state(st)
    try:
        if mode in ('compass', 'compass-arrow'):
            mod.draw_compass(sense, 45, st)
        elif mode == 'compass-cardinal':
            mod.draw_compass_cardinal(sense, 45, st)
        elif mode == 'rotation-test':
            mod.draw_rotation_test(sense, st, 3)
        elif mode == 'liquid':
            mod.draw_liquid(sense, orient, 3, st)
        elif mode == 'pacman':
            mod.PACMAN_STATE = {}
            for t in range(24):
                mod.draw_pacman_frame(sense, t, st)
            cache = mod.sense_snapshot().get('pacman_display', {})
            assert cache.get('ghosts') == 4 and cache.get('frame_sleep') == mod.PACMAN_FRAME_SLEEP
            assert cache.get('fruit_count', 0) >= 0 and cache.get('lit_leds', 0) >= 8
        elif mode == 'weather':
            mod.draw_weather(sense, 72, 55, 1012)
        elif mode == 'fire':
            mod.draw_fire(sense, 3)
        elif mode == 'flashlight':
            mod.draw_flashlight(sense, st)
        elif mode == 'sos':
            mod.draw_sos(sense, 2)
        elif mode == 'message':
            mod.text_once(sense, st['sense_message'], (0, 150, 80), 0.055)
        elif mode == 'boot':
            mod.text_once(sense, 'WELCOME TO THE WILDERNESS', (0, 120, 20), 0.055)
        elif mode == 'sun':
            mod.draw_sun(sense, {'sun_message': 'SUN TEST'})
        elif mode == 'gps':
            mod.draw_gps(sense, {'mode': 3, 'satellites': 6}, st)
        elif mode == 'clock':
            mod.text_once(sense, '12:34 PM', (80, 80, 180), 0.055)
        elif mode == 'progress':
            mod.draw_route_progress(sense, st)
        elif mode == 'beacon':
            sense.clear(0, 80, 120)
        elif mode == 'stars':
            pixels = [[0, 0, 0] for _ in range(64)]
            for _ in range(10):
                pixels[random.randrange(64)] = [40, 40, 120]
            mod.sense_set_pixels(sense, pixels, st)
        elif mode == 'temp':
            mod.draw_bar(sense, 32, (0, 120, 0))
        elif mode == 'humidity':
            mod.draw_bar(sense, 44, (0, 60, 180))
        elif mode == 'pressure':
            mod.draw_bar(sense, 38, (120, 80, 180))
        elif mode == 'avatar':
            mod.draw_sense_animated_face(sense, 1, st, orient, 68)
        elif mode == 'level':
            mod.draw_level(sense, orient, st)
        elif mode == 'custom':
            mod.draw_custom_pixels(sense, {**st, 'sense_custom_pixels': [[255, 0, 0] if i in (0, 63) else [0, 0, 0] for i in range(64)]})
        elif mode == 'border':
            mod.draw_border(sense, (0, 170, 85))
        elif mode == 'magic8':
            mod.text_once(sense, 'YES', (80, 0, 180), 0.055)
        elif mode == 'water':
            mod.draw_water_icon(sense, (0, 90, 220))
        elif mode == 'snake':
            mod.draw_snake_frame(sense, 3, (0, 220, 70))
        ok = bool(sense.frames or sense.messages)
        assert ok, mode
        results.append((mode, 'message' if sense.messages and not sense.frames else len(lit(sense.frames[-1]))))
    except Exception as e:
        raise AssertionError(f'mode {mode} failed: {e}')

sense = FakeSense()
mod.draw_sense_animated_face(sense, 1, base_state, orient, 68)
coords = {xy(i) for i in lit(sense.frames[-1])}
for forbidden in [(3,0),(4,0),(3,1),(4,1),(3,2),(4,2),(0,3),(7,3),(0,4),(7,4),(0,5),(7,5),(2,7),(3,7),(4,7),(5,7)]:
    assert forbidden not in coords, ('forbidden lit', forbidden, sorted(coords))
for center in [(1,1),(6,1)]:
    assert center not in coords, ('eye center lit', center)
assert {(0,0),(2,0),(5,0),(7,0),(1,5),(6,5)} & coords
blink_sense = FakeSense()
mod.draw_sense_animated_face(blink_sense, 10, base_state, orient, 68)
blink_coords = {xy(i) for i in lit(blink_sense.frames[-1])}
for center in [(1,1),(6,1)]:
    assert center not in blink_coords, ('blink eye center lit', center, sorted(blink_coords))
for label, expected in [('Pac-Man','pacman'),('Animated Face','avatar'),('Compass NSEW','compass-cardinal'),('Bubble Level','level')]:
    data = mod.set_sense_mode(label, {'brightnessLevel': 4, 'routeProgress': 0.5})
    assert data['ok'] and data['sense_mode'] == expected, data
print('AD_HOC_VERIFY_RESULT=PASS')
print('modes_checked=', len(results), [r[0] for r in results])
print('avatar_lit_coords=', sorted(coords))
print('pacman_cache=', json.dumps(mod.sense_snapshot().get('pacman_display', {}), sort_keys=True))
