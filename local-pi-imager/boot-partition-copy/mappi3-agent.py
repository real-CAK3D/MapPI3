#!/usr/bin/env python3
import base64, fcntl, hashlib, http.server, io, json, math, os, pathlib, random, shlex, shutil, socket, sqlite3, ssl, struct, subprocess, threading, time, urllib.parse, urllib.request, uuid
APP_DIR = pathlib.Path('/opt/mappi3/app')
STATE = pathlib.Path('/var/lib/mappi3/state.json')
PORT = int(os.environ.get('MAPPI3_PORT','5050'))
HTTPS_PORT = int(os.environ.get('MAPPI3_HTTPS_PORT','5443'))
CERT_DIR = pathlib.Path('/var/lib/mappi3/certs')
CERT_FILE = CERT_DIR / 'mappi3-local.crt'
KEY_FILE = CERT_DIR / 'mappi3-local.key'
LIQUID_STATE = {'gx': 0.0, 'gy': 0.0, 'gz': 1.0}
LIQUID_PARTICLES = []
PACMAN_STATE = {}
SENSE_MODES = ['compass','compass-arrow','compass-cardinal','rotation-test','liquid','pacman','weather','fire','flashlight','sos','message','boot','sun','gps','clock','progress','beacon','stars','temp','humidity','pressure','custom','border','magic8','water','snake']
ALLOWED = {'status','restart-web','reboot','shutdown','update-app','gps-sample','toggle-hotspot','hotspot-on','connect-home-wifi','wifi-scan','wifi-save-network','wifi-connect-saved','network-status','tailscale-status','tailscale-login','remote-access-repair','sense-mode','calibrate','harden-hotspot','plugin-update','vnc-setup','vnc-disable','weather-refresh','noaa-refresh','online-maintenance','gps-diagnose','sense-diagnose','field-ai-verify','captive-setup','captive-disable','captive-status','gps-pps-setup','plugin-status','plugin-install','plugin-install-all','plugin-uninstall'}
SENSE_CACHE = {'ok': False, 'mode': 'compass', 'message': 'Sense HAT display loop starting', 'updated': 0, 'joystick': {'seq': 0, 'direction': '', 'pressed': False, 'updated': 0}}
SENSE_LOCK = threading.Lock()
KEY_NAMES = {103:'up',108:'down',105:'left',106:'right',28:'press'}
COMPASS_PATTERNS = {
    'N': [(3,0),(4,0),(3,1),(4,1),(2,2),(5,2),(3,2),(4,2),(3,3),(4,3),(3,4),(4,4),(3,5),(4,5),(3,6),(4,6),(3,7),(4,7)],
    'NE': [(7,0),(6,0),(7,1),(5,0),(7,2),(6,1),(5,2),(4,3),(3,4),(2,5),(1,6),(0,7)],
    'E': [(7,3),(7,4),(6,2),(6,5),(5,3),(5,4),(4,3),(4,4),(3,3),(3,4),(2,3),(2,4),(1,3),(1,4),(0,3),(0,4)],
    'SE': [(7,7),(6,7),(7,6),(5,7),(7,5),(6,6),(5,5),(4,4),(3,3),(2,2),(1,1),(0,0)],
    'S': [(3,7),(4,7),(3,6),(4,6),(2,5),(5,5),(3,5),(4,5),(3,4),(4,4),(3,3),(4,3),(3,2),(4,2),(3,1),(4,1),(3,0),(4,0)],
    'SW': [(0,7),(1,7),(0,6),(2,7),(0,5),(1,6),(2,5),(3,4),(4,3),(5,2),(6,1),(7,0)],
    'W': [(0,3),(0,4),(1,2),(1,5),(2,3),(2,4),(3,3),(3,4),(4,3),(4,4),(5,3),(5,4),(6,3),(6,4),(7,3),(7,4)],
    'NW': [(0,0),(1,0),(0,1),(2,0),(0,2),(1,1),(2,2),(3,3),(4,4),(5,5),(6,6),(7,7)],
}
SOS_MORSE_UNITS = [1,0,1,0,1,0,0,0,3,0,3,0,3,0,0,0,1,0,1,0,1,0,0,0,0,0,0]  # SOS = ... --- ...; 1=dot, 3=dash, 0=off gap

def sh(cmd, timeout=20):
    try:
        p=subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return {'ok': p.returncode == 0, 'code': p.returncode, 'output': p.stdout[-4000:]}
    except Exception as e:
        return {'ok': False, 'code': -1, 'output': str(e)}

def read_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def write_state(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, indent=2))

def normalize_mode(mode):
    raw = str(mode or 'compass').strip().lower().replace(' ', '-').replace('_','-')
    aliases = {'custom-message':'message','scroll-message':'message','sunrise':'sun','sunset':'sun','sunrise-sunset':'sun','gps-fix':'gps','weather-now':'weather','flash-light':'flashlight','compass arrow':'compass-arrow','compass-arrow':'compass-arrow','compass nsew':'compass-cardinal','compass-nsew':'compass-cardinal','compass cardinal':'compass-cardinal','compass-cardinal':'compass-cardinal','cardinal':'compass-cardinal','rotation':'rotation-test','rotation-test':'rotation-test','pac-man':'pacman','pac man':'pacman','pac':'pacman','game-pacman':'pacman'}
    raw = aliases.get(raw, raw)
    return raw if raw in SENSE_MODES else ('liquid' if raw.startswith('liq') else 'compass')

def gps_device():
    for dev in ('/dev/serial0','/dev/ttyACM0','/dev/ttyUSB0'):
        if pathlib.Path(dev).exists(): return dev
    return None

def gps_json_sample():
    out = sh('timeout 7 gpspipe -w -n 10 2>&1', timeout=10)['output']
    parsed=[]
    for line in out.splitlines():
        try: parsed.append(json.loads(line))
        except Exception: pass
    tpv = next((x for x in parsed if x.get('class') == 'TPV'), {})
    sky = next((x for x in parsed if x.get('class') == 'SKY'), {})
    dev = next((x for x in parsed if x.get('class') == 'DEVICE'), {})
    return {'raw': out[-2000:], 'tpv': tpv, 'sky': sky, 'device': dev}

def gps_sample():
    dev=gps_device()
    if not dev: return {'ok': False, 'device': None, 'output': 'No GPS serial device present at /dev/serial0, /dev/ttyACM0, or /dev/ttyUSB0'}
    sample = gps_json_sample()
    if sample['raw'].strip(): return {'ok': True, **sample, 'device': dev, 'gpsd_device': sample.get('device')}
    raw = sh(f"timeout 5 bash -lc 'stty -F {dev} 9600 -echo -icrnl; cat {dev}'", timeout=8)
    raw['device'] = dev
    return raw

def gps_status():
    dev = gps_device()
    if not dev: return {'ok': False, 'device': None, 'mode': 0, 'message': 'GPS serial device missing'}
    sample = gps_json_sample(); tpv = sample.get('tpv') or {}; sky = sample.get('sky') or {}; device = sample.get('device') or {}
    mode = int(tpv.get('mode') or 0)
    return {'ok': bool(dev), 'device': dev, 'mode': mode, 'fix': mode >= 2, 'lat': tpv.get('lat'), 'lon': tpv.get('lon'), 'alt': tpv.get('altHAE') or tpv.get('altMSL'), 'speed': tpv.get('speed'), 'track': tpv.get('track'), 'satellites': sky.get('uSat') or sky.get('nSat'), 'driver': device.get('driver'), 'bps': device.get('bps'), 'raw': sample.get('raw','')[-600:]}

def wifi_info():
    active = sh("nmcli -t -f NAME,TYPE,DEVICE connection show --active 2>/dev/null || true", timeout=5)['output']
    dev = sh("nmcli -t -f DEVICE,TYPE,STATE device 2>/dev/null || true", timeout=5)['output']
    hotspot_active = 'MapPI3-hotspot' in active
    ssid = ''
    for line in active.splitlines():
        parts=line.split(':')
        if len(parts) >= 3 and parts[1] == 'wifi' and parts[0] != 'MapPI3-hotspot': ssid = parts[0]
    return {'active_connections': active, 'devices': dev, 'hotspot_active': hotspot_active, 'home_wifi_ssid': ssid}

def _cpu_sample():
    try:
        vals=[int(x) for x in pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
        idle=vals[3]+(vals[4] if len(vals)>4 else 0); total=sum(vals)
        return idle,total
    except Exception: return 0,0

def system_stats():
    try:
        idle1,total1=_cpu_sample(); time.sleep(0.08); idle2,total2=_cpu_sample()
        dt=max(1,total2-total1); cpu=max(0,min(100, round((1-((idle2-idle1)/dt))*100,1)))
        mem={}
        for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
            k,v=line.split(':',1); mem[k]=int(v.strip().split()[0])
        total=mem.get('MemTotal',1); avail=mem.get('MemAvailable',0); used=total-avail
        disk=shutil.disk_usage('/')
        net={}
        for line in pathlib.Path('/proc/net/dev').read_text().splitlines()[2:]:
            if ':' not in line: continue
            name,rest=line.split(':',1); vals=rest.split(); net[name.strip()]={'rx_bytes':int(vals[0]),'tx_bytes':int(vals[8])}
        load=os.getloadavg() if hasattr(os,'getloadavg') else (0,0,0)
        uptime=float(pathlib.Path('/proc/uptime').read_text().split()[0])
        throttled=sh('vcgencmd get_throttled 2>/dev/null || true', timeout=3)['output'].strip()
        temp_raw=sh("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0", timeout=3)['output'].strip().splitlines()[-1]
        temp_c=round(int(temp_raw)/1000,1) if temp_raw.isdigit() else None
        return {'cpu_percent':cpu,'load1':round(load[0],2),'load5':round(load[1],2),'load15':round(load[2],2),'memory':{'total_mb':round(total/1024),'used_mb':round(used/1024),'available_mb':round(avail/1024),'percent':round((used/total)*100,1)},'disk':{'total_gb':round(disk.total/1e9,1),'used_gb':round(disk.used/1e9,1),'free_gb':round(disk.free/1e9,1),'percent':round((disk.used/disk.total)*100,1)},'temperature_c':temp_c,'temperature_f':round(temp_c*9/5+32,1) if temp_c is not None else None,'uptime_seconds':round(uptime),'network':net,'throttled':throttled,'sampled_at':time.time()}
    except Exception as e:
        return {'error':str(e),'sampled_at':time.time()}

def sense_snapshot():
    with SENSE_LOCK: return dict(SENSE_CACHE)

def set_sense_mode(mode, payload=None):
    global LIQUID_PARTICLES, PACMAN_STATE
    payload = payload or {}; mode = normalize_mode(mode)
    st=read_state(); st['sense_mode']=mode; st['sense_mode_updated_at']=time.time()
    if mode == 'liquid':
        LIQUID_PARTICLES = []
        LIQUID_STATE.update({'gx': 0.0, 'gy': 0.0, 'gz': 1.0})
        st['liquid_reset_at'] = time.time()
    if mode == 'pacman':
        PACMAN_STATE = {}
        st['pacman_reset_at'] = time.time()
    if 'message' in payload: st['sense_message'] = str(payload.get('message') or '')[:96]
    if 'brightness' in payload: st['sense_brightness'] = payload.get('brightness')
    if 'brightnessLevel' in payload: st['sense_brightness_level'] = payload.get('brightnessLevel')
    if 'routeProgress' in payload: st['route_progress'] = payload.get('routeProgress')
    if 'routeDistanceMiles' in payload: st['route_distance_miles'] = payload.get('routeDistanceMiles')
    if 'senseRotation' in payload: st['sense_rotation'] = payload.get('senseRotation')
    if 'scrollSpeed' in payload: st['sense_scroll_speed'] = payload.get('scrollSpeed')
    if 'senseColor' in payload: st['sense_color'] = str(payload.get('senseColor') or '#00aa55')[:16]
    if 'borderOnly' in payload: st['sense_border_only'] = bool(payload.get('borderOnly'))
    if 'hydrationAlarm' in payload and isinstance(payload.get('hydrationAlarm'), dict): st['hydration_alarm'] = payload.get('hydrationAlarm')
    if 'features' in payload and isinstance(payload.get('features'), dict): st['features'] = payload.get('features')
    write_state(st)
    with SENSE_LOCK:
        SENSE_CACHE['mode'] = mode; SENSE_CACHE['message'] = f'Sense HAT mode set to {mode}'; SENSE_CACHE['updated'] = time.time()
    return {'ok': True, 'sense_mode': mode, 'available_modes': SENSE_MODES, 'sense': sense_snapshot(), 'state': st}

def calibrate(target):
    target = (target or 'all').lower(); st=read_state(); st.setdefault('calibration', {})[target] = {'requested_at': time.time(), 'status': 'requested'}; write_state(st)
    messages = {'compass':'Rotate the whole Pi/Sense HAT slowly in a figure-eight, away from metal/magnets. Compass display uses Sense HAT get_compass() magnetic North first, with optional compass_offset_deg/compass_declination_deg in state. Compare heading to a real compass before hiking.','sense':'Lay the Sense HAT level for 3 seconds, then tilt forward/back/left/right so roll and pitch move smoothly.','gps':'Take the GPS outside or to a clear window. Wait for mode 2/3 fix and multiple satellites; indoors mode 1 is normal.','all':'Compass: figure-eight away from metal. Sense: level then tilt. GPS: clear sky until mode 2/3 fix.'}
    return {'ok': True, 'target': target, 'message': messages.get(target, messages['all']), 'state': st.get('calibration', {})}


def rotate_pixels_for_orientation(pixels, st=None):
    try:
        rotation = int((st or read_state()).get('sense_rotation') or 0) % 360
    except Exception:
        rotation = 0
    turns = (rotation // 90) % 4
    if turns == 0:
        return pixels
    out = [[0,0,0] for _ in range(64)]
    for y in range(8):
        for x in range(8):
            nx, ny = x, y
            if turns == 1:
                nx, ny = 7-y, x
            elif turns == 2:
                nx, ny = 7-x, 7-y
            elif turns == 3:
                nx, ny = y, 7-x
            out[ny*8+nx] = pixels[y*8+x]
    return out

def sense_set_pixels(sense, pixels, st=None):
    sense.set_pixels(rotate_pixels_for_orientation(pixels, st))

def put_pixels(sense, coords, color=(0,140,30), st=None):
    pixels = [[0,0,0] for _ in range(64)]
    for x,y in coords:
        if 0 <= x < 8 and 0 <= y < 8: pixels[y*8+x] = list(color)
    sense_set_pixels(sense, pixels, st)

def sense_scroll_speed(st):
    try: return max(0.025, min(0.2, float(st.get('sense_scroll_speed') or 0.055)))
    except Exception: return 0.055

def sense_brightness(st):
    levels=[16,32,56,88,120,160,205,255]
    try:
        level=int(st.get('sense_brightness_level') or 0)
        if 1 <= level <= 8: return levels[level-1]
    except Exception: pass
    try: return max(8, min(255, int(st.get('sense_brightness') or 120)))
    except Exception: return 120

def scale_color(color, brightness):
    factor=max(0.03, min(1.0, float(brightness)/255.0))
    return tuple(max(0, min(255, int(c*factor))) for c in color)

def text_once(sense, text, color=(0,160,60), speed=0.06):
    try: sense.show_message(str(text)[:96], text_colour=list(color), scroll_speed=speed)
    except Exception: pass


def corrected_compass_heading(raw_heading, st=None):
    # Sense HAT get_compass() returns magnetic heading in degrees from North.
    # Optional stored corrections let field calibration/declination keep the LED arrow honest.
    st = st or {}
    try: heading = float(raw_heading or 0.0)
    except Exception: heading = 0.0
    try: heading += float(st.get('compass_offset_deg') or 0.0)
    except Exception: pass
    try: heading += float(st.get('compass_declination_deg') or 0.0)
    except Exception: pass
    return (heading + 360.0) % 360.0

def compass_name(yaw):
    labels = ['N','NE','E','SE','S','SW','W','NW']
    return labels[int(((float(yaw or 0) + 22.5) % 360) // 45)]

def compass_north_bearing(yaw):
    # Sense HAT get_compass() reports where the Pi/Sense HAT top edge is facing.
    # A compass needle on the 8x8 matrix must point toward North relative to the device,
    # so invert the heading: top-facing-East means North is to the display's left/West.
    try: return (360.0 - float(yaw or 0.0)) % 360.0
    except Exception: return 0.0

def compass_display_bearing(yaw, st=None):
    # MapPI3 rotates every 8x8 frame for the mounted Sense HAT orientation. If the compass
    # pattern is selected before that rotation without compensation, the visible arrow is
    # shifted by sense_rotation. Pre-compensate so the physical LED arrow still points North.
    bearing = compass_north_bearing(yaw)
    try: rotation = int((st or {}).get('sense_rotation') or 0) % 360
    except Exception: rotation = 0
    return (bearing - rotation) % 360.0

def draw_compass_cardinal(sense, yaw, st=None):
    st = st or {}
    heading_name = compass_name(yaw)
    north_bearing = compass_north_bearing(yaw)
    display_bearing = compass_display_bearing(yaw, st)
    north_name = compass_name(display_bearing)
    brightness = sense_brightness(st or {})
    pixels = [[0,0,0] for _ in range(64)]
    green = list(scale_color((0,180,50), brightness))
    blue = list(scale_color((0,80,190), brightness))
    white = list(scale_color((220,220,220), brightness))
    # Bright cardinal anchors: N top, E right, S bottom, W left. The green block marks where North is relative to the device.
    anchors = {'N':[(3,0),(4,0),(3,1),(4,1)], 'E':[(6,3),(7,3),(6,4),(7,4)], 'S':[(3,6),(4,6),(3,7),(4,7)], 'W':[(0,3),(1,3),(0,4),(1,4)]}
    active = north_name[0] if north_name else 'N'
    for k, pts in anchors.items():
        for x,y in pts: pixels[y*8+x] = green if k == active else blue
    # Center cross keeps the matrix readable when rotated.
    for x,y in [(3,3),(4,3),(3,4),(4,4)]: pixels[y*8+x] = white
    sense_set_pixels(sense, pixels, st)
    with SENSE_LOCK:
        SENSE_CACHE['compass_display'] = {'mode':'cardinal','heading':heading_name,'yaw':round(float(yaw or 0),1),'north_pointer':compass_name(north_bearing),'north_bearing':round(north_bearing,1),'display_pointer':north_name,'display_bearing':round(display_bearing,1),'rotation':st.get('sense_rotation',0)}

def draw_rotation_test(sense, st=None, tick=0):
    brightness = sense_brightness(st or {})
    pixels = [[0,0,0] for _ in range(64)]
    colors = [scale_color((255,0,0), brightness), scale_color((0,180,0), brightness), scale_color((0,80,255), brightness), scale_color((255,220,0), brightness)]
    # Four colored corner blocks + sweeping white dot: easy to see if 90/180/270 rotation is correct.
    blocks = [([(0,0),(1,0),(0,1),(1,1)], colors[0]), ([(6,0),(7,0),(6,1),(7,1)], colors[1]), ([(6,6),(7,6),(6,7),(7,7)], colors[2]), ([(0,6),(1,6),(0,7),(1,7)], colors[3])]
    for pts, color in blocks:
        for x,y in pts: pixels[y*8+x] = list(color)
    path = [(x,3) for x in range(8)] + [(7,y) for y in range(4,8)] + [(x,7) for x in range(6,-1,-1)] + [(0,y) for y in range(6,2,-1)]
    x,y = path[tick % len(path)]; pixels[y*8+x] = list(scale_color((255,255,255), brightness))
    sense_set_pixels(sense, pixels, st)
    with SENSE_LOCK:
        SENSE_CACHE['rotation_test'] = {'rotation':(st or {}).get('sense_rotation',0),'tick':tick,'corners':'red NW, green NE, blue SE, yellow SW before rotation'}

def draw_compass(sense, yaw, st=None):
    st = st or {}
    heading_name = compass_name(yaw)
    north_bearing = compass_north_bearing(yaw)
    display_bearing = compass_display_bearing(yaw, st)
    name = compass_name(display_bearing)
    put_pixels(sense, COMPASS_PATTERNS.get(name, COMPASS_PATTERNS['N']), scale_color((0,160,50), sense_brightness(st)), st)
    with SENSE_LOCK:
        SENSE_CACHE['compass_display'] = {'mode':'arrow','heading':heading_name,'yaw':round(float(yaw or 0),1),'north_pointer':compass_name(north_bearing),'north_bearing':round(north_bearing,1),'display_pointer':name,'display_bearing':round(display_bearing,1),'rotation':st.get('sense_rotation',0)}

def _liquid_particles():
    global LIQUID_PARTICLES
    if not LIQUID_PARTICLES:
        # Legacy particle state is retained only for compatibility diagnostics. The live renderer
        # below uses a gravity-sorted bottle fill so the 8x8 display visibly shifts immediately.
        LIQUID_PARTICLES = [{'x':1.0 + (i % 6) * 1.08 + (0.24 if (i//6) % 2 else 0), 'y':2.25 + (i//6) * 0.78, 'vx':0.0, 'vy':0.0} for i in range(24)]
    return LIQUID_PARTICLES

def _liquid_bottle_pixels(gx, gy, gz, tick, brightness):
    """Render liquid like a bottle: fill the downhill side with a level surface.

    Particle dots settled into a static-looking blob on the real 8x8 Sense HAT. For field use,
    the readable cue is a bright water mass whose surface moves opposite the projected gravity
    vector. We sort cells by downhill gravity, fill a fixed volume, then add a tiny animated
    surface slosh so small hand movements are visible.
    """
    plane = math.sqrt(gx*gx + gy*gy)
    fill_cells = 26
    water = list(scale_color((0, 82, 220), brightness))
    deep = list(scale_color((0, 35, 145), brightness))
    foam = list(scale_color((190, 248, 255), brightness))
    glow = list(scale_color((40, 170, 255), brightness))
    pixels = [[0,0,0] for _ in range(64)]
    center_band = 0.16
    if plane < center_band:
        # Near level: start as a centered blob, then drift outward from center as tilt grows.
        # The real Pi often reports ~0.04-0.05 plane magnitude while visually level, so a wider
        # center band keeps tiny sensor bias from pinning the liquid to a side.
        if plane < 0.001:
            nx, ny = 0.0, 0.0
        else:
            nx, ny = gx / plane, gy / plane
        drift = min(1.0, plane / center_band)
        center_x = 3.5 + nx * drift * 1.55
        center_y = 3.5 + ny * drift * 1.55
        wave_phase = tick * 0.58
        ranked = []
        for y in range(8):
            for x in range(8):
                dx = x - center_x; dy = y - center_y
                radius = math.sqrt(dx*dx + dy*dy)
                angle_wave = 0.18 * math.sin((x * 1.4) + (y * 0.8) + wave_phase)
                # Lower score is closer to the current liquid center. A small downhill bias gives
                # it range-of-motion from the center without snapping to an edge.
                score = radius - (nx * (x - 3.5) + ny * (y - 3.5)) * drift * 0.35 + angle_wave
                ranked.append((score, x, y))
        ranked.sort()
        filled = {(x,y): score for score,x,y in ranked[:fill_cells]}
        surface = set()
        for x,y in filled:
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                n = (x+dx, y+dy)
                if 0 <= n[0] < 8 and 0 <= n[1] < 8 and n not in filled:
                    surface.add((x,y)); break
        for (x,y), score in filled.items():
            pixels[y*8+x] = foam if (x,y) in surface else (water if score < 2.2 else deep)
        surface_list = sorted(surface)
        if surface_list:
            sx, sy = surface_list[tick % len(surface_list)]
            pixels[sy*8+sx] = glow
        return pixels, {
            'surface_cells': len(surface), 'fill_cells': len(filled),
            'downhill': 'center' if drift < 0.35 else ('right' if abs(nx) > abs(ny) and nx > 0 else ('left' if abs(nx) > abs(ny) else ('down' if ny > 0 else 'up'))),
            'centered': True, 'center_x': round(center_x, 2), 'center_y': round(center_y, 2), 'center_drift': round(drift, 2)
        }

    # Positive projection means the cell is downhill. The small sinusoidal term creates a
    # readable slosh ripple without hiding the physical tilt direction.
    nx, ny = gx / plane, gy / plane
    wave_phase = tick * 0.62
    ranked = []
    for y in range(8):
        for x in range(8):
            cx, cy = x - 3.5, y - 3.5
            cross = -ny * cx + nx * cy
            ripple = 0.20 * math.sin(cross * 1.15 + wave_phase) * min(1.0, plane * 1.8)
            score = (nx * cx + ny * cy) + ripple
            ranked.append((score, x, y, cross))
    ranked.sort(reverse=True)
    filled = {(x,y): score for score,x,y,cross in ranked[:fill_cells]}
    surface = set()
    for x,y in filled:
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            n = (x+dx, y+dy)
            if 0 <= n[0] < 8 and 0 <= n[1] < 8 and n not in filled:
                surface.add((x,y)); break
    for (x,y), score in filled.items():
        pixels[y*8+x] = foam if (x,y) in surface else (water if score > 0.5 else deep)
    # A moving specular fleck on the surface helps CAK3D see that the loop is alive.
    surface_list = sorted(surface)
    if surface_list:
        sx, sy = surface_list[tick % len(surface_list)]
        pixels[sy*8+sx] = glow
    downhill = 'right' if abs(nx) > abs(ny) and nx > 0 else ('left' if abs(nx) > abs(ny) else ('down' if ny > 0 else 'up'))
    return pixels, {'surface_cells': len(surface), 'fill_cells': len(filled), 'downhill': downhill}

def draw_liquid(sense, orientation, tick, st=None):
    # Bottle-fill renderer: project accelerometer gravity into the LED plane and fill the
    # downhill side. This is intentionally more readable than free particles on an 8x8 matrix.
    brightness = sense_brightness(st or {})
    raw_error = None
    try:
        raw = sense.get_accelerometer_raw()
        ax = float(raw.get('x', 0.0)); ay = float(raw.get('y', 0.0)); az = float(raw.get('z', 1.0))
    except Exception as e:
        raw_error = str(e)
        ax = max(-1, min(1, float((orientation or {}).get('roll', 0)) / 38.0))
        ay = max(-1, min(1, float((orientation or {}).get('pitch', 0)) / 45.0))
        az = 1.0
    raw_ax, raw_ay, raw_az = ax, ay, az
    mag = max(0.25, math.sqrt(ax*ax + ay*ay + az*az))
    ax, ay, az = ax/mag, ay/mag, az/mag
    LIQUID_STATE['gx'] += (max(-1, min(1, ax)) - LIQUID_STATE['gx']) * 0.75
    LIQUID_STATE['gy'] += (max(-1, min(1, ay)) - LIQUID_STATE['gy']) * 0.75
    LIQUID_STATE['gz'] += (max(-1, min(1, az)) - LIQUID_STATE['gz']) * 0.35
    gx, gy, gz = LIQUID_STATE['gx'], LIQUID_STATE['gy'], LIQUID_STATE['gz']
    pixels, render = _liquid_bottle_pixels(gx, gy, gz, tick, brightness)
    sense_set_pixels(sense, pixels, st)
    with SENSE_LOCK:
        plane = math.sqrt(gx*gx + gy*gy)
        raw_plane = math.sqrt(raw_ax*raw_ax + raw_ay*raw_ay)
        SENSE_CACHE['liquid_display'] = {
            'gx': round(gx,3), 'gy': round(gy,3), 'gz': round(gz,3),
            'raw_accel': {'x': round(raw_ax,3), 'y': round(raw_ay,3), 'z': round(raw_az,3)},
            'normalized_accel': {'x': round(ax,3), 'y': round(ay,3), 'z': round(az,3)},
            'plane_magnitude': round(plane,3),
            'raw_plane_magnitude': round(raw_plane,3),
            'tilt_degrees': round(math.degrees(math.atan2(plane, max(0.001, abs(gz)))),1),
            'raw_tilt_degrees': round(math.degrees(math.atan2(raw_plane, max(0.001, abs(raw_az)))),1),
            'lit_leds': sum(1 for c in pixels if c != [0,0,0]),
            'particles': 0,
            'loop_target_hz': 16,
            'surface_cells': render.get('surface_cells'),
            'fill_cells': render.get('fill_cells'),
            'downhill': render.get('downhill'),
            'centered': render.get('centered', False),
            'center_x': render.get('center_x'),
            'center_y': render.get('center_y'),
            'center_drift': render.get('center_drift'),
            'raw_error': raw_error,
            'model': 'centered bottle-fill liquid + tilt drift + slosh shimmer + raw accel telemetry'
        }
def draw_fire(sense, tick):
    pixels=[]
    for y in range(8):
        for x in range(8):
            heat=max(0, 7-y + random.randint(-2,3) - abs(x-3.5)/2)
            pixels.append([min(180,int(heat*32)), min(90,int(heat*14)), 0])
    sense_set_pixels(sense, pixels, st if 'st' in locals() else None)

def draw_flashlight(sense, st):
    b = sense_brightness(st); sense.clear(b,b,b)

def draw_sos(sense, tick):
    # White-only SOS beacon: no scrolling text, no red frames. Morse timing loops ... --- ...
    unit = SOS_MORSE_UNITS[(tick // 2) % len(SOS_MORSE_UNITS)]
    if unit:
        b = sense_brightness(read_state())
        sense.clear(b, b, b)
    else:
        sense.clear(0, 0, 0)
    with SENSE_LOCK:
        SENSE_CACHE['sos_display'] = {'mode':'white-only-morse', 'signal':'... --- ...', 'lit': bool(unit), 'unit': unit}

def draw_weather(sense, temp, humidity, pressure):
    msg=f'{temp:.0f}F {humidity:.0f}% {pressure:.0f}mb' if pressure else f'{temp:.0f}F {humidity:.0f}%'
    text_once(sense, msg, (0,120,180), 0.055)

def draw_sun(sense, st):
    text_once(sense, st.get('sun_message') or 'SUNRISE / SUNSET CHECK APP', (220,100,0), 0.055)

def draw_gps(sense, gps, st=None):
    mode=int(gps.get('mode') or 0); sats=int(gps.get('satellites') or 0); color=scale_color((180,0,0) if mode<2 else ((180,120,0) if mode==2 else (0,150,0)), sense_brightness(st or {}))
    pixels=[[0,0,0] for _ in range(64)]
    for i in range(min(8,max(0,sats))): pixels[56+i]=list(color)
    for y in range(2,6):
        for x in range(2,6): pixels[y*8+x]=list(color)
    sense_set_pixels(sense, pixels, st if 'st' in locals() else None)

def draw_bar(sense, value, color):
    n=max(0,min(64,int(value))); pixels=[[0,0,0] for _ in range(64)]
    for i in range(n): pixels[63-i]=list(color)
    sense_set_pixels(sense, pixels, st if 'st' in locals() else None)

def draw_route_progress(sense, st):
    brightness=sense_brightness(st)
    progress=max(0.0, min(1.0, float(st.get('route_progress') or 0)))
    distance=max(0.0, float(st.get('route_distance_miles') or 0))
    complete=max(0, min(63, int(round(progress*63))))
    remaining=scale_color((255,255,255), brightness)
    done=scale_color((255,0,0), brightness)
    finish=scale_color((0,255,0), brightness)
    pixels=[]
    for i in range(64):
        if i == 63:
            pixels.append(list(finish))
        elif i <= complete and progress > 0:
            pixels.append(list(done))
        else:
            pixels.append(list(remaining))
    sense_set_pixels(sense, pixels, st if 'st' in locals() else None)
    with SENSE_LOCK:
        SENSE_CACHE['progress_meter']={'progress':progress,'percent':round(progress*100),'distance_miles':distance,'completed_leds':complete+1 if progress > 0 else 0,'finish_led':'green','remaining_leds':'white','completed_leds_color':'red'}

def parse_color(value, default=(0,140,80)):
    try:
        s=str(value or '').strip()
        if s.startswith('#') and len(s)==7: return tuple(int(s[i:i+2],16) for i in (1,3,5))
    except Exception: pass
    return default

def draw_border(sense, color):
    pixels=[[0,0,0] for _ in range(64)]
    for y in range(8):
        for x in range(8):
            if x in (0,7) or y in (0,7): pixels[y*8+x]=list(color)
    sense_set_pixels(sense, pixels, st if 'st' in locals() else None)

def draw_water_icon(sense, color=(0,80,220)):
    put_pixels(sense, [(3,0),(4,0),(2,1),(5,1),(2,2),(5,2),(1,3),(6,3),(1,4),(6,4),(2,5),(5,5),(3,6),(4,6),(3,7),(4,7)], color)

def draw_snake_frame(sense, tick, color=(0,220,70)):
    pixels=[[0,0,0] for _ in range(64)]
    path=[(x,1) for x in range(1,7)] + [(6,y) for y in range(2,7)] + [(x,6) for x in range(5,0,-1)] + [(1,y) for y in range(5,1,-1)]
    for i in range(7):
        x,y=path[(tick+i)%len(path)]; pixels[y*8+x]=list(color)
    hx,hy=path[(tick+6)%len(path)]; pixels[hy*8+hx]=[255,255,255]
    sense_set_pixels(sense, pixels, st if 'st' in locals() else None)

PACMAN_MAPS = [
    # 8x8 tribute layouts: # = electric-blue maze wall, . = pellet lane, o = power pellet.
    ("o......o", ".##.##..", "........", ".#.##.#.", ".#....#.", "........", "..##.##.", "o......o"),
    ("o.####.o", "........", ".##..##.", "........", "..####..", "........", ".##..##.", "o......o"),
    ("o..##..o", ".#....#.", "...##...", "##....##", "##....##", "...##...", ".#....#.", "o..##..o"),
    ("o......o", "..#..#..", ".#....#.", "...##...", "...##...", ".#....#.", "..#..#..", "o......o"),
]
PACMAN_DIRS = [(1,0),(-1,0),(0,1),(0,-1)]
# Classic arcade palette approximated for Sense HAT LEDs: Blinky, Pinky, Inky, Clyde.
PACMAN_GHOST_COLORS = [(255,0,0),(255,184,255),(0,255,255),(255,184,82)]
PACMAN_WALL_COLOR = (33,33,255)
PACMAN_PELLET_COLOR = (255,184,174)
PACMAN_POWER_COLOR = (255,184,174)
PACMAN_YELLOW = (255,255,0)
PACMAN_CHERRY = (255,0,0)
PACMAN_CHERRY_STEM = (0,255,0)
PACMAN_PELLET_DRAW_INTERVAL = 3
PACMAN_FRAME_SLEEP = 0.42
PACMAN_GHOST_MOVE_INTERVAL = 3
PACMAN_FRUITS_PER_MAP = 12
PACMAN_POWER_TICKS = 45

def _pacman_cells(layout):
    return [(x,y) for y,row in enumerate(layout) for x,ch in enumerate(row) if ch != '#']

def _pacman_step(point, direction):
    return ((point[0] + direction[0]) % 8, (point[1] + direction[1]) % 8)

def _pacman_neighbors(point, cells):
    cellset=set(cells)
    return [_pacman_step(point,d) for d in PACMAN_DIRS if _pacman_step(point,d) in cellset]

def _pacman_distance(a, b):
    dx=min(abs(a[0]-b[0]), 8-abs(a[0]-b[0])); dy=min(abs(a[1]-b[1]), 8-abs(a[1]-b[1]))
    return dx+dy

def _pacman_new_fruit(state):
    cells=state['cells']; blocked={state['pacman']} | {g['pos'] for g in state['ghosts']}
    choices=[c for c in cells if c not in blocked]
    return random.choice(choices or cells)

def _pacman_new_state():
    layout=PACMAN_MAPS[0]; cells=sorted(_pacman_cells(layout), key=lambda p:(p[1],p[0])); homes=list(reversed(cells))
    state={'map_index':0,'layout':layout,'cells':cells,'pacman':cells[0],'dir':(1,0),'mouth_open':True,'score':0,'fruit_count':0,'power':0,'caught':0,'ticks':0,'ghosts':[]}
    state['ghosts']=[{'pos':homes[i % len(homes)], 'dir':random.choice(PACMAN_DIRS), 'home':homes[i % len(homes)], 'eaten':0, 'color':PACMAN_GHOST_COLORS[i % len(PACMAN_GHOST_COLORS)]} for i in range(4)]
    state['fruit']=_pacman_new_fruit(state)
    return state

def _pacman_next_map(state):
    state['map_index']=(int(state.get('map_index') or 0)+1)%len(PACMAN_MAPS); layout=PACMAN_MAPS[state['map_index']]; cells=sorted(_pacman_cells(layout), key=lambda p:(p[1],p[0])); homes=list(reversed(cells))
    state.update({'layout':layout,'cells':cells,'pacman':cells[0],'dir':(1,0),'mouth_open':True,'power':0,'caught':0,'ticks':0})
    state['ghosts']=[{'pos':homes[i % len(homes)], 'dir':random.choice(PACMAN_DIRS), 'home':homes[i % len(homes)], 'eaten':0, 'color':PACMAN_GHOST_COLORS[i % len(PACMAN_GHOST_COLORS)]} for i in range(4)]
    state['fruit']=_pacman_new_fruit(state)

def _pacman_best_dir(start, target, cells, chase=True):
    dirs=_pacman_neighbors(start, cells); random.shuffle(dirs)
    if not dirs: return (0,0)
    chosen=(min if chase else max)(dirs, key=lambda p:_pacman_distance(p,target))
    return ((chosen[0]-start[0]) % 8 if abs(chosen[0]-start[0]) <= 1 else -1 if chosen[0] > start[0] else 1, (chosen[1]-start[1]) % 8 if abs(chosen[1]-start[1]) <= 1 else -1 if chosen[1] > start[1] else 1)

def _pacman_direction_to(start, target, cells, chase=True):
    opts=PACMAN_DIRS[:]; random.shuffle(opts)
    legal=[d for d in opts if _pacman_step(start,d) in set(cells)]
    if not legal: return (0,0)
    return (min if chase else max)(legal, key=lambda d:_pacman_distance(_pacman_step(start,d), target))

def _pacman_tick_state(state):
    state['ticks']=int(state.get('ticks') or 0)+1
    if state.get('caught',0):
        state['caught']-=1
        if state['caught'] <= 0: _pacman_next_map(state)
        return
    cells=state['cells']; active=[g['pos'] for g in state['ghosts'] if not g.get('eaten')]
    target=min(active, key=lambda p:_pacman_distance(state['pacman'],p)) if state.get('power') and active else state.get('fruit')
    state['dir']=_pacman_direction_to(state['pacman'], target, cells, chase=True)
    state['pacman']=_pacman_step(state['pacman'], state['dir'])
    if state['pacman'] == state.get('fruit'):
        state['score']+=10; state['fruit_count']+=1; state['power']=PACMAN_POWER_TICKS; state['fruit']=_pacman_new_fruit(state)
        if state['fruit_count'] % PACMAN_FRUITS_PER_MAP == 0: _pacman_next_map(state); return
    ghosts_should_move = state['ticks'] % PACMAN_GHOST_MOVE_INTERVAL == 0
    for g in state['ghosts']:
        if g.get('eaten'):
            g['eaten']-=1
            if g['eaten'] <= 0: g['pos']=g['home']
            continue
        if not ghosts_should_move:
            continue
        if state.get('power') and random.random() < 0.75:
            g['dir']=_pacman_direction_to(g['pos'], state['pacman'], cells, chase=False)
        elif random.random() < 0.70:
            g['dir']=_pacman_direction_to(g['pos'], state['pacman'], cells, chase=True)
        g['pos']=_pacman_step(g['pos'], g['dir'])
    for g in state['ghosts']:
        if g['pos'] != state['pacman'] or g.get('eaten'): continue
        if state.get('power'):
            g['eaten']=10; state['score']+=25
        else:
            state['caught']=6
    state['mouth_open']=not state.get('mouth_open', True); state['power']=max(0, int(state.get('power') or 0)-1)

def draw_pacman_frame(sense, tick, st=None):
    global PACMAN_STATE
    if not PACMAN_STATE: PACMAN_STATE=_pacman_new_state()
    state=PACMAN_STATE; _pacman_tick_state(state)
    brightness=sense_brightness(st or {})
    pixels=[[0,0,0] for _ in range(64)]
    def put(pt, color):
        x,y=pt; pixels[y*8+x]=list(scale_color(color, brightness))
    layout=state['layout']
    # Classic Pac-Man read: black maze, electric-blue walls, warm peach pellets.
    # On 8x8, bright/full-density pellets wash out Pac-Man and the ghosts, so dots are deliberately sparse and dim.
    for y,row in enumerate(layout):
        for x,ch in enumerate(row):
            if ch == '#':
                pixels[y*8+x]=list(scale_color(PACMAN_WALL_COLOR, brightness))
            elif ch == 'o' and (tick % 8) < 5:
                pixels[y*8+x]=list(scale_color(PACMAN_POWER_COLOR, max(28, int(brightness * 0.45))))
            elif ch == '.' and ((x + y + tick) % PACMAN_PELLET_DRAW_INTERVAL) == 0:
                pixels[y*8+x]=list(scale_color(PACMAN_PELLET_COLOR, max(18, int(brightness * 0.22))))
    if not state.get('caught'):
        put(state['fruit'], PACMAN_CHERRY)
        fx,fy=state['fruit']; stem=(fx, max(0, fy-1))
        if stem in state['cells'] and tick % 3 != 0: put(stem, PACMAN_CHERRY_STEM)
    for g in state['ghosts']:
        if g.get('eaten'):
            if g['eaten'] % 2 == 0: put(g['pos'], PACMAN_POWER_COLOR)
            continue
        color=(33,33,255) if state.get('power') and state['power'] % 4 != 0 else g['color']
        put(g['pos'], color)
    put(state['pacman'], (255,60,0) if state.get('caught') else (PACMAN_YELLOW if not state.get('power') else (255,255,140)))
    if state.get('mouth_open') and not state.get('caught'):
        mouth=_pacman_step(state['pacman'], state.get('dir') or (1,0))
        if mouth in _pacman_neighbors(state['pacman'], state['cells']): pixels[mouth[1]*8+mouth[0]]=[0,0,0]
    sense_set_pixels(sense, pixels, st)
    with SENSE_LOCK:
        SENSE_CACHE['pacman_display']={'model':'classic arcade-inspired 8x8 pacman maze: blue walls, sparse warm pellets, cherry, four slower ghosts','score':state.get('score',0),'fruit_count':state.get('fruit_count',0),'map_index':state.get('map_index',0),'power_ticks':state.get('power',0),'caught_flash_ticks':state.get('caught',0),'ghosts':len(state.get('ghosts') or []),'ghost_move_interval':PACMAN_GHOST_MOVE_INTERVAL,'fruits_per_map':PACMAN_FRUITS_PER_MAP,'frame_sleep':PACMAN_FRAME_SLEEP,'pellet_draw_interval':PACMAN_PELLET_DRAW_INTERVAL,'lit_leds':sum(1 for c in pixels if c != [0,0,0]),'palette':'wall=#2121ff pac=#ffff00 pellet=#ffb8ae blinky=#ff0000 pinky=#ffb8ff inky=#00ffff clyde=#ffb852'}

def sense_alarm_due(st):
    alarm=st.get('hydration_alarm') or {}
    if not alarm.get('enabled'): return False
    now=time.time(); last=float(alarm.get('lastFiredAt') or 0); minutes=float(alarm.get('intervalMinutes') or 0)
    return minutes > 0 and now-last >= minutes*60

def sense_loop():
    tick=0; last_text=0; last_gps={}; last_gps_at=0
    try:
        from sense_hat import SenseHat
        sense=SenseHat(); sense.low_light=True; sense.clear(0,40,18)  # non-blocking startup flash; boot/message modes handle scrolling text
        with SENSE_LOCK: SENSE_CACHE.update({'ok': True, 'message': 'Sense HAT display loop active', 'updated': time.time()})
        while True:
            st=read_state(); mode=normalize_mode(st.get('sense_mode') or 'compass')
            try:
                orient=sense.get_orientation(); raw_yaw=orient.get('yaw',0)
                try: magnetic_yaw=sense.get_compass()
                except Exception: magnetic_yaw=raw_yaw
                yaw=corrected_compass_heading(magnetic_yaw, st); temp_c=sense.get_temperature(); temp_f=temp_c*9/5+32; hum=sense.get_humidity(); pressure=sense.get_pressure()
                now=time.time()
                # GPS sampling can block for several seconds indoors; keep LED/joystick modes responsive.
                if mode == 'gps' or now - last_gps_at > 30:
                    last_gps = gps_status(); last_gps_at = now
                gps = last_gps or {'ok': False, 'message': 'GPS not sampled for this display mode yet'}
                if mode=='liquid': draw_liquid(sense, orient, tick, st)
                elif mode=='pacman': draw_pacman_frame(sense, tick, st)
                elif mode in ('compass','compass-arrow'): draw_compass(sense, yaw, st)
                elif mode=='compass-cardinal': draw_compass_cardinal(sense, yaw, st)
                elif mode=='rotation-test': draw_rotation_test(sense, st, tick)
                elif mode=='weather':
                    if time.time()-last_text>8: text_once(sense, f'{temp_f:.0f}F {hum:.0f}% {pressure:.0f}mb', (0,120,180), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='fire': draw_fire(sense,tick)
                elif mode=='flashlight': draw_flashlight(sense,st)
                elif mode=='sos': draw_sos(sense,tick)
                elif mode=='message':
                    if time.time()-last_text>6: text_once(sense, st.get('sense_message') or 'MAPPI3', (0,150,80), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='boot':
                    if time.time()-last_text>10: text_once(sense, st.get('boot_message') or 'WELCOME TO THE WILDERNESS', (0,120,20), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='sun':
                    if time.time()-last_text>8: draw_sun(sense,st); last_text=time.time()
                elif mode=='gps': draw_gps(sense,gps,st)
                elif mode=='clock':
                    if time.time()-last_text>5: text_once(sense, time.strftime('%I:%M %p'), (80,80,180), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='progress': draw_route_progress(sense, st)
                elif mode=='beacon': sense.clear(0, 0 if tick%2 else 80, 0 if tick%2 else 120)
                elif mode=='stars':
                    pixels=[[0,0,0] for _ in range(64)]
                    for _ in range(10): pixels[random.randrange(64)]=[random.choice([40,80,140]),random.choice([40,80,140]),random.choice([80,160,220])]
                    sense_set_pixels(sense, pixels, st if 'st' in locals() else None)
                elif mode=='temp': draw_bar(sense, max(0,min(64,(temp_f-20)/80*64)), (180 if temp_f>80 else 0,120,180 if temp_f<50 else 0))
                elif mode=='humidity': draw_bar(sense, hum/100*64, (0,60,180))
                elif mode=='pressure': draw_bar(sense, max(0,min(64,(pressure-970)/80*64)), (120,80,180))
                elif mode=='custom':
                    color=parse_color(st.get('sense_color'), (0,170,85)); draw_border(sense,color) if st.get('sense_border_only') else sense.clear(*color)
                elif mode=='border': draw_border(sense, parse_color(st.get('sense_color'), (0,170,85)))
                elif mode=='magic8':
                    if time.time()-last_text>7: text_once(sense, random.choice(['YES','NO','MAYBE','TRAIL SAYS YES','ASK AGAIN','WATCH WEATHER','DRINK WATER']), parse_color(st.get('sense_color'), (80,0,180)), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='water': draw_water_icon(sense, parse_color(st.get('sense_color'), (0,90,220)))
                elif mode=='snake': draw_snake_frame(sense,tick,parse_color(st.get('sense_color'), (0,220,70)))
                if sense_alarm_due(st):
                    draw_water_icon(sense, (0,120,255)); text_once(sense, 'DRINK 8OZ WATER', (0,120,255), sense_scroll_speed(st)); alarm=st.get('hydration_alarm') or {}; alarm['lastFiredAt']=time.time(); st['hydration_alarm']=alarm; write_state(st)
                orient = dict(orient or {}); orient.update({'magnetic_heading': round(float(magnetic_yaw or 0),1), 'north_heading': round(float(yaw or 0),1), 'cardinal': compass_name(yaw)})
                with SENSE_LOCK: SENSE_CACHE.update({'ok': True, 'mode': mode, 'available_modes': SENSE_MODES, 'orientation': orient, 'compass': yaw, 'magnetic_compass': magnetic_yaw, 'compass_cardinal': compass_name(yaw), 'temp': temp_f, 'humidity': hum, 'pressure': pressure, 'gps': gps, 'message': f'{mode} display active', 'updated': time.time()})
            except Exception as e:
                with SENSE_LOCK: SENSE_CACHE.update({'ok': False, 'mode': mode, 'message': f'Sense HAT read/display error: {e}', 'updated': time.time()})
            tick+=1
            if mode == 'liquid':
                time.sleep(0.06)
            elif mode == 'pacman':
                time.sleep(PACMAN_FRAME_SLEEP)
            else:
                time.sleep(0.35 if mode in ('fire','stars','beacon') else 0.75)
    except Exception as e:
        with SENSE_LOCK: SENSE_CACHE.update({'ok': False, 'message': f'Sense HAT unavailable: {e}', 'updated': time.time()})

def joystick_loop():
    while True:
        try:
            link=pathlib.Path('/dev/input/by-path/platform-3f804000.i2c-platform-3f804000.i2c:sensehat@46:joystick-event'); path=str(link.resolve()) if link.exists() else '/dev/input/event0'
            with open(path,'rb') as f:
                flags=fcntl.fcntl(f,fcntl.F_GETFL); fcntl.fcntl(f,fcntl.F_SETFL,flags|os.O_NONBLOCK)
                while True:
                    try:
                        data=f.read(24)
                        if not data or len(data)<24: time.sleep(0.05); continue
                        _sec,_usec,etype,code,value=struct.unpack('llHHI',data)
                        if etype==1 and value==1 and code in KEY_NAMES:
                            direction=KEY_NAMES[code]
                            # Joystick is an input source for games/app controls. Do not auto-cycle
                            # Sense HAT display modes here; explicit app buttons/endpoints own display changes.
                            with SENSE_LOCK:
                                js=dict(SENSE_CACHE.get('joystick') or {})
                                js.update({'seq': int(js.get('seq') or 0)+1,'direction':direction,'pressed':direction=='press','updated':time.time()})
                                SENSE_CACHE['joystick']=js
                                SENSE_CACHE['message']=f'Joystick input: {direction}'
                    except BlockingIOError: time.sleep(0.05)
        except Exception as e:
            with SENSE_LOCK:
                js=dict(SENSE_CACHE.get('joystick') or {}); js.update({'error':str(e),'updated':time.time()}); SENSE_CACHE['joystick']=js
            time.sleep(2)


FIELD_AI_ROOT = pathlib.Path('/var/lib/mappi3/field-ai')
FIELD_AI_DB = FIELD_AI_ROOT / 'field_guide.db'
FIELD_AI_UPLOADS = FIELD_AI_ROOT / 'uploads'
BUILTIN_MODEL_DIR = pathlib.Path('/opt/mappi3/models')
BUILTIN_JSON_MODELS = {
    'cloud-color-prototypes-v1.json': {
        'id':'cloud-color-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Cumulus / bright fair-weather cloud','vector':[0.02,0.25,0.02,0.04,0.45,0.25],'safety':'Cloud observation only; not a forecast.'},
            {'name':'Cumulonimbus / storm cloud caution','vector':[0.01,0.10,0.02,0.42,0.18,0.55],'safety':'Storm cues possible. Watch thunder, wind, pressure; leave exposed ridges/water early.'},
            {'name':'Stratus / overcast layer','vector':[0.02,0.10,0.01,0.18,0.28,0.14],'safety':'Low cloud/overcast observation. Forecast needs more data.'},
            {'name':'Fog / low visibility','vector':[0.02,0.08,0.01,0.10,0.52,0.05],'safety':'Low visibility risk; navigation caution.'}
        ]
    },
    'plant-green-prototypes-v1.json': {
        'id':'plant-green-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Leaf/green plant feature match','vector':[0.45,0.04,0.02,0.18,0.15,0.35],'safety':'Possible plant features only. Do not eat based on this.'},
            {'name':'Bark/woody texture feature match','vector':[0.08,0.03,0.16,0.38,0.08,0.48],'safety':'Tree/bark cue only; need whole tree/leaf/habitat.'},
            {'name':'Flower/bright plant feature match','vector':[0.20,0.08,0.22,0.08,0.35,0.30],'safety':'Flower cue only; confirm all field marks.'}
        ]
    },
    'fungi-color-prototypes-v1.json': {
        'id':'fungi-color-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Orange/yellow mushroom-like color cue','vector':[0.04,0.03,0.32,0.14,0.24,0.36],'safety':'Never consume mushrooms from app/photo ID.'},
            {'name':'Pale mushroom-like color cue','vector':[0.03,0.04,0.04,0.12,0.48,0.28],'safety':'Deadly mushrooms can be pale. Need underside, stem, base, spore print, expert ID.'},
            {'name':'Dark/woodland fungi-like cue','vector':[0.08,0.03,0.08,0.45,0.10,0.42],'safety':'Mushroom/wood texture cue only; do not consume.'}
        ]
    },
    'animal-track-prototypes-v1.json': {
        'id':'animal-track-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Animal/fur/low-light texture cue','vector':[0.10,0.04,0.10,0.42,0.12,0.44],'safety':'Wildlife cue only. Keep distance and verify with tracks/sound/context.'},
            {'name':'Track/scat contrast cue','vector':[0.06,0.03,0.12,0.36,0.18,0.58],'safety':'Track/scat cue only; use scale, stride, habitat, and freshness.'},
            {'name':'Bird/sky silhouette cue','vector':[0.03,0.30,0.02,0.25,0.30,0.50],'safety':'Bird/silhouette cue only; do not disturb nests or wildlife.'}
        ]
    },
    'insect-closeup-prototypes-v1.json': {
        'id':'insect-closeup-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Bug/spider close-up texture cue','vector':[0.12,0.04,0.16,0.35,0.12,0.70],'safety':'Bite/sting risk varies; do not handle unknown bugs/spiders.'},
            {'name':'Tick-like dark small-object cue','vector':[0.04,0.02,0.04,0.55,0.05,0.62],'safety':'If attached tick: remove properly, save/photo, monitor symptoms.'}
        ]
    },
    'rock-mineral-prototypes-v1.json': {
        'id':'rock-mineral-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Gray rock/mineral texture cue','vector':[0.05,0.05,0.04,0.28,0.22,0.50],'safety':'Geology cue only. Do not rely on app for mine/slope/cave safety.'},
            {'name':'Quartz/light mineral cue','vector':[0.02,0.04,0.02,0.08,0.58,0.42],'safety':'Light mineral cue only; verify hardness/streak/context.'},
            {'name':'Iron/orange mineral cue','vector':[0.04,0.03,0.34,0.18,0.18,0.40],'safety':'Oxide/rust cue only; do not taste/ingest minerals.'}
        ]
    },
    'barcode-ocr-prototypes-v1.json': {
        'id':'barcode-ocr-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'High-contrast code/text-like cue','vector':[0.01,0.01,0.01,0.48,0.42,0.80],'safety':'Barcode/OCR cue only until ZXing/Tesseract plugin is installed.'},
            {'name':'Low-contrast label/text cue','vector':[0.02,0.02,0.02,0.22,0.35,0.55],'safety':'Text cue only; verify labels manually.'}
        ]
    },
    'injury-safety-prototypes-v1.json': {
        'id':'injury-safety-prototypes-v1','kind':'safety-router','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Skin/injury image safety router','vector':[0.02,0.02,0.22,0.18,0.26,0.36],'safety':'Do not diagnose from image. Use first aid decision tree and seek care for serious symptoms.'},
            {'name':'Bite/sting/rash safety router','vector':[0.04,0.02,0.18,0.24,0.22,0.42],'safety':'Monitor swelling, breathing, fever, spreading redness; emergency care if severe.'}
        ]
    }
}

def ensure_builtin_models():
    try:
        BUILTIN_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for name, payload in BUILTIN_JSON_MODELS.items():
            p=BUILTIN_MODEL_DIR/name
            if not p.exists(): p.write_text(json.dumps(payload, indent=2))
    except Exception: pass

FIELD_AI_CATEGORIES = [
    {'id':'auto','name':'Identify automatically','model':'router-lite','input':'image','ready':True},
    {'id':'plant','name':'Plant / tree / leaf / flower','model':'mobilenetv3-small-int8-plants-ne-v1.tflite','input':'image','ready':False},
    {'id':'mushroom','name':'Mushroom / fungi','model':'mobilenetv3-small-int8-fungi-ne-v1.tflite','input':'image','ready':False},
    {'id':'animal','name':'Animal / bird / mammal','model':'mobilenetv3-small-int8-fauna-ne-v1.tflite','input':'image','ready':False},
    {'id':'bug','name':'Bug / insect / spider','model':'mobilenetv3-small-int8-insects-ne-v1.tflite','input':'image','ready':False},
    {'id':'track','name':'Animal track / scat','model':'track-router-ne-v1.tflite','input':'image','ready':False},
    {'id':'cloud','name':'Cloud / weather observation','model':'mobilenetv3-small-int8-clouds-v1.tflite','input':'image','ready':False},
    {'id':'injury','name':'Bite, burn, rash, wound, sting','model':'fixed-decision-tree','input':'image+questions','ready':True},
    {'id':'firstaid','name':'First aid decision tree','model':'fixed-reference','input':'questions','ready':True},
    {'id':'survival','name':'Survival guide lookup','model':'sqlite-reference','input':'text','ready':True},
    {'id':'rock','name':'Rock / mineral','model':'future-specialist','input':'image','ready':False},
    {'id':'barcode','name':'Barcode / QR / OCR','model':'future-zxing-tesseract','input':'image','ready':False}
]
FIELD_GUIDE_SEED = [
    ('cattail','Cattail','Typha latifolia','edible wild plants','Wetland plant with flat blade leaves and brown cigar-shaped seed head.','Look for dense wetland stands, flat leaves, brown cylindrical seed head in season.','Wetlands, pond edges, marshes.','Maine/New England wetlands.','Spring shoots; summer/fall seed heads.','Low when correctly identified and from clean water; pollution risk is major.','Edible parts are used only after positive ID and proper preparation.','Yellow iris, other wetland plants, polluted lookalike habitat.','Do not harvest from polluted water or roadside runoff.','If illness after eating wild plants occurs, stop eating and seek medical help.','Survival food only with expert ID; clean water matters.','Photograph whole plant, seed head, leaf base, habitat.','0.82','MapPI3 offline seed guide; verify with local field guide.'),
    ('dandelion','Dandelion','Taraxacum officinale','edible wild plants','Common yellow composite flower with basal toothed leaves and milky sap.','Single yellow flower head, hollow stem, basal rosette, toothed leaves.','Lawns, fields, disturbed soil.','Common in New England.','Spring/fall leaves are less bitter; flowers in warm months.','Generally low when pesticide-free and correctly identified.','Leaves/flowers/roots used as food; avoid treated lawns.','Catsear and other yellow composites; pesticide contamination.','Avoid roadsides and treated lawns.','GI upset possible; seek help for severe reaction.','Useful common plant but not enough calories alone.','Photo flower, leaves, stem, entire plant, surrounding area.','0.78','MapPI3 offline seed guide.'),
    ('poison-ivy','Poison ivy','Toxicodendron radicans','poisonous plants','Plant that can cause severe allergic contact dermatitis.','Leaves of three, variable edge, vine/shrub forms, oily urushiol exposure.','Edges, woods, fields, trailsides.','Common in New England.','All seasons; leafless vines still hazardous.','Contact toxin; burning smoke can injure lungs.','Not edible.','Virginia creeper, boxelder seedlings, brambles.','Do not touch; wash skin/gear; never burn.','Trouble breathing or facial/throat swelling after smoke/exposure is emergency.','Know before brushing through vegetation.','Photo leaf cluster, vine/stem, growth form from distance.','0.70','MapPI3 offline safety guide.'),
    ('water-hemlock','Water hemlock','Cicuta maculata','poisonous plants','Deadly wetland carrot-family plant.','Umbel flowers, wet habitat, compound leaves, chambered root.','Wet meadows, stream banks, marshes.','New England and North America.','Spring through fall.','Extremely poisonous if ingested.','Not edible.','Wild carrot, angelica, elderberry, other umbel plants.','Never sample wild carrot-family roots/stems without expert ID.','Suspected ingestion is emergency; call poison control/EMS.','Avoid unknown wetland umbel plants.','Photo whole plant, leaf, stem, flower, habitat; do not handle bare-handed.','0.60','MapPI3 offline safety guide.'),
    ('amanita-warning','Amanita / deadly mushroom warning','Amanita spp.','mushrooms and fungi','Some Amanita species are deadly and can resemble edible mushrooms.','Look for cap, gills, ring, volva/base, spore color, habitat; many features hidden.','Woods, lawns, near host trees depending species.','New England has dangerous Amanita species.','Summer/fall common.','Potentially deadly.','Never treat as edible from photo ID.','Edible mushrooms can be confused with deadly Amanita/Galerina/Lepiota.','MapPI3 never certifies mushrooms safe to eat.','Suspected mushroom poisoning: save specimen/photos and seek emergency/poison control help.','Photo top, underside, full stem, base/volva, nearby trees, bruising.','Need multiple photos and expert ID.','0.95','MapPI3 mushroom safety rule.'),
    ('black-bear','Black bear','Ursus americanus','mammals','Large omnivore; usually avoids humans but food-conditioned bears are dangerous.','Large body, rounded ears, tracks with five toes/claws.','Forests, mountains, campsites.','Maine/New England.','Active spring-fall; denning winter.','Danger if surprised, cubs nearby, or food-conditioned.','Not applicable.','Large dog/coyote tracks can confuse track photos.','Do not approach; secure food; back away calmly.','Attack/injury requires emergency care.','Make noise, keep dog controlled, store food properly.','Photo tracks with scale, scat, or distant animal only.','0.75','MapPI3 wildlife safety seed.'),
    ('tick-warning','Tick / small arthropod caution','Ixodida / field arthropod cue','insects and spiders','Small dark arthropod reference for bug/spider/tick routing and bite-prevention reminders.','Tiny dark oval body, legs close to body, often found on clothing, skin, pets, grass, or leaf litter.','Tall grass, brush, leaf litter, animal trails, campsites.','Common in New England.','Spring through fall; active during mild weather.','Bite/vector risk varies; do not handle unknown bugs bare-handed.','Not edible.','Small beetles, seeds, dirt specks, spiders, other arthropods.','Use tweezers for attached ticks, clean skin, save/photo specimen if symptoms occur.','Seek medical guidance for fever, expanding rash, severe reaction, or embedded mouthparts concern.','Use as a caution cue only; verify with scale and clear close-up.','Close focused top photo, scale reference, body/leg view, where it was found.','0.55','MapPI3 offline arthropod safety seed.'),
    ('track-reference','Animal track / scat field cue','Track/scat reference','animal tracks and scat','Reference record for track/scat routing when the app sees ground marks rather than the animal.','Look for print shape, toe count, claw marks, stride, trail pattern, scat size, and scale.','Mud, snow, sand, trail edges, stream banks, campsites.','Universal field cue.','Any season; snow/mud preserve tracks best.','Wildlife proximity risk; scat can carry pathogens.','Not applicable.','Dog/coyote/fox/bobcat/bear/deer tracks overlap without scale and gait context.','Do not touch scat bare-handed; keep distance from fresh signs, dens, carcasses, or cubs.','Bites/scratches require real first aid; possible rabies exposure needs urgent care.','Use scale, stride, habitat, and freshness before guessing species.','Photo track with ruler/boot/coin scale, trail pattern, nearby scat, habitat context.','0.50','MapPI3 offline track safety seed.'),
    ('survival-priorities','Survival priorities checklist','Fixed offline reference','survival guide','A fixed reminder for field priorities when offline, lost, injured, cold, overheated, or low on supplies.','Stop, breathe, assess hazards, tell someone your plan if possible, mark location, preserve battery, water, shelter, warmth, signaling, navigation.','Any field setting.','Universal.','Any time.','Risk depends on exposure, injury, weather, water, and navigation state.','Not applicable.','Panic, bad shortcuts, unsafe water, exposure, delayed emergency call.','Do not rely on MapPI3 as your only navigation/emergency tool.','Call emergency services/use beacon when life safety is in question.','Prioritize immediate safety over app interaction.','No photo required; record location, conditions, injury, water/shelter/battery state.','1.0','MapPI3 curated survival reference.'),
    ('cumulonimbus','Cumulonimbus cloud','Cumulonimbus','clouds','Tall thunderstorm cloud associated with lightning, heavy rain, hail, gusts.','Vertical tower/anvil shape, dark base, rapid growth.','Sky observation.','Global.','Warm season common; can occur any storm season.','Weather hazard: lightning/wind/heavy rain.','Not applicable.','Cumulus congestus, dark stratus.','Cloud photo alone is not a forecast; leave ridges/open water if thunder/lightning risk.','Lightning injury/burn/shock are emergencies.','Watch sky, pressure, wind, thunder; seek shelter early.','Wide sky photo and horizon context.','0.70','MapPI3 cloud safety guide.'),
    ('granite-reference','Granite / light igneous rock cue','Granite','rocks and minerals','Coarse-grained light igneous rock reference for offline geology comparisons.','Look for interlocking light/dark crystals, quartz/feldspar/mica speckles, hardness, and outcrop context.','Outcrops, glacial erratics, trail cuts, old stone walls.','Common in New England bedrock/erratics.','Any season.','Low handling risk; rockfall, cliffs, mines, and sharp fragments are the real hazards.','Not edible.','Gneiss, quartzite, concrete, other speckled rocks.','Do not hammer near eyes; avoid unstable slopes, quarries, caves, and mine openings.','Eye injury/cut/fall requires real first aid or emergency care.','Use as a safe geology cue only; verify hardness, streak, grain, and geologic map context.','Photo fresh surface, weathered surface, scale, surrounding outcrop.','0.45','MapPI3 offline geology seed.'),
    ('code-label-reference','Barcode / QR / label text cue','Machine-readable label','barcode and ocr','High-contrast printed codes or label text that may be scanned later by a ZXing/Tesseract plugin.','Look for square QR finder marks, parallel barcode stripes, printed characters, and clear focus.','Packages, trail signs, gear labels, permits, maps.','Universal.','Any time.','Low; scanning labels can reveal private data, so avoid sharing sensitive codes publicly.','Not applicable.','Decorative stripes, low-contrast text, damaged labels, reflections.','Do not publish private IDs, tickets, addresses, medical info, or account codes.','Not a medical/safety classifier.','Use for offline note capture and future OCR/barcode plugin routing.','Take a straight-on, well-lit, focused photo; include full code borders.','0.50','MapPI3 offline barcode/OCR seed.'),
    ('first-aid-red-flags','Emergency warning signs','Fixed decision tree','first aid','Red flags requiring urgent care or emergency services.','Trouble breathing, facial/throat swelling, confusion, fainting, uncontrolled bleeding, severe burns, rapidly spreading redness, venomous snakebite, shock, severe allergic reaction.','Any field setting.','Universal.','Any time.','High danger.','Not applicable.','Mild symptoms can worsen; do not delay for app analysis.','Call emergency services/use real first-aid training; app is reference only.','Emergency warning signs require immediate help.','Use as fixed offline checklist.','No photo required; answer safety questions first.','1.0','Curated MapPI3 first-aid red flags.')
]

def field_ai_db():
    FIELD_AI_ROOT.mkdir(parents=True, exist_ok=True); FIELD_AI_UPLOADS.mkdir(parents=True, exist_ok=True)
    conn=sqlite3.connect(str(FIELD_AI_DB)); conn.row_factory=sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS species (id TEXT PRIMARY KEY, common_name TEXT, scientific_name TEXT, category TEXT, description TEXT, identification_features TEXT, habitat TEXT, geographic_range TEXT, seasonal_information TEXT, toxicity TEXT, edibility TEXT, dangerous_lookalikes TEXT, handling_warnings TEXT, first_aid_instructions TEXT, survival_notes TEXT, additional_photo_requirements TEXT, confidence_threshold REAL, source TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, created_at REAL, category TEXT, image_path TEXT, result_json TEXT, notes TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS corrections (id TEXT PRIMARY KEY, created_at REAL, observation_id TEXT, category TEXT, ai_guess TEXT, correction TEXT, evidence TEXT, source TEXT, votes INTEGER DEFAULT 0, public INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS plugins (id TEXT PRIMARY KEY, kind TEXT, label TEXT, path TEXT, enabled INTEGER, config_json TEXT)''')
    for row in FIELD_GUIDE_SEED:
        conn.execute('INSERT OR IGNORE INTO species VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', row)
    for cat in FIELD_AI_CATEGORIES:
        conn.execute('INSERT OR IGNORE INTO plugins VALUES (?,?,?,?,?,?)', (cat['id'], 'model' if cat.get('input')!='questions' else 'reference', cat['name'], '/opt/mappi3/models/'+cat['model'], 1 if cat['ready'] else 0, json.dumps(cat)))
    conn.commit(); return conn

PROTOTYPE_MODEL_BY_CATEGORY = {
    'auto':'plant-green-prototypes-v1.json','plant':'plant-green-prototypes-v1.json','mushroom':'fungi-color-prototypes-v1.json',
    'animal':'animal-track-prototypes-v1.json','track':'animal-track-prototypes-v1.json','bug':'insect-closeup-prototypes-v1.json',
    'cloud':'cloud-color-prototypes-v1.json','rock':'rock-mineral-prototypes-v1.json','barcode':'barcode-ocr-prototypes-v1.json',
    'ocr':'barcode-ocr-prototypes-v1.json','injury':'injury-safety-prototypes-v1.json'
}
SPECIALIST_MODEL_EXTENSIONS = ('.tflite','.onnx','.ncnn','.bin','.param','.onnxruntime')
SPECIALIST_BACKEND_BY_CATEGORY = {
    'barcode':['pyzbar','zbarimg','tesseract'],
    'ocr':['tesseract','pytesseract'],
    'plant':['tflite-runtime','onnxruntime'],
    'mushroom':['tflite-runtime','onnxruntime'],
    'animal':['tflite-runtime','onnxruntime'],
    'bug':['tflite-runtime','onnxruntime'],
    'track':['tflite-runtime','onnxruntime'],
    'cloud':['tflite-runtime','onnxruntime'],
    'rock':['tflite-runtime','onnxruntime']
}

def import_available(module):
    try:
        __import__(module); return True
    except Exception: return False

def field_ai_backend_status():
    py={'PIL': import_available('PIL'), 'numpy': import_available('numpy'), 'onnxruntime': import_available('onnxruntime'), 'tflite_runtime': import_available('tflite_runtime'), 'pyzbar': import_available('pyzbar'), 'pytesseract': import_available('pytesseract')}
    bins={name: bool(sh(f'command -v {name}', timeout=2).get('ok')) for name in ['tesseract','zbarimg']}
    ready={
        'barcode': py.get('pyzbar') or bins.get('zbarimg') or bins.get('tesseract'),
        'ocr': py.get('pytesseract') or bins.get('tesseract'),
        'image_classifiers': py.get('onnxruntime') or py.get('tflite_runtime'),
        'pillow_features': py.get('PIL')
    }
    return {'python_modules': py, 'binaries': bins, 'ready': ready, 'policy':'Barcode/OCR backends can run real local decoding when zbar/pyzbar/tesseract are installed. Plant/fungi/animal/cloud/rock still need vetted model files before authoritative recognition.'}

def category_specialist_ready(category, specialist_installed=None, backends=None):
    specialist_installed=specialist_installed or []
    backends=backends or field_ai_backend_status()
    if category in ('firstaid','survival','injury'): return True
    if category in ('barcode','ocr'): return bool(backends.get('ready',{}).get('barcode') or backends.get('ready',{}).get('ocr'))
    wanted=str(next((c.get('model') for c in FIELD_AI_CATEGORIES if c.get('id')==category), '')).lower()
    return any((category in name.lower()) or (wanted and pathlib.Path(wanted).name.lower()==name.lower()) for name in specialist_installed)

def field_ai_categories():
    conn=field_ai_db(); rows=[dict(r) for r in conn.execute('SELECT * FROM plugins ORDER BY label')]; conn.close()
    backends=field_ai_backend_status()
    installed=[]
    if BUILTIN_MODEL_DIR.exists(): installed=sorted([p.name for p in BUILTIN_MODEL_DIR.glob('*') if p.is_file()])
    specialist_installed=[name for name in installed if pathlib.Path(name).suffix.lower() in SPECIALIST_MODEL_EXTENSIONS]
    enriched=[]
    for cat in FIELD_AI_CATEGORIES:
        item=dict(cat); proto=PROTOTYPE_MODEL_BY_CATEGORY.get(item['id'])
        item['prototype_model']=proto
        item['prototype_ready']=bool(proto) or item['id'] in ('firstaid','survival')
        item['specialist_ready']=category_specialist_ready(item['id'], specialist_installed, backends)
        item['capability']='specialist-backend' if item['specialist_ready'] and item['id'] in ('barcode','ocr') else ('prototype-cue' if proto else ('fixed-reference' if item['id'] in ('firstaid','survival','injury') else 'future-specialist'))
        item['backend_candidates']=SPECIALIST_BACKEND_BY_CATEGORY.get(item['id'], [])
        enriched.append(item)
    return {'ok': True, 'categories': enriched, 'plugins': rows, 'offline': True, 'backend_status': backends, 'capability_tier': 'safe offline prototype cues + real barcode/OCR backend hooks where installed', 'model_policy': 'Prototype JSON cue models are bundled for routing/fallbacks. Barcode/OCR can use real local zbar/tesseract backends when installed. Plant/fungi/animal/cloud/rock specialist TFLite/ONNX/NCNN files must be added and verified separately.'}

def field_ai_status():
    ensure_builtin_models(); conn=field_ai_db(); species=conn.execute('SELECT COUNT(*) c FROM species').fetchone()['c']; obs=conn.execute('SELECT COUNT(*) c FROM observations').fetchone()['c']; corrections=conn.execute('SELECT COUNT(*) c FROM corrections').fetchone()['c']; plugins=[dict(r) for r in conn.execute('SELECT * FROM plugins ORDER BY id')]; conn.close()
    model_dir=BUILTIN_MODEL_DIR
    installed=[]
    if model_dir.exists(): installed=sorted([p.name for p in model_dir.glob('*') if p.is_file()])
    prototype_expected=sorted(set(BUILTIN_JSON_MODELS.keys()))
    prototype_installed=[name for name in prototype_expected if name in installed]
    specialist_installed=[name for name in installed if pathlib.Path(name).suffix.lower() in SPECIALIST_MODEL_EXTENSIONS]
    specialist_expected=[c['model'] for c in FIELD_AI_CATEGORIES if str(c.get('model','')).endswith(('.tflite','.onnx','.ncnn')) or str(c.get('model','')).startswith('future-')]
    backend_status=field_ai_backend_status()
    backend_categories_ready=[cat for cat in SPECIALIST_BACKEND_BY_CATEGORY if category_specialist_ready(cat, specialist_installed, backend_status)]
    return {'ok': True, 'offline': True, 'database': str(FIELD_AI_DB), 'species_records': species, 'observations': obs, 'corrections': corrections, 'model_dir': str(model_dir), 'installed_models': installed, 'installed_prototype_models': prototype_installed, 'expected_prototype_models': prototype_expected, 'missing_prototype_models': [name for name in prototype_expected if name not in prototype_installed], 'installed_specialist_models': specialist_installed, 'installed_specialist_backends': backend_categories_ready, 'specialist_backend_status': backend_status, 'expected_future_specialist_models': specialist_expected, 'specialist_models_ready': bool(specialist_installed or backend_categories_ready), 'capability_tier': 'prototype-cue-pack + backend hooks' if prototype_installed else 'curated-reference-fallback', 'plugins': plugins, 'model_policy': 'Current offline AI has prototype JSON cue matching, curated field-guide fallback, and real local barcode/OCR hooks when zbar/tesseract/pyzbar/pytesseract are installed. It is not authoritative species, medical, weather, or geology recognition until vetted specialist models/backends are installed and live-verified.', 'memory_policy': 'Zero 2 W: one model loaded at a time; image resize target 224/320; prefer small INT8/TFLite/ONNX; avoid PyTorch on Pi'}

def _species_by_category(conn, category):
    if category=='auto':
        rows=conn.execute('SELECT * FROM species LIMIT 8').fetchall()
    elif category=='survival':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%survival%' LIMIT 8").fetchall()
    elif category=='plant':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%plant%' OR category LIKE '%tree%' OR category LIKE '%edible%' LIMIT 8").fetchall()
    elif category=='mushroom':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%mushroom%' OR category LIKE '%fungi%' LIMIT 8").fetchall()
    elif category=='animal':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%mammal%' OR category LIKE '%animal%' LIMIT 8").fetchall()
    elif category=='bug':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%insect%' OR category LIKE '%spider%' OR category LIKE '%arthropod%' LIMIT 8").fetchall()
    elif category=='track':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%track%' OR category LIKE '%scat%' LIMIT 8").fetchall()
    elif category=='cloud':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%cloud%' LIMIT 8").fetchall()
    elif category=='rock':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%rock%' OR category LIKE '%mineral%' LIMIT 8").fetchall()
    elif category in ('barcode','ocr'):
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%barcode%' OR category LIKE '%ocr%' LIMIT 8").fetchall()
    elif category in ('injury','firstaid'):
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%first aid%' LIMIT 8").fetchall()
    else:
        rows=conn.execute('SELECT * FROM species LIMIT 8').fetchall()
    return [dict(r) for r in rows]


def basic_image_model(image_path, category):
    try:
        from PIL import Image, ImageStat, ImageFilter
        img=Image.open(image_path).convert('RGB'); w,h=img.size
        thumb=img.resize((96,96)); stat=ImageStat.Stat(thumb); mean=stat.mean
        gray=thumb.convert('L'); edges=gray.filter(ImageFilter.FIND_EDGES); edge_mean=ImageStat.Stat(edges).mean[0]
        pixels=list(thumb.getdata()); total=len(pixels)
        green=sum(1 for r,g,b in pixels if g>r*1.08 and g>b*1.08 and g>55)/total
        blue=sum(1 for r,g,b in pixels if b>r*1.05 and b>g*.95 and b>70)/total
        orange=sum(1 for r,g,b in pixels if r>120 and g>70 and b<90)/total
        dark=sum(1 for r,g,b in pixels if r+g+b<120)/total
        bright=sum(1 for r,g,b in pixels if r+g+b>610)/total
        cloud_guess='Cumulus' if bright>0.22 and blue>0.18 else ('Cumulonimbus / storm cloud caution' if dark>0.35 and edge_mean>18 else ('Fog/stratus' if edge_mean<10 and bright>0.12 else 'Cloud observation'))
        if category=='cloud':
            return {'engine':'pillow-feature-model-v0','features':{'mean_rgb':[round(x,1) for x in mean],'green_ratio':round(green,3),'blue_ratio':round(blue,3),'orange_ratio':round(orange,3),'dark_ratio':round(dark,3),'bright_ratio':round(bright,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':cloud_guess,'confidence':58 if 'Cumul' in cloud_guess else 45}
        if category in ('plant','auto') and green>0.18:
            return {'engine':'pillow-feature-model-v0','features':{'green_ratio':round(green,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':'Plant/leaf-like image features detected','confidence':52}
        if category=='mushroom' and (orange>0.08 or bright>0.2):
            return {'engine':'pillow-feature-model-v0','features':{'orange_ratio':round(orange,3),'bright_ratio':round(bright,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':'Mushroom-like color/shape cue possible; safety fallback required','confidence':38}
        return {'engine':'pillow-feature-model-v0','features':{'mean_rgb':[round(x,1) for x in mean],'green_ratio':round(green,3),'blue_ratio':round(blue,3),'dark_ratio':round(dark,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':'No specialist match; use reference fallback','confidence':30}
    except Exception as e:
        return {'engine':'unavailable','error':str(e),'guess':'Image stored; install Pillow/TFLite model for feature inference','confidence':0}


def decode_barcode_or_ocr(image_path, category='barcode'):
    result={'engine':'none','available':False,'decoded':[], 'text':'', 'notes':[]}
    if not image_path or not pathlib.Path(image_path).exists(): return result
    try:
        from PIL import Image
        img=Image.open(image_path)
    except Exception as e:
        result['notes'].append('Pillow image open failed: '+str(e)); img=None
    if img is not None:
        try:
            from pyzbar.pyzbar import decode as zbar_decode
            decoded=[]
            for item in zbar_decode(img):
                raw=item.data.decode('utf-8','replace') if getattr(item,'data',None) else ''
                decoded.append({'type': str(getattr(item,'type','barcode')), 'data': raw[:500]})
            if decoded:
                result.update({'engine':'pyzbar', 'available':True, 'decoded':decoded, 'text':'\n'.join(d['data'] for d in decoded)})
                return result
            result['available']=True; result['notes'].append('pyzbar available but no barcode decoded')
        except Exception as e:
            result['notes'].append('pyzbar unavailable/failed: '+str(e)[:160])
    if shutil.which('zbarimg'):
        out=sh('zbarimg --quiet --raw '+json.dumps(str(image_path)), timeout=12)
        if out.get('ok') and out.get('output','').strip():
            lines=[line.strip() for line in out.get('output','').splitlines() if line.strip()]
            result.update({'engine':'zbarimg', 'available':True, 'decoded':[{'type':'barcode','data':line[:500]} for line in lines], 'text':'\n'.join(lines)[:1500]})
            return result
        result['available']=True; result['notes'].append('zbarimg available but no barcode decoded')
    if category in ('ocr','barcode'):
        try:
            if img is not None:
                import pytesseract
                text=(pytesseract.image_to_string(img) or '').strip()
                result['available']=True
                if text:
                    result.update({'engine':'pytesseract', 'text':text[:2000], 'decoded':[{'type':'ocr','data':text[:500]}]})
                    return result
                result['notes'].append('pytesseract available but no text recognized')
        except Exception as e:
            result['notes'].append('pytesseract unavailable/failed: '+str(e)[:160])
        if shutil.which('tesseract'):
            out=sh('tesseract '+json.dumps(str(image_path))+' stdout --psm 6 2>/dev/null', timeout=15)
            result['available']=True
            text=(out.get('output') or '').strip()
            if text:
                result.update({'engine':'tesseract-cli', 'text':text[:2000], 'decoded':[{'type':'ocr','data':text[:500]}]})
                return result
            result['notes'].append('tesseract available but no text recognized')
    return result

def prototype_model_match(category, vision):
    ensure_builtin_models()
    name=PROTOTYPE_MODEL_BY_CATEGORY.get(category)
    if not name or not vision or not isinstance(vision.get('features'), dict): return None
    try:
        model=json.loads((BUILTIN_MODEL_DIR/name).read_text())
        f=vision.get('features') or {}; vec=[float(f.get('green_ratio') or 0), float(f.get('blue_ratio') or 0), float(f.get('orange_ratio') or 0), float(f.get('dark_ratio') or 0), float(f.get('bright_ratio') or 0), min(1.0, float(f.get('edge_mean') or 0)/60.0)]
        best=None
        for label in model.get('labels',[]):
            lv=[float(x) for x in label.get('vector',[])]
            d=sum((a-b)**2 for a,b in zip(vec,lv))**0.5
            score=max(12, min(82, round(82 - d*95)))
            item={**label,'distance':round(d,4),'confidence':score,'model_id':model.get('id'),'features':model.get('features')}
            if best is None or item['confidence']>best['confidence']: best=item
        return best
    except Exception as e:
        return {'name':'Prototype model unavailable','confidence':0,'error':str(e)}

def field_ai_analyze(payload):
    category=str(payload.get('category') or 'auto').lower(); notes=str(payload.get('notes') or '')[:500]
    image_data=payload.get('image') or ''
    image_path=''
    image_info={'received': False}
    if image_data:
        if ',' in image_data: image_data=image_data.split(',',1)[1]
        raw=base64.b64decode(image_data + '='*((4-len(image_data)%4)%4), validate=False)
        if len(raw) > 7_000_000: return {'ok': False, 'error': 'Image too large. Use a smaller photo under ~7 MB.'}
        obs_id='obs-'+uuid.uuid4().hex[:12]
        image_path=str(FIELD_AI_UPLOADS/(obs_id+'.jpg'))
        FIELD_AI_UPLOADS.mkdir(parents=True, exist_ok=True); pathlib.Path(image_path).write_bytes(raw)
        image_info={'received': True, 'bytes': len(raw), 'stored': image_path, 'resize_target': '224x224 or 320x320 when specialist model is installed'}
    else:
        obs_id='obs-'+uuid.uuid4().hex[:12]
    conn=field_ai_db(); candidates=_species_by_category(conn, category)
    vision = basic_image_model(image_path, category) if image_path else {'engine':'none','guess':'No image supplied','confidence':0}
    prototype = prototype_model_match(category, vision) if image_path else None
    specialist_backend = decode_barcode_or_ocr(image_path, category) if image_path and category in ('barcode','ocr') else None
    primary=candidates[0] if candidates else {}
    model_ready=category_specialist_ready(category) or any(c['id']==category and c.get('ready') for c in FIELD_AI_CATEGORIES)
    confidence=42 if category not in ('injury','firstaid','survival') else 100
    if category=='mushroom': confidence=36
    if specialist_backend and specialist_backend.get('decoded'):
        confidence=88
        primary={**primary, 'id':'decoded-code-or-text', 'common_name':'Decoded barcode/OCR text', 'scientific_name':'local zbar/tesseract backend', 'identification_features':'Real local barcode/OCR backend returned decoded data; review privately before sharing.', 'dangerous_lookalikes':'Damaged labels, reflections, partial codes, private IDs.', 'additional_photo_requirements':'Straight-on full code/label photo with borders visible.'}
    alternatives=[{'id':c['id'],'name':c['common_name'],'confidence':max(5, confidence-(i+1)*9),'category':c['category']} for i,c in enumerate(candidates[1:4])]
    warnings=['Possible identification only. Do not consume any wild plant or mushroom based only on this result.','Specialist species model files are not installed yet; this response uses the safe reference/database fallback unless a barcode/OCR backend returned decoded text.']
    if category in ('injury','firstaid'):
        warnings=['This app cannot diagnose bites, burns, rashes, wounds, infections, poisoning, or allergic reactions from an image.','Emergency signs: trouble breathing, facial/throat swelling, confusion, fainting, uncontrolled bleeding, severe burns, rapidly spreading redness, suspected venomous bite, shock, severe allergic reaction.']
    if category=='cloud': warnings=['Cloud photo only: not a reliable forecast. Use pressure, wind, radar/weather source when available, and leave exposed areas early if thunder/lightning threatens.']
    result={'ok': True,'observation_id': obs_id,'category': category,'router': {'selected_category': category, 'model_ready': model_ready, 'plugin': next((c for c in FIELD_AI_CATEGORIES if c['id']==category), FIELD_AI_CATEGORIES[0])},'image': image_info,'possible_identification': {'id': primary.get('id','reference'), 'name': primary.get('common_name','Offline reference guidance'), 'scientific_name': primary.get('scientific_name',''), 'confidence': confidence, 'confirmed': False},'alternatives': alternatives,'vision_model': vision, 'prototype_model': prototype, 'specialist_backend': specialist_backend, 'visible_features': [f"Local image model: {vision.get('guess')} ({vision.get('engine')})", (f"Specialist backend: {specialist_backend.get('engine')} decoded {len(specialist_backend.get('decoded') or [])} item(s)" if specialist_backend and specialist_backend.get('decoded') else ''), primary.get('identification_features','Collect multiple angles and habitat context.') if primary else 'Collect additional photos.'],'dangerous_lookalikes': primary.get('dangerous_lookalikes','Unknown lookalikes require expert/local confirmation.') if primary else 'Unknown','safety_warnings': warnings,'additional_photos_requested': (primary.get('additional_photo_requirements') if primary else 'Top, underside, stem/base, whole organism, habitat, scale reference.'),'recommended_next_steps': ['Take 2-4 more photos from different angles with scale/context.','Compare against offline field-guide record and dangerous lookalikes.','Prototype JSON models are active now; install/enable specialist INT8/TFLite/ONNX/OCR backend next for stronger inference.'],'field_guide': primary,'offline_reference_matches': candidates[:5],'history_saved': True,'limitations': 'This is an offline-first plugin scaffold and safety/reference fallback. Barcode/OCR can use real local backends when installed; species/geology/weather recognition needs vetted model files.'}
    conn.execute('INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?)', (obs_id, time.time(), category, image_path, json.dumps(result), notes)); conn.commit(); conn.close()
    return result

def field_ai_history():
    conn=field_ai_db(); rows=[dict(r) for r in conn.execute('SELECT id, created_at, category, image_path, notes FROM observations ORDER BY created_at DESC LIMIT 50')]; conn.close(); return {'ok': True, 'history': rows}

def field_ai_corrections():
    conn=field_ai_db(); rows=[dict(r) for r in conn.execute('SELECT * FROM corrections ORDER BY votes DESC, created_at DESC LIMIT 100')]; conn.close(); return {'ok': True, 'corrections': rows, 'policy': 'Local first. Public/wiki sync later should require source/evidence, votes, and review flags.'}

def field_ai_add_correction(payload):
    conn=field_ai_db(); cid='corr-'+uuid.uuid4().hex[:12]
    row=(cid,time.time(),str(payload.get('observation_id') or '')[:80],str(payload.get('category') or 'unknown')[:40],str(payload.get('ai_guess') or '')[:200],str(payload.get('correction') or '')[:1000],str(payload.get('evidence') or '')[:1000],str(payload.get('source') or 'local user note')[:200],0,1 if payload.get('public') else 0)
    conn.execute('INSERT INTO corrections VALUES (?,?,?,?,?,?,?,?,?,?)', row); conn.commit(); conn.close()
    return {'ok': True, 'correction_id': cid, 'message': 'Correction saved locally; future public sync can publish it as a fact-check note.'}

def field_ai_vote_correction(payload):
    cid=str(payload.get('id') or '')[:80]; delta=1 if int(payload.get('delta') or 0)>0 else -1
    conn=field_ai_db(); conn.execute('UPDATE corrections SET votes=COALESCE(votes,0)+? WHERE id=?', (delta,cid)); conn.commit(); conn.close()
    return field_ai_corrections()

def field_ai_clear_history():
    conn=field_ai_db(); conn.execute('DELETE FROM observations'); conn.commit(); conn.close(); return {'ok': True, 'message': 'Field AI observation history cleared.'}

def status():
    gps=gps_status(); sense=sense_snapshot(); ip=sh('hostname -I || true',timeout=5)['output'].strip(); w=wifi_info(); mode='hotspot' if w['hotspot_active'] else ('home-wifi' if w['home_wifi_ssid'] else 'local-pi')
    sense_text=sense.get('message') or ('sense-hat ok' if sense.get('ok') else 'sense-hat unavailable')
    if sense.get('ok') and sense.get('orientation'):
        o=sense.get('orientation') or {}; sense_text='sense-hat ok roll={:.1f} pitch={:.1f} yaw={:.1f} mode={}'.format(o.get('roll',0),o.get('pitch',0),o.get('yaw',0),sense.get('mode','compass'))
    return {'ok': True, 'host': socket.gethostname(), 'port': PORT, 'https': https_status(), 'ip': ip, 'connection_mode': mode, **w, 'gps_device': gps.get('device'), 'gps': gps, 'sense_hat': sense_text, 'sense': sense, 'system': system_stats(), 'state': read_state(), 'time': time.time()}

def _nmcli_lines(args, timeout=5):
    out = sh('nmcli -t ' + args + ' 2>/dev/null || true', timeout=timeout).get('output','')
    return [line for line in out.splitlines() if line.strip()]

def _systemd_state(service):
    active = sh(f'systemctl is-active {shlex.quote(service)} 2>/dev/null || true', timeout=4).get('output','').strip() or 'unknown'
    enabled = sh(f'systemctl is-enabled {shlex.quote(service)} 2>/dev/null || true', timeout=4).get('output','').strip() or 'unknown'
    return {'service': service, 'active': active, 'enabled': enabled}

def _ssh_status():
    names = ['ssh.service', 'sshd.service']
    states = [_systemd_state(name) for name in names]
    listeners = sh("ss -lntp 2>/dev/null | grep -E ':(22)\\s' || true", timeout=4).get('output','').strip()
    return {'ok': any(s.get('active') == 'active' for s in states) and bool(listeners), 'services': states, 'listening': bool(listeners), 'listeners': listeners[-1000:]}


def _safe_connection_name(ssid, label=None):
    base = ''.join(ch if ch.isalnum() or ch in ('-','_','.') else '-' for ch in str(label or ssid or 'wifi'))
    base = '-'.join([x for x in base.split('-') if x])[:48] or 'wifi'
    if not base.startswith('MapPI3-'):
        base = 'MapPI3-' + base
    return base[:64]

def wifi_scan(payload=None):
    payload = payload or {}
    if not pathlib.Path('/usr/bin/nmcli').exists():
        return {'ok': False, 'error': 'nmcli/NetworkManager not installed', 'networks': [], 'saved_wifi': []}
    if payload.get('rescan', True):
        sh('nmcli radio wifi on; rfkill unblock wifi || true; nmcli device wifi rescan ifname wlan0 2>/dev/null || nmcli device wifi rescan || true', timeout=15)
    raw = _nmcli_lines('-f IN-USE,SSID,SECURITY,SIGNAL,FREQ,BARS device wifi list --rescan no', timeout=8)
    networks = []
    seen = set()
    for line in raw:
        parts = line.split(':')
        if len(parts) < 6: continue
        in_use, ssid, security, signal, freq, bars = parts[0], parts[1], parts[2], parts[3], parts[4], ':'.join(parts[5:])
        ssid = ssid.strip()
        if not ssid or ssid in seen: continue
        seen.add(ssid)
        try: sig = int(signal or 0)
        except Exception: sig = 0
        networks.append({'ssid': ssid, 'in_use': in_use.strip() == '*', 'security': security or 'open', 'signal': sig, 'freq': freq, 'bars': bars, 'saved': False})
    saved = _wifi_saved_connections()
    saved_names = {item.get('name') for item in saved}
    saved_ssids = {item.get('ssid') for item in saved}
    for item in networks:
        item['saved'] = item['ssid'] in saved_ssids or _safe_connection_name(item['ssid']) in saved_names
    networks.sort(key=lambda n: (not n.get('in_use'), -int(n.get('signal') or 0), n.get('ssid','').lower()))
    return {'ok': True, 'networks': networks[:60], 'saved_wifi': saved, 'time': time.time()}

def wifi_save_network(payload=None):
    payload = payload or {}
    ssid = str(payload.get('ssid') or '').strip()
    password = str(payload.get('password') or '')
    label = str(payload.get('label') or ssid).strip()
    autoconnect = bool(payload.get('autoconnect', True))
    if not ssid: return {'ok': False, 'error': 'SSID is required'}
    if not pathlib.Path('/usr/bin/nmcli').exists():
        return {'ok': False, 'error': 'nmcli/NetworkManager not installed; cannot save Wi-Fi credentials on this image yet'}
    name = _safe_connection_name(ssid, label)
    priority = int(payload.get('priority') or 650)
    cmd = 'set -u; nmcli radio wifi on; rfkill unblock wifi || true; '
    cmd += 'nmcli connection delete ' + shlex.quote(name) + ' >/dev/null 2>&1 || true; '
    cmd += 'nmcli connection add type wifi ifname wlan0 con-name ' + shlex.quote(name) + ' ssid ' + shlex.quote(ssid) + '; '
    cmd += 'nmcli connection modify ' + shlex.quote(name) + ' connection.autoconnect ' + ('yes' if autoconnect else 'no') + ' connection.autoconnect-priority ' + shlex.quote(str(priority)) + ' ipv4.method auto; '
    if password:
        cmd += 'nmcli connection modify ' + shlex.quote(name) + ' wifi-sec.key-mgmt wpa-psk wifi-sec.psk ' + shlex.quote(password) + '; '
    else:
        cmd += 'nmcli connection modify ' + shlex.quote(name) + ' wifi-sec.key-mgmt none; '
    out = sh(cmd, timeout=30)
    st = read_state(); st.setdefault('saved_wifi_profiles', {})[name] = {'ssid': ssid, 'label': label or ssid, 'saved_at': time.time(), 'has_password': bool(password), 'autoconnect': autoconnect}; write_state(st)
    saved = _wifi_saved_connections()
    return {'ok': out.get('ok'), 'message': f'Saved Wi-Fi profile {name} for SSID {ssid}. Password is stored only in NetworkManager on the Pi and is never returned by the API.', 'name': name, 'ssid': ssid, 'has_password': bool(password), 'output': '[REDACTED]', 'saved_wifi': saved}

def _wifi_saved_connections():
    saved_raw = _nmcli_lines('-f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show')
    state_profiles = (read_state().get('saved_wifi_profiles') or {})
    saved = []
    for line in saved_raw:
        parts = line.split(':')
        if len(parts) >= 4 and parts[1] in ('802-11-wireless','wifi'):
            name = parts[0]
            meta = state_profiles.get(name, {}) if isinstance(state_profiles, dict) else {}
            ssid = meta.get('ssid') or sh('nmcli -g 802-11-wireless.ssid connection show ' + shlex.quote(name) + ' 2>/dev/null || true', timeout=4).get('output','').strip()
            saved.append({'name': name, 'ssid': ssid or name.replace('MapPI3-','',1), 'label': meta.get('label') or ssid or name, 'type': parts[1], 'autoconnect': parts[2], 'priority': parts[3], 'has_password': bool(meta.get('has_password', True)), 'secret': '[REDACTED]'})
    return saved

def network_status(payload=None):
    active = _nmcli_lines('-f NAME,TYPE,DEVICE connection show --active')
    devices = _nmcli_lines('-f DEVICE,TYPE,STATE,CONNECTION device')
    route = sh('ip route | sed -n "1,20p"', timeout=4).get('output','')
    ts = tailscale_status()
    ssh = _ssh_status()
    return {'ok': True, 'wifi': wifi_info(), 'active_connections': active, 'saved_wifi': _wifi_saved_connections(), 'devices': devices, 'has_default_route': any(line.startswith('default ') for line in route.splitlines()), 'route': route, 'tailscale': ts, 'ssh': ssh, 'remote_ready': bool(ts.get('online') and ssh.get('ok')), 'time': time.time()}

def repair_remote_access(payload=None):
    steps = []
    steps.append(sh('systemctl enable --now ssh.service 2>&1 || systemctl enable --now sshd.service 2>&1 || true', timeout=20))
    if shutil.which('tailscale'):
        steps.append(sh('systemctl enable --now tailscaled 2>&1 || true', timeout=20))
    if pathlib.Path('/usr/bin/nmcli').exists():
        steps.append(sh('nmcli radio wifi on; rfkill unblock wifi || true; iw dev wlan0 set power_save off 2>/dev/null || true', timeout=15))
    status_now = network_status()
    return {'ok': status_now.get('remote_ready'), 'message': 'Remote access repair attempted: SSH enabled, tailscaled started, Wi-Fi unblocked/power-save disabled.', 'steps': [s.get('output','')[-1000:] for s in steps], 'network': status_now}

def connect_home_wifi(payload):
    ssid=(payload.get('ssid') or '').strip(); password=payload.get('password') or ''
    keep_hotspot=bool(payload.get('keepHotspot', False))
    if not ssid: return {'ok': False, 'error': 'SSID is required'}
    st=read_state(); st['home_wifi_ssid']=ssid; st['home_wifi_saved_at']=time.time(); write_state(st)
    if not pathlib.Path('/usr/bin/nmcli').exists(): return {'ok': False, 'error': 'nmcli/NetworkManager not installed yet; saved SSID locally only'}
    pre = network_status()
    con = 'MapPI3-home'
    cmd = "set -u; nmcli radio wifi on; rfkill unblock wifi || true; iw dev wlan0 set power_save off 2>/dev/null || true; nmcli device wifi rescan || true; "
    cmd += "nmcli connection delete " + shlex.quote(con) + " >/dev/null 2>&1 || true; "
    cmd += "nmcli connection add type wifi ifname wlan0 con-name " + shlex.quote(con) + " ssid " + shlex.quote(ssid) + "; "
    cmd += "nmcli connection modify " + shlex.quote(con) + " connection.autoconnect yes connection.autoconnect-priority 700 wifi-sec.key-mgmt wpa-psk wifi-sec.psk " + shlex.quote(password) + " ipv4.method auto; "
    if keep_hotspot:
        cmd += "nmcli connection up " + shlex.quote(con) + " || nmcli device wifi connect " + shlex.quote(ssid) + " password " + shlex.quote(password) + "; "
    else:
        cmd += "nmcli connection down MapPI3-hotspot || true; sleep 2; nmcli connection up " + shlex.quote(con) + " || nmcli device wifi connect " + shlex.quote(ssid) + " password " + shlex.quote(password) + "; "
    cmd += "systemctl enable --now ssh.service 2>/dev/null || systemctl enable --now sshd.service 2>/dev/null || true; systemctl enable --now tailscaled 2>/dev/null || true"
    out = sh(cmd, timeout=60)
    time.sleep(3)
    out['pre_network'] = pre
    out['network'] = network_status()
    out['message'] = ('Attempted Wi-Fi join while keeping hotspot up. Some Pi Wi-Fi adapters cannot run AP+client together.' if keep_hotspot else 'Attempted Wi-Fi join after lowering the MapPI3 hotspot. Reconnect over Tailscale/LAN if successful; use hotspot restore locally if not.')
    return out

def wifi_connect_saved(payload=None):
    payload = payload or {}
    name = str(payload.get('name') or payload.get('connection') or '').strip()
    ssid = str(payload.get('ssid') or '').strip()
    keep_hotspot = bool(payload.get('keepHotspot', False))
    if not name and ssid:
        name = _safe_connection_name(ssid, payload.get('label') or ssid)
    if not name:
        return {'ok': False, 'error': 'Saved Wi-Fi connection name or SSID is required'}
    if not name.startswith('MapPI3-'):
        return {'ok': False, 'error': 'Refusing to switch to a non-MapPI3 managed connection'}
    if not pathlib.Path('/usr/bin/nmcli').exists(): return {'ok': False, 'error': 'nmcli/NetworkManager not installed'}
    known = [item.get('name') for item in network_status().get('saved_wifi', [])]
    if name not in known: return {'ok': False, 'error': f'Saved Wi-Fi connection not found: {name}', 'known': known}
    pre = network_status()
    cmd = 'nmcli radio wifi on; rfkill unblock wifi || true; iw dev wlan0 set power_save off 2>/dev/null || true; '
    if not keep_hotspot:
        cmd += 'nmcli connection down MapPI3-hotspot || true; sleep 2; '
    cmd += 'nmcli connection up ' + shlex.quote(name) + '; '
    cmd += 'systemctl enable --now ssh.service 2>/dev/null || systemctl enable --now sshd.service 2>/dev/null || true; '
    cmd += 'systemctl enable --now tailscaled 2>/dev/null || true'
    out = sh(cmd, timeout=60)
    time.sleep(4)
    net = network_status()
    out['ok'] = bool(out.get('ok') and (net.get('has_default_route') or net.get('tailscale',{}).get('online')))
    out['pre_network'] = pre
    out['network'] = net
    out['message'] = f'Requested switch to saved Wi-Fi {name}. SSH and tailscaled were enabled. If Tailscale is Running, disconnect from hotspot, turn on Tailscale, then SSH to the shown Tailscale IP/DNS.'
    return out

def hotspot_on(payload=None):
    saved_names = [item.get('name') for item in _wifi_saved_connections() if item.get('name','').startswith('MapPI3-') and item.get('name') != 'MapPI3-hotspot']
    down = ' '.join('nmcli connection down ' + shlex.quote(n) + ' >/dev/null 2>&1 || true;' for n in saved_names[:20])
    cmd = 'nmcli radio wifi on; rfkill unblock wifi || true; nmcli connection modify MapPI3-hotspot connection.autoconnect yes connection.autoconnect-priority 500 ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv4.never-default yes || true; ' + down + ' nmcli connection up MapPI3-hotspot'
    out = sh(cmd, timeout=45)
    out['network'] = network_status()
    return out

def tailscale_status(payload=None):
    if not shutil.which('tailscale'):
        return {'ok': False, 'installed': False, 'backend_state': 'not-installed'}
    text = sh('timeout 8 tailscale status --json 2>/dev/null', timeout=10).get('output','')
    try:
        data=json.loads(text)
        self_node=data.get('Self') or {}
        return {'ok': True, 'installed': True, 'backend_state': data.get('BackendState'), 'current_tailnet': data.get('CurrentTailnet'), 'hostname': self_node.get('HostName'), 'online': self_node.get('Online'), 'tailscale_ips': self_node.get('TailscaleIPs'), 'dns_name': self_node.get('DNSName')}
    except Exception:
        short = sh('timeout 6 tailscale status 2>&1 || true', timeout=8).get('output','')[-1000:]
        return {'ok': False, 'installed': True, 'backend_state': short.strip() or 'unknown'}

def tailscale_login(payload=None):
    if not shutil.which('tailscale'):
        return {'ok': False, 'installed': False, 'error': 'tailscale CLI is not installed'}
    sh('systemctl enable --now tailscaled || true', timeout=15)
    out = sh('timeout 25 tailscale up --ssh --hostname=MapPI3 --accept-dns=false 2>&1 || true', timeout=30)
    status = tailscale_status()
    auth_url = ''
    for token in out.get('output','').split():
        if token.startswith('https://login.tailscale.com/'):
            auth_url = token.strip()
            break
    return {'ok': status.get('backend_state') == 'Running', 'message': 'Open auth_url and sign into the real_cak3d tailnet if present. If no URL appears, connect the Pi to internet first, then retry.', 'auth_url': auth_url, 'output_tail': out.get('output','')[-1600:], 'status': status, 'network': network_status()}


def pi_weather(payload):
    try:
        lat=float(payload.get('lat') or 44.1004); lon=float(payload.get('lon') or -70.2148); days=max(1,min(10,int(payload.get('days') or 10))); tz=urllib.parse.quote(str(payload.get('timezone') or 'auto'))
        url=f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code&hourly=temperature_2m,relative_humidity_2m,precipitation_probability,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&forecast_days={days}&temperature_unit=fahrenheit&timezone={tz}'
        last_err=None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=18) as r:
                    data=json.loads(r.read().decode())
                break
            except Exception as e:
                last_err=e
                time.sleep(1.5)
        else:
            raise last_err
        daily=[{'date':d,'maxF':data.get('daily',{}).get('temperature_2m_max',[None]*days)[i],'minF':data.get('daily',{}).get('temperature_2m_min',[None]*days)[i],'precip':data.get('daily',{}).get('precipitation_probability_max',[None]*days)[i],'code':data.get('daily',{}).get('weather_code',[None]*days)[i]} for i,d in enumerate((data.get('daily',{}).get('time') or [])[:days])]
        hourly=[{'time':t,'tempF':data.get('hourly',{}).get('temperature_2m',[None])[i],'humidity':data.get('hourly',{}).get('relative_humidity_2m',[None])[i],'precip':data.get('hourly',{}).get('precipitation_probability',[None])[i],'code':data.get('hourly',{}).get('weather_code',[None])[i]} for i,t in enumerate((data.get('hourly',{}).get('time') or [])[:min(72,days*24)])]
        return {'ok': True, 'source':'Pi internet Open-Meteo live', 'lat':lat, 'lon':lon, 'days':days, 'current':data.get('current',{}), 'daily':daily, 'hourly':hourly, 'fetched_at':time.time()}
    except Exception as e:
        return {'ok': False, 'source':'Pi weather unavailable/offline', 'error':str(e), 'fetched_at':time.time()}

def setup_vnc(payload=None):
    payload=payload or {}; password=str(payload.get('password') or '4Walls')
    pw_hash=hashlib.sha256(('mappi3-vnc:'+password).encode()).hexdigest()
    path=pathlib.Path('/etc/mappi3'); path.mkdir(parents=True, exist_ok=True)
    (path/'vnc-password.sha256').write_text(pw_hash+'\n')
    os.chmod(path/'vnc-password.sha256', 0o600)
    install=sh('DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y x11vnc || true', timeout=180)
    if pathlib.Path('/usr/bin/x11vnc').exists():
        sh('x11vnc -storepasswd '+json.dumps(password)+' /etc/mappi3/x11vnc.pass >/dev/null 2>&1 || true', timeout=20)
        service="""[Unit]\\nDescription=MapPI3 debug VNC (disabled by default)\\nAfter=network.target\\n\\n[Service]\\nType=simple\\nExecStart=/usr/bin/x11vnc -forever -shared -rfbauth /etc/mappi3/x11vnc.pass -rfbport 5900 -display :0\\nRestart=on-failure\\n\\n[Install]\\nWantedBy=multi-user.target\\n"""
        pathlib.Path('/etc/systemd/system/mappi3-debug-vnc.service').write_text(service)
        sh('systemctl daemon-reload; systemctl disable --now mappi3-debug-vnc.service || true', timeout=20)
        return {'ok': True, 'installed': True, 'enabled': False, 'message':'x11vnc installed/configured but disabled. Enable only for debugging.', 'install_output':install.get('output','')[-1000:]}
    return {'ok': False, 'installed': False, 'enabled': False, 'message':'VNC password hash saved, but x11vnc is not installed. Pi likely has no internet or package install failed. Service left disabled/not created.', 'install_output':install.get('output','')[-2000:]}

def disable_vnc():
    r=sh('systemctl disable --now mappi3-debug-vnc.service vncserver-x11-serviced.service wayvnc.service x11vnc.service 2>/dev/null || true', timeout=20)
    return {'ok': True, 'message':'VNC services disabled for field mode.', 'output':r.get('output','')}


def gps_diagnose():
    dev=gps_device()
    checks={
        'device': dev,
        'serial0': sh('ls -l /dev/serial0 2>&1 || true', timeout=3).get('output','').strip(),
        'gpsd_active': sh('systemctl is-active gpsd 2>/dev/null || true', timeout=3).get('output','').strip(),
        'gpsd_enabled': sh('systemctl is-enabled gpsd 2>/dev/null || true', timeout=3).get('output','').strip(),
        'devices_file': sh('cat /etc/default/gpsd 2>/dev/null || true', timeout=3).get('output','')[-1200:],
        'sample': gps_status(),
    }
    if not dev:
        checks['recommendation']='No serial GPS device path found. Check wiring/HAT/USB and enable serial.'
    elif not checks['sample'].get('fix'):
        checks['recommendation']='GPS path exists but gpsd has no fix/device report. Try clear sky 5-15 min, then restart gpsd; if DEVICES is empty, set /dev/serial0 in /etc/default/gpsd.'
    else:
        checks['recommendation']='GPS fix present.'
    return {'ok': True, 'diagnostics': checks}

def sense_diagnose(payload=None):
    payload = payload or {}
    count = max(3, min(20, int(payload.get('count') or 8)))
    delay = max(0.02, min(0.5, float(payload.get('delay') or 0.12)))
    samples = []
    try:
        from sense_hat import SenseHat
        sense = SenseHat()
        for _ in range(count):
            raw = sense.get_accelerometer_raw()
            orient = sense.get_orientation()
            try: compass = sense.get_compass()
            except Exception: compass = None
            ax = float(raw.get('x', 0.0)); ay = float(raw.get('y', 0.0)); az = float(raw.get('z', 1.0))
            plane = math.sqrt(ax*ax + ay*ay)
            samples.append({
                'raw_accel': {'x': round(ax,4), 'y': round(ay,4), 'z': round(az,4)},
                'raw_plane_magnitude': round(plane,4),
                'raw_tilt_degrees': round(math.degrees(math.atan2(plane, max(0.001, abs(az)))),2),
                'orientation': {k: round(float(orient.get(k) or 0), 2) for k in ('roll','pitch','yaw')},
                'compass': round(float(compass), 2) if compass is not None else None,
                'time': time.time(),
            })
            time.sleep(delay)
        def span(path):
            vals=[]
            for sample in samples:
                cur=sample
                for part in path.split('.'):
                    cur=cur.get(part) if isinstance(cur, dict) else None
                if isinstance(cur, (int,float)): vals.append(float(cur))
            return round(max(vals)-min(vals),4) if vals else None
        spans = {
            'raw_x': span('raw_accel.x'),
            'raw_y': span('raw_accel.y'),
            'raw_z': span('raw_accel.z'),
            'roll': span('orientation.roll'),
            'pitch': span('orientation.pitch'),
            'tilt_degrees': span('raw_tilt_degrees'),
        }
        moving = any((spans.get(k) or 0) > (0.08 if k.startswith('raw_') else 3.0) for k in spans)
        return {'ok': True, 'count': count, 'delay': delay, 'samples': samples, 'spans': spans, 'moving': moving, 'sense_cache': sense_snapshot(), 'hint': 'Tilt the Pi during this command; raw_x/raw_y/roll/pitch/tilt_degrees spans should jump if the IMU is moving.'}
    except Exception as e:
        return {'ok': False, 'error': str(e), 'sense_cache': sense_snapshot()}


def field_ai_verify(payload=None):
    payload=payload or {}; ensure_builtin_models()
    status_info=field_ai_status()
    colors={'auto':(30,180,45),'plant':(30,180,45),'cloud':(245,245,245),'mushroom':(220,130,35),'animal':(55,48,42),'bug':(18,18,18),'track':(85,70,55),'rock':(145,145,145),'barcode':(0,0,0),'injury':(205,115,95),'firstaid':(205,40,35),'survival':(70,120,55)}
    def sample_png(color):
        try:
            from PIL import Image, ImageDraw
            img=Image.new('RGB',(24,24),color)
            draw=ImageDraw.Draw(img)
            if color==(0,0,0):
                img=Image.new('RGB',(24,24),(255,255,255)); draw=ImageDraw.Draw(img)
                for x in range(0,24,4): draw.rectangle([x,0,x+1,23], fill=(0,0,0))
            else:
                draw.line((0,0,23,23), fill=tuple(max(0,c-45) for c in color), width=2)
                draw.line((23,0,0,23), fill=tuple(min(255,c+45) for c in color), width=2)
            buf=io.BytesIO(); img.save(buf, format='PNG')
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgaGD4DwABBAEAgh1Y6QAAAABJRU5ErkJggg=='
    samples={k:sample_png(v) for k,v in colors.items()}
    requested=payload.get('category')
    all_cats=[c['id'] for c in FIELD_AI_CATEGORIES]
    cats=[requested] if requested and requested!='all' else all_cats
    results={}
    for cat in cats:
        image='' if cat in ('firstaid','survival') else (samples.get(cat) or samples['plant'])
        result=field_ai_analyze({'category': cat, 'image': image, 'notes':'MapPI3 all-category prototype/readiness self-test observation'})
        expected_proto=PROTOTYPE_MODEL_BY_CATEGORY.get(cat)
        prototype=result.get('prototype_model')
        field_id=(result.get('possible_identification') or {}).get('id')
        field_ok=bool(field_id and field_id!='reference')
        prototype_ok=bool(prototype) if expected_proto else True
        results[cat]={'ok': bool(result.get('ok')), 'field_guide_ok': field_ok, 'prototype_expected': expected_proto, 'prototype_ok': prototype_ok, 'specialist_ready': (result.get('router') or {}).get('model_ready'), 'specialist_backend': result.get('specialist_backend'), 'vision_model': result.get('vision_model'), 'prototype_model': prototype, 'possible_identification': result.get('possible_identification'), 'observation_id': result.get('observation_id')}
    return {'ok': all(v.get('ok') and v.get('field_guide_ok') and v.get('prototype_ok') for v in results.values()), 'status': status_info, 'results': results, 'sample': next(iter(results.values()), {}), 'note':'Self-test verifies all categories route to a safe field-guide/reference result. Prototype JSON cue models are expected for image categories; barcode/OCR specialist_backend reports real zbar/tesseract availability when installed. Species/geology/weather specialist model binaries are not implied.'}

NOAA_CACHE = pathlib.Path('/var/lib/mappi3/noaa-weather-cache.json')

def _http_json(url, timeout=15):
    req=urllib.request.Request(url, headers={'User-Agent':'MapPI3 Trail Buddy (github.com/real-CAK3D/MapPI3; offline field weather cache)', 'Accept':'application/geo+json, application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def noaa_weather(payload=None):
    payload=payload or {}
    lat=float(payload.get('lat') or 44.1004); lon=float(payload.get('lon') or -70.2148)
    force=bool(payload.get('force'))
    cache={'ok':False}
    if NOAA_CACHE.exists():
        try: cache=json.loads(NOAA_CACHE.read_text())
        except Exception: cache={'ok':False}
    age=time.time()-float(cache.get('fetched_at') or 0)
    if cache.get('ok') and not force and age < 1800 and abs(float(cache.get('lat',lat))-lat)<0.02 and abs(float(cache.get('lon',lon))-lon)<0.02:
        cache['cached']=True; cache['age_seconds']=round(age); return cache
    try:
        point=_http_json(f'https://api.weather.gov/points/{lat:.4f},{lon:.4f}')
        props=point.get('properties') or {}
        forecast_url=props.get('forecast'); hourly_url=props.get('forecastHourly')
        zone_url=props.get('forecastZone') or props.get('county')
        forecast=_http_json(forecast_url) if forecast_url else {}
        hourly=_http_json(hourly_url) if hourly_url else {}
        alerts=_http_json(f'https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}')
        periods=(forecast.get('properties') or {}).get('periods') or []
        hourly_periods=(hourly.get('properties') or {}).get('periods') or []
        alert_items=[]
        for f in (alerts.get('features') or [])[:12]:
            p=f.get('properties') or {}; alert_items.append({'event':p.get('event'),'headline':p.get('headline'),'severity':p.get('severity'),'urgency':p.get('urgency'),'certainty':p.get('certainty'),'area':p.get('areaDesc'),'instruction':p.get('instruction'),'description':(p.get('description') or '')[:1500],'effective':p.get('effective'),'expires':p.get('expires')})
        out={'ok':True,'source':'NOAA/NWS weather.gov live','lat':lat,'lon':lon,'cached':False,'fetched_at':time.time(),'office':props.get('cwa'),'grid':{'x':props.get('gridX'),'y':props.get('gridY')},'zone_url':zone_url,'forecast_url':forecast_url,'hourly_url':hourly_url,'periods':[{'name':p.get('name'),'startTime':p.get('startTime'),'temperature':p.get('temperature'),'temperatureUnit':p.get('temperatureUnit'),'windSpeed':p.get('windSpeed'),'windDirection':p.get('windDirection'),'shortForecast':p.get('shortForecast'),'detailedForecast':p.get('detailedForecast')} for p in periods[:14]],'hourly':[{'startTime':p.get('startTime'),'temperature':p.get('temperature'),'shortForecast':p.get('shortForecast'),'windSpeed':p.get('windSpeed'),'probabilityOfPrecipitation':(p.get('probabilityOfPrecipitation') or {}).get('value')} for p in hourly_periods[:36]],'alerts':alert_items,'alert_count':len(alert_items),'note':'NWS text forecasts/alerts cache for offline field reference. Satellite/radar imagery is a future plugin layer.'}
        NOAA_CACHE.parent.mkdir(parents=True, exist_ok=True); NOAA_CACHE.write_text(json.dumps(out))
        return out
    except Exception as e:
        if cache.get('ok'):
            cache['cached']=True; cache['offline_error']=str(e); cache['age_seconds']=round(age); cache['source']='NOAA/NWS cached fallback'; return cache
        return {'ok':False,'source':'NOAA/NWS unavailable','lat':lat,'lon':lon,'error':str(e),'hint':'Connect Pi to internet via online maintenance to refresh NOAA/NWS cache.'}

def start_online_maintenance(payload=None):
    payload=payload or {}
    ssid=str(payload.get('ssid') or payload.get('homeWifiSsid') or '').strip()[:64]
    password=str(payload.get('password') or payload.get('homeWifiPassword') or '').strip()[:128]
    lat=str(payload.get('lat') or '44.1004')[:32]; lon=str(payload.get('lon') or '-70.2148')[:32]
    days=str(payload.get('days') or '5')[:4]; tz=str(payload.get('timezone') or 'America/New_York')[:64]
    if not ssid or not password: return {'ok': False, 'error':'ssid and password required'}
    script=pathlib.Path('/tmp/mappi3-online-maintenance-from-app.sh')
    log=pathlib.Path('/var/lib/mappi3/app-online-maintenance.log')
    body=f"""#!/bin/bash
set -u
LOG={str(log)!r}
exec >>"$LOG" 2>&1
echo "=== app online maintenance $(date -Is) ==="
restore() {{
  echo "restoring MapPI3 hotspot"
  nmcli radio wifi on || true
  rfkill unblock wifi || true
  nmcli connection modify MapPI3-hotspot connection.autoconnect yes connection.autoconnect-priority 100 802-11-wireless.powersave 2 ipv4.method shared || true
  nmcli connection up MapPI3-hotspot || true
  iw dev wlan0 set power_save off 2>/dev/null || true
  echo "final active:"; nmcli -t -f NAME,TYPE,DEVICE connection show --active || true
  echo "=== done $(date -Is) ==="
}}
trap restore EXIT
nmcli radio wifi on || true
rfkill unblock wifi || true
nmcli connection modify MapPI3-home 802-11-wireless.ssid {json.dumps(ssid)} 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk {json.dumps(password)} connection.autoconnect yes connection.autoconnect-priority 50 ipv4.method auto ipv4.ignore-auto-dns yes ipv4.dns '1.1.1.1 8.8.8.8' || true
nmcli connection down MapPI3-hotspot || true
sleep 2
nmcli connection up MapPI3-home || true
sleep 24
echo "active:"; nmcli -t -f NAME,TYPE,DEVICE connection show --active || true
echo "routes:"; ip route || true
echo "dns:"; cat /etc/resolv.conf || true; getent hosts api.open-meteo.com || true; getent hosts deb.debian.org || true
python3 - <<'PY' || true
import urllib.request
for url in ['https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m','https://api.github.com']:
    try:
        r=urllib.request.urlopen(url,timeout=10); print(url, r.status)
    except Exception as e: print(url, 'ERR', repr(e))
PY
echo "weather:"; curl -sS --max-time 20 'http://127.0.0.1:{PORT}/api/weather?lat={urllib.parse.quote(lat)}&lon={urllib.parse.quote(lon)}&days={urllib.parse.quote(days)}&timezone={urllib.parse.quote(tz)}' || true; echo
echo "noaa weather:"; curl -sS --max-time 30 'http://127.0.0.1:{PORT}/api/noaa-weather?lat={urllib.parse.quote(lat)}&lon={urllib.parse.quote(lon)}&force=1' || true; echo
echo "ai verify:"; curl -sS --max-time 20 -H 'Content-Type: application/json' -d '{{"category":"plant"}}' http://127.0.0.1:{PORT}/api/command/field-ai-verify || true; echo
echo "vnc:"; curl -sS --max-time 10 http://127.0.0.1:{PORT}/api/vnc/status || true; echo
"""
    script.write_text(body); os.chmod(script,0o700)
    r=sh(f'systemd-run --unit=mappi3-app-online-maintenance --collect {script}', timeout=10)
    st=read_state(); st['online_maintenance_started_at']=time.time(); st['online_maintenance_log']=str(log); st['online_maintenance_ssid']=ssid; write_state(st)
    return {'ok': r.get('ok'), 'message':'Started online maintenance. The hotspot will drop briefly, then restore automatically. Reconnect to MapPI3 in about 60-120 seconds.', 'log': str(log), 'output': r.get('output','')[-1200:]}

def online_maintenance_log():
    p=pathlib.Path('/var/lib/mappi3/app-online-maintenance.log')
    try: content=p.read_text()[-6000:]
    except Exception as e: content=str(e)
    return {'ok': p.exists(), 'log': str(p), 'content': content}

def harden_hotspot():
    cmds = [
        "nmcli connection modify MapPI3-hotspot connection.autoconnect yes connection.autoconnect-priority 999 connection.autoconnect-retries 0 connection.wait-device-timeout 0 802-11-wireless.band bg 802-11-wireless.channel 1 802-11-wireless.powersave 2 ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv4.never-default yes ipv6.method ignore || true",
        "iw dev wlan0 set power_save off 2>/dev/null || true",
        "mkdir -p /etc/NetworkManager/conf.d && printf '[connection]\nwifi.powersave = 2\n\n[device]\nwifi.scan-rand-mac-address=no\n' > /etc/NetworkManager/conf.d/99-mappi3-field-lock.conf",
        "rfkill unblock wifi || true",
        "nmcli radio wifi on || true"
    ]
    out=[]
    for c in cmds: out.append(sh(c, timeout=15)['output'])
    st=read_state(); st['hotspot_hardened_at']=time.time(); write_state(st)
    return {'ok': True, 'message': 'Hotspot hardened: autoconnect priority raised and Wi-Fi power-save disabled.', 'output': '\n'.join(out)[-4000:], 'state': st}

def vnc_status():
    services=['vncserver-x11-serviced.service','wayvnc.service','x11vnc.service']
    found=[]
    for svc in services:
        r=sh(f'systemctl is-enabled {svc} 2>/dev/null; systemctl is-active {svc} 2>/dev/null', timeout=5)['output'].strip().splitlines()
        found.append({'service': svc, 'enabled': r[0] if r else 'unknown', 'active': r[1] if len(r)>1 else 'unknown'})
    bins=sh('command -v vncserver-x11 || command -v wayvnc || command -v x11vnc || true', timeout=5)['output'].strip().splitlines()
    active=[f for f in found if f.get('active')=='active']
    return {'ok': True, 'installed_bins': bins, 'services': found, 'summary': ('active: '+', '.join(f['service'] for f in active)) if active else ('installed but not active' if bins else 'not installed yet')}

def plugin_update(payload):
    st=read_state(); features=st.get('features') if isinstance(st.get('features'),dict) else {}
    key=str(payload.get('key') or '').strip(); enabled=bool(payload.get('enabled'))
    if not key: return {'ok': False, 'error': 'key required'}
    features[key]=enabled; st['features']=features; st['features_updated_at']=time.time(); write_state(st)
    return {'ok': True, 'features': features}

PLUGIN_ROOTS = [pathlib.Path('/opt/mappi3/plugins'), pathlib.Path('/var/lib/mappi3/plugins-src'), pathlib.Path('/boot/mappi3/plugins')]
PLUGIN_STATE = pathlib.Path('/var/lib/mappi3/plugins')

def _safe_plugin_id(value):
    raw=str(value or '').strip().lower()
    return ''.join(c for c in raw if c.isalnum() or c in ('-','_'))[:80]

def plugin_registry():
    packs={}
    for root in PLUGIN_ROOTS:
        if not root.exists(): continue
        for meta in root.glob('*/plugin.json'):
            try:
                data=json.loads(meta.read_text())
                pid=_safe_plugin_id(data.get('id') or meta.parent.name)
                if not pid: continue
                marker=PLUGIN_STATE/pid/'installed.json'
                installed={}
                if marker.exists():
                    try: installed=json.loads(marker.read_text())
                    except Exception: installed={'status':'installed'}
                packs[pid]={**data,'id':pid,'source':str(meta.parent),'installed':marker.exists(),'installed_marker':str(marker),'installed_state':installed}
            except Exception as e:
                packs[meta.parent.name]={'id':meta.parent.name,'source':str(meta.parent),'error':str(e),'installed':False}
    return packs

def plugin_status(payload=None):
    packs=plugin_registry()
    return {'ok': True, 'root_candidates':[str(x) for x in PLUGIN_ROOTS], 'installed_root':str(PLUGIN_STATE), 'count':len(packs), 'installed_count':sum(1 for p in packs.values() if p.get('installed')), 'packs':packs, 'time':time.time()}

def _run_plugin_script(pid, script_name):
    packs=plugin_registry(); pack=packs.get(pid)
    if not pack: return {'ok': False, 'id':pid, 'error':'plugin not found'}
    source=pathlib.Path(pack.get('source') or '')
    script=source/script_name
    if not script.exists(): return {'ok': False, 'id':pid, 'error':f'{script_name} missing', 'source':str(source)}
    if not str(script.resolve()).startswith(str(source.resolve())): return {'ok': False, 'id':pid, 'error':'unsafe script path'}
    os.chmod(script, os.stat(script).st_mode | 0o755)
    out=sh(f'cd {json.dumps(str(source))} && bash {json.dumps(str(script))}', timeout=180)
    st=read_state(); installed=st.get('installed_plugins') if isinstance(st.get('installed_plugins'),dict) else {}
    installed[pid]={'installed': script_name=='install.sh', 'updated_at':time.time(), 'source':str(source), 'output':out.get('output','')[-1200:]}
    st['installed_plugins']=installed; write_state(st)
    return {'ok': out.get('ok'), 'id':pid, 'script':script_name, 'source':str(source), 'output':out.get('output','')[-2500:], 'status':plugin_status().get('packs',{}).get(pid,{})}

def plugin_install(payload=None):
    payload=payload or {}; pid=_safe_plugin_id(payload.get('id') or payload.get('key'))
    if not pid: return {'ok': False, 'error':'id required'}
    return _run_plugin_script(pid, 'install.sh')

def plugin_uninstall(payload=None):
    payload=payload or {}; pid=_safe_plugin_id(payload.get('id') or payload.get('key'))
    if not pid: return {'ok': False, 'error':'id required'}
    return _run_plugin_script(pid, 'uninstall.sh')

def plugin_install_all(payload=None):
    payload=payload or {}; packs=plugin_registry(); ids=payload.get('ids') or payload.get('queue') or list(packs.keys())
    ids=[_safe_plugin_id(x) for x in ids if _safe_plugin_id(x)]
    results=[]
    for pid in ids:
        results.append(plugin_install({'id':pid}))
    ok=all(r.get('ok') for r in results)
    return {'ok': ok, 'requested':ids, 'installed':sum(1 for r in results if r.get('ok')), 'failed':[r for r in results if not r.get('ok')], 'results':results, 'status':plugin_status()}

def captive_status():
    active=sh('systemctl is-active mappi3-captive.service 2>/dev/null || true', timeout=5)['output'].strip()
    enabled=sh('systemctl is-enabled mappi3-captive.service 2>/dev/null || true', timeout=5)['output'].strip()
    port=sh("ss -lntp | grep ':80 ' || true", timeout=5)['output'].strip()
    return {'ok': active == 'active', 'active': active or 'unknown', 'enabled': enabled or 'unknown', 'port80': bool(port), 'summary': 'phone stay-connected portal active' if active=='active' else 'not active'}

def setup_captive(payload=None):
    script=pathlib.Path('/usr/local/bin/mappi3-captive.py')
    script.write_text('#!/usr/bin/env python3\nimport http.server, urllib.parse, time\nAPP=\'http://10.42.0.1:5050/\'\nPROBES={\'/generate_204\':(204,\'text/plain\',\'\'),\'/gen_204\':(204,\'text/plain\',\'\'),\'/hotspot-detect.html\':(200,\'text/html\',\'<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success<br><a href="%s">Open MapPI3</a></BODY></HTML>\'%APP),\'/connecttest.txt\':(200,\'text/plain\',\'Microsoft Connect Test\'),\'/ncsi.txt\':(200,\'text/plain\',\'Microsoft NCSI\'),\'/canonical.html\':(200,\'text/html\',\'<meta http-equiv="refresh" content="0; url=%s">\'%APP)}\nclass H(http.server.BaseHTTPRequestHandler):\n    def _send(self,code,ctype,body):\n        raw=body.encode(); self.send_response(code); self.send_header(\'Content-Type\',ctype); self.send_header(\'Cache-Control\',\'no-store\'); self.send_header(\'Content-Length\',str(len(raw))); self.end_headers(); self.wfile.write(raw)\n    def do_GET(self):\n        p=urllib.parse.urlparse(self.path).path\n        if p in PROBES:\n            code,ctype,body=PROBES[p]; self._send(code,ctype,body); return\n        if p in (\'/\',\'/index.html\',\'/map\',\'/login\'):\n            self._send(200,\'text/html\',\'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>MapPI3</title><style>body{font-family:sans-serif;background:#07130d;color:#eaffef;padding:24px}a{color:#70f0a0;font-size:1.2rem}</style><h1>MapPI3 Trail Buddy</h1><p>No internet required. Stay on this Wi-Fi and open the trail app.</p><p><a href="\'+APP+\'">Open MapPI3 app</a></p><small>\'+time.ctime()+\'</small>\'); return\n        self.send_response(302); self.send_header(\'Location\',APP); self.end_headers()\n    def log_message(self,*a): pass\nhttp.server.ThreadingHTTPServer((\'0.0.0.0\',80),H).serve_forever()\n')
    os.chmod(script,0o755)
    service=pathlib.Path('/etc/systemd/system/mappi3-captive.service')
    service.write_text('[Unit]\nDescription=MapPI3 phone stay-connected captive helper\nAfter=network-online.target NetworkManager.service\nWants=network-online.target\n\n[Service]\nType=simple\nExecStartPre=/bin/sh -c \'for i in $(seq 1 45); do ip addr show wlan0 | grep -q "10.42.0.1" && exit 0; sleep 1; done; exit 0\'\nExecStart=/usr/bin/python3 /usr/local/bin/mappi3-captive.py\nRestart=always\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\n')
    out=sh('systemctl daemon-reload && systemctl enable --now mappi3-captive.service && systemctl status --no-pager mappi3-captive.service | sed -n "1,12p"', timeout=30)
    st=read_state(); st['captive_portal_enabled_at']=time.time(); write_state(st)
    return {'ok': out.get('ok'), 'message':'Phone stay-connected captive portal enabled on port 80', 'status': captive_status(), 'output': out.get('output','')[-1200:]}

def setup_gps_pps(payload=None):
    backup = sh('STAMP=$(date +%Y%m%d-%H%M%S); mkdir -p /var/backups/mappi3-pps-setup; for f in /boot/firmware/cmdline.txt /boot/cmdline.txt /boot/firmware/config.txt /etc/default/gpsd; do [ -f "$f" ] && cp -a "$f" "/var/backups/mappi3-pps-setup/$(echo $f|tr / _).$STAMP.bak"; done', timeout=20)
    cmdline_script = r"""
python3 - <<'PY'
from pathlib import Path
src = Path('/proc/cmdline').read_text().strip().split()
bad = ('console=ttyAMA','console=ttyS','console=serial','kgdboc=ttyAMA','kgdboc=ttyS','kgdboc=serial')
parts = [t for t in src if not t.startswith(bad)]
if not any(x.startswith('root=') for x in parts):
    parts += ['console=tty1','root=/dev/mmcblk0p2','rootfstype=ext4','rootwait']
if not any(x.startswith('cfg80211.ieee80211_regdom=') for x in parts):
    parts.append('cfg80211.ieee80211_regdom=US')
seen = []
for part in parts:
    if part not in seen:
        seen.append(part)
Path('/tmp/mappi3-clean-cmdline.txt').write_text(' '.join(seen) + '\n')
PY
for f in /boot/firmware/cmdline.txt /boot/cmdline.txt; do [ -f "$f" ] && cp /tmp/mappi3-clean-cmdline.txt "$f" || true; done
"""
    cmdline = sh(cmdline_script, timeout=20)
    config = sh("CFG=/boot/firmware/config.txt; [ -f $CFG ] || CFG=/boot/config.txt; grep -q '^enable_uart=1' $CFG || echo 'enable_uart=1' >> $CFG; grep -q '^dtoverlay=pps-gpio,gpiopin=18' $CFG || echo 'dtoverlay=pps-gpio,gpiopin=18' >> $CFG", timeout=10)
    gpsd_script = r"""
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/default/gpsd')
s = p.read_text() if p.exists() else 'START_DAEMON="true"\nUSBAUTO="false"\n'
lines = []
for line in s.splitlines():
    if line.startswith('DEVICES='):
        lines.append('DEVICES="/dev/serial0 /dev/pps0"')
    elif line.startswith('GPSD_OPTIONS='):
        lines.append('GPSD_OPTIONS="-n"')
    else:
        lines.append(line)
if not any(x.startswith('DEVICES=') for x in lines):
    lines.append('DEVICES="/dev/serial0 /dev/pps0"')
if not any(x.startswith('GPSD_OPTIONS=') for x in lines):
    lines.append('GPSD_OPTIONS="-n"')
p.write_text('\n'.join(lines) + '\n')
PY
"""
    gpsd = sh(gpsd_script, timeout=10)
    services = sh('systemctl mask serial-getty@ttyAMA0.service serial-getty@serial0.service || true; systemctl disable --now serial-getty@ttyAMA0.service serial-getty@serial0.service || true; systemctl daemon-reload; systemctl restart gpsd.socket gpsd || true', timeout=30)
    return {'ok': True, 'message':'GPS UART console disabled; GPIO18 PPS overlay configured. Reboot required for boot cmdline/overlay persistence.', 'backup': backup.get('output','')[-800:], 'cmdline': cmdline.get('output','')[-800:], 'config': config.get('output','')[-800:], 'gpsd': gpsd.get('output','')[-800:], 'services': services.get('output','')[-1200:]}

def disable_captive():
    out=sh('systemctl disable --now mappi3-captive.service || true', timeout=20)
    return {'ok': True, 'message':'Phone stay-connected captive portal disabled', 'status': captive_status(), 'output': out.get('output','')[-800:]}

def command(name, payload=None):
    payload=payload or {}
    if name not in ALLOWED: return {'ok': False, 'error': 'unknown command'}
    if name=='status': return status()
    if name=='network-status': return network_status(payload)
    if name=='wifi-scan': return wifi_scan(payload)
    if name=='wifi-save-network': return wifi_save_network(payload)
    if name=='tailscale-status': return tailscale_status(payload)
    if name=='tailscale-login': return tailscale_login(payload)
    if name=='remote-access-repair': return repair_remote_access(payload)
    if name=='wifi-connect-saved': return wifi_connect_saved(payload)
    if name=='hotspot-on': return hotspot_on(payload)
    if name=='gps-sample': return gps_sample()
    if name=='sense-mode': return set_sense_mode(payload.get('mode') or payload.get('sense_mode') or payload.get('orientationMode') or 'compass', payload)
    if name=='calibrate': return calibrate(payload.get('target') or 'all')
    if name=='harden-hotspot': return harden_hotspot()
    if name=='plugin-update': return plugin_update(payload)
    if name=='plugin-status': return plugin_status(payload)
    if name=='plugin-install': return plugin_install(payload)
    if name=='plugin-uninstall': return plugin_uninstall(payload)
    if name=='plugin-install-all': return plugin_install_all(payload)
    if name=='vnc-setup': return setup_vnc(payload)
    if name=='vnc-disable': return disable_vnc()
    if name=='weather-refresh': return pi_weather(payload)
    if name=='noaa-refresh': return noaa_weather(payload)
    if name=='online-maintenance': return start_online_maintenance(payload)
    if name=='gps-diagnose': return gps_diagnose()
    if name=='sense-diagnose': return sense_diagnose(payload)
    if name=='field-ai-verify': return field_ai_verify(payload)
    if name=='captive-setup': return setup_captive(payload)
    if name=='captive-disable': return disable_captive()
    if name=='captive-status': return captive_status()
    if name=='gps-pps-setup': return setup_gps_pps(payload)
    if name=='restart-web': return sh('systemctl restart mappi3-web.service', timeout=10)
    if name=='reboot': return sh('systemctl reboot', timeout=3)
    if name=='shutdown': return sh('systemctl poweroff', timeout=3)
    if name=='update-app': return sh('/usr/local/bin/mappi3-update-app.sh', timeout=120)
    if name=='connect-home-wifi': return connect_home_wifi(payload)
    if name=='toggle-hotspot':
        st=read_state(); st['hotspot_enabled']=not st.get('hotspot_enabled', True); write_state(st); return sh('/usr/local/bin/mappi3-hotspot.sh', timeout=40)


MEDIA_ROOT = pathlib.Path('/var/lib/mappi3/media')
MEDIA_EXTS = {'.mp3':'audio/mpeg','.ogg':'audio/ogg','.wav':'audio/wav','.m4a':'audio/mp4','.flac':'audio/flac','.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime'}

def media_library_status():
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    items=[]; total=0
    for p in MEDIA_ROOT.rglob('*'):
        try:
            if not p.is_file() or p.suffix.lower() not in MEDIA_EXTS: continue
            st=p.stat(); total += st.st_size
            rel=p.relative_to(MEDIA_ROOT).as_posix()
            kind='video' if MEDIA_EXTS[p.suffix.lower()].startswith('video') else 'audio'
            items.append({'id': hashlib.sha1(rel.encode()).hexdigest()[:12], 'name': p.stem.replace('_',' ').replace('-',' '), 'file': rel, 'url': '/media/'+urllib.parse.quote(rel), 'kind': kind, 'size_bytes': st.st_size, 'size_mb': round(st.st_size/1024/1024,2), 'modified': st.st_mtime, 'content_type': MEDIA_EXTS[p.suffix.lower()]})
        except Exception: pass
    items=sorted(items, key=lambda x:(x['kind'], x['name'].lower()))[:500]
    return {'ok': True, 'root': str(MEDIA_ROOT), 'count': len(items), 'total_mb': round(total/1024/1024,2), 'items': items, 'supported': sorted(MEDIA_EXTS.keys()), 'hint': 'Copy music/videos to /var/lib/mappi3/media on larger SD cards; stream them over the MapPI3 hotspot.'}

def media_manifest():
    data=media_library_status()
    if not data['items']:
        data['starter_collections']=[
            {'name':'Ambient starters','items':['rain','creek','forest','night insects','campfire','white noise'], 'note':'Generated in browser until real audio loops are installed.'},
            {'name':'Trail media folder','path':str(MEDIA_ROOT), 'note':'Add MP3/OGG/WAV/MP4/WEBM files here.'}
        ]
    return data

GAME_ROOT = pathlib.Path('/var/lib/mappi3/games')

def game_library_status():
    GAME_ROOT.mkdir(parents=True, exist_ok=True)
    games=[]
    for d in sorted([x for x in GAME_ROOT.iterdir() if x.is_dir()]):
        try:
            if d.name == 'trail-runner-demo':
                continue
            index=d/'index.html'
            if not index.exists(): continue
            meta={}
            mp=d/'mappi3-game.json'
            if mp.exists():
                try: meta=json.loads(mp.read_text())
                except Exception: meta={}
            rel=d.name
            size=0
            for f in d.rglob('*'):
                try:
                    if f.is_file(): size += f.stat().st_size
                except Exception: pass
            games.append({'id':rel,'title':meta.get('title') or rel.replace('-',' ').replace('_',' ').title(),'url':'/games/'+urllib.parse.quote(rel)+'/index.html','folder':str(d),'offline':True,'size_mb':round(size/1024/1024,2),'note':meta.get('note') or 'Local HTML5 game pack served offline from the MapPI3 hotspot.'})
        except Exception: pass
    return {'ok': True, 'root': str(GAME_ROOT), 'count': len(games), 'games': games, 'hint':'Place legal HTML5 game folders at /var/lib/mappi3/games/<game-id>/index.html. Example: /var/lib/mappi3/games/playmario/index.html. MapPI3 will serve them at /games/<game-id>/index.html offline over the hotspot.'}

def bluetoothctl(args='', timeout=12):
    return sh('bluetoothctl ' + args, timeout=timeout)

def parse_bluetooth_devices(text):
    devices=[]
    for line in (text or '').splitlines():
        line=line.strip()
        if not line.startswith('Device '): continue
        parts=line.split(' ',2)
        if len(parts)>=3:
            devices.append({'mac':parts[1], 'name':parts[2]})
    return devices

def bluetooth_status():
    available=sh('command -v bluetoothctl', timeout=2)
    if not available.get('ok'):
        return {'ok': False, 'available': False, 'summary':'bluetoothctl not installed on this Pi image', 'devices':[], 'paired':[], 'connected':[]}
    ctl=bluetoothctl('show', timeout=3)
    paired_raw=bluetoothctl('paired-devices', timeout=3)
    devices_raw=bluetoothctl('devices', timeout=3)
    paired=parse_bluetooth_devices(paired_raw.get('output',''))[:8]
    devices=parse_bluetooth_devices(devices_raw.get('output',''))[:30]
    connected=[]
    for d in paired[:4]:
        detail=bluetoothctl('info '+d['mac'], timeout=2).get('output','')
        d['connected']='Connected: yes' in detail
        d['trusted']='Trusted: yes' in detail
        if d['connected']: connected.append(d)
    return {'ok': ctl.get('ok'), 'available': True, 'adapter': ctl.get('output','')[-1400:], 'devices': devices, 'paired': paired, 'connected': connected, 'summary':'Bluetooth adapter ready' if ctl.get('ok') else 'Bluetooth adapter not ready'}

def bluetooth_scan(payload=None):
    seconds=max(4, min(25, int((payload or {}).get('seconds') or 8)))
    if not sh('command -v bluetoothctl', timeout=3).get('ok'):
        return {'ok': False, 'error':'bluetoothctl not installed', 'devices':[]}
    sh('rfkill unblock bluetooth || true', timeout=5)
    sh('bluetoothctl power on', timeout=6)
    out=sh(f'timeout {seconds} bluetoothctl --timeout {seconds} scan on', timeout=seconds+8)
    listed=bluetoothctl('devices', timeout=8)
    devices=parse_bluetooth_devices((out.get('output','')+'\n'+listed.get('output','')))
    seen={}
    for d in devices: seen[d['mac']]=d
    return {'ok': True, 'seconds': seconds, 'devices': list(seen.values()), 'raw': out.get('output','')[-2400:], 'summary': f'Found {len(seen)} Bluetooth device(s).'}

def bluetooth_action(action, payload=None):
    payload=payload or {}; mac=(payload.get('mac') or payload.get('address') or '').strip()
    if not mac:
        return {'ok': False, 'error':'Bluetooth MAC/address required.'}
    if not sh('command -v bluetoothctl', timeout=3).get('ok'):
        return {'ok': False, 'error':'bluetoothctl not installed'}
    safe=''.join(ch for ch in mac if ch in '0123456789abcdefABCDEF:')
    if len(safe) < 11:
        return {'ok': False, 'error':'Invalid Bluetooth address.'}
    sh('rfkill unblock bluetooth || true', timeout=5); sh('bluetoothctl power on', timeout=6)
    if action == 'trust': cmd='trust '+safe
    elif action == 'pair': cmd='pair '+safe
    elif action == 'connect': cmd='connect '+safe
    elif action == 'disconnect': cmd='disconnect '+safe
    elif action == 'remove': cmd='remove '+safe
    else: return {'ok': False, 'error':'Unsupported Bluetooth action.'}
    res=bluetoothctl(cmd, timeout=25 if action in ['pair','connect'] else 12)
    status=bluetooth_status()
    return {'ok': res.get('ok'), 'action': action, 'mac': safe, 'output': res.get('output','')[-2400:], 'status': status}

def https_status():
    return {'enabled': True, 'port': HTTPS_PORT, 'cert': str(CERT_FILE), 'key': str(KEY_FILE), 'cert_exists': CERT_FILE.exists(), 'key_exists': KEY_FILE.exists(), 'url': f'https://10.42.0.1:{HTTPS_PORT}/', 'trust_note': 'Self-signed local cert: phone may need manual trust/CA install before sensors/camera/notifications count this as fully trusted HTTPS.'}

def ensure_https_cert():
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if CERT_FILE.exists() and KEY_FILE.exists(): return True
    cmd = 'openssl req -x509 -newkey rsa:2048 -nodes -days 825 -keyout '+json.dumps(str(KEY_FILE))+' -out '+json.dumps(str(CERT_FILE))+' -subj /CN=mappi3.local -addext subjectAltName=DNS:mappi3.local,IP:10.42.0.1,IP:127.0.0.1'
    r = sh(cmd, timeout=20)
    try:
        os.chmod(KEY_FILE, 0o600); os.chmod(CERT_FILE, 0o644)
    except Exception: pass
    return bool(r.get('ok') and CERT_FILE.exists() and KEY_FILE.exists())

def serve_http(port=PORT, use_https=False):
    httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), Handler)
    if use_https:
        if not ensure_https_cert():
            with SENSE_LOCK: SENSE_CACHE['https_error'] = 'Could not create HTTPS self-signed certificate'
            return
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    httpd.serve_forever()

class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path=urllib.parse.urlparse(path).path
        if path.startswith('/api/'): return str(APP_DIR/'index.html')
        if path.startswith('/media/'):
            rel=urllib.parse.unquote(path[len('/media/'):]).lstrip('/'); target=(MEDIA_ROOT/rel).resolve()
            try:
                if str(target).startswith(str(MEDIA_ROOT.resolve())) and target.is_file(): return str(target)
            except Exception: pass
            return str(APP_DIR/'index.html')
        if path.startswith('/games/'):
            rel=urllib.parse.unquote(path[len('/games/'):]).lstrip('/'); target=(GAME_ROOT/rel).resolve()
            try:
                if str(target).startswith(str(GAME_ROOT.resolve())) and target.is_file(): return str(target)
            except Exception: pass
            return str(APP_DIR/'index.html')
        p=APP_DIR/path.lstrip('/')
        if p.is_dir(): p=p/'index.html'
        if not p.exists(): p=APP_DIR/'index.html'
        return str(p)
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS'); self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'public, max-age=60'); super().end_headers()
    def do_OPTIONS(self): self.send_response(204); self.end_headers()
    def json_response(self, data):
        raw=json.dumps(data).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def read_json(self):
        try:
            length=int(self.headers.get('Content-Length','0') or 0); return json.loads(self.rfile.read(length).decode() or '{}') if length else {}
        except Exception: return {}
    def do_GET(self):
        if self.path.startswith('/api/status'): self.json_response(status()); return
        if self.path.startswith('/api/network/status'): self.json_response(network_status()); return
        if self.path.startswith('/api/wifi/scan'): self.json_response(wifi_scan()); return
        if self.path.startswith('/api/tailscale/status'): self.json_response(tailscale_status()); return
        if self.path.startswith('/api/field-ai/categories'): self.json_response(field_ai_categories()); return
        if self.path.startswith('/api/field-ai/status'): self.json_response(field_ai_status()); return
        if self.path.startswith('/api/field-ai/history'): self.json_response(field_ai_history()); return
        if self.path.startswith('/api/field-ai/corrections'): self.json_response(field_ai_corrections()); return
        if self.path.startswith('/api/vnc/status'): self.json_response(vnc_status()); return
        if self.path.startswith('/api/captive/status'): self.json_response(captive_status()); return
        if self.path.startswith('/api/noaa-weather'):
            qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); self.json_response(noaa_weather({k:v[-1] for k,v in qs.items()})); return
        if self.path.startswith('/api/weather'):
            qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); self.json_response(pi_weather({k:v[-1] for k,v in qs.items()})); return
        if self.path.startswith('/api/online-maintenance/log'): self.json_response(online_maintenance_log()); return
        if self.path.startswith('/api/media/library'): self.json_response(media_manifest()); return
        if self.path.startswith('/api/games/library'): self.json_response(game_library_status()); return
        if self.path.startswith('/api/plugins'): self.json_response(plugin_status()); return
        if self.path.startswith('/api/bluetooth/status'): self.json_response(bluetooth_status()); return
        if self.path.startswith('/api/sense'): self.json_response({'ok': True, 'sense': sense_snapshot(), 'state': read_state(), 'available_modes': SENSE_MODES, 'time': time.time()}); return
        return super().do_GET()
    def do_DELETE(self):
        if self.path.startswith('/api/field-ai/history'): self.json_response(field_ai_clear_history()); return
        self.send_error(404)
    def do_POST(self):
        payload=self.read_json()
        if self.path.startswith('/api/wifi-home'): self.json_response(connect_home_wifi(payload)); return
        if self.path.startswith('/api/wifi/scan'): self.json_response(wifi_scan(payload)); return
        if self.path.startswith('/api/wifi/save'): self.json_response(wifi_save_network(payload)); return
        if self.path.startswith('/api/wifi/connect'): self.json_response(wifi_connect_saved(payload)); return
        if self.path.startswith('/api/sense-mode'): self.json_response(set_sense_mode(payload.get('mode') or payload.get('sense_mode') or 'compass', payload)); return
        if self.path.startswith('/api/calibrate'): self.json_response(calibrate(payload.get('target') or 'all')); return
        if self.path.startswith('/api/field-ai/analyze'): self.json_response(field_ai_analyze(payload)); return
        if self.path.startswith('/api/field-ai/corrections/vote'): self.json_response(field_ai_vote_correction(payload)); return
        if self.path.startswith('/api/field-ai/corrections'): self.json_response(field_ai_add_correction(payload)); return
        if self.path.startswith('/api/bluetooth/scan'): self.json_response(bluetooth_scan(payload)); return
        if self.path.startswith('/api/bluetooth/action/'): self.json_response(bluetooth_action(self.path.rsplit('/',1)[-1], payload)); return
        if self.path.startswith('/api/command/'): self.json_response(command(self.path.rsplit('/',1)[-1], payload)); return
        self.send_error(404)

if __name__ == '__main__':
    threading.Thread(target=sense_loop, daemon=True).start(); threading.Thread(target=joystick_loop, daemon=True).start()
    os.chdir(str(APP_DIR))
    threading.Thread(target=lambda: serve_http(HTTPS_PORT, True), daemon=True).start()
    serve_http(PORT, False)
