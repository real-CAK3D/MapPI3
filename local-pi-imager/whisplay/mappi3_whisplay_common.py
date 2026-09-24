from __future__ import annotations
import json, os, sys, textwrap, time
from pathlib import Path
from urllib import request, error
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
    'gps-searching','gps-locked','off-route','thirsty','cold','storm-alert','summit','charging'
)
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
