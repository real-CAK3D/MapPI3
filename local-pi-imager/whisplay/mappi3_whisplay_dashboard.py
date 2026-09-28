#!/usr/bin/env python3
from __future__ import annotations
import datetime, json, math, random, threading, time
from urllib import request
from mappi3_whisplay_common import *

API = 'http://127.0.0.1:5050'
running = True
page = 0
seen_popup_events = set()
popup_event = None
popup_until = 0.0
phone_input_until = 0.0
phone_input_buffer = ''
phone_input_sensitive = False
phone_input_last_seq = 0
phone_input_status = 'phone keyboard ready'
snake = {'body': [(4,4),(3,4),(2,4)], 'dir': (1,0), 'food': (6,4), 'score': 0, 'over': False, 'last_emit': 0.0}
PAGES = ['Buddy Home','Herbie','Field Kit','Compass+Level','Weather+Sky','Mesh','Network','Safety']
HERBIE_MOTION_STATE = {'last_accel': None, 'last_at': 0.0, 'hits': [], 'event': None, 'event_until': 0.0, 'peak': 0.0}

def api(path, timeout=5.0):
    try:
        with request.urlopen(API + path, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}

# /api/status takes ~0.2-0.7 s, longer than the old 0.35 s inline timeout, so Herbie often fell back to the
# "offline face loop" and never saw events, GPS or battery. A background thread keeps a fresh copy instead.
_STATUS_CACHE = {'data': {'_error': 'status not loaded yet'}, 'at': 0.0, 'thread': None}

def _status_worker():
    while running:
        data = api('/api/status', timeout=4.0)
        _STATUS_CACHE['data'] = data
        _STATUS_CACHE['at'] = time.time()
        time.sleep(3.0)

def cached_status(max_age=20.0):
    if _STATUS_CACHE['thread'] is None:
        _STATUS_CACHE['thread'] = threading.Thread(target=_status_worker, daemon=True)
        _STATUS_CACHE['thread'].start()
    if time.time() - _STATUS_CACHE['at'] > max_age:
        return {'_error': 'status stale'}
    return _STATUS_CACHE['data']

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

def c_to_f(value):
    try:
        return float(value) * 9.0 / 5.0 + 32.0
    except Exception:
        return None

def temp_f_text(value_c):
    value_f = c_to_f(value_c)
    return '—' if value_f is None else f'{round(value_f,1)}F'

def lines_fieldkit():
    status = api('/api/status'); net = api('/api/network/status'); sense = sense_payload(api('/api/sense')); power = api('/api/power/status')
    stats = status.get('stats') if isinstance(status.get('stats'), dict) else status.get('system') if isinstance(status.get('system'), dict) else {}
    disk = stats.get('disk') if isinstance(stats.get('disk'), dict) else {}
    mem = stats.get('memory') if isinstance(stats.get('memory'), dict) else {}
    temp = stats.get('temperature_c')
    if temp is None and sense.get('temp') is not None:
        temp = (float(sense.get('temp')) - 32) * 5 / 9
    uptime = stats.get('uptime_seconds') or status.get('uptime_seconds') or status.get('uptime')
    wifi = net.get('wifi') if isinstance(net.get('wifi'), dict) else {}
    ts = net.get('tailscale') if isinstance(net.get('tailscale'), dict) else {}
    bt = net.get('bluetooth_pan') if isinstance(net.get('bluetooth_pan'), dict) else {}
    api_ok = not status.get('_error') and bool(status.get('ok', True))
    hotspot = bool(wifi.get('hotspot_active') or status.get('hotspot_active'))
    tailscale_online = bool(ts.get('online') or ts.get('tailscale_ips'))
    tailscale_seen = bool(ts.get('installed') is not False and (ts.get('ok') or ts.get('backend_state') or ts.get('tailscale_ips')))
    internet = bool(net.get('has_default_route') or bt.get('internet_ok'))
    disk_pct = disk.get('percent') if isinstance(disk.get('percent'), (int,float)) else None
    mem_pct = mem.get('percent') if isinstance(mem.get('percent'), (int,float)) else None
    temp_num = float(temp) if isinstance(temp, (int,float)) else None
    problems = []
    cautions = []
    if not api_ok: problems.append('API')
    if not hotspot: problems.append('hotspot')
    if temp_num is not None and temp_num >= 80: problems.append('temp')
    elif temp_num is not None and temp_num >= 70: cautions.append('temp')
    if mem_pct is not None and mem_pct >= 90: problems.append('RAM')
    elif mem_pct is not None and mem_pct >= 80: cautions.append('RAM')
    if disk_pct is not None and disk_pct >= 95: problems.append('disk')
    elif disk_pct is not None and disk_pct >= 85: cautions.append('disk')
    if not tailscale_online and tailscale_seen: cautions.append('tailnet')
    if not internet: cautions.append('offline')
    summary = 'problem' if problems else 'caution' if cautions else 'ready'
    lines=[f'{tone(summary == "ready", summary == "caution")}summary: {summary.upper()}', f'API: {"online" if api_ok else "offline"}', f'hotspot: {"READY" if hotspot else "PROBLEM"}', f'tailnet: {"online" if tailscale_online else "field/offline"}', f'internet: {"route" if internet else "cached only"}']
    if uptime: lines.append(f'uptime: {int(float(uptime)//60)} min' if str(uptime).replace('.','',1).isdigit() else f'uptime: {uptime}')
    if temp_num is not None: lines.append(f'CPU temp: {temp_f_text(temp_num)}')
    if mem_pct is not None: lines.append(f'RAM: {mem_pct}% used')
    if disk.get('free_gb') is not None: lines.append(f'disk: {disk.get("free_gb")}GB free')
    if isinstance(power, dict) and not power.get('_error') and power.get('ok', True):
        pct = power.get('percent')
        source = power.get('source') or 'power-api'
        charging = power.get('charging')
        plugged = power.get('battery_input_power_connected')
        pct_text = f'{round(float(pct))}%' if isinstance(pct, (int, float)) else 'unknown%'
        state = 'charging' if charging is True else 'not charging' if charging is False else 'charge ?'
        input_state = 'input on' if plugged is True else 'input off' if plugged is False else 'input ?'
        lines.append(f'battery: {pct_text} {state}')
        lines.append(f'PiSugar: {input_state} · {source}')
    else:
        err = power.get('_error') if isinstance(power, dict) else 'unavailable'
        lines.append('battery: unavailable')
        lines.append(f'PiSugar: {str(err)[:18]}')
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

# ---------- Weather + Sky ----------
WMO = {0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast', 45: 'Fog', 48: 'Freezing fog', 51: 'Light drizzle', 53: 'Drizzle',
       55: 'Heavy drizzle', 56: 'Freezing drizzle', 57: 'Freezing drizzle', 61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 66: 'Freezing rain',
       67: 'Freezing rain', 71: 'Light snow', 73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains', 80: 'Showers', 81: 'Showers', 82: 'Heavy showers',
       85: 'Snow showers', 86: 'Snow showers', 95: 'Thunderstorm', 96: 'T-storm + hail', 99: 'T-storm + hail'}
_pressure = []            # (time, hPa) samples for the trend, kept for 3 hours
_weather = {'at': 0.0, 'data': {}}

def pressure_trend(hpa):
    now = time.time()
    if hpa is not None and (not _pressure or now - _pressure[-1][0] >= 300):
        _pressure.append((now, float(hpa)))
    while _pressure and now - _pressure[0][0] > 3 * 3600:
        _pressure.pop(0)
    if len(_pressure) < 2 or now - _pressure[0][0] < 3000:
        return 'trend in ~1 h', DIM
    rate = (_pressure[-1][1] - _pressure[0][1]) / ((_pressure[-1][0] - _pressure[0][0]) / 3600)   # hPa per hour
    if rate <= -1.0: return 'falling fast!', RED
    if rate <= -0.3: return 'falling', AMBER
    if rate >= 0.3: return 'rising', GREEN
    return 'steady', WHITE

def sun_times(lat, lon, day=None):
    """NOAA sunrise/sunset, local time. Returns (sunrise, sunset) as datetimes or (None, None) in polar day/night."""
    day = day or datetime.date.today()
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = 0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g)
    cos_h = math.cos(math.radians(90.833)) / (math.cos(math.radians(lat)) * math.cos(decl)) - math.tan(math.radians(lat)) * math.tan(decl)
    if abs(cos_h) > 1:
        return None, None
    ha = math.degrees(math.acos(cos_h))
    noon_utc = 720 - 4 * lon - eq
    base = datetime.datetime.combine(day, datetime.time(0, 0), tzinfo=datetime.timezone.utc)
    rise = (base + datetime.timedelta(minutes=noon_utc - 4 * ha)).astimezone()
    sset = (base + datetime.timedelta(minutes=noon_utc + 4 * ha)).astimezone()
    return rise, sset

def moon_phase(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    days = (now - datetime.datetime(2000, 1, 6, 18, 14, tzinfo=datetime.timezone.utc)).total_seconds() / 86400
    age = days % 29.530588853
    lit = round((1 - math.cos(2 * math.pi * age / 29.530588853)) / 2 * 100)
    waxing = age < 29.530588853 / 2
    if lit < 2: return 'New moon', lit
    if lit >= 98: return 'Full moon', lit
    if 47 <= lit <= 53: return ('First quarter' if waxing else 'Last quarter'), lit
    return ('Waxing ' if waxing else 'Waning ') + ('crescent' if lit < 50 else 'gibbous'), lit

def clock_text(dt):
    return dt.strftime('%I:%M %p').lstrip('0') if dt else '—'

def draw_weather():
    if time.time() - _weather['at'] > 60:
        _weather['data'] = api('/api/weather?days=1', timeout=2.5) or {}
        _weather['at'] = time.time()
    w = _weather['data']
    sense = sense_payload(api('/api/sense', timeout=0.5))
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, W-7, H-7), 12, outline=AMBER, width=2, fill=(12, 26, 38))
    d.text((16, 12), 'Weather + Sky', font=F_TITLE, fill=AMBER)
    y = 44
    cur = w.get('current') if isinstance(w.get('current'), dict) else {}
    today = (w.get('daily') or [{}])[0] if isinstance(w.get('daily'), list) and w.get('daily') else {}
    if cur.get('temperature_2m') is not None:
        d.text((16, y), f"{round(cur['temperature_2m'])}°F", font=F_TITLE, fill=WHITE)
        d.text((86, y + 4), WMO.get(cur.get('weather_code'), 'Weather')[:16], font=F_BODY, fill=WHITE)
        y += 26
        bits = []
        if today.get('minF') is not None: bits.append(f"{round(today['minF'])}-{round(today['maxF'])}°F")
        if today.get('precip') is not None: bits.append(f"{today['precip']}% rain")
        if cur.get('relative_humidity_2m') is not None: bits.append(f"{cur['relative_humidity_2m']}% RH")
        d.text((16, y), ' · '.join(bits)[:32], font=F_SMALL, fill=DIM)
    else:
        d.text((16, y), 'No forecast', font=F_BODY, fill=AMBER); y += 20
        d.text((16, y), 'Needs internet on the Pi.', font=F_SMALL, fill=DIM)
    y += 22
    d.line((12, y, W-13, y), fill=(45, 70, 90)); y += 6
    d.text((16, y), 'On the Pi', font=F_SMALL, fill=AMBER); y += 16
    hpa = sense.get('pressure')
    if hpa:
        trend, color = pressure_trend(hpa)
        d.text((16, y), f"{round(float(hpa))} hPa", font=F_BODY, fill=WHITE)
        d.text((96, y + 2), trend[:22], font=F_SMALL, fill=color); y += 20
    hum = sense.get('humidity')
    if hum is not None:
        d.text((16, y), f"humidity {round(float(hum))}% (inside the case)", font=F_SMALL, fill=DIM); y += 16
    y += 4
    d.line((12, y, W-13, y), fill=(45, 70, 90)); y += 6
    d.text((16, y), 'Sky', font=F_SMALL, fill=AMBER); y += 16
    lat, lon = w.get('lat'), w.get('lon')
    if lat is not None and lon is not None:
        rise, sset = sun_times(float(lat), float(lon))
        d.text((16, y), f"sunrise {clock_text(rise)} · sunset {clock_text(sset)}", font=F_SMALL, fill=WHITE); y += 16
        if sset:
            left = (sset - datetime.datetime.now().astimezone()).total_seconds()
            if 0 < left < 3 * 3600:
                d.text((16, y), f"{int(left // 3600)} h {int(left % 3600 // 60)} min of daylight left", font=F_SMALL, fill=AMBER); y += 16
    name, lit = moon_phase()
    d.text((16, y), f"moon: {name.lower()}, {lit}% lit", font=F_SMALL, fill=WHITE); y += 16
    age = time.time() - float(w.get('fetched_at') or 0) if w.get('fetched_at') else None
    src = 'forecast ' + (f"{int(age // 60)} min old" if age is not None and age < 86400 else 'age unknown') if cur else 'offline'
    d.line((12, H-30, W-13, H-30), fill=(45, 70, 90), width=1)
    d.text((16, H-23), src[:34], font=F_TINY, fill=DIM)
    return img

# ---------- Network ----------
def draw_network():
    net = api('/api/network/status', timeout=2.5) or {}
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, W-7, H-7), 12, outline=BLUE, width=2, fill=(12, 26, 38))
    d.text((16, 12), 'Network', font=F_TITLE, fill=BLUE)
    if net.get('_error') or not net:
        d.text((16, 50), 'Network status unavailable', font=F_BODY, fill=RED)
        return img
    rows = []
    route = str(net.get('route') or '')
    gw = route.split('default via ', 1)[1].split()[0] if 'default via ' in route else None
    bt = net.get('bluetooth_pan') if isinstance(net.get('bluetooth_pan'), dict) else {}
    active = ' '.join(net.get('active_connections') or [])
    if bt.get('internet_ok'):
        rows.append(('ok', 'Internet', 'via phone (Bluetooth)'))
    elif gw == '10.42.0.38':
        rows.append(('ok', 'Internet', 'via NukeBox PC'))
    elif gw:
        home = next((w.get('ssid') for w in (net.get('saved_wifi') or []) if w.get('name') and w.get('name') in active and w.get('ssid') != 'MapPI3'), None)
        rows.append(('ok', 'Internet', f"via {home}" if home else f"via {gw}"))
    else:
        rows.append(('warn', 'Internet', 'offline (hotspot only)'))
    hotspot = 'MapPI3-hotspot' in active
    rows.append(('ok' if hotspot else 'bad', 'Hotspot', 'MapPI3 · 10.42.0.1' if hotspot else 'off'))
    ts = net.get('tailscale') if isinstance(net.get('tailscale'), dict) else {}
    ips = [ip for ip in (ts.get('tailscale_ips') or []) if '.' in ip]
    rows.append(('ok' if ts.get('online') else 'warn', 'Tailscale', (ips[0] if ips else 'no address') + ('' if ts.get('online') else ' · offline')))
    ssh = net.get('ssh') if isinstance(net.get('ssh'), dict) else {}
    rows.append(('ok' if ssh.get('listening') else 'warn', 'SSH', 'ready on port 22' if ssh.get('listening') else 'not listening'))
    rows.append(('ok' if bt.get('ready') else 'warn', 'Bluetooth', 'phone sharing internet' if bt.get('internet_ok') else 'ready to pair' if bt.get('ready') else 'not ready'))
    saved = [w.get('ssid') for w in (net.get('saved_wifi') or []) if w.get('ssid') and w.get('ssid') != 'MapPI3']
    rows.append(('info', 'Saved Wi-Fi', ', '.join(saved[:2]) + (f" +{len(saved) - 2}" if len(saved) > 2 else '') if saved else 'none'))
    rows.append(('ok' if net.get('remote_ready') else 'warn', 'Remote access', 'ready' if net.get('remote_ready') else 'not ready'))
    y = 46
    colors = {'ok': GREEN, 'warn': AMBER, 'bad': RED, 'info': BLUE}
    for state, label, value in rows:
        d.ellipse((16, y + 5, 24, y + 13), fill=colors[state])
        d.text((32, y), label, font=F_SMALL, fill=DIM)
        d.text((32, y + 13), str(value)[:28], font=F_BODY, fill=WHITE)
        y += 31
    return img

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

def poll_phone_input():
    """Bridge phone/PWA keyboard queue into the Whisplay dashboard loop.

    The phone sends text/password/buttons to /api/command/whisplay-input. The
    local Whisplay app is allowed to request sensitive payloads over loopback,
    while remote GETs keep those values redacted.
    """
    global phone_input_until, phone_input_buffer, phone_input_sensitive, phone_input_last_seq, phone_input_status, page, popup_until
    data = api(f'/api/whisplay/input?since={phone_input_last_seq}&include_sensitive=1', timeout=0.45)
    if data.get('_error') or not data.get('queue'):
        return False
    changed = False
    for item in data.get('queue') or []:
        try:
            seq = int(item.get('seq') or 0)
        except Exception:
            seq = 0
        if seq <= phone_input_last_seq:
            continue
        phone_input_last_seq = seq
        kind = str(item.get('kind') or 'text').lower()
        value = str(item.get('text') if item.get('text') is not None else item.get('value') if item.get('value') is not None else '')
        if kind == 'clear':
            phone_input_buffer = ''
            phone_input_sensitive = False
            phone_input_status = 'phone input cleared'
        elif kind in ('text', 'password'):
            phone_input_buffer += value
            phone_input_sensitive = phone_input_sensitive or kind == 'password' or bool(item.get('sensitive'))
            phone_input_status = 'password text received' if phone_input_sensitive else 'text received'
        elif kind == 'backspace':
            phone_input_buffer = phone_input_buffer[:-1]
            phone_input_status = 'backspace'
        elif kind == 'enter':
            phone_input_status = 'enter pressed from phone'
        elif kind == 'escape':
            phone_input_buffer = ''
            phone_input_sensitive = False
            phone_input_status = 'escaped / reset'
        elif kind in ('left','right','up','down'):
            if kind in ('right','down'):
                page += 1
            else:
                page -= 1
            popup_until = 0.0
            phone_input_status = f'phone nav: {kind}'
        else:
            phone_input_status = f'phone key: {kind}'
        phone_input_until = time.time() + 5.0
        changed = True
    return changed

def render_phone_input():
    shown = ('•' * min(len(phone_input_buffer), 18)) if phone_input_sensitive else phone_input_buffer[-22:]
    if not shown:
        shown = 'waiting for phone text'
    lines = [
        '+phone keyboard bridge',
        phone_input_status,
        f'chars: {len(phone_input_buffer)}',
        shown,
        'Enter/backspace supported',
        'Use direct Wi-Fi save for NM',
        '~password hidden on display',
    ]
    return draw_card('Phone Input', lines, BLUE, 'phone text -> Whisplay prompt')

# ---------- Meshtastic mesh (radio on USB or Wi-Fi, via the mappi3-mesh service) ----------
_mesh = {'at': 0.0, 'data': {}}
_mesh_seen = set()
_mesh_primed = [False]
def mesh_state(max_age=2.5):
    if time.time() - _mesh['at'] > max_age:
        _mesh['data'] = api('/api/mesh/status', timeout=1.2) or {}
        _mesh['at'] = time.time()
    return _mesh['data']

def ago_text(sec):
    if sec is None: return '?'
    sec = max(0, int(sec))
    return f'{sec}s' if sec < 60 else f'{sec // 60}m' if sec < 3600 else f'{sec // 3600}h' if sec < 86400 else f'{sec // 86400}d'

CARDINAL = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
def draw_arrow(d, cx, cy, deg, r, color):
    a = math.radians(deg)
    ux, uy = math.sin(a), -math.cos(a)           # pointing direction
    px, py = -uy, ux                              # sideways
    tip = (cx + ux * r, cy + uy * r)
    back = (cx - ux * r * 0.8, cy - uy * r * 0.8)
    notch = (cx - ux * r * 0.35, cy - uy * r * 0.35)
    d.polygon([tip, (back[0] + px * r * 0.6, back[1] + py * r * 0.6), notch, (back[0] - px * r * 0.6, back[1] - py * r * 0.6)], fill=color)

def draw_bars(d, x, y, snr, color):
    level = 0 if snr is None else 4 if snr >= 5 else 3 if snr >= 0 else 2 if snr >= -7 else 1
    for i in range(4):
        h = 4 + i * 3
        d.rectangle((x + i * 5, y + 13 - h, x + i * 5 + 3, y + 13), fill=color if i < level else (40, 60, 70))

def draw_mesh():
    m = mesh_state()
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    ok = bool(m.get('ok'))
    accent = BLUE if ok else AMBER
    d.rounded_rectangle((6, 6, W-7, H-7), 12, outline=accent, width=2, fill=(12, 26, 38))
    d.text((16, 12), 'Mesh', font=F_TITLE, fill=accent)
    conn = m.get('connection') or {}
    if not ok:
        err = m.get('error') or conn.get('error') or 'no radio'
        rows = [('~', 'Meshtastic radio'), ('!', str(err)[:26]), ('', 'Plug the radio into the'), ('', 'Pi USB port, or set its'), ('', 'Wi-Fi to join MapPI3.')]
        y = 50
        for mark, text in rows:
            color = RED if mark == '!' else AMBER if mark == '~' else WHITE
            d.text((16, y), text, font=F_BODY, fill=color); y += 20
        d.text((16, H-23), 'press = next page', font=F_TINY, fill=DIM)
        return img
    me = m.get('me') or {}; radio = m.get('radio') or {}
    batt = me.get('battery')
    power = 'USB power' if batt is not None and batt > 100 else f'{batt}%' if batt is not None else ''
    d.text((78, 16), f"{(me.get('long') or me.get('short') or '').strip()[:10]} · {(conn.get('via') or '').upper()}", font=F_SMALL, fill=WHITE)
    d.text((16, 38), f"{radio.get('preset') or ''} · {radio.get('region') or ''} · {power}"[:34], font=F_TINY, fill=DIM)
    heading = None
    try:
        sense = sense_payload(api('/api/sense', timeout=0.3))
        h = (sense.get('orientation') or {}).get('north_heading', sense.get('compass'))
        heading = float(h) if h is not None else None
    except Exception:
        heading = None
    nodes = (m.get('nodes') or [])[:4]
    y = 54
    if not nodes:
        d.text((16, y + 6), 'No other nodes heard yet.', font=F_BODY, fill=WHITE); y += 40
    for n in nodes:
        name = (n.get('long') or n.get('short') or n.get('id') or '?').strip()
        d.text((16, y), name[:17], font=F_BODY, fill=WHITE)
        bits = []
        if n.get('miles') is not None:
            mi = n['miles']
            bits.append(f"{mi:.1f} mi {CARDINAL[int(((n.get('bearing') or 0) + 22.5) // 45) % 8]}" if mi >= 0.1 else f"{int(mi * 5280)} ft")
        if n.get('hops'): bits.append(f"{n['hops']} hop" + ('s' if n['hops'] > 1 else ''))
        bits.append(ago_text(n.get('ago')) + ' ago' if n.get('ago') is not None else 'not heard yet')
        d.text((16, y + 18), ' · '.join(bits)[:30], font=F_TINY, fill=DIM)
        draw_bars(d, W - 34, y + 2, n.get('snr'), GREEN)
        if n.get('bearing') is not None:
            rel = (n['bearing'] - heading) % 360 if heading is not None else n['bearing']
            draw_arrow(d, W - 52, y + 10, rel, 9, AMBER if heading is not None else DIM)
        y += 36
    msgs = m.get('messages') or []
    d.line((12, H-62, W-13, H-62), fill=(45, 70, 90), width=1)
    if msgs:
        last = msgs[-1]
        who = 'you' if last.get('mine') else (last.get('fromName') or last.get('from') or '?').strip()
        d.text((16, H-56), f"{who[:14]} · {ago_text(time.time() - (last.get('at') or time.time()))} ago", font=F_TINY, fill=AMBER)
        for i, line in enumerate(wrap(last.get('text') or '', 28)[:2]):
            d.text((16, H-42 + i * 14), line, font=F_SMALL, fill=WHITE)
    else:
        d.text((16, H-50), 'No messages yet.', font=F_SMALL, fill=DIM)
    return img

def poll_mesh_popup():
    """New incoming text message -> full-screen popup (old messages are not replayed after a restart)."""
    global popup_event, popup_until
    m = mesh_state(max_age=3.0)
    msgs = [x for x in (m.get('messages') or []) if not x.get('mine')]
    if not _mesh_primed[0]:
        _mesh_seen.update(x.get('id') for x in msgs)
        _mesh_primed[0] = bool(m.get('ok'))
        return False
    for x in msgs:
        if x.get('id') in _mesh_seen: continue
        _mesh_seen.add(x.get('id'))
        popup_event = {'type': 'mesh_message', 'from': (x.get('fromName') or x.get('from') or '?').strip(), 'text': x.get('text') or '', 'direct': x.get('direct'), 'snr': x.get('snr')}
        popup_until = time.time() + 8.0
        return True
    return False

def render_popup(event):
    etype = event.get('type') or 'game_event'; label = event.get('label') or etype.replace('_',' ')
    if etype == 'mesh_message':
        head = ('+Direct from ' if event.get('direct') else '+Mesh · ') + str(event.get('from') or '?')[:16]
        lines = [head] + wrap(event.get('text') or '', 24)[:7]
        if event.get('snr') is not None: lines.append('~signal SNR ' + str(round(event['snr'], 1)))
        return draw_card('Message', lines, BLUE, 'auto returns · press next')
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

def herbie_cycle(period=6.0, offset=0, pool=None):
    pool = tuple(p for p in (pool or HERBIE_EXPRESSION_ORDER) if p not in HERBIE_MANUAL_ONLY)
    idx = int(time.time() // max(1.0, float(period))) + int(offset)
    return pool[idx % len(pool)]

def herbie_idle_face(period=6.0, offset=0):
    idx = int(time.time() // max(1.0, float(period))) + int(offset)
    # Four friendly priority beats, then one random cameo. Scenario-only faces stay out of idle.
    if idx % 5 == 4:
        return HERBIE_RANDOM_CAMEOS[(idx // 5) % len(HERBIE_RANDOM_CAMEOS)]
    return HERBIE_IDLE_PRIORITY[idx % len(HERBIE_IDLE_PRIORITY)]

def herbie_high_af_now(now=None):
    now = now or datetime.datetime.now()
    return now.hour in (4, 16) and now.minute == 20

TILT_DIRECTION_ASSETS = {
    # Use the provided Herbie sheet: motion examples for left/right, turnaround sheet for top/bottom.
    'left': (('motions','tilted-left'), ('expressions','side-eye'), ('expressions','curious')),
    'right': (('motions','tilted-right'), ('expressions','suspicious'), ('expressions','cheeky')),
    'top': (('turnarounds','top'), ('expressions','wow'), ('expressions','surprised')),
    'bottom': (('turnarounds','bottom'), ('expressions','oh-no'), ('expressions','facepalm')),
}

def herbie_best_asset(options):
    for kind, name in options:
        try:
            ref = herbie_asset_ref(kind, name)
            if ref:
                return ref
        except Exception:
            continue
    return 'expressions/surprised'

def herbie_tilt_direction(roll, pitch, threshold=8.0):
    if roll is None or pitch is None:
        return None
    if max(abs(roll), abs(pitch)) < threshold:
        return None
    if abs(roll) >= abs(pitch):
        return 'right' if roll < 0 else 'left'
    # Tilting the Pi up gives positive pitch on this Sense HAT mounting, which shows Herbie's top.
    return 'top' if pitch > 0 else 'bottom'

def herbie_directional_tilt_face(roll, pitch, threshold=8.0):
    direction = herbie_tilt_direction(roll, pitch, threshold)
    if not direction:
        return None
    asset = herbie_best_asset(TILT_DIRECTION_ASSETS[direction])
    label = {'left':'tilted left','right':'tilted right','top':'top view tilt','bottom':'bottom view tilt'}[direction]
    mag = max(abs(roll), abs(pitch))
    level = 3 if mag >= HERBIE_TILT_LEVELS[2] else 2 if mag >= HERBIE_TILT_LEVELS[1] else 1
    if direction in ('left', 'right'):
        if level > 1 and herbie_asset_ref('motions', f'tilted-{direction}-{level}'):
            asset = f'motions/tilted-{direction}-{level}'
        label = f'{label} {round(mag)} deg'
    else:
        # Herbie starts looking up/down first; the top/bottom view only shows at the strongest tilt.
        way = 'up' if direction == 'top' else 'down'
        step = f'motions/tilted-{way}' if level == 1 else f'motions/tilted-{way}-2' if level == 2 else None
        if step and herbie_asset_path_from_ref(step):
            asset = step
        label = f'looking {way} {round(mag)} deg' if step else label
    return asset, label, direction

# Low battery: at or below 40% Herbie keeps rotating his normal faces and shows the battery face for
# a few seconds every few minutes. Battery comes from /api/status power (PiSugar); unknown = no reminder.
LOW_BATTERY_PCT = 40
LOW_BATTERY_EVERY_S = 180
LOW_BATTERY_SHOW_S = 6

def battery_percent(status):
    power = status.get('power') if isinstance(status, dict) and isinstance(status.get('power'), dict) else {}
    try:
        return float(power['percent']) if power.get('percent') is not None else None
    except (TypeError, ValueError):
        return None

def low_battery_reminder(status, now_ts=None):
    pct = battery_percent(status)
    if pct is None or pct > LOW_BATTERY_PCT:
        return None
    if (now_ts or time.time()) % LOW_BATTERY_EVERY_S < LOW_BATTERY_SHOW_S:
        return 'motions/low-battery', f'battery {round(pct)}% - charge soon'
    return None

HERBIE_EVENT_STATE = {'gps_fix': None, 'gps_lock_until': 0.0}

def herbie_event_face(status, now_ts=None):
    """Face for an active event: app-set herbie_event first, then GPS just locked, then charging."""
    if not isinstance(status, dict) or status.get('_error'):
        return None
    t = time.time() if now_ts is None else now_ts
    st = status.get('state') if isinstance(status.get('state'), dict) else {}
    ev = st.get('herbie_event') if isinstance(st.get('herbie_event'), dict) else {}
    try:
        active = bool(ev.get('name')) and float(ev.get('until') or 0) > t
    except (TypeError, ValueError):
        active = False
    if active:
        return herbie_group_face(ev['name'], 'happy', period=6, now_ts=t), str(ev.get('reason') or ev['name'])[:28]
    gps = status.get('gps') if isinstance(status.get('gps'), dict) else {}
    fix = bool(gps.get('fix'))
    if HERBIE_EVENT_STATE['gps_fix'] is False and fix:
        HERBIE_EVENT_STATE['gps_lock_until'] = t + 30
    HERBIE_EVENT_STATE['gps_fix'] = fix
    if t < HERBIE_EVENT_STATE['gps_lock_until']:
        return herbie_group_face('gps-locked', 'gps-locked', period=6, now_ts=t), f"GPS locked - {gps.get('satellites') or '?'} sats"
    power = status.get('power') if isinstance(status.get('power'), dict) else {}
    if power.get('charging') is True and t % 120 < 8:
        return herbie_group_face('charging', 'charging', period=4, now_ts=t), 'charging'
    return None

def herbie_calendar_face(status, now_ts=None):
    """Holidays, special days, hike days and goals show as a cameo: 25 s of every 90 s when big, 12 s of every 3 min when small."""
    cal = status.get('herbie_calendar') if isinstance(status, dict) and isinstance(status.get('herbie_calendar'), dict) else {}
    if not cal.get('group'):
        return None
    t = time.time() if now_ts is None else now_ts
    period, show = (90, 25) if cal.get('strength') == 'high' else (180, 12)
    if t % period < show:
        return herbie_group_face(cal['group'], 'happy', period=6, now_ts=t), str(cal.get('reason') or cal['group'])[:28]
    return None

def whisplay_herbie_state(now=None, status=None, sense=None, net=None):
    now = now or datetime.datetime.now()
    # Tilt is the live interaction path, so read the fast Sense endpoint first and
    # short-circuit before slower status/network probes. On the Pi, /api/sense is
    # ~tens of ms while status/network can take 1-2s when services are busy/offline.
    sense = sense if sense is not None else sense_payload(api('/api/sense', timeout=0.25))
    set_live_heading(sense)
    roll, pitch, tilt_source = sense_tilt_axes(sense)
    motion_reaction = herbie_motion_reaction(sense)
    tilt_reaction = herbie_directional_tilt_face(roll, pitch, threshold=8.0)
    if herbie_high_af_now(now):
        return 'high-af', '4:20 trail minute'
    if motion_reaction:
        return motion_reaction[0], motion_reaction[1]
    if tilt_reaction:
        return tilt_reaction[0], tilt_reaction[1]
    status = status if status is not None else cached_status()
    net = net if net is not None else api('/api/network/status', timeout=0.6)
    temp = sense.get('temperature') if sense.get('temperature') is not None else sense.get('temp_c')
    battery_reminder = low_battery_reminder(status)
    event_face = herbie_event_face(status)
    try: tilted = roll is not None and pitch is not None and max(abs(roll), abs(pitch)) >= 12
    except Exception: tilted = False
    try: hot = temp is not None and float(temp) >= 30
    except Exception: hot = False
    if status.get('_error'):
        return herbie_idle_face(5.0), 'offline face loop'
    if event_face:
        return event_face
    if battery_reminder:
        return battery_reminder
    calendar_face = herbie_calendar_face(status)
    if calendar_face:
        return calendar_face
    if hot:
        return herbie_group_face('hot', 'sweating', period=8), f'temp {temp_f_text(temp)}'
    if tilted:
        return 'surprised', 'tilt reaction'
    if net.get('_error'):
        if status.get('hotspot_active') or status.get('connection_mode') == 'hotspot':
            return herbie_idle_face(5.0, 7), 'field hotspot mode'
        return ['confused','thinking','side-eye','focused'][int(time.time() // 4) % 4], 'network status unknown'
    if not net.get('has_default_route'):
        return herbie_idle_face(5.0, 11), 'field hotspot mode'
    return herbie_idle_face(5.0), 'live Whisplay avatar'

def num(value, default=None):
    try:
        return float(value)
    except Exception:
        return default

def signed_angle(value):
    v = num(value)
    if v is None:
        return None
    return ((v + 180.0) % 360.0) - 180.0

def accel_angle(value, z=1.0):
    v = num(value)
    zv = max(0.001, abs(num(z, 1.0) or 1.0))
    if v is None:
        return None
    try:
        return math.degrees(math.atan2(v, zv))
    except Exception:
        return None

def sense_tilt_axes(sense):
    sense = sense if isinstance(sense, dict) else {}
    orient = sense.get('orientation') if isinstance(sense.get('orientation'), dict) else {}
    liquid = sense.get('liquid_display') if isinstance(sense.get('liquid_display'), dict) else {}
    face = sense.get('animated_face') if isinstance(sense.get('animated_face'), dict) else {}
    accel = liquid.get('display_accel') if isinstance(liquid.get('display_accel'), dict) else {}
    if not accel:
        accel = liquid.get('raw_accel') if isinstance(liquid.get('raw_accel'), dict) else {}
    if not accel:
        accel = sense.get('display_accel') if isinstance(sense.get('display_accel'), dict) else {}
    if not accel:
        accel = sense.get('raw_accel') if isinstance(sense.get('raw_accel'), dict) else {}
    if not accel:
        accel = face.get('accel') if isinstance(face.get('accel'), dict) else {}
    accel_roll = accel_angle(accel.get('x'), accel.get('z', liquid.get('gz', 1.0))) if accel else None
    accel_pitch = accel_angle(accel.get('y'), accel.get('z', liquid.get('gz', 1.0))) if accel else None
    orient_roll = signed_angle(orient.get('level_x', orient.get('roll', sense.get('roll'))))
    orient_pitch = signed_angle(orient.get('level_y', orient.get('pitch', sense.get('pitch'))))
    try:
        accel_mag = max(abs(accel_roll), abs(accel_pitch))
    except Exception:
        accel_mag = 0.0
    try:
        orient_mag = max(abs(orient_roll), abs(orient_pitch))
    except Exception:
        orient_mag = 0.0
    # Live liquid mode updates display_accel every frame while orientation degrees
    # can remain near-frozen; prefer accel-derived tilt once it is readable.
    if accel_roll is not None and accel_pitch is not None and (accel_mag >= 5.0 or orient_roll is None or orient_pitch is None or orient_mag < 5.0):
        return accel_roll, accel_pitch, 'liquid accel'
    return orient_roll, orient_pitch, orient.get('level_status') or 'orientation'

def sense_accel_vector(sense):
    sense = sense if isinstance(sense, dict) else {}
    liquid = sense.get('liquid_display') if isinstance(sense.get('liquid_display'), dict) else {}
    accel = liquid.get('display_accel') if isinstance(liquid.get('display_accel'), dict) else {}
    if not accel:
        accel = liquid.get('raw_accel') if isinstance(liquid.get('raw_accel'), dict) else {}
    if not accel:
        accel = sense.get('display_accel') if isinstance(sense.get('display_accel'), dict) else {}
    if not accel:
        accel = sense.get('raw_accel') if isinstance(sense.get('raw_accel'), dict) else {}
    if not accel:
        face = sense.get('animated_face') if isinstance(sense.get('animated_face'), dict) else {}
        accel = face.get('accel') if isinstance(face.get('accel'), dict) else {}
    x = num(accel.get('x')); y = num(accel.get('y')); z = num(accel.get('z'))
    if x is None or y is None or z is None:
        return None
    return (x, y, z)

def herbie_motion_reaction(sense, now=None):
    now = time.time() if now is None else float(now)
    if HERBIE_MOTION_STATE.get('event') and now < float(HERBIE_MOTION_STATE.get('event_until') or 0.0):
        return HERBIE_MOTION_STATE['event']
    vec = sense_accel_vector(sense)
    face = sense.get('animated_face') if isinstance(sense, dict) and isinstance(sense.get('animated_face'), dict) else {}
    face_jerk = num(face.get('jerk'))
    if vec is None:
        return None
    last = HERBIE_MOTION_STATE.get('last_accel')
    last_at = float(HERBIE_MOTION_STATE.get('last_at') or 0.0)
    HERBIE_MOTION_STATE['last_accel'] = vec
    HERBIE_MOTION_STATE['last_at'] = now
    if not last or now - last_at > 2.0:
        return None
    dx = vec[0] - last[0]; dy = vec[1] - last[1]; dz = vec[2] - last[2]
    delta = math.sqrt(dx*dx + dy*dy + dz*dz)
    jerk = max(delta / max(0.05, now - last_at), face_jerk or 0.0)
    hits = [t for t in HERBIE_MOTION_STATE.get('hits', []) if now - t <= 1.2]
    if delta >= 0.18 or jerk >= 1.8:
        hits.append(now)
    HERBIE_MOTION_STATE['hits'] = hits
    event = None
    if len(hits) >= 2:
        event = ('motions/shaking', 'shake streak', 'shake', max(jerk, delta))
        HERBIE_MOTION_STATE['hits'] = []
        hold = 0.75
    elif delta >= 0.42 or (face_jerk is not None and face_jerk >= 3.0):
        event = ('expressions/surprised', 'sudden jolt', 'jolt', max(jerk, delta))
        hold = 0.55
    if event:
        HERBIE_MOTION_STATE['event'] = event
        HERBIE_MOTION_STATE['event_until'] = now + hold
        HERBIE_MOTION_STATE['peak'] = event[3]
        return event
    return None

def herbie_pawn_state():
    sense = sense_payload(api('/api/sense', timeout=0.25))
    set_live_heading(sense)
    roll, pitch, tilt_source = sense_tilt_axes(sense)
    now = datetime.datetime.now()
    hour = now.hour
    idle = herbie_idle_face(6.0)
    motion_reaction = herbie_motion_reaction(sense)
    tilt_reaction = herbie_directional_tilt_face(roll, pitch, threshold=8.0)
    if herbie_high_af_now(now):
        return {'mood': 'high-af', 'reason': '4:20 trail minute', 'accent': GREEN, 'details': ['fast tilt lane', 'priority faces + cameos'], 'idle': idle}
    if motion_reaction:
        details = [f'motion {motion_reaction[2]} peak {round(motion_reaction[3],1)}', 'short-lived sensor reaction', 'priority faces + cameos']
        return {'mood': motion_reaction[0], 'reason': motion_reaction[1], 'accent': AMBER, 'details': details, 'idle': idle}
    if tilt_reaction:
        details = [f'tilt {tilt_source} r{round(roll)} p{round(pitch)}', 'fast Sense-only reaction', 'priority faces + cameos']
        return {'mood': tilt_reaction[0], 'reason': tilt_reaction[1], 'accent': AMBER, 'details': details, 'idle': idle}
    status = cached_status()
    net = api('/api/network/status', timeout=0.6)
    weather = api('/api/weather?days=1', timeout=0.6)
    temp_c = num(sense.get('temperature') if sense.get('temperature') is not None else sense.get('temp_c'))
    humidity = num(sense.get('humidity'))
    pressure = num(sense.get('pressure'))
    compass = num(sense.get('compass') or sense.get('heading'))
    battery_reminder = low_battery_reminder(status)
    event_face = herbie_event_face(status)
    calendar_face = herbie_calendar_face(status)
    api_available = not (status.get('_error') and sense.get('_error') and net.get('_error') and weather.get('_error'))
    mood = idle
    reason = 'all-face wandering loop'
    accent = GREEN
    if herbie_high_af_now(now):
        mood, reason, accent = 'high-af', '4:20 trail minute', GREEN
    elif api_available and tilt_reaction:
        mood, reason, accent = tilt_reaction[0], tilt_reaction[1], AMBER
    elif api_available and event_face:
        mood, reason, accent = event_face[0], event_face[1], AMBER
    elif api_available and battery_reminder:
        mood, reason, accent = battery_reminder[0], battery_reminder[1], RED
    elif api_available and calendar_face:
        mood, reason, accent = calendar_face[0], calendar_face[1], GREEN
    elif api_available and temp_c is not None and temp_c >= 34:
        mood, reason, accent = herbie_group_face('hot', 'melting', period=8), f'hot field kit {temp_f_text(temp_c)}', RED
    elif api_available and temp_c is not None and temp_c >= 29:
        mood, reason, accent = herbie_group_face('hot', 'sweating', period=10), f'warm sensors {temp_f_text(temp_c)}', AMBER
    elif api_available and roll is not None and pitch is not None and max(abs(roll), abs(pitch)) >= 45:
        mood, reason, accent = 'oh-no', 'big tilt / picked up', AMBER
    elif api_available and roll is not None and pitch is not None and max(abs(roll), abs(pitch)) >= 16:
        mood, reason, accent = 'surprised', 'tilt reaction', AMBER
    elif api_available and humidity is not None and humidity >= 88:
        mood, reason, accent = ['overwhelmed','sweating','face-with-tears','determined'][int(time.time() // 4) % 4], f'humid air {round(humidity)}%', AMBER
    elif api_available and (hour >= 22 or hour < 5):
        mood, reason, accent = idle, 'night trail buddy awake', GREEN
    elif api_available and 5 <= hour < 7:
        mood, reason, accent = herbie_group_face('morning', 'greetings', period=10), 'early trail wakeup', GREEN
    elif api_available and net.get('_error'):
        if status.get('hotspot_active') or status.get('connection_mode') == 'hotspot':
            mood, reason, accent = herbie_idle_face(5.0, 7), 'offline hotspot trail mode', GREEN
        else:
            mood, reason, accent = ['confused','thinking','side-eye','focused'][int(time.time() // 4) % 4], 'network status unknown', AMBER
    elif api_available and not net.get('has_default_route'):
        mood, reason, accent = herbie_idle_face(5.0, 11), 'offline hotspot trail mode', GREEN
    elif api_available and weather.get('current'):
        mood, reason, accent = ['curious','happy','wow','focused'][int(time.time() // 4) % 4], 'watching live sky', BLUE
    details = []
    if temp_c is not None: details.append(f'temp {temp_f_text(temp_c)}')
    if humidity is not None: details.append(f'hum {round(humidity)}%')
    if pressure is not None: details.append(f'press {round(pressure)}hPa')
    if roll is not None and pitch is not None: details.append(f'tilt {tilt_source} r{round(roll)} p{round(pitch)}')
    if compass is not None: details.append(f'head {round(compass)}°')
    if status.get('_error'):
        details.append('offline face loop')
    details.append('priority faces + cameos')
    return {'mood': mood, 'reason': reason, 'accent': accent, 'details': details[:5], 'idle': idle}

def draw_herbie_mood():
    state = herbie_pawn_state()
    mood = state['mood']
    accent = state['accent']
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, W-7, H-7), 12, outline=accent, width=2, fill=(12, 24, 34))
    d.text((14, 12), 'Herbie', font=F_TITLE, fill=accent)
    blinking = int(time.time() * 2) % 29 == 0
    publish_face(herbie_gaze_ref(mood), state['reason'], 'herbie')
    p = herbie_asset_path_from_ref(blink_face(mood) if blinking else herbie_gaze_ref(mood))
    if p:
        try:
            face = face_image(p, (196, 136))
            x = (W - face.width) // 2
            y = 44 + max(0, (132 - face.height) // 2)
            img.paste(face, (x, y), face)
            if compass_eligible(mood):
                draw_compass_needle(img, x, y, face.width / 300.0, LIVE_HEADING[0])
        except Exception:
            pass
    y = 184
    d.text((16, y), herbie_asset_label(mood)[:25], font=F_BODY, fill=accent); y += 18
    d.text((16, y), state['reason'][:28], font=F_SMALL, fill=WHITE); y += 15
    for line in state['details'][:4]:
        d.text((16, y), line[:30], font=F_TINY, fill=DIM); y += 12
    d.text((16, H-23), 'offline mood loop · press next', font=F_TINY, fill=DIM)
    return img

# Tell the MapPI3 app which Herbie face is on screen, so the phone/web app shows the same one.
# Sent in the background (never blocks drawing), only when the face changes or every 4 s.
_now_sent = {'ref': None, 'at': 0.0}
def publish_face(ref, reason, page_name):
    ref = str(ref or '')
    if not ref:
        return
    if '/' not in ref:
        ref = 'expressions/' + ref
    t = time.time()
    if ref == _now_sent['ref'] and t - _now_sent['at'] < 4.0:
        return
    _now_sent.update(ref=ref, at=t)
    heading = LIVE_HEADING[0] if compass_eligible(ref) else None
    threading.Thread(target=post_command, args=('herbie-now', {'ref': ref, 'reason': str(reason or '')[:60], 'page': page_name, 'heading': heading}), kwargs={'timeout': 0.8}, daemon=True).start()

def render():
    if phone_input_until and time.time() < phone_input_until: return render_phone_input()
    if popup_event and time.time() < popup_until: return render_popup(popup_event)
    title = PAGES[page % len(PAGES)]
    if title == 'Buddy Home':
        mood, caption = whisplay_herbie_state()
        blinking = int(time.time() * 2) % 23 == 0
        shown = mood if blinking else herbie_gaze_ref(mood)
        publish_face(herbie_gaze_ref(mood), caption, 'home')
        return draw_face(shown, caption, blink=blinking)
    if title == 'Herbie': return draw_herbie_mood()
    if title == 'Field Kit': return draw_card('Field Kit/Power', lines_fieldkit(), GREEN)
    if title == 'Compass+Level': return draw_card('Compass + Level', lines_compass(), BLUE)
    if title == 'Weather+Sky': return draw_weather()
    if title == 'Mesh': return draw_mesh()
    if title == 'Network': return draw_network()
    return draw_card('Trail Safety', lines_safety(), AMBER)

def main():
    global running, page, popup_until
    hw = create_hw('whisplay-mappi3-dashboard', 'MapPI3 Dash', 'M3', 100)
    def next_page():
        global page, popup_until
        page += 1; popup_until = 0.0; show(hw, render())
    def exit_req():
        global running
        running = False
    hw.on_button_press(next_page); hw.on_exit_request(exit_req); show(hw, render())
    try:
        last = 0
        while running:
            time.sleep(0.12); active = page % len(PAGES)
            phone_changed = poll_phone_input()
            overlay = phone_changed or poll_popup() or poll_mesh_popup() or (phone_input_until and time.time() < phone_input_until) or (popup_event and time.time() < popup_until)
            # Herbie pages animate (~3 fps); the text cards only need a refresh each second. Every
            # redraw also queries the agent, so this keeps CPU and battery use down on the Zero.
            gap = 0.32 if active in (0, 1) else 1.0
            if overlay or time.time() - last >= gap:
                last = time.time(); show(hw, render())
    finally:
        hw.cleanup()

if __name__ == '__main__':
    main()
