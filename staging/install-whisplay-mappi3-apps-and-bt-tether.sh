#!/usr/bin/env bash
set -euo pipefail

WHISPLAY_DIR="${WHISPLAY_DIR:-/opt/whisplay/Whisplay-main}"
APP_DIR="${APP_DIR:-/home/mappi3/.whisplay-daemon/app}"
EXAMPLE_DIR="$WHISPLAY_DIR/example"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/opt/whisplay/backups/mappi3-whisplay-apps-bt-$STAMP"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR" "$APP_DIR" "$EXAMPLE_DIR" /usr/local/bin /etc/mappi3
for f in \
  "$EXAMPLE_DIR/mappi3_whisplay_dashboard.py" \
  "$EXAMPLE_DIR/mappi3_whisplay_ai_chat.py" \
  "$APP_DIR/whisplay-mappi3-dashboard.json" \
  "$APP_DIR/whisplay-mappi3-ai-chat.json" \
  /usr/local/bin/mappi3-bt-pan-client.sh \
  /etc/systemd/system/mappi3-bt-pan-client.service \
  /etc/mappi3/whisplay-ai.env \
  /etc/mappi3/bt-pan.env \
  /boot/firmware/config.txt; do
  if [ -e "$f" ]; then
    cp -a "$f" "$BACKUP_DIR/$(basename "$f")"
  fi
done

cat > /etc/mappi3/whisplay-ai.env <<'EOF'
# Home-mode AI backend for the Whisplay chatbot.
# NukeBox Ollama is reachable directly on the MapPI3 hotspot client IP when NukeBox is connected to MapPI3.
OLLAMA_HOST=http://10.42.0.38:11434
OLLAMA_MODEL=
OLLAMA_TIMEOUT=35
EOF

cat > "$EXAMPLE_DIR/mappi3_whisplay_common.py" <<'PY'
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

def draw_face(mood='happy'):
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, W-7, H-7), 12, outline=GREEN, width=2, fill=(14, 28, 36))
    d.text((16, 14), 'MapPI3 Buddy', font=F_TITLE, fill=GREEN)
    cx, cy = 120, 138
    d.ellipse((48, 68, 192, 212), fill=(245, 220, 115), outline=(90, 70, 20), width=3)
    d.ellipse((82, 112, 100, 130), fill=(20, 30, 35))
    d.ellipse((140, 112, 158, 130), fill=(20, 30, 35))
    if mood in ('warn','hot'):
        d.arc((80, 140, 160, 190), 200, 340, fill=(35, 30, 25), width=4)
        d.text((70, 224), 'trail-check mode', font=F_BODY, fill=AMBER)
    else:
        d.arc((78, 128, 162, 184), 20, 160, fill=(35, 30, 25), width=4)
        d.text((72, 224), 'ready to roam', font=F_BODY, fill=GREEN)
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
PY

cat > "$EXAMPLE_DIR/mappi3_whisplay_dashboard.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations
import json, random, time
from urllib import request
from mappi3_whisplay_common import *

API = 'http://127.0.0.1:5050'
running = True
page = 0
seen_popup_events = set()
popup_event = None
popup_until = 0.0
snake = {'body': [(4,4),(3,4),(2,4)], 'dir': (1,0), 'food': (6,4), 'score': 0, 'over': False, 'last_emit': 0.0}
PAGES = ['Buddy Home','Field Kit','Compass+Level','Weather+Sky','Network','Safety','Snake Trail']

def api(path, timeout=1.5):
    try:
        with request.urlopen(API + path, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}

def post_command(name, payload=None, timeout=1.8):
    body = json.dumps(payload or {}).encode('utf-8')
    req = request.Request(API + '/api/command/' + name, data=body, headers={'Content-Type':'application/json'}, method='POST')
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'ok': False, '_error': str(e)}

def sense_payload(data):
    if not isinstance(data, dict):
        return {}
    return data.get('sense') if isinstance(data.get('sense'), dict) else data

def tone(ok, warn=False):
    return '+' if ok and not warn else '~' if ok else '!'

def lines_fieldkit():
    status = api('/api/status'); net = api('/api/network/status'); sense = sense_payload(api('/api/sense'))
    stats = status.get('stats') if isinstance(status.get('stats'), dict) else status.get('system') if isinstance(status.get('system'), dict) else {}
    disk = stats.get('disk') if isinstance(stats.get('disk'), dict) else {}
    mem = stats.get('memory') if isinstance(stats.get('memory'), dict) else {}
    temp = stats.get('temperature_c') or sense.get('temperature') or sense.get('temp_c')
    uptime = stats.get('uptime_seconds') or status.get('uptime_seconds') or status.get('uptime')
    net_text = json.dumps(net).lower() if isinstance(net, dict) else ''
    hotspot = bool(net.get('hotspot_active') or 'mappi3-hotspot' in net_text) if isinstance(net, dict) else False
    tailscale = 'tailscale' in net_text and 'offline' not in net_text
    api_ok = not status.get('_error')
    caution = (isinstance(disk.get('percent'), (int,float)) and disk.get('percent') > 85) or (isinstance(temp, (int,float)) and temp > 70)
    ready = api_ok and hotspot and not caution
    lines=[f'{tone(ready, caution)}summary: {"ready" if ready else "caution" if api_ok else "problem"}', f'API: {"online" if api_ok else "offline"}', f'hotspot: {"on" if hotspot else "check"}', f'tailscale: {"seen" if tailscale else "field/offline"}']
    if uptime: lines.append(f'uptime: {int(float(uptime)//60)} min' if str(uptime).replace('.','',1).isdigit() else f'uptime: {uptime}')
    if temp is not None: lines.append(f'temp: {round(float(temp),1)}C')
    if mem.get('percent') is not None: lines.append(f'RAM: {mem.get("percent")}%')
    if disk.get('free_gb') is not None: lines.append(f'disk free: {disk.get("free_gb")}GB')
    lines.append('power: dim + burst GPS')
    return lines[:12]

def lines_compass():
    sense = sense_payload(api('/api/sense'))
    heading = sense.get('compass') or sense.get('heading')
    orient = sense.get('orientation') if isinstance(sense.get('orientation'), dict) else {}
    roll = orient.get('roll', sense.get('roll'))
    pitch = orient.get('pitch', sense.get('pitch'))
    level = (roll is not None and pitch is not None and abs(float(roll)) < 8 and abs(float(pitch)) < 8)
    card = ['N','NE','E','SE','S','SW','W','NW'][int(((float(heading or 0)+22.5)%360)//45)] if heading is not None else '—'
    return [f'heading: {round(float(heading),1) if heading is not None else "—"} {card}', f'roll: {round(float(roll),1) if roll is not None else "—"}', f'pitch: {round(float(pitch),1) if pitch is not None else "—"}', f'{tone(level)}level: {"steady" if level else "tilted/check"}', 'calibrate away from metal', '~carry real compass/map']

def lines_weather():
    sense = sense_payload(api('/api/sense'))
    weather = api('/api/weather?days=1', timeout=1.0)
    temp = sense.get('temperature') or sense.get('temp_c')
    hum = sense.get('humidity')
    pres = sense.get('pressure')
    src = weather.get('source') or ('Sense HAT' if temp is not None else 'cache/offline')
    lines=[f'source: {src}', f'temp: {round(float(temp),1) if temp is not None else "—"}C', f'humidity: {round(float(hum),1) if hum is not None else "—"}%', f'pressure: {round(float(pres),1) if pres is not None else "—"}', 'sky: offline sky cues', 'watch clouds/wind shifts']
    if weather.get('current'):
        lines += wrap(json.dumps(weather.get('current'))[:80], 24)[:3]
    return lines[:12]

def lines_network():
    net = api('/api/network/status')
    if net.get('_error'):
        return ['!network API offline'] + wrap(net['_error'], 24)[:7]
    text = json.dumps(net, indent=0, sort_keys=True)
    return wrap(text.replace('{','').replace('}','').replace('"',''), 25)[:12]

def lines_safety():
    return ['+Assist mode only','Carry real nav tools.','Phone/SOS primary.','Offline maps + compass.','Mark last known point.','~When unsure: stop,', '~backtrack, save power.']

def events_from_api():
    sense = sense_payload(api('/api/sense', timeout=1.0))
    pac = sense.get('pacman_display') or {}
    return [e for e in pac.get('events', []) if isinstance(e, dict) and e.get('id')]

def poll_popup():
    global popup_event, popup_until
    for event in events_from_api():
        eid = event.get('id')
        if eid in seen_popup_events:
            continue
        seen_popup_events.add(eid)
        popup_event = event
        popup_until = time.time() + float(event.get('display_seconds') or 2.8)
        return True
    return False

def render_popup(event):
    etype = event.get('type') or 'game_event'; label = event.get('label') or etype.replace('_',' ')
    if etype in ('manual_popup_test','snake_trail_event'):
        accent = GREEN if etype == 'manual_popup_test' else BLUE
        lines = ['+manual popup bridge' if etype == 'manual_popup_test' else '+Snake Trail', label, event.get('text') or event.get('trail') or 'shared game event', f'score +{event.get("score_delta",0)}', 'text/contrast check']
    elif etype == 'fruit_eaten':
        accent = RED; lines = ['~Sense HAT Pac-Man','Cherry eaten!', f'+{event.get("score_delta", 10)} points', f'fruit #{event.get("fruit_count", "?")}']
    elif etype == 'ghost_eaten':
        accent = BLUE; lines = ['~Sense HAT Pac-Man', label, f'ghost: {event.get("ghost_name", "ghost")}', f'+{event.get("score_delta", 25)} points']
    elif etype == 'pacman_caught':
        accent = RED; lines = ['~Sense HAT Pac-Man', label, 'resetting tiny maze', f'score: {event.get("score", 0)}']
    elif etype == 'map_advanced':
        accent = GREEN; lines = ['~Sense HAT Pac-Man', label, f'level {int(event.get("next_map", 0)) + 1}', f'{event.get("fruits_per_map", 12)} cherries/map']
    elif etype == 'power_started':
        accent = AMBER; lines = ['~Sense HAT Pac-Man','Power mode!','ghosts go blue', f'ticks: {event.get("power_ticks", 0)}']
    else:
        accent = AMBER; lines = wrap(label, 24)[:5]
    lines.append(f'score: {event.get("score", 0)}')
    return draw_card('Whisplay Popup', lines, accent, 'auto returns · press next')

def rand_food(body):
    choices=[(x,y) for x in range(8) for y in range(8) if (x,y) not in body]
    return random.choice(choices or [(0,0)])

def tick_snake():
    global snake
    if snake['over']: return
    hx,hy=snake['body'][0]; dx,dy=snake['dir']; head=((hx+dx)%8,(hy+dy)%8)
    if head in snake['body']:
        snake['over'] = True; post_command('snake-trail-event', {'label':'Snake Trail tangled', 'score_delta':0, 'segment_count':len(snake['body'])}, timeout=0.8); return
    body=[head]+snake['body']
    if head == snake['food']:
        snake['score'] += 15; snake['food'] = rand_food(body); now=time.time()
        if now - snake.get('last_emit',0) > 1.5:
            snake['last_emit'] = now; post_command('snake-trail-event', {'label':'Snake Trail snack found', 'score_delta':15, 'segment_count':len(body)}, timeout=0.8)
    else:
        body=body[:-1]
    snake['body']=body

def render_snake():
    tick_snake(); img = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(img)
    d.rounded_rectangle((6,6,W-7,H-7),12,outline=BLUE,width=2,fill=(10,24,34))
    d.text((16,12),'Snake Trail',font=F_TITLE,fill=BLUE); d.text((16,38),f'score {snake["score"]} · segments {len(snake["body"])}',font=F_SMALL,fill=DIM)
    ox,oy,cell=28,64,22; d.rounded_rectangle((ox-4,oy-4,ox+8*cell+4,oy+8*cell+4),6,outline=(40,70,90),width=1,fill=(4,12,18))
    for y in range(8):
        for x in range(8):
            fill=(8,20,28)
            if (x,y)==snake['food']: fill=AMBER
            if (x,y) in snake['body']: fill=GREEN
            if (x,y)==snake['body'][0]: fill=WHITE
            d.rounded_rectangle((ox+x*cell+2, oy+y*cell+2, ox+(x+1)*cell-2, oy+(y+1)*cell-2), 3, fill=fill)
    if snake['over']:
        d.rounded_rectangle((28,116,212,164),8,fill=(80,20,25),outline=RED,width=2); d.text((48,130),'Trail tangled',font=F_BODY,fill=WHITE)
    d.text((16,H-23),'press next · joystick parked',font=F_TINY,fill=DIM)
    return img

def render():
    if popup_event and time.time() < popup_until: return render_popup(popup_event)
    title = PAGES[page % len(PAGES)]
    if title == 'Buddy Home': return draw_face('happy')
    if title == 'Field Kit': return draw_card('Field Kit/Power', lines_fieldkit(), GREEN)
    if title == 'Compass+Level': return draw_card('Compass + Level', lines_compass(), BLUE)
    if title == 'Weather+Sky': return draw_card('Weather + Sky', lines_weather(), AMBER)
    if title == 'Network': return draw_card('Network', lines_network(), BLUE)
    if title == 'Snake Trail': return render_snake()
    return draw_card('Trail Safety', lines_safety(), AMBER)

def main():
    global running, page, popup_until
    hw = create_hw('whisplay-mappi3-dashboard', 'MapPI3 Dash', 'M3', 90)
    def next_page():
        global page, popup_until
        if page % len(PAGES) == 0:
            post_command('whisplay-test-popup', {'label':'Dash button popup test', 'display_seconds':3.2}, timeout=0.8)
        page += 1; popup_until = 0.0; show(hw, render())
    def exit_req():
        global running
        running = False
    hw.on_button_press(next_page); hw.on_exit_request(exit_req); show(hw, render())
    try:
        last = 0
        while running:
            time.sleep(0.35); active = page % len(PAGES)
            if poll_popup() or (popup_event and time.time() < popup_until) or active in (1,2,3,4,6):
                if active == 6 and time.time() - last < 0.18: continue
                last = time.time(); show(hw, render())
    finally:
        hw.cleanup()

if __name__ == '__main__':
    main()
PY
chmod 0755 "$EXAMPLE_DIR/mappi3_whisplay_dashboard.py"

cat > "$EXAMPLE_DIR/mappi3_whisplay_ai_chat.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations
import json, os, time
from urllib import request
from mappi3_whisplay_common import *

running = True
idx = 0
busy = False
last_answer = 'Press to ask home AI.'
PROMPTS = [
    ('Trail check', 'Give a very short MapPI3 trail readiness checklist. Mention that MapPI3 assists but does not replace real navigation/emergency tools.'),
    ('Hotspot help', 'In 3 short bullets, explain how MapPI3 can use hotspot at home and offline mode on trail.'),
    ('Battery saver', 'Give 4 concise low-power tips for a Raspberry Pi trail device with screen, GPS, and hotspot.'),
    ('Whisplay idea', 'Suggest one tiny Whisplay screen layout for MapPI3: face, GPS, network, and safety.'),
]

def ollama_config():
    env = load_env('/etc/mappi3/whisplay-ai.env')
    host = os.environ.get('OLLAMA_HOST') or env.get('OLLAMA_HOST') or 'http://10.42.0.38:11434'
    model = os.environ.get('OLLAMA_MODEL') or env.get('OLLAMA_MODEL') or ''
    timeout = float(os.environ.get('OLLAMA_TIMEOUT') or env.get('OLLAMA_TIMEOUT') or 35)
    return host.rstrip('/'), model, timeout

def pick_model(host, timeout=4):
    try:
        data = http_json(host + '/api/tags', timeout=timeout)
        models = [m.get('name') for m in data.get('models', []) if m.get('name')]
        for pref in ('llama3.2', 'llama3.1', 'gemma3', 'qwen', 'mistral'):
            for name in models:
                if name.startswith(pref): return name
        return models[0] if models else ''
    except Exception:
        return ''

def ask_ai(prompt):
    host, model, timeout = ollama_config()
    model = model or pick_model(host)
    if not model:
        return 'Home AI not found. Start Ollama/model on NukeBox, or set /etc/mappi3/whisplay-ai.env.'
    body = json.dumps({'model': model, 'prompt': prompt, 'stream': False, 'options': {'num_predict': 90}}).encode()
    req = request.Request(host + '/api/generate', data=body, headers={'Content-Type': 'application/json'})
    try:
        with request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode('utf-8'))
        return data.get('response','').strip() or 'AI returned empty response.'
    except Exception as e:
        return 'AI request failed: ' + str(e)[:120]

def render(title=None, body=None, accent=BLUE):
    title = title or PROMPTS[idx % len(PROMPTS)][0]
    body = body if body is not None else last_answer
    lines = wrap(body, 24)[:10]
    lines.insert(0, '~' + PROMPTS[idx % len(PROMPTS)][0])
    return draw_card('MapPI3 AI', lines, accent, 'press = ask/next · exit gesture backs out')

def main():
    global running, idx, busy, last_answer
    hw = create_hw('whisplay-mappi3-ai-chat', 'MapPI3 AI', 'AI', 80)
    def on_press():
        global idx, busy, last_answer
        if busy: return
        busy = True
        title, prompt = PROMPTS[idx % len(PROMPTS)]
        show(hw, draw_card('MapPI3 AI', ['~asking NukeBox...', title], AMBER))
        last_answer = ask_ai(prompt)
        show(hw, render(title, last_answer, GREEN if not last_answer.startswith('AI request failed') else RED))
        idx += 1
        busy = False
    def exit_req():
        global running
        running = False
    hw.on_button_press(on_press)
    hw.on_exit_request(exit_req)
    show(hw, render())
    try:
        while running:
            time.sleep(0.5)
    finally:
        hw.cleanup()

if __name__ == '__main__':
    main()
PY
chmod 0755 "$EXAMPLE_DIR/mappi3_whisplay_ai_chat.py"

cat > "$APP_DIR/whisplay-mappi3-dashboard.json" <<'JSON'
{
  "app_id": "whisplay-mappi3-dashboard",
  "display_name": "MapPI3 Dash",
  "icon": "M3",
  "launch_command": "python3 mappi3_whisplay_dashboard.py",
  "cwd": "/opt/whisplay/Whisplay-main/example",
  "env": {"WHISPLAY_APP_ID": "whisplay-mappi3-dashboard"},
  "exit_gesture": "quad_click",
  "priority": 90,
  "use_daemon_default_log": true,
  "persist": true,
  "disable_esc_exit_key": false
}
JSON

cat > "$APP_DIR/whisplay-mappi3-ai-chat.json" <<'JSON'
{
  "app_id": "whisplay-mappi3-ai-chat",
  "display_name": "MapPI3 AI",
  "icon": "AI",
  "launch_command": "python3 mappi3_whisplay_ai_chat.py",
  "cwd": "/opt/whisplay/Whisplay-main/example",
  "env": {"WHISPLAY_APP_ID": "whisplay-mappi3-ai-chat"},
  "exit_gesture": "quad_click",
  "priority": 80,
  "use_daemon_default_log": true,
  "persist": true,
  "disable_esc_exit_key": false
}
JSON

cat > /etc/mappi3/bt-pan.env <<'EOF'
# Optional: set PHONE_MAC to the paired/trusted phone Bluetooth MAC.
PHONE_MAC=
# Keep hotspot on wlan0 while using Bluetooth PAN/NAP as upstream.
HOTSPOT_IFACE=wlan0
PAN_IFACE=bnep0
EOF

cat > /usr/local/bin/mappi3-bt-pan-client.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
ENV=/etc/mappi3/bt-pan.env
[ -f "$ENV" ] && . "$ENV"
PHONE_MAC="${PHONE_MAC:-}"
PAN_IFACE="${PAN_IFACE:-bnep0}"
HOTSPOT_IFACE="${HOTSPOT_IFACE:-wlan0}"
log(){ printf '[mappi3-bt-pan] %s\n' "$*"; }
if ! bluetoothctl show >/dev/null 2>&1; then
  log 'No Bluetooth controller yet. If config had disable-bt, reboot after Maple enable step.'
  exit 2
fi
sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null || true
# Unblock/power the controller without requiring the optional rfkill CLI package.
for soft in /sys/class/rfkill/rfkill*/soft; do
  [ -e "$soft" ] || continue
  name_file="$(dirname "$soft")/type"
  if grep -qx bluetooth "$name_file" 2>/dev/null; then
    echo 0 | sudo tee "$soft" >/dev/null || true
  fi
done
if command -v btmgmt >/dev/null 2>&1; then
  timeout 8 sudo btmgmt power on >/dev/null 2>&1 || true
fi
if command -v bluetoothctl >/dev/null; then
  bluetoothctl power on >/dev/null 2>&1 || true
  bluetoothctl agent on >/dev/null 2>&1 || true
  bluetoothctl default-agent >/dev/null 2>&1 || true
fi
if [ -z "$PHONE_MAC" ]; then
  PHONE_MAC="$(bluetoothctl devices Paired 2>/dev/null | awk 'NR==1{print $2}')"
fi
if [ -z "$PHONE_MAC" ]; then
  log 'No paired phone found yet. Pair/trust phone first, then set PHONE_MAC in /etc/mappi3/bt-pan.env. Leaving hotspot unchanged.'
  exit 0
fi
log "Using phone $PHONE_MAC"
if command -v bt-network >/dev/null 2>&1; then
  timeout 30 bt-network -c "$PHONE_MAC" nap || true
else
  log 'bt-network not installed; relying on NetworkManager paired Bluetooth connection if present.'
fi
sleep 2
if ip link show "$PAN_IFACE" >/dev/null 2>&1; then
  sudo dhclient -v "$PAN_IFACE" || true
  sudo ip route replace default dev "$PAN_IFACE" metric 250 || true
  if command -v iptables >/dev/null 2>&1; then
    sudo iptables -t nat -C POSTROUTING -o "$PAN_IFACE" -j MASQUERADE 2>/dev/null || sudo iptables -t nat -A POSTROUTING -o "$PAN_IFACE" -j MASQUERADE
    sudo iptables -C FORWARD -i "$HOTSPOT_IFACE" -o "$PAN_IFACE" -j ACCEPT 2>/dev/null || sudo iptables -A FORWARD -i "$HOTSPOT_IFACE" -o "$PAN_IFACE" -j ACCEPT
    sudo iptables -C FORWARD -i "$PAN_IFACE" -o "$HOTSPOT_IFACE" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || sudo iptables -A FORWARD -i "$PAN_IFACE" -o "$HOTSPOT_IFACE" -m state --state ESTABLISHED,RELATED -j ACCEPT
  fi
  log "PAN ready on $PAN_IFACE while hotspot stays on $HOTSPOT_IFACE"
  ip addr show "$PAN_IFACE"; ip route
else
  log "$PAN_IFACE not present; phone may not expose Bluetooth internet/NAP yet."
  exit 4
fi
SH
chmod 0755 /usr/local/bin/mappi3-bt-pan-client.sh

cat > /etc/systemd/system/mappi3-bt-pan-client.service <<'UNIT'
[Unit]
Description=MapPI3 Bluetooth PAN internet client while preserving hotspot
After=bluetooth.service NetworkManager.service
Wants=bluetooth.service NetworkManager.service

[Service]
Type=oneshot
EnvironmentFile=-/etc/mappi3/bt-pan.env
ExecStart=/usr/local/bin/mappi3-bt-pan-client.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT

# Enable Bluetooth hardware on next boot if this image disabled it for serial/GPS experiments.
if grep -qE '^dtoverlay=disable-bt' /boot/firmware/config.txt; then
  cp -a /boot/firmware/config.txt "$BACKUP_DIR/config.txt.before-enable-bt"
  sed -i 's/^dtoverlay=disable-bt/# Maple enabled BT PAN on '"$STAMP"': dtoverlay=disable-bt/' /boot/firmware/config.txt
fi

systemctl daemon-reload
chown -R mappi3:mappi3 "$APP_DIR" "$EXAMPLE_DIR/mappi3_whisplay_common.py" "$EXAMPLE_DIR/mappi3_whisplay_dashboard.py" "$EXAMPLE_DIR/mappi3_whisplay_ai_chat.py" /etc/mappi3/whisplay-ai.env /etc/mappi3/bt-pan.env || true
chmod 0755 /etc/mappi3 || true
chmod 0644 /etc/mappi3/whisplay-ai.env /etc/mappi3/bt-pan.env || true
systemctl enable mappi3-bt-pan-client.service >/dev/null 2>&1 || true
systemctl restart whisplay-daemon.service

echo "MAPPI3_WHISPLAY_APPS_BT_INSTALL=PASS backup=$BACKUP_DIR"
