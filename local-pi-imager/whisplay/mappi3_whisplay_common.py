from __future__ import annotations
import json, os, sys, textwrap, time
from pathlib import Path
from urllib import request, error
import math
from PIL import Image, ImageDraw, ImageFont

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'runtime'))
if RUNTIME_DIR not in sys.path:
    sys.path.append(RUNTIME_DIR)
try:
    from whisplay_client import create_whisplay_hardware
except Exception:
    create_whisplay_hardware = None

W, H = 240, 280
BG = (8, 18, 28)
GREEN = (70, 230, 150)
AMBER = (250, 190, 75)
BLUE = (90, 170, 255)
RED = (250, 95, 95)
WHITE = (236, 246, 255)
DIM = (130, 150, 168)

def rgb565_bytes(img: Image.Image) -> bytes:
    img = img.convert('RGB')
    out = bytearray(W * H * 2)
    i = 0
    for r, g, b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[i] = (v >> 8) & 255
        out[i+1] = v & 255
        i += 2
    return bytes(out)

def font(size=16, bold=False):
    names = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf' if bold else '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    ]
    for p in names:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()

F_TITLE = font(21, True)
F_BODY = font(15, False)
F_SMALL = font(12, False)
F_TINY = font(10, False)

def wrap(text, width=24):
    lines=[]
    for part in str(text).split('\n'):
        lines += textwrap.wrap(part, width=width) or ['']
    return lines

def draw_card(title, lines, accent=GREEN, footer='press = next · hold/gesture = exit'):
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, W-7, H-7), 12, outline=accent, width=2, fill=(12, 26, 38))
    d.text((16, 14), title[:20], font=F_TITLE, fill=accent)
    y = 48
    for line in lines[:12]:
        color = WHITE
        if line.startswith('!'):
            color = RED; line = line[1:]
        elif line.startswith('+'):
            color = GREEN; line = line[1:]
        elif line.startswith('~'):
            color = AMBER; line = line[1:]
        d.text((16, y), line[:28], font=F_BODY, fill=color)
        y += 18
    d.line((12, H-30, W-13, H-30), fill=(45, 70, 90), width=1)
    d.text((16, H-23), footer[:34], font=F_TINY, fill=DIM)
    return img

HERBIE_ASSET_ROOTS = [
    Path('/opt/mappi3/app/assets/herbie'),
    Path('/home/ubuntu/MapPi3/public/assets/herbie'),
]
HERBIE_EXPRESSION_ORDER = (
    'neutral','happy','excited','curious','thinking','side-eye','suspicious','confused','surprised',
    'worried','sad','angry','annoyed','tired','yawning','determined','focused','bored','sleepy',
    'chillin','meditating','laughing','cheeky','wow','love','grateful','blushing','sweating','melting',
    'overwhelmed','high-af','party-mode','greetings','wink','thumbs-up','thumbs-down','facepalm',
    'oh-no','face-with-tears','party-hard',
    'gps-searching','gps-locked','off-route','thirsty','cold','storm-alert','summit','charging',
    'middle-finger','falling'
)
HERBIE_MANUAL_ONLY = ('middle-finger',)   # never picked automatically
HERBIE_EXPRESSIONS = set(HERBIE_EXPRESSION_ORDER)
HERBIE_IDLE_PRIORITY = ('happy','curious','thinking','focused','wink','grateful','excited','greetings','cheeky','love')
HERBIE_RANDOM_CAMEOS = ('neutral','chillin','meditating','laughing','blushing','party-mode','party-hard','thumbs-up','side-eye','suspicious')
HERBIE_SCENARIO_ONLY = ('high-af','worried','sad','angry','annoyed','tired','yawning','sweating','melting','overwhelmed','thumbs-down','facepalm','oh-no','face-with-tears')

def herbie_asset_path(kind, name):
    safe_kind = str(kind or 'expressions').strip().replace('..','').replace('/','-')
    safe = str(name or 'happy').strip().replace('..','').replace('/','-')
    for root in HERBIE_ASSET_ROOTS:
        p = root / safe_kind / f'{safe}.png'
        try:
            if p.exists() and os.access(p, os.R_OK):
                return p
        except OSError:
            continue
    return None

# Gaze: every expression also exists as <name>-left / <name>-right. Herbie glances around on a
# fixed beat while he stays in a state: straight, straight, left, straight, right.
HERBIE_GAZE_CYCLE = ('center', 'center', 'left', 'center', 'right')
HERBIE_GAZE_BEAT_S = 3.0
# Motions with 3 frames (<name>, <name>-2, <name>-3) play as a short loop at this many seconds per frame.
HERBIE_MOTION_CYCLE_S = {'spinning': 0.4, 'shaking': 0.5, 'scanning': 0.6, 'bouncing': 0.8, 'happy-hover': 1.2}
# Frame order per motion ('' = base frame): spinning rocks both ways, scanning sweeps round.
HERBIE_MOTION_SEQUENCES = {'spinning': ('', '-2', '-3', '-2', '', '-4', '-5', '-4'), 'scanning': ('', '-4', '-2', '-5', '-3'), 'shaking': ('', '-2', '-3'), 'bouncing': ('', '-2', '-3', '-2'), 'happy-hover': ('', '-2', '-3')}
# Tilt levels: tilted-<dir>, tilted-<dir>-2, tilted-<dir>-3 at these Sense HAT angles.
HERBIE_TILT_LEVELS = (8.0, 18.0, 30.0)

def herbie_gaze_now(now_ts=None):
    t = time.time() if now_ts is None else now_ts
    return HERBIE_GAZE_CYCLE[int(t // HERBIE_GAZE_BEAT_S) % len(HERBIE_GAZE_CYCLE)]

def herbie_gaze_ref(ref, now_ts=None):
    """'happy' / 'expressions/happy' -> 'expressions/happy-left' on a glance beat (motions/turnarounds unchanged)."""
    raw = str(ref or '')
    t = time.time() if now_ts is None else now_ts
    if raw.startswith('motions/'):
        base = raw.split('/', 1)[1]
        beat = HERBIE_MOTION_CYCLE_S.get(base)
        if not beat:
            return raw
        frames = [f'{base}{sfx}' for sfx in HERBIE_MOTION_SEQUENCES.get(base, ('',)) if herbie_asset_path('motions', f'{base}{sfx}')] or [base]
        return 'motions/' + frames[int(t // beat) % len(frames)]
    if '/' in raw and not raw.startswith('expressions/'):
        return raw
    name = raw.split('/', 1)[-1]
    gaze = herbie_gaze_now(now_ts)
    if gaze == 'center' or name.endswith(('-left', '-right')) or not herbie_asset_path('expressions', f'{name}-{gaze}'):
        return raw
    return f'expressions/{name}-{gaze}'

def load_herbie_groups():
    for root in HERBIE_ASSET_ROOTS:
        try:
            groups = json.loads((root / 'manifest.json').read_text()).get('groups') or {}
            if groups:
                return groups
        except Exception:
            continue
    return {}

HERBIE_GROUPS = load_herbie_groups()

def load_herbie_compass():
    for root in HERBIE_ASSET_ROOTS:
        try:
            compass = json.loads((root / 'manifest.json').read_text()).get('compass')
            if compass:
                return compass
        except Exception:
            continue
    return None

# Live north needle over the compass painted on Herbie's map. The dashboard updates the heading
# from the Sense HAT (degrees clockwise from north that the top of the Pi points to).
HERBIE_COMPASS = load_herbie_compass()
LIVE_HEADING = [None]

def set_live_heading(sense):
    try:
        orient = sense.get('orientation') if isinstance(sense.get('orientation'), dict) else {}
        h = orient.get('north_heading', sense.get('compass'))
        LIVE_HEADING[0] = float(h) % 360 if h is not None else None
    except (TypeError, ValueError, AttributeError):
        LIVE_HEADING[0] = None

def compass_eligible(ref):
    raw = str(ref or '')
    if '/' not in raw or raw.startswith('expressions/'):
        return True
    kind, name = raw.split('/', 1)
    base = name.rstrip('0123456789').rstrip('-')
    return kind == 'motions' and HERBIE_COMPASS is not None and base in HERBIE_COMPASS.get('kinds', [])

def draw_compass_needle(img, x, y, scale, heading):
    """Cover the painted needle with the dial colour and draw a live one pointing to real north."""
    if not HERBIE_COMPASS or heading is None:
        return
    ss = 4
    cx0, cy0 = HERBIE_COMPASS['center']
    r_cover = HERBIE_COMPASS['cover_radius'] * scale
    r_needle = HERBIE_COMPASS['needle_length'] * scale
    size = int((r_cover + 2) * 2 * ss)
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = size / 2
    d.ellipse((c - r_cover * ss, c - r_cover * ss, c + r_cover * ss, c + r_cover * ss), fill=tuple(HERBIE_COMPASS['face_color']) + (255,))
    a = math.radians(-heading)                      # screen angle of north: the top of the Pi faces `heading`
    ux, uy = math.sin(a), -math.cos(a)
    px, py = -uy, ux
    w = 2.6 * scale * ss
    tip_n = (c + ux * r_needle * ss, c + uy * r_needle * ss)
    tip_s = (c - ux * r_needle * ss, c - uy * r_needle * ss)
    left, right = (c + px * w, c + py * w), (c - px * w, c - py * w)
    d.polygon([tip_s, left, right], fill=(70, 62, 44, 255), outline=(30, 26, 18, 255))
    d.polygon([tip_n, left, right], fill=(206, 44, 36, 255), outline=(90, 16, 12, 255))
    pin = 2.2 * scale * ss
    d.ellipse((c - pin, c - pin, c + pin, c + pin), fill=(176, 132, 58, 255), outline=(60, 42, 16, 255))
    layer = layer.resize((size // ss, size // ss), Image.LANCZOS)
    img.paste(layer, (int(round(x + cx0 * scale - layer.width / 2)), int(round(y + cy0 * scale - layer.height / 2))), layer)

def herbie_group_face(group, fallback='happy', period=15.0, now_ts=None):
    """Pick from an event group, moving to the next face every `period` seconds."""
    faces = [f for f in HERBIE_GROUPS.get(group, []) if f not in HERBIE_MANUAL_ONLY or group == 'rude']
    if not faces:
        return fallback
    t = time.time() if now_ts is None else now_ts
    return faces[int(t // max(1.0, period)) % len(faces)]

def herbie_asset_ref(kind, name):
    return f'{kind}/{name}' if herbie_asset_path(kind, name) else None

def herbie_asset_path_from_ref(ref):
    raw = str(ref or 'happy').strip()
    if '/' in raw:
        kind, name = raw.split('/', 1)
        return herbie_asset_path(kind, name)
    return herbie_asset_path('expressions', raw)

def herbie_asset_label(ref):
    raw = str(ref or 'happy').strip()
    return raw.split('/', 1)[-1].replace('-', ' ')

# Herbie's eyes sit in a different spot on every face, so the old drawn "eyelid" bar landed across
# the face like a loading bar. Blink by briefly swapping calm faces to closed-eye artwork instead.
BLINK_FACE = 'meditating'
BLINKABLE_FACES = {'neutral', 'happy', 'curious', 'focused', 'chillin', 'determined', 'grateful', 'greetings', 'thinking'}

def blink_face(ref):
    raw = str(ref or '')
    name = raw.split('/', 1)[1] if raw.startswith('expressions/') else raw
    return BLINK_FACE if name in BLINKABLE_FACES else ref

def draw_face(mood='happy', caption='ready to roam', blink=False):
    mood = str(mood or 'happy')
    if blink:
        mood = str(blink_face(mood))
    p = herbie_asset_path_from_ref(mood)
    if mood not in HERBIE_EXPRESSIONS and not p:
        mood = 'happy'
        p = herbie_asset_path('expressions', mood)
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    accent = AMBER if mood in ('worried','confused','surprised','tired','yawning','sweating','oh-no') or mood.startswith('turnarounds/') or mood.startswith('motions/') else GREEN
    d.rounded_rectangle((6, 6, W-7, H-7), 12, outline=accent, width=2, fill=(14, 28, 36))
    d.text((16, 14), 'Herbie', font=F_TITLE, fill=accent)
    if p:
        try:
            face = Image.open(p).convert('RGBA')
            face.thumbnail((210, 158), Image.LANCZOS)
            x = (W - face.width) // 2
            y = 54 + max(0, (150 - face.height) // 2)
            img.paste(face, (x, y), face)
            if compass_eligible(mood):
                draw_compass_needle(img, x, y, face.width / 300.0, LIVE_HEADING[0])
        except Exception:
            p = None
    if not p:
        d.ellipse((48, 68, 192, 212), fill=(245, 220, 115), outline=(90, 70, 20), width=3)
        d.ellipse((82, 112, 100, 130), fill=(20, 30, 35))
        d.ellipse((140, 112, 158, 130), fill=(20, 30, 35))
        d.arc((78, 128, 162, 184), 20, 160, fill=(35, 30, 25), width=4)
    d.text((16, 214), str(caption or mood).replace('_',' ')[:27], font=F_BODY, fill=accent)
    d.text((16, H-23), 'press = status · exit gesture backs out', font=F_TINY, fill=DIM)
    return img

def show(hw, img):
    data = rgb565_bytes(img)
    if hasattr(hw, 'draw_image'):
        hw.draw_image(0, 0, W, H, data)
    elif hasattr(hw, 'display'):
        hw.display(img)

def load_env(path):
    vals={}
    try:
        for line in Path(path).read_text().splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k,v=line.split('=',1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return vals

def http_json(url, timeout=2.5):
    with request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def create_hw(app_id, name, icon, priority=70):
    if create_whisplay_hardware is None:
        raise RuntimeError('Whisplay runtime missing')
    return create_whisplay_hardware(app_id=app_id, display_name=name, icon=icon, priority=priority, exit_gesture='quad_click', use_daemon_default_log=True)
